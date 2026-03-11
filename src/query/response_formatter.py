"""Format Navigator tool results for readable, evidence-rich output.

Clearly separates graph-backed answers from semantic inference.
"""

from __future__ import annotations

from query.tools import (
    BlastRadiusResult,
    ImplementationMatch,
    LineageResult,
    ModuleExplanation,
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
        lines.append("--- Graph-backed (from module/lineage graph) ---")
        for m in graph_matches:
            line_range = f" lines {m.line_range[0]}-{m.line_range[1]}" if m.line_range else ""
            lines.append(f"  • {m.path}{line_range}")
            lines.append(f"    Confidence: {m.confidence:.2f}  Provenance: {m.method_provenance}")

    if semantic_matches:
        lines.append("")
        lines.append("--- Semantic inference (from CODEBASE.md) ---")
        for m in semantic_matches:
            line_range = f" lines {m.line_range[0]}-{m.line_range[1]}" if m.line_range else ""
            lines.append(f"  • {m.path}{line_range}")
            lines.append(f"    Confidence: {m.confidence:.2f}  Provenance: {m.method_provenance}")

    return "\n".join(lines)


def format_lineage_result(result: LineageResult) -> str:
    """Format trace_lineage result with evidence."""
    lines = []
    lines.append(f"Lineage ({result.direction}) from: {result.start}")
    lines.append("")
    lines.append("--- Graph-backed ---")
    lines.append(result.evidence)
    lines.append("")
    lines.append(f"Nodes ({len(result.nodes)}):")
    for n in result.nodes[:50]:
        lines.append(f"  • {n}")
    if len(result.nodes) > 50:
        lines.append(f"  ... and {len(result.nodes) - 50} more")
    if result.edges:
        lines.append("")
        lines.append("Edges (sample):")
        for u, v, attrs in result.edges[:20]:
            edge_type = attrs.get("edge_type", "")
            lines.append(f"  {u} → {v}" + (f"  [{edge_type}]" if edge_type else ""))
        if len(result.edges) > 20:
            lines.append(f"  ... and {len(result.edges) - 20} more")
    return "\n".join(lines)


def format_blast_radius_result(result: BlastRadiusResult) -> str:
    """Format blast_radius result with evidence."""
    lines = []
    lines.append(f"Blast radius from: {result.start}")
    lines.append("")
    lines.append("--- Graph-backed ---")
    lines.append(result.evidence)
    lines.append("")
    lines.append(f"Affected nodes ({len(result.affected)}):")
    for n in result.affected[:50]:
        lines.append(f"  • {n}")
    if len(result.affected) > 50:
        lines.append(f"  ... and {len(result.affected) - 50} more")
    return "\n".join(lines)


def format_module_explanation(explanation: ModuleExplanation) -> str:
    """Format explain_module with clear graph vs semantic sections."""
    lines = []
    lines.append(f"Module: {explanation.path}")
    if explanation.line_range:
        lines.append(f"Line range: {explanation.line_range[0]}-{explanation.line_range[1]}")
    lines.append(f"Confidence: {explanation.confidence:.2f}")
    lines.append("")
    lines.append("--- Graph-backed (structure) ---")
    lines.append(explanation.graph_section)
    lines.append("")
    lines.append("--- Semantic inference (purpose/description) ---")
    lines.append(explanation.semantic_section)
    return "\n".join(lines)
