"""Tests for Navigator agent: query interface over artifacts."""

import json
from pathlib import Path

from agents.navigator import Navigator


def _make_artifact_dir(tmp_path):
    d = tmp_path / ".cartography"
    d.mkdir()
    (d / "module_graph.json").write_text(
        json.dumps({
            "directed": True,
            "nodes": [{"id": "a.py", "attrs": {}}, {"id": "b.py", "attrs": {}}],
            "edges": [{"source": "a.py", "target": "b.py", "attrs": {}}],
        }),
        encoding="utf-8",
    )
    (d / "lineage_graph.json").write_text(
        json.dumps({
            "directed": True,
            "nodes": [{"id": "input", "attrs": {"node_type": "dataset"}}, {"id": "output", "attrs": {"node_type": "dataset"}}],
            "edges": [{"source": "input", "target": "output", "attrs": {"edge_type": "produces"}}],
        }),
        encoding="utf-8",
    )
    return d


def test_navigator_find_implementation(tmp_path):
    art = _make_artifact_dir(tmp_path)
    nav = Navigator(art)
    out = nav.find_implementation("a")
    assert isinstance(out, str)
    assert "a.py" in out or "No implementations" in out
    assert "Graph-backed" in out or "implementation" in out.lower()


def test_navigator_trace_lineage(tmp_path):
    art = _make_artifact_dir(tmp_path)
    nav = Navigator(art)
    out = nav.trace_lineage("output", direction="upstream")
    assert isinstance(out, str)
    assert "output" in out
    assert "Evidence" in out or "static analysis" in out or "Graph-backed" in out
    assert "input" in out


def test_navigator_blast_radius(tmp_path):
    art = _make_artifact_dir(tmp_path)
    nav = Navigator(art)
    out = nav.blast_radius("input")
    assert isinstance(out, str)
    assert "input" in out
    assert "Evidence" in out or "static analysis" in out or "Graph-backed" in out
    assert "Affected" in out or "affected" in out


def test_navigator_explain_module(tmp_path):
    art = _make_artifact_dir(tmp_path)
    nav = Navigator(art)
    out = nav.explain_module("a.py")
    assert isinstance(out, str)
    assert "a.py" in out
    assert "Evidence" in out or "Graph-backed" in out
    assert "Semantic" in out
