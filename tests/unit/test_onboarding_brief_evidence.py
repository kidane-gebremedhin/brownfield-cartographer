from pathlib import Path

import networkx as nx

from agents.archivist import ArchivistInputs, render_onboarding_brief
from agents.hydrologist import HydrologistResult
from agents.semanticist import SemanticistResult
from models.artifacts import DayOneAnswer
from models.common import Evidence


class _DummySurveyorResult:
    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.modules = {}
        self.pagerank = {}
        self.sccs = []


def test_onboarding_brief_includes_evidence_file_paths_and_ranges(tmp_path: Path) -> None:
    """onboarding_brief.md should include explicit file paths and line ranges when evidence exists."""
    # Fake lineage graph (not used directly in this test but required by ArchivistInputs)
    g = nx.DiGraph()
    hydro = HydrologistResult(graph=g)
    surveyor = _DummySurveyorResult()

    # SemanticistResult with a structured Day-One answer and evidence
    critical_file = "src/example.py"
    ev = Evidence(
        source="hydrologist",
        file_path=critical_file,
        line_start=10,
        line_end=20,
        analysis_method="graph_traversal",
        notes="Example edge evidence",
    )
    ans = DayOneAnswer(
        question_id=3,
        title="Blast radius of critical module",
        answer_markdown="Downstream blast radius is non-trivial.",
        confidence=0.9,
        method="graph_traversal",
        evidence=[ev],
    )
    sem = SemanticistResult()
    sem.day_one_answers = [ans]

    inputs = ArchivistInputs(
        repo_root=tmp_path,
        surveyor_result=surveyor,
        hydrologist_result=hydro,
        day_one_answers_markdown=None,
        semanticist_result=sem,
        trace_events=[],
    )

    md = render_onboarding_brief(inputs)

    # The onboarding brief should contain the exact file path and line range citation.
    assert critical_file in md
    assert "10-20" in md

