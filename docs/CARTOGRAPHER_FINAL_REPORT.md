# Brownfield Cartographer: Final PDF Report

**Report for FDE Day-One Analysis Comparison and Applicability**  
*Target Repository: mitodl/ol-data-platform*

---

## 1. RECONNAISSANCE.md vs. System-Generated Output (`.cartography`): Comparison

### Overview

| Source | Purpose | Method |
|--------|---------|--------|
| **RECONNAISSANCE.md** | Manual Day-One reconnaissance | Human analyst reads repo, docs, and architecture; answers the five FDE questions by hand |
| **`.cartography/`** | System-generated output | Four-agent pipeline (Surveyor → Hydrologist → Semanticist → Archivist) analyzes the repo and writes artifacts automatically |

### Artifacts Compared

- **Manual**: `RECONNAISSANCE.md` — structured answers to the five FDE Day-One questions
- **System**: `.cartography/onboarding_brief.md` (Day-One answers), `.cartography/CODEBASE.md` (architecture, sources/sinks, debt), `.cartography/lineage_graph.json`, `.cartography/module_graph.json`, Pyvis HTML visualizations

### Side-by-Side: Five Day-One Questions

| Question | RECONNAISSANCE.md (Manual) | .cartography (System) | Assessment |
|----------|----------------------------|------------------------|------------|
| **(1) Primary ingestion path** | Airbyte, dlt pipelines from S3, direct API extraction (Canvas, OpenEdX, Sloan), GCS sensors. Raw → S3 → Iceberg → dbt → Superset. Dagster orchestrates. | Airbyte + dbt source generation; Dagster triggers ingestion. Config at `dg_deployments/`, `dg_projects/`, `docker-compose.yaml`. Raw lands in `ol_warehouse_raw`. | **Partially aligned.** Both identify Airbyte and Dagster. Manual adds dlt, GCS sensors, and direct APIs; system emphasizes config locations and graph-derived evidence. |
| **(2) Critical outputs/endpoints** | dbt Marts, Iceberg tables, Superset datasets, S3 exports, Student Risk Probability reports | 5 combined marts: `marts__combined__orders`, `products`, `users`, `course_engagements`, `course_enrollment_detail` | **Aligned.** Both focus on dbt marts. Manual adds Superset, Iceberg, S3, ML outputs; system lists graph-traversal sinks from lineage. |
| **(3) Blast radius of critical module** | dbt Project (`src/ol_dbt/`) as most critical; complete BI outage, 7 code locations, recovery hours–days | `source:ol_warehouse_raw_data` as critical; 698 downstream nodes, 363 sinks | **Different framing.** Manual focuses on dbt (transformation); system on raw source (ingestion). Both valid—raw failure affects all downstream; dbt failure stops BI. |
| **(4) Business logic concentrated vs. distributed** | Concentrated: dbt models (staging/intermediate/marts); Distributed: ingestion (7 Dagster code locations) | Top dirs by PageRank: Superset charts, Trino datasets, dbt staging/intermediate. "Business logic appears fairly distributed" | **Broadly aligned.** Both show dbt as a concentration; system quantifies with PageRank and transformation counts. |
| **(5) Git velocity (90 days)** | uv.lock, pyproject.toml, dbt models, Dockerfiles, shared library | Migration SQL, edxorg_archive.py, Superset cli, reconcile_edxorg_partitions, etc. | **Partially aligned.** Different file sets: manual uses top 20 by commit count; system uses `.py`/`.sql` only. Some overlap (dbt models, Superset). |

### Key Differences

1. **Manual** synthesizes domain knowledge and external context; **system** relies on static analysis, lineage graph, and (when configured) LLM synthesis.
2. **Manual** answers in narrative form; **system** adds confidence scores, evidence citations, and traceable graph references.
3. **System** exposes graph-based metrics (698 nodes, 363 sinks) that a manual analyst would not easily compute.
4. **System** can miss sources not visible in code (e.g., external APIs, manual processes) unless they appear in config or docs.

---

## 2. Architecture Diagram: Four-Agent Pipeline (Finalized)

