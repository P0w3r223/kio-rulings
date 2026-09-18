"""Przewidywalne pomyłki osoby bez doświadczenia: co widzi na ekranie i z jakim kodem wyjścia.

Sprawdzana własność jest zawsze ta sama i jest to własność z doktryny („cisza jest usterką"):
po pomyłce ma paść **zdanie po polsku o tym, co się stało i co zrobić dalej**, a kod wyjścia ma
być niezerowy. Ślad stosu nie jest zdaniem, a pusty ekran nie jest odpowiedzią.

Siedem testów powstało 2026-09-18 jako znaleziska (`xfail(strict=True)`): ślad stosu przy złej
`--baza`, kod 1 i zero wskazówki przy literówce w `--run-id`, zero trafień milczące o pustym
korpusie, zgubiona liczba dokumentów bez daty, `--out` na katalog zapisujący obok, `runy` z
niedodatnim limitem, próg zgody bez zdania o zapisanym przebiegu. Wszystkie naprawione tego
samego dnia i testy mierzą od tej pory zachowanie docelowe.

Sieć nie wychodzi nigdzie: `pobierz` jedzie na atrapie transportu z `tests/test_pipeline.py`, a
pozostałe pięć poleceń nie buduje klienta HTTP. Każde wywołanie dostaje jawne `--baza` i `--out`
pod `tmp_path`, bo piaskownica z `conftest.py` porównuje stan prawdziwego korpusu przed i po.
"""

from __future__ import annotations

import copy
import sqlite3
from functools import partial
from pathlib import Path

import httpx
import pytest
from typer import rich_utils
from typer.testing import CliRunner

from kio_tool import cli, pipeline
from kio_tool.cli import app
from kio_tool.config import CONTACT_ENV
from kio_tool.criteria import Criteria
from kio_tool.httpclient import build_http_client
from kio_tool.store import Store
from kio_tool.ui import texts
from tests.test_pipeline import KLUCZ, LISTA, Serwer, strona
from tests.wsparcie_sondy import ZegarTestowy

runner = CliRunner()
ZAKRES = ("--od", "2024-01-01", "--do", "2024-01-31")


