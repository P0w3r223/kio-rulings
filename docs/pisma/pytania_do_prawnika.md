# Pytania do prawnika — projekt

Data przygotowania: 2026-09-15
Status: draft — do przekazania prawnikowi przez właściciela
Autor: P0w3r223
Related to: `AUDYT_KIO_ORZECZENIA.md` (3.3, 3.4, 3.6, 13.2 pkt 2), `ARCHITEKTURA_KIO_TOOL.md` (1.2, 8 decyzja 2), `docs/decisions.md` (pomiar 14)

---

## Jak czytać ten dokument

Audyt rekomenduje konsultację **przed fazą 1**, bo pytanie 2 dotyczy czynności, którą faza 1
wykonuje masowo. Pytania 1–3 są pilne w tym sensie; pytanie 4 dotyczy fazy 4 i może poczekać,
ale jego odpowiedź wpływa na to, co wolno napisać w opisie przeznaczenia narzędzia — a ten
ma powstać **przed** warstwą modelu, nie po niej.

### Które pytanie blokuje co (rozstrzygnięcie właściciela, 2026-09-17)

Cztery pytania nie mają jednej wagi czasowej i warto, żeby prawnik o tym wiedział przy
układaniu własnej kolejki:

| Pytanie | Co blokuje | Kiedy potrzebna odpowiedź |
|---|---|---|
| **1** — czy wniosek z art. 39 czegoś nie przesądza | nic nie zatrzymuje; wniosek idzie **równolegle** | im wcześniej, tym lepiej — odpowiedź może zmienić sposób pobierania w okresie oczekiwania na decyzję Urzędu |
| **2** — bazy *sui generis* | wejście do **fazy 1**; wejście bramki fazy 0 **tylko** w gałęzi, w której pomiary 2a i 3a wypadną negatywnie | przed pierwszym przebiegiem masowym |
| **3** — obowiązki administratora danych | fazę 1 (kształt magazynu i eksportu) | przed pierwszym zapisem korpusu |
| **4** — AI Act | fazę 4 | przed warstwą modelu |

Trzy dokumenty tego projektu mówiły o kolejności pism trzy różne rzeczy: `docs/pomiary.md`
nazywał je „niezależnymi od siebie nawzajem", `ARCHITEKTURA_KIO_TOOL.md` decyzja 2 ustawiała
prawnika **przed** wnioskiem, a sam projekt wniosku radził pokazać pismo prawnikowi przed
wysłaniem. Różnica między pierwszym a drugim odczytem to ~14 dni wobec ~3 miesięcy ścieżki
krytycznej. Właściciel rozstrzygnął 2026-09-17: **wniosek idzie równolegle**, a pytanie 1
zostaje wydzielone jako pilne, bo dotyczy pisma, które już leży gotowe.

Świadomie przyjęte ryzyko tego rozstrzygnięcia: jeżeli odpowiedź na pytanie 1 wypadnie tak, że
warunki określone przez Urząd wiążą wstecz, dowiemy się o tym **po** złożeniu wniosku. Cena
ostrożności była wyższa — dwa i pół miesiąca zatrzymania pozycji, której kosztem jest cudzy
kalendarz, a nie nasza praca.

Każde pytanie ma trzy części: co ustaliliśmy sami i skąd, czego nie wiemy, i jaka decyzja
projektowa od odpowiedzi zależy. Ostatnia część jest najważniejsza — bez niej prawnik nie wie,
która z możliwych odpowiedzi jest dla nas kosztowna.

**Nic w tym dokumencie nie jest opinią prawną.** Wszystko, co niżej nazwane jest ustaleniem,
pochodzi z odczytu tekstu przepisu albo strony internetowej, z datą, i wymaga potwierdzenia.

---

## Stan faktyczny, wspólny dla wszystkich pytań

Budujemy lokalny zbiór orzecznictwa Krajowej Izby Odwoławczej — organu quasi-sądowego przy
Prezesie Urzędu Zamówień Publicznych. Zbiór ma objąć około 30 tysięcy orzeczeń z lat
2007–2026, z pełną treścią uzasadnień. Źródła: wyszukiwarka UZP (`orzeczenia.uzp.gov.pl`),
ewentualnie pośrednik prywatny (Atlas Przetargów, licencja CC BY 4.0) oraz serwis SAOS dla lat
2007–2018. Zbiór jest lokalny i służy analizie orzecznictwa; **nie planujemy** jego publicznego
udostępniania w obecnej fazie, ale chcemy wiedzieć, co by z tego wynikało.

Ustalone własnym odczytem, z datami:

- Orzeczenia KIO jako dokumenty urzędowe nie stanowią przedmiotu prawa autorskiego (art. 4
  pkt 2 ustawy o prawie autorskim).
