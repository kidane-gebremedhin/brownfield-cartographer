
---

```md
# Knowledge Graph Schema

## Objective
Define the typed knowledge graph used by all agents.

## Files This Spec Owns

This spec is responsible for implementing the entire typed schema layer.

The following files MUST exist:

src/models/common.py
src/models/nodes.py
src/models/edges.py
src/models/graph_models.py
src/models/artifacts.py
src/models/trace.py

## Node Types

### ModuleNode
```python
path: str
language: str
purpose_statement: str | None
domain_cluster: str | None
complexity_score: float
change_velocity_30d: int
change_velocity_90d: int
is_dead_code_candidate: bool
last_modified: datetime | None
loc: int
comment_ratio: float | None
public_api_count: int

### FunctionNode
```python
qualified_name: str
parent_module: str
signature: str | None
purpose_statement: str | None
call_count_within_repo: int
is_public_api: bool
line_start: int | None
line_end: int | None


### DatasetNode
```python
name: str
storage_type: Literal["table", "file", "stream", "api"]
schema_snapshot: dict | None
freshness_sla: str | None
owner: str | None
is_source_of_truth: bool | None


### TransformationNode
```python
id: str
source_datasets: list[str]
target_datasets: list[str]
transformation_type: str
source_file: str
line_range: tuple[int, int] | None
sql_query_if_applicable: str | None



## Required Implementation

All graph entities must be implemented as Pydantic models.

The schema layer must include:

Node types
- ModuleNode
- FunctionNode
- DatasetNode
- TransformationNode

Edge types
- IMPORTS
- CALLS
- CONSUMES
- PRODUCES
- CONFIGURES

Graph models
- ModuleGraph
- DataLineageGraph

Artifact models
- CartographyArtifacts
- CODEBASEContext
- OnboardingBrief

Trace models
- CartographyTraceEntry
- Evidence

## Acceptance Criteria

The following conditions must be satisfied:

- `src/models/` directory exists
- all schema files compile without import errors
- all node and edge types are Pydantic models
- graph models support JSON serialization
- evidence metadata can attach to nodes and edges
- models are reusable across agents