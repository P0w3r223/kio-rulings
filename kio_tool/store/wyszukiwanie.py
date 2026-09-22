"""Odczyt korpusu: przegląd dokumentów, wyszukiwanie pełnotekstowe, struktura (ADR-0009 Z-1)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import TypeVar

from ..errors import StoreError
from .model import (
    Dokument,
    Filtr,
    StrukturaDokumentu,
    Trafienie,
    WierszCytowania,
    WierszPrzepisu,
    WierszSekcji,
    Wyszukanie,
)
from .polaczenie import _Rdzen

_W = TypeVar("_W")
DOMYSLNY_LIMIT_TRAFIEN = 20
KOLUMNA_FTS_TRESCI = 2
"""Indeks kolumny `tresc` w `fts` dla `snippet()` — kolumny liczą się od zera: `doc_id`,
`sygnatury`, `tresc`."""


class _Wyszukiwanie(_Rdzen):
    """Przegląd dokumentów, FTS, liczniki indeksu i struktury."""

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
