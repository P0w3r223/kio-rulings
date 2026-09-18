"""Strażnik oceny kształtu — reguły 17: maszyneria w `kio_tool/ksztalt.py`, instancje obok.

Powód istnienia tego pliku jest datowany i stoi w nagłówku `kio_tool/ksztalt.py` (do
2026-09-18 w `scripts/ksztalty.py`): cudzy kolektor przez około dwa miesiące zwracał `total=0`
**ze statusem 200**, bo pusta lista jest poprawnym wynikiem zapytania i nic tego nie zauważyło.
Sonda jest dziś jedynym programem w tym projekcie, który cokolwiek wysyła na zewnątrz, więc
odpowiedź na pytanie zasady 7.3 („co by się wypisało, gdyby zabezpieczenie zostało
naruszone?") brzmi dla niej tyle, ile wart jest ten moduł: bez niego strona bot-checka
wypisałaby się jako `200, 28 064 B`.

Jeden plik na dwa moduły — celowo. Maszyneria (`kio_tool.ksztalt`) i oczekiwania sondy
(`scripts/ksztalty.py`) są testowane tym samym wymyślonym materiałem, a większość testów
maszynerii jedzie przez instancję (`ksztalty.SAOS_DUMP.ocen(...)`), bo to instancja mówi,
którą gałąź fabryki pomiar naprawdę woła. Rozbicie po module dublowałoby materiał i rozcinało
testy gałęzi między dwa pliki bez zysku w czytelności.

Dwa zdania tego pliku są rozstrzygnięciami z nagłówka `ksztalt.py`, a nie drobiazgami, więc
każde ma tu własny test i żadne nie jest wpisane ręcznie po jednym przykładzie:

- **ocena niesie uwagę także przy zgodności** — ocena milcząca przy powodzeniu mówi tylko
  „nie zapaliło się", a przy pomiarach 2a i 3a pytaniem jest „co właściwie przyszło";
- **każde oczekiwanie niesie swoje źródło** — „kontrakt z drugiej ręki" i „własny odczyt" to
  dwa różne statusy dowodowe (zasada 7.1) i dlatego stoją w typie, a nie w komentarzu.
  Test chodzi po **wszystkich** obiektach `Ksztalt` znalezionych w module, więc oczekiwanie
  dopisane jutro bez źródła zapala się samo.

Napisy udające odpowiedzi serwisów są w tym pliku **wymyślone** i tak mają być czytane.
Nie są dowodem kształtu źródła, nie mają daty odczytu i nie mają prawa trafić do
`tests/examples/` — tam idzie materiał przejrzany okiem razem z parą `*.compare.json`
(reguła 17). Sprawdzamy nimi skaner, a nie źródło; stąd też brak sygnatur wyglądających
na prawdziwe: napis `KIO 1234/25` wygląda tak samo niezależnie od tego, czy istnieje.

Ten plik nie dotyka ani sieci, ani dysku.
"""

from __future__ import annotations

import ksztalty
import pytest

from kio_tool import ksztalt
from kio_tool.config import register_secret
from kio_tool.safetext import strip_control

# --- materiał wymyślony, opisany w nagłówku ----------------------------------------------

BOT_CHECK = (
    b"<!DOCTYPE html><html><head><title>Weryfikacja przegladarki</title></head><body>"
    b"<noscript>Wlacz obsluge JavaScript, aby kontynuowac.</noscript>"
    b"<div id='challenge-running'>Sprawdzamy, czy polaczenie jest bezpieczne.</div>"
    b"</body></html>"
)
"""Strona, dla której ten moduł powstał: status 200, rozmiar wiarygodny, treść nie ta."""

WYNIKI_OK = (
    b'<html><body><div id="resultCounts">KIO: 12</div>'
    b'<div class="search-list-item"><a href="/Home/Move/1">pozycja</a></div></body></html>'
)

DETAILS_OK = b"<html><body><label>Sygnatura akt</label><span>(napis wymyslony)</span></body></html>"

CONTENT_OK = (
    "<html><body><h2>Uzasadnienie</h2>"
    "<p>Izba zważyła, co następuje (napis wymyślony).</p></body></html>"
).encode()
"""Treść orzeczenia w kształcie, o jaki pyta pomiar 19. Z ogonkami **w materiale**, choć
oczekiwanie jest ASCII — bo tak wygląda prawdziwa strona i to jest sedno: porównanie ma
działać na bajtach, które ogonki niosą, nie na wyidealizowanym napisie."""


def uwaga_z(ocena: ksztalt.OcenaKsztaltu) -> str:
    """Skrót do asercji na treści uwagi — czytelniejszy niż `ocena.uwaga` w każdej linii."""
    return ocena.uwaga


DOWOLNA_LISTA = ksztalt.json_z_rekordami()
"""Oczekiwanie bez nazwy listy — do testów samej fabryki. Do 2026-09-18 tę rolę pełniło
`ATLAS_LISTA`, które od tego dnia nazywa klucz `data` z dokumentacji odczytanej z datą."""

DOKUMENT_OK = (
    b'{"slug": "wymyslony-slug", "primary_signature": "(napis wymyslony)", '
    b'"content": "tresc wymyslona, najdluzsze pole"}'
)


# --- kształt HTML: obecność znaczników kontraktu -------------------------------------------


def test_strona_bot_checka_ze_statusem_200_nie_przechodzi_jako_lista_wynikow() -> None:
    """Sedno całego modułu: odpowiedź zgodna statusem, niezgodna kształtem.

    Gdyby ta asercja przestała obowiązywać, sonda wypisałaby stronę bot-checka jako sukces
    i pomiar 4b odpowiedziałby „kontrakt potwierdzony" na pytanie, którego nikt nie zadał.
    Uwaga ma nieść **oba** brakujące znaczniki i podgląd treści, bo operator ma poznać stronę
    po tym, co na niej jest, a nie po samym rozmiarze.
    """
    ocena = ksztalty.UZP_WYNIKI.ocen(BOT_CHECK)

    assert ocena.zgodny is False, "strona bot-checka przeszła jako lista wyników wyszukiwarki"
    assert "resultCounts" in uwaga_z(ocena)
    assert "search-list-item" in uwaga_z(ocena)
    assert "Weryfikacja przegladarki" in uwaga_z(ocena), (
        "uwaga nie niesie podglądu treści — operator dostaje sam rozmiar, czyli to samo, "
        "co miał przed wprowadzeniem oceny kształtu"
    )


def test_lista_wynikow_z_kompletem_znacznikow_jest_zgodna() -> None:
    ocena = ksztalty.UZP_WYNIKI.ocen(WYNIKI_OK)

    assert ocena.zgodny is True
    assert "resultCounts" in uwaga_z(ocena) and "search-list-item" in uwaga_z(ocena)


