"""Proces ubity bez sprzątania — jak przy zaniku zasilania. Co zostaje i co da się z tym zrobić.

Wszystkie pozostałe przerwania w tym drzewie zostawiają Pythonowi chwilę na `finally`: `Ctrl+C`
podnosi `KeyboardInterrupt`, zerwane łącze podnosi `TransportError`, brak zgody podnosi
`ConsentMissingError`. Zanik zasilania nie zostawia nic — i to jest jedyny scenariusz, którego
nie da się zmierzyć w tym samym procesie, bo mierzy właśnie **brak** wykonania kodu sprzątającego.

Stąd podproces. Pomocnik jedzie tą samą produkcyjną drogą (`pipeline.pobierz`, prawdziwy `Store`
na pliku, prawdziwy `build_http_client`), zatrzymuje się w wybranym miejscu i melduje o tym na
standardowe wyjście; test ubija go `TerminateProcess` (to samo, co `taskkill /F` — bez obsługi
sygnału, bez `atexit`, bez `finally`), a potem otwiera bazę i pyta o stan.

**Żadne żądanie nie opuszcza podprocesu**: transport to `httpx.MockTransport`, ten sam, co
w pozostałych testach. `--block-network` z `pyproject.toml` obowiązuje proces pytesta i nie
sięga podprocesu, więc miejsce atrapy jest tu jedyną gwarancją — i dlatego pomocnik nie ma
w sobie ani jednej linii, która budowałaby transport sieciowy.

Baza i katalog wyjścia idą **jawnymi ścieżkami pod `tmp_path`**: podproces nie przechodzi przez
piaskownicę z `conftest.py`, więc polecenie bez `--baza` sięgnęłoby prawdziwego korpusu
operatora. Pomocnik nie zna wartości domyślnych i nie ma jak ich wziąć.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from kio_tool import pipeline
from kio_tool.clock import SystemClock
from kio_tool.criteria import Criteria
from kio_tool.errors import ConfigError
from kio_tool.store import Store
from tests.test_odpornosc_wspolne import SLUGI, SerwisAwaryjny, uruchom
from tests.wsparcie_sondy import ZegarTestowy

KORZEN = Path(__file__).resolve().parent.parent
MELDUNEK = "GOTOWY-DO-UBICIA"
"""Napis, po którym test wie, że pomocnik doszedł do miejsca ubicia. Bez niego ubicie padałoby
w losowym momencie, a test mierzyłby raz jedno, raz drugie — czyli byłby migotliwy."""

LIMIT_MELDUNKU_S = 60.0
"""Ile czekamy na meldunek. Podproces, który go nie przyśle, zostaje ubity i tak (`finally`),
więc test co najwyżej zawiedzie — nigdy nie zawiesi przebiegu suity."""

POMOCNIK = '''"""Pomocnik testu ubicia: pobiera do wskazanej bazy i zatrzymuje się na zawołanie.

Plik powstaje w `tmp_path` przy każdym uruchomieniu testu, bo jego treść jest częścią
scenariusza — a scenariusz ma być widoczny obok asercji, nie w osobnym katalogu skryptów.
"""

import json
import sys
import time
from datetime import date
from functools import partial
from pathlib import Path

import httpx
import socket


class _GniazdoZabronione:
    """Pomocnik biegnie poza `--block-network` pytesta, więc blokuje gniazdo sam (pomiar 21:
    blokada ma sięgać gniazda, nie transportu). Atrapa transportu jest tu jedyną drogą,
    a gniazdo otwarte w tym procesie jest usterką, nie żądaniem."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError("gniazdo w pomocniku testu ubicia jest usterka")


socket.socket = _GniazdoZabronione  # type: ignore[misc,assignment]

from kio_tool import pipeline
from kio_tool.criteria import Criteria
from kio_tool.docid import SourceName
from kio_tool.httpclient import build_http_client
from kio_tool.progress import NullEvents
from kio_tool.source.contract import load_contract
from kio_tool.store import Store

