"""Strażnicy szwu z `rich` — reguła 10.

Plik powstał, bo test mutacyjny 2026-09-15 pokazał dziurę: odwrócenie kolejności
`mask_tokens` i `strip_control` w `safe()` **przechodziło przez całą suitę niezauważone**.
Kolejność była poprawiona, ale nic jej nie pilnowało — czyli poprawka istniała jako
przekonanie autora, nie jako własność kodu. To ta sama zasada 7.3, tylko zastosowana do
świeżej poprawki zamiast do starego założenia.
"""

from __future__ import annotations

import pytest

from kio_tool.config import register_secret
from kio_tool.richtext import make_console, safe, safe_or_none

SEKRET_TESTOWY = "klucz-testowy-0123456789"
"""Wartość jawnie sztuczna, nie pochodząca z żadnego serwisu. Długość powyżej
`MIN_REGISTERED_SECRET`, bo krótszej `register_secret` nie przyjmie."""


def test_sekret_ze_wstrzyknietym_znakiem_sterujacym_nie_wycieka_na_ekran() -> None:
    """Najpierw postać kanoniczna, potem porównanie — i to jest cała treść tego testu.

    `mask_tokens` szuka **dokładnej** wartości sekretu. Jeżeli napis ze źródła niesie klucz
    z wstrzykniętym znakiem sterującym, dopasowanie nie zachodzi. Przy kolejności
    „maskuj, potem normalizuj" `strip_control` usuwa potem ten znak i **odtwarza sekret**
    już po tym, jak maskowanie go nie zobaczyło — czyli klucz ląduje na ekranie operatora.

    Test jest napisany tak, żeby padł dokładnie przy odwróceniu tych dwóch wywołań.
    """
    register_secret(SEKRET_TESTOWY)
    polowa = len(SEKRET_TESTOWY) // 2
    z_wstrzyknieciem = SEKRET_TESTOWY[:polowa] + "\x01" + SEKRET_TESTOWY[polowa:]

    wynik = safe(f"Nagłówek: {z_wstrzyknieciem} koniec").plain

    assert SEKRET_TESTOWY not in wynik, (
        "Sekret wyciekł na ekran. Maskowanie porównuje napis surowy, więc musi iść "
        "**po** usunięciu znaków sterujących, nie przed nim."
    )
    assert "<token>" in wynik


def test_sekret_bez_zaklocen_jest_maskowany() -> None:
    """Ścieżka podstawowa — żeby test wyżej nie przechodził dlatego, że maskowanie w ogóle
    przestało działać."""
    register_secret(SEKRET_TESTOWY)
    assert safe(f"klucz: {SEKRET_TESTOWY}").plain == "klucz: <token>"


def test_znaczniki_rich_nie_sa_interpretowane() -> None:
    """Nawias kwadratowy ze źródła jest tekstem, nie znacznikiem.

    W `ceidg-tool` nazwa firmy z `[/b]` kończyła program wyjątkiem `MarkupError` spoza
    taksonomii wyjątków narzędzia, a `[link=…]` robiła z rekordu klikalny odnośnik na obcy
    adres. Tutaj wejściem jest uzasadnienie orzeczenia, czyli tekst pisany przez osoby
    trzecie i liczony w stronach.
    """
    wrogi = "Wykonawca [bold red]X[/] oraz [link=https://przyklad.example]odnosnik[/link]"
    assert safe(wrogi).plain == wrogi


def test_znaki_sterujace_nie_docieraja_do_terminala() -> None:
    """Sekwencja sterująca ze źródła nie steruje ekranem operatora."""
    assert "\x1b" not in safe("przed\x1b[2Jpo").plain


def test_pusta_wartosc_opcjonalna_zostaje_brakiem_wartosci() -> None:
    """Pusta data wydania to brak daty, a nie pusty napis.

    Rozróżnienie jest tu nośne: audyt mówi, że brakujące daty wydania są **klasą, nie
    wyjątkiem**, a rekord z pustą datą wypada z każdego filtra zakresowego po cichu.
    Widok ma pokazać „brak", a nie pustą komórkę udającą wartość.
    """
    assert safe_or_none(None) is None
    assert safe_or_none("") is None


@pytest.mark.parametrize("wartosc", ["KIO 827/18", "2026-09-15"])
def test_zwykla_wartosc_przechodzi_bez_zmiany(wartosc: str) -> None:
    """Neutralizator nie przepisuje treści, która niczego nie łamie."""
    wynik = safe_or_none(wartosc)
    assert wynik is not None
    assert wynik.plain == wartosc


def test_konsola_programu_nie_interpretuje_znacznikow() -> None:
    """Reguła 10 jako własność obiektu, nie własność skanu.

    Skan AST łapie przeoczenia, a `KioError` mówi w docstringu, że komunikat jest
    przeznaczony dla użytkownika — więc pierwsze `console.print(f"Błąd: {e}")` w warstwie CLI
    wpuściłoby treść wyjątku, a przez nią napis ze źródła, prosto do parsera znaczników
    `rich`. W CEIDG kończyło się to `MarkupError` na nazwie firmy i klikalnym odnośnikiem
    z `[link=…]`.

    Test celuje w **konsolę zwracaną przez `make_console`**, nie w `safe` — bo pyta o to, co
    się stanie, gdy ktoś o `safe` zapomni. Wypisujemy więc surowy napis, tak jak zrobiłby to
    nieuważny `console.print(f"…{obcy}")`.
    """
    konsola = make_console()
    wrogi = "Wykonawca [bold red]X[/] oraz [link=https://przyklad.example]odnosnik[/link]"

    with konsola.capture() as przechwycone:
        konsola.print(wrogi)
    wypisane = przechwycone.get()

    assert "[bold red]" in wypisane, (
        "Konsola zinterpretowała znaczniki. Reguła 10 wisi wtedy wyłącznie na tym, czy autor "
        "pamiętał o `safe` — czyli na skanie, który łapie przeoczenia, a nie na obiekcie."
    )
    assert "[link=" in wypisane, "Odnośnik ze źródła stał się klikalny mimo `markup=False`."
