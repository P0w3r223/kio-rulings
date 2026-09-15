"""kio-tool — lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("kio-tool")
except PackageNotFoundError:  # pragma: no cover - drzewo źródłowe bez instalacji
    __version__ = "0.0.0+nieznana"

__all__ = ["__version__"]
