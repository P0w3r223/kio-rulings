"""Wszystkie zdania dla operatora — moduł czysty (reguła 6), jedyny autor zdań `cli.py` (reguła 9).

Bez `rich`, `typer`, `questionary`, `httpx`, `sqlite3` i `openpyxl`: każde zdanie da się
sprawdzić testem bez terminala, a flagi CLI i przyszły kreator pokazują dosłownie to samo. Zdania
przyjmują liczby, napisy i `Criteria` (moduł czysty), nie obiekty z `pipeline` ani `store` —
kierunek zależności idzie od warstwy użytkownika do potoku, nigdy odwrotnie (reguła 8), a moduł
czysty nie ma po co znać struktur, z których czyta trzy pola.

Pojemniki widoku (`Block`, `Pytanie`, `Opcja`, `StanKorpusu`) mieszkają od 2026-09-20
w `ui/modele.py` i są stąd re-eksportowane: ten moduł pisze zdania, tamten trzyma kształty,
w które się układają. Rysuje je `ui/render.py`, a `ui/maszynowo.py` wydaje maszynowo.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..criteria import ETYKIETY, Criteria
from ..wycena import Wycena
from .modele import Block, Opcja, Pytanie, RodzajPytania, StanKorpusu

__all__ = [  # re-eksport: jedno publiczne wejście do warstwy widoku zostaje w `texts`
    "Block",
    "Opcja",
    "Pytanie",
    "RodzajPytania",
    "StanKorpusu",
]


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
POMOC_KREATOR = (
    "Kreator dla operatora: menu, pytania i tabela kosztów przed każdym pobraniem. To samo "
    "otwiera `kio-tool` bez polecenia na terminalu."
)
POMOC_DEMO = (
    "Tryb pokazowy: kreator nad fikcyjnym korpusem generowanym w procesie — bez sieci, bez adresu "
    "kontaktowego, w osobnym katalogu danych. Ta sama ścieżka co na danych prawdziwych."
)
POMOC_OD_NOWA = "zacznij pokaz od pustej bazy (kasuje wyłącznie bazę trybu pokazowego)"
POMOC_PRZELICZ = (
    "Przelicza metadane i indeks pełnotekstowy z surowych wersji w bazie — zero żądań do sieci."
)
POMOC_POKRYCIE = (
    "Raport pokrycia parsera z bazy (sekcje, cytowania, przepisy po roczniku z sygnatury) do "
    "`docs/raporty/` — zero żądań, bez tekstu orzeczeń; z `--zloty` sprawdza adnotacje złotego "
    "zbioru."
)
POMOC_CEL_RAPORTU = "katalog raportu (domyślnie `docs/raporty` w bieżącym katalogu)"
POMOC_ZLOTY = "katalog złotego zbioru (`tests/gold`) — adnotacje sprawdzane wobec korpusu"
POMOC_SZUKAJ = (
    "Szuka frazy dosłownie w pełnym tekście korpusu lokalnego (FTS5) z filtrami; wynik zawsze "
    "mówi, ile dokumentów objął."
)

POMOC_OD = "początek zakresu dat wydania, RRRR-MM-DD (włącznie)"
POMOC_DO = "koniec zakresu dat wydania, RRRR-MM-DD (włącznie)"
POMOC_FRAZA = (
    "fraza szukana dosłownie: lokalnie w pełnym tekście (`szukaj`, `eksportuj`); w `pobierz` "
    "idzie do wyszukiwarki kanału, która u Atlasu dopasowuje sygnaturę, nie treść (zmierzone "
    "2026-09-18)"
)
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
POMOC_JSON = (
    "wynik jako JSON Lines na standardowe wyjście, jeden dokument na wiersz — dla programu, "
    "nie dla oka; tabela dla człowieka bez terminala łamie wartości na 80 znakach"
)

NAGLOWKI_TRAFIEN = ("sygnatura", "data wydania", "rozstrzygnięcie", "fragment")
NAGLOWKI_TRAFIEN_MASZYNOWE = ("doc_id", "url_zrodla", "cytowanie")
"""Droga od trafienia do źródła — tylko w `--json`; puste pole = wpisu nie odczytano."""


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
    ponowien_lacznie: int = 0,
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
    if ponowien_lacznie:
        # ADR-0007 Z-7 ujście 4: liczba z bazy, nie z pamięci procesu — to jest też wejście
        # pomiaru 24, więc ma przeżyć wznowienie tak samo jak `zadan_lacznie`.
        linie.append(
            f"Ponowień w całym przebiegu (z bazy): {ponowien_lacznie} — żądania powtórzone "
            "po zerwanym łączu, 5xx albo 429; każde liczy się do limitów tempa i do zgody"
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
        liczby=(("pokazano", len(wiersze)), ("lacznie", lacznie)),
    )


def czas_ludzki(sekundy: float) -> str:
    """`259200` → `3 doby 0 h`, `4320` → `1 h 12 min`, `42` → `42 s` — bez udawanej precyzji."""
    if sekundy < 60:
        return f"{sekundy:.0f} s"
    minuty = int(sekundy // 60)
    if minuty < 60:
        return f"{minuty} min"
    godziny, minuty = divmod(minuty, 60)
    if godziny < 24:
        return f"{godziny} h {minuty} min"
    doby, godziny = divmod(godziny, 24)
    return f"{doby} {odmiana(doby, 'doba', 'doby', 'dób')} {godziny} h"


def odmiana(ile: int, jedna: str, kilka: str, wiele: str) -> str:
    """Polski liczebnik: 1 doba, 2–4 doby, 5+ dób — z wyjątkiem nastek (12, 13, 14).

    Reguła „od pięciu — forma mnoga” kończy się na 21: poprawne jest „22 doby”, nie „22 dób”
    (przegląd kodu fazy 3, 2026-09-20). Jedna funkcja, bo ten sam błąd wyszedł potem przy
    liczbie orzeczeń w menu — licznik odmieniany w dwóch miejscach rozjeżdża się w trzecim."""
    if ile == 1:
        return jedna
    if ile % 10 in (2, 3, 4) and ile % 100 not in (12, 13, 14):
        return kilka
    return wiele


def orzeczen(ile: int) -> str:
    """`443` → `443 orzeczenia`, `445` → `445 orzeczeń`."""
    return f"{ile} {odmiana(ile, 'orzeczenie', 'orzeczenia', 'orzeczeń')}"


def tabela_kosztow(wycena: Wycena, *, prog_zgody: int, czas_pokazu_s: float | None = None) -> Block:
    """Koszt reszty przebiegu przed pierwszym dokumentem (ADR-0008 Z-5) — ten sam blok na
    ścieżce flag, w kreatorze i w pokazie. Czas jest **produkcyjny**; pokaz dopisuje swój obok."""
    if wycena.zadan is None:
        return Block(
            title="Koszt przebiegu",
            rows=(("dokumentów w zakresie", "kanał nie podał liczby"),),
            notes=(
                f"Bez liczby z kanału próg zgody pilnuje licznik żądań: bez zgody najwyżej "
                f"{prog_zgody} żądań.",
            ),
        )
    wiersze = [
        ("dokumentów do pobrania (najwyżej)", str(wycena.dokumentow)),
        ("dalszych stron listy", str(wycena.stron_listy)),
        ("żądań do serwisu (najwyżej)", str(wycena.zadan)),
        ("czas przy tempie kontraktu (co najmniej)", czas_ludzki(wycena.czas_s or 0.0)),
    ]
    if czas_pokazu_s is not None:
        wiersze.append(("czas w trybie pokazowym", czas_ludzki(czas_pokazu_s)))
    uwagi = [
        "Liczby są górną granicą: dokument już w bazie nie kosztuje żądania.",
    ]
    if wycena.zadan + wycena.zadan_juz > prog_zgody:
        uwagi.append(
            f"To przebieg masowy (ponad {prog_zgody} żądań) — wymaga zgody udzielonej w tej sesji."
        )
    return Block(title="Koszt przebiegu", rows=tuple(wiersze), notes=tuple(uwagi))


def blok_pokrycia(
    dokumentow: int,
    komplet: int,
    nierozpoznanych: int,
    cytowan: int,
    zloty: tuple[int, int, int] | None,
    sciezki: tuple[str, ...],
) -> Block:
    """Skrót raportu na ekran; `zloty` = (plików, sprawdzonych, zgodnych)."""
    wiersze = [
        ("dokumentów", str(dokumentow)),
        ("z kompletem sekcji", f"{komplet} z {dokumentow}"),
        ("cytowań nierozpoznanych", f"{nierozpoznanych} z {cytowan}"),
    ]
    uwagi: list[str] = []
    if zloty is None:
        uwagi.append("Złoty zbiór nie był podany — raport mówi „sprawdzono 0 z 0”.")
    else:
        plikow, sprawdzonych, zgodnych = zloty
        wiersze.append(
            ("złoty zbiór", f"sprawdzono {sprawdzonych} z {plikow}, zgodnych {zgodnych}")
        )
        if sprawdzonych < plikow:
            uwagi.append(
                f"{plikow - sprawdzonych} adnotacji niesprawdzonych — tej wersji dokumentu nie ma "
                "w korpusie; lista w raporcie."
            )
    wiersze += [("plik", sciezka) for sciezka in sciezki]
    return Block(title="Raport pokrycia zapisany", rows=tuple(wiersze), notes=tuple(uwagi))


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
        liczby=(
            ("przeliczonych", przeliczonych),
            ("bledow", bledow),
            ("w_korpusie", w_korpusie),
            ("zaindeksowanych", zaindeksowanych),
        ),
    )


def blok_wyszukiwania(
    wiersze: Sequence[tuple[str, ...]],
    *,
    fraza: str,
    w_korpusie: int,
    zaindeksowanych: int,
    trafien: int,
    bez_daty_poza_filtrem: int,
    zrodla: Sequence[tuple[str, ...]] = (),
) -> Block:
    """Tabela trafień z liczbami **nad** nią — mina 2: wynik mówi, czego nie objął.

    `zrodla` to wiersze `NAGLOWKI_TRAFIEN_MASZYNOWE`, równoległe do `wiersze`; puste = blok bez
    kolumn maszynowych (kreator, który ich nie pokazuje, nie musi ich liczyć).
    """
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
        liczby=(
            ("w_korpusie", w_korpusie),
            ("zaindeksowanych", zaindeksowanych),
            ("trafien", trafien),
            ("pokazano", len(wiersze)),
            ("bez_daty_poza_filtrem", bez_daty_poza_filtrem),
        ),
        kolumny_maszynowe=NAGLOWKI_TRAFIEN_MASZYNOWE if zrodla else (),
        wiersze_maszynowe=tuple(zrodla),
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
    # Mianownik przy zerze jest potrzebny **bardziej** niż przy trafieniach: to jedyne miejsce,
    # w którym konsument odróżnia „nie ma takich orzeczeń" od „nie ma ich w tym, co pobrano".
    liczby = (
        ("w_korpusie", w_korpusie),
        ("zaindeksowanych", zaindeksowanych),
        ("trafien", 0),
        ("pokazano", 0),
        ("bez_daty_poza_filtrem", bez_daty),
    )
    if w_korpusie == 0:
        uwagi.append(KORPUS_PUSTY)
        return Block(title="Zero trafień", notes=tuple(uwagi), liczby=liczby)
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
    return Block(title="Zero trafień", notes=tuple(uwagi), liczby=liczby)


def zero_kandydatow(kryteria: Criteria) -> Block:
    """Kanał nie zwrócił żadnego kandydata — diagnoza jak wyżej, plus jedno zastrzeżenie:
    semantyka filtrów kanału jest niezmierzona (mina 2), więc pusty wynik nie dowodzi braku."""
    uwagi = [f"Kryteria: {kryteria.describe()}"]
    uwagi.extend(
        f"Spróbuj bez pola „{ETYKIETY[pole]}”: {kandydat.describe()}"
        for pole, kandydat in kryteria.poszerzenia()
    )
    uwagi.append(
        "Filtry kanału mają inną semantykę niż lokalne (zmierzone 2026-09-18: `search` Atlasu "
        "dopasowuje sygnaturę, nie treść; `outcome` jest zgodny z rozstrzygnięciem): pusty wynik "
        "znaczy „kanał nic nie zwrócił”, nie „takich orzeczeń nie ma” — treść przeszukuje "
        "`szukaj` po pobraniu zakresu dat."
    )
    return Block(title="Kanał nie zwrócił żadnego kandydata", notes=tuple(uwagi))


# ------------------------------------------------------------------ kreator (ADR-0008 Z-7…Z-10)

MENU_WZNOW = "wznow"
MENU_POBIERZ = "pobierz"
MENU_SZUKAJ = "szukaj"
MENU_EKSPORTUJ = "eksportuj"
MENU_WYJDZ = "wyjdz"
WROC = "wroc"

CEL_DATY = "daty"
CEL_SYGNATURA = "sygnatura"
CEL_ROZSTRZYGNIECIE = "rozstrzygniecie"

BRAK_KONTAKTU = (
    "Pobieranie wymaga adresu kontaktowego w zmiennej KIO_TOOL_CONTACT — narzędzie przedstawia się "
    "nim serwisowi (reguła 16). Ustaw ją i uruchom program ponownie; wyszukiwanie i eksport "
    "działają bez niej."
)
PRZERWANO_AKCJE = (
    "Przerwano (Ctrl+C). Przebieg został zapisany jako przerwany — pozycja „Wznów” w menu "
    "dokończy go bez ponownego pobierania tego, co już przyszło."
)
FRAZA_TO_SYGNATURA = (
    "Wyszukiwarka Atlasu dopasowuje sygnaturę, nie treść (zmierzone 2026-09-18). Żeby szukać "
    "w treści, pobierz zakres dat, a potem użyj „Szukaj w korpusie”."
)


JAK_TO_DZIALA: tuple[str, ...] = (
    "Strzałki ↑↓ wybierają pozycję, Enter zatwierdza. W pytaniach tekstowych Enter bez "
    "wpisywania przyjmuje odpowiedź podaną w nawiasie kwadratowym.",
    "Każde pobranie pokazuje najpierw koszt — ile dokumentów, ile żądań i ile to potrwa — "
    "i dopiero wtedy pyta o zgodę. Nic nie wychodzi do sieci przed tą odpowiedzią.",
    "Ctrl+C przerywa bieżącą czynność i wraca do menu, a w menu kończy program. Przerwane "
    "pobranie wznowisz później od miejsca, w którym stanęło — nic nie pobierze się dwa razy.",
    "Szukanie i eksport czytają wyłącznie lokalną bazę: zero żądań, działają bez internetu.",
)
"""Cztery zdania o obsłudze narzędzia, nie o jego przeznaczeniu. Stoją na pierwszym ekranie,
bo operator czyta go raz i wtedy właśnie decyduje, czy wie, co robić."""


def pierwszy_ekran(*, pokaz: bool, stan: StanKorpusu | None = None) -> Block:
    """Pierwszy ekran kreatora; w trybie pokazowym — pierwszy z sześciu znaczników (Z-3)."""
    if pokaz:
        return Block(
            title="TRYB POKAZOWY — dane fikcyjne, żadne żądanie nie wychodzi do sieci",
            notes=(
                "Orzeczenia, sygnatury (KIO 9000–9999), osoby i strony są wygenerowane. "
                "Nic stąd nie "
                "jest cytatem z Krajowej Izby Odwoławczej ani z Atlasu Przetargów.",
                "Ścieżka jest ta sama co na danych prawdziwych: tabela kosztów, zgoda, przerwanie, "
                "wznowienie, wyszukiwanie i eksport.",
            ),
        )
    return Block(
        title="kio-tool — korpus orzecznictwa Krajowej Izby Odwoławczej",
        rows=_wiersze_stanu(stan),
        notes=JAK_TO_DZIALA,
    )


def _wiersze_stanu(stan: StanKorpusu | None) -> tuple[tuple[str, ...], ...]:
    if stan is None:
        return ()
    wiersze = [
        ("orzeczeń w korpusie", str(stan.dokumentow)),
        ("gotowych do szukania", f"{stan.zaindeksowanych} z {stan.dokumentow}"),
        ("baza", stan.sciezka),
    ]
    if stan.przerwanych:
        wiersze.insert(0, ("przerwane pobrania", str(stan.przerwanych)))
    return tuple(wiersze)


def pytanie_menu(*, jest_co_wznowic: bool, stan: StanKorpusu | None = None) -> Pytanie:
    """Menu, w którym każda pozycja mówi, co zrobi i czy kosztuje żądania.

    Gołe etykiety („Szukaj w korpusie") nie odpowiadają na jedyne pytanie, jakie ma operator
    przy pierwszym uruchomieniu: czy to wyśle coś do sieci i ile tego jest. Liczby pochodzą
    z lokalnej bazy (wzorzec z `ceidg-tool`, gdzie pozycja menu niesie koszt w żądaniach).
    """
    w_korpusie = "" if stan is None else f" — {orzeczen(stan.zaindeksowanych)}, bez sieci"
    opcje = [
        Opcja(MENU_POBIERZ, "Pobierz orzeczenia — najpierw koszt i pytanie o zgodę"),
        Opcja(MENU_SZUKAJ, f"Szukaj w korpusie{w_korpusie}"),
        Opcja(MENU_EKSPORTUJ, "Eksportuj z korpusu — Excel, Markdown, CSV albo JSONL; bez sieci"),
        Opcja(MENU_WYJDZ, "Wyjdź"),
    ]
    if jest_co_wznowic:
        opcje.insert(0, Opcja(MENU_WZNOW, "Wznów przerwany przebieg — dokończy to, co zostało"))
    return Pytanie(
        tresc="Co chcesz zrobić?",
        opcje=tuple(opcje),
        domyslna=MENU_WZNOW if jest_co_wznowic else MENU_POBIERZ,
    )


PYTANIE_CEL = Pytanie(
    tresc="Co pobrać? (koszt zobaczysz przed pobraniem, nic jeszcze nie wychodzi do sieci)",
    opcje=(
        Opcja(CEL_DATY, "Orzeczenia z zakresu dat wydania"),
        Opcja(CEL_SYGNATURA, "Jedno orzeczenie po sygnaturze (np. KIO 1205/20)"),
        Opcja(CEL_ROZSTRZYGNIECIE, "Orzeczenia z zakresu dat o danym rozstrzygnięciu"),
        Opcja(WROC, "Wróć do menu"),
    ),
    domyslna=CEL_DATY,
)
PYTANIE_OD = Pytanie(
    tresc="Data wydania od",
    rodzaj="tekst",
    podpowiedz="RRRR-MM-DD, na przykład 2024-01-01; jeden miesiąc to około 300 orzeczeń",
)
PYTANIE_DO = Pytanie(
    tresc="Data wydania do",
    rodzaj="tekst",
    podpowiedz="RRRR-MM-DD; Enter bez wpisywania = bez górnej granicy",
)
PYTANIE_SYGNATURA = Pytanie(
    tresc="Sygnatura",
    rodzaj="tekst",
    podpowiedz="na przykład KIO 1205/20 albo KIO 1205/2020 — oba zapisy znaczą to samo",
)
PYTANIE_FRAZA = Pytanie(
    tresc="Fraza do znalezienia w treści",
    rodzaj="tekst",
    podpowiedz=(
        "szukanie jest dosłowne i nie zna odmiany — „wadium” nie znajdzie „wadia” ani "
        "„wadiom”; Enter bez wpisywania = wszystko w zakresie"
    ),
)
PYTANIE_ROZSTRZYGNIECIE = Pytanie(
    tresc="Rozstrzygnięcie:",
    opcje=(
        Opcja("oddalono", "oddalono — Izba nie przyznała racji odwołującemu"),
        Opcja("uwzglednione", "uwzględnione — Izba przyznała rację odwołującemu"),
        Opcja("umorzono", "umorzono — sprawa zakończona bez rozstrzygnięcia co do meritum"),
        Opcja("odrzucono", "odrzucono — odwołanie nie weszło pod rozpoznanie"),
        Opcja("inne", "inne — pozostałe wartości, jakie zwraca kanał"),
    ),
    domyslna="oddalono",
    podpowiedz=(
        "lista zmierzona na stu rekordach kanału, nie słownik urzędowy — kanał może zwrócić "
        "wartość spoza niej"
    ),
)
PYTANIE_EKSPORT = Pytanie(
    tresc="Zapisać wynik do pliku? (czyta lokalną bazę, zero żądań)",
    opcje=(
        Opcja("xlsx", "Arkusz Excel (.xlsx)"),
        Opcja("md", "Katalog plików Markdown"),
        Opcja("csv", "CSV"),
        Opcja("jsonl", "JSONL"),
        Opcja(WROC, "Nie zapisuj"),
    ),
    domyslna="xlsx",
)


NIE_ROZUMIEM_TAK_NIE = "Nie rozumiem odpowiedzi — wpisz „tak” albo „nie”."


def linia_tekstowa(pytanie: Pytanie) -> str:
    """Pytanie tekstowe razem z podpowiedzią i odpowiedzią domyślną — jedno miejsce, żeby
    ścieżka ze strzałkami i ścieżka awaryjna pokazywały operatorowi to samo."""
    linia = pytanie.tresc if not pytanie.podpowiedz else f"{pytanie.tresc} ({pytanie.podpowiedz})"
    return linia if not pytanie.domyslna else f"{linia} [domyślnie: {pytanie.domyslna}]"


def linia_tak_nie(pytanie: Pytanie) -> str:
    """Pytanie tak/nie razem z klamrą akceptowanych odpowiedzi; WIELKA litera to sam Enter.

    Klamra jest tutaj, a nie w pytającym, bo to jest zdanie do operatora — `ui/texts.py`
    pisze zdania, `ui/prompts.py` je zadaje. Bez niej operator nie ma skąd wiedzieć, że Enter
    coś znaczy, ani co wolno wpisać (zgłoszenie operatora, 2026-09-20)."""
    klamra = "T/n" if pytanie.domyslna == "tak" else "t/N"
    return f"{pytanie.tresc} [{klamra}]"


def pytanie_zgody(*, masowy: bool) -> Pytanie:
    """Pytanie po tabeli kosztów. Przy przebiegu masowym Enter znaczy „nie” (ADR-0008 §10)."""
    return Pytanie(
        tresc="Pobrać? To jest zgoda na ten przebieg w tej sesji." if masowy else "Pobrać?",
        rodzaj="tak_nie",
        domyslna="nie" if masowy else "tak",
    )


def pytanie_poszerzenia(kryteria: Criteria) -> Pytanie:
    """Zero kandydatów → wybór poszerzenia zamiast ślepej uliczki (ADR-0008 Z-10)."""
    opcje = [
        Opcja(pole, f"Spróbuj bez pola „{ETYKIETY[pole]}”: {kandydat.describe()}")
        for pole, kandydat in kryteria.poszerzenia()
    ]
    opcje.append(Opcja(WROC, "Wróć do menu"))
    return Pytanie(
        tresc="Kanał nie zwrócił żadnego orzeczenia. Co dalej?",
        opcje=tuple(opcje),
        domyslna=opcje[0].klucz,
    )


def pytanie_wznowienia(przebiegi: Sequence[tuple[str, str]]) -> Pytanie:
    """`przebiegi` = (run_id, etykieta zakresu) — etykieta z bazy, więc idzie przez neutralizator
    pytającego (reguła 10), a nie jest tu formatowana w nic, co terminal mógłby zinterpretować."""
    return Pytanie(
        tresc="Który przebieg wznowić?",
        opcje=(
            *(Opcja(run_id, f"{run_id} — {etykieta}") for run_id, etykieta in przebiegi),
            Opcja(WROC, "Wróć do menu"),
        ),
        domyslna=przebiegi[0][0] if przebiegi else WROC,
    )


def niepoprawne(powod: str) -> str:
    return f"Tego nie da się użyć: {powod}. Spróbuj jeszcze raz albo zostaw puste, żeby wrócić."


def blad_akcji(powod: str) -> str:
    return f"Nie udało się: {powod}. Wracam do menu — nic nie zostało utracone."


PRZERWANO_PYTANIE = "Przerwano pytanie — wracam do menu; nic nie zostało pobrane ani zapisane."
