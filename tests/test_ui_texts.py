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


def test_zero_kandydatow_zastrzega_niezmierzona_semantyke_filtrow() -> None:
    tekst = texts.zero_kandydatow(Criteria(fraza="x", strona="y")).as_text()

    assert "Spróbuj bez pola „fraza”" in tekst
    assert "nie miały jeszcze własnego pomiaru" in tekst


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
