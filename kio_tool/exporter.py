"""Eksport korpusu: skoroszyt, CSV, JSONL i katalog Markdown — każdy z blokiem atrybucji.

Reguła 15 jest tu warunkiem ustawowym, nie konwencją redakcyjną (audyt 8.3, art. 15 ust. 1 pkt 4):
**każdy** format niesie przy każdym orzeczeniu sygnaturę, datę wydania i oznaczenie organu
(`ORGAN`), a przy rekordach z Atlasu — linię atrybucji z `contract.yaml` (`licencja.atrybucja`,
CC BY 4.0). Strażnikiem jest `tests/test_attribution.py`, nie skan granic: to zachowanie eksportu,
nie krawędź importu.

Reguła 19 (ADR-0005 Z-5) ma tu dwie postaci. Arkusz `Orzeczenia`, CSV i Markdown biorą pola
wyłącznie ze `Szczegoly` (`parser/details.py`) — struktury bez miejsca na `thesis*` ani inne pola
opracowania Atlasu, więc nie wchodzą one do korpusu pochodnego nie dzięki czyjejś pamięci, tylko
dlatego, że nie ma pola, którym mogłyby pójść. JSONL jest natomiast **zrzutem surowca**, nie
korpusem pochodnym: niesie rekord kanału w całości (razem z `full_text` i z polami odrzuconymi),
bo jego zadaniem jest odtworzenie tego, co przyszło po drucie, z `sha256` do sprawdzenia.

`full_text` **nie wchodzi do arkusza**: komórka Excela mieści 32 767 znaków, a orzeczenie bywa
dłuższe — arkusz z obciętą treścią wyglądałby na kompletny. Treść jest w JSONL i w Markdown.

Dane są wrogie (audyt 4.11): komórka tekstowa przechodzi przez `safetext.sanitize_text` (znaki
sterujące i prefiksy formuł), a plik powstaje jako tymczasowy i jest podmieniany atomowo.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from openpyxl.utils.exceptions import IllegalCharacterError

from .config import safe_filename
from .errors import ExportError
from .odczyt import struktura
from .parser.details import PARSE_VERSION, Szczegoly
from .progress import Events, NullEvents
from .safetext import sanitize_text, strip_control
from .store import Struktura, WierszSekcji

ORGAN = "Krajowa Izba Odwoławcza"
"""Oznaczenie organu — jedno miejsce, z którego biorą je wszystkie formaty (reguła 15)."""

DATA_NIEZNANA = "data nieznana"
FORMATY: tuple[str, ...] = ("xlsx", "csv", "jsonl", "md")
ARKUSZ_ORZECZENIA = "Orzeczenia"
ARKUSZ_SLOWNIK = "Slownik"
ARKUSZ_METADANE = "Metadane"
EXCEL_MAX_ROWS = 1_048_576
CSV_DELIMITER = ";"
TEXT_FORMAT = "@"
EXPORT_REPORT_EVERY = 250
MD_REPORT_EVERY = 25
"""Puls eksportu `md` gęstszy niż arkusza: plik `md` niesie strukturę liczoną przy zapisie
(zmierzone 2026-09-22: ~70 ms na dokument, 443 dokumenty ~30 s), więc 250 dokumentów to kilkanaście
sekund bez sygnału — a cisza jest usterką."""
PLIK_INDEKSU = "INDEX.md"
SUFIKS_KATALOGU_MD = "_md"
PLIK_ZNACZNIKA = ".kio-tool-eksport"
PRZEDROSTEK_POKAZU = "DEMO_"
"""Przedrostek każdego pliku i katalogu eksportu z bazy pokazowej (ADR-0008 Z-3, znacznik 3)."""
ATRYBUCJA_POKAZU = (
    "TRYB POKAZOWY — rekord fikcyjny, wygenerowany przez kio-tool; nie jest orzeczeniem Krajowej "
    "Izby Odwoławczej ani materiałem Atlasu Przetargów i nie wolno go cytować."
)
ORGAN_POKAZU = "brak — rekordy pokazowe nie pochodzą od żadnego organu"
"""Wartość wiersza `organ` w arkuszu `Metadane` eksportu pokazowego (przegląd kodu fazy 3,
2026-09-20). Wiersz `tryb` mówił „POKAZOWY”, a dwa wiersze niżej ten sam arkusz twierdził
`organ = Krajowa Izba Odwoławcza` i powtarzał atrybucję licencyjną Atlasu — czyli dokładnie to,
czemu `ATRYBUCJA_POKAZU` zapobiega w rekordzie. Znacznik 2 był prawdziwy, a arkusz obok niego
fałszywy."""
"""Zdanie zastępujące blok cytowania rekordu pokazowego (ADR-0008 Z-3, znacznik 5).

