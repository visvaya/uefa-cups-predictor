import pytest

from scripts.git_hooks import excluded_paths, message_problems


@pytest.mark.parametrize(
    "path",
    ["PRIVATE.md", "NOTES.md", "src/NOTES.local.md", ".local-a/x.py", ".local-b/settings.json", "a/.local-c/hooks.json"],
)
def test_excluded_paths_rejects_local_tool_files(path: str) -> None:
    assert excluded_paths([path]) == [path]


@pytest.mark.parametrize("path", ["readme.md", "src/agents.py", "docs/private-notes.md", ".github/workflows/ci.yml"])
def test_excluded_paths_keeps_project_files(path: str) -> None:
    assert excluded_paths([path]) == []


@pytest.mark.parametrize(
    "trailer",
    [
        "Co-authored-by: Someone <a@b.c>",
        "co-authored-by: x",
        "Generated with a tool",
        "Generated-by: tool",
        "Tool-Session: abc",
        "# Co-authored-by: x",
        "# Tool-Session: abc",
    ],
)
def test_message_problems_rejects_attribution_lines(trailer: str) -> None:
    assert message_problems(f"fix: handle empty odds cell\n\n{trailer}\n") != []


def test_message_problems_rejects_em_dash() -> None:
    assert message_problems("fix: odds " + chr(0x2014) + " cell") != []


def test_message_problems_rejects_em_dash_on_comment_line() -> None:
    assert message_problems("fix: odds\n\n# kept by git commit -m " + chr(0x2014) + " here\n") != []


def test_message_problems_checks_comment_lines_for_attribution() -> None:
    assert message_problems("fix: odds\n\n# Generated with a tool\n") != []


def test_message_problems_accepts_git_template_comments() -> None:
    template = (
        "fix: odds\n\n# Please enter the commit message for your changes. Lines starting\n# with '#' will be ignored.\n"
    )
    assert message_problems(template) == []


def test_message_problems_accepts_plain_message() -> None:
    assert message_problems("fix(scraper): handle empty odds cell\n\nThe cell can be blank before kickoff.\n") == []


def test_message_problems_ignores_text_below_scissors() -> None:
    message = "fix: odds\n# ------------------------ >8 ------------------------\nCo-authored-by: x\n"
    assert message_problems(message) == []
