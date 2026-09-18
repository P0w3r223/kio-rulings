"""Pierwszy kontakt z narzędziem: czy `--help` wystarczy, żeby użyć go bez czytania kodu.

Ten plik patrzy na wiersz poleceń oczami osoby, która nie zna ani tego projektu, ani jego
dokumentów: uruchamia program bez argumentów, czyta pomoc, myli nazwę polecenia i literuje flagę.
Sprawdzane jest to, czego taka osoba potrzebuje mechanicznie: **każda** flaga polecenia stoi w jego
pomocy ze zdaniem z `ui/texts.py` (reguła 9), postać daty jest w pomocy, a nie do odgadnięcia,
lista wartości zamkniętych (formaty, statusy) jest wypisana, a pomyłka w nazwie polecenia kończy
się kodem niezerowym.

Ten plik nie powtarza asercji z `test_cli.py` (tam: `--baza` w pomocy każdego polecenia i mapa
poleceń). Fixture konsoli jest tu własna, bo `tests/conftest.py` zostaje nietknięty — dwa zespoły
pracują w tym samym drzewie.
"""

from __future__ import annotations

import pytest
import typer.main
from typer import rich_utils
from typer.testing import CliRunner

from kio_tool.cli import app
from kio_tool.exporter import FORMATY
from kio_tool.store import STATUSY_PRZEBIEGU
from kio_tool.ui import texts

