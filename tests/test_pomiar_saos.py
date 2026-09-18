"""Strażnik pomiaru 2a/2b — `scripts/pomiar_saos.py`.

Do 2026-09-18 w `tests/test_sonda.py`. Treścią jest rozróżnienie z przebudowy 2026-09-17:
niezgodny kształt jedzie dalej (dwie sprzeczne pisownie parametru dat po to są, żeby sprawdzić,
która działa), odmowa **serwisu** zatrzymuje grupę, a kontrola hosta idzie dokładnie raz.
Materiał i kształt atrapy opisuje nagłówek `wsparcie_sondy.py`.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

# Moduły sondy mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import pomiar_saos
import pytest

from tests.wsparcie_sondy import (
    BOT_CHECK,
    SAOS_DUMP_OK,
    SCIEZKA_KORZEN,
    SCIEZKA_SAOS,
    UA_TESTOWY,
    Odpowiedz,
    Serwis,
    ZegarTestowy,
)


def test_pomiar_saos_po_odmowie_puka_w_korzen_dokladnie_raz(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Trzy odmowy, jedna kontrola. Kontrola na żądanie byłaby trzema dodatkowymi żądaniami
    przeciw hostowi, który właśnie powiedział „nie" — a odpowiada i tak na jedno pytanie."""
    serwis = Serwis(
        {SCIEZKA_SAOS: Odpowiedz(status=403, tresc=b"forbidden"), SCIEZKA_KORZEN: Odpowiedz()}
    )
    podstaw(serwis)

    wyniki = pomiar_saos.pomiar_saos(UA_TESTOWY)

    assert serwis.slad.count(("GET", SCIEZKA_KORZEN)) == 1
    assert serwis.slad[-1] == ("GET", SCIEZKA_KORZEN)
    assert len(wyniki) == 4


