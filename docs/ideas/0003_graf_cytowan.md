# Graf cytowań jako polecenie: `cytujace` i `cytowane`

Date: 2026-09-22
Status: draft
Author: P0w3r223
Related to: tabela `citations` (schemat 6, ADR-0006), architektura §3.5 i §3.8 (`get_citations`)

---

## Problem

Parser odczytuje z treści powołania innych orzeczeń i zapisuje je w `citations`, ale jedynym
wyjściem jest raport `pokrycie` i dodatek na końcu pliku `md`. Pytanie „kto powołuje to
orzeczenie” agent zamienia dziś w `szukaj --fraza "KIO 3810/23"`, co łapie też przypadkowe
wzmianki i nie mówi, w której sekcji padło powołanie.

## Co mówią dane

Pomiar 2026-09-22 na bazie operatora, 0 żądań:

| | |
|---|---|
| Powołań z sygnaturą | 1 685 (z 1 708 wierszy `citations`) |
| Różnych sygnatur powołanych | 1 171 |
| Powołań wskazujących dokument **obecny w korpusie** | **21** (1,2 %) |
| Rodzaje | `kio` 1 279, `so` 165, `sn` 99, `tsue` 60, `kio_bez_repertorium` 29, `sa` 19, `nsa` 12, `wsa` 12, `uzp_zo` 7, `inne` 26 |
| Najczęściej powoływane | KIO 3082/23, KIO 3388/23, KIO 473/14 (po 18 powołań), KIO 2516/23 (16) |

Wniosek zmienia kształt pomysłu: przy korpusie 1,5 % zbioru graf **wewnątrz** korpusu jest
prawie pusty. Największą wartością nie jest „kto cytuje”, tylko **„czego brakuje”** — lista
najczęściej powoływanych orzeczeń, których nie mamy, to gotowy, uzasadniony plan pobrania.

## Jak to sobie wyobrażam

```
kio-tool cytujace "KIO 3082/23" --json     # dokumenty w korpusie, które je powołują
kio-tool cytowane "KIO 3810/23" --json     # co powołuje ten dokument
kio-tool cytowane --brakujace --json       # najczęściej powoływane, których nie ma w korpusie
```

Wiersz `cytujace`: `sygnatura`, `doc_id`, `data_wydania`, `sekcja` (z `sections` po offsecie
powołania), `kontekst` (±200 znaków wokół `char_start..char_end`), `cytowanie`.
Wiersz `cytowane`: `sygnatura_powolana`, `rodzaj`, `surowy` (zapis z treści), `w_korpusie`
(bool) i `doc_id`, gdy jest.
`--brakujace`: `sygnatura`, `powolan`, `w_ilu_dokumentach`, tylko rodzaje `kio*` (tylko te
kanał `atlas` umie dostarczyć). `liczby` jak zawsze: `w_korpusie`, `powolan`, `pokazano`.

**Most do pobierania.** `pobierz --fraza "KIO 3082/23"` trafia w sygnaturę, bo tak działa
wyszukiwarka kanału (pułapka 1 obraca się tu na korzyść). Agent może więc z `--brakujace` zrobić
listę, pokazać operatorowi wycenę (`pobierz --wycena`, plan pkt 5) i poprosić o zgodę. Pobranie
nadal wymaga zgody operatora — polecenie niczego samo nie pobiera.

## Pułapki do opisania w `dla-modelu.md`

- „Nikt nie cytuje” znaczy „nikt **w pobranych N**”, nie w orzecznictwie.
- Powołanie ≠ aprobata: Izba powołuje orzeczenia także po to, żeby się od nich odciąć, a strony
  powołują je w swoich stanowiskach. `sekcja` i `kontekst` są po to, żeby agent to sprawdził.
- Sygnatura `kio_bez_repertorium` i `inne` mogą nie dać się rozwiązać — zwracać `surowy`.

## Koszt

Bez zmiany schematu i bez `PARSE_VERSION` — sam odczyt istniejących tabel. Nowe zapytania
w `store/wyszukiwanie.py` (moduł ma 298 linii, zmieści), polecenia w `cli.py`, teksty.
Indeks `citations(sygnatura)` przyda się przy rosnącym korpusie — wtedy to jest schemat 7.

## Związek z fazą 4

To jest `get_citations` z architektury §3.8. Zapytania powinny leżeć w `store`, nie w `obsluga`,
bo reguła 13 pozwala serwerowi MCP importować wyłącznie `store` i `exporter`.
