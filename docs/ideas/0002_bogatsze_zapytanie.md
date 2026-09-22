# Bogatsze zapytanie w `szukaj`: warianty, bliskość, stronicowanie

Date: 2026-09-22
Status: draft
Author: P0w3r223
Related to: `kio_tool/store/wyszukiwanie.py` (`szukaj`, `_fraza_fts`), `docs/dla-modelu.md`

---

## Problem

`szukaj` przyjmuje jedną frazę i szuka jej dosłownie — słowa obok siebie, w tej kolejności.
To dobra decyzja na start („odrzucenie oferty” nie ma trafiać w każdy dokument z obydwoma
słowami), ale polszczyzna się odmienia. „Rażąco niska cena”, „rażąco niskiej ceny”, „rażąco
niską cenę” to trzy wywołania, a agent sam scala wyniki i sam deduplikuje dokumenty. Liczby
(`trafien`) z trzech wywołań nie dają się zsumować, bo dokument może trafić kilka razy.

Brakuje też stronicowania: `--limit` zmienia tylko liczbę pokazanych wierszy, więc przy
39 trafieniach agent, który chce przejrzeć wszystkie, bierze `--limit 39` i dostaje całość naraz.

## Jak to sobie wyobrażam

**Warianty jako OR.** `--fraza` powtarzalne; każda fraza zostaje osobnym cytatem FTS5, łączonym
przez `OR`:

```
kio-tool szukaj --fraza "rażąco niska cena" --fraza "rażąco niskiej ceny" --json
```

`liczby.trafien` liczy dokumenty unikalne, a nowe `liczby.trafien_na_fraze` daje rozbicie
(`{"rażąco niska cena": 39, "rażąco niskiej ceny": 51}`). Agent widzi, który wariant coś wnosi.

**Prefiks na ostatnim słowie.** FTS5 obsługuje `"rażąco nisk" *` (prefiks dotyczy ostatniego
tokenu cytatu). Flaga `--prefiks` dokleja `*` do każdej frazy. Łapie odmianę bez słownika
morfologicznego — kosztem szumu, więc zawsze jako wybór agenta, nigdy domyślnie. Przed wdrożeniem
zmierzyć na korpusie: ile dodatkowych trafień daje prefiks i ile z nich to szum (próbka ręczna).

**Bliskość.** `--blisko N` przy dwóch frazach buduje `NEAR("…" "…", N)`: „wadium” w pobliżu
„zwrot” bez wymogu sąsiedztwa. Tylko dla dokładnie dwóch fraz — przy trzech semantyka NEAR robi
się nieoczywista dla agenta.

**Stronicowanie.** `--offset K` plus `liczby.nastepny_offset` (albo `null` na końcu). Kolejność
jest już stała (`ranga, doc_id`), więc strony są powtarzalne.

**Sortowanie.** `--sortuj trafnosc|data` (domyślnie `trafnosc`, jak dziś). Pytanie „jak Izba
orzeka ostatnio” potrzebuje najnowszych, nie najtrafniejszych.

## Czego nie robić

- **Nie przepuszczać składni FTS5 z wejścia.** Operatory buduje narzędzie; każda fraza zostaje
  cytatem z podwojonym cudzysłowem, jak w `_fraza_fts`. Surowe `--zapytanie` byłoby wygodne
  i otwierałoby błędy składni FTS5 jako kod 1 z komunikatem SQLite — gorzej dla agenta niż
  ograniczony, ale przewidywalny zestaw flag.
- **Nie dokładać stemmera** (Morfologik i podobne). To zależność i zmiana tokenizacji całego
  indeksu; prefiks i warianty OR pokrywają większość potrzeb bez tego. Wrócić, jeśli pomiar
  prefiksu pokaże za dużo szumu.

## Koszt

Bez zmiany schematu. Zmiany: `criteria.py` (lista fraz, tryb), `store/wyszukiwanie.py`
(budowa zapytania, liczniki na frazę, offset), `cli.py`, `ui/texts.py`, `docs/dla-modelu.md`.
`pobierz --fraza` zostaje pojedyncze — kanał i tak dopasowuje sygnaturę, nie treść.

## Związek z fazą 4

Te same parametry (`frazy[]`, `prefiks`, `blisko`, `offset`, `sortuj`) stają się argumentami
narzędzia `search_rulings`.
