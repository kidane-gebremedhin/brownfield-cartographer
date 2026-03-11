"""Unit tests for YAML/dbt-like config parser (models, sources)."""

from analyzers.dag_config_parser import ConfigEdge, ConfigParseResult, parse_yaml_config


def test_parse_sources_only():
    yaml_text = """
sources:
  - name: raw
    tables:
      - name: users
      - name: events
"""
    r = parse_yaml_config(yaml_text)
    assert r.parse_ok
    assert len(r.edges) >= 2
    kinds = [e.kind for e in r.edges]
    assert "CONFIGURES" in kinds
    names = [e.target for e in r.edges]
    assert any("users" in n for n in names)
    assert any("events" in n for n in names)


def test_parse_models_depends_on():
    yaml_text = """
models:
  - name: stg_users
    depends_on:
      nodes: []
  - name: fct_orders
    depends_on:
      nodes: ["stg_users", "raw.events"]
"""
    r = parse_yaml_config(yaml_text)
    assert r.parse_ok
    dep_edges = [e for e in r.edges if e.kind == "DEPENDS_ON"]
    assert any(e.source == "model:fct_orders" and e.target == "stg_users" for e in dep_edges)
    assert any(e.target == "raw.events" for e in dep_edges)


def test_parse_empty():
    r = parse_yaml_config("")
    assert r.parse_ok
    assert r.edges == []


def test_parse_invalid_yaml():
    r = parse_yaml_config("not: valid: yaml [[[")
    assert r.parse_ok is False or len(r.edges) == 0
    assert r.error or not r.parse_ok
