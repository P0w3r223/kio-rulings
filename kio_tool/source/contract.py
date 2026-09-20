"""Wczytanie `contract.yaml` kanału — jedyny czytelnik tych plików (ADR-0003 1B, reguła 17).

Kontrakt jest **jedynym** miejscem, z którego adapter bierze adresy, nazwy punktów końcowych,
nazwy pól, tempo i rozmiar strony; skan reguły 22 w `tests/test_boundaries.py` odrzuca każdy
taki literał w `source/**/*.py`. Powód ma datę: między majem a lipcem 2026 UZP przeniósł każdy
punkt końcowy wyszukiwarki, a cudzy kolektor przez około dwa miesiące zwracał `total=0` ze
statusem 200. Adres w pliku danych zmienia się jedną linią; adres w kodzie — przeglądem kodu.

Schemat jest ścisły (`extra="forbid"`): literówka w nazwie pola kontraktu wywraca **wczytanie**,
a nie pierwsze żądanie do cudzego serwisu. Każde oczekiwanie kształtu niesie własne `zrodlo`
(reguła 17, doprecyzowanie 2026-09-17): „dokumentacja dostawcy" i „własny odczyt z datą" to dwa
różne statusy dowodowe i ich niezgodność znaczy co innego.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..docid import RefCase, SourceName
from ..errors import ConfigError

PLIK_KONTRAKTU = "contract.yaml"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Licencja(_Model):
    nazwa: str
    atrybucja: str
    zrodlo: str


class Punkty(_Model):
    lista: str
    dokument: str
    """Przedrostek adresu dokumentu; referencja doklejana jako ostatni segment po kontroli
    `httpclient.powod_odrzucenia_segmentu`."""
    zrodlo: str


class ParametryListy(_Model):
    """Nazwy parametrów zapytania listy — wartości podaje adapter z `Scope` i numeru strony."""

    od: str
    do: str
    sortowanie: str
    sortowanie_wartosc: str
    strona: str
    na_strone: str
    filtry: dict[str, str] = Field(default_factory=dict)
    """Pole kryteriów (nasza nazwa) → parametr listy u dostawcy. Klucz spoza `Scope.filtry`
    jest tylko niewykorzystaną zdolnością; klucz w `Scope.filtry` bez wiersza tutaj jest
    błędem konfiguracji, nie parametrem do zgadnięcia."""
    zrodlo: str


class Okno(_Model):
    limit: int = Field(gt=0)
    sekund: float = Field(gt=0)


class NaglowkiBudzetu(_Model):
    limit: str
    pozostalo: str
    reset: str


class KluczApi(_Model):
    naglowek: str
    zmienna: str
    """Nazwa zmiennej środowiskowej z kluczem — czyta ją `config.klucz_api`."""


class Tempo(_Model):
    odstep_s: float = Field(gt=0)
    okna: list[Okno]
    naglowki_budzetu: NaglowkiBudzetu
    klucz_api: KluczApi
    zrodlo: str


KlasaPonowienia = Literal["transport", "urwana", "serwis_5xx", "odmowa_429"]
"""Zakończenia żądania, które wolno ponowić (ADR-0007 Z-1) — trzy pierwsze to jedno zdarzenie,
zerwane łącze, widziane trzema drogami; czwarte to „nie teraz" po pełnej blokadzie limitera."""


class Ponowienia(_Model):
    """Polityka ponowień kanału (ADR-0007 Z-5) — **nasze progi**, nie odczyt u dostawcy.

    Osobny blok, nie pole w `Tempo`: `tempo.zrodlo` dokumentuje limity odczytane u dostawcy,
    a te liczby są decyzją projektu. Wrzucone pod cudze `zrodlo` spłaszczyłyby dwa statusy
    dowodowe do jednego (zasada 7.1 audytu).
    """

    klasy: list[KlasaPonowienia]
    proby: int = Field(ge=1)
    """Łączna liczba prób (pierwsza + ponowienia) dla klas innych niż `odmowa_429`."""
    proby_429: int = Field(ge=1)
    """Łączna liczba prób po 429 — postój przed ponowieniem trzyma blokada limitera."""
    podstawa_s: float = Field(ge=0)
    mnoznik: float = Field(ge=1)
    pod_rzad_max: int = Field(gt=0)
    """Tyle kolejnych żądań wymagających ponowienia znaczy „serwis leży", nie „mruga" (Z-6)."""
    retry_after_max_s: float = Field(gt=0)
    """Najdłuższy `Retry-After`, na który przebieg czeka w procesie. Dłuższa prośba serwisu kończy
    przebieg jako `przerwany` ze zdaniem — zamiast usypiać proces na dobę albo rok (przegląd kodu
    2026-09-19: `Retry-After: 1e18` nie kończył się nigdy, bo odejmowanie plastrów po 300 s ginęło
    w precyzji liczby zmiennoprzecinkowej). Prośbę serwisu honoruje `wznow`, nie sen procesu."""
    zrodlo: str

    def postoj_przed(self, proba: int) -> float:
        """Postój przed próbą `proba` (2 = pierwsze ponowienie): `podstawa_s * mnoznik^(n-2)`."""
        if proba < 2:
            return 0.0
        return float(self.podstawa_s * self.mnoznik ** (proba - 2))


class Strony(_Model):
    na_strone: int = Field(gt=0)
    max_stron: int = Field(gt=0)
    zrodlo: str


class PolaRekordu(_Model):
    """Które pole rekordu listy niesie co — do budowy `Candidate`."""

    referencja: str
    sygnatury: str
    sygnatura_glowna: str
    data_wydania: str


