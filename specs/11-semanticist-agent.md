# Semanticist Agent Spec

## Objective
Add semantic understanding that static extraction cannot provide.

## Files This Spec Owns
- `src/llm/budget.py`
- `src/llm/prompts.py`
- `src/llm/provider.py`
- `src/llm/embeddings.py`
- `src/agents/semanticist.py`
- related tests

## Responsibilities
- generate code-grounded purpose statements
- detect documentation drift
- cluster modules into inferred domains
- synthesize the five Day-One answers
- manage token budgets and provider abstraction by using cheaper providers such as gemini-flash for bulk module summaries, and reserve the use of expensive providers such as gpt-4 for synthesis. these providers and api keys should be configured in .env file

## Requirements
### Purpose Statements
- must be based primarily on code-derived context
- should not simply repeat docstrings

### Documentation Drift
Classify as:
- aligned
- stale
- contradictory
- insufficient

### Domain Clustering
- embed module purpose statements
- cluster into 5–8 domains
- produce readable labels

### Day-One Synthesis
Must answer:
1. primary ingestion path
2. critical outputs/endpoints
3. blast radius of critical module
4. business logic concentrated vs distributed
5. git velocity hotspots

## Acceptance Criteria
- semantic outputs are grounded in code context
- doc drift classification is explicit
- clustering is readable
- answers include provenance