# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projekt

Skrypty Python 3.12+ (lokalnie 3.13): `analyze.py` (analyzer, jeden duży plik) oraz `src/scraping/` (scraper soccer-rating.com). Zależności runtime w `requirements.txt`, deweloperskie w `requirements-dev.txt`; `pyproject.toml` zawiera tylko konfigurację narzędzi, projekt nie jest instalowalnym pakietem (`src/` bez `__init__.py`, działa jako namespace package).

Znane długi techniczne są w `docs/tech-debt.md`. Nowy dług dopisuj tam, a spłacony usuwaj.

## Komendy

- Scraper uruchamiaj jako moduł z katalogu głównego: `python -m src.scraping.soccer_rating_cli` (nie `python src/scraping/soccer_rating_cli.py`, bo importy się nie rozwiążą).
- Typowy codzienny przebieg (tryb SR-only):
  - `python -m src.scraping.soccer_rating_cli --all-leagues --skip-cups --separate-snapshots --min-start 20 --max-start 700`
  - `python analyze.py --excel-pl --sr-only --input-file data/soccer-rating/match_odds_development_<YYYY-MM-DD>.csv --output-dir recommendations`
- Scraper wysyła prawdziwe zapytania HTTP do soccer-rating.com; do szybkich prób używaj `--limit N` albo `--local`.
- Bramka jakości (ta sama co w CI, `.github/workflows/ci.yml`): `pytest`, `ruff check .`, `ruff format --check .`, `mypy` (ścieżki mypy są w `pyproject.toml`, uruchamiaj bez argumentów). Wszystkie są obecnie czyste; nowe błędy blokują merge.
- Hook w `.claude/settings.json` formatuje ruffem każdy edytowany plik `.py`.
- Testy pokrywają tylko czyste funkcje. Zmiany w logice rekomendacji dodatkowo weryfikuj, uruchamiając starą i nową wersję `analyze.py` na lokalnych danych i porównując CSV (wyniki są deterministyczne). Uwaga: tryb standardowy nadpisuje `cl_/el_recommendations.csv` w katalogu głównym, więc najpierw zrób ich kopię.

## Dane i pliki wynikowe

- Wszystkie `*.csv`, `*.xlsx`, `*.txt` (poza `requirements.txt`) i `*.html` są gitignored, a w `data/` śledzone są tylko pliki `*_example.csv`. Na świeżym klonie analyzer nie ma danych wejściowych; nie commituj danych ani raportów.
- Dane The Analyst (`data/theanalyst/...`) są kopiowane ręcznie; scraper ich nie pobiera.
- CSV wejściowe mogą mieć `;` lub `,` i przecinek dziesiętny; czytaj je przez `read_smart_csv`, nie przez gołe `pd.read_csv`.
- Nazwy drużyn różnią się między źródłami: mapowanie w `NAME_FIX` w `analyze.py`; scraper ma osobną normalizację (`norm_team` w `parsers.py`).
- Parsery scrapera opierają się na markupie soccer-rating.com (np. komórka kursu `1.57<br/>∅&nbsp;68`). Przy zmianach parsera sprawdź go na świeżo pobranej stronie, nie tylko na testach z ręcznie napisanym HTML.

## Konwencje i pułapki

- `.agent/rules/project-rules.md` to generyczny szablon (Next.js, Supabase, Tailwind) i nie dotyczy tego repo. Obowiązują z niego tylko części o Pythonie: type hints, PEP 8, łapanie konkretnych wyjątków zamiast `except Exception`.
- Obowiązują też `.agent/rules/commit-policy.md` (Conventional Commits) i `.agent/rules/commit-rules.md` (bez sekretów, bez ścieżek bezwzględnych w kodzie, bez martwego kodu).
- `analyze.py` pisze na konsolę przez `print()` (to wyjście CLI, w tym raport `[AUDIT]` opisany w README); scraper używa `logging`. Trzymaj się konwencji danego pliku.
- Formaty wyjścia: domyślnie `,` i kropka dziesiętna; `--excel-pl` daje `;` i przecinek. Nie zmieniaj domyślnego formatu, README deklaruje go jako międzynarodowy.
- `.gitattributes` wymusza LF; ruff formatuje z `line-ending = "lf"`.
- Etykiety rekomendacji zawierają emoji (`🟢 STRONG BUY` itd.) i służą jako klucze sortowania; to świadomy wyjątek od zakazu emoji, opisany w `docs/tech-debt.md`.
- Logika modelu (statusy, Mot, RotRisk, progi rekomendacji) jest opisana w `readme.md` i `interpretation.md`; zmiana progów lub wag w kodzie wymaga aktualizacji tych dokumentów.