def test_brak_jednego_znacznika_wystarcza_do_niezgodnosci() -> None:
    """Uwaga wymienia znacznik brakujący, a nie obecny — inaczej nie mówi, czego szukać."""
    polowiczna = b'<html><div id="resultCounts">KIO: 0</div></html>'

    ocena = ksztalty.UZP_WYNIKI.ocen(polowiczna)

    assert ocena.zgodny is False
    assert "search-list-item" in uwaga_z(ocena)
    assert "'resultCounts'" not in uwaga_z(ocena), "uwaga wymienia znacznik, który **jest**"


def test_dopasowanie_znacznikow_nie_zalezy_od_wielkosci_liter() -> None:
    """Zmiana pisowni klasy CSS nie jest zmianą kontraktu — tak mówi nagłówek modułu."""
    inna_pisownia = b'<HTML><DIV ID="RESULTCOUNTS"></DIV><DIV CLASS="Search-List-Item"></DIV>'

    assert ksztalty.UZP_WYNIKI.ocen(inna_pisownia).zgodny is True


def test_metryka_dokumentu_ma_wlasne_oczekiwanie_niezalezne_od_listy_wynikow() -> None:
    """Znany-dobry odczyt z pomiaru UZP sprawdza `Details`, a nie listę wyników.

    Gdyby oba oczekiwania zlały się w jedno, kontrola przed ekspozycją mierzyłaby kształt
    strony, której nie odczytuje — i wracałaby niezgodnością przy każdym przebiegu.
    """
    assert ksztalty.UZP_DETAILS.ocen(DETAILS_OK).zgodny is True
    assert ksztalty.UZP_DETAILS.ocen(WYNIKI_OK).zgodny is False


# --- UZP_CONTENT: oczekiwanie pomiaru 19 ---------------------------------------------------
#
# Trzy punkty UZP mają trzy różne kształty i to jest cała treść tej sekcji. Pomiar 19 pyta
# o **bajty** treści orzeczenia, a jego werdykt jest wejściem ADR-0001; odpowiedź, która treścią
# nie jest, ma zostać rozpoznana **zanim** jej skrót wejdzie do porównania. Strona bot-checka
# bywa przy tym bitowo identyczna między pobraniami częściej niż orzeczenie, więc bez tego
# oczekiwania dwa zablokowane przebiegi wyglądałyby jak dowód stabilności.


def test_tresc_orzeczenia_z_naglowkami_sekcji_jest_zgodna() -> None:
    """Materiał z ogonkami, oczekiwanie z samego ASCII — i to ma się spotkać.

    Fragmenty są przycięte (`Izba` zamiast `Izba zważyła`) właśnie po to, żeby porównanie nie
    zależało od kodowania strony, którego nikt w tym projekcie jeszcze nie zmierzył.
    """
    ocena = ksztalty.UZP_CONTENT.ocen(CONTENT_OK)

    assert ocena.zgodny is True, uwaga_z(ocena)
    assert "Uzasadnienie" in uwaga_z(ocena) and "Izba" in uwaga_z(ocena)


def test_strona_bot_checka_nie_przechodzi_jako_tresc_orzeczenia() -> None:
    """Bez tej asercji pomiar 19 mierzyłby stabilność strony weryfikacji przeglądarki —
    a ta jest stabilna bitowo z definicji, bo jest statycznym szablonem."""
    ocena = ksztalty.UZP_CONTENT.ocen(BOT_CHECK)

    assert ocena.zgodny is False, "bot-check przeszedł jako treść orzeczenia"
    assert "Uzasadnienie" in uwaga_z(ocena) and "Weryfikacja przegladarki" in uwaga_z(ocena)


def test_metryka_dokumentu_nie_przechodzi_jako_tresc_orzeczenia() -> None:
    """Trzy oczekiwania UZP nie mają prawa się mylić.

    `ContentHtml` i `Details` są dwoma punktami tego samego serwisu i różnią się dokładnie tym,
    czego szuka pomiar 19: pierwszy niesie treść, drugi metrykę. Oczekiwanie pasujące do obu
    przepuściłoby przekierowanie z jednego na drugi jako poprawną odpowiedź — czyli pomiar 19
    porównywałby bajty metryki, nie zmieniając ani jednego napisu na ekranie.
    """
    assert ksztalty.UZP_CONTENT.ocen(DETAILS_OK).zgodny is False
    assert ksztalty.UZP_CONTENT.ocen(WYNIKI_OK).zgodny is False
    assert ksztalty.UZP_DETAILS.ocen(CONTENT_OK).zgodny is False


def test_brak_jednego_naglowka_sekcji_wystarcza_do_niezgodnosci() -> None:
    """Postanowienie bez uzasadnienia nie jest tym, o co pyta pomiar 19 — a uwaga ma wymienić
    fragment brakujący, nie obecny."""
    polowiczna = "<html><body><p>Izba postanawia (napis wymyślony).</p></body></html>".encode()

    ocena = ksztalty.UZP_CONTENT.ocen(polowiczna)

    assert ocena.zgodny is False
    assert "Uzasadnienie" in uwaga_z(ocena)
    assert "'Izba'" not in uwaga_z(ocena), "uwaga wymienia fragment, który **jest**"


# --- podgląd: obcy napis na drodze do terminala --------------------------------------------


def test_podglad_nie_przepuszcza_znakow_sterujacych_na_terminal() -> None:
    """Podgląd jest obcym napisem i idzie przez `strip_control` — sekwencja ANSI nie ma
    prawa dojść do terminala operatora, a znak dwukierunkowy nie ma prawa odwrócić kolejności
    wyświetlania tego, co sonda właśnie zmierzyła."""
    zlosliwa = "\x1b[2Jczysty ekran\x07‮gniw​o".encode()

    widok = ksztalt.podglad(zlosliwa)

    assert "\x1b" not in widok and "\x07" not in widok
    assert "‮" not in widok and "​" not in widok
    assert "czysty ekran" in widok


def test_podglad_jest_jedna_linia_przycieta_do_dlugosci_z_modulu() -> None:
    """Podgląd ma się zmieścić w wierszu tabeli, także gdy odpowiedź ma megabajt."""
    dluga = b"<html>\n  <body>\n    " + b"tresc " * 5000 + b"\n  </body>\n</html>"

    widok = ksztalt.podglad(dluga)

    assert "\n" not in widok
    assert len(widok) <= ksztalt.DLUGOSC_PODGLADU


