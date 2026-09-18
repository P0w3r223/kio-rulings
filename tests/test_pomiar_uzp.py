"""Strażnik pomiarów UZP — `scripts/pomiar_uzp.py`: 4b/16 (kontrakt wyszukiwarki) i 19 (bajty).

Do 2026-09-18 w `tests/test_sonda.py`. Pomiar 19 jest tu szczególny i ma własne sekcje: kończy
się **werdyktem**, a werdykt jest wejściem ADR-0001 — decyzji o kluczu tożsamości, bramki przed
`store.py` i strażnika miny 1. Fałszywy werdykt nie wywraca żadnego przebiegu: wygląda jak
zdanie do przepisania i jest zdaniem do przepisania, tylko nieprawdziwym. Materiał i kształt
atrapy opisuje nagłówek `wsparcie_sondy.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import httpx

# Moduły sondy mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import ksztalty
import pomiar_uzp
import pytest
import zadanie

from kio_tool import logbook
from kio_tool.config import register_secret
from tests.wsparcie_sondy import (
    ADRES_19,
    BOT_CHECK,
    SCIEZKA_UZP_KONTROLA,
    SCIEZKA_UZP_TRESC,
    SCIEZKA_UZP_WYNIKI,
    TRESC_19,
    TRESC_19_INNA,
    UA_TESTOWY,
    UZP_DETAILS_OK,
    UZP_WYNIKI_OK,
    Odpowiedz,
    Serwis,
    ZegarTestowy,
    dziennik_z_wierszami,
    odczyt,
    serwis_19,
    uzp_scenariusz,
    wiersz_reczny,
    wiersze_dziennika,
    wynik,
    wynik_19,
)

# --- pomiar UZP: kolejność, zatrzymanie, bramka --------------------------------------------


def test_pomiar_uzp_wysyla_kontrole_przed_nieznanym_postem(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Kolejność jest tu **całą** różnicą między kontrolą a jej brakiem.

    Przy odwrotnej kolejności pierwsza odmowa skaziłaby kontrolę: nie dałoby się odróżnić
    „POST jest niemile widziany" od „klient jest niemile widziany". Ten test jest jedynym
    obserwatorem tej kolejności — zamiana dwóch bloków miejscami nie psuje niczego innego.
    """
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(tresc=UZP_WYNIKI_OK))
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    assert serwis.slad == [
        ("GET", SCIEZKA_UZP_KONTROLA),
        ("POST", SCIEZKA_UZP_WYNIKI),
        ("POST", SCIEZKA_UZP_WYNIKI),
    ]
    assert [w.nazwa for w in wyniki] == [
        "uzp_kontrola_details_9620",
        "uzp_4b_getresults",
        "uzp_16_resultcounts",
    ]


def test_pomiar_uzp_trzyma_odstep_miedzy_zadaniami(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Limiter jest tu jedynym hamulcem — UZP nie publikuje żadnego limitu, a dwa cudze
    precedensy nie są pomiarem tolerancji serwisu. Sonda bez odstępu wygląda tak samo
    z naszej strony i inaczej z tamtej."""
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(tresc=UZP_WYNIKI_OK))
    zegar = podstaw(serwis)

    pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    assert sum(zegar.sleeps) >= 2 * zadanie.ODSTEP_UZP_S, (
        f"trzy żądania rozeszły się na {sum(zegar.sleeps)} s przy odstępie "
        f"{zadanie.ODSTEP_UZP_S} s — limiter nie zatrzymał ani jednego"
    )


@pytest.mark.parametrize(
    ("opis", "kontrola", "fragment_powodu"),
    [
        ("odmowa punktu", Odpowiedz(status=403, tresc=b"forbidden"), "403"),
        ("bot-check ze statusem 200", Odpowiedz(tresc=BOT_CHECK), "kształcie"),
        ("żądanie nie doszło", httpx.ConnectTimeout("limit czasu"), "nie doszedł"),
    ],
)
def test_pomiar_uzp_nie_wysyla_postu_gdy_kontrola_zawiodla(
    opis: str,
    kontrola: Odpowiedz | BaseException,
    fragment_powodu: str,
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Własność 6: „narzędzie nie omija zabezpieczeń" (audyt 12, art. 267 § 1 k.k.).

    Trzy drogi, którymi kontrola może zawieść, i jeden skutek: nieznany POST **nie idzie**.
    Przypadek środkowy jest najmocniejszy — status 200 zatrzymuje grupę, bo kształt jest nie
    do poznania. Scenariusz nie zawiera wpisu dla `/Home/GetResults`, więc żądanie wysłane
    mimo zatrzymania kończy się `AssertionError`, a nie cichą odpowiedzią zastępczą.
    """
    serwis = uzp_scenariusz(kontrola)
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_UZP_KONTROLA)], f"{opis}: POST mimo to poszedł"
    niewyslane = [w for w in wyniki if not w.wyslane]
    assert [w.nazwa for w in niewyslane] == ["uzp_4b_getresults", "uzp_16_resultcounts"], (
        f"{opis}: zatrzymany pomiar nie zostawił śladu po **każdym** żądaniu, które nie "
        "poszło — pomiar znikający z listy jest ciszą, a nie skrótem"
    )
    for pominiety in niewyslane:
        assert pominiety.adres == "(niewysłane)"
        assert fragment_powodu in pominiety.uwaga
        assert "nie omija zabezpieczeń" in pominiety.uwaga


def test_pomiar_uzp_zatrzymuje_sie_po_odmowie_pierwszego_postu(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Drugi POST (pomiar 16) nie idzie, gdy pierwszy dostał odmowę — nie ma czego mierzyć,
    a każde kolejne żądanie po odmowie jest pukaniem do zamkniętych drzwi.

    Pomiar 16 **zostaje na liście** jako wpis niewysłany i to jest poprawka z przeglądu
    2026-09-17: przy samym zniknięciu z listy czytający po tygodniu nie odróżniłby „nie
    poszedł, bo 4b dostał 429" od „nigdy go w tej wersji sondy nie było".
    """
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(status=429, tresc=b""))
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    assert len(serwis.zadania) == 2
    assert [w.nazwa for w in wyniki] == [
        "uzp_kontrola_details_9620",
        "uzp_4b_getresults",
        "uzp_16_resultcounts",
    ]
    assert [w.wyslane for w in wyniki] == [True, True, False]


def test_pomiar_uzp_zatrzymuje_sie_gdy_pierwszy_post_wraca_bot_checkiem(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Ten sam warunek po stronie POST-u: 200 z kształtem nie do poznania zatrzymuje grupę.

    Bez członu kształtu w `Wynik.odmowa` sonda pojechałaby dalej i zmierzyła liczniki
    `#resultCounts` na stronie, która ich nie ma.
    """
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(tresc=BOT_CHECK))
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    assert len(serwis.zadania) == 2
    post = next(w for w in wyniki if w.nazwa == "uzp_4b_getresults")
    assert post.ksztalt_zgodny is False
    assert not next(w for w in wyniki if w.nazwa == "uzp_16_resultcounts").wyslane


