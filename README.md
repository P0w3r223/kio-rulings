# kio-tool

Lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej — z pełnym tekstem,
wyszukiwaniem i eksportem z atrybucją.

**Status na 2026-09-15: faza 0 — sonda źródła. Kanał akwizycji nie jest wybrany i nie ma
czym pobierać.**

## Po co to powstaje

Orzecznictwo KIO jest publiczne, ale nie ma do niego żadnego udokumentowanego interfejsu
programistycznego. Urząd udostępnia wyszukiwarkę WWW, serwer FTP z archiwum przestał
publikować 30 września 2025 i dziś nie odpowiada, a jedyne API oferuje pośrednik prywatny.
Kto chce policzyć cokolwiek na całości — a nie przeczytać pojedyncze orzeczenie — nie ma dziś
czym.

Audyt tego przedsięwzięcia mówi wprost, że dla potrzeby „wyszukać i przeczytać" budowa nie ma
uzasadnienia: Atlas Przetargów robi to za darmo, a SzuKIO i wydawnictwa prawnicze odpłatnie
(krążąca cena roczna SzuKIO pozostaje w audycie **niepotwierdzona** — serwis odmówił odczytu).
Sens jest węższy i tylko taki: **programowy dostęp do korpusu pod własny potok przetwarzania.**

## Co jest w drzewie, a czego nie ma

Jest warstwa infrastruktury i producent tożsamości dokumentu: bramka wyjścia HTTP,
neutralizacja tekstu ze źródła, limiter żądań, zegar, protokół postępu, taksonomia wyjątków
i normalizator sygnatur. Do tego jednorazowa sonda fazy 0 w `scripts/` i 302 testy.

Nie ma adapterów kanałów (`kio_tool/source/`), parsera (`kio_tool/parser/`) ani interfejsu
(`kio_tool/ui/`) — i to jest stan zamierzony, nie niedokończony. Kanał wybiera się **po**
pomiarach fazy 0, bo przed nimi nie wiadomo, co adapter miałby implementować.

## Co już zmierzono

Wyniki z datami i liczbą żądań stoją w `docs/decisions.md`. Trzy pomiary własne:

- **FTP UZP nie odpowiada.** Port 21 milczy, przy kontroli na cudzym serwerze FTP działającym
  z tej samej maszyny w tej samej minucie. Droga „pobierz osiemnaście lat archiwum hurtem"
  jest zamknięta, a cały odcinek 2007–2018 zależy teraz od serwisu SAOS, którego dostępu nikt
  w tym projekcie jeszcze nie potwierdził.
- **Dla wyszukiwarki UZP nie ma warunków ponownego wykorzystywania ani informacji o ich
  braku.** Licencja CC BY-SA 4.0 ze stopki gov.pl jest zakreślona domeną `www.gov.pl` i tej
  domeny nie obejmuje. Otwiera to drogę wniosku z art. 39 ust. 1 pkt 2 ustawy o otwartych
  danych — projekt pisma leży w `docs/pisma/`.
- **Blokada sieci w testach działa na poziomie gniazda**, nie tylko transportu `httpx`, więc
  obejmuje także kanał spoza HTTP.

## Dwie reguły, które obowiązują od pierwszego commita

**Narzędzie nie omija zabezpieczeń.** Żadnego rozwiązywania CAPTCHA, żadnego podszywania się
pod przeglądarkę, żadnego obchodzenia ograniczeń tempa. Przy odmowie serwisu narzędzie
zatrzymuje się i mówi o tym operatorowi. Granica jest prawna, nie estetyczna.

**Żadnej liczby bez źródła i daty.** Każde twierdzenie w `docs/` niesie datę i sposób
uzyskania. Sygnatury, nazwy własne i treść przepisów pochodzą z odczytu z datą, nigdy
z pamięci modelu — sygnatura wygląda tak samo niezależnie od tego, czy istnieje.

## Uruchomienie

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Wymaga Pythona 3.12. Testy działają przy **zablokowanej sieci** — `--block-network` stoi
w konfiguracji pytest i jest to egzekwowane, nie deklarowane. Jedyny wyjątek to marker
`smoke`, uruchamiany ręcznie po zgodzie właściciela.

Żądanie do prawdziwego źródła wymaga adresu kontaktowego. Narzędzie przedstawia się nim przy
każdym żądaniu, żeby operator serwisu miał jak napisać, gdy coś pójdzie nie tak:

```
set KIO_TOOL_CONTACT=imie.nazwisko@example.org
.venv\Scripts\python.exe scripts\sonda.py --lista
```

Bez tej zmiennej klient HTTP się nie zbuduje. To jest odmowa zamierzona, nie usterka.

## Dokumentacja

| Plik | Co niesie |
|---|---|
| `docs/AUDYT_KIO_ORZECZENIA.md` | stan źródła, dopuszczalność w sześciu reżimach, rachunek build-vs-buy, doktryna, reguły granic, pomiary fazy 0 |
| `docs/ARCHITEKTURA_KIO_TOOL.md` | przegląd istniejących narzędzi, architektura, model danych, plan faz |
| `docs/decisions.md` | wyniki pomiarów z datami |
| `docs/adr/` | decyzje architektoniczne wraz z odrzuconymi wariantami |
| `docs/pisma/` | projekty pism do wysłania: wniosek do UZP, zapytanie do pośrednika, pytania do prawnika |
| `CLAUDE.md` | konfiguracja projektu dla sesji z Claude Code |

Kolejność czytania, jeśli masz przeczytać tylko część: `docs/decisions.md`, potem sekcja 14
audytu (status dowodowy — mówi, na których zdaniach wolno budować), potem sekcja 8
architektury (decyzje czekające na właściciela).

## Licencja

MIT dla kodu. Korpus nie wchodzi do repozytorium — niesie pełne nazwiska składu orzekającego
i protokolantów, a operator narzędzia jest dla tych danych administratorem.
