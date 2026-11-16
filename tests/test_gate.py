import itertools

import pytest

from scripts.gate import STEPS, StepResult, run_command, run_steps, summary


def test_steps_have_unique_names_and_cover_the_ci_checks() -> None:
    names = [name for name, _, _ in STEPS]
    assert len(names) == len(set(names))
    commands = [" ".join(command) for _, _, command in STEPS]
    for check in (
        "ruff check",
        "ruff format --check",
        "mypy",
        "lint-imports",
        "vulture",
        "pylint",
        "pytest --cov",
        "tracked",
    ):
        assert any(check in command for command in commands), check


def test_run_steps_continues_after_a_failure_and_times_each_step(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[tuple[str, list[str]]] = []
    exit_codes = iter([0, 2, 0])

    def fake_run(workdir: str, command: list[str]) -> int:
        calls.append((workdir, command))
        return next(exit_codes)

    ticks = itertools.count(step=1.5)
    steps = [("a", ".", ("python", "-m", "a")), ("b", "src", ("b", "--x")), ("c", ".", ("c",))]

    results = run_steps(steps, fake_run, lambda: next(ticks))

    assert calls == [(".", ["python", "-m", "a"]), ("src", ["b", "--x"]), (".", ["c"])]
    assert results == [StepResult("a", 0, 1.5), StepResult("b", 2, 1.5), StepResult("c", 0, 1.5)]
    assert "<== b: exit 2 in 1.5 s" in capsys.readouterr().out


def test_summary_lists_failed_steps() -> None:
    text = summary([StepResult("lint", 0, 1.25), StepResult("tests", 1, 30.0)])
    assert text.splitlines() == [
        "Summary:",
        "  ok   lint: exit 0 in 1.2 s",
        "  FAIL tests: exit 1 in 30.0 s",
        "Failed: tests",
    ]


def test_summary_reports_success_when_every_step_passed() -> None:
    assert summary([StepResult("lint", 0, 0.5)]).splitlines()[-1] == "All steps passed."


def test_run_command_reports_a_missing_program(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_command(".", ["no-such-gate-tool", "--version"]) == 127
    assert "no-such-gate-tool is not on PATH" in capsys.readouterr().err


def test_run_command_runs_python_in_the_step_directory(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_command("src", ["python", "-c", "import pathlib; print(pathlib.Path.cwd().name)"]) == 0
    assert capsys.readouterr().out.strip() == "src"
