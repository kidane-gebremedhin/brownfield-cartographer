"""Notebook parser.

Extracts code cells from .ipynb using nbformat so analyzers can process Python.
"""

from __future__ import annotations

import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class NotebookParseResult(BaseModel):
    code_cells: list[str] = Field(default_factory=list)
    parse_ok: bool = True
    error: str | None = None


def extract_code_cells(ipynb_bytes: bytes) -> NotebookParseResult:
    try:
        import nbformat
    except Exception as e:
        return NotebookParseResult(parse_ok=False, error=f"nbformat unavailable: {e}")

    try:
        nb = nbformat.reads(ipynb_bytes.decode('utf-8', errors='replace'), as_version=4)
        cells = []
        for c in nb.get('cells', []):
            if c.get('cell_type') == 'code':
                cells.append(c.get('source', '') or '')
        return NotebookParseResult(code_cells=cells)
    except Exception as e:
        logger.warning('Notebook parse failed: %s', e)
        return NotebookParseResult(parse_ok=False, error=str(e))
