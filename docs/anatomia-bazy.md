# Co dokładnie jest w bazie kio-tool

Data pomiaru: 2026-09-23
Status: migawka — liczby przeliczaj poleceniami z sekcji 8
Źródło: baza operatora, **zero żądań do sieci**; wersja odczytu 6

Plik: `%LOCALAPPDATA%\kio-tool\kio-tool\korpus.sqlite`, **173,1 MB**, jeden plik SQLite poza
repozytorium. Kopiuje się go przez skopiowanie tego pliku i niczego więcej.

Poprzednia migawka (2026-09-20) stała na korpusie 443 dokumentów. Przebieg 5 z 2026-09-23
(próbka warstwowa po kwartałach, 1 122 żądania) podniósł korpus do **1 499** i to jest stan
opisany niżej; liczby sprzed przebiegu leżą w `decisions.md`.

---

## 0. Ile tego jest w całym zbiorze — i ile z tego mamy

Zanim o naszej bazie: **cały zbiór orzeczeń KIO u pośrednika liczy 29 606 dokumentów** (pomiar 28,
2026-09-23, 5 żądań). To nie jest szacunek ani liczba z cudzego streszczenia — kanał podaje ją
polem `total` w odpowiedzi listy. Odczyt z 2026-09-18 dał 29 580 i leży w
`tests/examples/atlas/lista_20260918T103525Z.json` ze skrótem SHA-256 zapisanym w kontrakcie
kanału (`source/atlas/contract.yaml`); różnica 26 na pięć dób to rząd wielkości dopływu.

| | |
|---|---|
| Cały zbiór kanału | **29 606** orzeczeń, roczniki 2010–2026 |
| W naszej bazie | **1 499**, czyli **5,1 %** |
| Stron listy po 100 rekordów | 297 |

### Rozkład po rocznikach (pomiar 26, 2026-09-20, 20 żądań)

| Rocznik | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 |
|---|---|---|---|---|---|---|---|
| Dokumentów | 0 | 0 | 0 | 180 | 537 | 662 | 547 |

| Rocznik | 2014 | 2015 | 2016 | 2017 | **2018** | 2019 | 2020 |
|---|---|---|---|---|---|---|---|
| Dokumentów | 481 | 1 089 | 884 | 1 006 | **271** | 1 530 | 2 273 |

| Rocznik | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| Dokumentów | 1 531 | 2 717 | 3 264 | 4 267 | 4 850 | 3 412 |

Trzy rzeczy z tego wynikają. **2007–2009 mają zero** — brak najstarszych roczników jest odtąd
zmierzony, a nie wywnioskowany. **Zbiór jest młody**: lata 2021–2025 to 16 629 dokumentów, czyli
56 % całości, a rocznik 2025 ma dwadzieścia siedem razy więcej niż 2010. **Rocznik 2018 jest
dziurawy** — 271 to nie chudy rok, tylko osiem miesięcy prawie bez dokumentów. Pomiar 27
(2026-09-23, 12 żądań, spis miesięczny) daje 43 w styczniu, **11 łącznie od lutego do września**
oraz 83, 86 i 48 w ostatnim kwartale; suma 271 domyka się do licznika rocznego. Izba nie milknie
na osiem miesięcy, więc to brak u pośrednika, nie właściwość orzecznictwa — podejrzenie
z pomiaru 26 jest odtąd ustaleniem. Dlaczego pośrednik tych miesięcy nie ma, pomiar nie mówi.
Przebieg 5 potwierdził tę dziurę drugą drogą: kanał zgłosił w kwartałach 2018 roku 52, 1, 1, 217.

Suma roczników to 29 501 wobec licznika 29 580 z tej samej doby — różnica 79, czyli 0,27 %.
Kandydaci: dwie doby dopływu między odczytami i dokumenty z błędną datą wydania, które wypadają poza
każdy filtr rocznikowy (pomiar 3a: błędna data w 9 rekordach na 100). Szczegóły w `decisions.md`,
„Pomiar 26".

### Co kosztowałoby pobranie całości

Współczynnik jest zmierzony, nie założony: Przebieg 5 przyniósł 1 055 nowych dokumentów za
1 122 żądania, czyli **1,06 żądania na dokument** (dokument plus jego udział w stronach listy).
Przebieg kwartalny płaci za więcej stron listy niż rocznikowy, więc ta liczba jest ostrożniejsza
od wcześniejszych 1,047.

