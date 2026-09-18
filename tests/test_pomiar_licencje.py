"""Strażnik pomiaru 23 — `scripts/pomiar_licencje.py`.

Do 2026-09-18 w `tests/test_sonda.py`. Lista markerów jest **przepisana** z pomiaru 14, a nie
wymyślona dla pomiaru 23 — to jest cały sens pomiaru i pierwszy test niżej ją przybija.
Materiał i kształt atrapy opisuje nagłówek `wsparcie_sondy.py`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import httpx

# Moduły sondy mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import pomiar_licencje

from kio_tool.config import ATLAS_HOSTS, SAOS_HOSTS
from tests.wsparcie_sondy import (
    SCIEZKA_ATLAS_DOKUMENTACJA,
    SCIEZKA_KORZEN,
    UA_TESTOWY,
    Odpowiedz,
    Serwis,
    ZegarTestowy,
    wynik,
)

# --- pomiar 23: licencje pośredników odczytane u źródła ------------------------------------


def test_markery_licencji_sa_te_same_co_w_pomiarze_14() -> None:
    """Lista markerów jest **przepisana** z pomiaru 14, a nie wymyślona dla pomiaru 23.

    To jest cały sens tego pomiaru: to samo pytanie zadane tym samym sposobem trzem hostom daje
    wyniki, które wolno ze sobą zestawić. Inna lista dla innego hosta mierzyłaby różnicę między
    listami, nie między serwisami — i byłaby zdaniem prawdziwie wyglądającym i pustym.

    Test przybija skład listy, bo jej cicha zmiana unieważniłaby porównanie z wynikiem zapisanym
    w `docs/decisions.md` pod datą 2026-09-15, a nikt by tego nie zauważył.
    """
    assert pomiar_licencje.MARKERY_LICENCJI == (
        "licencj",
        "creative",
        "ponowne wykorzyst",
        "warunki korzystania",
        "regulamin",
        "prawa autorskie",
    )
    assert all(m.isascii() and m.islower() for m in pomiar_licencje.MARKERY_LICENCJI), (
        "porównanie idzie po bajtach ASCII i po małych literach — marker z ogonkiem albo "
        "z wielką literą nie trafiłby nigdy i milczałby o tym"
    )


def test_zliczanie_markerow_jest_niewrazliwe_na_wielkosc_liter_i_odmiane() -> None:
    """`licencj` ma łapać „licencja" i „licencji"; `Creative` ma się znaleźć mimo wielkich liter."""
    tresc = b"<html>Tresc na LICENCJI Creative Commons; licencja opisana w Regulaminie.</html>"

    trafienia = pomiar_licencje.policz_markery(tresc)

    assert trafienia["licencj"] == 2, "odmiana rzeczownika nie ma decydować o wyniku pomiaru"
    assert trafienia["creative"] == 1
    assert trafienia["regulamin"] == 1
    assert trafienia["prawa autorskie"] == 0


def test_zero_markerow_jest_wynikiem_a_nie_cisza() -> None:
    """Zero trafień to dokładnie ten wynik, który pomiar 14 uznał za rozstrzygający dla UZP.

    Gdyby opis przy zerze trafień był pusty, brak markerów wyglądałby w podsumowaniu jak pomiar
    pominięty, a nie jak jego rezultat — czyli cisza w miejscu, w którym stoi wniosek.
    """
    opis = pomiar_licencje.opisz_markery(
        pomiar_licencje.policz_markery(b"<html>nic tu nie ma</html>")
    )

    assert "zero trafień" in opis
    assert "pomiarze 14" in opis, "wynik ma się sam odnosić do pomiaru, z którym jest porównywalny"


def test_opis_markerow_wymienia_tylko_obecne() -> None:
    opis = pomiar_licencje.opisz_markery(
        pomiar_licencje.policz_markery(b"<html>regulamin i regulamin</html>")
    )

    assert "`regulamin`\u00d72" in opis
    # Nagłówek „markery licencji:" niesie ten napis zawsze; pytanie dotyczy **wyliczenia**,
    # czyli postaci z odwróconym apostrofem, w jakiej opis wymienia trafienia.
    assert "`licencj`" not in opis, "marker nieobecny nie ma prawa trafić do opisu jako obecny"


def test_pomiar_23_pyta_trzy_adresy_i_kazdy_przez_bramke_swojego_kanalu(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Dwa korzenie i jedna podstrona, każdy klient zawężony do **swojego** kanału.

    Jeden klient dopuszczający oba hosty byłby sumą zbiorów, czyli dokładnie tym, przed czym
    broni `test_kazdy_pomiar_zawezia_bramke_wyjscia_do_jednego_kanalu`: przekierowanie z jednego
    serwisu poprowadziłoby żądanie do drugiego wewnątrz tej samej bramki.
    """
    serwis = Serwis(
        {
            SCIEZKA_KORZEN: Odpowiedz(tresc=b"<html>licencja CC BY 4.0</html>"),
            SCIEZKA_ATLAS_DOKUMENTACJA: Odpowiedz(tresc=b"<html>na licencji CC BY 4.0</html>"),
        }
    )
    podstaw(serwis)

    wyniki = pomiar_licencje.pomiar_licencje(UA_TESTOWY)

    assert [w.nazwa for w in wyniki] == [
        "licencje_23_saos",
        "licencje_23_atlas",
        "licencje_23_atlas_dokumentacja",
    ]
    assert serwis.bramki == [SAOS_HOSTS, ATLAS_HOSTS, ATLAS_HOSTS], (
        f"bramki wyjścia: {serwis.bramki} — każdy adres ma iść przez klient własnego kanału"
    )
    assert all("licencj" in w.uwaga for w in wyniki), (
        "wynik pomiaru 23 nie dotarł do `uwaga`, więc nie trafi do podsumowania na dysku"
    )
    assert all("adres z:" in w.uwaga for w in wyniki), "źródło adresu nie doszło do uwagi"


