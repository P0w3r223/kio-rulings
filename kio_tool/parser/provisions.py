"""Przepisy powołane w orzeczeniu — z treści i z listy kanału, każdy z ustawą (ADR-0006 Z-7…Z-9).

Dwa źródła i kolumna, która je rozróżnia (Z-7): `tresc` to nasz odczyt z tekstu orzeczenia,
`kanal` to lista `law_articles` od Atlasu — opracowanie pośrednika o znanym pochodzeniu. Żadne nie
nadpisuje drugiego, a ich niezgodność jest informacją: najtańszym niezależnym sprawdzianem cudzego
potoku, jaki mamy bez żądań.

Przepis nosi ustawę (Z-8), bo korpus obejmuje dwa reżimy Pzp: ustawę z 29 stycznia 2004 r.
i ustawę z 11 września 2019 r. (obowiązuje od 2021-01-01) — „art. 186 ust. 2 Pzp" w orzeczeniu
z 2020 r. i z 2024 r. to dwa różne przepisy. Ustawa pochodzi **z treści, nigdy z daty**:

- przy przepisie stoi pełny tytuł z datą ustawy → ta ustawa;
- przy przepisie stoi skrót („Pzp", „ustawy Pzp", „p.z.p.") → ustawa Pzp, którą dokument nazywa
  pełnym tytułem, jeśli nazywa **dokładnie jedną**; jeśli żadnej albo obie — `nieustalone`.

Zmierzone 2026-09-19 na 443 dokumentach (0 żądań): 258 nazywa wyłącznie Pzp 2019, 69 wyłącznie
Pzp 2004, 15 obie, a **101 żadnej** — z tego 95 z roku 2024, czyli z czasu, w którym obowiązuje
jedna ustawa. Zgadywanie z daty byłoby tam trafne i właśnie dlatego kuszące; Z-8 go zakazuje,
bo data w tym kanale bywa błędna (9 na 100, pomiar 3a), a zdanie „w 2024 r. obowiązuje Pzp 2019"
nie mówi, czego dotyczy odwołanie wszczęte w postępowaniu sprzed 2021 r.

Słownika przepisów tu nie ma (Z-13): normalizacja jest gramatyką, nie sprawdzeniem wobec listy.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from .clean import normalizuj
from .sections import Sekcja

Akt = Literal["pzp2004", "pzp2019", "kc", "kpc", "rozporzadzenie", "inne", "nieustalone"]
AKTY: tuple[Akt, ...] = (
    "pzp2004",
    "pzp2019",
    "kc",
    "kpc",
    "rozporzadzenie",
    "inne",
    "nieustalone",
)
ZrodloPrzepisu = Literal["tresc", "kanal"]

_ARTYKUL = re.compile(
    r"(?i)\bart\.\s*(?P<art>\d+[a-z]?)"
    r"(?:\s*ust\.\s*(?P<ust>\d+[a-z]?))?"
    r"(?:\s*pkt\.?\s*(?P<pkt>\d+[a-z]?))?"
    r"(?:\s*lit\.\s*(?P<lit>[a-z])\)?)?"
)
"""`art. 226 ust. 1 pkt 5 lit. a` — 13 095 trafień `art.` w korpusie (2026-09-19)."""

# Data słownie **albo cyframi**. Zapis cyfrowy („ustawy z dnia 29.01.2004 r. Prawo Zamówień
# Publicznych") ma w korpusie 3 wystąpienia w 3 dokumentach (pomiar 2026-09-20, 0 żądań) — mało,
# ale każde z nich dawało wartość **błędną**, a nie brakującą: generyczne „ustawy z dnia" stoi
# w tym samym miejscu co pełny tytuł, więc przy remisie wygrywa wzorzec zadeklarowany wcześniej,
# a bez tej gałęzi był nim `inne`. Znalezione okiem w złotym zbiorze (O-4).
_PZP_2004 = re.compile(r"(?i)ustaw\w*\s+z\s+dnia\s+29(?:\s+stycznia\s+|[.\s-]*0?1[.\s-]*)2004")
_PZP_2019 = re.compile(r"(?i)ustaw\w*\s+z\s+dnia\s+11(?:\s+wrze[sś]nia\s+|[.\s-]*0?9[.\s-]*)2019")

# Oznaczenie ustawy za przepisem. Kolejność ma znaczenie: pełny tytuł z datą przed skrótem, bo
# „ustawy z dnia 11 września 2019 r. – Prawo zamówień publicznych" niesie i jedno, i drugie.
# Postaci skrótu z pomiaru ogonów za `art.` (2026-09-19): `ustawy Pzp` 1 562, `ustawy PZP` 254,
# `ustawy pzp` 127, `ustawy P.z.p.` 67 i warianty z przecinkiem i kropką.
#
# `praw\w*`, a nie `prawa?` — poprawka z przeglądu okiem złotego zbioru (O-4, 2026-09-20).
# Mianownik „ustawy **Prawo** zamówień publicznych" nie pasował do `prawa?\s+`, bo po „praw"
# stało „o", a nie spacja. Skutek był cichy i mylący: w zdaniu o kosztach („orzeczono na
# podstawie art. 574 i 575 ustawy Prawo zamówień publicznych oraz § … rozporządzenia…") wygrywało
# **następne** oznaczenie w oknie, czyli `rozporządzenie`, i przepis Pzp lądował jako przepis
# rozporządzenia. Znalezione okiem na 27 przepisach spoza Pzp w złotym zbiorze — automat nie miał
# jak tego zapalić, bo `rozporzadzenie` jest poprawną wartością pola.
_OZNACZENIA: tuple[tuple[re.Pattern[str], Akt | None], ...] = (
    (_PZP_2004, "pzp2004"),
    (_PZP_2019, "pzp2019"),
    (re.compile(r"(?i)\bp\.?\s?z\.?\s?p\b\.?|praw\w*\s+zamówień\s+publicznych"), None),
    (re.compile(r"(?i)\bk\.\s?p\.\s?c\.|kodeksu\s+postępowania\s+cywilnego|\bkpc\b"), "kpc"),
    (re.compile(r"(?i)\bk\.\s?c\.|kodeksu\s+cywilnego|\bkc\b"), "kc"),
    (re.compile(r"(?i)\brozporządzeni"), "rozporzadzenie"),
    (re.compile(r"(?i)\bustaw\w*\s+(?:o|z\s+dnia)\b"), "inne"),
)
"""`None` przy skrócie Pzp znaczy: ustawę bierze się z dokumentu (`akt_pzp_dokumentu`)."""

_OKNO_OZNACZENIA = 160
"""Jak daleko za przepisem szukać oznaczenia ustawy. Wyliczenie „art. 226 ust. 1 pkt 5 i art. 224
ust. 6 ustawy Pzp" niesie oznaczenie raz, na końcu — okno obejmuje je dla wszystkich pozycji."""

