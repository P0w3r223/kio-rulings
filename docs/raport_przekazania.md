# Raport stanu systemu — przekazanie do recenzji i zaplanowania startu

Date: 2026-09-18
Status: draft — do recenzji i edycji przez agenta przejmującego
Author: P0w3r223
Related to: `AUDYT_KIO_ORZECZENIA.md`, `ARCHITEKTURA_KIO_TOOL.md`, `decisions.md`, `adr/0003`, `adr/0004`, `adr/0005` (odpowiedź na ten raport), `README.md`, `CLAUDE.md`

---

## 0. Po co ten dokument i czego się po Tobie oczekuje

Czytasz to jako agent, który ma **zrecenzować ten raport, poprawić go i napisać plan działania**
prowadzący do tego, żeby program **zaczął realnie pracować jak najszybciej**, wykorzystując to,
co już istnieje — w tym repozytorium i poza nim.

Trzy rzeczy, które trzeba wiedzieć, zanim zaczniesz:

1. **Ten projekt nie pobrał jeszcze ani jednego orzeczenia.** Nie jest to niedokończona
   implementacja — jest to zamierzony stan fazy 0, której produktem jest dokument, nie program.
2. **Projekt ma nietypowo mocną doktrynę** (sekcja 5) i 23 reguły granic z mechanicznymi
   strażnikami. Plan, który je łamie, zostanie odrzucony przez testy w pierwszej minucie.
   Plan, który proponuje ich **zmianę**, jest dopuszczalny — ale musi to powiedzieć wprost
   i uzasadnić, a nie obejść.
3. **Największym realnym ryzykiem tego projektu nie jest jakość kodu, tylko proporcja.**
   574 testy, 3 108 linii dokumentacji, zero dokumentów w korpusie. W fazie 0 to jest obronne;
   od pewnego momentu przestaje być. Sekcja 12 mówi o tym wprost i oczekuję, że Twój plan się
   do tego odniesie.

Czego od Ciebie potrzebuję konkretnie — lista w sekcji 13.

---

## 1. Czym ten projekt jest

**`kio-tool` — lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej**, z pełnym
tekstem, wyszukiwaniem i eksportem z atrybucją. Python 3.12, Windows, pojedynczy operator.

### 1.1 Problem

Orzecznictwo KIO jest publiczne, ale **nie istnieje do niego żaden udokumentowany interfejs
programistyczny ze strony urzędowej**:

- Urząd Zamówień Publicznych udostępnia wyszukiwarkę WWW przeznaczoną dla człowieka
  (`orzeczenia.uzp.gov.pl`), bez API, bez `robots.txt` (404), bez warunków ponownego
  wykorzystywania;
- serwer FTP z archiwum przestał publikować 30.09.2025, a dziś **nie odpowiada wcale**
  (pomiar 1, zmierzone 2026-09-15 — port 21 milczy przy działającej kontroli);
- jedyne pełne API oferuje **pośrednik prywatny** (Atlas Przetargów), na licencji CC BY 4.0.

Skutek: kto chce policzyć cokolwiek **na całości zbioru** — a nie przeczytać pojedynczą
sprawę — nie ma dziś czym.

### 1.2 Zakres rozstrzygnięty uczciwie, czyli częściowo na „nie"

Audyt przeprowadził rachunek build-vs-buy i **odrzucił dwie z trzech potrzeb**:

| Potrzeba | Werdykt | Powód |
|---|---|---|
| „wyszukać i przeczytać orzeczenie" | **nie budować** | Atlas Przetargów robi to za darmo; SzuKIO i wydawnictwa odpłatnie |
| „zapytać w języku naturalnym" | nisza pusta, ale **z twardym ograniczeniem** | żaden czołowy model nie przeszedł części praktycznej egzaminu na członka KIO (arXiv 2511.04205, zgłoszenie 6.11.2025) |
| **„programowy dostęp do korpusu pod własny potok"** | **budować** | nikt nie utrzymuje otwartego, wersjonowanego, lokalnego korpusu KIO |

Weryfikacja niszy: kolektor Legal Data Hunter **nigdy nie wykonał pełnego przebiegu**
(`total_records: 0`), `kio-orzeczenia-mcp` jest POC-em bez magazynu, Atlas i SzuKIO są
produktami zamkniętymi lub pośredniczącymi.

### 1.3 Trzy różnice wobec sąsiedniego projektu `ceidg-tool`

Sąsiednie repozytorium `..\Ceidg` jest źródłem wzorców (bez wspólnej biblioteki — kopiujemy kod,
nie zależność). Trzy różnice, z których każda przestawia kolejność prac:

1. **Nie ma interfejsu, jest formularz.** CEIDG zaczynał od udokumentowanego API v3. Tutaj
   pierwszą fazą jest **zmierzenie, czym jest to źródło** — każda decyzja architektoniczna
   przed pomiarem byłaby zgadywaniem kształtu.
2. **Jednostką nie jest rekord, tylko dokument.** Kilkanaście stron polszczyzny prawniczej ze
   strukturą wewnętrzną. Dlatego faza 1 kończy się korpusem, a nie arkuszem.
3. **Ryzyko przesuwa się z danych na dostęp.** W CEIDG groźne były dane wyjściowe przy
   bezspornym prawie do zapytania. Tutaj dane są publiczne z założenia, a sporna jest **droga
   dostępu**.

---

## 2. Inwentarz — co fizycznie istnieje

Wszystkie liczby zmierzone 2026-09-18 poleceniem `wc -l` / `pytest --collect-only`.

### 2.1 Kod produkcyjny: `kio_tool/` — dziewięć modułów, 1 304 linie

