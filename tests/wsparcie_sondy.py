"""Wspólne narzędzia testów sondy fazy 0: materiał wymyślony, atrapa serwisu, zegar, ścieżki.

Do 2026-09-18 wszystko to stało w `tests/test_sonda.py` (2 932 linie). Rozbicie po module —
`test_logbook.py`, `test_console.py`, `test_zadanie.py`, `test_pomiar_*.py` — wymaga jednego
miejsca na to, co wspólne, bo drugi egzemplarz atrapy serwisu rozjeżdżałby się od pierwszego
bez jednego czerwonego testu. Fixtures (`_piaskownica`, `podstaw`, `zegar_sondy`, `przebieg`)
stoją w `tests/conftest.py`, bo piaskownica ma obowiązywać w **każdym** pliku, który dotyka
sondy — a plik dotykający jej bez piaskownicy wyglądałby identycznie jak z nią.

Trzy rzeczy o kształcie tych narzędzi:

1. **Żadne żądanie nie opuszcza procesu, ale każde jedzie prawdziwą ścieżką.** Atrapa jest
   wstrzyknięta jako `transport` do `build_http_client`, więc ruch przechodzi przez
   `AllowedHostsTransport` — tak jak mówi docstring `httpclient.py`: „atrapa z testu też
   jest opakowana", bo inaczej testy jeździłyby inną drogą niż produkcja.
2. **Zegar jest sterowany.** `zadanie.SystemClock` podstawiamy zegarem testowym w kształcie
   z `test_ratelimit.py`: limiter trzyma odstęp 2 s przy UZP, a test nie ma prawa go
   przesypiać. Znacznik czasu w nazwie pliku staje się przy okazji przewidywalny.
3. **Prawdziwy dysk jest poza zasięgiem, a mimo to sprawdzany.** `scripts/out/`
   i `docs/dziennik_zadan.md` są przekierowane do `tmp_path`, ale fixture `_piaskownica`
   **porównuje stan prawdziwych ścieżek przed testem i po nim**. Samo przekierowanie jest
   gwarancją bez obserwatora: funkcja, która kiedyś złoży ścieżkę sama zamiast czytać stałą
   modułu, ominie je bez śladu. Dziennik żądań jest w historii repozytorium — wiersz
   dopisany przez test byłby tam zapisem żądania, którego nikt nie wysłał.
4. **Od 2026-09-18 to samo dotyczy korpusu operatora.** `config.default_db_path()`
   i `config.default_output_dir()` wskazują do katalogu danych użytkownika, a testy etapu V
   uruchamiały `pobierz` bez `--out` — zmierzone tego dnia: cztery pliki eksportu na przebieg
   suity, wpisane do prawdziwego `wyniki/` z zegara testowego (nazwy `*_20231114T22…`),
   dwadzieścia cztery zastane i skasowane ręcznie. Zapis testu do prawdziwego katalogu wyjścia
   jest eksportem, którego nikt nie zlecił — ta sama klasa usterki, co wiersz w dzienniku żądań
   po żądaniu, którego nikt nie wysłał — więc dostaje to samo lekarstwo: przekierowanie
   **i** porównanie stanu przed testem i po nim.

Napisy udające odpowiedzi serwisów są **wymyślone** i mają ten sam status co w
`tests/test_ksztalty.py`: sprawdzają skaner, nie źródło. Sygnatur wyglądających na prawdziwe
tu nie ma świadomie.

Ten moduł nie jest plikiem testów — pytest go nie zbiera, bo nazwa nie zaczyna się od `test_`.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import httpx

# `zadanie` i `pomiar_uzp` mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import pomiar_uzp
import zadanie

import kio_tool
from kio_tool import config, logbook

if TYPE_CHECKING:  # `pytest` tylko dla adnotacji — ten moduł nie jest plikiem testów i nie ma
    import pytest  # powodu wciągać wtyczki przy imporcie z `conftest.py`.

UA_TESTOWY = "kio-tool/test (kontakt: test@example.org)"
"""Tożsamość podstawiana w testach, jak w `test_pomiar21_blokada_sieci.py`. Produkcja bierze
ją z `config.user_agent()`, który czyta zmienną środowiskową — test nie ma prawa od niej
zależeć poza tymi miejscami, gdzie przedmiotem testu jest właśnie ta zależność."""

PRAWDZIWY_DZIENNIK = zadanie.DZIENNIK
PRAWDZIWE_WYJSCIE = zadanie.KATALOG_WYJSCIA
"""Ścieżki odczytane **przed** jakimkolwiek przekierowaniem — do porównania w `_piaskownica`."""

PRAWDZIWA_BAZA = config.default_db_path()
PRAWDZIWE_WYNIKI = config.default_output_dir()
"""Korpus operatora i jego katalog eksportów — też odczytane przed przekierowaniem.

