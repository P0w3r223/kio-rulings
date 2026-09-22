"""Strażnik magazynu — pakiet `kio_tool/store/` (do 2026-09-22 `store.py`, ADR-0009), czyli
bramka fazy 1 po stronie zapisu.

Trzy własności, każda z powodem w nagłówku `store/magazyn.py` (dawniej `store.py`):

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


# --- schemat 4: `run_documents` odtworzone z dziennika żądań ----------------------------------

SHA_LISTY = hashlib.sha256(b'{"data": [], "has_more": false}').hexdigest()
"""Skrót odpowiedzi listy. Wiersza w `raw_versions` nie ma i mieć nie będzie, bo lista nie jest
dokumentem — odtworzenie ma ją odrzucić brakiem wersji, a nie listą wyjątków po adresie."""

TRESCI = {
    "atlas:a": b'{"slug": "wymyslony-a", "full_text": "tresc wymyslona a"}',
    "atlas:b": b'{"slug": "wymyslony-b", "full_text": "tresc wymyslona b"}',
    "atlas:c": b'{"slug": "wymyslony-c", "full_text": "tresc wymyslona c"}',
}


def sha(doc_id: str) -> str:
    return hashlib.sha256(TRESCI[doc_id]).hexdigest()


def chwila(minuta: int) -> str:
    return f"2026-09-18T12:{minuta:02d}:00Z"


def baza_schematu_1_z_pobranymi(sciezka: Path) -> None:
    """Schemat 1 z trzema dokumentami i dziennikiem, który pamięta, kto je przywiózł.

    Adres jest w każdym wierszu dziennika ten sam (`'u'`): `url_redacted` nie jest łącznikiem
    (reguła 22), więc implementacja, która by się o niego oparła, nie ma tu czego rozróżnić.
    Kolejność żądań (b, a, c) różni się od kolejności wersji w `raw_versions` (a, b, c), żeby
    `position` odtworzone z kolejności żądań nie mogło wyjść przypadkiem. `atlas:a` ma dwa
    żądania, bo pierwsze zerwało się po drodze — dokument jest jeden i wiersz ma być jeden.

    Trzy przebiegi: `stary` pobrał trzy dokumenty, `obcy` jeden, `pusty` sam listing.
    """
    with sqlite3.connect(sciezka) as p:
        p.executescript(SCHEMAT_1)
        for doc_id, tresc in TRESCI.items():
            p.execute(
                "INSERT INTO documents VALUES (?, 'atlas', ?, '[\"(napis wymyslony)\"]', "
                "'2024-01-15', ?, ?, ?)",
                (doc_id, doc_id.split(":")[1], TS, TS, sha(doc_id)),
            )
            p.execute(
                "INSERT INTO raw_versions VALUES (?, ?, ?, ?, '{}')",
                (doc_id, sha(doc_id), TS, tresc),
            )
        for run_id, zakres, status in (
            ("stary", "2024-01-01..2024-01-31", "przerwany"),
            ("obcy", "2024-02-01..2024-02-05", "zakonczony"),
            ("pusty", "2024-03-01..2024-03-02", "zakonczony"),
        ):
            p.execute(
                "INSERT INTO runs VALUES (?, 'atlas', ?, ?, ?, ?, NULL, NULL)",
                (run_id, zakres, TS, TS, status),
            )
        for run_id, minuta, skrot in (
            ("stary", 1, SHA_LISTY),
            ("stary", 2, sha("atlas:b")),
            ("stary", 3, sha("atlas:a")),
            ("stary", 4, sha("atlas:a")),
            ("stary", 5, sha("atlas:c")),
            ("obcy", 6, sha("atlas:c")),
            ("pusty", 7, SHA_LISTY),
        ):
            p.execute(
                "INSERT INTO requests_log VALUES (?, ?, 'GET', 'u', 200, 5, 10, ?, 'zgodny')",
                (run_id, chwila(minuta), skrot),
            )


def baza_schematu_3_z_luka(sciezka: Path) -> None:
    """Ta sama luka, ale na bazie stojącej już na wersji 3 — czyli tam, gdzie ona naprawdę jest.

    Budowana przez `Store` i cofnięta do wersji 3, nie z dosłownej kopii schematu 3: schemat 3
    różni się od bieżącego `_SCHEMA` wyłącznie numerem, więc kopia powtarzałaby `_SCHEMA` bez
    różnicy — inaczej niż `SCHEMAT_1`, który opisuje kształt, jakiego w kodzie już nie ma.
    """
    baza_schematu_1_z_pobranymi(sciezka)
    with Store.open(sciezka, clock=ZegarTestowy()):
        pass
    with sqlite3.connect(sciezka) as p:
        p.execute("DELETE FROM run_documents")
        p.execute("PRAGMA user_version = 3")


def powiazania(store: Store, run_id: str) -> list[tuple[str, int, int]]:
    return [
        (str(w["doc_id"]), int(w["position"]), int(w["nowy"]))
        for w in store._conn.execute(
            "SELECT doc_id, position, nowy FROM run_documents WHERE run_id = ? ORDER BY position",
            (run_id,),
        )
    ]


def test_backfill_odtwarza_dokumenty_przebiegu_w_kolejnosci_zadan(tmp_path: Path) -> None:
    """`eksportuj --run-id` dla przebiegu sprzed schematu 2 ma wreszcie co wydać.

    Pozycje wychodzą ciągłe od 1, kolejność bierze się z pierwszego żądania za dokument
    (b, a, c), a dwa żądania za `atlas:a` dają jeden wiersz, nie dwa.
    """
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1_z_pobranymi(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert powiazania(store, "stary") == [
            ("atlas:b", 1, 1),
            ("atlas:a", 2, 1),
            ("atlas:c", 3, 1),
        ]
        assert list(store.iter_run_documents("stary")) == ["atlas:b", "atlas:a", "atlas:c"]
        assert store.get_run("stary").dokumentow == 3


def test_odtworzony_dokument_jest_dla_przebiegu_nowy(tmp_path: Path) -> None:
    """`nowy = 1` nie jest założeniem: potok nie wysyła żądania za dokument, który już jest
    w bazie, więc żądanie zakończone wersją znaczy, że dokument był dla tego przebiegu nowy."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1_z_pobranymi(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.count_run_documents("stary", nowe=True) == 3
        assert store.count_run_documents("stary", nowe=False) == 0


