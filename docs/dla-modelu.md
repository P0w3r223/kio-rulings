# kio-tool — wytyczne dla modelu, który obsługuje to narzędzie

Data: 2026-09-20
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

## 5. Co da się wyszukać

Te same filtry działają w `szukaj`, `eksportuj` i `pobierz`:

| Flaga | Co robi | Uwaga |
|---|---|---|
| `--fraza` | Szukanie **dosłowne** w pełnym tekście (SQLite FTS5) | w `pobierz` znaczy co innego — patrz pułapka 1 |
| `--od`, `--do` | Zakres dat wydania, `RRRR-MM-DD`, włącznie | dokumenty bez daty wypadają poza filtr i wynik to mówi |
| `--rozstrzygniecie` | `oddalono`, `uwzglednione`, `umorzono`, `odrzucono`, `inne` | można powtórzyć; lista zmierzona na stu rekordach, nieudokumentowana przez kanał |
| `--rodzaj` | `wyrok` albo `postanowienie` | można powtórzyć |
| `--przepis` | Powołanie w zapisie kanału, np. `art. 226 ust. 1 pkt 5 Pzp` | dopasowanie po podnapisie — patrz pułapka 2 |
| `--przewodniczacy` | Podnapis nazwiska przewodniczącego składu | dane osobowe; używaj tylko gdy operator o to prosi |
| `--strona` | Podnapis nazwy odwołującego albo zamawiającego | |
| `--limit` | Ile wierszy pokazać (domyślnie 20) | nie zmienia liczby trafień, tylko widok |

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
3. **31 % powołań na przepisy ma akt „nieustalone".** To nie awaria: tekst nie wskazuje ustawy
   w sposób rozstrzygalny. Nie interpretuj tego jako „przepis spoza Pzp".
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

- Podawaj **sygnaturę i datę** przy każdym twierdzeniu o orzeczeniu. Odbiorca musi móc sprawdzić
  je u źródła.
- Podawaj **liczbę trafień i wielkość korpusu**, nie samo „znalazłem". „7 z 443 pobranych
  orzeczeń" to informacja; „znalazłem 7" to jej połowa.
- Kiedy filtr nic nie zwrócił, powiedz **który** filtr mógł być za wąski, zamiast odpowiadać
  „brak orzeczeń w tej sprawie".
- Nie cytuj długich fragmentów uzasadnień do plików i wiadomości. Korpus zawiera dane osobowe,
  a treść orzeczeń świadomie nie trafia do repozytorium.
- Nie zgaduj tam, gdzie narzędzie mówi „nieustalone". Przekaż tę wartość taką, jaka jest.