BAZA, ZLOTE, CO, ILE, WYJSCIE = sys.argv[1:6]
KONTRAKT = load_contract(SourceName("atlas"))
LISTA_BAJTY = Path(ZLOTE).read_bytes()
LISTA = json.loads(LISTA_BAJTY)
KLUCZ = KONTRAKT.ksztalt.lista.klucz
MELDUNEK = "{meldunek}"


class Zegar:
    """Zegar sterowany, jak `ZegarTestowy` w suicie: `sleep` przesuwa czas zamiast czekać."""

    def __init__(self):
        self._wall, self._mono = 1_700_000_000.0, 1000.0

    def monotonic(self):
        return self._mono

    def wall(self):
        return self._wall

    def sleep(self, seconds):
        self._mono += seconds
        self._wall += seconds


def dokument(slug):
    return json.dumps(
        {{
            "slug": slug,
            "primary_signature": "(sygnatura wymyslona dla " + slug + ")",
            "signatures": ["(sygnatura wymyslona dla " + slug + ")"],
            KONTRAKT.ksztalt.dokument.pole_tresci: "tresc wymyslona " + slug,
        }}
    ).encode()


def zatrzymaj_sie_na_zawsze():
    """Melduje i czeka na ubicie. Nie kończy się sama — kończy ją `TerminateProcess`."""
    print(MELDUNEK, flush=True)
    time.sleep(3600)


licznik = {{"dokumentow": 0}}


def serwis(zadanie):
    if zadanie.url.path == KONTRAKT.punkty.lista:
        numer = int(zadanie.url.params[KONTRAKT.parametry_listy.strona])
        if numer > 1:
            pusta = {{
                KLUCZ: [],
                KONTRAKT.ksztalt.lista.ma_wiecej: False,
                KONTRAKT.ksztalt.lista.licznik: LISTA[KONTRAKT.ksztalt.lista.licznik],
            }}
            return httpx.Response(200, content=json.dumps(pusta).encode())
        return httpx.Response(200, content=LISTA_BAJTY)
    licznik["dokumentow"] += 1
    if CO == "pobieranie" and licznik["dokumentow"] == int(ILE):
        zatrzymaj_sie_na_zawsze()
    return httpx.Response(200, content=dokument(zadanie.url.path.rsplit("/", 1)[1]))


zegar = Zegar()
with Store.open(Path(BAZA), clock=zegar) as store:
    wynik = pipeline.pobierz(
        "atlas",
        Criteria(od=date(2024, 1, 1), do=date(2024, 1, 31)),
        store,
        NullEvents(),
        zgoda=True,
        user_agent="kio-tool/test (kontakt: test@example.org)",
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(serwis)),
        zegar=zegar,
    )
    if CO == "eksport":
        przejscia = {{"n": 0}}

        def zrodlo_z_meldunkiem(prawdziwe=store.iter_documents):
            """Melduje po N dokumentach **drugiego** przejścia po korpusie.

            Przejścia są dwa i to nie jest szczegół: `pipeline.eksportuj` przechodzi po
            dokumentach najpierw po to, żeby je policzyć, a dopiero za drugim razem pisze do
            pliku. Zatrzymanie na pierwszym przejściu ubijałoby proces, **zanim** powstanie
            jakikolwiek plik — i test „ubicie nie zostawia połowy pliku” byłby wtedy prawdziwy
            bez zasługi kodu.
            """
            przejscia["n"] += 1
            moje = przejscia["n"]
            oddane = 0
            for dokument_ in prawdziwe(run_id=wynik.run_id):
                oddane += 1
                if moje == 2 and oddane == int(ILE):
                    zatrzymaj_sie_na_zawsze()
                yield dokument_

        store.iter_documents = lambda *a, **k: zrodlo_z_meldunkiem()  # type: ignore[assignment]
        pipeline.eksportuj(
            store,
            run_ids=(wynik.run_id,),
            formaty=("csv",),
            out=Path(WYJSCIE),
            zegar=zegar,
        )
