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

import httpx

from .config import ALLOWED_HOSTS
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
    transport: httpx.BaseTransport | None = None,
    allowed: frozenset[str] = ALLOWED_HOSTS,
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
    nie ma prawa wyjść na `orzeczenia.uzp.gov.pl`, choćby przez przekierowanie. Wartość
    domyślna obejmuje wszystkie trzy hosty, żeby wywołanie bez argumentów pozostało
    bezpieczne — a nie żeby było wygodne.

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
