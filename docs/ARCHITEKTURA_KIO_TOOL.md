# Narzędzie do orzecznictwa KIO: przegląd źródeł, przegląd istniejących narzędzi i propozycja architektury

Wersja: 2 (2026-09-14, drugi przebieg)
Status: proposed – do przyjęcia albo odrzucenia przez właściciela; sekcja 8 wylicza decyzje
Autor: P0w3r223
Podstawa: `AUDYT_KIO_ORZECZENIA.md` (2026-09-14), własny przegląd weryfikacyjny (2026-09-14, przebieg 1) oraz przegląd istniejących narzędzi i kolektorów (2026-09-14, przebieg 2)
Zakres żądań: wyłącznie pojedyncze odczyty diagnostyczne (sekcja 7); zero testów obciążeniowych, zero przebiegów masowych

---

## 0. Jak czytać ten dokument i co zmieniło się w wersji 2

Dokument robi trzy rzeczy i trzyma je osobno:

- **Sekcje 1–2**: przegląd weryfikacyjny audytu (bez zmian wobec wersji 1, poza dopisaniem dwóch wierszy do tabeli statusu).
- **Sekcja 3**: przegląd istniejących narzędzi, kolektorów i standardów, z odczytem 2026-09-14 i z rozstrzygnięciem „przejmujemy / nie przejmujemy / dlaczego". To jest nowa część.
- **Sekcje 4–6**: architektura i działanie, przepisane po lekturze wersji 1 i po przeglądzie narzędzi.

Kolejność, jeśli masz przeczytać tylko część: **0.1 → 3 → 4.4 → 6**.

### 0.1 Co poprawiono po ponownej lekturze wersji 1

Cztery usterki, każda w wersji 1 przeszłaby bramkę, bo nic jej nie sprawdzało:

1. **Model danych był sprzeczny.** `raw_documents` miał klucz główny `doc_id` i jednocześnie `UNIQUE (source, source_ref, content_sha256)`, czyli dopuszczał wiele wierszy na jeden klucz główny. Teraz są dwie tabele: `documents` (jeden wiersz na dokument) i `raw_versions` (jeden wiersz na wersję treści), a tabele pochodne są kluczowane parą `(doc_id, content_sha256)`, żeby wynik parsera był przypięty do wersji, z której powstał (4.4).
2. **To samo orzeczenie z dwóch kanałów nie miało jawnego powiązania.** `uzp:9620` i `atlas:kio-827-18` łączyły się tylko przez wspólną sygnaturę, co przy dokumentach wielosygnaturowych i sprostowaniach jest za słabe. Dochodzi tabela `equivalences`, zasilana przez `porownaj` (4.4).
3. **Niespójne nazwy modułów**: `sections.py` raz jako moduł luzem, raz jako `parser/sections.py`. Teraz `parser/` jest pakietem: `details.py`, `sections.py`, `clean.py`, `cite.py`.
4. **`sonda --kontrakt` było użyte w sekcji 4.4 wersji 1, a nieopisane w tabeli poleceń.** Poprawione (5.1).

### 0.2 Co dodał przegląd istniejących narzędzi

Siedem rzeczy, które wchodzą do architektury, każda z uzasadnieniem w sekcji 3:

- złote pliki parsera generowane przy pierwszym uruchomieniu i przeglądane przez człowieka (Juriscraper);
- kasety HTTP i blokada sieci w testach jako mechaniczny strażnik „zero żądań" (vcrpy / pytest-recording);
- niezależne potwierdzenie kontraktu wyszukiwarki UZP i górnej granicy identyfikatorów z cudzego kolektora, razem z listą rzeczy, których z niego nie wolno skopiować (Legal Data Hunter);
- SAOS przez Dump API z `sinceModificationDate`, nie przez API wyszukiwania (dokumentacja SAOS);
- graf cytowań między orzeczeniami jako tania warstwa fazy 2 (eyecite, LiDO, MateMatic);
- eksport Parquet z manifestem i warstwa modelowa jako osobny zbiór (JuDDGES);
- faza 4 jako lokalny serwer MCP nad korpusem zamiast asystenta wbudowanego w proces (kio-orzeczenia-mcp, rechtspraak-mcp, kontrakt cytowań MateMatic).

Konwencja zapisu bez zmian: liczba bez daty i sposobu uzyskania jest błędem. „Odczytane 2026-09-14" znaczy własny odczyt. „Z dokumentacji cudzej, data X" znaczy cudzy pomiar z podaną datą.

---

## 1. Co się zmieniło wobec audytu

### 1.1 Dwa ustalenia, które przestawiają projekt

**Kontrakt wyszukiwarki UZP jest odtworzony.** Audyt mówił (2.2): „kontrakt tego wywołania nie został odtworzony, nie wiadomo, skąd bierze się `total`". Dziś wiadomo, z dwóch niezależnych źródeł:

