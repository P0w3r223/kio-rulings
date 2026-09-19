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
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from typing import Protocol

import questionary

from ..config import mask_tokens
from ..safetext import strip_control
from .texts import Pytanie

TAK = "tak"
NIE = "nie"


def _do_pytania(napis: str) -> str:
    """Neutralizator napisu przed terminalem przez `questionary` — lustro `richtext.safe`."""
    return mask_tokens(strip_control(napis))


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
        if not self._terminal:
            return self._bez_terminala(pytanie)
        odpowiedz = self._pytanie_questionary(pytanie).ask()
        if odpowiedz is None:
            # `questionary` zwraca `None` po Ctrl+C — to jest przerwanie, nie odpowiedź.
            raise KeyboardInterrupt
        if isinstance(odpowiedz, bool):
            return TAK if odpowiedz else NIE
        return str(odpowiedz)

    def _pytanie_questionary(self, pytanie: Pytanie) -> questionary.Question:
        if pytanie.rodzaj == "tak_nie":
            return questionary.confirm(_do_pytania(pytanie.tresc), default=pytanie.domyslna == TAK)
        if pytanie.rodzaj == "tekst":
            return questionary.text(
                _do_pytania(pytanie.tresc), default=_do_pytania(pytanie.domyslna or "")
            )
        return questionary.select(
            _do_pytania(pytanie.tresc),
            choices=[
                questionary.Choice(title=_do_pytania(o.etykieta), value=o.klucz)
                for o in pytanie.opcje
            ],
            default=pytanie.domyslna,
        )

    def _bez_terminala(self, pytanie: Pytanie) -> str:
        """Numerowana lista na `input()` — zapas dla potoku, nie ścieżka główna."""
        if pytanie.rodzaj == "wybor":
            wiersze = [f"  {n}. {_do_pytania(o.etykieta)}" for n, o in enumerate(pytanie.opcje, 1)]
            odpowiedz = self._wejscie(
                "\n".join([_do_pytania(pytanie.tresc), *wiersze, "> "])
            ).strip()
            if odpowiedz.isdigit() and 1 <= int(odpowiedz) <= len(pytanie.opcje):
                return pytanie.opcje[int(odpowiedz) - 1].klucz
            return pytanie.domyslna or pytanie.opcje[0].klucz
        odpowiedz = self._wejscie(f"{_do_pytania(pytanie.tresc)} ").strip()
        if pytanie.rodzaj == "tak_nie":
            if not odpowiedz:
                return pytanie.domyslna or NIE
            return TAK if odpowiedz.lower() in {"t", "tak", "y", "yes"} else NIE
        return odpowiedz or (pytanie.domyslna or "")


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
