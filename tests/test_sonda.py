"""Strażnik dyspozytora sondy — `scripts/sonda.py`: pomiar 3 (Atlas), spis pomiarów, `main`.

Do 2026-09-18 ten plik niósł 2 932 linie i wszystkie testy sondy; rozbicie po module poszło
razem z kodem (`test_logbook.py`, `test_console.py`, `test_zadanie.py`, `test_httpclient.py`,
`test_pomiar_uzp.py`, `test_pomiar_saos.py`, `test_pomiar_licencje.py`), wspólne narzędzia do
`tests/wsparcie_sondy.py`, a fixtures do `tests/conftest.py`. Zostało to, co należy do
dyspozytora: Atlas, który nie ma jeszcze własnego pliku, bramka wyjścia widziana per pomiar,
wejście programu, rachunek żądań i kod wyjścia oraz maskowanie na całej drodze przebiegu.

Materiał i kształt atrapy opisuje nagłówek `wsparcie_sondy.py`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import httpx

# Moduły sondy mieszkają w `scripts/`, który nie jest pakietem; ścieżkę dokłada
# `tests/conftest.py` i tam stoi powód. Dla `ruff` wyglądają jak zależność zewnętrzna
# i dlatego stoją w tym bloku, a nie przy `kio_tool`.
import pomiar_uzp
import pytest
import sonda
import zadanie

from kio_tool.config import ATLAS_HOSTS, SAOS_HOSTS, UZP_HOSTS, mask_tokens
from tests.wsparcie_sondy import (
    ATLAS_LISTA_OK,
    BOT_CHECK,
    KLUCZ_TESTOWY,
    SAOS_DUMP_OK,
    SCIEZKA_ATLAS,
    SCIEZKA_ATLAS_DOKUMENT,
    SCIEZKA_ATLAS_DOKUMENTACJA,
    SCIEZKA_KORZEN,
    SCIEZKA_SAOS,
    SCIEZKA_UZP_KONTROLA,
    SCIEZKA_UZP_TRESC,
    SCIEZKA_UZP_WYNIKI,
    TRESC_19,
    UA_TESTOWY,
    UZP_DETAILS_OK,
    Odpowiedz,
    Serwis,
    ZegarTestowy,
    scenariusz_atlas_ok,
    serwis_19,
    uzp_scenariusz,
    wiersze_dziennika,
)

# --- kontrola hosta po odmowie: Atlas i SAOS -----------------------------------------------


def test_pomiar_atlas_po_odmowie_puka_raz_w_korzen_hosta(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Własność 5: odmowa bez kontroli nie rozróżnia „punkt odmawia" od „host odmawia".

    Pomiar 1 pokazał, ile jest warta ta różnica: bez kontroli na `ftp.gnu.org` cisza na
    porcie 21 równie dobrze mogła być zaporą po stronie mierzącego. Jedno żądanie, na korzeń,
    po odmowie — nie więcej.
    """
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(
        {SCIEZKA_ATLAS: Odpowiedz(status=403, tresc=b"forbidden"), SCIEZKA_KORZEN: Odpowiedz()}
    )
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_ATLAS), ("GET", SCIEZKA_KORZEN)]
    assert [w.nazwa for w in wyniki] == [
        "atlas_3a_lista",
        "atlas_kontrola_hosta",
        "atlas_3a_dokument",
    ]
    assert "kontrola po odmowie" in wyniki[1].uwaga
    assert wyniki[2].wyslane is False, (
        "po odmowie listy dokument ma zostać na liście jako wpis niewysłany, nie zniknąć"
    )


def test_pomiar_atlas_bez_odmowy_nie_puka_w_korzen(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kontrola jest reakcją na odmowę, a nie stałym kosztem przebiegu. Żądanie wysłane bez
    powodu kosztuje cudzy serwer tyle samo co potrzebne."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_ATLAS), ("GET", SCIEZKA_ATLAS_DOKUMENT)]
    assert len(wyniki) == 2


def test_pomiar_atlas_po_bot_checku_ze_statusem_200_tez_puka_w_korzen(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spięcie oceny kształtu z kontrolą hosta. Status 200 i treść nie ta znaczy „coś tu
    odmawia" — i właśnie wtedy pytanie „punkt czy host" ma sens."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis({SCIEZKA_ATLAS: Odpowiedz(tresc=BOT_CHECK), SCIEZKA_KORZEN: Odpowiedz()})
    podstaw(serwis)

    sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_ATLAS), ("GET", SCIEZKA_KORZEN)]


