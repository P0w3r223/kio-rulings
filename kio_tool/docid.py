"""Jedyny producent kanonicznej tożsamości — reguła 14, mina 1.

W `ceidg-tool` odpowiednik tego modułu powstał po awarii: jeden wpis miał dwie pisownie
identyfikatora, bo jeden punkt końcowy zwracał wielkimi literami, drugi małymi, a klucz
główny był wrażliwy na wielkość liter. Każdy zmieniony wpis zapisywał się dwa razy, cache
nigdy nie trafiał, jedna noc kosztowała 2 681 żądań i zero użytecznych rekordów.

Tutaj ten sam kształt problemu wraca w dwóch miejscach naraz: sygnatura („KIO 827/18")
i wewnętrzny identyfikator liczbowy w adresie („9620"). Moduł produkuje oba i jest dla nich
jedynym źródłem.

**Czego ten moduł świadomie NIE robi**, bo każde z tych działań dokładałoby informację,
której w źródle nie ma:

- nie rozwija dwucyfrowego roku do czterocyfrowego. „KIO 827/18" zostaje z „18". Rozwinięcie
  wymaga wiedzy, że nie ma sygnatur sprzed 2007 — a Izba zaczęła orzekać 5 grudnia 2007 i to
  jest fakt o organie, nie o zapisie sygnatury;
- nie sprawdza, czy sprawa istnieje. Sygnatura `KIO 1234/25` wygląda tak samo niezależnie od
  tego, czy istnieje (zasada 7.1) — rozstrzyga to korpus, nie wyrażenie regularne;
- nie zgaduje organu z samego numeru. Prefiks jest częścią zapisu i musi w nim stać.

Zbiór postaci obsługiwanych przez ten moduł pochodzi wyłącznie z odczytów udokumentowanych
w audycie i przeglądzie, z datami — nigdy z pamięci modelu. Pomiar 17 rozszerza go
o postaci znalezione w listingach wyników, a `parser/cite.py` (pomiar 22) o postaci
z uzasadnień, czyli o największy dostępny zbiór testowy.
"""

from __future__ import annotations

import re
from typing import Literal, NewType

from .errors import IdentityError
from .safetext import strip_control

Signature = NewType("Signature", str)
"""Kanoniczna postać sygnatury. Typ własny, bo reguły 14 pilnuje `mypy --strict`, nie skan AST:
skan widzi importy, a nie to, czy ktoś zbudował identyfikator konkatenacją napisów."""

DocId = NewType("DocId", str)
"""Kanoniczny identyfikator dokumentu w korpusie: `"{source}:{source_ref}"`."""

SourceName = NewType("SourceName", str)

RefCase = Literal["lower", "preserve"]
"""Jak kanał traktuje wielkość liter w referencji — deklaracja z `contract.yaml` (ADR-0001 2.2).

`lower` sprowadza referencję do małych liter, `preserve` zostawia ją tak, jak przyszła.
Rozstrzygnięcie 3 z 2026-09-15 mówi, że pisownia referencji jest sprawą kanału: „zapisuj tak,
jak przyszło" jest słuszne dla nieprzezroczystego identyfikatora liczbowego (`uzp:9620`)
i błędne dla sluga tekstowego, gdzie dwie pisownie dałyby dwa klucze główne na jeden dokument —
czyli minę 1 z nagłówka tego modułu.
"""

# `KIO 827/18`, `KIO/UZP 1482/08`, `KIO/KU 97/13` — wszystkie trzy z odczytów z datą.
#
# Separator jest opcjonalny (`\s*`), więc wzorzec złapie też postać sklejoną „KIO113/22".
# **Tej postaci nikt w tym projekcie nie widział w źródle.** Pierwsza wersja tego komentarza
# uzasadniała opcjonalność zdaniem o „złej konwersji PDF" — twierdzeniem bez daty i bez
# wskazania dokumentu, czyli dokładnie tym, czego zakazuje zasada 7.1, i to w module, który
# tę zasadę cytuje w nagłówku. Opcjonalność zostaje jako świadoma tolerancja wejścia dla
# `parser/cite.py`, nie jako opis zaobserwowanego zapisu; czy postać sklejona w ogóle
# występuje, rozstrzygnie pomiar 22 na prawdziwych uzasadnieniach.
_WZOR_KIO = re.compile(
    r"\b(?P<prefiks>KIO\s*/\s*UZP|KIO\s*/\s*KU|KIO)\s*(?P<numer>\d{1,5})\s*/\s*(?P<rok>\d{2})\b",
    re.IGNORECASE,
)

