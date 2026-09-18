"""Ocena kształtu odpowiedzi — reguła 17 jako część pakietu.

Reguła 17 wymaga od adaptera `SourceContractBroken` przy „status zgodny, kształt niezgodny",
i ma za sobą datę: między majem a lipcem 2026 UZP przeniósł każdy punkt końcowy wyszukiwarki,
a cudzy kolektor przez około dwa miesiące zwracał `total=0` **ze statusem 200** zamiast błędu.
Pusta lista jest poprawnym wynikiem zapytania, więc nic tego nie zauważyło.

Do 2026-09-18 ta maszyneria mieszkała w `scripts/ksztalty.py` obok oczekiwań sondy fazy 0,
z uzasadnieniem „ocena kształtu jest częścią sondy, a nie narzędzia". Od tego dnia jest
częścią pakietu i to jest rozstrzygnięcie, nie przeprowadzka: reguła 17 wymaga oceny kształtu
**od adaptera**, więc adapter `source/<kanał>/channel.py` ma się o co oprzeć bez importu ze
`scripts/`. Podział biegnie po pojęciu — tu stoi **jak** ocenić bajty wobec oczekiwania;
**konkretne oczekiwania kanału** (fragmenty HTML, nazwa listy, pola rekordu) idą do
`contract.yaml` tego kanału, a do bramki fazy 0 zostają jako instancje w `scripts/ksztalty.py`.

Sonda nie jest adapterem i nie rzuca — ale musi widzieć to samo, bo inaczej strona bot-checka
z kodem 200 wypisze się jako `200, 28 064 B` i będzie wyglądała na sukces. To jest zasada 7.2
(„cisza jest usterką") zastosowana do jedynego miejsca, które dziś cokolwiek wysyła.

Dwie własności tego modułu są rozstrzygnięciami, nie szczegółami:

1. **Ocena niesie uwagę także przy zgodności.** Ocena, która przy powodzeniu milczy, mówi
   operatorowi tylko „nie zapaliło się". Przy pomiarach 2a i 3a pytanie brzmi „co właściwie
   przyszło", więc nazwy pól pierwszego rekordu **są** wynikiem pomiaru.
2. **Każde oczekiwanie niesie swoje źródło.** Kontrakt `GetResults` stoi dziś na dwóch cudzych
   kolektorach, a struktura `Details` na własnym odczycie z 2026-09-14. Niezgodność pierwszego
   znaczy „albo kontrakt się zmienił, albo nigdy nie był taki"; niezgodność drugiego znaczy
   „serwis zmienił się od dnia, w którym patrzyliśmy". Zasada 7.1 mówi, że tej różnicy nie
   wolno zgubić — więc stoi w typie, a nie w komentarzu.

Ten moduł nie wysyła żądań i nie dotyka dysku: dostaje bajty, zwraca ocenę.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from .config import mask_tokens
from .safetext import strip_control

DLUGOSC_PODGLADU = 160
"""Ile znaków odpowiedzi wolno pokazać przy niezgodnym kształcie.

Podgląd jest po to, żeby operator poznał stronę bot-checka po treści, a nie po samym
rozmiarze. Idzie przez `strip_control`, bo to jest obcy napis na drodze do terminala.
"""

MAKS_POL_W_UWADZE = 14
"""Ile nazw pól rekordu pokazać. Nazwy — nigdy wartości: treść orzeczenia nie ma po co
trafiać na ekran, a do rozstrzygnięcia „czy jest pełny tekst" wystarczy nazwa pola."""


