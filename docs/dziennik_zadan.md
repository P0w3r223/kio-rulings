# Dziennik żądań

Data utworzenia: 2026-09-18
Status: żywy — dopisywany przez `scripts/sonda.py` przy każdym przebiegu, nigdy przepisywany
Autor: narzędzie (wpisy maszynowe)
Related to: `ARCHITEKTURA_KIO_TOOL.md` (4.1 reguła zgody, 4.4 `requests_log`), `decisions.md`

---

Reguła zgody mówi, że pojedynczy odczyt diagnostyczny nie wymaga zgody właściciela, ale
**zawsze zostawia wpis w dzienniku**. Dopóki nie ma bazy, dziennikiem jest ten plik; kolumny
są kolumnami `requests_log` z modelu danych (4.4), z dwiema dodanymi: `sha256` wiąże wiersz
z bajtami odpowiedzi w `scripts/out/` (katalog spoza historii), a `kształt` niesie ocenę
z reguły 17 — status 200 przy kształcie niezgodnym to jest właśnie ten przypadek, dla
którego reguła istnieje.

Adres przechodzi przez `mask_tokens`, bo `requests_log` trzyma `url_redacted`, nie `url`.

**Kolumna `adres` niesie punkt końcowy bez parametrów zapytania** i to jest granica, nie
przeoczenie: dwa żądania różniące się wyłącznie parametrami dają w tej tabeli dwa wiersze
nie do odróżnienia. Widać to na pomiarze 2a, który celowo wysyła to samo żądanie w dwóch
sprzecznych pisowniach parametru dat. Znaczenie praktyczne ma to dziś w jednym miejscu —
odczyt wstecz pomiaru 19 dopasowuje wiersze po tej kolumnie — a tam adres jest niepowtarzalny
(`ContentHtml/18946`). Gdy przestanie być, kolumna musi dostać parametry, a nie dopasowanie
dodatkowe kryterium: dziennik ma mówić, co naprawdę poszło.

Wiersz powstaje w chwili powrotu żądania, a nie po całym pomiarze: przerwany przebieg ma
zostawić ślad po tym, co **już** poszło do cudzego serwisu.

Pomiar, który nie został wysłany (bo grupa stanęła po odmowie), ma w kolumnie `metoda`
przedrostek `nie:` i nie liczy się do „N żądań" w `decisions.md`.

---

## Wpisy ręczne

Nie każde żądanie tego projektu wychodzi przez sondę, a reguła mówi „**każdy** pojedynczy
odczyt zostawia wpis". Przegląd z 2026-09-14 wysłał około trzydziestu żądań i zapisał je
w tabeli w `ARCHITEKTURA_KIO_TOOL.md` (sekcja 7); pomiar 1 poszedł `curl`-em, bo reguła 11
zabrania budowania konstruktu FTP w drzewie; weryfikacja adresu urzędu przed wysłaniem pisma
będzie takim samym odczytem. Wpisów maszynowych po nich nie ma i nie będzie.

Wiersz dopisuje się tutaj **ręką**, w tych samych kolumnach co niżej, z `run_id` w postaci
`recznie-RRRRMMDD`. Kolumny, których przy odczycie ręcznym nie da się wypełnić, dostają „—";
kolumna `sha256` zostaje pusta, jeśli bajtów nikt nie zachował — i to jest informacja o wadze
dowodu, nie brak do uzupełnienia.

| run_id | ts | metoda | adres | status | ms | bajty | sha256 | kształt |
|---|---|---|---|---|---|---|---|---|
| recznie-20260915 | 2026-09-15 | FTP | `ftp://ftp.uzp.gov.pl/` | — | ~21000 | 0 | — | — (pomiar 1, `curl`, limit 20 s: przekroczenie czasu) |
| recznie-20260915 | 2026-09-15 | FTP | `ftp://ftp.uzp.gov.pl/` | — | ~21000 | 0 | — | — (pomiar 1, `curl`, limit 25 s: przekroczenie czasu) |
| recznie-20260915 | 2026-09-15 | FTP | `ftp://ftp.uzp.gov.pl/` | — | ~21000 | 0 | — | — (pomiar 1, `curl`, limit 60 s: przekroczenie czasu) |
| recznie-20260915 | 2026-09-15 | FTP | `ftp://ftp.gnu.org/` | 226 | ~1500 | — | — | — (pomiar 1, kontrola z tej samej maszyny) |
| recznie-20260915 | 2026-09-15 | GET | `https://orzeczenia.uzp.gov.pl/` | 200 | ~4600 | — | — | — (pomiar 1, kontrola łączności do domeny) |
| recznie-20260915 | 2026-09-15 | GET | `https://orzeczenia.uzp.gov.pl/` | 200 | — | 28064 | — | — (pomiar 14, odczyt w surowych bajtach, zero markerów) |
| recznie-20260915 | 2026-09-15 | GET | `https://www.gov.pl/` | 200 | — | — | — | — (pomiar 14) |
| recznie-20260915 | 2026-09-15 | GET | `https://www.gov.pl/web/gov/warunki-korzystania` | 200 | — | — | — | — (pomiar 14) |
| recznie-20260915 | 2026-09-15 | GET | `https://www.gov.pl/web/gov/prawa-autorskie` | 200 | — | — | — | — (pomiar 14) |

Wiersze za pomiary 1 i 14 dopisane 2026-09-18 z `docs/decisions.md` (liczby i statusy stamtąd;
czasy przybliżone, skróty bajtów niezachowane — i to jest informacja o wadze tamtych dowodów).
Około trzydziestu żądań przeglądu z 2026-09-14 stoi w tabeli `ARCHITEKTURA_KIO_TOOL.md` sekcja 7
i nie jest tu przepisywane.

---

## Wpisy maszynowe

Dopisywane przez `scripts/sonda.py` na końcu pliku. Tabela rośnie w dół i nie jest sortowana.

| run_id | ts | metoda | adres | status | ms | bajty | sha256 | kształt |
|---|---|---|---|---|---|---|---|---|
| sonda-20260918T103525Z | 2026-09-18T10:35:25Z | GET | `https://atlasprzetargow.pl/api/kio` | 200 | 219 | 91447 | `0034a634ca2c98f9` | zgodny |
| sonda-20260918T103525Z | 2026-09-18T10:35:25Z | GET | `https://atlasprzetargow.pl/api/kio/kio-1205-20` | 200 | 78 | 8963 | `d29338bd88146731` | zgodny |
| sonda-20260918T103544Z | 2026-09-18T10:35:44Z | GET | `https://www.saos.org.pl/` | — | 45312 | 0 | `—` | — |
| sonda-20260918T103544Z | 2026-09-18T10:35:44Z | GET | `https://atlasprzetargow.pl/` | 200 | 203 | 331340 | `b9d462c80d050c2a` | — |
| sonda-20260918T103544Z | 2026-09-18T10:35:44Z | GET | `https://atlasprzetargow.pl/dokumentacja-api` | 200 | 94 | 298377 | `79b1e0562002cc37` | — |
