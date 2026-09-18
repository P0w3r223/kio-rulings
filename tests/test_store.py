"""Strażnik magazynu — `kio_tool/store.py`, czyli bramka fazy 1 po stronie zapisu.

Trzy własności, każda z powodem w nagłówku `store.py`:

1. **Ta sama treść drugi raz to jeden wiersz** — `INSERT OR IGNORE` na `(doc_id, content_sha256)`
   jest całą treścią bramki „przerwany i wznowiony bez duplikatów" (ADR-0001 2.3).
2. **Skrót liczy się z tego, co zapisano** — reguła 19 w brzmieniu ADR-0005 Z-5, część zapisu:
   `content_sha256` ma się zgadzać z bajtami w `content_bytes`, a skrót podany przez kanał, który
   się nie zgadza, jest odrzucany, nie przyjmowany na wiarę.
3. **Wznowienie od `ostatnia_strona`** — przerwany przebieg tego samego kanału i zakresu wraca
   jako `w_toku` ze swoim punktem kontrolnym; zakończony nie wraca.

Baza `":memory:"`, zegar testowy; żaden test nie dotyka sieci ani prawdziwego dysku poza
`tmp_path` w jednym teście o ścieżce pliku.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from kio_tool.clock import utc_iso
from kio_tool.config import register_secret
from kio_tool.criteria import Criteria
from kio_tool.docid import SourceName, document_id
from kio_tool.errors import StoreError
from kio_tool.ratelimit import RequestStamp
from kio_tool.store import SCHEMA_VERSION, Filtr, Metryka, Store
from tests.wsparcie_sondy import KLUCZ_TESTOWY, ZegarTestowy

TRESC = b'{"slug": "wymyslony-slug-1", "full_text": "tresc wymyslona"}'
TRESC_INNA = b'{"slug": "wymyslony-slug-1", "full_text": "tresc wymyslona, sprostowana"}'
TS = "2026-09-18T12:00:00Z"


@pytest.fixture
def store() -> Store:
    return Store.open(":memory:", clock=ZegarTestowy())


def start(store: Store, zakres: str = "2024-01-01..2024-01-31", kanal: str = "atlas") -> str:
    """Przebieg z kryteriami odtworzonymi z etykiety zakresu — jak robi to `pipeline`."""
    kryteria = Criteria(
        od=date.fromisoformat(zakres.split("..")[0]), do=date.fromisoformat(zakres.split("..")[1])
    )
    return store.start_run(
        kanal=kanal,
        zakres=zakres,
        started_at=TS,
        kryteria=kryteria.canonical_json(),
        fingerprint=kryteria.fingerprint(),
    )


def odcisk(zakres: str = "2024-01-01..2024-01-31") -> str:
    od, do = zakres.split("..")
    return Criteria(od=date.fromisoformat(od), do=date.fromisoformat(do)).fingerprint()


def zapisz(
    store: Store, doc_id: str, tresc: bytes = TRESC, *, data_wydania: str | None = None
) -> tuple[str, bool]:
    with store.transakcja():
        store.upsert_document(
            doc_id=doc_id,
            source="atlas",
            source_ref=doc_id.split(":", 1)[1],
            sygnatury=("(napis wymyslony)",),
            data_wydania=data_wydania,
            seen_at=TS,
            content_sha256=hashlib.sha256(tresc).hexdigest(),
        )
        return store.add_raw_version(doc_id=doc_id, content=tresc, fetched_at=TS, fetch_meta={})


# --- wersje surowe: bajty w całości, skrót z tego, co zapisano ------------------------------


def test_dwukrotny_zapis_tej_samej_wersji_daje_jeden_wiersz(store: Store) -> None:
    sha, nowa = zapisz(store, "atlas:wymyslony-slug-1")
    sha_2, nowa_2 = zapisz(store, "atlas:wymyslony-slug-1")

    assert (nowa, nowa_2) == (True, False)
    assert sha == sha_2
    assert store.count("raw_versions") == 1
    assert store.count("documents") == 1


def test_inna_tresc_daje_druga_wersje_nigdy_nadpisanie(store: Store) -> None:
    zapisz(store, "atlas:wymyslony-slug-1", TRESC)
    zapisz(store, "atlas:wymyslony-slug-1", TRESC_INNA)

    assert store.count("raw_versions") == 2
    assert store.count("documents") == 1


def test_content_sha256_zgadza_sie_z_bajtami_w_bazie(store: Store) -> None:
    """Reguła 19, część zapisu: skrót w wierszu jest skrótem **tych** bajtów, a bajty są całe."""
    sha, _ = zapisz(store, "atlas:wymyslony-slug-1")
    wiersz = store._conn.execute(
        "SELECT content_sha256, content_bytes FROM raw_versions"
    ).fetchone()

    assert wiersz["content_bytes"] == TRESC
    assert wiersz["content_sha256"] == sha == hashlib.sha256(TRESC).hexdigest()


def test_skrot_niezgodny_z_bajtami_jest_odrzucany(store: Store) -> None:
    with store.transakcja():
        store.upsert_document(
            doc_id="atlas:x",
            source="atlas",
            source_ref="x",
            sygnatury=(),
            data_wydania=None,
            seen_at=TS,
            content_sha256="a" * 64,
        )
        with pytest.raises(StoreError, match="nie zgadza"):
            store.add_raw_version(
                doc_id="atlas:x",
                content=TRESC,
                fetched_at=TS,
                fetch_meta={},
                expected_sha256="a" * 64,
            )


def test_fetch_meta_jest_maskowane(store: Store) -> None:
    register_secret(KLUCZ_TESTOWY)
    with store.transakcja():
        store.upsert_document(
            doc_id="atlas:x",
            source="atlas",
            source_ref="x",
            sygnatury=(),
            data_wydania=None,
            seen_at=TS,
            content_sha256=hashlib.sha256(TRESC).hexdigest(),
        )
        store.add_raw_version(
            doc_id="atlas:x", content=TRESC, fetched_at=TS, fetch_meta={"echo": KLUCZ_TESTOWY}
        )
    meta = str(store._conn.execute("SELECT fetch_meta FROM raw_versions").fetchone()[0])

    assert KLUCZ_TESTOWY not in meta and "<token>" in meta


# --- dokumenty: tożsamość z `docid`, nie składana tutaj ---------------------------------------


def test_dwie_pisownie_sluga_to_jeden_dokument(store: Store) -> None:
    """Mina 1 od strony magazynu: `doc_id` przychodzi z `document_id(..., ref_case="lower")`,
    więc druga pisownia tego samego sluga trafia w ten sam wiersz, nie obok niego."""
    pierwszy = document_id(SourceName("atlas"), "kio-1205-20", ref_case="lower")
    drugi = document_id(SourceName("atlas"), "KIO-1205-20", ref_case="lower")
    zapisz(store, pierwszy)
    zapisz(store, drugi)

    assert pierwszy == drugi
    assert store.count("documents") == 1
    assert store.has_document(pierwszy)


def test_has_document_odroznia_zapisany_od_niezapisanego(store: Store) -> None:
    assert not store.has_document("atlas:x")
    zapisz(store, "atlas:x")
    assert store.has_document("atlas:x")


def test_upsert_zachowuje_first_seen_at_i_aktualizuje_last_seen_at(store: Store) -> None:
    zapisz(store, "atlas:x")
    with store.transakcja():
        store.upsert_document(
            doc_id="atlas:x",
            source="atlas",
            source_ref="x",
            sygnatury=(),
            data_wydania="2020-06-16",
            seen_at="2026-09-19T12:00:00Z",
            content_sha256="b" * 64,
        )
    wiersz = store._conn.execute(
        "SELECT first_seen_at, last_seen_at, current_sha256 FROM documents"
    ).fetchone()

    assert (wiersz["first_seen_at"], wiersz["last_seen_at"]) == (TS, "2026-09-19T12:00:00Z")
    assert wiersz["current_sha256"] == "b" * 64


def test_transakcja_cofa_wszystko_przy_wyjatku(store: Store) -> None:
    with pytest.raises(RuntimeError), store.transakcja():
        store.upsert_document(
            doc_id="atlas:x",
            source="atlas",
            source_ref="x",
            sygnatury=(),
            data_wydania=None,
            seen_at=TS,
            content_sha256="a" * 64,
        )
        raise RuntimeError("awaria w polowie (wymyslona)")

    assert store.count("documents") == 0
    assert not store._conn.in_transaction


# --- przebiegi: start, punkt kontrolny, koniec, wznowienie ------------------------------------


def test_wznowienie_wraca_do_przerwanego_przebiegu_od_ostatniej_strony(store: Store) -> None:
    run_id = start(store)
    store.checkpoint(run_id, 3)
    store.finish_run(run_id, status="przerwany", finished_at=TS, powod="Ctrl+C")

    znaleziony = store.find_run(odcisk(), ("przerwany",))
    assert znaleziony is not None and znaleziony.run_id == run_id
    wznowiony = store.resume_run(znaleziony.run_id)

    assert wznowiony.run_id == run_id
    assert wznowiony.ostatnia_strona == 3
    assert wznowiony.status == "w_toku" and wznowiony.finished_at is None


def test_zakonczony_przebieg_ani_inne_kryteria_nie_wznawiaja_sie(store: Store) -> None:
    run_id = start(store)
    store.finish_run(run_id, status="zakonczony", finished_at=TS)
    inny = start(store, "2024-02-01..2024-02-29")
    store.finish_run(inny, status="przerwany", finished_at=TS)

    assert store.find_run(odcisk(), ("przerwany",)) is None
    with pytest.raises(StoreError, match="przerwany"):
        store.resume_run(run_id)


def test_finish_run_odrzuca_status_spoza_listy(store: Store) -> None:
    run_id = start(store)

    with pytest.raises(StoreError):
        store.finish_run(run_id, status="w_toku", finished_at=TS)
    with pytest.raises(StoreError):
        store.finish_run(run_id, status="gotowe", finished_at=TS)


def test_get_run_nieznanego_przebiegu(store: Store) -> None:
    with pytest.raises(StoreError):
        store.get_run("nie-ma")


# --- dziennik żądań ---------------------------------------------------------------------------


def test_log_request_maskuje_adres_i_jest_trwaly_poza_transakcja(store: Store) -> None:
    register_secret(KLUCZ_TESTOWY)
    run_id = start(store)

    store.log_request(
        run_id,
        ts=TS,
        metoda="GET",
        url=f"https://atlasprzetargow.pl/api/kio?key={KLUCZ_TESTOWY}",
        status=200,
        ms=12,
        bajtow=100,
        sha256="c" * 64,
        ksztalt="zgodny",
    )
    wiersz = store._conn.execute("SELECT url_redacted FROM requests_log").fetchone()

    assert KLUCZ_TESTOWY not in wiersz["url_redacted"] and "<token>" in wiersz["url_redacted"]
    assert not store._conn.in_transaction, "wpis dziennika nie zostawia otwartej transakcji"


def test_request_stamps_odtwarza_historie_kanalu_dla_limitera(store: Store) -> None:
    zegar = ZegarTestowy()
    run_id = start(store)
    ts = utc_iso(zegar.wall())
    store.log_request(
        run_id, ts=ts, metoda="GET", url="u", status=429, ms=1, bajtow=0, sha256=None, ksztalt="—"
    )
    obcy = start(store, kanal="uzp")
    store.log_request(
        obcy, ts=ts, metoda="GET", url="v", status=200, ms=1, bajtow=0, sha256=None, ksztalt="—"
    )

    znaczniki = store.request_stamps("atlas", zegar.wall() - 60)

    assert znaczniki == [RequestStamp(zegar.wall(), "u", 429)]
    assert store.request_stamps("atlas", zegar.wall() + 1) == []


def test_count_nieznanej_tabeli_jest_bledem_nie_zapytaniem(store: Store) -> None:
    with pytest.raises(StoreError):
        store.count("sqlite_master")


def test_open_tworzy_katalog_i_przelacza_na_wal(tmp_path: Path) -> None:
    sciezka = tmp_path / "glebiej" / "korpus.sqlite"

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.journal_mode == "wal"
        run_id = start(store)

    with sqlite3.connect(sciezka) as polaczenie:
        assert polaczenie.execute("SELECT run_id FROM runs").fetchone()[0] == run_id
        assert polaczenie.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


# --- migracja 1 → 2: baza „jak z etapu III" przeżywa z danymi -------------------------------

SCHEMAT_1 = """
CREATE TABLE documents (
  doc_id TEXT PRIMARY KEY, source TEXT NOT NULL, source_ref TEXT NOT NULL, sygnatury TEXT NOT NULL,
  data_wydania TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
  current_sha256 TEXT NOT NULL, UNIQUE (source, source_ref));
