"""Test dymny adaptera `atlas` na złotych plikach pomiaru 3a.

Trzy reguły mają tu swoich obserwatorów:

- **17, część behawioralna**: adapter, który dostanie 200 z kształtem niezgodnym z kontraktem,
  rzuca `SourceContractBroken`, nie zwraca pustej listy. Złotym plikiem jest surowa odpowiedź
  zapisana przez pomiar 3a (ADR-0005 Z-6), a `*.compare.json` obok mówi, co adapter ma z niej
  wyczytać — asercje biorą oczekiwania stamtąd, nie z pamięci.
- **20 (ADR-0005 Z-10)**: kasety kontra wstrzyknięty transport. Atrapa jedzie jako `transport=`
  przez **prawdziwy** `build_http_client`, więc każde żądanie przechodzi przez bramkę wyjścia
  i nagłówek tożsamości — dokładnie tą ścieżką, którą pojedzie produkcja. Jeśli to wystarcza
  (a wystarcza), `respx` wypada z zależności deweloperskich w osobnym kroku.
- **22**: adapter nie zna adresów — bierze je z kontraktu; ten test też bierze je stamtąd, żeby
  nie być drugą listą.

Materiał spoza złotych plików (druga strona listy, dokumenty pod innymi slugami, nagłówki
budżetu) jest **wymyślony** i tak nazwany: sprawdza adapter, nie źródło.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import httpx
import pytest

from kio_tool.config import ATLAS_HOSTS, mask_tokens
from kio_tool.docid import SourceName
from kio_tool.errors import (
    AuthError,
    NotFoundError,
    PagingRunawayError,
    RateLimitError,
    ServerError,
    SourceContractBroken,
    TransportError,
)
from kio_tool.httpclient import build_http_client
from kio_tool.logbook import Wynik
from kio_tool.progress import NullEvents
from kio_tool.ratelimit import REASON_BUDGET, REASON_COOLDOWN, InMemoryHistory, RateLimiter
from kio_tool.source.atlas.channel import AtlasChannel
from kio_tool.source.contract import load_contract
from kio_tool.source.protocol import Candidate, Scope
from tests.wsparcie_sondy import KLUCZ_TESTOWY, UA_TESTOWY, ZegarTestowy

ZLOTE = Path(__file__).resolve().parent / "examples" / "atlas"
LISTA_BAJTY = (ZLOTE / "lista_20260918T103525Z.json").read_bytes()
DOKUMENT_BAJTY = (ZLOTE / "dokument_20260918T103526Z.json").read_bytes()
LISTA_PORA = json.loads((ZLOTE / "lista_20260918T103525Z.compare.json").read_text("utf-8"))
DOKUMENT_PORA = json.loads((ZLOTE / "dokument_20260918T103526Z.compare.json").read_text("utf-8"))

KONTRAKT = load_contract(SourceName("atlas"))
SCIEZKA_LISTY = KONTRAKT.punkty.lista
SCIEZKA_DOKUMENTU = KONTRAKT.punkty.dokument
PARAM_STRONY = KONTRAKT.parametry_listy.strona
ZAKRES = Scope(date(2024, 1, 1), date(2024, 1, 31))

KONIEC_LISTY = json.dumps(
    {KONTRAKT.ksztalt.lista.klucz: [], KONTRAKT.ksztalt.lista.ma_wiecej: False, "page": 2}
).encode()
"""Druga strona — wymyślona: pusta lista z `has_more: false`. Zakres bez dalszych rekordów."""


class Serwer:
    """Atrapa Atlasu nad złotymi plikami. Strona 1 = złoty plik, strona 2 = koniec listy."""

    def __init__(
        self,
        *,
        strona_1: bytes = LISTA_BAJTY,
        strona_2: bytes = KONIEC_LISTY,
        dokument: bytes = DOKUMENT_BAJTY,
        status_dokumentu: int = 200,
        naglowki: Mapping[str, str] | None = None,
        blad: BaseException | None = None,
    ) -> None:
        self.strona_1 = strona_1
        self.strona_2 = strona_2
        self.dokument = dokument
        self.status_dokumentu = status_dokumentu
        self.naglowki = dict(naglowki or {})
        self.blad = blad
        self.zadania: list[httpx.Request] = []

    def __call__(self, zadanie: httpx.Request) -> httpx.Response:
        self.zadania.append(zadanie)
        if self.blad is not None:
            raise self.blad
        sciezka = zadanie.url.path
        if sciezka == SCIEZKA_LISTY:
            strona = zadanie.url.params.get(PARAM_STRONY)
            tresc = self.strona_1 if strona == "1" else self.strona_2
            return httpx.Response(200, content=tresc, headers=self.naglowki)
        if sciezka.startswith(SCIEZKA_DOKUMENTU + "/"):
            return httpx.Response(
                self.status_dokumentu, content=self.dokument, headers=self.naglowki
            )
        raise AssertionError(f"ścieżka spoza scenariusza: {sciezka}")

    @property
    def sciezki(self) -> list[str]:
        return [z.url.path for z in self.zadania]


class Slad:
    """`SladZadan` zbierający wyniki do listy."""

    def __init__(self) -> None:
        self.wyniki: list[Wynik] = []

    def zanotuj(self, wynik: Wynik) -> Wynik:
        self.wyniki.append(wynik)
        return wynik


class Puls(NullEvents):
    """`Events` zapisujący, co adapter zgłosił."""

    def __init__(self) -> None:
        self.zdarzenia: list[tuple[str, object]] = []

    def on_request(self, endpoint: str, status: int, elapsed_s: float) -> None:
        self.zdarzenia.append(("on_request", status))

    def on_page(self, page_index: int, candidates: int, total: int | None) -> None:
        self.zdarzenia.append(("on_page", (page_index, candidates, total)))

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        self.zdarzenia.append(("on_wait", reason))

    def on_message(self, text: str) -> None:
        self.zdarzenia.append(("on_message", text))


def zbuduj(
    serwer: Serwer,
    *,
    puls: Puls | None = None,
    slad: Slad | None = None,
    klucz_api: str | None = None,
) -> tuple[AtlasChannel, ZegarTestowy]:
    zegar = ZegarTestowy()
    klient = build_http_client(
        user_agent=UA_TESTOWY, allowed=ATLAS_HOSTS, transport=httpx.MockTransport(serwer)
    )
    limiter = RateLimiter(
        min_spacing_s=KONTRAKT.tempo.odstep_s,
        windows=[(o.limit, o.sekund) for o in KONTRAKT.tempo.okna],
        clock=zegar,
        history=InMemoryHistory(),
        events=puls,
    )
    kanal = AtlasChannel(
        klient, limiter, KONTRAKT, puls, zegar=zegar, slad=slad, klucz_api=klucz_api
    )
    return kanal, zegar


# --- listowanie na złotym pliku ---------------------------------------------------------------


def test_lista_ze_zlotego_pliku_daje_stu_kandydatow_zgodnych_z_para() -> None:
    serwer = Serwer()
    kanal, _ = zbuduj(serwer)

    kandydaci = list(kanal.list_candidates(ZAKRES))

    assert len(kandydaci) == LISTA_PORA["rekordow"] == 100
    pierwszy = kandydaci[0]
    assert pierwszy.source_ref == LISTA_PORA["pierwszy"]["slug"]
    assert pierwszy.sygnatury == tuple(LISTA_PORA["pierwszy"]["signatures"])
    assert pierwszy.data_wydania == LISTA_PORA["pierwszy"]["ruling_date"], (
        "`ruling_date` ma przyjść tak, jak jest — także gdy jest błędne (reguła 19)"
    )
    assert pierwszy.strona == 1
    assert kandydaci[-1].source_ref == LISTA_PORA["ostatni_slug"]


def test_lista_stronicuje_dopoki_has_more_i_pyta_o_zakres_dat() -> None:
    """`has_more: true` na stronie 1 (para złotego pliku) wymusza drugie żądanie o stronę 2."""
    serwer = Serwer()
    kanal, _ = zbuduj(serwer)

    list(kanal.list_candidates(ZAKRES))

    assert serwer.sciezki == [SCIEZKA_LISTY, SCIEZKA_LISTY]
    strony = [z.url.params.get(PARAM_STRONY) for z in serwer.zadania]
    assert strony == ["1", "2"]
    p = KONTRAKT.parametry_listy
    parametry = serwer.zadania[0].url.params
    assert parametry[p.od] == "2024-01-01" and parametry[p.do] == "2024-01-31"
    assert parametry[p.sortowanie] == p.sortowanie_wartosc
    assert parametry[p.na_strone] == str(KONTRAKT.strony.na_strone)
    assert all(z.headers["User-Agent"] == UA_TESTOWY for z in serwer.zadania), (
        "atrapa jedzie przez prawdziwy `build_http_client`, więc niesie nagłówek tożsamości"
    )


def test_wznowienie_prosi_o_liste_od_podanej_strony() -> None:
    serwer = Serwer()
    kanal, _ = zbuduj(serwer)

    kandydaci = list(kanal.list_candidates(ZAKRES, od_strony=2))

    assert kandydaci == []
    assert [z.url.params.get(PARAM_STRONY) for z in serwer.zadania] == ["2"]


def test_zakres_bez_orzeczen_konczy_sie_pusto_bez_bledu() -> None:
    """Pusta lista pod właściwym kluczem jest wynikiem zapytania, nie złamanym kontraktem."""
    kanal, _ = zbuduj(Serwer(strona_1=KONIEC_LISTY))

    assert list(kanal.list_candidates(ZAKRES)) == []


def test_lista_zglasza_strone_i_zadanie_przez_events_zanim_odda_kandydatow() -> None:
    puls = Puls()
    kanal, _ = zbuduj(Serwer(), puls=puls)
    iterator = kanal.list_candidates(ZAKRES)

    next(iterator)

    assert ("on_request", 200) in puls.zdarzenia
    assert ("on_page", (1, 100, LISTA_PORA["total"])) in puls.zdarzenia, (
        "`on_page` idzie przed pierwszym kandydatem, bo `pipeline` czyta stamtąd `total` "
        "do rozstrzygnięcia o zgodzie"
    )


# --- reguła 17: status zgodny, kształt niezgodny → wyjątek, nie pusta lista ------------------


def test_lista_pod_innym_kluczem_to_zlamany_kontrakt_a_nie_pusta_lista() -> None:
    inna = LISTA_BAJTY.replace(b'"data"', b'"items"', 1)
    slad = Slad()
    kanal, _ = zbuduj(Serwer(strona_1=inna), slad=slad)

    with pytest.raises(SourceContractBroken, match="kszta"):
        list(kanal.list_candidates(ZAKRES))

    assert len(slad.wyniki) == 1 and slad.wyniki[0].ksztalt_zgodny is False, (
        "żądanie już poszło do cudzego serwisu, więc ślad ma o nim mówić — także przy wyjątku"
    )


def test_lista_bez_has_more_to_zlamany_kontrakt() -> None:
    bez = LISTA_BAJTY.replace(b'"has_more"', b'"has_next"', 1)
    kanal, _ = zbuduj(Serwer(strona_1=bez))

    with pytest.raises(SourceContractBroken, match=KONTRAKT.ksztalt.lista.ma_wiecej):
        list(kanal.list_candidates(ZAKRES))


def test_rekord_bez_sluga_to_zlamany_kontrakt() -> None:
    bez = json.dumps(
        {
            KONTRAKT.ksztalt.lista.klucz: [{"primary_signature": "(napis wymyslony)"}],
            KONTRAKT.ksztalt.lista.ma_wiecej: False,
        }
    ).encode()
    kanal, _ = zbuduj(Serwer(strona_1=bez))

    with pytest.raises(SourceContractBroken, match=KONTRAKT.ksztalt.lista.rekord.referencja):
        list(kanal.list_candidates(ZAKRES))


def test_bot_check_ze_statusem_200_nie_jest_lista() -> None:
    kanal, _ = zbuduj(Serwer(strona_1=b"<html><body>Weryfikacja przegladarki</body></html>"))

    with pytest.raises(SourceContractBroken):
        list(kanal.list_candidates(ZAKRES))


def test_lista_ktora_nigdy_nie_gasnie_konczy_sie_paging_runaway() -> None:
    kanal, _ = zbuduj(Serwer(strona_2=LISTA_BAJTY))

    with pytest.raises(PagingRunawayError, match=str(KONTRAKT.strony.max_stron)):
        list(kanal.list_candidates(ZAKRES))


# --- pobranie dokumentu na złotym pliku ------------------------------------------------------


def test_fetch_zwraca_bajty_o_skrocie_ze_zrodlo_md() -> None:
    serwer = Serwer()
    kanal, _ = zbuduj(serwer)
    slug = DOKUMENT_PORA["slug"]

    surowy = kanal.fetch(slug)

    assert surowy.content == DOKUMENT_BAJTY
    assert surowy.sha256 == DOKUMENT_PORA["sha256"]
    assert hashlib.sha256(surowy.content).hexdigest() == surowy.sha256
    assert surowy.source_ref == slug
    assert serwer.sciezki == [f"{SCIEZKA_DOKUMENTU}/{slug}"]
    assert surowy.fetched_at.endswith("Z")


def test_dokument_bez_pol_wymaganych_to_zlamany_kontrakt() -> None:
    kanal, _ = zbuduj(Serwer(dokument=b'{"error": "not found"}'))

    with pytest.raises(SourceContractBroken):
        kanal.fetch(DOKUMENT_PORA["slug"])


@pytest.mark.parametrize(
    ("slug", "fragment"),
    [("..", "kropkowym"), (".", "kropkowym"), ("a/b?c=d", "spoza"), ("", "spoza")],
    ids=["dwie-kropki", "kropka", "ukosnik-i-pytajnik", "pusty"],
)
def test_slug_ktory_zmienilby_punkt_koncowy_nie_idzie_do_adresu(slug: str, fragment: str) -> None:
    """Ta sama kontrola co w sondzie (`httpclient.powod_odrzucenia_segmentu`): zero żądań."""
    serwer = Serwer()
    kanal, _ = zbuduj(serwer)

    with pytest.raises(SourceContractBroken, match=fragment):
        kanal.fetch(slug)

    assert serwer.zadania == []


# --- limiter: nagłówki budżetu, Retry-After, statusy odmowy ----------------------------------


def test_niski_budzet_z_naglowkow_hamuje_limiter_do_resetu() -> None:
    """`X-RateLimit-Remaining` poniżej rezerwy z resetem w przyszłości: następne żądanie czeka
    do resetu, z powodem `budzet_kanalu` — `note_budget` dostaje pierwszego wywołującego."""
    puls = Puls()
    n = KONTRAKT.tempo.naglowki_budzetu
    zegar_podgladu = ZegarTestowy()
    naglowki = {n.pozostalo: "3", n.reset: str(zegar_podgladu.wall() + 120)}
    kanal, zegar = zbuduj(Serwer(naglowki=naglowki), puls=puls)

    list(kanal.list_candidates(ZAKRES))

    assert ("on_wait", REASON_BUDGET) in puls.zdarzenia
    assert any(sen >= 100 for sen in zegar.sleeps), zegar.sleeps


def test_reset_jako_sekundy_do_resetu_tez_hamuje() -> None:
    """Postać `X-RateLimit-Reset` jest niezmierzona (kontrakt), więc adapter czyta obie."""
    puls = Puls()
    n = KONTRAKT.tempo.naglowki_budzetu
    kanal, zegar = zbuduj(Serwer(naglowki={n.pozostalo: "0", n.reset: "90"}), puls=puls)

    list(kanal.list_candidates(ZAKRES))

    assert ("on_wait", REASON_BUDGET) in puls.zdarzenia
    assert any(80 <= sen <= 90 for sen in zegar.sleeps), zegar.sleeps


def test_budzet_powyzej_rezerwy_nie_hamuje() -> None:
    puls = Puls()
    n = KONTRAKT.tempo.naglowki_budzetu
    kanal, zegar = zbuduj(Serwer(naglowki={n.pozostalo: "400", n.reset: "60"}), puls=puls)

    list(kanal.list_candidates(ZAKRES))

    assert ("on_wait", REASON_BUDGET) not in puls.zdarzenia
    assert all(sen <= KONTRAKT.tempo.odstep_s for sen in zegar.sleeps)


def test_retry_after_przy_429_idzie_do_limitera_i_przebieg_staje() -> None:
    """429 kończy przebieg `RateLimitError` (reguła 16: nie omijamy), a `Retry-After` jest
    honorowany dosłownie: kolejne żądanie czeka pełne 300 s, nie własne 60 s blokady."""
    puls = Puls()
    serwer = Serwer(status_dokumentu=429, naglowki={"Retry-After": "300"})
    kanal, zegar = zbuduj(serwer, puls=puls)

    with pytest.raises(RateLimitError):
        kanal.fetch(DOKUMENT_PORA["slug"])
    with pytest.raises(RateLimitError):
        kanal.fetch(DOKUMENT_PORA["slug"])

    assert ("on_wait", REASON_COOLDOWN) in puls.zdarzenia
    assert any(sen >= 299 for sen in zegar.sleeps), zegar.sleeps


@pytest.mark.parametrize(
    ("status", "wyjatek"),
    [(401, AuthError), (403, AuthError), (404, NotFoundError), (500, ServerError)],
)
def test_status_spoza_kontraktu_konczy_sie_wlasciwym_wyjatkiem(
    status: int, wyjatek: type[Exception]
) -> None:
    slad = Slad()
    kanal, _ = zbuduj(Serwer(status_dokumentu=status), slad=slad)

    with pytest.raises(wyjatek):
        kanal.fetch(DOKUMENT_PORA["slug"])

    assert [w.status for w in slad.wyniki] == [status]


def test_blad_transportu_zostawia_slad_i_jest_wznawialny() -> None:
    slad = Slad()
    kanal, _ = zbuduj(Serwer(blad=httpx.ConnectError("odmowa polaczenia (wymyslona)")), slad=slad)

    with pytest.raises(TransportError):
        kanal.fetch(DOKUMENT_PORA["slug"])

    assert len(slad.wyniki) == 1
    assert slad.wyniki[0].status is None and "ConnectError" in slad.wyniki[0].uwaga


# --- klucz API i reguła 19 --------------------------------------------------------------------


def test_klucz_api_idzie_w_naglowku_z_kontraktu() -> None:
    serwer = Serwer()
    kanal, _ = zbuduj(serwer, klucz_api=KLUCZ_TESTOWY)

    kanal.fetch(DOKUMENT_PORA["slug"])

    assert serwer.zadania[0].headers[KONTRAKT.tempo.klucz_api.naglowek] == KLUCZ_TESTOWY


def test_bez_klucza_naglowek_nie_idzie() -> None:
    serwer = Serwer()
    kanal, _ = zbuduj(serwer)

    kanal.fetch(DOKUMENT_PORA["slug"])

    assert KONTRAKT.tempo.klucz_api.naglowek not in serwer.zadania[0].headers


def test_slad_niesie_pelny_adres_z_parametrami_a_sekret_da_sie_zamaskowac() -> None:
    """Dwa żądania listy różnią się tylko `page` — ślad bez parametrów nie odróżniałby ich."""
    slad = Slad()
    kanal, _ = zbuduj(Serwer(), slad=slad)

    list(kanal.list_candidates(ZAKRES))

    adresy = [w.adres for w in slad.wyniki]
    assert len(adresy) == 2 and adresy[0] != adresy[1]
    assert all(f"{PARAM_STRONY}=" in adres for adres in adresy)
    assert mask_tokens(adresy[0]) == adresy[0], "adres listy nie niesie sekretu, więc nic do maski"


def test_kandydat_nie_ma_miejsca_na_pola_odrzucone() -> None:
    """Reguła 19 (ADR-0005 Z-5) strukturalnie: `Candidate` nie niesie pól z `pola_odrzucone`,
    więc nie wchodzą do tabel pochodnych nie dzięki czyjejś pamięci, tylko dlatego, że nie ma
    pola, którym mogłyby pójść. Surowe bajty idą osobno, w całości (`fetch`)."""
    pola_kandydata = set(Candidate.__dataclass_fields__)
    odrzucone = {p.pole for p in KONTRAKT.pola_odrzucone}

    assert odrzucone, "kontrakt Atlasu deklaruje pola odrzucone (thesis, thesis_snippet)"
    assert not (pola_kandydata & odrzucone)
    assert pola_kandydata == {"source_ref", "sygnatury", "data_wydania", "strona"}


def test_nazwa_kanalu_pochodzi_z_kontraktu_i_jest_kanoniczna() -> None:
    kanal, _ = zbuduj(Serwer())

    assert kanal.name == KONTRAKT.kanal == "atlas"
    assert kanal.hosty == ATLAS_HOSTS
