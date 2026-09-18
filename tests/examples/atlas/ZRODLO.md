# Złote pliki kanału `atlas` — pochodzenie, licencja, skróty

Data odczytu: 2026-09-18 (sonda fazy 0, `sonda-20260918T103525Z`, poziom anonimowy, 2 żądania)
Status: przejrzane okiem przed zapisem (reguła 17); **bajty surowe, nie edytować**
Autor odczytu: Claude na polecenie właściciela
Related to: `docs/decisions.md` (`## Pomiar 3a`, `## Pomiar 23`), `docs/adr/0004_wybor_kanalu.md` (sekcja 4), `docs/adr/0005_bramka_per_kanal.md` (Z-6)

---

## Pliki

| Plik | Żądanie | Bajtów | SHA-256 |
|---|---|---|---|
| `lista_20260918T103525Z.json` | `GET https://atlasprzetargow.pl/api/kio?per_page=100&page=1&sort=oldest` | 91 447 | `0034a634ca2c98f94dbd0cb68ef3aba2ad16abfa27ed5f1485953e01470feec0` |
| `dokument_20260918T103526Z.json` | `GET https://atlasprzetargow.pl/api/kio/kio-1205-20` | 8 963 | `d29338bd88146731dc2e06271a407cecf595e5b616ea4bc7d88055faab5c574e` |

Obok każdego pliku stoi `*.compare.json` z tym, co adapter ma z niego wyczytać. Pliki
przeniesiono ze `scripts/out/` bez zmiany bajtów (skróty policzone `sha256sum` 2026-09-18
zgadzają się z wierszami w `docs/dziennik_zadan.md`).

## Licencja i atrybucja

Dane Atlasu Przetargów są na licencji **CC BY 4.0** z wymaganą atrybucją — odczytane
u dostawcy 2026-09-18 ze strony `https://atlasprzetargow.pl/dokumentacja-api` (SHA-256 strony
`79b1e0562002cc37edbd19fdc0b88b89b5da9e2d98a3635b4316b3d60d497f48`, „Ostatnia aktualizacja:
10 września 2026"), pomiar 23:

> Źródło: Atlas Przetargów (https://atlasprzetargow.pl)

Strona rozróżnia dane źródłowe (orzeczenia KIO jako informacja publiczna) od opracowania
Atlasu (normalizacja, powiązania, profile, agregaty) objętego licencją. Pola opracowania
w rekordzie dokumentu: `related_by_entity`, `similar_rulings`, `cited_by`, `cites`,
`related_tenders`, `thesis`, `thesis_snippet`.

## Co te pliki niosą i co z tego wynika

- **Dane osobowe, policzone 2026-09-18 z bajtów, nie z pamięci.** Rekord dokumentu niesie
  nazwisko przewodniczącej składu (`chairperson`) i nazwy stron (`appellant_raw`,
  `procuring_entity_raw`). Plik listy niesie **100 rekordów**, a w nich pola `chairperson`
  (niepuste w 87), `panel` (31), `protocolant` (93) — razem **47 różnych osób** (skład
  orzekający i protokolanci) oraz 111 różnych nazw stron postępowań — tak, jak publikuje je
  Izba i pośrednik. `README.md` mówi, że korpus nie wchodzi do repozytorium z powodu nazwisk
  składu i protokolantów; reguła 17 wymaga złotego pliku z bajtami surowymi (redakcja odpada),
  ale nie wymaga stu rekordów — krótsza strona listy (nowy odczyt, nowy SHA-256, nowa data)
  dałaby to samo przy stukrotnie mniejszej ekspozycji. **Decyzja o commicie tego katalogu, i o
  tym, czy zastąpić listę krótszą stroną, należy do właściciela** — po commicie historia
  repozytorium jest nieodwracalna (przegląd kodu 2026-09-18).
- `ruling_date` pierwszego rekordu (2004-01-29) jest niezgodne z treścią (postanowienie
  z 16 czerwca 2020 r., `hearing_date` 2020-06-16) — zmierzony przykład błędu cudzego potoku
  z PDF; adapter nie ma prawa „poprawiać" tej wartości przed zapisem (reguła 19 w brzmieniu
  ADR-0005 Z-5).
- Ten dokument nie niesie `thesis`; plik z tezą od modelu, gdy się trafi, nie wchodzi do korpusu
  poza surowymi bajtami (`pola_odrzucone` w `contract.yaml`).
