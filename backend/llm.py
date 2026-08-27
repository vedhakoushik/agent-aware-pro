"""
LLM access — a thin async router over OpenAI-compatible providers with failover.

The LLM is the REASONING layer only (understand the query, rank + explain structured
data). It never fetches or scrapes data. Providers are tried in order; a rate-limited
or failed provider falls over to the next, so a search never dies on one quota.

Order: Gemini (fast, strong, key-pool rotation) → Groq (overflow) → Ollama (local,
free safety net). Gemini goes first as of 2026-08-27: Groq's free `llama-3.3-70b-versatile`
was decommissioned (404) and its replacement wasn't verified working, whereas Gemini's
multi-key pool gives reliable throughput for testing/eval — see ROUTE overrides in .env.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from .config import settings

logger = logging.getLogger(__name__)

_clients: dict[str, AsyncOpenAI] = {}


def _gemini_keys() -> list[str]:
    """Merge the pool (GEMINI_API_KEYS) with the singular key, deduped, order kept."""
    keys = [k.strip() for k in (settings.gemini_api_keys or "").split(",") if k.strip()]
    if settings.gemini_api_key and settings.gemini_api_key not in keys:
        keys.append(settings.gemini_api_key)
    return keys


def _provider_chain() -> list[tuple[str, str, str, str]]:
    """[(name, base_url, api_key, model)] in priority order, only configured ones.
    Gemini expands into one chain entry PER pooled key, so a per-key rate limit fails
    over to the next key before giving up on the provider entirely."""
    chain: list[tuple[str, str, str, str]] = []
    gem_keys = _gemini_keys()
    for i, key in enumerate(gem_keys):
        chain.append((f"gemini#{i}", "https://generativelanguage.googleapis.com/v1beta/openai/",
                      key, "gemini-3.6-flash"))
    if settings.groq_api_key:
        chain.append(("groq", "https://api.groq.com/openai/v1",
                      settings.groq_api_key, "llama-3.3-70b-versatile"))
    if settings.ollama_enabled:
        chain.append(("ollama", settings.ollama_base_url, "ollama", settings.ollama_model))
    return chain


def _client(name: str, base_url: str, api_key: str) -> AsyncOpenAI:
    if name not in _clients:
        _clients[name] = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _clients[name]


def _retryable(err: Exception) -> bool:
    s = str(err).lower()
    return any(k in s for k in ("rate", "429", "quota", "exhausted", "overloaded",
                                "503", "timeout", "temporarily",
                                "401", "403", "invalid api key", "unauthorized"))


async def complete_json(system: str, user: str, *, max_tokens: int = 1200) -> Optional[dict]:
    """Run a JSON-mode completion through the provider chain. Returns parsed dict or None."""
    chain = _provider_chain()
    if not chain:
        logger.warning("No LLM provider configured — reasoning disabled.")
        return None
    last_err = None
    for i, (name, base_url, api_key, model) in enumerate(chain):
        try:
            resp = await _client(name, base_url, api_key).chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            last_err = e
            if i < len(chain) - 1 and _retryable(e):
                logger.warning(f"LLM {name} failed ({str(e)[:70]}); failing over")
                continue
            logger.warning(f"LLM call failed: {e}")
            return None
    logger.warning(f"All LLM providers failed: {last_err}")
    return None