_SPACJE = re.compile(r"\s+")


def normalize_signature(raw: str) -> Signature | None:
    """Kanonizuje pojedynczą sygnaturę KIO. Zwraca `None`, gdy napis nią nie jest.

    Kanoniczna postać: prefiks wielkimi literami bez spacji wokół ukośnika, jedna spacja,
    numer bez zer wiodących, ukośnik, dwucyfrowy rok. `„  kio/uzp  1482 / 08 "` daje
    `„KIO/UZP 1482/08"`.

    Zwraca `None`, a nie rzuca, bo wywołuje to także `parser/cite.py` na tekście uzasadnienia,
    gdzie większość napisów sygnaturą nie jest. Cytowanie, którego nie da się znormalizować,
    ma trafić do tabeli `citations` z `signature_norm = NULL` i zostać **policzone** w raporcie
    pokrycia — cicha strata jest tu gorsza niż jawna dziura.

    **Hazard, który ta funkcja nosi w sobie i którego nie ukrywa.** Szuka pierwszego
    dopasowania w napisie, więc na wejściu wielosygnaturowym („KIO 233/18, KIO 234/18",
    tytuł rekordu SAOS 354301) zwróci `KIO 233/18` i **nie powie, że zgubiła drugą sprawę** —
    czyli popełni dokładnie ten błąd, przed którym ten moduł ma chronić i za który cudzy
    kolektor KIO gubi sprawy (architektura 3.1). Wyszukiwanie w środku napisu jest tu
    jednocześnie niezbędne, bo bez niego `parser/cite.py` nie znajdzie sygnatury wplecionej
    w zdanie „(tak: wyrok z dnia 27 stycznia 2022 r., KIO 113/22)".

    Reguła wynikająca z tego kompromisu: **napis poziomu dokumentu idzie wyłącznie przez
    `normalize_signature_list`.** Tę funkcję wolno wołać na fragmencie, co do którego wiadomo,
    że niesie jedną sygnaturę. Czy zamiast tego powinna odrzucać wejście wielosygnaturowe,
    jest pytaniem do ADR-001, nie do tego docstringa.
    """
    dopasowanie = _WZOR_KIO.search(_SPACJE.sub(" ", raw.strip()))
    if dopasowanie is None:
        return None
    prefiks = _SPACJE.sub("", dopasowanie.group("prefiks")).upper()
    numer = str(int(dopasowanie.group("numer")))
    return Signature(f"{prefiks} {numer}/{dopasowanie.group('rok')}")


def normalize_signature_list(raw: str) -> list[Signature]:
    """Wszystkie sygnatury KIO w napisie, w kolejności wystąpienia, bez powtórzeń.

    Istnieje, bo **dokument bywa nośnikiem kilku spraw** i to jest mina 1 audytu potwierdzona
    trzema niezależnymi dowodami: pliki `2021_1820_1821_1834.pdf` z listingu FTP, lista
    „Sygnatura akt / Sposób rozstrzygnięcia" na stronie `Details`, rekord SAOS zatytułowany
    „KIO 233/18, KIO 234/18" oraz zdanie z dokumentacji SAOS: „orzeczenie czasem może dotyczyć
    wielu spraw (np. orzeczenia KIO)".

    Cudzy kolektor KIO bierze w tym miejscu **pierwszy** element listy i przez to gubi drugą
    sprawę (architektura 3.1). Ta funkcja nie ma wariantu zwracającego jedną sygnaturę —
    „która jest główna" jest decyzją zapisywaną w `document_cases.is_primary`, a nie cechą
    napisu.
    """
    widziane: dict[str, Signature] = {}
    for dopasowanie in _WZOR_KIO.finditer(_SPACJE.sub(" ", raw)):
        sygnatura = normalize_signature(dopasowanie.group(0))
        if sygnatura is not None and sygnatura not in widziane:
            widziane[sygnatura] = sygnatura
    return list(widziane.values())


