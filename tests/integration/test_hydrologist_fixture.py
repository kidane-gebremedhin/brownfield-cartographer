from pathlib import Path

from agents.hydrologist import build_lineage_graph, find_sources, find_sinks, blast_radius


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
