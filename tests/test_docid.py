"""Strażnik kanonicznej tożsamości — `kio_tool.docid`.

Ten moduł jest jedynym producentem sygnatury kanonicznej i identyfikatora dokumentu, więc
jego defekt nie zostaje w module: rozlewa się na `cases.signature`, `documents.doc_id`
i `document_cases`, czyli na cały korpus. Testy pilnują **miejsc, w których informacja ginie
po cichu**, a nie ścieżek szczęśliwych — projekt ma za sobą dwie awarie dokładnie tego
kształtu (audyt, sekcja 11, mina 1):

1. pobranie **pierwszego** elementu listy sygnatur gubiło drugą sprawę w dokumentach
   wielosygnaturowych (architektura 3.1, kolektor Legal Data Hunter);
2. klucz tożsamości **wrażliwy na wielkość liter** zapisywał ten sam wpis dwa razy —
   jedna noc, 2 681 żądań, zero użytecznych rekordów.

**Pochodzenie danych testowych — mina 4 i zasada 7.1.** Sygnatura wygląda tak samo
niezależnie od tego, czy istnieje, więc wymyślony przykład przeszedłby każdy test i byłby
cicho nieprawdziwy. Dlatego **żadna postać sygnatury w tym pliku nie pochodzi z pamięci
modelu.** Każda grupa przypadków ma w komentarzu miejsce w dokumencie, z którego postać
została odczytana (`docs/AUDYT_KIO_ORZECZENIA.md`, `docs/ARCHITEKTURA_KIO_TOOL.md`).
Tam, gdzie testowane zachowanie nie ma w dokumentach przykładu z odczytu, użyty jest napis
**jawnie sztuczny** — nazwany w teście jako sztuczny i nieudający prawdziwej sygnatury.

Zero żądań. Ten moduł nie dotyka sieci ani bazy, więc `--block-network` nie ma tu nic do
roboty poza potwierdzeniem, że nadal nic do niej nie idzie.
"""

from __future__ import annotations

import pytest

from kio_tool.docid import (
    Signature,
    SourceName,
    document_id,
    normalize_signature,
    normalize_signature_list,
)
from kio_tool.errors import IdentityError

# --------------------------------------------------------------------------------------
# Sygnatury z odczytów udokumentowanych. Każdy wiersz ma źródło.
# --------------------------------------------------------------------------------------

SYGNATURY_Z_ODCZYTU: list[tuple[str, str]] = [
    # AUDYT 2.2 „Kształt wyszukiwarki — zmierzone bezpośrednio”: mapowanie identyfikatora
    # wewnętrznego na sygnaturę, odczyt 2026-09-14. `id=1`, `id=6906`, `id=30442`.
    ("KIO 2650/15", "id=1 (AUDYT 2.2); ta sama sprawa w AUDYT 2.3 jako Details/1"),
    ("KIO/UZP 1482/08", "id=6906, 9 stycznia 2009 (AUDYT 2.2)"),
    ("KIO 3019/25", "id=30442, 9 września 2025 (AUDYT 2.2)"),
    # AUDYT 2.4 „Zasięg archiwum”: najstarsze odnalezione orzeczenia, rocznik 2007.
    ("KIO/UZP 5/07", "najstarsze w bazie, grudzień 2007 (AUDYT 2.4)"),
    # AUDYT 2.4: wewnętrzna nazwa pliku Worda `2791_12.doc` zachowana w treści dokumentu.
    ("KIO 2791/12", "z nazwy `2791_12.doc` w treści dokumentu (AUDYT 2.4)"),
    # AUDYT 4.4 „SAOS”: skrajne rekordy zapytania `courtType=NATIONAL_APPEAL_CHAMBER`.
    ("KIO/UZP 2/07", "najstarszy rekord SAOS, 2007-12-10 (AUDYT 4.4)"),
    ("KIO 1711/18", "najnowszy rekord SAOS, 2018-09-06 (AUDYT 4.4)"),
    # AUDYT 5.1 i 5.3: dokument pobrany z `Home/PdfContent/19308?Kind=KIO`, 2026-09-14.
    ("KIO 704/23", "PdfContent/19308 (AUDYT 5.1, 5.3)"),
    # ARCHITEKTURA 1.2: identyfikatory wewnętrzne przetrwały przebudowę z lipca 2026.
    ("KIO 2924/21", "nadal id=15903 po przebudowie (ARCHITEKTURA 1.2)"),
    # ARCHITEKTURA 1.4: odczyty pojedynczych dokumentów z `Details`.
    ("KIO 1963/25", "sprawa zwrócona, „Przewodniczący: Prezes KIO” (ARCHITEKTURA 1.4)"),
    ("KIO 65/23", "siódmy dokument, anonimizacja 2023 (ARCHITEKTURA 1.4 i 2)"),
    # ARCHITEKTURA 1.4 / 4.4: rekord SAOS 354301 zatytułowany „KIO 233/18, KIO 234/18”.
    ("KIO 233/18", "rekord SAOS 354301, pierwsza sprawa (ARCHITEKTURA 1.4)"),
    ("KIO 234/18", "rekord SAOS 354301, druga sprawa (ARCHITEKTURA 1.4)"),
    # ARCHITEKTURA 4.4, komentarz przy `cases.signature`: postaci kanoniczne wprost.
    ("KIO 827/18", "kanoniczna postać w schemacie `cases` (ARCHITEKTURA 4.4)"),
    ("KIO/KU 97/13", "postać uchwał w schemacie `cases` (ARCHITEKTURA 4.4)"),
    # ARCHITEKTURA 3.5: cytowania wyciągnięte z uzasadnienia dokumentu `KIO 65/23`.
    ("KIO 835/22", "cytowane w uzasadnieniu KIO 65/23 (ARCHITEKTURA 3.5)"),
    ("KIO 113/22", "cytowane w uzasadnieniu KIO 65/23 (ARCHITEKTURA 3.5)"),
    ("KIO 115/22", "cytowane w uzasadnieniu KIO 65/23 (ARCHITEKTURA 3.5)"),
    ("KIO 178/15", "cytowane w uzasadnieniu KIO 65/23 (ARCHITEKTURA 3.5)"),
    ("KIO 520/21", "cytowane w uzasadnieniu KIO 65/23 (ARCHITEKTURA 3.5)"),
    ("KIO 293/21", "cytowane w uzasadnieniu KIO 65/23 (ARCHITEKTURA 3.5)"),
]


