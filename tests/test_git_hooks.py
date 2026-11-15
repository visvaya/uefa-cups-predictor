import pytest

from scripts.git_hooks import excluded_paths, identity_problems, message_problems, text_problems

# Neutral names: the real list lives in each checkout's git config and in a CI variable, not in this repository.
PATTERNS = ["NOTES.md", ".private/"]


@pytest.mark.parametrize("path", ["NOTES.md", "src/NOTES.md", ".private/x.py", "a/.private/settings.json"])
def test_excluded_paths_rejects_configured_paths(path: str) -> None:
    assert excluded_paths([path], PATTERNS) == [path]


@pytest.mark.parametrize(
    "path", ["readme.md", "src/notes.py", "docs/NOTES.md.bak", ".private", ".github/workflows/ci.yml"]
)
def test_excluded_paths_keeps_other_files(path: str) -> None:
    assert excluded_paths([path], PATTERNS) == []


def test_excluded_paths_without_patterns_excludes_nothing() -> None:
    assert excluded_paths(["NOTES.md", ".private/x.py"], []) == []


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


GREEN_LABEL = chr(0x1F7E2) + " STRONG BUY"
ROCKET = chr(0x1F680)


@pytest.mark.parametrize(
    "subject",
    [
        "feat: add x",
        "fix(scraper): handle empty odds cell",
        "chore!: drop python 3.11",
        "Merge branch 'main' into feature",
        'Revert "feat: add x"',
        "fixup! feat: add x",
    ],
)
def test_message_problems_accepts_conventional_and_git_generated_subjects(subject: str) -> None:
    assert message_problems(subject + "\n") == []


@pytest.mark.parametrize("subject", ["add x", "feat:add x", "Feat: add x", "feat: add x.", "feat: " + "x" * 70])
def test_message_problems_rejects_other_subjects(subject: str) -> None:
    assert message_problems(subject + "\n") != []


def test_message_problems_rejects_emoji() -> None:
    assert message_problems("feat: add x " + ROCKET + "\n") != []


def test_text_problems_rejects_em_dash_and_emoji_anywhere() -> None:
    assert text_problems("src/x.py", "a " + chr(0x2014) + " b\n") != []
    assert text_problems("docs.md", "launch " + ROCKET + "\n") != []


def test_text_problems_allows_label_emoji_only_where_labels_live() -> None:
    assert text_problems("analyze.py", 'label = "' + GREEN_LABEL + '"\n') == []
    assert text_problems("readme.md", GREEN_LABEL + "\n") == []
    assert text_problems("src/x.py", GREEN_LABEL + "\n") != []
    assert text_problems("analyze.py", ROCKET + "\n") != []


def test_identity_problems_only_when_owner_identities_are_configured() -> None:
    idents = {"GIT_AUTHOR_IDENT": "A <a@example.com>", "GIT_COMMITTER_IDENT": "B <b@example.com>"}
    assert identity_problems(idents, []) == []
    assert identity_problems(idents, ["a@example.com", "b@example.com"]) == []
    assert identity_problems(idents, ["A@example.com"]) == ["GIT_COMMITTER_IDENT is B <b@example.com>"]


def test_emoji_checks_catch_keycap_sequences() -> None:
    keycap = "1" + chr(0xFE0F) + chr(0x20E3)
    assert message_problems("feat: add " + keycap + "\n") != []
    assert text_problems("docs.md", keycap + "\n") != []


def test_message_problems_checks_the_first_line_git_keeps() -> None:
    assert message_problems("# release notes\n\nfeat: add x\n") != []
