"""Kreator (`ui/flow.py`, `ui/wizard.py`) na atrapie akcji — bez bazy, bez sieci (ADR-0008 C1).

Sekwencje mierzone są tu tym, co operator dostaje: tabelą kosztów przed pobraniem, zgodą, która
przy przebiegu masowym ma domyślne „nie", poszerzeniem zamiast ślepej uliczki przy zerze trafień,
zdaniem zamiast wyjścia z programu przy błędzie akcji (Z-10).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from kio_tool.criteria import Criteria
from kio_tool.errors import TransportError
from kio_tool.ui import texts, wizard
from kio_tool.ui.flow import DecyzjaKreatora, WynikPobrania
from kio_tool.ui.prompts import NIE, TAK, SkryptowyPrompter
from kio_tool.ui.texts import Block
from kio_tool.wycena import Wycena

WYCENA_MASOWA = Wycena(dokumentow=295, stron_listy=2, zadan=297, czas_s=296.0, zadan_juz=1)
WYCENA_MALA = Wycena(dokumentow=3, stron_listy=0, zadan=3, czas_s=2.0, zadan_juz=1)


@dataclass
class Ekran:
    bloki: list[Block] = field(default_factory=list)
    zdania: list[str] = field(default_factory=list)

    def block(self, block: Block) -> None:
        self.bloki.append(block)

    def message(self, text: str) -> None:
        self.zdania.append(text)

    def warning(self, text: str) -> None:
        self.zdania.append(text)


@dataclass
class Akcje:
    """Atrapa: pobranie woła decyzję jak potok — raz, z wyceną — i nie pobiera przy odmowie."""

    wycena: Wycena = WYCENA_MASOWA
    objetych: Sequence[int] = (295,)
    kontakt: str | None = None
    przebiegi: Sequence[tuple[str, str]] = ()
    blad: Exception | None = None
    prog_zgody: int = 50
    trafien: int = 3
    w_korpusie: int = 443
    czas_pokazu: Callable[[float], float] | None = None
    pobrania: list[Criteria] = field(default_factory=list)
    werdykty: list[str] = field(default_factory=list)
    eksporty: list[tuple[tuple[str, ...], Criteria | None, str]] = field(default_factory=list)
    szukane: list[Criteria] = field(default_factory=list)

    def brak_kontaktu(self) -> str | None:
        return self.kontakt

    def stan(self) -> texts.StanKorpusu:
        return texts.StanKorpusu(
            dokumentow=self.w_korpusie,
            zaindeksowanych=self.w_korpusie,
            przerwanych=len(self.przebiegi),
            sciezka="korpus.sqlite",
        )

    def wznawialne(self) -> Sequence[tuple[str, str]]:
        return self.przebiegi

    def pobierz(self, kryteria: Criteria, decyzja: DecyzjaKreatora) -> WynikPobrania:
        if self.blad is not None:
            raise self.blad
        werdykt = decyzja(self.wycena)
        self.werdykty.append(werdykt)
        if werdykt == "odmowa":
            from kio_tool.errors import ConsentMissingError

            raise ConsentMissingError("odmowa po wycenie")
        self.pobrania.append(kryteria)
        return WynikPobrania("atlas-test", self.objetych[len(self.pobrania) - 1])

    def wznow(self, run_id: str, decyzja: DecyzjaKreatora) -> WynikPobrania:
        self.werdykty.append(decyzja(self.wycena))
        return WynikPobrania(run_id, 10)

    def szukaj(self, kryteria: Criteria) -> int:
        self.szukane.append(kryteria)
        return self.trafien

    def eksportuj(
        self, *, run_ids: tuple[str, ...], kryteria: Criteria | None, format: str
    ) -> None:
        self.eksporty.append((run_ids, kryteria, format))


def _uruchom(akcje: Akcje, *odpowiedzi: str) -> tuple[Ekran, SkryptowyPrompter]:
    ekran = Ekran()
    prompter = SkryptowyPrompter([*odpowiedzi, texts.MENU_WYJDZ])
    wizard.uruchom(prompter, akcje, ekran)
    return ekran, prompter


def _tekst(ekran: Ekran) -> str:
    return "\n".join([*(b.as_text() for b in ekran.bloki), *ekran.zdania])


def test_pobranie_zakresu_dat_z_tabela_kosztow_zgoda_i_eksportem() -> None:
    akcje = Akcje()
    ekran, prompter = _uruchom(
        akcje, texts.MENU_POBIERZ, texts.CEL_DATY, "2024-01-01", "2024-01-31", TAK, "xlsx"
    )
    assert [str(k.od) for k in akcje.pobrania] == ["2024-01-01"]
    assert akcje.werdykty == ["zgoda"], "wycena i decyzja raz na pobranie"
    assert "Koszt przebiegu" in _tekst(ekran) and "297" in _tekst(ekran)
    assert akcje.eksporty == [(("atlas-test",), None, "xlsx")]
    zgoda = next(p for p in prompter.zadane if p.rodzaj == "tak_nie")
    assert zgoda.domyslna == NIE, "przebieg masowy: Enter znaczy „nie”"


def test_maly_przebieg_ma_domyslne_tak() -> None:
    akcje = Akcje(wycena=WYCENA_MALA, objetych=(3,))
    _, prompter = _uruchom(akcje, texts.MENU_POBIERZ, texts.CEL_DATY, "2024-01-01", "", TAK, "wroc")
    zgoda = next(p for p in prompter.zadane if p.rodzaj == "tak_nie")
    assert zgoda.domyslna == TAK


def test_odmowa_po_wycenie_nie_pobiera_i_wraca_do_menu() -> None:
    akcje = Akcje()
    ekran, _ = _uruchom(akcje, texts.MENU_POBIERZ, texts.CEL_DATY, "2024-01-01", "", NIE)
    assert akcje.pobrania == [] and akcje.werdykty == ["odmowa"]
    assert "Nie udało się" in _tekst(ekran)


def test_zla_data_to_zdanie_i_ponowne_pytanie() -> None:
    akcje = Akcje()
    ekran, _ = _uruchom(
        akcje, texts.MENU_POBIERZ, texts.CEL_DATY, "32.01.2024", "2024-01-01", "", TAK, "wroc"
    )
    assert "nie jest datą" in _tekst(ekran)
    assert len(akcje.pobrania) == 1


def test_zero_trafien_prowadzi_do_poszerzenia_zamiast_do_menu() -> None:
    """Z-10: rozstrzygnięcie w zakresie dat dało zero — kreator proponuje zdjęcie filtra."""
    akcje = Akcje(objetych=(0, 40))
    _, prompter = _uruchom(
        akcje,
        texts.MENU_POBIERZ,
        texts.CEL_ROZSTRZYGNIECIE,
        "2024-01-01",
        "2024-01-31",
        "odrzucono",
        TAK,
        "rozstrzygniecie",
        TAK,
        "wroc",
    )
    assert [k.rozstrzygniecie for k in akcje.pobrania] == [("odrzucono",), ()]
    assert any("nie zwrócił żadnego" in p.tresc for p in prompter.zadane)


def test_sygnatura_mowi_o_semantyce_wyszukiwarki() -> None:
    akcje = Akcje(wycena=WYCENA_MALA, objetych=(1,))
    ekran, _ = _uruchom(akcje, texts.MENU_POBIERZ, texts.CEL_SYGNATURA, "KIO 1205/20", TAK, "wroc")
    assert akcje.pobrania[0].fraza == "KIO 1205/20"
    assert texts.FRAZA_TO_SYGNATURA in _tekst(ekran)


def test_brak_kontaktu_wylacza_pobieranie_ale_nie_reszte_menu() -> None:
    akcje = Akcje(kontakt=texts.BRAK_KONTAKTU)
    ekran, _ = _uruchom(akcje, texts.MENU_POBIERZ, texts.MENU_SZUKAJ, "wadium", "wroc")
    assert akcje.pobrania == []
    assert texts.BRAK_KONTAKTU in _tekst(ekran)
    assert [k.fraza for k in akcje.szukane] == ["wadium"]


def test_blad_akcji_to_zdanie_i_powrot_do_menu() -> None:
    akcje = Akcje(blad=TransportError("sieć znikła (wymyślone)"))
    ekran, prompter = _uruchom(akcje, texts.MENU_POBIERZ, texts.CEL_DATY, "2024-01-01", "")
    assert "sieć znikła" in _tekst(ekran)
    assert prompter.zadane[-1].tresc == texts.pytanie_menu(jest_co_wznowic=False).tresc


def test_wznow_jest_pierwsza_pozycja_gdy_jest_co_wznowic() -> None:
    akcje = Akcje(przebiegi=(("atlas-1", "2024-01-01..2024-01-31"),))
    _, prompter = _uruchom(akcje, texts.MENU_WZNOW, "atlas-1", TAK, "wroc")
    menu = prompter.zadane[0]
    assert menu.opcje[0].klucz == texts.MENU_WZNOW and menu.domyslna == texts.MENU_WZNOW
    assert akcje.werdykty == ["zgoda"]


def test_ctrl_c_w_menu_konczy_kreator() -> None:
    class Przerywajacy(SkryptowyPrompter):
        def zapytaj(self, pytanie: texts.Pytanie) -> str:
            raise KeyboardInterrupt

    wizard.uruchom(Przerywajacy([]), Akcje(), Ekran())


def test_pierwszy_ekran_pokazu_mowi_o_fikcji() -> None:
    ekran = Ekran()
    wizard.uruchom(SkryptowyPrompter([texts.MENU_WYJDZ]), Akcje(), ekran, pokaz=True)
    assert "TRYB POKAZOWY" in ekran.bloki[0].title
