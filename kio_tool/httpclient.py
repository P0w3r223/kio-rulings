"""Jedyne miejsce, w którym powstaje klient HTTP — reguła granic 11.

Kontrola hosta w **adresie** jest kontrolą napisu: nie widzi, dokąd naprawdę idzie gniazdo.
`httpx.Client` budowany bez transportu i z domyślnym `trust_env=True` bierze
`HTTPS_PROXY`/`ALL_PROXY` ze środowiska (httpx 0.28.1, `_client.py`:
`allow_env_proxies = trust_env and transport is None`), a `SSL_CERT_FILE` podmienia zestaw
zaufanych certyfikatów — więc „TLS z weryfikacją certyfikatu" znaczyłoby „z weryfikacją
wobec tego, co wskaże zmienna środowiskowa".

Trzy różne mechanizmy zamykają trzy różne dziury i warto ich nie mylić — w `ceidg-tool`
przegląd kodu wykazał, że pierwsza wersja tego modułu przypisywała wszystko jednemu:

1. **Proxy ze środowiska** znika, bo transport jest podawany **zawsze**. To podanie
   transportu, a nie `trust_env`, zeruje `_mounts`; `trust_env=False` na kliencie zostaje
   jako drugi zamek (wyłącza też `.netrc`), ale sam z siebie niczego by tu nie zmienił.
2. **Podmianę zaufanych certyfikatów** blokuje `trust_env=False` przekazane
   `httpx.HTTPTransport`, bo to ono trafia do `create_ssl_context`.
3. **Obcy host** odbija się od `AllowedHostsTransport`, czyli od warstwy, w której otwiera
   się połączenie, a nie od tej, w której składa się adres.

Dwie różnice wobec wersji z CEIDG, obie wynikające z tego źródła:

- **Jeden stos HTTP, nie dwa.** W CEIDG warstwa modelu mieszkała w pakiecie i ciągnęła
  `httpx2` pod SDK, więc reguła wyjścia musiała istnieć w dwóch egzemplarzach. Tutaj faza 4
  jest osobnym procesem (architektura 4.10) i ten problem po prostu nie wchodzi.
- **Brak przekierowań jest tu decyzją operacyjną, nie tylko ostrożnością.** `GET /Home/Move`
  w wyszukiwarce UZP **jest** przekierowaniem na `/Home/Details/{id}` i to przekierowanie
  niesie informację: numer dokumentu dla n-tego wyniku zapytania. Adapter ma je odczytać
  z nagłówka `Location`, a nie przespać w bibliotece — inaczej zamrożona kaseta HTTP
  testowałaby wynik, a nie kontrakt.
"""

from __future__ import annotations

import math
import re
from datetime import UTC
from email.utils import parsedate_to_datetime

import httpx

from .errors import UntrustedLinkError

DOMYSLNY_LIMIT_CZASU_S = 30.0
"""Limit czasu pojedynczego żądania.

Wartość jawna, a nie domyślka httpx (5 s), bo źródło renderuje PDF-y na żądanie potokiem
Word → HTML → wkhtmltopdf (audyt 2.2) — a to jest profil, w którym pięć sekund bywa za mało
i przerwane żądanie kosztuje cudzy serwer tyle samo co udane. Liczba nie pochodzi z pomiaru
i tak ma być czytana: to jest wartość progowa do skorygowania po pomiarze 9, nie ustalenie.
"""


def refuse_foreign_host(scheme: str, host: str | None, allowed: frozenset[str]) -> None:
    """Jedyna kopia reguły „dokąd wolno wyjść"."""
    if scheme != "https" or host not in allowed:
        raise UntrustedLinkError(
            f"Odmowa połączenia z {host!r} (schemat {scheme!r}): dozwolone są tylko "
            "hosty " + ", ".join(sorted(allowed))
        )


