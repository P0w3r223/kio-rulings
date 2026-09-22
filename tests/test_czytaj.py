"""`czytaj`: jedno orzeczenie po sygnaturze albo `doc_id`, bez eksportu do katalogu (2026-09-22).

Przed tym poleceniem pełny tekst jednego orzeczenia dawał tylko `eksportuj --fraza … --format md`,
a fraza z sygnaturą łapała także orzeczenia ją **cytujące**. Tu pilnujemy trzech obietnic:
odcinki pokrywają treść znak w znak (nic nie ginie przy wyborze sekcji), sygnatura jest
porównywana z listą sygnatur dokumentu, a niejednoznaczność kończy się listą kandydatów, nie
zgadywaniem.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kio_tool.cli import app
from kio_tool.exporter import podzial_tekstu
from kio_tool.store import WierszSekcji
from tests import test_maszynowo

runner = CliRunner()
baza_z_przebiegiem = test_maszynowo.baza_z_przebiegiem
"""Ta sama baza z przebiegiem co w testach wyjścia maszynowego — materiał bez sieci."""


def _json(wyjscie: str) -> list[dict[str, object]]:
    return [json.loads(linia) for linia in wyjscie.splitlines() if linia.startswith("{")]


def _pierwszy_dokument(baza: Path) -> tuple[str, str]:
    doc_id, sygnatury = (
        sqlite3.connect(baza)
        .execute("SELECT doc_id, sygnatury FROM documents ORDER BY doc_id LIMIT 1")
        .fetchone()
    )
    return str(doc_id), str(json.loads(sygnatury)[0])


def _czytaj(baza: Path, *argumenty: str) -> tuple[int, list[dict[str, object]]]:
    wynik = runner.invoke(app, ["czytaj", *argumenty, "--baza", str(baza), "--json"])
    return wynik.exit_code, _json(wynik.output)


def test_odcinki_pokrywaja_tresc_w_calosci_i_po_kolei(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    baza, _ = baza_z_przebiegiem
    doc_id, _ = _pierwszy_dokument(baza)

    kod, linie = _czytaj(baza, doc_id)

    assert kod == 0
    blok = linie[-1]
    odcinki = blok["odcinki"]
    assert isinstance(odcinki, list) and odcinki
    liczby = blok["liczby"]
    assert isinstance(liczby, dict)
    assert [o["start"] for o in odcinki] == [0, *(o["koniec"] for o in odcinki[:-1])]
    assert odcinki[-1]["koniec"] == liczby["znakow_calosci"]
    assert sum(len(o["tresc"]) for o in odcinki) == liczby["znakow"] == liczby["znakow_calosci"]


def test_wybrana_sekcja_niesie_tresc_a_reszta_tylko_miejsce(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    baza, _ = baza_z_przebiegiem
    doc_id, _ = _pierwszy_dokument(baza)
    _, wszystko = _czytaj(baza, doc_id)
    rodzaj = wszystko[-1]["odcinki"][0]["rodzaj"]  # type: ignore[index]

    kod, linie = _czytaj(baza, doc_id, "--sekcja", str(rodzaj))

    assert kod == 0
    odcinki = linie[-1]["odcinki"]
    assert isinstance(odcinki, list)
    z_trescia = [o for o in odcinki if "tresc" in o]
    assert z_trescia and all(o["rodzaj"] == rodzaj for o in z_trescia)
    assert all(o["rodzaj"] != rodzaj for o in odcinki if "tresc" not in o)
    liczby = linie[-1]["liczby"]
    assert isinstance(liczby, dict)
    assert liczby["znakow"] == sum(o["znakow"] for o in z_trescia)


def test_sekcja_nieobecna_w_dokumencie_nie_daje_tresci_i_mowi_o_tym(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    """Dokument fikstury nie ma zdania odrębnego — wybór go nie może oddać cudzego tekstu."""
    baza, _ = baza_z_przebiegiem
    doc_id, _ = _pierwszy_dokument(baza)

    kod, linie = _czytaj(baza, doc_id, "--sekcja", "zdanie_odrebne")

    assert kod == 0
    blok = linie[-1]
    odcinki, liczby, uwagi = blok["odcinki"], blok["liczby"], blok["uwagi"]
    assert isinstance(odcinki, list) and isinstance(liczby, dict) and isinstance(uwagi, list)
    assert all("tresc" not in o for o in odcinki)
    assert liczby["pokazano"] == 0
    assert any("Treść pominięta" in u for u in uwagi)


def test_bez_tresci_zostawia_mape_i_cytowanie(baza_z_przebiegiem: tuple[Path, str]) -> None:
    baza, _ = baza_z_przebiegiem
    doc_id, _ = _pierwszy_dokument(baza)

    kod, linie = _czytaj(baza, doc_id, "--bez-tresci")

    assert kod == 0
    blok = linie[-1]
    odcinki = blok["odcinki"]
    assert isinstance(odcinki, list) and odcinki
    assert all("tresc" not in o and o["znakow"] > 0 for o in odcinki)
    assert blok["liczby"] == {
        "znakow_calosci": odcinki[-1]["koniec"],
        "znakow": 0,
        "odcinkow": len(odcinki),
        "pokazano": 0,
    }
    wiersz = blok["wiersze"][0]  # type: ignore[index]
    assert wiersz["doc_id"] == doc_id and wiersz["cytowanie"]


def test_sygnatura_w_dowolnej_pisowni_trafia_ten_sam_dokument(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    baza, _ = baza_z_przebiegiem
    doc_id, sygnatura = _pierwszy_dokument(baza)
    przedrostek, reszta = sygnatura.split(" ", 1)
    numer, rok = reszta.split("/")

    kod, linie = _czytaj(baza, f"  {przedrostek.lower()}  {numer} / {rok} ", "--bez-tresci")

    assert kod == 0
    assert linie[-1]["wiersze"][0]["doc_id"] == doc_id  # type: ignore[index]


def test_brak_dokumentu_to_kod_3_z_liczba_korpusu(baza_z_przebiegiem: tuple[Path, str]) -> None:
    baza, _ = baza_z_przebiegiem

    kod, linie = _czytaj(baza, "KIO 99999/99")

    assert kod == 3
    assert linie[-1]["rodzaj"] == "blad"
    assert "nie ma „KIO 99999/99”" in str(linie[-1]["tresc"])


def test_dwa_dokumenty_z_jedna_sygnatura_to_lista_kandydatow_nie_zgadywanie(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    """Wyrok i postanowienie w tej samej sprawie mają jedną sygnaturę i dwa dokumenty."""
    baza, _ = baza_z_przebiegiem
    polaczenie = sqlite3.connect(baza)
    (pierwszy, sygnatury), (drugi, _) = polaczenie.execute(
        "SELECT doc_id, sygnatury FROM documents ORDER BY doc_id LIMIT 2"
    ).fetchall()
    polaczenie.execute("UPDATE documents SET sygnatury = ? WHERE doc_id = ?", (sygnatury, drugi))
    polaczenie.commit()
    polaczenie.close()

    kod, linie = _czytaj(baza, json.loads(sygnatury)[0])
    kod_po_id, po_id = _czytaj(baza, drugi, "--bez-tresci")

    assert kod == 3
    tresc = str(linie[-1]["tresc"])
    assert pierwszy in tresc and drugi in tresc
    assert kod_po_id == 0 and po_id[-1]["wiersze"][0]["doc_id"] == drugi  # type: ignore[index]


def test_nieznana_sekcja_to_kod_3_z_lista_dozwolonych(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    baza, _ = baza_z_przebiegiem
    doc_id, _ = _pierwszy_dokument(baza)

    kod, linie = _czytaj(baza, doc_id, "--sekcja", "wstep")

    assert kod == 3
    assert "sentencja" in str(linie[-1]["tresc"])


def _sekcja(porzadek: int, rodzaj: str, start: int, koniec: int) -> WierszSekcji:
    return WierszSekcji(porzadek, rodzaj, start, koniec, "")


@pytest.mark.parametrize(
    ("sekcje", "oczekiwane"),
    [
        ([], [(None, 0, 10)]),
        ([_sekcja(0, "sentencja", 2, 5)], [(None, 0, 2), ("sentencja", 2, 5), (None, 5, 10)]),
        (
            [_sekcja(0, "sentencja", 0, 6), _sekcja(1, "uzasadnienie", 4, 10)],
            [("sentencja", 0, 6), ("uzasadnienie", 6, 10)],
        ),
        ([_sekcja(0, "sentencja", 12, 20)], [(None, 0, 10)]),
    ],
    ids=["bez-sekcji", "odstepy", "nakladanie", "poza-tekstem"],
)
def test_podzial_tekstu_nie_gubi_ani_nie_dubluje_znaku(
    sekcje: list[WierszSekcji], oczekiwane: list[tuple[str | None, int, int]]
) -> None:
    tresc = "0123456789"

    podzial = podzial_tekstu(tresc, sekcje)

    assert list(podzial) == oczekiwane
    assert "".join(tresc[a:b] for _, a, b in podzial) == tresc