@dataclass(frozen=True)
class OcenaKsztaltu:
    """Wynik oceny. `uwaga` jest wypełniona **zawsze**, także przy zgodności.

    Maskowanie sekretów dzieje się **przy budowie obiektu**, a nie w każdym miejscu, które
    uwagę składa, i to jest poprawka z przeglądu 2026-09-17. `uwaga` niesie fragment cudzej
    odpowiedzi, a odpowiedź błędu potrafi odbić nagłówek żądania — przy Atlasie razem
    z `X-Api-Key`. Stamtąd fragment idzie na ekran i do `podsumowanie_*.json`, a udokumentowaną
    ścieżką jest „przepisz wynik z ekranu do `docs/decisions.md`", czyli do pliku w historii
    repozytorium. `strip_control` sam nie wystarcza i mówi to wprost `tests/test_boundaries.py`
    przy definicji neutralizatorów: usuwa znaki sterujące, ale **nie maskuje sekretu**.

    Kolejność `strip_control` → `mask_tokens` jest już rozstrzygnięta w `richtext.safe`
    i przeniesiona tu razem z powodem: klucz z wstrzykniętym znakiem sterującym po samym
    maskowaniu przechodzi nierozpoznany, bo nie równa się zarejestrowanej wartości.
    """

    zgodny: bool
    uwaga: str
    przejsciowa: bool = False
    """Niezgodność, która wygląda na urwane łącze, nie na zmianę u dostawcy.

    Odpowiedź 200 z JSON-em uciętym w połowie (albo pustym ciałem) jest tym samym zdarzeniem, co
    `RemoteProtocolError` z `httpx` — sieć padła w trakcie odbioru, tylko serwer zdążył zamknąć
    strumień „poprawnie". Tester 2026-09-18 zmierzył, że jedna droga kończyła przebieg jako
    wznawialny, a druga jako trwale złamany kontrakt (kod 1, status `blad`). Pole niesie tę
    różnicę do adaptera, który rozstrzyga o wyjątku; ocena zgodna ma je zawsze `False`.
    """

    def __post_init__(self) -> None:
        # `strip_control` **przed** `mask_tokens` i w tym samym miejscu, w którym maskowanie —
        # przegląd kodu 2026-09-18 zmierzył, że docstring wyżej deklarował tę kolejność, a kod
        # robił tylko drugą połowę: `strip_control` stał wyłącznie w `podglad()`, więc nazwa pola
        # JSON z wstrzykniętym znakiem zerowej szerokości niosła sekret nierozpoznany, a `\x1b[2J`
        # w nazwie pola szedł na ekran i do podsumowania.
        object.__setattr__(self, "uwaga", mask_tokens(strip_control(self.uwaga)))


@dataclass(frozen=True)
class Ksztalt:
    """Oczekiwanie wobec odpowiedzi razem ze źródłem tego oczekiwania."""

    opis: str
    zrodlo: str
    ocen: Callable[[bytes], OcenaKsztaltu]


def podglad(tresc: bytes) -> str:
    """Początek odpowiedzi jako jedna linia bezpieczna dla terminala."""
    tekst = strip_control(tresc[: DLUGOSC_PODGLADU * 4].decode("utf-8", errors="replace"))
    return " ".join(tekst.split())[:DLUGOSC_PODGLADU]


def wyglada_na_urwana(tresc: bytes) -> bool:
    """Czy ciało, które nie jest JSON-em, zaczyna się jak JSON.

    Strona bot-checka zaczyna się od `<`, a odpowiedź o zmienionej strukturze **jest** JSON-em
    — obie zostają złamanym kontraktem. Ciało zaczynające się od `{` lub `[`, którego nie da się
    odczytać, to JSON urwany w trakcie odbioru. Ucięty bajt wielobajtowego znaku UTF-8 daje
    `UnicodeDecodeError`, nie `JSONDecodeError`, dlatego rozstrzyga początek bajtów, nie rodzaj
    wyjątku.

    Ciało puste **nie** jest przejściowe: urwanie przed pierwszym bajtem wykrywa ramkowanie HTTP
    (`Content-Length`, chunked) i wychodzi z `httpx` jako `RemoteProtocolError`, a puste 200 zza
    proxy znaczy zwykle przeniesiony punkt końcowy — czyli kontrakt, nie łącze (przegląd kodu
    2026-09-18). Ta sama uwaga dotyczy ciała pełnego co do długości: heurystyka po pierwszym
    bajcie kosztuje najwyżej jedno ręczne `wznow`, które wywróci się w tym samym miejscu, a błąd
    w drugą stronę kosztowałby punkt kontrolny — dlatego wątpliwość idzie w stronę wznawialności.
    """
    poczatek = tresc.lstrip()[:1]
    return poczatek in (b"{", b"[")


def _nie_json(tresc: bytes, blad: Exception) -> OcenaKsztaltu:
    return OcenaKsztaltu(
        zgodny=False,
        uwaga=f"nie jest JSON-em ({type(blad).__name__}); początek: {podglad(tresc)}",
        przejsciowa=wyglada_na_urwana(tresc),
    )


