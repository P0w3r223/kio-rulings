"""Parser: bajty → struktury. Pakiet czysty, rekursywnie (reguła 1).

Nie widzi sieci, bazy ani terminala — skan reguły 1 w `tests/test_boundaries.py` obejmuje każdy
moduł tego katalogu bez dopisywania go do listy. `PARSE_VERSION` stoi w `details.py`;
`przelicz` przelicza wyłącznie wersje starsze (architektura 4.5).
"""

from __future__ import annotations
