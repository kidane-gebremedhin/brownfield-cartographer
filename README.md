# brownfield-cartographer

Spec-first implementation. See ./specs.

## Running the agents

### Surveyor only (module graph)

Run static analysis and build the module dependency graph (Python imports + path references, all file types as nodes):

```bash
uv run cartographer surveyor https://github.com/dbt-labs/jaffle-shop
```

Output: `module_graph.json`, `surveyor_metrics.json` in the output directory (default: `<repo>/cartography`).

---

### Hydrologist (data lineage)

The **Hydrologist** (data flow & lineage) runs as part of the **full analysis pipeline**. It builds the data lineage DAG from Python, SQL/dbt, YAML (Airflow, dbt, Prefect), and notebooks.

**How to run the Hydrologist:**

```bash
uv run cartographer analyze https://github.com/mitodl/ol-data-platform
```

- **`repo_or_path`** – Local path or GitHub URL.
- **`--output-dir`** – Where to write artifacts (default: `<repo>/cartography`).
- **`--branch`** – Git branch/ref (GitHub URLs only).
- **`--dialect`** – SQL dialect for lineage extraction: `postgres` (default), `bigquery`, `snowflake`, `duckdb`.

Examples:

```bash
# Current repo
uv run cartographer analyze .

# dbt repo with Postgres SQL
uv run cartographer analyze https://github.com/dbt-labs/jaffle-shop

# BigQuery SQL
uv run cartographer analyze . --dialect bigquery
```

**Why does analyze feel slow or “stale”?** Large repos (e.g. many Python files) take time because: (1) the repo is cloned or scanned; (2) Surveyor and Hydrologist run over all files; (3) **Semanticist runs one LLM call per Python module** (purpose + drift), then clustering and Day-One synthesis. Progress is printed to stderr: `Running Surveyor...`, `Running Hydrologist...`, `Running Semanticist...`, `Semanticist: purpose 50/200`, then `Writing artifacts...`. So the run is not stuck—it is working through many modules. Increase `CARTOGRAPHER_LLM_TIMEOUT` in `.env` if you see timeouts.

**Artifacts** (in the output directory):

- **`lineage_graph.json`** – Data lineage graph (nodes = datasets/transformations; edges = consumes/produces with `source_file`, `line_range`, `transformation_type`).
- Plus Surveyor and Archivist outputs: `module_graph.json`, `CODEBASE.md`, `onboarding_brief.md`, etc.

**Query lineage** (after running `analyze`):

```bash
uv run cartographer query ./cartography
```

This prints a summary (artifact dir, module count, lineage graph size). To run the **required query steps** (lineage query and blast radius), you can **type your question** or use the explicit commands below.

---

### Ask (type your question)

You can type a natural language question. The system classifies it and routes to the right query:

```bash
uv run cartographer ask "<question>" [artifact_dir] [--about <dataset_or_module_id>] [--max-depth N]
```

`artifact_dir` defaults to `./cartography` if omitted.

Examples:

```bash
# Lineage query - no artifact path needed (defaults to ./cartography)
uv run cartographer ask "What upstream sources feed this output dataset?" --about "sql:src/ol_dbt/models/intermediate/edxorg/int__edxorg__mitx_courserun_certificates.sql"

# Or embed the dataset in the question
uv run cartographer ask "What upstream sources feed sql:src/ol_dbt/models/intermediate/edxorg/int__edxorg__mitx_courserun_certificates.sql?"

# Blast radius
uv run cartographer ask "What would break if this module changed?" --about "__micromasters__users"
```

Supported questions: *What upstream sources feed [this output dataset / X]?* (lineage query) and *What would break if [X] changed?* / *Blast radius for X* (blast radius). If the dataset/module ID is not in the question, use `--about <id>`.

---

### Step 2: The Lineage Query (Required)

**Ask:** *What upstream sources feed this output dataset?*

The command runs a DataLineageGraph upstream traversal and returns the answer with **file:line citations** for each edge.

```bash
uv run cartographer lineage-upstream <artifact_dir> <dataset> [--max-depth N]
```

- **`artifact_dir`** – Directory containing `lineage_graph.json` (e.g. `./cartography`).
- **`dataset`** – The output dataset node ID to trace upstream from (e.g. a dbt model id like `sql:src/ol_dbt/models/.../my_model.sql`, or a table name as in the graph).
- **`--max-depth`** – Max traversal depth (default: 10).

Example:

```bash
uv run cartographer lineage-upstream ./cartography "sql:src/ol_dbt/models/intermediate/edxorg/int__edxorg__mitx_courserun_certificates.sql"
```

Output: upstream nodes (sources that feed this dataset) and edges with citations like `source_file:line_start-line_end`.

---

### Step 3: The Blast Radius (Required)

**Pick a module/dataset.** Run blast radius to see the **dependency graph of everything that would break** if that module changed its interface (downstream dependents).

```bash
uv run cartographer blast-radius <artifact_dir> <module_or_dataset> [--max-depth N]
```

- **`artifact_dir`** – Directory containing `lineage_graph.json`.
- **`module_or_dataset`** – Lineage graph node ID (e.g. a table name or `sql:path/to/model.sql`).
- **`--max-depth`** – Max traversal depth (default: 5).

Example:

```bash
uv run cartographer blast-radius ./cartography __micromasters__users
```

Output: list of affected (downstream) nodes that depend on the given module/dataset.

---

You can also use the **Navigator API** from Python: `Navigator(artifact_dir).upstream_sources(dataset)` and `Navigator(artifact_dir).blast_radius(module_or_dataset)`.