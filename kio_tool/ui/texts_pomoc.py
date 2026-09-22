"""Zdania pomocy przy poleceniach i flagach CLI — część `ui/texts.py` wydzielona 2026-09-22.

Wydzielone, gdy `texts.py` doszedł do 763 linii przy suficie 800, a polecenia `czytaj`, `opis`
i flaga `--wycena` dokładały zdań. Szew jest prawdziwy: pomoc to zdania o **narzędziu**, pisane
raz dla `--help` i dla `opis --json`, a reszta `texts` to zdania o **wyniku**. Moduł czysty jak
`texts` (reguła 6); `texts` re-eksportuje wszystkie nazwy, więc `help=texts.POMOC_…` w `cli.py`
(reguła 9) działa bez zmian.
"""

from __future__ import annotations

POMOC_PROGRAMU = "kio-tool — lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej."
POMOC_POBIERZ = (
    "Pobiera orzeczenia według kryteriów do lokalnej bazy i eksportuje wynik. Przebieg przerwany "
    "(Ctrl+C, błąd sieci, brak zgody) wznawia się tym samym poleceniem albo przez `wznow`, "
    "bez duplikatów."
)
POMOC_WZNOW = (
    "Wznawia przerwany przebieg od ostatniej strony listy — podany przez --run-id albo ostatni "
    "przerwany. Kryteria bierze z bazy, nie z flag."
)
POMOC_EKSPORTUJ = (
    "Eksportuje z lokalnej bazy, bez żadnego żądania do sieci: dokumenty objęte przebiegiem "
    "(--run-id) albo pasujące do kryteriów (--od, --do, --fraza …)."
)
POMOC_RUNY = "Wypisuje ostatnie przebiegi z bazy: status, zakres, liczbę dokumentów i żądań."
POMOC_KREATOR = (
    "Kreator dla operatora: menu, pytania i tabela kosztów przed każdym pobraniem. To samo "
    "otwiera `kio-tool` bez polecenia na terminalu."
)
POMOC_DEMO = (
    "Tryb pokazowy: kreator nad fikcyjnym korpusem generowanym w procesie — bez sieci, bez adresu "
    "kontaktowego, w osobnym katalogu danych. Ta sama ścieżka co na danych prawdziwych."
)
POMOC_OD_NOWA = "zacznij pokaz od pustej bazy (kasuje wyłącznie bazę trybu pokazowego)"
POMOC_PRZELICZ = (
    "Przelicza metadane i indeks pełnotekstowy z surowych wersji w bazie — zero żądań do sieci."
)
POMOC_POKRYCIE = (
    "Raport pokrycia parsera z bazy (sekcje, cytowania, przepisy po roczniku z sygnatury) do "
    "`docs/raporty/` — zero żądań, bez tekstu orzeczeń; z `--zloty` sprawdza adnotacje złotego "
    "zbioru."
)
POMOC_CEL_RAPORTU = "katalog raportu (domyślnie `docs/raporty` w bieżącym katalogu)"
POMOC_ZLOTY = "katalog złotego zbioru (`tests/gold`) — adnotacje sprawdzane wobec korpusu"
POMOC_SZUKAJ = (
    "Szuka frazy dosłownie w pełnym tekście korpusu lokalnego (FTS5) z filtrami; wynik zawsze "
    "mówi, ile dokumentów objął."
)

