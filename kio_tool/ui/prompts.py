"""Jedyny importer `questionary` (reguła 7) — zadaje pytania, które napisał `texts.py`.

Trzy pytające za jednym protokołem `Prompter`, bo wejścia różnią się tym, **kto** odpowiada, a nie
tym, **o co** się pyta (ADR-0008 Z-7):

- `KonsolaPrompter` — operator przy terminalu, przez `questionary`; poza terminalem (potok,
  przekierowanie) spada do `input()`, bo `questionary` bez TTY rzuca, a zdanie „nie mogę zapytać"
  byłoby ślepą uliczką;
- `SkryptowyPrompter` — odpowiedzi z listy, do testów; wyczerpana lista to błąd głośny, nie
  cicha odpowiedź domyślna — inaczej test przechodziłby przez pytanie, którego nie przewidział.

**Reguła 10 obejmuje ten moduł** (ADR-0008 Z-15). Pytanie niesie napisy z zewnątrz — etykiety
przebiegów z bazy, kryteria wpisane przez operatora, sygnatury — a terminal czyta sekwencje
sterujące tak samo, czy przyszły przez `rich`, czy przez `questionary`. Każdy napis idzie przez
`_do_pytania` (`strip_control` + `mask_tokens`, para `richtext.safe` bez `rich`); strażnikiem
jest skan w `tests/test_boundaries.py`.

**Dwie poprawki z 2026-09-20**, obie przeniesione z `ceidg-tool` razem z powodem, dla którego
tam powstały — ten sam defekt zgłosił tu operator:

- Lista wyboru dostaje **jawny styl** i nie dostaje `default=`. Domyślny motyw `questionary`
  podświetla kolorem, którego ta konsola nie pokazuje: strzałka szła w dół, a podświetlenie
  stało w miejscu. `reverse` nie potrzebuje palety. `default=` trafiało do `selected_options`,
  a klasa `selected` wygrywa przy rysowaniu z `pointed_at`, więc wiersz domyślny zostawał
  oznaczony na stałe i operator widział **dwa zaznaczenia naraz**. Kursor startuje odtąd na
  pozycji pierwszej, a domyślną stawia tam `opcje_do_wyboru`.
- Pytanie tak/nie idzie przez pole tekstowe, nie przez `questionary.confirm`. `confirm` wiąże
  na sztywno klawisze `y` i `n` i po cichu pomija każdy inny znak: operator, który na polskie
  pytanie wpisywał „tak", dostawał odpowiedź domyślną i nie miał jak się zorientować.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Protocol

import questionary

from ..config import mask_tokens
from ..safetext import strip_control
from . import texts
from .texts import Opcja, Pytanie

TAK = "tak"
NIE = "nie"

ODPOWIEDZI_TAK = frozenset({"t", "tak", "y", "yes"})
ODPOWIEDZI_NIE = frozenset({"n", "nie", "no"})
"""Dopasowanie jest **dokładne**, nie po pierwszej literze: „to nie" i „teraz nie" zaczynają się
od „t", więc odmowa czytana przedrostkiem byłaby zgodą (`ceidg-tool`, ta sama para zbiorów)."""


def _do_pytania(napis: str) -> str:
    """Neutralizator napisu przed terminalem przez `questionary` — lustro `richtext.safe`."""
    return mask_tokens(strip_control(napis))


def opcje_do_wyboru(pytanie: Pytanie) -> tuple[Opcja, ...]:
    """Opcje z domyślną na czele — bo to pierwsza pozycja wyznacza start kursora.

    Bez `default=` (powód w docstringu modułu) `questionary` stawia kursor na pozycji pierwszej.
    Żeby zaczynał na odpowiedzi domyślnej, to ona musi tam stanąć. Kolejność jest ta sama na
    ścieżce z terminalem i bez niego: lista awaryjna nie może numerować opcji inaczej niż ta,
    której operator przed chwilą nie mógł zobaczyć.
    """
    domyslne = [o for o in pytanie.opcje if o.klucz == pytanie.domyslna]
    reszta = [o for o in pytanie.opcje if o.klucz != pytanie.domyslna]
    return (*domyslne, *reszta)


def rozumiana(odpowiedz: str) -> bool:
    """Czy odpowiedź na pytanie tak/nie da się przeczytać. Pusta = Enter = wartość domyślna."""
    czysta = odpowiedz.strip().casefold()
    return not czysta or czysta in ODPOWIEDZI_TAK | ODPOWIEDZI_NIE


def na_tak_nie(odpowiedz: str, *, domyslna: str | None) -> str:
    """Odpowiedź nierozpoznana znaczy „nie", nie „powtórz": po jednym dopytaniu obowiązuje
    kierunek bezpieczny, bo te pytania stoją przed wydatkiem żądań u cudzego serwisu."""
    czysta = odpowiedz.strip().casefold()
    if not czysta:
        return domyslna or NIE
    return TAK if czysta in ODPOWIEDZI_TAK else NIE


