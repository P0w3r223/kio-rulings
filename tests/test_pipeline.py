"""Bramka fazy 1 w teście: przebieg przerwany w połowie i wznowiony **bez duplikatów**.

`pipeline.pobierz` jedzie tu prawdziwą ścieżką — prawdziwy `build_http_client` z atrapą
transportu, prawdziwy adapter Atlasu na złotym pliku listy, prawdziwy `Store` w pamięci —
a atrapa serwisu potrafi w wybranym momencie przerwać przebieg tak, jak przerwałby go operator
(`KeyboardInterrupt`) albo sieć (`httpx.ConnectError`). Dokumenty pod slugami z listy są
**wymyślone** (jeden złoty dokument nie starczy na stu kandydatów) i tak nazwane.

Cztery własności, których pilnuje ten plik: dokument już w bazie nie kosztuje żądania; próg
zgody odmawia zanim pierwsze żądanie po dokument wyjdzie; wiersz w `requests_log` powstaje
w chwili powrotu żądania, nie po całym przebiegu; `finish_run` zapisuje koniec także wtedy,
gdy przebieg wywrócił się w pół.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import date
from functools import partial
from pathlib import Path

import httpx
import pytest

from kio_tool import pipeline
from kio_tool.config import MAX_FILENAME_STEM, safe_filename
from kio_tool.criteria import Criteria
from kio_tool.docid import SourceName
from kio_tool.errors import ConfigError, ConsentMissingError, RateLimitError, TransportError
from kio_tool.httpclient import build_http_client
from kio_tool.progress import NullEvents
from kio_tool.source.contract import load_contract
from kio_tool.store import Store
from tests.wsparcie_sondy import UA_TESTOWY, ZegarTestowy

ZLOTE = Path(__file__).resolve().parent / "examples" / "atlas"
LISTA_BAJTY = (ZLOTE / "lista_20260918T103525Z.json").read_bytes()
LISTA = json.loads(LISTA_BAJTY)
KONTRAKT = load_contract(SourceName("atlas"))
KLUCZ = KONTRAKT.ksztalt.lista.klucz
MA_WIECEJ = KONTRAKT.ksztalt.lista.ma_wiecej
LICZNIK = KONTRAKT.ksztalt.lista.licznik
SLUGI = [rekord["slug"] for rekord in LISTA[KLUCZ]]
KRYTERIA = Criteria(od=date(2024, 1, 1), do=date(2024, 1, 31))


def strona(rekordy: list[dict[str, object]], *, ma_wiecej: bool, total: int) -> bytes:
    return json.dumps({KLUCZ: rekordy, MA_WIECEJ: ma_wiecej, LICZNIK: total}).encode()


def dokument(slug: str) -> bytes:
    """Dokument wymyślony w kształcie z kontraktu (pola wymagane i pole treści)."""
    return json.dumps(
        {
            "slug": slug,
            "primary_signature": f"(sygnatura wymyslona dla {slug})",
            "signatures": [f"(sygnatura wymyslona dla {slug})"],
            KONTRAKT.ksztalt.dokument.pole_tresci: f"tresc wymyslona {slug}",
        }
    ).encode()


class Serwer:
    """Atrapa Atlasu: strony listy z podanej sekwencji, dokumenty generowane; umie przerwać."""

    def __init__(
        self,
        strony: list[bytes] | None = None,
        *,
        przerwij_na_dokumencie: int | None = None,
        wyjatek: BaseException | None = None,
        odmowa_na_dokumencie: int | None = None,
        naglowki: Mapping[str, str] | None = None,
    ) -> None:
        self.strony = strony or [LISTA_BAJTY, strona([], ma_wiecej=False, total=LISTA[LICZNIK])]
        self.przerwij_na = przerwij_na_dokumencie
        self.wyjatek = wyjatek or KeyboardInterrupt()
        self.odmowa_na = odmowa_na_dokumencie
        """Od którego dokumentu serwis odpowiada 429. Odmowa jest **odpowiedzią**, nie wyjątkiem:
        `Retry-After` przychodzi w jej nagłówkach i to go właśnie mierzymy."""
        self.naglowki = dict(naglowki or {})
        self.zadania: list[httpx.Request] = []
        self.dokumentow = 0

    def __call__(self, zadanie: httpx.Request) -> httpx.Response:
        self.zadania.append(zadanie)
        sciezka = zadanie.url.path
        if sciezka == KONTRAKT.punkty.lista:
            numer = int(zadanie.url.params[KONTRAKT.parametry_listy.strona])
            return httpx.Response(200, content=self.strony[numer - 1])
        self.dokumentow += 1
        if self.przerwij_na is not None and self.dokumentow == self.przerwij_na:
            raise self.wyjatek
        if self.odmowa_na is not None and self.dokumentow >= self.odmowa_na:
            return httpx.Response(429, content=b"{}", headers=self.naglowki)
        return httpx.Response(200, content=dokument(sciezka.rsplit("/", 1)[1]))

    @property
    def strony_zadane(self) -> list[str]:
        return [
            z.url.params[KONTRAKT.parametry_listy.strona]
            for z in self.zadania
            if z.url.path == KONTRAKT.punkty.lista
        ]


@pytest.fixture(autouse=True)
def _bez_klucza_ze_srodowiska(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KONTRAKT.tempo.klucz_api.zmienna, raising=False)


@pytest.fixture
def store() -> Store:
    return Store.open(":memory:", clock=ZegarTestowy())


def uruchom(
    store: Store, serwer: Serwer, *, zgoda: bool = True, kryteria: Criteria = KRYTERIA
) -> pipeline.Podsumowanie:
    return pipeline.pobierz(
        "atlas",
        kryteria,
        store,
        NullEvents(),
        zgoda=zgoda,
        user_agent=UA_TESTOWY,
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(serwer)),
        zegar=ZegarTestowy(),
    )


# --- pełny przebieg i pomijanie istniejących --------------------------------------------------


def test_pelny_przebieg_zapisuje_kazdego_kandydata_raz(store: Store) -> None:
    wynik = uruchom(store, Serwer())

    assert (wynik.kandydatow, wynik.nowych, wynik.pominietych) == (100, 100, 0)
    assert wynik.zadan == 102, "dwie strony listy i sto dokumentów"
    assert wynik.status == "zakonczony"
    assert store.count("documents") == store.count("raw_versions") == 100
    assert store.count("requests_log") == 102
    przebieg = store.get_run(wynik.run_id)
    assert przebieg.status == "zakonczony" and przebieg.finished_at is not None


def test_drugi_przebieg_pomija_istniejace_bez_zadan_po_dokument(store: Store) -> None:
    """Dokument już w bazie nie kosztuje żądania — cudzy serwer nie płaci za to, co mamy."""
    uruchom(store, Serwer())
    serwer = Serwer()

    wynik = uruchom(store, serwer)

    assert (wynik.nowych, wynik.pominietych) == (0, 100)
    assert wynik.zadan == 2 and serwer.dokumentow == 0
    assert store.count("raw_versions") == 100


def test_doc_id_uzywa_ref_case_z_kontraktu(store: Store) -> None:
    uruchom(store, Serwer())

    assert store.has_document(f"atlas:{SLUGI[0]}")


# --- próg zgody ------------------------------------------------------------------------------


def test_bez_zgody_przebieg_masowy_odmawia_zanim_wysle_pierwszy_dokument(store: Store) -> None:
    serwer = Serwer()

    with pytest.raises(ConsentMissingError, match="zgod"):
        uruchom(store, serwer, zgoda=False)

    assert serwer.dokumentow == 0, "odmowa ma paść po liście, przed pierwszym dokumentem"
    assert store.count("requests_log") == 1
    assert store.count("documents") == 0
    przebieg = store.get_run(store._conn.execute("SELECT run_id FROM runs").fetchone()[0])
    assert przebieg.status == "przerwany" and przebieg.powod is not None


def test_bez_zgody_maly_odczyt_diagnostyczny_przechodzi(store: Store) -> None:
    """Reguła zgody: pojedynczy odczyt diagnostyczny nie wymaga zgody — zostawia ślad."""
    maly = Serwer([strona(LISTA[KLUCZ][:3], ma_wiecej=False, total=3)])

    wynik = uruchom(store, maly, zgoda=False)

    assert wynik.nowych == 3 and wynik.zadan == 4
    assert store.count("requests_log") == 4


def test_prog_zgody_dziala_takze_gdy_kanal_nie_zglasza_liczby(store: Store) -> None:
    """Zabezpieczenie na licznik żądań, gdy `total` nie przyjdzie: odmowa po progu, nie nigdy."""
    rekordy = LISTA[KLUCZ][: pipeline.PROG_ZGODY + 5]
    bez_total = json.dumps({KLUCZ: rekordy, MA_WIECEJ: False}).encode()
    serwer = Serwer([bez_total])

    with pytest.raises(ConsentMissingError):
        uruchom(store, serwer, zgoda=False)

    assert serwer.dokumentow == pipeline.PROG_ZGODY - 1
    assert store.count("documents") == pipeline.PROG_ZGODY - 1


# --- ślad w chwili powrotu, koniec przebiegu przy wyjątku ----------------------------------


def test_wpis_w_requests_log_powstaje_w_chwili_powrotu_zadania(store: Store) -> None:
    serwer = Serwer(
        przerwij_na_dokumencie=3, wyjatek=httpx.ConnectError("zerwane polaczenie (wymyslone)")
    )

    with pytest.raises(TransportError):
        uruchom(store, serwer)

    statusy = [
        wiersz[0]
        for wiersz in store._conn.execute("SELECT status FROM requests_log ORDER BY rowid")
    ]
    assert statusy == [200, 200, 200, None], (
        "lista, dwa dokumenty i żądanie, które nie doszło — każde ze swoim wierszem, "
        "zanim wyjątek opuścił `pobierz`"
    )
    assert store.count("documents") == 2


def test_finish_run_zapisuje_koniec_takze_przy_ctrl_c(store: Store) -> None:
    serwer = Serwer(przerwij_na_dokumencie=5)

    with pytest.raises(KeyboardInterrupt):
        uruchom(store, serwer)

    run_id = store._conn.execute("SELECT run_id FROM runs").fetchone()[0]
    przebieg = store.get_run(run_id)
    assert przebieg.status == "przerwany"
    assert przebieg.finished_at is not None
    assert przebieg.powod is not None and "Ctrl+C" in przebieg.powod
    assert przebieg.ostatnia_strona == 1
    assert store.count("documents") == 4


def test_blad_spoza_taksonomii_zapisuje_status_blad(store: Store) -> None:
    serwer = Serwer(przerwij_na_dokumencie=2, wyjatek=RuntimeError("awaria wymyslona"))

    with pytest.raises(RuntimeError):
        uruchom(store, serwer)

    przebieg = store.get_run(store._conn.execute("SELECT run_id FROM runs").fetchone()[0])
    assert przebieg.status == "blad" and przebieg.powod == "RuntimeError: awaria wymyslona"


# --- bramka fazy 1: przerwany i wznowiony bez duplikatów ------------------------------------


def test_przerwany_i_wznowiony_przebieg_nie_tworzy_duplikatow(store: Store) -> None:
    with pytest.raises(KeyboardInterrupt):
        uruchom(store, Serwer(przerwij_na_dokumencie=5))
    przerwany = store._conn.execute("SELECT run_id FROM runs").fetchone()[0]
    serwer = Serwer()

    wynik = uruchom(store, serwer)

    assert wynik.run_id == przerwany, "wznowienie wraca do tego samego przebiegu"
    assert (wynik.nowych, wynik.pominietych) == (96, 4)
    assert serwer.dokumentow == 96, "cztery dokumenty sprzed przerwania nie kosztują żądań"
    assert store.count("documents") == store.count("raw_versions") == 100
    assert store.count("runs") == 1
    assert store.get_run(wynik.run_id).status == "zakonczony"


def test_wznowienie_startuje_od_ostatniej_strony(store: Store) -> None:
    """Punkt kontrolny to strona, z której pochodził ostatni zapisany kandydat."""
    druga = [dict(r, slug=f"{r['slug']}-2") for r in LISTA[KLUCZ][:5]]
    strony = [
        strona(LISTA[KLUCZ], ma_wiecej=True, total=105),
        strona(druga, ma_wiecej=False, total=105),
    ]
    with pytest.raises(KeyboardInterrupt):
        uruchom(store, Serwer(strony, przerwij_na_dokumencie=103))
    assert store.count("documents") == 102
    serwer = Serwer(strony)

    wynik = uruchom(store, serwer)

    assert serwer.strony_zadane == ["2"], "lista od strony 2, bez powtarzania strony 1"
    assert (wynik.nowych, wynik.pominietych) == (3, 2)
    assert store.count("documents") == 105


def test_ctrl_c_w_srodku_dokumentu_nie_zostawia_polowy_zapisu(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niezmiennik ADR-0001 2.3 mierzony tam, gdzie boli: przerwanie **wewnątrz** transakcji.

    `test_finish_run_zapisuje_koniec_takze_przy_ctrl_c` przerywa na transporcie, czyli zanim
    transakcja się otworzy — wtedy atomowość nie ma czego udowodnić. Tutaj `Ctrl+C` pada między
    zapisem surowej wersji a punktem kontrolnym, więc albo cofa się wszystko, albo baza zostaje
    z dokumentem bez metadanych i bez wiersza w `run_documents` — czyli z kandydatem, którego
    wznowienie uzna za pobrany, choć nie jest zaindeksowany.

    Wiersz w `requests_log` **zostaje** i to jest druga połowa tego samego zdania: żądanie
    naprawdę poszło do cudzego serwisu, więc ślad po nim nie ma prawa się cofnąć razem
    z transakcją (`store.py`: `log_request` zapisuje poza `transakcja()`).
    """
    prawdziwy = store.index_document
    stan = {"licznik": 0, "przerywaj": True}

    def przerwij(*args: object, **kwargs: object) -> None:
        stan["licznik"] = int(stan["licznik"]) + 1
        if stan["przerywaj"] and stan["licznik"] == 3:
            raise KeyboardInterrupt
        prawdziwy(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(store, "index_document", przerwij)

    with pytest.raises(KeyboardInterrupt):
        uruchom(store, Serwer())

    run_id = store._conn.execute("SELECT run_id FROM runs").fetchone()[0]
    assert store.count("documents") == 2, "trzeci dokument cofnął się razem z transakcją"
    assert store.count("raw_versions") == store.count("metadata") == 2
    assert store.count_run_documents(run_id) == 2
    assert store.get_run(run_id).ostatnia_strona == 1
    assert store.count("requests_log") == 4, (
        "lista i trzy dokumenty — ślad po żądaniu, które naprawdę poszło, nie cofa się z transakcją"
    )

    stan["przerywaj"] = False
    wynik = uruchom(store, Serwer())

    assert wynik.run_id == run_id and (wynik.nowych, wynik.pominietych) == (98, 2)
    assert store.count("documents") == store.count("raw_versions") == 100
    assert store.count("runs") == 1


def test_wznowienie_odczekuje_odstep_z_dziennika_zadan(store: Store) -> None:
    """Grzeczność ma przeżyć proces: limiter dostaje historię z `requests_log`, więc pierwsze
    żądanie po wznowieniu trzyma odstęp od ostatniego sprzed przerwania."""
    with pytest.raises(KeyboardInterrupt):
        uruchom(store, Serwer(przerwij_na_dokumencie=2))
    zegar = ZegarTestowy()
    serwer = Serwer()

    pipeline.pobierz(
        "atlas",
        KRYTERIA,
        store,
        NullEvents(),
        zgoda=True,
        user_agent=UA_TESTOWY,
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(serwer)),
        zegar=zegar,
    )

    assert zegar.sleeps and zegar.sleeps[0] > 0, "pierwsze żądanie po wznowieniu czekało"


