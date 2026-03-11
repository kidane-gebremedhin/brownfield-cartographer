"""SQL lineage extraction via sqlglot.

Responsibilities:
- Parse SQL with sqlglot.parse_one()
- Extract dataset/table dependencies from FROM/JOIN and write targets
- Preserve unresolved dynamic references (e.g. dbt ref/source) explicitly

Output is Pydantic-backed records suitable for building a NetworkX lineage graph.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


SqlDialect = Literal["postgres", "bigquery", "snowflake", "duckdb"]


class DatasetRef(BaseModel):
    """A resolved or unresolved dataset reference."""

    name: str = Field(description="Dataset identifier (table name, file path, model name, etc.)")
    ref_type: Literal["table", "dbt_ref", "dbt_source", "unresolved"] = Field(
        description="How this dataset was referenced"
    )
    raw: str | None = Field(default=None, description="Raw text for unresolved/dynamic refs")


class SqlLineage(BaseModel):
    """Lineage extracted from a single SQL statement."""

    sources: list[DatasetRef] = Field(default_factory=list)
    targets: list[DatasetRef] = Field(default_factory=list)
    ctes: list[str] = Field(default_factory=list, description="CTE names defined in this statement")
    parse_ok: bool = True
    error: str | None = None


_DBT_REF_RE = re.compile(r"\{\{\s*ref\(['\"]([^'\"]+)['\"]\)\s*\}\}")
_DBT_SOURCE_RE = re.compile(r"\{\{\s*source\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\)\s*\}\}")


def _extract_dbt_refs(sql_text: str) -> tuple[list[DatasetRef], list[DatasetRef]]:
    refs: list[DatasetRef] = []
    sources: list[DatasetRef] = []
    for m in _DBT_REF_RE.finditer(sql_text):
        refs.append(DatasetRef(name=m.group(1), ref_type="dbt_ref", raw=m.group(0)))
    for m in _DBT_SOURCE_RE.finditer(sql_text):
        sources.append(DatasetRef(name=f"{m.group(1)}.{m.group(2)}", ref_type="dbt_source", raw=m.group(0)))
    return refs, sources


def extract_sql_lineage(sql_text: str, *, dialect: SqlDialect = "postgres") -> SqlLineage:
    """Extract table lineage from SQL. Preserves dbt refs as unresolved refs if sqlglot can't parse."""
    sql_text = sql_text or ""

    # Pre-scan for dbt refs/sources (Jinja may break parsing)
    dbt_refs, dbt_sources = _extract_dbt_refs(sql_text)

    try:
        import sqlglot
        from sqlglot import exp

        tree = sqlglot.parse_one(sql_text, read=dialect)

        # CTEs
        ctes = []
        for cte in tree.find_all(exp.CTE):
            alias = cte.alias
            if alias:
                ctes.append(alias)

        # Tables referenced
        table_names: set[str] = set()
        for t in tree.find_all(exp.Table):
            # sqlglot Table has parts: db, catalog, name
            name = t.sql(dialect=dialect)
            table_names.add(name)

        # Write targets (INSERT/CREATE/CTAS)
        targets: set[str] = set()
        for node in tree.walk():
            if isinstance(node, exp.Insert):
                if node.this is not None:
                    targets.add(node.this.sql(dialect=dialect))
            if isinstance(node, exp.Create):
                if node.this is not None:
                    targets.add(node.this.sql(dialect=dialect))

        # Remove CTE names from sources if they appear as tables
        sources = [DatasetRef(name=n, ref_type="table") for n in sorted(table_names) if n not in set(ctes)]
        target_refs = [DatasetRef(name=n, ref_type="table") for n in sorted(targets)]

        # Add dbt refs/sources explicitly too
        sources.extend(dbt_sources)
        sources.extend(dbt_refs)

        return SqlLineage(sources=sources, targets=target_refs, ctes=ctes)

    except Exception as e:
        logger.warning("SQL parse failed; preserving dynamic refs: %s", e)
        # Preserve dbt refs as explicit unresolved sources
        sources = dbt_sources + dbt_refs

        # Best-effort fallback to extract obvious write targets when parsing fails.
        # This does not replace sqlglot; it only activates on parse failure.
        targets: list[DatasetRef] = []
        m = re.search(r"(?is)\binsert\s+into\s+([a-zA-Z_][\w]*)(?:\s*\.\s*([a-zA-Z_][\w]*))?", sql_text)
        if m:
            if m.group(2):
                targets.append(DatasetRef(name=f"{m.group(1)}.{m.group(2)}", ref_type="table", raw=m.group(0)))
            else:
                targets.append(DatasetRef(name=m.group(1), ref_type="table", raw=m.group(0)))

        m2 = re.search(r"(?is)\bcreate\s+table\s+([a-zA-Z_][\w]*)(?:\s*\.\s*([a-zA-Z_][\w]*))?", sql_text)
        if m2:
            if m2.group(2):
                targets.append(DatasetRef(name=f"{m2.group(1)}.{m2.group(2)}", ref_type="table", raw=m2.group(0)))
            else:
                targets.append(DatasetRef(name=m2.group(1), ref_type="table", raw=m2.group(0)))

        return SqlLineage(sources=sources, targets=targets, parse_ok=False, error=str(e))
