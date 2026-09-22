# Prezentacja kio-tool — plan i materiał liczbowy

Data: 2026-09-20
Status: **wykonany** — `prezentacja-kio-ekran.html`, 17 slajdów; przebudowana 2026-09-20 po przeglądzie właściciela (sekcja 2a), a potem rozszerzona o czym jest KIO, rozkład roczników i wniosek o gotowości pod agenta
Autor: właściciel
Dotyczy: `prezentacja-ceidg-ekran.html` jako wzorzec formy

---

## 0. Cztery decyzje, które zamykają kształt (2026-09-20)

| Pytanie | Rozstrzygnięcie | Co z tego wynika dla slajdów |
|---|---|---|
| Odbiorca | **Zarząd, ten sam rejestr co w `ceidg`** | Zero żargonu; każda liczba z pochodzeniem; slajd o zabezpieczeniach i slajd „czego to nie zrobi" są obowiązkowe, bo o to pytają pierwsi |
| Liczba wersji | **Sama ekranowa 16:9** | Jeden samowystarczalny plik HTML; rolę dokumentu do czytania pełni ten plik, więc slajd 1 nie odsyła do drugiej wersji |
| Ekrany narzędzia | **Makiety HTML z danymi z trybu pokazowego** | Kreator i wynik wyszukiwania rysowane w HTML wewnątrz prezentacji; zero obrazów rastrowych, zero ryzyka, że w zrzucie zostanie nazwisko; stopka mówi wprost, że dane w makiecie są syntetyczne |
| Pozycjonowanie | **Samo `kio-tool`** | Prezentacja stoi sama i niczego nie zakłada o znajomości `ceidg-tool`; wspólny rodowód widać w formie, nie w treści |

Dwie decyzje z tej samej rozmowy zmieniają treść slajdów 12 i 15: właściciel **potwierdził
przegląd cytowań i przepisów** (O-4 zamknięte w całości), a rozbicie `store.py` i `pipeline.py`
miało zostać świadomym, zmierzonym długiem (O-5). **2026-09-22 właściciel zmienił tę decyzję:**
oba pliki rozbite na pakiety (ADR-0009), slajd „Granice" mówi o tym w czasie przeszłym.

---

## 1. Po co ten plik istnieje przed prezentacją

Prezentacja `ceidg-tool` trzyma się jednej zasady i to ona daje jej wagę: **każdy slajd niesie
jedno twierdzenie, a w stopce źródło i datę pomiaru**. Zasada jest łatwa do złamania w chwili
składania slajdów, kiedy brakuje jednej liczby i kusi, żeby ją oszacować. Ten plik zbiera liczby
**przed** składaniem, razem z ich pochodzeniem, żeby slajd nie musiał niczego dopowiadać.

Druga zasada, tym razem tylko dla tego projektu i ważniejsza od pierwszej: **na slajdzie nie ma
ani jednego zdania orzeczenia i ani jednego nazwiska**. Pomiar 10 (2026-09-19, 443 dokumenty)
ustalił, że skład orzekający i protokolant **nie są anonimizowani** u pośrednika — 404 dokumenty
z imieniem i nazwiskiem przewodniczącego, 286 z protokolantem. Zrzuty ekranu robimy więc
**wyłącznie z trybu pokazowego** (`kio-tool demo`), który generuje korpus syntetyczny w pamięci
procesu; korpus operatora nie pojawia się na ekranie rzutnika w żadnej postaci.

---

## 2a. Przebudowa po przeglądzie właściciela (2026-09-20)

Pierwsza wersja miała 17 slajdów w układzie wzorca i **została odrzucona przez właściciela
w całości co do treści**, przy zachowanej formie. Powód jest jedną informacją, której w tym
planie brakowało: **sala już widziała prezentację `ceidg-tool`**. W tym stanie wierne odtworzenie
tamtego układu daje nie „spójną serię", tylko powtórkę — slajd o zabezpieczeniach, o koszcie
przed zgodą, o rządowej wyszukiwarce i o danych osobowych mówiły sali to, co usłyszała
14 września.

Nowy układ ma **12 slajdów** i inny kręgosłup: nie „co to narzędzie potrafi", tylko **czym się
różni od tego, które już znacie**.

