"""Limiter żądań: okna przesuwne, odstęp minimalny, blokada po 429, budżet z nagłówków.

Przeniesione z `ceidg-tool`. Problem jest identyczny — długa operacja przeciw cudzemu
serwerowi — ale materiał zmienia wagę dwóch rzeczy:

- **Odstęp minimalny waży tu więcej niż okna.** W CEIDG limit był nakładany na token
  i wyrażony w żądaniach na godzinę. Tutaj UZP nie publikuje żadnego limitu, a to, co mamy,
  to dwa cudze precedensy (1 żąd./s i 2 żąd./s z dwóch niezależnych kolektorów) — **żaden
  z nich nie jest pomiarem tolerancji serwisu**. Dlatego domyślnym hamulcem jest odstęp,
  a okna są opcjonalne i wchodzą dopiero tam, gdzie kanał je publikuje (Atlas: 500/min,
  1500/dobę/IP, 5000/konto).
- **Każde żądanie kosztuje cudzy serwer więcej niż odczyt z bazy.** Wyszukiwarka UZP renderuje
  treść dokumentów na żądanie potokiem Word → HTML → wkhtmltopdf (audyt 2.2), więc profil
  obciążenia jest inny niż przy API zwracającym gotowy rekord. Próg tolerancji jest nieznany
  i to jest brak pomiaru, nie stwierdzenie, że progu nie ma.

Obliczenia idą w dziedzinie zegara **monotonicznego**: własne żądania procesu są pamiętane
monotonicznie, a znaczniki z historii (czas ścienny, także z poprzednich procesów) przeliczane
przy każdym wywołaniu. Skok zegara systemowego nie skraca więc ani odstępu, ani okien, ani
blokady po 429 dla żądań wysłanych w tym procesie.

Czego w tej wersji nie ma wobec wzorca: powodu czekania „model". W CEIDG warstwa modelu żyła
w tym samym procesie i miała własną drabinkę ponowień; tutaj faza 4 jest osobnym procesem
(architektura 4.10), więc ten powód nie miałby kto zgłosić.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from .clock import Clock
from .errors import ResumableError
from .progress import Events, NullEvents

REASON_SPACING = "odstep"
REASON_WINDOW = "okno_limitu"
REASON_COOLDOWN = "blokada_429"
REASON_BACKOFF = "ponowienie"
REASON_RESUME = "wznowienie"
REASON_BUDGET = "budzet_kanalu"
# Powód spoza limitera, ale z tego samego zbioru: warstwa rysująca rozpoznaje wszystkie po
# nazwie i musi je brać z jednego miejsca, inaczej zmiana wartości ucisza komunikat zamiast
# go zmienić.
REASON_NO_CONNECTION = "brak_polaczenia"

WSZYSTKIE_POWODY = frozenset(
    {
        REASON_SPACING,
        REASON_WINDOW,
        REASON_COOLDOWN,
        REASON_BACKOFF,
        REASON_RESUME,
        REASON_BUDGET,
        REASON_NO_CONNECTION,
    }
)
"""Zbiór istnieje po to, żeby warstwa rysująca miała co asertować.

Powód czekania, którego ekran nie umie nazwać, wypisuje się operatorowi jako pusty napis —
czyli program milczy o tym, dlaczego stoi. Doktryna 7.2 nazywa ciszę usterką, więc test
porównuje ten zbiór z tym, co rozpoznaje warstwa rysująca, zamiast liczyć na czujność autora.
"""

BUDGET_RESERVE_DEFAULT = 10
"""Ile żądań z budżetu zgłaszanego przez serwer zostawiamy nietkniętych.

Własne okna limitera liczą wyłącznie żądania, które przeszły przez historię. Limit bywa
jednak nakładany na **adres IP albo konto**, więc sonda, druga maszyna albo ręczne wywołanie
zużywają ten sam budżet, a limiter ich nie widzi. Nagłówki `X-RateLimit-*` (Atlas) są jedynym
źródłem prawdy o tym zużyciu; rezerwa zostaje na ponowienia, których jeszcze nie znamy.
"""

WAIT_SLICE_S = 300.0
"""Najdłuższy pojedynczy sen limitera.

