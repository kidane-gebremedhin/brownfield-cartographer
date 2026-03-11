# Project Goal

## Objective
Build **The Brownfield Cartographer**: a multi-agent codebase intelligence system that ingests a repository (local path or GitHub URL) and produces a living, queryable map of the system's architecture, data flows, and semantic structure.

## Required Outputs
The system must produce:

- a structural **module graph**
- a mixed-language **data lineage graph**
- a semantic **module purpose index**
- a persistent **CODEBASE.md**
- an **onboarding_brief.md** answering the five FDE Day-One questions
- serialized graph artifacts for downstream tooling
- interactive **Pyvis** graph visualizations in the browser
- a query interface for architecture and lineage interrogation

## Supported Inputs
The system should support repositories containing:

- Python
- SQL
- YAML
- JSON
- Markdown
- optionally Jupyter notebooks

## Brownfield Context
This system is designed for brownfield FDE onboarding, where:

- documentation is stale
- architecture is unclear
- data lineage is opaque
- critical paths are hard to identify
- engineers need a fast operational mental model

## Core Principle
Do not memorize the codebase. Build instruments that make the codebase legible.

## Non-Negotiable Requirements
- Use structural parsing where possible instead of regex
- Preserve evidence for extracted facts
- Distinguish static facts from LLM inferences
- Gracefully degrade on parse failures
- Make artifacts useful for both humans and AI agents