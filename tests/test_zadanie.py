"""Strażnik środowiska sondy i jednego żądania — `scripts/zadanie.py`.

`wykonaj` jest jedynym miejscem, z którego sonda wychodzi do sieci, a fabryki `zegar`, `klient`,
`limiter`, `kronika` — jedynym, z którego pomiary biorą zależności. Testy niżej jadą przez
pomiary jako wehikuł (najkrótsza droga do `wykonaj` prowadzi przez `pomiar_atlas` albo
`pomiar_uzp`), ale sprawdzają własności żądania: skrót, zapis, `Retry-After`, sygnaturę, ciało
POST-u, ślad po awarii dysku po odebraniu odpowiedzi. Do 2026-09-18 w `tests/test_sonda.py`.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Callable
from pathlib import Path

import httpx

# Moduły sondy mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import pomiar_saos
import pomiar_uzp
import pytest
import sonda
import zadanie

from kio_tool import logbook
from kio_tool.config import UZP_HOSTS
from tests.wsparcie_sondy import (
    ATLAS_LISTA_OK,
    PRAWDZIWE_WYJSCIE,
    SAOS_DUMP_OK,
    SCIEZKA_ATLAS,
    SCIEZKA_KORZEN,
    SCIEZKA_SAOS,
    UA_TESTOWY,
    UZP_DETAILS_OK,
    UZP_WYNIKI_OK,
    Odpowiedz,
    Serwis,
    ZegarTestowy,
    scenariusz_atlas_ok,
    uzp_scenariusz,
    wiersze_dziennika,
    wynik,
)

# --- zatrzymanie grupy: `zatrzymaj_po_odmowie` --------------------------------------------


def test_powod_zatrzymania_gdy_kontrola_nie_doszla() -> None:
    powod = zadanie.zatrzymaj_po_odmowie(wynik(status=None))

    assert powod is not None and "nie doszedł" in powod


def test_powod_zatrzymania_niesie_kod_odmowy() -> None:
    """Kod w komunikacie jest różnicą między „napisz pismo" a „zdobądź klucz"."""
    powod = zadanie.zatrzymaj_po_odmowie(wynik(status=403))

    assert powod is not None and "403" in powod


def test_powod_zatrzymania_gdy_kontrola_wraca_nie_do_poznania() -> None:
    powod = zadanie.zatrzymaj_po_odmowie(wynik(status=200, ksztalt_zgodny=False))

    assert powod is not None and "kształcie" in powod


def test_udana_kontrola_nie_zatrzymuje_grupy() -> None:
    assert zadanie.zatrzymaj_po_odmowie(wynik(status=200, ksztalt_zgodny=True)) is None


def test_awaria_serwisu_nie_zatrzymuje_grupy() -> None:
    """Symetrycznie do `KODY_ODMOWY`: 503 jest powodem do powtórzenia, nie do wniosku."""
    assert zadanie.zatrzymaj_po_odmowie(wynik(status=503)) is None


# --- skrót odpowiedzi ----------------------------------------------------------------------


def test_wynik_niesie_skrot_zapisanych_bajtow(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Skrót ma się zgadzać z **bajtami na dysku**, nie z czymkolwiek policzonym po drodze.

    Zdanie „zmierzone {data}, N żądań" wskazywało dotąd na plik spoza historii repozytorium
    i nie było czym go związać z treścią. Tę rolę pełni ten skrót i dlatego test porównuje
    go z odczytem zapisanego pliku, a nie z odpowiedzią atrapy.
    """
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)
    zapisany = wyniki[0].plik

    assert zapisany is not None
    assert wyniki[0].sha256 == hashlib.sha256(zapisany.read_bytes()).hexdigest()
    assert wyniki[0].sha256 == hashlib.sha256(ATLAS_LISTA_OK).hexdigest()
    assert wyniki[0].bajtow == len(ATLAS_LISTA_OK)


