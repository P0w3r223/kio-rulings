"""Rodzina jednorazowa z ADR-0007 §5.1: awaria, która **ustępuje**, nie przerywa przebiegu.

`tests/test_odpornosc_sieci.py` mierzy awarię trwałą — ta kończy przebieg jako `przerwany`
i wznawialny, jak przed ponowieniami (Z-10). Tu mierzona jest druga połowa: ta sama awaria na
jednej próbie kończy się przebiegiem `zakonczony`, z **dwoma** wierszami dziennika na ten sam
adres (`proba` 1 i 2), zdaniem o ponowieniu na ekranie i liczbą ponowień w podsumowaniu, czytaną
z bazy. Całość idzie prawdziwą drogą produkcji: `pipeline.pobierz`, `build_http_client`, adapter
Atlasu, `Store` — atrapa wyłącznie jako transport (`SerwisAwaryjny(jednorazowa=True)`).

Obok stoi Z-9: żądanie, które opuściło proces i nie wróciło, liczy się do progu zgody. Przed
ADR-0007 tę różnicę ograniczał pierwszy wyjątek transportu, który i tak kończył przebieg; z
ponowieniami przebieg idzie dalej, więc licznik liczący odpowiedzi zamiast żądań rozszczelniłby
próg.
"""

from __future__ import annotations

import json

import httpx
import pytest

from kio_tool import pipeline
from kio_tool.errors import ConsentMissingError, TransportError
from kio_tool.progress import NullEvents
from kio_tool.store import Store
from tests.test_odpornosc_sieci import AWARIE_PRZEJSCIOWE
from tests.test_odpornosc_wspolne import (
    KONTRAKT,
    LICZNIK,
    MA_WIECEJ,
    REKORDY,
    SLUGI,
    Reakcja,
    SerwisAwaryjny,
    _bez_klucza_ze_srodowiska,
    jedyny_przebieg,
    store,
    uruchom,
)

__all__ = ["_bez_klucza_ze_srodowiska", "store"]
"""Fixtures z modułu wspólnego wymienione wprost — pytest szuka ich po nazwie w tym module."""

PON = KONTRAKT.ponowienia
KLUCZ = KONTRAKT.ksztalt.lista.klucz

LISTA_MALA = json.dumps({KLUCZ: REKORDY[:3], MA_WIECEJ: False, LICZNIK: 3}).encode()
"""Trzy rekordy ze złotego pliku — odczyt poniżej progu zgody, jak w `test_pipeline.py`."""

PELNY = json.dumps(
    {"slug": "x", "primary_signature": "(wymyslona)", KONTRAKT.ksztalt.dokument.pole_tresci: "t"}
).encode()


