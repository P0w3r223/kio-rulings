"""Konfiguracja: bramka wyjścia, tożsamość klienta, maskowanie sekretów.

Moduł celowo ubogi. Kanał akwizycji nie jest wybrany — pomiary 1, 2a/2b i 3 jeszcze nie
padły — więc wszystko, co zależy od kanału (adresy punktów końcowych, nazwy pól formularza,
rozmiar strony), mieszka w `contract.yaml` przy adapterze, a nie tutaj. Tu stoi wyłącznie to,
co obowiązuje niezależnie od tego, który kanał wygra.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from platformdirs import user_data_dir

from . import __version__
from .errors import ConfigError

# --- bramka wyjścia (reguła 11) ---
# Hosty per kanał, a nie jedna lista, bo `build_http_client(allowed=…)` ma zawężać bramkę do
# kanału, którym akurat jedzie przebieg. Adapter Atlasu niosący klucz `X-Api-Key` nie ma prawa
# wyjść na `orzeczenia.uzp.gov.pl` przez przekierowanie, i odwrotnie.
UZP_HOSTS = frozenset({"orzeczenia.uzp.gov.pl"})
ATLAS_HOSTS = frozenset({"atlasprzetargow.pl"})
SAOS_HOSTS = frozenset({"www.saos.org.pl"})

# Sumy tych zbiorów **nie ma** i to jest rozstrzygnięcie z 2026-09-17, a nie przeoczenie.
# Do tego dnia stała `ALLOWED_HOSTS` była wartością domyślną `build_http_client(allowed=…)`,
# a komentarz przy niej twierdził, że używają jej sondy fazy 0. Nie używały: sonda podaje
# zbiór jawnie przy każdym pomiarze, więc suma nie miała ani jednego wywołującego poza własną
# sygnaturą — czyli uzasadnienie opisywało użycie nieobecne w drzewie. Kto naprawdę potrzebuje
# dotknąć dwóch kanałów jednym klientem, składa sumę w miejscu wywołania i wtedy widać ją
# w przeglądzie kodu.

CONTACT_ENV = "KIO_TOOL_CONTACT"

# Napis musi nieść adres, pod którym da się napisać do operatora. Sprawdzamy obecność `@`
# (poczta) albo `http` (strona projektu) — to jest kontrola minimalna i celowo taka zostaje:
# ma odróżniać „jest kontakt" od „nie ma kontaktu", a nie walidować składnię adresu, bo
# walidator poczty napisany z pamięci odrzuca adresy poprawne.
_WZOR_KONTAKTU = re.compile(r"@|https?://", re.IGNORECASE)


def user_agent() -> str:
    """Tożsamość klienta z adresem kontaktowym — i odmowa, gdy adresu nie ma.

    Reguła 16 zabrania podszywania się pod przeglądarkę. Cudzy kolektor KIO ustawia
    `User-Agent` udający Chrome na macOS i to nie tylko łamie regułę, ale odbiera UZP jedyną
    możliwość napisania do operatora, gdy coś pójdzie nie tak (architektura 3.1).

    Brak adresu kontaktowego jest tu **błędem konfiguracji, nie wartością domyślną**:
    domyślny adres byłby cudzym adresem albo fikcją, a jedno i drugie jest gorsze od odmowy.

    Gałąź przepuszczająca gotowy napis (zaczynający się od `kio-tool/`) **też jest
    walidowana** i to jest poprawka z przeglądu kodu 2026-09-15. Pierwsza wersja przepuszczała
    ją bez sprawdzenia, więc `KIO_TOOL_CONTACT="kio-tool/1.0"` dawało `User-Agent` bez
    żadnego kontaktu, a `"kio-tool/1.0 Mozilla/5.0 (Macintosh…)"` przechodziło tak samo —
    czyli udokumentowaną ścieżką szczęśliwą była dokładnie ta gałąź, która nie sprawdzała nic.
    """
    contact = (os.environ.get(CONTACT_ENV) or "").strip()
    if not contact:
        raise ConfigError(
            f"Brak adresu kontaktowego w zmiennej {CONTACT_ENV}. Narzędzie przedstawia się "
            "własnym adresem przy każdym żądaniu, żeby operator serwisu miał jak napisać, "
            "gdy coś pójdzie nie tak. Ustaw np. "
            f'{CONTACT_ENV}="imie.nazwisko@example.org".'
        )
    if not _WZOR_KONTAKTU.search(contact):
        raise ConfigError(
            f"Wartość {CONTACT_ENV}={contact!r} nie zawiera adresu kontaktowego. "
            "Napis ma nieść adres poczty albo stronę projektu — sama nazwa i wersja "
            "narzędzia nie dają operatorowi serwisu możliwości napisania do nikogo."
        )
    if contact.startswith("kio-tool/"):
        return contact
    return f"kio-tool/{__version__} ({contact})"


# --- baza korpusu ---
NAZWA_APLIKACJI = "kio-tool"
PLIK_BAZY = "korpus.sqlite"


def default_db_path() -> Path:
    """Domyślna ścieżka bazy korpusu — w katalogu danych użytkownika, **poza repozytorium**.

    Powód stoi w `.gitignore` i nie jest rozmiarowy: orzeczenia niosą pełne nazwiska składu
    orzekającego i protokolantów (audyt 3.3), a operator narzędzia jest dla nich administratorem
    danych. Repozytorium przechowuje kod i dowody, nie korpus — więc domyślna ścieżka nie ma prawa
    wskazywać do drzewa źródłowego, nawet gdy wzorzec `*.sqlite` w `.gitignore` by ją ukrył.
    Operator podaje inną flagą `--baza`.
    """
    return Path(user_data_dir(NAZWA_APLIKACJI)) / PLIK_BAZY


KATALOG_WYNIKOW = "wyniki"


def default_output_dir() -> Path:
    """Domyślny katalog eksportów — obok bazy, z tego samego powodu poza repozytorium:
    arkusz niesie te same nazwiska składu, co korpus. Operator podaje inną flagą `--out`."""
    return Path(user_data_dir(NAZWA_APLIKACJI)) / KATALOG_WYNIKOW


# Znaki niedozwolone w nazwie pliku na Windowsie i w POSIX-ie razem, plus białe znaki — nazwa
# powstaje z kryteriów operatora (`describe()`), czyli z tekstu, który ktoś wpisał.
_FILENAME_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f\s]+')
MAX_FILENAME_STEM = 80
"""Ścieżka w katalogu danych użytkownika ma już kilkadziesiąt znaków; limit 260 na Windowsie
liczy się od korzenia (wzorzec z `ceidg-tool`)."""


def safe_filename(stem: str, suffix: str = "") -> str:
    """Nazwa pliku bez znaków ścieżki, o ograniczonej długości; pusty rdzeń daje `kio`."""
    cleaned = _FILENAME_FORBIDDEN.sub("_", stem).strip("_.")
    cleaned = re.sub(r"_+", "_", cleaned) or NAZWA_APLIKACJI.split("-")[0]
    return cleaned[:MAX_FILENAME_STEM] + suffix


def klucz_api(zmienna: str) -> str | None:
    """Klucz API z podanej zmiennej środowiskowej, zgłoszony do maskowania; `None`, gdy brak.

    Nazwa zmiennej przychodzi z `contract.yaml` kanału (dla Atlasu `KIO_TOOL_ATLAS_KEY`), bo
    klucz jest sprawą kanału, a nie narzędzia. Jedno miejsce, które klucz wczytuje, woła
    `register_secret` — tak mówi docstring tamtej funkcji — i odmawia przy kluczu za krótkim
    do zamaskowania, zanim ten trafi do jakiegokolwiek nagłówka.
    """
    wartosc = (os.environ.get(zmienna) or "").strip()
    if not wartosc:
        return None
    register_secret(wartosc)
    return wartosc


# --- maskowanie sekretów ---
# Rejestr znanych **wartości**, zasilany przy wczytaniu klucza. Wzorców kształtu tu nie ma
# i to jest świadome: formatu klucza `X-Api-Key` Atlasu nikt w tym projekcie nie widział
# (pomiar 3 i 15 jeszcze nie padły), a wzorzec napisany z pamięci modelu przeszedłby każdy
# test i cicho przepuszczał sekret o innym kształcie — dokładnie mina 4 z audytu.
_KNOWN_SECRETS: set[str] = set()
SECRET_PATTERNS: tuple[re.Pattern[str], ...] = ()

MIN_REGISTERED_SECRET = 12
"""Dolna granica długości sekretu, który wolno zarejestrować do maskowania.

