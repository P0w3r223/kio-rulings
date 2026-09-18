"""`Criteria` — jedyny kontrakt między wejściem (flagi, przyszły kreator) a potokiem.

Moduł czysty (reguła 1): bez `httpx`, `sqlite3`, `openpyxl`, `rich`, `os`. Waliduje semantykę
(kolejność dat, normalizację wartości, długość frazy) i produkuje trzy rzeczy, których potok
potrzebuje: odcisk do wznowienia (`fingerprint`), opis po polsku (`describe`) i zestaw filtrów
dla kanału (`filtry_kanalu`).

**Nazwy parametrów serwisu nie występują w tym module.** Mapowanie „pole kryteriów → parametr
listy" żyje w `source/atlas/contract.yaml` (`parametry_listy.filtry`, reguła 22), a `Scope`
w `source/protocol.py` niesie pola kryteriów po naszych nazwach — adapter tłumaczy je przez
kontrakt. Dzięki temu zmiana nazwy parametru u dostawcy jest zmianą jednej linii w pliku danych,
a nie przeglądem tego modułu.

Listy wartości `rozstrzygniecie` i `rodzaj` są **zmierzone, nie udokumentowane**: sto rekordów
listy z pomiaru 3a (2026-09-18, `docs/decisions.md`) niosło `outcome` ∈ {oddalono 81,
uwzglednione 8, umorzono 5, inne 4, odrzucono 2} i `ruling_kind` ∈ {wyrok 91, postanowienie 9}.
Sto rekordów rocznika 2010 nie jest całym zbiorem, więc wartość spoza listy jest **przyjmowana
z ostrzeżeniem** w `describe()`/`ostrzezenia()`, nie odrzucana — odrzucenie zamieniałoby próbkę
w regułę, a operator wpisujący „uwzględniono" dowiedziałby się o tym dopiero z pustego wyniku
(mina 2 audytu: kryterium poprawne ≠ wynik kompletny).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

ROZSTRZYGNIECIA_ZMIERZONE: tuple[str, ...] = (
    "oddalono",
    "uwzglednione",
    "umorzono",
    "odrzucono",
    "inne",
)
"""Wartości `outcome` ze stu rekordów pomiaru 3a (zmierzone 2026-09-18). Próbka, nie słownik."""

RODZAJE_ZMIERZONE: tuple[str, ...] = ("wyrok", "postanowienie")
"""Wartości `ruling_kind` z tej samej próbki (zmierzone 2026-09-18)."""

MAX_DLUGOSC_TEKSTU = 200
"""Fraza dłuższa niż to nie jest kryterium, tylko wklejonym akapitem — zapytanie bez sensu."""

POLA_TEKSTOWE = ("fraza", "przepis", "przewodniczacy", "strona")
POLA_LISTOWE = ("rozstrzygniecie", "rodzaj")
POLA_FILTROW = (*POLA_TEKSTOWE, *POLA_LISTOWE)
"""Pola, które idą do kanału jako filtry listy — po tych nazwach kontrakt kanału je tłumaczy."""

ETYKIETY: Mapping[str, str] = {
    "fraza": "fraza",
    "rozstrzygniecie": "rozstrzygnięcie",
    "rodzaj": "rodzaj",
    "przepis": "przepis",
    "przewodniczacy": "przewodniczący",
    "strona": "strona postępowania",
    "daty": "daty wydania",
}


def _bez_ogonkow(napis: str) -> str:
    """`uwzględnione` → `uwzglednione`: Atlas zapisuje wartości bez znaków diakrytycznych
    (zmierzone na stu rekordach), a operator pisze po polsku. `ł` nie ma rozkładu w NFKD,
    więc zamieniamy je wprost — jedyna litera polskiego alfabetu bez znaku łączącego."""
    rozlozony = unicodedata.normalize("NFKD", napis.replace("ł", "l").replace("Ł", "L"))
    return "".join(znak for znak in rozlozony if not unicodedata.combining(znak))


def _as_tuple(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Iterable):
        return tuple(v for v in value if v is not None and str(v).strip() != "")
    return (value,)


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    """Bez duplikatów, w stałej kolejności — `fingerprint()` nie zależy od kolejności wejścia."""
    return tuple(sorted(set(values)))


def bledy_po_polsku(exc: ValidationError) -> str:
    """Błędy pydantica jako zdania dla operatora, nie zrzut dla programisty.

    Kształt przeniesiony z `ceidg-tool` razem z powodem: surowy `ValidationError` niesie
    `[type=value_error, input_value=(...), input_type=tuple]` i odnośnik do errors.pydantic.dev,
    a odbiorca tego narzędzia z założenia nie zna ani API, ani angielskiego. Rozpoznajemy po
    **kodzie typu**, nie po treści komunikatu: treść zmienia się między wersjami pydantica,
    `type` jest jego API. Nieznany kod wraca dotychczasową ścieżką — czyta się gorzej, nie ginie.
    """
    linie = []
    for blad in exc.errors():
        czesci = [str(part) for part in blad["loc"] if not isinstance(part, int)]
        pole = ".".join(czesci) or "kryteria"
        linie.append(f"  {pole}: {_tresc_bledu(blad)}")
    return "\n".join(linie)


def _tresc_bledu(blad: Mapping[str, Any]) -> str:
    typ = str(blad.get("type", ""))
    ctx = blad.get("ctx") or {}
    wartosc = blad.get("input")
    podano = f"{wartosc!r} — " if wartosc is not None and wartosc != "" else ""
    if typ.startswith(("date_", "datetime_")):
        return f"{podano}to nie jest data w postaci RRRR-MM-DD (na przykład 2024-01-31)"
    if typ in ("int_parsing", "int_type", "int_from_float"):
        return f"{podano}to nie jest liczba całkowita"
    if typ in ("greater_than_equal", "greater_than"):
        granica = ctx.get("ge", ctx.get("gt"))
        return f"{podano}wartość musi być nie mniejsza niż {granica}"
    if typ == "missing":
        return "brak wymaganej wartości"
    if typ in ("string_type", "str_type"):
        return f"{podano}wartość musi być tekstem"
    if typ == "extra_forbidden":
        return "nieznane pole kryteriów"
    tresc = str(blad["msg"])
    return tresc.removeprefix("Value error, ").removeprefix("Assertion failed, ")


class Criteria(BaseModel):
    """Kryteria pobrania (kanał) i wyszukiwania (korpus lokalny) — ten sam obiekt w obu rolach.

    Poza modelem świadomie: numer strony, rozmiar strony, sortowanie, klucz API — to parametry
    transportu i kontraktu kanału, nie kryteria operatora.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    od: date | None = None
    do: date | None = None
    fraza: str = ""
    rozstrzygniecie: tuple[str, ...] = ()
    rodzaj: tuple[str, ...] = ()
    przepis: str = ""
    przewodniczacy: str = ""
    strona: str = ""
    maks: int | None = Field(default=None, ge=1)
    """Górna granica liczby kandydatów w przebiegu. Ogranicza koszt u cudzego serwisu, więc
    wchodzi do odcisku: przebieg „pierwszych 10" i przebieg „wszystkich" to dwa różne przebiegi."""

    @field_validator(*POLA_LISTOWE, mode="before")
    @classmethod
    def _lista_malymi_literami(cls, value: Any) -> tuple[str, ...]:
        return _dedupe(_bez_ogonkow(str(v).strip().lower()) for v in _as_tuple(value))

    @field_validator(*POLA_TEKSTOWE)
    @classmethod
    def _tekst(cls, value: str) -> str:
        if len(value) > MAX_DLUGOSC_TEKSTU:
            raise ValueError(
                f"wartość {value[:20]!r}… ma {len(value)} znaków, limit {MAX_DLUGOSC_TEKSTU}"
            )
        return value

    @model_validator(mode="after")
    def _daty_w_kolejnosci(self) -> Criteria:
        if self.od and self.do and self.od > self.do:
            raise ValueError(
                f"data od ({self.od.isoformat()}) nie może być późniejsza niż data do "
                f"({self.do.isoformat()})"
            )
        return self

    # ------------------------------------------------------------------------ pytania

    def is_empty(self) -> bool:
        """Brak jakiegokolwiek filtra — zapytanie objęłoby cały zbiór. `maks` filtrem nie jest."""
        return not self.ma_daty() and not any(getattr(self, pole) for pole in POLA_FILTROW)

    def ma_daty(self) -> bool:
        return self.od is not None or self.do is not None

    def filtry_kanalu(self) -> dict[str, str]:
        """Filtry do wysłania kanałowi, po nazwach pól kryteriów — bez dat i bez `maks`.

        Pole listowe z **więcej niż jedną** wartością nie da się wysłać jako jeden parametr:
        semantyka powtórzonego parametru u dostawcy jest niezmierzona, a sklejenie przecinkiem
        byłoby zgadywaniem. Taka wartość wraca `ValueError` — potok zamienia go na błąd
        konfiguracji, a wyszukiwanie lokalne (`szukaj`, `eksportuj`) wielu wartości nie boi się.
        """
        filtry: dict[str, str] = {}
        for pole in POLA_TEKSTOWE:
            wartosc: str = getattr(self, pole)
            if wartosc:
                filtry[pole] = wartosc
        for pole in POLA_LISTOWE:
            wartosci: tuple[str, ...] = getattr(self, pole)
            if len(wartosci) > 1:
                raise ValueError(
                    f"pole {ETYKIETY[pole]} ma {len(wartosci)} wartości ({', '.join(wartosci)}), "
                    "a do kanału idzie jedna — pobierz każdą osobnym przebiegiem"
                )
            if wartosci:
                filtry[pole] = wartosci[0]
        return filtry

    def ostrzezenia(self) -> tuple[str, ...]:
        """Wartości spoza list zmierzonych — przyjęte, ale operator ma o tym wiedzieć."""
        uwagi: list[str] = []
        for pole, znane in (
            ("rozstrzygniecie", ROZSTRZYGNIECIA_ZMIERZONE),
            ("rodzaj", RODZAJE_ZMIERZONE),
        ):
            obce = [w for w in getattr(self, pole) if w not in znane]
            if obce:
                uwagi.append(
                    f"{ETYKIETY[pole]} {', '.join(obce)} nie wystąpiło w stu rekordach zmierzonych "
                    f"2026-09-18 (znane: {', '.join(znane)}); przyjęte, ale wynik może być pusty"
                )
        return tuple(uwagi)

    def poszerzenia(self, *, limit: int = 4) -> tuple[tuple[str, Criteria], ...]:
        """Kandydaci na zdjęcie **jednego** filtra — od najczęstszej przyczyny pustego wyniku.

        Kolejność jest twierdzeniem o zbiorze, nie o ekranie: fraza i nazwy stron dopasowują się
        dosłownie, więc jedna literówka zeruje wynik; przepis ma u pośrednika własny zapis
        („art. 226 ust. 1 pkt 5 Pzp"), którego operator nie zgadnie; rozstrzygnięcie i rodzaj
        pochodzą ze zbiorów zamkniętych; daty są najmniej podejrzane — chyba że `ruling_date`
        jest błędne (9 ze 100 rekordów pomiaru 3a), i dlatego w ogóle tu stoją.
        Kandydat, który opróżniłby kryteria do zera, nie powstaje.
        """
        kolejnosc = ("fraza", "strona", "przewodniczacy", "przepis", "rozstrzygniecie", "rodzaj")
        wynik: list[tuple[str, Criteria]] = []
        for pole in kolejnosc:
            if not getattr(self, pole):
                continue
            puste: Any = () if pole in POLA_LISTOWE else ""
            kandydat = self.model_copy(update={pole: puste})
            if not kandydat.is_empty():
                wynik.append((pole, kandydat))
        if self.ma_daty():
            kandydat = self.model_copy(update={"od": None, "do": None})
            if not kandydat.is_empty():
                wynik.append(("daty", kandydat))
        return tuple(wynik[:limit])

    # -------------------------------------------------------------------- odcisk i opis

    def canonical_json(self) -> str:
        """Postać kanoniczna: pola puste znikają, klucze posortowane, bez białych znaków.

        Puste pola nie wchodzą do odcisku od pierwszego dnia (lekcja z `ceidg-tool`, gdzie pole
        dopisane po fakcie unieważniało odciski wszystkich wcześniejszych przebiegów, a z nimi
        możliwość wznowienia tego, co ktoś zaczął przed aktualizacją).
        """
        dane = self.model_dump(mode="json")
        return json.dumps(
            {k: v for k, v in dane.items() if v not in (None, "", [], ())},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def fingerprint(self) -> str:
        """Stabilny skrót kryteriów — klucz do odnalezienia przebiegu do wznowienia."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:16]

    def describe(self) -> str:
        """Podsumowanie po polsku generowane przez kod, nie przez model."""
        czesci: list[str] = []
        if self.ma_daty():
            od = self.od.isoformat() if self.od else "…"
            do = self.do.isoformat() if self.do else "…"
            czesci.append(f"{ETYKIETY['daty']}: {od} – {do}")
        if self.fraza:
            czesci.append(f"{ETYKIETY['fraza']}: „{self.fraza}”")
        for pole in POLA_LISTOWE:
            wartosci: tuple[str, ...] = getattr(self, pole)
            if wartosci:
                czesci.append(f"{ETYKIETY[pole]}: {', '.join(wartosci)}")
        for pole in ("przepis", "przewodniczacy", "strona"):
            wartosc: str = getattr(self, pole)
            if wartosc:
                czesci.append(f"{ETYKIETY[pole]}: {wartosc}")
        if self.maks:
            czesci.append(f"maksymalnie {self.maks} dokumentów")
        if not czesci:
            czesci.append("bez kryteriów")
        opis = "; ".join(czesci)
        uwagi = self.ostrzezenia()
        return opis if not uwagi else opis + " (uwaga: " + "; ".join(uwagi) + ")"

    @classmethod
    def z_json(cls, tekst: str) -> Criteria:
        """Odtworzenie z `runs.kryteria` — odwrotność `canonical_json`."""
        return cls.model_validate(json.loads(tekst))
