"""Detect ingestion tooling and orchestrator for Day-One "Primary ingestion path".

Ingestion = how data is moved from external systems (DBs, S3) into the warehouse.
We look for: Airbyte, dlt, Dagster, docker-compose, and raw-schema hints (e.g. ol_warehouse_raw).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class IngestionHints:
    """Signals about how data is ingested into the warehouse (for Day-One)."""

    ingestion_tools: list[str] = field(default_factory=list)  # e.g. ["Airbyte", "dlt"]
    orchestrator: str | None = None  # e.g. "Dagster"
    config_paths: list[str] = field(default_factory=list)  # e.g. ["docker-compose.yaml", "dg_projects/"]
    raw_schema_hint: str | None = None  # e.g. "ol_warehouse_raw"
    source_system_hints: list[str] = field(default_factory=list)  # e.g. ["Postgres", "S3"]


def detect_ingestion(repo_root: Path | str) -> IngestionHints:
    """Scan repo for ingestion tooling and orchestrator. Best-effort; never raises."""
    root = Path(repo_root).resolve()
    out = IngestionHints()

    if not root.is_dir():
        return out

    # Path-based detection
    for p in root.iterdir():
        if p.name.startswith("."):
            continue
        name_lower = p.name.lower()
        if "airbyte" in name_lower:
            out.ingestion_tools.append("Airbyte")
            out.config_paths.append(p.name + "/")
        if "dlt" in name_lower and "dlt" not in out.ingestion_tools:
            # avoid duplicates from paths like "dlt_config"
            if "dlt" not in [t.lower() for t in out.ingestion_tools]:
                out.ingestion_tools.append("dlt")
        if "dagster" in name_lower or name_lower == "dg_projects" or name_lower == "dg_deployments":
            if out.orchestrator is None:
                out.orchestrator = "Dagster"
            if p.is_dir() and p.name not in out.config_paths:
                out.config_paths.append(p.name + "/")

    if (root / "docker-compose.yaml").exists() or (root / "docker-compose.yml").exists():
        if "docker-compose.yaml" not in out.config_paths:
            out.config_paths.append("docker-compose.yaml")

    # Deduplicate ingestion_tools
    out.ingestion_tools = list(dict.fromkeys(out.ingestion_tools))

    # Scan key root-level files first (README, docker-compose) so we don't miss them
    try:
        _scan_key_files(root, out)
    except Exception as e:
        logger.debug("Ingestion key-file scan failed: %s", e)

    # Content-based hints: sample more files for ol_warehouse_raw, Airbyte, dlt
    try:
        _content_scan(root, out)
    except Exception as e:
        logger.debug("Ingestion content scan failed: %s", e)

    return out


def _scan_key_files(root: Path, out: IngestionHints) -> None:
    """Scan README and docker-compose first for Airbyte, dlt, Dagster."""
    for name in ("README.md", "README.MD", "docker-compose.yaml", "docker-compose.yml"):
        path = root / name
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
            if len(data) > 500_000:
                data = data[:500_000]
        except OSError:
            continue
        if b"airbyte" in data.lower() and "Airbyte" not in out.ingestion_tools:
            out.ingestion_tools.append("Airbyte")
        if (b"dlt" in data or b"data load" in data.lower()) and "dlt" not in [t.lower() for t in out.ingestion_tools]:
            out.ingestion_tools.append("dlt")
        if (b"dagster" in data or b"Dagster" in data) and out.orchestrator is None:
            out.orchestrator = "Dagster"
        if b"ol_warehouse_raw" in data or b"raw__" in data:
            if out.raw_schema_hint is None:
                out.raw_schema_hint = "ol_warehouse_raw (or raw__*)"
        if b"postgres" in data or b"Postgres" in data:
            if "Postgres" not in out.source_system_hints:
                out.source_system_hints.append("Postgres")
        if b"s3" in data or b"S3" in data:
            if "S3" not in out.source_system_hints:
                out.source_system_hints.append("S3")
        if b"api" in data.lower() or b"requests" in data.lower():
            if "Direct API Extraction" not in out.ingestion_tools:
                out.ingestion_tools.append("Direct API Extraction")
        if b"gcs" in data.lower() or b"google.cloud" in data.lower() or b"sensor" in data.lower():
            if "GCS Sensors" not in out.ingestion_tools:
                out.ingestion_tools.append("GCS Sensors")
        if b"canvas" in data.lower():
            if "Canvas" not in out.source_system_hints:
                out.source_system_hints.append("Canvas")
        if b"openedx" in data.lower() or b"edxorg" in data.lower():
            if "OpenEdX" not in out.source_system_hints:
                out.source_system_hints.append("OpenEdX")
    out.ingestion_tools = list(dict.fromkeys(out.ingestion_tools))


def _content_scan(root: Path, out: IngestionHints) -> None:
    """Augment hints by scanning key files for keywords."""
    keywords_ingestion = [b"airbyte", b"dlt", b"data load", b"ol_warehouse_raw", b"raw__", b"api", b"gcs", b"google.cloud", b"requests", b"sensor"]
    keywords_orchestrator = [b"dagster", b"Dagster"]
    keywords_sources = [b"postgres", b"Postgres", b"S3", b"s3", b"external", b"canvas", b"openedx", b"mitx", b"edxorg", b"api"]
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules"}

    checked = 0
    for path in root.rglob("*"):
        if checked > 100:
            break
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in skip_dirs for part in rel_parts):
            continue
        suf = path.suffix.lower()
        if suf not in (".yaml", ".yml", ".py", ".toml", ".md", ".json"):
            continue
        try:
            data = path.read_bytes()
            if len(data) > 200_000:
                continue
        except OSError:
            continue
        checked += 1
        rel = str(path.relative_to(root))
        if any(k in data for k in keywords_ingestion):
            if "Airbyte" not in out.ingestion_tools and b"airbyte" in data.lower():
                out.ingestion_tools.append("Airbyte")
            if "dlt" not in out.ingestion_tools and (b"dlt" in data or b"data load" in data.lower()):
                out.ingestion_tools.append("dlt")
            if "Direct API Extraction" not in out.ingestion_tools and (b"api" in data.lower() or b"requests" in data.lower()):
                out.ingestion_tools.append("Direct API Extraction")
            if "GCS Sensors" not in out.ingestion_tools and (b"gcs" in data.lower() or b"google.cloud" in data.lower() or b"sensor" in data.lower()):
                out.ingestion_tools.append("GCS Sensors")
            if out.raw_schema_hint is None and (b"ol_warehouse_raw" in data or b"raw__" in data):
                out.raw_schema_hint = "ol_warehouse_raw (or raw__*)"
        if out.orchestrator is None and any(k in data for k in keywords_orchestrator):
            out.orchestrator = "Dagster"
        if len(out.source_system_hints) < 5 and any(k in data for k in keywords_sources):
            if "Postgres" not in out.source_system_hints and (b"postgres" in data or b"Postgres" in data):
                out.source_system_hints.append("Postgres")
            if "S3" not in out.source_system_hints and (b"s3" in data or b"S3" in data):
                out.source_system_hints.append("S3")
            if "Canvas" not in out.source_system_hints and b"canvas" in data.lower():
                out.source_system_hints.append("Canvas")
            if "OpenEdX" not in out.source_system_hints and (b"openedx" in data.lower() or b"edxorg" in data.lower()):
                out.source_system_hints.append("OpenEdX")

    out.ingestion_tools = list(dict.fromkeys(out.ingestion_tools))
