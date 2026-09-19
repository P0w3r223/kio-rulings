"""Segmentacja orzeczenia na sekcje — offsety w oryginale, nie kopia tekstu (ADR-0006 Z-5, Z-6).

Segmentuje **tekst wyekstrahowany z PDF-a** (`full_text` kanału `atlas`, Z-1), nie HTML. Kotwice
szuka się w widoku znormalizowanym z `clean.py`, a do bazy idą przedziały w oryginale.

Kotwice i ich częstość pochodzą z pomiaru, nie z jednego dokumentu (Z-2, doktryna 7.1). Każda
niesie w `KOTWICE` liczbę dokumentów, w których wystąpiła, i datę pomiaru — `docs/decisions.md`,
„Pomiar 5". Zmiana wzorca bez nowego pomiaru jest dokładnie tym, czego ta lista ma nie dopuścić.

Kolejność sekcji w orzeczeniu KIO jest stała i na niej stoi algorytm: nagłówek (sygnatura,
`WYROK`/`POSTANOWIENIE`, skład, strony) → sentencja od `orzeka:`/`postanawia:` → pouczenie
o skardze → uzasadnienie → ewentualne zdanie odrębne. Każda kotwica jest szukana **za** poprzednią,
więc słowo „uzasadnienie" w sentencji nie otwiera uzasadnienia. Tekst, którego nie da się
przypisać — przed pierwszą kotwicą, gdy nie ma w nim cech nagłówka, albo cały dokument bez kotwic —
trafia do sekcji `nieprzypisane` i jest **policzony w znakach** (Z-12), nigdy przemilczany.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .clean import Widok, normalizuj

RodzajSekcji = Literal[
    "naglowek", "sentencja", "pouczenie", "uzasadnienie", "zdanie_odrebne", "nieprzypisane"
]

RODZAJE_SEKCJI: tuple[RodzajSekcji, ...] = (
    "naglowek",
    "sentencja",
    "pouczenie",
    "uzasadnienie",
    "zdanie_odrebne",
    "nieprzypisane",
)


def _rozstrzelone(slowo: str) -> str:
    """Wzorzec słowa tolerujący spację między literami: `Uz as adnienie` (25,8 % dokumentów
    ma nagłówek rozstrzelony — pomiar 5). Spacja jest opcjonalna, nie wymagana."""
    return r" ?".join(re.escape(litera) for litera in slowo)


_NAGLOWEK_CECHY = re.compile(
    rf"(?i)sygn\.?\s*akt|^\s*(?:{_rozstrzelone('wyrok')}|{_rozstrzelone('postanowienie')})\s*$",
    re.MULTILINE,
)
"""Cechy nagłówka orzeczenia: `Sygn. akt` (95,3 %) albo wiersz `WYROK`/`POSTANOWIENIE` (100 %)."""

_SENTENCJA = re.compile(
    rf"(?i)\b(?:{_rozstrzelone('orzeka')}|{_rozstrzelone('postanawia')})\b\s*(?::|(?=1\s*\.))"
)
"""`orzeka:`/`postanawia:` — 340 z 341 dokumentów (99,7 %), pomiar 5, 2026-09-19. Postać bez
dwukropka, z punktem `1.` zaraz dalej, znaleziona 2026-09-19 w `KIO 3884/23` (`postanawia` jako
osobny wiersz); normalizacja dokleja do niego punkt pierwszy."""

_POUCZENIE = re.compile(r"(?i)przysługuje\s+skarga")
"""Pouczenie o skardze — 337 z 341 dokumentów (98,8 %), pomiar 5, 2026-09-19."""

_STOSOWNIE_DO = re.compile(r"(?i)\bstosownie\s+do\b")
"""Pełny początek zdania pouczenia: „Stosownie do art. 198a i 198b ustawy … na niniejszy wyrok
… przysługuje skarga"."""

_NA_ORZECZENIE = re.compile(r"(?i)\bna\s+(?:niniejsz\w+|orzeczenie)\b")
"""Początek pouczenia bez wstępu („Na orzeczenie – w terminie 14 dni…", rocznik 2024+)."""

