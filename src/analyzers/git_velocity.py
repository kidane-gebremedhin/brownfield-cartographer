"""Git velocity analyzer.

Computes change counts over 30 and 90 day windows.
Must never crash analysis; returns 0 on errors.
"""

from __future__ import annotations

import logging
from pathlib import Path

from utils.safe_subprocess import run_cmd, CommandError

logger = logging.getLogger(__name__)


def change_velocity(repo_root: Path | str, file_path: str, *, days: int) -> int:
    """Return number of commits touching file in last N days."""
    root = Path(repo_root).resolve()
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
