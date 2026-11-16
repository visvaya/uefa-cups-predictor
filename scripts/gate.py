"""The quality gate: every code check CI's `check` job runs, in one command.

Usage (from the repository root): uv run python -m scripts.gate

Runs each step with the interpreter running this script, so the tools come from the project environment, prints
its name, exit code and duration, carries on after a failure so one run shows every problem, and exits 1 if any step
failed. The security audits (pip-audit, zizmor, actionlint) stay separate CI steps.
"""

import os
import sys
import time
from collections.abc import Callable, Sequence
from typing import NamedTuple

from scripts.git_hooks import run

# (name, arguments after `python`); the order is the order CI reports them in.
STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ruff check", ("-m", "ruff", "check", ".")),
    ("ruff format", ("-m", "ruff", "format", "--check", ".")),
    ("mypy", ("-m", "mypy")),
    # import-linter has no `python -m` entry point; --no-cache leaves no cache directory behind.
    (
        "import contracts",
        ("-c", "from importlinter.cli import lint_imports_command; lint_imports_command()", "--no-cache"),
    ),
    ("vulture", ("-m", "vulture")),
    ("pylint duplicate-code", ("-m", "pylint", "analyze.py", "src", "scripts", "tests")),
    ("pytest", ("-m", "pytest", "--cov", "--cov-report=term")),
    # CI passes the never-committed paths in EXCLUDED_PATHS; locally they come from git config.
    ("tracked files", ("scripts/git_hooks.py", "tracked")),
)


class StepResult(NamedTuple):
    name: str
    exit_code: int
    seconds: float


def run_steps(
    steps: Sequence[tuple[str, tuple[str, ...]]], run: Callable[[list[str]], int], clock: Callable[[], float]
) -> list[StepResult]:
    """Runs every step, including those after a failure, and reports each one as it finishes."""
    results = []
    for name, args in steps:
        print(f"==> {name}", flush=True)
        started = clock()
        result = StepResult(name, run(list(args)), clock() - started)
        print(f"<== {name}: exit {result.exit_code} in {result.seconds:.1f} s", flush=True)
        results.append(result)
    return results


def summary(results: Sequence[StepResult]) -> str:
    lines = [
        f"  {'ok  ' if r.exit_code == 0 else 'FAIL'} {r.name}: exit {r.exit_code} in {r.seconds:.1f} s" for r in results
    ]
    failed = [r.name for r in results if r.exit_code != 0]
    return "\n".join(["Summary:", *lines, f"Failed: {', '.join(failed)}" if failed else "All steps passed."])


def run_python(args: list[str]) -> int:
    """Runs this interpreter with arguments from STEPS and prints its captured output."""
    result = run([sys.executable, *args])
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main() -> int:
    # Every step is a Python process: UTF-8 mode makes them write UTF-8 whatever the Windows code page, which the
    # strict decoding in `run` expects.
    os.environ["PYTHONUTF8"] = "1"
    results = run_steps(STEPS, run_python, time.monotonic)
    print(f"\n{summary(results)}")
    return 1 if any(r.exit_code for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
