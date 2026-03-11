"""Edge types for the knowledge graph.

Typed edges with optional evidence; JSON-serializable.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from models.common import Evidence


class EdgeType(str, Enum):
    """Canonical edge types: module graph (IMPORTS, CALLS) and lineage (CONSUMES, PRODUCES, CONFIGURES)."""
    IMPORTS = "imports"
    CALLS = "calls"
    CONSUMES = "consumes"
    PRODUCES = "produces"
    CONFIGURES = "configures"


class TypedEdge(BaseModel):
    """A directed edge with type and optional evidence."""
    source: str = Field(description="Source node id or path")
    target: str = Field(description="Target node id or path")
    edge_type: EdgeType = Field(description="Kind of relationship")
    evidence: Evidence | None = Field(default=None, description="Optional evidence metadata")
    model_config = {"extra": "forbid"}
