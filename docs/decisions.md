# Dziennik pomiarów i decyzji

Data utworzenia: 2026-09-15
Status: żywy — dopisywany przy każdym pomiarze, nigdy przepisywany wstecz
Autor: P0w3r223
Related to: `AUDYT_KIO_ORZECZENIA.md` (sekcja 10), `ARCHITEKTURA_KIO_TOOL.md` (sekcja 6)

---

## Konwencja

Każdy wpis niesie **datę i sposób uzyskania**. „Zmierzone {data}, {N} żądań" znaczy własny
odczyt. „Policzone z pliku X, 0 żądań" znaczy rachunek lokalny. „Z dokumentacji cudzej,
data X" znaczy cudzy pomiar z podaną datą. Liczba bez daty i sposobu uzyskania jest w tym
pliku błędem, nie skrótem (zasada 7.1 audytu).

Wpis nie jest usuwany, gdy pomiar zostanie powtórzony — dopisuje się nowy. Widoczna zmiana
wyniku w czasie jest informacją o źródle.

---

## Pomiar 21 — czy blokada sieci w testach współistnieje z wstrzykniętym transportem httpx

**Zmierzone 2026-09-15, 0 żądań.** Wynik: **pozytywny dla `pytest-recording`.**

Żądanie zbudowane przez `kio_tool.httpclient.build_http_client` — czyli przez klienta, który
**zawsze** dostaje wstrzyknięty `AllowedHostsTransport` — zostało przy `addopts =
"--block-network"` zatrzymane wyjątkiem `RuntimeError("Network is disabled")`, a nie błędem
połączenia. Blokada widzi więc ruch mimo warstwy transportu, której architektura 3.4
obawiała się jako punktu rozjazdu z vcrpy.

Środowisko pomiaru: Python 3.12.10, httpx 0.28.1, pytest 9.1.1, pytest-recording 0.13.4,
Windows 11. Test: `tests/test_pomiar21_blokada_sieci.py`.

**Czego ten pomiar NIE rozstrzygnął.** Zablokowanie ruchu i **odtworzenie kasety** to dwa
różne mechanizmy, a zmierzona została tylko pierwsza połowa. Czy nagrana kaseta odtworzy się
przez ten sam wstrzyknięty transport, rozstrzygnie dopiero pierwsza prawdziwa kaseta, która
powstanie przy pomiarze 4b. Do tego czasu `respx` zostaje w zależnościach deweloperskich jako
druga droga; usunięcie go teraz byłoby zamknięciem pytania, które jest wciąż otwarte.

**Usterka po drodze, warta odnotowania.** Pierwsza wersja asercji sprawdzała **nazwę klasy**
wyjątku, a `pytest-recording` zgłasza blokadę jako zwykły `RuntimeError`. Test wyglądał więc
przez chwilę na wynik negatywny pomiaru, choć mechanizm działał. To jest w miniaturze zasada
7.3 zastosowana do samego testu: strażnik, który patrzy na niewłaściwą cechę, nie pilnuje
niczego. Poprawiona wersja sprawdza komunikat i osobno wyklucza `httpx.ConnectError`, czyli
wariant „żądanie jednak wyszło, a odbiła je dopiero sieć".

### Uzupełnienie tego samego dnia: czy blokada sięga poniżej httpx

**Zmierzone 2026-09-15, 0 żądań.** Wynik: **tak, blokada działa na poziomie gniazda.**

Pierwsza wersja tego pomiaru sprawdzała wyłącznie ruch idący przez `httpx`, a to jest połowa
pytania. Gdyby `--block-network` podmieniało tylko transport `httpx`, kanał spoza HTTP —
`ftplib`, `socket` wprost, `urllib` — przechodziłby przez blokadę **niewidziany**, a reguła 20
obejmowałaby tylko tę część ruchu, którą akurat widać.

`socket.create_connection(("127.0.0.1", 9))` pod `--block-network` kończy się tym samym
`RuntimeError("Network is disabled")`, co żądanie przez `httpx`. Blokada jest więc zamkiem na
gnieździe, nie na bibliotece.

Konsekwencja dla reguły 20: `pytest-recording` zamyka **blokadę** dla każdego protokołu,
niezależnie od tego, który kanał wygra po pomiarach 1–3. Otwarta zostaje wyłącznie druga
gwarancja — odtwarzanie **kaset** przez wstrzyknięty transport — którą rozstrzygnie pierwsza
prawdziwa kaseta przy pomiarze 4b. Dopóki nie padnie, `respx` zostaje w zależnościach.

Rozróżnienie „blokada" / „kasety" jako dwóch osobnych gwarancji pochodzi z przeglądu
architektonicznego 2026-09-15, nie z pierwotnego brzmienia pomiaru 21.

---

## Trzy pytania projektowe z przeglądu kodu — rozstrzygnięcia z 2026-09-15

Przegląd kodu wskazał trzy miejsca, które nie są usterkami, tylko decyzjami. Właściciel
przyjął rekomendacje 2026-09-15.

