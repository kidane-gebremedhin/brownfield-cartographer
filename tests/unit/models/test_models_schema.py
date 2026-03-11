"""Unit tests for knowledge-graph schema: validation and JSON serialization."""
import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from models.artifacts import CartographyArtifacts, CODEBASEContext, OnboardingBrief
from models.common import Evidence
from models.edges import EdgeType, TypedEdge
from models.graph_models import DataLineageGraph, ModuleGraph
from models.nodes import DatasetNode, FunctionNode, ModuleNode, TransformationNode
from models.trace import CartographyTraceEntry, agent_trace_entry


def test_evidence_validation():
    e = Evidence(source="static_analysis", confidence=0.9, raw="import foo")
    assert e.source == "static_analysis"
    assert e.confidence == 0.9
    with pytest.raises(ValidationError):
        Evidence(source="x", confidence=1.5)


def test_evidence_serialization():
    e = Evidence(source="lineage", confidence=0.8)
    d = e.model_dump(mode="json")
    assert d["source"] == "lineage"
    assert d["confidence"] == 0.8
    assert json.loads(e.model_dump_json()) == d


def test_module_node_validation():
    m = ModuleNode(path="src/foo.py", language="python", loc=10)
    assert m.path == "src/foo.py"
    assert m.complexity_score == 0.0
    m2 = ModuleNode(path="a.py", language="py", change_velocity_30d=5, public_api_count=2)
    assert m2.change_velocity_30d == 5


def test_module_node_datetime_serialization():
    m = ModuleNode(path="a.py", language="python", last_modified=datetime(2024, 1, 15, 12, 0, 0))
    d = m.model_dump(mode="json")
    assert "T" in d["last_modified"] and "2024" in d["last_modified"]
    js = m.model_dump_json()
    loaded = json.loads(js)
    assert loaded["last_modified"] == "2024-01-15T12:00:00"


def test_function_node():
    f = FunctionNode(qualified_name="mymod.main", parent_module="src/mymod.py", line_start=1, line_end=10)
    assert f.line_end == 10
    d = f.model_dump(mode="json")
    assert d["qualified_name"] == "mymod.main"


def test_dataset_node_storage_type():
    d = DatasetNode(name="raw.events", storage_type="table")
    assert d.storage_type == "table"
    d2 = DatasetNode(name="s3://b/p.parquet", storage_type="file")
    assert d2.storage_type == "file"
    with pytest.raises(ValidationError):
        DatasetNode(name="x", storage_type="invalid")


def test_transformation_node_line_range_serialization():
    t = TransformationNode(id="sql:m.sql", source_file="m.sql", line_range=(1, 20))
    d = t.model_dump(mode="json")
    assert d["line_range"] == [1, 20]
    js = t.model_dump_json()
    back = TransformationNode.model_validate_json(js)
    assert back.line_range == (1, 20)


def test_edge_type_enum():
    assert EdgeType.IMPORTS.value == "imports"
    assert EdgeType.CONSUMES.value == "consumes"


def test_typed_edge_with_evidence():
    ev = Evidence(source="parser", confidence=1.0)
    e = TypedEdge(source="a.py", target="b.py", edge_type=EdgeType.IMPORTS, evidence=ev)
    d = e.model_dump(mode="json")
    assert d["edge_type"] == "imports"
    assert d["evidence"]["source"] == "parser"
    e2 = TypedEdge(source="x", target="y", edge_type=EdgeType.PRODUCES)
    assert e2.evidence is None


def test_module_graph_serialization():
    g = ModuleGraph(
        module_nodes=[ModuleNode(path="a.py", language="python")],
        edges=[TypedEdge(source="a.py", target="b.py", edge_type=EdgeType.IMPORTS)],
    )
    d = g.model_dump(mode="json")
    assert len(d["module_nodes"]) == 1
    assert len(d["edges"]) == 1
    js = g.model_dump_json()
    g2 = ModuleGraph.model_validate_json(js)
    assert g2.module_nodes[0].path == "a.py"


def test_data_lineage_graph_serialization():
    g = DataLineageGraph(
        dataset_nodes=[DatasetNode(name="raw.x", storage_type="table")],
        transformation_nodes=[TransformationNode(id="sql:s.sql", source_file="s.sql", source_datasets=["raw.x"], target_datasets=["out"])],
        edges=[TypedEdge(source="raw.x", target="sql:s.sql", edge_type=EdgeType.CONSUMES)],
    )
    js = g.model_dump_json()
    g2 = DataLineageGraph.model_validate_json(js)
    assert len(g2.dataset_nodes) == 1
    assert g2.edges[0].edge_type == EdgeType.CONSUMES


def test_cartography_trace_entry():
    t = CartographyTraceEntry(event="incremental_reuse", reason="no file changes", files_checked=10)
    d = t.model_dump(mode="json")
    assert d["event"] == "incremental_reuse"
    assert d["files_checked"] == 10
    t2 = CartographyTraceEntry(event="invalidate", added=["a.py"], modified=["b.py"])
    assert t2.added == ["a.py"]


def test_agent_trace_entry():
    e = agent_trace_entry("surveyor", evidence_source="static analysis", confidence=1.0, payload={"modules": 5})
    assert e.event == "agent_surveyor"
    assert e.evidence is not None
    assert e.evidence.source == "static analysis"
    assert e.evidence.confidence == 1.0
    assert e.payload == {"modules": 5}


def test_codebase_context_and_onboarding_brief():
    c = CODEBASEContext(architecture_overview="Overview", data_sources=["s1"], data_sinks=["s2"])
    assert c.data_sources == ["s1"]
    o = OnboardingBrief(day_one_answers_markdown="# Answers", confidence_notes="Conservative.")
    d = o.model_dump(mode="json")
    assert "Answers" in d["day_one_answers_markdown"]


def test_cartography_artifacts():
    a = CartographyArtifacts(artifact_dir="/path/.cartography", module_graph=ModuleGraph(), lineage_graph=DataLineageGraph())
    js = a.model_dump_json()
    a2 = CartographyArtifacts.model_validate_json(js)
    assert a2.artifact_dir == "/path/.cartography"
    assert a2.module_graph is not None
