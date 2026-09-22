# kio-tool — wytyczne dla modelu, który obsługuje to narzędzie

Data: 2026-09-20, aktualizacja 2026-09-22 (źródło przy trafieniu, sekcje i odesłania w `md`)
Status: obowiązujący
Dotyczy: agenta (modelu) prowadzącego `kio-tool` w imieniu operatora

Ten plik jest instrukcją obsługi dla **modelu**, nie dla człowieka i nie dla programisty. Człowiek
ma kreator (`kio-tool` bez polecenia), programista ma `CLAUDE.md` i `docs/`. Tutaj stoi to, czego
model potrzebuje, żeby użyć narzędzia trafnie i nie wyrządzić szkody: co ono robi, czego nie robi,
co da się wyszukać i gdzie są pułapki.

---

## 1. Czym to jest w jednym akapicie

`kio-tool` buduje i utrzymuje **lokalny, wersjonowany korpus orzecznictwa Krajowej Izby
Odwoławczej**. Pobiera orzeczenia z jednego publicznego kanału (`atlas`), zapisuje pełny tekst
razem ze skrótem SHA-256 wersji, rozkłada każde orzeczenie na części, wyciąga z niego cytowania
i powołania na przepisy, a potem pozwala szukać w tym wszystkim **bez sieci**. Stan na 2026-09-20:
443 orzeczenia z roczników 2010–2026, 1 708 cytowań, 16 834 powołań na przepisy.

W narzędziu **nie ma modelu językowego**. To jest decyzja właściciela, nie brak: nie ma drugiego
wyjścia z procesu, nie ma łańcucha poświadczeń i nie ma miejsca, do którego mogłaby wyciec treść
orzeczenia. Rozumowanie należy do Ciebie; narzędzie dostarcza materiał i mówi, czego nie objęło.

## 2. Czego to narzędzie nie robi — powiedz to wprost, zanim ktoś się na tym oprze

- **Nie ocenia sprawy prawnie.** Zakres to wspomaganie wyszukiwania i cytowania. Wniosek prawny
  jest Twój albo człowieka i każdy trzeba sprawdzić u źródła.
- **Nie sięga przed rok 2010.** Izba orzeka od grudnia 2007, ale kanał zaczyna się w 2010.
  Pytanie o najstarsze orzecznictwo zostanie bez odpowiedzi — powiedz to, zamiast oddawać
  niepełny wynik jako pełny.
- **Nie wie, czy korpus jest kompletny.** Nikt nie zmierzył, ile orzeczeń w ogóle opublikowano,
  więc zdania „mamy wszystko" nie da się ani potwierdzić, ani obalić. Mów „443 pobrane
  orzeczenia", nigdy „wszystkie orzeczenia".
- **Nie anonimizuje.** Skład orzekający i protokolant są w treści z imienia i nazwiska (404 i 286
  dokumentów z 443). Nie przepisuj ich do odpowiedzi, notatek ani plików bez potrzeby.

## 3. Zasada nadrzędna: sieć wymaga zgody

`pobierz` i `wznow` wychodzą do cudzego serwisu. Wszystko pozostałe (`szukaj`, `eksportuj`,
`przelicz`, `pokrycie`, `runy`, `demo`) to **zero żądań**.

- Zgoda właściciela na przebieg masowy obowiązuje **w bieżącej sesji** i nie da się jej zapisać
  w konfiguracji. Flaga to `--zgoda`.
- Bez `--zgoda` narzędzie wyśle najwyżej kilkadziesiąt żądań i samo się zatrzyma.
- Zgoda niesie **górny pułap** wyliczony z wyceny; przekroczenie przerywa przebieg. Nie próbuj go
  obejść ponawianiem polecenia z wyższym `--maks`.
- Nie uruchamiaj `pobierz` „na wszelki wypadek". Najpierw sprawdź `szukaj`, czy tego, czego
  szukasz, nie ma już w korpusie.

