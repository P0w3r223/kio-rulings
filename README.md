# kio-tool

Lokalny, wersjonowany korpus orzecznictwa **Krajowej Izby Odwoławczej**. Pobiera orzeczenia
z pełnym tekstem z publicznego API Atlasu Przetargów (licencja CC BY 4.0), zapisuje je w SQLite
dokładnie tak, jak przyszły, rozkłada na sekcje, cytowania i przepisy, szuka bez sieci
i eksportuje do `xlsx`, `csv`, `jsonl` i `md` — zawsze z atrybucją źródła.

**Stan na 2026-09-22:** fazy 0–3 przyjęte; kreator, tryb pokazowy, wyjście maszynowe dla modelu
(`--json`, `docs/dla-modelu.md`). Korpus operatora: 443 orzeczenia z roczników 2010–2026.

## Instalacja

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Python 3.12. Testy działają przy zablokowanej sieci — żaden nie wysyła żądania na zewnątrz.

Do pobierania wymagany jest adres kontaktowy do nagłówka `User-Agent` (bez niego narzędzie nie
wyśle żądania); klucz API Atlasu jest opcjonalny i podnosi limit z 1 500 do 5 000 żądań na dobę:

```
set KIO_TOOL_CONTACT=twoj@adres
set KIO_TOOL_ATLAS_KEY=klucz          # opcjonalnie
```

## Najprościej

```
.venv\Scripts\kio-tool.exe            # kreator: menu, podpowiedzi, tabela kosztów przed pobraniem
.venv\Scripts\kio-tool.exe demo       # to samo na korpusie fikcyjnym, bez sieci i konfiguracji
```

Wszystko, co wytwarza tryb pokazowy, jest oznaczone (osobna baza, przedrostek `DEMO_`, rekordy
bez bloku cytowania).

## Użycie

Z aktywnym `.venv` (`.venv\Scripts\activate`), inaczej `.venv\Scripts\kio-tool.exe`:

```
kio-tool pobierz --od 2024-02-01 --do 2024-02-29 --wycena --json
kio-tool pobierz --od 2024-02-01 --do 2024-02-29 --zgoda
kio-tool wznow
kio-tool szukaj --fraza "rażąco niska cena" --od 2023-01-01 --json
kio-tool czytaj "KIO 3810/23" --sekcja sentencja --json
kio-tool eksportuj --od 2024-01-01 --do 2024-01-31 --format xlsx,md
kio-tool runy
kio-tool przelicz
kio-tool pokrycie --zloty tests/gold
```

| Polecenie | Co robi | Sieć |
|---|---|---|
| `pobierz` | lista z Atlasu + jeden rekord z pełnym tekstem za każdy nowy dokument; na końcu eksport | tak |
| `wznow` | dokończenie przerwanego przebiegu bez duplikatów | tak |
| `szukaj` | fraza dosłownie w pełnym tekście z filtrami; zawsze z liczbą dokumentów w korpusie i trafień | nie |
| `czytaj` | jedno orzeczenie po sygnaturze albo `doc_id`: metadane, cytowanie, mapa sekcji, treść całości albo wybranych sekcji | nie |
| `eksportuj` | dokumenty przebiegu (`--run-id`) albo pasujące do kryteriów | nie |
| `runy` | historia przebiegów | nie |
| `przelicz` | ponowny odczyt z zapisanych bajtów, bez pobierania | nie |
| `pokrycie` | raport jakości odczytu; `--zloty` sprawdza złoty zbiór | nie |

Filtry wspólne dla `pobierz`, `szukaj` i `eksportuj`: `--od`, `--do`, `--fraza`,
`--rozstrzygniecie`, `--rodzaj`, `--przepis`, `--przewodniczacy`, `--strona`. W `pobierz`
`--fraza` trafia do wyszukiwarki Atlasu, która dopasowuje sygnaturę, nie treść — treść
przeszukuje lokalnie `szukaj`. Wszystkie polecenia poza kreatorem i pokazem przyjmują `--json`; `pobierz --wycena` podaje sam koszt
(jedna strona listy, zero dokumentów).

