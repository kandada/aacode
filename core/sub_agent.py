# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

# 子Agent
# core/sub_agent.py
"""
子Agent实现，专注于特定任务
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
import asyncio
from aacode.i18n import t

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ..core.agent import BaseAgent
    from ..core.react_loop import AsyncReActLoop
else:
    from .agent import BaseAgent
    from .react_loop import AsyncReActLoop


class SubAgent(BaseAgent):
    """子Agent，专注于特定任务类型"""

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        model_caller: Any,
        tools: Dict[str, Any],
        context_manager: Any,
        parent_agent_id: Optional[str] = None,
        project_path: Optional[Path] = None,
        context_config: Any = None,
        route_context: Optional[Dict[str, Any]] = None,
        usage_meta: Optional[Dict[str, Any]] = None,
        session_manager: Any = None,
        max_iterations: int = 15,
        **kwargs,
    ):

        # Keep the native-tool-call instruction in the static system prompt so the
        # user message can stay byte-identical to the persisted task text.
        system_prompt = (
            system_prompt.rstrip()
            + "\n\n⚡ Always use native function calls (tool_calls) — do NOT output "
            "JSON/text-formatted tool call info in your response. The system executes "
            "tools automatically and returns results as tool role messages."
            "\n\nWhen the task is complete, call submit_result exactly once with a concise "
            "summary, exact files changed, remaining next steps, unresolved errors, and key "
            "evidence. Do not call other tools after submit_result."
        )
        self._structured_result: Optional[Dict[str, Any]] = None
        tools = dict(tools or {})
        tools["submit_result"] = self.submit_result
        try:
            from aacode.utils.tool_registry import get_global_registry
            from aacode.utils.tool_schemas import SUBMIT_RESULT_SCHEMA
            get_global_registry().register(self.submit_result, SUBMIT_RESULT_SCHEMA)
        except Exception:
            pass

        super().__init__(
            agent_id=agent_id,
            system_prompt=system_prompt,
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=max_iterations,
        )

        self.parent_agent_id = parent_agent_id
        self.task_description: Optional[str] = None
        self.project_path = project_path
        self.usage_meta = usage_meta or {"source": "subagent"}
        self.session_manager = session_manager

        # 创建专用的ReAct循环（独立预算、独立 usage、独立工具集）
        self.react_loop = AsyncReActLoop(
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=max_iterations,
            project_path=project_path,
            context_config=context_config,
            route_context=route_context,
        )
        self.react_loop.usage_meta = self.usage_meta

    async def execute(
        self,
        task: str,
        init_instructions: str = "",
        task_dir: Optional[Path] = None,
        max_iterations: int = 20,
    ) -> Dict[str, Any]:
        """
        执行任务（子Agent通常执行单一任务）

        Args:
            task: 任务描述
            init_instructions: 初始化指令
            task_dir: 任务目录
            max_iterations: 最大迭代次数

        Returns:
            执行结果
        """
        print(f"\n🔄 SubAgent {self.agent_id} starting task")
        self.task_description = task
        self.start_time = float(asyncio.get_event_loop().time())

        # 重置会话历史
        self.reset()

        # 添加任务描述
        self.conversation_history.append(
            {
                "role": "user",
                "content": task,
            }
        )

        # 子 agent 拥有独立的持久化 session（可恢复、可审计）。
        child_session_id = self.usage_meta.get("session_id")
        if self.session_manager is not None:
            if not self.session_manager.current_session_id:
                child_session_id = await self.session_manager.create_session(
                    task, title=f"[subagent] {task[:60]}"
                )
            else:
                child_session_id = self.session_manager.current_session_id
            self.usage_meta["session_id"] = child_session_id

        async def _save_child_messages(new_msgs):
            if self.session_manager is None:
                return
            from aacode.utils.session_manager import SessionMessage
            from datetime import datetime
            for msg in new_msgs:
                if msg.get("role") not in ("assistant", "tool", "system"):
                    continue
                content = msg.get("content", "")
                reasoning = msg.get("reasoning_content")
                counter = getattr(self.session_manager, "_count_tokens", None)
                tokens = (counter(content or "") if callable(counter) else len(content or "") // 4)
                if reasoning:
                    tokens += (counter(reasoning) if callable(counter) else len(reasoning) // 4)
                self.session_manager.current_messages.append(
                    SessionMessage(
                        role=msg.get("role", "assistant"),
                        content=content,
                        timestamp=datetime.now().isoformat(timespec="seconds"),
                        tokens=tokens,
                        tool_calls=msg.get("tool_calls"),
                        tool_call_id=msg.get("tool_call_id"),
                        reasoning_content=reasoning,
                        usage=msg.get("usage") if isinstance(msg.get("usage"), dict) else None,
                        model=msg.get("model") or self.usage_meta.get("model"),
                    )
                )
            try:
                summary = self.session_manager.sessions_index.get(child_session_id)
                if summary:
                    summary.last_activity = datetime.now().isoformat(timespec="seconds")
                    summary.total_messages = len(self.session_manager.current_messages)
                    summary.total_tokens = self.session_manager._get_total_tokens()
                await self.session_manager._save_session()
                self.session_manager._save_sessions_index()
            except Exception:
                pass

        # 运行ReAct循环（子 agent 使用独立会话 id 做 usage 归因）
        self.react_loop.usage_meta = {
            **self.usage_meta,
            "source": "subagent",
            "session_id": child_session_id,
        }
        result = await self.react_loop.run(
            initial_prompt=self.system_prompt,
            task_description=task,
            session_id=child_session_id,
            on_new_messages=_save_child_messages,
        )
        if self.session_manager is not None:
            try:
                summary = self.session_manager.sessions_index.get(child_session_id)
                if summary:
                    summary.status = "completed"
                await self.session_manager._save_session()
                self.session_manager._save_sessions_index()
            except Exception:
                pass

        # 更新统计
        self.iterations = len(self.react_loop.steps)
        if self._structured_result and isinstance(self._structured_result.get("summary"), str):
            result = dict(result)
            # The structured submission is the authoritative final answer.
            result["final_thought"] = self._structured_result["summary"]

        execution_time = 0.0
        if self.start_time is not None:
            execution_time = asyncio.get_event_loop().time() - self.start_time

        return {
            **result,
            "agent_id": self.agent_id,
            "task": task,
            "agent_stats": self.get_stats(),
            "execution_time": execution_time,
            "usage": getattr(self.react_loop, "_task_usage", {}),
            "structured": self._structured_result,
        }

    async def submit_result(self, **result) -> Dict[str, Any]:
        """Record the structured final result for this sub-agent."""
        try:
            if not isinstance(result, dict):
                return {"error": "Result must be dict format"}
            if not str(result.get("summary") or "").strip():
                return {"error": "submit_result requires a non-empty summary"}
            for key in ("files_changed", "next_steps", "errors", "key_evidence"):
                value = result.get(key)
                if value is not None and not isinstance(value, list):
                    result[key] = [str(value)]
            self._structured_result = dict(result)
            return {
                "success": True,
                "message": "Structured result recorded. The sub-agent task is complete.",
            }
        except Exception as e:
            return {"error": f"Submit result failed: {str(e)}"}

    async def get_focused_tools(self) -> Dict[str, Any]:
        """获取聚焦的工具集（可根据Agent类型定制）"""
        # 基础工具集
        base_tools = ["run_shell"]

        # 根据Agent ID判断类型
        if "test" in self.agent_id:
            base_tools.append("run_tests")

        if "research" in self.agent_id:
            # 研究Agent可能需要网络搜索
            pass

        # 返回过滤后的工具
        focused_tools = {
            name: func for name, func in self.tools.items() if name in base_tools
        }

        # 添加submit_result工具
        focused_tools["submit_result"] = self.submit_result

        return focused_tools