def test_pomiar_uzp_przedstawia_sie_podana_tozsamoscia(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Reguła 16 na całej drodze: nagłówek ustawia `build_http_client`, ale dopiero ten test
    mówi, że żądanie sondy naprawdę go niesie."""
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(tresc=UZP_WYNIKI_OK))
    podstaw(serwis)

    pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    assert serwis.zadania[0].headers["User-Agent"] == UA_TESTOWY


def test_powod_pominiecia_pomiaru_16_wskazuje_ktore_zadanie_grupe_zatrzymalo(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Powód bez nazwy żądania mówi „coś się stało" i zostawia czytającego z listą podejrzanych.

    Przy dwóch drogach zatrzymania — zawiedziona kontrola i odmowa pierwszego POST-u — nazwa
    jest jedyną rzeczą, która je rozróżnia w zapisie sprzed tygodnia.
    """
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(status=429, tresc=b""))
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_uzp(UA_TESTOWY)
    pominiety = next(w for w in wyniki if not w.wyslane)

    assert "uzp_4b_getresults" in pominiety.uwaga


def test_skrot_w_dzienniku_i_odczyt_wsteczny_uzywaja_jednej_dlugosci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zapis szedł literałem `[:16]`, odczyt przez `skrot_dziennika` — czyli stała, która
    istnieje po to, żeby ta liczba stała w jednym miejscu, stała w dwóch.

    Rozjazd byłby niewidoczny przy dzisiejszej wartości i fałszywy przy każdej innej: dwa
    przycięcia o różnej długości są zawsze nierówne, a nierówność znaczy w pomiarze 19 „bajty
    NIESTABILNE" — czyli odrzucenie klucza tożsamości, który działa. Test przestawia stałą,
    bo przy niezmienionej wartości obie drogi dają to samo i nie ma czego obserwować.
    """
    monkeypatch.setattr(logbook, "DLUGOSC_SKROTU_W_DZIENNIKU", 20)
    pelny = "abcdef0123456789" * 4
    adres = "https://orzeczenia.uzp.gov.pl/Home/ContentHtml/18946"

    logbook.dopisz_dziennik(
        zadanie.DZIENNIK, "sonda-1", "2023-11-14T22:13:20Z", [wynik(adres=adres, sha256=pelny)]
    )

    odczytane = pomiar_uzp.wczesniejsze_odczyty(adres, dziennik=zadanie.DZIENNIK)

    assert [o.skrot for o in odczytane] == [logbook.skrot_dziennika(pelny)], (
        "zapis i odczyt przycinają skrót na różnych długościach — porównanie bajtów tego "
        "samego dokumentu dałoby „NIESTABILNE” bez żadnej zmiany po drugiej stronie"
    )


# --- pomiar 19: czy bajty treści są stabilne między pobraniami -----------------------------
#
# Pomiar 19 jest w tym pliku szczególny i dlatego ma własną sekcję. Trzy inne pomiary kończą
# się liczbą, którą operator przepisuje; ten kończy się **werdyktem**, a werdykt jest wejściem
# ADR-0001 — decyzji o tym, czy `(doc_id, content_sha256)` jest kluczem tożsamości. ADR-0001
# jest z kolei bramką przed `store.py` (`tests/test_bramki_faz.py`) i strażnikiem miny 1, tej
# samej, która w CEIDG kosztowała 2 681 żądań i zero użytecznych rekordów. Fałszywy werdykt
# nie wywraca żadnego przebiegu: wygląda jak zdanie do przepisania i jest zdaniem do
# przepisania, tylko nieprawdziwym.
#
# Druga osobliwość jest kalendarzowa. Pomiar rozkłada się na dwa przebiegi w odstępie doby,
# a między nimi jedynym nośnikiem pierwszego odczytu jest `docs/dziennik_zadan.md` — czyli
# **plik czytany przez parsowanie tabeli markdown napisanej przez inny kod tego samego
# modułu**. Ten szew (`wiersz_dziennika` pisze, `wczesniejsze_odczyty` czyta) nie ma żadnej
# wspólnej deklaracji poza zgodnością dwóch wyrażeń i dlatego ma tu własny test przelotowy.


# --- odczyt wstecz: dziennik jako jedyny nośnik między przebiegami -------------------------


def test_brak_dziennika_znaczy_brak_wczesniejszych_odczytow() -> None:
    """Pierwszy przebieg w życiu repozytorium nie ma czego czytać i nie ma prawa się wywrócić.
    Dziennik powstaje dopiero przy pierwszym żądaniu, a odczyt wstecz idzie **przed** nim."""
    assert not zadanie.DZIENNIK.exists()

    assert pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK) == []


def test_to_co_dziennik_zapisal_odczyt_wstecz_odnajduje() -> None:
    """Przelot przez szew, na którym stoi cały pomiar 19: `wiersz_dziennika` pisze skrót
    przycięty do szesnastu znaków, `wczesniejsze_odczyty` czyta czwartą kolumnę jako adres
    i ósmą jako skrót. Obie strony są dwoma wyrażeniami bez wspólnej deklaracji.

    Rozjazd którejkolwiek — inna długość przycięcia, dołożona kolumna, inny cudzysłów wokół
    adresu — nie psuje ani zapisu, ani odczytu z osobna. Psuje wyłącznie **porównanie między
    przebiegami**, czyli jedyną rzecz, po którą pomiar 19 istnieje. Objawia się przy tym jako
    „pierwszy odczyt tego dokumentu — zegar ruszył" po raz drugi, trzeci i dziesiąty: werdykt
    poprawnie wyglądający, wypisywany w nieskończoność.
    """
    pelny_skrot = hashlib.sha256(TRESC_19).hexdigest()
    logbook.dopisz_dziennik(
        zadanie.DZIENNIK,
        "sonda-1",
        "2023-11-14T22:13:20Z",
        [wynik(adres=ADRES_19, sha256=pelny_skrot)],
    )

    odczytane = pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK)

    assert len(odczytane) == 1, (
        "wiersz dopisany przez sondę nie został odnaleziony przez odczyt wstecz — zapis "
        "i odczyt dziennika rozjechały się, a pomiar 19 wypisze „pierwszy odczyt” na zawsze"
    )
    assert odczytane[0].skrot == pelny_skrot[:16]
    assert odczytane[0].ts == "2023-11-14T22:13:20Z"


def test_odczyt_wstecz_pomija_wiersze_innych_adresow() -> None:
    """Dziennik niesie wszystkie żądania wszystkich pomiarów. Porównanie bajtów ma sens
    wyłącznie w obrębie jednego dokumentu — wiersz `Details/9620` w tej liście zamieniłby
    pomiar 19 w porównanie dwóch różnych stron."""
    logbook.dopisz_dziennik(
        zadanie.DZIENNIK,
        "sonda-1",
        "2023-11-14T22:13:20Z",
        [
            wynik(adres="https://orzeczenia.uzp.gov.pl/Home/Details/9620", sha256="a" * 64),
            wynik(adres=ADRES_19, sha256="b" * 64),
            wynik(adres="https://atlasprzetargow.pl/api/kio", sha256="c" * 64),
        ],
    )

    odczytane = pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK)

    assert [o.skrot for o in odczytane] == ["b" * 16]


def test_odczyt_wstecz_pomija_naglowki_obu_tabel_dziennika() -> None:
    """Nagłówek dziennika ma dwie tabele i pięć wierszy zaczynających się od `|`.

    Wiersz nagłówka kolumn wzięty za dane dałby „poprzedni odczyt" ze skrótem `sha256`
    i znacznikiem `ts` — czyli werdykt „bajty NIESTABILNE" przy pierwszym prawdziwym pomiarze,
    bo napis `sha256` nie równa się żadnemu skrótowi.
    """
    dziennik_z_wierszami()

    assert pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK) == []
    assert "| run_id | ts | metoda |" in zadanie.DZIENNIK.read_text(encoding="utf-8"), (
        "nagłówek podrzucony w tym teście nie zawiera wiersza kolumn — test mierzy pominięcie "
        "czegoś, czego w materiale nie ma"
    )


def test_odczyt_wstecz_pomija_wiersz_pomiaru_ktory_nie_poszedl() -> None:
    """Wiersz niewysłany ma „—" w kolumnie skrótu i jest zapisem **braku** bajtów.

    Wzięty za odczyt dałby porównanie skrótu z myślnikiem, czyli werdykt „bajty NIESTABILNE"
    z powodu pomiaru, który nigdy nie opuścił procesu.
    """
    logbook.dopisz_dziennik(
        zadanie.DZIENNIK,
        "sonda-1",
        "2023-11-14T22:13:20Z",
        [logbook.niewyslany("uzp_19_contenthtml", "GET", "pomiar przerwany")],
    )

    assert pomiar_uzp.wczesniejsze_odczyty("(niewysłane)", dziennik=zadanie.DZIENNIK) == []
    assert pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK) == []


def test_odczyt_wstecz_czyta_wpis_reczny_tak_samo_jak_maszynowy() -> None:
    """Deklaracja z docstringu `wczesniejsze_odczyty`, i to nie jest uprzejmość wobec formatu.

    Nagłówek dziennika mówi, że odczyt ręczny zostawia wiersz w tych samych kolumnach —
    pomiar 1 poszedł `curl`-em, przegląd z 2026-09-14 wysłał około trzydziestu żądań ręką.
    Odczyt ręczny tego samego adresu jest dokładnie tym samym dowodem co maszynowy, więc
    pominięcie go kasowałoby połowę materiału pomiaru rozłożonego na dobę.
    """
    dziennik_z_wierszami(wiersz_reczny(ADRES_19, "2023-11-13T09:00:00Z", "d" * 16))

    odczytane = pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK)

    assert [o.skrot for o in odczytane] == ["d" * 16]


def test_odczyt_wstecz_pomija_wpis_reczny_bez_zachowanych_bajtow() -> None:
    """Nagłówek dziennika mówi wprost: kolumna `sha256` zostaje pusta, jeśli bajtów nikt nie
    zachował — „i to jest informacja o wadze dowodu, nie brak do uzupełnienia". Wiersz bez
    skrótu nie ma czego wnieść do porównania bajtów."""
    dziennik_z_wierszami(
        wiersz_reczny(ADRES_19, "2023-11-13T09:00:00Z", "—"),
        wiersz_reczny(ADRES_19, "2023-11-13T10:00:00Z", ""),
    )

    assert pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK) == []


def test_odczyt_wstecz_szuka_adresu_po_zamaskowaniu() -> None:
    """Dziennik trzyma `url_redacted`, nie `url` — więc szukany adres też musi być zamaskowany.

    Bez tego pomiar dotykający adresu z zarejestrowanym sekretem nigdy nie znalazłby własnych
    wcześniejszych odczytów i wypisywałby „pierwszy odczyt” przy każdym przebiegu. Pomiar 19
    dziś sekretu w adresie nie ma; `wczesniejsze_odczyty` jest jednak funkcją ogólną i to
    zachowanie jest jej zadeklarowaną własnością, a nie przypadkiem konfiguracji.
    """
    klucz = "sekretny-klucz-atlasu"
    register_secret(klucz)
    adres = f"https://atlasprzetargow.pl/api/kio?key={klucz}"
    logbook.dopisz_dziennik(
        zadanie.DZIENNIK, "sonda-1", "2023-11-14T22:13:20Z", [wynik(adres=adres, sha256="e" * 64)]
    )

    odczytane = pomiar_uzp.wczesniejsze_odczyty(adres, dziennik=zadanie.DZIENNIK)

    assert [o.skrot for o in odczytane] == ["e" * 16], (
        "odczyt wstecz szuka adresu surowego w dzienniku, który trzyma adres zamaskowany"
    )


def test_odczyt_wstecz_zbiera_wszystkie_przebiegi_tego_samego_dokumentu() -> None:
    """Trzeci i czwarty przebieg mają widzieć poprzednie, a nie tylko ostatni."""
    for numer, skrot in enumerate(("1", "2", "3"), start=1):
        logbook.dopisz_dziennik(
            zadanie.DZIENNIK,
            f"sonda-{numer}",
            f"2023-11-1{numer}T09:00:00Z",
            [wynik(adres=ADRES_19, sha256=skrot * 64)],
        )

    assert [
        o.skrot for o in pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK)
    ] == ["1" * 16, "2" * 16, "3" * 16]


# --- odstęp: znacznik z pliku jest treścią, nie liczbą z zegara ----------------------------


@pytest.mark.parametrize(
    ("opis", "wczesniej", "pozniej", "oczekiwane"),
    [
        ("doba", "2023-11-13T22:13:20Z", "2023-11-14T22:13:20Z", 24.0),
        ("pół godziny", "2023-11-14T22:13:20Z", "2023-11-14T22:43:20Z", 0.5),
        ("ten sam moment", "2023-11-14T22:13:20Z", "2023-11-14T22:13:20Z", 0.0),
        ("znacznik w cudzej strefie", "2023-11-13T23:13:20+01:00", "2023-11-14T22:13:20Z", 24.0),
    ],
)
def test_odstep_liczony_miedzy_znacznikami(
    opis: str, wczesniej: str, pozniej: str, oczekiwane: float
) -> None:
    """Odstęp jest tym, co odróżnia „stabilne" od „nic się nie zdążyło zmienić" — czyli całą
    treścią pomiaru 19.

    Ostatni przypadek jest o wpisie ręcznym: `23:13+01:00` to ten sam moment co `22:13Z`, więc
    doba liczy się od niego jak od znacznika w UTC. Odczytanie tego napisu jako naiwnej godziny
    dałoby 23 godziny i werdykt „za wcześnie" przy pomiarze, który odczekał dobę.
    """
    assert pomiar_uzp._odstep_godzin(wczesniej, pozniej) == pytest.approx(oczekiwane), opis


@pytest.mark.parametrize(
    "znacznik", ["—", "", "wczoraj", "2023-13-45T99:99:99Z", "recznie, koło południa"]
)
def test_znacznik_nie_do_odczytania_daje_odstep_nieznany(znacznik: str) -> None:
    """Deklaracja z docstringu: „nieparsowalny znacznik nie ma prawa wywrócić pomiaru".

    Znacznik z dziennika jest napisem z pliku, a przy wpisie ręcznym — napisem wpisanym ręką.
    Wyjątek zamiast werdyktu wywracałby `pomiar_stabilnosc` **po** wysłaniu żądania, czyli
    kasował podsumowanie przebiegu, za który cudzy serwer już zapłacił pracą.
    """
    assert pomiar_uzp._odstep_godzin(znacznik, "2023-11-14T22:13:20Z") is None


# --- werdykt: jedyne, co z pomiaru 19 zostaje ----------------------------------------------


def test_pierwszy_odczyt_mowi_ze_zegar_ruszyl_i_kiedy_wrocic() -> None:
    """Werdykt pierwszego przebiegu jest instrukcją, nie komunikatem o niczym.

    Pomiar kosztuje kalendarz, nie pracę: bez zdania „wróć za dobę" operator zostaje z jednym
    skrótem i bez powodu, żeby uruchomić sondę drugi raz — a ADR-0001 czeka. Liczba godzin
    jest wzięta ze stałej modułu, nie wpisana w napis dwa razy.
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(wynik_19(), [], ts_teraz="2023-11-14T22:13:20Z")

    assert "pierwszy odczyt" in werdykt
    assert f"{pomiar_uzp.ODSTEP_POMIARU_19_H:.0f} h" in werdykt
    assert "stabiln" not in werdykt.lower(), "pierwszy odczyt ogłosił rozstrzygnięcie"


