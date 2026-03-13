from pathlib import Path

from analyzers.ingestion_detector import IngestionHints, detect_ingestion


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_detect_ingestion_collects_evidence_with_file_and_line(tmp_path: Path) -> None:
    """Detector should return evidence-rich hints for tools, sources, raw schemas, and orchestrator."""
    # README mentioning Airbyte and S3
    _write(
        tmp_path / "README.md",
        "This warehouse uses Airbyte to pull data from S3 buckets.\n",
    )

    # docker-compose with an Airbyte-like service
    _write(
        tmp_path / "docker-compose.yaml",
        "services:\n  airbyte-server:\n    image: airbyte/server:latest\n",
    )

    # Dagster config directories
    (tmp_path / "dg_deployments").mkdir()
    (tmp_path / "dg_projects").mkdir()

    # Script mentioning raw schemas and dbt source generation
    _write(
        tmp_path / "scripts" / "raw_loader.py",
        '\n'.join(
            [
                "def load_raw():",
                '    target_schema = \"ol_warehouse_raw_data\"',
                '    table_name = \"raw__micromasters__users\"',
                "    # dbt source generation for raw tables",
            ]
        ),
    )

    hints: IngestionHints = detect_ingestion(tmp_path)

    # High-level hints should be populated
    assert "Airbyte" in hints.ingestion_tools
    assert "S3" in hints.source_system_hints
    assert hints.orchestrator == "Dagster"
    assert hints.raw_schema_hint is not None

    # Evidence should include file paths and line numbers for key matches
    evidence_strs = [f"{e.file_path}:{e.line}:{e.keyword}:{e.category}" for e in hints.evidence]

    # README Airbyte/S3
    assert any("README.md" in e and "airbyte" in e and "tool" in e for e in evidence_strs)
    assert any("README.md" in e and "s3" in e and "source_system" in e for e in evidence_strs)

    # Dagster orchestrator paths
    assert any("dg_deployments/" in e or "dg_projects/" in e for e in (ev.file_path for ev in hints.evidence))
    assert any("dagster" in e and "orchestrator" in e for e in evidence_strs)

    # Raw schema script
    assert any("scripts/raw_loader.py" in e and "raw__" in e and "raw_schema" in e for e in evidence_strs)
    assert any("scripts/raw_loader.py" in e and "dbt source" in e and "tool" in e for e in evidence_strs)

