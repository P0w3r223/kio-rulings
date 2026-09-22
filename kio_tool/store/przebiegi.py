"""Przebiegi i dziennik żądań (ADR-0009 Z-1)."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from datetime import datetime

from ..clock import utc_iso
from ..config import mask_tokens
from ..errors import RunNotFoundError, StoreError
from ..ratelimit import RequestStamp
from .model import (
    STATUSY_PRZEBIEGU,
    STATUSY_WZNAWIALNE,
    Przebieg,
)
from .polaczenie import _Rdzen


class _Przebiegi(_Rdzen):
    """Przebiegi, powiązania z dokumentami, punkt kontrolny i dziennik żądań."""

    # ------------------------------------------------------------------------ przebiegi

    def start_run(
        self, *, kanal: str, zakres: str, started_at: str, kryteria: str, fingerprint: str
    ) -> str:
        run_id = f"{kanal}-{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            "INSERT INTO runs (run_id, kanal, zakres, started_at, status, kryteria, fingerprint) "
            "VALUES (?, ?, ?, ?, 'w_toku', ?, ?)",
            (run_id, kanal, zakres, started_at, kryteria, fingerprint),
        )
        return run_id

    def find_run(
        self, fingerprint: str, statuses: Sequence[str], *, kanal: str | None = None
    ) -> Przebieg | None:
        """Ostatni przebieg o tym odcisku kryteriów w jednym z podanych stanów, albo `None`.

        Wznowienie dotyczy **tych samych kryteriów i tego samego kanału**: inne kryteria są innym
        przebiegiem, a punkt kontrolny z jednego nie mówi nic o stronach drugiego; odcisk nie
        niesie kanału, więc kanał idzie osobno (przegląd kodu 2026-09-18 — bez niego `find_run`
        z kanału `atlas` znajdował przebieg kanału `saos`). Filtr jest w zapytaniu (lekcja
        z `ceidg-tool`, `list_runs`).
        """
        przebiegi = self.list_runs(
            limit=1, statuses=tuple(statuses), fingerprint=fingerprint, kanal=kanal
        )
        return przebiegi[0] if przebiegi else None

    def resume_run(self, run_id: str, *, takze_blad: bool = False) -> Przebieg:
        """Przestawia przerwany albo osierocony przebieg na `w_toku` i zwraca go z punktem
        kontrolnym; `takze_blad` dopuszcza też przebieg zakończony błędem.

        `takze_blad` jest dla wznowienia **jawnego** (`wznow --run-id`): po wygasłym kluczu albo
        odmowie serwisu stan ustępuje, a punkt kontrolny jest wart tyle stron listy, ile trzeba
        by wysłać od nowa. Wznowienie automatyczne w `pobierz` go nie dostaje, żeby złamany
        kontrakt nie wracał sam przy każdym uruchomieniu (przegląd kodu 2026-09-18).

        Osierocony to `w_toku` bez procesu, który by go kończył: zanik zasilania, `taskkill /F`,
        dysk pełny na tyle, że `finish_run` w `finally` też nie przeszedł (tester 2026-09-18).
        `finish_run` nie dostał wtedy sterowania, więc status mówi „pracuję" o przebiegu, który
        nie pracuje — a punkt kontrolny w `ostatnia_strona` jest prawdziwy i wart tyle, ile stron
        listy trzeba by wysłać od nowa. Jeden operator i jeden proces (nagłówek modułu) rozstrzyga,
        że `w_toku` przy wznawianiu znaczy „osierocony", nie „inny proces pracuje".
        """
        przebieg = self.get_run(run_id)
        dozwolone = (*STATUSY_WZNAWIALNE, "blad") if takze_blad else STATUSY_WZNAWIALNE
        if przebieg.status not in dozwolone:
            raise StoreError(
                f"Przebieg {run_id} ma status {przebieg.status!r}; wznowić da się wyłącznie "
                "przebieg przerwany albo osierocony (pracujący bez procesu)."
            )
        self._conn.execute(
            "UPDATE runs SET status = 'w_toku', finished_at = NULL, powod = NULL WHERE run_id = ?",
            (run_id,),
        )
        return self.get_run(run_id)

    def checkpoint(self, run_id: str, strona: int) -> None:
        self._conn.execute("UPDATE runs SET ostatnia_strona = ? WHERE run_id = ?", (strona, run_id))

    def finish_run(
        self, run_id: str, *, status: str, finished_at: str, powod: str | None = None
    ) -> None:
        if status not in STATUSY_PRZEBIEGU or status == "w_toku":
            raise StoreError(f"Nieznany status końcowy przebiegu: {status!r}")
        self._conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, powod = ? WHERE run_id = ?",
            (status, finished_at, powod, run_id),
        )

    def link_run_document(self, run_id: str, doc_id: str, *, position: int, nowy: bool) -> None:
        """Wiąże kandydata z przebiegiem — nowego i pominiętego tak samo.

        `INSERT OR IGNORE`: wznowiony przebieg listuje ostatnią stronę od nowa, więc kandydat
        zapisany przed przerwaniem wraca jako pominięty — a jego pierwszy wiersz (`nowy = 1`)
        ma zostać, bo to on mówi prawdę o tym, co ten przebieg pobrał.
        """
        self._conn.execute(
            "INSERT OR IGNORE INTO run_documents (run_id, doc_id, position, nowy) "
            "VALUES (?, ?, ?, ?)",
            (run_id, doc_id, position, 1 if nowy else 0),
        )

    def iter_run_documents(self, run_id: str) -> Iterator[str]:
        for w in self._conn.execute(
            "SELECT doc_id FROM run_documents WHERE run_id = ? ORDER BY position", (run_id,)
        ):
            yield str(w["doc_id"])

    def count_run_documents(self, run_id: str, *, nowe: bool | None = None) -> int:
        warunek = "" if nowe is None else f" AND nowy = {1 if nowe else 0}"
        return int(
            self._conn.execute(
                f"SELECT COUNT(*) FROM run_documents WHERE run_id = ?{warunek}", (run_id,)
            ).fetchone()[0]
        )

    def count_requests(self, run_id: str, *, ponowienia: bool = False) -> int:
        """Żądania przebiegu z dziennika; `ponowienia=True` liczy wyłącznie próby od drugiej."""
        warunek = " AND proba > 1" if ponowienia else ""
        return int(
            self._conn.execute(
                f"SELECT COUNT(*) FROM requests_log WHERE run_id = ?{warunek}", (run_id,)
            ).fetchone()[0]
        )

    _SELECT_RUN = (
        "SELECT r.*, (SELECT COUNT(*) FROM run_documents rd WHERE rd.run_id = r.run_id) "
        "AS dokumentow, (SELECT COUNT(*) FROM requests_log q WHERE q.run_id = r.run_id) AS zadan "
        "FROM runs r"
    )

    def get_run(self, run_id: str) -> Przebieg:
        wiersz = self._conn.execute(f"{self._SELECT_RUN} WHERE r.run_id = ?", (run_id,)).fetchone()
        if wiersz is None:
            raise RunNotFoundError(
                f"Nie ma przebiegu `{run_id}`. Listę identyfikatorów wypisuje `runy`."
            )
        return _przebieg(wiersz)

    def list_runs(
        self,
        limit: int = 20,
        *,
        statuses: Sequence[str] | None = None,
        fingerprint: str | None = None,
        kanal: str | None = None,
    ) -> list[Przebieg]:
        """Ostatnie przebiegi, filtrowane **w zapytaniu**, nie po jego wyniku.

        Filtr nałożony w Pythonie na wynik `LIMIT 20` znaczy „przejrzyj dwadzieścia ostatnich
        i zostaw pasujące", a nie „pokaż ostatnie pasujące". W `ceidg-tool` (`store.py:573`)
        przy dwudziestu nowszych zakończonych pobraniach `wznow` meldował, że nie ma czego
        wznawiać, choć przerwany run stał na pozycji dwudziestej pierwszej.
        """
        if limit < 1:
            # Jak w `szukaj`: ujemny `LIMIT` znaczy w SQLite „wszystko", więc `runy --limit -1`
            # pokazywało całość, a `--limit 0` pustą tabelę (tester 2026-09-18).
            raise StoreError(f"Limit wierszy ma być dodatni, a jest {limit}.")
        if statuses is not None and not statuses:
            return []
        warunki: list[str] = []
        argumenty: list[object] = []
        if statuses is not None:
            warunki.append("r.status IN ({})".format(",".join("?" for _ in statuses)))
            argumenty.extend(statuses)
        if fingerprint is not None:
            warunki.append("r.fingerprint = ?")
            argumenty.append(fingerprint)
        if kanal is not None:
            warunki.append("r.kanal = ?")
            argumenty.append(kanal)
        gdzie = (" WHERE " + " AND ".join(warunki)) if warunki else ""
        wiersze = self._conn.execute(
            f"{self._SELECT_RUN}{gdzie} ORDER BY r.started_at DESC, r.rowid DESC LIMIT ?",
            (*argumenty, limit),
        ).fetchall()
        return [_przebieg(w) for w in wiersze]

    def count_runs(self) -> int:
        """Ile przebiegów jest w bazie **naprawdę**, bez okna `LIMIT`."""
        return self.count("runs")

    # ------------------------------------------------------------------ dziennik żądań

    def log_request(
        self,
        run_id: str,
        *,
        ts: str,
        metoda: str,
        url: str,
        status: int | None,
        ms: int,
        bajtow: int,
        sha256: str | None,
        ksztalt: str,
        retry_after_s: float | None = None,
        proba: int = 1,
    ) -> None:
        """Jeden wiersz na żądanie, trwały natychmiast — poza `transakcja()` zapis jest atomowy sam."""  # noqa: E501
        self._conn.execute(
            "INSERT INTO requests_log (run_id, ts, metoda, url_redacted, status, ms, bajtow, "
            "sha256, ksztalt, retry_after_s, proba) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                ts,
                metoda,
                mask_tokens(url),
                status,
                ms,
                bajtow,
                sha256,
                ksztalt,
                retry_after_s,
                proba,
            ),
        )

    def request_stamps(self, kanal: str, since_epoch: float) -> list[RequestStamp]:
        """Historia żądań kanału jako znaczniki limitera — grzeczność ma przeżyć proces.

        `RateLimiter` widzi tylko żądania z historii; wznowienie z pustą pamięcią procesu
        zaczynałoby od serii bez odstępu i bez blokady po 429, choć dziennik obie rzeczy pamięta.
        """
        # Odcięcie po `ts` w zapytaniu, nie po wczytaniu całej historii kanału (przegląd kodu
        # 2026-09-18) — `ts` jest ISO-8601 UTC o stałym układzie, więc porównanie leksykograficzne
        # jest porównaniem czasu, a `requests_log_ts_idx` ma wreszcie czytelnika. Filtr w Pythonie
        # niżej zostaje jako zabezpieczenie przed znacznikiem w innej postaci.
        wiersze = self._conn.execute(
            "SELECT r.ts, r.url_redacted, r.status, r.retry_after_s FROM requests_log r "
            "JOIN runs p USING (run_id) WHERE p.kanal = ? AND r.ts >= ? ORDER BY r.ts",
            (kanal, utc_iso(since_epoch)),
        ).fetchall()
        znaczniki = [
            RequestStamp(
                _epoch(str(w["ts"])),
                str(w["url_redacted"]),
                w["status"],
                None if w["retry_after_s"] is None else float(w["retry_after_s"]),
            )
            for w in wiersze
        ]
        return [z for z in znaczniki if z.ts_epoch >= since_epoch]


def _przebieg(wiersz: sqlite3.Row) -> Przebieg:
    return Przebieg(
        run_id=str(wiersz["run_id"]),
        kanal=str(wiersz["kanal"]),
        zakres=str(wiersz["zakres"]),
        started_at=str(wiersz["started_at"]),
        finished_at=None if wiersz["finished_at"] is None else str(wiersz["finished_at"]),
        status=str(wiersz["status"]),
        ostatnia_strona=None
        if wiersz["ostatnia_strona"] is None
        else int(wiersz["ostatnia_strona"]),
        powod=None if wiersz["powod"] is None else str(wiersz["powod"]),
        kryteria=None if wiersz["kryteria"] is None else str(wiersz["kryteria"]),
        fingerprint=None if wiersz["fingerprint"] is None else str(wiersz["fingerprint"]),
        dokumentow=int(wiersz["dokumentow"]),
        zadan=int(wiersz["zadan"]),
    )


def _epoch(ts: str) -> float:
    """`2026-09-18T10:35:25Z` (postać z `clock.utc_iso`) na sekundy epoch."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
