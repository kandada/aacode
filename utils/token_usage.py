# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""Token estimation, provider-usage normalization, pricing, and prefix diagnostics.

The canonical usage shape used across AACode is deliberately disjoint:

    prompt_total   = uncached_input + cache_read + cache_write
    uncached_input = prompt tokens billed at the full input price
    cache_read     = prompt tokens served from the provider prefix cache
    cache_write    = prompt tokens written to the provider cache
    output         = completion tokens (reasoning is a subset, never added twice)

Provider fields are normalized into this shape so compaction, usage display and
cost estimation all read the same numbers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional

try:  # tiktoken is optional; callers may pass an encoding.
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    tiktoken = None


CJK_RANGES = (
    (0x3400, 0x4DBF),   # CJK Extension A
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
    (0x3040, 0x30FF),   # Hiragana + Katakana
    (0xAC00, 0xD7AF),   # Hangul Syllables
    (0x20000, 0x2FA1F), # CJK Extension B-F
)


def is_cjk_char(char: str) -> bool:
    """Return whether a character belongs to a CJK/kana/hangul block."""
    code = ord(char)
    for start, end in CJK_RANGES:
        if start <= code <= end:
            return True
    return False


def _encode_count(encoding: Any, text: str) -> Optional[int]:
    if encoding is None:
        return None
    try:
        return len(encoding.encode(text))
    except Exception:
        return None


def estimate_text_tokens(text: str, encoding: Any = None) -> int:
    """Estimate tokens for text, preferring a real tokenizer and falling back to a
    CJK-aware density heuristic.

    The previous ``len(text) // 4`` fallback underestimates Chinese/Japanese/Korean
    text by roughly 2-3x, which made the compaction trigger fire far too late.
    """
    if not text:
        return 0
    if encoding is not None:
        counted = _encode_count(encoding, text)
        if counted is not None:
            return counted
    if tiktoken is not None and encoding is None:
        # Do not download encodings implicitly; only use an already cached one.
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            counted = _encode_count(encoding, text)
            if counted is not None:
                return counted
        except Exception:
            pass

    cjk = 0
    other = 0
    for char in text:
        if is_cjk_char(char):
            cjk += 1
        else:
            other += 1
    # CJK: ~1.6 chars/token; ASCII/code: ~4 chars/token, plus a small framing cost.
    return int(cjk / 1.6 + 0.999) + int(other / 4 + 0.999) + 1


def estimate_message_tokens(
    message: Dict[str, Any],
    encoding: Any = None,
    include_reasoning: bool = False,
) -> int:
    """Estimate the prompt-side price of one model-visible message.

    Reasoning content is an output-side cost on DeepSeek and is excluded by
    default; callers that need the old estimate can request it explicitly.
    """
    total = 0
    content = message.get("content", "")
    if isinstance(content, (dict, list)):
        total += estimate_text_tokens(json.dumps(content, ensure_ascii=False), encoding)
    elif content:
        total += estimate_text_tokens(str(content), encoding)

    if include_reasoning and message.get("reasoning_content"):
        total += estimate_text_tokens(str(message["reasoning_content"]), encoding)

    tool_calls = message.get("tool_calls")
    if tool_calls:
        total += estimate_text_tokens(json.dumps(tool_calls, ensure_ascii=False), encoding)
    if message.get("tool_call_id"):
        total += estimate_text_tokens(str(message["tool_call_id"]), encoding)
    # Role framing and message separators.
    total += 4
    return total


