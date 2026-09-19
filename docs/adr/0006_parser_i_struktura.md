# ADR-0006: Faza 2 — parser nad tekstem z PDF-a, pochodzenie w tabelach pochodnych, raport pokrycia jako produkt

Data: 2026-09-19
Status: proposed — do przyjęcia albo odrzucenia przez właściciela; sekcja 9 wylicza, co czeka
Autor: P0w3r223
Related to: `docs/AUDYT_KIO_ORZECZENIA.md` (9 — bramka fazy 2; 5.1; 7; 8.2; 10 — pomiary 5 i 10; 11 — miny 1, 2, 4), `docs/ARCHITEKTURA_KIO_TOOL.md` (4.2, 4.4, 4.5, 4.8, 4.9; 6 — pomiary 18 i 22), `docs/adr/0001_tozsamosc_dokumentu.md`, `docs/adr/0005_bramka_per_kanal.md` (Z-3, Z-5), `docs/decisions.md` („Jakość pól Atlasu", „Przebieg 2", „Status pomiarów"), `kio_tool/parser/details.py`, `kio_tool/store.py`, `tests/test_bramki_faz.py`

---

## 1. Kontekst: co wie drzewo, a czego nie wie plan

Stan odczytany z plików 2026-09-19, zero żądań:

- `kio_tool/parser/` niesie **dwa pliki**: `__init__.py` i `details.py` (148 linii, czysty, nazwy pól
  wyłącznie z `MapaPol`, `PARSE_VERSION = 1`). Segmentacji, normalizacji cytowań i przepisów nie ma.
- `store.py` stoi w schemacie 3: `documents`, `raw_versions`, `runs`, `requests_log`,
  `run_documents`, `metadata` (klucz `(doc_id, content_sha256)`, kolumna `parse_version`) i `fts`
  (kopia treści bieżącej wersji, nie `content=`).
- `pipeline.przelicz` przelicza wersje z `parse_version` starszym niż `PARSE_VERSION`, w transakcji
  na dokument, **bez klienta HTTP** — reguła 20 (`--block-network`) pilnuje tego dziś, a nie dopiero
  w fazie 2. Połowa bramki fazy 2 („przeliczenie bez ani jednego żądania") jest więc już spełniona
  przez konstrukcję, nie do zdobycia.
- `tests/gold/` jest pusty (`.gitkeep`). `tests/examples/atlas/` niesie dwa złote pliki z pomiaru 3a.
- Korpus leży poza repozytorium (`config.default_db_path`, powód: nazwiska składu i protokolantów);
  plik `korpus.sqlite` istnieje na tej maszynie, 341 dokumentów (zmierzone 2026-09-18, „Przebieg 2").

I dwa ustalenia, które przestawiają plan z architektury 4.5.

### 1.1 Plan segmentacji opisuje inny materiał niż ten, który mamy

Architektura 4.5 każe `sections.py` segmentować **`ContentHtml` z UZP**: nagłówki HTML jako
kandydaci, wzorce `^WYROK$`, `^Uzasadnienie$`, `^orzeka:$`. Korpus pochodzi z Atlasu (ADR-0005 Z-3),
a treść jest w polu `full_text` — tekstem **wyekstrahowanym z PDF-a cudzym potokiem** (architektura
4.2 „dane sparsowane z PDF", słowa dostawcy).

Odczytane 2026-09-19 z `tests/examples/atlas/dokument_20260918T103526Z.json` (3 021 znaków, 0 żądań)
— cztery cechy tego materiału, każda z przykładem z tego jednego pliku:

| Cecha | Przykład z bajtów | Co psuje |
|---|---|---|
| Nagłówek rozstrzelony spacjami | `Uz as adnienie` | `^Uzasadnienie$` nie trafia; najważniejsza granica dokumentu przepada |
| Twarde łamanie wierszy w zdaniu | `naruszenie art. 89 ust.\n1pkt 2 ustawy` | wzorce zakotwiczone na końcu linii; numer artykułu skleja się z sąsiadem |
| Znak wysuwu strony | `\n\n\fuczestników postępowania` | granica strony w środku zdania; `\f` zostaje w treści i w indeksie |
| Brak spacji po dwukropku | `Przewodniczący:Emilia Garbala` | heurystyka „nagłówek fałszywy: `Protokolant:` i nazwisko pod nim" z architektury 4.5 |

Kotwice struktury **są** w tym tekście, ale w postaci wplecionej w akapit, nie jako osobne nagłówki:
`Sygn. akt:` (pierwsza linia), `POSTANOWIENIE`, `z dnia 16 czerwca 2020 r.`, `postanawia:`,
`Stosownie do art. 198a i 198b … przysługuje skarga` (pouczenie), `O kosztach postępowania orzeczono`,
`Przewodniczący:` (podpis, dwa razy). To jest materiał do segmentacji **regułowej nad tekstem
znormalizowanym**, nie nad znacznikami HTML — i lista kotwic ma pochodzić z pomiaru, nie z tej tabeli:
jeden dokument z 2020 r. to nie próbka, dokładnie tak samo jak jeden PDF z 2023 r. w audycie 5.1.

Ten sam plik niesie drugi dowód, tym razem do przepisów: treść powołuje `ustawy z dnia 29 stycznia
2004 r. Prawo zamówień publicznych (t.j. Dz. U. z 2019 poz. 1843 ze zm.)`, a `law_articles` od Atlasu
podaje `["art. 186 ust. 2 Pzp", "art. 186 ust. 6 pkt 1 Pzp"]` — **bez wskazania ustawy**. Korpus
sięga rocznika 2010 (pomiar 3a) i dalej, więc obejmuje obie ustawy Pzp: z 2004 r. i z 2019 r.
(obowiązuje od 2021-01-01). „art. 186 ust. 2 Pzp" w orzeczeniu z 2020 r. i w orzeczeniu z 2024 r.
to **dwa różne przepisy**. Filtr `--przepis` bez wymiaru ustawy jest więc miną 2 audytu w czystej
postaci: kryterium poprawne, wynik cicho mieszający dwa reżimy.

### 1.2 Bramka mówi „z rozbiciem na roczniki", a korpus ma dwa miesiące

Bramka fazy 2 (audyt 9): przeliczenie całego korpusu bez żądania **i raport pokrycia z rozbiciem na
roczniki**, przy czym „ten raport jest ważniejszy niż sam parser: pokazuje, gdzie materiał jest
niejednorodny".

Korpus to styczeń 2024 (295) i 1–5 lutego 2024 (46) — zmierzone 2026-09-18. Roczniki z sygnatur to
`23` i `24` (w styczniu weszły m.in. KIO 3814/23 i KIO 115/24). Raport rocznikowy nad tym korpusem
pokaże dwa wiersze z jednego rocznika kalendarzowego i **nie odpowie na pytanie, dla którego
powstał**. Materiał niejednorodny jest tam, gdzie zmieniał się potok redakcji i ekstrakcji: 2007–2010
(początki Izby, formaty Worda), przełom ustaw 2020/2021, roczniki bieżące.

Wniosek, który ten ADR wyciąga wprost: **faza 2 zawiera pobranie próbki rocznikowej** — i to jest
pomiar 5 w brzmieniu, które status pomiarów już mu nadaje („próbka ~50 dokumentów", „próbka staje
się zalążkiem `tests/gold/`"). Bez niej bramka domknie się formalnie i nie domknie się w rzeczy.

---

## 2. Co ten ADR rozstrzyga

| # | Pozycja | Rozstrzygnięcie | Powód |
|---|---|---|---|
| **Z-1** | Przedmiot parsera fazy 2 | Parser segmentuje **tekst wyekstrahowany z PDF-a** (`full_text` kanału `atlas`), nie HTML. Reguła 18 (`Details`/`ContentHtml`) zostaje kontraktem kanału `uzp` i wraca razem z nim | Korpus jest atlasowy (ADR-0005 Z-3); cztery cechy materiału z 1.1 |
| **Z-2** | Kolejność: pomiar przed kodem | `sections.py` powstaje **po** pomiarze 5 (kotwice i kształt tekstu, z próbką rocznikową); `cite.py` przed pomiarem 22, który jest jego pomiarem odbiorczym; pomiar 10 (anonimizacja) na korpusie, 0 żądań | Doktryna 7.1: lista kotwic wpisana z jednego dokumentu jest „wiadomo, że", nie pomiarem |
| **Z-3** | Próbka rocznikowa | Faza 2 pobiera **stratyfikowaną próbkę po rocznikach** (proponowane: 6 dokumentów × rocznik 2010–2026, ~17 stron listy + ~102 dokumenty ≈ **119 żądań**), kanałem `atlas`, **za zgodą właściciela w sesji**. Stratyfikacja idzie oknem dat, a rocznik **weryfikuje się z sygnatury po pobraniu** i rozjazd jest liczony | Bez roczników raport z bramki nie mierzy niejednorodności (1.2). Rozjazd `ruling_date` ↔ sygnatura jest przy okazji drugim pomiarem defektu znanego z 9 na 295 |
| **Z-4** | Model danych | Schemat **4**: `sections`, `citations`, `provisions` — wszystkie kluczowane `(doc_id, content_sha256)` z kolumną `parse_version`, migracja 3 → 4 **dopisaniem** (jak 1 → 2 → 3). `metadata` bez zmian | Architektura 4.4 nazywa te tabele; klucz parą jest już niezmiennikiem magazynu |
| **Z-5** | Sekcje trzymają **offsety**, nie kopię tekstu | `sections(… ordinal, kind, char_start, char_end, sha256_fragmentu)`; tekst sekcji wycina się z `raw_versions` przy odczycie | Cytat w eksporcie i w fazie 4 ma dać się sprawdzić przy źródle (architektura 4.9, 4.10). Tekst przepisany po czyszczeniu byłby napisem, którego u dostawcy nie ma — a korpus rośnie o drugą kopię 3,5 MB (dziś) i ~300 MB (przy 29 580) |
| **Z-6** | `clean.py` nie produkuje treści, produkuje **widok** | `clean` zwraca tekst znormalizowany **razem z mapą offsetów** do tekstu oryginalnego; wszystko, co trafia do bazy, jest offsetem w oryginale | To samo zdanie co Z-5, po stronie modułu: „nie zmienia treści, zmienia szum" (architektura 4.5) ma mieć postać strukturalną, a nie obietnicę |
| **Z-7** | Pochodzenie w tabelach pochodnych | `provisions` i `citations` niosą kolumnę `zrodlo` z zamkniętej listy `kanal \| tresc`. `metadata.przepisy` zostaje tym, czym jest — listą **od Atlasu**; nasza ekstrakcja nie nadpisuje jej nigdy | Reguła 19 (ADR-0005 Z-5) w wydaniu fazy 2: `law_articles` jest opracowaniem pośrednika o znanym pochodzeniu, nasza ekstrakcja jest odczytem z treści. Ich **niezgodność jest informacją** — i najtańszym niezależnym sprawdzianem cudzego potoku, jaki mamy bez żądań |
| **Z-8** | Przepis nosi ustawę | `provisions` ma kolumnę `akt` (np. `pzp2004`, `pzp2019`, `rozporzadzenie`, `inne`, `nieustalone`), wypełnianą z treści, a przy jej braku pozostającą `nieustalone` — **nigdy zgadywaną z daty** | Dwa reżimy Pzp w jednym korpusie (1.1). Zgadywanie z daty byłoby dopisaniem informacji, której w zdaniu nie ma — a data w tym kanale bywa błędna |
| **Z-9** | `parser/provisions.py` jako osobny moduł | Przepisy dostają własny moduł obok `cite.py` (cytowania orzeczeń) | Inna gramatyka, inny cel, inna tabela; architektura 4.2 wymienia cztery moduły parsera i dostaje piąty — zmiana dokumentu, nie wyjątek |
| **Z-10** | Wersja odczytu: jedna | `PARSE_VERSION` zostaje **jedną liczbą dla całego pakietu** `parser/`; każda tabela pochodna zapisuje, która wersja ją wyprodukowała. Podział na wersje per artefakt ma **wyzwalacz mierzony**: pełne przeliczenie dłuższe niż 10 minut na maszynie operatora | Policzone (nie zmierzone) z mediany 10 376 znaków × 341 dokumentów ≈ 3,5 MB — przeliczenie regułowe idzie w sekundach; trzy osie wersji kosztowałyby trzy zapytania w `versions_to_index` i trzy pętle w `przelicz` |
| **Z-11** | Złoty zbiór bez treści | `tests/gold/<doc_id>.json` niesie `content_sha256` dokumentu, granice sekcji jako offsety, SHA-256 każdego fragmentu, oczekiwane sygnatury i przepisy, datę i autora przeglądu — **nie niesie tekstu**. Tekst bierze się z korpusu operatora; jego brak **przerywa testy złotego zbioru głośno**, z liczbą „0 z N sprawdzonych", nigdy przez cichy `skip` | 50 orzeczeń w repozytorium to 50 dokumentów z nazwiskami składu i protokolantów w nieodwracalnej historii gita (`config.default_db_path`, `README`, `ZRODLO.md`). Redakcja odpada: doktryna 7.4 — sanityzacja zabiłaby dokładnie te cechy, które mierzymy (`Przewodniczący:Emilia Garbala` **jest** przypadkiem testowym) |
| **Z-12** | Raport pokrycia jest artefaktem, nie ekranem | Nowy moduł `kio_tool/pokrycie.py` (czyta `store`, nie zna `source`) i polecenie `pokrycie`; produkt: `docs/raporty/pokrycie_<data>.md` + plik maszynowy obok. Raport podaje **liczby bezwzględne przy każdym procencie**, datę, kanał, `parse_version`, liczbę dokumentów w korpusie i rozbicie po **roczniku z sygnatury**, skrzyżowane z rokiem z `ruling_date` | Audyt 9: raport jest ważniejszy niż parser. Doktryna 7.1: procent bez licznika i mianownika jest w tym projekcie błędem. Rozbicie po sygnaturze, a nie po `ruling_date`, bo to drugie jest polem znanym jako wadliwe (9 na 295) |
| **Z-13** | Słownik przepisów poza fazą 2 | `dictionaries.py` **nie powstaje** w fazie 2. Normalizacja przepisów jest gramatyką, nie sprawdzeniem wobec listy. Raport podaje **słownictwo zaobserwowane** (postać → liczba wystąpień) jako pomiar, nigdy jako autorytet odrzucający formy. Pomiar 18 wraca z własną decyzją, gdy pojawi się odbiorca autorytetu | Mina 4: słownik pisany ręcznie albo przez model przechodzi wszystkie testy i cicho gubi formy. Pomiar 18 kosztuje 2 żądania do UZP i zgodę — a dopóki nic nie waliduje, płaci się za odpowiedź, której nikt nie użyje (ten sam zarzut co ADR-0005 Z-1 wobec pomiarów 2a/4b) |
| **Z-14** | Bramka „kod po decyzji" | `tests/test_bramki_faz.py`: nowy wiersz `kio_tool/parser/sections.py` → **ADR-0006**; `NUMERY_ADR_OCZEKIWANE` zna `0006` | Trzy bramki tej tablicy mają ten sam kształt; czwarta nie jest wyjątkiem |
| **Z-15** | Bez nowej reguły granic | Faza 2 **nie dopisuje** reguły 24. Pochodzenie pilnuje kolumna `zrodlo` i test magazynu, offsety — test złotego zbioru | ADR-0005 §1 opisał pętlę „reguła → strażnik pusty → samosprawdzenie → metatest"; reguła bez własnego kształtu skanu byłaby jej kolejnym obrotem. Reguła 19 już mówi to, co trzeba, i ma dwóch strażników |

---

## 3. Warianty rozważone i ich cena

Każdy wariant był realny; odrzucone są tu z powodem, a nie pominięte.

### 3.1 Gdzie mieszka struktura pochodna

| Wariant | Za | Przeciw | Nakład / ryzyko |
|---|---|---|---|
| **A. Tabele `sections`/`citations`/`provisions` (wybrany)** | zgodny z architekturą 4.4; zapytania raportu to `GROUP BY`, nie skan JSON-a; `citations.resolved_signature` da się związać z korpusem | migracja schematu, trzy nowe zapisy w `przelicz` | M / niskie — migracja jest dopisaniem, wzorzec 1→2→3 sprawdzony |
| B. Jedna kolumna JSON w `metadata` | zero migracji poza kolumną | raport pokrycia — produkt bramki — liczyłby się w Pythonie po rozpakowaniu 341 (docelowo 29 580) JSON-ów; graf cytowań bez tabeli nie istnieje; droga do FTS nad sekcjami zamknięta | S / średnie |
| C. Bez zapisu, liczone na żądanie | parser pozostaje jedynym źródłem prawdy | każdy raport przelicza korpus od nowa; nie da się wykryć, że tabela pochodzi ze starszej wersji odczytu, bo tabeli nie ma | S / średnie |

Własność wariantu C zostaje mimo wyboru A i jest zapisana jako niezmiennik: **tabele pochodne są
pamięcią podręczną, nigdy źródłem prawdy** — kasowalne i odtwarzalne z `raw_versions` poleceniem
`przelicz --wszystko`, bez żądania.

### 3.2 Jak segmentować

| Wariant | Za | Przeciw | Nakład / ryzyko |
|---|---|---|---|
| A. Wzorce nagłówków wprost z architektury 4.5 | gotowa lista | napisana dla HTML-a z UZP; na `Uz as adnienie` i kotwicach wplecionych w akapit produkuje korpus w całości `nieprzypisany` — i robi to **cicho**, bo brak sekcji nie jest wyjątkiem | S / **wysokie** |
| **B. `clean` → widok znormalizowany → kotwice z pomiaru → offsety w oryginale (wybrany)** | odporne na rozstrzelenie, twarde łamanie i `\f`; każdy fragment zostaje weryfikowalny przy źródle; tekst niedopasowany ląduje w `nieprzypisane` **i jest policzony w znakach** | mapa offsetów to realna robota; kotwice trzeba najpierw zmierzyć | M / średnie |
| C. Analiza układu (Docling, modele DocLayNet) | odporna na PDF-y skanowane | audyt 5.1: materiał jest cyfrowy, nie skanowany; model w `parser/` łamie regułę 1 i czystość pakietu | L / wysokie |

Miejsce kotwic: **stałe modułowe w `sections.py`, z datą i liczbą wystąpień przy każdej**, nie
`contract.yaml`. Reguła 22 mówi o adresach i nazwach pól **dostawcy** — kotwice sekcji są własnością
polskiego orzeczenia, nie kanału, a `parser/` musi zostać czysty (reguła 1: bez `os`, bez wejścia-wyjścia).

### 3.3 Złoty zbiór

| Wariant | Za | Przeciw |
|---|---|---|
| A. 50 orzeczeń w repozytorium | test działa wszędzie i zawsze | nieodwracalna historia gita z nazwiskami składu i protokolantów; wprost wbrew `config.default_db_path` i `README` |
| **B. Adnotacje bez treści + SHA-256 fragmentów (wybrany)** | zero tekstu w repozytorium; adnotacja sprawdzalna wobec dowolnej kopii korpusu; manipulacja widoczna | bez korpusu nie ma sieci ochronnej — i to musi być **głośne**, nie ciche (Z-11) |
| C. Dokumenty syntetyczne | brak danych osobowych | mina 4: materiał odniesienia z pamięci przechodzi wszystkie bramki. Dopuszczalny wyłącznie jako jednostkowa atrapa konkretnej pułapki, nigdy jako mianownik pokrycia |

### 3.4 Próbka rocznikowa (pomiar 5)

| Wariant | Żądania | Za | Przeciw |
|---|---|---|---|
| **A. 6 dokumentów × 17 roczników (wybrany)** | ~119 | raport bramki mierzy wreszcie niejednorodność; próbka jest zalążkiem złotego zbioru; drugi pomiar rozjazdu dat | wymaga zgody w sesji; ~2 minuty przy odstępie 1 s |
| B. Bez próbki, raport na 341 dokumentach ze stycznia i lutego 2024 | 0 | zero kosztu i zero zgody | bramka domyka się formalnie; zdanie „materiał jest jednorodny" byłoby wnioskiem z dwóch miesięcy o osiemnastu latach |
| C. Pełne roczniki 2010–2026 | ~30 000 | korpus docelowy | to nie jest pomiar, to decyzja o pobraniu całości — należy do właściciela i do osobnego ADR-a (ADR-0005 §5) |

### 3.5 FTS5 — zostaje nad całą treścią

Architektura 4.8 przewiduje indeks nad `sections.text`. W fazie 2 **nie ruszamy indeksu**: dziś
działa nad treścią bieżącej wersji, ma przebieg 1 jako dowód (295 zaindeksowanych, 11 trafień),
a przejście na sekcje zmienia semantykę wyniku (fraza przecinająca granicę sekcji przestaje trafiać).
Wyzwalacz zmiany jest nazwany: **zestaw zapytań operatora z `tests/queries/`**, czyli miara fazy 3
(ADR-0005 Z-9). Decyzja bez tej miary byłaby wyborem bez kryterium.

---

## 4. Kolejność prac — sześć etapów, z kosztem w żądaniach

Każdy wynik trafia do `docs/decisions.md` w formacie tego pliku („Policzone {data} z bazy, 0 żądań"
albo „Zmierzone {data}, N żądań").

| # | Etap | Żądania | Produkt | Nakład |
|---|---|---|---|---|
| I | **Pomiar 5, część lokalna**: kształt tekstu na 341 dokumentach — udział `\f`, wierszy łamanych w zdaniu, nagłówków rozstrzelonych, sklejeń po dwukropku, rozkład długości, dokumenty z pustą treścią; inwentarz kotwic z liczbą wystąpień | 0 | wpis w `decisions.md`; **lista kotwic** dla etapu III | S |
| II | **Pomiar 5, część rocznikowa** (Z-3): próbka stratyfikowana 2010–2026, ta sama analiza per rocznik, rozjazd rocznika z sygnatury wobec `ruling_date` | ~119, **zgoda w sesji** | wpis w `decisions.md`; korpus z rozpiętością lat; zalążek złotego zbioru | S |
| III | `parser/clean.py` + `parser/sections.py` (czyste, kotwice z etapów I–II z datą i liczbą wystąpień przy każdej) | 0 | segmentacja z offsetami, `nieprzypisane` liczone w znakach | M |
| IV | `parser/cite.py` + `parser/provisions.py`; **pomiar 22** (gęstość cytowań, udział nieznormalizowanych, postaci sygnatur) i zestawienie `provisions(zrodlo='tresc')` z `law_articles` Atlasu | 0 | dwa wpisy w `decisions.md`; nowy zbiór testowy dla `docid.normalize_signature` | M |
| V | `store.py` → schemat 4 (migracja dopisaniem), `pipeline.przelicz` zapisuje sekcje, cytowania i przepisy w tej samej transakcji co metadane | 0 | korpus przeliczalny w całości | M |
| VI | `kio_tool/pokrycie.py` + polecenie `pokrycie`; **pomiar 10** (anonimizacja, wyłącznie liczby); złoty zbiór (Z-11) na próbce z etapu II, przejrzany okiem | 0 | `docs/raporty/pokrycie_<data>.md` — artefakt bramki | M |

Etapy I i II są wejściem etapu III i to jest cała treść Z-2: kotwice wpisane przed pomiarem byłyby
wzorcami wyprowadzonymi z jednego dokumentu z 2020 roku.

---

## 5. Konsekwencje w drzewie

- **Nowe pliki**: `kio_tool/parser/{clean,sections,cite,provisions}.py`, `kio_tool/pokrycie.py`,
  `tests/test_parser_{clean,sections,cite,provisions}.py`, `tests/test_pokrycie.py`,
  `tests/test_gold.py`, `tests/gold/*.json`, `docs/raporty/`.
- **Zmiany**: `store.py` (schemat 4 + `_migruj_do_4`), `pipeline.py` (`przelicz` zapisuje trzy tabele;
  `PARSE_VERSION` podniesiony), `cli.py` + `ui/texts.py` + `ui/render.py` (polecenie `pokrycie`),
  `docid.py` (rocznik z sygnatury jako funkcja jedynego producenta tożsamości — dwucyfrowy, **bez**
  rozwijania do czterech cyfr, zgodnie z nagłówkiem tego modułu).
- **Strażnicy**: `tests/test_bramki_faz.py` — wiersz `parser/sections.py` → ADR-0006 i `0006`
  w `NUMERY_ADR_OCZEKIWANE`; `tests/test_boundaries.py` — bez zmian w tablicy `REGULY` (reguła 1
  obejmuje `parser/` rekursywnie, więc nowe moduły wchodzą pod skan **bez dopisywania ich gdziekolwiek**;
  `pokrycie.py` wchodzi pod reguły 4, 5 i 8 jako zwykły moduł pakietu).
- **Dokumenty**: architektura 4.2 (piąty moduł parsera, `pokrycie.py` w mapie), 4.4 (`sections`
  z offsetami zamiast tekstu; `provisions` z `zrodlo` i `akt`), 4.5 (przedmiot: tekst z PDF-a; złoty
  zbiór bez treści), 6 (status pomiarów 5, 10, 18, 22); `decisions.md` — wyniki i statusy; `CLAUDE.md`
  — sekcja „Nie istnieje" traci `parser/{sections,clean,cite}.py`, zatrzymuje `dictionaries.py`.
- **Bez zmian**: `exporter.py` i jego cztery formaty (atrybucja i testy `tests/test_attribution.py`
  zostają nietknięte), `fts`, `source/`, `mcp_server.py`, `tests/queries/`, kreator `ui/`.

---

## 6. Cena, wypisana wprost

1. **Schemat 4 to czwarta migracja.** Każda jest dopisaniem, ale każda dokłada gałąź w `_migruj`
   i wiersz w testach magazynu. Alternatywa (jedna kolumna JSON) kosztowałaby raport bramki.
2. **~119 żądań do cudzego serwisu** za próbkę rocznikową, ze zgodą właściciela w tej sesji, w której
   padnie. Bez nich raport bramki jest raportem o dwóch miesiącach.
3. **Złoty zbiór bez tekstu nie jest przenośny.** Na maszynie bez korpusu testy sekcji nie mają na
   czym pracować i mówią to głośno. To jest świadomy wybór prywatności nad wygodą — i on **zwiększa**
   wagę decyzji C z 2026-09-17 (brak zdalnego): utrata dysku to utrata korpusu, a wtedy adnotacje
   złotego zbioru stają się zapisem o dokumentach, których nikt już nie ma.
4. **Pełne przeliczenie po każdej zmianie parsera** — jedna wersja odczytu na pakiet. Dziś sekundy,
   przy 29 580 dokumentach minuty; podział wersji ma wyzwalacz mierzony (Z-10), nie przeczucie.
5. **Raport pokrycia będzie pokazywał brzydkie liczby** i to jest jego funkcja. Nie ma progu
   zdawalności w kodzie: fazę przyjmuje właściciel, nie zielony test (audyt 9). Próg wpisany do testu
   byłby liczbą bez pomiaru i zamieniłby raport w bramkę samozatwierdzającą.

---

## 7. Ryzyka i ich obserwatorzy

| Ryzyko | Kto zapali czerwone światło |
|---|---|
| Segmentacja cicho odkłada cały tekst do `nieprzypisane` | raport: udział znaków `nieprzypisanych` per rocznik, liczba dokumentów bez sekcji `sentencja` i bez `uzasadnienie` |
| Adnotacja złotego zbioru rozjeżdża się z tekstem | SHA-256 fragmentu przy każdej granicy; niezgodność jest błędem testu, nie ostrzeżeniem |
| Brak korpusu zamienia testy złotego zbioru w ciszę | test mówi „0 z N sprawdzonych" i **nie przechodzi**; `skip` jest tu zakazany (doktryna 7.3) |
| Nasza ekstrakcja przepisów gubi formy, których Atlas nie gubi (albo odwrotnie) | zestawienie `zrodlo='tresc'` ↔ `zrodlo='kanal'` w raporcie: zawieranie w obie strony, liczby bezwzględne |
| Dwa reżimy Pzp zlewają się w filtrze `--przepis` | kolumna `akt`; raport liczy dokumenty z `akt = 'nieustalone'` |
| Dane osobowe wyciekają przez raport albo pomiar 10 | raport i pomiar publikują **wyłącznie liczby i `doc_id`**; żadnych fragmentów treści — pozycja listy kontrolnej przeglądu kodu |

---

## 8. Czego ten ADR nie rozstrzyga

- **Czy pobrać cały zbiór** (29 580 dokumentów) — ADR-0005 §5 zostawia to właścicielowi; próbka
  rocznikowa z Z-3 jest pomiarem, nie zaczątkiem pobrania całości.
- **Kanałów `uzp` i `saos`** — reguła 18 czeka na adapter UZP, odcinek 2007–2018 ma dostać własny ADR.
- **Pomiaru 18 i `dictionaries.py`** — wracają z odbiorcą autorytetu (Z-13).
- **Przejścia FTS na sekcje** — faza 3, po zestawie zapytań operatora (3.5).
- **Fazy 4** — bramka `mcp_server.py` → ADR-0002 stoi nietknięta; `citations` z offsetami jest dla
  niej przygotowaniem, nie wejściem.
- **Czy złoty zbiór w postaci adnotacji wystarcza jako „50 dokumentów z potwierdzonymi sekcjami"
  z architektury 4.5** — liczbę N ustala właściciel przy przyjęciu; ADR rozstrzyga **postać**, nie
  rozmiar.

---

## 9. Kryterium wyjścia z bramki fazy 2

Bramka jest domknięta, gdy jednocześnie:

1. `kio-tool przelicz --wszystko` przelicza **cały korpus bez ani jednego żądania** — mierzone testem
   z `--block-network`, nie deklaracją (reguła 20);
2. istnieje `docs/raporty/pokrycie_<data>.md` z rozbiciem po roczniku z sygnatury, skrzyżowanym
   z rokiem z `ruling_date`, i **każdy procent stoi tam obok liczb bezwzględnych**;
3. korpus obejmuje więcej niż jeden rocznik — próbka z Z-3 pobrana, jej wynik w `decisions.md`;
4. pomiary 5, 10 i 22 mają wpis w `decisions.md` z datą i liczbą żądań, a ich status w sekcji „Status
   pomiarów" nie brzmi już „niewykonany";
5. złoty zbiór istnieje w postaci z Z-11, jego adnotacje przechodzą wobec korpusu, a raport podaje,
   ile dokumentów złotego zbioru sprawdzono;
6. właściciel przyjmuje fazę — bo fazę kończy przyjęcie, nie zielona suita (audyt 9).
