"""Wspólne przygotowanie testów.

Jedna rzecz, i to ta, której brak w `ceidg-tool` opisano jako powód istnienia
`forget_secrets()`: `_KNOWN_SECRETS` jest stanem na poziomie modułu, więc bez czyszczenia
pierwszy test rejestrujący sekret zmienia wynik każdego następnego. Ciek stanu między
testami jest tą klasą usterki, która najpierw daje zielone przebiegi, a potem czerwony
przy zmianie kolejności testów.

Druga rzecz to `sys.path`. `scripts/` nie jest pakietem i nie ma nim być: sonda fazy 0
mieszka poza `kio_tool/` z powodu zapisanego w ADR-0003 — przed bramką wyboru kanału
`source/` nie powstaje, a sonda ma zniknąć albo zamienić się w adapter. Sama sonda działa,
bo `python scripts\\sonda.py` wkłada katalog skryptu na `sys.path` i dopiero dzięki temu
`import zadanie` w niej ma się o co oprzeć. Test uruchamiany przez pytest nie ma tej
ścieżki, więc dokłada ją tutaj — a nie w module testu, gdzie stałaby między importami
i byłaby albo `E402`, albo importem schowanym w funkcji.

Trzecia rzecz, od 2026-09-18: **piaskownica sondy obowiązuje w każdym teście**, nie tylko
w `test_sonda.py`. Testy sondy rozeszły się po ośmiu plikach i fixture `autouse` w jednym
z nich chroniłaby jeden; test w innym pliku, który dotknąłby prawdziwego dziennika żądań,
wyglądałby identycznie jak test z ochroną. Koszt dla testów spoza sondy to dwa odczyty
stanu dysku na test — mierzalny w milisekundach, niewidoczny w czasie suity.

Czwarta rzecz, tego samego dnia i z tego samego powodu: piaskownica objęła **korpus
operatora**. Do 2026-09-18 broniła wyłącznie ścieżek sondy, a cztery testy w `test_cli.py`
wołały `pobierz` bez `--out` i zapisywały eksport do prawdziwego `config.default_output_dir()`
— zmierzone: cztery pliki na przebieg suity, dwadzieścia cztery zastane i skasowane ręcznie.
Suita była przy tym cała zielona, bo miejsce zapisu nie było niczyją asercją.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from kio_tool.config import forget_secrets

SKRYPTY = Path(__file__).resolve().parent.parent / "scripts"
if str(SKRYPTY) not in sys.path:
    # `append`, nie `insert(0, …)`: wstawienie na początek sprawiłoby, że przyszły plik
    # w `scripts/` o nazwie kolidującej z modułem biblioteki przesłania ten moduł we
    # **wszystkich** testach, nie tylko w tych, które potrzebują sondy (przegląd kodu
    # 2026-09-17). Dopisanie na koniec daje ten sam import bez przesłaniania.
    sys.path.append(str(SKRYPTY))

# Po dopisaniu ścieżki, bo `wsparcie_sondy` importuje `zadanie` ze `scripts/` — import na górze
# pliku nie miałby czego importować. `noqa: E402` jest tu świadome i sprawdzone 2026-09-18:
# `ruff` zgłasza E402 mimo tego, że między importami stoi wyłącznie modyfikacja `sys.path`
# (wyjątek reguły nie obejmuje jej w bloku `if`). To jedyne dwa importy w `tests/` z tym
# znacznikiem; każdy plik testów importuje `wsparcie_sondy` zwyczajnie, bo conftest jest już
# wtedy załadowany.
import zadanie  # noqa: E402

from tests.wsparcie_sondy import (  # noqa: E402
    PRAWDZIWA_BAZA,
    PRAWDZIWE_WYJSCIE,
    PRAWDZIWE_WYNIKI,
    PRAWDZIWY_DZIENNIK,
    Serwis,
    ZegarTestowy,
    przekieruj_domyslne_sciezki,
    stan_prawdziwego_korpusu,
    stan_prawdziwych_sciezek,
    stan_raportow,
)


@pytest.fixture(autouse=True)
def _czysty_rejestr_sekretow() -> Iterator[None]:
    forget_secrets()
    yield
    forget_secrets()


@pytest.fixture(autouse=True)
def _piaskownica(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Przekierowuje zapis sondy i korpusu do `tmp_path` **i sprawdza, że to zadziałało**.

    Druga połowa jest ważniejsza od pierwszej. Przekierowanie bez porównania stanu jest
    gwarancją, której nikt nie obserwuje: wystarczy, że funkcja sondy złoży kiedyś ścieżkę
    z `Path(__file__)` zamiast czytać stałą modułu, i test po cichu dopisze wiersz do
    dziennika żądań w historii repozytorium — czyli zapisze żądanie, którego nikt nie wysłał.

    Dwie pary ścieżek i dwa porównania, bo to dwa różne zapisy z jednym uzasadnieniem: żądanie,
    którego nikt nie wysłał, i eksport, którego nikt nie zlecił. Korpus operatora niesie przy
    tym pełne nazwiska składu orzekającego (audyt 3.3), więc plik dorzucony tam przez test nie
    jest tylko śmieciem — jest wyciągiem z cudzych danych osobowych pod nazwą wyglądającą na
    wynik pracy operatora.
    """
    przed = stan_prawdziwych_sciezek()
    przed_korpus = stan_prawdziwego_korpusu()
    przed_raporty = stan_raportow()
    monkeypatch.setattr(zadanie, "KATALOG_WYJSCIA", tmp_path / "out")
    monkeypatch.setattr(zadanie, "DZIENNIK", tmp_path / "docs" / "dziennik_zadan.md")
    przekieruj_domyslne_sciezki(monkeypatch, tmp_path / "dane")
    yield tmp_path
    assert stan_prawdziwych_sciezek() == przed, (
        f"test ruszył prawdziwe ścieżki sondy ({PRAWDZIWE_WYJSCIE} albo {PRAWDZIWY_DZIENNIK}). "
        "Przekierowanie do `tmp_path` zostało ominięte — sonda złożyła ścieżkę sama zamiast "
        "czytać stałą modułu."
    )
    assert stan_prawdziwego_korpusu() == przed_korpus, (
        f"test ruszył korpus operatora ({PRAWDZIWA_BAZA} albo {PRAWDZIWE_WYNIKI}). Polecenie "
        "bez `--baza`/`--out` sięgnęło domyślnej ścieżki, której piaskownica nie przekierowała "
        "— zapis testu do prawdziwego katalogu wyjścia jest eksportem, którego nikt nie zlecił."
    )
    assert stan_raportow() == przed_raporty, (
        "test nadpisał zacommitowany raport pokrycia w `docs/raporty/` — `pokrycie` bez `--cel` "
        "pisze względem katalogu bieżącego, a pod pytestem jest nim korzeń repozytorium."
    )


