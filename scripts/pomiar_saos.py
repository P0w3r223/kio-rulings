"""Pomiar 2a/2b — Dump API SAOS: dostęp własnym klientem i filtr po organie.

Wejście bramki fazy 0 (ADR-0004): od tego pomiaru wisi jedenaście lat materiału, bo pomiar 1
zamknął drogę przez FTP. Jedzie przez `zadanie` — zegar, klient, limiter i kronika pochodzą
z tamtejszych fabryk, więc test podstawia je w jednym miejscu. Do 2026-09-18 w `sonda.py`.
"""

from __future__ import annotations

import ksztalty
import zadanie

from kio_tool.config import SAOS_HOSTS
from kio_tool.logbook import Kronika, Wynik, niewyslany

# --- pomiar 2a i 2b: SAOS Dump API -------------------------------------------------------


def pomiar_saos(ua: str, kronika: Kronika | None = None) -> list[Wynik]:
    """2a: czy własny klient dostaje się do Dump API. 2b: czy Dump API filtruje po organie.

    Audyt i architektura zgadzają się, że wyszukiwarka SAOS **nie służy** do pobierania bazy —
    mówi to wprost dokumentacja SAOS. Dwa niezależne klienty dostały 403 na `/api/search/*`,
    ale **Dump API nie było testowane przez nikogo**, a to ono jest właściwym punktem.

    Wiki SAOS jest wewnętrznie sprzeczna co do nazw parametrów dat: nagłówek tabeli mówi
    `judgmentDateFrom/To`, a przykład w tej samej sekcji `judgmentStartDate/EndDate`. Sonda
    próbuje **obu** — rozstrzygnie to własne wywołanie, nie lektura.

    Kontrola idzie tu **po** odmowie, a nie przed nią: żaden odczyt na tym hoście nie jest
    znany-dobry (dwa klienty dostały 403), więc nie ma czym zabezpieczyć ekspozycji. Jeśli
    Dump API odmówi, jedno żądanie na korzeń powie, czy odmawia punkt, czy host.

    Zatrzymanie po odmowie stoi tu na **węższym** warunku niż przy UZP i to jest decyzja,
    nie niedopatrzenie (przegląd 2026-09-17). Grupę przerywa odmowa **serwisu** — kod 401,
    403, 429 albo brak odpowiedzi — bo do serwisu, który właśnie powiedział „nie", nie puka
    się trzy razy. Nie przerywa jej natomiast **niezgodny kształt**: dwie sprzeczne pisownie
    parametru dat po to tu są, żeby sprawdzić, która działa, a zła pisownia objawi się
    najpewniej odpowiedzią 200 o kształcie innym niż kontraktowy. Przerwanie na tym byłoby
    porzuceniem pomiaru dokładnie w chwili, w której zaczyna on cokolwiek mierzyć.
    """
    kronika = kronika or zadanie.kronika()
    limiter = zadanie.limiter(zadanie.ODSTEP_POSREDNIK_S)
    baza = "https://www.saos.org.pl/api/dump/judgments"
    plan: tuple[tuple[str, dict[str, str | int]], ...] = (
        (
            "saos_2a_dump_datefrom",
            {
                "pageSize": 10,
                "pageNumber": 0,
                "judgmentDateFrom": "2018-09-01",
                "judgmentDateTo": "2018-09-30",
            },
        ),
        (
            "saos_2a_dump_startdate",
            {
                "pageSize": 10,
                "pageNumber": 0,
                "judgmentStartDate": "2018-09-01",
                "judgmentEndDate": "2018-09-30",
            },
        ),
        (
            "saos_2b_courttype",
            {"pageSize": 10, "pageNumber": 0, "courtType": "NATIONAL_APPEAL_CHAMBER"},
        ),
    )
    wyniki: list[Wynik] = []
    with zadanie.klient(ua, SAOS_HOSTS) as klient:
        powod_stopu: str | None = None
        for nazwa, params in plan:
            if powod_stopu is not None:
                wyniki.append(
                    kronika.zanotuj(niewyslany(nazwa, "GET", f"pomiar przerwany: {powod_stopu}"))
                )
                continue
            wynik = zadanie.wykonaj(
                klient,
                limiter,
                kronika,
                nazwa=nazwa,
                metoda="GET",
                adres=baza,
                rozszerzenie="json",
                ksztalt=ksztalty.SAOS_DUMP,
                params=params,
            )
            wyniki.append(wynik)
            if wynik.odmowa_serwisu:
                powod_stopu = (
                    f"serwis odmówił przy `{nazwa}` "
                    f"({'brak odpowiedzi' if wynik.status is None else wynik.status})"
                )
        if any(w.odmowa for w in wyniki):
            wyniki.append(
                zadanie.kontrola_hosta(
                    klient,
                    limiter,
                    kronika,
                    nazwa="saos_kontrola_hosta",
                    korzen="https://www.saos.org.pl/",
                )
            )
    return wyniki
