"""Strażnik śladu przebiegu — `kio_tool/logbook.py`.

Do 2026-09-18 te testy stały w `tests/test_sonda.py`; przeniosły się razem z kodem, bez zmiany
ani jednej asercji poza ścieżkami, które od tego dnia idą jawnie zamiast przez global modułu.
Każda własność sprawdzana tu ma tę cechę, o którą pyta zasada 7.3: naruszona, nie wypisuje
**nic** — `mask_tokens` skreślone z wiersza dziennika, nazwa pliku skrócona do dnia, dziennik
dopisywany dopiero po całym pomiarze zostawiają suitę zieloną bez tego pliku.

Piaskownica (`_piaskownica` w `conftest.py`) obowiązuje tu jak wszędzie: prawdziwy dziennik
i `scripts/out/` są poza zasięgiem i porównywane przed testem i po nim. Materiał i kształt
atrapy opisuje nagłówek `wsparcie_sondy.py`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

# Moduły sondy mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import pomiar_saos
import pomiar_uzp
import pytest
import zadanie

from kio_tool import logbook
from kio_tool.config import register_secret
from tests.wsparcie_sondy import (
    KLUCZ_TESTOWY,
    PRAWDZIWE_WYJSCIE,
    SAOS_DUMP_OK,
    SCIEZKA_SAOS,
    UA_TESTOWY,
    UZP_DETAILS_OK,
    UZP_WYNIKI_OK,
    Odpowiedz,
    Serwis,
    ZegarTestowy,
    uzp_scenariusz,
    wiersze_dziennika,
    wynik,
)

# --- piaskownica: obserwator własnej fixture ----------------------------------------------


def test_piaskownica_przekierowuje_zapis_poza_drzewo_repozytorium(tmp_path: Path) -> None:
    """Fixture wyżej sprawdza, że prawdziwe ścieżki się nie ruszyły. Ten test sprawdza drugą
    połowę tego samego zdania: że zapis w ogóle gdzieś trafia, więc zielony wynik reszty pliku
    nie bierze się z tego, że sonda nic nie zapisała."""
    sciezka = logbook.zapisz_surowe(
        zadanie.KATALOG_WYJSCIA, "probny", "20231114T221320Z", b"tresc", "html"
    )

    assert sciezka.read_bytes() == b"tresc"
    assert tmp_path in sciezka.parents
    assert PRAWDZIWE_WYJSCIE not in sciezka.parents


# --- `Wynik.odmowa`: co liczy się jako odmowa ----------------------------------------------


@pytest.mark.parametrize("kod", sorted(logbook.KODY_ODMOWY))
def test_kod_odmowy_jest_odmowa(kod: int) -> None:
    """Parametryzacja chodzi po **zbiorze z produkcji**, a nie po liście przepisanej ręcznie:
    kod usunięty ze zbioru ma zniknąć razem z testem, a nie zostawić test, który nic nie
    sprawdza."""
    assert wynik(status=kod).odmowa is True


def test_zadanie_ktore_nie_doszlo_do_skutku_jest_odmowa() -> None:
    """Brak statusu znaczy „nie wiadomo, czy host w ogóle rozmawia" — a to jest dokładnie ten
    stan, dla którego kontrola na korzeniu hosta ma sens (pomiar 1 i `ftp.gnu.org`)."""
    assert wynik(status=None).odmowa is True


def test_status_200_przy_ksztalcie_niezgodnym_jest_odmowa() -> None:
    """Strona bot-checka odpowiada 200 i to jest cały powód, dla którego kształt wchodzi do
    `odmowa`. Bez tego członu sonda uznałaby ją za sukces i nie zapytałaby, czy odmawia
    punkt, czy host."""
    assert wynik(status=200, ksztalt_zgodny=False).odmowa is True


def test_status_200_przy_ksztalcie_zgodnym_nie_jest_odmowa() -> None:
    assert wynik(status=200, ksztalt_zgodny=True).odmowa is False


def test_status_200_bez_oceny_ksztaltu_nie_jest_odmowa() -> None:
    """Kontrola hosta jedzie bez oczekiwania kształtu — korzeń serwisu nie ma kontraktu.
    Gdyby brak oceny liczył się jak ocena negatywna, każda kontrola byłaby odmową."""
    assert wynik(status=200, ksztalt_zgodny=None).odmowa is False


@pytest.mark.parametrize("kod", [500, 502, 503])
def test_awaria_serwisu_nie_jest_odmowa(kod: int) -> None:
    """5xx celowo nie stoi w `KODY_ODMOWY` i to jest rozstrzygnięcie zapisane przy zbiorze.

    Awaria po stronie serwisu prowadzi do innego wniosku niż odmowa: pierwsza powtarza się za
    jakiś czas, druga wymaga pisma albo klucza. Dopisanie 5xx do zbioru zamieniłoby chwilową
    awarię w wniosek „kanał zamknięty", a przy UZP dodatkowo zatrzymałoby grupę pomiarów.
    """
    assert wynik(status=kod).odmowa is False


# --- `Wynik.wiersz`: co zobaczy operator ---------------------------------------------------


def test_wiersz_krzyczy_gdy_ksztalt_sie_nie_zgadza() -> None:
    """Cisza jest usterką (7.2): niezgodność kształtu ma być widoczna w przelocie po ekranie,
    a nie dopiero po przeczytaniu uwagi."""
    linie = wynik(
        status=200,
        ksztalt_zgodny=False,
        ksztalt_uwaga="brak 'resultCounts'",
        ksztalt_zrodlo="kontrakt z drugiej ręki",
    ).wiersz()

    assert "KSZTAŁT NIEZGODNY" in linie
    assert "brak 'resultCounts'" in linie
    assert "kontrakt z drugiej ręki" in linie, (
        "wiersz nie niesie źródła oczekiwania — czytający nie odróżni „kontrakt się zmienił” "
        "od „nigdy taki nie był”"
    )


def test_wiersz_przy_ksztalcie_zgodnym_tez_mowi_co_przyszlo() -> None:
    linie = wynik(
        status=200, ksztalt_zgodny=True, ksztalt_uwaga="obecne: resultCounts", ksztalt_zrodlo="x"
    ).wiersz()

    assert "kształt OK" in linie
    assert "KSZTAŁT NIEZGODNY" not in linie


def test_wiersz_bez_oceny_ksztaltu_nie_udaje_ze_ocena_byla() -> None:
    """Kontrola hosta nie ma kontraktu, więc wiersz nie ma prawa wypisać ani „kształt OK",
    ani jego zaprzeczenia — brak oceny jest stanem trzecim, nie milczącym sukcesem."""
    linie = wynik(status=200).wiersz()

    assert "kształt" not in linie.lower()


def test_wiersz_niesie_skrot_odpowiedzi_i_nazwe_pliku() -> None:
    """Skrót wiąże wiersz na ekranie z bajtami w `scripts/out/` — katalogiem spoza historii."""
    linie = wynik(sha256="a" * 64, plik=Path("out/przyklad_20231114T221320Z.html")).wiersz()

    assert "aaaaaaaaaaaa" in linie
    assert "przyklad_20231114T221320Z.html" in linie


def test_wiersz_bledu_transportu_nie_udaje_statusu() -> None:
    assert "BŁĄD" in wynik(status=None, uwaga="ConnectTimeout: ...").wiersz()


# --- dowód się nie nadpisuje ---------------------------------------------------------------


def test_wolna_sciezka_w_pustym_katalogu_jest_nazwa_podstawowa(tmp_path: Path) -> None:
    assert logbook.wolna_sciezka(tmp_path, "rdzen", "json").name == "rdzen.json"


def test_wolna_sciezka_omija_kazdy_zajety_numer(tmp_path: Path) -> None:
    """Trzeci przebieg tej samej sekundy dostaje trzecią nazwę, nie drugą po raz drugi."""
    (tmp_path / "rdzen.json").write_text("pierwszy")
    (tmp_path / "rdzen_2.json").write_text("drugi")

    assert logbook.wolna_sciezka(tmp_path, "rdzen", "json").name == "rdzen_3.json"


def test_drugi_zapis_w_tej_samej_sekundzie_nie_gubi_pierwszej_odpowiedzi() -> None:
    """Własność 7 utwardzenia. Nazwa z dokładnością do dnia gubiła pierwszą odpowiedź przy
    dwóch przebiegach tego samego dnia; ta asercja chodzi po wersji ostrzejszej — ta sama
    sekunda — bo to ona pilnuje, żeby reakcją na zderzenie nie było nadpisanie.

    Za każdą z tych odpowiedzi cudzy serwer już zapłacił pracą. `decisions.md` mówi wprost:
    „wpis nie jest usuwany — dopisuje się nowy".
    """
    pierwszy = logbook.zapisz_surowe(
        zadanie.KATALOG_WYJSCIA, "uzp_4b", "20231114T221320Z", b"pierwsza odpowiedz", "html"
    )
    drugi = logbook.zapisz_surowe(
        zadanie.KATALOG_WYJSCIA, "uzp_4b", "20231114T221320Z", b"druga odpowiedz", "html"
    )

    assert pierwszy != drugi
    assert pierwszy.read_bytes() == b"pierwsza odpowiedz", "pierwsza odpowiedź została nadpisana"
    assert drugi.read_bytes() == b"druga odpowiedz"


def test_drugie_podsumowanie_tego_samego_przebiegu_nie_nadpisuje_pierwszego() -> None:
    """To samo zdanie dla podsumowania: `run_id` niesie znacznik co do sekundy, ale zderzenie
    nazw ma kończyć się drugim plikiem, a nie utratą pierwszego."""
    pierwsze = logbook.zapisz_podsumowanie(
        zadanie.KATALOG_WYJSCIA, "atlas", "sonda-20231114T221320Z", "ts", [wynik()]
    )
    drugie = logbook.zapisz_podsumowanie(
        zadanie.KATALOG_WYJSCIA, "atlas", "sonda-20231114T221320Z", "ts", [wynik(nazwa="inny")]
    )

    assert pierwsze != drugie
    assert json.loads(pierwsze.read_text(encoding="utf-8"))["zadania"][0]["nazwa"] == "przyklad"
    assert json.loads(drugie.read_text(encoding="utf-8"))["zadania"][0]["nazwa"] == "inny"


# --- podsumowanie: co zostaje po przebiegu -------------------------------------------------


def test_podsumowanie_niesie_skrot_i_status_dowodowy_oczekiwania() -> None:
    """Skrót wiąże zapis z bajtami, a źródło oczekiwania mówi, ile znaczy ocena kształtu.
    Bez obu podsumowanie jest zdaniem „zmierzone, N żądań" bez niczego pod spodem."""
    sciezka = logbook.zapisz_podsumowanie(
        zadanie.KATALOG_WYJSCIA,
        "uzp-getresults",
        "sonda-20231114T221320Z",
        "2023-11-14T22:13:20Z",
        [wynik(sha256="b" * 64, ksztalt_zgodny=False, ksztalt_zrodlo="dwa cudze kolektory")],
    )

    zapis = json.loads(sciezka.read_text(encoding="utf-8"))["zadania"][0]

    assert zapis["sha256"] == "b" * 64
    assert zapis["ksztalt_zgodny"] is False
    assert zapis["ksztalt_zrodlo"] == "dwa cudze kolektory"


