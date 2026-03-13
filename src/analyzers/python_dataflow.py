"""Python dataflow extraction (read/write patterns) for lineage.

Supports (best-effort, conservative):
- pandas.read_csv / read_parquet / read_sql
- SQLAlchemy engine.execute / connection.execute
- PySpark read (spark.read.*) and write (df.write.*)

Unresolved dynamic dataset references are preserved explicitly.
"""

from __future__ import annotations

import ast
import logging
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DatasetRef(BaseModel):
    name: str = Field(description="Dataset identifier")
    ref_type: Literal["file", "table", "unresolved"] = Field(description="Reference type")
    raw: str | None = Field(default=None, description="Raw text for unresolved refs")
    line_start: int | None = Field(default=None, ge=1, description="First line of the reference")
    line_end: int | None = Field(default=None, ge=1, description="Last line of the reference")


class PythonLineage(BaseModel):
    sources: list[DatasetRef] = Field(default_factory=list)
    sinks: list[DatasetRef] = Field(default_factory=list)
    parse_ok: bool = True
    error: str | None = None


def extract_python_lineage(py_text: str) -> PythonLineage:
    try:
        tree = ast.parse(py_text)
    except SyntaxError as e:
        logger.warning("Python parse failed: %s", e)
        return PythonLineage(parse_ok=False, error=str(e))

    sources: list[DatasetRef] = []
    sinks: list[DatasetRef] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _call_name(node.func)
            line_start = getattr(node, "lineno", None)
            line_end = getattr(node, "end_lineno", None) or line_start

            if fn in {"pandas.read_csv", "pd.read_csv", "pandas.read_parquet", "pd.read_parquet"}:
                ref = _first_arg_str(node)
                if ref is not None:
                    sources.append(DatasetRef(name=ref, ref_type="file", line_start=line_start, line_end=line_end))
                else:
                    sources.append(DatasetRef(name="<dynamic>", ref_type="unresolved", raw=ast.unparse(node), line_start=line_start, line_end=line_end))
            if fn in {"pandas.read_sql", "pd.read_sql"}:
                sources.append(DatasetRef(name="<sql_query>", ref_type="unresolved", raw=ast.unparse(node), line_start=line_start, line_end=line_end))
            if fn.endswith(".execute") and fn.startswith(("engine.", "conn.", "connection.")):
                sinks.append(DatasetRef(name="<sql_exec>", ref_type="unresolved", raw=ast.unparse(node), line_start=line_start, line_end=line_end))

            # PySpark read: spark.read.csv(path), spark.read.parquet(path), spark.read.table(name)
            if fn.startswith("spark.read"):
                path_or_table = _first_arg_str(node) or "<spark_read>"
                ref_type = "table" if ".table(" in fn or fn.endswith(".table") else ("file" if path_or_table != "<spark_read>" else "unresolved")
                sources.append(DatasetRef(name=path_or_table, ref_type=ref_type, raw=ast.unparse(node) if path_or_table == "<spark_read>" else None, line_start=line_start, line_end=line_end))

            # PySpark write: df.write.saveAsTable(name), df.write.parquet(path), etc.
            if ".write." in fn:
                path_or_table = _first_arg_str(node) or "<spark_write>"
                ref_type = "table" if "saveAsTable" in fn or "insertInto" in fn else ("file" if path_or_table != "<spark_write>" else "unresolved")
                sinks.append(DatasetRef(name=path_or_table, ref_type=ref_type, raw=ast.unparse(node) if path_or_table == "<spark_write>" else None, line_start=line_start, line_end=line_end))

    return PythonLineage(sources=sources, sinks=sinks)


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Attribute):
        return f"{_call_name(func.value)}.{func.attr}"
    if isinstance(func, ast.Name):
        return func.id
    return "<unknown>"


def _first_arg_str(call: ast.Call) -> str | None:
    if not call.args:
        return None
    a = call.args[0]
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return a.value
    return None
