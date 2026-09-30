"""PostToolUse hook shared by Claude Code and Codex.

- runs `ruff format` on edited Python files;
- re-syncs .claude/skills when a file under .agents/skills changed (see .agents/sync-skills.py).

Reads the hook payload from stdin. Claude Code passes `tool_input.file_path` (Write/Edit);
Codex passes an `apply_patch` body in `tool_input.command`. The hook never blocks the edit.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PATCH_FILE_HEADER = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
PATCH_MOVE_HEADER = re.compile(r"^\*\*\* Move to: (.+)$", re.MULTILINE)
RUFF_TIMEOUT_SECONDS = 20
SYNC_TIMEOUT_SECONDS = 20
REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
SYNC_SCRIPT = REPO_ROOT / ".agents" / "sync-skills.py"


def collect_paths(payload: dict) -> list[str]:
    """Returns every file path mentioned by a Claude Code or Codex edit payload."""
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    if not isinstance(tool_response, dict):
        tool_response = {}
    candidates = [
        tool_input.get("file_path"),
        tool_input.get("path"),
        tool_response.get("filePath"),
    ]
    command = tool_input.get("command")
    if isinstance(command, str):
        candidates += PATCH_FILE_HEADER.findall(command) + PATCH_MOVE_HEADER.findall(command)
    return [c.strip() for c in candidates if isinstance(c, str) and c.strip()]


def python_files(paths: list[Path]) -> list[Path]:
    """Keeps existing .py files."""
    return [p for p in paths if p.suffix == ".py" and p.is_file()]


def touches_shared_skills(paths: list[Path]) -> bool:
    """True when any path lies under .agents/skills."""
    return any(p.is_relative_to(SHARED_SKILLS_DIR) for p in paths)


def run_quietly(command: list[str], cwd: Path, timeout_seconds: int) -> None:
    """Runs a helper command; failures are ignored so the hook never blocks an edit."""
    try:
        # Commands are built in this file from fixed executables and resolved paths, never from a shell string.
        subprocess.run(command, cwd=cwd, timeout=timeout_seconds, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired):
        return


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    cwd = Path(payload.get("cwd") or Path.cwd())
    paths = sorted({(cwd / p).resolve() for p in collect_paths(payload)})

    ruff = shutil.which("ruff")
    files = python_files(paths)
    if ruff and files:
        run_quietly([ruff, "format", "--quiet", *map(str, files)], cwd, RUFF_TIMEOUT_SECONDS)
    if touches_shared_skills(paths):
        run_quietly([sys.executable, str(SYNC_SCRIPT)], REPO_ROOT, SYNC_TIMEOUT_SECONDS)


if __name__ == "__main__":
    main()
