# Audyt przedsięwzięcia: narzędzie do orzecznictwa KIO

Data: 2026-09-14
Status: proposed — do przyjęcia albo odrzucenia przez właściciela; sekcja 13 wylicza, co czeka
Autor: P0w3r223
Dotyczy: nowe narzędzie, osobne repozytorium; wzorce przenoszone z `ceidg-tool`
Podstawa: research dwuprzebiegowy, osiem perspektyw, 2026-09-14
Weryfikacja: 24 twierdzenia nośne sprawdzone przy źródle, 4 poprawione — sekcja 14

---

## 0. Jak czytać ten dokument

Piszę to dla agenta, który zacznie w pustym katalogu i nie będzie miał dostępu do tej sesji.
Dokument nie jest planem implementacji — jest **audytem przedpola**: co wiadomo, skąd to wiadomo,
czego nie wiadomo, i które z niewiadomych trzeba zmierzyć, zanim powstanie pierwsza linia kodu.

Trzy rzeczy o jego statusie, bo od nich zależy, jak go traktować:

- **Sekcje 2–5 pochodzą z pomiaru albo z lektury źródła, z datą 2026-09-14.** Twierdzenie bez
  wskazania, skąd pochodzi, jest w tym dokumencie błędem, a nie skrótem. Jeśli czytasz to po
  2026-12 i coś się nie zgadza ze źródłem — wierz źródłu i popraw ten plik w tym samym commicie,
  w którym opierasz się na nowej wersji.
- **Sekcja 10 to lista pomiarów, nie założeń.** Rzeczy, których nie da się ustalić bez wykonania
  własnych żądań, są tam wypisane osobno właśnie po to, żeby nie przeciekły do kodu jako
  „wiadomo, że". Zacznij od niej, a nie od kodu.
- **Sekcje 6, 7, 11 i 12 są przeniesione z projektu, który już przez to przeszedł.** Nie są
  filozofią. Każda z wypisanych tam reguł ma za sobą konkretną awarię z datą, i tam gdzie ta
  awaria jest pouczająca, jest opisana.

Kolejność czytania, jeśli masz przeczytać tylko część: **14 → 13 → 2 → 10**. Sekcja 14 to status
dowodowy — mówi, na których zdaniach tego dokumentu wolno budować, a które trzeba najpierw
zmierzyć; cztery twierdzenia były w pierwszej wersji błędne i tam widać które. Potem 13 daje
decyzję, 2 stan źródła, 10 plan pierwszego dnia. Reszta jest uzasadnieniem tych czterech.

Trzy ustalenia, które przewróciły założenia w trakcie pisania tego dokumentu, warto znać od razu,
bo każde z nich brzmiało wcześniej odwrotnie: **serwer FTP z orzecznictwem został wyłączony
z końcem września 2025**; **SAOS ma KIO tylko do września 2018**, mimo że opis mówi po prostu
„obejmuje KIO"; i **Izba jednak anonimizuje** dane osób fizycznych, wbrew rozumowaniu z art. 43⁴
k.c., które wydawało się przesądzać, że nie może.

---

## 1. Czym jest to przedsięwzięcie i czym różni się od CEIDG

Decyzje właściciela z 2026-09-14, które wyznaczają zakres:

| Pytanie | Rozstrzygnięcie |
|---|---|
| Produkt | **Fazowo**: faza 1 kończy się lokalnym korpusem z pełnym tekstem i eksportem; faza 2 dokłada pytania w języku naturalnym |
| Repozytorium | **Nowe, osobne**; wzorce z `ceidg-tool` kopiowane, bez wspólnej biblioteki |
| Odbiorca | **Ten sam operator co w CEIDG** — bez wiedzy o interfejsach, wynik do arkusza, kreator prowadzi przez decyzje |
| Rachunek build-vs-buy | **Rozstrzygany uczciwie**, sekcja 4 |

Trzy różnice wobec CEIDG, z których każda przestawia kolejność prac:

**Różnica 1: nie ma interfejsu, jest formularz.** CEIDG zaczynał od udokumentowanego API v3
z tokenem i parametrami — pierwszą fazą było napisanie klienta. Tutaj pierwszą fazą jest
**zmierzenie, czym jest to źródło**, bo nie wiadomo tego z dokumentacji: żadnej nie ma. Każda
decyzja architektoniczna podjęta przed tym pomiarem byłaby zgadywaniem kształtu.

**Różnica 2: jednostką nie jest rekord, tylko dokument.** W CEIDG wpis miał kilkadziesiąt pól
i mieścił się w wierszu arkusza. Tutaj jednostką jest kilkanaście stron polszczyzny prawniczej,
która ma strukturę wewnętrzną (sentencja, uzasadnienie, rozstrzygnięcie o kosztach) i której nie da
się sensownie zmieścić w komórce. To zmienia wszystko po stronie przechowywania, eksportu
i wyszukiwania — i jest powodem, dla którego faza 1 kończy się korpusem, a nie samym arkuszem.

**Różnica 3: ryzyko przesuwa się z danych na dostęp.** W CEIDG groźne były dane wyjściowe (rejestr
realnych osób, token z PESEL-em w ładunku) przy bezspornym prawie do zapytania. Tutaj dane są
publiczne z założenia, a sporna jest **droga dostępu** — patrz sekcja 3. Reguła zgody właściciela
przenosi się więc bez zmian, ale z innego powodu.

---

## 2. Stan źródła — co zmierzono 2026-09-14, a czego nadal nie wiadomo

### 2.1 Zdarzenie, które przewraca najprostszy plan

**Z dniem 30 września 2025 r. UZP zaprzestał publikacji orzecznictwa KIO na serwerze FTP.**
Komunikat wskazuje wyszukiwarkę `orzeczenia.uzp.gov.pl` jako źródło dostępu do aktualnych wyroków.
Zamyka to drogę „pobierz archiwum raz, przetwarzaj offline": każdy przyrostowy dopływ idzie tą samą
stroną WWW co pierwsze pobranie, więc grzeczne tempo i tożsamość dokumentu trzeba projektować od
początku pod pobieranie po jednym, a nie pod plik zbiorczy.

**Sprzeczność, której audyt nie wygładza — i która została zweryfikowana wprost.** W tym samym
serwisie gov.pl nadal serwuje się instrukcja „Instrukcja korzystania z orzecznictwa Krajowej Izby
Odwoławczej zgromadzonego na serwerze FTP" (PDF, 957 KB, pobrany 2026-09-14). Podaje adres
`ftp://ftp.uzp.gov.pl/KIO/Wyroki/`, zaznaczenie opcji „Zaloguj anonimowo", i **nie zawiera żadnej
adnotacji, noty ani znaku wodnego o wycofaniu usługi** — przeczytano wszystkie pięć stron.

Sam komunikat mówi zaś dokładnie tyle, że Urząd „zaprzestał publikacji orzecznictwa Krajowej Izby
Odwoławczej na serwerze FTP" z dniem 30 września 2025 r. **Nie mówi, że serwer wyłączono, ani co
stało się z istniejącymi plikami.** To nie jest interpretacja — to jest zakres tego zdania. Czy
serwer odpowiada, jest pozycją nr 1 na liście pomiarów i może okazać się najtańszą drogą do
osiemnastu lat materiału.

### 2.2 Kształt wyszukiwarki — zmierzone bezpośrednio

Adresowanie jest **liczbowe i wewnętrzne**, nie po sygnaturze:

| Punkt końcowy | Co zwraca |
|---|---|
| `/Home/Details/{id}` | strona szczegółów sprawy |
| `/Home/PdfContent/{id}?Kind=KIO` | pełna treść jako PDF |
| `/Home/ContentHtml/{id}?Kind=KIO` | ta sama treść jako HTML |
| `/Home/PdfMetrics/{id}?Kind=KIO` | metryka dokumentu |
| `/Home/Move?Phrase=…&Pg=…&total=…&ind=…` | wyniki wyszukiwania renderowane po stronie serwera |

`Kind` przyjmuje co najmniej `KIO` i `SO` (sądy okręgowe, dawne odwołania od orzeczeń Izby).
Wyszukiwarka TSUE jest osobnym modułem, więc prawdopodobnie **nie** kryje się pod tym parametrem —
niezweryfikowane.

Cztery pomiary, które zmieniają projekt:

- **PDF jest generowany na żądanie, nie leży gotowy.** Pobrany dokument miał w metadanych datę
  utworzenia z dnia pobrania i generator `wkhtmltopdf`. Masowe pobieranie oznacza więc **masowe
  renderowanie po stronie cudzego serwera**, a nie odczyt statycznych plików. To inny profil
  obciążenia i prawdopodobnie inny próg tolerancji — próg nieznany. Jeśli istnieje ścieżka
  `ContentHtml`, jest ona niemal na pewno tańsza dla serwisu i to ona powinna być domyślna.
- **Identyfikator nie jest chronologiczny.** Zmierzone: `id=1` → KIO 2650/15 (rok 2015),
  `id=6906` → KIO/UZP 1482/08 (9 stycznia 2009), `id=30442` → KIO 3019/25 (9 września 2025).
  `id=999999` zwraca 404, więc przestrzeń jest ograniczona z góry. **Enumerowanie identyfikatorów
  w górę nie odtwarza porządku dat** — a to jest dokładnie założenie, które przy wykrywaniu nowości
  narzuca się samo i byłoby fałszywe.
- **Wyszukiwanie idzie przez JS/AJAX.** Zwykłe żądanie GET na `/Home/Search` zwraca sam szkielet
  strony z komunikatem „Wyszukiwanie dokumentów. Proszę czekać…". Punktem, który odpowiada od razu,
  jest `/Home/Move` z pełnym zestawem parametrów. **Kontrakt tego wywołania nie został odtworzony** —
  nie wiadomo, skąd bierze się `total` przy pierwszym zapytaniu. To trzeba podejrzeć w narzędziach
  deweloperskich przeglądarki, nie zgadnąć.
- **Brak `robots.txt` (404) i brak `sitemap.xml` (404).** Czyli brak deklaracji w obie strony: ani
  zakazu, ani zgody.

**Nie znaleziono** API, eksportu masowego, kanału RSS ani webhooka. Nie znaleziono też zbioru
orzeczeń KIO w `dane.gov.pl` — wynik negatywny z wyszukiwarki portalu, wart potwierdzenia.

**Nie zmierzono żadnego throttlingu, limitu ani CAPTCHA** — ale też nie wykonano żadnego testu
obciążeniowego. To jest brak pomiaru, nie stwierdzenie, że limitów nie ma, i tak ma być czytane.

### 2.3 Wykrywanie nowości jest problemem otwartym

Nie ma RSS ani webhooka, identyfikator nie jest chronologiczny, a podmiot zewnętrzny obserwuje, że
UZP publikuje treści z opóźnieniem. Zostaje odpytywanie — ale **po czym?** Po dacie wydania, po
identyfikatorze, po dacie publikacji, jeśli w ogóle istnieje osobno od daty wydania? Żadna z tych
odpowiedzi nie jest oczywista i **ta jedna wymaga własnego eksperymentu**, bo od niej zależy, czy
`aktualizuj` w ogóle jest wykonalne. W CEIDG odpowiednikiem był punkt `/zmiana` — rejestr sam mówił,
co się zmieniło. Tutaj takiego punktu nie ma.