Wywołania stoją tu, a nie w `_piaskownica`: fixture dostaje już podstawione funkcje, więc
zapytana o ścieżkę wskazałaby `tmp_path` i porównywałaby piaskownicę samą ze sobą. To jest ta
sama pułapka, którą `test_piaskownica.py` zamknął 2026-09-18 przy dzienniku żądań.
"""

ORYGINALNE_SCIEZKI = {
    "default_db_path": config.default_db_path,
    "default_output_dir": config.default_output_dir,
    "katalog_pokazu": config.katalog_pokazu,
}
"""Funkcje sprzed podstawienia — po nich rozpoznajemy moduł, który zaimportował nazwę.

Zapamiętane przy imporcie, bo po pierwszym `monkeypatch.setattr(config, …)` porównanie
`is getattr(config, nazwa)` wskazywałoby już na zamiennik i kolejne moduły zostałyby pominięte.
"""


# --- materiał wymyślony, opisany w nagłówku ----------------------------------------------

BOT_CHECK = (
    b"<!DOCTYPE html><html><head><title>Weryfikacja przegladarki</title></head><body>"
    b"<div id='challenge-running'>Sprawdzamy, czy polaczenie jest bezpieczne.</div>"
    b"</body></html>"
)
UZP_DETAILS_OK = (
    b"<html><body><label>Sygnatura akt</label><span>(napis wymyslony)</span></body></html>"
)
UZP_WYNIKI_OK = (
    b'<html><body><div id="resultCounts">KIO: 12</div>'
    b'<div class="search-list-item">pozycja</div></body></html>'
)
SAOS_DUMP_OK = b'{"items": [{"id": 1, "courtType": "NATIONAL_APPEAL_CHAMBER"}], "links": []}'
ATLAS_LISTA_OK = (
    b'{"data": [{"slug": "wymyslony-slug-1", "primary_signature": "(napis wymyslony)", '
    b'"ruling_date": "2018-01-02"}]}'
)
ATLAS_DOKUMENT_OK = (
    b'{"slug": "wymyslony-slug-1", "primary_signature": "(napis wymyslony)", '
    b'"ruling_date": "2018-01-02", "content": "tresc wymyslona, dluzsza niz inne pola"}'
)
"""Lista i dokument w kształcie z dokumentacji Atlasu (odczyt 2026-09-18): rekord listy niesie
`slug`, a dokument — te same pola plus jedno długie pole tekstowe. Slug wymyślony, jak reszta."""

SCIEZKA_UZP_KONTROLA = "/Home/Details/9620"
SCIEZKA_UZP_WYNIKI = "/Home/GetResults"
SCIEZKA_UZP_TRESC = f"/Home/ContentHtml/{pomiar_uzp.UZP_CONTENT_ID}"
SCIEZKA_ATLAS = "/api/kio"
SCIEZKA_ATLAS_DOKUMENT = "/api/kio/wymyslony-slug-1"
SCIEZKA_ATLAS_DOKUMENTACJA = "/dokumentacja-api"
SCIEZKA_SAOS = "/api/dump/judgments"
SCIEZKA_KORZEN = "/"


# --- narzędzia testowe ---------------------------------------------------------------------


class ZegarTestowy:
    """Zegar sterowany przez test; `sleep` przesuwa czas zamiast czekać.

    Kształt przeniesiony z `tests/test_ratelimit.py`, bez `jump_wall`: skok zegara ściennego
    jest własnością limitera i ma tam swoje testy, a tutaj chodzi wyłącznie o to, żeby odstęp
    2 s przy UZP nie zamienił się w dwie sekundy przebiegu suity.
    """

    def __init__(self, start_wall: float = 1_700_000_000.0, start_mono: float = 1000.0) -> None:
        self._wall = start_wall
        self._mono = start_mono
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self._mono

    def wall(self) -> float:
        return self._wall

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._mono += seconds
        self._wall += seconds


@dataclass(frozen=True)
class Odpowiedz:
    """Jedna odpowiedź scenariusza. Budowana na nowo przy każdym żądaniu, bo `httpx.Response`
    zużywa swój strumień, a ten sam punkt bywa odpytywany dwa razy."""

    status: int = 200
    tresc: bytes = b"{}"
    naglowki: Mapping[str, str] = field(default_factory=dict)


class Serwis:
    """Atrapa cudzego serwisu: odpowiada według scenariusza i pamięta, co naprawdę wyszło.

    Pamięta dwie rzeczy, bo dwie są przedmiotem testów: **żądania** (ile, w jakiej
    kolejności, z jakimi parametrami) i **zbiory hostów**, z jakimi sonda budowała klienta.
    Drugie jest jedyną obserwowalną konsekwencją tego, że `allowed` przestało mieć wartość
    domyślną: gdyby pomiar zbudował klienta z sumą hostów, nic innego by o tym nie powiedziało.

    Żądanie spoza scenariusza kończy się `AssertionError`, a nie odpowiedzią zastępczą.
    Odpowiedź zastępcza czyniłaby z „sonda wysłała żądanie, którego nie miała wysłać" wynik
    zielony — czyli dokładnie tę ciszę, przed którą broni reszta tego pliku.

    Wartością scenariusza jest albo jedna odpowiedź powtarzana w nieskończoność, albo
    **lista zużywana po kolei**. Lista jest tu konieczna, a nie wygodna: `pomiar_saos` wysyła
    trzy żądania pod ten sam adres i cała treść jego przebudowy z 2026-09-17 polega na tym,
    że drugie zachowuje się inaczej niż pierwsze — niezgodny kształt jedzie dalej, odmowa
    serwisu zatrzymuje. Wyczerpanie listy jest `AssertionError`, a nie powtórzeniem
    ostatniego wpisu: żądanie, którego scenariusz nie przewidział, ma być głośne.
    """

    def __init__(
        self,
        scenariusz: Mapping[str, Odpowiedz | BaseException | Sequence[Odpowiedz | BaseException]],
    ) -> None:
        self._scenariusz = dict(scenariusz)
        self._zuzyte: dict[str, int] = {}
        self.zadania: list[httpx.Request] = []
        self.bramki: list[frozenset[str]] = []

    def _wpis(self, sciezka: str) -> Odpowiedz | BaseException:
        wpis = self._scenariusz.get(sciezka)
        if wpis is None:
            raise AssertionError(f"ścieżka spoza scenariusza: {sciezka}")
        if isinstance(wpis, Odpowiedz | BaseException):
            return wpis
        numer = self._zuzyte.get(sciezka, 0)
        self._zuzyte[sciezka] = numer + 1
        if numer >= len(wpis):
            raise AssertionError(
                f"żądanie nr {numer + 1} na `{sciezka}`, a scenariusz przewidział {len(wpis)}"
            )
        return wpis[numer]

    def _obsluz(self, zadanie: httpx.Request) -> httpx.Response:
        self.zadania.append(zadanie)
        wpis = self._wpis(zadanie.url.path)
        if isinstance(wpis, BaseException):
            raise wpis
        return httpx.Response(wpis.status, content=wpis.tresc, headers=dict(wpis.naglowki))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._obsluz)

    @property
    def slad(self) -> list[tuple[str, str]]:
        """Co wyszło: metoda i ścieżka, w kolejności wysłania."""
        return [(z.method, z.url.path) for z in self.zadania]


def scenariusz_atlas_ok() -> dict[str, Odpowiedz]:
    """Oba żądania pomiaru 3a odpowiadają zgodnie z kontraktem: lista, potem dokument."""
    return {
        SCIEZKA_ATLAS: Odpowiedz(tresc=ATLAS_LISTA_OK),
        SCIEZKA_ATLAS_DOKUMENT: Odpowiedz(tresc=ATLAS_DOKUMENT_OK),
    }


Stan = tuple[bytes | None, tuple[str, ...] | None]
"""Odczyt stanu dwóch ścieżek sondy: treść dziennika i spis katalogu wyjścia.