def test_podsumowanie_maskuje_sekret_w_adresie() -> None:
    """`requests_log` trzyma `url_redacted`, nie `url` — a podsumowanie jest dziś jego
    namiastką razem z dziennikiem. Klucz w zapytaniu nie ma prawa wylądować na dysku."""
    klucz = "sekretny-klucz-atlasu"
    register_secret(klucz)

    sciezka = logbook.zapisz_podsumowanie(
        zadanie.KATALOG_WYJSCIA,
        "atlas",
        "run",
        "ts",
        [wynik(adres=f"https://atlasprzetargow.pl/api/kio?key={klucz}")],
    )

    tresc = sciezka.read_text(encoding="utf-8")

    assert klucz not in tresc
    assert "<token>" in tresc


# --- dziennik żądań ------------------------------------------------------------------------


def test_pierwszy_wpis_zaklada_dziennik_razem_z_naglowkiem() -> None:
    """Dziennik jest **w historii repozytorium** i ma kolumny `requests_log` (model 4.4).
    Plik bez nagłówka byłby tabelą, której nikt nie umie przeczytać."""
    logbook.dopisz_dziennik(zadanie.DZIENNIK, "sonda-1", "2023-11-14T22:13:20Z", [wynik()])

    tresc = zadanie.DZIENNIK.read_text(encoding="utf-8")

    assert tresc.startswith("# Dziennik żądań")
    assert "| run_id | ts | metoda |" in tresc