def test_podglad_znosi_bajty_ktore_nie_sa_utf8() -> None:
    """Odpowiedź w cudzym kodowaniu jest wynikiem pomiaru, nie wyjątkiem w sondzie."""
    assert ksztalt.podglad(b"\xff\xfe nie-utf8") != ""


# --- kształt JSON: niepusta lista rekordów -------------------------------------------------


def test_pusta_lista_rekordow_nie_jest_sukcesem() -> None:
    """`total=0` ze statusem 200 — zdarzenie, które u cudzego kolektora trwało dwa miesiące."""
    ocena = ksztalty.SAOS_DUMP.ocen(b'{"items": [], "queryTemplate": {}}')

    assert ocena.zgodny is False, "pusta lista rekordów przeszła jako poprawna odpowiedź"
    assert "items" in uwaga_z(ocena)


def test_lista_pod_inna_nazwa_niz_w_kontrakcie_jest_niezgodnoscia() -> None:
    """Przeniesienie pola jest początkiem tego samego zdarzenia, nie drobiazgiem.

    Uwaga ma wymienić **obie** nazwy: tę z kontraktu i tę, która przyszła. Bez nich operator
    wie tylko, że coś się nie zgadza.
    """
    ocena = ksztalty.SAOS_DUMP.ocen(b'{"judgments": [{"id": 1}]}')

    assert ocena.zgodny is False
    assert "items" in uwaga_z(ocena) and "judgments" in uwaga_z(ocena)


def test_kontrakt_bez_nazwy_listy_przyjmuje_dowolny_klucz() -> None:
    """Odwrotność testu wyżej i cała różnica między `json_z_rekordami("items")`
    a `json_z_rekordami()`: oczekiwanie, którego nie ma, nie może się nie zgodzić."""
    ocena = DOWOLNA_LISTA(b'{"cokolwiek": [{"id": 1}]}')

    assert ocena.zgodny is True
    assert "cokolwiek" in uwaga_z(ocena)


def test_lista_atlasu_pod_innym_kluczem_niz_data_jest_niezgodnoscia() -> None:
    """Od 2026-09-18 `ATLAS_LISTA` nazywa klucz z dokumentacji odczytanej z datą.

    Bez nazwy `_pierwsza_lista` brała pierwszą listę w kolejności kluczy — ta sama usterka,
    którą 2026-09-17 naprawiono dla SAOS (`links` obok `items`), dla Atlasu stała otwarta:
    pomiar 3a mógł ogłosić „kształt OK" na liście, która nie jest listą rekordów.
    """
    ocena = ksztalty.ATLAS_LISTA.ocen(b'{"links": [{"rel": "next"}], "items": [{"id": 1}]}')

    assert ocena.zgodny is False
    assert "data" in uwaga_z(ocena), "uwaga ma mówić, o jakim kluczu mówi kontrakt"


def test_odpowiedz_ktora_nie_jest_jsonem_jest_niezgodna() -> None:
    """Bot-check na punkcie JSON-owym: ta sama strona, inny kanał, ten sam wniosek."""
    ocena = ksztalty.SAOS_DUMP.ocen(BOT_CHECK)

    assert ocena.zgodny is False
    assert "JSONDecodeError" in uwaga_z(ocena)
    assert "Weryfikacja przegladarki" in uwaga_z(ocena)


def test_json_bez_listy_rekordow_wypisuje_klucze_korzenia() -> None:
    """Odpowiedź błędu w JSON-ie ma powiedzieć, co przyszło zamiast listy."""
    ocena = ksztalty.SAOS_DUMP.ocen(b'{"error": "forbidden", "status": 403}')

    assert ocena.zgodny is False
    assert "error" in uwaga_z(ocena) and "status" in uwaga_z(ocena)


def test_korzen_bedacy_lista_liczy_sie_jako_lista_rekordow() -> None:
    """Punkt zwracający gołą tablicę jest kształtem poprawnym, a nie brakiem listy."""
    ocena = DOWOLNA_LISTA(b'[{"id": 1}, {"id": 2}]')

    assert ocena.zgodny is True
    assert "2 rekord" in uwaga_z(ocena)


def test_ocena_wypisuje_nazwy_pol_pierwszego_rekordu() -> None:
    """„Co właściwie przyszło" jest wynikiem pomiarów 2a i 3a, a nie ozdobą komunikatu.

    Przy pomiarze 3 pytanie brzmi „czy Atlas naprawdę zwraca pełny tekst" — i odpowiada na
    nie właśnie obecność nazwy pola z treścią, nie status odpowiedzi.
    """
    ocena = DOWOLNA_LISTA(b'[{"id": 1, "content": "x", "published_at": "2018-01-02"}]')

    for pole in ("id", "content", "published_at"):
        assert pole in uwaga_z(ocena)


def test_ocena_nie_wypuszcza_wartosci_pol_na_ekran() -> None:
    """Nazwy — nigdy wartości. Treść orzeczenia nie ma po co trafiać do terminala ani do
    podsumowania w `scripts/out/`, a do rozstrzygnięcia „czy jest pełny tekst" wystarcza
    nazwa pola."""
    tresc_orzeczenia = "TRESC-KTORA-NIE-MA-PRAWA-WYJSC-NA-EKRAN"
    dane = f'[{{"content": "{tresc_orzeczenia}"}}]'.encode()

    ocena = DOWOLNA_LISTA(dane)

    assert "content" in uwaga_z(ocena)
    assert tresc_orzeczenia not in uwaga_z(ocena), "wartość pola wyciekła do uwagi"


def test_liczba_wypisanych_pol_jest_ograniczona() -> None:
    """Rekord o czterdziestu polach nie ma prawa rozjechać wiersza tabeli."""
    rekord = ", ".join(f'"pole_{i:02d}": {i}' for i in range(40))
    ocena = DOWOLNA_LISTA(f"[{{{rekord}}}]".encode())

    wypisane = uwaga_z(ocena).split("pola pierwszego: ")[1]

    assert len(wypisane.split(", ")) == ksztalt.MAKS_POL_W_UWADZE


def test_lista_rekordow_ktore_nie_sa_slownikami_wychodzi_w_uwadze() -> None:
    """Zapis stanu, nie pochwała: lista napisów przechodzi jako **zgodna**.

    `json_z_rekordami()` bez nazwy listy pyta o dwie rzeczy — czy to JSON i czy lista jest
    niepusta — więc lista napisów spełnia oba warunki. Jedynym, co odróżnia ją od listy
    rekordów, jest uwaga: zamiast nazw pól niesie nazwę typu. Ta asercja pilnuje właśnie
    uwagi, bo to ona, a nie flaga, jest tu nośnikiem pomiaru. Gdyby kiedyś padło
    rozstrzygnięcie, że taki kształt ma być niezgodny, ten test jest miejscem, w którym
    zmiana staje się widoczna, a nie cicha.
    """
    ocena = DOWOLNA_LISTA(b'["a", "b"]')

    assert "str" in uwaga_z(ocena), "uwaga nie mówi, że rekordy nie są rekordami"
    assert ocena.zgodny is True


