"""Tests for LLM provider interface and mock."""

from llm.provider import MockLLMProvider


def test_mock_provider_default():
    p = MockLLMProvider()
    assert p.complete("hello") == "mock completion"
    assert p.complete("again") == "mock completion"


def test_mock_provider_responses():
    p = MockLLMProvider(responses=["first", "second", "third"])
    assert p.complete("q1") == "first"
    assert p.complete("q2") == "second"
    assert p.complete("q3") == "third"
    assert p.complete("q4") == "first"


def test_mock_provider_accepts_kwargs():
    p = MockLLMProvider(default="ok")
    assert p.complete("x", max_tokens=50, temperature=0.0) == "ok"
