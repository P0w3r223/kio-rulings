"""Sonda fazy 0 — jednorazowe pomiary źródeł, uruchamiane ręcznie, po zgodzie właściciela.

Skrypty sondujące mieszkają tutaj, a **nie w pakiecie**, i to jest reguła z audytu (sekcja 9,
faza 0): przed bramką wyboru kanału `source/` nie powstaje, bo nie wiadomo, co miałoby
implementować. Ten plik ma zniknąć albo zamienić się w adapter, gdy bramka padnie.

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

Uruchomienie wymaga adresu kontaktowego w `KIO_TOOL_CONTACT` — `config.user_agent()` odmawia
bez niego i to jest zamierzone (reguła 16).

    set KIO_TOOL_CONTACT=imie.nazwisko@example.org
    .venv\\Scripts\\python.exe scripts\\sonda.py --lista
    .venv\\Scripts\\python.exe scripts\\sonda.py saos-dump
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from kio_tool.clock import SystemClock, utc_iso
from kio_tool.config import ATLAS_HOSTS, SAOS_HOSTS, UZP_HOSTS, user_agent
from kio_tool.errors import KioError
from kio_tool.httpclient import build_http_client
from kio_tool.ratelimit import InMemoryHistory, RateLimiter

KATALOG_WYJSCIA = Path(__file__).resolve().parent / "out"
"""Surowe odpowiedzi lądują tu, a nie w `tests/examples/`.

