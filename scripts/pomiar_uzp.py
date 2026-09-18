"""Pomiary UZP: 4b/16 (własny POST do `GetResults` i liczniki) oraz 19 (stabilność bajtów).

Dwa pomiary jednego hosta w jednym module. 4b/16 jest wejściem bramki fazy 0 i jedynym
pomiarem, który zamienia „potwierdzone z drugiej ręki" na „potwierdzone"; 19 jest wejściem
ADR-0001 (klucz tożsamości dokumentu) i kosztuje kalendarz, nie pracę — dwa przebiegi w odstępie
doby, między którymi jedynym nośnikiem jest dziennik żądań. Oba jadą przez `zadanie`: zegar,
klient, limiter i kronika pochodzą z tamtejszych fabryk. Do 2026-09-18 w `sonda.py`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

import ksztalty
import zadanie

from kio_tool.config import UZP_HOSTS, mask_tokens
from kio_tool.logbook import KODY_ODMOWY, Kronika, Wynik, niewyslany, skrot_dziennika

# --- pomiar 4b i 16: kontrakt wyszukiwarki UZP --------------------------------------------


def pomiar_uzp(ua: str, kronika: Kronika | None = None) -> list[Wynik]:
    """4b: własny `POST /Home/GetResults`. 16: liczniki `#resultCounts` przy pustej frazie.

    Kontrakt tego wywołania stoi dziś na **dwóch niezależnych cudzych kolektorach** i na
    własnych odczytach GET — nikt w tym projekcie nie wysłał tu POST-a. To jest jedyny pomiar,
    który zamienia „potwierdzone z drugiej ręki" na „potwierdzone".

    Kolejność jest tu odwrotna niż w pierwszej wersji i to jest cała różnica między kontrolą
    a jej brakiem. Znany-dobry `GET Details/9620` (odczytany 2026-09-14 ze statusem 200) idzie
    **pierwszy**: jeśli wróci odmową albo kształtem nie do poznania, wiadomo, że serwis nie
    rozmawia z tym klientem, i nieznany POST już nie idzie. Przy odwrotnej kolejności pierwsza
    odmowa skaziłaby kontrolę — nie dałoby się odróżnić „POST jest niemile widziany" od
    „klient jest niemile widziany".
    """
    kronika = kronika or zadanie.kronika()
    limiter = zadanie.limiter(zadanie.ODSTEP_UZP_S)
    wyniki: list[Wynik] = []
    naglowki = {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    getresults = "https://orzeczenia.uzp.gov.pl/Home/GetResults"
    with zadanie.klient(ua, UZP_HOSTS) as klient:
        kontrola = zadanie.wykonaj(
            klient,
            limiter,
            kronika,
            nazwa="uzp_kontrola_details_9620",
            metoda="GET",
            adres="https://orzeczenia.uzp.gov.pl/Home/Details/9620",
            rozszerzenie="html",
            ksztalt=ksztalty.UZP_DETAILS,
            uwaga="kontrola przed ekspozycją: znany-dobry odczyt z 2026-09-14",
        )
        wyniki.append(kontrola)
        powod = zadanie.zatrzymaj_po_odmowie(kontrola)
        if powod is not None:
            for nazwa in ("uzp_4b_getresults", "uzp_16_resultcounts"):
                wyniki.append(
                    kronika.zanotuj(
                        niewyslany(
                            nazwa,
                            "POST",
                            f"pomiar przerwany: {powod}. Narzędzie nie omija zabezpieczeń "
                            "(audyt 12) — dalsze żądania nie poszły",
                        )
                    )
                )
            return wyniki

        wyniki.append(
            zadanie.wykonaj(
                klient,
                limiter,
                kronika,
                nazwa="uzp_4b_getresults",
                metoda="POST",
                adres=getresults,
                rozszerzenie="html",
                ksztalt=ksztalty.UZP_WYNIKI,
                headers=naglowki,
                data={
                    "Phrase": "",
                    "Kind": "KIO",
                    "Dt": "01-09-2025 - 30-09-2025",
                    "Pg": "1",
                    "Srt": "date_desc",
                    "Fle": "0",
                    "SCnt": "0",
                    "CountStats": "True",
                },
            )
        )
        if wyniki[-1].odmowa:
            wyniki.append(
                kronika.zanotuj(
                    niewyslany(
                        "uzp_16_resultcounts",
                        "POST",
                        "pomiar przerwany: `uzp_4b_getresults` wrócił odmową albo kształtem "
                        "nie do poznania — liczniki per organ nie poszły",
                    )
                )
            )
            return wyniki
        wyniki.append(
            zadanie.wykonaj(
                klient,
                limiter,
                kronika,
                nazwa="uzp_16_resultcounts",
                metoda="POST",
                adres=getresults,
                rozszerzenie="html",
                ksztalt=ksztalty.UZP_WYNIKI,
                headers=naglowki,
                data={
                    "Phrase": "",
                    "Kind": "",
                    "Pg": "1",
                    "Srt": "date_desc",
                    "Fle": "0",
                    "SCnt": "0",
                    "CountStats": "True",
                },
            )
        )
    return wyniki


# --- pomiar 19: czy bajty treści są stabilne między pobraniami -----------------------------

UZP_CONTENT_ID = "18946"
"""Dokument, którego `ContentHtml` ma własny odczyt z datą (architektura 7, 2026-09-14).