class AllowedHostsTransport(httpx.BaseTransport):
    """Ostatnia bramka przed gniazdem: żądanie do obcego hosta nie opuszcza procesu.

    Kontrola siedzi w transporcie, a nie w adapterze, bo tędy przechodzi **każde** żądanie —
    także takie, które powstałoby z pominięciem adaptera: przekierowanie, wywołanie dopisane
    w przyszłości, biblioteka doklejona do tego samego klienta.
    """

    def __init__(self, inner: httpx.BaseTransport, allowed: frozenset[str]) -> None:
        self._inner = inner
        self._allowed = allowed

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        refuse_foreign_host(request.url.scheme, request.url.host, self._allowed)
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def build_http_client(
    *,
    user_agent: str,
    allowed: frozenset[str],
    transport: httpx.BaseTransport | None = None,
    timeout: float = DOMYSLNY_LIMIT_CZASU_S,
) -> httpx.Client:
    """Klient HTTP z polityką wyjścia i tożsamością. `transport` podstawiają testy i kasety.

    `user_agent` jest **wymagany i bez wartości domyślnej**, i to jest poprawka z przeglądu
    kodu 2026-09-15. Reguła 16 mówi „narzędzie przedstawia się własnym adresem przy **każdym**
    żądaniu"; dopóki nagłówek ustawiał adapter, adapter mógł o nim zapomnieć i nic nie zapalało
    się na czerwono — klient wysyłał wtedy `python-httpx/0.28.1`. Skoro to jest jedyne wąskie
    gardło, przez które przechodzi każde żądanie, reguła ma tu być własnością obiektu, a nie
    pamięci autora adaptera. Produkcja podaje `config.user_agent()`; test podaje wartość
    zastępczą, więc konstrukcja klienta nie wymaga zmiennej środowiskowej.

    `allowed` zawęża bramkę do hostów jednego kanału: adapter Atlasu niosący `X-Api-Key`
    nie ma prawa wyjść na `orzeczenia.uzp.gov.pl`, choćby przez przekierowanie. **Ten
    parametr też jest wymagany i bez wartości domyślnej**, i to jest poprawka z 2026-09-17.
    Do tego dnia domyślną była suma trzech zbiorów hostów — wywołanie bez argumentu było
    więc „bezpieczne, a nie wygodne" w tym sensie, że nie otwierało bramki na oścież, ale
    adapter, który zapomniał zawęzić ją do swojego kanału, dostawał sumę i **nic się nie
    zapalało na czerwono**. To jest ten sam kształt, dla którego `user_agent` nie ma
    domyślnej, zastosowany do drugiej połowy tej samej gwarancji: zawężenie ma być
    własnością wywołania, a nie pamięci autora adaptera. Sprawdzone przy zmianie: suma
    trzech zbiorów nie miała ani jednego wywołującego poza tą sygnaturą, więc `ALLOWED_HOSTS`
    znikło razem z domyślną — stała bez wywołującego jest napisem, nie zabezpieczeniem.

    Atrapa z testu też jest opakowana. Inaczej testy jeździłyby po innej ścieżce niż
    produkcja i ta właśnie różnica ukrywała w CEIDG defekt z proxy: podanie transportu
    w testach sprawiało, że httpx pomijał proxy ze środowiska, więc defekt nie miał jak
    się pokazać.
    """
    inner = transport or httpx.HTTPTransport(verify=True, trust_env=False)
    return httpx.Client(
        transport=AllowedHostsTransport(inner, allowed),
        trust_env=False,
        follow_redirects=False,
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )


NAGLOWEK_RETRY_AFTER = "Retry-After"
"""Nazwa nagłówka, który `parse_retry_after` czyta. Stała u właściciela protokołu, bo sonda
i adapter mają pytać o ten sam nagłówek — druga pisownia w drugim module byłaby ciszą
w miejscu, w którym cudzy serwis mówi „nie teraz"."""


