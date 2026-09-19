"""SQLite: dokumenty, wersje surowe, przebiegi, dziennik żądań, metadane, indeks pełnotekstowy —
model danych 4.4 w wersji minimalnej, po przyjęciu ADR-0001 (2026-09-18); schemat 2 od etapu IV.

Bramka `store.py` → ADR-0001 (`tests/test_bramki_faz.py`) jest strażnikiem miny 1: w `ceidg-tool`
jeden wpis miał dwie pisownie identyfikatora, klucz główny był wrażliwy na wielkość liter, a jedna
noc kosztowała 2 681 żądań i zero użytecznych rekordów. Ten plik powstał **po** rozstrzygnięciu
tożsamości, więc nie zna pisowni referencji — dostaje gotowy `doc_id` z `docid.document_id`,
jedynego producenta tożsamości (reguła 14), i nie składa go sam z niczego.

Niezmiennik wznowienia (bramka fazy 1, audyt 9; ADR-0001 2.3): `raw_versions (doc_id,
content_sha256)` jest kluczem głównym i zapis idzie `INSERT OR IGNORE`, więc przerwany i wznowiony
przebieg nie tworzy duplikatu nawet przy nieaktualnym punkcie kontrolnym. Dokument, jego wersja,
powiązanie z przebiegiem i punkt kontrolny idą w jednej transakcji (`transakcja()`), po awarii są
wszystkie albo żadne — to jest to samo zdanie, które `ceidg-tool` zapisał o rekordach strony
i checkpoincie. `content_bytes` to bajty dokładnie takie, jakie przyszły po drucie (reguła 19
w brzmieniu ADR-0005 Z-5), a `content_sha256` liczy **ten** moduł z tego, co zapisuje — i porównuje
ze skrótem podanym przez kanał, bo skrót niezgodny z bajtami zrywa łańcuch dowodowy przy pierwszym
zapisie.

**Schemat 2 (etap IV, 2026-09-18)** dokłada do schematu 1: `runs.kryteria` i `runs.fingerprint`
(wznawianie po odcisku kryteriów, nie po etykiecie zakresu), `run_documents` (każdy kandydat
przebiegu — nowy i pominięty — jest z nim związany, bo `eksportuj --run-id` ma eksportować to, co
przebieg **objął**, a nie tylko to, co pobrał), `metadata` (pochodne z bieżącej wersji, przypięte
do `content_sha256` i `parse_version`) oraz `fts` (FTS5 nad sygnaturami i treścią bieżącej
wersji). Migracja 1 → 2 jest **dopisaniem**, nie przebudową: kolumny `ALTER TABLE … ADD`, tabele
`CREATE IF NOT EXISTS`, a odcisk przebiegów sprzed migracji jest dopisywany z ich etykiety
zakresu — przebieg przerwany pod schematem 1 wznawia się pod schematem 2 tym samym poleceniem.
Nazw pól kanału ten moduł nie zna: `Metryka` przychodzi gotowa z `parser/details.py`.

**Schemat 4 (2026-09-19)** nie zmienia ani jednej tabeli — jest wyłącznie backfillem: odtwarza
`run_documents` przebiegom sprzed schematu 2, którym migracja 1 → 2 dopisała odcisk kryteriów,
ale powiązań nie. Numer wersji niesie ten backfill, bo alternatywy są gorsze: skan przy każdym
otwarciu bazy kosztowałby przy każdym poleceniu, a beneficjenta ma tylko raz, zaś migracja
zaczepiona o wersję 1 nie zapaliłaby się na bazie stojącej już na 3 — czyli dokładnie na tej,
która lukę ma. Odtworzenie jest dokładne, nie zgadywane; czym stoi, mówi
`_odtworz_powiazania_sprzed_schematu_2`.

**Schemat 6 (2026-09-19, ADR-0006 Z-4)** dokłada `sections`, `citations` i `provisions` — samym
`CREATE TABLE IF NOT EXISTS`, bez ruszania istniejących tabel. Stare wersje dostają strukturę przy
`przelicz`, bo `PARSE_VERSION` wzrósł do 2.

**Schemat 5 (2026-09-19, ADR-0007 Z-8)** dokłada kolumnę `requests_log.proba`: dwie próby jednego
żądania mają być w dzienniku odróżnialne od dwóch różnych żądań, bo inaczej pomiaru 24
(skuteczność ponowień) nie dałoby się zrobić bez ponownego obciążenia serwisu.

Czego tu **nie ma** wobec wzorca z `ceidg-tool` (1 208 linii), z powodem przy każdym: dzierżawy
blokady (jeden operator i jeden proces; wraca razem z harmonogramem), kwarantanny uszkodzonej bazy
i `integrity_check` przy otwarciu (bez pomiaru, że to się zdarza, byłoby to mechanizmem bez
przedmiotu — ADR-0005 §1). Nie ma tu `httpx` (reguła 3) ani `rich` (reguła 4).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import TypeVar

from .clock import Clock, utc_iso
from .config import mask_tokens
from .criteria import Criteria
from .errors import ConfigError, KioError, RunNotFoundError, StoreError
from .ratelimit import RequestStamp

SCHEMA_VERSION = 6
_W = TypeVar("_W")
STATUSY_PRZEBIEGU = ("w_toku", "zakonczony", "przerwany", "blad")
STATUSY_WZNAWIALNE = ("przerwany", "w_toku")
"""Stany, z których `resume_run` wraca do pracy: przerwany właściwym wyjątkiem albo osierocony
(`w_toku` po ubiciu procesu) — powód w docstringu `resume_run`."""
TABELE = frozenset(
    {
        "documents",
        "raw_versions",
        "runs",
        "requests_log",
        "run_documents",
        "metadata",
        "fts",
        "sections",
        "citations",
        "provisions",
    }
)
"""Tabele, które `count` zna z nazwy — nazwa tabeli nie jest parametrem zapytania, więc nie
wolno jej wstawić do SQL z zewnątrz bez tej listy."""

DOMYSLNY_BUSY_TIMEOUT_S = 30.0
DOMYSLNY_LIMIT_TRAFIEN = 20
KOLUMNA_FTS_TRESCI = 2
"""Indeks kolumny `tresc` w `fts` dla `snippet()` — kolumny liczą się od zera: `doc_id`,
`sygnatury`, `tresc`."""

_SCHEMA: tuple[str, ...] = (
    """
CREATE TABLE IF NOT EXISTS documents (
  doc_id          TEXT PRIMARY KEY,
  source          TEXT NOT NULL,
  source_ref      TEXT NOT NULL,
  sygnatury       TEXT NOT NULL,
  data_wydania    TEXT,
  first_seen_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  current_sha256  TEXT NOT NULL,
  UNIQUE (source, source_ref)
)""",
    """
CREATE TABLE IF NOT EXISTS raw_versions (
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
  content_sha256  TEXT NOT NULL,
  fetched_at      TEXT NOT NULL,
  content_bytes   BLOB NOT NULL,
  fetch_meta      TEXT NOT NULL,
  PRIMARY KEY (doc_id, content_sha256)
)""",
    """
CREATE TABLE IF NOT EXISTS runs (
  run_id          TEXT PRIMARY KEY,
  kanal           TEXT NOT NULL,
  zakres          TEXT NOT NULL,
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  status          TEXT NOT NULL CHECK (status IN ('w_toku','zakonczony','przerwany','blad')),
  ostatnia_strona INTEGER,
  powod           TEXT,
  kryteria        TEXT,
  fingerprint     TEXT
)""",
    """
CREATE TABLE IF NOT EXISTS requests_log (
  run_id          TEXT NOT NULL REFERENCES runs(run_id),
  ts              TEXT NOT NULL,
  metoda          TEXT NOT NULL,
  url_redacted    TEXT NOT NULL,
  status          INTEGER,
  ms              INTEGER NOT NULL,
  bajtow          INTEGER NOT NULL,
  sha256          TEXT,
  ksztalt         TEXT NOT NULL,
  retry_after_s   REAL,
  proba           INTEGER NOT NULL DEFAULT 1
)""",
    "CREATE INDEX IF NOT EXISTS requests_log_ts_idx ON requests_log(ts)",
    """