@pytest.mark.parametrize(
    "sygnatura",
    [pytest.param(postac, id=f"{postac} [{skad}]") for postac, skad in SYGNATURY_Z_ODCZYTU],
)
def test_postac_kanoniczna_z_odczytu_jest_punktem_stalym(sygnatura: str) -> None:
    """Sygnatura już kanoniczna wychodzi z normalizatora bez zmiany.

    To nie jest test tożsamościowy dla ozdoby: normalizator jest jedynym producentem
    klucza `cases.signature`, więc brak idempotencji znaczyłby, że ta sama sprawa dostaje
    inny klucz przy drugim przejściu — dokładnie mina 1 w wersji „dwie pisownie jednego
    identyfikatora”. Wszystkie postacie pochodzą z odczytów z datą, nie z pamięci modelu.
    """
    assert normalize_signature(sygnatura) == sygnatura
    assert normalize_signature_list(sygnatura) == [sygnatura]


# --------------------------------------------------------------------------------------
# Mina 1, postać druga: klucz wrażliwy na wielkość liter
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("zapis", "oczekiwana"),
    [
        # Sygnatury poniżej pochodzą z odczytów (AUDYT 2.2, ARCHITEKTURA 4.4). Zmieniona
        # jest wyłącznie **pisownia** — wielkość liter i spacje wokół ukośnika — czyli
        # dokładnie to, co w CEIDG różniło dwa punkty końcowe zwracające ten sam wpis.
        ("kio/uzp 1482/08", "KIO/UZP 1482/08"),
        ("Kio/Uzp 1482/08", "KIO/UZP 1482/08"),
        ("kio 2650/15", "KIO 2650/15"),
        ("kio/ku 97/13", "KIO/KU 97/13"),
        ("  KIO / UZP  1482 / 08 ", "KIO/UZP 1482/08"),
        ("KIO\t827/18", "KIO 827/18"),
        ("KIO  827  /  18", "KIO 827/18"),
    ],
)
def test_pisownia_nie_tworzy_drugiej_tozsamosci(zapis: str, oczekiwana: str) -> None:
    """Różnice w wielkości liter i w spacjach schodzą do jednej postaci.

    Awaria z CEIDG (mina 1): jeden punkt końcowy zwracał identyfikator wielkimi literami,
    drugi małymi, klucz główny był wrażliwy na wielkość liter, więc każdy zmieniony wpis
    zapisywał się dwa razy. Ten test pilnuje, żeby wejście w dowolnej pisowni nie potrafiło
    wyprodukować drugiego klucza dla tej samej sprawy.
    """
    assert normalize_signature(zapis) == oczekiwana


