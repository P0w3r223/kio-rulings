"""Wiersz poleceń od strony operatora: kody wyjścia, zdania z `ui/texts.py`, baza poza drzewem.

`CliRunner` uruchamia prawdziwe `cli.pobierz`, a atrapa transportu wchodzi tam, gdzie wchodzi
w produkcji — w `pipeline.build_http_client` — więc polecenie jedzie całą drogą od flagi do
wiersza w bazie. Skan reguły 9 (`cli.py` nie drukuje sam) mieszka w `test_boundaries.py`; tu
stoi druga połowa tego zdania: to, co operator widzi, pochodzi z `texts`.
"""

from __future__ import annotations

import json
import sqlite3
from functools import partial
from pathlib import Path

import httpx
import pytest
from typer import rich_utils
from typer.testing import CliRunner

from kio_tool import cli, pipeline
from kio_tool.cli import app
from kio_tool.config import CONTACT_ENV, default_db_path, default_output_dir
from kio_tool.errors import KOD_WYJSCIA_PRZERWANIE
from kio_tool.exporter import FORMATY
from kio_tool.httpclient import build_http_client
from kio_tool.ui import texts
from tests.test_pipeline import KLUCZ, KONTRAKT, LISTA, MA_WIECEJ, Serwer, strona
from tests.test_store import baza_schematu_1
from tests.wsparcie_sondy import ZegarTestowy

POLECENIA = ("pobierz", "wznow", "eksportuj", "runy", "przelicz", "szukaj")

FLAGI_WYMAGANE: dict[str, tuple[str, ...]] = {
    "pobierz": ("--od", "2024-01-01", "--do", "2024-01-31"),
    "wznow": (),
    "eksportuj": ("--run-id", "atlas-x"),
    "runy": (),
    "przelicz": (),
    "szukaj": ("--fraza", "x"),
}
"""Najmniejszy zestaw flag, przy którym polecenie dochodzi do otwarcia bazy — po jednym na
polecenie z `POLECENIA`, żeby test przerwania mógł je przejść wszystkie tą samą drogą."""

ROOT = Path(__file__).resolve().parent.parent
runner = CliRunner()


@pytest.fixture(autouse=True)
def _zegar_sterowany(monkeypatch: pytest.MonkeyPatch) -> None:
    """Limiter trzyma odstęp 1 s z kontraktu Atlasu; sto żądań atrapy nie ma prawa kosztować
    stu sekund suity. `cli` buduje jeden zegar i to jest jedyne miejsce do podstawienia."""
    monkeypatch.setattr(cli, "SystemClock", ZegarTestowy)


