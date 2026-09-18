"""Parser `Retry-After` — własność właściciela protokołu, `kio_tool/httpclient.py`.

Do 2026-09-18 funkcja mieszkała w `scripts/sonda.py` jako `_retry_after_s`; przeniosła się do
właściciela protokołu razem z testem i z powodem: `ratelimit.note_response` deklaruje, że
nagłówek jest „honorowany dosłownie", więc czytać go ma ten, kto zna RFC 9110, a nie każdy
wywołujący z osobna. Trzy mechanizmy bramki wyjścia mają własnych strażników
w `test_bramka_wyjscia.py`. Żaden test w tym pliku nie dotyka sieci.

Przegląd 2026-09-18 rozbił jeden test o dziewięciu asercjach na przypadki. Powód jest
diagnostyczny, nie estetyczny: przy komplecie w jednym ciele pierwsza czerwona asercja
zatrzymuje pozostałe, więc „postać datowa się zepsuła" i „postać sekundowa się zepsuła"
wyglądały na ekranie tak samo — a nazwa testu mówiła wyłącznie o datowej. Rozbicie pokazało
przy okazji dwie granice, o które nikt nie pytał (`Retry-After: -5` i nagłówek pusty), oraz
jedną, która wiesza sondę (znalezisko na końcu pliku).
"""

from __future__ import annotations

import math

import pytest

from kio_tool.httpclient import parse_retry_after

TERAZ = 1_700_000_000.0
"""Ten sam punkt w czasie co `ZegarTestowy.start_wall`: 2023-11-14T22:13:20Z."""


# --- postać `delta-seconds` -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("naglowek", "oczekiwane"),
    [
        ("120", 120.0),
        ("  120  ", 120.0),
        ("1.5", 1.5),
        ("0", 0.0),
    ],
    ids=["sekundy", "z-bialymi-znakami", "zmiennoprzecinkowy", "zero"],
)
def test_delta_seconds_idzie_do_limitera_jako_liczba(naglowek: str, oczekiwane: float) -> None:
    """Pierwsza wersja brała wyłącznie `str.isdigit()`, więc wartość z białym znakiem i zapis
    zmiennoprzecinkowy szły do `note_response` jako `None`.

    Skutek był podwójnie cichy: limiter brał wtedy własną blokadę 60 s, sonda wznawiała
    **wcześniej, niż serwis poprosił**, i nikt się o tym nie dowiadywał. W projekcie, którego
    pierwsza reguła brzmi „narzędzie nie omija zabezpieczeń" (audyt 12), to jest cisza dokładnie
    w miejscu, w którym cudzy serwis mówi „nie teraz".
    """
    assert parse_retry_after(naglowek, teraz_epoch=TERAZ) == (oczekiwane, "")


def test_ujemne_delta_seconds_znaczy_termin_minal_a_nie_wznow_wczesniej() -> None:
    """Granica bez obserwatora do 2026-09-18 (zmierzone mutacją: skreślenie `max(0.0, …)`
    z gałęzi sekundowej przechodzi przez cały zielony przebieg).

    Wartość ujemna dojechałaby wtedy do `note_response` jako `-5.0`, a stamtąd do
    `max(self._cooldown_s, retry_after_s)` — czyli **skróciłaby** blokadę własną limitera
    zamiast ją wydłużyć. Kierunek pomyłki jest tu ten kosztowny: sonda wraca do serwisu, który
    właśnie powiedział „nie teraz", i robi to szybciej niż bez nagłówka.
    """
    assert parse_retry_after("-5", teraz_epoch=TERAZ) == (0.0, "")


# --- postać `HTTP-date` ---------------------------------------------------------------------


def test_data_w_przyszlosci_jest_przeliczana_na_sekundy_do_terminu() -> None:
    """RFC 9110 dopuszcza obok `delta-seconds` także `HTTP-date`, a pierwsza wersja jej nie
    czytała. `2023-11-14T22:23:20Z` to dziesięć minut po `TERAZ`."""
    sekundy, uwaga = parse_retry_after("Tue, 14 Nov 2023 22:23:20 GMT", teraz_epoch=TERAZ)

    assert uwaga == ""
    assert sekundy == pytest.approx(600.0, abs=1.0)


def test_data_w_przeszlosci_znaczy_termin_minal_a_nie_nie_umiem_przeczytac() -> None:
    """Dwa różne zdania i dwie różne reakcje: termin miniony zwalnia natychmiast, nagłówek
    nieczytelny każe trzymać własną blokadę limitera."""
    assert parse_retry_after("Tue, 14 Nov 2023 21:23:20 GMT", teraz_epoch=TERAZ) == (0.0, "")


# --- nagłówka nie ma albo nie da się go przeczytać ------------------------------------------


def test_brak_naglowka_nie_jest_zdarzeniem_i_nie_niesie_uwagi() -> None:
    """Serwis, który nie podał `Retry-After`, nie zrobił nic złego — uwaga przy każdej
    odpowiedzi bez nagłówka byłaby szumem w kolumnie, która ma krzyczeć tylko wtedy, gdy
    jest o czym."""
    assert parse_retry_after(None, teraz_epoch=TERAZ) == (None, "")