| | |
|---|---|
| Żądań na cały zbiór | ok. **31 400** |
| Czysty czas przy odstępie 1 s | **8,7 godziny** |
| Przy naszym sufitcie 1 400/dobę | **22 doby** (22,4) |
| Przy 5 000/dobę, czyli **z kluczem API** | **6,3 doby** |

Wiążący jest **limit dobowy, nie odstęp między żądaniami** — i to jest cały praktyczny powód,
dla którego konto u dostawcy ma znaczenie: skraca pobranie całości z trzech tygodni do sześciu
dni. Pobranie można przerwać i wznowić, więc nie musi to być sześć dób ciągiem.

### Ile to zajmie na dysku (szacunek z próbki, nie pomiar)

Skala to 19,7×. Przy naszej średniej 34 503 znaki na orzeczenie:

| | |
|---|---|
| Znaków treści | ok. **1,0 mld** |
| Surowej treści | ok. **0,95 GB** |
| Pliku bazy z indeksem | ok. **3,4 GB** |

Te trzy liczby są **wyliczone z próbki**, a nie zmierzone, i tak mają być podawane. Poprzedni
szacunek (1,2 GB treści, 4,6 GB bazy) stał na korpusie ważonym dwoma najdłuższymi rocznikami;
próbka warstwowa po kwartałach przesunęła go w dół, bo mnożnik spadł z 66,8 na 19,7. Rząd
wielkości jest pewny, ±20 % nie jest.

### Czego o rejestrze **nie** wiemy

- **Ile orzeczeń publikuje sam Urząd Zamówień Publicznych.** 29 606 to zbiór **pośrednika**, a nie
  źródła. Różnicy między nimi nikt nie zmierzył — zrobiłby to pomiar 4b/16 (dwa żądania do
  wyszukiwarki UZP), który leży na liście otwartych.
- Jedyna liczba po stronie źródła jest **z drugiej ręki**: ~33 366 identyfikatorów w kwietniu
  2026 (Legal Data Hunter). Nie jest porównywalna wprost, bo w tej numeracji **KIO i sądy okręgowe
  dzielą jedną przestrzeń**, więc część z tych 33 tysięcy to nie orzeczenia Izby.
- **Roczniki 2007-12 – 2009 są poza kanałem w całości.** Izba orzeka od grudnia 2007, zbiór
  pośrednika zaczyna się w 2010.

Stąd bierze się zdanie, które powtarzamy: wiemy, **ile trzyma pośrednik**, i nie wiemy, **ile
publikuje urząd**. Pierwsze jest mianownikiem dla postępu pobierania; drugie byłoby mianownikiem
dla kompletności — i tego drugiego nie mamy.

---

## 1. Dziewięć tabel w trzech warstwach

Podział bazy nie jest podziałem po temacie, tylko po **trwałości**: co przyszło z sieci i nie ma
prawa się zmienić, co z tego wyliczył parser, i co pamięta przebieg.

### Warstwa pierwsza — to, co przyszło (nie przelicza się nigdy)

| Tabela | Wierszy | Co trzyma |
|---|---|---|
| `documents` | 1 499 | Tożsamość dokumentu: `doc_id`, kanał, odnośnik u źródła, sygnatury, data wydania, skrót bieżącej wersji |
| `raw_versions` | 1 499 | **Surowa treść** i jej `content_sha256`; 71,7 MB zapisanych bajtów, w tym 49,3 MB samego tekstu. Ta sama sygnatura z inną treścią to nowy wiersz, nie nadpisanie |

`raw_versions` jest jedyną warstwą, z której nie da się niczego odtworzyć — reszta bazy powstaje
z niej i wolno ją skasować bez straty, byle zostało `przelicz`.

### Warstwa druga — to, co z tego wyczytał parser (odtwarzalna)

| Tabela | Wierszy | Co trzyma |
|---|---|---|
| `metadata` | 1 499 | Po jednym wierszu na dokument: sygnatura główna, daty, rodzaj, rozstrzygnięcie, przewodniczący, strony, koszty, długość treści |
| `sections` | 5 989 | Granice części orzeczenia w znakach (`char_start`, `char_end`) plus skrót każdej |
| `citations` | 7 078 | Odesłania do innych orzeczeń, z pozycją w tekście |
| `provisions` | 64 760 | Powołania na przepisy, z pozycją w tekście |
| `fts` | — | Indeks pełnotekstowy SQLite FTS5; to on odpowiada za `szukaj` |

