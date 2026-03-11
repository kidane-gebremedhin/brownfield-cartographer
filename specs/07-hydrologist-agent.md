# Hydrologist Agent Spec

## Objective
Construct the mixed-language data lineage graph.

## Files This Spec Owns
- `src/analyzers/python_dataflow.py`
- `src/analyzers/sql_lineage.py`
- `src/analyzers/dag_config_parser.py`
- `src/analyzers/notebook_parser.py`
- `src/agents/hydrologist.py`
- related tests

## Responsibilities
- parse Python data read/write patterns
- parse SQL lineage using sqlglot
- parse YAML/DAG topology
- merge all extracted flows into a lineage graph
- expose source/sink/upstream/downstream/blast-radius methods

## Python Patterns to Support
- pandas.read_csv
- pandas.read_parquet
- pandas.read_sql
- SQLAlchemy execution/read patterns
- PySpark read/write patterns
- unresolved dynamic references should be recorded explicitly

## SQL Requirements
- use sqlglot.parse_one()
- support at minimum postgres, bigquery, snowflake, duckdb
- detect table dependencies from FROM, JOIN, and CTE chains
- support dbt-style ref() and source() normalization where feasible

## YAML / Config Requirements
- parse dbt schema/config YAML
- parse DAG/config topology where represented in YAML
- emit CONFIGURES edges and topology hints

## Acceptance Criteria
- lineage graph builds on a small fixture repo
- upstream dependencies can be traced
- unresolved dynamic references are preserved, not dropped
- blast_radius works on lineage nodes