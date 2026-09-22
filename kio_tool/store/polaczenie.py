"""Szew ze sterownikiem SQLite i rdzeń klasy `Store` (ADR-0009 Z-1)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from ..clock import Clock
from ..errors import ConfigError, KioError, StoreError
from .schemat import TABELE


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


class _Rdzen:
    """Wspólne dla klas cząstkowych `Store` (ADR-0009 Z-1): połączenie, ścieżka, zegar, tryb,
    transakcja i licznik tabel. Atrybuty ustawia `Store.__init__`; tu są zadeklarowane, żeby
    klasa cząstkowa nie znała ich z domysłu."""

    _conn: _Polaczenie
    _path: str
    _clock: Clock
    pokazowa: bool

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

    def count(self, tabela: str) -> int:
        if tabela not in TABELE:
            raise StoreError(f"Nieznana tabela {tabela!r}; znane: {sorted(TABELE)}")
        return int(self._conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])
