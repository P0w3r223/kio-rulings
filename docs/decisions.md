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

**Stan faktyczny zmieniony przez właściciela (odnotowane 2026-09-19).** Repozytorium ma zdalne:
prywatne `P0w3r223/Kio` na GitHubie, i tam je znalazła sesja z 2026-09-19 na maszynie, na której
lokalnej kopii nie było. Właściciel wybrał tego dnia pracę na gałęzi z PR-em. Decyzja C nie jest
więc już opisem stanu — `decisions.md` i `dziennik_zadan.md` mają kopię poza jednym dyskiem.
**Korpus nadal nie ma** (leży poza repozytorium z powodu danych osobowych — `config.default_db_path`)
i to jest ta część ryzyka, która zostaje: sesja z 2026-09-19 odtworzyła go od nowa z Atlasu
(Przebieg 3, 464 żądania), bo baza z 2026-09-18 istniała tylko na innej maszynie.

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

## Pomiar 5, część lokalna — kształt tekstu w korpusie (etap I fazy 2)

**Policzone 2026-09-19 z bazy operatora, 0 żądań.** 341 dokumentów, każdy odczytany z bieżącej
wersji w `raw_versions`; 0 bez treści, 0 nieodczytanych. Długość `full_text` w znakach: min 2 348,
mediana 11 416, max 355 527, suma 9 487 501.

**Cztery cechy materiału po ekstrakcji z PDF-a** (ADR-0006 §1.1 nazwał je z jednego dokumentu;
tu są policzone na całym korpusie):

| Cecha | Dokumentów | % korpusu | Wystąpień |
|---|---|---|---|
| wysuw strony `\f` | 341 | 100,0 % | 2 110 |
| łamanie wiersza w środku zdania | 341 | 100,0 % | 60 090 |
| sklejenie po dwukropku (`:` + wielka litera) | 211 | 61,9 % | 276 |
| nagłówek rozstrzelony spacjami | 88 | 25,8 % | 178 |

**Kotwice struktury — w ilu dokumentach w ogóle występują:**

| Kotwica | Dokumentów | % korpusu |
|---|---|---|
| `WYROK` albo `POSTANOWIENIE` | 341 | 100,0 % |
| `orzeka:` albo `postanawia:` | 340 | 99,7 % |
| `przysługuje skarga` (pouczenie) | 337 | 98,8 % |
| `Sygn. akt` | 325 | 95,3 % |
| `Przewodniczący` | 312 | 91,5 % |
| słowo „uzasadnieni…" gdziekolwiek | 280 | 82,1 % |
| `O kosztach postępowania` | 224 | 65,7 % |
| **`^Uzasadnienie$` jako osobna linia** | **215** | **63,0 %** |

**Sprostowanie do ADR-0006 §1.1.** Ten ADR twierdzi, że wzorce z architektury 4.5 „przyłożone do
tego materiału dają korpus w całości `nieprzypisany`". Pomiar tego nie potwierdza: `^Uzasadnienie$`
jako osobna linia trafia w **63,0 %** dokumentów, a nie w zero. Teza powstała z jednego dokumentu
(`dokument_20260918T103526Z.json`, rocznik 2020) i jest przykładem dokładnie tego, przed czym
ostrzega doktryna 7.1. Problem jest **realny, ale inny co do wielkości**: wzorce oparte wyłącznie na
nagłówkach zgubiłyby około 37 % korpusu, nie 100 %. Kierunek rozwiązania z ADR-0006 (normalizacja
przed segmentacją, kotwice z pomiaru, offsety w oryginale) pomiar potwierdza — uzasadnienie liczbowe
w ADR-ze wymaga poprawki przy przyjęciu.

**Co z tego wynika dla etapu III.** Kotwice nośne to `WYROK`/`POSTANOWIENIE`, `orzeka:`/`postanawia:`
i pouczenie o skardze — wszystkie powyżej 98 %. `Sygn. akt` zawodzi w 16 dokumentach, `Przewodniczący`
w 29. Łamanie wiersza w zdaniu dotyczy **każdego** dokumentu (60 090 wystąpień), więc normalizacja
przed segmentacją nie jest opcją, tylko warunkiem — i to jest jedyna cecha z tej tabeli, której
żaden wzorzec nagłówkowy nie obejdzie.

**Rocznik z sygnatury głównej:** `23` — 185, `24` — 154, `25` — **2**. Dwa dokumenty z rocznikiem 25
w korpusie ograniczonym datą wydania do stycznia i 1–5 lutego 2024 są anomalią do wyjaśnienia:
albo `ruling_date` jest tam błędne (defekt znany z pomiaru 3a, 9 na 100), albo sygnatura ma postać,
której odczyt rocznika nie obsługuje. Nie rozstrzygnięte — zapisane.

**Zastrzeżenie metody.** „Nagłówek rozstrzelony" i „łamanie w zdaniu" są liczone wyrażeniami
regularnymi zbudowanymi pod te cechy, nie miarą kanoniczną: pierwsze wymaga co najmniej czterech
kolejnych grup jedno- lub dwuliterowych, drugie — małej litery albo przecinka przed końcem wiersza
i małej litery po nim. Obie liczby są dolnym oszacowaniem i tak mają być czytane.

---

## Przebieg 3 — odtworzenie korpusu na nowej maszynie i próbka rocznikowa (ADR-0006 Z-3)

**Zmierzone 2026-09-19, 464 żądania, wszystkie 200, zero ponowień** (`requests_log.proba > 1`
= 0 — pierwszy przebieg po wdrożeniu ADR-0007). Korpus z 2026-09-18 istniał na jednej maszynie
i repozytorium go nie niesie (`config.default_db_path`), więc na maszynie, na której pracowała
ta sesja, został pobrany od nowa za zgodą właściciela udzieloną w sesji.

| Przebieg | Zakres | Dokumentów | Żądań |
|---|---|---|---|
| `atlas-1bbd11b860cb` | 2024-01-01..2024-01-31 | 295 | 298 |
| `atlas-8958b75abcef` | 2024-02-01..2024-02-05 | 46 | 47 |
| 17 przebiegów po `--maks 6` | `RRRR-06-01..RRRR-12-31`, roczniki 2010–2026 | 102 | 119 |

Liczby stycznia i lutego zgadzają się z Przebiegami 1 i 2 (295 i 46) — zbiór Atlasu na tym
zakresie nie zmienił się w ciągu doby. Próbka rocznikowa bierze **pierwsze sześć** orzeczeń od
1 czerwca każdego roku (`sort=oldest`), więc jest stratyfikowana po roku, a w obrębie roku nie jest
losowa — to jest cena zapisana, nie ukryta. Korpus: **443 dokumenty**. `total` zgłoszony dla okien
czerwiec–grudzień: od 169 (2010) do 2 898 (2025).

---

## Pomiar 5, część rocznikowa — segmentacja na korpusie 443 dokumentów (etap II–III fazy 2)

**Policzone 2026-09-19 z bazy, 0 żądań**, po Przebiegu 3. `parser/sections.py` przyłożony do
widoku z `parser/clean.py`:

