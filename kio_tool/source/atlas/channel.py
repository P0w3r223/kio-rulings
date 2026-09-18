"""Adapter kanału `atlas` — pierwszy kanał masowy (ADR-0004 §6, ADR-0005 Z-3).

Dwie operacje o różnym koszcie (architektura 4.3): `list_candidates` stronicuje listę
`GET /api/kio` po numerze strony, dopóki serwis mówi `has_more`; `fetch` czyta jeden dokument
`GET /api/kio/{slug}`. Adresy i nazwy pól pochodzą wyłącznie z `contract.yaml` obok (reguła 22)
— ten docstring jest jedynym miejscem w pliku, w którym wolno je zapisać.

Czego ten moduł nie robi, i to są reguły granic, nie oszczędność: nie buduje klienta HTTP
(reguła 11 — klient jest wstrzyknięty, powstaje w `httpclient.build_http_client` przez
`pipeline`), nie zna bazy (reguła 2 — ślad żądań dostaje jako protokół `SladZadan`), nie rysuje
(reguła 4 — postęp idzie przez `Events`). Bajty odpowiedzi wracają **takie, jakie przyszły**
(reguła 19, ADR-0005 Z-5): pola o nieznanym pochodzeniu odcina `contract.yaml` (`pola_odrzucone`)
na wyjściu z kanału — `Candidate` ich nie niesie — a nie mutacja odpowiedzi przed zapisem.

Odpowiedź o statusie zgodnym z kontraktem, ale o kształcie niezgodnym, rzuca
`SourceContractBroken` (reguła 17) — po zapisaniu wiersza w śladzie żądań, bo żądanie już
poszło do cudzego serwisu i ślad ma o tym mówić, także gdy odpowiedź jest nie do poznania.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterator, Mapping
from typing import ClassVar

import httpx

from ...clock import Clock, SystemClock, utc_iso
from ...config import ATLAS_HOSTS
from ...docid import SourceName, normalize_source_name
from ...errors import (
    AuthError,
    BadRequestError,
    ConfigError,
    NotFoundError,
    PagingRunawayError,
    RateLimitError,
    ServerError,
    SourceContractBroken,
    TransportError,
)
from ...httpclient import NAGLOWEK_RETRY_AFTER, parse_retry_after, powod_odrzucenia_segmentu
from ...ksztalt import OcenaKsztaltu, json_z_rekordami, json_ze_slownikiem
from ...logbook import Wynik
from ...progress import Events, NullEvents
from ...ratelimit import RateLimiter
from ..contract import Contract
from ..protocol import BezSladu, Candidate, RawDocument, Scope, SladZadan

PROG_EPOCH = 1_000_000_000.0
"""Od jakiej wartości `X-RateLimit-Reset` czytamy jako znacznik epoch, a nie sekundy do resetu.