| Moduł | Linii | Co robi i dlaczego istnieje |
|---|---|---|
| `ratelimit.py` | 408 | Limiter: okna przesuwne, **odstęp minimalny wymagany** (nie opcjonalny), blokada po 429, budżet z nagłówków `X-RateLimit-*`, `Retry-After` honorowany, margines granicy okna, przycięcie budżetu. Emituje zdarzenia `Events`. |
| `docid.py` | 167 | **Jedyny** producent kanonicznej tożsamości dokumentu i jedyny normalizator sygnatur (`KIO 827/18`, `KIO/UZP 1482/08`, `KIO/KU 97/13`). Strażnik miny, która w CEIDG kosztowała noc i 2 681 żądań. |
| `errors.py` | 141 | Taksonomia wyjątków z kodami wyjścia; `KioError` deklaruje komunikat przeznaczony dla użytkownika. |
| `config.py` | 133 | Tożsamość klienta (`user_agent()` **odmawia bez `KIO_TOOL_CONTACT`**), zbiory hostów per kanał, rejestracja i maskowanie sekretów. |
| `httpclient.py` | 119 | **Jedyne** miejsce budujące `httpx.Client`. Bramka wyjścia `refuse_foreign_host` odmawia wszystkiemu poza `https` i podanym zbiorem hostów. Parametr `allowed` **bez wartości domyślnej**. |
| `progress.py` | 107 | Protokół `Events` — `source/` i `store` nie znają `rich` ani konsoli. |
| `safetext.py` | 100 | Neutralizacja wrogich napisów ze źródła: C1, DEL, znaki dwukierunkowe. Moduł czysty. |
| `richtext.py` | 69 | Jedyny szew z `rich`; `make_console()` idzie w `markup=False, highlight=False`, więc reguła „napis spoza programu tylko przez `safe`" jest własnością obiektu, nie skanu. |
| `clock.py` | 60 | Zegar jako zależność wstrzykiwana — jedyne `time.sleep` na ścieżce do źródła. |

**Zero funkcji dziedzinowej.** To są porty bez adapterów.

### 2.2 Sonda fazy 0: `scripts/` — 1 690 linii

| Plik | Linii | Co robi |
|---|---|---|
| `sonda.py` | 1 428 | Pięć pomiarów, ślad przebiegu (`Wynik`, `Kronika`, `PulsSondy`), dziennik żądań, podsumowanie JSON |
| `ksztalty.py` | 262 | Ocena kształtu odpowiedzi — **każde oczekiwanie niesie własne `zrodlo`**, bo „kontrakt z dwóch cudzych kolektorów" i „własny odczyt z datą" to dwa różne statusy dowodowe |

`scripts/` **nie jest pakietem**: `import ksztalty` działa, bo katalog skryptu wchodzi na
`sys.path` przy `python scripts\sonda.py`; testom dokłada tę ścieżkę `tests/conftest.py`.

### 2.3 Testy — 574 w dziesięciu plikach, 8 594 linie

| Plik | Testów | Co pilnuje |
|---|---|---|
| `test_sonda.py` | 166 | całą sondę, z atrapą cudzego serwisu i zegarem testowym |
| `test_boundaries.py` | 127 | 23 reguły granic skanem AST + metatest antypustkowy |
| `test_docid.py` | 74 | normalizator sygnatur na wszystkich znanych postaciach |
| `test_ratelimit.py` | 73 | limiter; trzy usterki produkcji znalezione 2026-09-15 zgłoszono wtedy jako `xfail(strict=True)` i **poprawiono tego samego dnia** — dziś plik nie ma ani jednego `xfail` |
| `test_ksztalty.py` | 61 | ocenę kształtu i niezmienniki oczekiwań |
| `test_bramki_faz.py` | 33 | **bramki planu faz** — kod nie powstaje przed decyzją, która go dopuszcza |
| `test_safetext.py` | 21 | neutralizację tekstu |
| `test_richtext.py` | 8 | konsolę bez interpretacji znaczników |
| `test_bramka_wyjscia.py` | 7 | politykę wyjścia HTTP |
| `test_pomiar21_blokada_sieci.py` | 4 | że blokada sieci w testach sięga gniazda, nie tylko `httpx` |

### 2.4 Dokumentacja — 3 108 linii

`AUDYT_KIO_ORZECZENIA.md` (1 097) · `ARCHITEKTURA_KIO_TOOL.md` (669) · `decisions.md` (265) ·
`adr/0003_ksztalt_source_i_bramka_wyjscia.md` (256) · `adr/0004_wybor_kanalu.md` (242) ·
`pomiary.md` (125; scalony 2026-09-18 po południu do `decisions.md`, ADR-0005) · trzy projekty pism w `pisma/` (454, **gotowe i niewysłane**).

Liczba nie obejmuje tego raportu — dolicz go, jeśli powołujesz się na nią po edycji.

### 2.5 Czego nie ma — i to jest stan zamierzony

`kio_tool/source/` (adaptery kanałów) · `kio_tool/parser/` · `kio_tool/ui/` · `store.py` ·
`pipeline.py` · `criteria.py` · `cli.py` · `exporter.py` · `mcp_server.py` · `logbook.py` ·
`dictionaries.py`.

Katalogi `source/`, `parser/`, `ui/`, `tests/{examples,cassettes,gold}` stoją puste
z `.gitkeep`. **Pilnuje tego test**, nie dobre chęci: `tests/test_bramki_faz.py` zapala się, gdy
`source/` niesie kanał, a ADR-0004 nie jest przyjęty.

---

## 3. Co system dziś potrafi

### 3.1 Uruchamialne: pięć pomiarów sondy

```
set KIO_TOOL_CONTACT=adres@example.org
.venv\Scripts\python.exe scripts\sonda.py --lista
.venv\Scripts\python.exe scripts\sonda.py <pomiar>
```

| Komenda | Pomiar | Co rozstrzyga | Żądań |
|---|---|---|---|
| `saos-dump` | 2a/2b | czy własny klient dostaje się do Dump API SAOS; czy filtruje po `courtType` | 3 |
| `atlas` | 3a | czy pośrednik zwraca pełny tekst; od którego rocznika sięga zbiór | 1–2 |
| `uzp-getresults` | 4b/16 | własny `POST /Home/GetResults`; liczniki `#resultCounts` per organ | 3 |
| `licencje` | 23 | czy SAOS i Atlas licencjonują reuse wprost | 2 |
| `uzp-stabilnosc` | 19 | czy bajty `ContentHtml` są stabilne między pobraniami | 1 ×2 przebiegi, ≥24 h |

**Blokada: brak adresu w `KIO_TOOL_CONTACT`.** `config.user_agent()` odmawia bez niego i jest to
zamierzone (reguła 16) — klient przedstawia się obcemu serwisowi, żeby jego operator miał jak
napisać.

### 3.2 Co sonda robi inaczej niż zwykły skrypt jednorazowy

To jest najważniejszy fragment dla Twojego planu, bo **sonda jest zalążkiem adaptera** (sekcja 10):

