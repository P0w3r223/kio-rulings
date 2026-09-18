# ADR-0003: Kanał jest pakietem, a bramka wyjścia jest indeksowana protokołem

Data: 2026-09-15
Status: accepted (2026-09-15, decyzja właściciela)
Autor: P0w3r223
Related to: `ARCHITEKTURA_KIO_TOOL.md` (4.1 reguły 17 i 20, 4.2, 4.3, 4.4, 8), `AUDYT_KIO_ORZECZENIA.md` (8.3 reguły 1, 2, 4, 11, 13), `docs/decisions.md` (pomiar 21), `tests/test_pomiar21_blokada_sieci.py`, `kio_tool/httpclient.py`, `kio_tool/docid.py`

ADR-0001 (tożsamość dokumentu) i ADR-0002 (surowiec, treść do modelu) jeszcze nie powstały; numeracja zostawia im miejsce.

---

## 1. Kontekst

### 1.1 Stan drzewa w dniu decyzji

`kio_tool/` nie jest już pusty. Istnieją: `__init__.py`, `clock.py`, `safetext.py`, `errors.py`, `config.py`, `richtext.py`, `progress.py`, `httpclient.py`, `docid.py` — warstwa infrastruktury przeniesiona z `ceidg-tool` plus producent tożsamości. Katalogi `source/`, `parser/` i `ui/` są nadal puste (`.gitkeep`). W `tests/` leżą `__init__.py`, `test_pomiar21_blokada_sieci.py` i `test_docid.py`. `pyproject.toml` ma `addopts = "--block-network"` i marker `smoke`.

Kanał akwizycji **nie jest wybrany**: pomiary 1 (FTP), 2a/2b (SAOS Dump API) i 3 (Atlas) nie padły. Bramka fazy 0 jeszcze nie przeszła, więc `source/` nie ma czego implementować. Ten ADR jest o kształcie, który `source/` przyjmie, gdy już powstanie, i o regule, którą trzeba mieć **zanim** powstanie — bo obie da się dziś kupić za tekst, a po pierwszym adapterze już nie.

### 1.2 Dwie niespójności strukturalne w dokumentacji

**Niespójność 1: `source/` występuje w dwóch niezgodnych postaciach.** Dwa wystąpienia opisowe mówią „płasko", trzy normatywne mówią „pakiet":

| Miejsce | Postać | Charakter |
|---|---|---|
| `ARCHITEKTURA_KIO_TOOL.md:330-334` (mapa modułów 4.2) | `source/` → `uzp.py`, `atlas.py`, `saos.py`, `ftp.py` | opisowe |
| `ARCHITEKTURA_KIO_TOOL.md:372-375` (tabela adapterów 4.3) | `source/uzp.py`, `source/atlas.py`, … | opisowe |
| `ARCHITEKTURA_KIO_TOOL.md:307` (reguła 17) | `source/uzp/contract.yaml` | **normatywne** |
| `ARCHITEKTURA_KIO_TOOL.md:469` (4.7) | `source/atlas/contract.yaml` | **normatywne** |
| `ARCHITEKTURA_KIO_TOOL.md:160` (3.1) | `source/uzp/contract.yaml` | normatywne |

Obie reguły, które mają mieć mechanicznego strażnika, zakładają pakiety. Płasko mówią wyłącznie rysunki. Kod napisany do tej pory też zakłada pakiety: `kio_tool/config.py:3-6` mówi wprost, że wszystko zależne od kanału „mieszka w `contract.yaml` **przy adapterze**".

**Niespójność 2: kanał FTP prowadzony przez moduł, który buduje klienta `httpx`.** Na mapie modułów (`ARCHITEKTURA_KIO_TOOL.md:330-337`) jedna strzałka wychodzi z całego pudełka `source/` — razem z `ftp.py` — do `httpclient.py`. Reguła 11 audytu (`AUDYT_KIO_ORZECZENIA.md:746`) brzmi „Tylko `httpclient.py` buduje `httpx.Client`". `httpx` nie obsługuje FTP, a istniejąca polityka wyjścia w `kio_tool/httpclient.py:41-47` odmawia wszystkiemu poza `https`:

```python
if scheme != "https" or host not in allowed:
    raise UntrustedLinkError(...)
```

Strzałka na rysunku opisuje więc ścieżkę, która nie ma prawa się wykonać. Reguła obejmuje FTP **pozornie** — i to jest gorsze niż jawny wyjątek, bo raportuje się jako domknięta. Ten sam kształt wystąpił już raz w `ceidg-tool`: skan reguły 11 dopasowywał dosłowną nazwę `httpx` i przez to przepuszczał `httpx2` spod SDK modelu (`Ceidg/tests/test_boundaries.py:643-648`), raportując pokrycie przy połowie ruchu.

