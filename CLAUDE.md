# kio-tool — konfiguracja projektu

Lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej. Nowe repozytorium,
wzorce przeniesione z sąsiedniego `..\Ceidg` (`ceidg-tool`) bez wspólnej biblioteki.

## Stan na 2026-09-15

**Faza 0 — sonda źródła. Kanał akwizycji nie jest wybrany i nie ma czym pobierać.**

Istnieje warstwa infrastruktury i producent tożsamości: `clock`, `safetext`, `errors`,
`config`, `richtext`, `progress`, `httpclient`, `docid`, `ratelimit` — dziewięć modułów,
1 295 linii bez `__init__.py`. Do tego `scripts/sonda.py` i 302 testy w siedmiu plikach.

**Nie istnieje** — i to jest stan zamierzony, nie niedokończony: `source/`, `parser/`, `ui/`,
`store.py`, `pipeline.py`, `criteria.py`, `cli.py`, `exporter.py`, `mcp_server.py`. Katalogi
`kio_tool/{source,parser,ui}` oraz `tests/{examples,cassettes,gold,queries}` stoją puste
z plikami `.gitkeep`. Bramka fazy 0 mówi, że przed wyborem kanału `source/` nie powstaje, bo
nie wiadomo, co miałoby implementować.

Repozytorium **nie ma zdalnego** — decyzja o jego miejscu jest otwarta (decyzja 5, audyt 13.2).

## Gdzie czego szukać

| Plik | Co niesie |
|---|---|
| `docs/AUDYT_KIO_ORZECZENIA.md` | stan źródła, dopuszczalność, build-vs-buy, doktryna (7), reguły granic (8.3), miny (11), pomiary fazy 0 (10) |
| `docs/ARCHITEKTURA_KIO_TOOL.md` | przegląd cudzych narzędzi (3), architektura (4), polecenia (5), pomiary (6), decyzje właściciela (8) |
| `docs/decisions.md` | **wyniki pomiarów z datami** — zbiorczy zapis tego, co ten projekt sam zmierzył |
| `docs/adr/` | ADR-0003 (kształt `source/`, bramka wyjścia) — przyjęty |
| `docs/pisma/` | projekty pism do wysłania przez właściciela: wniosek do UZP, mail do Atlasu, pytania do prawnika |

Kolejność czytania dla nowej sesji: `docs/decisions.md` → audyt 14 (status dowodowy) → audyt 13
(decyzje) → architektura 8 (decyzje właściciela).

## Co zmierzono, a co jest wciąż przypuszczeniem

Trzy pomiary własne, wszystkie w `docs/decisions.md` z datą i liczbą żądań:

- **pomiar 21** — blokada sieci w testach działa i sięga gniazda, nie tylko transportu `httpx`;
- **pomiar 1** — FTP UZP nie odpowiada (kontrola: `ftp.gnu.org` z tej samej maszyny działa);
- **pomiar 14** — dla `orzeczenia.uzp.gov.pl` nie ma warunków ponownego wykorzystywania ani
  informacji o ich braku; licencja CC BY-SA 4.0 z gov.pl jest zakreślona domeną `www.gov.pl`.

Wszystko pozostałe o źródłach pochodzi z lektury cudzych repozytoriów i dokumentacji. Kontrakt
`POST /Home/GetResults` stoi na dwóch niezależnych cudzych kolektorach — **własnego POST-a nikt
tu jeszcze nie wysłał**. Dostęp do Dump API SAOS jest nieprzetestowany, a od niego wisi
jedenaście lat materiału, bo pomiar 1 zamknął drogę przez FTP.

## Doktryna — cztery zasady, które nadpisują odruchy

Pełne brzmienie w audycie 7; tu jest to, co zmienia sposób pracy.

**Liczba bez źródła i daty jest w dokumentach tego projektu błędem, nie skrótem.** Zapis ma
postać „zmierzone 2026-09-15, 4 żądania" albo „z dokumentacji cudzej, data X". Ostrzejsza
wersja dotyczy materiału: sygnatury, nazwy własne i treść przepisów bierz z odczytu z datą.
Sygnatura `KIO 1234/25` wygląda tak samo niezależnie od tego, czy istnieje, a zdanie „Izba
wskazała, że…" brzmi wiarygodnie niezależnie od tego, czy Izba tak wskazała — więc jedno
ogniwo streszczenia za dużo produkuje zdanie prawdziwie wyglądające i fałszywe.

