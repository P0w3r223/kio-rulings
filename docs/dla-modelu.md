# kio-tool — instrukcja dla modelu obsługującego narzędzie

Data: 2026-09-22 · Odbiorca: agent prowadzący `kio-tool` w imieniu operatora.
Zmiana flagi albo polecenia w narzędziu jest zmianą tego pliku.

## Czym jest

Lokalny korpus orzeczeń Krajowej Izby Odwoławczej z pełnym tekstem, pobrany z kanału `atlas`
(Atlas Przetargów). Wyszukiwanie i eksport działają **bez sieci**. W narzędziu nie ma modelu —
rozumowanie jest Twoje, narzędzie daje materiał i mówi, czego nie objęło.

## Zasady nadrzędne

1. **Sieć tylko ze zgodą.** `pobierz` i `wznow` wysyłają żądania do cudzego serwisu. Przebieg
   powyżej 50 żądań wymaga `--zgoda`, a tę może dać wyłącznie operator w bieżącej sesji. Nie
   dodawaj `--zgoda` sam, nie obchodź progu podnoszeniem `--maks` ani ponawianiem polecenia.
   Najpierw sprawdź `szukaj`, czy materiału nie ma już w korpusie.
2. **Każde twierdzenie z orzeczenia podpieraj źródłem** — sygnaturą, datą i najlepiej polem
   `cytowanie` z wyniku. Podawaj liczbę trafień i wielkość korpusu („7 z 443”), nie samo
   „znalazłem”.
3. **Nie oceniaj sprawy prawnie** i nie zgaduj tam, gdzie narzędzie mówi „nieustalone”.
4. **Dane osobowe:** skład orzekający i protokolant są w treści z imienia i nazwiska. Nie
   przepisuj ich ani długich fragmentów uzasadnień do odpowiedzi i plików bez potrzeby.
5. **Nie ustawiaj zmiennych środowiskowych i nie wypisuj ich wartości** (`KIO_TOOL_CONTACT`,
   `KIO_TOOL_ATLAS_KEY`). Brak — poproś operatora.

## Granice korpusu — mów o nich, zamiast oddawać niepełny wynik jako pełny

- Tylko roczniki **2010–2026**; Izba orzeka od grudnia 2007, ale kanał zaczyna się w 2010.
- Kompletność nie jest znana: mów „N pobranych orzeczeń”, nigdy „wszystkie orzeczenia”.
- Korpus operatora to próbka (sprawdź `runy` albo `liczby.w_korpusie`), nie cały zbiór
  pośrednika (29 580 orzeczeń).

## Polecenia

| Polecenie | Po co | Sieć | `--json` |
|---|---|---|---|
| `szukaj --fraza "…"` | fraza dosłownie w pełnym tekście, z filtrami | nie | tak |
| `czytaj <sygnatura\|doc_id>` | jedno orzeczenie: metadane, cytowanie, mapa sekcji, treść (`--sekcja`, `--bez-tresci`) | nie | tak |
| `eksportuj` | pliki `xlsx`, `csv`, `jsonl`, `md` (`--format`, `--out`) | nie | — |
| `runy` | ostatnie przebiegi: status, zakres, liczby (`--status`, `--limit`) | nie | tak |
| `przelicz` | ponowny odczyt z zapisanych bajtów (`--wszystko`) | nie | tak |
| `pokrycie` | raport jakości odczytu (`--cel`, `--zloty tests/gold`) | nie | tak |
| `pobierz` | pobranie według kryteriów (`--maks`, `--zgoda`); na końcu eksport | **tak** | — |
| `wznow` | dokończenie przerwanego przebiegu (`--run-id`) | **tak** | — |

Wywołuj polecenia z flagami; `kio-tool` bez polecenia to kreator dla człowieka. `--baza`
wskazuje inny plik bazy.

**Filtry** (te same w `szukaj`, `eksportuj`, `pobierz`): `--od`/`--do` (RRRR-MM-DD,
włącznie), `--rozstrzygniecie` (oddalono, uwzglednione, umorzono, odrzucono, inne; można
powtórzyć), `--rodzaj` (wyrok, postanowienie), `--przepis`, `--przewodniczacy`, `--strona`
(podnapisy). `szukaj --limit N` zmienia tylko liczbę pokazanych wierszy (domyślnie 20, musi być
dodatni).

## Wynik maszynowy

Z `--json` wyjście to JSON Lines: jeden obiekt na wiersz z polem `rodzaj` (`blok`, `komunikat`,
`ostrzezenie`, `blad`). Wynikiem jest ostatni `blok`.

```
kio-tool szukaj --fraza "rażąco niska cena" --od 2023-01-01 --json
```

