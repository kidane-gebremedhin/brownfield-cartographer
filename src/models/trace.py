"""Trace models: CartographyTraceEntry for cartography_trace.jsonl.

Log every agent action, evidence source, and confidence level (audit pattern).
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from models.common import Evidence


class CartographyTraceEntry(BaseModel):
    """A single trace log entry (event) in the cartography run."""
    event: str = Field(description="Event type (e.g. agent_surveyor, incremental_reuse)")
    reason: str | None = None
    files_checked: int | None = None
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    evidence: Evidence | None = None
    payload: dict[str, Any] | None = Field(default=None, description="Extra event payload")
    model_config = {"extra": "allow"}


def agent_trace_entry(
    agent_name: str,
    *,
    evidence_source: str,
    confidence: float = 1.0,
    payload: dict[str, Any] | None = None,
) -> CartographyTraceEntry:
    """Build a trace entry for an agent step (surveyor, hydrologist, semanticist, archivist)."""
    return CartographyTraceEntry(
        event=f"agent_{agent_name}",
        evidence=Evidence(source=evidence_source, confidence=confidence),
        payload=payload or {},
    )