Musi być **mniejszy** niż okres wygaśnięcia dzierżawy blokady bazy, inaczej dzierżawa gaśnie
w środku czekania. W `ceidg-tool` jedno `sleep(3600)` zabijało ją pod pracującym procesem
i zostawiało w dzienniku dziurę nie do odróżnienia od uśpionej maszyny. Zależności nie da się
zapisać importem, bo reguła granic zabrania limiterowi znać bazę — pilnuje jej test, a samo
porównanie wyniku z tą stałą byłoby tautologią.
"""

DOBA_S = 86_400.0
"""Dolna granica przycięcia postoju budżetowego.

Najdłuższy znany limit kanału jest dobowy (Atlas: 1500 żądań na dobę na adres IP), więc
przycięcie krótsze niż doba potrafiłoby stłumić reset zdrowy — patrz `note_budget`.
"""

# Znaczniki epoch (~1,7e9) mają w float precyzję ~2,4e-7 s; bez tolerancji pętla oczekiwania
# mogłaby kręcić się na resztkach zaokrągleń. Ta sama stała wyznacza dolną granicę odstępu
# minimalnego w konstruktorze — inaczej walidacja i zachowanie rozjeżdżałyby się o tę wartość.
_WAIT_EPSILON_S = 0.005
_MAX_WAIT_ITERATIONS = 1000

# Względny margines granicy okna. Pokrywa narastający niedomiar zmiennoprzecinkowy
# przy odstępie równym `span / limit`; uzasadnienie liczby stoi przy użyciu.
_MARGINES_OKNA_WZGLEDNY = 1e-9


class LimiterStalledError(ResumableError):
    """Limiter nie doszedł do wolnego slotu — niespójny zegar albo historia."""


@dataclass(frozen=True)
class RequestStamp:
    """Jedno żądanie w historii: czas ścienny (epoch), punkt końcowy, status (None = w toku)."""

    ts_epoch: float
    endpoint: str
    status: int | None = None


class RequestHistory(Protocol):
    """Historia żądań dla danego kanału.

    Protokół, a nie klasa bazowa, bo limiter nie ma prawa znać bazy (reguła granic 2):
    w produkcji historię trzyma `store`, w testach i sondach wystarcza pamięć procesu.
    """

    def recent(self, since_epoch: float) -> Sequence[RequestStamp]: ...

    def record(self, ts_epoch: float, endpoint: str) -> None: ...

    def mark(self, ts_epoch: float, status: int) -> None: ...


class InMemoryHistory:
    """Historia w pamięci procesu — do testów i do sond fazy 0."""

    def __init__(self, initial: Sequence[RequestStamp] = ()) -> None:
        self._items: list[RequestStamp] = list(initial)

    def recent(self, since_epoch: float) -> Sequence[RequestStamp]:
        return [s for s in self._items if s.ts_epoch >= since_epoch]

    def record(self, ts_epoch: float, endpoint: str) -> None:
        self._items.append(RequestStamp(ts_epoch, endpoint))

    def mark(self, ts_epoch: float, status: int) -> None:
        for i in range(len(self._items) - 1, -1, -1):
            if self._items[i].ts_epoch == ts_epoch:
                self._items[i] = RequestStamp(ts_epoch, self._items[i].endpoint, status)
                return

    def __len__(self) -> int:
        return len(self._items)


class RateLimiter:
    """Jedna bramka dla wszystkich żądań, także ponowień."""

    def __init__(
        self,
        *,
        min_spacing_s: float,
        windows: Sequence[tuple[int, float]] = (),
        cooldown_s: float = 60.0,
        clock: Clock,
        history: RequestHistory,
        events: Events | None = None,
        budget_reserve: int = BUDGET_RESERVE_DEFAULT,
        # Wywołanie zwrotne, a nie zdarzenie: niesie bicie serca dzierżawy blokady, a blokada
        # należy do `pipeline` (reguła granic 5) — limiter nie ma prawa znać bazy.
        heartbeat: Callable[[], object] | None = None,
    ) -> None:
        # Okna są **opcjonalne**, a odstęp wymagany — odwrotnie niż we wzorcu z CEIDG.
        # Powód jest w nagłówku modułu: UZP nie publikuje żadnego limitu, więc okno byłoby
        # liczbą wziętą z niczego, a odstęp jest jedynym hamulcem, który da się uzasadnić.
        #
        # Granica walidacji to `_WAIT_EPSILON_S`, a nie zero, i to jest poprawka z 2026-09-15.
        # Pierwsza wersja odrzucała tylko wartości niedodatnie, a pętla oczekiwania honoruje
        # dopiero postoje **powyżej** epsilona — więc `min_spacing_s=0.004` przechodziło
        # walidację i nie hamowało w ogóle: tysiąc kolejnych `acquire` bez jednego snu i bez
        # jednego zdarzenia `on_wait`. Dwa różne miejsca wyznaczały granicę i rozjeżdżały się
        # o cztery tysięczne, a przy kanale bez okien odstęp jest **jedynym** hamulcem, więc
        # literówka w miejscu po przecinku zamieniała limiter w przelotkę. Jedynym obserwatorem
        # takiej zmiany jest cudzy serwer.
        if min_spacing_s <= _WAIT_EPSILON_S:
            raise ValueError(
                f"odstęp minimalny musi przekraczać {_WAIT_EPSILON_S} s, a wynosi "
                f"{min_spacing_s}; krótszy nie zatrzyma ani jednego żądania, bo pętla "
                "oczekiwania traktuje go jak zero — a przy kanale bez okien jest to jedyny "
                "hamulec, jaki ten limiter ma."
            )
        for limit, span in windows:
            if limit <= 0 or span <= 0:
                raise ValueError(f"okno limitera musi być dodatnie: ({limit}, {span})")
        self._windows = tuple((int(limit), float(span)) for limit, span in windows)
        self._min_spacing_s = float(min_spacing_s)
        self._cooldown_s = float(cooldown_s)
        self._clock = clock
        self._history = history
        self._events: Events = events or NullEvents()
        self._own: list[tuple[float, float, int | None]] = []  # (mono, wall, status)
        self._last_attempt_mono: float | None = None
        self._last_attempt_wall: float | None = None
        self._blocked_until_mono: float | None = None
        self._resume_until_mono: float | None = None
        self._budget_reserve = int(budget_reserve)
        self._budget_until_mono: float | None = None
        self._heartbeat = heartbeat

    @property
    def lookback_s(self) -> float:
        spans = [span for _, span in self._windows]
        return max([*spans, self._cooldown_s, self._min_spacing_s])

    def _sleep_in_slices(self, wait: float) -> None:
        """Przesypia `wait` w plastrach, bijąc w dzierżawę przed każdym z nich.

        Bicie idzie **przed** plastrem, nie po nim — tak samo jak zdarzenie `on_wait` wyprzedza
        całe czekanie. Dzięki temu najdłuższa przerwa między dwoma biciami to `WAIT_SLICE_S`,
        a nie długość postoju.
        """
        pozostalo = wait
        while pozostalo > _WAIT_EPSILON_S:
            if self._heartbeat is not None:
                self._heartbeat()
            plaster = min(pozostalo, WAIT_SLICE_S)
            self._clock.sleep(plaster)
            pozostalo -= plaster

    def acquire(self, endpoint: str, *, extra_delay_s: float = 0.0) -> None:
        """Blokuje do chwili, gdy żądanie jest dozwolone, i zapisuje próbę w historii."""
        backoff_until: float | None = (
            self._clock.monotonic() + extra_delay_s if extra_delay_s > 0 else None
        )
        for _ in range(_MAX_WAIT_ITERATIONS):
            wait, reason, resume_at_wall = self._next_slot(backoff_until)
            if wait <= _WAIT_EPSILON_S:
                break
            self._events.on_wait(wait, reason, resume_at_wall)
            self._sleep_in_slices(wait)
        else:
            raise LimiterStalledError(
                "Limiter nie doszedł do wolnego slotu — sprawdź zegar systemowy i historię "
                "żądań, potem wznów przebieg."
            )

        wall = self._clock.wall()
        mono = self._clock.monotonic()
        self._history.record(wall, endpoint)
        self._own.append((mono, wall, None))
        self._own = [entry for entry in self._own if entry[0] > mono - self.lookback_s]
        self._last_attempt_mono = mono
        self._last_attempt_wall = wall
        self._blocked_until_mono = None

    def enforce_resume_gap(self, gap_s: float) -> float:
        """Po wznowieniu: brakująca reszta `gap_s` od ostatniego żądania z historii.

        Zwraca liczbę sekund do odczekania (0, gdy ostatnie żądanie było dawno). Istnieje,
        bo wznowienie przerwanego przebiegu nie może zacząć od serii żądań bez odstępu tylko
        dlatego, że pamięć procesu jest pusta — historia przeżywa proces, a grzeczność ma
        przeżyć razem z nią.
        """
        mono_now = self._clock.monotonic()
        wall_now = self._clock.wall()
        stamps = [
            s.ts_epoch for s in self._history.recent(wall_now - gap_s) if s.ts_epoch <= wall_now
        ]
        if not stamps:
            return 0.0
        last_mono = mono_now - (wall_now - max(stamps))
        self._resume_until_mono = last_mono + gap_s
        return max(0.0, self._resume_until_mono - mono_now)

    def note_response(self, status: int, retry_after_s: float | None = None) -> None:
        """Rejestruje status; 429 uruchamia blokadę liczoną od ostatniej próby.

        `retry_after_s` pochodzi z nagłówka `Retry-After` i jest **honorowany dosłownie**, gdy
        jest dłuższy niż własna blokada. Atlas wymienia to wprost wśród dobrych praktyk dla
        klientów, a adapter UZP ma je spełniać przez analogię, dopóki UZP nie określi własnych
        warunków (architektura 4.7).
        """
        if self._last_attempt_wall is not None:
            self._history.mark(self._last_attempt_wall, status)
        if self._own:
            mono, wall, _ = self._own[-1]
            self._own[-1] = (mono, wall, status)
        if status == 429:
            base = (
                self._last_attempt_mono
                if self._last_attempt_mono is not None
                else self._clock.monotonic()
            )
            self._blocked_until_mono = base + max(self._cooldown_s, retry_after_s or 0.0)

    def note_budget(self, remaining: int | None, reset_epoch: float | None) -> float:
        """Hamulec oparty na budżecie, który raportuje serwer (`X-RateLimit-*`).

        Własne okna widzą tylko żądania z historii, a limit bywa nałożony na adres IP albo
        konto — sonda albo druga maszyna zużywają go niewidzialnie. Gdy serwer mówi, że
        zostało mniej niż rezerwa, czekamy do jego własnego momentu resetu zamiast dobijać
        do 429.

        Hamuje wyłącznie, gdy znane są **obie** liczby: bez czasu resetu nie wiadomo, jak długo
        czekać, a zgadywanie godziny postoju na podstawie samego licznika byłoby gorsze od
        jednego 429.

        **Przycięcie postoju ma dolną granicę dobową i to jest poprawka z 2026-09-15.**
        Wersja przeniesiona z CEIDG przycinała do najdłuższego okna, bo tam najdłuższe okno
        miało godzinę. Tutaj okna bywają minutowe, a wtedy zabezpieczenie przed zepsutym
        `X-RateLimit-Reset` tłumiło reset **zdrowy**: kanał z jednym oknem 500/60 s dostawał
        „reset za 900 s", czekał 60 s i wracał pod ten sam wyczerpany budżet, dobijając do 429
        — czyli dokładnie do tego, czemu ten hamulec miał zapobiec. Dolna granica jest dobowa,
        bo najdłuższy znany limit kanału (Atlas: 1500 na dobę na adres IP) jest dobowy.

        Górna granica zostaje, bo `reset` odległy o lata jest prawdopodobniej zepsuty niż
        prawdziwy. Postój nie jest przy tym cichy: `acquire` zgłasza go zdarzeniem `on_wait`
        z powodem i momentem wznowienia, więc wartość absurdalna jest dla operatora widoczna,
        a nie tłumiona po cichu.

        Zwraca długość ustawionego postoju w sekundach (0 = brak hamowania).
        """
        if remaining is None or reset_epoch is None or remaining > self._budget_reserve:
            return 0.0
        longest = max((span for _, span in self._windows), default=0.0)
        wait = min(max(0.0, reset_epoch - self._clock.wall()), max(longest, DOBA_S))
        if wait <= 0.0:
            return 0.0
        candidate = self._clock.monotonic() + wait
        if self._budget_until_mono is None or candidate > self._budget_until_mono:
            self._budget_until_mono = candidate
        return wait

    def _next_slot(self, backoff_until: float | None) -> tuple[float, str, float]:
        """Zwraca (ile czekać, powód, kiedy wznowić [epoch]); 0 = można wysyłać."""
        mono_now = self._clock.monotonic()
        wall_now = self._clock.wall()
        since = wall_now - self.lookback_s
        own_walls = {wall for _, wall, _ in self._own}

        # Znaczniki cudze (inny proces) z historii przeliczamy do dziedziny monotonicznej;
        # „przyszłe" (skok zegara) pomijamy. Własne bierzemy wprost z pamięci procesu.
        history_mono: list[tuple[float, int | None]] = [
            (max(0.0, mono_now - (wall_now - s.ts_epoch)), s.status)
            for s in self._history.recent(since)
            if s.ts_epoch <= wall_now and s.ts_epoch not in own_walls
        ]
        history_mono.extend((mono, status) for mono, _, status in self._own)
        history_mono.sort(key=lambda pair: pair[0])

        earliest = mono_now
        reason = ""

        last_mono = max((t for t, _ in history_mono), default=None)
        if self._last_attempt_mono is not None:
            last_mono = (
                self._last_attempt_mono
                if last_mono is None
                else max(last_mono, self._last_attempt_mono)
            )
        if last_mono is not None and last_mono + self._min_spacing_s > earliest:
            earliest, reason = last_mono + self._min_spacing_s, REASON_SPACING

        for limit, span in self._windows:
            # Granica okna jest rozszerzona o **względny** margines, w obie strony:
            # żądanie leżące na krawędzi liczy się jako będące w oknie, a moment zwolnienia
            # slotu wypada o tyleż później. Poprawka z 2026-09-15.
            #
            # Powód: przy odstępie równym `span / limit` oba hamulce wiążą w tym samym
            # punkcie, a odstępy liczy się przez dodawanie liczb zmiennoprzecinkowych
            # (0,12 nie ma dokładnej postaci binarnej). Narastający niedomiar rzędu 1e-13 s
            # na krok sprawiał, że najstarsze żądanie wypadało z okna o włos za wcześnie
            # i do okna wchodziło jedno żądanie **ponad limit** — zmierzone 501 na 60 s przy
            # oknie zadeklarowanym jako 500/60 s, powtarzalnie.
            #
            # Margines jest względny, a nie stały, bo ma pokryć dryf proporcjonalny do
            # długości okna, a nie do zegara. Dla okna minutowego to 60 ns wobec dryfu rzędu
            # 5e-11 s — z zapasem trzech rzędów wielkości, a jednocześnie o rzędy wielkości
            # poniżej tolerancji, z jaką ktokolwiek mierzy postoje. Stały epsilon 5 ms
            # załatwiłby to samo, ale przesuwałby **każde** czekanie na oknie o wartość
            # widoczną w testach i w dzienniku, czyli płaciłby widocznością za dryf
            # niewidoczny.
            #
            # Rozstrzygnięcie remisu idzie świadomie w stronę „policz i poczekaj", a nie
            # „wypuść": czekanie o nanosekundę za długo nie widzi nikt, a wysłanie o jedno
            # żądanie za dużo widzi cudzy serwer.
            margines = span * _MARGINES_OKNA_WZGLEDNY
            in_window = [t for t, _ in history_mono if t > mono_now - span - margines]
            if len(in_window) >= limit:
                candidate = in_window[-limit] + span + margines
                if candidate > earliest:
                    earliest, reason = candidate, REASON_WINDOW

        blocked = self._blocked_until_mono
        for t, status in history_mono:
            if status == 429:
                candidate = t + self._cooldown_s
                blocked = candidate if blocked is None else max(blocked, candidate)
        if blocked is not None and blocked > earliest:
            earliest, reason = blocked, REASON_COOLDOWN

        if self._budget_until_mono is not None and self._budget_until_mono > earliest:
            earliest, reason = self._budget_until_mono, REASON_BUDGET

        if self._resume_until_mono is not None and self._resume_until_mono > earliest:
            earliest, reason = self._resume_until_mono, REASON_RESUME

        if backoff_until is not None and backoff_until > earliest:
            earliest, reason = backoff_until, REASON_BACKOFF

        wait = earliest - mono_now
        return wait, reason, wall_now + max(wait, 0.0)
