# Response formatter tests
from query.response_formatter import format_implementation_matches, format_lineage_result, format_blast_radius_result, format_module_explanation
from query.tools import ImplementationMatch, LineageResult, BlastRadiusResult, ModuleExplanation

def test_format_implementation_matches_empty():
    out = format_implementation_matches([])
    assert "No implementations" in out

def test_format_implementation_matches_graph_and_semantic():
    matches = [ImplementationMatch("src/foo.py", source="graph", confidence=0.9, method_provenance="module graph"), ImplementationMatch("src/bar.py", source="semantic", confidence=0.7, method_provenance="CODEBASE.md")]
    out = format_implementation_matches(matches)
    assert "Graph-backed" in out
    assert "Semantic" in out
    assert "src/foo.py" in out

def test_format_lineage_result():
    result = LineageResult(start="analytics.events", direction="upstream", nodes=["raw.events", "analytics.events"], edges=[], evidence="Lineage graph traversal.")
    out = format_lineage_result(result)
    assert "Evidence" in out or "static analysis" in out
    assert "analytics.events" in out

def test_format_blast_radius_result():
    result = BlastRadiusResult(start="raw.events", affected=["analytics.events"], evidence="Downstream traversal. 1 nodes affected.")
    out = format_blast_radius_result(result)
    assert "Evidence" in out or "static analysis" in out
    assert "Affected" in out

def test_format_module_explanation():
    expl = ModuleExplanation(path="src/etl/load.py", graph_section="Module: src/etl/load.py", semantic_section="Purpose: Load data.", confidence=0.9)
    out = format_module_explanation(explanation=expl)
    assert "Graph-backed" in out
    assert "Semantic" in out
