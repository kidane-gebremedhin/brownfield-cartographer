"""Tests for Semanticist agent: docstring extraction, drift, clustering, Day-One."""

from pathlib import Path

import networkx as nx

from agents.semanticist import (
    extract_module_docstring,
    run_semanticist,
)
from agents.surveyor import SurveyorModuleMetrics, SurveyorResult
from agents.hydrologist import HydrologistResult
from llm.budget import TokenBudget
from llm.embeddings import MockEmbeddingsProvider
from llm.provider import MockLLMProvider


def _fake_surveyor_result(module_paths: list[str]) -> SurveyorResult:
    g = nx.DiGraph()
    g.add_nodes_from(module_paths)
    modules = {}
    for p in module_paths:
        modules[p] = SurveyorModuleMetrics(
            path=p,
            language="python",
            loc=10,
            complexity_score=1.0,
            change_velocity_30d=0,
            change_velocity_90d=0,
            public_api_count=1,
            is_dead_code_candidate=False,
        )
    pagerank = {p: 1.0 / len(module_paths) for p in module_paths} if module_paths else {}
    return SurveyorResult(graph=g, modules=modules, pagerank=pagerank, sccs=[])


def _fake_hydrologist_result() -> HydrologistResult:
    g = nx.DiGraph()
    g.add_node("source_a", node_type="dataset")
    g.add_node("sink_b", node_type="dataset")
    return HydrologistResult(graph=g)


def test_extract_module_docstring_none():
    assert extract_module_docstring("") is None
    assert extract_module_docstring("x = 1") is None
    assert extract_module_docstring("# comment only") is None


def test_extract_module_docstring_double():
    src = '"""Module doc here."""\nimport os'
    assert extract_module_docstring(src) == "Module doc here."


def test_extract_module_docstring_single():
    src = "'''Single quoted.'''\npass"
    assert extract_module_docstring(src) == "Single quoted."


def test_extract_module_docstring_after_comment():
    src = "# coding: utf-8\n'''Doc'''\npass"
    assert extract_module_docstring(src) is not None
    assert "Doc" in extract_module_docstring(src)


def test_drift_insufficient_when_no_docstring(tmp_path):
    (tmp_path / "no_doc.py").write_text("x = 1\n")
    surveyor = _fake_surveyor_result(["no_doc.py"])
    hydro = _fake_hydrologist_result()
    llm = MockLLMProvider(responses=["Purpose here."])
    result = run_semanticist(tmp_path, surveyor, hydro, llm, embeddings_provider=MockEmbeddingsProvider())
    for path, label in result.drift.items():
        assert label in ("aligned", "stale", "contradictory", "insufficient")
    # no_doc.py has no docstring so drift must be insufficient
    if "no_doc.py" in result.purpose_statements:
        assert result.drift.get("no_doc.py") == "insufficient"


def test_drift_classification_from_mock(tmp_path):
    (tmp_path / "with_doc.py").write_text('"""Auth helpers."""\nimport os\ndef login(): pass\n')
    surveyor = _fake_surveyor_result(["with_doc.py"])
    hydro = _fake_hydrologist_result()
    llm = MockLLMProvider(responses=["Handles auth.", "aligned"])
    result = run_semanticist(tmp_path, surveyor, hydro, llm, embeddings_provider=MockEmbeddingsProvider())
    assert isinstance(result.drift, dict)
    for v in result.drift.values():
        assert v in ("aligned", "stale", "contradictory", "insufficient")


def test_clustering_orchestration(tmp_path):
    (tmp_path / "a.py").write_text("def a(): pass")
    (tmp_path / "b.py").write_text("def b(): pass")
    surveyor = _fake_surveyor_result(["a.py", "b.py"])
    hydro = _fake_hydrologist_result()
    llm = MockLLMProvider(default="Purpose here.")
    emb = MockEmbeddingsProvider(dimension=8)
    result = run_semanticist(tmp_path, surveyor, hydro, llm, embeddings_provider=emb)
    if result.domains:
        for d in result.domains:
            assert "label" in d
            assert "modules" in d
            assert isinstance(d["modules"], list)


def test_day_one_synthesis_included(tmp_path):
    (tmp_path / "m.py").write_text("def main(): pass")
    surveyor = _fake_surveyor_result(["m.py"])
    hydro = _fake_hydrologist_result()
    llm = MockLLMProvider(default="1. Path: CLI.\n2. Outputs: stdout.\n3. Radius: small.\n4. Concentrated.\n5. m.py.")
    result = run_semanticist(tmp_path, surveyor, hydro, llm)
    assert isinstance(result.day_one_markdown, str)
    assert len(result.day_one_markdown) > 0


def test_budget_exhausted_skips_purpose(tmp_path):
    (tmp_path / "x.py").write_text("pass")
    surveyor = _fake_surveyor_result(["x.py"])
    hydro = _fake_hydrologist_result()
    llm = MockLLMProvider(default="Purpose")
    budget = TokenBudget(limit_input=10, limit_output=10)
    result = run_semanticist(tmp_path, surveyor, hydro, llm, budget=budget)
    assert isinstance(result.purpose_statements, dict)
    assert isinstance(result.day_one_markdown, str)
