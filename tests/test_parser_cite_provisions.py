"""Cytowania (`parser/cite.py`), przepisy (`parser/provisions.py`) i sygnatury obce (`docid`).

Materiał wymyślony — kształty z pomiaru na korpusie 2026-09-19 (443 dokumenty, 0 żądań),
treść bez nazwisk i bez prawdziwych stron (ADR-0006 Z-11).
"""

from __future__ import annotations

import pytest

from kio_tool.docid import znajdz_sygnatury
from kio_tool.parser.cite import cytowania
from kio_tool.parser.provisions import akt_pzp_dokumentu, przepisy_z_kanalu, przepisy_z_tresci
from kio_tool.parser.sections import segmentuj

TRESC = (
    "Sygn. akt: KIO 1/24\n"
    "WYROK\n"
    "z dnia 5 stycznia 2024 r.\n"
    "orzeka:\n"
    "1. oddala odwołanie.\n"
    "Stosownie do art. 579 ust. 1 ustawy na niniejszy wyrok przysługuje skarga.\n"
    "Przewodniczący: ……………\n"
    "Uzasadnienie\n"
    "Zamawiający prowadzi postępowanie na podstawie ustawy z dnia 11 września 2019 r. – Prawo\n"
    "zamówień publicznych. Odwołujący zarzucił naruszenie art. 226 ust. 1 pkt 5 i art. 224 ust. 6\n"
    "ustawy Pzp. Izba podziela pogląd z wyroku KIO 1234/23do postępowania, z wyroku SO\n"
    "sygn. akt XXIII Zs 12/22, z uchwały III CZP 56/17 i z wyroku TSUE C-652/22.\n"
    "W sprawie o sygn. akt KIO 1/24 Izba ustaliła, że art. 353 1 k.c. nie ma zastosowania.\n"
    "Pogląd wyrażono też w sprawie sygn. akt: 3376/23 — sam numer, organ z kontekstu.\n"
    "Odwołujący powołał się na sygn. akt IV CR 403, której nie da się rozpoznać.\n"
    "Izba zważyła, że odwołanie nie zasługuje na uwzględnienie w żadnym zakresie.\n" * 3
)


def _cyt() -> list[tuple[str, str | None]]:
    return [
        (c.rodzaj, c.sygnatura) for c in cytowania(TRESC, segmentuj(TRESC), wlasne=["KIO 1/24"])
    ]


# --- docid: sygnatury obce -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("zapis", "rodzaj", "kanon"),
    [
        ("KIO 1234/23do", "kio", "KIO 1234/23"),
        ("XXIII Zs 12/22", "so", "XXIII Zs 12/22"),
        ("III CZP 56/17", "sn", "III CZP 56/17"),
        ("I Aga 12/2020", "sa", "I AGa 12/20"),
        ("II GSK 7/15", "nsa", "II GSK 7/15"),
        ("C-652/22", "tsue", "C-652/22"),
        ("IV Xyz 1/20", "inne", "IV Xyz 1/20"),
    ],
)
def test_znajdz_sygnatury_rozpoznaje_organ_i_postac(zapis: str, rodzaj: str, kanon: str) -> None:
    trafienia = znajdz_sygnatury(f"zob. {zapis} oraz dalej")
    assert [(t.rodzaj, t.kanon) for t in trafienia] == [(rodzaj, kanon)]


def test_sklejony_rok_kio_nie_gubi_sygnatury() -> None:
    """`KIO 1234/23do` — 2 wystąpienia w korpusie; `\\b` między cyfrą a literą nie padał."""
    assert [t.kanon for t in znajdz_sygnatury("wyroku KIO 1234/23do postępowania")] == [
        "KIO 1234/23"
    ]


def test_trafienia_nie_nachodza_na_siebie() -> None:
    trafienia = znajdz_sygnatury("KIO 1/24 i KIO/UZP 2/08")
    for a, b in zip(trafienia, trafienia[1:], strict=False):
        assert a.koniec <= b.start


# --- cite ------------------------------------------------------------------------------------


def test_cytowania_tylko_z_uzasadnienia_bez_sygnatury_wlasnej() -> None:
    wynik = _cyt()
    assert ("kio", "KIO 1/24") not in wynik, "sygnatura własna nie jest cytowaniem"
    assert ("kio", "KIO 1234/23") in wynik
    assert ("so", "XXIII Zs 12/22") in wynik
    assert ("sn", "III CZP 56/17") in wynik
    assert ("tsue", "C-652/22") in wynik