1. **Wychodzi przez bramkę wyjścia pakietu** (`build_http_client`), nie własnym `httpx`. Reguła
   11 obejmuje `scripts/` wprost.
2. **Trzyma tempo przez `RateLimiter`**, choć wysyła pojedyncze żądania.
3. **Zapisuje surową odpowiedź na dysk przed jakąkolwiek interpretacją** — zalążek złotego pliku
   z reguły 17.
4. **Ocenia kształt odpowiedzi** z zapisanym źródłem oczekiwania. Powód ma datę: cudzy kolektor
   przez dwa miesiące zwracał `total=0` ze statusem 200 po przebudowie wyszukiwarki w lipcu 2026.
5. **Kontroluje host przy odmowie** — odmowa bez kontroli nie odróżnia „punkt końcowy odmawia" od
   „host odmawia wszystkiemu". Przy UZP kontrola idzie **przed** ekspozycją nieznanego POST-a.
6. **Zatrzymuje grupę przy odmowie** — narzędzie nie omija zabezpieczeń (art. 267 § 1 k.k.).
7. **Nie nadpisuje dowodów** — nazwa pliku ze znacznikiem co do sekundy plus wolna ścieżka.
8. **SHA-256 każdej odpowiedzi i wiersz w dzienniku żądań** w historii repozytorium, dopisywany
   **w chwili powrotu żądania**, nie po przebiegu — przerwany przebieg zostawia ślad po tym, co
   już poszło do cudzego serwisu.
9. **Puls** — wiersz na ekranie w chwili powrotu żądania; cisza przez cały przebieg jest usterką.
10. **Werdykt trafia do `podsumowanie_*.json`**, nie tylko na ekran.

### 3.3 Czego system nie potrafi

**Nie potrafi: pobrać, zapisać, sparsować, przeszukać, wyeksportować, ani odpowiedzieć na
pytanie.** Nie ma magazynu, parsera, CLI ani interfejsu. Nie ma też ani jednego pliku
w `tests/examples/` — czyli ani jednej zamrożonej odpowiedzi cudzego serwisu.

---

## 4. Status dowodowy — co zmierzono, a co jest cudzym twierdzeniem

**To jest sekcja, którą musisz przeczytać przed zaplanowaniem czegokolwiek.** Projekt rozróżnia
te dwa statusy rygorystycznie i Twój plan powinien też.

### 4.1 Zmierzone własnym klientem (3 pomiary)

| Pomiar | Wynik | Data, koszt |
|---|---|---|
| **1** — FTP UZP | **negatywny**: port 21 nie przyjmuje połączenia; kontrola `ftp.gnu.org` z tej samej maszyny w tej samej minucie działa (kod 226, 1,5 s) | 2026-09-15, 3 próby |
| **14** — warunki reuse dla `orzeczenia.uzp.gov.pl` | **warunków nie ma i nie ma informacji o ich braku**; zero trafień dla sześciu markerów na 28 064 bajtach strony; licencja CC BY-SA 4.0 z gov.pl jest zakreślona domeną `www.gov.pl` | 2026-09-15, 4 GET |
| **21** — blokada sieci w testach | **pozytywny w obu połowach**: `--block-network` jest zamkiem **na gnieździe**, nie na bibliotece; obejmuje kanał spoza HTTP | 2026-09-15, 0 żądań |

### 4.2 Niepotwierdzone samodzielnie — a nośne

| Twierdzenie | Skąd | Ryzyko, jeśli fałszywe |
|---|---|---|
| Kontrakt `POST /Home/GetResults` (pola, nagłówek `X-Requested-With`, `data-page`, `#resultCounts`) | **dwa niezależne cudze kolektory** + własne odczyty GET | średnie — zbieżność dwóch niezależnych źródeł jest najlepszym dowodem bez własnego POST-a |
| SAOS: 22 168 rekordów KIO, 2007-12-10 → 2018-09-06, pełny tekst | dokumentacja SAOS; **własny klient dostał 403 na API wyszukiwania** | **wysokie** — od tego wisi jedenaście lat materiału, a Dump API nie testował nikt |
| Atlas: pełny tekst przez `/api/kio/{slug}`, CC BY 4.0, 1500/dobę/IP, 5000/konto, 500/min | dokumentacja dostawcy odczytana 2026-09-14; **żadnego punktu nikt nie wywołał** | **wysokie** — to jest dziś najpoważniejszy kandydat na pierwszy kanał |
| Dane Atlasu są „sparsowane z PDF" (własne słowa dostawcy) | dokumentacja | cudzy potok ekstrakcji z jego błędami; brak SLA i gwarancji kompletności |
| Sygnatury z grudnia 2007 obecne w wyszukiwarce UZP | wyniki cudzej wyszukiwarki, **zero własnych żądań** | średnie — dotyczy pytania, czy odcinek 2007–2018 ma drogę poza SAOS |
| Granica przestrzeni identyfikatorów ~33 366 (kwiecień 2026); KIO i SO dzielą numerację | Legal Data Hunter | niskie — trzecie niezależne źródło rzędu wielkości |
| PDF generowany na żądanie przez `wkhtmltopdf` | pomiar z researchu | niskie, ale uzasadnia ostrożne tempo |

### 4.3 Reguła, która z tego wynika

**Liczba bez źródła i daty jest w dokumentach tego projektu błędem, nie skrótem.** Zapis ma
postać „zmierzone 2026-09-15, 4 żądania" albo „z dokumentacji cudzej, data X". Dotyczy to także
Twojego planu.

---

## 5. Doktryna — cztery zasady, które nadpisują odruchy

Pełne brzmienie w audycie sekcja 7. Tu jest to, co zmienia sposób pracy:

**Liczba bez źródła i daty jest błędem.** Ostrzejsza wersja dotyczy materiału: sygnatury, nazwy
własne i treść przepisów bierz z odczytu z datą. `KIO 1234/25` wygląda tak samo niezależnie od
tego, czy istnieje, a „Izba wskazała, że…" brzmi wiarygodnie niezależnie od tego, czy Izba tak
wskazała.

**Cisza jest usterką.** Przy każdym zabezpieczeniu: co by się wypisało, gdyby zostało naruszone?
Jeśli „nic" — to jest usterka, a nie zabezpieczenie. Puls długiej operacji liczy się w żądaniach
wysłanych, nigdy w stronach wyników.

