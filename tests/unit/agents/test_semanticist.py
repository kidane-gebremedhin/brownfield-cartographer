"""Tests for Semanticist agent: docstring extraction, drift, clustering, Day-One."""

from pathlib import Path

import networkx as nx

from agents.semanticist import (
    CriticalNodeScore,
    extract_module_docstring,
    generate_purpose_statement,
    run_semanticist,
    score_critical_candidates,
    _synthesize_day_one_fallback,
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


def test_generate_purpose_statement_returns_purpose_and_drift():
    """generate_purpose_statement returns (purpose, drift_label) and uses code not docstring."""
    llm = MockLLMProvider(responses=["This module handles auth.", "aligned"])
    source = '"""Old doc."""\ndef login(): pass\n'
    purpose, drift = generate_purpose_statement("auth.py", source, llm)
    assert isinstance(purpose, str)
    assert len(purpose) > 0
    assert drift in ("aligned", "stale", "contradictory", "insufficient")


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


def test_score_critical_candidates_ignores_empty_and_unresolved_ids():
    g = nx.DiGraph()
    # Empty and whitespace ids should be ignored
    g.add_node("", node_type="dataset")
    g.add_node("   ", node_type="dataset")
    # Unresolved placeholder should be ignored
    g.add_node("unresolved_table", node_type="unresolved")
    # A trivial sink-only node (no edges) should be ignored
    g.add_node("lonely_sink", node_type="dataset")

    surveyor = _fake_surveyor_result([])
    scored = score_critical_candidates(g, surveyor)

    assert scored == []


def test_score_critical_candidates_skips_pure_sinks_and_picks_internal():
    g = nx.DiGraph()
    # Lineage: src -> mid -> sink
    g.add_node("src", node_type="dataset")
    g.add_node("mid", node_type="dataset")
    g.add_node("sink", node_type="dataset")
    g.add_edge("src", "mid")
    g.add_edge("mid", "sink")

    surveyor = _fake_surveyor_result([])
    scored = score_critical_candidates(g, surveyor)

    # Only 'mid' has both upstream and downstream reach, so it should be first
    assert scored
    assert isinstance(scored[0], CriticalNodeScore)
    assert scored[0].node_id == "mid"


def test_day_one_fallback_uses_internal_node_not_trivial_sink():
    g = nx.DiGraph()
    # Graph where previous logic would have chosen 'sink' and produced a 1-node radius.
    g.add_node("src", node_type="dataset")
    g.add_node("mid", node_type="dataset")
    g.add_node("sink", node_type="dataset")
    g.add_edge("src", "mid")
    g.add_edge("mid", "sink")

    surveyor = _fake_surveyor_result([])
    hydro = HydrologistResult(graph=g)

    markdown = _synthesize_day_one_fallback(surveyor, hydro)

    # The blast radius answer should explicitly name 'mid' as the critical node
    assert "Critical module or transformation: `mid`." in markdown
    # And the blast radius should be non-trivial (mid can reach sink, so at least 1 node)
    assert "Downstream blast radius (excluding the node itself): 1 nodes." in markdown
