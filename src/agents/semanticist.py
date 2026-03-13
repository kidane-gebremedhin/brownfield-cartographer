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

from agents.hydrologist import blast_radius, find_sources, find_sinks, trace_lineage
from models.artifacts import DayOneAnswer
from models.common import Evidence
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
    paths_to_show = getattr(ing, "entry_point_paths", None) or ing.config_paths
    if paths_to_show:
        parts.append("Entry points: " + ", ".join(paths_to_show[:10]) + ".")
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
) -> tuple[list[DayOneAnswer], str]:
    """Build structured Day-One answers (with evidence) and render markdown.

    This implementation is deterministic and does not rely on the LLM. The llm_provider and
    budget parameters are accepted for API compatibility but are not used here.
    """
    sem_res = semanticist_result or SemanticistResult()
    answers = _build_structured_day_one_answers(
        surveyor_result=surveyor_result,
        hydrologist_result=hydrologist_result,
        sem_result=sem_res,
        repo_root=repo_root,
    )
    markdown = _render_day_one_markdown_from_answers(answers)

    # Preserve the ingestion-detector override for answer 1 wording when we have hints.
    if repo_root:
        from analyzers.ingestion_detector import detect_ingestion

        ing = detect_ingestion(Path(repo_root).resolve())
        if ing.orchestrator or ing.ingestion_tools or ing.config_paths:
            new_answer = _format_primary_ingestion_answer(ing)
            if new_answer:
                markdown = _replace_day_one_answer_1(markdown, new_answer)
    return answers, markdown


@dataclass
class SemanticistResult:
    """Output of run_semanticist."""

    purpose_statements: dict[str, str] = field(default_factory=dict)
    drift: dict[str, DriftLabel] = field(default_factory=dict)
    domains: list[dict[str, Any]] = field(default_factory=list)  # [{ "label": str, "modules": [path, ...] }]
    day_one_markdown: str = ""
    day_one_answers: list[DayOneAnswer] = field(default_factory=list)


@dataclass(frozen=True)
class CriticalNodeScore:
    """Scored candidate for 'most critical' internal lineage node."""

    node_id: str
    score: float
    downstream_reach: int
    upstream_reach: int
    degree: int
    pagerank: float
    bonus_tags: list[str]


def score_critical_candidates(graph: Any, surveyor_result: Any) -> list[CriticalNodeScore]:
    """Rank non-empty, internal lineage nodes by structural importance.

    Excludes:
    - empty / whitespace-only node ids
    - unresolved placeholder nodes (node_type='unresolved')
    - pure terminal sinks (no outgoing edges and not a transformation)
    """
    if graph is None:
        return []

    pr_map: dict[str, float] = getattr(surveyor_result, "pagerank", {}) or {}

    def _pagerank_for_node(node_id: str) -> float:
        if node_id in pr_map:
            return float(pr_map[node_id])
        # Transformation ids often look like "py:path" or "sql:path"
        if ":" in node_id:
            _, path = node_id.split(":", 1)
            return float(pr_map.get(path, 0.0))
        return 0.0

    results: list[CriticalNodeScore] = []

    for node_id in graph.nodes():
        # We only reason about string-like node ids
        if not isinstance(node_id, str):
            continue
        if not node_id.strip():
            continue

        attrs = graph.nodes[node_id] or {}
        node_type = attrs.get("node_type")

        # Skip unresolved placeholder nodes
        if node_type == "unresolved":
            continue

        in_deg = graph.in_degree(node_id)
        out_deg = graph.out_degree(node_id)

        # Skip isolated points
        if in_deg == 0 and out_deg == 0:
            continue

        # Exclude pure terminal sinks (no outgoing edges and not a transformation)
        if out_deg == 0 and node_type != "transformation":
            continue

        # Reachability within bounded depth for determinism and performance
        downstream_nodes = blast_radius(graph, node_id, max_depth=5)
        downstream_reach = max(0, len(downstream_nodes) - 1)

        upstream_nodes = trace_lineage(graph, node_id, direction="upstream", max_depth=5)
        upstream_reach = max(0, len(upstream_nodes) - 1)

        degree = int(in_deg + out_deg)
        pr_value = _pagerank_for_node(node_id)

        bonus_tags: list[str] = []
        nid_lower = node_id.lower()
        if "marts/" in nid_lower or "marts." in nid_lower:
            bonus_tags.append("marts")
        if "reporting/" in nid_lower or "reporting." in nid_lower:
            bonus_tags.append("reporting")
        if "intermediate/" in nid_lower or "intermediate." in nid_lower:
            bonus_tags.append("intermediate")

        orchestrator_keywords = ("dagster", "airflow", "orchestrate", "prefect", "scheduler")
        if any(k in nid_lower for k in orchestrator_keywords):
            bonus_tags.append("orchestrator")

        # Weighted score components
        score = (
            2.0 * downstream_reach
            + 1.5 * upstream_reach
            + degree
            + 50.0 * pr_value
            + 5.0 * len(bonus_tags)
        )

        results.append(
            CriticalNodeScore(
                node_id=node_id,
                score=score,
                downstream_reach=downstream_reach,
                upstream_reach=upstream_reach,
                degree=degree,
                pagerank=pr_value,
                bonus_tags=bonus_tags,
            )
        )

    # Deterministic ordering: score desc, then node id asc
    return sorted(results, key=lambda c: (-c.score, c.node_id))


