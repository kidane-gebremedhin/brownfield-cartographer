"""Command-line interface for brownfield-cartographer.

Commands:
- cartographer analyze <repo_or_path> [--output-dir ...] [--branch ...] [--dialect ...]
- cartographer surveyor <repo_or_path> [--output-dir ...] [--branch ...]
- cartographer query <artifact_dir>
- cartographer visualize <artifact_dir> [--open-browser]
- cartographer lineage-upstream <artifact_dir> <dataset> [--max-depth N]
- cartographer blast-radius <artifact_dir> <module_or_dataset> [--max-depth N]
- cartographer ask "<question>" [artifact_dir] [--about TARGET] [--max-depth N]

Semanticist (purpose statements, drift, domains, day-one answers) runs when DEEPSEEK_API_KEY
is set in .env. All LLM calls use the DeepSeek API.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from analyzers.sql_lineage import SqlDialect
from orchestrator import (
    AnalyzeOptions,
    run_analyze,
    run_query,
    run_surveyor_only,
    run_visualize,
    SurveyorOnlyOptions,
)


def _load_env() -> None:
    """Load .env from cwd and repo root so API keys are available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        # Also load from project root if different
        load_dotenv(Path.cwd() / ".env")
    except ImportError:
        pass


def _create_semanticist_providers():
    """Create LLM and embeddings providers from env for semanticist. Returns (llm_provider, embeddings_provider) or (None, None)."""
    _load_env()
    from llm.tiered_provider import create_tiered_provider_from_env
    from llm.embeddings import create_embeddings_from_env
    llm = create_tiered_provider_from_env()
    if llm is None:
        return None, None
    embeddings = create_embeddings_from_env()
    return llm, embeddings


def _add_analyze(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "analyze",
        help="Run full analysis pipeline for a repository (ingestion, surveyor, hydrologist, archivist).",
    )
    p.add_argument("repo_or_path", help="Local path or GitHub URL to analyze.")
    p.add_argument(
        "--output-dir",
        dest="output_dir",
        default="./cartography",
        help="Directory for artifacts (default: ./cartography).",
    )
    p.add_argument(
        "--branch",
        dest="branch",
        default=None,
        help="Git branch or ref to check out (GitHub URLs only).",
    )
    p.add_argument(
        "--dialect",
        dest="dialect",
        default="postgres",
        choices=list(SqlDialect.__args__),  # type: ignore[attr-defined]
        help="SQL dialect for lineage extraction (default: postgres).",
    )
    p.set_defaults(func=_cmd_analyze)


def _add_surveyor(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "surveyor",
        help="Run only the Surveyor agent (static analysis, module graph, PageRank, SCCs).",
    )
    p.add_argument("repo_or_path", help="Local path or GitHub URL to analyze.")
    p.add_argument(
        "--output-dir",
        dest="output_dir",
        default="./cartography",
        help="Directory for artifacts (default: ./cartography).",
    )
    p.add_argument(
        "--branch",
        dest="branch",
        default=None,
        help="Git branch or ref to check out (GitHub URLs only).",
    )
    p.set_defaults(func=_cmd_surveyor)


def _add_query(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "query",
        help="Summarize an existing artifact directory without rerunning analysis.",
    )
    p.add_argument("artifact_dir", help="Directory containing module_graph.json and lineage_graph.json.")
    p.set_defaults(func=_cmd_query)


def _add_visualize(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "visualize",
        help="Ensure Pyvis HTML visualizations exist for a given artifact directory.",
    )
    p.add_argument("artifact_dir", help="Directory containing serialized graph artifacts.")
    p.add_argument(
        "--open-browser",
        dest="open_browser",
        action="store_true",
        help="Open generated HTML files in the default browser.",
    )
    p.set_defaults(func=_cmd_visualize)


def _add_lineage_upstream(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "lineage-upstream",
        help="Answer: What upstream sources feed this output dataset? (DataLineageGraph traversal with file:line citations).",
    )
    p.add_argument("artifact_dir", help="Directory containing lineage_graph.json.")
    p.add_argument("dataset", help="Output dataset node ID to trace upstream from.")
    p.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=10,
        help="Max traversal depth (default: 10).",
    )
    p.set_defaults(func=_cmd_lineage_upstream)


def _add_blast_radius(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "blast-radius",
        help="Show everything that would break if this module/dataset changed (downstream dependency graph).",
    )
    p.add_argument("artifact_dir", help="Directory containing lineage_graph.json.")
    p.add_argument(
        "module_or_dataset",
        help="Lineage graph node ID (module/dataset) to compute blast radius from.",
    )
    p.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=5,
        help="Max traversal depth (default: 5).",
    )
    p.set_defaults(func=_cmd_blast_radius)


