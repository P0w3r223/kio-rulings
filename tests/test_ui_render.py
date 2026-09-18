"""`ui/render.py`: bloki na ekran przez `rich`, każdy napis przez `richtext.safe` (reguła 10).

Konsola z `record=True` i stałą szerokością — asercje o **treści**, nie o szerokości maszyny.
"""

from __future__ import annotations

from rich.console import Console

from kio_tool.config import register_secret
from kio_tool.ui.render import ConsoleView
from kio_tool.ui.texts import Block
from tests.wsparcie_sondy import KLUCZ_TESTOWY


def widok() -> tuple[ConsoleView, Console, Console]:
    wyjscie = Console(record=True, width=200, markup=False, highlight=False, file=open_null())
    bledy = Console(record=True, width=200, markup=False, highlight=False, file=open_null())
    return ConsoleView(wyjscie, bledy), wyjscie, bledy


def open_null() -> object:
    import io

    return io.StringIO()


def test_blok_z_naglowkami_rysuje_tabele_z_wierszami_i_uwagami() -> None:
    view, wyjscie, _ = widok()

    view.block(
        Block(title="Tytuł", headers=("a", "b"), rows=(("1", "2"),), notes=("uwaga wymyślona",))
    )

    tekst = wyjscie.export_text()
    for fragment in ("Tytuł", "a", "b", "1", "2", "uwaga wymyślona"):
        assert fragment in tekst


def test_blok_bez_naglowkow_rysuje_pary_klucz_wartosc() -> None:
    view, wyjscie, _ = widok()

    view.block(Block(title="", rows=(("klucz", "wartość"),)))

    # `export_text()` czyści bufor nagrania — jeden odczyt, dwie asercje.
    tekst = wyjscie.export_text()
    assert "klucz" in tekst and "wartość" in tekst


def test_blok_bez_wierszy_wypisuje_sam_tytul() -> None:
    view, wyjscie, _ = widok()

    view.block(Block(title="Zero trafień"))

    assert wyjscie.export_text().strip() == "Zero trafień"


def test_message_maskuje_sekret_i_zdejmuje_znaki_sterujace() -> None:
    register_secret(KLUCZ_TESTOWY)
    view, wyjscie, _ = widok()

    view.message(f"klucz {KLUCZ_TESTOWY} \x1b[2J\x07 tekst")

    tekst = wyjscie.export_text()
    assert KLUCZ_TESTOWY not in tekst and "<token>" in tekst
    assert "\x1b" not in tekst and "\x07" not in tekst and "tekst" in tekst


def test_komorka_tabeli_ze_znacznikiem_rich_jest_tekstem_a_nie_stylem() -> None:
    view, wyjscie, _ = widok()

    view.block(Block(title="", headers=("sygnatura",), rows=(("[red]KIO 1/10[/red]",),)))

    assert "[red]KIO 1/10[/red]" in wyjscie.export_text()


def test_error_idzie_na_konsole_bledow_a_message_na_wyjscie() -> None:
    view, wyjscie, bledy = widok()

    view.message("zwykłe")
    view.warning("ostrożnie")
    view.error("źle")

    na_wyjsciu = wyjscie.export_text()
    na_bledach = bledy.export_text()
    assert "zwykłe" in na_wyjsciu and "ostrożnie" in na_wyjsciu and "źle" not in na_wyjsciu
    assert "źle" in na_bledach


def test_dluga_sciezka_nie_jest_zawijana() -> None:
    view, wyjscie, _ = widok()
    sciezka = "C:/" + "katalog/" * 40 + "korpus.sqlite"

    view.message(f"Baza: {sciezka}")

    assert sciezka in wyjscie.export_text()
