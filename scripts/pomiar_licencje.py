"""Pomiar 23 — czy SAOS i Atlas licencjonują ponowne wykorzystywanie wprost.

Wejście bramki fazy 0 razem z decyzją B właściciela (2026-09-17): kanał masowy musi
licencjonować reuse wprost, odczytane u dostawcy z datą i SHA-256 strony. Te same markery co
w pomiarze 14, żeby wyniki wolno było zestawić. Jedzie przez `zadanie` — zegar, klient, limiter
i kronika pochodzą z tamtejszych fabryk. Do 2026-09-18 w `sonda.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

import zadanie

from kio_tool.config import ATLAS_HOSTS, SAOS_HOSTS
from kio_tool.logbook import Kronika, Wynik

# --- pomiar 23: czy pośrednicy licencjonują ponowne wykorzystywanie wprost ------------------

MARKERY_LICENCJI = (
    "licencj",
    "creative",
    "ponowne wykorzyst",
    "warunki korzystania",
    "regulamin",
    "prawa autorskie",
)
"""Te same sześć ciągów, których szukał pomiar 14 na `orzeczenia.uzp.gov.pl` (2026-09-15).

Lista jest **przepisana, a nie wymyślona na nowo**, i to jest cały sens pomiaru 23: to samo
pytanie zadane tym samym sposobem trzem hostom daje wyniki, które wolno ze sobą zestawić.
Inna lista dla innego hosta mierzyłaby różnicę między listami, nie między serwisami.
"""

if any(not marker or not marker.isascii() or not marker.islower() for marker in MARKERY_LICENCJI):
    # Ten sam niezmiennik co w `ksztalt.html_z_fragmentami`: `policz_markery` robi
    # `marker.encode("ascii")`, więc marker z ogonkiem albo wielką literą wywróciłby się
    # **po** wysłaniu żądania. Literówka w liście ma wywracać import, zanim cokolwiek wyjdzie
    # na zewnątrz (przegląd kodu 2026-09-18).
    raise ValueError(
        f"markery licencji muszą być niepustymi napisami ASCII małymi literami: {MARKERY_LICENCJI}"
    )


def werdykt_licencji(wynik: Wynik) -> str:
    """Zdanie o markerach dla jednego odczytu — albo zdanie, że markerów nie policzono.

    Do przeglądu kodu 2026-09-18 markery liczyły się z pustych bajtów, gdy żądanie nie wróciło,
    i ze strony błędu, gdy serwis odmówił — a `opisz_markery` przy zerze trafień sam powołuje
    się na pomiar 14. Powstawał wynik pomiaru licencyjnego z odpowiedzi, której nie było:
    zdanie prawdziwie wyglądające i fałszywe, w pliku, który ma produkować dowód dla decyzji B.
    Ten sam podział co w `pomiar_uzp.ocen_stabilnosc`: odpowiedź nienadająca się do odczytu
    nie wchodzi do porównania.
    """
    if wynik.plik is None or wynik.odmowa_serwisu:
        przyczyna = "brak odpowiedzi" if wynik.status is None else f"status {wynik.status}"
        return (
            f"markery licencji: **nie policzone** — odpowiedź nie nadaje się do odczytu "
            f"({przyczyna}); to nie jest „zero trafień” z pomiaru 14. Powtórz po ustaniu przyczyny"
        )
    return opisz_markery(policz_markery(wynik.plik.read_bytes()))


@dataclass(frozen=True)
class AdresLicencji:
    """Jeden odczyt pomiaru 23: adres razem ze źródłem, z którego ten adres pochodzi."""

    nazwa: str
    adres: str
    hosty: frozenset[str]
    zrodlo: str


KANALY_LICENCJI: tuple[AdresLicencji, ...] = (
    AdresLicencji(
        "saos",
        "https://www.saos.org.pl/",
        SAOS_HOSTS,
        "korzeń hosta — ścieżki do strony z warunkami nikt tu nie odczytał",
    ),
    AdresLicencji(
        "atlas",
        "https://atlasprzetargow.pl/",
        ATLAS_HOSTS,
        "korzeń hosta — ta sama droga co w pomiarze 14",
    ),
    AdresLicencji(
        "atlas_dokumentacja",
        "https://atlasprzetargow.pl/dokumentacja-api",
        ATLAS_HOSTS,
        "strona dokumentacji API odczytana 2026-09-18 — niesie notę CC BY 4.0 z formułą atrybucji",
    ),
)
"""Adresy do sprawdzenia, każdy ze zbiorem dla bramki wyjścia i ze źródłem adresu.

