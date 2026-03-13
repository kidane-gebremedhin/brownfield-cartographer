# Brownfield Cartographer: Implementation Interim Report

## Project Summary
---


The Brownfield Cartographer is a multi-agent codebase intelligence system designed to accelerate onboarding into large, unfamiliar software systems. The tool analyzes a repository and produces a structured, queryable map of its architecture, data flows, and operational hotspots, allowing engineers to understand complex codebases more quickly and reliably.

Modern production repositories often lack up-to-date documentation, making it difficult for engineers to determine where core functionality resides, how data moves through the system, and which components are most critical. The Brownfield Cartographer addresses this problem by automatically extracting structural and semantic knowledge from the codebase and organizing it into a knowledge graph and navigable artifact set.

The system processes repositories through a four-agent analysis pipeline:

Surveyor performs static structural analysis using tree-sitter and builds a module dependency graph, identifying architectural hubs, circular dependencies, and potential dead-code candidates.

Hydrologist reconstructs data lineage across Python, SQL, YAML, and configuration files, producing a unified graph that reveals how datasets are produced, transformed, and consumed across the system.

Semanticist applies language models to generate code-grounded module purpose statements, detect documentation drift, cluster modules into functional domains, and synthesize high-level onboarding insights.

Archivist persists all results into a durable artifact set including architecture documentation, lineage graphs, and interactive visualizations.

These artifacts are then exposed through the Navigator query layer, which allows engineers to ask practical questions about the codebase such as:

- where a feature is implemented
- how a dataset flows through the system
- which modules would be impacted by a change
- what role a given module plays in the overall architecture

The system outputs both machine-readable artifacts (JSON graphs and trace logs) and human-readable documentation (CODEBASE.md and onboarding briefs). Interactive visualizations generated with Pyvis provide a quick way to explore module dependencies and data lineage directly in the browser.

By combining static analysis, graph-based reasoning, and semantic inference, the Brownfield Cartographer transforms a repository into a living architectural map. This enables faster debugging, safer system modifications, and significantly shorter ramp-up times for engineers working in complex brownfield environments.

---

## 1. Architecture Diagram: Four-Agent Pipeline with Data Flow

### Overview

The Brownfield Cartographer is a multi-agent codebase intelligence system. The pipeline ingests a repository (local path or GitHub URL) and produces a living, queryable map of architecture, data flows, and semantic structure. Data flows sequentially through four analysis agents before being persisted and exposed for querying.


### Pipeline Architecture (ASCII Diagram)

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
│  Requires: DEEPSEEK_API_KEY in .env                                                │
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

### Detailed Data Flow

**Repository Loader** resolves the input to a local directory. For GitHub URLs it clones into a temporary directory; for local paths it uses the path directly. The loader enforces that clones never occur in the working tree.

**File Discovery** walks the repo and collects supported file types (`.py`, `.sql`, `.yaml`, `.yml`, `.json`, `.md`, `.ipynb`), skipping `.git`, `__pycache__`, `venv`, `node_modules`, etc. Each file gets a content hash for incremental invalidation.

**Surveyor** consumes the file set and builds the module import graph. For each Python file it runs tree-sitter to extract imports, public functions, and classes with inheritance. It resolves imports to repo-relative paths and adds directed edges. Git velocity (30/90 day commit counts) is computed per file; PageRank identifies architectural hubs; strongly connected components expose circular dependencies. Modules with no incoming edges and non-trivial public API (excluding main/cli/__init__) are flagged as dead-code candidates. Output: `SurveyorResult(graph, modules, pagerank, sccs)`.

**Hydrologist** constructs the lineage graph from Python, SQL, YAML, and notebook sources. Python dataflow analyzer finds `pandas.read_csv`, `read_sql`, SQLAlchemy, PySpark patterns. SQL lineage uses sqlglot with dialect support (postgres, bigquery, snowflake, duckdb) and preserves dbt `ref()`/`source()` when full parse fails. YAML/DAG config parser extracts dbt schema and pipeline topology. All flows merge into a single DiGraph with node types (dataset, transformation, unresolved) and edge types (consumes, produces, configures, depends_on). Unresolved references are retained explicitly. Output: `HydrologistResult(graph)` with helper methods for sources, sinks, blast radius.

**Semanticist** runs only when an LLM provider is configured (via `DEEPSEEK_API_KEY` in `.env`). It consumes Surveyor and Hydrologist outputs. For each Python module it generates a code-grounded purpose statement (not from docstring), then classifies documentation drift (aligned, stale, contradictory, insufficient). Purpose statements are embedded and clustered into 5–8 domains via k-means; each cluster gets an LLM-generated label. A synthesis prompt produces the five Day-One answers with evidence citations. All LLM calls use the DeepSeek API (bulk and synthesis tiers configurable via CARTOGRAPHER_DEEPSEEK_MODEL and CARTOGRAPHER_SYNTHESIS_MODEL).

**Archivist** writes all artifacts deterministically. `CODEBASE.md` includes Architecture Overview, Critical Path (top 5 PageRank), Data Sources & Sinks, Known Debt (SCCs, dead-code candidates, doc drift), High-Velocity Files, and Module Purpose Index. `onboarding_brief.md` contains Day-One answers, evidence citations, confidence notes, and known unknowns. JSON graphs use a stable schema. `cartography_trace.jsonl` logs agent actions with evidence and confidence. Pyvis HTML visualizations are generated when available.

**Navigator** operates purely from persisted `.cartography/` artifacts. It provides four tools that combine graph traversal with semantic search (when CODEBASE.md purpose index exists). Every response cites source file, line range when available, and analysis method (static vs LLM inference).

---

## 2. Progress Summary

