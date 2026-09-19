"""Polityka ponowień kanału Atlasu (ADR-0007) — pętla prób w `AtlasChannel._zadanie`.

Każdy test stawia kanałowi **kolejkę reakcji** serwisu: żądanie zdejmuje z niej jedną, a pusta
kolejka odpowiada złotym plikiem. Dzięki temu scenariusz „503, potem 200” jest zapisany wprost
w teście, a nie wywiedziony z licznika żądań atrapy — ta sama różnica, która w ADR-0007 §5.1
zapaliła szesnaście przypadków: awaria liczona po numerze żądania znika przy ponowieniu.

Liczby (próby, postoje, sufit) test bierze z `contract.yaml` przez `KONTRAKT.ponowienia`, bo
reguła 17 czyni kontrakt jedynym miejscem, z którego adapter bierze tempo; test, który
powtarzałby „3” i „2 s” z pamięci, byłby drugą listą. Jedyny wyjątek to test zgodności bloku
z ADR-0007 §3.1 — tam liczby są przedmiotem pomiaru.

Postoje są czytane z `ZegarTestowy.sleeps` co do wartości: brak rozrzutu (jitter) jest decyzją
ADR-0007 §3.1 właśnie po to, żeby dało się je tak czytać.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pydantic
import pytest

from kio_tool.config import ATLAS_HOSTS
from kio_tool.errors import (
    AuthError,
    BadRequestError,
    NotFoundError,
    RateLimitError,
    ServerError,
    SourceContractBroken,
    TransportError,
)
from kio_tool.httpclient import build_http_client
from kio_tool.progress import NullEvents
from kio_tool.ratelimit import (
    REASON_BACKOFF,
    REASON_COOLDOWN,
    InMemoryHistory,
    RateLimiter,
)
from kio_tool.source.atlas.channel import AtlasChannel
from kio_tool.source.contract import Contract, Ponowienia
from tests.test_source_atlas import (
    DOKUMENT_BAJTY,
    KONIEC_LISTY,
    KONTRAKT,
    LISTA_BAJTY,
    PARAM_STRONY,
    SCIEZKA_LISTY,
    ZAKRES,
    Slad,
)
from tests.wsparcie_sondy import UA_TESTOWY, ZegarTestowy

PON = KONTRAKT.ponowienia
REF = "kio-wymyslony-1-24"
"""Referencja wymyślona: kanał nie sprawdza, czy dokument pod nią jest tym ze złotego pliku."""

Krok = Callable[[httpx.Request], httpx.Response | BaseException]


def status(kod: int, **naglowki: str) -> Krok:
    return lambda _: httpx.Response(kod, content=b"{}", headers=naglowki)


def zerwane(_: httpx.Request) -> BaseException:
    return httpx.ConnectError("siec znikla (wymyslone)")


def urwana(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=DOKUMENT_BAJTY[: len(DOKUMENT_BAJTY) // 2])


def dobry(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=DOKUMENT_BAJTY)


def _lista_strona_1(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=LISTA_BAJTY)


class SerwerScenariusz:
    """Atrapa z kolejką reakcji — jedna na żądanie, po wyczerpaniu odpowiedź ze złotego pliku."""

    def __init__(self, *kroki: Krok) -> None:
        self.kroki = list(kroki)
        self.zadania: list[httpx.Request] = []

    def __call__(self, zadanie: httpx.Request) -> httpx.Response:
        self.zadania.append(zadanie)
        if self.kroki:
            wynik = self.kroki.pop(0)(zadanie)
            if isinstance(wynik, BaseException):
                raise wynik
            return wynik
        if zadanie.url.path == SCIEZKA_LISTY:
            tresc = LISTA_BAJTY if zadanie.url.params.get(PARAM_STRONY) == "1" else KONIEC_LISTY
            return httpx.Response(200, content=tresc)
        return httpx.Response(200, content=DOKUMENT_BAJTY)


class Zapis(NullEvents):
    """`Events` z pełną treścią komunikatów i postojów — o nich mówi Z-7."""

    def __init__(self) -> None:
        self.komunikaty: list[str] = []
        self.postoje: list[tuple[float, str]] = []
        self.kolejnosc: list[str] = []

    def on_message(self, text: str) -> None:
        self.komunikaty.append(text)
        self.kolejnosc.append(f"komunikat: {text}")

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        self.postoje.append((seconds, reason))
        self.kolejnosc.append(f"postoj: {reason}")

    @property
    def o_ponowieniu(self) -> list[str]:
        return [k for k in self.komunikaty if "próba" in k]


class Stanowisko:
    """Kanał na prawdziwym `build_http_client` i prawdziwym limiterze z tempem z kontraktu."""

    def __init__(self, *kroki: Krok, kontrakt: Contract = KONTRAKT) -> None:
        self.serwer = SerwerScenariusz(*kroki)
        self.zegar = ZegarTestowy()
        self.zapis = Zapis()
        self.slad = Slad()
        limiter = RateLimiter(
            min_spacing_s=KONTRAKT.tempo.odstep_s,
            windows=[(o.limit, o.sekund) for o in KONTRAKT.tempo.okna],
            clock=self.zegar,
            history=InMemoryHistory(),
            events=self.zapis,
        )
        klient = build_http_client(
            user_agent=UA_TESTOWY,
            allowed=ATLAS_HOSTS,
            transport=httpx.MockTransport(self.serwer),
        )
        self.kanal = AtlasChannel(
            klient, limiter, kontrakt, self.zapis, zegar=self.zegar, slad=self.slad
        )

    @property
    def proby(self) -> list[int]:
        return [w.proba for w in self.slad.wyniki]

    @property
    def statusy(self) -> list[int | None]:
        return [w.status for w in self.slad.wyniki]


# --- rodzina przejściowa: jedna awaria, potem sukces ------------------------------------------


@pytest.mark.parametrize(
    ("awaria", "status_awarii"),
    [
        pytest.param(zerwane, None, id="transport"),
        pytest.param(urwana, 200, id="urwana"),
        pytest.param(status(503), 503, id="serwis_5xx"),
        pytest.param(status(429), 429, id="odmowa_429"),
    ],
)
def test_kazda_klasa_z_z1_po_jednej_awarii_konczy_sie_dokumentem(
    awaria: Krok, status_awarii: int | None
) -> None:
    """Z-1: cztery klasy ponawiane. Dokument przychodzi, a dziennik ma **dwa** wiersze
    z numerami prób 1 i 2 — ten sam adres, więc to jedno żądanie powtórzone, nie dwa różne."""
    st = Stanowisko(awaria)

    surowy = st.kanal.fetch(REF)

    assert surowy.content == DOKUMENT_BAJTY
    assert st.proby == [1, 2]
    assert st.statusy == [status_awarii, 200]
    assert st.slad.wyniki[0].adres == st.slad.wyniki[1].adres
    assert len(st.serwer.zadania) == 2


def test_strona_listy_tez_jest_ponawiana_a_stronicowanie_idzie_dalej() -> None:
    """Z-3: pętla w kanale, bo stan stronicowania żyje w generatorze listy. 5xx na stronie 2
    nie kończy listy — a ponowienie prosi o tę samą stronę, nie o następną."""
    st = Stanowisko(_lista_strona_1, status(502))

    kandydaci = list(st.kanal.list_candidates(ZAKRES))

    assert len(kandydaci) == 100
    strony = [z.url.params.get(PARAM_STRONY) for z in st.serwer.zadania]
    assert strony == ["1", "2", "2"]
    assert st.proby == [1, 1, 2]
    assert st.zapis.o_ponowieniu == ["strona 2 listy: 502 od kanału, próba 2 z 3, czekam 2 s"]


# --- postój: backoff, Retry-After przy 5xx, 429 bez backoffu ----------------------------------


def test_5xx_czeka_backoff_z_kontraktu_przed_kazda_kolejna_proba() -> None:
    """Z-4: postój przed próbą 2 = `podstawa_s`, przed próbą 3 = `podstawa_s * mnoznik`,
    oba przez limiter z powodem „ponowienie” — to jest pierwszy producent `REASON_BACKOFF`."""
    st = Stanowisko(status(503), status(503))

    st.kanal.fetch(REF)

    przed_2, przed_3 = PON.postoj_przed(2), PON.postoj_przed(3)
    assert (przed_2, przed_3) == (PON.podstawa_s, PON.podstawa_s * PON.mnoznik)
    assert st.zegar.sleeps == [przed_2, przed_3]
    assert st.zapis.postoje == [(przed_2, REASON_BACKOFF), (przed_3, REASON_BACKOFF)]
    assert st.proby == [1, 2, 3]


def test_5xx_z_retry_after_dluzszym_od_backoffu_czeka_tyle_o_ile_prosi_serwis() -> None:
    st = Stanowisko(status(503, **{"Retry-After": "30"}))

    st.kanal.fetch(REF)

    assert st.zegar.sleeps == [30.0], "prośba serwisu przy 5xx ma być honorowana (Z-4)"
    assert st.zapis.o_ponowieniu == [f"dokument {REF}: 503 od kanału, próba 2 z 3, czekam 30 s"]


def test_5xx_z_retry_after_krotszym_od_backoffu_nie_skraca_backoffu() -> None:
    """`max(backoff, retry_after)`, nie „retry_after zamiast backoffu”: prośba serwisu może
    postój wyłącznie wydłużyć — ten sam kierunek co `max(cooldown, retry_after)` w limiterze."""
    st = Stanowisko(status(500, **{"Retry-After": "1"}))

    st.kanal.fetch(REF)

    assert st.zegar.sleeps == [PON.postoj_przed(2)]


def test_429_czeka_pelna_blokade_limitera_bez_dodatkowego_backoffu() -> None:
    """Z-4: przy 429 backoff wynosi 0 — pełną blokadę trzyma `note_response`. Postój jest jeden,
    z powodem blokady, a komunikat nie obiecuje sekund, których kanał nie odmierza."""
    st = Stanowisko(status(429))

    st.kanal.fetch(REF)

    assert st.zapis.postoje == [(60.0, REASON_COOLDOWN)], "blokada domyślna limitera, nic więcej"
    assert st.zegar.sleeps == [60.0]
    assert st.zapis.o_ponowieniu == [
        f"dokument {REF}: 429 od kanału, próba 2 z {PON.proby_429}, czekam na limiter"
    ]


def test_429_z_retry_after_czeka_tyle_o_ile_prosi_serwis() -> None:
    st = Stanowisko(status(429, **{"Retry-After": "300"}))

    st.kanal.fetch(REF)

    assert st.zegar.sleeps == [300.0]
    assert st.zapis.postoje == [(300.0, REASON_COOLDOWN)]


def test_drugie_429_pod_rzad_zatrzymuje_bez_trzeciej_proby() -> None:
    """Wariant Z-1 (ADR-0007 §2 pkt 4): `proby_429` = 2, a nie `proby` = 3."""
    st = Stanowisko(status(429), status(429), status(429))

    with pytest.raises(RateLimitError):
        st.kanal.fetch(REF)

    assert st.proby == list(range(1, PON.proby_429 + 1))
    assert len(st.serwer.zadania) == PON.proby_429 < PON.proby


def test_wyczerpane_proby_transportu_rzucaja_ten_sam_wyjatek_z_przyczyna() -> None:
    """Z-10: po wyczerpaniu prób leci `TransportError` jak przed ADR-0007 — z przyczyną
    z `httpx`, bo `_jedna_proba` składa wyjątek bez `raise … from` i musi ją dopiąć ręcznie."""
    st = Stanowisko(*([zerwane] * PON.proby))

    with pytest.raises(TransportError) as blad:
        st.kanal.fetch(REF)

    assert isinstance(blad.value.__cause__, httpx.ConnectError)
    assert st.proby == list(range(1, PON.proby + 1))
    assert [k.split(", czekam")[0] for k in st.zapis.o_ponowieniu] == [
        f"dokument {REF}: zerwane łącze (ConnectError), próba {n} z {PON.proby}"
        for n in range(2, PON.proby + 1)
    ]


def test_komunikat_o_ponowieniu_pada_przed_postojem_ktory_zapowiada() -> None:
    """Z-7 ujście 3: operator czyta „czekam 2 s” zanim zegar stanie, nie po fakcie."""
    st = Stanowisko(status(503))

    st.kanal.fetch(REF)

    assert st.zapis.kolejnosc == [
        f"komunikat: dokument {REF}: 503 od kanału, próba 2 z 3, czekam 2 s",
        f"postoj: {REASON_BACKOFF}",
    ]


# --- klasy nieponawiane --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("krok", "wyjatek"),
    [
        pytest.param(status(400), BadRequestError, id="400"),
        pytest.param(status(401), AuthError, id="401"),
        pytest.param(status(403), AuthError, id="403"),
        pytest.param(status(404), NotFoundError, id="404"),
        pytest.param(status(418), SourceContractBroken, id="status-spoza-kontraktu"),
        pytest.param(
            lambda _: httpx.Response(200, content=b'{"inne": "pole"}'),
            SourceContractBroken,
            id="200-ksztalt-niezgodny",
        ),
    ],
)
def test_klasa_spoza_z1_leci_od_pierwszej_proby_bez_postoju_i_bez_komunikatu(
    krok: Krok, wyjatek: type[Exception]
) -> None:
    """Z-1: trwałe do poprawki w kodzie albo decyzji człowieka — cicha pętla ponowień byłaby
    tą samą awarią co cicha pusta lista, widzianą od strony cudzego serwera."""
    st = Stanowisko(krok)

    with pytest.raises(wyjatek):
        st.kanal.fetch(REF)

    assert len(st.serwer.zadania) == 1
    assert st.proby == [1]
    assert st.zapis.o_ponowieniu == []
    assert st.zegar.sleeps == []


# --- sufit `pod_rzad_max` --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("awaria", "wyjatek"),
    [
        pytest.param(status(503), ServerError, id="serwis_5xx"),
        pytest.param(zerwane, TransportError, id="transport"),
    ],
)
def test_kolejne_zadania_wymagajace_ponowienia_zatrzymuja_kanal_na_suficie(
    awaria: Krok, wyjatek: type[Exception]
) -> None:
    """Z-6: `pod_rzad_max` kolejnych żądań z ponowieniem = serwis leży. Żądanie, które sufit
    osiąga, nie dostaje już drugiej próby, a wyjątek jest klasy, która się wyczerpała."""
    kroki: list[Krok] = [awaria, dobry] * (PON.pod_rzad_max - 1) + [awaria]
    st = Stanowisko(*kroki)

    for n in range(PON.pod_rzad_max - 1):
        st.kanal.fetch(f"{REF}-{n}")
    with pytest.raises(wyjatek, match="pod_rzad_max") as blad:
        st.kanal.fetch(f"{REF}-ostatni")

    assert len(st.serwer.zadania) == len(kroki), "żądanie na suficie nie dostało ponowienia"
    assert st.proby[-1] == 1
    assert isinstance(blad.value.__cause__, wyjatek)
    assert "serwis leży" in str(blad.value)


def test_zadanie_udane_za_pierwszym_razem_zeruje_licznik_pod_rzad() -> None:
    """Sufit liczy **kolejne** żądania: jedno czyste w środku zaczyna liczenie od nowa."""
    potrzebuje = [status(503), dobry]
    kroki = potrzebuje * (PON.pod_rzad_max - 1) + [dobry] + potrzebuje * (PON.pod_rzad_max - 1)
    st = Stanowisko(*kroki)

    for n in range(2 * (PON.pod_rzad_max - 1) + 1):
        st.kanal.fetch(f"{REF}-{n}")

    assert not st.serwer.kroki, "cały scenariusz przeszedł bez zatrzymania"


def test_sukces_dopiero_po_ponowieniu_nie_zeruje_licznika_pod_rzad() -> None:
    """Druga połowa Z-6: zeruje sukces **za pierwszym razem**. Gdyby zerował każdy sukces,
    serwis mrugający na każdym żądaniu nie osiągnąłby sufitu nigdy."""
    kroki: list[Krok] = [status(503), dobry] * PON.pod_rzad_max
    st = Stanowisko(*kroki)

    with pytest.raises(ServerError, match="pod_rzad_max"):
        for n in range(PON.pod_rzad_max):
            st.kanal.fetch(f"{REF}-{n}")


# --- model `Ponowienia` i blok kontraktu ------------------------------------------------------


def test_blok_ponowien_atlasu_jest_tym_z_adr_0007() -> None:
    """ADR-0007 §3.1 — liczby są progami decyzji, więc ich zmiana ma iść przez ADR, nie cicho."""
    assert set(PON.klasy) == {"transport", "urwana", "serwis_5xx", "odmowa_429"}
    assert (PON.proby, PON.proby_429, PON.podstawa_s, PON.mnoznik, PON.pod_rzad_max) == (
        3,
        2,
        2.0,
        3.0,
        3,
    )
    assert "ADR-0007" in PON.zrodlo


def test_postoj_przed_pierwsza_proba_jest_zerowy_a_dalej_rosnie_geometrycznie() -> None:
    pon = PON.model_copy(update={"podstawa_s": 1.5, "mnoznik": 2.0})

    assert [pon.postoj_przed(n) for n in (0, 1, 2, 3, 4)] == [0.0, 0.0, 1.5, 3.0, 6.0]


def _ponowienia(**zmiany: Any) -> dict[str, Any]:
    return {**PON.model_dump(), **zmiany}


@pytest.mark.parametrize(
    "zmiany",
    [
        pytest.param({"proby": 0}, id="proby-zero"),
        pytest.param({"proby_429": 0}, id="proby_429-zero"),
        pytest.param({"podstawa_s": -1.0}, id="podstawa-ujemna"),
        pytest.param({"mnoznik": 0.5}, id="mnoznik-skracajacy"),
        pytest.param({"pod_rzad_max": 0}, id="sufit-zero"),
        pytest.param({"klasy": ["transport", "auth_401"]}, id="klasa-spoza-z1"),
        pytest.param({"nieznane": 1}, id="pole-spoza-modelu"),
    ],
)
def test_model_ponowien_odrzuca_liczby_bez_sensu(zmiany: dict[str, Any]) -> None:
    """Klasa spoza Z-1 w kontrakcie znaczyłaby ponawianie 401 — reguła 16 od strony pliku."""
    with pytest.raises(pydantic.ValidationError):
        Ponowienia.model_validate(_ponowienia(**zmiany))


def test_kontrakt_bez_bloku_ponowien_jest_odrzucany() -> None:
    """ADR-0007 §5: `extra="forbid"` i pole wymagane — kanał bez polityki nie wstaje."""
    surowy = KONTRAKT.model_dump()
    del surowy["ponowienia"]

    with pytest.raises(pydantic.ValidationError, match="ponowienia"):
        Contract.model_validate(surowy)


def test_klasa_wykreslona_z_kontraktu_nie_jest_ponawiana() -> None:
    """Pętla czyta `klasy` z kontraktu, a nie z własnej listy — reguła 17."""
    bez_429 = KONTRAKT.model_copy(
        update={"ponowienia": PON.model_copy(update={"klasy": ["transport", "urwana"]})}
    )
    st = Stanowisko(status(429), kontrakt=bez_429)

    with pytest.raises(RateLimitError):
        st.kanal.fetch(REF)

    assert st.proby == [1]