# --- kształt JSON: jeden rekord z wymaganymi polami (punkt dokumentu, od 2026-09-18) --------


def test_rekord_z_wymaganymi_polami_nazywa_najdluzsze_pole_tekstowe() -> None:
    """Odpowiedź na „czy pełny tekst" jest nazwą i długością pola, nigdy jego wartością."""
    ocena = ksztalty.ATLAS_DOKUMENT.ocen(DOKUMENT_OK)

    assert ocena.zgodny is True, uwaga_z(ocena)
    assert "`content`" in uwaga_z(ocena)
    assert "32 znaków" in uwaga_z(ocena)
    assert "tresc wymyslona" not in uwaga_z(ocena), "wartość pola wyciekła do uwagi"
    for pole in ("slug", "primary_signature", "content"):
        assert pole in uwaga_z(ocena)


def test_rekord_bez_wymaganego_pola_jest_niezgodny_i_mowi_co_przyszlo() -> None:
    ocena = ksztalty.ATLAS_DOKUMENT.ocen(b'{"slug": "x", "error": "not found"}')

    assert ocena.zgodny is False
    assert "primary_signature" in uwaga_z(ocena), "uwaga ma nazwać brakujące pole"
    assert "error" in uwaga_z(ocena), "uwaga ma wypisać pola korzenia"


def test_lista_zamiast_rekordu_jest_niezgodna_z_oczekiwaniem_dokumentu() -> None:
    ocena = ksztalty.ATLAS_DOKUMENT.ocen(b'[{"slug": "x", "primary_signature": "y"}]')

    assert ocena.zgodny is False
    assert "list" in uwaga_z(ocena)


def test_rekord_opakowany_jest_zgodny_a_opakowanie_wchodzi_do_uwagi() -> None:
    """Dokumentacja nie pokazuje przykładowej odpowiedzi, więc rekord pod `data` i rekord goły
    to ten sam kontrakt w dwóch pisowniach — a która przyszła, ma być wynikiem, nie ciszą."""
    ocena = ksztalty.ATLAS_DOKUMENT.ocen(b'{"data": {"slug": "x", "primary_signature": "y"}}')

    assert ocena.zgodny is True
    assert "pod `data`" in uwaga_z(ocena)


def test_rekord_bez_pol_tekstowych_mowi_to_wprost() -> None:
    ocena = ksztalty.ATLAS_DOKUMENT.ocen(b'{"slug": 1, "primary_signature": 2}')

    assert ocena.zgodny is True
    assert "brak pól tekstowych" in uwaga_z(ocena)


def test_najdluzsze_pole_liczy_sie_w_rekordzie_a_nie_w_korzeniu_opakowania() -> None:
    """Odpowiedź na „czy pełny tekst" dotyczy **rekordu**, nie koperty, w której przyjechał.

    Pole korzenia potrafi być długie z powodów niemających nic wspólnego z treścią orzeczenia —
    komunikat, echo zapytania, lista odnośników sklejona w napis. Gdyby ocena mierzyła
    najdłuższe pole całej odpowiedzi, `GET /api/kio/{slug}` zwracający sam skrót w kopercie
    z długim komunikatem odpowiedziałby „pełny tekst jest" na pytanie, którego nikt nie zadał —
    czyli dałby fałszywy wynik w pomiarze, na którym stoi wybór pierwszego kanału.
    """
    koperta = (
        b'{"komunikat": "' + b"M" * 500 + b'", '
        b'"data": {"slug": "x", "primary_signature": "y", "content": "tresc"}}'
    )

    ocena = ksztalty.ATLAS_DOKUMENT.ocen(koperta)

    assert ocena.zgodny is True
    assert "pod `data`" in uwaga_z(ocena)
    assert "`content` (5 znaków)" in uwaga_z(ocena), (
        "najdłuższe pole policzone w korzeniu, nie w rekordzie — długi komunikat koperty "
        "przeszedłby jako dowód pełnego tekstu"
    )
    assert "komunikat" not in uwaga_z(ocena)


def test_rekord_schowany_dwa_poziomy_glebiej_nie_jest_znajdowany() -> None:
    """Granica „sam korzeń albo pierwszy słownik potomny" jest **zapisem stanu**, nie pochwałą.

    `_rekord_z_polami` schodzi o jeden poziom, bo dokumentacja Atlasu (odczyt 2026-09-18) nie
    pokazuje przykładowej odpowiedzi i obie pisownie — rekord goły i rekord pod `data` — są tym
    samym kontraktem. Trzeci poziom byłby już zgadywaniem struktury, więc ocena woli powiedzieć
    „nie znalazłam" i wypisać klucze korzenia.

    Kierunek pomyłki jest tu bezpieczny (niezgodność zamiast cichej zgody), ale nie jest
    darmowy: przy takiej odpowiedzi pomiar 3a zapisze „kształt niezgodny" i dopiero uwaga —
    wypisane klucze korzenia — powie czytającemu, że rzecz jest w zagnieżdżeniu, a nie w braku
    pól. Dlatego ta asercja pilnuje obu połów naraz.
    """
    ocena = ksztalty.ATLAS_DOKUMENT.ocen(
        b'{"wrap": {"data": {"slug": "x", "primary_signature": "y"}}}'
    )

    assert ocena.zgodny is False
    assert "wrap" in uwaga_z(ocena), "uwaga nie mówi, co przyszło zamiast rekordu"
    assert "slug" in uwaga_z(ocena), "uwaga nie mówi, czego w rekordzie zabrakło"


def test_liczba_wypisanych_pol_rekordu_tez_jest_ograniczona() -> None:
    """Ten sam limit co przy liście rekordów, o jedną fabrykę obok.

    `json_z_rekordami` ma swojego strażnika od 2026-09-17; `json_ze_slownikiem` powstało dzień
    później i przycina tą samą stałą, ale bez asercji. Rekord orzeczenia z metadanymi jest
    przy tym **bardziej** narażony niż rekord listy: punkt dokumentu z definicji zwraca komplet
    pól, a uwaga idzie do wiersza tabeli na ekranie i do `podsumowanie_*.json`.
    """
    pola = ", ".join(f'"pole_{i:02d}": {i}' for i in range(40))
    material = f'{{"slug": "x", "primary_signature": "y", {pola}}}'.encode()

    ocena = ksztalty.ATLAS_DOKUMENT.ocen(material)

    wypisane = uwaga_z(ocena).split(" pól (")[1].split("); ")[0]

    assert ocena.zgodny is True
    assert "42 pól" in uwaga_z(ocena), "uwaga ma podać pełną liczbę pól, choć wypisuje część"
    assert len(wypisane.split(", ")) == ksztalt.MAKS_POL_W_UWADZE


