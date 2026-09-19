"""Pomiar 21: czy mechanizm blokady sieci współistnieje z wstrzykniętym transportem httpx.

Zero żądań. Architektura 3.4 zostawia wybór między `vcrpy`/`pytest-recording`
a `respx` z zastrzeżeniem: `httpclient.build_http_client` **zawsze** podaje własny
transport (`AllowedHostsTransport`), a vcrpy podpina się na innym poziomie niż respx.
Jeśli wstrzyknięty transport omija punkt zaczepienia vcrpy, reguła 20 („sieć w testach jest
zablokowana, a wyjątek jest jawny") byłaby deklaracją, a nie strażnikiem — czyli dokładnie
tym, przed czym ostrzega zasada 7.3.
"""

from __future__ import annotations

import httpx
import pytest

from kio_tool.errors import UntrustedLinkError
from kio_tool.httpclient import build_http_client

UA_TESTOWY = "kio-tool/test (kontakt: test@example.org)"
"""Tożsamość podstawiana w testach. Produkcja bierze ją z `config.user_agent()`, który
czyta zmienną środowiskową — test nie ma prawa od niej zależeć."""


def test_obcy_host_odbija_sie_od_bramki_wyjscia() -> None:
    """Reguła 11: host spoza listy nie opuszcza procesu. Nie dotyka sieci."""
    client = build_http_client(user_agent=UA_TESTOWY, allowed=frozenset({"orzeczenia.uzp.gov.pl"}))
    with pytest.raises(UntrustedLinkError):
        client.get("https://example.org/cokolwiek")


def test_http_bez_tls_odbija_sie_od_bramki_wyjscia() -> None:
    """Bramka odmawia też po schemacie, nie tylko po hoście."""
    client = build_http_client(user_agent=UA_TESTOWY, allowed=frozenset({"orzeczenia.uzp.gov.pl"}))
    with pytest.raises(UntrustedLinkError):
        client.get("http://orzeczenia.uzp.gov.pl/Home/Details/1")


def test_blokada_sieci_lapie_zadanie_przez_wstrzykniety_transport() -> None:
    """Sedno pomiaru 21: czy `--block-network` widzi ruch idący przez nasz transport.

    Host jest dozwolony przez bramkę wyjścia, więc jedyne, co może to żądanie zatrzymać,
    to mechanizm blokady sieci z konfiguracji pytest. Jeśli test przechodzi — strażnik
    reguły 20 działa mimo wstrzykniętego transportu. Jeśli padnie z błędem połączenia
    zamiast z blokadą, znaczy to, że żądanie **wyszło** i mechanizm trzeba zmienić na
    `respx`, który podpina się dokładnie na poziomie transportu.
    """
    client = build_http_client(user_agent=UA_TESTOWY, allowed=frozenset({"orzeczenia.uzp.gov.pl"}))
    with pytest.raises(Exception) as zlapany:  # noqa: B017 - typ jest treścią pomiaru
        client.get("https://orzeczenia.uzp.gov.pl/Home/Details/9620")

    # Sprawdzamy komunikat, nie klasę. `pytest-recording` zgłasza blokadę jako zwykły
    # `RuntimeError("Network is disabled")`, więc asercja po nazwie klasy przepuściłaby
    # każdy inny `RuntimeError` i jednocześnie odrzuciła prawdziwą blokadę. Pierwsza
    # wersja tego testu robiła dokładnie to i przez chwilę wyglądała jak wynik negatywny
    # pomiaru — a mechanizm działał.
    assert "Network is disabled" in str(zlapany.value), (
        "Żądanie nie zostało zablokowane przez konfigurację pytest; wyjątek: "
        f"{type(zlapany.value).__name__}: {zlapany.value}"
    )
    assert not isinstance(zlapany.value, httpx.ConnectError), (
        "Blokada nie zadziałała: żądanie opuściło proces i dopiero warstwa sieciowa je odbiła."
    )


def test_blokada_sieci_siega_ponizej_httpx_do_samego_gniazda() -> None:
    """Druga połowa pomiaru 21: czy blokada działa na gnieździe, czy tylko na transporcie httpx.

    Rozróżnienie jest nośne, a nie akademickie. Jeśli blokada podmienia wyłącznie transport
    `httpx`, to kanał spoza HTTP — `ftplib`, `socket` wprost, `urllib` — przechodzi przez nią
    **niewidziany**, a reguła 20 obejmuje wtedy tylko tę część ruchu, którą akurat widać.
    Dokładnie ten kształt wystąpił już w `ceidg-tool`: skan reguły granic dopasowywał dosłowną
    nazwę `httpx` i przez to przepuszczał `httpx2` spod SDK modelu, raportując się jako
    domknięty przy pokryciu połowy ruchu.

    Adres docelowy jest celowo spoza bramki wyjścia i spoza jakiegokolwiek źródła projektu:
    gdyby blokada nie zadziałała, to połączenie i tak nie ma dokąd dojść, a test powie o tym
    wprost, zamiast po cichu wyjść do sieci.
    """
    import socket

    with pytest.raises(Exception) as zlapany:  # noqa: B017 - typ jest treścią pomiaru
        socket.create_connection(("127.0.0.1", 9), timeout=0.25)

    assert "Network is disabled" in str(zlapany.value), (
        "Blokada nie sięga gniazda — obejmuje wyłącznie transport httpx. Reguła 20 nie "
        "pokrywa wtedy kanału spoza HTTP; wyjątek: "
        f"{type(zlapany.value).__name__}: {zlapany.value}"
    )
