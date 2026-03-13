"""DeepSeek-only LLM provider for Semanticist.

Request timeout: 180s default; set CARTOGRAPHER_LLM_TIMEOUT (seconds) in .env for slow/large runs.

- Bulk tier (purpose statements, drift classification, cluster labels): DeepSeek model for
  per-module semantic extraction. Default model: deepseek-chat.
- Synthesis tier (Five Day-One Answers): same or a different DeepSeek model for the single
  synthesis prompt. Configure CARTOGRAPHER_DEEPSEEK_MODEL (bulk) and optionally
  CARTOGRAPHER_SYNTHESIS_MODEL (synthesis) in .env.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from llm.budget import ModelTier

logger = logging.getLogger(__name__)

LLM_TIMEOUT = max(60, int(os.environ.get("CARTOGRAPHER_LLM_TIMEOUT", "180")))

# DeepSeek API: one model for bulk, optional separate model for synthesis
DEFAULT_DEEPSEEK_MODEL = os.environ.get("CARTOGRAPHER_DEEPSEEK_MODEL", "deepseek-chat")
DEFAULT_SYNTHESIS_MODEL = os.environ.get("CARTOGRAPHER_SYNTHESIS_MODEL", "deepseek-chat")


class TieredLLMProvider:
    """Uses DeepSeek API for all LLM calls. Tier selects which model (bulk vs synthesis)."""

    def __init__(
        self,
        *,
        deepseek_api_key: str | None = None,
        bulk_model: str | None = None,
        synthesis_model: str | None = None,
        deepseek_base_url: str = "https://api.deepseek.com/v1",
    ):
        self.deepseek_api_key = (deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
        self.bulk_model = bulk_model or DEFAULT_DEEPSEEK_MODEL
        self.synthesis_model = synthesis_model or DEFAULT_SYNTHESIS_MODEL
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
        model = self.synthesis_model if use_synthesis else self.bulk_model
        if not self.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is required; set it in .env")
        return _deepseek_chat(
            base_url=self.deepseek_base_url,
            api_key=self.deepseek_api_key,
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=LLM_TIMEOUT,
        )


def _deepseek_chat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    timeout: int = 180,
) -> str:
    """Call DeepSeek API (https://api.deepseek.com). Retries once on timeout."""
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
    last_err: BaseException | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8") if e.fp else ""
            logger.warning("DeepSeek HTTP %s: %s", e.code, body_err[:500])
            raise RuntimeError(f"LLM request failed: {e.code} {body_err[:200]}") from e
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            is_timeout = getattr(e, "reason", None) is not None and "timed out" in str(e.reason).lower()
            if is_timeout and attempt == 0:
                logger.debug("DeepSeek timeout, retrying once: %s", e)
                time.sleep(2)
                continue
            logger.warning("DeepSeek request failed: %s", e)
            raise RuntimeError(f"DeepSeek request failed: {e}") from e
    else:
        if last_err is not None:
            raise RuntimeError(f"DeepSeek request failed: {last_err}") from last_err
        raise RuntimeError("DeepSeek request failed")

    choices = out.get("choices") or []
    if not choices:
        raise RuntimeError("DeepSeek returned no choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    return content.strip()


def create_tiered_provider_from_env() -> TieredLLMProvider | None:
    """Create TieredLLMProvider from env. Requires DEEPSEEK_API_KEY."""
    deepseek = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not deepseek:
        return None
    return TieredLLMProvider(deepseek_api_key=deepseek or None)