def _styl_wyboru() -> questionary.Style:
    """`reverse` zamiast koloru: podświetlenie ma iść za kursorem na każdej konsoli.

    Klasy `selected` nie ma celowo — skoro nie podajemy `default=`, nic jej nie użyje, a nadanie
    jej wyglądu przywróciłoby defekt dwóch zaznaczeń, gdyby `default=` kiedyś wróciło.
    """
    return questionary.Style([("pointer", "reverse bold"), ("highlighted", "reverse bold")])


class Prompter(Protocol):
    def zapytaj(self, pytanie: Pytanie) -> str:
        """Klucz wybranej opcji, wpisany tekst albo `tak`/`nie`. `Ctrl+C` → `KeyboardInterrupt`."""
        ...


class KonsolaPrompter:
    """Operator przy terminalu. `wejscie` i `terminal` są parametrami wyłącznie dla testów."""

    def __init__(
        self,
        *,
        terminal: bool | None = None,
        wejscie: Callable[[str], str] = input,
    ) -> None:
        self._terminal = sys.stdin.isatty() if terminal is None else terminal
        self._wejscie = wejscie

    def zapytaj(self, pytanie: Pytanie) -> str:
        if pytanie.rodzaj == "wybor":
            return self._wybor(pytanie)
        if pytanie.rodzaj == "tak_nie":
            return self._tak_nie(pytanie)
        return self._linia(f"{pytanie.tresc} ").strip() or (pytanie.domyslna or "")

    def _wybor(self, pytanie: Pytanie) -> str:
        opcje = opcje_do_wyboru(pytanie)
        if not self._terminal:
            return self._wybor_bez_terminala(pytanie, opcje)
        odpowiedz = questionary.select(
            _do_pytania(pytanie.tresc),
            choices=[
                questionary.Choice(title=_do_pytania(o.etykieta), value=o.klucz) for o in opcje
            ],
            style=_styl_wyboru(),
        ).ask()
        if odpowiedz is None:
            # `questionary` zwraca `None` po Ctrl+C — to jest przerwanie, nie odpowiedź.
            raise KeyboardInterrupt
        return str(odpowiedz)

    def _wybor_bez_terminala(self, pytanie: Pytanie, opcje: Sequence[Opcja]) -> str:
        """Numerowana lista na `input()` — zapas dla potoku, nie ścieżka główna."""
        wiersze = [f"  {n}. {_do_pytania(o.etykieta)}" for n, o in enumerate(opcje, 1)]
        odpowiedz = self._wejscie("\n".join([_do_pytania(pytanie.tresc), *wiersze, "> "])).strip()
        if odpowiedz.isdigit() and 1 <= int(odpowiedz) <= len(opcje):
            return opcje[int(odpowiedz) - 1].klucz
        return pytanie.domyslna or opcje[0].klucz

    def _tak_nie(self, pytanie: Pytanie) -> str:
        linia = texts.linia_tak_nie(pytanie)
        odpowiedz = self._linia(f"{linia} ")
        if not rozumiana(odpowiedz):
            # Kreator ma czas dopytać raz: operator, który wpisał „jasne", wyraził zgodę,
            # której nie wolno po cichu zamienić w odmowę.
            odpowiedz = self._linia(f"{texts.NIE_ROZUMIEM_TAK_NIE} {linia} ")
        return na_tak_nie(odpowiedz, domyslna=pytanie.domyslna)

    def _linia(self, tekst: str) -> str:
        """Jedno pytanie tekstowe: `questionary` przy terminalu, `input()` poza nim."""
        if not self._terminal:
            return self._wejscie(_do_pytania(tekst))
        odpowiedz = questionary.text(_do_pytania(tekst)).ask()
        if odpowiedz is None:
            raise KeyboardInterrupt
        return str(odpowiedz)


class WyczerpaneOdpowiedziError(AssertionError):
    """Skrypt testu nie przewidział pytania — błąd testu, nie operatora."""


class SkryptowyPrompter:
    """Odpowiedzi z listy, w kolejności; pamięta zadane pytania do asercji w testach."""

    def __init__(self, odpowiedzi: Sequence[str]) -> None:
        self._odpowiedzi = list(odpowiedzi)
        self.zadane: list[Pytanie] = []

    def zapytaj(self, pytanie: Pytanie) -> str:
        self.zadane.append(pytanie)
        if not self._odpowiedzi:
            raise WyczerpaneOdpowiedziError(f"Skrypt nie przewidział pytania: {pytanie.tresc!r}")
        odpowiedz = self._odpowiedzi.pop(0)
        klucze = {o.klucz for o in pytanie.opcje}
        if pytanie.rodzaj == "wybor" and odpowiedz not in klucze:
            raise WyczerpaneOdpowiedziError(
                f"Odpowiedź {odpowiedz!r} spoza opcji {sorted(klucze)} na {pytanie.tresc!r}"
            )
        return odpowiedz
