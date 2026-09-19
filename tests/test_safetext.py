"""Strażnicy neutralizatora tekstu ze źródła.

Powstały razem z poprawką z przeglądu kodu 2026-09-15. Pierwsza wersja `strip_control` była
kopią wersji z `ceidg-tool` (`ord(ch) >= 32`), czyli pokrywała wyłącznie C0 — a docstring
modułu deklarował, że przeniesienie ma **podwyższony priorytet**, bo wrogim wejściem jest
tu cały dokument, nie nazwa firmy. Priorytet podniesiono, zamka nie zmieniono, i nic tego
nie zauważyło, bo żaden test nie pytał o C1, DEL ani o znaki dwukierunkowe.

Ten plik jest pytaniem z zasady 7.3 zadanym temu modułowi: co by się wypisało, gdyby
neutralizacja przestała działać? Odpowiedź ma brzmieć „czerwony test", a nie „nic".
"""

from __future__ import annotations

import pytest

from kio_tool.safetext import FORMULA_PREFIXES, KEEP_CONTROL, sanitize_text, strip_control


# Znaki zapisane **punktami kodowymi, nie dosłownie**. Pierwsza wersja tej listy miała je
# wpisane wprost, czyli jako niewidoczne bajty w pliku testowym — których czytelnik
# przeglądu nie ma jak zweryfikować, a które są dokładnie tym, co ten test bada.
@pytest.mark.parametrize(
    ("nazwa", "znak"),
    [
        ("ESC (C0) — sekwencje ANSI sterujące terminalem", "\x1b"),
        ("NUL (C0)", "\x00"),
        ("BEL (C0)", "\x07"),
        ("DEL", "\x7f"),
        ("CSI jednobajtowe (C1) — sterowanie terminalem bez ESC", "\x9b"),
        ("NEL (C1)", "\x85"),
        ("ZERO WIDTH SPACE — niewidoczny podział rozbijający wyszukiwanie frazy", "\u200b"),
        ("RIGHT-TO-LEFT OVERRIDE — odwraca kolejność wyświetlania także w arkuszu", "\u202e"),
        ("LEFT-TO-RIGHT ISOLATE", "\u2066"),
        ("POP DIRECTIONAL ISOLATE", "\u2069"),
        ("BOM wewnątrz tekstu", "\ufeff"),
    ],
)
def test_znak_sterujacy_lub_formatujacy_nie_przechodzi(nazwa: str, znak: str) -> None:
    """Każdy z tych znaków przechodził przed poprawką albo przechodzi tylko dzięki niej.

    Cztery ostatnie pozycje to klasa, dla której ten moduł w ogóle istnieje w projekcie
    o tym materiale: tekst pisany przez osoby trzecie (cytaty z pism stron, fragmenty
    specyfikacji) trafia do arkusza i na ekran operatora.
    """
    wejscie = f"przed{znak}po"
    wynik = strip_control(wejscie)

    assert znak not in wynik, f"{nazwa}: znak przeszedł przez neutralizator"
    assert wynik == "przedpo", f"{nazwa}: neutralizator zmienił coś poza tym znakiem"


@pytest.mark.parametrize("znak", sorted(KEEP_CONTROL))
def test_tabulator_i_nowa_linia_przezywaja(znak: str) -> None:
    """Struktura dokumentu nie jest szumem.

    Tabulator i nowa linia niosą w orzeczeniu wcięcia list i podział akapitów; usunięcie ich
    zlepiłoby sekcje w jeden blok i zepsuło segmentację, zanim `parser/sections.py` w ogóle
    ją zobaczy.
    """
    assert strip_control(f"a{znak}b") == f"a{znak}b"


def test_tekst_bez_znakow_sterujacych_przechodzi_bez_zmiany() -> None:
    """Neutralizator usuwa szum, nie poprawia źródła.

    Polskie znaki diakrytyczne, cudzysłowy drukarskie, półpauza i znaki paragrafu są treścią
    orzeczenia. Moduł, który „przy okazji" normalizowałby typografię, zmieniałby dokument
    urzędowy — a `raw_versions` trzyma bajty właśnie po to, żeby tego nie robić.
    """
    tekst = "Izba zważyła, co następuje: „rażąco niska cena” — art. 224 ust. 1 Pzp; § 2 ust. 3."
    assert strip_control(tekst) == tekst


@pytest.mark.parametrize("prefiks", FORMULA_PREFIXES)
def test_prefiks_formuly_jest_neutralizowany(prefiks: str) -> None:
    """Każdy zadeklarowany prefiks faktycznie dostaje apostrof.

    Stała jest publiczna, więc deklaruje pokrycie. Wersja przeniesiona z CEIDG miała na tej
    liście `\\r`, który **nigdy** nie mógł zadziałać, bo `strip_control` usuwał go wcześniej —
    pozycja deklarowała ochronę, której nie było. Ten test jest strażnikiem tej klasy błędu:
    pozycja na liście bez działania zapali się na czerwono.
    """
    assert sanitize_text(f"{prefiks}SUMA(1)").startswith("'")


def test_znak_sterujacy_przed_prefiksem_formuly_nie_przemyca_formuly() -> None:
    """Kolejność: najpierw postać kanoniczna, potem rozpoznanie prefiksu.

    Gdyby rozpoznanie prefiksu szło przed usunięciem znaków sterujących, napis `\\x1b=SUMA(1)`
    nie zaczynałby się od `=`, nie dostałby apostrofu, a arkusz i tak zobaczyłby formułę,
    bo `\\x1b` zostałby usunięty po drodze albo zignorowany przez program otwierający plik.
    """
    assert sanitize_text("\x1b=SUMA(1)") == "'=SUMA(1)"


def test_zwykly_tekst_orzeczenia_nie_dostaje_apostrofu() -> None:
    """Neutralizacja nie może dotykać większości komórek.

    Apostrof jest widoczny dla czytelnika arkusza, więc fałszywe trafienie ma koszt — a nie
    zero, jak przy neutralizacji znaków niewidocznych.
    """
    assert sanitize_text("KIO 827/18") == "KIO 827/18"