def _urwana(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=PELNY[: len(PELNY) // 2])


def _odmowa(_: httpx.Request) -> httpx.Response:
    return httpx.Response(429, content=b"{}")


RODZINA_JEDNORAZOWA = [
    *AWARIE_PRZEJSCIOWE,
    pytest.param(_urwana, id="urwana-200"),
    pytest.param(_odmowa, id="429"),
]
"""Osiem awarii, po których README obiecuje wznowienie, plus dwie klasy, które Z-1 dołożyła do
ponawianych: urwane ciało przy 200 i 429 po pełnej blokadzie. Lista jest **importowana** z pliku
awarii trwałych, nie przepisana — pozycja dopisana tam trafia tu bez niczyjej pamięci."""


class Ekran(NullEvents):
    def __init__(self) -> None:
        self.komunikaty: list[str] = []

    def on_message(self, text: str) -> None:
        self.komunikaty.append(text)


def proby_adresu(store: Store, fragment: str) -> list[tuple[int | None, int]]:
    """(status, proba) wierszy dziennika o adresie kończącym się `fragment`, w kolejności zapisu."""
    kursor = store._conn.execute(
        "SELECT status, proba FROM requests_log WHERE url_redacted LIKE ? ORDER BY rowid",
        (f"%{fragment}",),
    )
    return [(w[0], int(w[1])) for w in kursor]


@pytest.mark.parametrize("reakcja", RODZINA_JEDNORAZOWA)
def test_jednorazowa_awaria_na_dokumencie_konczy_przebieg_z_ponowieniem_w_dzienniku(
    store: Store, reakcja: Reakcja
) -> None:
    ekran = Ekran()
    serwis = SerwisAwaryjny(na_dokumencie=3, reakcja=reakcja, jednorazowa=True)

    wynik = uruchom(store, serwis, events=ekran)

    assert serwis.awarii == 1, "atrapa zepsuła dokładnie jedną próbę"
    assert wynik.status == "zakonczony"
    assert store.get_run(jedyny_przebieg(store)).status == "zakonczony"
    assert store.count("documents") == store.count("raw_versions") == len(SLUGI)
    proby = proby_adresu(store, f"/{SLUGI[2]}")
    assert [p for _, p in proby] == [1, 2], "dwa wiersze na ten sam dokument: próba 1 i 2"
    assert proby[1][0] == 200
    assert wynik.ponowien_lacznie == 1
    assert wynik.zadan == wynik.zadan_lacznie == 2 + len(SLUGI) + 1, (
        "dwie strony listy, sto dokumentów i jedno ponowienie — każde żądanie policzone raz"
    )
    assert [k for k in ekran.komunikaty if "próba 2" in k and f"dokument {SLUGI[2]}" in k], (
        f"na ekranie nie padło zdanie o ponowieniu: {ekran.komunikaty}"
    )


@pytest.mark.parametrize("numer", [1, 2])
def test_jednorazowa_awaria_na_stronie_listy_nie_przerywa_stronicowania(
    store: Store, numer: int
) -> None:
    """Z-3 na potoku: strona listy jest ponawiana w kanale, więc przebieg nie zaczyna listy od
    nowa ani nie przeskakuje strony — prosi o tę samą stronę jeszcze raz."""
    serwis = SerwisAwaryjny(na_stronie=numer, jednorazowa=True)

    wynik = uruchom(store, serwis)

    oczekiwane = ["1", "2"]
    oczekiwane.insert(numer - 1, str(numer))
    assert serwis.strony_zadane == oczekiwane
    assert wynik.status == "zakonczony" and wynik.nowych == len(SLUGI)
    assert wynik.ponowien_lacznie == 1


def test_trwala_awaria_zostawia_wszystkie_proby_w_dzienniku_z_numerami(store: Store) -> None:
    """Z-8 od strony awarii, która nie ustępuje: pomiar 24 (skuteczność ponowień) ma w bazie
    każdą próbę, także te, które niczego nie dały."""
    with pytest.raises(TransportError):
        uruchom(store, SerwisAwaryjny(na_dokumencie=3))

    assert proby_adresu(store, f"/{SLUGI[2]}") == [(None, n) for n in range(1, PON.proby + 1)]


def test_liczba_ponowien_w_podsumowaniu_przezywa_wznowienie(store: Store) -> None:
    """Z-7 ujście 4: liczba z bazy, nie z pamięci procesu. Ponowienia padły w pierwszej sesji,
    a podsumowanie drugiej, która sama nie ponowiła niczego, ma je nadal wypisać."""
    with pytest.raises(TransportError):
        uruchom(store, SerwisAwaryjny(na_dokumencie=3))

    wynik = uruchom(store, SerwisAwaryjny())

    assert wynik.run_id == jedyny_przebieg(store) and wynik.status == "zakonczony"
    assert wynik.ponowien_lacznie == PON.proby - 1


def test_przebieg_bez_awarii_ma_zero_ponowien(store: Store) -> None:
    wynik = uruchom(store, SerwisAwaryjny())

    assert wynik.ponowien_lacznie == 0
    wiersze = store._conn.execute("SELECT DISTINCT proba FROM requests_log").fetchall()
    assert [w[0] for w in wiersze] == [1]


# --- Z-9: próg zgody liczy żądania wysłane, nie odpowiedzi ------------------------------------


def test_zadanie_bez_odpowiedzi_liczy_sie_do_progu_zgody(store: Store) -> None:
    """Lista bez `total`, więc próg pilnuje wyłącznie licznik żądań. Zerwane łącze na dziesiątym
    dokumencie i jego ponowienie to **dwa** żądania do cudzego serwera — przebieg bez zgody ma
    stanąć po `PROG_ZGODY` żądaniach, a nie po `PROG_ZGODY` odpowiedziach.

    Licznik w `on_request` (stan sprzed Z-9) nie widziałby próby, która nie wróciła, i puściłby
    o jeden dokument więcej — żądanie numer `PROG_ZGODY + 1` bez pytania o zgodę.
    """
    rekordy = REKORDY[: pipeline.PROG_ZGODY + 5]
    bez_total = json.dumps({KLUCZ: rekordy, MA_WIECEJ: False}).encode()
    serwis = SerwisAwaryjny([bez_total], na_dokumencie=10, jednorazowa=True)

    with pytest.raises(ConsentMissingError):
        uruchom(store, serwis, zgoda=False)

    assert serwis.awarii == 1
    assert store.count("requests_log") == pipeline.PROG_ZGODY, (
        "wysłano więcej żądań, niż próg zgody pozwala bez zgody"
    )
    assert store.count("documents") == pipeline.PROG_ZGODY - 2, (
        "lista i ponowienie zajęły dwa miejsca z progu, więc dokumentów jest o dwa mniej"
    )
    powod = store.get_run(jedyny_przebieg(store)).powod
    assert powod is not None and f"wysłano {pipeline.PROG_ZGODY}" in powod


def test_ponowienie_na_progu_zgody_nie_przekracza_progu(store: Store) -> None:
    """Znalezisko testera 2026-09-19: zgoda była sprawdzana raz na kandydata, a pętla prób
    wysyłała po nim kolejne żądania bez pytania — zmierzone 52 żądania przy progu 50. Awaria
    pada na **ostatnim** dokumencie mieszczącym się w progu i nie ustępuje, więc każda kolejna
    próba stoi już na progu i musi zostać zatrzymana przed wysłaniem."""
    rekordy = REKORDY[: pipeline.PROG_ZGODY + 5]
    bez_total = json.dumps({KLUCZ: rekordy, MA_WIECEJ: False}).encode()
    serwis = SerwisAwaryjny([bez_total], na_dokumencie=pipeline.PROG_ZGODY - 1)

    with pytest.raises(ConsentMissingError):
        uruchom(store, serwis, zgoda=False)

    assert store.count("requests_log") == pipeline.PROG_ZGODY, (
        "ponowienie poszło za próg zgody — pętla prób nie pyta o zgodę przed kolejną próbą"
    )


def test_zadanie_bez_odpowiedzi_liczy_sie_do_zadan_w_podsumowaniu(store: Store) -> None:
    """`Podsumowanie.zadan` (sesja) i `zadan_lacznie` (baza) mówią to samo także wtedy, gdy
    jedno z żądań nie dostało odpowiedzi — oba liczą żądania, które opuściły proces."""
    maly = SerwisAwaryjny(
        [LISTA_MALA], na_dokumencie=2, jednorazowa=True, reakcja=lambda _: httpx.ReadTimeout("x")
    )

    wynik = uruchom(store, maly, zgoda=False)

    assert wynik.status == "zakonczony" and wynik.nowych == 3
    assert wynik.zadan == wynik.zadan_lacznie == 1 + 3 + 1
