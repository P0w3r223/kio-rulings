"""Zegar jako zależność wstrzykiwana — jedyne `time.sleep` na ścieżce do źródła.

Przeniesione z `ceidg-tool` bez zmian w zachowaniu. Powód przeniesienia: bez wstrzykiwanego
zegara testy czekania są niewykonalne, a czekanie jest tu regułą, nie wyjątkiem — limiter
trzyma odstęp między żądaniami przez godziny.

W tym projekcie docstring „jedyne miejsce" ma szansę pozostać prawdą: warstwa modelu jest
osobnym procesem (serwer MCP, architektura 4.10), więc drabinka ponowień SDK — drugie
`time.sleep` w CEIDG — nie ma jak wejść do tego pakietu.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Zegar monotoniczny do odstępów, ścienny do trwałych znaczników i komunikatów."""

    def monotonic(self) -> float: ...

    def wall(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """Zegar systemowy."""

    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


def utc_iso(epoch: float) -> str:
    """Znacznik czasu UTC w formacie ISO bez mikrosekund, z sufiksem `Z`.

    Format kolumn `fetched_at`, `first_seen_at`, `last_seen_at` z modelu danych (4.4).
    Jedna postać czasu w całej bazie, bo porównanie wersji dokumentu po dacie jest
    operacją, którą `porownaj` i `aktualizuj` wykonują na tekście, nie na obiekcie.
    """
    stamp = datetime.fromtimestamp(epoch, tz=UTC).replace(microsecond=0)
    return stamp.isoformat().replace("+00:00", "Z")


def local_hhmm(epoch: float) -> str:
    """Godzina lokalna `HH:MM` do komunikatów typu „wznawiam o …”."""
    return datetime.fromtimestamp(epoch).strftime("%H:%M")


# Jak w `progress.py`: bez przypisania mypy nie sprawdza, czy `SystemClock` spełnia `Clock`.
_ZGODNOSC_Z_PROTOKOLEM: Clock = SystemClock()