def test_kolejny_przebieg_dopisuje_i_nie_przepisuje_naglowka() -> None:
    """„Dopisywany przy każdym przebiegu, nigdy przepisywany" — tak mówi sam nagłówek pliku.

    Drugi nagłówek w środku tabeli jest tą postacią usterki, która nie psuje żadnego testu
    i psuje każdy odczyt.
    """
    logbook.dopisz_dziennik(zadanie.DZIENNIK, "sonda-1", "ts", [wynik()])
    logbook.dopisz_dziennik(zadanie.DZIENNIK, "sonda-2", "ts", [wynik(), wynik(nazwa="drugie")])

    tresc = zadanie.DZIENNIK.read_text(encoding="utf-8")

    assert tresc.count("# Dziennik żądań") == 1
    assert tresc.count("| sonda-1 |") == 1
    assert tresc.count("| sonda-2 |") == 2


def test_wiersz_dziennika_maskuje_sekret_w_adresie() -> None:
    """Jedyny plik tej sondy, który idzie do historii repozytorium. Klucz dopisany tu raz
    zostaje tam na zawsze — stąd `mask_tokens` na ścieżce, a nie sam `url`."""
    klucz = "sekretny-klucz-atlasu"
    register_secret(klucz)

    wiersz = logbook.wiersz_dziennika(
        "sonda-1", wynik(adres=f"https://atlasprzetargow.pl/api/kio?key={klucz}"), "ts"
    )

    assert klucz not in wiersz, "sekret trafił do pliku wersjonowanego w repozytorium"
    assert "<token>" in wiersz