## 4. Polecenia

| Polecenie | Po co | Sieć |
|---|---|---|
| `kio-tool szukaj` | Szukanie frazy w pełnym tekście korpusu z filtrami | nie |
| `kio-tool eksportuj` | Wynik do `xlsx`, `csv`, `jsonl` albo `md`, z arkuszem metadanych | nie |
| `kio-tool przelicz` | Ponowny odczyt metadanych i indeksu z surowych wersji | nie |
| `kio-tool pokrycie` | Raport liczbowy o jakości odczytu (sekcje, cytowania, przepisy) | nie |
| `kio-tool runy` | Ostatnie przebiegi: status, zakres, liczba dokumentów i żądań | nie |
| `kio-tool demo` | Ta sama ścieżka nad korpusem fikcyjnym, w osobnym katalogu danych | nie |
| `kio-tool pobierz` | Pobranie orzeczeń według kryteriów do bazy | **tak** |
| `kio-tool wznow` | Dokończenie przerwanego przebiegu, bez duplikatów | **tak** |

Kreator (`kio-tool` bez polecenia) jest dla człowieka — zadaje pytania interaktywnie. Ty używaj
poleceń z flagami.

## 4a. Kod wyjścia mówi, co zrobić dalej

Narzędzie kończy się kodem, który niesie decyzję, a nie tylko „coś poszło źle". Czytaj go, zanim
przeczytasz komunikat.

| Kod | Znaczenie | Co z tym zrobić |
|---|---|---|
| `0` | Wykonane | — |
| `1` | Błąd zwykły, w tym przerwanie przez operatora | Przeczytaj komunikat ze **stderr** i zdecyduj |
| `2` | Przebieg **da się wznowić** | Uruchom `kio-tool wznow` — nie powtarzaj `pobierz`, bo to nowy przebieg |
| `3` | Konfiguracja, uprawnienia albo brak zgody | **Nie ponawiaj.** Poproś operatora — sam tego nie naprawisz |

Komunikaty o błędach idą na **stderr**, wyniki na **stdout**. Strumienie są rozdzielone celowo,
więc możesz czytać wynik bez filtrowania go z ostrzeżeń.

## 4b. Pułapka potoku: bez terminala tabela łamie się na 80 znakach

Wyniki są drukowane jako tabela dla człowieka. Kiedy przekierujesz je do potoku albo do pliku,
biblioteka rysująca nie zna szerokości terminala i **przyjmuje 80 znaków**, po czym łamie wartości
w środku. Zmierzone: identyfikator przebiegu `atlas-5e3048a63b05` rozpada się na trzy wiersze,
a zakres dat na dwa — czyli dokładnie to, czego potrzebujesz do `eksportuj --run-id`, staje się
nie do odczytania.

**Obejście: ustaw `COLUMNS` przed wywołaniem.**

```
COLUMNS=200 kio-tool runy --limit 5
```

Sprawdzone: przy `COLUMNS=200` identyfikatory i daty mieszczą się w jednym wierszu.

**Droga pewniejsza niż parsowanie tabeli.** Tam, gdzie wynik ma być maszynowy, używaj wyjść, które
maszynowe są z założenia:

- `kio-tool eksportuj --format jsonl` — jeden dokument na wiersz, pełne pola, plik na dysku;
- `kio-tool pokrycie` — obok raportu `.md` zapisuje **`.json`** z tymi samymi liczbami.

### Najprościej: JSON Lines

`szukaj`, `runy`, `przelicz` i `pokrycie` przyjmują **`--json`** i wtedy mówią **JSON Lines** — jeden dokument na wiersz,
każdy z polem `rodzaj` (`blok`, `komunikat`, `ostrzezenie`, `blad`). Wartości nie są łamane,
bo nic ich nie rysuje.

```
kio-tool szukaj --fraza "rażąco niska cena" --od 2023-01-01 --json
```

