"""Sonda fazy 0 — jednorazowe pomiary źródeł, uruchamiane ręcznie, pojedynczymi odczytami.

Zgody właściciela wymaga **przebieg masowy i pomiar tempa** (audyt 13.2 pkt 4); sonda nie
wykonuje ani jednego, ani drugiego, więc jej nie wymaga — zostawia natomiast wiersz w dzienniku
żądań za każdy odczyt i to jest mechaniczna postać tamtej reguły (architektura 4.1 i 5.2,
gdzie stoi wprost: „flagi `--zgoda` nie ma"). Brzmienie „po zgodzie właściciela", które stało
w tej linii do 2026-09-17, rozmywało granicę prawną do stylistycznej.

Skrypty sondujące mieszkają tutaj, a **nie w pakiecie**, i to jest reguła z audytu (sekcja 9,
faza 0): przed bramką wyboru kanału `source/` nie powstaje, bo nie wiadomo, co miałoby
implementować. Te pliki mają zniknąć albo zamienić się w adapter, gdy bramka padnie.

Ten plik jest **dyspozytorem**: spis pomiarów, wejście programu i pomiar 3 (Atlas), który nie
dostał jeszcze własnego pliku. Reszta stoi obok, po jednym pliku na kanał — `pomiar_saos.py`,
`pomiar_uzp.py`, `pomiar_licencje.py` — a środowisko wspólne (ścieżki, tempa, fabryki zegara,
klienta, limitera i kroniki, jedno żądanie) w `zadanie.py`. Dług 1 428 linii w jednym pliku,
zapisany 2026-09-17 z terminem „w dniu, w którym sonda zamieni się w adapter", został spłacony
wcześniej, 2026-09-18: ślad przebiegu poszedł do `kio_tool/logbook.py`, ocena kształtu do
`kio_tool/ksztalt.py`, głos limitera do `kio_tool/console.py`, a parser `Retry-After` do
właściciela protokołu w `kio_tool/httpclient.py`.

Trzy rzeczy, które ta sonda robi inaczej niż zwykły skrypt jednorazowy, i każda z powodem:

1. **Wychodzi przez bramkę wyjścia pakietu**, czyli przez `build_http_client`. Reguła 11
   w brzmieniu z ADR-0003 obejmuje `scripts/` wprost, z uzasadnieniem: sonda niesie ten sam
   ruch co narzędzie, więc obowiązuje ją ta sama polityka. Skan AST w
   `tests/test_boundaries.py` to egzekwuje.
2. **Trzyma tempo przez `RateLimiter`**, choć wysyła pojedyncze żądania. Powód jest
   praktyczny: sonda `--kontrakt` ma się dać uruchomić z harmonogramu, a wtedy „pojedyncze
   żądanie" przestaje być pojedyncze.
3. **Zapisuje surową odpowiedź na dysk**, zanim cokolwiek z niej wyciągnie. Odpowiedź
   z datą w nazwie jest zalążkiem złotego pliku z reguły 17; parser, który powstanie później,
   ma się o co oprzeć, a przeglądający ma co obejrzeć okiem.

Utwardzenie z 2026-09-17 — pięć własności, których pierwsza wersja nie miała, a każda
zmienia to, ile pomiar będzie znaczył:

4. **Ocena kształtu odpowiedzi.** Reguła 17 wymaga od adaptera `SourceContractBroken` przy
   „status zgodny, kształt niezgodny", i ma za sobą datę: między majem a lipcem 2026 cudzy
   kolektor przez dwa miesiące zwracał `total=0` ze statusem 200. Sonda tej własności nie
   miała, więc strona bot-checka z kodem 200 wypisałaby się jako sukces — czyli cisza
   w jedynym miejscu, gdzie cokolwiek dziś wychodzi na zewnątrz (zasada 7.2 i 7.3). Każde
   żądanie niesie teraz oczekiwany kształt **razem ze źródłem tego oczekiwania**, bo
   „kontrakt z drugiej ręki" i „własny odczyt" to dwa różne statusy dowodowe.
5. **Kontrola przy odmowie.** Pomiar 1 był wart dokładnie tyle, ile jego kontrola
   (`ftp.gnu.org` z tej samej maszyny w tej samej minucie). Odmowa bez kontroli nie
   rozróżnia „punkt końcowy odmawia" od „host odmawia wszystkiemu", a to są dwie różne
   architektury i dwie różne rozmowy z prawnikiem. Przy UZP kontrola idzie **przed**
   ekspozycją: znany-dobry odczyt pierwszy, nieznany POST po nim — inaczej pierwsza odmowa
   skaziłaby kontrolę.
6. **Zatrzymanie przy odmowie.** „Narzędzie nie omija zabezpieczeń" (audyt 12, art. 267 § 1
   k.k.) znaczy w praktyce: gdy kontrola wraca odmową albo kształtem nie do poznania,
   pozostałe żądania grupy **nie idą**.
7. **Dowód się nie nadpisuje.** Nazwa pliku z dokładnością do dnia gubiła pierwszą
   odpowiedź przy dwóch przebiegach tego samego dnia — a przy sprzecznych nazwach parametrów
   dat w SAOS to jest scenariusz podstawowy, nie skrajny. Konwencja `docs/decisions.md` mówi
   dokładnie odwrotnie: „wpis nie jest usuwany — dopisuje się nowy".
8. **SHA-256 odpowiedzi i dziennik żądań.** Zdanie „zmierzone {data}, N żądań" wskazywało na
   plik spoza historii (`scripts/out/` jest w `.gitignore`), więc nie było czym go związać
   z bajtami. Skrót wiąże, a `docs/dziennik_zadan.md` jest tym, czego wymaga reguła zgody:
   „pojedynczy odczyt diagnostyczny bez zgody, zawsze z wpisem w dzienniku" (architektura
   4.1). Do fazy 1 zastępuje tabelę `requests_log` i ma jej kolumny.

Uruchomienie wymaga adresu kontaktowego w `KIO_TOOL_CONTACT` — `config.user_agent()` odmawia
bez niego i to jest zamierzone (reguła 16). Klucz Atlasu w `KIO_TOOL_ATLAS_KEY` jest
opcjonalny, ale poziom dostępu wchodzi do wyniku pomiaru: „pełny tekst" zmierzony bez klucza
odpowiada na inne pytanie niż zadane.

    set KIO_TOOL_CONTACT=imie.nazwisko@example.org
    .venv\\Scripts\\python.exe scripts\\sonda.py --lista
    .venv\\Scripts\\python.exe scripts\\sonda.py saos-dump
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable

# Moduły obok, nie w pakiecie: `scripts/` nie jest pakietem i nie ma nim być. Importy działają
# przy uruchomieniu udokumentowanym w nagłówku (`python scripts\\sonda.py …`), bo katalog
# skryptu wchodzi wtedy na `sys.path`; testom dokłada tę ścieżkę `tests/conftest.py`. Dla
# `ruff` wyglądają jak zależność zewnętrzna i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import ksztalty
import zadanie
from pomiar_licencje import pomiar_licencje
from pomiar_saos import pomiar_saos
from pomiar_uzp import pomiar_stabilnosc, pomiar_uzp

from kio_tool.config import ATLAS_HOSTS, register_secret, user_agent
from kio_tool.errors import KioError
from kio_tool.httpclient import powod_odrzucenia_segmentu
from kio_tool.logbook import Kronika, Wynik, niewyslany, zapisz_podsumowanie

ATLAS_KEY_ENV = "KIO_TOOL_ATLAS_KEY"
"""Klucz `X-Api-Key` pośrednika. Nieobecny znaczy „mierzymy poziom anonimowy" — i tak ma być
zapisane, bo limity (1500/dobę/IP wobec 5000/konto) i zakres pól mogą się różnić."""

ATLAS_ADRES_LISTY = "https://atlasprzetargow.pl/api/kio"
ATLAS_ADRES_DOKUMENTU = "https://atlasprzetargow.pl/api/kio/{slug}"
ATLAS_POLE_LISTY = "data"
ATLAS_POLE_SLUG = "slug"
ATLAS_REKORDOW_NA_STRONE = 100
"""Punkty i pola Atlasu z dokumentacji odczytanej 2026-09-18 (`/dokumentacja-api`, strona
„ostatnia aktualizacja: 10 września 2026"): lista pod `GET /api/kio` zwraca tablicę `data[]`
z polem `slug`, a `GET /api/kio/{slug}` — „pełną treść orzeczenia z metadanymi".

`per_page=100` jest maksimum z dokumentacji. Ten sam koszt w żądaniach co `per_page=5`,
a sto rekordów daje materiał do pomiaru 17 (postaci sygnatur w zbiorze) bez dodatkowego ruchu
do cudzego serwisu — wejście ADR-0001 za darmo, zamiast osobnego pomiaru.
"""

# Alfabet sluga i zakaz segmentów kropkowych mieszkały tu do etapu III (2026-09-18) jako
# `WZOR_SLUGA` i `SEGMENTY_KROPKOWE`. Przeniesione do `kio_tool/httpclient.py` razem z powodami:
# adapter Atlasu wstawia ten sam slug do tego samego adresu, a sonda i adapter mają sprawdzać go
# **jedną** funkcją (`powod_odrzucenia_segmentu`), nie dwiema kopiami tej samej reguły.


# --- pomiar 3: Atlas ----------------------------------------------------------------------


def slug_pierwszego_rekordu(tresc: bytes) -> tuple[str | None, str]:
    """Slug pierwszego rekordu listy albo powód, dla którego adres dokumentu nie ma z czego powstać.

    Czysta funkcja: dostaje bajty zapisane po pierwszym żądaniu pomiaru 3a, zwraca `(slug, "")`
    albo `(None, powód)`. Powód jest **wynikiem pomiaru** o kształcie listy, nie awarią: lista
    bez pola `slug` mówi, że kontrakt z dokumentacji nie zgadza się z tym, co przyszło.

    Slug odrzucony przez `httpclient.powod_odrzucenia_segmentu` nie trafia ani do adresu, ani
    na ekran — powód niesie jego długość, nie treść, bo to jest obcy napis, którego postać
    właśnie została zakwestionowana.
    """
    try:
        dane = json.loads(tresc)
    except (json.JSONDecodeError, UnicodeDecodeError) as blad:
        return None, f"lista nie jest JSON-em ({type(blad).__name__})"
    lista = dane.get(ATLAS_POLE_LISTY) if isinstance(dane, dict) else None
    if not isinstance(lista, list) or not lista:
        return None, f"lista nie niesie niepustej tablicy `{ATLAS_POLE_LISTY}`"
    pierwszy = lista[0]
    slug = pierwszy.get(ATLAS_POLE_SLUG) if isinstance(pierwszy, dict) else None
    if not isinstance(slug, str) or not slug:
        return None, f"pierwszy rekord listy nie niesie pola `{ATLAS_POLE_SLUG}`"
    powod = powod_odrzucenia_segmentu(slug)
    if powod:
        return None, f"pole `{ATLAS_POLE_SLUG}` {powod}"
    return slug, ""


def pomiar_atlas(ua: str, kronika: Kronika | None = None) -> list[Wynik]:
    """3a: czy pośrednik naprawdę zwraca pełny tekst, i od kiedy sięga zbiór. Dwa żądania.

    Do 2026-09-18 pomiar wołał wyłącznie listę `/api/kio` — punkt, który z definicji niesie
    skróty — a jego docstring deklarował odpowiedź na pytanie o pełny tekst. Pełną treść
    niesie `GET /api/kio/{slug}` (dokumentacja odczytana 2026-09-18) i to jest punkt, od
    którego zależy `fetch` adaptera; pomiar, na którym stoi wybór pierwszego kanału, nie
    dotykał go wcale (przegląd architektoniczny 2026-09-18, F-1).

    Kolejność: lista pierwsza, bo z niej pochodzi slug pierwszego rekordu — adres dokumentu
    jest odczytany z odpowiedzi, nie zgadnięty. `sort=oldest` odpowiada przy okazji na pytanie,
    którego nikt nie zapisał jako pomiaru: **od którego rocznika sięga zbiór pośrednika** —
    wynik ma trafić do `docs/decisions.md` osobno, a nie jako uwaga do pomiaru 3. Rozmiar
    strony i jego powód stoją przy `ATLAS_REKORDOW_NA_STRONE`.

    Odmowa albo kształt nie do poznania na liście zatrzymują grupę: idzie kontrola hosta,
    dokument nie idzie i zostaje na liście jako wpis niewysłany. Niezgodny kształt **dokumentu**
    jest natomiast wynikiem, nie odmową — host już odpowiedział listą, więc kontrola nie ma
    czego rozstrzygać.

    Druga część pomiaru 3 — opóźnienie publikacji (3b) — to obserwacja w czasie, nie sonda.
    Poziom dostępu jest częścią wyniku, nie szczegółem uruchomienia: limity i zakres pól mogą
    zależeć od klucza, więc „pełny tekst" zmierzony anonimowo odpowiada na inne pytanie niż
    „pełny tekst" zmierzony kluczem.
    """
    kronika = kronika or zadanie.kronika()
    limiter = zadanie.limiter(zadanie.ODSTEP_POSREDNIK_S)
    klucz = (os.environ.get(ATLAS_KEY_ENV) or "").strip()
    naglowki: dict[str, str] = {}
    if klucz:
        register_secret(klucz)  # odmawia przy kluczu krótszym niż próg maskowania
        naglowki["X-Api-Key"] = klucz
    poziom = "poziom: z kluczem" if klucz else f"poziom: anonimowy (brak {ATLAS_KEY_ENV})"
    wyniki: list[Wynik] = []
    with zadanie.klient(ua, ATLAS_HOSTS) as klient:
        lista = zadanie.wykonaj(
            klient,
            limiter,
            kronika,
            nazwa="atlas_3a_lista",
            metoda="GET",
            adres=ATLAS_ADRES_LISTY,
            rozszerzenie="json",
            ksztalt=ksztalty.ATLAS_LISTA,
            uwaga=poziom,
            headers=naglowki,
            params={"per_page": ATLAS_REKORDOW_NA_STRONE, "page": 1, "sort": "oldest"},
        )
        wyniki.append(lista)
        if lista.odmowa:
            wyniki.append(
                zadanie.kontrola_hosta(
                    klient,
                    limiter,
                    kronika,
                    nazwa="atlas_kontrola_hosta",
                    korzen="https://atlasprzetargow.pl/",
                )
            )
            wyniki.append(
                kronika.zanotuj(
                    niewyslany(
                        "atlas_3a_dokument",
                        "GET",
                        "pomiar przerwany: lista wróciła odmową albo kształtem nie do poznania "
                        "— odczyt dokumentu nie poszedł. Narzędzie nie omija zabezpieczeń "
                        "(audyt 12)",
                    )
                )
            )
            return wyniki
        zapisane = b"" if lista.plik is None else lista.plik.read_bytes()
        slug, powod = slug_pierwszego_rekordu(zapisane)
        if slug is None:
            wyniki.append(
                kronika.zanotuj(
                    niewyslany(
                        "atlas_3a_dokument",
                        "GET",
                        f"odczyt dokumentu nie poszedł: {powod}. To jest wynik pomiaru "
                        "o kształcie listy, nie awaria",
                    )
                )
            )
            return wyniki
        wyniki.append(
            zadanie.wykonaj(
                klient,
                limiter,
                kronika,
                nazwa="atlas_3a_dokument",
                metoda="GET",
                adres=ATLAS_ADRES_DOKUMENTU.format(slug=slug),
                rozszerzenie="json",
                ksztalt=ksztalty.ATLAS_DOKUMENT,
                uwaga=poziom,
                headers=naglowki,
            )
        )
    return wyniki


POMIARY: dict[str, tuple[str, Callable[[str, Kronika | None], list[Wynik]]]] = {
    "saos-dump": ("2a/2b — Dump API SAOS: dostęp i filtr po organie", pomiar_saos),
    "uzp-getresults": ("4b/16 — własny POST do GetResults i liczniki per organ", pomiar_uzp),
    "atlas": (
        "3a — czy Atlas zwraca pełny tekst (lista i jeden dokument) i od kiedy sięga zbiór",
        pomiar_atlas,
    ),
    "licencje": (
        "23 — czy SAOS i Atlas licencjonują ponowne wykorzystywanie wprost (trzy odczyty)",
        pomiar_licencje,
    ),
    "uzp-stabilnosc": (
        "19 — czy bajty `ContentHtml` są stabilne; wymaga dwóch przebiegów w odstępie doby",
        pomiar_stabilnosc,
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        # Napis widoczny dla operatora jest w tym projekcie normą, nie ozdobą. Brzmienie
        # „wymaga zgody właściciela", które stało tu do 2026-09-17, przeczyło architekturze 5.2
        # („flagi --zgoda nie ma, bo pojedynczy odczyt diagnostyczny zgody nie wymaga") i audytowi
        # 13.2 pkt 4. Rozmywało granicę, która jest prawna, nie stylistyczna: zgody wymaga przebieg
        # masowy i pomiar tempa, a sonda nie wykonuje ani jednego, ani drugiego.
        description=(
            "Sonda fazy 0: pojedyncze odczyty diagnostyczne, każdy z wierszem w dzienniku żądań. "
            "Zgody właściciela wymaga przebieg masowy i pomiar tempa — sonda nie wykonuje żadnego "
            "z nich. Nie startuje bez adresu kontaktowego w KIO_TOOL_CONTACT."
        ),
    )
    parser.add_argument("pomiar", nargs="?", choices=sorted(POMIARY), help="który pomiar wykonać")
    parser.add_argument("--lista", action="store_true", help="wypisz dostępne pomiary i wyjdź")
    args = parser.parse_args(argv)

    if args.lista or not args.pomiar:
        print("Dostępne pomiary:\n")
        for klucz, (opis, _) in sorted(POMIARY.items()):
            print(f"  {klucz:16} {opis}")
        print("\nKażdy wysyła pojedyncze żądania diagnostyczne i zapisuje surowe odpowiedzi.")
        print(
            f"Każde żądanie zostawia wiersz w {zadanie.DZIENNIK.name} — tego wymaga reguła zgody."
        )
        return 0

    # `KioError` deklaruje w docstringu, że komunikat jest przeznaczony dla użytkownika,
    # i niesie `exit_code`. Ślad stosu zamiast komunikatu łamałby oba te zdania naraz:
    # operator zobaczyłby wewnętrzną ścieżkę pliku zamiast zdania, co ma zrobić, a powłoka
    # dostałaby kod 1 zamiast 3 (błąd konfiguracji). Obejmuje też `register_secret`, bo klucz
    # za krótki do zamaskowania nie ma prawa trafić do dziennika w historii repozytorium.
    kronika = zadanie.kronika()
    try:
        ua = user_agent()  # odmawia bez KIO_TOOL_CONTACT — to jest zamierzone (reguła 16)
        opis, funkcja = POMIARY[args.pomiar]

        print(f"Pomiar: {opis}")
        print(f"Tożsamość klienta: {ua}")
        print(f"Moment rozpoczęcia: {kronika.ts}  (run_id: {kronika.run_id})\n")
        # Nagłówek tabeli **przed** przebiegiem, bo wiersze drukują się teraz w chwili
        # powrotu żądania, a nie po całym pomiarze (`Kronika.zanotuj`).
        print(f"{'pomiar':26} {'met.':5} {'status':>6} {'rozmiar':>11}  {'czas':>5}  sha256  plik")
        print("-" * 96)

        wyniki = funkcja(ua, kronika)
    except (KioError, KeyboardInterrupt) as blad:
        # Rachunek i podsumowanie **także** na ścieżce wyjątku. Przebieg zatrzymany w pół jest
        # momentem, w którym liczba wysłanych żądań jest najtrudniejsza do policzenia ręką —
        # i jednocześnie momentem, w którym `decisions.md` wymaga jej co do sztuki. Materiał
        # jest: `Kronika` zapisała każdy wynik w chwili jego powstania.
        #
        # `KeyboardInterrupt` od przeglądu kodu 2026-09-18: `Ctrl+C` w czasie plastra 300 s po
        # 429 jest scenariuszem realnym, a do tego dnia zostawiał operatora bez rachunku, choć
        # `kronika.zapisane` go niosła. Kod 130 to konwencja powłoki dla przerwania sygnałem.
        poszlo = sum(1 for w in kronika.zapisane if w.wyslane)
        powod = (
            "przerwanie przez operatora (Ctrl+C)" if isinstance(blad, KeyboardInterrupt) else blad
        )
        print(f"\nSonda zatrzymana: {powod}", file=sys.stderr)
        print(f"Żądań wysłanych przed zatrzymaniem: {poszlo}", file=sys.stderr)
        if kronika.zapisane:
            urwane = zapisz_podsumowanie(
                kronika.katalog_wyjscia, args.pomiar, kronika.run_id, kronika.ts, kronika.zapisane
            )
            print(f"Podsumowanie przebiegu urwanego: {urwane.name}", file=sys.stderr)
        print(f"Dziennik żądań: {kronika.dziennik}", file=sys.stderr)
        return blad.exit_code if isinstance(blad, KioError) else 130

    podsumowanie = zapisz_podsumowanie(
        kronika.katalog_wyjscia, args.pomiar, kronika.run_id, kronika.ts, wyniki
    )
    wyslane = sum(1 for w in wyniki if w.wyslane)
    niewyslane = [w.nazwa for w in wyniki if not w.wyslane]

    # Liczba żądań jest wypisana, a nie zostawiona do policzenia z ekranu: konwencja
    # `decisions.md` wymaga dokładnego N, a wiersze pomiarów, które nie poszły, zawyżałyby
    # każde liczenie ręką (przegląd kodu 2026-09-17).
    print(f"\nŻądań wysłanych: {wyslane}")
    if niewyslane:
        print(f"Pomiary niewysłane (przebieg zatrzymany): {', '.join(niewyslane)}")
    print(f"Surowe odpowiedzi: {kronika.katalog_wyjscia}")
    print(f"Podsumowanie: {podsumowanie.name}")
    print(f"Dziennik żądań: {kronika.dziennik}")
    print(
        f"Wynik przepisz do docs/decisions.md w formacie „zmierzone {kronika.ts[:10]}, "
        f"{wyslane} żądań”."
    )
    # Kod 1 przy przebiegu zatrzymanym: wszystkie zaplanowane żądania poszły albo nie, i to
    # jest rozróżnienie warte kodu wyjścia. Odmowa **zmierzona** (403 na każde z trzech żądań)
    # jest wynikiem, nie awarią, i kończy się zerem — zatrzymanie w połowie nie.
    return 1 if niewyslane else 0


if __name__ == "__main__":
    sys.exit(main())