def html_z_fragmentami(*fragmenty: str) -> Callable[[bytes], OcenaKsztaltu]:
    """Kształt HTML jako obecność znaczników kontraktu.

    Porównanie idzie po bajtach ASCII i dlatego wszystkie fragmenty są ASCII: `bytes.lower()`
    nie zna polskich znaków, a dopasowanie wrażliwe na wielkość liter zapalałoby się na samej
    zmianie pisowni klasy CSS. Gdyby trzeba było szukać napisu z ogonkami, to jest moment na
    parser HTML, a nie na drugą pisownię tego samego porównania.

    **Niezmiennik jest sprawdzany przy budowie oczekiwania, a nie przy ocenie odpowiedzi**
    (poprawka 2026-09-17). Do tej pory był tylko zdaniem w tym docstringu, a fragment z ogonkiem
    wywracał się `UnicodeEncodeError`-em dopiero w `ocen` — czyli **po** wysłaniu żądania
    i przed `Kronika.zanotuj`, więc ślad po żądaniu, które już poszło do cudzego serwisu,
    ginął. Dokładnie ten kształt awarii projekt zamknął raz w tej sesji przy zapisie do
    dziennika; tu wracał tylnymi drzwiami. Teraz zła literówka w oczekiwaniu wywraca **import**
    sondy, czyli zanim cokolwiek wyjdzie na zewnątrz.
    """
    if not fragmenty or any(not f for f in fragmenty):
        # Oczekiwanie bez treści zgadza się z **każdą** odpowiedzią (`b"" in cokolwiek`), więc
        # `Wynik.odmowa` się nie zapala i nieznany POST idzie dalej po kontroli, która niczego
        # nie sprawdziła. Cisza jest tu groźniejsza niż przy ogonku: ogonek krzyczał wyjątkiem,
        # a pusty fragment wypisywał „kształt OK" i wpisywał „zgodny" do dziennika. Droga jest
        # krótka — zawężanie oczekiwania po fałszywym alarmie o krok za daleko albo literówka
        # `html_z_fragmentami("Uzasadnienie", "")` (znalezione przeglądem testów 2026-09-17).
        raise ValueError(
            "oczekiwanie kształtu musi nieść co najmniej jeden niepusty fragment; "
            f"dostało {list(fragmenty)}. Pusty fragment zgadza się z każdą odpowiedzią, "
            "więc oczekiwanie bez treści jest ciszą podpisaną słowem „zgodny”."
        )
    z_ogonkiem = [f for f in fragmenty if not f.isascii()]
    if z_ogonkiem:
        raise ValueError(
            f"fragmenty kształtu muszą być ASCII, a te nie są: {z_ogonkiem}. "
            "`bytes.lower()` nie zna polskich znaków, więc porównanie po ogonkach zależałoby "
            "od kodowania strony, którego nikt w tym projekcie jeszcze nie zmierzył."
        )

    def ocen(tresc: bytes) -> OcenaKsztaltu:
        male = tresc.lower()
        brakuje = [f for f in fragmenty if f.lower().encode("ascii") not in male]
        if brakuje:
            return OcenaKsztaltu(
                zgodny=False,
                uwaga=f"brak {', '.join(repr(f) for f in brakuje)}; początek: {podglad(tresc)}",
            )
        return OcenaKsztaltu(zgodny=True, uwaga=f"obecne: {', '.join(fragmenty)}")

    return ocen


def _pierwsza_lista(dane: object) -> tuple[str, list[object]] | None:
    """Lista rekordów: sam dokument, jeśli jest listą, albo pierwsza lista w słowniku."""
    if isinstance(dane, list):
        return ("(korzeń)", dane)
    if isinstance(dane, dict):
        for klucz, wartosc in dane.items():
            if isinstance(wartosc, list):
                return (str(klucz), wartosc)
    return None


