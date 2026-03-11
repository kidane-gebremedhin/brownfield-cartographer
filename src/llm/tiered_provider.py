"""Tiered LLM provider: cheap models for bulk, expensive for synthesis.

Two distinct API keys (set in .env):
- OPENROUTER_API_KEY: for OpenRouter (Gemini Flash, Mistral, etc.). Used for bulk tier
  and for synthesis if you do not set DEEPSEEK_API_KEY.
- DEEPSEEK_API_KEY: for DeepSeek's API directly (https://api.deepseek.com). When set,
  synthesis tier uses DeepSeek direct; optionally use DeepSeek for bulk if OpenRouter is not set.

Configure via .env: OPENROUTER_API_KEY, DEEPSEEK_API_KEY, CARTOGRAPHER_BULK_MODEL, CARTOGRAPHER_SYNTHESIS_MODEL.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from llm.budget import ModelTier

logger = logging.getLogger(__name__)

# OpenRouter model IDs (used when OPENROUTER_API_KEY is set)
DEFAULT_BULK_MODEL = os.environ.get("CARTOGRAPHER_BULK_MODEL", "google/gemini-2.0-flash-001")
# Synthesis via OpenRouter (only if DEEPSEEK_API_KEY is not set)
DEFAULT_SYNTHESIS_MODEL_OPENROUTER = os.environ.get("CARTOGRAPHER_SYNTHESIS_MODEL", "deepseek/deepseek-chat")
# DeepSeek direct API model (when DEEPSEEK_API_KEY is set)
DEFAULT_DEEPSEEK_MODEL = os.environ.get("CARTOGRAPHER_DEEPSEEK_MODEL", "deepseek-chat")


class TieredLLMProvider:
    """Uses one model for bulk (purpose/drift/cluster labels) and another for synthesis (day-one).
    Bulk: OpenRouter (Gemini/Mistral) or DeepSeek direct if only DEEPSEEK_API_KEY is set.
    Synthesis: DeepSeek API direct if DEEPSEEK_API_KEY set, else OpenRouter.
    """

    def __init__(
        self,
        *,
        openrouter_api_key: str | None = None,
        deepseek_api_key: str | None = None,
        bulk_model: str | None = None,
        synthesis_model_openrouter: str | None = None,
        deepseek_model: str | None = None,
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        deepseek_base_url: str = "https://api.deepseek.com/v1",
    ):
        self.openrouter_api_key = (openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
        self.deepseek_api_key = (deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        self.bulk_model = bulk_model or DEFAULT_BULK_MODEL
        self.synthesis_model_openrouter = synthesis_model_openrouter or DEFAULT_SYNTHESIS_MODEL_OPENROUTER
        self.deepseek_model = deepseek_model or DEFAULT_DEEPSEEK_MODEL
        self.openrouter_base_url = openrouter_base_url.rstrip("/")
        self.deepseek_base_url = deepseek_base_url.rstrip("/")

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        tier: ModelTier | None = None,
    ) -> str:
        use_synthesis = tier == "synthesis"
        # Synthesis: prefer DeepSeek direct when DEEPSEEK_API_KEY is set
        if use_synthesis and self.deepseek_api_key:
            return _deepseek_chat(
                base_url=self.deepseek_base_url,
                api_key=self.deepseek_api_key,
                model=self.deepseek_model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        # Bulk or synthesis without DeepSeek key: use OpenRouter when OPENROUTER_API_KEY is set
        if self.openrouter_api_key:
            model = self.synthesis_model_openrouter if use_synthesis else self.bulk_model
            return _openrouter_chat(
                base_url=self.openrouter_base_url,
                api_key=self.openrouter_api_key,
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        # Only DeepSeek key set: use DeepSeek for both bulk and synthesis
        if self.deepseek_api_key:
            return _deepseek_chat(
                base_url=self.deepseek_base_url,
                api_key=self.deepseek_api_key,
                model=self.deepseek_model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        raise ValueError("Set OPENROUTER_API_KEY and/or DEEPSEEK_API_KEY in .env for LLM calls")


def _openrouter_chat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> str:
    """Call OpenRouter chat completion (Gemini, Mistral, etc.)."""
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required for OpenRouter calls")
    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/brownfield-cartographer",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8") if e.fp else ""
        logger.warning("OpenRouter HTTP %s: %s", e.code, body_err[:500])
        raise RuntimeError(f"LLM request failed: {e.code} {body_err[:200]}") from e
    except urllib.error.URLError as e:
        logger.warning("OpenRouter request failed: %s", e)
        raise RuntimeError(f"LLM request failed: {e}") from e

    choices = out.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    return content.strip()


def _deepseek_chat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> str:
    """Call DeepSeek API directly (https://api.deepseek.com)."""
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek calls")
    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8") if e.fp else ""
        logger.warning("DeepSeek HTTP %s: %s", e.code, body_err[:500])
        raise RuntimeError(f"DeepSeek request failed: {e.code} {body_err[:200]}") from e
    except urllib.error.URLError as e:
        logger.warning("DeepSeek request failed: %s", e)
        raise RuntimeError(f"DeepSeek request failed: {e}") from e

    choices = out.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek returned no choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    return content.strip()


def create_tiered_provider_from_env() -> TieredLLMProvider | None:
    """Create TieredLLMProvider from env. Needs OPENROUTER_API_KEY and/or DEEPSEEK_API_KEY."""
    openrouter = os.environ.get("OPENROUTER_API_KEY", "").strip()
    deepseek = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not openrouter and not deepseek:
        return None
    return TieredLLMProvider(
        openrouter_api_key=openrouter or None,
        deepseek_api_key=deepseek or None,
    )