```json
{"rodzaj": "blok", "tytul": "Trafienia dla „rażąco niska cena”",
 "kolumny": ["sygnatura", "data_wydania", "rozstrzygniecie", "fragment",
             "doc_id", "url_zrodla", "cytowanie"],
 "wiersze": [{"sygnatura": "KIO 3810/23", "doc_id": "atlas:kio-3810-23",
              "url_zrodla": "https://orzeczenia.uzp.gov.pl/Home/PdfContent/24485?Kind=KIO",
              "cytowanie": "Wyrok KIO z 2024-01-09, sygn. KIO 3810/23, ...", "...": "..."}],
 "liczby": {"w_korpusie": 443, "zaindeksowanych": 443, "trafien": 39,
             "pokazano": 20, "bez_daty_poza_filtrem": 0},
 "uwagi": ["W korpusie: 443 dokumentów, ..."]}
```

**Każde trafienie w `--json` niesie drogę do źródła** (od 2026-09-22): `doc_id`, `url_zrodla`
(PDF orzeczenia w urzędowej wyszukiwarce UZP) i `cytowanie` — ten sam blok cytowania, który
trafia do eksportu, zbudowany tą samą funkcją. Przekazuj człowiekowi `cytowanie` w całości albo
co najmniej `url_zrodla`: to jest adres, pod którym sprawdzi zdanie u źródła. Pusty `url_zrodla`
znaczy, że kanał adresu nie podał — wtedy `cytowanie` niesie identyfikator kanału; nie zgaduj
adresu. **Puste `url_zrodla` i `cytowanie` naraz** znaczą, że bieżącej wersji tego dokumentu nie
dało się odczytać — trafienie jest prawdziwe, ale źródło trzeba ustalić po `doc_id`. W tabeli dla człowieka tych kolumn nie ma — są tylko w `--json`.

**Czytaj `liczby`, nie `uwagi`.** `uwagi` to zdania dla człowieka i wolno im się zmienić;
`liczby` są kontraktem. Pole `liczby` stoi także przy **zerze trafień** — i tam jest potrzebne
najbardziej, bo odróżnia „nie ma takich orzeczeń" od „nie ma ich w tym, co pobrano".

`eksportuj`, `pobierz`, `wznow` i `demo` wyjścia maszynowego nie mają (sekcja 9); tam tabela jest podglądem
dla człowieka, a materiał do dalszej pracy bierz z eksportu.

## 5. Co da się wyszukać

Te same filtry działają w `szukaj`, `eksportuj` i `pobierz`:

| Flaga | Co robi | Uwaga |
|---|---|---|
| `--fraza` | Szukanie **dosłowne** w pełnym tekście (SQLite FTS5) | w `pobierz` znaczy co innego — patrz pułapka 1 |
| `--od`, `--do` | Zakres dat wydania, `RRRR-MM-DD`, włącznie | dokumenty bez daty wypadają poza filtr i wynik to mówi |
| `--rozstrzygniecie` | `oddalono`, `uwzglednione`, `umorzono`, `odrzucono`, `inne` | można powtórzyć; lista zmierzona na stu rekordach, nieudokumentowana przez kanał |
| `--rodzaj` | `wyrok` albo `postanowienie` | można powtórzyć |
| `--przepis` | Powołanie **w zapisie kanału** (pole opracowania Atlasu), np. `art. 226 ust. 1 pkt 5 Pzp` | dopasowanie po podnapisie — patrz pułapki 2 i 3 |
| `--przewodniczacy` | Podnapis nazwiska przewodniczącego składu | dane osobowe; używaj tylko gdy operator o to prosi |
| `--strona` | Podnapis nazwy odwołującego albo zamawiającego | |
| `--limit` | Ile wierszy pokazać (domyślnie 20) | nie zmienia liczby trafień, tylko widok |
| `--json` | Wynik jako JSON Lines zamiast tabeli | `szukaj`, `runy`, `przelicz`, `pokrycie`; patrz sekcja 4b |

