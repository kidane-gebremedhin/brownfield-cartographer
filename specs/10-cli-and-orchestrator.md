# CLI and Orchestrator Spec

## Objective
Provide end-to-end execution for analyze, query, and visualize workflows.

## Files This Spec Owns
- `src/cli.py`
- `src/orchestrator.py`
- related tests

## Required Commands
```text
cartographer analyze <repo_or_path> [--output-dir .cartography] [--branch ...] [--dialect ...]
cartographer query <artifact_dir>
cartographer visualize <artifact_dir>

## Responsibilities
- wire agent execution order
- persist outputs
- expose structured terminal feedback
- load persisted artifacts for querying
- regenerate or open graph outputs when needed

## Acceptance Criteria
- analyze runs the full implemented pipeline
- query can operate from saved artifacts
- visualize works from persisted graphs
- failures surface cleanly