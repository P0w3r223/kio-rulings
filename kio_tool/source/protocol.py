"""Typy wspólne kanałów: zakres, kandydat, surowy dokument, ślad żądań i protokół `Channel`.

Dwie operacje o różnym koszcie (architektura 4.3, wzorzec dwóch kroków z Rechtspraak): listowanie
jest tanie i stronicowane, pobranie drogie. `Candidate` niesie **minimum do decyzji, czy
pobierać** — referencję, sygnatury, datę wydania tak, jak przyszła — i nic więcej. To jest
granica z reguły 19 w brzmieniu ADR-0005 Z-5: pole o nieznanym pochodzeniu (`pola_odrzucone`
w `contract.yaml`) nie ma w tym typie miejsca, więc nie wchodzi do tabel pochodnych nie dzięki
czyjejś pamięci, tylko dlatego, że nie ma pola, którym mogłoby pójść. Surowe bajty idą osobno,
w całości, w `RawDocument`.

`Channel` nie ma `capabilities()` — ADR-0005 Z-9 zdjął tę kolumnę ze ścieżki krytycznej, a
interfejs wyprowadzony z jednej implementacji koduje jej przypadkowości (Z-7), więc trójka metod
wraca przy drugim kanale, jeśli ten jej potrzebuje.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from ..docid import SourceName
from ..errors import ConfigError
from ..logbook import Wynik


@dataclass(frozen=True)
class Scope:
    """Zakres listowania: daty wydania (obie granice włącznie, każda opcjonalna) i filtry.

    `filtry` niesie **pola kryteriów po naszych nazwach** (`criteria.POLA_FILTROW`), nie
    parametry serwisu — tłumaczy je adapter przez `contract.yaml` (`parametry_listy.filtry`,
    reguła 22). Kolejność dat sprawdzana przy budowie, nie w kanale. Zakres bez dat i bez
    filtrów jest tu legalny (kanał umie wylistować wszystko); czy wolno go **użyć**, rozstrzyga
    `pipeline` na `Criteria.is_empty()`.
    """

    od: date | None = None
    do: date | None = None
    filtry: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.od is not None and self.do is not None and self.od > self.do:
            raise ConfigError(
                f"Zakres dat jest odwrócony: od {self.od.isoformat()} do {self.do.isoformat()}. "
                "Początek nie może być późniejszy niż koniec."
            )

    @property
    def etykieta(self) -> str:
        """Postać do kolumny `runs.zakres` i na ekran: `2024-01-01..2024-01-31; fraza=oferta`.

        Dla samych dat jest to dokładnie napis sprzed etapu IV (`od..do`) — kolumna `zakres`
        przebiegów z bazy sprzed migracji czyta się tak samo jak nowych.
        """
        od = self.od.isoformat() if self.od else "…"
        do = self.do.isoformat() if self.do else "…"
        czesci = [f"{od}..{do}"]
        czesci.extend(f"{pole}={wartosc}" for pole, wartosc in sorted(self.filtry.items()))
        return "; ".join(czesci)


@dataclass(frozen=True)
class Candidate:
    """Jeden rekord listy: tyle, ile trzeba, żeby zdecydować o pobraniu i policzyć `doc_id`."""

    source_ref: str
    sygnatury: tuple[str, ...]
    data_wydania: str | None
    """Tak, jak przyszła z kanału — także wtedy, gdy jest błędna (Atlas: 9 ze 100 rekordów
    pomiaru 3a). Adapter nie ma prawa jej poprawiać przed zapisem (reguła 19)."""
    strona: int
    """Strona listowania, z której kandydat pochodzi — punkt kontrolny wznawiania.

    `pipeline` zapisuje ją do `runs.ostatnia_strona` po każdym zapisanym dokumencie, a przy
    wznowieniu prosi kanał o listę od tej strony. Kandydaci z tej strony już zapisani wypadają
    na `has_document`, więc nieaktualny punkt kontrolny kosztuje najwyżej jedną stronę listy,
    nigdy duplikat (ADR-0001 2.3).
    """


@dataclass(frozen=True)
class RawDocument:
    """Bajty tak, jak przyszły, plus nagłówki i moment pobrania. Bez parsowania (reguła 19)."""

    source_ref: str
    content: bytes
    headers: Mapping[str, str]
    fetched_at: str
    sha256: str


class SladZadan(Protocol):
    """Odbiorca wyniku każdego żądania, wołany **w chwili powrotu żądania**.

    Kanał nie zna bazy (reguła 2) — historię żądań dostaje jako protokół. W przebiegu masowym
    wpis idzie do `requests_log` (`pipeline`), w sondzie do `logbook.Kronika`, która ten
    protokół spełnia bez wiedzy o nim. Wiersz powstaje po każdym żądaniu, a nie po całym
    przebiegu: przerwany przebieg ma zostawić ślad po tym, co **już** poszło do cudzego serwisu.
    """

    def zanotuj(self, wynik: Wynik) -> Wynik: ...


class BezSladu:
    """Ślad, który nic nie zapisuje — do testów kanału, które pytają o co innego."""

    def zanotuj(self, wynik: Wynik) -> Wynik:
        return wynik


class Channel(Protocol):
    """Kanał za jednym interfejsem (architektura 4.3)."""

    name: SourceName

    def list_candidates(self, scope: Scope, *, od_strony: int = 1) -> Iterator[Candidate]:
        """Tanie, stronicowane. Jedno żądanie na stronę; `od_strony` przy wznowieniu."""
        ...

    def fetch(self, ref: str) -> RawDocument:
        """Drogie. Bajty tak, jak przyszły, plus nagłówki i moment pobrania. Nie parsuje."""
        ...


# Jak w `progress.py`: bez przypisania mypy nie sprawdza, czy `BezSladu` spełnia protokół.
_ZGODNOSC_Z_PROTOKOLEM: SladZadan = BezSladu()
