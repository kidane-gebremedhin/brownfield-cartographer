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
            if fn in {"pandas.read_csv", "pd.read_csv", "pandas.read_parquet", "pd.read_parquet"}:
                ref = _first_arg_str(node)
                if ref is not None:
                    sources.append(DatasetRef(name=ref, ref_type="file"))
                else:
                    sources.append(DatasetRef(name="<dynamic>", ref_type="unresolved", raw=ast.unparse(node)))
            if fn in {"pandas.read_sql", "pd.read_sql"}:
                # pandas.read_sql(query, con)
                sources.append(DatasetRef(name="<sql_query>", ref_type="unresolved", raw=ast.unparse(node)))
            if fn.endswith(".execute") and fn.startswith(("engine.", "conn.", "connection.")):
                sinks.append(DatasetRef(name="<sql_exec>", ref_type="unresolved", raw=ast.unparse(node)))

            # PySpark read
            if fn.startswith("spark.read"):
                sources.append(DatasetRef(name="<spark_read>", ref_type="unresolved", raw=ast.unparse(node)))

            # PySpark write patterns: df.write.*(path/table)
            if ".write." in fn:
                sinks.append(DatasetRef(name="<spark_write>", ref_type="unresolved", raw=ast.unparse(node)))

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
