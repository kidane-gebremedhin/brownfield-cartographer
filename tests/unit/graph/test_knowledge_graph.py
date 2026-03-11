"""Tests for KnowledgeGraph wrapper."""

import json
from pathlib import Path

import networkx as nx

from graph.knowledge_graph import KnowledgeGraph


def test_knowledge_graph_wrap_and_roundtrip():
    g = nx.DiGraph()
    g.add_node("a", x=1)
    g.add_node("b")
    g.add_edge("a", "b", w=2)
    kg = KnowledgeGraph(g)
    d = kg.to_dict()
    assert d["directed"] is True
    assert len(d["nodes"]) == 2
    assert len(d["edges"]) == 1
    kg2 = KnowledgeGraph.from_dict(d)
    assert kg2.number_of_nodes() == 2
    assert kg2.number_of_edges() == 1
    assert list(kg2.graph.nodes()) == ["a", "b"]


def test_knowledge_graph_to_json_from_json(tmp_path):
    kg = KnowledgeGraph()
    kg.add_node("n1", node_type="dataset")
    kg.add_edge("n1", "n2", edge_type="produces")
    p = tmp_path / "graph.json"
    kg.to_json(p)
    assert p.exists()
    loaded = KnowledgeGraph.from_json(p)
    assert loaded.number_of_nodes() == 2
    assert loaded.number_of_edges() == 1
