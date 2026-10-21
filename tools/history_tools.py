# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

"""
Read-only history retrieval tools.

These tools let the model inspect messages that were omitted from its context
without cat-ing multi-megabyte session JSON files.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..utils.session_manager import SessionManager
except ImportError:  # pragma: no cover - direct execution fallback
    from utils.session_manager import SessionManager


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _tool_calls_text(message: Dict[str, Any], limit: int = 300) -> str:
    calls = message.get("tool_calls") or []
    parts = []
    for call in calls:
        func = call.get("function") or {}
        name = func.get("name") or call.get("name") or "?"
        args = func.get("arguments") or call.get("arguments") or ""
        parts.append(f"{name}({_as_text(args)[:limit]})")
    return "; ".join(parts)


def _snippet(text: str, query: str, radius: int = 320) -> str:
    text = text.replace("\n", " ")
    if not text:
        return ""
    match = re.search(re.escape(query), text, re.IGNORECASE)
    if not match:
        return text[: radius * 2]
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


class HistoryTools:
    """Search and read persisted session messages without changing session state."""

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.session_manager: Optional[SessionManager] = None

    def attach_session_manager(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager

    @property
    def sessions_dir(self) -> Path:
        if self.session_manager is not None:
            return self.session_manager.sessions_dir
        return self.project_path / ".aacode" / "sessions"

    def _current_session_id(self) -> Optional[str]:
        return self.session_manager.current_session_id if self.session_manager else None

    def _session_summaries(self) -> List[Dict[str, Any]]:
        if not self.session_manager:
            return []
        sessions = []
        for session_id, summary in self.session_manager.sessions_index.items():
            sessions.append(
                {
                    "session_id": session_id,
                    "created_at": getattr(summary, "created_at", ""),
                    "last_activity": getattr(summary, "last_activity", ""),
                    "title": getattr(summary, "title", ""),
                    "total_messages": getattr(summary, "total_messages", 0),
                    "total_tokens": getattr(summary, "total_tokens", 0),
                }
            )
        sessions.sort(key=lambda item: item.get("last_activity") or "", reverse=True)
        return sessions

    def _load_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Read a session without switching the active session.

        This is intentionally read-only: opening a historical session must not
        change ``current_session_id`` or the messages used by the running agent.
        """
        current = self._current_session_id()
        if self.session_manager is not None and session_id == current:
            return [
                {
                    "role": message.role,
                    "content": message.content,
                    "timestamp": message.timestamp,
                    "tool_calls": message.tool_calls,
                    "tool_call_id": message.tool_call_id,
                }
                for message in self.session_manager.current_messages
            ]

        path = self.sessions_dir / f"{session_id}.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        raw = data.get("structured_messages") or data.get("messages") or []
        return [message for message in raw if isinstance(message, dict)]

    def _resolve_session_id(self, session_id: Optional[str]) -> Optional[str]:
        return session_id or self._current_session_id()

    def list_sessions(self, limit: int = 20, offset: int = 0) -> str:
        limit = max(1, min(int(limit or 20), 50))
        offset = max(0, int(offset or 0))
        sessions = self._session_summaries()
        if not sessions:
            return "No sessions found."
        current = self._current_session_id()
        sliced = sessions[offset : offset + limit]
        lines = [f"Sessions ({len(sessions)} total):"]
        for item in sliced:
            marker = " *current" if item["session_id"] == current else ""
            lines.append(
                f"- {item['session_id']}{marker} | {item['last_activity']} | "
                f"{item['total_messages']} msgs | {item['total_tokens']} tokens | "
                f"{item['title'][:80]}"
            )
        if len(sessions) > offset + limit:
            lines.append(f"[More sessions: offset={offset + limit}]")
        return "\n".join(lines)

    def search_history(
        self,
        query: str,
        session_id: Optional[str] = None,
        scope: str = "current",
        role: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> str:
        query = (query or "").strip()
        if not query:
            return "search_history requires a non-empty query."
        limit = max(1, min(int(limit or 20), 50))
        offset = max(0, int(offset or 0))
        role = (role or "").strip().lower() or None
        if role and role not in ("user", "assistant", "tool", "system"):
            return "role must be one of: user, assistant, tool, system."

        # Current session first by default; cross-session search is explicit
        # because it can return irrelevant matches and costs more tokens.
        if session_id:
            session_ids = [session_id]
        elif scope == "project":
            session_ids = [
                item["session_id"] for item in self._session_summaries()[:50]
            ]
        else:
            current = self._current_session_id()
            session_ids = [current] if current else []

        matches = []
        for sid in session_ids:
            if not sid:
                continue
            messages = self._load_messages(sid)
            for index, message in enumerate(messages):
                if role and message.get("role") != role:
                    continue
                content = _as_text(message.get("content"))
                calls = _tool_calls_text(message)
                haystack = content + "\n" + calls
                if query.lower() not in haystack.lower():
                    continue
                matches.append(
                    {
                        "session_id": sid,
                        "index": index,
                        "role": message.get("role", ""),
                        "timestamp": message.get("timestamp", ""),
                        "snippet": _snippet(haystack, query),
                    }
                )

        if not matches:
            return f"No matches for {query!r} in {scope} scope."
        total = len(matches)
        sliced = matches[offset : offset + limit]
        lines = [
            f"Matches ({total} total, showing {offset + 1}-{offset + len(sliced)}):"
        ]
        for item in sliced:
            lines.append(
                f"[{item['session_id']}][{item['index']}] {item['role']} "
                f"{item['timestamp']}: {item['snippet']}"
            )
        if total > offset + limit:
            lines.append(f"[More matches: offset={offset + limit}]")
        return "\n".join(lines)

    def read_history(
        self,
        session_id: Optional[str] = None,
        start_index: int = 0,
        max_messages: int = 20,
        max_chars: int = 12000,
    ) -> str:
        sid = self._resolve_session_id(session_id)
        if not sid:
            return "No active session."
        messages = self._load_messages(sid)
        if not messages:
            return f"Session {sid} has no messages, or does not exist."

        start_index = min(max(0, int(start_index or 0)), len(messages))
        max_messages = max(1, min(int(max_messages or 20), 50))
        max_chars = max(1000, min(int(max_chars or 12000), 30000))
        end = min(len(messages), start_index + max_messages)

        lines = [
            f"Session {sid} | messages {start_index}-{max(end - 1, start_index)} of {len(messages)}:"
        ]
        used = len(lines[0])
        last_index = start_index
        for index in range(start_index, end):
            message = messages[index]
            role = message.get("role", "")
            timestamp = message.get("timestamp", "")
            content = _as_text(message.get("content"))
            per_message_cap = max(500, max_chars // max(1, max_messages))
            if len(content) > per_message_cap:
                content = (
                    content[:per_message_cap] + f"... [{len(content)} chars total]"
                )
            block = [f"[{index}] {role} {timestamp}"]
            if message.get("tool_call_id"):
                block.append(f"tool_call_id: {message['tool_call_id']}")
            calls = _tool_calls_text(message)
            if calls:
                block.append(f"tool_calls: {calls}")
            block.append(content)
            text = "\n".join(block)
            if used + len(text) > max_chars and index > start_index:
                break
            lines.append(text)
            used += len(text)
            last_index = index + 1

        if last_index < len(messages):
            lines.append(f"[Continue with start_index={last_index}]")
        return "\n\n".join(lines)
