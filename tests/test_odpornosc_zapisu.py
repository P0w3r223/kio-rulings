"""Co zostaje, gdy zapis odmawia: dysk pełny, katalog nie do założenia, cel zajęty.

Dwa zapisy mają w tym narzędziu różny status i ten plik trzyma je osobno.

**Baza jest jedynym miejscem, którego strata jest nieodwracalna** — surowe bajty wracają do niej
wyłącznie przez żądanie do cudzego serwisu. Awaria zapisu do bazy ma więc zostawić przebieg,
który da się dokończyć po zwolnieniu miejsca, i powiedzieć operatorowi zdaniem, co się stało.

**Eksport jest odtwarzalny z bazy i zero żądań kosztuje** — awaria jego zapisu ma tylko nie
zostawić pliku, który wygląda na kompletny. `exporter._zapis_atomowy` obiecuje dokładnie to
(„plik jest cały albo nie ma go wcale”) i połowa tego pliku mierzy tę obietnicę.

Pięć testów powstało 2026-09-18 jako znaleziska (`xfail(strict=True)`): surowy `sqlite3.Error`
zamiast zdania, przebieg `w_toku` bez drogi wznowienia po pełnym dysku, `mkdir` i eksport `md`
poza obsługą błędów, powtórny eksport `md` z cudzymi orzeczeniami w katalogu. Wszystkie
naprawione tego samego dnia (`store._Polaczenie`, `store.STATUSY_WZNAWIALNE`,
`pipeline._zamknij_przebieg`, `exporter._zapisz_md`) — testy mierzą zachowanie docelowe.
"""

from __future__ import annotations

import errno
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from kio_tool import exporter, pipeline
from kio_tool.criteria import Criteria
from kio_tool.errors import ExportError, KioError, StoreError
from kio_tool.exporter import Wpis
from kio_tool.store import Store
from tests.test_odpornosc_wspolne import (
    REKORDY,
    SLUGI,
    SerwisAwaryjny,
    _bez_klucza_ze_srodowiska,
    jedyny_przebieg,
    store,
    strona,
    uruchom,
)
from tests.wsparcie_sondy import ZegarTestowy

__all__ = ["_bez_klucza_ze_srodowiska", "store"]
"""Fixtures z modułu wspólnego — powód przy tej samej liście w `test_odpornosc_sieci.py`."""


def brak_miejsca() -> OSError:
    """Błąd, który zwraca system, gdy dysk jest pełny — nie wymyślony wyjątek, tylko ten numer.

    Fabryka, a nie stała modułu, i to jest różnica mierzalna: wyjątek podniesiony drugi raz
    niesie **oba** ślady stosu, a stała trzyma je wszystkie przy życiu do końca suity razem
    z ramkami, które je zbudowały — w tym z na wpół zapisanym skoroszytem `openpyxl`.
    """
    return OSError(errno.ENOSPC, "No space left on device")


PELNY_DYSK_SQLITE = "database or disk is full"
"""Komunikat SQLite przy `SQLITE_FULL` — tak brzmi awaria, o której mowa w tym pliku."""


def maly_przebieg(store: Store, ile: int = 3) -> str:
    """Kilka dokumentów w bazie, żeby było co eksportować — bez stu żądań na test."""
    wynik = uruchom(store, SerwisAwaryjny([strona(REKORDY[:ile], ma_wiecej=False, total=ile)]))
    assert wynik.nowych == ile
    return wynik.run_id


def ogony_tmp(katalog: Path) -> list[str]:
    """Pliki tymczasowe zapisu atomowego, które zostały po awarii (`.<nazwa>.tmp`)."""
    return sorted(p.name for p in katalog.iterdir() if p.name.endswith(".tmp"))


# --- zapis do bazy: dysk pełny w połowie przebiegu ----------------------------------------------


