"""Strażnik piaskownicy testów — fixture `_piaskownica` z `tests/conftest.py`.

Piaskownica jest jedynym zabezpieczeniem w tym drzewie, które chroni **prawdziwy** dziennik
żądań i **prawdziwy** `scripts/out/` przed testem. Waga bierze się stąd, że `docs/dziennik_zadan.md`
jest w historii repozytorium: wiersz dopisany tam przez test byłby zapisem żądania, którego
nikt nie wysłał — czyli fałszywym N w dokumencie, który konwencją `decisions.md` wymaga N co do
sztuki. Odwrotna pomyłka jest równie droga: test, który **skasuje** prawdziwy dziennik, kasuje
ślad po żądaniach naprawdę wysłanych do cudzych serwisów.

Sama piaskownica składa się z dwóch połów i do 2026-09-18 żadna nie miała obserwatora:

1. **przekierowanie** `zadanie.KATALOG_WYJSCIA` i `zadanie.DZIENNIK` do `tmp_path` — sprawdza je
   `test_logbook.py` („zapis w ogóle gdzieś trafia"), więc ta połowa była zaopiekowana;
2. **porównanie stanu prawdziwych ścieżek przed testem i po nim** — czyli czujnik na wypadek,
   gdyby przekierowanie zostało ominięte. Ten plik jest jego obserwatorem.

Zmierzone mutacją 2026-09-18, obie cicho przez cały zielony przebieg: asercja piaskownicy
osłabiona do `assert True or …` (610 zielonych) oraz czujnik `stan_prawdziwych_sciezek`
zwracający na sztywno „dziennika nie ma" (610 zielonych). Pierwsza mutacja znosi zabezpieczenie,
druga oślepia je po cichu — i to jest gorsza z dwóch, bo zostawia napis, który wygląda jak
strażnik.

**Druga para ścieżek, dopisana 2026-09-18 po zmierzonym incydencie.** Piaskownica broniła
wyłącznie sondy, a etap V dołożył polecenia, które bez `--baza`/`--out` sięgają domyślnych
ścieżek z katalogu danych użytkownika. Cztery testy w `test_cli.py` (`pobierz` bez `--out`)
zapisywały wtedy eksport do prawdziwego `config.default_output_dir()` — zmierzone tego dnia
na podstawionym katalogu danych: **4 pliki na przebieg suity, 905 testów zielonych**; w katalogu
operatora zastano 24 pliki z zegara testowego (`*_20231114T22…`) i skasowano je ręcznie.
Prawdziwa baza nie została dotknięta, bo każdy test CLI podaje `--baza` — ale to jest cecha
dzisiejszych testów, nie zabezpieczenie, więc czujnik obejmuje obie ścieżki.

Żaden test w tym pliku nie dotyka prawdziwych ścieżek: czujniki jadą na `tmp_path`, a asercje
fixture są czytane ze składni, nie wykonywane.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from tests import conftest
from tests import wsparcie_sondy as wsparcie
from tests.wsparcie_sondy import (
    PRAWDZIWA_BAZA,
    PRAWDZIWE_WYJSCIE,
    PRAWDZIWE_WYNIKI,
    PRAWDZIWY_DZIENNIK,
    moduly_z_domyslnymi_sciezkami,
    stan_korpusu,
    stan_sciezek,
)

# --- czujnik: czy w ogóle odróżnia stany ----------------------------------------------------


def test_czujnik_odroznia_brak_pliku_od_pliku_zalozonego(tmp_path: Path) -> None:
    """Założenie dziennika jest naruszeniem tak samo jak dopisanie do istniejącego.

    Prawdziwy `docs/dziennik_zadan.md` **dziś nie istnieje** — powstaje przy pierwszym przebiegu
    sondy. Gdyby czujnik widział wyłącznie zmianę treści istniejącego pliku, milczałby przez cały
    okres, w którym najłatwiej ten plik założyć przypadkiem: dopóki go nie ma.
    """
    dziennik = tmp_path / "dziennik.md"
    katalog = tmp_path / "out"

    przed = stan_sciezek(dziennik, katalog)
    dziennik.write_text("| sonda-1 |\n", encoding="utf-8")

    assert przed == (None, None)
    assert stan_sciezek(dziennik, katalog) != przed, "założenie dziennika przeszło niezauważone"


def test_czujnik_widzi_dopisany_wiersz_w_istniejacym_dzienniku(tmp_path: Path) -> None:
    """Treść, nie rozmiar i nie data modyfikacji: wiersz zamieniony na inny tej samej długości
    jest tą samą klasą usterki co wiersz dopisany."""
    dziennik = tmp_path / "dziennik.md"
    katalog = tmp_path / "out"
    dziennik.write_text("| sonda-1 |\n", encoding="utf-8")

    przed = stan_sciezek(dziennik, katalog)
    with dziennik.open("a", encoding="utf-8") as plik:
        plik.write("| sonda-2 |\n")

    assert stan_sciezek(dziennik, katalog) != przed, "dopisany wiersz przeszedł niezauważony"


def test_czujnik_widzi_skasowanie_dziennika(tmp_path: Path) -> None:
    """Kierunek, o którym łatwo zapomnieć: test kasujący dziennik kasuje ślad po żądaniach,
    które naprawdę poszły do cudzych serwisów."""
    dziennik = tmp_path / "dziennik.md"
    katalog = tmp_path / "out"
    dziennik.write_text("| sonda-1 |\n", encoding="utf-8")

    przed = stan_sciezek(dziennik, katalog)
    dziennik.unlink()

    assert stan_sciezek(dziennik, katalog) != przed, "skasowanie dziennika przeszło niezauważone"


def test_czujnik_widzi_surowa_odpowiedz_zapisana_do_prawdziwego_wyjscia(tmp_path: Path) -> None:
    """Druga ścieżka piaskownicy. `scripts/out/` jest poza historią repozytorium, ale plik
    dorzucony tam przez test miesza się z dowodami z prawdziwych przebiegów — a to one są
    materiałem, na którym stanie parser i porównanie bajtów pomiaru 19."""
    dziennik = tmp_path / "dziennik.md"
    katalog = tmp_path / "out"
    katalog.mkdir()

    przed = stan_sciezek(dziennik, katalog)
    (katalog / "atlas_3a_lista_20231114T221320Z.json").write_text("{}", encoding="utf-8")

    assert przed == (None, ())
    assert stan_sciezek(dziennik, katalog) != przed, "zapis do katalogu przeszedł niezauważony"


def test_czujnik_milczy_gdy_nic_sie_nie_ruszylo(tmp_path: Path) -> None:
    """Druga strona każdego z czterech testów wyżej.

    Czujnik zgłaszający zawsze jest tak samo bezużyteczny jak ten, który nie zgłasza nigdy —
    tylko głośniej: zapaliłby piaskownicę na **każdym** teście w drzewie i zostałby wyłączony
    tego samego dnia.
    """
    dziennik = tmp_path / "dziennik.md"
    katalog = tmp_path / "out"
    dziennik.write_text("| sonda-1 |\n", encoding="utf-8")
    katalog.mkdir()
    (katalog / "plik.json").write_text("{}", encoding="utf-8")

    assert stan_sciezek(dziennik, katalog) == stan_sciezek(dziennik, katalog)


def test_czujnik_czyta_te_sciezki_ktorych_piaskownica_broni() -> None:
    """Czujnik sprawdzony na `tmp_path` broniłby czegokolwiek, gdyby prawdziwe wywołanie
    wskazywało w inne miejsce.

    Ścieżki są odczytane w `wsparcie_sondy` **przed** jakimkolwiek przekierowaniem i to jest
    cała różnica między „porównuję stan prawdziwego dziennika" a „porównuję stan `tmp_path`
    z samym sobą" — drugie przechodzi zawsze.
    """
    assert PRAWDZIWY_DZIENNIK.name == "dziennik_zadan.md"
    assert PRAWDZIWY_DZIENNIK.parent.name == "docs"
    assert PRAWDZIWE_WYJSCIE.name == "out"
    assert PRAWDZIWE_WYJSCIE.parent.name == "scripts"


def test_prawdziwe_wywolanie_czujnika_naprawde_zaglada_pod_te_sciezki(tmp_path: Path) -> None:
    """Ostatnia luka tej pary, zmierzona mutacją 2026-09-18 i zamknięta tego samego dnia.

    Test wyżej sprawdza **nazwy stałych**, a testy czujnika jadą po `tmp_path` — więc obie
    połowy przechodziły zielono także wtedy, gdy `stan_prawdziwych_sciezek` wołało `stan_sciezek`
    z zupełnie innymi ścieżkami (`Path("nie_ma.md")`). Czujnik patrzył wtedy w nicość: zwracał
    `(None, None)` przed testem i po nim, więc porównanie w piaskownicy zawsze się zgadzało,
    a prawdziwy dziennik był bez ochrony. 649 zielonych testów.

    Podstawienie jest tu ręczne, a nie przez `monkeypatch`, i to jest konieczność, nie styl:
    `_piaskownica` też bierze `monkeypatch`, więc jego cofnięcie następuje **po** teardownie
    piaskownicy — czyli asercja piaskownicy zobaczyłaby podstawioną ścieżkę i zapaliła się na
    tym teście. `try/finally` przywraca stałe, zanim test odda sterowanie.
    """
    podstawiony = tmp_path / "podstawiony_dziennik.md"
    podstawiony.write_text("| sonda-1 |\n", encoding="utf-8", newline="\n")
    podstawione_wyjscie = tmp_path / "podstawione_out"
    podstawione_wyjscie.mkdir()
    (podstawione_wyjscie / "atlas_3a_lista.json").write_text("{}", encoding="utf-8")
    prawdziwy, prawdziwe = wsparcie.PRAWDZIWY_DZIENNIK, wsparcie.PRAWDZIWE_WYJSCIE
    try:
        wsparcie.PRAWDZIWY_DZIENNIK = podstawiony
        wsparcie.PRAWDZIWE_WYJSCIE = podstawione_wyjscie
        odczyt = wsparcie.stan_prawdziwych_sciezek()
    finally:
        wsparcie.PRAWDZIWY_DZIENNIK, wsparcie.PRAWDZIWE_WYJSCIE = prawdziwy, prawdziwe

    assert odczyt == (b"| sonda-1 |\n", ("atlas_3a_lista.json",)), (
        "`stan_prawdziwych_sciezek` nie czyta stałych `PRAWDZIWY_DZIENNIK` i `PRAWDZIWE_WYJSCIE` "
        "— czujnik piaskownicy zagląda pod inne ścieżki niż te, których piaskownica broni"
    )
    assert wsparcie.stan_prawdziwych_sciezek() != odczyt, "stałe nie wróciły na swoje miejsce"


# --- czujnik korpusu: baza operatora i katalog eksportów ------------------------------------


def _korpus(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "korpus.sqlite", tmp_path / "wyniki"


def test_czujnik_korpusu_widzi_eksport_dorzucony_do_katalogu_wynikow(tmp_path: Path) -> None:
    """Dokładnie zmierzony incydent: `pobierz` bez `--out` wpisuje arkusz do domyślnego
    katalogu wyników. Nazwa niesie zegar testowy, więc plik da się rozpoznać — ale rozpoznać
    go musiał człowiek, bo żaden test nie mówił, że coś tam powstało."""
    baza, katalog = _korpus(tmp_path)
    katalog.mkdir()

    przed = stan_korpusu(baza, katalog)
    (katalog / "kio_atlas-4684ec8cc01e_20231114T221322Z.xlsx").write_bytes(b"PK\x03\x04")

    assert przed == (None, ())
    assert stan_korpusu(baza, katalog) != przed, "dorzucony eksport przeszedł niezauważony"


def test_czujnik_korpusu_zaglada_w_glab_katalogu_eksportu_md(tmp_path: Path) -> None:
    """Eksport `md` jest katalogiem z plikiem na orzeczenie, więc spis samych wpisów najwyższego
    poziomu milczałby o pliku dorzuconym do katalogu, który już istnieje."""
    baza, katalog = _korpus(tmp_path)
    (katalog / "kio_2024_md").mkdir(parents=True)
    (katalog / "kio_2024_md" / "INDEX.md").write_text("# indeks\n", encoding="utf-8")

    przed = stan_korpusu(baza, katalog)
    (katalog / "kio_2024_md" / "atlas_kio-1205-20.md").write_text("---\n", encoding="utf-8")

    assert stan_korpusu(baza, katalog) != przed, (
        "plik dorzucony do istniejącego katalogu `*_md` przeszedł niezauważony — czujnik czyta "
        "tylko najwyższy poziom"
    )


def test_czujnik_korpusu_widzi_zalozenie_bazy_i_zmiane_jej_zawartosci(tmp_path: Path) -> None:
    """Dwa kierunki naraz: baza założona tam, gdzie jej nie było, i baza dopisana.

    Prawdziwy `korpus.sqlite` niesie 295 dokumentów operatora, więc obie pomyłki są drogie
    inaczej: pierwsza podkłada fałszywy korpus, druga miesza materiał testowy z prawdziwym.
    """
    baza, katalog = _korpus(tmp_path)

    przed_zalozeniem = stan_korpusu(baza, katalog)
    baza.write_bytes(b"SQLite format 3\x00")
    po_zalozeniu = stan_korpusu(baza, katalog)
    baza.write_bytes(b"SQLite format 3\x00" + b"\x00" * 4096)

    assert przed_zalozeniem == (None, None)
    assert po_zalozeniu != przed_zalozeniem, "założenie bazy przeszło niezauważone"
    assert stan_korpusu(baza, katalog) != po_zalozeniu, "dopisanie do bazy przeszło niezauważone"


def test_czujnik_korpusu_milczy_gdy_nic_sie_nie_ruszylo(tmp_path: Path) -> None:
    """Druga strona każdego z trzech testów wyżej — czujnik zapalający się zawsze zostałby
    wyłączony tego samego dnia, bo świeciłby na wszystkich 905 testach."""
    baza, katalog = _korpus(tmp_path)
    baza.write_bytes(b"SQLite format 3\x00")
    (katalog / "kio_2024_md").mkdir(parents=True)
    (katalog / "kio_2024_md" / "INDEX.md").write_text("# indeks\n", encoding="utf-8")

    assert stan_korpusu(baza, katalog) == stan_korpusu(baza, katalog)


def test_prawdziwe_wywolanie_czujnika_korpusu_zaglada_pod_sciezki_operatora(
    tmp_path: Path,
) -> None:
    """Ta sama luka, którą przy dzienniku żądań zamknięto 2026-09-18: testy wyżej jadą po
    `tmp_path`, więc przechodziłyby zielono także wtedy, gdyby `stan_prawdziwego_korpusu`
    czytało zupełnie inne ścieżki i zwracało `(None, None)` przed testem i po nim.

    Podstawienie ręczne, nie przez `monkeypatch`, bo cofnięcie `monkeypatch` następuje **po**
    teardownie `_piaskownica` — czyli asercja piaskownicy zobaczyłaby podstawioną ścieżkę.
    """
    podstawiona_baza = tmp_path / "podstawiony_korpus.sqlite"
    podstawiona_baza.write_bytes(b"SQLite format 3\x00")
    podstawione_wyniki = tmp_path / "podstawione_wyniki"
    podstawione_wyniki.mkdir()
    (podstawione_wyniki / "kio_2024.xlsx").write_bytes(b"PK")
    prawdziwa, prawdziwe = wsparcie.PRAWDZIWA_BAZA, wsparcie.PRAWDZIWE_WYNIKI
    try:
        wsparcie.PRAWDZIWA_BAZA = podstawiona_baza
        wsparcie.PRAWDZIWE_WYNIKI = podstawione_wyniki
        odczyt = wsparcie.stan_prawdziwego_korpusu()
    finally:
        wsparcie.PRAWDZIWA_BAZA, wsparcie.PRAWDZIWE_WYNIKI = prawdziwa, prawdziwe

    assert odczyt[0] is not None and odczyt[0][0] == 16
    assert odczyt[1] is not None and [n for n, _, _ in odczyt[1]] == ["kio_2024.xlsx"], (
        "`stan_prawdziwego_korpusu` nie czyta stałych `PRAWDZIWA_BAZA` i `PRAWDZIWE_WYNIKI` "
        "— czujnik zagląda pod inne ścieżki niż te, których piaskownica broni"
    )
    assert wsparcie.stan_prawdziwego_korpusu() != odczyt, "stałe nie wróciły na swoje miejsce"


def test_czujnik_korpusu_czyta_sciezki_z_katalogu_danych_uzytkownika() -> None:
    """Stałe wskazują tam, gdzie produkcja trzyma korpus — a nie do drzewa repozytorium."""
    assert PRAWDZIWA_BAZA.name == "korpus.sqlite"
    assert PRAWDZIWE_WYNIKI.name == "wyniki"
    assert PRAWDZIWA_BAZA.parent == PRAWDZIWE_WYNIKI.parent
    assert Path(__file__).resolve().parent.parent not in PRAWDZIWA_BAZA.parents


# --- przekierowanie domyślnych ścieżek: każdy moduł, który je trzyma -------------------------


@pytest.mark.parametrize("nazwa", ["default_db_path", "default_output_dir"])
def test_zaden_modul_nie_zostal_z_prawdziwa_domyslna_sciezka(nazwa: str) -> None:
    """Metatest przekierowania — ten sam kształt, co „reguła ma plik-właściciela, a skan go nie
    obejmuje" z `test_boundaries.py`.

    `cli.py` i `pipeline.py` biorą te funkcje przez `from .config import …`, więc podstawienie
    w samym `config` ich nie dosięga. Moduł dopisany kiedyś z takim importem zapali się tutaj,
    a nie przy pierwszym zapisie do katalogu operatora.
    """
    zostale = moduly_z_domyslnymi_sciezkami()[nazwa]

    assert zostale == (), (
        f"moduły {zostale} trzymają nadal prawdziwe `{nazwa}` — piaskownica ich nie "
        "przekierowała, więc polecenie bez `--baza`/`--out` sięgnie katalogu danych operatora"
    )


def test_przekierowane_sciezki_prowadza_do_piaskownicy_tego_testu(tmp_path: Path) -> None:
    """Widziane z wnętrza dowolnego testu i przez te same nazwy, których używa produkcja:
    `cli.default_db_path` przy poleceniu bez `--baza`, `pipeline.default_output_dir` przy
    eksporcie bez `--out`."""
    from kio_tool import cli, pipeline

    assert tmp_path in cli.default_db_path().parents
    assert tmp_path in pipeline.default_output_dir().parents


def test_przekierowanie_obejmuje_miejsca_uzycia_nie_tylko_modul_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sedno przekierowania, zmierzone na cofniętej piaskownicy.

    Podstawienie samego `kio_tool.config` **nie działa**: `cli.py` i `pipeline.py` mają własne
    nazwy z `from .config import …`, związane przy imporcie. Test przywraca oryginały w czterech
    miejscach, każe piaskownicy przekierować je jeszcze raz i pyta o wynik po nazwach modułów —
    więc przekierowanie zawężone kiedyś do `config` zapali się tutaj, zamiast po cichu wypuścić
    polecenia do katalogu operatora.
    """
    from kio_tool import cli, config, pipeline

    miejsca = (
        (config, "default_db_path"),
        (config, "default_output_dir"),
        (cli, "default_db_path"),
        (pipeline, "default_output_dir"),
    )
    for modul, nazwa in miejsca:
        monkeypatch.setattr(modul, nazwa, wsparcie.ORYGINALNE_SCIEZKI[nazwa])

    podstawione = wsparcie.przekieruj_domyslne_sciezki(monkeypatch, tmp_path / "drugie")

    assert set(podstawione) == {f"{m.__name__}.{n}" for m, n in miejsca}
    assert cli.default_db_path().parent == tmp_path / "drugie"
    assert pipeline.default_output_dir().parent == tmp_path / "drugie"


