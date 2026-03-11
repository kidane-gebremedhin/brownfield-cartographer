"""Repository loader.

Supports:
- local path input
- GitHub URL input (https://github.com/org/repo(.git) or git@github.com:org/repo(.git))

Remote clones:
- happen in temporary directories only
- never into the live working directory
- use subprocess with explicit args (no shell=True)
"""
from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.safe_subprocess import run_cmd, CommandError

logger = logging.getLogger(__name__)

_GH_HTTPS = re.compile(r'^(https?://)?(www\.)?github\.com/[\w.-]+/[\w.-]+(\.git)?$', re.IGNORECASE)
_GH_SSH = re.compile(r'^git@github\.com:[\w.-]+/[\w.-]+(\.git)?$')


@dataclass(frozen=True)
class LoadedRepository:
    root: Path
    is_temporary: bool
    _tmpdir: Any | None = None


def is_github_url(s: str) -> bool:
    s = s.strip()
    return bool(_GH_HTTPS.match(s) or _GH_SSH.match(s))


def load_repository(input_path_or_url: str, *, ref: str | None = None, temp_parent: Path | None = None) -> LoadedRepository:
    s = input_path_or_url.strip()
    if not s:
        raise ValueError('input_path_or_url cannot be empty')

    if is_github_url(s):
        return _clone_github(s, ref=ref, temp_parent=temp_parent)

    # reject other URL-like strings
    if s.startswith(('http://', 'https://', 'git@')):
        raise ValueError(f'Unsupported URL (only GitHub is supported): {s}')

    p = Path(s).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(str(p))
    if not p.is_dir():
        raise NotADirectoryError(str(p))

    logger.info('Using local repository: %s', p)
    return LoadedRepository(root=p, is_temporary=False)


def _clone_github(url: str, *, ref: str | None = None, temp_parent: Path | None = None) -> LoadedRepository:
    cwd = Path.cwd().resolve()

    # Temporary-only enforcement
    if temp_parent is not None:
        parent = Path(temp_parent).resolve()
        sys_tmp = Path(tempfile.gettempdir()).resolve()
        if sys_tmp not in parent.parents and parent != sys_tmp:
            raise ValueError(f'temp_parent must be under system temp dir ({sys_tmp}), got {parent}')
        parent.mkdir(parents=True, exist_ok=True)
        tmpdir_obj = tempfile.TemporaryDirectory(prefix='cartographer_clone_', dir=str(parent))
    else:
        tmpdir_obj = tempfile.TemporaryDirectory(prefix='cartographer_clone_')

    dest = Path(tmpdir_obj.name).resolve()

    if dest == cwd or cwd in dest.parents:
        tmpdir_obj.cleanup()
        raise ValueError('Refusing to clone into the current working directory tree')

    args = ['git', 'clone', '--depth', '1']
    if ref:
        args += ['--branch', ref]
    args += ['--', url, str(dest)]

    try:
        run_cmd(args, timeout_s=180)
    except Exception:
        tmpdir_obj.cleanup()
        raise

    logger.info('Cloned %s into %s', url, dest)
    # Keep TemporaryDirectory alive for the caller via LoadedRepository.
    return LoadedRepository(root=dest, is_temporary=True, _tmpdir=tmpdir_obj)