Postać nagłówka jest **niezmierzona** (kontrakt, `tempo.zrodlo`): sonda zapisuje treść, nie
nagłówki. Obie postaci są w użyciu u różnych dostawców, a pomylenie ich w jedną stronę daje
postój do roku 1970 (zero), w drugą — do roku 2001 od teraz. Próg 10^9 rozdziela je bez
niejednoznaczności: 10^9 s to 31 lat, więc żaden reset „za N sekund" go nie przekroczy,
a 10^9 jako epoch to 2001-09-09, więc żaden prawdziwy znacznik nie jest mniejszy.
"""

METODA = "GET"


class AtlasChannel:
    """Implementacja `Channel` dla Atlasu; konstruktor bierze gotowe zależności, nie buduje ich."""

    hosty: ClassVar[frozenset[str]] = ATLAS_HOSTS
    """Bramka wyjścia tego kanału — `pipeline` podaje ją do `build_http_client(allowed=…)`.

    Zbiór stoi w `config.py`, nie tutaj, bo jest listą hostów jednego kanału z komentarzem
    o tym, dlaczego nie ma sumy; adapter niosący `X-Api-Key` nie ma prawa wyjść gdzie indziej.
    """

    def __init__(
        self,
        klient: httpx.Client,
        limiter: RateLimiter,
        contract: Contract,
        events: Events | None = None,
        *,
        zegar: Clock | None = None,
        slad: SladZadan | None = None,
        klucz_api: str | None = None,
    ) -> None:
        self._klient = klient
        self._limiter = limiter
        self._k = contract
        self._events: Events = events or NullEvents()
        self._zegar: Clock = zegar or SystemClock()
        self._slad: SladZadan = slad or BezSladu()
        self.name: SourceName = normalize_source_name(contract.kanal)
        # Pusta strona jest dozwolona: zakres dat bez orzeczeń to poprawny wynik, nie złamany
        # kontrakt (docstring `json_z_rekordami`). Lista pod innym kluczem nadal nim jest.
        self._ocena_rekordow = json_z_rekordami(contract.ksztalt.lista.klucz, pusta_dozwolona=True)
        self._ocena_dokumentu = json_ze_slownikiem(*contract.ksztalt.dokument.pola_wymagane)
        self._naglowki: dict[str, str] = {}
        if klucz_api:
            self._naglowki[contract.tempo.klucz_api.naglowek] = klucz_api

    # ------------------------------------------------------------------------ listowanie

    def list_candidates(self, scope: Scope, *, od_strony: int = 1) -> Iterator[Candidate]:
        k = self._k
        strona = od_strony
        while True:
            if strona > k.strony.max_stron:
                raise PagingRunawayError(
                    f"Lista kanału {self.name!r} nie skończyła się po {k.strony.max_stron} "
                    f"stronach — pole `{k.ksztalt.lista.ma_wiecej}` nie zgasło. To jest pętla, "
                    "nie zbiór; twardy limit stoi w `contract.yaml` (`strony.max_stron`)."
                )
            params = self._parametry(scope, strona)
            odpowiedz = self._zadanie(
                k.baza + k.punkty.lista,
                nazwa=k.punkty.lista,
                params=params,
                ocena=self._ocena_listy,
            )
            dane = json.loads(odpowiedz.content)
            rekordy: list[object] = dane[k.ksztalt.lista.klucz]
            licznik = dane.get(k.ksztalt.lista.licznik)
            # `on_page` **przed** kandydatami: `pipeline` czyta stąd liczbę dokumentów w zakresie
            # i rozstrzyga o zgodzie, zanim wyśle pierwsze żądanie po dokument.
            self._events.on_page(
                strona, len(rekordy), licznik if isinstance(licznik, int) else None
            )
            for rekord in rekordy:
                yield self._kandydat(rekord, strona)
            if not dane.get(k.ksztalt.lista.ma_wiecej):
                return
            strona += 1

    def _parametry(self, scope: Scope, strona: int) -> dict[str, str | int]:
        """Parametry listy z kontraktu: daty tylko podane, filtry przetłumaczone przez
        `parametry_listy.filtry`. Filtr bez wiersza w kontrakcie jest błędem konfiguracji
        **przed** żądaniem — nie parametrem wysłanym pod zgadywaną nazwą."""
        p = self._k.parametry_listy
        params: dict[str, str | int] = {}
        if scope.od is not None:
            params[p.od] = scope.od.isoformat()
        if scope.do is not None:
            params[p.do] = scope.do.isoformat()
        for pole, wartosc in sorted(scope.filtry.items()):
            nazwa = p.filtry.get(pole)
            if nazwa is None:
                raise ConfigError(
                    f"Kanał {self.name!r} nie zna filtru {pole!r}; kontrakt "
                    f"(`parametry_listy.filtry`) tłumaczy: {', '.join(sorted(p.filtry)) or '—'}."
                )
            params[nazwa] = wartosc
        params[p.sortowanie] = p.sortowanie_wartosc
        params[p.strona] = strona
        params[p.na_strone] = self._k.strony.na_strone
        return params

    def _ocena_listy(self, tresc: bytes) -> OcenaKsztaltu:
        """Ocena listy z kontraktu plus pole `ma_wiecej`, bez którego nie wiadomo, czy jest
        następna strona — brak tego pola przy statusie 200 jest dokładnie tym, co reguła 17
        każe rzucić, a nie przemilczeć jako „koniec listy"."""
        ocena = self._ocena_rekordow(tresc)
        if not ocena.zgodny:
            return ocena
        dane = json.loads(tresc)
        nazwa = self._k.ksztalt.lista.ma_wiecej
        if not isinstance(dane, dict) or not isinstance(dane.get(nazwa), bool):
            return OcenaKsztaltu(
                zgodny=False,
                uwaga=(
                    f"{ocena.uwaga}; brak pola `{nazwa}` typu bool — kontrakt mówi, "
                    "że lista je niesie"
                ),
            )
        return ocena

    def _kandydat(self, rekord: object, strona: int) -> Candidate:
        pola = self._k.ksztalt.lista.rekord
        if not isinstance(rekord, dict):
            raise SourceContractBroken(
                f"Rekord listy kanału {self.name!r} nie jest słownikiem ({type(rekord).__name__})."
            )
        ref = rekord.get(pola.referencja)
        if not isinstance(ref, str) or not ref:
            raise SourceContractBroken(
                f"Rekord listy kanału {self.name!r} nie niesie pola `{pola.referencja}` — "
                "kontrakt (`ksztalt.lista.zrodlo`) mówi, że niesie je każdy rekord."
            )
        sygnatury = rekord.get(pola.sygnatury)
        lista = (
            tuple(s for s in sygnatury if isinstance(s, str)) if isinstance(sygnatury, list) else ()
        )
        if not lista:
            # ADR-0001 2.1: `signatures` z `primary_signature` jako pierwszą; gdy listy nie ma,
            # sama główna jest lepsza niż pusty zbiór — sygnatura jest etykietą, nie tożsamością.
            glowna = rekord.get(pola.sygnatura_glowna)
            lista = (glowna,) if isinstance(glowna, str) and glowna else ()
        data = rekord.get(pola.data_wydania)
        return Candidate(
            source_ref=ref,
            sygnatury=lista,
            data_wydania=data if isinstance(data, str) else None,
            strona=strona,
        )

    # -------------------------------------------------------------------------- pobranie

    def fetch(self, ref: str) -> RawDocument:
        powod = powod_odrzucenia_segmentu(ref)
        if powod:
            raise SourceContractBroken(
                f"Referencja z kanału {self.name!r} {powod}. Kanał zwrócił kandydata, którego nie "
                "da się zamienić w adres dokumentu bez zmiany punktu końcowego żądania."
            )
        k = self._k
        odpowiedz = self._zadanie(
            f"{k.baza}{k.punkty.dokument}/{ref}",
            nazwa=k.punkty.dokument,
            ocena=self._ocena_dokumentu,
        )
        tresc = odpowiedz.content
        return RawDocument(
            source_ref=ref,
            content=tresc,
            headers=dict(odpowiedz.headers),
            fetched_at=utc_iso(self._zegar.wall()),
            sha256=hashlib.sha256(tresc).hexdigest(),
        )

    # ---------------------------------------------------------------------- jedno żądanie

    def _zadanie(
        self,
        adres: str,
        *,
        nazwa: str,
        ocena: Callable[[bytes], OcenaKsztaltu],
        params: Mapping[str, str | int] | None = None,
    ) -> httpx.Response:
        """Przez limiter, przez bramkę wyjścia klienta, ze śladem **w chwili powrotu** i oceną
        kształtu. Kolejność jak w `scripts/zadanie.wykonaj`, z którego ten szew pochodzi."""
        pelny_adres = str(httpx.URL(adres, params=params)) if params else adres
        self._limiter.acquire(nazwa)
        start = self._zegar.monotonic()
        try:
            odpowiedz = self._klient.get(adres, params=params, headers=self._naglowki)
        except httpx.HTTPError as blad:
            self._slad.zanotuj(
                Wynik(
                    nazwa=nazwa,
                    metoda=METODA,
                    adres=pelny_adres,
                    status=None,
                    bajtow=0,
                    czas_s=self._zegar.monotonic() - start,
                    plik=None,
                    uwaga=f"{type(blad).__name__}: {blad}",
                )
            )
            raise TransportError(
                f"Żądanie do kanału {self.name!r} nie doszło do skutku "
                f"({type(blad).__name__}: {blad}). Przebieg da się wznowić tym samym poleceniem."
            ) from blad
        czas = self._zegar.monotonic() - start
        teraz = self._zegar.wall()
        retry_after_s, uwaga_retry = parse_retry_after(
            odpowiedz.headers.get(NAGLOWEK_RETRY_AFTER), teraz_epoch=teraz
        )
        self._limiter.note_response(odpowiedz.status_code, retry_after_s=retry_after_s)
        if uwaga_retry:
            self._events.on_message(uwaga_retry)
        self._zanotuj_budzet(odpowiedz.headers, teraz)
        self._events.on_request(nazwa, odpowiedz.status_code, czas)
        wynik_oceny = ocena(odpowiedz.content) if odpowiedz.status_code == 200 else None
        self._slad.zanotuj(
            Wynik(
                nazwa=nazwa,
                metoda=METODA,
                adres=pelny_adres,
                status=odpowiedz.status_code,
                bajtow=len(odpowiedz.content),
                czas_s=czas,
                plik=None,
                sha256=hashlib.sha256(odpowiedz.content).hexdigest(),
                ksztalt_zgodny=None if wynik_oceny is None else wynik_oceny.zgodny,
                ksztalt_uwaga="" if wynik_oceny is None else wynik_oceny.uwaga,
                uwaga=uwaga_retry,
                retry_after_s=retry_after_s,
            )
        )
        self._odrzuc_status(odpowiedz.status_code, nazwa)
        if wynik_oceny is not None and not wynik_oceny.zgodny:
            if wynik_oceny.przejsciowa:
                # Urwany JSON albo puste ciało przy 200 to zerwane łącze widziane od strony
                # treści, nie zmiana API — ta sama klasa co `RemoteProtocolError` wyżej
                # (tester 2026-09-18: dwie drogi jednego zdarzenia, dwa werdykty).
                raise TransportError(
                    f"Kanał {self.name!r} odpowiedział 200 na `{nazwa}`, ale odpowiedź przyszła "
                    f"urwana albo pusta ({wynik_oceny.uwaga}) — to wygląda na zerwane łącze, "
                    "nie na zmianę u dostawcy. Przebieg da się wznowić tym samym poleceniem."
                )
            raise SourceContractBroken(
                f"Kanał {self.name!r} odpowiedział 200 na `{nazwa}`, ale kształt nie zgadza się "
                f"z kontraktem: {wynik_oceny.uwaga}"
            )
        return odpowiedz

    def _odrzuc_status(self, status: int, nazwa: str) -> None:
        """Status spoza kontraktu kończy przebieg właściwym wyjątkiem — nie ponowieniem.

        Reguła 16: przy odmowie serwisu narzędzie zatrzymuje się i mówi o tym operatorowi. 429
        też zatrzymuje: limiter dostał już blokadę z `note_response`, a wznowienie tym samym
        poleceniem odczeka ją z historii żądań, zanim wyśle cokolwiek.
        """
        kanal = self.name
        if status == 200:
            return
        if status in (401, 403):
            raise AuthError(f"Kanał {kanal!r} odmówił dostępu do `{nazwa}` ({status}).")
        if status == 429:
            raise RateLimitError(f"Kanał {kanal!r} odrzucił `{nazwa}` statusem 429 mimo limitera.")
        if status == 404:
            raise NotFoundError(f"Kanał {kanal!r} nie zna `{nazwa}` (404).")
        if status == 400:
            raise BadRequestError(f"Kanał {kanal!r} odrzucił `{nazwa}` jako niepoprawne (400).")
        if status >= 500:
            raise ServerError(f"Kanał {kanal!r} odpowiedział {status} na `{nazwa}`.")
        raise SourceContractBroken(
            f"Kanał {kanal!r} odpowiedział {status} na `{nazwa}` — status spoza kontraktu."
        )

    def _zanotuj_budzet(self, naglowki: httpx.Headers, teraz: float) -> None:
        """`X-RateLimit-*` do `limiter.note_budget` — jedyne źródło prawdy o zużyciu przez IP."""
        n = self._k.tempo.naglowki_budzetu
        pozostalo = _liczba(naglowki.get(n.pozostalo))
        reset = _liczba(naglowki.get(n.reset))
        if pozostalo is None or reset is None:
            return
        reset_epoch = reset if reset >= PROG_EPOCH else teraz + reset
        postoj = self._limiter.note_budget(int(pozostalo), reset_epoch)
        if postoj > 0:
            self._events.on_message(
                f"budżet kanału: serwis zgłasza {int(pozostalo)} pozostałych żądań, "
                f"postój do resetu {postoj:.0f} s"
            )


def _liczba(napis: str | None) -> float | None:
    """Wartość nagłówka jako skończona liczba albo `None` — bez zgadywania z napisu."""
    if napis is None:
        return None
    try:
        wartosc = float(napis.strip())
    except ValueError:
        return None
    return wartosc if math.isfinite(wartosc) else None
