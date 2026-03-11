
---

```md
# Knowledge Graph Schema

## Objective
Define the typed knowledge graph used by all agents.

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