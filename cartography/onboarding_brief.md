# Onboarding Brief

## Day-One Answers
1. **Primary ingestion path**: Data is ingested from external source systems like Postgres, Canvas, OpenEdX, and S3 using tools including Airbyte, Direct API Extraction, and GCS Sensors. The orchestration is managed by Dagster, and the configuration/pipelines are rooted in `dg_deployments/`, `dg_projects/`, and `docker-compose.yaml`. Raw data lands in schemas such as `ol_warehouse_raw` (or `raw__*`) (Context: "Ingestion (data into warehouse): Ingestion tools: Airbyte, Direct API Extraction, GCS Sensors; Orchestrator: Dagster; Config/pipeline roots: dg_deployments/, dg_projects/, docker-compose.yaml; Raw landing schema (e.g.): ol_warehouse_raw (or raw__*); Source system hints: Postgres, Canvas, OpenEdX, S3").

2. **Critical outputs/endpoints**: Critical output datasets include the `instructor_module_report` and `learner_engagement_report`, as they are key lineage sinks referenced by multiple upstream models (Context: Lineage edges show `course_content`, `video`, `video_pre_query`, and `tfact_chatbot_events` all feed into `sql:src/ol_dbt/models/reporting/instructor_module_report.sql` and `sql:src/ol_dbt/models/reporting/learner_engagement_report.sql`).

3. **Blast radius of critical module**: The blast radius from the critical sink node `<sql_exec>` is minimal, affecting only 1 node directly (Context: "Blast radius from sink '<sql_exec>': 1 nodes.").

4. **Business logic concentrated vs distributed**: Business logic appears distributed across orchestration and utility modules (e.g., `dg_deployments/reconcile_edxorg_partitions.py`, `bin/dbt-create-staging-models.py`) and within dbt transformation models, as indicated by the variety of module purposes and the lineage graph edges (Context: "Module purposes (sample)" describe various orchestration and data pipeline tasks, and lineage edges show transformations feeding into reporting models).

5. **Git velocity hotspots**: The files changed most often in the last 30 days include `dg_deployments/reconcile_edxorg_partitions.py`, `bin/dbt-local-dev.py`, `bin/dbt-create-staging-models.py`, `bin/uv-operations.py`, and `dg_projects/__init__.py` (Context: "Git velocity (30d) among source modules: dg_deployments/reconcile_edxorg_partitions.py, bin/dbt-local-dev.py, bin/dbt-create-staging-models.py, bin/uv-operations.py, dg_projects/__init__.py...").

## Evidence citations
- Module graph: `.cartography/module_graph.json`
- Lineage graph: `.cartography/lineage_graph.json`

## Confidence notes
- Static extraction is conservative; dynamic refs are recorded as unresolved.

## Known unknowns
- Business logic semantics pending semanticist.
- Runtime-only dataset names may appear as `<dynamic>` / `<sql_query>` / `<spark_read>` etc.
