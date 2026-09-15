"""Strażnik limitera — jedynej bramki, przez którą przechodzi każde żądanie do UZP.

Usterka tego modułu nie objawia się u nas czerwonym ekranem, tylko u kogoś innego
obciążeniem serwera, którego próg tolerancji jest **nieznany** (audyt 2.2: każdy dokument
renderowany na żądanie potokiem Word → HTML → wkhtmltopdf). Dlatego rozkład ciężaru w tym
pliku jest asymetryczny i celowo:

- **Puszczenie żądania za wcześnie waży więcej niż czekanie za długo.** Czekanie widzi
  operator — zdarzenie `on_wait` niesie powód i godzinę wznowienia. Wysłanie za wcześnie
  nie zostawia u nas żadnego śladu; widzi je wyłącznie cudzy serwer. Stąd testy serii
  (`szczyt w oknie`), testy pamięci wstecznej i testy skoku zegara idą po tej stronie.
- **Dziedzina zegara ma strażnika, bo jest twierdzeniem z nagłówka modułu.** Nagłówek mówi,
  że skok zegara systemowego nie skraca ani odstępu, ani okien, ani blokady po 429 dla żądań
  wysłanych **w tym procesie**. Każdy z tych trzech członów ma tu własny test, a obok stoi
  przypadek odwrotny: znaczniki z historii poprzedniego procesu żyją w czasie ściennym
  i skok zegara **je właśnie skraca**. To nie jest ta sama gwarancja i test ma to pokazywać.
- **Cisza jest usterką (7.2).** Limiter, który stoi bez powodu, wypisuje operatorowi pusty
  napis. Test `test_limiter_nigdy_nie_czeka_bez_powodu` przechodzi przez wszystkie pięć
  powodów, które limiter umie zgłosić, i nie pozwala żadnemu z nich zniknąć ze zbioru.

Dwie zależności nie dają się tu zapisać importem, bo moduły po drugiej stronie **jeszcze nie
istnieją** (`store.py`, `ui/`). Oba mają w tym pliku wyzwalacz w kształcie przyjętym
w `tests/test_boundaries.py`: test robi porównanie sam, w dniu w którym drugi moduł powstanie,
a dopóki go nie ma — asertuje, że go nie ma. Czego wyzwalacz nie obejmuje, stoi w komentarzu
przy nim, a nie w tym miejscu.

Sekcja „znaleziska" na końcu pliku to dwa zachowania, w których limiter puszcza żądanie,
którego nie powinien. Stoją jako `xfail(strict=True)`: asercja opisuje zachowanie oczekiwane,
a nie to, które jest — więc dzień, w którym produkcja zostanie poprawiona, kończy się
czerwonym `XPASS` i zdjęciem znacznika, a nie cichym zielonym.

Zero żądań sieciowych. Cały czas jest sterowany `ZegarTestowy`; `--block-network` nie ma tu
czego blokować.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

import pytest

from kio_tool import ratelimit
from kio_tool.errors import ResumableError
from kio_tool.progress import NullEvents
from kio_tool.ratelimit import (
    REASON_BACKOFF,
    REASON_BUDGET,
    REASON_COOLDOWN,
    REASON_RESUME,
    REASON_SPACING,
    REASON_WINDOW,
    WAIT_SLICE_S,
    WSZYSTKIE_POWODY,
    InMemoryHistory,
    LimiterStalledError,
    RateLimiter,
    RequestStamp,
)

PAKIET = Path(__file__).resolve().parent.parent / "kio_tool"

# Tolerancja do porównań **czasu ściennego**. `pytest.approx(x)` ma domyślnie `rel=1e-6`,
# a zegar testowy startuje na 1 700 000 000, więc domyślna tolerancja to ±1700 s: asercja
# „bicie padło na początku postoju" przeszłaby dla bicia spóźnionego o cały plaster (300 s),
# a nawet o trzy. Arytmetyka `ZegarTestowy` jest dokładna, więc na znacznikach porównujemy
# bezwzględnie; na **czasach trwania** (małe liczby) domyślne `approx` zostaje.
TOLERANCJA_ZEGARA_S = 1e-6

# Okna Atlasu z architektury 4.7 — jedyny kanał, który w ogóle publikuje limity.
# W testach służą za realistyczny kształt konfiguracji, nie za pomiar tolerancji UZP.
OKNA_ATLAS: tuple[tuple[int, float], ...] = ((500, 60.0), (1500, 86_400.0))


# ------------------------------------------------------------------- narzędzia testowe


class ZegarTestowy:
    """Zegar sterowany przez test; `sleep` przesuwa czas zamiast czekać.

    Rozdzielenie `advance` (oba zegary) od `jump_wall` (tylko ścienny) jest całym sensem
    tej klasy: skok zegara systemowego to właśnie ruch jednego bez drugiego.
    """

    def __init__(self, start_wall: float = 1_700_000_000.0, start_mono: float = 1000.0) -> None:
        self._wall = start_wall
        self._mono = start_mono
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self._mono

    def wall(self) -> float:
        return self._wall

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._wall += seconds

    def jump_wall(self, seconds: float) -> None:
        """Skok zegara ściennego bez ruchu monotonicznego (NTP, zmiana czasu, ręczna korekta)."""
        self._wall += seconds


class ZegarStojacy(ZegarTestowy):
    """Zegar, który liczy sny, ale nie idzie — zamrożona maszyna wirtualna albo zła atrapa."""

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class Rejestrator(NullEvents):
    """Zapisuje `on_wait` razem z **czasem zegara**, w którym zdarzenie padło.

    Sama kolejność w liście nie odróżnia „przed postojem" od „po postoju": `sleep` przesuwa
    zegar natychmiast, więc zamiana `on_wait` i `_sleep_in_slices` miejscami w `acquire`
    nie zmienia ani kolejności wpisów, ani niczego, co widać bez zegara. Na produkcji ta
    zamiana jest widoczna jako cisza przez cały postój — pasek i dziennik dowiadują się
    o godzinnym czekaniu dopiero po fakcie. Rozróżnia je dopiero znacznik czasu.
    """

    def __init__(self, clock: ZegarTestowy) -> None:
        self.waits: list[tuple[float, str, float]] = []
        self.wait_walls: list[float] = []
        self._clock = clock

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        self.waits.append((seconds, reason, resume_at_epoch))
        self.wait_walls.append(self._clock.wall())

    @property
    def powody(self) -> list[str]:
        return [reason for _, reason, _ in self.waits]


class BicieSerca:
    """Wywołanie zwrotne limitera z zapisem czasu **ściennego** każdego bicia.

    Czas, a nie liczba: pytanie brzmi „jak długo dzierżawa blokady stała bez odświeżenia",
    a to jest odległość między biciami na zegarze, nie ich liczba w liście.
    """

    def __init__(self, clock: ZegarTestowy) -> None:
        self._clock = clock
        self.walle: list[float] = []

    def __call__(self) -> bool:
        self.walle.append(self._clock.wall())
        return True

    def najdluzsza_cisza(self, poczatek: float, koniec: float) -> float:
        """Najdłuższy odcinek, w którym dzierżawa nie dostała ani jednego dotknięcia.

        Liczony od **początku postoju**, a nie od pierwszego bicia: przed wejściem w czekanie
        dzierżawa była właśnie odświeżona, więc od tej chwili biegnie jej wiek. Metryka
        zaczynająca się od pierwszego bicia nie widziałaby pustego odcinka na samym początku,
        czyli dokładnie tego, co robi bicie przesunięte za plaster.
        """
        punkty = [poczatek, *self.walle, koniec]
        return max(b - a for a, b in zip(punkty[:-1], punkty[1:], strict=True))


@pytest.fixture
def clock() -> ZegarTestowy:
    return ZegarTestowy()


def zbuduj(
    clock: ZegarTestowy,
    *,
    spacing: float = 3.6,
    cooldown: float = 185.0,
    windows: tuple[tuple[int, float], ...] = (),
    history: InMemoryHistory | None = None,
    heartbeat: Callable[[], object] | None = None,
    budget_reserve: int = ratelimit.BUDGET_RESERVE_DEFAULT,
) -> tuple[RateLimiter, InMemoryHistory, Rejestrator]:
    """Domyślnie **bez okien** — tak wygląda konfiguracja dla UZP, który nie publikuje limitu."""
    hist = history if history is not None else InMemoryHistory()
    rec = Rejestrator(clock)
    limiter = RateLimiter(
        min_spacing_s=spacing,
        windows=windows,
        cooldown_s=cooldown,
        clock=clock,
        history=hist,
        events=rec,
        heartbeat=heartbeat,
        budget_reserve=budget_reserve,
    )
    return limiter, hist, rec


def przespane_od(clock: ZegarTestowy, od: int) -> float:
    """Suma snów od danego miejsca — kontraktem jest **łączny** postój, nie rozmiar plastra.

    Limiter tnie długie czekanie na plastry po `WAIT_SLICE_S`, więc asercja na `sleeps[-1]`
    mierzyłaby szczegół implementacyjny zamiast tempa, o które w tych testach chodzi.
    """
    return sum(clock.sleeps[od:])


def szczyt_w_oknie(stamps: Sequence[float], span: float) -> int:
    """Najwięcej znaczników mieszczących się w oknie `span` — po wszystkich położeniach okna.

    Półotwarte `(t - span, t]`, czyli ta sama konwencja, której używa `_next_slot`
    (`t > mono_now - span`). Inna konwencja po stronie testu dawałaby różnicę o jeden
    i kłóciłaby się z limiterem o arytmetykę zamiast o tempo.
    """
    best = start = 0
    for i, t in enumerate(stamps):
        while stamps[start] <= t - span:
            start += 1
        best = max(best, i - start + 1)
    return best


def seria(
    clock: ZegarTestowy,
    *,
    spacing: float,
    windows: tuple[tuple[int, float], ...],
    ile: int,
) -> list[float]:
    """Znaczniki monotoniczne żądań, które limiter faktycznie wypuścił.

    To jest jedyny pomiar w tym pliku, który odpowiada na pytanie „co zobaczy cudzy serwer".
    Konfiguracja deklaruje tempo, a wypuszczone znaczniki je pokazują — i te dwie rzeczy
    rozjeżdżały się we wzorcu z CEIDG o jedno żądanie na okno.
    """
    limiter, _, _ = zbuduj(clock, spacing=spacing, windows=windows)
    out: list[float] = []
    for _ in range(ile):
        limiter.acquire("szukaj")
        out.append(clock.monotonic())
    return out


# --------------------------------------------------------- bramka: każde żądanie, także ponowienie


def test_pierwsze_zadanie_idzie_bez_czekania_i_laduje_w_historii(clock: ZegarTestowy) -> None:
    limiter, hist, rec = zbuduj(clock)

    limiter.acquire("szukaj")

    assert clock.sleeps == []
    assert len(hist) == 1
    assert rec.waits == []


def test_odstep_minimalny_dzieli_kolejne_zadania(clock: ZegarTestowy) -> None:
    limiter, _, rec = zbuduj(clock, spacing=3.6)

    limiter.acquire("szukaj")
    clock.advance(1.0)  # odpowiedź przyszła po sekundzie
    limiter.acquire("szukaj")

    assert clock.sleeps == [pytest.approx(2.6)]
    assert rec.powody == [REASON_SPACING]


def test_kazde_zadanie_takze_ponowienie_przechodzi_przez_bramke(clock: ZegarTestowy) -> None:
    """„Jedna bramka dla wszystkich żądań, także ponowień" — liczona w historii, nie w intencji.

    Ponowienie, które omija limiter, jest najgorszym przypadkiem: wysyła się dokładnie wtedy,
    gdy serwer właśnie dał do zrozumienia, że ma dość.
    """
    limiter, hist, _ = zbuduj(clock, spacing=1.0, cooldown=5.0)

    for _ in range(3):
        limiter.acquire("szukaj")
        limiter.note_response(503)
    limiter.acquire("szukaj", extra_delay_s=2.0)

    assert len(hist) == 4


def test_ponowienie_krotsze_niz_odstep_nie_skraca_odstepu(clock: ZegarTestowy) -> None:
    """Drabinka ponowień nie **zastępuje** odstępu, tylko się z nim składa przez maksimum."""
    limiter, _, rec = zbuduj(clock, spacing=10.0)
    limiter.acquire("szukaj")
    przed = len(clock.sleeps)

    limiter.acquire("szukaj", extra_delay_s=2.0)

    assert przespane_od(clock, przed) == pytest.approx(10.0)
    assert rec.powody[-1] == REASON_SPACING


def test_ponowienie_dluzsze_niz_odstep_wydluza_postoj(clock: ZegarTestowy) -> None:
    limiter, _, rec = zbuduj(clock, spacing=10.0)
    limiter.acquire("szukaj")
    przed = len(clock.sleeps)

    limiter.acquire("szukaj", extra_delay_s=30.0)

    assert przespane_od(clock, przed) == pytest.approx(30.0)
    assert rec.powody[-1] == REASON_BACKOFF


@pytest.mark.parametrize("spacing", [0.0, -1.0], ids=["zero", "ujemny"])
def test_odstep_niedodatni_jest_odrzucony(clock: ZegarTestowy, spacing: float) -> None:
    """Odwrotnie niż we wzorcu z CEIDG: tam wymagane były okna, tu odstęp.

    UZP nie publikuje żadnego limitu, więc okno byłoby liczbą wziętą z niczego, a limiter
    bez odstępu nie hamuje w ogóle — konstruktor jest ostatnim miejscem, gdzie widać różnicę
    między „bez okien" a „bez hamulca".
    """
    with pytest.raises(ValueError, match="odstęp minimalny"):
        RateLimiter(
            min_spacing_s=spacing,
            clock=clock,
            history=InMemoryHistory(),
        )


@pytest.mark.parametrize(
    "windows",
    [((0, 180.0),), ((-1, 180.0),), ((5, 0.0),), ((5, -60.0),)],
    ids=["limit_zero", "limit_ujemny", "okres_zero", "okres_ujemny"],
)
def test_okno_niedodatnie_jest_odrzucone(
    clock: ZegarTestowy, windows: tuple[tuple[int, float], ...]
) -> None:
    with pytest.raises(ValueError, match="okno limitera"):
        RateLimiter(
            min_spacing_s=1.0,
            windows=windows,
            clock=clock,
            history=InMemoryHistory(),
        )


def test_limiter_bez_okien_hamuje_samym_odstepem(clock: ZegarTestowy) -> None:
    """Konfiguracja domyślna dla UZP: okien nie ma, bo nie ma czego z nich zrobić."""
    limiter = RateLimiter(min_spacing_s=2.0, clock=clock, history=InMemoryHistory())

    limiter.acquire("szukaj")
    limiter.acquire("szukaj")

    assert clock.sleeps == [pytest.approx(2.0)]


# ------------------------------------------------------------------------- dziedzina zegara
#
# Nagłówek modułu twierdzi: skok zegara systemowego nie skraca ani odstępu, ani okien, ani
# blokady po 429 **dla żądań wysłanych w tym procesie**. Trzy człony, trzy testy — a zaraz
# za nimi przypadek odwrotny, bo dla znaczników z historii to twierdzenie nie obowiązuje
# i nie ma obowiązywać.


def test_skok_zegara_sciennego_nie_skraca_odstepu(clock: ZegarTestowy) -> None:
    limiter, _, _ = zbuduj(clock, spacing=3.6)
    limiter.acquire("szukaj")

    clock.jump_wall(-3600.0)  # zegar cofnięty o godzinę
    limiter.acquire("szukaj")
    assert clock.sleeps[-1] == pytest.approx(3.6)

    clock.jump_wall(+7200.0)  # i skok o dwie do przodu
    limiter.acquire("szukaj")
    assert clock.sleeps[-1] == pytest.approx(3.6)


def test_skok_zegara_sciennego_nie_skraca_okna(clock: ZegarTestowy) -> None:
    """Okno liczone dla własnych żądań procesu — trzy żądania na sto sekund."""
    limiter, _, rec = zbuduj(clock, spacing=1.0, windows=((3, 100.0),))
    for _ in range(3):
        limiter.acquire("szukaj")
        clock.advance(1.0)
    przed = len(clock.sleeps)

    clock.jump_wall(+100_000.0)
    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(97.0)
    assert rec.powody[-1] == REASON_WINDOW


def test_skok_zegara_sciennego_nie_skraca_blokady_po_429(clock: ZegarTestowy) -> None:
    limiter, _, rec = zbuduj(clock, spacing=1.0, cooldown=185.0)
    limiter.acquire("szukaj")
    clock.advance(2.0)
    limiter.note_response(429)
    przed = len(clock.sleeps)

    clock.jump_wall(+100_000.0)
    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(183.0)
    assert rec.powody[-1] == REASON_COOLDOWN


def test_cudze_429_z_historii_obowiazuje_w_tym_procesie(clock: ZegarTestowy) -> None:
    """Blokada przeżywa proces: 429 zebrane przez poprzedni przebieg nadal hamuje."""
    hist = InMemoryHistory([RequestStamp(clock.wall() - 100.0, "szukaj", 429)])
    limiter, _, rec = zbuduj(clock, spacing=1.0, cooldown=185.0, history=hist)

    limiter.acquire("szukaj")

    assert clock.sleeps == [pytest.approx(85.0)]
    assert rec.powody[-1] == REASON_COOLDOWN


def test_skok_zegara_sciennego_skraca_blokade_liczona_z_cudzej_historii(
    clock: ZegarTestowy,
) -> None:
    """Przypadek odwrotny do trzech powyżej — i granica gwarancji z nagłówka modułu.

    Znaczniki z historii są czasem **ściennym**, bo przeżywają proces; nie ma innego czasu,
    w którym dałoby się je zapisać. Przeliczenie do dziedziny monotonicznej idzie więc przez
    `wall_now`, a ten skacze. Godzina przesunięta o 200 s postarza cudze 429 o 200 s
    i blokada, która miała trwać jeszcze 85 s, znika w całości.

    Test stoi tu nie dlatego, że to zachowanie jest dobre, tylko dlatego, że jest **inne**
    niż to, co gwarantuje nagłówek. Gwarancja bez współrzędnych rozlewa się na przypadki,
    których nie obejmuje — a ten akurat kończy się żądaniem wysłanym za wcześnie.
    """
    hist = InMemoryHistory([RequestStamp(clock.wall() - 100.0, "szukaj", 429)])
    limiter, _, rec = zbuduj(clock, spacing=1.0, cooldown=185.0, history=hist)

    clock.jump_wall(+200.0)
    limiter.acquire("szukaj")

    assert clock.sleeps == []
    assert rec.waits == []


def test_znaczniki_z_przyszlosci_sa_pomijane(clock: ZegarTestowy) -> None:
    """Historia z przyszłości to zepsuty zegar, nie ruch — liczenie jej byłoby zgadywaniem."""
    hist = InMemoryHistory(
        [RequestStamp(clock.wall() + 500.0 + i, "szukaj", 200) for i in range(50)]
    )
    limiter, _, _ = zbuduj(clock, spacing=1.0, windows=((5, 60.0),), history=hist)

    limiter.acquire("szukaj")

    assert clock.sleeps == []


def test_cofniecie_zegara_gasi_cala_cudza_historie(clock: ZegarTestowy) -> None:
    """Druga strona pomijania przyszłości: po cofnięciu zegara **cała** historia jest przyszła.

    Okno 5/60 s, dziesięć żądań poprzedniego procesu w ostatnich dziesięciu sekundach —
    po cofnięciu zegara o godzinę limiter rusza bez postoju, bo nie widzi żadnego z nich.
    To jest wysłanie za wcześnie, którego operator nie zobaczy: nie ma zdarzenia `on_wait`,
    nie ma snu, nie ma wpisu w dzienniku. Współrzędne tego zachowania są tutaj, żeby zmiana
    w tym miejscu była świadoma.
    """
    teraz = clock.wall()
    hist = InMemoryHistory([RequestStamp(teraz - 10.0 + i, "szukaj", 200) for i in range(10)])
    limiter, _, rec = zbuduj(clock, spacing=1.0, windows=((5, 60.0),), history=hist)

    clock.jump_wall(-3600.0)
    limiter.acquire("szukaj")

    assert clock.sleeps == []
    assert rec.waits == []


# ------------------------------------------------------------------------ okna i serie żądań


def test_zadanie_ponad_okno_czeka_na_zwolnienie_slotu(clock: ZegarTestowy) -> None:
    limiter, _, rec = zbuduj(clock, spacing=1.0, windows=((3, 100.0),))
    for _ in range(3):
        limiter.acquire("szukaj")
        clock.advance(1.0)
    przed = len(clock.sleeps)

    limiter.acquire("szukaj")

    assert rec.powody[-1] == REASON_WINDOW
    assert przespane_od(clock, przed) == pytest.approx(97.0)


def test_okno_z_poprzedniego_procesu_odtwarza_sie_z_historii(clock: ZegarTestowy) -> None:
    """Poprzedni przebieg wysłał pięć żądań w ostatnich pięciu sekundach i się wywrócił."""
    teraz = clock.wall()
    hist = InMemoryHistory([RequestStamp(teraz - 5.0 + i, "szukaj", 200) for i in range(5)])
    limiter, _, rec = zbuduj(clock, spacing=1.0, windows=((5, 60.0),), history=hist)

    limiter.acquire("szukaj")

    assert rec.powody[-1] == REASON_WINDOW
    assert clock.sleeps[-1] == pytest.approx(55.0)


@pytest.mark.parametrize(
    ("spacing", "windows"),
    [
        (0.05, ((500, 60.0),)),
        (0.5, OKNA_ATLAS),
        (1.0, OKNA_ATLAS),
        (0.02, ((60, 60.0),)),
    ],
    ids=["okno_wiaze", "odstep_wiaze", "jedno_na_sekunde", "waskie_okno"],
)
def test_szczyt_serii_nie_przekracza_zadeklarowanego_okna(
    clock: ZegarTestowy, spacing: float, windows: tuple[tuple[int, float], ...]
) -> None:
    """Pytanie, które boli: ile żądań zobaczył serwer w najgorszym oknie, a nie ile deklarujemy.

    Odstęp mniejszy niż `okres / limit` pozwala nadrabiać postojem i układać serie gęstsze
    niż własne okno — w CEIDG zmierzony szczyt wyniósł 49 przy oknie 48/180 s, czyli o jedno
    ponad własny limit i o jedno poniżej limitu API. Różnica „o jedno" jest tu istotna,
    bo próg tolerancji UZP nie jest zmierzony i nie wiadomo, po której stronie leży.
    """
    stamps = seria(clock, spacing=spacing, windows=windows, ile=1200)

    for limit, span in windows:
        assert szczyt_w_oknie(stamps, span) <= limit, f"okno {limit}/{span:.0f}s"


@pytest.mark.parametrize(
    ("spacing", "na_minute"),
    [(1.0, 60), (0.5, 120)],
    ids=["1_na_sekunde", "2_na_sekunde"],
)
def test_sam_odstep_wyznacza_szczyt_gdy_okien_nie_ma(
    clock: ZegarTestowy, spacing: float, na_minute: int
) -> None:
    """Dwa cudze precedensy z audytu (1 żąd./s i 2 żąd./s) — i to, co z nich wychodzi na minutę.

    Żaden z nich nie jest pomiarem tolerancji UZP; są tym, co robią dwa niezależne kolektory.
    Test pilnuje, żeby odstęp bez okien dawał dokładnie tempo, które deklaruje — bo to jest
    jedyna liczba, jaką operator w tej konfiguracji zobaczy.
    """
    stamps = seria(clock, spacing=spacing, windows=(), ile=300)

    assert szczyt_w_oknie(stamps, 60.0) == na_minute


def test_pamiec_wsteczna_obejmuje_odstep_a_nie_tylko_okna(clock: ZegarTestowy) -> None:
    """Różnica wobec wzorca z CEIDG, z której zniknięcie nie byłoby widoczne inaczej.

    Tam `lookback_s` liczyło się z okien i blokady, bo odstęp był zawsze najkrótszy z trzech.
    Tu odstęp jest hamulcem głównym i bywa **dłuższy** niż okno: przy odstępie 300 s i oknie
    100/60 s pamięć wsteczna licząca się bez odstępu obcięłaby historię do 60 s, cudzy
    znacznik sprzed 100 s zniknąłby z widoku, a limiter wysłałby natychmiast — zamiast
    odczekać brakujące 200 s.
    """
    hist = InMemoryHistory([RequestStamp(clock.wall() - 100.0, "szukaj", 200)])
    limiter, _, rec = zbuduj(
        clock, spacing=300.0, cooldown=60.0, windows=((100, 60.0),), history=hist
    )

    assert limiter.lookback_s == pytest.approx(300.0)

    limiter.acquire("szukaj")

    assert clock.sleeps == [pytest.approx(200.0)]
    assert rec.powody[-1] == REASON_SPACING


# --------------------------------------------------------------------------- blokada po 429


def test_blokada_liczy_sie_od_proby_a_nie_od_odpowiedzi(clock: ZegarTestowy) -> None:
    """Odpowiedź przyszła po dwóch sekundach; te dwie sekundy serwer już odpracował."""
    limiter, _, rec = zbuduj(clock, spacing=1.0, cooldown=185.0)
    limiter.acquire("szukaj")
    clock.advance(2.0)
    limiter.note_response(429)
    przed = len(clock.sleeps)

    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(183.0)
    assert rec.powody[-1] == REASON_COOLDOWN


def test_retry_after_krotszy_nie_skraca_wlasnej_blokady(clock: ZegarTestowy) -> None:
    """Nagłówek serwera wydłuża postój albo nic nie zmienia — skrócić go nie może."""
    limiter, _, _ = zbuduj(clock, spacing=1.0, cooldown=185.0)
    limiter.acquire("szukaj")
    limiter.note_response(429, retry_after_s=30.0)
    przed = len(clock.sleeps)

    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(185.0)


def test_retry_after_krotszy_nie_skraca_blokady_bez_proby_w_historii(clock: ZegarTestowy) -> None:
    """Ta sama gwarancja, ale na drodze, która nie ma drugiego zabezpieczenia.

    Blokada po 429 jest liczona dwa razy: raz w `note_response` (pole `_blocked_until_mono`),
    raz w `_next_slot`, które przechodzi po znacznikach ze statusem 429 i dokłada `cooldown_s`
    do każdego. Dopóki próba jest w historii, druga droga przykrywa pierwszą — i test
    powyżej przeszedłby także wtedy, gdyby `note_response` dało się skrócić nagłówkiem
    (sprawdzone mutacją: `max(cooldown, retry_after)` zamienione na `retry_after or cooldown`
    nie zapala tam niczego).

    Gdy 429 przychodzi z żądania, które nie przeszło przez bramkę, historii nie ma i zostaje
    wyłącznie pierwsza droga. To jest jedyny scenariusz, w którym widać, że `note_response`
    bierze **maksimum**, a nie to, co przysłał serwer.
    """
    limiter, _, rec = zbuduj(clock, spacing=1.0, cooldown=185.0)

    limiter.note_response(429, retry_after_s=30.0)
    limiter.acquire("szukaj")

    assert przespane_od(clock, 0) == pytest.approx(185.0)
    assert rec.powody[-1] == REASON_COOLDOWN


def test_retry_after_dluzszy_jest_honorowany_doslownie(clock: ZegarTestowy) -> None:
    """Architektura 4.7: dobre praktyki Atlasu spełniane przez analogię, dopóki UZP milczy."""
    limiter, _, _ = zbuduj(clock, spacing=1.0, cooldown=185.0)
    limiter.acquire("szukaj")
    limiter.note_response(429, retry_after_s=400.0)
    przed = len(clock.sleeps)

    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(400.0)


def test_status_odpowiedzi_trafia_do_historii(clock: ZegarTestowy) -> None:
    """Bez tego 429 nie przeżyje procesu, a następny przebieg zacznie od uderzenia w mur."""
    limiter, hist, _ = zbuduj(clock, spacing=1.0)
    limiter.acquire("szukaj")

    limiter.note_response(429)

    assert [s.status for s in hist.recent(0.0)] == [429]


def test_odpowiedz_bez_wczesniejszej_proby_nie_wywraca_limitera(clock: ZegarTestowy) -> None:
    """429 z żądania, które nie przeszło przez bramkę — blokada liczy się od teraz."""
    limiter, _, rec = zbuduj(clock, spacing=1.0, cooldown=185.0)

    limiter.note_response(429)
    limiter.acquire("szukaj")

    assert clock.sleeps == [pytest.approx(185.0)]
    assert rec.powody[-1] == REASON_COOLDOWN


# ------------------------------------------------------------------- budżet zgłaszany przez serwer
#
# Własne okna widzą wyłącznie żądania z historii, a limit bywa nałożony na adres IP albo
# konto (Atlas: 1500/dobę/IP, 5000/konto). Sonda, druga maszyna i ręczne wywołanie zużywają
# ten sam budżet niewidzialnie — nagłówki `X-RateLimit-*` są jedynym sygnałem, że tak się dzieje.


def test_niski_budzet_wstrzymuje_do_momentu_resetu(clock: ZegarTestowy) -> None:
    limiter, _, rec = zbuduj(clock, spacing=3.6)
    limiter.acquire("szukaj")
    reset = clock.wall() + 900.0
    przed = len(clock.sleeps)

    assert limiter.note_budget(remaining=3, reset_epoch=reset) == pytest.approx(900.0)

    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(900.0)
    assert rec.powody[-1] == REASON_BUDGET
    assert rec.waits[-1][2] == pytest.approx(reset, abs=TOLERANCJA_ZEGARA_S)


def test_zdrowy_budzet_nic_nie_zmienia(clock: ZegarTestowy) -> None:
    """Hamulec milczy, póki serwer nie zgłosi problemu — inaczej dubluje własne okna."""
    limiter, _, rec = zbuduj(clock, spacing=3.6)

    assert limiter.note_budget(remaining=900, reset_epoch=clock.wall() + 900.0) == 0.0

    limiter.acquire("szukaj")

    assert clock.sleeps == []
    assert REASON_BUDGET not in rec.powody


@pytest.mark.parametrize(
    ("remaining", "hamuje"),
    [(11, False), (10, True), (9, True)],
    ids=["ponad_rezerwe", "rowno_rezerwie", "ponizej_rezerwy"],
)
def test_granica_rezerwy_budzetu(clock: ZegarTestowy, remaining: int, hamuje: bool) -> None:
    """Rezerwa zostaje na ponowienia, których jeszcze nie znamy — granica jest domknięta."""
    limiter, _, _ = zbuduj(clock, spacing=1.0, budget_reserve=10)

    wynik = limiter.note_budget(remaining=remaining, reset_epoch=clock.wall() + 900.0)

    assert (wynik > 0.0) is hamuje


@pytest.mark.parametrize(
    ("remaining", "reset_offset"),
    [(None, 900.0), (3, None), (3, -60.0)],
    ids=["brak_licznika", "brak_resetu", "reset_juz_minal"],
)
def test_hamulec_milczy_bez_dwoch_uzytecznych_liczb(
    clock: ZegarTestowy, remaining: int | None, reset_offset: float | None
) -> None:
    """Zgadywanie godziny postoju z samego licznika byłoby gorsze niż jedno 429."""
    limiter, _, _ = zbuduj(clock, spacing=1.0)
    reset = None if reset_offset is None else clock.wall() + reset_offset

    assert limiter.note_budget(remaining=remaining, reset_epoch=reset) == 0.0

    limiter.acquire("szukaj")
    assert clock.sleeps == []


def test_odlegly_reset_jest_przyciety_do_najdluzszego_okna(clock: ZegarTestowy) -> None:
    """Zepsuty `X-RateLimit-Reset` (sekundy kontra milisekundy) nie zatrzymuje pracy na miesiąc."""
    limiter, _, _ = zbuduj(clock, spacing=1.0, windows=OKNA_ATLAS)

    wynik = limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 30 * 86_400.0)

    assert wynik == pytest.approx(max(span for _, span in OKNA_ATLAS))


def test_bez_okien_reset_jest_przyciety_do_doby(clock: ZegarTestowy) -> None:
    """Domyślna doba, bo najdłuższy znany limit kanału (Atlas: 1500/dobę/IP) jest dobowy."""
    limiter, _, _ = zbuduj(clock, spacing=1.0)

    wynik = limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 30 * 86_400.0)

    assert wynik == pytest.approx(86_400.0)


def test_przyciecie_skraca_postoj_ponizej_tego_co_powiedzial_serwer(clock: ZegarTestowy) -> None:
    """Przy krótkim oknie przycięcie **nie** tnie już zdrowego resetu — poprawka 2026-09-15.

    Historia tego testu jest warta zachowania, bo pokazuje, po co on jest. W pierwszej wersji
    asertował stan zastany: reguła „przycinamy do najdłuższego okna" przyszła z CEIDG, gdzie
    najdłuższe okno miało godzinę, więc przycięcie dotykało wyłącznie resetów absurdalnych.
    Tutaj okna bywają minutowe i kanał z jednym oknem 500/60 s dostawał od serwera „reset za
    900 s", czekał 60 s i wracał pod ten sam wyczerpany budżet — czyli zabezpieczenie przed
    sygnałem niewiarygodnym tłumiło sygnał wiarygodny i prowadziło prosto do 429.

    Po poprawce dolna granica przycięcia jest dobowa (`DOBA_S`), bo najdłuższy znany limit
    kanału — 1500 żądań na dobę na adres IP u pośrednika — jest dobowy. Serwer, który mówi
    „reset za 900 s", zostaje wysłuchany dosłownie.
    """
    limiter, _, _ = zbuduj(clock, spacing=1.0, windows=((500, 60.0),))

    assert limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 900.0) == pytest.approx(
        900.0
    )


def test_absurdalny_reset_nadal_jest_przyciety(clock: ZegarTestowy) -> None:
    """Górna granica zostaje: `reset` odległy o lata jest prawdopodobniej zepsuty niż prawdziwy.

    Poprawka z 2026-09-15 podniosła dolną granicę przycięcia do doby, ale samego przycięcia
    nie zniosła — inaczej jedna zepsuta wartość w nagłówku zatrzymywałaby przebieg na lata.
    Postój nie jest przy tym cichy: `acquire` zgłasza go zdarzeniem `on_wait` z powodem
    i momentem wznowienia, więc wartość absurdalna jest dla operatora widoczna.
    """
    limiter, _, _ = zbuduj(clock, spacing=1.0, windows=((500, 60.0),))

    postoj = limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 365 * 86_400.0)

    assert postoj == pytest.approx(86_400.0)


def test_dluzszy_postoj_wygrywa_gdy_budzet_zglaszany_jest_dwa_razy(clock: ZegarTestowy) -> None:
    """Kolejna odpowiedź nie skraca postoju — inaczej wystarczy jedna z krótszym resetem."""
    limiter, _, _ = zbuduj(clock, spacing=1.0)
    limiter.note_budget(remaining=1, reset_epoch=clock.wall() + 600.0)
    limiter.note_budget(remaining=1, reset_epoch=clock.wall() + 120.0)

    limiter.acquire("szukaj")

    assert przespane_od(clock, 0) == pytest.approx(600.0)


def test_po_wygasnieciu_postoju_budzetowego_limiter_wraca_do_odstepu(
    clock: ZegarTestowy,
) -> None:
    """Postój budżetowy jest jednorazowy; gdyby wracał, przebieg stanąłby na dobre."""
    limiter, _, rec = zbuduj(clock, spacing=1.0)
    limiter.acquire("szukaj")
    limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 600.0)
    limiter.acquire("szukaj")
    przed = len(clock.sleeps)

    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(1.0)
    assert rec.powody == [REASON_BUDGET, REASON_SPACING]


# ------------------------------------------------------------------------------- wznowienie


def test_wznowienie_doplaca_brakujaca_reszte_odstepu(clock: ZegarTestowy) -> None:
    """Pamięć procesu jest pusta, historia nie — i to historia niesie grzeczność przez restart."""
    hist = InMemoryHistory([RequestStamp(clock.wall() - 10.0, "szukaj", 200)])
    limiter, _, _ = zbuduj(clock, spacing=1.0, history=hist)

    assert limiter.enforce_resume_gap(30.0) == pytest.approx(20.0)


def test_wznowienie_po_dlugiej_przerwie_nie_doplaca_nic(clock: ZegarTestowy) -> None:
    hist = InMemoryHistory([RequestStamp(clock.wall() - 500.0, "szukaj", 200)])
    limiter, _, _ = zbuduj(clock, spacing=1.0, history=hist)

    assert limiter.enforce_resume_gap(30.0) == 0.0


def test_wznowienie_bez_historii_nie_doplaca_nic(clock: ZegarTestowy) -> None:
    limiter, _, _ = zbuduj(clock, spacing=1.0)

    assert limiter.enforce_resume_gap(30.0) == 0.0


def test_odstep_wznowienia_jest_egzekwowany_przez_bramke(clock: ZegarTestowy) -> None:
    """Zwrócona liczba to nie wszystko — postój ma faktycznie paść, z własnym powodem."""
    hist = InMemoryHistory([RequestStamp(clock.wall() - 10.0, "szukaj", 200)])
    limiter, _, rec = zbuduj(clock, spacing=1.0, history=hist)
    limiter.enforce_resume_gap(30.0)

    limiter.acquire("szukaj")

    assert clock.sleeps == [pytest.approx(20.0)]
    assert rec.powody[-1] == REASON_RESUME


def test_znacznik_z_przyszlosci_nie_tworzy_postoju_wznowienia(clock: ZegarTestowy) -> None:
    hist = InMemoryHistory([RequestStamp(clock.wall() + 500.0, "szukaj", 200)])
    limiter, _, _ = zbuduj(clock, spacing=1.0, history=hist)

    assert limiter.enforce_resume_gap(30.0) == 0.0


# ------------------------------------------------------------------------ powody czekania (7.2)


def _stale_powodow() -> dict[str, str]:
    return {
        nazwa: wartosc
        for nazwa, wartosc in vars(ratelimit).items()
        if nazwa.startswith("REASON_") and isinstance(wartosc, str)
    }


def test_kazda_stala_powodu_jest_w_zbiorze() -> None:
    """Dopisanie stałej bez dopisania jej do zbioru ucisza komunikat zamiast go zmienić."""
    assert set(_stale_powodow().values()) == set(WSZYSTKIE_POWODY)


def test_powody_nie_powtarzaja_wartosci() -> None:
    """Dwa powody o tej samej wartości to jeden powód i jedno zdanie, którego nikt nie napisze."""
    wartosci = list(_stale_powodow().values())

    assert len(wartosci) == len(set(wartosci))


def test_limiter_nigdy_nie_czeka_bez_powodu(clock: ZegarTestowy) -> None:
    """Każdy postój, jaki limiter umie wywołać, ma nazwę i ta nazwa jest w zbiorze.

    Powód, którego ekran nie umie nazwać, wypisuje się operatorowi jako pusty napis — czyli
    program milczy o tym, dlaczego stoi. Przebieg jest ułożony tak, żeby **każdy** z sześciu
    powodów wypadł raz jako ten najdłuższy: powód zgłoszony to zawsze ograniczenie wiążące,
    więc scenariusz, w którym okno przykrywa blokadę, sprawdziłby jeden powód mniej, niż
    deklaruje. Asercja „żaden nie zniknął" jest tu ważniejsza niż osobne sprawdzenie
    każdego z nich — te stoją w sekcjach wyżej.
    """
    hist = InMemoryHistory([RequestStamp(clock.wall() - 10.0, "szukaj", 200)])
    limiter, _, rec = zbuduj(clock, spacing=1.0, cooldown=30.0, windows=((5, 60.0),), history=hist)

    limiter.enforce_resume_gap(20.0)
    limiter.acquire("szukaj")  # wznowienie: brakująca reszta odstępu po restarcie
    limiter.acquire("szukaj")  # odstęp
    limiter.note_response(429)
    limiter.acquire("szukaj")  # blokada po 429
    limiter.acquire("szukaj")  # odstęp (okno jeszcze niepełne)
    limiter.acquire("szukaj")  # okno 5/60 s, licząc znacznik z poprzedniego procesu
    limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 120.0)
    limiter.acquire("szukaj")  # budżet kanału
    limiter.acquire("szukaj", extra_delay_s=600.0)  # ponowienie

    assert all(rec.powody), "limiter stanął bez powodu"
    assert set(rec.powody) == {
        REASON_RESUME,
        REASON_SPACING,
        REASON_COOLDOWN,
        REASON_WINDOW,
        REASON_BUDGET,
        REASON_BACKOFF,
    }
    assert set(rec.powody) < set(WSZYSTKIE_POWODY), "zbiór ma nieść też powody spoza limitera"


def _powody_nierozpoznane(zrodla: Iterable[Path]) -> dict[str, list[str]]:
    """Powody, których nie widać dosłownie w źródle modułu — po module.

    „Warstwa rysująca rozpoznaje powody po nazwie" znaczy, że nazwa występuje w jej kodzie.
    Skan nie odróżnia dobrego zdania od złego; odróżnia zdanie od jego braku.
    """
    braki: dict[str, list[str]] = {}
    for sciezka in zrodla:
        tekst = sciezka.read_text(encoding="utf-8")
        nieznane = sorted(powod for powod in WSZYSTKIE_POWODY if powod not in tekst)
        if nieznane:
            braki[sciezka.name] = nieznane
    return braki


def _konsumenci_zbioru_powodow(korzen: Path) -> list[Path]:
    """Moduły, które sięgają po `WSZYSTKIE_POWODY` — poza samym limiterem.

    Wykrywanie jest dynamiczne i idzie po całym pakiecie, a nie po zgadniętej ścieżce
    `ui/render.py`: warstwa rysująca może powstać pod inną nazwą, a wtedy strażnik
    przywiązany do ścieżki zostałby cicho pusty.
    """
    return [
        p
        for p in sorted(korzen.glob("**/*.py"))
        if "__pycache__" not in p.parts
        and p.name != "ratelimit.py"
        and "WSZYSTKIE_POWODY" in p.read_text(encoding="utf-8")
    ]


def test_wyzwalacz_kazdy_konsument_zbioru_powodow_zna_wszystkie_powody() -> None:
    """Druga strona zbioru `WSZYSTKIE_POWODY`, której dziś nie ma czym porównać.

    Zbiór istnieje po to, żeby warstwa rysująca miała co asertować — a `kio_tool/ui/` jest
    pusty i nic w pakiecie po ten zbiór nie sięga. Dziś asercja przechodzi więc **pusto**
    i to jest prawda o stanie projektu, nie luka (ADR-0003 5.1). Ciężar niesie wykrywanie:
    jest dynamiczne, więc pierwszy moduł, który sięgnie po `WSZYSTKIE_POWODY`, wchodzi pod
    tę asercję sam, bez zmiany w tym pliku — a że skan nie jest pusty tylko dlatego, że nie
    działa, pilnuje `test_samosprawdzenie_skanu_powodow`.

    Czego ten wyzwalacz **nie** obejmuje: nie sprawdza, czy warstwa rysująca ma dla każdego
    powodu sensowne **zdanie** — tylko czy w ogóle zna jego nazwę. Zdanie jest własnością
    `ui/texts.py` i jego testu, którego nie da się napisać przed powstaniem tekstów.
    Nie obejmuje też odbiorcy, który rozpoznaje powody po **stałych** (`REASON_*`) zamiast
    po wartościach — taki moduł przejdzie ten skan i musi mieć własny test przy sobie.
    """
    braki = _powody_nierozpoznane(_konsumenci_zbioru_powodow(PAKIET))

    assert not braki, f"konsument zbioru nie zna powodów: {braki}"


def test_samosprawdzenie_skanu_powodow(tmp_path: Path) -> None:
    """Pusty skan nie jest zielonym skanem — więc skan musi umieć zapalić się na dowodzie.

    Moduł podrzucony w `tmp_path` zna trzy powody z siedmiu; gdyby skan czytał nie to,
    co trzeba, ten test byłby zielony razem z poprzednim i oba nie znaczyłyby nic.
    """
    znane = [REASON_SPACING, REASON_WINDOW, REASON_COOLDOWN]
    modul = tmp_path / "render.py"
    modul.write_text(
        "from kio_tool.ratelimit import WSZYSTKIE_POWODY\n"
        f"ZDANIA = {{{', '.join(repr(p) for p in znane)}}}\n",
        encoding="utf-8",
    )

    assert _konsumenci_zbioru_powodow(tmp_path) == [modul]
    assert _powody_nierozpoznane([modul]) == {
        "render.py": sorted(set(WSZYSTKIE_POWODY) - set(znane))
    }


# ------------------------------------------------------- sen w plastrach i bicie w dzierżawę


def postoj_dobowy(clock: ZegarTestowy) -> tuple[RateLimiter, Rejestrator, BicieSerca, float]:
    """Limiter tuż przed najdłuższym postojem, jaki umie wywołać — dobą z hamulca budżetowego.

    Bez okien reset jest przycinany do doby, więc to jest górna granica czekania w tym
    module; jeżeli dzierżawa blokady ma gdziekolwiek zgasnąć pod pracującym procesem,
    to właśnie tutaj.
    """
    serce = BicieSerca(clock)
    limiter, _, rec = zbuduj(clock, spacing=1.0, heartbeat=serce)
    limiter.acquire("szukaj")
    limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 86_400.0)
    return limiter, rec, serce, clock.wall()


def test_dobowy_postoj_bije_w_dzierzawe_wiele_razy(clock: ZegarTestowy) -> None:
    """Jedno `sleep(86400)` zabiłoby dzierżawę i zostawiło w dzienniku dziurę.

    Asercja jest o **liczbie bić większej niż jedno** i o tym, że łączny postój się zgadza;
    ile dokładnie plastrów, to szczegół `WAIT_SLICE_S`.
    """
    przed = len(clock.sleeps)
    limiter, _, serce, _ = postoj_dobowy(clock)

    limiter.acquire("szukaj")

    assert len(serce.walle) > 1, "dobowy postój przespany jednym snem"
    assert przespane_od(clock, przed) == pytest.approx(86_400.0)


def test_najdluzsza_cisza_w_postoju_nie_przekracza_plastra(clock: ZegarTestowy) -> None:
    """Sedno plastrowania, mierzone na zegarze — bo to zegar decyduje o wygaśnięciu dzierżawy."""
    limiter, _, serce, start = postoj_dobowy(clock)

    limiter.acquire("szukaj")

    assert serce.najdluzsza_cisza(start, clock.wall()) <= WAIT_SLICE_S


def test_bicie_wyprzedza_plaster_a_nie_idzie_za_nim(clock: ZegarTestowy) -> None:
    """Pierwsze bicie pada, **zanim** proces zaśnie choćby na sekundę.

    Gdyby szło po plastrze, pierwsze odświeżenie wypadałoby `WAIT_SLICE_S` po ostatnim
    dotknięciu dzierżawy — w połowie drogi do wygaśnięcia, zanim cokolwiek zdąży pomóc.
    """
    limiter, _, serce, start = postoj_dobowy(clock)

    limiter.acquire("szukaj")

    assert serce.walle[0] == pytest.approx(start, abs=TOLERANCJA_ZEGARA_S), "pierwsze bicie po śnie"


def test_zapowiedz_postoju_pada_przed_postojem_a_nie_po_nim(clock: ZegarTestowy) -> None:
    """Zamiana `on_wait` z `_sleep_in_slices` jest niewidoczna w kolejności wpisów.

    Na produkcji jest widoczna jako cisza przez cały postój (7.2), więc kolejność mierzymy
    czasem zegara. Druga asercja pilnuje, żeby zapowiedziana godzina wznowienia była liczona
    od chwili zapowiedzi — bo to ona idzie do dziennika i na ekran.
    """
    limiter, rec, _, start = postoj_dobowy(clock)

    limiter.acquire("szukaj")

    assert rec.wait_walls, "limiter nie zapowiedział postoju"
    assert rec.wait_walls[0] == pytest.approx(start, abs=TOLERANCJA_ZEGARA_S)
    assert rec.wait_walls[0] < clock.wall()
    sekundy, _, wznowienie = rec.waits[0]
    assert wznowienie == pytest.approx(rec.wait_walls[0] + sekundy, abs=TOLERANCJA_ZEGARA_S)


def test_krotki_postoj_nie_jest_ciety_na_plastry(clock: ZegarTestowy) -> None:
    """Plastrowanie nie ma zmieniać tempa normalnej pracy.

    Odstęp minimalny pada między każdą parą żądań; gdyby plastrowanie dokładało tu choć
    jedno wywołanie więcej, każdy przebieg płaciłby za to tysiące razy.
    """
    serce = BicieSerca(clock)
    limiter, _, _ = zbuduj(clock, spacing=3.6, heartbeat=serce)
    limiter.acquire("szukaj")
    przed = len(clock.sleeps)

    limiter.acquire("szukaj")

    assert len(serce.walle) == 1
    assert len(clock.sleeps) - przed == 1
    assert przespane_od(clock, przed) == pytest.approx(3.6)


def test_limiter_bez_bicia_serca_dziala_tak_samo(clock: ZegarTestowy) -> None:
    """`heartbeat` jest opcjonalny — sonda fazy 0 i testy budują limiter bez blokady bazy."""
    limiter, _, rec = zbuduj(clock, spacing=1.0)
    limiter.acquire("szukaj")
    limiter.note_budget(remaining=0, reset_epoch=clock.wall() + 86_400.0)
    przed = len(clock.sleeps)

    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(86_400.0)
    assert rec.powody[-1] == REASON_BUDGET


def _stale_dzierzawy(korzen: Path) -> list[tuple[str, str, float]]:
    """Stałe modułowe, które wyglądają na okres wygaśnięcia dzierżawy blokady bazy.

    Czytane przez AST, nie przez import: moduł, który dopiero powstanie, może mieć skutki
    uboczne przy imporcie, a ten strażnik ma działać w dniu jego powstania, nie później.
    """
    wzorce = ("LOCK_STALE", "LEASE", "STALE_S", "DZIERZAW")
    znalezione: list[tuple[str, str, float]] = []
    for sciezka in sorted(korzen.glob("**/*.py")):
        if "__pycache__" in sciezka.parts:
            continue
        drzewo = ast.parse(sciezka.read_text(encoding="utf-8"), filename=str(sciezka))
        for wezel in drzewo.body:
            if not isinstance(wezel, ast.Assign) or not isinstance(wezel.value, ast.Constant):
                continue
            wartosc = wezel.value.value
            if not isinstance(wartosc, int | float) or isinstance(wartosc, bool):
                continue
            for cel in wezel.targets:
                if isinstance(cel, ast.Name) and any(w in cel.id for w in wzorce):
                    znalezione.append((sciezka.name, cel.id, float(wartosc)))
    return znalezione


def test_wyzwalacz_plaster_miesci_sie_pod_dzierzawa_blokady_bazy() -> None:
    """Zależność między dwoma modułami, której nie da się zapisać importem.

    `WAIT_SLICE_S` ma sens wyłącznie dlatego, że jest **mniejszy** niż okres wygaśnięcia
    dzierżawy blokady bazy. Reguła granic zabrania limiterowi znać bazę, więc importu nie
    będzie, a porównanie wyniku z `WAIT_SLICE_S` byłoby tautologią: podniesienie plastra
    do 600 s przeszłoby przez wszystkie pozostałe testy w tym pliku, bo każdy z nich liczy
    swoje oczekiwania z tej samej stałej.

    Drugiej strony nierówności **dziś nie ma**: `store.py` nie istnieje, więc nie istnieje
    też żaden okres dzierżawy. Test robi więc dwie rzeczy: gdy stała się pojawi, porównuje
    ją naprawdę (z marginesem, bo przy plastrze równym połowie dzierżawy jedno spóźnione
    bicie jej nie zabija); dopóki się nie pojawi, asertuje jej brak — i to jest asercja
    o stanie repozytorium, nie o samej stałej, więc nie jest tautologią i zapali się w dniu,
    w którym baza wejdzie.

    Czego ten test **nie** obejmuje, i trzeba to wiedzieć czytając go jako zielony:

    1. Nie dowodzi, że `WAIT_SLICE_S` jest mniejszy od dzierżawy, którą `store.py` dostanie —
       do tego potrzebna jest ta dzierżawa. Dziś niesie tylko gwarancję, że nie da się jej
       dodać po cichu.
    2. Widzi wyłącznie **stałą modułową o czytelnej nazwie** (`*LOCK_STALE*`, `*LEASE*`,
       `*STALE_S*`, `*DZIERZAW*`) z literałem liczbowym — taki kształt miała we wzorcu,
       z którego moduł przeniesiono. Dzierżawa schowana w domyślnym argumencie funkcji,
       w pliku konfiguracyjnym albo w literale SQL przejdzie obok niego niezauważona.
    3. Nie sprawdza, że bicie serca dociera do dzierżawy — sprawdza to, że odstęp między
       biciami jest ograniczony (`test_najdluzsza_cisza_w_postoju_nie_przekracza_plastra`).
       Kto wywołanie zwrotne podepnie i czy podepnie właściwe, jest własnością `pipeline`.
    """
    dzierzawy = _stale_dzierzawy(PAKIET)

    if not dzierzawy:
        assert not (PAKIET / "store.py").exists(), (
            "`store.py` powstał, a skan nie widzi w nim okresu dzierżawy — nazwij stałą tak, "
            "żeby ten test ją widział, albo dopisz porównanie ręcznie"
        )
        return

    for plik, nazwa, wartosc in dzierzawy:
        assert WAIT_SLICE_S < wartosc, f"{plik}:{nazwa} = {wartosc}"
        assert WAIT_SLICE_S <= wartosc / 2, f"{plik}:{nazwa} = {wartosc} — plaster bez marginesu"


def test_samosprawdzenie_skanu_dzierzawy(tmp_path: Path) -> None:
    """Skan, który niczego nie znajduje, i skan, który nie działa, wyglądają tak samo.

    Plik podrzucony w `tmp_path` ma kształt, który miała dzierżawa we wzorcu — stała
    modułowa `DEFAULT_LOCK_STALE_S` z literałem. Ten test jest jedynym miejscem, w którym
    widać, że `_stale_dzierzawy` w ogóle coś znajduje, i jednocześnie zapisuje, czego nie
    znajduje: wartości ukrytej w domyślnym argumencie funkcji.
    """
    (tmp_path / "store.py").write_text(
        "DEFAULT_LOCK_STALE_S = 600.0\n"
        "NIEWIDOCZNA = 'tekst'\n"
        "def open_store(lock_stale_s: float = 30.0) -> None: ...\n",
        encoding="utf-8",
    )

    assert _stale_dzierzawy(tmp_path) == [("store.py", "DEFAULT_LOCK_STALE_S", 600.0)]


# --------------------------------------------------------------------------------- zatrzymanie


def test_zegar_ktory_nie_idzie_konczy_sie_bledem_wznawialnym() -> None:
    """Limiter, który nie doszedł do wolnego slotu, ma się zatrzymać głośno.

    Cicha pętla w tym miejscu jest gorsza niż błąd: kręci się bez końca, nie wysyłając nic,
    a operator widzi proces, który „pracuje". Kod wyjścia 2 znaczy, że harmonogram może
    ponowić — i to jest właściwa odpowiedź na zamrożoną maszynę.
    """
    clock = ZegarStojacy()
    limiter, _, _ = zbuduj(clock, spacing=10.0)
    limiter.acquire("szukaj")

    with pytest.raises(LimiterStalledError) as wyjatek:
        limiter.acquire("szukaj")

    assert isinstance(wyjatek.value, ResumableError)
    assert wyjatek.value.exit_code == 2
    assert "zegar" in str(wyjatek.value)


# ------------------------------------------------------------------- historia w pamięci procesu
#
# `InMemoryHistory` nie jest wyłącznie atrapą testową: nagłówek klasy przewiduje ją dla sond
# fazy 0, czyli dla kodu, który naprawdę wychodzi do UZP.


def test_historia_zwraca_znaczniki_od_podanej_chwili_wlacznie(clock: ZegarTestowy) -> None:
    teraz = clock.wall()
    hist = InMemoryHistory([RequestStamp(teraz - 10.0, "a"), RequestStamp(teraz, "b")])

    assert [s.endpoint for s in hist.recent(teraz - 10.0)] == ["a", "b"]
    assert [s.endpoint for s in hist.recent(teraz - 9.9)] == ["b"]


def test_zapisane_zadanie_nie_ma_jeszcze_statusu() -> None:
    hist = InMemoryHistory()

    hist.record(100.0, "szukaj")

    assert list(hist.recent(0.0)) == [RequestStamp(100.0, "szukaj", None)]


def test_oznaczenie_statusu_trafia_w_znacznik_o_tym_czasie() -> None:
    hist = InMemoryHistory()
    hist.record(100.0, "szukaj")
    hist.record(200.0, "szukaj")

    hist.mark(100.0, 429)

    assert [(s.ts_epoch, s.status) for s in hist.recent(0.0)] == [(100.0, 429), (200.0, None)]


def test_oznaczenie_nieznanego_znacznika_jest_ciche() -> None:
    """Zapis współrzędnych: `mark` bez trafienia nie zgłasza niczego.

    Protokół `RequestHistory` zwraca `None`, więc `note_response` nie ma jak zauważyć, że
    status przepadł — a status, który przepadł, to 429 niewidoczny dla następnego procesu.
    Dla historii w pamięci to sytuacja nieosiągalna (znacznik zawsze pochodzi z `record`),
    ale implementacja w bazie ma tu mieć własne zdanie, zanim odziedziczy tę ciszę.
    """
    hist = InMemoryHistory()
    hist.record(100.0, "szukaj")

    hist.mark(999.0, 429)

    assert [s.status for s in hist.recent(0.0)] == [None]


# ------------------------------------------------------------------------------------ znaleziska
#
# Dwa zachowania, w których limiter puszczał żądanie, którego puścić nie powinien. Oba
# zgłoszone 2026-09-15 jako `xfail(strict=True)` — z asercją opisującą zachowanie oczekiwane,
# nie dzisiejsze — i oba **zamknięte w produkcji tego samego dnia**, więc znaczniki zdjęto.
# Docstringi zachowują opis usterki razem z poprawką: bez opisu usterki poprawka po pół roku
# wygląda na komplikację bez powodu i bywa upraszczana z powrotem.


def test_odstep_ponizej_tolerancji_petli_jest_odrzucany_przy_budowie(
    clock: ZegarTestowy,
) -> None:
    """Konstruktor odrzuca odstęp, którego pętla oczekiwania i tak by nie honorowała.

    `_WAIT_EPSILON_S` istnieje po to, żeby pętla nie kręciła się na resztkach zaokrągleń
    znaczników epoch — i to jest dobry powód. Skutkiem ubocznym jest to, że `min_spacing_s`
    z przedziału (0; 0,005] przechodzi walidację („odstęp minimalny musi być dodatni"),
    po czym nie hamuje **w ogóle**: zmierzone 1000 kolejnych `acquire` bez jednego snu,
    bez jednego zdarzenia `on_wait`, w zerowym czasie zegara.

    Waga tego znaleziska bierze się z konfiguracji domyślnej dla UZP: okna są opcjonalne
    i dla tego kanału ich nie ma, więc odstęp jest **jedynym** hamulcem. Literówka w miejscu
    po przecinku zamieniała limiter w przelotkę, a jedyny obserwator tej zmiany stoi po
    stronie UZP.

    Poprawka z 2026-09-15 przesunęła granicę walidacji z zera na `_WAIT_EPSILON_S`, czyli
    zsunęła w jedno miejsce granicę deklarowaną i granicę faktyczną. Test asertuje odmowę
    **przy budowie**, a nie brak hamowania przy pracy: limiter, którego nie da się zbudować,
    nie ma jak cicho nie hamować.
    """
    with pytest.raises(ValueError, match="odstęp minimalny"):
        zbuduj(clock, spacing=0.004)

    # Granica jest ostra w obie strony: wartość tuż powyżej tolerancji jest legalna
    # i faktycznie hamuje. Bez tej połowy test przechodziłby także wtedy, gdyby konstruktor
    # odrzucał wszystko.
    limiter, _, _ = zbuduj(clock, spacing=0.006)
    limiter.acquire("szukaj")
    przed = len(clock.sleeps)
    limiter.acquire("szukaj")

    assert przespane_od(clock, przed) == pytest.approx(0.006)


def test_szczyt_nie_przekracza_okna_gdy_odstep_rowna_sie_okresowi_na_zadanie(
    clock: ZegarTestowy,
) -> None:
    """Dokładnie ten kształt kosztował w CEIDG jedno żądanie na okno — tu jest powtarzalny.

    Przy `min_spacing_s == okres / limit` oba hamulce wiążą w tym samym punkcie, a odstępy
    liczone są przez dodawanie liczb zmiennoprzecinkowych (0,12 nie ma dokładnej postaci
    binarnej). Narastający niedomiar rzędu 1e-13 s na krok sprawia, że najstarszy znacznik
    okna nie zdążył z niego wyjść, gdy wchodzi nowy: zmierzony szczyt to 501 żądań na 60 s
    przy oknie zadeklarowanym jako 500/60 s. Powtarzalne — trzy przebiegi, ten sam wynik.

    Skala jest jednym żądaniem na okno i to jest cała różnica między „mieścimy się w limicie"
    a „przekraczamy go o jedno" — czyli między liczbą, którą można komuś pokazać, a liczbą,
    której nie można. Przy nieznanym progu tolerancji UZP nie ma podstaw, żeby uznać ją
    za nieistotną.

    Zamknięte 2026-09-15 **względnym** marginesem granicy okna (`_MARGINES_OKNA_WZGLEDNY`),
    rozszerzającym zarówno przynależność do okna, jak i moment zwolnienia slotu. Margines
    jest względny, a nie stały, bo dryf jest proporcjonalny do długości okna: dla okna
    minutowego to 60 ns wobec dryfu rzędu 5e-11 s. Stały epsilon 5 ms załatwiłby to samo,
    ale przesuwałby każde czekanie na oknie o wartość widoczną w testach i w dzienniku —
    czyli płaciłby widocznością za dryf niewidoczny.
    """
    stamps = seria(clock, spacing=60.0 / 500, windows=((500, 60.0),), ile=1200)

    assert szczyt_w_oknie(stamps, 60.0) <= 500
