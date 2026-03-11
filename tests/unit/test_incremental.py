"""Tests for incremental update: manifest, change detection, trace."""

import json
from pathlib import Path

import networkx as nx
import pytest

from agents.surveyor import SurveyorResult, SurveyorModuleMetrics
from agents.hydrologist import HydrologistResult
from incremental import (
    ChangeSet,
    append_trace_event,
    compute_changes,
    get_current_hashes,
    load_manifest,
    save_manifest,
    trace_event_for_invalidate,
    trace_event_for_reuse,
)


def test_compute_changes_no_prior():
    current = {"a.py": "aa", "b.py": "bb"}
    out = compute_changes(None, current)
    assert out.unchanged is False
    assert set(out.added) == {"a.py", "b.py"}
    assert out.reason == "no prior manifest"


def test_compute_changes_unchanged():
    h = {"a.py": "aa", "b.py": "bb"}
    out = compute_changes(h, h.copy())
    assert out.unchanged is True
    assert out.added == []
    assert out.removed == []
    assert out.modified == []
    assert out.reason == "no file changes"


def test_compute_changes_single_modified():
    prior = {"a.py": "aa", "b.py": "bb"}
    current = {"a.py": "aa2", "b.py": "bb"}
    out = compute_changes(prior, current)
    assert out.unchanged is False
    assert out.modified == ["a.py"]
    assert out.added == []
    assert out.removed == []


def test_compute_changes_single_added():
    prior = {"a.py": "aa"}
    current = {"a.py": "aa", "b.py": "bb"}
    out = compute_changes(prior, current)
    assert out.unchanged is False
    assert out.added == ["b.py"]
    assert out.removed == []


def test_compute_changes_single_removed():
    prior = {"a.py": "aa", "b.py": "bb"}
    current = {"a.py": "aa"}
    out = compute_changes(prior, current)
    assert out.unchanged is False
    assert out.removed == ["b.py"]
    assert out.added == []


def test_compute_changes_multi_modified():
    prior = {"a.py": "aa", "b.py": "bb", "c.py": "cc"}
    current = {"a.py": "aa", "b.py": "bb2", "c.py": "cc2"}
    out = compute_changes(prior, current)
    assert out.unchanged is False
    assert sorted(out.modified) == ["b.py", "c.py"]


def test_load_manifest_missing(tmp_path):
    assert load_manifest(tmp_path) is None


def test_save_and_load_manifest(tmp_path):
    hashes = {"a.py": "h1", "b.py": "h2"}
    save_manifest(tmp_path, hashes)
    loaded = load_manifest(tmp_path)
    assert loaded == hashes


def test_append_trace_event(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    append_trace_event(tmp_path, {"event": "reuse", "files_checked": 5})
    path = tmp_path / "cartography_trace.jsonl"
    assert path.exists()
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "reuse"
    append_trace_event(tmp_path, {"event": "invalidate"})
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["event"] == "invalidate"


def test_trace_event_for_reuse():
    ev = trace_event_for_reuse(ChangeSet(unchanged=True, reason="no file changes"), 10)
    assert ev["event"] == "incremental_reuse"
    assert ev["files_checked"] == 10


def test_trace_event_for_invalidate():
    ev = trace_event_for_invalidate(
        ChangeSet(unchanged=False, added=["x.py"], removed=[], modified=["a.py"], reason="changes"),
        10,
    )
    assert ev["event"] == "incremental_invalidate"
    assert ev["added"] == ["x.py"]
    assert ev["modified"] == ["a.py"]


def test_get_current_hashes(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.py").write_text("y = 2")
    h = get_current_hashes(tmp_path)
    assert "a.py" in h
    assert "b.py" in h
    assert len(h["a.py"]) == 64
    assert h["a.py"] != h["b.py"]


def _minimal_surveyor_result():
    g = nx.DiGraph()
    g.add_node("a.py")
    m = SurveyorModuleMetrics("a.py", "python", 5, 1.0, 0, 0, 1, False)
    return SurveyorResult(graph=g, modules={"a.py": m}, pagerank={"a.py": 1.0}, sccs=[])


def _minimal_hydro_result():
    g = nx.DiGraph()
    g.add_node("tbl", node_type="dataset")
    return HydrologistResult(graph=g)


def test_incremental_no_change_reuses_artifacts(tmp_path, monkeypatch):
    """Second run with no file changes returns reused=True and skips re-analysis."""
    (tmp_path / "a.py").write_text("x = 1")
    artifact_dir = tmp_path / ".cartography"

    from repository.loader import LoadedRepository
    monkeypatch.setattr("orchestrator.load_repository", lambda *a, **k: LoadedRepository(root=tmp_path, is_temporary=False))
    monkeypatch.setattr("orchestrator.run_surveyor", lambda *a, **k: _minimal_surveyor_result())
    monkeypatch.setattr("orchestrator.build_lineage_graph", lambda *a, **k: _minimal_hydro_result())

    from orchestrator import run_analyze, AnalyzeOptions
    opts = AnalyzeOptions(input_path_or_url=str(tmp_path), output_dir=artifact_dir)

    first = run_analyze(opts)
    assert first.reused is False
    assert (artifact_dir / "manifest.json").exists()
    assert (artifact_dir / "module_graph.json").exists()

    second = run_analyze(opts)
    assert second.reused is True
    assert second.modules_analyzed == first.modules_analyzed


def test_incremental_single_file_change_invalidates(tmp_path, monkeypatch):
    """Changing one file triggers full re-run (reused=False)."""
    (tmp_path / "a.py").write_text("x = 1")
    artifact_dir = tmp_path / ".cartography"

    from repository.loader import LoadedRepository
    monkeypatch.setattr("orchestrator.load_repository", lambda *a, **k: LoadedRepository(root=tmp_path, is_temporary=False))
    monkeypatch.setattr("orchestrator.run_surveyor", lambda *a, **k: _minimal_surveyor_result())
    monkeypatch.setattr("orchestrator.build_lineage_graph", lambda *a, **k: _minimal_hydro_result())

    from orchestrator import run_analyze, AnalyzeOptions
    opts = AnalyzeOptions(input_path_or_url=str(tmp_path), output_dir=artifact_dir)
    run_analyze(opts)

    (tmp_path / "a.py").write_text("x = 2")
    second = run_analyze(opts)
    assert second.reused is False


def test_incremental_multi_file_change_invalidates(tmp_path, monkeypatch):
    """Adding and removing files triggers full re-run."""
    (tmp_path / "a.py").write_text("x = 1")
    artifact_dir = tmp_path / ".cartography"

    from repository.loader import LoadedRepository
    monkeypatch.setattr("orchestrator.load_repository", lambda *a, **k: LoadedRepository(root=tmp_path, is_temporary=False))
    monkeypatch.setattr("orchestrator.run_surveyor", lambda *a, **k: _minimal_surveyor_result())
    monkeypatch.setattr("orchestrator.build_lineage_graph", lambda *a, **k: _minimal_hydro_result())

    from orchestrator import run_analyze, AnalyzeOptions
    opts = AnalyzeOptions(input_path_or_url=str(tmp_path), output_dir=artifact_dir)
    run_analyze(opts)

    (tmp_path / "b.py").write_text("y = 2")
    second = run_analyze(opts)
    assert second.reused is False
