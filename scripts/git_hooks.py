"""Git hook checks, also run in CI over all tracked files.

Usage:
  python scripts/git_hooks.py pre-commit            # staged paths
  python scripts/git_hooks.py commit-msg <file>     # commit message
  python scripts/git_hooks.py tracked               # every tracked path (CI)
Enable the hooks once per checkout: git config core.hooksPath .githooks
"""

import re
import subprocess
import sys
from pathlib import Path

# Local tool configuration and private notes stay outside this repository.
EXCLUDED_FILE_NAMES = frozenset({"PRIVATE.md", "NOTES.md", "NOTES.local.md"})
EXCLUDED_DIRECTORIES = frozenset({".local-a", ".local-b", ".local-c"})
ATTRIBUTION_LINES = (
    re.compile(r"^\W*co-authored-by:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\W*generated[ -](?:with|by)[\s:]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\W*[\w-]+-session:", re.IGNORECASE | re.MULTILINE),
)
EM_DASH = chr(0x2014)
SCISSORS = "------------------------ >8 ------------------------"


def excluded_paths(paths: list[str]) -> list[str]:
    """Returns the repository-relative paths (forward slashes) that must not be committed."""
    return [
        path
        for path in paths
        if path.split("/")[-1] in EXCLUDED_FILE_NAMES or EXCLUDED_DIRECTORIES.intersection(path.split("/")[:-1])
    ]


def message_problems(message: str) -> list[str]:
    """Lists what is wrong with a commit message.

    Comment lines are checked too, since `git commit -m` keeps them. Only the diff that `git commit -v`
    appends below the scissors line is ignored.
    """
    text = message.split(SCISSORS)[0]
    problems = []
    if any(pattern.search(text) for pattern in ATTRIBUTION_LINES):
        problems.append("Remove co-author, generated-by and session lines from the commit message.")
    if EM_DASH in text:
        problems.append("Replace the em dash (U+2014) with an en dash (U+2013) or a middle dot (U+00B7).")
    return problems


def path_problems(paths: list[str]) -> list[str]:
    """Formats one message per excluded path."""
    return [f"Not committed in this repository: {path}" for path in excluded_paths(paths)]


def git_paths(*args: str) -> list[str]:
    """Runs a git command that prints NUL-separated paths."""
    # Fixed executable and arguments from this file, no shell.
    output = subprocess.run(["git", *args, "-z"], capture_output=True, text=True, check=True).stdout  # noqa: S603, S607
    return [path for path in output.split("\0") if path]


def main(argv: list[str]) -> int:
    match argv:
        case ["commit-msg", message_file]:
            problems = message_problems(Path(message_file).read_text(encoding="utf-8"))
        case ["pre-commit"]:
            problems = path_problems(git_paths("diff", "--cached", "--name-only", "--diff-filter=ACMR"))
        case ["tracked"]:
            problems = path_problems(git_paths("ls-files"))
        case _:
            print(__doc__)
            return 2
    if problems:
        print("\n".join(problems), file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