def test_wiersz_dziennika_zaznacza_ksztalt_niezgodny() -> None:
    """Status 200 przy kształcie niezgodnym jest przypadkiem, dla którego reguła 17 istnieje —
    i właśnie on ma być widoczny w tabeli, a nie rozpłynąć się w kolumnie ze statusem."""
    wiersz = logbook.wiersz_dziennika("sonda-1", wynik(status=200, ksztalt_zgodny=False), "ts")

    assert "NIEZGODNY" in wiersz
    assert "| 200 |" in wiersz


def test_wiersz_dziennika_bez_oceny_ksztaltu_nie_zmyśla_oceny() -> None:
    wiersz = logbook.wiersz_dziennika("sonda-1", wynik(status=200), "ts")

    assert "| — |" in wiersz
    assert "NIEZGODNY" not in wiersz and "zgodny" not in wiersz


def test_wiersz_dziennika_wiaze_zapis_ze_skrotem_odpowiedzi() -> None:
    """Zdanie „zmierzone {data}, N żądań" wskazywało na plik spoza historii. Skrót jest
    jedynym, co wiąże wiersz w historii z bajtami w `scripts/out/`."""
    wiersz = logbook.wiersz_dziennika("sonda-1", wynik(sha256="c" * 64), "ts")

    assert "`" + "c" * 16 + "`" in wiersz


def test_wiersz_dziennika_niesie_czas_w_milisekundach() -> None:
    assert "| 250 |" in logbook.wiersz_dziennika("sonda-1", wynik(czas_s=0.25), "ts")


# --- Kronika: ślad powstaje w chwili powrotu żądania ---------------------------------------


def kronika_testowa(run_id: str = "sonda-1", ts: str = "2023-11-14T22:13:20Z") -> logbook.Kronika:
    """Kronika ze ścieżkami z piaskownicy — te same, które podstawia fixture w `conftest.py`."""
    return logbook.Kronika(
        run_id, ts, dziennik=zadanie.DZIENNIK, katalog_wyjscia=zadanie.KATALOG_WYJSCIA
    )


def test_kronika_bierze_znacznik_przebiegu_z_podanego_zegara() -> None:
    """`run_id` wiąże wiersze dziennika, nazwę podsumowania i wydruk w jeden przebieg.
    Wzięty z zegara, a nie składany w trzech miejscach — inaczej „ten sam przebieg" byłby
    zdaniem o zamiarze, nie o danych.

    Zegar jest **parametrem** `na_teraz` (od 2026-09-18), więc test podaje go wprost — bez
    podstawiania czegokolwiek w module. Że sonda podaje tu zegar ze swojej fabryki, sprawdza
    osobno `test_zadanie.py`.
    """
    kronika = logbook.Kronika.na_teraz(
        ZegarTestowy(), dziennik=zadanie.DZIENNIK, katalog_wyjscia=zadanie.KATALOG_WYJSCIA
    )

    assert kronika.ts == "2023-11-14T22:13:20Z"
    assert kronika.run_id == "sonda-20231114T221320Z"
    assert kronika.dziennik == zadanie.DZIENNIK
    assert kronika.katalog_wyjscia == zadanie.KATALOG_WYJSCIA


