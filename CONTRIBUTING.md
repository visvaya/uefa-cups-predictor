# Contributing

Thanks for your interest. This is a small personal tool maintained by one person, so issues and pull requests are
read, but there is no fixed response time.

## Before you start

- For anything larger than a small fix, open an issue first to agree on the change.
- Security problems go through private reporting, not issues: see [SECURITY.md](SECURITY.md).
- Do not commit data or reports: `*.csv`, `*.xlsx`, `*.txt` and `*.html` are ignored on purpose, and only
  `*_example.csv` files under `data/` are tracked.

## Setup

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked
git config core.hooksPath .githooks   # commit message and staged-file checks
```

## Checks

Run the same checks as CI before opening a pull request, from the repository root:

```bash
uv run python -m scripts.gate
```

The gate (`scripts/gate.py`) runs ruff, mypy, import-linter (layer contracts in `pyproject.toml`), vulture, pylint
(only the duplicate-code check is enabled), pytest with the coverage threshold, the tracked-file scan and markdownlint
(through `npx`, so it needs Node.js 22 or newer; config in `.markdownlint-cli2.jsonc`), reports each step's exit code
and duration, and exits 1 if any failed. Add a new code check to its `STEPS`, not to the workflow, so
local runs and CI stay the same. CI also checks the relative links and anchors in the Markdown files with
[lychee](https://github.com/lycheeverse/lychee) in offline mode (`lychee --offline --include-fragments`).

Changes to the recommendation logic in `src/analyzer/` must keep the reports deterministic. If a change is meant to
alter the output, say so in the pull request and update `README.md` and `interpretation.md` when thresholds or
weights change.

The scraper's parser tests use hand-written HTML. After changing a parser, and as a periodic manual check, run
`uv run soccer-rating --check-markup` against the live site: it sends three polite requests, stores nothing and exits
non-zero when the parsers no longer find the expected structures. It is not part of CI, which never contacts the site.

Mutation testing of the model rules (mutmut, configured in `pyproject.toml`) runs weekly in GitHub Actions; mutmut does
not run natively on Windows, so use WSL to run it locally (`uv run mutmut run`).

## Pull requests

- One topic per pull request, branched from `main`.
- The title is a [Conventional Commit](https://www.conventionalcommits.org/) of at most 72 characters, for example
  `fix(scraper): handle empty odds cell`. Pull requests are squash-merged and the title becomes the commit on
  `main`.
- Add or update tests for changed behaviour.
- The `gate` check must pass before merging. [CodeRabbit](https://www.coderabbit.ai/) reviews a pull request when
  the maintainer asks for it (the comment `@coderabbitai review`), usually for changes to parsing, CI or larger logic
  changes; its comments are suggestions, and the maintainer decides which to apply.

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