def _add_ask(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "ask",
        help="Type a question in natural language; routes to lineage-upstream or blast-radius.",
    )
    p.add_argument(
        "question",
        help='Natural language question, e.g. "What upstream sources feed this output dataset?" or "What would break if this module changed?"',
    )
    p.add_argument(
        "artifact_dir",
        nargs="?",
        default="./cartography",
        help="Directory containing lineage_graph.json (default: ./cartography).",
    )
    p.add_argument(
        "--about",
        dest="about",
        default=None,
        help="Dataset/module node ID the question is about (required if not extractable from the question).",
    )
    p.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=10,
        help="Max traversal depth (default: 10).",
    )
    p.set_defaults(func=_cmd_ask)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cartographer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_analyze(subparsers)
    _add_surveyor(subparsers)
    _add_query(subparsers)
    _add_visualize(subparsers)
    _add_lineage_upstream(subparsers)
    _add_blast_radius(subparsers)
    _add_ask(subparsers)
    return parser


def _cmd_analyze(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    llm_provider, embeddings_provider = _create_semanticist_providers()
    opts = AnalyzeOptions(
        input_path_or_url=args.repo_or_path,
        output_dir=output_dir,
        branch=args.branch,
        dialect=args.dialect,
        llm_provider=llm_provider,
        embeddings_provider=embeddings_provider,
    )
    res = run_analyze(opts)
    print(f"Repository root: {res.repo_root}")
    print(f"Artifacts written to: {res.artifact_dir}")
    if getattr(res, "reused", False):
        print("Artifacts reused (no file changes).")
    print(f"Modules analyzed: {res.modules_analyzed}")
    print(f"Lineage graph: {res.lineage_nodes} nodes, {res.lineage_edges} edges")
    if llm_provider is not None:
        print("Semanticist: purpose statements, drift, domains, and day-one answers included.")
    return 0


def _cmd_surveyor(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    opts = SurveyorOnlyOptions(
        input_path_or_url=args.repo_or_path,
        output_dir=output_dir,
        branch=args.branch,
    )
    res = run_surveyor_only(opts)
    print(f"Repository root: {res.repo_root}")
    print(f"Artifacts written to: {res.artifact_dir}")
    print(f"Modules analyzed: {res.modules_analyzed}")
    print(f"Module graph: {res.graph_nodes} nodes, {res.graph_edges} edges")
    print("Files: module_graph.json, surveyor_metrics.json")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    res = run_query(args.artifact_dir)
    print(f"Artifact dir: {res.artifact_dir}")
    print(f"Modules: {res.modules}")
    print(f"Lineage graph: {res.lineage_nodes} nodes, {res.lineage_edges} edges")
    return 0


def _cmd_visualize(args: argparse.Namespace) -> int:
    res = run_visualize(args.artifact_dir, open_browser=args.open_browser)
    print(f"Artifact dir: {res.artifact_dir}")
    print(f"Module graph HTML: {res.module_html}")
    print(f"Lineage graph HTML: {res.lineage_html}")
    if res.regenerated:
        print("Graphs were regenerated from persisted JSON.")
    else:
        print("Existing HTML graphs reused.")
    return 0


def _cmd_lineage_upstream(args: argparse.Namespace) -> int:
    from query.tools import upstream_sources_for_dataset
    from query.response_formatter import format_upstream_sources_answer
    result = upstream_sources_for_dataset(
        args.artifact_dir,
        args.dataset,
        max_depth=getattr(args, "max_depth", 10),
    )
    print(format_upstream_sources_answer(result))
    return 0


def _cmd_blast_radius(args: argparse.Namespace) -> int:
    from query.tools import blast_radius as tool_blast_radius
    from query.response_formatter import format_blast_radius_result
    result = tool_blast_radius(
        args.artifact_dir,
        args.module_or_dataset,
        max_depth=getattr(args, "max_depth", 5),
    )
    print(format_blast_radius_result(result))
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    from query.tools import ask_question, classify_lineage_question

    question = args.question
    artifact_dir = args.artifact_dir
    # If user passed (path, question) e.g. ask ./cartography "What...", fix the order
    if classify_lineage_question(question) is None and classify_lineage_question(artifact_dir) is not None:
        question, artifact_dir = artifact_dir, question

    answer, exit_code = ask_question(
        artifact_dir,
        question,
        about=getattr(args, "about", None),
        max_depth=getattr(args, "max_depth", 10),
    )
    print(answer)
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        func = getattr(args, "func", None)
    except AttributeError:  # pragma: no cover - argparse always sets this in our usage
        parser.print_help()
        return 1

    try:
        return func(args)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # pragma: no cover - generic safeguard
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

