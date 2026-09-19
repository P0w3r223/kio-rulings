"""Raport pokrycia i złoty zbiór (ADR-0006 Z-11, Z-12) — artefakt bramki fazy 2.

Trzy rzeczy są tu mierzone, bo to one czynią raport dowodem, a nie ekranem: procent nigdy nie
stoi bez licznika i mianownika, dokument bez struktury jest liczony jako brak (nie pomijany),
a adnotacja złotego zbioru bez odpowiednika w korpusie jest „niesprawdzona" — głośno.
Złote pliki w repozytorium są sprawdzane pod kątem tego, czego **nie wolno** im nieść: tekstu.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from kio_tool.pokrycie import (
    AdnotacjaZlota,
    SekcjaZlota,
    markdown,
    maszynowy,
    rocznik_z_sygnatury,
    sprawdz_zloty,
    wczytaj_zloty,
    zbuduj,
)
from kio_tool.store import StrukturaDokumentu, WierszCytowania, WierszPrzepisu, WierszSekcji

KATALOG_ZLOTY = Path(__file__).resolve().parent / "gold"
KLUCZE_ZLOTEGO = {"doc_id", "content_sha256", "sekcje", "przeglad"}
KLUCZE_SEKCJI = {"rodzaj", "start", "koniec", "sha256"}


def _dok(
    doc_id: str,
    *,
    sygnatura: str | None = "KIO 1/24",
    data: str | None = "2024-01-05",
    rodzaje: tuple[str, ...] = ("naglowek", "sentencja", "pouczenie", "uzasadnienie"),
    parse_version: int | None = 2,
) -> StrukturaDokumentu:
    sekcje = tuple(WierszSekcji(i, r, i * 10, i * 10 + 10, f"s{i}") for i, r in enumerate(rodzaje))
    return StrukturaDokumentu(
        doc_id=doc_id,
        content_sha256="c" + doc_id,
        sygnatura_glowna=sygnatura,
        data_wydania=data,
        parse_version=parse_version,
        sekcje=sekcje,
        cytowania=(
            WierszCytowania(0, "tresc", "kio", "KIO 2/23", "KIO 2/23", 1, 9),
            WierszCytowania(1, "tresc", "inne", None, "sygn. akt 5/23", 10, 20),
        ),
        przepisy=(
            WierszPrzepisu(0, "tresc", "art. 226", "pzp2019", "art. 226", 1, 9),
            WierszPrzepisu(0, "kanal", "art. 226", "pzp2019", "art. 226 Pzp", None, None),
            WierszPrzepisu(1, "kanal", "art. 99", "nieustalone", "art. 99 Pzp", None, None),
        ),
    )


def test_rocznik_pochodzi_z_sygnatury_nie_z_daty() -> None:
    assert rocznik_z_sygnatury("KIO 1205/20") == "2020"
    assert rocznik_z_sygnatury("KIO/UZP 1482/08") == "2008"
    assert rocznik_z_sygnatury(None) == rocznik_z_sygnatury("bez sygnatury") == "brak"


def test_raport_liczy_komplet_czesciowy_i_brak_zamiast_pomijac() -> None:
    raport = zbuduj(
        [
            _dok("a"),
            _dok("b", rodzaje=("naglowek", "sentencja")),
            _dok("c", rodzaje=("nieprzypisane",), parse_version=None, data=None),
        ],
        data="2026-09-19",
        parse_version=2,
    )
    r = raport.roczniki["2024"]
    assert (r.dokumentow, r.komplet, r.czesciowo, r.bez_sekcji) == (3, 1, 1, 1)
    assert (raport.bez_metadanych, raport.bez_daty) == (1, 1)
    assert r.nieprzypisanych == 10


def test_przepisy_kanalu_porownane_z_trescia() -> None:
    raport = zbuduj([_dok("a")], data="2026-09-19", parse_version=2)
    assert (raport.kanal_w_tresci, raport.kanal_razem) == (1, 2)
    assert raport.akty["kanal"]["nieustalone"] == 1


def test_zaden_procent_bez_licznika_i_mianownika() -> None:
    """Doktryna 7.1 w postaci mechanicznej — każdy `%` w raporcie ma przed sobą „N z M"."""
    tekst = markdown(zbuduj([_dok("a"), _dok("b")], data="2026-09-19", parse_version=2))
    procenty = re.findall(r"[^|\n]*%[^|\n]*", tekst)
    assert procenty, "raport bez żadnego procentu nie sprawdza tej reguły"
    for fragment in procenty:
        assert re.search(r"\d+ z \d+ \(\d+,\d %\)", fragment), fragment