# --- 429 i Retry-After przez granicę procesu ---------------------------------------------------

RETRY_AFTER_S = 300
"""Wartość nagłówka w atrapie — dłuższa niż domyślna blokada limitera (60 s), więc różnica
między „honorowany" a „zgubiony" jest widoczna w jednym odczycie snów zegara."""


def test_429_zatrzymuje_przebieg_i_zostawia_go_wznawialnym(store: Store) -> None:
    """Reguła 16: odmowy nie omijamy. 429 kończy przebieg `RateLimitError`, a że ten jest
    `ResumableError`, przebieg zostaje `przerwany` — z wierszem 429 w dzienniku żądań."""
    serwer = Serwer(odmowa_na_dokumencie=3, naglowki={"Retry-After": str(RETRY_AFTER_S)})

    with pytest.raises(RateLimitError):
        uruchom(store, serwer)

    przebieg = store.get_run(store._conn.execute("SELECT run_id FROM runs").fetchone()[0])
    assert przebieg.status == "przerwany" and przebieg.powod is not None
    statusy = [w[0] for w in store._conn.execute("SELECT status FROM requests_log ORDER BY rowid")]
    assert statusy == [200, 200, 200, 429]
    assert store.count("documents") == 2


def test_retry_after_przezywa_wznowienie_przebiegu(store: Store) -> None:
    """Znalezisko testera 2026-09-18, zgłoszone jako `xfail(strict=True)` i **poprawione tego
    samego dnia**; znacznik zdjęty razem z poprawką. Do tego dnia `Retry-After` był honorowany
    wyłącznie w procesie, w którym przyszedł: `requests_log` nie miał na niego kolumny, więc
    wznowienie po 429 z `Retry-After: 300` ruszało po własnej blokadzie 60 s — pięć razy wcześniej,
    niż serwis prosił, dokładnie po tym, jak odmówił. Poprawka: `Wynik.retry_after_s` →
    `requests_log.retry_after_s` (schemat 3) → `RequestStamp.retry_after_s` → `_next_slot`
    liczy blokadę z historii jako `max(cooldown_s, Retry-After)`."""
    serwer = Serwer(odmowa_na_dokumencie=3, naglowki={"Retry-After": str(RETRY_AFTER_S)})
    with pytest.raises(RateLimitError):
        uruchom(store, serwer)
    # Zegar wznowienia startuje dziesięć sekund po przerwanym przebiegu: znaczniki z dziennika
    # muszą leżeć w przeszłości, bo `_next_slot` pomija te „z przyszłości" (skok zegara).
    zegar = ZegarTestowy(start_wall=1_700_000_010.0)

    pipeline.pobierz(
        "atlas",
        KRYTERIA,
        store,
        NullEvents(),
        zgoda=True,
        user_agent=UA_TESTOWY,
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(Serwer())),
        zegar=zegar,
    )

    assert max(zegar.sleeps, default=0.0) >= RETRY_AFTER_S - 20, (
        f"wznowienie po 429 z `Retry-After: {RETRY_AFTER_S}` odczekało najwyżej "
        f"{max(zegar.sleeps, default=0.0):.0f} s — prośba serwisu nie przeżyła przerwania "
        "przebiegu, bo dziennik żądań jej nie zapisał"
    )