@pytest.mark.parametrize(("opis", "pola"), [("zero pól", ()), ("pole puste", ("slug", ""))])
def test_oczekiwanie_rekordu_bez_pol_jest_odrzucane_przy_budowie(
    opis: str, pola: tuple[str, ...]
) -> None:
    """Ten sam niezmiennik co przy `html_z_fragmentami`: oczekiwanie, które nie może się nie
    zgodzić, jest ciszą podpisaną słowem „zgodny" i pada przy imporcie, nie po żądaniu."""
    with pytest.raises(ValueError):
        ksztalt.json_ze_slownikiem(*pola)


@pytest.mark.parametrize(
    ("galaz", "material"),
    [
        ("nie jest JSON-em", "<html>klucz {sekret}</html>"),
        ("rekord bez pól", '{{"{sekret}": 1}}'),
        ("JSON nie jest rekordem", '["{sekret}"]'),
    ],
)
def test_kazda_galaz_oceny_rekordu_maskuje_sekret(galaz: str, material: str) -> None:
    """Antypustka dla maskowania po stronie ewaluatora rekordu — te same trzy drogi wyjścia,
    które ma `json_z_rekordami`, i ta sama poprawka w `__post_init__`."""
    register_secret(SEKRET)

    ocena = ksztalty.ATLAS_DOKUMENT.ocen(material.format(sekret=SEKRET).encode())

    assert ocena.zgodny is False
    assert SEKRET not in uwaga_z(ocena), f"{galaz}: sekret przeszedł do uwagi"


# --- niezmienniki całego modułu ------------------------------------------------------------

KSZTALTY: tuple[tuple[str, ksztalt.Ksztalt], ...] = tuple(
    sorted(
        ((nazwa, obj) for nazwa, obj in vars(ksztalty).items() if isinstance(obj, ksztalt.Ksztalt)),
        key=lambda para: para[0],
    )
)


PUNKTY_SONDY = frozenset(
    {"UZP_WYNIKI", "UZP_DETAILS", "UZP_CONTENT", "SAOS_DUMP", "ATLAS_LISTA", "ATLAS_DOKUMENT"}
)
"""Oczekiwania, których wołają dziś pomiary sondy — po jednym na punkt końcowy.

Wypisane z nazwy, a nie policzone, bo liczba rosnąca w górę nie odróżnia „dopisano piąte" od
„skasowano `UZP_DETAILS` i dopisano dwa inne". `UZP_CONTENT` dołączyło 2026-09-17 razem
z pomiarem 19, `ATLAS_DOKUMENT` 2026-09-18 razem z drugim żądaniem pomiaru 3a; kontrola hosta
po odmowie i odczyty pomiaru 23 jadą bez oczekiwania, bo strona bez kontraktu nie ma kształtu,
którego brak byłby odmową.
"""


def test_modul_ma_oczekiwanie_dla_kazdego_punktu_koncowego_sondy() -> None:
    """Antypustka dla wszystkich parametryzacji po `KSZTALTY` w tym pliku.

    Parametryzacja po pustej krotce przechodzi na zielono i wygląda identycznie jak
    przechodząca po pięciu oczekiwaniach. Ten test jest jedynym miejscem, w którym taka
    zamiana zapala się na czerwono — i jedynym, w którym zapala się **usunięcie** oczekiwania
    dla punktu, który sonda nadal odpytuje.
    """
    znalezione = {nazwa for nazwa, _ in KSZTALTY}

    assert PUNKTY_SONDY <= znalezione, (
        f"brakuje oczekiwań dla punktów {sorted(PUNKTY_SONDY - znalezione)} — pomiar wysyłający "
        "żądanie bez oczekiwania kształtu wypisze stronę bot-checka jako sukces"
    )


@pytest.mark.parametrize(("nazwa", "ksztalt"), KSZTALTY, ids=[n for n, _ in KSZTALTY])
def test_kazde_oczekiwanie_niesie_swoje_zrodlo(nazwa: str, ksztalt: ksztalt.Ksztalt) -> None:
    """Zasada 7.1 w typie, nie w komentarzu.

    Niezgodność oczekiwania wziętego z cudzego kolektora znaczy „albo kontrakt się zmienił,
    albo nigdy nie był taki". Niezgodność oczekiwania z własnego odczytu znaczy „serwis
    zmienił się od dnia, w którym patrzyliśmy". Bez zapisanego źródła te dwa zdania są
    nierozróżnialne, a sonda wypisuje tylko drugie z nich.
    """
    assert ksztalt.opis.strip(), f"{nazwa}: oczekiwanie bez opisu"
    assert ksztalt.zrodlo.strip(), (
        f"{nazwa}: oczekiwanie bez zapisanego źródła. Sonda wypisuje ten napis pod każdą oceną "
        "kształtu; pusty zamienia status dowodowy pomiaru w domysł czytającego."
    )


@pytest.mark.parametrize(("nazwa", "ksztalt"), KSZTALTY, ids=[n for n, _ in KSZTALTY])
def test_ocena_niesie_uwage_takze_gdy_kszalt_sie_nie_zgadza(
    nazwa: str, ksztalt: ksztalt.Ksztalt
) -> None:
    """Ocena milcząca przy niezgodności mówi „coś nie tak" i nic poza tym.

    Bot-check jest tu użyty jako materiał, który **żadnemu** z oczekiwań nie odpowiada —
    ani HTML-owemu (brak znaczników), ani JSON-owemu (nie jest JSON-em).
    """
    ocena = ksztalt.ocen(BOT_CHECK)

    assert ocena.zgodny is False, f"{nazwa}: bot-check uznany za odpowiedź zgodną z kontraktem"
    assert ocena.uwaga.strip(), f"{nazwa}: ocena niezgodna bez uwagi"