**I jest gorzej, niż wyglądało — zmierzone przy weryfikacji tego dokumentu (2026-09-14).**
Dokument `Details/1` ma sygnaturę `KIO 2650/15` i **puste pole „Data wydania rozstrzygnięcia"**:
pole jest w metryce, wartości nie ma. Skoro data bywa pusta, a identyfikator nie jest
chronologiczny, to **obie oczywiste osie porządkowania zawodzą jednocześnie** — jedna punktowo,
druga systematycznie. Strategia „co nowego od ostatniego przebiegu" nie ma więc w tym źródle
oczywistego oparcia i trzeba ją wymyślić, a nie wybrać. To zarazem ostrzeżenie dla filtrów po
dacie: rekord z pustą datą wypada z każdego zakresu, cicho.

### 2.4 Zasięg archiwum — sięga początku Izby, i to jest dobra wiadomość

Doprecyzowane w przebiegu 2 (2026-09-14). Izba przejęła kompetencje od Zespołów Arbitrów
**5 grudnia 2007 r.**, a najstarsze odnalezione w bazie orzeczenia noszą sygnatury `KIO/UZP 5/07`,
`7/07` (13.12.2007), `1423/07` (18.12.2007), `1435/07` (20.12.2007) oraz `1442/07` i `1443/07`
(27.12.2007). **Archiwum zaczyna się praktycznie w dniu, w którym Izba zaczęła orzekać**, bez
widocznego przesunięcia na starcie.

Liczniki widziane w adresach wyników wyszukiwania miały wartości rzędu `total=20386` i `total=19582`
— ale **to są liczniki konkretnych zapytań, nie rozmiar bazy**, i tak mają być czytane. Rozmiar
całości pozostaje nieustalony ze źródła; liczba 29 482 pochodzi od pośrednika i obejmuje
prawdopodobnie także inne organy.

**Materiał wygląda na tekstowy, nie skanowany — ale dowód jest pośredni.** Dokument z 2013 r.
zachował w treści ślad „Microsoft Word - 2791_12.doc", a orzeczenia z 2008 r. występują
w niezależnym systemie jako tekst przeszukiwalny. **Nie znaleziono dowodu, że którykolwiek rocznik
KIO jest skanem** — w odróżnieniu od kategorii `SO`, gdzie skany (`.tif`) potwierdzono. To jest
jednak brak dowodu przeciwnego, a nie pomiar na próbce, i pozostaje pozycją listy z sekcji 10.

**Nazewnictwo plików w archiwum FTP — zweryfikowane wprost z listingu** (odczyt instrukcji UZP,
2026-09-14). Konwencja jest **spójna**, wbrew wcześniejszemu podejrzeniu: `RRRR_NNNN` z numerem
dopełnionym zerami do czterech cyfr, plus wariant wielosygnaturowy.

- `2016_0095.doc` (159 KB), `2016_2155.doc` (213 KB), `2017_2037.docx` (21 KB) — starsze roczniki
  w formatach Worda; `2016_0095` przesądza o **zerach wiodących**;
- `2021_2281.pdf`, `2021_2070.pdf`, `2021_1875.pdf` — pojedyncze sprawy;
- `2021_1820_1821_1834.pdf` (818 KB), `2021_1755_1758.pdf` (1 322 KB), `2021_1586_1587.pdf`,
  `2021_1381_1388.pdf`, `2021_1295_1296.pdf` — **pliki łączące kilka sygnatur w jednym dokumencie**,
  bezpośrednie potwierdzenie miny 1 z sekcji 11: **jeden dokument bywa nośnikiem kilku spraw.**

**Pasek stanu tego samego okna pokazuje „Elementy: 30 660".** To jedyna zmierzona liczba wielkości
zasobu, jaką ten audyt ma — większa od 29 482 deklarowanych przez pośrednika, przy czym liczy pliki,
a nie sprawy, więc pliki wielosygnaturowe zaniżają ją względem liczby orzeczeń, a inne kategorie
mogą ją zawyżać. Traktować jako rząd wielkości, nie jako licznik.

**Jedno zastrzeżenie, które wcześniejsza wersja tego dokumentu myliła.** Krążący przykład
`2791_12.doc` (sprawa KIO 2791/12) nie pochodzi z listingu FTP — to **wewnętrzna nazwa pliku Worda**
zachowana w treści dokumentu serwowanego przez wyszukiwarkę, czyli robocza nazwa po stronie Izby,
w schemacie „numer podkreślnik rok". To dwa różne schematy w dwóch różnych miejscach, a nie jeden
niekonsekwentny. Parser nazw plików i parser treści patrzą więc na co innego.

---

## 3. Dopuszczalność — sześć reżimów, z których wiąże jeden, a dwa wymagają prawnika

Ustalenia z przebiegu 1, perspektywa prawna, 2026-09-14. **To nie jest opinia prawna** i cztery
punkty poniżej są wprost oznaczone jako wymagające konsultacji przed decyzją architektoniczną.

Najważniejsze zdanie tej sekcji, zanim padnie reszta: **nie znaleziono podstawy do twierdzenia, że
pobieranie jest zakazane** — ale nie znaleziono też podstawy do twierdzenia, że jest obojętne.
Reżimy się nakładają, a odpowiedzialność za dalsze przetwarzania przechodzi na operatora narzędzia.

### 3.1 Prawo autorskie — prawdopodobnie neutralne, z jednym zastrzeżeniem

Orzeczenia KIO jako dokumenty urzędowe mieszczą się w wyłączeniu z **art. 4 pkt 2 ustawy o prawie
autorskim** — nie stanowią przedmiotu prawa autorskiego. To jest brzmienie przepisu, nie
interpretacja. Doktryna, powołując wyrok SN z 26.09.2001 (IV CKN 458/00), zastrzega jednak, że
wyłączenia tego „nie należy utożsamiać z pozostawieniem pełnej swobody powielania
i rozpowszechniania".

Zastrzeżenie praktyczne: wyłączenie dotyczy **samego orzeczenia**, a niekoniecznie pism procesowych
stron i pełnomocników cytowanych w uzasadnieniu. Jeśli korpus miałby kiedyś wyjść poza tekst
orzeczenia, to jest granica do ponownego przemyślenia.

### 3.2 Ustawa o otwartych danych (11.08.2021) — reżim główny i realnie wiążący

To jest przepis wprost dedykowany masowemu pozyskiwaniu treści od podmiotu publicznego,
implementujący dyrektywę (UE) 2019/1024. Trzy rzeczy z niego wynikające:

- **art. 6 ust. 2** ogranicza prawo do ponownego wykorzystania ze względu na prywatność osób
  fizycznych, z wyjątkiem osób pełniących funkcje publiczne w związku z ich pełnieniem;
- **art. 7 ust. 2** — ustawa nie narusza przepisów o ochronie danych osobowych, więc RODO stosuje
  się w pełni i niezależnie;
- **art. 15 ust. 1 pkt 4** pozwala UZP określić warunki ponownego wykorzystania; przy ich braku
  obowiązuje warunek domyślny: **podanie źródła, czasu wytworzenia i pozyskania informacji, a dla
  orzeczeń — daty wydania, oznaczenia organu i sygnatury akt.**

Odpowiedź na pytanie o obowiązki wobec urzędu jest zatem twierdząca, ale węższa, niż można się
obawiać: **jest obowiązek atrybucji przy dalszym udostępnianiu, nie ma obowiązku zgłoszenia zamiaru
pobierania ani uzyskania zgody UZP na sam scraping** — pod warunkiem, że nie łamie się zabezpieczeń
technicznych. Konsekwencja dla kodu: eksport i każdy widok cytujący orzeczenie **musi** nieść
sygnaturę, datę wydania i oznaczenie organu. To nie jest ozdoba — to jest warunek ustawowy i ma
zostać zapisane jako niezmiennik pilnowany testem, nie jako dobra praktyka.

Uwaga: UZP zastrzega się od odpowiedzialności za dalsze rozpowszechnianie przez reużytkownika
z naruszeniem ochrony danych osobowych. **Odpowiedzialność jest po stronie operatora narzędzia.**

### 3.3 RODO — reżim najbardziej pracochłonny, i tu jest realna praca do wykonania

Nowa ustawa o otwartych danych, w odróżnieniu od poprzedniej z 2016 r., **zniosła zwolnienie
reużytkowników z obowiązków informacyjnych z art. 13–14 RODO**. Operator narzędzia staje się
administratorem danych dla własnego celu i musi mieć własną podstawę z art. 6 ust. 1 (realnie
lit. f — prawnie uzasadniony interes, z testem ważenia), rozważyć zgodność nowego celu
z pierwotnym (art. 6 ust. 4), i co do zasady zrealizować obowiązek z **art. 14** wobec osób,
których danych nie pozyskał od nich samych. Wyłączenie „niewspółmiernie dużego wysiłku"
(art. 14 ust. 5 lit. b) jest interpretowane **wąsko** — w sprawie Bisnode odrzucono argument
kosztów, a sama liczba osób nie wystarcza.

**Tu przebieg 2 obalił twierdzenie, które przebieg 1 uznał za najgroźniejsze — i jest to
najkorzystniejsze ustalenie całego researchu.** Rozumowanie przebiegu 1 brzmiało: jednoosobowa
działalność musi z ustawy (art. 43⁴ k.c.) zawierać w firmie imię i nazwisko przedsiębiorcy, więc
nazwa strony *jest* danymi osobowymi, których nie da się usunąć bez utraty sensu dokumentu.
Rozumowanie było poprawne i **nie zgadza się z praktyką Izby**.

Odczytano bezpośrednio sześć orzeczeń z lat 2015, 2020, 2022, 2024 i 2025 (obrazem strony PDF, nie
streszczeniem — bo narzędzie streszczające samo maskowało nazwiska, co mogło zostać wzięte za cechę
dokumentu). Obraz jest spójny przez dekadę:

| Kategoria | Postać w publikowanym orzeczeniu |
|---|---|
| Skład orzekający, protokolant | **pełne imię i nazwisko, zawsze, bez maskowania** |
| Strony będące osobami prawnymi | pełna nazwa, bez maskowania |
| Osoba fizyczna prowadząca działalność | **inicjały, wplecione w nazwę firmy** |
| Podmiot trzeci wzmiankowany w uzasadnieniu | **też inicjały**, mimo że nie jest stroną |
| Pełnomocnicy | w tej próbce nie występują z nazwiska (ustalenie słabsze) |
| Świadkowie, biegli | brak przykładu w próbce (nieprzebadane) |

Izba redukuje więc imię i nazwisko do inicjałów **nawet tam, gdzie ta nazwa jest prawnie częścią
firmy**. Sens dokumentu zostaje, tożsamość osoby fizycznej nie. Maskowanie jest redakcyjne, a nie
techniczne — inicjały są wplecione gramatycznie w zdania, nie zamalowane — czyli powstaje przy
redagowaniu treści, nie przez filtr nałożony na gotowy plik.

**Co z tego wynika dla ciężaru z art. 14 RODO:** kategoria osób, która budziła obawę, jest
w publikowanej wersji zanonimizowana u źródła. Zostają osoby wymienione pełnym imieniem
i nazwiskiem — członkowie składu orzekającego i protokolanci — czyli dokładnie **osoby pełniące
funkcje publiczne w związku z ich pełnieniem**, a te art. 6 ust. 2 ustawy o otwartych danych
wprost wyjmuje spod ograniczenia. To nie znosi obowiązków administratora, ale przesuwa je z „setki
tysięcy przedsiębiorców" na „orzecznicy wykonujący funkcję publiczną", co jest zupełnie innym
rozmiarem problemu.

