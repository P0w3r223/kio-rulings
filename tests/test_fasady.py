"""Strażnik fasad pakietów `store/` i `pipeline/` (ADR-0009 Z-3, Z-6; 2026-09-22).

Rozbicie dwóch modułów na pakiety wprowadziło klasę cichej awarii, której wcześniej nie było:
`monkeypatch.setattr(pipeline, "PROG_ZGODY", 3)` działał, dopóki `pipeline` był jednym plikiem,
a po rozbiciu zmienia wyłącznie przestrzeń nazw fasady — kod czyta stałą z globali `zgoda.py`,
więc podstawienie przechodzi bez skutku i bez słowa. Ten plik pilnuje trzech rzeczy:

1. powierzchnia fasad jest dokładnie dawną powierzchnią modułów (ograniczenie właściciela
   „`__init__.py` zachowuje API" w postaci mechanicznej);
2. szwy podstawiane w testach (`build_http_client`, `default_output_dir`) **nie** są atrybutami
   fasady — to przypina mechanizm, który czyni stare podstawienie głośnym (`AttributeError`);
3. żaden test nie podstawia nazwy w jednym module pakietu, gdy ten sam obiekt trzyma też inny —
   moduł definicji nie zawsze jest modułem, który czyta (`SCHEMA_VERSION`: `schemat` → `magazyn`).

Osobny plik, nie `test_boundaries.py`: tamten obiecuje nie importować modułów produkcyjnych.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path
from types import ModuleType

import pytest

from kio_tool import pipeline, store

TESTY = Path(__file__).resolve().parent
FASADY = {"kio_tool.store": store, "kio_tool.pipeline": pipeline}

POWIERZCHNIA_STORE = frozenset(
    {
        "SCHEMA_VERSION",
        "ID_BAZY_POKAZOWEJ",
        "STATUSY_PRZEBIEGU",
        "STATUSY_WZNAWIALNE",
        "TABELE",
        "DOMYSLNY_BUSY_TIMEOUT_S",
        "DOMYSLNY_LIMIT_TRAFIEN",
        "KOLUMNA_FTS_TRESCI",
        "Przebieg",
        "Metryka",
        "WierszSekcji",
        "WierszCytowania",
        "WierszPrzepisu",
        "Struktura",
        "StrukturaDokumentu",
        "Filtr",
        "Dokument",
        "Trafienie",
        "Wyszukanie",
        "Store",
        "blad_bazy",
    }
)
"""Każda publiczna nazwa dawnego `store.py` (odczyt 2026-09-22, `master` `c1ed572`)."""

POWIERZCHNIA_PIPELINE = frozenset(
    {
        "KANAL_DOMYSLNY",
        "PROG_ZGODY",
        "STATUS_PRZERWANY",
        "FORMATY_DOMYSLNE",
        "PROG_404_POD_RZAD",
        "KlientFactory",
        "Werdykt",
        "Decyzja",
        "decyzja_z_flagi",
        "ODMOWA_PO_WYCENIE",
        "Podsumowanie",
        "WynikEksportu",
        "WynikPrzeliczenia",
        "Wycena",
        "kanaly",
        "zakres_z_kryteriow",
        "pobierz",
        "do_wznowienia",
        "wznow",
        "eksportuj",
        "build_metadata",
        "przelicz",
        "szukaj",
        "czytaj",
        "Orzeczenie",
        "ODCINEK_BEZ_SEKCJI",
    }
)
"""Każda publiczna nazwa dawnego `pipeline.py` plus `Wycena`, czytana jako `pipeline.Wycena`,
plus `czytaj` z `Orzeczenie` i `ODCINEK_BEZ_SEKCJI` (2026-09-22)."""

SZWY_PODSTAWIANE = ("build_http_client", "default_output_dir")


@pytest.mark.parametrize(
    ("fasada", "powierzchnia"),
    [(store, POWIERZCHNIA_STORE), (pipeline, POWIERZCHNIA_PIPELINE)],
    ids=["store", "pipeline"],
)
def test_powierzchnia_fasady_jest_dawna_powierzchnia_modulu(
    fasada: object, powierzchnia: frozenset[str]
) -> None:
    wystawione = frozenset(getattr(fasada, "__all__", ()))

    assert wystawione == powierzchnia, (
        f"zmieniona powierzchnia: nowe {sorted(wystawione - powierzchnia)}, "
        f"zniknęły {sorted(powierzchnia - wystawione)} — to jest świadoma zmiana inwentarza"
    )
    assert [n for n in wystawione if not hasattr(fasada, n)] == []


@pytest.mark.parametrize("szew", SZWY_PODSTAWIANE)
def test_szew_podstawiany_w_testach_nie_mieszka_w_fasadzie(szew: str) -> None:
    """Fasada z tą nazwą zamieniłaby podstawienie w testach w podstawienie bez skutku."""
    for nazwa, fasada in FASADY.items():
        assert not hasattr(fasada, szew), f"{nazwa}.{szew} — szew nie ma prawa mieszkać w fasadzie"


def _moduly_pakietu(pakiet: str) -> dict[str, ModuleType]:
    korzen = FASADY[pakiet]
    moduly: dict[str, ModuleType] = {pakiet: korzen}
    for info in pkgutil.walk_packages(korzen.__path__, prefix=f"{pakiet}."):
        moduly[info.name] = importlib.import_module(info.name)
    return moduly


MODULY = {nazwa: modul for pakiet in FASADY for nazwa, modul in _moduly_pakietu(pakiet).items()}
"""Fasady i wszystkie ich podmoduły — tylko w nich podstawienie może trafić obok czytelnika."""


def trzymajacy(modul: str, atrybut: str) -> list[str]:
    """Moduły tego samego pakietu, które trzymają **ten sam obiekt** pod tą nazwą.

    Podstawienie w jednym z nich zostawia pozostałe przy starym obiekcie — a czytać może właśnie
    któryś z pozostałych. Tożsamość, nie składnia: tak samo rozpoznaje miejsca piaskownica
    domyślnych ścieżek (`wsparcie_sondy.przekieruj_domyslne_sciezki`).
    """
    obiekt = getattr(MODULY[modul], atrybut)
    pakiet = next(f for f in FASADY if modul == f or modul.startswith(f"{f}."))
    return sorted(
        nazwa
        for nazwa, m in MODULY.items()
        if (nazwa == pakiet or nazwa.startswith(f"{pakiet}."))
        and getattr(m, atrybut, None) is obiekt
    )


def _zwiazane(drzewo: ast.Module) -> dict[str, str]:
    """Nazwy w pliku związane importem z modułem fasady albo jej podmodułem."""
    zwiazane: dict[str, str] = {}
    for wezel in ast.walk(drzewo):
        if isinstance(wezel, ast.ImportFrom) and wezel.level == 0 and wezel.module:
            for alias in wezel.names:
                pelna = f"{wezel.module}.{alias.name}"
                if pelna in MODULY:
                    zwiazane[alias.asname or alias.name] = pelna
        elif isinstance(wezel, ast.Import):
            for alias in wezel.names:
                if alias.name in MODULY and alias.asname:
                    zwiazane[alias.asname] = alias.name
    return zwiazane


def _cel(wezel: ast.Call, zwiazane: dict[str, str]) -> tuple[str, str] | None:
    """(moduł, atrybut) podstawienia albo `None`, gdy cel nie jest modułem fasady."""
    pierwszy = wezel.args[0]
    drugi = wezel.args[1] if len(wezel.args) > 1 else None
    atrybut = (
        drugi.value if isinstance(drugi, ast.Constant) and isinstance(drugi.value, str) else None
    )
    if isinstance(pierwszy, ast.Name) and pierwszy.id in zwiazane and atrybut:
        return zwiazane[pierwszy.id], atrybut
    if isinstance(pierwszy, ast.Attribute) and ast.unparse(pierwszy) in MODULY and atrybut:
        return ast.unparse(pierwszy), atrybut
    if isinstance(pierwszy, ast.Constant) and isinstance(pierwszy.value, str):
        modul, _, reszta = pierwszy.value.rpartition(".")
        if modul in MODULY:
            return modul, reszta
    return None


def podstawienia_bez_skutku(zrodlo: str) -> list[str]:
    """`setattr`/`patch` na module fasady lub podmodule, gdy ten sam obiekt trzyma też inny moduł
    pakietu — podstawienie trafia w jedno miejsce, a czytać może drugie. Atrybut nieistniejący
    pomijamy: `monkeypatch.setattr` i `mock.patch` rzucają wtedy głośno."""
    drzewo = ast.parse(zrodlo)
    zwiazane = _zwiazane(drzewo)
    naruszenia: list[str] = []
    for wezel in ast.walk(drzewo):
        if not (isinstance(wezel, ast.Call) and isinstance(wezel.func, ast.Attribute)):
            continue
        if wezel.func.attr not in {"setattr", "patch", "object"} or not wezel.args:
            continue
        cel = _cel(wezel, zwiazane)
        if cel is None or not hasattr(MODULY[cel[0]], cel[1]):
            continue
        if isinstance(getattr(MODULY[cel[0]], cel[1]), ModuleType):
            continue
        if len(miejsca := trzymajacy(*cel)) > 1:
            naruszenia.append(f"{cel[0]}.{cel[1]} (linia {wezel.lineno}; trzymają: {miejsca})")
    return naruszenia


def test_zaden_test_nie_podstawia_w_jednym_z_wielu_miejsc() -> None:
    znalezione = {
        plik.name: naruszenia
        for plik in sorted(TESTY.rglob("*.py"))
        if plik.name != Path(__file__).name
        and (naruszenia := podstawienia_bez_skutku(plik.read_text(encoding="utf-8")))
    }

    assert znalezione == {}, (
        f"podstawienia, które mogą nie trafić w czytelnika: {znalezione} — podstaw we wszystkich "
        "miejscach naraz przez `wsparcie_sondy.podstaw_w_pakiecie`"
    )


@pytest.mark.parametrize(
    ("zrodlo", "oczekiwane"),
    [
        ('from kio_tool import pipeline\nm.setattr(pipeline, "PROG_ZGODY", 3)\n', 1),
        ('from kio_tool import store as s\nm.setattr(s, "TABELE", ())\n', 1),
        ('import kio_tool.pipeline\nm.setattr(kio_tool.pipeline, "PROG_ZGODY", 3)\n', 1),
        ('m.setattr("kio_tool.pipeline.PROG_ZGODY", 3)\n', 1),
        ('mock.patch("kio_tool.store.SCHEMA_VERSION", 9)\n', 1),
        ('m.setattr("kio_tool.store.schemat.SCHEMA_VERSION", 99)\n', 1),
        ('m.setattr("kio_tool.pipeline.zgoda.PROG_ZGODY", 3)\n', 1),
        ('from kio_tool import pipeline\nm.setattr(pipeline, "zgoda", z)\n', 0),
        ('from kio_tool.pipeline import lokalne\nm.setattr(lokalne, "default_output_dir", f)\n', 0),
        ('from kio_tool import pipeline\nm.setattr(pipeline, "build_http_client", f)\n', 0),
        ('m.setattr(store, "add_raw_version", f)\n', 0),
    ],
    ids=[
        "stala-na-fasadzie",
        "alias-fasady",
        "import-bez-aliasu",
        "cel-napisowy",
        "mock-patch",
        "definicja-nie-czytelnik",
        "podmodul-i-fasada",
        "podmodul-jako-atrybut",
        "jedyne-miejsce",
        "brak-atrybutu-glosno",
        "instancja-nie-modul",
    ],
)
def test_samosprawdzenie_skanu_podstawien(zrodlo: str, oczekiwane: int) -> None:
    """Skan, który niczego nie znajduje, wygląda tak samo jak skan, który nie działa."""
    assert len(podstawienia_bez_skutku(zrodlo)) == oczekiwane
