# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""Context policy, tool-result pruning, spill files, and compaction summaries.

This module keeps the policy math independent from the ReAct loop so it can be
unit-tested and reused by the CLI, the desktop event bridge, and the TUI.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .token_usage import estimate_text_tokens, format_tokens


DEFAULT_HEADROOM_TOKENS = 65_536
DEFAULT_WINDOW_RATIO = 0.8
DEFAULT_RETAIN_RATIO = 0.16
DEFAULT_PRUNE_THRESHOLD_CHARS = 8_192
DEFAULT_PRUNE_HEAD_CHARS = 4_096
DEFAULT_PRUNE_TAIL_CHARS = 1_024
DEFAULT_INLINE_TOOL_TOKENS = 6_000
DEFAULT_INLINE_HEAD_CHARS = 8_000
DEFAULT_INLINE_TAIL_CHARS = 4_000
DEFAULT_SUMMARY_MIN_SHADOW_TOKENS = 30_000
DEFAULT_SUMMARY_MAX_TOKENS = 2_000
SUMMARY_MODE_OFF = "off"
SUMMARY_MODE_ALWAYS = "always"
SUMMARY_MODE_ADAPTIVE = "adaptive"


@dataclass(frozen=True)
class RouteContext:
    """The exact route a request will use."""

    provider: str = ""
    model: str = ""
    context_window: int = 1_000_000
    max_output_tokens: int = 0
    pricing: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ContextPolicy:
    """Resolved pressure, retention, and pruning budgets for one route."""

    context_window: int
    max_output_tokens: int
    headroom_tokens: int
    threshold_tokens: int
    retain_tokens: int
    trigger_ratio: float
    cost_ceiling_tokens: Optional[int]
    prune_threshold_chars: int
    prune_head_chars: int
    prune_tail_chars: int
    prune_min_rounds: int
    inline_tool_tokens: int
    inline_head_chars: int
    inline_tail_chars: int
    prune_enabled: bool
    summary_mode: str
    summary_min_shadow_tokens: int
    summary_max_tokens: int
    summary_provider: str
    summary_model: str
    overflow_retries: int
    task_input_token_budget: int
    task_output_token_budget: int
    repeat_tool_enabled: bool
    repeat_tool_thresholds: Tuple[int, ...]
    read_cache_enabled: bool


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _cfg(config: Any, name: str, default: Any) -> Any:
    return getattr(config, name, default) if config is not None else default