@pytest.fixture
def podstaw(monkeypatch: pytest.MonkeyPatch) -> Callable[[Serwis], ZegarTestowy]:
    """Podstawia atrapę serwisu i zegar testowy. Zwraca zegar — sny są treścią jednego testu.

    Klient powstaje **prawdziwym** `build_http_client` z podanym transportem, a nie obok
    niego: gdyby test budował własnego `httpx.Client`, jechałby inną ścieżką niż produkcja
    i nie widziałby ani bramki wyjścia, ani nagłówka tożsamości. Regułę 11 egzekwuje na tym
    pliku skan z `tests/test_boundaries.py`.
    """

    def _podstaw(serwis: Serwis) -> ZegarTestowy:
        zegar = ZegarTestowy()
        monkeypatch.setattr(zadanie, "SystemClock", lambda: zegar)
        prawdziwy = zadanie.build_http_client

        def zbuduj(**kwargs: object) -> httpx.Client:
            bramka = kwargs["allowed"]
            assert isinstance(bramka, frozenset)
            serwis.bramki.append(bramka)
            return prawdziwy(**{**kwargs, "transport": serwis.transport()})  # type: ignore[arg-type]

        monkeypatch.setattr(zadanie, "build_http_client", zbuduj)
        return zegar

    return _podstaw


@pytest.fixture
def zegar_sondy(monkeypatch: pytest.MonkeyPatch) -> ZegarTestowy:
    """Sam zegar, bez atrapy serwisu — do testów, które nie wysyłają żądań."""
    zegar = ZegarTestowy()
    monkeypatch.setattr(zadanie, "SystemClock", lambda: zegar)
    return zegar
