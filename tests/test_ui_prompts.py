"""Pytający (`ui/prompts.py`) — bez prawdziwego terminala: zapas `input()` i skrypt testowy.

Ścieżka `questionary` wymaga TTY i nie jest tu uruchamiana; jej jedynym zobowiązaniem, które da
się sprawdzić bez terminala, jest neutralizacja napisów — tę trzyma skan reguły 10 w
`test_boundaries.py`. Tu mierzone jest to, co widzi operator bez TTY, i to, że Enter przy
pytaniu o zgodę znaczy „nie".
"""

from __future__ import annotations

import pytest

from kio_tool.ui.prompts import (
    NIE,
    TAK,
    KonsolaPrompter,
    SkryptowyPrompter,
    WyczerpaneOdpowiedziError,
)
from kio_tool.ui.texts import Opcja, Pytanie

MENU = Pytanie(
    tresc="Co robimy?",
    opcje=(Opcja("pobierz", "Pobierz"), Opcja("wyjdz", "Wyjdź")),
    domyslna="wyjdz",
)
ZGODA = Pytanie(tresc="Pobrać 4 308 żądań?", rodzaj="tak_nie", domyslna=NIE)


def _konsola(*odpowiedzi: str) -> tuple[KonsolaPrompter, list[str]]:
    wypisane: list[str] = []
    kolejka = list(odpowiedzi)

    def wejscie(tekst: str) -> str:
        wypisane.append(tekst)
        return kolejka.pop(0)

    return KonsolaPrompter(terminal=False, wejscie=wejscie), wypisane


def test_bez_terminala_wybor_po_numerze() -> None:
    prompter, wypisane = _konsola("1")
    assert prompter.zapytaj(MENU) == "pobierz"
    assert "1. Pobierz" in wypisane[0] and "2. Wyjdź" in wypisane[0]


def test_bez_terminala_zla_odpowiedz_daje_domyslna_a_nie_pierwsza() -> None:
    prompter, _ = _konsola("xyz")
    assert prompter.zapytaj(MENU) == "wyjdz"


def test_enter_przy_zgodzie_znaczy_nie() -> None:
    """ADR-0008 §10: Enter nie ma prawa pobrać przebiegu masowego."""
    prompter, _ = _konsola("")
    assert prompter.zapytaj(ZGODA) == NIE


def test_tak_rozpoznawane_po_polsku_i_angielsku() -> None:
    for odpowiedz in ("t", "Tak", "y", "YES"):
        prompter, _ = _konsola(odpowiedz)
        assert prompter.zapytaj(ZGODA) == TAK


def test_napis_wrogi_jest_neutralizowany_przed_terminalem() -> None:
    """Etykieta z bazy z sekwencją ESC nie steruje ekranem (reguła 10, ADR-0008 Z-15)."""
    wrogie = Pytanie(tresc="Wznowić?", opcje=(Opcja("a", "przebieg \x1b[2Jatlas"),))
    prompter, wypisane = _konsola("1")
    prompter.zapytaj(wrogie)
    assert "\x1b" not in wypisane[0]


def test_skrypt_odpowiada_w_kolejnosci_i_pamieta_pytania() -> None:
    skrypt = SkryptowyPrompter(["pobierz", TAK])
    assert skrypt.zapytaj(MENU) == "pobierz"
    assert skrypt.zapytaj(ZGODA) == TAK
    assert [p.tresc for p in skrypt.zadane] == [MENU.tresc, ZGODA.tresc]


def test_skrypt_wyczerpany_albo_spoza_opcji_to_blad_glosny() -> None:
    with pytest.raises(WyczerpaneOdpowiedziError):
        SkryptowyPrompter([]).zapytaj(MENU)
    with pytest.raises(WyczerpaneOdpowiedziError, match="spoza opcji"):
        SkryptowyPrompter(["nieznana"]).zapytaj(MENU)