**Dowód sanityzuje się dokładnie z tego, co ważne.** Sprawdzaj generator materiału testowego,
a nie tylko materiał. Słowniki generowane ze źródła z zapisanym SHA-256 tego źródła.

**Gwarancja bez obserwatora nie jest gwarancją.** Reguła bez mechanicznego strażnika jest
życzeniem, a życzenie w dokumencie wygląda dokładnie tak samo jak reguła egzekwowana.

### 5.1 Praktyka, która z tego wyrosła: weryfikacja mutacją

Poprawkę w module o charakterze zabezpieczenia sprawdza się **psując produkcję i patrząc, czy
test się zapala**. W tym repozytorium ta praktyka wykryła rzeczy, których cała zielona suita nie
wykryła — m.in. odwróconą kolejność maskowania w `richtext.safe`, `max(cooldown, retry_after)`
w limiterze, siedem cichych mutacji w strażnikach bramek i werdykt pomiaru 19 ogłaszający
„bajty stabilne" na dwóch odpowiedziach 403.

**Powtarzająca się przyczyna, warta zapamiętania:** *samosprawdzenie, które nie woła sprawdzanej
funkcji, nie jest samosprawdzeniem*, a *ciało testu, który dziś przechodzi pusto, nie ma
obserwatora*.

---

## 6. Reguły granic — 23, wszystkie ze strażnikiem

Mieszkają w audycie 8.3 (1–16) i architekturze 4.1 (17–23). Pilnuje ich `tests/test_boundaries.py`
skanem AST i sprawdzeniami systemu plików. **Numery są czytane z dokumentów**, więc reguła
dopisana do audytu zapala metatest bez niczyjej pamięci.

Najważniejsze dla Twojego planu:

| # | Reguła | Konsekwencja dla implementacji |
|---|---|---|
| 11 | **Jeden właściciel na protokół, jedna kopia polityki wyjścia** (brzmienie z ADR-0003). Tablica `EGRESS_OWNERS` wymienia **konstrukty, nie biblioteki**. Dziś właściciel jest jeden: `httpclient.py`, z wstrzykniętym transportem i `trust_env=False` | adapter **nie tworzy własnego** `httpx.Client`; kanał spoza HTTP wymaga własnego właściciela protokołu i decyzji w ADR |
| 13 | `mcp_server.py` importuje **wyłącznie** `store` (odczyt) i `exporter` — nie importuje `source` ani `pipeline` | `mcp_server.py` widzi tylko `store` i `exporter` |
| 14 | Jeden producent kanonicznej tożsamości dokumentu | wyłącznie `docid.py`; niesiona przez mypy strict na typie własnym, nie przez skan |
| 17 | Każdy kanał ma `contract.yaml`, złote pliki i test dymny; **każde oczekiwanie kształtu niesie własne `zrodlo` i datę** | adapter rzuca `SourceContractBroken` przy „status zgodny, kształt niezgodny" |
| 19 | Treść pochodząca od modelu nie wchodzi do korpusu i nie dzieli z nim nazwy | zbiory pochodne z sufiksem `-derived` i manifestem; adapter Atlasu **odrzuca pola `thesis*`** |
| 20 | Sieć w testach zablokowana, wyjątek jawny (marker `smoke`) | zmierzone: zamek na gnieździe |
| 21 | Kanał jest pakietem `source/<nazwa>/`; w `source/` nie leży moduł kanału luzem | roster kanałów **nigdzie nie jest wypisany** — skan porównuje trzy zbiory wyznaczone z drzewa i z kodu |
| 22 | Adres ani nazwa pola nie występują jako literał w kodzie kanału | wszystko idzie z `contract.yaml` |
| 23 | Każdy kanał deklaruje `role:` z listy `masowa \| weryfikacja \| doplyw`; **`uzp` nie ma prawa zadeklarować `masowa`** | patrz decyzja B, sekcja 7 |

**Reguła o liście wyjątków:** dopisanie do niej wymaga decyzji zapisanej w ADR, a nie komentarza
w teście. Dotyczy to także Ciebie.

---

## 7. Decyzje już podjęte — nie podważaj ich bez powodu, ale możesz

### 7.1 ADR-0003 (przyjęty 2026-09-15)

- **Kanał jest pakietem** `source/<nazwa>/` z `channel.py` i `contract.yaml` — nie płaskim
  modułem. Kontraktu nie da się osierocić; usunięcie przegranego kanału to jeden `rm -r`.
- **Bramka wyjścia indeksowana protokołem**, nie biblioteką. Tablica `EGRESS_OWNERS` mapuje
  konstrukt na zbiór plików, które wolno mu go budować; zbiór pusty znaczy „nikomu".

### 7.2 ADR-0004 (draft — to jest bramka fazy 0)

Kryterium wyjścia w pięciu punktach, **sprawdzane testem**:
1. status `accepted` z datą i podpisem właściciela;
2. każdy wiersz tabeli kandydatów domknięty w jednej z **dwóch** postaci — zmierzony albo
   „odpada, powód, data";
3. każda liczba z datą i sposobem uzyskania;
4. wynik każdego pomiaru wejściowego w `decisions.md`, wiersze żądań w `dziennik_zadan.md`;
5. wybrany **pierwszy adapter** z zapisanym powodem.

Wejście bramki: pomiary **2a, 2b, 3a, 4b/16, 23** (~9 żądań). Uwaga na ślad: pomiar 23 był do
2026-09-18 wejściem bramki **wyłącznie w `pomiary.md`** — ADR-0004 sekcja 3 i strażnik go nie
znały. Rozjazd wykryty przy weryfikacji tego raportu i domknięty w trzech miejscach naraz. Poza bramką świadomie: pomiar 9 (tempo —
obciąża cudzy serwis dla decyzji, która może nie zapaść), pomiary 7 i 19 (wejścia ADR-0001).

**Rekomendacja warunkowa:** SAOS pierwszy, jeśli 2a padnie pozytywnie; w przeciwnym razie Atlas;
UZP nigdy jako kanał masowy.

### 7.3 Trzy decyzje właściciela z 2026-09-17 — ścieżka bez korespondencji