def _lista_rekordow(dane: object, oczekiwany_klucz: str | None) -> tuple[str, list[object]] | None:
    """Najpierw lista wskazana przez kontrakt, dopiero potem pierwsza napotkana.

    Poprawka z 2026-09-17, znaleziona przez test, nie przez lekturę. Pierwsza wersja brała
    **pierwszą listę w kolejności kluczy**, a odpowiedź Dump API SAOS niesie obok `items`
    także `links` — też listę. Werdykt o kształcie zależał więc od tego, w jakiej kolejności
    cudzy serwis serializuje słownik, czyli od czegoś, co nie jest częścią żadnego kontraktu.

    Waga bierze się z tego, co sonda robi z tą oceną: kształt niezgodny wchodzi do
    `Wynik.odmowa`, więc fałszywy alarm wysyła dodatkowe żądanie kontrolne, a przy UZP
    zatrzymuje całą grupę pomiarów. Pomiar, który nie padł, wyglądałby wtedy tak samo jak
    pomiar zablokowany przez serwis — a to są dwa różne zdarzenia i jeden wpis w dzienniku.

    Gdy kontrakt nazwę podaje, a pod tą nazwą nie ma listy, szukanie dalej jest celowe:
    **niezgodność ma być opisana tym, co przyszło**, a nie samym „nie znaleziono".
    """
    if isinstance(dane, dict) and oczekiwany_klucz is not None:
        wskazana = dane.get(oczekiwany_klucz)
        if isinstance(wskazana, list):
            return (oczekiwany_klucz, wskazana)
    return _pierwsza_lista(dane)


def json_z_rekordami(
    oczekiwany_klucz: str | None = None, *, pusta_dozwolona: bool = False
) -> Callable[[bytes], OcenaKsztaltu]:
    """Kształt JSON jako niepusta lista rekordów, z wypisaniem pól pierwszego z nich.

    `oczekiwany_klucz` podany znaczy, że kontrakt wymienia nazwę listy. Lista pod **inną**
    nazwą jest wtedy niezgodnością, a nie drobiazgiem: to samo zdarzenie, które u cudzego
    kolektora dało dwa miesiące cichych zer, zaczyna się od przeniesienia pola.

    `pusta_dozwolona` rozdziela dwóch wywołujących o różnych pytaniach (etap III, 2026-09-18).
    Sonda pyta „co przyszło" na liście bez filtra, więc pusta lista jest tam podejrzana — tak
    właśnie wyglądały dwa miesiące `total=0` u cudzego kolektora. Adapter pyta o **zakres dat**,
    a zakres bez orzeczeń jest poprawnym wynikiem zapytania, nie złamanym kontraktem: `has_more`
    zgasło, lista jest pusta, przebieg kończy się zerem dokumentów i mówi o tym. Pusta lista pod
    **innym** kluczem pozostaje niezgodnością w obu trybach — o kluczu rozstrzyga kontrakt.
    """

    def ocen(tresc: bytes) -> OcenaKsztaltu:
        try:
            dane = json.loads(tresc)
        except (json.JSONDecodeError, UnicodeDecodeError) as blad:
            return _nie_json(tresc, blad)
        znaleziona = _lista_rekordow(dane, oczekiwany_klucz)
        if znaleziona is None:
            korzen = sorted(map(str, dane))[:MAKS_POL_W_UWADZE] if isinstance(dane, dict) else []
            return OcenaKsztaltu(
                zgodny=False,
                uwaga=f"JSON bez listy rekordów; korzeń: {korzen or type(dane).__name__}",
            )
        klucz, lista = znaleziona
        if not lista:
            zgodna_pusta = pusta_dozwolona and (
                oczekiwany_klucz is None or klucz == oczekiwany_klucz
            )
            return OcenaKsztaltu(
                zgodny=zgodna_pusta,
                uwaga=f"lista `{klucz}` jest pusta"
                + (" — dozwolone: zakres bez rekordów" if zgodna_pusta else ""),
            )
        pierwszy = lista[0]
        pola = (
            ", ".join(sorted(map(str, pierwszy))[:MAKS_POL_W_UWADZE])
            if isinstance(pierwszy, dict)
            else type(pierwszy).__name__
        )
        zgodny = oczekiwany_klucz is None or klucz == oczekiwany_klucz
        rozjazd = (
            ""
            if zgodny
            else f" — kontrakt mówi o kluczu `{oczekiwany_klucz}`, a lista jest pod `{klucz}`"
        )
        return OcenaKsztaltu(
            zgodny=zgodny,
            uwaga=f"lista `{klucz}`: {len(lista)} rekordów; pola pierwszego: {pola}{rozjazd}",
        )

    return ocen


