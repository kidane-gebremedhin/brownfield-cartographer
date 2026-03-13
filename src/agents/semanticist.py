"""Agent 3: The Semanticist (LLM-Powered Purpose Analyst).

Uses LLMs to generate semantic understanding of code that static analysis cannot provide.
This is not summarization—it is purpose extraction grounded in implementation evidence.

Core tasks:
- For each module: generate a Purpose Statement (what this module does, not how)
  based on its code, not its docstring.
- Flag if the docstring contradicts the implementation (aligned | stale | contradictory | insufficient).
- Identify Business Domain boundaries: cluster modules into inferred domains
  (e.g. ingestion, transformation, serving, monitoring) based on semantic similarity.
- Generate the Five FDE Day-One Answers by synthesizing Surveyor + Hydrologist output
  with LLM reasoning over the full architectural context.
- Cost discipline: tier 'bulk' (purpose/drift/cluster) and 'synthesis' (Day-One) both use
  DeepSeek; you can set CARTOGRAPHER_DEEPSEEK_MODEL and CARTOGRAPHER_SYNTHESIS_MODEL in .env.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from agents.hydrologist import blast_radius, find_sources, find_sinks
from llm.budget import ContextWindowBudget, TokenBudget, estimate_tokens
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

def _est_tokens(text: str) -> int:
    return estimate_tokens(text)


def extract_module_docstring(source: str) -> str | None:
    """Extract the first top-level module docstring (triple-quoted string)."""
    if not source or not source.strip():
        return None
    # Match """...""" or '''...''' at start (after optional BOM/whitespace)
    m = re.search(r'^(?:\s|#.*)*?(?:"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\')', source)
    if m:
        return (m.group(1) or m.group(2) or "").strip() or None
    return None


def generate_purpose_statement(
    module_path: str,
    source: str,
    llm_provider: LLMProvider,
    *,
    max_source_lines: int = 80,
    budget: TokenBudget | ContextWindowBudget | None = None,
) -> tuple[str, DriftLabel]:
    """Generate a 2–3 sentence purpose statement from the module's code (not docstring), then flag doc drift.

    Prompts the LLM with code preview; cross-references existing docstring and returns
    (purpose_statement, drift_label). Discrepancies are flagged as Documentation Drift.
    """
    preview = "\n".join(source.splitlines()[:max_source_lines])
    imports_str = ""
    funcs = ""
    classes = ""
    bases = ""
    try:
        from analyzers.tree_sitter_analyzer import analyze_python_source
        facts = analyze_python_source(source.encode("utf-8", errors="replace"), path=module_path)
        imports_str = ", ".join(f"{x.module}" for x in facts.imports[:20])
        funcs = ", ".join(f.name for f in facts.functions[:15])
        classes = ", ".join(c.name for c in facts.classes[:15])
        bases = ", ".join(b for c in facts.classes for b in c.bases[:3])
    except Exception:
        pass
    loc = len([l for l in source.splitlines() if l.strip() and not l.strip().startswith("#")])
    prompt = render_purpose_statement(
        module_path=module_path,
        loc=loc,
        imports=imports_str[:500],
        functions=funcs[:300],
        classes=classes[:300],
        bases=bases[:200],
        source_preview=preview[:4000],
    )
    in_tok, out_tok = _est_tokens(prompt), 150
    if budget is not None:
        can_afford = budget.can_afford(in_tok, out_tok) if hasattr(budget, "can_afford") else True
        if not can_afford:
            return ("(purpose skipped: token budget exhausted)", "insufficient")
    try:
        resp = llm_provider.complete(prompt, max_tokens=150, temperature=0.2, tier="bulk")
        purpose = resp.strip().split("\n")[0][:500]
    except Exception as e:
        logger.warning("Purpose statement failed for %s: %s", module_path, e)
        return ("(purpose generation failed)", "insufficient")
    if budget is not None:
        if hasattr(budget, "record_usage"):
            budget.record_usage(in_tok, _est_tokens(resp))
        else:
            budget.add(in_tok, _est_tokens(resp))
    doc = extract_module_docstring(source)
    if not doc:
        return (purpose, "insufficient")
    drift_prompt = render_drift_classification(purpose, doc)
    din, dout = _est_tokens(drift_prompt), 30
    if budget is not None and hasattr(budget, "can_afford") and not budget.can_afford(din, dout):
        return (purpose, "insufficient")
    try:
        drift_resp = llm_provider.complete(drift_prompt, max_tokens=30, temperature=0.0, tier="bulk")
        raw = drift_resp.strip().lower().split()[0] if drift_resp.strip() else ""
        drift = raw if raw in ("aligned", "stale", "contradictory", "insufficient") else "insufficient"
        if budget is not None:
            if hasattr(budget, "record_usage"):
                budget.record_usage(din, _est_tokens(drift_resp))
            else:
                budget.add(din, _est_tokens(drift_resp))
    except Exception as e:
        logger.warning("Drift classification failed for %s: %s", module_path, e)
        drift = "insufficient"
    return (purpose, drift)


def cluster_into_domains(
    purpose_statements: dict[str, str],
    embeddings_provider: EmbeddingsProvider,
    *,
    llm_provider: LLMProvider | None = None,
    budget: TokenBudget | ContextWindowBudget | None = None,
    num_domains_min: int = 5,
    num_domains_max: int = 8,
) -> list[dict[str, Any]]:
    """Embed all purpose statements, run k-means (k in [5, 8]), label each cluster → Domain Architecture Map."""
    if not purpose_statements:
        return []
    vectors = embeddings_provider.embed(list(purpose_statements.values()))
    paths = list(purpose_statements.keys())
    try:
        clusters = _cluster_assignments(vectors, min_c=num_domains_min, max_c=num_domains_max)
    except Exception as e:
        logger.warning("Clustering failed: %s; using single domain", e)
        clusters = [0] * len(paths)
    by_c: dict[int, list[str]] = defaultdict(list)
    for i, cid in enumerate(clusters):
        if i < len(paths):
            by_c[cid].append(paths[i])
    domain_list: list[dict[str, Any]] = []
    for cid in sorted(by_c.keys()):
        mods = by_c[cid]
        purposes_blob = "\n".join(f"- {p}: {purpose_statements.get(p, '')}" for p in mods[:30])
        label = f"Domain {cid + 1}"
        if llm_provider and (budget is None or (hasattr(budget, "can_afford") and budget.can_afford(200, 50))):
            try:
                prompt = render_cluster_label(purposes_blob)
                label = llm_provider.complete(prompt, max_tokens=50, temperature=0.2, tier="bulk").strip().split("\n")[0][:80]
                if hasattr(budget, "record_usage"):
                    budget.record_usage(_est_tokens(prompt), _est_tokens(label))
                else:
                    budget.add(_est_tokens(prompt), _est_tokens(label))
            except Exception:
                pass
        domain_list.append({"label": label, "modules": mods})
    return domain_list


def _format_primary_ingestion_answer(ing: Any) -> str:
    """Format the Primary ingestion path answer from ingestion hints (for Day-One)."""
    parts = []
    if ing.ingestion_tools:
        parts.append(
            "Data is moved from external systems into the warehouse via "
            + " and ".join(ing.ingestion_tools)
            + "."
        )
    elif ing.orchestrator:
        parts.append("Data is ingested into the warehouse; tooling is configured in the repo.")
    if ing.source_system_hints:
        parts.append("Source systems include " + ", ".join(ing.source_system_hints) + ".")
    if ing.raw_schema_hint:
        parts.append("Raw data lands in " + ing.raw_schema_hint + ".")
    if ing.orchestrator:
        parts.append(ing.orchestrator + " triggers ingestion and pipeline jobs.")
    if ing.config_paths:
        parts.append("Config and pipeline definitions: " + ", ".join(ing.config_paths[:6]) + ".")
    if not parts:
        return ""
    return " ".join(parts)


def _replace_day_one_answer_1(markdown: str, new_answer: str) -> str:
    """Replace the first Day-One answer (Primary ingestion path) with new_answer."""
    if not new_answer.strip():
        return markdown
    # Match "1. Primary ingestion path" or "1. **Primary ingestion path**" and the following paragraph(s) until "2."
    pattern = re.compile(
        r"(1\.\s*\*?\*?Primary ingestion path\*?\*?\s*\n\s*).*?(\n\n2\.|\n2\.)",
        re.DOTALL | re.IGNORECASE,
    )
    replacement = r"\g<1>" + new_answer.strip().replace("\n", "\n   ") + r"\n\2"
    return pattern.sub(replacement, markdown, count=1)


def answer_day_one_questions(
    surveyor_result: Any,
    hydrologist_result: Any,
    llm_provider: LLMProvider,
    *,
    repo_root: Path | str | None = None,
    semanticist_result: Any = None,
    budget: TokenBudget | ContextWindowBudget | None = None,
) -> str:
    """Synthesis prompt with full Surveyor + Hydrologist (and optional Semanticist) output; returns markdown with evidence citations (file paths and line numbers)."""
    context = _build_day_one_context(
        surveyor_result, hydrologist_result, semanticist_result or SemanticistResult(), repo_root=repo_root
    )
    prompt = render_day_one(context)
    in_tok, out_tok = _est_tokens(prompt), 800
    if budget is not None and hasattr(budget, "can_afford") and not budget.can_afford(in_tok, out_tok):
        out = _synthesize_day_one_fallback(
            surveyor_result, hydrologist_result, repo_root=repo_root
        )
    else:
        try:
            out = llm_provider.complete(prompt, max_tokens=800, temperature=0.3, tier="synthesis")
            if budget is not None:
                if hasattr(budget, "record_usage"):
                    budget.record_usage(in_tok, _est_tokens(out))
                else:
                    budget.add(in_tok, _est_tokens(out))
        except Exception as e:
            logger.warning("Day-One synthesis failed: %s", e)
            out = _synthesize_day_one_fallback(
                surveyor_result, hydrologist_result, repo_root=repo_root
            )

    # Force Primary ingestion path from detector when we have hints (so it's never dbt-lineage-only)
    if repo_root:
        from analyzers.ingestion_detector import detect_ingestion
        ing = detect_ingestion(Path(repo_root).resolve())
        if ing.orchestrator or ing.ingestion_tools or ing.config_paths:
            new_answer = _format_primary_ingestion_answer(ing)
            if new_answer:
                out = _replace_day_one_answer_1(out, new_answer)
    return out


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
    budget: TokenBudget | ContextWindowBudget | None = None,
    max_source_lines: int = 80,
    num_domains_min: int = 5,
    num_domains_max: int = 8,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> SemanticistResult:
    """Run full Semanticist pipeline: purpose (code-grounded), drift, domain clustering, Five Day-One Answers.

    Cost discipline: all per-module calls use tier='bulk'; Day-One uses tier='synthesis'.
    progress_callback(done, total, phase) is called periodically so the CLI can show progress.
    """
    root = Path(repo_root).resolve()
    budget = budget or TokenBudget()
    out = SemanticistResult()
    def _can_afford(inc: int, out_t: int) -> bool:
        return budget.can_afford(inc, out_t) if hasattr(budget, "can_afford") else True
    def _add(inc: int, out_t: int) -> None:
        if hasattr(budget, "record_usage"):
            budget.record_usage(inc, out_t)
        else:
            budget.add(inc, out_t)

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
        out.day_one_markdown = _synthesize_day_one_fallback(
            surveyor_result, hydrologist_result, repo_root=root
        )
        return out

    # Only Python modules get purpose statements
    py_items = [(p, m) for p, m in modules.items() if p in source_by_path]
    purpose_total = len(py_items)

    # 1) Purpose statements (code-grounded): only for Python modules
    for idx, (path, metrics) in enumerate(py_items):
        src = source_by_path[path]
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
        if not _can_afford(_est_tokens(prompt), 100):
            logger.warning("Token budget exhausted; skipping purpose for %s", path)
            continue
        try:
            resp = llm_provider.complete(prompt, max_tokens=150, temperature=0.2, tier="bulk")
            out.purpose_statements[path] = resp.strip().split("\n")[0][:500]
            _add(_est_tokens(prompt), _est_tokens(resp))
        except Exception as e:
            logger.warning("Purpose statement failed for %s: %s", path, e)
        if progress_callback and (purpose_total > 0):
            done = idx + 1
            if done % 10 == 0 or done == purpose_total:
                progress_callback(done, purpose_total, "purpose")

    # 2) Documentation drift
    for path, purpose in out.purpose_statements.items():
        src = source_by_path.get(path, "")
        doc = extract_module_docstring(src)
        if not doc:
            out.drift[path] = "insufficient"
            continue
        prompt = render_drift_classification(purpose, doc)
        if not _can_afford(_est_tokens(prompt), 20):
            out.drift[path] = "insufficient"
            continue
        try:
            resp = llm_provider.complete(prompt, max_tokens=30, temperature=0.0, tier="bulk")
            raw = resp.strip().lower().split()[0] if resp.strip() else ""
            if raw in ("aligned", "stale", "contradictory", "insufficient"):
                out.drift[path] = raw
            else:
                out.drift[path] = "insufficient"
            _add(_est_tokens(prompt), _est_tokens(resp))
        except Exception as e:
            logger.warning("Drift classification failed for %s: %s", path, e)
            out.drift[path] = "insufficient"

    # 3) Domain clustering (5–8 domains, readable labels)
    if embeddings_provider and out.purpose_statements:
        out.domains = cluster_into_domains(
            out.purpose_statements,
            embeddings_provider,
            llm_provider=llm_provider,
            budget=budget,
            num_domains_min=num_domains_min,
            num_domains_max=num_domains_max,
        )

    # 4) Day-One synthesis (five answers, evidence citations)
    out.day_one_markdown = answer_day_one_questions(
        surveyor_result,
        hydrologist_result,
        llm_provider,
        repo_root=root,
        semanticist_result=out,
        budget=budget,
    )

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
    *,
    repo_root: Path | str | None = None,
) -> str:
    """Build full architectural context for Day-One synthesis (Surveyor + Hydrologist + Semanticist)."""
    from pathlib import Path
    from analyzers.git_velocity import top_changed_files_all
    from analyzers.ingestion_detector import detect_ingestion

    lines = []
    s = surveyor_result
    h = hydrologist_result

    # FIRST: Ingestion (data into warehouse) so the model sees it before lineage
    if repo_root:
        ing = detect_ingestion(Path(repo_root).resolve())
        ing_parts: list[str] = []
        if ing.ingestion_tools:
            ing_parts.append("Ingestion tools: " + ", ".join(ing.ingestion_tools))
        if ing.orchestrator:
            ing_parts.append("Orchestrator: " + ing.orchestrator)
        if ing.config_paths:
            ing_parts.append("Config/pipeline roots: " + ", ".join(ing.config_paths[:8]))
        if ing.raw_schema_hint:
            ing_parts.append("Raw landing schema (e.g.): " + ing.raw_schema_hint)
        if ing.source_system_hints:
            ing_parts.append("Source system hints: " + ", ".join(ing.source_system_hints))
        if ing_parts:
            lines.append("Ingestion (data into warehouse): " + "; ".join(ing_parts))

    # Raw git velocity (all files with source extensions) - matches filtered git log
    if repo_root:
        raw_top = top_changed_files_all(Path(repo_root).resolve(), days=30, top_n=10)
        if raw_top:
            raw_str = ", ".join(f"{p}({n})" for p, n in raw_top)
            lines.append(f"Raw git velocity (source files, 30d): {raw_str}")

    # Module graph (Surveyor)
    mg = getattr(s, "graph", None)
    if mg is not None:
        lines.append(f"Module graph: {mg.number_of_nodes()} nodes, {mg.number_of_edges()} edges (imports/path refs).")
    mods = getattr(s, "modules", {}) or {}
    if mods:
        velocity = sorted(mods.values(), key=lambda m: getattr(m, "change_velocity_30d", 0), reverse=True)[:8]
        lines.append("Git velocity (30d) among source modules: " + ", ".join(getattr(m, "path", "") for m in velocity))
    pr = getattr(s, "pagerank", {}) or {}
    if pr:
        top = sorted(pr.items(), key=lambda x: -x[1])[:6]
        lines.append("PageRank (top modules): " + ", ".join(f"{p}({v:.3f})" for p, v in top))

    # Lineage graph (Hydrologist)
    g = getattr(h, "graph", None)
    if g is not None:
        lines.append(f"Lineage graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges.")
        sources = find_sources(g)
        sinks = find_sinks(g)
        lines.append("Data lineage sources (no incoming; these are dbt/transform inputs, not necessarily ingestion): " + ", ".join(sorted(sources)[:15]))
        lines.append("Data lineage sinks (no outgoing): " + ", ".join(sorted(sinks)[:15]))
        if sinks:
            critical = next(iter(sorted(sinks)))
            radius = blast_radius(g, critical, max_depth=5)
            lines.append(f"Blast radius from sink '{critical}': {len(radius)} nodes.")
        # Sample edges with source_file for evidence citations
        edge_sample: list[str] = []
        for u, v, attrs in list(g.edges(data=True))[:12]:
            sf = attrs.get("source_file", "")
            ls, le = attrs.get("line_start"), attrs.get("line_end")
            loc = f" @ {sf}:{ls}-{le}" if sf and ls is not None else ""
            edge_sample.append(f"  {u} -> {v}{loc}")
        if edge_sample:
            lines.append("Lineage edges (sample with file:line):")
            lines.extend(edge_sample)

    # Semanticist: purposes and domains
    if sem_result.purpose_statements:
        lines.append("Module purposes (sample): " + "; ".join(f"{p}: {t[:80]}" for p, t in list(sem_result.purpose_statements.items())[:12]))
    if sem_result.domains:
        lines.append("Inferred business domains: " + ", ".join(d.get("label", "") for d in sem_result.domains))
    return "\n".join(lines)


def _synthesize_day_one_fallback(
    surveyor_result: Any, hydrologist_result: Any, *, repo_root: Path | str | None = None
) -> str:
    """Fallback Day-One text when LLM is not used or fails; use actual Surveyor/Hydrologist data when available."""
    s = surveyor_result
    h = hydrologist_result
    g = getattr(h, "graph", None)
    mods = getattr(s, "modules", {}) or {}

    # 1. Primary ingestion path (real ingestion: external → warehouse, not dbt upstream)
    ingestion = "(No ingestion context.)"
    if repo_root:
        from pathlib import Path
        from analyzers.ingestion_detector import detect_ingestion
        ing = detect_ingestion(Path(repo_root).resolve())
        parts = []
        if ing.ingestion_tools:
            parts.append("Data is moved into the warehouse via " + " and ".join(ing.ingestion_tools) + ".")
        if ing.orchestrator:
            parts.append(ing.orchestrator + " triggers ingestion jobs.")
        if ing.config_paths:
            parts.append("Config at: " + ", ".join(ing.config_paths[:5]))
        if ing.raw_schema_hint:
            parts.append("Raw data lands in " + ing.raw_schema_hint + ".")
        if parts:
            ingestion = " ".join(parts)
        elif g is not None:
            sources = find_sources(g)
            ingestion = "Ingestion tooling not detected. Lineage source nodes (dbt/transform inputs): " + (", ".join(sorted(sources)[:8]) if sources else "(none)")
    elif g is not None:
        sources = find_sources(g)
        ingestion = ", ".join(sorted(sources)[:10]) if sources else "(No source nodes.)"

    # 2. Critical outputs/endpoints
    endpoints = "(No lineage graph.)"
    if g is not None:
        sinks = find_sinks(g)
        endpoints = ", ".join(sorted(sinks)[:10]) if sinks else "(No sink nodes.)"

    # 3. Blast radius
    blast = "(No lineage graph.)"
    if g is not None:
        sinks = find_sinks(g)
        if sinks:
            critical = next(iter(sorted(sinks)))
            radius = blast_radius(g, critical, max_depth=5)
            blast = f"Downstream of '{critical}': {len(radius)} nodes affected."

    # 4. Business logic concentrated vs distributed
    concentration = "(No module graph.)"
    if getattr(s, "pagerank", None):
        pr = s.pagerank
        top = sorted(pr.items(), key=lambda x: -x[1])[:3]
        concentration = "Top modules by PageRank: " + ", ".join(f"{p}({v:.3f})" for p, v in top)

    # 5. Git velocity hotspots (raw git + among modules)
    velocity_parts: list[str] = []
    if repo_root:
        from pathlib import Path
        from analyzers.git_velocity import top_changed_files_all
        raw_top = top_changed_files_all(Path(repo_root).resolve(), days=30, top_n=5)
        if raw_top:
            velocity_parts.append("Raw git (source files, 30d): " + ", ".join(f"{p}({n})" for p, n in raw_top))
    if mods:
        hot = sorted(mods.values(), key=lambda m: getattr(m, "change_velocity_30d", 0), reverse=True)[:5]
        velocity_parts.append("Among source modules (30d): " + ", ".join(getattr(m, "path", "") for m in hot))
    velocity = "; ".join(velocity_parts) if velocity_parts else "(No git data.)"

    return "\n\n".join([
        f"1. Primary ingestion path\n{ingestion}",
        f"2. Critical outputs/endpoints\n{endpoints}",
        f"3. Blast radius of critical module\n{blast}",
        f"4. Business logic concentrated vs distributed\n{concentration}",
        f"5. Git velocity hotspots\n{velocity}",
    ])
