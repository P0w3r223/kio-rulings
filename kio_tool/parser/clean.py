"""Widok znormalizowany tekstu orzeczenia **razem z mapą offsetów** do oryginału (ADR-0006 Z-6).

`clean` nie produkuje treści, produkuje widok. Segmentacja, cytowania i przepisy szukają kotwic
w tekście znormalizowanym, ale wszystko, co trafia do bazy, jest offsetem w **oryginale**
(`full_text` tak, jak przyszedł — reguła 19). Cytat w eksporcie i w fazie 4 ma dać się sprawdzić
przy źródle, a napis po czyszczeniu byłby napisem, którego u dostawcy nie ma (Z-5).

Co widok zmienia — każda pozycja z pomiaru 5, część lokalna (2026-09-19, 341 dokumentów, 0 żądań;
`docs/decisions.md`, „Pomiar 5"), nie z wyobrażenia o materiale:

- wysuw strony `\\f` znika (100 % dokumentów, 2 110 wystąpień) — granica strony PDF-a nie jest
  granicą niczego w orzeczeniu, a w indeksie i w kotwicach przeszkadza;
- łamanie wiersza w środku zdania staje się spacją (100 % dokumentów, 60 090 wystąpień): wiersz
  kończący się czymś innym niż znak końca zdania albo dwukropek i następny zaczynający się małą
  literą albo cyfrą to jedno zdanie, nie dwa;
- ciągi spacji, tabulatorów i twardych spacji stają się jedną spacją, puste wiersze znikają,
  a spacje na brzegach wiersza są obcinane.

Czego widok **nie** zmienia: liter, cudzysłowów, myślników ani wielkości liter. Nagłówek
rozstrzelony spacjami (`Uz as adnienie`, 25,8 % dokumentów) zostaje rozstrzelony — rozpoznaje go
`sections.py` wzorcem tolerującym spacje między literami, bo sklejanie liter na ślepo skleiłoby
też słowa, które spacji potrzebują.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PUNKT_WYLICZENIA = re.compile(r"\d{1,3}\s?\.(?!\d)")
"""Punkt wyliczenia na początku wiersza: `1.`, `35.` — ale nie `1.5` ani data `16.01.2024`."""

_BIALE_W_WIERSZU = frozenset(" \t\u00a0\u2007\u202f")
"""Znaki zwijane do jednej spacji. Twarda spacja jest tu, bo ekstrakcja z PDF-a zostawia ją
między numerem a jednostką („art. 89\u00a0ust."), a kotwica ma trafiać niezależnie od tego."""

_KONIEC_ZDANIA = frozenset(".:;!?")
"""Znak, po którym łamanie wiersza zostaje łamaniem — `orzeka:` przed punktami sentencji też."""


@dataclass(frozen=True)
class Widok:
    """Tekst znormalizowany i offset w oryginale każdego jego znaku.

    `offsety` ma długość `len(tekst) + 1`: ostatni element to koniec oryginału, więc przedział
    `[i, j)` w widoku daje przedział `[offsety[i], offsety[j])` w oryginale bez przypadku
    szczególnego na końcu.
    """

    tekst: str
    offsety: tuple[int, ...]

    def w_oryginale(self, start: int, koniec: int) -> tuple[int, int]:
        """Przedział widoku `[start, koniec)` jako przedział w oryginale."""
        if not 0 <= start <= koniec <= len(self.tekst):
            raise ValueError(
                f"Przedział [{start}, {koniec}) wychodzi poza widok długości {len(self.tekst)}."
            )
        if start == koniec:
            pozycja = self.offsety[start]
            return pozycja, pozycja
        return self.offsety[start], self.offsety[koniec - 1] + 1


def normalizuj(oryginal: str) -> Widok:
    """Widok znormalizowany `oryginal` z mapą offsetów — funkcja czysta, bez wyjątków."""
    znaki: list[str] = []
    offsety: list[int] = []
    poprzedni_wiersz = ""
    for numer, wiersz_start, wiersz in _wiersze(oryginal):
        tresc = _zwin_biale(wiersz, wiersz_start)
        if not tresc:
            continue
        if znaki:
            laczy = (
                znaki[-1] not in _KONIEC_ZDANIA
                and not _naglowek(poprzedni_wiersz)
                and _zaczyna_zdanie_dalej("".join(znak for znak, _ in tresc[:8]))
            )
            # Separator dostaje offset znaku końca poprzedniego wiersza w oryginale — łamanie,
            # które zastępuje, stało właśnie tam.
            znaki.append(" " if laczy else "\n")
            offsety.append(wiersz_start - 1 if numer else 0)
        for znak, pozycja in tresc:
            znaki.append(znak)
            offsety.append(pozycja)
        poprzedni_wiersz = "".join(znak for znak, _ in tresc)
    offsety.append(len(oryginal))
    return Widok(tekst="".join(znaki), offsety=tuple(offsety))


def _wiersze(oryginal: str) -> list[tuple[int, int, str]]:
    """Wiersze oryginału z offsetem początku; `\\f` i `\\r` są usuwane, nie zamieniane na łamanie.

    Usunięte w miejscu, a nie przez `replace` przed podziałem, bo offset każdego znaku ma
    wskazywać jego pozycję w **nietkniętym** oryginale.
    """
    wynik: list[tuple[int, int, str]] = []
    start = 0
    numer = 0
    for pozycja, znak in enumerate(oryginal):
        if znak == "\n":
            wynik.append((numer, start, oryginal[start:pozycja]))
            numer += 1
            start = pozycja + 1
    wynik.append((numer, start, oryginal[start:]))
    return wynik


def _zwin_biale(wiersz: str, wiersz_start: int) -> list[tuple[str, int]]:
    """Znaki wiersza bez `\\f`/`\\r`, z białymi zwiniętymi do jednej spacji i obciętymi brzegami."""
    wynik: list[tuple[str, int]] = []
    for przesuniecie, znak in enumerate(wiersz):
        if znak in "\f\r":
            continue
        pozycja = wiersz_start + przesuniecie
        if znak in _BIALE_W_WIERSZU:
            if wynik and wynik[-1][0] != " ":
                wynik.append((" ", pozycja))
            continue
        wynik.append((znak, pozycja))
    while wynik and wynik[-1][0] == " ":
        wynik.pop()
    return wynik


def _naglowek(wiersz: str) -> bool:
    """Wiersz z samych wielkich liter (`WYROK`, `POSTANOWIENIE`) jest nagłówkiem, nie zdaniem —
    „z dnia 5 stycznia" pod nim zaczyna się małą literą, a doklejone dałoby `WYROK z dnia`."""
    litery = [znak for znak in wiersz if znak.isalpha()]
    return len(litery) >= 2 and all(znak.isupper() for znak in litery)


def _zaczyna_zdanie_dalej(poczatek: str) -> bool:
    """Czy wiersz zaczynający się tym napisem ciągnie zdanie z wiersza poprzedniego.

    Punkt wyliczenia (`1.`, `35.`) zaczyna nowy wiersz, choć zaczyna się cyfrą: doklejony do
    `Uzasadnienie` dawał `Uzasadnienie 35. Krakowski…` i nagłówek przestawał być wierszem
    (`KIO 3778/23`, 2026-09-19).
    """
    if _PUNKT_WYLICZENIA.match(poczatek):
        return False
    znak = poczatek[0]
    return znak.islower() or znak.isdigit() or znak in ",)–-"
