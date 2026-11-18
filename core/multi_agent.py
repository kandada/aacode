# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

# core/multi_agent.py
"""Real sub-agent delegation with independent budgets and usage attribution."""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from aacode.i18n import t
from aacode.utils.colors import style, BLUE
from aacode.utils.token_usage import fingerprint


@dataclass
class AgentTask:
    """Agent 任务定义"""

    id: str
    description: str
    parent_id: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed, budget_exceeded
    result: Optional[Dict] = None
    created_at: float = 0.0


CODE_TOOL_NAMES = {"run_shell", "search_history", "read_history", "run_skills", "submit_result"}
RESEARCH_TOOL_NAMES = CODE_TOOL_NAMES | {
    "search_web", "fetch_url", "fetch_rendered", "browser_call", "browser_tools", "ax_act",
}
TODO_TOOL_NAMES = {
    "add_todo_item", "mark_todo_completed", "update_todo_item", "get_todo_summary",
}


class MultiAgentSystem:
    """多 Agent 协作系统。

    子 Agent 是真实的、独立预算的 Agent，而不是占位实现。父 Agent 只拿到
    结构化结果（最终回答 + 状态 + usage），不会把子 Agent 的完整 transcript
    重新塞回上下文。
    """

    def __init__(self, main_agent, context_manager):
        self.main_agent = main_agent
        self.context_manager = context_manager
        self.sub_agents: Dict[str, Any] = {}
        self.tasks: Dict[str, AgentTask] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        try:
            from aacode.config import settings
            concurrency = max(1, int(getattr(settings.agent, "max_sub_agent_concurrency", 3) or 3))
        except Exception:
            concurrency = 3
        self._semaphore = asyncio.Semaphore(concurrency)

    def _tool_names(self, task_type: str) -> set:
        task_type = (task_type or "general").lower()
        if task_type in ("code", "code_analysis", "test", "testing"):
            return set(CODE_TOOL_NAMES)
        if task_type in ("research", "search"):
            return set(RESEARCH_TOOL_NAMES)
        return set(CODE_TOOL_NAMES | {"search_web", "fetch_url", "fetch_rendered"})

    async def delegate_task(
        self,
        task_description: str,
        task_type: str = "general",
        context_strategy: str = "isolated",
    ) -> Dict[str, Any]:
        """Run a real child agent and return a compact result.

        ``context_strategy`` is retained for compatibility. The default is an
        isolated context; ``shared``/``minimal`` add a short project summary to
        the child's task rather than copying the parent transcript.
        """
        try:
            from aacode.config import settings
            max_depth = int(getattr(settings.agent, "max_sub_agent_depth", 2) or 2)
        except Exception:
            max_depth = 2
        parent_depth = int(getattr(self.main_agent, "agent_depth", 0) or 0)
        if parent_depth >= max_depth:
            return {
                "status": "error",
                "error": f"Subagent depth limit reached ({max_depth}); refusing to delegate further.",
            }

        task_id = f"task_{len(self.tasks)}_{int(asyncio.get_event_loop().time() * 1000)}"
        task = AgentTask(
            id=task_id,
            description=task_description,
            parent_id="main",
            status="pending",
            created_at=asyncio.get_event_loop().time(),
        )
        self.tasks[task_id] = task

        async with self._semaphore:
            task.status = "running"
            try:
                result = await self._run_child(
                    task_id=task_id,
                    task_description=task_description,
                    task_type=task_type,
                    context_strategy=context_strategy,
                    depth=parent_depth + 1,
                )
                task.status = result.get("status", "completed")
                task.result = result
            except asyncio.TimeoutError:
                task.status = "failed"
                task.result = {"status": "failed", "error": "Subagent timed out"}
            except Exception as exc:
                task.status = "failed"
                task.result = {"status": "failed", "error": str(exc)}

        return {
            "task_id": task_id,
            "status": task.status,
            "result": task.result,
        }

    async def _run_child(
        self,
        task_id: str,
        task_description: str,
        task_type: str,
        context_strategy: str,
        depth: int,
    ) -> Dict[str, Any]:
        from aacode.config import settings
        from .sub_agent import SubAgent

        parent = self.main_agent
        tool_names = self._tool_names(task_type)
        # Keep todo tools only when the parent tracks todos; they add little
        # value in short research tasks otherwise.
        if getattr(settings.agent, "enable_todo_tracking", True):
            tool_names |= TODO_TOOL_NAMES
        try:
            from aacode.utils.tool_schemas import get_all_schemas
            child_schemas = {k: v for k, v in get_all_schemas().items() if k in tool_names}
            tools_hash = fingerprint(child_schemas)
        except Exception:
            tools_hash = None

        model_config = dict(parent.model_config or {})
        if getattr(settings.agent, "subagent_model", ""):
            profile = settings.get_model_profile(settings.agent.subagent_model)
            for key in ("name", "gateway", "base_url", "api_key", "max_tokens", "max_output_tokens"):
                if profile.get(key) is not None:
                    model_config[key] = profile[key]
        child_caller = parent._create_model_caller(model_config, tool_names)

        child_tools = {
            name: func for name, func in parent.tools.items()
            if name in tool_names and name not in ("delegate_task", "create_sub_agent")
        }

        child_context = copy.copy(settings.context)
        child_context.task_input_token_budget = int(
            getattr(settings.agent, "subagent_input_token_budget", 0) or 0
        )
        child_context.task_output_token_budget = int(
            getattr(settings.agent, "subagent_output_token_budget", 0) or 0
        )

        profile = settings.get_model_profile(model_config.get("name"))
        route = {
            "provider": str(profile.get("name") or "").split("-", 1)[0],
            "model": str(profile.get("name") or ""),
            "context_window": int(profile.get("context_window") or settings.context.max_context_length or 1_000_000),
            "max_output_tokens": int(profile.get("max_output_tokens") or profile.get("max_tokens") or 0),
            "pricing": profile.get("pricing") if isinstance(profile.get("pricing"), dict) else None,
        }

        from aacode.utils.session_manager import SessionManager
        child_manager = SessionManager(parent.project_path)
        parent_session = getattr(parent.session_manager, "current_session_id", None) or "session"
        child_session_id = await child_manager.create_session(
            task_description, title=f"[subagent] {task_description[:60]}"
        )

        extra_context = ""
        if context_strategy == "shared" and self.context_manager is not None:
            try:
                extra_context = await self.context_manager.get_context()
            except Exception:
                extra_context = ""
        elif context_strategy == "minimal" and self.context_manager is not None:
            try:
                extra_context = await self.context_manager.get_compact_context()
            except Exception:
                extra_context = ""
        prompt = task_description
        if extra_context:
            prompt = f"{task_description}\n\nProject context:\n{extra_context[:6000]}"

        child = SubAgent(
            agent_id=f"sub_{task_type}_{task_id}",
            system_prompt=(
                f"You are a focused {task_type} sub-agent. Complete the assigned task and "
                "return a concise result. Do not delegate further. Use the available tools "
                "only as needed, and stop when the task is complete."
            ),
            model_caller=child_caller,
            tools=child_tools,
            context_manager=self.context_manager,
            parent_agent_id=parent.agent_id,
            project_path=parent.project_path,
            context_config=child_context,
            route_context=route,
            session_manager=child_manager,
            usage_meta={
                "source": "subagent",
                "session_id": child_session_id,
                "parent_session_id": parent_session,
                "task_id": task_id,
                "model": model_config.get("name"),
                "gateway": model_config.get("gateway"),
                "tools_hash": tools_hash,
            },
            max_iterations=int(getattr(settings.agent, "max_sub_agent_iterations", 30) or 30),
        )
        self.sub_agents[task_id] = child

        timeout = int(getattr(settings.agent, "subagent_timeout_seconds", 600) or 600)
        result = await asyncio.wait_for(child.execute(prompt), timeout=timeout)

        child_usage = result.get("usage") or {}
        try:
            parent.session_manager.record_subagent_usage(child_usage)
        except Exception:
            pass

        final_text = (
            result.get("final_thought")
            or result.get("message")
            or result.get("error")
            or ""
        )
        final_text = str(final_text)
        spill_path = None
        if len(final_text) > 12000:
            try:
                from aacode.utils.context_policy import spill_text
                path = spill_text(
                    parent.project_path,
                    parent_session,
                    task_id,
                    final_text,
                    label="subagent",
                )
                if path:
                    spill_path = str(path)
                    final_text = final_text[:8000] + (
                        f"\n\n[... subagent output truncated; full result: {path} ...]"
                    )
            except Exception:
                final_text = final_text[:12000] + "\n[... subagent output truncated ...]"

        return {
            "status": result.get("status", "completed"),
            "result": final_text,
            "iterations": result.get("iterations"),
            "usage": result.get("usage") or {},
            "structured": result.get("structured"),
            "session_id": child_session_id,
            "spill_path": spill_path,
            "depth": depth,
        }

    async def _prepare_subagent_context(self, strategy: str) -> str:
        """Compatibility helper retained for external callers."""
        if strategy == "isolated":
            return ""
        if strategy == "shared" and self.context_manager is not None:
            try:
                return await self.context_manager.get_context()
            except Exception:
                return ""
        if strategy == "minimal" and self.context_manager is not None:
            try:
                return await self.context_manager.get_compact_context()
            except Exception:
                return ""
        return ""

    async def _notify_main_agent(self, task: AgentTask) -> None:
        print(style(t("multi.task_done", id=task.id), fg=BLUE))
