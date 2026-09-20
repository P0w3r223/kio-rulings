# Prezentacja kio-tool — plan i materiał liczbowy

Data: 2026-09-20
Status: szkic (przygotowanie; slajdów jeszcze nie ma)
Autor: właściciel
Dotyczy: `prezentacja-ceidg-ekran.html` jako wzorzec formy

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

## 2. Układ slajdów (16, jak we wzorcu)

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
| 12 | Złoty zbiór: 17 dokumentów przejrzanych okiem; automat nie widzi wszystkiego | O-4, dwie usterki znalezione okiem |
| 13 | Czego to nie zrobi. Lepiej wiedzieć teraz | O-1…O-7, brak oceny prawnej, brak asystenta |
| 14 | Jawność orzeczeń nie zwalnia z obowiązków wobec danych osobowych | pomiar 10, CC BY 4.0 Atlasu |
| 15 | Stan przekazania: fazy 0–3 przyjęte, faza 4 za bramką warunkową | `decisions.md`, ADR-0008 §13 |
| 16 | Siedem zdań do zapamiętania | — |

Slajd 8 i slajd 12 są w tym zestawie celowo: prezentacja `ceidg-tool` wygrywa tym, że **pokazuje
usterkę i jej naprawę**, a nie tylko listę możliwości. Narzędzie, które opowiada, co mu się
zepsuło i jak to zauważyło, jest wiarygodniejsze od takiego, które jest samą zaletą.

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
| Żądań sieciowych wykonanych **przez cały projekt** | 464 | `requests_log`, wszystkie przebiegi |
| Przebiegów | 19 | `runs` |
| Złoty zbiór | 17 dokumentów, 68 granic sekcji, 91 cytowań, 226 postaci przepisów | `tests/gold/*.json` |
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
`prezentacja-ceidg-ekran.html` (275 KB, style i skrypt w pliku). Slajd = `<section class="slide">`
z głową, treścią i stopką; stopka niesie źródło i datę. Wersja ekranowa ma proporcje 16:9
i nawigację klawiszami.

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