- Izba **anonimizuje** dane osób fizycznych: przedsiębiorca jednoosobowy występuje pod
  inicjałami wplecionymi w nazwę firmy, również gdy jest tylko wzmiankowany. Skład orzekający
  i protokolanci — pełnym imieniem i nazwiskiem, zawsze. Obserwacja na kilkunastu dokumentach
  z lat 2015–2025, nie badanie ilościowe.
- UZP **nie publikuje zasad anonimizacji** ani metodologii; nie odnaleźliśmy też klauzuli
  informacyjnej skierowanej do stron postępowania odwoławczego.
- Serwis `orzeczenia.uzp.gov.pl` nie zawiera warunków ponownego wykorzystywania, noty
  licencyjnej ani informacji o braku warunków (zmierzone 2026-09-15). Licencja CC BY-SA 4.0
  ze stopki `gov.pl` jest zakreślona domeną `www.gov.pl`.
- Serwis nie ma `robots.txt` (404). Nie zamierzamy omijać żadnych zabezpieczeń technicznych;
  narzędzie ma się zatrzymywać przy odmowie serwisu, a nie szukać drogi naokoło.

---

## Pytanie 1 — czy wniosek z art. 39 jest właściwą drogą i czy czegoś nie przesądza

**Co ustaliliśmy.** Art. 39 ust. 1 pkt 2 ustawy z 11 sierpnia 2021 r. o otwartych danych
przewiduje wniosek, gdy informacje sektora publicznego są udostępniane „w innym systemie
teleinformatycznym" niż BIP albo portal danych „i nie zostały określone warunki ponownego
wykorzystywania [...] albo nie poinformowano o braku takich warunków". Obie przesłanki wydają
się spełnione łącznie. Art. 39 ust. 2 pozwala wnosić o dostęp „w sposób stały i bezpośredni
w czasie rzeczywistym"; art. 40 ust. 1 daje 14 dni, art. 17 — bezpłatność co do zasady.

**Czego nie wiemy.** Czy złożenie wniosku w jakikolwiek sposób **pogarsza** naszą pozycję:
czy do czasu rozpatrzenia wniosku wolno pobierać informacje istniejącymi środkami (art. 14
ust. 1 mówi, że ISP udostępnia się „bezwarunkowo, z wyjątkiem przypadków określonych
w ustawie", a art. 11 ust. 5, że brak informacji o warunkach oznacza udostępnianie bez
warunków); i czy warunki określone przez Urząd w odpowiedzi będą wiązać wstecz.

**Od czego to zależy decyzyjnie.** Czy wysyłamy wniosek **przed** pierwszym pobraniem, czy
równolegle. Projekt pisma: `docs/pisma/wniosek_uzp_art39.md`.

**Stan na 2026-09-17: wniosek idzie równolegle, przed odpowiedzią na to pytanie** (decyzja
właściciela). Odpowiedź jest więc potrzebna nie po to, żeby zdecydować o wysłaniu, tylko po to,
żeby wiedzieć, **czy w okresie oczekiwania na decyzję Urzędu wolno pobierać istniejącymi
środkami** — a ten okres to 14 dni ustawowo, do 2 miesięcy przy zawiadomieniu. To jest pytanie
o teraz, nie o później.

## Pytanie 2 — ochrona baz danych *sui generis* wobec ustawowego prawa reużycia

**Co ustaliliśmy.** Ustawa z 27 lipca 2001 r. o ochronie baz danych chroni inwestycję
producenta bazy niezależnie od praw autorskich do poszczególnych elementów. Systematyczne
pobranie „istotnej części" bazy mogłoby teoretycznie naruszać ten monopol nawet wtedy, gdy
pojedyncze orzeczenie nie jest przedmiotem prawa autorskiego.

**Czego nie wiemy.** Jak ta ochrona ma się do ustawowego prawa do ponownego wykorzystywania
ISP. W dostępnych źródłach nie znaleźliśmy jednoznacznego rozstrzygnięcia. Pytanie jest
praktyczne: planujemy pobranie **całości** zbioru, czyli z definicji istotnej części.

**Od czego to zależy decyzyjnie.** To jest pytanie, które audyt rekomenduje zamknąć **przed
fazą 1**, bo faza 1 wykonuje tę czynność masowo. Jeżeli odpowiedź jest niepewna, rozważamy
pobranie przez pośrednika (Atlas, CC BY 4.0, regulamin powołujący wprost ustawę o otwartych
danych) zamiast bezpośrednio z serwisu Urzędu — czyli inne rozstrzygnięcie architektoniczne,
nie inne pismo.

## Pytanie 3 — obowiązki administratora danych osobowych przy zbiorze orzeczeń

