# kio-tool — konfiguracja projektu

Lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej. Nowe repozytorium,
wzorce przeniesione z sąsiedniego `..\Ceidg` (`ceidg-tool`) bez wspólnej biblioteki.

## Stan na 2026-09-20 — fazy 2 i 3 przyjęte, ruszyła lista odłożonych

PR #1 scalony do `master`. Praca idzie dalej z listy „Świadomie odłożone" w `docs/decisions.md`
(O-1…O-7) — **przeczytaj ją, zanim cokolwiek zaczniesz**; pozycja stamtąd nie jest do zrobienia
przy okazji.

**O-4 zamknięte — złoty zbiór niesie cytowania i przepisy.** Adnotacja ma trzy granulacje
i każda odpowiada temu, co objął przegląd okiem: sekcje i cytowania **per wystąpienie**, przepisy
**per postać z liczbą**. Przegląd znalazł dwie usterki oznaczania ustawy, których automat nie
mógł zapalić, bo dawały wartości poprawne co do typu (`rozporzadzenie` zamiast Pzp, `inne`
zamiast `pzp2004`) — wersja odczytu **6**, 260 przepisów przeniesionych na właściwą ustawę.
**Właściciel potwierdził ten przegląd 2026-09-20**, więc `przeglad.kto` niesie jedno zdanie
i cała adnotacja jest potwierdzona, nie tylko granice sekcji.

**O-3 zamknięte — pomiar 25 (`decisions.md`).** Wersja odczytu **5**; nierozpoznanych
cytowań 78 → 23 (4,6 % → 1,3 %). Wdrożone sześć rodzin postaci: `KIO/KD`, `KIO/W`, `KIO/582/11`,
rok czterocyfrowy przy KIO, sądy administracyjne z kodem siedziby i Zespół Arbitrów UZP. Doszły
rodzaje `wsa` i `uzp_zo`. Trzy rzeczy, które ten pomiar ustalił na przyszłość: repertorium
**zostaje** w sygnaturze (`KIO/KD 3/10` ≠ `KIO 3/10`), rok czterocyfrowy jest skracany, a nie
odrzucany, i **tolerancja składni wymaga przeliczenia całego korpusu** — myślnik w sygnaturze
TSUE wyglądał na zbędny, a jego zdjęcie dało 3 trafienia poprawne i 12 fałszywych (klasy betonu
`C30/37`, numery Dz.U. UE serii C). Największa rodzina, „sam numer bez repertorium" (29 trafień), dostała
**własny rodzaj** `kio_bez_repertorium` (decyzja właściciela): sygnatura kanoniczna jest pełna,
a to, że organ dopisaliśmy z kontekstu, niesie rodzaj. Wzorzec sam numer wolno wołać **wyłącznie
zza zapowiedzi** `sygn. akt` — puszczony po tekście łapie numery stron i kwoty.

### Stan na 2026-09-20 — fazy 2 i 3 przyjęte, projekt domknięty przed prezentacją (`master`)

