import json
from pathlib import Path
from query.tools import load_module_graph, load_lineage_graph, find_implementation, trace_lineage, blast_radius, explain_module

def test_load_module_graph(tmp_path):
    d = tmp_path / ".cartography"
    d.mkdir()
    data = {"directed": True, "nodes": [{"id": "a.py", "attrs": {}}], "edges": []}
    (d / "module_graph.json").write_text(json.dumps(data), encoding="utf-8")
    g = load_module_graph(d)
    assert g is not None
    assert "a.py" in g.nodes()

def test_load_lineage_graph(tmp_path):
    d = tmp_path / ".cartography"
    d.mkdir()
    data = {"directed": True, "nodes": [{"id": "tbl", "attrs": {}}], "edges": []}
    (d / "lineage_graph.json").write_text(json.dumps(data), encoding="utf-8")
    g = load_lineage_graph(d)
    assert g is not None
    assert "tbl" in g.nodes()

def test_find_implementation(tmp_path):
    d = tmp_path / ".cartography"
    d.mkdir()
    (d / "module_graph.json").write_text(json.dumps({"directed": True, "nodes": [{"id": "src/etl.py", "attrs": {}}], "edges": []}), encoding="utf-8")
    matches = find_implementation(d, "etl")
    assert any("etl" in m.path for m in matches)

def test_trace_lineage(tmp_path):
    d = tmp_path / ".cartography"
    d.mkdir()
    lg = {"directed": True, "nodes": [{"id": "a", "attrs": {}}, {"id": "b", "attrs": {}}], "edges": [{"source": "a", "target": "b", "attrs": {}}]}
    (d / "lineage_graph.json").write_text(json.dumps(lg), encoding="utf-8")
    r = trace_lineage(d, "b", direction="upstream")
    assert r.start == "b"
    assert "a" in r.nodes and "b" in r.nodes

def test_blast_radius(tmp_path):
    d = tmp_path / ".cartography"
    d.mkdir()
    lg = {"directed": True, "nodes": [{"id": "a", "attrs": {}}, {"id": "b", "attrs": {}}], "edges": [{"source": "a", "target": "b", "attrs": {}}]}
    (d / "lineage_graph.json").write_text(json.dumps(lg), encoding="utf-8")
    r = blast_radius(d, "a")
    assert r.start == "a"
    assert "b" in r.affected

def test_explain_module(tmp_path):
    d = tmp_path / ".cartography"
    d.mkdir()
    (d / "module_graph.json").write_text(json.dumps({"directed": True, "nodes": [{"id": "x.py", "attrs": {}}], "edges": []}), encoding="utf-8")
    e = explain_module(d, "x.py")
    assert e.path == "x.py"
    assert "x.py" in e.graph_section
