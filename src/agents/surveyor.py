"""Surveyor agent.

Builds the structural analysis layer:
- parses Python modules using tree-sitter
- computes LOC + lightweight complexity
- computes git velocity 30/90
- builds a directed import graph
- runs PageRank and SCC detection
- flags conservative dead-code candidates

Python modules get full structural parsing; SQL/YAML/JSON/markdown/notebooks are
indexed as first-class modules with language, LOC, and git velocity so that
polyglot data engineering codebases (Python + SQL + YAML + notebooks) appear in
the module graph, even when we do not yet extract fine-grained imports for
those languages.
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

    # Build module set:
    # - Python files get full structural parse and import edges.
    # - Other discovered files (SQL/YAML/JSON/markdown/notebooks) become
    #   first-class modules with language + LOC + git velocity.
    # all_module_paths: every discovered file (for cross-language path resolution).
    # python_paths: only .py (for import resolution).
    python_files = [f for f in files if f.extension == ".py"]
    python_paths = {f.path for f in python_files}
    all_module_paths = {f.path for f in files}

    g = nx.DiGraph()
    modules: dict[str, SurveyorModuleMetrics] = {}

    # Parse Python modules
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

    # Index non-Python files as modules so that polyglot repos (SQL/YAML/etc.)
    # appear in the module graph and metrics, even if we do not yet extract
    # fine-grained imports for them.
    python_paths = {f.path for f in python_files}
    for f in files:
        if f.path in python_paths:
            continue
        lang = get_language(f.path)
        # Approximate LOC from bytes content.
        loc = f.content.count(b"\n")
        if f.content and not f.content.endswith(b"\n"):
            loc += 1
        v30, v90 = change_velocity_30_90(root, f.path)
        modules[f.path] = SurveyorModuleMetrics(
            path=f.path,
            language=lang,
            loc=loc,
            complexity_score=0.0,
            change_velocity_30d=v30,
            change_velocity_90d=v90,
            public_api_count=0,
            is_dead_code_candidate=False,
        )
        g.add_node(f.path)

    # Add edges: Python import resolution (Python -> Python)
    for path, facts in facts_by_path.items():
        for imp in facts.imports:
            target = _resolve_import_to_path(imp.module, python_paths)
            if target:
                g.add_edge(path, target, edge_type="import")

    # Add edges: path-like string references (Python -> any discovered file)
    for path, facts in facts_by_path.items():
        for ref in _path_like_strings(facts.string_literals):
            target = _resolve_path_reference(ref, path, all_module_paths)
            if target and target != path and not g.has_edge(path, target):
                g.add_edge(path, target, edge_type="path_reference")

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
        module.replace(".", "/") + ".py",
        module.replace(".", "/") + "/__init__.py",
    ]
    for c in candidates:
        if c in module_paths:
            return c
    return None


# Extensions we treat as path-like when seen in string literals (cross-language refs).
_PATH_EXTENSIONS = (".py", ".sql", ".yaml", ".yml", ".json", ".md", ".ipynb")


def _path_like_strings(literals: list[str]) -> list[str]:
    """Filter string literals to those that look like file paths (for reference resolution)."""
    out: list[str] = []
    for s in literals:
        if not s or len(s) > 512:
            continue
        # Skip URLs and flags
        if "://" in s or s.startswith("--") or s.startswith("-"):
            continue
        s_norm = s.replace("\\", "/").strip()
        if not s_norm:
            continue
        # Path-like: contains a path separator, or has a known file extension
        if "/" in s_norm or s_norm.endswith(_PATH_EXTENSIONS):
            out.append(s_norm)
    return out


def _resolve_path_reference(ref: str, source_path: str, all_module_paths: set[str]) -> str | None:
    """Resolve a path-like string (relative or repo-root) to a discovered module path."""
    ref = ref.replace("\\", "/").strip().lstrip("./")
    if not ref:
        return None
    # Normalize redundant parts (e.g. "models/../models/foo.sql" -> "models/foo.sql")
    parts: list[str] = []
    for p in ref.split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if parts:
                parts.pop()
            continue
        parts.append(p)
    ref = "/".join(parts)
    if not ref:
        return None
    # 1) Repo-root-relative
    if ref in all_module_paths:
        return ref
    # 2) Relative to current file's directory
    source_dir = str(Path(source_path).parent) if "/" in source_path else ""
    if source_dir:
        candidate = f"{source_dir}/{ref}"
        if candidate in all_module_paths:
            return candidate
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
