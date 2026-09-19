"""Mechaniczni strażnicy bramek planu faz — i spójności trzech dokumentów, które o nich mówią.

Plan faz (`docs/AUDYT_KIO_ORZECZENIA.md` 9) stawia przed każdą fazą warunek wejścia albo
wyjścia. Do 2026-09-17 **żaden z nich nie miał obserwatora**: ADR-0004 sam to przyznaje
w sekcji 5 („przy pustym `source/` reguły 21 i 17 przechodzą pusto, więc to nie jest strażnik
tej bramki"). Zdanie w dokumencie wygląda tak samo jak reguła egzekwowana — i to jest dokładnie
ten kształt, przed którym ostrzega doktryna projektu (audyt 7.3: gwarancja bez obserwatora nie
jest gwarancją).

Ten plik nie pilnuje **jakości** decyzji. Pilnuje jednej rzeczy: żeby kod, który wolno napisać
dopiero po zapadnięciu decyzji, nie powstał **przed** nią — i żeby decyzja ogłoszona jako
zapadła miała wypełnione to, czego sama od siebie wymaga.

Trzy bramki mają tu kształt implikacji „jeśli istnieje artefakt kodu, to istnieje przyjęty ADR":

| Artefakt kodu | Wymagany ADR | Czemu ta kolejność |
|---|---|---|
| `source/<kanał>/` | ADR-0004 | kanał nie jest wybrany, więc adapter nie ma czego implementować |
| `store.py` | ADR-0001 | tożsamość dokumentu przed **pierwszym zapisem do bazy** (audyt 9) |
| `mcp_server.py` | ADR-0002 | czy treść orzeczenia wolno wysłać do modelu (audyt 12, faza 4) |

Druga kolejność jest strażnikiem miny 1: w CEIDG jeden wpis miał dwie pisownie identyfikatora,
klucz główny był wrażliwy na wielkość liter, a jedna noc kosztowała 2 681 żądań i zero
użytecznych rekordów. Zabrakło tam dokładnie tej kolejności.

**Dziś wszystkie trzy przechodzą pusto** i to jest prawda o stanie projektu, nie luka — tak
samo jak w `test_boundaries.py`. Ciężar dowodu niosą więc samosprawdzenia na drzewie
podrzuconym w `tmp_path`: każda implikacja jest sprawdzana **w obie strony** na sztucznym
korzeniu, więc strażnik ma dowód działania w dniu, w którym jeszcze nie ma czego pilnować.

Przegląd 2026-09-17 zmierzył, ile ten ciężar naprawdę ważył, i odpowiedź brzmiała „mniej, niż
deklaruje nagłówek". Siedem mutacji tego pliku przeszło przez **cały zielony przebieg**:
kolumna statusu przestawiona z `1` na `0`, `startswith` zamienione na `==` przy myślniku,
`domkniety_werdyktem` zwracające zawsze `True`, `status_adr` czytające cały plik zamiast
nagłówka, pętla po kandydatach zredukowana do pustej krotki oraz literówka w każdej z dwóch
ścieżek artefaktów (`store.py`, `mcp_server.py`). Powód był w każdym przypadku ten sam
i jest wart nazwania, bo wraca: **samosprawdzenie, które nie woła sprawdzanej funkcji, nie
jest samosprawdzeniem**. Pierwsza wersja `test_samosprawdzenie_symetrii_pomiarow` przepisywała
ciało `statusy_pomiarow` do testu, a `test_samosprawdzenie_status_czytany_tylko_z_naglowka`
podrzucało dokument, w którym cytowany status **nie stał na początku linii** — więc oba
przechodziły identycznie przy strażniku działającym i zepsutym.

Stąd kształt po poprawce: strażniki bramek jadą z tablicy `BRAMKI`, a każdy jej wiersz niesie
razem z warunkiem także sposób podrzucenia artefaktu — dzięki temu „co strażnik sprawdza”
i „co samosprawdzenie uważa, że strażnik sprawdza” są jednym zdaniem, a nie dwoma do
uzgadniania (idiom `REGULY` z `test_boundaries.py`). Logika czytająca tabelę ADR-0004 wyszła
z ciała testu do `ocen_wiersz_kandydata`, bo funkcja wołana z dwóch stron da się sprawdzić na
materiale podrzuconym, a wyrażenie wpisane w test, który dziś przechodzi pusto — nie.

Czwarty strażnik — symetria statusu w `docs/pomiary.md` z wynikiem w `docs/decisions.md` —
istniał od 2026-09-17 do 2026-09-18 i został usunięty razem z `pomiary.md` (ADR-0005, Z-8).
Dwie listy wymagające synchronizatora powinny być jedną listą: status stoi odtąd w sekcji
„Status pomiarów" `decisions.md`, obok wyników, więc nie ma czego uzgadniać. Usunięto potrzebę
strażnika, nie strażnika.

**Kryterium wyjścia z bramki fazy 0 jest od 2026-09-18 per kanał** (ADR-0005, Z-1 i Z-2): wiersz
kanału obecnego w `kio_tool/source/` musi być zmierzony, a wejściem bramki są pomiary z pola
`pomiary:` w `contract.yaml` tego kanału. Kanał bez adaptera domyka wiersz trzecią postacią —
„nierozstrzygnięty (data, powód)" — i ta postać **zabrania** mu katalogu. Stary strażnik żądał
domknięcia czterech wierszy, z których dwa dotyczyły kanałów wykluczonych decyzjami A/B z roli
pierwszego adaptera, czyli żądań do dwóch serwisów po odpowiedź, której żadna gałąź nie użyje.

Żaden test w tym pliku nie dotyka sieci i nie importuje modułów produkcyjnych.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ADR = DOCS / "adr"

STATUS_PRZYJETY = "accepted"
"""Napis, po którym poznaje się przyjęty ADR.