Blok cytowania z organem i źródłem jest tu jednostką eksportu: pojedynczy `.md` albo wiersz JSONL
wyjęty z katalogu nie niesie przedrostka nazwy, więc gdyby blok zostawał bez zmian, fikcyjny rekord
stawałby się fałszywym cytatem przypisanym realnemu organowi (ADR-0008 §1.2)."""
"""Znacznik własności katalogu `_md` — porównywany dosłownie po nazwie, nie przez `exists()`.

`INDEX.md` nie nadaje się na znacznik: NTFS składa wielkość liter, więc cudzy `index.md`
(mkdocs, Jekyll, GitHub) przechodził za własny i cały katalog szedł pod `rmtree` (przegląd kodu
2026-09-18, zmierzone na tej maszynie). Nazwa z kropką i nazwą narzędzia jest napisem, którego
nikt inny nie napisze, a porównanie idzie po `iterdir()`, które zwraca nazwy tak, jak leżą.
"""

Rodzaj = Literal["text", "number"]


@dataclass(frozen=True)
class Kolumna:
    nazwa: str
    opis: str
    rodzaj: Rodzaj = "text"


KOLUMNY: tuple[Kolumna, ...] = (
    Kolumna("sygnatura", "sygnatura główna orzeczenia, tak jak publikuje ją kanał"),
    Kolumna("sygnatury", "wszystkie sygnatury dokumentu rozdzielone „; ” (sprawy połączone)"),
    Kolumna(
        "data_wydania",
        "data wydania RRRR-MM-DD tak, jak przyszła z kanału; w Atlasie bywa błędna "
        "(9 ze 100 rekordów pomiaru 3a) — pusta znaczy „brak”, nie zero",
    ),
    Kolumna("data_rozprawy", "data rozprawy/posiedzenia RRRR-MM-DD z rekordu kanału"),
    Kolumna("rodzaj", "wyrok albo postanowienie (wartości zmierzone 2026-09-18)"),
    Kolumna("rozstrzygniecie", "rozstrzygnięcie znormalizowane przez kanał, np. oddalono"),
    Kolumna("rozstrzygniecie_surowe", "rozstrzygnięcie w brzmieniu z sentencji"),
    Kolumna("przewodniczacy", "przewodniczący składu orzekającego"),
    Kolumna("odwolujacy", "odwołujący, tak jak publikuje go kanał"),
    Kolumna("zamawiajacy", "zamawiający, tak jak publikuje go kanał"),
    Kolumna("przepisy", "przepisy przywołane w orzeczeniu rozdzielone „; ”, zapis kanału"),
    Kolumna("koszty", "koszty postępowania łącznie, jeśli kanał je podaje", "number"),
    Kolumna("organ", f"oznaczenie organu — zawsze „{ORGAN}” (reguła 15)"),
    Kolumna("atrybucja", "atrybucja licencyjna kanału, z jego contract.yaml (CC BY 4.0)"),
    Kolumna("kanal", "kanał akwizycji, przedrostek doc_id"),
    Kolumna("slug", "identyfikator dokumentu w kanale, tak jak przyszedł"),
    Kolumna("url_zrodla", "adres dokumentu w wyszukiwarce UZP podany przez kanał"),
    Kolumna("doc_id", "kanoniczna tożsamość dokumentu w korpusie: kanał:identyfikator"),
    Kolumna("sha256", "SHA-256 surowej wersji, z której pochodzi wiersz"),
    Kolumna("pobrano", "moment pobrania tej wersji, ISO 8601 UTC"),
    Kolumna(
        "dlugosc_tresci", "długość pełnego tekstu w znakach — treść jest w JSONL i MD", "number"
    ),
)
NAZWY_KOLUMN: tuple[str, ...] = tuple(k.nazwa for k in KOLUMNY)


@dataclass(frozen=True)
class Wpis:
    """Jeden dokument do eksportu: tożsamość, wersja, szczegóły odczytane i surowy rekord."""

    doc_id: str
    source: str
    source_ref: str
    sha256: str
    fetched_at: str
    szczegoly: Szczegoly
    rekord: Mapping[str, object]
    """Surowy rekord kanału w całości — wyłącznie do JSONL (zrzut surowca)."""
    atrybucja: str
    pokaz: bool = False
    """Rekord z bazy pokazowej — blok cytowania zastępuje `ATRYBUCJA_POKAZU` (Z-3, Z-4)."""


Zrodlo = Callable[[], Iterator[Wpis]]
Metadane = Sequence[tuple[str, object]]


def wiersz(wpis: Wpis) -> dict[str, object]:
    """Wiersz arkusza/CSV — klucze dokładnie z `NAZWY_KOLUMN`, wartości ze `Szczegoly`."""
    s = wpis.szczegoly
    return {
        "sygnatura": s.sygnatura_glowna,
        "sygnatury": "; ".join(s.sygnatury),
        "data_wydania": s.data_wydania,
        "data_rozprawy": s.data_rozprawy,
        "rodzaj": s.rodzaj,
        "rozstrzygniecie": s.rozstrzygniecie,
        "rozstrzygniecie_surowe": s.rozstrzygniecie_surowe,
        "przewodniczacy": s.przewodniczacy,
        "odwolujacy": s.odwolujacy,
        "zamawiajacy": s.zamawiajacy,
        "przepisy": "; ".join(s.przepisy),
        "koszty": s.koszty,
        "organ": ORGAN,
        "atrybucja": wpis.atrybucja,
        "kanal": wpis.source,
        "slug": wpis.source_ref,
        "url_zrodla": s.url_zrodla,
        "doc_id": wpis.doc_id,
        "sha256": wpis.sha256,
        "pobrano": wpis.fetched_at,
        "dlugosc_tresci": s.dlugosc_tresci,
    }


def blok_atrybucji(wpis: Wpis) -> str:
    """Blok cytowania z architektury 4.9: rodzaj, data, sygnatury, organ, źródło, wersja,
    pobranie — plus linia licencji kanału. Ten sam napis idzie do Markdown i do JSONL."""
    s = wpis.szczegoly
    rodzaj = (s.rodzaj or "orzeczenie").capitalize()
    sygnatury = ", ".join(s.sygnatury) or wpis.source_ref
    if wpis.pokaz:
        return f"{ATRYBUCJA_POKAZU}\nsygn. {sygnatury} (fikcyjna); wersja: {wpis.sha256[:12]}"
    return (
        f"{rodzaj} KIO z {s.data_wydania or DATA_NIEZNANA}, sygn. {sygnatury}, {ORGAN}; "
        f"źródło: {s.url_zrodla or wpis.source_ref}; wersja: {wpis.sha256[:12]}; "
        f"pobrano {wpis.fetched_at}\n{wpis.atrybucja}"
    )


def sciezki_wyjsciowe(rdzen: Path, formaty: Sequence[str]) -> dict[str, Path]:
    """Format → ścieżka. Sufiks doklejany do **nazwy**, nie przez `with_suffix`: rdzeń bywa
    postaci `kio_2024-01-01..2024-01-31`, a `with_suffix` uznałby `.2024-01-31` za rozszerzenie."""
    sciezki: dict[str, Path] = {}
    for fmt in formaty:
        if fmt not in FORMATY:
            raise ExportError(f"Nieznany format {fmt!r}; dostępne: {', '.join(FORMATY)}.")
        koncowka = SUFIKS_KATALOGU_MD if fmt == "md" else f".{fmt}"
        sciezki[fmt] = rdzen.with_name(rdzen.name + koncowka)
    return sciezki


def eksportuj(
    rdzen: Path,
    zrodlo: Zrodlo,
    *,
    formaty: Sequence[str],
    metadane: Metadane,
    events: Events | None = None,
) -> list[Path]:
    """Zapisuje każdy z formatów obok siebie i zwraca listę utworzonych ścieżek.

    Źródło jest fabryką iteratorów, bo każdy format czyta je od nowa; korpus KIO to rząd
    30 tys. dokumentów, więc drugie przejście po SQLite jest tańsze niż trzymanie całości w pamięci.
    """
    sciezki = sciezki_wyjsciowe(rdzen, formaty)
    reporter = events or NullEvents()
    utworzone: list[Path] = []
    for fmt, sciezka in sciezki.items():
        if fmt == "xlsx":
            _zapisz_xlsx(sciezka, zrodlo, metadane, reporter)
        elif fmt == "csv":
            _zapisz_csv(sciezka, zrodlo)
        elif fmt == "jsonl":
            _zapisz_jsonl(sciezka, zrodlo)
        else:
            _zapisz_md(sciezka, zrodlo, metadane, reporter)
        utworzone.append(sciezka)
    return utworzone


# ----------------------------------------------------------------------------- arkusz


def _komorka(ws: object, wartosc: object, rodzaj: Rodzaj) -> WriteOnlyCell:
    if wartosc is None:
        return WriteOnlyCell(ws, value=None)
    if rodzaj == "number" and isinstance(wartosc, int | float) and not isinstance(wartosc, bool):
        return WriteOnlyCell(ws, value=wartosc)
    komorka = WriteOnlyCell(ws, value=sanitize_text(str(wartosc)))
    # Typ tekstowy wymuszony: bez tego Excel czyta `2024-01-31` jako datę i sygnaturę
    # `KIO 1/10` jako ułamek — a kolumna tożsamości ma być tym samym napisem, co w bazie.
    komorka.number_format = TEXT_FORMAT
    komorka.data_type = "s"
    return komorka


def _naglowek(ws: object, nazwy: Sequence[str]) -> list[WriteOnlyCell]:
    komorki = []
    for nazwa in nazwy:
        komorka = WriteOnlyCell(ws, value=nazwa)
        komorka.font = Font(bold=True)
        komorki.append(komorka)
    return komorki


def _zapisz_xlsx(sciezka: Path, zrodlo: Zrodlo, metadane: Metadane, reporter: Events) -> None:
    def zapis(tmp: Path) -> None:
        wb = Workbook(write_only=True)
        try:
            wierszy = _wypelnij_skoroszyt(wb, zrodlo, metadane, reporter)
            wb.save(tmp)
        finally:
            # Porzucony `Workbook(write_only=True)` trzyma otwarty plik w `%TEMP%`: po nieudanym
            # zapisie `atexit` openpyxl wywracał się na `PermissionError` **po** komunikacie
            # o błędzie, a plik zostawał na stałe (tester 2026-09-18).
            wb.close()
        reporter.on_export(wierszy, wierszy)

    _zapis_atomowy(sciezka, zapis)


def _wypelnij_skoroszyt(wb: Workbook, zrodlo: Zrodlo, metadane: Metadane, reporter: Events) -> int:
    ws = wb.create_sheet(ARKUSZ_ORZECZENIA)
    ws.freeze_panes = "B2"
    ws.append(_naglowek(ws, NAZWY_KOLUMN))
    wierszy = 0
    for wpis in zrodlo():
        dane = wiersz(wpis)
        ws.append([_komorka(ws, dane[k.nazwa], k.rodzaj) for k in KOLUMNY])
        wierszy += 1
        if wierszy >= EXCEL_MAX_ROWS:
            raise ExportError(
                f"Arkusz mieści {EXCEL_MAX_ROWS - 1} wierszy danych, a korpus ma ich więcej "
                "— podziel eksport zakresem dat."
            )
        if wierszy % EXPORT_REPORT_EVERY == 0:
            reporter.on_export(wierszy, 0)
    slownik = wb.create_sheet(ARKUSZ_SLOWNIK)
    slownik.append(_naglowek(slownik, ("kolumna", "opis")))
    for kolumna in KOLUMNY:
        slownik.append(
            [_komorka(slownik, kolumna.nazwa, "text"), _komorka(slownik, kolumna.opis, "text")]
        )
    meta = wb.create_sheet(ARKUSZ_METADANE)
    meta.append(_naglowek(meta, ("klucz", "wartosc")))
    for klucz, wartosc in metadane:
        rodzaj: Rodzaj = "number" if isinstance(wartosc, int | float) else "text"
        meta.append([_komorka(meta, klucz, "text"), _komorka(meta, wartosc, rodzaj)])
    return wierszy


# ----------------------------------------------------------------------------- CSV / JSONL


def _wartosc_csv(wartosc: object) -> str:
    if wartosc is None:
        return ""
    if isinstance(wartosc, bool):
        return "1" if wartosc else "0"
    if isinstance(wartosc, int | float):
        return str(wartosc)
    return sanitize_text(str(wartosc))


def _zapisz_csv(sciezka: Path, zrodlo: Zrodlo) -> None:
    def zapis(tmp: Path) -> None:
        # UTF-8 z BOM: bez niego Excel na Windowsie otwiera polskie znaki jako krzaki.
        with tmp.open("w", encoding="utf-8-sig", newline="") as plik:
            pisarz = csv.writer(plik, delimiter=CSV_DELIMITER)
            pisarz.writerow(NAZWY_KOLUMN)
            for wpis in zrodlo():
                dane = wiersz(wpis)
                pisarz.writerow([_wartosc_csv(dane[nazwa]) for nazwa in NAZWY_KOLUMN])

    _zapis_atomowy(sciezka, zapis)


def _zapisz_jsonl(sciezka: Path, zrodlo: Zrodlo) -> None:
    """Jeden obiekt na dokument: tożsamość, blok atrybucji i surowy rekord kanału w całości."""

    def zapis(tmp: Path) -> None:
        with tmp.open("w", encoding="utf-8", newline="\n") as plik:
            for wpis in zrodlo():
                s = wpis.szczegoly
                obiekt = {
                    "doc_id": wpis.doc_id,
                    "kanal": wpis.source,
                    "slug": wpis.source_ref,
                    "sha256": wpis.sha256,
                    "pobrano": wpis.fetched_at,
                    "sygnatura": s.sygnatura_glowna,
                    "sygnatury": list(s.sygnatury),
                    "data_wydania": s.data_wydania,
                    "organ": ORGAN,
                    "atrybucja": wpis.atrybucja,
                    "cytowanie": blok_atrybucji(wpis),
                    "rekord": wpis.rekord,
                }
                plik.write(json.dumps(obiekt, ensure_ascii=False) + "\n")

    _zapis_atomowy(sciezka, zapis)


# ----------------------------------------------------------------------------- Markdown


def nazwa_pliku_md(wpis: Wpis) -> str:
    """`atlas_kio-1205-20.md` — z tożsamości, nie z sygnatury: postanowienie i wyrok w tej samej
    sprawie mają jedną sygnaturę i dwa dokumenty, a dwie pisownie tej samej sygnatury
    nie mają prawa dać dwóch plików."""
    return safe_filename(f"{wpis.source}_{wpis.source_ref}", ".md")


def tresc_md(wpis: Wpis) -> str:
    """Nagłówek YAML (wartości jako napisy JSON — poprawne skalary YAML w cudzysłowie), blok
    atrybucji jako cytat, zdanie o wstawionych nagłówkach, pełny tekst bez znaków sterujących
    z nagłówkami sekcji, na końcu dodatek odesłań odczytanych z treści."""
    s = wpis.szczegoly
    naglowek = [
        ("sygnatura", s.sygnatura_glowna),
        ("sygnatury", list(s.sygnatury)),
        ("data_wydania", s.data_wydania),
        ("rodzaj", s.rodzaj),
        ("rozstrzygniecie", s.rozstrzygniecie),
        ("przewodniczacy", s.przewodniczacy),
        ("organ", ORGAN),
        ("atrybucja", wpis.atrybucja),
        ("kanal", wpis.source),
        ("doc_id", wpis.doc_id),
        ("sha256", wpis.sha256),
        ("pobrano", wpis.fetched_at),
        ("url_zrodla", s.url_zrodla),
    ]
    linie = ["---"]
    linie.extend(
        f"{klucz}: {json.dumps(wartosc, ensure_ascii=False)}" for klucz, wartosc in naglowek
    )
    linie.append("---")
    linie.append("")
    linie.append(f"# {strip_control(s.sygnatura_glowna or wpis.source_ref)}")
    linie.append("")
    linie.extend(f"> {strip_control(wiersz_)}" for wiersz_ in blok_atrybucji(wpis).splitlines())
    linie.append("")
    linie.append(UWAGA_SEKCJI.format(wersja=PARSE_VERSION))
    linie.append("")
    budowa = struktura(s)
    linie.append(strip_control(tresc_z_sekcjami(s.tresc, budowa.sekcje)))
    linie.extend(dodatek_odeslan(budowa))
    return "\n".join(linie) + "\n"


ETYKIETY_SEKCJI = {
    "naglowek": "Nagłówek",
    "sentencja": "Sentencja",
    "pouczenie": "Pouczenie",
    "uzasadnienie": "Uzasadnienie",
    "zdanie_odrebne": "Zdanie odrębne",
    "nieprzypisane": "Fragment bez rozpoznanej sekcji",
}
"""Nagłówki `##` wstawiane w tekst eksportu `md` (2026-09-22). Sekcje liczy ten sam
`odczyt.struktura`, który zapisuje je do bazy, z tych samych bajtów — plik nie ma drugiego
podziału. Przed tą zmianą tekst szedł płasko i czytelnik nie odróżniał zdania Izby od
przytoczonego stanowiska strony, choć odczyt znał granicę."""

UWAGA_SEKCJI = (
    "> Nagłówki `##` w tekście poniżej wstawił kio-tool (wersja odczytu {wersja}) — nie ma ich "
    "w orzeczeniu. Granice sekcji wyznacza odczyt automatyczny; cytując, kopiuj tekst bez nich."
)
"""Nagłówek wstawiony w tekst wygląda jak część orzeczenia, a kto skopiuje fragment do cytatu,
skopiowałby napis, którego u źródła nie ma (przegląd kodu 2026-09-22; ADR-0006 Z-5)."""

NAGLOWEK_ODESLAN = "## Odesłania odczytane z treści"
UWAGA_ODESLAN = (
    "> Wyliczone automatycznie przez kio-tool (wersja odczytu {wersja}) z tekstu powyżej, "
    "nie przez Izbę ani kanał. Każdą pozycję sprawdź w tekście. Akt „nieustalone” znaczy, "
    "że tekst nie wskazuje ustawy w sposób rozstrzygalny — nie, że przepis jest spoza Pzp."
)


def tresc_z_sekcjami(tresc: str, sekcje: Sequence[WierszSekcji]) -> str:
    """Pełny tekst z nagłówkiem przed każdą sekcją. **Nic z tekstu nie ginie**: odcinek między
    sekcjami idzie bez nagłówka, a sekcja nakładająca się na poprzednią zaczyna od jej końca —
    usunięcie wstawionych nagłówków oddaje `tresc` znak w znak (strażnik w `test_exporter`)."""
    kawalki: list[str] = []
    pozycja = 0
    for sekcja in sorted(sekcje, key=lambda w: (w.start, w.porzadek)):
        poczatek = max(sekcja.start, pozycja)
        koniec = min(max(sekcja.koniec, poczatek), len(tresc))
        if poczatek >= koniec:
            continue
        kawalki.append(tresc[pozycja:poczatek])
        kawalki.append(naglowek_sekcji(sekcja.rodzaj))
        kawalki.append(tresc[poczatek:koniec])
        pozycja = koniec
    kawalki.append(tresc[pozycja:])
    return "".join(kawalki)


def naglowek_sekcji(rodzaj: str) -> str:
    return f"\n## {ETYKIETY_SEKCJI.get(rodzaj, rodzaj)}\n\n"


def dodatek_odeslan(budowa: Struktura) -> list[str]:
    """Cytowane orzeczenia i powołane przepisy z treści — zliczone po postaci, nie po wystąpieniu,
    żeby dodatek dał się przeczytać. Wyłącznie `zrodlo == "tresc"`: opracowanie kanału nie wchodzi
    do korpusu pochodnego (reguła 19)."""
    cytowane = Counter(
        (c.sygnatura or c.surowy, c.rodzaj if c.sygnatura else "nierozpoznane")
        for c in budowa.cytowania
        if c.zrodlo == "tresc"
    )
    przepisy = Counter((p.postac, p.akt) for p in budowa.przepisy if p.zrodlo == "tresc")
    linie = ["", NAGLOWEK_ODESLAN, "", UWAGA_ODESLAN.format(wersja=PARSE_VERSION), ""]
    linie.append(f"### Cytowane orzeczenia ({sum(cytowane.values())})")
    linie.append("")
    linie.extend(
        f"- {_jeden_wiersz(syg)} — {_etykieta(rodzaj)}{_krotnosc(n)}"
        for (syg, rodzaj), n in cytowane.items()
    )
    if not cytowane:
        linie.append("- brak odesłań w treści")
    linie.append("")
    linie.append(f"### Powołane przepisy ({sum(przepisy.values())})")
    linie.append("")
    linie.extend(
        f"- {_jeden_wiersz(postac)} — {_etykieta(akt, akt=True)}{_krotnosc(n)}"
        for (postac, akt), n in przepisy.items()
    )
    if not przepisy:
        linie.append("- brak powołań w treści")
    return linie


ETYKIETY_ODESLAN = {
    "kio": "KIO",
    "kio_bez_repertorium": "KIO, organ dopisany z kontekstu „sygn. akt”",
    "so": "sąd okręgowy",
    "sa": "sąd apelacyjny",
    "sn": "Sąd Najwyższy",
    "nsa": "NSA",
    "wsa": "WSA",
    "uzp_zo": "Zespół Arbitrów UZP",
    "tsue": "TSUE",
    "inne": "inny organ",
    "nierozpoznane": "postać nierozpoznana — zapis dosłowny",
    "pzp2004": "Pzp z 2004 r.",
    "pzp2019": "Pzp z 2019 r.",
    "kc": "Kodeks cywilny",
    "kpc": "Kodeks postępowania cywilnego",
    "rozporzadzenie": "rozporządzenie",
    "inne_akty": "inny akt",
    "nieustalone": "akt nieustalony",
}
"""Kody rodzaju i aktu z bazy (`docid.RodzajSygnatury`, `parser.provisions.Akt`) słowami — plik
`md` czyta prawnik, nie program. Kod zostaje w nawiasie, żeby wpis dał się dopasować do bazy
i do raportu pokrycia; kod spoza słownika idzie sam, zamiast zniknąć."""


def _etykieta(kod: str, *, akt: bool = False) -> str:
    slowo = ETYKIETY_ODESLAN.get("inne_akty" if akt and kod == "inne" else kod)
    return f"{slowo} [{kod}]" if slowo else kod


def _jeden_wiersz(napis: str) -> str:
    """Zapis dosłowny z łamaniem wiersza (sklejka po ekstrakcji z PDF-a) rozbijałby listę dodatku
    na akapity; dodatek jest wyliczeniem, nie cytatem, więc białe znaki zwijamy do spacji."""
    return " ".join(strip_control(napis).split())


def _krotnosc(n: int) -> str:
    return f" (×{n})" if n > 1 else ""


def _zapisz_md(katalog: Path, zrodlo: Zrodlo, metadane: Metadane, reporter: Events) -> None:
    """Katalog z jednym plikiem na orzeczenie i `INDEX.md` — budowany obok jako tymczasowy
    i podmieniany w całości, więc katalog docelowy jest kompletny albo nie ma go wcale.

    Powtórny eksport pod to samo `--out` **zastępuje** katalog, nie dopisuje do niego: tester
    2026-09-18 zmierzył, że po eksporcie pięciu orzeczeń, a potem jednego, katalog niósł sześć
    plików, a `INDEX.md` wymieniał jeden — orzeczenia spoza zleconego zakresu, nieodróżnialne od
    zleconych, z pełnymi nazwiskami składu (audyt 3.3). Zastępowany jest wyłącznie katalog, który
    wygląda na własny wynik (ma `INDEX.md`) albo jest pusty; cudzy katalog pod tą nazwą zostaje
    nietknięty i eksport odmawia zdaniem.
    """
    tmp = katalog.with_name(f".{katalog.name}.tmp")
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        indeks = ["# Orzeczenia KIO — eksport", "", *(f"- {k}: {v}" for k, v in metadane), ""]
        indeks.append("| plik | sygnatura | data wydania | rozstrzygnięcie |")
        indeks.append("|---|---|---|---|")
        plikow = 0
        for wpis in zrodlo():
            nazwa = nazwa_pliku_md(wpis)
            _zapisz_tekst(tmp / nazwa, tresc_md(wpis))
            plikow += 1
            if plikow % MD_REPORT_EVERY == 0:
                reporter.on_export(plikow, 0)
            s = wpis.szczegoly
            indeks.append(
                f"| [{nazwa}]({nazwa}) | {strip_control(s.sygnatura_glowna or '')} "
                f"| {s.data_wydania or DATA_NIEZNANA} | {strip_control(s.rozstrzygniecie or '')} |"
            )
        indeks.append("")
        _zapisz_tekst(tmp / PLIK_INDEKSU, "\n".join(indeks))
        _zapisz_tekst(
            tmp / PLIK_ZNACZNIKA,
            "Katalog wyniku kio-tool. Ten plik pozwala narzędziu zastąpić katalog przy "
            "powtórnym eksporcie pod tę samą ścieżkę `--out`.\n",
        )
        _usun_poprzedni_katalog_md(katalog)
        os.replace(tmp, katalog)
    except OSError as blad:
        raise ExportError(f"Nie można zapisać {katalog}: {_powod(blad)}") from blad
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def _usun_poprzedni_katalog_md(katalog: Path) -> None:
    """Usuwa poprzedni wynik pod tą nazwą — i tylko wynik: cudzych plików nie kasuje."""
    if not katalog.exists():
        return
    if not katalog.is_dir():
        raise ExportError(f"Nie można zapisać {katalog}: w tym miejscu stoi plik, nie katalog.")
    nazwy = {p.name for p in katalog.iterdir()}
    if nazwy and PLIK_ZNACZNIKA not in nazwy:
        raise ExportError(
            f"Nie można zapisać {katalog}: katalog już istnieje i nie wygląda na wynik kio-tool "
            f"(brak znacznika {PLIK_ZNACZNIKA}) — nie nadpiszę cudzych plików; podaj inne `--out`."
        )
    shutil.rmtree(katalog)


def _zapisz_tekst(cel: Path, tekst: str) -> None:
    def zapis(tmp: Path) -> None:
        tmp.write_text(tekst, encoding="utf-8", newline="\n")

    _zapis_atomowy(cel, zapis)


# ----------------------------------------------------------------------------- zapis


def _powod(blad: Exception) -> str:
    """Zdanie o awarii zapisu bez nazwy pliku tymczasowego i strzałki `os.replace`.

    `str(OSError)` przy podmianie brzmi `[WinError 5] Odmowa dostępu: '…\\.wynik.xlsx.tmp' ->
    '…\\wynik.xlsx'` — operator czyta plik, którego nie podawał (tester 2026-09-18). Zostaje
    powód z systemu i wskazówka, że korpus jest w bazie, więc płaci się tylko za eksport.
    """
    powod = (blad.strerror or str(blad)) if isinstance(blad, OSError) else str(blad)
    return (
        f"{powod}. Dokumenty są już w bazie — powtórz sam eksport poleceniem `eksportuj` "
        "pod inną ścieżką `--out`."
    )


def _zapis_atomowy(cel: Path, zapis: Callable[[Path], None]) -> None:
    """Zapis do pliku tymczasowego obok celu i `os.replace` po sukcesie — plik jest cały albo
    nie ma go wcale. `IllegalCharacterError` z `openpyxl` znaczy, że `sanitize_text` czegoś nie
    zdjął: to jest błąd eksportu do pokazania, nie ślad stosu."""
    tmp = cel.with_name(f".{cel.name}.tmp")
    try:
        # `mkdir` wewnątrz `try` (tester 2026-09-18): literówka w `--out` stawiająca plik
        # w miejscu katalogu dawała surowy `FileExistsError` zamiast zdania.
        cel.parent.mkdir(parents=True, exist_ok=True)
        zapis(tmp)
        os.replace(tmp, cel)
    except (OSError, IllegalCharacterError) as blad:
        raise ExportError(f"Nie można zapisać {cel}: {_powod(blad)}") from blad
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
