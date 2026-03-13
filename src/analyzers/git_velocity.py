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

# Source-like extensions we consider for Day-One git velocity hotspots.
SOURCE_EXTENSIONS = {".py", ".sql", ".yaml", ".yml", ".json", ".md", ".ipynb", ".toml", ".lock"}


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


def top_changed_files_all(
    repo_root: Path | str, *, days: int = 90, top_n: int = 10
) -> list[tuple[str, int]]:
    """Return top N changed *source* files from raw git log.

    This matches:
      git log --since=N days ago --pretty=format: --name-only \\
        | grep -Ei '\\.(py|sql|yaml|yml|json|md|ipynb)$' \\
        | sort | uniq -c | sort -rg
    """
    root = Path(repo_root).resolve()
    if not _is_git_repo(root):
        return []
    try:
        r = run_cmd(
            ["git", "log", f"--since={days} days ago", "--pretty=format:", "--name-only"],
            cwd=root,
            timeout_s=60,
        )
        from collections import Counter

        counts: Counter[str] = Counter()
        for line in r.stdout.splitlines():
            p = line.strip()
            if not p:
                continue
            # Only count files with allowed source extensions
            if any(p.endswith(ext) for ext in SOURCE_EXTENSIONS):
                counts[p] += 1
        return counts.most_common(top_n)
    except Exception as e:
        logger.debug("top_changed_files_all failed: %s", e)
        return []