def test_kronika_wymaga_sciezek_jawnie() -> None:
    """Ścieżki są polami bez wartości domyślnej — kronika bez nich nie powstaje.

    Wartość domyślna wskazująca na `scripts/out/` albo `docs/dziennik_zadan.md` przywróciłaby
    global tylnymi drzwiami: test, który zapomniał podać ścieżkę, pisałby do prawdziwego
    dziennika i piaskownica zobaczyłaby to dopiero po fakcie. Bez domyślnej brak ścieżki jest
    `TypeError` przy budowie, czyli zanim cokolwiek trafi na dysk.
    """
    with pytest.raises(TypeError):
        logbook.Kronika("sonda-1", "ts")  # type: ignore[call-arg]


def test_kronika_wypisuje_przez_wstrzykniete_ujscie() -> None:
    """`wypisz` jest polem, nie `print`-em wpisanym na sztywno.

    Bez tego pola `logbook` musiałby wybrać między `print` a `rich` — a reguła 7 mówi, że
    biblioteki ekranu nie zna. Test podaje listę i sprawdza, że wiersz trafił **tam**, a nie
    na `stdout`; przy okazji: dziennik dostał swój wiersz niezależnie od ujścia druku.
    """
    zebrane: list[str] = []
    kronika = logbook.Kronika(
        "sonda-1",
        "2023-11-14T22:13:20Z",
        dziennik=zadanie.DZIENNIK,
        katalog_wyjscia=zadanie.KATALOG_WYJSCIA,
        wypisz=zebrane.append,
    )

    kronika.zanotuj(wynik(nazwa="probny"))

    assert len(zebrane) == 1 and "probny" in zebrane[0]
    assert zadanie.DZIENNIK.read_text(encoding="utf-8").count("| sonda-1 |") == 1


def test_kronika_zapisuje_wynik_od_razu_i_zwraca_go_dalej(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`zanotuj` jest przezroczysta dla wywołującego: zwraca ten sam obiekt, który dostała.

    Gdyby zwracała kopię albo `None`, `wykonaj` przestałby budować listę wyników i pomiar
    wracałby pusty — więc ta asercja trzyma szew, na którym stoi cała przebudowa.
    """
    dany = wynik(nazwa="probny")

    zwrocony = kronika_testowa().zanotuj(dany)

    assert zwrocony is dany
    assert "probny" in capsys.readouterr().out
    assert zadanie.DZIENNIK.read_text(encoding="utf-8").count("| sonda-1 |") == 1


def test_wiersz_dziennika_powstaje_po_kazdym_zadaniu_z_osobna(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Dziennik rośnie w trakcie przebiegu, a nie po nim — i to jest widoczne w kolejności.

    Wiersze mają stać w kolejności wysłania, bo dziennik jest dowodem tempa tak samo jak
    treści: „trzy żądania w tej samej sekundzie" i „trzy żądania co dwie sekundy" to dwa
    różne zdania wobec cudzego serwera.
    """
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(tresc=UZP_WYNIKI_OK))
    podstaw(serwis)

    pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    wiersze = wiersze_dziennika()

    assert len(wiersze) == 3
    assert "Details/9620" in wiersze[0]
    assert all("GetResults" in w for w in wiersze[1:])


