from pathlib import Path

import networkx as nx

from agents.semanticist import (
    SemanticistResult,
    analyze_business_logic_distribution,
    _build_structured_day_one_answers,
)
from agents.hydrologist import HydrologistResult
from agents.surveyor import SurveyorResult, SurveyorModuleMetrics


def _fake_surveyor_for_distribution() -> SurveyorResult:
    """Build a synthetic repo layout with centralized SQL models and distributed orchestration."""
    g = nx.DiGraph()

    modules = {}
    paths = [
        "src/ol_dbt/models/staging/user_staging.sql",
        "src/ol_dbt/models/staging/order_staging.sql",
        "src/ol_dbt/models/marts/user_mart.sql",
        "src/ol_dbt/models/marts/order_mart.sql",
        "dg_deployments/dagster_repo.py",
        "dg_projects/project_a/jobs/job_a.py",
        "dg_projects/project_b/jobs/job_b.py",
        "packages/utils/helpers.py",
    ]
    # Centralize PageRank on the dbt models, distribute some across orchestrations
    pagerank = {
        paths[0]: 0.15,
        paths[1]: 0.15,
        paths[2]: 0.2,
        paths[3]: 0.2,
        paths[4]: 0.1,
        paths[5]: 0.1,
        paths[6]: 0.08,
        paths[7]: 0.02,
    }
    for p in paths:
        modules[p] = SurveyorModuleMetrics(
            path=p,
            language="sql" if p.endswith(".sql") else "python",
            loc=50,
            complexity_score=1.0,
            change_velocity_30d=0,
            change_velocity_90d=0,
            public_api_count=1,
            is_dead_code_candidate=False,
        )

    return SurveyorResult(graph=g, modules=modules, pagerank=pagerank, sccs=[])


def _fake_hydrologist_for_distribution() -> HydrologistResult:
    g = nx.DiGraph()
    # Model some lineage edges with source_file paths under dbt models and dg_projects
    g.add_edge(
        "raw_users",
        "staging_users",
        source_file="src/ol_dbt/models/staging/user_staging.sql",
        line_start=10,
        line_end=40,
    )
    g.add_edge(
        "raw_orders",
        "staging_orders",
        source_file="src/ol_dbt/models/staging/order_staging.sql",
        line_start=15,
        line_end=45,
    )
    g.add_edge(
        "staging_users",
        "user_mart",
        source_file="src/ol_dbt/models/marts/user_mart.sql",
        line_start=5,
        line_end=30,
    )
    g.add_edge(
        "staging_orders",
        "order_mart",
        source_file="src/ol_dbt/models/marts/order_mart.sql",
        line_start=5,
        line_end=30,
    )
    g.add_edge(
        "user_mart",
        "reporting_dashboard",
        source_file="dg_projects/project_a/jobs/job_a.py",
        line_start=20,
        line_end=60,
    )
    g.add_edge(
        "order_mart",
        "reporting_dashboard",
        source_file="dg_projects/project_b/jobs/job_b.py",
        line_start=25,
        line_end=65,
    )
    return HydrologistResult(graph=g)


def test_analyze_business_logic_distribution_identifies_central_layers() -> None:
    surveyor = _fake_surveyor_for_distribution()
    hydro = _fake_hydrologist_for_distribution()

    dist = analyze_business_logic_distribution(surveyor, hydro)

    # We should see directories for dbt models and dg_projects
    dirs_by_modules = dict(dist["dir_module_counts"])
    assert any(d.startswith("src/ol_dbt/models") for d in dirs_by_modules)
    assert any(d.startswith("dg_projects") for d in dirs_by_modules)

    # Layer stats should include marts and staging
    layer_counts = dist["layer_counts"]
    assert "staging" in layer_counts
    assert "marts" in layer_counts

    # Concentration notes should call out centralization somewhere
    notes = " ".join(dist["concentration_notes"])
    assert "centralized" in notes or "distributed" in notes


def test_day_one_question_4_reads_like_architecture_assessment(tmp_path: Path) -> None:
    surveyor = _fake_surveyor_for_distribution()
    hydro = _fake_hydrologist_for_distribution()
    sem = SemanticistResult()

    answers = _build_structured_day_one_answers(
        surveyor_result=surveyor,
        hydrologist_result=hydro,
        sem_result=sem,
        repo_root=tmp_path,
    )

    q4 = next(a for a in answers if a.question_id == 4)

    # Answer should not be a single-line generic summary; it should mention where logic lives.
    assert "Top directories by module count" in q4.answer_markdown
    assert "Path-based layers" in q4.answer_markdown
    assert "centralized" in q4.answer_markdown or "distributed" in q4.answer_markdown

