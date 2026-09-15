# Wiadomość do Atlasu Przetargów o feed dzienny — projekt do wysłania (pomiar 15)

Data przygotowania: 2026-09-15
Status: draft — do wysłania przez właściciela
Autor: P0w3r223
Related to: `ARCHITEKTURA_KIO_TOOL.md` (1.4, 3.10, 5.3, 8 decyzja 6), `AUDYT_KIO_ORZECZENIA.md` (4.2)

---

## Po co to pismo

To jest **pomiar 15** i zarazem najtańsza pozycja w całym planie względem tego, co może dać.
Dokumentacja Atlasu wspomina o „feedzie dziennym, pełnym zrzucie zamiast paginacji" dostępnym
po kontakcie mailowym. Jeżeli obejmuje on orzeczenia KIO, zmienia się rachunek całego odcinka
2018–dziś:

| Droga | Koszt |
|---|---|
| Atlas przez API, orzeczenie po orzeczeniu | ~29 300 wywołań, około 6 dób przy limicie 5 000 na konto |
| Atlas przez feed dzienny | jedna wiadomość i uzgodnienie |
| UZP przez wyszukiwarkę | ~63 000 żądań, 17–19 godzin renderowania na cudzym serwerze |

Odpowiedź ma też drugą wartość, niezależną od feedu: potwierdza albo obala **pomiar 3**
w części dotyczącej opóźnienia publikacji. Dostawca deklaruje, że UZP publikuje z opóźnieniem,
ale nie podaje liczby — a bez liczby nie da się ocenić, czy ten kanał wystarcza tam, gdzie
liczy się świeżość.

## Czego ta wiadomość celowo nie robi

Nie prosi o dostęp poza regulaminem, nie prosi o zniesienie limitów i nie zapowiada pobierania
przed uzgodnieniem. Atlas dokumentuje cztery „dobre praktyki dla klientów" (synchronizacja
przyrostowa, honorowanie `Retry-After`, własny `User-Agent` z kontaktem, cache lokalny)
i adapter ma je spełniać dosłownie — więc wiadomość zaczyna od tego, że zamierzamy je
spełniać, a nie od prośby o wyjątek.

---

## Treść wiadomości

> **Temat:** Pytanie o dostęp do zbioru orzeczeń KIO — feed dzienny albo zrzut
>
> Dzień dobry,
>
> buduję lokalny, wersjonowany zbiór orzecznictwa Krajowej Izby Odwoławczej na potrzeby analizy
> orzecznictwa w zamówieniach publicznych. Państwa API jest jednym z dwóch kanałów, które biorę
> pod uwagę dla okresu od 2018 roku; drugim jest wyszukiwarka UZP.
>
> W dokumentacji znalazłem wzmiankę o możliwości uzgodnienia dziennego feedu albo pełnego
> zrzutu zamiast paginacji. Stąd trzy pytania:
>
> 1. Czy taka forma dostępu obejmuje również **orzeczenia KIO** (punkty `/api/kio`), czy
>    wyłącznie ogłoszenia o zamówieniach?
> 2. Jeżeli obejmuje — na jakich warunkach i w jakim formacie? Wystarczyłby zrzut zawierający
>    orzeczenia dodane i zmienione od poprzedniego zrzutu.
> 3. Jakie jest typowe **opóźnienie** między opublikowaniem orzeczenia przez UZP a jego
>    pojawieniem się u Państwa? Pytam o rząd wielkości — dni, tygodnie — bo od tego zależy,
>    czy Państwa kanał może być źródłem bieżącego dopływu, czy wyłącznie archiwum.
>
> Niezależnie od odpowiedzi: zamierzam korzystać z API zgodnie z opisanymi przez Państwa
> dobrymi praktykami — synchronizacja przyrostowa zamiast pełnych przebiegów, honorowanie
> nagłówka `Retry-After`, własny `User-Agent` z adresem kontaktowym i lokalny cache, żeby nie
> pobierać dwa razy tego samego. Atrybucja w formule „Źródło: Atlas Przetargów
> (https://atlasprzetargow.pl)" będzie towarzyszyć każdemu udostępnieniu danych pochodzących
> z Państwa serwisu, zgodnie z licencją CC BY 4.0.
>
> Jeżeli feed nie obejmuje orzeczeń KIO, proszę o informację — wtedy po prostu pobiorę je
> przez API w tempie mieszczącym się w limitach i nie będę Państwa infrastruktury obciążać
> ponad to.
>
> Z góry dziękuję za odpowiedź,
>
> **[IMIĘ I NAZWISKO]**
> **[ADRES POCZTY]**
> **[ewentualnie: nazwa działalności / instytucji]**

---

## Do uzupełnienia przed wysłaniem

- adres poczty Atlasu — **nie weryfikowałem go u źródła**; jest na stronie kontaktowej
  i dokumentacji API, trzeba go odczytać przed wysłaniem;
- dane nadawcy;
- jeżeli masz już klucz API do Atlasu, warto go wspomnieć — kontakt od istniejącego
  użytkownika czyta się inaczej niż od anonimowego.

## Co zrobić z odpowiedzią

Trafia do `docs/decisions.md` jako pomiar 15, z datą i cytatem. Skutki:

- **feed obejmuje KIO** → decyzja 6 (kolejność kanałów) rozstrzyga się na korzyść Atlasu dla
  odcinka 2018–dziś, a UZP zostaje wyłącznie do weryfikacji na próbce (`porownaj`) i do
  dopływu bieżącego, jeśli opóźnienie Atlasu okaże się za duże;
- **feed nie obejmuje KIO, ale opóźnienie jest małe** → Atlas przez API do pierwszego
  pobrania, rozłożone na kilka dób;
- **opóźnienie jest duże albo nieznane** → Atlas do archiwum, UZP do dopływu bieżącego, czyli
  kanał hybrydowy z rekomendacji 13.1 audytu, tylko z inną linią podziału niż zakładano.
