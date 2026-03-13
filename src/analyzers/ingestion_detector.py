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
class IngestionEvidence:
    """Single evidence match supporting ingestion hints."""

    file_path: str
    line: int | None
    keyword: str
    category: str  # e.g. "tool", "source_system", "raw_schema", "orchestrator", "config"


@dataclass
class IngestionHints:
    """Signals about how data is ingested into the warehouse (for Day-One)."""

    ingestion_tools: list[str] = field(default_factory=list)  # e.g. ["Airbyte", "dlt"]
    orchestrator: str | None = None  # e.g. "Dagster"
    config_paths: list[str] = field(default_factory=list)  # e.g. ["docker-compose.yaml", "dg_projects/"]
    entry_point_paths: list[str] = field(default_factory=list)  # specific file paths, not dirs
    raw_schema_hint: str | None = None  # e.g. "ol_warehouse_raw"
    source_system_hints: list[str] = field(default_factory=list)  # e.g. ["Postgres", "S3"]
    evidence: list[IngestionEvidence] = field(default_factory=list)


def detect_ingestion(repo_root: Path | str) -> IngestionHints:
    """Scan repo for ingestion tooling and orchestrator. Best-effort; never raises."""
    root = Path(repo_root).resolve()
    out = IngestionHints()

    if not root.is_dir():
        return out

    # Path-based detection (docker-compose, Airbyte/dlt projects, Dagster deployments)
    for p in root.iterdir():
        if p.name.startswith("."):
            continue
        name_lower = p.name.lower()
        if "airbyte" in name_lower:
            out.ingestion_tools.append("Airbyte")
            out.config_paths.append(p.name + "/")
            out.evidence.append(
                IngestionEvidence(
                    file_path=p.name + "/",
                    line=None,
                    keyword="airbyte",
                    category="tool",
                )
            )
        if "dlt" in name_lower and "dlt" not in out.ingestion_tools:
            # avoid duplicates from paths like "dlt_config"
            if "dlt" not in [t.lower() for t in out.ingestion_tools]:
                out.ingestion_tools.append("dlt")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=p.name + "/",
                        line=None,
                        keyword="dlt",
                        category="tool",
                    )
                )
        if "dagster" in name_lower or name_lower == "dg_projects" or name_lower == "dg_deployments":
            if out.orchestrator is None:
                out.orchestrator = "Dagster"
            if p.is_dir() and p.name not in out.config_paths:
                out.config_paths.append(p.name + "/")
            out.evidence.append(
                IngestionEvidence(
                    file_path=p.name + "/",
                    line=None,
                    keyword="dagster",
                    category="orchestrator",
                )
            )

    if (root / "docker-compose.yaml").exists() or (root / "docker-compose.yml").exists():
        if "docker-compose.yaml" not in out.config_paths:
            out.config_paths.append("docker-compose.yaml")
        out.evidence.append(
            IngestionEvidence(
                file_path="docker-compose.yaml",
                line=None,
                keyword="docker-compose",
                category="config",
            )
        )

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

    # Resolve generic config_paths to specific entry point file paths
    try:
        _resolve_entry_point_paths(root, out)
    except Exception as e:
        logger.debug("Entry point resolution failed: %s", e)

    return out


def _resolve_entry_point_paths(root: Path, out: IngestionHints) -> None:
    """Populate entry_point_paths with specific files, not generic directories."""
    seen: set[str] = set()
    entry_points: list[str] = []
    max_paths = 12

    def add(path: str) -> None:
        if path not in seen and len(entry_points) < max_paths:
            seen.add(path)
            entry_points.append(path)

    # 1. Add config_paths that are already files (no trailing slash)
    for p in out.config_paths:
        if not p.endswith("/") and (root / p).is_file():
            add(p)

    # 2. For each directory in config_paths, resolve to known entry point files
    for p in out.config_paths:
        if not p.endswith("/"):
            continue
        dir_path = root / p.rstrip("/")
        if not dir_path.is_dir():
            continue
        name_lower = dir_path.name.lower()

        if name_lower == "dg_projects":
            # Dagster projects: */*/definitions.py
            for defs in dir_path.glob("*/*/definitions.py"):
                if defs.is_file():
                    rel = str(defs.relative_to(root))
                    add(rel)
        elif name_lower == "dg_deployments":
            # Deployment scripts and workspace config
            for f in dir_path.glob("*.py"):
                if f.is_file():
                    add(str(f.relative_to(root)))
            for cfg in dir_path.rglob("dagster.yaml"):
                if cfg.is_file():
                    add(str(cfg.relative_to(root)))
            for ws in dir_path.rglob("workspace.yaml"):
                if ws.is_file():
                    add(str(ws.relative_to(root)))
        elif "airbyte" in name_lower:
            for dc in dir_path.rglob("docker-compose*.yaml"):
                if dc.is_file():
                    add(str(dc.relative_to(root)))
            for dc in dir_path.rglob("docker-compose*.yml"):
                if dc.is_file():
                    add(str(dc.relative_to(root)))
        elif "dlt" in name_lower:
            for py in dir_path.glob("*.py"):
                if py.is_file():
                    add(str(py.relative_to(root)))

    # 3. Add evidence file_paths that are entry-point-like (under ingestion dirs or known config names)
    config_dir_prefixes = tuple(f"{d.rstrip('/')}/" for d in out.config_paths if d.endswith("/"))
    entry_point_names = ("definitions.py", "dagster.yaml", "workspace.yaml", "docker-compose.yaml", "docker-compose.yml")
    relevance = {"config", "orchestrator", "tool"}
    for e in out.evidence:
        if e.category not in relevance or not e.file_path or e.file_path.endswith("/"):
            continue
        full = root / e.file_path
        if not full.is_file():
            continue
        # Only include files under config dirs or with known entry point names
        under_config = any(e.file_path.startswith(prefix) for prefix in config_dir_prefixes)
        is_entry_name = e.file_path.endswith(entry_point_names) or "/" not in e.file_path and full.name in entry_point_names
        if under_config or is_entry_name:
            add(e.file_path)

    out.entry_point_paths = entry_points


