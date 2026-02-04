# 会话管理器
# utils/session_manager.py
"""
会话管理器
支持连续对话，智能上下文管理，15万token限制
"""
import asyncio
import json
import os
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import tiktoken
from dataclasses import dataclass


@dataclass
class SessionMessage:
    """会话消息"""
    role: str  # user, assistant, system
    content: str
    timestamp: float
    tokens: int = 0
    metadata: Optional[Dict] = None


@dataclass
class SessionSummary:
    """会话摘要"""
    session_id: str
    created_at: float
    last_activity: float
    total_messages: int
    total_tokens: int
    task_count: int
    title: str
    status: str  # active, completed, archived


class SessionManager:
    """会话管理器"""
    
    def __init__(self, project_path: Path, max_tokens: int = 200000):
        self.project_path = project_path
        self.sessions_dir = project_path / ".aacode" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.max_tokens = max_tokens
        
        # 当前会话
        self.current_session_id: Optional[str] = None
        self.current_messages: List[SessionMessage] = []
        
        # 会话索引
        self.sessions_index: Dict[str, SessionSummary] = {}
        
        # token计数器
        self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # 加载会话索引
        self._load_sessions_index()
    
    def _load_sessions_index(self):
        """加载会话索引"""
        index_file = self.sessions_dir / "sessions_index.json"
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for session_id, session_data in data.items():
                        self.sessions_index[session_id] = SessionSummary(**session_data)
            except Exception as e:
                print(f"⚠️ 加载会话索引失败: {e}")
    
    def _save_sessions_index(self):
        """保存会话索引"""
        index_file = self.sessions_dir / "sessions_index.json"
        try:
            data = {}
            for session_id, session_summary in self.sessions_index.items():
                data[session_id] = {
                    "session_id": session_summary.session_id,
                    "created_at": session_summary.created_at,
                    "last_activity": session_summary.last_activity,
                    "total_messages": session_summary.total_messages,
                    "total_tokens": session_summary.total_tokens,
                    "task_count": session_summary.task_count,
                    "title": session_summary.title,
                    "status": session_summary.status
                }
            
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 保存会话索引失败: {e}")
    
    def _count_tokens(self, text: str) -> int:
        """计算文本的token数量"""
        try:
            return len(self.encoding.encode(text))
        except Exception:
            # 回退到简单估算（大致4字符=1token）
            return len(text) // 4
    
    def _get_total_tokens(self) -> int:
        """获取当前会话的总token数"""
        return sum(msg.tokens for msg in self.current_messages)
    
    async def create_session(self, task: str, title: Optional[str] = None) -> str:
        """创建新会话"""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.sessions_index)}"
        
        # 生成标题
        if title is None:
            title = task[:50] + "..." if len(task) > 50 else task
        
        # 创建会话摘要
        session_summary = SessionSummary(
            session_id=session_id,
            created_at=datetime.now().timestamp(),
            last_activity=datetime.now().timestamp(),
            total_messages=0,
            total_tokens=0,
            task_count=0,
            title=title,
            status="active"
        )
        
        self.sessions_index[session_id] = session_summary
        self.current_session_id = session_id
        self.current_messages = []
        
        # 添加系统消息和任务
        system_msg = SessionMessage(
            role="system",
            content=f"你是一个AI编程助手。请按照以下方式工作：\n1. 先规划任务步骤\n2. 逐步执行并验证\n3. 确保代码质量和可维护性",
            timestamp=datetime.now().timestamp(),
            tokens=self._count_tokens(f"你是一个AI编程助手。请按照以下方式工作：\n1. 先规划任务步骤\n2. 逐步执行并验证\n3. 确保代码质量和可维护性")
        )
        
        user_msg = SessionMessage(
            role="user",
            content=task,
            timestamp=datetime.now().timestamp(),
            tokens=self._count_tokens(task)
        )
        
        self.current_messages.extend([system_msg, user_msg])
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
            with open(current_session_file, 'w', encoding='utf-8') as f:
                f.write(f"当前会话ID: {self.current_session_id}\n")
                f.write(f"创建时间: {datetime.fromtimestamp(self.sessions_index[self.current_session_id].created_at).strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"标题: {self.sessions_index[self.current_session_id].title}\n")
                f.write(f"消息数: {len(self.current_messages)}\n")
                f.write(f"Token数: {self._get_total_tokens()}\n")
        except Exception as e:
            print(f"⚠️ 保存当前会话ID失败: {e}")
    
    async def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """添加消息到当前会话"""
        if not self.current_session_id:
            return False
        
        # 检查token限制
        new_tokens = self._count_tokens(content)
        current_tokens = self._get_total_tokens()
        
        if current_tokens + new_tokens > self.max_tokens:
            # 触发上下文缩减
            await self._compact_context()
            current_tokens = self._get_total_tokens()
            
            if current_tokens + new_tokens > self.max_tokens:
                # 如果还是超限，拒绝添加
                return False
        
        # 添加消息
        message = SessionMessage(
            role=role,
            content=content,
            timestamp=datetime.now().timestamp(),
            tokens=new_tokens,
            metadata=metadata or {}
        )
        
        self.current_messages.append(message)
        
        # 更新会话摘要
        if self.current_session_id in self.sessions_index:
            session_summary = self.sessions_index[self.current_session_id]
            session_summary.last_activity = datetime.now().timestamp()
            session_summary.total_messages = len(self.current_messages)
            session_summary.total_tokens = self._get_total_tokens()
        
        # 保存
        await self._save_session()
        self._save_sessions_index()
        
        # 更新当前会话ID文件
        await self._save_current_session_id()
        
        return True
    
    async def get_messages(self, session_id: Optional[str] = None, include_system: bool = True) -> List[Dict]:
        """获取会话消息"""
        target_session_id = session_id or self.current_session_id
        if not target_session_id:
            return []
        
        # 如果不是当前会话，加载它
        if target_session_id != self.current_session_id:
            await self._load_session(target_session_id)
        
        messages = []
        for msg in self.current_messages:
            if not include_system and msg.role == "system":
                continue
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
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
            role_name = "用户" if msg.role == "user" else "助手"
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            history_lines.append(f"{role_name}: {content_preview}")
        
        return "\n".join(history_lines)
    
    async def _compact_context(self):
        """压缩上下文，保持在token限制内"""
        if len(self.current_messages) <= 4:  # 保留系统消息和最少对话
            return
        
        # 保留系统消息和最近的用户消息
        system_msgs = [msg for msg in self.current_messages if msg.role == "system"]
        recent_msgs = self.current_messages[-3:]  # 保留最近3条消息
        
        # 生成摘要
        old_msgs = self.current_messages[:-3]
        if old_msgs:
            summary = f"之前的对话包含{len(old_msgs)}条消息，主要讨论了编程相关的任务。"
            summary_msg = SessionMessage(
                role="system",
                content=f"上下文摘要: {summary}",
                timestamp=datetime.now().timestamp(),
                tokens=self._count_tokens(summary)
            )
            
            self.current_messages = system_msgs + [summary_msg] + recent_msgs
        else:
            self.current_messages = system_msgs + recent_msgs
    
    async def _save_session(self):
        """保存当前会话"""
        if not self.current_session_id:
            return
        
        session_file = self.sessions_dir / f"{self.current_session_id}.json"
        
        session_data = {
            "session_id": self.current_session_id,
            "created_at": self.sessions_index.get(self.current_session_id, SessionSummary("", 0, 0, 0, 0, 0, "", "")).created_at,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "tokens": msg.tokens,
                    "metadata": msg.metadata
                }
                for msg in self.current_messages
            ]
        }
        
        try:
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 保存会话失败: {e}")
    
    async def _load_session(self, session_id: str):
        """加载指定会话"""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return False
        
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            self.current_session_id = session_id
            self.current_messages = []
            
            for msg_data in session_data.get("messages", []):
                message = SessionMessage(
                    role=msg_data["role"],
                    content=msg_data["content"],
                    timestamp=msg_data["timestamp"],
                    tokens=msg_data.get("tokens", 0),
                    metadata=msg_data.get("metadata")
                )
                self.current_messages.append(message)
            
            return True
            
        except Exception as e:
            print(f"⚠️ 加载会话失败: {e}")
            return False
    
    async def list_sessions(self) -> List[Dict]:
        """列出所有会话"""
        sessions = []
        for session_summary in self.sessions_index.values():
            sessions.append({
                "session_id": session_summary.session_id,
                "title": session_summary.title,
                "created_at": session_summary.created_at,
                "last_activity": session_summary.last_activity,
                "total_messages": session_summary.total_messages,
                "total_tokens": session_summary.total_tokens,
                "task_count": session_summary.task_count,
                "status": session_summary.status
            })
        
        # 按最后活动时间排序
        sessions.sort(key=lambda x: x["last_activity"], reverse=True)
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
            with open(session_file, 'r', encoding='utf-8') as f:
                session_summary = json.load(f)
        except Exception:
            return {}
        
        if not session_summary:
            return {}
        
        messages = await self.get_messages(session_id, include_system=True)
        
        return {
            "session_id": session_id,
            "title": session_summary.get('title', ''),
            "messages": messages,
            "total_messages": session_summary.get('total_messages', 0),
            "total_tokens": session_summary.get('total_tokens', 0),
            "created_at": session_summary.get('created_at', ''),
            "last_activity": session_summary.get('last_activity', '')
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
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            return session_data.get('total_tokens', 0)
        except Exception:
            return 0
    
    @property
    def token_limit(self) -> int:
        """获取token限制"""
        return self.max_tokens
    
    async def compress_session(self, session_id: Optional[str] = None, max_messages: int = 50) -> Dict[str, Any]:
        """压缩会话消息"""
        if not session_id:
            session_id = self.current_session_id
        
        if not session_id:
            return {"compressed_messages": [], "removed_count": 0}
        
        original_messages = await self.get_messages(session_id, include_system=False)
        
        if len(original_messages) <= max_messages:
            return {
                "compressed_messages": original_messages,
                "removed_count": 0
            }
        
        # 保留最近的max_messages条消息
        compressed_messages = original_messages[-max_messages:]
        removed_count = len(original_messages) - max_messages
        
        return {
            "compressed_messages": compressed_messages,
            "removed_count": removed_count
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
            with open(session_file, 'r', encoding='utf-8') as f:
                session_summary = json.load(f)
        except Exception:
            return {}
        
        return {
            "session_id": self.current_session_id,
            "title": session_summary.get('title', ''),
            "total_messages": session_summary.get('total_messages', 0),
            "total_tokens": session_summary.get('total_tokens', 0),
            "current_tokens": self._get_total_tokens(),
            "max_tokens": self.max_tokens,
            "created_at": session_summary.get('created_at', ''),
            "last_activity": session_summary.get('last_activity', '')
        }