
---

```md
# Implementation Roadmap

## Objective
Define the implementation phases and the exact build order.

## Phase 0 — Bootstrapping
- initialize project
- set up pyproject.toml
- configure formatting, linting, typing, tests
- create spec files
- scaffold source tree

## Phase 1 — Core Models and Graph, MUST produce the src/models package before any analyzers or agents are implemented.
- implement Pydantic models
- implement graph wrapper
- implement graph serialization contracts

## Phase 2 — Repository Ingestion
- support local paths
- support safe GitHub clone
- file discovery
- content hashing

## Phase 3 — Surveyor
- tree-sitter based static analysis
- imports, classes, functions
- complexity signals
- git velocity
- import graph and SCC detection

## Phase 4 — Hydrologist
- Python dataflow extraction
- SQL lineage extraction via sqlglot
- YAML / DAG topology extraction
- lineage graph and blast radius

## Phase 5 — Archivist
- CODEBASE.md
- onboarding_brief.md
- graph JSON
- trace logs

## Phase 6 — Pyvis Visualization
- module graph HTML
- lineage graph HTML

## Phase 7 — CLI and Orchestrator
- analyze command
- query command
- visualize command

## Phase 8 — Semanticist
- purpose statements
- doc drift detection
- domain clustering
- Day-One synthesis

## Phase 9 — Navigator
- implementation lookup
- lineage tracing
- blast radius
- explain module

## Phase 10 — Incremental Update Mode
- changed-file detection
- partial invalidation
- selective re-analysis

## Phase 11 — Testing and Fixtures
- unit tests
- integration tests
- fixture repos
- smoke tests

## Required Build Order
Cursor should implement in this order:

1. scaffolding
2. models
3. repository ingestion
4. surveyor
5. graph utilities
6. hydrologist
7. archivist
8. pyvis visualization
9. cli and orchestrator
10. semanticist
11. navigator
12. incremental mode
13. tests and fixtures
14. report/demo support

## Why This Order
This order ensures that static extraction and graph artifacts exist before semantic and query layers are added.