# --- fixture: czy porównanie stanu wciąż jest w jej ciele -----------------------------------


def _fixture(nazwa: str) -> ast.FunctionDef:
    """Definicja fixture z `conftest.py` odczytana ze **składni modułu**, nie z obiektu pytest.

    Odczyt składni, bo wykonać tej asercji się nie da: sprawdzenie zachowaniowe wymagałoby
    przebiegu pytest w przebiegu pytest (fixture `pytester`) albo testu, który **naprawdę**
    rusza prawdziwy dziennik po to, żeby zobaczyć, czy piaskownica krzyknie. Pierwsze kosztuje
    kilka sekund na przebieg suity liczonej w dziesięciu; drugie jest zabronione przez to samo
    zabezpieczenie, które miałoby sprawdzić. Zostaje odczyt składni — ten sam idiom, na którym
    stoi cały `test_boundaries.py`.

    Ze składni, a nie z atrybutów obiektu fixture, bo tamte są prywatne dla pytest i zmieniły
    już kształt raz: `_pytestfixturefunction` ustąpiło `FixtureFunctionDefinition`
    z `_fixture_function_marker` (sprawdzone 2026-09-18 na pytest zainstalowanym w tym drzewie).
    Strażnik wywrócony przez podbicie wersji zostaje wyłączony, a nie poprawiony.
    """
    drzewo = ast.parse(inspect.getsource(conftest))
    znaleziona = next(
        (node for node in drzewo.body if isinstance(node, ast.FunctionDef) and node.name == nazwa),
        None,
    )
    assert znaleziona is not None, (
        f"`tests/conftest.py` nie ma już funkcji `{nazwa}` — fixture zniknęła albo zmieniła nazwę"
    )
    return znaleziona


