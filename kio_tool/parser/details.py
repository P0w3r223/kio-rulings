"""Metadane i treść z surowego rekordu dokumentu — czysta funkcja nad JSON-em kanału.

Nazwy pól **nie są tu literałami**: przychodzą w `MapaPol`, którą `pipeline` buduje
z `contract.yaml` kanału (`ksztalt.dokument.pole_tresci` i `pola_metadanych`). Powód jest ten
sam, dla którego reguła 22 zabrania adresów w kodzie adaptera: zmiana nazwy pola u dostawcy ma
być zmianą w pliku danych z datą odczytu, a nie przeglądem kodu. `store.py` nie zna żadnej
z tych nazw — dostaje gotowe `Szczegoly`.

Reguła 19 (ADR-0005 Z-5) ma tu postać strukturalną: `Szczegoly` nie ma pola, którym mogłoby
pójść `thesis` ani żadne inne pole opracowania Atlasu, więc do tabel pochodnych, wyszukiwania
i eksportu nie wchodzą one nie dzięki czyjejś pamięci, tylko dlatego, że nie ma na nie miejsca.

Pusta wartość jest `None`, nigdy wartością zastępczą (architektura 4.5): „brak daty" i „data
nieznana" to dwie różne rzeczy, a arkusz z `0001-01-01` w kolumnie daty wygląda na kompletny.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from ..errors import ParseError

PARSE_VERSION = 5
"""Wersja odczytu **całego pakietu `parser/`** (ADR-0006 Z-10). `przelicz` przelicza wersje
dokumentów z `metadata.parse_version` mniejszym niż ta liczba — podnieś ją przy każdej zmianie
tego, co wyciąga `wyczytaj`, `sections`, `cite` albo `provisions`.

