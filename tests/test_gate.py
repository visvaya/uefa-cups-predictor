import itertools

import pytest

from scripts.gate import STEPS, StepResult, run_steps, summary


def test_steps_have_unique_names_and_cover_the_ci_checks() -> None:
    names = [name for name, _ in STEPS]
    assert len(names) == len(set(names))
    commands = [" ".join(args) for _, args in STEPS]
    for check in (
        "ruff check",
        "ruff format --check",
        "mypy",
        "importlinter",
        "vulture",
        "pylint",
        "pytest --cov",
        "tracked",
    ):
        assert any(check in command for command in commands), check


def test_run_steps_continues_after_a_failure_and_times_each_step(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[list[str]] = []
    exit_codes = iter([0, 2, 0])

    def fake_run(args: list[str]) -> int:
        calls.append(args)
        return next(exit_codes)

    ticks = itertools.count(step=1.5)
    steps = [("a", ("-m", "a")), ("b", ("-m", "b")), ("c", ("c.py",))]

    results = run_steps(steps, fake_run, lambda: next(ticks))

    assert calls == [["-m", "a"], ["-m", "b"], ["c.py"]]
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
