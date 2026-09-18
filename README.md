# kio-tool

Narzędzie budujące **lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej**:
pobiera orzeczenia z pełnym tekstem z publicznego API Atlasu Przetargów, zapisuje je w bazie
SQLite tak, jak przyszły, wyciąga z nich metadane, indeksuje pełny tekst i eksportuje wynik
do skoroszytu Excel, CSV, JSONL albo katalogu Markdown — zawsze z atrybucją źródła.

**Status na 2026-09-18 (wieczór): faza 1 zamknięta, narzędzie pracuje.** Bramka fazy 0 padła
po pomiarach 3a i 23 (ADR-0004 i ADR-0001 przyjęte, kanał `atlas`), a bramka fazy 1 tego samego
dnia: pierwszy korpus — styczeń 2024, 295 orzeczeń z pełnym tekstem, 302 żądania, przebieg
przerwany na progu zgody i wznowiony tym samym poleceniem, trzecie wywołanie bez jednego żądania
za dokument (`docs/decisions.md`, „Przebieg 1"). Nie ma jeszcze wykrywania zmian u źródła
(`aktualizuj`), drugiego kanału ani warstwy modelu — sekcja „Czego narzędzie nie robi" niżej.

Dokumenty: `docs/decisions.md` (wyniki i status pomiarów, decyzje właściciela),
`docs/adr/` (decyzje architektoniczne), `docs/AUDYT_KIO_ORZECZENIA.md` (stan źródła,
dopuszczalność, doktryna), `docs/ARCHITEKTURA_KIO_TOOL.md` (architektura, reguły granic,
polecenia), `docs/raport_przekazania.md` (raport dla nowej osoby), `CLAUDE.md` (fakty
o projekcie dla Claude Code).

## Po co to powstaje

Orzecznictwo KIO jest publiczne, ale Urząd nie udostępnia do niego żadnego udokumentowanego
interfejsu programistycznego: jest wyszukiwarka WWW, serwer FTP z archiwum przestał publikować
30 września 2025 i dziś nie odpowiada, a jedyne API oferuje pośrednik prywatny — Atlas Przetargów,
który ponowne wykorzystywanie licencjonuje wprost (CC BY 4.0, odczytane u dostawcy 2026-09-18).
Kto chce policzyć cokolwiek na całości orzecznictwa — a nie przeczytać jedno orzeczenie — nie
ma dziś czym.

Dla potrzeby „wyszukać i przeczytać" budowa nie ma uzasadnienia: Atlas robi to za darmo, SzuKIO
i wydawnictwa prawnicze odpłatnie. Sens jest węższy i tylko taki: **programowy dostęp do korpusu
pod własny potok przetwarzania** — analizy, zestawienia, cytowania, w przyszłości warstwa modelu.

Jednostką nie jest rekord, tylko **dokument**: kilkanaście stron polszczyzny prawniczej ze
strukturą wewnętrzną, której nie da się sensownie zmieścić w komórce arkusza. Dlatego skoroszyt
niesie metadane i długość tekstu, a sam tekst leży w bazie, w JSONL i w Markdownie.

## Instalacja

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Wymaga Pythona 3.12. Testy działają przy **zablokowanej sieci** (`--block-network` w konfiguracji
pytest, egzekwowane na poziomie gniazda) — żaden test nie wysyła żądania do cudzego serwisu.

## Adres kontaktowy i klucz

Każde żądanie do prawdziwego źródła niesie `User-Agent` z adresem kontaktowym operatora —
żeby administrator serwisu miał jak napisać, gdy coś pójdzie nie tak. Bez zmiennej
`KIO_TOOL_CONTACT` klient HTTP się nie zbuduje i to jest odmowa zamierzona, nie usterka.
Adres trafia wyłącznie do nagłówka; nie zapisuje się go w bazie, plikach wynikowych ani
w repozytorium.

```
set KIO_TOOL_CONTACT=twoj@adres          # cmd
$env:KIO_TOOL_CONTACT = "twoj@adres"     # PowerShell
```

Klucz API Atlasu jest opcjonalny: bez niego pośrednik daje 1500 żądań na dobę na adres IP,
z kontem 5000 (dokumentacja Atlasu, odczyt 2026-09-18). Klucz podaje się zmienną
`KIO_TOOL_ATLAS_KEY`; jest maskowany w każdym komunikacie i nigdy nie trafia do bazy.

## Zgoda na przebieg masowy

Pobranie powyżej **50 żądań** wymaga flagi `--zgoda`. Bez niej narzędzie wysyła najwyżej
kilkadziesiąt żądań, zatrzymuje się na progu, zapisuje przebieg jako `przerwany` i mówi, ile
dokumentów jest w zakresie — to samo polecenie z `--zgoda` wznawia go od miejsca zatrzymania.
Zgody nie da się zapisać w konfiguracji: obowiązuje w sesji, w której padła, bo ruch idzie do
cudzego serwera na cudzy koszt.

Narzędzie samo pilnuje tempa: odstęp co najmniej 1 s między żądaniami, okna 450 żądań na
minutę i 1400 na dobę (zawężone poniżej limitów pośrednika, bo limit liczy się na adres IP,
a nie na proces), budżet czytany z nagłówków `X-RateLimit-*`, a po odpowiedzi 429 albo `Retry-After`
przebieg staje i odczekuje wskazany czas przy wznowieniu. **Narzędzie nie omija zabezpieczeń**:
przy odmowie serwisu (CAPTCHA, blokada, wykrycie bota) zatrzymuje się i mówi o tym operatorowi.

## Użycie

```
.venv\Scripts\python.exe -m kio_tool.cli --help
.venv\Scripts\python.exe -m kio_tool.cli pobierz --od 2024-02-01 --do 2024-02-29 --zgoda
.venv\Scripts\python.exe -m kio_tool.cli pobierz --od 2024-01-01 --do 2024-01-31 --zgoda --format xlsx,jsonl,md --cel "analiza kosztów"
.venv\Scripts\python.exe -m kio_tool.cli pobierz --przepis "art. 226 ust. 1 pkt 5" --maks 40      # bez zgody: najwyżej 50 żądań
.venv\Scripts\python.exe -m kio_tool.cli wznow                                                   # ostatni przerwany przebieg
.venv\Scripts\python.exe -m kio_tool.cli wznow --run-id atlas-dd55fb768069 --zgoda
.venv\Scripts\python.exe -m kio_tool.cli runy --status przerwany
.venv\Scripts\python.exe -m kio_tool.cli eksportuj --run-id atlas-969ac406dd8f --format csv,md
.venv\Scripts\python.exe -m kio_tool.cli eksportuj --od 2024-01-01 --do 2024-01-31 --rodzaj wyrok --format xlsx
.venv\Scripts\python.exe -m kio_tool.cli przelicz                                                # indeks i metadane, zero żądań
.venv\Scripts\python.exe -m kio_tool.cli szukaj --fraza "odrzuca odwołanie" --rozstrzygniecie oddalono --limit 20
```

| Polecenie | Co robi | Żądań do sieci |
|---|---|---|
| `pobierz` | według kryteriów pobiera listę z Atlasu, a za każdy dokument, którego nie ma w bazie, jeden rekord z pełnym tekstem; zapisuje surowe bajty, metadane i indeks; na końcu eksportuje i drukuje podsumowanie | strony listy + 1 na nowy dokument |
| `wznow` | wznawia przerwany przebieg (`--run-id` albo ostatni) od zapisanej strony listy; kryteria bierze z bazy; dokumenty już zapisane pomija bez żądania | tylko brakujące |
| `eksportuj` | z bazy, bez sieci: dokumenty objęte przebiegiem (`--run-id`, można powtórzyć) **albo** pasujące do kryteriów; obu naraz odmawia | zero |
| `runy` | ostatnie przebiegi: status, zakres, liczba dokumentów i żądań (`--status`, `--limit`) | zero |
| `przelicz` | przelicza metadane i indeks pełnotekstowy z surowych wersji (`--wszystko` także już przeliczone) — po zmianie odczytu, bez ponownego pobierania | zero |
| `szukaj` | fraza dosłownie w pełnym tekście (FTS5) z filtrami; nad tabelą zawsze: dokumentów w korpusie, zaindeksowanych, trafień | zero |

Kryteria mają własne flagi i działają tak samo w `pobierz`, `eksportuj` i `szukaj`: `--od`/`--do`
(daty wydania, włącznie), `--fraza`, `--rozstrzygniecie` (oddalono, uwzglednione, umorzono,
odrzucono, inne — lista zmierzona na stu rekordach, nie udokumentowana), `--rodzaj` (wyrok,
postanowienie), `--przepis`, `--przewodniczacy`, `--strona` (podnapisy). W `pobierz` filtr idzie
do wyszukiwarki Atlasu pod nazwą z `contract.yaml` kanału; lokalnie ten sam filtr działa na
metadanych z bazy. `--maks` ogranicza liczbę kandydatów w przebiegu, `--cel` zapisuje zdanie
w arkuszu `Metadane` i nigdzie indziej, `--baza` zmienia miejsce bazy. `--out` jest rdzeniem
nazwy plików wyniku bez rozszerzenia (`--out C:\dane\styczen` daje `styczen.xlsx`); istniejący
katalog dostaje plik o nazwie domyślnej w środku. Ścieżka `--baza`, której jeszcze nie ma,
dostaje pustą bazę i zdanie o tym na ekranie — literówka nie wygląda wtedy jak utrata korpusu.

Każda pomyłka kończy się zdaniem po polsku i kodem wyjścia: 3 przy błędzie wywołania
(brak adresu, złe kryteria, literówka w identyfikatorze przebiegu, brak zgody), 2 przy błędzie
wznawialnym (sieć, serwis), 1 przy pozostałych, 130 po Ctrl+C. Pomyłki w samej składni
poleceń (`pobież`, `--limitt`) obsługuje biblioteka `typer` — jedyne zdania po angielsku
w narzędziu, też z kodem 2. Na Windowsie polskie znaki w wyjściu przekierowanym do pliku
wymagają `set PYTHONUTF8=1`.

Postęp długiej operacji liczy się w **żądaniach wysłanych i dokumentach zapisanych**, nigdy
w stronach; postoje limitera i odmowy serwisu są wypisywane, bo program, który milczy, bywa
zabijany w trakcie poprawnej pracy.

## Po przerwaniu

Przebieg przerwany przez Ctrl+C, brak zgody, błąd sieci albo odmowę serwisu zostaje w bazie ze
statusem `przerwany`, zapisaną ostatnią stroną listy i powodem. Wznawia go `wznow` albo to samo
polecenie `pobierz` z tymi samymi kryteriami (rozpoznane po odcisku kryteriów). Dokument, który
już jest w bazie, nie idzie drugi raz — klucz `(doc_id, sha256)` nie pozwala na duplikat nawet
przy nieaktualnym punkcie kontrolnym. Prośba serwisu o odczekanie (`Retry-After`) jest zapisana
w dzienniku żądań i przeżywa przerwanie: wznowienie odczekuje ją, zanim wyśle pierwsze żądanie.

**Zanik zasilania, ubicie procesu, pełny dysk.** Proces, który zginął bez sprzątania, nie zdąża
zapisać statusu — przebieg zostaje w bazie jako pracujący (`w_toku`) bez procesu, czyli
osierocony. To samo `pobierz` albo `wznow` rozpoznaje go, mówi o tym zdaniem i wznawia od
zapisanej strony; baza jest w trybie WAL, więc zapis przerwany w połowie dokumentu cofa się
w całości i liczniki tabel się zgadzają (zmierzone 2026-09-18 ubiciem procesu `taskkill /F`
w trakcie zapisu). Gdy nie da się zapisać nawet zakończenia przebiegu, powód przerwania zostaje
na ekranie, a przebieg jako osierocony. Dokument, który zniknął u pośrednika między listą
a pobraniem (404), jest liczony i pomijany, a przebieg idzie dalej — ale dziesięć kolejnych
404 zatrzymuje go jako złamany kontrakt, bo tak wygląda przeniesiony punkt końcowy, nie wycofane
sprawy. Odpowiedź z JSON-em uciętym w połowie jest traktowana jak zerwane łącze — przebieg jest
wznawialny, a nie zamknięty jako złamany kontrakt. Przebieg zakończony błędem (`blad`: wygasły
klucz, odmowa serwisu, złamany kontrakt) wznawia wyłącznie jawne `wznow --run-id`, bo stan bywa
ustępujący, a punkt kontrolny jest wart stron listy; automat do niego nie wraca.

Eksport przerwany w trakcie zapisu nie zostawia pliku, który wygląda na kompletny: plik
powstaje jako tymczasowy i jest podmieniany w całości; katalog Markdown tak samo. Powtórny
eksport Markdown pod to samo `--out` zastępuje poprzedni wynik, ale wyłącznie katalog z własnym
znacznikiem `.kio-tool-eksport` — cudzy katalog pod tą nazwą zostaje nietknięty i eksport
odmawia zdaniem.

Czego tu **nie ma**: automatycznych ponowień przy 429 i 5xx (przebieg staje właściwym wyjątkiem,
wznowienie jest świadome) oraz blokady między dwoma procesami na tej samej bazie — jedno
pobranie naraz jest obowiązkiem operatora, nie narzędzia; dlatego przebieg `w_toku` przy
wznawianiu znaczy „osierocony", a nie „inny proces pracuje".

## Gdzie są dane

Wszystko poza repozytorium, w katalogu danych użytkownika — na Windowsie
`%LOCALAPPDATA%\kio-tool\kio-tool\`:

| Miejsce | Co niesie | Dlaczego tu |
|---|---|---|
| `korpus.sqlite` | korpus: surowe wersje, dokumenty, metadane, indeks pełnotekstowy, przebiegi, dziennik żądań | orzeczenia niosą pełne nazwiska składu orzekającego i protokolantów; operator jest dla nich administratorem danych, więc korpus nie wchodzi do repozytorium |
| `wyniki/` | pliki eksportu (`--out` zmienia ścieżkę) | te same nazwiska, co w korpusie |
| `docs/dziennik_zadan.md` (w repozytorium) | ślad po każdym żądaniu **sondy fazy 0**, dopisywany w chwili powrotu żądania | pomiary są dowodami i zostają w historii repozytorium |
| `scripts/out/` (poza historią) | surowe odpowiedzi sondy | zawierają dane osobowe z rekordów |
| `tests/examples/atlas/` | złote pliki z pomiaru 3a z `ZRODLO.md` (licencja, SHA-256) | reguła 17: adapter jest testowany na prawdziwej odpowiedzi, nie na atrapie |

Po pierwszym korpusie (2026-09-18) baza ma 24,5 MB przy 295 dokumentach, z czego 11,5 MB to
surowe bajty odpowiedzi.

### Co jest w bazie i dlaczego

| Tabela | Zawartość | Powód istnienia |
|---|---|---|
| `raw_versions` | surowa odpowiedź kanału **w całości** (bajty, SHA-256, moment pobrania, nagłówki); klucz `(doc_id, sha256)` | reguła 19: łańcuch dowodowy — każdy wiersz pochodny da się przeliczyć z bajtów, które naprawdę przyszły; wersja nigdy nie jest nadpisywana |
| `documents` | tożsamość dokumentu `atlas:<slug>`, wszystkie sygnatury, data wydania, pierwsze i ostatnie widzenie, bieżąca wersja | ADR-0001: dokument jest jednostką, sygnatura etykietą (sprawy połączone mają kilka); slug małymi literami, żeby dwie pisownie nie dały dwóch dokumentów |
| `metadata` | pola odczytane z surowej wersji przez mapę z `contract.yaml`: sygnatura, daty, rodzaj, rozstrzygnięcie, przewodniczący, strony, przepisy, koszty, adres u źródła, długość tekstu; z numerem wersji odczytu | filtry i eksport bez czytania blobów; `przelicz` odtwarza tabelę po zmianie odczytu |
| `fts` | indeks FTS5 po pełnym tekście i sygnaturach | `szukaj` bez sieci; `remove_diacritics 2` składa `ó`→`o`, ale `ł` nie ma rozkładu w Unicode, więc „lodz" nie trafia „Łódź" |
| `runs` | przebieg: kanał, zakres, kryteria i ich odcisk, status (`w_toku`, `zakonczony`, `przerwany`, `blad`), ostatnia strona, powód | wznowienie i rozliczenie: `runy` mówi, co, kiedy i za ile żądań |
| `run_documents` | które dokumenty objął przebieg i czy były nowe | `eksportuj --run-id` bez zgadywania; przebieg sprzed migracji schematu nie ma tych wierszy i eksportuje się po kryteriach |
| `requests_log` | każde żądanie: czas, metoda, adres bez parametrów i sekretów, status, milisekundy, bajty, SHA-256 odpowiedzi, ocena kształtu, `Retry-After` | „cisza jest usterką": to, co poszło do cudzego serwera, ma ślad; limiter czyta stąd historię po wznowieniu |

Schemat ma numer (`PRAGMA user_version`, dziś 3) i migruje się sam przy pierwszym poleceniu,
bez utraty danych.

Pola, których pochodzenia nie znamy (`thesis`, `thesis_snippet` — teza może być tekstem od
modelu), zostają w surowych bajtach, ale **nie wchodzą** do metadanych, wyszukiwania ani
eksportu; lista z powodem i datą stoi w `contract.yaml` kanału (`pola_odrzucone`).

## Pliki wynikowe

Nazwa pliku powstaje z identyfikatora przebiegu albo z kryteriów i znacznika czasu UTC:
`kio_atlas-969ac406dd8f_20260918T121721Z.xlsx`,
`kio_daty_wydania_2024-01-01_–_2024-01-31_20260918T121806Z.csv`. Zapis jest atomowy — plik
pojawia się dopiero w całości.

| Format | Co zawiera |
|---|---|
| `xlsx` | arkusz `Orzeczenia` (tabela z autofiltrem, 21 kolumn), `Slownik` (opis każdej kolumny), `Metadane` (kryteria, cel pobrania, liczba dokumentów w eksporcie i w korpusie, formaty, czas, wersja narzędzia i odczytu, organ, atrybucja) |
| `csv` | te same kolumny, separator `;`, UTF-8 z BOM (Excel otwiera poprawnie polskie znaki) |
| `jsonl` | jeden obiekt na dokument: tożsamość, blok cytowania i **surowy rekord kanału w całości** z pełnym tekstem — format dla własnego potoku |
| `md` | katalog `<nazwa>_md/` z jednym plikiem na orzeczenie (`atlas_kio-1205-20.md`: nagłówek metadanych, blok atrybucji, pełny tekst) i `INDEX.md` z metadanymi eksportu i tabelą odsyłaczy |

Kolumny: `sygnatura`, `sygnatury`, `data_wydania`, `data_rozprawy`, `rodzaj`, `rozstrzygniecie`,
`rozstrzygniecie_surowe`, `przewodniczacy`, `odwolujacy`, `zamawiajacy`, `przepisy`, `koszty`,
`organ`, `atrybucja`, `kanal`, `slug`, `url_zrodla`, `doc_id`, `sha256`, `pobrano`,
`dlugosc_tresci`. Każdy wiersz i każdy plik niesie oznaczenie organu i atrybucję
„Źródło: Atlas Przetargów (https://atlasprzetargow.pl)" — reguła 15, pilnowana testem.
Sygnatury i daty są tekstem, `koszty` i `dlugosc_tresci` liczbami. Wartości ze źródła
zaczynające się od `=`, `+`, `-`, `@` są neutralizowane, a znaki sterujące usuwane — w skoroszycie,
CSV, Markdownie i na ekranie, bo nazwa strony postępowania pochodzi z cudzego serwisu i trzeba
ją traktować jak wrogie wejście.

`data_wydania` jest zapisana tak, jak przyszła z kanału: u pośrednika bywa błędna (w styczniu
2024 dziewięć z 295 dat wcześniejszych niż rozprawa), więc filtr po datach może wciągnąć cudze
i zgubić własne. To jest cena zapisana, nie ukryta.

## Czego narzędzie nie robi

- **Nie wykrywa zmian u źródła** — nie ma `aktualizuj` ani `porownaj`; powtórne `pobierz` na tym
  samym zakresie pobiera listę i pomija dokumenty już zapisane, ale nie sprawdza, czy ich treść
  się zmieniła.
- **Ma jeden kanał.** Kanały `uzp` i `saos` nie istnieją; kompletność Atlasu względem wyszukiwarki
  UZP jest niepotwierdzona (cena wyboru zapisana w ADR-0004 §6).
- **`--fraza` w `pobierz` nie przeszukuje treści u Atlasu** — jego `search` dopasowuje
  sygnaturę (zmierzone 2026-09-18, 6 żądań; słowo obecne w treści daje zero, sygnatura daje ten
  dokument). Treść przeszukuje lokalnie `szukaj` po pobraniu zakresu dat. `--rozstrzygniecie`
  u kanału jest zgodne z lokalnym (6 na 6 sygnatur). `--przepis`, `--przewodniczacy` i `--strona`
  u kanału nie miały jeszcze własnego wywołania.
- **Nie ma kreatora, warstwy modelu, parsera sekcji ani grafu cytowań** — plan faz 2–4
  w `docs/AUDYT_KIO_ORZECZENIA.md`.
- **Nie ponawia żądań i nie pilnuje dwóch procesów naraz** (sekcja „Po przerwaniu").
- **Nie usuwa danych** — nie ma retencji ani `wyczysc`; bazę i `wyniki/` kasuje operator.

## Pierwszy korpus

Styczeń 2024, wykonany 2026-09-18 za zgodą właściciela: 295 dokumentów i 4 żądania listy
(strona pierwsza poszła dwa razy — przed zatrzymaniem na progu zgody i po wznowieniu), razem
299 żądań, wszystkie 200 i każda odpowiedź kształtu zgodnego, około sześciu minut; trzecie
wywołanie tego samego polecenia wysłało 3 żądania listy i zero za dokumenty. W korpusie: 122 wyroki i 173 postanowienia; rozstrzygnięcia:
umorzono 134, oddalono 67, uwzględnione 57, inne 31, odrzucono 6. Pełny zapis
w `docs/decisions.md`, „Przebieg 1".

Drugi przebieg tego samego dnia sprawdził odporność na żywym serwisie: 1–5 lutego 2024,
46 orzeczeń, proces ubity siłą po 22 dokumentach i dokończony tym samym poleceniem jako
osierocony (24 nowe, 22 pominięte bez żądania, 48 żądań łącznie). Korpus po obu przebiegach:
341 orzeczeń, każde z wersją surową, metadanymi i indeksem. Zapis w „Przebieg 2".

## Co już zmierzono

Wyniki z datami i liczbą żądań oraz status każdego pomiaru stoją w `docs/decisions.md`
(sekcja „Status pomiarów"). Siedem pomiarów własnych:

- **FTP UZP nie odpowiada** (pomiar 1, 2026-09-15) — port 21 milczy przy kontroli na cudzym
  serwerze FTP z tej samej maszyny w tej samej minucie.
- **Dla wyszukiwarki UZP nie ma warunków ponownego wykorzystywania ani informacji o ich braku**
  (pomiar 14, 2026-09-15); licencja CC BY-SA 4.0 ze stopki gov.pl jest zakreślona domeną
  `www.gov.pl`. To jest dziś powód reguły 23.
- **Blokada sieci w testach działa na poziomie gniazda** (pomiar 21, 2026-09-15).
- **Atlas zwraca pełny tekst orzeczenia** (pomiar 3a, 2026-09-18, 2 żądania): rekord
  `GET /api/kio/{slug}` niesie `full_text`, listę sygnatur i identyfikator UZP; zbiór liczy
  29 580 orzeczeń i sięga co najmniej rocznika 2010.
- **Atlas licencjonuje ponowne wykorzystywanie wprost** (pomiar 23, 2026-09-18, 3 żądania):
  CC BY 4.0 z atrybucją, odczytane u dostawcy; korzeń SAOS nie odpowiedział w 45 s.
- **Filtr `outcome` Atlasu jest zgodny z lokalnym, `search` dopasowuje sygnaturę, nie treść**
  (pomiar filtrów, 2026-09-18, 6 żądań): te same 6 sygnatur „odrzucono" u kanału i lokalnie;
  fraza z 11 orzeczeń stycznia daje u kanału zero, sygnatura daje dokładnie jeden dokument.
- **Przebieg ubity w trakcie na żywym serwisie dokończył się tym samym poleceniem** (przebieg 2,
  2026-09-18, 48 żądań): 1–5 lutego 2024, 46 orzeczeń, proces ubity po 22 dokumentach.

Wszystko pozostałe o źródłach pochodzi z lektury cudzych repozytoriów i dokumentacji. Kontrakt
`POST /Home/GetResults` wyszukiwarki UZP stoi na dwóch cudzych kolektorach — własnego POST-a nikt
tu nie wysłał. Dostęp do Dump API SAOS jest nieprzetestowany.

## Ścieżka bez korespondencji

Właściciel rozstrzygnął 2026-09-17, że **projekt nie prowadzi korespondencji**: nie idzie
wniosek do UZP z art. 39 ustawy o otwartych danych, nie idą pytania do prawnika, nie idzie mail
do pośrednika. Projekty pism zostają gotowe w `docs/pisma/`, niewysłane. Konsekwencja jest jedna:
**pobranie całości zbioru idzie wyłącznie z kanału, który ponowne wykorzystywanie licencjonuje
wprost.** Dla UZP zostają dwie role: weryfikacja na próbce i dopływ bieżący. To nie jest opinia
prawna i nie udaje jej — ryzyko resztkowe przyjął właściciel, zapis w `docs/decisions.md`.

## Trzy reguły, które obowiązują od pierwszego commita

**Narzędzie nie omija zabezpieczeń.** Żadnego rozwiązywania CAPTCHA, podszywania się pod
przeglądarkę ani obchodzenia ograniczeń tempa. Granica jest prawna, nie estetyczna.

**Żadnej liczby bez źródła i daty.** Każde twierdzenie w `docs/` niesie datę i sposób uzyskania.
Sygnatury, nazwy własne i treść przepisów pochodzą z odczytu z datą, nigdy z pamięci modelu.

**UZP nigdy nie pełni roli kanału masowego** (reguła 23). Każdy kanał deklaruje w `contract.yaml`
pole `role:` z zamkniętej listy, a `uzp` nie ma prawa zadeklarować `masowa`.

Wszystkie trzy mają **mechanicznych strażników** w `tests/test_boundaries.py`
i `tests/test_bramki_faz.py`, nie deklaracje. Dwadzieścia trzy reguły granic razem z powodem
istnienia każdej — w audycie 8.3 i architekturze 4.1.

## Rozwój

```
set PYTHONUTF8=1                          # polskie znaki na konsoli Windows
.venv\Scripts\python.exe -m pytest        # 1066 testów w 34 plikach, sieć zablokowana
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\mypy.exe kio_tool scripts   # strict
```

Liczby zmierzone 2026-09-18 wieczorem, po testach odpornościowych; wszystkie cztery bramki
zielone. Testy odporności (`tests/test_odpornosc_*.py`) mierzą zanik sieci na dokumencie i na
stronie listy, 429 i 5xx, 404, 200 o złym kształcie i urwane, ubicie procesu `TerminateProcess`
w trakcie zapisu do bazy i w trakcie eksportu, pełny dysk w połowie dokumentu i w `finally`,
cel zajęty i katalog nie do założenia. Testy ścieżki użytkownika (`tests/test_uzytkownik_*.py`)
przechodzą każde polecenie na ścieżce szczęśliwej i w każdej przewidywalnej pomyłce laika,
z brzmieniem zdań odczytanym z `ui/texts.py`, nie z ekranu. Osiemnaście znalezisk testerów
i osiem z przeglądu kodu naprawiono tego samego dnia; dwadzieścia jeden zabezpieczeń sprawdzono
mutacją (psując produkcję i patrząc, czy test się zapala). Pakiet
`kio_tool/` ma 29 plików i 6 861 linii: warstwę infrastruktury (`httpclient` — jedyne miejsce budujące
klienta HTTP, bramka wyjścia odmawia wszystkiemu poza `https` i hostami kanału; `ratelimit`;
`docid` — jedyny producent tożsamości; `safetext`, `richtext`, `config`, `logbook`, `console`,
`ksztalt`), kanał `source/atlas/` z `contract.yaml` (jedyne miejsce z adresami i nazwami pól
pośrednika), `store.py`, `pipeline.py`, `criteria.py`, `parser/details.py`, `exporter.py`,
`cli.py` i `ui/`. Sonda fazy 0 w `scripts/` (dyspozytor, środowisko żądania, pomiary per kanał,
oczekiwania kształtu):

```
.venv\Scripts\python.exe scripts\sonda.py --lista
.venv\Scripts\python.exe scripts\sonda.py atlas        # 2 żądania: lista i jeden dokument
.venv\Scripts\python.exe scripts\sonda.py licencje     # 3 żądania: warunki reuse u SAOS i Atlasu
```

Sonda wykonuje pojedyncze odczyty diagnostyczne, które zgody nie wymagają, ale każdy zostawia
wiersz w `docs/dziennik_zadan.md`. Piaskownica testów przekierowuje bazę, katalog wyników
i zapis sondy do `tmp_path` i porównuje stan prawdziwych ścieżek przed i po — bo test, który
zapisał do prawdziwego katalogu, zdarzył się 2026-09-18 dwa razy.

Poprawkę w module o charakterze zabezpieczenia sprawdza się mutacją: psując produkcję i patrząc,
czy test się zapala. Kilka luk przeszło przez zieloną suitę i pokazała je dopiero mutacja.

## Dokumentacja

| Plik | Co niesie |
|---|---|
| `docs/AUDYT_KIO_ORZECZENIA.md` | stan źródła, dopuszczalność w sześciu reżimach, rachunek build-vs-buy, doktryna, reguły granic, plan faz |
| `docs/ARCHITEKTURA_KIO_TOOL.md` | przegląd istniejących narzędzi, architektura, model danych, reguły 17–23, decyzje właściciela |
| `docs/decisions.md` | wyniki pomiarów z datami, decyzje właściciela, przebiegi i **status każdego pomiaru**; wpis nigdy nie jest usuwany |
| `docs/dziennik_zadan.md` | ślad po każdym żądaniu sondy |
| `docs/adr/` | decyzje architektoniczne wraz z odrzuconymi wariantami (0001 tożsamość, 0003 kształt `source/`, 0004 wybór kanału, 0005 bramka per kanał) |
| `docs/pisma/` | projekty pism **gotowych i niewysłanych** |
| `docs/raport_przekazania.md` | raport dla nowej osoby z recenzją 2026-09-18 |
| `CLAUDE.md` | konfiguracja projektu dla sesji z Claude Code |

Kolejność czytania, jeśli masz przeczytać tylko część: `docs/decisions.md`, potem ADR-0005
i ADR-0004, potem sekcja 14 audytu — status dowodowy, czyli to, na których zdaniach wolno budować.

## Licencja

MIT dla kodu. Korpus nie wchodzi do repozytorium — niesie pełne nazwiska składu orzekającego
i protokolantów, a operator narzędzia jest dla tych danych administratorem. Dane z Atlasu
Przetargów są na licencji CC BY 4.0 i każdy eksport niesie wymaganą atrybucję.