| Co zrobiono | Z czym |
|---|---|
| **Zwinięte do jednego slajdu** (s10) | Zabezpieczenia, zgoda po wycenie, neutralizacja cudzego tekstu, tryb pokazowy — trzy wiersze „bez zmian" i dwa z wykrzyknikiem, bo tylko te dwie rzeczy są inne |
| **Zwinięte do jednego slajdu** (s7) | Jakość odczytu: sekcje, cytowania i przepisy, wcześniej trzy osobne slajdy |
| **Usunięte** | Porównanie z wyszukiwarką UZP i osobny slajd o danych osobowych — oba są odpowiednikami slajdów, które sala zna |
| **Nowe — kręgosłup** (s2) | Tabela `ceidg-tool` kontra `kio-tool`, wiersz po wierszu, z dwoma wierszami tezy: asystent **nie ma** / obsługa przez model **docelowa** |
| **Nowe** (s3) | Dlaczego brak asystenta jest zaletą dla agenta, a nie oszczędnością |
| **Nowe** (s4) | Jak model używa narzędzia; odsyła do `docs/dla-modelu.md` |
| **Nowe** (s5) | Co da się wyszukać i pułapka `--fraza` w `pobierz` |
| **Nowe** (s6) | Limity kanału i podniesienie ich kluczem: 1 500 → 5 000 na dobę |
| **Nowe** (s1a) | Czym jest KIO: odwołania, dwie strony, wyrok albo postanowienie, skarga do sądu — i jak kończą się sprawy |
| **Nowe** (s5b) | Rozkład zbioru po rocznikach z pomiaru 26: zera w 2007–2009, luka w 2018, 56 % w ostatnich pięciu latach |
| **Nowe** (s10a) | Wniosek: narzędzie jest gotowe pod agenta — sześć rzeczy, które to tworzą, i jedna, która zostaje |
| **Nowe** (s5a) | Skala całego zbioru: 29 580 orzeczeń u pośrednika, nasze 443 to 1,5 %, koszt pobrania całości i to, czego o samym urzędzie nie wiemy |
| **Nowe** (s7a) | Co dokładnie jest w bazie: dziewięć tabel w trzech warstwach i podział korpusu; materiał w `docs/anatomia-bazy.md` |
| **Zachowane bez zmian** | s8 (złoty zbiór i dwie usterki) — jedyny slajd, którego odpowiednika w tamtej prezentacji nie było |

**Zasada na przyszłość.** Prezentacja dla tej sali stoi **na** poprzedniej, nie obok niej. To, co
tamta już powiedziała, dostaje wiersz, a nie slajd; miejsce należy się temu, co jest inne.

---

## 2. Układ slajdów — wersja pierwsza, zastąpiona (zapis historyczny)

| # | Twierdzenie slajdu | Czym poparte |
|---|---|---|
| 1 | Tytuł: jedno pytanie o orzecznictwo, jeden lokalny korpus, każdy wynik do sprawdzenia u źródła | — |
| 2 | Państwo publikuje orzeczenia KIO trzema drogami; narzędzie chodzi jedną, z powodu | pomiary 1, 12, 14, 23; decyzje A i B |
| 3 | Co ląduje na dysku: baza SQLite z wersjami, nie zrzut ekranu | schemat 5, tabele `documents`/`raw_versions`/`sections`/`citations`/`provisions` |
| 4 | Wobec wyszukiwarki UZP: do jednego orzeczenia lepsza jest wyszukiwarka; różnica zaczyna się przy liczbie mnogiej | pomiar 11, liczby korpusu |
| 5 | Pełny tekst, nie streszczenie: 443 dokumenty, komplet sekcji w 100 %, zero znaków nieprzypisanych | raport pokrycia 2026-09-20 |
| 6 | Pułapka: pośrednik sięga tylko do 2010, a KIO orzeka od 2007-12 | pomiar 3a; korpus 2010–2026 |
| 7 | Ile to kosztuje: kosztem jest czas i cudzy serwis, a wycena pada **przed** zgodą | `pipeline.py`, sufit zgody; pomiar 5 (119 żądań) |
| 8 | Zgoda ma sufit, nie tylko treść — usterka znaleziona w przeglądzie fazy 3 i naprawiona | przegląd 2026-09-20, `_sufit()` |
| 9 | Cytowania: 1 708 w korpusie, 98,7 % rozpoznanych, każde z pozycją w tekście | pomiar 25, raport pokrycia |
| 10 | Przepisy: 16 834, a 31,1 % **nieustalonych** — narzędzie mówi, czego nie wie | tabela `provisions`, 2026-09-20 |
| 11 | Sześć zabezpieczeń; o te dwa zapytacie pierwsi (dane zostają lokalnie; zero żądań poza kanałem) | reguły granic 10–14, `test_boundaries.py` |
| 12 | Złoty zbiór: 17 dokumentów przejrzanych okiem **i potwierdzonych przez właściciela**; automat nie widzi wszystkiego | O-4, dwie usterki znalezione okiem, potwierdzenie 2026-09-20 |
| 13 | Czego to nie zrobi. Lepiej wiedzieć teraz | O-1, O-2, O-5, O-7; brak oceny prawnej; asystenta nie będzie (decyzja, nie brak) |
| 14 | Jawność orzeczeń nie zwalnia z obowiązków wobec danych osobowych | pomiar 10, CC BY 4.0 Atlasu |
| 15 | Stan przekazania: fazy 0–3 przyjęte, faza 4 za bramką warunkową | `decisions.md`, ADR-0008 §13 |
| 16 | Siedem zdań do zapamiętania | — |

