# Wniosek do UZP o ponowne wykorzystywanie orzecznictwa KIO — projekt do wysłania

Data przygotowania: 2026-09-15
Status: draft — do uzupełnienia danymi wnioskodawcy i do wysłania przez właściciela
Autor: P0w3r223
Related to: `docs/decisions.md` (pomiar 14), `AUDYT_KIO_ORZECZENIA.md` (3.2, 13.2 pkt 2), `ARCHITEKTURA_KIO_TOOL.md` (1.2, 4.6, 8 decyzja 2)

---

## Po co to pismo i dlaczego teraz

Jedno pismo może usunąć problem, który architektura opisuje jako wymagający **trzech osobnych
osi** wykrywania nowości (4.6): okna dat, kontroli krzyżowej pośrednikiem i rzadkiego skanu luk
w identyfikatorach. Wszystkie trzy istnieją wyłącznie dlatego, że źródło samo nie mówi, co się
w nim zmieniło. SAOS ma na to `sinceModificationDate`, Rechtspraak `dcterms:modified`, Atlas
`sort=newest` z `dateFrom` — UZP nie ma nic.

Drugi powód jest po stronie urzędu i wart wypisania w piśmie: pobranie całego zbioru przez
wyszukiwarkę to około **63 000 żądań i 17–19 godzin renderowania** na serwerze UZP, bo PDF-y
i strony powstają na żądanie (audyt 2.2). Zrzut przyrostowy jest tańszy dla obu stron.

Termin ustawowy to 14 dni (do dwóch miesięcy przy zawiadomieniu o opóźnieniu), więc jest to
najdłuższa pozycja planu, która nie zależy od kodu. Dlatego idzie pierwsza.

## Podstawa — i dlaczego akurat ta

Art. 39 ust. 1 pkt 2 ustawy z 11 sierpnia 2021 r. o otwartych danych i ponownym
wykorzystywaniu informacji sektora publicznego: wniosek wnosi się, gdy informacje sektora
publicznego „są udostępniane w innym systemie teleinformatycznym niż [BIP albo portal danych]
i nie zostały określone warunki ponownego wykorzystywania [...] albo nie poinformowano o braku
takich warunków".

**Obie przesłanki są spełnione łącznie i to jest zmierzone, nie założone** (pomiar 14,
2026-09-15, `docs/decisions.md`): `orzeczenia.uzp.gov.pl` jest odrębnym systemem
teleinformatycznym, jego strony nie zawierają ani warunków ponownego wykorzystywania, ani
noty licencyjnej, ani informacji o braku warunków — zero trafień dla „licencj", „Creative",
„ponowne wykorzyst", „regulamin" w treści strony. Licencja CC BY-SA 4.0 ze stopki `gov.pl`
jest zakreślona domeną `www.gov.pl` i tej domeny nie obejmuje.

Art. 39 ust. 2 pozwala, żeby wniosek dotyczył udostępniania „w sposób stały i bezpośredni
w czasie rzeczywistym". To jest przepis, na którym stoi cały postulat techniczny poniżej.

**Zastrzeżenie.** To jest odczyt przepisu, nie opinia prawna. Przed wysłaniem warto pokazać
pismo prawnikowi razem z pytaniami z `pytania_do_prawnika.md` — zwłaszcza pytaniem 1, bo
odpowiedź UZP może określić warunki, a te będą wiązać.

---

## Treść wniosku

