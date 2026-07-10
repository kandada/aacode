# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

# 会话管理器
# utils/session_manager.py
"""
会话管理器
支持连续对话，智能上下文管理，15万token限制
"""

import asyncio
import json
import os
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import uuid
from dataclasses import dataclass
from aacode.i18n import t


def _load_tiktoken_encoding():
    """加载 tiktoken 编码，支持镜像下载，添加超时保护"""
    import os
    import threading

    cache_file = os.path.expanduser("~/Library/Caches/tiktoken/cl100k_base.tiktoken")

    # 快速检查缓存文件是否存在且有效
    if not os.path.exists(cache_file):
        return None
    file_size = os.path.getsize(cache_file)
    if file_size < 100:
        print(f"\n⚠️ tiktoken cache file corrupted (only {file_size} bytes), using simple estimation")
        return None

    result = [None]
    exception = [None]

    def _load():
        try:
            import tiktoken

            result[0] = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            exception[0] = e

    # 使用线程实现超时，避免主线程阻塞
    t = threading.Thread(target=_load, daemon=True)
    t.start()
    t.join(timeout=5)  # 5秒超时

    if t.is_alive():
        print(f"\n⚠️ tiktoken loading timeout, using simple estimation")
        return None

    if exception[0]:
        error_msg = str(exception[0])
        if (
            "Connection" in error_msg
            or "ConnectionResetError" in error_msg
            or "HTTPError" in error_msg
            or "404" in error_msg
            or "timed out" in error_msg.lower()
        ):
            print(f"\n⚠️ tiktoken download failed, using simple estimation")
            print(
                f"   Manual fix: https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
            )
            print(f"   Save to: ~/Library/Caches/tiktoken/cl100k_base.tiktoken")
        return None

    return result[0]


def _ensure_iso_timestamp(ts: Any) -> str:
    """统一时间戳为 ISO 8601 字符串（如 "2026-05-28T09:16:11"），兼容旧版 float。

    反序列化时调用，确保内存中全用统一格式。
    """
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts).isoformat(timespec='seconds')
    return ts


def _timestamp_sort_key(ts: Any) -> float:
    """将 str/float 时间戳统一转为 float 用于排序，兼容新旧格式。"""
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _atomic_file_write(filepath, write_func):
    """Atomically write to file using temp file + os.replace"""
    import tempfile

    tmp_fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            write_func(f)
        os.replace(tmp_path, filepath)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _merge_sessions_index(filepath, our_data):
    """Read disk index, merge with our data, write atomically under a file lock.

    File lock ensures read-merge-write is atomic across concurrent processes,
    preventing lost updates when two processes modify the index simultaneously.

    Our data takes priority for same keys, but we preserve entries
    from disk that we don't know about (added by other processes).
    """
    import json as _json
    from aacode.utils.file_lock import file_lock

    def _read_disk():
        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return _json.load(f)
            except Exception:
                pass
        return {}

    with file_lock(filepath):
        disk_data = _read_disk()
        merged = {**disk_data, **our_data}
        _atomic_file_write(
            filepath,
            lambda f: _json.dump(merged, f, indent=2, ensure_ascii=False),
        )


@dataclass
class SessionMessage:
    """会话消息"""

    role: str  # user, assistant, system, tool
    content: str
    timestamp: str  # ISO 8601 字符串（如 "2026-05-01T20:29:31.951047"），兼容旧版 float
    tokens: int = 0
    tool_calls: Optional[List[Dict]] = None       # assistant 消息的 tool_calls
    tool_call_id: Optional[str] = None             # tool 消息的 tool_call_id
    reasoning_content: Optional[str] = None         # assistant 消息的 reasoning_content


@dataclass
class SessionSummary:
    """会话摘要"""

    session_id: str
    created_at: str  # ISO 8601 字符串（如 "2026-05-28T09:16:11"），兼容旧版 float
    last_activity: str  # ISO 8601 字符串，兼容旧版 float
    total_messages: int
    total_tokens: int
    task_count: int
    title: str
    status: str  # active, completed, archived