@pytest.fixture(autouse=True)
def _srodowisko_operatora(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zegar sterowany (odstęp limitera nie ma kosztować suity sekundami), konsola powtarzalna
    i adres kontaktowy ustawiony — brak adresu jest tu osobną pomyłką, testowaną wprost."""
    monkeypatch.setattr(cli, "SystemClock", ZegarTestowy)
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setattr(rich_utils, "MAX_WIDTH", 200)
    monkeypatch.setenv(CONTACT_ENV, "test@example.org")


def podstaw(monkeypatch: pytest.MonkeyPatch, serwer: Serwer) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_http_client",
        partial(build_http_client, transport=httpx.MockTransport(serwer)),
    )


@pytest.fixture
def korpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Baza z dwoma dokumentami z jednego zakończonego przebiegu — stan po pierwszym `pobierz`.

    Rekordy listy idą ze złotego pliku z pomiaru 3a z **wyzerowaną datą wydania** i to jest tu
    materiałem, nie niedopatrzeniem: u pośrednika data bywa pusta albo błędna (README, „Pliki
    wynikowe"; architektura 4.8), więc korpus, w którym filtr dat nie widzi części dokumentów,
    jest realnym stanem u operatora, a nie przypadkiem laboratoryjnym.
    """
    rekordy = copy.deepcopy(LISTA[KLUCZ][:2])
    for rekord in rekordy:
        rekord["ruling_date"] = None
    podstaw(monkeypatch, Serwer([strona(rekordy, ma_wiecej=False, total=2)]))
    baza = tmp_path / "korpus.sqlite"
    wynik = runner.invoke(
        app, ["pobierz", *ZAKRES, "--baza", str(baza), "--out", str(tmp_path / "pierwszy")]
    )
    assert wynik.exit_code == 0, wynik.output
    monkeypatch.setattr(pipeline, "build_http_client", _bez_sieci)
    return baza


def _bez_sieci(**_: object) -> httpx.Client:
    raise AssertionError("polecenie bez sieci zbudowało klienta HTTP")


def run_id(baza: Path) -> str:
    with sqlite3.connect(baza) as polaczenie:
        return str(polaczenie.execute("SELECT run_id FROM runs").fetchone()[0])


def dokumentow(baza: Path) -> int:
    with sqlite3.connect(baza) as polaczenie:
        return int(polaczenie.execute("SELECT COUNT(*) FROM documents").fetchone()[0])


# --- adres kontaktowy: kogo dotyczy, a kogo nie -------------------------------------------------


def test_wznow_bez_adresu_kontaktowego_odmawia_i_nazywa_zmienna(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pobierz` bez `KIO_TOOL_CONTACT` ma swój test w `test_cli.py`; `wznow` wysyła żądania tak
    samo i tak samo ma odmówić — zdaniem z nazwą zmiennej, nie śladem stosu."""
    monkeypatch.delenv(CONTACT_ENV, raising=False)

    wynik = runner.invoke(app, ["wznow", "--baza", str(tmp_path / "k.sqlite"), "--zgoda"])

    assert wynik.exit_code == 3, wynik.output
    assert CONTACT_ENV in wynik.output


@pytest.mark.parametrize(
    "polecenie",
    [("runy",), ("przelicz",), ("szukaj", "--fraza", "tresc")],
    ids=["runy", "przelicz", "szukaj"],
)
def test_polecenia_bez_sieci_dzialaja_bez_adresu_kontaktowego(
    korpus: Path, monkeypatch: pytest.MonkeyPatch, polecenie: tuple[str, ...]
) -> None:
    """Odwrotna strona reguły 16: adres kontaktowy jest ceną **wysłania żądania**, a nie ceną
    czytania własnego korpusu. Wymaganie go w `szukaj` zatrzymywałoby operatora przed pracą
    z danymi, które już ma na dysku."""
    monkeypatch.delenv(CONTACT_ENV, raising=False)

    wynik = runner.invoke(app, [*polecenie, "--baza", str(korpus)])

    assert wynik.exit_code == 0, wynik.output
    assert CONTACT_ENV not in wynik.output


def test_eksport_dziala_bez_adresu_kontaktowego(
    korpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """To samo dla `eksportuj`, ale z zapisem pliku — polecenie bez sieci ma dojść do końca
    i powiedzieć, gdzie leży wynik, bez zmiennej środowiskowej dla żądań, których nie wysyła."""
    monkeypatch.delenv(CONTACT_ENV, raising=False)
    out = tmp_path / "bez_adresu"

    wynik = runner.invoke(
        app, ["eksportuj", "--run-id", run_id(korpus), "--baza", str(korpus), "--out", str(out)]
    )

    assert wynik.exit_code == 0, wynik.output
    assert out.with_name("bez_adresu.xlsx").is_file()
    assert "bez_adresu.xlsx" in wynik.output, "podsumowanie nie mówi, gdzie leży wynik"


# --- ścieżka bazy wskazana po omacku ------------------------------------------------------------


def test_nowa_sciezka_bazy_zaklada_baze_zamiast_odmawiac(tmp_path: Path) -> None:
    """Ścieżka, której jeszcze nie ma, jest normalnym pierwszym uruchomieniem — baza ma powstać
    razem z katalogiem, a nie kończyć się błędem „nie ma takiego pliku"."""
    baza = tmp_path / "nowy" / "katalog" / "korpus.sqlite"

    wynik = runner.invoke(app, ["runy", "--baza", str(baza)])

    assert wynik.exit_code == 0, wynik.output
    assert texts.BRAK_PRZEBIEGOW in wynik.output
    assert baza.is_file()


@pytest.mark.parametrize("rodzaj", ["katalog", "plik_nie_bazy"])
def test_baza_ktora_nie_jest_baza_konczy_sie_zdaniem_a_nie_sladem_stosu(
    tmp_path: Path, rodzaj: str
) -> None:
    """`--baza` wskazane na katalog (np. na `wyniki\\`) albo na plik, który bazą nie jest (np. na
    skoroszyt eksportu) — obie pomyłki są o jedno dopełnienie ścieżki od poprawnej.

    Do 2026-09-18 obie kończyły się wyjątkiem `sqlite3` przepuszczonym przez
    `cli._obsluga_bledow` (ślad stosu z `unable to open database file` albo `file is not
    a database`). `store.blad_bazy` zamienia je na `ConfigError` ze ścieżką i wskazówką — kod 3,
    jak każda pomyłka w wywołaniu (przegląd kodu 2026-09-18 przypiął kod, nie samą niezerowość).
    """
    cel = tmp_path / "cel"
    if rodzaj == "katalog":
        cel.mkdir()
    else:
        cel.write_text("to nie jest baza, to notatka", encoding="utf-8")

    wynik = runner.invoke(app, ["runy", "--baza", str(cel)])

    assert wynik.exit_code == 3, wynik.output
    assert texts.blad("").strip() in wynik.output, "błąd bazy nie dostał zdania dla operatora"
    assert str(cel) in wynik.output, "zdanie o błędzie nie mówi, która ścieżka jest zła"


# --- nieistniejący `--run-id` -------------------------------------------------------------------


@pytest.mark.parametrize("polecenie", ["eksportuj", "wznow"])
def test_nieistniejacy_run_id_kieruje_do_polecenia_runy(korpus: Path, polecenie: str) -> None:
    """Identyfikator przebiegu jest napisem przepisywanym z ekranu (`atlas-969ac406dd8f`), więc
    literówka jest pomyłką spodziewaną, nie wyjątkową.

    Do 2026-09-18 `store.get_run` rzucał `StoreError` — kod wyjścia 1 („błąd nieodwracalny"),
    choć to jest pomyłka w wywołaniu, czyli kod 3; a zdanie „Nie ma przebiegu 'atlas-x'." nie
    mówiło, że listę przebiegów wypisuje `runy`. Od tego dnia `errors.RunNotFoundError` niesie
    kod 3 i wskazówkę, a `pipeline.eksportuj` sprawdza przebiegi przed pierwszym zdaniem
    o wyniku.
    """
    wynik = runner.invoke(app, [polecenie, "--run-id", "atlas-literowka", "--baza", str(korpus)])

    assert wynik.exit_code == 3, "literówka w identyfikatorze jest błędem wywołania, nie awarią"
    assert "runy" in wynik.output, "komunikat nie mówi, skąd wziąć poprawny identyfikator"


def test_wznow_zakonczonego_przebiegu_mowi_o_jego_statusie(korpus: Path) -> None:
    """Operator wznawia po numerze z `runy`, nie patrząc na kolumnę statusu. Odmowa ma nazwać
    powód — status przebiegu — a nie milczeć ani nie wysyłać żądań drugi raz."""
    wynik = runner.invoke(app, ["wznow", "--run-id", run_id(korpus), "--baza", str(korpus)])

    assert wynik.exit_code == 3, wynik.output
    assert "zakonczony" in wynik.output and "przerwany" in wynik.output


# --- pusty korpus -------------------------------------------------------------------------------


def test_przelicz_na_pustej_bazie_konczy_sie_zerami_bez_bledu(tmp_path: Path) -> None:
    """`przelicz` na świeżej bazie nie jest pomyłką, tylko niczym — i ma się tak skończyć: kod 0
    i cztery zera, bez „przeliczonych 0" ubranego w błąd."""
    wynik = runner.invoke(app, ["przelicz", "--baza", str(tmp_path / "pusta.sqlite")])

    assert wynik.exit_code == 0, wynik.output
    assert "dokumentów w korpusie" in wynik.output


@pytest.mark.parametrize(
    "polecenie",
    [("szukaj", "--fraza", "odrzucenie oferty"), ("eksportuj", "--fraza", "odrzucenie oferty")],
    ids=["szukaj", "eksportuj"],
)
def test_zero_trafien_na_pustej_bazie_mowi_ze_korpus_jest_pusty(
    tmp_path: Path, polecenie: tuple[str, ...]
) -> None:
    """Pierwsze, co robi osoba bez doświadczenia, to szukanie — zanim cokolwiek pobierze.

    Dostaje dziś „Zero trafień / To jedyny filtr — poszerz zakres dat albo sprawdź pisownię",
    czyli poradę dotyczącą kryteriów, podczas gdy prawdziwy powód jest inny: w bazie nie ma ani
    jednego dokumentu. `blok_wyszukiwania` wypisuje liczby korpusu zawsze (README: „nad tabelą
    zawsze"), `zero_trafien` — nigdy, gdy `zaindeksowanych == w_korpusie == 0`.
    """
    wynik = runner.invoke(
        app,
        [*polecenie, "--baza", str(tmp_path / "pusta.sqlite")]
        + (["--out", str(tmp_path / "e")] if polecenie[0] == "eksportuj" else []),
    )

    assert wynik.exit_code == 0, wynik.output
    assert "W korpusie" in wynik.output, "zero trafień nie mówi, ile dokumentów ma korpus"
    assert "pobierz" in wynik.output, "pusty korpus nie kieruje do polecenia, które go napełnia"


# --- filtr dat na dokumentach bez daty ----------------------------------------------------------


def test_liczba_dokumentow_bez_daty_jest_policzona_w_potoku(korpus: Path) -> None:
    """Antypustka dla testu niżej: potok **zna** liczbę dokumentów, które odpadły przez brak daty
    wydania. Gdyby jej nie liczył, tamten test mówiłby o czymś, czego nie ma."""
    with Store.open(korpus, clock=ZegarTestowy()) as store:
        wynik = pipeline.eksportuj(
            store,
            kryteria=Criteria.model_validate({"od": "2024-01-01", "do": "2024-01-31"}),
            zegar=ZegarTestowy(),
        )

    assert wynik.dokumentow == 0
    assert wynik.bez_daty_poza_filtrem == 2


def test_eksport_po_datach_mowi_ile_dokumentow_odpadlo_bez_daty(
    korpus: Path, tmp_path: Path
) -> None:
    """Zakres dat na korpusie, w którym data wydania bywa pusta — sytuacja opisana w README jako
    zmierzona (dziewięć z 295 dat błędnych u pośrednika w styczniu 2024).

    Przy niezerowym wyniku `blok_eksportu` wypisuje uwagę „Poza filtrem dat zostało N dokumentów
    bez daty wydania"; przy zerowym `cli._eksport_i_raport` schodzi gałęzią `NIC_DO_EKSPORTU`
    i tę samą liczbę — policzoną, dostępną w `WynikEksportu` — pomija. Operator widzi „żaden
    dokument nie pasuje" nad korpusem, który ma dokumenty pasujące do wszystkiego poza datą.
    """
    wynik = runner.invoke(
        app, ["eksportuj", *ZAKRES, "--baza", str(korpus), "--out", str(tmp_path / "daty")]
    )

    assert wynik.exit_code == 0, wynik.output
    assert "bez daty" in wynik.output, "zerowy eksport po datach milczy o dokumentach bez daty"


# --- `--out` wskazane obok celu -----------------------------------------------------------------


def test_out_wskazujacy_istniejacy_katalog_nie_zapisuje_obok_niego(
    korpus: Path, tmp_path: Path
) -> None:
    """Pomoc `--out` mówiła „ścieżka wyniku bez rozszerzenia; domyślnie katalog `wyniki/` obok
    bazy" — więc operator podawał katalog, bo o katalogu było w tym samym zdaniu, i dostawał plik
    **obok** niego (`wyniki.xlsx` przy pustym `wyniki\\`).

    Rozstrzygnięcie 2026-09-18: istniejący katalog dostaje plik o nazwie domyślnej **w środku**
    (`pipeline.eksportuj`), a pomoc flagi mówi o rdzeniu nazwy. Asercja mierzy to zachowanie,
    nie samą niezerowość kodu (przegląd kodu 2026-09-18: dysjunkcja przechodziła przy każdej
    awarii eksportu).
    """
    katalog = tmp_path / "wyniki"
    katalog.mkdir()

    wynik = runner.invoke(
        app, ["eksportuj", "--run-id", run_id(korpus), "--baza", str(korpus), "--out", str(katalog)]
    )

    assert wynik.exit_code == 0, wynik.output
    w_srodku = [p.name for p in katalog.iterdir()]
    assert len(w_srodku) == 1 and w_srodku[0].endswith(".xlsx"), "eksport minął wskazany katalog"
    assert not any(p.name.startswith("wyniki.") for p in tmp_path.iterdir()), "zapisał się obok"


def test_nieudany_zapis_eksportu_konczy_sie_zdaniem_ze_sciezka_a_korpus_zostaje(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zapis wyniku nie ma prawa się udać, gdy w miejscu pliku stoi katalog — a to jest kształt
    każdej odmowy systemu plików (brak uprawnień, plik zajęty, nośnik tylko do odczytu).

    Sprawdzane są trzy rzeczy naraz: kod niezerowy, zdanie ze ścieżką zamiast śladu stosu oraz to,
    że **pobrane dokumenty zostają w bazie** — bo inaczej operator powtórzy cudzemu serwisowi całe
    pobranie dla błędu, który dotyczył tylko zapisu pliku.
    """
    podstaw(monkeypatch, Serwer([strona(LISTA[KLUCZ][:2], ma_wiecej=False, total=2)]))
    baza = tmp_path / "korpus.sqlite"
    (tmp_path / "wynik.xlsx").mkdir()

    wynik = runner.invoke(
        app, ["pobierz", *ZAKRES, "--baza", str(baza), "--out", str(tmp_path / "wynik")]
    )

    assert wynik.exit_code == 1, wynik.output
    assert texts.blad("").strip() in wynik.output and "wynik.xlsx" in wynik.output
    assert dokumentow(baza) == 2, "korpus przepadł razem z nieudanym zapisem pliku"


# --- kryteria: postać daty, odwrócony zakres, brak frazy ----------------------------------------


@pytest.mark.parametrize("polecenie", ["eksportuj", "szukaj"])
def test_data_w_zlej_postaci_nazywa_pole_i_postac_w_kazdym_poleceniu(
    korpus: Path, polecenie: str
) -> None:
    """Sprawdzenie kryteriów siedzi w jednym miejscu, ale operator trafia na nie z sześciu stron;
    `test_cli.py` mierzy tylko `pobierz`. Zdanie ma nazwać pole (`od`) i postać (`RRRR-MM-DD`)."""
    wynik = runner.invoke(
        app, [polecenie, "--od", "01-01-2024", "--fraza", "x", "--baza", str(korpus)]
    )

    assert wynik.exit_code == 3, wynik.output
    assert "od" in wynik.output and "RRRR-MM-DD" in wynik.output


@pytest.mark.parametrize("polecenie", ["eksportuj", "szukaj"])
def test_zakres_dat_odwrocony_mowi_ktora_data_jest_ktora(korpus: Path, polecenie: str) -> None:
    """`--do` wcześniejsze niż `--od` daje pusty wynik przy każdej innej obsłudze; tu ma dać
    odmowę z obiema datami wypisanymi, żeby operator zobaczył, którą przestawił."""
    wynik = runner.invoke(
        app,
        [
            polecenie,
            "--od",
            "2024-02-01",
            "--do",
            "2024-01-31",
            "--fraza",
            "x",
            "--baza",
            str(korpus),
        ],
    )

    assert wynik.exit_code == 3, wynik.output
    assert "2024-02-01" in wynik.output and "2024-01-31" in wynik.output


def test_szukaj_z_samymi_filtrami_i_bez_frazy_nazywa_brakujaca_flage(korpus: Path) -> None:
    """Filtry bez frazy wyglądają jak komplet kryteriów (`eksportuj` tak właśnie działa), więc
    odmowa `szukaj` ma nazwać flagę, której brakuje, a nie mówić ogólnie o kryteriach."""
    wynik = runner.invoke(
        app, ["szukaj", "--rodzaj", "wyrok", "--rozstrzygniecie", "oddalono", "--baza", str(korpus)]
    )

    assert wynik.exit_code == 3, wynik.output
    assert "--fraza" in wynik.output


def test_szukaj_z_niedodatnim_limitem_odmawia_zdaniem_o_limicie(korpus: Path) -> None:
    wynik = runner.invoke(
        app, ["szukaj", "--fraza", "tresc", "--limit", "0", "--baza", str(korpus)]
    )

    assert wynik.exit_code == 3, wynik.output
    assert "imit" in wynik.output


@pytest.mark.parametrize("limit", ["0", "-1"])
def test_runy_z_niedodatnim_limitem_odmawia_tak_samo_jak_szukaj(korpus: Path, limit: str) -> None:
    """Ta sama flaga w dwóch poleceniach zachowuje się inaczej: `szukaj --limit 0` odmawia
    zdaniem, `runy --limit 0` pokazuje pustą tabelę („pokazano 0 z 1"), a `runy --limit -1`
    pokazuje **wszystko**, bo SQLite tak czyta ujemny `LIMIT`. Semantyka bazy przecieka do flagi,
    a operator, który wpisał `-1` z przyzwyczajenia, dostaje coś innego, niż prosił."""
    wynik = runner.invoke(app, ["runy", "--limit", limit, "--baza", str(korpus)])

    assert wynik.exit_code == 3, wynik.output
    assert "imit" in wynik.output


# --- próg zgody: co operator wie po zatrzymaniu --------------------------------------------------


def test_prog_zgody_zatrzymuje_przebieg_i_nazywa_flage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zatrzymanie na progu zgody jest zaprojektowane, ale dla laika wygląda jak awaria w połowie.
    Minimum: kod 3, nazwa flagi i liczba dokumentów w zakresie — żeby decyzja o `--zgoda` zapadała
    na liczbie, a nie na domyśle."""
    podstaw(monkeypatch, Serwer())
    baza = tmp_path / "korpus.sqlite"

    wynik = runner.invoke(
        app, ["pobierz", *ZAKRES, "--baza", str(baza), "--out", str(tmp_path / "z")]
    )

    assert wynik.exit_code == 3, wynik.output
    assert "--zgoda" in wynik.output and "29580" in wynik.output.replace(" ", "")


def test_po_progu_zgody_operator_wie_ze_przebieg_jest_zapisany(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przebieg zatrzymany na progu zostaje w bazie jako `przerwany` i to samo polecenie z `--zgoda`
    dokończy go bez duplikatów (README, „Zgoda na przebieg masowy") — ale komunikat mówi wyłącznie
    „podaj `zgoda=True`, w wierszu poleceń flagę `--zgoda`". Laik nie wie, że cokolwiek zostało
    zapisane, ani że powtórzenie polecenia nie zapłaci drugi raz za to, co już przyszło; zwrot
    `zgoda=True` jest przy tym nazwą parametru funkcji, nie czymś, co da się wpisać w powłoce.
    """
    podstaw(monkeypatch, Serwer())
    baza = tmp_path / "korpus.sqlite"

    wynik = runner.invoke(
        app, ["pobierz", *ZAKRES, "--baza", str(baza), "--out", str(tmp_path / "z")]
    )

    assert "przerwany" in wynik.output, "komunikat nie mówi, że przebieg został zapisany"
    assert "zgoda=True" not in wynik.output, "komunikat CLI podaje nazwę parametru funkcji"


# --- nowa baza: pierwsze uruchomienie i literówka wyglądają tak samo ---------------------------


def test_nowa_sciezka_bazy_mowi_ze_zalozyla_pusta_baze(tmp_path: Path) -> None:
    """Literówka w `--baza` i pierwsze uruchomienie zakładają pustą bazę tak samo cicho.

    Jedno zdanie ze ścieżką (`texts.nowa_baza`) odróżnia je dla operatora: „nie ma żadnego
    przebiegu" nad nową bazą obok prawdziwego korpusu wyglądało jak utrata danych (przejście
    ręczne 2026-09-18). Mutacja usuwająca to zdanie przeszła cicho przez suitę — stąd test.
    Drugie otwarcie tej samej ścieżki nie jest założeniem i zdania nie dostaje.
    """
    baza = tmp_path / "literowka.sqlite"

    pierwsze = runner.invoke(app, ["runy", "--baza", str(baza)])
    drugie = runner.invoke(app, ["runy", "--baza", str(baza)])

    assert pierwsze.exit_code == 0, pierwsze.output
    assert "Założono" in pierwsze.output and baza.name in pierwsze.output
    assert "Założono" not in drugie.output, "istniejąca baza nie jest zakładana drugi raz"
