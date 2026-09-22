"""Instrukcja dla modelu zgodna z narzędziem — strażnik zasady z `CLAUDE.md` (2026-09-22).

„`docs/dla-modelu.md` zmienia się razem z każdą flagą i poleceniem. Instrukcja rozjechana
z narzędziem jest gorsza niż jej brak.” Do dziś pilnowała tego tylko dyscyplina. Tu drzewo
poleceń `typer` (to samo, z którego powstają `--help` i `opis --json`) jest porównywane z ręczną
instrukcją w obie strony: flaga narzędzia bez słowa w instrukcji i flaga instrukcji, której
narzędzie nie zna, zapalają test. Skill Claude Code i README podlegają drugiej połowie.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import typer.main
from typer.core import TyperGroup
from typer.testing import CliRunner

from kio_tool import cli, errors
from kio_tool.cli import POLECENIA_DLA_CZLOWIEKA, POLECENIA_SIECIOWE, app
from kio_tool.ui.texts_pomoc import KODY_WYJSCIA

ROOT = Path(__file__).resolve().parent.parent
INSTRUKCJA = ROOT / "docs" / "dla-modelu.md"
SKILL = ROOT / ".claude" / "skills" / "kio-tool" / "SKILL.md"
README = ROOT / "README.md"
FLAGI_OBCE_README = frozenset({"--check"})
"""Flagi innych narzędzi w README (`ruff format --check`) — nie należą do `kio-tool`."""
KOD_BLEDU_SKLADNI = 2
"""Kod, którym `typer` kończy literówkę we fladze — nie pochodzi z `errors.py`."""

WZOR_FLAGI = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
runner = CliRunner()


def _grupa() -> TyperGroup:
    grupa = typer.main.get_command(app)
    assert isinstance(grupa, TyperGroup)
    return grupa


def _flagi_polecenia(nazwa: str) -> set[str]:
    return {o for p in _grupa().commands[nazwa].params for o in p.opts if o.startswith("--")}


def _wszystkie_flagi() -> set[str]:
    return {f for nazwa in _grupa().commands for f in _flagi_polecenia(nazwa)} | {"--help"}


def flagi_w_tekscie(tekst: str) -> set[str]:
    return set(WZOR_FLAGI.findall(tekst))


def brakujace(tekst: str, flagi: set[str]) -> set[str]:
    """Flagi narzędzia, o których tekst milczy."""
    return flagi - flagi_w_tekscie(tekst)


def nieznane(tekst: str, znane: set[str]) -> set[str]:
    """Flagi z tekstu, których narzędzie nie zna — literówka albo flaga usunięta z kodu."""
    return flagi_w_tekscie(tekst) - znane


def _polecenia_dla_modelu() -> list[str]:
    return sorted(set(_grupa().commands) - POLECENIA_DLA_CZLOWIEKA)


@pytest.mark.parametrize("polecenie", _polecenia_dla_modelu())
def test_kazde_polecenie_dla_modelu_jest_w_instrukcji(polecenie: str) -> None:
    assert re.search(rf"`{polecenie}\b", INSTRUKCJA.read_text(encoding="utf-8")), polecenie


@pytest.mark.parametrize("polecenie", _polecenia_dla_modelu())
def test_kazda_flaga_polecenia_jest_w_instrukcji(polecenie: str) -> None:
    tekst = INSTRUKCJA.read_text(encoding="utf-8")

    assert brakujace(tekst, _flagi_polecenia(polecenie)) == set(), polecenie


@pytest.mark.parametrize(
    ("plik", "obce"),
    [(INSTRUKCJA, frozenset()), (SKILL, frozenset()), (README, FLAGI_OBCE_README)],
    ids=["dla-modelu", "skill", "readme"],
)
def test_kazda_flaga_z_dokumentu_istnieje_w_narzedziu(plik: Path, obce: frozenset[str]) -> None:
    assert nieznane(plik.read_text(encoding="utf-8"), _wszystkie_flagi() | obce) == set()


def test_samosprawdzenie_skanu_widzi_brak_i_nadmiar() -> None:
    """Skan, który niczego nie widzi, przechodziłby zawsze — mutacja na tekście syntetycznym."""
    tekst = "Użyj `--fraza` oraz --limit-x; e-mail--to nie flaga, a `--json` tak."

    assert flagi_w_tekscie(tekst) == {"--fraza", "--limit-x", "--json"}
    assert brakujace(tekst, {"--fraza", "--limit"}) == {"--limit"}
    assert nieznane(tekst, {"--fraza", "--json"}) == {"--limit-x"}


def test_kody_wyjscia_z_errors_sa_w_opisie_i_w_instrukcji() -> None:
    znaczenia = dict(KODY_WYJSCIA)
    z_klas = {
        klasa.exit_code
        for klasa in vars(errors).values()
        if isinstance(klasa, type) and issubclass(klasa, errors.KioError)
    }
    uzywane = {0, KOD_BLEDU_SKLADNI, errors.KOD_WYJSCIA_PRZERWANIE, *z_klas}
    tekst = INSTRUKCJA.read_text(encoding="utf-8")

    assert uzywane == set(znaczenia)
    for kod in znaczenia:
        assert f"| {kod} |" in tekst, kod


def test_polecenia_sieciowe_to_dokladnie_te_ktore_przedstawiaja_sie_serwisowi() -> None:
    """`opis` mówi „sieć: tak” z listy wpisanej ręką; lista ma odpowiadać kodowi — polecenie
    bez `user_agent()` nie wyśle żądania (reguła 16), a z nim — może."""
    drzewo = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    sieciowe = set()
    for funkcja in drzewo.body:
        if not isinstance(funkcja, ast.FunctionDef):
            continue
        polecenie = any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == "command"
            for d in funkcja.decorator_list
        )
        wola_user_agent = any(
            isinstance(w, ast.Call) and isinstance(w.func, ast.Name) and w.func.id == "user_agent"
            for w in ast.walk(funkcja)
        )
        if polecenie and wola_user_agent:
            sieciowe.add(funkcja.name)

    assert sieciowe == POLECENIA_SIECIOWE


def test_opis_json_obejmuje_kazde_polecenie_i_kazdy_parametr() -> None:
    wynik = runner.invoke(app, ["opis", "--json"])

    assert wynik.exit_code == 0, wynik.output
    bloki = {d["tytul"]: d for d in map(json.loads, wynik.stdout.splitlines())}
    polecenia = [w["polecenie"] for w in bloki["Polecenia"]["wiersze"]]
    assert polecenia == sorted(_grupa().commands)
    flagi = {(w["polecenie"], w["flaga"]) for w in bloki["Flagi"]["wiersze"]}
    assert len(flagi) == sum(len(c.params) for c in _grupa().commands.values())
    siec = {w["polecenie"] for w in bloki["Polecenia"]["wiersze"] if w["siec"] == "tak"}
    assert siec == POLECENIA_SIECIOWE
    kody = [int(w["kod"]) for w in bloki["Kody wyjścia"]["wiersze"]]
    assert kody == [kod for kod, _ in KODY_WYJSCIA]


def test_skill_ma_naglowek_i_wskazuje_istniejaca_instrukcje() -> None:
    tekst = SKILL.read_text(encoding="utf-8")
    naglowek = tekst.split("---")[1]

    assert "name: kio-tool" in naglowek and "description:" in naglowek
    assert "docs/dla-modelu.md" in tekst and INSTRUKCJA.is_file()
    assert "opis --json" in tekst
