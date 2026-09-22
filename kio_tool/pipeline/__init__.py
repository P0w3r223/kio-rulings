"""Orkiestracja: kryteria → kanał → magazyn → parser → eksport — fasada pakietu (ADR-0009).

Do 2026-09-22 jeden plik `pipeline.py` (971 → 921 linii, ponad sufitem — O-5). Podział:
`pobieranie` (pobierz i wznow — **jedyny** moduł widzący naraz `source/` i `store`, reguła 5),
`lokalne` (eksport, przeliczenie, wyszukiwanie — zero żądań, bez `source` i `httpclient`),
`zgoda` (próg, werdykt wyceny, sufit), `slad` (puls i dziennik żądań).

Fasada wystawia dawną publiczną powierzchnię (`tests/test_fasady.py` przypina `__all__`) i **nie**
wystawia szwów podstawianych w testach: `build_http_client` i `default_output_dir` mieszkają
w modułach, które je czytają. Fasada z tymi nazwami zamieniłaby `monkeypatch.setattr(pipeline,
"build_http_client", …)` w podstawienie bez skutku — a fabryka zabroniona w testach operacji bez
sieci przestałaby czegokolwiek pilnować (ADR-0009 Z-3).
"""

from __future__ import annotations

from ..wycena import Wycena
from .lokalne import (
    FORMATY_DOMYSLNE,
    ODCINEK_BEZ_SEKCJI,
    Orzeczenie,
    WynikEksportu,
    WynikPrzeliczenia,
    build_metadata,
    czytaj,
    eksportuj,
    przelicz,
    szukaj,
)
from .pobieranie import (
    KANAL_DOMYSLNY,
    PROG_404_POD_RZAD,
    STATUS_PRZERWANY,
    KlientFactory,
    Podsumowanie,
    do_wznowienia,
    kanaly,
    pobierz,
    wznow,
    zakres_z_kryteriow,
)
from .zgoda import ODMOWA_PO_WYCENIE, PROG_ZGODY, Decyzja, Werdykt, decyzja_z_flagi

__all__ = [
    "FORMATY_DOMYSLNE",
    "KANAL_DOMYSLNY",
    "ODCINEK_BEZ_SEKCJI",
    "ODMOWA_PO_WYCENIE",
    "PROG_404_POD_RZAD",
    "PROG_ZGODY",
    "STATUS_PRZERWANY",
    "Decyzja",
    "KlientFactory",
    "Orzeczenie",
    "Podsumowanie",
    "Werdykt",
    "Wycena",
    "WynikEksportu",
    "WynikPrzeliczenia",
    "build_metadata",
    "czytaj",
    "decyzja_z_flagi",
    "do_wznowienia",
    "eksportuj",
    "kanaly",
    "pobierz",
    "przelicz",
    "szukaj",
    "wznow",
    "zakres_z_kryteriow",
]
