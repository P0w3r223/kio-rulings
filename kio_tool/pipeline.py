"""Orkiestracja: kryteria → kanał → magazyn → parser → eksport. Jedyny moduł widzący naraz
`source/` i `store` (reguła 5).

Dopóki jeden moduł łączy sieć z bazą, wznowienie ma jedno miejsce, w którym może być poprawne.
Drugi taki moduł to druga ścieżka od żądania do zapisu i drugi punkt kontrolny do pogodzenia —
a niezmiennik „dokument, wersja, powiązanie z przebiegiem i punkt kontrolny jedną transakcją" żyje
tylko dopóki wszystko idzie tędy.

Reguła zgody (architektura 4.1, audyt 13.2 pkt 4) ma tu postać mechaniczną: przebieg, który
przekroczyłby `PROG_ZGODY` żądań, odmawia `ConsentMissingError`, jeśli nie dostał `zgoda=True`.
Zgoda jest parametrem wywołania, nie polem konfiguracji — zgoda z poprzedniej sesji nie jest
zgodą, więc nie da się jej zapisać w pliku.

Puls idzie przez `Events` w jedynych jednostkach, w których doktryna pozwala go liczyć: żądania
wysłane (`on_request`) i dokumenty zapisane (`on_document`) — nigdy strony (`progress.py`).

Cztery operacje **bez sieci** — `eksportuj`, `przelicz`, `szukaj`, `wznow` przed pierwszym
żądaniem — nie budują klienta HTTP: fabryka klienta jest wołana wyłącznie w `pobierz`, a test
`--block-network` z `pyproject.toml` pilnuje, że żadna z nich nie sięga gniazda (reguła 20).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from . import __version__
from .clock import Clock, SystemClock, utc_iso
from .config import default_output_dir, klucz_api, safe_filename
from .criteria import Criteria
from .docid import SourceName, document_id, normalize_source_name
from .errors import (
    ConfigError,
    ConsentMissingError,
    NotFoundError,
    ParseError,
    ResumableError,
    SourceContractBroken,
    StoreError,
)
from .exporter import FORMATY, Wpis
from .exporter import eksportuj as zapisz_eksport
from .httpclient import build_http_client
from .logbook import Wynik
from .parser.details import PARSE_VERSION, MapaPol, Szczegoly, rekord_z_bajtow, wyczytaj
from .progress import Events, NullEvents
from .ratelimit import DOBA_S, InMemoryHistory, RateLimiter
from .source.contract import Contract, load_contract
from .source.protocol import Channel, Scope
from .source.registry import REGISTRY
from .store import (
    STATUSY_WZNAWIALNE,
    Dokument,
    Filtr,
    Metryka,
    Przebieg,
    Store,
    Wyszukanie,
)

KANAL_DOMYSLNY = SourceName("atlas")
"""Pierwszy adapter (ADR-0004 §6, ADR-0005 Z-3) — jedyny wpis `REGISTRY`, więc jedyna domyślna."""

PROG_ZGODY = 50
"""Od ilu żądań przebieg jest masowy i wymaga zgody właściciela udzielonej w tej sesji.

Liczba jest progiem, nie pomiarem, i tak ma być czytana: pojedynczy odczyt diagnostyczny to
kilka żądań, przebieg miesięczny to ~360 (właściciel 2026-09-18), a zgoda ma paść **przed**
pierwszym dokumentem, nie po pięćdziesiątym — dlatego próg porównuje się najpierw z liczbą
dokumentów zgłoszoną przez kanał na pierwszej stronie listy (przyciętą przez `maks`), a licznik
żądań jest tylko zabezpieczeniem na wypadek kanału, który liczby nie zgłasza.
"""

STATUS_PRZERWANY = "przerwany"
FORMATY_DOMYSLNE: tuple[str, ...] = ("xlsx",)

PROG_404_POD_RZAD = 10
"""Ile kolejnych 404 na dokumentach znaczy „przeniesiony punkt końcowy", nie „wycofane sprawy".

