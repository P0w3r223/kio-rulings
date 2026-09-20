"""Cytowania orzeczeń w uzasadnieniu — offsety w oryginale, sygnatura kanoniczna z `docid`.

Potok z architektury 3.5 (`eyecite`) w wersji tego projektu: clean → extract → resolve. `clean`
daje widok z mapą offsetów (`clean.py`), `extract` szuka sygnatur przez `docid.znajdz_sygnatury`
(jedyny normalizator — reguła 14), a `resolve` — czy cytowane orzeczenie KIO jest w korpusie —
robi `pipeline`, bo wymaga bazy, której parser nie widzi (reguła 1).

Szukane jest **w uzasadnieniu i zdaniu odrębnym**, nie w całym dokumencie: sygnatura własna
stoi w nagłówku i w stopkach stron, a cytowaniem nie jest. Sygnatura własna w uzasadnieniu też
nie jest cytowaniem („w sprawie o sygn. akt KIO 1/24 Izba…") i jest pomijana po postaci
kanonicznej.

Cytowanie nierozpoznane nie znika: napis „sygn. akt …", za którym nie stoi rozpoznana
sygnatura, trafia do wyniku z rodzajem `inne` i sygnaturą `None` — i jest liczony w raporcie
pokrycia (architektura 4.4: „cicha strata jest tu gorsza niż jawna dziura"). To jest też jedyny
sposób, żeby pomiar 22 („udział nieznormalizowanych") miał mianownik.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from ..docid import RodzajSygnatury, normalize_signature, znajdz_sygnatury
from .clean import normalizuj
from .sections import Sekcja

SEKCJE_CYTOWAN = frozenset({"uzasadnienie", "zdanie_odrebne"})
"""Sekcje, w których cytowanie jest cytowaniem — nagłówek i stopki niosą sygnaturę własną."""

_SYGN_AKT = re.compile(r"(?i)\bsygn\.\s*akt\.?\s*:?\s*")
"""„sygn. akt" — zapowiedź sygnatury. Gdy za nią nie stoi rozpoznana sygnatura, jest to
cytowanie nierozpoznane, a nie brak cytowania."""

_OKNO_ZAPOWIEDZI = 40
"""Ile znaków za „sygn. akt" może zacząć się sygnatura, żeby zapowiedź uznać za spełnioną."""


@dataclass(frozen=True)
class Cytowanie:
    """Jedno cytowanie: przedział w oryginale, napis surowy, organ i sygnatura kanoniczna."""

    porzadek: int
    start: int
    koniec: int
    surowy: str
    rodzaj: RodzajSygnatury
    sygnatura: str | None
    """`None` wyłącznie dla cytowania nierozpoznanego (rodzaj `inne` z zapowiedzi `sygn. akt`)."""


def cytowania(
    oryginal: str, sekcje: Iterable[Sekcja], *, wlasne: Iterable[str] = ()
) -> tuple[Cytowanie, ...]:
    """Cytowania z sekcji `SEKCJE_CYTOWAN`, bez sygnatur własnych dokumentu, w kolejności."""
    wlasne_kanon = {k for k in (normalize_signature(w) for w in wlasne) if k is not None}
    wynik: list[Cytowanie] = []
    for sekcja in sekcje:
        if sekcja.rodzaj not in SEKCJE_CYTOWAN:
            continue
        for start, koniec, rodzaj, kanon in _w_sekcji(oryginal, sekcja):
            if rodzaj == "kio" and kanon in wlasne_kanon:
                continue
            wynik.append(
                Cytowanie(
                    porzadek=len(wynik),
                    start=start,
                    koniec=koniec,
                    surowy=oryginal[start:koniec],
                    rodzaj=rodzaj,
                    sygnatura=kanon,
                )
            )
    return tuple(wynik)


def _w_sekcji(oryginal: str, sekcja: Sekcja) -> list[tuple[int, int, RodzajSygnatury, str | None]]:
    """Trafienia w jednej sekcji jako przedziały w oryginale."""
    widok = normalizuj(oryginal[sekcja.start : sekcja.koniec])
    trafienia = znajdz_sygnatury(widok.tekst)
    wynik: list[tuple[int, int, RodzajSygnatury, str | None]] = []
    for t in trafienia:
        a, b = widok.w_oryginale(t.start, t.koniec)
        wynik.append((sekcja.start + a, sekcja.start + b, t.rodzaj, t.kanon))
    poczatki = [t.start for t in trafienia]
    for zapowiedz in _SYGN_AKT.finditer(widok.tekst):
        spelniona = any(0 <= p - zapowiedz.end() <= _OKNO_ZAPOWIEDZI for p in poczatki)
        if spelniona:
            continue
        koniec = _koniec_napisu(widok.tekst, zapowiedz.end())
        a, b = widok.w_oryginale(zapowiedz.start(), koniec)
        wynik.append((sekcja.start + a, sekcja.start + b, "inne", None))
    wynik.sort(key=lambda trafienie: trafienie[0])
    return wynik


def _koniec_napisu(tekst: str, od: int) -> int:
    """Koniec napisu po zapowiedzi: do przecinka, średnika, nawiasu albo końca wiersza."""
    dopasowanie = re.compile(r"[^,;)\n]{0,30}").match(tekst, od)
    return dopasowanie.end() if dopasowanie is not None else od