Kody wyjścia: 0 — wykonane, 1 — błąd, 2 — przebieg do wznowienia (albo błąd składni polecenia),
3 — konfiguracja, brak zgody albo zły parametr, 130 — Ctrl+C.

## Zgoda na przebieg masowy

Powyżej **50 żądań** potrzebna jest flaga `--zgoda`; bez niej przebieg staje na progu jako
`przerwany`, a to samo polecenie z `--zgoda` go wznawia. Zgoda wiąże się z liczbą z tabeli
kosztów — przebieg, który by ją przekroczył, zatrzymuje się. Zgody nie da się zapisać
w konfiguracji.

Tempo pilnuje samo narzędzie: co najmniej 1 s między żądaniami, najwyżej 450 na minutę i 1 400 na
dobę; 429, 5xx i zerwane łącza są ponawiane według kontraktu kanału. **Narzędzie nie omija
zabezpieczeń** — przy CAPTCHA czy blokadzie zatrzymuje się i mówi o tym.

Przerwany przebieg (Ctrl+C, sieć, ubity proces, pełny dysk) zostaje w bazie z punktem
kontrolnym i wznawia się bez duplikatów.

## Pliki wynikowe

Baza i eksporty leżą poza repozytorium: `%LOCALAPPDATA%\kio-tool\kio-tool\` (`korpus.sqlite`,
`wyniki/`). Korpus niesie nazwiska składu orzekającego i protokolantów, więc nie trafia do
repozytorium.

| Format | Zawartość |
|---|---|
| `xlsx` | arkusz `Orzeczenia` (21 kolumn), `Slownik`, `Metadane`; bez pełnego tekstu |
| `csv` | te same kolumny, `;`, UTF-8 z BOM |
| `jsonl` | tożsamość, blok cytowania i surowy rekord kanału z pełnym tekstem |
| `md` | plik na orzeczenie: metadane, blok cytowania, tekst z nagłówkami sekcji, spis cytowanych orzeczeń i przepisów; `INDEX.md` |

Każdy wiersz niesie adres orzeczenia w wyszukiwarce UZP, skrót SHA-256 wersji i atrybucję
„Źródło: Atlas Przetargów (https://atlasprzetargow.pl)". `data_wydania` jest taka, jak podał
pośrednik — bywa błędna albo pusta.

## Czego narzędzie nie robi

- Nie sięga przed rocznik 2010 i nie wie, czy korpus jest kompletny wobec urzędu.
- Ma jeden kanał (`atlas`); nie wykrywa zmian u źródła po pobraniu.
- Nie ocenia spraw prawnie i nie ma modelu językowego w środku — model prowadzi je z zewnątrz.
- Nie pilnuje dwóch procesów pracujących na jednej bazie.

## Rozwój

```
set PYTHONUTF8=1
.venv\Scripts\python.exe -m pytest        # 1 397 testów (2026-09-22), sieć zablokowana
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\mypy.exe kio_tool scripts   # strict
```

Granice między modułami (m.in. sieć z bazą łączy wyłącznie `pipeline/pobieranie.py`) pilnują
testy w `tests/test_boundaries.py`. Poprawkę zabezpieczenia sprawdza się mutacją: zepsuć kod
i zobaczyć, że test się zapala.

## Dokumentacja

| Plik | Co niesie |
|---|---|
| `docs/dla-modelu.md` | instrukcja dla modelu prowadzącego narzędzie |
| `docs/decisions.md` | pomiary z datami, przebiegi, decyzje właściciela |
| `docs/adr/` | decyzje architektoniczne 0001–0009 |
| `docs/AUDYT_KIO_ORZECZENIA.md`, `docs/ARCHITEKTURA_KIO_TOOL.md` | źródło, dopuszczalność, reguły granic, architektura |
| `CLAUDE.md` | zasady pracy dla Claude Code |

## Licencja

MIT dla kodu. Dane z Atlasu Przetargów na licencji CC BY 4.0 — każdy eksport niesie atrybucję.