CREATE TABLE IF NOT EXISTS run_documents (
  run_id          TEXT NOT NULL REFERENCES runs(run_id),
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
  position        INTEGER NOT NULL,
  nowy            INTEGER NOT NULL,
  PRIMARY KEY (run_id, doc_id)
)""",
    """
CREATE TABLE IF NOT EXISTS metadata (
  doc_id                  TEXT NOT NULL REFERENCES documents(doc_id),
  content_sha256          TEXT NOT NULL,
  parse_version           INTEGER NOT NULL,
  sygnatura_glowna        TEXT,
  data_wydania            TEXT,
  data_rozprawy           TEXT,
  rodzaj                  TEXT,
  rozstrzygniecie         TEXT,
  rozstrzygniecie_surowe  TEXT,
  przewodniczacy          TEXT,
  odwolujacy              TEXT,
  zamawiajacy             TEXT,
  przepisy                TEXT NOT NULL,
  koszty                  REAL,
  url_zrodla              TEXT,
  dlugosc_tresci          INTEGER NOT NULL,
  PRIMARY KEY (doc_id, content_sha256)
)""",
    # Schemat 6 (ADR-0006 Z-4, Z-5, Z-7): struktura bieżącej wersji jako **offsety w oryginale**,
    # nie kopia tekstu, kluczowana `(doc_id, content_sha256)` jak `metadata`. `zrodlo` rozróżnia
    # nasz odczyt z treści od opracowania kanału (reguła 19) i nigdy nie jest nadpisywane.
    """
CREATE TABLE IF NOT EXISTS sections (
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
  content_sha256  TEXT NOT NULL,
  parse_version   INTEGER NOT NULL,
  porzadek        INTEGER NOT NULL,
  rodzaj          TEXT NOT NULL,
  char_start      INTEGER NOT NULL,
  char_end        INTEGER NOT NULL,
  sha256          TEXT NOT NULL,
  PRIMARY KEY (doc_id, content_sha256, porzadek)
)""",
    """
CREATE TABLE IF NOT EXISTS citations (
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
  content_sha256  TEXT NOT NULL,
  parse_version   INTEGER NOT NULL,
  porzadek        INTEGER NOT NULL,
  zrodlo          TEXT NOT NULL CHECK (zrodlo IN ('tresc', 'kanal')),
  rodzaj          TEXT NOT NULL,
  sygnatura       TEXT,
  surowy          TEXT NOT NULL,
  char_start      INTEGER,
  char_end        INTEGER,
  PRIMARY KEY (doc_id, content_sha256, zrodlo, porzadek)
)""",
    """