Wynik `szukaj` to tabela `sygnatura · data wydania · rozstrzygnięcie · fragment`, a **nad nią**
liczby: ile jest w korpusie, ile zaindeksowanych, ile trafień i ile pokazano. Czytaj te liczby
i przekazuj je dalej — to jest różnica między „nie ma takich orzeczeń" a „nie ma ich w tym, co
pobrano".

## 6. Pułapki, na których łatwo się przejechać

1. **`--fraza` w `pobierz` to nie to samo co w `szukaj`.** Lokalnie szuka w pełnym tekście;
   w `pobierz` idzie do wyszukiwarki kanału, która u Atlasu **dopasowuje sygnaturę, nie treść**
   (zmierzone 2026-09-18). Chcąc pobrać orzeczenia „o rażąco niskiej cenie", nie podawaj tej frazy
   do `pobierz` — pobierz zakres dat i przeszukaj lokalnie.
2. **`--przepis` dopasowuje zapis, nie znaczenie.** Ten sam przepis bywa w tekście zapisany na
   kilka sposobów. Jeżeli wynik wygląda na za mały, spróbuj krótszego podnapisu (`art. 226 ust. 1`).
3. **Dwa różne spisy przepisów — nie mieszaj ich.** `--przepis` filtruje po liście przepisów,
   którą **podaje kanał** (Atlas). Własny odczyt narzędzia z treści orzeczenia jest osobny:
   widać go w dodatku „Odesłania odczytane z treści" na końcu każdego pliku eksportu `md`
   i w raporcie `pokrycie`. W tym własnym odczycie **33,0 % powołań ma akt „nieustalone"**
   (4 518 z 13 697, raport `pokrycie` z 2026-09-20; w liście kanału — 22,8 %) —
   to nie awaria: tekst nie wskazuje ustawy w sposób rozstrzygalny. Nie interpretuj tego jako
   „przepis spoza Pzp" i nie przenoś tej liczby na wynik `--przepis`, bo ten filtr jej nie dotyczy.
