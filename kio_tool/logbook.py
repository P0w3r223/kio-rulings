"""Ślad przebiegu: wynik jednego żądania, wiersz na ekran, wiersz do dziennika, podsumowanie.

Nazwa jest zarezerwowana w architekturze 4.2 („`logbook.py` (dziennik)"). Do 2026-09-18 ten
szew mieszkał w `scripts/sonda.py` pod roboczą nazwą „ślad przebiegu" — z zapowiedzią, że
przeniesie się do pakietu razem z kolumnami `requests_log`, gdy sonda zamieni się w adapter.
Przeniósł się wcześniej, bo dług 1 428 linii w jednym pliku rósł z każdym pomiarem, a szew był
gotowy: `Wynik`, `Kronika`, zapis surowej odpowiedzi, wiersz dziennika i podsumowanie mówią,
**co zostaje po żądaniu** — niezależnie od tego, kto je wysłał.

Dwie własności tego modułu, obie z ceną zapisaną w docstringach niżej:

- **Ścieżki nie są globalami modułu.** `Kronika` niesie `dziennik` i `katalog_wyjscia` jako
  pola, a `dopisz_dziennik`, `zapisz_surowe` i `zapisz_podsumowanie` biorą ścieżkę jawnie.
  Środowisko sondy (`scripts/zadanie.py`) składa je w jednym miejscu, a test podstawia je tam,
  a nie w każdym module, który akurat pisze na dysk.
- **Druk jest wstrzykiwalny.** `Kronika.wypisz` domyślnie drukuje `print`-em z `flush=True`;
  ten moduł nie zna `rich` (reguła 7 — biblioteka ekranu mieszka w `console.py`
  i `richtext.py`) ani nie buduje klienta HTTP (reguła 11). Dostaje wynik, zostawia ślad.

Reguła zgody (architektura 4.1, audyt 13.2 pkt 4) mówi: pojedynczy odczyt diagnostyczny nie
wymaga zgody właściciela, ale **zawsze zostawia wpis w dzienniku**. Dopóki nie ma bazy,
dziennikiem jest plik markdown z kolumnami `requests_log` (model danych 4.4); adres idzie przez
`mask_tokens`, bo `requests_log` trzyma `url_redacted`, a nie `url`.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .clock import Clock, utc_iso
from .config import mask_tokens
from .safetext import strip_control

KODY_ODMOWY = frozenset({401, 402, 403, 407, 429})
"""Kody, przy których serwis mówi „nie tobie" albo „nie teraz".

