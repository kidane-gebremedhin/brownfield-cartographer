"""Navigator agent: user-facing query interface over saved graph and semantic artifacts.

Operates from persisted .cartography artifacts only; no full pipeline re-run.
Tools: find_implementation, trace_lineage, blast_radius, explain_module.
Responses distinguish graph-backed answers from semantic inference and include evidence and confidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from query.response_formatter import (
    format_blast_radius_result,
    format_implementation_matches,
    format_lineage_result,
    format_module_explanation,
)
from query.tools import (
    BlastRadiusResult,
    ImplementationMatch,
    LineageResult,
    ModuleExplanation,
    blast_radius as tool_blast_radius,
    explain_module as tool_explain_module,
    find_implementation as tool_find_implementation,
    trace_lineage as tool_trace_lineage,
)


class Navigator:
    """Query interface over an artifact directory (.cartography)."""

    def __init__(self, artifact_dir: Path | str):
        self.artifact_dir = Path(artifact_dir).resolve()

    def find_implementation(self, concept: str, *, max_results: int = 20) -> str:
        """Return formatted list of likely modules/functions implementing the concept."""
        matches = tool_find_implementation(self.artifact_dir, concept, max_results=max_results)
        return format_implementation_matches(matches)

    def trace_lineage(
        self,
        dataset: str,
        direction: Literal["upstream", "downstream"] = "upstream",
        *,
        max_depth: int = 5,
    ) -> str:
        """Return formatted upstream or downstream lineage with evidence."""
        result = tool_trace_lineage(
            self.artifact_dir,
            dataset,
            direction=direction,
            max_depth=max_depth,
        )
        return format_lineage_result(result)

    def blast_radius(self, module_or_dataset: str, *, max_depth: int = 5) -> str:
        """Return formatted downstream impact set with evidence."""
        result = tool_blast_radius(
            self.artifact_dir,
            module_or_dataset,
            max_depth=max_depth,
        )
        return format_blast_radius_result(result)

    def explain_module(self, path: str) -> str:
        """Return formatted structural and semantic explanation of a module."""
        explanation = tool_explain_module(self.artifact_dir, path)
        return format_module_explanation(explanation)
