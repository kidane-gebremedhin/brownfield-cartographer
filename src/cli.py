"""Command-line interface for brownfield-cartographer.

Commands:
- cartographer analyze <repo_or_path> [--output-dir ...] [--branch ...] [--dialect ...]
- cartographer query <artifact_dir>
- cartographer visualize <artifact_dir> [--open-browser]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from analyzers.sql_lineage import SqlDialect
from orchestrator import AnalyzeOptions, run_analyze, run_query, run_visualize


def _add_analyze(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "analyze",
        help="Run full analysis pipeline for a repository (ingestion, surveyor, hydrologist, archivist).",
    )
    p.add_argument("repo_or_path", help="Local path or GitHub URL to analyze.")
    p.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Directory for artifacts (default: .cartography under the repo root).",
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cartographer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_analyze(subparsers)
    _add_query(subparsers)
    _add_visualize(subparsers)
    return parser


def _cmd_analyze(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    opts = AnalyzeOptions(
        input_path_or_url=args.repo_or_path,
        output_dir=output_dir,
        branch=args.branch,
        dialect=args.dialect,
    )
    res = run_analyze(opts)
    print(f"Repository root: {res.repo_root}")
    print(f"Artifacts written to: {res.artifact_dir}")
    if getattr(res, "reused", False):
        print("Artifacts reused (no file changes).")
    print(f"Modules analyzed: {res.modules_analyzed}")
    print(f"Lineage graph: {res.lineage_nodes} nodes, {res.lineage_edges} edges")
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