CREATE TABLE raw_versions (
  doc_id TEXT NOT NULL REFERENCES documents(doc_id), content_sha256 TEXT NOT NULL,
  fetched_at TEXT NOT NULL, content_bytes BLOB NOT NULL, fetch_meta TEXT NOT NULL,
  PRIMARY KEY (doc_id, content_sha256));
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, kanal TEXT NOT NULL, zakres TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('w_toku','zakonczony','przerwany','blad')),
  ostatnia_strona INTEGER, powod TEXT);
CREATE TABLE requests_log (
  run_id TEXT NOT NULL REFERENCES runs(run_id), ts TEXT NOT NULL, metoda TEXT NOT NULL,
  url_redacted TEXT NOT NULL, status INTEGER, ms INTEGER NOT NULL, bajtow INTEGER NOT NULL,
  sha256 TEXT, ksztalt TEXT NOT NULL);
CREATE INDEX requests_log_ts_idx ON requests_log(ts);
PRAGMA user_version = 1;
"""
"""Schemat 1 dosłownie ze `store.py` sprzed etapu IV (2026-09-18) — kształt bazy, w której trwa
prawdziwy przebieg `pobierz` za styczeń 2024. Kopia jest tu celowo: migracja ma być sprawdzana
wobec tego, co **było**, a nie wobec bieżącego `_SCHEMA` z odjętymi kolumnami."""


def baza_schematu_1(sciezka: Path) -> None:
    """Baza w schemacie 1 z dokumentem, dwiema wersjami, przerwanym przebiegiem i dziennikiem."""
    with sqlite3.connect(sciezka) as p:
        p.executescript(SCHEMAT_1)
        p.execute(
            "INSERT INTO documents VALUES ('atlas:x', 'atlas', 'x', '[\"(napis wymyslony)\"]', "
            "'2024-01-15', ?, ?, ?)",
            (TS, TS, hashlib.sha256(TRESC_INNA).hexdigest()),
        )
        for tresc in (TRESC, TRESC_INNA):
            p.execute(
                "INSERT INTO raw_versions VALUES ('atlas:x', ?, ?, ?, '{}')",
                (hashlib.sha256(tresc).hexdigest(), TS, tresc),
            )
        p.execute(
            "INSERT INTO runs VALUES ('atlas-stary', 'atlas', '2024-01-01..2024-01-31', ?, ?, "
            "'przerwany', 2, 'Ctrl+C')",
            (TS, TS),
        )
        p.execute(
            "INSERT INTO runs VALUES ('atlas-dziwny', 'atlas', 'etykieta bez dat', ?, ?, "
            "'zakonczony', NULL, NULL)",
            (TS, TS),
        )
        p.execute(
            "INSERT INTO requests_log VALUES ('atlas-stary', ?, 'GET', 'u', 200, 5, 10, NULL, "
            "'zgodny')",
            (TS,),
        )


def test_migracja_1_do_2_zachowuje_dokumenty_wersje_przebiegi_i_dziennik(tmp_path: Path) -> None:
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.count("documents") == 1
        assert store.count("raw_versions") == 2
        assert store.count("runs") == 2
        assert store.count("requests_log") == 1
        assert store.count("run_documents") == 0 and store.count("metadata") == 0
        assert store.has_document("atlas:x")
        wersja = store._conn.execute("SELECT content_bytes FROM raw_versions ORDER BY rowid")
        assert [bytes(w[0]) for w in wersja] == [TRESC, TRESC_INNA]

    with sqlite3.connect(sciezka) as p:
        assert p.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        kolumny = {w[1] for w in p.execute("PRAGMA table_info(runs)")}
        assert {"kryteria", "fingerprint"} <= kolumny


def test_migracja_dopisuje_odcisk_przebiegom_z_etykieta_dat_i_zostawia_pusty_innym(
    tmp_path: Path,
) -> None:
    """Przebieg przerwany pod schematem 1 wznawia się pod schematem 2 tym samym poleceniem."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        stary = store.get_run("atlas-stary")
        assert stary.fingerprint == odcisk("2024-01-01..2024-01-31")
        assert stary.kryteria is not None
        assert Criteria.z_json(stary.kryteria) == Criteria(
            od=date(2024, 1, 1), do=date(2024, 1, 31)
        )
        assert stary.ostatnia_strona == 2 and stary.status == "przerwany"
        znaleziony = store.find_run(odcisk("2024-01-01..2024-01-31"), ("przerwany",))
        assert znaleziony is not None and znaleziony.run_id == "atlas-stary"
        dziwny = store.get_run("atlas-dziwny")
        assert dziwny.fingerprint is None and dziwny.kryteria is None


