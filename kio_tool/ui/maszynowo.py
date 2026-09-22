"""Wyjście maszynowe: ten sam `Block`, odbiorcą program zamiast oka.

Powstało 2026-09-20 z pomiaru, nie z pomysłu. Tabela `rich` puszczona do potoku nie zna
szerokości terminala, przyjmuje 80 znaków i **łamie wartości w środku**: identyfikator przebiegu
`atlas-5e3048a63b05` rozpadał się na trzy wiersze, a zakres dat na dwa — czyli dokładnie to,
czego agent potrzebuje do `eksportuj --run-id`, stawało się nie do odczytania. Obejście przez
`COLUMNS` istnieje, ale jest niewidoczne z zewnątrz i nikt go nie odkryje przez przypadek.

**Postać: JSON Lines, jeden dokument na wiersz**, każdy z polem `rodzaj`. Nie jeden obiekt na
przebieg polecenia, bo komunikat (`nowa baza`) potrafi paść przed blokiem wyniku, a wtedy trzeba
by albo buforować całe wyjście, albo zgubić zdanie. Ten sam kształt niesie `eksportuj --format
jsonl`, więc konsument uczy się go raz.

**Neutralizacja jest tu z konstrukcji, nie z dyscypliny.** Reguła 10 pilnuje drogi do `rich`,
bo tam nawias kwadratowy jest znacznikiem, a sekwencja sterująca — poleceniem dla terminala.
`json.dumps` koduje cudzysłów, odwrotny ukośnik i **wszystkie znaki sterujące łącznie z `ESC`
(`\\u001b`)**, więc tekst z uzasadnienia nie ma jak wyjść poza swoją wartość. Ten moduł nie
importuje `rich` i nie ma prawa go zaimportować.
"""

from __future__ import annotations

import json
import sys
from typing import IO

from .texts import Block, Odcinek

RODZAJ_BLOK = "blok"
RODZAJ_KOMUNIKAT = "komunikat"
RODZAJ_OSTRZEZENIE = "ostrzezenie"
RODZAJ_BLAD = "blad"

_LITERY = str.maketrans(
    {"ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ź": "z", "ż": "z"}
)


def klucz(naglowek: str) -> str:
    """Nagłówek dla oka („data wydania", „żądań") na klucz dla programu („data_wydania", „zadan").

    Fałdowanie polskich liter jest świadome: klucz JSON z ogonkiem jest legalny, ale przy
    odczycie w cudzym narzędziu bywa rozjechany kodowaniem, a to jest dokładnie ta klasa cichej
    usterki, przed którą powstał ten moduł.
    """
    zwykle = naglowek.strip().lower().translate(_LITERY)
    znaki = [z if z.isalnum() else "_" for z in zwykle]
    return "_".join(filter(None, "".join(znaki).split("_")))


def klucze(naglowki: tuple[str, ...]) -> tuple[str, ...]:
    """Klucze kolumn, z głośnym sprzeciwem przy kolizji.

    Dwa nagłówki dające ten sam klucz nadpisałyby się w słowniku i konsument dostałby wynik
    krótszy o kolumnę, nie wiedząc o tym. Cisza jest usterką (doktryna 7.2), więc kolizja jest
    wyjątkiem programisty, a nie cichym `_2` na końcu nazwy.
    """
    wynik = tuple(klucz(n) for n in naglowki)
    if len(set(wynik)) != len(wynik):
        raise ValueError(f"kolizja kluczy kolumn: {naglowki} → {wynik}")
    return wynik


def blok_na_slownik(block: Block) -> dict[str, object]:
    """`Block` na dokument JSON. Wiersze jako obiekty, gdy blok ma nagłówki."""
    dokument: dict[str, object] = {"rodzaj": RODZAJ_BLOK, "tytul": block.title}
    if block.headers:
        nazwy = klucze(block.headers + block.kolumny_maszynowe)
        dodatki = block.wiersze_maszynowe or tuple(() for _ in block.rows)
        if block.kolumny_maszynowe and len(dodatki) != len(block.rows):
            # Dodatek przesunięty o wiersz przypisałby trafieniu cudzy blok cytowania — to jest
            # błąd programisty, nie stan do pokazania.
            raise ValueError(f"wierszy {len(block.rows)}, dodatków {len(dodatki)}: {block.title}")
        dokument["kolumny"] = list(nazwy)
        dokument["wiersze"] = [
            dict(zip(nazwy, wiersz + dodatek, strict=False))
            for wiersz, dodatek in zip(block.rows, dodatki, strict=True)
        ]
    else:
        dokument["wiersze"] = [{"klucz": w[0], "wartosc": w[1]} for w in block.rows if len(w) > 1]
    if block.odcinki:
        dokument["odcinki"] = [odcinek_na_slownik(o) for o in block.odcinki]
    if block.liczby:
        dokument["liczby"] = dict(block.liczby)
    if block.notes:
        dokument["uwagi"] = list(block.notes)
    return dokument


def odcinek_na_slownik(odcinek: Odcinek) -> dict[str, object]:
    """Odcinek z miejscem i długością zawsze, z treścią tylko wtedy, gdy ją wybrano — brak klucza
    `tresc` znaczy „nie proszono", pusty napis znaczyłby „sekcja jest pusta"."""
    wynik: dict[str, object] = {
        "rodzaj": odcinek.rodzaj,
        "start": odcinek.start,
        "koniec": odcinek.koniec,
        "znakow": odcinek.znakow,
    }
    if odcinek.tresc is not None:
        wynik["tresc"] = odcinek.tresc
    return wynik


class JsonView:
    """Widok maszynowy — ta sama powierzchnia co `ConsoleView`, inne wyjście.

    Spełnia protokół `obsluga.Widok` plus `error`, więc polecenie nie wie, któremu widokowi
    oddaje blok. Błędy idą na `stderr` tak samo jak w widoku konsolowym: przekierowanie wyniku
    do pliku nie ma prawa zjeść zdania o tym, czemu wyniku nie ma.
    """

    def __init__(self, wyjscie: IO[str] | None = None, bledy: IO[str] | None = None) -> None:
        self._wyjscie = wyjscie
        self._bledy = bledy

    def _pisz(self, strumien: IO[str], dokument: dict[str, object]) -> None:
        print(json.dumps(dokument, ensure_ascii=False), file=strumien)

    @property
    def _stdout(self) -> IO[str]:
        # Strumień rozstrzygany przy zapisie, nie przy budowie widoku: testy CLI podmieniają
        # `sys.stdout` już po utworzeniu widoku, a widok zamrożony na starym strumieniu milczałby
        # w asercjach. Tę samą pułapkę opisuje docstring `richtext.make_console`.
        return self._wyjscie if self._wyjscie is not None else sys.stdout

    @property
    def _stderr(self) -> IO[str]:
        return self._bledy if self._bledy is not None else sys.stderr

    def block(self, block: Block) -> None:
        self._pisz(self._stdout, blok_na_slownik(block))

    def message(self, text: str) -> None:
        self._pisz(self._stdout, {"rodzaj": RODZAJ_KOMUNIKAT, "tresc": text})

    def warning(self, text: str) -> None:
        self._pisz(self._stdout, {"rodzaj": RODZAJ_OSTRZEZENIE, "tresc": text})

    def error(self, text: str) -> None:
        self._pisz(self._stderr, {"rodzaj": RODZAJ_BLAD, "tresc": text})