Nie ma tu 5xx: awaria po stronie serwisu jest czym innym niż odmowa i prowadzi do innego
wniosku — pierwsze powtarza się za jakiś czas, drugie wymaga pisma albo klucza.
"""


# --- wynik jednego żądania ----------------------------------------------------------------


@dataclass(frozen=True)
class Wynik:
    """Jedno żądanie sondy i to, co z niego wiadomo."""

    nazwa: str
    metoda: str
    adres: str
    status: int | None
    bajtow: int
    czas_s: float
    plik: Path | None
    sha256: str | None = None
    ksztalt_zgodny: bool | None = None
    ksztalt_uwaga: str = ""
    ksztalt_zrodlo: str = ""
    uwaga: str = ""
    retry_after_s: float | None = None
    """Prośba serwisu z nagłówka `Retry-After` przy tym żądaniu, w sekundach — do dziennika,
    żeby przeżyła proces (znalezisko testera 2026-09-18: wznowienie po 429 odczekiwało własną
    blokadę limitera zamiast tej, o którą serwis prosił)."""
    wyslane: bool = True
    """Czy to żądanie opuściło proces.

    Pole jawne, a nie rozpoznawanie po napisie w `adres`. Powód jest rachunkowy: konwencja
    `decisions.md` każe zapisać „zmierzone {data}, **N żądań**", a ADR-0004 czyni z tej liczby
    warunek zamknięcia bramki. Wiersz za pomiar, który nie poszedł, zawyżałby N przy liczeniu
    z ekranu albo z dziennika — czyli liczba pilnowana przez zasadę 7.1 byłaby fałszywa
    w dokumencie, który tę zasadę wprowadza.
    """

    def __post_init__(self) -> None:
        """Maskowanie sekretów przy budowie, tak samo jak w `ksztalt.OcenaKsztaltu`.

        `uwaga` niesie treść obcą i to nie jest teoria: `przekierowanie → {Location}` bierze
        adres z cudzego nagłówka (a czytanie `Location` z `/Home/Move` jest tu decyzją
        operacyjną, nie przypadkiem), a `{type(blad).__name__}: {blad}` bierze komunikat
        `httpx`, który potrafi wpisać w siebie adres żądania. Stamtąd napis idzie na ekran
        i do `podsumowanie_*.json`, czyli obok pliku, który operator przepisuje do
        `docs/decisions.md`.

        Do przeglądu 2026-09-17 maskowany był wyłącznie `adres`, i to dopiero przy zapisie —
        `uwaga` nie była maskowana nigdzie. Maskowanie przy budowie obiektu zamyka **oba**
        ujścia naraz i nie wymaga pamiętania o nim w trzecim, które powstanie jutro.
        """
        # `strip_control` przed `mask_tokens`, jak w `richtext.safe` i `ksztalt.OcenaKsztaltu`
        # (przegląd kodu 2026-09-18): `uwaga` idzie stąd przez `Kronika.zanotuj` gołym `print`,
        # a niesie `Location` z cudzego nagłówka i komunikat `httpx` — `\x1b[2J` w cudzym adresie
        # czyściłby operatorowi ekran razem z rachunkiem żądań, a sekret rozbity znakiem zerowej
        # szerokości przechodziłby maskowanie nierozpoznany.
        object.__setattr__(self, "uwaga", mask_tokens(strip_control(self.uwaga)))

    @property
    def odmowa(self) -> bool:
        """Czy to żądanie skończyło się odmową albo odpowiedzią nie do poznania.

        Kształt niezgodny przy statusie 200 liczy się tutaj, bo właśnie tak wygląda strona
        bot-checka — i właśnie dlatego pytanie „czy odmawia punkt, czy host" ma wtedy sens.
        """
        return self.status is None or self.status in KODY_ODMOWY or self.ksztalt_zgodny is False

    @property
    def odmowa_serwisu(self) -> bool:
        """Węższe pytanie: czy **serwis** odmówił, bez wciągania niezgodnego kształtu.

        Rozróżnienie jest potrzebne w SAOS i jest tam wyjaśnione: niezgodny kształt przy
        dwóch sprzecznych pisowniach parametru dat jest **wynikiem pomiaru**, a nie odmową,
        więc nie ma prawa przerwać drugiej próby.
        """
        return self.status is None or self.status in KODY_ODMOWY

    def wiersz(self) -> str:
        if not self.wyslane:
            return (
                f"{self.nazwa:26} {self.metoda:5} {'—':>6}  (niewysłane)\n{'':26} └─ {self.uwaga}"
            )
        status = "BŁĄD" if self.status is None else str(self.status)
        plik = self.plik.name if self.plik else "—"
        skrot = self.sha256[:12] if self.sha256 else "—"
        linie = [
            f"{self.nazwa:26} {self.metoda:5} {status:>6} "
            f"{self.bajtow:>9} B  {self.czas_s:5.2f}s  {skrot}  {plik}"
        ]
        if self.ksztalt_zgodny is not None:
            znacznik = "kształt OK" if self.ksztalt_zgodny else "KSZTAŁT NIEZGODNY"
            linie.append(f"{'':26} └─ {znacznik}: {self.ksztalt_uwaga}")
            linie.append(f"{'':26}    oczekiwanie z: {self.ksztalt_zrodlo}")
        if self.uwaga:
            linie.append(f"{'':26} └─ {self.uwaga}")
        return "\n".join(linie)


def niewyslany(nazwa: str, metoda: str, powod: str) -> Wynik:
    """Pomiar, który nie poszedł, zapisany jawnie — bo zniknięcie z listy jest ciszą.

    Dwie drogi zatrzymania grupy zachowywały się przeciwnie: zawiedziona kontrola zostawiała
    jawny wpis, a odmowa pierwszego POST-u kasowała kolejny pomiar bez śladu. Czytający po
    tygodniu nie odróżniłby „pomiar 16 nie poszedł, bo 4b dostał 429" od „pomiaru 16 nigdy
    w tej wersji sondy nie było" (przegląd kodu 2026-09-17).
    """
    return Wynik(
        nazwa=nazwa,
        metoda=metoda,
        adres="(niewysłane)",
        status=None,
        bajtow=0,
        czas_s=0.0,
        plik=None,
        uwaga=powod,
        wyslane=False,
    )


# --- kronika: ślad w chwili powstania wyniku -----------------------------------------------


def _drukuj(tekst: str) -> None:
    """Domyślny druk kroniki: `print` z `flush=True`.

    `flush`, bo bez niego wiersz utyka w buforze przy przekierowaniu wyjścia do pliku — czyli
    cisza dokładnie w klasie, która powstała po to, żeby operator widział przebieg w trakcie.
    Funkcja, a nie `functools.partial`, bo pole `Kronika.wypisz` ma czytelny podpis
    `Callable[[str], None]` i test podstawia w to miejsce własną listę.
    """
    print(tekst, flush=True)


@dataclass(frozen=True)
class Kronika:
    """Ślad przebiegu: wiersz na ekran i wiersz do dziennika **w chwili powstania wyniku**.

    Do przeglądu 2026-09-17 jedno i drugie działo się dopiero po powrocie z całego pomiaru.
    Skutek był podwójny i oba końce łamały doktrynę: operator nie widział nic przez cały
    przebieg sieciowy (zasada 7.2), a każdy wyjątek w środku — `LimiterStalledError`,
    `UntrustedLinkError`, pełny dysk w `zapisz_surowe`, `KeyboardInterrupt` w czasie blokady
    po 429 — kasował zapis **wszystkich** żądań, które już poszły do cudzego serwisu. Reguła
    zgody mówi, że odczyt diagnostyczny zawsze zostawia wpis w dzienniku; przerwany przebieg
    nie zostawiał żadnego.
    """

    run_id: str
    ts: str

    dziennik: Path = field(kw_only=True)
    """Dziennik żądań — plik **w historii repozytorium**, w przeciwieństwie do `katalog_wyjscia`.

    Pole, nie global modułu (od 2026-09-18). Dopóki ścieżka była stałą `scripts/sonda.py`,
    test musiał ją podstawiać w tym module, a każdy następny plik piszący do dziennika
    wymagałby drugiego podstawienia — i drugiego miejsca, w którym można o nim zapomnieć.
    Kronika niesie ścieżkę razem z `run_id` i `ts`, bo to są trzy współrzędne jednego
    przebiegu; kto ma kronikę, ma też prawo pisać tam, gdzie ona pisze.
    """

    katalog_wyjscia: Path = field(kw_only=True)
    """Katalog na surowe odpowiedzi i podsumowania — poza historią repozytorium."""

    zapisane: list[Wynik] = field(default_factory=list)
    """Wszystko, co przez tę kronikę przeszło — także wtedy, gdy przebieg wywrócił się w pół.

    Pole istnieje po to, żeby **rachunek** przeżył wyjątek tak samo jak ślad (poprawka
    2026-09-17). Wiersze dziennika przeżywały już wcześniej, ale `main` liczył żądania
    z wartości zwróconej przez pomiar — a przy `LimiterStalledError` po 429 pomiar niczego nie
    zwraca. Operator dostawał wtedy samo „Sonda zatrzymana" i musiał policzyć N ręką z dziennika
    dokładnie wtedy, gdy jest to najtrudniejsze, choć konwencja `decisions.md` wymaga tej liczby
    co do sztuki.
    """

    wypisz: Callable[[str], None] = field(default=_drukuj)
    """Dokąd idzie wiersz na ekran. Domyślnie `print` z `flush=True`; test podstawia listę.

    Wstrzykiwalne, bo ten moduł nie ma prawa znać `rich` (reguła 7), a przyszły `pipeline`
    będzie chciał wypisywać wiersz przez `console.py`, nie przez `print`. Druk zostaje
    **w** `zanotuj`, a nie w wywołującym: własność „wiersz na ekranie w chwili powstania
    wyniku" ma być własnością kroniki, nie pamięci każdego pomiaru z osobna.
    """

    @classmethod
    def na_teraz(cls, zegar: Clock, *, dziennik: Path, katalog_wyjscia: Path) -> Kronika:
        """Kronika przebiegu zaczynającego się teraz — według podanego zegara.

        Zegar jest parametrem, nie `SystemClock()` w środku: test podstawia go w jednym
        miejscu (`zadanie.zegar`), a `logbook` nie decyduje, który zegar jest prawdziwy.
        """
        ts = utc_iso(zegar.wall())
        return cls(
            run_id="sonda-" + ts.replace("-", "").replace(":", ""),
            ts=ts,
            dziennik=dziennik,
            katalog_wyjscia=katalog_wyjscia,
        )

    def zanotuj(self, wynik: Wynik) -> Wynik:
        """Wypisuje i zapisuje jeden wynik. Zwraca go, żeby dało się wołać w miejscu użycia."""
        self.wypisz(wynik.wiersz())
        dopisz_dziennik(self.dziennik, self.run_id, self.ts, [wynik])
        self.zapisane.append(wynik)
        return wynik


def wolna_sciezka(katalog: Path, rdzen: str, rozszerzenie: str) -> Path:
    """Ścieżka, której nie ma — dowód już zapłacony żądaniem nie ma prawa zniknąć.

    Zderzenie nazw jest przy znaczniku co do sekundy mało prawdopodobne, ale reakcją na nie
    nie może być ani nadpisanie (utrata pierwszej odpowiedzi), ani wyjątek (utrata drugiej,
    za którą cudzy serwer już zapłacił pracą). Zostaje trzecia droga: druga nazwa.
    """
    kandydat = katalog / f"{rdzen}.{rozszerzenie}"
    licznik = 2
    while kandydat.exists():
        kandydat = katalog / f"{rdzen}_{licznik}.{rozszerzenie}"
        licznik += 1
    return kandydat


def zapisz_surowe(
    katalog: Path, nazwa: str, znacznik: str, tresc: bytes, rozszerzenie: str
) -> Path:
    """Zapisuje surową odpowiedź ze znacznikiem czasu co do sekundy (zalążek złotego pliku).

    Bajty idą na dysk **takie, jakie przyszły** — maskowanie obowiązuje uwagi i adresy
    w dzienniku, nie dowód. Plik jest zalążkiem złotego pliku z reguły 17; parser, który
    powstanie później, ma się o co oprzeć, a przeglądający ma co obejrzeć okiem.
    """
    katalog.mkdir(parents=True, exist_ok=True)
    sciezka = wolna_sciezka(katalog, f"{nazwa}_{znacznik}", rozszerzenie)
    sciezka.write_bytes(tresc)
    return sciezka


# --- dziennik żądań i podsumowanie ---------------------------------------------------------


DLUGOSC_SKROTU_W_DZIENNIKU = 16
"""Ile znaków skrótu niesie kolumna `sha256` dziennika. 64 bity na rozróżnienie dwóch pobrań
tego samego dokumentu — z zapasem."""


def skrot_dziennika(sha256: str) -> str:
    """Skrót przycięty do postaci, w jakiej stoi w dzienniku.

    Jedno miejsce, bo porównanie dwóch skrótów o **różnej długości** jest zawsze nierówne, a to
    znaczy w tym pomiarze „bajty NIESTABILNE" — czyli fałszywy werdykt w kierunku droższym:
    odrzucenie klucza tożsamości, który działa. Droga do nierówności jest realna: sekcja wpisów
    ręcznych w dzienniku zaprasza człowieka do wypełnienia kolumny `sha256`, a człowiek
    kopiujący skrót z `podsumowanie_*.json` skopiuje wszystkie 64 znaki (znalezione przeglądem
    2026-09-17).
    """
    return sha256[:DLUGOSC_SKROTU_W_DZIENNIKU]


NAGLOWEK_DZIENNIKA = """# Dziennik żądań

