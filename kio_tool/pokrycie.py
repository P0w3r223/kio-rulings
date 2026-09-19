"""Raport pokrycia parsera — artefakt bramki fazy 2, nie ekran (ADR-0006 Z-12).

Czyta strukturę z magazynu (`Store.struktury`), nie zna kanału ani sieci. Produkt to plik
`docs/raporty/pokrycie_<data>.md` i plik maszynowy obok. Audyt 9: „ten raport jest ważniejszy niż
sam parser: pokazuje, gdzie materiał jest niejednorodny" — stąd rozbicie po **roczniku
z sygnatury**, skrzyżowane z rokiem z daty wydania. Po sygnaturze, nie po dacie, bo data w tym
kanale bywa błędna (9 na 100, pomiar 3a).

Doktryna 7.1 w postaci mechanicznej: **żaden procent nie stoi bez licznika i mianownika**
(`_udzial`). Raport nie niesie tekstu orzeczeń — liczy, nie cytuje — więc wolno go trzymać
w repozytorium.

Złoty zbiór (Z-11) to adnotacje **bez treści**: `content_sha256` dokumentu i granice sekcji ze
skrótem każdego fragmentu. Sprawdza się je wobec korpusu operatora; dokument, którego w korpusie
nie ma albo ma inną wersję, jest liczony jako niesprawdzony — głośno, liczbą „sprawdzono X z N",
nigdy przez ciche pominięcie.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .docid import normalize_signature
from .store import Store, StrukturaDokumentu

SEKCJE_KOMPLETU = ("naglowek", "sentencja", "pouczenie", "uzasadnienie")
"""Sekcje, które ma każde orzeczenie KIO z uzasadnieniem — komplet w rozumieniu raportu."""

BRAK = "brak"


@dataclass(frozen=True)
class SekcjaZlota:
    rodzaj: str
    start: int
    koniec: int
    sha256: str


@dataclass(frozen=True)
class AdnotacjaZlota:
    """Jeden plik `tests/gold/<doc_id>.json` — granice potwierdzone okiem, bez tekstu."""

    doc_id: str
    content_sha256: str
    sekcje: tuple[SekcjaZlota, ...]
    przejrzal: str
    data_przegladu: str


@dataclass
class _Rocznik:
    dokumentow: int = 0
    komplet: int = 0
    czesciowo: int = 0
    bez_sekcji: int = 0
    znakow: int = 0
    nieprzypisanych: int = 0
    cytowan: int = 0
    nierozpoznanych: int = 0


@dataclass(frozen=True)
class WynikZlotego:
    plikow: int
    sprawdzonych: int
    zgodnych: int
    rozbieznosci: tuple[str, ...]


@dataclass
class Raport:
    data: str
    parse_version: int
    dokumentow: int = 0
    bez_metadanych: int = 0
    bez_daty: int = 0
    roczniki: dict[str, _Rocznik] = field(default_factory=dict)
    krzyz: Counter[tuple[str, str]] = field(default_factory=Counter)
    rodzaje_cytowan: Counter[str] = field(default_factory=Counter)
    akty: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    kanal_razem: int = 0
    kanal_w_tresci: int = 0
    starsze_wersje: int = 0
    zloty: WynikZlotego | None = None


def rocznik_z_sygnatury(sygnatura: str | None) -> str:
    """`KIO 1205/20` → `2020`; brak albo postać nierozpoznana → `brak`. Izba orzeka od 2007 r.,
    więc dwucyfrowy rok jest zawsze rokiem XXI wieku — to fakt o organie, nie zgadywanie."""
    kanon = normalize_signature(sygnatura) if sygnatura else None
    return f"20{kanon.rsplit('/', 1)[1]}" if kanon else BRAK


def zbuduj(struktury: Iterable[StrukturaDokumentu], *, data: str, parse_version: int) -> Raport:
    raport = Raport(data=data, parse_version=parse_version)
    for d in struktury:
        _dolicz(raport, d, parse_version)
    return raport


def _dolicz(raport: Raport, d: StrukturaDokumentu, parse_version: int) -> None:
    raport.dokumentow += 1
    rocznik = rocznik_z_sygnatury(d.sygnatura_glowna)
    rok_daty = d.data_wydania[:4] if d.data_wydania else BRAK
    raport.krzyz[(rocznik, rok_daty)] += 1
    if d.parse_version is None:
        raport.bez_metadanych += 1
    elif d.parse_version < parse_version:
        raport.starsze_wersje += 1
    if not d.data_wydania:
        raport.bez_daty += 1
    r = raport.roczniki.setdefault(rocznik, _Rocznik())
    r.dokumentow += 1
    rodzaje = {s.rodzaj for s in d.sekcje}
    if all(k in rodzaje for k in SEKCJE_KOMPLETU):
        r.komplet += 1
    elif rodzaje - {"nieprzypisane"}:
        r.czesciowo += 1
    else:
        r.bez_sekcji += 1
    r.znakow += sum(s.koniec - s.start for s in d.sekcje)
    r.nieprzypisanych += sum(s.koniec - s.start for s in d.sekcje if s.rodzaj == "nieprzypisane")
    for c in d.cytowania:
        r.cytowan += 1
        raport.rodzaje_cytowan[c.rodzaj if c.sygnatura else "nierozpoznane"] += 1
        if c.sygnatura is None:
            r.nierozpoznanych += 1
    tresc = {p.postac for p in d.przepisy if p.zrodlo == "tresc"}
    for p in d.przepisy:
        raport.akty[p.zrodlo][p.akt] += 1
        if p.zrodlo == "kanal":
            raport.kanal_razem += 1
            raport.kanal_w_tresci += p.postac in tresc


# ------------------------------------------------------------------------------ złoty zbiór


def wczytaj_zloty(katalog: Path) -> list[AdnotacjaZlota]:
    """Adnotacje z katalogu, posortowane po `doc_id`. Plik niezgodny ze schematem to błąd
    głośny (`ValueError` z nazwą pliku), nie pominięcie."""
    wynik: list[AdnotacjaZlota] = []
    for plik in sorted(katalog.glob("*.json")):
        try:
            dane = json.loads(plik.read_text(encoding="utf-8"))
            wynik.append(
                AdnotacjaZlota(
                    doc_id=str(dane["doc_id"]),
                    content_sha256=str(dane["content_sha256"]),
                    sekcje=tuple(
                        SekcjaZlota(
                            str(s["rodzaj"]), int(s["start"]), int(s["koniec"]), str(s["sha256"])
                        )
                        for s in dane["sekcje"]
                    ),
                    przejrzal=str(dane["przeglad"]["kto"]),
                    data_przegladu=str(dane["przeglad"]["data"]),
                )
            )
        except (KeyError, TypeError, ValueError) as blad:
            raise ValueError(
                f"Złoty plik {plik.name} nie zgadza się ze schematem: {blad}"
            ) from blad
    return wynik


def sprawdz_zloty(
    adnotacje: Iterable[AdnotacjaZlota], struktury: Mapping[str, StrukturaDokumentu]
) -> WynikZlotego:
    """Granice z adnotacji wobec sekcji w bazie; niesprawdzony = brak dokumentu albo inna wersja."""
    lista = list(adnotacje)
    sprawdzonych = zgodnych = 0
    rozbieznosci: list[str] = []
    for a in lista:
        d = struktury.get(a.doc_id)
        if d is None or d.content_sha256 != a.content_sha256:
            rozbieznosci.append(f"{a.doc_id}: brak tej wersji w korpusie — niesprawdzony")
            continue
        sprawdzonych += 1
        w_bazie = tuple(SekcjaZlota(s.rodzaj, s.start, s.koniec, s.sha256) for s in d.sekcje)
        if w_bazie == a.sekcje:
            zgodnych += 1
        else:
            rozbieznosci.append(f"{a.doc_id}: granice sekcji inne niż w adnotacji")
    return WynikZlotego(len(lista), sprawdzonych, zgodnych, tuple(rozbieznosci))


def adnotacja(d: StrukturaDokumentu, *, kto: str, data: str) -> dict[str, object]:
    """Szkic złotego pliku z bieżącej struktury — do przejrzenia okiem **przed** zapisem."""
    return {
        "doc_id": d.doc_id,
        "content_sha256": d.content_sha256,
        "sekcje": [
            {"rodzaj": s.rodzaj, "start": s.start, "koniec": s.koniec, "sha256": s.sha256}
            for s in d.sekcje
        ],
        "przeglad": {"kto": kto, "data": data},
    }


# ---------------------------------------------------------------------------------- wydruk


def _udzial(licznik: int, mianownik: int) -> str:
    """„12 z 443 (2,7 %)" — procent nigdy bez liczb, z których powstał (doktryna 7.1)."""
    if mianownik == 0:
        return f"{licznik} z 0"
    return f"{licznik} z {mianownik} ({100 * licznik / mianownik:.1f} %)".replace(".", ",")


