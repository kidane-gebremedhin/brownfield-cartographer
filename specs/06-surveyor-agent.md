# Surveyor Agent Spec

## Objective
Build the structural analysis layer over the repository.

## Files This Spec Owns
- `src/analyzers/language_router.py`
- `src/analyzers/tree_sitter_analyzer.py`
- `src/analyzers/git_velocity.py`
- `src/agents/surveyor.py`
- related tests

## Responsibilities
- route files to parser strategies
- extract imports
- extract public functions and classes
- extract inheritance where possible
- compute LOC and lightweight complexity signals
- compute git velocity for 30 and 90 days
- build the module import graph
- run PageRank and strongly connected components
- identify conservative dead code candidates

## Minimum Parsing Coverage
### Python
- imports
- top-level functions
- classes
- inheritance

### SQL
- statement presence for indexing
- file-level metadata for future lineage work

### YAML
- key-path extraction for config awareness

## Acceptance Criteria
- builds a module graph on a real target repo
- computes PageRank
- identifies circular dependencies
- logs and skips unparseable files
- never crashes on a single bad file