Identyfikator jest **stały i to jest cały pomiar**. Wylosowany przy każdym uruchomieniu
mierzyłby różnicę między dokumentami, a nie różnicę między pobraniami tego samego dokumentu —
czyli odpowiadałby na inne pytanie niż zadane, wyglądając tak samo.
"""

ODSTEP_POMIARU_19_H = 24.0
"""Doba między odczytami. Poniżej tej granicy zgodność skrótów nie znaczy „stabilne" — znaczy
tylko „nic się nie zdążyło zmienić", a to jest inne zdanie."""

SEKUND_W_GODZINIE = 3600.0


@dataclass(frozen=True)
class WczesniejszyOdczyt:
    """Wiersz dziennika dotyczący tego samego adresu: kiedy i z jakim skrótem."""

    ts: str
    skrot: str


def wczesniejsze_odczyty(adres: str, *, dziennik: Path) -> list[WczesniejszyOdczyt]:
    """Wiersze dziennika dla tego samego adresu, najstarszy pierwszy. **Zero żądań.**

    Dziennik jest jedynym zapisem odczytów, który leży w historii repozytorium — pełne skróty
    trafiają do `scripts/out/`, a ten katalog jest w `.gitignore`. Porównanie międzyprzebiegowe
    musi więc czytać dziennik, nawet jeśli niesie skrót przycięty do szesnastu znaków: to jest
    64 bity na rozróżnienie dwóch pobrań tego samego dokumentu i wystarcza z zapasem.

    Wiersze ręczne czyta tak samo jak maszynowe, bo odczyt ręczny tego samego adresu jest
    dokładnie tym samym dowodem.

    **Kolejność wynika ze znaczników, nie z układu pliku** (poprawka 2026-09-17). Dopóki pisze
    sama sonda, to jest to samo — dopisuje na końcu, rosnąco w czasie. Przestaje być tym samym
    przy pierwszym wpisie ręcznym, bo nagłówek dziennika ma **dwie** tabele i „Wpisy ręczne"
    stoi fizycznie nad maszynową. Wpis ręczny z dziś lądował więc przed maszynowymi sprzed
    tygodnia, a `ocen_stabilnosc` bierze ostatni element jako poprzedni odczyt: porównanie szło
    z odczytem nie tym, co ostatni, a `_odstep_godzin` zwracał liczbę ujemną („minęło -168.0 h").
    Sortowanie po napisie wystarcza, bo `utc_iso` daje ISO-8601 w stałej strefie — postać
    leksykograficznie rosnąca razem z czasem.
    """
    # Ścieżka jawna, nie global (od 2026-09-18): pomiar czyta ten sam plik, do którego pisze
    # jego kronika, i to widać w wywołaniu, a nie w tym, który moduł akurat trzyma stałą.
    if not dziennik.exists():
        return []
    szukany = mask_tokens(adres)
    znalezione: list[WczesniejszyOdczyt] = []
    for linia in dziennik.read_text(encoding="utf-8").splitlines():
        if not linia.startswith("|"):
            continue
        pola = [czesc.strip() for czesc in linia.strip().strip("|").split("|")]
        if len(pola) < 8 or pola[0] in {"run_id", "---"} or set(pola[0]) <= {"-"}:
            continue
        if pola[3].strip("`") != szukany:
            continue
        skrot = pola[7].strip("`")
        if skrot and skrot != "—":
            znalezione.append(WczesniejszyOdczyt(ts=pola[1], skrot=skrot_dziennika(skrot)))
    return sorted(znalezione, key=lambda odczyt: odczyt.ts)