### Working

| Component | Status | Notes |
|-----------|--------|-------|
| Repository loader | ✅ | Local path + GitHub clone, safe subprocess |
| File discovery | ✅ | Supported extensions, content hashing, skip dirs |
| Surveyor | ✅ | Tree-sitter Python, imports, functions, classes, git velocity, PageRank, SCCs, dead-code flags |
| Hydrologist | ✅ | Python dataflow, SQL lineage (sqlglot), dbt refs/sources, YAML/DAG, notebook cells |
| Archivist | ✅ | CODEBASE.md, onboarding_brief.md, module_graph.json, lineage_graph.json, trace, Pyvis HTML |
| CLI | ✅ | `cartographer analyze`, `query`, `visualize` |
| Orchestrator | ✅ | Full pipeline wiring, incremental reuse (hash-based) |
| Navigator | ✅ | find_implementation, trace_lineage, blast_radius, explain_module; evidence citation |
| Semanticist | ✅ | Purpose statements, doc drift, domain clustering, Day-One synthesis (when API keys set) |
| Incremental mode | ✅ | Manifest of file hashes; full reuse when unchanged; trace logs invalidation |
| Models | ✅ | Pydantic schemas, graph serialization, trace entries |
| Knowledge graph | ✅ | NetworkX wrapper with serialize/deserialize, JSON I/O |

### In Progress

| Component | Status | Notes |
|-----------|--------|-------|
| SQL + Jinja/dbt | ⚠️ | dbt SQL with `{{ ref() }}` causes sqlglot parse failure; regex fallback preserves refs/sources but full lineage may be partial |
| Non-git repos | ✅ | Handled: git velocity returns 0 when `.git` absent (ZIP extracts) |
| LangGraph for Navigator | ❌ | Navigator is a simple class with four methods; no LangGraph agent framework |

### Not Started

| Component | Status | Notes |
|-----------|--------|-------|
| SQL/YAML/JS/TS structural parsing in Surveyor | ❌ | Only Python modules contribute to module graph |
| Partial re-analysis | ❌ | Incremental mode reuses *entire* artifact set when unchanged; no per-file invalidation and merge |
| Tree-sitter grammars for SQL/YAML/JS/TS | ❌ | Language router maps extensions but only Python has tree-sitter analysis |

---

## 3. Early Accuracy Observations

### Module Graph

The module graph is built from Python imports only. Import resolution maps dotted module names to repo-relative `.py` paths. Observations:

- **Correctness**: Import edges match `import` and `from ... import` statements for modules that resolve to discovered files. False positives are rare; false negatives occur for third-party imports and dynamic imports.
- **Coverage**: Only Python modules appear. SQL, YAML, and config files do not appear as nodes.
- **PageRank**: Correctly identifies heavily imported modules as hubs. Useful for "Critical Path."
- **SCCs**: Circular import sets are correctly detected.
- **Dead-code candidates**: Conservative (no incoming edges + public API + excludes main/cli/__init__). May miss modules used only via dynamic imports.

### Lineage Graph

The lineage graph merges Python dataflow, SQL lineage, and YAML/dbt config. Observations:

- **Python**: pandas, SQLAlchemy, PySpark patterns are extracted. Dynamic paths (e.g. f-strings) are recorded as unresolved.
- **SQL**: sqlglot parses standard SQL well. dbt-style `{{ ref('model') }}` and `{{ source('schema','table') }}` cause parse failures; regex fallback preserves these as dbt_ref/dbt_source. For repos like `ol-data-platform` with heavy dbt usage, many SQL files log "SQL parse failed; preserving dynamic refs" but lineage still includes those refs.
- **YAML/dbt**: Schema and model dependencies are extracted from dbt YAML configs.
- **Reality match**: Depends on the repo. Pure Python + standard SQL: high fidelity. dbt-heavy SQL: partial—refs are present but full CTE/join structure may be incomplete when Jinja breaks parsing.

---

## 4. Known Gaps and Plan for Final Submission

### Known Gaps

1. **dbt/Jinja SQL**: sqlglot cannot parse Jinja. Regex fallback captures `ref()`/`source()` but not full FROM/JOIN/CTE structure for templated SQL. Consider pre-processing: strip or expand Jinja before parsing, or integrate a dbt-aware parser.
2. **Module graph scope**: Only Python. SQL/YAML files are not nodes in the module graph.
3. **Partial incremental**: Full re-run on any change. No selective re-analysis of only changed files.
4. **Navigator**: Not a LangGraph agent. Four tools work; no orchestrated multi-step reasoning.
5. **Semanticist off by default**: Requires `.env` with API keys. Without them, purpose index and Day-One answers show "pending."

### Plan for Final Submission

1. **Stabilize dbt SQL handling**: Document the Jinja limitation and consider a preprocessor (e.g. replace `{{ ref('x') }}` with placeholder `ref_x` before sqlglot) to improve lineage completeness.
2. **Validate on target repo**: Run full pipeline on `ol-data-platform` (or the challenge target) and manually spot-check Critical Path, sources/sinks, and lineage vs actual architecture.
3. **Complete Semanticist integration**: Ensure `.env.example` is clear; add a `--with-semanticist` flag or env check so users know when semantic analysis runs.
4. **Final report**: Compare manually written Day-One answers with LLM-synthesized ones; quantify accuracy of module graph and lineage on a sample; document limitations.
5. **Demo**: Use `cartographer analyze`, `visualize --open-browser`, and Navigator tools (find_implementation, trace_lineage, blast_radius, explain_module) with evidence citations.
6. **Self-audit**: Re-run spec acceptance criteria checklist; confirm all required artifacts and sections are produced.
