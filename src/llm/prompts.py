"""Prompt templates for Semanticist agent.

Templates use simple {placeholder} substitution. Caller is responsible
for escaping or sanitizing values if needed.
"""

from __future__ import annotations

# ---- Purpose statement (code-grounded; avoid simply repeating docstrings) ----
PURPOSE_STATEMENT_TEMPLATE = """Based only on the code below, write a single short sentence describing this module's purpose. Do not repeat the docstring verbatim; infer from structure, names, and imports.

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

Purpose (one sentence):"""

# ---- Documentation drift classification ----
DRIFT_CLASSIFICATION_TEMPLATE = """Classify how well the existing documentation matches the code-derived purpose.

Code-derived purpose: {purpose}
Existing docstring or comment: {docstring}

Respond with exactly one word: aligned | stale | contradictory | insufficient
- aligned: doc accurately reflects current purpose
- stale: doc is outdated but not wrong
- contradictory: doc conflicts with code purpose
- insufficient: doc missing or too vague to compare

Classification:"""

# ---- Domain clustering: label for a cluster of module purposes ----
CLUSTER_LABEL_TEMPLATE = """These modules were grouped by similarity. Suggest a short domain label (2–4 words) for this group. Reply with only the label, no explanation.

Module purposes in this group:
{module_purposes}

Domain label:"""

# ---- Day-One synthesis (five FDE answers) ----
DAY_ONE_TEMPLATE = """Synthesize the five Day-One answers for a developer onboarding to this codebase. Use only the provided context; cite provenance (e.g. "from module graph", "from lineage").

Context:
{context}

Answer each in 1–3 short sentences. Use the exact headings below.

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