The Brownfield Cartographer processes a repository through a four-agent analysis pipeline, followed by a query layer:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         REPOSITORY INPUT                                          │
│  Local path or GitHub URL (--branch optional)                                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     REPOSITORY LOADER + FILE DISCOVERY                            │
│  • Clone from GitHub (temporary dir) or use local path                            │
│  • discover_files(): .py, .sql, .yaml, .yml, .json, .md, .ipynb                   │
│  • Content hashing for incremental detection                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         AGENT 1: SURVEYOR                                         │
│  Static structural analysis (tree-sitter, git, NetworkX)                          │
│  Outputs: DiGraph (imports), modules dict, PageRank, SCCs, dead-code flags        │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │ SurveyorResult
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        AGENT 2: HYDROLOGIST                                       │
│  Mixed-language data lineage (Python dataflow, SQL, YAML/DAG config)              │
│  Outputs: DiGraph (lineage), find_sources, find_sinks, blast_radius               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │ HydrologistResult
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       AGENT 3: SEMANTICIST (optional)                             │
│  LLM-powered: purpose statements, doc drift, domain clustering, Day-One answers   │
│  Requires: DEEPSEEK_API_KEY in .env                                               │
│  Outputs: purpose_statements, drift, domains, day_one_markdown                    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │ SemanticistResult
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        AGENT 4: ARCHIVIST                                         │
│  Serializes all outputs into .cartography/ artifacts                              │
│  Outputs: CODEBASE.md, onboarding_brief.md, module_graph.json, lineage_graph.json │
│           cartography_trace.jsonl, module_graph.html, lineage_graph.html          │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         NAVIGATOR (query layer)                                   │
│  Reads persisted artifacts; no re-analysis. Four tools:                           │
│  find_implementation, trace_lineage, blast_radius, explain_module                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Agent Responsibilities (Summary)

| Agent | Role | Key Outputs |
|-------|------|-------------|
| **Surveyor** | Structural analysis of Python modules | Import graph, PageRank, SCCs, dead-code candidates, git velocity |
| **Hydrologist** | Cross-language data lineage | Lineage graph (sources → transforms → sinks), blast radius |
| **Semanticist** | Semantic inference (when LLM configured) | Purpose statements, documentation drift, domain clustering, Day-One synthesis |
| **Archivist** | Persistence and formatting | `CODEBASE.md`, `onboarding_brief.md`, JSON graphs, Pyvis HTML, trace logs |
| **Navigator** | Query interface | `find_implementation`, `trace_lineage`, `blast_radius`, `explain_module` |

---

## 3. Accuracy Analysis: Which Day-One Answers Were Correct, Wrong, and Why

### Correct or Strongly Aligned

| Answer | Verdict | Why |
|--------|---------|-----|
| **Q1 (Ingestion path)** | Correct in substance | Both identify Airbyte, Dagster, and dbt; system correctly points to `dg_deployments/` and `docker-compose.yaml`. System misses dlt, GCS sensors, and direct APIs that require broader config/doc reading. |
| **Q2 (Critical outputs)** | Correct | System’s five combined marts match the manual’s dbt Marts; both rely on lineage to identify sinks. System omits Superset, Iceberg, S3, and ML outputs that are conceptual endpoints rather than lineage nodes. |
| **Q3 (Blast radius)** | Correct, different focus | System’s 698 nodes / 363 sinks for `ol_warehouse_raw_data` is graph-consistent. Manual focuses on dbt; both are valid interpretations of “most critical module.” |
| **Q4 (Concentrated vs. distributed)** | Correct | System’s PageRank and transformation counts align with the manual’s “dbt concentrated, ingestion distributed” view. |

### Partially Correct or Incomplete

| Answer | Issue | Why |
|--------|-------|-----|
| **Q1** | Missing dlt, GCS sensors, direct APIs | These appear in docs and config; ingestion detector emphasizes Airbyte and Dagster. |
| **Q2** | Omits Superset, Iceberg, S3, Student Risk reports | Lineage focuses on dbt; Superset/Iceberg are deployment/consumption, not transformation nodes. |
| **Q5 (Git velocity)** | Different file set | Manual’s top 20 includes uv.lock, pyproject.toml; system filters to `.py`/`.sql`. Both reflect active areas, but manual is broader. |

### Not Wrong but Differently Framed

| Answer | Observation | Why |
|--------|-------------|-----|
| **Q3** | Manual: dbt critical; System: raw source critical | Manual focuses on transformation failure; system on source failure. Both are correct for their respective definitions. |
| **Q4** | Manual: “fairly distributed”; System: quantifies with PageRank | Same conclusion; system adds numeric evidence. |

