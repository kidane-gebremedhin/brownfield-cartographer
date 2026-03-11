1. Implement the repository ingestion layer for brownfield-cartographer according to specs/05-repository-ingestion.md.

Files to create or complete:
- src/repository/loader.py
- src/repository/git_tools.py
- src/repository/file_discovery.py
- src/utils/safe_subprocess.py

Requirements:
- support local path and GitHub URL input
- all remote clones must happen in temporary directories
- use subprocess without shell=True
- discover supported source files for Python, SQL, YAML, JSON, Markdown, and notebooks
- compute stable content hashes per file for future incremental analysis
- include clear exceptions and logging
- add unit tests for invalid paths, invalid URLs, successful clone, and file discovery

Do not implement analyzers yet. Keep this layer focused only on safe repo loading and file discovery.

2. Implement the Surveyor agent according to specs/06-surveyor-agent.md.

Files to create or complete:
- src/analyzers/language_router.py
- src/analyzers/tree_sitter_analyzer.py
- src/analyzers/git_velocity.py
- src/agents/surveyor.py

Requirements:
- use tree-sitter for Python-first structural analysis
- extract imports, top-level public functions, classes, and inheritance
- compute LOC and lightweight complexity signals
- implement git velocity analysis for 30 and 90 day windows
- build a NetworkX directed import graph
- compute PageRank and strongly connected components
- mark dead code candidates conservatively
- skip unparseable files with logs rather than failing

Add unit tests and one integration-style fixture test. Keep the design extensible for SQL, YAML, and JS/TS later.

3. Implement the Hydrologist agent according to specs/07-hydrologist-agent.md.

Files to create or complete:
- src/analyzers/python_dataflow.py
- src/analyzers/sql_lineage.py
- src/analyzers/dag_config_parser.py
- src/analyzers/notebook_parser.py
- src/agents/hydrologist.py

Requirements:
- use sqlglot for SQL lineage extraction
- build a NetworkX directed lineage graph with typed Pydantic-backed records
- support pandas, SQLAlchemy, PySpark, dbt SQL models, and dbt-like YAML config inputs
- represent unresolved dynamic dataset references explicitly instead of failing
- expose find_sources, find_sinks, trace_lineage, and blast_radius

Add tests for SQL CTE chains, joins, dbt-style refs, and basic Python data read/write extraction.

4. Implement the Archivist agent according to specs/08-archivist-agent.md.

Files to create or complete:
- src/agents/archivist.py
- src/graph/serializers.py

Requirements:
- generate CODEBASE.md, onboarding_brief.md, module_graph.json, lineage_graph.json, and cartography_trace.jsonl
- render markdown from graph and analysis outputs
- serialize graph artifacts in a clean machine-readable format
- design outputs so they can later be consumed by the Navigator without rerunning analysis

Add tests for artifact generation and serialization. Do not implement Pyvis here; that belongs to the visualization spec.

5. Implement Pyvis-based graph visualization according to specs/09-pyvis-visualization.md.

Files to create or complete:
- src/graph/visualization.py

Requirements:
- generate self-contained HTML files from NetworkX graphs
- support both module graph and lineage graph rendering
- use meaningful labels, hover titles, groups, and directed edges
- keep repo-specific assumptions out of the visualization layer
- degrade gracefully when metadata is missing

Also add minimal integration hooks so Archivist can call this layer when graph artifacts are available. Add tests for HTML generation and metadata mapping.

6. Implement the CLI and orchestrator according to specs/10-cli-and-orchestrator.md.

Files to create or complete:
- src/cli.py
- src/orchestrator.py

Requirements:
- use Typer for the CLI
- support analyze, query, and visualize commands
- analyze should run the implemented pipeline and write artifacts into an output directory
- query should load saved artifacts instead of rerunning analysis
- visualize should regenerate or render Pyvis outputs from persisted graph data
- keep CLI thin and orchestration logic centralized

Add integration tests where practical.

7. Implement the Semanticist agent according to specs/11-semanticist-agent.md.

Files to create or complete:
- src/llm/budget.py
- src/llm/prompts.py
- src/llm/provider.py
- src/llm/embeddings.py
- src/agents/semanticist.py

Requirements:
- create a provider-agnostic LLM layer
- support budget tracking and prompt templating
- generate code-grounded purpose statements
- classify documentation drift against docstrings or comments
- cluster modules into inferred domains using embeddings
- synthesize the five FDE Day-One answers from Surveyor and Hydrologist outputs

Keep this layer testable with mock providers. Add unit tests for prompt assembly, budget tracking, drift classification logic, and clustering orchestration.

8. Implement the Navigator agent according to specs/12-navigator-agent.md.

Files to create or complete:
- src/agents/navigator.py
- src/query/tools.py
- src/query/response_formatter.py

Requirements:
- operate from persisted artifacts without rerunning the full pipeline
- support implementation lookup, lineage tracing, blast radius, and module explanation
- include path, line ranges when available, method provenance, and confidence in responses
- clearly separate graph-backed answers from semantic inference

Add tests for graph-backed queries and response formatting.

9. Implement incremental update mode according to specs/13-incremental-update-mode.md.

Requirements:
- track file content hashes and prior analysis metadata
- detect changed files since the previous run
- conservatively invalidate only affected analysis outputs
- reuse unchanged artifacts safely
- log invalidation decisions into the trace output

Favor correctness over aggressive caching. Add tests for no-change, single-file-change, and multi-file-change scenarios.

10. Implement the testing strategy according to specs/14-testing-and-fixtures.md.

Requirements:
- create representative fixture repositories for Python imports, SQL lineage, YAML configs, and DAG-style workflows
- write unit tests for models, analyzers, graph utilities, and visualization mapping
- write integration tests for Surveyor and Hydrologist behavior against fixtures
- keep tests deterministic and avoid network access except explicitly marked smoke tests