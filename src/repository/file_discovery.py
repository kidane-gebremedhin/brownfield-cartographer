"""File discovery for repository ingestion.

- Filters supported file types
- Computes stable SHA-256 content hashes
- Logs and skips unreadable files
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {'.py', '.sql', '.yaml', '.yml', '.json', '.md', '.ipynb'}
SKIP_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.tox', 'dist', 'build'}


@dataclass(frozen=True)
class DiscoveredFile:
    path: str  # repo-relative
    extension: str
    content: bytes
    content_hash: str


def discover_files(repo_root: Path | str) -> list[DiscoveredFile]:
    root = Path(repo_root).resolve()
    if not root.exists():
        raise FileNotFoundError(str(root))
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    out: list[DiscoveredFile] = []
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        ext = p.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        try:
            data = p.read_bytes()
        except OSError as e:
            logger.warning('Skipping unreadable file %s: %s', rel, e)
            continue
        h = hashlib.sha256(data).hexdigest()
        out.append(DiscoveredFile(path=str(rel), extension=ext, content=data, content_hash=h))

    return out
