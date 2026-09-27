"""Mirrors the shared skills in .agents/skills (read by Codex) into .claude/skills (read by Claude Code).

.agents/skills is the single source of truth; .claude/skills is generated and must not be edited by hand.
Usage: python .agents/sync-skills.py [--check]
  --check  exit with status 1 if .claude/skills is out of sync (used in CI), without writing anything.
"""

import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / ".agents" / "skills"
TARGET_DIR = REPO_ROOT / ".claude" / "skills"


def relative_files(root: Path) -> set[Path]:
    """Returns all file paths under `root`, relative to it."""
    if not root.is_dir():
        return set()
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file()}


def find_differences() -> list[str]:
    """Lists files that are missing, stale or extra in the target compared to the source."""
    source, target = relative_files(SOURCE_DIR), relative_files(TARGET_DIR)
    missing = [f"missing: {p.as_posix()}" for p in sorted(source - target)]
    extra = [f"extra: {p.as_posix()}" for p in sorted(target - source)]
    stale = [
        f"stale: {p.as_posix()}"
        for p in sorted(source & target)
        if not filecmp.cmp(SOURCE_DIR / p, TARGET_DIR / p, shallow=False)
    ]
    return missing + stale + extra


def sync() -> None:
    """Replaces the target directory with an exact copy of the source directory."""
    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    if SOURCE_DIR.is_dir():
        shutil.copytree(SOURCE_DIR, TARGET_DIR)


def main(argv: list[str]) -> int:
    differences = find_differences()
    if "--check" in argv:
        if differences:
            print("Claude skills are out of sync with .agents/skills; run: python .agents/sync-skills.py")
            print("\n".join(differences))
            return 1
        return 0
    if differences:
        sync()
        print(f"Synced .agents/skills -> .claude/skills ({len(differences)} change(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
