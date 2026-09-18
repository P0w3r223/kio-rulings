"""Strażnik głosu limitera — `kio_tool/console.py`.

`PulsKonsoli` (do 2026-09-18 `PulsSondy` w `scripts/sonda.py`) ma **trzy** głosy — postój
(`on_wait`), zdanie od limitera (`on_message`) i od etapu III dokument zapisany (`on_document`,
puls przebiegu masowego w dokumentach, nie w stronach) — i milczy wszędzie poza nimi.

Reguła 10 obejmuje ten moduł skanem AST z chwilą powstania pliku, więc skreślenie `safe`
z któregokolwiek druku zapala `test_boundaries.py` (zmierzone mutacją 2026-09-18: obie
pisownie `print(f"…")` bez `safe` łapie skan, żaden test zachowania ich nie widział). Skan jest
jednak **składniowy**: mówi, że wywołanie stoi, nie że cokolwiek neutralizuje. Dlatego testy
niżej pytają o drugą połowę tego zdania — co ląduje na ekranie, gdy napis niesie sekret albo
znak sterujący — i przy okazji o to, że `print(Text)` wypisuje sam napis, bez opakowania.
"""

from __future__ import annotations

# Moduły sondy mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import pytest

from kio_tool.clock import local_hhmm
from kio_tool.config import register_secret
from kio_tool.console import PulsKonsoli
from tests.wsparcie_sondy import KLUCZ_TESTOWY

# --- PulsKonsoli: głos limitera w czasie postoju -------------------------------------------


def test_puls_mowi_ile_czeka_dlaczego_i_do_kiedy(capsys: pytest.CaptureFixture[str]) -> None:
    """Trzy liczby, bo każda odpowiada na inne pytanie operatora.

    Sekundy mówią, czy warto czekać; powód mówi, czy to odstęp, czy blokada po 429; godzina
    wznowienia mówi, kiedy wrócić — i jest liczona zegarem **lokalnym**, bo operator patrzy
    na zegarek, a nie na UTC. Komunikat bez którejkolwiek z nich zostawia pytanie otwarte.
    """
    epoka = 1_700_000_000.0

    PulsKonsoli().on_wait(120.0, "blokada_429", epoka)

    wypisane = capsys.readouterr().out

    assert "120.0" in wypisane
    assert "blokada_429" in wypisane
    assert local_hhmm(epoka) in wypisane


