from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    source: str = Field(description="Evidence source")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    raw: str | None = None
    metadata: dict[str, Any] | None = None
    model_config = {"extra": "forbid"}
