"""Kreator: pierwszy ekran, menu, pętla (ADR-0008 Z-7…Z-9) — operator, który nie zna poleceń.

`kio-tool` bez argumentów na terminalu otwiera kreator (Z-8, decyzja właściciela 2026-09-19);
`kio-tool demo` otwiera go nad bazą pokazową. Kreator nie pobiera niczego sam: każda pozycja menu
woła sekwencję z `flow.py`, a ta — `Akcje` z `cli.py`. Pierwsza pozycja to „Wznów", gdy jest co
wznawiać: przerwany przebieg jest najczęstszym powodem, dla którego ktoś wraca do programu.

`Ctrl+C` w menu kończy program; w trakcie akcji — kończy akcję (`flow.bezpiecznie`) i wraca do menu.
"""

from __future__ import annotations

from . import flow, texts
from .flow import Akcje, Ekran
from .prompts import Prompter

KROKI = {
    texts.MENU_WZNOW: flow.krok_wznow,
    texts.MENU_POBIERZ: flow.krok_pobierz,
    texts.MENU_SZUKAJ: flow.krok_szukaj,
    texts.MENU_EKSPORTUJ: flow.krok_eksportuj,
}


def uruchom(prompter: Prompter, akcje: Akcje, ekran: Ekran, *, pokaz: bool = False) -> None:
    """Pętla kreatora do „Wyjdź" albo `Ctrl+C` w menu."""
    ekran.block(texts.pierwszy_ekran(pokaz=pokaz, stan=akcje.stan()))
    while True:
        try:
            stan = akcje.stan()
            wybor = prompter.zapytaj(
                texts.pytanie_menu(jest_co_wznowic=bool(stan.przerwanych), stan=stan)
            )
        except KeyboardInterrupt:
            return
        krok = KROKI.get(wybor)
        if krok is None:
            return
        try:
            krok(prompter, akcje, ekran)
        except KeyboardInterrupt:
            # Przerwanie w pytaniu wewnątrz kroku (poza akcją) — powrót do menu, nie wyjście.
            ekran.message(texts.PRZERWANO_PYTANIE)