**Sprostowanie liczby slajdów.** Ten plik mówił „16, jak we wzorcu"; wzorzec ma **17** — szesnaste
to podsumowanie, siedemnaste zamknięcie z propozycją pokazu na żywo. Złożona prezentacja ma 17
i taki jest układ w tabeli wyżej. Liczba wzięta z pamięci zamiast z pliku — dokładnie ten błąd,
przed którym ostrzega sekcja 4.

Slajd 8 i slajd 12 są w tym zestawie celowo: prezentacja `ceidg-tool` wygrywa tym, że **pokazuje
usterkę i jej naprawę**, a nie tylko listę możliwości. Narzędzie, które opowiada, co mu się
zepsuło i jak to zauważyło, jest wiarygodniejsze od takiego, które jest samą zaletą.

**Notatki prelegenta.** Każdy slajd niesie `<aside>` z jednym akapitem: po co ten slajd stoi
w tym miejscu i czego spodziewać się z sali. Otwiera je klawisz `N`; na rzutniku są niewidoczne.

---

## 3. Materiał liczbowy — wszystko z bazy operatora, zero żądań

Stan na 2026-09-20, wersja odczytu 6.

| Liczba | Wartość | Skąd |
|---|---|---|
| Dokumentów w korpusie | 443 | `documents`, raport pokrycia 2026-09-20 |
| Zakres roczników | 2010–2026 | sygnatury; 2023 → 192 dok., 2024 → 160, pozostałe roczniki po ~6 |
| Komplet sekcji | 443 z 443 (100 %) | raport pokrycia |
| Znaki nieprzypisane do sekcji | 0 z ~13,5 mln | raport pokrycia, wszystkie roczniki |
| Sekcji | 1 772 | `sections` |
| Cytowań | 1 708 | `citations` |
| Cytowań nierozpoznanych | 23 (1,3 %) | pomiar 25 po rodzinie A; przed pomiarem 78 (4,6 %) |
| Rozkład cytowań | KIO 1 279 · SO 165 · SN 99 · TSUE 60 · KIO bez repertorium 29 · inne 26 · SA 19 · WSA 12 · NSA 12 · UZP ZO 7 | `citations.rodzaj` |
| Przepisów | 16 834 | `provisions` |
| Rozkład aktów | Pzp 2019 — 7 849 · **nieustalone — 5 233 (31,1 %)** · Pzp 2004 — 2 529 · kc 591 · inne 554 · rozporządzenie 52 · kpc 26 | `provisions.akt` |
| Żądań na zbudowanie korpusu 443 od zera | 464 | Przebieg 3, `requests_log` tamtej bazy — **nie** cały projekt: poza nim Przebiegi 1–2, pomiary sondą, pomiar 26 i Przebieg 4 (2026-09-22: baza tej maszyny ma 475 żądań w 26 przebiegach) |
| Przebiegów | 19 | `runs` |
| Złoty zbiór | 17 dokumentów, 68 granic sekcji, 91 cytowań, 226 postaci przepisów — **potwierdzone przez właściciela 2026-09-20** | `tests/gold/*.json`, pole `przeglad` |
| Dług zamknięty | `store.py` 1 466 linii i `pipeline.py` 971 → 921 przy sufitze 800 — rozbite 2026-09-22 (ADR-0009), największy moduł po rozbiciu ma 497 linii | `tests/test_boundaries.py` |
| Testów | 1 340, wszystkie zielone | `pytest`, 2026-09-20 |
| Anonimizacja u pośrednika | przewodniczący nieanonimizowany w 404 dok., protokolant w 286 | pomiar 10, 2026-09-19 |
| Licencja kanału | Atlas: CC BY 4.0, odczytana u źródła | pomiar 23, 2026-09-18 |
| Warunki UZP | nie ma ich, ani informacji o ich braku | pomiar 14, 2026-09-15 |

