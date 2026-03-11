"""Tests for embeddings provider interface and mock."""

import pytest

from llm.embeddings import MockEmbeddingsProvider


def test_mock_embeddings_deterministic():
    p = MockEmbeddingsProvider(dimension=8)
    a = p.embed(["hello", "world"])
    b = p.embed(["hello", "world"])
    assert len(a) == 2
    assert len(a[0]) == 8
    assert a == b


def test_mock_embeddings_different_text_different_vector():
    p = MockEmbeddingsProvider(dimension=4)
    a = p.embed(["x"])
    b = p.embed(["y"])
    assert a[0] != b[0]


def test_mock_embeddings_dimension_override():
    p = MockEmbeddingsProvider(dimension=16)
    out = p.embed(["test"], dimension=4)
    assert len(out[0]) == 4
