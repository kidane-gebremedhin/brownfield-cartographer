"""Interactive Pyvis visualization for module and lineage graphs.

Produces HTML files that open locally in a browser; no server required.
Node hover metadata and grouping follow spec 09.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import networkx as nx

try:
    from pyvis.network import Network
except ImportError:
    Network = None  # type: ignore[misc, assignment]


def _short_label(path: str, max_parts: int = 2) -> str:
    """Short module path or basename for node label."""
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= max_parts:
        return path
    return "/".join(parts[-max_parts:])


def _module_node_title(
    path: str,
    modules: dict[str, Any],
    pagerank: dict[str, float],
) -> str:
    """Full path, PageRank, complexity, velocity, dead-code for hover."""
    lines = [f"path: {path}"]
    if path in pagerank:
        lines.append(f"PageRank: {pagerank[path]:.4f}")
    m = modules.get(path)
    if m is not None:
        lines.append(f"LOC: {getattr(m, 'loc', '—')}")
        lines.append(f"complexity: {getattr(m, 'complexity_score', '—')}")
        lines.append(f"velocity 30d: {getattr(m, 'change_velocity_30d', '—')}")
        lines.append(f"velocity 90d: {getattr(m, 'change_velocity_90d', '—')}")
        if getattr(m, "is_dead_code_candidate", False):
            lines.append("dead-code candidate: yes")
    return "\n".join(lines)


def _lineage_node_title(node_id: str, attrs: dict[str, Any]) -> str:
    """Node title including source file where available."""
    lines = [f"id: {node_id}", f"type: {attrs.get('node_type', '—')}"]
    if node_id.startswith(("sql:", "py:", "nb:")):
        prefix, _, rest = node_id.partition(":")
        lines.append(f"source: {rest}")
    return "\n".join(lines)


def build_module_graph_html(
    graph: nx.DiGraph,
    modules: dict[str, Any],
    pagerank: dict[str, float],
    out_path: Path | str,
    *,
    open_browser: bool = False,
) -> Path:
    """Write interactive module graph HTML. Node label = short path; title = full path + metrics; group = language."""
    out_path = Path(out_path)
    if Network is None:
        raise RuntimeError("pyvis is not installed; install with: pip install pyvis")

    g = copy.deepcopy(graph)
    language_groups: dict[str, int] = {}
    for n in g.nodes():
        m = modules.get(n)
        lang = getattr(m, "language", "unknown") if m else "unknown"
        if lang not in language_groups:
            language_groups[lang] = len(language_groups)
        g.nodes[n]["label"] = _short_label(n)
        g.nodes[n]["title"] = _module_node_title(n, modules, pagerank)
        g.nodes[n]["group"] = language_groups[lang]

    for u, v, attrs in list(g.edges(data=True)):
        edge_type = attrs.get("edge_type", "reference")
        g[u][v]["title"] = edge_type  # hover: import vs path_reference

    nt = Network(height="700px", width="100%", directed=True)
    nt.from_nx(g)
    nt.write_html(str(out_path), open_browser=open_browser)
    return out_path


def build_lineage_graph_html(
    graph: nx.DiGraph,
    out_path: Path | str,
    *,
    open_browser: bool = False,
) -> Path:
    """Write interactive lineage graph HTML. Datasets grouped by type; transformations distinct; direction visible."""
    out_path = Path(out_path)
    if Network is None:
        raise RuntimeError("pyvis is not installed; install with: pip install pyvis")

    g = copy.deepcopy(graph)
    type_to_group: dict[str, int] = {}
    for n in g.nodes():
        attrs = g.nodes[n]
        ntype = attrs.get("node_type", "unresolved")
        if ntype not in type_to_group:
            type_to_group[ntype] = len(type_to_group)
        g.nodes[n]["group"] = type_to_group[ntype]
        g.nodes[n]["title"] = _lineage_node_title(n, attrs)
        if ntype == "transformation":
            g.nodes[n]["label"] = _short_label(n.split(":", 1)[-1] if ":" in n else n)
            g.nodes[n]["shape"] = "box"
        else:
            g.nodes[n]["label"] = n if len(n) <= 40 else n[:37] + "..."

    nt = Network(height="700px", width="100%", directed=True)
    nt.from_nx(g)
    nt.write_html(str(out_path), open_browser=open_browser)
    return out_path