def test_sygnatura_sklejona_bez_spacji_wciaz_jest_rozpoznawana() -> None:
    """Separator między prefiksem a numerem jest opcjonalny — i to jest gałąź bez źródła.

    Napis `KIO113/22` jest **jawnie sztuczny**, sklejony z sygnatury pochodzącej z odczytu
    (`KIO 113/22`, cytowanie z uzasadnienia `KIO 65/23`, ARCHITEKTURA 3.5). Powód, dla
    którego wzorzec dopuszcza brak spacji, stoi w komentarzu przy `_WZOR_KIO` i brzmi:
    świadoma tolerancja wejścia dla `parser/cite.py`, nie opis zaobserwowanego zapisu.

    Pierwsza wersja tego docstringa cytowała wcześniejsze brzmienie tamtego komentarza —
    zdanie o postaci „po złej konwersji PDF" — które zostało z kodu **wycofane** jako
    twierdzenie bez daty i bez wskazania dokumentu. Cytat przywracał więc do obiegu
    niepotwierdzone twierdzenie, i to w pliku, którego nagłówek deklaruje, że żadna postać
    nie pochodzi z pamięci modelu (przegląd kodu 2026-09-15).

    **Zastrzeżenie do tej gałęzi.** Postaci sklejonej nie ma w żadnym odczycie w audycie
    ani w architekturze — jest twierdzeniem samego komentarza w kodzie, bez daty i bez
    wskazania dokumentu. Test pilnuje więc zachowania, na którym opiera się parser cytowań,
    ale **nie potwierdza**, że źródło rzeczywiście tak zapisuje; to rozstrzygnie dopiero
    pomiar 22 na tekście uzasadnień. Gdyby pomiar wypadł negatywnie, gałąź jest do usunięcia
    razem z tym testem — dopóki stoi, ma mieć strażnika.
    """
    sklejona_sztuczna = "KIO113/22"

    assert normalize_signature(sklejona_sztuczna) == "KIO 113/22"
    assert normalize_signature_list(f"{sklejona_sztuczna} oraz KIO 113/22") == ["KIO 113/22"]


def test_rozne_pisownie_tej_samej_sprawy_deduplikuja_sie_na_liscie() -> None:
    """Deduplikacja idzie po postaci kanonicznej, nie po napisie wejściowym.

    Gdyby `normalize_signature_list` deduplikowała po surowym napisie, dokument z zapisem
    „KIO 233/18” i „kio 233/18” dałby dwa wiersze w `document_cases` dla jednej sprawy.
    Sygnatury z odczytu: rekord SAOS 354301 (ARCHITEKTURA 1.4).
    """
    assert normalize_signature_list("KIO 233/18, kio 233/18, KIO 234/18") == [
        "KIO 233/18",
        "KIO 234/18",
    ]


# --------------------------------------------------------------------------------------
# Mina 1, postać pierwsza: dokument wielosygnaturowy
# --------------------------------------------------------------------------------------


def test_dokument_wielosygnaturowy_oddaje_obie_sprawy_w_kolejnosci() -> None:
    """Rdzeń miny 1: dokument bywa nośnikiem kilku spraw i żadna nie może zniknąć.

    Odczyt: rekord SAOS `saos.org.pl/judgments/354301` ma tytuł „KIO 233/18, KIO 234/18”
    (ARCHITEKTURA 1.4, powtórzone jako dowód w 4.4). Kolektor Legal Data Hunter bierze
    w tym miejscu `case_number` z **pierwszego** elementu listy i przez to gubi drugą
    sprawę (ARCHITEKTURA 3.1) — to jest awaria, której ta funkcja ma nie powtórzyć.
    """
    sygnatury = normalize_signature_list("KIO 233/18, KIO 234/18")

    assert sygnatury == ["KIO 233/18", "KIO 234/18"], (
        "Dokument wielosygnaturowy stracił sprawę albo kolejność. To jest kształt miny 1: "
        f"oczekiwano obu spraw z rekordu SAOS 354301, otrzymano {sygnatury!r}."
    )


def test_wszystkie_cytowania_z_uzasadnienia_wychodza_z_jednego_przebiegu() -> None:
    """Sześć cytowań z jednego uzasadnienia, w kolejności wystąpienia.

    Odczyt: uzasadnienie dokumentu `KIO 65/23` cytuje `KIO 835/22`, `KIO 113/22`,
    `KIO 115/22`, `KIO 178/15`, `KIO 520/21`, `KIO 293/21` w jednolitym wzorcu
    „(tak: wyrok z dnia 27 stycznia 2022 r., KIO 113/22)” (ARCHITEKTURA 3.5). Zdanie
    wokół sygnatury jest odtworzone z tego samego miejsca dokumentu, bo to właśnie data
    („27 stycznia 2022 r.”) jest sąsiadem, przy którym łatwo o fałszywe dopasowanie.
    """
    fragment_uzasadnienia = (
        "(tak: wyrok z dnia 27 stycznia 2022 r., KIO 113/22), a także KIO 835/22, "
        "KIO 115/22, KIO 178/15, KIO 520/21 oraz KIO 293/21."
    )

    assert normalize_signature_list(fragment_uzasadnienia) == [
        "KIO 113/22",
        "KIO 835/22",
        "KIO 115/22",
        "KIO 178/15",
        "KIO 520/21",
        "KIO 293/21",
    ]