`None` w którymkolwiek polu znaczy „nie istnieje" i jest **stanem**, nie brakiem odczytu —
założenie prawdziwego dziennika przez test jest tą samą usterką co dopisanie do istniejącego.
"""


def stan_sciezek(dziennik: Path, katalog: Path) -> Stan:
    """Treść dziennika i spis katalogu — albo `None`, gdy nie istnieją.

    Ścieżki są parametrami od 2026-09-18, a `stan_prawdziwych_sciezek` jest jednolinijkowym
    wywołaniem z prawdziwymi. Powód jest mierzalny: dopóki funkcja czytała wyłącznie stałe
    modułu, **nie dało się jej sprawdzić** — jej samosprawdzenie musiałoby ruszyć dokładnie te
    pliki, przed którymi ona broni. Zmierzone mutacją 2026-09-18: `dziennik = None` wpisane
    na sztywno przechodziło przez cały zielony przebieg, a piaskownica zostawała wtedy ślepa
    na połowę tego, czego pilnuje — bez jednego czerwonego testu.
    """
    tresc = dziennik.read_bytes() if dziennik.is_file() else None
    spis = tuple(sorted(p.name for p in katalog.iterdir())) if katalog.is_dir() else None
    return (tresc, spis)


def stan_prawdziwych_sciezek() -> Stan:
    """Stan prawdziwego dziennika i prawdziwego `scripts/out/` — do porównania w `_piaskownica`."""
    return stan_sciezek(PRAWDZIWY_DZIENNIK, PRAWDZIWE_WYJSCIE)


# --- druga połowa piaskownicy: korpus i katalog wyników operatora --------------------------

Drzewo = tuple[tuple[str, int, int], ...]
StanKorpusu = tuple[tuple[int, int] | None, Drzewo | None]
"""Odczyt stanu bazy korpusu i katalogu eksportów.

