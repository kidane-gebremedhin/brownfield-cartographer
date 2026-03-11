"""Hydrologist agent: constructs the mixed-language data lineage graph.

Merges:
- Python read/write patterns
- SQL lineage (sqlglot)
- YAML/dbt config hints
- Notebook code cells

Produces a NetworkX directed lineage graph and provides query methods:
- find_sources
- find_sinks
- trace_lineage
- blast_radius

Unresolved/dynamic references are represented explicitly, not dropped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import networkx as nx
from pydantic import BaseModel, Field

from analyzers.python_dataflow import extract_python_lineage, DatasetRef as PyDatasetRef
from analyzers.sql_lineage import SqlDialect, extract_sql_lineage, DatasetRef as SqlDatasetRef
from analyzers.dag_config_parser import parse_yaml_config
from analyzers.notebook_parser import extract_code_cells
from repository.file_discovery import discover_files

logger = logging.getLogger(__name__)


class LineageNode(BaseModel):
    id: str = Field(description="Node id")
    node_type: Literal["dataset", "transformation", "unresolved"]


class LineageEdge(BaseModel):
    source: str
    target: str
    edge_type: Literal["consumes", "produces", "configures", "depends_on"]
    evidence: str | None = None


@dataclass(frozen=True)
class HydrologistResult:
    graph: nx.DiGraph


def build_lineage_graph(repo_root: Path | str, *, dialect: SqlDialect = "postgres") -> HydrologistResult:
    root = Path(repo_root).resolve()
    files = discover_files(root)

    g = nx.DiGraph()

    def add_dataset(ref_name: str, unresolved: bool = False):
        if ref_name not in g:
            g.add_node(ref_name, node_type="unresolved" if unresolved else "dataset")

    def add_edge(src: str, dst: str, edge_type: str, evidence: str | None = None):
        g.add_edge(src, dst, edge_type=edge_type, evidence=evidence)

    for f in files:
        ext = f.extension
        if ext == '.sql':
            lineage = extract_sql_lineage(f.content.decode('utf-8', errors='replace'), dialect=dialect)
            t_id = f"sql:{f.path}"
            g.add_node(t_id, node_type="transformation")
            for s in lineage.sources:
                add_dataset(s.name, unresolved=(s.ref_type in {"dbt_ref", "dbt_source", "unresolved"}))
                add_edge(s.name, t_id, "consumes", evidence=s.raw)
            for t in lineage.targets:
                add_dataset(t.name, unresolved=(t.ref_type != "table"))
                add_edge(t_id, t.name, "produces")

        elif ext == '.py':
            pl = extract_python_lineage(f.content.decode('utf-8', errors='replace'))
            t_id = f"py:{f.path}"
            g.add_node(t_id, node_type="transformation")
            for s in pl.sources:
                add_dataset(s.name, unresolved=(s.ref_type == "unresolved"))
                add_edge(s.name, t_id, "consumes", evidence=s.raw)
            for t in pl.sinks:
                add_dataset(t.name, unresolved=(t.ref_type == "unresolved"))
                add_edge(t_id, t.name, "produces", evidence=t.raw)

        elif ext in {'.yaml', '.yml'}:
            cfg = parse_yaml_config(f.content.decode('utf-8', errors='replace'))
            for e in cfg.edges:
                add_dataset(e.source, unresolved=False)
                add_dataset(e.target, unresolved=False)
                add_edge(e.source, e.target, "configures" if e.kind == "CONFIGURES" else "depends_on")

        elif ext == '.ipynb':
            nb = extract_code_cells(f.content)
            t_id = f"nb:{f.path}"
            g.add_node(t_id, node_type="transformation")
            for cell in nb.code_cells:
                pl = extract_python_lineage(cell)
                for s in pl.sources:
                    add_dataset(s.name, unresolved=(s.ref_type == "unresolved"))
                    add_edge(s.name, t_id, "consumes", evidence=s.raw)
                for t in pl.sinks:
                    add_dataset(t.name, unresolved=(t.ref_type == "unresolved"))
                    add_edge(t_id, t.name, "produces", evidence=t.raw)

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
    return trace_lineage(graph, start, direction='downstream', max_depth=max_depth)
