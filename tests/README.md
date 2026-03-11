# Testing strategy

- **Unit tests** (`tests/unit/`): Fast, no I/O beyond tmp dirs. Cover schema/parsers, graph utilities, visualization mapping, query tools, incremental logic.
- **Integration tests** (`tests/integration/`): Run against fixture repos under `tests/fixtures/`. Deterministic; no network.
  - **python_imports**: Python modules with import edges (Surveyor).
  - **hydro_repo**, **sql_lineage**, **dbt_like**, **dag_style**: SQL, YAML configs, DAG-style scripts (Hydrologist).
- **Smoke tests**: Marked with `@pytest.mark.smoke`. May use network or external targets (e.g. analyze a real dbt/Airflow repo). Run with `pytest -m smoke` when needed; exclude with `pytest -m "not smoke"` for CI.

Run all non-smoke tests: `pytest tests/ -m "not smoke" -q`