@pytest.mark.parametrize(
    ("naglowek", "opis"),
    [
        ("jutro rano", "napis w cudzym języku"),
        ("", "nagłówek obecny, ale pusty"),
        ("   ", "nagłówek z samych białych znaków"),
        ("Tue, 99 Zzz 2023 99:99:99 GMT", "data w kształcie daty, ale nie do sparsowania"),
    ],
    ids=["napis", "pusty", "biale-znaki", "data-niepoprawna"],
)
def test_naglowek_nie_do_odczytania_zostawia_uwage_zamiast_ciszy(naglowek: str, opis: str) -> None:
    """Nagłówek nie do odczytania **nie jest** cichy: uwaga wraca przy wyniku, czyli trafia na
    ekran i do `podsumowanie_*.json` (`test_zadanie.py` pilnuje drugiej połowy tej drogi).

    Nagłówek pusty i nagłówek z samych białych znaków dołączyły 2026-09-18 — zmierzone mutacją:
    wcześniejsze zwrócenie `(None, "")` dla pustego napisu przechodziło zielono, a jest to
    postać, którą serwer wystawia najłatwiej z wszystkich (`Retry-After:` bez wartości).
    """
    sekundy, uwaga = parse_retry_after(naglowek, teraz_epoch=TERAZ)

    assert sekundy is None, f"{opis}: nieczytelny nagłówek dał limiterowi liczbę"
    assert "nie umiem przeczytać" in uwaga, f"{opis}: nieczytelny nagłówek przeszedł w ciszy"
    assert naglowek.strip() in uwaga, f"{opis}: uwaga nie mówi, czego nie umiała przeczytać"


# ------------------------------------------------------------------------------- znaleziska


@pytest.mark.parametrize(
    "naglowek", ["inf", "Infinity", "1e400", "nan"], ids=["inf", "Infinity", "1e400", "nan"]
)
def test_retry_after_nie_ma_prawa_zatrzymac_przebiegu_na_zawsze(naglowek: str) -> None:
    """Znalezisko 2026-09-18, zgłoszone jako `xfail(strict=True)` i **poprawione tego samego
    dnia** progiem `math.isfinite` po konwersji; znacznik zdjęty razem z poprawką, `nan` dopisany
    do parametrów, bo od tego dnia odpowiedź na niego jest rozstrzygnięta, nie przypadkowa.

    `delta-seconds` w RFC 9110 to `1*DIGIT`, a `float()` czyta więcej.

    Droga jest cała w kodzie tego projektu i nie ma na niej żadnego progu:
    `parse_retry_after("inf")` zwraca `(inf, "")`, `wykonaj` podaje to
    `limiter.note_response(retry_after_s=inf)`, tam `max(self._cooldown_s, inf)` daje
    `_blocked_until_mono = inf`, a `acquire` woła `_sleep_in_slices(inf)`. Ta pętla ma warunek
    `pozostalo > _WAIT_EPSILON_S` i odejmuje plaster 300 s od nieskończoności — czyli **nie
    kończy się nigdy** i nie kończy się też `LimiterStalledError`, bo licznik
    `_MAX_WAIT_ITERATIONS` stoi w pętli zewnętrznej. Operator widzi jedno „czekam inf s"
    i ciszę; sonda wisi do `Ctrl+C`.

    Zmierzone 2026-09-18:
    `parse_retry_after("inf", teraz_epoch=1_700_000_000.0) == (inf, "")`, tak samo `1e400`.
    `nan` jest dziś nieszkodliwy przypadkiem — `max(0.0, nan)` zwraca `0.0`, bo porównanie
    z `nan` jest fałszywe — i to też jest powód, żeby nie zostawiać tej gałęzi bez progu.

    Waga bierze się z tego, że nagłówek jest **cudzy**. Reguła „narzędzie nie omija
    zabezpieczeń" każe honorować `Retry-After` dosłownie, ale dosłowność kończy się tam, gdzie
    wartość przestaje być liczbą sekund: `inf` nie jest prośbą o odczekanie, tylko śmieciem
    albo złośliwością, a odpowiedzią na śmieć jest własna blokada limitera i uwaga — dokładnie
    to, co ta funkcja robi z napisem „jutro rano".

    Test celuje w zachowanie, nie w postać poprawki: wynik ma być albo skończoną liczbą sekund,
    albo odmową odczytu z uwagą. Progiem może być `str.isdigit()` na gałęzi sekundowej,
    `math.isfinite` po konwersji albo sufit wzięty z `WAIT_SLICE_S` — to jest decyzja
    właściciela protokołu, nie tego pliku.
    """
    sekundy, uwaga = parse_retry_after(naglowek, teraz_epoch=TERAZ)

    if sekundy is None:
        assert "nie umiem przeczytać" in uwaga
        return
    assert math.isfinite(sekundy), (
        f"`Retry-After: {naglowek}` wraca jako {sekundy} i wiesza przebieg w plastrach po 300 s "
        "— bez `LimiterStalledError`, bez drugiego komunikatu, bez końca"
    )
