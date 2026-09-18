"""Reguła 15: każdy eksport niesie sygnaturę, datę wydania, oznaczenie organu i atrybucję.

To jest warunek ustawowy (art. 15 ust. 1 pkt 4, audyt 8.3), a licencja CC BY 4.0 Atlasu wymaga
atrybucji — więc strażnik jest testem **zachowania** każdego formatu, nie skanem granic. Formaty
parametryzowane z `exporter.FORMATY`: format dopisany do eksportera bez czytnika tutaj zapala
`test_kazdy_format_ma_czytnik`, a `test_boundaries.py` pilnuje, że każdy format jest w tym pliku
wymieniony z nazwy: "xlsx", "csv", "jsonl", "md".
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import openpyxl
import pytest

from kio_tool.docid import SourceName
from kio_tool.exporter import DATA_NIEZNANA, FORMATY, ORGAN, Wpis, blok_atrybucji, eksportuj
from kio_tool.parser.details import rekord_z_bajtow, wyczytaj
from kio_tool.pipeline import mapa_pol
from kio_tool.source.contract import load_contract

ZLOTE = Path(__file__).resolve().parent / "examples" / "atlas"
DOKUMENT_BAJTY = (ZLOTE / "dokument_20260918T103526Z.json").read_bytes()
KONTRAKT = load_contract(SourceName("atlas"))
MAPA = mapa_pol(KONTRAKT)
ATRYBUCJA = KONTRAKT.licencja.atrybucja
SYGNATURA = "KIO 1205/20"
DATA = "2004-01-29"


def wpis(**zmiany: object) -> Wpis:
    rekord = rekord_z_bajtow(DOKUMENT_BAJTY)
    rekord.update(zmiany)
    return Wpis(
        doc_id="atlas:kio-1205-20",
        source="atlas",
        source_ref="kio-1205-20",
        sha256="e" * 64,
        fetched_at="2026-09-18T12:00:00Z",
        szczegoly=wyczytaj(rekord, MAPA),
        rekord=rekord,
        atrybucja=ATRYBUCJA,
    )


def _xlsx(sciezka: Path) -> str:
    wb = openpyxl.load_workbook(sciezka, read_only=True)
    naglowek, *dane = (tuple(w) for w in wb["Orzeczenia"].iter_rows(values_only=True))
    komorki = dict(zip(naglowek, dane[0], strict=True))
    # Kolumny z nazwy, nie "gdziekolwiek w arkuszu": sygnatura w kolumnie `sygnatura`. Doklejka
    # całego wiersza, która tu stała do przeglądu 2026-09-18, sprawiała, że asercja przechodziła
    # także przy pustej kolumnie `sygnatura`, byle sygnatura została w `sygnatury`.
    return " | ".join(str(komorki[k]) for k in ("sygnatura", "data_wydania", "organ", "atrybucja"))


def _csv(sciezka: Path) -> str:
    with sciezka.open(encoding="utf-8-sig", newline="") as plik:
        wiersze = list(csv.reader(plik, delimiter=";"))
    return " | ".join(wiersze[1])


def _jsonl(sciezka: Path) -> str:
    obiekt = json.loads(sciezka.read_text(encoding="utf-8").splitlines()[0])
    return " | ".join(
        str(obiekt[k]) for k in ("sygnatura", "data_wydania", "organ", "atrybucja", "cytowanie")
    )


def _md(katalog: Path) -> str:
    pliki = [p for p in katalog.glob("*.md") if p.name != "INDEX.md"]
    return pliki[0].read_text(encoding="utf-8")


CZYTNIKI: dict[str, Callable[[Path], str]] = {
    "xlsx": _xlsx,
    "csv": _csv,
    "jsonl": _jsonl,
    "md": _md,
}


def test_kazdy_format_ma_czytnik() -> None:
    """Antypustka: format dopisany do `FORMATY` bez czytnika tutaj nie ma strażnika reguły 15."""
    assert set(CZYTNIKI) == set(FORMATY)


def _eksport(tmp_path: Path, fmt: str, *wpisy: Wpis) -> str:
    def zrodlo() -> Iterator[Wpis]:
        yield from wpisy

    (sciezka,) = eksportuj(tmp_path / "e", zrodlo, formaty=(fmt,), metadane=())
    return CZYTNIKI[fmt](sciezka)


@pytest.mark.parametrize("fmt", FORMATY)
def test_eksport_niesie_sygnature_date_organ_i_atrybucje(tmp_path: Path, fmt: str) -> None:
    tresc = _eksport(tmp_path, fmt, wpis())

    assert SYGNATURA in tresc, f"{fmt}: brak sygnatury"
    assert DATA in tresc, f"{fmt}: brak daty wydania"
    assert ORGAN in tresc, f"{fmt}: brak oznaczenia organu"
    assert ATRYBUCJA in tresc, f"{fmt}: brak atrybucji licencyjnej Atlasu"


@pytest.mark.parametrize("fmt", ("jsonl", "md"))
def test_blok_cytowania_mowi_data_nieznana_zamiast_milczec(tmp_path: Path, fmt: str) -> None:
    """Pusta data jest `None` w danych, ale w bloku cytowania ma być **powiedziana**."""
    tresc = _eksport(tmp_path, fmt, wpis(ruling_date=None))

    assert DATA_NIEZNANA in tresc and SYGNATURA in tresc and ORGAN in tresc


def test_blok_atrybucji_ma_rodzaj_date_sygnatury_organ_zrodlo_wersje_i_licencje() -> None:
    blok = blok_atrybucji(wpis())

    pierwsza, druga = blok.splitlines()
    assert pierwsza.startswith(f"Postanowienie KIO z {DATA}, sygn. {SYGNATURA}, {ORGAN}")
    assert "wersja: " + "e" * 12 in pierwsza and "pobrano 2026-09-18T12:00:00Z" in pierwsza
    assert "orzeczenia.uzp.gov.pl" in pierwsza
    assert druga == ATRYBUCJA


def test_atrybucja_pochodzi_z_kontraktu_kanalu_nie_z_literalu() -> None:
    """`licencja.atrybucja` z `contract.yaml` (pomiar 23) — jedyne miejsce z tym napisem."""
    assert ATRYBUCJA.startswith("Źródło: Atlas Przetargów")
    assert "https://atlasprzetargow.pl" in ATRYBUCJA


def test_oznaczenie_organu_jest_pelna_nazwa_izby() -> None:
    """Art. 15 ust. 1 pkt 4 mówi o oznaczeniu organu — skrót „KIO” nim nie jest."""
    assert ORGAN == "Krajowa Izba Odwoławcza"
