"""Git velocity analyzer.

Computes change counts over 30 and 90 day windows.
Must never crash analysis; returns 0 on errors.
When the path is not a git repository (e.g. ZIP extract), returns 0 without running git.
"""

from __future__ import annotations

import logging
from pathlib import Path

from utils.safe_subprocess import run_cmd, CommandError

logger = logging.getLogger(__name__)


def _is_git_repo(root: Path) -> bool:
    """True if root has a .git directory or file (submodule)."""
    git_dir = root / ".git"
    return git_dir.exists()


def change_velocity(repo_root: Path | str, file_path: str, *, days: int) -> int:
    """Return number of commits touching file in last N days."""
    root = Path(repo_root).resolve()
    if not _is_git_repo(root):
        return 0
    fp = Path(file_path)
    rel = fp
    if fp.is_absolute():
        try:
            rel = fp.relative_to(root)
        except ValueError:
            return 0

    try:
        r = run_cmd(
            [
                'git',
                'log',
                '--oneline',
                f'--since={days} days ago',
                '--',
                str(rel),
            ],
            cwd=root,
            timeout_s=30,
        )
        return len([ln for ln in r.stdout.splitlines() if ln.strip()])
    except Exception as e:
        logger.debug('git velocity failed for %s: %s', rel, e)
        return 0


def change_velocity_30_90(repo_root: Path | str, file_path: str) -> tuple[int, int]:
    return change_velocity(repo_root, file_path, days=30), change_velocity(repo_root, file_path, days=90)


def extract_git_velocity(repo_root: Path | str, file_path: str, *, days: int = 30) -> int:
    """Return number of commits touching the file in the last N days (curriculum alias)."""
    return change_velocity(repo_root, file_path, days=days)
