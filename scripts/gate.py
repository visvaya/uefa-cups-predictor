"""The quality gate: every code check CI's `check` job runs, in one command.

Usage (from the repository root): uv run python -m scripts.gate

Runs each step from the repository root (or the directory the step names), prints its name, exit code and duration,
carries on after a failure so one run shows every problem, and exits 1 if any step failed. The Python tools come from
the project environment (run the gate through `uv run`). The security audits (pip-audit, zizmor, actionlint) stay
separate CI steps.
"""

import io
import os
import shutil
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from scripts.git_hooks import run

ROOT = Path(__file__).resolve().parents[1]

# (name, working directory relative to the root, command); "python" is the interpreter running this script. The order
# is the order CI reports them in.
type Step = tuple[str, str, tuple[str, ...]]
STEPS: tuple[Step, ...] = (
    ("ruff check", ".", ("python", "-m", "ruff", "check", ".")),
    ("ruff format", ".", ("python", "-m", "ruff", "format", "--check", ".")),
    ("mypy", ".", ("python", "-m", "mypy")),
    # --no-cache leaves no cache directory behind.
    ("import contracts", ".", ("lint-imports", "--no-cache")),
    ("vulture", ".", ("python", "-m", "vulture")),
    ("pylint duplicate-code", ".", ("python", "-m", "pylint", "analyze.py", "src", "scripts", "tests")),
    ("pytest", ".", ("python", "-m", "pytest", "--cov", "--cov-report=term")),
    # CI passes the never-committed paths in EXCLUDED_PATHS; locally they come from git config.
    ("tracked files", ".", ("python", "scripts/git_hooks.py", "tracked")),
)


class StepResult(NamedTuple):
    name: str
    exit_code: int
    seconds: float


def run_steps(
    steps: Sequence[Step], run: Callable[[str, list[str]], int], clock: Callable[[], float]
) -> list[StepResult]:
    """Runs every step, including those after a failure, and reports each one as it finishes."""
    results = []
    for name, workdir, command in steps:
        print(f"==> {name}", flush=True)
        started = clock()
        result = StepResult(name, run(workdir, list(command)), clock() - started)
        print(f"<== {name}: exit {result.exit_code} in {result.seconds:.1f} s", flush=True)
        results.append(result)
    return results


def summary(results: Sequence[StepResult]) -> str:
    lines = [
        f"  {'ok  ' if r.exit_code == 0 else 'FAIL'} {r.name}: exit {r.exit_code} in {r.seconds:.1f} s" for r in results
    ]
    failed = [r.name for r in results if r.exit_code != 0]
    return "\n".join(["Summary:", *lines, f"Failed: {', '.join(failed)}" if failed else "All steps passed."])


def run_command(workdir: str, command: list[str]) -> int:
    """Runs a command from STEPS in its directory and prints its captured output; 127 when the program is missing."""
    program = sys.executable if command[0] == "python" else shutil.which(command[0])
    if program is None:
        print(
            f"{command[0]} is not on PATH: run the gate through `uv run` after `uv sync --locked`; npx comes with "
            "Node.js 22 or newer",
            file=sys.stderr,
        )
        return 127
    result = run([program, *command[1:]], cwd=ROOT / workdir)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main() -> int:
    # UTF-8 mode makes the Python steps write UTF-8 whatever the Windows code page, which the strict decoding in `run`
    # expects; Node writes UTF-8 anyway.
    os.environ["PYTHONUTF8"] = "1"
    # This process's own streams may still use a narrower code page (output redirected on Windows): replace what
    # they cannot encode instead of stopping the gate.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")
    results = run_steps(STEPS, run_command, time.monotonic)
    print(f"\n{summary(results)}")
    return 1 if any(r.exit_code for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
