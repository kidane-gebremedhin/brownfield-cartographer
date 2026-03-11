# Navigator Agent Spec

## Objective
Provide a user-facing query interface over saved graph and semantic artifacts.

## Files This Spec Owns
- `src/agents/navigator.py`
- `src/query/tools.py`
- `src/query/response_formatter.py`
- related tests

## Tool Contract

### find_implementation(concept: str)
Return likely modules/functions implementing a concept.

### trace_lineage(dataset: str, direction: str)
Return upstream or downstream lineage with evidence.

### blast_radius(module_or_dataset: str)
Return downstream dependencies affected by change or failure.

### explain_module(path: str)
Return structural and semantic explanation of a module.

## Requirements
- should work from persisted artifacts
- should not require full re-analysis
- must distinguish graph traversal from semantic inference
- responses must include evidence and confidence

## Acceptance Criteria
- graph-backed queries work offline from artifacts
- semantic search and graph traversal are clearly distinguished
- output formatting is readable and evidence-rich