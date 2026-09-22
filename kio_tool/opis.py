"""Opis narzędzia dla programu (`kio-tool opis --json`) — z drzewa poleceń, nie z ręki (2026-09-22).

Instrukcja dla modelu (`docs/dla-modelu.md`) jest pisana ręką i ma prawo się rozjechać
z narzędziem; ten opis nie ma jak, bo czyta te same obiekty, z których `typer` buduje `--help`.
Agent, który nie jest pewny flagi, pyta tu zamiast zgadywać, a `tests/test_zgodnosc_instrukcji.py`
porównuje ręczną instrukcję z tym samym drzewem.

Moduł nie pisze zdań: opisy flag przychodzą z `ui/texts_pomoc.py` przez `help=` w `cli.py`,
a nagłówki bloków układa `ui/texts.py`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from typer.core import TyperGroup

TAK = "tak"
NIE = "nie"


@dataclass(frozen=True)
class OpisPolecenia:
    nazwa: str
    siec: bool
    json: bool
    dla_czlowieka: bool
    opis: str


@dataclass(frozen=True)
class OpisFlagi:
    polecenie: str
    flaga: str
    """`--fraza` dla opcji, `<klucz>` dla argumentu pozycyjnego."""
    typ: str
    powtarzalna: bool
    domyslna: str
    opis: str


def polecenia(
    grupa: TyperGroup, *, sieciowe: frozenset[str], dla_czlowieka: frozenset[str]
) -> tuple[OpisPolecenia, ...]:
    """Polecenia w kolejności alfabetycznej — stała kolejność, powtarzalny wynik."""
    wynik = []
    for nazwa, polecenie in sorted(grupa.commands.items()):
        opcje = {o for p in polecenie.params for o in p.opts}
        wynik.append(
            OpisPolecenia(
                nazwa=nazwa,
                siec=nazwa in sieciowe,
                json="--json" in opcje,
                dla_czlowieka=nazwa in dla_czlowieka,
                opis=" ".join((polecenie.help or "").split()),
            )
        )
    return tuple(wynik)


def flagi(grupa: TyperGroup) -> tuple[OpisFlagi, ...]:
    """Każdy parametr każdego polecenia — opcje i argumenty pozycyjne."""
    wynik = []
    for nazwa, polecenie in sorted(grupa.commands.items()):
        for parametr in polecenie.params:
            argument = parametr.param_type_name == "argument"
            wynik.append(
                OpisFlagi(
                    polecenie=nazwa,
                    flaga=f"<{parametr.name}>" if argument else parametr.opts[0],
                    typ="flaga" if getattr(parametr, "is_flag", False) else parametr.type.name,
                    powtarzalna=parametr.multiple,
                    domyslna=_domyslna(parametr.default),
                    opis=" ".join(str(getattr(parametr, "help", None) or "").split()),
                )
            )
    return tuple(wynik)


def _domyslna(wartosc: object) -> str:
    if wartosc is None or wartosc is False or wartosc == ():
        return ""
    return str(wartosc)


def wiersze_polecen(opisy: Sequence[OpisPolecenia]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (o.nazwa, _tak_nie(o.siec), _tak_nie(o.json), _tak_nie(o.dla_czlowieka), o.opis)
        for o in opisy
    )


def wiersze_flag(opisy: Sequence[OpisFlagi]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (o.polecenie, o.flaga, o.typ, _tak_nie(o.powtarzalna), o.domyslna, o.opis) for o in opisy
    )


def wiersze_wartosci(wartosci: Mapping[str, Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    return tuple((flaga, ", ".join(dozwolone)) for flaga, dozwolone in wartosci.items())


def _tak_nie(wartosc: bool) -> str:
    return TAK if wartosc else NIE
