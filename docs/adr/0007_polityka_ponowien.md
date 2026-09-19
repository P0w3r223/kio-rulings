# ADR-0007: Polityka ponowień — pętla w kanale, postój przez limiter, liczby w kontrakcie

Data: 2026-09-19
Status: accepted (2026-09-19, decyzja właściciela — wariant Z-1, pomiar 24, Z-9 razem z resztą)
Autor: P0w3r223
Related to: `AUDYT_KIO_ORZECZENIA.md` (7.2 cisza jest usterką, 8.3 reguła 16), `ARCHITEKTURA_KIO_TOOL.md` (4.1 reguły 17 i 22, 4.3, 4.7), `docs/decisions.md` („Przebieg 1", „Przebieg 2", „Status pomiarów"), `docs/adr/0005_bramka_per_kanal.md`, `docs/adr/0006_parser_i_struktura.md` (oba powstały 2026-09-19; ten dokument dostał numer 0007, bo 0006 zajęła faza 2), `kio_tool/source/atlas/channel.py`, `kio_tool/ratelimit.py`, `kio_tool/logbook.py`, `kio_tool/errors.py`, `kio_tool/pipeline.py`, `kio_tool/store.py`, `tests/test_odpornosc_sieci.py`

---

## 1. Stan faktyczny — co dziś robi kod

Jedno żądanie kanału przechodzi przez jedną funkcję: `AtlasChannel._zadanie`. Tędy idą **oba**
punkty końcowe — strona listy i dokument. Tam stoi limiter, tam powstaje wiersz dziennika w chwili
powrotu żądania, tam zapada ocena kształtu i tam `_odrzuc_status` zamienia status na wyjątek.
Dziewięć zakończeń jednego żądania, zero ponowień:

| Co wraca | Gdzie rozstrzygane | Dziś |
|---|---|---|
| `httpx.HTTPError` (ConnectError, ReadTimeout, ConnectTimeout, RemoteProtocolError, PoolTimeout) | `_zadanie`, blok `except` | wiersz w dzienniku ze statusem `None`, `TransportError` → przebieg `przerwany` |
| 200, kształt zgodny | — | wynik |
| 200, ciało urwane albo puste (`ksztalt.wyglada_na_urwana`) | `_zadanie` | `TransportError` → `przerwany` |
| 200, kształt niezgodny z kontraktem | `_zadanie` | `SourceContractBroken`, kod 1 → `blad` |
| 5xx | `_odrzuc_status` | `ServerError` → `przerwany` |
| 429 | `_odrzuc_status`, **po** `note_response` | `RateLimitError` → `przerwany`; blokada limitera już ustawiona |
| 401 / 403 | `_odrzuc_status` | `AuthError`, kod 3 → `blad` |
| 400 | `_odrzuc_status` | `BadRequestError` → `blad` |
| 404 | `_odrzuc_status`, dalej `pipeline._przebieg` | dokument liczony i pomijany, sufit `PROG_404_POD_RZAD = 10` |

Trzy miejsca w drzewie opisują przy tym politykę, której nie ma:

- `errors.ServerError` — „5xx **po wyczerpaniu prób**";
- `errors.RateLimitError` — „429 mimo limitera — **po odczekaniu pełnej blokady** nadal odrzucane";
- `ratelimit.REASON_BACKOFF = "ponowienie"` w `WSZYSTKIE_POWODY`, z parametrem
  `acquire(extra_delay_s=…)` i testami (`tests/test_ratelimit.py`) — **bez jednego producenta
  w kodzie produkcyjnym**; `ratelimit.BUDGET_RESERVE_DEFAULT` mówi wprost „rezerwa zostaje na
  ponowienia, których jeszcze nie znamy".

Taksonomia wyjątków i limiter zostały napisane pod politykę ponowień. Adapter jej nie ma, więc dwa
z tych trzech zdań są dziś nieprawdziwe o własnym kodzie.

### 1.1 Czego nie zmierzono

`docs/decisions.md`: Przebieg 1 (2026-09-18, 302 żądania) i Przebieg 2 (2026-09-18, 48 żądań) —
**352 żądania, wszystkie ze statusem 200 i kształtem zgodnym**. Zero 5xx, zero zerwanych łączy,
zero 429. Jedyne przerwania, jakie ten projekt zmierzył, to przerwania **własne**: próg zgody
(Przebieg 1) i `Stop-Process -Force` (Przebieg 2). Awaryjność kanału, na którą ten ADR odpowiada,
**nie jest pomiarem** — jest oczekiwaniem.

Zasada 7.1 każe to napisać wprost, bo to zmienia kształt rozstrzygnięcia: polityka ma być
zachowawcza i ma **mierzyć samą siebie**, żeby pierwszy przebieg kwartalny zamienił oczekiwanie
w liczbę (Z-8).

### 1.2 Skala, do której polityka ma się skalować — projekcja, nie pomiar

Zmierzone: styczeń 2024 to 295 orzeczeń, 1–5 lutego 2024 to 46 (2026-09-18); cały zbiór Atlasu to
29 580 dokumentów (`total`, pomiar 3a). Z tego **projekcja**: kwartał ≈ 900 żądań, rocznik ≈ 3 600
(liczba właściciela z polecenia: ~4 300). Żadna z tych dwóch liczb nie jest pomiarem i tak ma być
czytana.

Druga liczba jest ważniejsza od awaryjności i wychodzi z `contract.yaml` bez żadnego żądania: okno
`{limit: 1400, sekund: 86400}` znaczy, że **rocznik nie mieści się w dobie**. Przy 4 300 żądaniach
to co najmniej cztery doby, a limiter między nimi stoi (`_next_slot`, gałąź `REASON_WINDOW`) —
przesypiając postój w plastrach po `WAIT_SLICE_S = 300` s. Przebieg roczny jest więc z definicji
ciągiem wznowień rozłożonym na kilka dni, niezależnie od tego, czy kanał się psuje. Ponowienia nie
usuwają z tego procesu człowieka; usuwają z niego **nieplanowane** wezwania człowieka.

---

## 2. Napięcie do rozstrzygnięcia: reguła 16 a `KODY_ODMOWY`

`_odrzuc_status` uzasadnia brak ponowień regułą 16 (audyt 8.3): „narzędzie nie omija zabezpieczeń.
Żadnego rozwiązywania CAPTCHA, rotacji identyfikatora klienta w celu ominięcia blokady, ani
**obchodzenia ograniczeń tempa** […] przy odmowie serwisu narzędzie zatrzymuje się i mówi o tym
operatorowi."

`logbook.KODY_ODMOWY = {401, 402, 403, 407, 429}` rozdziela to inaczej: „kody, przy których serwis
mówi »nie tobie« **albo »nie teraz«**", a 5xx jest poza zbiorem, bo „pierwsze powtarza się za jakiś
czas, drugie wymaga pisma albo klucza".

**Rozstrzygnięcie: oba zdania są prawdziwe i mówią o dwóch różnych pytaniach.**

1. `KODY_ODMOWY` odpowiada na pytanie **„czy serwis odmówił temu żądaniu"** i jest używane wyłącznie
   przez `Wynik.odmowa` / `Wynik.odmowa_serwisu`, czyli przez sondę, do decyzji „czy zatrzymać grupę
   pomiarów". To nie jest polityka ponowień i ten ADR jej nie rusza. Ujawnia natomiast, że zbiór
   skleja dwie semantyki, które jego własny docstring nazywa osobno: „nie tobie" (401, 402, 403,
   407 — wymaga klucza albo pisma) i „nie teraz" (429 — powtarza się za jakiś czas). Zdanie
   uzasadniające pokrywa tylko pierwszą.
