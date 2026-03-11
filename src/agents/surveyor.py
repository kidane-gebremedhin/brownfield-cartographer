"""Surveyor agent.

Builds the structural analysis layer:
- parses Python modules using tree-sitter
- computes LOC + lightweight complexity
- computes git velocity 30/90
- builds a directed import graph
- runs PageRank and SCC detection
- flags conservative dead-code candidates

Design is extensible for SQL/YAML/JS/TS later via language_router.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from analyzers.language_router import get_language
from analyzers.tree_sitter_analyzer import analyze_python_source
from analyzers.git_velocity import change_velocity_30_90
from repository.file_discovery import discover_files, DiscoveredFile
from models.nodes import ModuleNode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SurveyorModuleMetrics:
    path: str
    language: str
    loc: int
    complexity_score: float
    change_velocity_30d: int
    change_velocity_90d: int
    public_api_count: int
    is_dead_code_candidate: bool


@dataclass(frozen=True)
class SurveyorResult:
    graph: nx.DiGraph
    modules: dict[str, SurveyorModuleMetrics]
    pagerank: dict[str, float]
    sccs: list[set[str]]


def run_surveyor(repo_root: Path | str) -> SurveyorResult:
    root = Path(repo_root).resolve()
    files = discover_files(root)

    # Build module set (only python for structural parse right now)
    python_files = [f for f in files if f.extension == '.py']
    module_paths = {f.path for f in python_files}

    g = nx.DiGraph()
    modules: dict[str, SurveyorModuleMetrics] = {}

    # Parse modules
    facts_by_path = {}
    for f in python_files:
        try:
            facts = analyze_python_source(f.content, path=f.path)
        except Exception as e:
            logger.warning('Skipping unparseable file %s: %s', f.path, e)
            continue
        if not facts.parse_ok:
            logger.warning('Skipping unparseable file %s: %s', f.path, facts.error)
            continue
        facts_by_path[f.path] = facts

        v30, v90 = change_velocity_30_90(root, f.path)
        public_api = [fn for fn in facts.functions if fn.is_public] + [c for c in facts.classes if not c.name.startswith('_')]
        modules[f.path] = SurveyorModuleMetrics(
            path=f.path,
            language='python',
            loc=facts.loc,
            complexity_score=facts.complexity_score,
            change_velocity_30d=v30,
            change_velocity_90d=v90,
            public_api_count=len(public_api),
            is_dead_code_candidate=False,
        )
        g.add_node(f.path)

    # Add edges (best-effort import resolution)
    for path, facts in facts_by_path.items():
        for imp in facts.imports:
            target = _resolve_import_to_path(imp.module, module_paths)
            if target:
                g.add_edge(path, target)

    # Graph algorithms
    pr: dict[str, float] = {}
    sccs: list[set[str]] = []
    if g.number_of_nodes() > 0:
        pr = nx.pagerank(g)
        sccs = [set(c) for c in nx.strongly_connected_components(g) if len(c) > 1]

    # Conservative dead code: public API module with no incoming edges (excluding common entry points)
    for p, m in list(modules.items()):
        if m.public_api_count <= 0:
            continue
        if g.in_degree(p) != 0:
            continue
        if p.endswith('main.py') or p.endswith('cli.py') or p.endswith('__init__.py'):
            continue
        modules[p] = SurveyorModuleMetrics(
            **{**m.__dict__, 'is_dead_code_candidate': True}  # type: ignore[arg-type]
        )

    return SurveyorResult(graph=g, modules=modules, pagerank=pr, sccs=sccs)


def _resolve_import_to_path(module: str, module_paths: set[str]) -> str | None:
    """Resolve a dotted import module name to a repo-relative .py path if possible."""
    if not module:
        return None
    candidates = [
        module.replace('.', '/') + '.py',
        module.replace('.', '/') + '/__init__.py',
    ]
    for c in candidates:
        if c in module_paths:
            return c
    return None


def high_velocity_core(
    surveyor_result: SurveyorResult,
    *,
    top_fraction: float = 0.2,
    contribution_target: float = 0.8,
    use_30d: bool = True,
) -> list[str]:
    """Return the minimal set of module paths that account for ~contribution_target of total changes (80/20 core).

    Sorts modules by change velocity descending, then takes the smallest set of paths
    whose cumulative change count >= contribution_target * total. Typically this is
    the "20% of files responsible for 80% of changes".
    """
    modules = list(surveyor_result.modules.values())
    if not modules:
        return []
    total = sum(m.change_velocity_30d if use_30d else m.change_velocity_90d for m in modules)
    if total <= 0:
        return []
    key = (lambda m: m.change_velocity_30d) if use_30d else (lambda m: m.change_velocity_90d)
    sorted_modules = sorted(modules, key=key, reverse=True)
    cum = 0
    out: list[str] = []
    threshold = contribution_target * total
    for m in sorted_modules:
        out.append(m.path)
        cum += key(m)
        if cum >= threshold:
            break
    return out


def analyze_module(repo_root: Path | str, path: str) -> ModuleNode:
    """Analyze a single module at path and return a ModuleNode (curriculum: structural + velocity).

    Supports Python only for now (tree-sitter); other extensions get a minimal ModuleNode
    with language from LanguageRouter and no structural extraction.
    """
    root = Path(repo_root).resolve()
    full = root / path
    if not full.is_file():
        return ModuleNode(path=path, language=get_language(path), loc=0)

    content = full.read_bytes()
    lang = get_language(path)

    if lang != "python":
        v30, v90 = change_velocity_30_90(root, path)
        return ModuleNode(
            path=path,
            language=lang,
            loc=0,
            change_velocity_30d=v30,
            change_velocity_90d=v90,
        )

    facts = analyze_python_source(content, path=path)
    v30, v90 = change_velocity_30_90(root, path)
    public_api = [fn for fn in facts.functions if fn.is_public] + [
        c for c in facts.classes if not c.name.startswith("_")
    ]
    return ModuleNode(
        path=path,
        language=lang,
        complexity_score=facts.complexity_score,
        change_velocity_30d=v30,
        change_velocity_90d=v90,
        is_dead_code_candidate=False,
        loc=facts.loc,
        public_api_count=len(public_api),
    )
