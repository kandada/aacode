# ReAct循环
# core/react_loop.py
"""
轻量化ReAct循环实现
支持异步工具调 with 和上下文管理
"""

from __future__ import annotations

import asyncio
import time
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass
from datetime import datetime

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from ..utils.agent_logger import get_logger
    from ..utils.tool_registry import get_global_registry
    from ..config import settings
else:
    from ..utils.agent_logger import get_logger
    from ..utils.tool_registry import get_global_registry
    from ..config import settings
from aacode.i18n import t
from aacode.utils.message_utils import (
    estimate_tokens as _util_estimate_tokens,
    split_into_rounds,
    build_compact_view,
    _find_last_n_real_user_round,
)


@dataclass
class ActionItem:
    """单个Action项"""

    action: str
    action_input: Dict
    observation: Optional[str] = None


@dataclass
class ReActStep:
    """ReAct单步记录"""

    thought: str
    raw_response: str = ""  # 模型完整响应（含 thinking），  forSave 会话历史
    actions: Optional[List[ActionItem]] = None
    timestamp: float = 0.0

    def __post_init__(self):
        if self.actions is None:
            self.actions = []


class AsyncReActLoop:
    """异步ReAct循环"""

    def __init__(
        self,
        model_caller: Callable[[List[Dict]], Awaitable[str]],
        tools: Dict[str, Callable],
        context_manager: Any,
        max_iterations: int = 50,
        project_path: Optional[Path] = None,
        todo_manager: Optional[Any] = None,
        context_config: Optional[Any] = None,
    ):
        """
        initializedReAct循环

        Args:
            model_caller: 异步模型调 with 函数
            tools: 工具字典
            context_manager: 上下文管理器
            max_iterations: 最大迭代次数
            project_path: 项目路径（  for日志记录）
            todo_manager: 待办管理器
            context_config: 上下文配置
        """
        self.model_caller = model_caller
        self.tools = tools
        self.context_manager = context_manager
        self.max_iterations = max_iterations
        self.project_path = project_path
        self.todo_manager = todo_manager

        self.steps: List[ReActStep] = []
        self.current_context: str = ""
        self.logger = get_logger(project_path) if project_path else None

        # 上下文配置
        self.context_config = context_config

        # Token计数器（  for智能缩减）
        from ..utils.session_manager import _load_tiktoken_encoding

        self.encoding = _load_tiktoken_encoding()

        # 上下文压缩摘要缓存
        self._compact_summary: Optional[str] = None
        self._compact_summary_msg_count: int = 0
        self._post_compact_tokens: int = 0  # 压缩后的 compact view token 基准值

        # Stale loop detection: tracks fetch_url results per domain to detect
        # when the model repeatedly hits pages that return no readable content
        # (e.g. JS-rendered pages, redirect walls, CSS-only garbage).
        #
        # Design rationale:
        # - We do NOT track "consecutive same tool" — run_shell is the universal
        #   tool used for 80%+ of all operations (reading files, running tests,
        #   git, etc.) and consecutive calls are normal productive workflow.
        #   Tracking tool name alone produces massive false positives.
        # - We ONLY detect fetch_url stale domains because the signal is clear:
        #   3+ returns from the same domain with zero readable text means the
        #   model really is wasting iterations and should switch to search_web.
        #
        # Performance: O(actions * unique_domains) per iteration, where both
        # are bounded (actions ≤ ~5, unique_domains ≤ ~20). Negligible overhead.
        self._stale_tracker: Dict[str, Any] = {
            "fetch_url_by_domain": {},
        }
        self._stale_warnings_issued: set = set()

    async def run(
        self,
        initial_prompt: str,
        task_description: str,
        todo_manager: Optional[Any] = None,
        history_messages: Optional[List[Dict]] = None,
        on_new_messages: Optional[Callable[[List[Dict]], Awaitable[None]]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        运 linesReAct循环

        Args:
            initial_prompt: 完整系统提示（调用方已组装好 todo/planning 等全部上下文）
            task_description: 任务描述
            todo_manager: to-do-list管理器（用于运行中错误时追加 todo 项，不影响初始 prompt）
            history_messages: 同一会话的历史对话消息（  for多轮任务上下文衔接）
            session_id: 当前会话ID（用于多会话并发时的 todo 隔离）

        Returns:
            execute结果
        """
        # 清除上一轮的 last_messages，确保失败时不残留旧数据
        self.last_messages = None

        # Reset stale loop detector for this run — each react_loop.run() call
        # starts with a clean tracker (fresh fetch_url domain history).
        self._stale_tracker = {
            "fetch_url_by_domain": {},
        }
        self._stale_warnings_issued = set()

        # 开始日志记录
        if self.logger:
            task_id = await self.logger.start_task(task_description)

        print(f"🚀 Starting ReAct loop, max {self.max_iterations} iterations")

        # 初始上下文
        self.current_context = await self.context_manager.get_context()

        # initial_prompt 已由调用方（main_agent.execute）组装完整：
        # SYSTEM_PROMPT + skills + working_dir + analysis + init_instructions + todo_section
        # 此处仅追加静态的 Planning in Thought 指令（也适用于 sub_agent）
        messages = [
            {
                "role": "system",
                "content": f"""{initial_prompt}

Important - Planning in Thought:
During each thought, naturally plan:
- For complex tasks (involving applications, systems, projects, architecture, etc.), analyze requirements, check the environment, and formulate a plan in the first few thoughts
- If the task contains keywords like "plan", "analyze", "check", "redesign", "strategy", "requirements", proactively plan in your thoughts
- Keep thinking natural, treating planning as part of the thought process, not a separate task

""",
            },
        ]

        # ─── 多轮任务上下文衔接 ───────────────────────────────────
        # 同一会话中，第二轮及后续任务需要看到之前的对话历史
        # history_messages 来自 session_manager，包含之前所有轮次的 user/assistant/tool 消息
        # 插入到 system prompt 之后、当前任务之前，让模型了解之前做了什么
        # ⚠️ 保留 tool 消息，否则前序任务的工具执行结果在多轮后会逐步丢失
        # ⚠️ token 超限时会由 _compact_context 自动压缩，不需要在这里截断
        if history_messages:
            for msg in history_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                has_tool_info = msg.get("tool_calls") or msg.get("tool_call_id")
                if role in ("user", "assistant", "tool", "system") and (content or has_tool_info):
                    if role == "tool":
                        messages.append({
                            "role": "tool",
                            "tool_call_id": msg.get("tool_call_id", ""),
                            "content": content,
                        })
                    else:
                        messages.append({
                            "role": role,
                            "content": content,
                            **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {}),
                            **({"reasoning_content": msg["reasoning_content"]} if msg.get("reasoning_content") else {}),
                        })
            if len(history_messages) > 0:
                print(f"📜 Loaded {len(history_messages)}  history messages into context")

        messages.append(
            {
                "role": "user",
                "content": f"Task: {task_description}\n\nCurrent context:\n{self.current_context}\n\nUse native function calls (tool_calls) to execute tools. Do NOT output JSON/text-formatted tool call information in your response — the system handles tool execution automatically via the API's tool_calls mechanism and returns results as tool role messages.",
            },
        )

        start_time = asyncio.get_event_loop().time()

        for iteration in range(self.max_iterations):
            iteration_start = asyncio.get_event_loop().time()
            print(f"\n🔄 Iteration {iteration + 1}/{self.max_iterations}")

            # 记录本轮开始前的消息总数，用于增量持久化
            msg_count_before = len(messages)

            # 调 with 模型Get 思考（使用 round-aware 压缩视图）
            # 同时缓存 compact view 和 token 数，供后续自适应截断复用，避免重复 split_into_rounds
            model_start = asyncio.get_event_loop().time()
            effective_msgs, _, compact_tokens = self._build_compact_view(messages)
            self._cached_compact_view = effective_msgs
            self._cached_compact_tokens = compact_tokens
            self._cached_compact_msg_count = len(messages)
            response = await self.model_caller(effective_msgs)
            model_time = asyncio.get_event_loop().time() - model_start

            # 提取文本和 tool_calls（兼容旧版返回字符串）
            if isinstance(response, dict):
                response_text = response.get("text", "")
                native_tool_calls = response.get("tool_calls", [])
                reasoning_content = response.get("reasoning_content", None)
            else:
                response_text = response
                native_tool_calls = []
                reasoning_content = None

            # Log model call
            if self.logger:
                await self.logger.log_model_call(
                    messages=messages,
                    response=response_text,
                    response_time=model_time,
                    model_info={"iteration": iteration + 1},
                )

            # 解析响应
            if native_tool_calls:
                # ─── 原生 Tool Calling 路径 ───
                thought = response_text
                actions = []
                for tc in native_tool_calls:
                    arguments = tc["arguments"]
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}
                    actions.append(ActionItem(
                        action=tc["name"],
                        action_input=arguments,
                    ))
            else:
                # ─── 文本解析路径（回退） ───
                thought, actions = self._parse_response(response_text)

            # 自动更新待办清单（已简化：不再自动记录思考过程）
            # if todo_manager:
            #     await self._update_todo_from_thought(thought, todo_manager)

            # 记录步骤（raw_response 保留完整模型响应，含 thinking，  for会话历史Save ）
            step = ReActStep(
                thought=thought, raw_response=response_text, actions=[], timestamp=asyncio.get_event_loop().time()
            )
            self.steps.append(step)

            # 注意：模型思考内容已在 main_agent.py 中流式打印，此处不再重复显示

            # 检查是否完成
            if native_tool_calls:
                # 原生 Tool Calling: 有 tool_calls = 未完成，继续execute
                pass
            elif not actions:
                # 无 tool_calls 且无文本 actions → 任务完成
                # 先追加 assistant 回复到 messages，确保 last_messages 包含模型输出内容
                response_entry = {"role": "assistant", "content": response_text}
                if reasoning_content:
                    response_entry["reasoning_content"] = reasoning_content
                messages.append(response_entry)

                # 增量持久化：本轮新消息立即保存到会话文件
                if on_new_messages:
                    await on_new_messages(messages[msg_count_before:])

                print(t("agent.task_done", default="✅ Task completed"))
                total_time = asyncio.get_event_loop().time() - start_time
                if self.logger:
                    await self.logger.log_iteration(
                        iteration=iteration + 1,
                        thought=thought,
                        action=None,
                        action_input=None,
                        execution_time=asyncio.get_event_loop().time() - iteration_start,
                    )
                    await self.logger.finish_task(
                        final_status="completed",
                        total_iterations=iteration + 1,
                        total_time=total_time,
                        summary={"final_thought": response_text},
                    )
                self.last_messages = messages
                return {
                    "status": "completed",
                    "final_thought": response_text,
                    "iterations": iteration + 1,
                    "steps": self.steps,
                    "total_time": total_time,
                }

            # execute所有Action（增强错误处理和重试机制）
            all_observations = []
            all_observations_for_display = []  #   for显示的简化版本

            # ─── Stale loop detection: warn model when stuck on unreadable fetch_url pages ───
            # Injects a [SYSTEM WARNING] into the message context so the model sees it in
            # the next API call. Each unique domain warning is issued at most once per run
            # (tracked by _stale_warnings_issued). Does NOT track run_shell or other tools.
            stale_warning = self._detect_stale_loop(actions)
            if stale_warning:
                print(f"\n⚠️  {stale_warning}")
                messages.append({
                    "role": "system",
                    "content": f"[SYSTEM WARNING]: {stale_warning}",
                })

            # 基于剩余上下文预算计算自适应截断阈值（复用模型调用前的缓存）
            if len(messages) == getattr(self, '_cached_compact_msg_count', -1):
                current_tokens = self._cached_compact_tokens
            else:
                effective_msgs, _, current_tokens = self._build_compact_view(messages)
            total_budget = (
                self.context_config.max_context_length
                if self.context_config
                else 16000
            )
            remaining_budget = max(0, total_budget - current_tokens)
            self._adaptive_threshold_chars = int(
                remaining_budget * settings.output.budget_ratio * 4
            )

            for i, action_item in enumerate(actions):
                if sys.stdout.isatty():
                    print(f"🛠️  Action {i + 1}/{len(actions)}: {action_item.action}")
                action_start = asyncio.get_event_loop().time()

                # 添加重试机制（使 with 配置的最大重试次数，来自 aacode_config.yaml）
                max_retries = settings.limits.max_retries
                retry_count = 0
                observation = None
                observation_for_display = None

                while retry_count < max_retries:
                    try:
                        # Get 完整的工具execute结果
                        full_result = await self._execute_action_internal(
                            action_item.action, action_item.action_input
                        )

                        # 为Agent保留完整结果
                        observation = full_result

                        # 为 user显示生成简化版本
                        observation_for_display = self._format_observation_for_display(
                            action_item.action, full_result
                        )

                        # 检查是否需要重试（某些错误可以重试）
                        if observation and isinstance(observation, str):
                            if "error" in observation.lower():
                                retryable_errors = [
                                    "timeout",
                                    "connection",
                                    "temporary",
                                ]
                                if any(
                                    err in observation.lower()
                                    for err in retryable_errors
                                ):
                                    retry_count += 1
                                    if retry_count < max_retries:
                                        print(
                                            f"⚠️  Action failed, retry {retry_count}/{max_retries}..."
                                        )
                                        await asyncio.sleep(1)  # 等待1秒后重试
                                        continue
                        break  # 成功或不可重试的错误，退出重试循环

                    except asyncio.CancelledError:
                        # 任务被取消，重新抛出以便上层处理
                        raise
                    except Exception as e:
                        retry_count += 1
                        if retry_count < max_retries:
                            print(
                                f"⚠️  Action error, retry {retry_count}/{max_retries}: {str(e)}"
                            )
                            await asyncio.sleep(1)
                        else:
                            observation = f"Execution error (retried {max_retries} times): {str(e)}"
                            observation_for_display = observation
                            break

                if observation is None:
                    observation = f"Execution failed: no result (retried {max_retries} times)"
                    observation_for_display = observation

                action_time = asyncio.get_event_loop().time() - action_start

                # 记录观察结果（完整版本）
                action_item.observation = observation
                assert step.actions is not None, "step.actions should not be None"
                step.actions.append(action_item)
                all_observations.append(observation)  # AgentGet 完整内容
                all_observations_for_display.append(
                    observation_for_display or observation or ""
                )  #  user看到简化版本

                # 实时打印 Observation（供客户端显示）
                display_obs = observation_for_display or observation or ""
                if display_obs:
                    # 截断过长的输出，避免刷屏
                    max_display = 3000
                    if len(display_obs) > max_display:
                        display_obs = display_obs[:max_display] + f"\n... (truncated, {len(observation_for_display or observation)} chars total)"
                    print(f"📋 Observation:\n{display_obs}", flush=True)
                    # ─── 源头数据：发送完整原始内容给前端做 markdown 渲染 ───
                    # Rust 层 read_line() 逐行读取会：1) 丢弃空行  2) 拦截 {/[ 开头的 JSON 行
                    # 前端逐行拼接重组的内容可能丢失信息，与 Python 原始数据不一致
                    # 因此必须在 Python 侧发送 seg_content，前端渲染时使用此原始数据而非 Rust 重组数据
                    if not sys.stdout.isatty():
                        _full_obs = (observation_for_display or observation or "")
                        import json as _json
                        print(_json.dumps({"type": "seg_content", "seg": "observation", "content": _full_obs}), flush=True)

                # 🔥 新增：从错误中自动更新待办清单
                if todo_manager:
                    await self._update_todo_from_error(observation, todo_manager, session_id)

                # 死循环检测：记录 fetch_url 结果
                if action_item.action == "fetch_url":
                    url = (action_item.action_input or {}).get("url", "")
                    if url:
                        self._record_fetch_url_result(url, observation)

                # Log tool call
                if self.logger:
                    await self.logger.log_tool_call(
                        tool_name=action_item.action,
                        tool_input=action_item.action_input or {},
                        result=observation,
                        execution_time=action_time,
                        success=not (
                            observation.lower().startswith("error")
                            or "error" in observation.lower()
                        ),
                        metadata=(
                            {"retry_count": retry_count} if retry_count > 0 else None
                        ),
                    )

            # 合并所有观察结果（AgentGet 完整内容）
            observation = "\n".join(
                [f"Action {i + 1}  result: {obs}" for i, obs in enumerate(all_observations)]
            )

            # 合并显示版本（ user看到简化版本）
            observation_for_display = "\n".join(
                [
                    f"Action {i + 1}  result: {obs}"
                    for i, obs in enumerate(all_observations_for_display)
                ]
            )

            # 添加到上下文消息
            if native_tool_calls:
                # ─── 原生 Tool Calling 消息格式 ───
                # assistant 消息包含 tool_calls
                assistant_msg: dict = {"role": "assistant", "content": response_text}
                # kimi-k2 等模型要求 reasoning_content 必须在 assistant 消息中保持一致
                if reasoning_content:
                    assistant_msg["reasoning_content"] = reasoning_content
                openai_tool_calls = []
                for tc in native_tool_calls:
                    args_str = json.dumps(tc["arguments"], ensure_ascii=False) if isinstance(tc["arguments"], dict) else str(tc["arguments"])
                    openai_tool_calls.append({
                        "id": tc.get("id", f"call_{len(openai_tool_calls)}"),
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": args_str,
                        },
                    })
                assistant_msg["tool_calls"] = openai_tool_calls
                messages.append(assistant_msg)

                # tool 结果消息
                for otc, observation_item in zip(openai_tool_calls, all_observations):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": otc["id"],
                        "content": str(observation_item),
                    })
            else:
                # ─── 文本解析消息格式 ───
                messages.append({"role": "assistant", "content": response_text})
                messages.append(
                    {
                        "role": "system",
                        "content": f"[System] Tool execution result below. Please continue to the next step (Thought→Action) based on the result. If the task is completed, output the final summary directly.\n\nObservation: {observation}",
                    }
                )

            # 增量持久化：本轮新消息立即保存到会话文件
            # 在上下文压缩和 finalize 检查之前保存，确保取消/压缩都不会丢消息
            if on_new_messages:
                await on_new_messages(messages[msg_count_before:])

            # 上下文一致性检查（在 messages 更新后，确保 assistant token 统计正确）

            await self._validate_context_consistency(
                all_observations, all_observations_for_display, messages
            )

            # Log iteration（使 with 完整observation）
            if self.logger:
                await self.logger.log_iteration(
                    iteration=iteration + 1,
                    thought=thought,
                    action=", ".join([a.action for a in actions]) if actions else None,
                    action_input={"multiple_actions": True, "count": len(actions)},
                    observation=observation,  # 日志记录完整内容
                    execution_time=asyncio.get_event_loop().time() - iteration_start,
                )

            # 智能上下文缩减检查（基于传入模型的压缩视图 token 数）
            effective_msgs, was_compacted, compact_view_tokens = self._build_compact_view(messages)
            trigger_tokens_raw = (
                self.context_config.compact_trigger_tokens
                if self.context_config
                else 8000
            )
            context_max = (
                self.context_config.max_context_length
                if self.context_config
                else 131072
            )
            trigger_tokens = min(trigger_tokens_raw, context_max)

            if compact_view_tokens > trigger_tokens:
                msg_count_changed = len(messages) - self._compact_summary_msg_count
                if msg_count_changed > 20 or self._compact_summary is None:
                    print(f"📊 Compact view tokens: {compact_view_tokens}, trigger threshold: {trigger_tokens}")
                    await self._compact_context(messages)
                    if self.logger:
                        await self.logger.log_context_update(
                            update_type="compact",
                            content=f"Context compaction executed after iteration {iteration + 1} (compact_view_tokens: {compact_view_tokens})",
                        )

        total_time = asyncio.get_event_loop().time() - start_time
        if self.logger:
            await self.logger.finish_task(
                final_status="max_iterations_reached",
                total_iterations=self.max_iterations,
                total_time=total_time,
                summary={
                    "last_thought": self.steps[-1].thought if self.steps else None
                },
            )

        print("\n⚠️  Maximum iterations reached, task may not be complete")
        print(f"💡 Tip: continue the session to finish remaining work")

        self.last_messages = messages
        return {
            "status": "max_iterations_reached",
            "iterations": self.max_iterations,
            "steps": self.steps,
            "total_time": total_time,
            "message": "Maximum iterations reached, suggest continuing the session to complete the task",
        }

    def _parse_response(self, response: str) -> tuple:
        """解析模型响应（支持多个action）- 增强健壮性版本"""
        # 阶段1: 尝试解析JSON格式（支持多个action）
        json_patterns = [
            r"```json\s*\n(.*?)\n```",  # 标准json代码块
            r"```JSON\s*\n(.*?)\n```",  # 大写JSON
            r"```\s*\n(\{.*?\})\s*\n```",  # 普通代码块包裹的JSON
            r'(\{[\s\S]*?"thought"[\s\S]*?\})',  # 直接的JSON对象（包含thought字段）
            r"```json\s*\n(.*?)(?:\n```|$)",  # 不严格的结束标记
        ]

        for pattern in json_patterns:
            json_match = re.search(pattern, response, re.DOTALL)
            if json_match:
                json_str = None
                try:
                    json_str = json_match.group(1).strip()
                    # 清理可能的markdown残留
                    json_str = (
                        json_str.replace("```json", "")
                        .replace("```JSON", "")
                        .replace("```", "")
                        .strip()
                    )

                    # 尝试修复常见的JSON格式问题
                    json_str = self._fix_json_format(json_str)

                    data = json.loads(json_str)
                    thought = (
                        data.get("thought")
                        or data.get("thinking")
                        or data.get("reasoning")
                        or ""
                    )

                    # 支持单个action或多个action
                    actions_data = data.get("actions", [])
                    if not actions_data and "action" in data:
                        # 单个action的兼容格式
                        actions_data = [
                            {
                                "action": data.get("action"),
                                "action_input": data.get("action_input", {}),
                            }
                        ]

                    actions = []
                    for action_data in actions_data:
                        if isinstance(action_data, dict) and "action" in action_data:
                            action_name = action_data["action"]
                            action_input = (
                                action_data.get("action_input")
                                or action_data.get("input")
                                or {}
                            )

                            # 验证action_input是字典
                            if not isinstance(action_input, dict):
                                action_input = {"value": action_input}

                            actions.append(
                                ActionItem(
                                    action=action_name, action_input=action_input
                                )
                            )

                    if thought and actions:
                        return thought, actions
                except json.JSONDecodeError as e:
                    # 记录JSON解析错误，但继续尝试其他格式
                    print(f"⚠️  JSON parse failed (pattern {pattern[:20]}...): {str(e)}")
                    if json_str:
                        print(f"⚠️  Attempted JSON: {json_str[:100]}...")
                    else:
                        print(f"⚠️  Attempted JSON: [unable to extract JSON string]")
                    continue
                except Exception as e:
                    print(f"⚠️  JSON processing exception: {str(e)}")
                    continue

        # 阶段2: 解析文本格式（支持多个action）
        thought_match = re.search(
            r"Thought[:\s]*(.*?)(?=Action|$)", response, re.DOTALL | re.IGNORECASE
        )
        thought = thought_match.group(1).strip() if thought_match else response[:200]

        actions = []

        # 改进的解析逻辑：精确匹配Action和Action Input对
        lines = response.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # 匹配Action lines（支持编号，但Action名称不能是"Input"）
            action_match = re.match(
                r"Action\s*(\d+)?[:\s]+(?!Input)(.+)", line, re.IGNORECASE
            )

            if action_match:
                action_num = action_match.group(1)  # 可能是None
                action_name = action_match.group(2).strip()

                # 跳过空的action名称或只有冒号
                if (
                    not action_name
                    or action_name == ":"
                    or action_name.lower() == "input"
                ):
                    i += 1
                    continue

                # 清理action名称（移除可能的引号和空格）
                action_name = action_name.strip("`\"' ")

                # 查找对应的Action Input（最多向下查找10 lines）
                action_input = {}
                found_input = False

                for j in range(i + 1, min(i + 11, len(lines))):
                    input_line = lines[j].strip()

                    # 如果遇到下一个Action，停止查找
                    if re.match(
                        r"Action\s*(\d+)?[:\s]+(?!Input)", input_line, re.IGNORECASE
                    ):
                        break

                    # 匹配 Action Input / Input  lines
                    input_match = re.match(
                        r"(?:Action\s*)?Input\s*(\d+)?[:\s]+(.+)", input_line, re.IGNORECASE
                    )

                    if input_match:
                        input_num = input_match.group(1)
                        input_text = input_match.group(2).strip()

                        # 检查编号是否匹配（如果都有编号）
                        if action_num and input_num and action_num != input_num:
                            continue

                        # 解析输入
                        if input_text.startswith("{"):
                            try:
                                # 清理可能的markdown残留
                                clean_input = (
                                    input_text.replace("```json", "")
                                    .replace("```", "")
                                    .strip()
                                )
                                # 尝试修复JSON格式
                                clean_input = self._fix_json_format(clean_input)
                                action_input = json.loads(clean_input)
                                found_input = True
                                break
                            except json.JSONDecodeError:
                                # 单 linesJSON parse failed，尝试收集后续 lines拼接完整JSON
                                collected_lines: list[str] = [input_text]
                                for k in range(j + 1, min(j + 20, len(lines))):
                                    # 遇到下一个Action标记则停止收集
                                    if re.match(
                                        r"\s*(?:Thought|Action|Observation)[:\s]",
                                        lines[k],
                                        re.IGNORECASE,
                                    ):
                                        break
                                    # 遇到空 lines也停止收集
                                    if not lines[k].strip():
                                        break
                                    collected_lines.append(lines[k])

                                    # 方式1: 字面换 lines连接（适  for原本就合法的多 linesJSON）
                                    json_text1 = "\n".join(collected_lines)
                                    clean1 = (
                                        json_text1.replace("```json", "")
                                        .replace("```", "")
                                        .strip()
                                    )
                                    clean1 = self._fix_json_format(clean1)
                                    try:
                                        action_input = json.loads(clean1)
                                        found_input = True
                                        break
                                    except json.JSONDecodeError:
                                        pass

                                if found_input:
                                    break

                                # 方式2:  with  json.dumps 安全转义（终极兜底）
                                # 提取 command 原始值，json.dumps 自动处理所有特殊字符
                                # （换 lines、双引号、反斜杠、\b \t \r 等转义序列）
                                full_raw = "\n".join(collected_lines)
                                cmd_match = re.match(
                                    r'\s*\{\s*"(command|cmd|shell|script|exec)"\s*:\s*"',
                                    full_raw,
                                )
                                if cmd_match:
                                    key_name = cmd_match.group(1)
                                    raw_value = full_raw[cmd_match.end():]
                                    raw_value = re.sub(r'"\s*\}?\s*$', '', raw_value)
                                    safe_value = json.dumps(raw_value)
                                    for kn in [key_name, "command"]:
                                        safe_json = '{"' + kn + '": ' + safe_value + '}'
                                        try:
                                            action_input = json.loads(safe_json)
                                            found_input = True
                                            break
                                        except json.JSONDecodeError:
                                            continue
                                    if found_input:
                                        break

                                if found_input:
                                    break

                                # 多 lines收集仍失败，提供详细错误信息
                                print(f"⚠️  Action Input JSON parse failed: multi-line JSON unresolvable | raw input: {input_text[:100]}...")
                                action_input = {
                                    "_error": "JSON format error: multi-line text cannot be parsed as valid JSON",
                                    "_raw": input_text[:500],
                                    "_suggestion": "Check JSON format: 1) Keys must use double quotes 2) String values must use double quotes 3) Use \\\\n to escape multi-line commands 4) Or use heredoc for multi-line commands",
                                }
                                found_input = True
                                break
                        else:
                            # 非JSON格式，尝试智能解析
                            action_input = self._parse_non_json_input(input_text)
                            found_input = True
                            break

                # 添加action（即使没有Found input也添加空字典）
                actions.append(
                    ActionItem(
                        action=action_name,
                        action_input=action_input if found_input else {},
                    )
                )

            i += 1

        # 如果没有解析到thought，使 with 响应的前200字符
        if not thought:
            thought = response[:500] + ("..." if len(response) > 200 else "")

        return thought, actions

    def _fix_json_format(self, json_str: str) -> str:
        """尝试修复常见的JSON格式问题"""
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)
        # 修复 JSON 结构字符前出现的转义换 lines（多 lines收集时可能产生）
        json_str = re.sub(r'\\n(\s*[}\]",:\]])', r"\1", json_str)
        return json_str

    def _parse_non_json_input(self, input_text: str) -> Dict:
        """解析非JSON格式的输入"""
        # 尝试解析key=value格式
        if "=" in input_text:
            result = {}
            pairs = input_text.split(",")
            for pair in pairs:
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    result[key.strip()] = value.strip().strip("\"'")
            if result:
                return result

        # 否则作为单个字符串值
        return {"input": input_text}

    def _format_observation_for_display(self, action: str, result: Any) -> str:
        """
        格式化observation  for显示给 user（简化版本）
        Agent内部仍然Get 完整结果
        """
        # 特殊处理：fetch_url 结果摘要而非原始 HTML
        if action == "fetch_url" and isinstance(result, dict) and result.get("success"):
            url = result.get("url", "")
            content_length = result.get("content_length", 0)
            raw_length = result.get("raw_length", 0)
            content_warning = result.get("content_warning")
            content = result.get("content", "")

            lines = []
            lines.append(f"🌐 {url}")
            if raw_length:
                lines.append(f"Raw HTML: {raw_length} bytes, Cleaned text: {content_length} chars")
            else:
                lines.append(f"Content: {content_length} chars")

            if content_warning:
                lines.append(content_warning)

            # 显示清洗后的文本前 500 字符作为预览
            if content:
                preview = content[:500]
                if len(content) > 500:
                    preview += f"\n... (total {content_length} chars)"
                lines.append(f"\n── Preview ──\n{preview}")

            lines.append("\n💡 Use run_shell to read the saved extract file for full content.")
            return "\n".join(lines)

        # 其他Action：统一预览截断（仅影响终端显示，不影响 Agent 看到的内容）
        result_str = str(result)
        display_max = settings.output.display_preview_chars
        if len(result_str) > display_max:
            preview = result_str[:display_max]
            return f"{preview}...\n\n(Display truncated, {len(result_str)} chars total. Agent received full content)"
        return result_str

    def _detect_stale_loop(self, actions: List[ActionItem]) -> Optional[str]:
        """Detect when the model is stuck fetching unreadable content from the
        same domain repeatedly.

        Only tracks fetch_url calls. Rule: if the last 3 fetches to domain X
        all returned no readable content (e.g. JS-only pages, redirect walls,
        CSS garbage), warn the model to switch to search_web.

        We intentionally do NOT track consecutive calls to other tools.
        run_shell is the universal tool used for most operations (reading files,
        running tests, git, etc.) and consecutive calls are normal workflow.

        Returns a warning string to inject as [SYSTEM WARNING], or None.
        """
        for action_item in actions:
            if action_item.action != "fetch_url":
                continue

            domain_tracker = self._stale_tracker.get("fetch_url_by_domain", {})
            for domain, entries in domain_tracker.items():
                if len(entries) < 3:
                    continue
                # Check if the 3 most recent fetches all returned no content
                last_three = entries[-3:]
                checks = [not r.get("has_content", True) for r in last_three]
                if all(checks):
                    warn_key = f"fetch_url_stale_{domain}"
                    if warn_key not in self._stale_warnings_issued:
                        self._stale_warnings_issued.add(warn_key)
                        return (
                            f"Last {len(entries)} fetch_url calls to '{domain}' returned unreadable content"
                            " (page may be dynamically rendered or content was stripped)."
                            " Try search_web for alternative sources, or proceed based on existing knowledge."
                        )

        return None

    def _record_fetch_url_result(self, url: str, observation: Any):
        """Record fetch_url result for stale-loop detection.

        Called after every fetch_url action completes. Strips HTML tags from
        the observation and checks if at least 200 chars of readable text remain.
        Entries are capped at 5 per domain (FIFO) to bound memory.

        Performance: urlparse is O(1); the regex strip is O(n) on the observation
        text which is already bounded by the tool's content length limit.
        """
        from urllib.parse import urlparse

        try:
            domain = urlparse(url).netloc
        except Exception:
            domain = url

        domain_tracker = self._stale_tracker["fetch_url_by_domain"]
        if domain not in domain_tracker:
            domain_tracker[domain] = []

        obs_str = str(observation)
        text_only = re.sub(r'<[^>]+>', ' ', obs_str)
        text_only = re.sub(r'\s+', ' ', text_only).strip()
        has_content = len(text_only) >= 200

        domain_tracker[domain].append({
            "url": url,
            "has_content": has_content,
        })

        # Keep only last 5 entries per domain to bound memory
        if len(domain_tracker[domain]) > 5:
            domain_tracker[domain] = domain_tracker[domain][-5:]

    async def _execute_action_internal(self, action: str, action_input: Dict) -> str:
        """executeAction（内部方法，返回完整结果）"""
        registry = get_global_registry()

        if action not in self.tools:
            # 使 with 工具注册表提供友好的错误消息
            return registry.format_tool_not_found_error(action)

        try:
            # 验证输入参数
            if action_input is None:
                action_input = {}

            if not isinstance(action_input, dict):
                return f'Error: Action input must be a dict, current type: {type(action_input)}\nHint: Please use {{"key": "value"}} format'

            # 检查是否包含JSON解析错误
            if "_error" in action_input:
                error_detail = action_input["_error"]
                raw_input = action_input.get("_raw", "N/A")
                suggestion = action_input.get("_suggestion", "Check JSON format")
                return f"❌ Parameter parsing error\n\nError: {error_detail}\nRaw input: {raw_input}\n\n💡 {suggestion}"

            # 使 with 工具注册表验证参数
            validation_result = registry.validate_call(action, action_input)
            if not validation_result.valid:
                # 返回详细的验证错误消息
                error_msg = f"❌ Parameter validation failed\n\n{validation_result.error_message}\n\n"
                # 添加工具文档引 with 
                doc = registry.get_documentation(action)
                if doc:
                    error_msg += f"📖 Tool docs:\n{doc[:500]}..."
                return error_msg

            # 规范化参数（将别名转换为标准名称）
            schema = registry.get_schema(action)
            if schema:
                action_input = schema.normalize_params(action_input)

            # 异步execute工具（增加timeout保护 + 心跳）
            async def _heartbeat(act, start, timeout):
                deadline = start + timeout
                while True:
                    remaining = max(0, deadline - time.time())
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(3, remaining))
                    elapsed = int(time.time() - start)
                    print(f"⏳ {act} running... ({elapsed}s / {timeout}s timeout)", flush=True)

            hb_task: asyncio.Task | None = None
            action_start = time.time()
            # run_shell 自己管超时，框架不做二次兜底
            timeout_cfg = getattr(settings, "timeout", None)
            tool_timeout = timeout_cfg.tool_default if timeout_cfg and action != "run_shell" else None
            hb_task = asyncio.create_task(_heartbeat(action, action_start, tool_timeout or 600))
            try:
                coro = (
                    self.tools[action](**action_input)
                    if asyncio.iscoroutinefunction(self.tools[action])
                    else asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.tools[action](**action_input)
                    )
                )
                if tool_timeout:
                    result = await asyncio.wait_for(coro, timeout=tool_timeout)
                else:
                    result = await coro
            except asyncio.TimeoutError:
                return f"❌ Tool execution timeout after {tool_timeout}s: {action}"
            except asyncio.CancelledError:
                raise
            finally:
                if hb_task:
                    hb_task.cancel()
                    try:
                        await hb_task
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass

            # 处理结果（增强None检查）
            if result is None:
                return "✅ Execution successful (no return value)"

            # 处理字典结果（增强错误检测）
            if isinstance(result, dict):
                if result.get("error"):  # 只在有实际错误内容时才报错
                    error_msg = result["error"]
                    # 提供更友好的错误提示
                    if "permission" in error_msg.lower():
                        return f"🔒 Permission Error\n\n{error_msg}\n\n💡 Tips:\n- Check file/directory permissions\n- May need to modify permissions or use another path\n- Use run_shell to execute chmod commands"
                    elif "not found" in error_msg.lower():
                        return f"🔍 Not Found Error\n\n{error_msg}\n\n💡 Tips:\n- Check if file/directory exists\n- Verify the path is correct\n- Use run_shell + find/ls to view available files"
                    elif "timeout" in error_msg.lower():
                        return f"⏱️ Timeout Error\n\n{error_msg}\n\n💡 Tips:\n- Network request or operation timed out\n- Try retrying or check network connection\n- Consider increasing timeout"
                    else:
                        return f"❌ Error: {error_msg}"
                elif "success" in result and not result["success"]:
                    reason = result.get("message") or result.get("reason") or "Unknown reason"
                    return f"❌ Execution failed: {reason}"

            # 自适应截断：基于剩余上下文预算
            result_str = str(result)

            # run_shell 不经过框架截断（工具自己管 max_output）
            if action == "run_shell" and isinstance(result, dict):
                # 避免 command 重复：heredoc 等场景 command 包含文件内容，模型已在
                # tool_calls 中发送过，无需在 tool 消息中再次回传
                summary = dict(result)
                cmd = summary.pop("command", "")
                first_line = cmd.split('\n')[0][:200] if cmd else ''
                if len(cmd) > len(first_line) or len(cmd) > 200:
                    summary["command"] = first_line + ("..." if first_line and len(cmd) > len(first_line) else "")
                elif first_line:
                    summary["command"] = first_line
                summary.pop("working_directory", None)
                return json.dumps(summary, ensure_ascii=False)

            threshold_chars = getattr(self, "_adaptive_threshold_chars", None)
            if threshold_chars is None:
                return result_str

            preview_chars = max(
                500,
                min(threshold_chars, int(settings.output.max_preview_tokens * 4)),
            )

            if len(result_str) > threshold_chars:
                try:
                    output_file = await self.context_manager.save_large_output(
                        result_str, f"{action}_output.txt"
                    )
                    preview = result_str[:preview_chars]
                    return (
                        f"📄 Output too long ({len(result_str)} chars, "
                        f"~{len(result_str) // 4} tokens), "
                        f"saved to file: {output_file}\n\n"
                        f"💡 Use run_shell (cat) to view full content\n\n"
                        f"First {preview_chars} chars preview:\n{preview}..."
                    )
                except Exception as e:
                    return (
                        f"{result_str[:preview_chars]}...\n\n"
                        f"⚠️ (Output too long, truncated. Save failed: {str(e)})"
                    )

            return result_str

        except TypeError as e:
            # 参数错误（增强提示）
            error_str = str(e)
            error_msg = f"❌ Execution error: parameter mismatch\n\n{error_str}\n\n"

            # 尝试提取缺失或多余的参数信息
            if "missing" in error_str.lower():
                error_msg += "💡 Possible cause: missing required parameters\n"
            elif (
                "unexpected" in error_str.lower()
                or "got an unexpected" in error_str.lower()
            ):
                error_msg += "💡 Possible cause: non-existent parameter name used\n"
            elif "takes" in error_str.lower() and "positional" in error_str.lower():
                error_msg += "💡 Possible cause: parameter count mismatch\n"

            error_msg += f"\n📝 Your input:\n"
            error_msg += f"  Action: {action}\n"
            error_msg += f"  Parameters: {action_input}\n\n"

            # 添加工具文档（完整版）
            doc = registry.get_documentation(action)
            if doc:
                error_msg += f"📖 Correct tool documentation:\n{doc}\n"

            # 添加常见错误提示
            error_msg += "\n🔧 Common solutions:\n"
            error_msg += "  1. Check if parameter names are spelled correctly\n"
            error_msg += "  2. Ensure all required parameters are provided\n"
            error_msg += "  3. Verify parameter types are correct (string, number, etc.)\n"
            error_msg += "  4. Refer to the tool documentation and examples above\n"

            return error_msg
        except FileNotFoundError as e:
            return f"🔍 Execution error: file not found\n\n{str(e)}\n\n💡 Tips:\n- Check if file path is correct\n- Verify the file exists\n- Use run_shell + find/ls to view available files"
        except PermissionError as e:
            return f"🔒 Execution error: insufficient permissions\n\n{str(e)}\n\n💡 Tips:\n- May need to modify file permissions\n- Use run_shell to execute chmod command\n- Or choose a directory with proper access"
        except ConnectionError as e:
            return f"🌐 Execution error: network connection failed\n\n{str(e)}\n\n💡 Tips:\n- Check network connection\n- Retry later\n- Check firewall settings"
        except Exception as e:
            # 提供更详细的错误信息（增强诊断）
            import traceback

            error_trace = traceback.format_exc()
            error_type = type(e).__name__
            error_msg = str(e)

            # 特殊错误类型的友好提示
            friendly_tips = {
                "JSONDecodeError": "JSON format error, check the input JSON string format",
                "KeyError": "Missing required key, check the input parameters",
                "ValueError": "Value error, check if the input parameter value is valid",
                "ImportError": "Import error, possibly missing dependency package, use run_shell to install",
                "ModuleNotFoundError": "Module not found, use run_shell to install the dependency package",
                "AttributeError": "Attribute error, the object may not have this attribute or method",
                "IndexError": "Index error, list index out of range",
                "KeyboardInterrupt": "user interrupted operation",
            }

            tip = friendly_tips.get(error_type, "Check the error message and fix accordingly")

            return f"❌ Execution error: {error_type}\n\n{error_msg}\n\n💡 Tip: {tip}\n\n📋 Details:\n{error_trace[:300]}..."

    def _build_compact_view(self, messages: List[Dict]) -> tuple:
        """
        构建可传入模型的 round-aware 压缩视图。

        不修改原始 messages 列表，每次从全量消息中按 round 边界
        选出 system_prompt + 前N轮 + 摘要 + 后N轮，确保 tool_calls/tool_messages
        完整性。

        Returns:
            (view_messages, was_compacted, token_count): 压缩视图的消息列表, 是否压缩, token 数
        """
        protect_first = (
            self.context_config.compact_protect_first_rounds
            if self.context_config
            else 1
        )
        keep_last = (
            self.context_config.compact_keep_rounds
            if self.context_config
            else 10
        )
        max_tokens = (
            self.context_config.max_context_length
            if self.context_config
            else 131072
        )
        protect_last_user = (
            self.context_config.compact_protect_user_rounds
            if self.context_config
            else 2
        )
        return build_compact_view(
            encoding=self.encoding,
            messages=messages,
            max_tokens=max_tokens,
            protect_first_rounds=protect_first,
            keep_last_rounds=keep_last,
            cached_summary=self._compact_summary,
            protect_last_user_rounds=protect_last_user,
        )

    async def _compact_context(self, messages: List[Dict]):
        """上下文缩减 - 智能版：生成 AI 摘要并缓存，不修改全量 messages

        仅在最后 N 条用户消息之前的历史轮次中生成摘要，后 N 条用户消息及其之后的所有轮次不参与压缩。
        """
        print("📦 Executing smart context compaction...")

        history_file = await self.context_manager.save_history(self.steps)

        protect_first_rounds = (
            self.context_config.compact_protect_first_rounds
            if self.context_config
            else 1
        )
        keep_last_rounds = (
            self.context_config.compact_keep_rounds
            if self.context_config
            else 10
        )
        summary_steps = (
            self.context_config.compact_summary_steps if self.context_config else 10
        )
        protect_last_user_rounds = (
            self.context_config.compact_protect_user_rounds
            if self.context_config
            else 2
        )

        # 使用 round 感知拆分，确保不会切断 tool_calls/tool_messages 配对
        rounds = split_into_rounds(messages)

        # 找到从末尾数第 N 条真实用户消息所在轮，仅在此之前的历史中生成摘要
        latest_user_idx = _find_last_n_real_user_round(rounds, protect_last_user_rounds)

        if latest_user_idx is not None:
            pre_user_rounds = rounds[:latest_user_idx]
            if len(pre_user_rounds) <= protect_first_rounds:
                print("✅ Pre-user rounds within threshold, no compaction needed")
                return
            middle_rounds = pre_user_rounds[protect_first_rounds:]
        else:
            if len(rounds) <= protect_first_rounds + keep_last_rounds:
                print("✅ Round count within threshold, no compaction needed")
                return
            middle_rounds = rounds[protect_first_rounds:-keep_last_rounds]

        middle_messages = [m for r in middle_rounds for m in r]

        if not middle_messages:
            print("✅ No intermediate messages to compact")
            return

        # 智能缩减文件内容：将大段文件内容保存到 .aacode
        middle_messages = await self._compact_file_contents(middle_messages)

        # 使用模型生成三块智能摘要
        try:
            summaries = await self._generate_three_part_summary(
                middle_messages, self.steps[-summary_steps:]
            )
        except Exception as e:
            print(t("context.smart_summary_fail", e=str(e)))
            summary = await self._generate_summary(self.steps[-summary_steps:])
            summaries = {
                "file_content_summary": "",
                "tool_execution_summary": summary,
                "keep_original_summary": "",
            }

        # 构建并缓存摘要内容（供后续 _build_compact_view 使用）
        compact_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._compact_summary = f"""## 🧠 Smart History Summary (AI Generated)

**⏰ Compaction Time**: {compact_time}

### 📁 File Content Summary
{summaries["file_content_summary"] or "No file read operations"}

### 🔧 Tool Execution Summary
{summaries["tool_execution_summary"] or "No tool execution"}

### 💡 Important Information (Kept Original)
{summaries["keep_original_summary"] or "No special information to retain"}

**Full History**: {history_file}

**Important Notes**: 
- The above summary was generated by AI analysis, categorically retaining key information
- File contents have been archived and can be re-read via the archive path
- To view the full history, use run_shell (cat) to read the above file
- Continue executing the current task, referencing recent observations
- Avoid duplicating already completed work"""

        self._compact_summary_msg_count = len(messages)

        # 验证：使用缓存摘要构建压缩视图，确认 tool_calls 完整性
        view, _, new_tokens = self._build_compact_view(messages)
        old_tokens = self._estimate_tokens(messages)
        self._post_compact_tokens = new_tokens  # 记录压缩后基准值

        trigger_tokens = (
            self.context_config.compact_trigger_tokens
            if self.context_config
            else 8000
        )
        context_max = (
            self.context_config.max_context_length
            if self.context_config
            else 131072
        )
        threshold = min(trigger_tokens, context_max)

        status = "✅" if new_tokens <= threshold else "⚠️"
        print(f"{status} Smart context compaction done: full messages kept intact ({len(messages)} messages) | Summary cached for compact view | Token: {old_tokens} → {new_tokens} (compact view: {(old_tokens - new_tokens) / max(old_tokens, 1) * 100:.1f}% reduction) | " + (f"Below trigger ({threshold})" if new_tokens <= threshold else f"Still above trigger ({threshold}), protected last {protect_last_user_rounds} user rounds may be large") + f" | Protected first {protect_first_rounds} pre-user rounds | Summarized {len(middle_rounds)} history rounds before latest user message")

    async def _compact_file_contents(self, messages: List[Dict]) -> List[Dict]:
        """
        智能缩减内容：将大段内容Save 到.aacode，只保留 summarized 和路径

        处理的内容类型：
        1. run_shell 的大段文件内容输出
        2. run_shell 的长输出

        Args:
            messages: 消息列表

        Returns:
            缩减后的消息列表
        """
        compacted = []

        for msg in messages:
            content = msg.get("content", "")

            # 跳过已经归档的内容（避免重复处理）
            if "[Archived]" in content or "Archive path:" in content:
                compacted.append(msg)
                continue

            # 检查是否包含大段内容（超过500字符）
            if len(content) > 500:
                import re

                new_content = content
                content_modified = False

                # 策略1：匹配代码块（```...```）超过500字符的
                code_blocks = list(
                    re.finditer(r"```[\s\S]{500,}?```", new_content, re.DOTALL)
                )

                for match in code_blocks:
                    content_block = match.group(0)

                    # 判断内容类型
                    content_type = self._detect_content_type(content, content_block)
                    identifier = self._extract_identifier(content, content_type)

                    # Save 到.aacode/context/
                    try:
                        saved_path = await self.context_manager.save_large_output(
                            content_block,
                            f"{content_type}_{identifier}_{asyncio.get_event_loop().time():.0f}.txt",
                        )

                        # 生成智能 summarized 
                        summary = self._generate_content_summary(
                            content_block, content_type
                        )

                        # 替换为简短引 with （包含 summarized 、路径和哈希）
                        # 从路径中提取哈希值
                        import re

                        hash_match = re.search(r"_([a-f0-9]{8})\.txt$", saved_path)
                        hash_info = f"Hash: {hash_match.group(1)}" if hash_match else ""

                        if content_type == "file_content":
                            replacement = f"""[{self._get_content_type_name(content_type)} Archived]
Original file: {identifier}
Archive path: {saved_path}
Size: {len(content_block)} chars
{hash_info}
Summary: {summary}
💡 To view full content, use run_shell to read the archive file: {saved_path}"""
                        else:
                            replacement = f"""[{self._get_content_type_name(content_type)} Archived]
Identifier: {identifier}
Archive path: {saved_path}
Size: {len(content_block)} chars
{hash_info}
Summary: {summary}
💡 To view full content, use run_shell to read the archive file: {saved_path}"""

                        new_content = new_content.replace(content_block, replacement)
                        content_modified = True

                    except Exception as e:
                        print(f"⚠️  Save {content_type} content failed: {e}")

                # 策略2：如果没有代码块，但内容很长（>1500字符），检查是否有大段文本
                if not content_modified and len(content) > 1500:
                    # 检查是否有搜索结果、文件列表等
                    if "match" in content.lower() or "search" in content.lower():
                        content_type = "search_results"
                        identifier = self._extract_identifier(content, content_type)

                        try:
                            saved_path = await self.context_manager.save_large_output(
                                content,
                                f"{content_type}_{identifier}_{asyncio.get_event_loop().time():.0f}.txt",
                            )

                            summary = self._generate_content_summary(
                                content, content_type
                            )

                            if content_type == "file_content":
                                new_content = f"""[{self._get_content_type_name(content_type)} Archived]
Original file: {identifier}
Archive path: {saved_path}
Size: {len(content)} chars
Summary: {summary}
💡 To view full content, use run_shell (cat) to read the archive file, or search for files yourself"""
                            else:
                                new_content = f"""[{self._get_content_type_name(content_type)} Archived]
Identifier: {identifier}
Archive path: {saved_path}
Size: {len(content)} chars
Summary: {summary}
💡 To view full content, use run_shell (cat) to read the archive file, or search for files yourself"""

                            content_modified = True

                        except Exception as e:
                            print(f"⚠️  Save {content_type} content failed: {e}")

                # 如果内容被修改，更新消息
                if content_modified:
                    msg = msg.copy()
                    msg["content"] = new_content

            compacted.append(msg)

        return compacted

    def _detect_content_type(self, full_content: str, content_block: str) -> str:
        """检测内容类型"""
        full_lower = full_content.lower()

        # 检查上下文关键词
        if any(
            kw in full_lower
            for kw in ["file content"]
        ):
            return "file_content"
        elif any(
            kw in full_lower
            for kw in ["Executing command", "run_shell", "command output", "stdout"]
        ):
            return "shell_output"
        elif any(
            kw in full_lower             for kw in ["code output"]
        ):
            return "code_output"
        else:
            # 默认类型
            return "content"

    def _extract_identifier(self, full_content: str, content_type: str) -> str:
        """提取内容的标识符（文件名、命令等）"""
        import re

        if content_type == "file_content":
            # 策略1: 从观察内容开头提取文件路径
            # format: "```python\n# path/to/file.py\n..."
            match = re.search(
                r"```[a-z]*\s*\n\s*#\s*([^\n]+\.[\w]+)", full_content, re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

            # 策略2: 查找明确的文件路径标记
            match = re.search(
                r"file path[:\s]+([^\n\s]+\.[\w]+)",
                full_content,
                re.IGNORECASE,
            )
            if match:
                return match.group(1).strip()

            # 策略3: 查找任何看起来像文件路径的内容（包含扩展名）
            match = re.search(
                r"([a-zA-Z0-9_/\-\.]+\.(?:py|js|ts|md|txt|json|yaml|yml|csv|html|css))",
                full_content,
                re.IGNORECASE,
            )
            if match:
                return match.group(1).strip()

            return "unknown_file"

        elif content_type == "shell_output":
            # 提取命令
            match = re.search(
                r"(?:command)[:\s]+([^\n]+)", full_content, re.IGNORECASE
            )
            if match:
                cmd = match.group(1).strip()
                # 只保留命令的前30个字符，清理特殊字符
                cmd = (
                    cmd[:30]
                    .replace(" ", "_")
                    .replace("/", "_")
                    .replace("|", "_")
                    .replace(">", "_")
                )
                return cmd
            return "unknown_cmd"

        elif content_type == "search_results":
            # 提取搜索查询
            match = re.search(
                r"(?:search|query)[:\s]+([^\n]+)", full_content, re.IGNORECASE
            )
            if match:
                query = (
                    match.group(1)
                    .strip()[:30]
                    .replace(" ", "_")
                    .replace('"', "")
                    .replace("'", "")
                )
                return query
            return "unknown_search"

        elif content_type == "file_list":
            return "file_list"

        elif content_type == "code_output":
            return "code_output"

        else:
            return "content"

    def _generate_content_summary(self, content_block: str, content_type: str) -> str:
        """生成内容的智能 summarized """
        # 提取前200字符作为预览
        preview = content_block[:200].replace("\n", " ").strip()
        if len(content_block) > 200:
            preview += "..."

        # 根据内容类型添加额外信息
        if content_type == "shell_output":
            # 检查是否有错误
            if "error" in content_block.lower() or "failed" in content_block.lower():
                preview = "⚠️ Contains error info | " + preview
            elif (
                "success" in content_block.lower() or "passed" in content_block.lower()
            ):
                preview = "✅ Execution successful | " + preview

        elif content_type == "search_results":
            # 统计匹配数
            import re

            matches = len(re.findall(r"\n", content_block[:1000]))
            preview = f"~{matches} matches | " + preview

        elif content_type == "file_list":
            # 统计文件数
            import re

            files = len(re.findall(r"\n", content_block[:1000]))
            preview = f"~{files} files | " + preview

        return preview

    def _get_content_type_name(self, content_type: str) -> str:
        """Get friendly name for content type"""
        names = {
            "file_content": "File Content",
            "shell_output": "Shell Output",
            "search_results": "Search Results",
            "file_list": "File List",
            "code_output": "Code Output",
            "content": "Content",
        }
        return names.get(content_type, "Content")

    async def _generate_intelligent_summary(
        self, middle_messages: List[Dict], recent_steps: List[ReActStep]
    ) -> str:
        """Use model to generate intelligent summary"""
        # 构建 summarized 请求
        summary_prompt = f"""Please analyze the following conversation history and execution steps, and generate a concise but comprehensive summary.

**Summary Requirements**:
1. Retain all key decisions and important discoveries
2. Record completed main tasks and subtasks
3. Note important errors encountered and solutions
4. Retain important file paths and configuration information
5. Remove redundant and duplicate information
6. Use structured format (headings, lists)
7. Keep within 500-800 characters

**Tool Content Offloading Principles** (Important!):
For tool outputs that have completed their purpose, they should be appropriately condensed, but archive paths must be retained:

1. **Archived Content**:
   - If you see "[xxx Archived]" markers, the full content has been saved
   - Archive paths must be retained in the summary, format: `Archive: .aacode/context/xxx.txt`
   - The summary can be further condensed, but archive paths cannot be deleted

2. **File Reading Content** (via run_shell cat/head/tail):
   - If the file content has already been used (e.g., code has been written based on it, configuration has been understood)
   - Summary: Retain key info + archive path
   - Example: `Read config.py, understood database config | Archive: .aacode/context/file_content_xxx.txt`

3. **run_shell Output**:
- If the command output has already been processed (e.g., packages installed based on version info)
   - Summary: Retain results + archive path
   - Example: `Ran pytest, 15 passed | Archive: .aacode/context/shell_output_xxx.txt`

 4. **run_shell Output** (using shell commands like grep/find instead of search):
    - If search results have already been used (e.g., target file found and modified)
    - Summary: Only keep "Ran xxx command, found N matches, located xxx file"

**Key Principles**:
- ✅ Must retain: Archive paths (.aacode/context/xxx.txt)
- ✅ Must retain: Key decisions and discoveries
- ✅ Can condense: Detailed output content
- ❌ Cannot delete: Archive path references
- ❌ Cannot delete: Unresolved error information
   - Summary: Only keep "Read xxx file, understood yyy", do not retain full content
   - Exception: If may be needed for reference later, retain key parts

2. **run_shell Output**:
- If the command output has already been processed (e.g., packages installed based on version info, bugs fixed based on test results)
   - Summary: Only keep "Ran xxx command, result was yyy", do not retain full output
   - Exception: If it's an error message and unresolved, retain detailed information

 **Criteria for Offloading**:
- ✅ Can offload: Tool output has achieved its purpose (understanding, verification, locating, etc.)
- ✅ Can offload: Subsequent steps did not reference this content again
- ❌ Cannot offload: Content contains unresolved errors
- ❌ Cannot offload: Content is the core reference material for the current task
- ❌ Cannot offload: Subsequent steps may need to view it again

**Summary Examples**:

Bad summary (retained too much already-used content):
```
Step 1: Read config.py file
Content: [Complete 500-line config file content]
Step 2: Modified database connection based on config file
```

Good summary (properly offloaded):
```
Step 1: Read config.py, understood database config (host=localhost, port=5432)
Step 2: Modified database connection based on config, tests passed
[config.py full content archived, use run_shell (cat) if needed]
```

**Conversation History** ({len(middle_messages)} messages):
"""

        # 添加中间消息的简要内容
        for i, msg in enumerate(middle_messages[:20]):  # 最多20条
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # 每条最多200字符
            summary_prompt += f"\n[{role}] {content}..."

        if len(middle_messages) > 20:
            summary_prompt += f"\n... {len(middle_messages) - 20} more messages"

        # 添加execute步骤
        summary_prompt += f"\n\n**Execution Steps** (last {len(recent_steps)} steps):\n"
        for i, step in enumerate(recent_steps):
            summary_prompt += f"\nStep {i + 1}: {step.thought[:150]}..."
            if step.actions:
                summary_prompt += (
                    f"\n  Action: {', '.join([a.action for a in step.actions])}"
                )

        summary_prompt += (
            "\n\nPlease generate a summary (500-800 chars), properly offloading tool content that has completed its purpose:"
        )

        # 调 with 模型生成 summarized 
        try:
            summary_messages = [{"role": "user", "content": summary_prompt}]
            summary_response = await asyncio.wait_for(
                self.model_caller(summary_messages),
                timeout=30.0,  # 30秒timeout
            )

            # 清理 summarized （移除可能的markdown格式）
            summary_text = summary_response.get("text", summary_response) if isinstance(summary_response, dict) else summary_response
            summary = summary_text.strip()
            if summary.startswith("```"):
                summary = "\n".join(summary.split("\n")[1:-1])

            # 限制长度
            if len(summary) > 1000:
                summary = summary[:1000] + "..."

            return summary
        except asyncio.TimeoutError:
            return "Summary generation timed out, please check full history"
        except Exception as e:
            return f"Summary generation failed: {str(e)}"

    async def _generate_three_part_summary(
        self, middle_messages: List[Dict], recent_steps: List[ReActStep]
    ) -> Dict[str, str]:
        """Use model to generate three-part classified summary"""
        summary_prompt = f"""Please analyze the following conversation history and generate a three-part classified summary.

**Conversation History** ({len(middle_messages)} messages):
"""

        # 添加中间消息的简要内容
        for i, msg in enumerate(middle_messages[:30]):  # 最多30条
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:300]  # 每条最多300字符
            summary_prompt += f"\n[{role}] {content}..."

        if len(middle_messages) > 30:
            summary_prompt += f"\n... {len(middle_messages) - 30} more messages"

        summary_prompt += f"""

**Requirements**: Generate a three-part summary, return JSON format:

{{
  "file_content_summary": "File content summary (200-300 words)",
  "tool_execution_summary": "Tool execution summary (200-300 words)",
  "keep_original_summary": "Important information to retain as-is (100-200 words)"
}}

**Section Descriptions**:

1. **file_content_summary**:
   - Summarize all file reading operations (run_shell cat/head/tail etc.)
   - Format: `Read config.py (database config), main.py (main program) | Archive: .aacode/context/xxx.txt`
   - Must retain archive paths
   - If no file reads, return empty string

2. **tool_execution_summary**:
   - Summarize run_shell and other tool executions
   - Format: `Ran 3 tests (2 passed), several file operations | Archive: .aacode/context/xxx.txt`
   - Retain key results and archive paths
   - If no tool executions, return empty string

3. **keep_original_summary**:
   - Include unresolved errors
   - Include key decisions and architecture choices
   - Include important technical dependencies and parameters
   - Include key tool execution results
   - If nothing special to retain, return empty string

**Key Principles**:
- ✅ Must retain all archive paths (.aacode/context/xxx.txt)
- ✅ Archived content only keeps summary + path, not detailed content
- ✅ Unresolved errors must be in keep_original_summary
- ❌ Do not duplicate information
- ❌ Do not retain detailed output of completed tasks

Please return the three-part summary in JSON format:"""

        # 调 with 模型生成 summarized 
        try:
            summary_messages = [{"role": "user", "content": summary_prompt}]
            summary_response = await asyncio.wait_for(
                self.model_caller(summary_messages),
                timeout=60.0,  # 60秒timeout
            )

            # 解析JSON响应
            summary_text2 = summary_response.get("text", summary_response) if isinstance(summary_response, dict) else summary_response
            summaries = self._extract_json_from_response(summary_text2)

            if summaries and isinstance(summaries, dict):
                return {
                    "file_content_summary": summaries.get("file_content_summary", ""),
                    "tool_execution_summary": summaries.get(
                        "tool_execution_summary", ""
                    ),
                    "keep_original_summary": summaries.get("keep_original_summary", ""),
                }
            else:
                # 如果无法解析JSON，返回默认值
                return {
                    "file_content_summary": "",
                    "tool_execution_summary": summary_response[:500],
                    "keep_original_summary": "",
                }
        except asyncio.TimeoutError:
            return {
                "file_content_summary": "",
                "tool_execution_summary": "Summary generation timed out",
            }
        except Exception as e:
            return {
                "file_content_summary": "",
                "tool_execution_summary": f"Summary generation failed: {str(e)}",
                "keep_original_summary": "",
            }

    def _extract_json_from_response(self, response: str) -> Optional[Dict]:
        """从模型响应中提取JSON（复 with 健壮的解析逻辑）"""
        import json
        import re

        # 使 with 与 _parse_response 相同的JSON解析模式
        json_patterns = [
            r"```json\s*\n(.*?)\n```",  # 标准json代码块
            r"```JSON\s*\n(.*?)\n```",  # 大写JSON
            r"```\s*\n(\{.*?\})\s*\n```",  # 普通代码块包裹的JSON
            r"(\{[\s\S]*?\})",  # 直接的JSON对象
            r"```json\s*\n(.*?)(?:\n```|$)",  # 不严格的结束标记
        ]

        for pattern in json_patterns:
            json_match = re.search(pattern, response, re.DOTALL)
            if json_match:
                json_str = None
                try:
                    json_str = json_match.group(1).strip()
                    # 清理可能的markdown残留
                    json_str = (
                        json_str.replace("```json", "")
                        .replace("```JSON", "")
                        .replace("```", "")
                        .strip()
                    )

                    # 尝试修复常见的JSON格式问题
                    json_str = self._fix_json_format(json_str)

                    data = json.loads(json_str)
                    return data
                except json.JSONDecodeError:
                    # 记录但继续尝试其他模式
                    continue
                except Exception:
                    continue

        return None

    async def _update_todo_from_thought(self, thought: str, todo_manager) -> None:
        """从思考中自动更新待办清单（已废弃，不再自动记录思考过程）"""
        pass

    async def _update_todo_from_error(self, observation, todo_manager, session_id: Optional[str] = None) -> None:
        """从错误观察中自动添加修复任务到待办清单 - 优化版：更精确的错误检测"""
        try:
            if not todo_manager:
                return

            # 1. 处理字典格式的observation
            if isinstance(observation, dict):
                # 特殊处理：run_shell 的返回
                # run_shell 总是返回 success=True（工具execute成功）
                # 需要检查 returncode 来判断命令是否成功
                if "returncode" in observation:
                    returncode = observation.get("returncode", 0)
                    if returncode == 0:
                        # 命令execute成功，不是错误
                        return
                    # returncode != 0，继续检查是否需要添加Todo item
                    # 但不是所有非零退出码都需要添加Todo item
                    # 例如：grep 没Found 匹配（退出码1）是正常的
                    stderr = observation.get("stderr", "")
                    if stderr and any(
                        err in stderr.lower()
                        for err in ["error", "exception", "traceback", "failed"]
                    ):
                        # stderr 中有明确的错误信息，才添加Todo item
                        pass
                    else:
                        # 只是非零退出码，但没有明确错误，不添加Todo item
                        return

                # 如果明确标记为成功，直接返回
                if observation.get("success") is True and "error" not in observation:
                    return

                # 如果有 error 字段但 success=True，可能是timeout等情况
                if observation.get("success") is True and "error" in observation:
                    # 检查是否是timeout
                    if observation.get("timeout"):
                        # timeout可以添加Todo item
                        pass
                    else:
                        # 其他情况，提取 error 字段
                        pass

                # 如果没有error字段且success=True，不当作错误
                if "error" not in observation and observation.get("success") is True:
                    return

                # 提取error字段作为观察内容
                if "error" in observation:
                    observation = str(observation.get("error", ""))
                else:
                    observation = str(observation)

            # 2. 转换为字符串并检查
            obs_str = str(observation)
            obs_lower = obs_str.lower()

            # 3. 先检查成功标识（更严格）
            success_indicators = [
                "'success': true",
                '"success": true',
                "✅",
                "successfully",
                "completed",
                "passed",
            ]

            if any(indicator.lower() in obs_lower for indicator in success_indicators):
                return

            # 4. 排除误报情况
            false_positive_patterns = [
                "no error",
                "error: none",
                "error=false",
                "0 errors",
                "without error",
                "error handling",  # 讨论错误处理的文本
            ]

            if any(pattern in obs_lower for pattern in false_positive_patterns):
                return

            # 5. 检测真正的错误（更精确的标识）
            error_indicators = [
                # Python 异常
                "traceback (most recent call last)",
                "exception:",
                # 明确的错误标记
                "❌",
                "execution failed",
                "command failed",
                # 参数错误
                "Parameter validation failed",
                "parameter validation failed",
                # 权限错误
                "permission denied",
                "insufficient permission",
                # 工具execute异常
                "tool execution error",
            ]

            has_error = any(indicator in obs_lower for indicator in error_indicators)

            # 如果没有明确的错误标识，但包含"error"关键词，进一步检查
            if not has_error and "error" in obs_lower:
                # 检查是否是真正的错误消息格式
                import re

                # 匹配 "error: xxx" 格式
                if re.search(r"(error)[:\s]+\w+", obs_lower):
                    has_error = True

            if not has_error:
                return

            # 6. 提取更详细的错误信息
            error_type, error_detail = self._extract_error_info(obs_str)

            # 7. 只有在错误类型明确时才添加Todo item
            if error_type != "Unknown error":
                fix_task = f"{error_type}: {error_detail}"
                await todo_manager.add_todo_item(
                    item=fix_task, priority="high", category="Error Fix", session_id=session_id
                )

                # 不再打印"已自动添加Todo item"，因为 add_todo_item 已经打印了
                # 只在日志级别记录
                pass
            else:
                # 未知错误：不自动添加Todo item，避免噪音
                pass

        except Exception as e:
            # 静默失败，避免干扰主流程
            pass

    def _extract_error_info(self, observation: str) -> tuple:
        """提取错误类型和详细信息"""
        import re

        # 1. 尝试匹配 Python 异常
        exception_patterns = [
            (r"(ImportError|ModuleNotFoundError)[:\s]+(.+)", "ImportError"),
            (r"(SyntaxError)[:\s]+(.+)", "SyntaxError"),
            (r"(NameError)[:\s]+(.+)", "NameError"),
            (r"(TypeError)[:\s]+(.+)", "TypeError"),
            (r"(ValueError)[:\s]+(.+)", "ValueError"),
            (r"(AttributeError)[:\s]+(.+)", "AttributeError"),
            (r"(FileNotFoundError)[:\s]+(.+)", "FileNotFoundError"),
            (r"(PermissionError)[:\s]+(.+)", "PermissionError"),
        ]

        for pattern, error_name in exception_patterns:
            match = re.search(pattern, observation, re.IGNORECASE)
            if match:
                error_detail = match.group(2).strip()[:150]
                return error_name, error_detail

        # 2. 尝试匹配命令execute失败（改进：更精确的匹配）
        if "command failed" in observation.lower():
            # 提取退出码
            exitcode_match = re.search(r"exit code[:\s]+(\d+)", observation)
            if exitcode_match:
                exitcode = exitcode_match.group(1)
                # 提取 stderr 或错误消息
                stderr_match = re.search(
                    r"error output[:\s]+(.+)", observation, re.IGNORECASE | re.DOTALL
                )
                if stderr_match:
                    stderr_text = stderr_match.group(1).strip()[:150]
                    return "Command Execution Failed", f"Exit code {exitcode}: {stderr_text}"
                return "Command Execution Failed", f"Exit code {exitcode}"

            # 没有退出码信息，尝试提取错误输出
            stderr_match = re.search(
                r"error output[:\s]+(.+)", observation, re.IGNORECASE | re.DOTALL
            )
            if stderr_match:
                return "Command Execution Failed", stderr_match.group(1).strip()[:150]

            return "Command Execution Failed", "Command returned non-zero exit code"

        # 3. 检查 returncode 或 exit code
        if "returncode" in observation.lower() or "exit code" in observation.lower():
            stderr_match = re.search(
                r"stderr[:\s]+(.+)", observation, re.IGNORECASE | re.DOTALL
            )
            if stderr_match:
                return "Command Execution Failed", stderr_match.group(1).strip()[:150]
            return "Command Execution Failed", "Command returned non-zero exit code"

        # 4. 尝试匹配参数错误
        if (
            "Parameter validation failed" in observation
            or "parameter validation failed" in observation.lower()
        ):
            # 提取参数名
            param_match = re.search(r"parameter[:\s]+(\w+)", observation)
            if param_match:
                return "Parameter Error", f"Parameter {param_match.group(1)} validation failed"
            return "Parameter Error", observation[:150]

        # 5. 尝试匹配权限错误
        if "permission" in observation.lower():
            return "Permission Error", observation[:150]

        # 6. 尝试匹配文件不存在
        if "not found" in observation.lower():
            return "File Not Found", observation[:150]

        # 7. 未知错误
        return "Unknown Error", observation[:150]

    async def _generate_summary(self, recent_steps: List[ReActStep]) -> str:
        """生成步骤 summarized  - 优化：包含更多关键信息"""
        summary_parts = []
        for i, step in enumerate(recent_steps):
            # 保留更多思考内容（从100提高到200字符）
            thought_preview = step.thought[:200] + (
                "..." if len(step.thought) > 200 else ""
            )
            summary_parts.append(f"\n### Step {i + 1}")
            summary_parts.append(f"**Thought**: {thought_preview}")

            if step.actions:
                summary_parts.append(
                    f"**Action**: {', '.join([a.action for a in step.actions])}"
                )

                # 添加关键观察结果
                for j, action in enumerate(step.actions):
                    if action.observation:
                        # 保留观察结果的前150字符
                        obs_preview = action.observation[:150] + (
                            "..." if len(action.observation) > 150 else ""
                        )
                        summary_parts.append(f"  - {action.action}: {obs_preview}")

        return "\n".join(summary_parts)

    async def _validate_context_consistency(
        self,
        all_observations: List[str],
        all_observations_for_display: List[str],
        messages: List[Dict],
    ) -> None:
        """
        验证上下文一致性

        Args:
            all_observations: AgentGet 的完整观察结果
            all_observations_for_display:  user看到的简化观察结果
            messages: 当前消息列表
        """
        # 1. 检查观察结果数量一致性
        if len(all_observations) != len(all_observations_for_display):
            print(f"⚠️  Context consistency warning: observation count mismatch | Agent: {len(all_observations)}, User: {len(all_observations_for_display)}")

        # 2. 检查token使 with 情况
        current_tokens = self._estimate_tokens(messages)
        if current_tokens > 5000:  # 警告阈值
            # 显示消息分布（含 tool 角色）
            system_tokens = self._estimate_tokens(
                [msg for msg in messages if msg.get("role") == "system"]
            )
            user_tokens = self._estimate_tokens(
                [msg for msg in messages if msg.get("role") == "user"]
            )
            assistant_tokens = self._estimate_tokens(
                [msg for msg in messages if msg.get("role") == "assistant"]
            )
            tool_tokens = self._estimate_tokens(
                [msg for msg in messages if msg.get("role") == "tool"]
            )
            print(f"📊 Context monitor: ~{current_tokens} tokens |  System: {system_tokens} |  User: {user_tokens} | Assistant: {assistant_tokens} | Tool: {tool_tokens}")

        # 3. 检查归档路径是否保留（简化版本中）
        for i, obs_display in enumerate(all_observations_for_display):
            if ".aacode/context/" in obs_display:
                # 检查对应的完整观察是否也包含归档路径
                if (
                    i < len(all_observations)
                    and ".aacode/context/" in all_observations[i]
                ):
                    # 提取归档文件名
                    import re

                    archive_match = re.search(
                        r"\.aacode/context/([^\s]+\.txt)", obs_display
                    )
                    if archive_match:
                        archive_file = archive_match.group(1)
                        print(f"✅ Archive path match: action{i + 1}archived to  {archive_file}")
                else:
                    print(
                        f"⚠️  Archive path inconsistency: Action {i + 1} simplified version has archive path but full version may be missing"
                    )

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """估算消息列表的 token 数（含 tool_calls / tool_call_id / reasoning_content）"""
        return _util_estimate_tokens(self.encoding, messages)


# 测试
if __name__ == "__main__":
    pass