def test_odpowiedz_listy_odpada_przez_brak_wersji_a_nie_przez_adres(tmp_path: Path) -> None:
    """Pięć żądań, trzy dokumenty: listing nie ma wiersza w `raw_versions`, więc wypada sam."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1_z_pobranymi(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.count_requests("stary") == 5
        assert store.count_run_documents("stary") == 3
        wersje = {
            str(w["content_sha256"])
            for w in store._conn.execute("SELECT content_sha256 FROM raw_versions")
        }
        assert SHA_LISTY not in wersje


def test_przebieg_bez_dokumentow_nie_dostaje_ani_jednego_wiersza(tmp_path: Path) -> None:
    """Pomiar filtru, który zwrócił zero trafień: `dokumentow = 0` jest prawdą o wyniku,
    a nie luką po migracji — i po backfillu ma nią zostać."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1_z_pobranymi(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.get_run("pusty").zadan == 1
        assert store.count_run_documents("pusty") == 0


def test_dokument_wraca_do_kazdego_przebiegu_ktory_o_niego_pytal(tmp_path: Path) -> None:
    """Odtworzenie idzie per przebieg: `obcy` dostaje swój jeden dokument z własną numeracją."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1_z_pobranymi(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert powiazania(store, "obcy") == [("atlas:c", 1, 1)]
        assert powiazania(store, "stary")[2] == ("atlas:c", 3, 1)


def test_backfill_zapala_sie_na_bazie_stojacej_juz_na_schemacie_3(tmp_path: Path) -> None:
    """Baza w wersji 3 to dokładnie ta, która lukę ma — migracja zaczepiona o wersję 1
    przeszłaby obok niej (nagłówek `store.py`, „Schemat 4")."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_3_z_luka(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.count_run_documents("stary") == 3
        assert store.count_run_documents("obcy") == 1


def test_przebieg_z_powiazaniami_zachowuje_swoje_wartosci_pierwotne(tmp_path: Path) -> None:
    """Tam, gdzie `position` i `nowy` są pierwotne, rekonstrukcja byłaby ich pogorszeniem:
    odtworzenie dałoby `obcy` pozycję 1 i `nowy = 1`, a pierwotne są 7 i 0."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_3_z_luka(sciezka)
    with sqlite3.connect(sciezka) as p:
        p.execute("INSERT INTO run_documents VALUES ('obcy', 'atlas:c', 7, 0)")

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert powiazania(store, "obcy") == [("atlas:c", 7, 0)]
        assert store.count_run_documents("stary") == 3


def test_przebieg_z_czescia_powiazan_zostaje_pominiety_w_calosci(tmp_path: Path) -> None:
    """Przypięcie decyzji o zasięgu: `NOT EXISTS` obejmuje cały przebieg, nie brakujący wiersz.

    `stary` ma tu jedno powiązanie z trzech — kształt przebiegu przerwanego pod schematem 1
    i wznowionego pod schematem 2, który powiązał wyłącznie to, co przeszło po wznowieniu.
    Backfill takiego przebiegu **świadomie** nie podejmuje i luka po `atlas:a` oraz `atlas:b`
    zostaje: dopisanie brakujących wierszy zmieszałoby w jednej tabeli wartości pierwotne
    z rekonstruowanymi, a znacznika, który by je rozróżnił, `run_documents` nie ma (powód
    stoi w docstringu `store._odtworz_powiazania_sprzed_schematu_2`, „Zasięg jest węższy").
    Jawna luka jest tańsza niż niejawna mieszanina — i to jest wybór do obalenia ADR-em,
    a nie stan zastany, więc jego zmiana ma się tu zapalić.
    """
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_3_z_luka(sciezka)
    with sqlite3.connect(sciezka) as p:
        p.execute("INSERT INTO run_documents VALUES ('stary', 'atlas:c', 3, 1)")

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert powiazania(store, "stary") == [("atlas:c", 3, 1)]


def baza_z_blizniakiem(sciezka: Path) -> None:
    """Schemat 1, w którym `atlas:blizniak` niesie **te same bajty** co `atlas:a`.

    Klucz `raw_versions` to `(doc_id, content_sha256)`, więc dwa dokumenty o identycznej treści
    są stanem reprezentowalnym — a żądanie, które te bajty przywiozło, przestaje wskazywać
    jeden dokument. W dzienniku `stary` nic się nie zmienia: to ta sama baza co wszędzie wyżej,
    plus jeden wiersz w `documents` i jeden w `raw_versions`.
    """
    baza_schematu_1_z_pobranymi(sciezka)
    with sqlite3.connect(sciezka) as p:
        p.execute(
            "INSERT INTO documents VALUES ('atlas:blizniak', 'atlas', 'blizniak', "
            "'[\"(napis wymyslony)\"]', '2024-01-15', ?, ?, ?)",
            (TS, TS, sha("atlas:a")),
        )
        p.execute(
            "INSERT INTO raw_versions VALUES ('atlas:blizniak', ?, ?, ?, '{}')",
            (sha("atlas:a"), TS, TRESCI["atlas:a"]),
        )


def test_skrot_wskazujacy_na_dwa_dokumenty_nie_daje_zadnego_wiersza(tmp_path: Path) -> None:
    """Skrót niejednoznaczny odpada w całości: ani dokument zgadnięty, ani oba.

    Obie wersje leżą w korpusie i obie są prawdziwe — to żądanie przestało je rozróżniać.
    Przypięcie decyzji, nie stanu zastanego: jawna luka jest w tym projekcie tańsza od
    zgadnięcia, bo powiązanie z dokumentem, o który przebieg nie pytał, byłoby zdaniem
    prawdziwie wyglądającym i fałszywym (docstring `_odtworz_powiazania_sprzed_schematu_2`).
    """
    sciezka = tmp_path / "stary.sqlite"
    baza_z_blizniakiem(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.has_document("atlas:blizniak") and store.count("raw_versions") == 4
        zwiazane = {
            str(w["doc_id"]) for w in store._conn.execute("SELECT doc_id FROM run_documents")
        }
        assert "atlas:a" not in zwiazane, "zgadnięty pierwowzór byłby zgadnięciem"
        assert "atlas:blizniak" not in zwiazane, "bliźniak też"


def test_niejednoznaczny_skrot_zabiera_swoj_dokument_a_nie_caly_przebieg(
    tmp_path: Path,
) -> None:
    """Odrzucenie jest per skrót: `atlas:b` i `atlas:c` wracają, numeracja jest ciągła po tym,
    co zostało (1, 2), a nie dziurawa po tym, co odpadło."""
    sciezka = tmp_path / "stary.sqlite"
    baza_z_blizniakiem(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert powiazania(store, "stary") == [("atlas:b", 1, 1), ("atlas:c", 2, 1)]
        assert powiazania(store, "obcy") == [("atlas:c", 1, 1)]


def test_backfill_jest_idempotentny_przy_kolejnym_otwarciu(tmp_path: Path) -> None:
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1_z_pobranymi(sciezka)
    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        pierwsze = powiazania(store, "stary")

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert powiazania(store, "stary") == pierwsze
        assert store.count("run_documents") == 4
    with sqlite3.connect(sciezka) as p:
        assert p.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_nieudany_backfill_cofa_caly_lancuch_migracji(tmp_path: Path) -> None:
    """Backfill stoi w tej samej transakcji co `CREATE TABLE` i `ALTER TABLE` przed nim.

    Awaria przy drugim powiązaniu zostawia bazę w wersji 1 z nietkniętymi danymi, a nie
    w wersji, której żaden numer nie opisuje: bez tabeli `run_documents`, bez kolumny
    `runs.fingerprint` i z trzema wersjami surowymi na miejscu.
    """
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1_z_pobranymi(sciezka)
    oryginalne = Store.link_run_document
    wywolania: list[str] = []

    def pekajace(self: Store, run_id: str, doc_id: str, *, position: int, nowy: bool) -> None:
        wywolania.append(doc_id)
        if len(wywolania) == 2:
            raise sqlite3.OperationalError("database or disk is full")
        oryginalne(self, run_id, doc_id, position=position, nowy=nowy)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Store, "link_run_document", pekajace)
        with pytest.raises(StoreError, match="Baza"):
            Store.open(sciezka, clock=ZegarTestowy())

    with sqlite3.connect(sciezka) as p:
        assert p.execute("PRAGMA user_version").fetchone()[0] == 1
        tabele = {str(w[0]) for w in p.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "run_documents" not in tabele
        assert "fingerprint" not in {str(w[1]) for w in p.execute("PRAGMA table_info(runs)")}
        assert p.execute("SELECT COUNT(*) FROM raw_versions").fetchone()[0] == 3


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
        store.index_document(doc_id, sha, m, None)


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


# --- schemat 5: `requests_log.proba` (ADR-0007 Z-8) -----------------------------------------


def zaloguj(store: Store, run_id: str, *, proba: int = 1, status: int | None = 200) -> None:
    store.log_request(
        run_id,
        ts=TS,
        metoda="GET",
        url="https://wymyslony.example/dokument/x",
        status=status,
        ms=5,
        bajtow=10,
        sha256=None,
        ksztalt="zgodny",
        proba=proba,
    )


def baza_schematu_4(sciezka: Path) -> None:
    """Baza na wersji 4 z jednym wierszem dziennika — jak korpus sprzed ADR-0007.

    Budowana przez `Store` i cofnięta, jak `baza_schematu_3_z_luka`: schemat 4 różni się od
    bieżącego wyłącznie brakiem kolumny `proba`, więc ta jedna różnica jest tu zdjęta wprost."""
    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        zaloguj(store, start(store))
    with sqlite3.connect(sciezka) as p:
        p.execute("ALTER TABLE requests_log DROP COLUMN proba")
        p.execute("PRAGMA user_version = 4")


def test_migracja_4_do_5_doklada_probe_i_daje_starym_wierszom_jedynke(tmp_path: Path) -> None:
    """Przed ADR-0007 żaden kanał nie ponawiał, więc 1 jest prawdą o starych wierszach, nie
    zgadywaniem — a liczba ponowień przebiegu sprzed migracji wychodzi zero, nie `NULL`."""
    sciezka = tmp_path / "czwarty.sqlite"
    baza_schematu_4(sciezka)
    with sqlite3.connect(sciezka) as p:
        assert "proba" not in {w[1] for w in p.execute("PRAGMA table_info(requests_log)")}

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        run_id = str(store._conn.execute("SELECT run_id FROM runs").fetchone()[0])
        assert store.count_requests(run_id) == 1
        assert store.count_requests(run_id, ponowienia=True) == 0
        zaloguj(store, run_id, proba=2)
        assert store.count_requests(run_id) == 2
        assert store.count_requests(run_id, ponowienia=True) == 1

    with sqlite3.connect(sciezka) as p:
        assert p.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert [w[0] for w in p.execute("SELECT proba FROM requests_log ORDER BY rowid")] == [1, 2]


def test_migracja_do_5_nie_wywraca_sie_na_kolumnie_ktora_juz_jest(tmp_path: Path) -> None:
    """Obecność kolumny sprawdzana, nie zakładana (jak `_migruj_do_3`): baza z `proba`, ale
    z wersją 4, nie może skończyć się `duplicate column name` przy otwarciu."""
    sciezka = tmp_path / "czwarty.sqlite"
    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        zaloguj(store, start(store), proba=3)
    with sqlite3.connect(sciezka) as p:
        p.execute("PRAGMA user_version = 4")

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store._conn.execute("SELECT proba FROM requests_log").fetchone()[0] == 3


def test_migracja_ze_schematu_1_dochodzi_do_kolumny_proba(tmp_path: Path) -> None:
    """Cały łańcuch 1 → 5: baza z etapu III dostaje `proba` tak samo jak baza z wersji 4."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1(sciezka)

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.count_requests("atlas-stary", ponowienia=True) == 0
        assert store._conn.execute("SELECT proba FROM requests_log").fetchone()[0] == 1


def test_count_requests_z_ponowieniami_liczy_proby_od_drugiej_w_jednym_przebiegu(
    store: Store,
) -> None:
    pierwszy = start(store)
    drugi = start(store, "2024-02-01..2024-02-29")
    for proba in (1, 2, 3):
        zaloguj(store, pierwszy, proba=proba, status=None)
    zaloguj(store, pierwszy)
    zaloguj(store, drugi, proba=2)

    assert store.count_requests(pierwszy) == 4
    assert store.count_requests(pierwszy, ponowienia=True) == 2
    assert store.count_requests(drugi, ponowienia=True) == 1, "cudzy przebieg się nie wlicza"
