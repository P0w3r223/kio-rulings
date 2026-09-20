"""Widok znormalizowany (`parser/clean.py`) i segmentacja (`parser/sections.py`) — ADR-0006, III.

Materiał jest **wymyślony** i to jest warunek, nie wygoda: prawdziwe orzeczenia niosą nazwiska
składu i protokolantów, więc do repozytorium nie wchodzą (ADR-0006 Z-11). Każdy tekst niżej
odtwarza **kształt** zmierzony na korpusie 2026-09-19 (443 dokumenty, 0 żądań) — cechę, która
w danym dokumencie wywracała segmentację — a nie jego treść. Przy każdym przypadku stoi
sygnatura dokumentu, w którym cechę znaleziono, żeby dało się wrócić do źródła w korpusie.
"""

from __future__ import annotations

import pytest

from kio_tool.parser.clean import normalizuj
from kio_tool.parser.sections import RODZAJE_SEKCJI, Sekcja, pokrycie, segmentuj

WYROK = (
    "Sygn. akt: KIO 1/24\n"
    "\n"
    "WYROK\n"
    "z dnia 5 stycznia 2024 r.\n"
    "Krajowa Izba Odwoławcza - w składzie:\n"
    "Przewodniczący: (imię wymyślone)\n"
    "po rozpoznaniu na rozprawie odwołania wniesionego przez wykonawcę\n"
    "(nazwa wymyślona) w postępowaniu prowadzonym przez zamawiającego (nazwa wymyślona)\n"
    "orzeka:\n"
    "1. oddala odwołanie,\n"
    "2. kosztami postępowania obciąża odwołującego.\n"
    "Stosownie do art. 579 ust. 1 i 580 ust. 1 ustawy na niniejszy wyrok przysługuje skarga\n"
    "za pośrednictwem Prezesa Krajowej Izby Odwoławczej do Sądu Okręgowego w Warszawie.\n"
    "\f\n"
    "Przewodniczący: ……………………\n"
    "Sygn. akt: KIO 1/24\n"
    "Uzasadnienie\n"
    "Zamawiający prowadzi postępowanie o udzielenie zamówienia publicznego w trybie\n"
    "podstawowym. Izba ustaliła, co następuje. Odwołanie nie zasługuje na uwzględnienie.\n"
    + "Izba zważyła, że zarzuty odwołania nie potwierdziły się w żadnym zakresie.\n"
    * 4
)


def _tekst(oryginal: str, sekcja: Sekcja) -> str:
    return oryginal[sekcja.start : sekcja.koniec]


def _rodzaje(oryginal: str) -> list[str]:
    return [s.rodzaj for s in segmentuj(oryginal)]


# --- clean: widok i offsety ------------------------------------------------------------------


def test_widok_skleja_wiersz_lamany_w_zdaniu_i_usuwa_wysuw_strony() -> None:
    widok = normalizuj("naruszenie art. 89\nw związku z\f art. 90\n\nWYROK\nz dnia 1")
    assert widok.tekst == "naruszenie art. 89 w związku z art. 90\nWYROK\nz dnia 1"


def test_offsety_widoku_wskazuja_ten_sam_napis_w_oryginale() -> None:
    """Z-5/Z-6: do bazy idą offsety w oryginale, więc przedział widoku ma wycinać z oryginału
    **te same litery** — inaczej cytat w eksporcie nie dałby się sprawdzić przy źródle."""
    oryginal = "  Sygn. akt:   KIO 1/24\n\fz dnia\n5 stycznia"
    widok = normalizuj(oryginal)
    for slowo in ("Sygn.", "KIO 1/24", "stycznia"):
        i = widok.tekst.index(slowo)
        a, b = widok.w_oryginale(i, i + len(slowo))
        assert oryginal[a:b].replace(" ", " ") == slowo
    assert len(widok.offsety) == len(widok.tekst) + 1


def test_naglowek_wielkimi_literami_nie_jest_doklejany_do_nastepnego_wiersza() -> None:
    assert normalizuj("WYROK\nz dnia 5 stycznia").tekst == "WYROK\nz dnia 5 stycznia"


def test_punkt_wyliczenia_zaczyna_nowy_wiersz() -> None:
    """`KIO 3778/23`: `Uzasadnienie` + `35. Krakowski…` sklejone gubiło nagłówek."""
    assert normalizuj("Uzasadnienie\n35. Zamawiający").tekst == "Uzasadnienie\n35. Zamawiający"


def test_przedzial_poza_widokiem_jest_bledem() -> None:
    with pytest.raises(ValueError):
        normalizuj("abc").w_oryginale(0, 4)


def test_pusty_tekst_daje_pusty_widok() -> None:
    widok = normalizuj("\f\n  \n")
    assert (widok.tekst, widok.offsety) == ("", (5,))


# --- sections: kolejność i pokrycie ----------------------------------------------------------


def test_wyrok_dzieli_sie_na_cztery_sekcje_w_kolejnosci() -> None:
    sekcje = segmentuj(WYROK)
    assert [s.rodzaj for s in sekcje] == ["naglowek", "sentencja", "pouczenie", "uzasadnienie"]
    assert _tekst(WYROK, sekcje[1]).startswith("orzeka:")
    assert _tekst(WYROK, sekcje[2]).startswith("Stosownie do art. 579")
    # Nagłówek wygrywa z powtórzoną sygnaturą nad nim: sygnatura zostaje stopką pouczenia.
    assert _tekst(WYROK, sekcje[3]).startswith("Uzasadnienie\nZamawiający")