> **[MIEJSCOWOŚĆ], [DATA]**
>
> **[IMIĘ I NAZWISKO ALBO NAZWA WNIOSKODAWCY]**
> **[ADRES UMOŻLIWIAJĄCY DOSTARCZENIE ODPOWIEDZI]**
> **[ADRES POCZTY ELEKTRONICZNEJ]**
>
> **Prezes Urzędu Zamówień Publicznych**
> ul. Postępu 17a, 02-676 Warszawa
>
> ### Wniosek o ponowne wykorzystywanie informacji sektora publicznego
>
> Na podstawie art. 39 ust. 1 pkt 2 oraz art. 39 ust. 2 ustawy z dnia 11 sierpnia 2021 r.
> o otwartych danych i ponownym wykorzystywaniu informacji sektora publicznego wnoszę
> o umożliwienie ponownego wykorzystywania informacji sektora publicznego wskazanych poniżej.
>
> **1. Podmiot zobowiązany**
>
> Urząd Zamówień Publicznych.
>
> **2. Informacje sektora publicznego, które będą ponownie wykorzystywane**
>
> Orzeczenia Krajowej Izby Odwoławczej oraz orzeczenia sądów rozpoznających skargi na
> orzeczenia Izby, udostępniane w wyszukiwarce pod adresem `https://orzeczenia.uzp.gov.pl`,
> w pełnym zakresie czasowym gromadzonego zbioru — od początku orzekania Izby (grudzień
> 2007 r.) do chwili bieżącej, wraz z orzeczeniami publikowanymi w przyszłości.
>
> Dla każdego orzeczenia wnoszę o udostępnienie:
>
> - pełnej treści orzeczenia wraz z uzasadnieniem;
> - metryki dokumentu w zakresie, w jakim Urząd nią dysponuje: organu wydającego, rodzaju
>   dokumentu, daty wydania rozstrzygnięcia, **listy wszystkich sygnatur akt** objętych
>   dokumentem wraz ze sposobem rozstrzygnięcia dla każdej z nich, składu orzekającego,
>   zamawiającego, miejscowości, trybu postępowania, rodzaju zamówienia, powołanych przepisów
>   Prawa zamówień publicznych oraz zagadnień z indeksu tematycznego;
> - identyfikatora dokumentu używanego w systemie Urzędu oraz daty ostatniej modyfikacji
>   treści lub metryki.
>
> Wskazanie **listy sygnatur, a nie jednej sygnatury**, jest celowe: część dokumentów dotyczy
> kilku połączonych spraw, co widać zarówno w metryce udostępnianej przez wyszukiwarkę, jak
> i w nazewnictwie plików dawnego archiwum (np. `2021_1820_1821_1834.pdf`).
>
> **3. Cel ponownego wykorzystywania, w tym rodzaj działalności**
>
> [DO UZUPEŁNIENIA — np.:] Budowa i utrzymywanie lokalnego, wersjonowanego zbioru orzecznictwa
> Krajowej Izby Odwoławczej na potrzeby analizy orzecznictwa w zamówieniach publicznych,
> w ramach działalności [rodzaj działalności]. Zbiór służy wyszukiwaniu pełnotekstowemu,
> analizie ilościowej i rzetelnemu cytowaniu orzeczeń ze wskazaniem źródła. Każde udostępnienie
> albo zacytowanie orzeczenia pochodzącego z tego zbioru będzie opatrzone oznaczeniem organu,
> sygnaturą akt, datą wydania oraz wskazaniem źródła i czasu pozyskania informacji.
>
> **4. Forma przygotowania informacji i format danych**
>
> Postać elektroniczna. Preferowany format, w kolejności od najbardziej użytecznego:
>
> 1. dane ustrukturyzowane (JSON, XML albo CSV) obejmujące metrykę oraz treść orzeczenia;
> 2. treść w formacie HTML odpowiadającym temu, który wyszukiwarka udostępnia dziś pod
>    adresem `/Home/ContentHtml/{identyfikator}`, wraz z metryką w postaci ustrukturyzowanej;
> 3. jeżeli żaden z powyższych nie jest możliwy — pliki w formacie, w jakim Urząd przechowuje
>    orzeczenia, wraz z wykazem wiążącym nazwę pliku z sygnaturami akt.
>
> Nie wnoszę o przygotowanie informacji w postaci wymagającej dodatkowego przetworzenia ponad
> to, czym Urząd już dysponuje.
>
> **5. Sposób i okres dostępu do informacji (art. 39 ust. 2)**
>
> Wnoszę o umożliwienie ponownego wykorzystywania **w sposób stały i bezpośredni w czasie
> rzeczywistym**, przez jeden z poniższych sposobów, wedle wyboru Urzędu:
>
> - interfejs programistyczny (API) pozwalający pobrać orzeczenia zmienione albo dodane po
>   wskazanej dacie — rozwiązanie stosowane w analogicznym zbiorze orzeczeń sądów
>   powszechnych i administracyjnych (SAOS, parametr `sinceModificationDate`); albo
> - okresowy zrzut przyrostowy (np. dobowy) udostępniany pod stałym adresem, obejmujący
>   orzeczenia dodane i zmienione od poprzedniego zrzutu; albo
> - jednorazowy zrzut całości zbioru wraz z późniejszymi zrzutami przyrostowymi.
>
> Okres dostępu: bezterminowo, a jeżeli Urząd określa okres — na okres 3 lat z możliwością
> przedłużenia.
>
> **Uzasadnienie tego żądania jest po stronie Urzędu, nie tylko wnioskodawcy.** Wyszukiwarka
> generuje treść dokumentów na żądanie, więc pozyskanie całego zbioru istniejącymi środkami
> oznaczałoby kilkadziesiąt tysięcy pojedynczych żądań i kilkanaście godzin pracy serwera
> Urzędu. Zrzut przyrostowy albo interfejs z datą modyfikacji obciąża infrastrukturę Urzędu
> nieporównanie mniej, a jednocześnie daje wnioskodawcy pewność kompletności, której
> pojedyncze pobrania nie dają.
>
> **6. Informacje dodatkowe**
>
> Uprzejmie proszę również o wskazanie, czy Urząd określił warunki ponownego wykorzystywania
> informacji udostępnianych w wyszukiwarce `orzeczenia.uzp.gov.pl`, a jeżeli ich nie określił —
> o potwierdzenie braku takich warunków. Na dzień złożenia wniosku ani warunki, ani informacja
> o ich braku nie są w tym serwisie publikowane.
>
> Proszę o przesłanie odpowiedzi na wskazany wyżej adres poczty elektronicznej.
>
> Z wyrazami szacunku,
>
> **[PODPIS / IMIĘ I NAZWISKO]**

