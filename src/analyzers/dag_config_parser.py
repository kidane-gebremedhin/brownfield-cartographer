"""YAML / DAG / dbt-like config parsing for lineage hints.

Supports:
- dbt schema/config YAML (models, sources)
- Airflow DAG definitions (tasks, dependencies)
- Prefect flow definitions (task dependencies)
- Emits configuration edges / topology hints for hydrologist

This is best-effort and should never crash the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ConfigEdge(BaseModel):
    """Represents a config-derived relationship (hint)."""

    kind: str = Field(description="CONFIGURES or DEPENDS_ON or AIRFLOW_TASK or PREFECT_TASK")
    source: str = Field(description="Config entity (task/model/source name)")
    target: str = Field(description="Target entity")
    raw: dict[str, Any] | None = Field(default=None, description="Raw YAML fragment")
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)


class ConfigParseResult(BaseModel):
    edges: list[ConfigEdge] = Field(default_factory=list)
    parse_ok: bool = True
    error: str | None = None


def parse_yaml_config(yaml_text: str, *, source_path: str | None = None) -> ConfigParseResult:
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
                            edges.append(ConfigEdge(kind="DEPENDS_ON", source=n, target=name, raw=m))

    # Airflow DAG: tasks with task_id and dependencies (depends_on or upstream_task_ids)
    if isinstance(data, dict):
        dag_id = data.get("dag_id") or (data.get("dag", {}) or {}).get("id") if isinstance(data.get("dag"), dict) else None
        tasks = data.get("tasks")
        if not tasks and "dag" in data and isinstance(data["dag"], dict):
            tasks = data["dag"].get("tasks")
        if isinstance(tasks, list) and tasks:
            task_ids = []
            for t in tasks:
                if isinstance(t, dict) and t.get("task_id"):
                    task_ids.append(t["task_id"])
            for t in tasks:
                if not isinstance(t, dict) or not t.get("task_id"):
                    continue
                tid = t["task_id"]
                # Downstream dependency: tid depends on upstream_task_ids
                for dep in t.get("upstream_task_ids") or t.get("depends_on") or []:
                    if isinstance(dep, str) and dep in task_ids:
                        edges.append(ConfigEdge(kind="AIRFLOW_TASK", source=dep, target=tid, raw=t))
                # Operator often references table/dataset via params or template
                if dag_id:
                    edges.append(ConfigEdge(kind="AIRFLOW_TASK", source=f"dag:{dag_id}", target=tid, raw=t))

    # Prefect: flow with task dependencies (task mapping or run order)
    if isinstance(data, dict):
        flow_name = data.get("name") or data.get("flow_name")
        tasks_prefect = data.get("tasks") or data.get("task_definitions")
        if isinstance(tasks_prefect, list) and flow_name:
            for t in tasks_prefect:
                if isinstance(t, dict) and t.get("name"):
                    tn = t["name"]
                    edges.append(ConfigEdge(kind="PREFECT_TASK", source=f"flow:{flow_name}", target=tn, raw=t))

    return ConfigParseResult(edges=edges)
