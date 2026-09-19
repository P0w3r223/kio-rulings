"""Korpus pokazowy trzymany pomiarem (ADR-0008 Z-12) — bramka fazy 3, §10 pkt 3.

Korpus, którego cech nikt nie mierzy, dryfuje i uczy czegoś, czego źródło nie robi (ADR-0014
`ceidg-tool`). Każda cecha z `tests/fixtures/cechy_atlasu.yaml` ma wartość zmierzoną na korpusie
operatora, tolerancję i źródło; test liczy tę samą cechę na korpusie pokazowym. Filtry atrapy mają
wpis ze statusem — `niezmierzone` jest dopuszczalne, brak wpisu nie.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from kio_tool.demo import wczytaj_wzorce
from kio_tool.demo.korpus import DokumentPokazowy, generuj
from kio_tool.docid import SourceName
from kio_tool.parser.sections import segmentuj
from kio_tool.source.contract import load_contract

CECHY = yaml.safe_load(
    (Path(__file__).resolve().parent / "fixtures" / "cechy_atlasu.yaml").read_text(encoding="utf-8")
)
KORPUS = generuj(wczytaj_wzorce())

POMIARY: dict[str, Callable[[DokumentPokazowy], bool]] = {
    "wysuw_strony": lambda d: "\f" in d.tresc,
    "lamanie_w_zdaniu": lambda d: (
        re.search(r"[a-ząćęłńóśźż,]\n[a-ząćęłńóśźż]", d.tresc) is not None
    ),
    "naglowek_rozstrzelony": lambda d: "Uz as adnienie" in d.tresc,
    "kotwica_sentencji": lambda d: re.search(r"(orzeka|postanawia):", d.tresc) is not None,
    "pouczenie": lambda d: "przysługuje skarga" in d.tresc,
    "wiele_sygnatur": lambda d: len(d.sygnatury) > 1,
    "cytowania": lambda d: bool(d.cytowane),
    "przepisy_puste": lambda d: not d.przepisy,
}


@pytest.mark.parametrize("cecha", sorted(CECHY["cechy"]))
def test_cecha_korpusu_pokazowego_w_tolerancji_pomiaru(cecha: str) -> None:
    wzor = CECHY["cechy"][cecha]
    udzial = sum(POMIARY[cecha](d) for d in KORPUS) / len(KORPUS)
    assert abs(udzial - wzor["udzial"]) <= wzor["tolerancja"], (
        f"{cecha}: pokaz {udzial:.3f}, zmierzone {wzor['udzial']} ± {wzor['tolerancja']} "
        f"({wzor['zrodlo']})"
    )


def test_kazda_cecha_z_pliku_ma_pomiar_i_odwrotnie() -> None:
    """Cecha bez pomiaru przechodziłaby pusto; pomiar bez cechy — nie miałby wzorca."""
    assert set(CECHY["cechy"]) == set(POMIARY)
    for wzor in CECHY["cechy"].values():
        assert {"udzial", "tolerancja", "zrodlo", "data"} <= set(wzor)


def test_kazdy_filtr_kontraktu_ma_wpis_ze_statusem() -> None:
    kontrakt = load_contract(SourceName("atlas"))
    filtry = CECHY["filtry_atrapy"]
    assert set(filtry) == set(kontrakt.parametry_listy.filtry)
    assert {f["status"] for f in filtry.values()} <= {"zmierzone", "niezmierzone"}


def test_parser_fazy_2_widzi_w_pokazie_komplet_sekcji() -> None:
    """Raport pokrycia na bazie pokazowej nie ma być pusty w żadnej kategorii sekcji."""
    rodzaje = [{s.rodzaj for s in segmentuj(d.tresc)} for d in KORPUS]
    komplet = {"naglowek", "sentencja", "pouczenie", "uzasadnienie"}
    assert sum(komplet <= r for r in rodzaje) == len(KORPUS)
