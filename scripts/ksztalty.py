"""Oczekiwania sondy fazy 0 wobec kształtu odpowiedzi — po jednym na punkt końcowy.

Maszyneria oceny (`Ksztalt`, `OcenaKsztaltu`, fabryki `html_z_fragmentami`,
`json_z_rekordami`, `json_ze_slownikiem`) mieszka od 2026-09-18 w `kio_tool/ksztalt.py`
razem z uzasadnieniem z reguły 17. Tu zostają **instancje**: konkretne fragmenty, nazwy list
i pola rekordów, każde ze źródłem tego oczekiwania — bo „kontrakt z drugiej ręki" i „własny
odczyt z datą" to dwa różne statusy dowodowe (zasada 7.1) i ich niezgodność znaczy co innego.
Po bramce fazy 0 oczekiwanie wybranego kanału przenosi się do jego `contract.yaml`.

Moduł obok, nie w pakiecie, z tego samego powodu co `sonda.py`: przed bramką wyboru kanału
`source/` nie powstaje. Działa przy uruchomieniu udokumentowanym w nagłówku sondy, bo katalog
skryptu wchodzi wtedy na `sys.path`; testom dokłada tę ścieżkę `tests/conftest.py`.

Niezmienniki fabryk (fragmenty ASCII, oczekiwanie bez treści) są sprawdzane przy budowie, więc
literówka w oczekiwaniu wywraca **import** tego modułu — czyli zanim cokolwiek wyjdzie na
zewnątrz. Ten moduł nie wysyła żądań i nie dotyka dysku.
"""

from __future__ import annotations

from kio_tool.ksztalt import Ksztalt, html_z_fragmentami, json_z_rekordami, json_ze_slownikiem

# --- oczekiwania per punkt końcowy, każde ze swoim statusem dowodowym ---------------------

UZP_WYNIKI = Ksztalt(
    opis="lista wyników wyszukiwarki",
    zrodlo="kontrakt z drugiej ręki: dwa cudze kolektory (architektura 3.1, reguła 17)",
    ocen=html_z_fragmentami("resultCounts", "search-list-item"),
)

UZP_DETAILS = Ksztalt(
    opis="metryka dokumentu z listą sygnatur",
    zrodlo="własny odczyt 2026-09-14 (architektura 4.4, 4.5)",
    ocen=html_z_fragmentami("<label", "Sygnatura"),
)

UZP_CONTENT = Ksztalt(
    opis="treść orzeczenia jako HTML, z nagłówkami sekcji",
    zrodlo=(
        "własny odczyt 2026-09-14: `ContentHtml/18946` wrócił 200 (architektura 7), "
        "a nagłówki `Uzasadnienie` i `Izba zważyła` są stamtąd wypisane (architektura 1)"
    ),
    # Dwa nagłówki, nie pięć: `WYROK` i `orzeka:` nie wystąpią w postanowieniu ani uchwale,
    # więc rozpoznawałyby rodzaj rozstrzygnięcia zamiast kształtu odpowiedzi. Pomiar 19 pyta
    # o bajty, nie o rodzaj — a kształt jest tu po to, żeby strona bot-checka z kodem 200 nie
    # przeszła jako „treść stabilna".
    #
    # Fragmenty przycięte na pierwszym ogonku (`Izba zwa` z `Izba zważyła, co następuje:`), bo
    # porównanie idzie po bajtach i nie zna kodowania strony. Przycięcie jest do **ogonka**,
    # a nie do słowa: samo `Izba` prawdopodobnie stoi w stopce lub nagłówku każdej strony tej
    # domeny („Krajowa Izba Odwoławcza"), więc oczekiwanie sprowadzałoby się wtedy do jednego
    # fragmentu, udając dwa (obserwacja z przeglądu testów 2026-09-17, niezmierzona).
    #
    # Zdanie „strona weryfikacji przeglądarki nie zawiera tych fragmentów" jest **założeniem**,
    # nie odczytem: nikt w tym projekcie takiej strony nie widział. Do sprawdzenia przy pierwszym
    # przebiegu — razem z tym, czy `Izba zwa` występuje w dokumencie niebędącym wyrokiem.
    ocen=html_z_fragmentami("Uzasadnienie", "Izba zwa"),
)

SAOS_DUMP = Ksztalt(
    opis="strona zrzutu z listą orzeczeń",
    zrodlo="dokumentacja SAOS (wiki), czytana przez pośrednika — nie własny odczyt",
    ocen=json_z_rekordami("items"),
)

ATLAS_LISTA = Ksztalt(
    opis="lista orzeczeń pośrednika",
    zrodlo=(
        "dokumentacja Atlasu odczytana 2026-09-18: rekordy w tablicy `data[]` z polami "
        "`slug`, `primary_signature`, `ruling_date`; własnego wywołania jeszcze nie było"
    ),
    # Klucz listy nazwany, a nie „pierwsza napotkana lista": bez nazwy `_pierwsza_lista`
    # bierze pierwszą listę w kolejności kluczy — dokładnie ta usterka, którą 2026-09-17
    # naprawiono dla SAOS (`links` obok `items`), dla Atlasu stała otwarta do 2026-09-18.
    ocen=json_z_rekordami("data"),
)

ATLAS_DOKUMENT = Ksztalt(
    opis="pełny rekord orzeczenia pośrednika",
    zrodlo=(
        "dokumentacja Atlasu odczytana 2026-09-18: `GET /api/kio/{slug}` opisany jako „pełna "
        "treść orzeczenia z metadanymi”, bez przykładowej odpowiedzi — pola wymagane są "
        "przeniesione z opisu listy, a nazwę pola z treścią ma znaleźć pomiar 3a"
    ),
    ocen=json_ze_slownikiem("slug", "primary_signature"),
)