@pytest.mark.parametrize(
    ("nazwa", "ocen", "material"),
    [
        ("UZP_WYNIKI", ksztalty.UZP_WYNIKI.ocen, WYNIKI_OK),
        ("UZP_DETAILS", ksztalty.UZP_DETAILS.ocen, DETAILS_OK),
        ("SAOS_DUMP", ksztalty.SAOS_DUMP.ocen, b'{"items": [{"id": 1}]}'),
        ("ATLAS_LISTA", ksztalty.ATLAS_LISTA.ocen, b'{"data": [{"id": 1}]}'),
        ("ATLAS_DOKUMENT", ksztalty.ATLAS_DOKUMENT.ocen, DOKUMENT_OK),
    ],
)
def test_ocena_niesie_uwage_takze_przy_zgodnosci(nazwa: str, ocen: object, material: bytes) -> None:
    """Rozstrzygnięcie 1 z nagłówka `ksztalty.py`: ocena, która przy powodzeniu milczy, mówi
    operatorowi wyłącznie „nie zapaliło się" — a pytaniem pomiaru jest „co przyszło"."""
    ocena = ocen(material)  # type: ignore[operator]

    assert ocena.zgodny is True, f"{nazwa}: materiał zgodny z kontraktem uznany za niezgodny"
    assert ocena.uwaga.strip(), f"{nazwa}: ocena zgodna bez uwagi"


# --- niezmiennik ASCII: oczekiwanie wywraca się przed żądaniem, nie po nim ------------------
#
# Poprawka z 2026-09-17. Do tego dnia „wszystkie fragmenty są ASCII" było zdaniem w docstringu
# `html_z_fragmentami`, a fragment z ogonkiem wywracał się `UnicodeEncodeError`-em dopiero
# w `ocen` — czyli **po wysłaniu żądania** i przed `Kronika.zanotuj`. Ślad po ruchu, za który
# cudzy serwer już zapłacił pracą, ginął. Dokładnie ten kształt awarii projekt zamknął raz
# w tej samej sesji przy zakładaniu dziennika (`replace` zamiast `format`); tu wracał tylnymi
# drzwiami, o jeden moduł obok.


def test_fragment_z_ogonkiem_wywraca_budowe_oczekiwania_a_nie_ocene() -> None:
    """Moment wywrócenia jest tu całą treścią poprawki, nie szczegółem.

    Wyjątek z fabryki pada przy imporcie `ksztalty`, czyli zanim sonda zbuduje klienta —
    a więc zanim cokolwiek wyjdzie na zewnątrz. Wyjątek z `ocen` padał po `acquire`,
    po odstępie limitera i po odpowiedzi cudzego serwisu.

    Druga połowa asercji pilnuje klasy wyjątku: `UnicodeEncodeError` mówi „coś z kodowaniem"
    i zostawia czytającego ze śladem stosu w `bytes.encode`, `ValueError` mówi, **który**
    fragment i dlaczego porównanie po ogonkach nie ma tu prawa działać.
    """
    with pytest.raises(ValueError) as zgloszony:
        ksztalt.html_z_fragmentami("Uzasadnienie", "Izba zważyła")

    komunikat = str(zgloszony.value)

    assert "Izba zważyła" in komunikat, "komunikat nie mówi, który fragment jest zły"
    assert "Uzasadnienie" not in komunikat, "komunikat wymienia fragment, który jest poprawny"
    assert "ASCII" in komunikat


def test_ocena_zbudowana_z_fragmentow_ascii_nie_wywraca_sie_na_ogonkach_w_odpowiedzi() -> None:
    """Niezmiennik dotyczy **oczekiwania**, nie materiału. Odpowiedź cudzego serwisu jest pełna
    ogonków i ma taka zostać — zakaz obowiązuje napis, z którym porównujemy."""
    ocen = ksztalt.html_z_fragmentami("Uzasadnienie", "Izba")

    assert ocen("<p>Uzasadnienie. Izba zważyła, co następuje.</p>".encode()).zgodny is True
    assert ocen("<p>Żądanie oddalono — bez uzasadnienia sekcji.</p>".encode()).zgodny is False


@pytest.mark.parametrize(("nazwa", "ksztalt"), KSZTALTY, ids=[n for n, _ in KSZTALTY])
def test_zadne_oczekiwanie_w_module_nie_wywraca_sie_przy_ocenie(
    nazwa: str, ksztalt: ksztalt.Ksztalt
) -> None:
    """Druga strona niezmiennika, sprawdzona na **każdym** oczekiwaniu, także dopisanym jutro.

    Sprawdzenie przy budowie broni oczekiwań budowanych przez `html_z_fragmentami`. To jest
    pytanie szersze: czy którakolwiek droga oceny — HTML-owa czy JSON-owa — potrafi wywrócić
    się na bajtach, zamiast wydać ocenę. Materiał jest tu celowo paskudny: nie-UTF-8, bajt
    zerowy i puste bajty, czyli trzy rzeczy, które cudzy serwis potrafi przysłać, a których
    żaden kontrakt nie obiecuje.
    """
    for material in (b"\xff\xfe\x00 nie-utf8", b"", b"\x00" * 32):
        ocena = ksztalt.ocen(material)
        assert ocena.zgodny is False, f"{nazwa}: śmieci uznane za odpowiedź zgodną z kontraktem"
        assert ocena.uwaga.strip(), f"{nazwa}: ocena bez uwagi"


# --- maskowanie: uwaga niesie cudzą odpowiedź, a ta potrafi odbić klucz ---------------------
#
# `uwaga` idzie stąd na ekran, do `podsumowanie_*.json` i — przez udokumentowane „przepisz
# wynik do `docs/decisions.md`" — do pliku w historii repozytorium. Odpowiedź błędu potrafi
# odbić nagłówek żądania, przy Atlasie razem z `X-Api-Key`. `strip_control` sam nie wystarcza
# i mówi to wprost `tests/test_boundaries.py` przy definicji neutralizatorów: usuwa znaki
# sterujące, ale **nie maskuje sekretu**.

SEKRET = "sekretny-klucz-atlasu"
"""Napis dłuższy niż `MIN_REGISTERED_SECRET`, bo `register_secret` krótszy odrzuca."""


def test_uwaga_jest_maskowana_przy_budowie_oceny() -> None:
    """Najkrótszy obserwator poprawki: maskowanie siedzi w `__post_init__`, a nie w miejscu,
    które akurat składa napis.

    Gdyby siedziało w miejscach składania, byłoby ich tyle, ile gałęzi oceny — a dopisanie
    szóstej gałęzi jutro nie zapaliłoby niczego.
    """
    register_secret(SEKRET)

    ocena = ksztalt.OcenaKsztaltu(zgodny=True, uwaga=f"nagłówek: {SEKRET}")

    assert SEKRET not in ocena.uwaga
    assert "<token>" in ocena.uwaga


