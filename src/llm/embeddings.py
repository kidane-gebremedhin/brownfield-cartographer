"""Provider-agnostic embeddings for clustering.

Implementations can wrap OpenAI, Gemini, or a mock for tests.
Use OPENAI_API_KEY for real embeddings; otherwise MockEmbeddingsProvider is used.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingsProvider(Protocol):
    """Interface for embedding text. Test with MockEmbeddingsProvider."""

    def embed(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        """Return one vector per input text. Dimension may be fixed by the provider."""
        ...


def create_embeddings_from_env():
    """Return an EmbeddingsProvider from env: OpenAI if OPENAI_API_KEY set, else Mock."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return OpenAIEmbeddingsProvider(api_key=key)
    return MockEmbeddingsProvider()


class OpenAIEmbeddingsProvider:
    """OpenAI text-embedding-3-small for domain clustering. Requires OPENAI_API_KEY."""

    def __init__(self, *, api_key: str | None = None, model: str = "text-embedding-3-small", dimension: int = 256):
        self.api_key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        self.model = model
        self.dimension = dimension

    def embed(self, texts: list[str], *, dimension: int | None = None) -> list[list[float]]:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
        dim = dimension or self.dimension
        out = []
        # API allows batch but has token limit; process in chunks of 20
        for i in range(0, len(texts), 20):
            chunk = texts[i : i + 20]
            vecs = _openai_embed(self.api_key, chunk, model=self.model, dimensions=min(dim, 3072))
            out.extend(vecs)
        return out


def _openai_embed(api_key: str, texts: list[str], model: str = "text-embedding-3-small", dimensions: int = 256) -> list[list[float]]:
    url = "https://api.openai.com/v1/embeddings"
    body = {"model": model, "input": texts, "dimensions": dimensions}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8") if e.fp else ""
        logger.warning("OpenAI embeddings HTTP %s: %s", e.code, body_err[:300])
        raise RuntimeError(f"Embeddings failed: {e.code}") from e
    data_list = out.get("data") or []
    data_list.sort(key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in data_list]


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
