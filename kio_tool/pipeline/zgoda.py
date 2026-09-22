"""Zgoda na przebieg masowy: próg, werdykt wyceny, sufit żądań (ADR-0008 §12, ADR-0009 Z-2).

Reguła zgody (architektura 4.1, audyt 13.2 pkt 4) ma tu postać mechaniczną: przebieg, który
przekroczyłby `PROG_ZGODY` żądań, odmawia `ConsentMissingError`, jeśli nie dostał `zgoda=True`.
Zgoda jest parametrem wywołania, nie polem konfiguracji — zgoda z poprzedniej sesji nie jest
zgodą, więc nie da się jej zapisać w pliku.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from ..errors import (
    ConsentMissingError,
)
from ..source.contract import Ponowienia
from ..wycena import Wycena
from .slad import _Puls

PROG_ZGODY = 50
"""Od ilu żądań przebieg jest masowy i wymaga zgody właściciela udzielonej w tej sesji.

Liczba jest progiem, nie pomiarem, i tak ma być czytana: pojedynczy odczyt diagnostyczny to
kilka żądań, przebieg miesięczny to ~360 (właściciel 2026-09-18), a zgoda ma paść **przed**
pierwszym dokumentem, nie po pięćdziesiątym — dlatego próg porównuje się najpierw z liczbą
dokumentów zgłoszoną przez kanał na pierwszej stronie listy (przyciętą przez `maks`), a licznik
żądań jest tylko zabezpieczeniem na wypadek kanału, który liczby nie zgłasza.
"""


Werdykt = Literal["zgoda", "bez_zgody", "odmowa"]
"""Odpowiedź na wycenę (ADR-0008 Z-6). `zgoda` — przebieg masowy dozwolony w tej sesji;
`bez_zgody` — obowiązuje próg `PROG_ZGODY` (ścieżka flag bez `--zgoda`); `odmowa` — operator
zobaczył koszt i nie chce: przebieg zostaje `przerwany`, wznawialny, bez żądania za dokument."""


Decyzja = Callable[[Wycena], Werdykt]
"""Wołana **raz na wywołanie**, przy pierwszym kandydacie — po pierwszej stronie listy, kiedy
`total` jest znany, a przed pierwszym dokumentem. Zero dodatkowych żądań (ADR-0008 §1.1)."""


def decyzja_z_flagi(zgoda: bool) -> Decyzja:
    """Polityka ścieżki flag: `--zgoda` znaczy zgodę, brak flagi — próg jak przed ADR-0008."""
    werdykt: Werdykt = "zgoda" if zgoda else "bez_zgody"
    return lambda _wycena: werdykt


ODMOWA_PO_WYCENIE = (
    "Operator odmówił po wycenie — przebieg zostaje zapisany jako przerwany, bez żadnego "
    "żądania o dokument. Wznowi go to samo polecenie albo `wznow`, znowu z wyceną."
)


class _Zgoda:
    """Zgoda w obrębie jednego wywołania — zmienia ją werdykt wyceny, czyta ją też bramka
    ponowień kanału (ADR-0007 Z-9), więc jest obiektem, a nie parametrem przekazanym raz.

    `sufit` jest drugą połową tej samej zgody, dopisaną po przeglądzie kodu fazy 3
    (2026-09-20, HIGH; ADR-0008 §12). „Tak" pada pod tabelą kosztów, więc zgoda dotyczy
    **liczby, którą operator zobaczył** — a do tej pory ustawiała wyłącznie `jest`, co zdejmowało
    `PROG_ZGODY` na resztę wywołania. Zmierzone na atrapie zgłaszającej `total = 5`: wycena
    pokazała 5 żądań, operator nacisnął Enter (przy małej wycenie pytanie ma domyślne „tak"),
    wyszły **103** żądania przy progu 50. Sufit wraca do tej liczby z zapasem na ponowienia,
    bo wycena ich nie zna, a ADR-0007 Z-9 liczy je do zgody.
    """

    def __init__(self, jest: bool) -> None:
        self.jest = jest
        self.sufit: int | None = None
        """Żądań wolno wysłać najwyżej tyle; `None` = zgoda udzielona bez znanego rozmiaru."""
        self.wycenionych: int | None = None
        """Liczba z tabeli kosztów — zdanie zatrzymujące przebieg wymienia ją obok sufitu."""


def _przewidywane(razem: int | None, maks: int | None) -> int | None:
    if razem is None:
        return maks
    return razem if maks is None else min(razem, maks)


def _rozstrzygnij(werdykt: Werdykt, zgoda: _Zgoda, wycena: Wycena, ponowienia: Ponowienia) -> None:
    if werdykt == "odmowa":
        raise ConsentMissingError(ODMOWA_PO_WYCENIE)
    if werdykt == "zgoda":
        zgoda.jest = True
        zgoda.wycenionych = None if wycena.zadan is None else wycena.zadan + wycena.zadan_juz
        zgoda.sufit = _sufit(wycena, ponowienia)


def _sufit(wycena: Wycena, ponowienia: Ponowienia) -> int | None:
    """Ile żądań wolno wysłać po zgodzie udzielonej pod tą wyceną.

    `None`, gdy kanał nie podał liczby: tabela kosztów mówi wtedy wprost „kanał nie podał liczby",
    a pytanie jest pytaniem o przebieg masowy z domyślnym „nie" — zgoda pada więc świadomie na
    przebieg o nieznanym rozmiarze i sufitu nie ma z czego policzyć.

    Zapas to `proby` z bloku `ponowienia` kontraktu, nie liczba wzięta stąd: wycena liczy żądania
    udane, a ponowienie jest żądaniem jak każde inne (ADR-0007 Z-9), więc sufit bez zapasu
    zatrzymywałby przebieg za awarię cudzego serwisu zamiast za rozjazd wyceny.
    """
    if wycena.zadan is None:
        return None
    return (wycena.zadan + wycena.zadan_juz) * max(ponowienia.proby, ponowienia.proby_429)


def _wymagaj_zgody(zgoda: _Zgoda, puls: _Puls, maks: int | None) -> None:
    if zgoda.jest:
        if zgoda.sufit is not None and puls.zadan >= zgoda.sufit:
            raise ConsentMissingError(
                f"Przebieg wyszedł poza wycenę, pod którą padła zgoda: tabela kosztów mówiła "
                f"o najwyżej {zgoda.wycenionych} żądaniach, sufit z zapasem na ponowienia wynosi "
                f"{zgoda.sufit}, a wysłano {puls.zadan}. Kanał pomylił się co do rozmiaru zakresu "
                "albo zakres urósł od czasu wyceny. Przebieg zostaje zapisany jako przerwany — "
                "wznowienie policzy koszt od nowa i zapyta jeszcze raz."
            )
        return
    przewidywane = _przewidywane(puls.razem, maks)
    if puls.zadan >= PROG_ZGODY or (przewidywane is not None and przewidywane > PROG_ZGODY):
        zgloszone = "?" if przewidywane is None else str(przewidywane)
        raise ConsentMissingError(
            f"Przebieg masowy bez zgody: kanał zgłasza {zgloszone} "
            f"dokumentów w zakresie, a bez zgody wolno wysłać najwyżej {PROG_ZGODY} żądań "
            f"(wysłano {puls.zadan}). Przebieg zostaje zapisany jako przerwany — to samo "
            "polecenie z flagą `--zgoda` dokończy go bez ponownego pobierania tego, co już "
            "przyszło. Zgoda obowiązuje w sesji, w której padła (audyt 13.2 pkt 4)."
        )