def resolve_context_policy(config: Any, route: RouteContext) -> ContextPolicy:
    """Resolve the pressure and retention budgets for one model route.

    ``threshold = min(window * ratio, window - output - headroom)`` by default.
    A positive ``cost_ceiling_tokens`` may cap an expensive route further, but
    it never raises the window-derived threshold. ``retain`` defaults to the
    DSH-style fraction of the non-output budget and can be overridden with an
    absolute token count.
    """
    window = _int(route.context_window or _cfg(config, "max_context_length", 1_000_000), 1_000_000)
    window = max(1, window)
    # An explicit per-route output cap wins; otherwise the model config's
    # max_tokens is the request's reserved completion budget.
    output = _int(route.max_output_tokens or _cfg(config, "max_output_tokens", 0), 0)
    if output <= 0:
        output = _int(_cfg(config, "max_tokens", 0), 0)
    output = max(0, min(output, max(0, window - 1)))

    headroom = max(0, _int(_cfg(config, "headroom_tokens", DEFAULT_HEADROOM_TOKENS), DEFAULT_HEADROOM_TOKENS))
    ratio = _float(_cfg(config, "window_ratio", DEFAULT_WINDOW_RATIO), DEFAULT_WINDOW_RATIO)
    if ratio <= 0 or ratio > 1:
        ratio = DEFAULT_WINDOW_RATIO

    message_budget = window - output
    pressure_budget = message_budget - headroom
    if pressure_budget <= 0:
        # Degrade safely instead of overflowing: keep a small but positive
        # message budget and record the misconfiguration for the caller.
        headroom = max(0, message_budget // 4)
        pressure_budget = max(1, message_budget - headroom)

    threshold = int(min(window * ratio, pressure_budget))
    threshold = max(1, threshold)

    cost_ceiling_raw = _cfg(config, "cost_ceiling_tokens", None)
    # Backward compatibility: old configs used retrieval_trigger_tokens as an
    # absolute trigger. Treat it as the optional cost ceiling when no explicit
    # cost_ceiling_tokens is configured. New defaults set it to 0.
    legacy_trigger = _cfg(config, "retrieval_trigger_tokens", 0)
    if cost_ceiling_raw in (None, "") and legacy_trigger not in (None, "", 0, "0"):
        cost_ceiling_raw = legacy_trigger
    cost_ceiling: Optional[int] = None
    if cost_ceiling_raw not in (None, "", 0, "0"):
        value = _int(cost_ceiling_raw, 0)
        if value > 0:
            cost_ceiling = value
            threshold = min(threshold, value)
    threshold = max(1, threshold)

    retain_override = _cfg(config, "retain_tokens", None)
    legacy_keep = _cfg(config, "retrieval_keep_tokens", 0)
    if retain_override in (None, "") and legacy_keep not in (None, "", 0, "0"):
        retain_override = legacy_keep
    if retain_override not in (None, "", 0, "0"):
        retain = max(0, _int(retain_override, 0))
    else:
        retain_ratio = _float(_cfg(config, "retain_ratio", DEFAULT_RETAIN_RATIO), DEFAULT_RETAIN_RATIO)
        if retain_ratio <= 0:
            retain_ratio = DEFAULT_RETAIN_RATIO
        retain = int(message_budget * retain_ratio)
    # Never retain the entire budget; leave room for the checkpoint and the
    # next step. A retention at/above the trigger would make compaction a no-op.
    retain = max(0, min(retain, max(0, threshold - 1)))

    summary_mode = str(_cfg(config, "summary_mode", SUMMARY_MODE_ADAPTIVE) or SUMMARY_MODE_ADAPTIVE).lower()
    if summary_mode not in (SUMMARY_MODE_OFF, SUMMARY_MODE_ALWAYS, SUMMARY_MODE_ADAPTIVE):
        summary_mode = SUMMARY_MODE_ADAPTIVE

    thresholds = _cfg(config, "repeat_tool_thresholds", (3, 5, 8))
    if not isinstance(thresholds, (list, tuple)):
        thresholds = (3, 5, 8)
    thresholds = tuple(sorted({int(x) for x in thresholds if _int(x, 0) >= 2})) or (3, 5, 8)

    return ContextPolicy(
        context_window=window,
        max_output_tokens=output,
        headroom_tokens=headroom,
        threshold_tokens=threshold,
        retain_tokens=retain,
        trigger_ratio=ratio,
        cost_ceiling_tokens=cost_ceiling,
        prune_threshold_chars=max(1, _int(_cfg(config, "prune_threshold_chars", DEFAULT_PRUNE_THRESHOLD_CHARS), DEFAULT_PRUNE_THRESHOLD_CHARS)),
        prune_head_chars=max(0, _int(_cfg(config, "prune_head_chars", DEFAULT_PRUNE_HEAD_CHARS), DEFAULT_PRUNE_HEAD_CHARS)),
        prune_tail_chars=max(0, _int(_cfg(config, "prune_tail_chars", DEFAULT_PRUNE_TAIL_CHARS), DEFAULT_PRUNE_TAIL_CHARS)),
        prune_min_rounds=max(0, _int(_cfg(config, "prune_min_rounds", 4), 4)),
        inline_tool_tokens=max(0, _int(_cfg(config, "inline_tool_tokens", DEFAULT_INLINE_TOOL_TOKENS), DEFAULT_INLINE_TOOL_TOKENS)),
        inline_head_chars=max(0, _int(_cfg(config, "inline_head_chars", DEFAULT_INLINE_HEAD_CHARS), DEFAULT_INLINE_HEAD_CHARS)),
        inline_tail_chars=max(0, _int(_cfg(config, "inline_tail_chars", DEFAULT_INLINE_TAIL_CHARS), DEFAULT_INLINE_TAIL_CHARS)),
        prune_enabled=bool(_cfg(config, "prune_enabled", True)),
        summary_mode=summary_mode,
        summary_min_shadow_tokens=max(0, _int(_cfg(config, "summary_min_shadow_tokens", DEFAULT_SUMMARY_MIN_SHADOW_TOKENS), DEFAULT_SUMMARY_MIN_SHADOW_TOKENS)),
        summary_max_tokens=max(1, _int(_cfg(config, "summary_max_tokens", DEFAULT_SUMMARY_MAX_TOKENS), DEFAULT_SUMMARY_MAX_TOKENS)),
        summary_provider=str(_cfg(config, "summary_provider", "") or ""),
        summary_model=str(_cfg(config, "summary_model", "") or ""),
        overflow_retries=max(0, _int(_cfg(config, "overflow_retries", 1), 1)),
        task_input_token_budget=max(0, _int(_cfg(config, "task_input_token_budget", 0), 0)),
        task_output_token_budget=max(0, _int(_cfg(config, "task_output_token_budget", 0), 0)),
        repeat_tool_enabled=bool(_cfg(config, "repeat_tool_enabled", True)),
        repeat_tool_thresholds=thresholds,
        read_cache_enabled=bool(_cfg(config, "read_cache_enabled", True)),
    )


def describe_policy(policy: ContextPolicy) -> str:
    return (
        f"window={policy.context_window} output={policy.max_output_tokens} "
        f"trigger={policy.threshold_tokens} retain={policy.retain_tokens} "
        f"headroom={policy.headroom_tokens}"
    )


PRUNE_MARKER = "\n\n[... tool result middle pruned ...]\n\n"


def prune_text_middle(
    text: str,
    threshold_chars: int = DEFAULT_PRUNE_THRESHOLD_CHARS,
    head_chars: int = DEFAULT_PRUNE_HEAD_CHARS,
    tail_chars: int = DEFAULT_PRUNE_TAIL_CHARS,
    marker: str = PRUNE_MARKER,
) -> Optional[Tuple[str, int, int]]:
    """Replace the middle of an oversized text while retaining head and tail.

    Returns ``(pruned, before_chars, after_chars)`` or ``None`` when the text
    is within budget. The marker is deterministic; callers must not include
    timestamps or random ids or they will break prompt-prefix caching.
    """
    if not text:
        return None
    before = len(text)
    if before <= threshold_chars:
        return None
    head = max(0, min(head_chars, before))
    tail = max(0, min(tail_chars, max(0, before - head)))
    # Ensure the replacement is actually smaller.
    if head + len(marker) + tail >= before:
        tail = 0
        if head + len(marker) >= before:
            head = max(0, before - len(marker) - 1)
            if head <= 0:
                return None
    pruned = text[:head] + marker + (text[-tail:] if tail else "")
    after = len(pruned)
    if after >= before:
        return None
    return pruned, before, after


def spill_text(
    project_path: Any,
    session_id: Optional[str],
    call_id: Optional[str],
    text: str,
    label: str = "tool",
) -> Optional[Path]:
    """Persist the full tool output for later retrieval.

    The path is deterministic apart from the call id, and the filename contains
    no timestamp, so the model-facing marker stays stable across replays.
    """
    if not project_path or not text:
        return None
    try:
        root = Path(project_path) / ".aacode" / "spill"
        if session_id:
            safe_session = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(session_id))[:80]
            root = root / safe_session
        root.mkdir(parents=True, exist_ok=True)
        safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label or "tool")[:40]
        safe_call = re.sub(r"[^A-Za-z0-9_.-]+", "_", call_id or uuid.uuid4().hex[:8])[:60]
        path = root / f"{safe_label}_{safe_call}.txt"
        if not path.exists() or path.stat().st_size != len(text.encode("utf-8")):
            path.write_text(text, encoding="utf-8")
        return path
    except Exception:
        return None


