"""Głos programu na ekranie: konsola `rich` z `richtext.make_console` i puls przebiegu.

Reguła 7 rezerwuje ten moduł jako jedno z trzech miejsc, którym wolno znać `rich` (obok
`richtext.py` i `ui/render.py`), a `tests/test_boundaries.py` obejmuje go skanem reguły 10:
każdy napis idący stąd na ekran ma przechodzić przez `richtext.safe`. Do etapu IV (2026-09-18)
`rich` tu nie wchodził — wystarczał `print` z `flush=True`, bo odbiorcami były sonda i `pobierz`.
Wszedł razem z `ui/render.py`, dokładnie tak, jak zapowiadał poprzedni nagłówek: warstwa `ui/`
dostała rysowanie (tabele `runy` i `szukaj`), więc jeden i ten sam obiekt konsoli ma nieść
i tabelę, i wiersz pulsu — dwa różne bufory na jednym strumieniu przeplatałyby się w połowie linii.

Dwie własności `make_console`, na których ten moduł stoi: `markup=False` (nawias kwadratowy
z uzasadnienia nie jest znacznikiem — reguła 10 jako własność obiektu, nie skanu) i brak `file=`
(konsola sięga po `sys.stdout` przy każdym zapisie, więc przechwytywanie w testach działa).
Druk idzie z `soft_wrap=True`: wiersz pulsu i ścieżka bazy mają zostać jednym wierszem także
na wąskim terminalu, bo zawinięta ścieżka nie daje się skopiować, a zawinięty wiersz dziennika
nie daje się policzyć. `print(Text)` z `rich` wypisuje sam napis, więc na ekran idzie to samo co
przed neutralizacją — bez znaków sterujących i bez sekretów.

`wypisz` i `wypisz_blad` są kanałem wyjścia dla sondy; `cli.py` rysuje przez `ui/render.py`
(reguła 9: `cli.py` nie drukuje niczym sam — zdania układa `ui/texts.py`).
"""

from __future__ import annotations

from rich.console import Console

from .clock import local_hhmm
from .progress import Events
from .richtext import make_console, safe

WCIECIE_PULSU = 26
"""Wiersz pulsu wcięty pod kolumnę statusu wiersza `Kroniki` — oba idą na ten sam ekran."""

_KONSOLA = make_console()
_KONSOLA_BLEDOW = make_console(stderr=True)


def wypisz(tekst: str) -> None:
    """Zdanie dla operatora na standardowe wyjście — przez `safe`, jak każdy druk tego modułu."""
    _KONSOLA.print(safe(tekst), soft_wrap=True)


def wypisz_blad(tekst: str) -> None:
    """Zdanie o błędzie na wyjście błędów — żeby przekierowanie `stdout` do pliku go nie zjadło."""
    _KONSOLA_BLEDOW.print(safe(tekst), soft_wrap=True)


class PulsKonsoli:
    """Głos limitera i pulsu przebiegu: mówi, że program czeka albo że coś zapisał.

    Zasada 7.2 mówi, że cisza jest usterką, a limiter ma dokładnie jeden moment, w którym
    program stoi bez własnego powodu: postój. Przy odstępie UZP to są pojedyncze sekundy,
    ale po statusie 429 `note_response` ustawia blokadę `max(cooldown_s, Retry-After)`,
    a `_sleep_in_slices` przesypia ją w plastrach po 300 s. Bez tego zdarzenia operator nie
    odróżni „limiter trzyma odstęp" od „gniazdo wisi" — a to jest ta sama cisza, którą
    docstring zbioru powodów w `ratelimit` nazywa usterką z doktryny (przegląd 2026-09-17).

    Mówią tu trzy zdarzenia: `on_wait` (postój), `on_message` (zdanie od limitera do operatora)
    i — od etapu III, 2026-09-18 — `on_document` (dokument zapisany do korpusu). Trzecie jest
    pulsem przebiegu masowego w jedynej jednostce, w której doktryna pozwala go liczyć:
    w dokumentach zapisanych, nigdy w stronach (`progress.py`). `on_request` milczy nadal —
    w sondzie wiersz na żądanie drukuje `Kronika`, a w przebiegu masowym wiersz na dokument
    wystarcza; drugi wiersz na każde żądanie zdublowałby dziennik na ekranie. Pozostałe zdarzenia
    milczą, bo należą do faz, które jeszcze nie istnieją.

    Powód postoju idzie na ekran **dosłownie**, bez tłumaczenia na zdanie: `on_wait` nie
    rozpoznaje powodów i nie ma listy, którą trzeba by uzupełniać przy każdym nowym. Zdanie
    dla operatora jest własnością `ui/texts.py` i tam ma powstać razem ze swoim strażnikiem
    (`tests/test_ratelimit.py`, wyzwalacz konsumenta zbioru powodów).

    Konsola jest wstrzykiwalna, żeby test mógł podać własną (np. `record=True`); domyślnie
    ta sama, przez którą mówi `wypisz`. Do 2026-09-18 klasa nazywała się `PulsSondy`
    i mieszkała w `scripts/sonda.py`.
    """

    def __init__(self, konsola: Console | None = None) -> None:
        self._konsola = konsola or _KONSOLA

    def on_request(self, endpoint: str, status: int, elapsed_s: float) -> None:
        return None

    def on_document(self, saved: int, total: int | None) -> None:
        razem = "?" if total is None else str(total)
        _wiersz_pulsu(
            self._konsola, f"zapisano {saved} dokumentów (kandydatów w zakresie: {razem})"
        )

    def on_version(self, doc_id: str, content_sha256: str) -> None:
        return None

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        _wiersz_pulsu(
            self._konsola,
            f"czekam {seconds:.1f} s ({reason}), wznowienie {local_hhmm(resume_at_epoch)}",
        )

    def on_page(self, page_index: int, candidates: int, total: int | None) -> None:
        return None

    def on_parse(self, done: int, total: int) -> None:
        return None

    def on_export(self, done: int, total: int) -> None:
        return None

    def on_message(self, text: str) -> None:
        _wiersz_pulsu(self._konsola, text)

    def close(self) -> None:
        return None


def _wiersz_pulsu(konsola: Console, tekst: str) -> None:
    """Jeden wiersz pulsu, wcięty pod kolumnę statusu `Kroniki`. Funkcja modułu, nie metoda:
    `tests/test_console.py` czyta metody `PulsKonsoli` jako listę głosów do sprawdzenia."""
    konsola.print(safe(f"{'':{WCIECIE_PULSU}} ⋯ {tekst}"), soft_wrap=True)


# Bez tego przypisania dopisanie metody do protokołu `Events` nie zapaliłoby tu niczego —
# ten sam powód, dla którego linia stoi w `kio_tool/progress.py`.
_ZGODNOSC_Z_PROTOKOLEM: Events = PulsKonsoli()


def puls_dla(*, maszynowo: bool) -> PulsKonsoli:
    """Puls na stdout dla człowieka, na stderr pod `--json` — stdout niesie wtedy wyłącznie linie
    JSON, a puls nadal jest widoczny (cisza jest usterką, 2026-09-22). Funkcja, nie metoda:
    `test_console` pilnuje, że każda metoda `PulsKonsoli` jest zdarzeniem z obserwatorem."""
    return PulsKonsoli(_KONSOLA_BLEDOW if maszynowo else None)