2. Reguła 16 zabrania **obejścia**, a nie powtórzenia. Trzy wymienione w niej czyny mają jedną cechę
   wspólną: każdy pokonuje zabezpieczenie, nie poddając się mu. Ponowienie, które przechodzi przez
   limiter, **nie może pokonać niczego** — i to jest własność konstrukcji, nie obietnica:
   - `RateLimiter._next_slot` liczy `earliest` jako **maksimum** po odstępie, oknach, blokadzie po
     429, budżecie z nagłówków, wznowieniu i backoffie. `extra_delay_s` może postój wyłącznie
     wydłużyć;
   - `note_response(429, retry_after_s)` ustawia blokadę `max(cooldown_s, Retry-After)` **zanim**
     cokolwiek zdąży zapytać o ponowienie, a ta sama blokada odtwarza się z historii żądań
     w następnym procesie (`_next_slot`, gałąź `status == 429`);
   - każde ponowienie liczy się do okien tak samo jak żądanie pierwsze, bo `acquire` zapisuje je
     w historii. Ponowienie nie kupuje budżetu — **zużywa** go.

   Tożsamość klienta się nie zmienia (`User-Agent` z `KIO_TOOL_CONTACT`, reguła 16 jako własność
   `build_http_client`), tempo się nie zmienia, adres się nie zmienia.