**Co ustaliliśmy.** Nowa ustawa o otwartych danych, w odróżnieniu od poprzedniej z 2016 r.,
zniosła zwolnienie reużytkowników z obowiązków informacyjnych z art. 13–14 RODO. Operator
zbioru staje się administratorem dla własnego celu i potrzebuje własnej podstawy z art. 6
ust. 1 RODO (realnie lit. f, z testem ważenia). Art. 6 ust. 2 ustawy o otwartych danych
ogranicza prawo do ponownego wykorzystywania ze względu na prywatność osób fizycznych,
**z wyjątkiem osób pełniących funkcje publiczne w związku z ich pełnieniem** — a osoby
występujące w orzeczeniach pełnym nazwiskiem to właśnie skład orzekający i protokolanci.

**Czego nie wiemy.** Trzech rzeczy:

1. Czy wobec członków składu orzekającego i protokolantów powstaje obowiązek z **art. 14
   RODO**, a jeżeli tak — czy wyłączenie „niewspółmiernie dużego wysiłku" (art. 14 ust. 5
   lit. b) ma tu zastosowanie. Wiemy, że jest interpretowane wąsko i że sama liczba osób nie
   wystarcza.
2. Co zrobić z **przeoczeniami anonimizacji** u źródła. Anonimizacja jest redakcyjna, wykonywana
   ręcznie, a UZP nie publikuje jej zasad — więc pojedynczy przeoczony fragment trafi do zbioru.
   Czy operator ma obowiązek aktywnie ich szukać, czy reagować na zgłoszenie?
3. Czy orzeczenia KIO mogą zawierać dane z **art. 10 RODO**. Z doktryny wynika, że
   rozstrzygnięcia cywilne i administracyjne nim objęte nie są, ale wniosek jest przez analogię
   i słabnie tam, gdzie orzeczenie stwierdza np. wprowadzenie zamawiającego w błąd.

**Od czego to zależy decyzyjnie.** Od odpowiedzi 1 zależy, czy w ogóle powstaje obowiązek
informacyjny i w jakiej formie (np. nota na stronie projektu). Od odpowiedzi 2 — czy
w narzędziu ma powstać osobna ścieżka zgłaszania i usuwania fragmentów, czyli praca
projektowa, nie tylko prawna.

## Pytanie 4 — AI Act, jeżeli powstanie warstwa modelu językowego (faza 4)

**Co ustaliliśmy.** Załącznik III pkt 8(a) AI Act klasyfikuje jako wysokiego ryzyka systemy
przeznaczone do użytku przez organ sądowy lub w jego imieniu do wspomagania badania
i interpretacji faktów i prawa, oraz używane podobnie w **alternatywnym rozwiązywaniu sporów**.
Postępowanie przed KIO leży blisko tej kategorii.

Planowany zakres warstwy modelu jest **celowo węższy** niż to, co budzi wątpliwość:
wspomaganie wyszukiwania i cytowania, nie generowanie oceny prawnej. Ograniczenie ma podstawę
empiryczną: w recenzowanym badaniu (arXiv:2511.04205, publikacja w *Artificial Intelligence
and Law*, 2026) trzy czołowe modele przepuszczono przez oficjalny egzamin kwalifikacyjny na
członka KIO i żaden nie przeszedł progu w części praktycznej. Warstwa modelu miałaby działać
jako osobny proces (serwer MCP) nad lokalnym zbiorem, zwracając cytaty z odesłaniem do źródła.

**Czego nie wiemy.** Czy narzędzie służące **podmiotowi prywatnemu do budowania wiedzy
o orzecznictwie** mieści się poza tą kategorią, oraz gdzie przebiega granica wobec narzędzia
wspierającego stronę w toczącym się sporze. Rozumiemy, że zależy to od opisu przeznaczenia.

**Od czego to zależy decyzyjnie.** Od odpowiedzi zależy treść opisu przeznaczenia, który ma
powstać **przed** warstwą modelu, oraz to, czy narzędzie zwraca treść orzeczeń, czy wyłącznie
metadane i cytat — w architekturze jest to jedna linia konfiguracji, ale decyzja zapada w ADR,
nie w kodzie.

---

## Czego od prawnika nie potrzebujemy

Żeby nie kupować pracy, której nie wykorzystamy: nie potrzebujemy opinii o dopuszczalności
scrapingu jako takiego ani analizy regulaminu serwisu, bo regulaminu nie ma, a granicę
techniczną zamknęliśmy po swojej stronie regułą projektową — narzędzie nie omija zabezpieczeń,
nie rozwiązuje CAPTCHA, nie podszywa się pod przeglądarkę i zatrzymuje się przy odmowie
serwisu. Rozumiemy, że naruszenie warunków korzystania z portalu ma charakter cywilny, chyba
że pozyskanie wymaga obejścia zabezpieczenia technicznego (art. 267 § 1 k.k.) — i właśnie
dlatego ta granica jest u nas regułą kodu, a nie przedmiotem oceny.
