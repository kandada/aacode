# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""
Provider usage normalization and JSONL recording.

Only token counts and request metadata are stored; prompt/response text is
never written to the usage log.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from .file_lock import file_lock
except ImportError:  # pragma: no cover - direct execution fallback
    from file_lock import file_lock


def _as_mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return vars(value)
        except Exception:
            pass
    return {}


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_openai_usage(usage: Any) -> Optional[Dict[str, int]]:
    """Normalize OpenAI-compatible usage, including DeepSeek cache fields."""
    data = _as_mapping(usage)
    if not data:
        return None

    input_tokens = _as_int(data.get("prompt_tokens"))
    output_tokens = _as_int(data.get("completion_tokens"))
    total_tokens = _as_int(data.get("total_tokens")) or (input_tokens + output_tokens)

    prompt_details = _as_mapping(data.get("prompt_tokens_details"))
    completion_details = _as_mapping(data.get("completion_tokens_details"))

    cache_read = data.get("prompt_cache_hit_tokens")
    if cache_read is None:
        cache_read = prompt_details.get("cached_tokens")
    cache_read = _as_int(cache_read)

    cache_miss = data.get("prompt_cache_miss_tokens")
    if cache_miss is None:
        cache_miss = max(input_tokens - cache_read, 0)
    cache_miss = _as_int(cache_miss)

    reasoning = _as_int(completion_details.get("reasoning_tokens"))

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": 0,
        "cache_miss_tokens": cache_miss,
        "reasoning_tokens": reasoning,
    }


def normalize_anthropic_usage(usage: Any) -> Optional[Dict[str, int]]:
    """Normalize Anthropic usage, folding cache reads/writes into input tokens."""
    data = _as_mapping(usage)
    if not data:
        return None

    uncached_input = _as_int(data.get("input_tokens"))
    cache_read = _as_int(data.get("cache_read_input_tokens"))
    cache_write = _as_int(data.get("cache_creation_input_tokens"))
    input_tokens = uncached_input + cache_read + cache_write
    output_tokens = _as_int(data.get("output_tokens"))

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "cache_miss_tokens": uncached_input,
        "reasoning_tokens": 0,
    }


class UsageTracker:
    """Append-only usage recorder.

    Set ``AACODE_USAGE_LOG=0`` to disable logging.
    Set ``AACODE_USAGE_VERBOSE=1`` to print one compact line per model call.
    """

    def __init__(
        self,
        project_path: Any,
        enabled: Optional[bool] = None,
        verbose: Optional[bool] = None,
    ):
        self.project_path = Path(project_path)
        if enabled is None:
            enabled = os.environ.get("AACODE_USAGE_LOG", "1") != "0"
        if verbose is None:
            verbose = os.environ.get("AACODE_USAGE_VERBOSE", "0") == "1"
        self.enabled = bool(enabled)
        self.verbose = bool(verbose)

    @property
    def usage_dir(self) -> Path:
        return self.project_path / ".aacode" / "usage"

    def record(self, event: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        try:
            self.usage_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now().astimezone()
            path = self.usage_dir / f"usage_{now.strftime('%Y-%m-%d')}.jsonl"
            payload = {"ts": now.isoformat(timespec="milliseconds"), **event}
            with file_lock(path):
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(payload, ensure_ascii=False, default=str) + "\n"
                    )
            return True
        except Exception:
            # Telemetry must never break a task.
            return False