Właściciel przyjął fazy 2 i 3 i potwierdził złoty zbiór (`docs/decisions.md`, „Przyjęcie faz 2
i 3"). Przejście operatora na pokazie wykonane, trzy zgłoszone usterki interfejsu naprawione
przed przyjęciem (ADR-0008 §13). **Faza 4 stoi za bramką warunkową i jest nietknięta.**

Sześć commitów z pracy nad odłożonymi pozycjami jest **scalonych lokalnie do `master`**; PR #2
zamknięty bez scalania, bo niósł stan sprzed nich (`decisions.md`, „Domknięcie projektu przed
prezentacją"). **Nic nie wysyłamy bez wyraźnej prośby właściciela** — to zasada, nie stan
przejściowy. Otwarte zostają O-1, O-2, O-5 i O-7; żadna z nich nie blokuje przekazania.

**Zanim cokolwiek dopiszesz: `docs/decisions.md`, sekcja „Świadomie odłożone"** — siedem pozycji
(O-1…O-7) z powodem odłożenia i z tym, co każdą odblokuje. Pozycja stamtąd nie jest do zrobienia
przy okazji.

**Asystenta językowego nie będzie — decyzja właściciela z 2026-09-20, nie odłożenie.** O-6 jest
zamknięte odmownie, więc **nie proponuj go ponownie i nie wprowadzaj SDK modelu do tego drzewa**;
konsekwencją jest brak drugiego właściciela klienta HTTP, drugiego wyjścia z procesu i łańcucha
poświadczeń, a przez to zdanie „narzędzie nie wysyła żądań poza kanał, z którego pobiera" bez
wyjątku i bez flagi. Bramka AI Act przed fazą 4 stoi mimo to, bo serwer MCP (`ARCHITEKTURA` §3.8 —
taki jest kształt fazy 4, nie asystent w procesie) oddaje tekst modelowi po drugiej stronie.

**Kreator mówi operatorowi, co robić** (zgłoszenie z 2026-09-20): każde pytanie tekstowe ma
podpowiedź (`Pytanie.podpowiedz` — strażnikiem jest test, który nie przepuszcza pytania bez niej),
pozycje menu niosą liczbę orzeczeń i informację, czy kosztują żądania, a pierwszy ekran pokazuje
stan korpusu i cztery zdania o obsłudze (`texts.JAK_TO_DZIALA`). Listy wyboru: **bez `default=`**,
domyślna opcja na czele, jawny styl `reverse bold`; pytania tak/nie **nie** przez
`questionary.confirm`. Powody w docstringu `ui/prompts.py` — oba defekty kosztowały już raz
w `ceidg-tool`.

### Stan na 2026-09-20 (przegląd kodu fazy 3)

**Przegląd kodu fazy 3 wykonany** (`decisions.md`, „Przegląd kodu fazy 3"); wszystkie znaleziska
naniesione. Co zmienia zastane odruchy:

- **Zgoda ma sufit, nie wyłącznik** (ADR-0008 §12.1). Werdykt `zgoda` wiąże przebieg z liczbą
  z tabeli kosztów: `(wycena + już wysłane) × proby` z bloku `ponowienia`. Dotyczy **także**
  `--zgoda` na ścieżce flag. Przekroczenie = przebieg `przerwany` ze zdaniem, wznowienie liczy
  koszt od nowa. Zmierzone przed naprawą: 103 żądania po Enterze pod tabelą mówiącą „5".
- **`PARSE_VERSION` ma 3 i ma obserwatora.** `tests/test_wersja_odczytu.py` trzyma odcisk
  SHA-256 źródeł odczytu (`parser/`, `docid.py`, `odczyt.py`); zmiana bez podniesienia wersji
  zapala test. Korpus operatora przeliczony (443 wersje, 0 żądań), raport
  `docs/raporty/pokrycie_2026-09-20.*`.
- **Sufit 800 linii ma strażnika** (`test_boundaries.py`): `store.py` (1 466) i `pipeline.py`
  (971) mają wpis z pomiarem i **nie mają prawa urosnąć**; nowy moduł ponad sufitem zapala test.
  Rozbicie obu to dług fazy 4.
- Arkusz `Metadane` eksportu pokazowego nie przypisuje już rekordów KIO ani Atlasowi; numer
  sprawy połączonej w korpusie pokazowym pochodzi z puli wolnych numerów.

Bramka fazy 3 §10 pkt 4 dostała obserwatora dopiero teraz — `pobierz` z flag drukował tabelę
kosztów, ale żaden test tego nie oglądał.

### Stan na 2026-09-19 (gałąź `feat/finalizacja-faz-2-3`)

**ADR-0006, ADR-0007 i ADR-0008 przyjęte 2026-09-19; fazy 2 i 3 zbudowane, czekają na przyjęcie
właściciela** (fazę kończy przyjęcie, nie zielona suita). Co jest nowe, w kolejności warstw:

- **ADR-0007 (ponowienia):** pętla prób w `AtlasChannel._zadanie`, liczby w bloku `ponowienia`
  kontraktu (z `retry_after_max_s`), zgoda liczona w żądaniach **wysłanych** i sprawdzana przed
  każdym ponowieniem, `requests_log.proba` (schemat 5).
- **Faza 2 (ADR-0006):** `parser/{clean,sections,cite,provisions}.py`, `odczyt.py` (parser →
  wiersze magazynu), schemat 6 (`sections`, `citations`, `provisions` — offsety w oryginale,
  `zrodlo` `tresc|kanal`, przepis z ustawą z treści, nigdy z daty), `PARSE_VERSION` 2 (dziś 3),
  `pokrycie.py` + polecenie `pokrycie` (raport w `docs/raporty/`, `--zloty` z kodem 1 przy
  rozbieżności), złoty zbiór `tests/gold/` — **wyłącznie sekcje**, 17 dokumentów (ADR-0006 §10.1).
- **Faza 3 (ADR-0008):** `wycena.py` + `Decyzja` w punkcie zgody (tabela kosztów bez dodatkowego
  żądania), `ui/{prompts,flow,wizard}.py`, `obsluga.py` (`AkcjeKreatora`, wydruki wspólne; objęty
  skanem reguły 9), `kio-tool` bez polecenia na terminalu = kreator; `demo/` (korpus generowany,
  atrapa Atlasu jako transport, `ZegarDemo`), `kio-tool demo`, znacznik bazy pokazowej
  (`PRAGMA application_id`) i znaczniki eksportu (`DEMO_`, `tryb`, `ATRYBUCJA_POKAZU`).

**Korpus operatora na tej maszynie** (odtworzony 2026-09-19, Przebieg 3): 443 dokumenty —
styczeń i 1–5 lutego 2024 plus próbka po 6 z każdego rocznika 2010–2026; schemat 6. Kopia sprzed
schematu 6 leży obok bazy (`korpus.sqlite.przed-schematem-6-20260919`).

**Otwarte, do decyzji albo ręki właściciela:** przyjęcie faz 2 i 3; potwierdzenie złotego zbioru
(przejrzał Claude, pole `przeglad.kto`); przejście operatora na pokazie (ADR-0008 §10 pkt 5 —
właściciel sam); luka „`Retry-After` przy 5xx nie przeżywa `wznow`" (ADR-0007 §8.1); postaci
sygnatur nierozpoznane w pomiarze 22 (`KIO/KD`, rok czterocyfrowy przy KIO, sam numer).

#### Stan na 2026-09-18 (historia)

**Bramka fazy 0 zamknięta 2026-09-18: pomiary 3a i 23 wykonane (5 żądań), ADR-0004 i ADR-0001
przyjęte, pierwszym adapterem jest `atlas`. Bramka fazy 1 spełniona tego samego dnia:
pierwszy korpus — styczeń 2024, 295 orzeczeń, 302 żądania, przebieg przerwany na progu zgody
i wznowiony tym samym poleceniem, trzecie wywołanie bez jednego żądania za dokument
(`docs/decisions.md`, „Przebieg 1"). Etapy planu z 2026-09-18: I (sonda i pakiet), II (pomiary),
III (adapter, magazyn, potok, `pobierz`), IV (przebieg), V (zakres „jak `ceidg-tool`").**

**Etap V (2026-09-18, polecenie właściciela „pełne narzędzie jak `ceidg-tool` do 2026-09-21"):** `criteria.py`
(kryteria z flag, odcisk do wznowienia; nazwy parametrów Atlasu wyłącznie w `contract.yaml`,
`parametry_listy.filtry`), `parser/details.py` (metadane i treść z surowego JSON-u po `MapaPol`
z kontraktu), `store.py` w schemacie 3 (migracje z `PRAGMA user_version` 1 → 2 → 3 bez utraty danych:
`runs.kryteria`/`runs.fingerprint` z odciskiem dopisywanym starym przebiegom, `run_documents`,
`metadata`, FTS5 `fts`, `requests_log.retry_after_s` — prośba serwisu przeżywa wznowienie),
`exporter.py` (xlsx/csv/jsonl/md z atrybucją — reguła 15,
`tests/test_attribution.py`), `ui/render.py` (`ConsoleView`), `console.py` na konsoli `rich`.
Polecenia: `pobierz`, `wznow`, `eksportuj`, `runy`, `przelicz`, `szukaj` (`--help` każdego).

Istnieje warstwa infrastruktury i producent tożsamości: `clock`, `safetext`, `errors`,
`config`, `richtext`, `progress`, `httpclient`, `docid`, `ratelimit`, a od 2026-09-18 także
`logbook` (ślad przebiegu: `Wynik`, `Kronika`, dziennik żądań, podsumowanie), `console`
(`PulsKonsoli`) i `ksztalt` (ocena kształtu odpowiedzi) — trzynaście plików, 2 179 linii
z `__init__.py` (zmierzone 2026-09-18 po etapie I planu). Sonda fazy 0 to dyspozytor
`scripts/sonda.py` (pomiar 3a: lista i jeden dokument Atlasu), środowisko żądania
`scripts/zadanie.py`, pomiary per kanał `scripts/pomiar_{uzp,saos,licencje}.py` i oczekiwania
`scripts/ksztalty.py` — 1 312 linii w sześciu plikach. Po etapach III–V i testach
odpornościowych pakiet ma 29 plików `*.py` i 6 861 linii (z `source/`, `parser/`, `ui/`),
a testów jest 1066 w 34 plikach (zmierzone 2026-09-18 w nocy; piaskownica w `conftest.py`
przekierowuje bazę i katalog wyjścia do `tmp_path` i porównuje stan prawdziwych ścieżek przed
i po — bo testy etapu V zdążyły zapisać 24 pliki do prawdziwego `wyniki/`). Testy odporności
`tests/test_odpornosc_*.py` (zanik sieci, 429/5xx/404, urwany JSON, ubicie procesu
`TerminateProcess` w trakcie zapisu, pełny dysk, cel zajęty) i ścieżki laika
`tests/test_uzytkownik_*.py` powstały 2026-09-18 wieczorem; osiemnaście znalezisk naprawiono tego
samego dnia — najważniejsze: przebieg `w_toku` bez procesu jest osierocony i wznawialny
(`store.STATUSY_WZNAWIALNE`), każdy `sqlite3.Error` wychodzi jako `StoreError` ze zdaniem
(`store._Polaczenie`), 404 na dokumencie jest liczony i pomijany (z sufitem
`pipeline.PROG_404_POD_RZAD`), JSON urwany przy 200 jest awarią przejściową
(`ksztalt.wyglada_na_urwana`), eksport `md` podmienia katalog w całości i tylko własny (znacznik
`exporter.PLIK_ZNACZNIKA`, bo NTFS składa wielkość liter i `INDEX.md` nim nie był). Przegląd kodu
tego wieczoru domknął jeszcze: `_Polaczenie.wycofaj` (nieudany `ROLLBACK` nie zastępuje
`KeyboardInterrupt`), `wznow --run-id` dla przebiegu `blad` (automat go nie podejmuje), kod 3 dla
złej `--baza` i niedodatniego `--limit`, zamknięcie połączenia po nieudanej migracji.

Sonda wymaga adresu w `KIO_TOOL_CONTACT` — bez niego `config.user_agent()` odmawia startu i to
jest zamierzone (reguła 16; właściciel 2026-09-18 potwierdził, że wymóg zostaje, i podał adres).
Adres idzie wyłącznie do nagłówka `User-Agent`; nie zapisuje się go w repozytorium. Zgoda
właściciela z 2026-09-18 objęła odczyty diagnostyczne (wykonane) i przebieg miesięczny
(~360 żądań) po zbudowaniu adaptera; zgoda obowiązuje w sesji, w której padła.

**Nie istnieje** — i to jest stan zamierzony, nie niedokończony: `mcp_server.py` (bramka
ADR-0002), `dictionaries.py` (ADR-0006 Z-13), `aktualizuj`, `porownaj`, `cytowania`, `slowniki`,
kanały `uzp` i `saos`. Katalog `tests/cassettes` stoi pusty z `.gitkeep`;
`tests/queries/` ma od 2026-09-17 szkielet, od 2026-09-18 poza ścieżką krytyczną (ADR-0005 Z-9).
Bramka fazy 0 mówi od 2026-09-18: kanał obecny w `source/` musi mieć wiersz zmierzony
w ADR-0004, a wejściem bramki są pomiary z pola `pomiary:` jego `contract.yaml`.

Repozytorium **ma zdalne**: prywatne `P0w3r223/Kio` na GitHubie; praca idzie na gałęziach z PR-em
(wybór właściciela 2026-09-19). Decyzja C („bez zdalnego") opisuje dziś historię — dopisek w
`docs/decisions.md`. Korpus nadal leży poza repozytorium i na innej maszynie trzeba go odtworzyć.
Adres kontaktowy dla `KIO_TOOL_CONTACT` jest zmienną środowiskową **użytkownika** Windows — poza
repozytorium, zgodnie z regułą; nie pytaj o niego.

## Ścieżka bez korespondencji — trzy decyzje z 2026-09-17

Właściciel rozstrzygnął, że projekt **nie prowadzi korespondencji**: nie idzie wniosek do UZP
z art. 39, nie idą pytania do prawnika, nie idzie mail do Atlasu. Pełny zapis razem z ceną
każdej decyzji stoi w `docs/decisions.md`; tu jest to, co zmienia sposób pracy.

**Nie pytaj, czy wysłać pismo, i nie planuj wokół odpowiedzi.** Projekty pism zostają
w `docs/pisma/` nienaruszone — są gotowe, gdyby decyzja się zmieniła — ale żaden plan na nich
nie wisi. Pomiar 15 jest zamknięty, pomiar 3b mierzy się wyłącznie obserwacją w czasie.

**UZP nigdy nie pełni roli kanału masowego** (reguła 23, strażnik w `test_boundaries.py`).
Pobranie całości idzie wyłącznie z kanału, który ponowne wykorzystywanie licencjonuje wprost —
dla UZP zostają weryfikacja na próbce i dopływ bieżący. Ta reguła **zastępuje pytanie 2 do
prawnika**, którego nikt nie zada: pytanie brzmiało „czy wolno pobrać istotną część cudzej
bazy", a odpowiedź brzmi „nie pobieramy istotnej części tej bazy".

Stąd **pomiar 23**: warunki reuse SAOS i Atlasu odczytane u źródła, tą samą metodą i tą samą
listą markerów co pomiar 14 — bo tylko wtedy wyniki wolno ze sobą zestawić. Licencja odczytana
u dostawcy z datą i SHA-256 jest mocniejszą podstawą niż cudza interpretacja przepisu, ale
**nie jest opinią prawną i nie udaje jej**. Ryzyko resztkowe jest przyjęte przez właściciela.

## Gdzie czego szukać

| Plik | Co niesie |
|---|---|
| `docs/AUDYT_KIO_ORZECZENIA.md` | stan źródła, dopuszczalność, build-vs-buy, doktryna (7), reguły granic (8.3), miny (11), pomiary fazy 0 (10) |
| `docs/ARCHITEKTURA_KIO_TOOL.md` | przegląd cudzych narzędzi (3), architektura (4), polecenia (5), pomiary (6), decyzje właściciela (8) |
| `docs/decisions.md` | **wyniki pomiarów z datami** — zbiorczy zapis tego, co ten projekt sam zmierzył |
| `docs/decisions.md`, sekcja „Status pomiarów" | **status każdego pomiaru** (wykonany / niewykonany / zamknięty / odłożony) i do czego jest wejściem — od 2026-09-18 w tym samym pliku co wyniki (ADR-0005 scalił `pomiary.md`, bo dwie listy wymagały strażnika symetrii) |
| `docs/adr/0005_bramka_per_kanal.md` | **przyjęty 2026-09-18**: bramka fazy 0 per kanał (wejście z `contract.yaml`), trzecia postać domknięcia wiersza, `atlas` pierwszy bezwarunkowo, reguła 19 na wyjściu z kanału, ADR-0001 bez pomiaru 19 |
| `docs/dziennik_zadan.md` | ślad po każdym żądaniu, w kolumnach `requests_log`; dwie sekcje — wpisy ręczne i maszynowe; powstaje przy pierwszym przebiegu sondy |
| `tests/test_bramki_faz.py` | **mechaniczni strażnicy bramek planu faz**: kod, który wolno napisać dopiero po ADR-ze, nie powstaje przed nim; ADR ogłoszony jako przyjęty ma wypełnione to, czego od siebie wymaga |
| `docs/adr/` | ADR-0003 (kształt `source/`, bramka wyjścia) — przyjęty; ADR-0004 (wybór kanału) — **artefakt bramki fazy 0**, od 2026-09-18 w brzmieniu per kanał: wejście z `contract.yaml` (3), trzy postaci domknięcia wiersza (4.2), `atlas` pierwszy bezwarunkowo (6), status `draft` do pomiarów 3a i 23; ADR-0001 (tożsamość dokumentu) — szkic z dwoma nawiasami do wypełnienia po pomiarze 3a, blokuje `store.py` |
| `docs/pisma/` | projekty pism do wysłania przez właściciela: wniosek do UZP, mail do Atlasu, pytania do prawnika |
| `tests/queries/` | szkielet zestawu zapytań operatora — praca domenowa właściciela, zero żądań; od 2026-09-18 poza ścieżką krytyczną (ADR-0005 Z-9), wraca w fazie 3 jako miara wyszukiwania |

Kolejność czytania dla nowej sesji: `docs/decisions.md` (wyniki i status pomiarów) → ADR-0005
(co zmieniło bramkę 2026-09-18) → ADR-0004 (co ją domyka) → audyt 14 (status dowodowy) →
audyt 13 (decyzje) → architektura 8 (decyzje właściciela).

## Co zmierzono, a co jest wciąż przypuszczeniem

Siedem pomiarów własnych, wszystkie w `docs/decisions.md` z datą i liczbą żądań:

- **pomiar 21** — blokada sieci w testach działa i sięga gniazda, nie tylko transportu `httpx`;
- **pomiar 1** — FTP UZP nie odpowiada (kontrola: `ftp.gnu.org` z tej samej maszyny działa);
- **pomiar 14** — dla `orzeczenia.uzp.gov.pl` nie ma warunków ponownego wykorzystywania ani
  informacji o ich braku; licencja CC BY-SA 4.0 z gov.pl jest zakreślona domeną `www.gov.pl`;
- **pomiar 3a** (2026-09-18, 2 żądania) — Atlas zwraca pełny tekst w `full_text` rekordu
  `GET /api/kio/{slug}`; lista `data[]` z `has_more`/`total` (29 580); `signatures` jako lista,
  `document_id` = identyfikator UZP, `updated_at`; slug `kio-<numer>-<rr>`; `ruling_date` bywa
  błędne (9 ze 100) — zbiór sięga co najmniej rocznika 2010, 2007–2009 niezmierzone;
- **pomiar 23** (2026-09-18, 3 żądania) — Atlas licencjonuje reuse wprost: CC BY 4.0
  z atrybucją „Źródło: Atlas Przetargów (https://atlasprzetargow.pl)", odczytane u dostawcy;
  korzeń SAOS nie odpowiedział w 45 s;
- **pomiar filtrów Atlasu** (2026-09-18, 6 żądań) — `outcome` zgodny z lokalnym rozstrzygnięciem
  (6 na 6 sygnatur), `search` dopasowuje sygnaturę, nie treść (słowo z treści daje 0, sygnatura
  daje 1); mina 2 audytu rozstrzygnięta;
- **przebieg 2** (2026-09-18, 48 żądań) — 1–5 lutego 2024, 46 orzeczeń; proces ubity
  `Stop-Process -Force` po 22 dokumentach i dokończony tym samym poleceniem jako osierocony
  (`docs/decisions.md`, „Przebieg 2"). Korpus: 341 orzeczeń.

Złote pliki z pomiaru 3a leżą w `tests/examples/atlas/` z `.compare.json` i `ZRODLO.md`.
Wszystko pozostałe o źródłach pochodzi z lektury cudzych repozytoriów i dokumentacji. Kontrakt
`POST /Home/GetResults` stoi na dwóch niezależnych cudzych kolektorach — **własnego POST-a nikt
tu jeszcze nie wysłał**. Dostęp do Dump API SAOS jest nieprzetestowany; korzeń SAOS nie
odpowiedział w pomiarze 23.

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

Dwadzieścia trzy, w audycie 8.3 (1–16) i architekturze 4.1 (17–23); numery czyta z tych sekcji
sam metatest, więc reguła dopisana do dokumentu zapala się bez niczyjej pamięci. Nie trzeba ich pamiętać — pilnuje ich
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
.venv\Scripts\python.exe -m pytest        # --block-network z konfiguracji; liczbę testów przelicz, nie przepisuj
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
i patrząc, czy test się zapala. Dwa razy w sesji 2026-09-15 luka przechodziła przez całą
zieloną suitę i pokazała ją dopiero mutacja: odwrócona kolejność maskowania i normalizacji
w `richtext.safe` oraz `max(cooldown, retry_after)` w `ratelimit.note_response`.

Sonda jest od 2026-09-18 podzielona po pojęciu i po kanale: `sonda.py` jest dyspozytorem i niesie
pomiar 3a (Atlas), `pomiar_uzp.py` / `pomiar_saos.py` / `pomiar_licencje.py` mówią, **co mierzymy**
na swoim kanale, `zadanie.py` daje jedno żądanie i środowisko (zegar, klient, limiter, kronika —
z jednego miejsca, żeby testy podstawiały je w jednym module), a `ksztalty.py` — **po czym poznać,
że odpowiedź jest tą, o której mówi kontrakt**. Każde oczekiwanie niesie tam swoje źródło
(`zrodlo`), bo „kontrakt z dwóch cudzych kolektorów" i „własny odczyt z datą" to dwa różne statusy
dowodowe i ich niezgodność znaczy co innego; fabryki oczekiwań mieszkają w `kio_tool/ksztalt.py`,
bo reguła 17 wymaga oceny kształtu od adaptera. Ślad przebiegu (`Wynik`, `Kronika` ze ścieżkami
jawnymi, dziennik dopisywany w chwili powrotu żądania) mieszka w `kio_tool/logbook.py`.
`scripts/` nie jest pakietem: `import zadanie` w sondzie działa, bo katalog skryptu wchodzi
na `sys.path` przy `python scripts\sonda.py`, a testom dokłada tę ścieżkę `tests/conftest.py`.
Piaskownica testów (`conftest.py`) przekierowuje zapis sondy do `tmp_path` **i porównuje stan
prawdziwych ścieżek przed i po** — mutacja, która ją wyłączyła, zapisała 2026-09-18 84 wiersze
z atrapy do prawdziwego dziennika; stąd `tests/test_piaskownica.py`.

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