def test_pomiar_23_podstrona_wylacznie_z_odczytem_z_data() -> None:
    """Korzeń hosta nie wymaga źródła; podstrona wymaga daty odczytu w `zrodlo`.

    Wpisanie `/regulamin` albo `/terms` z domysłu byłoby adresem bez pokrycia w pliku, którego
    zadaniem jest produkować dowód — czyli zasadą 7.1 złamaną w sondzie. `/dokumentacja-api`
    Atlasu weszła 2026-09-18 **po odczycie**, i data tego odczytu ma stać przy adresie.
    """
    korzenie = 0
    for kanal in pomiar_licencje.KANALY_LICENCJI:
        assert any(host in kanal.adres for host in kanal.hosty), (
            f"{kanal.nazwa}: adres spoza zbioru bramki"
        )
        ogon = kanal.adres.split("://", 1)[1].split("/", 1)
        if len(ogon) == 1 or ogon[1] == "":
            korzenie += 1
            continue
        assert re.search(r"20\d\d-\d\d-\d\d", kanal.zrodlo), (
            f"{kanal.nazwa}: podstrona `{kanal.adres}` bez daty odczytu w źródle — adres "
            "zgadnięty, nie odczytany"
        )
    assert korzenie >= 2, "pomiar 23 ma pytać korzenie obu hostów tą samą drogą co pomiar 14"


# --- werdykt tylko z odpowiedzi, która nadaje się do odczytu ---------------------------------
#
# Przegląd kodu 2026-09-18: markery liczyły się z pustych bajtów, gdy żądanie nie wróciło, i ze
# strony błędu, gdy serwis odmówił — a zdanie o zerze trafień samo powołuje się na pomiar 14.
# Powstawał wynik pomiaru licencyjnego z odpowiedzi, której nie było. Poprawione tego samego dnia
# (`werdykt_licencji`).


def test_werdykt_bez_odpowiedzi_nie_udaje_zera_trafien() -> None:
    bez_odpowiedzi = wynik(status=None, plik=None, bajtow=0)

    opis = pomiar_licencje.werdykt_licencji(bez_odpowiedzi)

    assert "nie policzone" in opis and "brak odpowiedzi" in opis
    assert "zero trafień**" not in opis, "brak odpowiedzi wypisał się jako wynik pomiaru"


def test_werdykt_po_odmowie_serwisu_nie_liczy_markerow_na_stronie_bledu(tmp_path: Path) -> None:
    strona_bledu = tmp_path / "403.html"
    strona_bledu.write_bytes(b"<html>403 forbidden; licencja? regulamin?</html>")
    odmowa = wynik(status=403, plik=strona_bledu)

    opis = pomiar_licencje.werdykt_licencji(odmowa)

    assert "nie policzone" in opis and "status 403" in opis
    assert "`licencj`" not in opis, "markery ze strony błędu weszły do werdyktu"


def test_pomiar_23_zapisuje_nieodczytane_odpowiedzi_jako_nieodczytane(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Spięcie: SAOS odmawia (403), korzeń Atlasu nie odpowiada wcale, dokumentacja odpowiada —
    trzy wyniki, trzy różne zdania w `uwaga`, żadne nie udaje pomiaru 14."""
    serwis = Serwis(
        {
            SCIEZKA_KORZEN: [
                Odpowiedz(status=403, tresc=b"forbidden"),
                httpx.ConnectError("brak połączenia"),
            ],
            SCIEZKA_ATLAS_DOKUMENTACJA: Odpowiedz(tresc=b"<html>na licencji CC BY 4.0</html>"),
        }
    )
    podstaw(serwis)

    saos, atlas, dokumentacja = pomiar_licencje.pomiar_licencje(UA_TESTOWY)

    assert "nie policzone" in saos.uwaga and "status 403" in saos.uwaga
    assert "nie policzone" in atlas.uwaga and "brak odpowiedzi" in atlas.uwaga
    assert "`licencj`" in dokumentacja.uwaga and "nie policzone" not in dokumentacja.uwaga
