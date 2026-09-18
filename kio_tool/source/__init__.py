"""Kanały akwizycji — pakiet na kanał (ADR-0003, rozstrzygnięcie 1B; reguła 21).

Wyłącznie re-eksport typów wspólnych. Roster kanałów niesie `registry.REGISTRY` i nic poza nim:
wypisanie go drugi raz tutaj byłoby drugą listą do uzgadniania, przed którą ADR-0003 broni
`SourceName` jako `NewType`.
"""

from __future__ import annotations

from .protocol import BezSladu, Candidate, Channel, RawDocument, Scope, SladZadan

__all__ = ["BezSladu", "Candidate", "Channel", "RawDocument", "Scope", "SladZadan"]