_OKNO_POUCZENIA = 700
"""Ile znaków przed `przysługuje skarga` szukać `Stosownie do`. Przegląd złotego zbioru
(2026-09-19) znalazł cztery na siedemnaście dokumentów, w których odsyłacz do Dziennika Ustaw
(„Nr 219, poz. 1706 i Nr 223, poz. 1778") wypychał ten wstęp poza wcześniejsze okno 300 znaków
i pouczenie zaczynało się w pół zdania. Próg, nie pomiar."""

_UZASADNIENIE = re.compile(
    rf"(?im)^\s*{_rozstrzelone('uzasadnienie')}\s*(?::|\s+do\s+(?:wyroku|postanowienia)\b.*)?$",
)
"""`Uzasadnienie` jako osobny wiersz — 215 z 341 (63,0 %) przed normalizacją, pomiar 5."""

_UZASADNIENIE_ZA_PODPISEM = re.compile(
    rf"(?i)[.…]{{3}}\s*(?P<slowo>{_rozstrzelone('uzasadnienie')})\b"
)
"""Nagłówek wklejony przez ekstrakcję w wiersz podpisu: `Przewodniczący:……… uzasadnienie`
(`KIO 3700/23`, 2026-09-19) — bez tego uzasadnieniem stawał się dopiero nagłówek `UZASADNIENIE`
dwadzieścia tysięcy znaków dalej, a stanowisko odwołującego lądowało w pouczeniu."""

_SYGNATURA_STRONY = re.compile(r"(?im)^\s*sygn\.?\s*akt\b.*$")
"""Powtórzona sygnatura otwiera w postanowieniu stronę uzasadnienia bez nagłówka — tak wygląda
większość z 9 na 356 dokumentów bez wiersza `Uzasadnienie` (2026-09-19, 0 żądań)."""

_PODPIS = re.compile(r"(?im)^\s*przewodnicząc\w*\s*:.*$")
"""Podpis pod sentencją. W orzeczeniach z 2012 r. uzasadnienie zaczyna się zaraz pod nim, bez
nagłówka i bez powtórzonej sygnatury (`KIO 1004/12`, próbka rocznikowa 2026-09-19)."""

_ZA_PODPISEM = re.compile(r"(?:\n[\s.…·\d]*(?=\n))*\n")
"""Wiersze z samych kropek, wielokropków i numerów stron pod podpisem — do przeskoczenia."""

_MIN_UZASADNIENIE = 200
"""Ile znaków musi stać za powtórzoną sygnaturą, żeby była początkiem uzasadnienia, a nie
stopką strony z podpisem — próg, nie pomiar."""

_ZDANIE_ODREBNE = re.compile(rf"(?im)^\s*{_rozstrzelone('zdanie')} ?{_rozstrzelone('odrębne')}")


@dataclass(frozen=True)
class Sekcja:
    """Jedna sekcja: rodzaj i przedział `[start, koniec)` w **oryginale**."""

    porzadek: int
    rodzaj: RodzajSekcji
    start: int
    koniec: int

    @property
    def dlugosc(self) -> int:
        return self.koniec - self.start


def segmentuj(oryginal: str) -> tuple[Sekcja, ...]:
    """Sekcje dokumentu w kolejności; pokrywają oryginał od pierwszego do ostatniego znaku
    widoku bez luk i bez nakładania się. Pusty tekst daje krotkę pustą."""
    widok = normalizuj(oryginal)
    if not widok.tekst:
        return ()
    granice = _granice(widok.tekst)
    sekcje: list[Sekcja] = []
    for porzadek, (rodzaj, start, koniec) in enumerate(granice):
        a, b = widok.w_oryginale(start, koniec)
        sekcje.append(Sekcja(porzadek=porzadek, rodzaj=rodzaj, start=a, koniec=b))
    return tuple(sekcje)