| Sekcja | Dokumentów z sekcją |
|---|---|
| nagłówek, sentencja, pouczenie, uzasadnienie | 443 z 443 (100 %) |
| nieprzypisane | 0 znaków z 13 498 909 |

Długości sekcji (znaki): nagłówek mediana 655 (max 2 519), sentencja 510 (max 6 593 — rozbudowane
wyroki z punktami zarzutów, przejrzane okiem), pouczenie 243 (max 503), uzasadnienie 17 686.

**Normalizacja podniosła trafienie nagłówka uzasadnienia z 63,0 % do 97,3 %.** Reszta idzie
drogami zastępczymi, każda znaleziona na konkretnym dokumencie i opisana w kodzie: `postanawia` bez
dwukropka (`KIO 3884/23`), punkt wyliczenia doklejany do nagłówka (`KIO 3778/23`), strona
uzasadnienia otwarta powtórzoną sygnaturą, uzasadnienie wprost pod podpisem w roczniku 2012
(`KIO 1004/12`), nagłówek wklejony przez ekstrakcję w wiersz podpisu (`KIO 3700/23`).

**100 % pokrycia nie jest dowodem poprawności granic** — algorytm przypisuje każdy znak, jeśli
znajdzie choć jedną kotwicę. Jedynym sprawdzianem granic jest złoty zbiór (Z-11) i raport pokrycia;
dlatego długości sekcji stoją wyżej, a odstające przejrzano ręcznie.

---

## Pomiar 22 — gęstość cytowań i udział nieznormalizowanych

**Policzone 2026-09-19 z bazy, 0 żądań**, na 443 dokumentach, w sekcjach `uzasadnienie`
i `zdanie_odrebne`, bez sygnatur własnych dokumentu.

| Rodzaj | Cytowań |
|---|---|
| KIO | 1 260 |
| sąd okręgowy | 165 |
| Sąd Najwyższy | 99 |
| TSUE | 60 |
| sąd apelacyjny | 19 |
| NSA | 11 |
| **nierozpoznane** (`sygn. akt` bez rozpoznanej sygnatury) | **81** (78 po poprawce pouczenia — niżej) |
| razem | 1 695 |

Cytowania ma 194 z 443 dokumentów. **Udział nierozpoznanych: 81 z 1 695 = 4,8 %** — na granicy
progu „kilku procent" z decyzji 8 architektury. Postaci nierozpoznane, od najczęstszej: sam numer
bez prefiksu (`3376/23`), sygnatura bez numeru (`IV CR 403`), rok czterocyfrowy przy KIO
(`KIO 1460/2011`), prefiks `KIO/KD`, repertoria WSA (`II SA/Wa`). **`docid` ich nie dostał** —
czterocyfrowy rok KIO wymagałby skracania roku, a `KIO/KD` nie ma odczytu z datą poza tym jednym
cytowaniem; oba zostają do decyzji z pomiarem na większym korpusie.

**Przepisy: treść ↔ kanał.** Z treści 13 697 powołań; z `law_articles` Atlasu 3 137 pozycji,
z których **3 137 (100 %) ma tę samą postać kanoniczną w treści** dokumentu — pośrednik nie dodaje
przepisów spoza tekstu. **Druga strona zawierania** (dopisana po przeglądzie kodu 2026-09-19,
liczona na różnych postaciach per dokument): z 6 397 postaci przepisów w treści lista kanału
wymienia **3 137 (49,0 %)** — `law_articles` Atlasu jest wyborem przepisów, nie ich spisem, więc
filtr `--przepis` na kanale pomija orzeczenia, które przepis powołują, a Atlas go nie wybrał. Ustawa z treści (Z-8): `pzp2019` 5 789, `pzp2004` 1 905, `kc` 595,
`inne` 557, `rozporzadzenie` 87, `kpc` 26, **`nieustalone` 4 738 (34,6 %)**. Wysoki udział
nieustalonych bierze się ze 101 dokumentów, które nie nazywają żadnej ustawy Pzp pełnym tytułem
(95 z nich z roku 2024) — zgadywanie z daty dałoby tam „trafny" wynik i Z-8 go zakazuje.

---

**Aktualizacja tego samego dnia.** Przegląd złotego zbioru przesunął granicę pouczenia w 4 z 17
dokumentów (niżej), więc uzasadnienie w kilku dokumentach zaczyna się teraz gdzie indziej.
Raport pokrycia z 2026-09-19 (`docs/raporty/pokrycie_2026-09-19.md`) podaje **78 nierozpoznanych
z 1 695 (4,6 %)** — to jest liczba obowiązująca; 81 powyżej to stan sprzed poprawki, zostawiony
jako zapis kolejności.

---

## Przegląd złotego zbioru — granice sekcji przejrzane okiem (ADR-0006 Z-11)

**2026-09-19, 0 żądań.** Po jednym dokumencie z każdego rocznika próbki (pierwszy dokument każdego
przebiegu rocznikowego z Przebiegu 3): 17 dokumentów, 2010–2026. Każda granica wypisana z 50
znakami przed i 60 po i przejrzana okiem przez Claude'a w sesji; adnotacje leżą w `tests/gold/`
jako offsety i SHA-256 fragmentów, **bez tekstu**.

**Przegląd znalazł usterkę, której nie widziała żadna liczba zbiorcza:** w 4 z 17 dokumentów
(roczniki 2010, 2020, 2021, 2023) pouczenie zaczynało się w pół zdania — wstęp „Stosownie do
art. 198a i 198b ustawy … (Dz. U. … Nr 219, poz. 1706 i Nr 223, poz. 1778)" był dłuższy niż okno
300 znaków, a wcześniejsza reguła szukała początku wyłącznie w wierszu `przysługuje skarga`.
Pokrycie 443 z 443 było przy tym stuprocentowe — dokładnie ten przypadek, dla którego ADR-0006 Z-12
nazywa raport liczbowy niewystarczającym bez złotego zbioru. Po poprawce (`sections._pouczenie`:
najbliższe `Stosownie do` w oknie 700 znaków, potem `Na orzeczenie`/`na niniejszy …`) wszystkie
17 granic pouczenia stoi na początku zdania; długość pouczenia na korpusie: mediana 248, max 562.

Dwie granice uzasadnienia stoją na drogach zastępczych i zostały uznane za poprawne: `KIO 1003/18`
(brak nagłówka; strona uzasadnienia otwarta sygnaturą z literówką w źródle, `1003/19`)
i `KIO 915/19` (brak nagłówka i sygnatury; uzasadnienie pod podpisem).

**Czym ten zbiór jest, a czym nie jest.** Adnotacje wygenerowano z wyjścia parsera **po** przeglądzie
i poprawce, więc dziś zgadzają się z nim 17 na 17 z definicji. Ich wartość to (1) przegląd, który
już znalazł jedną usterkę, i (2) strażnik regresji: każda przyszła zmiana `clean`/`sections`, która
przesunie którąkolwiek z 68 granic, pokaże się w raporcie jako rozbieżność. **Przegląd wykonał
Claude, nie właściciel** — pole `przeglad.kto` mówi to w każdym pliku; potwierdzenie przez
właściciela jest częścią przyjęcia fazy.