- `liczby` — kontrakt: `w_korpusie`, `zaindeksowanych`, `trafien`, `pokazano`,
  `bez_daty_poza_filtrem`. Czytaj je, nie `uwagi` (to proza dla człowieka).
- `wiersze[]` w `szukaj`: `sygnatura`, `data_wydania`, `rozstrzygniecie`, `fragment`, `doc_id`,
  `url_zrodla` (PDF w wyszukiwarce UZP), `cytowanie` (gotowy blok cytowania — przekazuj go
  w całości). Puste `url_zrodla` i `cytowanie` naraz: wersji nie dało się odczytać, trafienie
  jest prawdziwe, źródło ustal po `doc_id`.
- Liczbę trafień bez listy daje `szukaj … --json --limit 1`.
- Bez `--json` tabela w potoku łamie wartości na 80 znakach — nie parsuj jej.

### Jedno orzeczenie: `czytaj`

```
kio-tool czytaj "KIO 3810/23" --bez-tresci --json        # mapa sekcji z długościami
kio-tool czytaj "KIO 3810/23" --sekcja sentencja --json  # tylko rozstrzygnięcie
kio-tool czytaj atlas:kio-3810-23 --json                 # całość
```

Najpierw `--bez-tresci`: uzasadnienie ma średnio ok. 29 tys. znaków, sentencja ok. 800 —
bierz do kontekstu tylko to, czego potrzebujesz. Sekcje: `naglowek`, `sentencja`, `pouczenie`,
`uzasadnienie`, `zdanie_odrebne`, `nieprzypisane` (tekst między rozpoznanymi sekcjami);
`--sekcja` można powtórzyć.

- Wynik: `wiersze[0]` (`sygnatura`, `data_wydania`, `rodzaj`, `rozstrzygniecie`, `doc_id`,
  `url_zrodla`, `wersja`, `cytowanie`) i `odcinki[]` — każdy z `rodzaj`, `start`, `koniec`,
  `znakow`, a `tresc` tylko przy wybranych. Odcinki pokrywają treść w całości i po kolei.
- `liczby`: `znakow_calosci`, `znakow` (oddanych), `odcinkow`, `pokazano`.
- Sygnaturę podaj w dowolnej pisowni („kio 3810 / 23”); porównywana jest z sygnaturami
  dokumentu, nie szukana w treści. Kilka dokumentów pod jedną sygnaturą (wyrok i postanowienie)
  → kod 3 z listą `doc_id`; wybierz jeden i wywołaj ponownie.
- Nazwy sekcji wyznacza odczyt automatyczny — nie ma ich w orzeczeniu, nie przenoś ich do
  cytatu. Spis cytowanych orzeczeń i przepisów jest w eksporcie `md`.

## Kody wyjścia (czytaj przed komunikatem; błędy idą na stderr)

| Kod | Znaczenie | Co zrobić |
|---|---|---|
| 0 | wykonane | — |
| 1 | błąd zwykły | przeczytaj stderr |
| 2 | przebieg da się wznowić **albo** błąd składni polecenia (literówka we fladze) | przy przebiegu: `wznow` (nie ponownie `pobierz`); przy składni: popraw wywołanie |
| 3 | konfiguracja, brak zgody, zła ścieżka lub parametr | nie ponawiaj — zapytaj operatora |
| 130 | przerwane przez Ctrl+C | — |

## Pułapki

1. **`--fraza` w `pobierz` szuka po sygnaturze**, nie w treści (tak działa wyszukiwarka
   kanału). Chcąc orzeczeń „o X”: pobierz zakres dat, potem `szukaj` lokalnie.
2. **`--przepis` dopasowuje zapis z listy kanału**, podnapisem. Za mało trafień → krótszy zapis
   (`art. 226 ust. 1`). Własny odczyt przepisów z treści jest w pliku `md`; 33 % powołań ma tam
   akt „nieustalone” — to nie znaczy „spoza Pzp”.
3. **Fragment nie mówi, z której części orzeczenia pochodzi.** Zdanie w uzasadnieniu bywa
   stanowiskiem strony, nie Izby — sprawdź kontekst przez `czytaj`, zanim przypiszesz je Izbie.
4. **`zaindeksowanych` < `w_korpusie`** → uruchom `przelicz`, inaczej część korpusu jest
   niewidoczna.
5. **Filtr dat pomija dokumenty bez daty wydania**; ich liczba to `bez_daty_poza_filtrem`.
   Data u pośrednika bywa też błędna.
6. **Sygnatury są normalizowane** do postaci `KIO 1234/23`; wyszukiwanie ignoruje ogonki poza
   `ł` („lodz” nie trafi „Łódź”).
