"""Orchestrator: end-to-end execution for analyze/query/visualize.

High-level responsibilities:
- Wire repository loader, Surveyor, Hydrologist, Archivist, and visualization.
- Provide structured, user-friendly summaries for the CLI.
- Operate from persisted artifacts for query/visualize (no re-analysis required).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Literal

import networkx as nx

from agents.archivist import ArchivistInputs, write_artifacts
from agents.hydrologist import HydrologistResult, build_lineage_graph
from agents.surveyor import SurveyorResult, run_surveyor
from analyzers.sql_lineage import SqlDialect
from graph.visualization import build_lineage_graph_html, build_module_graph_html
from incremental import (
    append_trace_event,
    compute_changes,
    get_current_hashes,
    load_manifest,
    save_manifest,
    trace_event_for_invalidate,
    trace_event_for_reuse,
)
from repository.loader import LoadedRepository, load_repository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalyzeOptions:
    input_path_or_url: str
    output_dir: Path | None = None
    branch: str | None = None
    dialect: SqlDialect = "postgres"


@dataclass(frozen=True)
class AnalyzeResult:
    repo_root: Path
    artifact_dir: Path
    modules_analyzed: int
    lineage_nodes: int
    lineage_edges: int
    reused: bool = False  # True when incremental reuse (no re-analysis)


@dataclass(frozen=True)
class QueryResult:
    artifact_dir: Path
    modules: int
    lineage_nodes: int
    lineage_edges: int


@dataclass(frozen=True)
class VisualizeResult:
    artifact_dir: Path
    module_html: Path
    lineage_html: Path
    regenerated: bool


def run_analyze(opts: AnalyzeOptions) -> AnalyzeResult:
    """Run analysis pipeline; reuse artifacts when no file changes (incremental)."""
    repo: LoadedRepository | None = None
    try:
        repo = load_repository(opts.input_path_or_url, ref=opts.branch)
        repo_root = repo.root
        logger.info("Loaded repository at %s (temporary=%s)", repo_root, repo.is_temporary)

        out_dir = Path(opts.output_dir) if opts.output_dir is not None else repo_root / ".cartography"
        artifact_dir = out_dir.resolve()
        current_hashes = get_current_hashes(repo_root)
        prior_hashes = load_manifest(artifact_dir)
        changes = compute_changes(prior_hashes, current_hashes)

        if changes.unchanged and (artifact_dir / "module_graph.json").exists() and (artifact_dir / "lineage_graph.json").exists():
            logger.info("Incremental reuse: %s", changes.reason)
            append_trace_event(artifact_dir, trace_event_for_reuse(changes, len(current_hashes)))
            module_payload = json.loads((artifact_dir / "module_graph.json").read_text(encoding="utf-8"))
            lineage_payload = json.loads((artifact_dir / "lineage_graph.json").read_text(encoding="utf-8"))
            return AnalyzeResult(
                repo_root=repo_root,
                artifact_dir=artifact_dir,
                modules_analyzed=len(module_payload.get("nodes", [])),
                lineage_nodes=len(lineage_payload.get("nodes", [])),
                lineage_edges=len(lineage_payload.get("edges", [])),
                reused=True,
            )

        if not changes.unchanged:
            logger.info("Invalidating: %s (added=%s, removed=%s, modified=%s)", changes.reason, len(changes.added), len(changes.removed), len(changes.modified))

        surveyor_result: SurveyorResult = run_surveyor(repo_root)
        hydro_result: HydrologistResult = build_lineage_graph(repo_root, dialect=opts.dialect)

        artifact_dir = write_artifacts(
            ArchivistInputs(
                repo_root=repo_root,
                surveyor_result=surveyor_result,
                hydrologist_result=hydro_result,
                trace_events=[trace_event_for_invalidate(changes, len(current_hashes))],
            ),
            out_dir=artifact_dir,
        )
        save_manifest(artifact_dir, current_hashes)

        return AnalyzeResult(
            repo_root=repo_root,
            artifact_dir=artifact_dir,
            modules_analyzed=len(surveyor_result.modules),
            lineage_nodes=hydro_result.graph.number_of_nodes(),
            lineage_edges=hydro_result.graph.number_of_edges(),
            reused=False,
        )
    finally:
        # Best-effort cleanup of temporary clone if applicable.
        if repo is not None and repo.is_temporary and getattr(repo, "_tmpdir", None) is not None:
            try:
                repo._tmpdir.cleanup()  # type: ignore[union-attr]
            except Exception as e:  # pragma: no cover - cleanup failures are non-fatal
                logger.debug("Temporary repo cleanup failed: %s", e)


def run_query(artifact_dir: Path | str) -> QueryResult:
    """Summarize existing artifacts without rerunning analysis."""
    artifact_dir = Path(artifact_dir).resolve()
    module_graph_path = artifact_dir / "module_graph.json"
    lineage_graph_path = artifact_dir / "lineage_graph.json"

    if not module_graph_path.exists() or not lineage_graph_path.exists():
        raise FileNotFoundError(
            f"Expected module_graph.json and lineage_graph.json in {artifact_dir}; "
            "run 'cartographer analyze' first."
        )

    module_payload = json.loads(module_graph_path.read_text(encoding="utf-8"))
    lineage_payload = json.loads(lineage_graph_path.read_text(encoding="utf-8"))

    modules = len(module_payload.get("nodes", []))
    lineage_nodes = len(lineage_payload.get("nodes", []))
    lineage_edges = len(lineage_payload.get("edges", []))

    return QueryResult(
        artifact_dir=artifact_dir,
        modules=modules,
        lineage_nodes=lineage_nodes,
        lineage_edges=lineage_edges,
    )


def run_visualize(
    artifact_dir: Path | str,
    *,
    open_browser: bool = False,
) -> VisualizeResult:
    """
    Ensure Pyvis HTML outputs exist for module and lineage graphs.

    Operates purely from persisted JSON artifacts; does not rerun analyzers.
    """
    artifact_dir = Path(artifact_dir).resolve()
    module_json = artifact_dir / "module_graph.json"
    lineage_json = artifact_dir / "lineage_graph.json"

    if not module_json.exists() or not lineage_json.exists():
        raise FileNotFoundError(
            f"Expected module_graph.json and lineage_graph.json in {artifact_dir}; "
            "run 'cartographer analyze' first."
        )

    module_html = artifact_dir / "module_graph.html"
    lineage_html = artifact_dir / "lineage_graph.html"

    regenerated = False
    if not module_html.exists() or not lineage_html.exists():
        regenerated = True

        module_payload = json.loads(module_json.read_text(encoding="utf-8"))
        lineage_payload = json.loads(lineage_json.read_text(encoding="utf-8"))

        module_graph = _graph_from_payload(module_payload)
        lineage_graph = _graph_from_payload(lineage_payload)

        # We no longer have Surveyor module metrics or PageRank at this layer,
        # so we pass empty mappings. Visualization logic degrades gracefully.
        build_module_graph_html(module_graph, {}, {}, module_html, open_browser=open_browser)
        build_lineage_graph_html(lineage_graph, lineage_html, open_browser=open_browser)

    return VisualizeResult(
        artifact_dir=artifact_dir,
        module_html=module_html,
        lineage_html=lineage_html,
        regenerated=regenerated,
    )


def _graph_from_payload(payload: dict[str, Any]) -> nx.DiGraph:
    """Rebuild a NetworkX DiGraph from archivist JSON."""
    g = nx.DiGraph()
    for n in payload.get("nodes", []):
        attrs = n.get("attrs") or {}
        g.add_node(n["id"], **attrs)
    for e in payload.get("edges", []):
        attrs = e.get("attrs") or {}
        g.add_edge(e["source"], e["target"], **attrs)
    return g

