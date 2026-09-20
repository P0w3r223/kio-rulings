"""Wycena przebiegu przed pierwszym dokumentem — czysta, bez sieci i bez bazy (ADR-0008 Z-5).

Liczby pochodzą z punktu, który potok już ma w ręku: `total` zgłoszony przez kanał na pierwszej
stronie listy (ADR-0008 §1.1, Przebieg 1). Osobne żądanie „policz" kosztowałoby stronę pierwszą
dwa razy — więc wycena nie wysyła niczego.

**Wszystkie liczby są górną granicą.** Dokument już obecny w bazie nie kosztuje żądania, a potok
dowie się o tym dopiero, idąc po liście. Czas jest czasem **produkcyjnym** z tempa kontraktu —
z oknami, nie tylko z odstępem: przy oknie dobowym 1 400 żądań rocznik (~4 300 żądań) to trzy
doby, a nie `4 300 × 1 s ≈ 72 min` (ADR-0008 Z-5). Tabela pokazu drukuje ten sam czas obok
czasu pokazu, żeby przyspieszony zegar nie uczył fałszywych oczekiwań (Z-13).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Wycena:
    """Koszt reszty przebiegu. `None` przy dokumentach znaczy: kanał nie zgłosił liczby."""

    dokumentow: int | None
    stron_listy: int | None
    zadan: int | None
    czas_s: float | None
    zadan_juz: int
    """Żądania, które ten przebieg już wysłał (strony listy, wznowienie) — wliczone w próg zgody."""


def wycen(
    *,
    zgloszone: int | None,
    maks: int | None,
    juz_objetych: int,
    zadan_juz: int,
    na_strone: int,
    odstep_s: float,
    okna: Sequence[tuple[int, float]],
) -> Wycena:
    """Wycena reszty przebiegu z liczby zgłoszonej przez kanał, przyciętej przez `--maks`."""
    if zgloszone is None:
        dokumenty = maks
    else:
        dokumenty = zgloszone if maks is None else min(zgloszone, maks)
    if dokumenty is None:
        return Wycena(None, None, None, None, zadan_juz)
    reszta = max(0, dokumenty - juz_objetych)
    strony = max(0, math.ceil(dokumenty / na_strone) - 1) if na_strone > 0 else 0
    zadan = reszta + strony
    return Wycena(reszta, strony, zadan, czas_zadan(zadan, odstep_s, okna), zadan_juz)


def czas_zadan(zadan: int, odstep_s: float, okna: Sequence[tuple[int, float]]) -> float:
    """Najkrótszy czas, w jakim limiter puści `zadan` żądań: maksimum po odstępie i oknach.

    Okno `(limit, sekund)` puszcza `limit` żądań, potem każe czekać do końca okna — więc `n`
    żądań zajmuje co najmniej `⌊(n − 1) / limit⌋ × sekund`. Odstęp daje `(n − 1) × odstep_s`.
    To jest dolne oszacowanie **czasu** przy górnym oszacowaniu **żądań**: nie wlicza czasu
    odpowiedzi serwisu ani postojów po 429.
    """
    if zadan <= 0:
        return 0.0
    kandydaci = [(zadan - 1) * odstep_s]
    kandydaci += [((zadan - 1) // limit) * sekund for limit, sekund in okna if limit > 0]
    return float(max(kandydaci))