def test_data_w_sasiedztwie_sygnatury_nie_tworzy_falszywej_sprawy() -> None:
    """Rok w dacie nie może zostać odczytany jako numer sprawy.

    Ten sam fragment co wyżej (ARCHITEKTURA 3.5). Cicha strata miałaby tu odwrotny znak
    niż zwykle: nie zgubienie sprawy, lecz **dopisanie nieistniejącej** do `cases`.
    """
    sygnatury = normalize_signature_list("wyrok z dnia 27 stycznia 2022 r., KIO 113/22")

    assert sygnatury == ["KIO 113/22"], (
        f"Z fragmentu z datą wyszło coś innego niż jedno cytowanie: {sygnatury!r}"
    )


def test_normalize_signature_na_napisie_wielosygnaturowym_oddaje_tylko_pierwsza_sprawe() -> None:
    """Strażnik hazardu, nie potwierdzenie poprawności — czytać razem z komentarzem.

    `normalize_signature` używa `re.search`, więc na napisie niosącym dwie sprawy zwraca
    **pierwszą i nie sygnalizuje niczego**. Jest to ten sam kształt straty, przed którym
    ostrzega ARCHITEKTURA 3.1, tyle że wewnątrz modułu, który ma go nie dopuścić: wywołanie
    `normalize_signature` na tekście poziomu dokumentu (pozycja `<li>` z `Details`, tytuł
    rekordu SAOS) gubi drugą sprawę po cichu.

    Test przybija bieżące zachowanie celowo. Jeśli ktoś zmieni `normalize_signature` tak,
    by wejście wielosygnaturowe odrzucała albo zgłaszała, ten test padnie — i dobrze:
    zmiana kontraktu jedynego producenta tożsamości ma być decyzją widoczną, nie skutkiem
    ubocznym. Do czasu takiej decyzji obowiązuje reguła: tekst poziomu dokumentu idzie
    wyłącznie przez `normalize_signature_list`.
    """
    tytul_rekordu_saos = "KIO 233/18, KIO 234/18"  # ARCHITEKTURA 1.4, saos.org.pl/judgments/354301

    pojedyncza = normalize_signature(tytul_rekordu_saos)
    lista = normalize_signature_list(tytul_rekordu_saos)

    assert pojedyncza == "KIO 233/18"
    assert lista == ["KIO 233/18", "KIO 234/18"]
    assert [pojedyncza] != lista, (
        "Obie funkcje zgadzają się na napisie wielosygnaturowym — znaczy to, że kontrakt "
        "jednej z nich się zmienił i komentarz przy tym teście jest nieaktualny."
    )


def test_sygnatura_w_srodku_zdania_jest_znajdowana_a_nie_pomijana() -> None:
    """Druga strona tego samego `re.search` — i powód, dla którego nie wolno go zamienić.

    Test wyżej pokazuje koszt wyszukiwania „gdziekolwiek w napisie": na tekście
    wielosygnaturowym wygrywa pierwsza sprawa. Ten test pokazuje, za co ten koszt jest
    płacony: `parser/cite.py` puszcza przez normalizator zdania z uzasadnienia, gdzie
    sygnatura stoi w środku, a nie na początku (ARCHITEKTURA 3.5, wzorzec
    „(tak: wyrok z dnia 27 stycznia 2022 r., KIO 113/22)” z dokumentu `KIO 65/23`).
    Zakotwiczenie wzorca na początku napisu zamieniłoby każde takie cytowanie w `None` —
    czyli w tysiące krawędzi grafu cytowań zgubionych bez jednego komunikatu.

    Obie asercje razem trzymają kompromis w widocznym miejscu: zmiana `search` na `match`
    psuje ten test, zmiana na „odrzucaj napisy wielosygnaturowe" psuje tamten.
    """
    zdanie_z_uzasadnienia = "(tak: wyrok z dnia 27 stycznia 2022 r., KIO 113/22)"

    assert normalize_signature(zdanie_z_uzasadnienia) == "KIO 113/22"
    assert normalize_signature("skarga na wyrok KIO 113/22") == "KIO 113/22"


def test_sygnatura_bez_wlasnego_prefiksu_nie_jest_odzyskiwana() -> None:
    """Granica odzyskiwania spraw: prefiks musi stać przy każdej sygnaturze.

    Napis poniżej jest **jawnie sztuczny** — skrócony zapis „KIO 233/18 i 234/18” nie
    pochodzi z żadnego odczytu w audycie ani w architekturze; obie sprawy są prawdziwe
    (rekord SAOS 354301), sklejenie ich w ten sposób jest konstrukcją testu. Test nie
    twierdzi więc, że źródło tak zapisuje — mierzy, gdzie kończy się odzyskiwanie spraw
    przez `normalize_signature_list`, bo to jest dokładnie miejsce, w którym mina 1
    mogłaby wrócić: druga sprawa znika i nic tego nie liczy.
    """
    zapis_skrocony_sztuczny = "KIO 233/18 i 234/18"

    assert normalize_signature_list(zapis_skrocony_sztuczny) == ["KIO 233/18"], (
        "Zmieniło się zachowanie na zapisie skróconym. Jeśli funkcja zaczęła odzyskiwać "
        "„234/18” przez dziedziczenie prefiksu — to jest zgadywanie organu z samego numeru, "
        "czego moduł świadomie nie robi (docstring modułu)."
    )


