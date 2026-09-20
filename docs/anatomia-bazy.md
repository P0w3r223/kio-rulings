# Co dokładnie jest w bazie kio-tool

Data pomiaru: 2026-09-20
Status: migawka — liczby przeliczaj poleceniami z sekcji 7
Źródło: baza operatora, **zero żądań do sieci**; wersja odczytu 6

Plik: `%LOCALAPPDATA%\kio-tool\kio-tool\korpus.sqlite`, **70,2 MB**, jeden plik SQLite poza
repozytorium. Kopiuje się go przez skopiowanie tego pliku i niczego więcej.

---

## 1. Dziewięć tabel w trzech warstwach

Podział bazy nie jest podziałem po temacie, tylko po **trwałości**: co przyszło z sieci i nie ma
prawa się zmienić, co z tego wyliczył parser, i co pamięta przebieg.

### Warstwa pierwsza — to, co przyszło (nie przelicza się nigdy)

| Tabela | Wierszy | Co trzyma |
|---|---|---|
| `documents` | 443 | Tożsamość dokumentu: `doc_id`, kanał, odnośnik u źródła, sygnatury, data wydania, skrót bieżącej wersji |
| `raw_versions` | 443 | **Surowa treść** i jej `content_sha256`; 19,8 MB bajtów. Ta sama sygnatura z inną treścią to nowy wiersz, nie nadpisanie |

`raw_versions` jest jedyną warstwą, z której nie da się niczego odtworzyć — reszta bazy powstaje
z niej i wolno ją skasować bez straty, byle zostało `przelicz`.

### Warstwa druga — to, co z tego wyczytał parser (odtwarzalna)

| Tabela | Wierszy | Co trzyma |
|---|---|---|
| `metadata` | 443 | Po jednym wierszu na dokument: sygnatura główna, daty, rodzaj, rozstrzygnięcie, przewodniczący, strony, koszty, długość treści |
| `sections` | 1 772 | Granice części orzeczenia w znakach (`char_start`, `char_end`) plus skrót każdej |
| `citations` | 1 708 | Odesłania do innych orzeczeń, z pozycją w tekście |
| `provisions` | 16 834 | Powołania na przepisy, z pozycją w tekście |
| `fts` | — | Indeks pełnotekstowy SQLite FTS5; to on odpowiada za `szukaj` |

Każdy wiersz tych tabel niesie `content_sha256` **i** `parse_version`. Stąd bierze się
odtwarzalność: `przelicz` czyta surowe wersje jeszcze raz i podmienia tę warstwę, a stara para
(treść, wersja odczytu) mówi wprost, czym poprzedni wynik został policzony. Dziś wszystkie
443 dokumenty stoją na **wersji odczytu 6** — rozjazd byłby widoczny w raporcie pokrycia.

### Warstwa trzecia — to, co pamięta przebieg

| Tabela | Wierszy | Co trzyma |
|---|---|---|
| `runs` | 19 | Przebieg: zakres, kryteria, status, ostatnia strona listy, odcisk kryteriów |
| `run_documents` | 443 | Który przebieg objął który dokument i na której pozycji |
| `requests_log` | 464 | Każde żądanie: czas, metoda, **adres z wyciętymi sekretami**, status, czas odpowiedzi, bajty, numer próby |

Ta warstwa jest powodem, dla którego przerwany przebieg wznawia się bez duplikatów: `runs`
pamięta, gdzie stanął, a `run_documents` — co już wzięto.

---

## 2. Co jest w korpusie: 443 orzeczenia

| Wymiar | Podział |
|---|---|
| Roczniki | 2010–2026; po ~6 dokumentów na rocznik z próbki stratyfikowanej plus 192 z rocznika 2023 i 160 z 2024 z pierwszego pełnego przebiegu |
| Rodzaj | **wyrok 225**, postanowienie 218 |
| Rozstrzygnięcie | umorzono 168 · oddalono 116 · uwzględnione 110 · inne 36 · odrzucono 13 |
| Długość treści | najkrótsze **2 348** znaków, średnio **30 475**, najdłuższe **355 527**; razem **13 500 253** znaki |

