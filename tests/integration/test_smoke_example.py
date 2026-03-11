"""Smoke tests: may use network or external targets. Skip in CI with -m 'not smoke'."""

import pytest


@pytest.mark.smoke
def test_smoke_placeholder():
    """Placeholder for future smoke tests (e.g. analyze dbt target, Airflow target)."""
    assert True