def test_dysk_pelny_w_polowie_dokumentu_cofa_cala_transakcje(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Niezmiennik ADR-0001 2.3 pod awarią dysku, nie pod `Ctrl+C`.

    `test_pipeline.py` mierzy przerwanie transakcji sygnałem operatora; tutaj transakcję
    przerywa SQLite, bo nie ma gdzie zapisać. Różnica jest w tym, że `Ctrl+C` pada między
    wywołaniami, a `SQLITE_FULL` w środku jednego z nich — a wynik ma być ten sam: dokument
    wchodzi cały albo nie wchodzi wcale.
    """
    prawdziwy = store.index_document
    licznik = {"n": 0}

    def pelny(*args: object, **kwargs: object) -> None:
        licznik["n"] += 1
        if licznik["n"] == 3:
            raise sqlite3.OperationalError(PELNY_DYSK_SQLITE)
        prawdziwy(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(store, "index_document", pelny)

    with pytest.raises(StoreError):
        uruchom(store, SerwisAwaryjny())

    assert store.count("documents") == store.count("raw_versions") == 2
    assert store.count("metadata") == store.count("fts") == 2
    assert store.count_run_documents(jedyny_przebieg(store)) == 2
    assert store.count("requests_log") == 4, (
        "ślad po żądaniu, które naprawdę poszło do cudzego serwisu, nie cofa się razem "
        "z transakcją — dysk zabrakło po stronie naszego zapisu, nie ich odpowiedzi"
    )


def test_dysk_pelny_mowi_operatorowi_zdaniem_a_nie_sladem_stosu(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`errors.KioError` deklaruje w docstringu: „komunikat jest przeznaczony dla użytkownika”.

    Dopóki awaria dysku przechodzi obok tej taksonomii, zdanie to obowiązuje wszystkie awarie
    poza tą jedną, po której operator najbardziej potrzebuje wiedzieć, co zrobić dalej.
    """
    prawdziwy = store.add_raw_version

    def pelny(*args: object, **kwargs: object) -> tuple[str, bool]:
        raise sqlite3.OperationalError(PELNY_DYSK_SQLITE)

    monkeypatch.setattr(store, "add_raw_version", pelny)
    assert prawdziwy is not None

    with pytest.raises(KioError) as zlapany:
        uruchom(store, SerwisAwaryjny())

    assert isinstance(zlapany.value, StoreError)


def test_przebieg_zatrzymany_pelnym_dyskiem_da_sie_dokonczyc_po_zwolnieniu_miejsca(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dysk zapełnia się w połowie i nie pozwala zapisać nawet zakończenia przebiegu.

    Operator kasuje pliki i uruchamia to samo polecenie — i to jest cały scenariusz. Do
    2026-09-18 dostawał nowy przebieg obok starego, a stary zostawał w `runy` jako pracujący;
    od tego dnia `w_toku` bez procesu jest osierocony i wznawialny (`store.STATUSY_WZNAWIALNE`),
    a `pipeline._zamknij_przebieg` nie zastępuje powodu przerwania awarią zapisu zakończenia.
    """
    pelno = {"teraz": False}
    prawdziwy_raw = store.add_raw_version
    prawdziwy_finish = store.finish_run
    prawdziwy_upsert = store.upsert_document

    def gdy_pelno() -> None:
        if pelno["teraz"]:
            raise sqlite3.OperationalError(PELNY_DYSK_SQLITE)

    def raw(*args: object, **kwargs: object) -> tuple[str, bool]:
        gdy_pelno()
        return prawdziwy_raw(*args, **kwargs)  # type: ignore[arg-type]

    def finish(*args: object, **kwargs: object) -> None:
        gdy_pelno()
        prawdziwy_finish(*args, **kwargs)  # type: ignore[arg-type]

    licznik = {"n": 0}

    def upsert(*args: object, **kwargs: object) -> None:
        licznik["n"] += 1
        if licznik["n"] == 3:
            pelno["teraz"] = True
        prawdziwy_upsert(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(store, "add_raw_version", raw)
    monkeypatch.setattr(store, "finish_run", finish)
    monkeypatch.setattr(store, "upsert_document", upsert)

    with pytest.raises(StoreError):
        uruchom(store, SerwisAwaryjny())
    pelno["teraz"] = False

    przebieg = store.get_run(jedyny_przebieg(store))
    assert przebieg.status == "w_toku", (
        f"status {przebieg.status!r} — zakończenia nie dało się zapisać, więc przebieg zostaje "
        "osierocony, nie przerwany"
    )
    assert pipeline.do_wznowienia(store, None)[0] == przebieg.run_id

    wynik = uruchom(store, SerwisAwaryjny())

    assert (wynik.status, store.count_runs()) == ("zakonczony", 1), "to samo polecenie dokończa"
    assert store.count("documents") == len(SLUGI)


def test_awaria_zapisu_zakonczenia_bez_innego_bledu_wychodzi_zdaniem(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Przebieg skończył pracę, a nie da się zapisać `zakonczony`: to jedyny błąd i ma wyjść.

    `pipeline._zamknij_przebieg` przemilcza awarię zamknięcia wyłącznie wtedy, gdy inny wyjątek
    już leci — inaczej „zakonczony" na ekranie mówiłoby nieprawdę o wierszu w bazie. Mutacja
    zamieniająca ten warunek na „zawsze przemilcz" przeszła 2026-09-18 cicho przez suitę; ten
    test ją łapie.
    """

    def finish(*args: object, **kwargs: object) -> None:
        raise sqlite3.OperationalError(PELNY_DYSK_SQLITE)

    monkeypatch.setattr(store, "finish_run", finish)

    with pytest.raises(StoreError, match="zakończenia"):
        uruchom(store, SerwisAwaryjny())

    przebieg = store.get_run(jedyny_przebieg(store))
    assert przebieg.status == "w_toku", "zostaje osierocony — wznowi go to samo polecenie"
    assert store.count("documents") == len(SLUGI), "dokumenty sprzed awarii zamknięcia zostają"


def test_nieudany_rollback_nie_zastepuje_wyjatku_w_locie(store: Store) -> None:
    """SQLite sam cofa transakcję przy `SQLITE_FULL`; jawny `ROLLBACK` mówi wtedy „no transaction
    is active" i do 2026-09-18 zastępował wyjątek w locie — `Ctrl+C` stawał się `StoreError`,
    przebieg dostawał `blad` zamiast `przerwany` i tracił punkt kontrolny (przegląd kodu).

    Transakcja jest tu cofnięta ręcznie, żeby odtworzyć ten stan bez pełnego dysku: to, co ma
    wyjść z `transakcja()`, to wyjątek operatora, nie wyjątek sprzątania.
    """
    with pytest.raises(KeyboardInterrupt), store.transakcja():
        store._conn.execute("ROLLBACK")
        raise KeyboardInterrupt

    assert not store._conn.in_transaction


def test_nieudana_migracja_nie_zostawia_zajetego_pliku_bazy(tmp_path: Path) -> None:
    """`with Store.open(...)` nie wchodzi w `__exit__`, gdy `__init__` rzuci — do 2026-09-18
    połączenie zostawało otwarte i plik bazy był na Windowsie zajęty (`WinError 32`) do końca
    procesu (przegląd kodu). Baza w schemacie z przyszłości jest najprostszą nieudaną migracją.
    """
    baza = tmp_path / "z_przyszlosci.sqlite"
    polaczenie = sqlite3.connect(baza)
    polaczenie.execute("PRAGMA user_version = 99")
    # `with sqlite3.connect(...)` zatwierdza, ale nie zamyka — plik ma być wolny od strony testu.
    polaczenie.close()

    with pytest.raises(StoreError, match="wersji 99"):
        Store.open(baza, clock=ZegarTestowy())

    baza.unlink()
    assert not baza.exists(), "plik bazy został zajęty przez porzucone połączenie"


@pytest.mark.parametrize("cudzy_plik", ["notatki.txt", "index.md", "INDEX.md"])
def test_eksport_md_nie_nadpisuje_cudzego_katalogu_pod_ta_sama_nazwa(
    store: Store, tmp_path: Path, cudzy_plik: str
) -> None:
    """Katalog `<out>_md` istnieje, ma pliki i nie ma znacznika kio-tool — to nie jest nasz wynik.

    Sprzątanie poprzedniego eksportu (test wyżej) kasuje katalog w całości, więc granica musi
    być ostra: własny wynik poznaje się po `.kio-tool-eksport`, a wszystko inne zostaje nietknięte
    i eksport odmawia zdaniem. `index.md` i `INDEX.md` są tu osobno, bo NTFS składa wielkość
    liter: znacznik po `INDEX.md` uznawał cudzy `index.md` (mkdocs, Jekyll) za własny i katalog
    szedł pod `rmtree` (przegląd kodu 2026-09-18, zmierzone na tej maszynie).
    """
    run_id = maly_przebieg(store)
    cudzy = tmp_path / f"e{exporter.SUFIKS_KATALOGU_MD}"
    cudzy.mkdir()
    (cudzy / cudzy_plik).write_text("cudze, nie do skasowania", encoding="utf-8")

    with pytest.raises(ExportError, match="nie wygląda na wynik"):
        pipeline.eksportuj(
            store, run_ids=(run_id,), formaty=("md",), out=tmp_path / "e", zegar=ZegarTestowy()
        )

    assert (cudzy / cudzy_plik).read_text(encoding="utf-8") == "cudze, nie do skasowania"
    assert ogony_tmp(tmp_path) == [], "katalog tymczasowy eksportu nie zostaje po odmowie"


def test_awaria_zapisu_do_bazy_nie_gubi_tego_co_juz_bylo(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Druga połowa obietnicy o bazie: awaria nie ma prawa **zabrać** dokumentów sprzed niej.

    Mierzone po zwolnieniu miejsca i na żywym korpusie: dokumenty sprzed awarii dają się
    przeliczyć i znaleźć, więc nie są uszkodzonymi bajtami z poprawnym licznikiem.
    """
    maly_przebieg(store, ile=3)
    przed = store.count("documents")

    def pelny(*args: object, **kwargs: object) -> tuple[str, bool]:
        raise sqlite3.OperationalError(PELNY_DYSK_SQLITE)

    monkeypatch.setattr(store, "add_raw_version", pelny)
    with pytest.raises(StoreError):
        uruchom(store, SerwisAwaryjny())
    monkeypatch.undo()

    assert store.count("documents") == przed == 3
    assert pipeline.przelicz(store, wszystko=True).bledow == 0
    assert pipeline.szukaj(store, Criteria(fraza="tresc wymyslona"), limit=10).trafien == 3


# --- zapis eksportu: cel zajęty, dysk pełny w połowie pliku -------------------------------------


def test_eksport_do_zajetej_sciezki_odmawia_zdaniem_i_nie_rusza_korpusu(
    store: Store, tmp_path: Path
) -> None:
    """W miejscu pliku wynikowego stoi katalog — zapis odmawia, korpus zostaje nietknięty.

    Test pilnuje trzech rzeczy naraz, bo to trzy różne sposoby, na jakie nieudany eksport
    mógłby zaszkodzić: wyjątek jest zdaniem z taksonomii (a nie `PermissionError` z systemu),
    przebieg zostaje `zakonczony` (eksport nie jest częścią przebiegu), a ten sam eksport
    zlecony pod dobrą ścieżkę przechodzi — czyli nic się nie zepsuło po drodze.
    """
    run_id = maly_przebieg(store)
    (tmp_path / "e.csv").mkdir()

    with pytest.raises(ExportError) as zlapany:
        pipeline.eksportuj(
            store, run_ids=(run_id,), formaty=("csv",), out=tmp_path / "e", zegar=ZegarTestowy()
        )

    assert "e.csv" in str(zlapany.value), "komunikat ma nazwać ścieżkę, której nie da się zapisać"
    assert store.get_run(run_id).status == "zakonczony"
    assert store.count("documents") == 3
    assert ogony_tmp(tmp_path) == [], "po nieudanym zapisie nie zostaje plik tymczasowy"

    drugi = tmp_path / "gdzie_indziej"
    wynik = pipeline.eksportuj(
        store, run_ids=(run_id,), formaty=("csv",), out=drugi / "e", zegar=ZegarTestowy()
    )
    assert wynik.dokumentow == 3 and (drugi / "e.csv").is_file()


FORMATY_POD_AWARIE = [
    pytest.param("csv", id="csv"),
    pytest.param("jsonl", id="jsonl"),
    # `md` był 2026-09-18 znaleziskiem: `_zapisz_md` czytał źródło poza obsługą błędów i awaria
    # wejścia-wyjścia wychodziła surowym `OSError`; od tego dnia katalog powstaje jako tymczasowy
    # i jest podmieniany w całości, jak plik w `_zapis_atomowy`.
    pytest.param(
        "md",
        id="md",
    ),
]


@pytest.mark.parametrize("format_", FORMATY_POD_AWARIE)
def test_dysk_pelny_w_polowie_eksportu_nie_zostawia_pliku_wygladajacego_na_kompletny(
    tmp_path: Path, format_: str
) -> None:
    """Obietnica `_zapis_atomowy`: „plik jest cały albo nie ma go wcale”.

    Awaria pada **w trakcie** strumienia wpisów, czyli po otwarciu pliku tymczasowego
    i przed `os.replace` — dokładnie tam, gdzie plik częściowy mógłby przetrwać. Plik
    częściowy jest groźniejszy od braku pliku: otwiera się bez słowa i wygląda jak wynik
    zapytania, które objęło mniej, niż objęło.

    Formatów jest tu trzy, nie cztery, i brak `xlsx` jest zapisanym defektem produkcji, nie
    luką w pokryciu: `_zapisz_xlsx` porzuca `Workbook(write_only=True)` bez `close()`, gdy
    zapis się nie powiedzie, więc przerwanie **w połowie strumienia wierszy** zostawia
    niedokończony generator `openpyxl` i wypisuje `Exception ignored in …` przy zbieraniu
    śmieci. Atomowość skoroszytu mierzy więc test niżej, w drugim możliwym miejscu awarii —
    przy podmianie pliku docelowego.
    """
    from kio_tool.parser.details import Szczegoly

    def zrodlo() -> Iterator[Wpis]:
        yield Wpis(
            doc_id="atlas:kio-1-24",
            source="atlas",
            source_ref="kio-1-24",
            sha256="a" * 64,
            fetched_at="2026-09-18T12:00:00Z",
            szczegoly=Szczegoly(
                sygnatura_glowna="(sygnatura wymyslona)",
                sygnatury=("(sygnatura wymyslona)",),
                data_wydania="2024-01-15",
                data_rozprawy=None,
                rodzaj="wyrok",
                rozstrzygniecie="oddalono",
                rozstrzygniecie_surowe=None,
                przewodniczacy=None,
                odwolujacy=None,
                zamawiajacy=None,
                przepisy=(),
                koszty=None,
                url_zrodla=None,
                tresc="tresc wymyslona",
            ),
            rekord={"slug": "kio-1-24"},
            atrybucja="Źródło: atrapa",
        )
        raise brak_miejsca()

    cel = tmp_path / "wynik"
    (sciezka,) = exporter.sciezki_wyjsciowe(cel, (format_,)).values()

    with pytest.raises(ExportError):
        exporter.eksportuj(cel, zrodlo, formaty=(format_,), metadane=(("kryteria", "test"),))

    assert ogony_tmp(tmp_path) == [], "plik tymczasowy został po awarii zapisu"
    if format_ == "md":
        # Katalog powstaje obok jako tymczasowy i jest podmieniany w całości, więc po awarii
        # docelowego nie ma wcale — tak samo jak pliku w pozostałych formatach.
        assert not sciezka.exists(), "katalog `_md` po awarii w połowie eksportu udawałby wynik"
    else:
        assert not sciezka.exists(), f"po awarii został plik {sciezka.name}"


def test_skoroszyt_nie_podmienia_celu_gdy_podmiana_odmawia(store: Store, tmp_path: Path) -> None:
    """Atomowość skoroszytu w drugim możliwym miejscu awarii: `os.replace` po udanym zapisie.

    Plik tymczasowy jest w tym momencie **kompletnym** skoroszytem, więc to jest jedyny stan,
    w którym „prawie się udało" mogłoby zostawić `.xlsx` obok celu i wyglądać na wynik. Test
    pilnuje, że po odmowie nie ma ani pliku docelowego, ani ogona `.tmp`.
    """
    run_id = maly_przebieg(store)
    (tmp_path / "e.xlsx").mkdir()

    with pytest.raises(ExportError, match="e.xlsx"):
        pipeline.eksportuj(
            store, run_ids=(run_id,), formaty=("xlsx",), out=tmp_path / "e", zegar=ZegarTestowy()
        )

    assert (tmp_path / "e.xlsx").is_dir(), "cel nie został podmieniony"
    assert ogony_tmp(tmp_path) == [], "kompletny skoroszyt tymczasowy został po nieudanej podmianie"


def test_awaria_drugiego_formatu_zostawia_pierwszy_zapisany_na_dysku(
    store: Store, tmp_path: Path
) -> None:
    """Zapis stanu na dziś: formaty idą po kolei i nie ma między nimi transakcji.

    Gdy drugi format odmawia, pierwszy **zostaje** na dysku, a wywołanie kończy się wyjątkiem
    — więc `WynikEksportu` nie wraca i operator nie usłyszy, że jeden plik jednak powstał.
    Test jest tu bez `xfail`, bo to zachowanie da się obronić (plik jest kompletny i poprawny),
    ale ma być **zapisane**: cicha zmiana w którąkolwiek stronę jest tu zmianą tego, co
    operator zastaje w katalogu po błędzie.
    """
    run_id = maly_przebieg(store)
    (tmp_path / "e.jsonl").mkdir()

    with pytest.raises(ExportError):
        pipeline.eksportuj(
            store,
            run_ids=(run_id,),
            formaty=("csv", "jsonl"),
            out=tmp_path / "e",
            zegar=ZegarTestowy(),
        )

    assert (tmp_path / "e.csv").is_file(), "format zapisany przed awarią zostaje kompletny"
    wiersze = (tmp_path / "e.csv").read_text(encoding="utf-8-sig").splitlines()
    assert len(wiersze) - 1 == 3, "zostaje plik kompletny, nie ucięty"


def test_eksport_gdy_katalogu_wyjscia_nie_da_sie_zalozyc_mowi_zdaniem(
    store: Store, tmp_path: Path
) -> None:
    """`--out` wskazujące pod ścieżkę, w której stoi plik zamiast katalogu.

    To nie jest przypadek wyszukany: `--out` jest ścieżką wpisywaną ręcznie, a literówka
    w przedostatnim członie daje dokładnie ten stan.
    """
    run_id = maly_przebieg(store)
    (tmp_path / "zajete").write_text("to jest plik, nie katalog", encoding="utf-8")

    with pytest.raises(ExportError):
        pipeline.eksportuj(
            store,
            run_ids=(run_id,),
            formaty=("csv",),
            out=tmp_path / "zajete" / "e",
            zegar=ZegarTestowy(),
        )


# --- eksport `md`: katalog, którego nikt nie sprząta -------------------------------------------


def test_powtorny_eksport_md_nie_zostawia_w_katalogu_cudzych_orzeczen(
    store: Store, tmp_path: Path
) -> None:
    """Pięć orzeczeń, potem jedno — pod tym samym `--out`. W katalogu ma zostać jedno.

    `--out` jest jedyną drogą do powtórzenia nazwy katalogu (nazwa domyślna niesie znacznik
    czasu), a jest to droga udokumentowana w README i używana wszędzie tam, gdzie wynik ma
    trafiać w ustalone miejsce.
    """
    piec = maly_przebieg(store, ile=5)
    pipeline.eksportuj(
        store, run_ids=(piec,), formaty=("md",), out=tmp_path / "e", zegar=ZegarTestowy()
    )
    katalog = tmp_path / f"e{exporter.SUFIKS_KATALOGU_MD}"
    assert len(list(katalog.glob("*.md"))) == 6, "pięć orzeczeń i INDEX.md po pierwszym eksporcie"

    wynik = pipeline.eksportuj(
        store,
        kryteria=Criteria(fraza=f"tresc wymyslona {SLUGI[0]}"),
        formaty=("md",),
        out=tmp_path / "e",
        zegar=ZegarTestowy(),
    )

    assert wynik.dokumentow == 1
    orzeczenia = sorted(p.name for p in katalog.glob("*.md") if p.name != exporter.PLIK_INDEKSU)
    indeks = (katalog / exporter.PLIK_INDEKSU).read_text(encoding="utf-8")
    niewymienione = [nazwa for nazwa in orzeczenia if f"({nazwa})" not in indeks]
    assert niewymienione == [], (
        f"w katalogu eksportu leżą orzeczenia, o których `INDEX.md` milczy: {niewymienione}"
    )


def test_eksport_md_pod_swiezy_katalog_wymienia_w_indeksie_kazdy_plik(
    store: Store, tmp_path: Path
) -> None:
    """Druga połowa znaleziska wyżej: pod świeżą ścieżką niezgodności nie ma.

    Bez tego testu `xfail` mógłby wskazywać na zepsuty `INDEX.md` w ogóle, a wskazuje na
    **niesprzątany katalog** — różnica rozstrzyga o tym, gdzie stoi poprawka.
    """
    run_id = maly_przebieg(store, ile=4)

    pipeline.eksportuj(
        store, run_ids=(run_id,), formaty=("md",), out=tmp_path / "swiezy", zegar=ZegarTestowy()
    )

    katalog = tmp_path / f"swiezy{exporter.SUFIKS_KATALOGU_MD}"
    indeks = (katalog / exporter.PLIK_INDEKSU).read_text(encoding="utf-8")
    orzeczenia = [p.name for p in katalog.glob("*.md") if p.name != exporter.PLIK_INDEKSU]
    assert len(orzeczenia) == 4
    assert all(f"({nazwa})" in indeks for nazwa in orzeczenia)
