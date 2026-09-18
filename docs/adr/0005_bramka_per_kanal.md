# ADR-0005: Bramka fazy 0 per kanał — pomiary tego kanału, który powstaje

Data: 2026-09-18
Status: accepted (2026-09-18, decyzja właściciela — podejście B z przeglądu architektonicznego tego dnia)
Autor: P0w3r223
Related to: `docs/adr/0004_wybor_kanalu.md`, `docs/adr/0003_ksztalt_source_i_bramka_wyjscia.md`, `docs/raport_przekazania.md` (sekcje 11.2 i 15), `docs/decisions.md` (sekcja „Status pomiarów"), `ARCHITEKTURA_KIO_TOOL.md` (4.1: reguły 17, 19, 20, 21), `tests/test_bramki_faz.py`

---

## 1. Kontekst: bramka, której wejście kosztuje minuty, a obudowa — dni

Stan drzewa 2026-09-18 rano, zmierzony `wc -l` i `pytest --collect-only`: 1 316 linii kodu
produkcyjnego w dziesięciu plikach (porty bez adapterów), 1 690 linii sondy, 8 635 linii testów
(574 testy), 3 702 linie dokumentacji — i **zero pobranych orzeczeń**. Z 574 testów 187 (33 %)
obserwuje zachowanie kodu produkcyjnego, 227 (40 %) skrypt diagnostyczny, który nigdy nie
został uruchomiony (`docs/dziennik_zadan.md` nie istnieje), a 160 (28 %) własne dokumenty
i puste katalogi.

Wejście bramki fazy 0 to ~9 żądań i jedna zmienna środowiskowa. Jej obudowa to sonda, testy
sondy, strażnik bramki, dokument bramki i osobna lista pomiarów. **Nikt nie wykonał wejścia ani
razu.** Projekt zoptymalizował procedurę decyzyjną, nie wykonując jej.

Mechanizm, nie wina: doktryna „gwarancja bez obserwatora nie jest gwarancją" (audyt 7.3),
przyłożona do kodu produkcyjnego, zwróciła się trzykrotnie (kolejność maskowania w `richtext.safe`,
`max(cooldown, retry_after)` w limiterze, siedem cichych mutacji strażników bramek). Przyłożona
do artefaktów **bez przedmiotu** — pustych katalogów i dokumentów o dokumentach — wchodzi
w pętlę: reguła → strażnik przechodzący pusto → samosprawdzenie na materiale podrzuconym →
metatest antypustkowy → … Każdy krok jest lokalnie uzasadniony i globalnie jałowy, a pętla ma
jedno wyjście: powstanie przedmiotu.

Do tego jedno spostrzeżenie, które zmienia wejście bramki. Po decyzjach A i B właściciela
(2026-09-17, `decisions.md`) **jedynym kandydatem na kanał masowy jest Atlas**: `uzp` jest
wykluczony w każdej gałęzi, a `saos` deklaruje zasięg do 2018-09, więc z definicji nie unosi
korpusu. Tymczasem kryterium wyjścia ADR-0004 żądało domknięcia wierszy `saos` i `uzp` przed
powstaniem `source/atlas/` — czyli pomiarów 2a/2b i 4b/16, pięciu żądań do dwóch cudzych
serwisów po odpowiedź, której żadna gałąź decyzji nie użyje. ADR-0004 sekcja 3 sam zakazuje tego
wzorca przy pomiarze 9 („obciążanie cudzej infrastruktury dla decyzji, która może nie zapaść").

Doktryna zostaje w całości. Zmienia się **przedmiot**, na którym pracuje — z dokumentów
i strażników strażników na bajty z cudzego serwisu.

---

## 2. Co ten ADR rozstrzyga

| # | Pozycja | Nowe brzmienie | Powód |
|---|---|---|---|
| **Z-1** | ADR-0004 §3, wejście bramki | Wejściem bramki są **pomiary kanału, który ten ADR wybiera jako pierwszy**. Lista stoi w `contract.yaml` tego kanału (pole `pomiary:`), nie w dokumencie — strażnik ją czyta, nie powtarza. Dla `atlas`: **3a** (lista i jeden dokument) i **23** | Pomiary 2a/2b i 4b/16 rozstrzygają o kanałach, które po decyzjach A/B nie mogą być pierwszym adapterem. Lista wejść była 2026-09-18 rano w dwóch miejscach (ADR-0004 §3 i `tests/test_bramki_faz.py`), które mówiły dwie rzeczy o pomiarze 23 |
| **Z-2** | ADR-0004 §4.2 i §5 pkt 2, domknięcie wierszy | Wiersz kanału **obecnego w `kio_tool/source/`** musi być zmierzony. Kanał bez adaptera domyka wiersz jedną z trzech postaci: zmierzony · odpada (powód, data) · **nierozstrzygnięty (data, powód odroczenia)** — i dwie ostatnie **zabraniają** powstania jego katalogu | Chroni tę samą własność co przedtem — „żaden adapter bez pomiaru" — implikacją drzewo → tabela (kierunek reguły 21), a przestaje chronić własności „żaden korpus, zanim nie zmierzysz wszystkich kandydatów", która nie ma obserwowalnej korzyści. **To nie jest powrót furtki usuniętej 2026-09-17**: tamta („otwarty warunkowo: wniosek złożony…") zamykała wiersz kanału, *który wolno było budować*; ta zamyka wiersz kanału, którego budować *nie wolno* |
| **Z-3** | ADR-0004 §6, pierwszy adapter | Bezwarunkowo **`atlas`**. `saos` → osobny ADR (odcinek 2007–2018) po bramce fazy 1; `uzp` → role weryfikacji i dopływu, faza 2 | Kryterium §6 („na którym kanale kształt `store.py` i adaptera może się iterować, nie obciążając cudzego serwera") rozstrzyga na korzyść Atlasu: limity publikowane (1500/dobę/IP, 5000 z kluczem, 500/min) i raportowane nagłówkami `X-RateLimit-*` (odczyt 2026-09-18); SAOS ma dostęp nieprzetestowany (403 na API wyszukiwania), zasięg z definicji niepełny, warunki reuse nieodczytane |
| **Z-4** | ADR-0001, wejścia | Rozstrzyga tożsamość **w kanale pierwszego zapisu**: postać `source_ref` z pomiaru 3a, `ref_case: preserve \| lower` deklarowane w `contract.yaml`, wielosygnaturowość. **Pomiary 19 i 7 stają się wejściem polityki wersji kanału `uzp`**, nie warunkiem `store.py`; pomiar 17 wykonuje się na rekordach z pomiaru 3a (sto rekordów listy) i z pierwszego przebiegu, zero żądań | Klucz `raw_versions (doc_id, content_sha256)` jest poprawny przy **obu** wynikach pomiaru 19: niestabilny render daje nadmiarowe wiersze wersji, czyli szum, nie utratę tożsamości. Mina 1 z CEIDG dotyczy wielkości liter w kluczu głównym — rozstrzyga ją `ref_case`, znany z pierwszej odpowiedzi. Bramka `store.py` → ADR-0001 bez zmian |
| **Z-5** | Reguła 19 (architektura 4.1) | Surowa odpowiedź zapisuje się **w całości**; `content_sha256` zgadza się z tym, co przyszło. Granica przebiega **na wyjściu z kanału**: pole o nieznanym pochodzeniu nie wchodzi do tabel pochodnych, wyszukiwania ani eksportu i stoi w `contract.yaml` jako `pola_odrzucone:` z powodem i datą. Jeśli kanał umie nie zwrócić pola (Atlas: `with_thesis`), adapter o nie nie prosi | Brzmienie „adapter Atlasu odrzuca pola `thesis*` na wejściu" kazało zmutować cudzą odpowiedź przed zapisem — wtedy skrót nie jest skrótem tego, co przyszło, a złoty plik z reguły 17 przestaje odpowiadać temu, co leży w bazie (przegląd 2026-09-18, F-2) |
| **Z-6** | Reguła 17 — dopisek | Złotym plikiem kanału jest **surowa odpowiedź zapisana przez pomiar wejściowy**, przeniesiona ze `scripts/out/` do `tests/examples/<kanał>/` razem z `ZRODLO.md` (licencja, data odczytu, SHA-256) | Zero dodatkowych żądań; atrybucja wymagana przez CC BY 4.0 leży przy bajtach |
| **Z-7** | Reguła 21 — doprecyzowanie | `protocol.py` i `contract.py` są w `source/` **dozwolone, nie wymagane**; skan wymaga `registry.py` i kompletu `__init__.py`/`channel.py`/`contract.yaml` | Skan (`test_boundaries.py`, `MODULY_WSPOLNE_SOURCE`) już tak działa; architektura 4.2 i ADR-0004 §6 czytały się, jakby komplet był warunkiem (F-17) |
| **Z-8** | `docs/pomiary.md` | **Wchłonięty** do `docs/decisions.md` jako sekcja „Status pomiarów". Plik usunięty. Strażnik symetrii (`statusy_pomiarow` i pięć testów w `test_bramki_faz.py`) usunięty | Dwie listy wymagające synchronizatora powinny być jedną listą. Usuwamy **potrzebę** strażnika, nie strażnika: status stoi obok wyniku w tym samym pliku |
| **Z-9** | Pomiar 9, `tests/queries/`, kolumna `capabilities()` | Zdjęte ze ścieżki krytycznej. Kolumnę `capabilities()` w ADR-0004 wypełnia udokumentowana lista filtrów (odczyt 2026-09-18); zestaw zapytań operatora wraca w fazie 3 jako miara wyszukiwania | Porównanie zdolności ma sens przy więcej niż jednym kandydacie; pomiar 9 jest zbędny dla kanału, który limity publikuje i raportuje nagłówkami |
| **Z-10** | Reguła 20, `pyproject.toml` | Pytanie „kasety vs wstrzyknięty transport" rozstrzyga **test dymny adaptera Atlasu** na złotym pliku przez `httpx.MockTransport` (parametr `transport=` w `build_http_client`), nie pomiar 4b. Jeśli wstrzyknięty transport wystarcza, `respx` wypada z zależności | Wiązanie z pomiarem 4b, którego ścieżka rekomendowana nie wykonuje (F-11) |

---

## 3. Czego ten ADR nie zmienia

Decyzji A/B/C (bez korespondencji, UZP nigdy masowo, bez zdalnego). Reguły 16 i wymogu
`KIO_TOOL_CONTACT` — właściciel rozstrzygnął 2026-09-18, że adres zostaje i że go poda. Reguł
1–16, 20, 21, 22, 23 w brzmieniu (poza dopiskami z Z-7 i Z-10). ADR-0003 w całości. Bramek
`store.py` → ADR-0001 i `mcp_server.py` → ADR-0002. Dziewięciu modułów infrastruktury.

Odłożone bez łamania doktryny: `parser/`, `exporter.py`, `mcp_server.py`, `criteria.py`, kreator
`ui/`, graf cytowań, FTS5, `porownaj`, trzy osie nowości, pomiary 2a/2b, 4b/16, 7, 9, 19,
`tests/queries/`.

---

## 4. Konsekwencje w drzewie

- `tests/test_bramki_faz.py`: kryterium wyjścia czyta kanały z drzewa (`kanaly_w_drzewie`)
  i pomiary z kontraktu (`pomiary_zadeklarowane`); trzecia postać domknięcia; strażnik symetrii
  usunięty; `NUMERY_ADR_OCZEKIWANE` zna `0005`.
- `docs/decisions.md`: sekcja „Status pomiarów" (dawny `pomiary.md`).
- `ARCHITEKTURA_KIO_TOOL.md` 4.1: reguły 17, 19, 20, 21 w brzmieniu z tabeli.
- ADR-0004: sekcje 3, 4.2, 5, 6 — status zostaje `draft`, dopóki pomiary 3a i 23 nie padną;
  przyjęcie zapisuje wiersz `atlas` zmierzony, a `saos` i `uzp` jako „nierozstrzygnięty".
- Sonda (I.1 planu, wykonane 2026-09-18 przed tym ADR-em): pomiar 3a wysyła drugie żądanie po
  dokument (`GET /api/kio/{slug}`), lista nazywa klucz `data`, pomiar 23 czyta także stronę
  dokumentacji Atlasu.

---

## 5. Cena, wypisana wprost

- **Kompletność pośrednika zostaje niepotwierdzona** do czasu `porownaj` (faza 2). Regulamin
  Atlasu mówi o braku gwarancji kompletności — to jest cena wyboru, zapisana w ADR-0004 §6.
- **Odcinek 2007–2018** nie ma rozstrzygniętej drogi: pomiar 3a (`sort=oldest`) powie, od kiedy
  sięga zbiór pośrednika; jeśli nie sięga 2007, wraca `saos` jako osobny ADR.
- **UZP w rolach weryfikacji i dopływu** wymaga pomiaru 4b — odłożonego, nie skasowanego.
- Kryterium wyjścia jest **węższe w zasięgu** (jeden kanał zamiast czterech) i **ściślejsze
  w kierunku** (kanał w drzewie musi być zmierzony). Rozluźnieniem byłoby dopiero pozwolenie,
  by kanał z wierszem „nierozstrzygnięty" miał katalog — i to jest dokładnie to, co strażnik
  zapala.