_KONIEC_ZDANIA = re.compile(r"\.\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ])")


@dataclass(frozen=True)
class Przepis:
    """Jeden przepis: postać kanoniczna, ustawa, źródło i — dla treści — przedział w oryginale."""

    porzadek: int
    postac: str
    akt: Akt
    zrodlo: ZrodloPrzepisu
    surowy: str
    start: int | None = None
    koniec: int | None = None


def akt_pzp_dokumentu(tekst: str) -> Akt:
    """Ustawa Pzp nazwana pełnym tytułem — gdy dokładnie jedna; inaczej `nieustalone`."""
    widok = normalizuj(tekst).tekst
    stara, nowa = bool(_PZP_2004.search(widok)), bool(_PZP_2019.search(widok))
    if stara and not nowa:
        return "pzp2004"
    if nowa and not stara:
        return "pzp2019"
    return "nieustalone"


def przepisy_z_tresci(oryginal: str, sekcje: Iterable[Sekcja]) -> tuple[Przepis, ...]:
    """Przepisy ze wszystkich sekcji dokumentu, w kolejności wystąpienia, z ustawą z treści."""
    akt_dokumentu = akt_pzp_dokumentu(oryginal)
    wynik: list[Przepis] = []
    for sekcja in sekcje:
        widok = normalizuj(oryginal[sekcja.start : sekcja.koniec])
        for m in _ARTYKUL.finditer(widok.tekst):
            a, b = widok.w_oryginale(m.start(), m.end())
            wynik.append(
                Przepis(
                    porzadek=len(wynik),
                    postac=_postac(m),
                    akt=_akt_za(widok.tekst, m.end(), akt_dokumentu),
                    zrodlo="tresc",
                    surowy=oryginal[sekcja.start + a : sekcja.start + b],
                    start=sekcja.start + a,
                    koniec=sekcja.start + b,
                )
            )
    return tuple(wynik)


def przepisy_z_kanalu(lista: Sequence[str], oryginal: str) -> tuple[Przepis, ...]:
    """Lista przepisów od kanału (`law_articles`) tą samą gramatyką, z ustawą z treści dokumentu.

    Kanał podaje przepis **bez wskazania ustawy** („art. 186 ust. 2 Pzp") — ADR-0006 §1.1 — więc
    skrót rozstrzyga się jak w treści: ustawą, którą dokument nazywa, albo `nieustalone`.
    Pozycja, w której gramatyka nie znajduje artykułu, zostaje z postacią surową i aktem
    `nieustalone`: lepsza jawna pozycja niż zgubiona.
    """
    akt_dokumentu = akt_pzp_dokumentu(oryginal)
    wynik: list[Przepis] = []
    for pozycja in lista:
        m = _ARTYKUL.search(pozycja)
        wynik.append(
            Przepis(
                porzadek=len(wynik),
                postac=_postac(m) if m is not None else pozycja.strip(),
                akt=_akt_za(pozycja, m.end(), akt_dokumentu) if m is not None else "nieustalone",
                zrodlo="kanal",
                surowy=pozycja,
            )
        )
    return tuple(wynik)


def _postac(m: re.Match[str]) -> str:
    czesci = [f"art. {m.group('art')}"]
    for nazwa, skrot in (("ust", "ust."), ("pkt", "pkt"), ("lit", "lit.")):
        if m.group(nazwa):
            czesci.append(f"{skrot} {m.group(nazwa)}")
    return " ".join(czesci)


def _akt_za(tekst: str, od: int, akt_dokumentu: Akt) -> Akt:
    """Ustawa z oznaczenia za przepisem, w obrębie zdania i `_OKNO_OZNACZENIA` znaków."""
    okno = tekst[od : od + _OKNO_OZNACZENIA]
    koniec = _KONIEC_ZDANIA.search(okno)
    if koniec is not None:
        okno = okno[: koniec.start()]
    najblizsze: tuple[int, Akt] | None = None
    for wzor, akt in _OZNACZENIA:
        trafienie = wzor.search(okno)
        if trafienie is None:
            continue
        rozstrzygniety: Akt = akt_dokumentu if akt is None else akt
        if najblizsze is None or trafienie.start() < najblizsze[0]:
            najblizsze = (trafienie.start(), rozstrzygniety)
    return najblizsze[1] if najblizsze is not None else "nieustalone"
