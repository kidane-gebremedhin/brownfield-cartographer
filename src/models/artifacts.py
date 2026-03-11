from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from models.graph_models import DataLineageGraph, ModuleGraph


class CODEBASEContext(BaseModel):
    architecture_overview: str | None = None
    critical_path: str | None = None
    data_sources: list[str] = Field(default_factory=list)
    data_sinks: list[str] = Field(default_factory=list)
    known_debt: str | None = None
    recent_velocity: list[dict[str, Any]] = Field(default_factory=list)
    module_purpose_index: list[dict[str, str]] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class OnboardingBrief(BaseModel):
    day_one_answers_markdown: str | None = None
    evidence_citations: list[str] = Field(default_factory=list)
    confidence_notes: str | None = None
    known_unknowns: str | None = None
    model_config = {"extra": "forbid"}


class CartographyArtifacts(BaseModel):
    artifact_dir: str | None = None
    module_graph: ModuleGraph | None = None
    lineage_graph: DataLineageGraph | None = None
    codebase_context: CODEBASEContext | None = None
    onboarding_brief: OnboardingBrief | None = None
    model_config = {"extra": "forbid"}
