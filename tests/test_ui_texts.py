"""`ui/texts.py`: zdania da się sprawdzić bez terminala — i mówią liczby, nie etykiety."""

from __future__ import annotations

from datetime import date

from kio_tool.criteria import Criteria
from kio_tool.ui import texts
from kio_tool.ui.texts import Block


def test_block_as_text_sklada_tytul_naglowki_wiersze_i_uwagi() -> None:
    blok = Block(title="T", headers=("a", "b"), rows=(("1", "2"),), notes=("u",))

    assert blok.as_text() == "T\na | b\n1 | 2\nu"
    assert Block(title="").as_text() == ""


def test_kazda_stala_pomocy_jest_niepustym_zdaniem() -> None:
    pomoce = {n: v for n, v in vars(texts).items() if n.startswith("POMOC_")}

    assert len(pomoce) >= 20
    assert all(isinstance(v, str) and v.strip() for v in pomoce.values())


def test_podsumowanie_mowi_o_calym_przebiegu_gdy_sesja_go_nie_pokrywa() -> None:
    tekst = texts.podsumowanie(
        run_id="r",
        status="zakonczony",
        kandydatow=96,
        nowych=96,
        pominietych=0,
        zadan=97,
        baza="b",
        zgloszone=100,
        objetych_lacznie=100,
        pobranych_lacznie=100,
        zadan_lacznie=102,
        bledow_odczytu=1,
    )

    assert "Żądań wysłanych: 97" in tekst
    assert "objętych 100, pobranych 100, żądań 102" in tekst
    assert "Kanał zgłosił w zakresie: 100" in tekst
    assert "nieodczytanych do metadanych: 1" in tekst


def test_podsumowanie_bez_wznowienia_nie_powtarza_liczb() -> None:
    tekst = texts.podsumowanie(
        run_id="r",
        status="zakonczony",
        kandydatow=3,
        nowych=3,
        pominietych=0,
        zadan=4,
        baza="b",
        zgloszone=3,
        objetych_lacznie=3,
        pobranych_lacznie=3,
        zadan_lacznie=4,
    )

    assert "W całym przebiegu" not in tekst and "zgłosił" not in tekst


def test_blok_wyszukiwania_niesie_liczby_nad_tabela() -> None:
    blok = texts.blok_wyszukiwania(
        (("s", "d", "r", "f"),),
        fraza="x",
        w_korpusie=10,
        zaindeksowanych=8,
        trafien=3,
        bez_daty_poza_filtrem=2,
    )

    assert blok.headers == texts.NAGLOWKI_TRAFIEN
    assert "W korpusie: 10 dokumentów, zaindeksowanych: 8, trafień: 3, pokazano: 1." in blok.notes
    assert any("2 dokumentów nie ma w indeksie" in n for n in blok.notes)
    assert any("bez daty" in n for n in blok.notes)


def test_zero_trafien_diagnozuje_co_zdjac_i_czy_indeks_jest_pelny() -> None:
    kryteria = Criteria(fraza="x", od=date(2024, 1, 1), rozstrzygniecie=("oddalono",))

    blok = texts.zero_trafien(kryteria, w_korpusie=5, zaindeksowanych=3)

    tekst = blok.as_text()
    assert "Zero trafień" in tekst and kryteria.describe() in tekst
    assert "Tylko 3 z 5 dokumentów" in tekst
    assert "Spróbuj bez pola „fraza”" in tekst
    assert "Spróbuj bez pola „rozstrzygnięcie”" in tekst
    assert "Spróbuj bez pola „daty wydania”" in tekst


def test_zero_trafien_przy_jedynym_filtrze_mowi_ze_jest_jedyny() -> None:
    tekst = texts.zero_trafien(Criteria(fraza="x"), w_korpusie=1, zaindeksowanych=1).as_text()

    assert "jedyny filtr" in tekst