def test_puls_powtarza_zdanie_limitera_do_operatora(capsys: pytest.CaptureFixture[str]) -> None:
    """`on_message` jest drugim głosem tej klasy i do 2026-09-18 nie miał żadnego obserwatora.

    Zmierzone mutacją 2026-09-18: ciało `on_message` zamienione na `return None` przechodzi
    przez **cały zielony przebieg**. Skan reguły 10 tego nie widzi i widzieć nie może — nie ma
    już wtedy czego skanować, bo druku nie ma. Zdarzenie niesie zdania, które limiter kieruje
    wprost do operatora (wznowienie po blokadzie, przycięcie budżetu), więc jego zniknięcie
    jest dokładnie tą ciszą, dla której `PulsKonsoli` powstał.
    """
    PulsKonsoli().on_message("budżet przycięty do 40 żądań")

    assert "budżet przycięty do 40 żądań" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("zdarzenie", "wypisz"),
    [
        ("on_wait", lambda puls, tekst: puls.on_wait(1.0, tekst, 1_700_000_000.0)),
        ("on_message", lambda puls, tekst: puls.on_message(tekst)),
    ],
)
def test_oba_glosy_maskuja_sekret_zanim_napis_dojdzie_do_ekranu(
    zdarzenie: str,
    wypisz: object,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Druga połowa reguły 10, której skan AST nie sprawdza: że `safe` cokolwiek robi.

    Skan mówi, że wywołanie neutralizatora stoi w wyrażeniu. Nie mówi, czy neutralizator
    maskuje — `strip_control` podstawione w to miejsce ma tę samą składnię i usuwa znaki
    sterujące, **nie maskując sekretu** (`test_boundaries.py` wymienia go przy definicji
    `NEUTRALIZATORY` właśnie z tego powodu). Ta asercja pyta o skutek na ekranie.

    Że powód postoju i zdanie limitera niosą dziś wyłącznie słowa programu, mówi docstring
    `PulsKonsoli` — i dlatego test jest tu **własnością klasy**, nie opisem dzisiejszego
    wywołującego: klasa, której jedynym zadaniem jest drukowanie, ma neutralizować to, co
    drukuje, zamiast pamiętać, skąd napis pochodzi. Ta sama klasa ma obsłużyć `pipeline`.
    """
    register_secret(KLUCZ_TESTOWY)

    wypisz(PulsKonsoli(), f"odmowa klucza {KLUCZ_TESTOWY}")  # type: ignore[operator]

    wypisane = capsys.readouterr().out

    assert KLUCZ_TESTOWY not in wypisane, f"{zdarzenie}: sekret doszedł do terminala operatora"
    assert "<token>" in wypisane


@pytest.mark.parametrize(
    ("zdarzenie", "wypisz"),
    [
        ("on_wait", lambda puls, tekst: puls.on_wait(1.0, tekst, 1_700_000_000.0)),
        ("on_message", lambda puls, tekst: puls.on_message(tekst)),
    ],
)
def test_oba_glosy_nie_przepuszczaja_znakow_sterujacych_na_terminal(
    zdarzenie: str,
    wypisz: object,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sekwencja ANSI nie ma prawa wyczyścić ekranu, na którym stoi ślad przebiegu.

    Wiersze `Kroniki` i wiersze pulsu idą na to samo wyjście, więc znak sterujący w napisie
    pulsu kasuje nie swój komunikat, tylko rachunek żądań wypisany wyżej. Znak dwukierunkowy
    odwraca przy tym kolejność wyświetlania tego, co sonda właśnie zmierzyła.
    """
    wypisz(PulsKonsoli(), "\x1b[2Jczysty ekran\x07‮gniwo")  # type: ignore[operator]

    wypisane = capsys.readouterr().out

    assert "\x1b" not in wypisane and "\x07" not in wypisane, f"{zdarzenie}: ANSI na terminalu"
    assert "‮" not in wypisane
    assert "czysty ekran" in wypisane


def test_puls_wypisuje_sam_napis_bez_opakowania_rich(capsys: pytest.CaptureFixture[str]) -> None:
    """`safe` zwraca `Text`, a `print(Text)` wypisuje `Text.__str__`, czyli `plain`.

    Zdanie z nagłówka `console.py` („na ekran idzie to samo co przed neutralizacją — bez znaków
    sterujących i bez sekretów") jest tu jedyną rzeczą do sprawdzenia: gdyby druk poszedł
    `repr`-em albo przez `rich` z domyślnym zawijaniem, operator zobaczyłby `<rich.text.Text …>`
    zamiast komunikatu, a `test_zadanie.py` szukające napisu „czekam" zapaliłoby się dopiero
    przypadkiem.
    """
    PulsKonsoli().on_message("zwykłe zdanie")

    assert capsys.readouterr().out == f"{'':26} ⋯ zwykłe zdanie\n"


def test_puls_mowi_ile_dokumentow_zapisal(capsys: pytest.CaptureFixture[str]) -> None:
    """Trzeci głos, od etapu III (2026-09-18): puls przebiegu masowego w dokumentach zapisanych.

    Jedyna jednostka, w której doktryna pozwala liczyć puls, to żądania wysłane albo dokumenty
    zapisane — nigdy strony (`progress.py`). `on_document` mówi obie liczby: ile zapisano i ile
    kanał zgłosił w zakresie, bo bez drugiej pierwsza nie mówi, czy to początek, czy koniec.
    """
    PulsKonsoli().on_document(7, 360)

    wypisane = capsys.readouterr().out

    assert "7" in wypisane and "360" in wypisane


def test_puls_przy_nieznanej_liczbie_dokumentow_nie_udaje_ze_ja_zna(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`total` bywa `None` (docstring `Events.on_document`) — pasek, który udaje, że wie, kłamie."""
    PulsKonsoli().on_document(7, None)

    assert "?" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("metoda", "argumenty"),
    [
        ("on_request", ("szukaj", 200, 0.1)),
        ("on_version", ("kio-1", "a" * 64)),
        ("on_page", (1, 10, 100)),
        ("on_parse", (1, 10)),
        ("on_export", (1, 10)),
        ("close", ()),
    ],
)
def test_puls_milczy_wszedzie_poza_postojem_zdaniem_limitera_i_dokumentem(
    metoda: str, argumenty: tuple[object, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    """Puls ma trzy głosy i to jest decyzja z docstringu `PulsKonsoli`.

    `on_request` milczy celowo: w sondzie wiersz na żądanie drukuje `Kronika`, a w przebiegu
    masowym wiersz na dokument (`on_document`) wystarcza — drugi wiersz na każde żądanie
    zdublowałby dziennik na ekranie. `on_page` milczy, bo strona nie jest jednostką pulsu.
    """
    getattr(PulsKonsoli(), metoda)(*argumenty)

    assert capsys.readouterr().out == ""


def test_metatest_kazda_metoda_protokolu_ma_tu_swoje_zdanie() -> None:
    """Antypustka dla parametryzacji wyżej: metoda dopisana do `Events` ma trafić pod strażnika.

    Parametryzacja po liście wpisanej ręką nie odróżnia „milczy, bo tak ma być" od „milczy, bo
    nikt o nią nie zapytał" — a `on_message` przez cały 2026-09-18 był dokładnie tym drugim
    przypadkiem: nie stał ani na liście milczących, ani w żadnym teście mówiących.
    """
    sprawdzane = {
        "on_request",
        "on_document",
        "on_version",
        "on_page",
        "on_parse",
        "on_export",
        "close",
        "on_wait",
        "on_message",
    }
    zadeklarowane = {
        nazwa
        for nazwa in vars(PulsKonsoli)
        if not nazwa.startswith("__") and callable(getattr(PulsKonsoli, nazwa))
    }

    assert zadeklarowane == sprawdzane, (
        f"`PulsKonsoli` niesie metody {sorted(zadeklarowane)}, a ten plik pyta o "
        f"{sorted(sprawdzane)} — metoda bez zdania w tym pliku milczy albo mówi bez obserwatora"
    )