POMOC_OD = "początek zakresu dat wydania, RRRR-MM-DD (włącznie)"
POMOC_DO = "koniec zakresu dat wydania, RRRR-MM-DD (włącznie)"
POMOC_FRAZA = (
    "fraza szukana dosłownie: lokalnie w pełnym tekście (`szukaj`, `eksportuj`); w `pobierz` "
    "idzie do wyszukiwarki kanału, która u Atlasu dopasowuje sygnaturę, nie treść (zmierzone "
    "2026-09-18)"
)
POMOC_ROZSTRZYGNIECIE = (
    "rozstrzygnięcie (można powtórzyć przy szukaniu i eksporcie): oddalono, uwzglednione, "
    "umorzono, odrzucono, inne — lista zmierzona na stu rekordach, nie udokumentowana"
)
POMOC_RODZAJ = "rodzaj orzeczenia (można powtórzyć lokalnie): wyrok albo postanowienie"
POMOC_PRZEPIS = "przepis w zapisie kanału, np. „art. 226 ust. 1 pkt 5 Pzp” (podnapis)"
POMOC_PRZEWODNICZACY = "przewodniczący składu (podnapis nazwiska)"
POMOC_STRONA = "strona postępowania — odwołujący albo zamawiający (podnapis nazwy)"
POMOC_MAKS = "najwyżej tyle kandydatów w przebiegu — ogranicza koszt u cudzego serwisu"
POMOC_FORMAT = "formaty eksportu po przecinku: xlsx, csv, jsonl, md (domyślnie xlsx)"
POMOC_OUT = (
    "rdzeń nazwy plików wyniku, bez rozszerzenia (np. `--out C:\\dane\\styczen` daje "
    "`styczen.xlsx`); istniejący katalog dostaje plik o nazwie domyślnej w środku; bez flagi — "
    "katalog `wyniki/` obok bazy"
)
POMOC_CEL = "cel pobrania — zdanie zapisywane w arkuszu Metadane, nigdzie indziej"
POMOC_BAZA = "plik bazy SQLite; domyślnie w katalogu danych użytkownika, poza repozytorium"
POMOC_KANAL = "kanał akwizycji (dziś wyłącznie `atlas`)"
POMOC_ZGODA = (
    "zgoda właściciela na przebieg masowy — obowiązuje w tej sesji i nie da się jej zapisać "
    "w konfiguracji; bez niej narzędzie wysyła najwyżej kilkadziesiąt żądań"
)
POMOC_RUN_ID = "identyfikator przebiegu z `runy`; można powtórzyć"
POMOC_RUN_ID_JEDEN = "identyfikator przebiegu z `runy`; bez niego — ostatni przerwany"
POMOC_LIMIT = "ile wierszy pokazać"
POMOC_STATUS = "tylko przebiegi w tym stanie: w_toku, zakonczony, przerwany, blad (można powtórzyć)"
POMOC_WSZYSTKO = "przelicz także wersje już przeliczone bieżącą wersją odczytu"
POMOC_CZYTAJ = (
    "Pokazuje jedno orzeczenie z korpusu lokalnego po sygnaturze albo `doc_id`: metadane, blok "
    "cytowania, mapę sekcji z długościami i treść — całą albo wybranych sekcji. Zero żądań."
)
POMOC_KLUCZ = (
    "sygnatura (np. „KIO 3810/23”) albo `doc_id` z wyniku `szukaj` (np. atlas:kio-3810-23)"
)
POMOC_SEKCJA = (
    "tylko te sekcje (można powtórzyć): naglowek, sentencja, pouczenie, uzasadnienie, "
    "zdanie_odrebne, nieprzypisane"
)
POMOC_BEZ_TRESCI = "bez treści — same metadane i mapa sekcji z długościami"
POMOC_WYCENA = (
    "tylko koszt: jedna strona listy, zero żądań o dokument; przebieg zostaje przerwany do "
    "dokończenia tym samym poleceniem z --zgoda"
)
POMOC_JSON = (
    "wynik jako JSON Lines na standardowe wyjście, jeden dokument na wiersz — dla programu, "
    "nie dla oka; tabela dla człowieka bez terminala łamie wartości na 80 znakach"
)

__all__ = [
    "POMOC_PROGRAMU",
    "POMOC_POBIERZ",
    "POMOC_WZNOW",
    "POMOC_EKSPORTUJ",
    "POMOC_RUNY",
    "POMOC_KREATOR",
    "POMOC_DEMO",
    "POMOC_OD_NOWA",
    "POMOC_PRZELICZ",
    "POMOC_POKRYCIE",
    "POMOC_CEL_RAPORTU",
    "POMOC_ZLOTY",
    "POMOC_SZUKAJ",
    "POMOC_OD",
    "POMOC_DO",
    "POMOC_FRAZA",
    "POMOC_ROZSTRZYGNIECIE",
    "POMOC_RODZAJ",
    "POMOC_PRZEPIS",
    "POMOC_PRZEWODNICZACY",
    "POMOC_STRONA",
    "POMOC_MAKS",
    "POMOC_FORMAT",
    "POMOC_OUT",
    "POMOC_CEL",
    "POMOC_BAZA",
    "POMOC_KANAL",
    "POMOC_ZGODA",
    "POMOC_RUN_ID",
    "POMOC_RUN_ID_JEDEN",
    "POMOC_LIMIT",
    "POMOC_STATUS",
    "POMOC_WSZYSTKO",
    "POMOC_CZYTAJ",
    "POMOC_KLUCZ",
    "POMOC_SEKCJA",
    "POMOC_BEZ_TRESCI",
    "POMOC_WYCENA",
    "POMOC_JSON",
]