3. Dlatego **429 wolno ponowić dokładnie raz, po odczekaniu pełnej blokady** — i to nie jest
   odwrócenie doktryny, tylko jej dosłowne wykonanie. Dowód jest operacyjny: to, co dziś robi
   operator po 429 (wpisuje `wznow`), wykonuje **tę samą blokadę** — `pipeline.pobierz` ładuje
   limiterowi historię z bazy (`store.request_stamps(nazwa, wall - DOBA_S)`) razem z kolumną
   `retry_after_s` dopisaną w schemacie 3 właśnie po to, żeby prośba serwisu przeżyła proces. Cudzy
   serwer widzi w obu wariantach **to samo**: jedno żądanie po upływie czasu, o który poprosił.
   Różnica jest wyłącznie w tym, czy ktoś musiał w nocy wstać i to wpisać.
4. Drugie 429 **pod rząd zatrzymuje przebieg**, bo znaczy co innego niż pierwsze: nasz model tempa
   jest błędny, a nie „serwis miał chwilę". Wtedy zatrzymanie z komunikatem do operatora jest
   dokładnie tym, czego żąda reguła 16 — i dopiero wtedy `RateLimitError` mówi prawdę o sobie
   („po odczekaniu pełnej blokady nadal odrzucane").

---

## 3. Rozstrzygnięcia

| # | Pozycja | Brzmienie | Powód |
|---|---|---|---|
| **Z-1** | Klasy ponawiane | Ponawiane są **cztery** klasy zakończenia żądania: `transport` (`httpx.HTTPError`), `urwana` (200 + `ksztalt.wyglada_na_urwana`), `serwis_5xx`, `odmowa_429`. **Nie są ponawiane:** 401/403, 400, 404, 200 o kształcie niezgodnym, `PagingRunawayError`, `UntrustedLinkError`, `LimiterStalledError`, `ConsentMissingError`, `KeyboardInterrupt` | Trzy pierwsze klasy to jedno zdarzenie widziane trzema drogami: zerwane łącze. `tests/test_odpornosc_sieci.py` mówi to wprost o klasie `urwana`: „tu przyszła ta sama, urwana (ponowienie da pełną odpowiedź)". Klasy nieponawiane są **trwałe do czasu poprawki w kodzie albo decyzji człowieka** — powód przy `SourceContractBroken` w `errors.py`: ponowienie ich nie naprawi, a cicha pętla ponowień to ta sama awaria co cicha pusta lista, widziana od strony cudzego serwera |
| **Z-2** | Ponawiane wyłącznie metody bezpieczne | Ponowienie dotyczy `GET`. Kanał, którego listowanie idzie `POST`-em (`uzp`: `POST /Home/GetResults`, architektura 4.3), nie dziedziczy tej polityki — wymaga własnego wiersza w tym ADR-ze | Dziś `channel.METODA = "GET"` dla obu punktów Atlasu, więc klauzula nic nie kosztuje. Kosztowałaby w dniu, w którym powstaje drugi kanał, a polityka jest już w kontrakcie wspólnym dla wszystkich |
| **Z-3** | Warstwa pętli | Pętla mieszka w **kanale**, w `_zadanie` (rozbitym na `_zadanie` z pętlą i `_jedna_proba` z dzisiejszym ciałem). `pipeline` nie ponawia niczego | Dwa powody, oba z drzewa. (1) Stan stronicowania listy (`strona`, `has_more`) żyje w generatorze `list_candidates`; `pipeline` widzi z niego tylko iterator, więc ponowienie na poziomie potoku obroniłoby `fetch`, a 5xx na siódmej stronie listy nadal zabijałoby przebieg. (2) Klasyfikacja zakończenia — wyjątek transportu, status, werdykt kształtu — zbiega się w `_zadanie` i w żadnym innym miejscu; pętla gdzie indziej musiałaby ją odtworzyć, czyli mieć drugą kopię reguły 17 |
| **Z-4** | Postój | Każda kolejna próba idzie przez `limiter.acquire(nazwa, extra_delay_s=…)`. Dla `serwis_5xx` z nagłówkiem `Retry-After` postój to `max(backoff, retry_after)`; dla `odmowa_429` backoff wynosi **0**, bo pełną blokadę trzyma już `note_response` | Limiter jest jedyną bramką, przez którą przechodzi każde żądanie, także ponowienie. Backoff podany osobno **nie może skrócić** żadnego innego hamulca, bo `_next_slot` bierze maksimum. Dla 429 doliczanie backoffu byłoby nadmiarowe i mylące w dzienniku. `Retry-After` przy 5xx jest dziś parsowany (`parse_retry_after` woła się przy każdej odpowiedzi), ale używany wyłącznie przy 429 — to jest luka i Z-4 ją zamyka, w tym samym kierunku co poprawka `max(cooldown, retry_after)` z 2026-09-15 |
| **Z-5** | Liczby | Polityka stoi w `contract.yaml` kanału, w **osobnym** bloku `ponowienia:` z własnym `zrodlo`, nie w `tempo:` i nie jako stała w `channel.py`. Model w `kio_tool/source/contract.py` | Reguła 17 czyni kontrakt jedynym miejscem, z którego adapter bierze tempo; precedens `strony.max_stron` i zawężonych `tempo.okna` pokazuje, że kontrakt już niesie **nasze** decyzje obok cudzych faktów. Blok jest osobny, bo `tempo.zrodlo` dokumentuje limity **odczytane u dostawcy**, a te liczby są progami tego projektu — wrzucone pod cudze `zrodlo` spłaszczyłyby dwa statusy dowodowe do jednego, czyli złamały zasadę 7.1 w pliku, który ją niesie. Per kanał, bo drugi kanał ma inny koszt ponowienia: UZP renderuje każdy dokument potokiem Word → HTML → wkhtmltopdf (audyt 2.2), więc tam ponowienie kosztuje cudzy serwer wielokrotnie więcej niż odczyt gotowego rekordu |
| **Z-6** | Sufit | `ponowienia.pod_rzad_max`: tyle **kolejnych** żądań wymagających ponowienia znaczy „serwis leży", nie „serwis mruga". Licznik zeruje pierwsze żądanie udane za pierwszym razem; przekroczenie kończy przebieg wyjątkiem klasy, która się wyczerpała | Idiom z drzewa: `pipeline.PROG_404_POD_RZAD` z licznikiem zerowanym przez pierwszy sukces. Absolutnego budżetu ponowień ten ADR **nie wprowadza** i to jest rozstrzygnięcie: górną granicę ruchu wyznacza już okno dobowe limitera, które liczy ponowienia identycznie jak dokumenty — przebieg nie może wydać na ponowienia więcej, niż ma na cokolwiek |
| **Z-7** | Widoczność — cztery ujścia, nie jedno | Każde ponowienie zostawia: (1) **własny wiersz** w `requests_log` — bo jest prawdziwym żądaniem do cudzego serwera; (2) `on_wait(sekundy, "ponowienie", moment)` — postój z powodem; (3) `on_message` nazywający punkt końcowy, przyczynę i numer próby („`dokument kio-115-24`: 503 od kanału, próba 2 z 3, czekam 2 s"); (4) liczbę w `Podsumowanie` na końcu przebiegu, czytaną **z bazy**, nie z pamięci procesu | Zasada 7.2: cisza jest usterką, a pytanie kontrolne brzmi „co by się wypisało, gdyby zabezpieczenie zostało naruszone". Ujścia (1) i (2) działają dziś bez zmiany: wiersz powstaje w `_zadanie` **przed** `_odrzuc_status`, a `console.PulsKonsoli.on_wait` drukuje powód dosłownie, więc stała `REASON_BACKOFF` dostaje wreszcie producenta. Ujście (3) jest nowe, bo napis „ponowienie" nie mówi, **co** się nie udało. Ujście (4) jest nowe i jest jednocześnie pomiarem — patrz Z-8 |
| **Z-8** | Pomiar 24 (numer do potwierdzenia przez właściciela) | Dziennik dostaje kolumnę `requests_log.proba` (numer próby, 1 = pierwsza) — migracja schematu. Pierwszy przebieg kwartalny po wdrożeniu raportuje do `docs/decisions.md` liczbę ponowień per klasa i skuteczność („ile ponowień skończyło się 200"). **Do czasu tego wpisu liczby z Z-5 są progami, nie ustaleniami** | Ten ADR odpowiada na awaryjność, której nikt nie zmierzył (§1.1). Polityka, która nie produkuje pomiaru samej siebie, zostawiłaby ten stan na zawsze. Bez kolumny `proba` dwie próby tego samego dokumentu są w dzienniku nie do odróżnienia od dwóch różnych żądań (kolumna `url_redacted` identyczna, różni się tylko `ts`) — czyli pomiaru nie dałoby się zrobić bez ponownego obciążenia serwisu. Precedens migracji: schemat 3 powstał dokładnie tym argumentem dla `retry_after_s` |
| **Z-9** | Zgoda liczona w żądaniach **wysłanych** | Próg zgody (`pipeline.PROG_ZGODY`) porównuje się z liczbą żądań, które opuściły proces — **łącznie z ponowieniami i łącznie z żądaniami, które nie dostały odpowiedzi**. Licznik przenosi się z `_Puls.on_request` do `_SladDoBazy.zanotuj` | Dziś `_Puls.on_request` liczy odpowiedzi, a nie żądania: na ścieżce wyjątku transportowego `_zadanie` zapisuje ślad i rzuca **przed** `on_request`, więc żądanie, które poszło do cudzego serwisu i nie wróciło, nie jest liczone do zgody. Bez ponowień ta różnica jest ograniczona, bo pierwszy wyjątek transportowy i tak kończy przebieg; z ponowieniami staje się nośna, bo przebieg mógłby wysłać ponad `PROG_ZGODY` żądań, nie pytając o zgodę ani razu. `_SladDoBazy.zanotuj` jest wołany dla **każdego** żądania, które opuściło proces, z odpowiedzią i bez |
| **Z-10** | Wyczerpanie prób nie zmienia niczego dalej | Po wyczerpaniu prób leci **ten sam wyjątek co dziś** (`TransportError`, `ServerError`, `RateLimitError`), przebieg zostaje `przerwany` z punktem kontrolnym, a `wznow` działa bez zmian | Ponowienia **zawężają** klasę przerwań wymagających człowieka; nie zastępują ścieżki wznowienia i nie wolno im jej osłabić. README obiecuje jedno zdanie o wznowieniu, a `tests/test_odpornosc_sieci.py` mierzy tę obietnicę rodzaj awarii po rodzaju — po tej zmianie ma mierzyć ją dalej, tyle że na awarii, która **nie ustępuje** |

### 3.1 Proponowany blok kontraktu (`kio_tool/source/atlas/contract.yaml`)

```yaml
ponowienia:
  klasy: [transport, urwana, serwis_5xx, odmowa_429]
  proby: 3            # 1 pierwsza + 2 ponowienia; dla `odmowa_429` patrz `proby_429`
  proby_429: 2        # 1 pierwsza + 1 ponowienie, po pełnej blokadzie limitera
  podstawa_s: 2.0     # postój przed próbą 2
  mnoznik: 3.0        # postój przed próbą 3 = podstawa_s * mnoznik
  pod_rzad_max: 3     # tyle kolejnych żądań z ponowieniem = serwis leży, nie mruga
  zrodlo: >-
    decyzja tego projektu (ADR-0007, 2026-09-19), nie odczyt u dostawcy. Liczby są progami,
    nie pomiarem — jak `pipeline.PROG_ZGODY` i `pipeline.PROG_404_POD_RZAD`. Wejściem do ich
    korekty jest pomiar 24 (Z-8): pierwszy przebieg kwartalny po wdrożeniu. Awaryjność kanału
    jest na 2026-09-19 niezmierzona: 352 żądania z 2026-09-18 wróciły ze statusem 200.
```

**Bez losowego rozrzutu (jitter) i to jest decyzja, nie przeoczenie.** Rozrzut służy rozkorelowaniu
wielu klientów uderzających w jeden serwis po wspólnej awarii. Tu klient jest jeden i odstęp
minimalny już go rozkorelowuje sam ze sobą, a niedeterminizm kosztowałby testowalność: testy
postojów czytają `ZegarTestowy.sleeps` co do wartości (`tests/test_pipeline.py`,
`tests/test_ratelimit.py`). Rozrzut wchodzi dopiero z drugim równoległym procesem, którego ten
projekt nie ma.

---

## 4. Warianty rozważone i odrzucone

| Wariant | Co daje | Dlaczego nie |
|---|---|---|
| **A. Zostawić bez ponowień** (stan dzisiejszy) | Zero kodu, zero ryzyka, reguła 16 w najostrzejszym czytaniu | Nie odpowiada na skalę: rocznik to ≥4 doby przebiegu (§1.2), a każda awaria przejściowa w tym czasie wymaga człowieka **w nieznanym momencie**. Koszt jest asymetryczny: jedno zerwane łącze kosztuje ponowną listę od punktu kontrolnego i obecność operatora, a ponowienie kosztuje jedno żądanie w tej samej kopercie tempa |
| **A′. Nadzorca zewnętrzny: harmonogram woła `wznow` po kodzie wyjścia 2** | Zero zmian w kodzie — taksonomia kodów wyjścia jest pod to napisana („2 = błąd wznawialny (harmonogram może ponowić)", `errors.py`); wznowienie jest tanie, bo dokumenty z bazy nie kosztują żądań | **Łamie regułę zgody.** Zgoda właściciela obowiązuje w sesji, w której padła, i dlatego nie da się jej zapisać w konfiguracji (`pipeline.pobierz`, parametr `zgoda`). Harmonogram wpisujący `--zgoda` produkuje zgodę, a nie ją wykonuje. Jeśli operator jest przy maszynie, żeby jej udzielić, to może równie dobrze wpisać `wznow` sam — czyli A′ zwija się do A. Zostaje jako droga dla przebiegów **nadzorowanych**, nie jako polityka |
| **B. Pętla w `pipeline` wokół `fetch`** | Ponowienia bez dotykania adaptera; `pipeline` i tak jest miejscem, gdzie mieszka sufit 404 | Nie obejmuje **stron listy** — stan stronicowania żyje w generatorze kanału (Z-3), więc 5xx na siódmej stronie nadal kończyłby przebieg. Wymaga też drugiej kopii klasyfikacji „co jest przejściowe" (werdykt kształtu powstaje w `_zadanie`), czyli drugiego miejsca do pogodzenia z regułą 17 |
| **C. Ponowienia w transporcie `httpx`** | Najmniej kodu | Przechodzi **obok limitera** — czyli obok jedynej bramki, która w tym projekcie gwarantuje tempo. Ponowienie niewidoczne dla `ratelimit` nie liczy się do okien i nie zostawia wiersza w `requests_log`: cisza w miejscu, w którym doktryna nazywa ciszę usterką, a jedyny obserwator tej zmiany to cudzy serwer. Odrzucone bezwarunkowo |
| **D. Ponowienia dla wszystkiego poza 401/403** | Prostsza reguła | 400 i niezgodny kształt są trwałe do poprawki w kodzie — `errors.SourceContractBroken` opisuje dokładnie tę pętlę jako awarię, nie lekarstwo |
| **E. 429 bez ponowienia, reszta ponawiana** | Najostrożniejsze czytanie reguły 16 | Do obrony i **warte decyzji właściciela**, ale kupuje mniej, niż się wydaje: limiter i tak trzyma pełną blokadę, a operator po 429 wpisuje `wznow`, który wykonuje tę samą blokadę z historii. Wariant różni się od Z-1 wyłącznie tym, kto wpisuje polecenie, a kosztuje obecność człowieka w nocy czwartej doby przebiegu rocznego |

---

## 5. Konsekwencje w drzewie

- `kio_tool/source/atlas/channel.py`: `_zadanie` rozbite na pętlę prób i `_jedna_proba` (dzisiejsze
  ciało, z `acquire` jako pierwszą linią). `_odrzuc_status` bez zmian — nadal rzuca; pętla łapie
  podzbiór z Z-1 i rozstrzyga o kolejnej próbie.
- `kio_tool/source/contract.py`: model `Ponowienia` i pole `Contract.ponowienia`. Schemat ma
  `extra="forbid"`, więc **każdy** kontrakt musi zadeklarować blok — dziś jest jeden.
- `kio_tool/source/atlas/contract.yaml`: blok z §3.1.
- `kio_tool/store.py`: migracja schematu, kolumna `requests_log.proba` (obecność sprawdzana, nie
  zakładana — jak w `_migruj_do_3`); `count_requests` uzupełniony o wariant liczący ponowienia.
- `kio_tool/pipeline.py`: licznik zgody przeniesiony do `_SladDoBazy.zanotuj` (Z-9); `Podsumowanie`
  o pole `ponowien`; `_SladDoBazy.zanotuj` przekazuje `proba` do `log_request`.
- `kio_tool/logbook.py`: `Wynik` o pole `proba` (domyślnie 1) i kolumna w dzienniku markdown.
  `KODY_ODMOWY` **bez zmian** — z dopiskiem, że odpowiada na inne pytanie niż polityka
  ponowień (§2 pkt 1).
- `kio_tool/errors.py`: docstringi `ServerError` i `RateLimitError` przestają być nieprawdziwe; bez
  zmiany kodów wyjścia.
- `kio_tool/ui/texts.py` + `ui/render.py`: zdanie dla operatora przy ponowieniu i liczba ponowień
  w podsumowaniu. Uwaga: pierwszy moduł sięgający po `WSZYSTKIE_POWODY` wchodzi pod
  `test_wyzwalacz_kazdy_konsument_zbioru_powodow_zna_wszystkie_powody` — wyzwalacz zapali się sam.
- `docs/decisions.md`: sekcja „Status pomiarów" o wiersz pomiaru 24 (Z-8).
- `ARCHITEKTURA_KIO_TOOL.md` 4.7: opis tempa kanału o zdanie o polityce ponowień.

### 5.1 Co się zepsuje w testach i dlaczego to jest zamierzone

`tests/test_odpornosc_sieci.py` — lista `AWARIE_PRZEJSCIOWE` (8 pozycji) w dwóch testach
parametryzowanych, czyli **16 przypadków** asertujących „jedna awaria → przebieg przerwany". Atrapa
psuje się po numerze **żądania** (`SerwisAwaryjny.__call__`: licznik `dokumentow` rośnie przy każdym
żądaniu o dokument, awaria pada przy `dokumentow == na_dokumencie`), więc po wdrożeniu ponowienie
byłoby żądaniem numer N+1 i skończyłoby się sukcesem — przebieg dochodziłby do końca i 16
przypadków zapaliłoby się na czerwono.

To jest właściwa reakcja, nie regresja: te testy mierzą dziś „awaria zdarzyła się raz", a mają
mierzyć „awaria **nie ustępuje**". Atrapa dostaje wybór awarii po **slugu** (albo licznik prób per
żądanie), a testy rozdzielają się na dwie rodziny: awaria trwała → przebieg `przerwany` i wznawialny
(dzisiejsze asercje bez zmian) oraz awaria jednorazowa → przebieg kończy się, w dzienniku są **dwa**
wiersze na ten sam dokument (`proba` 1 i 2), a na ekranie padło zdanie o ponowieniu.

`tests/test_pipeline.py::test_429_zatrzymuje_przebieg_i_zostawia_go_wznawialnym` **przechodzi bez
zmian** i to jest dobra wiadomość o Z-1: atrapa odpowiada 429 na każdy dokument od trzeciego w górę
(`odmowa_na_dokumencie` z porównaniem `>=`), więc ponowienie dostaje drugie 429 i przebieg staje —
dokładnie tak, jak opisuje `RateLimitError`.

---

## 6. Cena, wypisana wprost

- **Przebieg trwa dłużej, nigdy szybciej.** Ponowienie to dodatkowe żądanie w tej samej kopercie
  tempa: zużywa slot okna dobowego, którego rocznik i tak nie ma w nadmiarze (4 300 żądań wobec
  1 400 na dobę). W skrajnym przypadku ponowienia przesuwają koniec przebiegu o kolejną dobę.
- **Cudzy serwis dostaje więcej żądań.** Mniej, niż wygląda: górną granicą jest okno dobowe, a nie
  nasza dobra wola — ale to nadal są żądania wysłane do serwisu, który być może właśnie dlatego
  odpowiedział 5xx, że ma problem. Sufit `pod_rzad_max` jest jedynym mechanizmem, który odróżnia
  „mruga" od „leży", i jest **progiem, nie pomiarem**.
- **Liczby z §3.1 są zgadywane.** Trzy próby, 2 s i 6 s postoju, sufit 3 — żadna z tych wartości nie
  pochodzi z obserwacji tego kanału, bo obserwacja tego kanału to 352 odpowiedzi 200. Z-8 jest
  warunkiem, żeby ten stan się skończył; do tego czasu ADR świadomie stoi na oczekiwaniu.
- **Rośnie powierzchnia stanu w `_zadanie`.** Funkcja, która dziś robi jedną rzecz raz, zaczyna
  robić ją w pętli z licznikiem — a jest to funkcja, przez którą przechodzi każde żądanie projektu.
  Dlatego Z-3 rozbija ją na dwie, a nie dopisuje `while` do istniejącego ciała.
- **Migracja schematu bazy przy żywym korpusie** (341 dokumentów, 356 wierszy dziennika). Migracje
  1 → 2 → 3 → 4 przeszły bez utraty danych; kolejna ma ten sam kształt (`ALTER TABLE` po sprawdzeniu
  `PRAGMA table_info`), ale to nadal jest zapis do jedynego egzemplarza korpusu w repozytorium bez
  zdalnego (decyzja C).

---

## 7. Czego ten ADR nie rozstrzyga

- **`KODY_ODMOWY` zostaje w obecnym brzmieniu.** Ujawniona niespójność (zbiór skleja „nie tobie"
  z „nie teraz", a zdanie uzasadniające pokrywa tylko pierwszą) dotyczy sondy i nie ma dziś
  obserwowalnego skutku. Rozdzielenie zbioru na dwa to osobna, tania decyzja — ale wykonana przy
  okazji zmieniłaby zachowanie pomiarów per kanał bez pomiaru.
- **Przebieg wielodobowy a zgoda w sesji.** §1.2 pokazuje, że rocznik to ≥4 doby jednego procesu
  z postojami rzędu doby. Czy zgoda udzielona w chwili startu obejmuje żądania wysyłane czwartej
  doby — to jest pytanie do właściciela, **nie do tego ADR-a**, i jest ono niezależne od ponowień:
  postawiłoby się tak samo, gdyby kanał nie psuł się nigdy.
- **Polityka ponowień kanałów `uzp` i `saos`.** Z-2 i Z-5 zostawiają im własny wiersz; dla `uzp`
  koszt ponowienia po stronie serwisu jest jakościowo inny (render na żądanie, audyt 2.2), a rola
  masowa jest mu zakazana regułą 23.
- **Wycofanie żądania w locie** (limit czasu krótszy niż `DOMYSLNY_LIMIT_CZASU_S = 30`). Trzy próby
  po 30 s to 90 s na jeden dokument przy serwisie, który milczy; sufit `pod_rzad_max` to ogranicza,
  ale nie jest to strojenie limitu czasu. Wejściem do tej decyzji jest pomiar 9, zdjęty ze ścieżki
  krytycznej przez ADR-0005 Z-9.

---

## 8. Do decyzji właściciela

1. **Wariant Z-1 czy wariant E** — czy 429 dostaje jedno ponowienie po pełnej blokadzie (Z-1), czy
   zero (E). §2 broni Z-1 i pokazuje, że cudzy serwer widzi w obu wariantach to samo; E jest
   najostrożniejszym czytaniem reguły 16 i też jest do obrony. Różnica operacyjna: kto wpisuje
   polecenie w nocy czwartej doby przebiegu rocznego.
2. **Numer pomiaru z Z-8** — proponowany 24, pierwszy wolny w sekcji „Status pomiarów".
3. **Czy Z-9 wdrożyć osobno i wcześniej.** Poprawka licznika zgody jest logicznie niezależna od
   ponowień i dotyczy zabezpieczenia; dziś jej skutek jest ograniczony, bo pierwszy wyjątek
   transportowy kończy przebieg — ale jest warunkiem, żeby ponowienia nie rozszczelniły progu zgody.

### 8.1 Rozstrzygnięcie (2026-09-19)

Właściciel wybrał **wariant Z-1** (429 dostaje jedno ponowienie po pełnej blokadzie) i przyjął
numer **24** dla pomiaru z Z-8. Z-9 weszło w tym samym commicie co pętla — przed nią w kolejności
prac, nie osobnym wydaniem, bo drzewo nie było wydawane między jednym a drugim.

Dwa odstępstwa od §5, oba świadome:

- **Dziennik markdown sondy (`docs/dziennik_zadan.md`) nie dostaje kolumny `proba`.** Sonda nie
  ponawia, więc kolumna niosłaby wyłącznie jedynki, a dopisana do żywej tabeli rozjechałaby
  wiersze sprzed zmiany. `Wynik.proba` istnieje i idzie do `requests_log` (schemat 5).
- **§5.1 mylił się co do `test_429_zatrzymuje_przebieg_i_zostawia_go_wznawialnym`.** Test nie
  przeszedł bez zmian: przebieg nadal staje na `RateLimitError`, ale dziennik ma teraz **dwa**
  wiersze 429 (`proba` 1 i 2), a test liczył jeden. Asercja poprawiona na dokładną listę par
  (status, próba) — czyli mierzy teraz także to, że drugiego ponowienia nie było.
