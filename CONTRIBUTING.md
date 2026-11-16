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

Run the same checks as CI before opening a pull request:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run vulture                                   # dead code
uv run pylint analyze.py src scripts tests       # duplicated code (only this check is enabled)
uv run pytest --cov
uv run python scripts/git_hooks.py tracked
```

Changes to the recommendation logic in `src/analyzer/` must keep the reports deterministic. If a change is meant to
alter the output, say so in the pull request and update `readme.md` and `interpretation.md` when thresholds or
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
- CodeRabbit reviews every pull request into `main` automatically (drafts only when marked ready); its review and
  the `gate` check must pass before merging.

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