# --- konfiguracja -----------------------------------------------------------------------------


def test_zgoda_obejmuje_strony_listy_gdy_wszystkie_dokumenty_sa_juz_w_bazie(
    store: Store,
) -> None:
    """Przegląd kodu 2026-09-18 (HIGH), poprawione tego samego dnia: sprawdzenie zgody stało za
    `continue` dla kandydata pominiętego, więc ponowny przebieg na zakresie, w którym wszystko
    jest już w bazie, wysyłał wszystkie strony listy bez zgody (zmierzone: 60 przy progu 50).
    Strony listy są żądaniami do cudzego serwisu tak samo jak dokumenty."""
    uruchom(store, Serwer(), zgoda=True)
    assert store.count("documents") == len(SLUGI)
    serwer = Serwer()

    with pytest.raises(ConsentMissingError):
        uruchom(store, serwer, zgoda=False)

    assert len(serwer.zadania) == 1, (
        f"bez zgody poszło {len(serwer.zadania)} żądań — zgoda ma paść po pierwszej stronie "
        "listy, zanim pójdzie druga, także gdy nie ma ani jednego dokumentu do pobrania"
    )


def test_wznow_wznawia_wskazany_przebieg_a_nie_najnowszy_o_tym_odcisku(store: Store) -> None:
    """Przegląd kodu 2026-09-18 (MEDIUM), poprawione tego samego dnia: `wznow --run-id A`
    szukało przebiegu drugi raz po odcisku i brało najnowszy — ekran mówił „wznawiam A",
    a rachunek dotyczył B, a A zostawał przerwany na zawsze."""
    zegar = ZegarTestowy()
    kwargs = dict(
        kanal="atlas",
        zakres=KRYTERIA.describe(),
        kryteria=KRYTERIA.canonical_json(),
        fingerprint=KRYTERIA.fingerprint(),
    )
    starszy = store.start_run(started_at="2026-09-18T10:00:00Z", **kwargs)
    store.finish_run(starszy, status="przerwany", finished_at="2026-09-18T10:01:00Z")
    nowszy = store.start_run(started_at="2026-09-18T11:00:00Z", **kwargs)
    store.finish_run(nowszy, status="przerwany", finished_at="2026-09-18T11:01:00Z")

    wynik = pipeline.wznow(
        store,
        starszy,
        NullEvents(),
        zgoda=True,
        user_agent=UA_TESTOWY,
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(Serwer())),
        zegar=zegar,
    )

    assert wynik.run_id == starszy
    assert store.get_run(starszy).status == "zakonczony"
    assert store.get_run(nowszy).status == "przerwany", "wznowiono nie ten przebieg"


