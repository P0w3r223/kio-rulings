"""Tryb pokazowy — praca bez rejestru jako własność produktu (ADR-0008, wzorzec ADR-0014 ceidg).

`zbuduj_pokaz()` składa trzy rzeczy, które `cli` podstawia w korzeniu kompozycji: fabrykę klienta
z atrapą Atlasu jako transportem (gniazdo się nie otwiera; bramka wyjścia `ATLAS_HOSTS` bez
zmian), zegar przyspieszony i stały `User-Agent` pokazu. Pokaz nie czyta `KIO_TOOL_CONTACT` ani
klucza Atlasu (Z-14): ma działać w dniu klonu, bez żadnej konfiguracji.

Czas: `ZegarDemo` przyspiesza `monotonic` i `sleep`, nie `wall` — limiter trzyma odstępy z tempa
kontraktu, tylko szybciej, a tabela kosztów drukuje czas **produkcyjny** obok czasu pokazu (Z-13).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from functools import partial
from importlib import resources

import httpx
import yaml

from ..docid import SourceName
from ..httpclient import build_http_client
from ..source.contract import Contract, load_contract
from .atlas import AtlasPokazowy
from .korpus import DokumentPokazowy, Wzorce, generuj

UA_POKAZU = "kio-tool-pokaz (tryb pokazowy, bez sieci; https://pokaz.invalid)"
"""`User-Agent` legalny wyłącznie z `MockTransport`; produkcja bierze go z `config.user_agent()`."""
TEMPO_ENV = "KIO_TOOL_DEMO_TEMPO"
TEMPO_DOMYSLNE = 4.0
TEMPO_MAKS = 50.0


class ZegarDemo:
    """Zegar pokazu: ścienny prawdziwy, monotoniczny i sen przyspieszone `tempo` razy."""

    def __init__(self, tempo: float = TEMPO_DOMYSLNE) -> None:
        self.tempo = min(max(tempo, 1.0), TEMPO_MAKS)
        self._przesuniecie = 0.0

    def monotonic(self) -> float:
        return time.monotonic() + self._przesuniecie

    def wall(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        prawdziwe = seconds / self.tempo
        time.sleep(prawdziwe)
        self._przesuniecie += seconds - prawdziwe


@dataclass(frozen=True)
class Pokaz:
    klient_factory: partial[httpx.Client]
    zegar: ZegarDemo
    atrapa: AtlasPokazowy
    user_agent: str = UA_POKAZU

    def czas_pokazu(self, produkcyjny_s: float) -> float:
        return produkcyjny_s / self.zegar.tempo


def wczytaj_wzorce() -> Wzorce:
    """`wzorce.yaml` z pakietu — wygenerowany skryptem, nigdy pisany ręcznie (Z-11)."""
    tekst = resources.files(__package__).joinpath("wzorce.yaml").read_text(encoding="utf-8")
    dane = yaml.safe_load(tekst)
    return Wzorce(
        rozstrzygniecia=dict(dane["rozstrzygniecia"]),
        etykiety_przepisow=tuple(
            (e["etykieta"], int(e["liczba"])) for e in dane["etykiety_przepisow"]
        ),
    )


def tempo_ze_srodowiska() -> float:
    try:
        return float(os.environ.get(TEMPO_ENV, TEMPO_DOMYSLNE))
    except ValueError:
        return TEMPO_DOMYSLNE


def zbuduj_pokaz(
    *,
    korpus: tuple[DokumentPokazowy, ...] | None = None,
    kontrakt: Contract | None = None,
    tempo: float | None = None,
) -> Pokaz:
    kontrakt = kontrakt or load_contract(SourceName("atlas"))
    atrapa = AtlasPokazowy(korpus if korpus is not None else generuj(wczytaj_wzorce()), kontrakt)
    return Pokaz(
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(atrapa)),
        zegar=ZegarDemo(tempo_ze_srodowiska() if tempo is None else tempo),
        atrapa=atrapa,
    )
