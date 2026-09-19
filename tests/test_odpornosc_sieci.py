"""Co zostaje po zaniku sieci i po odmowie serwisu — i czy przebieg da się dokończyć.

README obiecuje jedno zdanie: „przebieg przerwany przez Ctrl+C, brak zgody, błąd sieci albo
odmowę serwisu zostaje w bazie ze statusem `przerwany`, zapisaną ostatnią stroną listy i powodem.
Wznawia go `wznow` albo to samo polecenie `pobierz`”. Ten plik mierzy tę obietnicę **rodzaj
awarii po rodzaju**, bo obietnica jest jedna, a wyjątków, którymi może się skończyć jedno
żądanie, jest dziewięć (`errors.py`) i tylko trzy z nich są `ResumableError`.

`test_pipeline.py` mierzy już dwie awarie: `httpx.ConnectError` na dokumencie i 429
z `Retry-After`. Tu idą pozostałe — timeout odczytu, zerwanie w połowie odpowiedzi, 5xx, 404,
200 o niezgodnym kształcie, ucięty JSON — oraz to, czego tamten plik nie dotyka wcale: zanik
sieci **na stronie listy**, czyli w miejscu, w którym punktu kontrolnego jeszcze nie ma.

Dwa testy powstały 2026-09-18 jako znaleziska (`xfail(strict=True)`): 404 na jednym dokumencie
kończył cały przebieg statusem `blad`, a JSON urwany w połowie był klasyfikowany jak zmiana API
u dostawcy. Oba naprawione tego samego dnia (`pipeline._przebieg`, `ksztalt.wyglada_na_urwana`)
i testy mierzą od tej pory zachowanie docelowe.
"""

from __future__ import annotations

from functools import partial

import httpx
import pytest

from kio_tool import pipeline
from kio_tool.errors import (
    ConfigError,
    ResumableError,
    ServerError,
    SourceContractBroken,
    TransportError,
)
from kio_tool.httpclient import build_http_client
from kio_tool.store import Store
from tests.test_odpornosc_wspolne import (
    KONTRAKT,
    LICZNIK,
    LISTA,
    REKORDY,
    SLUGI,
    SerwisAwaryjny,
    _bez_klucza_ze_srodowiska,
    jedyny_przebieg,
    statusy_zadan,
    store,
    strona,
    uruchom,
)
from tests.wsparcie_sondy import ZegarTestowy

__all__ = ["_bez_klucza_ze_srodowiska", "store"]
"""Fixtures z modułu wspólnego wymienione wprost, bo pytest szuka ich **po nazwie w tym
module**, a nie w module, z którego pochodzą. Bez tej listy `ruff` widziałby dwa nieużywane
importy i skasowanie ich zabrałoby testom bazę i czyszczenie zmiennej z kluczem."""


# --- zanik sieci na dokumencie ---------------------------------------------------------------


AWARIE_PRZEJSCIOWE = [
    pytest.param(lambda _: httpx.ConnectError("siec znikla (wymyslone)"), id="connect-error"),
    pytest.param(lambda _: httpx.ReadTimeout("serwis milczy (wymyslone)"), id="read-timeout"),
    pytest.param(
        lambda _: httpx.ConnectTimeout("nie zestawiono (wymyslone)"), id="connect-timeout"
    ),
    pytest.param(
        lambda _: httpx.RemoteProtocolError("peer closed connection without sending complete"),
        id="zerwane-w-polowie-odpowiedzi",
    ),
    pytest.param(lambda _: httpx.PoolTimeout("brak wolnego polaczenia (wymyslone)"), id="pool"),
    pytest.param(lambda _: httpx.Response(503, content=b"{}"), id="503"),
    pytest.param(lambda _: httpx.Response(502, content=b"nginx"), id="502"),
    pytest.param(lambda _: httpx.Response(500, content=b"{}"), id="500"),
]
"""Awarie, po których README obiecuje wznowienie tym samym poleceniem.

Każda z nich zdarza się przy zaniku sieci albo przy serwisie, który na chwilę padł — żadna
nie jest trwała i żadna nie wymaga poprawki w kodzie, żeby przebieg dało się dokończyć.
"""