def test_klucz_odbity_w_odpowiedzi_bledu_nie_dochodzi_do_uwagi() -> None:
    """Droga, dla której ta poprawka powstała: pośrednik odbija nagłówek w komunikacie błędu.

    Podgląd cudzej odpowiedzi szedł wcześniej przez sam `strip_control`, czyli wprost na
    ekran i na dysk. Operator przepisuje z ekranu do `decisions.md` — pliku wersjonowanego.
    """
    register_secret(SEKRET)
    # Strona błędu pośrednika, nie JSON — i to jest gałąź, którą trzeba tu trafić: podgląd
    # wchodzi do uwagi **w całości**, więc tylko tędy wartość nagłówka może wyjść na ekran.
    # Gałęzie JSON-owe wypisują nazwy pól, a nie wartości, i mają swoją parametryzację niżej.
    odbicie = f"<html><body>401 invalid api key: {SEKRET}</body></html>".encode()

    ocena = ksztalty.SAOS_DUMP.ocen(odbicie)

    assert ocena.zgodny is False
    assert SEKRET not in uwaga_z(ocena), "klucz przeszedł do uwagi razem z podglądem odpowiedzi"
    assert "<token>" in uwaga_z(ocena)


def test_maskowanie_dziala_takze_gdy_ksztalt_sie_zgadza() -> None:
    """Ocena zgodna wypisuje nazwy pól pierwszego rekordu — a nazwą pola bywa `api_key`
    z wartością odbitą w echu zapytania. Zgodność kształtu nie jest dowodem, że w uwadze
    nie ma sekretu."""
    register_secret(SEKRET)
    echo = f'{{"data": [{{"id": 1, "{SEKRET}": "x"}}]}}'.encode()

    ocena = ksztalty.ATLAS_LISTA.ocen(echo)

    assert ocena.zgodny is True
    assert SEKRET not in uwaga_z(ocena)


def test_maskowanie_idzie_po_usunieciu_znakow_sterujacych() -> None:
    """Kolejność `strip_control` → `mask_tokens`, przeniesiona z `richtext.safe` razem z powodem.

    Klucz z wstrzykniętym znakiem zerowej szerokości nie równa się wartości zarejestrowanej,
    więc samo maskowanie przepuściłoby go nierozpoznany — a po usunięciu znaku dopasowuje się
    dokładnie. Odwrócenie kolejności nie psuje żadnego innego testu i nie wypisuje nic:
    w `ceidg-tool` ta sama luka przeszła całą zieloną suitę i pokazała ją dopiero mutacja.
    """
    register_secret(SEKRET)
    rozbity = SEKRET[:6] + "​" + SEKRET[6:]
    odbicie = f"<html><body>401 invalid key: {rozbity}</body></html>".encode()

    ocena = ksztalty.SAOS_DUMP.ocen(odbicie)

    assert SEKRET not in uwaga_z(ocena), (
        "klucz rozbity znakiem zerowej szerokości przeszedł przez maskowanie — kolejność "
        "`strip_control` → `mask_tokens` jest odwrócona"
    )
    assert "<token>" in uwaga_z(ocena)


def test_maskowanie_idzie_po_usunieciu_znakow_sterujacych_takze_w_nazwie_pola() -> None:
    """Ta sama kolejność sprawdzona na gałęzi, która **nie** przechodzi przez `podglad`.

    Przegląd kodu 2026-09-18: test wyżej przechodził zielono dlatego, że `podglad` ma własny
    `strip_control`, a `__post_init__` — o którym mówi jego nazwa — tej własności nie miał. Nazwa
    pola JSON z wstrzykniętym znakiem zerowej szerokości niosła sekret nierozpoznany, a po
    pierwszym `strip_control` w dalszej warstwie sekret się odtwarzał. Poprawione tego samego dnia
    w `OcenaKsztaltu.__post_init__`; ten test jest obserwatorem tej gałęzi.
    """
    register_secret(SEKRET)
    rozbity = SEKRET[:6] + "​" + SEKRET[6:]

    ocena = ksztalty.ATLAS_LISTA.ocen(('{"data": [{"' + rozbity + '": 1}]}').encode())

    assert ocena.zgodny is True
    assert SEKRET not in strip_control(uwaga_z(ocena)), (
        "sekret rozbity znakiem zerowej szerokości w nazwie pola odtworzył się po `strip_control`"
    )
    assert "<token>" in uwaga_z(ocena)


def test_znak_sterujacy_w_nazwie_pola_nie_dochodzi_do_uwagi() -> None:
    """`\\x1b[2J` w nazwie pola cudzej odpowiedzi czyściłby operatorowi ekran; `U+202E`
    odwracałby wyświetlanie zmierzonego wyniku. Oba mają zniknąć przy budowie oceny."""
    material = b'{"data": [{"\\u001b[2J\\u202eEVIL": 1}]}'

    ocena = ksztalty.ATLAS_LISTA.ocen(material)

    assert "\x1b" not in uwaga_z(ocena) and "‮" not in uwaga_z(ocena)
    assert "EVIL" in uwaga_z(ocena), "nazwa pola ma zostać, bez znaków sterujących"


@pytest.mark.parametrize(
    ("galaz", "material"),
    [
        ("nie jest JSON-em", "<html>klucz {sekret}</html>"),
        ("JSON bez listy rekordów", '{{"{sekret}": 1}}'),
        ("lista pusta", '{{"{sekret}": []}}'),
        ("lista pod obcym kluczem", '{{"{sekret}": [{{"id": 1}}]}}'),
    ],
)
def test_kazda_galaz_oceny_json_maskuje_sekret(galaz: str, material: str) -> None:
    """Antypustka dla maskowania: każda droga wyjścia z `json_z_rekordami` buduje własną uwagę.

    Test chodzi po wszystkich czterech, bo poprawka w `__post_init__` jest warta dokładnie
    tyle, ile najsłabsza z nich — a gałąź pominięta wygląda tak samo jak pokryta.
    """
    register_secret(SEKRET)

    ocena = ksztalty.SAOS_DUMP.ocen(material.format(sekret=SEKRET).encode())

    assert ocena.zgodny is False
    assert SEKRET not in uwaga_z(ocena), f"{galaz}: sekret przeszedł do uwagi"


@pytest.mark.parametrize(("nazwa", "ksztalt"), KSZTALTY, ids=[n for n, _ in KSZTALTY])
def test_zadne_oczekiwanie_nie_wypuszcza_sekretu_w_uwadze(
    nazwa: str, ksztalt: ksztalt.Ksztalt
) -> None:
    """To samo pytanie zadane **każdemu** oczekiwaniu w module, także dopisanemu jutro.

    Materiał jest niezgodny z każdym z nich, więc każde schodzi do gałęzi z podglądem —
    czyli do jedynego miejsca, w którym cudza treść wchodzi do uwagi w całości.
    """
    register_secret(SEKRET)

    ocena = ksztalt.ocen(f"<html>odbicie naglowka: {SEKRET}</html>".encode())

    assert ocena.zgodny is False
    assert SEKRET not in uwaga_z(ocena), f"{nazwa}: sekret przeszedł do uwagi"