2 (2026-09-19): struktura wersji — sekcje, cytowania, przepisy (schemat 6).
3 (2026-09-20): rok czterocyfrowy w sygnaturze sądu skracany do dwucyfrowego (`docid`).
Zmiana weszła dzień wcześniej **bez** podniesienia tej liczby — znalezione w przeglądzie kodu
fazy 3. Skutek: `przelicz` bez `--wszystko` nie miał czego przeliczyć, więc korpus operatora
zostałby z obiema pisowniami naraz w indeksie cytowań, a powód zmiany (pięć par rozdzielonych
spraw) nie byłby na nim osiągnięty.
4 (2026-09-20): postaci sygnatur z pomiaru 25 — `KIO/KD`, `KIO/W`, `KIO/582/11`, rok czterocyfrowy
przy KIO, sądy administracyjne z kodem siedziby (`II SA/Op 4/18`) i Zespół Arbitrów UZP
(`UZP/ZO/0-62/07`). Nierozpoznanych cytowań 78 → 52 na korpusie 443 dokumentów.
5 (2026-09-20): rodzina A pomiaru 25 — sam numer po zapowiedzi `sygn. akt` jako rodzaj
`kio_bez_repertorium` (decyzja właściciela). Nierozpoznanych 52 → 23."""


@dataclass(frozen=True)
class MapaPol:
    """Nazwy pól rekordu u dostawcy — z `contract.yaml`, nigdy wpisane tutaj."""

    tresc: str
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


@dataclass(frozen=True)
class Szczegoly:
    """To, co z rekordu dokumentu wchodzi do tabel pochodnych i eksportu — i nic więcej."""

    sygnatura_glowna: str | None
    sygnatury: tuple[str, ...]
    data_wydania: str | None
    data_rozprawy: str | None
    rodzaj: str | None
    rozstrzygniecie: str | None
    rozstrzygniecie_surowe: str | None
    przewodniczacy: str | None
    odwolujacy: str | None
    zamawiajacy: str | None
    przepisy: tuple[str, ...]
    koszty: float | None
    url_zrodla: str | None
    tresc: str

    @property
    def dlugosc_tresci(self) -> int:
        return len(self.tresc)


def rekord_z_bajtow(content: bytes) -> dict[str, object]:
    """Surowe bajty wersji jako słownik JSON — albo `ParseError` z powodem, nigdy pusty słownik."""
    try:
        dane = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as blad:
        raise ParseError(f"Surowa wersja nie jest poprawnym JSON-em: {blad}") from blad
    if not isinstance(dane, dict):
        raise ParseError(
            f"Surowa wersja jest JSON-em typu {type(dane).__name__}, a rekord dokumentu ma być "
            "słownikiem."
        )
    return dane


def wyczytaj(rekord: Mapping[str, object], mapa: MapaPol) -> Szczegoly:
    """Metadane i treść z rekordu według mapy pól. Brak pola daje `None`/pustkę, nie wyjątek.

    Wyjątek jest zarezerwowany dla rekordu, który nie jest słownikiem (`rekord_z_bajtow`) —
    brak pojedynczego pola to stan dokumentu (Atlas: `outcome_raw` bywa `null`), nie awaria.
    """
    sygnatura_glowna = _napis(rekord.get(mapa.sygnatura_glowna))
    sygnatury = _lista_napisow(rekord.get(mapa.sygnatury))
    if not sygnatury and sygnatura_glowna:
        # ADR-0001 2.1: lista z główną jako pierwszą; bez listy — sama główna jest lepsza
        # niż pusty zbiór, bo sygnatura jest etykietą, nie tożsamością.
        sygnatury = (sygnatura_glowna,)
    return Szczegoly(
        sygnatura_glowna=sygnatura_glowna,
        sygnatury=sygnatury,
        data_wydania=_napis(rekord.get(mapa.data_wydania)),
        data_rozprawy=_napis(rekord.get(mapa.data_rozprawy)),
        rodzaj=_napis(rekord.get(mapa.rodzaj)),
        rozstrzygniecie=_napis(rekord.get(mapa.rozstrzygniecie)),
        rozstrzygniecie_surowe=_napis(rekord.get(mapa.rozstrzygniecie_surowe)),
        przewodniczacy=_napis(rekord.get(mapa.przewodniczacy)),
        odwolujacy=_napis(rekord.get(mapa.odwolujacy)),
        zamawiajacy=_napis(rekord.get(mapa.zamawiajacy)),
        przepisy=_lista_napisow(rekord.get(mapa.przepisy)),
        koszty=_liczba(rekord.get(mapa.koszty)),
        url_zrodla=_napis(rekord.get(mapa.url_zrodla)),
        tresc=_tresc(rekord.get(mapa.tresc)),
    )


def _tresc(wartosc: object) -> str:
    """Treść **bez** obcinania białych znaków: długość ma się zgadzać z tym, co przyszło
    (`dlugosc_full_text` w `*.compare.json` liczy bajty dostawcy, nie nasz porządek)."""
    return wartosc if isinstance(wartosc, str) else ""


def _napis(wartosc: object) -> str | None:
    """Napis niepusty po obcięciu białych znaków; wszystko inne — w tym liczba — to `None`.

    Liczba **nie** jest rzutowana na napis: `document_id: 13053` wpisane w kolumnę tekstową
    wyglądałoby na sygnaturę, a dokładnie takich wartości „prawdziwie wyglądających" zakazuje
    zasada 7.1 audytu.
    """
    if isinstance(wartosc, str):
        czysty = wartosc.strip()
        return czysty or None
    return None


def _lista_napisow(wartosc: object) -> tuple[str, ...]:
    if not isinstance(wartosc, list):
        return ()
    return tuple(w.strip() for w in wartosc if isinstance(w, str) and w.strip())


def _liczba(wartosc: object) -> float | None:
    """`int` albo `float`, bez `bool` (który w Pythonie jest `int`) i bez parsowania napisów."""
    if isinstance(wartosc, bool) or not isinstance(wartosc, int | float):
        return None
    return float(wartosc)