def spill_preview(
    text: str,
    project_path: Any,
    session_id: Optional[str],
    call_id: Optional[str],
    label: str = "tool",
    head_chars: int = DEFAULT_INLINE_HEAD_CHARS,
    tail_chars: int = DEFAULT_INLINE_TAIL_CHARS,
) -> Tuple[str, Optional[Path]]:
    """Keep head/tail inline and persist the full text when it is oversized."""
    path = spill_text(project_path, session_id, call_id, text, label=label)
    if path is None:
        return text, None
    try:
        display_path = str(path)
        try:
            display_path = str(path.relative_to(Path(project_path)))
        except Exception:
            pass
    except Exception:
        display_path = str(path)
    head = max(0, head_chars)
    tail = max(0, tail_chars)
    marker = (
        f"\n\n[... middle omitted: {max(0, len(text) - head - tail)} chars; "
        f"full output: {display_path} (use rg/sed/head/tail) ...]\n\n"
    )
    return text[:head] + marker + (text[-tail:] if tail else ""), path


def should_inline_spill(text: str, max_tokens: int, encoding: Any = None) -> bool:
    return max_tokens > 0 and estimate_text_tokens(text, encoding) > max_tokens


def _round_starts(messages: List[Dict[str, Any]]) -> List[int]:
    starts = []
    for index, message in enumerate(messages):
        if index == 0 or message.get("role") != "tool":
            starts.append(index)
    return starts


