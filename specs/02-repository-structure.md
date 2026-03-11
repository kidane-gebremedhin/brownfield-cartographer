
---

```md
# Repository Structure

## Required Project Layout

```text
brownfield-cartographer/
├── pyproject.toml
├── README.md
├── .gitignore
├── src/
│   ├── cli.py
│   ├── orchestrator.py
│   ├── settings.py
│   ├── logging_config.py
│   ├── repository/
│   │   ├── loader.py
│   │   ├── git_tools.py
│   │   └── file_discovery.py
│   ├── models/
│   │   ├── common.py
│   │   ├── nodes.py
│   │   ├── edges.py
│   │   ├── graph_models.py
│   │   ├── artifacts.py
│   │   └── trace.py
│   ├── analyzers/
│   │   ├── language_router.py
│   │   ├── tree_sitter_analyzer.py
│   │   ├── python_dataflow.py
│   │   ├── sql_lineage.py
│   │   ├── dag_config_parser.py
│   │   ├── notebook_parser.py
│   │   └── git_velocity.py
│   ├── agents/
│   │   ├── surveyor.py
│   │   ├── hydrologist.py
│   │   ├── semanticist.py
│   │   ├── archivist.py
│   │   └── navigator.py
│   ├── graph/
│   │   ├── knowledge_graph.py
│   │   ├── graph_algorithms.py
│   │   ├── serializers.py
│   │   └── visualization.py
│   ├── llm/
│   │   ├── budget.py
│   │   ├── prompts.py
│   │   ├── embeddings.py
│   │   └── provider.py
│   ├── query/
│   │   ├── tools.py
│   │   └── response_formatter.py
│   └── utils/
│       ├── files.py
│       ├── text.py
│       ├── hashing.py
│       ├── line_ranges.py
│       └── safe_subprocess.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── specs/
└── examples/


## Package Rules
- Keep analyzers separate from agents
- Keep graph utilities separate from semantic inference
- Keep models centralized under src/models
- Keep Pyvis logic isolated in src/graph/visualization.py
- Keep CLI thin; orchestration belongs in src/orchestrator.py
## Artifact Output Convention
- Each analysis run should write artifacts into: .cartography/