### Root Causes of Gaps

1. **Ingestion detector** is tuned for Airbyte, Dagster, docker-compose; dlt, GCS, and custom APIs need additional patterns.
2. **Lineage graph** models transformations and dataset nodes; Superset and Iceberg are consumer layers, not modeled as first-class sinks.
3. **Git velocity** restricts to source files; lock and config files are excluded by design.
4. **“Critical module”** is not uniquely defined; system defaults to the largest graph component (raw source); manual uses business impact (dbt).

---

## 4. Limitations: What the Cartographer Fails to Understand, and What Remains Opaque

### Structural and Parsing Limits

| Limitation | Description |
|------------|-------------|
| **dbt/Jinja SQL** | sqlglot cannot parse Jinja. Regex fallback preserves `ref()` and `source()` but not full CTE/join structure. Templated SQL yields partial lineage. |
| **Module graph scope** | Only Python modules appear. SQL, YAML, and config files are lineage nodes but not module-graph nodes. |
| **Dynamic imports** | `importlib`, `__import__`, path-based imports are often unresolved. |
| **Dynamic paths** | F-strings and variables in `read_csv`, `read_sql`, etc. become unresolved references. |

### Semantic and Context Limits

| Limitation | Description |
|------------|-------------|
| **External systems** | APIs, webhooks, and manual processes not reflected in code/config are invisible. |
| **Run-time behavior** | Actual schedules, retries, and failure modes are not modeled. |
| **Business meaning** | System identifies structure and flow, not which datasets are “most important” for stakeholders. |
| **Documentation drift** | Detected only for modules with docstrings; many modules have none. |

### Operational Limits

| Limitation | Description |
|------------|-------------|
| **Semanticist off by default** | Requires `DEEPSEEK_API_KEY`; without it, purpose index and Day-One synthesis fall back to static/graph-only. |
| **Full incremental** | Any file change invalidates the whole run; no per-file or per-component partial re-analysis. |
| **Navigator** | Four discrete tools; no multi-step reasoning or planning. |

### What Remains Opaque

- **Upstream systems**: Databases, APIs, and object stores not referenced in the repo.
- **Deployment topology**: Which components run where, scaling, and environment-specific config.
- **Ownership and SLAs**: Who maintains what, SLOs, and incident response.
- **Historical evolution**: Rationale for past design and migration choices.

---

## 5. FDE Applicability: Using the Cartographer in a Real Client Engagement

**How to use the Brownfield Cartographer in a real client engagement:**

The Cartographer is built for **brownfield FDE onboarding**: situations where documentation is outdated, architecture is unclear, and engineers need a fast, evidence-based mental model of the system. In a real client engagement, run the Cartographer on the client’s repository as soon as access is granted—ideally before or during Day One of the engagement. Use the `analyze` command to produce the `.cartography` artifacts (including `onboarding_brief.md` and `CODEBASE.md`), then open the Pyvis visualizations to explore module dependencies and data lineage. Treat the five Day-One answers as a starting checklist: use them to validate with the client’s team, identify gaps (e.g., missing ingestion paths, undocumented critical datasets), and prioritize interviews and deep dives. The Navigator’s `find_implementation`, `trace_lineage`, and `blast_radius` tools support rapid queries during discovery sessions. Combine the Cartographer’s graph-derived insights with client knowledge to build an accurate architectural picture. The tool does not replace human judgment or stakeholder input; it reduces the time needed to reach a useful operational understanding and highlights areas where the codebase and documentation diverge.

---

## Appendix: Artifact Locations

| Artifact | Path |
|----------|------|
| Manual reconnaissance | `RECONNAISSANCE.md` |
| System Day-One answers | `.cartography/onboarding_brief.md` |
| System architecture | `.cartography/CODEBASE.md` |
| Module graph (JSON) | `.cartography/module_graph.json` |
| Lineage graph (JSON) | `.cartography/lineage_graph.json` |
| Module graph (HTML) | `.cartography/module_graph.html` |
| Lineage graph (HTML) | `.cartography/lineage_graph.html` |
| Trace log | `.cartography/cartography_trace.jsonl` |

---

*End of Report*