Każdy wiersz tych tabel niesie `content_sha256` **i** `parse_version`. Stąd bierze się
odtwarzalność: `przelicz` czyta surowe wersje jeszcze raz i podmienia tę warstwę, a stara para
(treść, wersja odczytu) mówi wprost, czym poprzedni wynik został policzony. Dziś wszystkie
1 499 dokumentów stoi na **wersji odczytu 6** — rozjazd byłby widoczny w raporcie pokrycia.

### Warstwa trzecia — to, co pamięta przebieg

| Tabela | Wierszy | Co trzyma |
|---|---|---|
| `runs` | 111 | Przebieg: zakres, kryteria, status, ostatnia strona listy, odcisk kryteriów |
| `run_documents` | 1 838 | Który przebieg objął który dokument i na której pozycji |
| `requests_log` | 1 616 | Każde żądanie: czas, metoda, **adres z wyciętymi sekretami**, status, czas odpowiedzi, bajty, numer próby |

`run_documents` ma więcej wierszy niż `documents`, bo ten sam dokument bywa objęty kilkoma
przebiegami — drugi raz już jako znany, nie nowy.

Ta warstwa jest powodem, dla którego przerwany przebieg wznawia się bez duplikatów: `runs`
pamięta, gdzie stanął, a `run_documents` — co już wzięto.

---

## 2. Co jest w korpusie: 1 499 orzeczeń z 29 606

| Wymiar | Podział |
|---|---|
| Roczniki | 2010–2026, każdy obecny: 2010 → 16, 2011 → 24, 2012 → 32, 2013 → 39, 2014 → 47, 2015 → 57, 2016 → 59, 2017 → 69, 2018 → 37, 2019 → 64, 2020 → 112, 2021 → 95, 2022 → 79, 2023 → 294, 2024 → 276, 2025 → 129, 2026 → 70 |
| Rodzaj | **wyrok 909**, postanowienie 590 |
| Rozstrzygnięcie | umorzono 498 · oddalono 484 · uwzględnione 407 · inne 73 · odrzucono 37 |
| Długość treści | najkrótsze **2 277** znaków, średnio **34 503**, najdłuższe **392 370**; razem **51 720 210** znaków |

Rozkład roczników nie jest losowy: do 2026-09-22 korpus stał na dwóch rocznikach (192 z 2023
i 160 z 2024), a Przebieg 5 dobrał próbkę warstwową z wagami malejącymi wstecz, żeby każdy
rocznik miał reprezentację. Dlatego 2023 i 2024 są nadal najliczniejsze, ale żaden rocznik nie
stoi na sześciu dokumentach.

Rozkład rozstrzygnięć jest sam w sobie ustaleniem: **umorzeń jest więcej niż oddaleń**, co znaczy,
że najczęstszym zakończeniem sprawy przed Izbą nie jest przegrana odwołującego, tylko wycofanie
albo uwzględnienie zarzutów przez zamawiającego przed rozprawą. W korpusie margines jest wąski
(498 do 484), ale pomiar 28 sprawdził to na **całym zbiorze pośrednika** i tam przewaga wynosi
osiem punktów procentowych: umorzono 11 509 (38,9 %) wobec oddalono 9 142 (30,9 %). Próbka
tłumiła tę różnicę, nie zawyżała jej.

## 3. Części orzeczenia: cztery rodzaje w 1 492 dokumentach z 1 499

| Część | W ilu dokumentach |
|---|---|
| `naglowek` | 1 499 |
| `sentencja` | 1 495 |
| `uzasadnienie` | 1 496 |
| `pouczenie` | 1 499 |

Komplet czterech części ma **1 492 dokumenty (99,5 %)**; siedmiu brakuje jednej — czterem
sentencji, trzem uzasadnienia. Na korpusie 443 dokumentów ten przypadek nie wystąpił ani razu
i dopiero potrojenie zbioru go pokazało.

**Znaków nieprzypisanych jest zero** w całym korpusie, teraz z 51,7 miliona zamiast z 13,5 mln.
To nie jest deklaracja: `sections` trzyma granice w znakach, więc raport pokrycia liczy
dopełnienie i pokazuje je rocznik po roczniku.

## 4. Wypełnienie pól, czyli czego w orzeczeniach po prostu nie ma

| Pole | Wypełnione | Udział |
|---|---|---|
| `przewodniczacy` | 1 410 z 1 499 | 94 % |
| `data_rozprawy` | 1 262 z 1 499 | 84 % |
| `koszty` | 1 128 z 1 499 | 75 % |

