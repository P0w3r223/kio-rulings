"""Struktura wersji w magazynie (ADR-0006 etap V, schemat 6): sekcje, cytowania, przepisy.

Mierzone przez prawdziwy potok — `pobierz` na atrapie Atlasu i `przelicz` bez sieci — bo
bramka fazy 2 brzmi „przeliczenie całego korpusu bez ani jednego żądania" (reguła 20), a ta sama
struktura ma powstać z obu dróg. Materiał wymyślony, bez nazwisk (ADR-0006 Z-11).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from kio_tool import pipeline, wpisy
from kio_tool.odczyt import struktura
from kio_tool.parser.details import PARSE_VERSION, MapaPol
from kio_tool.store import SCHEMA_VERSION, Store
from tests.test_odpornosc_wspolne import (
    KONTRAKT,
    SerwisAwaryjny,
    _bez_klucza_ze_srodowiska,
    store,
    uruchom,
)
from tests.wsparcie_sondy import ZegarTestowy

__all__ = ["_bez_klucza_ze_srodowiska", "store"]

TRESC = (
    "Sygn. akt: KIO 1/24\nWYROK\nz dnia 5 stycznia 2024 r.\norzeka:\n1. oddala odwołanie.\n"
    "Stosownie do art. 579 ustawy na niniejszy wyrok przysługuje skarga.\n"
    "Uzasadnienie\nNa podstawie ustawy z dnia 11 września 2019 r. Izba zważyła, że zarzut\n"
    "naruszenia art. 226 ust. 1 pkt 5 ustawy Pzp jest chybiony (por. KIO 2/23).\n"
)


def _rekord(slug: str) -> dict[str, object]:
    return {
        "slug": slug,
        "primary_signature": "KIO 1/24",
        "signatures": ["KIO 1/24"],
        "law_articles": ["art. 226 ust. 1 pkt 5 Pzp"],
        KONTRAKT.ksztalt.dokument.pole_tresci: TRESC,
    }


def _mapa() -> MapaPol:
    return wpisy.mapa_pol(KONTRAKT)


def test_struktura_ma_sekcje_cytowania_i_przepisy_z_obu_zrodel() -> None:
    from kio_tool.odczyt import odczytaj

    szczegoly = odczytaj(json.dumps(_rekord("kio-1-24")).encode(), _mapa())
    assert szczegoly is not None
    s = struktura(szczegoly)
    assert [w.rodzaj for w in s.sekcje] == ["naglowek", "sentencja", "pouczenie", "uzasadnienie"]
    for w in s.sekcje:
        fragment = TRESC[w.start : w.koniec].encode("utf-8")
        assert w.sha256 == hashlib.sha256(fragment).hexdigest(), "Z-11: skrót fragmentu"
    assert [(c.rodzaj, c.sygnatura) for c in s.cytowania] == [("kio", "KIO 2/23")]
    assert {(p.zrodlo, p.postac, p.akt) for p in s.przepisy} >= {
        ("tresc", "art. 226 ust. 1 pkt 5", "pzp2019"),
        ("kanal", "art. 226 ust. 1 pkt 5", "pzp2019"),
    }


def test_pobierz_zapisuje_strukture_w_transakcji_dokumentu(store: Store) -> None:
    uruchom(store, SerwisAwaryjny())
    dokumenty = store.count("documents")
    assert dokumenty > 0
    wiersze = store._conn.execute("SELECT COUNT(DISTINCT doc_id) FROM sections").fetchone()[0]
    assert wiersze == dokumenty, "każdy zapisany dokument ma sekcje"
    wersje = {w[0] for w in store._conn.execute("SELECT DISTINCT parse_version FROM sections")}
    assert wersje == {PARSE_VERSION}


def test_przelicz_odtwarza_strukture_bez_dublowania(store: Store) -> None:
    """Przeliczenie zastępuje strukturę tej samej wersji, nie dokłada drugiego kompletu."""
    uruchom(store, SerwisAwaryjny())
    przed = store.count("sections"), store.count("provisions"), store.count("citations")
    store._conn.execute("DELETE FROM sections WHERE rowid IN (SELECT rowid FROM sections LIMIT 3)")

    wynik = pipeline.przelicz(store, wszystko=True)

    assert wynik.bledow == 0
    po = store.count("sections"), store.count("provisions"), store.count("citations")
    assert po == przed


def test_migracja_5_do_6_doklada_tabele_struktury(tmp_path: Path) -> None:
    """Baza schematu 5 (sprzed fazy 2) otwiera się na 6 bez utraty danych i bez struktury,
    której `przelicz` dopiero dopisze — `parse_version` 1 < 2 kwalifikuje każdą wersję."""
    sciezka = tmp_path / "korpus.sqlite"
    with Store.open(str(sciezka), clock=ZegarTestowy()):
        pass
    with sqlite3.connect(sciezka) as p:
        for tabela in ("sections", "citations", "provisions"):
            p.execute(f"DROP TABLE {tabela}")
        p.execute("PRAGMA user_version = 5")
    with Store.open(str(sciezka), clock=ZegarTestowy()) as ponownie:
        assert ponownie.count("sections") == 0
    with sqlite3.connect(sciezka) as p:
        assert p.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 6
