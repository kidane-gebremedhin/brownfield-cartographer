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
    statement_line_start: int | None = Field(default=None, ge=1, description="First line of the SQL statement")
    statement_line_end: int | None = Field(default=None, ge=1, description="Last line of the SQL statement")
    parse_ok: bool = True
    error: str | None = None


_DBT_REF_RE = re.compile(r"\{\{\s*ref\(['\"]([^'\"]+)['\"]\)\s*\}\}")
_DBT_SOURCE_RE = re.compile(r"\{\{\s*source\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\)\s*\}\}")
# Match any Jinja expression so we can replace with a placeholder (avoids sqlglot getting stuck on {)
_JINJA_BLOCK_RE = re.compile(r"\{\{[\s\S]*?\}\}")


def _extract_dbt_refs(sql_text: str) -> tuple[list[DatasetRef], list[DatasetRef]]:
    refs: list[DatasetRef] = []
    sources: list[DatasetRef] = []
    for m in _DBT_REF_RE.finditer(sql_text):
        refs.append(DatasetRef(name=m.group(1), ref_type="dbt_ref", raw=m.group(0)))
    for m in _DBT_SOURCE_RE.finditer(sql_text):
        sources.append(DatasetRef(name=f"{m.group(1)}.{m.group(2)}", ref_type="dbt_source", raw=m.group(0)))
    return refs, sources


def _strip_jinja_for_parsing(sql_text: str) -> str:
    """Replace Jinja {{ ... }} with placeholder identifiers so sqlglot can parse the rest.

    dbt SQL often contains {{ ref('model') }}, {{ source('src','tbl') }}, {{ env_var(...) }}, etc.
    sqlglot fails on '{'; replacing with a valid identifier avoids parse failures and prevents
    the analyzer from getting stuck.
    """
    def repl(m: re.Match[str]) -> str:
        raw = m.group(0)
        # Use ref/source name as placeholder when possible so table names stay meaningful
        ref_m = _DBT_REF_RE.match(raw)
        if ref_m:
            return f'dbt_ref_{ref_m.group(1).replace(".", "_").replace("-", "_")}'
        src_m = _DBT_SOURCE_RE.match(raw)
        if src_m:
            return f'dbt_src_{src_m.group(1)}_{src_m.group(2)}'.replace(".", "_").replace("-", "_")
        return "dbt_expr"
    return _JINJA_BLOCK_RE.sub(repl, sql_text)


def _fallback_lineage(
    sql_text: str,
    dbt_refs: list[DatasetRef],
    dbt_sources: list[DatasetRef],
    num_lines: int,
    parse_error: Exception | None = None,
) -> SqlLineage:
    """Regex-only lineage when sqlglot cannot parse. Log at DEBUG to avoid flooding terminal."""
    logger.debug(
        "SQL parse skipped or partial; using dbt ref/source extraction only (regex). %s",
        parse_error if parse_error else "",
        extra={"dbt_refs": len(dbt_refs), "dbt_sources": len(dbt_sources)},
    )
    sources = dbt_sources + dbt_refs
    targets: list[DatasetRef] = []
    for m in re.finditer(r"(?is)\binsert\s+into\s+([a-zA-Z_][\w]*)(?:\s*\.\s*([a-zA-Z_][\w]*))?", sql_text):
        if m.group(2):
            targets.append(DatasetRef(name=f"{m.group(1)}.{m.group(2)}", ref_type="table", raw=m.group(0)))
        else:
            targets.append(DatasetRef(name=m.group(1), ref_type="table", raw=m.group(0)))
    for m in re.finditer(r"(?is)\bcreate\s+table\s+([a-zA-Z_][\w]*)(?:\s*\.\s*([a-zA-Z_][\w]*))?", sql_text):
        if m.group(2):
            targets.append(DatasetRef(name=f"{m.group(1)}.{m.group(2)}", ref_type="table", raw=m.group(0)))
        else:
            targets.append(DatasetRef(name=m.group(1), ref_type="table", raw=m.group(0)))
    return SqlLineage(
        sources=sources,
        targets=targets,
        statement_line_start=1,
        statement_line_end=num_lines,
        parse_ok=False,
        error="parse skipped; using regex fallback" + (f": {parse_error!s}" if parse_error else ""),
    )


def _parse_and_extract(
    parseable_sql: str,
    dialect: SqlDialect,
    dbt_refs: list[DatasetRef],
    dbt_sources: list[DatasetRef],
    num_lines: int,
) -> SqlLineage | None:
    """Parse with sqlglot (lenient) and extract lineage. Returns None on failure."""
    try:
        import sqlglot
        from sqlglot import exp
        from sqlglot.errors import ErrorLevel

        tree = sqlglot.parse_one(parseable_sql, read=dialect, error_level=ErrorLevel.IGNORE)
        if tree is None:
            return None

        ctes = []
        for cte in tree.find_all(exp.CTE):
            alias = cte.alias
            if alias:
                ctes.append(alias)

        table_names: set[str] = set()
        for t in tree.find_all(exp.Table):
            name = t.sql(dialect=dialect)
            if name.startswith("dbt_ref_") or name.startswith("dbt_src_") or name == "dbt_expr":
                continue
            table_names.add(name)

        targets: set[str] = set()
        for node in tree.walk():
            if isinstance(node, exp.Insert):
                if node.this is not None:
                    targets.add(node.this.sql(dialect=dialect))
            if isinstance(node, exp.Create):
                if node.this is not None:
                    targets.add(node.this.sql(dialect=dialect))

        sources = [DatasetRef(name=n, ref_type="table") for n in sorted(table_names) if n not in set(ctes)]
        target_refs = [DatasetRef(name=n, ref_type="table") for n in sorted(targets)]
        sources.extend(dbt_sources)
        sources.extend(dbt_refs)

        return SqlLineage(
            sources=sources,
            targets=target_refs,
            ctes=ctes,
            statement_line_start=1,
            statement_line_end=num_lines if num_lines else 1,
        )
    except Exception:
        return None


def extract_sql_lineage(sql_text: str, *, dialect: SqlDialect = "postgres") -> SqlLineage:
    """Extract table lineage from SQL. Strips Jinja (dbt) so sqlglot can parse; dbt refs/sources preserved.

    Uses sqlglot with ErrorLevel.IGNORE for lenient parsing. If that fails, tries other dialects.
    When all parsing fails, falls back to regex (dbt refs/sources + INSERT/CREATE). Parse
    failures are logged at DEBUG so the terminal is not flooded.
    """
    sql_text = sql_text or ""
    dbt_refs, dbt_sources = _extract_dbt_refs(sql_text)
    parseable_sql = _strip_jinja_for_parsing(sql_text)
    num_lines = len(sql_text.splitlines()) or 1

    # Try lenient parse with requested dialect, then other dialects (sqlglot supports 20+)
    dialects_to_try: list[SqlDialect] = [dialect, "postgres", "bigquery", "snowflake", "duckdb"]
    seen: set[str] = set()
    for d in dialects_to_try:
        if d in seen:
            continue
        seen.add(d)
        result = _parse_and_extract(parseable_sql, d, dbt_refs, dbt_sources, num_lines)
        if result is not None:
            return result

    return _fallback_lineage(sql_text, dbt_refs, dbt_sources, num_lines, None)
