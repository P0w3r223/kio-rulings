"""Wspólne przygotowanie testów.

Jedna rzecz, i to ta, której brak w `ceidg-tool` opisano jako powód istnienia
`forget_secrets()`: `_KNOWN_SECRETS` jest stanem na poziomie modułu, więc bez czyszczenia
pierwszy test rejestrujący sekret zmienia wynik każdego następnego. Ciek stanu między
testami jest tą klasą usterki, która najpierw daje zielone przebiegi, a potem czerwony
przy zmianie kolejności testów.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from kio_tool.config import forget_secrets


@pytest.fixture(autouse=True)
def _czysty_rejestr_sekretow() -> Iterator[None]:
    forget_secrets()
    yield
    forget_secrets()
