"""Node types for the knowledge graph."""
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ModuleNode(BaseModel):
    """A source module (file) in the codebase."""
    path: str = Field(description="Repo-relative file path")
    language: str = Field(description="Language identifier")
    purpose_statement: str | None = None
    domain_cluster: str | None = None
    complexity_score: float = 0.0
    change_velocity_30d: int = Field(default=0, ge=0)
    change_velocity_90d: int = Field(default=0, ge=0)
    is_dead_code_candidate: bool = False
    last_modified: datetime | None = None
    loc: int = Field(default=0, ge=0)
    comment_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    public_api_count: int = Field(default=0, ge=0)
    model_config = {"extra": "forbid"}


class FunctionNode(BaseModel):
    """A function or callable within a module."""
    qualified_name: str = Field(description="Fully qualified name")
    parent_module: str = Field(description="Repo-relative path of the containing module")
    signature: str | None = None
    purpose_statement: str | None = None
    call_count_within_repo: int = Field(default=0, ge=0)
    is_public_api: bool = False
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    model_config = {"extra": "forbid"}


class DatasetNode(BaseModel):
    """A dataset in the lineage graph."""
    name: str = Field(description="Dataset identifier")
    storage_type: Literal["table", "file", "stream", "api"] = "table"
    schema_snapshot: dict | None = None
    freshness_sla: str | None = None
    owner: str | None = None
    is_source_of_truth: bool | None = None
    model_config = {"extra": "forbid"}


class TransformationNode(BaseModel):
    """A transformation step in the lineage graph."""
    id: str = Field(description="Unique id")
    source_datasets: list[str] = Field(default_factory=list)
    target_datasets: list[str] = Field(default_factory=list)
    transformation_type: str = "sql"
    source_file: str = Field(description="Repo-relative path of the transformation file")
    line_range: tuple[int, int] | None = None
    sql_query_if_applicable: str | None = None
    model_config = {"extra": "forbid"}
