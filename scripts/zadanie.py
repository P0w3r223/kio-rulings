"""Środowisko sondy fazy 0 i jedno żądanie: skąd biorą się zegar, klient, limiter i kronika.

Pomiary (`pomiar_saos.py`, `pomiar_uzp.py`, `pomiar_licencje.py`, `sonda.pomiar_atlas`) biorą
te cztery rzeczy **wyłącznie z fabryk tego modułu** — `zegar()`, `klient()`, `limiter()`,
`kronika()` — i to jest cała treść jego istnienia. Test podstawia `zadanie.SystemClock`,
`zadanie.build_http_client`, `zadanie.KATALOG_WYJSCIA` i `zadanie.DZIENNIK` w jednym module,
a nie w sześciu; pomiar, który zbudowałby klienta albo zegar obok fabryki, ominąłby
piaskownicę testów bez śladu.

Trzy rzeczy, które `wykonaj` robi inaczej niż zwykłe żądanie, każda z powodem w nagłówku
`sonda.py`: wychodzi przez bramkę wyjścia pakietu (reguła 11), trzyma tempo przez
`RateLimiter`, zapisuje surową odpowiedź na dysk **zanim** cokolwiek z niej wyciągnie.

Moduł obok, nie w pakiecie: ścieżki `scripts/out/` i `docs/dziennik_zadan.md` oraz tempa
startowe są ustaleniami sondy fazy 0, a po bramce wyboru kanału ich miejsce jest w `pipeline`
i `contract.yaml`, nie w `logbook`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

import httpx

from kio_tool.clock import Clock, SystemClock, utc_iso
from kio_tool.console import PulsKonsoli
from kio_tool.httpclient import NAGLOWEK_RETRY_AFTER, build_http_client, parse_retry_after
from kio_tool.ksztalt import Ksztalt
from kio_tool.logbook import KODY_ODMOWY, Kronika, Wynik, zapisz_surowe
from kio_tool.ratelimit import InMemoryHistory, RateLimiter

KATALOG_WYJSCIA = Path(__file__).resolve().parent / "out"
"""Surowe odpowiedzi lądują tu, a nie w `tests/examples/`.

Do `tests/examples/` trafiają **po przejrzeniu okiem** i razem z `*.compare.json` — bo reguła
17 mówi o dowodzie przejrzanym przez człowieka, a nie o wszystkim, co wpadło. `scripts/out/`
jest w `.gitignore` właśnie po to, żeby ta granica nie zatarła się przez przypadek.
"""

DZIENNIK = Path(__file__).resolve().parent.parent / "docs" / "dziennik_zadan.md"
"""Dziennik żądań — **w historii repozytorium**, w przeciwieństwie do `scripts/out/`.

