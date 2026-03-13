from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """Evidence for a claim or answer, including where it was observed."""

    source: str = Field(description="High-level evidence source (e.g. surveyor, hydrologist, git)")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    raw: str | None = None
    metadata: dict[str, Any] | None = None

    # Optional structured location and method details for auditability
    file_path: str | None = Field(default=None, description="Source file path for this evidence, if applicable")
    line_start: int | None = Field(default=None, description="1-based start line for the evidence span")
    line_end: int | None = Field(default=None, description="1-based end line for the evidence span")
    analysis_method: str | None = Field(
        default=None,
        description="Mechanism that produced this evidence (e.g. graph_traversal, static_analysis, git_velocity)",
    )
    notes: str | None = Field(default=None, description="Short human-readable explanation of this evidence")

    model_config = {"extra": "forbid"}
