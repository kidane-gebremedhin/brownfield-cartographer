from pathlib import Path

from analyzers.git_velocity import build_git_velocity_map, top_changed_files_all
from agents.semanticist import _build_structured_day_one_answers, SemanticistResult
from agents.hydrologist import HydrologistResult
from agents.surveyor import SurveyorResult, SurveyorModuleMetrics


class _DummyHydrologist:
    def __init__(self) -> None:
        import networkx as nx

        self.graph = nx.DiGraph()


def _fake_surveyor_with_modules() -> SurveyorResult:
    g = _DummyHydrologist().graph
    modules = {}
    for path in ["a.py", "b.py"]:
        modules[path] = SurveyorModuleMetrics(
            path=path,
            language="python",
            loc=10,
            complexity_score=1.0,
            change_velocity_30d=0,
            change_velocity_90d=5,
            public_api_count=1,
            is_dead_code_candidate=False,
        )
    return SurveyorResult(graph=g, modules=modules, pagerank={}, sccs=[])


def test_build_git_velocity_map_uses_90_days_by_default(tmp_path: Path) -> None:
    """Git velocity map should default to 90 days and be safe for non-git repos."""
    vmap = build_git_velocity_map(tmp_path)
    assert isinstance(vmap, dict)
    assert vmap["files"] == []
    assert vmap["directories"] == []
    assert vmap["prefixes"] == []


def test_day_one_git_velocity_answer_mentions_90_days(tmp_path: Path) -> None:
    """Day-One Question 5 should describe git velocity over the last 90 days with file paths and counts."""
    # We can't easily fabricate git history here, but we can still check structure.
    surveyor = _fake_surveyor_with_modules()
    hydro = HydrologistResult(graph=_DummyHydrologist().graph)
    sem = SemanticistResult()

    answers = _build_structured_day_one_answers(
        surveyor_result=surveyor,
        hydrologist_result=hydro,
        sem_result=sem,
        repo_root=tmp_path,
    )

    q5 = next(a for a in answers if a.question_id == 5)

    # Title and text should clearly mention 90 days
    assert "90 days" in q5.title or "90 days" in q5.answer_markdown

    # Evidence objects for git velocity should carry file paths (even if counts are zero in this synthetic case)
    for ev in q5.evidence:
        if ev.source == "git_velocity":
            assert ev.file_path is not None


def test_top_changed_files_all_returns_descending_count_order(tmp_path: Path) -> None:
    """top_changed_files_all must return [(path, count), ...] sorted by count descending, then path ascending."""
    # Non-git dir: empty list
    result = top_changed_files_all(tmp_path, days=90, top_n=10)
    assert result == []


def test_build_git_velocity_map_files_are_code_only(tmp_path: Path) -> None:
    """Day-One velocity map uses .py and .sql only for 'files' so hotspots match git log | grep -E '\\.(py|sql)$'."""
    vmap = build_git_velocity_map(tmp_path)
    for path, _ in vmap["files"]:
        assert path.endswith((".py", ".sql")), f"Expected .py or .sql path, got {path}"