def select_prunable_indices(
    messages: List[Dict[str, Any]],
    cutoff: int,
    min_rounds: int,
    threshold_chars: int,
    already_pruned: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """Choose tool messages in the retained tail that can lose their middle.

    The newest ``min_rounds`` rounds stay verbatim; the system message and the
    latest user request are never candidates.
    """
    if not messages or cutoff >= len(messages):
        return []
    already = already_pruned or {}
    starts = [s for s in _round_starts(messages) if s >= cutoff]
    protected_from = starts[-min_rounds] if min_rounds > 0 and len(starts) >= min_rounds else len(messages)
    selected = []
    for index in range(max(0, cutoff), protected_from):
        message = messages[index]
        if message.get("role") != "tool":
            continue
        content = message.get("content", "")
        if not isinstance(content, str) or len(content) <= threshold_chars:
            continue
        key = str(index)
        previous = already.get(key)
        if isinstance(previous, dict) and previous.get("chars_before") == len(content):
            continue
        selected.append(index)
    return selected


SUMMARY_TEMPLATE_SECTIONS = (
    "Primary Request and Intent",
    "Key Technical Concepts",
    "Files and Code",
    "Errors and Fixes",
    "Pending Jobs",
    "Current Work",
    "Next Step",
    "Critical Context",
)

SUMMARY_INSTRUCTION = """You are now acting as a compaction engine for this AI coding assistant. Condense the conversation ABOVE into a structured checkpoint that lets another model resume the work with no loss of essential context.

Output EXACTLY the Markdown structure below: keep every section, in order. Use terse bullets, not prose paragraphs. Write "(none)" for an empty section — never drop a section.

## Primary Request and Intent
- [the user's original and evolving goals; quote verbatim where the exact wording matters]

## Key Technical Concepts
- [technologies, frameworks, patterns, and conventions in play]

## Files and Code
- [exact path: why it matters, key changes or snippets]

## Errors and Fixes
- [error: how it was resolved, plus any related user feedback]

## Pending Jobs
- [explicitly requested work not yet completed]

## Current Work
- [precisely what was in progress at this checkpoint]

## Next Step
- [the single next action, directly in line with the most recent request, or "(none)"]

## Critical Context
- [decisions and their rationale, constraints, user preferences, open questions, data needed to continue]

Rules:
- Write concise English engineering prose. Preserve exact file paths, commands, error strings, identifiers, numeric values, function signatures, and syntax fragments.
- Capture user feedback and explicit instructions faithfully, especially corrections.
- Do NOT mention this summarization request or that the context was compacted.
- Output only the checkpoint text: do not call any tool or take any other action.
- If the conversation already contains a <compacted-summary> block, it is a PRIOR checkpoint. Do not copy it forward verbatim: preserve still-true facts, drop stale ones, and merge newer information into a single consolidated summary under the same structure."""

SUMMARY_OPEN_TAG = "<compacted-summary>"
SUMMARY_CLOSE_TAG = "</compacted-summary>"
SUMMARY_PREAMBLE = (
    "This is an automatically generated checkpoint condensing an earlier span of the conversation "
    "to free up context. Treat the captured context as established background and build on it "
    "without restating it. Continue the task directly from the messages that follow, without "
    "acknowledging this checkpoint."
)


def validate_summary(text: str) -> bool:
    if not text or not text.strip():
        return False
    missing = [section for section in SUMMARY_TEMPLATE_SECTIONS if section not in text]
    return not missing


def frame_summary(summary: str) -> str:
    return f"{SUMMARY_PREAMBLE}\n\n{SUMMARY_OPEN_TAG}\n{summary.strip()}\n{SUMMARY_CLOSE_TAG}"


def build_summary_messages(
    prefix_messages: List[Dict[str, Any]],
    instruction: str = SUMMARY_INSTRUCTION,
) -> List[Dict[str, Any]]:
    """Replay the exact cached prefix, then append the compaction instruction."""
    messages = []
    for message in prefix_messages:
        # The summary call must not include tool calls that cannot be answered.
        if message.get("role") == "tool":
            messages.append({
                "role": "tool",
                "tool_call_id": message.get("tool_call_id", ""),
                "content": message.get("content", ""),
            })
        elif message.get("role") == "assistant":
            entry = {"role": "assistant", "content": message.get("content", "")}
            if message.get("tool_calls"):
                entry["tool_calls"] = message["tool_calls"]
            messages.append(entry)
        else:
            messages.append({"role": message.get("role", "user"), "content": message.get("content", "")})
    messages.append({"role": "user", "content": instruction})
    return messages


def summarize_usage(policy: ContextPolicy, usage: Optional[Dict[str, Any]]) -> str:
    if not usage:
        return ""
    return (
        f"summary input={format_tokens(usage.get('prompt_total', 0))} "
        f"output={format_tokens(usage.get('output', 0))}"
    )