Baza jest opisana parą `(rozmiar, mtime_ns)`, a nie treścią, i to jest kompromis z podaną ceną:
prawdziwy `korpus.sqlite` ma 24 498 176 bajtów (zmierzone 2026-09-18), więc czytanie go dwa razy
na test kosztowałoby przy 905 testach ~42 GB odczytu na przebieg suity. SQLite nie zapisuje
niczego bez zmiany czasu modyfikacji — nawet samo otwarcie w trybie WAL i zamknięcie rusza
nagłówek pliku — więc para wystarcza, żeby dotknięcie bazy przez test było głośne.

Katalog eksportów jest czytany **w głąb**: eksport `md` jest katalogiem z plikiem na orzeczenie,
więc spis samych wpisów najwyższego poziomu nie zobaczyłby pliku dorzuconego do już istniejącego
katalogu `*_md`. `os.scandir` niesie rozmiar i czas modyfikacji razem z nazwą (zmierzone
2026-09-18: 1 ms na odczyt przy 299 wpisach, czyli ~1,8 s na przebieg suity).
"""


def _drzewo(katalog: Path) -> Drzewo | None:
    """Ścieżki względne, rozmiary i czasy modyfikacji wszystkich plików w drzewie — albo `None`.

    `None` znaczy „katalogu nie ma" i jest **stanem**: założenie katalogu wyjścia przez test jest
    tą samą usterką co dorzucenie do niego pliku.
    """
    if not katalog.is_dir():
        return None
    wynik: list[tuple[str, int, int]] = []
    stos: list[tuple[str, str]] = [("", str(katalog))]
    while stos:
        przedrostek, sciezka = stos.pop()
        with os.scandir(sciezka) as wpisy:
            for wpis in wpisy:
                nazwa = przedrostek + wpis.name
                if wpis.is_dir():
                    stos.append((nazwa + "/", wpis.path))
                else:
                    dane = wpis.stat()
                    wynik.append((nazwa, dane.st_size, dane.st_mtime_ns))
    return tuple(sorted(wynik))


def stan_korpusu(baza: Path, katalog: Path) -> StanKorpusu:
    """Stan pliku bazy i drzewa katalogu eksportów — ścieżki parametrami, jak w `stan_sciezek`.

    Parametrami z tego samego powodu: funkcja czytająca wyłącznie stałe modułu nie da się
    sprawdzić inaczej niż ruszeniem dokładnie tych plików, przed którymi broni.
    """
    dane = baza.stat() if baza.is_file() else None
    return (None if dane is None else (dane.st_size, dane.st_mtime_ns), _drzewo(katalog))


PRAWDZIWE_RAPORTY = Path(__file__).resolve().parent.parent / "docs" / "raporty"
"""Zacommitowane raporty pokrycia — domyślny `--cel` polecenia `pokrycie` względem katalogu
bieżącego, czyli pod pytestem właśnie ten (przegląd kodu 2026-09-19)."""


def stan_raportow() -> Drzewo | None:
    return _drzewo(PRAWDZIWE_RAPORTY)


PRAWDZIWY_POKAZ = config.katalog_pokazu()
"""Prawdziwy katalog trybu pokazowego — zapamiętany przy imporcie, przed podstawieniem."""


def stan_pokazu() -> Drzewo | None:
    return _drzewo(PRAWDZIWY_POKAZ)


def stan_prawdziwego_korpusu() -> StanKorpusu:
    """Stan prawdziwej bazy i prawdziwego `wyniki/` — do porównania w `_piaskownica`."""
    return stan_korpusu(PRAWDZIWA_BAZA, PRAWDZIWE_WYNIKI)


_MODULY: list[ModuleType] = []


def moduly_kio_tool() -> tuple[ModuleType, ...]:
    """Wszystkie moduły pakietu `kio_tool`, zaimportowane.

    Import jest tu konieczny, a nie profilaktyczny: `cli.py` i `pipeline.py` biorą domyślne
    ścieżki **przez `from .config import …`**, więc podstawienie w samym `config` ich nie
    dosięga. Moduł niezaimportowany w chwili działania fixture nie dostałby podstawienia,
    a pierwszy test, który go zaimportuje, pisałby do katalogu operatora.

    Wynik jest liczony raz na proces: przeszukanie pakietu idzie po dysku, a fixture
    `_piaskownica` woła to przed **każdym** testem.
    """
    if not _MODULY:
        for info in pkgutil.walk_packages(kio_tool.__path__, prefix=f"{kio_tool.__name__}."):
            importlib.import_module(info.name)
        _MODULY.extend(
            modul
            for nazwa, modul in sorted(sys.modules.items())
            if nazwa == kio_tool.__name__ or nazwa.startswith(f"{kio_tool.__name__}.")
        )
    return tuple(_MODULY)


def moduly_z_domyslnymi_sciezkami() -> dict[str, tuple[str, ...]]:
    """Nazwa funkcji → moduły `kio_tool`, które ją u siebie trzymają (import albo definicja).

    Czytane z **obiektów modułów**, nie ze składni: `from .config import default_db_path`
    i `config.default_db_path` dają w module dwie różne postaci zapisu i tylko jedna z nich
    jest napisem do znalezienia w źródle.
    """
    znalezione: dict[str, list[str]] = {nazwa: [] for nazwa in ORYGINALNE_SCIEZKI}
    for modul in moduly_kio_tool():
        for nazwa, oryginal in ORYGINALNE_SCIEZKI.items():
            if getattr(modul, nazwa, None) is oryginal:
                znalezione[nazwa].append(modul.__name__)
    return {nazwa: tuple(moduly) for nazwa, moduly in znalezione.items()}


def przekieruj_domyslne_sciezki(monkeypatch: pytest.MonkeyPatch, katalog: Path) -> tuple[str, ...]:
    """Podstawia `default_db_path` i `default_output_dir` w **każdym** module, który je trzyma.

    Zwraca podstawione miejsca w postaci `modul.nazwa` — pusty wynik znaczy, że piaskownica nie
    przekierowała niczego, i dlatego jest wynikiem, a nie efektem ubocznym.
    """
    zamienniki = {
        "default_db_path": lambda: katalog / config.PLIK_BAZY,
        "default_output_dir": lambda: katalog / config.KATALOG_WYNIKOW,
        "katalog_pokazu": lambda: katalog / config.KATALOG_POKAZU,
    }
    podstawione: list[str] = []
    for modul in moduly_kio_tool():
        for nazwa, oryginal in ORYGINALNE_SCIEZKI.items():
            if getattr(modul, nazwa, None) is oryginal:
                monkeypatch.setattr(modul, nazwa, zamienniki[nazwa])
                podstawione.append(f"{modul.__name__}.{nazwa}")
    return tuple(podstawione)


def wynik(**nadpisania: object) -> logbook.Wynik:
    """Wynik z sensownymi wartościami domyślnymi — test nadpisuje tylko to, co bada."""
    pola: dict[str, object] = {
        "nazwa": "przyklad",
        "metoda": "GET",
        "adres": "https://orzeczenia.uzp.gov.pl/Home/Details/9620",
        "status": 200,
        "bajtow": 128,
        "czas_s": 0.25,
        "plik": None,
    }
    pola.update(nadpisania)
    return logbook.Wynik(**pola)  # type: ignore[arg-type]


def wiersze_dziennika() -> list[str]:
    """Wiersze danych z dziennika — bez nagłówka i bez pustych linii.

    Osobno, bo trzy testy pytają o to samo, a rozróżnienie „wiersz danych" od „wiersz
    nagłówka tabeli" jest tym, co decyduje o liczbie N w `decisions.md`.
    """
    if not zadanie.DZIENNIK.exists():
        return []
    return [
        w
        for w in zadanie.DZIENNIK.read_text(encoding="utf-8").splitlines()
        if w.startswith("| sonda-")
    ]


def uzp_scenariusz(
    kontrola: Odpowiedz | BaseException, wyniki: Odpowiedz | BaseException | None = None
) -> Serwis:
    scenariusz: dict[str, Odpowiedz | BaseException] = {SCIEZKA_UZP_KONTROLA: kontrola}
    if wyniki is not None:
        scenariusz[SCIEZKA_UZP_WYNIKI] = wyniki
    return Serwis(scenariusz)


KLUCZ_TESTOWY = "sekretny-klucz-atlasu"
"""Dłuższy niż `MIN_REGISTERED_SECRET`; `pomiar_atlas` rejestruje go sam przy starcie."""


def dziennik_z_wierszami(*wiersze: str) -> None:
    """Zakłada dziennik z nagłówkiem produkcyjnym i dopisuje podane wiersze surowo.

    Nagłówek jest prawdziwy, a nie skrócony, bo to on niesie **dwie** tabele i trzy wiersze
    zaczynające się od `|`, których czytanie ma pominąć: nagłówki kolumn i separatory. Tabela
    podrzucona w skrócie nie zmierzyłaby tego pominięcia.
    """
    zadanie.DZIENNIK.parent.mkdir(parents=True, exist_ok=True)
    zadanie.DZIENNIK.write_text(
        logbook.NAGLOWEK_DZIENNIKA.replace("{data}", "2023-11-14") + "".join(wiersze),
        encoding="utf-8",
        newline="\n",
    )


def wiersz_reczny(adres: str, ts: str, skrot: str) -> str:
    """Wpis ręczny w kształcie opisanym w nagłówku dziennika: `run_id` postaci `recznie-*`,
    kolumny niewypełnialne ręką jako „—"."""
    return f"| recznie-20231114 | {ts} | GET | `{adres}` | 200 | — | — | `{skrot}` | — |\n"


