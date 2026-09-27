# Technical Debt

Known shortcomings accepted for now. Each entry states the impact and a suggested direction. Ordered by expected impact.

## Code structure

- **`analyze.py` is a ~1,270-line monolith.** Configuration, CSV loading, the status/motivation model, recommendation rules and the CLI live in one file, which makes isolated testing and review harder. Direction: split into `src/analyzer/` modules (`config`, `data`, `model`, `recommendations`, `cli`) and keep `analyze.py` as a thin entry point.
- **Model thresholds are scattered literals.** Values such as `0.985` (LOCKED), `0.015` (OUT), `1.39` (high rotation risk), `0.04` (good SR edge) and the recommendation cut-offs are inline in functions. Direction: one configuration object with documented units, referenced by `readme.md` and `interpretation.md`.
- **`print()` instead of `logging` in `analyze.py`,** and `read_smart_csv` calls `sys.exit(1)` on a missing file, so the function cannot be reused as a library call. Direction: raise a dedicated error and let the CLI layer decide how to exit.
- **`parse_today_prediction` mutates the module-level `LEAGUES` dict** when running with `--all-leagues`, so state leaks between calls in one process. Direction: return league names alongside matches instead of mutating a global.
- **`src/` is a namespace package without a build backend.** The project cannot be installed with `pip install .`; imports rely on running from the repository root. Direction: add `__init__.py` files and a build backend once the analyzer is split into modules.

## Testing

- **Coverage is limited to pure helpers.** `format_recommendations`, `analyze_league`, `analyze_sr_only` and the scraper's `main()` flow have no automated tests; the analyzer refactor in this branch was verified manually by comparing outputs byte for byte. Direction: golden-file tests over the `_example.csv` inputs and a synthetic SR snapshot, plus coverage reporting in CI.
- **Parser tests use hand-written HTML.** The fixtures mirror the markup observed on soccer-rating.com on 2026-09-27, but a site change will only surface at runtime. Direction: store a trimmed, anonymised page snapshot as a fixture and add a periodic manual check.

## Scraper behaviour

- **Kickoff times are assumed to be in the machine's local timezone.** The time window filter (`--min-start`, `--max-start`) is wrong if the site renders another timezone. Kickoffs more than 12 hours in the past are treated as next-day fixtures.
- **National team fixtures are skipped.** Their links use a separate `/n<id>/` ID namespace, so they are logged and dropped rather than scraped.
- **Politeness and terms of use are not enforced in code.** The fetcher sends a browser-like User-Agent, does not read `robots.txt` and relies on a fixed per-request delay. Direction: identify the client honestly, respect `robots.txt`, and confirm the site's terms before any scheduled use.

## Data and output

- **Recommendation labels contain emoji** (for example `🟢 STRONG BUY`). They are part of the CSV output and are used as sort keys, so changing them is a breaking change for anyone consuming the reports. Direction: plain labels plus a separate display column.
- **Dependencies are unpinned** in `requirements.txt`, so a new pandas or BeautifulSoup release can change behaviour silently. Direction: a lock file or pinned upper bounds, refreshed deliberately.
- **The Analyst data is copied manually,** and the model is not calibrated against real outcomes. See "Future Work" in `readme.md`.