# --------------------------------------------------------------------------------------
# Kontrakty negatywne z docstringa modułu: czego ten moduł świadomie NIE robi
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sygnatura_obcego_organu", "organ"),
    [
        # ARCHITEKTURA 4.5, opis `parser/cite.py`: wzorce, na których pracuje `extract`,
        # wymienione razem z organem. Dla `docid.py` są to przypadki negatywne — moduł
        # obsługuje wyłącznie KIO i nie wolno mu przemilczeć cudzej sygnatury jako swojej.
        ("sygn. akt XXIII Ga 365/17", "sąd okręgowy"),
        ("III CZP 56/17", "Sąd Najwyższy"),
        ("C-652/22", "TSUE"),
    ],
)
def test_sygnatura_obcego_organu_nie_jest_kanonizowana(
    sygnatura_obcego_organu: str, organ: str
) -> None:
    """Moduł nie zgaduje organu: cudza sygnatura wychodzi jako `None`, nie jako KIO.

    Fałszywe dopasowanie byłoby tu najgorszym rodzajem cichej straty — sprawa z innego
    organu (`{organ}`) wylądowałaby w `cases` jako sprawa Izby.
    """
    assert normalize_signature(sygnatura_obcego_organu) is None
    assert normalize_signature_list(sygnatura_obcego_organu) == []


def test_z_tekstu_mieszanego_wychodzi_tylko_sygnatura_kio() -> None:
    """Obecność cudzej sygnatury obok własnej nie psuje żadnej ze stron.

    Oba wzorce z ARCHITEKTURA 4.5 (`XXIII Ga 365/17` — SO) i ARCHITEKTURA 3.5
    (`KIO 113/22` — cytowanie z uzasadnienia `KIO 65/23`).
    """
    tekst = "skarga na wyrok KIO 113/22, sygn. akt XXIII Ga 365/17"

    assert normalize_signature_list(tekst) == ["KIO 113/22"]


def test_nazwa_pliku_wielosygnaturowego_nie_daje_zgadnietych_sygnatur() -> None:
    """Numery bez prefiksu zostają numerami — moduł nie dorabia do nich organu.

    Odczyt: listing archiwum FTP zawiera `2021_1820_1821_1834.pdf` (818 KB), plik łączący
    kilka sygnatur w jednym dokumencie (AUDYT 2.4, weryfikacja 2026-09-14). Kusi, żeby
    wyprowadzić z tej nazwy `KIO 1820/21`, `KIO 1821/21`, `KIO 1834/21` — i to byłaby mina
    4 w czystej postaci: trzy sygnatury, które przejdą każdy test formatu, a których nikt
    nie odczytał ze źródła. Pusta lista jest tu poprawnym wynikiem; sprawy z tego pliku
    ustala parser nazw plików, nie normalizator sygnatur.
    """
    assert normalize_signature_list("2021_1820_1821_1834.pdf") == []
    assert normalize_signature("2021_1820_1821_1834.pdf") is None


@pytest.mark.parametrize(
    ("sygnatura", "rok_dwucyfrowy"),
    [
        # AUDYT 2.4: najstarsze orzeczenia w bazie, rocznik 2007 — Izba zaczęła orzekać
        # 5 grudnia 2007. AUDYT 2.2: `id=30442` → KIO 3019/25, 9 września 2025.
        ("KIO/UZP 5/07", "07"),
        ("KIO/UZP 2/07", "07"),
        ("KIO 3019/25", "25"),
    ],
)
def test_rok_zostaje_dwucyfrowy(sygnatura: str, rok_dwucyfrowy: str) -> None:
    """Moduł nie rozwija roku do czterech cyfr i to jest kontrakt, nie niedoróbka.

    Rozwinięcie „07” do „2007” wymaga wiedzy, że nie ma sygnatur sprzed 2007 — a to jest
    fakt o organie (Izba przejęła kompetencje 5 grudnia 2007, AUDYT 2.4), nie o zapisie
    sygnatury. Dokładanie go tutaj byłoby dokładaniem informacji, której w źródle nie ma.
    """
    kanoniczna = normalize_signature(sygnatura)

    assert kanoniczna is not None
    assert kanoniczna.endswith(f"/{rok_dwucyfrowy}")
    assert f"/20{rok_dwucyfrowy}" not in kanoniczna
    assert f"/19{rok_dwucyfrowy}" not in kanoniczna