@pytest.mark.parametrize("reakcja", AWARIE_PRZEJSCIOWE)
def test_awaria_przejsciowa_zostawia_przebieg_przerwany_i_wznawialny(
    store: Store, reakcja: object
) -> None:
    """Jeden pomiar na rodzaj awarii: status `przerwany`, powód zapisany, `wznow` go widzi.

    To jest zdanie README w postaci mechanicznej. Bez parametryzacji byłoby ośmioma kopiami
    tego samego testu, a przy dziewięciu klasach wyjątków kopia jest miejscem, w którym jedna
    z nich cicho wypada z pokrycia.
    """
    serwis = SerwisAwaryjny(na_dokumencie=3, reakcja=reakcja)  # type: ignore[arg-type]

    with pytest.raises(ResumableError):
        uruchom(store, serwis)

    przebieg = store.get_run(jedyny_przebieg(store))
    assert przebieg.status == "przerwany", (
        f"awaria przejściowa dała status {przebieg.status!r} — przebieg, którego nie da się "
        "wznowić, bo `do_wznowienia` przyjmuje wyłącznie `przerwany`"
    )
    assert przebieg.powod, "przerwany przebieg bez powodu nie mówi operatorowi, co się stało"
    assert przebieg.finished_at is not None, "przebieg bez `finished_at` udaje wciąż pracujący"
    assert przebieg.ostatnia_strona == 1, "punkt kontrolny ze strony ostatniego zapisu"
    assert store.count("documents") == 2, "dwa dokumenty sprzed awarii zostają"

    wybrany, kryteria = pipeline.do_wznowienia(store, None)
    assert wybrany == przebieg.run_id and not kryteria.is_empty()


@pytest.mark.parametrize("reakcja", AWARIE_PRZEJSCIOWE)
def test_po_awarii_przejsciowej_wznowienie_konczy_przebieg_bez_duplikatow(
    store: Store, reakcja: object
) -> None:
    """Druga połowa obietnicy: nie „da się uruchomić”, tylko **da się dokończyć**.

    Trzy liczby razem znaczą „bez duplikatów i bez utraty”: korpus ma dokładnie tylu
    dokumentów, ilu było kandydatów; wersji surowych tyle samo (żaden dokument nie dostał
    drugiej); przebieg jest jeden — wznowienie nie założyło drugiego obok.
    """
    with pytest.raises(ResumableError):
        uruchom(store, SerwisAwaryjny(na_dokumencie=3, reakcja=reakcja))  # type: ignore[arg-type]
    przerwany = jedyny_przebieg(store)
    serwis = SerwisAwaryjny()

    wynik = uruchom(store, serwis)

    assert wynik.run_id == przerwany, "wznowienie wróciło do tego samego przebiegu"
    assert (wynik.nowych, wynik.pominietych) == (98, 2)
    assert serwis.dokumentow == 98, "dwa dokumenty sprzed awarii nie kosztowały żądania"
    assert store.count("documents") == store.count("raw_versions") == len(SLUGI)
    assert store.count("runs") == 1
    assert store.get_run(wynik.run_id).status == "zakonczony"


def test_zerwane_polaczenie_zostawia_w_dzienniku_wiersz_o_zadaniu_bez_odpowiedzi(
    store: Store,
) -> None:
    """„Cisza jest usterką” na granicy procesu: żądanie poszło, odpowiedź nie wróciła.

    Wiersz ze statusem `NULL` jest jedynym śladem po koszcie, który cudzy serwer **już**
    poniósł. Gdyby dziennik zapisywał się dopiero po udanej odpowiedzi, rachunek przebiegu
    milczałby akurat o tych żądaniach, które poszły na darmo.
    """
    serwis = SerwisAwaryjny(
        na_dokumencie=3,
        reakcja=lambda _: httpx.ReadTimeout("serwis milczy (wymyslone)"),
    )

    with pytest.raises(TransportError):
        uruchom(store, serwis)

    # Awaria trwała: trzy próby tego samego dokumentu (`ponowienia.proby`), każda z wierszem.
    assert statusy_zadan(store) == [200, 200, 200, None, None, None]
    uwaga = store._conn.execute(
        "SELECT ksztalt FROM requests_log ORDER BY rowid DESC LIMIT 1"
    ).fetchone()[0]
    assert uwaga == "—", "żądanie bez odpowiedzi nie ma kształtu do oceny i tak ma być zapisane"


# --- zanik sieci na stronie listy ------------------------------------------------------------