**Trzy zastrzeżenia, których nie wolno zgubić:**

1. Próbka to **sześć dokumentów dobranych celowo**, nie badanie ilościowe. Nie wiadomo, czy
   inicjalizacja jest stosowana w 100 % przypadków, ani jak wygląda w rocznikach sprzed 2015.
   Anonimizacja **ręczna zawodzi punktowo** — i to jest realne ryzyko operacyjne: pojedynczy
   przeoczony fragment trafi do korpusu.
2. **UZP nie publikuje żadnych zasad anonimizacji.** Nie znaleziono metodologii, zakresu, ani
   informacji, kto ją wykonuje. Sądy powszechne mają w tej sprawie jawne zarządzenia; Izba nie ma
   nic analogicznego. Konsekwencja: **praktyka może się zmienić bez ostrzeżenia**, w obie strony.
3. Klauzula informacyjna skierowana do stron postępowania odwoławczego, opisująca podstawę
   i zakres publikacji ich danych, **nie została odnaleziona**. Strona „KIO — RODO" przekierowuje
   dziś na stronę ogólną, a klauzula „Dane osobowe" na gov.pl dotyczy wyłącznie naboru pracowników.

Kategorie „pełnomocnicy" i „świadkowie" pozostają **niedomknięte** i trafiają na listę z sekcji 10
— w części orzeczeń protokół rozprawy wymienia obecnych, a takiego fragmentu w próbce nie było.

Co do **art. 10 RODO** (wyroki skazujące i naruszenia prawa): z doktryny wynika, że rozstrzygnięcia
cywilne i administracyjne nie są nim objęte, więc orzeczenia KIO prawdopodobnie **nie** kwalifikują
zawartych w nich danych do tego szczególnego reżimu. To wniosek przez analogię, nie z orzecznictwa
dotyczącego wprost KIO — i słabnie tam, gdzie orzeczenie stwierdza np. wprowadzenie zamawiającego
w błąd.

### 3.4 Ochrona baz danych *sui generis* — nierozstrzygnięte, wymaga prawnika

Ustawa z 27.07.2001 chroni **inwestycję producenta bazy** niezależnie od praw autorskich do
poszczególnych elementów. Systematyczne pobranie „istotnej części" bazy mogłoby teoretycznie
naruszać ten monopol nawet wtedy, gdy pojedyncze orzeczenie nie jest chronione prawem autorskim.
Relacja między tym prawem a ustawowym obowiązkiem reużycia ISP **nie jest jednoznacznie
rozstrzygnięta** w dostępnych źródłach. To jest pierwsze z dwóch miejsc, w których audyt mówi:
zapytać prawnika, zwłaszcza przy planie pobrania całego zasobu.

### 3.5 Warunki serwisu — i granica między sprawą cywilną a karną

- Stopka `gov.pl/web/uzp` deklaruje treści tekstowe na licencji **CC BY-SA 4.0**. **Nie
  potwierdzono, czy obejmuje ona technicznie odrębną domenę `orzeczenia.uzp.gov.pl`**, gdzie nie
  znaleziono noty licencyjnej ani regulaminu ponownego wykorzystania. Różnica jest realna: CC BY-SA
  niesie *share-alike*, czyli obowiązek udostępnienia korpusów pochodnych na tej samej licencji,
  którego reżim ustawowy nie nakłada.
- **`robots.txt` pod `orzeczenia.uzp.gov.pl` zwraca 404** (sprawdzone 2026-09-14) — brak pliku,
  więc brak formalnego zakazu crawlowania. Nie wyklucza to innych zabezpieczeń.
- I najważniejsze rozróżnienie tej sekcji: naruszenie warunków korzystania z portalu ma charakter
  cywilny, **chyba że pozyskanie wymaga obejścia zabezpieczenia technicznego** — wtedy w grę wchodzi
  **art. 267 § 1 k.k.** Konsekwencja dla kodu jest twarda i bezwarunkowa: **narzędzie nigdy nie
  omija CAPTCHA, nie podszywa się pod przeglądarkę w celu ominięcia blokady i nie obchodzi
  ograniczeń tempa.** Jeśli serwis odmawia, narzędzie ma się zatrzymać i powiedzieć to operatorowi,
  a nie znaleźć drogę naokoło. Ta reguła należy do sekcji 12 i jest tam powtórzona.

### 3.6 Faza 2 i AI Act — drugie miejsce, w którym trzeba prawnika

Załącznik III pkt 8(a) AI Act klasyfikuje jako **wysokiego ryzyka** systemy przeznaczone do użytku
przez organ sądowy lub w jego imieniu do wspomagania badania i interpretacji faktów i prawa — oraz
używane podobnie w **alternatywnym rozwiązywaniu sporów**. To ostatnie jest istotne, bo postępowanie
przed KIO leży blisko tej kategorii.

Rozróżnienie, od którego wszystko zależy: narzędzie służące **podmiotowi prywatnemu do budowania
wiedzy o orzecznictwie** ma mocniejszy argument za wyłączeniem niż narzędzie wspierające stronę
w toczącym się sporze. Granica nie jest jednoznacznie rozstrzygnięta i **zależy od opisu
przeznaczenia**, którego jeszcze nie ma. Wniosek praktyczny dla fazy 2: opis przeznaczenia trzeba
napisać **zanim** powstanie warstwa modelu, a nie po niej.

### 3.7 Precedens rynkowy

Atlas Przetargów już dziś masowo reużywa treść orzeczeń KIO z tego źródła, wprost powołując się na
status reużytkownika informacji sektora publicznego i zastrzegając, że nie jest źródłem urzędowym.
To dowód praktyki, nie rozstrzygnięcie prawne — ale pokazuje, że reżim z 3.2 jest na tym rynku
stosowany jawnie.

---

## 4. Czy w ogóle budować — rachunek wobec tego, co już istnieje

Właściciel dał temu pytaniu mandat (2026-09-14), więc odpowiedź nie jest kurtuazyjna. Ustalenia
z przebiegu 1, perspektywa „jak rozwiązano to do tej pory".

**Odpowiedź zależy od tego, która z trzech potrzeb jest prawdziwa, i dla dwóch z nich brzmi „nie".**

### 4.1 Jeśli potrzebą jest wyszukać i przeczytać — to jest już rozwiązane, za darmo

**Atlas Przetargów** prowadzi darmową bazę **29 482 orzeczeń KIO** (deklaracja dostawcy, stan na
2026-09-14) z filtrami po przepisie Pzp, rodzaju rozstrzygnięcia, stronie, kodzie CPV i okresie,
z powiązaniem około 10 000 orzeczeń z konkretnymi ogłoszeniami w BZP oraz z kanałem RSS. To jest
dokładnie produkt odpowiadający na najprostszą wersję potrzeby.

