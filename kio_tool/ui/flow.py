"""Sekwencje kreatora nad protokołem `Akcje` — bez bazy, bez sieci, bez `rich` (ADR-0008 Z-7).

Reguła 8: `ui/*` nie importuje `source` ani `store`. Kreator potrzebuje jednak pobierać, wznawiać,
szukać i eksportować — więc widzi te czynności jako protokół `Akcje`, implementowany w `cli.py`
nad `pipeline` i otwartym `Store` (C1). Dzięki temu każda sekwencja jest testowalna na atrapie
akcji: „dokładnie jedna wycena", „odmowa = zero żądań o dokument", „zero trafień prowadzi do
poszerzeń, nie do menu bez słowa".

**Bez ślepych uliczek** (Z-10): błąd akcji to zdanie i powrót do menu; `Ctrl+C` w trakcie akcji
to przebieg `przerwany` i powrót do menu; brak `KIO_TOOL_CONTACT` wyłącza pobieranie ze zdaniem
dlaczego, ale nie resztę menu; zero kandydatów to pytanie o poszerzenie.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from pydantic import ValidationError

from ..criteria import Criteria, bledy_po_polsku
from ..errors import KioError
from ..wycena import Wycena
from . import texts
from .prompts import TAK, Prompter
from .texts import Block

Werdykt = Literal["zgoda", "bez_zgody", "odmowa"]
DecyzjaKreatora = Callable[[Wycena], Werdykt]


class Ekran(Protocol):
    def block(self, block: Block) -> None: ...
    def message(self, text: str) -> None: ...
    def warning(self, text: str) -> None: ...


@dataclass(frozen=True)
class WynikPobrania:
    run_id: str
    objetych: int


class Akcje(Protocol):
    """Czynności kreatora — implementacja w `cli.py`, atrapa w testach."""

    prog_zgody: int
    czas_pokazu: Callable[[float], float] | None
    """W trybie pokazowym: czas pokazu z czasu produkcyjnego (ADR-0008 Z-13); inaczej `None`."""

    def brak_kontaktu(self) -> str | None: ...
    def wznawialne(self) -> Sequence[tuple[str, str]]: ...
    def pobierz(self, kryteria: Criteria, decyzja: DecyzjaKreatora) -> WynikPobrania: ...
    def wznow(self, run_id: str, decyzja: DecyzjaKreatora) -> WynikPobrania: ...
    def szukaj(self, kryteria: Criteria) -> int: ...
    def eksportuj(
        self, *, run_ids: tuple[str, ...], kryteria: Criteria | None, format: str
    ) -> None: ...


def decyzja_kreatora(prompter: Prompter, ekran: Ekran, akcje: Akcje) -> DecyzjaKreatora:
    """Tabela kosztów, potem pytanie. „Tak” jest zgodą udzieloną w tej sesji — człowiek zobaczył
    koszt i odpowiedział — więc werdykt to `zgoda`, nie próg; „nie” to `odmowa`."""

    def decyzja(wycena: Wycena) -> Werdykt:
        pokaz = None
        if akcje.czas_pokazu is not None and wycena.czas_s is not None:
            pokaz = akcje.czas_pokazu(wycena.czas_s)
        ekran.block(texts.tabela_kosztow(wycena, prog_zgody=akcje.prog_zgody, czas_pokazu_s=pokaz))
        masowy = wycena.zadan is None or wycena.zadan + wycena.zadan_juz > akcje.prog_zgody
        odpowiedz = prompter.zapytaj(texts.pytanie_zgody(masowy=masowy))
        return "zgoda" if odpowiedz == TAK else "odmowa"

    return decyzja


def bezpiecznie[T](ekran: Ekran, czynnosc: Callable[[], T]) -> T | None:
    """Akcja bez ślepej uliczki: błąd i przerwanie kończą się zdaniem, nie wyjściem z programu."""
    try:
        return czynnosc()
    except KeyboardInterrupt:
        ekran.warning(texts.PRZERWANO_AKCJE)
    except KioError as blad:
        ekran.warning(texts.blad_akcji(str(blad)))
    return None


# ------------------------------------------------------------------------------ pobranie


def krok_pobierz(prompter: Prompter, akcje: Akcje, ekran: Ekran) -> None:
    powod = akcje.brak_kontaktu()
    if powod is not None:
        ekran.warning(powod)
        return
    kryteria = zbierz_kryteria(prompter, ekran)
    while kryteria is not None:
        kryteria = _pobierz_raz(prompter, akcje, ekran, kryteria)


def _pobierz_raz(
    prompter: Prompter, akcje: Akcje, ekran: Ekran, kryteria: Criteria
) -> Criteria | None:
    """Jedno pobranie; zwraca kryteria poszerzone, gdy kanał nic nie zwrócił, inaczej `None`."""
    decyzja = decyzja_kreatora(prompter, ekran, akcje)
    wynik = bezpiecznie(ekran, lambda: akcje.pobierz(kryteria, decyzja))
    if wynik is None:
        return None
    if wynik.objetych > 0:
        zaproponuj_eksport(prompter, akcje, ekran, run_ids=(wynik.run_id,))
        return None
    return poszerz(prompter, kryteria)


def zbierz_kryteria(prompter: Prompter, ekran: Ekran) -> Criteria | None:
    """Cel pobrania i jego pola; `None` = operator wrócił do menu."""
    cel = prompter.zapytaj(texts.PYTANIE_CEL)
    if cel == texts.WROC:
        return None
    if cel == texts.CEL_SYGNATURA:
        ekran.message(texts.FRAZA_TO_SYGNATURA)
        return _kryteria(
            prompter, ekran, lambda: {"fraza": prompter.zapytaj(texts.PYTANIE_SYGNATURA)}
        )
    zakres = _zakres(prompter, ekran)
    if zakres is None:
        return None
    if cel == texts.CEL_ROZSTRZYGNIECIE:
        wybor = prompter.zapytaj(texts.PYTANIE_ROZSTRZYGNIECIE)
        return zakres.model_copy(update={"rozstrzygniecie": (wybor,)})
    return zakres


def _zakres(prompter: Prompter, ekran: Ekran) -> Criteria | None:
    def pola() -> dict[str, object]:
        od = prompter.zapytaj(texts.PYTANIE_OD).strip()
        if not od:
            return {}
        # Sprawdzona od razu, nie po drugim pytaniu: inaczej operator wpisywał datę „do"
        # do zakresu, którego początek i tak zostanie odrzucony.
        data_od = _data(od)
        do = prompter.zapytaj(texts.PYTANIE_DO).strip()
        return {"od": data_od, "do": _data(do) if do else None}

    return _kryteria(prompter, ekran, pola)


def _data(napis: str) -> date:
    try:
        return date.fromisoformat(napis)
    except ValueError as blad:
        raise _NiepoprawneError(f"„{napis}” nie jest datą RRRR-MM-DD") from blad


class _NiepoprawneError(ValueError):
    pass


def _kryteria(
    prompter: Prompter, ekran: Ekran, pola: Callable[[], dict[str, object]]
) -> Criteria | None:
    """Pola od operatora → `Criteria`; zła wartość to zdanie i ponowne pytanie, puste — powrót."""
    while True:
        try:
            wartosci = pola()
            if not any(v for v in wartosci.values()):
                return None
            return Criteria.model_validate(wartosci)
        except _NiepoprawneError as blad:
            ekran.warning(texts.niepoprawne(str(blad)))
        except ValidationError as blad:
            ekran.warning(texts.niepoprawne(bledy_po_polsku(blad)))


def poszerz(prompter: Prompter, kryteria: Criteria) -> Criteria | None:
    """Zero kandydatów → kryteria bez jednego filtra albo powrót do menu (ADR-0008 Z-10)."""
    kandydaci = dict(kryteria.poszerzenia())
    if not kandydaci:
        return None
    wybor = prompter.zapytaj(texts.pytanie_poszerzenia(kryteria))
    return kandydaci.get(wybor)


def zaproponuj_eksport(
    prompter: Prompter,
    akcje: Akcje,
    ekran: Ekran,
    *,
    run_ids: tuple[str, ...] = (),
    kryteria: Criteria | None = None,
) -> None:
    format = prompter.zapytaj(texts.PYTANIE_EKSPORT)
    if format == texts.WROC:
        return
    bezpiecznie(ekran, lambda: akcje.eksportuj(run_ids=run_ids, kryteria=kryteria, format=format))


# --------------------------------------------------------------- wznowienie, szukanie, eksport


def krok_wznow(prompter: Prompter, akcje: Akcje, ekran: Ekran) -> None:
    powod = akcje.brak_kontaktu()
    if powod is not None:
        ekran.warning(powod)
        return
    wybor = prompter.zapytaj(texts.pytanie_wznowienia(akcje.wznawialne()))
    if wybor == texts.WROC:
        return
    wynik = bezpiecznie(ekran, lambda: akcje.wznow(wybor, decyzja_kreatora(prompter, ekran, akcje)))
    if wynik is not None and wynik.objetych > 0:
        zaproponuj_eksport(prompter, akcje, ekran, run_ids=(wynik.run_id,))


def krok_szukaj(prompter: Prompter, akcje: Akcje, ekran: Ekran) -> None:
    fraza = prompter.zapytaj(texts.PYTANIE_FRAZA).strip()
    kryteria = _kryteria(prompter, ekran, lambda: {"fraza": fraza}) if fraza else None
    if kryteria is None:
        kryteria = _zakres(prompter, ekran)
    if kryteria is None:
        return
    ustalone = kryteria
    # Eksport proponowany tylko po trafieniach: przy zerze ekran pokazał już blok `zero_trafien`
    # z liczbami, a po błędzie akcji `bezpiecznie` zwraca `None` — pytanie o zapis pustego pliku
    # było w obu wypadkach pytaniem o nic (przegląd kodu fazy 3, 2026-09-20).
    if bezpiecznie(ekran, lambda: akcje.szukaj(ustalone)):
        zaproponuj_eksport(prompter, akcje, ekran, kryteria=ustalone)


def krok_eksportuj(prompter: Prompter, akcje: Akcje, ekran: Ekran) -> None:
    kryteria = _zakres(prompter, ekran)
    if kryteria is None:
        return
    zaproponuj_eksport(prompter, akcje, ekran, kryteria=kryteria)