def analyze_business_logic_distribution(surveyor_result: Any, hydrologist_result: Any) -> dict[str, Any]:
    """Compute where business logic is concentrated vs distributed across directories and layers."""
    s = surveyor_result
    h = hydrologist_result
    g = getattr(h, "graph", None)
    modules = getattr(s, "modules", {}) or {}
    pagerank = getattr(s, "pagerank", {}) or {}

    from collections import Counter, defaultdict

    dir_module_counts: Counter[str] = Counter()
    dir_pagerank: Counter[str] = Counter()
    dir_transformations: Counter[str] = Counter()

    layer_prefixes = {
        "staging": ("staging/", "staging."),
        "intermediate": ("intermediate/", "intermediate."),
        "marts": ("marts/", "marts."),
        "reporting": ("reporting/", "reporting."),
        "dg_deployments": ("dg_deployments/",),
        "dg_projects": ("dg_projects/",),
        "packages": ("packages/",),
    }
    layer_stats: dict[str, dict[str, float]] = defaultdict(
        lambda: {"modules": 0.0, "pagerank": 0.0, "transformations": 0.0}
    )

    for path, _metrics in modules.items():
        if not isinstance(path, str):
            continue
        parts = path.split("/")
        d = "/".join(parts[:-1]) if len(parts) > 1 else "."
        dir_module_counts[d] += 1
        pr_val = float(pagerank.get(path, 0.0))
        dir_pagerank[d] += pr_val
        for layer, prefixes in layer_prefixes.items():
            if any(path.startswith(p) for p in prefixes):
                layer_stats[layer]["modules"] += 1
                layer_stats[layer]["pagerank"] += pr_val

    if g is not None:
        for _u, _v, attrs in g.edges(data=True):
            sf = attrs.get("source_file")
            if not sf:
                continue
            parts = sf.split("/")
            d = "/".join(parts[:-1]) if len(parts) > 1 else "."
            dir_transformations[d] += 1
            for layer, prefixes in layer_prefixes.items():
                if any(sf.startswith(p) for p in prefixes):
                    layer_stats[layer]["transformations"] += 1

    dir_module_top = dir_module_counts.most_common(6)
    dir_pagerank_top = dir_pagerank.most_common(6)
    dir_transform_top = dir_transformations.most_common(6)

    concentration_notes: list[str] = []
    if dir_pagerank_top:
        top_dir, top_pr = dir_pagerank_top[0]
        total_pr = sum(v for _, v in dir_pagerank_top) or 1.0
        ratio = top_pr / total_pr
        if ratio > 0.6:
            concentration_notes.append(
                f"Business logic is highly centralized in `{top_dir}` (≈{ratio:.0%} of PageRank among top directories)."
            )
        elif ratio > 0.3:
            concentration_notes.append(
                f"Business logic is moderately concentrated in `{top_dir}`, with meaningful activity elsewhere."
            )
        else:
            concentration_notes.append(
                "Business logic appears fairly distributed across multiple directories."
            )

    if g is not None:
        total_edges = g.number_of_edges() or 1
        for layer, stats in layer_stats.items():
            if stats["transformations"] > 0:
                frac = stats["transformations"] / total_edges
                concentration_notes.append(
                    f"Layer `{layer}` accounts for ≈{frac:.0%} of lineage transformations."
                )

    return {
        "dir_module_counts": dir_module_top,
        "dir_pagerank": dir_pagerank_top,
        "dir_transformations": dir_transform_top,
        "layer_counts": layer_stats,
        "concentration_notes": concentration_notes,
    }