def test_sygnatura_z_rokiem_czterocyfrowym_nie_jest_po_cichu_przycinana() -> None:
    """Zapis z rokiem czterocyfrowym odpada jawnie, zamiast zamienić się w inną sprawę.

    Napis `KIO 827/2018` jest **jawnie sztuczny**: sprawa `KIO 827/18` pochodzi z odczytu
    (ARCHITEKTURA 4.4, komentarz przy `cases.signature`), ale zapis roku czterema cyframi
    nie występuje w żadnym odczycie — jest konstrukcją testu. Chodzi o to, co się dzieje
    przy dopasowaniu częściowym: gdyby wzorzec przyciął rok do „20”, powstałaby sygnatura
    `KIO 827/20`, czyli **inna, wyglądająca poprawnie sprawa**. `None` trafia do
    `citations` z `signature_norm = NULL` i zostaje policzone w raporcie pokrycia —
    jawna dziura zamiast cichej podmiany.
    """
    assert normalize_signature("KIO 827/2018") is None


def test_sygnatura_nieistniejacej_sprawy_normalizuje_sie_tak_samo_jak_kazda_inna() -> None:
    """Moduł nie sprawdza, czy sprawa istnieje — i nie wolno mu tego udawać.

    Napis `KIO 1234/25` jest przykładem podanym wprost w audycie (zasada 7.1) jako zapis,
    który „wygląda tak samo niezależnie od tego, czy istnieje”. Używamy go tu dokładnie
    w tej roli: normalizacja przechodzi, bo istnienie sprawy rozstrzyga korpus, a nie
    wyrażenie regularne. Test istnieje po to, żeby nikt nie dopisał tu „walidacji”, która
    brzmiałaby jak potwierdzenie istnienia.
    """
    assert normalize_signature("KIO 1234/25") == "KIO 1234/25"


@pytest.mark.parametrize(
    "napis_bez_sygnatury",
    [
        "",
        "   ",
        "Uzasadnienie",
        "Przewodniczący: Prezes Krajowej Izby Odwoławczej",  # ARCHITEKTURA 1.4, wartość z Details
        "Tryb postępowania: brak danych",  # ARCHITEKTURA 1.4, wartość z Details
    ],
)
def test_napis_bez_sygnatury_zwraca_none_zamiast_rzucac(napis_bez_sygnatury: str) -> None:
    """Brak sygnatury to wynik, nie wyjątek — inaczej parser cytowań by się zatrzymał.

    `parser/cite.py` puszcza przez normalizator tekst uzasadnienia, gdzie większość
    napisów sygnaturą nie jest (docstring `normalize_signature`). Wyjątek w tym miejscu
    zatrzymywałby potok na pierwszym zdaniu. Dwie ostatnie wartości pochodzą z odczytu
    metryki `Details` (ARCHITEKTURA 1.4) i są wartościami, nie błędami.
    """
    assert normalize_signature(napis_bez_sygnatury) is None
    assert normalize_signature_list(napis_bez_sygnatury) == []


def test_zera_wiodace_w_numerze_schodza_do_jednej_postaci() -> None:
    """Numer bez zer wiodących, żeby dopełnienie nie tworzyło drugiego klucza.

    Napis `KIO 0095/16` jest **jawnie sztuczny**. Pytanie o zera wiodące jest prawdziwe
    i ma odczyt — listing FTP dopełnia numer zerami do czterech cyfr, co przesądza plik
    `2016_0095.doc` (AUDYT 2.4) — ale dopełnienie udokumentowano na **nazwach plików**,
    nie na sygnaturach; żadnego odczytu sygnatury z zerem wiodącym w dokumentach nie ma.
    Test mierzy więc samo zachowanie normalizatora: obie pisownie muszą dać jeden klucz,
    bo inaczej sprawa z kanału FTP i ta sama sprawa z wyszukiwarki rozjechałyby się na
    dwa wiersze w `cases`.
    """
    z_dopelnieniem_sztuczne = "KIO 0095/16"

    assert normalize_signature(z_dopelnieniem_sztuczne) == "KIO 95/16"
    assert normalize_signature_list(f"{z_dopelnieniem_sztuczne}, KIO 95/16") == ["KIO 95/16"]


def test_lista_zwraca_pusta_liste_a_nie_none() -> None:
    """Pusty wynik ma być policzalny, nie fałszywy.

    Raport pokrycia liczy cytowania, których nie dało się znormalizować (docstring
    `normalize_signature`). `None` zamiast `[]` zamieniłby „zero sygnatur” w wyjątek
    albo w cichy pominięty rekord po stronie wywołującego.
    """
    wynik = normalize_signature_list("tekst bez żadnej sygnatury")

    assert wynik == []
    assert isinstance(wynik, list)


