"""Wspólny warsztat testów odpornościowych: atrapa serwisu, która potrafi zepsuć się celowo.

Testy odpornościowe pytają o jedno: **co zostaje w bazie i co słyszy operator**, gdy przebieg
nie dochodzi do końca. Materiał i ścieżka są te same co w `tests/test_pipeline.py` — prawdziwy
`build_http_client` z atrapą transportu, prawdziwy adapter Atlasu na złotym pliku listy,
prawdziwy `Store` — bo odporność mierzy się na produkcyjnej drodze albo wcale.

Różnica wobec `Serwer` z `test_pipeline.py` jest jedna i to ona uzasadnia drugą atrapę:
tamta umie przerwać przebieg **jednym** zdarzeniem podanym przy budowie, a tu przedmiotem
pomiaru jest rodzaj awarii — timeout, zerwane połączenie, 5xx, 200 o niezgodnym kształcie,
ucięty JSON — więc reakcja jest funkcją żądania i numeru. Modyfikować cudzą atrapę pod ten
kształt znaczyłoby przepisać ją w miejscu, z którego korzysta osiemnaście istniejących testów.

Ten plik nie ma własnego przedmiotu poza jednym: **sprawdzeniem, że wstrzyknięcie awarii
naprawdę dociera do produkcji**. Atrapa, która „psuje się”, a której awaria gubi się po drodze,
dałaby zielone testy odporności na kodzie, który odporny nie jest — czyli dokładnie tę ciszę,
przed którą broni reszta tego drzewa.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date
from functools import partial
from pathlib import Path

import httpx
import pytest

from kio_tool import pipeline
from kio_tool.clock import Clock
from kio_tool.criteria import Criteria
from kio_tool.docid import SourceName
from kio_tool.errors import TransportError
from kio_tool.httpclient import build_http_client
from kio_tool.progress import Events, NullEvents
from kio_tool.source.contract import load_contract
from kio_tool.store import Store
from tests.wsparcie_sondy import UA_TESTOWY, ZegarTestowy

ZLOTE = Path(__file__).resolve().parent / "examples" / "atlas"
LISTA_BAJTY = (ZLOTE / "lista_20260918T103525Z.json").read_bytes()
LISTA = json.loads(LISTA_BAJTY)
KONTRAKT = load_contract(SourceName("atlas"))
KLUCZ = KONTRAKT.ksztalt.lista.klucz
MA_WIECEJ = KONTRAKT.ksztalt.lista.ma_wiecej
LICZNIK = KONTRAKT.ksztalt.lista.licznik
REKORDY: list[dict[str, object]] = LISTA[KLUCZ]
SLUGI: list[str] = [str(rekord["slug"]) for rekord in REKORDY]
KRYTERIA = Criteria(od=date(2024, 1, 1), do=date(2024, 1, 31))

Reakcja = Callable[[httpx.Request], httpx.Response | BaseException]
"""Co serwis robi z **tym** żądaniem: odpowiada albo wywraca się na łączu.

