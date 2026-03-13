"""Format Navigator tool results for readable, evidence-rich output.

Every answer cites evidence: source file (and line range when available),
and analysis method (static analysis vs. LLM inference) for trust.
"""

from __future__ import annotations

from query.tools import (
    BlastRadiusResult,
    EdgeCitation,
    ImplementationMatch,
    LineageResult,
    ModuleExplanation,
    UpstreamSourcesResult,
)


def format_implementation_matches(matches: list[ImplementationMatch]) -> str:
    """Format find_implementation results with source and confidence."""
    lines = []
    if not matches:
        lines.append("No implementations found.")
        return "\n".join(lines)

    lines.append("Implementations found:")
    graph_matches = [m for m in matches if m.source == "graph"]
    semantic_matches = [m for m in matches if m.source == "semantic"]

    if graph_matches:
        lines.append("")
        lines.append("--- Graph-backed (static analysis) ---")
        for m in graph_matches:
            line_range = f" lines {m.line_range[0]}-{m.line_range[1]}" if m.line_range else ""
            lines.append(f"  • {m.path}{line_range}")
            lines.append(f"    Evidence: source={m.path}, method=static analysis, confidence={m.confidence:.2f}  [{m.method_provenance}]")

    if semantic_matches:
        lines.append("")
        lines.append("--- Semantic (LLM inference from CODEBASE.md) ---")
        for m in semantic_matches:
            line_range = f" lines {m.line_range[0]}-{m.line_range[1]}" if m.line_range else ""
            lines.append(f"  • {m.path}{line_range}")
            lines.append(f"    Evidence: source={m.path}, method=LLM inference, confidence={m.confidence:.2f}  [{m.method_provenance}]")

    return "\n".join(lines)


def _citation_str(e: EdgeCitation) -> str:
    """Format file:line citation for an edge."""
    if e.source_file and e.line_start is not None:
        if e.line_end is not None and e.line_end != e.line_start:
            return f"{e.source_file}:{e.line_start}-{e.line_end}"
        return f"{e.source_file}:{e.line_start}"
    return e.source_file or "(no location)"


def format_upstream_sources_answer(result: UpstreamSourcesResult) -> str:
    """Format the answer to: What upstream sources feed this output dataset?

    Shows DataLineageGraph upstream traversal with file:line citations per edge.
    """
    lines = []
    lines.append("What upstream sources feed this output dataset?")
    lines.append("")
    lines.append(f"Output dataset: {result.dataset}")
    lines.append("")
    lines.append("--- Evidence: DataLineageGraph upstream traversal (static analysis), source=lineage_graph.json ---")
    lines.append(result.evidence)
    lines.append("")
    lines.append("Upstream nodes (sources that feed this dataset):")
    # Exclude the dataset itself from "upstream" list for clarity
    upstream_only = [n for n in result.upstream_nodes if n != result.dataset]
    if not upstream_only:
        lines.append("  (none)")
    else:
        for n in upstream_only[:100]:
            lines.append(f"  • {n}")
        if len(upstream_only) > 100:
            lines.append(f"  ... and {len(upstream_only) - 100} more")
    lines.append("")
    lines.append("Edges with file:line citations:")
    if not result.edges_with_citations:
        lines.append("  (none)")
    else:
        for e in result.edges_with_citations[:80]:
            loc = _citation_str(e)
            tt = f"  [{e.transformation_type}]" if e.transformation_type else ""
            lines.append(f"  {e.source} → {e.target}{tt}  @ {loc}")
        if len(result.edges_with_citations) > 80:
            lines.append(f"  ... and {len(result.edges_with_citations) - 80} more")
    return "\n".join(lines)


def format_lineage_result(result: LineageResult) -> str:
    """Format trace_lineage result with evidence (source, method, confidence)."""
    lines = []
    lines.append(f"Lineage ({result.direction}) from: {result.start}")
    lines.append("")
    lines.append("--- Evidence: method=static analysis (lineage graph), source=lineage_graph.json ---")
    lines.append(result.evidence)
    lines.append("")
    lines.append(f"Nodes ({len(result.nodes)}):")
    for n in result.nodes[:50]:
        lines.append(f"  • {n}")
    if len(result.nodes) > 50:
        lines.append(f"  ... and {len(result.nodes) - 50} more")
    if result.edges:
        lines.append("")
        lines.append("Edges (sample) [transformation_type, source_file:line_range]:")
        for u, v, attrs in result.edges[:20]:
            edge_type = attrs.get("edge_type", "")
            tt = attrs.get("transformation_type", "")
            sf = attrs.get("source_file", "")
            ls, le = attrs.get("line_start"), attrs.get("line_end")
            loc = f"{sf}:{ls}-{le}" if sf and ls is not None else (sf or "")
            lines.append(f"  {u} → {v}" + (f"  [{edge_type}]" if edge_type else "") + (f"  {tt}" if tt else "") + (f"  @ {loc}" if loc else ""))
        if len(result.edges) > 20:
            lines.append(f"  ... and {len(result.edges) - 20} more")
    return "\n".join(lines)


def format_blast_radius_result(result: BlastRadiusResult) -> str:
    """Format blast_radius result: dependency graph of what would break if this module/dataset changed."""
    lines = []
    lines.append("What would break if this module/dataset changed its interface?")
    lines.append("")
    lines.append(f"Module/dataset: {result.start}")
    lines.append("")
    lines.append("--- Evidence: method=static analysis (lineage graph), source=lineage_graph.json ---")
    lines.append(result.evidence)
    lines.append("")
    lines.append(f"Affected nodes ({len(result.affected)}):")
    for n in result.affected[:50]:
        lines.append(f"  • {n}")
    if len(result.affected) > 50:
        lines.append(f"  ... and {len(result.affected) - 50} more")
    return "\n".join(lines)


def format_module_explanation(explanation: ModuleExplanation) -> str:
    """Format explain_module with evidence: source file, line range, analysis method."""
    lines = []
    lines.append(f"Module: {explanation.path}")
    if explanation.line_range:
        lines.append(f"Line range: {explanation.line_range[0]}-{explanation.line_range[1]}")
    lines.append(f"Evidence: source={explanation.path}, method=static analysis (graph) + LLM inference (purpose), confidence={explanation.confidence:.2f}")
    lines.append("")
    lines.append("--- Graph-backed (structure) ---")
    lines.append(explanation.graph_section)
    lines.append("")
    lines.append("--- Semantic inference (purpose/description) ---")
    lines.append(explanation.semantic_section)
    return "\n".join(lines)