# --------------------------------------------------------------------------------------
# `document_id` — tożsamość dokumentu, czyli mina 1 w drugim miejscu naraz
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kanal", "ref", "oczekiwany"),
    [
        # ARCHITEKTURA 1.1 i 4.4 (komentarz przy `documents.doc_id`): trzy postacie wprost
        # z dokumentu — `uzp:9620`, `atlas:kio-827-18`, `saos:354301`. Identyfikator `9620`
        # i slug `kio-827-18` opisują to samo orzeczenie w dwóch kanałach (ARCHITEKTURA 1.1).
        ("uzp", "9620", "uzp:9620"),
        ("atlas", "kio-827-18", "atlas:kio-827-18"),
        ("saos", "354301", "saos:354301"),
        # AUDYT 5.1/5.3: dokument `KIO 704/23` pod identyfikatorem wewnętrznym 19308.
        ("uzp", "19308", "uzp:19308"),
        # ARCHITEKTURA 1.2: `KIO 2924/21` to nadal `15903` po przebudowie z lipca 2026.
        ("uzp", "15903", "uzp:15903"),
    ],
)
def test_identyfikator_dokumentu_ma_postac_kanal_dwukropek_referencja(
    kanal: str, ref: str, oczekiwany: str
) -> None:
    """Postaci z odczytu składają się dokładnie tak, jak opisuje schemat `documents`."""
    assert document_id(SourceName(kanal), ref) == oczekiwany


@pytest.mark.parametrize(
    ("kanal_zapisany", "ref"),
    [
        ("UZP", "9620"),
        ("Uzp", "9620"),
        ("  uzp  ", "9620"),
        ("uzp", "  9620  "),
        ("\tUZP\n", "\t9620\n"),
    ],
)
def test_pisownia_kanalu_nie_tworzy_drugiego_identyfikatora(kanal_zapisany: str, ref: str) -> None:
    """Nazwa kanału schodzi do małych liter i traci obramowanie z białych znaków.

    To jest bezpośrednia odpowiedź na minę 1: w CEIDG to właśnie wrażliwy na wielkość
    liter klucz główny kazał zapisywać każdy zmieniony wpis dwa razy. Identyfikator
    `uzp:9620` pochodzi z odczytu (ARCHITEKTURA 1.1); zmieniona jest tylko pisownia.
    """
    assert document_id(SourceName(kanal_zapisany), ref) == "uzp:9620"


def test_wielkosc_liter_w_referencji_kanalu_wciaz_tworzy_dwa_identyfikatory() -> None:
    """Strażnik hazardu: składanie tożsamości jest odporne na pisownię tylko po jednej stronie.

    `document_id` sprowadza do małych liter **kanał**, a referencję zostawia bez zmiany —
    zgodnie z komentarzem w schemacie (`source_ref TEXT -- identyfikator w kanale, tak jak
    przyszedł`, ARCHITEKTURA 4.4). Skutek jest jednak taki, że dla kanału, w którym
    referencją jest slug tekstowy, a nie liczba, wraca dokładnie kształt miny 1: dwa zapisy
    tego samego dokumentu dają dwa różne klucze główne, cache nigdy nie trafia, a wpis
    zapisuje się dwa razy. Ryzyko jest realne tylko dla Atlasu — `uzp:9620` i `saos:354301`
    mają referencje liczbowe, `atlas:kio-827-18` jest slugiem (ARCHITEKTURA 1.1, 4.4).

    Test przybija bieżące zachowanie i zostawia ślad. Jeśli ktoś zacznie sprowadzać
    referencję do małych liter, ten test padnie — i wtedy trzeba świadomie rozstrzygnąć,
    czy „tak jak przyszedł” ze schematu nadal obowiązuje, zamiast zmieniać klucz główny
    korpusu mimochodem.
    """
    z_odczytu = document_id(SourceName("atlas"), "kio-827-18")
    ta_sama_sprawa_inna_pisownia_sztuczna = document_id(SourceName("atlas"), "KIO-827-18")

    assert z_odczytu == "atlas:kio-827-18"
    assert ta_sama_sprawa_inna_pisownia_sztuczna != z_odczytu, (
        "Referencja przestała być wrażliwa na wielkość liter. To zmiana klucza głównego "
        "`documents.doc_id`, a nie drobiazg — wymaga decyzji wobec komentarza "
        "„tak jak przyszedł” w schemacie (ARCHITEKTURA 4.4)."
    )


def test_dwukropek_w_referencji_przechodzi_i_rozmywa_granice_skladnikow() -> None:
    """Strażnik hazardu: zakaz dwukropka obowiązuje tylko po stronie kanału.

    `document_id` odrzuca dwukropek w nazwie kanału, ale w referencji go przepuszcza.
    Powstały identyfikator ma trzy człony i nie da się go jednoznacznie rozłożyć z powrotem
    na `(kanał, referencja)` naiwnym podziałem po dwukropku — a to jest operacja, którą
    kod czytający `documents.doc_id` wykona odruchowo.

    Referencja `96:20` jest **jawnie sztuczna**: żaden z odczytanych kanałów nie zwraca
    referencji z dwukropkiem (`9620`, `19308`, `15903`, `kio-827-18`, `354301`). Test nie
    twierdzi więc, że takie dane istnieją — pilnuje asymetrii w samej bramce, żeby nie
    została odkryta dopiero przez kanał, którego jeszcze nie ma.
    """
    with pytest.raises(IdentityError, match="dwukropka"):
        document_id(SourceName("u:zp"), "9620")

    assert document_id(SourceName("uzp"), "96:20") == "uzp:96:20", (
        "Referencja z dwukropkiem przestała przechodzić. Jeśli to zamierzona zmiana, "
        "bramka jest teraz symetryczna i ten komentarz trzeba usunąć."
    )


