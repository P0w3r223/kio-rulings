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

**2. `normalize_signature` zostaje przy wyszukiwaniu w napisie. Do ADR-001.**
Funkcja na wejściu wielosygnaturowym zwraca pierwszą sygnaturę i nie sygnalizuje, że zgubiła
drugą sprawę — czyli popełnia błąd, przed którym ten moduł ma chronić. Wyszukiwanie w środku
napisu jest jednak niezbędne dla `parser/cite.py`, który szuka sygnatur wplecionych w zdania
uzasadnienia. Rozstrzygnięcie robocze: kompromis zostaje, jest opisany w docstringu jako
hazard, a reguła brzmi „napis poziomu dokumentu idzie wyłącznie przez
`normalize_signature_list`". Strażnik istnieje i przybija złe zachowanie jawnie. Czy funkcja
ma zamiast tego **odrzucać** wejście wielosygnaturowe, rozstrzyga ADR-001 — razem z pomiarem
7 (sprostowania), bo obie rzeczy dotyczą tego, czym jest tożsamość dokumentu.

**3. Pisownia referencji w `document_id` jest sprawą kanału. Do ADR-001.**
Dziś `document_id` sprowadza do małych liter nazwę kanału, ale nie referencję. Dla `uzp:9620`
i `saos:354301` jest to obojętne (identyfikatory liczbowe), dla sluga `atlas:kio-827-18`
realne: dwie pisownie dałyby dwa klucze główne na jeden dokument, czyli minę 1 z CEIDG.
Rekomendacja do ADR-001: **normalizacja per kanał, zadeklarowana w `contract.yaml`** (pole
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