**Cisza jest usterką.** Przy każdym zabezpieczeniu warto zadać pytanie: co by się wypisało,
gdyby zostało naruszone? Jeśli uczciwa odpowiedź brzmi „nic", to jest usterka, a nie
zabezpieczenie. Puls długiej operacji liczy się w żądaniach wysłanych albo dokumentach
zapisanych, nigdy w stronach wyników.

**Dowód sanityzuje się dokładnie z tego, co ważne.** Sprawdzaj generator materiału testowego,
a nie tylko sam materiał. Słownik przepisów, haseł czy rozstrzygnięć ma być generowany ze
źródła z zapisanym SHA-256 tego źródła.

## Reguły granic

Dwadzieścia dwie, w audycie 8.3 i architekturze 4.1. Nie trzeba ich pamiętać — pilnuje ich
`tests/test_boundaries.py` skanem AST i sprawdzeniami systemu plików, a plik niesie przy każdej
regule powód jej istnienia.

Jedna rzecz o kształcie tego skanu: przy pustych katalogach większość reguł przechodzi **pusto**
i to jest prawda o stanie projektu, nie luka. Ciężar dowodu niosą wtedy samosprawdzenia na
plikach podrzuconych w `tmp_path` oraz metatest wykrywający stan „reguła ma plik-właściciela,
a skan go nie obejmuje".

Gdy skan zapali się na czerwono, lekarstwem jest przeniesienie napisu do `contract.yaml` albo
poprawka kodu. Lista wyjątków jest miejscem, w którym reguła cicho przestaje obowiązywać, więc
dopisanie do niej wymaga decyzji zapisanej w ADR, a nie komentarza w teście.

## Praca z kodem

```
.venv\Scripts\python.exe -m pytest        # 302 testy, --block-network z konfiguracji
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format .
.venv\Scripts\mypy.exe kio_tool scripts   # strict
```

Katalog `docs/` jest wyłączony z `ruff format`, bo ruff formatuje bloki kodu Pythona osadzone
w markdown — przy pierwszym uruchomieniu przeformatował dokument decyzyjny. Wykluczenie ma
`force-exclude = true`, więc obowiązuje także przy podaniu ścieżki wprost; samo
`extend-exclude` broniło tylko przed `ruff format .`.

Python 3.12.10; `requires-python = ">=3.12"`, bo na 3.11 nic w tym projekcie nie zostało
uruchomione, a deklaracja bez uruchomienia jest obietnicą bez pokrycia.

Komentarze przeniesione z `ceidg-tool` niosą powody konkretnych awarii z datami — przy
przenoszeniu kolejnych modułów warto je zachować razem z kodem. Kilka modułów odbiega przy tym
od wzorca świadomie i każde odstępstwo jest opisane w nagłówku pliku: `httpclient` (jeden stos
HTTP zamiast dwóch, `user_agent` jako parametr wymagany), `safetext` (C1, DEL i znaki
dwukierunkowe), `ratelimit` (odstęp wymagany zamiast okien, margines granicy okna, przycięcie
budżetu), `config` (brak wzorców kształtu sekretów, bo formatu klucza nikt tu nie widział),
`richtext` (kolejność maskowania, konsola bez znaczników).

Poprawkę w module o charakterze zabezpieczenia warto sprawdzić mutacją — psując produkcję
i patrząc, czy test się zapala. Dwa razy w tej sesji luka przechodziła przez całą zieloną
suitę i pokazała ją dopiero mutacja: odwrócona kolejność maskowania i normalizacji
w `richtext.safe` oraz `max(cooldown, retry_after)` w `ratelimit.note_response`.

## Żądania do cudzych serwisów

Dwie rzeczy różnią ten projekt od zwykłego klienta HTTP.

**Narzędzie nie omija zabezpieczeń.** Przy odmowie serwisu — CAPTCHA, wykrycie bota, blokada —
zatrzymuje się i mówi o tym operatorowi. Granica jest prawna, nie estetyczna (art. 267 § 1 k.k.).
Z tego samego powodu klient przedstawia się własnym `User-Agent` z adresem kontaktowym i nie
startuje bez zmiennej `KIO_TOOL_CONTACT`; adres jest po to, żeby operator serwisu miał jak
napisać, gdy coś pójdzie nie tak.

**Zgoda właściciela obowiązuje w sesji, w której padła.** Przebieg masowy i pomiar tempa
wymagają jej wprost; pojedynczy odczyt diagnostyczny nie, ale zostawia wpis w dzienniku. Zgoda
z poprzedniej sesji nie jest zgodą — dlatego nie da się jej zapisać w konfiguracji.

Sonda fazy 0: `.venv\Scripts\python.exe scripts\sonda.py --lista`.