---

## Pomiar 10 — ślady anonimizacji w treści (liczby, bez przykładów)

**Policzone 2026-09-19 z bazy, 0 żądań**, na 443 dokumentach. Wyłącznie liczby — przykłady
niosłyby dane osobowe.

| Wzorzec | Dokumentów | Wystąpień |
|---|---|---|
| `Przewodniczący:` z imieniem i nazwiskiem | 404 | 404 |
| `Protokolant:` z imieniem i nazwiskiem | 286 | 286 |
| inicjały `A. B.` | 266 | 2 145 |
| `(...)` / `(…)` | 175 | 894 |
| `[...]` / `[…]` | 19 | 36 |
| słowo „zanonimizowan…"/„anonimizac…" | 9 | 22 |
| `***` | 2 | 6 |
| `XXX` | 0 | 0 |

**Wniosek: skład orzekający i protokolant nie są anonimizowani** (404 i 286 dokumentów z pełnym
nazwiskiem). Wielokropki w nawiasach to w przeważającej części opuszczenia w cytatach, nie
anonimizacja — tego rozróżnienia wzorzec nie robi i liczba jest górnym oszacowaniem. Inicjały mogą
być skrótami nazw firm albo osób; bez przeglądu okiem nie wiadomo, które. Ten pomiar jest
uzasadnieniem liczbowym ADR-0006 Z-11 („złoty zbiór bez treści") i reguły, że korpus leży poza
repozytorium.

---

## Pomiar 3b — opóźnienie publikacji u pośrednika (w toku, jeden kanał)

**Stan 2026-09-19: procedura ustalona, zero odczytów.** Ta sekcja gromadzi kolejne odczyty;
wynik pojawi się wtedy, gdy szereg będzie miał co powiedzieć, a nie przy pierwszym wierszu.

**Dlaczego brzmienie pierwotne jest niewykonalne.** Audyt 10 opisuje pomiar 3 metodą „pobrać tę
samą sprawę z Atlasu i z UZP, porównać treść i datę pojawienia się". Kanał `uzp` nie istnieje,
a decyzja B odbiera mu rolę masową — drugiej połowy porównania nie ma skąd wziąć. Droga przez
pytanie do dostawcy jest zamknięta decyzją A. Zostaje obserwacja jednego kanału w czasie i to
jest zmiana definicji pomiaru, nie jego wykonanie: zapisana tutaj, żeby nikt nie wziął jednej
wielkości za drugą.

**Co mierzy wersja jednokanałowa — i czego nie mierzy.** Mierzy **wiek najświeższego orzeczenia
w Atlasie**: różnicę między dniem odczytu a najpóźniejszą datą wydania, dla której Atlas ma
jakikolwiek dokument, oraz to, jak liczność świeżych dni rośnie przy kolejnych odczytach
(dopełnianie wstecz). **Nie mierzy** opóźnienia Atlasu względem UZP — to jest inna wielkość
i ta procedura jej nie zastępuje. Odpowiada natomiast na pytanie, które projekt ma naprawdę:
jak świeży jest korpus, jeśli pobiorę go dzisiaj.

**Procedura — jeden odczyt dziennie, jedno żądanie.**
`GET /api/kio?date_from={dziś−14}&date_to={dziś}&sort=oldest&per_page=100`, bez pobierania
dokumentów. Z odpowiedzi zapisuje się: dzień odczytu, `total`, najpóźniejszą `ruling_date`
w `data[]` oraz liczność per dzień dla ostatnich czternastu dni. Okno czternastodniowe, bo
krótsze nie pokaże dopełniania wstecz, a dłuższe kosztuje kolejne strony. Zastrzeżenie
przeniesione z pomiaru 3a: `ruling_date` bywa błędne (9 na 100 rekordów), więc „najpóźniejsza
data wydania" bywa datą pomyłki, a nie datą publikacji — dlatego obok niej stoi liczność,
której pojedyncza pomyłka nie przesuwa.

| Dzień odczytu | `total` | Najpóźniejsza `ruling_date` | Wiek w dniach | Uwaga |
|---|---|---|---|---|
| — | — | — | — | pierwszy odczyt czeka na adres kontaktowy operatora |

---

## Przegląd kodu fazy 3 — znaleziska i co z nimi zrobiono (2026-09-20)

Przegląd zakresu `e8e595b~1..HEAD` (10 commitów, 50 plików) wykonany po zamknięciu prac fazy 3;
w sesji z 2026-09-19 nie doszedł do skutku, bo agenta ubił limit sesji. Zero żądań do sieci —
wszystkie liczby niżej pochodzą z atrap i z korpusu operatora.

**Jedno znalezisko wysokiej wagi, zmierzone i naprawione.** Werdykt `zgoda` zdejmował próg
`PROG_ZGODY` na resztę wywołania zamiast wiązać zgodę z liczbą, którą operator zobaczył.
Odtworzone na atrapie zgłaszającej `total = 5` przy trzech stronach po sto rekordów: tabela
kosztów pokazała „5 żądań, 4 s", pytanie miało wtedy domyślne „tak" (bo przebieg nie jest
masowy), a po Enterze wyszły **103 żądania przy progu 50** — rozjazd widoczny dopiero
w podsumowaniu, czyli po wydatku. Naprawa w ADR-0008 §12.1: zgoda niesie sufit
`(wycena + już wysłane) × proby z kontraktu`, przekroczenie kończy przebieg jako `przerwany`
ze zdaniem wymieniającym obie liczby. Sufit sprawdzony mutacją (wyłączony warunek zapala test).

**Trzy znaleziska średniej wagi.** Arkusz `Metadane` eksportu pokazowego twierdził
`organ = Krajowa Izba Odwoławcza` i powtarzał atrybucję licencyjną Atlasu — znacznik `tryb` mówił
prawdę, a dwa wiersze niżej ten sam arkusz przypisywał fikcję realnemu organowi i realnemu
dostawcy (ADR-0008 §12.3). Generator korpusu pokazowego doklejał numer sprawy połączonej bez
patrzenia na pulę, więc **7 z 384** dokumentów miało drugą sygnaturę będącą sygnaturą główną
innego dokumentu (§12.4). `PARSE_VERSION` nie został podniesiony przy zmianie `docid`
z 2026-09-19 (ADR-0006 §10.2) — tu skutek na tej bazie **nie wystąpił**, bo korpus był po tamtej
zmianie przeliczony ręcznie: zmierzone po podniesieniu wersji do 3 i przeliczeniu 443 wersji
(0 żądań) — 1 118 różnych sygnatur cytowanych przed i po, zero z rokiem czterocyfrowym w obu.
Brakowało obserwatora, nie danych; obserwatorem jest odtąd odcisk źródeł odczytu.

**Siedem drobnych.** `KIO_TOOL_DEMO_TEMPO=nan` przechodziło przez `float()` i wywracało pokaz
w środku ścieżki; `zbuduj_pokaz` stał przed obsługą błędów, więc zła konfiguracja pokazu dawała
ślad stosu i kod 1 zamiast zdania i kodu 3; koniec wejścia w kreatorze kończył się angielskim
„Aborted." z kodem 1; stała `UDZIAL_PELNEGO_TYTULU = 327 / 443` przepisywała ręcznie sumę dwóch
liczb z `wzorce.yaml`; `czas_ludzki` dawało „22 dób" zamiast „22 doby"; kreator proponował eksport
także po błędzie wyszukiwania i przy zerze trafień; sufit 800 linii żył wyłącznie w prozie przy
dwóch modułach powyżej (`store.py` 1 466, `pipeline.py` 971). Wszystkie naprawione, każda
z obserwatorem.

**Co przegląd potwierdził.** Punkt decyzji nie kosztuje żądania i jest mierzony kosztem, nie
wywołaniem funkcji; reguła 10 obejmuje `questionary` razem z samosprawdzeniem skanu w obie
strony; `wzorce.yaml` jest generowany ze zmierzonego wejścia z SHA-256 i białą listą kluczy
czytaną ze skryptu, nie z pamięci; wrogie napisy stoją w samym korpusie pokazowym, nie tylko
w prozie o nim.

---

## Pomiar 25 — postaci sygnatur nierozpoznanych w cytowaniach (O-3)

Wykonany 2026-09-20 na korpusie operatora, **0 żądań**: 78 cytowań, przy których zapowiedź
`sygn. akt` stała, a postaci kanonicznej nie dało się zbudować (pomiar 22 policzył je, nie
rozebrał). Każda rodzina niżej jest odczytem z tych 78 napisów, żadna nie pochodzi z pamięci.

| Rodzina | Trafień | Udział | Przykłady | Stan |
|---|---|---|---|---|
| A — sam numer, bez repertorium | 29 | 37,2 % | `sygn. akt: 3376/23`, `sygn. akt 1004/09` | wdrożone jako **osobny rodzaj** `kio_bez_repertorium` (decyzja właściciela) |
| B — KIO z ukośnikiem przed numerem | 3 | 3,8 % | `KIO/582/11`, `KIO/1945/10` | wdrożone |
| C — Zespół Arbitrów UZP i `KIO/UZP` | 4 | 5,1 % | `UZP/ZO/0-62/07`, `KIO/UZP 782/2009` | wdrożone |
| D — repertoria kontrolne Izby | 10 | 12,8 % | `KIO/KD 44/11`, `KIO/W 2/24` | wdrożone |
| E — rok czterocyfrowy przy KIO | 2 | 2,6 % | `KIO 1460/2011` | wdrożone |
| F — sądy administracyjne z kodem siedziby | 7 | 9,0 % | `II SA/Op 4/18`, `II GSK/WA 3487/15` | wdrożone |
| G — Trybunał Konstytucyjny bez wydziału | 3 | 3,8 % | `SK 22/08`, `K 13/07` | **nie wdrożone — kolizja z repertorium SN** |
| H — TSUE bez myślnika | 3 | 3,8 % | `C 106/77`, `C387/14` | **nie wdrożone — pomiar odrzucił** |
| I — sklejka bez spacji | 6 | 7,7 % | `IICSK 197/15`, `X Ga254/10` | **nie wdrożone — ryzyko fałszywych trafień** |
| J — nie do odzyskania | 11 | 14,1 % | `IV CR 403` (bez roku), `KIO 7 1 3`, `IPRN` | zostaje nierozpoznane |

**Wynik wdrożenia.** Wersja odczytu 4 (sześć rodzin postaci) zdjęła nierozpoznanych
**78 → 52**; wersja 5 (rodzina A jako osobny rodzaj) **52 → 23** na 1 708 cytowaniach, czyli
z 4,6 % do **1,3 %**. Przybyło 38 cytowań rozpoznanych — 18 KIO, 12 WSA, 7 Zespołu Arbitrów,
1 NSA — i **każde z nich zostało przejrzane okiem**, po jednym wierszu z kontekstem; żadne nie
okazało się fałszywe. Rodzina A dała dokładnie 29 trafień, ani jednego więcej: wzorzec sam numer
dopasowuje **tylko** od końca zapowiedzi `sygn. akt`, więc numery stron, kwoty i odesłania do
przepisów go nie wyzwalają. Raport: `docs/raporty/pokrycie_2026-09-20.md`.

### Rodzina H — pomiar, który odrzucił własną hipotezę

Tolerancja na brak myślnika w sygnaturze TSUE wyglądała na zysk darmowy: trzy prawdziwe sygnatury
(`C 106/77` Simmenthal ×2, `C 689/13` PFE) zapisano bez myślnika. Przeliczenie całego korpusu
z myślnikiem opcjonalnym dało **3 trafienia poprawne i 12 fałszywych**:

- **9 × klasa betonu z kosztorysu.** PN-EN 206 zapisuje wytrzymałość dokładnie tak: `C12/15`,
  `C20/25`, `C30/37`, `C35/45`. Kontekst z korpusu: „Ława pod krawężniki betonowa z oporem
  z betonu C12/15", „wycenił beton klasy wyższej tj. C35/45".
- **3 × numer Dziennika Urzędowego UE serii C.** „(2014/C 92/01)", „(Dz.U.UE C z dnia 18 marca
  2021 r. 2021/C 91/01)".

