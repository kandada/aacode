# Agent日志系统
# utils/agent_logger.py
"""
Agent操作日志系统
为每次任务创建独立的详细日志文件
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import aiofiles
import os
from aacode.i18n import t


class AgentLogger:
    """Agent操作日志记录器"""

    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.logs_dir = project_path / ".aacode" / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.current_log_file: Optional[Path] = None
        self.log_buffer: List[Dict] = []
        self.file_handle: Optional[aiofiles.threadpool.text.AsyncTextIOWrapper] = None

    async def start_task(
        self, task_description: str, task_id: Optional[str] = None
    ) -> str:
        """开始新任务，创建日志文件"""
        # 生成任务ID和日志文件名
        if not task_id:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_id = f"task_{timestamp}"

        log_filename = (
            f"agent_thought_and_action_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        self.current_log_file = self.logs_dir / log_filename

        # 打开日志文件
        self.file_handle = await aiofiles.open(
            self.current_log_file, "w", encoding="utf-8"
        )

        # 写入日志头部
        header = {
            "type": "task_start",
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
            "task_description": task_description,
            "project_path": str(self.project_path),
            "log_file": str(self.current_log_file),
        }

        await self._write_log_entry(header)

        print(f"📝 Start logging: {self.current_log_file.name}")

        return task_id

    async def log_iteration(
        self,
        iteration: int,
        thought: str,
        action: Optional[str] = None,
        action_input: Optional[Dict] = None,
        observation: Optional[str] = None,
        execution_time: Optional[float] = None,
    ) -> None:
        """记录ReAct循环迭代"""
        if not self.file_handle:
            return

        log_entry = {
            "type": "iteration",
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "observation": observation,
            "execution_time_ms": execution_time * 1000 if execution_time else None,
        }

        await self._write_log_entry(log_entry)

        # 不在这里输出到控制台，避免与react_loop.py中的print重复
        # react_loop.py已经负责输出到控制台

    async def log_model_call(
        self,
        messages: List[Dict],
        response: str,
        response_time: float,
        model_info: Dict,
    ) -> None:
        """记录模型调用详情"""
        if not self.file_handle:
            return

        log_entry = {
            "type": "model_call",
            "timestamp": datetime.now().isoformat(),
            "model_info": model_info,
            "messages_count": len(messages),
            "response_time_ms": response_time * 1000,
            "response_length": len(response),
            "messages": messages,  # 保存完整对话上下文
            "response": response,
        }

        await self._write_log_entry(log_entry)

    async def log_tool_call(
        self,
        tool_name: str,
        tool_input: Dict,
        result: Any,
        execution_time: float,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """记录工具调用详情"""
        if not self.file_handle:
            return

        log_entry = {
            "type": "tool_call",
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "tool_input": tool_input,
            "result": str(result) if result is not None else None,
            "result_type": type(result).__name__,
            "execution_time_ms": execution_time * 1000,
            "success": success,
            "error": error,
            "metadata": metadata or {},
        }

        await self._write_log_entry(log_entry)

    async def log_context_update(
        self, update_type: str, content: str, metadata: Optional[Dict] = None
    ) -> None:
        """记录上下文更新"""
        if not self.file_handle:
            return

        log_entry = {
            "type": "context_update",
            "timestamp": datetime.now().isoformat(),
            "update_type": update_type,
            "content": content[:500] + "..." if len(content) > 500 else content,
            "content_length": len(content),
            "metadata": metadata or {},
        }

        await self._write_log_entry(log_entry)

    async def log_error(
        self, error_type: str, error_message: str, context: Optional[Dict] = None
    ) -> None:
        """记录错误信息"""
        if not self.file_handle:
            return

        log_entry = {
            "type": "error",
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {},
        }

        await self._write_log_entry(log_entry)

    async def finish_task(
        self,
        final_status: str,
        total_iterations: int,
        total_time: float,
        summary: Optional[Dict] = None,
    ) -> None:
        """完成任务，写入总结"""
        if not self.file_handle:
            return

        log_entry = {
            "type": "task_complete",
            "timestamp": datetime.now().isoformat(),
            "final_status": final_status,
            "total_iterations": total_iterations,
            "total_time_seconds": total_time,
            "summary": summary or {},
        }

        await self._write_log_entry(log_entry)

        # 关闭文件
        await self.file_handle.close()
        self.file_handle = None

        if self.current_log_file:
            print(f"📋 Task log saved: {self.current_log_file.name}")

        # 创建简洁的日志摘要文件
        await self._create_log_summary(log_entry, summary)

    async def _write_log_entry(self, entry: Dict) -> None:
        """写入日志条目"""
        if not self.file_handle:
            return

        try:
            log_line = (
                json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            # 类型检查器认为file_handle可能是None，但我们已经检查过了
            file_handle = self.file_handle
            if file_handle:
                await file_handle.write(log_line)
                await file_handle.flush()
        except Exception as e:
            print(f"⚠️  Log write failed: {e}")

    async def _create_log_summary(
        self, completion_entry: Dict, summary: Optional[Dict]
    ) -> None:
        """创建日志摘要文件"""
        if not self.current_log_file:
            return

        summary_file = self.current_log_file.with_suffix(".summary.json")

        summary_data = {
            "task_info": {
                "log_file": str(self.current_log_file),
                "project_path": str(self.project_path),
                "completion": completion_entry,
            },
            "quick_stats": summary or {},
            "log_location": str(self.current_log_file.relative_to(self.project_path)),
        }

        try:
            async with aiofiles.open(summary_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(summary_data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"⚠️  Summary file creation failed: {e}")

    async def get_recent_logs(self, limit: int = 10) -> List[Dict]:
        """获取最近的日志文件列表"""
        try:
            log_files = sorted(
                [
                    f
                    for f in self.logs_dir.glob("*.log")
                    if not f.name.endswith(".summary.json")
                ],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )

            recent_logs = []
            for log_file in log_files[:limit]:
                try:
                    # 读取文件头部获取任务信息
                    async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
                        first_line = await f.readline()
                        if first_line:
                            header = json.loads(first_line.strip())
                            recent_logs.append(
                                {
                                    "file": str(
                                        log_file.relative_to(self.project_path)
                                    ),
                                    "task_id": header.get("task_id"),
                                    "task_description": header.get("task_description"),
                                    "timestamp": header.get("timestamp"),
                                    "size": log_file.stat().st_size,
                                }
                            )
                except Exception:
                    continue

            return recent_logs
        except Exception as e:
            print(f"⚠️  Get log list failed: {e}")
            return []

    async def cleanup_old_logs(self, keep_days: int = 7) -> None:
        """清理旧的日志文件"""
        try:
            import time

            cutoff_time = time.time() - (keep_days * 24 * 3600)

            for log_file in self.logs_dir.glob("*.log*"):
                if log_file.stat().st_mtime < cutoff_time:
                    try:
                        log_file.unlink()
                        print(f"🗑️  Clean old log: {log_file.name}")
                    except Exception as e:
                        print(f"⚠️  Clean log failed {log_file.name}: {e}")
        except Exception as e:
            print(f"⚠️  Log cleanup failed: {e}")

    async def log_planning_point(
        self,
        iteration: int,
        context: Dict[str, Any],
        planning_response: str,
        confidence: float,
    ):
        """记录动态规划点"""
        await self._write_log_entry(
            {
                "type": "planning_point",
                "timestamp": asyncio.get_event_loop().time(),
                "iteration": iteration,
                "context": context,
                "planning_response": planning_response,
                "confidence": confidence,
            }
        )


# 全局日志管理器实例
_loggers: Dict[str, AgentLogger] = {}


def get_logger(project_path: Path) -> AgentLogger:
    """获取项目的日志管理器"""
    project_key = str(project_path.absolute())
    if project_key not in _loggers:
        _loggers[project_key] = AgentLogger(project_path)
    return _loggers[project_key]
