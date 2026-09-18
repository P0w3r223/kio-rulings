"""Wszystkie zdania dla operatora — moduł czysty (reguła 6), jedyny autor zdań `cli.py` (reguła 9).

Bez `rich`, `typer`, `questionary`, `httpx`, `sqlite3` i `openpyxl`: każde zdanie da się
sprawdzić testem bez terminala, a flagi CLI i przyszły kreator pokazują dosłownie to samo. Zdania
przyjmują liczby, napisy i `Criteria` (moduł czysty), nie obiekty z `pipeline` ani `store` —
kierunek zależności idzie od warstwy użytkownika do potoku, nigdy odwrotnie (reguła 8), a moduł
czysty nie ma po co znać struktur, z których czyta trzy pola.

`Block` jest modelem widoku (wzorzec z `ceidg-tool`): tytuł, nagłówki, wiersze, uwagi. Rysuje
go `ui/render.py`; `as_text()` jest postacią do asercji w testach i do logu.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..criteria import ETYKIETY, Criteria


@dataclass(frozen=True)
class Block:
    """Jeden ekran albo jedna tabela. `headers` puste = blok klucz-wartość."""

    title: str
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    notes: tuple[str, ...] = ()

    def as_text(self) -> str:
        """Postać tekstowa — do logu, do trybu cichego i do asercji w testach."""
        lines = [self.title] if self.title else []
        if self.headers:
            lines.append(" | ".join(self.headers))
        lines.extend(" | ".join(row) for row in self.rows)
        lines.extend(self.notes)
        return "\n".join(lines)


# ------------------------------------------------------------------------ pomoc poleceń

POMOC_PROGRAMU = "kio-tool — lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej."
POMOC_POBIERZ = (
    "Pobiera orzeczenia według kryteriów do lokalnej bazy i eksportuje wynik. Przebieg przerwany "
    "(Ctrl+C, błąd sieci, brak zgody) wznawia się tym samym poleceniem albo przez `wznow`, "
    "bez duplikatów."
)
POMOC_WZNOW = (
    "Wznawia przerwany przebieg od ostatniej strony listy — podany przez --run-id albo ostatni "
    "przerwany. Kryteria bierze z bazy, nie z flag."
)
POMOC_EKSPORTUJ = (
    "Eksportuje z lokalnej bazy, bez żadnego żądania do sieci: dokumenty objęte przebiegiem "
    "(--run-id) albo pasujące do kryteriów (--od, --do, --fraza …)."
)
POMOC_RUNY = "Wypisuje ostatnie przebiegi z bazy: status, zakres, liczbę dokumentów i żądań."
POMOC_PRZELICZ = (
    "Przelicza metadane i indeks pełnotekstowy z surowych wersji w bazie — zero żądań do sieci."
)
POMOC_SZUKAJ = (
    "Szuka frazy dosłownie w pełnym tekście korpusu lokalnego (FTS5) z filtrami; wynik zawsze "
    "mówi, ile dokumentów objął."
)

POMOC_OD = "początek zakresu dat wydania, RRRR-MM-DD (włącznie)"
POMOC_DO = "koniec zakresu dat wydania, RRRR-MM-DD (włącznie)"
POMOC_FRAZA = "fraza szukana dosłownie: u kanału w jego wyszukiwarce, lokalnie w pełnym tekście"
POMOC_ROZSTRZYGNIECIE = (
    "rozstrzygnięcie (można powtórzyć przy szukaniu i eksporcie): oddalono, uwzglednione, "
    "umorzono, odrzucono, inne — lista zmierzona na stu rekordach, nie udokumentowana"
)
POMOC_RODZAJ = "rodzaj orzeczenia (można powtórzyć lokalnie): wyrok albo postanowienie"
POMOC_PRZEPIS = "przepis w zapisie kanału, np. „art. 226 ust. 1 pkt 5 Pzp” (podnapis)"
POMOC_PRZEWODNICZACY = "przewodniczący składu (podnapis nazwiska)"
POMOC_STRONA = "strona postępowania — odwołujący albo zamawiający (podnapis nazwy)"
POMOC_MAKS = "najwyżej tyle kandydatów w przebiegu — ogranicza koszt u cudzego serwisu"
POMOC_FORMAT = "formaty eksportu po przecinku: xlsx, csv, jsonl, md (domyślnie xlsx)"
POMOC_OUT = (
    "rdzeń nazwy plików wyniku, bez rozszerzenia (np. `--out C:\\dane\\styczen` daje "
    "`styczen.xlsx`); istniejący katalog dostaje plik o nazwie domyślnej w środku; bez flagi — "
    "katalog `wyniki/` obok bazy"
)
POMOC_CEL = "cel pobrania — zdanie zapisywane w arkuszu Metadane, nigdzie indziej"
POMOC_BAZA = "plik bazy SQLite; domyślnie w katalogu danych użytkownika, poza repozytorium"
POMOC_KANAL = "kanał akwizycji (dziś wyłącznie `atlas`)"
POMOC_ZGODA = (
    "zgoda właściciela na przebieg masowy — obowiązuje w tej sesji i nie da się jej zapisać "
    "w konfiguracji; bez niej narzędzie wysyła najwyżej kilkadziesiąt żądań"
)
POMOC_RUN_ID = "identyfikator przebiegu z `runy`; można powtórzyć"
POMOC_RUN_ID_JEDEN = "identyfikator przebiegu z `runy`; bez niego — ostatni przerwany"
POMOC_LIMIT = "ile wierszy pokazać"
POMOC_STATUS = "tylko przebiegi w tym stanie: w_toku, zakonczony, przerwany, blad (można powtórzyć)"
POMOC_WSZYSTKO = "przelicz także wersje już przeliczone bieżącą wersją odczytu"

# ------------------------------------------------------------------------ zdania stałe

PRZERWANE = (
    "Przerwano (Ctrl+C). Przebieg zapisany jako przerwany — to samo polecenie albo `wznow` "
    "dokończy go bez duplikatów."
)
KRYTERIA_PUSTE = (
    "Brak kryteriów: podaj zakres dat (--od, --do) albo filtr (--fraza, --rozstrzygniecie, "
    "--rodzaj, --przepis, --przewodniczacy, --strona). Przebieg bez kryteriów objąłby cały "
    "zbiór kanału — na to trzeba zdecydować się jawnie, zakresem dat."
)
EKSPORT_BEZ_ZAKRESU = (
    "Podaj, co eksportować: --run-id z listy `runy` albo kryteria (--od, --do, --fraza …)."
)
BRAK_PRZEBIEGOW = "W bazie nie ma jeszcze żadnego przebiegu."
NIC_DO_EKSPORTU = "Nie ma czego eksportować: żaden dokument nie pasuje."
EKSPORT_RUN_I_KRYTERIA = (
    "Podaj albo `--run-id`, albo kryteria (`--od/--do` i filtry) — nie jedno i drugie: eksport "
    "przebiegu obejmuje to, co przebieg objął, a kryteria zostałyby po cichu pominięte."
)
NAGLOWKI_RUNOW = ("przebieg", "status", "kanał", "zakres", "start", "dokumentów", "żądań")
NAGLOWKI_TRAFIEN = ("sygnatura", "data wydania", "rozstrzygnięcie", "fragment")


def przebieg_bez_powiazan(run_id: str, zakres: str) -> str:
    """Przebieg sprzed schematu 2: żądania zapisane, dokumenty w korpusie, zero powiązań.

    Schemat 1 nie miał tabeli `run_documents`, a migracja tworzy ją pustą, więc `eksportuj
    --run-id` nie ma po czym wybrać dokumentów tamtego przebiegu. Operator ma się dowiedzieć
    **dlaczego** i dostać drogę zapasową nazwaną wprost — jak przy `do_wznowienia`.
    """
    od, _, do = zakres.partition("..")
    wskazowka = (
        f"`eksportuj --od {od} --do {do}`"
        if od and do
        else f"`eksportuj --od … --do …` z zakresem {zakres}"
    )
    return (
        f"Przebieg {run_id} pochodzi sprzed schematu z tabelą powiązań: ma zapisane żądania, "
        "a jego dokumenty są w korpusie, ale nie są z nim powiązane. Wyeksportuj ten zakres "
        f"przez {wskazowka} albo uruchom `pobierz` z tym zakresem — dokumenty w bazie nie "
        "kosztują żądań, a nowy przebieg je powiąże."
    )


def blad(komunikat: str) -> str:
    return f"Błąd: {komunikat}"


def uwaga(komunikat: str) -> str:
    return f"Uwaga: {komunikat}"


def zle_kryteria(bledy: str) -> str:
    return f"Kryteria nie przeszły sprawdzenia:\n{bledy}"


def zly_format(podany: str, dostepne: Sequence[str]) -> str:
    return f"Nieznany format {podany!r}; dostępne: {', '.join(dostepne)}."


def zly_status(podany: str, dostepne: Sequence[str]) -> str:
    return f"Nieznany status przebiegu {podany!r}; dostępne: {', '.join(dostepne)}."


def start_przebiegu(kanal: str, kryteria: str, baza: str, tozsamosc: str) -> str:
    """Pierwszy ekran: co robimy, dokąd wysyłamy, gdzie zapisujemy, jak się przedstawiamy."""
    return "\n".join(
        (
            f"Kanał: {kanal}    kryteria: {kryteria}",
            f"Baza: {baza}",
            f"Tożsamość klienta: {tozsamosc}",
        )
    )


def wznawiam(run_id: str, kryteria: str, strona: int) -> str:
    return f"Wznawiam przebieg {run_id} ({kryteria}) od strony {strona}."


def podsumowanie(
    *,
    run_id: str,
    status: str,
    kandydatow: int,
    nowych: int,
    pominietych: int,
    zadan: int,
    baza: str,
    zgloszone: int | None = None,
    objetych_lacznie: int | None = None,
    pobranych_lacznie: int | None = None,
    zadan_lacznie: int | None = None,
    bledow_odczytu: int = 0,
    brakujacych: int = 0,
) -> str:
    """Rachunek przebiegu — liczba żądań wypisana, nie zostawiona do policzenia z ekranu.

    Dwa rachunki, gdy przebieg był wznawiany: „w tej sesji" (liczniki wywołania) i „w całym
    przebiegu" (z bazy: `run_documents`, `requests_log`). Bez drugiego operator po wznowieniu
    widziałby 96 nowych i nie wiedziałby, że przebieg objął sto.
    """
    linie = [
        f"Przebieg {run_id}: {status}",
        f"Kandydatów w zakresie: {kandydatow}, zapisanych nowych: {nowych}, "
        f"pominiętych (już w bazie): {pominietych}",
        f"Żądań wysłanych: {zadan}",
    ]
    if zgloszone is not None and zgloszone != kandydatow:
        linie.append(
            f"Kanał zgłosił w zakresie: {zgloszone} — objęto {kandydatow}; różnica to "
            "limit --maks, przerwanie albo dopływ w trakcie"
        )
    if objetych_lacznie is not None and (
        objetych_lacznie != kandydatow or (zadan_lacznie or 0) != zadan
    ):
        linie.append(
            f"W całym przebiegu (z bazy): objętych {objetych_lacznie}, pobranych "
            f"{pobranych_lacznie}, żądań {zadan_lacznie}"
        )
    if bledow_odczytu:
        linie.append(
            f"Wersji zapisanych, ale nieodczytanych do metadanych: {bledow_odczytu} "
            "(surowe bajty są w bazie; `przelicz` spróbuje ponownie)"
        )
    if brakujacych:
        linie.append(
            f"Dokumentów z listy, których kanał już nie ma (404): {brakujacych} — pominięte, "
            "przebieg poszedł dalej"
        )
    linie.append(f"Baza: {baza}")
    return "\n".join(linie)


def nowa_baza(sciezka: str) -> str:
    """Pierwsze otwarcie ścieżki zakłada pustą bazę — i ma o tym powiedzieć.

    Literówka w `--baza` nie kończy się błędem, tylko nową, pustą bazą obok prawdziwej: `runy`
    mówi wtedy „nie ma żadnego przebiegu" nad korpusem, który istnieje pod inną ścieżką
    (przejście ręczne 2026-09-18). Jedno zdanie ze ścieżką rozstrzyga, czy to pierwsze
    uruchomienie, czy pomyłka.
    """
    return (
        f"Założono nową, pustą bazę: {sciezka}. Jeśli spodziewałeś się istniejącego korpusu, "
        "sprawdź ścieżkę `--baza`."
    )


def zly_limit(limit: int) -> str:
    return f"Limit wierszy (`--limit`) ma być liczbą dodatnią, a jest {limit}."


def blok_eksportu(
    sciezki: Sequence[str], dokumentow: int, formaty: Sequence[str], bez_daty_poza_filtrem: int
) -> Block:
    wiersze: list[tuple[str, str]] = [
        ("dokumentów w eksporcie", str(dokumentow)),
        ("formaty", ", ".join(formaty)),
    ]
    wiersze.extend(("plik", sciezka) for sciezka in sciezki)
    uwagi: list[str] = []
    if bez_daty_poza_filtrem:
        uwagi.append(
            f"Poza filtrem dat zostało {bez_daty_poza_filtrem} dokumentów bez daty wydania — "
            "filtr po dacie ich nie widzi (architektura 4.8)."
        )
    return Block(title="Eksport zapisany", rows=tuple(wiersze), notes=tuple(uwagi))


def blok_runow(wiersze: Sequence[tuple[str, ...]], lacznie: int) -> Block:
    """Tabela przebiegów; `lacznie` z bazy, nie z długości strony (lekcja z `ceidg-tool`)."""
    return Block(
        title=f"Przebiegi: pokazano {len(wiersze)} z {lacznie}",
        headers=NAGLOWKI_RUNOW,
        rows=tuple(wiersze),
    )


def blok_przeliczenia(
    przeliczonych: int, bledow: int, w_korpusie: int, zaindeksowanych: int
) -> Block:
    uwagi: list[str] = []
    if w_korpusie == 0:
        uwagi.append(KORPUS_PUSTY)
    if zaindeksowanych < w_korpusie:
        uwagi.append(
            f"{w_korpusie - zaindeksowanych} dokumentów nadal bez metadanych — `szukaj` ich nie "
            "obejmie; sprawdź błędy odczytu."
        )
    return Block(
        title="Przeliczenie zakończone",
        rows=(
            ("przeliczonych wersji", str(przeliczonych)),
            ("błędów odczytu", str(bledow)),
            ("dokumentów w korpusie", str(w_korpusie)),
            ("zaindeksowanych", str(zaindeksowanych)),
        ),
        notes=tuple(uwagi),
    )


def blok_wyszukiwania(
    wiersze: Sequence[tuple[str, ...]],
    *,
    fraza: str,
    w_korpusie: int,
    zaindeksowanych: int,
    trafien: int,
    bez_daty_poza_filtrem: int,
) -> Block:
    """Tabela trafień z liczbami **nad** nią — mina 2: wynik mówi, czego nie objął."""
    uwagi = [
        f"W korpusie: {w_korpusie} dokumentów, zaindeksowanych: {zaindeksowanych}, "
        f"trafień: {trafien}, pokazano: {len(wiersze)}."
    ]
    if zaindeksowanych < w_korpusie:
        uwagi.append(
            f"{w_korpusie - zaindeksowanych} dokumentów nie ma w indeksie — uruchom `przelicz`."
        )
    if bez_daty_poza_filtrem:
        uwagi.append(
            f"Poza filtrem dat zostało {bez_daty_poza_filtrem} dokumentów bez daty wydania."
        )
    return Block(
        title=f"Trafienia dla „{fraza}”",
        headers=NAGLOWKI_TRAFIEN,
        rows=tuple(wiersze),
        notes=tuple(uwagi),
    )


KORPUS_PUSTY = (
    "Korpus jest pusty — napełnia go `pobierz --od RRRR-MM-DD --do RRRR-MM-DD` (z `--zgoda` "
    "powyżej kilkudziesięciu żądań)."
)


def bez_daty_poza_filtrem(ile: int) -> str:
    return (
        f"Poza filtrem dat zostało {ile} dokumentów bez daty wydania — filtr po dacie ich nie "
        "widzi (architektura 4.8); `eksportuj --run-id …` obejmie je bez filtra dat."
    )


def zero_trafien(
    kryteria: Criteria,
    *,
    w_korpusie: int,
    zaindeksowanych: int,
    bez_daty: int = 0,
) -> Block:
    """Zero trafień z diagnozą: co usunąć z kryteriów, od najbardziej podejrzanego filtra.

    Liczby korpusu stoją tu **zawsze**, jak nad tabelą trafień — tester 2026-09-18 zmierzył, że
    pierwsze `szukaj` na świeżej bazie radziło „poszerz zakres dat", a prawdziwym powodem był
    korpus bez ani jednego dokumentu. Pusty korpus dostaje jedno zdanie i polecenie, które go
    napełnia; diagnoza filtrów ma sens dopiero, gdy jest w czym szukać.
    """
    uwagi = [
        f"W korpusie: {w_korpusie} dokumentów, zaindeksowanych: {zaindeksowanych}.",
        f"Kryteria: {kryteria.describe()}",
    ]
    if w_korpusie == 0:
        uwagi.append(KORPUS_PUSTY)
        return Block(title="Zero trafień", notes=tuple(uwagi))
    if zaindeksowanych < w_korpusie:
        uwagi.append(
            f"Tylko {zaindeksowanych} z {w_korpusie} dokumentów ma metadane i indeks — filtry po "
            "polach i frazie nie widzą reszty; uruchom `przelicz`."
        )
    if bez_daty:
        uwagi.append(bez_daty_poza_filtrem(bez_daty))
    for pole, kandydat in kryteria.poszerzenia():
        uwagi.append(f"Spróbuj bez pola „{ETYKIETY[pole]}”: {kandydat.describe()}")
    if not kryteria.poszerzenia():
        uwagi.append("To jedyny filtr — poszerz go albo sprawdź pisownię.")
    return Block(title="Zero trafień", notes=tuple(uwagi))


def zero_kandydatow(kryteria: Criteria) -> Block:
    """Kanał nie zwrócił żadnego kandydata — diagnoza jak wyżej, plus jedno zastrzeżenie:
    semantyka filtrów kanału jest niezmierzona (mina 2), więc pusty wynik nie dowodzi braku."""
    uwagi = [f"Kryteria: {kryteria.describe()}"]
    uwagi.extend(
        f"Spróbuj bez pola „{ETYKIETY[pole]}”: {kandydat.describe()}"
        for pole, kandydat in kryteria.poszerzenia()
    )
    uwagi.append(
        "Filtry kanału nie miały jeszcze własnego pomiaru (contract.yaml, `parametry_listy`): "
        "pusty wynik znaczy „kanał nic nie zwrócił”, nie „takich orzeczeń nie ma”."
    )
    return Block(title="Kanał nie zwrócił żadnego kandydata", notes=tuple(uwagi))
