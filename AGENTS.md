# AGENTS.md

Wspólne instrukcje dla agentów AI pracujących w tym repozytorium (Codex, Claude Code i inne). To jedyne źródło instrukcji: `CLAUDE.md` tylko importuje ten plik, więc zmiany wprowadzaj tutaj.

## Projekt

Skrypty Python 3.12+ (lokalnie 3.13): `analyze.py` (analyzer, jeden duży plik) oraz `src/scraping/` (scraper soccer-rating.com). Zależności (runtime i grupa `dev`) są zadeklarowane w `pyproject.toml` i zablokowane w `uv.lock`; środowisko to `.venv` tworzone przez `uv sync --locked`. Zależności zmieniaj przez `uv add`/`uv lock`, nie ręczną edycją `uv.lock`. `exclude-newer = "7 days"` w `[tool.uv]` celowo pomija wydania młodsze niż tydzień; nie usuwaj go bez powodu. Projekt nie jest instalowalnym pakietem (`package = false`, `src/` bez `__init__.py`, działa jako namespace package).

Znane długi techniczne są w `docs/tech-debt.md`. Nowy dług dopisuj tam, a spłacony usuwaj.

## Komendy

- Komendy poniżej zakładają aktywne `.venv` (albo prefiks `uv run`); globalny Python nie ma zablokowanych wersji.
- Scraper uruchamiaj jako moduł z katalogu głównego: `python -m src.scraping.soccer_rating_cli` (nie `python src/scraping/soccer_rating_cli.py`, bo importy się nie rozwiążą).
- Typowy codzienny przebieg (tryb SR-only) opisuje skill `daily-sr`:
  - `python -m src.scraping.soccer_rating_cli --all-leagues --skip-cups --separate-snapshots --min-start 20 --max-start 700`
  - `python analyze.py --excel-pl --sr-only --input-file data/soccer-rating/match_odds_development_<YYYY-MM-DD>.csv --output-dir recommendations`
- Scraper wysyła prawdziwe zapytania HTTP do soccer-rating.com; do szybkich prób używaj `--limit N` albo `--local`.
- Bramka jakości (ta sama co w CI, `.github/workflows/ci.yml`): `pytest`, `ruff check .`, `ruff format --check .`, `mypy` (ścieżki są w `pyproject.toml`, uruchamiaj bez argumentów), `python .agents/sync-skills.py --check`. Wszystkie są obecnie czyste; nowe błędy blokują merge.
- CI uruchamia dodatkowo kontrole bezpieczeństwa (raz, w nodze macierzy 3.13): `pip-audit` na zależnościach runtime z `uv.lock`, `zizmor --persona pedantic .` i `actionlint`. Po zmianie workflowów uruchom lokalnie `uv run zizmor --offline --persona pedantic .`. Akcje są przypięte do SHA z komentarzem wersji, a pobierane narzędzia do sumy kontrolnej; nazwy jobów (`check (3.12)`, `check (3.13)`, `conventional-commit`) są wymaganymi checkami w ochronie `main`, więc ich zmiana wymaga zmiany ustawień repozytorium.
- CI uruchamia `pytest --cov` z progiem `fail_under` w `pyproject.toml` (zapadka skalibrowana na CI, nie na laptopie; podnoś ją po dodaniu testów, nie obniżaj). Lokalnie: `uv run pytest --cov`.
- Testy pokrywają tylko czyste funkcje. Zmiany w logice rekomendacji dodatkowo weryfikuj, uruchamiając starą i nową wersję `analyze.py` na lokalnych danych i porównując CSV (wyniki są deterministyczne). Tryb standardowy nadpisuje `cl_/el_recommendations.csv` w katalogu głównym, więc najpierw zrób ich kopię.

## Dane i pliki wynikowe

- Wszystkie `*.csv`, `*.xlsx`, `*.txt` i `*.html` są gitignored, a w `data/` śledzone są tylko pliki `*_example.csv`. Na świeżym klonie analyzer nie ma danych wejściowych; nie commituj danych ani raportów.
- Dane The Analyst (`data/theanalyst/...`) są kopiowane ręcznie; scraper ich nie pobiera.
- CSV wejściowe mogą mieć `;` lub `,` i przecinek dziesiętny; czytaj je przez `read_smart_csv`, nie przez gołe `pd.read_csv`.
- Nazwy drużyn różnią się między źródłami: mapowanie w `NAME_FIX` w `analyze.py`; scraper ma osobną normalizację (`norm_team` w `parsers.py`).
- Parsery scrapera opierają się na markupie soccer-rating.com (np. komórka kursu `1.57<br/>∅&nbsp;68`). Przy zmianach parsera sprawdź go na świeżo pobranej stronie, nie tylko na testach z ręcznie napisanym HTML.

