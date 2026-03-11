"""YAML / DAG / dbt-like config parsing for lineage hints.

Supports:
- dbt schema/config YAML (models, sources)
- emits configuration edges / topology hints for hydrologist

This is best-effort and should never crash the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ConfigEdge(BaseModel):
    """Represents a config-derived relationship (hint)."""

    kind: str = Field(description="CONFIGURES or DEPENDS_ON")
    source: str = Field(description="Config entity")
    target: str = Field(description="Target entity")
    raw: dict[str, Any] | None = Field(default=None, description="Raw YAML fragment")


class ConfigParseResult(BaseModel):
    edges: list[ConfigEdge] = Field(default_factory=list)
    parse_ok: bool = True
    error: str | None = None


def parse_yaml_config(yaml_text: str) -> ConfigParseResult:
    try:
        import yaml
    except Exception as e:
        return ConfigParseResult(parse_ok=False, error=f"pyyaml unavailable: {e}")

    try:
        data = yaml.safe_load(yaml_text) or {}
    except Exception as e:
        logger.warning("YAML parse failed: %s", e)
        return ConfigParseResult(parse_ok=False, error=str(e))

    edges: list[ConfigEdge] = []

    # dbt-like schema: sources: [{name, tables:[{name}]}]
    sources = data.get("sources") if isinstance(data, dict) else None
    if isinstance(sources, list):
        for s in sources:
            if not isinstance(s, dict):
                continue
            src_name = s.get("name")
            for t in s.get("tables", []) or []:
                if isinstance(t, dict) and src_name and t.get("name"):
                    edges.append(
                        ConfigEdge(kind="CONFIGURES", source=f"source:{src_name}", target=f"{src_name}.{t['name']}", raw=t)
                    )

    # dbt-like models: [{name, depends_on: {nodes: [...]}}]
    models = data.get("models") if isinstance(data, dict) else None
    if isinstance(models, list):
        for m in models:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            name = m["name"]
            depends_on = m.get("depends_on")
            if isinstance(depends_on, dict):
                nodes = depends_on.get("nodes")
                if isinstance(nodes, list):
                    for n in nodes:
                        if isinstance(n, str):
                            edges.append(ConfigEdge(kind="DEPENDS_ON", source=f"model:{name}", target=n, raw=m))

    return ConfigParseResult(edges=edges)
