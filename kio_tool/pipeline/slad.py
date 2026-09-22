"""Puls przebiegu i ślad żądań do bazy (ADR-0009 Z-2).

Puls idzie przez `Events` w jedynych jednostkach, w których doktryna pozwala go liczyć: żądania
wysłane (`on_request`) i dokumenty zapisane (`on_document`) — nigdy strony (`progress.py`).
"""

from __future__ import annotations

from ..clock import Clock, utc_iso
from ..logbook import Wynik
from ..progress import Events
from ..store import (
    Store,
)


class _Puls:
    """Otulina `Events`: pamięta liczbę dokumentów w zakresie i liczbę żądań **wysłanych**.

    `zadan` rośnie w `_SladDoBazy.zanotuj`, nie w `on_request` (ADR-0007 Z-9): `on_request` pada
    wyłącznie na ścieżce odpowiedzi, więc żądanie, które opuściło proces i nie wróciło, nie
    liczyło się do progu zgody. Z ponowieniami ta różnica przestaje być ograniczona — przebieg
    mógłby wysłać ponad `PROG_ZGODY` żądań, nie pytając o zgodę ani razu.
    """

    def __init__(self, inner: Events) -> None:
        self._inner = inner
        self.zadan = 0
        self.razem: int | None = None

    def on_request(self, endpoint: str, status: int, elapsed_s: float) -> None:
        self._inner.on_request(endpoint, status, elapsed_s)

    def on_page(self, page_index: int, candidates: int, total: int | None) -> None:
        if total is not None:
            self.razem = total
        self._inner.on_page(page_index, candidates, total)

    def on_document(self, saved: int, total: int | None) -> None:
        self._inner.on_document(saved, total)

    def on_version(self, doc_id: str, content_sha256: str) -> None:
        self._inner.on_version(doc_id, content_sha256)

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        self._inner.on_wait(seconds, reason, resume_at_epoch)

    def on_parse(self, done: int, total: int) -> None:
        self._inner.on_parse(done, total)

    def on_export(self, done: int, total: int) -> None:
        self._inner.on_export(done, total)

    def on_message(self, text: str) -> None:
        self._inner.on_message(text)

    def close(self) -> None:
        self._inner.close()


class _SladDoBazy:
    """`SladZadan` nad `requests_log`: wiersz w chwili powrotu żądania, nie po całym przebiegu."""

    def __init__(self, store: Store, run_id: str, zegar: Clock, puls: _Puls) -> None:
        self._store = store
        self._run_id = run_id
        self._zegar = zegar
        self._puls = puls

    def zanotuj(self, wynik: Wynik) -> Wynik:
        # Licznik zgody tutaj, nie w `on_request` (ADR-0007 Z-9): kanał woła `zanotuj` dla
        # **każdego** żądania, które opuściło proces — z odpowiedzią i bez niej.
        if wynik.wyslane:
            self._puls.zadan += 1
        ksztalt = (
            "—"
            if wynik.ksztalt_zgodny is None
            else ("zgodny" if wynik.ksztalt_zgodny else "NIEZGODNY")
        )
        self._store.log_request(
            self._run_id,
            ts=utc_iso(self._zegar.wall()),
            metoda=wynik.metoda,
            url=wynik.adres,
            status=wynik.status,
            ms=round(wynik.czas_s * 1000),
            bajtow=wynik.bajtow,
            sha256=wynik.sha256,
            ksztalt=ksztalt,
            retry_after_s=wynik.retry_after_s,
            proba=wynik.proba,
        )
        return wynik