class SessionManager:
    """会话管理器"""

    def __init__(self, project_path, max_tokens: int = 200000):
        from pathlib import Path
        self.project_path = Path(project_path) if not isinstance(project_path, Path) else project_path
        self.sessions_dir = self.project_path / ".aacode" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.max_tokens = max_tokens

        # 当前会话
        self.current_session_id: Optional[str] = None
        self.current_messages: List[SessionMessage] = []

        # 会话索引
        self.sessions_index: Dict[str, SessionSummary] = {}

        # token计数器（惰性加载，首次 _count_tokens 时才加载）
        self._encoding = None

        # 加载会话索引
        self._load_sessions_index()

    def _load_sessions_index(self):
        """加载会话索引"""
        index_file = self.sessions_dir / "sessions_index.json"
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for session_id, session_data in data.items():
                        # 兼容旧版 float 时间戳，反序列化时统一转为 ISO 8601 字符串
                        session_data["created_at"] = _ensure_iso_timestamp(session_data.get("created_at", ""))
                        session_data["last_activity"] = _ensure_iso_timestamp(session_data.get("last_activity", ""))
                        self.sessions_index[session_id] = SessionSummary(**session_data)
            except Exception as e:
                print(t("session.load_error", e=str(e)))

    def _save_sessions_index(self):
        """保存会话索引（merge with disk to prevent concurrent overwrite loss）"""
        index_file = self.sessions_dir / "sessions_index.json"
        try:
            our_data = {}
            for session_id, session_summary in self.sessions_index.items():
                our_data[session_id] = {
                    "session_id": session_summary.session_id,
                    "created_at": session_summary.created_at,
                    "last_activity": session_summary.last_activity,
                    "total_messages": session_summary.total_messages,
                    "total_tokens": session_summary.total_tokens,
                    "task_count": session_summary.task_count,
                    "title": session_summary.title,
                    "status": session_summary.status,
                }

            _merge_sessions_index(index_file, our_data)
        except Exception as e:
            print(f"⚠️ Failed to save session index: {e}")

    def _count_tokens(self, text: str) -> int:
        """计算文本的token数量"""
        if self._encoding is None:
            self._encoding = _load_tiktoken_encoding()
        if self._encoding:
            try:
                return len(self._encoding.encode(text))
            except Exception:
                pass
        # 回退到简单估算（大致4字符=1token）
        return len(text) // 4

    def _get_total_tokens(self) -> int:
        """获取当前会话的总token数"""
        return sum(msg.tokens for msg in self.current_messages)

    async def create_session(self, task: str, title: Optional[str] = None) -> str:
        """创建新会话"""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        # 生成标题
        if title is None:
            title = task[:50] + "..." if len(task) > 50 else task

        # 创建会话摘要
        now = datetime.now().isoformat(timespec='seconds')
        session_summary = SessionSummary(
            session_id=session_id,
            created_at=now,
            last_activity=now,
            total_messages=0,
            total_tokens=0,
            task_count=0,
            title=title,
            status="active",
        )

        self.sessions_index[session_id] = session_summary
        self.current_session_id = session_id
        self.current_messages = []

        # 不再创建占位 system 消息。
        # 第一条 system prompt 完全由代码规则确定（SYSTEM_PROMPT + skills + working_dir
        # + analysis + init_instructions + todo_section），无需持久化到 session JSON。
        # 仅持久化 user / assistant / tool 消息，以及 LLM 生成的压缩摘要 system 消息。
        #
        # 兼容性：旧版 session JSON 中 current_messages[0] 可能是占位 system，
        # 由 get_messages(include_system=False) 过滤，不影响 LLM 调用。
        if task and task.strip():
            user_msg = SessionMessage(
                role="user",
                content=task,
                timestamp=datetime.now().isoformat(timespec='seconds'),
                tokens=self._count_tokens(task),
            )
            self.current_messages.append(user_msg)
        session_summary.total_messages = len(self.current_messages)
        session_summary.total_tokens = self._get_total_tokens()

        # 保存索引
        self._save_sessions_index()

        # 保存会话文件
        await self._save_session()

        # 保存当前会话ID到文件（方便用户查询）
        await self._save_current_session_id()

        return session_id

    async def _save_current_session_id(self):
        """保存当前会话ID到文件"""
        if not self.current_session_id:
            return

        current_session_file = self.sessions_dir.parent / "current_session.txt"
        try:
            content = (
                f"Session ID: {self.current_session_id}\n"
                f"Created: {datetime.fromisoformat(self.sessions_index[self.current_session_id].created_at).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Title: {self.sessions_index[self.current_session_id].title}\n"
                f"Messages: {len(self.current_messages)}\n"
                f"Tokens: {self._get_total_tokens()}\n"
            )
            _atomic_file_write(current_session_file, lambda f: f.write(content))
        except Exception as e:
            print(t("session.save_id_error", e=str(e)))

    async def add_message(
        self, role: str, content: str,
        tool_calls: Optional[List[Dict]] = None,
        tool_call_id: Optional[str] = None,
        reasoning_content: Optional[str] = None,
    ) -> bool:
        """添加消息到当前会话"""
        if not self.current_session_id:
            return False

        # 添加消息
        new_tokens = self._count_tokens(content)
        message = SessionMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(timespec='seconds'),
            tokens=new_tokens,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            reasoning_content=reasoning_content,
        )

        self.current_messages.append(message)

        # 更新会话摘要
        if self.current_session_id in self.sessions_index:
            session_summary = self.sessions_index[self.current_session_id]
            session_summary.last_activity = datetime.now().isoformat(timespec='seconds')
            session_summary.total_messages = len(self.current_messages)
            session_summary.total_tokens = self._get_total_tokens()
            # 如果 title 为空，用第一条 user 消息作为标题
            if role == "user" and (not session_summary.title or session_summary.title.strip() == ""):
                session_summary.title = content[:50] + ("..." if len(content) > 50 else "")

        # 保存
        await self._save_session()
        self._save_sessions_index()

        # 更新当前会话ID文件
        await self._save_current_session_id()

        return True

    async def get_messages(
        self, session_id: Optional[str] = None, include_system: bool = True
    ) -> List[Dict]:
        """获取会话消息（转换为 dict 格式，供 LLM API / 客户端使用）

        现在只有一个消息源 current_messages，始终包含结构化字段
        （tool_calls / reasoning_content / tool_call_id）。
        """
        target_session_id = session_id or self.current_session_id
        if not target_session_id:
            return []

        # 如果不是当前会话，加载它
        if target_session_id != self.current_session_id:
            await self._load_session(target_session_id)

        messages = []
        for msg in self.current_messages:
            # include_system=False 是关键兼容机制：
            # 1. 过滤旧版占位 system（不再创建，但旧数据可能残留）
            # 2. 过滤 LLM 生成的压缩摘要 system（仅在需要完整上下文时 include_system=True）
            if not include_system and msg.role == "system":
                continue
            entry = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.reasoning_content:
                entry["reasoning_content"] = msg.reasoning_content
            messages.append(entry)

        return messages

    async def get_conversation_history(self, max_length: int = 10) -> str:
        """获取对话历史（用于显示给用户）"""
        if not self.current_messages:
            return ""

        recent_messages = self.current_messages[-max_length:]
        history_lines = []

        for msg in recent_messages:
            if msg.role == "system":
                continue
            role_name = "User" if msg.role == "user" else "Assistant"
            content_preview = (
                msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            )
            history_lines.append(f"{role_name}: {content_preview}")

        return "\n".join(history_lines)

    async def _compact_context(self):
        """检查上下文 token 使用量，记录警告但不修改持久化数据。

        持久化的全量消息不可破坏，真正的压缩由 react_loop._build_compact_view
        在传入模型时执行（round-aware 压缩视图）。
        """
        current_tokens = self._get_total_tokens()
        if current_tokens > self.max_tokens * 0.8:
            print(
                f"⚠️ Session token count ({current_tokens}) approaching limit ({self.max_tokens}). "
                f"Full data preserved; model-input compression handled by react_loop."
            )

    async def _save_session(self):
        """保存当前会话（单轨：messages 数组包含全部结构化字段）"""
        if not self.current_session_id:
            return

        session_file = self.sessions_dir / f"{self.current_session_id}.json"

        session_data = {
            "session_id": self.current_session_id,
            "created_at": self.sessions_index.get(
                self.current_session_id, SessionSummary("", "", "", 0, 0, 0, "", "")
            ).created_at,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "tokens": msg.tokens,
                    "tool_calls": msg.tool_calls,
                    "tool_call_id": msg.tool_call_id,
                    "reasoning_content": msg.reasoning_content,
                }
                for msg in self.current_messages
            ],
        }

        try:
            _atomic_file_write(
                session_file,
                lambda f: json.dump(session_data, f, indent=2, ensure_ascii=False)
            )
        except Exception as e:
            print(t("session.save_error", e=str(e)))

    async def _load_session(self, session_id: str):
        """加载指定会话（兼容旧版 collapsed text 格式和 structured_messages 双轨格式）

        兼容性说明：
        - 旧版 session JSON（2026-06-07 之前）的 current_messages[0] 是一条占位 system 消息
          （"You are an AI coding assistant..."），新代码不再创建此消息。
        - 加载旧数据时该消息会原样保留在 current_messages 中，不影响运行：
          通过 get_messages(include_system=False) 过滤，不会传给 LLM；
          通过 _compact_context 被归类为 system_msgs 保留但无实际影响。
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return False

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            self.current_session_id = session_id
            self.current_messages = []

            # ── 旧版兼容（TODO: 下个大版本移除，若确认无旧 structured_messages 会话） ──
            # 旧版文件同时存了 structured_messages 和 messages（collapsed text）。
            # 如果 structured_messages 存在，以它为准（它已经是我们需要的结构化格式）；
            # 否则走 messages 数组。
            raw_messages = session_data.get("structured_messages") or session_data.get("messages", [])

            for msg_data in raw_messages:
                msg_data["timestamp"] = _ensure_iso_timestamp(msg_data.get("timestamp"))
                message = SessionMessage(
                    role=msg_data["role"],
                    content=msg_data.get("content", ""),
                    timestamp=msg_data["timestamp"],
                    tokens=msg_data.get("tokens", 0),
                    tool_calls=msg_data.get("tool_calls"),
                    tool_call_id=msg_data.get("tool_call_id"),
                    reasoning_content=msg_data.get("reasoning_content"),
                )
                self.current_messages.append(message)

            return True

        except Exception as e:
            print(t("session.load_session_error", e=str(e)))
            return False

    async def list_sessions(self) -> List[Dict]:
        """列出所有会话"""
        sessions = []
        for session_summary in self.sessions_index.values():
            sessions.append(
                {
                    "session_id": session_summary.session_id,
                    "title": session_summary.title,
                    "created_at": session_summary.created_at,
                    "last_activity": session_summary.last_activity,
                    "total_messages": session_summary.total_messages,
                    "total_tokens": session_summary.total_tokens,
                    "task_count": session_summary.task_count,
                    "status": session_summary.status,
                }
            )

        # 按最后活动时间排序（兼容 str / float 时间戳）
        sessions.sort(key=lambda x: _timestamp_sort_key(x.get("last_activity")), reverse=True)
        return sessions

    async def switch_session(self, session_id: str) -> bool:
        """切换到指定会话"""
        if session_id not in self.sessions_index:
            return False

        # 保存当前会话
        if self.current_session_id:
            await self._save_session()

        # 加载目标会话
        success = await self._load_session(session_id)
        if success:
            self.current_session_id = session_id
            # 更新当前会话ID文件
            await self._save_current_session_id()

        return success

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id not in self.sessions_index:
            return False

        # 删除会话文件
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()

        # 从索引中删除
        del self.sessions_index[session_id]
        self._save_sessions_index()

        # 如果是当前会话，清空
        if self.current_session_id == session_id:
            self.current_session_id = None
            self.current_messages = []

        return True

    async def archive_session(self, session_id: str) -> bool:
        """归档会话"""
        if session_id not in self.sessions_index:
            return False

        # 更新状态
        self.sessions_index[session_id].status = "archived"
        self._save_sessions_index()

        return True

    async def get_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """获取会话详细信息"""
        if not session_id:
            session_id = self.current_session_id

        if not session_id:
            return {}

        # 加载会话数据
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return {}

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                session_summary = json.load(f)
        except Exception:
            return {}

        if not session_summary:
            return {}

        messages = await self.get_messages(session_id, include_system=True)

        return {
            "session_id": session_id,
            "title": session_summary.get("title", ""),
            "messages": messages,
            "total_messages": session_summary.get("total_messages", 0),
            "total_tokens": session_summary.get("total_tokens", 0),
            "created_at": session_summary.get("created_at", ""),
            "last_activity": session_summary.get("last_activity", ""),
        }

    async def count_tokens(self, session_id: Optional[str] = None) -> int:
        """计算会话的token数量"""
        if not session_id:
            session_id = self.current_session_id

        if not session_id:
            return 0

        # 加载会话数据
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return 0

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)
            return session_data.get("total_tokens", 0)
        except Exception:
            return 0

    @property
    def token_limit(self) -> int:
        """获取token限制"""
        return self.max_tokens

    async def compress_session(
        self, session_id: Optional[str] = None, max_messages: int = 50
    ) -> Dict[str, Any]:
        """压缩会话消息"""
        if not session_id:
            session_id = self.current_session_id

        if not session_id:
            return {"compressed_messages": [], "removed_count": 0}

        original_messages = await self.get_messages(session_id, include_system=False)

        if len(original_messages) <= max_messages:
            return {"compressed_messages": original_messages, "removed_count": 0}

        # 保留最近的max_messages条消息
        compressed_messages = original_messages[-max_messages:]
        removed_count = len(original_messages) - max_messages

        return {
            "compressed_messages": compressed_messages,
            "removed_count": removed_count,
        }

    def get_session_stats(self) -> Dict[str, Any]:
        """获取当前会话统计信息"""
        if not self.current_session_id:
            return {}

        # 加载会话数据
        session_file = self.sessions_dir / f"{self.current_session_id}.json"
        if not session_file.exists():
            return {}

        try:
            with open(session_file, "r", encoding="utf-8") as f:
                session_summary = json.load(f)
        except Exception:
            return {}

        return {
            "session_id": self.current_session_id,
            "title": session_summary.get("title", ""),
            "total_messages": session_summary.get("total_messages", 0),
            "total_tokens": session_summary.get("total_tokens", 0),
            "current_tokens": self._get_total_tokens(),
            "max_tokens": self.max_tokens,
            "created_at": session_summary.get("created_at", ""),
            "last_activity": session_summary.get("last_activity", ""),
        }