def test_pomiar_atlas_bez_klucza_zapisuje_poziom_anonimowy(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Poziom dostępu jest częścią wyniku, nie szczegółem uruchomienia: „pełny tekst"
    zmierzony anonimowo odpowiada na inne pytanie niż zadane."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert "anonimowy" in wyniki[0].uwaga
    assert sonda.ATLAS_KEY_ENV in wyniki[0].uwaga
    assert "X-Api-Key" not in serwis.zadania[0].headers


def test_pomiar_atlas_z_kluczem_wysyla_go_i_rejestruje_do_maskowania(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dwie połowy jednego zdania. Klucz ma dojść do serwisu **i** ma być od tej chwili
    maskowany — bo zaraz potem ten sam przebieg dopisuje wiersze do pliku w historii
    repozytorium. Rejestracja bez wysłania mierzy nie ten poziom dostępu; wysłanie bez
    rejestracji zostawia klucz w `docs/dziennik_zadan.md` na zawsze.
    """
    klucz = "sekretny-klucz-atlasu"
    monkeypatch.setenv(sonda.ATLAS_KEY_ENV, klucz)
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.zadania[0].headers["X-Api-Key"] == klucz
    assert serwis.zadania[1].headers["X-Api-Key"] == klucz, (
        "dokument ma iść z tym samym kluczem co lista — inaczej mierzy inny poziom dostępu"
    )
    assert mask_tokens(f"?key={klucz}") == "?key=<token>", (
        "klucz nie został zgłoszony do maskowania"
    )
    assert "z kluczem" in wyniki[0].uwaga


# --- pomiar 3a: dokument po liście, adres odczytany, nie zgadnięty ---------------------------
#
# Poprawka z 2026-09-18 (przegląd architektoniczny, F-1). Do tego dnia pomiar wołał wyłącznie
# listę `/api/kio` i deklarował odpowiedź na pytanie o pełny tekst — a listę z definicji niosą
# skróty. Drugie żądanie idzie pod `/api/kio/{slug}` i jest jedynym, które na to pytanie
# odpowiada. Slug pochodzi z cudzej odpowiedzi, więc jest tu obcym napisem na granicy: trafia
# do adresu wyłącznie po kontroli `httpclient.powod_odrzucenia_segmentu` (do etapu III
# `WZOR_SLUGA` i `SEGMENTY_KROPKOWE` w `sonda.py`), a inaczej zostaje niewysłany z powodem.


def test_pomiar_atlas_czyta_dokument_pierwszego_rekordu_z_listy(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pełny tekst mierzy się na dokumencie, a dokument bierze adres z pierwszego rekordu listy."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_ATLAS), ("GET", SCIEZKA_ATLAS_DOKUMENT)]
    assert wyniki[1].nazwa == "atlas_3a_dokument"
    assert wyniki[1].ksztalt_zgodny is True, wyniki[1].ksztalt_uwaga
    assert "`content`" in wyniki[1].ksztalt_uwaga, (
        "ocena dokumentu ma nazwać najdłuższe pole tekstowe — to jest odpowiedź na pytanie "
        "o pełny tekst"
    )
    assert "tresc wymyslona" not in wyniki[1].ksztalt_uwaga, "wartość pola wyciekła do uwagi"


def test_pomiar_atlas_prosi_o_pelna_strone_listy_od_najstarszych(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`per_page` na maksimum z dokumentacji i `sort=oldest`: ten sam koszt w żądaniach, a sto
    rekordów jest materiałem pomiaru 17 i odpowiedzią na „od kiedy sięga zbiór"."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    sonda.pomiar_atlas(UA_TESTOWY)

    parametry = serwis.zadania[0].url.params
    assert parametry["per_page"] == str(sonda.ATLAS_REKORDOW_NA_STRONE) == "100"
    assert parametry["sort"] == "oldest"


def test_pomiar_atlas_bez_sluga_w_liscie_nie_zgaduje_adresu_dokumentu(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lista bez pola `slug` jest wynikiem pomiaru o kształcie listy: dokument zostaje
    niewysłany z powodem, a sonda nie składa adresu z niczego innego."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis({SCIEZKA_ATLAS: Odpowiedz(tresc=b'{"data": [{"id": 1}]}')})
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_ATLAS)]
    assert wyniki[1].nazwa == "atlas_3a_dokument" and wyniki[1].wyslane is False
    assert "`slug`" in wyniki[1].uwaga


def test_pomiar_atlas_slug_spoza_alfabetu_nie_trafia_do_adresu(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Slug z ukośnikiem albo pytajnikiem zmieniłby żądanie w inne niż zaplanowane. Nie idzie
    do adresu i nie idzie na ekran — powód niesie długość, nie treść."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis({SCIEZKA_ATLAS: Odpowiedz(tresc=b'{"data": [{"slug": "a/b?c=d"}]}')})
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_ATLAS)]
    assert wyniki[1].wyslane is False
    assert "a/b?c=d" not in wyniki[1].uwaga, "zakwestionowany slug wyszedł na ekran"
    assert "długość 7" in wyniki[1].uwaga


def test_pomiar_atlas_niezgodny_ksztalt_dokumentu_jest_wynikiem_nie_odmowa(
    podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Host już odpowiedział listą, więc kontrola hosta po dokumencie nie ma czego
    rozstrzygać — niezgodny kształt dokumentu zostaje w ocenie, bez trzeciego żądania."""
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(
        {
            SCIEZKA_ATLAS: Odpowiedz(tresc=ATLAS_LISTA_OK),
            SCIEZKA_ATLAS_DOKUMENT: Odpowiedz(tresc=b'{"error": "not found"}'),
        }
    )
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)

    assert serwis.slad == [("GET", SCIEZKA_ATLAS), ("GET", SCIEZKA_ATLAS_DOKUMENT)]
    assert wyniki[1].ksztalt_zgodny is False
    assert "error" in wyniki[1].ksztalt_uwaga


@pytest.mark.parametrize(
    ("material", "oczekiwany_slug", "fragment_powodu"),
    [
        (b'{"data": [{"slug": "kio-1-24", "id": 1}]}', "kio-1-24", ""),
        (b'{"data": [{"slug": "a_b.c~d-e"}]}', "a_b.c~d-e", ""),
        (b"<html>bot-check</html>", None, "nie jest JSON-em"),
        (b'{"data": [{"slug": "\xff\xfe"}]}', None, "UnicodeDecodeError"),
        (b'{"items": [{"slug": "x"}]}', None, "`data`"),
        (b'[{"slug": "x"}]', None, "`data`"),
        (b'{"data": "napis"}', None, "`data`"),
        (b'{"data": []}', None, "`data`"),
        (b'{"data": [{"id": 1}]}', None, "`slug`"),
        (b'{"data": [{"slug": ""}]}', None, "`slug`"),
        (b'{"data": [{"slug": 123}]}', None, "`slug`"),
        (b'{"data": [{"slug": "ma spacje"}]}', None, "spoza"),
        (b'{"data": ["napis"]}', None, "`slug`"),
    ],
    ids=[
        "ok",
        "ok-caly-alfabet",
        "nie-json",
        "nie-utf8",
        "inny-klucz",
        "korzen-lista",
        "pole-data-nie-jest-lista",
        "pusta",
        "bez-sluga",
        "pusty-slug",
        "slug-nie-napis",
        "spacja",
        "nie-rekord",
    ],
)
def test_slug_pierwszego_rekordu(
    material: bytes, oczekiwany_slug: str | None, fragment_powodu: str
) -> None:
    """Czysta funkcja na granicy: każda droga odmowy niesie powód, droga zgody — pusty napis.

    Cztery przypadki dopisane 2026-09-18 domykają gałęzie, których żaden materiał nie dotykał:
    `UnicodeDecodeError` (drugi wyjątek wymieniony w `except`, a bajty spoza UTF-8 są tym, co
    cudzy serwis przysyła najczęściej wraz z pomyloną deklaracją kodowania), korzeń będący
    listą i pole `data` niebędące listą (obie schodzą do tego samego zdania, ale innymi
    warunkami) oraz `slug` niebędący napisem — bo `123` nie jest brakiem pola, a JSON pozwala
    wstawić tam cokolwiek.
    """
    slug, powod = sonda.slug_pierwszego_rekordu(material)

    assert slug == oczekiwany_slug
    assert fragment_powodu in powod
    assert (slug is None) == bool(powod), "powód i slug wykluczają się nawzajem"


def test_powod_odmowy_nie_niesie_zakwestionowanego_sluga() -> None:
    """Powód niesie długość, nie treść — i to obowiązuje **każdą** drogę odmowy, nie tylko tę
    po `WZOR_SLUGA`.

    Napis, którego postać właśnie zakwestionowano, jest obcym napisem na drodze do terminala
    i do `podsumowanie_*.json`; wypisany w całości robi z uwagi kanał wyjścia dla cudzej treści.
    """
    _, powod = sonda.slug_pierwszego_rekordu(b'{"data": [{"slug": "\\u202egniwo/../etc"}]}')

    assert "gniwo" not in powod, "zakwestionowany slug wyszedł do uwagi w całości"
    assert "długość" in powod


# --- bramka wyjścia widziana od strony sondy -----------------------------------------------

ZBIORY_KANALOW = {UZP_HOSTS, ATLAS_HOSTS, SAOS_HOSTS}

SCENARIUSZ_SAMYCH_ODMOW: dict[str, Odpowiedz | BaseException] = {
    SCIEZKA_UZP_KONTROLA: Odpowiedz(status=403, tresc=b"forbidden"),
    SCIEZKA_UZP_WYNIKI: Odpowiedz(status=403, tresc=b"forbidden"),
    SCIEZKA_UZP_TRESC: Odpowiedz(status=403, tresc=b"forbidden"),
    SCIEZKA_ATLAS: Odpowiedz(status=403, tresc=b"forbidden"),
    SCIEZKA_ATLAS_DOKUMENT: Odpowiedz(status=403, tresc=b"forbidden"),
    SCIEZKA_ATLAS_DOKUMENTACJA: Odpowiedz(status=403, tresc=b"forbidden"),
    SCIEZKA_SAOS: Odpowiedz(status=403, tresc=b"forbidden"),
    SCIEZKA_KORZEN: Odpowiedz(status=403, tresc=b"forbidden"),
}


@pytest.mark.parametrize("klucz", sorted(sonda.POMIARY))
def test_kazdy_pomiar_zawezia_bramke_wyjscia_do_jednego_kanalu(
    klucz: str, podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Od 2026-09-17 `allowed` nie ma wartości domyślnej — ale sam brak domyślnej mówi tylko,
    że **jakiś** zbiór został podany. Że jest to zbiór jednego kanału, a nie suma trzech,
    widać wyłącznie tutaj.

    Parametryzacja chodzi po `sonda.POMIARY`, a nie po ręcznej liście, więc pomiar dopisany
    jutro z sumą hostów zapali ten test sam. Zbiór hostów jest jedyną barierą między
    nagłówkiem `X-Api-Key` Atlasu a `orzeczenia.uzp.gov.pl` — także przy przekierowaniu.
    """
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(SCENARIUSZ_SAMYCH_ODMOW)
    podstaw(serwis)

    sonda.POMIARY[klucz][1](UA_TESTOWY)

    assert serwis.bramki, f"{klucz}: nie zbudował klienta — nic nie przeszło przez bramkę"
    for bramka in serwis.bramki:
        assert bramka in ZBIORY_KANALOW, (
            f"{klucz}: bramka wyjścia otwarta na {sorted(bramka)} zamiast na hosty jednego "
            "kanału. Suma zbiorów przepuszcza żądanie z nagłówkiem jednego serwisu do drugiego."
        )


# --- wejście programu ----------------------------------------------------------------------


def test_lista_pomiarow_nie_wysyla_zadnego_zadania(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--lista` jest jedynym wywołaniem sondy, które wolno uruchomić bez zgody właściciela.
    Gdyby cokolwiek wysyłało, ta gwarancja byłaby napisem w `--help`."""

    def zakaz(**kwargs: object) -> httpx.Client:
        raise AssertionError("`--lista` zbudowała klienta HTTP")

    monkeypatch.setattr(zadanie, "build_http_client", zakaz)

    assert sonda.main(["--lista"]) == 0

    wypisane = capsys.readouterr().out
    for klucz in sonda.POMIARY:
        assert klucz in wypisane
    assert not zadanie.DZIENNIK.exists()


def test_przebieg_zostawia_wiersz_w_dzienniku_i_wlasne_podsumowanie(
    podstaw: Callable[[Serwis], ZegarTestowy],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spięcie całości: reguła zgody mówi, że pojedynczy odczyt diagnostyczny nie wymaga
    zgody, **ale zawsze zostawia wpis w dzienniku**. Dopisanie wiersza to ostatni krok
    `main`, więc pominięcie go nie psuje żadnego pomiaru i nie wypisuje niczego."""
    monkeypatch.setenv("KIO_TOOL_CONTACT", "test@example.org")
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    assert sonda.main(["atlas"]) == 0

    wiersze = wiersze_dziennika()

    assert len(wiersze) == len(serwis.zadania) == 2
    assert len(list((zadanie.KATALOG_WYJSCIA).glob("podsumowanie_atlas_*.json"))) == 1
    assert "sha256" in capsys.readouterr().out


def test_przebieg_bez_adresu_kontaktowego_nie_wysyla_niczego(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reguła 16: klient nie startuje bez `KIO_TOOL_CONTACT`, bo adres jest po to, żeby
    operator serwisu miał jak napisać. Odmowa ma być komunikatem i kodem 3 (błąd
    konfiguracji), a nie śladem stosu — `KioError` deklaruje oba te zdania w docstringu."""
    monkeypatch.delenv("KIO_TOOL_CONTACT", raising=False)

    def zakaz(**kwargs: object) -> httpx.Client:
        raise AssertionError("sonda zbudowała klienta bez adresu kontaktowego")

    monkeypatch.setattr(zadanie, "build_http_client", zakaz)

    assert sonda.main(["atlas"]) == 3

    zebrane = capsys.readouterr()

    assert "KIO_TOOL_CONTACT" in zebrane.err
    assert "Traceback" not in zebrane.err
    assert not zadanie.DZIENNIK.exists(), "nieudany start zostawił wiersz w dzienniku żądań"


# --- main: rachunek żądań i kod wyjścia ----------------------------------------------------


@pytest.fixture
def przebieg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Warunki uruchomienia `main`: adres kontaktowy jest, klucza Atlasu nie ma."""
    monkeypatch.setenv("KIO_TOOL_CONTACT", "test@example.org")
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)


def test_przebieg_liczy_zadania_wyslane_a_nie_wiersze_na_ekranie(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """N z `decisions.md` jest wypisane, a nie zostawione do policzenia z ekranu.

    Przy zatrzymanej grupie na ekranie stoją trzy wiersze, a żądanie poszło **jedno**.
    Liczenie ręką dałoby trzy — czyli liczba pilnowana przez zasadę 7.1 byłaby fałszywa
    w dokumencie, który tę zasadę wprowadza. Zdanie do przepisania niesie tę samą liczbę,
    bo dwie liczby w jednym wydruku rozjeżdżają się przy pierwszej zmianie.
    """
    serwis = uzp_scenariusz(Odpowiedz(status=403, tresc=b"forbidden"))
    podstaw(serwis)

    sonda.main(["uzp-getresults"])

    wypisane = capsys.readouterr().out

    assert "Żądań wysłanych: 1" in wypisane
    assert "zmierzone 2023-11-14, 1 żądań" in wypisane
    assert "uzp_4b_getresults" in wypisane and "uzp_16_resultcounts" in wypisane


def test_liczba_wierszy_dziennika_bez_przedrostka_zgadza_sie_z_wypisanym_n(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Trzy miejsca liczą to samo N i ten test jest jedynym, który je ze sobą zestawia.

    Ekran mówi „Żądań wysłanych: N”, dziennik ma N wierszy bez przedrostka `nie:`, a atrapa
    serwisu widziała N żądań. Rozjazd któregokolwiek z nich znaczy, że zapis w `decisions.md`
    będzie mówił o innej liczbie żądań niż ta, którą dostał cudzy serwis.
    """
    serwis = Serwis(
        {
            SCIEZKA_SAOS: [Odpowiedz(tresc=SAOS_DUMP_OK), Odpowiedz(status=403, tresc=b"nie")],
            SCIEZKA_KORZEN: Odpowiedz(),
        }
    )
    podstaw(serwis)

    sonda.main(["saos-dump"])

    wypisane = capsys.readouterr().out
    wiersze = wiersze_dziennika()
    wyslane = [w for w in wiersze if "| nie:" not in w]

    assert f"Żądań wysłanych: {len(serwis.zadania)}" in wypisane
    assert len(wyslane) == len(serwis.zadania) == 3
    assert len(wiersze) == 4, "wiersz po pomiarze, który nie poszedł, zniknął z dziennika"


def test_przebieg_zatrzymany_konczy_sie_kodem_jeden(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy]
) -> None:
    """Kod wyjścia niesie różnicę między „zmierzono wszystko” a „stanęło w połowie”.

    Bez niego harmonogram albo powłoka nie odróżnią przebiegu, po którym jest komplet danych,
    od przebiegu, po którym trzeba wrócić — a jedyną informacją byłby wydruk, którego nikt
    nie czyta maszynowo.
    """
    serwis = uzp_scenariusz(Odpowiedz(status=403, tresc=b"forbidden"))
    podstaw(serwis)

    assert sonda.main(["uzp-getresults"]) == 1


def test_zmierzona_odmowa_nie_jest_awaria_i_konczy_sie_zerem(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """403 na każde zaplanowane żądanie jest **wynikiem pomiaru**, nie awarią narzędzia.

    To jest ta sama myśl co przy `KODY_ODMOWY` bez 5xx: „kanał odmawia” jest odpowiedzią na
    pytanie fazy 0 i ma trafić do `decisions.md`, a nie zostać zgłoszone jako błąd przebiegu.
    Pomiar 23 nie ocenia kształtu i nie zatrzymuje się po odmowie, więc wszystkie trzy
    zaplanowane żądania poszły — i to odróżnia go od Atlasu, gdzie odmowa listy zostawia
    dokument niewysłany (test niżej).
    """
    serwis = Serwis(
        {
            SCIEZKA_KORZEN: Odpowiedz(status=403, tresc=b"forbidden"),
            SCIEZKA_ATLAS_DOKUMENTACJA: Odpowiedz(status=403, tresc=b"forbidden"),
        }
    )
    podstaw(serwis)

    assert sonda.main(["licencje"]) == 0
    assert "Żądań wysłanych: 3" in capsys.readouterr().out


def test_odmowa_listy_atlasu_zostawia_dokument_niewyslany_i_konczy_sie_jedynka(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Od 2026-09-18 pomiar 3a planuje dwa żądania; odmowa na pierwszym zatrzymuje grupę tak
    samo jak przy UZP — kontrola hosta idzie, dokument nie, a kod wyjścia mówi „stanęło"."""
    serwis = Serwis(
        {
            SCIEZKA_ATLAS: Odpowiedz(status=403, tresc=b"forbidden"),
            SCIEZKA_KORZEN: Odpowiedz(status=403, tresc=b"forbidden"),
        }
    )
    podstaw(serwis)

    assert sonda.main(["atlas"]) == 1

    wypisane = capsys.readouterr().out
    assert "Żądań wysłanych: 2" in wypisane
    assert "atlas_3a_dokument" in wypisane


def test_przebieg_bez_zatrzymania_konczy_sie_zerem(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy]
) -> None:
    serwis = Serwis(scenariusz_atlas_ok())
    podstaw(serwis)

    assert sonda.main(["atlas"]) == 0


def test_przebieg_wywrocony_w_polowie_i_tak_podaje_rachunek_zadan(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Zatrzymanie w pół jest momentem, w którym liczba wysłanych żądań jest najtrudniejsza do
    policzenia ręką — i jednocześnie momentem, w którym `decisions.md` wymaga jej co do sztuki.

    Do przeglądu 2026-09-17 `zapisz_podsumowanie` i wiersz „Żądań wysłanych" stały **za** blokiem
    `try`, więc `KioError` w środku przebiegu zostawiał operatora z jednym zdaniem „Sonda
    zatrzymana" i dziennikiem do ręcznego przeliczenia. Materiał był — `Kronika` zapisała każdy
    wynik w chwili powstania — brakowało rachunku.
    """
    zatrzymanie = sonda.KioError("limiter stanął")
    serwis = Serwis(
        {
            SCIEZKA_UZP_KONTROLA: Odpowiedz(tresc=UZP_DETAILS_OK),
            SCIEZKA_UZP_WYNIKI: zatrzymanie,
        }
    )
    podstaw(serwis)

    assert sonda.main(["uzp-getresults"]) == zatrzymanie.exit_code

    zapisane = capsys.readouterr()

    assert "Żądań wysłanych przed zatrzymaniem: 1" in zapisane.err, (
        "przebieg urwany nie podał N, choć znany-dobry odczyt poszedł do cudzego serwisu"
    )
    assert list(zadanie.KATALOG_WYJSCIA.glob("podsumowanie_uzp-getresults_*.json")), (
        "przebieg urwany nie zostawił podsumowania, choć miał co w nim zapisać"
    )


# --- maskowanie na całej drodze przebiegu --------------------------------------------------


def test_klucz_odbity_przez_serwis_nie_dochodzi_do_podsumowania_na_dysku(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pełna droga poprawki z `OcenaKsztaltu.__post_init__`, zmierzona na dysku.

    Ryzyko jest konkretne: pośrednik dostaje `X-Api-Key`, odpowiada stroną błędu, która ten
    nagłówek odbija, a sonda bierze z niej podgląd do `ksztalt_uwaga`. Stamtąd napis idzie na
    ekran i do `podsumowanie_*.json` — a udokumentowaną ścieżką operatora jest „przepisz wynik
    do `docs/decisions.md`", czyli do pliku w historii repozytorium.

    Test celuje w **plik**, a nie w obiekt oceny, bo to plik zostaje po sesji.
    """
    monkeypatch.setenv(sonda.ATLAS_KEY_ENV, KLUCZ_TESTOWY)
    odbicie = f"<html><body>401 invalid api key: {KLUCZ_TESTOWY}</body></html>".encode()
    serwis = Serwis({SCIEZKA_ATLAS: Odpowiedz(tresc=odbicie), SCIEZKA_KORZEN: Odpowiedz()})
    podstaw(serwis)

    sonda.main(["atlas"])

    podsumowanie = next(zadanie.KATALOG_WYJSCIA.glob("podsumowanie_atlas_*.json"))
    zapis = podsumowanie.read_text(encoding="utf-8")

    assert KLUCZ_TESTOWY not in zapis, "klucz wyszedł na dysk w uwadze o kształcie"
    assert "<token>" in zapis
    assert KLUCZ_TESTOWY not in zadanie.DZIENNIK.read_text(encoding="utf-8")


def test_surowa_odpowiedz_zostaje_surowa_mimo_maskowania_uwag(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Druga strona tej samej granicy: maskowanie obowiązuje **uwagi**, a nie dowód.

    Plik w `scripts/out/` jest zalążkiem złotego pliku z reguły 17 i ma nieść bajty takie,
    jakie przyszły — inaczej nie da się na nim oprzeć parsera ani porównania. `scripts/out/`
    jest poza historią repozytorium właśnie dlatego, że trzyma surowiznę. Gdyby maskowanie
    zaczęło sięgać zapisu, dowód przestałby być dowodem, a nikt by tego nie zauważył.
    """
    monkeypatch.setenv(sonda.ATLAS_KEY_ENV, KLUCZ_TESTOWY)
    odbicie = f"<html><body>401 invalid api key: {KLUCZ_TESTOWY}</body></html>".encode()
    serwis = Serwis({SCIEZKA_ATLAS: Odpowiedz(tresc=odbicie), SCIEZKA_KORZEN: Odpowiedz()})
    podstaw(serwis)

    wyniki = sonda.pomiar_atlas(UA_TESTOWY)
    zapisany = wyniki[0].plik

    assert zapisany is not None
    assert zapisany.read_bytes() == odbicie
    assert wyniki[0].sha256 == hashlib.sha256(odbicie).hexdigest()


# ------------------------------------------------------------------------------- znaleziska


@pytest.mark.parametrize(
    ("slug", "sciezka_ktora_dostanie_serwis"),
    [("..", "/api"), (".", SCIEZKA_ATLAS)],
    ids=["dwie-kropki", "kropka"],
)
def test_slug_nie_ma_prawa_zmienic_punktu_koncowego_drugiego_zadania(
    slug: str,
    sciezka_ktora_dostanie_serwis: str,
    podstaw: Callable[[Serwis], ZegarTestowy],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Znalezisko 2026-09-18, zgłoszone jako `xfail(strict=True)` i **poprawione tego samego
    dnia** (`SEGMENTY_KROPKOWE` w `sonda.py`: slug `.` albo `..` zostaje niewysłany z powodem);
    znacznik zdjęty razem z poprawką. Alfabet `WZOR_SLUGA` był za szeroki o segment „wyżej".

    `WZOR_SLUGA` niesie znaki „unreserved" z RFC 3986, a kropka jest wśród nich — więc slug `..`
    przechodzi kontrolę w całości. Dalej dzieje się to, przed czym ta kontrola stoi: adres
    `https://atlasprzetargow.pl/api/kio/..` jest normalizowany przez `httpx` przy budowie
    żądania i do cudzego serwisu idzie `GET /api`, a slug `.` daje `GET /api/kio`, czyli
    **powtórzenie listy** policzone jako odczyt dokumentu.

    Zmierzone 2026-09-18 na prawdziwym `build_http_client` z atrapą transportu: ścieżki widziane
    po drugiej stronie to kolejno `/api`, `/api/kio`, `/api/kio/wymyslony`.

    Cena jest podwójna i obie połowy są wprost przeciwne deklaracjom tego projektu:

    - **dziennik mówi co innego niż poszło.** `wykonaj` zapisuje `adres` w postaci, w jakiej go
      dostało, więc w `docs/dziennik_zadan.md` — pliku w historii repozytorium — stanie wiersz
      `…/api/kio/..`, a serwis odnotuje `/api`. Nagłówek dziennika mówi wprost: „dziennik ma
      mówić, co naprawdę poszło";
    - **pomiar 3a mierzy nie to, o co pyta.** Odpowiedź z `/api` albo z `/api/kio` jest listą,
      a `ATLAS_DOKUMENT` wymaga `slug` i `primary_signature` — czyli ocena wróci niezgodnością
      i zostanie zapisana jako „pośrednik nie zwraca pełnego tekstu", choć pytania o pełny tekst
      nikt nie zadał. To jest fałszywy wynik w pomiarze, na którym stoi wybór pierwszego kanału.

    Droga nie wymaga złośliwości po drugiej stronie: pole `slug` z wartością `.` albo `..`
    wystarczy, żeby cudzy serwis — przez pomyłkę w eksporcie albo przez rekord-zaślepkę —
    przekierował nasze żądanie na własny punkt listy.

    Test celuje w zachowanie, nie w postać poprawki: żądanie ma pójść pod adres złożony z tego
    sluga albo nie pójść wcale. Progiem może być odrzucenie sluga złożonego z samych kropek,
    porównanie ścieżki żądania po normalizacji z zaplanowaną albo `params`/`quote` zamiast
    sklejania napisu — to jest decyzja właściciela pomiaru.
    """
    monkeypatch.delenv(sonda.ATLAS_KEY_ENV, raising=False)
    serwis = Serwis(
        {
            SCIEZKA_ATLAS: [
                Odpowiedz(tresc=b'{"data": [{"slug": "' + slug.encode() + b'"}]}'),
                Odpowiedz(tresc=ATLAS_LISTA_OK),
            ],
            "/api": Odpowiedz(tresc=ATLAS_LISTA_OK),
        }
    )
    podstaw(serwis)

    sonda.pomiar_atlas(UA_TESTOWY)

    assert sciezka_ktora_dostanie_serwis not in [s for _, s in serwis.slad[1:]], (
        f"slug `{slug}` przeniósł drugie żądanie na `{sciezka_ktora_dostanie_serwis}` — "
        f"dziennik zapisze `{SCIEZKA_ATLAS}/{slug}`, a serwis odnotuje co innego"
    )


def test_pomiar_19_ma_wlasna_komende_w_spisie_pomiarow() -> None:
    """ADR-0004 sekcja 3 obiecuje, że pomiary 7 i 19 „startują razem z pierwszym przebiegiem
    sondy". Bez pozycji w `POMIARY` obietnica nie ma czym się wykonać, a `main` nie zna
    komendy — zegar doby ruszyłby dopiero wtedy, gdy ktoś sobie o nim przypomni."""
    assert "uzp-stabilnosc" in sonda.POMIARY
    opis, funkcja = sonda.POMIARY["uzp-stabilnosc"]

    assert funkcja is pomiar_uzp.pomiar_stabilnosc
    assert "19" in opis
    assert "doby" in opis, "opis nie mówi, że pomiar kosztuje kalendarz, a nie pracę"


def test_przebieg_pomiaru_19_konczy_sie_zerem_i_jednym_zadaniem(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Spięcie z `main`: rachunek żądań i zdanie do przepisania obejmują też pomiar 19."""
    podstaw(serwis_19(Odpowiedz(tresc=TRESC_19)))

    assert sonda.main(["uzp-stabilnosc"]) == 0

    wypisane = capsys.readouterr().out

    assert "Żądań wysłanych: 1" in wypisane
    assert "Pomiar 19" in wypisane
    assert len(list(zadanie.KATALOG_WYJSCIA.glob("podsumowanie_uzp-stabilnosc_*.json"))) == 1


def test_ctrl_c_w_srodku_przebiegu_zostawia_rachunek_zadan(
    przebieg: None, podstaw: Callable[[Serwis], ZegarTestowy], capsys: pytest.CaptureFixture[str]
) -> None:
    """Przegląd kodu 2026-09-18: `main` łapał wyłącznie `KioError`, więc `Ctrl+C` w czasie plastra
    300 s po 429 zostawiał operatora bez rachunku, choć `kronika.zapisane` go niosła. Od tego
    dnia `KeyboardInterrupt` idzie tą samą ścieżką co `KioError`, z kodem 130 powłoki."""
    serwis = Serwis(
        {
            SCIEZKA_ATLAS: Odpowiedz(tresc=ATLAS_LISTA_OK),
            SCIEZKA_ATLAS_DOKUMENT: KeyboardInterrupt(),
        }
    )
    podstaw(serwis)

    # `KeyboardInterrupt`, który wyjdzie z `main`, przerwałby całą sesję pytest zamiast zapalić
    # ten test — zmierzone mutacją 2026-09-18 (`except KioError` bez `KeyboardInterrupt` dawało
    # „45 passed" i `!!! KeyboardInterrupt !!!`, czyli wynik do przeoczenia). Stąd jawna porażka.
    try:
        kod = sonda.main(["atlas"])
    except KeyboardInterrupt:
        pytest.fail("`main` przepuściło KeyboardInterrupt bez rachunku żądań i podsumowania")

    assert kod == 130

    zebrane = capsys.readouterr()
    assert "Żądań wysłanych przed zatrzymaniem: 1" in zebrane.err
    assert "Ctrl+C" in zebrane.err
    assert len(list(zadanie.KATALOG_WYJSCIA.glob("podsumowanie_atlas_*.json"))) == 1, (
        "podsumowanie przebiegu urwanego nie powstało"
    )