def normalize_source_name(source: str) -> SourceName:
    """Kanoniczna nazwa kanału: małe litery, bez spacji, bez dwukropka.

    Funkcja jest **publiczna**, i to jest poprawka z przeglądu kodu 2026-09-15. Pierwsza
    wersja kanonizowała nazwę kanału wewnątrz `document_id` i nie zwracała wyniku tej
    kanonizacji, więc kolumnę `documents.source` zapisywał ktoś inny, najpewniej wartością
    nieznormalizowaną — a wtedy przedrostek `doc_id` i kolumna niosą dwie pisownie jednego
    kanału. To jest mina 1 w dokładnie tej postaci, którą opisuje nagłówek tego modułu, tyle
    że schowana o jedno wywołanie dalej. Jeden producent tożsamości znaczy też jeden
    producent nazwy kanału.
    """
    kanal = _SPACJE.sub("", source.strip()).lower()
    if not kanal:
        raise IdentityError("Pusta nazwa kanału; tożsamość dokumentu nie ma przedrostka.")
    if ":" in kanal:
        raise IdentityError(
            f"Nazwa kanału nie może zawierać dwukropka: {source!r}. Dwukropek rozdziela "
            "kanał od referencji w `doc_id`, więc nazwa z dwukropkiem czyni identyfikator "
            "niejednoznacznym."
        )
    return SourceName(kanal)


def document_id(source: SourceName, source_ref: str, *, ref_case: RefCase) -> DocId:
    """Kanoniczny identyfikator dokumentu: `„uzp:9620"`, `„atlas:kio-827-18"`, `„saos:354301"`.

    Sygnatura **nie jest** tożsamością dokumentu i to jest rozstrzygnięcie, nie wygoda:
    jeden dokument nosi kilka sygnatur, a jedna sygnatura bywa na kilku dokumentach
    (postanowienie i wyrok w tej samej sprawie; sprostowanie, jeśli publikowane osobno —
    pomiar 7). Tożsamość niesie para `(kanał, identyfikator w kanale)`, a to, że dwa kanały
    opisują to samo orzeczenie, jest **stwierdzane** w tabeli `equivalences` przez polecenie
    `porownaj`, nigdy zakładane.

    `ref_case` jest **wymagany i bez wartości domyślnej** (ADR-0001 2.2, przyjęty 2026-09-18):
    kanał dopisany jutro musi tę decyzję podjąć jawnie, a nie odziedziczyć. Wartość pochodzi
    z `contract.yaml` kanału; dla `atlas` jest to `lower`, bo slug jest sygnaturą główną małymi
    literami (100 na 100 rekordów pomiaru 3a) i druga pisownia byłaby drugim kluczem głównym.
    Kanał sprowadzany jest do małych liter zawsze — po tej stronie nie ma czego deklarować.
    """
    kanal = normalize_source_name(source)
    ref = strip_control(source_ref).strip()
    if not ref:
        raise IdentityError(
            f"Pusty identyfikator dokumentu w kanale {kanal!r}. Kanał zwrócił kandydata bez "
            "referencji — to jest usterka kontraktu źródła, nie dokument."
        )
    if ref != source_ref.strip():
        raise IdentityError(
            f"Identyfikator dokumentu z kanału {kanal!r} zawiera znaki sterujące: "
            f"{source_ref!r}. Tożsamość trafia do klucza głównego, do arkusza i na ekran, "
            "więc nie przechodzi przez neutralizator po drodze — musi być czysta u wejścia."
        )
    if ref_case == "lower":
        ref = ref.lower()
    return DocId(f"{kanal}:{ref}")
