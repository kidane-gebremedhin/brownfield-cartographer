"""Language router: maps file paths to parser strategies.

Python-first today; designed to extend to SQL, YAML, JS, TS.
"""

from __future__ import annotations

from pathlib import Path

_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".ipynb": "notebook",
    ".js": "javascript",
    ".ts": "typescript",
}


def get_language(path: str | Path) -> str:
    """Return a normalized language id for a file path."""
    ext = Path(path).suffix.lower()
    return _EXT_TO_LANGUAGE.get(ext, "unknown")
