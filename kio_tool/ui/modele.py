"""Pojemniki widoku: kształty, w które `ui/texts.py` układa zdania.

Wydzielone z `texts.py` 2026-09-20, gdy ten przekroczył sufit 800 linii przy dopisaniu pola
`liczby`. Sufit istnieje po to, żeby wzrost modułu był aktem świadomym, więc dopisanie go do
listy wyjątków byłoby obejściem własnej reguły — szew jest przy tym prawdziwy, nie mechaniczny:
`texts` produkuje **zdania**, a te klasy są **strukturami**. Dowodem szwu jest `ui/maszynowo.py`,
które potrzebuje `Block` i nie potrzebuje ani jednego zdania.

Moduł czysty tak samo jak `texts` (reguła 6): bez `rich`, `typer`, `questionary`, `httpx`,
`sqlite3`. `texts` re-eksportuje te nazwy, więc dotychczasowe `from .texts import Block` działa
dalej i warstwa widoku zachowuje jedno publiczne wejście.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Odcinek:
    """Odcinek tekstu orzeczenia: rodzaj sekcji, przedział `[start, koniec)` w treści i sam tekst.

    `tresc` jest `None`, gdy odcinek nie został wybrany — wtedy blok niesie tylko jego miejsce
    i długość, żeby agent zobaczył mapę dokumentu, zanim poprosi o 28 tysięcy znaków
    uzasadnienia (`czytaj`, 2026-09-22).
    """

    rodzaj: str
    start: int
    koniec: int
    tresc: str | None = None

    @property
    def znakow(self) -> int:
        return self.koniec - self.start


@dataclass(frozen=True)
class Block:
    """Jeden ekran albo jedna tabela. `headers` puste = blok klucz-wartość.

    `liczby` to te same wielkości co w `notes`, tylko bez zdania wokół nich — dla wyjścia
    maszynowego (`ui/maszynowo.py`, od 2026-09-20). Nie są drugim źródłem prawdy: obie postacie
    powstają z tych samych argumentów w tej samej funkcji `blok_*`, więc nie mają jak się
    rozjechać. Agent czytający „trafień: 61" ze zdania musiałby parsować prozę, a proza jest
    własnością widoku dla człowieka i wolno jej się zmienić bez uprzedzenia.
    """

    title: str
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    notes: tuple[str, ...] = ()
    liczby: tuple[tuple[str, int], ...] = ()
    kolumny_maszynowe: tuple[str, ...] = ()
    """Kolumny wyłącznie dla wyjścia maszynowego, doklejane do `headers` wiersz po wierszu
    z `wiersze_maszynowe`. Tabela dla oka ich nie rysuje: blok cytowania i adres źródła przy
    każdym trafieniu rozsadziłyby szerokość terminala, a agent potrzebuje ich w całości, żeby
    przejść od trafienia do źródła bez drugiego polecenia (2026-09-22)."""
    wiersze_maszynowe: tuple[tuple[str, ...], ...] = ()
    odcinki: tuple[Odcinek, ...] = ()
    """Tekst ciągły pod tabelą — odcinki orzeczenia w `czytaj`. Konsola drukuje te z treścią,
    wyjście maszynowe oddaje wszystkie (z treścią albo samą długością)."""

    def as_text(self) -> str:
        """Postać tekstowa — do logu, do trybu cichego i do asercji w testach."""
        lines = [self.title] if self.title else []
        if self.headers:
            lines.append(" | ".join(self.headers))
        lines.extend(" | ".join(row) for row in self.rows)
        lines.extend(o.tresc for o in self.odcinki if o.tresc is not None)
        lines.extend(self.notes)
        return "\n".join(lines)


RodzajPytania = Literal["wybor", "tekst", "tak_nie"]


@dataclass(frozen=True)
class Opcja:
    """Jedna odpowiedź do wyboru: `klucz` wraca do programu, `etykieta` idzie na ekran."""

    klucz: str
    etykieta: str


@dataclass(frozen=True)
class Pytanie:
    """Pytanie jako dane (ADR-0008 Z-7): treść pisze ten moduł, zadaje je `ui/prompts.py`.

    `domyslna` jest odpowiedzią na sam Enter — i dlatego przy pytaniu o zgodę na przebieg
    masowy wynosi „nie": Enter nie ma prawa pobrać czterech tysięcy orzeczeń (ADR-0008 §10).
    """

    tresc: str
    rodzaj: RodzajPytania = "wybor"
    opcje: tuple[Opcja, ...] = ()
    domyslna: str | None = None
    podpowiedz: str = ""
    """Co wolno wpisać, w nawiasie za pytaniem — format daty, przykład, znaczenie pustej
    odpowiedzi. Operator, który nie zna narzędzia, nie ma tego skąd wiedzieć, a pytanie bez
    podpowiedzi wygląda tak samo jak pytanie, na które jest jedna poprawna odpowiedź
    (wzorzec z `ceidg-tool`, zgłoszenie operatora 2026-09-20)."""


@dataclass(frozen=True)
class StanKorpusu:
    """Liczby, które kreator pokazuje **zanim** operator cokolwiek wybierze.

    Pierwszy ekran bez stanu mówi, czym narzędzie jest; ekran ze stanem mówi, co operator ma
    w ręku — a to jest ta informacja, której brakowało, żeby wybrać pozycję menu świadomie.
    Zero żądań: wszystkie trzy liczby są odczytem z lokalnej bazy.
    """

    dokumentow: int
    zaindeksowanych: int
    przerwanych: int
    sciezka: str
