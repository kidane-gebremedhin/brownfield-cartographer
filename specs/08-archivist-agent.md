# Archivist Agent Spec

## Objective
Generate durable artifacts for humans and AI agents.

## Files This Spec Owns
- `src/agents/archivist.py`
- `src/graph/serializers.py`
- related tests

## Required Artifacts
For each analysis run, generate:

- `.cartography/CODEBASE.md`
- `.cartography/onboarding_brief.md`
- `.cartography/module_graph.json`
- `.cartography/lineage_graph.json`
- `.cartography/cartography_trace.jsonl`

## CODEBASE.md Required Sections
- Architecture Overview
- Critical Path
- Data Sources & Sinks
- Known Debt
- Recent Change Velocity
- Module Purpose Index

## onboarding_brief.md Required Sections
- the five FDE Day-One answers
- evidence citations
- confidence notes
- known unknowns

## Acceptance Criteria
- artifacts are generated from previous agent outputs
- markdown is readable
- JSON is machine-readable
- artifact writing is deterministic and testable