"""Strażnik fasad pakietów `store/` i `pipeline/` (ADR-0009 Z-3, Z-6; 2026-09-22).

Rozbicie dwóch modułów na pakiety wprowadziło klasę cichej awarii, której wcześniej nie było:
`monkeypatch.setattr(pipeline, "PROG_ZGODY", 3)` działał, dopóki `pipeline` był jednym plikiem,
a po rozbiciu zmienia wyłącznie przestrzeń nazw fasady — kod czyta stałą z globali `zgoda.py`,
więc podstawienie przechodzi bez skutku i bez słowa. Ten plik pilnuje trzech rzeczy:

1. powierzchnia fasad jest dokładnie dawną powierzchnią modułów (ograniczenie właściciela
   „`__init__.py` zachowuje API" w postaci mechanicznej);
2. szwy podstawiane w testach (`build_http_client`, `default_output_dir`) **nie** są atrybutami
   fasady — to przypina mechanizm, który czyni stare podstawienie głośnym (`AttributeError`);
3. żaden test nie podstawia na fasadzie atrybutu, który nie jest podmodułem.

Osobny plik, nie `test_boundaries.py`: tamten obiecuje nie importować modułów produkcyjnych.
"""

from __future__ import annotations

import ast
from pathlib import Path

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
    }
)
"""Każda publiczna nazwa dawnego `pipeline.py` plus `Wycena`, czytana jako `pipeline.Wycena`."""

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
        assert not hasattr(fasada, szew), f"{nazwa}.{szew} — szew musi mieszkać w module definicji"


def _nazwy_fasad(drzewo: ast.Module) -> dict[str, str]:
    """Nazwy w pliku związane z fasadą przez import: `from kio_tool import pipeline` itd."""
    zwiazane: dict[str, str] = {}
    for wezel in ast.walk(drzewo):
        if isinstance(wezel, ast.ImportFrom) and wezel.module == "kio_tool" and wezel.level == 0:
            for alias in wezel.names:
                pelna = f"kio_tool.{alias.name}"
                if pelna in FASADY:
                    zwiazane[alias.asname or alias.name] = pelna
        elif isinstance(wezel, ast.Import):
            for alias in wezel.names:
                if alias.name in FASADY and alias.asname:
                    zwiazane[alias.asname] = alias.name
    return zwiazane


def _podmoduly(pelna: str) -> frozenset[str]:
    katalog = Path(FASADY[pelna].__file__ or "").parent
    return frozenset(p.stem for p in katalog.glob("*.py") if p.stem != "__init__")


def podstawienia_na_fasadzie(zrodlo: str) -> list[str]:
    """`monkeypatch.setattr(<fasada>, "<atrybut>", …)` i cel napisowy `"kio_tool.<fasada>.<atr>"`
    w `setattr`/`patch`, gdzie atrybut nie jest podmodułem — każde to podstawienie bez skutku."""
    drzewo = ast.parse(zrodlo)
    zwiazane = _nazwy_fasad(drzewo)
    naruszenia: list[str] = []
    for wezel in ast.walk(drzewo):
        if not (isinstance(wezel, ast.Call) and isinstance(wezel.func, ast.Attribute)):
            continue
        if wezel.func.attr not in {"setattr", "patch", "object"} or not wezel.args:
            continue
        pierwszy = wezel.args[0]
        if (
            isinstance(pierwszy, ast.Name)
            and pierwszy.id in zwiazane
            and len(wezel.args) > 1
            and isinstance(wezel.args[1], ast.Constant)
            and isinstance(wezel.args[1].value, str)
        ):
            pelna = zwiazane[pierwszy.id]
            if wezel.args[1].value not in _podmoduly(pelna):
                naruszenia.append(f"{pelna}.{wezel.args[1].value} (linia {wezel.lineno})")
        elif isinstance(pierwszy, ast.Constant) and isinstance(pierwszy.value, str):
            for pelna in FASADY:
                reszta = pierwszy.value.removeprefix(f"{pelna}.")
                if reszta != pierwszy.value and reszta.split(".")[0] not in _podmoduly(pelna):
                    naruszenia.append(f"{pierwszy.value} (linia {wezel.lineno})")
    return naruszenia


def test_zaden_test_nie_podstawia_na_fasadzie() -> None:
    znalezione = {
        plik.name: naruszenia
        for plik in sorted(TESTY.rglob("*.py"))
        if plik.name != Path(__file__).name
        and (naruszenia := podstawienia_na_fasadzie(plik.read_text(encoding="utf-8")))
    }

    assert znalezione == {}, (
        f"podstawienia bez skutku na fasadzie: {znalezione} — podstaw w module definicji "
        "(np. `kio_tool.pipeline.zgoda`) albo przez pomocnika z `wsparcie_sondy`"
    )


@pytest.mark.parametrize(
    ("zrodlo", "oczekiwane"),
    [
        ('from kio_tool import pipeline\nm.setattr(pipeline, "PROG_ZGODY", 3)\n', 1),
        ('from kio_tool import pipeline as p\nm.setattr(p, "build_http_client", f)\n', 1),
        ('from kio_tool import store\nm.setattr(store, "TABELE", ())\n', 1),
        ('m.setattr("kio_tool.pipeline.PROG_ZGODY", 3)\n', 1),
        ('mock.patch("kio_tool.store.SCHEMA_VERSION", 9)\n', 1),
        ('from kio_tool import pipeline\nm.setattr(pipeline, "zgoda", z)\n', 0),
        ('m.setattr("kio_tool.pipeline.zgoda.PROG_ZGODY", 3)\n', 0),
        ('m.setattr(store, "add_raw_version", f)\n', 0),
    ],
    ids=[
        "stala-na-fasadzie",
        "alias-fasady",
        "store",
        "cel-napisowy",
        "mock-patch",
        "podmodul",
        "cel-w-podmodule",
        "instancja-nie-modul",
    ],
)
def test_samosprawdzenie_skanu_podstawien(zrodlo: str, oczekiwane: int) -> None:
    """Skan, który niczego nie znajduje, wygląda tak samo jak skan, który nie działa."""
    assert len(podstawienia_na_fasadzie(zrodlo)) == oczekiwane