def test_migracja_jest_idempotentna_i_odmawia_bazy_z_przyszlosci(tmp_path: Path) -> None:
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1(sciezka)
    with Store.open(sciezka, clock=ZegarTestowy()):
        pass
    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.count("runs") == 2
    with sqlite3.connect(sciezka) as p:
        p.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(StoreError, match="schemat"):
        Store.open(sciezka, clock=ZegarTestowy())


def test_przerwana_migracja_nie_zostawia_bazy_w_polowie(tmp_path: Path) -> None:
    """Jedna transakcja: kolumna dopisana, a wersja nie — to jest stan, którego nie ma."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1(sciezka)
    with sqlite3.connect(sciezka) as p:
        p.execute("ALTER TABLE runs ADD COLUMN kryteria TEXT")

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.get_run("atlas-stary").fingerprint is not None


# --- run_documents: każdy kandydat związany z przebiegiem, nowy i pominięty --------------------


def test_run_documents_wiaze_nowego_i_pominietego_w_kolejnosci_kandydatow(store: Store) -> None:
    run_id = start(store)
    zapisz(store, "atlas:a")
    zapisz(store, "atlas:b")
    store.link_run_document(run_id, "atlas:a", position=1, nowy=True)
    store.link_run_document(run_id, "atlas:b", position=2, nowy=False)

    assert list(store.iter_run_documents(run_id)) == ["atlas:a", "atlas:b"]
    assert store.count_run_documents(run_id) == 2
    assert store.count_run_documents(run_id, nowe=True) == 1
    assert store.count_run_documents(run_id, nowe=False) == 1
    assert store.get_run(run_id).dokumentow == 2


def test_ponowne_powiazanie_po_wznowieniu_zostawia_pierwszy_wiersz(store: Store) -> None:
    run_id = start(store)
    zapisz(store, "atlas:a")
    store.link_run_document(run_id, "atlas:a", position=1, nowy=True)

    store.link_run_document(run_id, "atlas:a", position=7, nowy=False)

    assert store.count_run_documents(run_id, nowe=True) == 1
    assert store.count_run_documents(run_id) == 1


def test_iter_documents_po_przebiegu_zwraca_wylacznie_objete_w_kolejnosci_pozycji(
    store: Store,
) -> None:
    run_id = start(store)
    for doc_id in ("atlas:c", "atlas:a", "atlas:b"):
        zapisz(store, doc_id)
    store.link_run_document(run_id, "atlas:b", position=1, nowy=True)
    store.link_run_document(run_id, "atlas:a", position=2, nowy=False)

    assert [d.doc_id for d in store.iter_documents(run_id=run_id)] == ["atlas:b", "atlas:a"]
    assert [d.doc_id for d in store.iter_documents()] == ["atlas:a", "atlas:b", "atlas:c"]


# --- list_runs: filtr w zapytaniu, liczba z bazy -------------------------------------------------


def test_list_runs_filtruje_w_zapytaniu_a_nie_po_wyniku_limit(store: Store) -> None:
    """Lekcja z `ceidg-tool` (`store.py:573`): przerwany przebieg na pozycji 26 ma być widoczny
    przy `limit=20` z filtrem po statusie — inaczej `wznow` melduje, że nie ma czego wznawiać."""
    przerwany = store.start_run(
        kanal="atlas",
        zakres="z0",
        started_at="2026-09-01T00:00:00Z",
        kryteria="{}",
        fingerprint="f0",
    )
    store.finish_run(przerwany, status="przerwany", finished_at=TS)
    for numer in range(25):
        run_id = store.start_run(
            kanal="atlas",
            zakres=f"z{numer + 1}",
            started_at=f"2026-09-02T00:00:{numer:02d}Z",
            kryteria="{}",
            fingerprint=f"f{numer + 1}",
        )
        store.finish_run(run_id, status="zakonczony", finished_at=TS)

    tylko_przerwane = store.list_runs(limit=20, statuses=("przerwany",))

    assert [p.run_id for p in tylko_przerwane] == [przerwany]
    assert len(store.list_runs(limit=20)) == 20
    assert store.count_runs() == 26
    assert store.list_runs(limit=20, statuses=()) == []


def test_find_run_bierze_najnowszy_o_tym_odcisku_i_statusie(store: Store) -> None:
    pierwszy = start(store)
    store.finish_run(pierwszy, status="przerwany", finished_at=TS)
    drugi = store.start_run(
        kanal="atlas",
        zakres="2024-01-01..2024-01-31",
        started_at="2026-09-19T00:00:00Z",
        kryteria="{}",
        fingerprint=odcisk(),
    )
    store.finish_run(drugi, status="przerwany", finished_at=TS)

    znaleziony = store.find_run(odcisk(), ("przerwany",))

    assert znaleziony is not None and znaleziony.run_id == drugi
    assert store.find_run(odcisk(), ("zakonczony",)) is None


# --- metadane i FTS5 ---------------------------------------------------------------------------


def metryka(tresc: str, **zmiany: object) -> Metryka:
    pola: dict[str, object] = {
        "parse_version": 1,
        "sygnatura_glowna": "(napis wymyslony)",
        "sygnatury": ("(napis wymyslony)",),
        "data_wydania": "2024-01-15",
        "data_rozprawy": None,
        "rodzaj": "wyrok",
        "rozstrzygniecie": "oddalono",
        "rozstrzygniecie_surowe": None,
        "przewodniczacy": "(przewodnicząca wymyślona)",
        "odwolujacy": "(odwołujący wymyślony)",
        "zamawiajacy": "(zamawiający wymyślony)",
        "przepisy": ("art. 1 wymyślony",),
        "koszty": None,
        "url_zrodla": None,
        "tresc": tresc,
    }
    pola.update(zmiany)
    return Metryka(**pola)  # type: ignore[arg-type]


def zaindeksuj(store: Store, doc_id: str, tresc: str, **zmiany: object) -> None:
    """Dokument z datą w `documents` (jak z kandydata listy) i metadanymi (jak z parsera)."""
    m = metryka(tresc, **zmiany)
    sha, _ = zapisz(store, doc_id, tresc.encode(), data_wydania=m.data_wydania)
    with store.transakcja():
        store.index_document(doc_id, sha, m)


def test_szukaj_zwraca_trafienia_z_liczbami_z_bazy(store: Store) -> None:
    """Mina 2: liczby w wyniku pochodzą z tabel, nie z etykiety — dokument niezaindeksowany
    jest w korpusie, a nie w indeksie, i wynik ma to powiedzieć."""
    zaindeksuj(store, "atlas:a", "Izba oddala odwołanie w całości (napis wymyślony)")
    zaindeksuj(
        store, "atlas:b", "Izba umarza postępowanie (napis wymyślony)", rozstrzygniecie="umorzono"
    )
    zapisz(store, "atlas:c", b"bez indeksu")

    wynik = store.szukaj("oddala odwołanie", limit=10)

    assert wynik.w_korpusie == 3 == store.count("documents")
    assert wynik.zaindeksowanych == 2 == store.count_indexed()
    assert wynik.trafien == 1 and [t.doc_id for t in wynik.trafienia] == ["atlas:a"]
    assert wynik.trafienia[0].sygnatura == "(napis wymyslony)"
    assert "oddala" in wynik.trafienia[0].fragment


def test_szukaj_z_filtrem_po_rozstrzygnieciu_i_datach_liczy_dokumenty_bez_daty(
    store: Store,
) -> None:
    zaindeksuj(store, "atlas:a", "wspólne słowo wymyślone", rozstrzygniecie="oddalono")
    zaindeksuj(store, "atlas:b", "wspólne słowo wymyślone", rozstrzygniecie="umorzono")
    zaindeksuj(store, "atlas:c", "wspólne słowo wymyślone", data_wydania=None)

    po_rozstrzygnieciu = store.szukaj("wspólne słowo", Filtr(rozstrzygniecie=("umorzono",)))
    po_datach = store.szukaj("wspólne słowo", Filtr(od=date(2024, 1, 1), do=date(2024, 12, 31)))

    assert [t.doc_id for t in po_rozstrzygnieciu.trafienia] == ["atlas:b"]
    assert po_datach.trafien == 2 and po_datach.bez_daty_poza_filtrem == 1


def test_szukaj_sklada_ogonki_i_traktuje_fraze_jako_jeden_cytat(store: Store) -> None:
    zaindeksuj(store, "atlas:a", "Zamówienie publiczne na dostawę (napis wymyślony)")

    assert store.szukaj("zamowienie publiczne").trafien == 1
    assert store.szukaj("publiczne zamówienie").trafien == 0, "cytat, nie koniunkcja słów"
    assert store.szukaj('"cudzysłów" OR NOT "operator"').trafien == 0, (
        "operatory z wejścia są tekstem"
    )


def test_nowa_wersja_zastepuje_wiersz_fts_i_dodaje_wiersz_metadata(store: Store) -> None:
    zaindeksuj(store, "atlas:a", "pierwsza treść wymyślona")
    zaindeksuj(store, "atlas:a", "druga treść wymyślona")

    assert store.count("fts") == 1 and store.count("metadata") == 2
    assert store.szukaj("pierwsza treść").trafien == 0
    assert store.szukaj("druga treść").trafien == 1
    assert store.count_indexed() == 1


def test_versions_to_index_zwraca_brakujace_i_starsze_niz_wersja_odczytu(store: Store) -> None:
    zaindeksuj(store, "atlas:stary", "x", parse_version=1)
    zaindeksuj(store, "atlas:nowy", "y", parse_version=2)
    zapisz(store, "atlas:bez", b"z")

    assert sorted(d.doc_id for d in store.versions_to_index(2)) == ["atlas:bez", "atlas:stary"]
    assert sorted(d.doc_id for d in store.versions_to_index(None)) == [
        "atlas:bez",
        "atlas:nowy",
        "atlas:stary",
    ]


def test_iter_documents_z_filtrem_tekstowym_i_fraza(store: Store) -> None:
    zaindeksuj(store, "atlas:a", "oferta odrzucona (wymyślone)", przewodniczacy="Anna Wymyślona")
    zaindeksuj(store, "atlas:b", "oferta przyjęta (wymyślone)", przewodniczacy="Jan Wymyślony")

    assert [d.doc_id for d in store.iter_documents(Filtr(przewodniczacy="anna"))] == ["atlas:a"]
    assert [d.doc_id for d in store.iter_documents(Filtr(fraza="oferta przyjęta"))] == ["atlas:b"]
    assert [d.doc_id for d in store.iter_documents(Filtr(strona="%"))] == [], "`%` jest tekstem"
    assert store.count_documents(Filtr(rodzaj=("wyrok",))) == 2


def test_szukaj_odrzuca_limit_niedodatni(store: Store) -> None:
    with pytest.raises(StoreError):
        store.szukaj("x", limit=0)