Rozkład rozstrzygnięć jest sam w sobie ustaleniem: **umorzeń jest więcej niż oddaleń**, co znaczy,
że najczęstszym zakończeniem sprawy przed Izbą nie jest przegrana odwołującego, tylko wycofanie
albo uwzględnienie zarzutów przez zamawiającego przed rozprawą.

## 3. Części orzeczenia: 4 × 443, bez wyjątku

| Część | W ilu dokumentach |
|---|---|
| `naglowek` | 443 |
| `sentencja` | 443 |
| `uzasadnienie` | 443 |
| `pouczenie` | 443 |

Cztery części w każdym dokumencie i **zero znaków nieprzypisanych** w całym korpusie. To nie jest
deklaracja: `sections` trzyma granice w znakach, więc raport pokrycia liczy dopełnienie i pokazuje
je rocznik po roczniku.

## 4. Wypełnienie pól, czyli czego w orzeczeniach po prostu nie ma

| Pole | Wypełnione | Udział |
|---|---|---|
| `przewodniczacy` | 403 z 443 | 91 % |
| `data_rozprawy` | 368 z 443 | 83 % |
| `koszty` | 336 z 443 | 76 % |

Puste pole zwykle nie jest błędem odczytu, tylko właściwością dokumentu: postanowienie o umorzeniu
bez rozprawy nie ma daty rozprawy ani rozstrzygnięcia o kosztach. Narzędzie zostawia pustkę
zamiast ją zgadywać.

## 5. Cytowania: 1 708 odesłań, ale nie w każdym orzeczeniu

- **194 z 443 dokumentów (44 %) powołuje się na inne orzeczenie.** Pozostałe **249 nie cytuje
  niczego** — i to jest normalny stan, nie brak odczytu.
- W dokumencie, który cytuje: średnio **8,8** odesłań, najwięcej **59**.
- Podział po organach: KIO 1 279 · sądy okręgowe 165 · Sąd Najwyższy 99 · Trybunał UE 60 ·
  KIO bez oznaczenia repertorium 29 · inne 26 · sądy apelacyjne 19 · WSA 12 · NSA 12 ·
  Zespół Arbitrów UZP 7.
- Wszystkie 1 708 pochodzą z **treści** orzeczenia (`zrodlo = tresc`); kanał nie dostarcza
  gotowej listy cytowań.

## 6. Przepisy: 16 834 powołań z dwóch źródeł

| Źródło | Wierszy | Co to znaczy |
|---|---|---|
| `tresc` | 13 697 | Wyczytane z tekstu orzeczenia przez parser |
| `kanal` | 3 137 | Lista podana przez sam kanał przy rekordzie |

Podział po akcie: Pzp 2019 — 7 849 · **nieustalone — 5 233 (31,1 %)** · Pzp 2004 — 2 529 ·
kodeks cywilny 591 · inne 554 · rozporządzenie 52 · kpc 26.

Dwa źródła są trzymane osobno celowo: lista z kanału jest cudzym odczytem i wolno jej się różnić
od tego, co stoi w tekście. Zlanie ich w jedną kolumnę odebrałoby możliwość porównania.

## 7. Ślad sieci: 464 żądania, wszystkie udane

| | |
|---|---|
| Przebiegów | 19, **wszystkie zakończone** (zero przerwanych) |
| Żądań łącznie | 464 |
| Statusów HTTP | **464 × 200** — ani jednego błędu, ani jednego ponowienia |
| Czas odpowiedzi | średnio 122 ms, najdłuższy 578 ms |
| Okno czasowe | wszystkie 19 przebiegów 2026-09-19, między 13:31 a 13:39 UTC |

To ostatnie jest też ograniczeniem, o którym trzeba mówić głośno: **awaryjności kanału nikt jeszcze
nie zmierzył**, bo nie było ani jednej awarii. Progi ponawiania w `contract.yaml` są decyzją
projektu, nie pomiarem — dlatego pomiar 24 stoi na liście otwartych.

---

## 8. Jak to przeliczyć samemu

```powershell
cd E:\GitHub\Kio
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe pokrycie --zloty tests\gold
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe runy --limit 20 --json
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe szukaj --fraza "rażąco niska cena" --json
```

Żadne z tych poleceń nie wysyła ani jednego żądania. `pokrycie` zapisuje przy okazji raport
`.md` i `.json` w `docs/raporty/`, więc liczby z tego pliku dają się odtworzyć co do sztuki.
