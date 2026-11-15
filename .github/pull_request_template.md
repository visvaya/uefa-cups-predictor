## What and why

<!-- What changes and the reason for it. Link an issue if there is one. -->

## Effect on the reports

<!-- "None" or what changes in the CSV output and why. -->

## Checks run

- [ ] `uv run ruff check .` and `uv run ruff format --check .`
- [ ] `uv run mypy`
- [ ] `uv run pytest --cov`
- [ ] `uv run python scripts/git_hooks.py tracked`