Reguła zgody (architektura 4.1, audyt 13.2 pkt 4) mówi: pojedynczy odczyt diagnostyczny nie
wymaga zgody, ale zawsze zostawia wpis w dzienniku. Dopóki nie ma bazy, dziennikiem jest ten
plik i niesie kolumny `requests_log` z modelu danych 4.4. Adres idzie przez `mask_tokens`,
bo `requests_log` trzyma `url_redacted`, a nie `url`.
"""


# Tempo startowe dla UZP. To jest **precedens z dwóch cudzych kolektorów (1 i 2 żąd./s),
# nie pomiar tolerancji serwisu** — pomiar 9 dopiero ma je zmierzyć. Sonda jedzie wolniej
# niż wolniejszy z precedensów, bo pojedynczy odczyt diagnostyczny nie ma powodu się spieszyć.
ODSTEP_UZP_S = 2.0
ODSTEP_POSREDNIK_S = 1.0

LIMIT_CZASU_S = 45.0
"""Dłuższy niż domyślny limit narzędzia: sonda dotyka punktów, których nikt jeszcze nie
zmierzył, a przekroczenie czasu jest tu wynikiem pomiaru, nie awarią do ukrycia."""


# --- fabryki: jedyne miejsce, z którego pomiary biorą zegar, klienta, limiter i kronikę ----


def zegar() -> Clock:
    """Zegar systemowy; fabryka po to, żeby test podstawiał `zadanie.SystemClock` raz."""
    return SystemClock()


def klient(ua: str, hosty: frozenset[str]) -> httpx.Client:
    """Klient jednego kanału: przez bramkę wyjścia pakietu, z limitem czasu sondy."""
    return build_http_client(user_agent=ua, allowed=hosty, timeout=LIMIT_CZASU_S)


def limiter(odstep_s: float) -> RateLimiter:
    """Limiter z głosem: `PulsKonsoli` zamiast domyślnego `NullEvents`.

    Do przeglądu 2026-09-17 limiter dostawał `NullEvents`, więc sonda milczała przez cały
    postój — po statusie 429 nawet przez plastry po 300 s. Skreślenie `events=` z powrotem nie
    psuje żadnego pomiaru i nie wypisuje nic; jedynym obserwatorem jest test w `test_zadanie.py`.
    """
    return RateLimiter(
        min_spacing_s=odstep_s,
        clock=zegar(),
        history=InMemoryHistory(),
        events=PulsKonsoli(),
    )


def kronika() -> Kronika:
    """Kronika przebiegu ze ścieżkami tego modułu i zegarem z `zegar()`."""
    return Kronika.na_teraz(zegar(), dziennik=DZIENNIK, katalog_wyjscia=KATALOG_WYJSCIA)


# --- jedno żądanie ------------------------------------------------------------------------


def wykonaj(
    klient: httpx.Client,
    limiter: RateLimiter,
    kronika: Kronika,
    *,
    nazwa: str,
    metoda: str,
    adres: str,
    rozszerzenie: str,
    ksztalt: Ksztalt | None = None,
    uwaga: str = "",
    params: Mapping[str, str | int] | None = None,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Wynik:
    """Jedno żądanie: przez limiter, przez bramkę wyjścia, z zapisem, skrótem i oceną kształtu.

    Parametry żądania są wyliczone, a nie zebrane w `**kwargs: object`, i to jest poprawka
    z przeglądu 2026-09-17. Worek `kwargs` wymagał `type: ignore[arg-type]` dokładnie na
    wywołaniu wychodzącym do sieci, więc literówka w nazwie (`param=` zamiast `params=`)
    przechodziła przez `mypy --strict` i wywracała się dopiero w przebiegu — po `acquire`,
    czyli po zapłaceniu za odstęp.
    """
    limiter.acquire(nazwa)
    zegar_zadania = zegar()
    start = zegar_zadania.monotonic()
    znacznik = utc_iso(zegar_zadania.wall()).replace("-", "").replace(":", "")
    try:
        odpowiedz = klient.request(metoda, adres, params=params, data=data, headers=headers)
    except httpx.HTTPError as blad:
        return kronika.zanotuj(
            Wynik(
                nazwa=nazwa,
                metoda=metoda,
                adres=adres,
                status=None,
                bajtow=0,
                czas_s=zegar_zadania.monotonic() - start,
                plik=None,
                uwaga="; ".join(filter(None, (uwaga, f"{type(blad).__name__}: {blad}"))),
            )
        )
    czas = zegar_zadania.monotonic() - start
    retry_after_s, uwaga_retry = parse_retry_after(
        odpowiedz.headers.get(NAGLOWEK_RETRY_AFTER), teraz_epoch=zegar_zadania.wall()
    )
    limiter.note_response(odpowiedz.status_code, retry_after_s=retry_after_s)
    try:
        plik = zapisz_surowe(
            kronika.katalog_wyjscia, nazwa, znacznik, odpowiedz.content, rozszerzenie
        )
    except OSError as blad:
        # Jedyna z czterech awarii wymienionych w docstringu `Kronika`, która pada **po
        # odebraniu odpowiedzi** — czyli po tym, jak cudzy serwer zapłacił za nasze żądanie
        # pracą. Trzy pozostałe padają przed wysłaniem. Do 2026-09-17 ta jedna wywracała
        # `wykonaj` przed `kronika.zanotuj`, więc reguła zgody („pojedynczy odczyt zawsze
        # zostawia wpis w dzienniku") przestawała obowiązywać dokładnie wtedy, gdy zabrakło
        # miejsca na dysku roboczym. Strażnik na to wyglądał, ale nim nie był: atrapa podawała
        # „brak miejsca na dysku" jako wyjątek **transportu**, więc do `zapisz_surowe` nie
        # dochodziła.
        #
        # Wiersz powstaje z tym, co wiadomo, a wyjątek leci dalej — przebieg ma się zatrzymać,
        # bo bez miejsca na dysku następne żądanie zapisałoby się tak samo. Ale zatrzymuje się
        # **ze śladem**.
        kronika.zanotuj(
            Wynik(
                nazwa=nazwa,
                metoda=metoda,
                adres=adres,
                status=odpowiedz.status_code,
                bajtow=len(odpowiedz.content),
                czas_s=czas,
                plik=None,
                sha256=hashlib.sha256(odpowiedz.content).hexdigest(),
                uwaga="; ".join(
                    filter(
                        None,
                        (
                            uwaga,
                            uwaga_retry,
                            f"odpowiedź odebrana, ale nie zapisana na dysk "
                            f"({type(blad).__name__}: {blad})",
                        ),
                    )
                ),
            )
        )
        raise
    uwagi = [tekst for tekst in (uwaga, uwaga_retry) if tekst]
    if odpowiedz.is_redirect:
        uwagi.append(f"przekierowanie → {odpowiedz.headers.get('Location', '?')}")
    ocena = ksztalt.ocen(odpowiedz.content) if ksztalt is not None else None
    return kronika.zanotuj(
        Wynik(
            nazwa=nazwa,
            metoda=metoda,
            adres=adres,
            status=odpowiedz.status_code,
            bajtow=len(odpowiedz.content),
            czas_s=czas,
            plik=plik,
            sha256=hashlib.sha256(odpowiedz.content).hexdigest(),
            ksztalt_zgodny=None if ocena is None else ocena.zgodny,
            ksztalt_uwaga="" if ocena is None else ocena.uwaga,
            ksztalt_zrodlo="" if ksztalt is None else ksztalt.zrodlo,
            uwaga="; ".join(uwagi),
        )
    )


def kontrola_hosta(
    klient: httpx.Client, limiter: RateLimiter, kronika: Kronika, *, nazwa: str, korzen: str
) -> Wynik:
    """Jedno żądanie na korzeń hosta po odmowie — bez niego odmowa nic nie znaczy.

    Rozróżnia „punkt końcowy odmawia" od „host odmawia wszystkiemu". Pierwsze jest sprawą
    parametrów, klucza albo pisma; drugie zamyka kanał i przestawia architekturę. Pomiar 1
    pokazał, ile jest warta ta różnica: bez kontroli na `ftp.gnu.org` cisza na porcie 21
    równie dobrze mogła być zaporą po stronie mierzącego.
    """
    return wykonaj(
        klient,
        limiter,
        kronika,
        nazwa=nazwa,
        metoda="GET",
        adres=korzen,
        rozszerzenie="html",
        uwaga="kontrola po odmowie: czy host w ogóle odpowiada",
    )


def zatrzymaj_po_odmowie(wynik: Wynik) -> str | None:
    """Powód zatrzymania grupy pomiarów albo `None`, jeśli wolno jechać dalej.

    Rozstrzyga `Wynik.odmowa`, a nie powtórzony obok warunek — do przeglądu 2026-09-17 ta
    funkcja przepisywała te same trzy przypadki drugi raz, żeby dołożyć do nich powód. Czwarty
    przypadek dopisany kiedyś do `odmowa` nie zatrzymywałby wtedy grupy UZP, a rozjazd byłby
    niewidoczny: obie listy wyglądałyby na kompletne.
    """
    if not wynik.odmowa:
        return None
    if wynik.status is None:
        return "znany-dobry odczyt nie doszedł do skutku"
    if wynik.status in KODY_ODMOWY:
        return f"znany-dobry odczyt dostał {wynik.status}"
    return "znany-dobry odczyt wrócił w kształcie nie do poznania"