Data utworzenia: {data}
Status: żywy — dopisywany przez `scripts/sonda.py` przy każdym przebiegu, nigdy przepisywany
Autor: narzędzie (wpisy maszynowe)
Related to: `ARCHITEKTURA_KIO_TOOL.md` (4.1 reguła zgody, 4.4 `requests_log`), `decisions.md`

---

Reguła zgody mówi, że pojedynczy odczyt diagnostyczny nie wymaga zgody właściciela, ale
**zawsze zostawia wpis w dzienniku**. Dopóki nie ma bazy, dziennikiem jest ten plik; kolumny
są kolumnami `requests_log` z modelu danych (4.4), z dwiema dodanymi: `sha256` wiąże wiersz
z bajtami odpowiedzi w `scripts/out/` (katalog spoza historii), a `kształt` niesie ocenę
z reguły 17 — status 200 przy kształcie niezgodnym to jest właśnie ten przypadek, dla
którego reguła istnieje.

Adres przechodzi przez `mask_tokens`, bo `requests_log` trzyma `url_redacted`, nie `url`.

**Kolumna `adres` niesie punkt końcowy bez parametrów zapytania** i to jest granica, nie
przeoczenie: dwa żądania różniące się wyłącznie parametrami dają w tej tabeli dwa wiersze
nie do odróżnienia. Widać to na pomiarze 2a, który celowo wysyła to samo żądanie w dwóch
sprzecznych pisowniach parametru dat. Znaczenie praktyczne ma to dziś w jednym miejscu —
odczyt wstecz pomiaru 19 dopasowuje wiersze po tej kolumnie — a tam adres jest niepowtarzalny
(`ContentHtml/18946`). Gdy przestanie być, kolumna musi dostać parametry, a nie dopasowanie
dodatkowe kryterium: dziennik ma mówić, co naprawdę poszło.

