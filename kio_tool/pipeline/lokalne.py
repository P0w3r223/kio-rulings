"""Operacje na korpusie lokalnym: eksport, przeliczenie, wyszukiwanie — zero żądań (ADR-0009 Z-2).

Cztery operacje **bez sieci** — `eksportuj`, `przelicz`, `szukaj`, `wznow` przed pierwszym
żądaniem — nie budują klienta HTTP: fabryka klienta jest wołana wyłącznie w `pobierz`, a test
`--block-network` z `pyproject.toml` pilnuje, że żadna z nich nie sięga gniazda (reguła 20).

Ten moduł nie importuje ani `source`, ani `httpclient` — zdanie wyżej jest granicą modułu.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import __version__
from ..clock import Clock, SystemClock, utc_iso
from ..config import default_output_dir, safe_filename
from ..criteria import Criteria
from ..docid import normalize_signature
from ..errors import (
    ConfigError,
)
from ..exporter import (
    ATRYBUCJA_POKAZU,
    FORMATY,
    ORGAN_POKAZU,
    PRZEDROSTEK_POKAZU,
    Wpis,
    podzial_tekstu,
)
from ..exporter import eksportuj as zapisz_eksport
from ..odczyt import metryka, odczytaj, struktura
from ..parser.details import PARSE_VERSION
from ..progress import Events, NullEvents
from ..store import (
    Dokument,
    Filtr,
    Store,
    Wyszukanie,
)
from ..wpisy import MapyPol, wpis_z_dokumentu

FORMATY_DOMYSLNE: tuple[str, ...] = ("xlsx",)


@dataclass(frozen=True)
class WynikEksportu:
    sciezki: tuple[Path, ...]
    dokumentow: int
    formaty: tuple[str, ...]
    run_ids: tuple[str, ...]
    bez_daty_poza_filtrem: int


@dataclass(frozen=True)
class WynikPrzeliczenia:
    przeliczonych: int
    bledow: int
    w_korpusie: int
    zaindeksowanych: int


# --------------------------------------------------------------------------------- eksport


def eksportuj(
    store: Store,
    *,
    run_ids: Sequence[str] = (),
    kryteria: Criteria | None = None,
    formaty: Sequence[str] = FORMATY_DOMYSLNE,
    out: Path | None = None,
    cel: str | None = None,
    zegar: Clock | None = None,
    events: Events | None = None,
) -> WynikEksportu:
    """Eksport wyłącznie z bazy (`online=False` w duchu `ceidg-tool`): żadnego klienta HTTP.

    Dokumenty objęte przebiegami (`run_documents`) albo pasujące do kryteriów; puste kryteria
    bez przebiegu są błędem, a zero dokumentów nie tworzy pliku — plik pusty wyglądałby na wynik.
    """
    zegar = zegar or SystemClock()
    pokaz = store.pokazowa
    for fmt in formaty:
        if fmt not in FORMATY:
            raise ConfigError(f"Nieznany format {fmt!r}; dostępne: {', '.join(FORMATY)}.")
    if not run_ids and (kryteria is None or kryteria.is_empty()):
        raise ConfigError("Podaj przebiegi (`run_ids`) albo niepuste kryteria eksportu.")
    przebiegi = [store.get_run(r) for r in run_ids]
    filtr = None if kryteria is None else Filtr.z_kryteriow(kryteria)
    mapy = MapyPol()

    def dokumenty() -> Iterator[Dokument]:
        if przebiegi:
            # Dokument objęty dwoma przebiegami (styczeń i I kwartał) jest jednym dokumentem —
            # bez odsiania szedł do eksportu dwa razy, a `dokumentow_w_eksporcie` w `Metadane`
            # mówiło nieprawdę o własnym wyniku (przegląd kodu 2026-09-18; mina 1: duplikaty).
            widziane: set[str] = set()
            for przebieg in przebiegi:
                for dokument in store.iter_documents(run_id=przebieg.run_id):
                    if dokument.doc_id in widziane:
                        continue
                    widziane.add(dokument.doc_id)
                    yield dokument
        else:
            yield from store.iter_documents(filtr)

    def zrodlo() -> Iterator[Wpis]:
        for dokument in dokumenty():
            yield wpis_z_dokumentu(dokument, mapy, pokaz=pokaz)

    # Pierwsze przejście liczy dokumenty **i** ładuje kontrakty kanałów, które w eksporcie
    # wystąpią — atrybucja per kanał ma trafić do `Metadane`, a te powstają przed zapisem.
    dokumentow = 0
    for dokument in dokumenty():
        dokumentow += 1
        mapy.dla(dokument.source)
    bez_daty = 0 if filtr is None or przebiegi else store.bez_daty_poza_filtrem(filtr)
    if dokumentow == 0:
        return WynikEksportu((), 0, tuple(formaty), tuple(run_ids), bez_daty)
    metadane = build_metadata(
        store,
        run_ids=tuple(run_ids),
        kryteria=kryteria,
        dokumentow=dokumentow,
        formaty=tuple(formaty),
        cel=cel,
        zegar=zegar,
        atrybucje=mapy.atrybucje(),
        pokaz=pokaz,
    )
    nazwa = _nazwa_eksportu(run_ids, kryteria, zegar)
    if pokaz:
        nazwa = PRZEDROSTEK_POKAZU + nazwa
    # `--out` wskazujące istniejący katalog: plik o nazwie domyślnej **w środku**, nie obok —
    # pomoc flagi mówiła o katalogu `wyniki/`, więc operator podawał katalog i dostawał
    # `wyniki.xlsx` przy pustym `wyniki\` (tester 2026-09-18).
    if out is None:
        rdzen = default_output_dir() / nazwa
    elif out.is_dir():
        rdzen = out / nazwa
    else:
        rdzen = out
    if pokaz and not rdzen.name.startswith(PRZEDROSTEK_POKAZU):
        # Także pod `--out`: nazwa podana przez operatora nie zdejmuje znacznika (Z-3, pkt 3).
        rdzen = rdzen.with_name(PRZEDROSTEK_POKAZU + rdzen.name)
    sciezki = zapisz_eksport(rdzen, zrodlo, formaty=formaty, metadane=metadane, events=events)
    return WynikEksportu(tuple(sciezki), dokumentow, tuple(formaty), tuple(run_ids), bez_daty)


def _nazwa_eksportu(run_ids: Sequence[str], kryteria: Criteria | None, zegar: Clock) -> str:
    moment = utc_iso(zegar.wall()).replace(":", "").replace("-", "")
    if kryteria is not None and not kryteria.is_empty():
        return safe_filename(f"kio_{kryteria.describe()[:40]}_{moment}")
    return safe_filename(f"kio_{'_'.join(run_ids)}_{moment}")


def build_metadata(
    store: Store,
    *,
    run_ids: Sequence[str],
    kryteria: Criteria | None,
    dokumentow: int,
    formaty: Sequence[str],
    cel: str | None,
    zegar: Clock,
    atrybucje: dict[str, str],
    pokaz: bool = False,
) -> list[tuple[str, object]]:
    """Arkusz `Metadane`: kryteria, przebiegi, liczby z bazy, licencja, wersja narzędzia.

    `zgloszone_przez_kanal` i `objetych` to **dwa osobne wiersze**: pierwsze jest cudzą liczbą
    (`total` z listy), drugie naszą (`run_documents`) — ich różnica jest informacją, nie błędem.
    """
    przebiegi = [store.get_run(r) for r in run_ids]
    # Wiersz `tryb` pierwszy i zawsze — także w eksporcie produkcyjnym, żeby jego brak nie był
    # jedynym sposobem odróżnienia arkusza pokazowego (ADR-0008 Z-3, znacznik 2).
    meta: list[tuple[str, object]] = [
        ("tryb", "POKAZOWY — dane fikcyjne" if pokaz else "produkcyjny")
    ]
    if kryteria is not None:
        meta.append(("kryteria", kryteria.describe()))
        meta.append(("kryteria_json", kryteria.canonical_json()))
    elif przebiegi:
        meta.append(("kryteria", "; ".join(p.zakres for p in przebiegi)))
        meta.append(("kryteria_json", "; ".join(p.kryteria or "" for p in przebiegi)))
    meta.append(("cel_pobrania", cel or ""))
    if przebiegi:
        meta.extend(
            [
                ("run_id", ", ".join(p.run_id for p in przebiegi)),
                ("kanal", ", ".join(sorted({p.kanal for p in przebiegi}))),
                ("status_przebiegu", ", ".join(f"{p.run_id}: {p.status}" for p in przebiegi)),
                ("przebieg_start_utc", min(p.started_at for p in przebiegi)),
                (
                    "przebieg_koniec_utc",
                    max((p.finished_at or "" for p in przebiegi), default=""),
                ),
                ("objetych_przez_przebiegi", sum(p.dokumentow for p in przebiegi)),
                (
                    "pobranych_przez_przebiegi",
                    sum(store.count_run_documents(p.run_id, nowe=True) for p in przebiegi),
                ),
                ("zadan_w_przebiegach", sum(p.zadan for p in przebiegi)),
            ]
        )
    meta.extend(
        [
            ("dokumentow_w_eksporcie", dokumentow),
            ("dokumentow_w_korpusie", store.count("documents")),
            ("formaty", ", ".join(formaty)),
            ("eksport_utc", utc_iso(zegar.wall())),
            ("wersja_narzedzia", __version__),
            ("wersja_odczytu", PARSE_VERSION),
            ("organ", ORGAN_POKAZU if pokaz else "Krajowa Izba Odwoławcza"),
        ]
    )
    # Atrybucja licencyjna kanału jest twierdzeniem o pochodzeniu danych, więc w eksporcie
    # pokazowym byłaby fałszywa tak samo jak nazwa organu (przegląd kodu fazy 3, 2026-09-20).
    for kanal, atrybucja in sorted(atrybucje.items()):
        meta.append((f"atrybucja_{kanal}", ATRYBUCJA_POKAZU if pokaz else atrybucja))
    return meta


# ----------------------------------------------------------------------------- przeliczenie


def przelicz(
    store: Store, events: Events | None = None, *, wszystko: bool = False
) -> WynikPrzeliczenia:
    """Metadane i indeks z surowych wersji w bazie — zero żądań (reguła 20 pilnuje tego testem).

    Przelicza bieżące wersje bez metadanych albo z `parse_version` starszym niż
    `PARSE_VERSION`; `wszystko=True` przelicza każdą. Błąd odczytu jest **liczony**, nie
    przemilczany: surowe bajty zostają, wiersz metadanych nie powstaje.
    """
    reporter = events or NullEvents()
    mapy = MapyPol()
    przeliczonych = 0
    bledow = 0
    do_przeliczenia = list(store.versions_to_index(None if wszystko else PARSE_VERSION))
    for numer, dokument in enumerate(do_przeliczenia, start=1):
        mapa, _ = mapy.dla(dokument.source)
        szczegoly = odczytaj(dokument.content_bytes, mapa)
        if szczegoly is None:
            bledow += 1
        else:
            with store.transakcja():
                store.index_document(
                    dokument.doc_id,
                    dokument.current_sha256,
                    metryka(szczegoly),
                    struktura(szczegoly),
                )
            przeliczonych += 1
        reporter.on_parse(numer, len(do_przeliczenia))
    return WynikPrzeliczenia(
        przeliczonych=przeliczonych,
        bledow=bledow,
        w_korpusie=store.count("documents"),
        zaindeksowanych=store.count_indexed(),
    )


# ------------------------------------------------------------------------------ wyszukiwanie


def szukaj(store: Store, kryteria: Criteria, *, limit: int) -> Wyszukanie:
    """Wyszukiwanie w korpusie lokalnym — zero żądań; fraza jest wymagana."""
    if not kryteria.fraza:
        raise ConfigError("Wyszukiwanie wymaga frazy (`--fraza`).")
    return store.szukaj(kryteria.fraza, Filtr.z_kryteriow(kryteria), limit=limit)


# ------------------------------------------------------------------------ jedno orzeczenie

ODCINEK_BEZ_SEKCJI = "nieprzypisane"
"""Rodzaj odstępu między sekcjami w `czytaj` — ta sama nazwa co w `parser.sections`, żeby agent
filtrował jednym słownikiem (`--sekcja nieprzypisane`)."""


@dataclass(frozen=True)
class Orzeczenie:
    """Jedno orzeczenie do czytania: wpis (metadane, cytowanie, treść) i podział treści."""

    wpis: Wpis
    odcinki: tuple[tuple[str, int, int], ...]
    """Rozłączne odcinki `(rodzaj, start, koniec)` pokrywające `wpis.szczegoly.tresc` w całości."""


def czytaj(store: Store, klucz: str) -> Orzeczenie:
    """Orzeczenie po `doc_id` albo sygnaturze — zero żądań (2026-09-22).

    Powstało, bo pełny tekst jednego orzeczenia dawał dotąd tylko eksport `md` do katalogu,
    a fraza z sygnaturą łapała też orzeczenia **cytujące** tę sygnaturę. Tu sygnatura jest
    porównywana z listą sygnatur dokumentu, nie szukana w treści. Sekcje liczone w locie z tych
    samych bajtów tym samym `odczyt.struktura` co eksport — jeden dokument to ułamek sekundy.
    """
    klucz = klucz.strip()
    if not klucz:
        raise ConfigError("Podaj sygnaturę (np. „KIO 3810/23”) albo `doc_id` z wyniku `szukaj`.")
    dokumenty = store.znajdz_dokumenty(doc_id=klucz, sygnatura=normalize_signature(klucz) or klucz)
    if not dokumenty:
        raise ConfigError(
            f"W korpusie ({store.count('documents')} dokumentów) nie ma „{klucz}”. Sprawdź "
            "`szukaj --fraza`; orzeczenia spoza korpusu wymagają pobrania (wycena i zgoda)."
        )
    if len(dokumenty) > 1:
        kandydaci = "; ".join(
            f"{d.doc_id} ({', '.join(d.sygnatury)}, {d.data_wydania or 'bez daty'})"
            for d in dokumenty
        )
        raise ConfigError(
            f"„{klucz}” pasuje do {len(dokumenty)} dokumentów: {kandydaci}. Podaj `doc_id`."
        )
    wpis = wpis_z_dokumentu(dokumenty[0], MapyPol(), pokaz=store.pokazowa)
    odcinki = tuple(
        (rodzaj or ODCINEK_BEZ_SEKCJI, poczatek, koniec)
        for rodzaj, poczatek, koniec in podzial_tekstu(
            wpis.szczegoly.tresc, struktura(wpis.szczegoly).sekcje
        )
    )
    return Orzeczenie(wpis=wpis, odcinki=odcinki)
