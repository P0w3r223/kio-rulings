"""Wyjście maszynowe (`--json`) i jego powód: tabela dla oka gubi wartości poza terminalem.

Ten plik jest obserwatorem usterki, której suita **sama nie mogła zobaczyć**. Autouse
`_konsola_powtarzalna` w `test_cli.py` przypina `COLUMNS=200`, i słusznie — bez tego asercje
o treści komunikatów mierzyłyby przy okazji szerokość maszyny. Skutkiem ubocznym było jednak to,
że żaden test nigdy nie oglądał wypisu przy szerokości domyślnej, czyli dokładnie w warunkach,
w jakich narzędzie pracuje pod agentem: bez terminala `rich` przyjmuje 80 znaków i łamie wartości
w środku. Tu szerokość jest **wąska celowo** (doktryna: gwarancja bez obserwatora nie jest
gwarancją).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer import rich_utils
from typer.testing import CliRunner

from kio_tool import cli, obsluga
from kio_tool.cli import app
from kio_tool.config import CONTACT_ENV
from kio_tool.store import Dokument, Filtr
from kio_tool.ui import texts
from kio_tool.ui.maszynowo import JsonView, blok_na_slownik, klucz, klucze
from tests.test_cli import Serwer, podstaw
from tests.wsparcie_sondy import ZegarTestowy

runner = CliRunner()

WASKO = "80"
"""Szerokość domyślna `rich` bez terminala — ta, przy której usterka powstaje."""


@pytest.fixture
def baza_z_przebiegiem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """Baza z jednym przebiegiem i jego identyfikatorem — materiał obu wypisów."""
    monkeypatch.setattr(cli, "SystemClock", ZegarTestowy)
    monkeypatch.setenv(CONTACT_ENV, "test@example.org")
    monkeypatch.delenv("KIO_TOOL_ATLAS_KEY", raising=False)
    monkeypatch.setattr(rich_utils, "MAX_WIDTH", 200)
    monkeypatch.setenv("COLUMNS", WASKO)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    baza = tmp_path / "korpus.sqlite"
    podstaw(monkeypatch, Serwer())
    runner.invoke(
        app,
        [
            "pobierz",
            "--od",
            "2024-01-01",
            "--do",
            "2024-01-31",
            "--baza",
            str(baza),
            "--zgoda",
            "--out",
            str(tmp_path / "wynik"),
        ],
    )
    run_id = sqlite3.connect(baza).execute("SELECT run_id FROM runs").fetchone()[0]
    return baza, str(run_id)


def _wiersze_json(wyjscie: str) -> list[dict[str, object]]:
    return [json.loads(linia) for linia in wyjscie.splitlines() if linia.startswith("{")]


# --- klucze ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("naglowek", "oczekiwany"),
    [
        ("sygnatura", "sygnatura"),
        ("data wydania", "data_wydania"),
        ("żądań", "zadan"),
        ("dokumentów", "dokumentow"),
        ("rozstrzygnięcie", "rozstrzygniecie"),
        ("kanał", "kanal"),
        ("  Dwa  Słowa  ", "dwa_slowa"),
    ],
)
def test_klucz_zwija_naglowek_dla_oka_do_klucza_dla_programu(
    naglowek: str, oczekiwany: str
) -> None:
    assert klucz(naglowek) == oczekiwany


def test_kolizja_kluczy_jest_wyjatkiem_a_nie_cichym_nadpisaniem() -> None:
    """Dwa nagłówki dające ten sam klucz zabrałyby konsumentowi kolumnę bez słowa."""
    with pytest.raises(ValueError, match="kolizja"):
        klucze(("data wydania", "data_wydania"))


def test_naglowki_obu_polecen_nie_kolizjonuja() -> None:
    assert klucze(texts.NAGLOWKI_TRAFIEN) and klucze(texts.NAGLOWKI_RUNOW)


# --- kształt dokumentu ---------------------------------------------------------------------------


def test_blok_z_naglowkami_daje_wiersze_jako_obiekty_i_liczby_osobno() -> None:
    blok = texts.blok_runow((("atlas-abc", "zakonczony", "atlas", "2024", "t", "6", "7"),), 19)

    dokument = blok_na_slownik(blok)

    assert dokument["rodzaj"] == "blok"
    assert dokument["kolumny"] == [
        "przebieg",
        "status",
        "kanal",
        "zakres",
        "start",
        "dokumentow",
        "zadan",
    ]
    assert dokument["wiersze"] == [
        {
            "przebieg": "atlas-abc",
            "status": "zakonczony",
            "kanal": "atlas",
            "zakres": "2024",
            "start": "t",
            "dokumentow": "6",
            "zadan": "7",
        }
    ]
    assert dokument["liczby"] == {"pokazano": 1, "lacznie": 19}


def test_liczby_wyszukania_niosa_to_samo_co_zdanie_nad_tabela() -> None:
    """Agent nie ma parsować prozy: proza należy do widoku dla człowieka i wolno jej się
    zmienić bez uprzedzenia. Liczby są kontraktem, zdanie nie jest."""
    blok = texts.blok_wyszukiwania(
        (("KIO 1/24", "2024-01-02", "oddalono", "…"),),
        fraza="x",
        w_korpusie=443,
        zaindeksowanych=443,
        trafien=61,
        bez_daty_poza_filtrem=0,
    )

    liczby = blok_na_slownik(blok)["liczby"]

    assert liczby == {
        "w_korpusie": 443,
        "zaindeksowanych": 443,
        "trafien": 61,
        "pokazano": 1,
        "bez_daty_poza_filtrem": 0,
    }
    assert "trafień: 61" in " ".join(blok.notes)


def test_znak_sterujacy_z_korpusu_nie_wychodzi_poza_swoja_wartosc() -> None:
    """Reguła 10 na drugim kanale: `json.dumps` koduje `ESC`, więc nie steruje terminalem."""
    blok = texts.blok_runow((("a\x1b[31mb", "s", "k", "z", "t", "1", "1"),), 1)

    napis = json.dumps(blok_na_slownik(blok), ensure_ascii=False)

    assert "\\u001b" in napis and "\x1b" not in napis


def test_blad_idzie_na_stderr_takze_w_postaci_maszynowej(
    capsys: pytest.CaptureFixture[str],
) -> None:
    JsonView().error("nie ma bazy")

    zlapane = capsys.readouterr()
    assert zlapane.out == ""
    assert json.loads(zlapane.err) == {"rodzaj": "blad", "tresc": "nie ma bazy"}


# --- to, po co ta flaga w ogóle powstała ---------------------------------------------------------


def test_waska_konsola_lamie_identyfikator_przebiegu_a_json_go_oddaje_w_calosci(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    """Pomiar z 2026-09-20, powtórzony jako test.

    Przy 80 znakach identyfikator `atlas-…` rozpada się na kilka wierszy, więc agent nie ma
    z czego złożyć `eksportuj --run-id`. Ten test pilnuje obu połówek naraz: że problem jest
    prawdziwy i że `--json` go nie ma. Gdyby kiedyś tabela przestała się łamać, pierwsza asercja
    zapali się i każe sprawdzić, czy flaga jest jeszcze potrzebna.
    """
    baza, run_id = baza_z_przebiegiem

    tabela = runner.invoke(app, ["runy", "--baza", str(baza)])
    maszynowo = runner.invoke(app, ["runy", "--baza", str(baza), "--json"])

    assert run_id not in tabela.output, "tabela nie łamie już wartości — sprawdź powód flagi"
    wiersze = _wiersze_json(maszynowo.output)
    assert [w["przebieg"] for w in wiersze[-1]["wiersze"]] == [run_id]  # type: ignore[index]


def test_json_i_ekran_mowia_te_same_liczby(baza_z_przebiegiem: tuple[Path, str]) -> None:
    """`--json` zamienia odbiorcę, nie treść — osobna ścieżka mogłaby się rozjechać."""
    baza, _ = baza_z_przebiegiem

    tabela = runner.invoke(app, ["runy", "--baza", str(baza)])
    maszynowo = runner.invoke(app, ["runy", "--baza", str(baza), "--json"])

    liczby = _wiersze_json(maszynowo.output)[-1]["liczby"]
    assert liczby == {"pokazano": 1, "lacznie": 1}
    assert "pokazano 1 z 1" in tabela.output


def test_szukaj_json_niesie_mianownik_i_klucze_kolumn(
    baza_z_przebiegiem: tuple[Path, str],
) -> None:
    baza, _ = baza_z_przebiegiem

    wynik = runner.invoke(
        app, ["szukaj", "--fraza", "tresc wymyslona", "--baza", str(baza), "--json"]
    )

    assert wynik.exit_code == 0
    blok = _wiersze_json(wynik.output)[-1]
    assert blok["kolumny"] == [
        "sygnatura",
        "data_wydania",
        "rozstrzygniecie",
        "fragment",
        "doc_id",
        "url_zrodla",
        "cytowanie",
    ]
    liczby = blok["liczby"]
    assert isinstance(liczby, dict) and liczby["trafien"] > 0
    assert liczby["w_korpusie"] == liczby["zaindeksowanych"] > 0


def test_trafienie_json_niesie_ten_sam_blok_cytowania_co_eksport(
    baza_z_przebiegiem: tuple[Path, str], tmp_path: Path
) -> None:
    """Slajd obiecuje „blok cytowania, ten sam w pliku i w wyniku dla programu" (2026-09-22).
    Porównanie z JSONL eksportu, nie z wzorcem napisu: dwa niezależne wzorce zgadzałyby się
    ze sobą także wtedy, gdy oba wyjścia rozjechały się z blokiem, który trafia do pliku."""
    baza, _ = baza_z_przebiegiem
    fraza = ["--fraza", "tresc wymyslona", "--baza", str(baza)]

    wynik = runner.invoke(app, ["szukaj", *fraza, "--json"])
    eksport = runner.invoke(
        app, ["eksportuj", *fraza, "--format", "jsonl", "--out", str(tmp_path / "e")]
    )

    assert wynik.exit_code == 0 and eksport.exit_code == 0, eksport.output
    z_pliku = {
        (d := json.loads(w))["doc_id"]: d["cytowanie"]
        for w in (tmp_path / "e.jsonl").read_text(encoding="utf-8").splitlines()
    }
    trafienia = _wiersze_json(wynik.output)[-1]["wiersze"]
    assert isinstance(trafienia, list) and trafienia
    for trafienie in trafienia:
        assert trafienie["cytowanie"] == z_pliku[trafienie["doc_id"]]


def test_tabela_nie_rysuje_kolumn_maszynowych(baza_z_przebiegiem: tuple[Path, str]) -> None:
    """Blok cytowania przy każdym wierszu rozsadziłby tabelę dla oka — idzie tylko do `--json`."""
    baza, _ = baza_z_przebiegiem

    wynik = runner.invoke(app, ["szukaj", "--fraza", "tresc wymyslona", "--baza", str(baza)])

    assert wynik.exit_code == 0
    assert "cytowanie" not in wynik.output and "url_zrodla" not in wynik.output


def test_dodatek_przesuniety_o_wiersz_jest_bledem_nie_wynikiem() -> None:
    blok = texts.Block(
        title="t",
        headers=("a",),
        rows=(("1",), ("2",)),
        kolumny_maszynowe=("b",),
        wiersze_maszynowe=(("x",),),
    )

    with pytest.raises(ValueError, match="dodatków"):
        blok_na_slownik(blok)


def test_zero_trafien_tez_niesie_mianownik(baza_z_przebiegiem: tuple[Path, str]) -> None:
    """Przy zerze mianownik jest potrzebny **bardziej**: odróżnia „nie ma takich orzeczeń"
    od „nie ma ich w tym, co pobrano". Bez niego agent odpowie pierwszym zdaniem zamiast
    drugiego i nikt tego nie zauważy."""
    baza, _ = baza_z_przebiegiem

    wynik = runner.invoke(
        app, ["szukaj", "--fraza", "czegos takiego tam nie ma", "--baza", str(baza), "--json"]
    )

    blok = _wiersze_json(wynik.output)[-1]
    assert blok["tytul"] == "Zero trafień"
    liczby = blok["liczby"]
    assert isinstance(liczby, dict)
    assert liczby["trafien"] == 0 and liczby["w_korpusie"] > 0


class _MagazynZNieczytelnym:
    """Atrapa `Store` na jedną metodę: bieżąca wersja `zly` nie jest JSON-em, `dobry` jest."""

    pokazowa = False

    def __init__(self) -> None:
        dobry = (Path(__file__).parent / "examples" / "atlas").glob("dokument_*.json")
        self._dobry = next(iter(sorted(dobry))).read_bytes()

    def iter_documents(self, filtr: object) -> Iterator[Dokument]:
        for doc_id, bajty in (("atlas:zly", b"{urwany"), ("atlas:dobry", self._dobry)):
            yield Dokument(doc_id, "atlas", doc_id[6:], (), None, "a" * 64, "2026", bajty)


def test_nieczytelna_wersja_zostawia_trafienie_bez_zrodla_zamiast_wywracac_wynik() -> None:
    """Wersja, której nie da się odczytać, jest w modelu legalna (reguła 19), a jej stary wiersz
    FTS zostaje trafieniem. Wywrócenie całego `szukaj --json` z jej powodu odebrałoby agentowi
    pozostałe trafienia; puste pola mówią to samo głośno i są opisane w `dla-modelu.md`."""
    magazyn = _MagazynZNieczytelnym()

    wpisy = obsluga.wpisy_trafien(magazyn, Filtr(), ["atlas:zly", "atlas:dobry"])  # type: ignore[arg-type]

    assert set(wpisy) == {"atlas:dobry"}
    assert obsluga._zrodlo_wpisu(wpisy.get("atlas:zly")) == ("", "")
