# ADR-0004: Wybór kanału akwizycji — artefakt bramki wyjścia z fazy 0

Data: 2026-09-17
Status: accepted (2026-09-18, decyzja właściciela — plan z tego dnia zatwierdzony, polecenie „rozpocznij pracę od razu" po podaniu adresu kontaktowego; pomiary 3a i 23 wykonane 2026-09-18)
Zmiany: 2026-09-18 po pomiarach — wiersz `atlas` zmierzony (sekcja 4), `saos` i `uzp` domknięte werdyktem „nierozstrzygnięty" (sekcja 4.2, postać 3), pierwszy adapter wybrany z powodem (sekcja 6). 2026-09-17 rano — pytanie 2 do prawnika jako wejście warunkowe, trzecia postać domknięcia wiersza, kolumna `capabilities()`. 2026-09-17 po południu, po decyzjach A/B/C właściciela (`decisions.md`) — pytanie 2 **przestaje być wejściem bramki** (sekcja 3.1), wiersz `uzp_zrzut` **odpada** (sekcja 4), trzecia postać domknięcia **usunięta** jako furtka bez użytkownika (sekcja 4.2), wariant C **wykluczony**, a nie odradzany (sekcja 6). 2026-09-18 rano — pomiar 23 dopisany do wejścia bramki (sekcja 3); do tego dnia był wejściem wyłącznie w `pomiary.md`, czyli w jednym z trzech miejsc, przeciwko czemu ten dokument powstał. **2026-09-18 po południu — ADR-0005**: wejście bramki **per kanał** (sekcja 3), trzecia postać domknięcia „nierozstrzygnięty" w innym kształcie niż usunięta (sekcja 4.2), kryterium wyjścia czyta drzewo i kontrakt (sekcja 5), pierwszy adapter bezwarunkowo `atlas` (sekcja 6); `pomiary.md` scalony do `decisions.md`
Autor: P0w3r223
Related to: `AUDYT_KIO_ORZECZENIA.md` (9 bramka fazy 0, 10, 13.1, 14.2), `ARCHITEKTURA_KIO_TOOL.md` (4.3, 5.3, 6, 8), `docs/decisions.md` (sekcja „Status pomiarów"), `docs/adr/0003_ksztalt_source_i_bramka_wyjscia.md`, `docs/adr/0005_bramka_per_kanal.md`

---

## 1. Kontekst: bramka bez artefaktu nie jest bramką

Plan faz ma pięć bramek i cztery z nich mają wykonalne kryterium. Faza 1 kończy się
przebiegiem przerwanym w połowie i wznowionym bez duplikatów. Faza 2 — raportem pokrycia
parsera. Faza 3 — przejściem operatora bez pomocy autora. Faza 4 ma bramkę **przed** sobą,
w postaci dwóch dokumentów.

Bramka fazy 0 brzmi: „właściciel widzi tabelę kandydatów z pomiarami i wybiera kanał"
(audyt 9). Tej tabeli nikt nie produkuje, nie ma jej w żadnym pliku i nie wiadomo, czym się
kończy jej wypełnienie. To jest jedyna bramka w planie, której zamknięcia nie da się
stwierdzić inaczej niż przez czyjeś zdanie — a zasada 7.3 mówi, że gwarancja bez obserwatora
nie jest gwarancją.

Drugi powód powstania tego dokumentu: **to, co musi paść przed bramką, ma dziś trzy różne
brzmienia**:

| Gdzie | Co mówi |
|---|---|
| `AUDYT_KIO_ORZECZENIA.md` 10 | „Pierwsze trzy rozstrzygają wybór kanału" — pomiary 1, 2, 3 |
| `ADR-0003` sekcja 8 | pomiary 1, 2a/2b, 3 |
| `ARCHITEKTURA_KIO_TOOL.md` 4.3 (tabela adapterów) | dla UZP dokłada 4b i 9 |

Trzy listy tego samego są dokładnie tym, co ADR-0003 odrzucił przy `SourceName`: drugą listą
do uzgadniania. Reguła, którą tam przyjęto dla typów, obowiązuje tu dla dokumentów — jest
**jedno** miejsce z listą pomiarów (sekcja „Status pomiarów" w `docs/decisions.md`; do
2026-09-18 osobny `docs/pomiary.md`, scalony przez ADR-0005) i **jedno** miejsce z warunkiem
bramki (ten plik), przy czym od 2026-09-18 listę pomiarów **wejściowych** niesie `contract.yaml`
kanału, a nie ten dokument (sekcja 3).

---

## 2. Co ten ADR rozstrzyga, a czego nie

**Rozstrzyga:** który kanał (albo które kanały, bo rekomendacja 13.1 audytu jest hybrydowa)
niesie który odcinek czasu, na podstawie własnych pomiarów; oraz który adapter powstaje jako
pierwszy.

**Nie rozstrzyga:**

- **tożsamości dokumentu** — to ADR-0001, którego wejściami są od 2026-09-18 (ADR-0005 Z-4):
  postać `source_ref` z pomiaru 3a, `ref_case` w `contract.yaml`, wielosygnaturowość, pomiar 17
  (postaci sygnatur, na rekordach z pomiaru 3a) oraz dwa pytania projektowe z przeglądu kodu
  zapisane w `decisions.md`; pomiary 7 (sprostowania) i 19 (stabilność bajtów) przeszły do
  polityki wersji kanału `uzp`. ADR-0001 musi paść **przed pierwszym zapisem do bazy**, co jest
  osobną bramką i nie wolno jej pomylić z tą;
- **czy treść orzeczenia wolno wysłać do modelu** — to ADR-0002, faza 4;
- **postaci kanału archiwalnego** — decyzja 9 odpadła bez kosztu po pomiarze 1 (FTP nie
  odpowiada, zmierzone 2026-09-15).

---

## 3. Wejście bramki: pomiary kanału, który powstaje (brzmienie od 2026-09-18, ADR-0005 Z-1)

Wejściem bramki są **pomiary kanału, który ten ADR wybiera jako pierwszy**. Lista stoi w polu
`pomiary:` jego `contract.yaml` — strażnik (`tests/test_bramki_faz.py`) ją stamtąd czyta, więc ten
dokument jej nie powtarza. Dla `atlas` są to:

| Pomiar | Co rozstrzyga dla wyboru | Koszt |
|---|---|---|
| 3a | czy Atlas zwraca pełny tekst — **lista i jeden dokument** `/api/kio/{slug}` (drugie żądanie dopisane 2026-09-18: do tego dnia pomiar wołał wyłącznie listę, czyli punkt niosący skróty) — oraz od kiedy sięga zbiór (`sort=oldest`) | 2 żądania, +1 kontrolne przy odmowie |
| 23 | czy Atlas (i SAOS) **licencjonują ponowne wykorzystywanie wprost** — dopisany 2026-09-17 razem z decyzją B: skoro UZP nie pełni roli masowej, kanał masowy musi tę licencję mieć, a licencja ma być odczytana u dostawcy, nie wzięta z cudzego streszczenia; od 2026-09-18 także strona dokumentacji Atlasu, odczytana z datą | 3 żądania |

Razem 5 żądań: 4 do `atlasprzetargow.pl` (lista, dokument, korzeń hosta, strona dokumentacji)
i 1 do `www.saos.org.pl` (korzeń hosta w pomiarze 23 — ta sama lista markerów zadana obu
pośrednikom, żeby wyniki wolno było zestawić).

**Do 2026-09-18 wejściem były także 2a/2b (SAOS) i 4b/16 (UZP)** — pięć żądań do dwóch cudzych
serwisów po odpowiedź, której po decyzjach A i B żadna gałąź nie użyje: `uzp` jest wykluczony jako
pierwszy adapter w każdej gałęzi, a `saos` deklaruje zasięg do 2018-09, więc nie unosi korpusu.
Ten sam dokument zakazywał tego wzorca przy pomiarze 9 (niżej); ADR-0005 rozciągnął zakaz na
pomiary, które go dotyczyły. Zostają jako wejścia **swoich** kanałów: 2a/2b dla `saos` (osobny
ADR po bramce fazy 1), 4b/16 dla `uzp` w rolach weryfikacji i dopływu (faza 2).

Poza bramką zostają świadomie:

- **pomiar 9 (tempo)** — mierzy tolerancję serwisu, którego rola nie jest jeszcze
  rozstrzygnięta. Obciążanie cudzej infrastruktury dla decyzji, która może nie zapaść, jest
  dokładnie tym, czego zakazuje reguła zgody. Dla Atlasu zbędny: limity są publikowane
  i raportowane nagłówkami `X-RateLimit-*`;
- **pomiary 7 i 19** — od 2026-09-18 wejścia polityki wersji kanału `uzp`, nie ADR-0001
  (ADR-0005 Z-4: klucz `(doc_id, content_sha256)` jest poprawny przy obu wynikach pomiaru 19).
  Ich kosztem jest kalendarz, a bramka na nie nie czeka;
- **pomiar 17 (postaci sygnatur)** — wejście ADR-0001, wykonywane na stu rekordach listy
  z pomiaru 3a i na rekordach pierwszego przebiegu, zero dodatkowych żądań;
- **pomiary 5, 10, 22** — przygotowanie fazy 2.

### 3.1 Pytanie 2 do prawnika nie jest wejściem tej bramki (rozstrzygnięcie 2026-09-17)

Pytanie 2 z `docs/pisma/pytania_do_prawnika.md` — relacja ochrony baz danych *sui generis* do
ustawowego prawa reużycia — brzmiało „czy wolno pobrać istotną część cudzej bazy". Po decyzji B
(`docs/decisions.md`) odpowiedź brzmi: **nie pobieramy istotnej części tej bazy.**

UZP nigdy nie pełni roli kanału masowego. Zostają dwie role — weryfikacja na próbce
(`porownaj`) i dopływ bieżący — rzędu kilkudziesięciu żądań, nie 63 000. Pobranie całości idzie
wyłącznie z kanału, który ponowne wykorzystywanie **licencjonuje wprost**.

Uzasadnienie stoi zresztą w treści samego pytania: przy odpowiedzi niepewnej rozstrzygnięciem
miało być „pobranie przez pośrednika […] zamiast bezpośrednio z serwisu Urzędu — czyli **inne
rozstrzygnięcie architektoniczne, nie inne pismo**". Decyzja B jest tym rozstrzygnięciem,
podjętym z góry zamiast warunkowo.

Pytanie nie znika jako **ryzyko** — znika jako **wejście bramki**. Brak opinii prawnej jest
ryzykiem resztkowym przyjętym świadomie przez właściciela (decyzja A) i tak jest zapisany;
decyzja B je zawęża, nie usuwa.

Ślad po wcześniejszych brzmieniach, bo ten dokument powstał przeciwko trzem brzmieniom tego
samego (sekcja 1) i zdążył mieć dwa własne: sekcja 7 mówiła „to jest jedyne wejście tej bramki,
którego nie da się przyspieszyć pracą własną", sekcja 3 wymieniała cztery pomiary i wyrzucała
z bramki wszystko o koszcie kalendarzowym. Rano 2026-09-17 rozstrzygnięto to na „wejście
warunkowe, czynne tylko przy negatywnych 2a i 3a"; po południu decyzja B uczyniła ten warunek
niespełnialnym, bo UZP nie dostanie roli masowej **w żadnej gałęzi**.

---

## 4. Tabela kandydatów — pusta do czasu pomiarów

Kolumny są stałe i każda komórka niesie **datę i sposób uzyskania**. Komórka bez daty jest
w tym dokumencie błędem, nie skrótem (zasada 7.1). „—" znaczy „niezmierzone", nigdy „brak".

| Kanał | Odcinek czasu | Dostęp własnym klientem | Kształt odpowiedzi | Zdolności (`capabilities()`) | Koszt w żądaniach | Data modyfikacji | Warunki prawne | Ryzyko kontraktu | Werdykt |
|---|---|---|---|---|---|---|---|---|---|
| `saos` | 2007-12 – 2018-09 (deklaracja SAOS) | — (pomiar 2a) | — (pomiar 2a) | — (pomiar 2b) | — (pomiar 2b) | deklarowana `sinceModificationDate`, niezmierzona | korzeń `www.saos.org.pl` nie odpowiedział w 45 s (pomiar 23, zmierzone 2026-09-18, 1 żądanie) | — | **nierozstrzygnięty** (2026-09-18, odroczone: nie jest pierwszym adapterem — ADR-0005 Z-2/Z-3; wraca jako osobny ADR po bramce fazy 1, jeśli odcinek 2007–2009 okaże się nieobsadzony) |
| `atlas` | co najmniej rocznik 2010 – 2026: 91 ze 100 najstarszych rekordów ma sufiks sygnatury `/10` (zmierzone 2026-09-18, 2 żądania); `ruling_date` bywa błędne (`kio-1205-20`: 2004-01-29 wobec rozprawy 2020-06-16; w styczniu 2024 — 9 z 295 dat wcześniejszych niż rozprawa), więc dolna granica z sortowania nie jest wiarygodna, a roczniki 2007–2009 są niezmierzone | tak, anonimowo: 200 na liście i na dokumencie (zmierzone 2026-09-18, `sonda-20260918T103525Z`) | lista `data[]` z `has_more`/`page`/`per_page`/`total`; dokument 34 pól, w tym `full_text` (3 021 znaków w postanowieniu `KIO 1205/20`), `signatures`, `document_id` = identyfikator UZP z `source_url`, `created_at`/`updated_at` (zmierzone 2026-09-18) | filtry z dokumentacji odczytanej 2026-09-18: `search, outcome, ruling_kind, date_from, date_to, law_article, chairperson, party, cpv, tender_id, bzp_number, costs_min, costs_max, with_thesis, sort, page, per_page≤100` (ADR-0005 Z-9) | ~29 900 na cały zbiór: 29 580 dokumentów (`total`, zmierzone 2026-09-18) + 296 stron listy po 100 | `updated_at` w rekordzie dokumentu (zmierzone 2026-09-18); dokumentacja pola nie wymienia | CC BY 4.0 z atrybucją „Źródło: Atlas Przetargów (https://atlasprzetargow.pl)" — odczytane u dostawcy 2026-09-18 (pomiar 23, `## Pomiar 23` w `decisions.md` z SHA-256 strony) | zależność od cudzego SLA i cudzego potoku z PDF — zmierzone 2026-09-18: `ruling_date` 2004-01-29 przy treści „z dnia 16 czerwca 2020 r." | **zmierzony 2026-09-18** — pierwszy adapter (sekcja 6) |
| `uzp` | 2007-12 – dziś (obecność sygnatur z 2007 niepotwierdzona własnym odczytem) | — (pomiar 4b) | — (pomiar 4b) | — (pomiar 4b/16) | ~63 000 na cały zbiór przez `GetResults` (policzone, 2026-09-14) | brak; trzy osie z 4.6 | brak warunków i brak informacji o ich braku (pomiar 14, zmierzone 2026-09-15) | kontrakt przeniesiony w lipcu 2026 | **nierozstrzygnięty** (2026-09-18, odroczone do fazy 2: role weryfikacji i dopływu z decyzji B, wejście 4b/16 idzie z tym kanałem — ADR-0005 Z-1) |
| `uzp_zrzut` | — | — | — | — | — | — | art. 39 ust. 2 ustawy o otwartych danych | — | **odpada** (2026-09-17, decyzja A właściciela: projekt nie prowadzi korespondencji, więc wniosek nie zostanie złożony i kanał nie ma z czego powstać) |

### 4.1 Skąd bierze się kolumna `capabilities()` (dopisana 2026-09-17)

Kolumna była powoływana w **czterech** miejscach — `ARCHITEKTURA_KIO_TOOL.md` 5.2 („tabela
kandydatów z `capabilities()` i kosztem z 5.3"), `tests/queries/README.md`, `CLAUDE.md` i brief
sesji — a w tabeli jej nie było. Twierdzenie bez desygnatu jest tym samym kształtem błędu, przed
którym ostrzega zasada 7.1, zastosowanym do struktury zamiast do liczby.

Kolumna jest potrzebna, bo kryterium wyjścia (sekcja 5 pkt 5) każe wybrać **pierwszy adapter**,
a żadna z pozostałych kolumn nie niesie tego, co kanał **umie**. Kanał, który nie umie filtrować
po tym, czego operator naprawdę szuka, jest gorszym kanałem niezależnie od tego, ile dokumentów
niesie i jak tanio. Wejściem do tej kolumny miał być zestaw zapytań operatora z `tests/queries/`.
**Od 2026-09-18 (ADR-0005 Z-9)** przy jednym kandydacie porównanie zdolności nie ma z czym się
zmierzyć: kolumnę wypełnia udokumentowana lista filtrów (odczyt 2026-09-18), a zestaw zapytań
wraca w fazie 3 jako miara wyszukiwania.

### 4.2 Trzy postaci domknięcia wiersza (rozstrzygnięcia 2026-09-17 i 2026-09-18)

Wiersz tabeli jest domknięty w jednej z trzech postaci:

1. **zmierzony** — kolumny „dostęp" i „kształt" wypełnione, każda komórka z datą i sposobem
   uzyskania. **Jedyna postać dopuszczalna dla kanału obecnego w `kio_tool/source/`**;
2. **odpada** — jawny werdykt „odpada, powód, data";
3. **nierozstrzygnięty** — jawny werdykt „nierozstrzygnięty (data, powód odroczenia)"; od
   2026-09-18, ADR-0005 Z-2. Kanał z tym werdyktem **nie ma prawa mieć katalogu** w `source/`
   — strażnik zapala się na kanale w drzewie, którego wiersz zamyka się werdyktem 2 albo 3.

**Postać usunięta 2026-09-17 nie wraca pod nową nazwą.** Brzmiała „otwarty warunkowo: wniosek
złożony {data}, termin ustawowy {data}" i powstała dla wiersza `uzp_zrzut`, bo kryterium z sekcji 5
pkt 2 żądało domknięcia **każdego** wiersza, a kanału warunkowego nie wypełniłby żaden pomiar —
tylko odpowiedź urzędu, czyli 14 dni do 2 miesięcy. Po decyzji A ten wiersz zamyka się werdyktem
„odpada" i tamta postać straciła jedynego użytkownika; zostawienie jej byłoby furtką pozwalającą
uznać za zamknięty wiersz kanału, **który wolno było budować**, bez pomiaru i bez werdyktu.

Postać 3 różni się dokładnie w tym punkcie: zamyka wiersz kanału, którego budować **nie wolno**.
Kryterium chroni więc tę samą własność co przedtem — żaden adapter bez pomiaru — implikacją
drzewo → tabela (kierunek reguły 21), i przestaje chronić własności „żaden korpus, zanim nie
zmierzysz wszystkich kandydatów", która kosztowała żądania do dwóch serwisów bez obserwowalnej
korzyści. Kryterium jest przez to węższe w zasięgu i ściślejsze w kierunku.

Wiersz `uzp_zrzut` był kanałem **warunkowym** — miał powstać, gdyby wniosek z art. 39 przyniósł
zrzut albo punkt z datą modyfikacji. Wtedy trzy osie wykrywania nowości z 4.6 redukowałyby się
do jednej, a kanał nie byłby objęty żadnym z pomiarów 1–22.

**Wiersz jest zamknięty odmownie 2026-09-17** (decyzja A, `docs/decisions.md`): projekt nie
prowadzi korespondencji, więc wniosek nie zostanie złożony. Zostają trzy osie i to jest cena
tej decyzji — koszt wykonawcy, nie właściciela. Projekt pisma nie znika z `docs/pisma/`;
gdyby decyzja kiedyś się zmieniła, wiersz wraca do tabeli jako nowy kandydat z datą.

---

## 5. Kryterium wyjścia — wykonywalne, nie deklarowane

Bramka fazy 0 jest zamknięta, gdy **wszystkie** poniższe są prawdziwe:

1. ten plik ma status `accepted` z datą i z podpisem decyzji właściciela;
2. każdy wiersz tabeli z sekcji 4 jest domknięty w jednej z trzech postaci z sekcji 4.2 —
   zmierzony, odpada z powodem i datą, nierozstrzygnięty z datą i powodem odroczenia — przy czym
   wiersz kanału **obecnego w `kio_tool/source/`** jest zmierzony;
3. każda liczba w tabeli niesie datę i sposób uzyskania;
4. wynik każdego pomiaru wejściowego kanału obecnego w drzewie (pole `pomiary:` jego
   `contract.yaml`) stoi w `docs/decisions.md` w konwencji zdania z datą i liczbą żądań,
   a wiersze żądań — w `docs/dziennik_zadan.md`;
5. wybrany jest **pierwszy adapter** (sekcja 6) i zapisany powód wyboru.

Dopóki punkt 1 nie jest spełniony, `source/` nie powstaje. Reguły 21 i 17 przy pustym `source/`
przechodzą **pusto**, więc nie są strażnikiem tej bramki, tylko strażnikiem tego, żeby kanał
nie powstał po cichu w kawałkach.

**Strażnik samej bramki powstał 2026-09-17: `tests/test_bramki_faz.py`.** Zdanie wyżej stało tu
w wersji pierwotnej jako przyznanie się do braku — i było cytowane w nagłówku tamtego pliku jako
powód jego istnienia. Od 2026-09-18 (ADR-0005) czerwono robi się w czterech sytuacjach: gdy
`kio_tool/source/` niesie kanał, a ten dokument nie ma statusu `accepted`; gdy ten dokument **ma**
status `accepted`, a któryś wiersz tabeli z sekcji 4 nie jest domknięty w jednej z trzech postaci
z sekcji 4.2; gdy kanał obecny w drzewie ma wiersz zamknięty werdyktem „odpada" albo
„nierozstrzygnięty" zamiast pomiaru — albo nie ma wiersza wcale; oraz gdy `contract.yaml` kanału
z drzewa wymienia pomiar, którego wyniku `docs/decisions.md` nie niesie (albo nie wymienia
żadnego). Punktów 1 i 5 kryterium **żaden test nie sprawdza i nie ma sprawdzać** — podpis
właściciela i powód wyboru pierwszego adaptera to nie są własności drzewa plików.

---

## 6. Pierwszy adapter: kryterium i trzy warianty

Kryterium nie brzmi „który odcinek jest najcenniejszy", tylko: **na którym kanale kształt
`protocol.py`, `contract.py`, `registry.py` i `store.py` może się iterować, nie obciążając
cudzego serwera.** Pierwszy adapter ustala kształt dla wszystkich następnych, więc każda
poprawka projektowa na nim kosztuje tyle, ile kosztuje jego kanał.

| Wariant | Warunek wejścia | Za | Przeciw |
|---|---|---|---|
| **A: `saos` pierwszy** | pomiar 2a pozytywny | rekord Dump API jest kompletny, więc `fetch` jest jednokrokowy; archiwum zamrożone na 2018-09, więc przebieg jest **deterministyczny i powtarzalny** — bramka fazy 1 („przerwany i wznowiony bez duplikatów") ma wtedy stabilne wejście; zero obciążenia UZP | nie ćwiczy osi „co nowego" ani dwukrokowego pobrania |
| **B: `atlas` pierwszy** | pomiar 3a pozytywny | ćwiczy klucz API (pierwszy wywołujący `register_secret`), `Retry-After`, atrybucję z reguły 15 i odrzucanie pól od modelu z reguły 19; prawdopodobnie pokrywa cały zakres | kompletność pośrednika niepotwierdzona; wchodzi zależność od cudzego SLA |
| **C: `uzp` pierwszy** | pomiar 4b pozytywny | najwierniejsze źródło | 2 żądania na dokument, parser HTML, kontrakt przebudowany w lipcu 2026, najcięższe obciążenie cudzego serwera, wymaga jeszcze pomiaru 9 |

**Wariant C jest od 2026-09-17 wykluczony, a nie odradzany** (decyzja B, `docs/decisions.md`):
UZP nie pełni roli kanału masowego, więc nie może być ani pierwszym adapterem, ani żadnym
późniejszym adapterem pobierającym całość. Wiersz zostaje w tabeli, bo pokazuje, co tracimy,
i dlatego, że `uzp` nadal powstanie — w roli weryfikacji i dopływu bieżącego.

Gdyby pomiar 3a wypadł negatywnie, nie oznacza to powrotu wariantu C. Oznacza, że projekt nie
ma kanału masowego i to jest wynik fazy 0, a nie zaproszenie do obejścia własnej reguły. Wtedy
wraca pytanie, którego decyzja A nie zadaje — i decyzję trzeba podjąć ponownie, świadomie, a nie
przez wyczerpanie listy.

**Rozstrzygnięcie 2026-09-18 (ADR-0005 Z-3): wariant B, `atlas` pierwszy — bezwarunkowo.**
Do tego dnia rekomendacja była warunkowa („A, jeśli 2a padnie pozytywnie; inaczej B") i to ona
sprzęgała budowę adaptera Atlasu z pomiarem SAOS. Kryterium z początku tej sekcji rozstrzyga na
korzyść Atlasu: limity są publikowane i raportowane nagłówkami `X-RateLimit-*` (jedyny kanał,
na którym „ile wolno" nie jest zgadywaniem), a `RateLimiter.note_budget` — funkcja przetestowana
i bez ani jednego wywołania produkcyjnego — dostaje wywołującego. SAOS wygrywa wyłącznie na
determinizmie zamrożonego archiwum, a przegrywa na trzech rzeczach naraz: dostęp nieprzetestowany
(403 na API wyszukiwania), zasięg z definicji niepełny, warunki reuse nieodczytane. Determinizm
kupowałoby się kosztem adaptera, który nigdy nie uniesie korpusu. Cena wyboru B, wypisana wprost:
kompletność pośrednika zostaje niepotwierdzona do czasu `porownaj` (faza 2), a odcinek 2007–2018
zależy od tego, od kiedy sięga zbiór Atlasu (pomiar 3a, `sort=oldest`). `saos` wraca jako osobny
ADR po bramce fazy 1, jeśli ten odcinek okaże się nieobsadzony.

**Wybór 2026-09-18 (kryterium wyjścia, pkt 5): pierwszym adapterem jest `atlas`.** Powód
z pomiarów tego dnia: pomiar 3a pozytywny — dokument `GET /api/kio/{slug}` niesie pełny tekst
w polu `full_text` razem z listą sygnatur i identyfikatorem UZP, lista stronicuje przez
`has_more`, dostęp anonimowy działa; pomiar 23 — licencja CC BY 4.0 z formułą atrybucji
odczytana u dostawcy, podczas gdy korzeń SAOS nie odpowiedział w 45 s. Cena zapisana wyżej:
kompletność i jakość pól pochodzą z cudzego potoku (zmierzone błędy `ruling_date`: 2004 wobec
rozprawy w 2020 w najstarszej próbce; 9 z 295 dat wcześniejszych niż rozprawa w styczniu 2024),
a roczniki 2007–2009 są niezmierzone.

---

## 7. Co ten dokument zapisuje jako niewiadome

- **Czy odcinek 2007–2018 ma drogę poza SAOS.** Audyt 14.2 mówi, że przy negatywnym pomiarze
  2a „połowa rekomendowanej architektury znika". Przegląd z 2026-09-17 osłabia to zdanie,
  wskazując, że sygnatury z grudnia 2007 widziano w wyszukiwarce UZP (audyt 2.4) — ale ten
  odczyt pochodzi z przebiegu, w którym do `orzeczenia.uzp.gov.pl` poszło **zero żądań**
  (architektura 7), czyli z wyników cudzej wyszukiwarki. Status: **niepotwierdzone
  samodzielnie**. Rozstrzyga to pomiar 3a (zasięg zbioru pośrednika) i jedno zapytanie
  `GetResults` z zakresem dat z 2007 r. po pozytywnym 4b.
- **Czy pomiar 4b jest odczytem, czy obejściem.** Jeśli UZP odpowie CAPTCHĄ albo blokadą,
  narzędzie zatrzymuje się i mówi o tym operatorowi (audyt 12, art. 267 § 1 k.k.). Po decyzji A
  nie ma wtedy drogi zapasowej: wniosek z art. 39 był jedyną i nie zostanie złożony. Odmowa
  zamyka to źródło **także w rolach weryfikacji i dopływu**, a projekt zostaje z tym, co dają
  pośrednicy. To jest cena decyzji A zapisana w miejscu, w którym się zmaterializuje.
- **Czy licencje pośredników wystarczają zamiast opinii prawnej.** Nie wystarczają — zastępują
  ją częściowo i tak są zapisane. Atlas publikuje na CC BY 4.0 z wymaganą atrybucją
  (dokumentacja odczytana 2026-09-14); warunków SAOS nikt tu jeszcze nie czytał u źródła
  i rozstrzyga to **pomiar 23** (`docs/decisions.md`, „Status pomiarów"). Licencja odczytana u dostawcy z datą jest
  mocniejszą podstawą niż cudza interpretacja przepisu, ale nie jest opinią prawną i nie udaje
  jej. Ryzyko resztkowe pozostaje przyjęte przez właściciela (decyzja A).