def ocen_stabilnosc(teraz: Wynik, wczesniej: Sequence[WczesniejszyOdczyt], *, ts_teraz: str) -> str:
    """Werdykt pomiaru 19 jako zdanie dla operatora. Funkcja czysta — bez zegara i bez sieci.

    Cisza jest usterką (zasada 7.2), a pomiar rozłożony na dwa przebiegi w odstępie doby jest
    najłatwiejszym miejscem na ciszę w całym planie: operator, który musiałby porównać skróty
    ręką, porówna je albo nie, a wynik „nie porównał" wygląda identycznie jak „zgodne".

    **Odpowiedź, która nie jest treścią orzeczenia, nie jest materiałem tego pomiaru**
    (poprawka 2026-09-17). Pierwsza wersja odrzucała dwa stany — pomiar niewysłany i wynik bez
    skrótu — a odmowa 403 i strona weryfikacji przeglądarki ze statusem 200 przechodziły przez
    oba sita: mają bajty, mają skrót, mają status. Gorzej: statyczny szablon błędu jest **bitowo
    stabilniejszy** niż treść orzeczenia, więc dwa zablokowane przebiegi w odstępie doby dawały
    werdykt „bajty stabilne — `(doc_id, content_sha256)` może być kluczem". Zdanie prawdziwie
    wyglądające i fałszywe, wydane na wejście ADR-0001, czyli na decyzję chronioną przed miną 1.
    `Wynik.odmowa` łączy brak odpowiedzi, `KODY_ODMOWY` i niezgodny kształt dokładnie po to.
    """
    if not teraz.wyslane or teraz.sha256 is None:
        return "pomiar nie doszedł do skutku — zegar doby nie ruszył"
    if teraz.odmowa:
        powod = (
            f"status {teraz.status}"
            if teraz.status in KODY_ODMOWY
            else "kształt nie do poznania — to nie jest treść orzeczenia"
        )
        return (
            f"odpowiedź nie nadaje się do porównania ({powod}), więc zegar doby **nie ruszył**. "
            "Szablon odmowy bywa bitowo niezmienny między pobraniami częściej niż treść "
            "orzeczenia, więc porównanie go odpowiadałoby na inne pytanie niż pomiar 19. "
            "Powtórz po ustaniu przyczyny."
        )
    skrot_teraz = skrot_dziennika(teraz.sha256)
    if not wczesniej:
        return (
            "pierwszy odczyt tego dokumentu — zegar ruszył. Uruchom ten sam pomiar ponownie "
            f"po co najmniej {ODSTEP_POMIARU_19_H:.0f} h; dopiero drugi odczyt coś rozstrzyga."
        )
    poprzedni = wczesniej[-1]
    odstep_h = _odstep_godzin(poprzedni.ts, ts_teraz)
    zgodne = poprzedni.skrot == skrot_teraz
    if odstep_h is None:
        # Zgodność skrótów przy odstępie **nieznanym** nie znaczy „stabilne przez dobę" — może
        # znaczyć „ten sam plik pobrany dwa razy w ciągu pięciu minut". Do 2026-09-17 ta gałąź
        # ustawiała tylko opis i spadała do pełnego werdyktu pozytywnego razem z instrukcją
        # przepisania go do `decisions.md`, gdzie „wpis nie jest usuwany" — czyli odstęp znany
        # i za krótki blokował rozstrzygnięcie, a odstęp nieznany dawał najmocniejsze możliwe.
        #
        # Asymetria jest tu treścią, nie ostrożnością: **niezgodność** rozstrzyga przy każdym
        # odstępie (różne bajty to różne bajty), **zgodność** wymaga wiedzy, ile czasu minęło.
        if not zgodne:
            return (
                f"**bajty NIESTABILNE** mimo nieznanego odstępu: było `{poprzedni.skrot}` "
                f"{poprzedni.ts}, jest `{skrot_teraz}`. Odstęp nie jest tu potrzebny — różne "
                "bajty tego samego dokumentu rozstrzygają same. Wejście ADR-0001."
            )
        return (
            f"skróty zgodne, ale **odstęp nieznany** (znacznik `{poprzedni.ts}` nie do "
            "odczytania), więc pomiar nie rozstrzyga: zgodność przy pięciu minutach znaczy co "
            "innego niż przy dobie. Popraw znacznik w dzienniku albo powtórz pomiar tak, żeby "
            "poprzednim odczytem był wpis maszynowy."
        )
    if odstep_h < ODSTEP_POMIARU_19_H:
        return (
            f"za wcześnie: od poprzedniego odczytu minęło {odstep_h:.1f} h, a pomiar wymaga "
            f"{ODSTEP_POMIARU_19_H:.0f} h. Skróty są "
            + ("zgodne" if zgodne else "**różne**")
            + ", ale przy tym odstępie to nie jest odpowiedź na pytanie pomiaru 19."
            + (
                ""
                if zgodne
                else " Różnica przy krótkim odstępie jest jednak wynikiem sama w sobie: "
                "bajty zmieniły się w ciągu godzin."
            )
        )
    opis_odstepu = f"odstęp {odstep_h:.1f} h"
    if zgodne:
        return (
            f"**bajty stabilne** ({opis_odstepu}): skrót `{skrot_teraz}` taki sam jak "
            f"{poprzedni.ts}. `(doc_id, content_sha256)` może być kluczem — wpisz to do "
            "`docs/decisions.md` jako wejście ADR-0001."
        )
    return (
        f"**bajty NIESTABILNE** ({opis_odstepu}): było `{poprzedni.skrot}` {poprzedni.ts}, "
        f"jest `{skrot_teraz}`. Ta sama treść pobrana dwa razy daje dwie wersje, więc "
        "`content_sha256` nie jest kluczem tożsamości — to jest mina 1 w nowym przebraniu "
        "i wejście ADR-0001."
    )


