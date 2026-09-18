# ADR-0001: Tożsamość dokumentu w kanale pierwszego zapisu

Data: 2026-09-18
Status: accepted (2026-09-18, decyzja właściciela — plan z tego dnia zatwierdzony, polecenie „rozpocznij pracę od razu"; pomiar 3a wykonany 2026-09-18, nawiasy z sekcji 2 wypełnione z odczytu). Przyjęcie odblokowuje `kio_tool/store.py`
Autor: P0w3r223
Related to: `docs/adr/0005_bramka_per_kanal.md` (Z-4), `docs/adr/0004_wybor_kanalu.md`, `docs/decisions.md` (rozstrzygnięcia 2 i 3 z 2026-09-15; sekcja „Status pomiarów"), `ARCHITEKTURA_KIO_TOOL.md` (4.4 model danych), `AUDYT_KIO_ORZECZENIA.md` (11, mina 1), `kio_tool/docid.py`, `tests/test_bramki_faz.py`

---

## 1. Kontekst: mina 1 i dlaczego ten ADR stoi przed `store.py`

W `ceidg-tool` jeden wpis miał dwie pisownie identyfikatora, klucz główny był wrażliwy na
wielkość liter, a jedna noc kosztowała 2 681 żądań i zero użytecznych rekordów (audyt 11,
mina 1). Zabrakło tam jednej rzeczy: rozstrzygnięcia, czym jest tożsamość rekordu, **przed**
pierwszym zapisem do bazy. Bramka `store.py` → ADR-0001 (`tests/test_bramki_faz.py`) jest
mechaniczną postacią tej kolejności i ten ADR nie zmienia jej ani o krok.

Do 2026-09-18 wejściami tego ADR-a były pomiary 7 (sprostowania), 19 (stabilność bajtów
`ContentHtml`, wymaga doby odstępu) i 17 (postaci sygnatur). ADR-0005 (Z-4) zawęził je: pomiary
7 i 19 dotyczą kanału `uzp`, którego nie ma na ścieżce do pierwszego korpusu, a klucz wersji
`(doc_id, content_sha256)` jest poprawny **przy obu wynikach pomiaru 19** — niestabilny render
daje nadmiarowe wiersze wersji, czyli szum, nie utratę tożsamości. Ten ADR rozstrzyga tożsamość
**w kanale pierwszego zapisu**, czyli `atlas`, i zapisuje, co przy drugim kanale trzeba będzie
rozstrzygnąć ponownie.

---

## 2. Rozstrzygnięcia

### 2.1 Dokument jest jednostką, sygnatura jest etykietą

Jednostką korpusu jest **dokument** (jedno orzeczenie tak, jak przyszło z kanału), a nie
sygnatura. Relacja dokument ↔ sygnatura jest wiele-do-wielu (architektura 4.4: `documents`,
`cases`, `document_cases`). Dowody wielosygnaturowości stoją w architekturze 4.4 i nie są tu
powtarzane; kolektor Legal Data Hunter bierze tylko pierwszą sygnaturę i przez to gubi sprawy —
to jest błąd, przed którym ten podział chroni.

Dla `atlas` lista sygnatur dokumentu powstaje z pola `signatures` rekordu (lista napisów;
w stu rekordach listy z pomiaru 3a: 93 z jedną sygnaturą, 6 z dwiema, 1 z trzema, np.
`kio-388-10` → `["KIO 388/10", "KIO 390/10"]`; pierwszy element równy `primary_signature` —
zmierzone 2026-09-18, 2 żądania), z `primary_signature` jako pierwszą. Pole `signatures` jest
i w rekordzie listy, i w rekordzie dokumentu.
Napis poziomu dokumentu idzie wyłącznie przez `docid.normalize_signature_list`;
`normalize_signature` zostaje wyszukiwaniem w napisie dla przyszłego `parser/cite.py`
(rozstrzygnięcie 2 z 2026-09-15, `decisions.md`) — kompromis opisany w docstringu jako hazard
i przybity testem, nie zmieniany tym ADR-em.

### 2.2 `doc_id` i pisownia referencji: `ref_case` per kanał

`doc_id = document_id(source, source_ref)` — jedyny producent tożsamości to `kio_tool/docid.py`
(reguła 14). Dla `atlas` referencją jest `slug` z rekordu listy; postać sluga (zmierzone
2026-09-18, pomiar 3a, 100 rekordów listy i rekord dokumentu): `kio-<numer>-<rr>`, czyli
sygnatura główna małymi literami z myślnikami zamiast spacji i ukośnika, alfabet `[a-z0-9-]`,
długość 9–11 znaków, bez wielkich liter w 100 na 100 przypadków; przykład z odczytu:
`kio-1205-20` ↔ `KIO 1205/20`. Rekord dokumentu niesie ponadto `document_id` (liczba, np.
`13053`) będące identyfikatorem tego samego orzeczenia w wyszukiwarce UZP (`source_url` =
`https://orzeczenia.uzp.gov.pl/Home/PdfContent/13053?Kind=KIO`) — to jest wskazówka dla
przyszłego `porownaj`, a nie założona równoważność (sekcja 2.4).

Rozstrzygnięcie 3 z 2026-09-15 (`decisions.md`) mówi, że pisownia referencji jest sprawą kanału:
„zapisuj tak, jak przyszło" jest słuszne dla nieprzezroczystego identyfikatora liczbowego
(`uzp:9620`) i błędne dla sluga tekstowego, gdzie dwie pisownie dałyby dwa klucze główne na
jeden dokument — minę 1. Dlatego:

- `contract.yaml` kanału deklaruje `ref_case: preserve | lower`; dla `atlas` — `lower`;
- `docid.document_id(source, source_ref, *, ref_case)` stosuje deklarację kanału; parametr jest
  wymagany (bez wartości domyślnej), żeby kanał dopisany jutro musiał tę decyzję podjąć
  jawnie, a nie odziedziczyć;
- test w `tests/test_docid.py` przybija: dwie pisownie tego samego sluga przy `lower` dają jeden
  `doc_id`, a przy `preserve` — dwa (stan przybity, nie pochwalony).

### 2.3 Treść jest wersjonowana i nigdy nadpisywana

`raw_versions (doc_id, content_sha256)` jest kluczem głównym; `content_bytes` to bajty
dokładnie takie, jakie przyszły po drucie (reguła 19 w brzmieniu ADR-0005 Z-5 — pole
o nieznanym pochodzeniu odcina się na wyjściu z kanału, nie przed zapisem). `INSERT OR IGNORE`
sprawia, że przerwany i wznowiony przebieg nie tworzy duplikatu nawet przy nieaktualnym punkcie
kontrolnym — to jest cała treść bramki fazy 1 po stronie magazynu. Ta sama sprawa pobrana dwa
razy z tą samą treścią daje jeden wiersz; z inną treścią — drugą wersję, nigdy nadpisanie.

### 2.4 Co ten ADR zostawia drugiemu kanałowi

- **Sprostowania (pomiar 7)** i **stabilność bajtów (pomiar 19)** — polityka wersji kanału `uzp`
  (ADR-0005 Z-4). Dla `atlas` każda zmiana treści jest nową wersją bez pytania, dlaczego zaszła;
  to jest stan przyjęty, nie rozstrzygnięty.
- **Równoważność między kanałami** (`equivalences`) jest **stwierdzana** przez `porownaj`,
  nigdy zakładana (architektura 4.4). Ten ADR nie mówi, kiedy `atlas:x` i `uzp:9620` są tym
  samym orzeczeniem — bo przy jednym kanale nie ma czego stwierdzać.

---

## 3. Wejścia i ich status

| Wejście | Status | Gdzie |
|---|---|---|
| Pomiar 3a: postać `slug`, pola rekordu, pole z treścią | **wykonany 2026-09-18, 2 żądania** — pełny tekst w `full_text`, sygnatury w `signatures`, slug jak w sekcji 2.2 | `docs/decisions.md`, `## Pomiar 3a` |
| Rozstrzygnięcie 2 (`normalize_signature` zostaje wyszukiwaniem) | przyjęte 2026-09-15 | `docs/decisions.md` |
| Rozstrzygnięcie 3 (`ref_case` per kanał) | przyjęte 2026-09-15, tu wykonane | `docs/decisions.md` |
| Pomiar 17: postaci sygnatur | **częściowo wykonany 2026-09-18, zero dodatkowych żądań** na stu rekordach listy: trzy postaci `KIO 9999/99` (86), `KIO 999/99` (13), `KIO 99/99` (1), bez postaci `KIO/UZP` i `KIO/KU` w tej próbce (rocznik 2010); dopełnienie po pierwszym przebiegu, wynik dopisywany tu z datą jako uzupełnienie, nie warunek | `docs/decisions.md`, `## Pomiar 17` |

Nawiasy w sekcji 2 zostały wypełnione 2026-09-18 z odczytu z datą; sygnatur i nazw pól nie wolno
tu wpisać z pamięci (zasada 7.1 audytu) i żadna nie została.