4. **Sygnatury mają wiele postaci.** Narzędzie normalizuje je do `KIO 1234/23`. Część odesłań jest
   w orzeczeniach zapisana bez oznaczenia repertorium (samo `3376/23` za „sygn. akt") i taka
   niesie osobny rodzaj — organ dopisano z kontekstu, nie odczytano z zapisu.
5. **Po zmianie w odczycie trzeba `przelicz`.** Jeżeli `szukaj` mówi, że zaindeksowanych jest
   mniej niż dokumentów w korpusie, uruchom `przelicz` — bez tego część korpusu jest niewidoczna.

## 7. Limity kanału i jak je podnieść

Kanał `atlas` publikuje limity i raportuje je nagłówkami `X-RateLimit-*`:

| | Bez klucza | Z kontem | Ustawienie narzędzia |
|---|---|---|---|
| Na dobę na adres IP | 1 500 | **5 000** | 1 400 |
| Na minutę | 500 | 500 | 450 |
| Odstęp między żądaniami | — | — | 1,0 s |

Narzędzie chodzi **poniżej** limitu dostawcy celowo: limit jest nakładany na adres IP i zużywa go
także ruch spoza narzędzia (druga maszyna, ręczne wywołanie), więc rezerwa jest realna, a nie
ostrożnościowa.

Podniesienie limitu do 5 000/dobę wymaga **konta u dostawcy i klucza API**. Klucz idzie do
zmiennej środowiskowej `KIO_TOOL_ATLAS_KEY` i stamtąd do nagłówka `X-Api-Key`. **Nigdy nie
zapisuj klucza w repozytorium, w poleceniu ani w pliku konfiguracyjnym w drzewie.** Jeżeli klucz
jest potrzebny, poproś operatora, żeby ustawił zmienną — nie ustawiaj jej za niego i nie wypisuj
jej wartości.

Przy 1 s odstępu 443 orzeczenia to około ośmiu minut pracy maszyny. Cała dotychczasowa historia
projektu to 464 żądania.

## 8. Jak odpowiadać na podstawie tego korpusu

- Podawaj **sygnaturę i datę** przy każdym twierdzeniu o orzeczeniu, a najlepiej całe pole
  `cytowanie` z wyniku `--json`. Odbiorca musi móc sprawdzić je u źródła, a `url_zrodla`
  prowadzi wprost do PDF-a w wyszukiwarce UZP.
- Podawaj **liczbę trafień i wielkość korpusu**, nie samo „znalazłem". „7 z 443 pobranych
  orzeczeń" to informacja; „znalazłem 7" to jej połowa.
- Kiedy filtr nic nie zwrócił, powiedz **który** filtr mógł być za wąski, zamiast odpowiadać
  „brak orzeczeń w tej sprawie".
- Nie cytuj długich fragmentów uzasadnień do plików i wiadomości. Korpus zawiera dane osobowe,
  a treść orzeczeń świadomie nie trafia do repozytorium.
- Nie zgaduj tam, gdzie narzędzie mówi „nieustalone". Przekaż tę wartość taką, jaka jest.

---

## 9. Czego temu narzędziu brakuje z Twojego punktu widzenia (stan 2026-09-20)

Zapisane tutaj, żebyś nie szukał czegoś, czego nie ma, i nie zakładał, że źle wołasz polecenie.

- **`--json` mają `szukaj`, `runy`, `przelicz` i `pokrycie`.** Nie ma go `eksportuj` (zapisuje
  plik, więc go nie potrzebuje) ani `pobierz`/`wznow` — te mówią do człowieka w trakcie długiego
  przebiegu.
- **Brak serwera, przez który sięgałbyś do korpusu narzędziami zamiast powłoką.** Taki jest
  kształt etapu czwartego (`docs/ARCHITEKTURA_KIO_TOOL.md` §3.8), który stoi za bramką zgodności.
- **Kolumna `fragment` w wyniku `szukaj` jest przycięta pod ekran** i nie ma flagi, która by ją
  poszerzyła. Po szerszy kontekst idź eksportem — `eksportuj --format md` daje od 2026-09-22
  tekst podzielony nagłówkami sekcji (Nagłówek, Sentencja, Pouczenie, Uzasadnienie, Zdanie
  odrębne), więc odczyt narzędzia wskazuje, czy zdanie należy do rozstrzygnięcia Izby, czy do
  jej uzasadnienia. Granice wyznacza heurystyka, a nagłówków **nie ma w orzeczeniu** — cytując,
  nie przenoś ich do cytatu. Eksport `md` całego korpusu trwa ok. 30 s (struktura liczona przy
  zapisie).
- **Fragment nie mówi, z której sekcji pochodzi.** Zdanie w uzasadnieniu bywa przytoczeniem
  stanowiska strony, nie poglądem Izby. Zanim przypiszesz je Izbie, sprawdź kontekst w `md`.
- **Nie ma polecenia „pokaż jedno orzeczenie".** Pełny tekst jednego dokumentu daje eksport
  z frazą, która go wyróżnia (np. jego sygnaturą: `eksportuj --fraza "KIO 3810/23" --format md`).
  Fraza szuka w treści, więc trafią **także orzeczenia, które tę sygnaturę cytują** — właściwy
  plik rozpoznasz po sygnaturze w `INDEX.md`.
- **Nie ma trybu „tylko policz".** Żeby poznać liczbę trafień, wołasz `szukaj --json --limit 1`
  i czytasz `liczby.trafien`; `--limit 0` kończy się kodem 3 (limit ma być dodatni).

Żadna z tych rzeczy nie blokuje pracy — wszystkie mają obejście opisane wyżej. Ale jeśli operator
pyta, czy narzędzie jest „gotowe pod agenta", odpowiedź brzmi: **budowa i zasady tak, kanał
wyjścia jeszcze nie**.
