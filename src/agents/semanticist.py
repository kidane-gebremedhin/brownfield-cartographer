"""Semanticist agent: code-grounded purpose, doc drift, domain clustering, Day-One synthesis.

Consumes Surveyor and Hydrologist outputs; uses an LLM and optional embeddings provider.
Designed to be testable with mock providers and token budget tracking.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from agents.hydrologist import blast_radius, find_sources, find_sinks
from llm.budget import TokenBudget
from llm.embeddings import EmbeddingsProvider
from llm.prompts import (
    render_cluster_label,
    render_day_one,
    render_drift_classification,
    render_purpose_statement,
)
from llm.provider import LLMProvider
from repository.file_discovery import discover_files

logger = logging.getLogger(__name__)

# Drift classification labels (spec)
DriftLabel = Literal["aligned", "stale", "contradictory", "insufficient"]

# Approximate tokens for budget (chars / 4)
def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def extract_module_docstring(source: str) -> str | None:
    """Extract the first top-level module docstring (triple-quoted string)."""
    if not source or not source.strip():
        return None
    # Match """...""" or '''...''' at start (after optional BOM/whitespace)
    m = re.search(r'^(?:\s|#.*)*?(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\')', source)
    if m:
        return (m.group(1) or m.group(2) or "").strip() or None
    return None


@dataclass
class SemanticistResult:
    """Output of run_semanticist."""

    purpose_statements: dict[str, str] = field(default_factory=dict)
    drift: dict[str, DriftLabel] = field(default_factory=dict)
    domains: list[dict[str, Any]] = field(default_factory=list)  # [{ "label": str, "modules": [path, ...] }]
    day_one_markdown: str = ""


def run_semanticist(
    repo_root: Path | str,
    surveyor_result: Any,
    hydrologist_result: Any,
    llm_provider: LLMProvider,
    *,
    embeddings_provider: EmbeddingsProvider | None = None,
    budget: TokenBudget | None = None,
    max_source_lines: int = 80,
    num_domains_min: int = 5,
    num_domains_max: int = 8,
) -> SemanticistResult:
    """Run full semanticist pipeline: purpose, drift, clustering, Day-One synthesis."""
    root = Path(repo_root).resolve()
    budget = budget or TokenBudget()
    out = SemanticistResult()

    # Index module source by path
    files = discover_files(root)
    source_by_path: dict[str, str] = {}
    for f in files:
        if f.extension == ".py":
            try:
                source_by_path[f.path] = f.content.decode("utf-8", errors="replace")
            except Exception:
                pass

    modules = getattr(surveyor_result, "modules", {})
    if not modules:
        out.day_one_markdown = _synthesize_day_one_fallback(surveyor_result, hydrologist_result)
        return out

    # 1) Purpose statements (code-grounded)
    for path, metrics in modules.items():
        src = source_by_path.get(path, "")
        preview = "\n".join(src.splitlines()[:max_source_lines])
        imports_str = ""
        funcs = ""
        classes = ""
        bases = ""
        try:
            from analyzers.tree_sitter_analyzer import analyze_python_source
            facts = analyze_python_source(src.encode("utf-8", errors="replace"), path=path)
            imports_str = ", ".join(f"{x.module}" for x in facts.imports[:20])
            funcs = ", ".join(f.name for f in facts.functions[:15])
            classes = ", ".join(c.name for c in facts.classes[:15])
            bases = ", ".join(b for c in facts.classes for b in c.bases[:3])
        except Exception:
            pass
        prompt = render_purpose_statement(
            module_path=path,
            loc=getattr(metrics, "loc", 0),
            imports=imports_str[:500],
            functions=funcs[:300],
            classes=classes[:300],
            bases=bases[:200],
            source_preview=preview[:4000],
        )
        if not budget.can_afford(_est_tokens(prompt), 100):
            logger.warning("Token budget exhausted; skipping purpose for %s", path)
            continue
        try:
            resp = llm_provider.complete(prompt, max_tokens=150, temperature=0.2)
            out.purpose_statements[path] = resp.strip().split("\n")[0][:500]
            budget.add(_est_tokens(prompt), _est_tokens(resp))
        except Exception as e:
            logger.warning("Purpose statement failed for %s: %s", path, e)

    # 2) Documentation drift
    for path, purpose in out.purpose_statements.items():
        src = source_by_path.get(path, "")
        doc = extract_module_docstring(src)
        if not doc:
            out.drift[path] = "insufficient"
            continue
        prompt = render_drift_classification(purpose, doc)
        if not budget.can_afford(_est_tokens(prompt), 20):
            out.drift[path] = "insufficient"
            continue
        try:
            resp = llm_provider.complete(prompt, max_tokens=30, temperature=0.0)
            raw = resp.strip().lower().split()[0] if resp.strip() else ""
            if raw in ("aligned", "stale", "contradictory", "insufficient"):
                out.drift[path] = raw
            else:
                out.drift[path] = "insufficient"
            budget.add(_est_tokens(prompt), _est_tokens(resp))
        except Exception as e:
            logger.warning("Drift classification failed for %s: %s", path, e)
            out.drift[path] = "insufficient"

    # 3) Domain clustering (5–8 domains, readable labels)
    if embeddings_provider and out.purpose_statements:
        vectors = embeddings_provider.embed(list(out.purpose_statements.values()))
        paths = list(out.purpose_statements.keys())
        try:
            clusters = _cluster_assignments(vectors, min_c=num_domains_min, max_c=num_domains_max)
        except Exception as e:
            logger.warning("Clustering failed: %s; using single domain", e)
            clusters = [0] * len(paths)
        # Group by cluster id
        from collections import defaultdict
        by_c: dict[int, list[str]] = defaultdict(list)
        for i, cid in enumerate(clusters):
            if i < len(paths):
                by_c[cid].append(paths[i])
        domain_list = []
        for cid in sorted(by_c.keys()):
            mods = by_c[cid]
            purposes_blob = "\n".join(f"- {p}: {out.purpose_statements.get(p, '')}" for p in mods[:30])
            label = f"Domain {cid + 1}"
            if budget.can_afford(200, 50):
                try:
                    prompt = render_cluster_label(purposes_blob)
                    label = llm_provider.complete(prompt, max_tokens=50, temperature=0.2).strip().split("\n")[0][:80]
                    budget.add(_est_tokens(prompt), _est_tokens(label))
                except Exception:
                    pass
            domain_list.append({"label": label, "modules": mods})
        out.domains = domain_list

    # 4) Day-One synthesis (five answers)
    context = _build_day_one_context(surveyor_result, hydrologist_result, out)
    prompt = render_day_one(context)
    if budget.can_afford(_est_tokens(prompt), 800):
        try:
            out.day_one_markdown = llm_provider.complete(prompt, max_tokens=800, temperature=0.3)
            budget.add(_est_tokens(prompt), _est_tokens(out.day_one_markdown))
        except Exception as e:
            logger.warning("Day-One synthesis failed: %s", e)
            out.day_one_markdown = _synthesize_day_one_fallback(surveyor_result, hydrologist_result)
    else:
        out.day_one_markdown = _synthesize_day_one_fallback(surveyor_result, hydrologist_result)

    return out


def _cluster_assignments(vectors: list[list[float]], min_c: int = 5, max_c: int = 8) -> list[int]:
    """Return cluster index per vector. Prefer k in [min_c, max_c]. Uses simple k-means if numpy available."""
    import random
    n = len(vectors)
    if n == 0:
        return []
    k = min(max_c, max(min_c, (n + 3) // 4))
    k = max(1, min(k, n))  # k must be <= n
    try:
        import numpy as np
        X = np.array(vectors, dtype=float)
        centroids = X[random.sample(range(n), k)]
        for _ in range(15):
            dists = np.array([[np.linalg.norm(x - c) for c in centroids] for x in X])
            assign = np.argmin(dists, axis=1)
            new_c = np.array([X[assign == i].mean(axis=0) if np.any(assign == i) else centroids[i] for i in range(k)])
            if np.allclose(centroids, new_c):
                break
            centroids = new_c
        return assign.tolist()
    except ImportError:
        return [hash(str(v)) % k for v in vectors]


def _build_day_one_context(
    surveyor_result: Any,
    hydrologist_result: Any,
    sem_result: SemanticistResult,
) -> str:
    """Build context string for Day-One prompt."""
    lines = []
    s = surveyor_result
    h = hydrologist_result
    g = getattr(h, "graph", None)
    if g is not None:
        sources = find_sources(g)
        sinks = find_sinks(g)
        lines.append("Data lineage sources (no incoming edges): " + ", ".join(sorted(sources)[:15]))
        lines.append("Data lineage sinks (no outgoing edges): " + ", ".join(sorted(sinks)[:15]))
        if sinks:
            critical = next(iter(sorted(sinks)))
            radius = blast_radius(g, critical, max_depth=5)
            lines.append(f"Blast radius (downstream of one sink, max_depth=5): {len(radius)} nodes")
    pr = getattr(s, "pagerank", {}) or {}
    if pr:
        top = sorted(pr.items(), key=lambda x: -x[1])[:5]
        lines.append("PageRank (top 5 modules): " + ", ".join(f"{p}({v:.3f})" for p, v in top))
    mods = getattr(s, "modules", {}) or {}
    velocity = sorted(mods.values(), key=lambda m: getattr(m, "change_velocity_30d", 0), reverse=True)[:5]
    if velocity:
        lines.append("Git velocity (30d) hotspots: " + ", ".join(getattr(m, "path", "") for m in velocity))
    if sem_result.purpose_statements:
        lines.append("Module purposes (sample): " + "; ".join(f"{p}: {t[:80]}" for p, t in list(sem_result.purpose_statements.items())[:10]))
    if sem_result.domains:
        lines.append("Inferred domains: " + ", ".join(d.get("label", "") for d in sem_result.domains))
    return "\n".join(lines)


def _synthesize_day_one_fallback(surveyor_result: Any, hydrologist_result: Any) -> str:
    """Fallback Day-One text when LLM is not used or fails."""
    lines = [
        "1. Primary ingestion path\n(Pending: from lineage sources and entry modules.)",
        "2. Critical outputs/endpoints\n(Pending: from lineage sinks and API modules.)",
        "3. Blast radius of critical module\n(Pending: run blast_radius on critical node.)",
        "4. Business logic concentrated vs distributed\n(Pending: from module graph and domains.)",
        "5. Git velocity hotspots\n(Pending: from Surveyor velocity metrics.)",
    ]
    return "\n\n".join(lines)