ADRES_19 = f"https://orzeczenia.uzp.gov.pl/Home/ContentHtml/{pomiar_uzp.UZP_CONTENT_ID}"
TRESC_19 = (
    # Transliteracja ASCII nagłówka odczytanego 2026-09-14 („Izba zważyła, co następuje:",
    # architektura 1) — bo `UZP_CONTENT` szuka fragmentu `Izba zwa`, przyciętego na pierwszym
    # ogonku. Pierwsza wersja tego materiału zlepiała dwa różne nagłówki („Izba ustaliła"
    # i „co następuje") w jeden, którego nikt nigdy nie widział; przy zawężeniu fragmentu
    # z `Izba` do `Izba zwa` 2026-09-17 atrapa przestała przypominać stronę, którą udaje.
    b"<html><body><h2>Uzasadnienie</h2><p>Izba zwazyla, co nastepuje (napis wymyslony).</p>"
    b"</body></html>"
)
TRESC_19_INNA = TRESC_19.replace(b"nastepuje", b"nastepowalo")


def odczyt(ts: str, skrot: str) -> pomiar_uzp.WczesniejszyOdczyt:
    return pomiar_uzp.WczesniejszyOdczyt(ts=ts, skrot=skrot)


def wynik_19(sha: str = "a" * 64, **nadpisania: object) -> logbook.Wynik:
    return wynik(adres=ADRES_19, sha256=sha, ksztalt_zgodny=True, **nadpisania)


def serwis_19(*odpowiedzi: Odpowiedz | BaseException) -> Serwis:
    return Serwis({SCIEZKA_UZP_TRESC: list(odpowiedzi)})