def test_zanik_sieci_na_pierwszej_stronie_listy_zostawia_przebieg_bez_dokumentow(
    store: Store,
) -> None:
    """Awaria **przed** pierwszym dokumentem: punktu kontrolnego jeszcze nie ma.

    Miejsce nietknięte przez `test_pipeline.py`, a to właśnie tu przebieg jest najbardziej
    goły: wiersz w `runs` już istnieje (powstaje przed pierwszym żądaniem), a `ostatnia_strona`
    jest pusta. Wznowienie ma wtedy zacząć od strony pierwszej, a nie wywrócić się na `None`.
    """
    serwis = SerwisAwaryjny(na_stronie=1)

    with pytest.raises(TransportError):
        uruchom(store, serwis)

    przebieg = store.get_run(jedyny_przebieg(store))
    assert (przebieg.status, przebieg.ostatnia_strona) == ("przerwany", None)
    assert store.count("documents") == 0 and store.count("run_documents") == 0
    assert statusy_zadan(store) == [None, None, None], (
        "każda z trzech prób strony nie doszła i każda ma o tym wiersz"
    )

    dokonczony = uruchom(store, SerwisAwaryjny())

    assert dokonczony.run_id == przebieg.run_id
    assert (dokonczony.nowych, dokonczony.pominietych) == (len(SLUGI), 0)
    assert store.count("runs") == 1


def test_zanik_sieci_na_dalszej_stronie_listy_wznawia_od_punktu_kontrolnego(
    store: Store,
) -> None:
    """Punkt kontrolny jest stroną, nie dokumentem — więc wznowienie przepytuje ją od nowa.

    Awaria pada na stronie **trzeciej**, a nie drugiej, i to jest warunek, żeby test cokolwiek
    mierzył: przy przerwaniu na stronie drugiej punkt kontrolny wynosi 1, czyli dokładnie tyle,
    ile wyniósłby przy zepsutym zapisie punktu kontrolnego. Zmierzone mutacją 2026-09-18:
    `store.checkpoint(run_id, 1)` wpisane w `pipeline._przebieg` przeszło przez pierwszą wersję
    tego testu bez jednego czerwonego wyniku.

    Wznowienie ma więc wysłać listę **od strony 2** — tej, z której pochodził ostatni zapisany
    kandydat — a nie od pierwszej. Kandydaci z tej strony już zapisani wypadają na
    `has_document`, więc nieaktualny punkt kontrolny kosztuje najwyżej jedną stronę listy,
    nigdy duplikat (ADR-0001 2.3).
    """
    strony = [
        strona(REKORDY[:5], ma_wiecej=True, total=15),
        strona(REKORDY[5:10], ma_wiecej=True, total=15),
        strona(REKORDY[10:15], ma_wiecej=False, total=15),
    ]
    with pytest.raises(TransportError):
        uruchom(store, SerwisAwaryjny(strony, na_stronie=3))
    przerwany = store.get_run(jedyny_przebieg(store))
    assert (przerwany.status, przerwany.ostatnia_strona) == ("przerwany", 2)
    assert store.count("documents") == 10
    serwis = SerwisAwaryjny(strony)

    wynik = uruchom(store, serwis)

    assert serwis.strony_zadane == ["2", "3"], (
        f"wznowienie poszło po strony {serwis.strony_zadane} — punkt kontrolny wskazywał stronę "
        "2, a lista od pierwszej to żądanie do cudzego serwisu za dane, które już mamy"
    )
    assert (wynik.nowych, wynik.pominietych) == (5, 5)
    assert serwis.dokumentow == 5, "pięć kandydatów ze strony 2 nie kosztuje żądań po dokument"
    assert store.count("documents") == store.count("raw_versions") == 15