# ------------------------------------------------------------------------------- znaleziska
#
# Trzy zachowania, wszystkie zgłoszone i zamknięte 2026-09-17: kolejność kluczy w cudzym
# JSON-ie (werdykt zależał od tego, jak ktoś inny serializował odpowiedź), fragment z ogonkiem
# wywracający ocenę **po** wysłaniu żądania, i opisane niżej oczekiwanie bez fragmentów.
#
# Oczekiwanie HTML, które nie może się nie zgodzić. Zgłoszone 2026-09-17 jako
# `xfail(strict=True)` i **poprawione tego samego dnia**: `html_z_fragmentami` odrzuca teraz
# przy budowie oczekiwanie bez fragmentów i oczekiwanie z fragmentem pustym. Znacznik zdjęty,
# bo asercja opisuje odtąd zachowanie dzisiejsze; sam mechanizm zgłaszania (asercja oczekiwana,
# dzień poprawki kończy się czerwonym `XPASS`) zadziałał i jest wzorcem z `test_ratelimit.py`.


@pytest.mark.parametrize(
    ("opis", "fragmenty"),
    [
        ("zero fragmentów", ()),
        ("pusty fragment", ("",)),
        ("pusty obok poprawnego", ("Uzasadnienie", "")),
    ],
)
def test_oczekiwanie_ktore_nie_moze_sie_nie_zgodzic_jest_odrzucane_przy_budowie(
    opis: str, fragmenty: tuple[str, ...]
) -> None:
    """Ta sama myśl co niezmiennik ASCII, o jeden stan dalej — i ten stan jest cichy.

    `html_z_fragmentami` sprawdza od 2026-09-17, czy fragmenty są ASCII, bo zły fragment
    wywracał `ocen`. Nie sprawdza natomiast, czy fragment cokolwiek **znaczy**. Pusty napis
    zawiera się w każdych bajtach (`b"" in cokolwiek` jest prawdą), a lista pusta nie ma czego
    sprawdzać — więc oba przypadki dają oczekiwanie, którego `zgodny` wynosi `True` zawsze.

    Zmierzone 2026-09-17: `html_z_fragmentami()(BOT_CHECK).zgodny is True` oraz
    `html_z_fragmentami("")(BOT_CHECK).zgodny is True`.

    Różnica wobec niezmiennika ASCII jest w tym, po której stronie leży cisza. Fragment
    z ogonkiem **krzyczy** — wywraca przebieg wyjątkiem, więc nikt go nie przeoczy. Fragment
    pusty milczy: sonda wypisuje „kształt OK: obecne: " pod każdą odpowiedzią, dziennik dostaje
    w kolumnie kształtu słowo „zgodny", a strona bot-checka przechodzi jako kontrakt
    potwierdzony — czyli dokładnie ten stan, dla którego cały ten moduł powstał (dwa miesiące
    `total=0` ze statusem 200 u cudzego kolektora). Cena jest przy tym wyższa niż przy zwykłym
    fałszywym alarmie, bo błąd idzie w stronę przeciwną: `Wynik.odmowa` nie zapala się, więc
    przy UZP nieznany POST **idzie dalej** po kontroli, która niczego nie sprawdziła.

    Droga jest realna i krótka: zawężanie oczekiwania w reakcji na fałszywy alarm (dokładnie
    to, co zrobił komentarz przy `UZP_CONTENT`, przycinając pięć fragmentów do dwóch) o jeden
    krok dalej daje zero, a literówka w przecinku — `html_z_fragmentami("Uzasadnienie", "")` —
    daje pusty fragment obok poprawnego i rozbraja **całe** oczekiwanie, nie połowę.

    Lekarstwem jest ten sam kształt co przy ASCII: odmowa przy budowie, z komunikatem mówiącym,
    że oczekiwanie bez treści nie jest oczekiwaniem. Test celuje w zachowanie, nie w postać
    poprawki — żąda wyjątku przy budowie, nie konkretnego napisu.
    """
    with pytest.raises(ValueError):
        ksztalt.html_z_fragmentami(*fragmenty)


def test_lista_wskazana_w_kontrakcie_jest_znajdowana_niezaleznie_od_kolejnosci_kluczy() -> None:
    """Werdykt o kształcie nie ma prawa zależeć od kolejności kluczy w cudzej odpowiedzi.

    Odpowiedź Dump API SAOS niesie obok `items` także `links` — i to jest **lista**. Pierwsza
    wersja `_pierwsza_lista` zwracała pierwszą listę napotkaną w słowniku, a nie tę, o której
    mówi kontrakt, więc odpowiedź poprawna z `links` przed `items` dostawała ocenę „lista
    `links` jest pusta" albo „kontrakt mówi o kluczu `items`". Kolejność kluczy w JSON-ie nie
    jest częścią żadnego kontraktu i cudzy serwis może ją zmienić między wersjami bez
    uprzedzenia. Zgłoszone 2026-09-17 jako `xfail(strict=True)`, poprawione tego samego dnia
    przez `_lista_rekordow`; znacznik zdjęty razem z poprawką.

    Waga bierze się z tego, co sonda robi z tą oceną. Kształt niezgodny wchodzi do
    `Wynik.odmowa`, więc fałszywy alarm tutaj wysyła dodatkowe żądanie kontrolne na korzeń
    hosta, a przy UZP **zatrzymuje całą grupę pomiarów**: znany-dobry odczyt „wrócił
    w kształcie nie do poznania" i nieznany POST nie idzie. Pomiar, który nie padł, wygląda
    wtedy tak samo jak pomiar zablokowany przez serwis — czyli z dwóch różnych zdarzeń robi
    się jeden zapis w `decisions.md`.

    Lekarstwem jest sięgnięcie po `dane[oczekiwany_klucz]`, gdy kontrakt nazwę podaje,
    i dopiero przy jej braku szukanie pierwszej listy. Test celuje w zachowanie, a nie
    w postać poprawki.
    """
    ocena = ksztalty.SAOS_DUMP.ocen(b'{"links": [{"rel": "next"}], "items": [{"id": 1}]}')

    assert ocena.zgodny is True, uwaga_z(ocena)
    assert "items" in uwaga_z(ocena)
