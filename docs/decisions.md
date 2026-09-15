# Dziennik pomiarów i decyzji

Data utworzenia: 2026-09-15
Status: żywy — dopisywany przy każdym pomiarze, nigdy przepisywany wstecz
Autor: P0w3r223
Related to: `AUDYT_KIO_ORZECZENIA.md` (sekcja 10), `ARCHITEKTURA_KIO_TOOL.md` (sekcja 6)

---

## Konwencja

Każdy wpis niesie **datę i sposób uzyskania**. „Zmierzone {data}, {N} żądań" znaczy własny
odczyt. „Policzone z pliku X, 0 żądań" znaczy rachunek lokalny. „Z dokumentacji cudzej,
data X" znaczy cudzy pomiar z podaną datą. Liczba bez daty i sposobu uzyskania jest w tym
pliku błędem, nie skrótem (zasada 7.1 audytu).

Wpis nie jest usuwany, gdy pomiar zostanie powtórzony — dopisuje się nowy. Widoczna zmiana
wyniku w czasie jest informacją o źródle.

---

## Pomiar 21 — czy blokada sieci w testach współistnieje z wstrzykniętym transportem httpx

**Zmierzone 2026-09-15, 0 żądań.** Wynik: **pozytywny dla `pytest-recording`.**

Żądanie zbudowane przez `kio_tool.httpclient.build_http_client` — czyli przez klienta, który
**zawsze** dostaje wstrzyknięty `AllowedHostsTransport` — zostało przy `addopts =
"--block-network"` zatrzymane wyjątkiem `RuntimeError("Network is disabled")`, a nie błędem
połączenia. Blokada widzi więc ruch mimo warstwy transportu, której architektura 3.4
obawiała się jako punktu rozjazdu z vcrpy.

Środowisko pomiaru: Python 3.12.10, httpx 0.28.1, pytest 9.1.1, pytest-recording 0.13.4,
Windows 11. Test: `tests/test_pomiar21_blokada_sieci.py`.

**Czego ten pomiar NIE rozstrzygnął.** Zablokowanie ruchu i **odtworzenie kasety** to dwa
różne mechanizmy, a zmierzona została tylko pierwsza połowa. Czy nagrana kaseta odtworzy się
przez ten sam wstrzyknięty transport, rozstrzygnie dopiero pierwsza prawdziwa kaseta, która
powstanie przy pomiarze 4b. Do tego czasu `respx` zostaje w zależnościach deweloperskich jako
druga droga; usunięcie go teraz byłoby zamknięciem pytania, które jest wciąż otwarte.

**Usterka po drodze, warta odnotowania.** Pierwsza wersja asercji sprawdzała **nazwę klasy**
wyjątku, a `pytest-recording` zgłasza blokadę jako zwykły `RuntimeError`. Test wyglądał więc
przez chwilę na wynik negatywny pomiaru, choć mechanizm działał. To jest w miniaturze zasada
7.3 zastosowana do samego testu: strażnik, który patrzy na niewłaściwą cechę, nie pilnuje
niczego. Poprawiona wersja sprawdza komunikat i osobno wyklucza `httpx.ConnectError`, czyli
wariant „żądanie jednak wyszło, a odbiła je dopiero sieć".

### Uzupełnienie tego samego dnia: czy blokada sięga poniżej httpx

**Zmierzone 2026-09-15, 0 żądań.** Wynik: **tak, blokada działa na poziomie gniazda.**

Pierwsza wersja tego pomiaru sprawdzała wyłącznie ruch idący przez `httpx`, a to jest połowa
pytania. Gdyby `--block-network` podmieniało tylko transport `httpx`, kanał spoza HTTP —
`ftplib`, `socket` wprost, `urllib` — przechodziłby przez blokadę **niewidziany**, a reguła 20
obejmowałaby tylko tę część ruchu, którą akurat widać.

`socket.create_connection(("127.0.0.1", 9))` pod `--block-network` kończy się tym samym
`RuntimeError("Network is disabled")`, co żądanie przez `httpx`. Blokada jest więc zamkiem na
gnieździe, nie na bibliotece.

