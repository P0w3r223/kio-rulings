# Kontrakt wyjścia `--json`: kody błędów i wersja kontraktu

Date: 2026-09-22
Status: draft
Author: P0w3r223
Related to: `kio_tool/ui/maszynowo.py`, `docs/dla-modelu.md` (kody wyjścia)

---

## Problem

Wyjście maszynowe jest dobrze pomyślane (JSON Lines, `rodzaj`, `liczby` jako kontrakt, błędy na
stderr), ale ma dwie luki, które agent odczuwa:

1. **Błąd to sama proza.** `{"rodzaj": "blad", "tresc": "…"}`. Kod wyjścia 3 mówi „nie ponawiaj,
   zapytaj operatora”, ale nie mówi, *o co* zapytać: brak `KIO_TOOL_CONTACT`, brak zgody, zła
   data, nieznana sygnatura i nieistniejąca baza to ten sam kod 3. Agent rozróżnia je dziś,
   czytając polskie zdania, a zdania się zmieniają.
2. **Brak wersji.** Zmiana nazwy klucza w `wiersze` albo `liczby` jest niewidoczna dla
   konsumenta, dopóki coś się nie wyłoży.

## Jak to sobie wyobrażam

**Pole `kod` w każdym `blad` i `ostrzezenie`.** Stały, krótki identyfikator ASCII:

```json
{"rodzaj": "blad", "kod": "brak_zgody", "tresc": "…", "wersja_kontraktu": 1}
```

Zestaw startowy z istniejących ścieżek: `brak_kontaktu`, `brak_zgody`, `poza_wycena`,
`zly_parametr`, `brak_bazy`, `baza_pokazowa`, `nieznany_dokument`, `przebieg_do_wznowienia`,
`zabezpieczenie_serwisu` (CAPTCHA/blokada), `blad_sieci`, `blad_odczytu`. Kody niesie klasa
wyjątku (atrybut), nie tekst — `_obsluga_bledow` w `cli.py` tylko go przepisuje. Tabela kodów
w `dla-modelu.md` obok kodów wyjścia i w `opis --json`.

Strażnik: każda klasa w `errors.py` ma kod; każdy kod z `errors.py` jest w `dla-modelu.md`;
mutacja (usunięcie kodu z jednej klasy) zapala test.

**`wersja_kontraktu` w każdej linii.** Liczba całkowita, podnoszona przy zmianie łamiącej
(usunięty lub przemianowany klucz, zmiana typu). Dodanie klucza nie łamie. Strażnik na wzór
`tests/test_wersja_odczytu.py`: odcisk zbioru kluczy każdego bloku maszynowego; zmiana odcisku
bez podniesienia wersji zapala test.

## Czego nie zmieniać

- `uwagi` zostają prozą dla człowieka — instrukcja już mówi, żeby ich nie parsować.
- `kolumny` obok obiektów w `wiersze` wyglądają na dublowanie, ale niosą kolejność kolumn;
  zostają.
- Linia atrybucji w każdym `cytowanie` powtarza się przy każdym trafieniu — kosztuje kilkadziesiąt
  znaków na wiersz i jest wymogiem CC BY 4.0 dla każdego cytatu osobno. Zostaje.

## Koszt

Mały: `errors.py`, `ui/maszynowo.py`, `cli._obsluga_bledow`, dwa strażniki, `dla-modelu.md`.
Naturalnie dołącza do planu pkt 6 (`opis --json`), jeśli ma powstać razem z nim — tam kody błędów
i wersja kontraktu są częścią opisu narzędzia.
