"""Pobieranie i wznawianie — jedyny moduł widzący naraz `source/` i `store` (reguła 5, ADR-0009).
Dopóki jeden moduł łączy sieć z bazą, wznowienie ma jedno miejsce, w którym może być poprawne.
Drugi taki moduł to druga ścieżka od żądania do zapisu i drugi punkt kontrolny do pogodzenia —
a niezmiennik „dokument, wersja, powiązanie z przebiegiem i punkt kontrolny jedną transakcją" żyje
tylko dopóki wszystko idzie tędy.

Do 2026-09-22 całość żyła w `pipeline.py`; operacje bez sieci przeszły do `lokalne.py`, zgoda do
`zgoda.py`, puls i ślad do `slad.py`. Transakcja strony z punktem kontrolnym zostaje tutaj.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from ..clock import Clock, SystemClock, utc_iso
from ..config import klucz_api
from ..criteria import Criteria
from ..docid import SourceName, document_id, normalize_source_name
from ..errors import (
    ConfigError,
    ConsentMissingError,
    NotFoundError,
    ResumableError,
    SourceContractBroken,
    StoreError,
)
from ..httpclient import build_http_client
from ..odczyt import metryka, odczytaj, struktura
from ..progress import Events, NullEvents
from ..ratelimit import DOBA_S, InMemoryHistory, RateLimiter
from ..source.contract import Contract, load_contract
from ..source.protocol import Channel, Scope
from ..source.registry import REGISTRY
from ..store import (
    STATUSY_WZNAWIALNE,
    Przebieg,
    Store,
)
from ..wpisy import mapa_pol
from ..wycena import Wycena, wycen
from .slad import _Puls, _SladDoBazy
from .zgoda import (
    Decyzja,
    _przewidywane,
    _rozstrzygnij,
    _wymagaj_zgody,
    _Zgoda,
    decyzja_z_flagi,
)

KANAL_DOMYSLNY = SourceName("atlas")
"""Pierwszy adapter (ADR-0004 §6, ADR-0005 Z-3) — jedyny wpis `REGISTRY`, więc jedyna domyślna."""


STATUS_PRZERWANY = "przerwany"


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
    ponowien_lacznie: int = 0
    """Próby od drugiej w całym przebiegu, czytane **z bazy** (ADR-0007 Z-7 ujście 4, Z-8)."""


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


def pobierz(
    kanal: str,
    kryteria: Criteria,
    store: Store,
    events: Events | None = None,
    *,
    zgoda: bool,
    user_agent: str,
    decyzja: Decyzja | None = None,
    klient_factory: KlientFactory | None = None,
    klucz_z_srodowiska: bool = True,
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
    # `build_http_client` w tym module (`podstaw_fabryke_klienta`, ADR-0009 Z-3) z atrapą
    # transportu, a wartość domyślna parametru byłaby związana raz, przy imporcie modułu.
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
    stan = _Zgoda(zgoda)
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
                slad=_SladDoBazy(store, run_id, zegar, puls),
                # Pokaz nie czyta klucza (ADR-0008 Z-14): `register_secret` odmawia sekretu
                # krótszego niż 12 znaków, więc zły klucz w środowisku blokowałby pokaz, który
                # klucza nie potrzebuje.
                klucz_api=(
                    klucz_api(kontrakt.tempo.klucz_api.zmienna) if klucz_z_srodowiska else None
                ),
                # ADR-0007 Z-9: ponowienie jest żądaniem jak każde inne, więc przed nim też
                # pada pytanie o zgodę — inaczej pętla prób przekraczała próg o `proby - 1`.
                przed_ponowieniem=lambda: _wymagaj_zgody(stan, puls, kryteria.maks),
            )
            _przebieg(
                kanal_obj,
                kontrakt,
                scope,
                store,
                run_id,
                od_strony,
                puls,
                stan,
                licznik,
                decyzja or decyzja_z_flagi(zgoda),
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
        ponowien_lacznie=store.count_requests(run_id, ponowienia=True),
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
    zgoda: _Zgoda,
    licznik: _Licznik,
    decyzja: Decyzja,
    *,
    maks: int | None,
) -> None:
    mapa = mapa_pol(kontrakt)
    wyceniono = False
    for kandydat in kanal.list_candidates(scope, od_strony=od_strony):
        if maks is not None and licznik.kandydatow >= maks:
            return
        if not wyceniono:
            wyceniono = True
            wycena = _wycena(kontrakt, puls, licznik, maks)
            _rozstrzygnij(decyzja(wycena), zgoda, wycena, kontrakt.ponowienia)
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
        szczegoly = odczytaj(surowy.content, mapa)
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
                store.index_document(
                    doc_id, surowy.sha256, metryka(szczegoly), struktura(szczegoly)
                )
            else:
                licznik.bledow_odczytu += 1
            store.link_run_document(run_id, doc_id, position=licznik.pozycja, nowy=True)
            store.checkpoint(run_id, kandydat.strona)
        licznik.nowych += 1
        puls.on_document(licznik.nowych, _przewidywane(puls.razem, maks))


def _wycena(kontrakt: Contract, puls: _Puls, licznik: _Licznik, maks: int | None) -> Wycena:
    return wycen(
        zgloszone=puls.razem,
        maks=maks,
        juz_objetych=licznik.pozycja,
        zadan_juz=puls.zadan,
        na_strone=kontrakt.strony.na_strone,
        odstep_s=kontrakt.tempo.odstep_s,
        okna=[(okno.limit, okno.sekund) for okno in kontrakt.tempo.okna],
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
    decyzja: Decyzja | None = None,
    klient_factory: KlientFactory | None = None,
    klucz_z_srodowiska: bool = True,
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
        decyzja=decyzja,
        klient_factory=klient_factory,
        klucz_z_srodowiska=klucz_z_srodowiska,
        zegar=zegar,
        wznow_run_id=wybrany,
    )