## Konwencje i pułapki

- Python: type hints, PEP 8 (egzekwowane przez ruff; zestaw reguł w `[tool.ruff.lint]`, m.in. bandit `S`, `BLE`, `PTH`), łapanie konkretnych wyjątków zamiast `except Exception`, `pathlib` zamiast `open()`; każde `noqa` z uzasadnieniem w komentarzu, bez sekretów i ścieżek bezwzględnych w kodzie, bez martwego kodu.
- Commity: Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `build:`, `ci:`, `chore:`), temat w trybie rozkazującym, po angielsku.
- PR-y merguje się wyłącznie squashem: tytuł PR-a staje się commitem na `main` (bez opisu), a gałąź jest usuwana automatycznie. Format tytułu sprawdza `.github/workflows/pr-title.yml`. Ochrona `main` obejmuje też administratora, więc zmiany trafiają tam tylko przez PR z zielonym CI.
- `analyze.py` pisze na konsolę przez `print()` (to wyjście CLI, w tym raport `[AUDIT]` opisany w README); scraper używa `logging`. Trzymaj się konwencji danego pliku.
- Formaty wyjścia: domyślnie `,` i kropka dziesiętna; `--excel-pl` daje `;` i przecinek. Nie zmieniaj domyślnego formatu, README deklaruje go jako międzynarodowy.
- `.gitattributes` wymusza LF; ruff formatuje z `line-ending = "lf"`.
- Etykiety rekomendacji zawierają emoji (`🟢 STRONG BUY` itd.) i służą jako klucze sortowania; to świadomy wyjątek od zakazu emoji, opisany w `docs/tech-debt.md`.
- Logika modelu (statusy, Mot, RotRisk, progi rekomendacji) jest opisana w `readme.md` i `interpretation.md`; zmiana progów lub wag w kodzie wymaga aktualizacji tych dokumentów.

## Publikacja

Cel: lokalnie (CLI uruchamiane ręcznie, bez strony WWW i domeny). Opcjonalnie w fazie ligowej pucharów: scraper soccer-rating.com jako rzadki timer systemd na współdzielonym serwerze `vps-waw`, wyniki w `/var/lib`. Propozycja i decyzje: `docs/publikacja.md` (niewdrożone).

## Wspólna konfiguracja agentów

Codex i Claude Code korzystają z tych samych skilli i hooków; edytuj tylko źródła:

| Co | Źródło (edytuj) | Codex | Claude Code |
| --- | --- | --- | --- |
| Instrukcje | `AGENTS.md` | czyta natywnie | `CLAUDE.md` importuje `@AGENTS.md` |
| Skille | `.agents/skills/<nazwa>/SKILL.md` | czyta natywnie | kopia w `.claude/skills/` (generowana) |
| Hook po edycji | `.agents/hooks/post-edit.py` | `.codex/hooks.json` | `.claude/settings.json` |

- `.claude/skills/` jest generowane przez `python .agents/sync-skills.py`; nie edytuj go ręcznie. Hook po edycji uruchamia synchronizację automatycznie, gdy zmienisz plik w `.agents/skills/`, a CI odrzuca rozjechane kopie. Symlinki odpadają, bo na Windows bez Trybu dewelopera git zapisuje je jako zwykłe pliki.
- `.agents/hooks/post-edit.py` formatuje ruffem edytowane pliki `.py` i synchronizuje skille. Obsługuje payload obu narzędzi (`tool_input.file_path` z Claude Code, `apply_patch` z Codexa). Nowe zachowanie po edycji dopisuj do tego skryptu, nie do plików konfiguracyjnych narzędzi.
- Frontmatter `SKILL.md` może zawierać klucze jednego narzędzia (np. `disable-model-invocation` dla Claude Code); drugie je ignoruje. Ustawienia specyficzne dla Codexa są w `agents/openai.yaml` obok `SKILL.md`.
- Subagenty nie mają wspólnego formatu (Codex: `.codex/agents/*.toml`, Claude Code: `.claude/agents/*.md`). Jeśli będą potrzebne, opisz rolę raz w `.agents/`, a w obu formatach zostaw tylko krótkie odwołanie do tego opisu.