Odwołania o roboty drogowe są pełne jednego i drugiego, więc myślnik zostaje obowiązkowy, a trzy
sygnatury zostają nierozpoznane. Zapisane tutaj, bo następna sesja zobaczy te trzy trafienia
i pomyśli to samo co ta.

### Czego pomiar nie rozstrzyga

**Rodzina A — rozstrzygnięta przez właściciela 2026-09-20: osobny rodzaj.** Napis
`sygn. akt: 3376/23` wewnątrz uzasadnienia Izby jest niemal na pewno sygnaturą KIO, ale „niemal
na pewno" nie jest pomiarem. Sprawdzenie na korpusie: **11 z 29 numerów** ma odpowiednik
`KIO N/RR` gdzie indziej w tym samym korpusie (`3376/23`, `1020/23`, `1131/11`, `1900/11`,
`2025/14`, `351/23`), pozostałych 18 nie da się potwierdzić niczym poza kontekstem.

Właściciel wybrał wariant pośredni: sygnatura kanoniczna jest **pełna** (`KIO 3376/23`), żeby
łączyła się z indeksem cytowań, a informacja o tym, że organ **dopisaliśmy z kontekstu, a nie
odczytali z zapisu**, stoi w `citations.rodzaj` jako `kio_bez_repertorium`. Tylko tam przeżyje
drogę do raportu i do każdego przyszłego czytelnika, który może te 29 cytowań wykluczyć jednym
warunkiem. Wrzucone do `kio` byłyby nie do odróżnienia od odczytanych; zostawione jako
nierozpoznane byłyby stratą największej rodziny. Zdanie z nagłówka `docid.py` — „nie zgaduje
organu z samego numeru" — zostaje prawdziwe dla `znajdz_sygnatury`: sam numer rozpoznaje osobna
funkcja, wołana wyłącznie zza zapowiedzi.

