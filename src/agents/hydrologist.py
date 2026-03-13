"""Hydrologist agent: Data Flow & Lineage Analyst.

Constructs the data lineage DAG by analyzing data sources, transformations, and sinks
across all languages in the repo.

Supported input patterns:
- Python: pandas read/write, SQLAlchemy, PySpark
- SQL/dbt: sqlglot-parsed table dependencies (SELECT/FROM/JOIN/CTE)
- YAML/Config: Airflow DAGs, dbt schema.yml, Prefect flows
- Notebooks: Jupyter .ipynb code cells (data source refs and output paths)

Output: DataLineageGraph (NetworkX DiGraph) with nodes = datasets/tables/transformations;
edges carry transformation_type, source_file, line_start, line_end.

Query methods: find_sources, find_sinks, trace_lineage, blast_radius,
upstream_dependencies, schema_change_impact.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, Field

from analyzers.python_dataflow import extract_python_lineage
from analyzers.sql_lineage import SqlDialect, extract_sql_lineage
from analyzers.dag_config_parser import parse_yaml_config
from analyzers.notebook_parser import extract_code_cells
from repository.file_discovery import discover_files

logger = logging.getLogger(__name__)

# Canonical transformation types for edge metadata (serialized in lineage_graph.json).
TRANSFORMATION_TYPE_SQL = "sql"
TRANSFORMATION_TYPE_DBT = "dbt"
TRANSFORMATION_TYPE_PYTHON_PANDAS = "python_pandas"
TRANSFORMATION_TYPE_PYTHON_SQLALCHEMY = "python_sqlalchemy"
TRANSFORMATION_TYPE_PYTHON_PYSPARK = "python_pyspark"
TRANSFORMATION_TYPE_NOTEBOOK = "notebook"
TRANSFORMATION_TYPE_YAML_DBT = "yaml_dbt"
TRANSFORMATION_TYPE_YAML_AIRFLOW = "yaml_airflow"
TRANSFORMATION_TYPE_YAML_PREFECT = "yaml_prefect"


class LineageNode(BaseModel):
    id: str = Field(description="Node id")
    node_type: Literal["dataset", "transformation", "unresolved"]


class LineageEdge(BaseModel):
    source: str
    target: str
    edge_type: Literal["consumes", "produces", "configures", "depends_on"]
    transformation_type: str | None = None
    source_file: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    evidence: str | None = None


@dataclass(frozen=True)
class HydrologistResult:
    """Result of build_lineage_graph: the DataLineageGraph (NetworkX DiGraph)."""

    graph: nx.DiGraph


def _edge_attrs(
    edge_type: str,
    transformation_type: str,
    source_file: str,
    line_start: int | None = None,
    line_end: int | None = None,
    evidence: str | None = None,
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "edge_type": edge_type,
        "transformation_type": transformation_type,
        "source_file": source_file,
    }
    if line_start is not None:
        attrs["line_start"] = line_start
    if line_end is not None:
        attrs["line_end"] = line_end
    if evidence is not None:
        attrs["evidence"] = evidence
    return attrs


def build_lineage_graph(repo_root: Path | str, *, dialect: SqlDialect = "postgres") -> HydrologistResult:
    root = Path(repo_root).resolve()
    files = discover_files(root)

    g = nx.DiGraph()

    def add_dataset(ref_name: str, unresolved: bool = False):
        if ref_name not in g:
            g.add_node(ref_name, node_type="unresolved" if unresolved else "dataset")

    def add_edge(
        src: str,
        dst: str,
        edge_type: str,
        transformation_type: str,
        source_file: str,
        line_start: int | None = None,
        line_end: int | None = None,
        evidence: str | None = None,
    ):
        attrs = _edge_attrs(edge_type, transformation_type, source_file, line_start, line_end, evidence)
        if g.has_edge(src, dst):
            existing = dict(g.edges[src, dst])
            attrs = {**existing, **attrs}
        g.add_edge(src, dst, **attrs)

    for f in files:
        ext = f.extension
        path = f.path

        if ext == ".sql":
            lineage = extract_sql_lineage(f.content.decode("utf-8", errors="replace"), dialect=dialect)
            t_id = f"sql:{path}"
            g.add_node(t_id, node_type="transformation")
            ls = lineage.statement_line_start or 1
            le = lineage.statement_line_end or 1
            tt = TRANSFORMATION_TYPE_DBT if any(s.ref_type in ("dbt_ref", "dbt_source") for s in lineage.sources) else TRANSFORMATION_TYPE_SQL
            for s in lineage.sources:
                add_dataset(s.name, unresolved=(s.ref_type in {"dbt_ref", "dbt_source", "unresolved"}))
                add_edge(s.name, t_id, "consumes", tt, path, ls, le, s.raw)
            for t in lineage.targets:
                add_dataset(t.name, unresolved=(t.ref_type != "table"))
                add_edge(t_id, t.name, "produces", tt, path, ls, le)

        elif ext == ".py":
            pl = extract_python_lineage(f.content.decode("utf-8", errors="replace"))
            t_id = f"py:{path}"
            g.add_node(t_id, node_type="transformation")
            for s in pl.sources:
                add_dataset(s.name, unresolved=(s.ref_type == "unresolved"))
                raw = s.raw or ""
                tt = TRANSFORMATION_TYPE_PYTHON_PANDAS if ("read_csv" in raw or "read_parquet" in raw) else TRANSFORMATION_TYPE_PYTHON_PYSPARK if "spark.read" in raw else TRANSFORMATION_TYPE_PYTHON_SQLALCHEMY
                add_edge(s.name, t_id, "consumes", tt, path, s.line_start, s.line_end, s.raw)
            for t in pl.sinks:
                add_dataset(t.name, unresolved=(t.ref_type == "unresolved"))
                raw = t.raw or ""
                tt = TRANSFORMATION_TYPE_PYTHON_PYSPARK if ".write." in raw else TRANSFORMATION_TYPE_PYTHON_SQLALCHEMY
                add_edge(t_id, t.name, "produces", tt, path, t.line_start, t.line_end, t.raw)

        elif ext in {".yaml", ".yml"}:
            cfg = parse_yaml_config(f.content.decode("utf-8", errors="replace"), source_path=path)
            for e in cfg.edges:
                add_dataset(e.source, unresolved=False)
                add_dataset(e.target, unresolved=False)
                if e.kind == "CONFIGURES":
                    tt = TRANSFORMATION_TYPE_YAML_DBT
                elif e.kind == "AIRFLOW_TASK":
                    tt = TRANSFORMATION_TYPE_YAML_AIRFLOW
                elif e.kind == "PREFECT_TASK":
                    tt = TRANSFORMATION_TYPE_YAML_PREFECT
                else:
                    tt = TRANSFORMATION_TYPE_YAML_DBT
                add_edge(e.source, e.target, "configures" if e.kind == "CONFIGURES" else "depends_on", tt, path, e.line_start, e.line_end)

        elif ext == ".ipynb":
            nb = extract_code_cells(f.content)
            t_id = f"nb:{path}"
            g.add_node(t_id, node_type="transformation")
            for cell in nb.code_cells:
                pl = extract_python_lineage(cell)
                for s in pl.sources:
                    add_dataset(s.name, unresolved=(s.ref_type == "unresolved"))
                    add_edge(s.name, t_id, "consumes", TRANSFORMATION_TYPE_NOTEBOOK, path, s.line_start, s.line_end, s.raw)
                for t in pl.sinks:
                    add_dataset(t.name, unresolved=(t.ref_type == "unresolved"))
                    add_edge(t_id, t.name, "produces", TRANSFORMATION_TYPE_NOTEBOOK, path, t.line_start, t.line_end, t.raw)

    return HydrologistResult(graph=g)


def find_sources(graph: nx.DiGraph) -> set[str]:
    """Datasets with no incoming edges."""
    return {n for n in graph.nodes() if graph.in_degree(n) == 0}


def find_sinks(graph: nx.DiGraph) -> set[str]:
    """Datasets with no outgoing edges."""
    return {n for n in graph.nodes() if graph.out_degree(n) == 0}


def trace_lineage(graph: nx.DiGraph, start: str, *, direction: Literal['upstream', 'downstream'] = 'upstream', max_depth: int = 5) -> set[str]:
    """Return nodes reachable upstream or downstream within max_depth."""
    visited = {start}
    frontier = {start}

    for _ in range(max_depth):
        nxt = set()
        for n in frontier:
            neighbors = graph.predecessors(n) if direction == 'upstream' else graph.successors(n)
            for nb in neighbors:
                if nb not in visited:
                    visited.add(nb)
                    nxt.add(nb)
        if not nxt:
            break
        frontier = nxt

    return visited


def blast_radius(graph: nx.DiGraph, start: str, *, max_depth: int = 5) -> set[str]:
    """Downstream impact set."""
    return trace_lineage(graph, start, direction="downstream", max_depth=max_depth)


def upstream_dependencies(
    graph: nx.DiGraph,
    table_or_dataset: str,
    *,
    max_depth: int = 10,
    include_evidence: bool = True,
) -> dict[str, Any]:
    """
    Answer: 'Show me all upstream dependencies of table X'.

    Returns nodes reachable upstream (sources, transformations that feed this node)
    and optionally per-edge evidence (source_file, line_range, transformation_type).
    """
    nodes = trace_lineage(graph, table_or_dataset, direction="upstream", max_depth=max_depth)
    edges_with_evidence: list[dict[str, Any]] = []
    if include_evidence:
        for u, v in graph.edges():
            if v in nodes and u in nodes:
                attrs = dict(graph.edges[u, v])
                edges_with_evidence.append(
                    {
                        "source": u,
                        "target": v,
                        "transformation_type": attrs.get("transformation_type"),
                        "source_file": attrs.get("source_file"),
                        "line_range": (attrs.get("line_start"), attrs.get("line_end"))
                        if attrs.get("line_start") is not None
                        else None,
                    }
                )
    return {"dataset": table_or_dataset, "upstream_nodes": sorted(nodes), "edges": edges_with_evidence}


def schema_change_impact(
    graph: nx.DiGraph,
    table_or_dataset: str,
    *,
    max_depth: int = 10,
    include_evidence: bool = True,
) -> dict[str, Any]:
    """
    Answer: 'What would break if I change the schema of table Y?'

    Returns all nodes downstream of the given table (transformations and datasets
    that consume it), with source_file and line_range so you can find where
    to update code.
    """
    nodes = trace_lineage(graph, table_or_dataset, direction="downstream", max_depth=max_depth)
    nodes.discard(table_or_dataset)
    edges_with_evidence: list[dict[str, Any]] = []
    if include_evidence:
        for u, v in graph.edges():
            if u in nodes or u == table_or_dataset:
                if v in nodes or v == table_or_dataset:
                    attrs = dict(graph.edges[u, v])
                    edges_with_evidence.append(
                        {
                            "source": u,
                            "target": v,
                            "transformation_type": attrs.get("transformation_type"),
                            "source_file": attrs.get("source_file"),
                            "line_range": (attrs.get("line_start"), attrs.get("line_end"))
                            if attrs.get("line_start") is not None
                            else None,
                        }
                    )
    return {
        "dataset": table_or_dataset,
        "affected_downstream_nodes": sorted(nodes),
        "edges": edges_with_evidence,
    }
