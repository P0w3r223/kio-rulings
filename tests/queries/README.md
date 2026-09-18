# Zapytania operatora — miara wyszukiwania i wejście do wyboru kanału

Data utworzenia: 2026-09-17
Status: **szkielet do wypełnienia przez właściciela** — treść jest pracą domenową, nie kodem; **od 2026-09-18 poza ścieżką krytyczną** (ADR-0005 Z-9): przy jednym kandydacie kolumnę `capabilities()` w ADR-0004 wypełnia udokumentowana lista filtrów, a zestaw zapytań wraca w fazie 3 jako miara wyszukiwania. Zdania niżej o „wejściu do wyboru kanału" opisują stan z 2026-09-17
Autor: P0w3r223
Related to: `ARCHITEKTURA_KIO_TOOL.md` (4.8, 5.2), `docs/adr/0004_wybor_kanalu.md` (sekcja 4.1), `docs/adr/0005_bramka_per_kanal.md` (Z-9)

---

## Po co ten katalog istnieje przed jakimkolwiek kodem wyszukiwania

Architektura 4.8 mówi, że zestaw 30–50 zapytań operatora jest **miarą** wyszukiwania: dopiero
wobec niego wolno rozstrzygać, czy FTS5 wystarcza, czy potrzebny jest analizator fleksyjny
albo warstwa gęsta. To jest rola oczywista i odległa — faza 3.

Rola mniej oczywista jest natychmiastowa: **zapytania są wejściem do wyboru kanału.** Kanał,
który nie umie filtrować po tym, czego operator naprawdę szuka, jest gorszym kanałem —
niezależnie od tego, ile dokumentów niesie i jak tanio. Tabela kandydatów w ADR-0004 ma
kolumnę na `capabilities()`, a bez tej listy porównuje się możliwości z niczym.

Dlatego ten katalog da się wypełnić **dziś**: kosztuje godzinę pracy domenowej i zero żądań,
a stoi na ścieżce krytycznej do bramki fazy 0.

## Czego tu nie ma i dlaczego

Zapytań nie napisał tu model i nie ma ich napisać. Powód stoi w audycie jako mina 4: pierwsza
wersja korpusu pokazowego w `ceidg-tool` miała wymyślone nazwy branż, dwa nieistniejące kody
i cztery z pięciu miast w złym powiecie — wszystko przeszło bramki, bo nic tego nie
sprawdzało. Zapytanie wymyślone brzmi tak samo wiarygodnie jak zapytanie prawdziwe, a różni
się tym, że nie mierzy niczego.

Plik `szablon.yaml` niesie **kształt wpisu**, nie treść: pola są prawdziwe, wartości są puste
albo neutralne i mają zostać zastąpione.

## Format

Jeden plik `zapytania.yaml` z listą wpisów. Pola:

| Pole | Co niesie |
|---|---|
| `id` | krótki identyfikator, stabilny — po nim raport pokrycia wskazuje zapytanie |
| `cel` | `zakres_dat`, `sygnatury`, `przepis`, `haslo`, `fraza` — cztery pierwsze odpowiadają ścieżce kreatora z 5.2 |
| `pytanie` | **własnymi słowami operatora**: co chce znaleźć i po co |
| `kryteria` | ta sama treść wyrażona parametrami, jeśli już wiadomo jak |
| `dlaczego` | jaka decyzja albo praca zależy od odpowiedzi; pozwala odróżnić zapytania nośne od ciekawostek |
| `dobra_odpowiedz` | po czym poznasz, że wynik jest **kompletny**, a nie tylko niepusty (mina 2 audytu: „kryterium jest poprawne" to nie to samo co „wynik jest kompletny") |
| `wymaga_od_kanalu` | jakiej zdolności wymaga to zapytanie: filtr po dacie, po przepisie, wyszukiwanie w treści, sortowanie. Wypełniane przy porównaniu kanałów — to jest ta kolumna, która wchodzi do ADR-0004 |

Pole `dobra_odpowiedz` jest w tym zestawie najważniejsze i najłatwiejsze do pominięcia.
Zapytanie bez niego mierzy, czy narzędzie cokolwiek zwróciło; zapytanie z nim mierzy, czy
zwróciło **to, co trzeba** — a cała mina 2 polega na tym, że te dwie rzeczy wyglądają
identycznie.