def estimate_messages_tokens(
    messages: Iterable[Dict[str, Any]],
    encoding: Any = None,
    include_reasoning: bool = False,
) -> int:
    return sum(
        estimate_message_tokens(msg, encoding, include_reasoning=include_reasoning)
        for msg in messages
    )


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def canonical_from_normalized(
    normalized: Optional[Dict[str, Any]],
    provider: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """Convert the legacy normalized usage dict into the canonical disjoint shape."""
    if not normalized:
        return None
    prompt_total = _as_int(normalized.get("input_tokens"))
    cache_read = _as_int(normalized.get("cache_read_tokens"))
    cache_write = _as_int(normalized.get("cache_write_tokens"))
    output = _as_int(normalized.get("output_tokens"))
    reasoning = _as_int(normalized.get("reasoning_tokens"))
    uncached = _as_int(normalized.get("cache_miss_tokens"))
    if uncached <= 0 and prompt_total > 0:
        uncached = max(prompt_total - cache_read - cache_write, 0)
    # Keep prompt_total internally consistent even when a gateway reports only
    # the uncached portion (Anthropic's input_tokens).
    computed_total = uncached + cache_read + cache_write
    if computed_total > 0:
        prompt_total = computed_total
    return {
        "provider": provider,
        "prompt_total": prompt_total,
        "uncached_input": uncached,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "output": output,
        "reasoning": reasoning,
        "total": prompt_total + output,
        "source": normalized.get("usage_source", "provider"),
    }


def merge_usage(total: Dict[str, Any], one: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Add one canonical usage record into a running total."""
    if not one:
        return total
    for key in ("prompt_total", "uncached_input", "cache_read", "cache_write", "output", "reasoning", "total"):
        total[key] = _as_int(total.get(key)) + _as_int(one.get(key))
    total["calls"] = _as_int(total.get("calls")) + 1
    return total


def empty_usage() -> Dict[str, int]:
    return {
        "prompt_total": 0,
        "uncached_input": 0,
        "cache_read": 0,
        "cache_write": 0,
        "output": 0,
        "reasoning": 0,
        "total": 0,
        "calls": 0,
    }


def cache_hit_rate(usage: Optional[Dict[str, Any]]) -> Optional[float]:
    """Prompt-side cache hit share, or None when no prompt was billed."""
    if not usage:
        return None
    denominator = _as_int(usage.get("prompt_total"))
    if denominator <= 0:
        denominator = (
            _as_int(usage.get("uncached_input"))
            + _as_int(usage.get("cache_read"))
            + _as_int(usage.get("cache_write"))
        )
    if denominator <= 0:
        return None
    return min(1.0, max(0.0, _as_int(usage.get("cache_read")) / denominator))


def usage_cost(usage: Optional[Dict[str, Any]], pricing: Optional[Dict[str, Any]]) -> Optional[float]:
    """Estimated cost from a per-million-token pricing table.

    Accepted keys: input, cache_read, cache_write, output. Missing buckets fall
    back to the input price (except cache_write, which falls back to input).
    """
    if not usage or not pricing:
        return None
    per = 1_000_000.0

    def price(name: str, fallback: Optional[float] = None) -> float:
        value = pricing.get(name)
        if value is None:
            value = fallback
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    input_price = price("input", price("prompt"))
    cache_read_price = price("cache_read", input_price * 0.1)
    cache_write_price = price("cache_write", input_price)
    output_price = price("output", input_price * 4)
    cost = (
        _as_int(usage.get("uncached_input")) * input_price
        + _as_int(usage.get("cache_read")) * cache_read_price
        + _as_int(usage.get("cache_write")) * cache_write_price
        + _as_int(usage.get("output")) * output_price
    )
    return cost / per


def savings_from_cache(usage: Optional[Dict[str, Any]], pricing: Optional[Dict[str, Any]]) -> Optional[float]:
    """Money saved by serving cache_read tokens at the cache price instead of input."""
    if not usage or not pricing:
        return None
    try:
        input_price = float(pricing.get("input") or pricing.get("prompt") or 0.0)
        cache_price = pricing.get("cache_read")
        cache_price = input_price * 0.1 if cache_price is None else float(cache_price)
    except (TypeError, ValueError):
        return None
    return _as_int(usage.get("cache_read")) * (input_price - cache_price) / 1_000_000.0


def format_tokens(value: int) -> str:
    value = _as_int(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def format_cost(value: Optional[float], currency: str = "") -> str:
    if value is None:
        return "—"
    prefix = "¥" if currency.upper() in ("CNY", "RMB", "¥") else "$"
    if value < 0.01 and value > 0:
        return f"{prefix}{value:.4f}"
    return f"{prefix}{value:.2f}"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:16]


def prefix_diagnostics(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[str] = None,
    tools: Optional[Any] = None,
    previous: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fingerprint the request prefix and locate the first changed message.

    Only hashes and indices are returned; no prompt text is stored.
    """
    history_prefix = messages[:-1] if messages else []
    diagnostics = {
        "system_hash": fingerprint(system_prompt or (messages[0].get("content") if messages else "")),
        "tools_hash": fingerprint(tools) if tools is not None else None,
        "history_hash": fingerprint(history_prefix),
        "messages_count": len(messages),
    }
    if previous:
        old = previous.get("history_messages")
        if isinstance(old, list):
            first_diff = -1
            for index, (a, b) in enumerate(zip(old, history_prefix)):
                if canonical_json(a) != canonical_json(b):
                    first_diff = index
                    break
            if first_diff == -1 and len(old) != len(history_prefix):
                first_diff = min(len(old), len(history_prefix))
            diagnostics["first_diff"] = first_diff
        diagnostics["previous_system_hash"] = previous.get("system_hash")
        diagnostics["previous_tools_hash"] = previous.get("tools_hash")
    return diagnostics


def prefix_state(messages: List[Dict[str, Any]], diagnostics: Dict[str, Any]) -> Dict[str, Any]:
    """Small previous-request state for the next prefix comparison."""
    return {
        "system_hash": diagnostics.get("system_hash"),
        "tools_hash": diagnostics.get("tools_hash"),
        "history_hash": diagnostics.get("history_hash"),
        "history_messages": messages[:-1] if messages else [],
    }


def ensure_canonical_usage(usage: Optional[Dict[str, Any]], provider: str = "unknown") -> Optional[Dict[str, Any]]:
    """Return a canonical usage dict, accepting legacy input/cache field names.

    Test doubles, third-party gateways and older code may provide only
    ``input_tokens``/``cache_read_tokens``/``cache_miss_tokens``. Normalize them
    without mutating the caller's dict.
    """
    if not usage:
        return None
    if "prompt_total" in usage and "uncached_input" in usage:
        result = dict(usage)
        result.setdefault("provider", provider)
        result.setdefault("total", _as_int(result.get("prompt_total")) + _as_int(result.get("output")))
        return result
    prompt_total = _as_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    cache_read = _as_int(usage.get("cache_read_tokens") or usage.get("cache_read"))
    cache_write = _as_int(usage.get("cache_write_tokens") or usage.get("cache_write"))
    output = _as_int(usage.get("output_tokens") or usage.get("output"))
    reasoning = _as_int(usage.get("reasoning_tokens") or usage.get("reasoning"))
    uncached = _as_int(usage.get("cache_miss_tokens") or usage.get("uncached_input"))
    if uncached <= 0 and prompt_total > 0:
        uncached = max(prompt_total - cache_read - cache_write, 0)
    computed_prompt = uncached + cache_read + cache_write
    if computed_prompt > 0:
        prompt_total = computed_prompt
    result = dict(usage)
    result.update({
        "provider": provider,
        "prompt_total": prompt_total,
        "uncached_input": uncached,
        "cache_read": cache_read,
        "cache_write": cache_write,
        "output": output,
        "reasoning": reasoning,
        "total": prompt_total + output,
        "usage_source": usage.get("usage_source", "provider"),
    })
    return result
