# kio-tool — konfiguracja projektu

Lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej (kanał `atlas`). Wzorce
przeniesione z sąsiedniego `..\Ceidg` (`ceidg-tool`) bez wspólnej biblioteki.

## Stan (2026-09-22)

- Fazy 0–3 przyjęte przez właściciela; **pozycji otwartych nie ma** — nie odtwarzaj ich
  z historii, briefów ani ADR-ów. Faza 4 nie jest w toku.
- **Praca lokalna na `master`, bez `push` i bez PR-ów.** Nic nie wysyłamy bez wyraźnej prośby
  właściciela.
- Korpus operatora na tej maszynie: 443 orzeczenia, schemat 6, `PARSE_VERSION` 6. Baza poza
  repozytorium (`%LOCALAPPDATA%\kio-tool\kio-tool\korpus.sqlite`).
- `.venv` na Pythonie 3.12.10. `KIO_TOOL_CONTACT` jest zmienną użytkownika Windows — nie pytaj
  o nią i nie zapisuj jej w repozytorium.

## Decyzje, których nie podważaj

- **Asystenta językowego nie będzie.** Nie proponuj go i nie wprowadzaj SDK modelu do drzewa.
  Model prowadzi narzędzie z zewnątrz — przez polecenia i `--json`.
- **`docs/dla-modelu.md` zmienia się razem z każdą flagą i poleceniem.** Instrukcja rozjechana
  z narzędziem jest gorsza niż jej brak.
- **Projekt nie prowadzi korespondencji** (UZP, prawnik, Atlas). Pisma w `docs/pisma/` zostają
  niewysłane; nie planuj wokół odpowiedzi.
- **UZP nigdy nie jest kanałem masowym** (reguła 23). Całość pobieramy wyłącznie z kanału, który
  licencjonuje reuse wprost.

## Żądania do cudzych serwisów

- **Zgoda właściciela obowiązuje w sesji, w której padła**; przebieg masowy (>50 żądań) wymaga
  jej wprost. Pojedynczy odczyt diagnostyczny nie, ale zostawia wpis w dzienniku.
- **Narzędzie nie omija zabezpieczeń** (CAPTCHA, blokada) — zatrzymuje się i mówi. Granica
  prawna (art. 267 § 1 k.k.).
- Klient przedstawia się `User-Agent` z adresem z `KIO_TOOL_CONTACT`; bez niego nie startuje.

## Doktryna

- **Liczba bez źródła i daty jest błędem.** Zapis: „zmierzone 2026-09-15, 4 żądania". Sygnatury,
  nazwy i treść przepisów bierz z odczytu z datą, nigdy z pamięci.
- **Cisza jest usterką.** Przy każdym zabezpieczeniu zapytaj: co by się wypisało, gdyby zostało
  naruszone? Puls liczy się w żądaniach wysłanych i dokumentach zapisanych.
- **Poprawkę zabezpieczenia sprawdzaj mutacją** — zepsuj kod i zobacz, że test się zapala.
  Kilka luk przeszło przez zieloną suitę i pokazała je dopiero mutacja.

## Kod

```
.venv\Scripts\python.exe -m pytest        # --block-network; liczbę testów przelicz, nie przepisuj
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format .
.venv\Scripts\mypy.exe kio_tool scripts   # strict
```

- **Reguły granic** (23; audyt 8.3 i architektura 4.1) pilnuje `tests/test_boundaries.py` skanem
  AST. Na czerwień lekarstwem jest poprawka kodu albo przeniesienie napisu do `contract.yaml`
  kanału — **dopisanie do listy wyjątków wymaga ADR-u**.
- **`store/` i `pipeline/` są pakietami z fasadą** (ADR-0009). Importuj przez fasadę; sieć
  z bazą łączy wyłącznie `pipeline/pobieranie.py`. **W testach podstawiaj we wszystkich modułach
  pakietu naraz** (`wsparcie_sondy.podstaw_w_pakiecie`, `podstaw_fabryke_klienta`) —
  `tests/test_fasady.py` zapala podstawienie w jednym z wielu miejsc.
- **Sufit 800 linii na moduł** ma strażnika; `PONAD_SUFITEM` jest pusty.
- **Zmiana w `parser/`, `docid.py` albo `odczyt.py` wymaga podniesienia `PARSE_VERSION`**
  (strażnik: odcisk w `tests/test_wersja_odczytu.py`) i `przelicz` korpusu (zero żądań).
- **Tolerancja składni sygnatur wymaga przeliczenia całego korpusu** — pozornie zbędny myślnik
  w sygnaturze TSUE po zdjęciu dał 12 fałszywych trafień (pomiar 25).
- **Zgoda ma sufit** z tabeli kosztów, także przy `--zgoda` (ADR-0008 §12.1).
- **Kreator:** każde pytanie tekstowe ma podpowiedź (test); listy wyboru bez `default=`, domyślna
  opcja na czele, styl `reverse bold`; tak/nie nie przez `questionary.confirm` (powody
  w `ui/prompts.py`).
- Piaskownica testów (`tests/conftest.py`) przekierowuje bazę, wyniki i zapis sondy do
  `tmp_path` i porównuje stan prawdziwych ścieżek przed i po.
- `docs/` jest wyłączony z `ruff format` (`force-exclude`) — ruff formatował kod w markdownie.
- Komentarze niosą powody konkretnych awarii z datami; przy przenoszeniu kodu zostaw je.

## Gdzie szukać

| Plik | Co niesie |
|---|---|
| `docs/decisions.md` | pomiary z datami i liczbą żądań, przebiegi, decyzje właściciela |
| `docs/adr/` | ADR 0001–0009, wszystkie przyjęte |
| `docs/dla-modelu.md` | instrukcja dla modelu obsługującego narzędzie |
| `docs/AUDYT_KIO_ORZECZENIA.md` | źródło, dopuszczalność, doktryna (7), reguły granic (8.3) |
| `docs/ARCHITEKTURA_KIO_TOOL.md` | architektura (4), reguły 17–23 (4.1), decyzje właściciela (8) |
| `tests/test_boundaries.py`, `tests/test_bramki_faz.py` | strażnicy reguł granic i bramek faz |
