# ADR-0008: Faza 3 — kreator nad istniejącym punktem zgody, wycena bez dodatkowego żądania, tryb pokazowy jako podstawiony transport nad korpusem generowanym

Data: 2026-09-19
Status: accepted (2026-09-19, decyzja właściciela — sekcja 11)
Autor: P0w3r223
Related to: `docs/AUDYT_KIO_ORZECZENIA.md` (7.1, 7.4, 8.3 reguły 1–16, 9 „Faza 3", 11 miny 2 i 4), `docs/ARCHITEKTURA_KIO_TOOL.md` (4.1 reguły 17–23, 4.2, 4.8, 4.9, 5.1–5.3), `docs/decisions.md` („Pomiar 3a", „Pomiar 17", „Jakość pól Atlasu", „Przebieg 1", „Pomiar filtrów Atlasu", „Pomiar 5"), `docs/adr/0006_parser_i_struktura.md`, `docs/adr/0007_polityka_ponowien.md`, `ceidg-tool/docs/adr/0008_phase3_user_interface.md`, `ceidg-tool/docs/adr/0014_offline_demo_mode.md`, `ceidg-tool/docs/adr/0017_clarification_round.md`, `kio_tool/pipeline.py`, `kio_tool/cli.py`, `kio_tool/ui/texts.py`, `kio_tool/exporter.py`, `kio_tool/store.py`, `tests/test_boundaries.py`, `tests/test_bramki_faz.py`

---

## 1. Kontekst: co wie drzewo

Stan odczytany z plików 2026-09-19, zero żądań:

- Sześć poleceń (`pobierz`, `wznow`, `eksportuj`, `runy`, `przelicz`, `szukaj`) woła `pipeline` wprost
  z `cli.py`; zdania są w `ui/texts.py`, rysowanie w `ui/render.py`. `questionary>=2.0` stoi
  w `pyproject.toml`, ale nie importuje go żaden moduł. `ui/{wizard,flow,prompts}.py` i `kio-tool demo`
  nie istnieją.
- `pipeline.py` ma ponad 800 linii, a etap V ADR-0006 dopisuje do niego zapis sekcji, cytowań
  i przepisów, w tym samym `_przebieg`.
- `store.py` stoi na schemacie 5 (ADR-0007 Z-8); faza 2 dostaje 6. Faza 3 nie sięga po żaden numer.

### 1.1 Wycena i zgoda mają już jedno miejsce w potoku

`pipeline._przebieg` woła `_wymagaj_zgody` przy pierwszym kandydacie — **po pierwszej stronie listy,
przed pierwszym dokumentem** — kiedy `_Puls.on_page` zna już `total` kanału. Przebieg 1 jest pomiarem
tego punktu: bez `--zgoda` przebieg stanął po 1 żądaniu, to samo polecenie z `--zgoda` go wznowiło.
Tabela kosztów potrzebuje dokładnie liczby, którą ten punkt ma w ręku; osobne żądanie „policz"
kosztowałoby stronę 1 dwa razy.

### 1.2 Eksport jest blokiem cytowania, więc znaczniki ceidg nie wystarczą

`exporter.blok_atrybucji` składa dla **każdego rekordu** blok z organem, sygnaturą, adresem źródła
i licencją kanału. Rekord pokazowy puszczony przez ten kod bez zmian jest fałszywym cytatem
przypisanym realnemu organowi i realnemu pośrednikowi. ADR-0014 `ceidg-tool` znakował skoroszyt, bo
tam jednostką był skoroszyt; tu jednostką bywa pojedynczy `.md` albo wiersz JSONL. Drugi kształt tego
samego: `url_zrodla` ma postać `https://orzeczenia.uzp.gov.pl/Home/PdfContent/{id}?Kind=KIO`
(Pomiar 3a), więc zmyślony identyfikator w tym wzorcu **otwiera prawdziwe, inne orzeczenie**.

### 1.3 Korpusu nie ma skąd skopiować

Korpus operatora i złote pliki niosą nazwiska składu, protokolantów i stron — nagranie odpada
(audyt 9, mina 4). Z pamięci też nie: etykieta „art. N Pzp" z 2010 r. w orzeczeniu z 2024 r. to mina 2
z ADR-0006 §1.1. Wszystko, co w korpusie pokazowym udaje dane odniesienia, ma pochodzić z pliku
generowanego ze źródła o zapisanym SHA-256.

### 1.4 Ścieżka z architektury 5.2 obiecuje trzy rzeczy, których drzewo nie ma

- „hasło indeksu tematycznego" — Atlas nie ma takiego filtra;
- „przepis Pzp z podpowiedzią ze słownika" — słownika nie ma i w fazie 2 nie będzie (ADR-0006 Z-13);
- „fraza" jako cel pobrania — `search` Atlasu dopasowuje **sygnaturę, nie treść** (zmierzone).

Krok „Kanał" ma dziś jeden wiersz: `REGISTRY` = `{atlas}`.

### 1.5 Reguły granic wykluczają dwa odruchy

Reguła 8 wyklucza kreator trzymający `Store`. Reguły 17, 19, 21, 23 i bramka per kanał (ADR-0005)
wykluczają „kanał pokazowy" bez fałszowania dowodów (§3.1).

---

## 2. Co ten ADR rozstrzyga

| # | Pozycja | Rozstrzygnięcie | Powód |
|---|---|---|---|
| **Z-1** | Tryb pokazowy | Podstawiony transport pod **prawdziwym** kanałem `atlas`: `httpx.MockTransport` odpowiadający z korpusu generowanego w procesie, podany istniejącym szwem `pipeline.pobierz(klient_factory=…)` i wybrany w `cli.py`. Nie kanał w `source/` | Pokaz jedzie ścieżką operatora — adapter, ocena kształtu, limiter, potok, parser, magazyn, eksport — a reguły kanałów zostają nietknięte |
| **Z-2** | Znacznik w danych | Baza pokazowa ma `PRAGMA application_id` = `store.ID_BAZY_POKAZOWEJ`. `Store` odmawia bazy pokazowej w trybie produkcyjnym i niepustej bazy bez znacznika w trybie pokazowym; `demo --od-nowa` kasuje wyłącznie plik ze znacznikiem. `SCHEMA_VERSION` bez zmian | Znacznik jedzie z plikiem przy kopiowaniu; bez migracji |
| **Z-3** | Znaczniki artefaktów | Sześć, **obowiązkowych łącznie**: (1) pierwszy ekran; (2) wiersz `tryb` w `Metadane`; (3) przedrostek `DEMO_` każdego pliku i katalogu `_md`, także pod `--out`; (4) osobny katalog danych razem z Z-2; (5) **linia atrybucji każdego rekordu** zastąpiona zdaniem o fikcji (`exporter.ATRYBUCJA_POKAZU`); (6) pierwszy wiersz `full_text` i pole `demo` w surowym rekordzie. Adresy w domenie zastrzeżonej `.invalid` | §1.2 — jednostką eksportu bywa pojedynczy rekord |
| **Z-4** | Skąd eksport wie o trybie | Znaczniki 2, 3 i 5 wynikają **z bazy** (`Store.pokazowa`), nie z flagi `cli` | Baza pokazowa jest oznaczona niezależnie od wejścia |
| **Z-5** | Wycena | Czysty `kio_tool/wycena.py`: strony listy, dokumenty, żądania, czas z `tempo` kontraktu **z oknami**; przy wznowieniu — reszta. Liczby są górną granicą | Czas przy oknie dobowym nie jest `N × odstęp`: rocznik ~4 300 żądań to ~3 doby |
| **Z-6** | Punkt decyzji | `pipeline.pobierz(…, decyzja: Decyzja)`, `Decyzja = Callable[[Wycena], bool]`, wołane **raz na wywołanie**, w miejscu dzisiejszego `_wymagaj_zgody`. `False` → `ConsentMissingError` jak dziś. Flagi: polityka `--zgoda`/`PROG_ZGODY` i tabela drukowana zawsze; kreator: pytanie. Strażnik licznika żądań dla kanału bez `total` i przed każdym ponowieniem (ADR-0007 Z-9) zostaje | Zero dodatkowych żądań, jedna sekwencja dla flag, kreatora i pokazu |
| **Z-7** | Warstwa `ui/` | `texts.py` jedynym autorem zdań **i pytań** (`Pytanie`, `Opcja` jako dane); `prompts.py` jedynym importerem `questionary`; `flow.py` — sekwencje nad protokołem `Akcje`; `wizard.py` — pierwszy ekran, menu, pętla. Implementacja `Akcje` nad `pipeline` i otwartym `Store` — w `cli.py` | Reguła 8 |
| **Z-8** | Wejścia | `kio-tool` bez argumentów **na terminalu** → kreator (poza terminalem pomoc); `kio-tool demo` → kreator nad bazą pokazową. Flagi zachowują semantykę i zyskują tabelę kosztów | Operator nieznający poleceń wpisuje nazwę programu |
| **Z-9** | Menu i cele | **Wznów** (pierwsza, gdy jest co), **Pobierz**, **Szukaj w korpusie**, **Eksportuj**, **Wyjdź**. Cele pobrania: zakres dat; jedna sygnatura; rozstrzygnięcie i rodzaj z list zmierzonych; przepis — z ostrzeżeniem o semantyce niezmierzonej i dwóch ustawach. Krok „Kanał" zwinięty, dopóki `REGISTRY` ma jeden klucz | §1.4 |
| **Z-10** | Bez ślepych uliczek | Zero kandydatów → pytanie z opcjami z `Criteria.poszerzenia()` + „popraw" + „menu"; fraza w celu pobrania → zdanie o semantyce `search` i droga „pobierz zakres, potem szukaj"; brak `KIO_TOOL_CONTACT` → pozycja Pobierz mówi dlaczego i jak, reszta menu działa; błąd akcji → zdanie i powrót do menu; `Ctrl+C` w trakcie → przebieg `przerwany`, powrót do menu | ADR-0017 `ceidg-tool` bez modelu |
| **Z-11** | Korpus pokazowy | Generowany w procesie, deterministyczny (stałe ziarno), ~360 dokumentów z dat I kwartału 2024. Dane odniesienia wyłącznie z `kio_tool/demo/wzorce.yaml`, generowanego przez `scripts/zbuduj_wzorce_demo.py` z bazy operatora (0 żądań), z SHA-256 wejścia i datą, bez żadnego pola osobowego. Osoby i strony z puli jawnie fikcyjnej. Sygnatury z numerami 9000–9999 | §1.3 |
| **Z-12** | Cechy trzymane testem | `tests/fixtures/cechy_atlasu.yaml`: każda cecha z wartością, źródłem i datą; `tests/test_demo_cechy.py` mierzy korpus i atrapę | Korpus nietrzymany pomiarem dryfuje |
| **Z-13** | Czas | `ZegarDemo` przyspiesza `monotonic`/`sleep`, nie `wall`. Tabela kosztów drukuje czas **produkcyjny**, obok czas pokazu | Uczciwość wyceny |
| **Z-14** | Pokaz nie dotyka poświadczeń | `demo` nie czyta `KIO_TOOL_CONTACT` (stały `User-Agent` pokazu, legalny wyłącznie z `MockTransport`) ani `KIO_TOOL_ATLAS_KEY` | Pokaz ma działać w dniu klonu |
| **Z-15** | Reguła 10 obejmuje `questionary` | Skan reguły 10 obejmuje `ui/prompts.py` z neutralizatorem pytań; brzmienie w audycie 8.3 dopisuje `questionary` | Nowy kanał ekranu: etykiety z bazy i kryteria operatora |
| **Z-16** | Reguła 1 | `wycena.py` i `demo/korpus.py` dopisane do modułów czystych | Sprawdzalne bez atrap |
| **Z-17** | Bramka „kod po decyzji" | `tests/test_bramki_faz.py`: `ui/wizard.py` i `kio_tool/demo/` → ADR-0008; `0008` w `NUMERY_ADR_OCZEKIWANE` w tym samym commicie co plik ADR-a | Czwarta i piąta bramka tego samego kształtu |

---

## 3. Warianty rozważone i ich cena

### 3.1 Tryb pokazowy

| Wariant | Za | Przeciw | Nakład / ryzyko |
|---|---|---|---|
| **A1. Podstawiony transport pod kanałem `atlas`, korpus generowany (wybrany)** | pokaz = ścieżka operatora: tabela kosztów, zgoda, puls, `Ctrl+C` i wznowienie, eksport; faza 2 dostaje dane za darmo; reguły 11 i 17–23 nietknięte | baza pokazowa niesie `doc_id` `atlas:…` i dziennik z hostem Atlasu — prawdziwe co do ścieżki, fałszywe co do świata; stąd Z-2–Z-4 | M / średnie |
| A2. Kanał `source/demo/` z własnym `contract.yaml` | `doc_id` `demo:…` | kanał bez pomiarów musi przejść bramkę per kanał i reguły 17, 19, 23 — albo wyjątki osłabiające bramki prawdziwych kanałów, albo fałszywe dowody; `demo` w `REGISTRY` widoczny w produkcji | L / wysokie |
| A3. Baza pokazowa wypełniana wprost | najtańsza | brak tabeli kosztów, zgody, pulsu, przerwania i wznowienia — bramki „cała ścieżka" nie da się przejść | S / niskie — **plan awaryjny** |
| A4. Nagranie ruchu z anonimizacją | realizm | nazwiska; audyt 9 i mina 4 zakazują wprost | odrzucony |

### 3.2 Gdzie mieszka wycena i decyzja

| Wariant | Żądań na pobranie | Za | Przeciw |
|---|---|---|---|
| B1. Osobne `pipeline.wycen()`, potem `pobierz` | +1 | decyzja poza długą operacją | strona 1 dwa razy; flagi dostają drugą sekwencję |
| **B2. Wywołanie zwrotne `decyzja` w punkcie zgody (wybrany)** | 0 | jedna sekwencja dla flag, kreatora i pokazu | człowiek decyduje, gdy przebieg jest `w_toku` — ubicie przy pytaniu zostawia go osieroconym, wznawialnym |
| B3. Pełne przeniesienie `cli.pobierz` na `ui/flow` | 0 albo +1 | jedna sekwencja z definicji | refaktor w tygodniu, w którym faza 2 edytuje `pipeline` |

### 3.3 Jak kreator dochodzi do potoku (reguła 8)

| Wariant | Za | Przeciw |
|---|---|---|
| **C1. Protokół `Akcje` w `ui/flow.py`, implementacja w `cli.py` (wybrany)** | `flow` testowalny na atrapie akcji, bez bazy i sieci; reguła 8 bez zmian | ~60 linii pośrednich w `cli.py` |
| C2. `flow` dostaje `Store` przez reeksport z `pipeline` | krócej | skan reguły 8 to przepuści — luka, nie zgodność |

### 3.4 Znacznik bazy pokazowej

| Wariant | Za | Przeciw |
|---|---|---|
| D1. Sam osobny katalog | zero zmian w `store` | `--baza` na plik pokazowy otwiera go w produkcji bez słowa |
| **D2. `PRAGMA application_id` (wybrany)** | jedzie z plikiem; odmowa w obie strony; bez migracji | jedna gałąź w `Store.__init__` |
| D3. Kolumna albo wartość w schemacie | najbardziej jawny | migracja w tygodniu migracji fazy 2 |

### 3.5 Sygnatury w korpusie pokazowym

| Wariant | Za | Przeciw |
|---|---|---|
| **E1. Numery 9000–9999, lata `/23` i `/24` (wybrany)** | postać zmierzona, pole tożsamości wierne; numer ponad dwukrotnie powyżej zmierzonego maksimum | argument z liczb, nie gwarancja — dlatego sygnatura nie jest jedynym znacznikiem |
| E2. Rok sprzed Izby (`/00`–`/06`) | pewność | rozjazd roku sygnatury z datą w 100 % — raport pokrycia fazy 2 liczyłby bzdurę |
| E3. Numery pięciocyfrowe | rzucają się w oczy | postać niezmierzona |

---

## 4. Co z `ceidg-tool` przechodzi, co się zmienia, co nie przechodzi

| Wzorzec ceidg | Tutaj | Dlaczego |
|---|---|---|
| ADR-0014: praca bez rejestru jako własność produktu | **przechodzi**, argument mocniejszy | każdy przebieg próbny obciąża cudzy serwis |
| ADR-0014: podstawienie w korzeniu kompozycji | **przechodzi**: `cli` → `klient_factory`; dochodzi test „produkcja bez `transport=`" | ceidg miał taki test, Kio nie |
| ADR-0014: bez nowego hosta w mapie wyjścia | **przechodzi** | `MockTransport` nie otwiera połączenia |
| ADR-0014: korpus generowany, zmierzone rozkłady | **przechodzi** + dane odniesienia z pliku generowanego | mina 4 |
| ADR-0014: pięć znaczników łącznie | **zmienia się**: sześć, a odmowa łączenia schodzi z flagi do danych | §1.2 |
| ADR-0014: czas skalowany, tabela drukuje czas prawdziwy | **przechodzi** | — |
| ADR-0014: `api_traits.yaml` trzymane testem | **przechodzi** jako `cechy_atlasu.yaml` | — |
| ADR-0017: wyzwalacz „puste kryteria" | **nie przechodzi**: kreator zbiera kryteria polami | modelu w procesie nie ma |
| ADR-0017: zero trafień → poszerzenia liczone kodem | **przechodzi** | Z-10 |
| ADR-0008 ceidg: podział na partie | **nie przechodzi** | `batching.py` świadomie nieprzeniesiony |
| ADR-0008 ceidg decyzja 4: jedna firma po NIP | **przechodzi** jako „jedna sygnatura" | `search` = sygnatura |

---

## 5. Reguły granic — co z nich wynika

| Reguła | Co z niej wynika dla fazy 3 | Zmiana strażnika |
|---|---|---|
| 1 | `wycena.py`, `demo/korpus.py` bez `os`, `httpx`, `sqlite3`, `openpyxl`, `rich` | lista modułów czystych (Z-16) |
| 5 | `demo/` importuje `source.contract` i `httpclient`, **nigdy** `store` | bez zmian |
| 7 | `questionary` wyłącznie w `ui/prompts.py` | asercja obecności |
| 8 | `flow.py`, `wizard.py` bez `source`/`store` → `Akcje` | bez zmian |
| 10 | nowy kanał ekranu: `questionary` | skan na `prompts.py` (Z-15) |
| 11 | `MockTransport` wolno, klient wyłącznie z `build_http_client` | nowy test ścieżki produkcyjnej |
| 15 | rekord pokazowy niesie organ i **zdanie o fikcji** zamiast atrybucji Atlasu | `test_attribution.py` z eksportem pokazowym |
| 16 | stały `User-Agent` pokazu — legalny wyłącznie z `MockTransport` | test |
| 17, 19, 21, 22, 23 | nie dotyczą — pokaz nie jest kanałem | bez zmian |
| 20 | test końcowy pokazu pod `--block-network` | nowy test |

---

## 6. Korpus pokazowy — co generatorowi wolno

| Składnik | Źródło | Czego nie wolno |
|---|---|---|
| Etykiety przepisów, zwroty ustaw, `outcome_raw`, rozkłady `outcome` i `ruling_kind` | `demo/wzorce.yaml` ze `scripts/zbuduj_wzorce_demo.py` nad bazą operatora (0 żądań); nagłówek: data, liczba dokumentów, SHA-256 wejścia | pisać ręką, uzupełniać z pamięci |
| Kotwice i cechy tekstu | liczby z „Pomiar 5" przez `cechy_atlasu.yaml` | kotwic spoza pomiaru |
| Sygnatury | 9000–9999, `/23` i `/24` | numerów poniżej 9000 |
| Osoby, strony | pula jawnie fikcyjna; test: żaden napis puli nie występuje w polach osobowych złotych plików | imion i nazwisk z korpusu |
| Treść uzasadnień | zdania-wypełniacze jawnie pokazowe, z hasłami do wyszukania | zdań „Izba wskazała, że…" |
| Cytowania | wyłącznie sygnatury pokazowe; część celowo nienormalizowalna | sygnatur spoza puli pokazowej |
| Adresy | `https://pokaz.invalid/…` | wzorca `orzeczenia.uzp.gov.pl` |
| Napisy wrogie | `=` na początku, znaczniki `rich`, znak ESC | — |

Semantyka atrapy: `search` dopasowuje sygnaturę, `outcome` równość, daty po `ruling_date` — zmierzone;
`ruling_kind`, `law_article`, `chairperson`, `party` według dokumentacji — **założenie, niezmierzone**,
oznaczone w pliku cech. Nagłówków `X-RateLimit-*` atrapa nie wysyła, bo ich postać jest niezmierzona.

Korpus pokazowy nie pisze do tabel pochodnych — robi to potok, jak dla danych prawdziwych.

---

## 7. Kolejność prac

| # | Etap | Produkt | Zależy od |
|---|---|---|---|
| I | ADR-0008 przyjęty; `0008` i bramka (Z-17) jednym commitem | bramka | — |
| II | `wycena.py` + tabela kosztów + `Decyzja` w `pipeline`; test „produkcja bez `transport=`" | tabela na ścieżce flag | I; po etapie V ADR-0006 |
| III | `ui/prompts.py` + skan reguły 10 + asercja reguły 7 | pytający | I |
| IV | `ui/flow.py` + testy na atrapie akcji | sekwencje | II, III |
| V | `ui/wizard.py` + dyspozycja w `cli.py` + `_Akcje` | kreator produkcyjny | IV |
| VI | `Store`: `application_id`, `pokazowa`, odmowy; `config.katalog_demo()` | znacznik w danych | I |
| VII | `scripts/zbuduj_wzorce_demo.py` → `demo/wzorce.yaml`; `package-data` | wzorce z SHA-256 | I |
| VIII | `demo/korpus.py` + `cechy_atlasu.yaml` + `test_demo_cechy.py` | korpus | VII |
| IX | `demo/atlas.py` + `demo/__init__.py` (`zbuduj_demo`, `ZegarDemo`) | atrapa | VIII |
| X | Znaczniki eksportu z `Store.pokazowa` + `test_attribution.py` w obie strony | eksport oznaczony | VI |
| XI | Polecenie `demo` (+ `--od-nowa`) + test końcowy pod `--block-network` | bramka techniczna | V, IX, X |
| XII | CLAUDE.md, architektura, audyt 8.3, README | — | XI |
| XIII | Przejście operatora | wpis w `decisions.md` | XII |

**Linia cięcia**, gdyby tydzień nie wystarczył: cel „przepis", `--od-nowa` i tempo pokazu schodzą za
bramkę. Planem awaryjnym dla VIII–IX jest A3, ale z nim bramka fazy 3 nie domyka się w całości.

---

## 8. Cena, wypisana wprost

1. **Atrapa Atlasu żyje w pakiecie na stałe** — odpowiedzią jest sześć znaczników łącznie i test
   każdego.
2. **Baza pokazowa niesie `doc_id` `atlas:…`** — uczciwe wyłącznie razem ze znacznikiem bazy.
3. **Człowiek decyduje w środku otwartego przebiegu** (B2); ubicie przy pytaniu zostawia przebieg
   osierocony, wznawialny.
4. **Odmowa po wycenie zostawia przebieg `przerwany`** z powodem — lista „Wznów" rośnie o odmowy.
5. **`pipeline.py` zostaje ponad 800 linii** — podział wymaga decyzji o regule 5, osobny ADR.
6. **Wzorce wiążą pokaz z jednym zrzutem bazy operatora.**
7. **Cztery filtry atrapy odpowiadają według dokumentacji, nie pomiaru.**

---

## 9. Czego ten ADR nie rozstrzyga

Przejścia FTS na sekcje; `parquet` i `warc`; `aktualizuj`, `porownaj`, `cytowania`, `slowniki`,
`serve-mcp`; podziału `pipeline.py` i `store.py`; podpowiedzi przepisów ze słownika; listy sygnatur
jednym przebiegiem; przeniesienia flag na `ui/flow`.

---

## 10. Kryterium wyjścia z bramki fazy 3

1. `kio-tool demo` na świeżym klonie — bez `KIO_TOOL_CONTACT`, bez klucza, pod `--block-network` —
   przechodzi w teście końcowym ścieżkę: pobierz (tabela → zgoda) → przerwanie → wznów → wynik →
   szukaj → eksport, bez otwarcia gniazda;
2. sześć znaczników stoi w każdym formacie eksportu pokazowego i w żadnym produkcyjnym — test;
3. `test_demo_cechy.py` jest zielony, a odstępstwa są wypisane w pliku cech;
4. `pobierz` z flag drukuje tabelę kosztów przed pierwszym dokumentem, a liczba żądań przebiegu jest
   taka jak przed zmianą — test;
5. **przejście operatora** zapisane w `decisions.md` — każde pytanie przejścia jest usterką zdania
   albo kroku, naprawioną przed przyjęciem;
6. właściciel przyjmuje fazę.

---

## 11. Przyjęcie (2026-09-19)

Szkic przygotował architekt; właściciel przyjął go 2026-09-19 i rozstrzygnął pytania z szkicu:

1. `kio-tool` bez argumentów na terminalu **otwiera kreator** (Z-8 bez zmian).
2. `demo/wzorce.yaml` **wolno wygenerować z bazy operatora i zacommitować** z SHA-256 wejścia —
   wyłącznie etykiety przepisów, zwroty ustaw i rozkłady, biała lista kluczy pilnowana testem.
3. Sygnatury pokazowe: **wariant E1** (9000–9999), rekomendacja szkicu przyjęta bez uwag.
4. Odmowa po wycenie zostawia przebieg **`przerwany`** — rekomendacja szkicu, bez migracji statusu.
5. **Przejście operatora (§10 pkt 5) wykonuje sam właściciel**, gdy pokaz będzie gotowy; uwagi
   zapisuje się w `decisions.md` jako „Przejście operatora — tryb pokazowy".

---

## 12. Poprawki po przeglądzie kodu fazy 3 (2026-09-20)

Przegląd wykonany po zamknięciu prac, na zakresie `e8e595b~1..HEAD`. Cztery rzeczy zmieniają
brzmienie tego ADR-a; reszta znalezisk to usterki bez wpływu na decyzje i stoi w `decisions.md`.

### 12.1 Zgoda niesie sufit, a nie wyłącznik (HIGH)

Z-6 mówiło „werdykt operatora rozstrzyga, czy przebieg masowy jest dozwolony w tej sesji", a kod
czytał to jako wyłączenie progu `PROG_ZGODY` na resztę wywołania. Skutek jest mierzalny: przy
kanale zgłaszającym `total = 5` tabela kosztów pokazuje „5 żądań, 4 s", pytanie ma wtedy domyślne
„tak" (bo przebieg nie jest masowy), a Enter otwierał przebieg bez żadnego sufitu — **zmierzone
103 żądania przy progu 50**, z rozjazdem widocznym dopiero w podsumowaniu, czyli po wydatku.
Do wyzwolenia nie trzeba złośliwego serwisu: dokładność `total` Atlasu nie jest zmierzona
(pomiar 24), a ponowienia liczą się do zgody (ADR-0007 Z-9), więc wycena ich nie obejmuje.

**Nowe brzmienie Z-6:** zgoda dotyczy **liczby, którą operator zobaczył**. Werdykt `zgoda`
ustawia sufit `(wycena.zadan + wycena.zadan_juz) × proby`, gdzie `proby` pochodzi z bloku
`ponowienia` kontraktu — zapas jest po to, żeby sufit zatrzymywał rozjazd wyceny, a nie awarię
cudzego serwisu. Przekroczenie kończy przebieg jako `przerwany`, ze zdaniem wymieniającym obie
liczby; wznowienie liczy koszt od nowa i pyta jeszcze raz. Gdy kanał nie podał liczby, sufitu nie
ma — tabela mówi wtedy wprost „kanał nie podał liczby", pytanie jest pytaniem o przebieg masowy
z domyślnym „nie", więc zgoda pada świadomie na przebieg o nieznanym rozmiarze.

Sufit obowiązuje **tak samo na ścieżce flag**: `--zgoda` nie jest zgodą na dowolną liczbę żądań,
tylko na tę, którą policzyła wycena. Obserwator: `tests/test_pipeline.py`
`test_zgoda_pod_wycena_nie_zdejmuje_progu_na_caly_przebieg` (sprawdzony mutacją).

### 12.2 `Decyzja` jest trójwartościowa

Z-6 zapisało `Decyzja = Callable[[Wycena], bool]`; kod ma `Werdykt = Literal["zgoda",
"bez_zgody", "odmowa"]`, bo `bool` nie odróżniał „operator odmówił" od „obowiązuje próg jak przed
ADR-0008". Rozszerzenie jest świadome i zostaje — ten punkt je odnotowuje, żeby ADR i kod mówiły
to samo.

### 12.3 Znacznik 2 obejmuje cały arkusz `Metadane`, nie sam wiersz `tryb`

Z-3 wymienia sześć znaczników; wiersz `tryb` był prawdziwy, a dwa wiersze niżej ten sam arkusz
twierdził `organ = Krajowa Izba Odwoławcza` i powtarzał atrybucję licencyjną Atlasu nad korpusem,
którego nikt nie licencjonował. Znacznik 2 znaczy odtąd: **żaden wiersz arkusza eksportu
pokazowego nie przypisuje rekordów realnemu organowi ani realnemu dostawcy.** `organ` niesie
`exporter.ORGAN_POKAZU`, wiersze `atrybucja_*` — `ATRYBUCJA_POKAZU`.

### 12.4 Numer sprawy połączonej pochodzi z puli wolnych numerów

§6 pozwalało generatorowi dokleić `numer + 1`. Bez patrzenia na pulę druga sygnatura bywała
sygnaturą **główną** innego dokumentu — zmierzone 7 z 384 — więc pokaz uczył właściwości, której
rejestr nie ma (mina 4). Numer sprawy połączonej bierze się odtąd z numerów, których nikt nie ma
za sygnaturę główną; `tests/test_demo.py` sprawdza, że każda sygnatura występuje w korpusie raz.

---

## 13. Przyjęcie fazy 3 (2026-09-20)

Bramka §10 zamknięta w komplecie:

1–4. Cztery kryteria techniczne zielone testami (pkt 4 dostał obserwatora dopiero po przeglądzie
   kodu fazy 3 — `pobierz` z flag drukował tabelę kosztów, ale żaden test tego nie oglądał).
5. **Przejście operatora wykonane** przez właściciela na `kio-tool demo`; trzy zgłoszone usterki
   interfejsu naprawione przed przyjęciem — `docs/decisions.md`, „Przejście operatora — tryb
   pokazowy". Dwie z nich (podświetlenie listy, ciche pomijanie polskiego „tak") były już
   znalezione w `ceidg-tool` 2026-09-09; poprawki przeniesione razem z powodem.
6. **Właściciel przyjął fazę** 2026-09-20 razem z fazą 2.

Zakres przyjęcia nie obejmuje asystenta językowego: właściciel zdecydował tego samego dnia, że
fazy 2 i 3 domykamy bez niego, a asystent zostaje na liście świadomie odłożonych (O-6) za bramką
warunkową fazy 4.