| | Decyzja | Konsekwencja |
|---|---|---|
| **A** | projekt **nie prowadzi korespondencji** — bez wniosku z art. 39, bez prawnika, bez maila do pośrednika | kanał `uzp_zrzut` odpada; zostają **trzy osie** wykrywania nowości zamiast jednej; pomiar 15 zamknięty; pomiar 3b tylko przez obserwację; **brak opinii prawnej = ryzyko resztkowe przyjęte świadomie** |
| **B** | **UZP nigdy nie pełni roli kanału masowego** | pobranie całości wyłącznie z kanału licencjonującego reuse wprost; dla UZP zostają weryfikacja na próbce i dopływ bieżący; ~63 000 żądań i 17–19 h renderowania po stronie UZP nie wystąpi; reguła 23 ze strażnikiem |
| **C** | repozytorium **bez zdalnego**, ryzyko przyjęte | `decisions.md` i dziennik żądań leżą na jednym dysku; temat zamknięty, nie wraca |

**Decyzja B zastępuje pytanie do prawnika, a nie je pomija.** Pytanie brzmiało „czy wolno pobrać
istotną część cudzej bazy"; odpowiedź brzmi „nie pobieramy istotnej części tej bazy". Uzasadnienie
stoi w treści samego pytania: przy odpowiedzi niepewnej rozstrzygnięciem miało być pobranie przez
pośrednika — *inne rozstrzygnięcie architektoniczne, nie inne pismo*.

### 7.4 ADR-0001 i ADR-0002 — nie istnieją, a są wymagane

- **ADR-0001 (tożsamość dokumentu)** musi paść **przed pierwszym zapisem do bazy**. Pilnuje tego
  test: `store.py` nie może powstać wcześniej. Wejścia: pomiar 7 (sprostowania), 19 (stabilność
  bajtów), 17 (postaci sygnatur) oraz dwa pytania projektowe z `decisions.md`.
- **ADR-0002 (czy treść wolno wysłać do modelu)** — warunek wejścia do fazy 4.

---

## 8. Architektura docelowa — już zaprojektowana, nie projektuj jej od nowa

### 8.1 Mapa modułów (architektura 4.2)

```
cli.py (typer)  ui/wizard.py (questionary)      mcp_server.py (faza 4, osobny proces)
        \              |                                |
         └──── ui/flow.py: jedna sekwencja decyzji ─────┘  (mcp_server widzi tylko store i exporter)
                       v
                 criteria.py        CZYSTY: pydantic, bez I/O
                       v
                 pipeline.py        JEDYNY moduł widzący naraz source/ i store.py
         ┌────────┬────────┼────────┬────────┐
         v        v        v        v        v
      source/  store.py  parser/  docid.py  exporter.py
      ├ protocol.py      ├ details.py       (xlsx, md, parquet, warc)
      ├ contract.py      ├ sections.py
      ├ registry.py      ├ clean.py
      └ <kanal>/         └ cite.py
          ├ channel.py
          └ contract.yaml
         v (kanały HTTP i tylko one)
   httpclient.py ─► ratelimit.py ─► clock.py
```

### 8.2 Interfejs kanału (architektura 4.3)

```python
class Channel(Protocol):
    name: SourceName

    def list_candidates(self, scope: Scope) -> Iterator[Candidate]:
        """Tanie, stronicowane. Minimum do decyzji, czy pobierać."""

    def fetch(self, ref: SourceRef) -> RawDocument:
        """Drogie. Bajty tak, jak przyszły, plus nagłówki i moment pobrania. Nie parsuje."""

    def capabilities(self) -> Capabilities:
        """Filtry, sortowanie, rozmiar strony, limit tempa, czy ma datę modyfikacji."""
```

Podział na dwie operacje o różnym koszcie pochodzi z Rechtspraak (indeks → dokument) i Juriscrapera
(biblioteka parsuje, wywołujący pobiera).

### 8.3 Model danych (architektura 4.4) — zaprojektowany, czeka na ADR-0001

Rozstrzygnięcie do zatwierdzenia: **dokument jest jednostką, sygnatura jest etykietą, relacja jest
wiele-do-wielu, treść jest wersjonowana i nigdy nadpisywana.**

Tabele: `documents` · `raw_versions` (PK `doc_id, content_sha256`) · `cases` · `document_cases`
(z `outcome` per sygnatura) · `equivalences` (to samo orzeczenie z dwóch kanałów, **stwierdzane**
przez `porownaj`, nigdy zakładane) · `metadata` · `provisions` · `index_terms` · `sections` ·
`citations` · `fts` (FTS5) · `runs` · `requests_log` · `dictionaries`.

`doc_id` = `"{source}:{source_ref}"`, np. `uzp:9620`, `atlas:kio-827-18`, `saos:354301`.

**Dowody na wielosygnaturowość:** pliki `2021_1820_1821_1834.pdf` z listingu FTP; lista
„Sygnatura akt / Sposób rozstrzygnięcia" w `Details`; rekord SAOS „KIO 233/18, KIO 234/18";
dokumentacja SAOS mówiąca, że „orzeczenie czasem może dotyczyć wielu spraw"; pole
`primary_signature` w API Atlasu; **kolektor Legal Data Hunter bierze tylko pierwszą sygnaturę
i przez to gubi sprawy**.

### 8.4 Planowane polecenia (architektura 5.1)

`pobierz` (masowo, wznawialny) · `aktualizuj` (trzy osie) · `przelicz` (**zero żądań**, pilnowane
blokadą sieci) · `szukaj` (FTS5) · `eksportuj --format xlsx|md|parquet|warc` · `porownaj`
(dwa kanały, zapis do `equivalences`) · `cytowania` · `demo` (korpus **generowany**, nie
skopiowany) · `slowniki` · `serve-mcp` (faza 4) · `sonda --kontrakt` (faza 1: test dymny
kontraktu, nadaje się do harmonogramu).

---

## 9. Koszt akwizycji — policzony z liczb ze źródła

| Zakres | Kanał | Razem żądań | Czas |
|---|---|---|---|
| Rocznik 2024 (4 266 orzeczeń) | UZP | ~8 960 | ~2,5 h przy 1/s |
| Rocznik 2024 | Atlas z kluczem | ~4 310 | jedna doba; min. ~9 min przez 500/min |
| Rocznik 2024 | Atlas bez klucza | ~4 310 | 3 doby (1 500/dobę/IP) |
| **Cały zbiór (~29–32 tys.)** | **UZP przez `GetResults`** | **~63 000** | **~17,5 h przy 1/s** |
| Cały zbiór | UZP przez skan id 1…34 000 | ~68 000 | ~19 h przy 1/s |
| **Cały zbiór** | **Atlas z kluczem** | **~29 300** | **~6 dób** |
| 2007-12 – 2018-09 (22 168 KIO) | SAOS Dump API | zależy od `courtType` (pomiar 2b) | kanał warunkowy |