print("KONIEC", flush=True)
'''


@pytest.fixture
def pomocnik(tmp_path: Path) -> Path:
    """Skrypt pomocnika zapisany w `tmp_path` — poza repozytorium, jak każdy artefakt testu."""
    sciezka = tmp_path / "pomocnik_ubicia.py"
    sciezka.write_text(POMOCNIK.format(meldunek=MELDUNEK), encoding="utf-8", newline="\n")
    return sciezka


def ubij_w_miejscu(pomocnik: Path, baza: Path, *, co: str, ile: int, wyjscie: Path) -> int:
    """Uruchamia pomocnika, czeka na meldunek i ubija proces bez dania mu szansy na sprzątanie.

    `Popen.kill()` na Windowsie to `TerminateProcess` — dokładnie to, co wysyła `taskkill /F`
    i czego nie da się obsłużyć: żaden `finally`, żaden `atexit`, żaden `__exit__` menedżera
    kontekstu nie dostanie sterowania. Na POSIX-ie to `SIGKILL`, o tej samej własności.
    """
    proces = subprocess.Popen(
        [
            sys.executable,
            str(pomocnik),
            str(baza),
            str(ZLOTY_PLIK_LISTY),
            co,
            str(ile),
            str(wyjscie),
        ],
        cwd=str(KORZEN),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert proces.stdout is not None
        linia = proces.stdout.readline().strip()
        assert linia == MELDUNEK, (
            f"pomocnik nie doszedł do miejsca ubicia (powiedział {linia!r}); "
            f"błędy: {proces.stderr.read() if proces.stderr else ''}"
        )
        proces.kill()
        return proces.wait(timeout=LIMIT_MELDUNKU_S)
    finally:
        if proces.poll() is None:
            proces.kill()
            proces.wait(timeout=LIMIT_MELDUNKU_S)


ZLOTY_PLIK_LISTY = (
    Path(__file__).resolve().parent / "examples" / "atlas" / ("lista_20260918T103525Z.json")
)


@pytest.fixture
def po_ubiciu(tmp_path: Path, pomocnik: Path) -> Iterator[Store]:
    """Baza po ubiciu procesu w trakcie zapisu piątego dokumentu, otwarta do oględzin.

    Otwarcie bazy przechodzi przez `Store.open`, czyli razem z migracją schematu — bo tak samo
    zrobi następne polecenie operatora. Gdyby ubicie zostawiło bazę, której `Store` nie otworzy,
    ten fixture jest miejscem, w którym to widać.
    """
    baza = tmp_path / "korpus.sqlite"
    ubij_w_miejscu(pomocnik, baza, co="pobieranie", ile=6, wyjscie=tmp_path / "e")
    with Store.open(baza, clock=SystemClock()) as store:
        yield store


# --- co zostaje w bazie -------------------------------------------------------------------------


def test_ubicie_procesu_w_trakcie_zapisu_zostawia_baze_spojna(po_ubiciu: Store) -> None:
    """Zanik zasilania w środku przebiegu: baza otwiera się, a liczniki się zgadzają.

    Pięć tabel musi mówić to samo, bo `pipeline` wpisuje je **jedną transakcją**: dokument
    bez wersji surowej, wersja bez metadanych albo kandydat bez powiązania z przebiegiem
    znaczyłyby, że transakcja się rozpadła i część zapisu przetrwała bez reszty.

    Wiersz w `requests_log` jest o jeden większy celowo: żądanie po piąty dokument **poszło**
    do cudzego serwisu, a dziennik zapisuje się poza transakcją właśnie po to, żeby ten koszt
    nie zniknął razem z niedokończonym zapisem.
    """
    assert po_ubiciu.count("documents") == 5
    assert po_ubiciu.count("raw_versions") == 5
    assert po_ubiciu.count("metadata") == 5
    assert po_ubiciu.count("fts") == 5
    assert po_ubiciu.count("run_documents") == 5
    assert po_ubiciu.count("requests_log") == 6, "strona listy i pięć żądań po dokument"


def test_ubicie_procesu_nie_uszkadza_zapisanych_dokumentow(po_ubiciu: Store) -> None:
    """Liczniki mogą się zgadzać na bajtach, które nie są już tym, co przyszło po drucie.

    Reguła 19 stoi na tym, że `content_sha256` jest skrótem `content_bytes` — więc to jest
    pytanie, czy ubicie procesu rozerwało zapis w środku strony bazy. Sprawdzenie idzie po
    każdej wersji, nie po próbce: pięć dokumentów to pięć porównań i zero powodu do losowania.
    """
    import hashlib

    wiersze = po_ubiciu._conn.execute(
        "SELECT doc_id, content_sha256, content_bytes FROM raw_versions"
    ).fetchall()
    assert len(wiersze) == 5
    for doc_id, sha, bajty in wiersze:
        assert hashlib.sha256(bytes(bajty)).hexdigest() == sha, (
            f"bajty {doc_id} nie zgadzają się ze swoim skrótem — zapis rozerwany przez ubicie"
        )
        assert json.loads(bytes(bajty))["slug"], "zapisany dokument daje się odczytać"


def test_po_ubiciu_procesu_korpus_da_sie_przeliczyc_i_przeszukac(po_ubiciu: Store) -> None:
    """To, co przetrwało, ma być korpusem, a nie pięcioma wierszami o poprawnych licznikach.

    Fraza bez zakresu dat celowo: daty w złotym pliku listy są z lat 2017–2020, a kryteria
    przebiegu mówią o styczniu 2024 (u pośrednika data wydania bywa błędna — README). Ten test
    pyta o indeks pełnotekstowy, nie o filtr dat, i nie ma prawa się o niego potknąć.
    """
    assert pipeline.przelicz(po_ubiciu, wszystko=True).bledow == 0
    assert pipeline.szukaj(po_ubiciu, Criteria(fraza="tresc wymyslona"), limit=10).trafien == 5


# --- czego po ubiciu nie da się zrobić -----------------------------------------------------------


def test_ubity_przebieg_zostaje_w_toku_bo_finally_nie_dostalo_sterowania(po_ubiciu: Store) -> None:
    """Zapis stanu, na którym stoją testy niżej: `finish_run` nigdy się nie wykonał.

    To samo w sobie nie jest defektem — `TerminateProcess` z definicji nie uruchamia `finally`.
    Liczy się to, co narzędzie robi z takim przebiegiem przy następnym uruchomieniu (testy
    niżej): do 2026-09-18 zakładało nowy i płaciło za całą listę od nowa, od tego dnia `w_toku`
    bez procesu jest osierocony i wznawialny (`store.STATUSY_WZNAWIALNE`). Ten test stoi osobno,
    bo nazywa **przyczynę**, i bez niego tamte wyglądałyby na pomyłkę w `finish_run`.
    """
    przebieg = po_ubiciu.list_runs(limit=2)[0]

    assert przebieg.status == "w_toku"
    assert przebieg.finished_at is None
    assert przebieg.ostatnia_strona == 1, "punkt kontrolny ostatniego zapisu przetrwał"
    assert przebieg.fingerprint is not None, "odcisk kryteriów jest w bazie od `start_run`"


def test_przebieg_po_ubiciu_procesu_da_sie_wznowic(po_ubiciu: Store) -> None:
    """Scenariusz operatora: prąd wrócił, komputer wstał, uruchamiam `wznow`.

    Wznowienie ma wrócić do tego samego przebiegu — nie dlatego, że tak ładniej, tylko dlatego,
    że w `ostatnia_strona` stoi punkt kontrolny, a lista Atlasu przy 29 580 orzeczeniach to
    ~296 żądań do cudzego serwisu, które przebieg zaczynający od nowa wysyła drugi raz.
    """
    run_id, _kryteria = pipeline.do_wznowienia(po_ubiciu, None)

    assert run_id == po_ubiciu.list_runs(limit=1)[0].run_id


def test_po_ubiciu_ponowny_pobierz_nie_gubi_dokumentow_i_nie_robi_duplikatow(
    po_ubiciu: Store,
) -> None:
    """Scenariusz operatora bez `wznow`: prąd wrócił, powtarzam to samo `pobierz`.

    To samo polecenie wraca do osieroconego przebiegu i **nie gubi** ani **nie dubluje** niczego:
    pięć dokumentów sprzed ubicia jest pomijanych bez żądania po dokument (strona pierwsza idzie
    raz jeszcze, bo punkt kontrolny wskazuje stronę, nie pozycję), korpus kończy na stu, a rachunek
    stycznia 2024 zostaje jednym wierszem w `runy` ze statusem `zakonczony`. Do 2026-09-18 ten
    sam scenariusz zakładał drugi przebieg, a pierwszy zostawał pracujący na zawsze.
    """
    serwis = SerwisAwaryjny()
    osierocony = po_ubiciu.list_runs(limit=1)[0].run_id

    wynik = uruchom(po_ubiciu, serwis, zegar=ZegarTestowy())

    assert (wynik.run_id, wynik.status) == (osierocony, "zakonczony")
    assert (wynik.nowych, wynik.pominietych) == (95, 5)
    assert serwis.dokumentow == 95, "pięć dokumentów sprzed ubicia nie kosztuje żądania"
    assert po_ubiciu.count("documents") == po_ubiciu.count("raw_versions") == len(SLUGI)
    assert po_ubiciu.count_runs() == 1, "jeden przebieg, dokończony, nie dwa"
    with pytest.raises(ConfigError, match="nie ma czego wznawiać"):
        pipeline.do_wznowienia(po_ubiciu, None)


# --- ubicie w trakcie zapisu eksportu ------------------------------------------------------------


def test_ubicie_w_trakcie_zapisu_eksportu_nie_zostawia_pliku_wynikowego(
    tmp_path: Path, pomocnik: Path
) -> None:
    """Zapis atomowy pod ubiciem: przy celu ma nie być nic, choć plik częściowy **istnieje**.

    To jest jedyny test w tym drzewie, w którym obietnica `_zapis_atomowy` („plik jest cały
    albo nie ma go wcale") jest mierzona przy przerwaniu, które nie daje kodowi ani jednej
    instrukcji na posprzątanie. Dowód ma dwie połowy i obie są konieczne:

    - przy celu (`wynik.csv`) **nie ma nic** — `os.replace` nie zdążył, więc operator nie
      zastanie pliku, który otworzy i weźmie za wynik zapytania;
    - obok leży `.wynik.csv.tmp` z **częścią** wierszy — to on dowodzi, że ubicie padło
      naprawdę w środku zapisu, a nie przed nim. Bez tej połowy test byłby zielony także
      wtedy, gdyby eksport w ogóle się nie zaczął.

    Ogon `.tmp` zostaje, bo `finally` nie dostało sterowania, i to jest cena zapisana, nie
    usterka: plik z kropką na początku nazwy nie udaje wyniku i nie ma go w `INDEX.md`.
    """
    baza = tmp_path / "korpus.sqlite"

    ubij_w_miejscu(pomocnik, baza, co="eksport", ile=60, wyjscie=tmp_path / "wynik")

    assert not (tmp_path / "wynik.csv").exists(), (
        "przy celu leży `wynik.csv` mimo ubicia w środku zapisu — podmiana nie była atomowa"
    )
    ogon = tmp_path / ".wynik.csv.tmp"
    assert ogon.is_file(), (
        "nie ma pliku tymczasowego, więc ubicie padło **przed** zapisem — ten test nie zmierzył "
        "atomowości, tylko to, że eksport się nie zaczął"
    )
    assert ogon.stat().st_size > 0, "plik tymczasowy jest pusty — zapis nie zdążył ruszyć"
    with Store.open(baza, clock=SystemClock()) as store:
        assert store.count("documents") == len(SLUGI), "korpus po ubiciu eksportu jest kompletny"