1. Własny odczyt (2026-09-14): `GET /Home/Move?Phrase=…&Pg=…&ind=N` **nie jest stroną wyników**. Jest przekierowaniem HTTP na `/Home/Details/{id}` dla N-tego wyniku zapytania. Parametr `total` jest w tym adresie dekoracyjny (linki „Pierwsze/Następne" na stronie go nie niosą). Strona `Details` ma ustrukturyzowaną metrykę: organ, rodzaj dokumentu, data wydania, przewodniczący, zamawiający, miejscowość, **lista** „Sygnatura akt / Sposób rozstrzygnięcia", tryb, rodzaj zamówienia, kluczowe przepisy Pzp (jako linki do wyszukiwania), zagadnienia z Indeksu tematycznego (jak wyżej). Linki niosą parametry `Fle=0` (fleksja) i `SCnt=0` (szukaj w treści).
2. Cudza dokumentacja: `matematicsolutions/kio-orzeczenia-mcp`, plik `DISCOVERY.md`, wersja v0.3.0, re-discovery **2026-07-31** (odczytany 2026-09-14). Wyszukiwanie idzie przez `POST /Home/GetResults` (form-urlencoded) z polami: `Phrase`, `Sign` (sygnatura), `Dt` (zakres dat `DD-MM-YYYY - DD-MM-YYYY`, oba końce wymagane), `ThIdx` (indeks tematyczny), `Art` (przepis Pzp, słownikowy, wrażliwy na format), `Fle`, `SCnt`, `Kind` (`KIO`/`SO`/`SA`/`SN`/puste), `Pg`, `Srt` (`rank`/`date_asc`/`date_desc`), `CountStats=True`. Odpowiedź to fragment HTML: `#resultCounts` z licznikami per organ, nagłówek „Liczba znalezionych dokumentów: N" i do 10 bloków `div.search-list-item`. Rozmiar strony jest stały. Są też słowniki: `/DictionaryPzpArticle/SearchArticle?query=`, `SearchIndex`, `/Dictionary/SearchCity`, `SearchPurchaser`, `SearchChairman`, oraz nieopisane `/AiSearch/*` (`GetQueryRelatedMetrics`, `RateMetric`).

Konsekwencje: pomiar 4 z listy audytu jest w większości wykonany (zostaje potwierdzenie `GetResults` własnym klientem, bo mój klient robi tylko GET). Pomiar 11 (co indeksuje „Hasło") ma odpowiedź strukturalną: `SCnt` przełącza wyszukiwanie w treści, `Fle` fleksję. Strategia „co nowego" ma nagle oparcie: `Dt` plus `Srt=date_desc`. Słowniki przepisów i haseł da się **wygenerować ze źródła** (mina 4), zamiast pisać ręcznie.

**UZP przebudował wyszukiwarkę w lipcu 2026 i przeniósł każdy punkt końcowy.** Z tego samego `DISCOVERY.md`: między 2026-05-20 a 2026-07-31 wyszukiwanie przeszło z `GET /?phrase=` na `POST /Home/GetResults`, treść z `/Home/HtmlContent/{id}` na `/Home/ContentHtml/{id}` (nazwa odwrócona), a stary scraper przez ~2 miesiące **zwracał `total=0` i pustą listę zamiast błędu**, bo `GET /Home/Search` nadal odpowiadał 200 ze szkieletem strony. Identyfikatory wewnętrzne przetrwały (`KIO 2924/21` to nadal `15903`).

Konsekwencje: adapter UZP jest z definicji kruchy i ma to mieć strukturalne zabezpieczenie, nie deklarację. Reguła 17 w sekcji 4.1. Cache po `internal_id` przeżyje kolejną przebudowę, cache po adresie nie.

### 1.2 Trzy korekty do audytu

**Korekta 1: podstawa prawna reguły 15 jest błędna.** Audyt (3.2, 8.3) mówi, że art. 15 ust. 1 pkt 4 ustawy o otwartych danych ustanawia „warunek domyślny: podanie źródła, czasu wytworzenia i pozyskania, a dla orzeczeń daty wydania, oznaczenia organu i sygnatury akt", i na tej podstawie nazywa regułę 15 „warunkiem ustawowym". Tekst jednolity ustawy (Dz.U. 2023 poz. 1524, odczytany 2026-09-14 z reprodukcji w BIP WSA w Warszawie; ISAP jest za captchą, jak zauważył audyt) mówi co innego:

- art. 15 ust. 1 pkt 4 dotyczy warunków dla „informacji sektora publicznego stanowiących lub zawierających dane osobowe"; obowiązek podania źródła i czasu to **pkt 1**;
- w ustawie **nie ma** żadnej formuły „data wydania, oznaczenie organu, sygnatura akt"; to standardowy warunek, który poszczególne sądy ustalają w swoich BIP-ach na podstawie art. 15 ust. 1 pkt 1, i przez jedno ogniwo streszczenia za dużo trafił do audytu jako przepis;
- art. 14 ust. 1: ISP udostępnia się „bezwarunkowo, z wyjątkiem przypadków określonych w ustawie"; art. 11 ust. 5: brak informacji o warunkach w BIP lub portalu danych oznacza udostępnianie bez warunków.

Reguła 15 **zostaje**, ale z inną etykietą: jest to decyzja projektowa (rzetelność cytowania, obowiązek atrybucji z CC BY 4.0 u pośrednika, ewentualnie CC BY-SA 4.0 z gov.pl, jeśli obejmuje `orzeczenia.uzp.gov.pl`), a nie warunek ustawowy. Test pilnujący reguły zostaje bez zmian.

Jest w tej samej ustawie przepis, którego audyt nie widział, a który ma znaczenie praktyczne: **art. 39 ust. 1 pkt 2**. Wniosek o ponowne wykorzystywanie wnosi się m.in., gdy ISP „są udostępniane w innym systemie teleinformatycznym niż [BIP lub portal danych] i nie zostały określone warunki ponownego wykorzystywania [...] albo nie poinformowano o braku takich warunków". `orzeczenia.uzp.gov.pl` jest takim „innym systemem", a audyt nie znalazł tam ani warunków, ani informacji o ich braku (3.5). Jeśli pomiar 14 z sekcji 6 potwierdzi brak, ustawa wskazuje wprost drogę: wniosek, w tym o dostęp „w sposób stały i bezpośredni w czasie rzeczywistym" (art. 39 ust. 2), rozpatrywany w 14 dni (art. 40 ust. 1), bezpłatnie (art. 17). To zamyka jednocześnie pytanie o bazy danych *sui generis* (3.4 audytu) i o tempo, bo w odpowiedzi UZP może określić warunki. Nie jestem prawnikiem; to jest odczyt przepisu, nie opinia, i wymaga potwierdzenia u prawnika, o którym audyt i tak mówi w 13.2 pkt 2.

**Korekta 2: limit 30/min u Atlasa istnieje.** Audyt w tabeli 14 uznał tę liczbę za „obaloną, nie znalezioną w dokumentacji". Dokumentacja Atlasu (odczytana 2026-09-14, „ostatnia aktualizacja: 10 września 2026") ma sekcję „Powierzchnia /api/llm dla agentów: trzy publiczne końcówki [...] bez klucza, limit 30 wywołań na minutę na adres IP". Historia zmian mówi, że opis `/api/llm` dodano 10 września, więc audyt czytał wcześniejszą wersję strony. Dla projektu to bez znaczenia (`/api/llm/*` nie obejmuje KIO), ale tabela statusu dowodowego ma wpis do poprawienia: **potwierdzone, nieistotne**.

**Korekta 3: tytuł komunikatu o FTP mówi o wyłączeniu serwera.** Audyt (2.1) stwierdza, że komunikat „nie mówi, że serwer wyłączono", i na tym opiera pomiar 1 jako potencjalnie najtańszą drogę do 18 lat materiału. Treść komunikatu rzeczywiście mówi tylko o zaprzestaniu publikacji, ale jego **tytuł** (odczytany 2026-09-14) brzmi: „Komunikat dotyczący wyłączenia serwera FTP z orzecznictwem KIO". Audyt oceniał zdanie, pominął nagłówek. Pomiar 1 nadal warto wykonać (kosztuje jedno żądanie), ale plan ma zakładać wynik negatywny, a nie liczyć na pozytywny.

### 1.3 Jeden spór rozstrzygnięty

Skład modeli w pracy arXiv:2511.04205 (audyt 4.3, „sporne"): abstrakt na arXiv i wersja opublikowana w *Artificial Intelligence and Law* (Springer, marzec 2026, DOI 10.1007/s10506-026-09505-w) podają **GPT-4.1, Claude 4 Sonnet i Bielik-11B-v2.6**. Wniosek audytu jest więc mocniejszy, nie słabszy: praca przeszła recenzję, a badane modele były aktualne na dzień badania. Granica dla fazy 2 („wspomaganie wyszukiwania i cytowania, nie ocena prawna") stoi na twardszym gruncie.

### 1.4 Ustalenia drobniejsze, które trafiają do kodu

Każde z odczytem 2026-09-14, chyba że zaznaczono inaczej.

- **Sufiks `VS` w nazwach plików FTP oznacza zdanie odrębne** (dawna strona `uzp.gov.pl/kio/orzecznictwo/wyroki`). Parser nazw plików ma to znać, jeśli FTP kiedykolwiek wróci; parser treści ma szukać sekcji „Zdanie odrębne".
- **Rodzaje rozstrzygnięć widziane w metryce**: `oddalone`, `zwrócone` (obok `uwzględnione`, `odrzucone`, `umorzone` znanych z Atlasu). Słownik ma być generowany z danych, nie z tej listy.
- **`Details` może mieć „Przewodniczący: Prezes Krajowej Izby Odwoławczej"** i „Tryb postępowania: brak danych" (sprawa `KIO 1963/25`, zwrócona). Pole przewodniczącego nie zawsze jest nazwiskiem.
- **`ContentHtml` niesie nagłówki**: `WYROK`, `orzeka:`, `Uzasadnienie`, `Izba ustaliła następujący stan faktyczny sprawy:`, `Izba zważyła, co następuje:`. Konwersja jest heurystyczna: w tym samym dokumencie `Protokolant:` i nazwisko protokolanta też były nagłówkami. Segmentację robić z HTML, nie z PDF (audyt 5.1 zakładał PDF), ale nagłówki traktować jako kandydatów, nie jako prawdę.
- **Do tekstu wycieka numer strony** (samotne `16` na końcu dokumentu) i **w źródle są błędy** (ten sam dokument ma „odwołanie wniesione 9 stycznia 2022 r." w nagłówku i „9 stycznia 2023 r." w uzasadnieniu). Parser nie poprawia źródła; zapisuje, co jest.
- **Anonimizacja potwierdzona na siódmym dokumencie** (`KIO 65/23`, 2023): „A. B. prowadząca działalność gospodarczą pod firmą [...] A. B.", skład pełnym nazwiskiem. Zgodne z 3.3 audytu.
- **Brakujące daty wydania to klasa, nie wyjątek**: `DISCOVERY.md` mówi o „sizeable share of older records" z `Data wydania: -`. Audyt widział jedną (`Details/1`). Pomiar 13 zostaje, ale pytanie brzmi już „ile", nie „czy".
- **SAOS reprezentuje dokument wielosygnaturowy jako jeden rekord** z tytułem „KIO 233/18, KIO 234/18" (strona `saos.org.pl/judgments/354301`, snippet). Atlas ma pole `primary_signature`. Oba pośredniki rozstrzygnęły minę 1 tak samo: dokument jest jednostką, sygnatury są listą.
- **Atlas dokłada „tezę wygenerowaną przez AI"** do stron orzeczeń i ma parametr `with_thesis`. To warstwa cudzego modelu w cudzym potoku; do korpusu nie wchodzi (reguła 19).
- **Atlas oferuje „feed dzienny, pełny zrzut zamiast paginacji"** po kontakcie mailowym; audyt tej opcji nie widział. Zmienia rachunek dla odcinka 2018–dziś.
- **Atlas: 29 tys. orzeczeń KIO wg stanu na 16.08.2026** (strona „O nas"); rocznik 2024 to **4 266** orzeczeń (strona `/kio/rocznik/2024`). Ta druga liczba jest podstawą tabeli kosztów w 5.3.
- **Adres w indeksie wyszukiwarki**: `Details/29368?Phrase=------&CountStats=False&Pg=1&total=29039&ind=28989`. Jeśli `Phrase=------` jest tym, co formularz wysyła przy pustej frazie, to `total=29039` byłby rozmiarem całego zbioru w dniu, w którym wyszukiwarka zaindeksowała ten adres (data nieznana). Nie sprawdzone własnym żądaniem. Trafia do pomiaru 16 (sekcja 6).
- **Pzp zmienione z dniem 13 marca 2026** w zakresie procedury odwoławczej (strona `gov.pl/web/uzp/krajowa-izba-odwolawcza`: „Stan prawny procedury odwoławczej przed zmianami Pzp – do 13 marca 2026 r."). Słownik przepisów w `/DictionaryPzpArticle` mógł się zmienić; to argument za generowaniem go ze źródła z sumą kontrolną, nigdy z pamięci.
- **Inspektor Ochrony Danych KIO**: `iod.kio@uzp.gov.pl` (strona kontaktowa UZP). Adresat pytania o klauzulę informacyjną dla stron, której audyt nie odnalazł (3.3 pkt 3).
- **SAOS blokuje mojego klienta** na każdym adresie API, także na przykładowym z własnej dokumentacji SAOS („bot detection"). Zgodne z 403 z audytu. Pomiar 2 otwarty; cudza notatka (`smithery.ai/skills/matematicsolutions/saos-orzecznictwo`) dodaje, że `pageSize` ma twardy dolny limit 10, `textContent` zawiera znaczniki HTML, a w datach są artefakty OCR (`3013`, `2101`).
- **SzuKIO nadal zwraca 429.** Cena roczna niepotwierdzona; snippet potwierdza tylko dostęp testowy 30 zł netto za 2 tygodnie.
- **Zbiór KIO w `dane.gov.pl`**: ponownie nie znaleziony. Znaleziono natomiast wpis Atlasu jako „showcase" (1 lipca 2026) powiązany ze zbiorem ogłoszeń BZP.

---

## 2. Status dowodowy po przeglądzie

Kolumna „audyt" to status z tabeli 14 audytu. Kolumna „przegląd" to mój odczyt 2026-09-14. Ostatnia kolumna mówi, czy wolno na tym budować.

| Twierdzenie | Audyt | Przegląd 2026-09-14 | Wynik |
|---|---|---|---|
| Zaprzestanie publikacji na FTP z 30.09.2025 | potwierdzone | komunikat gov.pl odczytany; treść zgodna | **potwierdzone** |
| Komunikat nie mówi o wyłączeniu serwera | potwierdzone | treść nie mówi; **tytuł mówi** | **poprawione** |
| Konwencja `RRRR_NNNN`, zera wiodące | poprawione | dawna strona UZP podaje przykład `2009_0001.pdf`; dodatkowo sufiks `VS` | **potwierdzone, uzupełnione** |
| FTP nie aktualizowane po sprostowaniu | – | dawna strona UZP mówi to wprost | **potwierdzone** |
| Punkty `Details`/`PdfContent`/`ContentHtml`/`PdfMetrics` z `Kind=KIO` | potwierdzone | trzy odczytane własnym klientem | **potwierdzone** |
| `Move` to strona wyników, kontrakt nieznany | – | `Move` to przekierowanie na `Details`; kontrakt w `DISCOVERY.md` 2026-07-31 | **nowe ustalenie** |
| UZP przeniósł punkty końcowe w lipcu 2026 | – | `DISCOVERY.md`, cudza obserwacja z datą | **z drugiej ręki, spójne z własnymi odczytami** |
| Data wydania bywa pusta | nowe ustalenie | `DISCOVERY.md`: „sizeable share" starszych rekordów | **potwierdzone jako klasa** |
| PDF przez `wkhtmltopdf`/Qt 4.8.7 | niepotwierdzone | `DISCOVERY.md` niezależnie: „Qt 4.8.7 from .docx" | **potwierdzone z drugiej ręki** |
| Anonimizacja: skład pełnym nazwiskiem, JDG inicjałami | potwierdzone | siódmy dokument (`KIO 65/23`) zgodny | **potwierdzone** |
| Atlas: 1500/dobę/IP, 5000/konto, 500/min | potwierdzone | dokumentacja z 10.09.2026 zgodna; dodatkowo `X-RateLimit-*`, `Retry-After`, do 3 kluczy na konto | **potwierdzone** |
| Atlas: `/api/llm/*` 30/min | **obalone** | sekcja istnieje w dokumentacji | **poprawione: potwierdzone, nieistotne dla KIO** |
| Atlas: CC BY 4.0, atrybucja, bez gwarancji kompletności | potwierdzone | zgodne; formuła atrybucji: „Źródło: Atlas Przetargów (https://atlasprzetargow.pl)" | **potwierdzone** |
| Atlas: `GET /api/kio`, `/api/kio/{slug}`, `/stats`, `/entities/{nip}/rulings`, `/tenders/{id}/rulings` | potwierdzone | zgodne; `per_page` ≤ 100, pola `primary_signature`, `has_more` | **potwierdzone, uzupełnione** |
| Atlas: dane „sparsowane z PDF" | potwierdzone | zgodne | **potwierdzone** |
| Atlas: feed dzienny na życzenie | – | dokumentacja, sekcja „Klucz i limity" i „Dobre praktyki" | **nowe ustalenie** |
| Atlas MCP: 7 narzędzi, bez KIO | potwierdzone | dziś 8 narzędzi, nadal żadnego dla KIO (wstęp deklaruje KIO, lista nie) | **potwierdzone z korektą liczby** |
| `kio-orzeczenia-mcp`: POC v0.1.0, Apache-2.0, 2 gwiazdki, 1 żąd./s, 10/stronę, TODO powiadomienia UZP | potwierdzone | GitHub API + README + CONSTITUTION odczytane; ostatni push 2026-08-24 | **potwierdzone** |
| arXiv 2511.04205: skład modeli | sporne | abstrakt arXiv i Springer: Claude 4 Sonnet | **rozstrzygnięte** |
| SAOS: 22 168 rekordów, 2007-12 → 2018-09 | niepotwierdzone | własny klient zablokowany na każdym adresie API; strony HTML z 2018 istnieją w indeksie | **nadal niepotwierdzone** |
| Ustawa: art. 6 ust. 2, art. 7 ust. 2 | do sprawdzenia | tekst jednolity odczytany, zgodne | **potwierdzone** |
| Ustawa: art. 15 ust. 1 pkt 4 jako warunek domyślny atrybucji | do sprawdzenia | pkt 4 dotyczy danych osobowych; formuły o sygnaturze nie ma; art. 14 ust. 1 mówi „bezwarunkowo" | **obalone** |
| SzuKIO: 2 530 zł/rok | niepotwierdzone | 429; snippet potwierdza tylko 30 zł/2 tyg. | **nadal niepotwierdzone** |
| Zbiór KIO w `dane.gov.pl` | negatywny z wyszukiwarki | ponownie negatywny; showcase Atlasu istnieje | **potwierdzone negatywne** |
| `POST /Home/GetResults` jako kontrakt listowania | – | dwa niezależne kolektory: Legal Data Hunter (uruchomiony 2026-04-18) i `kio-orzeczenia-mcp` (2026-07-31) używają tego samego wywołania z tymi samymi polami | **potwierdzone z dwóch niezależnych źródeł, nie własnym POST-em** |
| Jeden dokument nosi wiele sygnatur | z listingu FTP | dokumentacja SAOS mówi wprost: „orzeczenie czasem może dotyczyć wielu spraw (np. orzeczenia KIO)"; `Details` ma listę | **potwierdzone, także w dokumentacji urzędowej pośrednika** |

Podsumowanie: z 24 twierdzeń audytu sprawdziłem 20; **3 poprawione**, 1 rozstrzygnięte, 2 nadal niepotwierdzone (SAOS, SzuKIO), reszta stoi. Czterech nie sprawdzałem (Morfologik 85,7 %, PL-MTEB, „Elementy: 30 660" z listingu, liczby z repozytorium CEIDG); ich status z audytu obowiązuje. Do tego 4 ustalenia nowe z przebiegu 1 i kolejne z przeglądu narzędzi (sekcja 3). Rekomendacja 13.1 audytu (kanał hybrydowy) nadal stoi w połowie na SAOS, którego żaden klient poza pośrednikiem nie potwierdził.

---

## 3. Przegląd istniejących narzędzi: czego się uczymy, a czego nie kopiujemy

Cel tej sekcji jest praktyczny: sprawdzić, czy ktoś już rozwiązał któryś z problemów tego projektu, i jeśli tak, przejąć rozwiązanie zamiast wymyślać je od nowa. Każda pozycja ma odczyt z datą, jedno zdanie o tym, co narzędzie robi, listę rzeczy do przejęcia i listę rzeczy do odrzucenia z powodem. Kolejność po wadze dla projektu.

### 3.1 Legal Data Hunter: gotowy kolektor KIO, który potwierdza kontrakt i pokazuje pułapki

**Co to jest.** `worldwidelaw/legal-sources` (nazwa robocza: Legal Data Hunter), otwarte repozytorium kolektorów otwartych danych prawnych z 110+ krajów, ponad 960 kolektorów, licencja skryptów **AGPL-3.0**, licencje danych per źródło (z opisu w skillu `legal-data-hunter-pl` MateMatic, odczytanym 2026-09-14). Ma katalog `sources/PL/KIO/` z plikami `config.yaml`, `bootstrap.py`, `status.yaml`, `README.md` (odczytane 2026-09-14 z `raw.githubusercontent.com`; `retrieve.py` nie istnieje, 404).

**Co mówi o źródle, niezależnie od audytu i od `kio-orzeczenia-mcp`:**

- Strategia: „Sequential ID crawl: documents have IDs from 1 to ~33,400", `MAX_DOC_ID = 34000` z komentarzem „current max ~33,366"; „~31,700 KIO rulings + ~1,300 district court (SO) rulings"; typy: wyrok, postanowienie, uchwała. To jest **trzecia niezależna liczba wielkości zasobu** (obok 29 482 z Atlasu i 30 660 z listingu FTP) i pierwsza, która mówi, że KIO i SO **dzielą jedną numerację**, co domyka część pomiaru 6 z audytu. Data: kod bez daty w nagłówku, `status.yaml` ma `last_run: 2026-04-18`.
- Wywołania: `GET /Home/Details/{id}`, `GET /Home/ContentHtml/{id}?Kind=KIO&flection=0`, `POST /Home/GetResults` z polami `Phrase`, `Dt`, `Pg`, `Kind`, `Srt=date_desc`, `CountStats`, z nagłówkiem `X-Requested-With: XMLHttpRequest`. Identyfikatory wyników czyta regexem `/Home/Details/(\d+)`, następną stronę wykrywa po `data-page="N"` w HTML, liczniki po `id="resultCounts" value="ALL,KIO,SO"`. Kolektor działał na tym kontrakcie **w kwietniu 2026**, czyli przed lipcową „przebudową" z `DISCOVERY.md`. Wniosek: `GetResults` istniało wcześniej niż sądził autor `kio-orzeczenia-mcp`; to, co zniknęło w lipcu, to stara ścieżka `GET /?phrase=` i `HtmlContent`. Dwa niezależne kolektory zbiegły się na tym samym zestawie wywołań i to jest najlepsze potwierdzenie kontraktu, jakie da się mieć bez własnego POST-a.
- Metryka `Details`: struktura `<label>Etykieta</label><br/> wartość` w `<p>`, lista sygnatur w `<ul><li>KIO 2650/15 / oddalone</li></ul>`. Etykiety zgodne z moim odczytem (Organ wydający, Rodzaj dokumentu, Data wydania rozstrzygnięcia, Przewodniczący, Zamawiający, Miejscowość, Tryb postępowania, Rodzaj zamówienia).
- Tempo: `requests_per_second: 2`, `burst: 5`. Drugi precedens obok 1 żąd./s z `kio-orzeczenia-mcp`. Nadal żaden z nich nie jest pomiarem tolerancji serwisu.
- Zatrzymanie enumeracji po 100 kolejnych brakach. Sensowna heurystyka, ale niebezpieczna, jeśli w przestrzeni identyfikatorów są dziury dłuższe niż 100 (nieznane; pomiar 6).

**Co przejmujemy:**

- kształt `config.yaml` per źródło (adres, tempo, schemat, licencja) jako `source/uzp/contract.yaml`, wersjonowany z datą odczytu;
- `status.yaml` z historią uruchomień (`records_fetched`, `records_new`, `errors`) jako tabela `runs`;
- katalog `sample/` z kilkunastoma rekordami do walidacji jako `tests/examples/`.

**Czego nie kopiujemy, z powodem:**

- `User-Agent` udający Chrome na macOS. Łamie regułę 16 (nie podszywać się pod przeglądarkę) i, co ważniejsze, pozbawia UZP możliwości napisania do operatora, gdy coś pójdzie źle.
- `update_strategy: upsert`, `dedup_key: _id`. Nadpisuje, więc gubi sprostowania. My wersjonujemy (4.4).
- `case_number` z **pierwszego** elementu listy sygnatur. Dokładnie mina 1 audytu: dokument `KIO 233/18, KIO 234/18` traci drugą sprawę.
- Wpis `license: "Open Government Data"` z linkiem do `dane.gov.pl`. Nie ma pokrycia w źródle (pomiar 12 audytu i mój przegląd: zbioru KIO w `dane.gov.pl` nie ma).
- Sam kod, z powodu licencji. Skill MateMatic podaje AGPL-3.0 dla całego repozytorium, a opis `mcp-nsa` w katalogu glama.ai nazywa katalog `sources/PL/NSA` „MIT"; sprzeczność w cudzych źródłach, której tu nie rozstrzygam, bo kod i tak nie jest kopiowany. MateMatic w `mcp-nsa` opisał właściwą praktykę: „reproduces the query pattern and HTML parsing, does not import the source code". Tak samo tutaj: kontrakt tak, kod nie.

### 3.2 SAOS przez Dump API, nie przez wyszukiwarkę

**Co to jest.** Dokumentacja SAOS (`saos.org.pl/help`, snippety z wyszukiwarki 2026-09-14, bo strony pomocy blokują mojego klienta tak samo jak API) i wiki `CeON/saos` (odczytana 2026-09-14, ostatnia edycja 29.01.2015).

**Co mówi:**

- „API pobierania danych zawiera serwisy, które pozwalają na hurtowe ściąganie całej bazy orzeczeń SAOS [...] i synchronizować zgromadzone orzeczenia z jednym centralnym źródłem". Wyszukiwarka natomiast: „ten serwis nie służy do pobierania bazy orzeczeń (niepełne dane, brak łatwej synchronizacji)". Audyt i wersja 1 planowały SAOS przez `/api/search/judgments`, czyli dokładnie tym, czym dokumentacja każe nie pobierać.
- `GET /api/dump/judgments` z parametrami `pageSize`, `pageNumber`, zakresem dat orzeczenia i **`sinceModificationDate`** („Allows you to select judgments which were modified later than the specified dateTime"). Rekord niesie `courtCases[]`, `judgmentType` (DECISION / RESOLUTION / SENTENCE / REGULATION), `judges[]` z rolami, `source.judgmentUrl`, `textContent`, `legalBases`, `referencedRegulations`, `keywords`, `decision`, `summary`.
- Uwaga na wiki: nagłówek tabeli parametrów mówi `judgmentDateFrom/To`, a przykład w tej samej sekcji używa `judgmentStartDate/EndDate`. Dokumentacja jest wewnętrznie sprzeczna i tylko własne wywołanie rozstrzygnie, która nazwa działa.
- W dokumentacji `api/judgments/{id}`: „Orzeczenie czasem może dotyczyć wielu spraw (np. orzeczenia KIO)". Urzędowa dokumentacja pośrednika potwierdza minę 1 wprost.
- Wiki z 2015 zna tylko `courtType` COMMON / SUPREME / ADMINISTRATIVE; nowsza pomoc dodaje CONSTITUTIONAL_TRIBUNAL i NATIONAL_APPEAL_CHAMBER. Czy Dump API filtruje po `courtType`, wiki nie mówi. Jeśli nie, pobranie KIO za 2007–2018 oznacza zrzut wszystkich sądów z tych lat i filtr po stronie klienta, co jest inną skalą.

**Co przejmujemy:** adapter `source/saos.py` używa Dump API; pomiar 2 dzieli się na 2a (czy Dump API odpowiada własnemu klientowi) i 2b (czy ma filtr `courtType`). Wzorzec `sinceModificationDate` trafia jako konkretny postulat do wniosku do UZP (sekcja 8, decyzja 2): źródło, które samo mówi, co się zmieniło, rozwiązuje problem z 4.6 lepiej niż trzy osie.

**Czego nie przejmujemy:** niczego z API wyszukiwania SAOS do pobierania. Zostaje ono ewentualnie dla `porownaj` po sygnaturze (`caseNumber=`).

### 3.3 Juriscraper (Free Law Project): złote pliki, które generuje się raz i przegląda

**Co to jest.** Biblioteka scraperów sądów amerykańskich, podstawa CourtListener (`freelawproject/juriscraper`, `CONTRIBUTING.md` odczytany 2026-09-14; 618 gwiazdek, 162 forki wg strony).

**Co robi lepiej niż wersja 1 tego dokumentu:**

- Każdy scraper ma plik `*_example*` (surowy HTML zapisany z przeglądarki) i `*_example*.compare.json`, **generowany automatycznie przy pierwszym uruchomieniu testów**, przeglądany przez człowieka, potem zamrażany: „Run the test suite once, it will generate the .compare.json. Review that data in .compare.json is correct. Re-run tests. If all pass, include both files in your PR." Wersja 1 mówiła o „zamrożonym HTML" i „asercji niezerowego total", ale nie mówiła, skąd bierze się oczekiwany wynik parsera. Odpowiedź Juriscrapera: z pierwszego przebiegu, potwierdzonego okiem. To domyka zasadę 7.4 audytu (sanityzuj dowód z tego, co ważne): człowiek patrzy na `compare.json`, nie na kod parsera.
- „Two-part system": biblioteka parsuje, kod wywołujący pobiera i zapisuje; „no need for a database" po stronie biblioteki. To jest dokładnie granica `parser/` (czysty) wobec `source/` i `store.py` z reguł 1–5 audytu, tylko sprawdzona na dziesiątkach milionów rekordów.
- Osobne „backscrapers" do historii i scrapery bieżące. U nas: `pobierz` (zakres) i `aktualizuj` (okno) jako dwie ścieżki, nie jedna z flagą.
- Cel projektowy wypisany wprost: „friendly as possible to court websites".

**Co przejmujemy:** `tests/examples/uzp/{details,content,getresults}/*.html` z `*.compare.json` generowanym przy pierwszym uruchomieniu i przeglądanym przed commitem; ta sama para dla SAOS (JSON) i Atlasu (JSON). Reguła 17 z wersji 1 dostaje przez to mechanikę.

**Czego nie przejmujemy:** XPath/lxml jako jedynego narzędzia (u nas `Details` jest tabelaryczne, `ContentHtml` nagłówkowe; `selectolax` albo `lxml`, do wyboru po fixture), i Selenium (nie ma potrzeby, wyszukiwarka odpowiada bez JS, gdy woła się `GetResults`).

### 3.4 vcrpy i pytest-recording: blokada sieci jako test, nie obietnica

**Co to jest.** VCR.py nagrywa interakcje HTTP do „kaset" (YAML) i odtwarza je w testach; obsługuje `httpx` (przykład z `alexwlchan.net`, 2025, odczytany 2026-09-14). `pytest-recording` (kiwicom) dodaje `@pytest.mark.vcr`, tryby nagrywania (`once`, `rewrite`, `none`, `new_episodes`) i **`--block-network`** z listą dozwolonych hostów.

**Dlaczego to ważne tutaj.** Bramka fazy 2 audytu brzmi „przeliczenie całego korpusu bez ani jednego żądania sieciowego", tryb pokazowy ma być „bez sieci", a zasada 7.3 pyta: co by się wypisało, gdyby gwarancja została naruszona? Bez blokady sieci odpowiedź brzmi „nic". Z `--block-network` w konfiguracji pytest odpowiedź brzmi „test czerwony".

**Co przejmujemy:**

- `pytest --block-network` jako domyślna konfiguracja; jedyny wyjątek to `-m smoke`, uruchamiany ręcznie, po zgodzie;
- kasety dla adapterów jako drugi rodzaj złotego pliku obok `*_example*`: `*_example*` testuje parser, kaseta testuje adapter razem z warstwą HTTP (przekierowanie `Move` → `Details`, nagłówki, kody);
- nagrywanie tylko w trybie `once`, nigdy `all`, a ponowne nagranie jest osobnym commitem z opisem „kontrakt UZP zmieniony {data}".

**Zastrzeżenie.** `httpclient.py` z CEIDG wstrzykuje transport `httpx` i wyłącza `trust_env`; VCR podpina się na innym poziomie. Trzeba sprawdzić w pierwszym teście, czy oba mechanizmy się nie gryzą; jeśli tak, `respx` (mock na poziomie transportu `httpx`) robi to samo bliżej reguły 11.

### 3.5 eyecite, LiDO i ekstraktor MateMatic: graf cytowań jako tania warstwa

**Co to jest.**

- `eyecite` (Free Law Project, JOSS 2021; README odczytany 2026-09-14): wyciąga cytowania z tekstu prawniczego, przetestowany na ponad 50 mln cytowań; potok **clean → extract → resolve → annotate**, gdzie `resolve` łączy cytowania pełne, skrócone, „supra" i „id." w jeden zasób, a `annotate` wstawia znaczniki z powrotem w tekst po offsetach (diff-match-patch).
- LiDO (Holandia): graf cytowań między orzeczeniami i przepisami, używany przez `rechtspraak-mcp` do „co cytuje, co jest cytowane, odwołania do ustaw" (opis z katalogu glama.ai, 2026-09-14).
- MateMatic: skill „deterministyczny ekstraktor cytatów prawnych z polskiego pisma: sygnatury sądów, ECLI, identyfikatory Dz.U./M.P./ELI, powołane przepisy; normalizuje, deduplikuje i rozwiązuje odwołania skrótowe (tamże, op. cit., wyżej)" (katalog skillsmp.com, 2026-09-14). Polski odpowiednik `eyecite`, w formie instrukcji dla modelu, nie biblioteki.
- Atlas pokazuje na stronie orzeczenia „Powiązania z innymi wyrokami KIO: cytowane precedensy oraz orzeczenia, które się do tego wyroku odwołują" (strona `kio-2363-24`, 2026-09-14); SzuKIO reklamuje „funkcjonalność identyfikującą zmienione wyroki Izby w trybie skargi do sądu" (strona oferty, snippet 2026-09-14).

**Dlaczego to ważne tutaj.** W dokumencie `KIO 65/23` uzasadnienie cytuje `KIO 835/22`, `KIO 113/22`, `KIO 115/22`, `KIO 178/15`, `KIO 520/21`, `KIO 293/21` w jednolitym wzorcu „(tak: wyrok z dnia 27 stycznia 2022 r., KIO 113/22)". Orzeczenia SO (`Kind=SO`) cytują sygnatury KIO, od których wniesiono skargę. Wyciągnięcie tego regexem opartym na tym samym normalizatorze co `docid.py` daje trzy rzeczy naraz: graf cytowań (kto na kogo się powołuje), relację KIO → SO (czy orzeczenie zostało zaskarżone i z jakim skutkiem, to jest cecha SzuKIO) oraz **test normalizatora sygnatur na dziesiątkach tysięcy wystąpień z prawdziwego tekstu**, czego pomiar 17 z wersji 1 nie dawał.

**Co przejmujemy:** `parser/cite.py` (czysty), tabela `citations`, potok jak w `eyecite` z jedną różnicą: `resolve` łączy do `document_cases`, nie do zewnętrznej bazy. Wchodzi do fazy 2, nie fazy 4, bo nie potrzebuje modelu.

**Czego nie przejmujemy:** samego `eyecite` (baza `reporters-db` jest amerykańska; wzorzec tak, kod nie) ani skillu MateMatic (jest instrukcją dla modelu; u nas ma być kod z testem, zasada 7.1: sygnatury nie pochodzą z pamięci modelu).

### 3.6 JuDDGES: eksport, warstwa modelowa osobno, graf orzeczenie–przepis

**Co to jest.** `pwr-ai/JuDDGES` (Politechnika Wrocławska, Middlesex, Lyon; README odczytany 2026-09-14; Apache-2.0 kod, CC BY 4.0 zbiory, DOI Zenodo). Zbiory na Hugging Face: `pl-court-raw` (437 450 orzeczeń z `orzeczenia.ms.gov.pl` wg karty `pl-appealcourt-criminal`), `pl-court-raw-enriched` (pola wyciągnięte modelem Gemini 2.5 Pro, **jako osobny zbiór**), `pl-court-graph` (dwudzielny graf orzeczenie ↔ podstawa prawna, z osadzeniami `sdadas/mmlw-roberta-large`). Aplikacja `juddges-app`: Supabase pgvector + Meilisearch, wyszukiwanie hybrydowe. Repozytorium używa DVC do wersjonowania danych, Prefect do orkiestracji, Label Studio z schematami Pydantic do anotacji z człowiekiem w pętli. KIO nadal nieobecne, zgodnie z 4.3 audytu.

**Co robi lepiej:**

- **Warstwa modelowa jako osobny zbiór z własną nazwą** (`-enriched`). To jest reguła 19 z wersji 1 zrealizowana na poziomie publikacji, a nie tylko schematu: nikt nie pomyli treści orzeczenia z tym, co wyciągnął model.
- **Parquet jako format wymiany** i DOI dla korpusu. Arkusz z wersji 1 jest dla operatora; Parquet jest dla każdego, kto chce policzyć coś na całości bez otwierania SQLite. Atlas robi to samo (Parquet + CSV, Zenodo, Kaggle, CC BY 4.0; strona `/dane`, 2026-09-14).
- **Graf orzeczenie ↔ przepis** jako produkt sam w sobie. U nas `provisions` z `Details` daje to za darmo, bo UZP już przypisał przepisy.
- Anotacja HITL ze schematem Pydantic: model proponuje, człowiek poprawia, wynik jest zbiorem z `schema.yaml`. To jest wzorzec dla **raportu pokrycia parsera** z bramki fazy 2: próbka 50 dokumentów z ręcznie potwierdzonymi granicami sekcji jako złoty zbiór, na którym mierzy się parser.

**Co przejmujemy:** eksport Parquet z manifestem (`manifest.json`: liczba dokumentów, zakres dat, `parse_version`, SHA-256 każdego pliku, blok atrybucji); złoty zbiór 50 dokumentów dla parsera w `tests/gold/`; nazewnictwo `*-derived` dla każdego zbioru pochodzącego od modelu.

**Czego nie przejmujemy teraz:** DVC, Prefect, Supabase, Weaviate, vLLM. To jest infrastruktura projektu badawczego z GPU; dla jednego operatora i 30 tys. dokumentów SQLite z FTS5 wystarcza, a migracja jest decyzją po pomiarze (4.8).

### 3.7 Rechtspraak i ECLI: dwa kroki, data modyfikacji, trwały identyfikator

**Co to jest.** Otwarte dane holenderskiego sądownictwa (opis na `data.overheid.nl`, 2026-09-14): „bevragen van de ECLI-index is gescheiden van het opvragen van uitspraakdocumenten": najpierw zapytanie do indeksu metadanych po kryteriach, wynik to lista ECLI, potem pobranie dokumentów po ECLI. Ponad 800 000 pełnych dokumentów, 3 miliony rekordów samych metadanych. Narzędzia wokół (monitor na Apify, `rechtspraak-mcp`) opierają aktualizację na dacie modyfikacji („only returns rulings modified since the previous run"), a cytowania na trwałych linkach ECLI z zakotwiczeniem cytowanego fragmentu w adresie.

**Co przejmujemy:** rozdział `list_candidates` / `fetch` z wersji 1 jest już tym wzorcem; dochodzi **trwały link cytowania**: każdy eksport i każdy wynik fazy 4 niesie adres `Details/{id}` plus `content_sha256` wersji plus dokładny cytat, tak żeby odbiorca mógł sprawdzić fragment przy źródle. ECLI dla KIO nie istnieje (nie sprawdzałem urzędowo; nie znalazłem żadnego przykładu `ECLI:PL:KIO`), więc rolę trwałego identyfikatora sprawy gra znormalizowana sygnatura z `docid.py`, a dokumentu para `(source, source_ref)`.

**Czego nie przejmujemy:** RDF/Dublin Core jako formatu metadanych. Autor `rechtspraak-js` opisuje dwie kolidujące właściwości `dcterms:modified` i nietypowane wartości; XML/RDF nie daje tu nic, czego nie da SQLite z jawnym schematem.

### 3.8 Serwery MCP nad orzecznictwem: faza 4 jako serwer, nie asystent w procesie

**Co to jest.** Cztery precedensy odczytane 2026-09-14: `kio-orzeczenia-mcp` (UZP, POC), `mcp-saos` i `saos-mcp` (SAOS), `rechtspraak-mcp` (Holandia), `mcp-nsa` (CBOSA). MateMatic utrzymuje pięć serwerów ze wspólnym kontraktem `structuredContent.citations = [{title, url, snippet?, ...}]`, „żeby agenci prawni mogli je renderować bezpośrednio w panelu cytowań" (`mcp-isap`, README).

**Dlaczego to zmienia fazę 4.** Audyt i wersja 1 zakładały `assistant/` wewnątrz pakietu, z regułą 13 pilnującą, żeby nie importował `source`, `store` ani `pipeline`. Serwer MCP realizuje tę granicę **na poziomie procesu**: korpus jest po jednej stronie gniazda, model po drugiej, a jedyne, co przechodzi, to wywołania narzędzi i ich wyniki. Trzy skutki:

1. Reguła 13 przestaje być regułą importów, a staje się topologią: nie ma procesu, w którym model i baza żyją razem.
2. ADR z sekcji 12 audytu („czy treść orzeczenia wolno wysłać do modelu") dostaje mechanizm egzekucji: narzędzie `get_ruling` zwraca treść albo tylko metadane i cytat, zależnie od decyzji, i to jest jedna linia konfiguracji, a nie audyt promptów.
3. Właściciel dostaje fazę 2 produktu bez pisania własnego czatu: każdy klient MCP (Claude Desktop, Claude Code, inne) pyta korpus w języku naturalnym. Praca z 4.3 audytu (egzamin KIO) nadal ogranicza, co model może z tego zrobić; serwer nie zmienia tej granicy, tylko ją czyni widoczną.

**Co przejmujemy:** `kio-tool serve-mcp` jako postać fazy 4; narzędzia `search_rulings`, `get_ruling` (z przełącznikiem treść / metadane), `get_citations` (graf z 3.5), `cite` (blok atrybucji z 4.9); kontrakt wyników zgodny z `structuredContent.citations`, żeby klienci już to rozumieli; dziennik wywołań jak `CONSTITUTION.md` art. 3 z `kio-orzeczenia-mcp` (skrót parametrów, nie treść).

**Czego nie przejmujemy:** hostowania korpusu w chmurze (skill MateMatic mówi to samo o własnym hostowanym API: „zależność chmurowa sprzeczna z tezą zero-cloud"; u nas dochodzi RODO z 3.3 audytu) i limitu 2 000 znaków treści z `mcp-nsa` jako reguły; u nas ilość treści jest decyzją ADR, nie stałą.

### 3.9 WARC i warcio: surowiec w formacie archiwalnym, na życzenie

**Co to jest.** WARC 1.0/1.1 (ISO) to format archiwów WWW; `webrecorder/warcio` (Apache-2.0, README odczytany 2026-09-14) zapisuje żądanie i odpowiedź razem, liczy skróty bloku i ładunku automatycznie, a `pywb` odtwarza takie archiwum jak Wayback Machine.

**Co przejmujemy:** `eksportuj --warc` jako czwarty format eksportu: surowe bajty z `raw_versions` razem z nagłówkami HTTP z `fetch_meta` zapisane jako rekordy `response` (i `request`, jeśli zachowane). Powód: SQLite jest formatem tego narzędzia, WARC jest formatem, który za dziesięć lat przeczyta każde archiwum. Koszt: kilkadziesiąt linii.

**Czego nie przejmujemy:** WARC jako **głównego** magazynu zamiast SQLite. Dzierżawa blokady, wznawianie i zapytania po sygnaturze potrzebują bazy; dwa źródła prawdy to prośba o rozjazd.

### 3.10 Atlas Przetargów i SzuKIO: co pośrednicy pokazują, a czego nie

Bez zmian wobec sekcji 1 i 2, z jednym dopiskiem po przeglądzie: Atlas dokumentuje **dobre praktyki dla klientów** („synchronizuj przyrostowo `sort=newest` z `dateFrom`", „przy 429 odczekaj tyle, ile mówi `Retry-After`", „podaj własny `User-Agent` z kontaktem", „cache'uj orzeczenia lokalnie; zmieniają się rzadko"). Te cztery zdania są kontraktem grzeczności, który adapter Atlasu ma spełniać dosłownie, a adapter UZP, przy braku własnej dokumentacji UZP, ma spełniać przez analogię.

### 3.11 Tabela: co skąd wchodzi

| Rzecz | Skąd | Gdzie w architekturze |
|---|---|---|
| Kontrakt `GetResults` potwierdzony drugim kolektorem; granica id ~33,4 tys.; KIO i SO w jednej numeracji | Legal Data Hunter | 4.3, 6 (pomiar 6) |
| `contract.yaml` per źródło, `runs` z historią, `tests/examples/` | Legal Data Hunter | 4.2, 4.4 |
| Złote pliki `*_example*` + `*.compare.json` generowane raz, przeglądane | Juriscraper | 4.1 reguła 17, 4.5 |
| Biblioteka parsuje, wywołujący pobiera; backscraper osobno | Juriscraper | 4.2, 5.1 |
| Kasety HTTP, `--block-network` | vcrpy, pytest-recording | 4.1 reguła 20 |
| SAOS przez Dump API, `sinceModificationDate` | dokumentacja SAOS, wiki CeON | 4.3, 6 (pomiar 2a/2b), 8 (decyzja 2) |
| `courtCases[]` w dokumentacji urzędowej pośrednika | dokumentacja SAOS | 4.4 (ADR-001) |
| Graf cytowań: clean → extract → resolve → annotate | eyecite, LiDO, MateMatic | 4.5 (`parser/cite.py`), 4.4 (`citations`) |
| Warstwa modelowa jako osobny zbiór; Parquet z manifestem; złoty zbiór HITL | JuDDGES, Atlas | 4.1 reguła 19, 4.9, 4.5 |
| Dwa kroki (indeks → dokument); trwały link z cytatem | Rechtspraak | 4.3, 4.9 |
| Faza 4 jako serwer MCP; kontrakt `citations`; dziennik wywołań | kio-orzeczenia-mcp, rechtspraak-mcp, MateMatic | 4.10, 8 (decyzja 3) |
| Eksport WARC | warcio | 4.9 |
| Kontrakt grzeczności klienta | Atlas | 4.7 |

---

## 4. Architektura

### 4.1 Reguły, które obowiązują od pierwszego commita

Reguły 1–16 z sekcji 8.3 audytu przenoszą się w całości, z jedną zmianą etykiety (reguła 15, sekcja 1.2). Wersja 1 dodała trzy (17–19), przegląd narzędzi dokłada jedną (20) i doprecyzowuje dwie.

17. **Każdy kanał ma kontrakt, złote pliki i test dymny.** (Brzmienie z ADR-0003, przyjęte 2026-09-15. Poprzednia wersja była regułą o UZP, choć kanał nie jest wybrany, i mówiła „200", choć kanał plikowy nie ma statusu HTTP.) Kanał jest pakietem `source/<nazwa>/` i zawiera `channel.py` (implementacja `Channel`), `contract.yaml` (adres bazowy, nazwy punktów końcowych i pól, tempo, rozmiar strony, licencja, data odczytu) oraz, jeśli trzeba, moduły pomocnicze. `contract.yaml` jest jedynym miejscem, z którego `channel.py` bierze adresy i nazwy pól — pilnuje tego reguła 22. `tests/examples/<nazwa>/` zawiera surowe odpowiedzi z datą pobrania w nazwie, a obok każdej `*.compare.json` wygenerowany przy pierwszym uruchomieniu i przejrzany przez człowieka przed commitem (wzorzec Juriscrapera, 3.3). Adapter, który dostanie odpowiedź o statusie zgodnym z kontraktem, ale o kształcie niezgodnym, **rzuca `SourceContractBroken`**, nie zwraca pustej listy. Dla UZP kształtem jest obecność `div.search-list-item` i `#resultCounts`; powód jest datowany: między majem a lipcem 2026 UZP przeniósł każdy punkt końcowy, a cudzy scraper przez około dwa miesiące zwracał `total=0` ze statusem 200 zamiast błędu.
18. **Metadane pochodzą z `Details/{id}`, treść z `ContentHtml/{id}`, oba jako bajty.** Bez zmian wobec wersji 1. PDF tylko na jawne życzenie operatora.
19. **Każdy rekord niesie pochodzenie; treść pochodząca od modelu nie wchodzi do korpusu i nie dzieli z nim nazwy.** Doprecyzowanie po JuDDGES (3.6): każdy zbiór pochodzący od modelu ma sufiks `-derived` i własny manifest z nazwą modelu i `prompt_sha256`. Adapter Atlasu odrzuca pola `thesis*` na wejściu.
20. **Nowa: sieć w testach jest zablokowana, a wyjątek jest jawny.** `pytest` uruchamia się z `--block-network`; jedyny wyjątek to marker `smoke`, uruchamiany ręcznie po zgodzie właściciela. Bramka „zero żądań" (faza 2, `przelicz`, `demo`) jest przez to testowana, a nie deklarowana (zasada 7.3 audytu: gwarancja bez obserwatora nie jest gwarancją). Mechanika rozstrzygnięta pomiarem 21 (zmierzone 2026-09-15, 0 żądań, `docs/decisions.md`): `--block-network` z `pytest-recording` jest zamkiem **na gnieździe**, nie na transporcie `httpx`, więc reguła pokrywa także kanał spoza HTTP — niezależnie od tego, który kanał wygra po pomiarach 1–3. **Blokada i kasety to dwie osobne gwarancje** i to rozróżnienie jest częścią reguły, nie komentarzem do niej: zamknięta jest blokada, otwarte zostaje odtwarzanie kaset przez wstrzyknięty transport z `httpclient.py`, które rozstrzygnie pomiar 4b. Do tego czasu `respx` zostaje w zależnościach deweloperskich jako druga droga do kaset.

21. **Nowa (ADR-0003): kanał jest pakietem; w `source/` nie leży moduł kanału luzem.** Bezpośrednio w `source/` wolno leżeć wyłącznie modułom wspólnym z wyliczonej listy: `__init__.py` (re-eksport), `protocol.py` (`Channel`, `Candidate`, `RawDocument`, `Capabilities`, `Scope`), `contract.py` (wczytanie `contract.yaml`) i `registry.py` (`REGISTRY: dict[SourceName, type[Channel]]`, importy statyczne). Każdy inny wpis w `source/` jest katalogiem zawierającym `__init__.py`, `channel.py` i `contract.yaml`. Nazwa katalogu jest nazwą kanału: tym samym napisem, który idzie do `docid.document_id` jako `source`, do kolumny `documents.source` i do przedrostka `doc_id`. Skan sprawdza równość trzech zbiorów — katalogi z `channel.py`, katalogi z `contract.yaml`, klucze `REGISTRY` — więc nie przechodzi ani kanał bez kontraktu, ani kontrakt-sierota, ani kanał niewidoczny dla kreatora. `SourceName` zostaje `NewType`, a nie `Literal`: roster kanałów nie jest znany przed bramką fazy 0, a `REGISTRY` jest jedynym miejscem, które go wymienia. Przy pustym `source/` wszystkie trzy zbiory są puste i reguła przechodzi zgodnie ze stanem projektu; ciężar dowodu niosą wtedy samosprawdzenia skanu na plikach podrzuconych w `tmp_path`.

22. **Nowa (ADR-0003): adres i nazwa pola nie występują jako literał w kodzie kanału.** Skan AST odrzuca w `source/**/*.py` każdy napis pasujący do `^[a-z][a-z0-9+.-]*://` albo `^/[A-Za-z]`, z wyjątkiem napisów dokumentacyjnych (docstring modułu, klasy i funkcji). To jest mechaniczna postać zdania z reguły 17 „`contract.yaml` jest jedynym miejscem, z którego adapter bierze adresy i nazwy pól"; bez niej to zdanie jest życzeniem, a po przebudowie wyszukiwarki UZP z lipca 2026 jest to życzenie kosztowne. Lekarstwem na czerwony test jest przeniesienie napisu do `contract.yaml`, nigdy dopisanie wyjątku — lista wyjątków jest miejscem, w którym reguła cicho przestaje obowiązywać.

Doktryna z sekcji 7 audytu obowiązuje bez zmian. Reguła zgody: każdy przebieg masowy i pomiar 9 wymagają zgody w bieżącej sesji; pojedynczy odczyt diagnostyczny bez zgody, zawsze z wpisem w dzienniku (13.2 pkt 4 audytu).

### 4.2 Moduły

Strzałki to importy. Reguły granic pilnuje `tests/test_boundaries.py` skanem AST.

```
wejścia:  cli.py (typer)   ui/wizard.py (questionary)   faza 4: mcp_server.py (osobny proces)
             \                    |                              |
              └────── ui/flow.py: jedna sekwencja decyzji ───────┘   (mcp_server widzi tylko store i exporter,
                                  |                                   nigdy source ani pipeline)
                                  v
                          criteria.py          CZYSTY: pydantic, bez I/O; jedyny kontrakt wejścia
                                  |
                                  v
                          pipeline.py          orkiestracja; JEDYNY moduł widzący jednocześnie source/ i store.py
                 ┌──────────┬──────────┼──────────┬──────────┐
                 v          v          v          v          v
              source/          store.py   parser/       docid.py   exporter.py
              ├ protocol.py    (SQLite,   ├ details.py  (CZYSTY)  (xlsx, md, parquet, warc)
              ├ contract.py     wersje,   ├ sections.py
              ├ registry.py     dzierżawa)├ clean.py
              └ <kanal>/                  └ cite.py  ──► docid.py
                  ├ channel.py
                  └ contract.yaml
                 |
                 v  (kanały HTTP — i tylko one)
           httpclient.py ─► ratelimit.py ─► clock.py

poprzecznie: progress.py (Events), richtext.py + safetext.py, ui/texts.py + ui/render.py,
             console.py, logbook.py (dziennik), dictionaries.py (CZYSTY, słowniki z SHA-256 źródła)

zamrożone dowody: tests/examples/{uzp,atlas,saos}/ (*_example* + *.compare.json),
                  tests/cassettes/ (kasety HTTP), tests/gold/ (50 dokumentów z potwierdzonymi sekcjami)
```

Strzałka do `httpclient.py` wychodzi z kanałów HTTP i **tylko z nich** (ADR-0003, rozstrzygnięcie 2). Kanał spoza HTTP dostaje własnego właściciela protokołu obok `httpclient.py`, wołającego tę samą, jedyną kopię reguły „dokąd wolno wyjść" — nigdy przez `httpx`, który protokołu FTP nie obsługuje, a którego polityka wyjścia odmawia wszystkiemu poza `https`. Dopóki takiego właściciela nie ma, tablica `EGRESS_OWNERS` w `tests/test_boundaries.py` zabrania budowania `ftplib.FTP` gdziekolwiek w drzewie.

Co przychodzi z `ceidg-tool` bez zmian poza nazwami: `ratelimit.py`, `httpclient.py`, `clock.py`, `progress.py`, `richtext.py`, `safetext.py`, `ui/texts.py`, `ui/render.py`, `console.py`, wzorzec `store.py`, `tests/test_boundaries.py`. Co jest nowe: pakiet `source/` za jednym protokołem, pakiet `parser/`, `docid.py`, `dictionaries.py`, `logbook.py`, `mcp_server.py` (faza 4). Co nie przychodzi: `apiprofile.py`, `pkdmap.py`, `recordid.py`, `batching.py` (uzasadnienie w sekcji 6 audytu).

### 4.3 Kanał za jednym interfejsem

Dwie operacje o różnym koszcie, bo w każdym kanale listowanie jest tanie, a pobranie drogie (wzorzec dwóch kroków z Rechtspraak, 3.7; podział „biblioteka / wywołujący" z Juriscrapera, 3.3):

```python
class Channel(Protocol):
    name: SourceName  # "uzp" | "atlas" | "saos" | "ftp"

    def list_candidates(self, scope: Scope) -> Iterator[Candidate]:
        """Tanie, stronicowane. Minimum do decyzji, czy pobierać: source_ref,
        sygnatury (lista), data wydania (może być None), rodzaj dokumentu,
        i, jeśli kanał to ma, data modyfikacji. Jedno żądanie na stronę."""

    def fetch(self, ref: SourceRef) -> RawDocument:
        """Drogie. Bajty tak, jak przyszły, plus nagłówki i moment pobrania.
        Nie parsuje. 1–3 żądania."""

    def capabilities(self) -> Capabilities:
        """Filtr po dacie / sygnaturze / przepisie, sortowanie, rozmiar strony,
        znany limit tempa, czy ma datę modyfikacji. Kreator liczy z tego koszt."""
```

| Adapter | `list_candidates` | `fetch` | Tempo i granice | Stan |
|---|---|---|---|---|
| `source/uzp/` | `POST /Home/GetResults` z `Kind=KIO`, `Dt=od - do`, `Srt=date_asc` (pobierz) lub `date_desc` (aktualizuj), `Pg=1..n`, `CountStats=True`, nagłówek `X-Requested-With: XMLHttpRequest`; 10 na stronę; koniec po braku `data-page="n+1"` | `GET /Home/Details/{id}` + `GET /Home/ContentHtml/{id}?Kind=KIO&flection=0`; `PdfContent` na życzenie | Start 1 żąd./s (precedensy: 1/s i 2/s z dwóch kolektorów, żaden nie jest pomiarem), do 2 po pomiarze 9; `User-Agent` z kontaktem; stop przy 403 / 429 / CAPTCHA / `SourceContractBroken` | do zbudowania po 4b i 9 |
| `source/atlas/` | `GET /api/kio?date_from&date_to&sort=oldest&per_page=100&page=n` | `GET /api/kio/{slug}`; pola `thesis*` odrzucane | `X-Api-Key`; nagłówki `X-RateLimit-*` czytane, `Retry-After` honorowany; 500/min; feed dzienny po uzgodnieniu | do zbudowania po pomiarze 3 |
| `source/saos/` | `GET /api/dump/judgments?pageSize=100&pageNumber=n&…` z zakresem dat; przy synchronizacji `sinceModificationDate` | rekord z Dump API jest kompletny (`textContent`, `courtCases[]`, `judges[]`); osobny `fetch` tylko dla `porownaj` | nieznane; dwa niezależne klienty zablokowane na API wyszukiwania; Dump API nie testowane | **warunkowy**: istnieje po pomiarach 2a i 2b |

Kanału FTP nie ma w tej tabeli i to jest decyzja, nie przeoczenie (ADR-0003, rozstrzygnięcie 2). Rysunek i tabela pokazują to, co istnieje albo jest rozstrzygnięte, a pomiar 1 kosztuje jedno żądanie i jeszcze nie padł — przy czym tytuł komunikatu UZP mówi o **wyłączeniu serwera**, więc plan zakłada wynik negatywny. Kanał wchodzi razem z decyzją 9 (sekcja 8), która rozstrzyga jego postać: pełny kanał z własnym właścicielem protokołu albo import offline z lokalnego lustra.

Narzędzie `porownaj` (5.1) pobiera tę samą sprawę dwoma kanałami, pokazuje różnicę znormalizowanego tekstu i **zapisuje wynik do `equivalences`** (4.4). Bez tego pomiar 3 z audytu nie ma narzędzia, a dwa kanały nie mają wspólnej tożsamości.

### 4.4 Tożsamość dokumentu i model danych

Rozstrzygnięcie do ADR-001, **przed** pierwszym zapisem do bazy:

**Dokument jest jednostką. Sygnatura jest etykietą. Relacja jest wiele-do-wielu. Treść jest wersjonowana, nigdy nadpisywana.**

Dowody: pliki `2021_1820_1821_1834.pdf` z listingu FTP; lista „Sygnatura akt / Sposób rozstrzygnięcia" w `Details`; rekord SAOS „KIO 233/18, KIO 234/18"; dokumentacja SAOS: „orzeczenie czasem może dotyczyć wielu spraw (np. orzeczenia KIO)"; pole `primary_signature` w API Atlasu; kolektor Legal Data Hunter, który bierze tylko pierwszą sygnaturę i przez to gubi sprawy (3.1). Jedna sygnatura na kilku dokumentach: postanowienie i wyrok w tej samej sprawie; sprostowanie, jeśli publikowane osobno (pomiar 7).

```
documents                                      -- jeden wiersz na dokument
  doc_id            TEXT PK      -- "{source}:{source_ref}", np. "uzp:9620", "atlas:kio-827-18", "saos:354301"
  source            TEXT         -- uzp | atlas | saos | ftp
  source_ref        TEXT         -- identyfikator w kanale, tak jak przyszedł
  kind              TEXT NULL    -- KIO | SO | SA | SN (u UZP)
  first_seen_at     TEXT
  last_seen_at      TEXT
  current_sha256    TEXT         -- która wersja jest "bieżąca"; decyzja operatora/ADR, nie algorytmu
  UNIQUE (source, source_ref)

raw_versions                                   -- jeden wiersz na wersję treści
  doc_id            TEXT
  content_sha256    TEXT         -- SHA-256 z content_bytes
  fetched_at        TEXT         -- ISO 8601 UTC
  details_bytes     BLOB NULL    -- Details/{id} (uzp)
  content_bytes     BLOB         -- ContentHtml (uzp) | JSON rekordu (atlas, saos) | plik (ftp)
  pdf_bytes         BLOB NULL    -- na życzenie
  fetch_meta        TEXT         -- JSON zależny od kanału: dla HTTP status, nagłówki, adres finalny po
                                 -- przekierowaniach i użyty User-Agent; dla kanału plikowego nazwa pliku,
                                 -- rozmiar, znacznik czasu z serwera i sposób pozyskania. Nazwa `http_meta`
                                 -- niosła założenie, że każdy kanał jest kanałem HTTP — to samo, które stało
                                 -- za strzałką z `ftp.py` do `httpclient.py` (ADR-0003)
  PK (doc_id, content_sha256)
  -- ta sama treść pobrana ponownie: aktualizuje documents.last_seen_at, nie tworzy wiersza
  -- inna treść: nowy wiersz + wpis w dzienniku; sprostowania i niedeterministyczne renderowanie (pomiar 19)
  -- są obie widoczne, a nie zgubione

cases
  signature         TEXT PK      -- kanoniczna postać z docid.py: "KIO 827/18", "KIO/UZP 1482/08", "KIO/KU 97/13"
  first_seen_doc    TEXT

document_cases
  doc_id, signature, is_primary BOOL, outcome TEXT NULL
  PK (doc_id, signature)         -- outcome per sygnatura, bo Details podaje rozstrzygnięcie osobno dla każdej

equivalences                                   -- to samo orzeczenie z dwóch kanałów
  doc_id_a, doc_id_b, method TEXT, similarity REAL, decided_at TEXT, decided_by TEXT
  PK (doc_id_a, doc_id_b)        -- method: porownaj | sygnatura | reczne; zasilane przez `porownaj`, nigdy domyślnie

metadata                                       -- pochodne z details_bytes; przypięte do wersji
  doc_id, content_sha256, parse_version, doc_type, ruling_date NULL, chair, purchaser, city,
  procedure, order_kind, dissent BOOL
  PK (doc_id, content_sha256)

provisions   (doc_id, content_sha256, article)          -- z Details, wartości ze słownika
index_terms  (doc_id, content_sha256, term)             -- z Details, wartości ze słownika
sections     (doc_id, content_sha256, parse_version, ordinal, kind, text)
             PK (doc_id, content_sha256, ordinal)
             -- kind: naglowek | sklad | strony | sentencja | uzasadnienie | stan_faktyczny | ocena |
             --       koszty | pouczenie | zdanie_odrebne | nieprzypisane
citations    (doc_id, content_sha256, ordinal, char_start, char_end, raw, signature_norm,
              target_kind, resolved_signature NULL)
             -- target_kind: kio | so | sn | sa | tsue | inne; resolved_signature → cases.signature, jeśli w korpusie
fts          -- FTS5 nad sections.text, external content, tylko dla documents.current_sha256

runs         (run_id, started_at, finished_at, command, criteria_json, channel, requests_sent,
              docs_new, versions_new, docs_seen, errors, status, resume_token)
requests_log (run_id, ts, method, url_redacted, status, latency_ms, bytes)
             -- `method` i `status` niosą polecenie i kod **protokołu**, nie wyłącznie HTTP:
             -- HTTP `GET`/`200`, FTP `RETR`/`226` (ADR-0003)
dictionaries (name, fetched_at, source_url, sha256, payload)
```

`docid.py` jest jedynym producentem `doc_id` i jedynym normalizatorem sygnatury (reguła 14). Normalizator ma test na każdej postaci sygnatury znalezionej w danych (pomiar 17), a po wdrożeniu `parser/cite.py` dostaje drugi, znacznie większy zbiór testowy: każde cytowanie w uzasadnieniu, którego nie umie znormalizować, ląduje w `citations` z `signature_norm = NULL` i jest policzone w raporcie pokrycia.

Bramka fazy 1 audytu w tym modelu: ta sama para `(source, source_ref)` o tym samym `content_sha256` nie tworzy drugiego wiersza w `raw_versions`; o innym tworzy nową wersję i wpis w dzienniku. Dwa kanały tworzą dwa `doc_id`, a ich tożsamość jest **stwierdzana** w `equivalences` przez `porownaj`, nie zakładana.

### 4.5 Parser: pakiet czysty, wersjonowany, ze złotym zbiorem

`parser/` dostaje bajty, zwraca struktury. Nie widzi sieci, bazy ani terminala. `PARSE_VERSION` w jednym miejscu; `przelicz` przelicza tylko wersje starsze.

- **`parser/details.py`**: metryka z `Details` (`<label>…</label><br/> wartość` w `<p>`, lista sygnatur w `<ul><li>`; struktura potwierdzona własnym odczytem i kodem Legal Data Hunter). Lista sygnatur w całości do `document_cases`, przepisy i hasła z walidacją wobec słownika. Pusta data to `NULL`, nigdy wartość zastępcza. „Przewodniczący: Prezes Krajowej Izby Odwoławczej" i „Tryb postępowania: brak danych" to wartości, nie błędy.
- **`parser/clean.py`**: normalizacja tekstu przed segmentacją i przed cytowaniami (odpowiednik `clean_text` z eyecite i `cleanup_content` z Juriscrapera): białe znaki, cudzysłowy, myślniki, numery stron na końcu, wykropkowane linie po „Przewodniczący:". Nie zmienia treści, zmienia szum; oryginał zostaje w `raw_versions`.
- **`parser/sections.py`**: segmentacja `ContentHtml`. Nagłówki HTML są kandydatami; rozstrzyga słownik wzorców (`^WYROK$`, `^POSTANOWIENIE$`, `^UCHWAŁA$`, `^orzeka:$`, `^postanawia:$`, `^Uzasadnienie$`, `^Izba ustaliła`, `^Izba zważyła`, `^O kosztach`, `^Zdanie odrębne`) plus heurystyki na fałszywe nagłówki (`Protokolant:` i nazwisko pod nim). Tekst, który nie pasuje, ląduje w `nieprzypisane` z zachowaniem kolejności.
- **`parser/cite.py`**: potok clean → extract → resolve → annotate (3.5). `extract` używa normalizatora z `docid.py` na wzorcach „KIO 113/22", „KIO/UZP 1482/08", „sygn. akt XXIII Ga 365/17" (SO), „III CZP 56/17" (SN), „C-652/22" (TSUE); `resolve` łączy do `cases`; `annotate` zapisuje offsety do `citations`, żeby eksport i faza 4 mogły pokazać cytowanie w kontekście.

Bramka fazy 2 dostaje **złoty zbiór**: `tests/gold/` z 50 dokumentami z różnych roczników, w których granice sekcji i lista cytowań są potwierdzone ręcznie (wzorzec HITL z JuDDGES, 3.6). Raport pokrycia liczy się wobec tego zbioru, a nie wobec samego siebie: ile dokumentów ma wszystkie sekcje, ile częściowo, ile wcale, ile ma pustą datę, ile cytowań nie dało się znormalizować, z rozbiciem na roczniki.

### 4.6 „Co nowego": trzy osie, a docelowo jedna

Bez zmian wobec wersji 1 co do trzech osi (okno dat przez `GetResults`, kontrola krzyżowa pośrednikiem, rzadki skan luk w identyfikatorach) i co do zasady, że każdy przebieg zapisuje, która oś co znalazła. Dwie zmiany po przeglądzie:

- **Skan luk ma górną granicę z pomiaru, nie z założenia.** Legal Data Hunter podaje ~33 366 (kwiecień 2026) jako maksimum; pomiar 6 sprawdza tę liczbę dwoma żądaniami zamiast szukać jej dwudzielnie od zera. Heurystyka „stop po 100 kolejnych brakach" jest odnotowana jako cudza; u nas skan zapisuje gęstość trafień i decyzję o zatrzymaniu podejmuje operator.
- **Docelowo źródło ma samo mówić, co się zmieniło.** SAOS ma `sinceModificationDate` (3.2), Rechtspraak `dcterms:modified` (3.7), Atlas `sort=newest` z `dateFrom` (3.10). UZP nie ma nic takiego i to jest najkonkretniejszy postulat do wniosku o ponowne wykorzystywanie w sposób stały (sekcja 8, decyzja 2): kanał z datą modyfikacji albo zrzut przyrostowy. Dopóki go nie ma, trzy osie zostają.

### 4.7 Tempo, grzeczność, zatrzymanie

Bez zmian wobec wersji 1 (identyfikacja w `User-Agent`, zatrzymanie zamiast obejścia, ślad w dzienniku), z jednym dopiskiem: cztery zdania „dobrych praktyk" z dokumentacji Atlasu (3.10) są zapisane w `source/atlas/contract.yaml` jako wymagania z testem, a adapter UZP spełnia je przez analogię, dopóki UZP nie określi własnych warunków.

### 4.8 Wyszukiwanie: najpierw dosłownie, mierzone

Bez zmian wobec wersji 1: SQLite FTS5 nad `sections.text` bieżącej wersji, zestaw 30–50 zapytań operatora w `tests/queries/` jako miara, migracja (Elasticsearch z Morfologikiem, Meilisearch jak w `juddges-app`, warstwa gęsta z modeli PL-MTEB) dopiero po tej mierze. Wynik zapytania zawsze mówi, czego nie objął: liczba dokumentów w korpusie, liczba przeszukanych sekcji, liczba dokumentów z pustą datą, które wypadły z filtra zakresowego (mina 2 audytu).

### 4.9 Eksport i atrybucja

`exporter.py` produkuje cztery formaty z tym samym blokiem atrybucji:

- **arkusz** (`openpyxl`): jeden wiersz na dokument, sygnatury jako lista w komórce, rozstrzygnięcie per sygnatura, przepisy, hasła, link do `Details`, `fetched_at`, `source`, `content_sha256`; tekst sekcji tylko na życzenie i przez `safetext`;
- **korpus tekstowy**: jeden `.md` na dokument z nagłówkiem YAML (escapowanym) i sekcjami;
- **Parquet** z `manifest.json` (liczba dokumentów, zakres dat, `parse_version`, SHA-256 każdego pliku, blok atrybucji, licencje per źródło); zbiory pochodzące od modelu osobno, z sufiksem `-derived` (3.6);
- **WARC** (`warcio`): surowe odpowiedzi z `raw_versions` i `fetch_meta` jako rekordy archiwalne (3.9). Rekord WARC powstaje wyłącznie dla kanału HTTP; dla kanału plikowego `fetch_meta` nie niesie odpowiedzi HTTP, więc eksport pomija te dokumenty i **mówi ile**.

Blok atrybucji (reguła 15, test w `tests/test_attribution.py`): `{rodzaj} KIO z {data lub "data nieznana"}, sygn. {sygnatury}, Krajowa Izba Odwoławcza; źródło: {adres Details}; wersja: {content_sha256[:12]}; pobrano {fetched_at}`. Dla rekordów z Atlasu dochodzi linia z licencji CC BY 4.0: `Źródło: Atlas Przetargów (https://atlasprzetargow.pl)`. Każdy cytat w eksporcie i w fazie 4 niesie ten blok plus dokładny fragment, tak żeby odbiorca mógł go sprawdzić przy źródle (wzorzec trwałego linku z cytatem, 3.7).

### 4.10 Faza 4 jako serwer MCP

`mcp_server.py` jest osobnym procesem, który importuje tylko `store` (odczyt) i `exporter` (blok atrybucji). Nie importuje `source` ani `pipeline`; skan AST tego pilnuje, a topologia procesu czyni to widocznym (3.8). Narzędzia:

| Narzędzie | Co zwraca | Uwagi |
|---|---|---|
| `search_rulings(query, filters)` | lista trafień z `structuredContent.citations` (tytuł = sygnatury + data, url = `Details`, snippet = fragment z FTS5) | zawsze z liczbami z 4.8 („czego zapytanie nie objęło") |
| `get_ruling(signature \| doc_id, mode)` | `mode=metadata`: metryka, sekcje jako nagłówki, cytowania; `mode=text`: także treść sekcji | `mode=text` jest włączany konfiguracją po ADR o wysyłaniu treści do modelu (sekcja 12 audytu); domyślnie wyłączony |
| `get_citations(signature, direction)` | co dokument cytuje / kto cytuje dokument, z `citations` | cała wartość grafu z 3.5 bez modelu |
| `cite(doc_id, fragment)` | blok atrybucji z 4.9 dla dokładnego fragmentu | fragment jest weryfikowany wobec `sections.text` bieżącej wersji; obcy fragment zwraca błąd, nie blok |

Dziennik wywołań jak w `CONSTITUTION.md` art. 3 z `kio-orzeczenia-mcp`: znacznik czasu, narzędzie, skrót parametrów, liczby wyników, bez treści. Zakres fazy 4 pozostaje ten z audytu (4.3): wspomaganie wyszukiwania i cytowania, nie ocena prawna; serwer tego nie zmienia, tylko czyni granicę jedną linią konfiguracji.

### 4.11 Bezpieczeństwo treści

Bez zmian wobec wersji 1: `safetext` i `richtext.safe` na każdej ścieżce (terminal, arkusz, `.md` z escapowanym YAML, Parquet bez interpretacji), reguła 13 jako skan AST od pierwszego commita, a od fazy 4 dodatkowo jako granica procesu.

---

## 5. Działanie

### 5.1 Polecenia

Każde polecenie jest cienką warstwą nad `ui/flow.py`; `cli.py` nie pisze żadnego zdania do użytkownika (reguła 9). Odbiorca ten sam co w CEIDG.

| Polecenie | Co robi | Żądania do sieci |
|---|---|---|
| `kio-tool sonda [--pomiar N] [--kontrakt] [--zgoda]` | Faza 0: wykonuje wybrane pomiary z sekcji 6 i zapisuje wynik do `docs/decisions.md` w formacie „zmierzone {data}, {N} żądań"; `--kontrakt` robi jedno wywołanie każdego punktu z `contract.yaml` i porównuje kształt z `tests/examples/`; nadaje się do uruchamiania z harmonogramu (odpowiednik „periodic smoke run" z TODO `kio-orzeczenia-mcp`) | pojedyncze; pomiar 9 wymaga `--zgoda` |
| `kio-tool pobierz` | Przebieg masowy według `criteria` wybranym kanałem; wznawialny (`--wznow`) | masowe; zgoda w sesji |
| `kio-tool aktualizuj` | Trzy osie z 4.6; raport, która oś co znalazła | przyrostowe; zgoda w sesji |
| `kio-tool przelicz` | Parser na wersjach starszych niż `PARSE_VERSION`; raport pokrycia wobec `tests/gold/` | **zero**; pilnowane przez `--block-network` |
| `kio-tool szukaj` | FTS5 z filtrami; wynik do terminala albo eksportu | zero |
| `kio-tool eksportuj --format xlsx\|md\|parquet\|warc` | Eksport z atrybucją i manifestem | zero |
| `kio-tool porownaj --sygnatura … --kanaly uzp,atlas` | Ta sama sprawa dwoma kanałami; różnica; zapis do `equivalences` | 2–4 |
| `kio-tool cytowania --sygnatura …` | Graf cytowań w obie strony z `citations` | zero |
| `kio-tool demo` | Tryb pokazowy na korpusie **generowanym** (mina 4) | zero; pilnowane przez `--block-network` |
| `kio-tool slowniki` | Odświeża słowniki z `/Dictionary*` z zapisem SHA-256 | kilka |
| `kio-tool serve-mcp` | Faza 4: serwer MCP nad korpusem (4.10) | zero do UZP; klient MCP po drugiej stronie |

### 5.2 Ścieżka operatora w kreatorze

1. **Cel.** Jedno z czterech: zakres dat, lista sygnatur, przepis Pzp (podpowiedź ze słownika, bo `Art` jest wrażliwy na format), hasło indeksu tematycznego. Odpowiedź staje się obiektem `criteria`.
2. **Kanał.** Tabela kandydatów z `capabilities()` i kosztem z 5.3. Kanały niedostępne po pomiarach są wyszarzone z powodem („SAOS: pomiar 2a negatywny 2026-…").
3. **Koszt i zgoda.** Liczba żądań, czas przy skonfigurowanym tempie, budżet u pośrednika. Zgoda właściciela w tej sesji; bez niej kreator kończy na podglądzie.
4. **Przebieg.** Puls w żądaniach wysłanych i dokumentach zapisanych (7.2 audytu). Przerwanie zostawia `resume_token`.
5. **Wynik.** Dokumentów nowych, wersji nowych, pominiętych, z pustą datą, błędów parsera, cytowań nieznormalizowanych. Propozycja eksportu.

### 5.3 Tabela kosztów, policzona z liczb ze źródła

Podstawa: rocznik 2024 to 4 266 orzeczeń (Atlas, strona rocznika, 2026-09-14); cały zbiór to ~29 tys. wg Atlasu (stan 16.08.2026) i ~31,7 tys. KIO + ~1,3 tys. SO wg Legal Data Hunter (kwiecień 2026); trzy liczby z trzech źródeł, rząd wielkości ten sam. Tempo UZP 1 żąd./s to precedens, nie pomiar. UZP liczone jako 2 żądania na dokument.

| Zakres | Kanał | Listowanie | Pobranie | Razem | Czas / budżet |
|---|---|---|---|---|---|
| Rocznik 2024 (4 266) | UZP | 427 stron | 8 532 | ~8 960 żądań | ~2,5 h przy 1/s; ~1,25 h przy 2/s |
| Rocznik 2024 | Atlas z kluczem | 43 | 4 266 | ~4 310 | jedna doba (5 000); min. ~9 min przez 500/min |
| Rocznik 2024 | Atlas bez klucza | 43 | 4 266 | ~4 310 | 3 doby (1 500/dobę/IP) |
| Cały zbiór KIO (~29–32 tys.) | UZP przez `GetResults` | ~3 000 | ~60 000 | ~63 000 | ~17,5 h przy 1/s, w sesjach |
| Cały zbiór | UZP przez skan id 1…34 000 (strategia LDH) | 0 | ~68 000 (w tym ~1,3 tys. SO i nieznana liczba pustych) | ~68 000 | ~19 h przy 1/s; ~9,5 h przy 2/s |
| Cały zbiór | Atlas z kluczem | ~300 | ~29 000 | ~29 300 | ~6 dób; **albo feed dzienny po uzgodnieniu** |
| 2007-12 – 2018-09 (22 168 KIO) | SAOS Dump API | zależy od filtra `courtType` (pomiar 2b): ~222 strony, jeśli jest; nieznana wielokrotność, jeśli nie ma | w zrzucie | – | kanał warunkowy |

Wniosek bez zmian wobec wersji 1, teraz z drugim źródłem liczb: dla pełnego zbioru różnica między UZP a Atlasem to „17–19 godzin renderowania na cudzym serwerze" wobec „jeden mail o feed dzienny". Rekomendacja dla odcinka 2018–dziś: pośrednik jako źródło pierwszego pobrania, UZP jako źródło weryfikacji na próbce (`porownaj`) i dopływu bieżącego.

### 5.4 Co się dzieje, gdy źródło się zmienia

Adapter dostaje 200 bez `div.search-list-item` → `SourceContractBroken` → przebieg staje z komunikatem „kształt odpowiedzi UZP nie zgadza się z kontraktem z {data}; uruchom `sonda --kontrakt`, potem popraw `contract.yaml` i nagraj nowe `tests/examples/`" → dziennik ma wpis → operator wie w pierwszej minucie. Uruchamianie `sonda --kontrakt` z harmonogramu (np. raz dziennie) zamienia „operator zauważy" na „narzędzie zauważy". Cache po `internal_id` przeżywa przebudowę (identyfikatory przetrwały lipcową); jeśli kiedyś nie przeżyje, `document_cases` po sygnaturze jest drugą drogą do tego samego dokumentu.

---

## 6. Faza 0 po przeglądzie: lista pomiarów

Numeracja z audytu zachowana. Status mówi, co dwa przebiegi przeglądu zrobiły za pomiar, a co zostaje.

| # | Pomiar | Status po przeglądzie | Co zostaje |
|---|---|---|---|
| 1 | FTP nadal odpowiada? | nie wykonany; tytuł komunikatu obniża oczekiwanie | jedno `curl ftp://ftp.uzp.gov.pl/KIO/Wyroki/`; plan zakłada wynik negatywny |
| 2a | Własny klient do **Dump API** SAOS | nie wykonany; API wyszukiwania blokuje dwa niezależne klienty; Dump API nieprzetestowane | jedno `GET /api/dump/judgments?pageSize=10&pageNumber=0&judgmentDateFrom=2018-09-01&judgmentDateTo=2018-09-30` (i wariant `judgmentStartDate`, bo wiki jest sprzeczna) |
| 2b | Czy Dump API filtruje po `courtType` | nie wykonany | jedno żądanie z `courtType=NATIONAL_APPEAL_CHAMBER`; jeśli nie filtruje, koszt odcinka 2007–2018 rośnie o wielokrotność i wraca pytanie o Atlas |
| 3 | Atlas: pełny tekst i opóźnienie | nie wykonany | `porownaj` na 5 sprawach z różnych lat; opóźnienie z porównania `fetched_at` przez 2 tygodnie |
| 4 | Kontrakt wyszukiwarki | **wykonany**: `Move` → `Details` własnym odczytem; `GetResults` z dwóch niezależnych kolektorów | 4b: jedno własne `POST` i zamrożenie odpowiedzi jako `tests/examples/uzp/getresults_*.html` |
| 5 | Warstwa tekstowa w próbce ~50 dokumentów | nie wykonany | bez zmian; próbka staje się jednocześnie zalążkiem `tests/gold/` |
| 6 | Granice przestrzeni identyfikatorów | **z drugiej ręki**: ~33 366 w kwietniu 2026, KIO i SO w jednej numeracji | dwa żądania (`Details/33366`, `Details/34500`) i jedno `GetResults` z `CountStats=True` po liczniki per organ (pomiar 16) |
| 7 | Sprostowania: nowy rekord czy nadpisanie? | nie wykonany; model danych obsługuje obie odpowiedzi | `GetResults` z `Sign=` dla sprawy ze znanym sprostowaniem |
| 8 | Dokumenty wielosygnaturowe w wyszukiwarce | **potwierdzone strukturalnie** (lista w `Details`, dokumentacja SAOS) | jeden odczyt `Details` sprawy z listingu FTP (`2021_1820_1821_1834`) |
| 9 | Tolerancja tempa | nie wykonany; wymaga zgody | start 1/s, narastanie do 2/s, stop przy pierwszym sygnale |
| 10 | Anonimizacja na większej próbce | siódmy dokument zgodny | 30–50 dokumentów, w tym z protokołem rozprawy |
| 11 | Co indeksuje „Hasło", co dokłada „w treści" | **wykonany strukturalnie** (`SCnt`, `Fle`) | jedno zapytanie o frazę z uzasadnienia z `SCnt=0` i `SCnt=1` |
| 12 | Zbiór KIO w `dane.gov.pl` | potwierdzony negatywny | zamknięty |
| 13 | Jak często data wydania jest pusta | klasa, nie wyjątek | policzyć na próbce 200 identyfikatorów |

Pomiary nowe (14–20 z wersji 1 bez zmian; 21–22 po przeglądzie narzędzi):

| # | Pomiar | Jak najtaniej | Co rozstrzyga |
|---|---|---|---|
| 14 | Warunki ponownego wykorzystywania dla `orzeczenia.uzp.gov.pl` w BIP UZP | przejrzeć BIP UZP i stopkę wyszukiwarki | Czy droga z art. 39 ust. 1 pkt 2 jest właściwa; treść pytania do prawnika |
| 15 | Warunki feedu dziennego Atlasu | jeden mail | Czy odcinek 2018–dziś da się wziąć bez 29 tys. wywołań |
| 16 | Liczniki `#resultCounts` przy pustej frazie | jedno `GetResults` z `CountStats=True` | Rozmiar zbioru per organ; zastępuje część pomiaru 6 |
| 17 | Postaci sygnatur w zbiorze | z listingu wyników po rocznikach; docelowo z `citations` | Test normalizatora `docid.py` |
| 18 | Czy zmiana Pzp z 13.03.2026 zmieniła słownik przepisów | dwa wywołania `/DictionaryPzpArticle/SearchArticle` | Czy słowniki wersjonować po dacie |
| 19 | Czy `ContentHtml` jest bitowo stabilny między pobraniami | ten sam `id` dwa razy w odstępie doby | Czy `(doc_id, content_sha256)` jest kluczem, czy fikcją |
| 20 | Co zwracają `/AiSearch/*` | narzędzia deweloperskie przeglądarki | Czy UZP ma warstwę semantyczną do cytowania |
| 21 | Czy blokada sieci w testach współistnieje z wstrzykniętym transportem `httpx` **i** czy sięga gniazda | jeden test lokalny, zero żądań | **Wykonany w obu połowach 2026-09-15**: tak i tak. Blokada zamknięta dla każdego protokołu; otwarte zostaje odtwarzanie kaset (pomiar 4b) |
| 22 | Gęstość cytowań i udział nieznormalizowanych | `parser/cite.py` na próbce z pomiaru 5, zero żądań | Czy graf cytowań jest wart fazy 2 i ile postaci sygnatur brakuje w `docid.py` |

Bramka fazy 0 bez zmian: właściciel widzi tabelę kanałów z pomiarami i wybiera. Przed nią `source/` nie powstaje.

---

## 7. Żądania wykonane w tym przeglądzie

Dla rozliczalności (7.1 audytu). Wszystkie żądania były pojedynczymi odczytami; żadne nie było testem tempa ani przebiegiem masowym. Zlecenie właściciela potraktowałem jako zgodę na pojedyncze odczyty diagnostyczne w rozumieniu 13.2 pkt 4 audytu.

**Przebieg 1 (weryfikacja źródeł):**

| Host | Żądań | Cel | Wynik |
|---|---|---|---|
| `orzeczenia.uzp.gov.pl` | 3 GET | `Move` (przekierowanie na `Details/9620`), `PdfMetrics/9620`, `ContentHtml/18946` | 200, 200, 200 |
| `www.gov.pl` | 1 GET | komunikat o FTP | 200 |
| `atlasprzetargow.pl` | 2 GET | „O nas", dokumentacja API | 200, 200 |
| `www.saos.org.pl` | 2 GET | `/api/search/judgments` | zablokowane (bot detection) |
| `szukio.pl` | 1 GET | oferta | 429 |
| `bip.warszawa.wsa.gov.pl` | 1 GET | tekst jednolity ustawy o otwartych danych | 200 |
| `api.github.com`, `raw.githubusercontent.com` | 5 GET | `kio-orzeczenia-mcp`: metadane, `README`, `DISCOVERY`, `CONSTITUTION`, drzewo | 200 (drzewo puste) |
| wyszukiwarka | 11 zapytań | – | – |

**Przebieg 2 (przegląd narzędzi):**

| Host | Żądań | Cel | Wynik |
|---|---|---|---|
| `raw.githubusercontent.com` | 9 GET | `worldwidelaw/legal-sources/sources/PL/KIO/*` (5, w tym `retrieve.py` 404); `matematicsolutions/legal-data-hunter*` (4, wszystkie 404: repo nie istnieje pod tą nazwą albo jest prywatne) | 200×4, 404×5 |
| `api.github.com` | 3 GET | metadane repozytoriów | limit API (403), bez danych |
| `github.com` | 3 GET | `juriscraper/CONTRIBUTING.md`, `pwr-ai/JuDDGES` README, wiki `CeON/saos` | 200×3 |
| `skills.lc` | 1 GET | skill `legal-data-hunter-pl` | 200 |
| `www.saos.org.pl` | 1 GET | strona pomocy Dump API | zablokowane (bot detection) |
| `orzeczenia.uzp.gov.pl`, `atlasprzetargow.pl`, `szukio.pl` | **0** | – | – |
| wyszukiwarka | 8 zapytań | – | – |

Czego przegląd **nie** zrobił: nie wysłał żadnego `POST` do `GetResults`, nie pobrał żadnego PDF-a, nie sprawdził FTP, nie wywołał Dump API SAOS (zablokowane na poziomie strony pomocy, więc prawdopodobnie i API), nie odczytał BIP UZP pod kątem warunków ponownego wykorzystywania (pomiar 14), nie uruchomił żadnego cudzego kolektora.

---

## 8. Decyzje właściciela

Pięć decyzji z 13.2 audytu stoi; wersja 1 dodała dwie (kolejność kanałów, co jest surowcem); przegląd narzędzi zmienia treść dwóch i dodaje jedną.

1. **Czy w ogóle budować** (bez zmian): „nie" dla „wyszukać i przeczytać", „tak" dla programowego dostępu do korpusu. Przegląd narzędzi nie znalazł nikogo, kto utrzymuje otwarty, wersjonowany, lokalny korpus KIO: Legal Data Hunter ma kolektor, który nigdy nie wykonał pełnego przebiegu (`total_records: 0`), `kio-orzeczenia-mcp` jest POC bez magazynu, Atlas i SzuKIO są produktami zamkniętymi lub pośredniczącymi. Nisza z 4.2 audytu jest nadal pusta.
2. **Kiedy pytać prawnika i o co** (zmieniona treść): pytanie ma kształt art. 39 ust. 1 pkt 2 i ust. 2 ustawy o otwartych danych, zależy od pomiaru 14, a wniosek o ponowne wykorzystywanie w sposób stały dostaje **konkretny postulat techniczny**: kanał z datą modyfikacji albo zrzut przyrostowy, na wzór `sinceModificationDate` w SAOS (3.2). Rekomendacja: pomiar 14 w pierwszym dniu fazy 0, prawnik z jego wynikiem, wniosek przed fazą 1.
3. **Kształt fazy 4** (nowa): serwer MCP nad korpusem (4.10) zamiast asystenta wbudowanego w pakiet. Argumenty: granica z reguły 13 staje się granicą procesu; ADR o wysyłaniu treści do modelu jest jedną linią konfiguracji; właściciel dostaje pytania w języku naturalnym bez własnego czatu. Koszt: zależność od klienta MCP po drugiej stronie. Zakres z 4.3 audytu („wspomaganie, nie ocena") bez zmian.
4. **Reguła zgody** (bez zmian).
5. **Gdzie mieszka repozytorium** (bez zmian).
6. **Kolejność kanałów dla odcinka 2018–dziś** (z wersji 1, wzmocniona): tabela 5.3 ma teraz dwie niezależne liczby wielkości zbioru i kosztu; rekomendacja bez zmian: Atlas do pierwszego pobrania, UZP do weryfikacji i dopływu. Warunki: pomiary 3 i 15.
7. **Co jest surowcem** (z wersji 1): HTML (`Details` + `ContentHtml`) jako surowiec, PDF na życzenie, WARC jako eksport archiwalny. Alternatywa (PDF jako surowiec) bez zmian.
8. **Czy graf cytowań wchodzi do fazy 2** (nowa): koszt to jeden czysty moduł i pomiar 22 (zero żądań); korzyść to relacja KIO → SO, „cytowane przez" i największy dostępny test normalizatora sygnatur. Rekomendacja: tak, pod warunkiem, że pomiar 22 pokaże udział nieznormalizowanych poniżej kilku procent na próbce; w przeciwnym razie najpierw naprawić `docid.py`.
9. **Postać kanału FTP, jeśli pomiar 1 wypadnie pozytywnie** (nowa, z ADR-0003). Przy wyniku negatywnym decyzja odpada bez kosztu, a tytuł komunikatu UZP każe zakładać właśnie taki wynik. Wariant **(a)**: pełny kanał z własnym właścicielem protokołu obok `httpclient.py`, wspólną polityką wyjścia w postaci par `(schemat, host)`, tempem z `ratelimit.py` i wpisem w `requests_log`; identyfikacja hasłem anonimowym z adresem kontaktowym, bo FTP nie ma `User-Agent`. Wariant **(b)**: import offline — operator robi jedno lustro katalogu narzędziem systemowym pod jedną zgodą, a `source/archiwum/` czyta katalog lokalny i nie otwiera żadnego połączenia. Koszt (b): pobranie ~30 tys. plików dzieje się poza jakimkolwiek strażnikiem narzędzia, bez `requests_log`, z tempem ustawionym przez operatora. Zysk (b): reguła 11 zostaje z jednym właścicielem i pełnym pokryciem, a kanał jest jedynym, którego **pełną** ścieżkę da się przetestować przy włączonej blokadzie sieci. Rekomendacja: (b), bo publikacja ustała 30.09.2025, więc lustro jest jednorazowe; (a) tylko wtedy, gdyby FTP okazał się nadal aktualizowany — wtedy kanał ma dopływ bieżący i potrzebuje dziennika oraz wznawiania. Niezależnie od wariantu nazwa kanału opisuje **pochodzenie bajtów**, nie transport.

---

## 9. Czego ten dokument nie zrobił

- Nie potwierdził własnym klientem `POST /Home/GetResults` ani Dump API SAOS. Kontrakt wyszukiwarki stoi na dwóch niezależnych cudzych kolektorach i moich odczytach GET; SAOS stoi na dokumentacji z 2015 i snippetach z 2026.
- Nie uruchomił żadnego z przeglądanych narzędzi. Wszystkie oceny pochodzą z lektury kodu, dokumentacji i kart projektów, z datą.
- Nie sprawdził kolizji vcrpy z wstrzykniętym transportem `httpx` (pomiar 21).
- Nie napisał kodu. Schematy w 4.3–4.5 i 4.10 są propozycją do ADR-001 i ADR-002 (surowiec, treść do modelu), nie implementacją. Pierwsze trzy testy, które mają powstać: `test_boundaries.py`, normalizator sygnatur na postaciach z pomiaru 17, i `--block-network` w konfiguracji pytest.
- Nie jest opinią prawną. Odczyt art. 39 ustawy o otwartych danych jest odczytem tekstu i tak ma być traktowany.
