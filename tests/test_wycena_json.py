"""`pobierz --wycena` i `--json` poleceń sieciowych: agent zna koszt, zanim zapyta o zgodę.

Do 2026-09-22 tabelę kosztów widział tylko człowiek (kreator albo ekran `pobierz`), a agent,
który miał poprosić operatora o zgodę, nie znał liczby, o którą prosi. `--wycena` wysyła to,
co wycena i tak musi wysłać — pierwszą stronę listy, bo dopiero ona niesie `total` — i odmawia
tą samą drogą co kreator. Tu pilnujemy, że to jest **dokładnie jedno żądanie**, a stdout pod
`--json` niesie wyłącznie linie JSON.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kio_tool.cli import app
from kio_tool.ui import texts
from tests.test_cli import _konsola_powtarzalna, _zegar_sterowany, baza, podstaw
from tests.test_pipeline import Serwer

runner = CliRunner()
ZAKRES = ("--od", "2024-01-01", "--do", "2024-01-31")
baza_testowa = baza
"""Pusta baza w `tmp_path` z adresem kontaktowym w środowisku — z `test_cli`."""
zegar_sterowany = _zegar_sterowany
"""Autouse z `test_cli`: limiter na zegarze testowym — sto żądań atrapy bez stu sekund."""
konsola_powtarzalna = _konsola_powtarzalna


def _json_stdout(wyjscie: str) -> list[dict[str, object]]:
    linie = [linia for linia in wyjscie.splitlines() if linia.strip()]
    return [json.loads(linia) for linia in linie]


def _bloki(linie: list[dict[str, object]], tytul: str) -> list[dict[str, object]]:
    return [linia for linia in linie if linia.get("rodzaj") == "blok" and linia["tytul"] == tytul]


def _pary(blok: dict[str, object], klucz: str) -> list[str]:
    """Wartości wierszy klucz-wartość bloku o danym kluczu (np. wszystkie `plik`)."""
    wiersze = blok["wiersze"]
    assert isinstance(wiersze, list)
    return [str(w["wartosc"]) for w in wiersze if w["klucz"] == klucz]


def _liczby(blok: dict[str, object]) -> dict[str, int]:
    liczby = blok["liczby"]
    assert isinstance(liczby, dict)
    return liczby


def _dokumentow(sciezka: Path) -> int:
    return int(sqlite3.connect(sciezka).execute("SELECT COUNT(*) FROM documents").fetchone()[0])


def test_wycena_to_jedna_strona_listy_zero_dokumentow_i_kod_0(
    baza_testowa: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    wynik = runner.invoke(
        app, ["pobierz", *ZAKRES, "--baza", str(baza_testowa), "--wycena", "--json"]
    )

    assert wynik.exit_code == 0, wynik.output
    assert len(serwer.zadania) == 1 and serwer.strony_zadane == ["1"]
    assert serwer.dokumentow == 0 and _dokumentow(baza_testowa) == 0
    linie = _json_stdout(wynik.stdout)
    (koszt,) = _bloki(linie, "Koszt przebiegu")
    liczby = _liczby(koszt)
    assert liczby["zadan"] > liczby["prog_zgody"] and liczby["wymaga_zgody"] == 1
    assert {"rodzaj": "komunikat", "tresc": texts.WYCENA_GOTOWA} in linie
    status = sqlite3.connect(baza_testowa).execute("SELECT status FROM runs").fetchone()[0]
    assert status == "przerwany"


def test_po_wycenie_to_samo_polecenie_z_zgoda_konczy_przebieg(
    baza_testowa: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer())
    runner.invoke(app, ["pobierz", *ZAKRES, "--baza", str(baza_testowa), "--wycena"])
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    wynik = runner.invoke(
        app,
        ["pobierz", *ZAKRES, "--baza", str(baza_testowa), "--zgoda", "--out", str(tmp_path / "w")],
    )

    assert wynik.exit_code == 0, wynik.output
    assert _dokumentow(baza_testowa) == 100
    przebiegi = sqlite3.connect(baza_testowa).execute("SELECT status FROM runs").fetchall()
    assert przebiegi == [("zakonczony",)], "wznowiony ten sam przebieg, nie drugi"


def test_wycena_ze_zgoda_to_blad_konfiguracji_bez_zadania(
    baza_testowa: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    wynik = runner.invoke(
        app, ["pobierz", *ZAKRES, "--baza", str(baza_testowa), "--wycena", "--zgoda"]
    )

    assert wynik.exit_code == 3
    assert serwer.zadania == []


def test_pobierz_json_stdout_to_same_linie_json_z_rachunkiem_i_plikami(
    baza_testowa: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer())

    wynik = runner.invoke(
        app,
        [
            "pobierz",
            *ZAKRES,
            "--baza",
            str(baza_testowa),
            "--zgoda",
            "--json",
            "--out",
            str(tmp_path / "w"),
        ],
    )

    assert wynik.exit_code == 0, wynik.output
    linie = _json_stdout(wynik.stdout)
    (przebieg,) = _bloki(linie, "Przebieg")
    assert _pary(przebieg, "status") == ["zakonczony"]
    assert _pary(przebieg, "run_id")[0].startswith("atlas-")
    assert _liczby(przebieg)["nowych"] == 100
    (eksport,) = _bloki(linie, "Eksport zapisany")
    assert _liczby(eksport)["dokumentow"] == 100
    pliki = _pary(eksport, "plik")
    assert pliki and all(Path(p).is_file() for p in pliki)


def test_rachunek_dla_programu_nie_trafia_na_ekran_czlowieka(
    baza_testowa: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer())

    wynik = runner.invoke(
        app,
        ["pobierz", *ZAKRES, "--baza", str(baza_testowa), "--zgoda", "--out", str(tmp_path / "w")],
    )

    assert wynik.exit_code == 0, wynik.output
    assert "run_id" not in wynik.output


def test_eksportuj_json_mowi_ile_dokumentow_i_gdzie(
    baza_testowa: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer())
    runner.invoke(
        app,
        ["pobierz", *ZAKRES, "--baza", str(baza_testowa), "--zgoda", "--out", str(tmp_path / "a")],
    )

    run_id = sqlite3.connect(baza_testowa).execute("SELECT run_id FROM runs").fetchone()[0]

    wynik = runner.invoke(
        app,
        [
            "eksportuj",
            "--run-id",
            str(run_id),
            "--baza",
            str(baza_testowa),
            "--format",
            "jsonl",
            "--out",
            str(tmp_path / "b"),
            "--json",
        ],
    )

    assert wynik.exit_code == 0, wynik.output
    (eksport,) = _bloki(_json_stdout(wynik.stdout), "Eksport zapisany")
    assert _liczby(eksport) == {"dokumentow": 100, "bez_daty_poza_filtrem": 0}
    assert _pary(eksport, "plik") == [str(tmp_path / "b.jsonl")]
