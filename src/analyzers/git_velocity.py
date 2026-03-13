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
    repo_root: Path | str,
    *,
    days: int = 90,
    top_n: int = 10,
    extensions: set[str] | None = None,
) -> list[tuple[str, int]]:
    """Return top N changed source files from raw git log, sorted by count descending.

    Matches: git log --since=N days ago --pretty=format: --name-only | grep <exts> | sort | uniq -c | sort -rg
    Uses SOURCE_EXTENSIONS when extensions is None; use e.g. {".py", ".sql"} for code-only (Day-One).
    """
    root = Path(repo_root).resolve()
    if not _is_git_repo(root):
        return []
    exts = extensions if extensions is not None else SOURCE_EXTENSIONS
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
            if any(p.endswith(ext) for ext in exts):
                counts[p] += 1
        # Descending by count, then ascending by path for ties (matches sort -rg)
        pairs = list(counts.items())
        pairs.sort(key=lambda x: (-x[1], x[0]))
        return pairs[:top_n]
    except Exception as e:
        logger.debug("top_changed_files_all failed: %s", e)
        return []


def build_git_velocity_map(
    repo_root: Path | str,
    *,
    days: int = 90,
    top_n_files: int = 10,
    top_n_dirs: int = 5,
    top_n_prefixes: int = 5,
) -> dict[str, list[tuple[str, int]]]:
    """Build a small git velocity map for Day-One answers.

    Returns a dict with:
    - files: [(path, count)]
    - directories: [(dir_prefix, aggregated_count)]
    - prefixes: [(subsystem_prefix, aggregated_count)]

    Safe for non-git repos (returns empty lists).
    """
    root = Path(repo_root).resolve()
    if not _is_git_repo(root):
        return {"files": [], "directories": [], "prefixes": []}

    # Code-only extensions so "Top changed files" matches git log | grep -E '\.(py|sql)$' (real hotspots)
    files = top_changed_files_all(
        root, days=days, top_n=top_n_files, extensions={".py", ".sql"}
    )

    from collections import Counter

    dir_counts: Counter[str] = Counter()
    prefix_counts: Counter[str] = Counter()

    for path, count in files:
        parts = path.split("/")
        if len(parts) > 1:
            dir_prefix = parts[0]
            dir_counts[dir_prefix] += count
        # heuristic subsystems based on path prefixes
        for prefix in ("dg_projects", "dg_deployments", "packages", "src", "bin"):
            if path.startswith(prefix + "/"):
                prefix_counts[prefix] += count

    top_dirs = dir_counts.most_common(top_n_dirs)
    top_prefixes = prefix_counts.most_common(top_n_prefixes)

    return {
        "files": files,
        "directories": top_dirs,
        "prefixes": top_prefixes,
    }

