"""Neutralizacja wrogich napisów ze źródła — moduł czysty, wspólny dla eksportu i ekranu.

Przeniesione z `ceidg-tool` **z podwyższonym priorytetem** (audyt 6). Tam wrogim wejściem była
nazwa firmy z rejestru — kilkadziesiąt znaków. Tutaj wrogim wejściem jest **cały dokument**:
kilkanaście stron, w których stoją cytaty z ofert, nazwy plików, fragmenty specyfikacji
i przytoczenia pism stron. Wszystko to trafia do arkusza, gdzie wiodące `=` jest formułą,
i na ekran, gdzie `rich` czyta nawiasy kwadratowe jako znaczniki.

**Priorytet podniesiono, a zamek został ten sam — i to był błąd, zamknięty 2026-09-15.**
Pierwsza wersja tego modułu była bajt w bajt kopią wersji z CEIDG, czyli `ord(ch) >= 32`.
To pokrywa wyłącznie C0. Zmierzone na tej funkcji przed poprawką: przechodziły `\x9b` (CSI
w postaci jednobajtowej, czyli sterowanie terminalem bez ESC), `\x7f` (DEL), `‮`
(RIGHT-TO-LEFT OVERRIDE) i izolaty kierunku `⁦`–`⁩`, oraz `​` (spacja zerowej
szerokości). Znak dwukierunkowy nie zależy przy tym od kaprysów terminala: odwraca kolejność
wyświetlania tak samo w arkuszu, więc komórka może pokazywać co innego, niż zawiera. Przy
materiale pisanym przez osoby trzecie jest to dokładnie ta klasa znaków, dla której ten
moduł istnieje.

Konwersja na `str.translate` z prekompilowaną tablicą jest przy okazji, ale niebagatelna:
zmierzone na dokumencie 100 kB, 20 powtórzeń — generator z `join` 9,15 ms, `translate`
0,08 ms. Dla 30 tys. dokumentów i jednego przejścia to różnica między ~274 s a ~2,5 s,
a przejść jest więcej niż jedno (ścieżka do arkusza i ścieżka na ekran).
"""

from __future__ import annotations

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t")
"""Prefiksy, które arkusz i CSV interpretują jako formułę.

`\\r` **nie** stoi na tej liście, choć stał w wersji z CEIDG. Powód: `strip_control` usuwa go
wcześniej, więc `cleaned.startswith("\\r")` nigdy nie zachodziło — stała deklarowała pokrycie,
którego nie miała. Tabulator zostaje, bo `KEEP_CONTROL` go przepuszcza.
"""

KEEP_CONTROL = {"\t", "\n"}
"""Jedyne znaki sterujące, które przeżywają. Tabulator i nowa linia niosą w orzeczeniu
strukturę: wcięcia list i podział akapitów."""

# Znaki formatujące (kategoria Unicode `Cf`) wyliczone **punktami kodowymi, nie dosłownie**.
# Pierwsza wersja tej listy zawierała same znaki wpisane wprost — czyli niewidoczne bajty
# w pliku źródłowym, których czytelnik przeglądu nie ma jak zweryfikować, i to w module,
# którego zadaniem jest usuwanie dokładnie takich bajtów. Zapis liczbowy z nazwą obok jest
# jedyną postacią, w której tę listę da się sprawdzić okiem.
_ZNAKI_FORMATUJACE: tuple[tuple[int, str], ...] = (
    (0x200B, "ZERO WIDTH SPACE — niewidoczny podział, rozbija wyszukiwanie frazy"),
    (0x200C, "ZERO WIDTH NON-JOINER"),
    (0x200D, "ZERO WIDTH JOINER"),
    (0x200E, "LEFT-TO-RIGHT MARK"),
    (0x200F, "RIGHT-TO-LEFT MARK"),
    (0x202A, "LEFT-TO-RIGHT EMBEDDING"),
    (0x202B, "RIGHT-TO-LEFT EMBEDDING"),
    (0x202C, "POP DIRECTIONAL FORMATTING"),
    (0x202D, "LEFT-TO-RIGHT OVERRIDE"),
    (0x202E, "RIGHT-TO-LEFT OVERRIDE — odwraca kolejność wyświetlania także w arkuszu"),
    (0x2066, "LEFT-TO-RIGHT ISOLATE"),
    (0x2067, "RIGHT-TO-LEFT ISOLATE"),
    (0x2068, "FIRST STRONG ISOLATE"),
    (0x2069, "POP DIRECTIONAL ISOLATE"),
    (0xFEFF, "ZERO WIDTH NO-BREAK SPACE / BOM wewnątrz tekstu"),
)


def _zbuduj_tablice() -> dict[int, None]:
    """Tablica usuwanych punktów kodowych. Liczona raz, przy imporcie."""
    usuwane: dict[int, None] = {}
    for kod in range(0x00, 0x20):  # C0
        if chr(kod) not in KEEP_CONTROL:
            usuwane[kod] = None
    for kod in range(0x7F, 0xA0):  # DEL oraz C1
        usuwane[kod] = None
    for kod, _nazwa in _ZNAKI_FORMATUJACE:
        usuwane[kod] = None
    return usuwane


_TABLICA = _zbuduj_tablice()


def strip_control(text: str) -> str:
    """Usuwa znaki sterujące i formatujące; zostawia tabulator i nową linię.

    Zakres: C0 bez `KEEP_CONTROL`, DEL, C1 (`\\x80`–`\\x9f`) oraz wyliczone znaki
    dwukierunkowe i zerowej szerokości. Reszta tekstu przechodzi bez zmian — funkcja usuwa
    szum, nie poprawia źródła.
    """
    return text.translate(_TABLICA)


def sanitize_text(text: str) -> str:
    """Usuwa znaki sterujące i neutralizuje prefiksy interpretowane jako formuła.

    Apostrof poprzedzający wartość jest widoczny dla czytelnika arkusza, a w polskim tekście
    prawniczym myślnik na początku linii jest częsty (wyliczenia). Czy eksporter ma zamiast
    tego wymuszać typ komórki, rozstrzyga się przy `exporter.py`; decyzja zapada tutaj i to
    jest jedyne miejsce, które trzeba będzie wtedy zmienić.
    """
    cleaned = strip_control(text)
    if cleaned.startswith(FORMULA_PREFIXES):
        return "'" + cleaned
    return cleaned