def _rekord_z_polami(dane: object, pola: tuple[str, ...]) -> tuple[str, dict[str, object]] | None:
    """Słownik niosący wszystkie wymagane pola: sam korzeń albo pierwszy słownik potomny.

    Zagnieżdżenie jest dopuszczone, bo dokumentacja Atlasu (odczyt 2026-09-18) nie pokazuje
    przykładowej odpowiedzi `GET /api/kio/{slug}` — rekord opakowany w `data` i rekord goły
    to ten sam kontrakt zapisany dwiema pisowniami. Gdzie rekord leżał, mówi uwaga oceny,
    więc opakowanie **jest** wynikiem pomiaru, a nie szczegółem, który ocena przemilczała.
    """
    if not isinstance(dane, dict):
        return None
    if all(pole in dane for pole in pola):
        return ("(korzeń)", dane)
    for klucz, wartosc in dane.items():
        if isinstance(wartosc, dict) and all(pole in wartosc for pole in pola):
            return (f"pod `{klucz}`", wartosc)
    return None


def _najdluzsze_pole_tekstowe(rekord: dict[str, object]) -> tuple[str, int] | None:
    """Nazwa i długość najdłuższego pola napisowego — nigdy jego wartość."""
    napisy = [
        (str(klucz), len(wartosc)) for klucz, wartosc in rekord.items() if isinstance(wartosc, str)
    ]
    if not napisy:
        return None
    return max(napisy, key=lambda para: para[1])


def json_ze_slownikiem(*pola_wymagane: str) -> Callable[[bytes], OcenaKsztaltu]:
    """Kształt JSON jako jeden rekord z wymaganymi polami — oczekiwanie dla punktu dokumentu.

    Powstało 2026-09-18 razem z drugim żądaniem pomiaru 3a. Pomiar pytał „czy pośrednik
    zwraca pełny tekst", a wołał wyłącznie listę — punkt, który z definicji niesie skróty.
    Odpowiedź daje `GET /api/kio/{slug}`, a odpowiedzią jest **nazwa i długość najdłuższego
    pola tekstowego** rekordu: nazwy pola z treścią nikt tu nie odczytał, więc ocena ma je
    znaleźć i nazwać, a nie zakładać.

    Ten sam niezmiennik co w `html_z_fragmentami`: oczekiwanie bez pól zgadza się z każdym
    słownikiem, więc jest odrzucane przy budowie, nie przy ocenie.
    """
    if not pola_wymagane or any(not pole for pole in pola_wymagane):
        raise ValueError(
            "oczekiwanie rekordu musi nieść co najmniej jedno niepuste pole; "
            f"dostało {list(pola_wymagane)}. Rekord bez wymaganych pól zgadza się z każdym "
            "słownikiem, więc oczekiwanie bez treści jest ciszą podpisaną słowem „zgodny”."
        )

    def ocen(tresc: bytes) -> OcenaKsztaltu:
        try:
            dane = json.loads(tresc)
        except (json.JSONDecodeError, UnicodeDecodeError) as blad:
            return _nie_json(tresc, blad)
        znaleziony = _rekord_z_polami(dane, pola_wymagane)
        if znaleziony is None:
            if isinstance(dane, dict):
                brakuje = [pole for pole in pola_wymagane if pole not in dane]
                korzen = sorted(map(str, dane))[:MAKS_POL_W_UWADZE]
                return OcenaKsztaltu(
                    zgodny=False, uwaga=f"rekord bez pól {brakuje}; pola korzenia: {korzen}"
                )
            return OcenaKsztaltu(
                zgodny=False, uwaga=f"JSON nie jest rekordem; korzeń: {type(dane).__name__}"
            )
        gdzie, rekord = znaleziony
        pola = ", ".join(sorted(map(str, rekord))[:MAKS_POL_W_UWADZE])
        najdluzsze = _najdluzsze_pole_tekstowe(rekord)
        opis_tresci = (
            "brak pól tekstowych"
            if najdluzsze is None
            else f"najdłuższe pole tekstowe: `{najdluzsze[0]}` ({najdluzsze[1]} znaków)"
        )
        return OcenaKsztaltu(
            zgodny=True, uwaga=f"rekord {gdzie}: {len(rekord)} pól ({pola}); {opis_tresci}"
        )

    return ocen
