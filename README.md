# kio-tool

Lokalny, wersjonowany korpus orzecznictwa Krajowej Izby Odwoławczej — z pełnym tekstem,
wyszukiwaniem i eksportem z atrybucją.

**Status: faza 0 — sonda źródła. Nie ma jeszcze kanału akwizycji i nie ma czym pobierać.**

## Co tu jest, a czego nie ma

W drzewie stoi warstwa infrastruktury i producent tożsamości dokumentu. Nie ma adapterów
kanałów (`kio_tool/source/`), parsera (`kio_tool/parser/`) ani interfejsu (`kio_tool/ui/`) —
i to jest stan zamierzony, nie niedokończony. Kanał akwizycji wybiera się **po** pomiarach
fazy 0, bo przed nimi nie wiadomo, co adapter miałby implementować.

Kolejność czytania dla kogoś, kto zaczyna: `docs/AUDYT_KIO_ORZECZENIA.md` (sekcje 14 → 13 →
2 → 10), potem `docs/ARCHITEKTURA_KIO_TOOL.md` (0.1 → 3 → 4.4 → 6), potem `docs/adr/`
i `docs/decisions.md`.

## Dwie reguły, które obowiązują od pierwszego commita

**Narzędzie nie omija zabezpieczeń.** Żadnego rozwiązywania CAPTCHA, żadnego podszywania się
pod przeglądarkę, żadnego obchodzenia ograniczeń tempa. Przy odmowie serwisu narzędzie
zatrzymuje się i mówi o tym operatorowi. Granica jest prawna, nie estetyczna.

**Żadnej liczby bez źródła i daty.** Każde twierdzenie w `docs/` niesie datę i sposób
uzyskania. Sygnatury, nazwy własne i treść przepisów nigdy nie pochodzą z pamięci modelu —
sygnatura wygląda tak samo niezależnie od tego, czy istnieje.

## Uruchomienie

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Testy działają przy **zablokowanej sieci** (`--block-network` w konfiguracji pytest) i to jest
egzekwowane, nie deklarowane: blokada jest zamkiem na gnieździe, więc obejmuje także ruch
spoza `httpx`. Jedyny wyjątek to marker `smoke`, uruchamiany ręcznie po zgodzie właściciela.

Żądanie do prawdziwego źródła wymaga adresu kontaktowego — narzędzie przedstawia się nim przy
każdym żądaniu, żeby operator serwisu miał jak napisać, gdy coś pójdzie nie tak:

```
set KIO_TOOL_CONTACT=imie.nazwisko@example.org
```

Bez tej zmiennej klient HTTP się nie zbuduje. To jest odmowa zamierzona, nie usterka.

## Licencja

MIT dla kodu. Korpus nie wchodzi do repozytorium — niesie pełne nazwiska składu orzekającego
i protokolantów, a operator narzędzia jest dla tych danych administratorem.