@pytest.mark.parametrize(
    ("kanal", "ref"),
    [
        ("", "9620"),
        ("uzp", ""),
        ("   ", "9620"),
        ("uzp", "   "),
        ("", ""),
        ("\t\n", "\t\n"),
    ],
)
def test_pusty_skladnik_tozsamosci_konczy_sie_bledem_a_nie_kaleka_tozsamoscia(
    kanal: str, ref: str
) -> None:
    """Brakujący składnik zatrzymuje zapis, zamiast wyprodukować klucz w rodzaju `uzp:`.

    Identyfikator `„uzp:”` albo `„:9620”` przeszedłby przez każdą walidację formatu
    i zebrał pod sobą wszystkie dokumenty kanału. To jest odpowiednik wiersza raportu bez
    numeru z CEIDG, opisanego w minie 1: klucz liczony z czegoś, czego w danych nie ma,
    daje tożsamość, która niczego nie identyfikuje. Błąd musi paść przed zapisem.
    """
    # Komunikat jest inny dla każdej ze stron („Pusta nazwa kanału" wobec „Pusty
    # identyfikator dokumentu"), bo od 2026-09-15 kanał i referencja mają osobne bramki.
    # Dopasowanie po wspólnym rdzeniu, żeby test pilnował zachowania, a nie brzmienia zdania.
    with pytest.raises(IdentityError, match="Pust"):
        document_id(SourceName(kanal), ref)


def test_sygnatura_nie_jest_tozsamoscia_dokumentu() -> None:
    """Dwa kanały opisujące to samo orzeczenie mają dwie tożsamości, a nie jedną.

    Odczyt: `uzp:9620` i `atlas:kio-827-18` opisują to samo orzeczenie i łączyły się dotąd
    „tylko przez wspólną sygnaturę, co przy dokumentach wielosygnaturowych i sprostowaniach
    jest za słabe" (ARCHITEKTURA 1.1). Równoważność jest **stwierdzana** w tabeli
    `equivalences` przez polecenie `porownaj`, nigdy zakładana — więc `document_id` ma tu
    dać dwa różne klucze i nie próbować ich scalać.
    """
    z_uzp = document_id(SourceName("uzp"), "9620")
    z_atlasu = document_id(SourceName("atlas"), "kio-827-18")

    assert z_uzp != z_atlasu
    assert z_uzp.split(":", 1)[0] != z_atlasu.split(":", 1)[0]


def test_identyfikator_dokumentu_nie_powstaje_z_sygnatury() -> None:
    """Sygnatura kanoniczna nie przecieka do tożsamości dokumentu.

    Jeden dokument nosi kilka sygnatur (rekord SAOS 354301: „KIO 233/18, KIO 234/18”,
    ARCHITEKTURA 1.4), a jedna sygnatura bywa na kilku dokumentach (postanowienie i wyrok
    w tej samej sprawie; sprostowanie — pomiar 7). Gdyby `document_id` przyjmowało
    sygnaturę jako referencję bez śladu, dokument wielosygnaturowy dostałby tożsamość
    jednej ze swoich spraw — wybraną przez kolejność, czyli przez przypadek.
    """
    sygnatury = normalize_signature_list("KIO 233/18, KIO 234/18")
    assert len(sygnatury) == 2

    identyfikator_z_odczytu = document_id(SourceName("saos"), "354301")

    for sygnatura in sygnatury:
        assert sygnatura not in identyfikator_z_odczytu


def test_typ_sygnatury_pozostaje_napisem_o_postaci_kanonicznej() -> None:
    """`Signature` jest `NewType` nad `str` — w czasie wykonania to nadal napis.

    Reguły 14 („jeden producent tożsamości”) pilnuje `mypy --strict`, a nie warstwa
    wykonania: skan AST widzi importy, nie konkatenację napisów (docstring `Signature`).
    Test odnotowuje, że w czasie wykonania nie ma tu żadnego strażnika — jedynym jest
    typowanie statyczne, więc `mypy --strict` w bramce nie jest opcjonalny.
    """
    sygnatura = normalize_signature("KIO 827/18")  # ARCHITEKTURA 4.4, `cases.signature`

    assert isinstance(sygnatura, str)
    assert Signature("KIO 827/18") == "KIO 827/18"
