"""Roster kanałów — jedyne miejsce, które go wymienia (ADR-0003, reguła 21).

Literał słownika, nie pętla ani komprehensja: skan reguły 21 w `tests/test_boundaries.py` czyta
klucze **ze składni** i porównuje je z katalogami niosącymi `channel.py` i `contract.yaml`.
`REGISTRY` zbudowane dynamicznie jest dla skanu nieczytelne i zapala go głośno — celowo, bo
„nie wiem" ma być czerwone, a nie równe pustemu zbiorowi.

Typ wartości jest dziś konkretną klasą, nie `type[Channel]`: protokół nie deklaruje
konstruktora, a `pipeline` buduje kanał z czterech zależności. Interfejs konstrukcji wraca do
protokołu przy drugim kanale, kiedy będzie z czego go wyprowadzić (ADR-0005 Z-7).
"""

from __future__ import annotations

from ..docid import SourceName
from .atlas.channel import AtlasChannel

REGISTRY: dict[SourceName, type[AtlasChannel]] = {SourceName("atlas"): AtlasChannel}
