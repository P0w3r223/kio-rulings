"""Protokół zdarzeń postępu — `source/` i `store` nie znają `rich` ani konsoli.

Zestaw zdarzeń jest własny, nie przeniesiony, i wynika wprost z zasady 7.2 audytu:
**puls liczy się w żądaniach wysłanych albo dokumentach zapisanych, nigdy w stronach
wyników ani w dopasowanych sprawach.** Pomyłka o jedną warstwę dała w `ceidg-tool` cztery
osobne usterki jednego dnia, w tym wygaśnięcie dzierżawy blokady pod pracującym procesem.

Dlatego `on_page` istnieje jako informacja dla operatora, ale to `on_request` i `on_document`
są zdarzeniami, na których wolno oprzeć puls i odświeżanie dzierżawy.
"""

from __future__ import annotations

from typing import Protocol


class Events(Protocol):
    """Odbiorca zdarzeń; implementacja konsolowa powstaje w fazie 3."""

    def on_request(self, endpoint: str, status: int, elapsed_s: float) -> None:
        """Żądanie wysłane i rozliczone. Jedna z dwóch podstaw pulsu."""
        ...

    def on_document(self, saved: int, total: int | None) -> None:
        """Dokument zapisany do korpusu. Druga podstawa pulsu.

        `total` bywa `None`, bo przy skanie przestrzeni identyfikatorów nie wiadomo z góry,
        ile dokumentów wpadnie — a pasek, który udaje, że wie, kłamie operatorowi o czasie.
        """
        ...

    def on_version(self, doc_id: str, content_sha256: str) -> None:
        """Nowa **wersja** treści istniejącego dokumentu.

        Zdarzenie osobne od `on_document`, bo to jest moment, w którym źródło zmieniło
        treść pod tym samym identyfikatorem: sprostowanie albo niedeterministyczne
        renderowanie (pomiar 19). Operator ma się o tym dowiedzieć, a nie odkryć to
        w bazie po miesiącu.
        """
        ...

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        """Limiter wstrzymuje przebieg. `resume_at_epoch` idzie też do dziennika.

        Sam czas trwania nie odróżnia po fakcie wstrzymania przez limiter od uśpienia
        laptopa — stąd przewidywany moment wznowienia, a nie tylko liczba sekund.
        """
        ...

    def on_page(self, page_index: int, candidates: int, total: int | None) -> None:
        """Strona listowania przetworzona. Informacja, nie podstawa pulsu."""
        ...

    def on_parse(self, done: int, total: int) -> None:
        """Postęp przeliczania korpusu. Zero żądań na tej ścieżce."""
        ...

    def on_export(self, done: int, total: int) -> None: ...

    def on_message(self, text: str) -> None: ...

    def close(self) -> None:
        """Kończy żywy pasek postępu.

        Należy do protokołu, bo pasek musi zgasnąć **zanim** cokolwiek innego trafi na ekran.
        W CEIDG dopóki `close()` wywoływał tylko `finally` w `cli.py`, w kreatorze pasek żył
        do końca sesji i nadpisywał podsumowanie oraz pytanie o zapis — program czekał na
        odpowiedź, której nie było widać, i wyglądał na zawieszony.
        """
        ...


class NullEvents:
    """Odbiorca, który nic nie robi — domyślny w testach i w bibliotece."""

    def on_request(self, endpoint: str, status: int, elapsed_s: float) -> None:
        return None

    def on_document(self, saved: int, total: int | None) -> None:
        return None

    def on_version(self, doc_id: str, content_sha256: str) -> None:
        return None

    def on_wait(self, seconds: float, reason: str, resume_at_epoch: float) -> None:
        return None

    def on_page(self, page_index: int, candidates: int, total: int | None) -> None:
        return None

    def on_parse(self, done: int, total: int) -> None:
        return None

    def on_export(self, done: int, total: int) -> None:
        return None

    def on_message(self, text: str) -> None:
        return None

    def close(self) -> None:
        return None


# Protokół strukturalny jest weryfikowany w miejscu przypisania, a nie w definicji klasy.
# Bez tej linii dopisanie metody do `Events` bez dopisania jej do `NullEvents` przechodziło
# przez `mypy --strict`, `ruff` i całą suitę testów (przegląd kodu 2026-09-15).
_ZGODNOSC_Z_PROTOKOLEM: Events = NullEvents()
