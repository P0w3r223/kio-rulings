"""Taksonomia wyjątków narzędzia.

Kody wyjścia: 1 = błąd nieodwracalny w tym uruchomieniu, 2 = błąd wznawialny
(harmonogram może ponowić), 3 = błąd konfiguracji lub autoryzacji, 130 = przerwanie przez
operatora (konwencja powłoki dla sygnału przerwania; stała `KOD_WYJSCIA_PRZERWANIE`).

Kształt przeniesiony z `ceidg-tool`; treść jest własna, bo wrogie zdarzenia są tu inne.
Najważniejsza różnica to `SourceContractBroken` — w CEIDG nie miała odpowiednika, bo tam
źródłem było udokumentowane API z wersją w adresie.
"""

from __future__ import annotations

KOD_WYJSCIA_PRZERWANIE = 130
"""Kod powłoki dla przebiegu przerwanego `Ctrl+C`. Jedno miejsce, bo `cli` i sonda mają mówić
powłoce to samo — a przerwany przebieg nie jest ani błędem konfiguracji, ani błędem kodu."""


class KioError(Exception):
    """Bazowy wyjątek narzędzia. Komunikat jest przeznaczony dla użytkownika."""

    exit_code: int = 1


class ConfigError(KioError):
    """Brak klucza pośrednika, zła ścieżka, niepoprawny kontrakt źródła."""

    exit_code = 3


class ConsentMissingError(ConfigError):
    """Przebieg masowy albo pomiar tempa bez zgody właściciela udzielonej w tej sesji.

    Reguła zgody z audytu 13.2 pkt 4: pojedynczy odczyt diagnostyczny nie wymaga zgody,
    przebieg masowy i pomiar 9 wymagają jej **w bieżącej sesji**. Zgoda z poprzedniej
    sesji nie jest zgodą, więc nie da się jej zapisać w konfiguracji — stąd wyjątek,
    a nie flaga w pliku.
    """


# Nazwa bez sufiksu `Error` wbrew konwencji `N818` jest celowa: reguła 17 w
# `ARCHITEKTURA_KIO_TOOL.md` i ADR-0003 nazywają ten wyjątek dosłownie `SourceContractBroken`.
# Zmiana nazwy tutaj rozjechałaby kod z regułą, która go wymienia — a to jest dokładnie ta
# klasa usterki, którą ADR-0003 zamyka. Jeśli nazwa ma się zmienić, zmienia się najpierw
# w regule.
class SourceContractBroken(KioError):  # noqa: N818
    """Źródło odpowiedziało 200, ale kształt odpowiedzi nie zgadza się z kontraktem.

    Reguła 17, i jest to reguła z konkretną datą: między majem a lipcem 2026 UZP przeniósł
    każdy punkt końcowy wyszukiwarki, a cudzy scraper przez około dwa miesiące zwracał
    `total=0` i pustą listę **zamiast błędu**, bo `GET /Home/Search` nadal odpowiadał 200
    ze szkieletem strony. Pusta lista jest poprawnym wynikiem zapytania, więc nic tego nie
    zauważyło. Adapter, który dostaje 200 bez oczekiwanej struktury, ma tu rzucić — cisza
    w tym miejscu jest usterką, nie wynikiem (zasada 7.3).

    **Kod wyjścia to 1, nie 2, i to jest rozstrzygnięcie, nie domyślka.** Pierwsza wersja
    miała tu 2, czyli „harmonogram może ponowić", a jednocześnie klasa nie dziedziczyła
    `ResumableError` — dwa kanały tej samej informacji mówiły co innego i jeden z nich był
    fałszywy (przegląd kodu 2026-09-15). Rozstrzygnięcie idzie w stronę 1, bo złamany
    kontrakt jest trwały **do czasu poprawki w kodzie**: żadne ponowienie go nie naprawi,
    a `sonda --kontrakt` uruchamiana z harmonogramu waliłaby w kółko w serwis, którego każdy
    PDF jest renderowany na żądanie. To byłaby ta sama awaria co „przez dwa miesiące zwracał
    `total=0`", tylko widziana od strony cudzego serwera: cicha pętla ponowień zamiast cichej
    pustej listy.
    """

    exit_code = 1


