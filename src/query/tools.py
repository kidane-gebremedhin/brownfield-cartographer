"""Query tools over persisted .cartography artifacts.

All tools operate offline from module_graph.json, lineage_graph.json, and optional
CODEBASE.md / onboarding_brief.md. No full pipeline re-run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import networkx as nx


@dataclass
class ImplementationMatch:
    path: str
    source: Literal["graph", "semantic"]
    confidence: float
    line_range: tuple[int, int] | None = None
    method_provenance: str = ""


@dataclass
class LineageResult:
    start: str
    direction: Literal["upstream", "downstream"]
    nodes: list[str]
    edges: list[tuple[str, str, dict[str, Any]]]
    source: Literal["graph"] = "graph"
    evidence: str = ""


@dataclass
class BlastRadiusResult:
    start: str
    affected: list[str]
    source: Literal["graph"] = "graph"
    evidence: str = ""


@dataclass
class ModuleExplanation:
    path: str
    graph_section: str
    semantic_section: str
    line_range: tuple[int, int] | None = None
    confidence: float = 1.0


def _load_graph(artifact_dir: Path, name: str) -> nx.DiGraph | None:
    path = artifact_dir / name
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _graph_from_payload(payload)
    except (json.JSONDecodeError, KeyError):
        return None


def _graph_from_payload(payload: dict[str, Any]) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in payload.get("nodes", []):
        attrs = n.get("attrs") or {}
        g.add_node(n["id"], **attrs)
    for e in payload.get("edges", []):
        attrs = e.get("attrs") or {}
        g.add_edge(e["source"], e["target"], **attrs)
    return g


def load_module_graph(artifact_dir: Path | str) -> nx.DiGraph | None:
    return _load_graph(Path(artifact_dir).resolve(), "module_graph.json")


def load_lineage_graph(artifact_dir: Path | str) -> nx.DiGraph | None:
    return _load_graph(Path(artifact_dir).resolve(), "lineage_graph.json")


def find_implementation(
    artifact_dir: Path | str,
    concept: str,
    *,
    max_results: int = 20,
) -> list[ImplementationMatch]:
    """Return likely modules/functions implementing a concept. Graph: node id match. Semantic: CODEBASE.md."""
    artifact_dir = Path(artifact_dir).resolve()
    out: list[ImplementationMatch] = []
    concept_lower = concept.lower().strip()
    if not concept_lower:
        return out

    # Graph-backed: module paths containing concept
    mg = load_module_graph(artifact_dir)
    if mg:
        for nid in mg.nodes():
            if concept_lower in nid.lower():
                out.append(
                    ImplementationMatch(
                        path=nid,
                        source="graph",
                        confidence=0.9 if concept_lower in nid.lower() else 0.6,
                        method_provenance="module graph (path substring match)",
                    )
                )
                if len(out) >= max_results:
                    return out[:max_results]

    # Semantic: CODEBASE.md Module Purpose Index
    codebase_path = artifact_dir / "CODEBASE.md"
    if codebase_path.exists():
        text = codebase_path.read_text(encoding="utf-8")
        in_purpose = False
        for line in text.splitlines():
            if line.strip() == "## Module Purpose Index":
                in_purpose = True
                continue
            if in_purpose and line.strip().startswith("##"):
                break
            if in_purpose and "`" in line and concept_lower in line.lower():
                # Parse "- `path`: purpose"
                try:
                    start = line.index("`") + 1
                    end = line.index("`", start)
                    path = line[start:end].strip()
                    if path and not any(m.path == path for m in out):
                        out.append(
                            ImplementationMatch(
                                path=path,
                                source="semantic",
                                confidence=0.7,
                                method_provenance="CODEBASE.md Module Purpose Index",
                            )
                        )
                        if len(out) >= max_results:
                            return out[:max_results]
                except ValueError:
                    pass

    return out[:max_results]


def trace_lineage(
    artifact_dir: Path | str,
    dataset: str,
    direction: Literal["upstream", "downstream"] = "upstream",
    *,
    max_depth: int = 5,
) -> LineageResult:
    """Return upstream or downstream lineage with evidence. Graph-only."""
    artifact_dir = Path(artifact_dir).resolve()
    lg = load_lineage_graph(artifact_dir)
    if not lg or dataset not in lg:
        return LineageResult(
            start=dataset,
            direction=direction,
            nodes=[],
            edges=[],
            evidence=f"Dataset '{dataset}' not in lineage graph or artifact missing.",
        )

    visited = {dataset}
    frontier = {dataset}
    for _ in range(max_depth):
        nxt = set()
        for n in frontier:
            neighbors = list(lg.predecessors(n) if direction == "upstream" else lg.successors(n))
            for nb in neighbors:
                if nb not in visited:
                    visited.add(nb)
                    nxt.add(nb)
        if not nxt:
            break
        frontier = nxt

    edges_list: list[tuple[str, str, dict[str, Any]]] = []
    for u, v in lg.edges():
        if u in visited and v in visited:
            attrs = dict(lg.edges[u, v])
            edges_list.append((u, v, attrs))

    evidence = f"Lineage graph traversal ({direction}, max_depth={max_depth}). Nodes: {len(visited)}."
    return LineageResult(
        start=dataset,
        direction=direction,
        nodes=sorted(visited),
        edges=edges_list,
        evidence=evidence,
    )


def blast_radius(
    artifact_dir: Path | str,
    module_or_dataset: str,
    *,
    max_depth: int = 5,
) -> BlastRadiusResult:
    """Return downstream dependencies affected by change/failure. Graph-only."""
    artifact_dir = Path(artifact_dir).resolve()
    lg = load_lineage_graph(artifact_dir)
    if not lg:
        return BlastRadiusResult(
            start=module_or_dataset,
            affected=[],
            evidence="Lineage graph artifact not found.",
        )
    if module_or_dataset not in lg:
        return BlastRadiusResult(
            start=module_or_dataset,
            affected=[],
            evidence=f"Node '{module_or_dataset}' not in lineage graph.",
        )

    visited = {module_or_dataset}
    frontier = {module_or_dataset}
    for _ in range(max_depth):
        nxt = set()
        for n in frontier:
            for nb in lg.successors(n):
                if nb not in visited:
                    visited.add(nb)
                    nxt.add(nb)
        if not nxt:
            break
        frontier = nxt

    affected = sorted(visited - {module_or_dataset})
    return BlastRadiusResult(
        start=module_or_dataset,
        affected=affected,
        evidence=f"Downstream traversal from lineage graph (max_depth={max_depth}). {len(affected)} nodes affected.",
    )


def explain_module(
    artifact_dir: Path | str,
    path: str,
) -> ModuleExplanation:
    """Return structural (graph) and semantic (CODEBASE) explanation of a module."""
    artifact_dir = Path(artifact_dir).resolve()
    graph_parts: list[str] = []
    semantic_parts: list[str] = []

    mg = load_module_graph(artifact_dir)
    if mg and path in mg:
        preds = list(mg.predecessors(path))
        succs = list(mg.successors(path))
        graph_parts.append(f"Module: {path}")
        graph_parts.append(f"Imported by ({len(preds)}): {', '.join(sorted(preds)[:15])}" + (" ..." if len(preds) > 15 else ""))
        graph_parts.append(f"Imports ({len(succs)}): {', '.join(sorted(succs)[:15])}" + (" ..." if len(succs) > 15 else ""))
    else:
        graph_parts.append(f"Module '{path}' not in module graph (or artifact missing).")

    codebase_path = artifact_dir / "CODEBASE.md"
    if codebase_path.exists():
        text = codebase_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if path in line and ("purpose" in line.lower() or "`" + path in line or "`" in line):
                semantic_parts.append(line.strip())
    if not semantic_parts:
        semantic_parts.append("(No purpose or description found in CODEBASE.md for this module.)")

    return ModuleExplanation(
        path=path,
        graph_section="\n".join(graph_parts),
        semantic_section="\n".join(semantic_parts),
        line_range=None,
        confidence=0.9 if (mg and path in mg) else 0.5,
    )
