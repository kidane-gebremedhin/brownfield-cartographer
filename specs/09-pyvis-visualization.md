# Pyvis Visualization Spec

## Objective
Provide interactive browser graph visualization using Pyvis from NetworkX data.

## Files This Spec Owns
- `src/graph/visualization.py`
- Archivist integration hooks
- related tests

## Required Outputs
- `.cartography/module_graph.html`
- `.cartography/lineage_graph.html`

## Module Graph Rules
- node label: short module path or basename
- node title: full path, PageRank, complexity, velocity, dead-code flag
- node group: language or domain
- edge direction must be visible

## Lineage Graph Rules
- dataset nodes grouped by storage type
- transformation nodes visually distinct
- node title includes source file and line range where available
- graph direction must be obvious

## UX Requirements
- output must open locally in a browser
- no server required
- hover metadata should be useful
- degrade gracefully if metadata is missing

## Acceptance Criteria
- HTML files are produced from NetworkX graphs
- metadata appears on hover
- graph is usable for medium-sized repos