class AuthError(KioError):
    """401 / 403 — klucz pośrednika odrzucony albo klient zablokowany; bez ponawiania."""

    exit_code = 3


class BlockedByServiceError(KioError):
    """Serwis odmawia: CAPTCHA, wykrycie bota, trwała blokada adresu.

    Reguła 16: narzędzie nie omija zabezpieczeń. Granica jest prawna, nie estetyczna
    (art. 267 § 1 k.k.), więc odmowa serwisu kończy przebieg komunikatem do operatora,
    a nie próbą obejścia. Wyjątek jest osobny od `AuthError` właśnie po to, żeby żadna
    obsługa błędu nie mogła go potraktować jak „spróbuj z innym kluczem".
    """

    exit_code = 3


class BadRequestError(KioError):
    """400 — niepoprawnie skonstruowane zapytanie; bez ponawiania."""


class NotFoundError(KioError):
    """404 — dokument o tym identyfikatorze nie istnieje.

    W przestrzeni identyfikatorów UZP 404 jest **spodziewanym** wynikiem, nie awarią:
    skan luk trafia w dziury, których gęstość jest pomiarem 6, a nie błędem.
    """


class UntrustedLinkError(KioError):
    """Adres wskazuje na host spoza bramki wyjścia."""


class IdentityError(KioError):
    """Nie da się zbudować kanonicznej tożsamości dokumentu z tego, co przyszło z kanału.

    Istnieje, bo `docid.document_id` dostaje `source_ref` **ze scrapowanej strony**, czyli
    z zewnątrz, a nie od programisty. Pusty identyfikator albo identyfikator ze znakami
    sterującymi to warunek na danych, nie pomyłka w kodzie — więc operator ma zobaczyć
    komunikat i kod wyjścia, a nie ślad stosu z `ValueError`, którego `except KioError`
    w warstwie CLI nie złapie.
    """


class PagingRunawayError(KioError):
    """Przekroczony twardy limit stron — ochrona przed nieskończoną pętlą."""


class StoreError(KioError):
    """Niespójność bazy lokalnej."""


class StoreLockedError(StoreError):
    """Inny proces pisze do tego samego korpusu."""


class RunNotFoundError(StoreError):
    """Nie ma przebiegu o podanym identyfikatorze — pomyłka w wywołaniu, nie awaria bazy.

    Identyfikator jest napisem przepisywanym z ekranu (`atlas-969ac406dd8f`), więc literówka
    jest pomyłką spodziewaną, nie wyjątkową: kod 3 jak przy złej fladze, a zdanie ma mówić,
    skąd wziąć poprawny identyfikator (tester 2026-09-18: kod 1 i zero wskazówki).
    """

    exit_code = 3


class ResumableError(KioError):
    """Błąd, po którym warto wznowić przebieg."""

    exit_code = 2


class ServerError(ResumableError):
    """5xx po wyczerpaniu prób."""


class TransportError(ResumableError):
    """Timeout, DNS, zerwane połączenie."""


class RateLimitError(ResumableError):
    """429 mimo limitera — po odczekaniu pełnej blokady nadal odrzucane."""


class ExportError(KioError):
    """Nie da się zapisać wyniku (np. przekroczony limit wierszy arkusza)."""


class ParseError(KioError):
    """Surowa wersja dokumentu nie daje się odczytać do metadanych i treści.

    Surowe bajty są już w `raw_versions` (reguła 19: zapis przed parsowaniem), więc ten błąd
    nie gubi niczego — mówi, że tabele pochodne dla tej wersji nie powstały, i ma być
    **policzony** w raporcie `przelicz`, a nie przemilczany.
    """