---

## Do uzupełnienia przed wysłaniem

| Miejsce | Co wpisać |
|---|---|
| Nagłówek | miejscowość, data, imię i nazwisko albo nazwa, adres do doręczeń, adres poczty |
| Punkt 3 | cel i **rodzaj działalności** — ustawa wymaga obu; ogólnik („cele analityczne") bywa podstawą do wezwania o uzupełnienie |
| Podpis | forma zależna od kanału: pismo papierowe, ePUAP albo poczta elektroniczna |

Adres siedziby UZP w nagłówku pochodzi z ogólnodostępnych danych kontaktowych Urzędu
i **wymaga sprawdzenia przed wysłaniem** — ten dokument nie weryfikował go u źródła.

## Co zrobić z odpowiedzią

Każda odpowiedź, także odmowna, jest wynikiem pomiaru i trafia do `docs/decisions.md` z datą.
Trzy scenariusze i ich skutki dla architektury:

- **Urząd daje kanał z datą modyfikacji albo zrzut przyrostowy** → trzy osie z 4.6 redukują się
  do jednej, a `aktualizuj` staje się trywialne. To jest najlepszy możliwy wynik całej fazy 0.
- **Urząd określa warunki** → warunki wiążą, trafiają do `source/uzp/contract.yaml` z datą
  i do bloku atrybucji; reguła 15 dostaje wtedy podstawę mocniejszą niż decyzja projektowa.
- **Urząd odmawia albo milczy** → zostaje droga przez wyszukiwarkę z trzema osiami i tempem
  1 żąd./s, a odmowa sama w sobie jest informacją, którą warto mieć na piśmie przed pierwszym
  przebiegiem masowym.