Konsekwencja dla reguły 20: `pytest-recording` zamyka **blokadę** dla każdego protokołu,
niezależnie od tego, który kanał wygra po pomiarach 1–3. Otwarta zostaje wyłącznie druga
gwarancja — odtwarzanie **kaset** przez wstrzyknięty transport — którą rozstrzygnie pierwsza
prawdziwa kaseta przy pomiarze 4b. Dopóki nie padnie, `respx` zostaje w zależnościach.

Rozróżnienie „blokada" / „kasety" jako dwóch osobnych gwarancji pochodzi z przeglądu
architektonicznego 2026-09-15, nie z pierwotnego brzmienia pomiaru 21.

---

## Trzy pytania projektowe z przeglądu kodu — rozstrzygnięcia z 2026-09-15

Przegląd kodu wskazał trzy miejsca, które nie są usterkami, tylko decyzjami. Właściciel
przyjął rekomendacje 2026-09-15.

**1. `make_console()` idzie w `markup=False, highlight=False`. Wykonane.**
Reguła 10 („napis spoza programu staje się drukowalny wyłącznie przez `safe`") miała dotąd
jednego strażnika: skan AST. Skan łapie przeoczenia, a `KioError` deklaruje w docstringu, że
komunikat jest przeznaczony dla użytkownika — więc pierwsze `console.print(f"Błąd: {e}")`
w warstwie CLI odtworzyłoby dziurę z CEIDG. Wyłączenie znaczników na poziomie konsoli zamienia
regułę z własności skanu w własność obiektu. Koszt: własne komunikaty podają styl jawnie
(`Text`, `style=`) zamiast znacznikami w napisie — przy pustej jeszcze warstwie `ui/` jest to
koszt zerowy, po jej powstaniu byłby to koszt przepisania każdego ekranu. Strażnik:
`tests/test_richtext.py::test_konsola_programu_nie_interpretuje_znacznikow`, zweryfikowany
mutacją.

**2. `normalize_signature` zostaje przy wyszukiwaniu w napisie. Do ADR-001.**
Funkcja na wejściu wielosygnaturowym zwraca pierwszą sygnaturę i nie sygnalizuje, że zgubiła
drugą sprawę — czyli popełnia błąd, przed którym ten moduł ma chronić. Wyszukiwanie w środku
napisu jest jednak niezbędne dla `parser/cite.py`, który szuka sygnatur wplecionych w zdania
uzasadnienia. Rozstrzygnięcie robocze: kompromis zostaje, jest opisany w docstringu jako
hazard, a reguła brzmi „napis poziomu dokumentu idzie wyłącznie przez
`normalize_signature_list`". Strażnik istnieje i przybija złe zachowanie jawnie. Czy funkcja
ma zamiast tego **odrzucać** wejście wielosygnaturowe, rozstrzyga ADR-001 — razem z pomiarem
7 (sprostowania), bo obie rzeczy dotyczą tego, czym jest tożsamość dokumentu.

**3. Pisownia referencji w `document_id` jest sprawą kanału. Do ADR-001.**
Dziś `document_id` sprowadza do małych liter nazwę kanału, ale nie referencję. Dla `uzp:9620`
i `saos:354301` jest to obojętne (identyfikatory liczbowe), dla sluga `atlas:kio-827-18`
realne: dwie pisownie dałyby dwa klucze główne na jeden dokument, czyli minę 1 z CEIDG.
Rekomendacja do ADR-001: **normalizacja per kanał, zadeklarowana w `contract.yaml`** (pole
w rodzaju `ref_case: preserve | lower`), bo zasada „zapisuj tak, jak przyszło" jest słuszna
dla nieprzezroczystego identyfikatora liczbowego i błędna dla sluga tekstowego. Jedna reguła
dla obu przypadków byłaby błędna w jednym z nich. Do czasu ADR stan bieżący jest przybity
testem, więc nie zmieni się mimochodem.