Podstawa: 4 266 orzeczeń w roczniku 2024 (Atlas, 2026-09-14); ~29 tys. wg Atlasu, ~31,7 tys. KIO
+ ~1,3 tys. SO wg Legal Data Hunter (kwiecień 2026), 30 660 elementów w listingu FTP — **trzy
liczby z trzech źródeł, ten sam rząd wielkości**. Tempo UZP 1 żąd./s to **precedens z dwóch
cudzych kolektorów, nie pomiar tolerancji serwisu**.

---

## 10. Co da się wykorzystać — istniejące rozwiązania

### 10.1 Wewnątrz tego repozytorium

| Aktywo | Stan | Jak wykorzystać |
|---|---|---|
| **`scripts/sonda.py` → adapter** | 1 428 linii, działające | Sonda **już robi** to, co ma robić adapter: wychodzi przez bramkę, trzyma tempo, zapisuje surowe bajty, ocenia kształt, loguje żądania. Szew nazywa się „ślad przebiegu" (`Wynik`, `Kronika`, `PulsSondy`, dziennik, podsumowanie) i przenosi się do `logbook.py` w pakiecie; reszta pliku mówi, **co** mierzymy, i staje się `channel.py` |
| **`scripts/ksztalty.py` → `contract.yaml`** | 262 linie | Oczekiwania kształtu z polem `zrodlo` przenoszą się do `contract.yaml` (reguła 17 wymaga tego wprost od 2026-09-17) |
| Dziewięć modułów infrastruktury | gotowe, przetestowane | Bez zmian. To są porty, które adapter po prostu wywoła |
| `tests/test_boundaries.py` | 127 testów, skan AST | Rośnie razem z `source/` bez zmian w skanie — `package_targets` bierze pierwszy segment modułu niezależnie od poziomu importu względnego |
| **`..\Ceidg` (`ceidg-tool`)** | sąsiednie repo | Wzorzec `store.py`, `ui/texts.py`, `ui/render.py`, `console.py`. **Kopiujemy kod z komentarzami niosącymi powody awarii z datami**, nie zależność |

### 10.2 Na zewnątrz — co już przejęto i co można przejąć dalej

| Źródło | Co daje | Status |
|---|---|---|
| **Legal Data Hunter** (`worldwidelaw/legal-sources`, AGPL-3.0) | potwierdzenie kontraktu `GetResults`; granica id ~33 366; KIO i SO w jednej numeracji; kształt `config.yaml` per źródło; struktura `Details` (`<label>…</label><br/>` w `<p>`, sygnatury w `<ul><li>`) | przejęte jako wzorzec; **uwaga na licencję AGPL — przejmujemy kształt, nie kod** |
| **Juriscraper** (Free Law Project) | złote pliki `*_example*` + `*.compare.json` generowane raz i przeglądane przez człowieka; podział „biblioteka parsuje, wywołujący pobiera"; `cleanup_content` | przejęte do reguły 17 i `parser/clean.py` |
| **SAOS Dump API** | `/api/dump/judgments` z `sinceModificationDate`; rekord kompletny (`textContent`, `courtCases[]`, `judges[]`) | **nietestowane** — pomiar 2a |
| **Atlas Przetargów REST API** | `/api/kio` (lista z filtrami), `/api/kio/{slug}` (**pełny tekst**), `/api/kio/stats`, `/api/entities/{nip}/rulings`, `/api/tenders/{id}/rulings`; CC BY 4.0 | **nietestowane** — pomiar 3a; najpoważniejszy kandydat na pierwszy kanał |
| **eyecite, LiDO, MateMatic** | graf cytowań: clean → extract → resolve → annotate | wzorzec dla `parser/cite.py` |
| **vcrpy + pytest-recording** | kasety HTTP i blokada sieci | **w użyciu**; blokada zmierzona, odtwarzanie kaset rozstrzygnie pierwsza kaseta (pomiar 4b) |
| **JuDDGES** | warstwa modelowa jako osobny zbiór; Parquet z manifestem | wzorzec dla reguły 19 i eksportu |
| **Rechtspraak / ECLI** | dwa kroki (indeks → dokument); trwały link z cytatem; `dcterms:modified` | wzorzec dla `Channel` i bloku atrybucji |
| **warcio** | eksport WARC | wzorzec dla `exporter.py` |
| **`kio-orzeczenia-mcp`** | faza 4 jako serwer MCP; kontrakt `citations`; dziennik wywołań | wzorzec dla `mcp_server.py` |

---

## 11. Najkrótsza droga do działającego programu — propozycja do krytyki

**To jest moja propozycja, nie decyzja.** Napisana po to, żebyś miał co poprawiać, a nie pustą
kartkę. Zakładam, że celem jest **pierwszy realny korpus na dysku**, nie komplet funkcji.

| Krok | Co | Koszt | Blokuje |
|---|---|---|---|
| **0** | adres w `KIO_TOOL_CONTACT` | 10 s właściciela | **wszystko** |
| **1** | pięć pomiarów sondy (~9 żądań) + wpis wyników do `decisions.md` | ~30 min | bramkę fazy 0 |
| **2** | wypełnienie tabeli kandydatów w ADR-0004, wybór pierwszego adaptera, podpis właściciela | ~1 h + decyzja | `source/` |
| **3** | **ADR-0001** — tożsamość dokumentu, na podstawie pomiarów 7, 19, 17 | ~2 h; pomiar 19 wymaga doby | `store.py` |
| **4** | `source/protocol.py`, `contract.py`, `registry.py` + **pierwszy adapter** (wg rekomendacji: `saos`, inaczej `atlas`) | ~1 dzień | `pipeline` |
| **5** | `store.py` (SQLite, `documents` + `raw_versions`, wznawianie) | ~1 dzień | przebieg |
| **6** | `pipeline.py` + minimalne `cli.py` z jednym poleceniem `pobierz --zakres` | ~0,5 dnia | **pierwszy korpus** |
| **7** | przebieg na jednym roczniku, przerwany i wznowiony — **bramka fazy 1** | godziny kalendarzowe | fazę 2 |