@pytest.mark.parametrize(
    ("opis", "awaria"),
    [
        ("wyjątek spoza httpx", RuntimeError("brak miejsca na dysku")),
        ("przerwanie z klawiatury", KeyboardInterrupt()),
    ],
)
def test_slad_po_zadaniach_ktore_juz_poszly_przezywa_awarie_w_srodku_grupy(
    opis: str, awaria: BaseException, podstaw: Callable[[Serwis], ZegarTestowy]
) -> None:
    """Sedno `Kroniki` i jedyny powód, dla którego zapis przeniósł się z końca pomiaru.

    Przed przeglądem 2026-09-17 wiersze żyły w lokalnej liście do powrotu z całego pomiaru,
    więc dowolny wyjątek w środku — `LimiterStalledError`, `UntrustedLinkError`, pełny dysk
    w `zapisz_surowe`, `Ctrl+C` w czasie blokady po 429 — kasował zapis **wszystkich** żądań, które
    już poszły do cudzego serwisu. Reguła zgody mówi, że odczyt diagnostyczny zawsze zostawia
    wpis w dzienniku; przebieg przerwany nie zostawiał żadnego, więc jedyny ślad po ruchu
    wysłanym w cudzą stronę był po tamtej stronie.

    Awaria jest tu spoza `httpx.HTTPError` celowo: błędy transportu `wykonaj` łapie i zamienia
    w wynik, więc nie pokazałyby tej różnicy. `KeyboardInterrupt` sprawdza przy okazji, że
    `except httpx.HTTPError` go nie połyka.
    """
    serwis = Serwis({SCIEZKA_SAOS: [Odpowiedz(tresc=SAOS_DUMP_OK), awaria]})
    podstaw(serwis)

    with pytest.raises(type(awaria)):
        pomiar_saos.pomiar_saos(UA_TESTOWY)

    wiersze = wiersze_dziennika()

    assert len(wiersze) == 1, (
        f"{opis}: po przerwanym przebiegu w dzienniku jest {len(wiersze)} wierszy zamiast "
        "jednego — żądanie, które poszło do cudzego serwisu, nie zostawiło śladu"
    )
    assert "dump/judgments" in wiersze[0]


def test_naglowek_dziennika_niesie_date_przebiegu_ktory_go_zalozyl() -> None:
    """Data z przebiegu, nie z dnia napisania kodu — inaczej byłaby liczbą bez pokrycia
    w pliku, który powstał po to, żeby zasady 7.1 pilnować."""
    logbook.dopisz_dziennik(zadanie.DZIENNIK, "sonda-1", "2023-11-14T22:13:20Z", [wynik()])

    assert "Data utworzenia: 2023-11-14" in zadanie.DZIENNIK.read_text(encoding="utf-8")


