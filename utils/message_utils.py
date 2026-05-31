"""
消息处理工具函数

提供：
- estimate_tokens: 增强的 token 估算（含 tool_calls 等结构化字段）
- split_into_rounds: 按 round 拆分消息列表（尊重 tool_calls/tool_messages 边界）
- build_compact_view: 构建 round-aware 的压缩视图（不修改原列表）
- validate_tool_call_integrity: 验证 tool_calls/tool_messages 配对完整性
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def estimate_tokens(encoding, messages: List[Dict]) -> int:
    """
    估算消息列表的 token 数（含 tool_calls / tool_call_id / reasoning_content 等结构化字段）。

    Args:
        encoding: tiktoken encoding 对象，可以为 None（回退到字符数 // 4）
        messages: 消息列表

    Returns:
        估算的 token 数
    """
    total_tokens = 0
    for msg in messages:
        for field in ("content", "reasoning_content"):
            val = msg.get(field, "")
            if val:
                total_tokens += _encode_str(encoding, val)

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            tc_str = json.dumps(tool_calls, ensure_ascii=False)
            total_tokens += _encode_str(encoding, tc_str)

        tool_call_id = msg.get("tool_call_id")
        if tool_call_id:
            total_tokens += _encode_str(encoding, tool_call_id)

    return total_tokens


def _encode_str(encoding, text: str) -> int:
    """编码字符串为 token 数，失败时回退到字符数 // 4。"""
    if not text:
        return 0
    if encoding is None:
        return len(text) // 4
    try:
        return len(encoding.encode(text))
    except Exception:
        return len(text) // 4


def split_into_rounds(messages: List[Dict]) -> List[List[Dict]]:
    """
    将消息列表按 round 拆分。

    规则：
    - 任何非 tool 角色的消息开启一个新 round
    - 后续连续的 tool 消息属于同一 round
    - 确保 assistant(tool_calls) 和对应的 tool(tool_call_id) 永不分离

    Args:
        messages: 消息列表

    Returns:
        rounds 列表，每个 round 是一个消息子列表
    """
    rounds: List[List[Dict]] = []
    current: List[Dict] = []
    for msg in messages:
        role = msg.get("role", "")
        if role != "tool" and current:
            rounds.append(current)
            current = []
        current.append(msg)
    if current:
        rounds.append(current)
    return rounds


def build_compact_view(
    encoding,
    messages: List[Dict],
    max_tokens: int,
    protect_first_rounds: int = 3,
    keep_last_rounds: int = 10,
    cached_summary: Optional[str] = None,
) -> Tuple[List[Dict], bool]:
    """
    构建可传入模型的 round-aware 压缩视图。

    核心原则：
    - 不修改原始 messages 列表
    - 只在 round 边界处切割，确保 tool_calls/tool_messages 完整性
    - 保留 system prompt + 前 N round + 摘要 + 后 N round

    Args:
        encoding: tiktoken encoding 对象
        messages: 全量消息列表
        max_tokens: 模型最大上下文长度
        protect_first_rounds: 保护前 N 个 round
        keep_last_rounds: 保留后 N 个 round
        cached_summary: 预生成的中间轮次摘要（None 表示尚未生成）

    Returns:
        (compact_view, was_compacted): 压缩后的消息列表, 是否实际进行了压缩
    """
    full_tokens = estimate_tokens(encoding, messages)

    if full_tokens <= max_tokens:
        return list(messages), False

    rounds = split_into_rounds(messages)

    if len(rounds) <= protect_first_rounds + keep_last_rounds:
        return list(messages), False

    result: List[Dict] = []

    for r in rounds[:protect_first_rounds]:
        result.extend(r)

    if cached_summary:
        summary_content = cached_summary
    else:
        middle_count = len(rounds) - protect_first_rounds - keep_last_rounds
        compact_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary_content = (
            f"## Context Summary\n\n"
            f"**Compaction Time**: {compact_time}\n\n"
            f"*Intermediate {middle_count} rounds were omitted to stay within the context limit.*\n\n"
            f"Please continue based on the most recent context below and the task description above."
        )

    result.append({"role": "system", "content": summary_content})

    for r in rounds[-keep_last_rounds:]:
        result.extend(r)

    validate_tool_call_integrity(result)

    return result, True


def validate_tool_call_integrity(messages: List[Dict]) -> None:
    """
    验证 tool_calls/tool_messages 配对完整性。

    规则：
    - 每个 assistant(tool_calls) 的每个 tool_call.id 必须有对应的 tool(tool_call_id)
    - 每个 tool(tool_call_id) 必须有对应的 assistant(tool_calls) 中的 id

    不满足时抛出 ValueError，调用方可以回退到更保守的策略。

    Args:
        messages: 待验证的消息列表

    Raises:
        ValueError: 存在未配对的 tool_calls 或 tool_messages
    """
    pending_ids: set = set()

    for msg in messages:
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                if tc_id:
                    pending_ids.add(tc_id)

        if msg.get("role") == "tool":
            tid = msg.get("tool_call_id", "")
            if tid in pending_ids:
                pending_ids.discard(tid)
            elif tid:
                raise ValueError(
                    f"Orphaned tool message: tool_call_id={tid} has no matching "
                    f"assistant with tool_calls in the compact view"
                )

    if pending_ids:
        raise ValueError(
            f"Orphaned tool_calls: {pending_ids} have no matching tool messages "
            f"in the compact view"
        )