Pojedynczy 404 jest wynikiem spodziewanym i `_przebieg` go pomija. Ale gdy pośrednik przeniesie
punkt dokumentu, lista nadal odpowiada 200, a każdy dokument 404 — pomijanie bez sufitu
przemieliłoby całą listę, czyli ~29 580 żądań do cudzego serwisu za nic (przegląd kodu
2026-09-18). Licznik zeruje pierwszy udany dokument; próg jest liczbą, nie pomiarem, jak
`PROG_ZGODY`.
"""

KlientFactory = Callable[..., httpx.Client]


@dataclass(frozen=True)
class Podsumowanie:
    """Rachunek jednego wywołania `pobierz` plus liczby całego przebiegu odczytane z bazy."""

    run_id: str
    status: str
    kandydatow: int
    nowych: int
    pominietych: int
    zadan: int
    zgloszone: int | None
    """Liczba dokumentów w zakresie zgłoszona przez kanał (`total`) — osobno od objętych."""
    objetych_lacznie: int
    pobranych_lacznie: int
    zadan_lacznie: int
    bledow_odczytu: int
    zakres: str
    brakujacych: int = 0
    """Kandydaci z listy, których kanał już nie miał (404) — pominięci, nie zatrzymujący."""


@dataclass(frozen=True)
class WynikEksportu:
    sciezki: tuple[Path, ...]
    dokumentow: int
    formaty: tuple[str, ...]
    run_ids: tuple[str, ...]
    bez_daty_poza_filtrem: int


@dataclass(frozen=True)
class WynikPrzeliczenia:
    przeliczonych: int
    bledow: int
    w_korpusie: int
    zaindeksowanych: int


class _Puls:
    """Otulina `Events`: liczy żądania i pamięta liczbę dokumentów w zakresie, resztę przekazuje."""

    def __init__(self, inner: Events) -> None:
        self._inner = inner
        self.zadan = 0
        self.razem: int | None = None

    def on_request(self, endpoint: str, status: int, elapsed_s: float) -> None:
        self.zadan += 1
        self._inner.on_request(endpoint, status, elapsed_s)

    def on_page(self, page_index: int, candidates: int, total: int | None) -> None:
        if total is not None:
            self.razem = total
        self._inner.on_page(page_index, candidates, total)

    def on_document(self, saved: int, total: int | None) -> None:
        self._inner.on_document(saved, total)

    def on_version(self, doc_id: str, content_sha256: str) -> None:
        self._inner.on_version(doc_id, content_sha256)

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        self._inner.on_wait(seconds, reason, resume_at_epoch)

    def on_parse(self, done: int, total: int) -> None:
        self._inner.on_parse(done, total)

    def on_export(self, done: int, total: int) -> None:
        self._inner.on_export(done, total)

    def on_message(self, text: str) -> None:
        self._inner.on_message(text)

    def close(self) -> None:
        self._inner.close()


class _SladDoBazy:
    """`SladZadan` nad `requests_log`: wiersz w chwili powrotu żądania, nie po całym przebiegu."""

    def __init__(self, store: Store, run_id: str, zegar: Clock) -> None:
        self._store = store
        self._run_id = run_id
        self._zegar = zegar

    def zanotuj(self, wynik: Wynik) -> Wynik:
        ksztalt = (
            "—"
            if wynik.ksztalt_zgodny is None
            else ("zgodny" if wynik.ksztalt_zgodny else "NIEZGODNY")
        )
        self._store.log_request(
            self._run_id,
            ts=utc_iso(self._zegar.wall()),
            metoda=wynik.metoda,
            url=wynik.adres,
            status=wynik.status,
            ms=round(wynik.czas_s * 1000),
            bajtow=wynik.bajtow,
            sha256=wynik.sha256,
            ksztalt=ksztalt,
            retry_after_s=wynik.retry_after_s,
        )
        return wynik


def kanaly() -> tuple[str, ...]:
    return tuple(sorted(REGISTRY))


def zakres_z_kryteriow(kryteria: Criteria, kontrakt: Contract) -> Scope:
    """`Criteria` → `Scope` po naszych nazwach pól; filtr, którego kontrakt nie tłumaczy,
    jest błędem konfiguracji **przed** pierwszym żądaniem."""
    if kryteria.is_empty():
        raise ConfigError(
            "Brak kryteriów: przebieg bez zakresu dat i bez filtra objąłby cały zbiór kanału."
        )
    try:
        filtry = kryteria.filtry_kanalu()
    except ValueError as blad:
        raise ConfigError(str(blad)) from blad
    nieznane = sorted(set(filtry) - set(kontrakt.parametry_listy.filtry))
    if nieznane:
        raise ConfigError(
            f"Kanał {kontrakt.kanal!r} nie tłumaczy filtrów {', '.join(nieznane)} "
            f"(`parametry_listy.filtry` w contract.yaml zna: "
            f"{', '.join(sorted(kontrakt.parametry_listy.filtry)) or '—'})."
        )
    return Scope(kryteria.od, kryteria.do, filtry)


def mapa_pol(kontrakt: Contract) -> MapaPol:
    """Nazwy pól rekordu dokumentu z kontraktu — jedyne miejsce, które je przepisuje do parsera."""
    dokument = kontrakt.ksztalt.dokument
    return MapaPol(tresc=dokument.pole_tresci, **dokument.pola_metadanych.model_dump())


def pobierz(
    kanal: str,
    kryteria: Criteria,
    store: Store,
    events: Events | None = None,
    *,
    zgoda: bool,
    user_agent: str,
    klient_factory: KlientFactory | None = None,
    zegar: Clock | None = None,
    wznow_run_id: str | None = None,
) -> Podsumowanie:
    """Pobiera kandydatów według kryteriów do bazy; przerwany przebieg o tym samym odcisku
    kryteriów wznawia sam, od ostatniej strony listy.

    `wznow_run_id` wskazuje przebieg do wznowienia wprost — bez tego `wznow --run-id A`
    wznawiało **najnowszy** przebieg o tym odcisku, a ekran pokazywał identyfikator A nad
    rachunkiem przebiegu B (przegląd kodu 2026-09-18; dwa przerwane przebiegi o jednym odcisku
    powstają choćby z `_dopisz_odciski_przebiegom_sprzed_schematu_2`).
    """
    nazwa = normalize_source_name(kanal)
    klasa = REGISTRY.get(nazwa)
    if klasa is None:
        raise ConfigError(f"Nieznany kanał {kanal!r}; dostępne: {', '.join(kanaly())}.")
    kontrakt = load_contract(nazwa)
    scope = zakres_z_kryteriow(kryteria, kontrakt)
    zegar = zegar or SystemClock()
    puls = _Puls(events or NullEvents())
    # Fabryka rozstrzygana **przy wywołaniu**, nie przy definicji: test podstawia
    # `pipeline.build_http_client` z atrapą transportu, a wartość domyślna parametru byłaby
    # związana raz, przy imporcie modułu.
    fabryka: KlientFactory = klient_factory or build_http_client
    odcisk = kryteria.fingerprint()
    przerwany: Przebieg | None
    if wznow_run_id is not None:
        przerwany = store.get_run(wznow_run_id)
    else:
        # Kanał w zapytaniu, nie tylko odcisk: `pobierz --kanal saos` nie ma prawa wznowić
        # przebiegu atlasowego ani załadować limiterowi historii cudzego hosta. Statusy
        # wznawialne obejmują `w_toku` bez procesu (zanik zasilania, `taskkill /F`): bez tego
        # to samo polecenie zakładało nowy przebieg i płaciło cudzemu serwisowi za całą listę
        # od strony pierwszej, a stary zostawał w `runy` na zawsze jako pracujący (tester
        # 2026-09-18).
        przerwany = store.find_run(odcisk, STATUSY_WZNAWIALNE, kanal=nazwa)
    if przerwany is None:
        run_id = store.start_run(
            kanal=nazwa,
            zakres=scope.etykieta,
            started_at=utc_iso(zegar.wall()),
            kryteria=kryteria.canonical_json(),
            fingerprint=odcisk,
        )
        od_strony = 1
    else:
        osierocony = przerwany.status == "w_toku"
        wznowiony = store.resume_run(przerwany.run_id, takze_blad=wznow_run_id is not None)
        run_id = wznowiony.run_id
        od_strony = wznowiony.ostatnia_strona or 1
        if osierocony:
            puls.on_message(
                f"przebieg {run_id} był zapisany jako pracujący, ale żaden proces go nie kończył "
                "— najpewniej zanik zasilania albo ubicie procesu; wznawiam od strony "
                f"{od_strony}. Jeśli inny proces nadal pobiera na tej bazie, przerwij (Ctrl+C)."
            )
        else:
            puls.on_message(f"wznawiam przerwany przebieg {run_id} od strony {od_strony}")
    limiter = RateLimiter(
        min_spacing_s=kontrakt.tempo.odstep_s,
        windows=[(okno.limit, okno.sekund) for okno in kontrakt.tempo.okna],
        clock=zegar,
        # Historia z dziennika, nie pusta pamięć procesu: odstęp i blokada po 429 mają przeżyć
        # przerwanie przebiegu razem z dziennikiem (`Store.request_stamps`).
        history=InMemoryHistory(store.request_stamps(nazwa, zegar.wall() - DOBA_S)),
        events=puls,
    )
    licznik = _Licznik(pozycja=store.count_run_documents(run_id))
    status = "blad"
    powod: str | None = None
    try:
        with fabryka(user_agent=user_agent, allowed=klasa.hosty) as klient:
            kanal_obj: Channel = klasa(
                klient,
                limiter,
                kontrakt,
                puls,
                zegar=zegar,
                slad=_SladDoBazy(store, run_id, zegar),
                klucz_api=klucz_api(kontrakt.tempo.klucz_api.zmienna),
            )
            _przebieg(
                kanal_obj,
                kontrakt,
                scope,
                store,
                run_id,
                od_strony,
                puls,
                zgoda,
                licznik,
                maks=kryteria.maks,
            )
        status = "zakonczony"
    except (ResumableError, ConsentMissingError, KeyboardInterrupt) as blad:
        # Przerwany, nie błędny: to samo polecenie wznowi go od `ostatnia_strona`. Zgoda należy
        # do tej grupy, bo jej brak jest sprawą wywołania, nie kodu ani serwisu.
        status = STATUS_PRZERWANY
        powod = (
            "przerwanie przez operatora (Ctrl+C)"
            if isinstance(blad, KeyboardInterrupt)
            else str(blad)
        )
        raise
    except Exception as blad:
        powod = f"{type(blad).__name__}: {blad}"
        raise
    finally:
        # Także przy wyjątku: przebieg bez `finished_at` wyglądałby jak proces, który wciąż pracuje.
        _zamknij_przebieg(
            store,
            run_id,
            status=status,
            powod=powod,
            zegar=zegar,
            puls=puls,
            w_locie=status != "zakonczony",
        )
        puls.close()
    return Podsumowanie(
        run_id=run_id,
        status=status,
        kandydatow=licznik.kandydatow,
        nowych=licznik.nowych,
        pominietych=licznik.pominietych,
        zadan=puls.zadan,
        zgloszone=puls.razem,
        objetych_lacznie=store.count_run_documents(run_id),
        pobranych_lacznie=store.count_run_documents(run_id, nowe=True),
        zadan_lacznie=store.count_requests(run_id),
        bledow_odczytu=licznik.bledow_odczytu,
        zakres=scope.etykieta,
        brakujacych=licznik.brakujacych,
    )


def _zamknij_przebieg(
    store: Store,
    run_id: str,
    *,
    status: str,
    powod: str | None,
    zegar: Clock,
    puls: _Puls,
    w_locie: bool,
) -> None:
    """`finish_run` z bloku `finally` — bez zastępowania wyjątku, który już leci.

    Dysk pełny na tyle, że nie da się zapisać nawet zakończenia przebiegu, rzucał z `finally`
    drugi wyjątek, który **zastępował** pierwszy: operator widział błąd zapisu statusu zamiast
    powodu przerwania (tester 2026-09-18). Gdy wyjątek już leci, awaria zamknięcia idzie na ekran
    zdaniem, a przebieg zostaje `w_toku` — czyli osierocony i wznawialny tym samym poleceniem.
    Gdy nic nie leci, awaria zamknięcia jest jedynym błędem i ma wyjść jako `StoreError`, bo
    inaczej `zakonczony` na ekranie mówiłoby nieprawdę o wierszu w bazie.

    `w_locie` przychodzi od wołającego jako `status != "zakonczony"`, nie z `sys.exc_info()`:
    introspekcja widziała także cudzy wyjątek, gdy `pobierz` wołano z wnętrza czyjegoś `except`
    (przegląd kodu 2026-09-18).
    """
    try:
        store.finish_run(run_id, status=status, finished_at=utc_iso(zegar.wall()), powod=powod)
    except Exception as blad_zamkniecia:
        if not w_locie:
            raise StoreError(
                f"Przebieg {run_id} skończył pracę, ale nie udało się zapisać jego zakończenia "
                f"({blad_zamkniecia}). Zostaje jako pracujący — wznowi go to samo polecenie."
            ) from blad_zamkniecia
        puls.on_message(
            f"nie udało się zapisać zakończenia przebiegu {run_id} ({blad_zamkniecia}); "
            "zostaje jako pracujący — wznowi go to samo polecenie"
        )


class _Licznik:
    def __init__(self, *, pozycja: int) -> None:
        self.kandydatow = 0
        self.nowych = 0
        self.pominietych = 0
        self.bledow_odczytu = 0
        self.brakujacych = 0
        self.brakujacych_pod_rzad = 0
        self.pozycja = pozycja
        """Pozycja kandydata w przebiegu — po wznowieniu liczona dalej, nie od zera."""


def _przebieg(
    kanal: Channel,
    kontrakt: Contract,
    scope: Scope,
    store: Store,
    run_id: str,
    od_strony: int,
    puls: _Puls,
    zgoda: bool,
    licznik: _Licznik,
    *,
    maks: int | None,
) -> None:
    mapa = mapa_pol(kontrakt)
    for kandydat in kanal.list_candidates(scope, od_strony=od_strony):
        if maks is not None and licznik.kandydatow >= maks:
            return
        # Zgoda sprawdzana **przed** rozstrzygnięciem „nowy czy pominięty" (przegląd kodu
        # 2026-09-18, HIGH): strony listy są żądaniami do cudzego serwisu tak samo jak dokumenty,
        # a przebieg, w którym wszyscy kandydaci są już w bazie, nie dochodził do sprawdzenia ani
        # razu — zmierzone: 60 stron listy bez zgody przy progu 50. Ponowne `pobierz` na dużym
        # zakresie wymaga więc `--zgoda` także wtedy, gdy nie pobierze ani jednego dokumentu:
        # 296 żądań to 296 żądań.
        _wymagaj_zgody(zgoda, puls, maks)
        licznik.kandydatow += 1
        licznik.pozycja += 1
        doc_id = document_id(kanal.name, kandydat.source_ref, ref_case=kontrakt.ref_case)
        if store.has_document(doc_id):
            # Wznawianie: dokument już w bazie nie kosztuje żądania. Duplikatu i tak nie byłoby
            # (`INSERT OR IGNORE`), ale cudzy serwer płaciłby za odpowiedź, której nie potrzebujemy.
            # Powiązanie z przebiegiem powstaje mimo to: `eksportuj --run-id` ma objąć to, co
            # przebieg **objął**, nie tylko to, co pobrał.
            store.link_run_document(run_id, doc_id, position=licznik.pozycja, nowy=False)
            licznik.pominietych += 1
            continue
        try:
            surowy = kanal.fetch(kandydat.source_ref)
        except NotFoundError as blad:
            # 404 na jednym dokumencie to dokument wycofany u pośrednika między listą
            # a pobraniem — `errors.NotFoundError` nazywa go wynikiem spodziewanym. Zatrzymanie
            # przebiegu byłoby ślepą uliczką: wznowienie listuje tę samą stronę i trafia w ten sam
            # 404 (tester 2026-09-18). Liczony i pominięty; wiersz w dzienniku żądań już jest.
            licznik.brakujacych += 1
            licznik.brakujacych_pod_rzad += 1
            puls.on_message(f"dokument {kandydat.source_ref}: {blad} — pomijam, idę dalej")
            if licznik.brakujacych_pod_rzad >= PROG_404_POD_RZAD:
                raise SourceContractBroken(
                    f"Kanał {kanal.name!r} odpowiedział 404 na {licznik.brakujacych_pod_rzad} "
                    "kolejnych dokumentów, choć lista je zwraca — to nie są wycofane sprawy, "
                    "to przeniesiony punkt końcowy. Zatrzymuję przebieg zamiast przemielić "
                    "całą listę."
                ) from blad
            continue
        licznik.brakujacych_pod_rzad = 0
        # Odczyt **przed** transakcją: `ParseError` w jej środku cofałby zapis surowych bajtów,
        # a reguła 19 każe zapisać je w całości niezależnie od tego, czy dają się odczytać.
        szczegoly = _odczytaj(surowy.content, mapa)
        with store.transakcja():
            store.upsert_document(
                doc_id=doc_id,
                source=kanal.name,
                source_ref=kandydat.source_ref,
                sygnatury=kandydat.sygnatury,
                data_wydania=kandydat.data_wydania,
                seen_at=surowy.fetched_at,
                content_sha256=surowy.sha256,
            )
            store.add_raw_version(
                doc_id=doc_id,
                content=surowy.content,
                fetched_at=surowy.fetched_at,
                fetch_meta={"naglowki": dict(surowy.headers)},
                expected_sha256=surowy.sha256,
            )
            if szczegoly is not None:
                store.index_document(doc_id, surowy.sha256, metryka(szczegoly))
            else:
                licznik.bledow_odczytu += 1
            store.link_run_document(run_id, doc_id, position=licznik.pozycja, nowy=True)
            store.checkpoint(run_id, kandydat.strona)
        licznik.nowych += 1
        puls.on_document(licznik.nowych, _przewidywane(puls.razem, maks))


def _odczytaj(content: bytes, mapa: MapaPol) -> Szczegoly | None:
    try:
        return wyczytaj(rekord_z_bajtow(content), mapa)
    except ParseError:
        return None


def metryka(szczegoly: Szczegoly) -> Metryka:
    return Metryka(parse_version=PARSE_VERSION, **asdict(szczegoly))


def _przewidywane(razem: int | None, maks: int | None) -> int | None:
    if razem is None:
        return maks
    return razem if maks is None else min(razem, maks)


def _wymagaj_zgody(zgoda: bool, puls: _Puls, maks: int | None) -> None:
    if zgoda:
        return
    przewidywane = _przewidywane(puls.razem, maks)
    if puls.zadan >= PROG_ZGODY or (przewidywane is not None and przewidywane > PROG_ZGODY):
        zgloszone = "?" if przewidywane is None else str(przewidywane)
        raise ConsentMissingError(
            f"Przebieg masowy bez zgody: kanał zgłasza {zgloszone} "
            f"dokumentów w zakresie, a bez zgody wolno wysłać najwyżej {PROG_ZGODY} żądań "
            f"(wysłano {puls.zadan}). Przebieg zostaje zapisany jako przerwany — to samo "
            "polecenie z flagą `--zgoda` dokończy go bez ponownego pobierania tego, co już "
            "przyszło. Zgoda obowiązuje w sesji, w której padła (audyt 13.2 pkt 4)."
        )


# ------------------------------------------------------------------------------ wznowienie


def do_wznowienia(store: Store, run_id: str | None) -> tuple[str, Criteria]:
    """Przebieg do wznowienia i jego kryteria odtworzone z bazy — bez żadnego żądania.

    Przebieg sprzed schematu 2 bez odtworzonego odcisku (etykieta zakresu w nieznanej postaci)
    nie da się wznowić przez `wznow`; `pobierz` z tymi samymi datami założy nowy przebieg
    i pominie dokumenty już w bazie — to jest droga zapasowa, nazwana w komunikacie.
    """
    if run_id is None:
        ostatnie = store.list_runs(limit=1, statuses=STATUSY_WZNAWIALNE)
        if not ostatnie:
            raise ConfigError(
                "W bazie nie ma przerwanego ani osieroconego przebiegu — nie ma czego wznawiać."
            )
        przebieg = ostatnie[0]
    else:
        przebieg = store.get_run(run_id)
    # Przebieg zakończony błędem (wygasły klucz, odmowa serwisu, złamany kontrakt) wznawia się
    # wyłącznie jawnie, po `--run-id`: stan bywa ustępujący i punkt kontrolny jest wart stron
    # listy, ale automat nie ma prawa wracać do złamanego kontraktu sam (przegląd 2026-09-18).
    dozwolone = STATUSY_WZNAWIALNE if run_id is None else (*STATUSY_WZNAWIALNE, "blad")
    if przebieg.status not in dozwolone:
        raise ConfigError(
            f"Przebieg {przebieg.run_id} ma status {przebieg.status!r}; wznowić da się "
            "przerwany albo osierocony (pracujący bez procesu), a przez `--run-id` także "
            "zakończony błędem."
        )
    if przebieg.kryteria is None:
        raise ConfigError(
            f"Przebieg {przebieg.run_id} pochodzi sprzed schematu 2 i nie ma zapisanych kryteriów "
            f"(zakres: {przebieg.zakres}). Uruchom `pobierz` z tym zakresem dat — dokumenty już "
            "w bazie nie będą pobierane ponownie."
        )
    return przebieg.run_id, Criteria.z_json(przebieg.kryteria)


def wznow(
    store: Store,
    run_id: str | None,
    events: Events | None = None,
    *,
    zgoda: bool,
    user_agent: str,
    klient_factory: KlientFactory | None = None,
    zegar: Clock | None = None,
) -> Podsumowanie:
    wybrany, kryteria = do_wznowienia(store, run_id)
    przebieg = store.get_run(wybrany)
    return pobierz(
        przebieg.kanal,
        kryteria,
        store,
        events,
        zgoda=zgoda,
        user_agent=user_agent,
        klient_factory=klient_factory,
        zegar=zegar,
        wznow_run_id=wybrany,
    )


# --------------------------------------------------------------------------------- eksport


def eksportuj(
    store: Store,
    *,
    run_ids: Sequence[str] = (),
    kryteria: Criteria | None = None,
    formaty: Sequence[str] = FORMATY_DOMYSLNE,
    out: Path | None = None,
    cel: str | None = None,
    zegar: Clock | None = None,
    events: Events | None = None,
) -> WynikEksportu:
    """Eksport wyłącznie z bazy (`online=False` w duchu `ceidg-tool`): żadnego klienta HTTP.

    Dokumenty objęte przebiegami (`run_documents`) albo pasujące do kryteriów; puste kryteria
    bez przebiegu są błędem, a zero dokumentów nie tworzy pliku — plik pusty wyglądałby na wynik.
    """
    zegar = zegar or SystemClock()
    for fmt in formaty:
        if fmt not in FORMATY:
            raise ConfigError(f"Nieznany format {fmt!r}; dostępne: {', '.join(FORMATY)}.")
    if not run_ids and (kryteria is None or kryteria.is_empty()):
        raise ConfigError("Podaj przebiegi (`run_ids`) albo niepuste kryteria eksportu.")
    przebiegi = [store.get_run(r) for r in run_ids]
    filtr = None if kryteria is None else Filtr.z_kryteriow(kryteria)
    mapy = _MapyPol()

    def dokumenty() -> Iterator[Dokument]:
        if przebiegi:
            # Dokument objęty dwoma przebiegami (styczeń i I kwartał) jest jednym dokumentem —
            # bez odsiania szedł do eksportu dwa razy, a `dokumentow_w_eksporcie` w `Metadane`
            # mówiło nieprawdę o własnym wyniku (przegląd kodu 2026-09-18; mina 1: duplikaty).
            widziane: set[str] = set()
            for przebieg in przebiegi:
                for dokument in store.iter_documents(run_id=przebieg.run_id):
                    if dokument.doc_id in widziane:
                        continue
                    widziane.add(dokument.doc_id)
                    yield dokument
        else:
            yield from store.iter_documents(filtr)

    def zrodlo() -> Iterator[Wpis]:
        for dokument in dokumenty():
            yield _wpis(dokument, mapy)

    # Pierwsze przejście liczy dokumenty **i** ładuje kontrakty kanałów, które w eksporcie
    # wystąpią — atrybucja per kanał ma trafić do `Metadane`, a te powstają przed zapisem.
    dokumentow = 0
    for dokument in dokumenty():
        dokumentow += 1
        mapy.dla(dokument.source)
    bez_daty = 0 if filtr is None or przebiegi else store.bez_daty_poza_filtrem(filtr)
    if dokumentow == 0:
        return WynikEksportu((), 0, tuple(formaty), tuple(run_ids), bez_daty)
    metadane = build_metadata(
        store,
        run_ids=tuple(run_ids),
        kryteria=kryteria,
        dokumentow=dokumentow,
        formaty=tuple(formaty),
        cel=cel,
        zegar=zegar,
        atrybucje=mapy.atrybucje(),
    )
    nazwa = _nazwa_eksportu(run_ids, kryteria, zegar)
    # `--out` wskazujące istniejący katalog: plik o nazwie domyślnej **w środku**, nie obok —
    # pomoc flagi mówiła o katalogu `wyniki/`, więc operator podawał katalog i dostawał
    # `wyniki.xlsx` przy pustym `wyniki\` (tester 2026-09-18).
    if out is None:
        rdzen = default_output_dir() / nazwa
    elif out.is_dir():
        rdzen = out / nazwa
    else:
        rdzen = out
    sciezki = zapisz_eksport(rdzen, zrodlo, formaty=formaty, metadane=metadane, events=events)
    return WynikEksportu(tuple(sciezki), dokumentow, tuple(formaty), tuple(run_ids), bez_daty)


class _MapyPol:
    """Mapa pól i atrybucja per kanał, ładowane raz z kontraktu przy pierwszym dokumencie."""

    def __init__(self) -> None:
        self._mapy: dict[str, MapaPol] = {}
        self._atrybucje: dict[str, str] = {}

    def dla(self, source: str) -> tuple[MapaPol, str]:
        if source not in self._mapy:
            kontrakt = load_contract(SourceName(source))
            self._mapy[source] = mapa_pol(kontrakt)
            self._atrybucje[source] = kontrakt.licencja.atrybucja
        return self._mapy[source], self._atrybucje[source]

    def atrybucje(self) -> dict[str, str]:
        return dict(self._atrybucje)


def _wpis(dokument: Dokument, mapy: _MapyPol) -> Wpis:
    mapa, atrybucja = mapy.dla(dokument.source)
    try:
        rekord = rekord_z_bajtow(dokument.content_bytes)
    except ParseError as blad:
        # Reguła 19 każe zapisać surowe bajty także wtedy, gdy nie dają się odczytać, więc taki
        # wiersz jest w modelu legalny. Eksport, który wywraca się bez nazwy winnego dokumentu,
        # zostawia operatora z korpusem bez pliku i bez adresu (przegląd kodu 2026-09-18).
        raise ParseError(
            f"{dokument.doc_id} (wersja {dokument.current_sha256[:12]}): {blad}"
        ) from blad
    return Wpis(
        doc_id=dokument.doc_id,
        source=dokument.source,
        source_ref=dokument.source_ref,
        sha256=dokument.current_sha256,
        fetched_at=dokument.fetched_at,
        szczegoly=wyczytaj(rekord, mapa),
        rekord=rekord,
        atrybucja=atrybucja,
    )


def _nazwa_eksportu(run_ids: Sequence[str], kryteria: Criteria | None, zegar: Clock) -> str:
    moment = utc_iso(zegar.wall()).replace(":", "").replace("-", "")
    if kryteria is not None and not kryteria.is_empty():
        return safe_filename(f"kio_{kryteria.describe()[:40]}_{moment}")
    return safe_filename(f"kio_{'_'.join(run_ids)}_{moment}")


def build_metadata(
    store: Store,
    *,
    run_ids: Sequence[str],
    kryteria: Criteria | None,
    dokumentow: int,
    formaty: Sequence[str],
    cel: str | None,
    zegar: Clock,
    atrybucje: dict[str, str],
) -> list[tuple[str, object]]:
    """Arkusz `Metadane`: kryteria, przebiegi, liczby z bazy, licencja, wersja narzędzia.

    `zgloszone_przez_kanal` i `objetych` to **dwa osobne wiersze**: pierwsze jest cudzą liczbą
    (`total` z listy), drugie naszą (`run_documents`) — ich różnica jest informacją, nie błędem.
    """
    przebiegi = [store.get_run(r) for r in run_ids]
    meta: list[tuple[str, object]] = []
    if kryteria is not None:
        meta.append(("kryteria", kryteria.describe()))
        meta.append(("kryteria_json", kryteria.canonical_json()))
    elif przebiegi:
        meta.append(("kryteria", "; ".join(p.zakres for p in przebiegi)))
        meta.append(("kryteria_json", "; ".join(p.kryteria or "" for p in przebiegi)))
    meta.append(("cel_pobrania", cel or ""))
    if przebiegi:
        meta.extend(
            [
                ("run_id", ", ".join(p.run_id for p in przebiegi)),
                ("kanal", ", ".join(sorted({p.kanal for p in przebiegi}))),
                ("status_przebiegu", ", ".join(f"{p.run_id}: {p.status}" for p in przebiegi)),
                ("przebieg_start_utc", min(p.started_at for p in przebiegi)),
                (
                    "przebieg_koniec_utc",
                    max((p.finished_at or "" for p in przebiegi), default=""),
                ),
                ("objetych_przez_przebiegi", sum(p.dokumentow for p in przebiegi)),
                (
                    "pobranych_przez_przebiegi",
                    sum(store.count_run_documents(p.run_id, nowe=True) for p in przebiegi),
                ),
                ("zadan_w_przebiegach", sum(p.zadan for p in przebiegi)),
            ]
        )
    meta.extend(
        [
            ("dokumentow_w_eksporcie", dokumentow),
            ("dokumentow_w_korpusie", store.count("documents")),
            ("formaty", ", ".join(formaty)),
            ("eksport_utc", utc_iso(zegar.wall())),
            ("wersja_narzedzia", __version__),
            ("wersja_odczytu", PARSE_VERSION),
            ("organ", "Krajowa Izba Odwoławcza"),
        ]
    )
    for kanal, atrybucja in sorted(atrybucje.items()):
        meta.append((f"atrybucja_{kanal}", atrybucja))
    return meta


# ----------------------------------------------------------------------------- przeliczenie


def przelicz(
    store: Store, events: Events | None = None, *, wszystko: bool = False
) -> WynikPrzeliczenia:
    """Metadane i indeks z surowych wersji w bazie — zero żądań (reguła 20 pilnuje tego testem).

    Przelicza bieżące wersje bez metadanych albo z `parse_version` starszym niż
    `PARSE_VERSION`; `wszystko=True` przelicza każdą. Błąd odczytu jest **liczony**, nie
    przemilczany: surowe bajty zostają, wiersz metadanych nie powstaje.
    """
    reporter = events or NullEvents()
    mapy = _MapyPol()
    przeliczonych = 0
    bledow = 0
    do_przeliczenia = list(store.versions_to_index(None if wszystko else PARSE_VERSION))
    for numer, dokument in enumerate(do_przeliczenia, start=1):
        mapa, _ = mapy.dla(dokument.source)
        szczegoly = _odczytaj(dokument.content_bytes, mapa)
        if szczegoly is None:
            bledow += 1
        else:
            with store.transakcja():
                store.index_document(dokument.doc_id, dokument.current_sha256, metryka(szczegoly))
            przeliczonych += 1
        reporter.on_parse(numer, len(do_przeliczenia))
    return WynikPrzeliczenia(
        przeliczonych=przeliczonych,
        bledow=bledow,
        w_korpusie=store.count("documents"),
        zaindeksowanych=store.count_indexed(),
    )


# ------------------------------------------------------------------------------ wyszukiwanie


def szukaj(store: Store, kryteria: Criteria, *, limit: int) -> Wyszukanie:
    """Wyszukiwanie w korpusie lokalnym — zero żądań; fraza jest wymagana."""
    if not kryteria.fraza:
        raise ConfigError("Wyszukiwanie wymaga frazy (`--fraza`).")
    return store.szukaj(kryteria.fraza, Filtr.z_kryteriow(kryteria), limit=limit)
