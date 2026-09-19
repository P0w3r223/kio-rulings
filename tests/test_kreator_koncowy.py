"""Kreator na prawdziwym potoku: `AkcjeKreatora` nad `Store` i adapterem Atlasu na atrapie.

`test_ui_flow.py` sprawdza sekwencje na atrapie akcji; tu mierzone jest to, że te same odpowiedzi
operatora przechodzą przez `pipeline.pobierz` z decyzją kreatora — wycena raz, zgoda z pytania,
przebieg zakończony, eksport zapisany — i że odmowa nie kosztuje ani jednego żądania o dokument.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path

import httpx
import pytest

from kio_tool.clock import SystemClock
from kio_tool.httpclient import build_http_client
from kio_tool.obsluga import AkcjeKreatora
from kio_tool.store import Store
from kio_tool.ui import texts, wizard
from kio_tool.ui.prompts import NIE, TAK, SkryptowyPrompter
from kio_tool.ui.texts import Block
from tests.test_odpornosc_wspolne import SerwisAwaryjny, _bez_klucza_ze_srodowiska
from tests.wsparcie_sondy import UA_TESTOWY, ZegarTestowy

__all__ = ["_bez_klucza_ze_srodowiska"]


class Ekran:
    def __init__(self) -> None:
        self.teksty: list[str] = []

    def block(self, block: Block) -> None:
        self.teksty.append(block.as_text())

    def message(self, text: str) -> None:
        self.teksty.append(text)

    def warning(self, text: str) -> None:
        self.teksty.append(text)


def _kreator(tmp_path: Path, serwis: SerwisAwaryjny, *odpowiedzi: str) -> tuple[Store, Ekran]:
    store = Store.open(":memory:", clock=ZegarTestowy())
    ekran = Ekran()
    akcje = AkcjeKreatora(
        ekran,
        store,
        tmp_path / "korpus.sqlite",
        ZegarTestowy(),
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(serwis)),
        tozsamosc=lambda: UA_TESTOWY,
    )
    wizard.uruchom(SkryptowyPrompter([*odpowiedzi, texts.MENU_WYJDZ]), akcje, ekran)
    return store, ekran


@pytest.fixture(autouse=True)
def _wyniki_w_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)


def test_kreator_pobiera_z_zgoda_z_pytania_i_eksportuje(tmp_path: Path) -> None:
    serwis = SerwisAwaryjny()
    store, ekran = _kreator(
        tmp_path,
        serwis,
        texts.MENU_POBIERZ,
        texts.CEL_DATY,
        "2024-01-01",
        "2024-01-31",
        TAK,
        "jsonl",
    )
    tekst = "\n".join(ekran.teksty)
    assert "Koszt przebiegu" in tekst
    assert store.count("documents") == 100
    assert store.list_runs(1)[0].status == "zakonczony"
    assert "Eksport" in tekst


def test_odmowa_w_kreatorze_nie_wysyla_zadania_o_dokument(tmp_path: Path) -> None:
    serwis = SerwisAwaryjny()
    store, ekran = _kreator(
        tmp_path, serwis, texts.MENU_POBIERZ, texts.CEL_DATY, "2024-01-01", "", NIE
    )
    assert serwis.dokumentow == 0
    assert store.list_runs(1)[0].status == "przerwany"
    assert any("odmówił po wycenie" in t for t in ekran.teksty)


def test_przerwany_przebieg_trafia_do_menu_wznow(tmp_path: Path) -> None:
    serwis = SerwisAwaryjny()
    store, _ = _kreator(tmp_path, serwis, texts.MENU_POBIERZ, texts.CEL_DATY, "2024-01-01", "", NIE)
    akcje = AkcjeKreatora(
        Ekran(), store, tmp_path / "k.sqlite", SystemClock(), tozsamosc=lambda: UA_TESTOWY
    )
    assert [run_id for run_id, _ in akcje.wznawialne()] == [store.list_runs(1)[0].run_id]
