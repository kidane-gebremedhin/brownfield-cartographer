# Incremental Update Mode Spec

## Objective
Avoid full re-analysis when only part of the repository changed.

## Files This Spec Owns
- cache/invalidation logic in orchestrator or dedicated helpers
- artifact metadata format
- related tests

## Responsibilities
- compare content hashes and/or git diff
- identify changed files
- invalidate impacted modules and datasets conservatively
- rerun only required analyzers
- log invalidation decisions

## Acceptance Criteria
- repeated runs are faster for small changes
- unchanged artifacts are safely reused
- invalidation is explicit and auditable