def markdown(raport: Raport) -> str:
    linie = [
        f"# Raport pokrycia parsera — {raport.data}",
        "",
        f"Wersja odczytu: {raport.parse_version}. Dokumentów w korpusie: {raport.dokumentow}; "
        f"bez metadanych: {raport.bez_metadanych}; odczytanych starszą wersją: "
        f"{raport.starsze_wersje}; bez daty wydania: {raport.bez_daty}. Raport nie niesie tekstu "
        "orzeczeń — wyłącznie liczby z bazy operatora (0 żądań).",
        "",
        "## Sekcje po roczniku z sygnatury",
        "",
        "| Rocznik | Dokumentów | Komplet sekcji | Częściowo | Bez sekcji | Znaki nieprzypisane |",
        "|---|---|---|---|---|---|",
    ]
    for rocznik, r in sorted(raport.roczniki.items()):
        linie.append(
            f"| {rocznik} | {r.dokumentow} | {_udzial(r.komplet, r.dokumentow)} | "
            f"{_udzial(r.czesciowo, r.dokumentow)} | {_udzial(r.bez_sekcji, r.dokumentow)} | "
            f"{_udzial(r.nieprzypisanych, r.znakow)} |"
        )
    linie += [
        "",
        "## Rocznik z sygnatury × rok z daty wydania",
        "",
        "Rozjazd nie jest błędem parsera: sprawa wniesiona w grudniu dostaje sygnaturę roku, "
        "a orzeczenie datę następnego. Wiersze z rozjazdem większym niż rok są kandydatami do "
        "błędnej daty u pośrednika.",
        "",
        "| Rocznik | Rok daty | Dokumentów |",
        "|---|---|---|",
    ]
    for (rocznik, rok), n in sorted(raport.krzyz.items()):
        linie.append(f"| {rocznik} | {rok} | {n} |")
    razem_cyt = sum(raport.rodzaje_cytowan.values())
    linie += [
        "",
        "## Cytowania (uzasadnienie i zdanie odrębne, bez sygnatury własnej)",
        "",
        "| Rodzaj | Cytowań |",
        "|---|---|",
        *(f"| {k} | {_udzial(v, razem_cyt)} |" for k, v in raport.rodzaje_cytowan.most_common()),
        "",
        "| Rocznik | Cytowań | Nierozpoznanych |",
        "|---|---|---|",
        *(
            f"| {rocznik} | {r.cytowan} | {_udzial(r.nierozpoznanych, r.cytowan)} |"
            for rocznik, r in sorted(raport.roczniki.items())
        ),
        "",
        "## Przepisy — ustawa z treści, nigdy z daty (ADR-0006 Z-8)",
        "",
    ]
    for zrodlo, akty in sorted(raport.akty.items()):
        razem = sum(akty.values())
        linie.append(f"**Źródło `{zrodlo}`** ({razem} powołań):")
        linie.append("")
        linie += [f"- `{akt}`: {_udzial(n, razem)}" for akt, n in akty.most_common()]
        linie.append("")
    linie.append(
        "Pozycje listy kanału znalezione w treści (ta sama postać kanoniczna): "
        f"{_udzial(raport.kanal_w_tresci, raport.kanal_razem)}."
    )
    linie += ["", "## Złoty zbiór (ADR-0006 Z-11)", ""]
    z = raport.zloty
    if z is None:
        linie.append("Złoty zbiór nie był podany — **sprawdzono 0 z 0**.")
    else:
        linie.append(
            f"Sprawdzono {_udzial(z.sprawdzonych, z.plikow)} adnotacji; zgodnych granic "
            f"{_udzial(z.zgodnych, z.sprawdzonych)}."
        )
        linie += [f"- {r}" for r in z.rozbieznosci]
    return "\n".join(linie) + "\n"


