"""Wycena i punkt decyzji (ADR-0008 Z-5, Z-6) — faza 3, etap II.

Cztery gwarancje: wycena odtwarza wiersz architektury 5.3 (rocznik ≈ 3 doby, nie 72 minuty);
decyzja pada dokładnie raz, przed pierwszym dokumentem, bez dodatkowego żądania; odmowa zostawia
przebieg `przerwany` bez żądania o dokument; ścieżka produkcyjna buduje klienta **bez**
podstawionego transportu — lustro testu z `ceidg-tool`, którego tu brakowało (ADR-0008 §4).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from kio_tool import pipeline
from kio_tool.errors import ConsentMissingError
from kio_tool.store import Store
from kio_tool.ui import texts
from kio_tool.wycena import Wycena, czas_zadan, wycen
from tests.test_odpornosc_wspolne import (
    KONTRAKT,
    KRYTERIA,
    LICZNIK,
    LISTA,
    SerwisAwaryjny,
    _bez_klucza_ze_srodowiska,
    jedyny_przebieg,
    store,
)
from tests.wsparcie_sondy import UA_TESTOWY, ZegarTestowy

__all__ = ["_bez_klucza_ze_srodowiska", "store"]

OKNA = [(okno.limit, okno.sekund) for okno in KONTRAKT.tempo.okna]


def _pobierz(store: Store, serwis: SerwisAwaryjny, decyzja: pipeline.Decyzja) -> Any:
    from functools import partial

    from kio_tool.httpclient import build_http_client

    return pipeline.pobierz(
        "atlas",
        KRYTERIA,
        store,
        zgoda=False,
        user_agent=UA_TESTOWY,
        decyzja=decyzja,
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(serwis)),
        zegar=ZegarTestowy(),
    )


# --- wycena -----------------------------------------------------------------------------------


def test_rocznik_to_doby_a_nie_minuty() -> None:
    """Architektura 5.3: rocznik 2024 to 4 266 orzeczeń; przy oknie dobowym 1 400 — trzy doby."""
    w = wycen(
        zgloszone=4266,
        maks=None,
        juz_objetych=0,
        zadan_juz=1,
        na_strone=100,
        odstep_s=KONTRAKT.tempo.odstep_s,
        okna=OKNA,
    )
    assert (w.dokumentow, w.stron_listy, w.zadan) == (4266, 42, 4308)
    assert w.czas_s == 3 * 86400
    assert texts.czas_ludzki(w.czas_s) == "3 doby 0 h"


def test_maks_i_wznowienie_zmniejszaja_wycene() -> None:
    w = wycen(
        zgloszone=295,
        maks=100,
        juz_objetych=40,
        zadan_juz=1,
        na_strone=100,
        odstep_s=1.0,
        okna=OKNA,
    )
    assert (w.dokumentow, w.stron_listy, w.zadan) == (60, 0, 60)


def test_brak_liczby_z_kanalu_daje_wycene_pusta() -> None:
    w = wycen(
        zgloszone=None,
        maks=None,
        juz_objetych=0,
        zadan_juz=1,
        na_strone=100,
        odstep_s=1.0,
        okna=OKNA,
    )
    assert w.zadan is None
    assert "nie podał liczby" in texts.tabela_kosztow(w, prog_zgody=50).as_text()


def test_czas_to_maksimum_po_odstepie_i_oknach() -> None:
    assert czas_zadan(0, 1.0, OKNA) == 0.0
    assert czas_zadan(10, 1.0, OKNA) == 9.0
    assert czas_zadan(451, 0.01, [(450, 60.0)]) == 60.0


def test_tabela_mowi_o_zgodzie_powyzej_progu() -> None:
    w = Wycena(dokumentow=295, stron_listy=2, zadan=297, czas_s=296.0, zadan_juz=1)
    tekst = texts.tabela_kosztow(w, prog_zgody=50, czas_pokazu_s=74.0).as_text()
    assert "297" in tekst and "przebieg masowy" in tekst and "4 min" in tekst


# --- decyzja w potoku ---------------------------------------------------------------------------


def _licznik_wywolan(werdykt: pipeline.Werdykt) -> tuple[list[Wycena], pipeline.Decyzja]:
    wyceny: list[Wycena] = []

    def decyzja(w: Wycena) -> pipeline.Werdykt:
        wyceny.append(w)
        return werdykt

    return wyceny, decyzja


def test_decyzja_pada_raz_przed_pierwszym_dokumentem(store: Store) -> None:
    serwis = SerwisAwaryjny()
    wyceny, decyzja = _licznik_wywolan("zgoda")

    wynik = _pobierz(store, serwis, decyzja)

    assert len(wyceny) == 1, "wycena jest jedna na wywołanie"
    assert wyceny[0].dokumentow == LISTA[LICZNIK]
    assert wyceny[0].zadan_juz == 1, "w chwili wyceny poszła wyłącznie pierwsza strona listy"
    assert wynik.status == "zakonczony"


def test_odmowa_po_wycenie_nie_wysyla_zadania_o_dokument(store: Store) -> None:
    serwis = SerwisAwaryjny()
    _, decyzja = _licznik_wywolan("odmowa")

    with pytest.raises(ConsentMissingError, match="odmówił po wycenie"):
        _pobierz(store, serwis, decyzja)

    assert serwis.dokumentow == 0
    assert store.get_run(jedyny_przebieg(store)).status == "przerwany"


def test_bez_zgody_zachowuje_prog_sprzed_adr_0008(store: Store) -> None:
    """Ścieżka flag bez `--zgoda`: przebieg masowy nadal staje przed pierwszym dokumentem."""
    serwis = SerwisAwaryjny()
    with pytest.raises(ConsentMissingError):
        _pobierz(store, serwis, pipeline.decyzja_z_flagi(False))
    assert serwis.dokumentow == 0


def test_produkcja_buduje_klienta_bez_podstawionego_transportu(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-0008 §4: podstawienie transportu (tryb pokazowy, testy) żyje w korzeniu kompozycji.
    Bez `klient_factory` potok woła `build_http_client` bez `transport=` — inaczej atrapa mogłaby
    przeciec na ścieżkę produkcyjną bez jednego czerwonego testu."""
    wywolania: list[dict[str, object]] = []

    class StopError(Exception):
        pass

    def szpieg(**kwargs: object) -> Callable[..., object]:
        wywolania.append(kwargs)
        raise StopError

    monkeypatch.setattr(pipeline, "build_http_client", szpieg)
    with pytest.raises(StopError):
        pipeline.pobierz("atlas", KRYTERIA, store, zgoda=False, user_agent=UA_TESTOWY)
    assert wywolania and "transport" not in wywolania[0]