CREATE TABLE IF NOT EXISTS provisions (
  doc_id          TEXT NOT NULL REFERENCES documents(doc_id),
  content_sha256  TEXT NOT NULL,
  parse_version   INTEGER NOT NULL,
  porzadek        INTEGER NOT NULL,
  zrodlo          TEXT NOT NULL CHECK (zrodlo IN ('tresc', 'kanal')),
  postac          TEXT NOT NULL,
  akt             TEXT NOT NULL,
  surowy          TEXT NOT NULL,
  char_start      INTEGER,
  char_end        INTEGER,
  PRIMARY KEY (doc_id, content_sha256, zrodlo, porzadek)
)""",
    "CREATE INDEX IF NOT EXISTS citations_sygnatura_idx ON citations(sygnatura)",
    "CREATE INDEX IF NOT EXISTS provisions_postac_idx ON provisions(postac, akt)",
    "CREATE INDEX IF NOT EXISTS runs_fingerprint_idx ON runs(fingerprint)",
    # Kopia treści w FTS5, nie `content=`: treść leży w JSON-ie `raw_versions.content_bytes`,
    # a tabela zewnętrzna FTS5 czyta kolumny zwykłej tabeli — nie wyrażenie nad blobem.
    # `remove_diacritics 2` składa `ó`→`o`, ale nie `ł`→`l` (`ł` nie ma rozkładu w Unicode);
    # zmierzone 2026-09-18 na tym Pythonie: „zamowienie" trafia „Zamówienie", „lodz" nie trafia
    # „Łódź". To jest cecha wyszukiwania dosłownego, zapisana, nie ukryta (architektura 4.8).
    """
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  doc_id UNINDEXED, sygnatury, tresc, tokenize = 'unicode61 remove_diacritics 2'
)""",
)


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


class _Polaczenie:
    """Jedyny szew ze sterownikiem: każdy `sqlite3.Error` wychodzi stąd jako `StoreError`.

    `errors.KioError` obiecuje, że komunikat jest dla użytkownika, a `cli._obsluga_bledow` łapie
    wyłącznie `KioError` — więc `sqlite3.OperationalError: database or disk is full` przechodził
    obok taksonomii i kończył się śladem stosu (tester 2026-09-18). Tłumaczenie stoi przy
    połączeniu, nie w czterdziestu metodach: metoda dopisana jutro dostaje je za darmo.
    """

    def __init__(self, conn: sqlite3.Connection, sciezka: str) -> None:
        self._conn = conn
        self._sciezka = sciezka

    def execute(self, sql: str, parametry: Sequence[object] = ()) -> sqlite3.Cursor:
        try:
            return self._conn.execute(sql, parametry)
        except sqlite3.Error as blad:
            raise blad_bazy(self._sciezka, blad) from blad

    def executemany(self, sql: str, wiersze: Sequence[Sequence[object]]) -> sqlite3.Cursor:
        try:
            return self._conn.executemany(sql, wiersze)
        except sqlite3.Error as blad:
            raise blad_bazy(self._sciezka, blad) from blad

    def wycofaj(self) -> None:
        """`ROLLBACK`, który nie zastępuje wyjątku w locie.

        SQLite sam cofa transakcję przy `SQLITE_FULL` i `SQLITE_IOERR`, więc jawny `ROLLBACK`
        kończy się wtedy `cannot rollback - no transaction is active` — a rzucony z bloku
        `except` zastępował wyjątek w locie, łącznie z `KeyboardInterrupt`: `Ctrl+C` stawał się
        `StoreError`, przebieg dostawał `blad` zamiast `przerwany` i tracił punkt kontrolny
        (przegląd kodu 2026-09-18). Powód przerwania jest wart więcej niż powód nieudanego
        sprzątania, więc nieudany `ROLLBACK` jest tu przemilczany świadomie — transakcji i tak
        już nie ma.
        """
        if not self._conn.in_transaction:
            return
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            return

    def close(self) -> None:
        self._conn.close()

    @property
    def in_transaction(self) -> bool:
        return self._conn.in_transaction

    @property
    def row_factory(self) -> object:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, fabryka: object) -> None:
        self._conn.row_factory = fabryka  # type: ignore[assignment]


def blad_bazy(sciezka: str, blad: sqlite3.Error) -> KioError:
    """Wyjątek dla operatora zamiast komunikatu sterownika — ze ścieżką i tym, co zrobić.

    Trzy pomyłki o jedno dopełnienie ścieżki od poprawnej (przejście ręczne i tester
    2026-09-18): `--baza` na katalog (`unable to open database file`), na skoroszyt eksportu
    (`file is not a database`), na plik bez prawa zapisu. Dwie pierwsze są błędem wywołania
    (`ConfigError`, kod 3 — jak literówka w `--run-id`; przegląd kodu 2026-09-18); pełny dysk
    i błąd wejścia-wyjścia to awaria bazy (`StoreError`) z powodem sterownika dosłownie, bo on
    jest tu treścią, nie szumem.
    """
    if Path(sciezka).is_dir():
        return ConfigError(
            f"Ścieżka {sciezka} nie jest plikiem bazy kio-tool (to katalog). Podaj plik "
            "`*.sqlite` albo pomiń `--baza` — domyślna baza leży w katalogu danych użytkownika."
        )
    if "not a database" in str(blad):
        return ConfigError(
            f"Plik {sciezka} nie jest bazą kio-tool. Podaj plik `*.sqlite` założony przez to "
            "narzędzie albo pomiń `--baza`."
        )
    return StoreError(
        f"Baza {sciezka}: {blad}. Sprawdź miejsce na dysku i prawa do pliku; korpus w bazie "
        "jest nietknięty."
    )


class Store:
    """Baza lokalna korpusu. `open` tworzy katalog i schemat; `":memory:"` do testów."""

    def __init__(self, path: Path | str, *, clock: Clock) -> None:
        self._path = str(path)
        self._clock = clock
        self.nowa = self._path != ":memory:" and not Path(self._path).exists()
        """Czy to otwarcie założyło bazę — `cli` mówi o tym zdaniem, bo literówka w `--baza`
        wygląda inaczej tak samo jak pierwsze uruchomienie."""
        try:
            if isinstance(path, Path):
                path.parent.mkdir(parents=True, exist_ok=True)
            # `isolation_level=None`: transakcjami steruje **ten** moduł jawnie (`transakcja()`),
            # a pojedynczy zapis poza nią jest atomowy sam z siebie. Domyślny tryb `sqlite3`
            # otwiera transakcję niejawnie przed pierwszym `INSERT` i zamyka ją dopiero przy
            # `commit()` — czyli wpis do `requests_log` czekałby w otwartej transakcji na koniec
            # przebiegu, a przerwany przebieg nie zostawiałby śladu po żądaniach, które już poszły.
            polaczenie = sqlite3.connect(
                self._path, timeout=DOMYSLNY_BUSY_TIMEOUT_S, isolation_level=None
            )
        except (sqlite3.Error, OSError) as blad:
            sterownika = blad if isinstance(blad, sqlite3.Error) else sqlite3.OperationalError(blad)
            raise blad_bazy(self._path, sterownika) from blad
        self._conn = _Polaczenie(polaczenie, self._path)
        try:
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            if self._path != ":memory:":
                # WAL: `Ctrl+C` w środku zapisu zostawia bazę spójną, a czytelnik nie blokuje
                # pisarza. `PRAGMA journal_mode` **zwraca** tryb wynikowy — nieprzeczytany
                # zostawiałby ciche nieprzejście na WAL bez obserwatora (lekcja z `ceidg-tool`).
                tryb = self._conn.execute("PRAGMA journal_mode = WAL").fetchone()
                self.journal_mode = str(tryb[0]).lower() if tryb else "?"
            else:
                self.journal_mode = "memory"
            self._migruj()
        except KioError:
            # `with Store.open(...)` nie wchodzi w `__exit__`, gdy `__init__` rzuci — bez tego
            # plik bazy zostawał zajęty na Windowsie po nieudanej migracji (przegląd 2026-09-18).
            polaczenie.close()
            raise

    def _migruj(self) -> None:
        """Schemat do wersji `SCHEMA_VERSION` w jednej transakcji — bez utraty danych.

        Instrukcje idą pojedynczo, nie `executescript`: ten ostatni zatwierdza otwartą transakcję
        przed uruchomieniem, więc migracja przerwana w połowie zostawiałaby bazę w wersji, której
        żaden numer nie opisuje. `PRAGMA user_version` ustawia się na końcu, w tej samej
        transakcji — baza jest albo w starej wersji z nietkniętymi danymi, albo w nowej.
        """
        wersja = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if wersja > SCHEMA_VERSION:
            raise StoreError(
                f"Baza {self._path} ma schemat w wersji {wersja}, a narzędzie zna {SCHEMA_VERSION}."
            )
        with self.transakcja():
            if wersja == 1:
                self._migruj_1_do_2()
            for instrukcja in _SCHEMA:
                self._conn.execute(instrukcja)
            if wersja == 1:
                self._dopisz_odciski_przebiegom_sprzed_schematu_2()
            if 0 < wersja < 3:
                self._migruj_do_3()
            if 0 < wersja < 4:
                self._odtworz_powiazania_sprzed_schematu_2()
            if 0 < wersja < 5:
                self._migruj_do_5()
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migruj_1_do_2(self) -> None:
        """Kolumny `runs.kryteria` i `runs.fingerprint` — `CREATE IF NOT EXISTS` ich nie dopisze
        do tabeli, która już istnieje. Obecność sprawdzana, nie zakładana: `ALTER TABLE … ADD`
        na istniejącej kolumnie jest błędem, a baza po przerwanej migracji może ją już mieć."""
        obecne = {str(w["name"]) for w in self._conn.execute("PRAGMA table_info(runs)")}
        for kolumna in ("kryteria", "fingerprint"):
            if kolumna not in obecne:
                self._conn.execute(f"ALTER TABLE runs ADD COLUMN {kolumna} TEXT")

    def _migruj_do_3(self) -> None:
        """Kolumna `requests_log.retry_after_s` (schemat 3, 2026-09-18) — prośba serwisu ma
        przeżyć proces razem z faktem odmowy. Znalezisko testera: wznowienie po 429 odczekiwało
        własną blokadę limitera (60 s) zamiast `Retry-After` (np. 300 s), bo dziennik nagłówka nie
        zapisywał. Obecność kolumny sprawdzana, nie zakładana — jak w `_migruj_1_do_2`; tabela
        w bazie schematu 1 i 2 istnieje, więc `CREATE IF NOT EXISTS` kolumny nie dopisze."""
        obecne = {str(w["name"]) for w in self._conn.execute("PRAGMA table_info(requests_log)")}
        if "retry_after_s" not in obecne:
            self._conn.execute("ALTER TABLE requests_log ADD COLUMN retry_after_s REAL")

    def _migruj_do_5(self) -> None:
        """Kolumna `requests_log.proba` (schemat 5, ADR-0007 Z-8) — numer próby żądania.

        Wiersze sprzed schematu 5 dostają 1 z wartości domyślnej i to jest prawda o nich: przed
        ADR-0007 żaden kanał nie ponawiał. Obecność kolumny sprawdzana, nie zakładana — jak
        w `_migruj_do_3`."""
        obecne = {str(w["name"]) for w in self._conn.execute("PRAGMA table_info(requests_log)")}
        if "proba" not in obecne:
            self._conn.execute(
                "ALTER TABLE requests_log ADD COLUMN proba INTEGER NOT NULL DEFAULT 1"
            )

    def _dopisz_odciski_przebiegom_sprzed_schematu_2(self) -> None:
        """Przebieg sprzed schematu 2 miał wyłącznie zakres dat (`od..do`), więc jego kryteria
        i odcisk da się odtworzyć z etykiety — i dzięki temu przebieg przerwany pod schematem 1
        wznawia się pod schematem 2 tym samym poleceniem `pobierz --od … --do …`. Etykieta
        w innej postaci zostawia oba pola puste: lepsza jawna luka niż zgadywany odcisk."""
        wiersze = self._conn.execute(
            "SELECT run_id, zakres FROM runs WHERE fingerprint IS NULL"
        ).fetchall()
        for wiersz in wiersze:
            kryteria = _kryteria_z_etykiety(str(wiersz["zakres"]))
            if kryteria is None:
                continue
            self._conn.execute(
                "UPDATE runs SET kryteria = ?, fingerprint = ? WHERE run_id = ?",
                (kryteria.canonical_json(), kryteria.fingerprint(), wiersz["run_id"]),
            )

    def _odtworz_powiazania_sprzed_schematu_2(self) -> None:
        """`run_documents` dla przebiegów sprzed schematu 2 — odtworzone z dziennika żądań.

        Przebieg zapisany pod schematem 1 nie ma ani jednego wiersza powiązania, więc
        `eksportuj --run-id` zwraca dla niego zero dokumentów, choć jego dokumenty leżą
        w korpusie. Migracja 1 → 2 dopisała wtedy odciski kryteriów, ale powiązań nie — i to
        jest druga luka po tamtej, nie ta sama.

        **Zasięg jest węższy, niż brzmi, i to jest wybór.** Przebieg przerwany pod schematem 1
        i wznowiony pod schematem 2 ma powiązania **częściowe** — tylko dla kandydatów obsłużonych
        po wznowieniu. Taki przebieg ta migracja pomija w całości, bo warunek `NOT EXISTS` jest
        per przebieg: dopisywanie brakujących wierszy do przebiegu, który część ma pierwotną,
        mieszałoby wartości pierwotne z rekonstruowanymi w jednej tabeli i bez znacznika, który
        by je rozróżnił. Jawna luka jest tu tańsza niż niejawna mieszanina (znalezisko testera
        2026-09-19; `test_przebieg_z_czescia_powiazan_zostaje_pominiety_w_calosci` przypina ten
        zasięg, więc jego zmiana nie przejdzie po cichu).

        Łączenie idzie po `requests_log.sha256` = `raw_versions.content_sha256`, a **nie** po
        adresie: `store.py` nie zna kształtu adresów kanału (reguła 22) i nie zacznie go tutaj
        poznawać. Skrót odpowiedzi jest przy tym mocniejszym łącznikiem niż adres — mówi, że ten
        przebieg przywiózł dokładnie te bajty, a nie że pytał o ten zasób. Odpowiedzi listy
        odpadają same, bo ich skrót nie ma wiersza w `raw_versions`.

        `nowy = 1` nie jest założeniem: potok nie wysyła żądania za dokument, który już jest
        w bazie — pomija go bez żądania i wiąże z `nowy = 0` — więc żądanie zakończone wersją
        w `raw_versions` znaczy, że dokument był dla tego przebiegu nowy. `position` odtwarza się
        z kolejności żądań i jest **rekonstrukcją, nie wartością pierwotną**: numeracja wychodzi
        ciągła (1..N), a pierwotna mogła mieć przerwy po wznowieniu, bo liczyła także kandydatów
        pominiętych. Dla przebiegu bez pominięć obie są tym samym ciągiem.

        Przebieg, który **ma** już powiązania, zostaje nietknięty: tam wartości są pierwotne,
        a rekonstrukcja byłaby ich pogorszeniem. Przebieg bez dokumentów (pomiar filtru, który
        zwrócił zero trafień) nie dostaje nic i to jest poprawne — jego `rd = 0` jest prawdą
        o wyniku, a nie luką po migracji.

        Skrót wskazujący na **więcej niż jeden** dokument jest odrzucany, nie zgadywany:
        `raw_versions` ma klucz `(doc_id, content_sha256)`, więc dwa dokumenty o identycznej
        treści są stanem reprezentowalnym, a złączenie bez tego warunku dopisałoby przebiegowi
        dokument, o który nigdy nie pytał (znalezisko testera 2026-09-19, zmierzone na bazie
        jednorazowej). Że w korpusie operatora takich skrótów nie ma, jest faktem o **tych
        danych**, nie własnością kodu — i dlatego warunek stoi w zapytaniu, a nie w zdaniu niżej.

        Zmierzone 2026-09-19 na bazie operatora: jeden przebieg z luką (299 żądań), 295
        dokumentów odtworzonych, 4 strony listy odrzucone przez brak wersji, zero
        niejednoznacznych skrótów, zgodność 295/295 z niezależnym odniesieniem — te same
        dokumenty powiązane z późniejszym przebiegiem na tym samym zakresie.
        """
        osierocone = [
            str(w["run_id"])
            for w in self._conn.execute(
                "SELECT run_id FROM runs r WHERE NOT EXISTS "
                "(SELECT 1 FROM run_documents rd WHERE rd.run_id = r.run_id)"
            )
        ]
        for run_id in osierocone:
            wiersze = self._conn.execute(
                "SELECT v.doc_id AS doc_id, MIN(q.ts) AS pierwsze FROM requests_log q "
                "JOIN raw_versions v ON v.content_sha256 = q.sha256 "
                "WHERE q.run_id = ? AND (SELECT COUNT(DISTINCT v2.doc_id) FROM raw_versions v2 "
                "WHERE v2.content_sha256 = q.sha256) = 1 "
                "GROUP BY v.doc_id ORDER BY pierwsze",
                (run_id,),
            ).fetchall()
            for position, wiersz in enumerate(wiersze, start=1):
                self.link_run_document(run_id, str(wiersz["doc_id"]), position=position, nowy=True)

    @classmethod
    def open(cls, path: Path | str, *, clock: Clock) -> Store:
        return cls(path, clock=clock)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transakcja(self) -> Iterator[None]:
        """`BEGIN IMMEDIATE` … `COMMIT`; wyjątek w środku cofa wszystko, co weszło po `BEGIN`.

        Surowy `sqlite3.Error` z wnętrza transakcji (metoda podstawiona w teście, sterownik
        wołany obok `_Polaczenie`) wychodzi stąd jako `StoreError` — po `ROLLBACK`, z tym samym
        zdaniem, co przy każdym innym błędzie bazy.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except sqlite3.Error as blad:
            self._conn.wycofaj()
            raise blad_bazy(self._path, blad) from blad
        except BaseException:
            self._conn.wycofaj()
            raise
        self._conn.execute("COMMIT")

    # ------------------------------------------------------------------------ dokumenty

    def has_document(self, doc_id: str) -> bool:
        wiersz = self._conn.execute(
            "SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return wiersz is not None

    def upsert_document(
        self,
        *,
        doc_id: str,
        source: str,
        source_ref: str,
        sygnatury: Sequence[str],
        data_wydania: str | None,
        seen_at: str,
        content_sha256: str,
    ) -> None:
        """Nowy dokument dostaje `first_seen_at`; znany — tylko `last_seen_at` i bieżącą wersję."""
        self._conn.execute(
            "INSERT INTO documents (doc_id, source, source_ref, sygnatury, data_wydania, "
            "first_seen_at, last_seen_at, current_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET last_seen_at = excluded.last_seen_at, "
            "current_sha256 = excluded.current_sha256, sygnatury = excluded.sygnatury, "
            "data_wydania = excluded.data_wydania",
            (
                doc_id,
                source,
                source_ref,
                json.dumps(list(sygnatury), ensure_ascii=False),
                data_wydania,
                seen_at,
                seen_at,
                content_sha256,
            ),
        )

    def add_raw_version(
        self,
        *,
        doc_id: str,
        content: bytes,
        fetched_at: str,
        fetch_meta: Mapping[str, object],
        expected_sha256: str | None = None,
    ) -> tuple[str, bool]:
        """Zapisuje wersję treści; zwraca `(sha256, czy_nowa)`.

        Ta sama treść drugi raz daje `(sha, False)` i **zero** nowych wierszy — `INSERT OR IGNORE`
        na kluczu `(doc_id, content_sha256)` jest całą treścią bramki fazy 1 po stronie magazynu
        (ADR-0001 2.3). Inna treść daje drugą wersję, nigdy nadpisanie.
        """
        sha = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None and expected_sha256 != sha:
            raise StoreError(
                f"Skrót podany przez kanał ({expected_sha256[:12]}…) nie zgadza się ze skrótem "
                f"bajtów do zapisu ({sha[:12]}…) dla {doc_id!r}. Łańcuch dowodowy pęka przy "
                "pierwszym zapisie — nie zapisuję."
            )
        kursor = self._conn.execute(
            "INSERT OR IGNORE INTO raw_versions (doc_id, content_sha256, fetched_at, "
            "content_bytes, fetch_meta) VALUES (?, ?, ?, ?, ?)",
            # `fetch_meta` przez `mask_tokens`: nagłówki odpowiedzi bywają echem nagłówków
            # żądania, a przy Atlasie żądanie niesie `X-Api-Key`.
            (
                doc_id,
                sha,
                fetched_at,
                content,
                mask_tokens(json.dumps(dict(fetch_meta), ensure_ascii=False)),
            ),
        )
        return sha, kursor.rowcount == 1

    def iter_documents(
        self, filtr: Filtr | None = None, *, run_id: str | None = None
    ) -> Iterator[Dokument]:
        """Dokumenty z bieżącą wersją: cały korpus, po filtrze albo objęte jednym przebiegiem.

        Kolejność jest stała (data wydania, potem `doc_id`; dla przebiegu — kolejność
        kandydatów), bo eksport ma być powtarzalny co do wiersza.
        """
        gdzie, argumenty = _warunki(filtr or Filtr())
        zlaczenie = ""
        porzadek = "ORDER BY d.data_wydania, d.doc_id"
        if run_id is not None:
            zlaczenie = "JOIN run_documents rd ON rd.doc_id = d.doc_id AND rd.run_id = ?"
            argumenty = [run_id, *argumenty]
            porzadek = "ORDER BY rd.position"
        kursor = self._conn.execute(
            "SELECT d.doc_id, d.source, d.source_ref, d.sygnatury, d.data_wydania, "
            "d.current_sha256, v.fetched_at, v.content_bytes FROM documents d "
            "JOIN raw_versions v ON v.doc_id = d.doc_id AND v.content_sha256 = d.current_sha256 "
            "LEFT JOIN metadata m ON m.doc_id = d.doc_id AND m.content_sha256 = d.current_sha256 "
            f"{zlaczenie} {gdzie} {porzadek}",
            argumenty,
        )
        for w in kursor:
            yield Dokument(
                doc_id=str(w["doc_id"]),
                source=str(w["source"]),
                source_ref=str(w["source_ref"]),
                sygnatury=tuple(json.loads(str(w["sygnatury"]))),
                data_wydania=None if w["data_wydania"] is None else str(w["data_wydania"]),
                current_sha256=str(w["current_sha256"]),
                fetched_at=str(w["fetched_at"]),
                content_bytes=bytes(w["content_bytes"]),
            )

    def count_documents(self, filtr: Filtr | None = None) -> int:
        gdzie, argumenty = _warunki(filtr or Filtr())
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM documents d LEFT JOIN metadata m ON m.doc_id = d.doc_id "
                f"AND m.content_sha256 = d.current_sha256 {gdzie}",
                argumenty,
            ).fetchone()[0]
        )

    # ------------------------------------------------------------- metadane i indeks

    def index_document(
        self,
        doc_id: str,
        content_sha256: str,
        metryka: Metryka,
        struktura: Struktura | None,
    ) -> None:
        """Metadane wersji i wiersz FTS bieżącej wersji — poprzedni wiersz FTS dokumentu znika.

        `struktura` jest wymagana, choć może być `None`: wołający, który ją pominie, zapisywał
        metadane z `parse_version` 2 bez sekcji, a `przelicz` bez `--wszystko` nie wracał już do
        takiego dokumentu (przegląd kodu 2026-09-19). `None` wolno podać świadomie — w testach
        magazynu, które struktury nie dotyczą.

        `metadata` jest przypięte do wersji (klucz z `content_sha256`), więc dwie wersje mają
        dwa wiersze; `fts` niesie wyłącznie bieżącą (architektura 4.4), więc stary wiersz jest
        usuwany, nie dokładany — inaczej sprostowanie trafiałoby dwa razy.
        """
        self._conn.execute(
            "INSERT INTO metadata (doc_id, content_sha256, parse_version, sygnatura_glowna, "
            "data_wydania, data_rozprawy, rodzaj, rozstrzygniecie, rozstrzygniecie_surowe, "
            "przewodniczacy, odwolujacy, zamawiajacy, przepisy, koszty, url_zrodla, "
            "dlugosc_tresci) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(doc_id, content_sha256) DO UPDATE SET "
            "parse_version = excluded.parse_version, "
            "sygnatura_glowna = excluded.sygnatura_glowna, data_wydania = excluded.data_wydania, "
            "data_rozprawy = excluded.data_rozprawy, rodzaj = excluded.rodzaj, "
            "rozstrzygniecie = excluded.rozstrzygniecie, "
            "rozstrzygniecie_surowe = excluded.rozstrzygniecie_surowe, "
            "przewodniczacy = excluded.przewodniczacy, odwolujacy = excluded.odwolujacy, "
            "zamawiajacy = excluded.zamawiajacy, przepisy = excluded.przepisy, "
            "koszty = excluded.koszty, url_zrodla = excluded.url_zrodla, "
            "dlugosc_tresci = excluded.dlugosc_tresci",
            (
                doc_id,
                content_sha256,
                metryka.parse_version,
                metryka.sygnatura_glowna,
                metryka.data_wydania,
                metryka.data_rozprawy,
                metryka.rodzaj,
                metryka.rozstrzygniecie,
                metryka.rozstrzygniecie_surowe,
                metryka.przewodniczacy,
                metryka.odwolujacy,
                metryka.zamawiajacy,
                json.dumps(list(metryka.przepisy), ensure_ascii=False),
                metryka.koszty,
                metryka.url_zrodla,
                len(metryka.tresc),
            ),
        )
        self._conn.execute("DELETE FROM fts WHERE doc_id = ?", (doc_id,))
        self._conn.execute(
            "INSERT INTO fts (doc_id, sygnatury, tresc) VALUES (?, ?, ?)",
            (doc_id, " ".join(metryka.sygnatury), metryka.tresc),
        )
        if struktura is not None:
            self._zapisz_strukture(doc_id, content_sha256, metryka.parse_version, struktura)

    def _zapisz_strukture(
        self, doc_id: str, content_sha256: str, parse_version: int, struktura: Struktura
    ) -> None:
        """Struktura wersji **zastępuje** poprzednią tej samej wersji — przeliczenie nie dokłada
        drugiego kompletu wierszy. W transakcji wołającego, razem z metadanymi."""
        klucz = (doc_id, content_sha256)
        for tabela in ("sections", "citations", "provisions"):
            self._conn.execute(
                f"DELETE FROM {tabela} WHERE doc_id = ? AND content_sha256 = ?", klucz
            )
        self._conn.executemany(
            "INSERT INTO sections (doc_id, content_sha256, parse_version, porzadek, rodzaj, "
            "char_start, char_end, sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (*klucz, parse_version, w.porzadek, w.rodzaj, w.start, w.koniec, w.sha256)
                for w in struktura.sekcje
            ],
        )
        self._conn.executemany(
            "INSERT INTO citations (doc_id, content_sha256, parse_version, porzadek, zrodlo, "
            "rodzaj, sygnatura, surowy, char_start, char_end) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    *klucz,
                    parse_version,
                    w.porzadek,
                    w.zrodlo,
                    w.rodzaj,
                    w.sygnatura,
                    w.surowy,
                    w.start,
                    w.koniec,
                )
                for w in struktura.cytowania
            ],
        )
        self._conn.executemany(
            "INSERT INTO provisions (doc_id, content_sha256, parse_version, porzadek, zrodlo, "
            "postac, akt, surowy, char_start, char_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    *klucz,
                    parse_version,
                    w.porzadek,
                    w.zrodlo,
                    w.postac,
                    w.akt,
                    w.surowy,
                    w.start,
                    w.koniec,
                )
                for w in struktura.przepisy
            ],
        )

    def versions_to_index(self, parse_version: int | None) -> Iterator[Dokument]:
        """Bieżące wersje bez metadanych albo z `parse_version` starszym niż podany.

        `None` znaczy „wszystkie" — `przelicz --wszystko` po zmianie, której numer wersji nie
        objął. Iteracja jest nad kursorem, a zapisy `index_document` idą w tym samym połączeniu:
        SQLite pozwala na to, dopóki zapis nie dotyka tabel czytanych przez kursor bez
        zmaterializowania — dlatego wynik jest tu **zmaterializowany** przed `yield`.
        """
        warunek = "" if parse_version is None else "WHERE m.doc_id IS NULL OR m.parse_version < ?"
        argumenty: list[object] = [] if parse_version is None else [parse_version]
        wiersze = self._conn.execute(
            "SELECT d.doc_id, d.source, d.source_ref, d.sygnatury, d.data_wydania, "
            "d.current_sha256, v.fetched_at, v.content_bytes FROM documents d "
            "JOIN raw_versions v ON v.doc_id = d.doc_id AND v.content_sha256 = d.current_sha256 "
            "LEFT JOIN metadata m ON m.doc_id = d.doc_id AND m.content_sha256 = d.current_sha256 "
            f"{warunek} ORDER BY d.doc_id",
            argumenty,
        ).fetchall()
        for w in wiersze:
            yield Dokument(
                doc_id=str(w["doc_id"]),
                source=str(w["source"]),
                source_ref=str(w["source_ref"]),
                sygnatury=tuple(json.loads(str(w["sygnatury"]))),
                data_wydania=None if w["data_wydania"] is None else str(w["data_wydania"]),
                current_sha256=str(w["current_sha256"]),
                fetched_at=str(w["fetched_at"]),
                content_bytes=bytes(w["content_bytes"]),
            )

    def count_indexed(self) -> int:
        """Dokumenty, których **bieżąca** wersja ma metadane — a nie wierszy `metadata` w ogóle."""
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM documents d JOIN metadata m ON m.doc_id = d.doc_id "
                "AND m.content_sha256 = d.current_sha256"
            ).fetchone()[0]
        )

    def szukaj(
        self, fraza: str, filtr: Filtr | None = None, *, limit: int = DOMYSLNY_LIMIT_TRAFIEN
    ) -> Wyszukanie:
        """Wyszukiwanie dosłowne frazy w FTS5 z filtrami — zawsze z liczbami (mina 2).

        Fraza idzie do FTS5 jako **jeden cytat** (słowa obok siebie, w tej kolejności), nie jako
        koniunkcja słów: „odrzucenie oferty" ma znaleźć to wyrażenie, a nie każdy dokument, w którym
        oba słowa padły na różnych stronach. Cudzysłów w frazie jest podwajany, więc żaden znak
        z wejścia nie jest operatorem zapytania FTS5.
        """
        if limit < 1:
            raise StoreError(f"Limit trafień ma być dodatni, a jest {limit}.")
        filtr = replace(filtr or Filtr(), fraza=fraza)
        gdzie, argumenty = _warunki(filtr, fraza_osobno=True)
        zapytanie = _fraza_fts(fraza)
        laczenie = (
            "FROM fts JOIN documents d ON d.doc_id = fts.doc_id "
            "LEFT JOIN metadata m ON m.doc_id = d.doc_id AND m.content_sha256 = d.current_sha256 "
            f"WHERE fts MATCH ? {gdzie.replace('WHERE', 'AND', 1)}"
        )
        trafien = int(
            self._conn.execute(f"SELECT COUNT(*) {laczenie}", [zapytanie, *argumenty]).fetchone()[0]
        )
        wiersze = self._conn.execute(
            "SELECT d.doc_id, d.source, d.source_ref, d.sygnatury, d.data_wydania, "
            f"m.rozstrzygniecie, snippet(fts, {KOLUMNA_FTS_TRESCI}, '', '', '…', 16) AS fragment, "
            f"bm25(fts) AS ranga {laczenie} ORDER BY ranga, d.doc_id LIMIT ?",
            [zapytanie, *argumenty, limit],
        ).fetchall()
        trafienia = tuple(
            Trafienie(
                doc_id=str(w["doc_id"]),
                source=str(w["source"]),
                source_ref=str(w["source_ref"]),
                sygnatura=_pierwsza(str(w["sygnatury"])),
                data_wydania=None if w["data_wydania"] is None else str(w["data_wydania"]),
                rozstrzygniecie=None if w["rozstrzygniecie"] is None else str(w["rozstrzygniecie"]),
                fragment=str(w["fragment"]),
            )
            for w in wiersze
        )
        return Wyszukanie(
            trafienia=trafienia,
            w_korpusie=self.count("documents"),
            zaindeksowanych=self.count_indexed(),
            trafien=trafien,
            bez_daty_poza_filtrem=self.bez_daty_poza_filtrem(filtr),
        )

    def bez_daty_poza_filtrem(self, filtr: Filtr) -> int:
        """Ile dokumentów pasuje do wszystkiego poza datą, a daty nie ma — więc filtr dat je
        odrzucił (architektura 4.8). Zero, gdy filtr dat nie był nałożony."""
        if not filtr.ma_daty:
            return 0
        gdzie, argumenty = _warunki(replace(filtr, od=None, do=None))
        warunki = [gdzie.removeprefix("WHERE ").strip(), "d.data_wydania IS NULL"]
        return int(
            self._conn.execute(
                "SELECT COUNT(*) FROM documents d LEFT JOIN metadata m ON m.doc_id = d.doc_id "
                "AND m.content_sha256 = d.current_sha256 WHERE "
                + " AND ".join(w for w in warunki if w),
                argumenty,
            ).fetchone()[0]
        )

    # ------------------------------------------------------------------------ przebiegi

    def start_run(
        self, *, kanal: str, zakres: str, started_at: str, kryteria: str, fingerprint: str
    ) -> str:
        run_id = f"{kanal}-{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            "INSERT INTO runs (run_id, kanal, zakres, started_at, status, kryteria, fingerprint) "
            "VALUES (?, ?, ?, ?, 'w_toku', ?, ?)",
            (run_id, kanal, zakres, started_at, kryteria, fingerprint),
        )
        return run_id

    def find_run(
        self, fingerprint: str, statuses: Sequence[str], *, kanal: str | None = None
    ) -> Przebieg | None:
        """Ostatni przebieg o tym odcisku kryteriów w jednym z podanych stanów, albo `None`.

        Wznowienie dotyczy **tych samych kryteriów i tego samego kanału**: inne kryteria są innym
        przebiegiem, a punkt kontrolny z jednego nie mówi nic o stronach drugiego; odcisk nie
        niesie kanału, więc kanał idzie osobno (przegląd kodu 2026-09-18 — bez niego `find_run`
        z kanału `atlas` znajdował przebieg kanału `saos`). Filtr jest w zapytaniu (lekcja
        z `ceidg-tool`, `list_runs`).
        """
        przebiegi = self.list_runs(
            limit=1, statuses=tuple(statuses), fingerprint=fingerprint, kanal=kanal
        )
        return przebiegi[0] if przebiegi else None

    def resume_run(self, run_id: str, *, takze_blad: bool = False) -> Przebieg:
        """Przestawia przerwany albo osierocony przebieg na `w_toku` i zwraca go z punktem
        kontrolnym; `takze_blad` dopuszcza też przebieg zakończony błędem.

        `takze_blad` jest dla wznowienia **jawnego** (`wznow --run-id`): po wygasłym kluczu albo
        odmowie serwisu stan ustępuje, a punkt kontrolny jest wart tyle stron listy, ile trzeba
        by wysłać od nowa. Wznowienie automatyczne w `pobierz` go nie dostaje, żeby złamany
        kontrakt nie wracał sam przy każdym uruchomieniu (przegląd kodu 2026-09-18).

        Osierocony to `w_toku` bez procesu, który by go kończył: zanik zasilania, `taskkill /F`,
        dysk pełny na tyle, że `finish_run` w `finally` też nie przeszedł (tester 2026-09-18).
        `finish_run` nie dostał wtedy sterowania, więc status mówi „pracuję" o przebiegu, który
        nie pracuje — a punkt kontrolny w `ostatnia_strona` jest prawdziwy i wart tyle, ile stron
        listy trzeba by wysłać od nowa. Jeden operator i jeden proces (nagłówek modułu) rozstrzyga,
        że `w_toku` przy wznawianiu znaczy „osierocony", nie „inny proces pracuje".
        """
        przebieg = self.get_run(run_id)
        dozwolone = (*STATUSY_WZNAWIALNE, "blad") if takze_blad else STATUSY_WZNAWIALNE
        if przebieg.status not in dozwolone:
            raise StoreError(
                f"Przebieg {run_id} ma status {przebieg.status!r}; wznowić da się wyłącznie "
                "przebieg przerwany albo osierocony (pracujący bez procesu)."
            )
        self._conn.execute(
            "UPDATE runs SET status = 'w_toku', finished_at = NULL, powod = NULL WHERE run_id = ?",
            (run_id,),
        )
        return self.get_run(run_id)

    def checkpoint(self, run_id: str, strona: int) -> None:
        self._conn.execute("UPDATE runs SET ostatnia_strona = ? WHERE run_id = ?", (strona, run_id))

    def finish_run(
        self, run_id: str, *, status: str, finished_at: str, powod: str | None = None
    ) -> None:
        if status not in STATUSY_PRZEBIEGU or status == "w_toku":
            raise StoreError(f"Nieznany status końcowy przebiegu: {status!r}")
        self._conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, powod = ? WHERE run_id = ?",
            (status, finished_at, powod, run_id),
        )

    def link_run_document(self, run_id: str, doc_id: str, *, position: int, nowy: bool) -> None:
        """Wiąże kandydata z przebiegiem — nowego i pominiętego tak samo.

        `INSERT OR IGNORE`: wznowiony przebieg listuje ostatnią stronę od nowa, więc kandydat
        zapisany przed przerwaniem wraca jako pominięty — a jego pierwszy wiersz (`nowy = 1`)
        ma zostać, bo to on mówi prawdę o tym, co ten przebieg pobrał.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO run_documents (run_id, doc_id, position, nowy) "
            "VALUES (?, ?, ?, ?)",
            (run_id, doc_id, position, 1 if nowy else 0),
        )

    def iter_run_documents(self, run_id: str) -> Iterator[str]:
        for w in self._conn.execute(
            "SELECT doc_id FROM run_documents WHERE run_id = ? ORDER BY position", (run_id,)
        ):
            yield str(w["doc_id"])

    def count_run_documents(self, run_id: str, *, nowe: bool | None = None) -> int:
        warunek = "" if nowe is None else f" AND nowy = {1 if nowe else 0}"
        return int(
            self._conn.execute(
                f"SELECT COUNT(*) FROM run_documents WHERE run_id = ?{warunek}", (run_id,)
            ).fetchone()[0]
        )

    def count_requests(self, run_id: str, *, ponowienia: bool = False) -> int:
        """Żądania przebiegu z dziennika; `ponowienia=True` liczy wyłącznie próby od drugiej."""
        warunek = " AND proba > 1" if ponowienia else ""
        return int(
            self._conn.execute(
                f"SELECT COUNT(*) FROM requests_log WHERE run_id = ?{warunek}", (run_id,)
            ).fetchone()[0]
        )

    _SELECT_RUN = (
        "SELECT r.*, (SELECT COUNT(*) FROM run_documents rd WHERE rd.run_id = r.run_id) "
        "AS dokumentow, (SELECT COUNT(*) FROM requests_log q WHERE q.run_id = r.run_id) AS zadan "
        "FROM runs r"
    )

    def get_run(self, run_id: str) -> Przebieg:
        wiersz = self._conn.execute(f"{self._SELECT_RUN} WHERE r.run_id = ?", (run_id,)).fetchone()
        if wiersz is None:
            raise RunNotFoundError(
                f"Nie ma przebiegu `{run_id}`. Listę identyfikatorów wypisuje `runy`."
            )
        return _przebieg(wiersz)

    def list_runs(
        self,
        limit: int = 20,
        *,
        statuses: Sequence[str] | None = None,
        fingerprint: str | None = None,
        kanal: str | None = None,
    ) -> list[Przebieg]:
        """Ostatnie przebiegi, filtrowane **w zapytaniu**, nie po jego wyniku.

        Filtr nałożony w Pythonie na wynik `LIMIT 20` znaczy „przejrzyj dwadzieścia ostatnich
        i zostaw pasujące", a nie „pokaż ostatnie pasujące". W `ceidg-tool` (`store.py:573`)
        przy dwudziestu nowszych zakończonych pobraniach `wznow` meldował, że nie ma czego
        wznawiać, choć przerwany run stał na pozycji dwudziestej pierwszej.
        """
        if limit < 1:
            # Jak w `szukaj`: ujemny `LIMIT` znaczy w SQLite „wszystko", więc `runy --limit -1`
            # pokazywało całość, a `--limit 0` pustą tabelę (tester 2026-09-18).
            raise StoreError(f"Limit wierszy ma być dodatni, a jest {limit}.")
        if statuses is not None and not statuses:
            return []
        warunki: list[str] = []
        argumenty: list[object] = []
        if statuses is not None:
            warunki.append("r.status IN ({})".format(",".join("?" for _ in statuses)))
            argumenty.extend(statuses)
        if fingerprint is not None:
            warunki.append("r.fingerprint = ?")
            argumenty.append(fingerprint)
        if kanal is not None:
            warunki.append("r.kanal = ?")
            argumenty.append(kanal)
        gdzie = (" WHERE " + " AND ".join(warunki)) if warunki else ""
        wiersze = self._conn.execute(
            f"{self._SELECT_RUN}{gdzie} ORDER BY r.started_at DESC, r.rowid DESC LIMIT ?",
            (*argumenty, limit),
        ).fetchall()
        return [_przebieg(w) for w in wiersze]

    def count_runs(self) -> int:
        """Ile przebiegów jest w bazie **naprawdę**, bez okna `LIMIT`."""
        return self.count("runs")

    # ------------------------------------------------------------------ dziennik żądań

    def log_request(
        self,
        run_id: str,
        *,
        ts: str,
        metoda: str,
        url: str,
        status: int | None,
        ms: int,
        bajtow: int,
        sha256: str | None,
        ksztalt: str,
        retry_after_s: float | None = None,
        proba: int = 1,
    ) -> None:
        """Jeden wiersz na żądanie, trwały natychmiast — poza `transakcja()` zapis jest atomowy sam."""  # noqa: E501
        self._conn.execute(
            "INSERT INTO requests_log (run_id, ts, metoda, url_redacted, status, ms, bajtow, "
            "sha256, ksztalt, retry_after_s, proba) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                ts,
                metoda,
                mask_tokens(url),
                status,
                ms,
                bajtow,
                sha256,
                ksztalt,
                retry_after_s,
                proba,
            ),
        )

    def request_stamps(self, kanal: str, since_epoch: float) -> list[RequestStamp]:
        """Historia żądań kanału jako znaczniki limitera — grzeczność ma przeżyć proces.

        `RateLimiter` widzi tylko żądania z historii; wznowienie z pustą pamięcią procesu
        zaczynałoby od serii bez odstępu i bez blokady po 429, choć dziennik obie rzeczy pamięta.
        """
        # Odcięcie po `ts` w zapytaniu, nie po wczytaniu całej historii kanału (przegląd kodu
        # 2026-09-18) — `ts` jest ISO-8601 UTC o stałym układzie, więc porównanie leksykograficzne
        # jest porównaniem czasu, a `requests_log_ts_idx` ma wreszcie czytelnika. Filtr w Pythonie
        # niżej zostaje jako zabezpieczenie przed znacznikiem w innej postaci.
        wiersze = self._conn.execute(
            "SELECT r.ts, r.url_redacted, r.status, r.retry_after_s FROM requests_log r "
            "JOIN runs p USING (run_id) WHERE p.kanal = ? AND r.ts >= ? ORDER BY r.ts",
            (kanal, utc_iso(since_epoch)),
        ).fetchall()
        znaczniki = [
            RequestStamp(
                _epoch(str(w["ts"])),
                str(w["url_redacted"]),
                w["status"],
                None if w["retry_after_s"] is None else float(w["retry_after_s"]),
            )
            for w in wiersze
        ]
        return [z for z in znaczniki if z.ts_epoch >= since_epoch]

    def struktury(self) -> Iterator[StrukturaDokumentu]:
        """Struktura bieżącej wersji każdego dokumentu korpusu — także bez metadanych i sekcji.

        Dokument bez wiersza w `metadata` albo bez sekcji **nie wypada**: wraca z pustymi
        krotkami i `parse_version = None`, bo raport pokrycia ma go policzyć jako brak, nie
        pominąć (doktryna 7.2). Zmaterializowane przed `yield`, jak `versions_to_index`.
        """
        dokumenty = self._conn.execute(
            "SELECT d.doc_id, d.current_sha256, m.sygnatura_glowna, d.data_wydania, "
            "m.parse_version FROM documents d LEFT JOIN metadata m "
            "ON m.doc_id = d.doc_id AND m.content_sha256 = d.current_sha256 ORDER BY d.doc_id"
        ).fetchall()
        sekcje = self._pogrupuj(
            "SELECT doc_id, content_sha256, porzadek, rodzaj, char_start, char_end, sha256 "
            "FROM sections ORDER BY doc_id, porzadek",
            lambda w: WierszSekcji(
                int(w["porzadek"]),
                str(w["rodzaj"]),
                int(w["char_start"]),
                int(w["char_end"]),
                str(w["sha256"]),
            ),
        )
        cytowania = self._pogrupuj(
            "SELECT * FROM citations ORDER BY doc_id, zrodlo, porzadek",
            lambda w: WierszCytowania(
                int(w["porzadek"]),
                str(w["zrodlo"]),
                str(w["rodzaj"]),
                None if w["sygnatura"] is None else str(w["sygnatura"]),
                str(w["surowy"]),
                w["char_start"],
                w["char_end"],
            ),
        )
        przepisy = self._pogrupuj(
            "SELECT * FROM provisions ORDER BY doc_id, zrodlo, porzadek",
            lambda w: WierszPrzepisu(
                int(w["porzadek"]),
                str(w["zrodlo"]),
                str(w["postac"]),
                str(w["akt"]),
                str(w["surowy"]),
                w["char_start"],
                w["char_end"],
            ),
        )
        for d in dokumenty:
            klucz = (str(d["doc_id"]), str(d["current_sha256"]))
            yield StrukturaDokumentu(
                doc_id=klucz[0],
                content_sha256=klucz[1],
                sygnatura_glowna=d["sygnatura_glowna"],
                data_wydania=d["data_wydania"],
                parse_version=d["parse_version"],
                sekcje=tuple(sekcje.get(klucz, ())),
                cytowania=tuple(cytowania.get(klucz, ())),
                przepisy=tuple(przepisy.get(klucz, ())),
            )

    def _pogrupuj(
        self, sql: str, wiersz: Callable[[sqlite3.Row], _W]
    ) -> dict[tuple[str, str], list[_W]]:
        wynik: dict[tuple[str, str], list[_W]] = {}
        for w in self._conn.execute(sql).fetchall():
            wynik.setdefault((str(w["doc_id"]), str(w["content_sha256"])), []).append(wiersz(w))
        return wynik

    def count(self, tabela: str) -> int:
        if tabela not in TABELE:
            raise StoreError(f"Nieznana tabela {tabela!r}; znane: {sorted(TABELE)}")
        return int(self._conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])


def _przebieg(wiersz: sqlite3.Row) -> Przebieg:
    return Przebieg(
        run_id=str(wiersz["run_id"]),
        kanal=str(wiersz["kanal"]),
        zakres=str(wiersz["zakres"]),
        started_at=str(wiersz["started_at"]),
        finished_at=None if wiersz["finished_at"] is None else str(wiersz["finished_at"]),
        status=str(wiersz["status"]),
        ostatnia_strona=None
        if wiersz["ostatnia_strona"] is None
        else int(wiersz["ostatnia_strona"]),
        powod=None if wiersz["powod"] is None else str(wiersz["powod"]),
        kryteria=None if wiersz["kryteria"] is None else str(wiersz["kryteria"]),
        fingerprint=None if wiersz["fingerprint"] is None else str(wiersz["fingerprint"]),
        dokumentow=int(wiersz["dokumentow"]),
        zadan=int(wiersz["zadan"]),
    )


def _kryteria_z_etykiety(zakres: str) -> Criteria | None:
    """`2024-01-01..2024-01-31` (etykieta `Scope` sprzed etapu IV) → `Criteria(od, do)`."""
    czesci = zakres.split("..")
    if len(czesci) != 2:
        return None
    try:
        return Criteria(od=date.fromisoformat(czesci[0]), do=date.fromisoformat(czesci[1]))
    except ValueError:
        return None


def _warunki(filtr: Filtr, *, fraza_osobno: bool = False) -> tuple[str, list[object]]:
    """Klauzula `WHERE` dla `documents d` z `metadata m` — parametry zawsze przez `?`."""
    warunki: list[str] = []
    argumenty: list[object] = []
    if filtr.od is not None:
        warunki.append("d.data_wydania >= ?")
        argumenty.append(filtr.od.isoformat())
    if filtr.do is not None:
        warunki.append("d.data_wydania <= ?")
        argumenty.append(filtr.do.isoformat())
    for kolumna, wartosci in (
        ("m.rozstrzygniecie", filtr.rozstrzygniecie),
        ("m.rodzaj", filtr.rodzaj),
    ):
        if wartosci:
            warunki.append("{} IN ({})".format(kolumna, ",".join("?" for _ in wartosci)))
            argumenty.extend(wartosci)
    for kolumna, wartosc in (
        ("m.przewodniczacy", filtr.przewodniczacy),
        ("m.przepisy", filtr.przepis),
    ):
        if wartosc:
            warunki.append(f"{kolumna} LIKE ? ESCAPE '\\'")
            argumenty.append(_podnapis(wartosc))
    if filtr.strona:
        warunki.append("(m.odwolujacy LIKE ? ESCAPE '\\' OR m.zamawiajacy LIKE ? ESCAPE '\\')")
        argumenty.extend([_podnapis(filtr.strona), _podnapis(filtr.strona)])
    if filtr.fraza and not fraza_osobno:
        warunki.append("d.doc_id IN (SELECT doc_id FROM fts WHERE fts MATCH ?)")
        argumenty.append(_fraza_fts(filtr.fraza))
    return ("WHERE " + " AND ".join(warunki)) if warunki else "", argumenty


def _podnapis(wartosc: str) -> str:
    """Wzorzec `LIKE` na podnapis z neutralizacją `%`, `_` i `\\` z wejścia operatora."""
    zneutralizowany = wartosc.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{zneutralizowany}%"


def _fraza_fts(fraza: str) -> str:
    """Fraza jako jeden cytat FTS5: cudzysłów podwojony, zero operatorów z wejścia."""
    return '"' + fraza.replace('"', '""') + '"'


def _pierwsza(sygnatury_json: str) -> str | None:
    sygnatury = json.loads(sygnatury_json)
    return str(sygnatury[0]) if sygnatury else None


def _epoch(ts: str) -> float:
    """`2026-09-18T10:35:25Z` (postać z `clock.utc_iso`) na sekundy epoch."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
