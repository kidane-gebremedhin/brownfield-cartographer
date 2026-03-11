"""
Graph serializers for archivist artifacts.

Produces deterministic, machine-readable JSON payloads for:
- module import graph
- data lineage graph

Designed to be consumed later by Navigator without rerunning analysis.
"""

from __future__ import annotations

from typing import Any

import networkx as nx


def serialize_digraph(graph: nx.DiGraph) -> dict[str, Any]:
    """
    Serialize a directed graph into a stable JSON-friendly dict.

    Output shape:
    {
      "directed": true,
      "nodes": [{"id": "...", "attrs": {...}}, ...],
      "edges": [{"source": "...", "target": "...", "attrs": {...}}, ...]
    }
    """
    nodes = []
    for nid, attrs in graph.nodes(data=True):
        nodes.append({"id": str(nid), "attrs": _jsonable(attrs)})
    nodes.sort(key=lambda x: x["id"])

    edges = []
    for u, v, attrs in graph.edges(data=True):
        edges.append({"source": str(u), "target": str(v), "attrs": _jsonable(attrs)})
    edges.sort(key=lambda e: (e["source"], e["target"]))

    return {"directed": True, "nodes": nodes, "edges": edges}


def _jsonable(obj: Any) -> Any:
    """Best-effort conversion of common objects to JSON-compatible types."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(x) for x in obj]
    # Pydantic models / dataclasses often have model_dump or __dict__
    if hasattr(obj, "model_dump"):
        try:
            return _jsonable(obj.model_dump())
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return _jsonable({k: v for k, v in obj.__dict__.items() if not k.startswith("_")})
        except Exception:
            pass
    return str(obj)