**Rodzina G (3)** wymagałaby wzorca bez wydziału (`K 13/07`), a `SK` stoi już w repertoriach Sądu
Najwyższego — tam odróżnia je wydział rzymski, którego Trybunał nie ma. Wzorzec na dwie litery
i liczbę bez żadnej kotwicy jest w tym korpusie ryzykiem tego samego rodzaju co klasa betonu.

**Rodzina I (6)** to ekstrakcja z PDF-a, która zjadła spację (`X Ga254/10`). Rozluźnienie
separatorów we wzorcu sądu dotyczy **wszystkich** sygnatur sądowych naraz, więc kosztem byłby
pomiar na całym korpusie, nie na sześciu napisach.

---

## Przegląd okiem cytowań i przepisów złotego zbioru (O-4, 2026-09-20)

Złoty zbiór niósł do tej pory **wyłącznie granice sekcji**, a ADR-0006 §10.1 mówił dlaczego:
cytowań i przepisów nikt nie przejrzał, a adnotacja parsera napisana przez samego parsera jest
gorsza niż jej brak. Ten przegląd zamyka tamten brak. Zero żądań — wszystko z bazy operatora.

**Co przejrzano.** 91 cytowań w 17 dokumentach — **każde z osobna**, z jednym wierszem kontekstu.
Przepisy: 226 różnych postaci z treści plus postaci z listy kanału; przegląd objął **postaci**,
a nie każde z 856 wystąpień, i adnotacja jest zapisana dokładnie w tej granulacji (cytowania per
wystąpienie, przepisy per postać z liczbą). Adnotacja nie ma prawa twierdzić więcej, niż objął
przegląd.

**Cytowania: zero rozbieżności.** Sprawdzone zostało też jedno podejrzenie — `KIO 385/14`
występuje 14 razy w jednym dokumencie (`atlas:kio-985-14`, sygnatura własna `KIO 985/14`).
Kontekst pokazał, że to nie artefakt stopki ani sygnatury własnej: całe odwołanie dotyczy
wykonania wcześniejszego wyroku w tym samym postępowaniu.

**Przepisy: dwie usterki parsera, obie znalezione okiem i obie naprawione.**