Wiersz powstaje w chwili powrotu żądania, a nie po całym pomiarze: przerwany przebieg ma
zostawić ślad po tym, co **już** poszło do cudzego serwisu.

Pomiar, który nie został wysłany (bo grupa stanęła po odmowie), ma w kolumnie `metoda`
przedrostek `nie:` i nie liczy się do „N żądań" w `decisions.md`.

---

## Wpisy ręczne

Nie każde żądanie tego projektu wychodzi przez sondę, a reguła mówi „**każdy** pojedynczy
odczyt zostawia wpis". Przegląd z 2026-09-14 wysłał około trzydziestu żądań i zapisał je
w tabeli w `ARCHITEKTURA_KIO_TOOL.md` (sekcja 7); pomiar 1 poszedł `curl`-em, bo reguła 11
zabrania budowania konstruktu FTP w drzewie; weryfikacja adresu urzędu przed wysłaniem pisma
będzie takim samym odczytem. Wpisów maszynowych po nich nie ma i nie będzie.

Wiersz dopisuje się tutaj **ręką**, w tych samych kolumnach co niżej, z `run_id` w postaci
`recznie-RRRRMMDD`. Kolumny, których przy odczycie ręcznym nie da się wypełnić, dostają „—";
kolumna `sha256` zostaje pusta, jeśli bajtów nikt nie zachował — i to jest informacja o wadze
dowodu, nie brak do uzupełnienia.