def _odstep_godzin(wczesniej_ts: str, pozniej_ts: str) -> float | None:
    """Odstęp w godzinach między dwoma znacznikami `utc_iso` albo `None`, gdy nie do odczytania.

    Znacznik z dziennika jest napisem z pliku, a nie liczbą z zegara — czyli treścią, którą
    ktoś mógł wpisać ręką przy wpisie ręcznym. Nieparsowalny znacznik nie ma prawa wywrócić
    pomiaru; ma dać werdykt „odstęp nieznany".

    Pierwsza wersja obejmowała o jedną klasę mniej, niż obiecywała, i był to błąd niewidoczny
    z lektury: `datetime.fromisoformat("2026-09-14")` **nie jest błędem** — zwraca poprawną datę
    **bez strefy**, a odejmowanie jej od znacznika przebiegu, który strefę ma, kończy się
    `TypeError`, którego `except ValueError` nie łapie. Znacznik w tej postaci jest scenariuszem
    podstawowym, nie skrajnym: nagłówek dziennika każe wpisywać `run_id` w postaci
    `recznie-RRRRMMDD`, więc ręka wypełniająca sąsiednią kolumnę ma wszelkie powody napisać samą
    datę. Awaria padała **po** żądaniu i przed `zapisz_podsumowanie`, a każdy kolejny przebieg
    czytał ten sam wiersz — pomiar byłby zablokowany na zawsze.

    Data bez strefy jest odrzucana, a nie domyślana na UTC: różnica dwóch godzin przy progu doby
    zmienia werdykt, a zgadywanie strefy cudzego wpisu produkowałoby liczbę bez pokrycia.
    """
    try:
        a = datetime.fromisoformat(wczesniej_ts.replace("Z", "+00:00"))
        b = datetime.fromisoformat(pozniej_ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if a.tzinfo is None or b.tzinfo is None:
        return None
    return (b - a).total_seconds() / SEKUND_W_GODZINIE


def pomiar_stabilnosc(ua: str, kronika: Kronika | None = None) -> list[Wynik]:
    """19: czy `ContentHtml` jest bitowo stabilny między pobraniami. Jedno żądanie na przebieg.

    Pomiar jest wejściem ADR-0001, a nie bramki fazy 0 — i ma osobną komendę właśnie dlatego,
    że jego kosztem jest **kalendarz, nie praca**: wymaga doby odstępu. ADR-0004 sekcja 3
    obiecuje, że pomiary 7 i 19 „startują razem z pierwszym przebiegiem sondy"; bez własnej
    komendy ta obietnica nie miała czym się wykonać, a zegar doby ruszyłby dopiero wtedy, gdy
    ktoś sobie o nim przypomni. ADR-0001 musi paść przed pierwszym zapisem do bazy, więc dzień
    zwłoki tutaj jest dniem zwłoki fazy 1.

    Punkt końcowy ma własny odczyt z datą (architektura 7), więc to nie jest ekspozycja
    nieznanego wywołania i nie potrzebuje kontroli przed sobą — inaczej niż POST z pomiaru 4b.
    """
    kronika = kronika or zadanie.kronika()
    limiter = zadanie.limiter(zadanie.ODSTEP_UZP_S)
    adres = f"https://orzeczenia.uzp.gov.pl/Home/ContentHtml/{UZP_CONTENT_ID}"
    # Odczyt wstecz **przed** żądaniem, a nie po nim: `Kronika.zanotuj` dopisuje wiersz do
    # dziennika w chwili powrotu odpowiedzi, więc po żądaniu bieżący przebieg zobaczyłby sam
    # siebie jako „poprzedni odczyt" i wypisał zgodność skrótu z samym sobą przy odstępie zera.
    poprzednie = wczesniejsze_odczyty(adres, dziennik=kronika.dziennik)
    with zadanie.klient(ua, UZP_HOSTS) as klient:
        wynik = zadanie.wykonaj(
            klient,
            limiter,
            kronika,
            nazwa="uzp_19_contenthtml",
            metoda="GET",
            adres=adres,
            rozszerzenie="html",
            ksztalt=ksztalty.UZP_CONTENT,
            params={"Kind": "KIO", "flection": "0"},
            uwaga="pomiar 19: ten sam dokument co poprzednio, dla porównania bajtów",
        )
    werdykt = ocen_stabilnosc(wynik, poprzednie, ts_teraz=kronika.ts)
    print(f"\nPomiar 19 — {werdykt}")
    # Werdykt idzie także do `podsumowanie_*.json`, a nie tylko na ekran (poprawka 2026-09-17).
    # To jest **to zdanie**, które operator przepisuje do `docs/decisions.md`; zostawione
    # wyłącznie w terminalu ginie razem z oknem, a dowód, z którego dałoby się je odtworzyć —
    # dwa skróty w dzienniku — wymaga porównania ręką, czyli tej samej czynności, dla której
    # `ocen_stabilnosc` powstała. Kanałem jest `uwaga`, bo niesie dokładnie „co warto o tym
    # wyniku wiedzieć" i już płynie do podsumowania; nowe pole na `Wynik` opisywałoby parę
    # przebiegów w typie, który opisuje jedno żądanie.
    return [replace(wynik, uwaga="; ".join(filter(None, (wynik.uwaga, f"werdykt: {werdykt}"))))]