def _wola(node: ast.AST, nazwa: str) -> bool:
    return any(
        isinstance(w, ast.Call)
        and (getattr(w.func, "id", "") == nazwa or getattr(w.func, "attr", "") == nazwa)
        for w in ast.walk(node)
    )


def _autouse(fixture: ast.FunctionDef) -> bool:
    """Czy dekorator fixture niesie `autouse=True`."""
    return any(
        isinstance(dekorator, ast.Call)
        and any(
            kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in dekorator.keywords
        )
        for dekorator in fixture.decorator_list
    )


@pytest.mark.parametrize(
    ("czujnik", "czego_broni"),
    [
        ("stan_prawdziwych_sciezek", f"{PRAWDZIWY_DZIENNIK} i {PRAWDZIWE_WYJSCIE}"),
        ("stan_prawdziwego_korpusu", f"{PRAWDZIWA_BAZA} i {PRAWDZIWE_WYNIKI}"),
    ],
)
def test_piaskownica_porownuje_stan_po_kazdym_tescie(czujnik: str, czego_broni: str) -> None:
    """Obserwator samych asercji piaskownicy — bo skreślona nie zapala niczego.

    Zmierzone mutacją 2026-09-18: `assert stan_prawdziwych_sciezek() == przed` osłabione do
    `assert True or …` zostawia 610 zielonych testów. Piaskownica zostaje wtedy samym
    przekierowaniem, a przekierowanie bez porównania jest gwarancją, której nikt nie obserwuje:
    wystarczy, że funkcja sondy złoży kiedyś ścieżkę z `Path(__file__)` zamiast czytać stałą
    modułu, i test po cichu dopisze wiersz do dziennika w historii repozytorium. Drugi czujnik
    ma tę samą wagę z drugiego powodu: bez jego porównania cztery testy `test_cli.py` wróciłyby
    do zapisywania eksportów do katalogu operatora, znów bez jednego czerwonego testu.

    Asercja ma być **porównaniem** (`ast.Compare`), a nie dowolnym wyrażeniem zawierającym
    wywołanie czujnika — `True or stan_prawdziwych_sciezek() == przed` zawiera je i nie sprawdza
    nic. To jest ta sama myśl, którą `test_boundaries.py` zapisał przy `argument_bezpieczny`:
    liczy się korzeń wyrażenia, nie to, co da się w nim znaleźć obchodem drzewa.
    """
    asercje = [node for node in ast.walk(_fixture("_piaskownica")) if isinstance(node, ast.Assert)]

    porownania = [
        node for node in asercje if isinstance(node.test, ast.Compare) and _wola(node.test, czujnik)
    ]

    assert porownania, (
        f"fixture `_piaskownica` nie porównuje już stanu przez `{czujnik}`. Zostaje samo "
        "przekierowanie do `tmp_path` — a ono jest gwarancją bez obserwatora: kod, który złoży "
        f"ścieżkę sam zamiast czytać przekierowaną nazwę, ruszy {czego_broni} bez jednego "
        "czerwonego testu"
    )
    assert any(node.msg is not None for node in porownania), (
        "porównanie stanu bez komunikatu: `AssertionError` z samym `==` nie powie czytającemu, "
        "co dokładnie się ruszyło"
    )


