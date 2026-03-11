# Five FDE Day-One Questions - Reconnaissance Report


### Data Engineering Repository Used
- https://github.com/mitodl/ol-data-platform

## (1) What is the primary data ingestion path?

The primary data ingestion path follows a multi-source architecture:

**Core Ingestion Mechanisms:**
- **Airbyte**: Extracts data from various sources and loads to S3 raw layer (`ol_warehouse_raw_data` key prefix)
- **dlt Pipelines**: Ingests edX.org database exports from S3 (`s3://ol-data-lake-landing-zone-production/edxorg-raw-data/`)
- **Direct API Extraction**: Canvas, OpenEdX, Sloan Executive Education APIs pull data via OAuth/Vault-authenticated clients
- **GCS Sensors**: Monitor Google Cloud Storage buckets for edX.org course archives and tracking logs

**Data Flow:**
1. Raw data lands in S3 data lake (landing zone)
2. Incremental processing via sensors and schedules
3. Data stored as Iceberg tables in Glue catalogs (`ol_warehouse_production_raw`, `ol_warehouse_qa_raw`)
4. dbt transformations create staging → intermediate → marts layers
5. Final datasets exposed in Superset via automated dataset creation

**Key Technologies:**
- Dagster for orchestration (7 code locations)
- S3 + Iceberg for storage
- Trino for querying
- dbt for transformations
- Superset for BI visualization

## (2) What are the 3-5 most critical output datasets/endpoints?

**1. dbt Marts Models** (`src/ol_dbt/models/marts/`)
- Analytics-ready tables with business logic
- Naming: `fct_<domain>__<metric>.sql` or `dim_<domain>__<entity>.sql`
- Auto-exposed to Superset via `create_superset_asset`
- Critical for all BI dashboards and reporting

**2. Iceberg Data Lake Tables**
- Production: `ol_warehouse_production_*` databases (raw, staging, reporting, mart)
- QA: `ol_warehouse_qa_*` databases
- Queried via Trino/Athena
- Foundation for all downstream analytics

**3. Superset Datasets**
- Physical datasets created from dbt models
- Auto-refreshed when dbt models update
- Row-level security (RLS) policies applied
- Direct endpoint for BI users

**4. S3 Raw Data Exports**
- Course metadata, tracking logs, enrollment data
- Partitioned by source system (edxorg, canvas, openedx)
- Consumed by institutional research and external systems

**5. Student Risk Probability Reports**
- Machine learning model outputs for academic integrity
- Combines cheating detection with logistic regression
- Critical for course administration decisions

## (3) What is the blast radius if the most critical module fails?

**Most Critical Module: dbt Project** (`src/ol_dbt/`)

**Failure Impact:**
- **Complete BI Outage**: All Superset dashboards become stale/unusable
- **Analytics Paralysis**: No new reporting data available
- **Downstream Dependencies**: All code locations that depend on transformed data halt
- **Business Impact**: Institutional research, course administration, and executive reporting stop
- **Recovery Time**: Hours to days depending on failure scope

**Secondary Critical Modules:**
- **Lakehouse Code Location**: Handles dbt execution and Superset integration
- **ol-orchestrate-lib**: Shared resources used by all 7 code locations
- **Airbyte Connections**: If ingestion stops, all raw data pipelines fail

**Mitigation Factors:**
- Iceberg tables provide historical data availability
- Local development environment allows isolated testing
- Git-based deployment with rollback capability
- Monitoring via Dagster UI and health checks

## (4) Where is the business logic concentrated vs. distributed?

**Concentrated Business Logic:**
- **dbt Project** (`src/ol_dbt/models/`): Core transformations and business rules
  - `staging/`: 1:1 source transformations
  - `intermediate/`: Business logic, joins, calculations
  - `marts/`: Analytics-ready final datasets
- **Student Risk Probability**: ML model weights and feature scaling logic
- **Superset Integration**: RLS policies and dataset management

**Distributed Business Logic:**
- **Data Ingestion Logic**: Spread across 7 Dagster code locations
  - API authentication and error handling
  - Data validation and quality checks
  - Incremental loading strategies
- **Resource Configuration**: Environment-specific settings in each code location
- **Scheduling Logic**: Custom schedules per data source (daily, hourly, etc.)

**Architecture Pattern:**
- **Centralized**: Business transformations (dbt)
- **Distributed**: Data acquisition and quality assurance
- **Shared**: Common utilities in `ol-orchestrate-lib`

## (5) What has changed most frequently in the last 90 days (git velocity map)?

Based on git commit analysis (top 20 most changed files):

**High Velocity Files:**
1. **uv.lock files** (52+ changes each): Dependency management across all code locations
2. **pyproject.toml** (20 changes): Root workspace configuration
3. **src/ol_dbt/models/reporting/_reporting__models.yml** (21 changes): dbt model definitions
4. **packages/ol-orchestrate-lib/pyproject.toml** (15 changes): Shared library dependencies
5. **Dockerfiles** (13+ changes): Container configurations

**Velocity Insights:**
- **Dependency Management**: uv.lock files change most frequently (38-52 commits each)
- **dbt Models**: Active development in reporting layer
- **Infrastructure**: Docker and configuration files updated regularly
- **Shared Library**: Core orchestration library evolving

**Implications:**
- Active dependency updates and security patches
- Rapid dbt model development for new reporting requirements
- Infrastructure-as-code evolution
- Shared components under active maintenance

**Low Velocity Areas:**
- Core business logic in assets/ (stable)
- Legacy code locations (minimal changes)
- Documentation (infrequent updates)