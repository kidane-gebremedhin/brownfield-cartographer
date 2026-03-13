# Tests for prompt assembly
from llm.prompts import render_purpose_statement, render_drift_classification, render_cluster_label, render_day_one

def test_render_purpose_statement():
    out = render_purpose_statement(module_path="src/foo.py", loc=50, imports="os", functions="main", classes="Bar", bases="Base", source_preview="def main(): pass")
    assert "src/foo.py" in out
    assert "Purpose" in out and "one sentence" in out

def test_render_drift_classification():
    out = render_drift_classification(purpose="Handles auth.", docstring="Auth utilities.")
    assert "Handles auth." in out
    assert "aligned" in out

def test_render_drift_none():
    out = render_drift_classification(purpose="x", docstring="")
    assert "(none)" in out

def test_render_cluster_label():
    out = render_cluster_label("a: load\nb: save")
    assert "Domain label:" in out

def test_render_day_one():
    out = render_day_one("Sources: x. Sinks: z.")
    assert "1. Primary ingestion path" in out
    assert "5. Git velocity hotspots" in out