def test_kolejne_zaniki_sieci_nie_mnoza_przebiegow_ani_wersji(store: Store) -> None:
    """Sieć znikająca trzy razy pod rząd — bo tak wygląda łącze, które naprawdę pada.

    Pytanie jest o kumulację: po trzech przerwaniach i jednym dokończeniu w bazie ma stać
    jeden przebieg, sto dokumentów i sto wersji surowych. Każdy inny wynik znaczy, że koszt
    przerwania rośnie z liczbą przerwań — a to jest ta klasa usterki, którą widać dopiero
    przy czwartym.
    """
    for na_dokumencie in (3, 20, 60):
        with pytest.raises(TransportError):
            uruchom(store, SerwisAwaryjny(na_dokumencie=na_dokumencie))

    wynik = uruchom(store, SerwisAwaryjny())

    assert store.count("runs") == 1 and wynik.status == "zakonczony"
    assert store.count("documents") == store.count("raw_versions") == len(SLUGI)
    assert store.count_run_documents(wynik.run_id) == len(SLUGI)
    assert store.count_run_documents(wynik.run_id, nowe=True) == len(SLUGI)
    assert store.count_indexed() == len(SLUGI), "metadane i indeks przeżyły trzy przerwania"


# --- 200 o niezgodnym kształcie ---------------------------------------------------------------


def test_200_o_niezgodnym_ksztalcie_nie_wchodzi_do_korpusu(store: Store) -> None:
    """Reguła 17: 200 bez struktury z kontraktu jest awarią, nie dokumentem.

    Najcichsza możliwa usterka w tym miejscu to zapisanie takiej odpowiedzi jako wersji
    surowej — korpus wyglądałby wtedy na kompletny i niósłby stronę bot-checka pod sygnaturą
    orzeczenia. Test mierzy więc dwie rzeczy: przebieg staje, a bajty nie wchodzą do bazy.
    """
    smiec = b'{"komunikat": "chwilowo niedostepne"}'
    serwis = SerwisAwaryjny(na_dokumencie=3, reakcja=lambda _: httpx.Response(200, content=smiec))

    with pytest.raises(SourceContractBroken, match="kształt"):
        uruchom(store, serwis)

    assert store.count("documents") == store.count("raw_versions") == 2
    zapisane = [bytes(w[0]) for w in store._conn.execute("SELECT content_bytes FROM raw_versions")]
    assert smiec not in zapisane, "odpowiedź o niezgodnym kształcie weszła do korpusu"
    assert statusy_zadan(store) == [200, 200, 200, 200]
    ksztalty = [
        w[0] for w in store._conn.execute("SELECT ksztalt FROM requests_log ORDER BY rowid")
    ]
    assert ksztalty[-1] == "NIEZGODNY", "dziennik ma nazwać odpowiedź, która przyszła nie ta"


def test_pusta_lista_w_zakresie_dat_nie_jest_zlamanym_kontraktem(store: Store) -> None:
    """Granica reguły 17 od drugiej strony: zakres bez orzeczeń jest wynikiem, nie awarią.

    Bez tego testu „każdy 200 o nieoczekiwanej treści jest awarią” wyglądałoby na pełną
    prawdę, a wtedy pierwszy pusty miesiąc kończyłby się `SourceContractBroken` zamiast
    zerem dokumentów — czyli narzędzie zgłaszałoby awarię źródła przy poprawnej odpowiedzi.
    """
    serwis = SerwisAwaryjny([strona([], ma_wiecej=False, total=0)])

    wynik = uruchom(store, serwis)

    assert (wynik.status, wynik.kandydatow, wynik.nowych) == ("zakonczony", 0, 0)
    assert store.count("documents") == 0


# --- znaleziska testera 2026-09-18, naprawione tego samego dnia --------------------------------


def test_404_na_jednym_dokumencie_nie_zabija_calego_przebiegu(store: Store) -> None:
    """Pośrednik wycofał jeden slug między listą a pobraniem — pozostałe mają dojechać.

    `errors.NotFoundError` mówi wprost, że 404 jest „**spodziewanym** wynikiem, nie awarią”.
    Do 2026-09-18 jeden brakujący dokument kończył przebieg statusem `blad`, którego `wznow` nie
    przyjmował — a wznowienie i tak trafiłoby w ten sam 404 na tej samej stronie listy. Teraz
    dokument jest policzony (`brakujacych`), wiersz w dzienniku żądań zostaje, przebieg idzie
    dalej i kończy się jako `zakonczony`.
    """
    serwis = SerwisAwaryjny(
        na_dokumencie=3, reakcja=lambda _: httpx.Response(404, content=b'{"detail": "not found"}')
    )

    wynik = uruchom(store, serwis)

    assert (wynik.status, wynik.brakujacych, wynik.nowych) == ("zakonczony", 1, len(SLUGI) - 1)
    assert store.count("documents") == store.count("raw_versions") == len(SLUGI) - 1
    assert 404 in statusy_zadan(store), "żądanie po brakujący dokument poszło i ma wiersz"


