"""Provider-agnostic embeddings for clustering.

Implementations can wrap OpenAI, Gemini, or a mock for tests.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingsProvider(Protocol):
    """Interface for embedding text. Test with MockEmbeddingsProvider."""

    def embed(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        """Return one vector per input text. Dimension may be fixed by the provider."""
        ...


class MockEmbeddingsProvider:
    """Deterministic mock: hashes text to a repeatable vector. Useful for clustering tests."""

    def __init__(self, dimension: int = 32):
        self.dimension = dimension

    def embed(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        dim = dimension or self.dimension
        out = []
        for t in texts:
            h = hash(t) & 0x7FFF_FFFF
            vec = [(float((h + i) % 1000) / 1000.0) - 0.5 for i in range(dim)]
            out.append(vec)
        return out
