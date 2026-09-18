"""Rysowanie modeli widoku przez `rich`. Jedyna wiedza o wyglądzie, zero decyzji.

Napis z korpusu (sygnatura, fragment uzasadnienia, nazwa strony) trafia tu jako `rich.Text`
z `richtext.safe`, nigdy jako znaczniki — reguła 10, pilnowana skanem tego pliku
w `tests/test_boundaries.py`. Neutralizacja siedzi w `richtext.safe`; tutaj zostaje samo
rysowanie: tabela dla bloku z nagłówkami, lista klucz–wartość dla bloku bez nich, wiersz dla
zdania. Kształt przeniesiony z `ceidg-tool` (`ui/render.py`) z jedną zmianą: błędy idą na
`stderr`, żeby przekierowanie wyniku do pliku nie zjadło komunikatu o tym, czemu wyniku nie ma.

Reguła 8: ten moduł nie importuje `source` ani `store` — dostaje `Block` z `texts`.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Column, Table

from ..richtext import make_console, safe, safe_or_none
from .texts import Block

STYL_UWAGI = "yellow"
STYL_BLEDU = "bold red"
STYL_TYTULU = "bold"


class ConsoleView:
    """Widok konsolowy: bloki z `texts` na ekran, komunikaty przez filtr maskujący sekrety."""

    def __init__(self, console: Console | None = None, bledy: Console | None = None) -> None:
        self.console = console or make_console()
        self.bledy = bledy or make_console(stderr=True)

    def block(self, block: Block) -> None:
        tytul = safe_or_none(block.title)
        if block.headers:
            naglowki = [Column(header=safe(h), overflow="fold") for h in block.headers]
            tabela = Table(*naglowki, title=tytul, title_justify="left")
            for wiersz in block.rows:
                tabela.add_row(*(safe(komorka) for komorka in wiersz))
        else:
            tabela = Table(title=tytul, show_header=False, title_justify="left")
            tabela.add_column("klucz", style=STYL_TYTULU)
            tabela.add_column("wartość", overflow="fold")
            for wiersz in block.rows:
                tabela.add_row(*(safe(komorka) for komorka in wiersz))
        if block.rows:
            self.console.print(tabela)
        elif block.title:
            self.console.print(safe(block.title), style=STYL_TYTULU, soft_wrap=True)
        for uwaga in block.notes:
            self.console.print(safe(uwaga), soft_wrap=True)

    def message(self, text: str) -> None:
        self.console.print(safe(text), soft_wrap=True)

    def warning(self, text: str) -> None:
        self.console.print(safe(text), style=STYL_UWAGI, soft_wrap=True)

    def error(self, text: str) -> None:
        self.bledy.print(safe(text), style=STYL_BLEDU, soft_wrap=True)