def test_zero_kandydatow_mowi_co_search_kanalu_naprawde_przeszukuje() -> None:
    """Pomiar filtrów Atlasu 2026-09-18 (`docs/decisions.md`): `search` dopasowuje sygnaturę, nie
    treść. Pusty wynik u kanału ma kierować do `szukaj` na korpusie lokalnym, nie do poszerzania
    frazy."""
    tekst = texts.zero_kandydatow(Criteria(fraza="x", strona="y")).as_text()

    assert "Spróbuj bez pola „fraza”" in tekst
    assert "sygnaturę, nie treść" in tekst and "`szukaj`" in tekst


def test_blok_runow_i_eksportu_niosa_liczby_z_argumentow() -> None:
    runy = texts.blok_runow((("r1", "zakonczony", "atlas", "z", "t", "3", "4"),), lacznie=26)
    eksport = texts.blok_eksportu(["a.xlsx"], 3, ("xlsx",), bez_daty_poza_filtrem=2)

    assert runy.title == "Przebiegi: pokazano 1 z 26" and runy.headers == texts.NAGLOWKI_RUNOW
    assert ("plik", "a.xlsx") in eksport.rows and ("dokumentów w eksporcie", "3") in eksport.rows
    assert any("2 dokumentów bez daty" in n for n in eksport.notes)


def test_blok_przeliczenia_ostrzega_o_dokumentach_bez_metadanych() -> None:
    blok = texts.blok_przeliczenia(5, 1, w_korpusie=6, zaindeksowanych=5)

    assert ("błędów odczytu", "1") in blok.rows
    assert any("1 dokumentów nadal bez metadanych" in n for n in blok.notes)
    assert texts.blok_przeliczenia(6, 0, w_korpusie=6, zaindeksowanych=6).notes == ()


def test_podsumowanie_wypisuje_ponowienia_z_bazy_tylko_gdy_byly() -> None:
    """ADR-0007 Z-7 ujście 4: liczba ponowień na końcu przebiegu — a przy zerze bez wiersza,
    żeby zwykły przebieg nie niósł zdania o zdarzeniu, którego nie było."""
    wspolne: dict[str, object] = {
        "run_id": "r",
        "status": "zakonczony",
        "kandydatow": 3,
        "nowych": 3,
        "pominietych": 0,
        "zadan": 5,
        "baza": "b",
    }

    z = texts.podsumowanie(**wspolne, ponowien_lacznie=2)  # type: ignore[arg-type]
    bez = texts.podsumowanie(**wspolne)  # type: ignore[arg-type]

    assert "Ponowień w całym przebiegu (z bazy): 2" in z
    assert z.splitlines()[-1] == "Baza: b", "baza zostaje ostatnim wierszem"
    assert "Ponowień" not in bez


def test_czas_ludzki_odmienia_doby_takze_powyzej_dwudziestu_jeden() -> None:
    """Wycena rocznika idzie w dziesiątki dób, a reguła „od pięciu — dób" kończy się na 21.

    Do przeglądu kodu fazy 3 (2026-09-20) 22 doby wychodziły jako „22 dób"; to zdanie
    operator widzi w tabeli kosztów, więc kosmetyka jest tu widoczna, nie ukryta.
    """
    doba = 24 * 3600
    assert texts.czas_ludzki(doba) == "1 doba 0 h"
    assert texts.czas_ludzki(3 * doba) == "3 doby 0 h"
    assert texts.czas_ludzki(5 * doba) == "5 dób 0 h"
    assert texts.czas_ludzki(12 * doba) == "12 dób 0 h"
    assert texts.czas_ludzki(22 * doba) == "22 doby 0 h"
    assert texts.czas_ludzki(25 * doba) == "25 dób 0 h"


# --- podpowiedzi dla operatora, który nie zna narzędzia (zgłoszenie z 2026-09-20) --------------