def test_pomiar_saos_probuje_obu_pisowni_parametrow_dat(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Wiki SAOS jest wewnętrznie sprzeczna co do nazw parametrów dat i to własne wywołanie
    ma to rozstrzygnąć, a nie lektura. Pomiar wysyłający jedną pisownię odpowiada na pytanie
    „czy ta nazwa działa", a nie na zadane „która z dwóch"."""
    serwis = Serwis({SCIEZKA_SAOS: Odpowiedz(tresc=SAOS_DUMP_OK)})
    podstaw(serwis)

    pomiar_saos.pomiar_saos(UA_TESTOWY)

    klucze = [set(z.url.params.keys()) for z in serwis.zadania]

    assert any({"judgmentDateFrom", "judgmentDateTo"} <= k for k in klucze)
    assert any({"judgmentStartDate", "judgmentEndDate"} <= k for k in klucze)
    assert any("courtType" in k for k in klucze), "pomiar 2b (filtr po organie) nie został wysłany"


def test_pomiar_saos_bez_odmowy_nie_puka_w_korzen(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    serwis = Serwis({SCIEZKA_SAOS: Odpowiedz(tresc=SAOS_DUMP_OK)})
    podstaw(serwis)

    assert len(pomiar_saos.pomiar_saos(UA_TESTOWY)) == 3
    assert ("GET", SCIEZKA_KORZEN) not in serwis.slad


# --- pomiar SAOS: co zatrzymuje grupę, a co nie --------------------------------------------


def test_pomiar_saos_jedzie_dalej_po_niezgodnym_ksztalcie(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Pierwsza połowa rozróżnienia i ta trudniejsza do zauważenia.

    Zła pisownia parametru dat objawi się najpewniej odpowiedzią **200 o innym kształcie** —
    bo serwis dostanie zapytanie bez filtru albo z filtrem nierozpoznanym. Przerwanie na tym
    byłoby porzuceniem pomiaru dokładnie w chwili, w której zaczyna on odpowiadać na zadane
    pytanie „która z dwóch pisowni działa”. Scenariusz przewiduje **trzy** odpowiedzi, więc
    czwarte żądanie na ten punkt kończy się `AssertionError`.
    """
    serwis = Serwis(
        {
            SCIEZKA_SAOS: [
                Odpowiedz(tresc=b'{"error": "unknown parameter"}'),
                Odpowiedz(tresc=SAOS_DUMP_OK),
                Odpowiedz(tresc=SAOS_DUMP_OK),
            ],
            SCIEZKA_KORZEN: Odpowiedz(),
        }
    )
    podstaw(serwis)

    wyniki = pomiar_saos.pomiar_saos(UA_TESTOWY)

    assert [w.wyslane for w in wyniki[:3]] == [True, True, True], (
        "niezgodny kształt pierwszej pisowni zatrzymał grupę — pomiar 2a przestał mierzyć to, "
        "po co powstał"
    )
    assert [w.ksztalt_zgodny for w in wyniki[:3]] == [False, True, True]


def test_pomiar_saos_po_niezgodnym_ksztalcie_i_tak_puka_w_korzen(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Kontrola hosta stoi na szerszym warunku niż zatrzymanie i to jest celowe: 200 o obcym
    kształcie może być stroną bot-checka, a wtedy pytanie „punkt czy host” ma sens mimo że
    grupa pojechała do końca."""
    serwis = Serwis(
        {
            SCIEZKA_SAOS: [
                Odpowiedz(tresc=BOT_CHECK),
                Odpowiedz(tresc=SAOS_DUMP_OK),
                Odpowiedz(tresc=SAOS_DUMP_OK),
            ],
            SCIEZKA_KORZEN: Odpowiedz(),
        }
    )
    podstaw(serwis)

    wyniki = pomiar_saos.pomiar_saos(UA_TESTOWY)

    assert serwis.slad[-1] == ("GET", SCIEZKA_KORZEN)
    assert wyniki[-1].nazwa == "saos_kontrola_hosta"


@pytest.mark.parametrize(
    ("opis", "pierwsza", "fragment_powodu"),
    [
        ("odmowa 403", Odpowiedz(status=403, tresc=b"forbidden"), "403"),
        ("limit 429", Odpowiedz(status=429, tresc=b""), "429"),
        ("brak odpowiedzi", httpx.ConnectError("brak polaczenia"), "brak odpowiedzi"),
    ],
)
def test_pomiar_saos_staje_po_odmowie_serwisu_i_nie_puka_trzy_razy(
    opis: str,
    pierwsza: Odpowiedz | BaseException,
    fragment_powodu: str,
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Druga połowa rozróżnienia: do serwisu, który właśnie powiedział „nie”, nie puka się
    trzy razy pod rząd.

    Scenariusz podaje dla punktu zrzutu **jedną** odpowiedź w liście, więc drugie żądanie na
    ten sam punkt kończy się `AssertionError` — zatrzymanie jest tu sprawdzane tym, że
    następne żądanie fizycznie nie ma prawa wyjść, a nie samą liczbą wpisów na liście.
    """
    serwis = Serwis({SCIEZKA_SAOS: [pierwsza], SCIEZKA_KORZEN: Odpowiedz()})
    podstaw(serwis)

    wyniki = pomiar_saos.pomiar_saos(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_SAOS), ("GET", SCIEZKA_KORZEN)], (
        f"{opis}: poszło więcej żądań, niż wolno po odmowie serwisu"
    )
    assert [w.wyslane for w in wyniki] == [True, False, False, True]
    for pominiety in wyniki[1:3]:
        assert fragment_powodu in pominiety.uwaga
        assert "saos_2a_dump_datefrom" in pominiety.uwaga


def test_pomiar_saos_staje_dopiero_na_tej_probie_ktora_dostala_odmowe(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Odmowa na drugiej próbie zostawia pierwszą zmierzoną, a trzecią niewysłaną.

    Zatrzymanie liczone od początku grupy skasowałoby wynik, za który cudzy serwer już
    zapłacił pracą; zatrzymanie nieliczone w ogóle wysłałoby trzecie żądanie po „nie”.
    """
    serwis = Serwis(
        {
            SCIEZKA_SAOS: [Odpowiedz(tresc=SAOS_DUMP_OK), Odpowiedz(status=403, tresc=b"nie")],
            SCIEZKA_KORZEN: Odpowiedz(),
        }
    )
    podstaw(serwis)

    wyniki = pomiar_saos.pomiar_saos(UA_TESTOWY)

    assert [w.wyslane for w in wyniki] == [True, True, False, True]
    assert [w.nazwa for w in wyniki] == [
        "saos_2a_dump_datefrom",
        "saos_2a_dump_startdate",
        "saos_2b_courttype",
        "saos_kontrola_hosta",
    ]
    assert "saos_2a_dump_startdate" in wyniki[2].uwaga
