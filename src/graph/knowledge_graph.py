"""NetworkX wrapper with serialization.

Provides a unified API for module and lineage graphs: wrap DiGraph,
serialize to/from JSON-compatible dict, and read/write artifact files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from graph.serializers import deserialize_digraph, serialize_digraph


class KnowledgeGraph:
    """NetworkX DiGraph wrapper with serialize/deserialize and file I/O."""

    def __init__(self, graph: nx.DiGraph | None = None):
        self._graph = graph if graph is not None else nx.DiGraph()

    @property
    def graph(self) -> nx.DiGraph:
        """The underlying NetworkX DiGraph."""
        return self._graph

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict (stable node/edge ordering)."""
        return serialize_digraph(self._graph)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> KnowledgeGraph:
        """Deserialize from a dict produced by to_dict()."""
        return cls(graph=deserialize_digraph(payload))

    def to_json(self, path: Path | str) -> None:
        """Write the graph to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path | str) -> KnowledgeGraph:
        """Load the graph from a JSON file."""
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    def add_node(self, node_id: str, **attrs: Any) -> None:
        """Add a node. Delegates to the underlying graph."""
        self._graph.add_node(node_id, **attrs)

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        """Add an edge. Delegates to the underlying graph."""
        self._graph.add_edge(source, target, **attrs)

    def number_of_nodes(self) -> int:
        return self._graph.number_of_nodes()

    def number_of_edges(self) -> int:
        return self._graph.number_of_edges()
