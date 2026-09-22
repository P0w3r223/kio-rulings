"""Dokument z bazy na `Wpis` eksportu — jedno miejsce dla eksportu i dla wyniku `szukaj`.

Wydzielone z `pipeline.py` 2026-09-22, kiedy `szukaj --json` dostał blok cytowania przy każdym
trafieniu. Slajd prezentacji obiecywał „blok cytowania, ten sam w pliku i w wyniku dla programu",
a trafienie wyszukiwania niosło tylko sygnaturę i fragment: od trafienia do źródła prowadziła
wyłącznie droga przez eksport. Blok ma być **ten sam**, nie podobny, więc oba wyjścia budują go
jedną funkcją (`exporter.blok_atrybucji`) z jednego `Wpis`, a ten powstaje wyłącznie tutaj.

`pipeline.py` stał wtedy ponad sufitem 800 linii z zakazem wzrostu (`PONAD_SUFITEM`; od ADR-0009
jest pakietem), więc dopisanie tam nowej drogi nie wchodziło w grę; wydzielenie jest przy tym
szwem prawdziwym — odczyt rekordu kanału na strukturę eksportu nie należy do orkiestracji przebiegu.

Moduł zna kontrakt kanału i **nie zna bazy** (reguła 5: sieć i bazę naraz widzi tylko
`pipeline`). Dokument przychodzi jako `DokumentSurowy` — kształt, który `store.Dokument` spełnia
strukturalnie — a przejście po bazie za wpisami trafień robi `obsluga`.
"""

from __future__ import annotations

from typing import Protocol

from .docid import SourceName
from .errors import ParseError
from .exporter import ATRYBUCJA_POKAZU, Wpis
from .parser.details import MapaPol, rekord_z_bajtow, wyczytaj
from .source.contract import Contract, load_contract


class DokumentSurowy(Protocol):
    """Bieżąca wersja dokumentu z bazy — to, czego potrzeba do `Wpis` (`store.Dokument`)."""

    @property
    def doc_id(self) -> str: ...
    @property
    def source(self) -> str: ...
    @property
    def source_ref(self) -> str: ...
    @property
    def current_sha256(self) -> str: ...
    @property
    def fetched_at(self) -> str: ...
    @property
    def content_bytes(self) -> bytes: ...


def mapa_pol(kontrakt: Contract) -> MapaPol:
    """Nazwy pól rekordu dokumentu z kontraktu — jedyne miejsce, które je przepisuje do parsera."""
    dokument = kontrakt.ksztalt.dokument
    return MapaPol(tresc=dokument.pole_tresci, **dokument.pola_metadanych.model_dump())


class MapyPol:
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


def wpis_z_dokumentu(dokument: DokumentSurowy, mapy: MapyPol, *, pokaz: bool = False) -> Wpis:
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
        atrybucja=ATRYBUCJA_POKAZU if pokaz else atrybucja,
        pokaz=pokaz,
    )
