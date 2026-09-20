"""Generator `kio_tool/demo/wzorce.yaml` z bazy operatora — 0 żądań (ADR-0008 Z-11).

Korpus pokazowy nie ma prawa pisać danych odniesienia z pamięci (mina 4): etykieta przepisu
wymyślona albo przepisana ze streszczenia przechodzi każdy test i cicho uczy fałszu. Ten skrypt
czyta bazę operatora i zapisuje **wyłącznie** trzy rodzaje liczb i napisów z białej listy:

- rozkład `rozstrzygniecie` i `rodzaj` (wartości zamkniętej listy kanału),
- najczęstsze etykiety przepisów z listy kanału (`law_articles`) z liczbą wystąpień,
- liczbę dokumentów nazywających każdą z dwóch ustaw Pzp pełnym tytułem.

Żadnego pola osobowego: bez przewodniczących, stron, sygnatur i treści. Nagłówek niesie datę,
liczbę dokumentów i SHA-256 listy `doc_id:content_sha256` wejścia — odświeżenie wzorców to nowe
uruchomienie i nowy skrót, nigdy ręczna poprawka. Bez bazy skrypt odmawia; wariantu zastępczego
nie ma.

    .venv\\Scripts\\python.exe scripts\\zbuduj_wzorce_demo.py [--baza ŚCIEŻKA]
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from kio_tool.clock import SystemClock
from kio_tool.config import default_db_path
from kio_tool.docid import SourceName
from kio_tool.odczyt import odczytaj
from kio_tool.parser.provisions import akt_pzp_dokumentu
from kio_tool.pipeline import mapa_pol
from kio_tool.source.contract import load_contract
from kio_tool.store import Store

CEL = Path(__file__).resolve().parent.parent / "kio_tool" / "demo" / "wzorce.yaml"
ETYKIET = 40
"""Ile najczęstszych etykiet przepisów trafia do wzorców — ogon jest szumem, nie wzorcem."""
KLUCZE = ("zrodlo", "rozstrzygniecia", "rodzaje", "etykiety_przepisow", "ustawy_pzp")
"""Biała lista kluczy pliku — test (`tests/test_demo.py`) czyta ją stąd i nic spoza niej."""


def zbuduj(baza: Path) -> dict[str, object]:
    if not baza.is_file():
        raise SystemExit(f"Nie ma bazy {baza} — wzorców nie da się zbudować bez korpusu.")
    mapa = mapa_pol(load_contract(SourceName("atlas")))
    rozstrzygniecia: Counter[str] = Counter()
    rodzaje: Counter[str] = Counter()
    etykiety: Counter[str] = Counter()
    ustawy: Counter[str] = Counter()
    wejscie: list[str] = []
    with Store.open(baza, clock=SystemClock()) as store:
        for d in store.iter_documents():
            szczegoly = odczytaj(d.content_bytes, mapa)
            if szczegoly is None:
                continue
            wejscie.append(f"{d.doc_id}:{d.current_sha256}")
            rozstrzygniecia[szczegoly.rozstrzygniecie or "brak"] += 1
            rodzaje[szczegoly.rodzaj or "brak"] += 1
            etykiety.update(szczegoly.przepisy)
            ustawy[akt_pzp_dokumentu(szczegoly.tresc)] += 1
    skrot = hashlib.sha256("\n".join(sorted(wejscie)).encode("utf-8")).hexdigest()
    return {
        "zrodlo": {
            "data": datetime.now(UTC).strftime("%Y-%m-%d"),
            "dokumentow": len(wejscie),
            "sha256_wejscia": skrot,
            "opis": "scripts/zbuduj_wzorce_demo.py nad bazą operatora, 0 żądań",
        },
        "rozstrzygniecia": dict(rozstrzygniecia.most_common()),
        "rodzaje": dict(rodzaje.most_common()),
        "etykiety_przepisow": [
            {"etykieta": e, "liczba": n} for e, n in etykiety.most_common(ETYKIET)
        ],
        "ustawy_pzp": dict(ustawy.most_common()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--baza", type=Path, default=default_db_path())
    args = parser.parse_args(argv)
    dane = zbuduj(args.baza)
    naglowek = (
        "# Wygenerowane przez scripts/zbuduj_wzorce_demo.py — NIE EDYTOWAĆ RĘCZNIE.\n"
        "# Dane odniesienia korpusu pokazowego (ADR-0008 Z-11): wyłącznie rozkłady i etykiety\n"
        "# przepisów z bazy operatora, bez pól osobowych. Odświeżenie = ponowne uruchomienie.\n"
    )
    CEL.write_text(
        naglowek + yaml.safe_dump(dane, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    sys.stdout.write(f"{CEL} — {dane['zrodlo']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