def test_raport_maszynowy_to_poprawny_json() -> None:
    dane = json.loads(maszynowy(zbuduj([_dok("a")], data="2026-09-19", parse_version=2)))
    assert dane["dokumentow"] == 1 and dane["roczniki"]["2024"]["komplet"] == 1


# --- złoty zbiór --------------------------------------------------------------------------------


def _adnotacja(d: StrukturaDokumentu) -> AdnotacjaZlota:
    return AdnotacjaZlota(
        doc_id=d.doc_id,
        content_sha256=d.content_sha256,
        sekcje=tuple(SekcjaZlota(s.rodzaj, s.start, s.koniec, s.sha256) for s in d.sekcje),
        przejrzal="test",
        data_przegladu="2026-09-19",
    )


def test_zloty_zgodny_niezgodny_i_niesprawdzony() -> None:
    a, b = _dok("a"), _dok("b")
    przesuniete = _adnotacja(b)
    przesuniete = AdnotacjaZlota(
        przesuniete.doc_id,
        przesuniete.content_sha256,
        (SekcjaZlota("naglowek", 0, 11, "s0"), *przesuniete.sekcje[1:]),
        "test",
        "2026-09-19",
    )
    brak = AdnotacjaZlota("zniknal", "x", (), "test", "2026-09-19")
    wynik = sprawdz_zloty([_adnotacja(a), przesuniete, brak], {"a": a, "b": b})
    assert (wynik.plikow, wynik.sprawdzonych, wynik.zgodnych) == (3, 2, 1)
    assert any("zniknal" in r and "niesprawdzony" in r for r in wynik.rozbieznosci)


def test_inna_wersja_dokumentu_to_niesprawdzony_nie_zgodny() -> None:
    a = _dok("a")
    stara = _adnotacja(a)
    stara = AdnotacjaZlota(stara.doc_id, "inny-skrot", stara.sekcje, "test", "2026-09-19")
    wynik = sprawdz_zloty([stara], {"a": a})
    assert (wynik.sprawdzonych, wynik.zgodnych) == (0, 0)


def test_zly_plik_zlotego_zbioru_jest_bledem_glosnym(tmp_path: Path) -> None:
    (tmp_path / "zly.json").write_text('{"doc_id": "a"}', encoding="utf-8")
    with pytest.raises(ValueError, match="zly.json"):
        wczytaj_zloty(tmp_path)


def test_zlote_pliki_w_repozytorium_nie_niosa_tekstu() -> None:
    """Z-11: orzeczenia niosą nazwiska składu (pomiar 10: 404 z 443 z nazwiskiem
    przewodniczącego) — adnotacja ma wyłącznie offsety i skróty, żadnego pola tekstowego."""
    pliki = sorted(KATALOG_ZLOTY.glob("*.json"))
    assert len(pliki) >= 17, "złoty zbiór: po jednym dokumencie z roczników 2010–2026"
    for plik in pliki:
        dane = json.loads(plik.read_text(encoding="utf-8"))
        assert set(dane) == KLUCZE_ZLOTEGO, plik.name
        assert set(dane["przeglad"]) == {"kto", "data"}, plik.name
        for sekcja in dane["sekcje"]:
            assert set(sekcja) == KLUCZE_SEKCJI, plik.name
            assert re.fullmatch(r"[0-9a-f]{64}", sekcja["sha256"]), plik.name
    assert len(wczytaj_zloty(KATALOG_ZLOTY)) == len(pliki)