1. **Mianownik „ustawy Prawo zamówień publicznych" nie był rozpoznawany.** Wzorzec
   `prawa?\s+zamówień` wymagał po „praw" spacji albo „a", a w mianowniku stoi „o". Skutek był
   cichy i mylący, bo pole dostawało wartość **poprawną co do typu**: w zdaniu o kosztach
   („orzeczono na podstawie art. 574 i 575 ustawy Prawo zamówień publicznych oraz § …
   rozporządzenia…") wygrywało następne oznaczenie w oknie i przepis Pzp lądował jako przepis
   **rozporządzenia**. Na korpusie 443 dokumentów poprawka przeniosła **260 przepisów**:
   `nieustalone` −220, `rozporzadzenie` −35, `kc` −4, `inne` −1, a `pzp2019` +153 i `pzp2004` +107.
   Cztery przepisy przeszły z `kc` na `nieustalone` — z wartości **błędnej** na uczciwą.
2. **Data ustawy zapisana cyframi.** „ustawy z dnia 29.01.2004 r. Prawo Zamówień Publicznych"
   dawało `inne`, bo generyczne „ustawy z dnia" stoi w tym samym miejscu co pełny tytuł, a przy
   remisie wygrywa wzorzec zadeklarowany wcześniej. Zapis cyfrowy ma w korpusie **3 wystąpienia
   w 3 dokumentach** — mało, ale każde z nich dawało wartość błędną, a nie brakującą.

Żadnej z tych dwóch nie mógł zapalić automat: `rozporzadzenie` i `inne` są poprawnymi wartościami
pola `provisions.akt`, więc raport pokrycia liczył je bez mrugnięcia. To jest dokładnie ten rodzaj
usterki, dla którego ADR-0006 Z-11 wymaga człowieka przy adnotacji.

**Potwierdzenie właściciela (2026-09-20).** Właściciel potwierdził przegląd cytowań i przepisów
w tej samej sesji, w której powstał. Pole `przeglad.kto` w `tests/gold/*.json` mówi odtąd jednym
zdaniem: przejrzane okiem — granice sekcji 2026-09-19, cytowania i przepisy 2026-09-20 — i całość
potwierdzona przez właściciela 2026-09-20. Zmieniło się **wyłącznie to pole**; liczby i granice
w adnotacji są bit w bit te same, bo potwierdzenie dotyczy tego, co przejrzano, a nie tego, co
parser odczytał.

**Czego ten przegląd nie zamyka.** Postać `art. 3531` (czyli `art. 353¹` po ekstrakcji z PDF-a)
zostaje taka, jaka jest — to wierny zapis tego, co przyszło z kanału, a nie usterka parsera;
poprawianie go wymagałoby wiedzy o indeksie górnym, której w tekście nie ma. Pole `przeglad.kto`
w plikach złotego zbioru niesie odtąd **dwa fakty naraz i ich nie zrównuje**: granice sekcji
przejrzał Claude 2026-09-19 i potwierdził właściciel 2026-09-20, a cytowania i przepisy przejrzał
Claude 2026-09-20 i **nie są jeszcze potwierdzone**.

---

## Przejście operatora — tryb pokazowy (2026-09-20)

Bramka fazy 3 §10 pkt 5 (ADR-0008 §11 pkt 5: wykonuje sam właściciel). Właściciel przeszedł
`kio-tool demo` i zgłosił **trzy usterki interfejsu**; wszystkie naprawione przed przyjęciem,
zgodnie z brzmieniem kryterium („każde pytanie przejścia jest usterką zdania albo kroku").

1. **Zaznaczenie chodziło strzałkami, podświetlenie stało w miejscu.** Dwie przyczyny naraz:
   `questionary.select(default=…)` wkłada wartość domyślną do `selected_options`, a klasa
   `selected` wygrywa przy rysowaniu z `pointed_at` — wiersz domyślny zostawał oznaczony na
   stałe; do tego domyślny motyw podświetla kolorem, którego ta konsola nie pokazuje. Ten sam
   defekt został znaleziony w `ceidg-tool` 2026-09-09, więc poprawka jest przeniesiona razem
   z powodem: bez `default=`, domyślna opcja na czele listy, jawny styl `reverse bold`.
2. **Pytania tak/nie po cichu pomijały polskie odpowiedzi.** `questionary.confirm` wiąże na
   sztywno `y` i `n`; wpisane „tak" dawało odpowiedź domyślną bez żadnego sygnału. Zamienione
   na pole tekstowe z klamrą `[T/n]`, zbiorami dokładnych odpowiedzi i jednym dopytaniem.
3. **Za mało informacji dla kogoś, kto narzędzia nie zna** — „nie będzie wiedzieć, co należy
   wpisać". Dopisane: podpowiedź przy **każdym** pytaniu tekstowym (format daty, przykład,
   znaczenie pustej odpowiedzi), pozycje menu mówiące, co robią i czy kosztują żądania, oraz
   pierwszy ekran ze stanem korpusu i czterema zdaniami o obsłudze. Wzorzec z `ceidg-tool`,
   gdzie pozycja menu niesie koszt w żądaniach, a każde pytanie tekstowe ma podpowiedź.

Asystent językowy **nie wchodzi** w tym zakresie — decyzja właściciela z tego samego dnia
(niżej, „Świadomie odłożone").

---

## Przyjęcie faz 2 i 3 (2026-09-20)

**Właściciel przyjął fazy 2 i 3**, w tym pozostałe kryteria obu bramek, oraz **potwierdził
złoty zbiór** (17 dokumentów, 68 granic sekcji; pole `przeglad.kto` w `tests/gold/*.json` mówi
odtąd, że przegląd wykonał Claude, a właściciel go potwierdził). Fazę kończy przyjęcie, nie
zielona suita — od tej daty fazy 2 i 3 są zamknięte.

Stan w chwili przyjęcia: 1 319 testów, `ruff check`, `ruff format --check`,
`mypy kio_tool scripts` — zielone; raport pokrycia `docs/raporty/pokrycie_2026-09-20.md`
(443 dokumenty, 443 z kompletem sekcji, złoty zbiór 17 z 17 zgodnych, 0 żądań).

Co przyjęcie **nie** obejmuje: fazy 4 (bramka warunkowa stoi przed nią i jest nietknięta) ani
pozycji z listy niżej.

---

## Świadomie odłożone — lista otwarta, nie zapomniana (2026-09-20)

Decyzja właściciela: te pytania **nie** blokują przyjęcia faz 2 i 3 i wracają później. Zapisane
tutaj, bo pozycja odłożona bez zapisu jest nie do odróżnienia od przeoczonej.

| # | Pytanie | Dlaczego odłożone | Co je odblokuje |
|---|---|---|---|
| O-1 | `Retry-After` przy 5xx nie przeżywa `wznow` — historia żądań odtwarza go tylko dla 429, więc natychmiastowy `wznow` po wyczerpaniu prób nie czeka na prośbę serwisu (ADR-0007 §8.1) | Z-4 domyka lukę w obrębie procesu; poza nim kosztowałaby zmianę schematu dziennika | Pomiar 24 — dopiero on powie, jak często 5xx w ogóle wyczerpuje próby |
| O-2 | Pomiar 24: awaryjność kanału i skuteczność ponowień (ADR-0007 Z-8) | Wymaga pierwszego przebiegu kwartalnego **po** wdrożeniu ponowień; danych jeszcze nie ma | Pierwszy duży przebieg na `requests_log.proba`, zero żądań dodatkowych |
| O-3 | Postaci sygnatur nierozpoznane w pomiarze 22 | **zamknięte pomiarem 25 (2026-09-20)**: 78 → 23 nierozpoznanych (4,6 % → 1,3 %), siedem rodzin wdrożonych wraz z rodziną A jako `kio_bez_repertorium` | — (zostają trzy rodziny z powodem: TSUE bez myślnika, Trybunał bez wydziału, sklejka po ekstrakcji z PDF-a) |
| O-4 | Złoty zbiór nie niesie cytowań ani przepisów (ADR-0006 §10.1) | **zamknięte w całości 2026-09-20**: przegląd okiem 91 cytowań i 226 postaci przepisów, dwie usterki parsera znalezione i naprawione, **przegląd potwierdzony przez właściciela** tego samego dnia | — |
| O-5 | `store.py` (1 466 linii) i `pipeline.py` (971) ponad sufitem 800 | Rozbicie w bramce fazy 3 byłoby zmianą struktury tuż przed przyjęciem | Dług fazy 4; do tego czasu oba mają wpis z pomiarem i **nie mogą urosnąć** (`test_boundaries.py`) |
| O-6 | Asystent językowy (wzorzec `ceidg-tool/assistant`) | **zamknięte odmownie 2026-09-20**: właściciel zrezygnował — pozycja schodzi z listy jako „nie", nie jako „później" (sekcja „Asystent językowy — rezygnacja, nie odłożenie") | — (wraca wyłącznie z nowym ADR-em; bramka AI Act przed fazą 4 stoi niezależnie, bo serwer MCP też oddaje tekst modelowi) |
| O-7 | Pomiary odłożone do innych kanałów i faz: 2a, 2b, 4b, 7, 9, 16, 18, 19, 20 | Dotyczą kanałów `uzp`/`saos` albo fazy 4, których drzewo nie ma; **co każdy z nich dałby projektowi — sekcja „Co dałyby pomiary kanałów `uzp` i `saos`" (2026-09-20)** | Decyzja o drugim kanale albo wejście w fazę 4 |

---

## Domknięcie projektu przed prezentacją — sześć decyzji (2026-09-20)

Runda pytań zamykająca projekt. Zapisane razem, bo razem zapadły i razem tłumaczą stan drzewa,
który zobaczy odbiorca prezentacji.

| # | Pytanie | Decyzja właściciela | Skutek |
|---|---|---|---|
| 1 | Otwarty PR #2 na GitHubie | **Zamknąć bez scalania** | Zamknięty 2026-09-20 z komentarzem wyjaśniającym; niósł stan sprzed sześciu commitów, więc opisywał wersję, której już nie ma. Gałąź zdalna zostaje nietknięta |
| 2 | Przegląd cytowań i przepisów (O-4) | **Potwierdzony** | `przeglad.kto` w 17 plikach niesie jedno zdanie zamiast dwóch faktów o różnym statusie; O-4 zamknięte w całości |
| 3 | Rozbicie `store.py` (1 466) i `pipeline.py` (971) — O-5 | **Zostaje długiem** | Rozbijanie 2 437 linii tuż przed oddaniem to ryzyko regresu bez zysku dla odbiorcy. Sufit w `test_boundaries.py` pilnuje, że nie urosną, a pozycja idzie na slajd jako **zmierzony dług**, nie jako cisza |
| 4 | Gałąź `feat/odlozone-sygnatury` | **Scalona lokalnie do `master`** | Sześć commitów przewinięte do przodu bez scalenia-commita; **nic nie wysłane** |
| 5 | Odbiorca prezentacji | **Zarząd**, rejestr jak w `ceidg-tool` | `docs/prezentacja/plan.md` §0 |
| 6 | Forma prezentacji | Sama wersja **ekranowa**, ekrany jako **makiety HTML** z trybu pokazowego, narzędzie **stoi samo** | `docs/prezentacja/plan.md` §0 |

Decyzja 3 zasługuje na zdanie więcej, bo wygląda jak odpuszczenie, a nim nie jest. Dług, który
ma **wpis z pomiarem, zakaz wzrostu i strażnika w suicie**, jest czymś innym niż dług przemilczany:
pierwszy jest stanem wybranym, drugi — stanem odkrytym po czasie. Na slajdzie ma paść w tej
pierwszej postaci.

Po tej rundzie otwarte zostają **O-1, O-2, O-5 i O-7** — i wszystkie cztery z tego samego powodu:
trzy wymagają przebiegu z siecią albo decyzji o drugim kanale, a czwarty jest świadomym długiem.
Żadna z nich nie blokuje przekazania narzędzia.

---

## Asystent językowy — rezygnacja, nie odłożenie (2026-09-20)

Właściciel zrezygnował z asystenta językowego. O-6 schodzi z listy odłożonych jako **„nie"**,
a nie jako „później", i ta różnica jest istotna: pozycja odłożona wraca sama, pozycja
rozstrzygnięta odmownie wraca wyłącznie z nowym ADR-em.

**Co to potwierdza.** `ARCHITEKTURA_KIO_TOOL.md` §3.8 i rekomendacja 3 kształtowały fazę 4 jako
**lokalny serwer MCP nad korpusem, a nie asystenta wbudowanego w proces**, i podawały powód:
granica z reguły 13 staje się wtedy granicą procesu, a ADR o wysyłaniu treści do modelu jest
jedną linią konfiguracji zamiast zależności w drzewie. Decyzja właściciela zbiega się z tym
kształtem i czyni go rozstrzygnięciem, a nie preferencją architekta.

**Co z drzewa znika na stałe.** Nie wchodzi SDK modelu, więc nie wchodzi drugi właściciel klienta
HTTP (reguła 11), drugie wyjście z procesu ani łańcuch poświadczeń, którego nikt nie deklarował —
w `ceidg-tool` to była reguła 12 z dwiema połowami i całym jej ciężarem (`api_key=`
i `http_client=` wypisane w każdym wywołaniu, bo bez nich SDK buduje własny transport poza bramką
wyjścia). Zdanie „narzędzie nie wysyła żądań poza kanał, z którego pobiera" zostaje prawdziwe
**bez wyjątku i bez flagi** — a takie zdanie jest sprawdzalne przez przeczytanie jednego modułu.

**Czego ta decyzja nie zdejmuje.** Bramka warunkowa przed fazą 4 stoi nietknięta. Serwer MCP
oddaje tekst orzeczenia modelowi po drugiej stronie, więc pytanie „czy treść orzeczenia wolno
wysłać do modelu" wraca w całości, tak samo jak konfrontacja opisu przeznaczenia z załącznikiem
III AI Act (audyt 9, 12). Rezygnacja z asystenta usuwa **drugą** drogę, która musiałaby
odpowiedzieć na to pytanie osobno — nie samo pytanie.

**Co użytkownik dostaje zamiast.** Kreator mówi wprost, co wpisać (ADR-0008 §12): podpowiedź przy
każdym pytaniu tekstowym, blok `JAK_TO_DZIALA` na pierwszym ekranie, etykiety kosztu i kontekstu
przy pozycjach menu, stan korpusu nad pytaniem. To jest ta część inspiracji z `ceidg-tool`, która
nie wymaga modelu, i właściciel wybrał ją w całości.

---

## Co dałyby pomiary kanałów `uzp` i `saos` — wyjaśnienie O-7 (2026-09-20)

O-7 wygląda na worek z dziewięcioma numerami. Nie jest workiem: te dziewięć pomiarów odpowiada na
**trzy** pytania, a każde z nich rozszerza projekt w inną stronę i za inną cenę.

### Pytanie 1: czy korpus może sięgnąć przed rok 2010 (`saos`, pomiary 2a i 2b)

Zmierzone, nie przypuszczane: najstarszy dokument w korpusie operatora ma rocznik **2010**
(443 dokumenty, roczniki 2010–2026, raport pokrycia 2026-09-20, 0 żądań), a pomiar 3a odczytał
u pośrednika to samo — zbiór Atlasu sięga rocznika 2010. KIO orzeka od **grudnia 2007**. Odcinek
**2007-12 – 2009** nie jest więc w tym narzędziu niedostępny przez błąd ani przez limit: on po
prostu **nie istnieje w kanale, którego używamy**, i żadna liczba żądań tego nie zmieni.

SAOS deklaruje 22 168 rekordów za okres 2007-12 – 2018-09. Pomiar **2a** pyta o jedną rzecz: czy
**Dump API** odpowiada naszemu własnemu klientowi — bo API **wyszukiwania** SAOS zablokowało dwa
niezależne klienty, w tym na przykładzie z własnej dokumentacji SAOS („bot detection"), a korzeń
`www.saos.org.pl` nie odpowiedział w 45 s przy pomiarze 23. Pomiar **2b** pyta, czy Dump API
filtruje po `courtType`, czyli czy da się wziąć samo KIO zamiast całego orzecznictwa Polski.

**Co by to dało projektowi.** Trzy brakujące roczniki — i **drugi kanał**, co znaczy dużo więcej
niż „więcej danych". Drugi kanał jest jedyną drogą do polecenia `porownaj`, czyli do zobaczenia
tego samego orzeczenia z dwóch niezależnych źródeł; do pomiaru 3b w brzmieniu pierwotnym
(opóźnienie publikacji jako różnica między kanałami, a nie obserwacja kalendarzowa); i do
odpowiedzi na pytanie, którego dziś nie umiemy zadać: **czy pośrednik czegoś nie zgubił**.
Archiwum SAOS jest przy tym zamrożone na 2018-09, więc przebieg po nim jest deterministyczny
i powtarzalny — bramka fazy 1 („przerwany i wznowiony bez duplikatów") dostałaby stabilne
wejście, czego żywy kanał nie daje.

**Cena.** Dwa żądania na sam pomiar, ale potem osobny ADR (ADR-0004 §4.2 zostawił wiersz `saos`
jako „nierozstrzygnięty"), adapter `source/saos.py`, własna polityka wersji i — to najważniejsze —
**warunki ponownego wykorzystywania odczytane u źródła**, których przy pomiarze 23 nikt nie
odczytał, bo host nie odpowiedział. Kanał bez licencji nie dostaje roli masowej; tak zamknęliśmy
UZP (decyzja B) i ta sama reguła obowiązuje SAOS.

### Pytanie 2: czy źródło urzędowe może weryfikować pośrednika (`uzp`: 4b, 16, 7, 19, 9)

`orzeczenia.uzp.gov.pl` to **źródło**, a Atlas — pośrednik. Decyzja B zabrania UZP roli masowej
i ma na to pomiar: pomiar 14 ustalił 2026-09-15, że warunków ponownego wykorzystywania tam **nie
ma, a informacji o ich braku też nie**. Zostają dwie role, które licencji masowej nie wymagają:
**weryfikacja** (czy to, co mamy z pośrednika, zgadza się ze źródłem) i **dopływ** (pojedyncze
dokumenty, których pośrednik nie ma).

- **4b i 16** — własny `POST /Home/GetResults` oraz liczniki `#resultCounts` przy pustej frazie.
  Razem odpowiadają, ile wpisów urząd w ogóle publikuje, czyli dają **mianownik**, którego dziś
  nie mamy. Bez niego zdanie „korpus jest kompletny" jest niesprawdzalne w obie strony: nie da
  się go ani potwierdzić, ani obalić.
- **7** — czy sprostowanie orzeczenia jest nowym rekordem, czy nadpisaniem. To nie ciekawostka:
  od tego zależy polityka wersji kanału (ADR-0005 Z-4), a więc to, czy `przelicz --wszystko` ma
  prawo nadpisać wersję, którą ktoś już zacytował w piśmie.
- **19** — czy `ContentHtml` jest bitowo stabilny między pobraniami odległymi o dobę. Jeżeli nie,
  `content_sha256` przestaje znaczyć „inna treść" i zaczyna znaczyć „inne pobranie", co uderza
  w tożsamość wersji dokumentu — a na niej stoi cały złoty zbiór.
- **9** — tolerancja serwisu na tempo. Jako jedyny z dziewięciu **wymaga zgody właściciela**, bo
  polega na ostrożnym narastaniu obciążenia cudzego serwisu, i jako jedyny jest dziś zbędny:
  Atlas publikuje limity i raportuje je nagłówkami. Wraca tylko wtedy, gdyby UZP dostało rolę
  masową, czego decyzja B zabrania.

**Co by to dało projektowi.** Polecenie `porownaj` z prawdziwym drugim zdaniem i odpowiedź na
pytanie „czy ufamy pośrednikowi", dziś przyjęte na wiarę wraz z ryzykiem resztkowym (decyzja A).

### Pytanie 3: pomiary czekające na fazę 4 albo na zmianę prawa (18, 20)

- **18** — czy nowelizacja Pzp z 13.03.2026 zmieniła słownik przepisów. Dwa wywołania słownika,
  zero ryzyka, a waży dokładnie tyle, ile tabela `provisions`: w korpusie **16 834 przepisy**,
  z czego `pzp2019` 7 849, `pzp2004` 2 529, `kc` 591, a `nieustalone` **5 233, czyli 31,1 %**
  (stan 2026-09-20, wersja odczytu 6). Jeżeli nowelizacja przenumerowała artykuły, część tych
  „ustalonych" wskazuje dziś na inny przepis niż w dniu orzeczenia — a tego automat nie zapali,
  bo wartość pola pozostaje poprawna. To ta sama klasa usterki, którą znalazł przegląd O-4.
- **20** — co zwracają `/AiSearch/*` w wyszukiwarce UZP. Pomiar czysto rozpoznawczy; po
  rezygnacji z asystenta jego jedynym możliwym skutkiem jest wiedza, **czym** urząd wyszukuje,
  a nie zapożyczenie tego do narzędzia.

### Odpowiedź krótka

Żaden z tych dziewięciu pomiarów nie jest potrzebny do tego, żeby narzędzie działało — to jest
ich wspólna cecha i dlatego wszystkie leżą w O-7, a nie w bramce. Każdy z nich odpowiada
natomiast na pytanie, którego dziś **nie umiemy zadać**: czy korpus jest kompletny (4b, 16), czy
sięga tak daleko jak orzecznictwo (2a, 2b), czy pośrednik jest wierny (`porownaj`, 19) i czy
wersja, którą ktoś zacytował, ma prawo się zmienić (7). Rozszerzenie, które z nich wynika, nie
jest „więcej funkcji", tylko **drugie zdanie o tych samych danych** — a doktryna tego projektu
mówi, że gwarancja bez obserwatora nie jest gwarancją.

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
| 3b | Opóźnienie publikacji u pośrednika | **w toku od 2026-09-19 — procedura ustalona, zero odczytów** (`## Pomiar 3b`) | faza 1 | obserwacja **jednokanałowa**, 1 żądanie dziennie; brzmienie pierwotne (ta sama sprawa z dwóch kanałów) jest niewykonalne bez kanału `uzp` — powód i nowa definicja w `## Pomiar 3b` |
| 4 | Kontrakt wyszukiwarki UZP | **wykonany strukturalnie** (`Move` → `Details` własnym odczytem; `GetResults` z dwóch cudzych kolektorów) | — | — |
| 4b | Własny `POST /Home/GetResults` i pierwsza kaseta | niewykonany | odłożony (kanał `uzp` w rolach weryfikacji i dopływu, faza 2) | `sonda.py uzp-getresults` |
| 5 | Warstwa tekstowa w próbce ~50 dokumentów | **wykonany 2026-09-19**: część lokalna na 341 dokumentach (0 żądań), część rocznikowa na 443 po Przebiegu 3 (119 żądań próbki; `## Pomiar 5, część rocznikowa`) | faza 2 (ADR-0006 Z-3, etapy I–II) | część rocznikowa: próbka stratyfikowana 2010–2026, ~119 żądań, zgoda w sesji; próbka staje się zalążkiem `tests/gold/` |
| 6 | Granice przestrzeni identyfikatorów | z drugiej ręki (~33 366 w kwietniu 2026) | faza 1 | dwa odczyty `Details` + pomiar 16 |
| 7 | Sprostowania: nowy rekord czy nadpisanie | niewykonany | polityka wersji kanału `uzp` (ADR-0005 Z-4) | `GetResults` dla sprawy ze znanym sprostowaniem |
| 8 | Dokumenty wielosygnaturowe w wyszukiwarce | potwierdzone strukturalnie | ADR-0001 | jeden odczyt `Details` sprawy z listingu FTP |
| 9 | Tolerancja serwisu na tempo | niewykonany; **wymaga zgody właściciela** | odłożony — zbędny dla Atlasu (limity publikowane i raportowane nagłówkami); tylko jeśli UZP dostanie rolę masową, czego decyzja B zabrania | ostrożne narastanie ze stopem |
| 10 | Anonimizacja na większej próbce | **wykonany 2026-09-19, 0 żądań**, 443 dokumenty — skład i protokolant nieanonimizowani (`## Pomiar 10`) | faza 2 | 30–50 dokumentów, w tym z protokołem rozprawy |
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
| 22 | Gęstość cytowań i udział nieznormalizowanych | **wykonany 2026-09-19, 0 żądań** — 1 695 cytowań, 4,6 % nierozpoznanych (`## Pomiar 22`, raport pokrycia) | faza 2 | `parser/cite.py` na próbce z pomiaru 5, zero żądań |
| 23 | Warunki ponownego wykorzystywania SAOS i Atlasu, odczytane **u źródła** | **wykonany 2026-09-18 — Atlas: CC BY 4.0 z atrybucją u źródła; SAOS: brak odpowiedzi w 45 s** (`## Pomiar 23`) | **bramka** (`atlas`) — spełnione dla Atlasu; SAOS nieodczytany | `sonda.py licencje` — 3 żądania; SHA-256 każdej strony w `## Pomiar 23` |
| 24 | Awaryjność kanału i skuteczność ponowień (ADR-0007 Z-8) | niewykonany — wymaga pierwszego przebiegu kwartalnego po wdrożeniu ponowień | korekta progów bloku `ponowienia` w `contract.yaml` | `requests_log.proba` (schemat 5): ponowienia per klasa i ile skończyło się 200, zero żądań dodatkowych |

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
