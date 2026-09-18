"""`Criteria` — kontrakt wejścia: normalizacja, odcisk, opis po polsku, filtry dla kanału.

Trzy własności z nagłówka `criteria.py`, każda z obserwatorem tutaj: nazwy parametrów serwisu
nie występują w module (skan poniżej czyta źródło), wartości spoza list zmierzonych przechodzą
z ostrzeżeniem zamiast odmowy, a pole listowe z wieloma wartościami nie da się wysłać kanałowi
jako jeden parametr.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from kio_tool import criteria as modul
from kio_tool.criteria import (
    POLA_FILTROW,
    RODZAJE_ZMIERZONE,
    ROZSTRZYGNIECIA_ZMIERZONE,
    Criteria,
    bledy_po_polsku,
)
from kio_tool.docid import SourceName
from kio_tool.source.contract import load_contract

KONTRAKT = load_contract(SourceName("atlas"))


# --- normalizacja -----------------------------------------------------------------------------


def test_rozstrzygniecie_sprowadzane_do_postaci_kanalu_bez_ogonkow_i_bez_powtorzen() -> None:
    k = Criteria(rozstrzygniecie=["Uwzględnione", " oddalono ", "uwzglednione"])

    assert k.rozstrzygniecie == ("oddalono", "uwzglednione")


def test_pojedynczy_napis_w_polu_listowym_jest_jednoelementowa_krotka() -> None:
    assert Criteria(rodzaj="Wyrok").rodzaj == ("wyrok",)
    assert Criteria(rodzaj="").rodzaj == ()


def test_daty_odwrocone_wracaja_po_polsku() -> None:
    with pytest.raises(ValidationError) as blad:
        Criteria(od=date(2024, 2, 1), do=date(2024, 1, 31))

    tekst = bledy_po_polsku(blad.value)
    assert "nie może być późniejsza" in tekst and "Value error" not in tekst


def test_zla_data_wraca_zdaniem_o_postaci_rrrr_mm_dd() -> None:
    with pytest.raises(ValidationError) as blad:
        Criteria.model_validate({"od": "2024-13-01"})

    assert "RRRR-MM-DD" in bledy_po_polsku(blad.value)


def test_nieznane_pole_i_maks_ponizej_jedynki_sa_odrzucane() -> None:
    with pytest.raises(ValidationError) as blad:
        Criteria.model_validate({"pkd": "6201Z"})
    assert "nieznane pole" in bledy_po_polsku(blad.value)

    with pytest.raises(ValidationError) as blad_maks:
        Criteria(maks=0)
    assert "nie mniejsza niż 1" in bledy_po_polsku(blad_maks.value)


def test_fraza_dluzsza_niz_limit_jest_odrzucana() -> None:
    with pytest.raises(ValidationError):
        Criteria(fraza="a" * (modul.MAX_DLUGOSC_TEKSTU + 1))


# --- pytania ----------------------------------------------------------------------------------


def test_is_empty_ignoruje_maks_a_widzi_kazdy_filtr() -> None:
    assert Criteria().is_empty()
    assert Criteria(maks=5).is_empty()
    for pole in POLA_FILTROW:
        wartosc: object = ("oddalono",) if pole in ("rozstrzygniecie", "rodzaj") else "x"
        assert not Criteria.model_validate({pole: wartosc}).is_empty(), pole
    assert not Criteria(od=date(2024, 1, 1)).is_empty()


def test_filtry_kanalu_niosa_nazwy_pol_kryteriow_nie_parametry_serwisu() -> None:
    k = Criteria(fraza="oferta", rozstrzygniecie=("oddalono",), przepis="art. 226", maks=3)

    filtry = k.filtry_kanalu()

    assert filtry == {"fraza": "oferta", "rozstrzygniecie": "oddalono", "przepis": "art. 226"}
    assert set(filtry) <= set(KONTRAKT.parametry_listy.filtry), (
        "każde pole filtru kryteriów ma wiersz w `parametry_listy.filtry` kontraktu Atlasu"
    )


def test_pole_listowe_z_wieloma_wartosciami_nie_idzie_do_kanalu() -> None:
    with pytest.raises(ValueError, match="osobnym przebiegiem"):
        Criteria(rozstrzygniecie=("oddalono", "umorzono")).filtry_kanalu()


def test_nazwy_parametrow_atlasu_nie_wystepuja_w_criteria_py() -> None:
    """Reguła 22 od strony kryteriów: mapowanie żyje w `contract.yaml`, nie w module czystym."""
    zrodlo = Path(modul.__file__).read_text(encoding="utf-8")
    for parametr in KONTRAKT.parametry_listy.filtry.values():
        assert f'"{parametr}"' not in zrodlo, f"parametr `{parametr}` jest literałem w criteria.py"


# --- odcisk i opis ----------------------------------------------------------------------------


def test_fingerprint_nie_zalezy_od_kolejnosci_wartosci_ani_pol_pustych() -> None:
    a = Criteria(rozstrzygniecie=("oddalono", "umorzono"), od=date(2024, 1, 1))
    b = Criteria(rozstrzygniecie=("umorzono", "oddalono"), od=date(2024, 1, 1), fraza="")

    assert a.fingerprint() == b.fingerprint()
    assert len(a.fingerprint()) == 16
    assert a.fingerprint() != Criteria(od=date(2024, 1, 2)).fingerprint()


def test_canonical_json_pomija_pola_puste_i_odtwarza_sie_z_json() -> None:
    k = Criteria(od=date(2024, 1, 1), do=date(2024, 1, 31), rodzaj=("wyrok",), maks=10)

    dane = json.loads(k.canonical_json())

    assert set(dane) == {"od", "do", "rodzaj", "maks"}
    assert Criteria.z_json(k.canonical_json()) == k


def test_describe_jest_po_polsku_i_niesie_kazde_pole() -> None:
    k = Criteria(
        od=date(2024, 1, 1),
        fraza="odrzucenie oferty",
        rozstrzygniecie=("oddalono",),
        rodzaj=("wyrok",),
        przepis="art. 226",
        przewodniczacy="Nowak",
        strona="Gmina",
        maks=7,
    )

    opis = k.describe()

    for fragment in (
        "daty wydania: 2024-01-01 – …",
        "fraza: „odrzucenie oferty”",
        "rozstrzygnięcie: oddalono",
        "rodzaj: wyrok",
        "przepis: art. 226",
        "przewodniczący: Nowak",
        "strona postępowania: Gmina",
        "maksymalnie 7 dokumentów",
    ):
        assert fragment in opis, fragment
    assert Criteria().describe() == "bez kryteriów"


def test_wartosc_spoza_listy_zmierzonej_przechodzi_z_ostrzezeniem() -> None:
    """Sto rekordów rocznika 2010 to próbka, nie słownik — odmowa zamieniałaby próbkę w regułę."""
    k = Criteria(rozstrzygniecie=("uwzgledniono",), rodzaj=("uchwala",))

    uwagi = k.ostrzezenia()

    assert len(uwagi) == 2
    assert "uwzgledniono" in uwagi[0] and "2026-09-18" in uwagi[0]
    assert "uchwala" in uwagi[1]
    assert "uwaga:" in k.describe()
    assert (
        Criteria(rozstrzygniecie=ROZSTRZYGNIECIA_ZMIERZONE, rodzaj=RODZAJE_ZMIERZONE).ostrzezenia()
        == ()
    )


def test_poszerzenia_zdejmuja_po_jednym_filtrze_od_najbardziej_podejrzanego() -> None:
    k = Criteria(od=date(2024, 1, 1), fraza="x", strona="y", rozstrzygniecie=("oddalono",))

    kandydaci = k.poszerzenia()

    assert [pole for pole, _ in kandydaci] == ["fraza", "strona", "rozstrzygniecie", "daty"]
    assert all(not kandydat.is_empty() for _, kandydat in kandydaci)
    assert kandydaci[0][1].fraza == "" and kandydaci[0][1].strona == "y"


def test_poszerzenia_nie_produkuja_kandydata_pustego() -> None:
    assert Criteria(fraza="x").poszerzenia() == ()
    assert Criteria(od=date(2024, 1, 1)).poszerzenia() == ()
