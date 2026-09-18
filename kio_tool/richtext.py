"""Jedyny szew z `rich`: konsola programu i neutralizacja tekstu z zewnątrz.

Reguła granic 10: napis spoza programu staje się drukowalny wyłącznie przez `safe`.
W `ceidg-tool` ta sama formuła stała najpierw w dwóch miejscach i dopiero awaria pokazała,
że dwa egzemplarze reguły krytycznej dla bezpieczeństwa to o jeden za dużo — poprawka
jednego nie dotyka drugiego.
"""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from .config import mask_tokens
from .safetext import strip_control


def make_console(*, stderr: bool = False) -> Console:
    """Konsola programu — bez `file=`, bez interpretacji znaczników, bez podświetlania.

    `rich` sięga po `sys.stdout` (albo `sys.stderr` przy `stderr=True`) przy każdym zapisie,
    więc konsola zbudowana bez `file=` trafia tam, gdzie akurat wskazuje strumień. Podanie
    `file=sys.stdout` zamroziłoby strumień z chwili importu i przechwytywanie wyjścia w testach
    CLI przestałoby działać.

    **`markup=False` i `highlight=False` to rozstrzygnięcie z 2026-09-15, nie ostrożność.**
    Reguła 10 mówi, że napis spoza programu staje się drukowalny wyłącznie przez `safe`, a jej
    jedynym strażnikiem jest skan AST. Skan łapie przeoczenia, więc pierwsze
    `console.print(f"Błąd: {e}")` w warstwie CLI odtworzyłoby dziurę z CEIDG — a `KioError`
    mówi w docstringu wprost, że komunikat jest przeznaczony dla użytkownika, czyli treści
    wyjątków z założenia trafią na ekran. Wyłączenie znaczników na poziomie konsoli zamienia
    regułę 10 z własności skanu w **własność obiektu**: nawias kwadratowy z uzasadnienia
    orzeczenia nie ma jak stać się stylem ani klikalnym odnośnikiem, niezależnie od tego, czy
    ktoś pamiętał o `safe`.

    Koszt: własne komunikaty programu nie mogą używać znaczników w napisie i muszą podawać
    styl jawnie (`Text`, `style=`). Przy pustej jeszcze warstwie `ui/` jest to koszt zerowy,
    a po jej powstaniu byłby to koszt przepisania każdego ekranu.

    `safe` zostaje mimo to i nie jest przez to zbędne: neutralizuje znaki sterujące i maskuje
    sekrety, czego wyłączenie znaczników nie robi. Dwa zamki na dwie różne dziury.
    """
    return Console(markup=False, highlight=False, stderr=stderr)


def safe(value: str) -> Text:
    """Napis z zewnątrz jako zwykły tekst: bez parsowania znaczników, bez znaków sterujących.

    `rich` czyta nawiasy kwadratowe jako znaczniki. W CEIDG kończyło się to wyjątkiem
    `MarkupError` na nazwie firmy i klikalnym odnośnikiem na obcy adres z `[link=…]`.
    Tutaj wejściem jest uzasadnienie orzeczenia, które cytuje pisma stron i fragmenty
    specyfikacji — czyli tekst pisany przez osoby trzecie, o dowolnej zawartości,
    liczony w stronach.

    Kolejność `strip_control` przed `mask_tokens` jest istotna i była w pierwszej wersji
    odwrotna (przegląd kodu 2026-09-15). `mask_tokens` szuka dokładnej wartości sekretu;
    jeżeli w napisie stoi klucz z wstrzykniętym znakiem sterującym (`SEC\\x01RET`),
    dopasowanie nie zachodzi, a usunięcie znaku sterującego **później** odtwarza sekret
    i wypisuje go na ekran. Najpierw postać kanoniczna, potem porównanie.
    """
    return Text(mask_tokens(strip_control(value)))


def safe_or_none(value: str | None) -> Text | None:
    """`safe` dla pól opcjonalnych. Pusta data wydania to brak daty, a nie pusty napis.

    Osobna funkcja, a nie wyrażenie warunkowe w miejscu użycia: skan reguły 10 rozpoznaje
    wywołanie neutralizatora, a nie `safe(x) if x else None`.
    """
    return safe(value) if value else None