Korzenie hostów idą tą samą drogą, którą przeszedł pomiar 14: odczyt w surowych bajtach
i zliczenie markerów. Podstrona jest wpisana **wyłącznie wtedy, gdy ktoś ją odczytał z datą**:
`/dokumentacja-api` Atlasu odczytano 2026-09-18 i to ten odczyt przyniósł notę licencyjną
z formułą atrybucji. Wpisanie `/regulamin` albo `/terms` z domysłu byłoby adresem bez pokrycia
w pliku, który ma produkować dowód. Bez wiersza z dokumentacją pomiar mógł wrócić „zero
markerów" ze strony głównej i zamknąć regułę 23 kanałowi o udokumentowanej licencji — przegląd
architektoniczny 2026-09-18 nazwał to jako F-6.
"""


def policz_markery(tresc: bytes) -> dict[str, int]:
    """Ile razy każdy marker licencji występuje w odpowiedzi. Zero żądań, czysta funkcja.

    Porównanie po bajtach ASCII i po małych literach, tak jak w `ksztalty.html_z_fragmentami`:
    `bytes.lower()` nie zna polskich znaków, więc wszystkie markery są ASCII i „licencj" łapie
    zarówno „licencja", jak i „licencji".
    """
    male = tresc.lower()
    return {marker: male.count(marker.encode("ascii")) for marker in MARKERY_LICENCJI}


def opisz_markery(trafienia: Mapping[str, int]) -> str:
    """Wynik pomiaru 23 jako zdanie — także wtedy, gdy nie ma żadnego trafienia.

    Zero trafień **jest wynikiem**, i to tym samym, który pomiar 14 uznał za rozstrzygający dla
    UZP. Dlatego brak markerów nie zwraca pustego napisu: cisza w tym miejscu wyglądałaby jak
    pominięcie pomiaru, a nie jak jego rezultat.
    """
    obecne = {marker: ile for marker, ile in trafienia.items() if ile}
    if not obecne:
        return (
            "markery licencji: **zero trafień** w tej odpowiedzi — tak samo jak "
            "`orzeczenia.uzp.gov.pl` w pomiarze 14. Do rozstrzygnięcia pozostaje, czy warunki "
            "stoją gdzie indziej w serwisie"
        )
    return "markery licencji: " + ", ".join(f"`{m}`×{ile}" for m, ile in sorted(obecne.items()))


def pomiar_licencje(ua: str, kronika: Kronika | None = None) -> list[Wynik]:
    """23: czy SAOS i Atlas licencjonują ponowne wykorzystywanie wprost. Trzy żądania.

    Dwa korzenie hostów i jedna podstrona — ta, którą odczytano z datą (`KANALY_LICENCJI`).
    Jeden limiter na całą grupę, bo dwa z trzech adresów leżą na tym samym hoście i odstęp
    między nimi ma obowiązywać tak samo jak między żądaniami jednego pomiaru.

    Pomiar wszedł do wejścia bramki 2026-09-17 razem z decyzją B właściciela: skoro UZP nie
    pełni roli kanału masowego, kanał masowy **musi** licencjonować reuse wprost — i musi to
    być odczytane u dostawcy, z datą i SHA-256 strony, a nie wzięte z cudzego streszczenia.

    To nie jest opinia prawna i nie udaje jej. Jest tym, czym był pomiar 14: odczytem tego, co
    serwis sam o sobie mówi. Różnica wobec pomiaru 14 polega wyłącznie na tym, że tam wynik
    negatywny stał się podstawą reguły, a tu wynik pozytywny ma być podstawą wyboru kanału.

    Kształt odpowiedzi **nie jest** tu oceniany przez `ksztalty`: brak markerów licencji jest
    wynikiem pomiaru, a nie zerwanym kontraktem, i nie ma prawa zapalić `Wynik.odmowa` ani
    zatrzymać drugiego hosta. To jest ta sama różnica, którą SAOS wprowadził przy dwóch
    sprzecznych pisowniach parametru dat: niezgodność bywa odpowiedzią, nie awarią.
    """
    kronika = kronika or zadanie.kronika()
    limiter = zadanie.limiter(zadanie.ODSTEP_POSREDNIK_S)
    wyniki: list[Wynik] = []
    for kanal in KANALY_LICENCJI:
        with zadanie.klient(ua, kanal.hosty) as klient:
            wynik = zadanie.wykonaj(
                klient,
                limiter,
                kronika,
                nazwa=f"licencje_23_{kanal.nazwa}",
                metoda="GET",
                adres=kanal.adres,
                rozszerzenie="html",
                uwaga=(
                    "pomiar 23: warunki ponownego wykorzystywania u źródła; "
                    f"adres z: {kanal.zrodlo}"
                ),
            )
        opis = werdykt_licencji(wynik)
        print(f"{'':26} └─ {opis}", flush=True)
        # Do `uwaga`, nie tylko na ekran — z tego samego powodu co werdykt pomiaru 19: to jest
        # zdanie, które operator przepisuje do `docs/decisions.md`, a ekran ginie razem z oknem.
        wyniki.append(replace(wynik, uwaga="; ".join(filter(None, (wynik.uwaga, opis)))))
    return wyniki