Ta sama pisownia co w nagłówku ADR-0003 („Status: accepted (2026-09-15, decyzja
właściciela)"). Angielski napis w polskim dokumencie jest świadomy i pochodzi ze wzorca ADR;
wersja polska istniałaby wtedy w dwóch pisowniach naraz, czyli dałaby drugą listę do
uzgadniania.
"""


def status_adr(sciezka: Path) -> str:
    """Wartość pola `Status:` z nagłówka ADR-a albo pusty napis, gdy pliku nie ma.

    Czyta wyłącznie **nagłówek**, czyli do pierwszego separatora `---`: `Status:` przed nim jest
    deklaracją dokumentu, a to samo słowo za nim bywa cytatem z innego dokumentu (ADR-0004
    cytuje status ADR-0003, a ADR-0003 cytuje własny w treści).

    Granica była do przeglądu 2026-09-17 liczbą — stałe dziesięć linii — i kierunek jej pomyłki
    był wprawdzie bezpieczny (brak `Status:` nie znaczy „przyjęty"), ale skutkiem było
    **uśpienie** strażnika kryterium wyjścia: dokument z nagłówkiem o dwie linie dłuższym
    stawałby się „nieprzyjęty", a test tabeli przechodziłby pusto, nie mówiąc o tym nikomu.
    Separator stoi w każdym dokumencie tego projektu i nie zależy od tego, ile pól ma nagłówek.
    """
    if not sciezka.is_file():
        # `is_file`, nie `exists`: katalog też istnieje, a `read_text` na katalogu daje
        # `PermissionError` zamiast zdania dla operatora. Przegląd 2026-09-17 zmierzył tę drogę
        # na tej maszynie przy ścieżce `docs/adr` — czyli w dniu, w którym ta bramka miałaby się
        # zapalić na `store.py`, operator dostałby ślad stosu zamiast nazwy miny, przed którą
        # bramka stoi.
        return ""
    for linia in sciezka.read_text(encoding="utf-8").splitlines():
        if linia.startswith("---"):
            return ""
        if linia.startswith("Status:"):
            return linia.removeprefix("Status:").strip()
    return ""


def adr_przyjety(korzen: Path, numer: str) -> bool:
    """Czy ADR o tym numerze istnieje i jest przyjęty. Numer, nie nazwa — slug bywa zmieniany."""
    trafienia = sorted((korzen / "docs" / "adr").glob(f"{numer}_*.md"))
    return any(status_adr(plik).startswith(STATUS_PRZYJETY) for plik in trafienia)


def kanaly_w_drzewie(korzen: Path) -> frozenset[str]:
    """Nazwy kanałów obecne w `source/` — katalogi z czymkolwiek poza `.gitkeep`.

    Ta sama definicja „kanał istnieje", której używa reguła 21 w `test_boundaries.py`: obecność
    katalogu z zawartością, a nie wpis na liście. Roster nigdzie nie jest wypisany i to jest
    rozstrzygnięcie ADR-0003 — druga lista byłaby listą do uzgadniania.
    """
    katalog = korzen / "kio_tool" / "source"
    if not katalog.is_dir():
        return frozenset()
    return frozenset(
        podkatalog.name
        for podkatalog in katalog.iterdir()
        # `__pycache__` jest wytworem interpretera, nie kanałem — to samo zawężenie zakresu co
        # w `zbadaj_source` (`test_boundaries.py`). Bez niego pierwszy import `kio_tool.source`
        # w suicie dokładał „kanał" bez wiersza w tabeli ADR-0004 i bez kontraktu, czyli dwa
        # czerwone testy o katalogu, którego nikt nie napisał (etap III, 2026-09-18).
        if podkatalog.is_dir()
        and podkatalog.name != "__pycache__"
        and any(p.name != ".gitkeep" for p in podkatalog.iterdir())
    )


# --- trzy bramki „artefakt kodu dopiero po przyjętym ADR" -----------------------------------


class Bramka(NamedTuple):
    """Jedna implikacja „jeśli artefakt kodu, to przyjęty ADR" razem ze sposobem jej sprawdzenia.

    `obecne` i `podrzuc` stoją w **jednym** wierszu celowo: to jest ta sama myśl, którą
    `test_boundaries.py` zapisał przy `Regula.objete_skanem` — „co strażnik czyta" i „co
    samosprawdzenie uważa, że strażnik czyta" mają być jednym zdaniem. Do przeglądu
    2026-09-17 ścieżki `store.py` i `mcp_server.py` stały wyłącznie w ciałach testów, które
    przechodziły pusto; literówka w którejkolwiek z nich rozbrajała bramkę na zawsze i nie
    zapalała niczego (zmierzone mutacją: `store.py` → `sklep.py`, cały plik zielony).
    """

    nazwa: str
    adr: str
    obecne: Callable[[Path], frozenset[str]]
    podrzuc: Callable[[Path], None]
    powod: str


def _artefakt(wzgledna: str) -> Callable[[Path], frozenset[str]]:
    """Predykat obecności pojedynczego pliku, wyrażony tą samą ścieżką co jego podrzucenie."""

    def obecne(korzen: Path) -> frozenset[str]:
        return frozenset({wzgledna} if (korzen / wzgledna).exists() else ())

    return obecne


def _podrzuc_plik(wzgledna: str) -> Callable[[Path], None]:
    def podrzuc(korzen: Path) -> None:
        sciezka = korzen / wzgledna
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        sciezka.write_text("# podrzucony artefakt\n", encoding="utf-8")

    return podrzuc


def _podrzuc_kanal(korzen: Path) -> None:
    katalog = korzen / "kio_tool" / "source" / "saos"
    katalog.mkdir(parents=True, exist_ok=True)
    (katalog / "channel.py").write_text("", encoding="utf-8")


BRAMKI: tuple[Bramka, ...] = (
    Bramka(
        nazwa="source/<kanał> przed ADR-0004",
        adr="0004",
        obecne=kanaly_w_drzewie,
        podrzuc=_podrzuc_kanal,
        powod=(
            "bramka fazy 0 (ADR-0004 sekcja 5): kanał nie jest wybrany, więc adapter nie ma "
            "czego implementować"
        ),
    ),
    Bramka(
        nazwa="store.py przed ADR-0001",
        adr="0001",
        obecne=_artefakt("kio_tool/store.py"),
        podrzuc=_podrzuc_plik("kio_tool/store.py"),
        powod=(
            "audyt 9, faza 1: tożsamość dokumentu rozstrzygnięta przed **pierwszym zapisem do "
            "bazy**. To jest strażnik miny 1 — w CEIDG jeden wpis miał dwie pisownie "
            "identyfikatora, klucz główny był wrażliwy na wielkość liter, a jedna noc "
            "kosztowała 2 681 żądań i zero użytecznych rekordów. Zabrakło tam tej kolejności. "
            "Wejściami ADR-0001 są od 2026-09-18 (ADR-0005, Z-4): postać `source_ref` "
            "z pomiaru 3a, `ref_case` w `contract.yaml`, wielosygnaturowość, pomiar 17 na "
            "rekordach z pomiaru 3a oraz dwa pytania projektowe z `decisions.md`; pomiary 7 "
            "i 19 przeszły do polityki wersji kanału `uzp`"
        ),
    ),
    Bramka(
        nazwa="parser/sections.py przed ADR-0006",
        adr="0006",
        obecne=_artefakt("kio_tool/parser/sections.py"),
        podrzuc=_podrzuc_plik("kio_tool/parser/sections.py"),
        powod=(
            "ADR-0006 Z-2 i Z-14: segmentacja powstaje po pomiarze 5, a kotwice pochodzą "
            "z pomiaru na korpusie, nie z jednego dokumentu z 2020 roku — lista wzorców wpisana "
            "przed decyzją byłaby „wiadomo, że”, czyli tym, czego zakazuje zasada 7.1"
        ),
    ),
    Bramka(
        nazwa="ui/wizard.py przed ADR-0008",
        adr="0008",
        obecne=_artefakt("kio_tool/ui/wizard.py"),
        podrzuc=_podrzuc_plik("kio_tool/ui/wizard.py"),
        powod=(
            "ADR-0008 Z-17: kreator stoi na decyzji o punkcie zgody (Z-6) i o granicy `Akcje` "
            "(Z-7) — napisany przed nią trzymałby `Store` albo pytał o zgodę drugim żądaniem"
        ),
    ),
    Bramka(
        nazwa="demo/ przed ADR-0008",
        adr="0008",
        obecne=_artefakt("kio_tool/demo/__init__.py"),
        podrzuc=_podrzuc_plik("kio_tool/demo/__init__.py"),
        powod=(
            "ADR-0008 Z-1…Z-4: tryb pokazowy bez rozstrzygnięcia o znacznikach produkuje "
            "artefakty nieodróżnialne od prawdziwych — fałszywe cytaty przypisane KIO i Atlasowi"
        ),
    ),
    Bramka(
        nazwa="mcp_server.py przed ADR-0002",
        adr="0002",
        obecne=_artefakt("kio_tool/mcp_server.py"),
        podrzuc=_podrzuc_plik("kio_tool/mcp_server.py"),
        powod=(
            "audyt 9, faza 4: wejście warunkowe — ADR o tym, czy treść orzeczenia wolno wysłać "
            "do modelu, stoi **przed** warstwą. Faza 4 jest jedyną, której bramka stoi przed nią"
        ),
    ),
)


@pytest.mark.parametrize("bramka", BRAMKI, ids=[b.nazwa for b in BRAMKI])
def test_artefakt_nie_powstaje_przed_przyjeciem_swojego_adr(bramka: Bramka) -> None:
    """Strażnik na prawdziwym drzewie. Przechodzi dziś pusto — dowód działania niesie
    `test_samosprawdzenie_bramki_dziala_w_obie_strony` na korzeniu podrzuconym."""
    if adr_przyjety(ROOT, bramka.adr):
        return
    obecne = sorted(bramka.obecne(ROOT))
    pliki_adr = sorted(ADR.glob(f"{bramka.adr}_*.md"))
    status = status_adr(pliki_adr[0]) if pliki_adr else "brak pliku"
    assert not obecne, (
        f"w drzewie jest {obecne}, a ADR-{bramka.adr} nie jest przyjęty (status: {status!r}). "
        f"Powód kolejności: {bramka.powod}. Kod powstał przed decyzją — albo decyzja zapadła "
        "i jej ADR o tym nie wie."
    )


def _drzewo(korzen: Path, *, status_0004: str | None = None, kanal: str | None = None) -> Path:
    """Sztuczny korzeń repozytorium do samosprawdzeń — tyle plików, ile strażnik czyta."""
    (korzen / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (korzen / "kio_tool" / "source").mkdir(parents=True, exist_ok=True)
    if status_0004 is not None:
        (korzen / "docs" / "adr" / "0004_wybor_kanalu.md").write_text(
            f"# ADR-0004\n\nData: 2026-09-17\nStatus: {status_0004}\n",
            encoding="utf-8",
        )
    if kanal is not None:
        katalog = korzen / "kio_tool" / "source" / kanal
        katalog.mkdir(parents=True, exist_ok=True)
        (katalog / "channel.py").write_text("", encoding="utf-8")
    return korzen


@pytest.mark.parametrize("bramka", BRAMKI, ids=[b.nazwa for b in BRAMKI])
def test_samosprawdzenie_bramki_dziala_w_obie_strony(bramka: Bramka, tmp_path: Path) -> None:
    """Każda bramka sprawdzona w obie strony na korzeniu podrzuconym — bo prawdziwy jest pusty.

    Dwa stany, bo strażnik widzący tylko jeden z nich nie odróżnia się od testu, który zawsze
    przechodzi. Kierunek drugi — „podrzucony artefakt **jest** widziany" — jest tym, którego
    do 2026-09-17 nie miały ani `store.py`, ani `mcp_server.py`: literówka w ścieżce dawała
    strażnika patrzącego w nieistniejące miejsce i zielony przebieg na zawsze.
    """
    czysty = tmp_path / "czysty"
    czysty.mkdir()
    assert bramka.obecne(czysty) == frozenset(), (
        f"{bramka.nazwa}: strażnik widzi artefakt w korzeniu, w którym nie ma niczego"
    )

    z_artefaktem = tmp_path / "z_artefaktem"
    z_artefaktem.mkdir()
    bramka.podrzuc(z_artefaktem)
    assert bramka.obecne(z_artefaktem), (
        f"{bramka.nazwa}: podrzucony artefakt nie został zauważony — strażnik patrzy w inne "
        "miejsce niż to, w którym artefakt powstaje"
    )


def test_metatest_kazda_bramka_planu_faz_ma_swoj_wiersz() -> None:
    """Antypustka dla obu parametryzacji wyżej.

    Parametryzacja po pustej krotce przechodzi na zielono i wygląda identycznie jak
    przechodząca po trzech bramkach; tablica okrojona do dwóch wygląda identycznie jak pełna.
    Numery ADR-ów są wypisane, bo bramka usunięta z tablicy przestaje obowiązywać bez jednego
    czerwonego testu — to ta sama cicha awaria, przed którą broni reszta pliku, o poziom wyżej.
    """
    assert {b.adr for b in BRAMKI} == {"0001", "0002", "0004", "0006", "0008"}, (
        f"tablica bramek niesie ADR-y {sorted(b.adr for b in BRAMKI)}; plan faz (audyt 9) stawia "
        "trzy warunki kolejności, ADR-0006 Z-14 czwarty, ADR-0008 Z-17 piąty — każdy ma tu "
        "mieć wiersz"
    )
    assert all(b.powod for b in BRAMKI), "bramka bez powodu kolejności jest bramką porzuconą"
    assert len({b.nazwa for b in BRAMKI}) == len(BRAMKI), "dwie bramki o tej samej nazwie"


def test_samosprawdzenie_adr_przyjety_odroznia_trzy_stany(tmp_path: Path) -> None:
    """Przyjęty, nieprzyjęty i nieistniejący — trzy stany, z których tylko pierwszy otwiera
    bramkę. Brak pliku nie jest przyjęciem i to jest kierunek, w którym pomyłka jest cicha:
    ADR skasowany przy renumeracji **zamyka** bramkę zamiast ją otworzyć."""
    assert not adr_przyjety(_drzewo(tmp_path / "c", status_0004="draft"), "0004")
    assert adr_przyjety(
        _drzewo(tmp_path / "d", status_0004="accepted (2026-09-20, decyzja właściciela)"), "0004"
    )
    assert not adr_przyjety(_drzewo(tmp_path / "e"), "0004"), "brak pliku to nie jest przyjęcie"


def test_samosprawdzenie_kanal_bez_zawartosci_nie_jest_kanalem(tmp_path: Path) -> None:
    """`.gitkeep` w katalogu kanału nie czyni kanału — inaczej pusty szkielet zapalałby bramkę;
    `__pycache__` też nie — inaczej pierwszy import pakietu zapalałby ją na katalogu
    interpretera."""
    korzen = _drzewo(tmp_path, status_0004="draft")
    pusty = korzen / "kio_tool" / "source" / "uzp"
    pusty.mkdir(parents=True)
    (pusty / ".gitkeep").write_text("", encoding="utf-8")
    pycache = korzen / "kio_tool" / "source" / "__pycache__"
    pycache.mkdir()
    (pycache / "contract.cpython-312.pyc").write_bytes(b"")
    assert kanaly_w_drzewie(korzen) == frozenset()
    assert kanaly_w_drzewie(_drzewo(tmp_path / "z", status_0004="draft", kanal="saos")) == {"saos"}


def test_samosprawdzenie_status_czytany_tylko_z_naglowka(tmp_path: Path) -> None:
    """`Status:` w treści dokumentu nie jest statusem dokumentu.

    ADR-0004 cytuje w treści status ADR-0003; gdyby strażnik czytał cały plik, cudzy przyjęty
    status ogłosiłby przyjęcie tego dokumentu.

    Materiał trafia w **jedyny** stan, w którym granica dziesięciu linii cokolwiek robi, i to
    jest poprawka z przeglądu 2026-09-17. Pierwsze dwie wersje w ten stan nie trafiały:
    wersja pierwsza podrzucała cytat jako `` ADR-0003 ma `Status: accepted` ``, czyli linię,
    która nie zaczyna się od `Status:` i nie jest widziana niezależnie od granicy; wersja druga
    przepisała cytat na początek linii, ale zostawiła **własny** `Status: draft` w nagłówku —
    a pętla zwraca na pierwszym trafieniu, więc dalsza treść i tak nie ma znaczenia. Obie
    przechodziły zielono przy `[:10]` skreślonym z `status_adr` (zmierzone mutacją).

    Stanem, którego granica broni, jest dokument **bez własnego pola** `Status:` w nagłówku,
    cytujący cudzy nagłówek niżej: bez granicy skan przypisałby mu cudze `accepted` i otworzył
    bramkę fazy 0 na dokumencie, który niczego nie deklaruje. Blok kodu z nagłówkiem cudzego
    ADR-a jest najbardziej prawdopodobną postacią cytatu, bo tak cytuje się nagłówki w tym
    projekcie. Drugi kierunek — nagłówek własny stoi, cytat jest niżej — trzyma asercja na
    końcu tego testu.
    """
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    cytat = "ADR-0003 niesie w nagłówku:\n\n```\nStatus: accepted (2026-09-15, właściciel)\n```\n"

    bez_wlasnego = tmp_path / "docs" / "adr" / "0004_wybor_kanalu.md"
    bez_wlasnego.write_text(
        "# ADR-0004\n\nData: 2026-09-17\n\n---\n\n" + "wypełniacz\n" * 20 + cytat,
        encoding="utf-8",
    )

    assert status_adr(bez_wlasnego) == "", (
        "dokument bez własnego pola `Status:` dostał status z cytatu w treści — `status_adr` "
        "czyta dalej niż nagłówek, więc cudze `accepted` otwiera bramkę fazy 0"
    )
    assert not adr_przyjety(tmp_path, "0004")

    z_wlasnym = tmp_path / "docs" / "adr" / "0004_wybor_kanalu.md"
    z_wlasnym.write_text(
        "# ADR-0004\n\nData: 2026-09-17\nStatus: draft\n\n---\n\n" + "wypełniacz\n" * 20 + cytat,
        encoding="utf-8",
    )

    assert status_adr(z_wlasnym) == "draft"
    assert not adr_przyjety(tmp_path, "0004")


def test_samosprawdzenie_status_nieobecny_w_naglowku_nie_otwiera_bramki(tmp_path: Path) -> None:
    """Dokument bez pola `Status:` nie jest dokumentem przyjętym — pusty napis nie zaczyna się
    od `accepted`, więc kierunek błędu jest bezpieczny i ta asercja go utrwala."""
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    plik = tmp_path / "docs" / "adr" / "0004_wybor_kanalu.md"
    plik.write_text("# ADR-0004\n\nData: 2026-09-17\n", encoding="utf-8")
    assert status_adr(plik) == ""
    assert not adr_przyjety(tmp_path, "0004")


# --- kryterium wyjścia ADR-0004: przyjęty znaczy wypełniony --------------------------------

POLE_POMIAROW_KONTRAKTU = "pomiary:"
"""Pole `contract.yaml`, które niesie wejście bramki dla swojego kanału (ADR-0005, Z-1).

Lista pomiarów wejściowych stała do 2026-09-18 w tym pliku jako ręcznie pisana krotka
`POMIARY_WEJSCIOWE_BRAMKI` i w ADR-0004 sekcja 3 jako tabela — dwa miejsca, które tego dnia rano
mówiły dwie rzeczy o pomiarze 23. Kontrakt kanału jest jedynym miejscem, które wie, czego ten
kanał wymagał, więc lista mieszka tam; strażnik ją czyta, nie powtarza.
"""


def pomiary_zadeklarowane(contract: Path) -> frozenset[str]:
    """Numery pomiarów z pola `pomiary:` kontraktu — odczyt tekstowy, bez parsera YAML.

    Ten sam kształt co `role_zadeklarowane` w `test_boundaries.py` i z tego samego powodu:
    kontrakt czytany bez parsera rozumie tyle, ile deklaruje (lista w nawiasie albo po przecinku,
    komentarz po `#` odcięty), a przy niezrozumiałym daje zbiór pusty — czyli zarzut, nie
    zwolnienie.
    """
    for linia in contract.read_text(encoding="utf-8").splitlines():
        if not linia.startswith(POLE_POMIAROW_KONTRAKTU):
            continue
        wartosc = linia.removeprefix(POLE_POMIAROW_KONTRAKTU).split("#", 1)[0].strip().strip("[]")
        return frozenset(
            czesc.strip().strip("\"'") for czesc in wartosc.split(",") if czesc.strip()
        )
    return frozenset()


def pomiary_wejsciowe_bramki(korzen: Path) -> dict[str, frozenset[str]]:
    """Kanał obecny w `source/` → pomiary, które jego kontrakt czyni wejściem bramki.

    Kanał bez `contract.yaml` albo bez pola `pomiary:` dostaje zbiór pusty — i to jest zarzut,
    nie zwolnienie (`test_kanal_w_drzewie_deklaruje_swoje_pomiary_wejsciowe`).
    """
    wynik: dict[str, frozenset[str]] = {}
    for kanal in sorted(kanaly_w_drzewie(korzen)):
        contract = korzen / "kio_tool" / "source" / kanal / "contract.yaml"
        wynik[kanal] = pomiary_zadeklarowane(contract) if contract.is_file() else frozenset()
    return wynik


ZNAK_NIEZMIERZONE = "—"
"""Myślnik otwierający komórkę znaczy „niezmierzone", nigdy „brak" (ADR-0004 sekcja 4).

Sprawdzany jest **początek** komórki, nie jej całość: pierwsza wersja tego strażnika porównywała
całą treść i przechodziła nad „— (pomiar 2a)", czyli nad komórką, która wprost mówi, że wyniku
jeszcze nie ma. Pokazała to mutacja (status ADR-a przestawiony na `accepted` 2026-09-17), a nie
zielony przebieg — to jest ta sama lekcja, którą projekt zapisał przy `richtext.safe`
i `ratelimit.note_response`.
"""

POSTACI_DOMKNIECIA_WERDYKTEM = ("odpada", "nierozstrzygnięty")
"""Postaci z sekcji 4.2, które zamykają wiersz **bez** wypełniania komórek.

Postać „zmierzony" nie ma własnego napisu, bo poznaje się ją po tym, że w wierszu nie ma już
komórek niezmierzonych — i jest jedyną dopuszczalną dla kanału obecnego w `kio_tool/source/`.

**„nierozstrzygnięty (data, powód odroczenia)" weszła 2026-09-18 (ADR-0005, Z-2)** i nie jest
powrotem postaci usuniętej 2026-09-17. Tamta — „otwarty warunkowo: wniosek złożony {data}" —
pozwalała zamknąć wiersz kanału, **który wolno było budować**, bez pomiaru i bez werdyktu, a po
decyzji A straciła jedynego użytkownika (`uzp_zrzut` zamyka się werdyktem „odpada"). Ta zamyka
wiersz kanału, którego budować **nie wolno**: kanał z takim werdyktem obecny w drzewie jest
zarzutem (`zarzuty_do_tabeli`), tak samo jak kanał z werdyktem „odpada". Kryterium chroni więc tę
samą własność co przedtem — żaden adapter bez pomiaru — implikacją drzewo → tabela, i przestaje
chronić własności „żaden korpus, zanim nie zmierzysz wszystkich kandydatów", która nie miała
obserwowalnej korzyści, a kosztowała żądania do dwóch cudzych serwisów.
"""


def domkniety_werdyktem(werdykt: str) -> bool:
    """Czy wiersz zamyka się werdyktem zamiast pomiarem (ADR-0004 sekcja 4.2, postaci 2 i 3)."""
    return postac_werdyktu(werdykt) is not None


def postac_werdyktu(werdykt: str) -> str | None:
    """Która postać z `POSTACI_DOMKNIECIA_WERDYKTEM` otwiera komórkę werdyktu; `None` gdy żadna."""
    maly = werdykt.strip().strip("*").lower()
    return next(
        (postac for postac in POSTACI_DOMKNIECIA_WERDYKTEM if maly.startswith(postac)), None
    )


def werdykt_domykajacy(tresc: str, kanal: str) -> str | None:
    """Postać werdyktu zamykającego wiersz kandydata albo `None` (brak wiersza, brak werdyktu)."""
    wiersz = next((w for w in tresc.splitlines() if w.startswith(f"| {kanal} ")), None)
    if wiersz is None:
        return None
    komorki = [k.strip() for k in wiersz.strip().strip("|").split("|")]
    return postac_werdyktu(komorki[-1]) if komorki else None


BRAK_WIERSZA = -1
"""Znacznik „tabela nie ma wiersza tego kandydata" w wyniku `ocen_wiersz_kandydata`.

Osobny od pustej listy, bo to dwa różne naruszenia kryterium wyjścia: wiersz nieobecny znaczy
„kandydata w ogóle nie rozważono", a lista pusta znaczy „rozważono i domknięto".
"""


WZORZEC_WIERSZA_KANDYDATA = re.compile(r"^\|\s*(`[a-z_]+`)\s*\|")


def kandydaci_w_tabeli(tresc: str) -> frozenset[str]:
    """Nazwy kanałów **wyczytane z tabeli** sekcji 4, a nie z listy obok niej.

    Dopisana w przeglądzie 2026-09-17, bo `WIERSZE_KANDYDATOW` było drugą listą do uzgadniania —
    i to w strażniku kryterium wyjścia. Piąty kandydat dopisany do tabeli z pustymi komórkami
    **przechodził bramkę**: strażnik chodził po czterech nazwach wpisanych ręką i nowego wiersza
    nie widział. To jest dokładnie ten kształt, dla którego powstał sam ADR-0004 (sekcja 1:
    „trzy listy tego samego"), a kierunek „drzewo → lista" był w tym pliku domknięty dla numerów
    ADR-ów i otwarty dla kandydatów.
    """
    return frozenset(
        dopasowanie.group(1)
        for linia in tresc.splitlines()
        if (dopasowanie := WZORZEC_WIERSZA_KANDYDATA.match(linia)) is not None
    )


def ocen_wiersz_kandydata(tresc: str, kanal: str) -> list[int]:
    """Pozycje niezmierzonych komórek w wierszu kandydata; `[]` gdy domknięty, `[BRAK_WIERSZA]`
    gdy wiersza nie ma.

    Wyjęte z ciała testu w przeglądzie 2026-09-17 i to jest cała poprawka tego strażnika.
    Test, który przechodzi pusto, nie sprawdza swojego własnego ciała — więc dopóki ta logika
    stała w środku `if adr_przyjety(...)`, przechodziły przez nią zielono: `startswith`
    zamienione na `==` (dokładnie ta regresja, którą opisuje `ZNAK_NIEZMIERZONE`),
    `domkniety_werdyktem` zwracające zawsze `True` i pętla po pustej krotce kandydatów.
    Funkcja wołana z dwóch stron da się sprawdzić na materiale podrzuconym; wyrażenie w ciele
    uśpionego testu — nie.
    """
    wiersz = next((w for w in tresc.splitlines() if w.startswith(f"| {kanal} ")), None)
    if wiersz is None:
        return [BRAK_WIERSZA]
    komorki = [k.strip() for k in wiersz.strip().strip("|").split("|")]
    if komorki and domkniety_werdyktem(komorki[-1]):
        return []
    return [i for i, k in enumerate(komorki) if k.startswith(ZNAK_NIEZMIERZONE)]


def zarzuty_do_tabeli(tresc: str, w_drzewie: frozenset[str]) -> list[str]:
    """Wszystko, co blokuje zamknięcie bramki po stronie tabeli kandydatów; `[]` gdy domknięta.

    Dwa źródła kandydatów: **wiersze tabeli** i **katalogi w `source/`**. Pierwsze, bo kandydat
    dopisany do tabeli wchodzi pod strażnika bez niczyjej pamięci (do przeglądu 2026-09-17
    strażnik chodził po czterech nazwach wpisanych ręką). Drugie od 2026-09-18 (ADR-0005), bo
    kanał z adapterem musi mieć wiersz zmierzony — to jest cała implikacja drzewo → tabela.
    Kanał w drzewie z werdyktem „odpada" albo „nierozstrzygnięty" jest zarzutem: werdykt mówi
    „nie buduj", a katalog mówi „zbudowane". Kanał, który z tabeli **zniknął**, nadal zapala brak
    wiersza — ale tylko wtedy, gdy stoi w drzewie; kanał bez adaptera i bez wiersza nie jest
    kandydatem, którego ktoś rozważał.
    """
    zarzuty: list[str] = []
    kandydaci = kandydaci_w_tabeli(tresc) | {f"`{kanal}`" for kanal in w_drzewie}
    for kanal in sorted(kandydaci):
        nazwa = kanal.strip("`")
        puste = ocen_wiersz_kandydata(tresc, kanal)
        werdykt = werdykt_domykajacy(tresc, kanal)
        if puste == [BRAK_WIERSZA]:
            zarzuty.append(f"  {kanal}: tabela nie ma takiego wiersza")
        elif nazwa in w_drzewie and werdykt is not None:
            zarzuty.append(
                f"  {kanal}: jest w `kio_tool/source/`, a wiersz zamyka go werdyktem „{werdykt}” "
                "— kanał, którego nie wolno budować, ma katalog"
            )
        elif puste:
            dopisek = " — a kanał obecny w drzewie musi być zmierzony" if nazwa in w_drzewie else ""
            zarzuty.append(
                f"  {kanal}: niezmierzone komórki na pozycjach {puste}. Sekcja 4.2 daje trzy "
                "postaci domknięcia: zmierzony, odpada z powodem i datą, nierozstrzygnięty z datą "
                f"i powodem odroczenia{dopisek}"
            )
    return zarzuty


def test_samosprawdzenie_zarzutow_do_tabeli() -> None:
    """Obserwator ciała uśpionego strażnika — na tabeli podrzuconej, bo prawdziwa go nie budzi."""
    zarzuty = zarzuty_do_tabeli(TABELA_PODRZUCONA, frozenset())

    assert any("kanal_dopisany_jutro" in z for z in zarzuty), (
        "wiersz dopisany do tabeli nie trafił pod strażnika — kryterium wyjścia przepuściłoby "
        "kandydata z pustymi komórkami"
    )
    assert any("`atlas`" in z for z in zarzuty), "wiersz z samymi myślnikami ma być zarzutem"
    assert not any("`saos`" in z for z in zarzuty), "wiersz zmierzony nie jest zarzutem"
    assert not any("`uzp_zrzut`" in z for z in zarzuty), "werdykt „odpada” domyka wiersz"
    assert not any("`odroczony`" in z for z in zarzuty), (
        "„nierozstrzygnięty” domyka wiersz kanału, którego nie ma w drzewie (ADR-0005, Z-2)"
    )
    assert any("`saos_api`" in z for z in zarzuty), (
        "„otwarty warunkowo” przestało domykać wiersz 2026-09-17 — postać bez użytkownika była "
        "furtką pozwalającą zamknąć kandydata bez pomiaru i bez werdyktu"
    )
    assert not zarzuty_do_tabeli(TABELA_DOMKNIETA, frozenset({"saos", "atlas"})), (
        "tabela domknięta z kanałami zmierzonymi w drzewie nie ma zarzutów"
    )

    # Kierunek dopisany 2026-09-18: kanał w drzewie, którego wiersz mówi „nie buduj".
    for kanal, tabela in (("odroczony", TABELA_PODRZUCONA), ("uzp_zrzut", TABELA_DOMKNIETA)):
        z_katalogiem = zarzuty_do_tabeli(tabela, frozenset({kanal}))
        assert any(f"`{kanal}`" in z and "nie wolno budować" in z for z in z_katalogiem), (
            f"kanał `{kanal}` z werdyktem zamykającym ma katalog w drzewie, a strażnik milczy"
        )
    assert any(
        "`nowy`" in z and "nie ma takiego wiersza" in z
        for z in zarzuty_do_tabeli(TABELA_DOMKNIETA, frozenset({"nowy"}))
    ), "kanał w drzewie bez wiersza w tabeli przeszedł bramkę"

    # Trzeci stan, bez którego dwa poprzednie nie wystarczają: **znany kandydat zniknął**.
    # Mutacja z 2026-09-17 („`if puste == [BRAK_WIERSZA]` → `if False`") przechodziła zielono,
    # bo cały materiał miał komplet czterech wierszy — czyli stan, o którym mówi `BRAK_WIERSZA`,
    # nie występował w żadnym samosprawdzeniu.
    bez_uzp = "\n".join(
        linia for linia in TABELA_DOMKNIETA.splitlines() if not linia.startswith("| `uzp` ")
    )
    zniknal = zarzuty_do_tabeli(bez_uzp, frozenset({"uzp"}))

    assert any("`uzp`" in z and "nie ma takiego wiersza" in z for z in zniknal), (
        "kandydat usunięty z tabeli przeszedł bramkę — znikanie wiersza jest tańszym sposobem "
        f"domknięcia niż jego wypełnienie; zarzuty: {zniknal}"
    )


def test_przyjety_adr_0004_ma_wypelniona_tabele() -> None:
    """Kryterium wyjścia (ADR-0004 sekcja 5 pkt 2 i 3) sprawdzone, a nie zadeklarowane.

    Zapala się wtedy i tylko wtedy, gdy ktoś ogłosi bramkę zamkniętą przy pustych komórkach.
    Dziś ADR jest w stanie `draft`, więc test przechodzi pusto — i to jest poprawny stan.
    Dowód działania niesie `test_samosprawdzenie_odczytu_wiersza_kandydata`.

    Strażnik jest celowo gruby: sprawdza obecność wiersza i **brak samotnego myślnika** tam,
    gdzie ma stać wynik. Nie sprawdza, czy wynik jest prawdziwy — tego nie zrobi żaden test,
    i dlatego bramka kończy się podpisem właściciela, a nie zielonym paskiem.

    Całe rozstrzyganie mieszka w `zarzuty_do_tabeli`, a nie w tym ciele, i to jest druga runda
    tej samej poprawki co przy `ocen_wiersz_kandydata`. Mutacja z 2026-09-17 pokazała, że
    zawężenie pętli z „kandydaci z tabeli ∪ lista" z powrotem do samej listy przechodzi tu
    **zielono**: dopóki ADR jest w stanie `draft`, ciało tego testu nie wykonuje się ani razu,
    więc każda zmiana w nim jest niewidoczna. Wyjęta funkcja ma obserwatora w każdym przebiegu.
    """
    if not adr_przyjety(ROOT, "0004"):
        return
    zarzuty = zarzuty_do_tabeli(
        (ADR / "0004_wybor_kanalu.md").read_text(encoding="utf-8"), kanaly_w_drzewie(ROOT)
    )

    assert not zarzuty, (
        "ADR-0004 jest przyjęty, a tabela sekcji 4 nie jest domknięta:\n" + "\n".join(zarzuty)
    )


def test_kanal_w_drzewie_ma_wiersz_zmierzony_niezaleznie_od_statusu_adr() -> None:
    """Implikacja drzewo → tabela (ADR-0005, Z-2) obowiązuje także wtedy, gdy ADR-0004 jest
    w stanie `draft` — bo wtedy kanału w drzewie w ogóle nie powinno być (tablica `BRAMKI`),
    a gdyby był, dwa strażniki mają mówić to samo, nie jeden."""
    w_drzewie = kanaly_w_drzewie(ROOT)
    if not w_drzewie:
        return
    tresc = (ADR / "0004_wybor_kanalu.md").read_text(encoding="utf-8")
    zarzuty = [
        z for z in zarzuty_do_tabeli(tresc, w_drzewie) if any(f"`{k}`" in z for k in w_drzewie)
    ]

    assert not zarzuty, "kanał w `kio_tool/source/` bez zmierzonego wiersza:\n" + "\n".join(zarzuty)


def test_samosprawdzenie_kandydaci_czytani_z_tabeli_a_nie_z_listy_obok() -> None:
    """Dowód, że dopisany wiersz naprawdę wchodzi pod strażnika — na materiale podrzuconym,
    bo na prawdziwej tabeli te dwa zbiory są dziś równe i nie ma czego obserwować."""
    znalezieni = kandydaci_w_tabeli(TABELA_PODRZUCONA)

    assert "`saos`" in znalezieni and "`uzp_zrzut`" in znalezieni
    assert "`kanal_dopisany_jutro`" in znalezieni, (
        "wiersz kandydata dopisany do tabeli nie został zauważony — strażnik kryterium wyjścia "
        "przepuściłby go z pustymi komórkami"
    )
    assert "`nagłówek`" not in znalezieni
    assert ocen_wiersz_kandydata(TABELA_PODRZUCONA, "`kanal_dopisany_jutro`") == [1, 2, 3, 4], (
        "dopisany wiersz ma same myślniki i musi być widziany jako niezmierzony"
    )


TABELA_PODRZUCONA = """## 4. Kandydaci

| kanał | zasięg | licencja | capabilities() | werdykt |
|---|---|---|---|---|
| `saos` | 2007-2018 | CC BY 4.0 | pełny tekst | zmierzony 2026-09-20 |
| `atlas` | — | — | — | — |
| `uzp` | 2018-2026 | — (pomiar 14) | liczniki | zmierzony 2026-09-20 |
| `uzp_zrzut` | — | — | — | **odpada** (2026-09-20, FTP milczy — pomiar 1) |
| `saos_api` | — | — | — | otwarty warunkowo: wniosek z 2026-09-18, termin 14 dni |
| `odroczony` | — | — | — | **nierozstrzygnięty** (2026-09-20, nie jest pierwszym adapterem) |
| `kanal_dopisany_jutro` | — | — | — | — |
"""
"""Tabela wymyślona, w kształcie sekcji 4 ADR-0004 — materiał do samosprawdzenia skanu.

Wiersz `uzp` niesie komórkę `— (pomiar 14)`: to jest postać, nad którą pierwsza wersja skanu
przechodziła obojętnie, bo porównywała całą treść komórki z myślnikiem zamiast patrzeć na jej
początek. Komórka mówi wprost, że wyniku jeszcze nie ma, i ma się liczyć jako niezmierzona.

Ten docstring stał do przeglądu 2026-09-18 **pod `TABELA_DOMKNIETA`**, jako drugi napis z rzędu
po jej własnym opisie — czyli opisywał nie tę stałą, o której mówił, a Python traktował go jak
wyrażenie bez wartości. Objaw jest z tej samej rodziny co reszta tego pliku: napis, który
wygląda na dokumentację i nią nie jest.
"""

TABELA_DOMKNIETA = """## 4. Kandydaci

| kanał | zasięg | licencja | capabilities() | werdykt |
|---|---|---|---|---|
| `saos` | 2007-2018 | CC BY 4.0 | pełny tekst | zmierzony 2026-09-20 |
| `atlas` | 2007-2026 | CC BY 4.0 | pełny tekst | zmierzony 2026-09-20 |
| `uzp` | 2018-2026 | brak warunków (pomiar 14, 2026-09-15) | liczniki | zmierzony 2026-09-20 |
| `uzp_zrzut` | — | — | — | **odpada** (2026-09-20, wniosek nie zostanie złożony) |
"""
"""Ta sama tabela w stanie, który bramkę **domyka** — druga strona samosprawdzenia.

Bez niej test zarzutów sprawdzałby wyłącznie, że funkcja potrafi coś zgłosić, a nie że potrafi
też zamilknąć. Strażnik, który zgłasza zawsze, jest tak samo bezużyteczny jak ten, który nie
zgłasza nigdy — tylko głośniej.
"""


@pytest.mark.parametrize(
    ("kanal", "oczekiwane", "co_sprawdza"),
    [
        ("`saos`", [], "wiersz z kompletem pomiarów jest domknięty"),
        ("`atlas`", [1, 2, 3, 4], "same myślniki — cztery komórki niezmierzone"),
        ("`uzp`", [2], "„— (pomiar 14)” liczy się jako niezmierzona, mimo dopisku"),
        ("`uzp_zrzut`", [], "werdykt „odpada” domyka wiersz bez wypełniania komórek"),
        ("`saos_api`", [1, 2, 3], "„otwarty warunkowo” **nie** domyka wiersza od 2026-09-17"),
        ("`odroczony`", [], "„nierozstrzygnięty” domyka wiersz od 2026-09-18 (ADR-0005, Z-2)"),
        ("`nieobecny`", [BRAK_WIERSZA], "kandydat bez wiersza to inne naruszenie niż pusty"),
    ],
)
def test_samosprawdzenie_odczytu_wiersza_kandydata(
    kanal: str, oczekiwane: list[int], co_sprawdza: str
) -> None:
    """Skan tabeli sprawdzony na tabeli podrzuconej — bo na prawdziwej dziś nie działa.

    Sześć stanów, bo tylko dwa z nich są domknięciem. Skan widzący wyłącznie stan „komórka
    pusta" nie odróżniłby się od takiego, który zawsze zwraca `[]` — a to jest dokładnie ta
    mutacja, która 2026-09-17 przeszła przez cały zielony przebieg tego pliku.
    """
    assert ocen_wiersz_kandydata(TABELA_PODRZUCONA, kanal) == oczekiwane, co_sprawdza


def test_prawdziwa_tabela_adr_0004_jest_czytana_i_niesie_czterech_kandydatow() -> None:
    """Antypustka dla skanu na prawdziwym dokumencie.

    Do 2026-09-18 tę rolę pełniła lista `WIERSZE_KANDYDATOW` w tym pliku — druga lista do
    uzgadniania, usunięta razem z kryterium per kanał (ADR-0005). Skan ma widzieć cztery wiersze,
    które sekcja 4 ADR-0004 niesie od 2026-09-17; gdyby wzorzec początku wiersza rozjechał się
    z pisownią, strażnik kryterium wyjścia chodziłby po pustym zbiorze i milczał.
    """
    tresc = (ADR / "0004_wybor_kanalu.md").read_text(encoding="utf-8")
    znalezieni = kandydaci_w_tabeli(tresc)

    assert {"`saos`", "`atlas`", "`uzp`", "`uzp_zrzut`"} <= znalezieni, (
        f"skan widzi w prawdziwej tabeli tylko {sorted(znalezieni)}"
    )
    for kanal in znalezieni:
        assert ocen_wiersz_kandydata(tresc, kanal) != [BRAK_WIERSZA], (
            f"skan nie znajduje wiersza {kanal}, choć sam go wyczytał — wzorzec początku wiersza "
            "rozjechał się między `kandydaci_w_tabeli` a `ocen_wiersz_kandydata`"
        )


def sekcja_pomiaru_w_decisions(decisions: str, numer: str) -> bool:
    """Czy `decisions.md` ma sekcję `## Pomiar N` — jedyne miejsce z tym wzorcem.

    Wzorzec stał wcześniej w dwóch testach osobno, a jeden z nich przechodzi pusto. Numer idzie
    przez `\\b`, bo `## Pomiar 14` nie jest wynikiem pomiaru 1, a `## Pomiar 2a` nie jest
    wynikiem pomiaru 2.
    """
    return re.search(rf"^## Pomiar {re.escape(numer)}\b", decisions, re.MULTILINE) is not None


def test_samosprawdzenie_rozpoznawania_sekcji_pomiaru() -> None:
    """Numer pomiaru nie jest przedrostkiem innego numeru — i to jest cały ciężar `\\b`.

    Bez niego `## Pomiar 14` zaliczałoby pomiar 1, a bramka fazy 0 zamykałaby się na wyniku
    innego pomiaru niż wymieniony w jej wejściu.
    """
    material = "## Pomiar 14 — warunki\n\ntresc\n\n## Pomiar 2a — dostep\n"

    assert sekcja_pomiaru_w_decisions(material, "14")
    assert sekcja_pomiaru_w_decisions(material, "2a")
    assert not sekcja_pomiaru_w_decisions(material, "1"), "`## Pomiar 14` zaliczone jako pomiar 1"
    assert not sekcja_pomiaru_w_decisions(material, "2"), "`## Pomiar 2a` zaliczone jako pomiar 2"
    assert not sekcja_pomiaru_w_decisions("tekst ## Pomiar 14 w linii", "14"), (
        "wzmianka w środku linii zaliczona jako sekcja z wynikiem"
    )


def test_kanal_w_drzewie_ma_wyniki_swoich_pomiarow_w_decisions() -> None:
    """Kryterium wyjścia pkt 4 w brzmieniu ADR-0005: wynik każdego pomiaru z pola `pomiary:`
    kontraktu kanału obecnego w `source/` stoi w `docs/decisions.md`.

    Niezależne od statusu ADR-0004 — kanał w drzewie i tak wymaga przyjętego ADR (tablica
    `BRAMKI`), a tu chodzi o to, żeby przyjęcie nie było jedyną rzeczą, jaką ten kanał ma za sobą.
    Przechodzi dziś pusto; dowód działania niesie
    `test_samosprawdzenie_pomiary_czytane_z_kontraktu`.
    """
    decisions = (DOCS / "decisions.md").read_text(encoding="utf-8")
    brakujace = {
        kanal: [
            numer for numer in sorted(pomiary) if not sekcja_pomiaru_w_decisions(decisions, numer)
        ]
        for kanal, pomiary in pomiary_wejsciowe_bramki(ROOT).items()
    }
    brakujace = {kanal: numery for kanal, numery in brakujace.items() if numery}

    assert not brakujace, (
        f"kanał w `kio_tool/source/` bez wyniku swoich pomiarów wejściowych w `decisions.md`: "
        f"{brakujace}. Adapter zbudowany bez zapisanego pomiaru jest zdaniem, nie pomiarem."
    )


def test_kanal_w_drzewie_deklaruje_swoje_pomiary_wejsciowe() -> None:
    """Kanał bez pola `pomiary:` w kontrakcie nie ma wejścia bramki — czyli test wyżej
    przechodziłby dla niego pusto. Pusty zbiór jest zarzutem, nie zwolnieniem."""
    bez_pomiarow = sorted(k for k, pomiary in pomiary_wejsciowe_bramki(ROOT).items() if not pomiary)

    assert not bez_pomiarow, (
        f"kanały {bez_pomiarow} są w `kio_tool/source/`, a ich `contract.yaml` nie wymienia "
        "pomiarów wejściowych (pole `pomiary:`, ADR-0005 Z-1)"
    )


def test_samosprawdzenie_pomiary_czytane_z_kontraktu(tmp_path: Path) -> None:
    """Czytnik kontraktu sprawdzony na drzewie podrzuconym — na prawdziwym nie ma dziś kanału.

    Trzy stany: kanał bez kontraktu (zbiór pusty), kontrakt z listą i komentarzem po `#`
    (komentarz nie wchodzi do numerów), kontrakt bez pola (zbiór pusty). Woła **te** funkcje, nie
    ich przepisane ciała — lekcja z 2026-09-17.
    """
    korzen = _drzewo(tmp_path, status_0004="accepted (2026-09-20, właściciel)", kanal="atlas")
    kontrakt = korzen / "kio_tool" / "source" / "atlas" / "contract.yaml"

    assert pomiary_wejsciowe_bramki(korzen) == {"atlas": frozenset()}, "kanał bez kontraktu"

    kontrakt.write_text(
        "kanal: atlas\nrole: [masowa]\npomiary: [3a, 23]  # wejście bramki\n", encoding="utf-8"
    )
    assert pomiary_wejsciowe_bramki(korzen) == {"atlas": frozenset({"3a", "23"})}

    kontrakt.write_text("kanal: atlas\nrole: [masowa]\n", encoding="utf-8")
    assert pomiary_zadeklarowane(kontrakt) == frozenset(), "brak pola ma dać zbiór pusty"
    assert pomiary_wejsciowe_bramki(korzen) == {"atlas": frozenset()}


def test_samosprawdzenie_kontrakt_w_pisowni_wielolinijkowej_jest_zarzutem(tmp_path: Path) -> None:
    """Czwarty stan, dopisany 2026-09-18: pole `pomiary:` rozpisane po YAML-owemu, w liniach.

    Czytnik jest tekstowy i „rozumie tyle, ile deklaruje" — tak mówi jego docstring. Pisownia
    wielolinijkowa jest jednak w YAML-u **równie zwyczajna** jak lista w nawiasie, więc nie jest
    to stan egzotyczny: to jest najbardziej prawdopodobny sposób, w jaki prawdziwy
    `contract.yaml` wymknie się temu odczytowi.

    Cała wartość zdania „przy niezrozumiałym daje zbiór pusty — czyli zarzut, nie zwolnienie"
    leży w kierunku tej pomyłki, a do dziś nie miało ono ani jednej asercji. Kierunek jest
    bezpieczny: kanał dostaje pusty zbiór, więc zapala
    `test_kanal_w_drzewie_deklaruje_swoje_pomiary_wejsciowe` i bramka stoi zamknięta na kanale,
    którego kontrakt jest nie do odczytania. Gdyby czytnik zamiast tego zwrócił nazwę pola albo
    pierwszą linię, kanał przeszedłby bramkę z wejściem, którego nikt nie sprawdził.
    """
    korzen = _drzewo(tmp_path, status_0004="draft", kanal="atlas")
    kontrakt = korzen / "kio_tool" / "source" / "atlas" / "contract.yaml"
    kontrakt.write_text(
        "kanal: atlas\npomiary:\n  - 3a\n  - 23\nrole: [masowa]\n", encoding="utf-8"
    )

    assert pomiary_zadeklarowane(kontrakt) == frozenset(), (
        "czytnik wydobył coś z pisowni, której nie rozumie — pusty zbiór jest tu jedyną "
        "bezpieczną odpowiedzią, bo zamyka bramkę zamiast ją otwierać"
    )
    assert pomiary_wejsciowe_bramki(korzen) == {"atlas": frozenset()}


NUMERY_ADR_OCZEKIWANE = frozenset({"0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008"})
"""Numery, o których ten plik coś wie: trzy bramki, ADR-0003 (kształt `source/`), ADR-0005
(bramka per kanał, 2026-09-18 — zmienia kryterium, po którym ten plik chodzi) i ADR-0006
(faza 2, 2026-09-19) i ADR-0007 (polityka ponowień, 2026-09-19). Oba są `proposed`, więc żadnej
bramki jeszcze nie otwierają; numery są tu po to, żeby ich duplikat miał strażnika od pierwszego
dnia, a nie dopiero po przyjęciu — dwa ADR-y powstałe tego samego dnia od dwóch architektów
sięgnęły po ten sam numer i tylko ten strażnik by to złapał.

Lista jest wypisana, a nie wyliczona z katalogu, bo ADR skasowany przy renumeracji zniknąłby
razem ze swoim strażnikiem — a `test_numer_adr_nie_ma_dwoch_plikow` chodzący po samym globie
przechodziłby wtedy pusto.
"""


@pytest.mark.parametrize("numer", sorted(NUMERY_ADR_OCZEKIWANE))
def test_numer_adr_nie_ma_dwoch_plikow(numer: str) -> None:
    """Dwa pliki na jeden numer ADR-a to dwa statusy tej samej decyzji.

    Renumeracja ADR-ów już raz w tym projekcie przepisała plik szerzej, niż zamierzano
    (sesja 2026-09-17, zamiana CRLF na LF w całym dokumencie). Duplikat numeru jest tańszy do
    złapania tutaj niż przy czytaniu.

    ADR-0003 dopisany 2026-09-17: do tego dnia lista pomijała jedyny **przyjęty** ADR
    w projekcie, czyli ten, którego duplikat kosztowałby najwięcej.
    """
    trafienia = sorted(ADR.glob(f"{numer}_*.md"))
    assert len(trafienia) <= 1, f"numer ADR {numer} ma dwa pliki: {[p.name for p in trafienia]}"


def test_kazdy_plik_adr_w_katalogu_ma_swoj_numer_na_liscie() -> None:
    """Antypustka dla parametryzacji wyżej: ADR dopisany jutro ma trafić na listę sam.

    Bez tego numer spoza listy nie miałby strażnika duplikatów, a lista wyglądałaby tak samo
    kompletnie jak dziś.
    """
    w_katalogu = {plik.name.split("_")[0] for plik in ADR.glob("*.md")}

    assert w_katalogu, "katalog `docs/adr/` jest pusty — ADR-0003 i ADR-0004 zniknęły"
    assert w_katalogu <= NUMERY_ADR_OCZEKIWANE, (
        f"ADR-y {sorted(w_katalogu - NUMERY_ADR_OCZEKIWANE)} leżą w katalogu, a ten plik ich nie "
        "zna — dopisz numer do `NUMERY_ADR_OCZEKIWANE` razem z ADR-em, nie osobnym krokiem"
    )