| run_id | ts | metoda | adres | status | ms | bajty | sha256 | kształt |
|---|---|---|---|---|---|---|---|---|

---

## Wpisy maszynowe

Dopisywane przez `scripts/sonda.py` na końcu pliku. Tabela rośnie w dół i nie jest sortowana.

| run_id | ts | metoda | adres | status | ms | bajty | sha256 | kształt |
|---|---|---|---|---|---|---|---|---|
"""


def wiersz_dziennika(run_id: str, wynik: Wynik, ts: str) -> str:
    if not wynik.wyslane:
        # Wiersz jest, bo zniknięcie pomiaru z dziennika jest ciszą; przedrostek jest,
        # bo „ślad po każdym żądaniu" nie może obejmować czegoś, co żądaniem nie było.
        return (
            f"| {run_id} | {ts} | nie:{wynik.metoda} | `(niewysłane)` | — | — | — | — | "
            f"{wynik.uwaga} |\n"
        )
    status = "—" if wynik.status is None else str(wynik.status)
    ksztalt = (
        "—"
        if wynik.ksztalt_zgodny is None
        else ("zgodny" if wynik.ksztalt_zgodny else "**NIEZGODNY**")
    )
    # Przez `skrot_dziennika`, nie literałem: odczyt wsteczny przycina tą samą funkcją, a dwa
    # przycięcia o różnej długości dają zawsze nierówność, czyli fałszywe „bajty NIESTABILNE".
    skrot = skrot_dziennika(wynik.sha256) if wynik.sha256 else "—"
    adres = mask_tokens(wynik.adres)
    return (
        f"| {run_id} | {ts} | {wynik.metoda} | `{adres}` | {status} | "
        f"{round(wynik.czas_s * 1000)} | {wynik.bajtow} | `{skrot}` | {ksztalt} |\n"
    )


def dopisz_dziennik(dziennik: Path, run_id: str, ts: str, wyniki: Sequence[Wynik]) -> None:
    """Dopisuje po wierszu na żądanie. Plik jest w historii repozytorium — inaczej nie byłby
    dziennikiem, tylko kolejnym plikiem roboczym obok `scripts/out/`.

    Data w nagłówku pochodzi z przebiegu, który ten plik zakłada, a nie z dnia napisania
    kodu. Wpisana na sztywno byłaby liczbą bez pokrycia w pierwszym dniu, w którym ktoś
    uruchomi sondę później niż autor tego napisu — czyli zasadą 7.1 złamaną w pliku, który
    powstał po to, żeby jej pilnować.
    """
    dziennik.parent.mkdir(parents=True, exist_ok=True)
    if not dziennik.exists():
        # `replace`, nie `format`: nagłówek jest dwudziestoma linijkami markdownu, a pierwszy
        # dopisany do niego przykład z nawiasem klamrowym wywróciłby tworzenie dziennika
        # `KeyError`-em — w pliku, który powstaje po to, żeby ślad nie ginął.
        naglowek = NAGLOWEK_DZIENNIKA.replace("{data}", ts[:10])
        dziennik.write_text(naglowek, encoding="utf-8", newline="\n")
    with dziennik.open("a", encoding="utf-8", newline="\n") as plik:
        for wynik in wyniki:
            plik.write(wiersz_dziennika(run_id, wynik, ts))


def zapisz_podsumowanie(
    katalog: Path, pomiar: str, run_id: str, ts: str, wyniki: Sequence[Wynik]
) -> Path:
    """Podsumowanie ze znacznikiem czasu w nazwie — dwa przebiegi tego samego dnia nie
    nadpisują się nawzajem, bo konwencja `decisions.md` mówi „dopisuje się nowy"."""
    katalog.mkdir(parents=True, exist_ok=True)
    sciezka = wolna_sciezka(katalog, f"podsumowanie_{pomiar}_{run_id}", "json")
    sciezka.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "ts": ts,
                "pomiar": pomiar,
                "zadania": [
                    {
                        "nazwa": w.nazwa,
                        "metoda": w.metoda,
                        "adres": mask_tokens(w.adres),
                        "status": w.status,
                        "bajtow": w.bajtow,
                        "czas_s": round(w.czas_s, 3),
                        "sha256": w.sha256,
                        "plik": w.plik.name if w.plik else None,
                        "ksztalt_zgodny": w.ksztalt_zgodny,
                        "ksztalt_uwaga": w.ksztalt_uwaga,
                        "ksztalt_zrodlo": w.ksztalt_zrodlo,
                        "uwaga": w.uwaga,
                        "wyslane": w.wyslane,
                    }
                    for w in wyniki
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return sciezka
