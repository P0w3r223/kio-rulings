"""SQLite: dokumenty, wersje surowe, przebiegi, dziennik żądań, metadane, indeks pełnotekstowy —
model danych 4.4 w wersji minimalnej, po przyjęciu ADR-0001 (2026-09-18); schemat 2 od etapu IV.

Bramka `store.py` → ADR-0001 (`tests/test_bramki_faz.py`) jest strażnikiem miny 1: w `ceidg-tool`
jeden wpis miał dwie pisownie identyfikatora, klucz główny był wrażliwy na wielkość liter, a jedna
noc kosztowała 2 681 żądań i zero użytecznych rekordów. Ten plik powstał **po** rozstrzygnięciu
tożsamości, więc nie zna pisowni referencji — dostaje gotowy `doc_id` z `docid.document_id`,
jedynego producenta tożsamości (reguła 14), i nie składa go sam z niczego.

Niezmiennik wznowienia (bramka fazy 1, audyt 9; ADR-0001 2.3): `raw_versions (doc_id,
content_sha256)` jest kluczem głównym i zapis idzie `INSERT OR IGNORE`, więc przerwany i wznowiony
przebieg nie tworzy duplikatu nawet przy nieaktualnym punkcie kontrolnym. Dokument, jego wersja,
powiązanie z przebiegiem i punkt kontrolny idą w jednej transakcji (`transakcja()`), po awarii są
wszystkie albo żadne — to jest to samo zdanie, które `ceidg-tool` zapisał o rekordach strony
i checkpoincie. `content_bytes` to bajty dokładnie takie, jakie przyszły po drucie (reguła 19
w brzmieniu ADR-0005 Z-5), a `content_sha256` liczy **ten** moduł z tego, co zapisuje — i porównuje
ze skrótem podanym przez kanał, bo skrót niezgodny z bajtami zrywa łańcuch dowodowy przy pierwszym
zapisie.


Czego tu **nie ma** wobec wzorca z `ceidg-tool` (1 208 linii), z powodem przy każdym: dzierżawy
blokady (jeden operator i jeden proces; wraca razem z harmonogramem), kwarantanny uszkodzonej bazy
i `integrity_check` przy otwarciu (bez pomiaru, że to się zdarza, byłoby to mechanizmem bez
przedmiotu — ADR-0005 §1). Nie ma tu `httpx` (reguła 3) ani `rich` (reguła 4).

Od 2026-09-22 (ADR-0009) klasa jest złożona z klas cząstkowych: `zapis`, `wyszukiwanie`,
`przebiegi` nad rdzeniem z `polaczenie`; historia schematów mieszka w `schemat`.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from ..clock import Clock
from ..criteria import Criteria
from ..errors import KioError, StoreError
from .polaczenie import _Polaczenie, blad_bazy
from .przebiegi import _Przebiegi
from .schemat import _SCHEMA, ID_BAZY_POKAZOWEJ, SCHEMA_VERSION
from .wyszukiwanie import _Wyszukiwanie
from .zapis import _ZapisKorpusu

DOMYSLNY_BUSY_TIMEOUT_S = 30.0


class Store(_ZapisKorpusu, _Wyszukiwanie, _Przebiegi):
    """Baza lokalna korpusu. `open` tworzy katalog i schemat; `":memory:"` do testów."""

    def __init__(self, path: Path | str, *, clock: Clock, pokazowa: bool = False) -> None:
        self._path = str(path)
        self._clock = clock
        self.nowa = self._path != ":memory:" and not Path(self._path).exists()
        """Czy to otwarcie założyło bazę — `cli` mówi o tym zdaniem, bo literówka w `--baza`
        wygląda inaczej tak samo jak pierwsze uruchomienie."""
        try:
            if isinstance(path, Path):
                path.parent.mkdir(parents=True, exist_ok=True)
            # `isolation_level=None`: transakcjami steruje **ten** moduł jawnie (`transakcja()`),
            # a pojedynczy zapis poza nią jest atomowy sam z siebie. Domyślny tryb `sqlite3`
            # otwiera transakcję niejawnie przed pierwszym `INSERT` i zamyka ją dopiero przy
            # `commit()` — czyli wpis do `requests_log` czekałby w otwartej transakcji na koniec
            # przebiegu, a przerwany przebieg nie zostawiałby śladu po żądaniach, które już poszły.
            polaczenie = sqlite3.connect(
                self._path, timeout=DOMYSLNY_BUSY_TIMEOUT_S, isolation_level=None
            )
        except (sqlite3.Error, OSError) as blad:
            sterownika = blad if isinstance(blad, sqlite3.Error) else sqlite3.OperationalError(blad)
            raise blad_bazy(self._path, sterownika) from blad
        self._conn = _Polaczenie(polaczenie, self._path)
        try:
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            if self._path != ":memory:":
                # WAL: `Ctrl+C` w środku zapisu zostawia bazę spójną, a czytelnik nie blokuje
                # pisarza. `PRAGMA journal_mode` **zwraca** tryb wynikowy — nieprzeczytany
                # zostawiałby ciche nieprzejście na WAL bez obserwatora (lekcja z `ceidg-tool`).
                tryb = self._conn.execute("PRAGMA journal_mode = WAL").fetchone()
                self.journal_mode = str(tryb[0]).lower() if tryb else "?"
            else:
                self.journal_mode = "memory"
            self._migruj()
            self.pokazowa = self._sprawdz_tryb(pokazowa)
        except KioError:
            # `with Store.open(...)` nie wchodzi w `__exit__`, gdy `__init__` rzuci — bez tego
            # plik bazy zostawał zajęty na Windowsie po nieudanej migracji (przegląd 2026-09-18).
            polaczenie.close()
            raise

    def _sprawdz_tryb(self, pokazowa: bool) -> bool:
        """Znacznik bazy pokazowej zgodny z trybem otwarcia — albo `StoreError` ze zdaniem."""
        znacznik = int(self._conn.execute("PRAGMA application_id").fetchone()[0])
        if not pokazowa:
            if znacznik == ID_BAZY_POKAZOWEJ:
                raise StoreError(
                    f"Baza {self._path} jest bazą trybu pokazowego (dane fikcyjne). Otwórz ją "
                    "przez `kio-tool demo`; tryb produkcyjny nie dopisze do niej prawdziwych "
                    "orzeczeń."
                )
            return False
        if znacznik == ID_BAZY_POKAZOWEJ:
            return True
        pusta = self.count("documents") == 0 and self.count("runs") == 0
        if znacznik != 0 or not pusta:
            raise StoreError(
                f"Baza {self._path} nie jest bazą pokazową i nie jest pusta — tryb pokazowy nie "
                "zapisze fikcji do korpusu operatora."
            )
        self._conn.execute(f"PRAGMA application_id = {ID_BAZY_POKAZOWEJ}")
        return True

    def _migruj(self) -> None:
        """Schemat do wersji `SCHEMA_VERSION` w jednej transakcji — bez utraty danych.

        Instrukcje idą pojedynczo, nie `executescript`: ten ostatni zatwierdza otwartą transakcję
        przed uruchomieniem, więc migracja przerwana w połowie zostawiałaby bazę w wersji, której
        żaden numer nie opisuje. `PRAGMA user_version` ustawia się na końcu, w tej samej
        transakcji — baza jest albo w starej wersji z nietkniętymi danymi, albo w nowej.
        """
        wersja = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if wersja > SCHEMA_VERSION:
            raise StoreError(
                f"Baza {self._path} ma schemat w wersji {wersja}, a narzędzie zna {SCHEMA_VERSION}."
            )
        with self.transakcja():
            if wersja == 1:
                self._migruj_1_do_2()
            for instrukcja in _SCHEMA:
                self._conn.execute(instrukcja)
            if wersja == 1:
                self._dopisz_odciski_przebiegom_sprzed_schematu_2()
            if 0 < wersja < 3:
                self._migruj_do_3()
            if 0 < wersja < 4:
                self._odtworz_powiazania_sprzed_schematu_2()
            if 0 < wersja < 5:
                self._migruj_do_5()
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migruj_1_do_2(self) -> None:
        """Kolumny `runs.kryteria` i `runs.fingerprint` — `CREATE IF NOT EXISTS` ich nie dopisze
        do tabeli, która już istnieje. Obecność sprawdzana, nie zakładana: `ALTER TABLE … ADD`
        na istniejącej kolumnie jest błędem, a baza po przerwanej migracji może ją już mieć."""
        obecne = {str(w["name"]) for w in self._conn.execute("PRAGMA table_info(runs)")}
        for kolumna in ("kryteria", "fingerprint"):
            if kolumna not in obecne:
                self._conn.execute(f"ALTER TABLE runs ADD COLUMN {kolumna} TEXT")

    def _migruj_do_3(self) -> None:
        """Kolumna `requests_log.retry_after_s` (schemat 3, 2026-09-18) — prośba serwisu ma
        przeżyć proces razem z faktem odmowy. Znalezisko testera: wznowienie po 429 odczekiwało
        własną blokadę limitera (60 s) zamiast `Retry-After` (np. 300 s), bo dziennik nagłówka nie
        zapisywał. Obecność kolumny sprawdzana, nie zakładana — jak w `_migruj_1_do_2`; tabela
        w bazie schematu 1 i 2 istnieje, więc `CREATE IF NOT EXISTS` kolumny nie dopisze."""
        obecne = {str(w["name"]) for w in self._conn.execute("PRAGMA table_info(requests_log)")}
        if "retry_after_s" not in obecne:
            self._conn.execute("ALTER TABLE requests_log ADD COLUMN retry_after_s REAL")

    def _migruj_do_5(self) -> None:
        """Kolumna `requests_log.proba` (schemat 5, ADR-0007 Z-8) — numer próby żądania.

        Wiersze sprzed schematu 5 dostają 1 z wartości domyślnej i to jest prawda o nich: przed
        ADR-0007 żaden kanał nie ponawiał. Obecność kolumny sprawdzana, nie zakładana — jak
        w `_migruj_do_3`."""
        obecne = {str(w["name"]) for w in self._conn.execute("PRAGMA table_info(requests_log)")}
        if "proba" not in obecne:
            self._conn.execute(
                "ALTER TABLE requests_log ADD COLUMN proba INTEGER NOT NULL DEFAULT 1"
            )

    def _dopisz_odciski_przebiegom_sprzed_schematu_2(self) -> None:
        """Przebieg sprzed schematu 2 miał wyłącznie zakres dat (`od..do`), więc jego kryteria
        i odcisk da się odtworzyć z etykiety — i dzięki temu przebieg przerwany pod schematem 1
        wznawia się pod schematem 2 tym samym poleceniem `pobierz --od … --do …`. Etykieta
        w innej postaci zostawia oba pola puste: lepsza jawna luka niż zgadywany odcisk."""
        wiersze = self._conn.execute(
            "SELECT run_id, zakres FROM runs WHERE fingerprint IS NULL"
        ).fetchall()
        for wiersz in wiersze:
            kryteria = _kryteria_z_etykiety(str(wiersz["zakres"]))
            if kryteria is None:
                continue
            self._conn.execute(
                "UPDATE runs SET kryteria = ?, fingerprint = ? WHERE run_id = ?",
                (kryteria.canonical_json(), kryteria.fingerprint(), wiersz["run_id"]),
            )

    def _odtworz_powiazania_sprzed_schematu_2(self) -> None:
        """`run_documents` dla przebiegów sprzed schematu 2 — odtworzone z dziennika żądań.

        Przebieg zapisany pod schematem 1 nie ma ani jednego wiersza powiązania, więc
        `eksportuj --run-id` zwraca dla niego zero dokumentów, choć jego dokumenty leżą
        w korpusie. Migracja 1 → 2 dopisała wtedy odciski kryteriów, ale powiązań nie — i to
        jest druga luka po tamtej, nie ta sama.

        **Zasięg jest węższy, niż brzmi, i to jest wybór.** Przebieg przerwany pod schematem 1
        i wznowiony pod schematem 2 ma powiązania **częściowe** — tylko dla kandydatów obsłużonych
        po wznowieniu. Taki przebieg ta migracja pomija w całości, bo warunek `NOT EXISTS` jest
        per przebieg: dopisywanie brakujących wierszy do przebiegu, który część ma pierwotną,
        mieszałoby wartości pierwotne z rekonstruowanymi w jednej tabeli i bez znacznika, który
        by je rozróżnił. Jawna luka jest tu tańsza niż niejawna mieszanina (znalezisko testera
        2026-09-19; `test_przebieg_z_czescia_powiazan_zostaje_pominiety_w_calosci` przypina ten
        zasięg, więc jego zmiana nie przejdzie po cichu).

        Łączenie idzie po `requests_log.sha256` = `raw_versions.content_sha256`, a **nie** po
        adresie: `store.py` nie zna kształtu adresów kanału (reguła 22) i nie zacznie go tutaj
        poznawać. Skrót odpowiedzi jest przy tym mocniejszym łącznikiem niż adres — mówi, że ten
        przebieg przywiózł dokładnie te bajty, a nie że pytał o ten zasób. Odpowiedzi listy
        odpadają same, bo ich skrót nie ma wiersza w `raw_versions`.

        `nowy = 1` nie jest założeniem: potok nie wysyła żądania za dokument, który już jest
        w bazie — pomija go bez żądania i wiąże z `nowy = 0` — więc żądanie zakończone wersją
        w `raw_versions` znaczy, że dokument był dla tego przebiegu nowy. `position` odtwarza się
        z kolejności żądań i jest **rekonstrukcją, nie wartością pierwotną**: numeracja wychodzi
        ciągła (1..N), a pierwotna mogła mieć przerwy po wznowieniu, bo liczyła także kandydatów
        pominiętych. Dla przebiegu bez pominięć obie są tym samym ciągiem.

        Przebieg, który **ma** już powiązania, zostaje nietknięty: tam wartości są pierwotne,
        a rekonstrukcja byłaby ich pogorszeniem. Przebieg bez dokumentów (pomiar filtru, który
        zwrócił zero trafień) nie dostaje nic i to jest poprawne — jego `rd = 0` jest prawdą
        o wyniku, a nie luką po migracji.

        Skrót wskazujący na **więcej niż jeden** dokument jest odrzucany, nie zgadywany:
        `raw_versions` ma klucz `(doc_id, content_sha256)`, więc dwa dokumenty o identycznej
        treści są stanem reprezentowalnym, a złączenie bez tego warunku dopisałoby przebiegowi
        dokument, o który nigdy nie pytał (znalezisko testera 2026-09-19, zmierzone na bazie
        jednorazowej). Że w korpusie operatora takich skrótów nie ma, jest faktem o **tych
        danych**, nie własnością kodu — i dlatego warunek stoi w zapytaniu, a nie w zdaniu niżej.

        Zmierzone 2026-09-19 na bazie operatora: jeden przebieg z luką (299 żądań), 295
        dokumentów odtworzonych, 4 strony listy odrzucone przez brak wersji, zero
        niejednoznacznych skrótów, zgodność 295/295 z niezależnym odniesieniem — te same
        dokumenty powiązane z późniejszym przebiegiem na tym samym zakresie.
        """
        osierocone = [
            str(w["run_id"])
            for w in self._conn.execute(
                "SELECT run_id FROM runs r WHERE NOT EXISTS "
                "(SELECT 1 FROM run_documents rd WHERE rd.run_id = r.run_id)"
            )
        ]
        for run_id in osierocone:
            wiersze = self._conn.execute(
                "SELECT v.doc_id AS doc_id, MIN(q.ts) AS pierwsze FROM requests_log q "
                "JOIN raw_versions v ON v.content_sha256 = q.sha256 "
                "WHERE q.run_id = ? AND (SELECT COUNT(DISTINCT v2.doc_id) FROM raw_versions v2 "
                "WHERE v2.content_sha256 = q.sha256) = 1 "
                "GROUP BY v.doc_id ORDER BY pierwsze",
                (run_id,),
            ).fetchall()
            for position, wiersz in enumerate(wiersze, start=1):
                self.link_run_document(run_id, str(wiersz["doc_id"]), position=position, nowy=True)

    @classmethod
    def open(cls, path: Path | str, *, clock: Clock, pokazowa: bool = False) -> Store:
        return cls(path, clock=clock, pokazowa=pokazowa)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _kryteria_z_etykiety(zakres: str) -> Criteria | None:
    """`2024-01-01..2024-01-31` (etykieta `Scope` sprzed etapu IV) → `Criteria(od, do)`."""
    czesci = zakres.split("..")
    if len(czesci) != 2:
        return None
    try:
        return Criteria(od=date.fromisoformat(czesci[0]), do=date.fromisoformat(czesci[1]))
    except ValueError:
        return None
