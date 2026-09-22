---
name: kio-tool
description: Obsługa lokalnego korpusu orzeczeń Krajowej Izby Odwoławczej (kio-tool) — wyszukiwanie w orzecznictwie KIO, czytanie orzeczenia po sygnaturze („KIO 3810/23”), cytowanie ze źródłem, pobieranie nowych orzeczeń za zgodą operatora. Używaj, gdy pytanie dotyczy orzeczeń KIO, zamówień publicznych, Pzp, sygnatur KIO albo tego, jak Izba orzeka w danej sprawie.
---

# kio-tool — procedura wejścia

Narzędzie uruchamiasz z katalogu repozytorium jako `.venv\Scripts\kio-tool.exe`, zawsze
z `--json`. Rozumowanie jest Twoje; narzędzie daje materiał i mówi, czego nie objęło.

1. **Zanim zaczniesz, przeczytaj `docs/dla-modelu.md`** — zasady nadrzędne, granice korpusu
   i pułapki. Ten plik ich nie powtarza, żeby się z nimi nie rozjechać.
2. **Flag nie zgaduj.** `kio-tool opis --json` oddaje polecenia, flagi, wartości dozwolone
   i kody wyjścia prosto z narzędzia.
3. **Kolejność pracy:**
   - `szukaj --fraza "…" --json` — trafienia z `doc_id`, `cytowanie` i liczbami
     (`liczby.trafien` z `liczby.w_korpusie`);
   - `czytaj <sygnatura|doc_id> --bez-tresci --json` — mapa sekcji z długościami;
   - `czytaj … --sekcja sentencja --json` (albo `uzasadnienie`) — tylko potrzebny tekst;
   - w odpowiedzi: sygnatura, data i pole `cytowanie` w całości; „N z M”, nigdy „wszystkie”.
4. **Sieć tylko za zgodą operatora.** Brakuje materiału → `pobierz … --wycena --json`
   (jedno żądanie), pokaż operatorowi liczby z bloku „Koszt przebiegu” i zapytaj. `--zgoda`
   dodajesz wyłącznie po jego wyraźnym „tak” w tej sesji; nie obchodź progu przez `--maks`.
5. **Kod wyjścia czytaj przed komunikatem.** 3 znaczy: nie ponawiaj, zapytaj operatora;
   2 przy przebiegu: `wznow`, nie ponowne `pobierz`.
