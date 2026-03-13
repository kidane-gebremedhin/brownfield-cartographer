"""Incremental update mode: track file hashes, detect changes, conservative invalidation.

Persists a manifest of content hashes after each run. On the next run, compares
current hashes to the manifest; if identical, artifacts are reused and no re-analysis
is performed. If any file changed, added, or removed, the full pipeline is re-run
and invalidation is logged to cartography_trace.jsonl (added/removed/modified lists).
Future work: re-analyze only changed files and merge with cached graphs to avoid full re-run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from repository.file_discovery import discover_files

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = 1


@dataclass
class ChangeSet:
    """Result of comparing current repo state to prior manifest."""

    unchanged: bool
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    reason: str = ""


def load_manifest(artifact_dir: Path | str) -> dict[str, str] | None:
    """Load prior file hashes from cartography/manifest.json. Returns None if missing or invalid."""
    path = Path(artifact_dir).resolve() / MANIFEST_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != MANIFEST_VERSION:
            return None
        hashes = data.get("file_hashes")
        if not isinstance(hashes, dict):
            return None
        return {k: str(v) for k, v in hashes.items()}
    except (json.JSONDecodeError, OSError):
        return None


def save_manifest(artifact_dir: Path | str, file_hashes: dict[str, str]) -> None:
    """Write manifest with file path -> content hash for the next incremental check."""
    path = Path(artifact_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    payload = {"version": MANIFEST_VERSION, "file_hashes": file_hashes}
    (path / MANIFEST_FILENAME).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def get_current_hashes(
    repo_root: Path | str,
    *,
    exclude_dirs: frozenset[str] | None = None,
) -> dict[str, str]:
    """Return repo-relative path -> SHA-256 content hash. Excludes paths under exclude_dirs (e.g. cartography)."""
    if exclude_dirs is None:
        exclude_dirs = frozenset({"cartography"})
    files = discover_files(repo_root)
    out = {}
    for f in files:
        top = f.path.split("/")[0] if "/" in f.path else f.path.split("\\")[0]
        if top in exclude_dirs:
            continue
        out[f.path] = f.content_hash
    return out


def compute_changes(
    prior_hashes: dict[str, str] | None,
    current_hashes: dict[str, str],
) -> ChangeSet:
    """Compare current hashes to prior. Favor correctness: no prior or any diff -> not unchanged."""
    if prior_hashes is None:
        return ChangeSet(
            unchanged=False,
            added=list(current_hashes),
            removed=[],
            modified=[],
            reason="no prior manifest",
        )
    prior_set = set(prior_hashes)
    current_set = set(current_hashes)
    added = sorted(current_set - prior_set)
    removed = sorted(prior_set - current_set)
    modified = sorted(p for p in (prior_set & current_set) if prior_hashes[p] != current_hashes[p])
    unchanged = len(added) == 0 and len(removed) == 0 and len(modified) == 0
    reason = "no file changes" if unchanged else "file changes detected"
    return ChangeSet(
        unchanged=unchanged,
        added=added,
        removed=removed,
        modified=modified,
        reason=reason,
    )


def append_trace_event(artifact_dir: Path | str, event: dict | "CartographyTraceEntry") -> None:
    """Append a single JSON object as one line to cartography_trace.jsonl."""
    from models.trace import CartographyTraceEntry
    path = Path(artifact_dir).resolve() / "cartography_trace.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(event, CartographyTraceEntry):
        line = event.model_dump_json(exclude_none=True) + "\n"
    else:
        line = json.dumps(event, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def trace_event_for_reuse(change_set: ChangeSet, files_checked: int) -> "CartographyTraceEntry":
    """Build trace event when artifacts are reused."""
    from models.trace import CartographyTraceEntry
    return CartographyTraceEntry(
        event="incremental_reuse",
        reason=change_set.reason,
        files_checked=files_checked,
    )


def trace_event_for_invalidate(change_set: ChangeSet, files_checked: int) -> "CartographyTraceEntry":
    """Build trace event when analysis is invalidated and full run is performed."""
    from models.trace import CartographyTraceEntry
    return CartographyTraceEntry(
        event="incremental_invalidate",
        reason=change_set.reason,
        files_checked=files_checked,
        added=change_set.added,
        removed=change_set.removed,
        modified=change_set.modified,
    )
