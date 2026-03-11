import pytest

from analyzers.sql_lineage import extract_sql_lineage


def test_cte_chain_and_join_sources():
    sql = """
    WITH a AS (SELECT * FROM raw.users),
         b AS (SELECT * FROM a JOIN raw.events e ON a.id = e.user_id)
    SELECT * FROM b JOIN raw.dim d ON b.id = d.id
    """
    r = extract_sql_lineage(sql, dialect="postgres")
    names = {s.name for s in r.sources}
    # Should include base tables (CTE names excluded)
    assert any('raw.users' in n for n in names)
    assert any('raw.events' in n for n in names)
    assert any('raw.dim' in n for n in names)


def test_insert_target_detected():
    sql = "INSERT INTO analytics.out SELECT * FROM raw.users"
    r = extract_sql_lineage(sql)
    assert any(t.name for t in r.targets)


def test_dbt_ref_preserved():
    sql = "SELECT * FROM {{ ref('my_model') }}"
    r = extract_sql_lineage(sql)
    assert any(s.ref_type == 'dbt_ref' and s.name == 'my_model' for s in r.sources)


def test_dbt_source_preserved():
    sql = "SELECT * FROM {{ source('raw', 'users') }}"
    r = extract_sql_lineage(sql)
    assert any(s.ref_type == 'dbt_source' and s.name == 'raw.users' for s in r.sources)
