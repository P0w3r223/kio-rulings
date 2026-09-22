# ADR-0009: `store` i `pipeline` jako pakiety — fasada z jawną powierzchnią, reguły granic przepięte z pliku na pakiet bez utraty ostrości

Data: 2026-09-22
Status: accepted (2026-09-22, decyzja właściciela; razem z nowym brzmieniem slajdu „Granice")
Autor: P0w3r223
Related to: `docs/decisions.md` („Świadomie odłożone", O-5; „Domknięcie projektu przed prezentacją", decyzja 3 — **zastąpiona przez ten ADR**), `docs/AUDYT_KIO_ORZECZENIA.md` (8.3 reguły 2–5, 8, 13), `docs/ARCHITEKTURA_KIO_TOOL.md` (4.2), `docs/adr/0001_tozsamosc_dokumentu.md`, `docs/adr/0003_ksztalt_source_i_bramka_wyjscia.md` (§4 reguła 2), `kio_tool/store/`, `kio_tool/pipeline/`, `tests/test_boundaries.py`, `tests/test_bramki_faz.py`, `tests/test_ratelimit.py`, `tests/test_piaskownica.py`, `tests/wsparcie_sondy.py`, `tests/test_fasady.py`

---

## 1. Kontekst

Zmierzone na `master` `c1ed572` (2026-09-22, zero żądań): `kio_tool/store.py` 1 466 linii, z czego
sama klasa `Store` 879 (28 metod nad jednym `_Polaczenie`); `kio_tool/pipeline.py` 921 linii,
z czego pozyskanie (jedyne miejsce łączące `source` ze `store`, transakcja strony) to linie
256–710, a eksport, przeliczenie i wyszukiwanie (tylko `store`) — 712–921. Sufit projektu to 800
linii; `PONAD_SUFITEM` trzymał oba pliki z zakazem wzrostu (O-5).

Decyzja 3 z 2026-09-20 zostawiała O-5 jako dług z powodu ryzyka regresu przed oddaniem.
Właściciel 2026-09-22 postanowił zamknąć O-5 przed prezentacją. Ten ADR zastępuje decyzję 3.

Ograniczenia twarde: zero zmiany zachowania; żadnego nowego wpisu na listach wyjątków testów
granic; ~3 h pracy z istniejącą suitą jako siatką; commity lokalne.

## 2. Co pęka przy rozbiciu naiwnym

| Strażnik | Po przeniesieniu kodu bez dotykania testów | Awaria |
|---|---|---|
| reguły 3 i 4 (`istniejace("kio_tool/store.py")`) | skan pusty → zielono | **cicha** |
| metatest `REGULY` dla reguł 3 i 4 | właściciel znika, reguła wygląda jak w stanie wyzwalacza | **cicha** |
| blokada bez dzierżawy (`test_ratelimit.py`, `if store.exists()`) | nic nie jest sprawdzane | **cicha** |
| bramka ADR-0001 (`test_bramki_faz.py`) | patrzy na ścieżkę, której nie ma | cicha |
| reguła 5 (`obaj == {"kio_tool/pipeline.py"}`) | inna ścieżka | głośna |
| `build_http_client` podstawiany na module `pipeline` | fasada z tą nazwą → podstawienie trafia w fasadę, `pobierz` czyta własne globale | **cicha** przy złej fasadzie |
| fabryka zabroniona w testach operacji bez sieci | pilnuje tylko jednego modułu | **cicha** (zawężenie) |

Pięć awarii jest cichych bezwarunkowo, dwie — przy źle zaprojektowanej fasadzie. Ten ADR istnieje
głównie dla nich: głośne naprawi każdy, kto uruchomi suitę; ciche przeszłyby przez zieloną.

## 3. Warianty

- **W0 — nie rozbijać** (decyzja 3). Zero ryzyka, O-5 otwarte. Zostaje wariantem odwrotu
  w punkcie kontrolnym planu.
- **W1 — pakiety z fasadą, `Store` złożony z klas cząstkowych nad wspólnym rdzeniem** (przyjęty).
  Kod przenoszony dosłownie; wywołania `store.<metoda>` i podstawienia na instancji bez zmian.
  Cena: jeden poziom dziedziczenia zamiast kompozycji; `git log --follow` nie przejdzie przez
  rozbicie (historię niesie `git blame -C -C -C`).
- **W2 — `Store` deleguje do funkcji modułowych.** Kompozycja, ale każda z 28 metod dostaje dwie
  kopie sygnatury; nie mieści się pewnie w 3 h.
- **W3 — pakiety bez fasady.** Dotyka siedmiu plików produkcyjnych, w tym `odczyt.py` z odcisku
  `PARSE_VERSION`; łamie ograniczenie „powierzchnia zostaje". Odrzucony.

## 4. Decyzja

### Z-1. `kio_tool/store/`

| Moduł | Treść |
|---|---|
| `__init__.py` | fasada (Z-3) |
| `model.py` | statusy przebiegu, klasy danych (`Przebieg`, `Metryka`, wiersze struktury, `Filtr`, `Dokument`, `Trafienie`, `Wyszukanie`) |
| `schemat.py` | `SCHEMA_VERSION`, `ID_BAZY_POKAZOWEJ`, `TABELE`, DDL `_SCHEMA`, historia schematów |
| `polaczenie.py` | `_Polaczenie`, `blad_bazy`, `_Rdzen` (`transakcja`, `count`) |
| `zapis.py` | `_ZapisKorpusu(_Rdzen)`: dokumenty, wersje, indeks, struktura |
| `wyszukiwanie.py` | `_Wyszukiwanie(_Rdzen)`: przegląd dokumentów, FTS, struktury; pomocnicze SQL filtrów |
| `przebiegi.py` | `_Przebiegi(_Rdzen)`: przebiegi i dziennik żądań |
| `magazyn.py` | `class Store(_ZapisKorpusu, _Wyszukiwanie, _Przebiegi)`: otwarcie, tryb, migracje |

Nazwy z podkreślnikiem mogą przechodzić między modułami pakietu — to prywatność pakietu. Nazwy
podmodułów **nie powtarzają** nazw modułów najwyższego poziomu `kio_tool` (`package_targets` czyta
pierwszy człon importu względnego), stąd `wyszukiwanie.py`, a nie `odczyt.py`.

### Z-2. `kio_tool/pipeline/`

| Moduł | Treść | `source` | `store` |
|---|---|---|---|
| `__init__.py` | fasada | — | — |
| `zgoda.py` | próg i werdykt zgody, sufit, rozstrzygnięcie | typ `Ponowienia` | — |
| `slad.py` | `_Puls`, `_SladDoBazy` | — | typ `Store` |
| `pobieranie.py` | `pobierz`, `_przebieg`, wycena, `do_wznowienia`, `wznow` | **tak** | **tak** |
| `lokalne.py` | `eksportuj`, `build_metadata`, `przelicz`, `szukaj` | — | tak |

`lokalne.py` nie importuje ani `source`, ani `httpclient` — to zdanie z nagłówka dawnego
`pipeline.py` („fabryka klienta jest wołana wyłącznie w `pobierz`") staje się granicą modułu.

### Z-3. Fasada: reeksport tego, co się czyta, nigdy szwu, który się podstawia

Każdy `__init__.py` wystawia wyłącznie nazwy z `__all__` — publiczną powierzchnię dawnego modułu.
**Poza fasadą zostają szwy podstawiane w testach: `build_http_client` i `default_output_dir`.**
Fasada z tą nazwą zamieniłaby `monkeypatch.setattr(pipeline, "build_http_client", x)` w podstawienie
bez skutku; fasada bez niej zamienia je w `AttributeError`. Testy podstawiają fabrykę pomocnikiem
`podstaw_fabryke_klienta`, który obchodzi wszystkie moduły pakietu potoku — zakres „cały pakiet"
jest dokładnie dzisiejszym zakresem „cały moduł".

### Z-4. Reguły granic: z pliku na pakiet

| Reguła | Po |
|---|---|
| 2, 8, 13 | bez zmian — skan nazwowy i rekursywny |
| 3 | `pliki_store()` — `store/**/*.py` |
| 4 | `(*pliki_source(), *pliki_store())` |
| 5 | `obaj == {"kio_tool/pipeline/pobieranie.py"}` — **równość z jednym plikiem**, nie podzbiór pakietu |
| `PONAD_SUFITEM` | `{}` |

**Z-4.1.** Nowy metatest: właściciele reguł 3, 4 i 5 (`store/__init__.py`, `pipeline/pobieranie.py`)
muszą leżeć w skanie — zmiana nazwy pakietu nie rozbraja już reguł bez czerwonego testu. To lista
obowiązków, nie wyjątków.

**Z-4.2.** Bramka ADR-0001 patrzy na `kio_tool/store/__init__.py`; kontrola blokady
w `test_ratelimit.py` iteruje po pakiecie i żąda jego istnienia.

### Z-5. Niezmiennik „rekordy strony i punkt kontrolny jedną transakcją"

Nowy skan w sekcji reguły 5: `.checkpoint(` może stać wyłącznie w `pipeline/pobieranie.py`, każde
wywołanie leksykalnie w bloku `with <x>.transakcja():`, który woła też `upsert_document`,
`add_raw_version` i `link_run_document`. Samosprawdzenie na podrzuconych źródłach.

### Z-6. Strażnik fasady — `tests/test_fasady.py`

1. `__all__` obu fasad równe inwentarzowi i każda nazwa się rozwiązuje.
2. `build_http_client` i `default_output_dir` **nie** są atrybutami fasady.
3. Skan testów: `setattr`/`patch` na fasadzie albo podmodule jest naruszeniem, gdy **ten sam
   obiekt** trzyma pod tą nazwą więcej niż jeden moduł pakietu — podstawienie trafia w jedno
   miejsce, a czytać może drugie. Tożsamość, nie składnia (poprawka po przeglądzie kodu
   2026-09-22: pierwsza wersja przepuszczała `store.schemat.SCHEMA_VERSION`, czytane
   w `magazyn`, i postać `import kio_tool.pipeline`).

## 5. Plan

Gałąź `refactor/o5-pakiety`: (1) `store/` z regułami 3–4 i Z-4.1, (2) `pipeline/` z regułą 5
i pomocnikiem, **punkt kontrolny** — przy czerwieni powrót do W0, (3) `test_fasady.py` i Z-5,
(4) dokumenty, (5) suita, `kio-tool demo`, `szukaj` i `runy` na bazie operatora, scalenie lokalne.
Każda przepięta reguła sprawdzona mutacją.

## 6. Konsekwencje

- Dwa pakiety, trzynaście plików (jedenaście modułów i dwie fasady), `PONAD_SUFITEM` pusty.
- Powierzchnia fasad przypięta testem; szew podstawiany w testach nie mieszka w fasadzie,
  a nazwę trzymaną przez kilka modułów pakietu podstawia się we wszystkich naraz
  (`wsparcie_sondy.podstaw_w_pakiecie`) — moduł definicji nie zawsze jest modułem, który czyta
  (`SCHEMA_VERSION`: definicja w `schemat`, odczyt w `magazyn`; przegląd kodu 2026-09-22).
- `odczyt.py` zostaje bajt w bajt (odcisk `PARSE_VERSION`).
- Slajd „Granice": „Dwa pliki przekraczały własną normę projektu; rozbite 22.09 bez zmiany
  zachowania, reguły granic przepięte tak, że nie osłabły" (brzmienie zaakceptowane przez
  właściciela 2026-09-22).

**Kiedy wrócić:** klasa cząstkowa potrzebuje cudzego stanu poza `_conn` i `_path` → W2;
`pobieranie.py` ponad 600 linii → wydzielić wznowienie; faza 4 (`mcp_server.py`) → czy serwer
czyta z fasady.

## 7. Czego ten ADR nie rozstrzyga

`scripts/zbuduj_wzorce_demo.py` importuje naraz `source.contract` i `store` (reguła 5 obejmuje
`kio_tool/`, nie `scripts/`); czy `store/model.py` i `store/schemat.py` wejdą do modułów czystych
reguły 1; przejście `Store` na kompozycję (W2).