**SzuKIO** — płatna alternatywa specjalizowana, ok. **53,57 zł netto miesięcznie (2 530 zł netto
rocznie)** za stanowisko, obejmująca KIO, sądy okręgowe, SN, TSUE i GKO. LEX (od ok. 119 zł/mies.,
„Kompas Orzeczniczy 2.0" ok. 2 214 zł/rok) i Legalis (od ok. 185 zł/mies.) włączają KIO do znacznie
szerszych baz z komentarzem — rozwiązują potrzebę prawnika-praktyka, ale jako produkty zamknięte,
bez dostępu programowego do własnego potoku przetwarzania.

Budowa własnego narzędzia **na tym poziomie nie ma uzasadnienia kosztowego** i audyt to stwierdza
wprost.

### 4.2 Jeśli potrzebą jest programowy dostęp do korpusu — tu budowa ma sens, ale jako warstwa akwizycji

Żaden podmiot **urzędowy** nie oferuje udokumentowanego API do orzecznictwa KIO. Oferuje je jednak
pośrednik prywatny i to jest najważniejsze ustalenie całego researchu.

**Atlas Przetargów ma dwa różne interfejsy programistyczne o różnym zakresie** — i na tym polegała
sprzeczność między dwiema perspektywami przebiegu 1, rozstrzygnięta w przebiegu 2 (2026-09-14).
Warto ją znać, bo agent budujący narzędzie trafi na ten sam rozjazd:

- **serwer MCP** (`github.com/atlasprzetargow/mcp-server`, MIT) — siedem narzędzi, wyłącznie
  przetargi BZP/TED, **o KIO nie wspomina ani słowem**;
- **pełne REST API** (`atlasprzetargow.pl/dokumentacja-api`) — cztery dedykowane punkty do
  orzeczeń plus dwa krzyżowe.

Kto zajrzy tylko do repozytorium, wyciągnie wniosek, że orzeczeń tam nie ma. Obie obserwacje były
prawdziwe wobec swojego przedmiotu; różniły się przedmiotem.

| Punkt końcowy | Co daje |
|---|---|
| `GET /api/kio` | lista z filtrami: fraza, wynik, rodzaj orzeczenia, daty, przepis, koszty |
| `GET /api/kio/{slug}` | **pełny tekst orzeczenia** z metadanymi i powiązanym przetargiem |
| `GET /api/kio/stats` | statystyki wg wyniku i roku |
| `GET /api/entities/{nip}/rulings` | orzeczenia, w których dany podmiot był stroną |
| `GET /api/tenders/{id}/rulings` | orzeczenia dotyczące konkretnego postępowania |

Warunki, odczytane wprost ze strony dostawcy: klucz API opcjonalny (`X-Api-Key`), **1500 zapytań
na dobę i na adres IP bez klucza, 5000 na konto z darmowym**, oraz limit chwilowy **500 wywołań na
minutę** niezależnie od klucza (odczytane wprost ze strony dokumentacji 2026-09-14; krążąca wartość
30/min dla puli `/api/llm/*` **nie znalazła potwierdzenia** przy weryfikacji). Licencja
**CC BY 4.0** z wymaganą atrybucją. Regulamin powołuje wprost **ustawę z 11 sierpnia 2021 r.
o otwartych danych** i wymienia bazę orzeczeń KIO wśród źródeł — czyli podstawa prawna jest
nazwana, w odróżnieniu od przypadkowego scrapingu.

Trzy rzeczy, które równoważą ten obraz i muszą trafić do decyzji, a nie zginąć w entuzjazmie:

1. **Dane są „sparsowane z PDF"** — to własne słowa dostawcy. Czyli jest to cudzy potok ekstrakcji
   tekstu, z jego błędami, a nie ustrukturyzowany kanał od urzędu. Ryzyko literówek, urwanych
   fragmentów i źle rozpoznanych sygnatur jest realne i nieocenione.
2. **Brak SLA i brak gwarancji kompletności** — regulamin mówi to wprost, łącznie ze zdaniem, że
   przy decyzjach formalnych należy sprawdzić publikację źródłową. Klauzula wypowiedzenia dotyczy
   relacji z użytkownikiem, nie trwałości samych punktów końcowych.
3. **Opóźnienie publikacji istnieje, ale nie jest podane liczbowo.** Dostawca stwierdza tylko, że
   UZP publikuje z opóźnieniem. Bez tej liczby nie da się ocenić, czy kanał wystarcza tam, gdzie
   liczy się świeżość.

Bilans: kanał **realny i tańszy w budowie**, ale przenoszący produkt na cudzą infrastrukturę bez
zobowiązań. To jest rozstrzygnięcie architektoniczne, nie techniczne, i sekcja 13 zostawia je
właścicielowi.

Dla drogi bezpośredniej istnieje z kolei cudzy dowód wykonalności:
**`matematicsolutions/kio-orzeczenia-mcp`** — serwer MCP
scrapujący wyszukiwarkę UZP, wyszukiwanie plus pełny tekst plus filtr po artykule Pzp. Status:
**POC v0.1.0, Apache-2.0, dwie gwiazdki**, z jawnie przyznanymi ograniczeniami — płytki parser
(zwykły tekst, bez sekcji), narzucony przez UZP limit 10 wyników na stronę, tempo 1 żądanie na
sekundę. Jedna rzecz z tego repozytorium jest ważniejsza niż cały jego kod: **autor sam zapowiada,
że przed wdrożeniem produkcyjnym zamierza powiadomić UZP.** Czyli twórca najdalej posuniętej
publicznie znanej próby nie uznał kwestii dopuszczalności za rozstrzygniętą — patrz sekcja 3.

### 4.3 Jeśli potrzebą jest pytanie w języku naturalnym — to nisza realnie pusta, z twardym ograniczeniem

**JuDDGES**, najpoważniejszy otwarty polski projekt RAG nad orzecznictwem (aktywny, 1062 commity,
zbiory na HuggingFace, wyszukiwanie hybrydowe), obejmuje sądy apelacyjne karne i sprawy frankowe,
ale **w żadnym znalezionym materiale nie wspomina KIO**. Ogólne polskie asystenty prawne również
nie wykazują pokrycia KIO. Jest to spójne z przyczyną strukturalną: KIO jest organem quasi-sądowym
przy UZP, nie sądem, więc regularnie wypada poza zakres korpusów orzeczniczych — przeglądowy
artykuł z 2026 r. porównujący polskie bazy orzeczeń w ogóle jej nie wymienia.

I tu jest ustalenie, które powinno wyznaczyć zakres fazy 2. Praca **arXiv:2511.04205** (listopad
2025, „LLM-as-a-Judge is Bad, Based on AI Attempting the Exam Qualifying for the Member of the
Polish National Board of Appeal", zgłoszona 6 listopada 2025) przepuściła trzy modele przez
oficjalny **egzamin kwalifikacyjny na członka KIO**. Radziły sobie zadowalająco w części testowej
(znajomość przepisów), ale **żaden nie przeszedł progu zdawalności w części praktycznej**, czyli
w pisaniu orzeczenia — a przy okazji ocena metodą „model jako sędzia" systematycznie rozjeżdżała
się z ocenami prawdziwej komisji.

**Zastrzeżenie do składu badanych modeli, istotne dla wagi wniosku.** Testowano GPT-4.1
i Bielika-11B-v2.6; co do trzeciego źródła się różnią — jedno podaje Claude Sonnet 4, drugie
Claude 3 Sonnet, a to modele o różnym pokoleniu. Jeśli badano starszy, wniosek „nawet czołowe
modele nie dają rady" jest **słabszy, niż wygląda**, i przed powołaniem się na tę pracę w decyzji
o zakresie fazy 2 trzeba sprawdzić skład w samym artykule. Co jest pewne niezależnie od tego:
w części praktycznej próg padł dla wszystkich badanych.

Wniosek dla zakresu: budować warto **wspomaganie wyszukiwania i cytowania**, nie generowanie oceny
prawnej. To nie jest ostrożnościowa formuła, tylko zapisanie zmierzonej granicy.

### 4.4 SAOS — archiwum zamrożone w 2018 roku, i właśnie dlatego użyteczne

Przebieg 2 rozstrzygnął to pomiarem na żywym API (2026-09-14) i wynik jest jednoznaczny.

**Pokrycie KIO w SAOS urwało się osiem lat temu.** Zapytanie `courtType=NATIONAL_APPEAL_CHAMBER`
z sortowaniem rosnącym daje najstarszy rekord `KIO/UZP 2/07` z **2007-12-10**; z malejącym —
najnowszy `KIO 1711/18` z **2018-09-06**. Zapytanie z `judgmentDateFrom=2019-01-01` zwraca
`totalResults: 0`. Łącznie **22 168 rekordów KIO**.

Ogólny opis SAOS („obejmuje KIO") mówi prawdę o tym, co system zawiera, i **nic** o tym, że ten
strumień wysechł. To jest dokładnie kształt pułapki opisanej w zasadzie 7.1: zdanie prawdziwe,
które czytelnik rozumie jako odpowiedź na pytanie, na które nie odpowiada.

Trzy ustalenia towarzyszące, wszystkie zmierzone:

- **Właściwa nazwa wartości to `NATIONAL_APPEAL_CHAMBER`** — druga wersja krążąca w źródłach
  wtórnych jest błędna. Uwaga na pułapkę: ten sam parametr podany na stronie HTML `/search`, a nie
  na `/api/search/judgments`, jest **po cichu ignorowany** i zwraca niefiltrowaną listę wszystkich
  sądów. Kto testuje od strony wyszukiwarki, wyciągnie wniosek, że filtr nie działa.
- **API zwraca pełny tekst, nie metrykę.** Sprawdzony rekord miał `textContent` na około 2 800 słów
  — kompletne postanowienie z uzasadnieniem. Pola wzbogacające (`keywords`, `legalBases`,
  `referencedRegulations`, `decision`, `summary`) były puste, więc warstwy semantycznej dla KIO tam
  nie ma.
- **`source.judgmentUrl` wskazuje `ftp://ftp.uzp.gov.pl/KIO/Wyroki/2018_1711.pdf`** — czyli SAOS
  zbierał dokumenty właśnie z tego FTP i przechowuje ich tekst już wyekstrahowany. To zarazem
  niezależne potwierdzenie konwencji nazw `rok_numer.pdf` z sekcji 2.4.

**Wniosek architektoniczny, którego nie było w żadnej perspektywie z osobna:** skoro SAOS ma
2007–2018 z pełnym tekstem i przez udokumentowane API, a UZP i pośrednik pokrywają lata następne,
to **historyczna część korpusu może powstać bez ani jednego żądania do wyszukiwarki UZP**. Jedenaście
lat materiału, już wyekstrahowanego z PDF-ów, których dziś nie da się pobrać z wyłączonego FTP.
Kanał zamrożony jest bezużyteczny jako źródło bieżące i cenny jako źródło archiwalne — to nie jest
ta sama rola i nie należy ich mylić.

Dwa zastrzeżenia do domknięcia przed oparciem się na tym:

- **Wszystkie liczby SAOS w tej sekcji pochodzą zza pośrednika i żadnej z nich ten audyt nie
  potwierdził własnym klientem.** Próba weryfikacyjna wykonana przy przeglądzie tego dokumentu
  (2026-09-14, żądanie wprost na `/api/search/judgments?courtType=NATIONAL_APPEAL_CHAMBER`)
  **również zwróciła 403** — czyli blokada nie ogranicza się do stron HTML, jak sugerował pierwotny
  opis, tylko obejmuje też sam punkt API dla tego klienta. To nie znaczy, że dane są nieprawdziwe;
  znaczy, że **cała sekcja 4.4 stoi na jednym niezależnym kanale** i dopóki pomiar 2 z sekcji 10
  nie padnie, rekomendacja z 13.1 opiera się w połowie na niepotwierdzonym źródle. Traktować jako
  hipotezę roboczą o wysokiej wartości, nie jako pomiar.
- W bazie ogólnej SAOS potwierdzono realne **błędne daty** (rekord z rokiem `3013`, inny z `2101`),
  które przy sortowaniu malejącym wypływają na górę wyników. W podzbiorze KIO takich rekordów nie
  znaleziono, ale to wniosek z zapytania granicznego, nie audyt wszystkich 22 168 pozycji.

Ostatnia rzecz warta odnotowania, bo jest kontrintuicyjna: ostatni commit w repozytorium silnika
SAOS pochodzi z lutego 2021, a mimo to sądy powszechne mają tam rekordy z 2025 i 2026 roku. Import
działa więc dalej bez zmian w kodzie, a **strumień KIO ucichł dwa i pół roku przed zamarciem
repozytorium** — co wskazuje raczej na odcięcie po stronie UZP niż na śmierć projektu. Przyczyny
nie udało się ustalić; żadnego ogłoszenia nie ma.

---

## 5. Warsztat: od pliku do indeksu

Ustalenia z przebiegu 1 (perspektywa techniczna, 2026-09-14). Cztery miejsca, w których spodziewano
się trudności — dwie okazały się mniejsze, niż zakładano, dwie większe.

### 5.1 Dokumenty są cyfrowe u źródła, nie skanowane — OCR odpada

Pobrany i przeanalizowany dokument (sygn. KIO 704/23, `orzeczenia.uzp.gov.pl/Home/PdfContent/19308?Kind=KIO`,
2026-09-14) ma w metadanych `Creator: wkhtmltopdf 0.12.6`, `Producer: Qt 4.8.7` i tytuł zaczynający
się od „Microsoft Word — ". UZP renderuje PDF-y potokiem **Word → HTML → wkhtmltopdf**. Warstwa
tekstowa jest natywna (Arial/Calibri, FlateDecode), więc `pdfplumber` albo `PyMuPDF` powinny dawać
tekst z polskimi znakami diakrytycznymi praktycznie bez szumu.

To **odwraca domyślne założenie** o korpusach prawniczych, gdzie OCR bywa głównym źródłem błędów.
Konsekwencja praktyczna: cała rodzina narzędzi do analizy układu wizyjnego (Docling, modele
trenowane na DocLayNet) jest tu prawdopodobnie zbędna, a wystarczy segmentacja regułowa — stały,
mały zestaw nagłówków („Sygn. akt", „WYROK", „UZASADNIENIE", „Orzeka:") plus heurystyka rozmiaru
czcionki z PyMuPDF. Struktura dokumentu jest bowiem **wyłącznie typograficzna**: nie ma tagowanego
PDF-a ani PDF/UA, choć w badanym pliku były zakładki (outline) odpowiadające sekcjom.

**Zastrzeżenie, które trzeba domknąć pomiarem, a nie założeniem:** to jest **jeden dokument
z 2023 roku**, nie próbka. Orzeczenia archiwalne — z okolic 2007–2010, gdy Izba zaczynała — mogły
powstawać innym potokiem i mogą być skanami. Zanim ktoś napisze „OCR niepotrzebny" w kodzie, ma
pobrać próbkę z najstarszej dostępnej partii i to sprawdzić.

### 5.2 Fleksja: różnica między analizatorami jest zmierzona i wynosi kilkanaście punktów

W ewaluacji wyszukiwania na polskich zdaniach w Lucene **Morfologik osiągnął 85,7 % wobec 73,0 %
dla Stempela**. Różnica ma źródło w konstrukcji: Morfologik jest słownikowy (pełna lematyzacja),
Stempel algorytmiczny (reguły wyuczone z korpusu), więc traci systematycznie na formach nietypowych
— a tekst prawniczy jest ich pełen: terminologia łacińska, nazwiska w odmianie, rzadkie formy.

Dla PostgreSQL sytuacja jest inna i warto ją znać przed wyborem: polskie słowniki `tsearch` to
nieoficjalne pliki ispell/hunspell od społeczności (sjp.pl, LibreOffice), konwertowane ręcznie
i utrzymywane przez pojedyncze osoby. **Nie mają żadnego niezależnego pomiaru jakości** — to białe
pole, nie zła ocena. Rekomendacja: zacząć od wyszukiwania pełnotekstowego w bazie, którą i tak masz,
a migrację do Elasticsearch z wtyczką Morfologik podejmować **dopiero po pomiarze na własnym
zestawie zapytań**, nie z przeczucia.

### 5.3 Sprostowania: to jest udokumentowany defekt tego rejestru, nie hipoteza

Wersje elektroniczne orzeczeń KIO **nie były aktualizowane po sprostowaniu** — postanowienie
prostujące oczywistą omyłkę (art. 350 k.p.c.) nie nadpisywało opublikowanego pliku. To ustalenie
dotyczy nieistniejącego już FTP; **jak zachowuje się w tej sprawie wyszukiwarka WWW, nie wiadomo**
i jest to jedno z tańszych pytań do zmierzenia (kilka zapytań o znaną sprawę ze sprostowaniem).

Istotne jest to, że w grze są **dwa różne klucze**: wewnętrzny identyfikator liczbowy w URL
(`19308`) i sygnatura prawna (`KIO 704/23`). To dokładnie kształt miny 1 z sekcji 11. Deduplikacja
treści (SimHash/MinHash) wykryje „to ten sam dokument po korekcie", ale **nie odpowie, który wariant
jest prawnie aktualny** — to jest decyzja projektowa, nie zadanie dla algorytmu podobieństwa.

### 5.4 Wyszukiwanie znaczeniowe: kolejność „najpierw dosłownie" ma poparcie w pomiarach

Trzy rzeczy zmierzone, z których wynika ta sama kolejność:

- **Model musi być polski.** W PL-MTEB (11 zadań retrieval) modele trenowane pod polski biją
  wielojęzyczne ogólnego przeznaczenia z dużym marginesem: `stella-pl-retrieval-8k` nDCG@10 **61,59**
  i `mmlw-retrieval-roberta-large-v2` **58,35**, wobec `multilingual-e5-large` **52,43** i LaBSE
  **27,36**. Ostatnia liczba jest ostrzeżeniem: „weź jakiś model embeddingów" potrafi dać jakość
  bliską przypadkowej.
- **Nie trzeba za to płacić.** Modele polskie (OPI-PIB/PolDense, rodzina mmlw) są dostępne lokalnie
  na HuggingFace, więc próg kosztowy wejścia w wyszukiwanie znaczeniowe jest niski.
- **BM25 zostaje mocnym punktem odniesienia w domenie prawnej**, bo terminologia jest precyzyjna
  i dopasowanie leksykalne dobrze ją chwyta; układy hybrydowe (BM25 + gęsty, z przewagą wagi po
  stronie BM25) biją każdą metodę osobno.

Wniosek nie jest etapowy, tylko docelowy: dla korpusu jednej wąskiej domeny dobrze zestrojone
wyszukiwanie pełnotekstowe pokrywa większość zapytań, a warstwa znaczeniowa zarabia na siebie tam,
gdzie pytanie jest pojęciowe („czy Izba orzekała o rażąco niskiej cenie przy robotach budowlanych"),
a nie frazowe. Docelowo hybryda, nie zamiana jednego na drugie.

---

## 6. Co przenosimy z `ceidg-tool`, a co było tam lokalnym rozwiązaniem

Decyzja właściciela (2026-09-14): **nowe repozytorium, wzorce przeniesione, bez wspólnej
biblioteki.** Dwa projekty to za mało, żeby znieść koszt wersjonowania wspólnego API; trzeci
projekt byłby momentem, w którym warto to przemyśleć ponownie.

Przenosi się dobrze — skopiuj i dostosuj, zachowując komentarze, bo one niosą powód:

| Moduł CEIDG | Co robi | Dlaczego przenośny |
|---|---|---|
| `ratelimit.py` | odstęp między żądaniami, budżet, czekanie w plastrach z pulsem | problem identyczny: długa operacja przeciw obcemu serwerowi |
| `store.py` (wzorzec) | SQLite, surowy dokument obok znormalizowanych kolumn, dzierżawa blokady | pozwala przeliczyć korpus po zmianie parsera bez ponownego pobierania |
| `httpclient.py` | jedyne miejsce budujące `httpx.Client`, brama wyjścia, lista dozwolonych hostów | reguła „jedno miejsce" jest tym, co czyni politykę wyjścia sprawdzalną |
| `richtext.py` + `safetext.py` | neutralizacja tekstu z zewnątrz przed terminalem i arkuszem | **tu ważniejsze niż w CEIDG** — patrz niżej |
| `ui/texts.py` + `ui/render.py` | modele widoku bez biblioteki wyjścia | każdy ekran testowalny bez terminala |
| `progress.py` (`Events`) | postęp jako protokół, nie jako `print` | pozwala `client` i `store` nie widzieć `rich` |
| `clock.py` | czas jako wstrzykiwana zależność | bez tego testy czekania są niewykonalne |
| `criteria.py` (wzorzec) | jedyny kontrakt między wejściem a pobraniem | patrz sekcja 8 |
| `tests/test_boundaries.py` | skan AST pilnujący reguł granic | reguła bez mechanicznego strażnika jest życzeniem |

**`safetext` przenosi się z podwyższonym priorytetem.** W CEIDG wrogim wejściem była nazwa firmy
z rejestru — kilkadziesiąt znaków. Tutaj wrogim wejściem jest **cały dokument**: kilkanaście stron,
w których występują cytaty z ofert, nazwy plików, fragmenty specyfikacji i przytoczenia pism stron.
Wszystko to trafia do arkusza (gdzie wiodące `=` jest formułą) i na ekran (gdzie `rich` czyta
nawiasy kwadratowe jako znaczniki). Powierzchnia jest o rząd wielkości większa niż w CEIDG i rośnie
z każdym pobranym dokumentem.

Nie przenosi się — to były rozwiązania problemów, których tu (jeszcze) nie ma:

- **`apiprofile.py`** — CEIDG miał udokumentowany interfejs z parametrami, więc profil API jako
  dane był na to odpowiedzią. Dopóki nie wiadomo, czym jest źródło KIO (sekcja 2), nie ma czego
  profilować, a wprowadzenie tej abstrakcji przed pomiarem to zgadywanie kształtu.
- **`pkdmap.py` i `recordid.py` w obecnej postaci** — obie rozwiązują problem tożsamości
  specyficzny dla CEIDG. **Ale sam kształt problemu wraca**, i to jest najważniejsze zdanie tej
  sekcji: patrz sekcja 11, mina 1.
- **`batching.py`** — dzielenie zapytania po datach było odpowiedzią na limit stron w API. Czy ten
  problem tu istnieje, rozstrzyga pomiar, nie analogia.

---

## 7. Doktryna, która obowiązuje od pierwszego commita

Cztery zasady, które w `ceidg-tool` zapisano dopiero po tym, jak ich brak coś kosztował.
W nowym projekcie mają obowiązywać od początku, bo koszt ich wprowadzenia jest wtedy zerowy.

### 7.1 Żadnej liczby bez źródła i daty

W CEIDG jedna ręcznie napisana linia w atrapie testowej podtrzymywała przez tydzień fałszywe
przekonanie o tym, jak działa rejestr — a dokument decyzyjny cytował ją jako pomiar. Stąd zasada:
**to, co napisała atrapa, nie jest obserwacją.** Liczba w dokumencie ma przy sobie datę i sposób
uzyskania: „zmierzone 2026-09-14, N żądań" albo „policzone z pliku X, 0 żądań".

Zasada ma tu ostrzejszą wersję niż w CEIDG, z powodu materiału: **sygnatury, nazwy własne i treść
przepisów nigdy nie pochodzą z pamięci modelu.** W CEIDG kosztowała to lekcja z nazwami PKD — model
potrafi wygenerować listę, która przejdzie każdy automatyczny test (poprawny format, właściwa
liczba pozycji, zgodność z tym, co zwrócił rejestr) i będzie cicho nieprawdziwa w warstwie, której
nikt nie czyta obok źródła. Orzecznictwo jest na to jeszcze podatniejsze: sygnatura `KIO 1234/25`
wygląda tak samo niezależnie od tego, czy istnieje, a zdanie „Izba wskazała, że…" brzmi wiarygodnie
niezależnie od tego, czy Izba tak wskazała.

### 7.2 Cisza jest usterką i mierzy się ją w żądaniach

Operacja budująca korpus może pracować godzinami. Odcinek bez wyjścia nie czyta się jako „pracuje" —
czyta się jako „zawiesiło się", a program, który wygląda na zawieszony, zostaje zabity. Puls postępu
i odświeżanie dzierżawy blokady liczy się w **żądaniach wysłanych albo dokumentach zapisanych**,
nigdy w stronach wyników ani w dopasowanych sprawach. Pomyłka o jedną warstwę dała w CEIDG cztery
osobne usterki jednego dnia, w tym wygaśnięcie blokady bazy pod pracującym procesem.

Czekanie też ma zostawiać ślad **w pliku dziennika**, nie tylko na ekranie, i zapisywać przewidywany
moment wznowienia — bo sam czas trwania nie odróżnia po fakcie wstrzymania przez limiter od uśpienia
laptopa.

### 7.3 Gwarancja bez obserwatora nie jest gwarancją

Przy każdym zabezpieczeniu zadaj pytanie: **co by się wypisało, gdyby zostało naruszone?** Jeśli
uczciwa odpowiedź brzmi „nic", to jest usterka, a nie zabezpieczenie. W CEIDG trzy takie zamknięto
jednego dnia i wszystkie miały ten sam kształt: niezmiennik tożsamości ukryty za pobłażliwym
`.upper()`, utrata dzierżawy blokady za odrzuconym `rowcount`, dziesięć godzin czekania bez śladu
w dzienniku.

### 7.4 Dowód sanityzuje się dokładnie z tego, co ważne

Skrypt budujący materiał testowy w CEIDG zamieniał identyfikatory na wielkie litery — więc pakiet
testów potwierdzał brak dokładnie tej cechy, która wywróciła produkcję. **Sprawdzaj generator
materiału dowodowego, nie tylko sam materiał.** Ten kształt wystąpił tam trzykrotnie. Przy
orzeczeniach dochodzi wariant własny: dokument z anonimizacją zastosowaną przez urząd wygląda jak
dokument bez danych osobowych, ale nim nie jest — patrz sekcja 3.

---

## 8. Architektura wyjściowa i reguły granic

### 8.1 Jedna decyzja, która jest tu ważniejsza niż w CEIDG: kanał jest wymienny

Sekcja 2 zostawia kanał akwizycji nierozstrzygnięty, a sekcja 4 pokazuje, że kandydaci są co
najmniej trzej (wyszukiwarka UZP, cudze API pośrednika, SAOS) i różnią się wszystkim. Z tego
wynika reguła architektoniczna, której CEIDG nie potrzebował: **kanał ma być za jednym interfejsem,
z osobną implementacją na każdego kandydata.**

Nie jest to abstrakcja na zapas. Jest to jedyny układ, w którym da się kanały **porównać na
danych** — pobrać tę samą sprawę dwoma drogami i sprawdzić, czy zgadza się treść. A skoro
pośrednik jest podejrzany o niekompletność, a scraper o kruchość, takie porównanie jest jedynym
sposobem, żeby wiedzieć, którym się jedzie.

```
wejścia: cli.py (flagi), ui/wizard.py, faza 2: assistant/
         |  wszystkie przez ui/flow.py -> jedna sekwencja decyzji
         v
    criteria.py      CZYSTY: pydantic, bez I/O; jedyny kontrakt wejścia
         |
         v
    pipeline.py      orkiestracja; jedyny moduł znający i sieć, i bazę
      |       |          |            |
      v       v          v            v
  source/   store.py  parser.py   exporter.py
  (adaptery)          (CZYSTY)
      |
      v
  httpclient.py  ->  ratelimit.py  ->  clock.py
```

### 8.2 Surowy dokument zapisuje się przed sparsowaniem — i to jest reguła, nie optymalizacja

W CEIDG obok znormalizowanych kolumn leżał surowy JSON i to pozwalało przeliczyć bazę po zmianie
normalizatora bez ponownego odpytywania rejestru. Tutaj ta sama zasada ma większą wagę, bo parser
dokumentu prawniczego **na pewno będzie się zmieniał** — segmentacja po nagłówkach typograficznych
jest heurystyką, a heurystyki się poprawia.

Stąd: `store` zapisuje **bajty dokumentu tak, jak przyszły**, razem z sumą kontrolną, a `parser`
jest czysty — nie sięga do sieci, dostaje bajty i zwraca strukturę. Konsekwencja praktyczna: zmiana
parsera kosztuje przeliczenie lokalne, zero żądań. Bez tej reguły każda poprawka segmentacji
oznaczałaby ponowne obciążenie cudzego serwera, który — przypomnijmy z 2.2 — renderuje każdy PDF
na żądanie.

### 8.3 Reguły granic

Reguły 1–14 przenoszą się z CEIDG i mają być egzekwowane **skanem AST od pierwszego commita**, nie
przeglądem — z jednym wyjątkiem, który tam też jest wyjątkiem: reguła 14 jest niesiona przez mypy
strict na typie własnym, nie przez skan, i dokument projektowy ma to mówić wprost, zamiast liczyć
ją do pokrycia skanu. Dwie ostatnie są nowe i wynikają z tego audytu.

1. `criteria.py`, `docid.py`, `dictionaries.py` oraz **każdy moduł w `parser/` (rekursywnie)**
   nie importują `httpx`, `sqlite3`, `openpyxl`, `rich`, `os`. Moduły czyste spoza `parser/`
   są w teście wyliczone wprost i mają test istnienia pliku; `parser/` jest skanowany
   rekursywnie, żeby nowy moduł parsera podlegał regule bez dopisywania go do listy.
   `config.py` do modułów czystych **nie** należy — importuje `os` i ma do tego powód
   (adres kontaktowy ze środowiska). *(brzmienie z ADR-0003, przyjęte 2026-09-15)*
2. Żaden moduł w `source/` — **rekursywnie, `source/**/*.py`** — nie importuje `store` ani
   `sqlite3`; historię żądań dostaje jako protokół. Słowo „rekursywnie" jest tu nośne:
   `Path("source").glob("*.py")` jest skanem, który wygląda na działający dokładnie do dnia,
   w którym kanały stają się pakietami, a potem nie obejmuje niczego — bez jednego
   czerwonego testu. *(ADR-0003)*
3. `store.py` nie importuje `httpx`.
4. Żaden moduł w `source/` (rekursywnie) ani `store.py` nie importuje `rich`; postęp idzie
   przez protokół `Events`. *(ADR-0003)*
5. Tylko `pipeline.py` importuje jednocześnie `source` i `store`.
6. Moduły czyste i `ui/texts.py` nie importują `rich`, `questionary`, `typer`, `httpx`, `anthropic`,
   `sqlite3`, `openpyxl`.
7. Tylko `ui/prompts.py` importuje `questionary`; tylko `richtext.py`, `ui/render.py` i `console.py`
   importują `rich`.
8. `ui/*` nie importuje `source` ani `store` — idzie przez `pipeline`.
9. `cli.py` nie pisze żadnego zdania do użytkownika; każdy blok pochodzi z `ui/texts.py`.
10. Każdy napis z zewnątrz trafiający do `rich` przechodzi przez `richtext.safe`.
11. **Jeden właściciel na protokół, jedna kopia polityki wyjścia.** *(brzmienie z ADR-0003,
    przyjęte 2026-09-15)* Konstrukt otwierający połączenie sieciowe powstaje wyłącznie
    w module-właścicielu przypisanym do jego protokołu. Dziś właściciel jest jeden —
    `kio_tool/httpclient.py` — i buduje wyłącznie `httpx.Client` / `httpx.AsyncClient`,
    zawsze z wstrzykniętym transportem i `trust_env=False`. Tablica `EGRESS_OWNERS`
    w `tests/test_boundaries.py` wymienia **konstrukty, nie biblioteki**: `httpx.Client`,
    `httpx.AsyncClient`, `ftplib.FTP`, `ftplib.FTP_TLS`, `socket.socket`,
    `socket.create_connection`, `urllib.request.urlopen`, `urllib.request.build_opener`,
    `asyncio.open_connection`. Pozycja z pustym zbiorem właścicieli znaczy „żaden plik nie ma
    prawa tego zbudować"; żeby ją zbudować, trzeba najpierw dopisać właściciela do tablicy
    i regułę wyjścia do dokumentu architektury. Zakres skanu obejmuje `kio_tool/`, `tests/`
    oraz `scripts/`, jeśli powstanie: sonda niesie ten sam ruch co narzędzie, więc reguła
    obowiązuje i ją.

    Powód, dla którego reguła mówi o protokole, a nie o `httpx`: `httpx` nie obsługuje FTP,
    a polityka wyjścia odmawia wszystkiemu poza `https`. Zdanie „jedno miejsce buduje klienta
    i jest bramką wyjścia" w poprzednim brzmieniu obejmowało kanał FTP wyłącznie na rysunku.
    W `ceidg-tool` ten sam kształt wystąpił raz wcześniej — skan dopasowywał nazwę `httpx`
    i przepuszczał `httpx2` spod SDK modelu — i został naprawiony zamianą nazwy na zbiór;
    tu zamiana idzie o poziom dalej, ze zbioru bibliotek na tablicę konstruktów z właścicielem.
12. Jeden właściciel klienta SDK modelu, z jawnym `api_key=` i `http_client=` w każdym wywołaniu.
13. **`mcp_server.py` importuje wyłącznie `store` (odczyt) i `exporter`; nie importuje
    `source`, `pipeline` ani `criteria`.** *(brzmienie z ADR-0003, przyjęte 2026-09-15;
    poprzednie mówiło o `assistant/*`, a decyzja 3 zastąpiła asystenta w procesie serwerem
    MCP — architektura 4.10)* W CEIDG ta reguła jest strukturalną postacią zdania „do modelu
    idzie pytanie i słownik, pobrane rekordy nigdy": rekordy nie mogą tam dotrzeć, bo nie ma
    krawędzi importu, którą mogłyby pójść — a to mocniejsze twierdzenie niż staranność przy
    budowaniu promptu. **Tutaj waży jeszcze więcej niż tam**, bo faza 4 z założenia ma sięgać
    po treść, więc granica musi być widoczna, a nie domniemana. Serwer MCP czyni ją przy tym
    granicą **procesu**, nie tylko importów: korpus jest po jednej stronie gniazda, model po
    drugiej. Do czasu fazy 4 reguła jest wyzwalaczem — plik nie istnieje, więc skan przechodzi
    pusto, ale dzień jego powstania zapala ją sam.
14. **Jeden producent kanonicznej tożsamości dokumentu.** Odpowiednik `recordid.py`. Powód
    w minie 1; niesione przez mypy strict na typie własnym, nie przez skan AST.
15. **Nowa: każdy eksport i każdy widok cytujący orzeczenie niesie sygnaturę, datę wydania
    i oznaczenie organu.** To nie jest konwencja redakcyjna, tylko **warunek ustawowy z art. 15
    ust. 1 pkt 4** (sekcja 3.2), więc ma mieć test, który go pilnuje — dokładnie w duchu zasady 7.3:
    gwarancja bez obserwatora nie jest gwarancją.
16. **Nowa: narzędzie nie omija zabezpieczeń.** Żadnego rozwiązywania CAPTCHA, rotacji
    identyfikatora klienta w celu ominięcia blokady, ani obchodzenia ograniczeń tempa. Granica jest
    prawna, nie estetyczna (sekcja 3.5, art. 267 § 1 k.k.): przy odmowie serwisu narzędzie
    zatrzymuje się i mówi o tym operatorowi. Tej reguły nie da się w pełni sprawdzić skanem — ma
    być pozycją listy kontrolnej przeglądu kodu i ma być wymieniona w opisie projektu.

---

## 9. Plan faz i bramki

Faza kończy się, gdy właściciel ją przyjmie, a nie gdy testy przechodzą. Tak było w CEIDG i tu
zostaje bez zmian.

### Faza 0 — sonda źródła. Zero kodu produktowego

Jedyna faza, której produktem jest **dokument, nie program**. Wykonać pomiary z sekcji 10, zapisać
je w `docs/decisions.md` w formacie „zmierzone {data}, {liczba} żądań", i dopiero na tej podstawie
wybrać kanał. Skrypty sondujące są jednorazowe i mieszkają w `scripts/`, nie w pakiecie.

**Bramka:** właściciel widzi tabelę kandydatów z pomiarami i wybiera kanał. Przed tą bramką nie
powstaje `source/`, bo nie wiadomo, co ma implementować.

### Faza 1 — akwizycja i korpus

Adapter wybranego kanału, `store` z surowymi bajtami i sumą kontrolną, limiter z pulsem, wznawianie
przerwanego przebiegu, dziennik. Tożsamość dokumentu rozstrzygnięta i zapisana w ADR **przed**
pierwszym zapisem do bazy.

**Bramka:** przebieg na ograniczonym zakresie (np. jeden rocznik), przerwany w połowie i wznowiony,
kończy się korpusem bez duplikatów; ta sama sprawa pobrana dwa razy nie tworzy drugiego wpisu.

### Faza 2 — parser i struktura

Czysty parser bajtów na strukturę: sygnatura, data, skład, rodzaj rozstrzygnięcia, sentencja,
uzasadnienie, powołane przepisy. Segmentacja regułowa (5.1). Korpus przeliczalny lokalnie.

**Bramka:** przeliczenie całego korpusu bez ani jednego żądania sieciowego, i raport pokrycia —
ile dokumentów sparsowało się w całości, ile częściowo, ile wcale, z rozbiciem na roczniki. Ten
raport jest ważniejszy niż sam parser: pokazuje, gdzie materiał jest niejednorodny.

### Faza 3 — wyszukiwanie, eksport, kreator

Wyszukiwanie pełnotekstowe (5.2), eksport z obowiązkową atrybucją (reguła 14), kreator prowadzący
operatora, tabela kosztów przed pobraniem, tryb pokazowy.

**Tryb pokazowy zbudować tutaj, nie na końcu.** W CEIDG powstał późno i notatki projektu mówią
wprost, że istnieje „mniej dla pokazu, a bardziej dla przetrwania" — bez niego nie było jak
uruchomić narzędzia, nie dotykając prawdziwych danych. Tutaj argument jest mocniejszy: każdy
przebieg testowy obciąża cudzy serwer, który renderuje PDF-y na żądanie. Korpus pokazowy ma być
**generowany**, nie skopiowany z prawdziwych orzeczeń — patrz zasada 7.4 i mina 4.

**Bramka:** operator przechodzi całą ścieżkę bez pomocy autora, na trybie pokazowym.

### Faza 4 — warstwa modelu (druga faza produktu)

**Wejście do tej fazy jest warunkowe** i to jest jedyne miejsce w planie, gdzie bramka stoi przed
fazą, a nie za nią. Warunki: opis przeznaczenia narzędzia napisany i skonfrontowany z Załącznikiem
III AI Act (3.6), oraz ADR rozstrzygający, czy treść orzeczenia wolno wysłać do modelu (sekcja 12).
Zakres ograniczony do **wspomagania wyszukiwania i cytowania** — nie do generowania oceny prawnej,
z powodu zmierzonego w 4.3.

---

## 10. Pomiary do wykonania w fazie 0 — lista, nie założenia

Kolejność jest posortowana po tym, **ile decyzji odblokowuje pomiar**, nie po trudności. Pierwsze
trzy rozstrzygają wybór kanału i dopóki nie padną, `source/` nie ma co implementować.

| # | Pomiar | Jak najtaniej | Co rozstrzyga |
|---|---|---|---|
| 1 | Czy `ftp.uzp.gov.pl` **nadal odpowiada** | `curl ftp://ftp.uzp.gov.pl/KIO/Wyroki/` z osobnej maszyny; data najnowszego pliku | Komunikat mówi o zaprzestaniu *publikacji*, nie o wyłączeniu serwera. Jeśli archiwum żyje, 18 lat materiału jest do wzięcia hurtem — i cały plan akwizycji się zmienia |
| 2 | Czy **własny klient** dostaje się do API SAOS | jedno żądanie na `/api/search/judgments?courtType=NATIONAL_APPEAL_CHAMBER` własnym `httpx` | Pomiary uzyskano przez pośrednika; 403 dotyczyło stron HTML. Jeśli własny klient przechodzi — lata 2007–2018 są za darmo, z pełnym tekstem |
| 3 | Czy `/api/kio/{slug}` **naprawdę zwraca pełny tekst** i jakie jest opóźnienie | pobrać tę samą sprawę z Atlasu i z UZP, porównać treść i datę pojawienia się | Dostawca deklaruje pełny tekst i „opóźnienie" bez liczby. Bez tego porównania nie wiadomo, czy pośrednik zastępuje źródło, czy tylko je przybliża |
| 4 | **Kontrakt `/Home/Move`** w wyszukiwarce UZP | podejrzeć ruch w narzędziach deweloperskich przeglądarki | Skąd bierze się `total` przy pierwszym zapytaniu i czy da się przejść cały zbiór. Zgadywanie tego kosztowałoby serię ślepych żądań |
| 5 | **Warstwa tekstowa** w próbce ~50 dokumentów z roczników 2007, 2010, 2015, 2020, 2025 | `pdftotext`/`pypdf`, policzyć udział | Czy w potoku potrzebny jest OCR. Dowód tekstowości jest dziś pośredni i sięga 2008, nie 2007 |
| 6 | **Granice przestrzeni identyfikatorów** | dwudzielne szukanie górnej granicy; próbka na luki; czy `Kind=KIO` i `Kind=SO` dzielą numerację | Czy enumeracja jest w ogóle strategią i ile dokumentów naprawdę jest |
| 7 | **Sprostowania**: nowy rekord czy nadpisanie? | znaleźć sprawę z opublikowanym sprostowaniem i sprawdzić, jak figuruje | Rozstrzyga tożsamość dokumentu (mina 1). Musi paść **przed** pierwszym zapisem do bazy |
| 8 | **Dokumenty wielosygnaturowe** w wyszukiwarce | sprawdzić, czy sprawy łączone mają jeden wpis, czy kilka | Potwierdzone dla plików FTP; nie wiadomo, jak reprezentuje je wyszukiwarka |
| 9 | **Tolerancja serwisu na tempo** | ostrożne narastanie, z zatrzymaniem przy pierwszym sygnale | Nie zmierzono nic. PDF-y są renderowane na żądanie, więc próg może być niski. **Wymaga zgody właściciela** |
| 10 | **Anonimizacja** na większej próbce | 30–50 orzeczeń, w tym sprzed 2015 i z protokołem rozprawy | Domknąć kategorie „pełnomocnicy" i „świadkowie" oraz sprawdzić, czy inicjalizacja bywa przeoczona |
| 11 | Co indeksuje **„Hasło"** i co dokłada **„Szukaj również w treści"** | dwa zapytania o frazę występującą tylko w uzasadnieniu | Mina 2. Bez tego nie wiadomo, co znaczy pusty wynik |
| 12 | Zbiór KIO w **`dane.gov.pl`** | bezpośrednie przeszukanie katalogu | Wynik negatywny pochodzi z wyszukiwarki portalu, nie z przeglądu katalogu |
| 13 | **Jak często data wydania jest pusta** | próbka po identyfikatorach, policzyć braki | Potwierdzone na `Details/1`. Rekord bez daty wypada z każdego filtru zakresowego po cichu — trzeba wiedzieć, czy to wyjątek, czy klasa |

Każdy wynik ląduje w `docs/decisions.md` w formacie zdania z datą i liczbą żądań. Pomiary 1–3
i 5–8 są tanie i bezpieczne; **pomiar 9 jest jedynym, który celowo obciąża cudzy serwis** i dlatego
wymaga osobnej zgody, tak jak w CEIDG wymagało jej dotknięcie produkcji.

---

## 11. Miny — cztery rzeczy, które w CEIDG kosztowały po dniu

**Mina 1: tożsamość dokumentu.** W CEIDG jeden wpis miał dwie pisownie identyfikatora — jeden punkt
końcowy zwracał wielkimi literami, drugi małymi — a klucz główny był wrażliwy na wielkość liter.
Skutek: każdy zmieniony wpis zapisywał się dwa razy, cache nigdy nie trafiał, jedna noc kosztowała
2 681 żądań i zero użytecznych rekordów. **Zanim zapiszesz pierwszy dokument, rozstrzygnij, czym
jest tożsamość orzeczenia** — i udowodnij to na danych, nie z definicji. Kandydat oczywisty to
sygnatura, i właśnie dlatego jest podejrzany. Do rozstrzygnięcia: czy sygnatura jest unikalna
w skali całego zbioru, czy tylko w roczniku; co się dzieje przy sprawach połączonych, gdzie jeden
dokument nosi kilka sygnatur; czy istnieją sprostowania i czy nadpisują dokument, czy tworzą nowy;
czy jedna sprawa może mieć i postanowienie, i wyrok; oraz czy dokument pobrany dwa razy jest
bitowo tożsamy. Odpowiednikiem tego ostatniego w CEIDG był wiersz raportu bez numeru — klucz
liczony z pozycji porządkowej w pliku dawał tej samej firmie nową tożsamość w każdym pobraniu.

**Mina 2: filtr nie znaczy tego, co nazwa filtra.** W CEIDG parametr `pkd` dopasowywał kod tak, jak
jest zapisany na rekordzie, a nie w bieżącej klasyfikacji — więc zapytanie formalnie poprawne cicho
zwracało podzbiór, i dotyczyło to 8,6 % rejestru. Przy wyszukiwarce KIO to samo pytanie brzmi:
**co właściwie indeksuje pole „Hasło" i co dokłada opcja „Szukaj również w treści".** Dopóki nie
wiesz, czy przeszukanie obejmuje uzasadnienie, czy tylko metadane, nie wiesz, co znaczy pusty
wynik. Zasada ogólna: **„kryterium jest poprawne" to nie to samo, co „wynik jest kompletny"** —
i interfejs ma mówić, czego zapytanie nie obejmuje.

**Mina 3: naprawa jednej cichej straty odsłania drugą.** W CEIDG przywrócenie cache'u szczegółów
uaktywniło usterkę progu świeżości, która wcześniej była niewidoczna, bo nic nie docierało do
warstwy, w której tkwiła. Po każdej naprawie zapytaj, co ta naprawa właśnie uruchomiła.

**Mina 4: dane odniesienia budowane z pamięci przechodzą wszystkie testy.** Pierwsza wersja korpusu
pokazowego w CEIDG miała wymyślone nazwy branż, dwa nieistniejące kody i cztery z pięciu miast
przypisane do złego powiatu. Wszystko przeszło bramki, bo nic tego nie sprawdzało. Jeśli nowe
narzędzie będzie miało słownik — przepisów Pzp, haseł indeksu tematycznego, rodzajów rozstrzygnięć —
**ma być generowany ze źródła, z zapisanym SHA-256 tego źródła, nigdy pisany ręcznie ani przez
model.**

---

## 12. Czego nie wolno zrobić

- **Nie wolno wysłać żądania do serwisu produkcyjnego bez zgody właściciela udzielonej w bieżącej
  sesji.** Reguła przenosi się z CEIDG bez zmian, choć z innego powodu: tam chodziło o dane osobowe
  w rejestrze, tu o obciążenie cudzego serwisu i o warunki z sekcji 3. Zgoda z poprzedniej sesji
  nie jest zgodą.
- **Nie wolno budować `httpx.Client` poza jednym modułem** i nie wolno pominąć wstrzyknięcia
  transportu — to ono, a nie sama konfiguracja, powstrzymuje `httpx` przed odczytaniem
  `HTTPS_PROXY` ze środowiska; osobnym mechanizmem (`trust_env=False`) wyłącza się podmianę
  zestawu certyfikatów przez `SSL_CERT_FILE`. Dwa różne mechanizmy na dwie połowy tego samego
  problemu, łatwe do pomylenia.
- **Nie wolno wysłać treści orzeczenia do modelu bez decyzji zapisanej w ADR.** W CEIDG rekordy nie
  szły do modelu nigdy — szło pytanie i słownik, a dwie listy dozwolonych hostów są celowo
  rozłączne i pilnuje tego test. Tutaj sens fazy 2 zakłada wysyłanie treści, więc to jest realna
  decyzja do podjęcia, a nie formalność: patrz sekcje 3 i 13.
- **Nie wolno pisać zdania do użytkownika z `cli.py`.** Wygląda na kaprys, a jest warunkiem
  sprawdzalności reguły o neutralizacji obcego tekstu: dopóki `cli` drukuje sam, „każdy obcy napis
  przechodzi przez `safe`" wymagałoby analizy przepływu danych przez cały pakiet.
- **Nie wolno dodać `-q` do polecenia pytest**, jeśli konfiguracja już je zawiera — przy `-qq`
  pytest nie drukuje linii podsumowania w ogóle. W CEIDG trzy rewizje dokumentacji cytowały liczbę
  testów, której udokumentowana bramka nie potrafiła wypisać.

---

## 13. Co zostaje do rozstrzygnięcia przez właściciela

### 13.1 Rekomendacja audytu: kanał hybrydowy, a nie jeden

Research nie wskazał zwycięzcy, bo kandydaci pokrywają **różne odcinki czasu**, a nie ten sam
zakres taniej lub drożej. Stąd rekomendacja, którą audyt daje wprost, zamiast wyliczać opcje:

| Odcinek | Kanał | Dlaczego |
|---|---|---|
| 2007-12 – 2018-09 | **SAOS**, API `courtType=NATIONAL_APPEAL_CHAMBER` | 22 168 rekordów z pełnym tekstem, już wyekstrahowanym z PDF-ów, których dziś nie ma skąd pobrać. Zero obciążenia UZP |
| 2018-09 – dziś | **do rozstrzygnięcia po pomiarach 1 i 3** | FTP (jeśli żyje), Atlas (jeśli pełny tekst i akceptowalne opóźnienie), wyszukiwarka UZP jako ostateczność |
| bieżące dopływy | **kanał z odcinka drugiego** | tu liczy się świeżość, więc opóźnienie pośrednika waży najwięcej |

Warto zauważyć, że ta rekomendacja wynika ze złożenia dwóch perspektyw, z których **żadna sama jej
nie zawierała**. Perspektywa techniczna widziała tylko scraping, perspektywa rynkowa tylko
pośredników. Zamrożone archiwum jest bezużyteczne jako źródło bieżące i cenne jako archiwalne —
to nie ta sama rola.

Reguła architektoniczna z 8.1 (kanał za jednym interfejsem) przestaje więc być zapasową
ostrożnością i staje się wymogiem: **korpus i tak będzie składany z dwóch źródeł.**

### 13.2 Pięć decyzji, których audyt nie podejmuje

1. **Czy w ogóle budować** — sekcja 4 mówi „nie" dla potrzeby „wyszukać i przeczytać" (jest Atlas
   za darmo i SzuKIO za ~2 530 zł rocznie) i „tak" dla programowego dostępu do korpusu pod własny
   potok. To rozstrzygnięcie o potrzebie, nie o technologii, i należy do właściciela.
2. **Czy pytać prawnika przed fazą 1, czy przed fazą 4.** Dwa punkty wymagają opinii: relacja
   ochrony baz danych *sui generis* do ustawowego prawa reużycia (3.4) oraz kwalifikacja fazy 2
   pod Załącznik III AI Act (3.6). Pierwszy dotyczy już samego pobierania; drugi dopiero warstwy
   modelu. Audyt rekomenduje **pierwszy przed fazą 1**, bo dotyczy czynności, którą faza 1 wykonuje
   masowo.
3. **Czy faza 2 w ogóle wchodzi w zakres.** Zmierzona granica z 4.3 (żaden z czołowych modeli nie
   przeszedł części praktycznej egzaminu na członka KIO) nie wyklucza wspomagania wyszukiwania
   i cytowania, ale wyklucza to, czego decydent może się po takiej warstwie spodziewać.
   Rozbieżność oczekiwań lepiej zamknąć teraz niż po zbudowaniu.
4. **Reguła zgody na żądania.** W CEIDG obowiązuje zgoda właściciela udzielona w bieżącej sesji na
   dotknięcie produkcji. Tutaj proponowany kształt jest węższy: **zgoda na pomiar 9 (test tempa)
   i na każdy przebieg masowy**, bez zgody na pojedyncze żądanie diagnostyczne — bo dane są
   publiczne, a chroniony jest cudzy serwer, nie osoby.
5. **Gdzie mieszka nowe repozytorium.** Zdalne repozytorium CEIDG to gałąź w projekcie innego
   zespołu. Nowy projekt potrzebuje własnego miejsca i to trzeba uzgodnić, zanim powstanie pierwszy
   commit — nie po nim.

### 13.3 Czego ten audyt nie zrobił

- **Nie wysłał ani jednego żądania w celu pomiaru wydajności.** Wszystkie obserwacje pochodzą
  z pojedynczych odczytów podczas researchu. Sekcja 2.2 mówi „nie zmierzono throttlingu", a nie
  „throttlingu nie ma", i tak ma być czytana.
- **Nie wywołał ani Atlasa, ani SAOS własnym klientem.** Warunki Atlasa odczytano wprost z jego
  dokumentacji, ale **żadnego punktu końcowego nie wywołano**, więc „zwraca pełny tekst" pozostaje
  deklaracją dostawcy. SAOS odpowiadał wyłącznie przez pośrednika i odmówił własnemu klientowi.
  Pomiary 2 i 3 istnieją właśnie po to. Pełny rozkład — sekcja 14.
- **Nie zbadał anonimizacji ilościowo.** Sześć dokumentów to obserwacja praktyki, nie miara jej
  szczelności.
- **Nie rozstrzygnął tożsamości dokumentu.** To jest zadanie fazy 0, pomiar 7, i pierwsza rzecz,
  która pójdzie źle, jeśli zostanie pominięta — w CEIDG kosztowała noc i 2 681 żądań.

---

## 14. Status dowodowy — co sprawdzono przy źródle, a co nie

Ta sekcja jest wynikiem przeglądu weryfikacyjnego wykonanego **po napisaniu sekcji 1–13**, na tym
samym dokumencie, według zasady 7.1: twierdzenie z drugiej ręki nie jest pomiarem, dopóki ktoś nie
zajrzy do źródła. Sprawdzono dwadzieścia cztery twierdzenia nośne. **Cztery okazały się błędne
i zostały poprawione w tekście** — poniższa tabela jest jedynym miejscem, gdzie widać, że były.

Czytaj tę sekcję **przed** oparciem na czymkolwiek z sekcji 2–5. Kolumna „status" mówi, czy wolno
na danym zdaniu budować, czy trzeba je najpierw zmierzyć.

| Twierdzenie | Gdzie | Jak sprawdzone | Status |
|---|---|---|---|
| Zaprzestanie publikacji na FTP z 30.09.2025 | 2.1 | komunikat gov.pl odczytany | **potwierdzone** |
| Komunikat nie mówi o wyłączeniu serwera ani o losie plików | 2.1 | j.w., zakres zdania | **potwierdzone** |
| Instrukcja FTP nadal serwowana, bez adnotacji o wycofaniu | 2.1 | PDF pobrany, pięć stron przeczytanych | **potwierdzone** |
| Adres `ftp://ftp.uzp.gov.pl/KIO/Wyroki/`, logowanie anonimowe | 2.1 | s. 3 instrukcji | **potwierdzone** |
| Konwencja `RRRR_NNNN` z zerami wiodącymi; pliki wielosygnaturowe | 2.4 | listing na s. 5 instrukcji | **poprawione** — była opisana jako niespójna |
| `Elementy: 30 660` w katalogu FTP | 2.4 | j.w. | **potwierdzone**, data zrzutu nieznana |
| Punkty `Details` / `PdfContent` / `ContentHtml` z `Kind=KIO` | 2.2 | dwa dokumenty odczytane | **potwierdzone** |
| Identyfikator niechronologiczny (`1` → 2015, `30442` → 09.09.2025) | 2.2 | oba odczytane | **potwierdzone** |
| `Details/1` ma **pustą** datę wydania | 2.3 | odczytane przy weryfikacji | **nowe ustalenie** |
| `robots.txt` zwraca 404 | 2.2 | żądanie | **potwierdzone** |
| PDF generowany na żądanie przez `wkhtmltopdf` | 2.2, 5.1 | pomiar z researchu | niepotwierdzone samodzielnie |
| Skład orzekający pełnym nazwiskiem, przedsiębiorca inicjałami, pełnomocnicy nieobecni | 3.3 | orzeczenie odczytane wprost | **potwierdzone** |
| Atlas: pięć punktów KIO, CC BY 4.0, wymagana atrybucja, zastrzeżenie kompletności | 4.2 | dokumentacja odczytana | **potwierdzone** |
| Atlas: 1500/dobę/IP, 5000/konto, 500/min chwilowo | 4.2 | j.w. | **potwierdzone** |
| Atlas: pula `/api/llm/*` z limitem 30/min | 4.2 | nie znaleziono w dokumentacji | **obalone**, usunięte z tekstu |
| Atlas: 29 482 orzeczeń, źródło `orzeczenia.uzp.gov.pl`, opóźnienie bez liczby | 4.1, 4.2 | strona odczytana | **potwierdzone** |
| `kio-orzeczenia-mcp`: POC v0.1.0, Apache-2.0, dwie gwiazdki, 1 żąd./s, 10 wyników na stronę | 4.2 | repozytorium odczytane | **potwierdzone** |
| Tamże: powiadomienie UZP przed produkcją, ze statusem TODO | 4.2 | j.w. | **potwierdzone** |
| arXiv 2511.04205: tytuł, zgłoszenie 6.11.2025, próg w części praktycznej nieosiągnięty | 4.3 | abstrakt odczytany | **potwierdzone** |
| Skład badanych modeli w tej pracy | 4.3 | źródła podają różne pokolenia Claude | **sporne**, zastrzeżone w tekście |
| SAOS: 22 168 rekordów, 2007-12-10 → 2018-09-06, pełny tekst | 4.4 | **własny klient też dostał 403** | **niepotwierdzone** |
| Morfologik 85,7 % wobec Stempela 73,0 % | 5.2 | z pracy przeglądowej, nie od źródła | niepotwierdzone samodzielnie |
| PL-MTEB: nDCG@10 dla modeli polskich i wielojęzycznych | 5.4 | j.w. | niepotwierdzone samodzielnie |
| Ustawa o otwartych danych: art. 6 ust. 2, 7 ust. 2, 15 ust. 1 pkt 4 | 3.2 | źródła wtórne; ISAP za captchą | **do sprawdzenia w Dzienniku Ustaw** |
| SzuKIO: ~53,57 zł/mies., 2 530 zł/rok | 4.1 | ze snippetów; serwis zwrócił 429 | niepotwierdzone |
| CEIDG: 2 681 żądań, 8,6 %, `addopts = "-q"` | 7, 11, 12 | odczyt z repozytorium | **potwierdzone** |
| Reguły granic przeniesione z CEIDG | 8.3 | `docs/design/phase2_core.md` | **poprawione** — brakowało reguły 13 |

### 14.1 Cztery poprawki, i czego uczą

1. **Zgubiona reguła granic.** Sekcja 8.3 wymieniała dwanaście reguł CEIDG i nazywała „nową" tę,
   która jest tam regułą 14 — a jednocześnie gubiła regułę 13, mówiącą, że warstwa modelu nie
   importuje ani źródła, ani bazy, ani orkiestracji. To była **najgroźniejsza z czterech pomyłek**,
   bo akurat ta reguła jest tu ważniejsza niż w CEIDG: faza 2 ma z założenia sięgać po treść, więc
   strukturalna granica jest tym, co czyni zakaz z sekcji 12 sprawdzalnym, zamiast deklarowanym.
2. **Konwencja nazw plików.** Dokument twierdził, że archiwum nie ma jednej konwencji, powołując
   przykład `2791_12.doc`. Listing pokazuje konwencję **spójną**, a ten przykład pochodzi z zupełnie
   innego miejsca — to wewnętrzna nazwa pliku Worda po stronie Izby, widoczna w treści dokumentu.
   Dwa schematy w dwóch warstwach zostały wzięte za jeden niekonsekwentny.
3. **Limit 30/min u pośrednika** — liczba, której w dokumentacji nie ma.
4. **Skład modeli w pracy o egzaminie KIO** — źródła podają różne pokolenia, a od tego zależy, czy
   wniosek brzmi „nawet czołowe modele nie dają rady", czy znacznie słabiej.

Trzy z tych czterech to ten sam kształt: **liczba albo nazwa przeniesiona przez jedno ogniwo
streszczenia za dużo.** Dokładnie to, przed czym ostrzega zasada 7.1 — i fakt, że przydarzyło się
to w dokumencie, który tę zasadę formułuje, jest najlepszym argumentem, żeby jej przestrzegać.

### 14.2 Jedno miejsce, w którym rekomendacja stoi na niepotwierdzonym

Rekomendacja z 13.1 mówi, żeby lata 2007–2018 wziąć z SAOS. **Żadnej liczby SAOS ten audyt nie
potwierdził własnym klientem** — próba weryfikacyjna dostała 403 na samym punkcie API, nie tylko
na stronach HTML. Jeśli pomiar 2 z sekcji 10 wypadnie negatywnie, **połowa rekomendowanej
architektury znika** i zostaje FTP (pomiar 1) albo pośrednik (pomiar 3). Kolejność pomiarów 1–3
jest z tego powodu nienegocjowalna: dopóki nie padną, `source/` nie ma czego implementować.