Powód przeniesiony z `ceidg-tool` razem z liczbą: sekret o długości 3 zamieniłby **każdy**
tekst zawierający te trzy znaki w `<token>`, czyli maskowanie zjadałoby treść orzeczenia.
Pierwsza wersja tego modułu miała tu goły literał `8` bez komentarza — czyli próg obniżony
w stronę, przed którą ostrzegał usunięty komentarz (przegląd kodu 2026-09-15).
"""


def register_secret(value: str) -> None:
    """Zgłasza sekret do maskowania. Woła to miejsce, które go wczytuje, raz.

    Odmawia zamiast milczeć: wywołujący ma prawo sądzić, że po tym wywołaniu wartość jest
    maskowana, a ciche odrzucenie zostawia go w przekonaniu, którego nic nie potwierdza.
    """
    if len(value) < MIN_REGISTERED_SECRET:
        raise ConfigError(
            f"Sekret krótszy niż {MIN_REGISTERED_SECRET} znaków nie zostanie zarejestrowany "
            "do maskowania: krótki napis występuje w treści orzeczeń i maskowanie zjadałoby "
            "tekst zamiast chronić klucz."
        )
    _KNOWN_SECRETS.add(value)


def forget_secrets() -> None:
    """Czyści rejestr. Istnieje wyłącznie po to, żeby testy nie przeciekały do siebie.

    Przeniesione z `ceidg-tool` razem z powodem. `_KNOWN_SECRETS` jest stanem na poziomie
    modułu, więc bez tego pierwszy test rejestrujący cokolwiek zmienia wynik każdego
    następnego — a `tests/conftest.py` woła to przed każdym testem.
    """
    _KNOWN_SECRETS.clear()


def mask_tokens(text: str) -> str:
    """Zastępuje każdy znany sekret w tekście znacznikiem `<token>`.

    Stoi na ścieżce do ekranu (`richtext.safe`) i do dziennika żądań, bo `requests_log`
    trzyma `url_redacted` — adres bez tego, co mogłoby w nim być.

    Kolejność malejąca po długości: przy iteracji po nieuporządkowanym zbiorze krótszy sekret
    mógłby zamaskować prefiks dłuższego i zostawić resztę na ekranie.
    """
    for secret in sorted(_KNOWN_SECRETS, key=len, reverse=True):
        text = text.replace(secret, "<token>")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<token>", text)
    return text
