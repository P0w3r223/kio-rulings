"""Mechaniczny strażnik reguł granic — kształt przyjęty w ADR-0003 sekcja 5.

Reguły stoją w `docs/AUDYT_KIO_ORZECZENIA.md` 8.3 (1–16), `docs/ARCHITEKTURA_KIO_TOOL.md`
4.1 (17–20) i w ADR-0003 sekcja 4 (nowe brzmienia 11 i 17, nowe reguły 21 i 22, poprawki
do 1, 2, 4 i 13). Ten plik jest ich jedyną mechaniczną postacią: reguła bez strażnika jest
w tym projekcie życzeniem, a życzenie w dokumencie wygląda dokładnie tak samo jak reguła
egzekwowana.

**Zasada nadrzędna: pusty skan nie jest zielonym skanem** (ADR-0003 5.1). Większość reguł
dotyczy katalogów, które jeszcze nie powstały — `source/`, `parser/`, `ui/`, `mcp_server.py`.
Reguła na prawdziwym drzewie przechodzi wtedy **pusto** i to jest prawda o stanie projektu,
nie luka. Ciężar dowodu niosą wtedy dwie pozostałe części, obecne od pierwszego commita:

1. **Samosprawdzenie skanu** na plikach podrzuconych w `tmp_path` — nigdy nie jest puste.
2. **Metatest antypustkowy** (`test_metatest_...`) — wykrywa stan „reguła ma plik-właściciela,
   a skan go nie obejmuje”. To jedyny sposób, w jaki tablica `REGULY` może skłamać: wpis
   w stanie *wyzwalacza* jest legalny wyłącznie wtedy, gdy pliku-właściciela nie ma.
   Dlatego każdy wpis niesie **funkcję liczącą pliki, które skan naprawdę czyta**, i jest to
   ta sama funkcja, po której iteruje test reguły — rozjazd między „co skan obejmuje”
   a „co skan deklaruje, że obejmuje” jest przez to niemożliwy, a nie tylko pilnowany.

**Granica skanu jest w teście widoczna, nie domniemana.** Skan łapie przeoczenia, nie
napastnika (ADR-0003 7.3). Sekcja „granica skanu” na końcu pliku **asertuje** kształty,
których skan świadomie nie widzi — `getattr`, przypisanie fabryki do zmiennej, sklejenie
adresu z dwóch literałów. Te testy są tam po to, żeby granica miała współrzędne: gdyby
ktoś kiedyś skan wzmocnił, zapalą się i wymuszą świadomą zmianę zamiast cichego rozszerzenia.

**Lista wyjątków nie jest lekarstwem na czerwony test.** Reguła, która zapala się na
istniejącym kodzie, znaczy, że do poprawki jest albo kod, albo reguła — i to jest decyzja
właściciela, nie wpis w tablicy.

Żaden test w tym pliku nie dotyka sieci ani nie importuje modułów produkcyjnych poza
`kio_tool.docid`, z którego bierze kanoniczną nazwę kanału (reguła 21).
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

import pytest
import yaml

from kio_tool.docid import normalize_source_name
from kio_tool.errors import IdentityError

ROOT = Path(__file__).resolve().parent.parent
PAKIET = ROOT / "kio_tool"
TESTY = ROOT / "tests"
SKRYPTY = ROOT / "scripts"
SOURCE = PAKIET / "source"
PRZYKLADY = TESTY / "examples"


# --------------------------------------------------------------- wspólne narzędzia skanu


def drzewo(path: Path) -> ast.Module:
    """Drzewo składniowe pliku. Jedyne miejsce, w którym ten plik czyta kod z dysku."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def moduly_py(katalog: Path) -> tuple[Path, ...]:
    """Moduły `.py` w katalogu, rekursywnie, bez `__pycache__`.

    Rekursywnie — i to jest poprawka reguł 2 i 4 z ADR-0003 sekcja 4. `glob("*.py")`
    jest skanem, który wygląda na działający dokładnie do dnia, w którym kanały stają się
    pakietami, a potem nie obejmuje niczego i nie mówi o tym ani słowa.
    """
    if not katalog.is_dir():
        return ()
    return tuple(
        sorted(p for p in katalog.rglob("*.py") if "__pycache__" not in p.parts and p.is_file())
    )


def wzgledne(pliki: Iterable[Path]) -> frozenset[str]:
    """Ścieżki względem korzenia repozytorium, w jednej pisowni — do tablicy `REGULY`."""
    return frozenset(p.relative_to(ROOT).as_posix() for p in pliki)


def istniejace(*sciezki: str) -> tuple[Path, ...]:
    """Te z podanych ścieżek, które dziś istnieją. Reguła w stanie wyzwalacza daje pustkę."""
    return tuple(ROOT / s for s in sciezki if (ROOT / s).is_file())