**Liczba, która robi największe wrażenie i jest prawdziwa:** 464 żądania sieciowe przez cały
projekt, przy 443 dokumentach z pełnym tekstem w bazie. Nie dlatego, że narzędzie jest oszczędne
z natury — dlatego, że każdy pomiar był liczony pod kątem kosztu, a większość wykonano na danych
już pobranych.

---

## 4. Czego na slajdach twierdzić nie wolno

- **Że korpus jest kompletny.** Mianownika nie mamy; dałby go pomiar 4b/16 (O-7). Wolno
  powiedzieć: „443 dokumenty pobrane i przeczytane w całości", nie „wszystkie orzeczenia".
- **Że narzędzie ocenia prawnie.** Zakres to wspomaganie wyszukiwania i cytowania (audyt 4.3).
- **Że 31,1 % nieustalonych przepisów to defekt parsera.** Część z nich to zapisy, które nie
  wskazują aktu w sposób rozstrzygalny z tekstu; przegląd O-4 pokazał, że uczciwe „nieustalone"
  bywa **poprawką** wobec błędnego przypisania.
- **Że pośrednik jest wierny źródłu.** Nikt tego nie zmierzył; ryzyko resztkowe jest przyjęte
  świadomie (decyzja A) i tak ma być powiedziane.
- **Liczby testów, żądań i dokumentów z pamięci.** Każda z nich zmienia się przy przebiegu —
  przelicz je w dniu składania slajdów poleceniami z sekcji 6.

---

## 5. Forma

Jeden plik HTML, samowystarczalny, bez połączenia z siecią przy wyświetlaniu — tak jak
`prezentacja-ceidg-ekran.html`. Slajd = `<section class="slide">` z głową, treścią i stopką;
stopka niesie źródło i datę. Nawigacja klawiszami (`←` `→`, `N` notatki), pasek postępu na dole.

**Stan wykonania: `prezentacja-kio-ekran.html`, 264 KB, 17 slajdów.** Z tego 214 KB to trzy fonty
osadzone w pliku jako `@font-face` — przeniesione z wzorca, żeby prezentacja wyglądała tak samo
na każdej maszynie i **nie odpytywała żadnego serwera fontów**. Sprawdzone po złożeniu: w pliku
nie ma ani jednego odwołania do adresu zewnętrznego (`http`, `https`, `src=`, `href=`), a znaczniki
są domknięte. Plik otwiera się dwuklikiem, bez serwera i bez internetu; motyw jasny i ciemny idzie
za ustawieniem systemu.

Plik prezentacji **nie wchodzi do repozytorium `kio-tool`**, tak samo jak wzorzec `ceidg`
(nieśledzony w drzewie Kio): niesie treści prezentacyjne, a nie kod, i żyje własnym cyklem.

---

## 6. Polecenia, którymi przeliczyć liczby w dniu składania

```powershell
cd E:\GitHub\Kio
$env:PYTHONUTF8 = "1"; .venv\Scripts\python.exe -m pytest
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe pokrycie --zloty tests\gold
$env:PYTHONUTF8 = "1"; .venv\Scripts\kio-tool.exe demo
```

Wszystkie trzy działają **bez jednego żądania sieciowego**; trzecie generuje korpus pokazowy
i jest jedynym dopuszczalnym źródłem zrzutów ekranu.
