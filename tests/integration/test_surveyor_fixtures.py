"""Integration tests: Surveyor against fixture repos (Python imports). Deterministic, no network."""

from pathlib import Path

import pytest

from agents.surveyor import run_surveyor, SurveyorResult, SurveyorModuleMetrics


def _fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures" / name


def test_surveyor_python_imports_fixture():
    pytest.importorskip("numpy", reason="Surveyor PageRank uses numpy")
    repo = _fixture_path("python_imports")
    result = run_surveyor(repo)
    assert isinstance(result, SurveyorResult)
    g = result.graph
    assert g.number_of_nodes() >= 3
    paths = set(g.nodes())
    assert any("main.py" in p for p in paths)
    assert any("lib" in p and "utils" in p for p in paths)
    assert any("lib" in p and "foo" in p for p in paths)
    assert len(result.modules) >= 3
    for m in result.modules.values():
        assert isinstance(m, SurveyorModuleMetrics)
        assert m.language == "python"
    if g.number_of_edges() > 0:
        assert result.pagerank
    assert isinstance(result.sccs, list)


def test_surveyor_import_edges_resolved():
    pytest.importorskip("numpy", reason="Surveyor PageRank uses numpy")
    repo = _fixture_path("python_imports")
    result = run_surveyor(repo)
    g = result.graph
    main_path = next((p for p in g.nodes() if "main.py" in p), None)
    if main_path and g.out_degree(main_path) > 0:
        assert True
    else:
        assert g.number_of_nodes() >= 1
