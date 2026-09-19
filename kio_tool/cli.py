"""Wiersz poleceń (typer): `pobierz`, `wznow`, `eksportuj`, `runy`, `przelicz`, `szukaj`.

Cienki adapter — zdania należą do `ui/texts.py` (reguła 9), rysowanie do `ui/render.py`
(reguła 10), praca do `pipeline`. Ten moduł nie importuje `source` (reguła 5: tylko `pipeline`
widzi naraz sieć i bazę), nie zna `rich` (reguła 7) i nie drukuje niczym sam — ani `print`, ani
`typer.echo`; pilnuje tego skan reguły 9 w `tests/test_boundaries.py`, razem z pomocą flag,
która też jest zdaniem do użytkownika i też pochodzi z `texts`.

Wspólne opcje są stałymi `Annotated` (wzorzec z `ceidg-tool`): jedna definicja flagi, ta sama
pomoc w każdym poleceniu, które ją niesie. Kody wyjścia z `errors.py`: wyjątek `KioError` niesie
własny, `Ctrl+C` daje 130.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from . import pipeline
from . import pokrycie as raport_pokrycia
from .clock import SystemClock, utc_iso
from .config import default_db_path, user_agent
from .console import PulsKonsoli
from .criteria import Criteria, bledy_po_polsku
from .errors import KOD_WYJSCIA_PRZERWANIE, ConfigError, KioError
from .exporter import FORMATY
from .parser.details import PARSE_VERSION
from .pipeline import KANAL_DOMYSLNY
from .store import STATUSY_PRZEBIEGU, Store
from .ui import texts
from .ui.render import ConsoleView
from .wycena import Wycena

app = typer.Typer(help=texts.POMOC_PROGRAMU, add_completion=False, no_args_is_help=True)
view = ConsoleView()

OpcjaOd = Annotated[str | None, typer.Option("--od", help=texts.POMOC_OD)]
OpcjaDo = Annotated[str | None, typer.Option("--do", help=texts.POMOC_DO)]
OpcjaFraza = Annotated[str | None, typer.Option("--fraza", help=texts.POMOC_FRAZA)]
OpcjaRozstrzygniecie = Annotated[
    list[str] | None, typer.Option("--rozstrzygniecie", help=texts.POMOC_ROZSTRZYGNIECIE)
]
OpcjaRodzaj = Annotated[list[str] | None, typer.Option("--rodzaj", help=texts.POMOC_RODZAJ)]
OpcjaPrzepis = Annotated[str | None, typer.Option("--przepis", help=texts.POMOC_PRZEPIS)]
OpcjaPrzewodniczacy = Annotated[
    str | None, typer.Option("--przewodniczacy", help=texts.POMOC_PRZEWODNICZACY)
]
OpcjaStrona = Annotated[str | None, typer.Option("--strona", help=texts.POMOC_STRONA)]
OpcjaMaks = Annotated[int | None, typer.Option("--maks", help=texts.POMOC_MAKS)]
OpcjaFormat = Annotated[str, typer.Option("--format", help=texts.POMOC_FORMAT)]
OpcjaOut = Annotated[Path | None, typer.Option("--out", help=texts.POMOC_OUT)]
OpcjaCel = Annotated[str | None, typer.Option("--cel", help=texts.POMOC_CEL)]
OpcjaBaza = Annotated[Path | None, typer.Option("--baza", help=texts.POMOC_BAZA)]
OpcjaKanal = Annotated[str, typer.Option("--kanal", help=texts.POMOC_KANAL)]
OpcjaZgoda = Annotated[bool, typer.Option("--zgoda", help=texts.POMOC_ZGODA)]
OpcjaRunId = Annotated[list[str] | None, typer.Option("--run-id", help=texts.POMOC_RUN_ID)]
OpcjaJedenRunId = Annotated[str | None, typer.Option("--run-id", help=texts.POMOC_RUN_ID_JEDEN)]
OpcjaLimit = Annotated[int, typer.Option("--limit", help=texts.POMOC_LIMIT)]
OpcjaStatus = Annotated[list[str] | None, typer.Option("--status", help=texts.POMOC_STATUS)]
OpcjaWszystko = Annotated[bool, typer.Option("--wszystko", help=texts.POMOC_WSZYSTKO)]

FORMAT_DOMYSLNY = ",".join(pipeline.FORMATY_DOMYSLNE)
LIMIT_RUNOW = 20
LIMIT_TRAFIEN = 20


@app.callback(help=texts.POMOC_PROGRAMU)
def _program() -> None:
    # `typer` z jednym poleceniem i bez wywołania zwrotnego zwija je do polecenia głównego —
    # `kio-tool pobierz …` przestawałoby wtedy istnieć, a drugie polecenie zmieniałoby składnię
    # pierwszego. Pusty callback utrwala kształt `kio-tool <polecenie>`.
    return None


@contextmanager
def _obsluga_bledow() -> Iterator[None]:
    """`KioError` → zdanie i kod wyjścia; `Ctrl+C` → zdanie o wznowieniu i 130.

    `KioError` mówi w docstringu, że komunikat jest dla użytkownika, i niesie `exit_code`.
    Ślad stosu zamiast zdania łamałby oba te zdania naraz.
    """
    try:
        yield
    except KioError as blad:
        view.error(texts.blad(str(blad)))
        raise typer.Exit(code=blad.exit_code) from blad
    except KeyboardInterrupt:
        view.error(texts.PRZERWANE)
        raise typer.Exit(code=KOD_WYJSCIA_PRZERWANIE) from None


@contextmanager
def _otworz_baze(sciezka: Path, zegar: SystemClock) -> Iterator[Store]:
    """`Store.open` plus jedno zdanie, gdy ścieżka dopiero co dostała pustą bazę."""
    with Store.open(sciezka, clock=zegar) as store:
        if store.nowa:
            view.message(texts.nowa_baza(str(sciezka)))
        yield store


def _kryteria(
    *,
    od: str | None = None,
    do: str | None = None,
    fraza: str | None = None,
    rozstrzygniecie: Sequence[str] | None = None,
    rodzaj: Sequence[str] | None = None,
    przepis: str | None = None,
    przewodniczacy: str | None = None,
    strona: str | None = None,
    maks: int | None = None,
) -> Criteria:
    """Flagi → `Criteria`; błąd walidacji wraca po polsku jako błąd konfiguracji."""
    try:
        return Criteria.model_validate(
            {
                "od": od,
                "do": do,
                "fraza": fraza or "",
                "rozstrzygniecie": rozstrzygniecie or (),
                "rodzaj": rodzaj or (),
                "przepis": przepis or "",
                "przewodniczacy": przewodniczacy or "",
                "strona": strona or "",
                "maks": maks,
            }
        )
    except ValidationError as blad:
        raise ConfigError(texts.zle_kryteria(bledy_po_polsku(blad))) from blad


def _formaty(napis: str) -> tuple[str, ...]:
    formaty = tuple(f.strip().lower() for f in napis.split(",") if f.strip())
    for fmt in formaty:
        if fmt not in FORMATY:
            raise ConfigError(texts.zly_format(fmt, FORMATY))
    return formaty or pipeline.FORMATY_DOMYSLNE


def _statusy(podane: Sequence[str] | None) -> tuple[str, ...] | None:
    if not podane:
        return None
    for status in podane:
        if status not in STATUSY_PRZEBIEGU:
            raise ConfigError(texts.zly_status(status, STATUSY_PRZEBIEGU))
    return tuple(podane)


def _limit(limit: int) -> int:
    """Niedodatni `--limit` jest pomyłką w wywołaniu (kod 3), sprawdzaną przed otwarciem bazy —
    tak samo w `runy` i `szukaj`; magazyn ma własny strażnik, ale jego kod to awaria bazy."""
    if limit < 1:
        raise ConfigError(texts.zly_limit(limit))
    return limit


def _eksport_i_raport(
    store: Store,
    *,
    run_ids: Sequence[str],
    kryteria: Criteria | None,
    formaty: Sequence[str],
    out: Path | None,
    cel: str | None,
    zegar: SystemClock,
) -> None:
    """Eksport z bazy plus podsumowanie — te same zdania po `pobierz`, `wznow` i `eksportuj`."""
    wynik = pipeline.eksportuj(
        store, run_ids=run_ids, kryteria=kryteria, formaty=formaty, out=out, cel=cel, zegar=zegar
    )
    if wynik.dokumentow == 0:
        view.message(texts.NIC_DO_EKSPORTU)
        for run_id in run_ids:
            # Przebieg sprzed schematu 2 ma żądania i dokumenty w korpusie, ale nie ma wierszy
            # w `run_documents` — „żaden dokument nie pasuje" jest wtedy prawdziwe i mylące naraz
            # (znalezisko testera 2026-09-18, zmierzone na bazie operatora).
            przebieg = store.get_run(run_id)
            if przebieg.dokumentow == 0 and przebieg.zadan > 0:
                view.message(texts.przebieg_bez_powiazan(przebieg.run_id, przebieg.zakres))
        if kryteria is not None:
            view.block(
                texts.zero_trafien(
                    kryteria,
                    w_korpusie=store.count("documents"),
                    zaindeksowanych=store.count_indexed(),
                    bez_daty=wynik.bez_daty_poza_filtrem,
                )
            )
        return
    view.block(
        texts.blok_eksportu(
            [str(s) for s in wynik.sciezki],
            wynik.dokumentow,
            wynik.formaty,
            wynik.bez_daty_poza_filtrem,
        )
    )


def _raport_przebiegu(wynik: pipeline.Podsumowanie, baza: Path) -> None:
    view.message(
        texts.podsumowanie(
            run_id=wynik.run_id,
            status=wynik.status,
            kandydatow=wynik.kandydatow,
            nowych=wynik.nowych,
            pominietych=wynik.pominietych,
            zadan=wynik.zadan,
            baza=str(baza),
            zgloszone=wynik.zgloszone,
            objetych_lacznie=wynik.objetych_lacznie,
            pobranych_lacznie=wynik.pobranych_lacznie,
            zadan_lacznie=wynik.zadan_lacznie,
            bledow_odczytu=wynik.bledow_odczytu,
            brakujacych=wynik.brakujacych,
            ponowien_lacznie=wynik.ponowien_lacznie,
        )
    )


def _decyzja_flag(zgoda: bool) -> pipeline.Decyzja:
    """Ścieżka flag: tabela kosztów zawsze na ekranie, werdykt z `--zgoda` (ADR-0008 Z-6)."""
    polityka = pipeline.decyzja_z_flagi(zgoda)

    def decyzja(wycena: Wycena) -> pipeline.Werdykt:
        view.block(texts.tabela_kosztow(wycena, prog_zgody=pipeline.PROG_ZGODY))
        return polityka(wycena)

    return decyzja


@app.command(help=texts.POMOC_POBIERZ)
def pobierz(
    od: OpcjaOd = None,
    do: OpcjaDo = None,
    fraza: OpcjaFraza = None,
    rozstrzygniecie: OpcjaRozstrzygniecie = None,
    rodzaj: OpcjaRodzaj = None,
    przepis: OpcjaPrzepis = None,
    przewodniczacy: OpcjaPrzewodniczacy = None,
    strona: OpcjaStrona = None,
    maks: OpcjaMaks = None,
    format: OpcjaFormat = FORMAT_DOMYSLNY,
    out: OpcjaOut = None,
    cel: OpcjaCel = None,
    baza: OpcjaBaza = None,
    kanal: OpcjaKanal = KANAL_DOMYSLNY,
    zgoda: OpcjaZgoda = False,
) -> None:
    with _obsluga_bledow():
        kryteria = _kryteria(
            od=od,
            do=do,
            fraza=fraza,
            rozstrzygniecie=rozstrzygniecie,
            rodzaj=rodzaj,
            przepis=przepis,
            przewodniczacy=przewodniczacy,
            strona=strona,
            maks=maks,
        )
        if kryteria.is_empty():
            raise ConfigError(texts.KRYTERIA_PUSTE)
        formaty = _formaty(format)
        tozsamosc = user_agent()  # odmawia bez KIO_TOOL_CONTACT — zamierzone (reguła 16)
        sciezka = baza or default_db_path()
        # Jeden zegar dla bazy i potoku — i jedno miejsce, w którym test podstawia zegar sterowany
        # (`tests/test_cli.py`). Drugi `SystemClock()` w `pipeline` dawał testowi CLI prawdziwe
        # `time.sleep(1.0)` na każde ze stu żądań atrapy.
        zegar = SystemClock()
        view.message(texts.start_przebiegu(kanal, kryteria.describe(), str(sciezka), tozsamosc))
        for ostrzezenie in kryteria.ostrzezenia():
            view.warning(texts.uwaga(ostrzezenie))
        with _otworz_baze(sciezka, zegar) as store:
            wynik = pipeline.pobierz(
                kanal,
                kryteria,
                store,
                PulsKonsoli(),
                zgoda=zgoda,
                user_agent=tozsamosc,
                decyzja=_decyzja_flag(zgoda),
                zegar=zegar,
            )
            _raport_przebiegu(wynik, sciezka)
            if wynik.objetych_lacznie == 0:
                view.block(texts.zero_kandydatow(kryteria))
                return
            _eksport_i_raport(
                store,
                run_ids=(wynik.run_id,),
                kryteria=None,
                formaty=formaty,
                out=out,
                cel=cel,
                zegar=zegar,
            )


@app.command(help=texts.POMOC_WZNOW)
def wznow(
    run_id: OpcjaJedenRunId = None,
    format: OpcjaFormat = FORMAT_DOMYSLNY,
    out: OpcjaOut = None,
    cel: OpcjaCel = None,
    baza: OpcjaBaza = None,
    zgoda: OpcjaZgoda = False,
) -> None:
    with _obsluga_bledow():
        formaty = _formaty(format)
        tozsamosc = user_agent()
        sciezka = baza or default_db_path()
        zegar = SystemClock()
        with _otworz_baze(sciezka, zegar) as store:
            wybrany, kryteria = pipeline.do_wznowienia(store, run_id)
            przebieg = store.get_run(wybrany)
            view.message(
                texts.wznawiam(wybrany, kryteria.describe(), przebieg.ostatnia_strona or 1)
            )
            view.message(
                texts.start_przebiegu(przebieg.kanal, kryteria.describe(), str(sciezka), tozsamosc)
            )
            wynik = pipeline.wznow(
                store,
                wybrany,
                PulsKonsoli(),
                zgoda=zgoda,
                user_agent=tozsamosc,
                decyzja=_decyzja_flag(zgoda),
                zegar=zegar,
            )
            _raport_przebiegu(wynik, sciezka)
            _eksport_i_raport(
                store,
                run_ids=(wynik.run_id,),
                kryteria=None,
                formaty=formaty,
                out=out,
                cel=cel,
                zegar=zegar,
            )


@app.command(help=texts.POMOC_EKSPORTUJ)
def eksportuj(
    run_id: OpcjaRunId = None,
    od: OpcjaOd = None,
    do: OpcjaDo = None,
    fraza: OpcjaFraza = None,
    rozstrzygniecie: OpcjaRozstrzygniecie = None,
    rodzaj: OpcjaRodzaj = None,
    przepis: OpcjaPrzepis = None,
    przewodniczacy: OpcjaPrzewodniczacy = None,
    strona: OpcjaStrona = None,
    format: OpcjaFormat = FORMAT_DOMYSLNY,
    out: OpcjaOut = None,
    cel: OpcjaCel = None,
    baza: OpcjaBaza = None,
) -> None:
    with _obsluga_bledow():
        formaty = _formaty(format)
        kryteria = _kryteria(
            od=od,
            do=do,
            fraza=fraza,
            rozstrzygniecie=rozstrzygniecie,
            rodzaj=rodzaj,
            przepis=przepis,
            przewodniczacy=przewodniczacy,
            strona=strona,
        )
        run_ids = tuple(run_id or ())
        if not run_ids and kryteria.is_empty():
            raise ConfigError(texts.EKSPORT_BEZ_ZAKRESU)
        if run_ids and not kryteria.is_empty():
            # Oba naraz gubiły kryteria po cichu — eksport całych przebiegów bez słowa o datach
            # (przegląd kodu 2026-09-18).
            raise ConfigError(texts.EKSPORT_RUN_I_KRYTERIA)
        sciezka = baza or default_db_path()
        zegar = SystemClock()
        with _otworz_baze(sciezka, zegar) as store:
            _eksport_i_raport(
                store,
                run_ids=run_ids,
                kryteria=None if run_ids else kryteria,
                formaty=formaty,
                out=out,
                cel=cel,
                zegar=zegar,
            )


@app.command(help=texts.POMOC_RUNY)
def runy(
    limit: OpcjaLimit = LIMIT_RUNOW,
    status: OpcjaStatus = None,
    baza: OpcjaBaza = None,
) -> None:
    with _obsluga_bledow():
        statusy = _statusy(status)
        limit = _limit(limit)
        sciezka = baza or default_db_path()
        with _otworz_baze(sciezka, SystemClock()) as store:
            przebiegi = store.list_runs(limit, statuses=statusy)
            lacznie = store.count_runs()
        if lacznie == 0:
            view.message(texts.BRAK_PRZEBIEGOW)
            return
        wiersze = tuple(
            (
                p.run_id,
                p.status,
                p.kanal,
                p.zakres,
                p.started_at,
                str(p.dokumentow),
                str(p.zadan),
            )
            for p in przebiegi
        )
        view.block(texts.blok_runow(wiersze, lacznie))


@app.command(help=texts.POMOC_PRZELICZ)
def przelicz(wszystko: OpcjaWszystko = False, baza: OpcjaBaza = None) -> None:
    with _obsluga_bledow():
        sciezka = baza or default_db_path()
        with _otworz_baze(sciezka, SystemClock()) as store:
            wynik = pipeline.przelicz(store, PulsKonsoli(), wszystko=wszystko)
        view.block(
            texts.blok_przeliczenia(
                wynik.przeliczonych, wynik.bledow, wynik.w_korpusie, wynik.zaindeksowanych
            )
        )


OpcjaCelRaportu = Annotated[Path, typer.Option("--cel", help=texts.POMOC_CEL_RAPORTU)]
OpcjaZloty = Annotated[Path | None, typer.Option("--zloty", help=texts.POMOC_ZLOTY)]


@app.command(help=texts.POMOC_POKRYCIE)
def pokrycie(
    cel: OpcjaCelRaportu = Path("docs") / "raporty",
    zloty: OpcjaZloty = None,
    baza: OpcjaBaza = None,
) -> None:
    zegar = SystemClock()
    with _obsluga_bledow():
        sciezka = baza or default_db_path()
        with _otworz_baze(sciezka, zegar) as store:
            wynik = raport_pokrycia.wykonaj(
                store,
                cel=cel,
                zloty=zloty,
                data=utc_iso(zegar.wall())[:10],
                parse_version=PARSE_VERSION,
            )
        r = wynik.raport
        z = r.zloty
        view.block(
            texts.blok_pokrycia(
                r.dokumentow,
                sum(x.komplet for x in r.roczniki.values()),
                sum(x.nierozpoznanych for x in r.roczniki.values()),
                sum(x.cytowan for x in r.roczniki.values()),
                None if z is None else (z.plikow, z.sprawdzonych, z.zgodnych),
                (str(wynik.markdown), str(wynik.maszynowy)),
            )
        )


@app.command(help=texts.POMOC_SZUKAJ)
def szukaj(
    fraza: OpcjaFraza = None,
    od: OpcjaOd = None,
    do: OpcjaDo = None,
    rozstrzygniecie: OpcjaRozstrzygniecie = None,
    rodzaj: OpcjaRodzaj = None,
    przepis: OpcjaPrzepis = None,
    przewodniczacy: OpcjaPrzewodniczacy = None,
    strona: OpcjaStrona = None,
    limit: OpcjaLimit = LIMIT_TRAFIEN,
    baza: OpcjaBaza = None,
) -> None:
    with _obsluga_bledow():
        kryteria = _kryteria(
            od=od,
            do=do,
            fraza=fraza,
            rozstrzygniecie=rozstrzygniecie,
            rodzaj=rodzaj,
            przepis=przepis,
            przewodniczacy=przewodniczacy,
            strona=strona,
        )
        limit = _limit(limit)
        sciezka = baza or default_db_path()
        with _otworz_baze(sciezka, SystemClock()) as store:
            wynik = pipeline.szukaj(store, kryteria, limit=limit)
        for ostrzezenie in kryteria.ostrzezenia():
            view.warning(texts.uwaga(ostrzezenie))
        if wynik.trafien == 0:
            view.block(
                texts.zero_trafien(
                    kryteria,
                    w_korpusie=wynik.w_korpusie,
                    zaindeksowanych=wynik.zaindeksowanych,
                    bez_daty=wynik.bez_daty_poza_filtrem,
                )
            )
            return
        wiersze = tuple(
            (
                t.sygnatura or t.source_ref,
                t.data_wydania or "",
                t.rozstrzygniecie or "",
                t.fragment,
            )
            for t in wynik.trafienia
        )
        view.block(
            texts.blok_wyszukiwania(
                wiersze,
                fraza=kryteria.fraza,
                w_korpusie=wynik.w_korpusie,
                zaindeksowanych=wynik.zaindeksowanych,
                trafien=wynik.trafien,
                bez_daty_poza_filtrem=wynik.bez_daty_poza_filtrem,
            )
        )


if __name__ == "__main__":
    app()
