"""Odczyt jednej wersji dokumentu: surowe bajty → metadane i struktura w wierszach magazynu.

Jedyne miejsce, w którym wyniki `parser/*` zamieniają się na wiersze `store` (`Metryka`,
`Struktura`). Parser nie zna magazynu, magazyn nie zna parsera (architektura 4.2) — przepisanie
między nimi mieszkało w `pipeline.py` i dla fazy 2 (ADR-0006 etap V) wyniosłoby tam kolejne
kilkadziesiąt linii ponad sufit 800. Ten moduł nie zna sieci ani kanału (reguła 5 zostaje przy
`pipeline`): dostaje bajty i mapę pól, a oddaje to, co `Store.index_document` przyjmuje.

`zrodlo = 'kanal'` przy przepisach to lista `law_articles` od pośrednika — zapisywana obok odczytu
z treści, nigdy zamiast niego (ADR-0006 Z-7). Cytowań od kanału nie ma: pola opracowania Atlasu
(`cites`, `cited_by`) celowo nie mają wiersza w kontrakcie.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict

from .errors import ParseError
from .parser.cite import cytowania
from .parser.details import PARSE_VERSION, MapaPol, Szczegoly, rekord_z_bajtow, wyczytaj
from .parser.provisions import przepisy_z_kanalu, przepisy_z_tresci
from .parser.sections import segmentuj
from .store import Metryka, Struktura, WierszCytowania, WierszPrzepisu, WierszSekcji


def odczytaj(content: bytes, mapa: MapaPol) -> Szczegoly | None:
    """Szczegóły wersji albo `None`, gdy bajty nie dają się odczytać — błąd liczony, nie rzucany."""
    try:
        return wyczytaj(rekord_z_bajtow(content), mapa)
    except ParseError:
        return None


def metryka(szczegoly: Szczegoly) -> Metryka:
    return Metryka(parse_version=PARSE_VERSION, **asdict(szczegoly))


def struktura(szczegoly: Szczegoly) -> Struktura:
    """Sekcje, cytowania i przepisy wersji — offsety w oryginale `szczegoly.tresc` (Z-5)."""
    tresc = szczegoly.tresc
    sekcje = segmentuj(tresc)
    return Struktura(
        sekcje=tuple(
            WierszSekcji(
                porzadek=s.porzadek,
                rodzaj=s.rodzaj,
                start=s.start,
                koniec=s.koniec,
                sha256=hashlib.sha256(tresc[s.start : s.koniec].encode("utf-8")).hexdigest(),
            )
            for s in sekcje
        ),
        cytowania=tuple(
            WierszCytowania(
                porzadek=c.porzadek,
                zrodlo="tresc",
                rodzaj=c.rodzaj,
                sygnatura=c.sygnatura,
                surowy=c.surowy,
                start=c.start,
                koniec=c.koniec,
            )
            for c in cytowania(tresc, sekcje, wlasne=szczegoly.sygnatury)
        ),
        przepisy=tuple(
            WierszPrzepisu(
                porzadek=p.porzadek,
                zrodlo=p.zrodlo,
                postac=p.postac,
                akt=p.akt,
                surowy=p.surowy,
                start=p.start,
                koniec=p.koniec,
            )
            for p in (
                *przepisy_z_tresci(tresc, sekcje),
                *przepisy_z_kanalu(szczegoly.przepisy, tresc),
            )
        ),
    )