def test_kazde_pytanie_tekstowe_ma_podpowiedz() -> None:
    """Pytanie tekstowe bez podpowiedzi nie mówi, co wolno wpisać.

    To jest strażnik zgłoszenia operatora: „użytkownik, który nie jest zapoznany z tematem,
    nie będzie wiedzieć, co należy wpisać". Pole wyboru podpowiedzi nie potrzebuje — opcje
    widać — ale pole tekstowe jest pustą linią, a format daty albo znaczenie pustej odpowiedzi
    nie są odgadywalne.
    """
    tekstowe = {
        nazwa: p
        for nazwa, p in vars(texts).items()
        if isinstance(p, texts.Pytanie) and p.rodzaj == "tekst"
    }
    bez_podpowiedzi = sorted(nazwa for nazwa, p in tekstowe.items() if not p.podpowiedz.strip())

    assert tekstowe, "skan pusty — pytania tekstowe przestały być stałymi modułu"
    assert not bez_podpowiedzi, bez_podpowiedzi


def test_linia_tekstowa_sklada_podpowiedz_i_domyslna() -> None:
    goły = texts.Pytanie(tresc="Data", rodzaj="tekst")
    assert texts.linia_tekstowa(goły) == "Data"

    z_podpowiedzia = texts.Pytanie(tresc="Data", rodzaj="tekst", podpowiedz="RRRR-MM-DD")
    assert texts.linia_tekstowa(z_podpowiedzia) == "Data (RRRR-MM-DD)"

    z_domyslna = texts.Pytanie(
        tresc="Data", rodzaj="tekst", podpowiedz="RRRR-MM-DD", domyslna="2024-01-01"
    )
    assert texts.linia_tekstowa(z_domyslna) == "Data (RRRR-MM-DD) [domyślnie: 2024-01-01]"


def test_pierwszy_ekran_niesie_stan_korpusu_i_zasady_obslugi() -> None:
    """Operator ma po pierwszym ekranie wiedzieć, co ma w ręku i jak się tym steruje."""
    stan = texts.StanKorpusu(
        dokumentow=443, zaindeksowanych=440, przerwanych=2, sciezka="C:/baza/korpus.sqlite"
    )
    tekst = texts.pierwszy_ekran(pokaz=False, stan=stan).as_text()

    assert "443" in tekst and "440 z 443" in tekst
    assert "C:/baza/korpus.sqlite" in tekst
    assert "przerwane pobrania | 2" in tekst
    for zdanie in texts.JAK_TO_DZIALA:
        assert zdanie in tekst

    bez_stanu = texts.pierwszy_ekran(pokaz=False).as_text()
    assert "443" not in bez_stanu, "bez stanu ekran nie zmyśla liczb"


def test_pozycje_menu_mowia_czy_kosztuja_zadania() -> None:
    stan = texts.StanKorpusu(
        dokumentow=443, zaindeksowanych=443, przerwanych=1, sciezka="korpus.sqlite"
    )
    etykiety = {
        o.klucz: o.etykieta for o in texts.pytanie_menu(jest_co_wznowic=True, stan=stan).opcje
    }

    assert "443 orzeczenia" in etykiety[texts.MENU_SZUKAJ]
    assert "bez sieci" in etykiety[texts.MENU_SZUKAJ]
    assert "bez sieci" in etykiety[texts.MENU_EKSPORTUJ]
    assert "koszt" in etykiety[texts.MENU_POBIERZ]
    assert texts.MENU_WZNOW in etykiety


def test_odmiana_liczebnika_po_polsku() -> None:
    """Ta sama reguła dla dób i orzeczeń — licznik odmieniany osobno rozjeżdża się w trzecim."""
    assert texts.orzeczen(1) == "1 orzeczenie"
    assert texts.orzeczen(3) == "3 orzeczenia"
    assert texts.orzeczen(5) == "5 orzeczeń"
    assert texts.orzeczen(12) == "12 orzeczeń"
    assert texts.orzeczen(22) == "22 orzeczenia"
    assert texts.orzeczen(443) == "443 orzeczenia"
    assert texts.orzeczen(445) == "445 orzeczeń"
    assert texts.orzeczen(0) == "0 orzeczeń"