@pytest.fixture(autouse=True)
def _konsola_powtarzalna(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trzy pułapki konsoli `rich` pod `CliRunner`, przeniesione z `ceidg-tool` razem z powodami.

    Szerokość przypięta, żeby asercje o **treści** komunikatów nie mierzyły przy okazji
    szerokości maszyny — w `ceidg-tool` ten sam brak wywrócił pięć testów na pierwszym przebiegu
    CI. Konsole `cli.view` powstają na poziomie modułu, ale `rich` czyta `COLUMNS` z `os.environ`
    przy każdym pomiarze, więc `setenv` je dosięga. Kolor wyłączony, bo `rich` koloruje **nazwę
    opcji**, rozbijając ją sekwencjami ANSI: przy włączonym kolorze `"--zgoda" in output` jest
    fałszem, choć flaga jest na ekranie; `NO_COLOR` nie przebija `FORCE_COLOR`, `TERM=dumb`
    przebija. Pomocy `--help` nie rysuje `cli.view`, tylko własna konsola typera — dlatego
    `rich_utils.MAX_WIDTH`, a nie tylko `COLUMNS`.
    """
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setattr(rich_utils, "MAX_WIDTH", 200)


@pytest.fixture
def baza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTACT_ENV, "test@example.org")
    monkeypatch.delenv("KIO_TOOL_ATLAS_KEY", raising=False)
    return tmp_path / "korpus.sqlite"


def podstaw(monkeypatch: pytest.MonkeyPatch, serwer: Serwer) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_http_client",
        partial(build_http_client, transport=httpx.MockTransport(serwer)),
    )


def pobierz(baza: Path, *dodatkowe: str) -> tuple[int, str]:
    wynik = runner.invoke(
        app,
        ["pobierz", "--od", "2024-01-01", "--do", "2024-01-31", "--baza", str(baza), *dodatkowe],
    )
    return wynik.exit_code, wynik.output


def dokumentow(baza: Path) -> int:
    with sqlite3.connect(baza) as polaczenie:
        return int(polaczenie.execute("SELECT COUNT(*) FROM documents").fetchone()[0])


def test_pomoc_nie_wysyla_niczego_i_wymienia_polecenie() -> None:
    wynik = runner.invoke(app, ["--help"])

    assert wynik.exit_code == 0
    assert "pobierz" in wynik.output


def test_bez_adresu_kontaktowego_odmawia_kodem_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CONTACT_ENV, raising=False)
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    kod, wyjscie = pobierz(tmp_path / "k.sqlite", "--zgoda")

    assert kod == 3
    assert CONTACT_ENV in wyjscie
    assert serwer.zadania == [], "bez tożsamości klienta nic nie wychodzi"


@pytest.mark.parametrize(
    "flagi",
    [("--od", "2024-13-01", "--do", "2024-01-31"), ("--od", "2024-02-01", "--do", "2024-01-31")],
    ids=["zla_data", "zakres_odwrocony"],
)
def test_zla_data_albo_odwrocony_zakres_to_blad_konfiguracji(
    baza: Path, monkeypatch: pytest.MonkeyPatch, flagi: tuple[str, ...]
) -> None:
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    wynik = runner.invoke(app, ["pobierz", *flagi, "--baza", str(baza), "--zgoda"])

    assert wynik.exit_code == 3
    assert serwer.zadania == []


def test_bez_zgody_przebieg_masowy_konczy_sie_kodem_3_i_sladem(
    baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    podstaw(monkeypatch, Serwer())

    kod, wyjscie = pobierz(baza)

    assert kod == 3
    assert "--zgoda" in wyjscie
    assert dokumentow(baza) == 0


def test_ze_zgoda_przebieg_zapisuje_korpus_i_wypisuje_rachunek(
    baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    podstaw(monkeypatch, Serwer())

    kod, wyjscie = pobierz(baza, "--zgoda")

    assert kod == 0, wyjscie
    assert dokumentow(baza) == 100
    assert "102" in wyjscie, "rachunek żądań wypisany, nie zostawiony do policzenia"
    assert str(baza) in wyjscie


def test_ctrl_c_konczy_sie_kodem_130_i_zdaniem_o_wznowieniu(
    baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    podstaw(monkeypatch, Serwer(przerwij_na_dokumencie=3))

    kod, wyjscie = pobierz(baza, "--zgoda")

    assert kod == KOD_WYJSCIA_PRZERWANIE
    assert texts.PRZERWANE in wyjscie
    assert dokumentow(baza) == 2


def test_wznowienie_tym_samym_poleceniem_dopelnia_korpus(
    baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    podstaw(monkeypatch, Serwer(przerwij_na_dokumencie=3))
    pobierz(baza, "--zgoda")
    podstaw(monkeypatch, Serwer())

    kod, _ = pobierz(baza, "--zgoda")

    assert kod == 0
    assert dokumentow(baza) == 100


def test_maly_zakres_nie_wymaga_zgody(baza: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    podstaw(monkeypatch, Serwer([strona(LISTA[KLUCZ][:2], ma_wiecej=False, total=2)]))

    kod, _ = pobierz(baza)

    assert kod == 0 and dokumentow(baza) == 2


def test_nieznany_kanal_to_blad_konfiguracji(baza: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    podstaw(monkeypatch, Serwer())

    kod, wyjscie = pobierz(baza, "--zgoda", "--kanal", "saos")

    assert kod == 3 and "atlas" in wyjscie


def test_domyslna_baza_lezy_poza_repozytorium() -> None:
    """Korpus nie wchodzi do historii (`.gitignore`, nazwiska składu) — domyślna ścieżka nie ma
    prawa wskazywać do drzewa źródłowego."""
    sciezka = default_db_path()

    assert ROOT not in sciezka.parents and sciezka != ROOT
    assert sciezka.name.endswith(".sqlite")


def test_zdania_na_ekranie_pochodza_z_texts(baza: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Druga połowa reguły 9: każdy wiersz podsumowania jest wierszem zdania z `ui/texts.py`."""
    podstaw(monkeypatch, Serwer([strona(LISTA[KLUCZ][:1], ma_wiecej=False, total=1)]))

    kod, wyjscie = pobierz(baza)

    assert kod == 0
    for wiersz in texts.podsumowanie(
        run_id="x", status="zakonczony", kandydatow=1, nowych=1, pominietych=0, zadan=2, baza="b"
    ).splitlines()[1:3]:
        rdzen = wiersz.split(":")[0]
        assert rdzen in wyjscie, f"wiersz podsumowania `{rdzen}` nie trafił na ekran"


def test_material_listy_jest_zlotym_plikiem_a_nie_kopia() -> None:
    """Antypustka: test CLI jedzie na tym samym złotym pliku co adapter i potok."""
    assert LISTA[MA_WIECEJ] is True
    assert json.dumps(LISTA[KLUCZ][0])


# --- pomoc i mapa poleceń ------------------------------------------------------------------------


@pytest.mark.parametrize("polecenie", POLECENIA)
def test_pomoc_kazdego_polecenia_wymienia_jego_flagi_z_texts(polecenie: str) -> None:
    wynik = runner.invoke(app, [polecenie, "--help"])

    assert wynik.exit_code == 0, wynik.output
    assert "--baza" in wynik.output
    assert texts.POMOC_BAZA[:30] in wynik.output


def test_pomoc_programu_wymienia_wszystkie_polecenia() -> None:
    wynik = runner.invoke(app, ["--help"])

    assert all(p in wynik.output for p in POLECENIA)


# --- pobierz: kryteria, eksport, diagnoza --------------------------------------------------------


def test_pobierz_bez_kryteriow_odmawia_bez_zadania(
    baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    wynik = runner.invoke(app, ["pobierz", "--baza", str(baza), "--zgoda"])

    assert wynik.exit_code == 3 and "Brak kryteriów" in wynik.output
    assert serwer.zadania == []


def test_pobierz_eksportuje_do_out_w_podanych_formatach(
    baza: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer([strona(LISTA[KLUCZ][:3], ma_wiecej=False, total=3)]))
    out = tmp_path / "wynik" / "styczen"

    kod, wyjscie = pobierz(baza, "--format", "xlsx,jsonl,md", "--out", str(out), "--cel", "test")

    assert kod == 0, wyjscie
    assert (out.parent / "styczen.xlsx").is_file()
    assert (out.parent / "styczen.jsonl").is_file()
    assert (out.parent / "styczen_md" / "INDEX.md").is_file()
    assert "Eksport zapisany" in wyjscie and "styczen.xlsx" in wyjscie


def test_pobierz_z_fraza_i_maks_wysyla_filtr_z_kontraktu(
    baza: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    wynik = runner.invoke(
        app,
        [
            "pobierz",
            "--fraza",
            "oferta",
            "--maks",
            "3",
            "--baza",
            str(baza),
            "--out",
            str(tmp_path / "f"),
        ],
    )

    assert wynik.exit_code == 0, wynik.output
    lista = next(z for z in serwer.zadania if z.url.path == KONTRAKT.punkty.lista)
    assert lista.url.params[KONTRAKT.parametry_listy.filtry["fraza"]] == "oferta"
    assert dokumentow(baza) == 3


def test_pobierz_z_nieznanym_formatem_odmawia_kodem_3(
    baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serwer = Serwer()
    podstaw(monkeypatch, serwer)

    kod, wyjscie = pobierz(baza, "--zgoda", "--format", "zip")

    assert kod == 3 and "zip" in wyjscie and serwer.zadania == []


def test_pobierz_ostrzega_o_wartosci_spoza_listy_zmierzonej(
    baza: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer([strona(LISTA[KLUCZ][:1], ma_wiecej=False, total=1)]))

    kod, wyjscie = pobierz(baza, "--rozstrzygniecie", "uwzględniono", "--out", str(tmp_path / "o"))

    assert kod == 0, wyjscie
    assert "Uwaga:" in wyjscie and "uwzgledniono" in wyjscie


def test_pobierz_bez_kandydatow_diagnozuje_zamiast_eksportowac(
    baza: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer([strona([], ma_wiecej=False, total=0)]))

    kod, wyjscie = pobierz(baza, "--fraza", "nic", "--out", str(tmp_path / "z"))

    assert kod == 0, wyjscie
    assert "nie zwrócił żadnego kandydata" in wyjscie
    assert not list(tmp_path.glob("z*")), "bez kandydatów nie powstaje żaden plik eksportu"


# --- runy, wznow --------------------------------------------------------------------------------


def test_runy_na_pustej_bazie_mowi_ze_nic_nie_ma(baza: Path) -> None:
    wynik = runner.invoke(app, ["runy", "--baza", str(baza)])

    assert wynik.exit_code == 0 and texts.BRAK_PRZEBIEGOW in wynik.output


def test_runy_pokazuje_przebieg_z_liczbami_i_filtruje_po_statusie(
    baza: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer(przerwij_na_dokumencie=3))
    pobierz(baza, "--zgoda", "--out", str(tmp_path / "r"))
    run_id = sqlite3.connect(baza).execute("SELECT run_id FROM runs").fetchone()[0]

    wszystkie = runner.invoke(app, ["runy", "--baza", str(baza)])
    przerwane = runner.invoke(app, ["runy", "--baza", str(baza), "--status", "przerwany"])
    zakonczone = runner.invoke(app, ["runy", "--baza", str(baza), "--status", "zakonczony"])
    zly = runner.invoke(app, ["runy", "--baza", str(baza), "--status", "gotowe"])

    assert run_id in wszystkie.output and "pokazano 1 z 1" in wszystkie.output
    assert run_id in przerwane.output
    assert run_id not in zakonczone.output and "pokazano 0 z 1" in zakonczone.output
    assert zly.exit_code == 3 and "gotowe" in zly.output


def test_wznow_dokancza_przerwany_przebieg_i_eksportuje(
    baza: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    podstaw(monkeypatch, Serwer(przerwij_na_dokumencie=3))
    pobierz(baza, "--zgoda", "--out", str(tmp_path / "p"))
    podstaw(monkeypatch, Serwer())

    wynik = runner.invoke(
        app, ["wznow", "--baza", str(baza), "--zgoda", "--out", str(tmp_path / "w")]
    )

    assert wynik.exit_code == 0, wynik.output
    assert "Wznawiam przebieg" in wynik.output and dokumentow(baza) == 100
    assert (tmp_path / "w.xlsx").is_file()


def test_wznow_bez_przerwanego_przebiegu_konczy_sie_kodem_3(baza: Path) -> None:
    wynik = runner.invoke(app, ["wznow", "--baza", str(baza), "--zgoda"])

    assert wynik.exit_code == 3 and "nie ma czego wznawiać" in wynik.output


# --- eksportuj, przelicz, szukaj — bez sieci -----------------------------------------------------


@pytest.fixture
def korpus(baza: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, str]:
    """Baza ze stu dokumentami z jednego przebiegu; potem fabryka klienta jest zabroniona."""
    podstaw(monkeypatch, Serwer())
    kod, _ = pobierz(baza, "--zgoda", "--out", str(tmp_path / "korpus"))
    assert kod == 0
    run_id = sqlite3.connect(baza).execute("SELECT run_id FROM runs").fetchone()[0]

    def zabroniona(**_: object) -> httpx.Client:
        raise AssertionError("polecenie bez sieci zbudowało klienta HTTP")

    monkeypatch.setattr(pipeline, "build_http_client", zabroniona)
    return baza, run_id


def test_eksportuj_po_run_id_zapisuje_kazdy_format_bez_sieci(
    korpus: tuple[Path, str], tmp_path: Path
) -> None:
    baza, run_id = korpus

    wynik = runner.invoke(
        app,
        [
            "eksportuj",
            "--run-id",
            run_id,
            "--baza",
            str(baza),
            "--format",
            ",".join(FORMATY),
            "--out",
            str(tmp_path / "e"),
        ],
    )

    assert wynik.exit_code == 0, wynik.output
    assert "dokumentów w eksporcie" in wynik.output and "100" in wynik.output
    assert (tmp_path / "e.xlsx").is_file() and (tmp_path / "e.csv").is_file()
    assert (tmp_path / "e.jsonl").is_file() and (tmp_path / "e_md" / "INDEX.md").is_file()


def test_eksportuj_po_kryteriach_i_odmowa_bez_zakresu(
    korpus: tuple[Path, str], tmp_path: Path
) -> None:
    baza, _ = korpus

    po_frazie = runner.invoke(
        app,
        [
            "eksportuj",
            "--fraza",
            "tresc wymyslona",
            "--baza",
            str(baza),
            "--out",
            str(tmp_path / "k"),
        ],
    )
    bez = runner.invoke(app, ["eksportuj", "--baza", str(baza)])
    puste = runner.invoke(app, ["eksportuj", "--fraza", "nic takiego", "--baza", str(baza)])

    assert po_frazie.exit_code == 0 and (tmp_path / "k.xlsx").is_file()
    assert bez.exit_code == 3 and "--run-id" in bez.output
    assert puste.exit_code == 0 and "Zero trafień" in puste.output


def test_przelicz_odtwarza_indeks_i_raportuje_liczby(korpus: tuple[Path, str]) -> None:
    baza, _ = korpus
    with sqlite3.connect(baza) as p:
        p.execute("DELETE FROM metadata")
        p.execute("DELETE FROM fts")

    wynik = runner.invoke(app, ["przelicz", "--baza", str(baza)])

    assert wynik.exit_code == 0, wynik.output
    assert "przeliczonych wersji" in wynik.output and "100" in wynik.output


def test_szukaj_pokazuje_tabele_z_liczbami_nad_nia(korpus: tuple[Path, str]) -> None:
    baza, _ = korpus

    wynik = runner.invoke(
        app, ["szukaj", "--fraza", "tresc wymyslona", "--limit", "3", "--baza", str(baza)]
    )

    assert wynik.exit_code == 0, wynik.output
    assert (
        "W korpusie: 100 dokumentów, zaindeksowanych: 100, trafień: 100, pokazano: 3."
        in wynik.output
    )
    assert "sygnatura" in wynik.output and "fragment" in wynik.output


def test_szukaj_bez_trafien_diagnozuje_a_bez_frazy_odmawia(korpus: tuple[Path, str]) -> None:
    baza, _ = korpus

    zero = runner.invoke(
        app,
        ["szukaj", "--fraza", "nic takiego", "--rozstrzygniecie", "oddalono", "--baza", str(baza)],
    )
    bez_frazy = runner.invoke(app, ["szukaj", "--baza", str(baza)])

    assert zero.exit_code == 0 and "Zero trafień" in zero.output
    assert "Spróbuj bez pola „rozstrzygnięcie”" in zero.output
    assert bez_frazy.exit_code == 3 and "--fraza" in bez_frazy.output


def test_domyslny_katalog_wynikow_lezy_poza_repozytorium() -> None:
    katalog = default_output_dir()

    assert ROOT not in katalog.parents and katalog != ROOT


# --- Ctrl+C: każde polecenie kończy się kodem 130 -----------------------------------------------


@pytest.mark.parametrize("polecenie", POLECENIA)
def test_ctrl_c_w_kazdym_poleceniu_konczy_sie_kodem_130_i_zdaniem(
    polecenie: str, baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reguła kodów wyjścia z nagłówka `cli.py` — dla **każdego** polecenia, nie tylko `pobierz`.

    Ctrl+C jest sygnałem, nie wyjątkiem `KioError`, więc łapie go osobna gałąź `_obsluga_bledow`.
    Polecenie dopisane bez `with _obsluga_bledow()` wychodziłoby ze śladem stosu i kodem 1 —
    a operator, który przerwał długi przebieg, ma zobaczyć zdanie o wznowieniu, nie traceback.
    Punktem przerwania jest otwarcie bazy, bo to jedyne miejsce wspólne dla wszystkich sześciu;
    sprawdzana własność jest własnością opakowania, nie tego konkretnego wywołania.
    """

    class BazaPrzerwana:
        @staticmethod
        def open(*_a: object, **_k: object) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "Store", BazaPrzerwana)

    wynik = runner.invoke(app, [polecenie, *FLAGI_WYMAGANE[polecenie], "--baza", str(baza)])

    assert wynik.exit_code == KOD_WYJSCIA_PRZERWANIE, wynik.output
    assert texts.PRZERWANE in wynik.output


# --- eksport przebiegu sprzed migracji schematu 1 → 2 -------------------------------------------


def test_eksportuj_odmawia_run_id_i_kryteriow_naraz(tmp_path: Path) -> None:
    """Przegląd kodu 2026-09-18 (LOW), poprawione tego samego dnia: oba naraz gubiły kryteria po
    cichu — eksport całych przebiegów bez słowa o zignorowanych datach."""
    wynik = runner.invoke(
        app,
        [
            "eksportuj",
            "--run-id",
            "atlas-x",
            "--od",
            "2024-01-01",
            "--do",
            "2024-01-31",
            "--baza",
            str(tmp_path / "b.sqlite"),
        ],
    )

    assert wynik.exit_code == 3, wynik.output
    assert "nie jedno i drugie" in wynik.output


def test_eksportuj_przebiegu_sprzed_migracji_mowi_dlaczego_nic_nie_wychodzi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Znalezisko testera 2026-09-18, zmierzone na prawdziwej bazie operatora, zgłoszone jako
    `xfail(strict=True)` i **poprawione tego samego dnia** (`texts.przebieg_bez_powiazan`,
    wołane w `cli._eksport_i_raport` dla przebiegu z żądaniami i bez powiązań); znacznik zdjęty
    razem z poprawką. Schemat 1 nie miał tabeli `run_documents`, migracja tworzy ją pustą, więc
    „żaden dokument nie pasuje" było prawdziwe i mylące naraz — tamten przebieg objął 295
    dokumentów. Operator ma się dowiedzieć **dlaczego** i dostać drogę zapasową (`--od/--do`);
    backfill z `requests_log` zostaje decyzją właściciela."""
    monkeypatch.setenv(CONTACT_ENV, "test@example.org")
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1(sciezka)

    wynik = runner.invoke(
        app,
        [
            "eksportuj",
            "--run-id",
            "atlas-stary",
            "--baza",
            str(sciezka),
            "--out",
            str(tmp_path / "s"),
        ],
    )

    assert wynik.exit_code == 0, wynik.output
    assert "--od" in wynik.output and "--do" in wynik.output, (
        "eksport przebiegu sprzed schematu 2 kończy się zdaniem „żaden dokument nie pasuje”, "
        "a dokumenty tego przebiegu są w korpusie — brakuje drogi zapasowej, którą `wznow` "
        "przy tym samym przebiegu nazywa wprost (`do_wznowienia`: „Uruchom `pobierz` z tym "
        "zakresem dat”)"
    )


def test_przebieg_sprzed_migracji_ma_dokumenty_w_korpusie_i_zero_w_run_documents(
    tmp_path: Path,
) -> None:
    """Antypustka dla `xfail` wyżej: gdyby baza schematu 1 nie miała dokumentu albo gdyby
    migracja wypełniała `run_documents`, tamten test mierzyłby coś innego, niż mówi."""
    sciezka = tmp_path / "stary.sqlite"
    baza_schematu_1(sciezka)

    with cli.Store.open(sciezka, clock=ZegarTestowy()) as store:
        assert store.count("documents") == 1
        assert store.count_run_documents("atlas-stary") == 0
        assert store.count_requests("atlas-stary") == 1, (
            "ślad po żądaniach przebiegu **jest** w bazie — to z niego dałby się odtworzyć "
            "`run_documents`, gdyby właściciel wybrał backfill"
        )


def test_ponowienie_widac_na_ekranie_i_w_podsumowaniu(
    baza: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0007 Z-7 od strony operatora: zdanie o ponowieniu w trakcie i liczba na końcu —
    oba przez `cli` i konsolę, nie tylko w `Podsumowanie`."""
    serwer = Serwer(
        [strona(LISTA[KLUCZ][:3], ma_wiecej=False, total=3)],
        przerwij_na_dokumencie=2,
        wyjatek=httpx.ConnectError("siec znikla (wymyslone)"),
    )
    podstaw(monkeypatch, serwer)

    kod, wyjscie = pobierz(baza)

    assert kod == 0, wyjscie
    assert "zerwane łącze (ConnectError), próba 2 z 3" in wyjscie
    assert "Ponowień w całym przebiegu (z bazy): 1" in wyjscie
    assert dokumentow(baza) == 3
