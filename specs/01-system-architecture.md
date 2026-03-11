# System Architecture

## High-Level Pipeline

```text
Repository / GitHub URL
        ↓
Repository Loader
        ↓
File Discovery + Language Router
        ↓
Surveyor Agent
  - module graph
  - API surface
  - git velocity
  - complexity signals
  - dead code candidates
        ↓
Hydrologist Agent
  - Python data flow
  - SQL lineage
  - YAML / DAG topology
        ↓
Semanticist Agent
  - purpose statements
  - documentation drift
  - domain clustering
  - Day-One answer synthesis
        ↓
Archivist Agent
  - CODEBASE.md
  - onboarding_brief.md
  - cartography_trace.jsonl
  - serialized graph artifacts
  - Pyvis visualizations
        ↓
Navigator Agent
  - find_implementation
  - trace_lineage
  - blast_radius
  - explain_module