def test_zapowiedz_bez_sygnatury_jest_cytowaniem_nierozpoznanym() -> None:
    """Pomiar 22 potrzebuje mianownika: nierozpoznane jest liczone, nie gubione.

    Przykładem nierozpoznanego jest odtąd `sygn. akt IV CR 403` — zapis bez roku, z rodziny J
    pomiaru 25 („nie do odzyskania", 11 trafień w korpusie). Wcześniej stał tu `sygn. akt:
    3376/23`, który od tego samego pomiaru **jest** rozpoznawany, tyle że jako
    `kio_bez_repertorium`.
    """
    nierozpoznane = [c for c in _cyt() if c[1] is None]
    assert nierozpoznane == [("inne", None)] * len(nierozpoznane) and nierozpoznane


def test_sam_numer_po_zapowiedzi_jest_cytowaniem_z_organem_z_kontekstu() -> None:
    """Rodzina A pomiaru 25 — 29 trafień w korpusie, 37 % wszystkich nierozpoznanych.

    Sygnatura kanoniczna jest pełna, żeby łączyła się z indeksem; to, że organ dopisaliśmy
    z kontekstu, a nie odczytali z zapisu, niesie rodzaj — i tylko on.
    """
    assert ("kio_bez_repertorium", "KIO 3376/23") in _cyt()


def test_cytowanie_niesie_offsety_w_oryginale() -> None:
    for c in cytowania(TRESC, segmentuj(TRESC)):
        assert TRESC[c.start : c.koniec] == c.surowy
        if c.sygnatura is not None and c.rodzaj == "kio":
            assert c.surowy.replace("do", "").startswith("KIO")


# --- provisions ------------------------------------------------------------------------------


def test_akt_dokumentu_z_pelnego_tytulu() -> None:
    assert akt_pzp_dokumentu(TRESC) == "pzp2019"
    assert akt_pzp_dokumentu("ustawy z dnia 29 stycznia 2004 r. Prawo") == "pzp2004"
    oba = "ustawy z dnia 29 stycznia 2004 r. i ustawy z dnia 11 września 2019 r."
    assert akt_pzp_dokumentu(oba) == "nieustalone"


def test_brak_tytulu_ustawy_daje_nieustalone_nigdy_date() -> None:
    """Z-8: 101 z 443 dokumentów nie nazywa ustawy — data w nagłówku jej nie rozstrzyga."""
    tekst = "WYROK\nz dnia 5 stycznia 2024 r.\nnaruszenie art. 226 ust. 1 pkt 5 Pzp."
    (przepis,) = przepisy_z_tresci(tekst, segmentuj(tekst))
    assert (przepis.postac, przepis.akt) == ("art. 226 ust. 1 pkt 5", "nieustalone")


def test_wyliczenie_dzieli_oznaczenie_ustawy() -> None:
    przepisy = przepisy_z_tresci(TRESC, segmentuj(TRESC))
    postaci = {p.postac: p.akt for p in przepisy}
    assert postaci["art. 226 ust. 1 pkt 5"] == "pzp2019"
    assert postaci["art. 224 ust. 6"] == "pzp2019"
    assert postaci["art. 353"] == "kc"


def test_przepis_z_tresci_ma_offsety_w_oryginale() -> None:
    for p in przepisy_z_tresci(TRESC, segmentuj(TRESC)):
        assert p.start is not None and p.koniec is not None
        assert TRESC[p.start : p.koniec] == p.surowy


def test_lista_kanalu_ta_sama_gramatyka_bez_offsetow() -> None:
    """Z-7: `law_articles` od Atlasu trafia obok odczytu z treści, ze źródłem `kanal`."""
    przepisy = przepisy_z_kanalu(["art. 226 ust. 1 pkt 5 Pzp", "brak przepisu"], TRESC)
    assert [(p.postac, p.akt, p.zrodlo) for p in przepisy] == [
        ("art. 226 ust. 1 pkt 5", "pzp2019", "kanal"),
        ("brak przepisu", "nieustalone", "kanal"),
    ]
    assert all(p.start is None for p in przepisy)