def _granice(tekst: str) -> list[tuple[RodzajSekcji, int, int]]:
    """Przedziały sekcji w widoku — kotwica każdej następnej szukana za poprzednią."""
    punkty: list[tuple[RodzajSekcji, int]] = []
    kursor = 0
    sentencja = _SENTENCJA.search(tekst)
    if sentencja is not None:
        # Od samej kotwicy, nie od początku wiersza: normalizacja skleja „po rozpoznaniu
        # na posiedzeniu … postanawia:" w jeden wiersz, a wszystko przed kotwicą to nagłówek.
        punkty.append(("sentencja", sentencja.start()))
        kursor = sentencja.end()
    pouczenie = _pouczenie(tekst, kursor)
    if pouczenie is not None:
        punkty.append(("pouczenie", pouczenie))
        kursor = pouczenie
    uzasadnienie = _poczatek_uzasadnienia(tekst, kursor)
    if uzasadnienie is not None:
        punkty.append(("uzasadnienie", uzasadnienie))
        kursor = uzasadnienie
    zdanie = _ZDANIE_ODREBNE.search(tekst, kursor)
    if zdanie is not None:
        punkty.append(("zdanie_odrebne", zdanie.start()))
    if not punkty:
        return [("nieprzypisane", 0, len(tekst))]
    wynik: list[tuple[RodzajSekcji, int, int]] = []
    pierwszy = punkty[0][1]
    if pierwszy > 0:
        glowa = tekst[:pierwszy]
        rodzaj: RodzajSekcji = "naglowek" if _NAGLOWEK_CECHY.search(glowa) else "nieprzypisane"
        wynik.append((rodzaj, 0, pierwszy))
    for numer, (rodzaj_punktu, start) in enumerate(punkty):
        koniec = punkty[numer + 1][1] if numer + 1 < len(punkty) else len(tekst)
        if koniec > start:
            wynik.append((rodzaj_punktu, start, koniec))
    return wynik


def _poczatek_uzasadnienia(tekst: str, od: int) -> int | None:
    """Trzy drogi, w kolejności pewności: nagłówek `Uzasadnienie`, powtórzona sygnatura otwierająca
    stronę uzasadnienia, podpis przewodniczącego pod sentencją. Dwie ostatnie liczą się tylko,
    gdy za nimi stoi co najmniej `_MIN_UZASADNIENIE` znaków."""
    kandydaci: list[int] = []
    if (naglowek := _UZASADNIENIE.search(tekst, od)) is not None:
        kandydaci.append(naglowek.start())
    if (w_podpisie := _UZASADNIENIE_ZA_PODPISEM.search(tekst, od)) is not None:
        kandydaci.append(w_podpisie.start("slowo"))
    if kandydaci:
        return min(kandydaci)
    sygnatura = _SYGNATURA_STRONY.search(tekst, od)
    if sygnatura is not None and len(tekst) - sygnatura.end() >= _MIN_UZASADNIENIE:
        return sygnatura.start()
    podpis = _PODPIS.search(tekst, od)
    if podpis is None:
        return None
    dalej = _ZA_PODPISEM.match(tekst, podpis.end())
    start = dalej.end() if dalej is not None else podpis.end()
    return start if len(tekst) - start >= _MIN_UZASADNIENIE else None


def _pouczenie(tekst: str, od: int) -> int | None:
    """Początek zdania pouczenia, w kolejności pewności: najbliższe `Stosownie do` w oknie
    przed `przysługuje skarga`, najbliższe `na niniejszy …`/`na orzeczenie`, początek wiersza.

    Najbliższe, nie pierwsze: pouczenie jest jedno, a wcześniejsze „stosownie do" potrafi stać
    w sentencji. Okno nie jest ograniczone wierszem, bo wstęp z długim odsyłaczem do Dziennika
    Ustaw łamie się na kilka wierszy zakończonych nawiasem albo kropką."""
    trafienie = _POUCZENIE.search(tekst, od)
    if trafienie is None:
        return None
    okno = max(od, trafienie.start() - _OKNO_POUCZENIA)
    for wzor in (_STOSOWNIE_DO, _NA_ORZECZENIE):
        kandydaci = list(wzor.finditer(tekst, okno, trafienie.start()))
        if kandydaci:
            return kandydaci[-1].start()
    return max(_poczatek_wiersza(tekst, trafienie.start()), od)


def _poczatek_wiersza(tekst: str, pozycja: int) -> int:
    return tekst.rfind("\n", 0, pozycja) + 1


def pokrycie(sekcje: tuple[Sekcja, ...]) -> dict[RodzajSekcji, int]:
    """Znaki per rodzaj sekcji — wejście raportu pokrycia (Z-12)."""
    wynik: dict[RodzajSekcji, int] = dict.fromkeys(RODZAJE_SEKCJI, 0)
    for sekcja in sekcje:
        wynik[sekcja.rodzaj] += sekcja.dlugosc
    return wynik


__all__ = ["RODZAJE_SEKCJI", "RodzajSekcji", "Sekcja", "Widok", "pokrycie", "segmentuj"]