def test_find_run_nie_widzi_przebiegu_innego_kanalu(store: Store) -> None:
    """Odcisk kryteriów nie niesie kanału — bez `kanal=` `pobierz --kanal saos` wznowiłoby
    przebieg atlasowy i załadowało limiterowi historię cudzego hosta (przegląd 2026-09-18)."""
    run_id = store.start_run(
        kanal="saos",
        zakres=KRYTERIA.describe(),
        started_at="2026-09-18T10:00:00Z",
        kryteria=KRYTERIA.canonical_json(),
        fingerprint=KRYTERIA.fingerprint(),
    )
    store.finish_run(run_id, status="przerwany", finished_at="2026-09-18T10:01:00Z")

    assert store.find_run(KRYTERIA.fingerprint(), ("przerwany",), kanal="atlas") is None
    znaleziony = store.find_run(KRYTERIA.fingerprint(), ("przerwany",), kanal="saos")
    assert znaleziony is not None and znaleziony.run_id == run_id


def test_eksport_wielu_przebiegow_nie_duplikuje_dokumentu(store: Store, tmp_path: Path) -> None:
    """Przegląd kodu 2026-09-18 (MEDIUM), poprawione tego samego dnia: dokument objęty dwoma
    przebiegami (nowy w pierwszym, pominięty w drugim) szedł do eksportu dwa razy, a liczba
    „dokumentów w eksporcie" mówiła nieprawdę — mina 1 z audytu, tylko w pliku wynikowym."""
    pierwszy = uruchom(store, Serwer()).run_id
    drugi = uruchom(store, Serwer()).run_id
    assert store.count("documents") == len(SLUGI)

    wynik = pipeline.eksportuj(
        store, run_ids=(pierwszy, drugi), formaty=("csv",), out=tmp_path / "e", zegar=ZegarTestowy()
    )

    assert wynik.dokumentow == len(SLUGI)
    wiersze = (tmp_path / "e.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(wiersze) - 1 == len(SLUGI), "duplikat dokumentu w pliku csv"


def test_eksport_nazywa_dokument_ktorego_wersji_nie_da_sie_odczytac(
    store: Store, tmp_path: Path
) -> None:
    """Przegląd kodu 2026-09-18 (MEDIUM), poprawione tego samego dnia w minimalnej postaci:
    reguła 19 pozwala zapisać bajty, które nie są JSON-em, a eksport wywracał się bez nazwy
    winnego wiersza. Operator ma dostać `doc_id`; liczenie takich wierszy jak w `przelicz`
    zostaje do rozstrzygnięcia."""
    import hashlib

    from kio_tool.errors import ParseError

    tresc = b"to nie jest json"
    skrot = hashlib.sha256(tresc).hexdigest()
    with store.transakcja():
        store.upsert_document(
            doc_id="atlas:kio-zepsuty-24",
            source="atlas",
            source_ref="kio-zepsuty-24",
            sygnatury=("(sygnatura wymyslona)",),
            data_wydania="2024-01-15",
            seen_at="2026-09-18T10:00:00Z",
            content_sha256=skrot,
        )
        store.add_raw_version(
            doc_id="atlas:kio-zepsuty-24",
            content=tresc,
            fetched_at="2026-09-18T10:00:00Z",
            fetch_meta={},
            expected_sha256=skrot,
        )

    with pytest.raises(ParseError, match="kio-zepsuty-24"):
        pipeline.eksportuj(
            store, kryteria=KRYTERIA, formaty=("jsonl",), out=tmp_path / "e", zegar=ZegarTestowy()
        )


def test_nieznany_kanal_konczy_sie_bledem_konfiguracji(store: Store) -> None:
    with pytest.raises(ConfigError, match="atlas"):
        pipeline.pobierz("saos", KRYTERIA, store, zgoda=True, user_agent=UA_TESTOWY)

    assert store.count("runs") == 0


def test_kanal_domyslny_jest_w_rejestrze() -> None:
    assert pipeline.KANAL_DOMYSLNY in pipeline.kanaly()


def test_puste_kryteria_i_filtr_wielowartosciowy_odmawiaja_przed_zadaniem(store: Store) -> None:
    serwer = Serwer()
    for kryteria in (Criteria(), Criteria(rozstrzygniecie=("oddalono", "umorzono"))):
        with pytest.raises(ConfigError):
            uruchom(store, serwer, kryteria=kryteria)

    assert serwer.zadania == [] and store.count("runs") == 0


# --- run_documents: przebieg obejmuje nowych i pominiętych ------------------------------------


def test_kazdy_kandydat_nowy_i_pominiety_jest_zwiazany_z_przebiegiem(store: Store) -> None:
    """Mutacja „bez pominiętych" zapala się tu: drugi przebieg ma 100 objętych, 0 pobranych."""
    pierwszy = uruchom(store, Serwer())
    drugi = uruchom(store, Serwer())

    assert store.count_run_documents(pierwszy.run_id) == 100
    assert store.count_run_documents(pierwszy.run_id, nowe=True) == 100
    assert store.count_run_documents(drugi.run_id) == 100
    assert store.count_run_documents(drugi.run_id, nowe=True) == 0
    assert list(store.iter_run_documents(drugi.run_id)) == [f"atlas:{s}" for s in SLUGI]


def test_podsumowanie_liczy_calosc_przebiegu_z_bazy_nie_z_licznikow_sesji(store: Store) -> None:
    with pytest.raises(KeyboardInterrupt):
        uruchom(store, Serwer(przerwij_na_dokumencie=5))

    wynik = uruchom(store, Serwer())

    assert (wynik.nowych, wynik.pominietych) == (96, 4)
    assert wynik.objetych_lacznie == store.count_run_documents(wynik.run_id) == 100
    assert wynik.pobranych_lacznie == store.count_run_documents(wynik.run_id, nowe=True) == 100
    assert wynik.zadan_lacznie == store.count_requests(wynik.run_id) == wynik.zadan + 5
    assert wynik.zgloszone == LISTA[LICZNIK]


def test_maks_ogranicza_kandydatow_i_nie_prosi_o_kolejna_strone(store: Store) -> None:
    serwer = Serwer()

    wynik = uruchom(
        store, serwer, kryteria=Criteria(od=date(2024, 1, 1), do=date(2024, 1, 31), maks=5)
    )

    assert (wynik.kandydatow, wynik.nowych) == (5, 5)
    assert serwer.strony_zadane == ["1"] and serwer.dokumentow == 5
    assert wynik.zgloszone == LISTA[LICZNIK] and store.count_run_documents(wynik.run_id) == 5


def test_maks_ponizej_progu_zgody_nie_wymaga_zgody(store: Store) -> None:
    """Próg porównuje się z `min(total, maks)`: pięć dokumentów to odczyt diagnostyczny."""
    wynik = uruchom(
        store,
        Serwer(),
        zgoda=False,
        kryteria=Criteria(od=date(2024, 1, 1), do=date(2024, 1, 31), maks=5),
    )

    assert wynik.nowych == 5


# --- filtry idą do kanału pod nazwami z kontraktu -----------------------------------------------


def test_filtry_kryteriow_trafiaja_do_zadania_pod_nazwami_z_kontraktu(store: Store) -> None:
    serwer = Serwer([strona(LISTA[KLUCZ][:2], ma_wiecej=False, total=2)])
    kryteria = Criteria(
        fraza="odrzucenie oferty", rozstrzygniecie=("oddalono",), przepis="art. 226"
    )

    uruchom(store, serwer, kryteria=kryteria)

    lista = next(z for z in serwer.zadania if z.url.path == KONTRAKT.punkty.lista)
    tlumaczenie = KONTRAKT.parametry_listy.filtry
    assert lista.url.params[tlumaczenie["fraza"]] == "odrzucenie oferty"
    assert lista.url.params[tlumaczenie["rozstrzygniecie"]] == "oddalono"
    assert lista.url.params[tlumaczenie["przepis"]] == "art. 226"
    assert KONTRAKT.parametry_listy.od not in lista.url.params, "dat nie podano — nie wysyłamy"
    assert (
        store.get_run(store.list_runs()[0].run_id).zakres
        == "…..…; fraza=odrzucenie oferty; przepis=art. 226; rozstrzygniecie=oddalono"
    )


# --- indeks powstaje w przebiegu, `przelicz` bez sieci, `eksportuj` bez sieci -----------------


@pytest.fixture
def bez_sieci(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fabryka klienta, której wywołanie jest naruszeniem: operacje offline nie mają po co
    budować klienta HTTP, a `--block-network` z `pyproject.toml` pilnuje gniazda pod spodem."""

    def zabroniona(**_: object) -> httpx.Client:
        raise AssertionError("operacja bez sieci zbudowała klienta HTTP")

    monkeypatch.setattr(pipeline, "build_http_client", zabroniona)


def test_pobierz_indeksuje_dokumenty_w_tej_samej_transakcji(store: Store) -> None:
    uruchom(store, Serwer())

    assert store.count_indexed() == 100 == store.count("fts")
    assert store.szukaj("tresc wymyslona").trafien == 100


def test_przelicz_odtwarza_metadane_i_indeks_bez_zadnego_zadania(
    store: Store, bez_sieci: None
) -> None:
    uruchom(store, Serwer())
    store._conn.execute("DELETE FROM metadata")
    store._conn.execute("DELETE FROM fts")
    assert store.count_indexed() == 0

    wynik = pipeline.przelicz(store)

    assert wynik.przeliczonych == 100 and wynik.bledow == 0
    assert (wynik.w_korpusie, wynik.zaindeksowanych) == (100, 100)
    assert pipeline.przelicz(store).przeliczonych == 0, "wersje bieżące nie liczą się drugi raz"
    assert pipeline.przelicz(store, wszystko=True).przeliczonych == 100


def test_przelicz_liczy_wersje_nie_do_odczytania_zamiast_je_przemilczec(
    store: Store, bez_sieci: None
) -> None:
    uruchom(store, Serwer([strona(LISTA[KLUCZ][:2], ma_wiecej=False, total=2)]))
    zepsuty = f"atlas:{SLUGI[0]}"
    sha = store._conn.execute(
        "SELECT current_sha256 FROM documents WHERE doc_id = ?", (zepsuty,)
    ).fetchone()[0]
    store._conn.execute("DELETE FROM metadata")
    store._conn.execute(
        "UPDATE raw_versions SET content_bytes = ? WHERE doc_id = ? AND content_sha256 = ?",
        (b"[nie slownik]", zepsuty, sha),
    )

    wynik = pipeline.przelicz(store)

    assert (wynik.przeliczonych, wynik.bledow) == (1, 1)
    assert wynik.zaindeksowanych == 1


def test_eksportuj_z_przebiegu_zapisuje_formaty_bez_sieci(
    store: Store, bez_sieci: None, tmp_path: Path
) -> None:
    przebieg = uruchom(store, Serwer())

    wynik = pipeline.eksportuj(
        store,
        run_ids=(przebieg.run_id,),
        formaty=("xlsx", "jsonl"),
        out=tmp_path / "e",
        zegar=ZegarTestowy(),
    )

    assert wynik.dokumentow == 100 and [p.name for p in wynik.sciezki] == ["e.xlsx", "e.jsonl"]
    assert len((tmp_path / "e.jsonl").read_text(encoding="utf-8").splitlines()) == 100


def test_eksportuj_po_kryteriach_i_metadane_z_bazy(
    store: Store, bez_sieci: None, tmp_path: Path
) -> None:
    przebieg = uruchom(store, Serwer())
    kryteria = Criteria(fraza="tresc wymyslona")

    wynik = pipeline.eksportuj(
        store, kryteria=kryteria, formaty=("csv",), out=tmp_path / "k", zegar=ZegarTestowy()
    )
    metadane = dict(
        pipeline.build_metadata(
            store,
            run_ids=(przebieg.run_id,),
            kryteria=None,
            dokumentow=100,
            formaty=("csv",),
            cel="test",
            zegar=ZegarTestowy(),
            atrybucje={"atlas": KONTRAKT.licencja.atrybucja},
        )
    )

    assert wynik.dokumentow == 100
    assert metadane["objetych_przez_przebiegi"] == 100 == store.count_run_documents(przebieg.run_id)
    assert metadane["zadan_w_przebiegach"] == 102 == store.count_requests(przebieg.run_id)
    assert metadane["atrybucja_atlas"] == KONTRAKT.licencja.atrybucja
    assert metadane["cel_pobrania"] == "test" and metadane["run_id"] == przebieg.run_id


def test_eksportuj_bez_dokumentow_nie_tworzy_pliku(
    store: Store, bez_sieci: None, tmp_path: Path
) -> None:
    wynik = pipeline.eksportuj(
        store, kryteria=Criteria(fraza="nic takiego"), out=tmp_path / "n", zegar=ZegarTestowy()
    )

    assert wynik.dokumentow == 0 and wynik.sciezki == ()
    assert not list(tmp_path.iterdir())


# --- nazwa pliku eksportu: kryteria operatora są wrogim wejściem -------------------------------


def test_nazwa_eksportu_z_kryteriow_nie_niesie_znakow_sciezki_ani_dwukropka(
    store: Store, bez_sieci: None
) -> None:
    """Rdzeń nazwy powstaje z `Criteria.describe()`, czyli z tekstu, który ktoś wpisał — razem
    z ukośnikiem w sygnaturze przepisu i z dwukropkiem z etykiety pola.

    Bez `--out`, celowo: to jest jedyny test, który przechodzi domyślną ścieżką eksportu, i to
    on pokazuje, że piaskownica trzyma ją w `tmp_path`. Fraza z ukośnikiem trafia w dokumenty,
    bo `unicode61` dzieli na nim tokeny — więc test mierzy nazwę **naprawdę zapisanego** pliku,
    a nie sam wynik funkcji.
    """
    uruchom(store, Serwer([strona(LISTA[KLUCZ][:2], ma_wiecej=False, total=2)]))

    wynik = pipeline.eksportuj(
        store,
        kryteria=Criteria(fraza="tresc wymyslona/kio"),
        formaty=("csv",),
        zegar=ZegarTestowy(),
    )

    (sciezka,) = wynik.sciezki
    assert wynik.dokumentow == 2 and sciezka.is_file()
    assert sciezka.parent == pipeline.default_output_dir(), (
        "eksport bez `--out` ma trafić do domyślnego katalogu wyników (w teście: do piaskownicy)"
    )
    assert "/" not in sciezka.name and "\\" not in sciezka.name and ":" not in sciezka.name
    assert "„" in sciezka.name and "”" in sciezka.name, (
        "polska typografia z `describe()` przeżywa — `safe_filename` zdejmuje znaki ścieżki, "
        "nie znaki spoza ASCII"
    )


@pytest.mark.parametrize(
    ("rdzen", "oczekiwana"),
    [
        ("art. 226/2020 Pzp", "art._226_2020_Pzp"),
        ("..\\..\\windows\\system32", "windows_system32"),
        ("przewodniczący: Żółć", "przewodniczący_Żółć"),
        ("   ", "kio"),
        ("", "kio"),
        ("...", "kio"),
    ],
    ids=["ukosnik", "wyjscie-z-katalogu", "polskie-znaki", "same-biale", "pusty", "same-kropki"],
)
def test_safe_filename_zdejmuje_znaki_sciezki_i_nie_zostawia_pustego_rdzenia(
    rdzen: str, oczekiwana: str
) -> None:
    """Jedyny producent nazw plików w tym drzewie (`exporter.nazwa_pliku_md`,
    `pipeline._nazwa_eksportu`), a do 2026-09-18 bez jednego testu.

    Pusty rdzeń jest osobnym przypadkiem, nie szczegółem: bez wartości zastępczej `kio` nazwa
    pliku byłaby samym rozszerzeniem (`.csv`), czyli plikiem ukrytym na POSIX-ie.
    """
    assert safe_filename(rdzen) == oczekiwana


def test_safe_filename_przycina_rdzen_i_dokleja_sufiks_po_przycieciu() -> None:
    """Limit liczy się od rdzenia, a sufiks dochodzi po nim — inaczej `.xlsx` obcięłoby się
    razem z nazwą i plik straciłby rozszerzenie przy długich kryteriach."""
    nazwa = safe_filename("a" * (MAX_FILENAME_STEM + 50), ".xlsx")

    assert nazwa == "a" * MAX_FILENAME_STEM + ".xlsx"


def test_eksportuj_bez_przebiegu_i_bez_kryteriow_odmawia(store: Store, bez_sieci: None) -> None:
    with pytest.raises(ConfigError):
        pipeline.eksportuj(store, zegar=ZegarTestowy())
    with pytest.raises(ConfigError, match="zip"):
        pipeline.eksportuj(
            store, kryteria=Criteria(fraza="x"), formaty=("zip",), zegar=ZegarTestowy()
        )


# --- wznow ---------------------------------------------------------------------------------------


def test_wznow_bez_run_id_bierze_ostatni_przerwany_i_konczy_go(store: Store) -> None:
    with pytest.raises(KeyboardInterrupt):
        uruchom(store, Serwer(przerwij_na_dokumencie=5))
    przerwany = store.list_runs(limit=1, statuses=("przerwany",))[0].run_id
    serwer = Serwer()

    wynik = pipeline.wznow(
        store,
        None,
        NullEvents(),
        zgoda=True,
        user_agent=UA_TESTOWY,
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(serwer)),
        zegar=ZegarTestowy(),
    )

    assert wynik.run_id == przerwany and wynik.status == "zakonczony"
    assert (wynik.nowych, wynik.pominietych) == (96, 4)
    assert store.count("runs") == 1


def test_wznow_odmawia_gdy_nie_ma_przerwanego_albo_wskazany_jest_zakonczony(store: Store) -> None:
    with pytest.raises(ConfigError, match="nie ma czego"):
        pipeline.do_wznowienia(store, None)
    zakonczony = uruchom(store, Serwer()).run_id

    with pytest.raises(ConfigError, match="zakonczony"):
        pipeline.do_wznowienia(store, zakonczony)


def test_wznow_przebiegu_sprzed_schematu_2_bez_kryteriow_mowi_co_zrobic(store: Store) -> None:
    run_id = store.start_run(
        kanal="atlas", zakres="etykieta", started_at="t", kryteria="{}", fingerprint="f"
    )
    store._conn.execute(
        "UPDATE runs SET kryteria = NULL, fingerprint = NULL, status = 'przerwany' "
        "WHERE run_id = ?",
        (run_id,),
    )

    with pytest.raises(ConfigError, match="pobierz"):
        pipeline.do_wznowienia(store, run_id)


# --- schemat 4: odtworzenie powiązań sprawdzone na wyniku prawdziwego przebiegu ---------------


def test_odtworzone_powiazania_zgadzaja_sie_z_tym_co_zapisal_przebieg(tmp_path: Path) -> None:
    """Zgodność odtworzenia z zapisem pierwotnym — na bazie z potoku, nie z ręki.

    Backfill schematu 4 (`store._odtworz_powiazania_sprzed_schematu_2`) łączy
    `requests_log.sha256` z `raw_versions.content_sha256` — dwie kolumny wypełniane w dwóch
    różnych miejscach produkcji (`_Slad.zanotuj` w tym module i `Store.add_raw_version`).
    Baza ułożona w teście ręcznie potwierdzałaby wyłącznie założenie testu o tych kolumnach,
    więc ta pochodzi z `pipeline.pobierz`: sto dokumentów i sto dwa żądania, z dwoma żądaniami
    listy, które mają odpaść. Po skasowaniu powiązań i cofnięciu wersji schematu odtworzenie
    ma wrócić z tą samą listą doc_id w tej samej kolejności — to jest ta sama miara, którą
    właściciel zmierzył 2026-09-19 na swoim korpusie jako „zgodność 295/295".
    """
    sciezka = tmp_path / "korpus.sqlite"
    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        wynik = uruchom(store, Serwer())
        pierwotne = list(store.iter_run_documents(wynik.run_id))
    assert len(pierwotne) == 100

    with sqlite3.connect(sciezka) as p:
        p.execute("DELETE FROM run_documents")
        p.execute("PRAGMA user_version = 3")

    with Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert list(store.iter_run_documents(wynik.run_id)) == pierwotne
        assert store.count_run_documents(wynik.run_id, nowe=True) == 100
        assert store.count_requests(wynik.run_id) == 102
