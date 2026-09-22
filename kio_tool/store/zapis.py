"""Zapis korpusu: dokument, wersja surowa, metadane, indeks i struktura (ADR-0009 Z-1)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from ..config import mask_tokens
from ..errors import StoreError
from .model import (
    Metryka,
    Struktura,
)
from .polaczenie import _Rdzen


class _ZapisKorpusu(_Rdzen):
    """Zapis dokumentów, wersji, metadanych, indeksu i struktury."""

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
