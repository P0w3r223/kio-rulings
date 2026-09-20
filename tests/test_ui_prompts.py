"""Pytający (`ui/prompts.py`) — bez prawdziwego terminala: zapas `input()` i skrypt testowy.

Ścieżka `questionary` wymaga TTY i nie jest tu uruchamiana; jej jedynym zobowiązaniem, które da
się sprawdzić bez terminala, jest neutralizacja napisów — tę trzyma skan reguły 10 w
`test_boundaries.py`. Tu mierzone jest to, co widzi operator bez TTY, i to, że Enter przy
pytaniu o zgodę znaczy „nie".
"""

from __future__ import annotations

import pytest

from kio_tool.ui import texts
from kio_tool.ui.prompts import (
    NIE,
    TAK,
    KonsolaPrompter,
    SkryptowyPrompter,
    WyczerpaneOdpowiedziError,
    _styl_wyboru,
    opcje_do_wyboru,
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


def test_bez_terminala_wybor_po_numerze_z_domyslna_na_czele() -> None:
    """Numer 1 to odpowiedź domyślna — ta sama kolejność co na liście ze strzałkami.

    Lista awaryjna, która numeruje opcje inaczej niż ta narysowana przez `questionary`,
    uczy operatora złego odruchu przy dwóch wywołaniach tego samego pytania."""
    prompter, wypisane = _konsola("1")

    assert prompter.zapytaj(MENU) == "wyjdz", "domyślna `wyjdz` stoi na pozycji pierwszej"
    assert "1. Wyjdź" in wypisane[0] and "2. Pobierz" in wypisane[0]


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


# --- poprawki po zgłoszeniu operatora (2026-09-20) --------------------------------------------


def test_domyslna_stoi_na_czele_listy_wyboru() -> None:
    """Kursor `questionary` startuje na pozycji pierwszej, bo nie podajemy `default=`.

    `default=` trafiało do `selected_options`, a klasa `selected` wygrywa przy rysowaniu
    z `pointed_at`: wiersz domyślny zostawał oznaczony na stałe, więc zaznaczenie chodziło
    strzałkami, a podświetlenie stało w miejscu. Żeby kursor zaczynał na domyślnej, to ona
    musi być pierwsza — i tym jest ta funkcja.
    """
    assert [o.klucz for o in opcje_do_wyboru(MENU)] == ["wyjdz", "pobierz"]

    bez_domyslnej = Pytanie(tresc="?", opcje=MENU.opcje)
    assert opcje_do_wyboru(bez_domyslnej) == MENU.opcje, "brak domyślnej nie zmienia kolejności"


def test_lista_wyboru_dostaje_jawny_styl_podswietlenia() -> None:
    """`reverse` zamiast koloru — domyślny motyw nie rysował podświetlenia na tej konsoli."""
    klasy = dict(_styl_wyboru().style_rules)

    assert klasy["pointer"] == "reverse bold"
    assert klasy["highlighted"] == "reverse bold"
    assert "selected" not in klasy, (
        "klasa `selected` przywróciłaby defekt dwóch zaznaczeń, gdyby `default=` wróciło"
    )


def test_pytanie_tak_nie_niesie_klamre_z_domyslna_wielka_litera() -> None:
    prompter, wypisane = _konsola("")

    assert prompter.zapytaj(ZGODA) == NIE
    assert "[t/N]" in wypisane[0], "operator ma widzieć, co wolno wpisać i co znaczy Enter"

    prompter, wypisane = _konsola("")
    prompter.zapytaj(Pytanie(tresc="Pobrać?", rodzaj="tak_nie", domyslna=TAK))
    assert "[T/n]" in wypisane[0]


def test_odpowiedz_nierozpoznana_pyta_jeszcze_raz_zanim_padnie_domyslna() -> None:
    """„jasne" to zgoda, której nie wolno po cichu zamienić w odmowę — pytamy raz.

    Przy `questionary.confirm` nie było tej szansy: wiąże na sztywno `y` i `n`, a polskie
    „tak" pomijał po cichu i odpowiadał wartością domyślną (zgłoszenie operatora).
    """
    prompter, wypisane = _konsola("jasne", "tak")
    assert prompter.zapytaj(ZGODA) == TAK
    assert texts.NIE_ROZUMIEM_TAK_NIE in wypisane[1]

    prompter, _ = _konsola("jasne", "bzdura")
    assert prompter.zapytaj(ZGODA) == NIE, "po dopytaniu obowiązuje kierunek bezpieczny"


def test_nie_rozpoznawane_po_polsku_i_angielsku() -> None:
    for odpowiedz in ("n", "Nie", "no", "NO"):
        prompter, _ = _konsola(odpowiedz)
        assert prompter.zapytaj(Pytanie(tresc="?", rodzaj="tak_nie", domyslna=TAK)) == NIE


def test_odmowa_nie_jest_czytana_po_pierwszej_literze() -> None:
    """„to nie" zaczyna się od „t" — przedrostek zamieniłby odmowę w zgodę."""
    prompter, _ = _konsola("to nie", "nie")

    assert prompter.zapytaj(ZGODA) == NIE
