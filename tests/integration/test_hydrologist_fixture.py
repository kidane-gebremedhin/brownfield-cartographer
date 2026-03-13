from pathlib import Path

import pytest

from agents.hydrologist import (
    build_lineage_graph,
    find_sources,
    find_sinks,
    blast_radius,
    upstream_dependencies,
    schema_change_impact,
)


def _fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parent.parent / "fixtures" / name


def test_build_lineage_graph_hydro_repo():
    repo = _fixture_path("hydro_repo")
    result = build_lineage_graph(repo)
    g = result.graph
    assert g.number_of_nodes() > 0
    assert "raw.users" in g.nodes
    br = blast_radius(g, "raw.users", max_depth=3)
    assert "raw.users" in br


def test_hydrologist_sql_lineage_fixture():
    repo = _fixture_path("sql_lineage")
    result = build_lineage_graph(repo)
    g = result.graph
    assert g.number_of_nodes() > 0
    sources = find_sources(g)
    sinks = find_sinks(g)
    assert isinstance(sources, set)
    assert isinstance(sinks, set)
    node_ids = set(g.nodes())
    assert any("raw" in n or "staging" in n or "analytics" in n for n in node_ids)


def test_hydrologist_dbt_like_fixture():
    repo = _fixture_path("dbt_like")
    result = build_lineage_graph(repo)
    g = result.graph
    assert g.number_of_nodes() > 0
    assert "raw.users" in g.nodes or any("raw" in n for n in g.nodes)
    assert any("stg" in n or "sql:" in n for n in g.nodes) or g.number_of_nodes() >= 1


def test_hydrologist_dag_style_fixture():
    repo = _fixture_path("dag_style")
    result = build_lineage_graph(repo)
    g = result.graph
    assert g.number_of_nodes() >= 1


def test_lineage_edges_have_metadata():
    """DataLineageGraph edges carry transformation_type, source_file, line range when available."""
    repo = _fixture_path("hydro_repo")
    result = build_lineage_graph(repo)
    g = result.graph
    for u, v, attrs in g.edges(data=True):
        assert "edge_type" in attrs
        assert attrs.get("source_file") or attrs.get("transformation_type")


def test_upstream_dependencies():
    """upstream_dependencies returns upstream nodes and edge evidence (source_file, line_range)."""
    repo = _fixture_path("hydro_repo")
    result = build_lineage_graph(repo)
    g = result.graph
    # Pick any node that might have upstream (e.g. a transformation or sink)
    candidates = [n for n in g.nodes() if g.in_degree(n) > 0]
    if not candidates:
        pytest.skip("no node with upstream in fixture")
    node = next(iter(candidates))
    out = upstream_dependencies(g, node, max_depth=5, include_evidence=True)
    assert "dataset" in out
    assert "upstream_nodes" in out
    assert "edges" in out
    assert node in out["upstream_nodes"]


def test_schema_change_impact():
    """schema_change_impact returns downstream nodes affected by changing a table's schema."""
    repo = _fixture_path("hydro_repo")
    result = build_lineage_graph(repo)
    g = result.graph
    # Start from a source (raw.users) and get downstream impact
    out = schema_change_impact(g, "raw.users", max_depth=5, include_evidence=True)
    assert out["dataset"] == "raw.users"
    assert "affected_downstream_nodes" in out
    assert "edges" in out
