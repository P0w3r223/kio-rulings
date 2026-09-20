"""Korpus pokazowy generowany w procesie — czysty, deterministyczny, fikcyjny (ADR-0008 Z-11).

Moduł czysty (reguła 1): bez sieci, bazy, systemu plików i `os`. Dostaje wzorce (rozkłady
i etykiety przepisów z `wzorce.yaml`, zbudowane skryptem z bazy operatora) i ziarno, oddaje
dokumenty. **Nic tu nie pochodzi z pamięci** poza tym, co jest jawnie fikcją:

- osoby i strony — z puli nazw mówiących (`Przykładowa`, `Pokazowy`), których w żadnym rejestrze
  nie ma; test pilnuje, że żaden napis puli nie występuje w polach osobowych złotych plików;
- sygnatury — wyłącznie `KIO 9000/23`…`KIO 9999/24`, ponad dwa razy powyżej zmierzonego maksimum
  numeru (E1); rok sygnatury rozjeżdża się z datą wydania jak w korpusie (186 z 295 w styczniu);
- treść — zdania-wypełniacze jawnie pokazowe, z hasłami do wyszukania; żadnego „Izba wskazała,
  że…", które brzmi wiarygodnie niezależnie od prawdy (doktryna 7.1);
- adresy — domena zastrzeżona `pokaz.invalid` (RFC 2606), nigdy wzorzec prawdziwego serwisu.

Cechy tekstu z PDF-a (wysuw strony, łamanie wiersza w zdaniu, nagłówek rozstrzelony) są odtwarzane
w proporcjach z pomiaru 5, żeby parser fazy 2 miał na pokazie ten sam materiał co na korpusie —
i żeby raport pokrycia na bazie pokazowej nie był pusty w żadnej kategorii.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

ZIARNO = 20260919
ZNACZNIK_TRESCI = "[TRYB POKAZOWY — dokument fikcyjny, wygenerowany przez kio-tool]"
"""Pierwszy wiersz treści każdego dokumentu (ADR-0008 Z-3, znacznik 6)."""
DOMENA = "https://pokaz.invalid"
NUMER_OD = 9000
NUMER_DO = 9999

PRZEWODNICZACY = ("Anna Przykładowa", "Jan Pokazowy", "Ewa Fikcyjna", "Piotr Wzorcowy")
PROTOKOLANCI = ("Marta Testowa", "Adam Demonstracyjny", "Zofia Umowna")
ODWOLUJACY = (
    "Pokazowa Spółka Budowlana sp. z o.o.",
    "Fikcyjne Usługi Medyczne S.A.",
    "Przykładowe Konsorcjum Drogowe",
    "Wzorcowa Firma Sprzątająca s.c.",
    "=SUMA(A1:A9) Spółka Pokazowa",
    "[link=https://pokaz.invalid]Klik[/link] Pokazowa sp. z o.o.",
    "Pokazowa \x1b[31mCzerwona\x1b[0m sp. z o.o.",
)
"""Trzy ostatnie są wrogie celowo: formuła arkusza, znacznik `rich`, sekwencja ESC — pokaz ma
pokazać `safetext` i `richtext.safe` w działaniu, nie tylko o nich mówić."""
ZAMAWIAJACY = (
    "Gmina Przykładowo",
    "Szpital Pokazowy w Fikcyjnej Woli",
    "Zarząd Dróg Wzorcowych",
    "Uniwersytet Demonstracyjny",
)
HASLA = (
    "wadium",
    "rażąco niska cena",
    "termin związania ofertą",
    "wyjaśnienia treści oferty",
    "tajemnica przedsiębiorstwa",
    "doświadczenie wykonawcy",
    "kryteria oceny ofert",
)
SENTENCJE = {
    "oddalono": "oddala odwołanie",
    "uwzglednione": "uwzględnia odwołanie i nakazuje zamawiającemu powtórzenie oceny ofert",
    "umorzono": "umarza postępowanie odwoławcze",
    "odrzucono": "odrzuca odwołanie",
    "inne": "rozstrzyga w sposób pokazowy",
}

UDZIAL_ROZSTRZELONEGO = 88 / 341
"""Nagłówek rozstrzelony spacjami — 88 z 341 dokumentów (pomiar 5, 2026-09-19)."""
UDZIAL_CYTOWAN = 194 / 443
"""Dokumenty z cytowaniami — 194 z 443 (pomiar 22, 2026-09-19)."""
UDZIAL_WIELU_SYGNATUR = 17 / 295
"""Dokumenty z więcej niż jedną sygnaturą — 16 × 2 i 1 × 3 z 295 (pomiar 17, dopełnienie)."""
UDZIAL_ROKU_POPRZEDNIEGO = 186 / 295
"""Rok sygnatury ≠ rok daty w styczniu — 186 z 295 (pomiar 3a, sprostowanie)."""
SZEROKOSC_WIERSZA = 90


@dataclass(frozen=True)
class Wzorce:
    """Dane odniesienia z `wzorce.yaml` — rozkłady i etykiety, bez pól osobowych."""

    rozstrzygniecia: Mapping[str, int]
    etykiety_przepisow: Sequence[tuple[str, int]]
    ustawy_pzp: Mapping[str, int]
    """Rozkład ustaw rozpoznanych w treści. Stała `UDZIAL_PELNEGO_TYTULU = 327 / 443` stała
    tu do przeglądu kodu fazy 3 (2026-09-20) i przepisywała ręcznie sumę dwóch liczb z tego
    właśnie pola — po odtworzeniu wzorców z innej bazy rozjechałaby się po cichu, bo nic
    nie porównywało jej ze źródłem."""

    @property
    def udzial_pelnego_tytulu(self) -> float:
        """Udział dokumentów nazywających Pzp pełnym tytułem: ustawa rozpoznana z treści."""
        razem = sum(self.ustawy_pzp.values())
        rozpoznane = razem - self.ustawy_pzp.get("nieustalone", 0)
        return rozpoznane / razem if razem else 0.0


@dataclass(frozen=True)
class DokumentPokazowy:
    """Rekord pokazowy w naszych nazwach — `demo/atlas.py` przepisuje go na pola z kontraktu."""

    slug: str
    sygnatury: tuple[str, ...]
    data_wydania: date
    data_rozprawy: date | None
    rodzaj: str
    rozstrzygniecie: str
    rozstrzygniecie_surowe: str
    przewodniczacy: str
    odwolujacy: str
    zamawiajacy: str
    przepisy: tuple[str, ...]
    koszty: float | None
    url_zrodla: str
    tresc: str
    cytowane: tuple[str, ...] = field(default=())


def dni_robocze(od: date, do: date) -> list[date]:
    dni = []
    dzien = od
    while dzien <= do:
        if dzien.weekday() < 5:
            dni.append(dzien)
        dzien += timedelta(days=1)
    return dni


def generuj(
    wzorce: Wzorce,
    *,
    ziarno: int = ZIARNO,
    od: date = date(2024, 1, 2),
    do: date = date(2024, 3, 29),
    na_dzien: int = 6,
) -> tuple[DokumentPokazowy, ...]:
    """Korpus pokazowy: `na_dzien` orzeczeń na dzień roboczy, deterministycznie z `ziarno`."""
    los = random.Random(ziarno)
    dni = dni_robocze(od, do)
    numery = los.sample(range(NUMER_OD, NUMER_DO + 1), k=len(dni) * na_dzien)
    # Numery wolne, czyli takie, które nie są niczyją sygnaturą główną: stąd bierze numer
    # sprawa połączona. Dopisane po przeglądzie kodu fazy 3 (2026-09-20) — doklejanie
    # `numer + 1` bez patrzenia na pulę dawało 7 z 384 dokumentów, których druga sygnatura
    # była główną sygnaturą innego dokumentu. W rejestrze numery sprawy połączonej należą
    # do tej jednej sprawy, więc pokaz uczył własności, której źródło nie ma (mina 4).
    wolne = sorted(set(range(NUMER_OD, NUMER_DO + 1)) - set(numery))
    dokumenty: list[DokumentPokazowy] = []
    for i, numer in enumerate(numery):
        dokumenty.append(_dokument(los, wzorce, numer, dni[i // na_dzien], dokumenty, wolne))
    return tuple(dokumenty)


def _wolny_po(numer: int, wolne: list[int]) -> int | None:
    """Najbliższy numer powyżej `numer`, którego nikt nie ma za sygnaturę główną.

    Zwykle jest to `numer + 1` — sprawy połączone mają w rejestrze numery kolejne — a gdy ten
    numer jest już czyjąś sygnaturą, następny wolny. `None` znaczy, że pula się skończyła:
    dokument zostaje wtedy z jedną sygnaturą, bo lepszy mniejszy udział spraw połączonych
    niż dwa dokumenty o tej samej sygnaturze."""
    return next((n for n in wolne if n > numer), None)


def _dokument(
    los: random.Random,
    wzorce: Wzorce,
    numer: int,
    dzien: date,
    poprzednie: Sequence[DokumentPokazowy],
    wolne: list[int],
) -> DokumentPokazowy:
    rok = (
        dzien.year - 1
        if dzien.month == 1 and los.random() < UDZIAL_ROKU_POPRZEDNIEGO
        else dzien.year
    )
    glowna = f"KIO {numer}/{rok % 100:02d}"
    sygnatury = [glowna]
    if los.random() < UDZIAL_WIELU_SYGNATUR:
        drugi = _wolny_po(numer, wolne)
        if drugi is not None:
            wolne.remove(drugi)
            sygnatury.append(f"KIO {drugi}/{rok % 100:02d}")
    rozstrzygniecie = _wybierz(los, wzorce.rozstrzygniecia)
    rodzaj = "postanowienie" if rozstrzygniecie in ("umorzono", "odrzucono") else "wyrok"
    przepisy = _przepisy(los, wzorce)
    # Udział liczony per dokument, nie per kandydat: dwa losowania po 43,8 % dawały 68,5 %
    # dokumentów z cytowaniem — złapane przez `tests/test_demo_cechy.py` (Z-12).
    cytowane: tuple[str, ...] = ()
    if poprzednie and los.random() < UDZIAL_CYTOWAN:
        wybrane = los.sample(list(poprzednie), k=min(los.randint(1, 2), len(poprzednie)))
        cytowane = tuple(d.sygnatury[0] for d in wybrane)
    rozprawa = dzien - timedelta(days=los.choice((0, 0, 1, 7))) if rodzaj == "wyrok" else None
    osoby = (los.choice(PRZEWODNICZACY), los.choice(PROTOKOLANCI))
    strony = (los.choice(ODWOLUJACY), los.choice(ZAMAWIAJACY))
    tresc = _tresc(
        los,
        sygnatury,
        rodzaj,
        rozstrzygniecie,
        dzien,
        osoby,
        strony,
        przepisy,
        cytowane,
        wzorce.udzial_pelnego_tytulu,
    )
    slug = f"kio-{numer}-{rok % 100:02d}"
    return DokumentPokazowy(
        slug=slug,
        sygnatury=tuple(sygnatury),
        data_wydania=dzien,
        data_rozprawy=rozprawa,
        rodzaj=rodzaj,
        rozstrzygniecie=rozstrzygniecie,
        rozstrzygniecie_surowe=SENTENCJE[rozstrzygniecie].capitalize(),
        przewodniczacy=osoby[0],
        odwolujacy=strony[0],
        zamawiajacy=strony[1],
        przepisy=przepisy,
        koszty=None if rozstrzygniecie == "umorzono" else float(los.choice((7500, 15000, 20000))),
        url_zrodla=f"{DOMENA}/orzeczenie/{slug}",
        tresc=tresc,
        cytowane=cytowane,
    )


def _wybierz(los: random.Random, rozklad: Mapping[str, int]) -> str:
    klucze = [k for k in rozklad if k != "brak"]
    return los.choices(klucze, weights=[rozklad[k] for k in klucze])[0]


def _przepisy(los: random.Random, wzorce: Wzorce) -> tuple[str, ...]:
    if not wzorce.etykiety_przepisow or los.random() < 41 / 443:
        return ()
    etykiety = [e for e, _ in wzorce.etykiety_przepisow]
    wagi = [n for _, n in wzorce.etykiety_przepisow]
    return tuple(dict.fromkeys(los.choices(etykiety, weights=wagi, k=los.randint(1, 3))))


def _tresc(
    los: random.Random,
    sygnatury: Sequence[str],
    rodzaj: str,
    rozstrzygniecie: str,
    dzien: date,
    osoby: tuple[str, str],
    strony: tuple[str, str],
    przepisy: Sequence[str],
    cytowane: Sequence[str],
    udzial_pelnego_tytulu: float,
) -> str:
    """Treść w kształcie orzeczenia po ekstrakcji z PDF-a — kotwice z pomiaru 5, cechy PDF-a."""
    naglowek = "POSTANOWIENIE" if rodzaj == "postanowienie" else "WYROK"
    kotwica = "postanawia:" if rodzaj == "postanowienie" else "orzeka:"
    tytul = "Uz as adnienie" if los.random() < UDZIAL_ROZSTRZELONEGO else "Uzasadnienie"
    ustawa = (
        "ustawy z dnia 11 września 2019 r. – Prawo zamówień publicznych"
        if los.random() < udzial_pelnego_tytulu
        else "ustawy Pzp"
    )
    haslo = los.choice(HASLA)
    zdania = [
        f"Zamawiający {strony[1]} prowadzi postępowanie pokazowe na podstawie {ustawa}.",
        f"Odwołujący {strony[0]} podniósł zarzuty dotyczące zagadnienia: {haslo}.",
        *(f"Zdanie pokazowe o przepisie {p} — bez treści prawnej." for p in przepisy),
        *(f"Zdanie pokazowe z odesłaniem do sygn. akt {s} (sygnatura fikcyjna)." for s in cytowane),
        f"Zdanie pokazowe o pojęciu: {haslo}. Treść jest wypełniaczem, nie oceną prawną.",
    ]
    if los.random() < 0.05:
        zdania.append("Zdanie pokazowe z odesłaniem nierozpoznawalnym: sygn. akt: 9999/24.")
    uzasadnienie = _lam(" ".join(zdania * los.randint(2, 6)))
    return "\n".join(
        [
            ZNACZNIK_TRESCI,
            f"Sygn. akt: {', '.join(sygnatury)}",
            "",
            naglowek,
            f"z dnia {dzien.day} {_MIESIACE[dzien.month]} {dzien.year} r.",
            "Krajowa Izba Odwoławcza - w składzie:",
            f"Przewodniczący:{osoby[0]}",
            f"Protokolant: {osoby[1]}",
            _lam(
                "po rozpoznaniu na posiedzeniu pokazowym odwołania wniesionego przez wykonawcę "
                f"{strony[0]} w postępowaniu prowadzonym przez zamawiającego {strony[1]}"
            ),
            kotwica,
            f"1. {SENTENCJE[rozstrzygniecie]},",
            "2. kosztami postępowania obciąża stronę pokazową.",
            "Na orzeczenie - w terminie 14 dni od dnia jego doręczenia - przysługuje skarga za",
            "pośrednictwem Prezesa Krajowej Izby Odwoławczej do Sądu Okręgowego w Warszawie.",
            "\f",
            "Przewodniczący: ……………………",
            f"Sygn. akt: {sygnatury[0]}",
            tytul,
            uzasadnienie,
            "Przewodniczący: ……………………",
        ]
    )


def _lam(tekst: str) -> str:
    """Łamanie wiersza w środku zdania co ~90 znaków — cecha 100 % dokumentów (pomiar 5)."""
    wiersze: list[str] = []
    biezacy = ""
    for slowo in tekst.split(" "):
        if biezacy and len(biezacy) + len(slowo) + 1 > SZEROKOSC_WIERSZA:
            wiersze.append(biezacy)
            biezacy = slowo
        else:
            biezacy = f"{biezacy} {slowo}" if biezacy else slowo
    wiersze.append(biezacy)
    return "\n".join(wiersze)


_MIESIACE = {
    1: "stycznia",
    2: "lutego",
    3: "marca",
    4: "kwietnia",
    5: "maja",
    6: "czerwca",
    7: "lipca",
    8: "sierpnia",
    9: "września",
    10: "października",
    11: "listopada",
    12: "grudnia",
}