def _scan_key_files(root: Path, out: IngestionHints) -> None:
    """Scan README and docker-compose first for Airbyte, dlt, Dagster and raw schemas."""
    for name in ("README.md", "README.MD", "docker-compose.yaml", "docker-compose.yml"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            if "airbyte" in low:
                if "Airbyte" not in out.ingestion_tools:
                    out.ingestion_tools.append("Airbyte")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="airbyte",
                        category="tool",
                    )
                )
            if ("dlt" in line or "data load" in low) and "dlt" not in [t.lower() for t in out.ingestion_tools]:
                out.ingestion_tools.append("dlt")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="dlt",
                        category="tool",
                    )
                )
            if "dagster" in line and out.orchestrator is None:
                out.orchestrator = "Dagster"
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="dagster",
                        category="orchestrator",
                    )
                )
            if "ol_warehouse_raw" in line or "raw__" in line:
                if out.raw_schema_hint is None:
                    out.raw_schema_hint = "ol_warehouse_raw (or raw__*)"
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="raw__",
                        category="raw_schema",
                    )
                )
            if "postgres" in low:
                if "Postgres" not in out.source_system_hints:
                    out.source_system_hints.append("Postgres")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="postgres",
                        category="source_system",
                    )
                )
            if "s3" in line:
                if "S3" not in out.source_system_hints:
                    out.source_system_hints.append("S3")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="s3",
                        category="source_system",
                    )
                )
            if "api" in low or "requests" in low:
                if "Direct API Extraction" not in out.ingestion_tools:
                    out.ingestion_tools.append("Direct API Extraction")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="api",
                        category="tool",
                    )
                )
            if "gcs" in low or "google.cloud" in low or "sensor" in low:
                if "GCS Sensors" not in out.ingestion_tools:
                    out.ingestion_tools.append("GCS Sensors")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="gcs",
                        category="tool",
                    )
                )
            if "canvas" in low:
                if "Canvas" not in out.source_system_hints:
                    out.source_system_hints.append("Canvas")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="canvas",
                        category="source_system",
                    )
                )
            if "openedx" in low or "edxorg" in low or "mitx" in low:
                if "OpenEdX" not in out.source_system_hints:
                    out.source_system_hints.append("OpenEdX")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="openedx",
                        category="source_system",
                    )
                )
    out.ingestion_tools = list(dict.fromkeys(out.ingestion_tools))


def _content_scan(root: Path, out: IngestionHints) -> None:
    """Augment hints by scanning key files for keywords (line-aware)."""
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
            text = path.read_text(encoding="utf-8", errors="ignore")
            # skip extremely large files to keep the detector lightweight
            if len(text) > 200_000:
                continue
        except OSError:
            continue
        checked += 1
        rel = str(path.relative_to(root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            low = line.lower()

            # dbt source-generation scripts and ingestion tools
            if "airbyte" in low:
                if "Airbyte" not in out.ingestion_tools:
                    out.ingestion_tools.append("Airbyte")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="airbyte",
                        category="tool",
                    )
                )
            if ("dlt" in line or "data load" in low) and "dlt" not in [t.lower() for t in out.ingestion_tools]:
                out.ingestion_tools.append("dlt")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="dlt",
                        category="tool",
                    )
                )
            if "dbt" in low and "source" in low:
                if "dbt source generation" not in out.ingestion_tools:
                    out.ingestion_tools.append("dbt source generation")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="dbt source",
                        category="tool",
                    )
                )

            # Raw schemas
            if "ol_warehouse_" in line and "_raw" in line or "raw__" in line:
                if out.raw_schema_hint is None:
                    out.raw_schema_hint = "ol_warehouse_raw (or raw__*)"
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="raw__",
                        category="raw_schema",
                    )
                )

            # Orchestrator references (Dagster)
            if out.orchestrator is None and "dagster" in low:
                out.orchestrator = "Dagster"
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="dagster",
                        category="orchestrator",
                    )
                )

            # Source systems (Postgres, S3, Canvas, OpenEdX)
            if "postgres" in low:
                if "Postgres" not in out.source_system_hints:
                    out.source_system_hints.append("Postgres")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="postgres",
                        category="source_system",
                    )
                )
            if "s3" in line:
                if "S3" not in out.source_system_hints:
                    out.source_system_hints.append("S3")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="s3",
                        category="source_system",
                    )
                )
            if "canvas" in low:
                if "Canvas" not in out.source_system_hints:
                    out.source_system_hints.append("Canvas")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="canvas",
                        category="source_system",
                    )
                )
            if "openedx" in low or "edxorg" in low or "mitx" in low:
                if "OpenEdX" not in out.source_system_hints:
                    out.source_system_hints.append("OpenEdX")
                out.evidence.append(
                    IngestionEvidence(
                        file_path=rel,
                        line=lineno,
                        keyword="openedx",
                        category="source_system",
                    )
                )

    out.ingestion_tools = list(dict.fromkeys(out.ingestion_tools))
