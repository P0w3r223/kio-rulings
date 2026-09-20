"""Obserwator `PARSE_VERSION` — zmiana parsera bez podniesienia wersji jest cicha (ADR-0006 Z-10).

`przelicz` bez `--wszystko` przelicza wyłącznie dokumenty z `parse_version` **mniejszym** niż
bieżący, więc zmiana tego, co parser wyciąga, przy tej samej liczbie nie ma czego przeliczyć:
korpus zostaje z wynikiem sprzed zmiany, a powód zmiany nie jest na nim osiągnięty. Dokładnie
to stało się między 2026-09-19 a 2026-09-20 — `docid.znajdz_sygnatury` zaczęło skracać rok
czterocyfrowy do dwucyfrowego, a `PARSE_VERSION` został na 2 (przegląd kodu fazy 3).

Strażnikiem jest odcisk **źródeł**, nie wyniku: wynik da się policzyć tylko na korpusie, a ten
leży poza repozytorium. Odcisk zapala się też przy zmianie komentarza — i to jest cena, którą
płacimy świadomie, bo alternatywą jest cisza. Reakcja na czerwony test jest jedna z dwóch:
podnieś `PARSE_VERSION` (zmiana rusza wynik odczytu) albo zaktualizuj odcisk w tym pliku,
wpisując w komentarzu, dlaczego wynik się nie zmienia.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from kio_tool.parser.details import PARSE_VERSION

PAKIET = Path(__file__).resolve().parent.parent / "kio_tool"
ZRODLA_ODCZYTU = ("parser", "docid.py", "odczyt.py")
"""Co składa się na wynik odczytu: cały pakiet `parser/` plus dwa moduły, z których `parser`
bierze postać kanoniczną sygnatury (`docid`) i które przepisują jego wynik na wiersze
magazynu (`odczyt`)."""

ODCISK = "5d99f759041d716ff505586e05bdc4e80c6dbeb2272ecdcf843fa34a92a5bbfc"
"""SHA-256 źródeł odczytu, zmierzony 2026-09-20 przy `PARSE_VERSION = 6`.

Poprzedni odcisk (`d6f03010…`, `PARSE_VERSION = 3`) zapalił się przy pomiarze 25 dokładnie tak,
jak miał: zmiana `docid` ruszyła wynik odczytu, więc wersja poszła w górę razem z odciskiem."""


def _pliki() -> list[Path]:
    pliki: list[Path] = []
    for wpis in ZRODLA_ODCZYTU:
        sciezka = PAKIET / wpis
        pliki.extend(sorted(sciezka.rglob("*.py")) if sciezka.is_dir() else [sciezka])
    return pliki


def _odcisk() -> str:
    suma = hashlib.sha256()
    for plik in _pliki():
        suma.update(plik.relative_to(PAKIET).as_posix().encode())
        suma.update(plik.read_bytes())
    return suma.hexdigest()


def test_zrodla_odczytu_maja_odcisk_zgodny_z_wersja() -> None:
    assert _odcisk() == ODCISK, (
        f"źródła odczytu zmienione przy `PARSE_VERSION = {PARSE_VERSION}`. Jeśli zmiana rusza "
        "to, co parser wyciąga — podnieś `PARSE_VERSION` i dopisz wiersz w jego docstringu. "
        "Jeśli nie rusza (komentarz, nazwa lokalna) — wpisz tu nowy odcisk razem z powodem."
    )


def test_skan_odcisku_nie_jest_pusty() -> None:
    """Pusty skan dałby odcisk stały i zielony test na zawsze."""
    pliki = _pliki()

    assert len(pliki) >= 6, [p.name for p in pliki]
    assert any(p.name == "docid.py" for p in pliki)
    assert any(p.parent.name == "parser" for p in pliki)


def test_odcisk_zmienia_sie_z_trescia(tmp_path: Path) -> None:
    """Samosprawdzenie: odcisk liczony tą samą funkcją reaguje na jeden znak."""
    a = tmp_path / "a.py"
    a.write_text("x = 1\n", encoding="utf-8")
    pierwszy = hashlib.sha256(a.read_bytes()).hexdigest()
    a.write_text("x = 2\n", encoding="utf-8")

    assert hashlib.sha256(a.read_bytes()).hexdigest() != pierwszy
