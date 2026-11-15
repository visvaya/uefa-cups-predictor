"""Git hook checks, also run in CI over all tracked files.

Usage:
  python scripts/git_hooks.py pre-commit            # staged paths and their content, ruff on staged Python files
  python scripts/git_hooks.py commit-msg <file>     # commit message
  python scripts/git_hooks.py tracked               # every tracked path and its content (CI)
Enable the hooks once per checkout: git config core.hooksPath .githooks
Per checkout, kept out of the repository:
  git config hooks.excludedPaths "<file name> <directory>/ ..."  paths that must never be committed
  git config hooks.ownerIdentities "<email> ..."                 author and committer e-mails pre-commit accepts
CI reads the excluded paths from the EXCLUDED_PATHS environment variable instead.
"""

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ATTRIBUTION_LINES = (
    re.compile(r"^\W*co-authored-by:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\W*generated[ -](?:with|by)[\s:]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\W*[\w-]+-session:", re.IGNORECASE | re.MULTILINE),
)
EM_DASH = chr(0x2014)
SCISSORS = "------------------------ >8 ------------------------"
CONVENTIONAL_SUBJECT = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9._/-]+\))?!?: [^ ](.*[^.])?$"
)
MAX_SUBJECT_CHARS = 72
GIT_GENERATED_SUBJECTS = ("Merge ", 'Revert "', "fixup! ", "squash! ", "amend! ")
EMOJI = re.compile(
    "[" + chr(0x1F000) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + chr(0x2B00) + "-" + chr(0x2BFF) + "]"
)
# Recommendation labels in the report output carry these circles and serve as sort keys (accepted exception).
LABEL_EMOJI = frozenset({chr(0x26AA), chr(0x1F534), chr(0x1F7E0), chr(0x1F7E1), chr(0x1F7E2)})
LABEL_FILES = frozenset({"analyze.py", "readme.md", "interpretation.md"})
IDENT_TIMESTAMP = re.compile(r"\s+\d+\s+[+-]\d{4}$")


def excluded_paths(paths: list[str], patterns: list[str]) -> list[str]:
    """Paths matching a pattern: `name` matches a file name anywhere, `name/` a directory anywhere."""
    names = {pattern for pattern in patterns if not pattern.endswith("/")}
    directories = {pattern.rstrip("/") for pattern in patterns if pattern.endswith("/")}
    return [path for path in paths if path.split("/")[-1] in names or directories.intersection(path.split("/")[:-1])]


def subject_problems(text: str) -> list[str]:
    """Checks the first line that is neither blank nor a comment."""
    subject = next((line for line in text.splitlines() if line.strip() and not line.startswith("#")), "")
    if subject.startswith(GIT_GENERATED_SUBJECTS):
        return []
    if CONVENTIONAL_SUBJECT.match(subject) is None:
        return ["Write the subject as a Conventional Commit, e.g. 'fix(scraper): handle empty odds cell'."]
    if len(subject) > MAX_SUBJECT_CHARS:
        return [f"Shorten the subject to at most {MAX_SUBJECT_CHARS} characters (now {len(subject)})."]
    return []


def message_problems(message: str) -> list[str]:
    """Lists what is wrong with a commit message.

    Comment lines are checked too, since `git commit -m` keeps them. Only the diff that `git commit -v`
    appends below the scissors line is ignored.
    """
    text = message.split(SCISSORS)[0]
    problems = subject_problems(text)
    if any(pattern.search(text) for pattern in ATTRIBUTION_LINES):
        problems.append("Remove co-author, generated-by and session lines from the commit message.")
    if EM_DASH in text:
        problems.append("Replace the em dash (U+2014) with an en dash (U+2013) or a middle dot (U+00B7).")
    if EMOJI.search(text):
        problems.append("Remove emoji from the commit message.")
    return problems


def text_problems(path: str, text: str) -> list[str]:
    """Em dashes and emoji in a file; the label circles are allowed only in the files that define or document them."""
    allowed = LABEL_EMOJI if path in LABEL_FILES else frozenset()
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        if EM_DASH in line:
            problems.append(f"{path}:{number}: replace the em dash (U+2014) with an en dash or a middle dot")
        if any(char not in allowed for char in EMOJI.findall(line)):
            problems.append(f"{path}:{number}: remove the emoji")
    return problems


def identity_problems(idents: dict[str, str], owner_emails: list[str]) -> list[str]:
    """Author and committer identities outside `owner_emails`; nothing to check when none are configured."""
    allowed = {email.lower() for email in owner_emails}
    return [
        f"{role} is {ident}"
        for role, ident in idents.items()
        if allowed and ident[ident.find("<") + 1 : ident.rfind(">")].lower() not in allowed
    ]


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Runs a command built in this file (resolved executable, no shell) and captures its text output."""
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)  # noqa: S603


def git(*args: str) -> str:
    """Standard output of a git command; raises when git fails."""
    result = run([shutil.which("git") or "git", *args])
    result.check_returncode()
    return result.stdout


def config_list(key: str) -> list[str]:
    """Space-separated values of a git config key, or an empty list when it is not set."""
    return git("config", "--default", "", "--get", key).split()


def path_problems(paths: list[str], patterns: list[str]) -> list[str]:
    """Formats one message per excluded path."""
    return [f"Not committed in this repository: {path}" for path in excluded_paths(paths, patterns)]


def content_problems(paths: list[str], read: Callable[[str], str]) -> list[str]:
    """Runs `text_problems` over every path whose content `read` returns as text (binary files are skipped)."""
    problems = []
    for path in paths:
        try:
            text = read(path)
        except UnicodeDecodeError:
            continue
        problems += text_problems(path, text)
    return problems


def ruff_problems(python_files: list[str]) -> list[str]:
    """Fast lint and format check of the staged Python files."""
    commands = (["check", "--quiet"], ["format", "--check", "--quiet"])
    return [
        f"ruff {command[0]} failed on the staged Python files:\n{result.stdout}{result.stderr}"
        for command in commands
        if python_files and (result := run([sys.executable, "-m", "ruff", *command, *python_files])).returncode != 0
    ]


def pre_commit_problems() -> list[str]:
    staged = [path for path in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0") if path]
    idents = {
        role: IDENT_TIMESTAMP.sub("", git("var", role).strip()) for role in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT")
    }
    return (
        identity_problems(idents, config_list("hooks.ownerIdentities"))
        + path_problems(staged, config_list("hooks.excludedPaths"))
        + content_problems(staged, lambda path: git("show", f":{path}"))
        + ruff_problems([path for path in staged if path.endswith(".py")])
    )


def tracked_problems() -> list[str]:
    tracked = [path for path in git("ls-files", "-z").split("\0") if path]
    patterns = os.environ.get("EXCLUDED_PATHS", "").split() or config_list("hooks.excludedPaths")
    return path_problems(tracked, patterns) + content_problems(
        tracked, lambda path: Path(path).read_text(encoding="utf-8")
    )


def main(argv: list[str]) -> int:
    match argv:
        case ["commit-msg", message_file]:
            problems = message_problems(Path(message_file).read_text(encoding="utf-8"))
        case ["pre-commit"]:
            problems = pre_commit_problems()
        case ["tracked"]:
            problems = tracked_problems()
        case _:
            print(__doc__)
            return 2
    if problems:
        print("\n".join(problems), file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
