"""Magazyn korpusu (SQLite) — fasada pakietu `store/` (ADR-0009, 2026-09-22).

Do 2026-09-22 jeden plik `store.py` (1 466 linii, ponad sufitem projektu — O-5). Fasada wystawia
dokładnie dawną publiczną powierzchnię, więc `from .store import Store, Filtr` działa bez zmian;
`tests/test_fasady.py` przypina `__all__`. Nazwę trzymaną przez kilka modułów pakietu testy
podstawiają we wszystkich naraz (`wsparcie_sondy.podstaw_w_pakiecie`, ADR-0009 Z-3).

Podział: `schemat` (DDL i historia schematów), `model` (klasy danych), `polaczenie` (szew ze
sterownikiem i rdzeń `Store`), `zapis`, `wyszukiwanie`, `przebiegi` (klasy cząstkowe), `magazyn`
(`Store`, otwarcie, tryb, migracje). Reguły 3 i 4 obejmują cały pakiet rekursywnie.
"""

from __future__ import annotations

from .magazyn import DOMYSLNY_BUSY_TIMEOUT_S, Store
from .model import (
    STATUSY_PRZEBIEGU,
    STATUSY_WZNAWIALNE,
    Dokument,
    Filtr,
    Metryka,
    Przebieg,
    Struktura,
    StrukturaDokumentu,
    Trafienie,
    WierszCytowania,
    WierszPrzepisu,
    WierszSekcji,
    Wyszukanie,
)
from .polaczenie import blad_bazy
from .schemat import ID_BAZY_POKAZOWEJ, SCHEMA_VERSION, TABELE
from .wyszukiwanie import DOMYSLNY_LIMIT_TRAFIEN, KOLUMNA_FTS_TRESCI

__all__ = [
    "DOMYSLNY_BUSY_TIMEOUT_S",
    "DOMYSLNY_LIMIT_TRAFIEN",
    "ID_BAZY_POKAZOWEJ",
    "KOLUMNA_FTS_TRESCI",
    "SCHEMA_VERSION",
    "STATUSY_PRZEBIEGU",
    "STATUSY_WZNAWIALNE",
    "TABELE",
    "Dokument",
    "Filtr",
    "Metryka",
    "Przebieg",
    "Store",
    "Struktura",
    "StrukturaDokumentu",
    "Trafienie",
    "WierszCytowania",
    "WierszPrzepisu",
    "WierszSekcji",
    "Wyszukanie",
    "blad_bazy",
]