def maszynowy(raport: Raport) -> str:
    """Ten sam raport jako JSON — do porównań między datami bez parsowania markdownu."""
    return json.dumps(
        {
            "data": raport.data,
            "parse_version": raport.parse_version,
            "dokumentow": raport.dokumentow,
            "bez_metadanych": raport.bez_metadanych,
            "bez_daty": raport.bez_daty,
            "starsze_wersje": raport.starsze_wersje,
            "roczniki": {k: vars(v) for k, v in sorted(raport.roczniki.items())},
            "krzyz": [[r, rok, n] for (r, rok), n in sorted(raport.krzyz.items())],
            "cytowania": dict(raport.rodzaje_cytowan),
            "akty": {k: dict(v) for k, v in raport.akty.items()},
            "kanal_w_tresci": [raport.kanal_w_tresci, raport.kanal_razem],
            "zloty": None if raport.zloty is None else vars(raport.zloty),
        },
        ensure_ascii=False,
        indent=2,
    )


@dataclass(frozen=True)
class WynikPokrycia:
    raport: Raport
    markdown: Path
    maszynowy: Path


def wykonaj(
    store: Store, *, cel: Path, zloty: Path | None, data: str, parse_version: int
) -> WynikPokrycia:
    """Raport z bazy do `cel/pokrycie_<data>.md` i `.json` — zero żądań, bez tekstu orzeczeń."""
    struktury = {d.doc_id: d for d in store.struktury()}
    raport = zbuduj(struktury.values(), data=data, parse_version=parse_version)
    if zloty is not None:
        raport.zloty = sprawdz_zloty(wczytaj_zloty(zloty), struktury)
    cel.mkdir(parents=True, exist_ok=True)
    md = cel / f"pokrycie_{data}.md"
    js = cel / f"pokrycie_{data}.json"
    md.write_text(markdown(raport), encoding="utf-8", newline="\n")
    js.write_text(maszynowy(raport) + "\n", encoding="utf-8", newline="\n")
    return WynikPokrycia(raport=raport, markdown=md, maszynowy=js)
