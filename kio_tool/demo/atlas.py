"""Atrapa Atlasu dla trybu pokazowego — odpowiada z korpusu pokazowego według kontraktu kanału.

Nazwy punktów, parametrów i pól bierze wyłącznie z `contract.yaml` (to samo źródło co adapter),
więc pokaz jedzie ścieżką operatora: prawdziwy `AtlasChannel`, ocena kształtu, limiter, potok,
parser, magazyn, eksport (ADR-0008 Z-1). Nie jest kanałem i nie stoi w `REGISTRY` — podstawia
się ją w korzeniu kompozycji jako transport, a gniazdo sieciowe się nie otwiera.

Semantyka filtrów (ADR-0008 §6):

- `search` dopasowuje **sygnaturę, nie treść** — zmierzone 2026-09-18 („Pomiar filtrów Atlasu");
- `outcome` — równość, zmierzone; `date_from`/`date_to` — po dacie wydania, zmierzone;
- `ruling_kind`, `law_article`, `chairperson`, `party` — według dokumentacji Atlasu,
  **niezmierzone**: pokaz może na nich uczyć semantyki, której Atlas nie ma (cena w ADR-ze).

Nagłówków `X-RateLimit-*` atrapa nie wysyła: ich postać jest niezmierzona (kontrakt,
`tempo.zrodlo`), a atrapa nie uczy tego, czego nikt nie zmierzył.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence

import httpx

from ..source.contract import Contract
from .korpus import DokumentPokazowy


class AtlasPokazowy:
    """`httpx.MockTransport(AtlasPokazowy(...))` — lista i dokument z korpusu pokazowego."""

    def __init__(self, korpus: Sequence[DokumentPokazowy], kontrakt: Contract) -> None:
        self._k = kontrakt
        self._po_slugu = {d.slug: d for d in korpus}
        self._korpus = sorted(korpus, key=lambda d: (d.data_wydania, d.slug))
        self.zadan = 0

    def __call__(self, zadanie: httpx.Request) -> httpx.Response:
        self.zadan += 1
        k = self._k
        sciezka = zadanie.url.path
        if sciezka == k.punkty.lista:
            return self._lista(zadanie.url.params)
        przedrostek = k.punkty.dokument + "/"
        if sciezka.startswith(przedrostek):
            dokument = self._po_slugu.get(sciezka[len(przedrostek) :])
            if dokument is None:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, content=json.dumps(self.rekord(dokument)).encode())
        return httpx.Response(404, json={"error": "not found"})

    # -------------------------------------------------------------------------- lista

    def _lista(self, params: Mapping[str, str]) -> httpx.Response:
        p = self._k.parametry_listy
        trafione = [d for d in self._korpus if self._pasuje(d, params)]
        na_strone = int(params.get(p.na_strone, str(self._k.strony.na_strone)))
        strona = int(params.get(p.strona, "1"))
        wycinek = trafione[(strona - 1) * na_strone : strona * na_strone]
        lista = self._k.ksztalt.lista
        tresc = {
            lista.klucz: [self._rekord_listy(d) for d in wycinek],
            lista.ma_wiecej: strona < math.ceil(len(trafione) / na_strone),
            lista.licznik: len(trafione),
        }
        return httpx.Response(200, content=json.dumps(tresc).encode())

    def _pasuje(self, d: DokumentPokazowy, params: Mapping[str, str]) -> bool:
        p = self._k.parametry_listy
        od, do = params.get(p.od), params.get(p.do)
        if od and d.data_wydania.isoformat() < od:
            return False
        if do and d.data_wydania.isoformat() > do:
            return False
        f = p.filtry
        warunki: dict[str, Callable[[str], bool]] = {
            "fraza": lambda w: any(w.lower() in s.lower() for s in d.sygnatury),
            "rozstrzygniecie": lambda w: d.rozstrzygniecie == w,
            "rodzaj": lambda w: d.rodzaj == w,
            "przepis": lambda w: any(w.lower() in e.lower() for e in d.przepisy),
            "przewodniczacy": lambda w: w.lower() in d.przewodniczacy.lower(),
            "strona": lambda w: w.lower() in (d.odwolujacy + " " + d.zamawiajacy).lower(),
        }
        for pole, warunek in warunki.items():
            wartosc = params.get(f.get(pole, ""))
            if wartosc and not warunek(wartosc):
                return False
        return True

    def _rekord_listy(self, d: DokumentPokazowy) -> dict[str, object]:
        r = self._k.ksztalt.lista.rekord
        return {
            r.referencja: d.slug,
            r.sygnatura_glowna: d.sygnatury[0],
            r.sygnatury: list(d.sygnatury),
            r.data_wydania: d.data_wydania.isoformat(),
            "demo": True,
        }

    # ------------------------------------------------------------------------- dokument

    def rekord(self, d: DokumentPokazowy) -> dict[str, object]:
        """Rekord dokumentu w polach z kontraktu plus pole `demo` (Z-3, znacznik 6)."""
        m = self._k.ksztalt.dokument.pola_metadanych
        return {
            self._k.ksztalt.lista.rekord.referencja: d.slug,
            m.sygnatura_glowna: d.sygnatury[0],
            m.sygnatury: list(d.sygnatury),
            m.data_wydania: d.data_wydania.isoformat(),
            m.data_rozprawy: None if d.data_rozprawy is None else d.data_rozprawy.isoformat(),
            m.rodzaj: d.rodzaj,
            m.rozstrzygniecie: d.rozstrzygniecie,
            m.rozstrzygniecie_surowe: d.rozstrzygniecie_surowe,
            m.przewodniczacy: d.przewodniczacy,
            m.odwolujacy: d.odwolujacy,
            m.zamawiajacy: d.zamawiajacy,
            m.przepisy: list(d.przepisy),
            m.koszty: d.koszty,
            m.url_zrodla: d.url_zrodla,
            self._k.ksztalt.dokument.pole_tresci: d.tresc,
            "demo": True,
        }