def _score_critical_output_node(node_id: str, attrs: dict[str, Any]) -> float:
    """Score a sink node as a candidate critical output."""
    nid = node_id.lower()
    score = 0.0
    if "marts" in nid or "mart" in nid:
        score += 3.0
    if "reporting" in nid:
        score += 3.0
    if "analytics" in nid:
        score += 2.0
    if "superset" in nid or "dashboard" in nid or "bi_" in nid:
        score += 2.0
    if "raw__" in nid or "raw_" in nid:
        score -= 4.0
    if "source(" in nid or attrs.get("node_type") == "source":
        score -= 3.0
    return score


def select_critical_outputs(graph: Any, max_outputs: int = 5) -> list[str]:
    """Select 3–5 critical outputs/endpoints (analytics/reporting/BI-facing)."""
    if graph is None:
        return []
    sinks = find_sinks(graph)
    scored: list[tuple[float, str]] = []
    for n in sinks:
        attrs = graph.nodes.get(n, {}) if hasattr(graph, "nodes") else {}
        s = _score_critical_output_node(n, attrs)
        scored.append((s, n))
    # prefer higher score; break ties alphabetically
    scored.sort(key=lambda x: (-x[0], x[1]))
    # filter out heavily penalized raw/source-only sinks when possible
    positive = [n for s, n in scored if s > 0]
    chosen = positive[:max_outputs] if positive else [n for _s, n in scored[:max_outputs]]
    return chosen


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
    answers, markdown = answer_day_one_questions(
        surveyor_result,
        hydrologist_result,
        llm_provider,
        repo_root=root,
        semanticist_result=out,
        budget=budget,
    )
    out.day_one_answers = answers
    out.day_one_markdown = markdown

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

    # Structural critical node summary (for human context; independent of LLM)
    if g is not None:
        scored = score_critical_candidates(g, s)
        if scored:
            top = scored[0]
            impact_nodes = blast_radius(g, top.node_id, max_depth=5)
            impact_nodes.discard(top.node_id)
            evidence_bits: list[str] = [
                f"upstream_reach={top.upstream_reach}",
                f"downstream_reach={top.downstream_reach}",
                f"degree={top.degree}",
            ]
            if top.pagerank > 0:
                evidence_bits.append(f"pagerank={top.pagerank:.3f}")
            if top.bonus_tags:
                evidence_bits.append("tags=" + ",".join(sorted(top.bonus_tags)))
            lines.append(
                "Critical internal lineage node: "
                f"{top.node_id} "
                f"(blast radius: {len(impact_nodes)} nodes; "
                + ", ".join(evidence_bits)
                + ")."
            )

    return "\n".join(lines)


