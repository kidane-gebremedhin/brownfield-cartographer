# Testing and Fixtures Spec

## Objective
Make the system verifiable on fixture repos and real-world targets.

## Test Strategy

### Unit Tests
- schema validation
- parser helpers
- graph utilities
- visualization mapping

### Integration Tests
- fixture repo with Python imports
- fixture SQL lineage project
- fixture dbt-like project
- fixture Airflow-style DAG subset

### Smoke Tests
- analyze a dbt target
- analyze an Airflow target

## Acceptance Criteria
- unit tests are fast
- integration tests are deterministic
- failures localize quickly
- fixture repos are small and representative