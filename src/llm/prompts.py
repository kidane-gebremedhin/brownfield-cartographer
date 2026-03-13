"""Prompt templates for Semanticist agent.

Templates use simple {placeholder} substitution. Caller is responsible
for escaping or sanitizing values if needed.
"""

from __future__ import annotations

# ---- Purpose statement (code-grounded; what it does, not how; not from docstring) ----
PURPOSE_STATEMENT_TEMPLATE = """Based only on the implementation below, write a single short sentence stating what this module does (its purpose), not how it does it. Use only evidence from the code: structure, names, imports, functions, and classes. Do not use or repeat the docstring; infer purpose from implementation.

Path: {module_path}
LOC: {loc}
Imports: {imports}
Top-level functions: {functions}
Top-level classes: {classes}
Bases (if any): {bases}

Source (first ~80 lines):
```
{source_preview}
```

Purpose (one sentence, what this module does):"""

# ---- Documentation drift: flag if docstring contradicts implementation ----
DRIFT_CLASSIFICATION_TEMPLATE = """Classify how well the existing docstring matches the code-derived purpose (from implementation evidence).

Code-derived purpose (from code, not docstring): {purpose}
Existing docstring or comment: {docstring}

Respond with exactly one word: aligned | stale | contradictory | insufficient
- aligned: doc accurately reflects current purpose
- stale: doc is outdated but not wrong
- contradictory: doc contradicts or conflicts with code purpose
- insufficient: doc missing or too vague to compare

Classification:"""

# ---- Domain clustering: business-domain boundaries (ingestion, transformation, etc.) ----
CLUSTER_LABEL_TEMPLATE = """These modules were grouped by semantic similarity. Suggest a short business-domain label (2–4 words) for this group, e.g. ingestion, transformation, serving, monitoring, orchestration, testing, api. Reply with only the label, no explanation.

Module purposes in this group:
{module_purposes}

Domain label:"""

# ---- Five FDE Day-One Answers: synthesize Surveyor + Hydrologist with LLM reasoning ----
DAY_ONE_TEMPLATE = """Synthesize the five Day-One answers for a developer onboarding to this codebase. Use only the provided context.

Definitions (use these precisely):
- **Primary ingestion path**: How data is moved from EXTERNAL systems (source databases, S3, etc.) INTO the warehouse. Identify: (1) source systems (e.g. Postgres, S3), (2) the ingestion tool that does the move (e.g. Airbyte, dlt), (3) where that tool is configured in the repo, (4) the orchestrator that triggers ingestion (e.g. Dagster). Do NOT describe only dbt upstream lineage or "sources" inside the warehouse—that is transformation, not ingestion. If context includes "Ingestion (data into warehouse):" use that.
- **Critical outputs/endpoints**: The 3-5 most critical output datasets/endpoints, such as final datasets, APIs, reports, or key deliverables (lineage sinks).
- **Blast radius**: Downstream impact if the most critical module (e.g. highest PageRank or key sink) fails.
- **Business logic concentrated vs distributed**: Where business logic is concentrated vs distributed (e.g. in dbt transformations, ingestion pipelines, PageRank hubs).
- **Git velocity hotspots**: Files changed most often (use "Raw git velocity" when present).

Context:
{context}

Answer each in 1–3 short sentences. Use the exact headings below. Include evidence citations (source_file:line_range or graph node) so the reader can verify.

1. Primary ingestion path
2. Critical outputs/endpoints
3. Blast radius of critical module
4. Business logic concentrated vs distributed
5. Git velocity hotspots"""


def render_purpose_statement(
    module_path: str,
    loc: int,
    imports: str,
    functions: str,
    classes: str,
    bases: str,
    source_preview: str,
) -> str:
    """Build the purpose-statement prompt from structured context."""
    return PURPOSE_STATEMENT_TEMPLATE.format(
        module_path=module_path,
        loc=loc,
        imports=imports,
        functions=functions,
        classes=classes,
        bases=bases,
        source_preview=source_preview,
    )


def render_drift_classification(purpose: str, docstring: str) -> str:
    """Build the drift-classification prompt."""
    doc = docstring.strip() if docstring else "(none)"
    return DRIFT_CLASSIFICATION_TEMPLATE.format(purpose=purpose, docstring=doc)


def render_cluster_label(module_purposes: str) -> str:
    """Build the cluster-label prompt."""
    return CLUSTER_LABEL_TEMPLATE.format(module_purposes=module_purposes)


def render_day_one(context: str) -> str:
    """Build the Day-One synthesis prompt."""
    return DAY_ONE_TEMPLATE.format(context=context)