Po kroku 7 program **realnie pracuje**: pobiera, zapisuje, wznawia, nie duplikuje.
Parser, wyszukiwanie i eksport (fazy 2–3) są dopiero po tym.

### 11.1 Dlaczego rekomendacja mówi „SAOS pierwszy, inaczej Atlas"

Kryterium nie brzmi „który odcinek jest najcenniejszy", tylko: **na którym kanale kształt
`protocol.py`, `contract.py`, `registry.py` i `store.py` może się iterować, nie obciążając cudzego
serwera.**

- **SAOS**: rekord Dump API jest kompletny, więc `fetch` jest jednokrokowy; archiwum **zamrożone
  na 2018-09**, więc przebieg jest deterministyczny i powtarzalny — bramka fazy 1 („przerwany
  i wznowiony bez duplikatów") ma stabilne wejście. Zero obciążenia UZP. Nie ćwiczy osi
  „co nowego".
- **Atlas**: ćwiczy klucz API, `Retry-After`, atrybucję z reguły 15 i odrzucanie pól od modelu
  z reguły 19; prawdopodobnie pokrywa cały zakres. Wchodzi zależność od cudzego SLA.
- **UZP**: wykluczony jako masowy (decyzja B).

### 11.2 Napięcie, które musisz rozstrzygnąć

Ten projekt ma **574 testy i zero dokumentów**. Doktryna „mierz, zanim zbudujesz" jest tu
uzasadniona historią (mina z CEIDG: noc, 2 681 żądań, zero użytecznych rekordów) — ale
proporcja machiny do produktu jest dziś niewygodna i będzie rosła.

Twój plan powinien zająć stanowisko: **które zabezpieczenia są nośne dla pierwszego przebiegu,
a które można odłożyć bez łamania doktryny.** Moja obserwacja: nośne są reguły 11, 14, 17, 20
i 23 oraz `docid.py`; `parser/`, `exporter.py`, `mcp_server.py`, tryb pokazowy i graf cytowań
nie są potrzebne do pierwszego korpusu.

---

## 12. Długi, ryzyka i pułapki

### 12.1 Dług techniczny zapisany świadomie

- **`scripts/sonda.py` ma 1 428 linii wobec granicy 800.** Szew („ślad przebiegu") jest nazwany
  i przenosi się do `logbook.py` w dniu, w którym sonda stanie się adapterem. Dług urósł w tej
  sesji o połowę i zasługuje na ponowne rozważenie.
- **Zakończenia wierszy są mieszane bez wzorca** — 12 plików CRLF, 10 LF. Ujednolicenie da
  jednorazowy diff „każda linia zmieniona"; lepiej osobnym commitem, zanim wpadnie w środek pracy.
- **`respx` zostaje w zależnościach deweloperskich** jako druga droga do kaset, dopóki pierwsza
  prawdziwa kaseta (pomiar 4b) nie rozstrzygnie, czy vcrpy współistnieje ze wstrzykniętym
  transportem `httpx`.

### 12.2 Ryzyka merytoryczne

1. **Pomiar 2a może wypaść negatywnie.** Wtedy odcinek 2007–2018 (jedenaście lat, ~22 tys.
   orzeczeń) zostaje bez znanej drogi poza pośrednikiem — bo FTP już odpadł, a UZP jest
   wykluczony jako masowy.
2. **Pomiar 4b może wrócić CAPTCHĄ albo blokadą.** Po decyzji A nie ma drogi zapasowej: wniosek
   z art. 39 był jedyną i nie zostanie złożony. Odmowa zamyka UZP **także w rolach weryfikacji
   i dopływu**.
3. **Brak opinii prawnej** — ryzyko resztkowe przyjęte przez właściciela, zawężone decyzją B,
   nieusunięte.
4. **Zależność od cudzego SLA**, jeśli pierwszym kanałem zostanie Atlas. Regulamin mówi wprost
   o braku gwarancji kompletności i zaleca sprawdzenie publikacji źródłowej przy decyzjach
   formalnych.
5. **Jedyny egzemplarz dowodów na jednym dysku** (decyzja C).

### 12.3 Cztery miny przeniesione z CEIDG

1. **Tożsamość dokumentu** — jeden wpis, dwie pisownie identyfikatora, klucz główny wrażliwy na
   wielkość liter: noc, 2 681 żądań, zero użytecznych rekordów. **Strażnik istnieje:**
   `store.py` nie powstanie przed ADR-0001.
2. **„Kryterium poprawne" ≠ „wynik kompletny"** — pusty wynik wyszukiwania nie mówi, czego nie
   objął. Stąd wymóg, żeby wynik zapytania zawsze podawał liczby: dokumentów w korpusie,
   przeszukanych sekcji, dokumentów z pustą datą wypadających z filtra zakresowego.
3. **Cisza w długiej operacji** — stąd puls liczony w żądaniach, nie w stronach.
4. **Zmyślony materiał testowy** — pierwsza wersja korpusu pokazowego w CEIDG miała wymyślone
   nazwy branż, dwa nieistniejące kody i cztery z pięciu miast w złym powiecie; wszystko przeszło
   bramki, bo nic tego nie sprawdzało. Stąd: **korpus pokazowy generowany, nie kopiowany**,
   a sygnatury i nazwy własne wyłącznie z odczytu z datą.

---

## 13. Czego konkretnie od Ciebie oczekuję

1. **Zrecenzuj ten dokument** — wskaż, gdzie mówi rzeczy niepokryte, gdzie myli pomiar z cudzym
   twierdzeniem i gdzie jest nieaktualny wobec drzewa. Liczby sprawdź `wc -l` i `pytest`.
2. **Zajmij stanowisko wobec napięcia z 11.2** — co jest nośne dla pierwszego przebiegu, a co
   można odłożyć. To jest najważniejsze pytanie tego przekazania.
3. **Napisz plan startu** z krokami, kosztem i zależnościami. Jeśli uważasz, że kolejność
   z sekcji 11 jest zła — powiedz to wprost i uzasadnij.
4. **Wskaż, co z istniejących rozwiązań (sekcja 10) jest niewykorzystane**, a powinno być.
   Szczególnie: czy sonda → adapter da się zrobić taniej, niż zakładam.
5. **Nie łam reguł granic po cichu.** Jeśli któraś przeszkadza, zaproponuj jej zmianę jako ADR
   z powodem — lista wyjątków jest miejscem, w którym reguła cicho przestaje obowiązywać.
6. **Nie wymyślaj materiału dziedzinowego.** Sygnatur, nazw własnych, treści przepisów ani
   adresów punktów końcowych nie bierz z pamięci — tylko z odczytu z datą albo z dokumentów
   tego repozytorium.

### 13.1 Jedna rzecz, która blokuje wszystko

**Adres w `KIO_TOOL_CONTACT`.** Nie jest to formalność: klient przedstawia się nim obcemu
serwisowi, żeby jego operator miał jak napisać, gdy coś pójdzie nie tak. Bez niego
`config.user_agent()` odmawia startu i żaden pomiar nie pójdzie.

---

## 14. Jak uruchomić i czego nie uruchamiać

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest        # 574 testy, --block-network z konfiguracji
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format .
.venv\Scripts\mypy.exe kio_tool scripts   # strict
```

Katalog `docs/` jest wyłączony z `ruff format` (`force-exclude = true`) — ruff formatuje bloki
kodu Pythona osadzone w markdown i przy pierwszym uruchomieniu przeformatował dokument decyzyjny.

**Czego nie robić:** nie uruchamiaj przebiegu masowego ani pomiaru tempa bez zgody właściciela
udzielonej **w bieżącej sesji** — zgoda z poprzedniej sesji nie jest zgodą i dlatego nie da się
jej zapisać w konfiguracji. Pojedynczy odczyt diagnostyczny zgody nie wymaga, ale zawsze zostawia
wpis w `docs/dziennik_zadan.md`.

**Przy odmowie serwisu** — CAPTCHA, wykrycie bota, blokada — narzędzie zatrzymuje się i mówi
o tym operatorowi. Granica jest prawna, nie estetyczna (art. 267 § 1 k.k.).

---

## 15. Recenzja 2026-09-18 — odpowiedź na sekcję 13

Recenzję wykonał przegląd architektoniczny tego dnia; rozstrzygnięcia właściciela i pełna treść
zmian stoją w `docs/adr/0005_bramka_per_kanal.md`. Tu tylko to, co w tym raporcie było
niepokryte, pomylone albo nieaktualne wobec drzewa — bez edycji liczb w treści wyżej, żeby zapis
z rana 2026-09-18 pozostał zapisem.

**Stanowisko wobec 11.2.** Nośne dla pierwszego przebiegu: reguły 11, 14, 16, 17 (złoty plik
z `zrodlo`), 20, 22, 23, kolejność `store.py` po ADR-0001, dziennik w chwili powrotu żądania,
surowe bajty przed interpretacją, limiter z odstępem i `Retry-After`. Odłożone bez łamania
doktryny: to, co sekcja 11.2 wymienia, plus `criteria.py`, `porownaj`, trzy osie nowości,
pomiary 2a/2b, 4b/16, 7, 9, 19, `tests/queries/`. **Ceremonia do przebudowy, nie do odłożenia**
(odłożona wróciłaby w tym samym kształcie): kryterium „wszystkie cztery wiersze tabeli", dwie
listy pomiarów ze strażnikiem symetrii, `POMIARY_WEJSCIOWE_BRAMKI` jako ręcznie pisana krotka.
Doktryna zostaje w całości; zmienia się przedmiot, na którym pracuje.

**Kolejność z sekcji 11 jest zła w jednym punkcie:** krok 1 („pięć pomiarów, ~9 żądań") wysyłał
pięć żądań do dwóch serwisów po odpowiedź, której po decyzjach A/B żadna gałąź nie użyje.
Ścieżka po ADR-0005: 4–5 żądań wyłącznie do Atlasu, bez pomiaru 19 z dobą odstępu na ścieżce
krytycznej, ~365 żądań do bramki fazy 1 (jeden miesiąc 2024, policzone z 4 266 / 12).

**Co w tym raporcie było pomylone lub nieaktualne:**

- **Sekcja 3.1, wiersz `atlas` („czy pośrednik zwraca pełny tekst", 1–2 żądania):** pomiar 3a
  wołał wyłącznie listę `/api/kio` i nie dotykał `/api/kio/{slug}`, od którego zależy `fetch`;
  drugie żądanie było kontrolą hosta po odmowie, nie odczytem dokumentu. Poprawione w sondzie
  2026-09-18 (`pomiar_atlas`: lista `per_page=100` + dokument pierwszego rekordu; ocena
  `ATLAS_LISTA` nazywa klucz `data`, nowe `ATLAS_DOKUMENT` nazywa najdłuższe pole tekstowe).
  Pomiar 23 puka od tego dnia także w stronę dokumentacji Atlasu, odczytaną z datą.
- **Sekcja 2.1 „dziewięć modułów, 1 304 linie":** w pakiecie jest dziesięć plików i 1 316 linii
  (`__init__.py` 12). **Sekcja 2.3 „8 594":** `tests/` ma 8 635 linii (`conftest.py` 41).
  **Sekcja 2.4:** ADR-0004 ma 243 linie (edycja 2026-09-18), suma bez raportu 3 109. Po
  poprawkach z tego dnia liczby są inne i nie są tu przepisywane — kto ich potrzebuje, mierzy.
- **Sekcja 7.2 „kryterium w pięciu punktach, sprawdzane testem":** ADR-0004 §5 mówi wprost,
  że punktów 1 i 5 żaden test nie sprawdza i nie ma sprawdzać.
- **Sekcja 8.1 / ADR-0004 §6:** `protocol.py`, `contract.py`, `registry.py` czytały się jak
  wymagany komplet; skan reguły 21 wymaga wyłącznie `registry.py` (ADR-0005 Z-7).
- **Sekcja 6, reguła 19 („adapter Atlasu odrzuca pola `thesis*`"):** w brzmieniu „na wejściu"
  kolidowała z zapisem surowych bajtów i kluczem `content_sha256` (ADR-0005 Z-5).
- **Sekcja 12.1, `respx` do pomiaru 4b:** pytanie o kasety rozstrzyga test dymny adaptera
  Atlasu (ADR-0005 Z-10).
- **Sekcja 4.2, `dziennik_zadan.md`:** nie istnieje do pierwszego przebiegu sondy; wpisy ręczne
  za pomiary 1 i 14 (2026-09-15) dopisuje się przy jego powstaniu.