def test_sekcje_nie_nachodza_na_siebie_i_nie_zostawiaja_luk_w_widoku() -> None:
    sekcje = segmentuj(WYROK)
    for poprzednia, nastepna in zip(sekcje, sekcje[1:], strict=False):
        assert poprzednia.koniec <= nastepna.start
        luka = WYROK[poprzednia.koniec : nastepna.start]
        assert not luka.strip(), f"luka z treścią między sekcjami: {luka!r}"
    assert [s.porzadek for s in sekcje] == list(range(len(sekcje)))


def test_slowo_uzasadnienie_w_sentencji_nie_otwiera_uzasadnienia() -> None:
    """Każda kotwica jest szukana za poprzednią — stąd tylko wiersz za pouczeniem się liczy."""
    tekst = WYROK.replace("1. oddala odwołanie,", "1. oddala odwołanie, bo brak uzasadnienia,")
    sekcje = segmentuj(tekst)
    uzasadnienie = [s for s in sekcje if s.rodzaj == "uzasadnienie"]
    assert len(uzasadnienie) == 1 and "Zamawiający prowadzi" in _tekst(tekst, uzasadnienie[0])
    assert "brak uzasadnienia" in _tekst(tekst, sekcje[1])


def test_naglowek_rozstrzelony_spacjami_jest_rozpoznany() -> None:
    """Pomiar 5: 25,8 % dokumentów ma nagłówek rozstrzelony (`Uz as adnienie`)."""
    tekst = WYROK.replace("\nUzasadnienie\n", "\nUz as adnie nie\n")
    assert _rodzaje(tekst)[-1] == "uzasadnienie"


def test_postanawia_bez_dwukropka_przed_punktem_pierwszym() -> None:
    """`KIO 3884/23`: `postanawia` jako osobny wiersz, bez dwukropka, z `1.` pod spodem."""
    tekst = WYROK.replace("WYROK", "POSTANOWIENIE").replace("orzeka:\n", "postanawia\n")
    sekcje = segmentuj(tekst)
    assert _tekst(tekst, sekcje[1]).startswith("postanawia\n1.")


def test_uzasadnienie_bez_naglowka_zaczyna_sie_od_powtorzonej_sygnatury() -> None:
    """Postanowienia bez wiersza `Uzasadnienie` — strona uzasadnienia otwarta sygnaturą."""
    tekst = WYROK.replace("Uzasadnienie\n", "")
    sekcje = segmentuj(tekst)
    assert sekcje[-1].rodzaj == "uzasadnienie"
    assert _tekst(tekst, sekcje[-1]).startswith("Sygn. akt: KIO 1/24")


def test_uzasadnienie_bez_naglowka_i_sygnatury_zaczyna_sie_pod_podpisem() -> None:
    """`KIO 1004/12` (rocznik 2012): ani nagłówka, ani powtórzonej sygnatury."""
    tekst = WYROK.replace("Sygn. akt: KIO 1/24\nUzasadnienie\n", "")
    sekcje = segmentuj(tekst)
    assert sekcje[-1].rodzaj == "uzasadnienie"
    assert _tekst(tekst, sekcje[-1]).startswith("Zamawiający prowadzi")


def test_uzasadnienie_wklejone_w_wiersz_podpisu() -> None:
    """`KIO 3700/23`: `Przewodniczący:……… uzasadnienie` — ekstrakcja skleiła nagłówek z podpisem,
    a dalszy `UZASADNIENIE` stał dwadzieścia tysięcy znaków niżej."""
    tekst = (
        WYROK.replace(
            "Przewodniczący: ……………………\nSygn. akt: KIO 1/24\nUzasadnienie\n",
            "Przewodniczący: …………………… uzasadnienie odwołania\n",
        )
        + ("dalszy wywód " * 30)
        + "\nUZASADNIENIE\nIzba zważyła.\n"
    )
    sekcje = segmentuj(tekst)
    assert _tekst(tekst, sekcje[-1]).startswith("uzasadnienie odwołania")
    assert len(_tekst(tekst, sekcje[2])) < 400, "stanowisko odwołującego wpadło do pouczenia"


def test_tekst_bez_kotwic_jest_nieprzypisany_i_policzony() -> None:
    """Z-12: brak sekcji nie jest wyjątkiem — jest policzony w znakach, nigdy przemilczany."""
    tekst = "Zwykły akapit bez żadnej struktury orzeczenia."
    sekcje = segmentuj(tekst)
    assert [s.rodzaj for s in sekcje] == ["nieprzypisane"]
    assert pokrycie(sekcje)["nieprzypisane"] == len(tekst)


def test_glowa_bez_cech_naglowka_jest_nieprzypisana() -> None:
    tekst = "Luźny wstęp bez sygnatury\norzeka:\n1. oddala odwołanie."
    assert _rodzaje(tekst)[0] == "nieprzypisane"


def test_pokrycie_zna_kazdy_rodzaj_sekcji() -> None:
    assert set(pokrycie(segmentuj(WYROK))) == set(RODZAJE_SEKCJI)


def test_pusty_tekst_nie_ma_sekcji() -> None:
    assert segmentuj("") == ()
