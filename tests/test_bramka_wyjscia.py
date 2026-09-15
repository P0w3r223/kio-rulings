"""Strażnicy trzech mechanizmów bramki wyjścia — reguła 11.

Docstring `kio_tool/httpclient.py` wymienia trzy mechanizmy zamykające trzy różne dziury.
Do przeglądu kodu 2026-09-15 testy pokrywały **wyłącznie trzeci** (obcy host). Mechanizm 1
(proxy ze środowiska) i mechanizm 2 (podmiana zaufanych certyfikatów przez `SSL_CERT_FILE`)
nie miały ani jednej asercji — a skreślenie `trust_env=False` z linii budującej transport
zostawiało całą suitę zieloną, `ruff` czysty i `mypy` czysty.

Odpowiedź na pytanie zasady 7.3 („co by się wypisało, gdyby zabezpieczenie zostało
naruszone?") brzmiała więc **nic**, czyli z definicji tej zasady: usterka, nie zabezpieczenie.
Ten plik jest tą odpowiedzią. Wzorzec przeniesiony z `Ceidg/tests/resilience/
test_egress_allowlist.py`, razem ze zdaniem „stąd jej własny test", które w pierwszym
przeniesieniu zostało w docstringu bez testu.

Żaden test w tym pliku nie dotyka sieci.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from kio_tool.httpclient import build_http_client

UA_TESTOWY = "kio-tool/test (kontakt: test@example.org)"


def test_mechanizm_1_proxy_ze_srodowiska_nie_jest_montowane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proxy ze zmiennych środowiskowych nie ma wpływu na klienta.

    W httpx 0.28.1 decyduje o tym `allow_env_proxies = trust_env and transport is None`
    w `Client.__init__`: samo podanie transportu zeruje `_mounts`. Test celuje w skutek
    (`_mounts` puste), a nie w nazwę pola biblioteki — ale nazwa stoi w komentarzu, żeby
    przy podniesieniu pinu było wiadomo, czego szukać.

    Gdyby `build_http_client` przestał podawać transport, ten test zapali się na czerwono,
    zamiast pozwolić żądaniu z nagłówkiem uwierzytelniającym wyjść przez host, którego nikt
    nie porównał z listą dozwolonych.
    """
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example.org:8080")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.example.org:8080")

    with build_http_client(user_agent=UA_TESTOWY) as client:
        assert client._mounts == {}, (
            "Klient zamontował proxy ze środowiska. Mechanizm 1 bramki wyjścia nie działa: "
            "żądanie wyszłoby przez host spoza listy dozwolonych."
        )


def test_mechanizm_2_podmiana_zaufanych_certyfikatow_jest_zablokowana(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`SSL_CERT_FILE` nie podmienia zestawu zaufanych certyfikatów.

    Mechanizm: `trust_env=False` przekazane do `httpx.HTTPTransport` trafia do
    `create_ssl_context`, gdzie `trust_env and os.environ.get("SSL_CERT_FILE")` decyduje
    o źródle CA. Ta jedna wartość jest **całym** mechanizmem połowy zdania „TLS
    z weryfikacją certyfikatu" — stąd jej własny test.

    Dowód działa przez wskazanie nieistniejącego pliku: przy `trust_env=True` budowa
    transportu kończy się `FileNotFoundError`, przy `trust_env=False` przechodzi, bo
    certyfikaty idą z `certifi`. Jeżeli więc konstrukcja klienta przejdzie, znaczy to,
    że zmienna środowiskowa została zignorowana — i o to chodzi.
    """
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "nie-ma-takiego-pliku.pem"))

    with build_http_client(user_agent=UA_TESTOWY) as client:
        assert client is not None

    # Druga połowa dowodu: pokazujemy, że zmienna **jest** żywa, więc test wyżej nie
    # przechodzi dlatego, że mechanizm w httpx zniknął. Bez tego test sprawdzałby
    # nieobecność zjawiska, a nie jego zablokowanie.
    with pytest.raises(FileNotFoundError):
        httpx.HTTPTransport(verify=True, trust_env=True)


def test_mechanizm_3_obcy_host_nie_opuszcza_procesu() -> None:
    """Trzeci mechanizm ma już pokrycie w `test_pomiar21_blokada_sieci.py`.

    Ten test istnieje jako kotwica: gdyby tamten plik kiedyś zniknął razem z pomiarem 21,
    reguła 11 nie zostałaby bez strażnika. Trzy mechanizmy, trzy asercje, jeden plik, który
    da się przeczytać obok docstringa `httpclient.py`.
    """
    from kio_tool.errors import UntrustedLinkError

    with build_http_client(
        user_agent=UA_TESTOWY, allowed=frozenset({"orzeczenia.uzp.gov.pl"})
    ) as client:
        with pytest.raises(UntrustedLinkError):
            client.get("https://example.org/cokolwiek")


def test_uzytkownik_klienta_przedstawia_sie_podanym_naglowkiem() -> None:
    """Reguła 16 jako własność obiektu, nie pamięci autora adaptera.

    `user_agent` jest parametrem wymaganym, więc adapter nie może go pominąć. Ten test
    pilnuje, że podana wartość faktycznie ląduje w nagłówkach klienta — bo parametr
    przyjmowany i nieużywany byłby gorszy niż jego brak: dawałby pewność bez pokrycia.
    """
    with build_http_client(user_agent=UA_TESTOWY) as client:
        assert client.headers["User-Agent"] == UA_TESTOWY
