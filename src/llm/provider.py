"""Provider-agnostic LLM completion interface.

Implementations can wrap OpenAI, Gemini, or a mock for tests.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Interface for LLM completion. Test with MockLLMProvider."""

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        """Return completion for the given prompt. No streaming required."""
        pass


class MockLLMProvider:
    """Deterministic mock for tests. Returns configured responses or a default."""

    def __init__(
        self,
        responses: list[str] | None = None,
        default: str = "mock completion",
    ):
        self.responses = list(responses) if responses else []
        self.default = default
        self._call_count = 0

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        self._call_count += 1
        if self.responses:
            return self.responses[(self._call_count - 1) % len(self.responses)]
        return self.default
