# kio-tool

A local, versioned corpus of rulings of Poland's National Appeals Chamber (Krajowa Izba
Odwoławcza, KIO), which hears public-procurement appeals. The command-line tool downloads rulings
with full text from the public Atlas Przetargów API (CC BY 4.0), stores each one in SQLite exactly as
it arrived, splits it into sections, citations and legal provisions, searches it offline, and exports
`xlsx`, `csv`, `jsonl` and `md`, always with source attribution.

**Status (2026-09-23):** phases 0 to 3 accepted: interactive wizard, demo mode, machine-readable
output for a model (`--json`, `docs/dla-modelu.md`). The operator's corpus holds 1 499 rulings from
2010 to 2026, every year present, and 1 492 of them have all four section types recognised
(`docs/anatomia-bazy.md`).

The rulings and the command vocabulary are Polish. Commands and flags below are written as they are
typed, with an English gloss.

## Why this is more than a scraper

- The source is a third-party mirror, not the official register, and its HTML changes across 16 years
  of rulings, so parsing, dates and identity matching are checked per document. An issue date the
  source got wrong or left empty is kept as delivered.
- The API has a request budget. Above 50 requests a run stops until it is confirmed with `--zgoda`;
  the confirmation is bound to the cost shown before the run and cannot be stored in configuration.
- A run interrupted by Ctrl+C, the network, a killed process or a full disk resumes from a checkpoint
  without duplicate records.
- Rulings name judges and court clerks, so the database and exports stay outside the repository.

## Quick start

```
.venv\Scripts\kio-tool.exe            # wizard: menu, hints, cost table before downloading
.venv\Scripts\kio-tool.exe demo       # the same on a fictional corpus, no network or configuration
```

Everything demo mode produces is marked: a separate database, a `DEMO_` prefix, and records without a
citation block.

## Details

<details>
<summary><strong>Install and configuration</strong></summary>

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Python 3.12. The tests run with the network blocked; none sends a request.

Downloading needs a contact address for the `User-Agent` header, and the tool sends nothing without
it. An Atlas API key is optional and raises the limit from 1 500 to 5 000 requests a day:

```
set KIO_TOOL_CONTACT=your@address
set KIO_TOOL_ATLAS_KEY=key          # optional
```

</details>

<details>
<summary><strong>Usage: commands, filters, exit codes</strong></summary>

With `.venv` active (`.venv\Scripts\activate`), otherwise `.venv\Scripts\kio-tool.exe`:

```
kio-tool pobierz --od 2024-02-01 --do 2024-02-29 --wycena --json
kio-tool pobierz --od 2024-02-01 --do 2024-02-29 --zgoda
kio-tool wznow
kio-tool szukaj --fraza "rażąco niska cena" --od 2023-01-01 --json
kio-tool czytaj "KIO 3810/23" --sekcja sentencja --json
kio-tool eksportuj --od 2024-01-01 --do 2024-01-31 --format xlsx,md
kio-tool runy
kio-tool przelicz
kio-tool pokrycie --zloty tests/gold
```

| Command | What it does | Network |
|---|---|---|
| `pobierz` (download) | list from Atlas plus one full-text record per new document; export at the end | yes |
| `wznow` (resume) | finishes an interrupted run without duplicates | yes |
| `szukaj` (search) | literal phrase in the full text, with filters; always prints corpus size and hit count | no |
| `czytaj` (read) | one ruling by case number or `doc_id`: metadata, citation, section map, full text or chosen sections | no |
| `eksportuj` (export) | the documents of a run (`--run-id`) or those matching the criteria | no |
| `runy` (runs) | run history | no |
| `opis` (describe) | commands, flags, allowed values and exit codes, read from the command tree, for a program | no |
| `przelicz` (re-parse) | parses the stored bytes again without downloading | no |
| `pokrycie` (coverage) | parsing quality report; `--zloty` checks the gold set | no |

Filters shared by `pobierz`, `szukaj` and `eksportuj`: `--od` (from), `--do` (to), `--fraza` (phrase),
`--rozstrzygniecie` (outcome), `--rodzaj` (type), `--przepis` (provision), `--przewodniczacy`
(presiding member), `--strona` (party). In `pobierz`, `--fraza` goes to the Atlas search, which
matches the case number and not the text; `szukaj` searches the text locally. Every command except
the wizard and the demo accepts `--json`; `pobierz --wycena` prints the cost only (one list page, zero
documents).

Exit codes: 0 done, 1 error, 2 run to resume (or a command syntax error), 3 configuration, missing
confirmation or a bad parameter, 130 Ctrl+C.

The tool sets its own pace: at least 1 s between requests, at most 450 a minute and 1 400 a day; 429,
5xx and dropped connections are retried under the channel contract. It does not work around
protections: on a CAPTCHA or a block it stops and says so.

</details>

<details>
<summary><strong>Output files</strong></summary>

The database and exports live outside the repository, in `%LOCALAPPDATA%\kio-tool\kio-tool\`
(`korpus.sqlite`, `wyniki/`).

| Format | Contents |
|---|---|
| `xlsx` | sheets `Orzeczenia` (21 columns), `Slownik`, `Metadane`; no full text |
| `csv` | the same columns, `;`, UTF-8 with BOM |
| `jsonl` | identity, citation block and the raw channel record with full text |
| `md` | one file per ruling: metadata, citation block, text with section headings, cited rulings and provisions; `INDEX.md` |

Every row carries the ruling's address in the UZP search, the SHA-256 of the stored version and the
attribution "Źródło: Atlas Przetargów (https://atlasprzetargow.pl)".

</details>

<details>
<summary><strong>What it does not do</strong></summary>

- It does not go back before 2010 and does not know whether the corpus is complete against the
  official register.
- It has one channel (`atlas`) and does not detect changes at the source after download.
- It does not assess cases legally and has no language model inside; a model drives it from outside.
- It does not guard against two processes working on one database.

</details>

<details>
<summary><strong>Development</strong></summary>

```
set PYTHONUTF8=1
.venv\Scripts\python.exe -m pytest        # 1 441 tests (2026-09-26), network blocked
.venv\Scripts\ruff.exe check .
.venv\Scripts\ruff.exe format --check .
.venv\Scripts\mypy.exe kio_tool scripts   # strict
```

Module boundaries are enforced by `tests/test_boundaries.py`; for example, only
`pipeline/pobieranie.py` connects the network to the database. A fix to a safeguard is checked by
mutation: break the code and watch the test fail.

</details>

<details>
<summary><strong>Documentation (in Polish)</strong></summary>

| File | Contents |
|---|---|
| `docs/dla-modelu.md` | instructions for the model that drives the tool |
| `docs/decisions.md` | dated measurements, runs, owner decisions |
| `docs/adr/` | architecture decisions 0001 to 0009 |
| `docs/AUDYT_KIO_ORZECZENIA.md`, `docs/ARCHITEKTURA_KIO_TOOL.md` | source, admissibility, boundary rules, architecture |
| `CLAUDE.md` | working rules for Claude Code |

</details>

## License

MIT for the code, see [LICENSE](LICENSE). Data from Atlas Przetargów is CC BY 4.0, and every export
carries the attribution.