def test_piaskownica_przekierowuje_domyslne_sciezki_korpusu() -> None:
    """Pierwsza połowa piaskownicy korpusu, czytana ze składni — bo jej brak jest cichy.

    Wywołanie `przekieruj_domyslne_sciezki` skreślone z fixture zostawia porównanie stanu,
    czyli czujnik, który **zapala się już po zapisie**. Piaskownica ma nie dopuścić do zapisu,
    a nie zgłosić go po fakcie: plik w katalogu operatora trzeba wtedy skasować ręcznie, co
    2026-09-18 zdarzyło się raz, przy dwudziestu czterech plikach.
    """
    assert _wola(_fixture("_piaskownica"), "przekieruj_domyslne_sciezki"), (
        "fixture `_piaskownica` nie przekierowuje już `default_db_path`/`default_output_dir` — "
        "polecenie bez `--baza`/`--out` pisze do katalogu danych operatora, a porównanie stanu "
        "powie o tym dopiero po zapisie"
    )


def test_piaskownica_i_czysty_rejestr_sekretow_obowiazuja_bez_proszenia() -> None:
    """Obie fixtures są `autouse` i to jest rozstrzygnięcie z nagłówka `conftest.py`.

    Fixture wymagająca wpisania nazwy chroni plik, który o nią poprosił; plik, który zapomniał,
    wygląda identycznie jak plik z ochroną. Testy sondy rozeszły się 2026-09-18 po ośmiu plikach,
    więc to jest ta różnica, która decyduje o wszystkim.
    """
    for nazwa in ("_piaskownica", "_czysty_rejestr_sekretow"):
        assert _autouse(_fixture(nazwa)), (
            f"`{nazwa}` przestała być `autouse` — plik testów, który o nią nie poprosi, "
            "wygląda tak samo jak plik chroniony"
        )


@pytest.mark.parametrize("nazwa", ["KATALOG_WYJSCIA", "DZIENNIK"])
def test_piaskownica_naprawde_przekierowala_stala_modulu(nazwa: str, tmp_path: Path) -> None:
    """Pierwsza połowa piaskownicy, widziana z wnętrza dowolnego testu.

    `test_logbook.py` sprawdza, że zapis trafia poza drzewo repozytorium; ta asercja mówi to
    samo o samej stałej i robi to w **każdym** pliku, który ją zaimportuje — więc przekierowanie
    zawężone kiedyś do jednego modułu zapali się tutaj, a nie przy pierwszym zapisie na dysk.
    """
    import zadanie

    sciezka = getattr(zadanie, nazwa)

    assert tmp_path in sciezka.parents, (
        f"`zadanie.{nazwa}` wskazuje na {sciezka}, a nie do piaskownicy tego testu"
    )