**1. `make_console()` idzie w `markup=False, highlight=False`. Wykonane.**
Reguła 10 („napis spoza programu staje się drukowalny wyłącznie przez `safe`") miała dotąd
jednego strażnika: skan AST. Skan łapie przeoczenia, a `KioError` deklaruje w docstringu, że
komunikat jest przeznaczony dla użytkownika — więc pierwsze `console.print(f"Błąd: {e}")`
w warstwie CLI odtworzyłoby dziurę z CEIDG. Wyłączenie znaczników na poziomie konsoli zamienia
regułę z własności skanu w własność obiektu. Koszt: własne komunikaty podają styl jawnie
(`Text`, `style=`) zamiast znacznikami w napisie — przy pustej jeszcze warstwie `ui/` jest to
koszt zerowy, po jej powstaniu byłby to koszt przepisania każdego ekranu. Strażnik:
`tests/test_richtext.py::test_konsola_programu_nie_interpretuje_znacznikow`, zweryfikowany
mutacją.

**2. `normalize_signature` zostaje przy wyszukiwaniu w napisie. Do ADR-0001.**
Funkcja na wejściu wielosygnaturowym zwraca pierwszą sygnaturę i nie sygnalizuje, że zgubiła
drugą sprawę — czyli popełnia błąd, przed którym ten moduł ma chronić. Wyszukiwanie w środku
napisu jest jednak niezbędne dla `parser/cite.py`, który szuka sygnatur wplecionych w zdania
uzasadnienia. Rozstrzygnięcie robocze: kompromis zostaje, jest opisany w docstringu jako
hazard, a reguła brzmi „napis poziomu dokumentu idzie wyłącznie przez
`normalize_signature_list`". Strażnik istnieje i przybija złe zachowanie jawnie. Czy funkcja
ma zamiast tego **odrzucać** wejście wielosygnaturowe, rozstrzyga ADR-0001 — razem z pomiarem
7 (sprostowania), bo obie rzeczy dotyczą tego, czym jest tożsamość dokumentu.

**3. Pisownia referencji w `document_id` jest sprawą kanału. Do ADR-0001.**
Dziś `document_id` sprowadza do małych liter nazwę kanału, ale nie referencję. Dla `uzp:9620`
i `saos:354301` jest to obojętne (identyfikatory liczbowe), dla sluga `atlas:kio-827-18`
realne: dwie pisownie dałyby dwa klucze główne na jeden dokument, czyli minę 1 z CEIDG.
Rekomendacja do ADR-0001: **normalizacja per kanał, zadeklarowana w `contract.yaml`** (pole
w rodzaju `ref_case: preserve | lower`), bo zasada „zapisuj tak, jak przyszło" jest słuszna
dla nieprzezroczystego identyfikatora liczbowego i błędna dla sluga tekstowego. Jedna reguła
dla obu przypadków byłaby błędna w jednym z nich. Do czasu ADR stan bieżący jest przybity
testem, więc nie zmieni się mimochodem.

---

## Pomiar 1 — czy `ftp.uzp.gov.pl` nadal odpowiada

**Zmierzone 2026-09-15, 3 próby połączenia (zero pobranych bajtów).** Wynik: **negatywny.**

Nazwa rozwiązuje się poprawnie na `37.128.76.156`, ale port 21 nie przyjmuje połączenia.
Trzy próby, limity 20 s, 25 s i 60 s; każda kończy się `Failed to connect to
ftp.uzp.gov.pl:21 ... Could not connect to server` po około 21 sekundach.

**Kontrola, bez której ten pomiar nic by nie znaczył.** Cisza na porcie 21 ma dwie możliwe
przyczyny i z samego wyniku nie da się ich odróżnić: albo serwer nie odpowiada, albo port 21
jest zablokowany wychodząco po stronie mierzącego — co w sieciach firmowych jest regułą,
nie wyjątkiem. Dlatego:

- `ftp://ftp.gnu.org/` **z tej samej maszyny, w tej samej minucie**: kod 226, czas 1,5 s.
  Port 21 nie jest więc u mierzącego zablokowany.
- `https://orzeczenia.uzp.gov.pl/`: HTTP 200, czas 4,6 s. Łączność do tej domeny działa,
  a sam urząd odpowiada — milczy wyłącznie usługa FTP.

**Czego ten pomiar NIE dowodzi.** Przekroczenie czasu to nie to samo co odmowa połączenia
(`ECONNREFUSED`). Zapora odrzucająca pakiety po stronie UZP dałaby ten sam obraz co wyłączony
serwer, więc nie wiadomo, czy usługa nie istnieje, czy jest niedostępna dla obcych adresów.
Dla operatora narzędzia skutek jest ten sam.

**Konsekwencje.** Tytuł komunikatu UZP („Komunikat dotyczący wyłączenia serwera FTP
z orzecznictwem KIO") okazuje się celniejszy niż jego treść, a korekta 3 z przeglądu
architektury — trafna. Droga „pobierz osiemnaście lat archiwum hurtem" jest zamknięta.
Wobec tego:

- **decyzja 9 (postać kanału FTP) odpada bez kosztu** — nie ma czego implementować, a reguła
  11 w brzmieniu z ADR-0003 i tak zabrania budowania `ftplib.FTP` gdziekolwiek, dopóki nie
  dopisze się właściciela protokołu;
- **ciężar odcinka 2007–2018 przechodzi w całości na SAOS** (pomiar 2a/2b), czyli na kanał,
  którego żaden klient w tym projekcie jeszcze nie potwierdził. Jeśli pomiar 2a wypadnie
  negatywnie, jedenaście lat materiału zostaje bez żadnej znanej drogi poza pośrednikiem;
- `source/ftp/` nie powstaje, a wiersz w tabeli 4.3 architektury, usunięty przy wdrożeniu
  ADR-0003, zostaje usunięty na stałe.

Sposób wykonania warto odnotować: pomiar zrobiono **narzędziem systemowym (`curl`)**, a nie
kodem Pythona, bo reguła 11 zabrania budowania konstruktu FTP w drzewie — także w `scripts/`.
Gdyby pomiar wypadł pozytywnie, dopiero decyzja 9 otwierałaby drogę do własnego właściciela
protokołu.

---

## Pomiar 14 — warunki ponownego wykorzystywania dla `orzeczenia.uzp.gov.pl`

**Zmierzone 2026-09-15, 4 żądania GET** (`orzeczenia.uzp.gov.pl/`, `gov.pl/`,
`gov.pl/web/gov/warunki-korzystania`, `gov.pl/web/gov/prawa-autorskie`). Wynik:
**warunków nie ma, informacji o ich braku też nie ma.**

Sposób uzyskania jest tu częścią wyniku. Pierwszy odczyt szedł przez narzędzie streszczające
i dopiero powtórzenie **w surowych bajtach** uznaję za pomiar — bo audyt opisuje dokładnie tę
pułapkę: liczba albo zdanie przeniesione przez jedno ogniwo streszczenia za dużo (14.1).

**Na `orzeczenia.uzp.gov.pl` (28 064 bajty strony głównej): zero trafień** dla ciągów
„licencj", „Creative", „ponowne wykorzyst", „warunki korzystania", „regulamin", „prawa
autorskie". Stopka niesie wyłącznie logotypy, nazwę projektu „Profesjonalizacja kadr
w zamówieniach publicznych" i „Deklarację dostępności". Jedyny odnośnik o charakterze
prawnym w całym serwisie dotyczy plików cookie.

**Na `gov.pl` licencja jest, ale jej zakres nie sięga tej domeny.** Wspólna stopka gov.pl
niesie dwa zdania, oba odczytane dosłownie:

> „Treści tekstowe publikowane **w serwisie** (z wyłączeniem treści audiowizualnych), są
> udostępniane na licencji typu Creative Commons: uznanie autorstwa - na tych samych
> warunkach 4.0 (CC BY-SA 4.0)."

> „**Strony dostępne w domenie www.gov.pl** mogą zawierać adresy skrzynek mailowych. […]"

Zakres jest więc zakreślony domeną `www.gov.pl`, a `orzeczenia.uzp.gov.pl` jest technicznie
odrębnym serwisem w odrębnej domenie, z własną stopką bez noty licencyjnej. Nie znalazłem
żadnego zdania rozciągającego licencję gov.pl na serwisy podmiotów w innych domenach.

**Co to rozstrzyga.** Dwie rzeczy, obie otwarte od audytu (3.5):

1. **Obawa o *share-alike* odpada.** CC BY-SA 4.0 niesie obowiązek udostępniania korpusów
   pochodnych na tej samej licencji, którego reżim ustawowy nie nakłada. Skoro licencja
   gov.pl nie obejmuje tej domeny, ten obowiązek nie wchodzi.
2. **Droga z art. 39 ust. 1 pkt 2 ustawy o otwartych danych jest właściwa.** Przepis mówi
   o ISP „udostępnianych w innym systemie teleinformatycznym niż [BIP lub portal danych]",
   dla których „nie zostały określone warunki ponownego wykorzystywania [...] albo nie
   poinformowano o braku takich warunków". Obie przesłanki są spełnione łącznie: wyszukiwarka
   jest takim innym systemem, warunków nie ma i informacji o ich braku też nie ma.

**Konsekwencja dla decyzji 2.** Wniosek o ponowne wykorzystywanie ma podstawę, a razem z nim
postulat techniczny z 4.6: kanał z datą modyfikacji albo zrzut przyrostowy, na wzór
`sinceModificationDate` z SAOS. Art. 39 ust. 2 pozwala wprost żądać dostępu „w sposób stały
i bezpośredni w czasie rzeczywistym"; art. 40 ust. 1 daje urzędowi 14 dni; art. 17 — bez
opłaty. To jest jedyna pozycja planu, która jednym pismem może usunąć problem „co nowego"
opisany w 4.6 jako wymagający trzech osobnych osi.

**Czego ten pomiar nie zrobił.** Nie przejrzałem całego BIP UZP pod kątem osobnej strony
o ponownym wykorzystywaniu — `uzp.gov.pl/bip` przekierowuje na `gov.pl/web/uzp/`, a strona
`gov.pl/web/uzp/ponowne-wykorzystywanie-informacji-sektora-publicznego` nie istnieje. Nie
jestem prawnikiem; to jest odczyt przepisu i odczyt stron, nie opinia, i wymaga potwierdzenia
u prawnika, o którym audyt mówi w 13.2 pkt 2.

---

## Trzy decyzje właściciela z 2026-09-17 — ścieżka bez korespondencji

Nie są pomiarem i nie udają pomiaru. Są rozstrzygnięciem o **zakresie przedsięwzięcia**,
podjętym po tym, jak plan kolejnych kroków postawił przed właścicielem trzy pozycje o koszcie
liczonym w tygodniach cudzego kalendarza. Odpowiedź brzmiała: na to nie ma czasu.

Zapisane tutaj, bo każda z trzech zmienia architekturę albo status dowodowy, a decyzja
przemilczana czyta się po pół roku jak rozstrzygnięcie techniczne.

### Decyzja A: projekt nie prowadzi korespondencji

**Odpada na stałe:** wniosek do UZP z art. 39 ustawy o otwartych danych, cztery pytania do
prawnika, mail do Atlasu o warunki feedu (pomiar 15). Projekty pism zostają w `docs/pisma/`
nienaruszone — są gotowe, gdyby decyzja kiedyś się zmieniła — ale **żaden plan nie wisi już
na ich wysłaniu**.

Co to kosztuje, wypisane wprost, żeby nie wyglądało na darmowe:

- **kanał `uzp_zrzut` nie powstanie.** Wykrywanie nowości zostaje przy trzech osiach z 4.6
  architektury (okna dat, kontrola krzyżowa pośrednikiem, rzadki skan luk w identyfikatorach)
  zamiast zredukować się do jednej. To jest więcej kodu w fazie 1 — koszt wykonawcy, nie
  właściciela;
- **opóźnienie publikacji u pośrednika (pomiar 3b) mierzy się obserwacją**, nie pytaniem:
  ta sama sprawa z dwóch kanałów w odstępie dni. Wolniej i mniej dokładnie niż odpowiedź
  dostawcy, ale bez niczyjej korespondencji;
- **nie ma opinii prawnej** i to jest ryzyko resztkowe przyjęte świadomie przez właściciela.
  Nie usuwa go żadna decyzja projektowa; decyzja B je zawęża.

### Decyzja B: UZP nigdy nie pełni roli kanału masowego

**Reguła, nie preferencja.** Pobranie całości zbioru idzie wyłącznie z kanału, który
ponowne wykorzystywanie **licencjonuje wprost**. Dla `orzeczenia.uzp.gov.pl` takiej licencji
nie ma — pomiar 14 (zmierzone 2026-09-15) wykazał brak warunków i brak informacji o ich braku.

Dla UZP zostają dwie role: **weryfikacja na próbce** (`porownaj`) i **dopływ bieżący** —
rzędu kilkudziesięciu żądań, nie 63 000.

Ta decyzja zastępuje pytanie 2 do prawnika (bazy *sui generis* wobec ustawowego prawa
reużycia). Pytanie brzmiało „czy wolno pobrać istotną część cudzej bazy"; odpowiedź brzmi
„nie pobieramy istotnej części tej bazy". Uzasadnienie stoi zresztą w treści samego pytania:
przy odpowiedzi niepewnej rozstrzygnięciem miało być pobranie przez pośrednika, czyli **inne
rozstrzygnięcie architektoniczne, nie inne pismo**.

Skutek uboczny, wart odnotowania po stronie cudzego serwera: ~63 000 żądań i 17–19 godzin
renderowania PDF-ów po stronie UZP po prostu nie wystąpi.

Reguła dostaje mechanicznego strażnika (reguła 23 w architekturze 4.1), bo reguła bez
strażnika jest w tym projekcie życzeniem.

### Decyzja C: repozytorium zostaje bez zdalnego, ryzyko przyjęte

Decyzja 5 z audytu 13.2 jest **zamknięta odmownie**. `docs/decisions.md` i
`docs/dziennik_zadan.md` są jedynym nieodtwarzalnym aktywem tego przedsięwzięcia — kod da się
napisać ponownie, a zdanie „FTP UZP nie odpowiada, zmierzone 2026-09-15" powtórzone za rok
będzie inną informacją, nie tą samą. Oba pliki leżą na jednym dysku i tak zostaje.

Zapisane tutaj po to, żeby utrata dysku była zdarzeniem **przewidzianym**, a nie odkryciem.
Ten wpis zamyka temat: nie wraca w kolejnych sesjach jako przypomnienie.

---

## Pomiar 3a — czy Atlas zwraca pełny tekst; od kiedy sięga zbiór

**Zmierzone 2026-09-18, 2 żądania GET** (`sonda-20260918T103525Z`, poziom anonimowy, bez klucza
API; tożsamość klienta z adresem kontaktowym właściciela). Wynik: **pozytywny — pełny tekst jest,
w polu `full_text` rekordu dokumentu.**

**Lista** `GET /api/kio?per_page=100&page=1&sort=oldest`: 200, 91 447 B, SHA-256
`0034a634ca2c98f94dbd0cb68ef3aba2ad16abfa27ed5f1485953e01470feec0`. Korzeń odpowiedzi:
`data` (tablica 100 rekordów), `has_more: true`, `page: 1`, `per_page: 100`, `search_engine:
"sql"`, `total: 29580`. Rekord listy ma 23 pola: `appellant_raw, bzp_numbers, chairperson,
cited_rulings, costs_total, hearing_date, law_articles, outcome, outcome_raw, panel,
primary_signature, procuring_entity_raw, protocolant, ruling_date, ruling_kind, signatures, slug,
source_url, subject, ted_numbers, tender_id, thesis_snippet, url`.

**Dokument** `GET /api/kio/kio-1205-20` (slug pierwszego rekordu listy): 200, 8 963 B, SHA-256
`d29338bd88146731dc2e06271a407cecf595e5b616ea4bc7d88055faab5c574e`. Rekord ma 34 pola — te same
co lista oraz `cited_by, cites, created_at, document_id, full_text, related_buyer_name,
related_by_entity, related_tenders, similar_rulings, thesis, updated_at`. Najdłuższe pole tekstowe
to `full_text` (3 021 znaków; postanowienie zaczynające się od „Sygn. akt: KIO 1205/20 /
POSTANOWIENIE / z dnia 16 czerwca 2020 r."). `signatures` jest listą (`["KIO 1205/20"]`),
`document_id` to liczba `13053` równa identyfikatorowi tego orzeczenia w wyszukiwarce UZP
(`source_url` = `https://orzeczenia.uzp.gov.pl/Home/PdfContent/13053?Kind=KIO`),
`created_at`/`updated_at` = `2026-04-22T00:01:22+00:00`, `thesis` i `thesis_snippet` są `null`
w tym dokumencie. Pola `related_by_entity` i `similar_rulings` to opracowanie Atlasu (powiązania),
nie treść orzeczenia.

**Postać sluga:** `kio-<numer>-<rr>` — sygnatura główna małymi literami z myślnikami zamiast
spacji i ukośnika; alfabet `[a-z0-9-]`, 9–11 znaków, 100 na 100 rekordów (rozstrzyga `ref_case:
lower` w ADR-0001).

**Zasięg zbioru — wynik osobny, jak wymagał dawny `pomiary.md`.** `sort=oldest` dało sto
rekordów z `ruling_date` od 2004-01-29 do 2010-11-04, ale sufiksy sygnatur mówią co innego:
91 rekordów z `/10`, 4 z `/17`, 5 z `/20`. Rok sufiksu różny od roku `ruling_date` sam w sobie
błędem nie jest (sprawa wniesiona pod koniec roku rozstrzygana w następnym — w korpusie stycznia
2024 tak wygląda 186 z 295 rekordów; sprostowanie 2026-09-18 po pierwszym przebiegu). Błędem jest
`ruling_date` **wcześniejsze niż `hearing_date`** — jak w `kio-1205-20`: `ruling_date`
2004-01-29 wobec rozprawy 2020-06-16 i treści „z dnia 16 czerwca 2020 r.". Wniosek:
**`ruling_date` w Atlasie bywa błędne** (cudzy potok z PDF — ryzyko z audytu 4.2 zmierzone, nie
przypuszczone), więc dolnej granicy zbioru nie da się odczytać z sortowania po dacie. **Zbiór
sięga co najmniej rocznika 2010**; roczniki 2007–2009 są niezmierzone — rozstrzygnie filtr po
sygnaturze albo `date_from`/`date_to` w osobnym przebiegu. `total` 29 580 wobec 29 482
deklarowanych 2026-09-14 (dopływ 98 orzeczeń w 4 dni albo różnica liczenia; nierozstrzygnięte).

**Czego ten pomiar nie zrobił.** Nie odczytał nagłówków `X-RateLimit-*` (sonda zapisuje treść
odpowiedzi, nie nagłówki) — adapter czyta je przy pierwszym przebiegu. Nie sprawdził, czy pole
`thesis` w innych dokumentach niesie treść od modelu; dokumentacja tego nie wyjaśnia, więc reguła
19 traktuje `thesis*` jako pole o nieznanym pochodzeniu (`pola_odrzucone` w kontrakcie).

---

## Pomiar 17 — postaci sygnatur w zbiorze (częściowy)

**Policzone 2026-09-18 z odpowiedzi pomiaru 3a, 0 dodatkowych żądań** (sto rekordów listy,
rocznik 2010 w przewadze). Trzy postaci `primary_signature`: `KIO 9999/99` (86), `KIO 999/99`
(13), `KIO 99/99` (1). Sygnatur wielokrotnych: 6 rekordów po dwie (np. `kio-388-10` →
`["KIO 388/10", "KIO 390/10"]`), 1 po trzy; pierwszy element `signatures` równy
`primary_signature`. Postaci `KIO/UZP 1482/08` i `KIO/KU 97/13` (znane `docid.py` z odczytów
2026-09-15) w tej próbce nie ma — próbka nie sięga 2008. `ruling_kind`: `wyrok` 91,
`postanowienie` 9. **Dopełnienie** na rekordach pierwszego przebiegu (etap IV), zero żądań.

### Dopełnienie 2026-09-18 — 295 rekordów stycznia 2024 (pierwszy przebieg), 0 żądań

Policzone z `raw_versions` bazy `korpus.sqlite` po przebiegu `atlas-dd55fb768069`. Cztery
postaci `primary_signature`: `KIO 9999/99` (196), `KIO 99/99` (58), `KIO 999/99` (34),
`KIO 9/99` (7). Sygnatur wielokrotnych: 16 rekordów po dwie, 1 po trzy; w 295 na 295
`signatures[0] == primary_signature`. Postaci `KIO/UZP` i `KIO/KU` w tej próbce nie ma (rocznik
2024). `ruling_kind`: `postanowienie` 173, `wyrok` 122. `outcome`: `umorzono` 134, `oddalono`
67, `uwzglednione` 57, `inne` 31, `odrzucono` 6 — ta sama zamknięta lista pięciu wartości co
w próbce z pomiaru 3a. Razem z próbką z 3a: cztery postaci sygnatury, wszystkie obsługiwane przez
`docid.normalize_signature`.

---

## Jakość pól Atlasu — próbka 295 rekordów (styczeń 2024)

**Policzone 2026-09-18 z bazy, 0 żądań.** Zapis dla parsera i dla operatora, nie dla wyboru
kanału (ten zapadł):

- `full_text`: 2 348 – 182 631 znaków, mediana 10 376, pustych 0. Tam, gdzie pierwsze 600 znaków
  niesie datę „z dnia D miesiąca RRRR" (75 z 295), zgadza się ona z `ruling_date` w 75 na 75.
- **`ruling_date` wcześniejsze niż `hearing_date` w 9 z 295** (np. `kio-4618-24`: `ruling_date`
  2024-01-07, rozprawa 2024-12-09) — te rekordy weszły do zakresu styczniowego przez błędną datę,
  a orzeczenia z sygnaturą `46xx/24` należą do końca 2024. Filtr `date_from`/`date_to` po stronie
  Atlasu zarówno wciąga cudze, jak i (prawdopodobnie) gubi własne; kompletność rocznika wymaga
  drugiej osi (numer sygnatury), nie tylko dat.
- `hearing_date` puste w 56, `chairperson` puste w 29, `panel` puste w 250, `law_articles` puste
  w 23. `thesis` i `thesis_snippet` puste w 295 na 295 — teza od modelu w tej próbce nie
  występuje.
- `document_id` (identyfikator UZP) od 19 721 do 28 875; `created_at` 2026-04-21/22 (import
  pośrednika), `updated_at` od 2026-04-21 do 2026-08-14 — pole zmienia się po imporcie, więc nadaje
  się na oś „co nowego" (do zmierzenia osobno).
- `cited_rulings`/`cites` niepuste w 104 z 295 — materiał do pomiaru 22 (graf cytowań).

---

## Przebieg 1 — styczeń 2024 z Atlasu: bramka fazy 1

**Zmierzone 2026-09-18, 302 żądania GET łącznie** (kanał `atlas`, poziom anonimowy, baza
`%LOCALAPPDATA%\kio-tool\kio-tool\korpus.sqlite`). Kryterium bramki fazy 1 (audyt 9): przebieg
na ograniczonym zakresie, **przerwany w połowie i wznowiony**, kończy się korpusem bez
duplikatów; ta sama sprawa pobrana dwa razy nie tworzy drugiego wpisu. **Spełnione:**

1. `kio-tool pobierz --od 2024-01-01 --do 2024-01-31` **bez** `--zgoda` — kanał zgłosił 295
   dokumentów w zakresie (`total` z filtrem dat), przebieg `atlas-dd55fb768069` stanął po
   pierwszej stronie listy na progu zgody (`ConsentMissingError`, kod 3, 1 żądanie, status
   `przerwany`, `ostatnia_strona` 1). To jest realne przerwanie, nie symulowane.
2. To samo polecenie z `--zgoda` — wznowienie tego samego przebiegu: 3 strony listy + 295
   dokumentów, 298 żądań, 11:32:32Z–11:38:29Z, wszystkie odpowiedzi 200, odstęp ~1 s przez
   limiter (puls „zapisano N dokumentów", nigdy stron). Wynik: `documents` 295 = `raw_versions`
   295 = liczba kandydatów, `requests_log` 299 wierszy, 11 546 831 bajtów treści.
3. To samo polecenie trzeci raz (po migracji schematu 1→2): 295 kandydatów, **0 nowych,
   295 pominiętych bez żądań**, 3 żądania (same strony listy); nowy przebieg
   `atlas-969ac406dd8f` powiązał wszystkich 295 kandydatów w `run_documents`.
4. `kio-tool przelicz` (0 żądań, `--block-network` pilnuje tego w testach): 295 wersji
   przeliczonych, 0 błędów odczytu, 295 zaindeksowanych w FTS5.
5. `kio-tool szukaj --fraza "odrzuca odwołanie"`: w korpusie 295, zaindeksowanych 295, trafień
   11 — liczby nad tabelą (mina 2 z audytu 11).
6. `kio-tool eksportuj`: xlsx (arkusze `Orzeczenia` 295 wierszy, `Slownik`, `Metadane` z liczbami
   z bazy, organem i atrybucją CC BY 4.0), jsonl (295 rekordów z `full_text`), csv, md (295 plików
   z nagłówkiem YAML i blokiem cytowania + `INDEX.md`).

**Czego ten przebieg nie rozstrzygnął.** Kompletności rocznika: filtr `date_from`/`date_to` idzie
po `ruling_date` pośrednika, a to pole bywa błędne (sekcja „Jakość pól Atlasu"), więc styczeń
2024 według Atlasu ma 295 orzeczeń z 9 podejrzanymi datami; pełny rocznik i cały zbiór to osobna
decyzja właściciela (ADR-0005 §5). Postaci `X-RateLimit-Reset` nikt nie odczytał (dziennik
trzyma treści, nie nagłówki; `fetch_meta` w `raw_versions` je niesie — do odczytu przy
następnym przebiegu). Przebieg sprzed migracji schematu (`atlas-dd55fb768069`) nie ma wierszy
w `run_documents`, więc `eksportuj --run-id` dla niego zwraca zero — eksport tego zakresu idzie
przez `--od/--do` (zgłoszone testerowi 2026-09-18).

---

## Przebieg 2 — luty 2024 (1–5) z Atlasu: ubicie procesu i wznowienie na żywym serwisie

**Zmierzone 2026-09-18, 48 żądań GET** (kanał `atlas`, poziom anonimowy, ta sama baza co
Przebieg 1). Scenariusz „zanik zasilania": `pobierz --od 2024-02-01 --do 2024-02-05 --zgoda`
uruchomione jako osobny proces i ubite `Stop-Process -Force` (odpowiednik `taskkill /F`) po
24 sekundach — bez `finally`, bez zapisu statusu, bez sprzątania.

- Po ubiciu: przebieg `atlas-009ab0e9dd93` stoi w bazie jako `w_toku` bez procesu, 22 dokumenty,
  23 żądania (1 strona listy + 22 dokumenty), `ostatnia_strona = 1`; kanał zgłosił 46 dokumentów
  w zakresie.
- To samo polecenie: rozpoznane jako osierocony (zdanie na ekranie), wznowione od strony 1 —
  24 nowe dokumenty, 22 pominięte bez żądania, 25 żądań; łącznie w przebiegu 48 żądań,
  46 dokumentów objętych i pobranych, status `zakonczony`; eksport xlsx, jsonl i md (46).
- Po wznowieniu `wznow` odmawia: „nie ma przerwanego ani osieroconego przebiegu" (kod 3).
- Baza po całości dnia: 341 dokumentów = 341 wersji surowych = 341 metadanych = 341 w indeksie;
  352 żądania, wszystkie ze statusem 200 i kształtem zgodnym; `run_documents` przebiegu: 46,
  wszystkie nowe.

Wniosek: poprawka „przebieg `w_toku` bez procesu jest osierocony i wznawialny" (tester
i przegląd 2026-09-18) działa na żywym serwisie tak samo jak na atrapie; kosztem ubicia jest
jedna strona listy wysłana ponownie.

---

## Pomiar filtrów Atlasu — `outcome` i `search` (pierwsze własne wywołania)

**Zmierzone 2026-09-18, 6 żądań GET** — po jednej stronie listy na wywołanie; dokumenty były już
w bazie, więc żadne żądanie za dokument nie poszło. Metoda: ten sam zakres dat u kanału
i lokalnie, porównanie zbiorów sygnatur.

| Wywołanie | U Atlasu | Lokalnie (`eksportuj`, `szukaj` na 295 dokumentach stycznia) |
|---|---|---|
| `outcome=odrzucono`, 2024-01-01..31 | 6 | 6 — te same sygnatury: KIO 3814/23, 3841/23, 3869/23, 3951/23, 115/24, 155/24 |
| `search=odrzuca odwołanie`, styczeń | 0 | 11 (pełny tekst, FTS5) |
| `search=odwołanie`, styczeń | 0 | co najmniej 11 (każde z orzeczeń wyżej niesie to słowo) |
| `search=KIO 115/24`, styczeń | 1 — KIO 115/24 | — |
| `outcome=odrzucono`, 2024-02-01..05 | 0 | 0 |
| `search=odrzuca odwołanie`, 2024-02-01..05 | 0 | 0 |

Wnioski — mina 2 audytu (semantyka `search`) rozstrzygnięta: **`search` Atlasu dopasowuje
sygnaturę, nie treść** — słowo obecne w treści zwraca zero, sygnatura zwraca dokładnie ten
dokument. `outcome` jest zgodny z rozstrzygnięciem znormalizowanym w rekordzie (6 na 6). Skutek
dla narzędzia: `pobierz --fraza` nie służy do wyszukiwania w treści u kanału — treść przeszukuje
lokalnie `szukaj` po pobraniu zakresu dat; pomoc flagi i zdanie przy pustym wyniku mówią to od
2026-09-18. Parametry `date_from`/`date_to` miały pierwsze własne wywołanie w Przebiegu 1
(295 dokumentów z datami 2024-01-03..2024-01-31) i drugie w Przebiegu 2 (46 dokumentów
2024-02-01..2024-02-05). Filtry `law_article`, `chairperson`, `party` nadal bez własnego
wywołania.

---

## Pomiar 23 — warunki ponownego wykorzystywania SAOS i Atlasu, odczytane u źródła

**Zmierzone 2026-09-18, 3 żądania GET** (`sonda-20260918T103544Z`), te same sześć markerów
co w pomiarze 14 (`licencj`, `creative`, `ponowne wykorzyst`, `warunki korzystania`,
`regulamin`, `prawa autorskie`).

- **`https://www.saos.org.pl/`: brak odpowiedzi** — `ReadTimeout` po 45,31 s. Markery
  **nie policzone**; to nie jest „zero trafień" z pomiaru 14, tylko odczyt, który nie doszedł do
  skutku. SAOS pozostaje kanałem o nieodczytanych warunkach i nieprzetestowanym dostępie.
- **`https://atlasprzetargow.pl/`** (korzeń): 200, 331 340 B, SHA-256
  `b9d462c80d050c2af1ac021f5e8d5eef1c9ea1f0232643c1b0f69dd0f8d6a0d8`; markery: `regulamin`×4.
- **`https://atlasprzetargow.pl/dokumentacja-api`**: 200, 298 377 B, SHA-256
  `79b1e0562002cc37edbd19fdc0b88b89b5da9e2d98a3635b4316b3d60d497f48`; markery: `licencj`×26,
  `creative`×4, `regulamin`×4. Strona niesie datę „Ostatnia aktualizacja: 10 września 2026"
  i dwa zdania odczytane z surowych bajtów (po zdjęciu znaczników HTML):

  > „Licencja danych CC BY 4.0 z podaniem źródła"

  > „[…] udostępniamy na licencji CC BY 4.0. Możesz je wykorzystywać także komercyjnie, pod
  > warunkiem podania źródła: Źródło: Atlas Przetargów (https://atlasprzetargow.pl)"

**Co to rozstrzyga.** Atlas licencjonuje ponowne wykorzystywanie wprost, z formułą atrybucji,
więc spełnia warunek decyzji B dla kanału masowego; formuła idzie do `contract.yaml` kanału
i do każdego eksportu (reguła 15). Nie jest to opinia prawna: licencja dotyczy „opracowania
Atlasu", a dane źródłowe strona nazywa informacją publiczną — rozróżnienie zapisane, nie
rozstrzygnięte.

---

## Status pomiarów

**Ta sekcja zastępuje `docs/pomiary.md`** (istniał od 2026-09-17 do 2026-09-18; ADR-0005, Z-8).
Powód scalenia: lista ze statusem w jednym pliku i wyniki w drugim wymagały strażnika symetrii
w `tests/test_bramki_faz.py`, a dwie listy wymagające synchronizatora powinny być jedną listą.
Status stoi odtąd obok wyniku, w tym samym pliku: kolumna „Status" przy pomiarze wykonanym
wskazuje sekcję `## Pomiar N` wyżej albo niżej. Audyt 10 i architektura 6 zostają jako zapis
tego, **po co** pomiar powstał i jak go wykonać najtaniej.

Legenda kolumny „wejście do": **bramka** = wejście bramki wyboru kanału w brzmieniu ADR-0005
(pomiary kanału, który powstaje — dla `atlas` z pola `pomiary:` jego `contract.yaml`);
**ADR-0001** = wejście rozstrzygnięcia o tożsamości dokumentu w brzmieniu ADR-0005 Z-4;
**faza 1 / 2** = potrzebny później; **zamknięty** = nie wraca; **odłożony** = poza ścieżką
rekomendowaną 2026-09-18, wraca z kanałem, którego dotyczy.

| # | Pomiar | Status | Wejście do | Czym wykonać |
|---|---|---|---|---|
| 1 | Czy `ftp.uzp.gov.pl` nadal odpowiada | **wykonany 2026-09-15 — negatywny** (`## Pomiar 1`) | zamknięty | — |
| 2a | Własny klient do Dump API SAOS | niewykonany | odłożony (kanał `saos`, po bramce fazy 1) | `sonda.py saos-dump` |
| 2b | Czy Dump API filtruje po `courtType` | niewykonany | odłożony (jak 2a) | `sonda.py saos-dump` |
| 3a | Czy Atlas zwraca pełny tekst (lista + dokument `/api/kio/{slug}`); od kiedy sięga zbiór | **wykonany 2026-09-18 — pozytywny: `full_text`, zbiór ≥ rocznik 2010, `ruling_date` bywa błędne** (`## Pomiar 3a`) | **bramka** (`atlas`) — spełnione | `sonda.py atlas` — 2 żądania |
| 3b | Opóźnienie publikacji u pośrednika | niewykonany | faza 1 | **wyłącznie obserwacja w czasie** — ta sama sprawa z dwóch kanałów w odstępie dni; droga przez pytanie do dostawcy zamknięta decyzją A |
| 4 | Kontrakt wyszukiwarki UZP | **wykonany strukturalnie** (`Move` → `Details` własnym odczytem; `GetResults` z dwóch cudzych kolektorów) | — | — |
| 4b | Własny `POST /Home/GetResults` i pierwsza kaseta | niewykonany | odłożony (kanał `uzp` w rolach weryfikacji i dopływu, faza 2) | `sonda.py uzp-getresults` |
| 5 | Warstwa tekstowa w próbce ~50 dokumentów | niewykonany | faza 2 | próbka staje się zalążkiem `tests/gold/` |
| 6 | Granice przestrzeni identyfikatorów | z drugiej ręki (~33 366 w kwietniu 2026) | faza 1 | dwa odczyty `Details` + pomiar 16 |
| 7 | Sprostowania: nowy rekord czy nadpisanie | niewykonany | polityka wersji kanału `uzp` (ADR-0005 Z-4) | `GetResults` dla sprawy ze znanym sprostowaniem |
| 8 | Dokumenty wielosygnaturowe w wyszukiwarce | potwierdzone strukturalnie | ADR-0001 | jeden odczyt `Details` sprawy z listingu FTP |
| 9 | Tolerancja serwisu na tempo | niewykonany; **wymaga zgody właściciela** | odłożony — zbędny dla Atlasu (limity publikowane i raportowane nagłówkami); tylko jeśli UZP dostanie rolę masową, czego decyzja B zabrania | ostrożne narastanie ze stopem |
| 10 | Anonimizacja na większej próbce | niewykonany | faza 2 | 30–50 dokumentów, w tym z protokołem rozprawy |
| 11 | Co indeksuje „Hasło", co dokłada „w treści" | wykonany strukturalnie (`SCnt`, `Fle`) | faza 3 | jedno zapytanie o frazę z uzasadnienia |
| 12 | Zbiór KIO w `dane.gov.pl` | **zamknięty — negatywny** | zamknięty | — |
| 13 | Jak często data wydania jest pusta | klasa, nie wyjątek | faza 1 | próbka 200 identyfikatorów |
| 14 | Warunki ponownego wykorzystywania dla `orzeczenia.uzp.gov.pl` | **wykonany 2026-09-15 — warunków nie ma, informacji o ich braku też nie** (`## Pomiar 14`) | **decyzja B**: brak licencji jest powodem, dla którego UZP nie pełni roli masowej | — |
| 15 | Warunki feedu dziennego Atlasu | **zamknięty 2026-09-17 — decyzja A, projekt nie prowadzi korespondencji** | zamknięty; pytanie o świeżość przejmuje 3b | mail zostaje gotowy w `docs/pisma/`, niewysłany |
| 16 | Liczniki `#resultCounts` przy pustej frazie | niewykonany | odłożony (idzie razem z 4b) | — |
| 17 | Postaci sygnatur w zbiorze | **częściowo wykonany 2026-09-18** na stu rekordach listy (`## Pomiar 17`); dopełnienie po pierwszym przebiegu | ADR-0001 (przyjęty 2026-09-18) — uzupełnienie, nie warunek (ADR-0005 Z-4) | z odpowiedzi pomiaru 3a; docelowo z `citations` |
| 18 | Czy zmiana Pzp z 13.03.2026 zmieniła słownik przepisów | niewykonany | faza 2 | dwa wywołania słownika |
| 19 | Czy `ContentHtml` jest bitowo stabilny między pobraniami | niewykonany; **wymaga doby odstępu** | polityka wersji kanału `uzp` (ADR-0005 Z-4) — **nie jest już warunkiem `store.py`** | `sonda.py uzp-stabilnosc`, dwa przebiegi ≥24 h |
| 20 | Co zwracają `/AiSearch/*` | niewykonany | faza 4 | narzędzia deweloperskie przeglądarki |
| 21 | Blokada sieci w testach wobec wstrzykniętego transportu i wobec gniazda | **wykonany 2026-09-15 w obu połowach — pozytywny** (`## Pomiar 21`) | zamknięty w części „blokada"; odtwarzanie kaset rozstrzyga test dymny adaptera Atlasu (ADR-0005 Z-10) | — |
| 22 | Gęstość cytowań i udział nieznormalizowanych | niewykonany | faza 2 | `parser/cite.py` na próbce z pomiaru 5, zero żądań |
| 23 | Warunki ponownego wykorzystywania SAOS i Atlasu, odczytane **u źródła** | **wykonany 2026-09-18 — Atlas: CC BY 4.0 z atrybucją u źródła; SAOS: brak odpowiedzi w 45 s** (`## Pomiar 23`) | **bramka** (`atlas`) — spełnione dla Atlasu; SAOS nieodczytany | `sonda.py licencje` — 3 żądania; SHA-256 każdej strony w `## Pomiar 23` |

### Dlaczego pomiar 3 jest rozbity na 3a i 3b

Architektura 6 mówi, że pomiar 3 wykonuje się poleceniem `porownaj` — a `porownaj` potrzebuje
dwóch kanałów i bazy, czyli istnieje **po** bramce, którą pomiar 3 ma odblokować. W tym brzmieniu
pomiar jest cyrkularny i nie da się go wykonać na czas. Rozdzielenie idzie po koszcie, nie po
temacie: **3a — czy zwraca pełny tekst** (dwa żądania sondy, koszt minutowy, wejście bramki;
odpowiedź daje nazwa i długość najdłuższego pola tekstowego rekordu dokumentu, nie deklaracja
dostawcy — od 2026-09-18, wcześniej pomiar wołał wyłącznie listę), **3b — opóźnienie publikacji**
(obserwacja w czasie; kosztem jest kalendarz, więc nie ma prawa blokować bramki). Przy okazji 3a
odpowiada na pytanie, którego nikt nie zapisał jako pomiaru: **od którego rocznika sięga zbiór
pośrednika** (`sort=oldest`) — wynik ma trafić do tego pliku osobno, a nie jako uwaga do
pomiaru 3, bo od niego zależy, czy odcinek 2007–2018 potrzebuje kanału `saos`.
