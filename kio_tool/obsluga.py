"""Obsługa operatora: wydruki wspólne dla flag i kreatora oraz `Akcje` kreatora (ADR-0008 Z-7).

Wyniesione z `cli.py`, bo kreator potrzebuje tych samych wydruków co polecenia — ten sam
rachunek przebiegu, ten sam blok eksportu, ta sama tabela trafień — a `cli.py` zbliżał się do
sufitu 800 linii. Ten moduł stoi po tej samej stronie reguły 9 co `cli.py`: **nie pisze żadnego
zdania**, każdy napis bierze z `ui/texts.py`, i jest objęty tym samym skanem.

`AkcjeKreatora` implementuje protokół `ui.flow.Akcje` nad `pipeline` i otwartym `Store` — kreator
widzi czynności, nie magazyn (reguła 8, ADR-0008 C1).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from . import pipeline
from .clock import Clock
from .config import user_agent
from .console import PulsKonsoli
from .criteria import Criteria
from .errors import ConfigError
from .progress import Events
from .store import STATUSY_WZNAWIALNE, Store
from .ui import texts
from .ui.flow import DecyzjaKreatora, WynikPobrania
from .ui.texts import Block

LIMIT_WZNAWIALNYCH = 10


class Widok(Protocol):
    def block(self, block: Block) -> None: ...
    def message(self, text: str) -> None: ...
    def warning(self, text: str) -> None: ...


class WidokZBledem(Widok, Protocol):
    """Widok, który umie też powiedzieć, czemu wyniku nie ma — potrzebny obsłudze błędów w CLI.

    Osobny protokół, bo `error` idzie na `stderr` i nie należy do ścieżki wyniku: `obsluga`
    nigdy go nie woła, a `cli._obsluga_bledow` woła wyłącznie jego.
    """

    def error(self, text: str) -> None: ...


def eksport_i_raport(
    view: Widok,
    store: Store,
    *,
    run_ids: Sequence[str],
    kryteria: Criteria | None,
    formaty: Sequence[str],
    out: Path | None,
    cel: str | None,
    zegar: Clock,
) -> None:
    """Eksport z bazy plus podsumowanie — te same zdania po `pobierz`, `wznow` i `eksportuj`."""
    wynik = pipeline.eksportuj(
        store, run_ids=run_ids, kryteria=kryteria, formaty=formaty, out=out, cel=cel, zegar=zegar
    )
    if wynik.dokumentow == 0:
        view.message(texts.NIC_DO_EKSPORTU)
        for run_id in run_ids:
            # Przebieg sprzed schematu 2 ma żądania i dokumenty w korpusie, ale nie ma wierszy
            # w `run_documents` — „żaden dokument nie pasuje" jest wtedy prawdziwe i mylące naraz
            # (znalezisko testera 2026-09-18, zmierzone na bazie operatora).
            przebieg = store.get_run(run_id)
            if przebieg.dokumentow == 0 and przebieg.zadan > 0:
                view.message(texts.przebieg_bez_powiazan(przebieg.run_id, przebieg.zakres))
        if kryteria is not None:
            view.block(
                texts.zero_trafien(
                    kryteria,
                    w_korpusie=store.count("documents"),
                    zaindeksowanych=store.count_indexed(),
                    bez_daty=wynik.bez_daty_poza_filtrem,
                )
            )
        return
    view.block(
        texts.blok_eksportu(
            [str(s) for s in wynik.sciezki],
            wynik.dokumentow,
            wynik.formaty,
            wynik.bez_daty_poza_filtrem,
        )
    )


def raport_przebiegu(view: Widok, wynik: pipeline.Podsumowanie, baza: Path) -> None:
    view.message(
        texts.podsumowanie(
            run_id=wynik.run_id,
            status=wynik.status,
            kandydatow=wynik.kandydatow,
            nowych=wynik.nowych,
            pominietych=wynik.pominietych,
            zadan=wynik.zadan,
            baza=str(baza),
            zgloszone=wynik.zgloszone,
            objetych_lacznie=wynik.objetych_lacznie,
            pobranych_lacznie=wynik.pobranych_lacznie,
            zadan_lacznie=wynik.zadan_lacznie,
            bledow_odczytu=wynik.bledow_odczytu,
            brakujacych=wynik.brakujacych,
            ponowien_lacznie=wynik.ponowien_lacznie,
        )
    )


def pokaz_wyszukanie(view: Widok, store: Store, kryteria: Criteria, *, limit: int) -> int:
    """Tabela trafień z liczbami nad nią — ta sama po `szukaj` i w kreatorze. Zwraca liczbę
    trafień, bo kreator proponuje eksport tylko wtedy, gdy jest co eksportować."""
    wynik = pipeline.szukaj(store, kryteria, limit=limit)
    for ostrzezenie in kryteria.ostrzezenia():
        view.warning(texts.uwaga(ostrzezenie))
    if wynik.trafien == 0:
        view.block(
            texts.zero_trafien(
                kryteria,
                w_korpusie=wynik.w_korpusie,
                zaindeksowanych=wynik.zaindeksowanych,
                bez_daty=wynik.bez_daty_poza_filtrem,
            )
        )
        return 0
    wiersze = tuple(
        (
            t.sygnatura or t.source_ref,
            t.data_wydania or "",
            t.rozstrzygniecie or "",
            t.fragment,
        )
        for t in wynik.trafienia
    )
    view.block(
        texts.blok_wyszukiwania(
            wiersze,
            fraza=kryteria.fraza,
            w_korpusie=wynik.w_korpusie,
            zaindeksowanych=wynik.zaindeksowanych,
            trafien=wynik.trafien,
            bez_daty_poza_filtrem=wynik.bez_daty_poza_filtrem,
        )
    )
    return wynik.trafien


class AkcjeKreatora:
    """`ui.flow.Akcje` nad `pipeline` i `Store` otwartym na całą sesję kreatora."""

    prog_zgody = pipeline.PROG_ZGODY

    def __init__(
        self,
        view: Widok,
        store: Store,
        sciezka: Path,
        zegar: Clock,
        *,
        klient_factory: pipeline.KlientFactory | None = None,
        tozsamosc: Callable[[], str] = user_agent,
        czas_pokazu: Callable[[float], float] | None = None,
        limit_trafien: int = 20,
        klucz_z_srodowiska: bool = True,
        katalog_wynikow: Path | None = None,
    ) -> None:
        self._view = view
        self._store = store
        self._sciezka = sciezka
        self._zegar = zegar
        self._klient_factory = klient_factory
        self._tozsamosc = tozsamosc
        self.czas_pokazu = czas_pokazu
        self._limit = limit_trafien
        self._klucz = klucz_z_srodowiska
        self._wyniki = katalog_wynikow
        """Pokaz eksportuje do własnego katalogu (Z-3, znacznik 4), nigdy do `wyniki/` operatora."""

    def brak_kontaktu(self) -> str | None:
        try:
            self._tozsamosc()
        except ConfigError:
            return texts.BRAK_KONTAKTU
        return None

    def stan(self) -> texts.StanKorpusu:
        """Liczby na pierwszy ekran — odczyt z lokalnej bazy, zero żądań."""
        return texts.StanKorpusu(
            dokumentow=self._store.count("documents"),
            zaindeksowanych=self._store.count_indexed(),
            przerwanych=len(self.wznawialne()),
            sciezka=str(self._sciezka),
        )

    def wznawialne(self) -> Sequence[tuple[str, str]]:
        return [
            (p.run_id, p.zakres)
            for p in self._store.list_runs(LIMIT_WZNAWIALNYCH, statuses=STATUSY_WZNAWIALNE)
            if p.kryteria is not None
        ]

    def pobierz(self, kryteria: Criteria, decyzja: DecyzjaKreatora) -> WynikPobrania:
        wynik = pipeline.pobierz(
            pipeline.KANAL_DOMYSLNY,
            kryteria,
            self._store,
            self._puls(),
            zgoda=False,
            user_agent=self._tozsamosc(),
            decyzja=decyzja,
            klient_factory=self._klient_factory,
            klucz_z_srodowiska=self._klucz,
            zegar=self._zegar,
        )
        raport_przebiegu(self._view, wynik, self._sciezka)
        return WynikPobrania(wynik.run_id, wynik.objetych_lacznie)

    def wznow(self, run_id: str, decyzja: DecyzjaKreatora) -> WynikPobrania:
        wynik = pipeline.wznow(
            self._store,
            run_id,
            self._puls(),
            zgoda=False,
            user_agent=self._tozsamosc(),
            decyzja=decyzja,
            klient_factory=self._klient_factory,
            klucz_z_srodowiska=self._klucz,
            zegar=self._zegar,
        )
        raport_przebiegu(self._view, wynik, self._sciezka)
        return WynikPobrania(wynik.run_id, wynik.objetych_lacznie)

    def szukaj(self, kryteria: Criteria) -> int:
        return pokaz_wyszukanie(self._view, self._store, kryteria, limit=self._limit)

    def eksportuj(
        self, *, run_ids: tuple[str, ...], kryteria: Criteria | None, format: str
    ) -> None:
        eksport_i_raport(
            self._view,
            self._store,
            run_ids=run_ids,
            kryteria=None if run_ids else kryteria,
            formaty=(format,),
            out=self._wyniki,
            cel=None,
            zegar=self._zegar,
        )

    def _puls(self) -> Events:
        return PulsKonsoli()
