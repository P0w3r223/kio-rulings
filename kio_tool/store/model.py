"""Klasy danych magazynu: przebieg, metryka, struktura, filtr, dokument, wynik wyszukiwania.

Wydzielone z `store.py` 2026-09-22 (ADR-0009 Z-1) — kształty, nie dostęp do danych."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..criteria import Criteria

STATUSY_PRZEBIEGU = ("w_toku", "zakonczony", "przerwany", "blad")
STATUSY_WZNAWIALNE = ("przerwany", "w_toku")
"""Stany, z których `resume_run` wraca do pracy: przerwany właściwym wyjątkiem albo osierocony
(`w_toku` po ubiciu procesu) — powód w docstringu `resume_run`."""


@dataclass(frozen=True)
class Przebieg:
    run_id: str
    kanal: str
    zakres: str
    started_at: str
    finished_at: str | None
    status: str
    ostatnia_strona: int | None
    powod: str | None
    kryteria: str | None
    """`Criteria.canonical_json()`; `None` dla przebiegu sprzed schematu 2."""
    fingerprint: str | None
    dokumentow: int
    """Kandydatów związanych z przebiegiem (`run_documents`) — nowych i pominiętych."""
    zadan: int
    """Wierszy w `requests_log` tego przebiegu."""


@dataclass(frozen=True)
class Metryka:
    """Pochodne bieżącej wersji dokumentu — kształt `parser.details.Szczegoly` plus wersja odczytu.

    Osobna klasa, a nie import `Szczegoly`: magazyn nie ma znać parsera (kierunek zależności
    idzie przez `pipeline`, architektura 4.2), a te same nazwy pól sprawiają, że przepisanie
    w `pipeline` jest jednym wywołaniem `dataclasses.asdict`.
    """

    parse_version: int
    sygnatura_glowna: str | None
    sygnatury: tuple[str, ...]
    data_wydania: str | None
    data_rozprawy: str | None
    rodzaj: str | None
    rozstrzygniecie: str | None
    rozstrzygniecie_surowe: str | None
    przewodniczacy: str | None
    odwolujacy: str | None
    zamawiajacy: str | None
    przepisy: tuple[str, ...]
    koszty: float | None
    url_zrodla: str | None
    tresc: str


@dataclass(frozen=True)
class WierszSekcji:
    """Sekcja w oryginale — kształt `parser.sections.Sekcja` plus skrót fragmentu (Z-11)."""

    porzadek: int
    rodzaj: str
    start: int
    koniec: int
    sha256: str


@dataclass(frozen=True)
class WierszCytowania:
    porzadek: int
    zrodlo: str
    rodzaj: str
    sygnatura: str | None
    surowy: str
    start: int | None
    koniec: int | None


@dataclass(frozen=True)
class WierszPrzepisu:
    porzadek: int
    zrodlo: str
    postac: str
    akt: str
    surowy: str
    start: int | None
    koniec: int | None


@dataclass(frozen=True)
class Struktura:
    """Struktura wersji (ADR-0006 Z-4): sekcje, cytowania, przepisy. Magazyn nie zna parsera —
    `pipeline` przepisuje wyniki `parser/*` na te wiersze, jak `Metryka` z `Szczegoly`."""

    sekcje: tuple[WierszSekcji, ...]
    cytowania: tuple[WierszCytowania, ...]
    przepisy: tuple[WierszPrzepisu, ...]


@dataclass(frozen=True)
class StrukturaDokumentu:
    """Struktura bieżącej wersji jednego dokumentu, tak jak leży w bazie — wejście raportu
    pokrycia (ADR-0006 Z-12). Bez tekstu: raport liczy, nie cytuje."""

    doc_id: str
    content_sha256: str
    sygnatura_glowna: str | None
    data_wydania: str | None
    parse_version: int | None
    sekcje: tuple[WierszSekcji, ...]
    cytowania: tuple[WierszCytowania, ...]
    przepisy: tuple[WierszPrzepisu, ...]


@dataclass(frozen=True)
class Filtr:
    """Filtr korpusu lokalnego — po naszych nazwach pól, wartości z `Criteria`.

    Daty porównują `documents.data_wydania` jako napisy ISO; pola metadanych wymagają wiersza
    w `metadata` (dokument niezaindeksowany **wypada** z filtra po tych polach — liczbę
    zaindeksowanych podaje `szukaj`, żeby ta strata nie była cicha). Pola tekstowe dopasowują
    podnapis bez rozróżniania wielkości liter ASCII (`LIKE` SQLite nie składa liter polskich).
    """

    od: date | None = None
    do: date | None = None
    rozstrzygniecie: tuple[str, ...] = ()
    rodzaj: tuple[str, ...] = ()
    przewodniczacy: str = ""
    przepis: str = ""
    strona: str = ""
    fraza: str = ""

    @classmethod
    def z_kryteriow(cls, kryteria: Criteria) -> Filtr:
        return cls(
            od=kryteria.od,
            do=kryteria.do,
            rozstrzygniecie=kryteria.rozstrzygniecie,
            rodzaj=kryteria.rodzaj,
            przewodniczacy=kryteria.przewodniczacy,
            przepis=kryteria.przepis,
            strona=kryteria.strona,
            fraza=kryteria.fraza,
        )

    @property
    def ma_daty(self) -> bool:
        return self.od is not None or self.do is not None


@dataclass(frozen=True)
class Dokument:
    """Dokument z bieżącą wersją — do eksportu i przeliczania."""

    doc_id: str
    source: str
    source_ref: str
    sygnatury: tuple[str, ...]
    data_wydania: str | None
    current_sha256: str
    fetched_at: str
    content_bytes: bytes


@dataclass(frozen=True)
class Trafienie:
    doc_id: str
    source: str
    source_ref: str
    sygnatura: str | None
    data_wydania: str | None
    rozstrzygniecie: str | None
    fragment: str


@dataclass(frozen=True)
class Wyszukanie:
    """Trafienia **z liczbami** — mina 2 audytu: wynik ma mówić, czego nie objął."""

    trafienia: tuple[Trafienie, ...]
    w_korpusie: int
    zaindeksowanych: int
    trafien: int
    bez_daty_poza_filtrem: int
    """Dokumenty pasujące do reszty filtrów, ale bez `data_wydania` — wypadły z filtra dat."""
