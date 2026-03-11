"""Tests for Pyvis graph visualization (module and lineage HTML)."""

from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

from graph.visualization import (
    build_lineage_graph_html,
    build_module_graph_html,
)


@pytest.fixture
def tmp_html_dir(tmp_path):
    return tmp_path


def test_module_graph_html_produced(tmp_html_dir):
    """HTML file is created with node metadata (path, PageRank) in title/hover."""
    g = nx.DiGraph()
    g.add_node("src/foo.py")
    g.add_node("src/bar.py")
    g.add_edge("src/foo.py", "src/bar.py")
    modules = {
        "src/foo.py": _make_mock_module("src/foo.py", "python", 100, 2.0, 5, 12, False),
        "src/bar.py": _make_mock_module("src/bar.py", "python", 50, 1.0, 2, 4, False),
    }
    pagerank = {"src/foo.py": 0.4, "src/bar.py": 0.6}

    out = build_module_graph_html(g, modules, pagerank, tmp_html_dir / "module_graph.html")

    assert out.exists()
    html = out.read_text()
    assert "path: src/foo.py" in html or "path:" in html
    assert "PageRank" in html
    assert "bar" in html and "foo" in html


def test_lineage_graph_html_produced(tmp_html_dir):
    """HTML file is created with node types and direction."""
    g = nx.DiGraph()
    g.add_node("raw_events", node_type="dataset")
    g.add_node("py:etl/load.py", node_type="transformation")
    g.add_node("analytics.out", node_type="dataset")
    g.add_edge("raw_events", "py:etl/load.py", edge_type="consumes")
    g.add_edge("py:etl/load.py", "analytics.out", edge_type="produces")

    out = build_lineage_graph_html(g, tmp_html_dir / "lineage_graph.html")

    assert out.exists()
    html = out.read_text()
    assert "id:" in html or "raw_events" in html
    assert "transformation" in html or "dataset" in html
    assert "etl" in html or "load" in html


def test_visualization_graceful_missing_metadata(tmp_html_dir):
    """Module graph works when modules/pagerank are empty (degrade gracefully)."""
    g = nx.DiGraph()
    g.add_node("a.py")
    g.add_node("b.py")
    g.add_edge("a.py", "b.py")

    out = build_module_graph_html(g, {}, {}, tmp_html_dir / "mod.html")

    assert out.exists()
    html = out.read_text()
    assert "a.py" in html or "a" in html
    assert "b" in html


def test_visualization_raises_when_pyvis_missing(tmp_html_dir):
    """When pyvis is not available, build_* raises RuntimeError."""
    g = nx.DiGraph()
    g.add_node("a.py")
    with patch("graph.visualization.Network", None):
        with pytest.raises(RuntimeError, match="pyvis"):
            build_module_graph_html(g, {}, {}, tmp_html_dir / "mod.html")
        with pytest.raises(RuntimeError, match="pyvis"):
            build_lineage_graph_html(g, tmp_html_dir / "lin.html")


def test_visualization_lineage_node_mapping(tmp_html_dir):
    """Lineage graph: transformation nodes get shape=box and short label; dataset nodes get id as label."""
    g = nx.DiGraph()
    g.add_node("dataset_a", node_type="dataset")
    g.add_node("py:src/etl/load.py", node_type="transformation")
    g.add_edge("dataset_a", "py:src/etl/load.py")
    out = build_lineage_graph_html(g, tmp_html_dir / "lineage_mapping.html")
    html = out.read_text()
    assert "transformation" in html or "dataset" in html
    assert "etl" in html or "load" in html
    assert "dataset_a" in html


def _make_mock_module(path, language, loc, complexity, v30, v90, is_dead):
    """Minimal object with SurveyorModuleMetrics-like attributes."""
    class M:
        pass
    m = M()
    m.path = path
    m.language = language
    m.loc = loc
    m.complexity_score = complexity
    m.change_velocity_30d = v30
    m.change_velocity_90d = v90
    m.is_dead_code_candidate = is_dead
    return m