def test_nawias_klamrowy_w_naglowku_nie_wywraca_zakladania_dziennika(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nagłówek składa się `replace`, a nie `format`, i to jest różnica między „dziennik
    powstał" a `KeyError` w pliku, który istnieje po to, żeby ślad nie ginął.

    Zagrożenie nie jest hipotetyczne i nie leży w wierszach danych — te idą do pliku bez
    składania. Leży w samym nagłówku: to dwadzieścia linijek markdownu **opisujących format
    zapisu**, a formatem, który ten plik opisuje, jest „zmierzone {data}, {N} żądań" — zdanie
    z nawiasem klamrowym, które `main` już dziś drukuje. Pierwszy taki przykład dopisany do
    nagłówka wywraca `format` na `KeyError`.

    Dlatego test podstawia nagłówek z drugim miejscem w nawiasach, zamiast liczyć na to, że
    dzisiejsza treść stałej go zawiera: sprawdzamy sposób składania, a nie dzisiejszy napis.
    """
    naglowek_z_przykladem = """# Dziennik żądań

Data utworzenia: {data}

Wynik zapisuje się jako „zmierzone {data}, {N} żądań”.

| run_id | ts |
|---|---|
"""
    monkeypatch.setattr(logbook, "NAGLOWEK_DZIENNIKA", naglowek_z_przykladem)

    logbook.dopisz_dziennik(zadanie.DZIENNIK, "sonda-1", "2023-11-14T22:13:20Z", [wynik()])

    tresc = zadanie.DZIENNIK.read_text(encoding="utf-8")

    assert "Data utworzenia: 2023-11-14" in tresc
    assert "{N} żądań" in tresc, "przykład formatu został zjedzony przez składanie nagłówka"
    assert tresc.count("| sonda-1 |") == 1


# --- pomiar niewysłany: jawny wpis zamiast zniknięcia --------------------------------------


def test_niewyslany_jest_wynikiem_a_nie_brakiem_wyniku() -> None:
    """Pole `wyslane` jest jawne, a nie rozpoznawane po napisie w `adres`.

    Rozpoznawanie po napisie znaczyłoby, że odpowiedź niosąca gdzieś tekst „(niewysłane)"
    zmienia rachunek żądań — a ten rachunek jest warunkiem zamknięcia bramki fazy 0.
    """
    pominiety = logbook.niewyslany("uzp_16_resultcounts", "POST", "pomiar przerwany: 403")

    assert pominiety.wyslane is False
    assert pominiety.status is None and pominiety.bajtow == 0 and pominiety.plik is None
    assert pominiety.sha256 is None
    assert "403" in pominiety.uwaga


def test_wiersz_niewyslanego_nie_udaje_zmierzonego_zera() -> None:
    """Wiersz pomiaru, który nie poszedł, nie ma prawa wyglądać jak odpowiedź o rozmiarze 0 B.

    „0 B w 0,00 s" jest zdaniem o zmierzonej odpowiedzi; brak żądania jest zdaniem o tym, że
    nie ma czego mierzyć. Ta sama kolumna dla obu zamieniałaby jedno w drugie przy przepisaniu
    wyniku do `decisions.md`.
    """
    linie = logbook.niewyslany("uzp_16_resultcounts", "POST", "pomiar przerwany: 429").wiersz()

    assert "(niewysłane)" in linie
    assert "pomiar przerwany: 429" in linie
    assert " B " not in linie and "0.00s" not in linie


def test_wiersz_dziennika_niewyslanego_ma_przedrostek_i_nie_liczy_sie_do_n() -> None:
    """Przedrostek `nie:` jest tym, co pozwala policzyć N z samego dziennika.

    Wiersz jest, bo zniknięcie pomiaru jest ciszą. Przedrostek jest, bo „ślad po każdym
    żądaniu" nie może obejmować czegoś, co żądaniem nie było — a `decisions.md` wymaga
    dokładnego „zmierzone {data}, N żądań".
    """
    wiersz = logbook.wiersz_dziennika(
        "sonda-1", logbook.niewyslany("uzp_16_resultcounts", "POST", "pomiar przerwany"), "ts"
    )

    assert "| nie:POST |" in wiersz
    assert "(niewysłane)" in wiersz
    assert "pomiar przerwany" in wiersz
    assert "| POST |" not in wiersz, "wiersz niewysłany daje się policzyć jako wysłany"


def test_podsumowanie_odroznia_pomiar_wyslany_od_niewyslanego() -> None:
    """Rozróżnienie ma przeżyć drogę na dysk: `podsumowanie_*.json` jest tym, co czyta się
    po tygodniu, gdy ekranu już nie ma."""
    sciezka = logbook.zapisz_podsumowanie(
        zadanie.KATALOG_WYJSCIA,
        "uzp-getresults",
        "sonda-1",
        "ts",
        [wynik(nazwa="poszlo"), logbook.niewyslany("nie_poszlo", "POST", "przerwane")],
    )

    zadania = json.loads(sciezka.read_text(encoding="utf-8"))["zadania"]

    assert [z["wyslane"] for z in zadania] == [True, False]


# --- `odmowa` wobec `odmowa_serwisu` -------------------------------------------------------


@pytest.mark.parametrize("kod", sorted(logbook.KODY_ODMOWY))
def test_kod_odmowy_jest_odmowa_serwisu(kod: int) -> None:
    assert wynik(status=kod).odmowa_serwisu is True


def test_brak_odpowiedzi_jest_odmowa_serwisu() -> None:
    assert wynik(status=None).odmowa_serwisu is True


@pytest.mark.parametrize("kod", [200, 404, 500, 503])
def test_serwis_ktory_odpowiedzial_nie_odmowil(kod: int) -> None:
    """Węższe pytanie zadaje się serwisowi, a nie kontraktowi: 404 i 503 są odpowiedziami,
    nie odmowami, więc nie mają prawa zatrzymać grupy pomiarów."""
    assert wynik(status=kod).odmowa_serwisu is False


def test_niezgodny_ksztalt_jest_odmowa_ale_nie_odmowa_serwisu() -> None:
    """Jedna asercja trzyma obie własności naraz, bo to ich **różnica** jest tu treścią.

    Przy UZP kształt nie do poznania zatrzymuje grupę: znany-dobry odczyt wrócił nie taki,
    więc serwis nie rozmawia z tym klientem. Przy SAOS ten sam kształt jest **wynikiem
    pomiaru** — dwie sprzeczne pisownie parametru dat po to tam są, żeby sprawdzić, która
    działa, a zła objawi się najpewniej odpowiedzią 200 o innym kształcie. Zlanie obu pojęć
    w jedno kasuje drugą próbę dokładnie w chwili, w której pomiar zaczyna coś mierzyć.
    """
    bot_check = wynik(status=200, ksztalt_zgodny=False)

    assert bot_check.odmowa is True
    assert bot_check.odmowa_serwisu is False


def test_uwaga_o_przekierowaniu_tez_nie_ma_prawa_wynies_klucza_na_dysk() -> None:
    """Ta sama klasa luki, którą `OcenaKsztaltu.__post_init__` zamknął — o jedno pole obok.

    Zgłoszone 2026-09-17 jako `xfail(strict=True)` i poprawione tego samego dnia:
    `Wynik.__post_init__` maskuje `uwaga` **przy budowie**, więc zamyka oba ujścia naraz —
    podsumowanie na dysku i wiersz dziennika — a trzecie, które powstanie jutro, nie wymaga
    pamiętania o niczym. Znacznik zdjęty razem z poprawką.

    `zapisz_podsumowanie` przepuszcza `adres` przez `mask_tokens`, bo `requests_log` trzyma
    `url_redacted`. Pole `uwaga` z tego samego wyniku idzie do pliku **bez maskowania**,
    a niesie treść obcą dokładnie tak samo:

    - `przekierowanie → {Location}` — nagłówek cudzej odpowiedzi. Brak przekierowań jest tu
      decyzją operacyjną, a nie ostrożnością: `GET /Home/Move` w wyszukiwarce UZP **jest**
      przekierowaniem i adapter ma czytać `Location`. Adres w tym nagłówku bywa podpisany
      albo niesie klucz w zapytaniu.
    - `{type(blad).__name__}: {blad}` — komunikat wyjątku `httpx`, który potrafi wpisać w
      siebie adres żądania razem z zapytaniem.

    Zmierzone 2026-09-17: `zapisz_podsumowanie` z wynikiem, którego `uwaga` niesie adres
    z zarejestrowanym sekretem, zapisuje ten sekret do `podsumowanie_*.json` dosłownie.

    Ta sama pisownia stoi w `wiersz_dziennika` dla wiersza niewysłanego (`{wynik.uwaga}`
    w ostatniej kolumnie). Dziś niesie tam wyłącznie napis złożony przez samą sondę, więc nie
    jest luką — ale jest tym samym kształtem czekającym na pierwszą uwagę z cudzej treści.

    Wybrano drogę szczelniejszą: maskowanie `uwaga` przy budowie `Wynik`, tak jak
    `OcenaKsztaltu` robi to w `__post_init__`. Maskowanie przy ujściu zamykałoby tę lukę
    dwa razy i zostawiało otwartą każdą następną.
    """
    register_secret(KLUCZ_TESTOWY)
    z_kluczem = wynik(
        uwaga=f"przekierowanie → https://atlasprzetargow.pl/api/kio?key={KLUCZ_TESTOWY}"
    )

    sciezka = logbook.zapisz_podsumowanie(
        zadanie.KATALOG_WYJSCIA, "atlas", "sonda-1", "ts", [z_kluczem]
    )

    assert KLUCZ_TESTOWY not in sciezka.read_text(encoding="utf-8")


# --- znaki sterujące w uwadze: neutralizacja przy budowie, nie przy druku --------------------


def test_uwaga_wyniku_traci_znaki_sterujace_przy_budowie() -> None:
    """Przegląd kodu 2026-09-18: `Wynik.__post_init__` maskował sekret, ale nie neutralizował
    znaków sterujących, a `Kronika.zanotuj` drukuje `wiersz()` gołym `print` — `\\x1b[2J` z cudzego
    `Location` czyściłby operatorowi ekran razem z rachunkiem żądań. Poprawione tego samego dnia
    kolejnością `strip_control` → `mask_tokens`, tą samą co w `richtext.safe`."""
    register_secret(KLUCZ_TESTOWY)
    rozbity = KLUCZ_TESTOWY[:6] + "​" + KLUCZ_TESTOWY[6:]

    w = wynik(uwaga=f"przekierowanie → \x1b[2J‮https://x/?key={rozbity}")

    assert "\x1b" not in w.uwaga and "‮" not in w.uwaga
    assert KLUCZ_TESTOWY not in w.uwaga and "<token>" in w.uwaga, (
        "sekret rozbity znakiem zerowej szerokości przeszedł przez maskowanie — kolejność "
        "`strip_control` → `mask_tokens` jest odwrócona albo `strip_control` nie ma"
    )
    assert "\x1b" not in w.wiersz(), "wiersz na ekran niesie znak sterujący z cudzej odpowiedzi"
