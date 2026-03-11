"""Git tools for repository ingestion.

Kept minimal for ingestion layer; provides helpers used by later analyzers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from utils.safe_subprocess import run_cmd

logger = logging.getLogger(__name__)


def last_modified(repo_root: Path | str, file_path: str) -> datetime | None:
    """Return the last modification time for a file using git log."""
    root = Path(repo_root).resolve()
    fp = Path(file_path)
    rel = fp
    if fp.is_absolute():
        try:
            rel = fp.relative_to(root)
        except ValueError:
            return None

    try:
        r = run_cmd(['git', 'log', '-1', '--format=%cI', '--', str(rel)], cwd=root, timeout_s=10)
        s = r.stdout.strip()
        if not s:
            return None
        # ISO 8601
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.debug('last_modified failed for %s: %s', rel, e)
        return None


def commit_count_since(repo_root: Path | str, file_path: str, *, days: int) -> int:
    """Return number of commits touching file since N days ago."""
    root = Path(repo_root).resolve()
    fp = Path(file_path)
    rel = fp
    if fp.is_absolute():
        try:
            rel = fp.relative_to(root)
        except ValueError:
            return 0

    try:
        r = run_cmd(['git', 'log', '--oneline', f'--since={days} days ago', '--', str(rel)], cwd=root, timeout_s=30)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        return len(lines)
    except Exception as e:
        logger.debug('commit_count_since failed for %s: %s', rel, e)
        return 0
