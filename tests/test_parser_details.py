"""`parser/details.py` na złotym dokumencie pomiaru 3a — oczekiwania z `*.compare.json`, nie
z pamięci.

Reguła 19 ma tu postać strukturalną: `Szczegoly` nie ma pola, którym mogłoby pójść `thesis`
ani inne pole opracowania Atlasu. Nazwy pól przychodzą z kontraktu (`MapaPol`), więc test buduje
mapę dokładnie tak, jak robi to `pipeline`.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from kio_tool.docid import SourceName
from kio_tool.errors import ParseError
from kio_tool.parser.details import PARSE_VERSION, MapaPol, Szczegoly, rekord_z_bajtow, wyczytaj
from kio_tool.pipeline import mapa_pol
from kio_tool.source.contract import load_contract

ZLOTE = Path(__file__).resolve().parent / "examples" / "atlas"
DOKUMENT_BAJTY = (ZLOTE / "dokument_20260918T103526Z.json").read_bytes()
DOKUMENT_PORA = json.loads((ZLOTE / "dokument_20260918T103526Z.compare.json").read_text("utf-8"))
KONTRAKT = load_contract(SourceName("atlas"))
MAPA = mapa_pol(KONTRAKT)


def test_mapa_pol_pokrywa_kazde_pole_z_kontraktu_i_nic_poza_tym() -> None:
    nazwy_mapy = {f.name for f in fields(MapaPol)}
    z_kontraktu = set(KONTRAKT.ksztalt.dokument.pola_metadanych.model_dump()) | {"tresc"}

    assert nazwy_mapy == z_kontraktu
    assert MAPA.tresc == KONTRAKT.ksztalt.dokument.pole_tresci


def test_zloty_dokument_daje_szczegoly_zgodne_z_przejrzana_para() -> None:
    s = wyczytaj(rekord_z_bajtow(DOKUMENT_BAJTY), MAPA)

    assert s.sygnatura_glowna == DOKUMENT_PORA["primary_signature"]
    assert s.sygnatury == tuple(DOKUMENT_PORA["signatures"])
    assert s.data_wydania == DOKUMENT_PORA["ruling_date"]
    assert s.data_rozprawy == DOKUMENT_PORA["hearing_date"]
    assert s.rodzaj == DOKUMENT_PORA["ruling_kind"]
    assert s.url_zrodla == DOKUMENT_PORA["source_url"]
    assert s.dlugosc_tresci == DOKUMENT_PORA["dlugosc_full_text"]
    assert s.tresc.startswith(DOKUMENT_PORA["poczatek_full_text"])
    assert s.rozstrzygniecie == "umorzono" and s.rozstrzygniecie_surowe is not None
    assert len(s.przepisy) == 2 and s.koszty is None


def test_szczegoly_nie_maja_miejsca_na_pola_odrzucone_ani_opracowanie_atlasu() -> None:
    """Reguła 19 (ADR-0005 Z-5) jako własność struktury, nie pamięci."""
    nazwy = {f.name for f in fields(Szczegoly)}
    odrzucone = {wpis.pole for wpis in KONTRAKT.pola_odrzucone}
    opracowanie = {"related_by_entity", "similar_rulings", "cited_by", "cites", "related_tenders"}

    assert not any(nazwa.startswith("thesis") for nazwa in nazwy)
    assert nazwy.isdisjoint(odrzucone | opracowanie)


def test_brak_pola_daje_none_albo_pustke_nigdy_wartosc_zastepcza() -> None:
    s = wyczytaj({"slug": "wymyslony"}, MAPA)

    assert s.sygnatura_glowna is None and s.sygnatury == ()
    assert s.data_wydania is None and s.koszty is None and s.przepisy == ()
    assert s.tresc == "" and s.dlugosc_tresci == 0


def test_sygnatura_glowna_wypelnia_puste_signatures() -> None:
    s = wyczytaj({MAPA.sygnatura_glowna: "(napis wymyslony)"}, MAPA)

    assert s.sygnatury == ("(napis wymyslony)",)


@pytest.mark.parametrize(
    ("wartosc", "oczekiwane"),
    [(15000, 15000.0), (7.5, 7.5), (None, None), (True, None), ("15000", None)],
    ids=["int", "float", "null", "bool_nie_jest_liczba", "napis_nie_jest_liczba"],
)
def test_koszty_przyjmuja_liczbe_i_odrzucaja_reszte(
    wartosc: object, oczekiwane: float | None
) -> None:
    assert wyczytaj({MAPA.koszty: wartosc}, MAPA).koszty == oczekiwane


def test_liczba_w_polu_tekstowym_nie_staje_sie_napisem() -> None:
    """`document_id: 13053` w kolumnie sygnatury wyglądałoby na sygnaturę (zasada 7.1)."""
    assert wyczytaj({MAPA.sygnatura_glowna: 13053}, MAPA).sygnatura_glowna is None


@pytest.mark.parametrize(
    "bajty", [b"[1, 2]", b"nie json", b"\xff\xfe"], ids=["lista", "tekst", "bajty"]
)
def test_wersja_ktora_nie_jest_slownikiem_json_rzuca_parse_error(bajty: bytes) -> None:
    with pytest.raises(ParseError):
        rekord_z_bajtow(bajty)


def test_parse_version_jest_dodatnia_liczba() -> None:
    assert isinstance(PARSE_VERSION, int) and PARSE_VERSION >= 1