def _synthesize_day_one_fallback(
    surveyor_result: Any, hydrologist_result: Any, *, repo_root: Path | str | None = None
) -> str:
    """Fallback Day-One text when LLM is not used or fails; uses structured answers."""
    answers = _build_structured_day_one_answers(
        surveyor_result=surveyor_result,
        hydrologist_result=hydrologist_result,
        sem_result=SemanticistResult(),
        repo_root=repo_root,
    )
    return _render_day_one_markdown_from_answers(answers)


def _build_structured_day_one_answers(
    surveyor_result: Any,
    hydrologist_result: Any,
    sem_result: SemanticistResult,
    *,
    repo_root: Path | str | None = None,
) -> list[DayOneAnswer]:
    """Build five Day-One answers backed by static analysis and graph traversal."""
    from analyzers.git_velocity import top_changed_files_all
    from analyzers.ingestion_detector import detect_ingestion

    s = surveyor_result
    h = hydrologist_result
    g = getattr(h, "graph", None)
    mods = getattr(s, "modules", {}) or {}

    answers: list[DayOneAnswer] = []

    # 1. Primary ingestion path (external -> warehouse)
    ingestion_text = "(No ingestion context.)"
    ingestion_evidence: list[Evidence] = []
    if repo_root:
        root = Path(repo_root).resolve()
        ing = detect_ingestion(root)
        parts = []
        if ing.ingestion_tools:
            parts.append("Data is moved into the warehouse via " + " and ".join(ing.ingestion_tools) + ".")
        if ing.orchestrator:
            parts.append(ing.orchestrator + " triggers ingestion jobs.")
        if ing.config_paths:
            parts.append("Config at: " + ", ".join(ing.config_paths[:5]))
        if ing.raw_schema_hint:
            parts.append("Raw data lands in " + ing.raw_schema_hint + ".")
        # Map ingestion detector evidence into structured Evidence objects
        for iev in getattr(ing, "evidence", [])[:50]:
            ingestion_evidence.append(
                Evidence(
                    source="ingestion_detector",
                    file_path=iev.file_path,
                    line_start=iev.line,
                    line_end=iev.line,
                    analysis_method="static_analysis",
                    notes=f"{iev.category} match: {iev.keyword}",
                )
            )
        if parts:
            ingestion_text = " ".join(parts)
        elif g is not None:
            sources = find_sources(g)
            ingestion_text = "Ingestion tooling not detected. Lineage source nodes (dbt/transform inputs): " + (
                ", ".join(sorted(sources)[:8]) if sources else "(none)"
            )
            for src in sorted(list(sources))[:8]:
                for u, v, attrs in g.out_edges(src, data=True):
                    sf = attrs.get("source_file")
                    ls, le = attrs.get("line_start"), attrs.get("line_end")
                    if sf and ls is not None and le is not None:
                        ingestion_evidence.append(
                            Evidence(
                                source="hydrologist",
                                file_path=sf,
                                line_start=ls,
                                line_end=le,
                                analysis_method="graph_traversal",
                                notes=f"Source dataset {src} feeding {v}",
                            )
                        )
    elif g is not None:
        sources = find_sources(g)
        ingestion_text = ", ".join(sorted(sources)[:10]) if sources else "(No source nodes.)"

    answers.append(
        DayOneAnswer(
            question_id=1,
            title="Primary ingestion path",
            answer_markdown=ingestion_text,
            confidence=0.8,
            method="mixed" if ingestion_evidence else "static_analysis",
            evidence=ingestion_evidence,
        )
    )

    # 2. Critical outputs/endpoints (prefer marts/reporting/analytics/BI)
    endpoints_text = "(No lineage graph.)"
    endpoints_evidence: list[Evidence] = []
    if g is not None:
        critical_nodes = select_critical_outputs(g, max_outputs=5)
        if critical_nodes:
            endpoints_text = ", ".join(critical_nodes)
            for sink in critical_nodes:
                for u, v, attrs in g.in_edges(sink, data=True):
                    sf = attrs.get("source_file")
                    ls, le = attrs.get("line_start"), attrs.get("line_end")
                    if sf and ls is not None and le is not None:
                        endpoints_evidence.append(
                            Evidence(
                                source="hydrologist",
                                file_path=sf,
                                line_start=ls,
                                line_end=le,
                                analysis_method="graph_traversal",
                                notes=f"Transformation edge {u} -> {v}",
                            )
                        )
        else:
            endpoints_text = "(No sink nodes.)"

    answers.append(
        DayOneAnswer(
            question_id=2,
            title="Critical outputs/endpoints",
            answer_markdown=endpoints_text,
            confidence=0.8 if g is not None else 0.3,
            method="graph_traversal" if g is not None else "static_analysis",
            evidence=endpoints_evidence,
        )
    )

    # 3. Blast radius of critical module/transformation
    blast_text = "(No lineage graph.)"
    blast_evidence: list[Evidence] = []
    if g is not None:
        scored = score_critical_candidates(g, s)
        if scored:
            top = scored[0]
            radius = blast_radius(g, top.node_id, max_depth=5)
            impact_nodes = set(radius)
            impact_nodes.discard(top.node_id)

            # classify downstream impacts
            downstream_sinks = {n for n in impact_nodes if g.out_degree(n) == 0}
            reporting_like = {n for n in downstream_sinks if "reporting" in str(n).lower() or "mart" in str(n).lower()}

            blast_lines = [
                f"Critical module or transformation: `{top.node_id}`.",
                f"Downstream blast radius (excluding the node itself): {len(impact_nodes)} nodes.",
                f"Affected output datasets: {len(downstream_sinks)} sinks.",
            ]
            if reporting_like:
                blast_lines.append(f"Impacted reporting/analytics layers include: {', '.join(sorted(list(reporting_like))[:8])}.")
            blast_text = "\n".join(blast_lines)

            for u, v, attrs in g.edges(data=True):
                if u == top.node_id or (u in impact_nodes and v in impact_nodes):
                    sf = attrs.get("source_file")
                    ls, le = attrs.get("line_start"), attrs.get("line_end")
                    if sf and ls is not None and le is not None:
                        blast_evidence.append(
                            Evidence(
                                source="hydrologist",
                                file_path=sf,
                                line_start=ls,
                                line_end=le,
                                analysis_method="graph_traversal",
                                notes=f"Blast-radius edge {u} -> {v}",
                            )
                        )
        else:
            sinks = find_sinks(g)
            if sinks:
                critical = next(iter(sorted(sinks)))
                radius = blast_radius(g, critical, max_depth=5)
                impact_nodes = set(radius)
                impact_nodes.discard(critical)
                blast_text = (
                    f"Sink-only graph; using terminal node '{critical}'. "
                    f"Downstream blast radius (excluding the node itself): {len(impact_nodes)} nodes."
                )

    answers.append(
        DayOneAnswer(
            question_id=3,
            title="Blast radius of critical module",
            answer_markdown=blast_text,
            confidence=0.8 if g is not None else 0.3,
            method="graph_traversal" if g is not None else "static_analysis",
            evidence=blast_evidence,
        )
    )

    # 4. Business logic concentrated vs distributed (directories, layers, lineage)
    concentration_text = "(No module graph.)"
    concentration_evidence: list[Evidence] = []
    if getattr(s, "modules", None):
        dist = analyze_business_logic_distribution(s, h)
        lines: list[str] = []

        dir_mod = dist.get("dir_module_counts") or []
        dir_pr = dist.get("dir_pagerank") or []
        dir_tr = dist.get("dir_transformations") or []
        layer_counts = dist.get("layer_counts") or {}
        notes = dist.get("concentration_notes") or []

        if dir_mod:
            lines.append("Top directories by module count:")
            for d, c in dir_mod:
                lines.append(f"- `{d}`: {c} modules")
                concentration_evidence.append(
                    Evidence(
                        source="surveyor",
                        file_path=d,
                        analysis_method="static_analysis",
                        notes=f"{c} modules under {d}",
                    )
                )

        if dir_pr:
            lines.append("Top directories by PageRank-weighted importance:")
            for d, pr_val in dir_pr:
                lines.append(f"- `{d}`: total PageRank ≈ {pr_val:.3f}")

        if dir_tr:
            lines.append("Top directories by lineage transformations:")
            for d, c in dir_tr:
                lines.append(f"- `{d}`: {c} transformation edges")

        if layer_counts:
            lines.append("Path-based layers (staging/intermediate/marts/reporting/dg_*/packages):")
            for layer, stats in layer_counts.items():
                if stats["modules"] or stats["transformations"]:
                    lines.append(
                        f"- `{layer}`: modules={int(stats['modules'])}, "
                        f"transformations={int(stats['transformations'])}, "
                        f"PageRank≈{stats['pagerank']:.3f}"
                    )

        for note in notes:
            lines.append(note)

        if lines:
            concentration_text = "\n".join(lines)

    answers.append(
        DayOneAnswer(
            question_id=4,
            title="Business logic concentrated vs distributed",
            answer_markdown=concentration_text,
            confidence=0.8 if getattr(s, "modules", None) else 0.4,
            method="static_analysis",
            evidence=concentration_evidence,
        )
    )

    # 5. Git velocity hotspots (raw git + among modules) over 90 days
    from analyzers.git_velocity import build_git_velocity_map

    velocity_lines: list[str] = []
    velocity_evidence: list[Evidence] = []
    window_days = 90

    if repo_root:
        root = Path(repo_root).resolve()
        vmap = build_git_velocity_map(root, days=window_days)
        files = vmap.get("files", [])
        dirs = vmap.get("directories", [])
        prefixes = vmap.get("prefixes", [])

        if files:
            velocity_lines.append(
                f"Top changed files in the last {window_days} days:"
            )
            for path, count in files:
                velocity_lines.append(f"- `{path}`: {count} commits")
                velocity_evidence.append(
                    Evidence(
                        source="git_velocity",
                        file_path=path,
                        analysis_method="static_analysis",
                        notes=f"{count} commits in last {window_days} days",
                    )
                )

        if dirs:
            velocity_lines.append(
                f"Top changed directories in the last {window_days} days:"
            )
            for d, count in dirs:
                velocity_lines.append(f"- `{d}/`: {count} commits (aggregated)")

        if prefixes:
            velocity_lines.append(
                f"Top changed subsystems in the last {window_days} days:"
            )
            for prefix, count in prefixes:
                velocity_lines.append(f"- `{prefix}`: {count} commits (aggregated)")

    if mods:
        hot = sorted(
            mods.values(), key=lambda m: getattr(m, "change_velocity_90d", 0), reverse=True
        )[:5]
        if hot:
            velocity_lines.append(
                f"Among source modules (90d change_velocity_90d): "
                + ", ".join(getattr(m, "path", "") for m in hot)
            )
            for m in hot:
                velocity_evidence.append(
                    Evidence(
                        source="git_velocity",
                        file_path=getattr(m, "path", ""),
                        analysis_method="static_analysis",
                        notes=f"Module change velocity 90d={getattr(m, 'change_velocity_90d', 0)}",
                    )
                )

    velocity_text = "\n".join(velocity_lines) if velocity_lines else "(No git data.)"

    answers.append(
        DayOneAnswer(
            question_id=5,
            title="Git velocity hotspots (last 90 days)",
            answer_markdown=velocity_text,
            confidence=0.8 if velocity_lines else 0.4,
            method="static_analysis",
            evidence=velocity_evidence,
        )
    )

    return answers


def _render_day_one_markdown_from_answers(answers: list[DayOneAnswer]) -> str:
    """Render legacy Day-One markdown from structured answers."""
    by_q = {a.question_id: a for a in answers}
    sections = []
    for q in sorted(by_q.keys()):
        a = by_q[q]
        sections.append(f"{q}. {a.title}\n{a.answer_markdown}")
    return "\n\n".join(sections)