**Niespójność pochodna, z tego samego korzenia:** `raw_versions.http_meta` (`ARCHITEKTURA_KIO_TOOL.md:405`) ma nieść „status, nagłówki, adres finalny, User-Agent", podczas gdy wiersz wyżej dopuszcza w `content_bytes` „plik (ftp)". Nazwa kolumny niesie to samo fałszywe założenie co strzałka.

### 1.3 Co zmienił pomiar 21

Zmierzone 2026-09-15, 0 żądań, `tests/test_pomiar21_blokada_sieci.py`, zapisane w `docs/decisions.md`. Środowisko: Python 3.12.10, httpx 0.28.1, pytest 9.1.1, pytest-recording 0.13.4, Windows 11.

- Żądanie przez `build_http_client` — czyli przez klienta z **zawsze** wstrzykniętym `AllowedHostsTransport` — jest pod `--block-network` zatrzymywane `RuntimeError("Network is disabled")`, a nie błędem połączenia. Wstrzyknięty transport nie omija punktu zaczepienia blokady.
- `socket.create_connection` kończy się tym samym wyjątkiem. Blokada jest zamkiem **na gnieździe**, nie na bibliotece.

Konsekwencja dla tego ADR jest bezpośrednia: reguła 20 pokrywa także kanał spoza HTTP, **niezależnie od tego, który kanał wygra**. Zastrzeżenie z przeglądu architektonicznego („to jest odczyt cudzej dokumentacji, nie pomiar") jest zamknięte dla połowy „blokada". Otwarta zostaje wyłącznie druga gwarancja — odtwarzanie kaset przez wstrzyknięty transport — którą rozstrzygnie pierwsza prawdziwa kaseta przy pomiarze 4b; do tego czasu `respx` zostaje w zależnościach deweloperskich.

To **nie** czyni niespójności 2 mniej ważną. Blokada sieci pilnuje testów; bramka wyjścia pilnuje produkcji. Pomiar 21 mówi, że nowy protokół nie rozszczelni testów — nie mówi nic o tym, dokąd taki kanał wyjdzie w przebiegu u operatora.

---

## 2. Rozstrzygnięcie 1: kanał jest pakietem

### Opcja 1A (odrzucona): moduły płaskie plus katalog kontraktów

- **Opis**: `source/uzp.py` obok `source/contracts/uzp.yaml`. Edytujemy dwie reguły (17 i 4.7), rysunki zostają.
- **Za**: najmniej plików przy jednym kanale; brak zagnieżdżenia w importach względnych.
- **Przeciw**: adapter i jego kontrakt da się rozjechać zmianą nazwy jednego z nich, a jedynym spoiwem jest test parujący. Gdy kanał urośnie ponad jeden moduł — a UZP już wymaga budowania formularza `GetResults`, czytania `Details`, odczytania nagłówka `Location` przy `Move` i wykrywania `data-page` — dostajemy `uzp_forms.py` obok `uzp.py`, czyli płaską przestrzeń nazw z dorozumianym grupowaniem. Usunięcie kanału, który przegrał pomiary, to wtedy kilka plików w dwóch katalogach zamiast jednego `rm -r`.
- **Nakład**: S. **Ryzyko**: niskie technicznie, średnie dokumentacyjnie — dopasowuje normę do rysunku, czyli daje drugą okazję do tego samego rozjazdu.

### Opcja 1B (przyjęta): pakiet na kanał

- **Opis**:

```
kio_tool/source/
  __init__.py       # wyłącznie re-eksport
  protocol.py       # Channel, Candidate, RawDocument, Capabilities, Scope
  contract.py       # wczytanie contract.yaml; jedyny czytelnik tych plików
  registry.py       # REGISTRY: dict[SourceName, type[Channel]]; importy statyczne
  <kanal>/
    __init__.py
    channel.py      # implementacja Channel
    contract.yaml   # adresy, nazwy pól, tempo, rozmiar strony, licencja, data odczytu
```

- **Za**: kontraktu nie da się osierocić (`Path(__file__).parent / "contract.yaml"`, zero konfiguracji ścieżek); usunięcie przegranego kanału to jeden katalog; kanał może mieć moduły pomocnicze bez zanieczyszczania wspólnej przestrzeni nazw; norma i rysunek zgadzają się po edycji **rysunku**, czyli części opisowej.
- **Przeciw**: przy dokładnie jednym kanale na zawsze jest to o dwa pliki więcej niż trzeba.
- **Nakład**: S. **Ryzyko**: niskie. Nic nie istnieje, więc nie ma czego migrować.

### Decyzja i argument rozstrzygający

Przyjmujemy 1B. Trzy rzeczy przechyliły szalę:

1. **Kierunek edycji.** Reguły są normatywne, rysunki opisowe. Dopasowanie rysunku do reguły zamyka temat; dopasowanie reguły do rysunku otwiera go ponownie przy pierwszym module pomocniczym.
2. **Kanałów w planie nie jest jeden.** Decyzja 6 (`ARCHITEKTURA_KIO_TOOL.md:636`) rekomenduje Atlas do pierwszego pobrania i UZP do weryfikacji oraz dopływu bieżącego; polecenie `porownaj` z definicji potrzebuje dwóch kanałów naraz; tabela `equivalences` istnieje wyłącznie dlatego, że kanały będą dwa. Pakiet obsługuje planowaną rzeczywistość, nie hipotetyczną.
3. **Skan z CEIDG przenosi się bez zmiany.** `package_targets` w `Ceidg/tests/test_boundaries.py:123-152` bierze `node.module.split(".")[0]` niezależnie od `node.level`, więc `from ...httpclient import build_http_client` w `source/uzp/channel.py` daje `"httpclient"`, a `from .source.registry import REGISTRY` w `pipeline.py` daje `"source"`. Zagnieżdżenie o poziom głębiej nie wymaga ani jednej linii zmiany w skanie. To jest odczyt tej funkcji, nie domysł.

### Jak to godzi się z „kanał nie jest wybrany"

Roster kanałów **nie jest w teście wypisany**. Skan porównuje trzy zbiory wyznaczone z drzewa i z kodu: katalogi z `channel.py`, katalogi z `contract.yaml`, klucze `REGISTRY`. Przy pustym `source/` wszystkie trzy są puste i reguła przechodzi zgodnie ze stanem projektu. `SourceName` zostaje `NewType` z `kio_tool/docid.py:40`, a nie `Literal`: `REGISTRY` jest jedynym miejscem wymieniającym kanały, a wypisanie ich drugi raz w typie byłoby drugą listą do uzgadniania. Nazwa katalogu jest nazwą kanału — tym samym napisem, który `docid.document_id` wstawia przed dwukropkiem.

---

## 3. Rozstrzygnięcie 2: bramka wyjścia indeksowana protokołem

### Opcja 2A (odrzucona): jawny wyjątek dla FTP

- **Opis**: dopisać do reguły 11 zdanie „reguła obejmuje HTTP; kanał FTP jest poza nią".
- **Za**: uczciwe wobec stanu faktycznego; zero kodu.
- **Przeciw**: doktryna projektu mówi, że reguła bez mechanicznego strażnika jest życzeniem — a wyjątek bez strażnika jest życzeniem z podpisem. Adapter FTP mógłby otworzyć gniazdo dokądkolwiek i nic nie byłoby czerwone. Zamienia pozorne pokrycie na jawną dziurę: poprawa uczciwości, zero poprawy bezpieczeństwa.
- **Nakład**: S. **Ryzyko**: wysokie — dziura w bramce wyjścia dla kanału, który (decyzja 9) może jednak powstać.

### Opcja 2B (przyjęta): tablica właścicieli indeksowana konstruktem

- **Opis**: reguła przestaje mówić o bibliotece, zaczyna mówić o konstrukcie otwierającym połączenie. Tablica `EGRESS_OWNERS` w `tests/test_boundaries.py` mapuje konstrukt na zbiór plików, które wolno mu budować; zbiór pusty znaczy „żaden plik nie ma prawa tego zbudować".
- **Za**: działa przy pustym `source/` i przy nieznanym kanale; w dniu, w którym ktokolwiek napisze `ftplib.FTP(...)`, test jest czerwony i wymusza decyzję zamiast pozwolić ją przemilczeć; to ten sam ruch, który `ceidg-tool` wykonał raz przy `httpx2`, tylko o poziom dalej — ze zbioru bibliotek na tablicę konstruktów z właścicielem.
- **Przeciw**: tablica jest wyliczeniem, więc konstrukt w niej niewymieniony przechodzi niewidziany. Lekarstwem jest trzymanie jej krótkiej i uzasadnionej, a nie szerokiej.
- **Nakład**: S (sam skan jest uogólnieniem `builds_http_client` z CEIDG z dwóch zbiorów na jedną mapę). **Ryzyko**: niskie.

### Decyzja

Przyjmujemy 2B. Kanał FTP **wypada z mapy modułów i z tabeli adapterów** do czasu pomiaru 1 — nie dlatego, że przegrał, tylko dlatego, że rysunek ma pokazywać to, co istnieje albo jest rozstrzygnięte, a pomiar kosztuje jedno żądanie i jeszcze nie padł. Tytuł komunikatu UZP („Komunikat dotyczący wyłączenia serwera FTP z orzecznictwem KIO", `ARCHITEKTURA_KIO_TOOL.md:75`) każe zakładać wynik negatywny.

### Co to znaczy dla `refuse_foreign_host` — zmiana w istniejącym pliku, nie nowy byt

Powiedziane wprost, żeby nie było wątpliwości przy czytaniu za pół roku: **jeżeli** zapadnie decyzja 9 w wariancie (a), to `refuse_foreign_host(scheme, host, allowed: frozenset[str])` z `kio_tool/httpclient.py:41` **zostaje zastąpiona** przez `refuse_foreign_endpoint(scheme, host, allowed: frozenset[tuple[str, str]])` w tym samym pliku, a `UZP_HOSTS` / `ATLAS_HOSTS` / `SAOS_HOSTS` w `kio_tool/config.py` zmieniają typ na zbiory par `(schemat, host)`.

> **Dopisek 2026-09-17** (zmiana w dokumencie przyjętym, więc jawna, a nie cicha): zdanie wymieniało tu także `ALLOWED_HOSTS`. Tej stałej **już nie ma** — została usunięta razem z wartością domyślną parametru `allowed` w `build_http_client`, bo miała zero wywołujących, a jej komentarz opisywał użycie nieobecne w drzewie. Powrotu pilnuje `tests/test_bramka_wyjscia.py`. Reszta zdania obowiązuje bez zmian. To jest edycja dwóch istniejących plików i jednego istniejącego testu (`test_http_bez_tls_odbija_sie_od_bramki_wyjscia`), nie dopisanie nowego modułu obok.

Pary, a nie osobny parametr na dozwolone schematy: lista schematów rozłączna z listą hostów pozwoliłaby na `ftp://orzeczenia.uzp.gov.pl` i `https://ftp.uzp.gov.pl`, czyli dokładnie na przypadkowe rozszerzenie, któremu ta reguła ma zapobiegać.

**Tej zmiany nie robimy teraz.** Dziś istnieje jeden protokół i jedna kopia polityki, która go poprawnie obsługuje; wyzwalaczem zmiany jest pozytywny pomiar 1 plus wariant (a) decyzji 9, a nie ten ADR. Reguła 11 w brzmieniu z sekcji 4 gwarantuje, że drugi protokół nie da się dopisać po cichu — a to jest cała potrzebna gwarancja przed pomiarem. Zasada jest ta sama, którą `ceidg-tool` zapisał w nagłówku `httpclient.py`: jedna kopia reguły krytycznej dla bezpieczeństwa, nigdy dwie.

---

## 4. Brzmienia reguł do przeniesienia

Do przeniesienia bez przepisywania. Numeracja reguł 11 i 17 zastępuje obecne brzmienia; 21 i 22 są nowe.

### Reguła 11 (zastępuje `AUDYT_KIO_ORZECZENIA.md:746-747`)

> 11. **Jeden właściciel na protokół, jedna kopia polityki wyjścia.** Konstrukt otwierający połączenie sieciowe powstaje wyłącznie w module-właścicielu przypisanym do jego protokołu. Dziś właściciel jest jeden — `kio_tool/httpclient.py` — i buduje wyłącznie `httpx.Client` / `httpx.AsyncClient`, zawsze z wstrzykniętym transportem i `trust_env=False`. Tablica `EGRESS_OWNERS` w `tests/test_boundaries.py` wymienia **konstrukty, nie biblioteki**: `httpx.Client`, `httpx.AsyncClient`, `ftplib.FTP`, `ftplib.FTP_TLS`, `socket.socket`, `socket.create_connection`, `urllib.request.urlopen`, `urllib.request.build_opener`, `asyncio.open_connection`. Pozycja z pustym zbiorem właścicieli znaczy „żaden plik nie ma prawa tego zbudować"; żeby ją zbudować, trzeba najpierw dopisać właściciela do tablicy i regułę wyjścia do dokumentu architektury. Każdy właściciel woła tę samą, jedyną kopię reguły „dokąd wolno wyjść" — dziś jest nią `refuse_foreign_host`. Zakres skanu obejmuje `kio_tool/`, `tests/` oraz `scripts/`, jeśli powstanie: sonda niesie ten sam ruch co narzędzie, więc reguła obowiązuje i ją.
>
> Powód, dla którego reguła mówi o protokole, a nie o `httpx`: `httpx` nie obsługuje FTP, a polityka wyjścia odmawia wszystkiemu poza `https`. Zdanie „jedno miejsce buduje klienta i jest bramką wyjścia" w poprzednim brzmieniu obejmowało kanał FTP wyłącznie na rysunku. W `ceidg-tool` ten sam kształt wystąpił raz wcześniej — skan dopasowywał nazwę `httpx` i przepuszczał `httpx2` spod SDK modelu — i został naprawiony zamianą nazwy na zbiór; tu zamiana idzie o poziom dalej, ze zbioru bibliotek na tablicę konstruktów z właścicielem.

### Reguła 17 (zastępuje `ARCHITEKTURA_KIO_TOOL.md:307`)

> 17. **Każdy kanał ma kontrakt, złote pliki i test dymny.** Kanał jest pakietem `source/<nazwa>/` i zawiera `channel.py` (implementacja `Channel`), `contract.yaml` (adres bazowy, nazwy punktów końcowych i pól, tempo, rozmiar strony, licencja, data odczytu) oraz, jeśli trzeba, moduły pomocnicze. `contract.yaml` jest jedynym miejscem, z którego `channel.py` bierze adresy i nazwy pól — pilnuje tego reguła 22. `tests/examples/<nazwa>/` zawiera surowe odpowiedzi z datą pobrania w nazwie, a obok każdej `*.compare.json` wygenerowany przy pierwszym uruchomieniu i przejrzany przez człowieka przed commitem (wzorzec Juriscrapera, 3.3). Adapter, który dostanie odpowiedź o statusie zgodnym z kontraktem, ale o kształcie niezgodnym, **rzuca `SourceContractBroken`**, nie zwraca pustej listy. Dla UZP kształtem jest obecność `div.search-list-item` i `#resultCounts`; powód jest datowany: między majem a lipcem 2026 UZP przeniósł każdy punkt końcowy, a cudzy scraper przez około dwa miesiące zwracał `total=0` ze statusem 200 zamiast błędu.

Zmiana wobec poprzedniego brzmienia jest dwojaka: reguła przestaje być regułą o UZP (kanał nie jest wybrany, a wymaganie dotyczy każdego kandydata) i przestaje mówić „200" (kanał plikowy nie ma statusu HTTP — to ta sama choroba, co strzałka z rysunku). Docstring `SourceContractBroken` w `kio_tool/errors.py:36-47` nazywa dziś HTTP 200 wprost; uogólnia się tak samo i dopiero wtedy, gdy powstanie kanał spoza HTTP.

### Reguła 21 (nowa)

> 21. **Kanał jest pakietem; w `source/` nie leży moduł kanału luzem.** Bezpośrednio w `source/` wolno leżeć wyłącznie modułom wspólnym z wyliczonej listy: `__init__.py` (re-eksport), `protocol.py` (`Channel`, `Candidate`, `RawDocument`, `Capabilities`, `Scope`), `contract.py` (wczytanie `contract.yaml`) i `registry.py` (`REGISTRY: dict[SourceName, type[Channel]]`, importy statyczne). Każdy inny wpis w `source/` jest katalogiem zawierającym `__init__.py`, `channel.py` i `contract.yaml`. Nazwa katalogu jest nazwą kanału: tym samym napisem, który idzie do `docid.document_id` jako `source`, do kolumny `documents.source` i do przedrostka `doc_id`. Skan sprawdza równość trzech zbiorów — katalogi z `channel.py`, katalogi z `contract.yaml`, klucze `REGISTRY` — więc nie przechodzi ani kanał bez kontraktu, ani kontrakt-sierota, ani kanał niewidoczny dla kreatora. `SourceName` zostaje `NewType`, a nie `Literal`: roster kanałów nie jest znany przed bramką fazy 0, a `REGISTRY` jest jedynym miejscem, które go wymienia — wypisanie go drugi raz w typie byłoby drugą listą do uzgadniania. Przy pustym `source/` wszystkie trzy zbiory są puste i reguła przechodzi zgodnie ze stanem projektu; ciężar dowodu niosą wtedy samosprawdzenia skanu na plikach podrzuconych w `tmp_path`.

### Reguła 22 (nowa)

> 22. **Adres i nazwa pola nie występują jako literał w kodzie kanału.** Skan AST odrzuca w `source/**/*.py` każdy napis pasujący do `^[a-z][a-z0-9+.-]*://` albo `^/[A-Za-z]`, z wyjątkiem napisów dokumentacyjnych (docstring modułu, klasy i funkcji). To jest mechaniczna postać zdania z reguły 17 „`contract.yaml` jest jedynym miejscem, z którego adapter bierze adresy i nazwy pól"; bez niej to zdanie jest życzeniem, a po przebudowie wyszukiwarki UZP z lipca 2026 jest to życzenie kosztowne. Lekarstwem na czerwony test jest przeniesienie napisu do `contract.yaml`, nigdy dopisanie wyjątku — lista wyjątków jest miejscem, w którym reguła cicho przestaje obowiązywać.

### Reguły, które wymagają krótszej poprawki

| Reguła | Gdzie | Poprawka |
|---|---|---|
| 1 | audyt 8.3 | `parser.py` → **każdy moduł w `parser/` (rekursywnie)**; lista modułów czystych spoza `parser/` wyliczona wprost (dziś: `docid.py`, `safetext.py`; docelowo `criteria.py`, `dictionaries.py`). `config.py` do niej **nie** należy — importuje `os` i ma do tego powód (`CONTACT_ENV`). |
| 2 | audyt 8.3 | „Adaptery w `source/`" → „Żaden moduł w `source/` — **rekursywnie, `source/**/*.py`**". Powód: `Path("source").glob("*.py")` jest skanem, który wygląda na działający dokładnie do dnia, w którym kanały stają się pakietami, a potem nie obejmuje niczego. |
| 4 | audyt 8.3 | To samo słowo „rekursywnie" dla zakazu `rich` w `source/`. |
| 13 | audyt 8.3 | Mówi o `assistant/*`, a decyzja 3 (`ARCHITEKTURA_KIO_TOOL.md:633`) zastąpiła asystenta serwerem MCP. Nowe brzmienie: „`mcp_server.py` importuje wyłącznie `store` (odczyt) i `exporter`; nie importuje `source`, `pipeline` ani `criteria`". Do fazy 4 jest to wyzwalacz, nie reguła. |
| 20 | architektura 4.1 | Dopisać wynik pomiaru 21: blokada jest zamkiem na gnieździe (zmierzone 2026-09-15, 0 żądań), więc reguła 20 pokrywa także kanał spoza HTTP niezależnie od wyniku pomiarów 1–3. Otwarte zostaje **odtwarzanie kaset** przez wstrzyknięty transport — rozstrzyga pomiar 4b; do tego czasu `respx` zostaje w zależnościach deweloperskich. Rozróżnienie „blokada" / „kasety" jako dwóch osobnych gwarancji jest częścią reguły, nie komentarzem do niej. |

---

## 5. Kształt `tests/test_boundaries.py`

Implementacja powstaje w osobnym przebiegu; tu stoi kształt, żeby nie trzeba było odtwarzać tej rozmowy.

### 5.1 Zasada nadrzędna: pusty skan nie jest zielonym skanem

Każda reguła ma od pierwszego commita trzy części:

1. **Reguła na prawdziwym drzewie.** Może przechodzić pusto, dopóki drzewo jest puste — i to jest prawda o stanie projektu, nie luka.
2. **Samosprawdzenie skanu na plikach podrzuconych w `tmp_path`.** Nigdy nie jest puste. W fazie 0 to ono niesie cały ciężar dowodu. Wzorzec: `test_the_rule_11_scan_tells_building_a_client_from_naming_one` i `test_the_rule_13_scan_would_notice_a_planted_import` z CEIDG.
3. **Metatest antypustkowy.** Reguła, której plik-właściciel istnieje, a skan go nie obejmuje, jest jedynym sposobem, w jaki ta tablica może skłamać. Stan „wyzwalacz" jest legalny wyłącznie wtedy, gdy pliku nie ma.

Dziś w stanie **reguły** są: 11 (właściciel `httpclient.py` istnieje i buduje klienta) oraz 1/6 w części dotyczącej `docid.py` i `safetext.py`. W stanie **wyzwalacza** są: 21, 22, 2, 4, 5, 13 i reszta — ich pliki jeszcze nie powstały.

### 5.2 Pułapka, którą trzeba obsłużyć od razu

`tests/test_pomiar21_blokada_sieci.py` woła `socket.create_connection` — i **musi**, bo przedmiotem tego pomiaru jest właśnie to, czy blokada sięga gniazda. Gdyby `EGRESS_OWNERS` mapowało konstrukt na pojedynczy plik-właściciel, ten istniejący i poprawny test byłby naruszeniem reguły 11 od pierwszego uruchomienia skanu, a naturalnym odruchem byłoby dopisanie wyjątku.

Dlatego wartością w tablicy jest **zbiór** dozwolonych plików, nie jeden plik, a `("socket", "create_connection")` ma jako właściciela `tests/test_pomiar21_blokada_sieci.py` z zapisanym powodem. CEIDG ma dokładnie ten kształt w regule 12, gdzie `dozwolone` obejmuje moduł produkcyjny i jeden test, z uzasadnieniem w komunikacie asercji.

### 5.3 Reguły filesystemowe obok AST

Reguła 21 i parowanie kontraktów to sprawdzenia **systemu plików**, nie skan AST. Mieszkają w tym samym pliku i tak ma być — CEIDG trzyma tam `test_every_pure_module_actually_exists` z tego samego powodu. Nazywanie ich skanem AST byłoby nieścisłe i tego ADR nie robi.

### 5.4 Jedna poprawka wobec wzorca z CEIDG

Reguła 7 w CEIDG asertuje **równość** zbiorów (`users == RICH_MODULES`, `Ceidg/tests/test_boundaries.py:175-183`). W Kio `rich` zna dziś wyłącznie `richtext.py`; `console.py` i `ui/render.py` nie istnieją. Równość byłaby więc czerwona od pierwszego uruchomienia. Reguła 7 ma tu kształt zawierania (`users <= RICH_MODULES`) plus metatest z 5.1, i przechodzi w równość, gdy warstwa `ui/` powstanie.

---

## 6. Decyzja 9 do rozstrzygnięcia przez właściciela: postać kanału FTP

**To nie jest rozstrzygnięte tym ADR-em i nic dziś nie blokuje.** Wchodzi do rozstrzygnięcia dopiero z pozytywnym pomiarem 1; przy wyniku negatywnym odpada bez kosztu. Obie drogi podlegają tej samej regule 11 i temu samemu skanowi — i o to w rozstrzygnięciu 2 chodziło.

**Wariant (a): pełny kanał z własnym właścicielem protokołu.** `ftpclient.py` obok `httpclient.py`, wspólna polityka wyjścia w postaci par `(schemat, host)`, tempo z `ratelimit.py`, wpis w `requests_log`, identyfikacja hasłem anonimowym z adresem kontaktowym (FTP nie ma `User-Agent`). Koszt: jeden moduł, zmiana sygnatury polityki w dwóch istniejących plikach, druga lista dozwolonych punktów. Zysk: pobranie jest pod kontrolą narzędzia — tempo, dziennik, wznawianie, zgoda w sesji.

**Wariant (b): import offline z lokalnego lustra.** Operator robi jedno lustro katalogu narzędziem systemowym pod jedną zgodą, a `source/archiwum/` czyta katalog lokalny i nie otwiera żadnego połączenia. Koszt: pobranie ~30 tys. plików dzieje się poza jakimkolwiek strażnikiem narzędzia — brak `requests_log`, tempo ustawia operator w poleceniu. Zysk: reguła 11 zostaje z jednym właścicielem i pełnym pokryciem; kanał jest jedynym, którego pełną ścieżkę da się przetestować przy włączonej blokadzie sieci.

**Rekomendacja, do potwierdzenia po pomiarze 1**: wariant (b), jeżeli lustro jest jednorazowe — a publikacja na FTP ustała 30.09.2025, więc jest. Wariant (a) tylko wtedy, gdyby FTP okazał się nadal aktualizowany, bo wtedy kanał ma dopływ bieżący i potrzebuje dziennika oraz wznawiania. Niezależnie od wariantu: nazwa kanału opisuje **pochodzenie bajtów**, nie transport, więc `fetch_meta` niesie w wariancie (b) narzędzie lustra, datę lustra, nazwę pliku, rozmiar i znacznik czasu z serwera.

---

## 7. Konsekwencje

### 7.1 Co się zmienia w dokumentach

**Wykonane 2026-09-15**, w tym samym dniu, w którym ADR został przyjęty. Tabela zostaje jako
zapis tego, co zmieniono i gdzie — numery linii odnoszą się do stanu **sprzed** edycji, więc
nie próbuj ich odczytywać w bieżącej wersji dokumentów.

| Plik i miejsce | Zmiana |
|---|---|
| `ARCHITEKTURA_KIO_TOOL.md:330-337` | Pudełko `source/` pokazuje `__init__.py`, `protocol.py`, `contract.py`, `registry.py` i **jeden** przykładowy katalog `<kanal>/` z `channel.py` + `contract.yaml`. Strzałka do `httpclient.py` z podpisem „kanały HTTP — i tylko one". Pod rysunkiem zdanie o właścicielu protokołu dla kanału spoza HTTP. |
| `ARCHITEKTURA_KIO_TOOL.md:372-375` | Kolumna adapterów: `source/uzp/`, `source/atlas/`, `source/saos/`. Wiersz `source/ftp.py` **usunąć**, zastąpić zdaniem pod tabelą z odesłaniem do decyzji 9. |
| `ARCHITEKTURA_KIO_TOOL.md:405` | `http_meta` → **`fetch_meta`**, z opisem zależnym od kanału. Zmiana kosztuje dziś zero, bo nie ma bazy. |
| `ARCHITEKTURA_KIO_TOOL.md:441` | `requests_log`: `method` i `status` niosą polecenie i kod protokołu (HTTP `GET`/`200`, FTP `RETR`/`226`), nie wyłącznie HTTP. |
| `ARCHITEKTURA_KIO_TOOL.md:307, 310` | Nowe brzmienia reguł 17 i 20 z sekcji 4. |
| `ARCHITEKTURA_KIO_TOOL.md` sekcja 4.1 | Dopisać reguły 21 i 22. |
| `ARCHITEKTURA_KIO_TOOL.md` sekcja 8 | Dopisać decyzję 9 w brzmieniu z sekcji 6. |
| `ARCHITEKTURA_KIO_TOOL.md:587` | Pomiar 21: status „wykonany w obu połowach 2026-09-15"; otwarte wyłącznie odtwarzanie kaset (pomiar 4b). |
| `AUDYT_KIO_ORZECZENIA.md:733-754` | Reguły 1, 2, 4, 11, 13 wg sekcji 4. |

### 7.2 Co się zmienia w kodzie

Dziś: **nic**. Wszystkie cztery reguły są albo już spełnione (11 — `httpclient.py` jest jedynym budowniczym klienta), albo dotyczą katalogów, które jeszcze nie powstały (17, 21, 22). Pierwszy kod, którego dotkną, to pierwszy adapter po bramce fazy 0.

Potem, w kolejności: `tests/test_boundaries.py` (osobny przebieg), `source/protocol.py` + `source/contract.py` + `source/registry.py` przy pierwszym adapterze, a `refuse_foreign_endpoint` dopiero przy decyzji 9 w wariancie (a).

### 7.3 Czego świadomie nie dostajemy

- Reguła 22 złapie też ścieżkę posixową w kodzie kanału. Uważam to za cechę (adapter nie ma powodu znać ścieżek na dysku), ale jest to założenie do weryfikacji przy pierwszym adapterze; jeśli okaże się fałszywe, lekarstwem jest zawężenie wzorca, nie lista wyjątków.
- Tablica `EGRESS_OWNERS` jest wyliczeniem. Konstrukt w niej niewymieniony przechodzi niewidziany. Nie ma sposobu, żeby skan składniowy „złapał każde wyjście" bez wyliczenia; jest natomiast sposób, żeby wyliczenie było krótkie i uzasadnione wierszem po wierszu.
- Skan łapie przeoczenia, nie napastnika. Aliasowanie i `getattr` omijają go tak samo jak w CEIDG i jest to świadome.

### 7.4 Kiedy wrócić do tej decyzji

- **Pomiar 1 pozytywny** → decyzja 9 → ewentualnie drugi właściciel protokołu i zmiana sygnatury polityki wyjścia w `httpclient.py` i `config.py`.
- **Pomiar 4b** → domknięcie drugiej połowy reguły 20 (odtwarzanie kaset) i usunięcie `respx` albo `pytest-recording` z zależności deweloperskich.
- **Odwrócenie decyzji 6** (jeden kanał na zawsze, `porownaj` i `equivalences` nie powstają) → kształt pakietowy z rozstrzygnięcia 1 wart ponownego rozważenia. Nie wcześniej: dopóki w planie są dwa kanały i polecenie porównujące, pakiet zarabia na siebie.

---

## 8. Czego ten ADR nie rozstrzyga

- Który kanał wygra. Rozstrzygają pomiary 1, 2a/2b i 3 oraz bramka fazy 0.
- Czy kaseta HTTP odtworzy się przez wstrzyknięty transport (pomiar 4b).
- Tożsamości dokumentu — to ADR-0001; `docid.document_id` realizuje dziś propozycję z architektury 4.4 i sam o tym mówi.
- Czy treść orzeczenia wolno wysłać do modelu — to ADR-0002.
