import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx
import pytest

from cli import main as cli_main
from orchestrator import (
    AnalyzeOptions,
    AnalyzeResult,
    QueryResult,
    VisualizeResult,
    _graph_from_payload,
    run_analyze,
    run_query,
    run_visualize,
)


@dataclass(frozen=True)
class _FakeSurveyorResult:
    graph: nx.DiGraph
    modules: dict[str, Any]
    pagerank: dict[str, float]
    sccs: list[set[str]]


@dataclass(frozen=True)
class _FakeHydroResult:
    graph: nx.DiGraph


def test_graph_from_payload_roundtrip():
    g = nx.DiGraph()
    g.add_node("a", role="dataset")
    g.add_node("b", role="transformation")
    g.add_edge("a", "b", edge_type="consumes")

    payload = {
        "directed": True,
        "nodes": [
            {"id": "a", "attrs": {"role": "dataset"}},
            {"id": "b", "attrs": {"role": "transformation"}},
        ],
        "edges": [
            {"source": "a", "target": "b", "attrs": {"edge_type": "consumes"}},
        ],
    }

    g2 = _graph_from_payload(payload)
    assert set(g2.nodes()) == {"a", "b"}
    # Attributes may be stored directly or nested under \"attrs\" depending on implementation details.
    a_data = g2.nodes["a"]
    b_data = g2.nodes["b"]
    a_role = a_data.get("role", a_data.get("attrs", {}).get("role"))
    b_role = b_data.get("role", b_data.get("attrs", {}).get("role"))
    assert a_role == "dataset"
    assert b_role == "transformation"
    assert g2["a"]["b"]["edge_type"] == "consumes"


def test_run_visualize_regenerates_from_json(tmp_path, monkeypatch):
    artifact_dir = tmp_path / ".cartography"
    artifact_dir.mkdir()

    # Minimal payloads
    mg_payload = {
        "directed": True,
        "nodes": [{"id": "a.py", "attrs": {}}],
        "edges": [],
    }
    lg_payload = {
        "directed": True,
        "nodes": [{"id": "raw.users", "attrs": {"node_type": "dataset"}}],
        "edges": [],
    }
    (artifact_dir / "module_graph.json").write_text(json.dumps(mg_payload), encoding="utf-8")
    (artifact_dir / "lineage_graph.json").write_text(json.dumps(lg_payload), encoding="utf-8")

    # Ensure no HTML exists initially
    assert not (artifact_dir / "module_graph.html").exists()
    assert not (artifact_dir / "lineage_graph.html").exists()

    res = run_visualize(artifact_dir, open_browser=False)

    assert res.regenerated is True
    assert res.module_html.exists()
    assert res.lineage_html.exists()


def test_run_query_uses_existing_artifacts(tmp_path):
    artifact_dir = tmp_path / ".cartography"
    artifact_dir.mkdir()

    mg_payload = {"directed": True, "nodes": [{"id": "a.py", "attrs": {}}], "edges": []}
    lg_payload = {
        "directed": True,
        "nodes": [{"id": "raw.users", "attrs": {"node_type": "dataset"}}],
        "edges": [{"source": "raw.users", "target": "model", "attrs": {}}],
    }
    (artifact_dir / "module_graph.json").write_text(json.dumps(mg_payload), encoding="utf-8")
    (artifact_dir / "lineage_graph.json").write_text(json.dumps(lg_payload), encoding="utf-8")

    res = run_query(artifact_dir)
    assert res.modules == 1
    assert res.lineage_nodes == 1
    assert res.lineage_edges == 1


def test_cli_analyze_uses_orchestrator(monkeypatch, tmp_path, capsys):
    fake_artifacts = tmp_path / ".cartography"
    fake_artifacts.mkdir()

    def _fake_run_analyze(opts: AnalyzeOptions) -> AnalyzeResult:
        return AnalyzeResult(
            repo_root=Path("/fake/repo"),
            artifact_dir=fake_artifacts,
            modules_analyzed=3,
            lineage_nodes=5,
            lineage_edges=7,
        )

    monkeypatch.setattr("cli.run_analyze", _fake_run_analyze)

    code = cli_main(["analyze", "/fake/repo"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Artifacts written to" in captured.out
    assert ".cartography" in captured.out


def test_cli_query_uses_orchestrator(monkeypatch, capsys):
    def _fake_run_query(path: str | Path) -> QueryResult:
        return QueryResult(
            artifact_dir=Path(path),
            modules=10,
            lineage_nodes=20,
            lineage_edges=30,
        )

    monkeypatch.setattr("cli.run_query", _fake_run_query)

    code = cli_main(["query", "/tmp/artifacts"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Modules: 10" in captured.out


def test_cli_visualize_uses_orchestrator(monkeypatch, capsys):
    def _fake_run_visualize(path: str | Path, open_browser: bool = False) -> VisualizeResult:
        artifact_dir = Path(path)
        return VisualizeResult(
            artifact_dir=artifact_dir,
            module_html=artifact_dir / "module_graph.html",
            lineage_html=artifact_dir / "lineage_graph.html",
            regenerated=False,
        )

    monkeypatch.setattr("cli.run_visualize", _fake_run_visualize)

    code = cli_main(["visualize", "/tmp/artifacts"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Module graph HTML" in captured.out
    assert "Existing HTML graphs reused." in captured.out

