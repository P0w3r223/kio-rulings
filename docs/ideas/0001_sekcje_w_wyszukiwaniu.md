# Sekcja przy trafieniu i `szukaj --sekcja`

Date: 2026-09-22
Status: draft
Author: P0w3r223
Related to: `docs/dla-modelu.md` (pułapka 3), ADR-0006 (parser i struktura), architektura §3.8 (`search_rulings`)

---

## Problem

`szukaj --json` zwraca fragment bez informacji, z której części orzeczenia pochodzi. Instrukcja
dla modelu przyznaje to wprost (pułapka 3): zdanie z uzasadnienia bywa stanowiskiem strony, nie
Izby, więc agent musi dociągnąć pełny tekst, żeby nie przypisać Izbie cudzego poglądu. To jest
najczęstszy powód, dla którego agent czyta całe orzeczenie zamiast jednego akapitu.

Struktura już jest w bazie: tabela `sections` ma granice sekcji jako offsety w oryginale.
Zmierzone 2026-09-22 na bazie operatora, 0 żądań: 443 dokumenty, każdy ma `naglowek`,
`sentencja`, `pouczenie` i `uzasadnienie`; średnie długości 711 / 772 / 285 / 28 704 znaki.

## Jak to sobie wyobrażam

**Indeks FTS na sekcję zamiast na dokument.** Wiersz `fts` to dziś `(doc_id, sygnatury, tresc)`.
Proponuję wiersz na odcinek: `(doc_id, porzadek, rodzaj, tresc)` plus osobny wiersz na sygnatury.
Odcinki między sekcjami (to, co `exporter.tresc_z_sekcjami` przepuszcza bez nagłówka) idą jako
`nieprzypisane`. **Nic z tekstu nie może wypaść z indeksu** — strażnik: suma długości
zaindeksowanych odcinków równa się długości treści dla każdego dokumentu.

FTS5 nie ma `offsets()` z FTS3, więc wyznaczanie sekcji po fakcie z pozycji trafienia wymagałoby
własnej funkcji pomocniczej albo szukania fragmentu z `snippet()` w tekście (kruche: wielokropki,
powtórzenia frazy). Wiersz na sekcję daje sekcję za darmo, z samego `SELECT`.

**Wynik `szukaj --json`** — nadal jeden wiersz na dokument (liczby się nie zmieniają):

```json
{"sygnatura": "KIO 3810/23", "sekcja": "uzasadnienie",
 "trafien_w_sekcjach": {"uzasadnienie": 3, "sentencja": 1},
 "fragment": "…", "doc_id": "atlas:kio-3810-23", "...": "..."}
```

Ranga dokumentu to najlepsza (najniższa) `bm25` z jego odcinków, fragment pochodzi z tego
odcinka. `liczby.trafien` liczy dokumenty, jak dziś.

**Filtr `--sekcja`** (powtarzalny): `szukaj --fraza "rażąco niska cena" --sekcja sentencja`.
Wartości z `parser.sections.RODZAJE_SEKCJI`; w `opis --json` jako lista dozwolona.

## Krok dalej: ocena Izby a stanowiska stron

Prawdziwa odpowiedź na pułapkę 3 to rozcięcie `uzasadnienia` na część ustaleń i stanowisk oraz
część „Izba zważyła”. Pomiar 2026-09-22, 0 żądań, FTS na bazie operatora:

| Znacznik | Dokumentów z 443 |
|---|---|
| „Izba zważyła” | 119 (27 %) |
| „Izba zważyła, co następuje” | 99 |
| „Izba ustaliła” | 232 |

Jeden znacznik pokrywa ćwierć korpusu — to za mało na regułę. Zanim cokolwiek powstanie: zebrać
warianty („Izba zważyła”, „Izba ustaliła i zważyła”, „Rozpoznając odwołanie, Izba…”, „Izba
uznała”) i zmierzyć pokrycie łącznie, na złotym zbiorze sprawdzić, czy granica wypada tam, gdzie
wskazałby prawnik. Nowe rodzaje sekcji to zmiana w `parser/` → `PARSE_VERSION` + `przelicz`.

## Koszt i ryzyko

- Zmiana schematu (7), migracja `CREATE … IF NOT EXISTS` + przebudowa `fts` przy `przelicz`;
  zero żądań. Wymaga ADR-u.
- Rozmiar bazy: treść już jest w `fts` (tabela z treścią), więc przyrost to głównie liczba
  wierszy, nie bajty — do zmierzenia na kopii bazy przed decyzją.
- Granice sekcji są odczytem automatycznym. `sekcja` w wyniku musi to mówić tak samo jak `md`
  („granice wyznacza odczyt automatyczny”), inaczej agent weźmie je za pewnik.

## Związek z fazą 4

`search_rulings` z architektury §3.8 dostaje ten sam kształt — pole `sekcja` jest dokładnie tym,
czego klient MCP potrzebuje do panelu cytowań.