Odpowiedź i wyjątek są tu jednym typem świadomie: „serwis odmówił” i „połączenie nie doszło”
to dwa różne zdarzenia dla narzędzia, ale jeden wybór dla scenariusza testu.
"""


def strona(rekordy: Sequence[object], *, ma_wiecej: bool, total: int) -> bytes:
    return json.dumps({KLUCZ: list(rekordy), MA_WIECEJ: ma_wiecej, LICZNIK: total}).encode()


def dokument(slug: str) -> bytes:
    """Dokument wymyślony w kształcie z kontraktu — jak w `test_pipeline.py`."""
    return json.dumps(
        {
            "slug": slug,
            "primary_signature": f"(sygnatura wymyslona dla {slug})",
            "signatures": [f"(sygnatura wymyslona dla {slug})"],
            KONTRAKT.ksztalt.dokument.pole_tresci: f"tresc wymyslona {slug}",
        }
    ).encode()


DWIE_STRONY: list[bytes] = [LISTA_BAJTY, strona([], ma_wiecej=False, total=LISTA[LICZNIK])]
"""Sto rekordów na stronie pierwszej i pusta druga — kształt przebiegu z `test_pipeline.py`."""


class SerwisAwaryjny:
    """Atrapa Atlasu, której awarię wybiera test: na którym dokumencie, na której stronie.

    Awaria jest **funkcją**, a nie wartością, bo `httpx.Response` zużywa swój strumień: ten sam
    punkt bywa odpytywany dwa razy (raz przed przerwaniem, raz po wznowieniu) i odpowiedź
    zbudowana raz przy konstrukcji atrapy nie przeżyłaby drugiego odczytu.

    Awaria jest domyślnie **trwała** (ADR-0007 §5.1): po wprowadzeniu ponowień „awaria zdarzyła
    się raz" przestała przerywać przebieg, więc testy obietnicy wznowienia mierzą awarię, która
    nie ustępuje — każda próba tego samego dokumentu albo tej samej strony dostaje ją znowu.
    `jednorazowa=True` psuje wyłącznie pierwszą próbę: to jest rodzina testów ponowień.
    """

    def __init__(
        self,
        strony: Sequence[bytes] | None = None,
        *,
        na_dokumencie: int | None = None,
        na_stronie: int | None = None,
        reakcja: Reakcja | None = None,
        jednorazowa: bool = False,
    ) -> None:
        self.strony = list(strony) if strony is not None else list(DWIE_STRONY)
        self.na_dokumencie = na_dokumencie
        self.na_stronie = na_stronie
        self.reakcja: Reakcja = reakcja or (lambda _: httpx.ConnectError("siec znikla (wymyslone)"))
        self.zadania: list[httpx.Request] = []
        self.dokumentow = 0
        self.awarii = 0
        self.jednorazowa = jednorazowa
        self._slug_awarii: str | None = None
        self._rozne_dokumenty: list[str] = []

    def __call__(self, zadanie: httpx.Request) -> httpx.Response:
        self.zadania.append(zadanie)
        if zadanie.url.path == KONTRAKT.punkty.lista:
            numer = int(zadanie.url.params[KONTRAKT.parametry_listy.strona])
            if numer == self.na_stronie and not (self.jednorazowa and self.awarii):
                return self._awaria(zadanie)
            return httpx.Response(200, content=self.strony[numer - 1])
        self.dokumentow += 1
        slug = zadanie.url.path.rsplit("/", 1)[1]
        if slug not in self._rozne_dokumenty:
            self._rozne_dokumenty.append(slug)
            if len(self._rozne_dokumenty) == self.na_dokumencie:
                self._slug_awarii = slug
                return self._awaria(zadanie)
        elif slug == self._slug_awarii and not self.jednorazowa:
            return self._awaria(zadanie)
        return httpx.Response(200, content=dokument(slug))

    def _awaria(self, zadanie: httpx.Request) -> httpx.Response:
        self.awarii += 1
        wynik = self.reakcja(zadanie)
        if isinstance(wynik, BaseException):
            raise wynik
        return wynik

    @property
    def strony_zadane(self) -> list[str]:
        return [
            z.url.params[KONTRAKT.parametry_listy.strona]
            for z in self.zadania
            if z.url.path == KONTRAKT.punkty.lista
        ]


def uruchom(
    store: Store,
    serwis: SerwisAwaryjny,
    *,
    zgoda: bool = True,
    kryteria: Criteria = KRYTERIA,
    zegar: Clock | None = None,
    events: Events | None = None,
) -> pipeline.Podsumowanie:
    """`pobierz` prawdziwą ścieżką: prawdziwa fabryka klienta, atrapa wyłącznie jako transport."""
    return pipeline.pobierz(
        "atlas",
        kryteria,
        store,
        events or NullEvents(),
        zgoda=zgoda,
        user_agent=UA_TESTOWY,
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(serwis)),
        zegar=zegar or ZegarTestowy(),
    )


def jedyny_przebieg(store: Store) -> str:
    """Identyfikator jedynego przebiegu w bazie — asercja, że jest dokładnie jeden."""
    wiersze = store._conn.execute("SELECT run_id FROM runs").fetchall()
    assert len(wiersze) == 1, f"spodziewano się jednego przebiegu, jest {len(wiersze)}"
    return str(wiersze[0][0])


def statusy_zadan(store: Store) -> list[int | None]:
    """Kolumna `status` dziennika żądań w kolejności zapisu; `None` = żądanie, które nie doszło."""
    kursor = store._conn.execute("SELECT status FROM requests_log ORDER BY rowid")
    return [wiersz[0] for wiersz in kursor]


@pytest.fixture
def store() -> Store:
    return Store.open(":memory:", clock=ZegarTestowy())


@pytest.fixture(autouse=True)
def _bez_klucza_ze_srodowiska(monkeypatch: pytest.MonkeyPatch) -> None:
    """Klucz Atlasu z maszyny dewelopera nie ma prawa wejść do żądania atrapy."""
    monkeypatch.delenv(KONTRAKT.tempo.klucz_api.zmienna, raising=False)


# --- samosprawdzenie warsztatu ---------------------------------------------------------------


def test_awaria_wstrzyknieta_w_atrape_naprawde_dociera_do_produkcji(store: Store) -> None:
    """Bez tego testu cały plik odporności mógłby być zielony na atrapie, która nic nie psuje.

    Mierzone są trzy rzeczy naraz: wyjątek atrapy dochodzi do `pipeline` przetłumaczony na
    taksonomię narzędzia, licznik awarii atrapy rośnie (czyli scenariusz naprawdę się odpalił),
    a żądania przed awarią poszły — więc awaria padła **w środku** przebiegu, a nie przed nim.
    """
    serwis = SerwisAwaryjny(na_dokumencie=3)

    with pytest.raises(TransportError):
        uruchom(store, serwis)

    proby = KONTRAKT.ponowienia.proby
    assert serwis.awarii == proby, "awaria trwała dostała każdą próbę z `ponowienia.proby`"
    assert serwis.dokumentow == 2 + proby, "awaria padła na trzecim dokumencie, nie wcześniej"
    assert store.count("documents") == 2, "dwa dokumenty sprzed awarii są w bazie"


def test_atrapa_bez_scenariusza_awarii_konczy_przebieg_normalnie(store: Store) -> None:
    """Druga połowa samosprawdzenia: atrapa domyślnie **nie** psuje niczego.

    Atrapa psująca zawsze dałaby zielone „przerwany przebieg da się wznowić” także wtedy, gdyby
    wznowienie nie działało — bo każdy przebieg byłby przerwany.
    """
    serwis = SerwisAwaryjny()

    wynik = uruchom(store, serwis)

    assert serwis.awarii == 0
    assert (wynik.status, wynik.nowych) == ("zakonczony", len(SLUGI))
    assert store.count("documents") == len(SLUGI)