@pytest.mark.parametrize(
    ("opis", "teraz"),
    [
        ("pomiar nie poszedł", logbook.niewyslany("uzp_19_contenthtml", "GET", "przerwany")),
        ("błąd transportu — brak bajtów", wynik(adres=ADRES_19, status=None, sha256=None)),
    ],
)
def test_werdykt_bez_bajtow_mowi_ze_zegar_doby_nie_ruszyl(opis: str, teraz: logbook.Wynik) -> None:
    """Przebieg bez odpowiedzi nie jest odczytem i nie ma prawa uchodzić za połowę pomiaru.

    Gdyby uchodził, operator odczekałby dobę licząc od przebiegu, w którym nic nie przyszło,
    i drugi odczyt porównałby się z niczym — czyli znowu wypisał „pierwszy odczyt”, tyle że
    dobę później.
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(
        teraz, [odczyt("2023-11-13T09:00:00Z", "b" * 16)], ts_teraz="2023-11-14T22:13:20Z"
    )

    assert "nie doszedł do skutku" in werdykt, opis
    assert "stabiln" not in werdykt.lower()


def test_zgodne_skroty_po_dobie_rozstrzygaja_na_rzecz_klucza() -> None:
    """Werdykt pozytywny niesie trzy rzeczy: rozstrzygnięcie, skrót i **gdzie go zapisać**.

    Zdanie bez wskazania `decisions.md` i ADR-0001 zostawia wynik na ekranie, a ekran znika
    z sesją. Pomiar rozłożony na dwie doby, którego wynik nigdzie nie trafia, trzeba wykonać
    trzeci raz.
    """
    skrot = "a" * 16
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(sha="a" * 64),
        [odczyt("2023-11-13T09:00:00Z", skrot)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "stabilne" in werdykt and "NIESTABILNE" not in werdykt
    assert skrot in werdykt
    assert "ADR-0001" in werdykt
    assert "decisions.md" in werdykt


def test_rozne_skroty_po_dobie_wykluczaja_klucz_i_nazywaja_mine() -> None:
    """Werdykt negatywny jest tym cenniejszym z dwóch: zamyka drogę, którą inaczej poszedłby
    `store.py`. Niesie **oba** skróty, bo bez nich zdanie „bajty się zmieniły" nie ma czym się
    obronić przed pytaniem „na pewno ten sam dokument?"."""
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(sha="c" * 64),
        [odczyt("2023-11-13T09:00:00Z", "b" * 16)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "NIESTABILNE" in werdykt
    assert "b" * 16 in werdykt and "c" * 16 in werdykt
    assert "2023-11-13T09:00:00Z" in werdykt
    assert "ADR-0001" in werdykt
    assert "mina 1" in werdykt


@pytest.mark.parametrize(
    ("opis", "sha_teraz", "skrot_wczesniej"),
    [
        ("skróty zgodne", "a" * 64, "a" * 16),
        ("skróty różne", "c" * 64, "b" * 16),
    ],
)
def test_odstep_krotszy_niz_doba_nie_rozstrzyga(
    opis: str, sha_teraz: str, skrot_wczesniej: str
) -> None:
    """Sedno stałej `ODSTEP_POMIARU_19_H` i jedyne miejsce, w którym o niej mowa.

    Zgodność skrótów po trzech godzinach nie znaczy „stabilne" — znaczy „nic się nie zdążyło
    zmienić", a to jest inne zdanie i prowadzi do innego ADR-0001. Werdykt ogłaszający
    stabilność po godzinie byłby dokładnie tą liczbą bez pokrycia, której zakazuje zasada 7.1,
    w miejscu, gdzie kosztuje najwięcej.
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(sha=sha_teraz),
        [odczyt("2023-11-14T19:13:20Z", skrot_wczesniej)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "za wcześnie" in werdykt, opis
    assert "3.0 h" in werdykt
    assert "**bajty stabilne**" not in werdykt


def test_roznica_przy_krotkim_odstepie_jest_wynikiem_sama_w_sobie() -> None:
    """Asymetria dwóch krótkich odstępów, i to jest rozstrzygnięcie, nie szczegół napisu.

    Zgodność po trzech godzinach nie mówi nic. **Różnica** po trzech godzinach mówi dużo:
    bajty zmieniły się w ciągu godzin, więc `content_sha256` odpada jako klucz bez czekania
    na dobę. Zrównanie obu przypadków kosztowałoby operatora dobę na potwierdzenie czegoś, co
    już wiadomo.
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(sha="c" * 64),
        [odczyt("2023-11-14T19:13:20Z", "b" * 16)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "**różne**" in werdykt
    assert "w ciągu godzin" in werdykt


def test_odstep_dokladnie_doby_juz_rozstrzyga() -> None:
    """Granica jest domknięta od góry — inaczej przebieg uruchomiony co do sekundy dobę później
    wypisywałby „za wcześnie: minęło 24.0 h, a pomiar wymaga 24 h", czyli zdanie sprzeczne
    z samym sobą."""
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(),
        [odczyt("2023-11-13T22:13:20Z", "a" * 16)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "za wcześnie" not in werdykt
    assert "stabilne" in werdykt


def test_werdykt_przy_nieczytelnym_znaczniku_mowi_o_tym_zamiast_milczec() -> None:
    """Wpis ręczny z datą wpisaną ręką nie ma prawa ani wywrócić pomiaru, ani przemilczeć tego,
    że odstęp jest nieznany. Werdykt „bajty stabilne" bez odstępu byłby zdaniem mocniejszym,
    niż pozwala materiał.

    **Asercja mówiła do 2026-09-17 coś przeciwnego niż ten docstring** i to jest najciekawsze
    w tym teście: żądała słowa „stabilne" w werdykcie wydanym przy odstępie nieznanym, czyli
    utrwalała dokładnie to zdanie mocniejsze, przed którym docstring ostrzega. Test przechodził
    zielono, bo produkcja robiła to samo: gałąź „odstęp nieznany" ustawiała wyłącznie opis
    i spadała do pełnego werdyktu pozytywnego razem z instrukcją przepisania go do
    `decisions.md`, gdzie „wpis nie jest usuwany". Znalezione przeglądem 2026-09-17.

    Zgodność skrótów przy nieznanym odstępie może znaczyć „ten sam plik dwa razy w ciągu pięciu
    minut" — a to jest inne zdanie niż „stabilny przez dobę".
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(),
        [odczyt("wczoraj koło południa", "a" * 16)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "odstęp nieznany" in werdykt
    assert "wczoraj koło południa" in werdykt, "znacznik do poprawienia ma być w werdykcie"
    assert "stabilne" not in werdykt, "zgodność bez odstępu nie jest stabilnością"
    assert "decisions.md" not in werdykt, (
        "werdykt nierozstrzygający nie ma prawa kazać przepisywać się do dokumentu, "
        "w którym wpis nie jest usuwany"
    )


def test_niezgodnosc_rozstrzyga_takze_przy_nieznanym_odstepie() -> None:
    """Druga strona tej samej asymetrii — i powód, dla którego nie wystarczyło uciszyć gałęzi.

    **Niezgodność** skrótów rozstrzyga przy każdym odstępie: różne bajty tego samego dokumentu
    znaczą to samo po pięciu minutach i po dobie. **Zgodność** wymaga wiedzy, ile czasu minęło.
    Poprawka, która przy nieznanym odstępie milczałaby w obu przypadkach, zamieniłaby fałszywy
    werdykt pozytywny na utratę werdyktu prawdziwego — czyli ciszę w miejscu, gdzie materiał
    niesie rozstrzygnięcie.
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(),
        [odczyt("wczoraj koło południa", "b" * 16)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "NIESTABILNE" in werdykt
    assert "ADR-0001" in werdykt, "rozstrzygnięcie ma nieść swoje przeznaczenie"


def test_werdykt_porownuje_sie_z_najnowszym_odczytem_a_nie_z_pierwszym() -> None:
    """Przy trzecim i czwartym przebiegu pytanie brzmi „czy zmieniło się od **ostatniego** razu".

    Porównanie z najstarszym odczytem odpowiadałoby na pytanie o cały okres naraz i gubiło
    zmianę, która zaszła i wróciła — a to jest właśnie ten kształt niestabilności, który
    wygląda jak stabilność.
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(
        wynik_19(sha="c" * 64),
        [odczyt("2023-11-11T09:00:00Z", "z" * 16), odczyt("2023-11-13T09:00:00Z", "c" * 16)],
        ts_teraz="2023-11-14T22:13:20Z",
    )

    assert "stabilne" in werdykt
    assert "2023-11-13T09:00:00Z" in werdykt
    assert "2023-11-11T09:00:00Z" not in werdykt


# --- przebieg pomiaru 19: jedno żądanie i głośny werdykt -----------------------------------


def test_pomiar_19_wysyla_dokladnie_jedno_zadanie_na_staly_dokument(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Identyfikator stały jest **całym** pomiarem i to stoi przy `UZP_CONTENT_ID`.

    Dokument wylosowany przy każdym uruchomieniu mierzyłby różnicę między dokumentami, a nie
    między pobraniami tego samego — czyli odpowiadałby na inne pytanie niż zadane, wyglądając
    tak samo. Drugie żądanie w przebiegu byłoby drugim kosztem bez drugiej odpowiedzi.
    """
    serwis = serwis_19(Odpowiedz(tresc=TRESC_19))
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_UZP_TRESC)]
    assert [w.nazwa for w in wyniki] == ["uzp_19_contenthtml"]
    assert pomiar_uzp.UZP_CONTENT_ID in serwis.zadania[0].url.path


def test_dokument_pomiaru_19_jest_tym_ktorego_odczyt_ma_date() -> None:
    """Identyfikator dokumentu i źródło oczekiwania mają mówić o **tym samym** dokumencie.

    `UZP_CONTENT_ID` niesie w docstringu zdanie, że dokument ma własny odczyt z datą
    (architektura 7, 2026-09-14), a `ksztalty.UZP_CONTENT.zrodlo` wypisuje ten odczyt razem
    z numerem. Zmiana identyfikatora bez zmiany źródła rozjeżdża te dwa zdania po cichu:
    sonda pobierałaby dokument, którego nikt nigdy nie odczytał, powołując się na odczyt
    innego — czyli zasada 7.1 złamana w miejscu, gdzie źródło jest wypisywane pod każdą oceną
    kształtu. Ekran wyglądałby przy tym identycznie.

    Ten test jest jedynym obserwatorem tej pary: zmiana samej stałej nie psuje żadnego innego
    testu, bo wszystkie biorą numer z produkcji.
    """
    assert pomiar_uzp.UZP_CONTENT_ID in ksztalty.UZP_CONTENT.zrodlo, (
        f"pomiar 19 pobiera `ContentHtml/{pomiar_uzp.UZP_CONTENT_ID}`, a źródło oczekiwania mówi "
        f"o innym dokumencie: {ksztalty.UZP_CONTENT.zrodlo}"
    )


def test_pomiar_19_wypisuje_werdykt_a_nie_sam_wiersz_zadania(
    podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Werdykt jest jedynym produktem tego pomiaru — reszta przebiegu wygląda jak każdy inny.

    Skreślenie linii `print(f"\\nPomiar 19 — …")` nie psuje żadnego żądania, nie zmienia
    dziennika i nie rusza podsumowania: zostawia przebieg, po którym operator ma skrót
    i nie ma zdania. Ta asercja jest jedynym obserwatorem tej linii.
    """
    podstaw(serwis_19(Odpowiedz(tresc=TRESC_19)))

    pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)

    wypisane = capsys.readouterr().out

    assert "Pomiar 19" in wypisane, "przebieg skończył się bez werdyktu"
    assert "pierwszy odczyt" in wypisane


def test_pomiar_19_nie_porownuje_pierwszego_przebiegu_z_samym_soba(
    podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Odczyt wstecz idzie **przed** żądaniem i to jest różnica między pomiarem a jego pozorem.

    `Kronika.zanotuj` dopisuje wiersz w chwili powrotu odpowiedzi, więc odczyt wstecz wykonany
    po żądaniu zobaczyłby bieżący przebieg jako „poprzedni odczyt" i wypisał zgodność skrótu
    z samym sobą przy odstępie zera. Werdykt wyglądałby wtedy jak wynik pomiaru przy każdym
    pierwszym uruchomieniu — i byłby zawsze pozytywny.
    """
    podstaw(serwis_19(Odpowiedz(tresc=TRESC_19)))

    pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)

    wypisane = capsys.readouterr().out

    assert "pierwszy odczyt" in wypisane
    assert "stabilne" not in wypisane, (
        "pierwszy przebieg porównał się z własnym wierszem w dzienniku — odczyt wstecz "
        "wykonał się po żądaniu"
    )
    assert len(wiersze_dziennika()) == 1


@pytest.mark.parametrize(
    ("opis", "druga_tresc", "oczekiwany_werdykt"),
    [
        ("te same bajty", TRESC_19, "**bajty stabilne**"),
        ("bajty zmienione", TRESC_19_INNA, "**bajty NIESTABILNE**"),
    ],
)
def test_drugi_przebieg_po_dobie_rozstrzyga_przez_dziennik(
    opis: str,
    druga_tresc: bytes,
    oczekiwany_werdykt: str,
    podstaw: Callable[[Serwis], ZegarTestowy],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cały pomiar 19 od końca do końca, z dobą przesuniętą na zegarze zamiast przeczekanej.

    To jest jedyny test, który przechodzi przez **oba** przebiegi razem z plikiem między nimi.
    Wersje z osobna — zapis dziennika i odczyt wstecz — mają swoje asercje wyżej; dopiero ta
    mówi, że sonda uruchomiona dobę później wyda werdykt zamiast wypisać „pierwszy odczyt"
    po raz drugi.
    """
    serwis = serwis_19(Odpowiedz(tresc=TRESC_19), Odpowiedz(tresc=druga_tresc))
    zegar = podstaw(serwis)

    pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)
    capsys.readouterr()
    zegar.sleep(25 * 3600)
    pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)

    wypisane = capsys.readouterr().out

    assert oczekiwany_werdykt in wypisane, f"{opis}: {wypisane}"
    assert "25.0 h" in wypisane
    assert len(wiersze_dziennika()) == 2


def test_pomiar_19_ocenia_ksztalt_odpowiedzi(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Bez oceny kształtu strona bot-checka byłaby dla pomiaru 19 materiałem jak każdy inny —
    i to jest jego najgroźniejszy tryb cichej awarii, bo strona weryfikacji przeglądarki bywa
    **bitowo identyczna** między pobraniami. Dwa takie przebiegi dałyby zgodne skróty."""
    serwis = serwis_19(Odpowiedz(tresc=BOT_CHECK))
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)

    assert wyniki[0].ksztalt_zgodny is False
    assert wyniki[0].ksztalt_zrodlo, "ocena bez zapisanego źródła oczekiwania"


def test_pomiar_19_po_odmowie_nie_puka_w_korzen_hosta(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Zapis stanu, nie pochwała.

    `pomiar_atlas` i `pomiar_saos` po odmowie wysyłają jedno żądanie na korzeń, bo pytanie
    „punkt czy host" jest tam otwarte. Pomiar 19 tego nie robi i ma ku temu powód: punkt
    końcowy ma własny odczyt z datą (architektura 7), więc odmowa na nim jest zmianą wobec
    stanu znanego, a nie pierwszym kontaktem. Scenariusz nie przewiduje wpisu dla korzenia,
    więc żądanie kontrolne skończyłoby się `AssertionError`. Gdyby padło rozstrzygnięcie, że
    kontrola ma tu być, ten test jest miejscem, w którym zmiana staje się widoczna.
    """
    serwis = serwis_19(Odpowiedz(status=403, tresc=b"forbidden"))
    podstaw(serwis)

    wyniki = pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_UZP_TRESC)]
    assert len(wyniki) == 1
    assert wyniki[0].odmowa is True


def test_pomiar_19_zostawia_wiersz_w_dzienniku_takze_gdy_zadanie_nie_doszlo(
    podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Reguła zgody nie zna wyjątku dla żądań nieudanych, a werdykt ma to powiedzieć wprost."""
    podstaw(serwis_19(httpx.ConnectError("brak połączenia")))

    wyniki = pomiar_uzp.pomiar_stabilnosc(UA_TESTOWY)

    assert wyniki[0].status is None and wyniki[0].sha256 is None
    assert len(wiersze_dziennika()) == 1
    assert "zegar doby nie ruszył" in capsys.readouterr().out


# ------------------------------------------------------------------------------- znaleziska
#
# Cztery zachowania: jedno zamknięte tego samego dnia i trzy otwarte w pomiarze 19. Wszystkie
# zgłoszone jako `xfail(strict=True)` — asercja opisuje zachowanie oczekiwane, nie dzisiejsze —
# więc dzień poprawki kończy się czerwonym `XPASS` i zdjęciem znacznika, a nie cichym zielonym.
# Wzorzec sekcji przeniesiony z `tests/test_ratelimit.py`.
#
# **Wszystkie trzy zgłoszone 2026-09-17 i poprawione tego samego dnia**; znaczniki zdjęte, bo
# asercje opisują odtąd zachowanie dzisiejsze. Mechanizm zadziałał dokładnie tak, jak miał:
# poprawki zapaliły `XPASS(strict)` na czerwono i wymusiły świadome zdjęcie znacznika.
#
# Trzy miały wspólny kształt wart nazwania, bo to on decydował o ich wadze: żadna nie wywracała
# liczby żądań. Wszystkie trzy zmieniały **werdykt** — a werdykt pomiaru 19 jest wejściem
# ADR-0001, czyli decyzji o kluczu tożsamości dokumentu, przed którą nie wolno napisać
# `store.py` (`tests/test_bramki_faz.py`). Zła odpowiedź na to pytanie ma w tym projekcie
# zapisany koszt: mina 1, jedna noc, 2 681 żądań, zero użytecznych rekordów.
#
# Poprawki, dla śladu: `ocen_stabilnosc` odrzuca odpowiedź, dla której `Wynik.odmowa` jest
# prawdą; `_odstep_godzin` łapie także `TypeError` i odrzuca znacznik bez strefy;
# `wczesniejsze_odczyty` sortuje po znaczniku i przycina skrót przez `skrot_dziennika`.


@pytest.mark.parametrize(
    ("opis", "teraz"),
    [
        (
            "odmowa 403 — skrót strony błędu",
            wynik(adres=ADRES_19, status=403, bajtow=512, sha256="f" * 64),
        ),
        (
            "bot-check ze statusem 200 — skrót strony weryfikacji",
            wynik(adres=ADRES_19, status=200, bajtow=28_064, sha256="f" * 64, ksztalt_zgodny=False),
        ),
    ],
)
def test_werdykt_nie_oglasza_stabilnosci_bajtow_odpowiedzi_nie_do_poznania(
    opis: str, teraz: logbook.Wynik
) -> None:
    """Najcichsza z trzech i jedyna, która daje werdykt **pozytywny** bez żadnego pomiaru.

    `ocen_stabilnosc` odrzuca dziś dokładnie dwa stany: pomiar niewysłany i wynik bez `sha256`.
    Odpowiedź, która przyszła, ale nie jest treścią orzeczenia, przechodzi przez oba te sita:
    ma bajty, ma skrót, ma status. Strona odmowy i strona weryfikacji przeglądarki są przy tym
    **bitowo identyczne między pobraniami** znacznie częściej niż treść orzeczenia — statyczny
    szablon błędu nie ma się od czego zmienić. Dwa przebiegi w odstępie doby, oba zablokowane,
    dają więc zgodne skróty i werdykt:
    „**bajty stabilne** — `(doc_id, content_sha256)` może być kluczem, wpisz to do
    `docs/decisions.md` jako wejście ADR-0001".
    Zdanie prawdziwie wyglądające i fałszywe, czyli dokładnie to, przed czym ostrzega doktryna
    projektu (CLAUDE.md, zasada 7.1).

    Zmierzone 2026-09-17: `ocen_stabilnosc` z wynikiem 403 i zgodnym skrótem poprzednim wypisuje
    „**bajty stabilne** (odstęp 48.0 h)". Ta sama odpowiedź dla bot-checka ze statusem 200
    i `ksztalt_zgodny=False`.

    Cały mechanizm rozpoznania już w module jest i nie trzeba go budować: `Wynik.odmowa` łączy
    brak odpowiedzi, `KODY_ODMOWY` i niezgodny kształt w jedno pojęcie, i właśnie po to powstało.
    Lekarstwem jest dołożenie go do warunku wejścia `ocen_stabilnosc` razem z osobnym zdaniem
    dla operatora — „odpowiedź nie jest treścią orzeczenia, zegar doby nie ruszył" — bo werdykt
    milczący byłby drugą ciszą w miejscu pierwszej. Test celuje w zachowanie, nie w postać
    poprawki: żąda tylko, żeby przy takiej odpowiedzi nie padło słowo o stabilności.
    """
    werdykt = pomiar_uzp.ocen_stabilnosc(
        teraz, [odczyt("2023-11-12T22:13:20Z", "f" * 16)], ts_teraz="2023-11-14T22:13:20Z"
    )

    assert "stabiln" not in werdykt.lower(), (
        f"{opis}: werdykt o kluczu tożsamości wydany na odpowiedzi, która nie jest treścią "
        f"orzeczenia — {werdykt}"
    )


def test_znacznik_bez_godziny_daje_odstep_nieznany_a_nie_wyjatek() -> None:
    """Docstring `_odstep_godzin` obiecuje werdykt „odstęp nieznany" dla każdego znacznika nie
    do odczytania. Obietnica obejmuje jedną klasę mniej, niż mówi: `except ValueError`.

    `datetime.fromisoformat("2026-09-14")` **nie jest błędem** — od Pythona 3.11 zwraca
    poprawną datę bez strefy. Odejmowanie jej od znacznika przebiegu, który strefę ma,
    kończy się `TypeError`, a `TypeError` przez to `except` nie przechodzi. Zmierzone
    2026-09-17: `_odstep_godzin("2026-09-14", "2026-09-17T10:00:00Z")` →
    `TypeError: can't subtract offset-naive and offset-aware datetimes`.

    Droga do tego znacznika jest krótka i udokumentowana: nagłówek `docs/dziennik_zadan.md`
    każe dopisywać wpisy ręczne „w tych samych kolumnach, z `run_id` postaci `recznie-RRRRMMDD`",
    a kolumna `run_id` w tym samym wierszu niesie **samą datę**. Człowiek wpisujący wiersz ręką
    po odczycie `curl`-em ma wszelkie powody napisać w kolumnie `ts` to samo, co w `run_id`.
    Sam projekt takich odczytów już wykonał trzydzieści (przegląd 2026-09-14) plus pomiar 1.

    Skutek jest o klasę gorszy niż zwykły wyjątek, bo pada **po** żądaniu: `pomiar_stabilnosc`
    woła `ocen_stabilnosc` po powrocie z `wykonaj`, więc wywraca się `main` przed
    `zapisz_podsumowanie`. Wiersz dziennika przeżywa (dopisuje go `Kronika.zanotuj`), ale
    operator dostaje ślad stosu zamiast zdania — czyli dokładnie to, czego zakazuje obsługa
    `KioError` w `main`. Do tego pomiar jest odtąd zablokowany na zawsze: każdy kolejny przebieg
    czyta ten sam wiersz z dziennika i wywraca się w tym samym miejscu.

    Ta sama klasa awarii została w tej sesji zamknięta dwa razy — `replace` zamiast `format`
    w nagłówku dziennika i sprawdzenie ASCII przy budowie `html_z_fragmentami`. Obie poprawki
    mają w docstringu to samo zdanie: wyjątek po wysłaniu żądania kasuje ślad po ruchu, za
    który cudzy serwer już zapłacił.

    Lekarstwem jest rozszerzenie przechwytywania na `TypeError` albo domknięcie strefy przed
    odejmowaniem; test celuje w zachowanie, nie w postać poprawki.
    """
    assert pomiar_uzp._odstep_godzin("2026-09-14", "2026-09-17T10:00:00Z") is None


def test_odczyty_wsteczne_wracaja_od_najstarszego_takze_gdy_plik_mowi_inaczej() -> None:
    """`wczesniejsze_odczyty` deklaruje „najstarszy pierwszy", a zwraca kolejność **pliku**.

    Dopóki wiersze pisze sama sonda, to jest to samo: dopisuje je na końcu, rosnąco w czasie.
    Przestaje być tym samym przy pierwszym wpisie ręcznym, bo nagłówek dziennika ma **dwie**
    tabele i tabela „Wpisy ręczne" stoi fizycznie **nad** maszynową. Wpis ręczny dodany dziś
    ląduje więc przed maszynowymi sprzed tygodnia, a `ocen_stabilnosc` bierze `wczesniej[-1]`
    jako „poprzedni odczyt".

    Skutki są dwa i oba są werdyktem, nie awarią:

    - porównanie idzie z odczytem **nie tym**, co ostatni — czyli gubi zmianę, która zaszła
      po nim, a to jest ten kształt niestabilności, który wygląda jak stabilność;
    - `_odstep_godzin` dostaje znaczniki w odwrotnej kolejności i zwraca liczbę **ujemną**.
      Werdykt brzmi wtedy „za wcześnie: od poprzedniego odczytu minęło -168.0 h" — zdanie,
      którego operator nie ma jak zinterpretować, i blokada rozstrzygnięcia przy materiale,
      który je zawiera.

    Zmierzone 2026-09-17 na dzienniku z wpisem ręcznym z 2023-11-20 w tabeli ręcznej i wpisem
    maszynowym z 2023-11-13 w maszynowej.

    Lekarstwem jest posortowanie wyniku po `ts` — z wierszami o znaczniku nie do odczytania na
    końcu albo na początku, byle rozstrzygnięcie było zapisane. Test celuje w zachowanie:
    żąda, żeby zwrócona kolejność zgadzała się ze znacznikami, a nie z układem pliku.
    """
    dziennik_z_wierszami(wiersz_reczny(ADRES_19, "2023-11-20T09:00:00Z", "n" * 16))
    logbook.dopisz_dziennik(
        zadanie.DZIENNIK,
        "sonda-1",
        "2023-11-13T09:00:00Z",
        [wynik(adres=ADRES_19, sha256="s" * 64)],
    )

    odczytane = pomiar_uzp.wczesniejsze_odczyty(ADRES_19, dziennik=zadanie.DZIENNIK)

    assert [o.ts for o in odczytane] == sorted(o.ts for o in odczytane), (
        f"odczyty wróciły w kolejności pliku, nie znaczników: {[o.ts for o in odczytane]}"
    )
    assert odczytane[-1].skrot == "n" * 16, "najnowszym odczytem jest wpis ręczny z 2023-11-20"
