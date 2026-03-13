"""Archivist agent: generates durable artifacts for humans and AI agents.

Artifacts written to cartography/:
- CODEBASE.md
- onboarding_brief.md
- module_graph.json
- lineage_graph.json
- cartography_trace.jsonl

Design:
- Deterministic output ordering
- Consumes outputs of Surveyor/Hydrologist (and later Semanticist)
- JSON artifacts are machine-readable for Navigator consumption
- Pyvis HTML: module_graph.html, lineage_graph.html (optional; written when pyvis is available)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graph.serializers import serialize_digraph
from models.artifacts import DayOneAnswer, OnboardingBrief

logger = logging.getLogger(__name__)

try:
    from graph.visualization import build_lineage_graph_html, build_module_graph_html
    _PYVIS_AVAILABLE = True
except ImportError:
    _PYVIS_AVAILABLE = False


@dataclass(frozen=True)
class ArchivistInputs:
    repo_root: Path
    surveyor_result: Any  # SurveyorResult
    hydrologist_result: Any  # HydrologistResult
    day_one_answers_markdown: str | None = None  # optional (Semanticist)
    semanticist_result: Any | None = None  # SemanticistResult: purpose_statements, drift, domains
    trace_events: list[dict[str, Any]] | None = None


def write_artifacts(inputs: ArchivistInputs, out_dir: Path | str | None = None) -> Path:
    """Write all archivist artifacts. Returns output directory path."""
    repo_root = Path(inputs.repo_root).resolve()
    out = Path(out_dir) if out_dir is not None else repo_root / 'cartography'
    out.mkdir(parents=True, exist_ok=True)

    # JSON graph artifacts
    module_graph = serialize_digraph(inputs.surveyor_result.graph)
    lineage_graph = serialize_digraph(inputs.hydrologist_result.graph)

    _write_json(out / 'module_graph.json', module_graph)
    _write_json(out / 'lineage_graph.json', lineage_graph)

    # Markdown artifacts
    codebase_md = generate_CODEBASE_md(inputs)
    onboarding_md = render_onboarding_brief(inputs)

    (out / 'CODEBASE.md').write_text(codebase_md, encoding='utf-8')
    (out / 'onboarding_brief.md').write_text(onboarding_md, encoding='utf-8')

    # Trace log
    trace_path = out / 'cartography_trace.jsonl'
    _write_trace_jsonl(trace_path, inputs.trace_events or [])

    # Pyvis HTML (optional)
    if _PYVIS_AVAILABLE:
        try:
            build_module_graph_html(
                inputs.surveyor_result.graph,
                getattr(inputs.surveyor_result, 'modules', {}),
                getattr(inputs.surveyor_result, 'pagerank', {}),
                out / 'module_graph.html',
                open_browser=False,
            )
            build_lineage_graph_html(inputs.hydrologist_result.graph, out / 'lineage_graph.html', open_browser=False)
        except Exception as e:
            logger.warning('Pyvis HTML generation failed: %s', e)

    return out


def generate_CODEBASE_md(inputs: ArchivistInputs) -> str:
    """Generate the living context file (CODEBASE.md) for AI coding agents. Alias for render_codebase_md."""
    return render_codebase_md(inputs)


def render_codebase_md(inputs: ArchivistInputs) -> str:
    """Render CODEBASE.md with required sections."""
    s = inputs.surveyor_result
    h = inputs.hydrologist_result

    # Recent velocity hotspots
    velocity_sorted = sorted(
        getattr(s, 'modules', {}).values(),
        key=lambda m: (getattr(m, 'change_velocity_30d', 0), getattr(m, 'change_velocity_90d', 0)),
        reverse=True,
    )
    top_velocity = velocity_sorted[:10]

    # Sources/sinks from lineage graph
    lg = h.graph
    sources = [n for n in lg.nodes() if lg.in_degree(n) == 0]
    sinks = [n for n in lg.nodes() if lg.out_degree(n) == 0]

    # Purpose index (from semanticist if available)
    sem = inputs.semanticist_result
    purpose_map = getattr(sem, 'purpose_statements', {}) if sem else {}
    module_purpose_lines = []
    for m in sorted(getattr(s, 'modules', {}).values(), key=lambda x: x.path):
        purpose = purpose_map.get(m.path, '(purpose pending)')
        module_purpose_lines.append(f"- `{m.path}`: {purpose}")

    lines = []
    lines.append('# CODEBASE')
    lines.append('')

    lines.append('## Architecture Overview')
    lines.append('This codebase is summarized from the Surveyor (module import graph and PageRank) and Hydrologist (data lineage graph). Critical path, sources/sinks, and known debt are derived from these graphs; purpose and drift come from the Semanticist when run.')
    lines.append('')

    lines.append('## Critical Path')
    lines.append('Top 5 modules by PageRank (architectural hubs).')
    pagerank = getattr(s, 'pagerank', {})
    for path in sorted(pagerank.keys(), key=lambda p: -pagerank.get(p, 0))[:5]:
        lines.append(f"- `{path}` (PageRank={pagerank.get(path, 0):.4f})")
    lines.append('')

    lines.append('## Data Sources & Sinks')
    lines.append('### Sources')
    for n in sorted(sources)[:20]:
        lines.append(f"- `{n}`")
    lines.append('')
    lines.append('### Sinks')
    for n in sorted(sinks)[:20]:
        lines.append(f"- `{n}`")
    lines.append('')

    lines.append('## Known Debt')
    sccs = getattr(s, 'sccs', [])
    for i, comp in enumerate(sccs):
        if len(comp) > 1:
            lines.append(f"- **Circular dependency (SCC {i + 1})**: {', '.join(sorted(comp))}")
    dead = [m.path for m in getattr(s, 'modules', {}).values() if getattr(m, 'is_dead_code_candidate', False)]
    for p in sorted(dead):
        lines.append(f"- **Dead-code candidate**: `{p}`")
    drift_map = getattr(sem, 'drift', {}) if sem else {}
    for path, label in sorted(drift_map.items()):
        if label in ('stale', 'contradictory'):
            lines.append(f"- **Documentation drift** (`{path}`): {label}")
    if not sccs and not dead and not any(drift_map.get(p) in ('stale', 'contradictory') for p in drift_map):
        lines.append('- No circular dependencies, dead-code candidates, or documentation drift identified.')
    lines.append('')

    lines.append('## High-Velocity Files (Recent Change Velocity)')
    lines.append('Files changing most frequently (likely pain points).')
    for m in top_velocity:
        lines.append(f"- `{m.path}`: 30d={m.change_velocity_30d}, 90d={m.change_velocity_90d}")
    lines.append('')

    lines.append('## Module Purpose Index')
    lines.extend(module_purpose_lines)
    lines.append('')

    return '\n'.join(lines)


def render_onboarding_brief(inputs: ArchivistInputs) -> str:
    """Render onboarding_brief.md with required sections and explicit evidence citations."""
    sem = inputs.semanticist_result
    structured_answers: list[DayOneAnswer] = getattr(sem, "day_one_answers", []) if sem else []

    lines: list[str] = []
    lines.append("# Onboarding Brief")
    lines.append("")

    lines.append("## Day-One Answers")
    if structured_answers:
        for ans in sorted(structured_answers, key=lambda a: a.question_id):
            lines.append(f"### {ans.question_id}. {ans.title}")
            lines.append(ans.answer_markdown.strip())
            lines.append(
                f"_Confidence: {ans.confidence:.2f} via {ans.method}_"
            )
            lines.append("")
    elif inputs.day_one_answers_markdown:
        lines.append(inputs.day_one_answers_markdown.strip())
        lines.append("")
    else:
        lines.append("- (pending: semanticist synthesis)")
        lines.append("")

    lines.append("## Evidence citations")
    if structured_answers:
        for ans in sorted(structured_answers, key=lambda a: a.question_id):
            lines.append(f"- Q{ans.question_id} {ans.title}")
            if ans.evidence:
                for ev in ans.evidence:
                    if ev.file_path and ev.line_start is not None and ev.line_end is not None:
                        loc = f"`{ev.file_path}:{ev.line_start}-{ev.line_end}`"
                    elif ev.file_path:
                        loc = f"`{ev.file_path}`"
                    else:
                        loc = ev.source
                    note_bits = []
                    if ev.analysis_method:
                        note_bits.append(ev.analysis_method)
                    if ev.notes:
                        note_bits.append(ev.notes)
                    note_str = " - " + "; ".join(note_bits) if note_bits else ""
                    lines.append(f"  - {loc}{note_str}")
            else:
                lines.append("  - (no structured evidence captured)")
    else:
        lines.append("- Module graph: `cartography/module_graph.json`")
        lines.append("- Lineage graph: `cartography/lineage_graph.json`")
    lines.append("")

    lines.append("## Confidence notes")
    if structured_answers:
        avg_conf = sum(a.confidence for a in structured_answers) / max(len(structured_answers), 1)
        lines.append(f"- Overall Day-One confidence (static/graph-based): {avg_conf:.2f}")
    lines.append("- Static extraction is conservative; dynamic refs are recorded as unresolved.")
    lines.append("")

    lines.append("## Known unknowns")
    lines.append("- Business logic semantics may still be incomplete despite static analysis.")
    lines.append("- Runtime-only dataset names may appear as `<dynamic>` / `<sql_query>` / `<spark_read>` etc.")
    lines.append("")

    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')


def _write_trace_jsonl(path: Path, events: list[dict[str, Any] | Any]) -> None:
    """Write trace events (dict or CartographyTraceEntry) as JSONL."""
    from models.trace import CartographyTraceEntry
    with path.open('w', encoding='utf-8') as f:
        for ev in events:
            if isinstance(ev, CartographyTraceEntry):
                f.write(ev.model_dump_json(exclude_none=True) + '\n')
            else:
                f.write(json.dumps(ev, sort_keys=True) + '\n')