def test_uciety_json_jest_awaria_przejsciowa_a_nie_zlamanym_kontraktem(store: Store) -> None:
    """Sieć padła w połowie odpowiedzi, a pośrednik zdążył zamknąć strumień „poprawnie”.

    Różnica wobec `test_200_o_niezgodnym_ksztalcie_nie_wchodzi_do_korpusu` jest cała: tam
    przyszła **inna** struktura (dostawca zmienił API — ponowienie nic nie da), tu przyszła
    **ta sama, urwana** (ponowienie da pełną odpowiedź). Do 2026-09-18 obie kończyły się
    `SourceContractBroken` (kod 1, status `blad`); od tego dnia `ksztalt.wyglada_na_urwana`
    odróżnia JSON urwany od JSON-u innego, a adapter rzuca `TransportError` jak przy
    `RemoteProtocolError` — przebieg jest wznawialny.
    """
    pelny = b'{"slug": "kio-1-24", "primary_signature": "(wymyslona)", "content": "tresc"}'
    serwis = SerwisAwaryjny(
        na_dokumencie=3, reakcja=lambda _: httpx.Response(200, content=pelny[: len(pelny) // 2])
    )

    with pytest.raises(TransportError, match="urwana"):
        uruchom(store, serwis)

    przebieg = store.get_run(jedyny_przebieg(store))
    assert przebieg.status == "przerwany", (
        f"status {przebieg.status!r}: ucięte ciało odpowiedzi ma zostawić przebieg wznawialny"
    )
    assert store.count("documents") == 2, "urwane bajty nie weszły do korpusu"
    pipeline.do_wznowienia(store, przebieg.run_id)


def test_uciety_json_na_liscie_zatrzymuje_przebieg_przed_pierwszym_dokumentem(
    store: Store,
) -> None:
    """Ten sam ucięty JSON na stronie listy kończy się tak samo jak na dokumencie.

    Lista i dokument idą tą samą drogą (`_zadanie` w adapterze), więc test pilnuje, żeby
    klasyfikacja nie rozjechała się między nimi: oba wznawialne, zero dokumentów w korpusie.
    """
    serwis = SerwisAwaryjny(na_stronie=1, reakcja=lambda _: httpx.Response(200, content=b'{"da'))

    with pytest.raises(TransportError, match="urwana"):
        uruchom(store, serwis)

    przebieg = store.get_run(jedyny_przebieg(store))
    assert przebieg.status == "przerwany"
    assert store.count("documents") == 0
    pipeline.do_wznowienia(store, przebieg.run_id)


class _PrzeniesionyPunktDokumentu(SerwisAwaryjny):
    """Lista odpowiada 200, każdy dokument 404 — tak wygląda punkt dokumentu przeniesiony
    u pośrednika, nie sprawa wycofana."""

    def __call__(self, zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.path == KONTRAKT.punkty.lista:
            return super().__call__(zadanie)
        self.dokumentow += 1
        return httpx.Response(404, content=b'{"detail": "not found"}')


def test_404_na_kazdym_dokumencie_zatrzymuje_przebieg_przed_progiem(store: Store) -> None:
    """Pomijanie 404 ma sufit: `PROG_404_POD_RZAD` kolejnych braków to złamany kontrakt.

    Bez sufitu przeniesiony punkt dokumentu dawałby przebieg `zakonczony` po przemieleniu całej
    listy — przy 29 580 orzeczeniach tyle samo żądań do cudzego serwisu za nic (przegląd kodu
    2026-09-18). Próg ma zatrzymać przebieg, zanim pójdzie setne żądanie.
    """
    serwis = _PrzeniesionyPunktDokumentu()

    with pytest.raises(SourceContractBroken, match="404"):
        uruchom(store, serwis)

    assert serwis.dokumentow == pipeline.PROG_404_POD_RZAD, "zatrzymanie dokładnie na progu"
    assert store.get_run(jedyny_przebieg(store)).status == "blad"
    assert store.count("documents") == 0


def test_przebieg_zakonczony_bledem_wznawia_sie_tylko_jawnie(store: Store) -> None:
    """Po złamanym kontrakcie, wygasłym kluczu albo odmowie serwisu stan bywa ustępujący,
    a punkt kontrolny jest wart stron listy — więc `wznow --run-id` przyjmuje `blad`.

    Automat nie: `wznow` bez identyfikatora i `pobierz` z tymi samymi kryteriami nie mają
    prawa wracać do złamanego kontraktu same przy każdym uruchomieniu (przegląd kodu
    2026-09-18). Tu kontrakt „naprawia się" między wywołaniami, bo drugą atrapą jest serwis
    zdrowy.
    """
    smiec = b'{"komunikat": "chwilowo niedostepne"}'
    with pytest.raises(SourceContractBroken):
        uruchom(
            store,
            SerwisAwaryjny(na_dokumencie=3, reakcja=lambda _: httpx.Response(200, content=smiec)),
        )
    run_id = jedyny_przebieg(store)
    assert store.get_run(run_id).status == "blad"

    with pytest.raises(ConfigError, match="nie ma czego wznawiać"):
        pipeline.do_wznowienia(store, None)
    with pytest.raises(TransportError):
        uruchom(store, SerwisAwaryjny(na_dokumencie=1))
    assert store.count_runs() == 2 and store.get_run(run_id).status == "blad", (
        "`pobierz` z tymi samymi kryteriami nie ma prawa wrócić do złamanego kontraktu sam"
    )
    assert pipeline.do_wznowienia(store, run_id)[0] == run_id

    wynik = pipeline.wznow(
        store,
        run_id,
        zgoda=True,
        user_agent="kio-tool-test (test@example.org)",
        klient_factory=partial(build_http_client, transport=httpx.MockTransport(SerwisAwaryjny())),
        zegar=ZegarTestowy(),
    )

    assert (wynik.run_id, wynik.status) == (run_id, "zakonczony")
    assert store.count_runs() == 2, "jawne wznowienie nie zakłada trzeciego przebiegu"
    assert store.count("documents") == store.count("raw_versions") == len(SLUGI)


# --- odmowa serwisu: 5xx trafia do dziennika razem z powodem ------------------------------------


def test_5xx_zapisuje_powod_ktory_nazywa_status(store: Store) -> None:
    """Powód przebiegu ma nieść liczbę, a nie samo „coś poszło nie tak”.

    Operator czyta go z `runy`, więc to jedyne miejsce, w którym po przerwanym przebiegu
    widać, czy winna była sieć, czy serwis — a to są dwie różne decyzje o tym, co zrobić dalej.
    """
    serwis = SerwisAwaryjny(na_dokumencie=3, reakcja=lambda _: httpx.Response(503, content=b"{}"))

    with pytest.raises(ServerError):
        uruchom(store, serwis)

    przebieg = store.get_run(jedyny_przebieg(store))
    assert przebieg.powod is not None and "503" in przebieg.powod
    assert statusy_zadan(store)[-1] == 503, "odmowa serwisu ma wiersz w dzienniku żądań"


def test_zgloszona_liczba_dokumentow_przezywa_przerwanie(store: Store) -> None:
    """Po przerwaniu operator ma wiedzieć, ilu dokumentów jeszcze nie ma.

    `runs.zakres` i `run_documents` razem odpowiadają na „ile zostało”: kanał zgłosił `total`
    na stronie listy, a przebieg objął tylu, ilu zdążył. Bez tego przerwany przebieg mówi
    tylko „nie skończyłem”.
    """
    serwis = SerwisAwaryjny(na_dokumencie=4, reakcja=lambda _: httpx.Response(503, content=b"{}"))

    with pytest.raises(ServerError):
        uruchom(store, serwis)

    przebieg = store.get_run(jedyny_przebieg(store))
    assert przebieg.dokumentow == 3, "objęci kandydaci są policzeni mimo przerwania"
    assert przebieg.zadan == 7, (
        "strona listy, trzy udane dokumenty i trzy próby czwartego (`ponowienia.proby`)"
    )
    assert przebieg.zakres.startswith("2024-01-01"), "zakres zostaje przy przerwanym przebiegu"
    assert LISTA[LICZNIK] > przebieg.dokumentow, (
        "kanał zgłosił więcej dokumentów, niż przebieg objął — ta różnica jest tym, "
        "czego operatorowi brakuje po przerwaniu"
    )