def imported_roots(path: Path) -> set[str]:
    """Nazwy pakietów najwyższego poziomu importowanych w module (bez importów względnych)."""
    roots: set[str] = set()
    for node in ast.walk(drzewo(path)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def package_targets(path: Path) -> set[str]:
    """Moduły pakietu importowane przez ten plik — do reguł 2, 5, 8 i 13.

    Liczą się obie formy zapisu. Pakiet pisze dziś wyłącznie względnie (`from .config import …`),
    ale `from kio_tool.config import …` znaczy dokładnie to samo, a podpowiadacz w edytorze
    wstawia właśnie tę wersję. Skan patrzący tylko na `level > 0` przestawałby wtedy cokolwiek
    znaczyć — bez jednego czerwonego testu, czyli w sposób nie do zauważenia w przeglądzie.

    Pierwszy człon wystarcza niezależnie od zagnieżdżenia i to jest odczyt, na którym stoi
    rozstrzygnięcie 1 ADR-0003: `from ...httpclient import build_http_client` w
    `source/uzp/channel.py` daje `"httpclient"`, a `from .source.registry import REGISTRY`
    w `pipeline.py` daje `"source"`. Kanał jako pakiet nie wymaga tu ani jednej zmiany.
    """
    targets: set[str] = set()
    for node in ast.walk(drzewo(path)):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.level > 0:
                targets.add(node.module.split(".")[0])
            elif node.module and node.module.startswith(f"{PAKIET.name}."):
                targets.add(node.module.split(".")[1])
            elif (node.module is None and node.level > 0) or node.module == PAKIET.name:
                # `from . import store` i `from kio_tool import store` niosą nazwę modułu
                # dopiero w `names`. Obie formy zwracały w pierwszej wersji skanu CEIDG zbiór
                # pusty, więc reguły 2, 5, 8 i 13 przestawały obowiązywać bez jednego
                # czerwonego testu.
                targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            targets.update(
                alias.name.split(".")[1]
                for alias in node.names
                if alias.name.startswith(f"{PAKIET.name}.")
            )
    return targets


@pytest.mark.parametrize(
    "zrodlo",
    [
        "from ..store import Store",
        "from kio_tool.store import Store",
        "import kio_tool.store",
        "import kio_tool.store as store",
        "from .. import store",
        "from kio_tool import store",
        "from ...store.zapis import zapisz",
    ],
    ids=[
        "wzgledny",
        "bezwzgledny_from",
        "bezwzgledny_import",
        "bezwzgledny_alias",
        "wzgledny_paczkowy",
        "bezwzgledny_paczkowy",
        "wzgledny_z_pakietu_kanalu",
    ],
)
def test_skan_importow_widzi_obie_pisownie_tej_samej_zaleznosci(
    tmp_path: Path, zrodlo: str
) -> None:
    """Reguły 2, 5, 8 i 13 mówią o zależności, nie o składni, którą ktoś wybrał.

    Ostatni przypadek jest z rozstrzygnięcia 1 ADR-0003: kanał jako pakiet importuje o poziom
    głębiej (`from ...store …` z `source/uzp/channel.py`) i skan ma to widzieć bez zmiany.
    """
    modul = tmp_path / "probny.py"
    modul.write_text(zrodlo, encoding="utf-8")

    assert "store" in package_targets(modul)


# ---------------------------------------------------- reguły 1 i 6: moduły czyste


# Reguła 1 po poprawce z ADR-0003 sekcja 4: lista modułów czystych spoza `parser/` jest
# wyliczona wprost, a `parser/` wchodzi w całości i rekursywnie. `config.py` do listy
# **nie** należy — importuje `os` i ma do tego powód (`CONTACT_ENV`). `criteria.py` doszedł
# 2026-09-18 (etap IV) — reguła 1 wymienia go z nazwy od pierwszego brzmienia.
MODULY_CZYSTE_WPROST = ("criteria.py", "docid.py", "safetext.py", "wycena.py", "demo/korpus.py")

# Reguła 1: moduł czysty nie zna wejścia/wyjścia ani systemu.
ZAKAZANE_REGULA_1 = frozenset({"httpx", "sqlite3", "openpyxl", "rich", "os"})

# Reguła 6: ta sama granica plus warstwa użytkownika i SDK modelu. Bez `os` — reguła 6 go
# nie wymienia, a dopisywanie go tutaj byłoby zaostrzeniem reguły w teście zamiast
# w dokumencie.
ZAKAZANE_REGULA_6 = frozenset(
    {"rich", "questionary", "typer", "httpx", "anthropic", "sqlite3", "openpyxl"}
)


def pliki_czyste() -> tuple[Path, ...]:
    """Moduły objęte regułą 1: wyliczone wprost plus całe `parser/` rekursywnie."""
    wyliczone = istniejace(*(f"kio_tool/{m}" for m in MODULY_CZYSTE_WPROST))
    return (*wyliczone, *moduly_py(PAKIET / "parser"))


def test_regula_1_moduly_czyste_nie_znaja_wejscia_wyjscia_ani_systemu() -> None:
    """Reguła 1: `docid`, `safetext` i każdy moduł w `parser/` dają się sprawdzić bez atrap.

    To jest reguła, która czyni fazę 2 wykonalną: „przeliczenie całego korpusu bez ani jednego
    żądania sieciowego” jest bramką, a nie deklaracją, dopóki parser nie ma czym wyjść.
    """
    naruszenia = {
        path.relative_to(ROOT).as_posix(): sorted(imported_roots(path) & ZAKAZANE_REGULA_1)
        for path in pliki_czyste()
        if imported_roots(path) & ZAKAZANE_REGULA_1
    }

    assert naruszenia == {}, f"moduł czysty sięga poza swoją warstwę: {naruszenia}"


def test_regula_6_moduly_czyste_i_teksty_nie_znaja_warstwy_uzytkownika() -> None:
    """Reguła 6: ta sama granica z drugiej strony — bibliotek ekranu i SDK modelu."""
    objete = (*pliki_czyste(), *istniejace("kio_tool/ui/texts.py"))
    naruszenia = {
        path.relative_to(ROOT).as_posix(): sorted(imported_roots(path) & ZAKAZANE_REGULA_6)
        for path in objete
        if imported_roots(path) & ZAKAZANE_REGULA_6
    }

    assert naruszenia == {}, f"moduł czysty zna warstwę użytkownika: {naruszenia}"


def test_regula_1_kazdy_wyliczony_modul_czysty_naprawde_istnieje() -> None:
    """Zabezpieczenie przed cichym rozbrojeniem reguły po zmianie nazwy pliku.

    Lista modułów wyliczona wprost jest jedyną częścią reguł 1 i 6, która **nie** wynika
    z drzewa. Zmiana nazwy `safetext.py` zamieniłaby ją w pętlę po zbiorze pustym, a taka
    pętla przechodzi zawsze i o niczym nie mówi.
    """
    for modul in MODULY_CZYSTE_WPROST:
        assert (PAKIET / modul).is_file(), modul
    assert ZAKAZANE_REGULA_1 and ZAKAZANE_REGULA_6, "pusty zbiór zakazów przechodzi zawsze"


def test_skan_regul_1_i_6_zauwaza_podrzucony_import(tmp_path: Path) -> None:
    """Kontrola mutacyjna, która powtarza się sama przy każdym uruchomieniu.

    Ręczne „sprawdziłem, że zapala się na podrzuconym `import httpx`” jest zdaniem
    w dokumencie, a nie własnością zestawu testów.
    """
    podrzucony = tmp_path / "parser_cite.py"
    podrzucony.write_text("import os\nimport httpx\nimport re\n", encoding="utf-8")

    assert imported_roots(podrzucony) & ZAKAZANE_REGULA_1 == {"os", "httpx"}
    # Reguła 6 nie wymienia `os` — różnica list jest zamierzona i tu widoczna.
    assert imported_roots(podrzucony) & ZAKAZANE_REGULA_6 == {"httpx"}


# ------------------------------------------- reguły 2, 3, 4, 5, 8, 13: krawędzie importu


def pliki_source() -> tuple[Path, ...]:
    """Reguła 2 i 4 po poprawce z ADR-0003: **rekursywnie**, `source/**/*.py`."""
    return moduly_py(SOURCE)


def pliki_pakietu() -> tuple[Path, ...]:
    return moduly_py(PAKIET)


ROLE_KANALU = frozenset({"masowa", "weryfikacja", "doplyw"})
"""Zamknięta lista ról z reguły 23. Rola spoza listy jest błędem, nie rozszerzeniem."""

ROLA_ZAKAZANA_DLA = {"uzp": "masowa"}
"""Dostawca → rola, której nie wolno zadeklarować kanałowi tego dostawcy (reguła 23, decyzja B
właściciela 2026-09-17).

Jeden wpis i to nie jest niedopatrzenie. Powód jest **per dostawca i zmierzony**: pomiar 14
(2026-09-15) wykazał, że dla `orzeczenia.uzp.gov.pl` nie ma warunków ponownego wykorzystywania
ani informacji o ich braku, a projekt zrezygnował z opinii prawnej (decyzja A). Kanał, który
reuse licencjonuje wprost, rolę masową mieć może — zakaz ogólny byłby regułą bez powodu.

Klucz jest **przedrostkiem nazwy katalogu**, nie pełną nazwą (przegląd kodu 2026-09-18): decyzja
B mówi o dostawcy, a tabela ADR-0004 zna drugi kanał tego samego dostawcy, `uzp_zrzut` — odpadł
decyzją A, ale gdyby kiedyś powstał z `role: [masowa]`, dopasowanie po pełnej nazwie przepuściłoby
go bez jednego czerwonego testu. Dopasowanie po hoście z kontraktu przyjdzie z pierwszym
`contract.yaml`, który hosty nazywa. Tablica, a nie napis w teście, bo drugi dostawca bez
licencji trafi tutaj razem ze swoją datą.
"""


def rola_zakazana(kanal: str) -> str:
    """Rola zakazana dla kanału: nazwa równa kluczowi albo zaczynająca się od `<klucz>_`."""
    for dostawca, rola in ROLA_ZAKAZANA_DLA.items():
        if kanal == dostawca or kanal.startswith(f"{dostawca}_"):
            return rola
    return ""


def contract_yaml_kanalow() -> dict[str, Path]:
    """Kanał → jego `contract.yaml`, o ile istnieje. Przy pustym `source/` pusty słownik."""
    if not SOURCE.is_dir():
        return {}
    return {
        katalog.name: katalog / "contract.yaml"
        for katalog in sorted(SOURCE.iterdir())
        if katalog.is_dir()
        and katalog.name != "__pycache__"
        and (katalog / "contract.yaml").is_file()
    }


def role_zadeklarowane(contract: Path) -> frozenset[str]:
    """Role z pola `role:` kontraktu — odczyt tekstowy, bez zależności od parsera YAML.

    Kontrakt jest dziś plikiem, którego nikt nie napisał, a `pyproject.toml` nie ma zależności
    od biblioteki YAML: wybór parsera jest odroczony do pierwszego prawdziwego `contract.yaml`
    (reguła 17). Skan czyta więc linię `role:` i wartości w postaci listy w nawiasie
    kwadratowym albo po przecinku — węziej niż YAML, ale bez udawania, że rozumie cały format.
    Kontrakt, którego ten odczyt nie zrozumie, daje zbiór pusty i zapala regułę jako brak `role`.
    """
    for linia in contract.read_text(encoding="utf-8").splitlines():
        if not linia.startswith("role:"):
            continue
        # Komentarz po `#` odcięty (przegląd kodu 2026-09-18): `role: [masowa]  # …` dawał zbiór
        # `{"masowa]  # …"}`, więc zakaz z decyzji B nie trafiał, a suita zostawała czerwona tylko
        # ubocznie — przez test zamkniętej listy, z innym komunikatem. Ten sam odczyt co
        # `pomiary_zadeklarowane` w `test_bramki_faz.py`.
        wartosc = linia.removeprefix("role:").split("#", 1)[0].strip().strip("[]")
        return frozenset(
            czesc.strip().strip("\"'") for czesc in wartosc.split(",") if czesc.strip()
        )
    return frozenset()


def pliki_ui() -> tuple[Path, ...]:
    return moduly_py(PAKIET / "ui")


def test_regula_2_kanaly_nie_siegaja_do_bazy() -> None:
    """Reguła 2: żaden moduł w `source/` nie importuje `store` ani `sqlite3`.

    Historię żądań kanał dostaje jako protokół. Bez tej granicy limiter i wznawianie
    przestają dać się sprawdzić z podstawioną historią, czyli bez pliku bazy.
    """
    naruszenia: dict[str, list[str]] = {}
    for path in pliki_source():
        zakazane = (package_targets(path) & {"store"}) | (imported_roots(path) & {"sqlite3"})
        if zakazane:
            naruszenia[path.relative_to(ROOT).as_posix()] = sorted(zakazane)

    assert naruszenia == {}, f"kanał sięga do bazy: {naruszenia}"


def test_regula_3_baza_nie_chodzi_do_sieci() -> None:
    """Reguła 3: `store.py` nie importuje `httpx`."""
    naruszenia = {
        path.relative_to(ROOT).as_posix(): sorted(imported_roots(path) & {"httpx"})
        for path in istniejace("kio_tool/store.py")
        if imported_roots(path) & {"httpx"}
    }

    assert naruszenia == {}, f"baza chodzi do sieci: {naruszenia}"


def test_regula_4_kanaly_i_baza_nie_rysuja() -> None:
    """Reguła 4: `source/` (rekursywnie) i `store.py` nie importują `rich`.

    Postęp idzie przez protokół `Events` z `kio_tool/progress.py`. Moduł, który rysuje sam,
    wymaga w teście terminala — a `NullEvents` istnieje właśnie po to, żeby nie wymagał.
    """
    objete = (*pliki_source(), *istniejace("kio_tool/store.py"))
    naruszenia = {
        path.relative_to(ROOT).as_posix(): sorted(imported_roots(path) & {"rich"})
        for path in objete
        if imported_roots(path) & {"rich"}
    }

    assert naruszenia == {}, f"warstwa danych rysuje sama: {naruszenia}"


def test_regula_5_tylko_pipeline_widzi_naraz_siec_i_baze() -> None:
    """Reguła 5 — ta, na której stoi wznawianie.

    Równość, nie zawieranie — od etapu III (2026-09-18), kiedy `pipeline.py` powstał. Do tego
    dnia stało tu zawieranie z powodu z ADR-0003 5.4: równość byłaby czerwona przy pustym
    drzewie. Teraz pilnuje obu kierunków: że drugiego takiego modułu nie ma **i** że ten jeden
    nadal łączy sieć z bazą — gdyby przestał, wznawianie działoby się gdzie indziej albo nigdzie.
    """
    obaj = {
        path.relative_to(ROOT).as_posix()
        for path in pliki_pakietu()
        if {"source", "store"} <= package_targets(path)
    }

    assert obaj == {"kio_tool/pipeline.py"}, (
        f"drugi moduł łączący sieć z bazą: {sorted(obaj)}. Druga ścieżka od żądania do zapisu "
        "to drugi checkpoint do pogodzenia — a niezmiennik „rekordy strony i checkpoint jedną "
        "transakcją” żyje tylko dopóki wszystko idzie przez `pipeline`."
    )


def test_regula_8_warstwa_uzytkownika_nie_siega_po_kanal_ani_baze() -> None:
    """Reguła 8: `ui/*` chodzi przez `pipeline`, nigdy wprost do źródła ani do bazy."""
    naruszenia = {
        path.relative_to(ROOT).as_posix(): sorted(package_targets(path) & {"source", "store"})
        for path in pliki_ui()
        if package_targets(path) & {"source", "store"}
    }

    assert naruszenia == {}, f"warstwa użytkownika omija pipeline: {naruszenia}"


# Reguła 13 w brzmieniu z ADR-0003 sekcja 4: decyzja 3 zastąpiła asystenta serwerem MCP.
MCP_ZAKAZANE_CELE = frozenset({"source", "pipeline", "criteria"})


def test_regula_13_serwer_mcp_nie_ma_krawedzi_do_akwizycji() -> None:
    """Reguła 13: `mcp_server.py` importuje wyłącznie `store` (odczyt) i `exporter`.

    To jest strukturalna postać zdania „serwer MCP czyta korpus, nie pobiera”. Zdanie da się
    sprawdzić przeglądem tego, co serwer robi, albo brakiem krawędzi importu, którą mogłoby
    pójść pobieranie. Drugi sposób nie wymaga niczyjej uwagi.
    """
    naruszenia = {
        path.relative_to(ROOT).as_posix(): sorted(package_targets(path) & MCP_ZAKAZANE_CELE)
        for path in istniejace("kio_tool/mcp_server.py")
        if package_targets(path) & MCP_ZAKAZANE_CELE
    }

    assert naruszenia == {}, f"serwer MCP sięga po akwizycję: {naruszenia}"


def test_skan_regul_2_i_13_zauwaza_podrzucony_import(tmp_path: Path) -> None:
    """Samosprawdzenie skanu krawędzi — jedyna niepusta część reguł 2, 8 i 13 w fazie 0."""
    podrzucony = tmp_path / "channel.py"
    podrzucony.write_text(
        "from ...store import Store\nfrom ...progress import Events\n", encoding="utf-8"
    )

    assert package_targets(podrzucony) & {"store"} == {"store"}
    assert package_targets(podrzucony) & MCP_ZAKAZANE_CELE == set()


# ------------------------------------------------- reguła 7: jedno miejsce na bibliotekę ekranu


# Reguła 7. Zawieranie, nie równość — ADR-0003 5.4: `rich` zna dziś wyłącznie `richtext.py`,
# `console.py` i `ui/render.py` nie istnieją, więc równość byłaby czerwona od pierwszego
# uruchomienia. Przechodzi w równość, gdy warstwa `ui/` powstanie.
MODULY_RICH = frozenset({"richtext.py", "ui/render.py", "console.py"})
MODULY_QUESTIONARY = frozenset({"ui/prompts.py"})


def uzytkownicy(biblioteka: str) -> frozenset[str]:
    """Moduły pakietu, które importują daną bibliotekę — ścieżki względem `kio_tool/`."""
    return frozenset(
        path.relative_to(PAKIET).as_posix()
        for path in pliki_pakietu()
        if biblioteka in imported_roots(path)
    )


def test_regula_7_biblioteka_ekranu_mieszka_tam_gdzie_rysowanie() -> None:
    """Reguła 7: `rich` zna wyłącznie warstwa rysująca, reszta operuje na modelach widoku."""
    assert uzytkownicy("rich") <= MODULY_RICH, (
        f"`rich` poza warstwą rysującą: {sorted(uzytkownicy('rich') - MODULY_RICH)}"
    )


def test_regula_7_pytajacy_siedzi_w_jednym_module() -> None:
    """Reguła 7: wymiana pytającego ma sens tylko wtedy, gdy `questionary` jest w jednym module."""
    assert uzytkownicy("questionary") <= MODULY_QUESTIONARY


def test_regula_7_kazdy_modul_rysujacy_naprawde_zna_rich() -> None:
    """Zawieranie przechodzi także dla zbioru pustego — stąd ta asercja obok.

    Bez niej reguła 7 zrobiłaby się zielona przez zniknięcie `richtext.py`, czyli przez
    zdarzenie, które powinno być najgłośniejsze z możliwych. To jest metatest 5.1 punkt 3
    w miejscu, w którym reguła ma żywych właścicieli. Do etapu IV (2026-09-18) `rich` znał
    dokładnie jeden moduł i test asertował `{"richtext.py"}`; z powstaniem `ui/render.py`
    przeszedł w równość z `MODULY_RICH`, tak jak zapowiadał ADR-0003 5.4 — `console.py` dostał
    wtedy konsolę z `richtext.make_console`, żeby tabela i wiersz pulsu szły jednym strumieniem.
    """
    assert uzytkownicy("rich") == MODULY_RICH, (
        f"`rich` znają: {sorted(uzytkownicy('rich'))}, a reguła 7 wymienia {sorted(MODULY_RICH)}. "
        "Moduł z listy, który przestał importować `rich`, jest wpisem martwym; moduł spoza listy "
        "jest naruszeniem łapanym przez test wyżej."
    )


# ---------------------------------------- reguła 10: do `rich` trafia tylko napis zneutralizowany


# Wywołania, których argumenty lądują na ekranie i mogą zostać potraktowane jak znaczniki.
TEKSTONOSNE_WYWOLANIA = frozenset(
    {
        "print",
        "print_json",
        "log",
        "rule",
        "add_task",
        "add_row",
        "add_column",
        "Table",
        "Column",
        "Columns",
        "Panel",
        "Group",
    }
)

# Wywołania, w których liczą się wyłącznie słowa kluczowe: `progress.update(task, advance=n)`
# ma pierwszy argument techniczny, a treść wnosi dopiero `description=`.
WYWOLANIA_TYLKO_SLOWA_KLUCZOWE = frozenset({"update"})

# Słowa kluczowe niosące treść — w odróżnieniu od `style=` czy `total=`.
TEKSTONOSNE_SLOWA_KLUCZOWE = frozenset({"title", "header", "description", "label", "renderable"})

# Jedyne funkcje, które robią z obcego napisu coś, co wolno wydrukować. `strip_control` tu
# **nie** należy: usuwa znaki sterujące, ale nie maskuje sekretu — a `richtext.safe` robi
# jedno i drugie, w kolejności, której pilnuje `tests/test_richtext.py`.
NEUTRALIZATORY = frozenset({"safe", "safe_or_none"})

# Obiekty `rich`, które rysują się same; napisy trafiły do nich wcześniej przez `safe`.
# Bez `Text`: `safe` zwraca `Text`, ale `Text(surowy)` blokuje znaczniki i przepuszcza ESC.
FABRYKI_WIDOKU = frozenset({"Table", "Column", "Columns", "Panel", "Group"})

BEZPIECZNE_ZRODLA = NEUTRALIZATORY | FABRYKI_WIDOKU


def rozpakuj(argument: ast.expr) -> ast.expr:
    """Zdejmuje `*` i komprehensje, żeby dojść do wyrażenia, które naprawdę niesie tekst."""
    while True:
        if isinstance(argument, ast.Starred):
            argument = argument.value
        elif isinstance(argument, ast.GeneratorExp | ast.ListComp | ast.SetComp):
            argument = argument.elt
        else:
            return argument


def nazwa_wywolania(node: ast.expr) -> str:
    """Nazwa wywoływanej funkcji: `safe(...)` i `x.safe(...)` dają to samo."""
    if not isinstance(node, ast.Call):
        return ""
    func = node.func
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def nazwy_bezpieczne(tree: ast.Module) -> set[str]:
    """Nazwy związane z bezpiecznym wyrażeniem: `tytul = safe_or_none(...)`, `t = Table(...)`.

    Zakres jest modułowy, nie funkcyjny — celowo. Skan ma łapać przeoczenia, a nazwa użyta
    w jednej funkcji i związana w innej to już kod, którego nikt nie napisze przypadkiem.
    """
    nazwy: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if nazwa_wywolania(rozpakuj(node.value)) in BEZPIECZNE_ZRODLA:
            nazwy.update(cel.id for cel in node.targets if isinstance(cel, ast.Name))
    return nazwy


def argumenty_tekstonosne(tree: ast.Module) -> list[tuple[ast.expr, int]]:
    """Argumenty, które trafią na ekran: pozycyjne i te słowa kluczowe, które niosą treść."""
    znalezione: list[tuple[ast.expr, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        nazwa = nazwa_wywolania(node)
        if nazwa in TEKSTONOSNE_WYWOLANIA:
            znalezione.extend((argument, argument.lineno) for argument in node.args)
        elif nazwa not in WYWOLANIA_TYLKO_SLOWA_KLUCZOWE:
            continue
        znalezione.extend(
            (kw.value, kw.value.lineno)
            for kw in node.keywords
            if kw.arg in TEKSTONOSNE_SLOWA_KLUCZOWE
        )
    return znalezione


def argument_bezpieczny(argument: ast.expr, nazwy: set[str]) -> bool:
    """Bezpieczne jest **całe** wyrażenie, nie wyrażenie z neutralizatorem gdzieś w środku.

    `f"{safe(a)} {surowy}"` zawiera `safe`, a mimo to przepuszcza `surowy` — dlatego liczy się
    korzeń wyrażenia, a nie to, co da się w nim znaleźć obchodem drzewa.
    """
    node = rozpakuj(argument)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True  # napis programu, nie z zewnątrz — wolno mu być znacznikiem
    if isinstance(node, ast.Name) and node.id in nazwy:
        return True
    return nazwa_wywolania(node) in BEZPIECZNE_ZRODLA


def pliki_rich() -> tuple[Path, ...]:
    """Moduły znające `rich` — dziś dokładnie `richtext.py`, jutro także `ui/render.py`."""
    return istniejace(*(f"kio_tool/{m}" for m in sorted(MODULY_RICH)))


def test_regula_10_do_rich_trafia_wylacznie_napis_zneutralizowany() -> None:
    """Reguła 10: na ekran idzie albo napis programu, albo wynik `richtext.safe`.

    Wejściem jest tu uzasadnienie orzeczenia — tekst pisany przez osoby trzecie, cytujący
    pisma stron, liczony w stronach. `rich` czyta nawiasy kwadratowe jako znaczniki, więc
    napis z uzasadnienia wywraca wypis albo wstawia klikalny odnośnik na obcy adres.

    Skan jest składniowy i taki ma być. Jedna zależność, której nie widzi: reguła 9 („`cli.py`
    nie pisze żadnego zdania”) jest warunkiem, przy którym to sprawdzenie da się prowadzić
    modułami zamiast analizą przepływu przez cały pakiet. Reguła 9 ma własny skan niżej
    (od 2026-09-18, dnia powstania `cli.py`; do tego dnia była wyzwalaczem w `POZA_SKANEM`).
    """
    naruszenia: list[str] = []
    for path in pliki_rich():
        tree = drzewo(path)
        nazwy = nazwy_bezpieczne(tree)
        naruszenia.extend(
            f"{path.relative_to(ROOT).as_posix()}:{linia}"
            for argument, linia in argumenty_tekstonosne(tree)
            if not argument_bezpieczny(argument, nazwy)
        )

    assert naruszenia == [], f"napis z zewnątrz idzie do rich z pominięciem `safe`: {naruszenia}"


@pytest.mark.parametrize(
    ("zrodlo", "naruszenia"),
    [
        ("console.print(safe(nazwa))", 0),
        ('console.print("[red]Blad:[/red]", safe(tekst))', 0),
        ("tabela = Table()\nconsole.print(tabela)", 0),
        ("tabela.add_row(*(safe(komorka) for komorka in wiersz))", 0),
        ("tytul = safe_or_none(t)\ntabela = Table(title=tytul)", 0),
        ('postep.add_task("Pobieranie orzeczeń", total=n)', 0),
        ("postep.update(zadanie, advance=n)", 0),
        # sygnatura i uzasadnienie wprost, w f-stringu, z rekordu, sklejone
        ("console.print(orzeczenie.uzasadnienie)", 1),
        ('console.print(f"Sygnatura: {sygnatura}")', 1),
        ('console.print(rekord["sentencja"])', 1),
        ('console.print("a" + nazwa)', 1),
        ("console.print(str(wyjatek))", 1),
        # kształty, które przepuszczała pierwsza wersja skanu w `ceidg-tool`
        ("tabela.add_row(sygnatura)", 1),
        ("Table(title=sygnatura)", 1),
        ("postep.update(zadanie, description=orzeczenie.sygnatura)", 1),
        ("t = Text(sygnatura)\nconsole.print(t)", 1),
        ('console.print(f"{safe(a)} {surowy}")', 1),
        ("console.print(strip_control(x))", 1),
        ("console.print(Columns(sygnatury))", 1),
    ],
)
def test_skan_reguly_10_odroznia_napis_programu_od_napisu_ze_zrodla(
    zrodlo: str, naruszenia: int
) -> None:
    """Skan bez tej próby byłby nie do odróżnienia od testu, który zawsze przechodzi.

    Druga połowa listy to kształty, które przepuszczała pierwsza wersja tego skanu
    w `ceidg-tool` — każdy znaleziony w przeglądzie kodu, żaden wymyślony. Przypadek
    `Text(sygnatura)` jest naruszeniem celowo: `Text` blokuje znaczniki, ale przepuszcza
    znaki sterujące i nie maskuje sekretu, więc nie jest neutralizatorem.
    """
    tree = ast.parse(zrodlo)
    nazwy = nazwy_bezpieczne(tree)

    znalezione = [
        argument
        for argument, _ in argumenty_tekstonosne(tree)
        if not argument_bezpieczny(argument, nazwy)
    ]

    assert len(znalezione) == naruszenia


def test_fabryka_ktora_uswieca_napis_jest_sama_skanowana() -> None:
    """Niezmiennik zamykający całą klasę dziur zamiast kolejnej pojedynczej.

    Wpisanie obiektu do `FABRYKI_WIDOKU` mówi „temu wolno wydrukować to, co w nim siedzi”.
    Jeśli jego własne argumenty nie są sprawdzane, to zdanie jest obietnicą bez pokrycia:
    `console.print(Columns(sygnatury))` przechodziłoby bez śladu. W `ceidg-tool` dokładnie
    tak wyglądało znalezisko z przeglądu — dwa razy z rzędu.
    """
    assert FABRYKI_WIDOKU <= TEKSTONOSNE_WYWOLANIA


# ------------------------------------------------- reguła 9: `cli.py` nie drukuje niczym sam


# `cli.py` nie drukuje **niczym**. `typer.echo` jest w programie na `typer` odruchem pierwszym,
# a `console.log` odruchem przy szukaniu błędu — skan pilnujący samego `console.print` dałby
# fałszywe poczucie domknięcia reguły 9. Każdy kanał ekranu z reguły 10 jest tu zakazany
# (`test_kazdy_kanal_ekranu_z_reguly_10_jest_zakazany_w_cli`). Skan przeniesiony z `ceidg-tool`
# w dniu powstania `cli.py` (2026-09-18) — do tego dnia reguła 9 stała w `POZA_SKANEM` z uwagą,
# że „połowiczny skan byłby gorszy niż jego brak"; obie połowy (kanały wyjścia i układanie treści
# pytań) są tu razem.
WYWOLANIA_WYJSCIA = TEKSTONOSNE_WYWOLANIA | {"echo", "secho"}

# Korzenie, po których poznajemy zapis wprost do strumienia — także po `from sys import stdout`.
KORZENIE_STRUMIENI = frozenset({"sys", "stdout", "stderr"})

# Pytania też drukują, ale ich zakazać nie można: przyszłe `typer.prompt(hide_input=True)` musi
# zostać w `cli.py`, bo tylko ono umie ukryć wpisywany klucz. Reguła 9 zabrania więc nie samego
# pytania, lecz **ułożenia jego treści** na miejscu.
WYWOLANIA_PYTAJACE = frozenset({"prompt", "confirm"})

# Słowo kluczowe, którym `typer` przyjmuje zdanie pomocy — też jest zdaniem do użytkownika.
SLOWO_POMOCY = "help"
MODUL_TEKSTOW = "texts"


def _korzen_odbiorcy(node: ast.Attribute) -> str:
    """Korzeń łańcucha `sys.stdout.write` — po to, żeby nie mylić go z `path.write_text`.

    Sam `stdout` też jest korzeniem: po `from sys import stdout` łańcuch nie zaczyna się od `sys`.
    """
    wartosc: ast.expr = node.value
    while isinstance(wartosc, ast.Attribute):
        wartosc = wartosc.value
    return wartosc.id if isinstance(wartosc, ast.Name) else ""


def wywolania_wyjscia(tree: ast.Module) -> list[int]:
    """Linie, w których moduł drukuje czymkolwiek: `rich`, `print`, `typer.echo`, `sys.stdout`."""
    linie: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        nazwa = nazwa_wywolania(node)
        if nazwa == "write":
            if (
                isinstance(node.func, ast.Attribute)
                and _korzen_odbiorcy(node.func) in KORZENIE_STRUMIENI
            ):
                linie.append(node.lineno)
        elif nazwa in WYWOLANIA_WYJSCIA:
            linie.append(node.lineno)
    return linie


def _ulozony(node: ast.expr) -> bool:
    """Czy wyrażenie układa napis: f-string, sklejenie, `%` (oba to `BinOp`) albo `.format`."""
    return isinstance(node, ast.JoinedStr | ast.BinOp) or (
        isinstance(node, ast.Call) and nazwa_wywolania(node) == "format"
    )


def _nazwy_ulozone(tree: ast.Module) -> set[str]:
    """Nazwy związane z ułożonym napisem — `linia = f"…"` i dopiero potem `prompt(linia)`.

    Ten sam obchód, którym reguła 10 rozpoznaje nazwy bezpieczne, tylko w drugą stronę:
    tam szukamy neutralizatora, tu autora zdania.
    """
    nazwy: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _ulozony(node.value):
            nazwy.update(cel.id for cel in node.targets if isinstance(cel, ast.Name))
    return nazwy


def argumenty_ulozone(tree: ast.Module) -> list[int]:
    """Argumenty pytań, których treść powstaje na miejscu: f-string, sklejenie, `format`, `%`.

    Przekazanie `texts.X` dalej jest w porządku — to `ui` jest autorem zdania. Dopisanie do
    niego czegokolwiek w `cli.py` czyni autorem `cli.py`, czyli łamie regułę 9. Także słowa
    kluczowe: pierwszy parametr `typer.prompt` nazywa się `text`, więc `typer.prompt(text=f"…")`
    omijało skan patrzący wyłącznie na argumenty pozycyjne (znalezisko z `ceidg-tool`).
    """
    ulozone_tu = _nazwy_ulozone(tree)
    linie: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or nazwa_wywolania(node) not in WYWOLANIA_PYTAJACE:
            continue
        kandydaci = [*node.args, *(kw.value for kw in node.keywords)]
        linie.extend(
            argument.lineno
            for argument in kandydaci
            if _ulozony(argument) or (isinstance(argument, ast.Name) and argument.id in ulozone_tu)
        )
    return linie


def pomoce_spoza_tekstow(tree: ast.Module) -> list[int]:
    """Linie, w których `help=` nie jest atrybutem modułu `texts`.

    Zdanie pomocy przy fladze jest zdaniem do użytkownika tak samo jak komunikat — a `typer`
    przyjmuje je słowem kluczowym, którego żaden skan wywołań wyjścia nie widzi.
    """
    linie: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != SLOWO_POMOCY:
                continue
            wartosc = kw.value
            if not (
                isinstance(wartosc, ast.Attribute)
                and isinstance(wartosc.value, ast.Name)
                and wartosc.value.id == MODUL_TEKSTOW
            ):
                linie.append(wartosc.lineno)
    return linie


def pliki_cli() -> tuple[Path, ...]:
    """`cli.py` i jego przedłużenie `obsluga.py` (wydruki wspólne z kreatorem, ADR-0008 Z-7) —
    oba stoją po tej samej stronie reguły 9: żadnego zdania własnego, każdy napis z `texts`."""
    return istniejace("kio_tool/cli.py", "kio_tool/obsluga.py")


def _naruszenia_w_cli(skan: Callable[[ast.Module], list[int]]) -> list[str]:
    return [
        f"{path.relative_to(ROOT).as_posix()}:{linia}"
        for path in pliki_cli()
        for linia in skan(drzewo(path))
    ]


def test_regula_9_cli_nie_drukuje_niczym_sam() -> None:
    """Reguła 9: `cli.py` nie ma własnego kanału wyjścia — zdania idą przez `ui/texts.py`,
    a druk przez `console.wypisz`.

    To jest warunek, który czyni regułę 10 sprawdzalną skanem: dopóki `cli.py` drukował sam,
    „każdy napis z zewnątrz przechodzi przez `safe`” wymagałoby analizy przepływu danych przez
    cały pakiet. Sprawdzamy wszystkie kanały, nie tylko `rich`: w programie na `typer` pierwszym
    odruchem jest `typer.echo`, a nie `console.print`.
    """
    assert _naruszenia_w_cli(wywolania_wyjscia) == [], "`cli.py` drukuje sam"


def test_regula_9_cli_nie_uklada_tresci_pytan() -> None:
    """Reguła 9 obejmuje też pytania, nie tylko komunikaty (w `ceidg-tool` `_confirm` doklejał
    w `cli.py` klamrę `[t/N]` do zdania z `texts` — dokładnie to, czego reguła zabrania)."""
    assert _naruszenia_w_cli(argumenty_ulozone) == [], "`cli.py` układa treść pytania sam"


def test_regula_9_pomoc_flag_pochodzi_z_texts() -> None:
    """Zdanie pomocy przy fladze jest zdaniem do użytkownika — jego autorem jest `ui/texts.py`."""
    assert _naruszenia_w_cli(pomoce_spoza_tekstow) == [], "`cli.py` pisze pomoc flagi sam"


@pytest.mark.parametrize(
    ("zrodlo", "naruszenia"),
    [
        ("wypisz(texts.PRZERWANE)", 0),
        ("sciezka.write_text(dane, encoding='utf-8')", 0),
        ("typer.confirm(texts.PYTANIE, default=False)", 0),
        ('print("cokolwiek")', 1),
        ("typer.echo(rekord)", 1),
        ('typer.secho(f"Sygnatura: {sygnatura}")', 1),
        ("sys.stdout.write(sygnatura)", 1),
        ("stdout.write(sygnatura)", 1),
        ("console.log(rekord)", 1),
        ("console.print(safe(sygnatura))", 1),
    ],
    ids=[
        "wypisz_z_texts",
        "zapis_do_pliku_nie_jest_drukiem",
        "pytanie_z_texts",
        "print",
        "typer_echo",
        "typer_secho",
        "sys_stdout",
        "stdout_z_importu",
        "console_log",
        "console_print_nawet_zneutralizowany",
    ],
)
def test_skan_reguly_9_widzi_kazdy_kanal_wyjscia(zrodlo: str, naruszenia: int) -> None:
    """`cli.py` ma nie drukować niczym — także `print`, `typer.echo` i `sys.stdout`.

    Ostatni przypadek jest z rozmysłem naruszeniem: w `cli.py` nawet zneutralizowany
    `console.print` jest zdaniem napisanym poza `ui/texts.py`, czyli złamaniem reguły 9.
    """
    assert len(wywolania_wyjscia(ast.parse(zrodlo))) == naruszenia


@pytest.mark.parametrize(
    ("zrodlo", "naruszenia"),
    [
        ("typer.prompt(texts.PYTANIE_O_KLUCZ, hide_input=True)", 0),
        ("typer.confirm(texts.PYTANIE, default=False)", 0),
        ('typer.prompt(f"{pytanie} [t/N]")', 1),
        ('typer.confirm(texts.PYTANIE + " (t/n)")', 1),
        ('typer.prompt("{} [t/N]".format(pytanie))', 1),
        ('typer.prompt(text=f"{pytanie} [t/N]")', 1),
        ("linia = f'{p} [t/N]'\ntyper.prompt(linia)", 1),
    ],
    ids=[
        "zdanie_z_texts",
        "potwierdzenie_z_texts",
        "f_string",
        "sklejenie",
        "format",
        "slowo_kluczowe_text",
        "nazwa_zwiazana_wczesniej",
    ],
)
def test_skan_reguly_9_odroznia_przekazanie_zdania_od_ulozenia_go(
    zrodlo: str, naruszenia: int
) -> None:
    """Granica przebiega między „przekazać zdanie z `ui`” a „ułożyć je tutaj”."""
    assert len(argumenty_ulozone(ast.parse(zrodlo))) == naruszenia


@pytest.mark.parametrize(
    ("zrodlo", "naruszenia"),
    [
        ('typer.Option("--od", help=texts.POMOC_OD)', 0),
        ('typer.Option("--od", help="początek zakresu")', 1),
        ('typer.Option("--od", help=f"{texts.POMOC_OD} (RRRR-MM-DD)")', 1),
        ('typer.Option("--od")', 0),
    ],
    ids=["z_texts", "wprost", "ulozona_z_texts", "bez_pomocy"],
)
def test_skan_reguly_9_widzi_pomoc_flagi_pisana_na_miejscu(zrodlo: str, naruszenia: int) -> None:
    assert len(pomoce_spoza_tekstow(ast.parse(zrodlo))) == naruszenia


def test_kazdy_kanal_ekranu_z_reguly_10_jest_zakazany_w_cli() -> None:
    """Kanał, który liczy się w regule 10, ma się liczyć i w regule 9 — rozjazd między zbiorami
    oznaczałby, że jedna reguła łapie `console.log`, a druga nie."""
    assert TEKSTONOSNE_WYWOLANIA <= WYWOLANIA_WYJSCIA


# ----------------------------------------- reguła 11: jeden właściciel na protokół wyjścia


class Konstrukt(NamedTuple):
    """Konstrukt otwierający połączenie sieciowe: moduł biblioteki i nazwa w nim."""

    modul: str
    nazwa: str


# Reguła 11 w brzmieniu z ADR-0003 sekcja 4. Tablica wymienia **konstrukty, nie biblioteki**,
# i to jest cała treść rozstrzygnięcia 2: `httpx` nie obsługuje FTP, a polityka wyjścia
# odmawia wszystkiemu poza `https`, więc zdanie „jedno miejsce buduje klienta i jest bramką
# wyjścia” obejmowało kanał spoza HTTP wyłącznie na rysunku. W `ceidg-tool` ten sam kształt
# wystąpił raz wcześniej: skan dopasowywał dosłowną nazwę `httpx` i przepuszczał `httpx2`
# spod SDK modelu, raportując się jako domknięty przy pokryciu połowy ruchu.
#
# Wartością jest **zbiór** dozwolonych plików, nie pojedynczy właściciel (ADR-0003 5.2).
# Zbiór pusty znaczy „żaden plik nie ma prawa tego zbudować”; żeby go zbudować, trzeba
# najpierw dopisać właściciela **tutaj** i regułę wyjścia do dokumentu architektury.
EGRESS_OWNERS: dict[Konstrukt, frozenset[str]] = {
    Konstrukt("httpx", "Client"): frozenset({"kio_tool/httpclient.py"}),
    Konstrukt("httpx", "AsyncClient"): frozenset({"kio_tool/httpclient.py"}),
    # Kanał FTP nie ma dziś właściciela i to jest stan przed pomiarem 1 (ADR-0003 decyzja 9),
    # a nie przeoczenie. W dniu, w którym ktokolwiek napisze `ftplib.FTP(...)`, ten test jest
    # czerwony i wymusza decyzję zamiast pozwolić ją przemilczeć.
    Konstrukt("ftplib", "FTP"): frozenset(),
    Konstrukt("ftplib", "FTP_TLS"): frozenset(),
    Konstrukt("socket", "socket"): frozenset(),
    # `tests/test_pomiar21_blokada_sieci.py` woła `socket.create_connection` i **musi**:
    # przedmiotem pomiaru 21 jest właśnie to, czy blokada sieci sięga gniazda, a nie tylko
    # transportu httpx. Gdyby tablica mapowała konstrukt na jeden plik-właściciel, ten
    # istniejący i poprawny test byłby naruszeniem od pierwszego uruchomienia skanu, a
    # odruchem — dopisanie wyjątku (ADR-0003 5.2).
    Konstrukt("socket", "create_connection"): frozenset({"tests/test_pomiar21_blokada_sieci.py"}),
    Konstrukt("urllib.request", "urlopen"): frozenset(),
    Konstrukt("urllib.request", "build_opener"): frozenset(),
    Konstrukt("asyncio", "open_connection"): frozenset(),
}


def _mapy_importow(tree: ast.Module) -> tuple[dict[str, str], dict[str, Konstrukt]]:
    """Nazwy widoczne w pliku: osobno moduły, osobno konstrukty wzięte wprost z importu.

    `from urllib import request` trafia do obu map: `request.urlopen(...)` czyni z niego
    moduł, a `request(...)` konstrukt. Rejestrujemy obie możliwości, bo AST nie rozstrzyga,
    która zachodzi, a tablica i tak wymienia tylko te pary, które coś znaczą.
    """
    moduly: dict[str, str] = {}
    wprost: dict[str, Konstrukt] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    moduly[alias.asname] = alias.name
                else:
                    # `import urllib.request` wiąże nazwę `urllib`; dalsze człony czyta
                    # dopiero łańcuch atrybutów w wywołaniu.
                    korzen = alias.name.split(".")[0]
                    moduly[korzen] = korzen
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                widoczna = alias.asname or alias.name
                moduly[widoczna] = f"{node.module}.{alias.name}"
                wprost[widoczna] = Konstrukt(node.module, alias.name)
    return moduly, wprost


def _lancuch_atrybutow(node: ast.expr) -> list[str] | None:
    """`urllib.request.urlopen` → `["urllib", "request", "urlopen"]`; `self.x.y` → `None`."""
    czesci: list[str] = []
    while isinstance(node, ast.Attribute):
        czesci.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    czesci.append(node.id)
    return list(reversed(czesci))


def konstrukty_wyjscia(path: Path) -> set[Konstrukt]:
    """Konstrukty, które w tym pliku **powstają** — po wywołaniu, nie po adnotacji typu.

    Adnotacja (`http: httpx.Client | None`) jest niegroźna: przyjąć gotowego klienta wolno
    każdemu, kto go dostaje. Groźne jest utworzenie go z pominięciem polityki wyjścia.

    Liczą się wszystkie formy zapisu — `httpx.Client(…)`, `Client(…)` po `from httpx import
    Client`, `hx.Client(…)` po `import httpx as hx`, `urllib.request.urlopen(…)` po `import
    urllib.request` oraz `ur.urlopen(…)` po `import urllib.request as ur`. Powód jest ten sam,
    dla którego `package_targets` czyta oba warianty importu: reguła mówi o zależności, a nie
    o składni, którą ktoś wybrał. Skan pilnujący jednej pisowni wygląda na działający
    dokładnie do dnia, w którym ktoś napisze drugą.
    """
    tree = drzewo(path)
    moduly, wprost = _mapy_importow(tree)
    znalezione: set[Konstrukt] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            konstrukt = wprost.get(node.func.id)
            if konstrukt is not None:
                znalezione.add(konstrukt)
            continue
        lancuch = _lancuch_atrybutow(node.func)
        if lancuch is None or len(lancuch) < 2 or lancuch[0] not in moduly:
            continue
        znalezione.add(Konstrukt(".".join([moduly[lancuch[0]], *lancuch[1:-1]]), lancuch[-1]))
    return znalezione


def pliki_regula_11() -> tuple[Path, ...]:
    """Zakres reguły 11: `kio_tool/`, `tests/` oraz `scripts/`, jeśli powstanie.

    Sonda niesie ten sam ruch co narzędzie, więc reguła obowiązuje i ją. Testy są w zakresie
    celowo: w `ceidg-tool` to `tests/support.py` budował własnego klienta i dlatego jedyna
    produkcyjna linia tworząca klienta nie miała pokrycia — a że httpx pomija proxy ze
    środowiska, gdy transport jest podany, ten właśnie szew ukrywał defekt.
    """
    return (*moduly_py(PAKIET), *moduly_py(TESTY), *moduly_py(SKRYPTY))


def test_regula_11_konstrukt_wyjscia_buduje_wylacznie_jego_wlasciciel() -> None:
    """Reguła 11: jeden właściciel na protokół, jedna kopia polityki wyjścia.

    `httpx` z `trust_env=True` i bez podanego transportu bierze `HTTPS_PROXY` ze środowiska
    (0.28.1, `_client.py`: `allow_env_proxies = trust_env and transport is None`), więc żądanie
    wychodzi przez host, którego nikt nie porównał ze zbiorem `allowed`. „Żadne połączenie nie
    idzie poza listę” da się sprawdzić przeczytaniem jednego modułu dopóty, dopóki klient
    powstaje w jednym miejscu; drugi konstruktor zamienia to zdanie w analizę całego pakietu.
    """
    naruszenia: dict[str, list[Konstrukt]] = {}
    for path in pliki_regula_11():
        wzgledna = path.relative_to(ROOT).as_posix()
        nieuprawnione = sorted(
            konstrukt
            for konstrukt in konstrukty_wyjscia(path) & set(EGRESS_OWNERS)
            if wzgledna not in EGRESS_OWNERS[konstrukt]
        )
        if nieuprawnione:
            naruszenia[wzgledna] = nieuprawnione

    assert naruszenia == {}, (
        f"konstrukt wyjścia poza modułem-właścicielem: {naruszenia}. Lekarstwem jest "
        "wywołanie właściciela protokołu albo — jeśli protokół jest nowy — decyzja właściciela "
        "projektu i wpis w `EGRESS_OWNERS` wraz z regułą wyjścia w dokumencie architektury. "
        "Nigdy dopisanie pliku do zbioru po to, żeby było zielono."
    )


def test_regula_11_kazdy_wpisany_wlasciciel_istnieje_i_naprawde_nim_jest() -> None:
    """Metatest: właściciel, który zniknął albo przestał budować, zamienia regułę w pustkę.

    Zmiana nazwy `httpclient.py` nie może po cichu sprawić, że reguła 11 nie ma czego pilnować
    — a tak właśnie wygląda jej najcichsza awaria: zbiór budowniczych staje się pusty i wszystko
    jest zielone.
    """
    wlasciciele: dict[str, set[Konstrukt]] = {}
    for konstrukt, pliki in EGRESS_OWNERS.items():
        for plik in pliki:
            wlasciciele.setdefault(plik, set()).add(konstrukt)

    assert wlasciciele, "tablica bez ani jednego właściciela nie pilnuje niczego"
    for plik, konstrukty in sorted(wlasciciele.items()):
        assert (ROOT / plik).is_file(), f"{plik} nie istnieje, a stoi w EGRESS_OWNERS"
        zbudowane = konstrukty_wyjscia(ROOT / plik) & konstrukty
        assert zbudowane, (
            f"{plik} jest w tablicy właścicielem {sorted(konstrukty)}, ale nie buduje żadnego "
            "z nich — wpis jest martwy, a reguła w tej pozycji nic nie sprawdza."
        )


@pytest.mark.parametrize(
    ("zrodlo", "oczekiwane"),
    [
        ("import httpx\nc = httpx.Client()\n", {Konstrukt("httpx", "Client")}),
        ("from httpx import Client\nc = Client()\n", {Konstrukt("httpx", "Client")}),
        ("from httpx import Client as C\nc = C()\n", {Konstrukt("httpx", "Client")}),
        ("import httpx as hx\nc = hx.Client()\n", {Konstrukt("httpx", "Client")}),
        ("import httpx\nc = httpx.AsyncClient()\n", {Konstrukt("httpx", "AsyncClient")}),
        ("import ftplib\nf = ftplib.FTP('x')\n", {Konstrukt("ftplib", "FTP")}),
        ("from ftplib import FTP_TLS\nf = FTP_TLS()\n", {Konstrukt("ftplib", "FTP_TLS")}),
        (
            "import socket\ns = socket.create_connection(a)\n",
            {Konstrukt("socket", "create_connection")},
        ),
        (
            "import urllib.request\nr = urllib.request.urlopen(u)\n",
            {Konstrukt("urllib.request", "urlopen")},
        ),
        (
            "import urllib.request as ur\nr = ur.urlopen(u)\n",
            {Konstrukt("urllib.request", "urlopen")},
        ),
        (
            "from urllib import request\nr = request.urlopen(u)\n",
            {Konstrukt("urllib.request", "urlopen")},
        ),
        (
            "from urllib.request import build_opener\no = build_opener()\n",
            {Konstrukt("urllib.request", "build_opener")},
        ),
        (
            "import asyncio\nr = await asyncio.open_connection(h, p)\n",
            {Konstrukt("asyncio", "open_connection")},
        ),
        # adnotacja, transport i fabryka właściciela to nie utworzenie konstruktu wyjścia
        ("import httpx\ndef f(c: httpx.Client) -> None: ...\n", set()),
        ("import httpx\nt = httpx.MockTransport(h)\n", set()),
        ("import httpx\nt = httpx.HTTPTransport(verify=True, trust_env=False)\n", set()),
        (
            "from kio_tool.httpclient import build_http_client\n"
            "c = build_http_client(user_agent=u)\n",
            set(),
        ),
        # cudza klasa o tej samej nazwie nie jest konstruktem wyjścia
        ("from zewnetrzne import Client\nc = Client()\n", set()),
        ("import zewnetrzne\nc = zewnetrzne.Client()\n", set()),
        ("s = self.socket.socket()\n", set()),
    ],
    ids=[
        "httpx_modul",
        "httpx_z_importu",
        "httpx_alias_z_importu",
        "httpx_alias_modulu",
        "httpx_async",
        "ftplib_modul",
        "ftplib_z_importu",
        "socket_polaczenie",
        "urllib_modul_kropkowany",
        "urllib_alias_modulu",
        "urllib_modul_z_pakietu",
        "urllib_funkcja_z_importu",
        "asyncio_strumien",
        "adnotacja",
        "transport_atrapy",
        "transport_wlasciwy",
        "fabryka_wlasciciela",
        "obca_klasa",
        "obcy_modul",
        "atrybut_obiektu",
    ],
)
def test_skan_reguly_11_odroznia_zbudowanie_konstruktu_od_nazwania_go(
    tmp_path: Path, zrodlo: str, oczekiwane: set[Konstrukt]
) -> None:
    """Skan, który zawsze przechodzi, jest nie do odróżnienia od działającego.

    W fazie 0 to jest **jedyna** niepusta część reguły 11 dla wszystkich protokołów poza HTTP:
    `ftplib`, `urllib` i `asyncio` nie występują dziś w drzewie ani razu, więc skan na prawdziwym
    drzewie nie ma dla nich czego znaleźć.

    Przypadki „obca_klasa” i „obcy_modul” są tu, bo skan po samej nazwie `Client` uznałby za
    naruszenie każdą klasę o tej nazwie i zmusiłby do wyjątków — a lista wyjątków to miejsce,
    w którym reguła cicho przestaje obowiązywać. Przypadek „transport_wlasciwy” pilnuje, że
    `httpx.HTTPTransport` z `httpclient.py` nie jest konstruktem wyjścia: bramką jest klient,
    transport jest jej częścią.
    """
    modul = tmp_path / "probny.py"
    modul.write_text(zrodlo, encoding="utf-8")

    assert konstrukty_wyjscia(modul) & set(EGRESS_OWNERS) == oczekiwane


def test_skan_reguly_11_zapala_sie_na_protokole_bez_wlasciciela(tmp_path: Path) -> None:
    """Pozycja z pustym zbiorem właścicieli — cała treść rozstrzygnięcia 2 ADR-0003.

    Adapter FTP mógłby dziś otworzyć gniazdo dokądkolwiek i nic nie byłoby czerwone, gdyby
    reguła mówiła o `httpx` zamiast o konstrukcie. Ten test jest dowodem, że mówi o konstrukcie:
    plik podrzucony w miejsce przyszłego kanału zapala regułę, choć `httpx` nie pada w nim ani razu.
    """
    podrzucony = tmp_path / "channel.py"
    podrzucony.write_text("import ftplib\n\ndef pobierz():\n    return ftplib.FTP('x')\n", "utf-8")

    zbudowane = konstrukty_wyjscia(podrzucony) & set(EGRESS_OWNERS)

    assert zbudowane == {Konstrukt("ftplib", "FTP")}
    assert all(EGRESS_OWNERS[k] == frozenset() for k in zbudowane), (
        "Konstrukt bez właściciela ma nie mieć właściciela — gdyby go dostał, ten test straciłby "
        "przedmiot i trzeba go przepisać razem z decyzją, która właściciela wyznaczyła."
    )


# --------------------------------------- reguła 12: właściciel klienta SDK modelu niewyznaczony


# Reguła 12 z audytu 8.3. W Kio faza 4 jest **osobnym procesem** (architektura 4.10, decyzja 3),
# więc problem dwóch stosów HTTP z `ceidg-tool` tu nie wchodzi, a `anthropic` nie stoi ani
# w zależnościach, ani w zależnościach deweloperskich. Właściciel nie został więc wyznaczony
# i zbiór jest pusty — ta sama postać, co pozycje bez właściciela w `EGRESS_OWNERS`: żeby
# zaimportować SDK modelu, trzeba najpierw dopisać właściciela tutaj i regułę do dokumentu.
WLASCICIELE_SDK_MODELU: frozenset[str] = frozenset()


def test_regula_12_nikt_nie_importuje_sdk_modelu_bo_wlasciciel_nie_zostal_wyznaczony() -> None:
    """Reguła 12 jako wyzwalacz, nie jako pamięć o niej.

    Pozycja w sekcji „do rozstrzygnięcia” jest czyimś wspomnieniem; ten test zapala się sam
    w dniu, w którym ktoś zaimportuje SDK — w pakiecie, w teście albo w sondzie. Wtedy zapada
    decyzja: kto jest właścicielem i czy każde wywołanie ma jawne `api_key=` i `http_client=`.
    """
    uzywajacy = {
        path.relative_to(ROOT).as_posix()
        for path in pliki_regula_11()
        if "anthropic" in imported_roots(path)
    }

    assert uzywajacy <= WLASCICIELE_SDK_MODELU, (
        f"SDK modelu importują: {sorted(uzywajacy)}, a reguła 12 nie ma dziś wyznaczonego "
        "właściciela. Klient SDK bez jawnego `api_key=` sięga po własny łańcuch poświadczeń, "
        "a bez jawnego `http_client=` buduje transport poza bramką wyjścia z `httpclient.py`."
    )


# ------------------------------- reguły 17 i 21: kanał jest pakietem, kontrakt nie jest sierotą


# Reguła 21 z ADR-0003 sekcja 4: bezpośrednio w `source/` wolno leżeć wyłącznie modułom
# wspólnym z wyliczonej listy. Każdy inny wpis jest katalogiem kanału.
MODULY_WSPOLNE_SOURCE = frozenset({"__init__.py", "protocol.py", "contract.py", "registry.py"})
PLIKI_KANALU = ("__init__.py", "channel.py", "contract.yaml")

# Klucz `REGISTRY`, którego nie da się odczytać jako literału. Nie równa się żadnej nazwie
# katalogu, więc porównanie trzech zbiorów zapala się **głośno** zamiast przejść pusto.
KLUCZ_NIECZYTELNY = "<nieczytelny>"


class StanSource(NamedTuple):
    """Trzy zbiory reguły 21 plus to, co skan po drodze przeczytał (do metatestu)."""

    moduly_luzem: frozenset[str]
    katalogi: frozenset[str]
    z_kanalem: frozenset[str]
    z_kontraktem: frozenset[str]
    bez_init: frozenset[str]
    zle_nazwy: frozenset[str]
    klucze_registry: frozenset[str]
    odczytane: frozenset[str]


def klucze_registry(path: Path) -> frozenset[str]:
    """Klucze `REGISTRY` odczytane ze składni, bez importowania modułu.

    Importowanie wykonałoby kod i wymagało, żeby cały pakiet dał się zaimportować — a reguła
    ma działać także wtedy, gdy kanał jest w połowie napisany. Czytamy literał: zarówno
    `"uzp": UzpChannel`, jak i `SourceName("uzp"): UzpChannel`, bo `SourceName` jest `NewType`
    i mypy strict wymaga jawnego opakowania.
    """
    if not path.is_file():
        return frozenset()
    for node in ast.walk(drzewo(path)):
        # `REGISTRY: dict[SourceName, type[Channel]] = {...}` jest `AnnAssign`, a `REGISTRY = {...}`
        # zwykłym `Assign`. Reguła 21 wymaga adnotacji, ale skan ma widzieć obie formy: brak
        # adnotacji jest usterką dla mypy, nie powodem, żeby przestać czytać klucze.
        if isinstance(node, ast.AnnAssign):
            cele: list[ast.expr] = [node.target]
        elif isinstance(node, ast.Assign):
            cele = list(node.targets)
        else:
            continue
        if not any(isinstance(cel, ast.Name) and cel.id == "REGISTRY" for cel in cele):
            continue
        wartosc = node.value
        if not isinstance(wartosc, ast.Dict):
            return frozenset({KLUCZ_NIECZYTELNY})
        return frozenset(_klucz_literalny(klucz) for klucz in wartosc.keys)
    return frozenset()


def _klucz_literalny(klucz: ast.expr | None) -> str:
    """`"uzp"` i `SourceName("uzp")` dają ten sam napis; wszystko inne jest nieczytelne."""
    if isinstance(klucz, ast.Constant) and isinstance(klucz.value, str):
        return klucz.value
    if isinstance(klucz, ast.Call) and len(klucz.args) == 1:
        return _klucz_literalny(klucz.args[0])
    return KLUCZ_NIECZYTELNY


def zbadaj_source(source: Path) -> StanSource:
    """Trzy zbiory reguły 21 wyznaczone z drzewa i z kodu, nigdy z wypisanej listy kanałów.

    Roster kanałów **nie jest w teście wypisany** i to jest warunek, przy którym ta reguła
    da się mieć przed bramką fazy 0 (ADR-0003, „Jak to godzi się z «kanał nie jest wybrany»”).
    Przy pustym `source/` wszystkie trzy zbiory są puste i reguła przechodzi zgodnie ze stanem
    projektu; ciężar dowodu niosą wtedy samosprawdzenia niżej.

    Zakres: **moduły `.py` luzem** i **katalogi**. `.gitkeep` nie jest ani jednym, ani drugim —
    jest znacznikiem pustego katalogu, czyli dokładnie tego stanu, o którym ADR-0003 mówi, że
    reguła ma go przepuścić. `__pycache__` jest wytworem interpretera, nie wpisem, który ktoś
    napisał. Oba pominięcia są zawężeniem **zakresu**, nie listą wyjątków: nie wymieniają
    żadnego modułu ani kanału z nazwy i nie dają się rozszerzyć o kolejny wpis.
    """
    if not source.is_dir():
        return StanSource(*([frozenset()] * 8))
    wpisy = sorted(p for p in source.iterdir() if p.name != "__pycache__")
    odczytane = {p.name for p in wpisy}
    moduly_luzem = {
        p.name
        for p in wpisy
        if p.is_file() and p.suffix == ".py" and p.name not in MODULY_WSPOLNE_SOURCE
    }
    katalogi = {p.name for p in wpisy if p.is_dir()}
    z_kanalem: set[str] = set()
    z_kontraktem: set[str] = set()
    bez_init: set[str] = set()
    for nazwa in katalogi:
        for plik in PLIKI_KANALU:
            odczytane.add(f"{nazwa}/{plik}")
        if (source / nazwa / "channel.py").is_file():
            z_kanalem.add(nazwa)
        if (source / nazwa / "contract.yaml").is_file():
            z_kontraktem.add(nazwa)
        if not (source / nazwa / "__init__.py").is_file():
            bez_init.add(nazwa)
    return StanSource(
        moduly_luzem=frozenset(moduly_luzem),
        katalogi=frozenset(katalogi),
        z_kanalem=frozenset(z_kanalem),
        z_kontraktem=frozenset(z_kontraktem),
        bez_init=frozenset(bez_init),
        zle_nazwy=frozenset(n for n in katalogi if not _nazwa_kanoniczna(n)),
        klucze_registry=klucze_registry(source / "registry.py"),
        odczytane=frozenset(odczytane),
    )


def _nazwa_kanoniczna(nazwa: str) -> bool:
    """Czy nazwa katalogu jest już kanoniczną nazwą kanału — sprawdzone produkcyjną funkcją.

    Reguła 21 mówi: „Nazwa katalogu jest nazwą kanału: tym samym napisem, który idzie do
    `docid.document_id` jako `source`”. Sprawdzamy to jedynym producentem tej nazwy, a nie
    drugą kopią zasady kanonizacji — dwie kopie reguły tożsamości to o jedną za dużo.
    """
    try:
        return normalize_source_name(nazwa) == nazwa
    except IdentityError:
        return False


def test_regula_21_w_source_nie_lezy_modul_kanalu_luzem() -> None:
    """Reguła 21: bezpośrednio w `source/` wolno leżeć wyłącznie modułom wspólnym."""
    stan = zbadaj_source(SOURCE)

    assert stan.moduly_luzem == frozenset(), (
        f"moduł luzem w `source/`: {sorted(stan.moduly_luzem)}. Kanał jest pakietem "
        f"`source/<nazwa>/`; bezpośrednio w `source/` stoją wyłącznie "
        f"{sorted(MODULY_WSPOLNE_SOURCE)}."
    )


def test_regula_21_kazdy_katalog_kanalu_ma_komplet_plikow() -> None:
    """Reguła 21: katalog kanału niesie `__init__.py`, `channel.py` i `contract.yaml`."""
    stan = zbadaj_source(SOURCE)

    assert stan.z_kanalem == stan.katalogi, (
        f"katalog bez `channel.py`: {sorted(stan.katalogi - stan.z_kanalem)}"
    )
    assert stan.z_kontraktem == stan.katalogi, (
        f"katalog bez `contract.yaml`: {sorted(stan.katalogi - stan.z_kontraktem)}"
    )
    assert stan.bez_init == frozenset(), f"katalog bez `__init__.py`: {sorted(stan.bez_init)}"


def test_regula_21_nazwa_katalogu_jest_kanoniczna_nazwa_kanalu() -> None:
    """Reguła 21: ten sam napis idzie do `doc_id`, do `documents.source` i do kreatora."""
    stan = zbadaj_source(SOURCE)

    assert stan.zle_nazwy == frozenset(), (
        f"nazwa katalogu nie jest kanoniczną nazwą kanału: {sorted(stan.zle_nazwy)}. "
        "Przedrostek `doc_id` i kolumna `documents.source` niosłyby wtedy dwie pisownie."
    )


def test_regula_21_kanal_kontrakt_i_registry_to_ten_sam_zbior() -> None:
    """Reguła 21: nie przechodzi ani kanał bez kontraktu, ani kontrakt-sierota, ani kanał
    niewidoczny dla kreatora.

    Trzy zbiory wyznaczone z trzech niezależnych źródeł — drzewa, drzewa i kodu — bo każdy
    z nich rozjeżdża się inaczej: kontrakt zostaje po usuniętym kanale, kanał dopisuje się bez
    kontraktu, a kanał kompletny bywa niewpisany do `REGISTRY` i przez to niewidoczny dla
    polecenia `porownaj`.
    """
    stan = zbadaj_source(SOURCE)

    assert stan.z_kanalem == stan.z_kontraktem == stan.klucze_registry, (
        f"kanały z `channel.py`: {sorted(stan.z_kanalem)}; z `contract.yaml`: "
        f"{sorted(stan.z_kontraktem)}; klucze `REGISTRY`: {sorted(stan.klucze_registry)}"
    )


def zbuduj_source(korzen: Path, pliki: dict[str, str]) -> Path:
    """Podrzucone `source/` do samosprawdzeń reguł 17 i 21."""
    source = korzen / "source"
    for wzgledna, tresc in pliki.items():
        plik = source / wzgledna
        plik.parent.mkdir(parents=True, exist_ok=True)
        plik.write_text(tresc, encoding="utf-8")
    source.mkdir(parents=True, exist_ok=True)
    return source


KANAL_POPRAWNY = {
    "__init__.py": "",
    "protocol.py": "",
    "contract.py": "",
    "registry.py": 'REGISTRY = {SourceName("uzp"): UzpChannel}\n',
    "uzp/__init__.py": "",
    "uzp/channel.py": "",
    "uzp/contract.yaml": "base: x\n",
}


def test_skan_reguly_21_przepuszcza_poprawny_pakiet_kanalu(tmp_path: Path) -> None:
    """Punkt odniesienia dla wszystkich samosprawdzeń niżej: kształt z ADR-0003 1B przechodzi."""
    stan = zbadaj_source(zbuduj_source(tmp_path, KANAL_POPRAWNY))

    assert stan.moduly_luzem == frozenset()
    assert stan.z_kanalem == stan.z_kontraktem == stan.klucze_registry == {"uzp"}
    assert stan.bez_init == frozenset()
    assert stan.zle_nazwy == frozenset()


@pytest.mark.parametrize(
    ("zmiana", "pole", "oczekiwane"),
    [
        ({"uzp.py": "class UzpChannel: ...\n"}, "moduly_luzem", {"uzp.py"}),
        ({"uzp_forms.py": ""}, "moduly_luzem", {"uzp_forms.py"}),
        ({"uzp/contract.yaml": None}, "z_kontraktem", set()),
        ({"uzp/channel.py": None}, "z_kanalem", set()),
        ({"uzp/__init__.py": None}, "bez_init", {"uzp"}),
        ({"atlas/contract.yaml": "base: y\n"}, "z_kontraktem", {"uzp", "atlas"}),
        # Nazwa różniąca się od kanonicznej **nie tylko** wielkością liter obok istniejącego
        # `uzp/`: na Windowsie katalogi `UZP/` i `uzp/` są jednym katalogiem, więc próba
        # sprawdzenia samej wielkości liter przechodziłaby pusto na jednym z systemów,
        # na których ten zestaw ma działać.
        ({"UZP2/": ""}, "zle_nazwy", {"UZP2"}),
        ({"uzp nowy/": ""}, "zle_nazwy", {"uzp nowy"}),
        # Obie pisownie `REGISTRY`: z adnotacją, której wymaga reguła 21, i bez niej. Skan
        # czytający tylko jedną z nich przestawałby widzieć kanały w dniu, w którym ktoś
        # adnotację doda albo usunie — bez jednego czerwonego testu.
        (
            {"registry.py": 'REGISTRY: dict[SourceName, type[Channel]] = {"uzp": UzpChannel}\n'},
            "klucze_registry",
            {"uzp"},
        ),
        ({"registry.py": "REGISTRY = {}\n"}, "klucze_registry", set()),
        ({"registry.py": "REGISTRY = zbuduj()\n"}, "klucze_registry", {KLUCZ_NIECZYTELNY}),
        ({"registry.py": None}, "klucze_registry", set()),
        ({".gitkeep": ""}, "moduly_luzem", set()),
        ({"__pycache__/uzp.cpython-312.pyc": ""}, "katalogi", {"uzp"}),
    ],
    ids=[
        "modul_kanalu_luzem",
        "modul_pomocniczy_luzem",
        "kanal_bez_kontraktu",
        "kontrakt_sierota",
        "katalog_bez_init",
        "kontrakt_bez_kanalu",
        "nazwa_wielkimi_literami",
        "nazwa_ze_spacja",
        "registry_z_adnotacja",
        "registry_puste",
        "registry_nieczytelne",
        "brak_registry",
        "gitkeep_nie_jest_wpisem",
        "pycache_nie_jest_kanalem",
    ],
)
def test_skan_reguly_21_zauwaza_kazdy_sposob_rozjechania_sie_kanalu(
    tmp_path: Path, zmiana: dict[str, str | None], pole: str, oczekiwane: set[str]
) -> None:
    """W fazie 0 to jest **cały** dowód na regułę 21: `source/` jest puste i nie ma czego skanować.

    Lista wymienia sposoby, na które kanał i jego kontrakt dają się rozjechać — każdy z nich
    jest tym, przed czym rozstrzygnięcie 1 ADR-0003 wybiera pakiet zamiast płaskich modułów.
    Dwa ostatnie przypadki pilnują zawężenia zakresu opisanego w `zbadaj_source`: znacznik
    pustego katalogu i wytwór interpretera nie są wpisami, o których mówi reguła — a gdyby
    nimi były, jedynym lekarstwem byłaby lista wyjątków.
    """
    pliki = dict(KANAL_POPRAWNY)
    for wzgledna, tresc in zmiana.items():
        if tresc is None:
            pliki.pop(wzgledna)
        elif wzgledna.endswith("/"):
            pliki[f"{wzgledna}__init__.py"] = ""
        else:
            pliki[wzgledna] = tresc

    stan = zbadaj_source(zbuduj_source(tmp_path, pliki))

    assert getattr(stan, pole) == oczekiwane


# Reguła 17, część filesystemowa: kanał ma złote pliki, a każdy złoty plik ma przejrzaną parę.
def braki_zlotych_plikow(kanaly: frozenset[str], przyklady: Path) -> dict[str, list[str]]:
    """Kanały bez złotych plików i złote pliki bez `*.compare.json` obok.

    Kierunek sprawdzenia jest z kanału do przykładów, nie odwrotnie, i to jest świadome:
    `tests/examples/{uzp,atlas,saos}/` istnieją dziś jako miejsca dla **kandydatów** sprzed
    bramki fazy 0. Katalog przykładów bez kanału jest stanem legalnym; kanał bez przykładów
    nie jest.
    """
    braki: dict[str, list[str]] = {}
    for kanal in sorted(kanaly):
        katalog = przyklady / kanal
        if not katalog.is_dir():
            braki[kanal] = ["brak katalogu tests/examples/<kanal>/"]
            continue
        # `ZRODLO.md` jest opisem katalogu (licencja, data odczytu, SHA-256 — ADR-0005 Z-6),
        # nie surową odpowiedzią, więc pary `.compare.json` nie ma i mieć nie musi.
        surowe = [
            p
            for p in sorted(katalog.iterdir())
            if p.is_file()
            and p.name not in {".gitkeep", "ZRODLO.md"}
            and not p.name.endswith(".compare.json")
        ]
        if not surowe:
            braki[kanal] = ["katalog złotych plików bez ani jednej surowej odpowiedzi"]
            continue
        bez_pary = [p.name for p in surowe if not p.with_suffix(".compare.json").is_file()]
        if bez_pary:
            braki[kanal] = bez_pary
    return braki


def katalogi_kanalow() -> frozenset[str]:
    return zbadaj_source(SOURCE).z_kanalem


def test_regula_17_kazdy_kanal_ma_zlote_pliki_z_przejrzana_para() -> None:
    """Reguła 17: surowa odpowiedź z datą pobrania, a obok `*.compare.json` przejrzany przez
    człowieka przed commitem.

    Powód jest datowany: między majem a lipcem 2026 UZP przeniósł każdy punkt końcowy, a cudzy
    scraper przez około dwa miesiące zwracał `total=0` ze statusem 200 zamiast błędu. Złoty plik
    bez pary jest wtedy plikiem, którego nikt nie przeczytał, a test regresji przy nim milczy.
    """
    braki = braki_zlotych_plikow(katalogi_kanalow(), PRZYKLADY)

    assert braki == {}, f"kanał bez przejrzanych złotych plików: {braki}"


def test_skan_reguly_17_zauwaza_zloty_plik_bez_przejrzanej_pary(tmp_path: Path) -> None:
    """W fazie 0 to jest cały dowód na regułę 17: żaden kanał nie istnieje."""
    (tmp_path / "uzp").mkdir()
    (tmp_path / "uzp" / "details_2026-09-15.html").write_text("<html/>", encoding="utf-8")
    (tmp_path / "atlas").mkdir()
    (tmp_path / "atlas" / "lista_2026-09-15.json").write_text("{}", encoding="utf-8")
    (tmp_path / "atlas" / "lista_2026-09-15.compare.json").write_text("{}", encoding="utf-8")
    # Opis katalogu nie jest złotym plikiem i nie ma prawa zapalić reguły (ADR-0005 Z-6).
    (tmp_path / "atlas" / "ZRODLO.md").write_text("# licencja\n", encoding="utf-8")

    braki = braki_zlotych_plikow(frozenset({"uzp", "atlas", "saos"}), tmp_path)

    assert sorted(braki) == ["saos", "uzp"]
    assert braki["uzp"] == ["details_2026-09-15.html"]


# --------------------- reguła 22: adres i nazwa pola nie występują jako literał w kodzie kanału


# Reguła 22 z ADR-0003 sekcja 4. Dwa wzorce: schemat adresu i ścieżka posixowa.
WZORZEC_ADRESU = re.compile(r"^[a-z][a-z0-9+.-]*://")
WZORZEC_SCIEZKI = re.compile(r"^/[A-Za-z]")


def _id_napisow_dokumentacyjnych(tree: ast.Module) -> set[int]:
    """Docstringi modułu, klasy i funkcji — jedyny wyjątek, jaki reguła 22 wymienia."""
    dokumentacyjne: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        pierwszy = node.body[0] if node.body else None
        if (
            isinstance(pierwszy, ast.Expr)
            and isinstance(pierwszy.value, ast.Constant)
            and isinstance(pierwszy.value.value, str)
        ):
            dokumentacyjne.add(id(pierwszy.value))
    return dokumentacyjne


def literaly_adresow(path: Path) -> list[tuple[int, str]]:
    """Napisy wyglądające na adres albo ścieżkę, poza dokumentacją. Linia i treść.

    To jest mechaniczna postać zdania z reguły 17: „`contract.yaml` jest jedynym miejscem,
    z którego `channel.py` bierze adresy i nazwy pól”. Bez niej to zdanie jest życzeniem,
    a po przebudowie wyszukiwarki UZP z lipca 2026 jest to życzenie kosztowne.

    Lekarstwem na czerwony test jest przeniesienie napisu do `contract.yaml`, **nigdy**
    dopisanie wyjątku — lista wyjątków jest miejscem, w którym reguła cicho przestaje
    obowiązywać. Wzorzec złapie też ścieżkę posixową i to jest cecha, nie usterka: adapter
    nie ma powodu znać ścieżek na dysku. Jeżeli przy pierwszym kanale okaże się to fałszywe,
    lekarstwem jest zawężenie wzorca (ADR-0003 7.3), też nie lista wyjątków.
    """
    tree = drzewo(path)
    dokumentacyjne = _id_napisow_dokumentacyjnych(tree)
    znalezione: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in dokumentacyjne:
            continue
        if WZORZEC_ADRESU.match(node.value) or WZORZEC_SCIEZKI.match(node.value):
            znalezione.append((node.lineno, node.value))
    return znalezione


# ------------- reguła 19: pole o nieznanym pochodzeniu stoi w kontrakcie z powodem i datą


POLE_ODRZUCONYCH = "pola_odrzucone"
KLUCZE_WPISU_ODRZUCONEGO = ("pole", "powod", "data")


def pola_odrzucone_bez_powodu(contract: Path) -> list[str]:
    """Zarzuty do `pola_odrzucone:` kontraktu: brak pola, zły kształt, wpis bez powodu albo daty.

    Reguła 19 w brzmieniu ADR-0005 Z-5: granica przebiega na wyjściu z kanału, a pole o nieznanym
    pochodzeniu stoi w kontrakcie **z powodem i datą** — wpis bez nich jest listą wyjątków, czyli
    miejscem, w którym reguła cicho przestaje obowiązywać. Lista może być pusta (kanał bez takich
    pól), ale ma być zadeklarowana: brak deklaracji i „nie pomyślałem" wyglądają tak samo.

    Odczyt przez `yaml.safe_load`, nie tekstowy jak `role_zadeklarowane`: to pole jest listą
    słowników, a od 2026-09-18 `pyyaml` jest zależnością pakietu (`source/contract.py`). Czytniki
    tekstowe `role:` i `pomiary:` zostają — te pola są płaskie, a ich odczyt bez parsera jest
    częścią kontraktu z `test_bramki_faz.py`.
    """
    dane = yaml.safe_load(contract.read_text(encoding="utf-8"))
    if not isinstance(dane, dict) or POLE_ODRZUCONYCH not in dane:
        return [f"brak pola `{POLE_ODRZUCONYCH}:` (lista może być pusta, ale ma być zadeklarowana)"]
    wpisy = dane[POLE_ODRZUCONYCH]
    if not isinstance(wpisy, list):
        return [f"`{POLE_ODRZUCONYCH}:` nie jest listą"]
    zarzuty: list[str] = []
    for numer, wpis in enumerate(wpisy):
        if not isinstance(wpis, dict):
            zarzuty.append(f"wpis {numer}: nie jest słownikiem")
            continue
        for klucz in KLUCZE_WPISU_ODRZUCONEGO:
            if not wpis.get(klucz):
                zarzuty.append(f"wpis {numer} (`{wpis.get('pole', '?')}`): brak `{klucz}`")
    return zarzuty


def test_regula_19_kazdy_kontrakt_deklaruje_pola_odrzucone_z_powodem_i_data() -> None:
    """Reguła 19, część kontraktowa. Część zapisu (bajty w całości, skrót z tego, co zapisano)
    pilnuje `tests/test_store.py` — `test_metatest_regula_19_ma_zywego_strazniska_zapisu`."""
    zarzuty = {
        kanal: pola_odrzucone_bez_powodu(contract)
        for kanal, contract in contract_yaml_kanalow().items()
        if pola_odrzucone_bez_powodu(contract)
    }

    assert zarzuty == {}, f"kontrakt z polem odrzuconym bez powodu albo daty: {zarzuty}"


@pytest.mark.parametrize(
    ("tresc", "oczekiwane_zarzuty"),
    [
        ("pola_odrzucone: []\n", 0),
        ("pola_odrzucone:\n  - {pole: thesis, powod: nieznane, data: 2026-09-18}\n", 0),
        ("kanal: x\n", 1),
        ("pola_odrzucone: thesis\n", 1),
        ("pola_odrzucone:\n  - {pole: thesis, data: 2026-09-18}\n", 1),
        ("pola_odrzucone:\n  - {pole: thesis, powod: nieznane}\n", 1),
        ("pola_odrzucone:\n  - {pole: thesis, powod: '', data: 2026-09-18}\n", 1),
        ("pola_odrzucone:\n  - thesis\n", 1),
    ],
    ids=[
        "pusta_lista",
        "komplet",
        "brak_pola",
        "nie_lista",
        "bez_powodu",
        "bez_daty",
        "pusty_powod",
        "wpis_bez_slownika",
    ],
)
def test_skan_reguly_19_zauwaza_wpis_bez_powodu_albo_daty(
    tmp_path: Path, tresc: str, oczekiwane_zarzuty: int
) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(tresc, encoding="utf-8")

    assert len(pola_odrzucone_bez_powodu(contract)) == oczekiwane_zarzuty


def test_regula_23_uzp_nie_deklaruje_roli_masowej() -> None:
    """Reguła 23 na prawdziwym drzewie. Dziś `source/` jest puste i to jest prawda o fazie 0.

    Decyzja B właściciela (2026-09-17) brzmi „UZP nigdy nie pełni roli kanału masowego" i jest
    **zamiennikiem pytania do prawnika**, którego projekt nie zada (decyzja A). Zamiennik bez
    strażnika byłby jednak gorszy od pytania: pytanie przynajmniej wraca, a zdanie w dokumencie
    nie. Skan daje tej decyzji obserwatora w dniu, w którym powstanie pierwszy `contract.yaml`.

    Dowód działania niosą samosprawdzenia niżej — tutaj, przy pustym `source/`, nie ma czego
    czytać i zielony wynik znaczy wyłącznie „kanałów nie ma".
    """
    naruszenia = {
        kanal: sorted(role_zadeklarowane(contract))
        for kanal, contract in contract_yaml_kanalow().items()
        if rola_zakazana(kanal) in role_zadeklarowane(contract)
    }

    assert naruszenia == {}, (
        f"kanał deklaruje rolę, której mieć nie może: {naruszenia}. Reguła 23 stoi na pomiarze "
        "14 (brak warunków ponownego wykorzystywania dla `orzeczenia.uzp.gov.pl`, zmierzone "
        "2026-09-15) i na decyzji B właściciela. Zmiana roli wymaga zapisania decyzji "
        "w `docs/decisions.md`, a nie edycji tablicy w teście."
    )


def test_regula_23_kazdy_kontrakt_deklaruje_role_z_zamknietej_listy() -> None:
    """Druga połowa reguły 23: brak `role:` jest naruszeniem tak samo jak rola zakazana.

    Bez tej połowy zakaz byłby do obejścia przez **pominięcie** pola — kanał bez zadeklarowanej
    roli nie deklaruje roli masowej, więc przechodziłby przez test wyżej. To jest ten sam kształt
    obejścia, który w tym pliku zamknęła reguła 11 przy `httpx2`: strażnik patrzący na obecność
    złego napisu zamiast na obecność dobrego.
    """
    bledy = {
        kanal: sorted(role_zadeklarowane(contract) - ROLE_KANALU) or "brak pola `role:`"
        for kanal, contract in contract_yaml_kanalow().items()
        if not role_zadeklarowane(contract) or role_zadeklarowane(contract) - ROLE_KANALU
    }

    assert bledy == {}, (
        f"kontrakt bez poprawnej deklaracji ról: {bledy}. Dozwolone role: {sorted(ROLE_KANALU)}."
    )


@pytest.mark.parametrize(
    ("opis", "tresc", "kanal", "narusza"),
    [
        ("uzp z rolą masową", "role: [masowa]\n", "uzp", True),
        ("uzp z rolą masową wśród innych", "role: [weryfikacja, masowa]\n", "uzp", True),
        ("uzp bez cudzysłowów i nawiasów", "role: masowa\n", "uzp", True),
        ("uzp w dozwolonych rolach", "role: [weryfikacja, doplyw]\n", "uzp", False),
        ("uzp z komentarzem YAML po roli", "role: [masowa]  # kanal masowy\n", "uzp", True),
        ("uzp_zrzut — ten sam dostawca, ten sam zakaz", "role: [masowa]\n", "uzp_zrzut", True),
        ("uzpx — inna nazwa, nie ten dostawca", "role: [masowa]\n", "uzpx", False),
        ("atlas z rolą masową — wolno, licencja jest", "role: [masowa]\n", "atlas", False),
        ("saos z rolą masową — wolno", "role: [masowa, weryfikacja]\n", "saos", False),
    ],
)
def test_samosprawdzenie_reguly_23(
    opis: str,
    tresc: str,
    kanal: str,
    narusza: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skan sprawdzony na kontraktach podrzuconych, bo na prawdziwym drzewie nie ma żadnego.

    Sprawdzane **w obie strony**: kanał z licencją ma prawo do roli masowej i ten przypadek jest
    tu tak samo ważny jak zakaz. Strażnik, który zapala się na każdym kanale, nie pilnuje
    decyzji B — pilnuje tego, żeby nikt nie pobierał niczego.
    """
    source = tmp_path / "kio_tool" / "source" / kanal
    source.mkdir(parents=True)
    (source / "contract.yaml").write_text(tresc, encoding="utf-8")
    monkeypatch.setattr("tests.test_boundaries.SOURCE", tmp_path / "kio_tool" / "source")

    kontrakty = contract_yaml_kanalow()
    role = role_zadeklarowane(kontrakty[kanal])
    zakazana = rola_zakazana(kanal)

    assert (zakazana in role) is narusza, f"{opis}: role odczytane jako {sorted(role)}"
    assert role <= ROLE_KANALU, f"{opis}: rola spoza zamkniętej listy"


def test_samosprawdzenie_kontrakt_bez_pola_role_jest_naruszeniem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pominięcie pola nie jest drogą ucieczki przed regułą 23."""
    source = tmp_path / "kio_tool" / "source" / "uzp"
    source.mkdir(parents=True)
    (source / "contract.yaml").write_text("base: https://example.org\n", encoding="utf-8")
    monkeypatch.setattr("tests.test_boundaries.SOURCE", tmp_path / "kio_tool" / "source")

    assert role_zadeklarowane(contract_yaml_kanalow()["uzp"]) == frozenset()


def test_regula_22_kod_kanalu_nie_niesie_adresu_ani_sciezki_wprost() -> None:
    """Reguła 22 na prawdziwym drzewie. Dziś `source/` jest puste i to jest prawda o fazie 0."""
    naruszenia = {
        path.relative_to(ROOT).as_posix(): literaly_adresow(path)
        for path in pliki_source()
        if literaly_adresow(path)
    }

    assert naruszenia == {}, (
        f"adres albo ścieżka jako literał w kodzie kanału: {naruszenia}. Miejscem na nie jest "
        "`contract.yaml` przy adapterze, razem z datą odczytu."
    )


@pytest.mark.parametrize(
    ("zrodlo", "oczekiwane"),
    [
        ('"""Adapter UZP: https://orzeczenia.uzp.gov.pl."""\nBAZA = kontrakt["base"]\n', 0),
        ('def f():\n    """Czyta /Home/Details."""\n    return kontrakt["details"]\n', 0),
        ('class K:\n    """Kanał https://x."""\n', 0),
        ('BAZA = kontrakt["base_url"]\n', 0),
        ("SCIEZKA = f\"{kontrakt['details']}/{ident}\"\n", 0),
        ('WZOR = "div.search-list-item"\n', 0),
        ('BAZA = "https://orzeczenia.uzp.gov.pl"\n', 1),
        ('SCIEZKA = "/Home/Details/{id}"\n', 1),
        ('ADRES = "ftp://ftp.uzp.gov.pl/orzeczenia"\n', 1),
        ('ADRES = "https://" "orzeczenia.uzp.gov.pl"\n', 1),
        ('BAZA = "htt" + "ps://orzeczenia.uzp.gov.pl"\n', 1),
        ('BAZA = "https:/" + "/orzeczenia.uzp.gov.pl"\n', 1),
        ('URL = f"https://{host}/Home/Details"\n', 2),
        ('def f():\n    x = 1\n    return "/Home/Move"\n', 1),
        ('WYWOLANIE = klient.get("https://orzeczenia.uzp.gov.pl/Home/Details/1")\n', 1),
    ],
    ids=[
        "docstring_modulu",
        "docstring_funkcji",
        "docstring_klasy",
        "nazwa_pola_z_kontraktu",
        "sklejenie_z_kontraktu",
        "selektor_nie_jest_sciezka",
        "adres_wprost",
        "sciezka_wprost",
        "adres_ftp",
        "sklejenie_literalow_sasiadujacych",
        "sklejenie_operatorem_po_schemacie",
        "sklejenie_operatorem_po_ukosniku",
        "f_string_z_adresem_i_sciezka",
        "napis_w_ciele_funkcji_nie_jest_docstringiem",
        "adres_w_wywolaniu",
    ],
)
def test_skan_reguly_22_odroznia_dokumentacje_od_adresu_w_kodzie(
    tmp_path: Path, zrodlo: str, oczekiwane: int
) -> None:
    """W fazie 0 to jest **cały** dowód na regułę 22: `source/` nie ma ani jednego pliku `.py`.

    Przypadek „sklejenie_literalow_sasiadujacych” jest tu jako naruszenie, bo parser skleja
    sąsiadujące literały w jeden — więc ten akurat obchód skan widzi. Kształt, którego nie
    widzi, stoi niżej, w sekcji „granica skanu”, i jest tam zapisany jako asercja.
    """
    modul = tmp_path / "channel.py"
    modul.write_text(zrodlo, encoding="utf-8")

    assert len(literaly_adresow(modul)) == oczekiwane


# ----------------------------------------------------------------- metatesty antypustkowe


class Regula(NamedTuple):
    """Reguła ze skanem w tym pliku.

    `objete_skanem` jest **tą samą** funkcją, po której iteruje test reguły — dzięki temu
    „co skan obejmuje” i „co skan deklaruje, że obejmuje” nie są dwoma zdaniami do uzgadniania.
    `wlasciciele` są wzorcami ścieżek; wzorzec ze `*` rozwija się globem.
    """

    numer: int
    wlasciciele: tuple[str, ...]
    objete_skanem: Callable[[], frozenset[str]]


def _objete_source() -> frozenset[str]:
    return frozenset(f"kio_tool/source/{w}" for w in zbadaj_source(SOURCE).odczytane)


def _objete_kanaly() -> frozenset[str]:
    return frozenset(f"kio_tool/source/{k}/channel.py" for k in katalogi_kanalow())


REGULY: tuple[Regula, ...] = (
    Regula(
        1,
        (
            "kio_tool/criteria.py",
            "kio_tool/docid.py",
            "kio_tool/safetext.py",
            "kio_tool/parser/**/*.py",
        ),
        lambda: wzgledne(pliki_czyste()),
    ),
    Regula(2, ("kio_tool/source/**/*.py",), lambda: wzgledne(pliki_source())),
    Regula(3, ("kio_tool/store.py",), lambda: wzgledne(istniejace("kio_tool/store.py"))),
    Regula(
        4,
        ("kio_tool/source/**/*.py", "kio_tool/store.py"),
        lambda: wzgledne((*pliki_source(), *istniejace("kio_tool/store.py"))),
    ),
    Regula(5, ("kio_tool/pipeline.py",), lambda: wzgledne(pliki_pakietu())),
    Regula(
        6,
        (
            "kio_tool/criteria.py",
            "kio_tool/docid.py",
            "kio_tool/safetext.py",
            "kio_tool/ui/texts.py",
        ),
        lambda: wzgledne((*pliki_czyste(), *istniejace("kio_tool/ui/texts.py"))),
    ),
    Regula(
        7,
        (
            "kio_tool/richtext.py",
            "kio_tool/console.py",
            "kio_tool/ui/render.py",
            "kio_tool/ui/prompts.py",
        ),
        lambda: wzgledne(pliki_pakietu()),
    ),
    Regula(8, ("kio_tool/ui/**/*.py",), lambda: wzgledne(pliki_ui())),
    Regula(9, ("kio_tool/cli.py", "kio_tool/obsluga.py"), lambda: wzgledne(pliki_cli())),
    Regula(
        10,
        (
            "kio_tool/richtext.py",
            "kio_tool/console.py",
            "kio_tool/ui/render.py",
            "kio_tool/ui/prompts.py",
        ),
        lambda: wzgledne((*pliki_rich(), *istniejace("kio_tool/ui/prompts.py"))),
    ),
    Regula(
        11,
        tuple(sorted({p for pliki in EGRESS_OWNERS.values() for p in pliki})),
        lambda: wzgledne(pliki_regula_11()),
    ),
    Regula(12, tuple(sorted(WLASCICIELE_SDK_MODELU)), lambda: wzgledne(pliki_regula_11())),
    Regula(13, ("kio_tool/mcp_server.py",), lambda: wzgledne(istniejace("kio_tool/mcp_server.py"))),
    Regula(17, ("kio_tool/source/*/channel.py",), _objete_kanaly),
    Regula(
        19,
        ("kio_tool/source/*/contract.yaml",),
        lambda: wzgledne(contract_yaml_kanalow().values()),
    ),
    Regula(
        21,
        ("kio_tool/source/*.py", "kio_tool/source/*/channel.py", "kio_tool/source/*/contract.yaml"),
        _objete_source,
    ),
    Regula(22, ("kio_tool/source/**/*.py",), lambda: wzgledne(pliki_source())),
    Regula(
        23,
        ("kio_tool/source/*/contract.yaml",),
        lambda: wzgledne(contract_yaml_kanalow().values()),
    ),
)


class PozaSkanem(NamedTuple):
    """Reguła bez skanu w tym pliku — z powodem i, jeśli to stan przejściowy, z wyzwalaczem."""

    numer: int
    wyzwalacze: tuple[str, ...]
    powod: str


POZA_SKANEM: tuple[PozaSkanem, ...] = (
    PozaSkanem(
        14,
        (),
        "Reguła 14 (jeden producent kanonicznej tożsamości) jest niesiona przez `mypy --strict` "
        "na typach własnych z `kio_tool/docid.py`, nie przez skan AST — audyt 8.3 mówi to wprost. "
        "Skan widzi importy, a nie to, czy ktoś zbudował identyfikator konkatenacją napisów.",
    ),
    PozaSkanem(
        15,
        (),
        "Reguła 15 (każdy eksport i widok cytujący orzeczenie niesie sygnaturę, datę wydania "
        "i oznaczenie organu) jest warunkiem ustawowym z art. 15 ust. 1 pkt 4 i ma test "
        "zachowania eksportu, nie skan granic: `tests/test_attribution.py` sprawdza każdy format "
        "z `exporter.FORMATY`. Do 2026-09-18 wyzwalaczem było powstanie `exporter.py`; od etapu IV "
        "obecność strażnika sprawdza `test_metatest_regula_15_ma_zywego_strazniska_atrybucji`.",
    ),
    PozaSkanem(
        16,
        (),
        "Reguła 16 (narzędzie nie omija zabezpieczeń) nie da się w pełni sprawdzić skanem — "
        "audyt 8.3 mówi to wprost i czyni ją pozycją listy kontrolnej przeglądu kodu.",
    ),
    PozaSkanem(
        17,
        ("kio_tool/source/*/channel.py",),
        "Reguła 17 jest tu **częściowo**: część filesystemowa (złote pliki i ich przejrzane "
        "pary) ma skan wyżej, a część behawioralna — adapter rzuca `SourceContractBroken` "
        "zamiast zwracać pustą listę — mieszka w teście dymnym kanału na złotym pliku, "
        "`tests/test_source_<kanał>.py`; jego istnienie sprawdza "
        "`test_metatest_regula_17_kazdy_kanal_ma_test_dymny_na_zlotym_pliku`.",
    ),
    PozaSkanem(
        18,
        # Wyzwalaczem jest adapter **UZP**, nie dowolny kanał — reguła mówi o `Details/{id}`
        # i `ContentHtml/{id}`, czyli o kontrakcie jednego dostawcy. Do 2026-09-18 wzorzec brzmiał
        # `source/*/channel.py`, bo kanał nie był wybrany; w dniu powstania `source/atlas/`
        # zapaliłby regułę o punktach końcowych, których Atlas nie ma.
        ("kio_tool/source/uzp/channel.py",),
        "Reguła 18 (metadane z `Details/{id}`, treść z `ContentHtml/{id}`, oba jako bajty) jest "
        "kontraktem adaptera UZP; kanał `uzp` wraca w fazie 2 w rolach weryfikacji i dopływu "
        "(ADR-0005 Z-3) i wtedy ta reguła dostaje skan albo test dymny.",
    ),
    PozaSkanem(
        19,
        ("kio_tool/store.py",),
        "Reguła 19 jest tu **częściowo**: część kontraktowa (`pola_odrzucone:` z powodem "
        "i datą) ma skan wyżej, a część zapisu — bajty w całości, `content_sha256` z tego, co "
        "zapisano — jest własnością `store.py` i mieszka w `tests/test_store.py`; jego "
        "istnienie sprawdza `test_metatest_regula_19_ma_zywego_strazniska_zapisu`. Sufiks "
        "`-derived` i manifest zbioru od modelu czekają na fazę 4.",
    ),
    PozaSkanem(
        20,
        (),
        "Reguła 20 (sieć w testach zablokowana, wyjątek jawny) ma dwóch strażników poza tym "
        "plikiem: `--block-network` w `pyproject.toml` i `tests/test_pomiar21_blokada_sieci.py`, "
        "który asertuje treść blokady dla httpx **i** dla gniazda. Obecność obu sprawdza "
        "`test_metatest_regula_20_ma_zywego_strazniska_poza_tym_plikiem`.",
    ),
)

# Reguły 17 i 19 stoją świadomie w obu tablicach: część każdej z nich jest skanem (złote pliki;
# `pola_odrzucone:` w kontrakcie), a część zachowaniem z własnym testem poza tym plikiem (test
# dymny adaptera; zapis bajtów w całości). Każde inne nałożenie się tablic byłoby niechlujstwem.
REGULY_CZESCIOWE = frozenset({17, 19})
AUDYT = ROOT / "docs" / "AUDYT_KIO_ORZECZENIA.md"
ARCHITEKTURA = ROOT / "docs" / "ARCHITEKTURA_KIO_TOOL.md"
"""Dwa dokumenty, w których mieszkają reguły granic — jedyne źródło ich numerów."""


def numery_regul_z_dokumentow() -> frozenset[int]:
    """Numery reguł **odczytane z dokumentów**, a nie wypisane tutaj zakresem.

    Do 2026-09-17 stała tu liczba: `frozenset(range(1, 23))`. Docstring metatestu przyznawał
    wprost, że „reguła dopisana do dokumentów i tu pominięta nie jest przez ten test widziana" —
    czyli jedyne miejsce w tym pliku, w którym doktryna „reguła bez strażnika jest życzeniem"
    nie miała strażnika samej siebie. Tego samego dnia dopisano regułę 23 i granica natychmiast
    okazała się realna: reguła istniała w architekturze i w skanie, a metatest o niej nie wiedział.

    Reguły mieszkają w dwóch sekcjach i to jest podział historyczny, nie przypadkowy: 1–16
    przeniesione z `ceidg-tool` (audyt 8.3), 17 i dalsze dopisane w tym projekcie
    (architektura 4.1). Skan czyta obie i sumuje.

    **Pusty odczyt jest błędem, nie zerem.** Gdyby nagłówek sekcji się zmienił, wyrażenie
    przestałoby dopasowywać cokolwiek, zbiór byłby pusty i metatest przechodziłby zielono przy
    każdej tablicy — czyli parsowanie markdownu zamieniłoby się w wyłącznik strażnika. Dlatego
    obie sekcje muszą dać niepusty wynik, a reguła 1 i ostatnia dopisana muszą się znaleźć.
    """
    numery: set[int] = set()
    for sciezka, naglowek, konczy, wzorzec in (
        (AUDYT, "### 8.3 Reguły granic", "## 9.", r"^(\d+)\. "),
        (ARCHITEKTURA, "## 4. Architektura", "## 5.", r"^(\d+)\. \*\*"),
    ):
        tresc = sciezka.read_text(encoding="utf-8")
        assert naglowek in tresc, f"{sciezka.name}: nie ma sekcji `{naglowek}` z regułami"
        sekcja = tresc.split(naglowek, 1)[1].split(konczy, 1)[0]
        znalezione = {int(m) for m in re.findall(wzorzec, sekcja, re.MULTILINE)}
        assert znalezione, (
            f"{sciezka.name}: w sekcji `{naglowek}` nie odczytano ani jednego numeru reguły. "
            "Pusty odczyt wyłączyłby metatest zamiast go zasilić — popraw wzorzec albo nagłówek."
        )
        numery |= znalezione
    assert 1 in numery, "odczyt reguł nie objął reguły 1 — sekcje czytają się inaczej niż zakładano"
    return frozenset(numery)


NUMERY_REGUL = numery_regul_z_dokumentow()


def rozwin(wzorzec: str) -> frozenset[str]:
    """Wzorzec ścieżki na istniejące dziś ścieżki względem korzenia repozytorium."""
    if "*" in wzorzec:
        return frozenset(
            p.relative_to(ROOT).as_posix()
            for p in ROOT.glob(wzorzec)
            if "__pycache__" not in p.parts
        )
    return frozenset({wzorzec}) if (ROOT / wzorzec).exists() else frozenset()


def test_metatest_kazda_regula_ze_skanem_obejmuje_swoje_istniejace_pliki() -> None:
    """Jedyny sposób, w jaki tablica `REGULY` może skłamać (ADR-0003 5.1 punkt 3).

    Reguła, której plik-właściciel istnieje, a skan go nie czyta, przechodzi pusto i wygląda
    identycznie jak reguła egzekwowana. Stan „wyzwalacz” jest legalny **wyłącznie** wtedy,
    gdy pliku nie ma — i to jest dokładnie ta różnica, którą ten test mierzy.
    """
    pominiete: dict[int, list[str]] = {}
    for regula in REGULY:
        istniejacy = frozenset[str]().union(*(rozwin(w) for w in regula.wlasciciele))
        poza = sorted(istniejacy - regula.objete_skanem())
        if poza:
            pominiete[regula.numer] = poza

    assert pominiete == {}, (
        f"reguła ma istniejący plik-właściciel, którego skan nie czyta: {pominiete}. "
        "To jest stan, w którym reguła raportuje się jako domknięta przy pokryciu części ruchu."
    )


def test_metatest_regula_w_stanie_wyzwalacza_nie_ma_jeszcze_plikow() -> None:
    """Druga połowa tej samej myśli, dla reguł **bez** skanu w tym pliku.

    Reguła odłożona „do czasu, aż powstanie X” jest uczciwa dopóty, dopóki X nie powstało.
    W dniu, w którym powstanie, ten test zapala się i wymusza napisanie skanu — zamiast
    zostawić regułę w dokumencie jako zdanie, którego nikt nie pilnuje.
    """
    przedwczesne: dict[int, list[str]] = {}
    for wpis in POZA_SKANEM:
        if wpis.numer in REGULY_CZESCIOWE:
            continue  # część tej reguły jest skanowana; wyzwalacz dotyczy tylko reszty
        obecne = sorted(frozenset[str]().union(*(rozwin(w) for w in wpis.wyzwalacze)))
        if obecne:
            przedwczesne[wpis.numer] = obecne

    assert przedwczesne == {}, "\n".join(
        f"reguła {numer}: powstało {pliki}; powód odłożenia: "
        f"{next(w.powod for w in POZA_SKANEM if w.numer == numer)}"
        for numer, pliki in sorted(przedwczesne.items())
    )


def test_metatest_kazda_regula_granic_ma_w_tym_pliku_swoje_miejsce() -> None:
    """Żaden numer reguły nie może po cichu zniknąć z obu tablic.

    Reguła usunięta z `REGULY` i niedopisana do `POZA_SKANEM` przestaje obowiązywać bez jednego
    czerwonego testu — to jest ta sama cicha awaria, przed którą broni reszta tego pliku, tylko
    o poziom wyżej. Reguła **dopisana** do dokumentów i tu pominięta nie jest przez ten test
    widziana; jej dopisanie tutaj jest częścią dopisania reguły, nie osobnym krokiem.
    """
    ze_skanem = {r.numer for r in REGULY}
    bez_skanu = {w.numer for w in POZA_SKANEM}

    assert ze_skanem | bez_skanu == NUMERY_REGUL, (
        f"reguła bez miejsca w tym pliku: {sorted(NUMERY_REGUL - (ze_skanem | bez_skanu))}"
    )
    assert ze_skanem & bez_skanu == REGULY_CZESCIOWE, (
        f"reguła w obu tablicach bez adnotacji o częściowości: "
        f"{sorted((ze_skanem & bez_skanu) - REGULY_CZESCIOWE)}"
    )
    assert len(ze_skanem) == len(REGULY) and len(bez_skanu) == len(POZA_SKANEM), "numer powtórzony"
    assert all(w.powod for w in POZA_SKANEM), "reguła odłożona bez powodu to reguła porzucona"


def test_metatest_regula_20_ma_zywego_strazniska_poza_tym_plikiem() -> None:
    """Reguła 20 jest jedyną pozycją `POZA_SKANEM`, której strażnik istnieje **dziś**.

    Wpis „pilnuje tego coś innego” jest zdaniem bez pokrycia, dopóki nikt nie sprawdza, czy to
    coś innego wciąż tam jest. `--block-network` skreślone z `addopts` rozbraja regułę 20 w całym
    zestawie i nie zapala niczego na czerwono — poza tą asercją.
    """
    konfiguracja = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts = konfiguracja["tool"]["pytest"]["ini_options"]["addopts"]

    assert "--block-network" in addopts, "reguła 20 rozbrojona w `pyproject.toml`"
    assert (TESTY / "test_pomiar21_blokada_sieci.py").is_file(), (
        "zniknął pomiar 21 — a to on, a nie ten plik, pokazuje, że blokada jest zamkiem "
        "na gnieździe, czyli że reguła 20 obejmuje także kanał spoza HTTP."
    )


PLIK_EKSPORTERA = PAKIET / "exporter.py"
PLIK_TESTU_ATRYBUCJI = TESTY / "test_attribution.py"
OZNACZENIE_ORGANU = "Krajowa Izba Odwoławcza"


def test_metatest_regula_15_ma_zywego_strazniska_atrybucji() -> None:
    """Reguła 15 mieszka w teście zachowania eksportu — ten test pilnuje, że tamten istnieje,
    zna oznaczenie organu i mówi o każdym formacie, a nie o jednym wybranym.

    Wpis „pilnuje tego coś innego" jest zdaniem bez pokrycia, dopóki nikt nie sprawdza, czy to
    coś innego wciąż tam jest — ten sam kształt co dla reguł 17, 19 i 20 wyżej. Formaty czytane
    są z `FORMATY` w `exporter.py` **ze składni**, nie importem: reguła ma zapalać się także
    wtedy, gdy eksporter jest w połowie napisany.
    """
    assert PLIK_EKSPORTERA.is_file(), "`exporter.py` zniknął — reguła 15 nie ma przedmiotu"
    assert PLIK_TESTU_ATRYBUCJI.is_file(), (
        "`exporter.py` istnieje, a `tests/test_attribution.py` nie — reguła 15 bez strażnika"
    )
    tresc = PLIK_TESTU_ATRYBUCJI.read_text(encoding="utf-8")
    assert OZNACZENIE_ORGANU in tresc, "strażnik reguły 15 nie zna oznaczenia organu"
    formaty = _formaty_eksportera(PLIK_EKSPORTERA)
    assert formaty, "nie odczytano `FORMATY` z `exporter.py` — pusty odczyt wyłączyłby ten test"
    brakujace = sorted(fmt for fmt in formaty if f'"{fmt}"' not in tresc)
    assert brakujace == [], f"strażnik reguły 15 nie wymienia formatów: {brakujace}"


def _formaty_eksportera(path: Path) -> frozenset[str]:
    """Wartości literału `FORMATY = (...)` w `exporter.py`, odczytane z drzewa składniowego."""
    for node in ast.walk(drzewo(path)):
        cele: list[ast.expr]
        if isinstance(node, ast.AnnAssign):
            cele = [node.target]
        elif isinstance(node, ast.Assign):
            cele = list(node.targets)
        else:
            continue
        if not any(isinstance(cel, ast.Name) and cel.id == "FORMATY" for cel in cele):
            continue
        if isinstance(node.value, ast.Tuple):
            return frozenset(
                e.value
                for e in node.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            )
    return frozenset()


def test_metatest_regula_17_kazdy_kanal_ma_test_dymny_na_zlotym_pliku() -> None:
    """Część behawioralna reguły 17 mieszka poza tym plikiem — to zdanie ma tu obserwatora.

    Wpis w `POZA_SKANEM` mówi „pilnuje tego test dymny kanału"; dopóki nikt nie sprawdza, czy ten
    test istnieje i czy w ogóle zna `SourceContractBroken`, jest to zdanie bez pokrycia — ten sam
    kształt, który dla reguły 20 zamyka test wyżej.
    """
    for kanal in sorted(katalogi_kanalow()):
        plik = TESTY / f"test_source_{kanal}.py"
        assert plik.is_file(), f"kanał {kanal!r} ma adapter, a nie ma testu dymnego {plik.name}"
        assert "SourceContractBroken" in plik.read_text(encoding="utf-8"), (
            f"{plik.name} nie zna `SourceContractBroken` — część behawioralna reguły 17 "
            "(status zgodny, kształt niezgodny → wyjątek, nie pusta lista) nie ma tam obserwatora"
        )


def test_metatest_regula_19_ma_zywego_strazniska_zapisu() -> None:
    """Część zapisu reguły 19 („bajty w całości, skrót z tego, co zapisano") mieszka
    w `tests/test_store.py`; ten test pilnuje, że tamten plik istnieje i mówi o skrócie."""
    plik = TESTY / "test_store.py"

    assert plik.is_file(), (
        "`store.py` istnieje, a `tests/test_store.py` nie — reguła 19 bez strażnika"
    )
    assert "sha256" in plik.read_text(encoding="utf-8"), (
        "`tests/test_store.py` nie wspomina o `sha256` — część zapisu reguły 19 nie ma obserwatora"
    )


# ------------------------------------------------------ granica skanu: czego świadomie nie łapie


# ADR-0003 7.3: „Skan łapie przeoczenia, nie napastnika. Aliasowanie i `getattr` omijają go
# tak samo jak w CEIDG i jest to świadome.” Poniższe testy są **asercjami** na tę granicę,
# a nie zdaniem o niej. Dwa powody. Po pierwsze: granica opisana w komentarzu z czasem przestaje
# odpowiadać kodowi i nikt tego nie zauważa. Po drugie: gdyby ktoś skan wzmocnił, te testy
# zapalą się i wymuszą świadomą zmianę tablicy oraz dokumentu — zamiast cichego rozszerzenia
# reguły, które zaczyna łapać kształty, o których nikt nie rozmawiał.


@pytest.mark.parametrize(
    "zrodlo",
    [
        'import httpx\nc = getattr(httpx, "Client")()\n',
        "import httpx\nfabryka = httpx.Client\nc = fabryka()\n",
        'import importlib\nc = importlib.import_module("httpx").Client()\n',
        'c = __import__("socket").create_connection(a)\n',
        "import socket\nwolanie = socket.create_connection\nwolanie(a)\n",
    ],
    ids=["getattr", "fabryka_w_zmiennej", "import_module", "dunder_import", "alias_funkcji"],
)
def test_granica_skanu_reguly_11_nie_siega_poza_skladnie(tmp_path: Path, zrodlo: str) -> None:
    """Reguła 11 pilnuje zapisu, nie wykonania — i tu jest tego dowód, nie obietnica.

    Każdy z tych kształtów buduje konstrukt wyjścia i przechodzi niewidziany. Nie ma sposobu,
    żeby skan składniowy złapał każde wyjście bez wyliczenia; jest natomiast sposób, żeby
    wyliczenie było krótkie, uzasadnione i żeby jego brzeg był zapisany.

    Naprawa tej granicy wymaga innego narzędzia niż AST — na przykład strażnika na gnieździe
    w przebiegu, czyli tego, co `--block-network` robi w testach (pomiar 21). Ten plik nie
    udaje, że to robi.
    """
    modul = tmp_path / "probny.py"
    modul.write_text(zrodlo, encoding="utf-8")

    assert konstrukty_wyjscia(modul) & set(EGRESS_OWNERS) == set(), (
        "Skan złapał kształt, który do tej pory omijał. To nie jest samo z siebie usterka — "
        "ale jest zmianą zakresu reguły 11 i ma zapaść jako decyzja, razem z wpisem w ADR."
    )


@pytest.mark.parametrize(
    "zrodlo",
    [
        'HOST = "orzeczenia.uzp.gov.pl"\n',
        'SCIEZKA = "Home/Details"\n',
        'SCIEZKA = "/".join(["", "Home", "Details"])\n',
        "from .stale import BAZA\nADRES = BAZA\n",
    ],
    ids=[
        "sam_host_bez_schematu",
        "sciezka_bez_ukosnika",
        "zlozenie_z_czesci",
        "adres_z_innego_modulu",
    ],
)
def test_granica_skanu_reguly_22_widzi_literal_a_nie_zamiar(tmp_path: Path, zrodlo: str) -> None:
    """Reguła 22 odrzuca **napis wyglądający na adres**, nie wiedzę adaptera o adresie.

    Dwa pierwsze przypadki są w tym pliku ważniejsze niż cała reszta tej sekcji, bo są jedynymi,
    które ktoś napisze z przekonania, że tak jest czyściej. `HOST = "orzeczenia.uzp.gov.pl"`
    i `"Home/Details"` łamią regułę 17 w całości — adapter bierze adres skądinąd niż
    z `contract.yaml` — a przez wzorce reguły 22 przechodzą, bo nie niosą ani schematu, ani
    wiodącego ukośnika. Lekarstwem jest **zawężenie problemu, nie poszerzenie wzorca**: wzorzec
    łapiący każdą kropkowaną nazwę zapalałby się na `selectolax.parser`, a wtedy jedynym wyjściem
    byłaby lista wyjątków, czyli miejsce, w którym reguła cicho przestaje obowiązywać (ADR-0003
    7.3). Do czasu pierwszego kanału pilnuje tego przegląd kodu i tak ma to być czytane.

    Czego ta sekcja **nie** obejmuje: naiwnego rozcięcia literału. `"htt" + "ps://…"` skan łapie,
    bo drugi człon wciąż zaczyna się jak schemat, a `"https:/" + "/orzeczenia…"` łapie po
    ukośniku — oba stoją w tabeli wyżej jako naruszenia. Pierwsza wersja tej sekcji twierdziła
    inaczej i padła: granica opisana z pamięci była o dwa kształty szersza niż prawdziwa.
    """
    modul = tmp_path / "channel.py"
    modul.write_text(zrodlo, encoding="utf-8")

    assert literaly_adresow(modul) == []


def test_granica_skanu_regul_importowych_nie_widzi_importu_dynamicznego(tmp_path: Path) -> None:
    """Reguły 1–8 i 13 czytają instrukcje `import`, nie wykonanie.

    `importlib.import_module("sqlite3")` w module czystym przechodzi. To jest ta sama granica,
    co wyżej, i ma tu być zapisana osobno, bo reguły importowe są w tym pliku najliczniejsze —
    a najłatwiej o nich pomyśleć, że „pilnują zależności”.
    """
    podrzucony = tmp_path / "parser_cite.py"
    podrzucony.write_text('import importlib\nb = importlib.import_module("sqlite3")\n', "utf-8")

    assert imported_roots(podrzucony) & ZAKAZANE_REGULA_1 == set()
    assert "importlib" in imported_roots(podrzucony), "skan widzi za to sam `importlib`"


def test_granica_skanu_reguly_21_zaglusza_sie_glosno_a_nie_cicho(tmp_path: Path) -> None:
    """Wyjątek od reguły „skan omijany po cichu”: `REGISTRY` złożone dynamicznie.

    `REGISTRY` zbudowane pętlą albo komprehensją jest dla skanu nieczytelne — i właśnie
    dlatego `klucze_registry` zwraca wtedy klucz, który nie równa się żadnej nazwie katalogu.
    Skutkiem jest czerwony test z czytelnym komunikatem, a nie zbiór pusty równy pustemu
    zbiorowi kanałów. Różnica między „nie wiem” a „nic nie znalazłem” jest tu całą treścią:
    pierwsze ma być głośne, drugie jest prawdą o fazie 0.
    """
    pliki = dict(KANAL_POPRAWNY)
    pliki["registry.py"] = "REGISTRY = {SourceName(n): k for n, k in odkryj()}\n"
    stan = zbadaj_source(zbuduj_source(tmp_path, pliki))

    assert stan.klucze_registry == {KLUCZ_NIECZYTELNY}
    assert stan.klucze_registry != stan.z_kanalem, (
        "Nieczytelne `REGISTRY` ma dawać rozjazd trzech zbiorów, czyli czerwony test — "
        "nie zbiór pusty, który przy pustym `source/` byłby nie do odróżnienia od porządku."
    )


# --------------------- reguła 10 na `questionary` (ADR-0008 Z-15) i reguła 7 w równości

WYWOLANIA_PYTAN = frozenset(
    {"confirm", "text", "select", "Choice", "checkbox", "rawselect", "autocomplete", "print"}
)
"""Konstrukty `questionary`, które wypisują napis na terminal."""
SLOWA_PYTAN = frozenset({"message", "title", "instruction", "qmark"})
NEUTRALIZATOR_PYTAN = "_do_pytania"


def naruszenia_pytan(tree: ast.Module) -> list[int]:
    """Linie, w których napis idzie do `questionary` z pominięciem `_do_pytania`.

    `default` liczy się wyłącznie przy `text` — tam jest wpisanym na ekran napisem; przy
    `select` jest kluczem opcji, przy `confirm` wartością logiczną. Bezpieczny jest napis
    programu (stała) albo **całe** wyrażenie będące wywołaniem neutralizatora — ta sama zasada
    korzenia wyrażenia co `argument_bezpieczny` dla `rich`.
    """
    naruszenia: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "questionary"
            and func.attr in WYWOLANIA_PYTAN
        ):
            continue
        slowa = SLOWA_PYTAN | ({"default"} if func.attr == "text" else set())
        argumenty = [*node.args, *(kw.value for kw in node.keywords if kw.arg in slowa)]
        for argument in argumenty:
            napis = isinstance(argument, ast.Constant) and isinstance(argument.value, str)
            if not napis and nazwa_wywolania(argument) != NEUTRALIZATOR_PYTAN:
                naruszenia.append(argument.lineno)
    return naruszenia


def test_regula_10_pytania_questionary_ida_przez_neutralizator() -> None:
    """Etykieta przebiegu z bazy albo kryterium wpisane przez operatora dociera do terminala
    przez `questionary` tak samo jak przez `rich` — sekwencja ESC steruje ekranem w obu."""
    for wzgledna in sorted(MODULY_QUESTIONARY):
        sciezka = PAKIET / wzgledna
        assert naruszenia_pytan(drzewo(sciezka)) == [], f"{wzgledna}: napis bez `_do_pytania`"


@pytest.mark.parametrize(
    ("zrodlo", "ile"),
    [
        ("questionary.select(_do_pytania(p.tresc), choices=[])", 0),
        ('questionary.confirm("Kontynuować?", default=True)', 0),
        ("questionary.Choice(title=_do_pytania(o.etykieta), value=o.klucz)", 0),
        ("questionary.select(p.tresc)", 1),
        ("questionary.text(_do_pytania(p.tresc), default=p.domyslna)", 1),
        ('questionary.Choice(title=f"{o.etykieta}", value=o.klucz)', 1),
        ("questionary.select(_do_pytania(a) + b)", 1),
    ],
)
def test_samosprawdzenie_skanu_pytan(zrodlo: str, ile: int) -> None:
    assert len(naruszenia_pytan(ast.parse(zrodlo))) == ile


def test_regula_7_pytajacy_naprawde_zna_questionary() -> None:
    """Lustro testu dla `rich`: zawieranie przechodzi też dla zbioru pustego."""
    assert uzytkownicy("questionary") == MODULY_QUESTIONARY
