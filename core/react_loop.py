# ReAct循环
# core/react_loop.py
"""
轻量化ReAct循环实现
支持异步工具调 with 和上下文管理
"""

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

    async def run(
        self,
        initial_prompt: str,
        task_description: str,
        todo_manager: Optional[Any] = None,
        history_messages: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        运 linesReAct循环

        Args:
            initial_prompt: 初始提示
            task_description: 任务描述
            todo_manager: to-do-list管理器
            history_messages: 同一会话的历史对话消息（  for多轮任务上下文衔接）

        Returns:
            execute结果
        """
        # 开始日志记录
        if self.logger:
            task_id = await self.logger.start_task(task_description)

        print(f"🚀 Starting ReAct loop, max {self.max_iterations} iterations")

        # 初始上下文
        self.current_context = await self.context_manager.get_context()

        # 构建初始消息，集成规划提示到系统prompt中
        todo_section = ""
        if todo_manager:
            try:
                todo_summary = await todo_manager.get_todo_summary()
                if "error" not in todo_summary:
                    todo_section = f"""

📋 Task Todo List
For simple tasks like just answering a user question, there's no need to create or update a todo list. Check relevant files and analyze quickly before answering.
For complex tasks, please use the todo task list:
- Todo files: {todo_summary.get("todo_file", "Unknown")}
- Total items: {todo_summary.get("total_todos", 0)} 
- Completed: {todo_summary.get("completed_todos", 0)}
- Pending: {todo_summary.get("pending_todos", 0)}
- Completion rate: {todo_summary.get("completion_rate", 0):.1f}%

Notes:
1. add_todo_item will return a todo_id (e.g., t1, t2), please remember it
2. When marking complete, prefer mark_todo_completed(todo_id="t1"), which is precise and reliable
3. If new task steps are needed, add new Todo items
4. If the task plan changes, update existing Todo items

Example:
add_todo_item(description="Implement authentication API") → returns todo_id: "t1"
mark_todo_completed(todo_id="t1") → precisely marked complete

"""
            except Exception as e:
                print(f"⚠️  Failed to get todo summarized: {e}")

        system_prompt = f"""{initial_prompt}{todo_section}
        
Important - Planning in Thought:
During each thought, naturally plan:
- For complex tasks (involving applications, systems, projects, architecture, etc.), analyze requirements, check the environment, and formulate a plan in the first few thoughts
- If the task contains keywords like "plan", "analyze", "check", "redesign", "strategy", "requirements", proactively plan in your thoughts
- Keep thinking natural, treating planning as part of the thought process, not a separate task

"""

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # ─── 多轮任务上下文衔接 ───────────────────────────────────
        # 同一会话中，第二轮及后续任务需要看到之前的对话历史
        # history_messages 来自 session_manager，包含之前所有轮次的 user/assistant 消息
        # 插入到 system prompt 之后、当前任务之前，让模型了解之前做了什么
        # ⚠️ 不要去掉这段逻辑，否则多轮任务间上下文会脱节
        # ⚠️ token 超限时会由 _compact_context 自动压缩，不需要在这里截断
        if history_messages:
            for msg in history_messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
            if len(history_messages) > 0:
                print(f"📜 Loaded {len(history_messages)}  history messages into context")

        messages.append(
            {
                "role": "user",
                "content": f"Task: {task_description}\n\nCurrent context:\n{self.current_context}\n\nPlease follow the Thought->Action format to execute (do not output Observation; the system will automatically execute tools and return results)",
            },
        )

        start_time = asyncio.get_event_loop().time()

        for iteration in range(self.max_iterations):
            iteration_start = asyncio.get_event_loop().time()
            print(f"\n🔄 Iteration {iteration + 1}/{self.max_iterations}")

            # 调 with 模型Get 思考
            model_start = asyncio.get_event_loop().time()
            response = await self.model_caller(messages)
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

            for i, action_item in enumerate(actions):
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

                # 🔥 新增：从错误中自动更新待办清单
                if todo_manager:
                    await self._update_todo_from_error(observation, todo_manager)

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
                for tc, observation_item in zip(native_tool_calls, all_observations):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": str(observation_item),
                    })
            else:
                # ─── 文本解析消息格式（保持不变） ───
                messages.append({"role": "assistant", "content": response_text})
                messages.append(
                    {
                        "role": "user",
                        "content": f"[System] Tool execution result below. Please continue to the next step (Thought→Action) based on the result. If the task is completed, output the final summary directly.\n\nObservation: {observation}",
                    }
                )

            # 上下文一致性检查（在 messages 更新后，确保 assistant token 统计正确）

            # 检查是否有 finalize_task：消息已记录到会话历史，现在可以安全返回
            finalize_action = next((a for a in actions if a.action == "finalize_task"), None)
            if finalize_action:
                summary_text = finalize_action.action_input.get("summary", "Task completed") if finalize_action.action_input else "Task completed"
                print(t("agent.task_done_summary", summary=summary_text))
                total_time = asyncio.get_event_loop().time() - start_time
                if self.logger:
                    await self.logger.finish_task(
                        final_status="completed",
                        total_iterations=iteration + 1,
                        total_time=total_time,
                        summary={"summary": summary_text},
                    )
                self.last_messages = messages
                return {
                    "status": "completed",
                    "final_thought": summary_text,
                    "iterations": iteration + 1,
                    "steps": self.steps,
                    "total_time": total_time,
                }

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

            # 更新上下文（使 with 完整observation）
            await self.context_manager.update(observation)
            self.current_context = await self.context_manager.get_compact_context()

            # 智能上下文缩减检查（基于token数）
            current_tokens = self._estimate_tokens(messages)
            trigger_tokens = (
                self.context_config.compact_trigger_tokens
                if self.context_config
                else 8000
            )

            if current_tokens > trigger_tokens:
                print(f"📊 Current tokens: {current_tokens}, trigger threshold: {trigger_tokens}")
                await self._compact_context(messages)
                if self.logger:
                    await self.logger.log_context_update(
                        update_type="compact",
                        content=f"Context compaction executed after iteration {iteration + 1} (tokens: {current_tokens})",
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
        # 特殊处理：read_file显示可折叠预览
        if action == "read_file" and isinstance(result, dict) and result.get("success"):
            path = result.get("path", "unknown")
            lines = result.get("lines", 0)
            size = result.get("size", 0)
            content = result.get("content", "")

            # 显示前20 lines作为预览
            preview_lines = content.split("\n")[:20]
            preview = "\n".join(preview_lines)

            if len(content.split("\n")) > 20:
                return f"📄 {path} ({lines} lines, {size} chars)\n```\n{preview}\n...\n```\n📋 Showing first 20 lines, full content saved ({len(content.split('\n'))} lines total)"
            else:
                return f"📄 {path} ({lines} lines, {size} chars)\n```\n{preview}\n```"

        # 其他Action返回完整结果（可能被截断）
        result_str = str(result)

        # 判断内容类型
        is_code_content = any(
            indicator in result_str[:200]
            for indicator in [
                "def ",
                "class ",
                "import ",
                "from ",
                "#!/",  # Python
                "function ",
                "const ",
                "let ",
                "var ",  # JavaScript
                "public ",
                "private ",
                "protected ",  # Java/C++
                "<?php",
                "namespace ",  # PHP
            ]
        )

        is_test_output = any(
            indicator in result_str[:500]
            for indicator in [
                "test session starts",
                "PASSED",
                "FAILED",
                "pytest",
                "unittest",
                "Test",
                "Traceback",
                "AssertionError",
                "===",
                "---",
                "collected",
                "passed",
                "failed",
            ]
        )

        # 根据内容类型设置不同的阈值
        if is_test_output:
            truncate_threshold = settings.output.test_output_threshold
            preview_length = settings.output.test_output_preview
        elif is_code_content:
            truncate_threshold = settings.output.code_content_threshold
            preview_length = settings.output.code_content_preview
        else:
            truncate_threshold = settings.output.normal_output_threshold
            preview_length = settings.output.normal_output_preview

        # 如果超过阈值，只显示预览
        if len(result_str) > truncate_threshold:
            preview = result_str[:preview_length]
            return f"{preview}...\n\n(Output too long, truncated. {len(result_str)} chars total. Agent received full content)"

        # 中等长度的输出
        medium_threshold = truncate_threshold // 2
        if len(result_str) > medium_threshold:
            return (
                result_str[:medium_threshold]
                + f"...\n\n(Truncated, {len(result_str)} chars total)"
            )

        return result_str

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
            async def _heartbeat(act, start):
                while True:
                    await asyncio.sleep(3)
                    elapsed = int(time.time() - start)
                    print(f"⏳ {act} running... ({elapsed}s)", flush=True)

            hb_task: asyncio.Task | None = None
            action_start = time.time()
            if action != "finalize_task":
                hb_task = asyncio.create_task(_heartbeat(action, action_start))
            try:
                if asyncio.iscoroutinefunction(self.tools[action]):
                    result = await asyncio.wait_for(
                        self.tools[action](**action_input), timeout=60.0
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: self.tools[action](**action_input)
                        ),
                        timeout=60.0,
                    )
            except asyncio.TimeoutError:
                return f"⏱️ Execution timeout\n\nAction '{action}' timed out after 60s\n\n💡 Tip: Task may be too complex, consider breaking into smaller steps"
            except asyncio.CancelledError:
                raise
            finally:
                if hb_task:
                    hb_task.cancel()
                    try:
                        await hb_task
                    except asyncio.CancelledError:
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

            # 优化：根据内容类型动态调整截断阈值（从配置读取）
            result_str = str(result)

            # 不再在这里做特殊处理，返回完整结果
            # 显示格式化由_format_observation_for_display处理

            # 判断内容类型
            is_code_content = any(
                indicator in result_str[:200]
                for indicator in [
                    "def ",
                    "class ",
                    "import ",
                    "from ",
                    "#!/",  # Python
                    "function ",
                    "const ",
                    "let ",
                    "var ",  # JavaScript
                    "public ",
                    "private ",
                    "protected ",  # Java/C++
                    "<?php",
                    "namespace ",  # PHP
                ]
            )

            is_test_output = any(
                indicator in result_str[:500]
                for indicator in [
                    "test session starts",
                    "PASSED",
                    "FAILED",
                    "pytest",
                    "unittest",
                    "Test",
                    "Traceback",
                    "AssertionError",
                    "===",
                    "---",
                    "collected",
                    "passed",
                    "failed",
                ]
            )

            # 根据内容类型设置不同的阈值（从配置读取）
            if is_test_output:
                truncate_threshold = settings.output.test_output_threshold
                preview_length = settings.output.test_output_preview
            elif is_code_content:
                truncate_threshold = settings.output.code_content_threshold
                preview_length = settings.output.code_content_preview
            else:
                truncate_threshold = settings.output.normal_output_threshold
                preview_length = settings.output.normal_output_preview

            # 尊重 run_shell 的 max_output 设置，不做第二层截断
            max_output_setting = None
            if action == "run_shell" and isinstance(result, dict):
                # run_shell 默认不截断，完全信任 atomic_tools 的处理
                truncate_threshold = 999999999

            # 如果超过阈值，Save 到文件
            if len(result_str) > truncate_threshold:
                try:
                    output_file = await self.context_manager.save_large_output(
                        result_str, f"{action}_output.txt"
                    )
                    # 返回预览内容
                    preview = result_str[:preview_length]
                    # 如果是测试输出且启 with 了 summarized ，尝试提取 summarized 
                    if is_test_output and settings.output.test_summary_enabled:
                        summary_lines = []
                        for line in result_str.split("\n"):
                            if any(
                                keyword in line
                                for keyword in [
                                    "passed",
                                    "failed",
                                    "error",
                                    "PASSED",
                                    "FAILED",
                                    "ERROR",
                                    "===",
                                    "collected",
                                ]
                            ):
                                summary_lines.append(line)
                        if summary_lines:
                            # 使 with 配置的最大 lines数
                            max_lines = settings.output.test_summary_max_lines
                            summary = "\n".join(summary_lines[-max_lines:])
                            return f"📄 Output too long ({len(result_str)} chars), saved to file: {output_file}\n\n📊 Test summary:\n{summary}\n\n💡 Use read_file tool to view full content"

                    return f"📄 Output too long ({len(result_str)} chars), saved to file: {output_file}\n\n💡 Use read_file tool to view full content\n\nFirst {preview_length} chars preview:\n{preview}..."
                except Exception as e:
                    # 如果Save 失败，返回更多内容
                    return f"{result_str[:preview_length]}...\n\n⚠️ (Output too long, truncated. Save failed: {str(e)})"

            # 对于中等长度的输出，返回更多内容
            medium_threshold = truncate_threshold // 2
            if len(result_str) > medium_threshold:
                return (
                    result_str[:medium_threshold]
                + f"...\n\n(Truncated, {len(result_str)} chars total)"
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

    async def _compact_context(self, messages: List[Dict]):
        """上下文缩减 - 智能版：让模型参与判断重要信息，并缩减文件内容"""
        print("📦 Executing smart context compaction...")

        # Save 完整历史到文件
        history_file = await self.context_manager.save_history(self.steps)

        # 从配置Get 参数
        keep_messages = (
            self.context_config.compact_keep_messages if self.context_config else 20
        )
        keep_rounds = (
            self.context_config.compact_keep_rounds if self.context_config else 8
        )
        summary_steps = (
            self.context_config.compact_summary_steps if self.context_config else 10
        )
        protect_first_rounds = (
            self.context_config.compact_protect_first_rounds
            if self.context_config
            else 3
        )

        # 计算需要缩减的消息范围
        if len(messages) <= keep_messages:
            print("✅ Message count within threshold, no compaction needed")
            return

        # 提取需要总结的中间消息（保留系统提示、前N轮、最近N轮）
        system_messages = messages[:2]  # 系统提示 + 初始任务
        first_rounds_messages = messages[
            2 : 2 + protect_first_rounds * 2
        ]  # 前N轮对话（任务规划）
        recent_messages = messages[-keep_rounds * 2 :]  # 最近N轮对话

        # 中间消息：跳过系统、前N轮、最近N轮
        middle_start = 2 + protect_first_rounds * 2
        middle_end = -keep_rounds * 2
        middle_messages = (
            messages[middle_start:middle_end]
            if len(messages) > middle_start + keep_rounds * 2
            else []
        )

        if not middle_messages:
            print("✅ No intermediate messages to compact")
            return

        # 智能缩减文件内容：将大段文件内容Save 到.aacode，只保留 summarized 
        middle_messages = await self._compact_file_contents(middle_messages)

        # 使 with 模型生成三块智能 summarized 
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

        # 构建缩减后的消息列表
        compacted_messages = system_messages.copy()
        compacted_messages.extend(first_rounds_messages)  # 添加前N轮（任务规划）

        # 插入三块智能 summarized 
        compact_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary_content = f"""## 🧠 Smart History Summary (AI Generated)

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
- To view the full history, use the read_file tool to read the above file
- Continue executing the current task, referencing recent observations
- Avoid duplicating already completed work"""

        compacted_messages.append({"role": "system", "content": summary_content})

        # 添加最近的消息
        compacted_messages.extend(recent_messages)

        # 计算缩减效果
        old_tokens = self._estimate_tokens(messages)
        new_tokens = self._estimate_tokens(compacted_messages)

        messages.clear()
        messages.extend(compacted_messages)

        print(f"✅ Smart context compaction done: {len(messages)} messages | Token: {old_tokens} → {new_tokens} (reduced {(old_tokens - new_tokens) / old_tokens * 100:.1f}%) | Protected first {protect_first_rounds} rounds | Kept last {keep_rounds} rounds | Summarized {len(middle_messages)} messages")

    async def _compact_file_contents(self, messages: List[Dict]) -> List[Dict]:
        """
        智能缩减内容：将大段内容Save 到.aacode，只保留 summarized 和路径

        处理的内容类型：
        1. read_file 的文件内容（已移除，现通过run_shell读取）
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
💡 To view full content, use read_file to read the archive file, or search for files yourself"""
                            else:
                                new_content = f"""[{self._get_content_type_name(content_type)} Archived]
Identifier: {identifier}
Archive path: {saved_path}
Size: {len(content)} chars
Summary: {summary}
💡 To view full content, use read_file to read the archive file, or search for files yourself"""

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
            for kw in ["file content", "read_file"]
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
            # 策略1: 从观察内容开头提取文件路径（read_file 的标准格式）
            # format: "观察：文件内容\n```python\n# path/to/file.py\n..."
            match = re.search(
                r"```[a-z]*\s*\n\s*#\s*([^\n]+\.[\w]+)", full_content, re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

            # 策略2: 查找明确的文件路径标记
            match = re.search(
                r"(?:file path|read_file)[:\s]+([^\n\s]+\.[\w]+)",
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

2. **read_file Content**:
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
[config.py full content archived, use read_file if needed]
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
   - Summarize all read_file operations
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

    async def _update_todo_from_error(self, observation, todo_manager) -> None:
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
                    item=fix_task, priority="high", category="Error Fix"
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
            # 显示消息分布
            system_tokens = self._estimate_tokens(
                [msg for msg in messages if msg.get("role") == "system"]
            )
            user_tokens = self._estimate_tokens(
                [msg for msg in messages if msg.get("role") == "user"]
            )
            assistant_tokens = self._estimate_tokens(
                [msg for msg in messages if msg.get("role") == "assistant"]
            )
            print(f"📊 Context monitor: ~{current_tokens} tokens |  System: {system_tokens} |  User: {user_tokens} | Assistant: {assistant_tokens}")

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
        """
        估算消息列表的token数

        Args:
            messages: 消息列表

        Returns:
            估算的token数
        """
        if self.encoding:
            # 使 with tiktoken精确计算
            total_tokens = 0
            for message in messages:
                content = message.get("content", "")
                try:
                    total_tokens += len(self.encoding.encode(content))
                except:
                    # 回退到简单估算
                    total_tokens += len(content) // 4
            return total_tokens
        else:
            # 简单估算：大约4字符=1token
            total_chars = sum(len(msg.get("content", "")) for msg in messages)
            return total_chars // 4


# 测试
if __name__ == "__main__":
    pass