class KsztaltListy(_Model):
    klucz: str
    ma_wiecej: str
    licznik: str
    rekord: PolaRekordu
    zrodlo: str


class PolaMetadanych(_Model):
    """Nasza nazwa pola metadanych → nazwa w rekordzie dokumentu u dostawcy.

    Atrybuty tej klasy są nazwami z `parser.details.MapaPol` (bez `tresc`, które niesie
    `pole_tresci`); `pipeline` przepisuje je jeden do jednego. Pole o nieznanym pochodzeniu
    (`pola_odrzucone`) nie ma tu wiersza — i to jest granica reguły 19 po stronie kontraktu.
    """

    sygnatura_glowna: str
    sygnatury: str
    data_wydania: str
    data_rozprawy: str
    rodzaj: str
    rozstrzygniecie: str
    rozstrzygniecie_surowe: str
    przewodniczacy: str
    odwolujacy: str
    zamawiajacy: str
    przepisy: str
    koszty: str
    url_zrodla: str


class KsztaltDokumentu(_Model):
    pola_wymagane: list[str] = Field(min_length=1)
    pole_tresci: str
    pola_metadanych: PolaMetadanych
    zrodlo: str


class Ksztalt(_Model):
    lista: KsztaltListy
    dokument: KsztaltDokumentu


class PoleOdrzucone(_Model):
    """Pole o nieznanym pochodzeniu — reguła 19 (ADR-0005 Z-5): powód i data są wymagane."""

    pole: str
    powod: str = Field(min_length=1)
    data: date


class Contract(_Model):
    kanal: str
    role: list[Literal["masowa", "weryfikacja", "doplyw"]] = Field(min_length=1)
    pomiary: list[str] = Field(min_length=1)
    licencja: Licencja
    ref_case: RefCase
    baza: str
    punkty: Punkty
    parametry_listy: ParametryListy
    tempo: Tempo
    ponowienia: Ponowienia
    strony: Strony
    ksztalt: Ksztalt
    pola_odrzucone: list[PoleOdrzucone]

    @field_validator("pomiary", mode="before")
    @classmethod
    def _numery_pomiarow_jako_napisy(cls, wartosc: object) -> object:
        """`pomiary: [3a, 23]` — YAML czyta `23` jako liczbę, a numer pomiaru jest etykietą.

        Strażnik bramki (`test_bramki_faz.py`) czyta to pole tekstowo i porównuje z nagłówkami
        `## Pomiar N` w `decisions.md`; tu ma być ten sam napis, a nie liczba, która przy
        `23` przypadkiem wygląda tak samo, a przy `2a` już nie.
        """
        if isinstance(wartosc, list):
            return [str(pozycja) for pozycja in wartosc]
        return wartosc


def sciezka_kontraktu(kanal: SourceName) -> Path:
    """`source/<kanał>/contract.yaml` — kontraktu nie da się osierocić (ADR-0003 1B)."""
    return Path(__file__).resolve().parent / kanal / PLIK_KONTRAKTU


def load_contract(kanal: SourceName) -> Contract:
    """Wczytuje i waliduje kontrakt kanału; każda usterka jest `ConfigError` ze ścieżką pliku."""
    sciezka = sciezka_kontraktu(kanal)
    if not sciezka.is_file():
        raise ConfigError(
            f"Kanał {kanal!r} nie ma kontraktu: brak pliku {sciezka}. Kanał jest pakietem "
            f"`source/<nazwa>/` z `{PLIK_KONTRAKTU}` (reguła 21)."
        )
    try:
        dane = yaml.safe_load(sciezka.read_text(encoding="utf-8"))
    except yaml.YAMLError as blad:
        raise ConfigError(f"Kontrakt {sciezka} nie jest poprawnym YAML-em: {blad}") from blad
    if not isinstance(dane, dict):
        raise ConfigError(
            f"Kontrakt {sciezka} ma być słownikiem pól, a jest: {type(dane).__name__}"
        )
    try:
        kontrakt = Contract.model_validate(dane)
    except ValidationError as blad:
        raise ConfigError(f"Kontrakt {sciezka} nie zgadza się ze schematem:\n{blad}") from blad
    odrzucone = {wpis.pole for wpis in kontrakt.pola_odrzucone}
    przepuszczone = sorted(
        odrzucone & set(kontrakt.ksztalt.dokument.pola_metadanych.model_dump().values())
    )
    if przepuszczone or kontrakt.ksztalt.dokument.pole_tresci in odrzucone:
        # Reguła 19 w brzmieniu ADR-0005 Z-5: pole odrzucone nie ma prawa stać się polem
        # metadanych ani treści. Dwie listy w jednym pliku mogą się rozjechać jedną edycją —
        # sprawdzenie przy wczytaniu jest tańsze niż przegląd kodu po fakcie.
        raise ConfigError(
            f"Kontrakt {sciezka} wymienia w `pola_odrzucone` pole, które jednocześnie mapuje "
            f"na metadane albo treść: {przepuszczone or [kontrakt.ksztalt.dokument.pole_tresci]}."
        )
    if kontrakt.kanal != kanal:
        # Nazwa katalogu jest nazwą kanału — tym samym napisem, który idzie do `doc_id`
        # (reguła 21). Kontrakt mówiący inaczej niósłby dwie pisownie jednego kanału.
        raise ConfigError(
            f"Kontrakt {sciezka} deklaruje `kanal: {kontrakt.kanal}`, a leży w katalogu "
            f"kanału {kanal!r}. Nazwa katalogu i pole `kanal` mają być tym samym napisem."
        )
    return kontrakt
