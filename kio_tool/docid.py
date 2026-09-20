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
from dataclasses import dataclass
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
#
# Koniec roku jest `(?!\d)`, nie `\b`: w uzasadnieniach stoi „KIO 1234/23do postępowania"
# (2 wystąpienia w korpusie 443 dokumentów, 2026-09-19, 0 żądań) — ekstrakcja z PDF-a zjada
# spację, a `\b` między cyfrą a literą nie pada, więc sygnatura przepadała w ciszy.
# Pomiar 25 (2026-09-20, 0 żądań) dołożył do tego wzorca cztery rodziny postaci, wszystkie
# odczytane z cytowań korpusu, żadna z pamięci: repertoria kontrolne `KIO/KD` (9) i `KIO/W` (1),
# ukośnik przed numerem `KIO/582/11` (3), rok czterocyfrowy `KIO 1460/2011` (2). Rok jest
# skracany do dwóch cyfr tak samo jak w sygnaturze sądu — skrócenie nie dokłada informacji.
_WZOR_KIO = re.compile(
    r"\b(?P<prefiks>KIO\s*/\s*UZP|KIO\s*/\s*KU|KIO\s*/\s*KD|KIO\s*/\s*W|KIO)"
    r"\s*/?\s*(?P<numer>\d{1,5})\s*/\s*(?P<rok>\d{2}(?:\d{2})?)(?!\d)",
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
    return Signature(f"{prefiks} {numer}/{dopasowanie.group('rok')[-2:]}")


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


# --------------------------------------------------------------- sygnatury innych organów

RodzajSygnatury = Literal[
    "kio", "kio_bez_repertorium", "so", "sa", "sn", "nsa", "wsa", "uzp_zo", "tsue", "inne"
]
"""Organ, którego sygnaturę rozpoznano — kolumna `citations.rodzaj` (architektura 4.4, ADR-0006).

`nsa` stoi osobno, choć architektura 4.4 wymienia `kio | so | sn | sa | tsue | inne`: sygnatury
NSA wystąpiły w korpusie (`GSK`, `OSK`, `FSK` — 10 trafień, 2026-09-19), a wrzucone do `inne`
zlewałyby się z sygnaturami nierozpoznanymi.

`kio_bez_repertorium` jest rodzajem **osobnym i to jest jego cała treść** (decyzja właściciela
2026-09-20 przy pomiarze 25). Postać `sygn. akt: 3376/23` — numer i rok bez żadnego repertorium —
wystąpiła 29 razy w cytowaniach korpusu i jest niemal na pewno sygnaturą Izby, ale „niemal na
pewno" nie jest odczytem: sprawdzenie na korpusie potwierdziło **11 z 29** numerów odpowiednikiem
`KIO N/RR` gdzie indziej, a pozostałych 18 nie potwierdza nic poza kontekstem. Sygnatura
kanoniczna jest więc zapisana jako `KIO N/RR`, żeby łączyła się z indeksem, a organ **dopisany
z kontekstu, nie odczytany z zapisu** stoi w rodzaju — czytelnik raportu i każdy przyszły
konsument widzi tę różnicę i może te cytowania wykluczyć jednym warunkiem. Wrzucone do `kio`
byłyby nie do odróżnienia od odczytanych; zostawione jako nierozpoznane byłyby stratą 37 %
największej rodziny.

`wsa` i `uzp_zo` doszły z pomiarem 25 (2026-09-20). Wojewódzkie sądy administracyjne piszą
repertorium z kodem siedziby po ukośniku (`II SA/Op 4/18`, 7 trafień), więc nie mieszczą się
w zbiorze repertoriów bezukośnikowych; Zespół Arbitrów UZP (`UZP/ZO/0-62/07`, 3 trafienia) jest
poprzednikiem Izby, a nie Izbą — wrzucony do `kio` twierdziłby, że orzekał organ, który wtedy
nie istniał."""

# Repertoria — **z pomiaru**, nie z pamięci: każdy wpis wystąpił w uzasadnieniach korpusu
# 443 dokumentów (2026-09-19, 0 żądań) z liczbą trafień w nawiasie przy grupie. Repertorium
# spoza tych zbiorów daje rodzaj `inne` z sygnaturą kanoniczną — nie zgadujemy sądu z litery.
_REPERTORIA_SN = frozenset(
    {"CSK", "CZP", "CKN", "CK", "CRN", "CR", "CZ", "PK", "PKN", "SK", "PZ", "CKU", "CSR", "UKN"}
)
"""Sąd Najwyższy (CSK 28, CZP 26, CKN 15, CK 12, CRN 5, CR 3, CZ 3, PK 3, PKN 2, pozostałe po 1)."""
_REPERTORIA_SA = frozenset({"ACa", "AGa", "ACr", "ACz", "AGz"})
"""Sądy apelacyjne (ACa 12, AGa 6 — w tym `Aga` 4, ACr 1). Porównanie bez wielkości liter."""
_REPERTORIA_SO = frozenset({"Ga", "Zs", "Ca", "GC", "C", "Gz", "Cz", "AmA", "AmZ", "AmR", "Ns"})
"""Sądy okręgowe, w tym Sąd Zamówień Publicznych (`Zs`, 45) i SOKiK (`AmA`/`AmZ`/`AmR`, 6)."""
_REPERTORIA_NSA = frozenset({"GSK", "OSK", "FSK", "FPS", "OPS", "GPS"})
"""Naczelny Sąd Administracyjny (GSK 6, OSK 2, FSK 2, FPS 1)."""

_ORGANY: tuple[tuple[frozenset[str], RodzajSygnatury], ...] = (
    (_REPERTORIA_SN, "sn"),
    (_REPERTORIA_SA, "sa"),
    (_REPERTORIA_SO, "so"),
    (_REPERTORIA_NSA, "nsa"),
)
_KANON_REPERTORIUM: dict[str, tuple[str, RodzajSygnatury]] = {
    r.casefold(): (r, rodzaj) for zbior, rodzaj in _ORGANY for r in zbior
}
"""Repertorium bez wielkości liter → pisownia kanoniczna i organ (`Aga` → `AGa`, `sa`)."""

_WZOR_SADU = re.compile(
    r"\b(?P<wydzial>[IVXL]{1,6})\s+(?P<rep>[A-Z][A-Za-z]{0,4})\s+(?P<numer>\d{1,6})\s*/\s*"
    r"(?P<rok>\d{2}(?:\d{2})?)(?!\d)"
)
"""Sygnatura sądu: wydział rzymski, repertorium, numer, rok — `XXIII Zs 12/22`, `III CZP 56/17`."""

_WZOR_WSA = re.compile(
    r"\b(?P<wydzial>[IVXL]{1,6})\s+(?P<rep>SA|GSK)\s*/\s*(?P<siedziba>[A-Za-z]{2})\s+"
    r"(?P<numer>\d{1,6})\s*/\s*(?P<rok>\d{2}(?:\d{2})?)(?!\d)"
)
"""Sąd administracyjny z kodem siedziby: `II SA/Op 4/18`, `VI SA/Wa 2187/21` (pomiar 25).

`GSK` z kodem siedziby daje `nsa`, bo to repertorium Naczelnego Sądu Administracyjnego i stoi
już w `_REPERTORIA_NSA`; `SA` z kodem siedziby daje `wsa`. Kod siedziby wraca **wielką pierwszą
literą i małą drugą** (`Op`, `Wa`), bo tak zapisuje go sąd, a `WA` i `Wa` byłyby dwiema
sprawami."""

_WZOR_SAM_NUMER = re.compile(r"\s*(?P<numer>\d{1,4})\s*/\s*(?P<rok>\d{2})(?!\d)")
"""Numer i rok bez repertorium — **wyłącznie tuż za zapowiedzią `sygn. akt`**.

Ten wzorzec nie ma prawa chodzić po całym tekście: `1/2`, `226/1`, numery stron, kwoty i daty
wyglądają tak samo. Kotwicą jest zapowiedź, a jedynym wywołującym `parser/cite.py`; dlatego
funkcja niżej bierze pozycję, od której ma dopasować, zamiast przeszukiwać napis."""


def numer_bez_repertorium(tekst: str, od: int) -> TrafienieSygnatury | None:
    """Sygnatura Izby bez repertorium, dopasowana **od pozycji `od`** (koniec zapowiedzi).

    Zwraca rodzaj `kio_bez_repertorium`, nie `kio`: organ pochodzi z kontekstu — z tego, że
    zapowiedź stoi w uzasadnieniu Izby — a nie z zapisu. Różnica jest zapisana w rodzaju, bo
    tylko tam przeżyje drogę do raportu i do każdego przyszłego czytelnika indeksu.
    """
    dopasowanie = _WZOR_SAM_NUMER.match(tekst, od)
    if dopasowanie is None:
        return None
    kanon = f"KIO {int(dopasowanie.group('numer'))}/{dopasowanie.group('rok')}"
    return TrafienieSygnatury(dopasowanie.start(), dopasowanie.end(), "kio_bez_repertorium", kanon)


_WZOR_UZP_ZO = re.compile(
    r"\bUZP\s*/\s*ZO\s*/\s*0\s*-\s*(?P<numer>\d{1,4})\s*/\s*(?P<rok>\d{2})(?!\d)",
    re.IGNORECASE,
)
"""Zespół Arbitrów UZP — poprzednik Izby: `UZP/ZO/0-62/07` (3 trafienia, pomiar 25)."""

_WZOR_TSUE = re.compile(r"\b(?P<sad>[CT])\s*[-‑–]\s*(?P<numer>\d{1,4})\s*/\s*(?P<rok>\d{2})(?!\d)")
"""Sprawa TSUE: `C-652/22` (59 trafień w korpusie, 2026-09-19). `T-` to Sąd Unii Europejskiej.

**Myślnik jest obowiązkowy i to jest rozstrzygnięcie pomiaru 25 (2026-09-20), nie przeoczenie.**
W korpusie stoją trzy sygnatury TSUE zapisane bez myślnika (`C 106/77` Simmenthal ×2, `C 689/13`
PFE), więc tolerancja wyglądała na darmowy zysk. Przeliczenie całego korpusu z myślnikiem
opcjonalnym dało **3 trafienia poprawne i 12 fałszywych**: dziewięć to klasy betonu z kosztorysów
(`C12/15`, `C20/25`, `C30/37`, `C35/45`, `C50/30` — PN-EN 206 zapisuje je dokładnie tak), a trzy
to numery Dziennika Urzędowego UE serii C (`2014/C 92/01`, `2021/C 91/01`). Odwołania o roboty
drogowe są pełne jednego i drugiego. Trzy odzyskane cytowania nie są warte dwunastu fałszywych
krawędzi w indeksie, więc te trzy zostają nierozpoznane — jawna dziura zamiast cichej podmiany."""


@dataclass(frozen=True)
class TrafienieSygnatury:
    """Sygnatura znaleziona w tekście: przedział w **podanym** napisie, organ, postać kanoniczna."""

    start: int
    koniec: int
    rodzaj: RodzajSygnatury
    kanon: str


def znajdz_sygnatury(tekst: str) -> list[TrafienieSygnatury]:
    """Wszystkie sygnatury KIO, sądów i TSUE w tekście, w kolejności wystąpienia.

    Jedyny normalizator sygnatur innych organów, z tego samego powodu co `normalize_signature`
    dla KIO (reguła 14): `parser/cite.py` ma zapisywać postać kanoniczną, a nie składać ją sam.
    Trafienia na siebie nie nachodzą — przy kolizji wygrywa wcześniejsze, a przy równym
    początku dłuższe.
    """
    trafienia: list[TrafienieSygnatury] = []
    for m in _WZOR_KIO.finditer(tekst):
        sygnatura_kio = normalize_signature(m.group(0))
        if sygnatura_kio is not None:
            trafienia.append(TrafienieSygnatury(m.start(), m.end(), "kio", sygnatura_kio))
    for m in _WZOR_SADU.finditer(tekst):
        nieznane: tuple[str, RodzajSygnatury] = (m.group("rep"), "inne")
        repertorium, rodzaj = _KANON_REPERTORIUM.get(m.group("rep").casefold(), nieznane)
        # Rok czterocyfrowy skracany do dwóch: `X Ga 7/2010` i `X Ga 7/10` to jedna sprawa, a pięć
        # takich par w korpusie (przegląd kodu 2026-09-19) rozdzielało się w indeksie cytowań.
        # Skrócenie nie dokłada informacji — w odróżnieniu od rozwinięcia, którego moduł nie robi.
        sad = f"{m.group('wydzial')} {repertorium} {int(m.group('numer'))}/{m.group('rok')[-2:]}"
        trafienia.append(TrafienieSygnatury(m.start(), m.end(), rodzaj, sad))
    for m in _WZOR_WSA.finditer(tekst):
        siedziba = m.group("siedziba").capitalize()
        rodzaj_sadu: RodzajSygnatury = "nsa" if m.group("rep").upper() == "GSK" else "wsa"
        sad_adm = (
            f"{m.group('wydzial')} {m.group('rep').upper()}/{siedziba} "
            f"{int(m.group('numer'))}/{m.group('rok')[-2:]}"
        )
        trafienia.append(TrafienieSygnatury(m.start(), m.end(), rodzaj_sadu, sad_adm))
    for m in _WZOR_UZP_ZO.finditer(tekst):
        zespol = f"UZP/ZO/0-{int(m.group('numer'))}/{m.group('rok')}"
        trafienia.append(TrafienieSygnatury(m.start(), m.end(), "uzp_zo", zespol))
    for m in _WZOR_TSUE.finditer(tekst):
        sprawa = f"{m.group('sad')}-{int(m.group('numer'))}/{m.group('rok')}"
        trafienia.append(TrafienieSygnatury(m.start(), m.end(), "tsue", sprawa))
    trafienia.sort(key=lambda t: (t.start, -(t.koniec - t.start)))
    wynik: list[TrafienieSygnatury] = []
    for trafienie in trafienia:
        if wynik and trafienie.start < wynik[-1].koniec:
            continue
        wynik.append(trafienie)
    return wynik


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