def parse_retry_after(naglowek: str | None, *, teraz_epoch: float) -> tuple[float | None, str]:
    """`Retry-After` na sekundy, razem z uwagą, gdy nagłówek jest, ale nie do odczytania.

    RFC 9110 dopuszcza dwie postaci: `delta-seconds` i `HTTP-date`. Pierwsza wersja sondy brała
    wyłącznie `str.isdigit()`, więc postać datowa, wartość z białym znakiem i zapis
    zmiennoprzecinkowy szły do `note_response` jako `None` — a wtedy limiter bierze własną
    blokadę 60 s i sonda wznawia **wcześniej, niż serwis poprosił**, nie mówiąc o tym nikomu.
    W projekcie, którego pierwsza reguła brzmi „narzędzie nie omija zabezpieczeń" (audyt 12),
    to jest cisza dokładnie w miejscu, w którym cudzy serwis mówi „nie teraz".

    Nagłówek nie do odczytania **nie jest** cichy: wraca jako uwaga przy wyniku, czyli trafia
    na ekran i do `podsumowanie_*.json`. Wartość ujemna (data w przeszłości) daje zero, bo
    „termin już minął" i „nie umiem przeczytać" to dwa różne zdania.

    Do 2026-09-18 funkcja mieszkała w `scripts/sonda.py` jako `_retry_after_s`. Jest tutaj,
    bo parser nagłówka należy do właściciela protokołu: `ratelimit.note_response` deklaruje,
    że `Retry-After` jest „honorowany dosłownie", i każdy wywołujący — sonda dziś, adapter
    jutro — ma czytać go tą samą funkcją, a nie własnym `str.isdigit()`.

    Dosłowność kończy się tam, gdzie wartość przestaje być liczbą sekund (znalezisko testera
    2026-09-18, poprawione tego samego dnia): `float()` przyjmuje `inf`, `Infinity`, `1e400`
    i `nan`, a `inf` podane limiterowi ustawiało `_blocked_until_mono = inf` i pętlę
    `_sleep_in_slices`, która odejmując plaster od nieskończoności nie kończy się nigdy — bez
    `LimiterStalledError`, bo licznik iteracji stoi w pętli zewnętrznej. Wartość nieskończona
    albo `nan` nie jest prośbą o odczekanie; dostaje tę samą odpowiedź co napis „jutro rano":
    własna blokada limitera i uwaga.
    """
    if naglowek is None:
        return None, ""
    napis = naglowek.strip()
    try:
        sekundy = float(napis)
    except ValueError:
        sekundy = None
    if sekundy is not None:
        if not math.isfinite(sekundy):
            return None, (
                f"serwis podał Retry-After w postaci, której nie umiem przeczytać: `{napis}` — "
                "to nie jest skończona liczba sekund; trzymam własną blokadę limitera"
            )
        return max(0.0, sekundy), ""
    try:
        termin = parsedate_to_datetime(napis)
    except (TypeError, ValueError):
        return None, (
            f"serwis podał Retry-After w postaci, której nie umiem przeczytać: `{napis}` — "
            "trzymam własną blokadę limitera"
        )
    if termin.tzinfo is None:
        termin = termin.replace(tzinfo=UTC)
    return max(0.0, termin.timestamp() - teraz_epoch), ""


WZOR_SEGMENTU = re.compile(r"[A-Za-z0-9._~-]+")
"""Alfabet napisu, który wolno wstawić do ścieżki adresu jako jeden segment.

Referencja dokumentu (slug Atlasu, identyfikator liczbowy UZP) pochodzi z cudzej odpowiedzi
i idzie do adresu następnego żądania, więc jest obcym napisem na granicy: ukośnik, pytajnik
albo biały znak zmieniłyby żądanie w inne niż zaplanowane, a projekt wysyła wyłącznie żądania,
które zaplanował. Alfabet to znaki „unreserved" z RFC 3986 — węziej niż dopuszcza ścieżka, ale
dokładnie tyle, ile niesie slug (`[a-z0-9-]`, 100 na 100 rekordów pomiaru 3a, 2026-09-18).

Do etapu III (2026-09-18) wzorzec mieszkał w `scripts/sonda.py` jako `WZOR_SLUGA`. Jest tutaj
z tego samego powodu co `parse_retry_after`: należy do właściciela protokołu, a sonda i adapter
mają sprawdzać referencję **tą samą** funkcją, nie dwiema kopiami tej samej reguły.
"""

SEGMENTY_KROPKOWE = frozenset({".", ".."})
"""Dwa napisy z alfabetu wyżej, które **nie są** segmentem ścieżki, tylko poleceniem dla niej.

Znalezisko testera 2026-09-18, poprawione tego samego dnia: kropka jest znakiem „unreserved",
więc slug `..` przechodził alfabet w całości, a `httpx` przy budowie żądania usuwa segmenty
kropkowe (RFC 3986, 5.2.4) — `…/api/kio/..` szło do cudzego serwisu jako `GET /api`, a `.` jako
`GET /api/kio`, czyli powtórzenie listy policzone jako odczyt dokumentu. Dziennik zapisywał
adres, którego serwis nie dostał. Zmierzone na prawdziwym `build_http_client` z atrapą transportu.
"""


def powod_odrzucenia_segmentu(napis: str) -> str:
    """Dlaczego napis nie może być segmentem ścieżki adresu; pusty napis znaczy „może".

    Powód niesie **długość, nie treść**: napis, którego postać właśnie zakwestionowano, jest obcym
    napisem na drodze do terminala i do dziennika, a wypisany w całości robiłby z powodu kanał
    wyjścia dla cudzej treści.
    """
    if WZOR_SEGMENTU.fullmatch(napis) is None:
        return (
            f"niesie znaki spoza `{WZOR_SEGMENTU.pattern}` (długość {len(napis)}) — "
            "nie wstawię go do adresu"
        )
    if napis in SEGMENTY_KROPKOWE:
        return (
            f"jest segmentem kropkowym (długość {len(napis)}), który zmieniłby punkt końcowy "
            "żądania — nie wstawię go do adresu"
        )
    return ""