Puste pole zwykle nie jest błędem odczytu, tylko właściwością dokumentu: postanowienie o umorzeniu
bez rozprawy nie ma daty rozprawy ani rozstrzygnięcia o kosztach. Narzędzie zostawia pustkę
zamiast ją zgadywać.

## 5. Cytowania: 7 078 odesłań, ale nie w każdym orzeczeniu

- **719 z 1 499 dokumentów (48 %) powołuje się na inne orzeczenie.** Pozostałe **780 nie cytuje
  niczego** — i to jest normalny stan, nie brak odczytu.
- W dokumencie, który cytuje: średnio **9,8** odesłań, najwięcej **136**.
- Podział po organach: KIO 5 149 · sądy okręgowe 736 · Sąd Najwyższy 481 · Trybunał UE 221 ·
  inne 139 · KIO bez oznaczenia repertorium 121 · sądy apelacyjne 85 · NSA 65 · WSA 44 ·
  Zespół Arbitrów UZP 37.
- **Postaci kanonicznej nie udało się zbudować przy 104 odesłaniach (1,5 %)** — rozpoznanych jest
  98,5 %. Rodziny, które zostają nierozpoznane z powodem, opisuje pomiar 25 w `decisions.md`.
- Wszystkie 7 078 pochodzą z **treści** orzeczenia (`zrodlo = tresc`); kanał nie dostarcza
  gotowej listy cytowań.

## 6. Przepisy: 64 760 powołań z dwóch źródeł

| Źródło | Wierszy | Co to znaczy |
|---|---|---|
| `tresc` | 53 646 | Wyczytane z tekstu orzeczenia przez parser |
| `kanal` | 11 114 | Lista podana przez sam kanał przy rekordzie |

Podział po akcie w tym, co wyczytał parser z treści: Pzp 2019 — 17 844 · Pzp 2004 — 17 245 ·
**nieustalone — 14 175 (26,4 %)** · kodeks cywilny 2 044 · inne 1 993 · rozporządzenie 267 ·
kpc 78. Lista z kanału dzieli się na trzy pozycje: Pzp 2019 — 5 255 · Pzp 2004 — 4 307 ·
nieustalone 1 552.

Udział nieustalonych **spadł z 31,1 % na 26,4 %** po potrojeniu korpusu. Kierunek jest odwrotny
do intuicji „większy zbiór to więcej śmieci": stara wartość była zawyżona przez dwa roczniki,
które w niej dominowały.

Dwa źródła są trzymane osobno celowo: lista z kanału jest cudzym odczytem i wolno jej się różnić
od tego, co stoi w tekście. Zlanie ich w jedną kolumnę odebrałoby możliwość porównania.

## 7. Ślad sieci: 1 616 żądań, wszystkie udane

| | |
|---|---|
| Przebiegów | 111: **99 zakończonych, 12 przerwanych** |
| Żądań łącznie | 1 616 |
| Statusów HTTP | **1 616 × 200** — ani jednego błędu, ani jednego ponowienia |
| Czas odpowiedzi | średnio 292 ms, najdłuższy 11 469 ms |
| Okno czasowe | 2026-09-18T11:32Z – 2026-09-23T12:27Z; 356 żądań 18 września, 119 22 września, 1 141 23 września |

Dwanaście przebiegów przerwanych to nie awarie, tylko **wyceny**: pomiar 27 pytał o licznik
miesiąca poleceniem `pobierz --wycena`, które bierze jedną stronę listy i zatrzymuje przebieg
przed pobraniem czegokolwiek.

Doba 23 września zamknęła się na 1 141 żądaniach przy sufitcie **1 400/dobę** z `tempo.okna` —
264 pod limitem, przy zgodzie właściciela danej w tamtej sesji.

To wszystko jest też ograniczeniem, o którym trzeba mówić głośno: **awaryjności kanału nikt jeszcze
nie zmierzył**, bo nie było ani jednej awarii — także w przebiegu na 1 122 żądania. Progi
ponawiania w `contract.yaml` są decyzją projektu, nie pomiarem; dlatego pomiar 24 stoi na liście
otwartych.

---

## 8. Jak to przeliczyć samemu

```powershell
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe pokrycie --zloty tests\gold
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe runy --limit 20 --json
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe szukaj --fraza "rażąco niska cena" --json
```

Żadne z tych poleceń nie wysyła ani jednego żądania. `pokrycie` zapisuje przy okazji raport
`.md` i `.json` w `docs/raporty/`, więc liczby z tego pliku dają się odtworzyć co do sztuki.