Do `tests/examples/` trafiają **po przejrzeniu okiem** i razem z `*.compare.json` — bo reguła
17 mówi o dowodzie przejrzanym przez człowieka, a nie o wszystkim, co wpadło. `scripts/out/`
jest w `.gitignore` właśnie po to, żeby ta granica nie zatarła się przez przypadek.
"""

# Tempo startowe dla UZP. To jest **precedens z dwóch cudzych kolektorów (1 i 2 żąd./s),
# nie pomiar tolerancji serwisu** — pomiar 9 dopiero ma je zmierzyć. Sonda jedzie wolniej
# niż wolniejszy z precedensów, bo pojedynczy odczyt diagnostyczny nie ma powodu się spieszyć.
ODSTEP_UZP_S = 2.0
ODSTEP_POSREDNIK_S = 1.0

LIMIT_CZASU_S = 45.0
"""Dłuższy niż domyślny limit narzędzia: sonda dotyka punktów, których nikt jeszcze nie
zmierzył, a przekroczenie czasu jest tu wynikiem pomiaru, nie awarią do ukrycia."""


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
    uwaga: str = ""

    def wiersz(self) -> str:
        status = "BŁĄD" if self.status is None else str(self.status)
        plik = self.plik.name if self.plik else "—"
        return (
            f"{self.nazwa:28} {self.metoda:5} {status:>6} "
            f"{self.bajtow:>9} B  {self.czas_s:5.2f}s  {plik}"
            + (f"\n{'':28} └─ {self.uwaga}" if self.uwaga else "")
        )


def _zapisz(nazwa: str, tresc: bytes, rozszerzenie: str) -> Path:
    """Zapisuje surową odpowiedź z datą w nazwie — zalążek złotego pliku (reguła 17)."""
    KATALOG_WYJSCIA.mkdir(parents=True, exist_ok=True)
    dzis = datetime.now(tz=UTC).strftime("%Y%m%d")
    sciezka = KATALOG_WYJSCIA / f"{nazwa}_{dzis}.{rozszerzenie}"
    sciezka.write_bytes(tresc)
    return sciezka


def _wykonaj(
    klient: httpx.Client,
    limiter: RateLimiter,
    *,
    nazwa: str,
    metoda: str,
    adres: str,
    rozszerzenie: str,
    **kwargs: object,
) -> Wynik:
    """Jedno żądanie: przez limiter, przez bramkę wyjścia, z zapisem surowej odpowiedzi."""
    limiter.acquire(nazwa)
    zegar = SystemClock()
    start = zegar.monotonic()
    try:
        odpowiedz = klient.request(metoda, adres, **kwargs)  # type: ignore[arg-type]
    except httpx.HTTPError as blad:
        return Wynik(
            nazwa=nazwa,
            metoda=metoda,
            adres=adres,
            status=None,
            bajtow=0,
            czas_s=zegar.monotonic() - start,
            plik=None,
            uwaga=f"{type(blad).__name__}: {blad}",
        )
    czas = zegar.monotonic() - start
    limiter.note_response(
        odpowiedz.status_code,
        retry_after_s=float(odpowiedz.headers["Retry-After"])
        if odpowiedz.headers.get("Retry-After", "").isdigit()
        else None,
    )
    plik = _zapisz(nazwa, odpowiedz.content, rozszerzenie)
    uwaga = ""
    if odpowiedz.is_redirect:
        uwaga = f"przekierowanie → {odpowiedz.headers.get('Location', '?')}"
    return Wynik(
        nazwa=nazwa,
        metoda=metoda,
        adres=adres,
        status=odpowiedz.status_code,
        bajtow=len(odpowiedz.content),
        czas_s=czas,
        plik=plik,
        uwaga=uwaga,
    )


# --- pomiar 2a i 2b: SAOS Dump API -------------------------------------------------------


def pomiar_saos(ua: str) -> list[Wynik]:
    """2a: czy własny klient dostaje się do Dump API. 2b: czy Dump API filtruje po organie.

    Audyt i architektura zgadzają się, że wyszukiwarka SAOS **nie służy** do pobierania bazy —
    mówi to wprost dokumentacja SAOS. Dwa niezależne klienty dostały 403 na `/api/search/*`,
    ale **Dump API nie było testowane przez nikogo**, a to ono jest właściwym punktem.

    Wiki SAOS jest wewnętrznie sprzeczna co do nazw parametrów dat: nagłówek tabeli mówi
    `judgmentDateFrom/To`, a przykład w tej samej sekcji `judgmentStartDate/EndDate`. Sonda
    próbuje **obu** — rozstrzygnie to własne wywołanie, nie lektura.
    """
    limiter = RateLimiter(
        min_spacing_s=ODSTEP_POSREDNIK_S, clock=SystemClock(), history=InMemoryHistory()
    )
    wyniki: list[Wynik] = []
    with build_http_client(user_agent=ua, allowed=SAOS_HOSTS, timeout=LIMIT_CZASU_S) as klient:
        baza = "https://www.saos.org.pl/api/dump/judgments"
        wyniki.append(
            _wykonaj(
                klient,
                limiter,
                nazwa="saos_2a_dump_datefrom",
                metoda="GET",
                adres=baza,
                rozszerzenie="json",
                params={
                    "pageSize": 10,
                    "pageNumber": 0,
                    "judgmentDateFrom": "2018-09-01",
                    "judgmentDateTo": "2018-09-30",
                },
            )
        )
        wyniki.append(
            _wykonaj(
                klient,
                limiter,
                nazwa="saos_2a_dump_startdate",
                metoda="GET",
                adres=baza,
                rozszerzenie="json",
                params={
                    "pageSize": 10,
                    "pageNumber": 0,
                    "judgmentStartDate": "2018-09-01",
                    "judgmentEndDate": "2018-09-30",
                },
            )
        )
        wyniki.append(
            _wykonaj(
                klient,
                limiter,
                nazwa="saos_2b_courttype",
                metoda="GET",
                adres=baza,
                rozszerzenie="json",
                params={
                    "pageSize": 10,
                    "pageNumber": 0,
                    "courtType": "NATIONAL_APPEAL_CHAMBER",
                },
            )
        )
    return wyniki


# --- pomiar 4b i 16: kontrakt wyszukiwarki UZP --------------------------------------------


def pomiar_uzp(ua: str) -> list[Wynik]:
    """4b: własny `POST /Home/GetResults`. 16: liczniki `#resultCounts` przy pustej frazie.

    Kontrakt tego wywołania stoi dziś na **dwóch niezależnych cudzych kolektorach** i na
    własnych odczytach GET — nikt w tym projekcie nie wysłał tu POST-a. To jest jedyny pomiar,
    który zamienia „potwierdzone z drugiej ręki" na „potwierdzone".

    Jedno żądanie GET na `Details/{id}` idzie razem, bo zamrożona odpowiedź jest zalążkiem
    złotego pliku dla `parser/details.py`, a identyfikator 9620 był już odczytany w przeglądzie
    architektury, więc nie zgadujemy.
    """
    limiter = RateLimiter(
        min_spacing_s=ODSTEP_UZP_S, clock=SystemClock(), history=InMemoryHistory()
    )
    wyniki: list[Wynik] = []
    with build_http_client(user_agent=ua, allowed=UZP_HOSTS, timeout=LIMIT_CZASU_S) as klient:
        wyniki.append(
            _wykonaj(
                klient,
                limiter,
                nazwa="uzp_4b_getresults",
                metoda="POST",
                adres="https://orzeczenia.uzp.gov.pl/Home/GetResults",
                rozszerzenie="html",
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
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
        wyniki.append(
            _wykonaj(
                klient,
                limiter,
                nazwa="uzp_16_resultcounts",
                metoda="POST",
                adres="https://orzeczenia.uzp.gov.pl/Home/GetResults",
                rozszerzenie="html",
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
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
        wyniki.append(
            _wykonaj(
                klient,
                limiter,
                nazwa="uzp_details_9620",
                metoda="GET",
                adres="https://orzeczenia.uzp.gov.pl/Home/Details/9620",
                rozszerzenie="html",
            )
        )
    return wyniki


# --- pomiar 3: Atlas ----------------------------------------------------------------------


def pomiar_atlas(ua: str) -> list[Wynik]:
    """3, część pierwsza: czy `/api/kio/{slug}` naprawdę zwraca pełny tekst.

    Dostawca to deklaruje, ale audyt odnotował, że **żadnego punktu końcowego nie wywołano**,
    więc „zwraca pełny tekst" pozostaje deklaracją. Druga część pomiaru 3 — opóźnienie
    publikacji — wymaga porównania w czasie i zrobi ją polecenie `porownaj`, nie sonda.
    """
    limiter = RateLimiter(
        min_spacing_s=ODSTEP_POSREDNIK_S, clock=SystemClock(), history=InMemoryHistory()
    )
    wyniki: list[Wynik] = []
    with build_http_client(user_agent=ua, allowed=ATLAS_HOSTS, timeout=LIMIT_CZASU_S) as klient:
        wyniki.append(
            _wykonaj(
                klient,
                limiter,
                nazwa="atlas_3_lista",
                metoda="GET",
                adres="https://atlasprzetargow.pl/api/kio",
                rozszerzenie="json",
                params={"per_page": 5, "page": 1, "sort": "oldest"},
            )
        )
    return wyniki


POMIARY: dict[str, tuple[str, Callable[[str], list[Wynik]]]] = {
    "saos-dump": ("2a/2b — Dump API SAOS: dostęp i filtr po organie", pomiar_saos),
    "uzp-getresults": ("4b/16 — własny POST do GetResults i liczniki per organ", pomiar_uzp),
    "atlas": ("3 (część 1) — czy Atlas zwraca pełny tekst", pomiar_atlas),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sonda fazy 0. Wymaga zgody właściciela udzielonej w bieżącej sesji.",
    )
    parser.add_argument("pomiar", nargs="?", choices=sorted(POMIARY), help="który pomiar wykonać")
    parser.add_argument("--lista", action="store_true", help="wypisz dostępne pomiary i wyjdź")
    args = parser.parse_args(argv)

    if args.lista or not args.pomiar:
        print("Dostępne pomiary:\n")
        for klucz, (opis, _) in sorted(POMIARY.items()):
            print(f"  {klucz:16} {opis}")
        print("\nKażdy wysyła pojedyncze żądania diagnostyczne i zapisuje surowe odpowiedzi.")
        return 0

    # `KioError` deklaruje w docstringu, że komunikat jest przeznaczony dla użytkownika,
    # i niesie `exit_code`. Ślad stosu zamiast komunikatu łamałby oba te zdania naraz:
    # operator zobaczyłby wewnętrzną ścieżkę pliku zamiast zdania, co ma zrobić, a powłoka
    # dostałaby kod 1 zamiast 3 (błąd konfiguracji).
    try:
        ua = user_agent()  # odmawia bez KIO_TOOL_CONTACT — to jest zamierzone (reguła 16)
    except KioError as blad:
        print(f"Sonda nie wystartowała: {blad}", file=sys.stderr)
        return blad.exit_code

    opis, funkcja = POMIARY[args.pomiar]
    print(f"Pomiar: {opis}")
    print(f"Tożsamość klienta: {ua}")
    print(f"Moment rozpoczęcia: {utc_iso(SystemClock().wall())}\n")

    wyniki = funkcja(ua)

    print(f"{'pomiar':28} {'met.':5} {'status':>6} {'rozmiar':>11}  {'czas':>5}  plik")
    print("-" * 88)
    for wynik in wyniki:
        print(wynik.wiersz())

    podsumowanie = KATALOG_WYJSCIA / f"podsumowanie_{args.pomiar}.json"
    podsumowanie.write_text(
        json.dumps(
            [
                {
                    "nazwa": w.nazwa,
                    "metoda": w.metoda,
                    "adres": w.adres,
                    "status": w.status,
                    "bajtow": w.bajtow,
                    "czas_s": round(w.czas_s, 3),
                    "plik": w.plik.name if w.plik else None,
                    "uwaga": w.uwaga,
                }
                for w in wyniki
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSurowe odpowiedzi i podsumowanie: {KATALOG_WYJSCIA}")
    print("Wynik przepisz do docs/decisions.md w formacie „zmierzone {data}, {N} żądań”.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