def test_zadanie_ktore_nie_doszlo_nie_udaje_zapisanego_dowodu(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Błąd transportu zostawia wynik bez pliku i bez skrótu — bo nie ma czego wiązać.
    Skrót pustych bajtów byłby skrótem, który wygląda jak dowód i nim nie jest."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(
        {SCIEZKA_ATLAS: httpx.ConnectError("brak połączenia"), SCIEZKA_KORZEN: Odpowiedz()}
    )
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert wyniki[0].status is None
    assert wyniki[0].plik is None and wyniki[0].sha256 is None
    assert "ConnectError" in wyniki[0].uwaga


def test_slad_przezywa_takze_awarie_dysku_po_odebraniu_odpowiedzi(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Czwarta z czterech awarii wymienionych w docstringu `Kroniki` — i jedyna, która pada
    **po** odebraniu odpowiedzi, czyli po tym, jak cudzy serwer zapłacił za nasze żądanie pracą.

    Test obok („ślad po żądaniach, które już poszły") wygląda, jakby ją obejmował: podaje
    `RuntimeError("brak miejsca na dysku")`. Napis mówi o dysku, ale wyjątek leci z atrapy
    **transportu**, więc `zapisz_surowe` nigdy się nie wykonuje i ta ścieżka pozostawała
    niesprawdzona. To jest dokładnie ten kształt, który projekt nazwał przy `test_bramki_faz.py`:
    materiał testu nie trafia w stan, o którym mówi docstring. Znalezione przeglądem 2026-09-17.

    Różnica wobec trzech pozostałych awarii jest rachunkowa, nie estetyczna: przy nich żądanie
    nie wyszło i N w `decisions.md` jest o jeden mniejsze. Tutaj wyszło, wróciło i zostało
    policzone przez serwis po drugiej stronie — więc musi być policzone i po tej.
    """
    serwis = Serwis({SCIEZKA_SAOS: Odpowiedz(tresc=SAOS_DUMP_OK)})
    podstaw(serwis)

    def bez_miejsca(*_args: object, **_kwargs: object) -> Path:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(zadanie, "zapisz_surowe", bez_miejsca)

    with pytest.raises(OSError, match="No space left"):
        pomiar_saos.pomiar_saos(UA_TESTOWY)

    wiersze = wiersze_dziennika()

    assert len(wiersze) == 1, (
        "odpowiedź odebrana, a w dzienniku zero wierszy — jedyny ślad w historii repozytorium "
        "po żądaniu, za które cudzy serwer już zapłacił, zniknął razem z miejscem na dysku"
    )
    assert "dump/judgments" in wiersze[0]
    assert "200" in wiersze[0], "status odebranej odpowiedzi jest znany i ma być zapisany"


def test_wynik_po_awarii_dysku_mowi_ze_odpowiedz_odebrano_ale_nie_zapisano(
    podstaw: Callable[[Serwis], ZegarTestowy], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sam wiersz w dzienniku to za mało: ma jeszcze **mówić, co się stało**.

    Zmierzone mutacją 2026-09-18: napis „odpowiedź odebrana, ale nie zapisana na dysk
    ({typ}: {treść})" skreślony z `wykonaj` do pustego zostawia 610 zielonych testów. Test obok
    liczy wiersze dziennika, a dziennik tej kolumny nie ma — więc jedyna droga, którą ta
    informacja dociera dziś do operatora, nie miała żadnego obserwatora.

    Co wiersz niesie, a czego nie, jest tu drugą połową asercji i **stanem do przeczytania**,
    nie pochwałą. Wynik ma komplet tego, co wiadomo o odpowiedzi — status, rozmiar, skrót
    zliczony z odebranych bajtów — i `plik is None`, bo pliku nie ma. Skrót bez pliku znaczy
    jednak w dzienniku co innego, niż mówi nagłówek tej kolumny („`sha256` wiąże wiersz
    z bajtami odpowiedzi w `scripts/out/`"): bajtów tam nie ma i nie będzie. Kolumna `uwaga`
    w tabeli dziennika nie istnieje, więc zdanie o niezapisanym pliku zostaje na ekranie
    i w `podsumowanie_*.json` — a przy braku miejsca na dysku podsumowanie też się nie zapisze.
    Ta asercja jest miejscem, w którym zmiana tego rozstrzygnięcia staje się widoczna.
    """
    serwis = Serwis({SCIEZKA_SAOS: Odpowiedz(tresc=SAOS_DUMP_OK)})
    zegar = podstaw(serwis)
    kronika = logbook.Kronika.na_teraz(
        zegar, dziennik=tmp_path / "d.md", katalog_wyjscia=tmp_path / "o"
    )

    def bez_miejsca(*_args: object, **_kwargs: object) -> Path:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(zadanie, "zapisz_surowe", bez_miejsca)

    with pytest.raises(OSError, match="No space left"):
        pomiar_saos.pomiar_saos(UA_TESTOWY, kronika)

    zapisany = kronika.zapisane[0]

    assert "nie zapisana na dysk" in zapisany.uwaga, (
        "wynik po awarii dysku nie mówi, że odpowiedź odebrano, a pliku nie ma — operator "
        "widzi wiersz nie do odróżnienia od udanego zapisu"
    )
    assert "OSError" in zapisany.uwaga, "uwaga nie niesie klasy awarii, więc nie mówi, co zawiodło"
    assert zapisany.plik is None
    assert zapisany.status == 200
    assert zapisany.bajtow == len(SAOS_DUMP_OK)
    assert zapisany.sha256 == hashlib.sha256(SAOS_DUMP_OK).hexdigest()

    wiersz = (tmp_path / "d.md").read_text(encoding="utf-8").splitlines()[-1]

    assert "nie zapisana" not in wiersz, (
        "tabela dziennika nie ma kolumny `uwaga` (model 4.4) — gdyby zaczęła ją nieść, ten "
        "test jest miejscem, w którym rozstrzygnięcie zmienia się jawnie, a nie po cichu"
    )


def test_limiter_sondy_dostaje_glos_a_nie_cisze(
    podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Sedno drugiej poprawki: `events=PulsKonsoli()` zamiast domyślnego `NullEvents`.

    Do przeglądu 2026-09-17 limiter dostawał `NullEvents`, więc sonda milczała przez cały
    postój. Przy odstępie UZP są to dwie sekundy, ale po statusie 429 blokada jest liczona
    z `max(cooldown_s, Retry-After)` i przesypiana w plastrach po 300 s — operator nie miał
    jak odróżnić „limiter trzyma odstęp" od „gniazdo wisi". Skreślenie `events=…` z powrotem
    nie psuje żadnego pomiaru i nie wypisuje **nic**; jedynym obserwatorem jest ta asercja.
    """
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(tresc=UZP_WYNIKI_OK))
    podstaw(serwis)

    pomiar_uzp.pomiar_uzp(UA_TESTOWY)

    wypisane = capsys.readouterr().out

    assert "czekam" in wypisane, "sonda przemilczała postój limitera"
    assert "odstep" in wypisane


def test_nieczytelny_retry_after_dociera_do_operatora_a_nie_tylko_do_limitera(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Uwaga o nieprzeczytanym nagłówku ma trafić na ekran i do podsumowania, a nie zostać
    w funkcji, która go czytała — inaczej poprawka zamieniłaby jedną ciszę na drugą."""
    serwis = Serwis(
        {
            SCIEZKA_ATLAS: Odpowiedz(
                status=429, tresc=b"{}", naglowki={"Retry-After": "kiedy indziej"}
            ),
            SCIEZKA_KORZEN: Odpowiedz(status=429, tresc=b"{}"),
        }
    )
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert any("nie umiem przeczytać" in w.uwaga for w in wyniki), (
        "nagłówek nie do odczytania nie zostawił śladu przy żadnym wyniku"
    )


# --- `wykonaj`: parametry żądania wyliczone, nie zebrane w worku --------------------------


def test_parametry_zadania_sa_wyliczone_w_sygnaturze() -> None:
    """Worek `**kwargs: object` wymagał `type: ignore[arg-type]` dokładnie na wywołaniu
    wychodzącym do sieci — czyli w jedynym miejscu, gdzie wyłączenie kontroli typów kosztuje
    cudze żądanie.

    Literówka `param=` zamiast `params=` przechodziła wtedy przez `mypy --strict` i wywracała
    się dopiero w przebiegu, **po** `acquire`, czyli po zapłaceniu za odstęp. Przywrócenie
    worka nie psuje żadnego testu zachowania; ta asercja jest jego jedynym obserwatorem.
    """
    parametry = inspect.signature(zadanie.wykonaj).parameters

    assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parametry.values()), (
        "`wykonaj` przyjmuje z powrotem worek argumentów — literówka w nazwie parametru "
        "żądania przechodzi wtedy przez `mypy --strict`"
    )
    for nazwa in ("params", "data", "headers"):
        assert parametry[nazwa].kind is inspect.Parameter.KEYWORD_ONLY


def test_pola_formularza_ida_do_ciala_zadania_a_nie_do_zapytania(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """Zachowanie po drugiej stronie tej samej poprawki: `data=` ma trafić do ciała POST-u.

    `Phrase`, `Kind` i `Dt` w pasku adresu zamiast w ciele znaczą inne żądanie niż to, które
    wysyłają dwa cudze kolektory — a pomiar 4b istnieje po to, żeby potwierdzić **ich**
    kontrakt, nie żeby zmierzyć wariant.
    """
    serwis = uzp_scenariusz(Odpowiedz(tresc=UZP_DETAILS_OK), Odpowiedz(tresc=UZP_WYNIKI_OK))
    podstaw(serwis)

    pomiar_uzp.pomiar_uzp(UA_TESTOWY)
    post = serwis.zadania[1]

    assert post.method == "POST"
    assert b"Kind=KIO" in post.content
    assert post.url.params.get("Kind") is None, "pola formularza wyszły w pasku adresu"
    assert post.headers["X-Requested-With"] == "XMLHttpRequest"


# --- fabryki: jedno miejsce, z którego pomiary biorą zależności ---------------------------
#
# Od 2026-09-18 zegar, klient, limiter i kronika powstają wyłącznie tutaj, a test podstawia
# `zadanie.SystemClock` i `zadanie.build_http_client` w jednym module. Testy niżej pilnują,
# że fabryki naprawdę czytają te nazwy z modułu w chwili wywołania — fabryka, która związałaby
# `SystemClock` przy imporcie, ominęłaby podstawienie bez śladu, a `_piaskownica` nie zobaczyłaby
# tego, bo zegar nie pisze na dysk.


def test_kronika_z_fabryki_czyta_zegar_i_sciezki_modulu_w_chwili_wywolania(
    zegar_sondy: ZegarTestowy,
) -> None:
    """`run_id` i `ts` z podstawionego zegara, ścieżki z podstawionych stałych.

    Co ten test obserwuje, a czego nie — zmierzone mutacją 2026-09-18. Fabryka, która wzięłaby
    `SystemClock()` wprost zamiast `zegar()`, **przechodzi**: `zegar_sondy` podstawia
    `zadanie.SystemClock`, więc obie pisownie w tym module dają zegar testowy. Zapala się
    natomiast fabryka, która związała zegar albo ścieżkę **przy imporcie** — domyślną wartością
    argumentu albo stałą policzoną raz — bo taka wartość jest sprzed podstawienia. To jest ta
    postać usterki, którą piaskownica przepuściłaby bez śladu: ścieżka związana przy imporcie
    wskazuje prawdziwy `scripts/out/`.

    Do 2026-09-18 ten test wołał `Kronika.na_teraz()` bez argumentów, a kronika brała
    `SystemClock()` sama; teraz zegar jest parametrem, więc to fabryka sondy odpowiada za to,
    że podaje ten, który test podstawił.
    """
    kronika = zadanie.kronika()

    assert kronika.ts == "2023-11-14T22:13:20Z"
    assert kronika.run_id == "sonda-20231114T221320Z"
    assert kronika.dziennik == zadanie.DZIENNIK
    assert kronika.katalog_wyjscia == zadanie.KATALOG_WYJSCIA
    assert PRAWDZIWE_WYJSCIE not in kronika.katalog_wyjscia.parents, (
        "fabryka kroniki związała ścieżkę przy imporcie zamiast czytać stałą modułu"
    )


def test_limiter_z_fabryki_czyta_zegar_modulu_w_chwili_wywolania(
    zegar_sondy: ZegarTestowy,
) -> None:
    """Limiter z zegarem związanym przy imporcie przesypiałby odstęp naprawdę.

    Odstęp 2 s przy UZP razy trzy żądania na test razy kilkadziesiąt testów — to jest różnica
    między suitą na sekundy a suitą na minuty, i ta różnica jest jedynym obserwatorem tego,
    że limiter dostał zegar testowy. Test mierzy ją wprost: po `acquire` sny są na zegarze
    testowym, a nie na ściennym. Tak samo jak w teście wyżej: `SystemClock()` wprost w tym
    module przechodzi (jest podstawione), zegar związany przy imporcie — nie.
    """
    limiter = zadanie.limiter(zadanie.ODSTEP_UZP_S)

    limiter.acquire("pierwsze")
    limiter.acquire("drugie")

    assert zegar_sondy.sleeps, "limiter nie zasnął na zegarze testowym — wziął inny zegar"
    assert sum(zegar_sondy.sleeps) >= zadanie.ODSTEP_UZP_S


def test_wykonaj_pisze_do_katalogu_i_dziennika_kroniki_a_nie_do_stalych_modulu(
    podstaw: Callable[[Serwis], ZegarTestowy], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ścieżki nie są globalami (od 2026-09-18) i to jest jedyny test, który tę różnicę widzi.

    Piaskownica podstawia `zadanie.KATALOG_WYJSCIA` i `zadanie.DZIENNIK` na ten sam `tmp_path`,
    do którego prowadzi `zadanie.kronika()` — więc `wykonaj` piszące do stałej modułu zamiast
    do `kronika.katalog_wyjscia` wyglądałoby w każdym innym teście identycznie (zmierzone
    mutacją 2026-09-18: bez tego testu mutacja przechodzi cicho). Kronika z **innymi**
    ścieżkami niż stałe modułu rozdziela te dwa zdania: surowa odpowiedź i wiersz dziennika mają
    wylądować tam, gdzie mówi kronika, a stałe modułu mają zostać nietknięte.
    """
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(scenariusz_atlas_ok())
    zegar = podstaw(serwis)
    kronika = logbook.Kronika.na_teraz(
        zegar,
        dziennik=tmp_path / "inny" / "dziennik.md",
        katalog_wyjscia=tmp_path / "inny_out",
    )

    wyniki = sonda.pomiar_atlas(UA_TESTOWY, kronika)

    assert wyniki[0].plik is not None and wyniki[0].plik.parent == tmp_path / "inny_out"
    assert (tmp_path / "inny" / "dziennik.md").is_file()
    assert not zadanie.DZIENNIK.exists(), "wiersz poszedł do stałej modułu, nie do kroniki"
    assert not zadanie.KATALOG_WYJSCIA.exists(), "zapis poszedł do stałej modułu, nie do kroniki"


def test_klient_z_fabryki_przechodzi_przez_bramke_wyjscia(
    podstaw: Callable[[Serwis], ZegarTestowy],
) -> None:
    """`klient()` woła `build_http_client` z modułu, więc podstawienie w `podstaw` go widzi.

    Klient zbudowany obok — `httpx.Client(...)` wprost — zapaliłby regułę 11 w skanie granic;
    klient zbudowany prawdziwym `build_http_client`, ale związanym przy imporcie, przeszedłby
    skan i ominął atrapę serwisu: test wysłałby prawdziwe żądanie, a `--block-network` byłoby
    jedyną barierą. Zbiór hostów zapisany w atrapie jest dowodem, że wywołanie poszło tędy.
    """
    serwis = Serwis({})
    podstaw(serwis)

    with zadanie.klient(UA_TESTOWY, UZP_HOSTS) as klient:
        assert klient.headers["User-Agent"] == UA_TESTOWY

    assert serwis.bramki == [UZP_HOSTS]