POLECENIA = ("pobierz", "wznow", "eksportuj", "runy", "przelicz", "szukaj")
POMOC_POLECEN = {
    "pobierz": texts.POMOC_POBIERZ,
    "wznow": texts.POMOC_WZNOW,
    "eksportuj": texts.POMOC_EKSPORTUJ,
    "runy": texts.POMOC_RUNY,
    "przelicz": texts.POMOC_PRZELICZ,
    "szukaj": texts.POMOC_SZUKAJ,
}
ZDANIA_POMOCY = frozenset(
    wartosc
    for nazwa, wartosc in vars(texts).items()
    if nazwa.startswith("POMOC_") and isinstance(wartosc, str)
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def _konsola_powtarzalna(monkeypatch: pytest.MonkeyPatch) -> None:
    """Szerokość przypięta i kolor wyłączony — inaczej asercja o treści mierzy przy okazji
    szerokość maszyny, a `rich` rozbija nazwę flagi sekwencjami ANSI (powód w `test_cli.py`)."""
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setattr(rich_utils, "MAX_WIDTH", 200)


def flagi(polecenie: str) -> dict[str, str | None]:
    """Flaga → jej zdanie pomocy, wprost z drzewa poleceń `click`, nie z ekranu."""
    komenda = typer.main.get_command(app).commands[polecenie]  # type: ignore[attr-defined]
    return {
        parametr.opts[0]: parametr.help
        for parametr in komenda.params
        if parametr.name != "help" and parametr.opts
    }


# --- pierwsze uruchomienie ----------------------------------------------------------------------


def test_bez_argumentow_program_pokazuje_pomoc_zamiast_milczec() -> None:
    """Osoba, która nie wie nic, uruchamia samą nazwę. `no_args_is_help=True` w `cli.py` jest
    tym, co odróżnia narzędzie od programu, który kończy się bez słowa."""
    wynik = runner.invoke(app, [])

    assert all(polecenie in wynik.output for polecenie in POLECENIA), wynik.output
    assert texts.POMOC_PROGRAMU.split("—")[0].strip() in wynik.output


@pytest.mark.parametrize("polecenie", POLECENIA)
def test_mapa_polecen_niesie_zdanie_opisujace_kazde_polecenie(polecenie: str) -> None:
    """Wybór polecenia zapada na ekranie `--help` programu, więc tam ma stać zdanie o tym, co
    polecenie robi — a zdanie ma pochodzić z `texts`, nie z docstringa funkcji."""
    wynik = runner.invoke(app, ["--help"])

    poczatek = POMOC_POLECEN[polecenie].split(".")[0][:40]
    assert poczatek in " ".join(wynik.output.split()), wynik.output


# --- pomoc pojedynczego polecenia ---------------------------------------------------------------


@pytest.mark.parametrize("polecenie", POLECENIA)
def test_pomoc_polecenia_wymienia_kazda_jego_flage(polecenie: str) -> None:
    """Flaga, której nie ma w pomocy, jest flagą do znalezienia w kodzie — a kod czyta programista,
    nie operator. Lista brana z drzewa `click`, więc flaga dopisana jutro wchodzi do testu sama."""
    wynik = runner.invoke(app, [polecenie, "--help"])

    assert wynik.exit_code == 0, wynik.output
    brakujace = [flaga for flaga in flagi(polecenie) if flaga not in wynik.output]
    assert not brakujace, f"pomoc `{polecenie}` nie wymienia: {brakujace}"


@pytest.mark.parametrize("polecenie", POLECENIA)
def test_kazda_flaga_ma_zdanie_pomocy_pochodzace_z_texts(polecenie: str) -> None:
    """Reguła 9 od strony operatora: pomoc flagi też jest zdaniem do użytkownika. Flaga bez zdania
    albo ze zdaniem napisanym na miejscu w `cli.py` zapala ten test."""
    bez_zdania = [flaga for flaga, zdanie in flagi(polecenie).items() if not zdanie]
    obce = [
        flaga
        for flaga, zdanie in flagi(polecenie).items()
        if zdanie and zdanie not in ZDANIA_POMOCY
    ]

    assert not bez_zdania, f"flagi bez pomocy w `{polecenie}`: {bez_zdania}"
    assert not obce, f"flagi ze zdaniem spoza `ui/texts.py` w `{polecenie}`: {obce}"


@pytest.mark.parametrize("polecenie", ["pobierz", "eksportuj", "szukaj"])
def test_pomoc_dat_podaje_postac_zamiast_zostawiac_ja_do_zgadniecia(polecenie: str) -> None:
    """`--od 01-01-2024` jest pierwszą pomyłką laika; jedyne, co ją uprzedza, to postać daty
    napisana **przy każdej** z dwóch flag — nie gdziekolwiek na ekranie pomocy."""
    wynik = runner.invoke(app, [polecenie, "--help"])
    zdania = flagi(polecenie)

    bez_postaci = [flaga for flaga in ("--od", "--do") if "RRRR-MM-DD" not in (zdania[flaga] or "")]
    assert not bez_postaci, f"pomoc nie podaje postaci daty przy: {bez_postaci}"
    assert "RRRR-MM-DD" in " ".join(wynik.output.split()), wynik.output


def test_pomoc_formatu_wymienia_kazdy_dostepny_format() -> None:
    """Wartość zamknięta: pomoc ma wypisać wszystkie, inaczej `--format excel` jest jedyną drogą
    do poznania listy — a ta droga kończy się błędem."""
    brakujace = [fmt for fmt in FORMATY if fmt not in texts.POMOC_FORMAT]

    assert not brakujace, f"pomoc `--format` nie wymienia: {brakujace}"


def test_pomoc_statusu_wymienia_kazdy_status_przebiegu() -> None:
    brakujace = [status for status in STATUSY_PRZEBIEGU if status not in texts.POMOC_STATUS]

    assert not brakujace, f"pomoc `--status` nie wymienia: {brakujace}"


def test_pomoc_pobierz_mowi_o_progu_zgody_przed_pierwszym_przebiegiem() -> None:
    """Próg zgody jest jedynym zachowaniem, które zatrzymuje pierwszy prawdziwy przebieg w połowie.
    Operator ma o nim przeczytać w pomocy, a nie dowiedzieć się z komunikatu o przerwaniu."""
    wynik = runner.invoke(app, ["pobierz", "--help"])
    zwarte = " ".join(wynik.output.split())

    assert "--zgoda" in zwarte
    assert texts.POMOC_ZGODA.split("—")[0].strip() in zwarte


# --- pomyłka w nazwie polecenia i flagi ---------------------------------------------------------


def test_literowka_w_nazwie_polecenia_konczy_sie_kodem_niezerowym_i_podpowiedzia() -> None:
    """`pobież` zamiast `pobierz` — pomyłka o jeden znak. Program ma odmówić kodem niezerowym
    i nazwać polecenie, o które chodziło."""
    wynik = runner.invoke(app, ["pobież", "--od", "2024-01-01"])

    assert wynik.exit_code != 0
    assert "pobierz" in wynik.output


def test_literowka_w_nazwie_flagi_konczy_sie_kodem_niezerowym_i_podpowiedzia() -> None:
    wynik = runner.invoke(app, ["runy", "--limitt", "5"])

    assert wynik.exit_code != 0
    assert "--limit" in wynik.output


def test_wartosc_nieliczbowa_w_liczbowej_fladze_konczy_sie_kodem_niezerowym() -> None:
    """`--maks dużo` nie ma prawa wejść w przebieg z liczbą podstawioną po cichu."""
    wynik = runner.invoke(app, ["pobierz", "--maks", "duzo", "--od", "2024-01-01"])

    assert wynik.exit_code != 0
    assert "--maks" in wynik.output
