"""Schemat bazy: wersja, znacznik bazy pokazowej, lista tabel i DDL (ADR-0009 Z-1).

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
(skuteczność ponowień) nie dałoby się zrobić bez ponownego obciążenia serwisu."""

from __future__ import annotations

SCHEMA_VERSION = 6
ID_BAZY_POKAZOWEJ = 0x4B494F44
"""`PRAGMA application_id` bazy trybu pokazowego („KIOD") — znacznik w samym pliku (ADR-0008 Z-2).

Jedzie z plikiem przy kopiowaniu i zmianie nazwy, więc `--baza` wskazujące plik pokazowy nie
otworzy go po cichu w trybie produkcyjnym (wtedy `pobierz` dopisywałby prawdziwe orzeczenia do
fikcyjnych), a `kio-tool demo` nie zacznie pisać fikcji do niepustej bazy operatora."""
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
