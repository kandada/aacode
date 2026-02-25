# ReAct循环
# core/react_loop.py
"""
轻量化ReAct循环实现
支持异步工具调用和上下文管理
"""

import asyncio
import json
import re
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass
from pathlib import Path
from utils.agent_logger import get_logger
from utils.tool_registry import get_global_registry
from config import settings  # 导入全局配置


@dataclass
class ActionItem:
    """单个动作项"""

    action: str
    action_input: Dict
    observation: Optional[str] = None


@dataclass
class ReActStep:
    """ReAct单步记录"""

    thought: str
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
        初始化ReAct循环

        Args:
            model_caller: 异步模型调用函数
            tools: 工具字典
            context_manager: 上下文管理器
            max_iterations: 最大迭代次数
            project_path: 项目路径（用于日志记录）
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

        # Token计数器（用于智能缩减）
        try:
            import tiktoken

            self.encoding = tiktoken.get_encoding("cl100k_base")
        except:
            self.encoding = None
            print("⚠️  tiktoken未安装，将使用简单的token估算")

    async def run(
        self,
        initial_prompt: str,
        task_description: str,
        todo_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        运行ReAct循环

        Args:
            initial_prompt: 初始提示
            task_description: 任务描述
            todo_manager: to-do-list管理器

        Returns:
            执行结果
        """
        # 开始日志记录
        if self.logger:
            task_id = await self.logger.start_task(task_description)

        print(f"🚀 开始ReAct循环，最多{self.max_iterations}次迭代")

        # 初始上下文
        self.current_context = await self.context_manager.get_context()

        # 构建初始消息，集成规划提示到系统prompt中
        todo_section = ""
        if todo_manager:
            try:
                todo_summary = await todo_manager.get_todo_summary()
                if "error" not in todo_summary:
                    todo_section = f"""

## 📋 任务待办清单
已创建待办清单文件，请在每次思考时参考和更新待办事项：
- 待办清单文件: {todo_summary.get('todo_file', '未知')}
- 总事项: {todo_summary.get('total_todos', 0)} 
- 已完成: {todo_summary.get('completed_todos', 0)}
- 待处理: {todo_summary.get('pending_todos', 0)}
- 完成率: {todo_summary.get('completion_rate', 0):.1f}%

重要提示 - 待办清单管理：
在每次思考时，请参考待办清单并更新状态：
1. 当完成一个子任务时，在思考中提及并标记对应的待办事项为完成
2. 如果发现需要新的任务步骤，添加新的待办事项
3. 如果任务计划有变，更新现有的待办事项
4. 每次迭代后添加执行记录

示例思考：
"我已经完成了用户认证API的开发。现在需要标记'实现认证API'待办事项为完成，并添加'测试认证功能'作为新的待办事项。"
"""
            except Exception as e:
                print(f"⚠️  获取待办清单摘要失败: {e}")

        system_prompt = f"""{initial_prompt}{todo_section}

📝 输出格式（重要！）：
你的每次回复应该只包含：
1. Thought: 你的思考过程
2. Action: 要执行的工具名称
3. Action Input: 工具的参数（JSON格式）

**不要输出Observation**！系统会自动执行工具并返回真实的结果。
**可以执行一个或多个Action（支持多个Action同时执行）
**善用工具，尤其善用run_shell使用计算机能力

示例格式：
```
Thought: 我需要读取配置文件来了解项目设置
Action: read_file
Action Input: {{"path": "config.py"}}
```

重要提示 - 思考中的规划：
在每次思考时，请自然地进行规划：
- 如果是复杂任务（涉及应用、系统、项目、架构等），在前几次思考时先分析需求、检查环境、制定计划
- 如果任务中包含"规划"、"分析"、"检查"、"重新"、"计划"、"策略"、"需求"等关键词，在思考中主动进行规划
- 保持思考的自然性，将规划作为思考过程的一部分，而不是独立的任务

🔄 持续迭代和错误处理（最重要！）：
1. **测试驱动**: 编写代码后**必须立即测试**
   - 使用 execute_python 运行Python代码
   - 使用 run_shell 运行其他程序
   - 使用 run_tests 运行测试套件
2. **错误必须修复**: 
   - 如果测试出现错误（ImportError、SyntaxError、逻辑错误等），**不要停止**
   - 分析错误原因，更新待办清单（添加"修复XX错误"）
   - 继续迭代修复错误，直到代码正常运行
3. **动态更新TODO**: 
   - 发现新问题时，添加新的待办事项
   - 完成子任务时，标记待办事项为完成
   - 保持待办清单反映真实进度
4. **不要过早声称完成**: 
   - ❌ 错误示例："代码已编写，任务完成" → 但代码未测试
   - ✅ 正确示例："代码已编写，现在测试..." → 发现错误 → "修复错误..." → "测试通过，任务完成"

代码开发最佳实践：
1. **测试驱动**: 编写代码后立即测试，使用execute_python或run_tests工具验证功能
2. **增量更新**: 修改代码时尽量只更新必要的部分，避免重写整个文件,也要避免新建一个增强版的文件与原文件并存
3. **全面验证**: 任务完成前必须进行全面的功能测试
4. **错误处理**: 确保代码包含适当的错误处理和边界情况检查
5. **代码质量**: 编写高效、可维护、有良好注释的代码


"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"任务：{task_description}\n\n当前上下文：\n{self.current_context}\n\n请按照Thought->Action的格式执行（不要输出Observation，系统会自动执行工具并返回结果）。",
            },
        ]

        start_time = asyncio.get_event_loop().time()

        for iteration in range(self.max_iterations):
            iteration_start = asyncio.get_event_loop().time()
            print(f"\n🔄 迭代 {iteration + 1}/{self.max_iterations}")

            # 调用模型获取思考
            model_start = asyncio.get_event_loop().time()
            response = await self.model_caller(messages)
            model_time = asyncio.get_event_loop().time() - model_start

            # 记录模型调用
            if self.logger:
                await self.logger.log_model_call(
                    messages=messages,
                    response=response,
                    response_time=model_time,
                    model_info={"iteration": iteration + 1},
                )

            # 解析响应（支持多个action）
            thought, actions = self._parse_response(response)

            # 自动更新待办清单
            if todo_manager:
                await self._update_todo_from_thought(thought, todo_manager)

            # 记录步骤
            step = ReActStep(
                thought=thought, actions=[], timestamp=asyncio.get_event_loop().time()
            )
            self.steps.append(step)

            # 注意：模型思考内容已在 main_agent.py 中流式打印，此处不再重复显示

            # 检查是否完成（没有action表示任务完成）
            if not actions or await self._is_task_completed(
                thought, actions[0].action if actions else None, task_description
            ):
                print("✅ 任务完成")
                print(f"\n📋 任务总结:\n{thought}")
                total_time = asyncio.get_event_loop().time() - start_time
                if self.logger:
                    await self.logger.log_iteration(
                        iteration=iteration + 1,
                        thought=thought,
                        action=None,
                        action_input=None,
                        execution_time=asyncio.get_event_loop().time()
                        - iteration_start,
                    )
                    await self.logger.finish_task(
                        final_status="completed",
                        total_iterations=iteration + 1,
                        total_time=total_time,
                        summary={"final_thought": thought},
                    )
                return {
                    "status": "completed",
                    "final_thought": thought,
                    "iterations": iteration + 1,
                    "steps": self.steps,
                    "total_time": total_time,
                }

            # 执行所有动作（增强错误处理和重试机制）
            all_observations = []
            all_observations_for_display = []  # 用于显示的简化版本

            for i, action_item in enumerate(actions):
                print(f"🛠️  动作 {i+1}/{len(actions)}: {action_item.action}")
                action_start = asyncio.get_event_loop().time()

                # 添加重试机制（使用配置的最大重试次数，来自 aacode_config.yaml）
                max_retries = settings.limits.max_retries
                retry_count = 0
                observation = None
                observation_for_display = None

                while retry_count < max_retries:
                    try:
                        # 获取完整的工具执行结果
                        full_result = await self._execute_action_internal(
                            action_item.action, action_item.action_input
                        )

                        # 为Agent保留完整结果
                        observation = full_result

                        # 为用户显示生成简化版本
                        observation_for_display = self._format_observation_for_display(
                            action_item.action, full_result
                        )

                        # 检查是否需要重试（某些错误可以重试）
                        if observation and isinstance(observation, str):
                            if "错误" in observation or "error" in observation.lower():
                                # 检查是否是可重试的错误
                                retryable_errors = [
                                    "timeout",
                                    "connection",
                                    "temporary",
                                    "暂时",
                                ]
                                if any(
                                    err in observation.lower()
                                    for err in retryable_errors
                                ):
                                    retry_count += 1
                                    if retry_count < max_retries:
                                        print(
                                            f"⚠️  动作失败，{retry_count}/{max_retries} 次重试..."
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
                                f"⚠️  动作异常，{retry_count}/{max_retries} 次重试: {str(e)}"
                            )
                            await asyncio.sleep(1)
                        else:
                            observation = f"执行错误（已重试{max_retries}次）: {str(e)}"
                            observation_for_display = observation
                            break

                if observation is None:
                    observation = f"执行失败：未获得结果（已重试{max_retries}次）"
                    observation_for_display = observation

                action_time = asyncio.get_event_loop().time() - action_start

                # 记录观察结果（完整版本）
                action_item.observation = observation
                assert step.actions is not None, "step.actions should not be None"
                step.actions.append(action_item)
                all_observations.append(observation)  # Agent获取完整内容
                all_observations_for_display.append(
                    observation_for_display
                )  # 用户看到简化版本

                # 🔥 新增：从错误中自动更新待办清单
                if todo_manager:
                    await self._update_todo_from_error(observation, todo_manager)

                # 记录工具调用
                if self.logger:
                    await self.logger.log_tool_call(
                        tool_name=action_item.action,
                        tool_input=action_item.action_input or {},
                        result=observation,
                        execution_time=action_time,
                        success=not (
                            observation.startswith("错误")
                            or "error" in observation.lower()
                        ),
                        metadata=(
                            {"retry_count": retry_count} if retry_count > 0 else None
                        ),
                    )

            # 合并所有观察结果（Agent获取完整内容）
            observation = "\n".join(
                [f"动作 {i+1} 结果: {obs}" for i, obs in enumerate(all_observations)]
            )

            # 合并显示版本（用户看到简化版本）
            observation_for_display = "\n".join(
                [
                    f"动作 {i+1} 结果: {obs}"
                    for i, obs in enumerate(all_observations_for_display)
                ]
            )

            # 上下文一致性检查
            await self._validate_context_consistency(
                all_observations, all_observations_for_display, messages
            )

            # 记录迭代（使用完整observation）
            if self.logger:
                await self.logger.log_iteration(
                    iteration=iteration + 1,
                    thought=thought,
                    action=", ".join([a.action for a in actions]) if actions else None,
                    action_input={"multiple_actions": True, "count": len(actions)},
                    observation=observation,  # 日志记录完整内容
                    execution_time=asyncio.get_event_loop().time() - iteration_start,
                )

            # 更新上下文（使用完整observation）
            await self.context_manager.update(observation)
            self.current_context = await self.context_manager.get_compact_context()

            # 添加观察到消息（Agent获取完整内容）
            messages.append({"role": "assistant", "content": response})
            messages.append(
                {
                    "role": "user",
                    "content": f"观察：{observation}\n\n请继续...",  # Agent获取完整observation
                }
            )

            # 智能上下文缩减检查（基于token数）
            current_tokens = self._estimate_tokens(messages)
            trigger_tokens = (
                self.context_config.compact_trigger_tokens
                if self.context_config
                else 8000
            )

            if current_tokens > trigger_tokens:
                print(f"📊 当前token数: {current_tokens}, 触发阈值: {trigger_tokens}")
                await self._compact_context(messages)
                if self.logger:
                    await self.logger.log_context_update(
                        update_type="compact",
                        content=f"在第{iteration + 1}次迭代后执行上下文缩减（token数: {current_tokens}）",
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

        print("\n⚠️  达到最大迭代次数，任务可能未完成")
        print(f"💡 提示：你可以继续执行追加任务来完成剩余工作")

        return {
            "status": "max_iterations_reached",
            "iterations": self.max_iterations,
            "steps": self.steps,
            "total_time": total_time,
            "message": "达到最大迭代次数，建议继续会话完成任务",
        }

    async def _is_task_completed(
        self, thought: str, first_action: Optional[str], task_description: str
    ) -> bool:
        """
        使用模型判断任务是否已完成

        Args:
            thought: 当前思考内容
            first_action: 第一个动作（如果有）
            task_description: 原始任务描述

        Returns:
            是否任务已完成
        """
        # 如果没有action，才可能是任务完成
        if not first_action:
            # 检查最近的执行记录中是否有错误
            has_recent_errors = await self._check_recent_errors()
            if has_recent_errors:
                print("⚠️  检测到最近的执行错误，任务未完成，继续解决问题")
                return False

            # 使用模型判断
            try:
                # 获取最近的执行结果上下文
                recent_context = await self._get_recent_execution_context()

                completion_check_prompt = f"""请判断以下任务是否已经完成。

原始任务：{task_description}

当前思考：{thought}

最近执行情况：
{recent_context}

判断标准（严格）：
1. 任务的核心目标是否已经实现（例如：要求写爬虫，是否已经创建并测试了爬虫代码）
2. 是否只是完成了某个子步骤（例如：只是"标记待办事项为完成"不算任务完成）
3. 是否明确表示整个任务已经完成，不需要进一步操作
4. **关键**：如果最近的执行中有错误（ImportError、SyntaxError等），任务未完成
5. **关键**：如果代码未经过实际运行测试验证，任务未完成
6. **关键**：如果只是"写完代码"但没有"运行测试"，任务未完成

请只回答 "YES" 或 "NO"：
- YES: 整个任务已经完成，代码已测试通过，没有错误
- NO: 任务还未完成、有错误需要修复、或只是完成了子步骤

回答："""

                messages = [{"role": "user", "content": completion_check_prompt}]
                response = await self.model_caller(messages)

                # 解析响应
                response_clean = response.strip().upper()
                if "YES" in response_clean[:10]:  # 检查前10个字符
                    return True
                else:
                    return False

            except Exception as e:
                print(f"⚠️  模型判断任务完成状态失败: {e}")
                # 回退到简单判断：如果有错误就不算完成
                if has_recent_errors:
                    return False
                return True

        # 如果有action，检查是否是最终确认动作
        final_actions = ["finalize", "complete_task", "finish"]
        if first_action.lower() in final_actions:
            return True

        return False

    async def _check_recent_errors(self) -> bool:
        """检查最近的步骤中是否有错误"""
        if not self.steps:
            return False

        # 检查最近3步
        recent_steps = self.steps[-3:]
        error_keywords = [
            "error",
            "exception",
            "traceback",
            "failed",
            "failure",
            "错误",
            "异常",
            "失败",
            "importerror",
            "syntaxerror",
            "nameerror",
            "typeerror",
            "valueerror",
            "attributeerror",
        ]

        for step in recent_steps:
            if step.actions:
                for action in step.actions:
                    if action.observation:
                        obs_lower = action.observation.lower()
                        if any(keyword in obs_lower for keyword in error_keywords):
                            return True

        return False

    async def _get_recent_execution_context(self) -> str:
        """获取最近的执行上下文（用于任务完成判断）"""
        if not self.steps:
            return "无执行记录"

        # 获取最近3步的摘要
        recent_steps = self.steps[-3:]
        context_parts = []

        for i, step in enumerate(recent_steps):
            context_parts.append(
                f"\n步骤 {len(self.steps) - len(recent_steps) + i + 1}:"
            )
            context_parts.append(f"  思考: {step.thought[:500]}...")

            if step.actions:
                for action in step.actions:
                    context_parts.append(f"  动作: {action.action}")
                    if action.observation:
                        # 检查是否有错误
                        obs_preview = action.observation[:1000]
                        if any(
                            kw in action.observation.lower()
                            for kw in ["error", "错误", "failed", "失败"]
                        ):
                            context_parts.append(f"  ❌ 结果: {obs_preview}...")
                        else:
                            context_parts.append(f"  ✅ 结果: {obs_preview}...")

        return "\n".join(context_parts)

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
                    print(f"⚠️  JSON解析失败 (pattern {pattern[:20]}...): {str(e)}")
                    if json_str:
                        print(f"   尝试的JSON: {json_str[:100]}...")
                    else:
                        print(f"   尝试的JSON: [无法获取JSON字符串]")
                    continue
                except Exception as e:
                    print(f"⚠️  JSON处理异常: {str(e)}")
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

            # 匹配Action行（支持编号，但Action名称不能是"Input"）
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

                # 查找对应的Action Input（最多向下查找10行）
                action_input = {}
                found_input = False

                for j in range(i + 1, min(i + 11, len(lines))):
                    input_line = lines[j].strip()

                    # 如果遇到下一个Action，停止查找
                    if re.match(
                        r"Action\s*(\d+)?[:\s]+(?!Input)", input_line, re.IGNORECASE
                    ):
                        break

                    # 匹配Action Input行
                    input_match = re.match(
                        r"Action\s+Input\s*(\d+)?[:\s]+(.+)", input_line, re.IGNORECASE
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
                            except json.JSONDecodeError as e:
                                # JSON解析失败，提供详细错误信息
                                print(f"⚠️  Action Input JSON解析失败: {str(e)}")
                                print(f"   原始输入: {input_text[:100]}...")
                                action_input = {
                                    "_error": f"JSON格式错误: {str(e)}",
                                    "_raw": input_text,
                                    "_suggestion": "请检查JSON格式：1) 键名需要双引号 2) 字符串值需要双引号 3) 不要有尾随逗号",
                                }
                                found_input = True
                                break
                        else:
                            # 非JSON格式，尝试智能解析
                            action_input = self._parse_non_json_input(input_text)
                            found_input = True
                            break

                # 添加action（即使没有找到input也添加空字典）
                actions.append(
                    ActionItem(
                        action=action_name,
                        action_input=action_input if found_input else {},
                    )
                )

            i += 1

        # 如果没有解析到thought，使用响应的前200字符
        if not thought:
            thought = response[:500] + ("..." if len(response) > 200 else "")

        return thought, actions

    def _fix_json_format(self, json_str: str) -> str:
        """尝试修复常见的JSON格式问题"""
        # 移除尾随逗号
        json_str = re.sub(r",\s*}", "}", json_str)
        json_str = re.sub(r",\s*]", "]", json_str)

        # 修复单引号为双引号（但要小心字符串内的单引号）
        # 这是一个简化的实现，可能不完美
        # json_str = json_str.replace("'", '"')

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
        格式化observation用于显示给用户（简化版本）
        Agent内部仍然获取完整结果
        """
        # 特殊处理：read_file显示可折叠预览
        if action == "read_file" and isinstance(result, dict) and result.get("success"):
            path = result.get("path", "unknown")
            lines = result.get("lines", 0)
            size = result.get("size", 0)
            content = result.get("content", "")

            # 显示前20行作为预览
            preview_lines = content.split("\n")[:20]
            preview = "\n".join(preview_lines)

            if len(content.split("\n")) > 20:
                return f"📄 {path} ({lines}行, {size}字符)\n```\n{preview}\n...\n```\n📋 显示前20行，完整内容已保存（共{len(content.split('\n'))}行）"
            else:
                return f"📄 {path} ({lines}行, {size}字符)\n```\n{preview}\n```"

        # 其他动作返回完整结果（可能被截断）
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
            return f"{preview}...\n\n（输出过长已截断，共{len(result_str)}字符，Agent已获取完整内容）"

        # 中等长度的输出
        medium_threshold = truncate_threshold // 2
        if len(result_str) > medium_threshold:
            return (
                result_str[:medium_threshold]
                + f"...\n\n（已截断，共{len(result_str)}字符）"
            )

        return result_str

    async def _execute_action_internal(self, action: str, action_input: Dict) -> str:
        """执行动作（内部方法，返回完整结果）"""
        registry = get_global_registry()

        if action not in self.tools:
            # 使用工具注册表提供友好的错误消息
            return registry.format_tool_not_found_error(action)

        try:
            # 验证输入参数
            if action_input is None:
                action_input = {}

            if not isinstance(action_input, dict):
                return f'错误：动作输入必须是字典格式，当前类型：{type(action_input)}\n提示：请使用 {{"key": "value"}} 格式'

            # 检查是否包含JSON解析错误
            if "_error" in action_input:
                error_detail = action_input["_error"]
                raw_input = action_input.get("_raw", "N/A")
                suggestion = action_input.get("_suggestion", "请检查JSON格式")
                return f"❌ 参数解析错误\n\n错误: {error_detail}\n原始输入: {raw_input}\n\n💡 {suggestion}"

            # 使用工具注册表验证参数
            validation_result = registry.validate_call(action, action_input)
            if not validation_result.valid:
                # 返回详细的验证错误消息
                error_msg = f"❌ 参数验证失败\n\n{validation_result.error_message}\n\n"
                # 添加工具文档引用
                doc = registry.get_documentation(action)
                if doc:
                    error_msg += f"📖 工具文档：\n{doc[:500]}..."
                return error_msg

            # 规范化参数（将别名转换为标准名称）
            schema = registry.get_schema(action)
            if schema:
                action_input = schema.normalize_params(action_input)

            # 异步执行工具（增加超时保护）
            try:
                if asyncio.iscoroutinefunction(self.tools[action]):
                    # 为异步工具添加超时保护（默认60秒）
                    result = await asyncio.wait_for(
                        self.tools[action](**action_input), timeout=60.0
                    )
                else:
                    # 同步函数转异步（也添加超时）
                    result = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: self.tools[action](**action_input)
                        ),
                        timeout=60.0,
                    )
            except asyncio.TimeoutError:
                return f"⏱️ 执行超时\n\n动作 '{action}' 执行超过60秒\n\n💡 提示：任务可能过于复杂，考虑分解为更小的步骤"
            except asyncio.CancelledError:
                # 任务被取消，重新抛出以便上层处理
                raise

            # 处理结果（增强None检查）
            if result is None:
                return "✅ 执行成功（无返回值）"

            # 处理字典结果（增强错误检测）
            if isinstance(result, dict):
                if "error" in result:
                    error_msg = result["error"]
                    # 提供更友好的错误提示
                    if "permission" in error_msg.lower() or "权限" in error_msg:
                        return f"🔒 权限错误\n\n{error_msg}\n\n💡 提示：\n- 检查文件/目录权限\n- 可能需要修改权限或使用其他路径\n- 使用 run_shell 执行 chmod 命令修改权限"
                    elif "not found" in error_msg.lower() or "不存在" in error_msg:
                        return f"🔍 未找到错误\n\n{error_msg}\n\n💡 提示：\n- 检查文件/目录是否存在\n- 确认路径是否正确\n- 使用 list_files 查看可用文件"
                    elif "timeout" in error_msg.lower() or "超时" in error_msg:
                        return f"⏱️ 超时错误\n\n{error_msg}\n\n💡 提示：\n- 网络请求或操作超时\n- 可以重试或检查网络连接\n- 考虑增加超时时间"
                    else:
                        return f"❌ 错误：{error_msg}"
                elif "success" in result and not result["success"]:
                    reason = result.get("message") or result.get("reason") or "未知原因"
                    return f"❌ 执行失败：{reason}"

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

            # 如果超过阈值，保存到文件
            if len(result_str) > truncate_threshold:
                try:
                    output_file = await self.context_manager.save_large_output(
                        result_str, f"{action}_output.txt"
                    )
                    # 返回预览内容
                    preview = result_str[:preview_length]
                    # 如果是测试输出且启用了摘要，尝试提取摘要
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
                            # 使用配置的最大行数
                            max_lines = settings.output.test_summary_max_lines
                            summary = "\n".join(summary_lines[-max_lines:])
                            return f"📄 输出过长（{len(result_str)}字符），已保存到文件：{output_file}\n\n📊 测试摘要：\n{summary}\n\n💡 使用 read_file 工具查看完整内容"

                    return f"📄 输出过长（{len(result_str)}字符），已保存到文件：{output_file}\n\n💡 使用 read_file 工具查看完整内容\n\n前{preview_length}字符预览：\n{preview}..."
                except Exception as e:
                    # 如果保存失败，返回更多内容
                    return f"{result_str[:preview_length]}...\n\n⚠️ （输出过长已截断，保存失败：{str(e)}）"

            # 对于中等长度的输出，返回更多内容
            medium_threshold = truncate_threshold // 2
            if len(result_str) > medium_threshold:
                return (
                    result_str[:medium_threshold]
                    + f"...\n\n（已截断，共{len(result_str)}字符）"
                )

            return result_str

        except TypeError as e:
            # 参数错误（增强提示）
            error_str = str(e)
            error_msg = f"❌ 执行错误：参数不匹配\n\n{error_str}\n\n"

            # 尝试提取缺失或多余的参数信息
            if "missing" in error_str.lower():
                error_msg += "💡 可能原因：缺少必需参数\n"
            elif (
                "unexpected" in error_str.lower()
                or "got an unexpected" in error_str.lower()
            ):
                error_msg += "💡 可能原因：使用了不存在的参数名\n"
            elif "takes" in error_str.lower() and "positional" in error_str.lower():
                error_msg += "💡 可能原因：参数数量不匹配\n"

            error_msg += f"\n📝 你的输入：\n"
            error_msg += f"  动作：{action}\n"
            error_msg += f"  参数：{action_input}\n\n"

            # 添加工具文档（完整版）
            doc = registry.get_documentation(action)
            if doc:
                error_msg += f"📖 正确的工具文档：\n{doc}\n"

            # 添加常见错误提示
            error_msg += "\n🔧 常见解决方法：\n"
            error_msg += "  1. 检查参数名是否拼写正确\n"
            error_msg += "  2. 确认所有必需参数都已提供\n"
            error_msg += "  3. 检查参数类型是否正确（字符串、数字等）\n"
            error_msg += "  4. 参考上面的工具文档和示例\n"

            return error_msg
        except FileNotFoundError as e:
            return f"🔍 执行错误：文件未找到\n\n{str(e)}\n\n💡 提示：\n- 检查文件路径是否正确\n- 确认文件是否存在\n- 使用 list_files 查看可用文件"
        except PermissionError as e:
            return f"🔒 执行错误：权限不足\n\n{str(e)}\n\n💡 提示：\n- 可能需要修改文件权限\n- 使用 run_shell 执行 chmod 命令\n- 或选择有权限的目录"
        except ConnectionError as e:
            return f"🌐 执行错误：网络连接失败\n\n{str(e)}\n\n💡 提示：\n- 检查网络连接\n- 稍后重试\n- 检查防火墙设置"
        except Exception as e:
            # 提供更详细的错误信息（增强诊断）
            import traceback

            error_trace = traceback.format_exc()
            error_type = type(e).__name__
            error_msg = str(e)

            # 特殊错误类型的友好提示
            friendly_tips = {
                "JSONDecodeError": "JSON格式错误，请检查输入的JSON字符串格式",
                "KeyError": "缺少必需的键，请检查输入参数",
                "ValueError": "值错误，请检查输入参数的值是否有效",
                "ImportError": "导入错误，可能缺少依赖包，使用 run_shell 安装",
                "ModuleNotFoundError": "模块未找到，使用 run_shell 安装依赖包",
                "AttributeError": "属性错误，对象可能不存在该属性或方法",
                "IndexError": "索引错误，列表索引超出范围",
                "KeyboardInterrupt": "用户中断操作",
            }

            tip = friendly_tips.get(error_type, "请检查错误信息并修正")

            return f"❌ 执行错误：{error_type}\n\n{error_msg}\n\n💡 提示：{tip}\n\n📋 详细信息：\n{error_trace[:300]}..."

    async def _compact_context(self, messages: List[Dict]):
        """上下文缩减 - 智能版：让模型参与判断重要信息，并缩减文件内容"""
        print("📦 执行智能上下文缩减...")

        # 保存完整历史到文件
        history_file = await self.context_manager.save_history(self.steps)

        # 从配置获取参数
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
            print("✅ 消息数量未超过阈值，无需缩减")
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
            print("✅ 没有中间消息需要缩减")
            return

        # 智能缩减文件内容：将大段文件内容保存到.aacode，只保留摘要
        middle_messages = await self._compact_file_contents(middle_messages)

        # 使用模型生成三块智能摘要
        try:
            summaries = await self._generate_three_part_summary(
                middle_messages, self.steps[-summary_steps:]
            )
        except Exception as e:
            print(f"⚠️  智能摘要生成失败，使用简单摘要: {e}")
            summary = await self._generate_summary(self.steps[-summary_steps:])
            summaries = {
                "file_content_summary": "",
                "tool_execution_summary": summary,
                "keep_original_summary": "",
            }

        # 构建缩减后的消息列表
        compacted_messages = system_messages.copy()
        compacted_messages.extend(first_rounds_messages)  # 添加前N轮（任务规划）

        # 插入三块智能摘要
        summary_content = f"""## 🧠 智能历史摘要（AI生成）

### 📁 文件内容摘要
{summaries['file_content_summary'] or '无文件读取操作'}

### 🔧 工具执行摘要
{summaries['tool_execution_summary'] or '无工具执行'}

### 💡 重要信息（保留原样）
{summaries['keep_original_summary'] or '无需特别保留的信息'}

**完整历史**: {history_file}

**重要提示**: 
- 上述摘要由AI分析生成，分类保留了关键信息
- 文件内容已归档，可通过归档路径重新读取
- 如需查看完整历史，使用 read_file 工具读取上述文件
- 继续执行当前任务，参考最近的观察结果
- 避免重复已完成的工作"""

        compacted_messages.append({"role": "system", "content": summary_content})

        # 添加最近的消息
        compacted_messages.extend(recent_messages)

        # 计算缩减效果
        old_tokens = self._estimate_tokens(messages)
        new_tokens = self._estimate_tokens(compacted_messages)

        messages.clear()
        messages.extend(compacted_messages)

        print(f"✅ 智能上下文缩减完成：{len(messages)} 条消息")
        print(
            f"   Token数: {old_tokens} → {new_tokens} (减少 {old_tokens - new_tokens}, {(old_tokens - new_tokens) / old_tokens * 100:.1f}%)"
        )
        print(f"   保护前 {protect_first_rounds} 轮（任务规划）")
        print(f"   保留最近 {keep_rounds} 轮对话")
        print(f"   摘要了 {len(middle_messages)} 条中间消息")

    async def _compact_file_contents(self, messages: List[Dict]) -> List[Dict]:
        """
        智能缩减内容：将大段内容保存到.aacode，只保留摘要和路径

        处理的内容类型：
        1. read_file 的文件内容
        2. run_shell 的长输出
        3. search_files 的搜索结果
        4. list_files 的文件列表
        5. execute_python 的执行输出

        Args:
            messages: 消息列表

        Returns:
            缩减后的消息列表
        """
        compacted = []

        for msg in messages:
            content = msg.get("content", "")

            # 跳过已经归档的内容（避免重复处理）
            if "[已归档]" in content or "归档路径:" in content:
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

                    # 保存到.aacode/context/
                    try:
                        saved_path = await self.context_manager.save_large_output(
                            content_block,
                            f"{content_type}_{identifier}_{asyncio.get_event_loop().time():.0f}.txt",
                        )

                        # 生成智能摘要
                        summary = self._generate_content_summary(
                            content_block, content_type
                        )

                        # 替换为简短引用（包含摘要、路径和哈希）
                        # 从路径中提取哈希值
                        import re

                        hash_match = re.search(r"_([a-f0-9]{8})\.txt$", saved_path)
                        hash_info = f"哈希: {hash_match.group(1)}" if hash_match else ""

                        if content_type == "file_content":
                            replacement = f"""[{self._get_content_type_name(content_type)}已归档]
原文件: {identifier}
归档路径: {saved_path}
大小: {len(content_block)} 字符
{hash_info}
摘要: {summary}
💡 如需查看完整内容，使用 read_file 工具读取归档文件: {saved_path}"""
                        else:
                            replacement = f"""[{self._get_content_type_name(content_type)}已归档]
标识: {identifier}
归档路径: {saved_path}
大小: {len(content_block)} 字符
{hash_info}
摘要: {summary}
💡 如需查看完整内容，使用 read_file 工具读取归档文件: {saved_path}"""

                        new_content = new_content.replace(content_block, replacement)
                        content_modified = True

                    except Exception as e:
                        print(f"⚠️  保存{content_type}内容失败: {e}")

                # 策略2：如果没有代码块，但内容很长（>1500字符），检查是否有大段文本
                if not content_modified and len(content) > 1500:
                    # 检查是否有搜索结果、文件列表等
                    if "匹配" in content or "search" in content.lower():
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
                                new_content = f"""[{self._get_content_type_name(content_type)}已归档]
原文件: {identifier}
归档路径: {saved_path}
大小: {len(content)} 字符
摘要: {summary}
💡 如需查看完整内容，使用 read_file 工具读取归档文件，或自己搜索文件"""
                            else:
                                new_content = f"""[{self._get_content_type_name(content_type)}已归档]
标识: {identifier}
归档路径: {saved_path}
大小: {len(content)} 字符
摘要: {summary}
💡 如需查看完整内容，使用 read_file 工具读取归档文件，或自己自主搜索需要的文件"""

                            content_modified = True

                        except Exception as e:
                            print(f"⚠️  保存{content_type}内容失败: {e}")

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
            for kw in ["文件内容", "file content", "读取文件", "read_file"]
        ):
            return "file_content"
        elif any(
            kw in full_lower
            for kw in ["执行命令", "run_shell", "命令输出", "command output", "stdout"]
        ):
            return "shell_output"
        elif any(
            kw in full_lower for kw in ["搜索结果", "search_files", "search results"]
        ):
            return "search_results"
        elif any(kw in full_lower for kw in ["文件列表", "list_files", "file list"]):
            return "file_list"
        elif any(
            kw in full_lower
            for kw in ["执行结果", "execute_python", "代码输出", "code output"]
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
            # 格式: "观察：文件内容\n```python\n# path/to/file.py\n..."
            match = re.search(
                r"```[a-z]*\s*\n\s*#\s*([^\n]+\.[\w]+)", full_content, re.IGNORECASE
            )
            if match:
                return match.group(1).strip()

            # 策略2: 查找明确的文件路径标记
            match = re.search(
                r"(?:文件路径|file path|读取文件|read_file)[:\s]+([^\n\s]+\.[\w]+)",
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
                r"(?:命令|command)[:\s]+([^\n]+)", full_content, re.IGNORECASE
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
                r"(?:搜索|search|query)[:\s]+([^\n]+)", full_content, re.IGNORECASE
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
        """生成内容的智能摘要"""
        # 提取前200字符作为预览
        preview = content_block[:200].replace("\n", " ").strip()
        if len(content_block) > 200:
            preview += "..."

        # 根据内容类型添加额外信息
        if content_type == "shell_output":
            # 检查是否有错误
            if "error" in content_block.lower() or "failed" in content_block.lower():
                preview = "⚠️ 包含错误信息 | " + preview
            elif (
                "success" in content_block.lower() or "passed" in content_block.lower()
            ):
                preview = "✅ 执行成功 | " + preview

        elif content_type == "search_results":
            # 统计匹配数
            import re

            matches = len(re.findall(r"\n", content_block[:1000]))
            preview = f"约 {matches} 个匹配 | " + preview

        elif content_type == "file_list":
            # 统计文件数
            import re

            files = len(re.findall(r"\n", content_block[:1000]))
            preview = f"约 {files} 个文件 | " + preview

        return preview

    def _get_content_type_name(self, content_type: str) -> str:
        """获取内容类型的友好名称"""
        names = {
            "file_content": "文件内容",
            "shell_output": "命令输出",
            "search_results": "搜索结果",
            "file_list": "文件列表",
            "code_output": "代码输出",
            "content": "内容",
        }
        return names.get(content_type, "内容")

    async def _generate_intelligent_summary(
        self, middle_messages: List[Dict], recent_steps: List[ReActStep]
    ) -> str:
        """使用模型生成智能摘要"""
        # 构建摘要请求
        summary_prompt = f"""请分析以下对话历史和执行步骤，生成一个简洁但全面的摘要。

**摘要要求**：
1. 保留所有关键决策和重要发现
2. 记录已完成的主要任务和子任务
3. 标注遇到的重要错误和解决方案
4. 保留重要的文件路径、配置信息
5. 删除冗余和重复的信息
6. 使用结构化格式（标题、列表）
7. 控制在500-800字符内

**工具内容卸载原则**（重要！）：
对于已经完成其目的的工具输出，应该适当缩减，但必须保留归档路径：

1. **已归档的内容**：
   - 如果看到 "[xxx已归档]" 标记，说明完整内容已保存
   - 摘要中必须保留归档路径，格式：`归档: .aacode/context/xxx.txt`
   - 可以进一步精简摘要，但不能删除归档路径

2. **read_file 的内容**：
   - 如果文件内容已经被使用（如：已经根据内容编写了代码、已经理解了配置）
   - 摘要：保留关键信息 + 归档路径
   - 例：`已读取 config.py，了解数据库配置 | 归档: .aacode/context/file_content_xxx.txt`

3. **run_shell 的输出**：
   - 如果命令输出已经被处理（如：已经根据版本信息安装了包）
   - 摘要：保留结果 + 归档路径
   - 例：`执行 pytest，15 passed | 归档: .aacode/context/shell_output_xxx.txt`

4. **search_files 的结果**：
   - 如果搜索结果已经被使用（如：已经找到目标文件）
   - 摘要：保留关键发现 + 归档路径
   - 例：`搜索到 10 个匹配，定位到 utils/helper.py | 归档: .aacode/context/search_results_xxx.txt`

5. **list_files 的结果**：
   - 如果文件列表已经被使用（如：已经了解项目结构）
   - 摘要：保留结构概览 + 归档路径
   - 例：`项目包含 50 个文件，主要模块 core/, utils/ | 归档: .aacode/context/file_list_xxx.txt`

**关键原则**：
- ✅ 必须保留：归档路径（.aacode/context/xxx.txt）
- ✅ 必须保留：关键决策和发现
- ✅ 可以精简：详细的输出内容
- ❌ 不能删除：归档路径引用
- ❌ 不能删除：未解决的错误信息
   - 摘要：只保留"已读取 xxx 文件，了解了 yyy"，不保留完整内容
   - 例外：如果后续可能还需要参考，保留关键部分

2. **run_shell 的输出**：
   - 如果命令输出已经被处理（如：已经根据版本信息安装了包、已经根据测试结果修复了bug）
   - 摘要：只保留"执行了 xxx 命令，结果是 yyy"，不保留完整输出
   - 例外：如果是错误信息且未解决，保留详细信息

3. **search_files 的结果**：
   - 如果搜索结果已经被使用（如：已经找到了目标文件并进行了修改）
   - 摘要：只保留"搜索到 N 个匹配，定位到 xxx 文件"
   - 例外：如果还需要进一步分析，保留关键匹配

4. **list_files 的结果**：
   - 如果文件列表已经被使用（如：已经了解了项目结构）
   - 摘要：只保留"项目包含 N 个文件，主要有 xxx, yyy"
   - 例外：如果还需要查找特定文件，保留完整列表

5. **execute_python 的输出**：
   - 如果代码执行结果已经被验证（如：测试通过、功能正常）
   - 摘要：只保留"执行了 xxx 代码，测试通过"
   - 例外：如果有错误需要修复，保留错误信息

**判断是否可以卸载的标准**：
- ✅ 可以卸载：工具输出已经达成了其目的（理解、验证、定位等）
- ✅ 可以卸载：后续步骤没有再次引用该内容
- ❌ 不能卸载：内容包含未解决的错误
- ❌ 不能卸载：内容是当前任务的核心参考资料
- ❌ 不能卸载：后续步骤可能需要再次查看

**摘要示例**：

不好的摘要（保留了太多已使用的内容）：
```
步骤1: 读取了 config.py 文件
内容: [完整的500行配置文件内容]
步骤2: 根据配置文件修改了数据库连接
```

好的摘要（适当卸载）：
```
步骤1: 读取 config.py，了解了数据库配置（host=localhost, port=5432）
步骤2: 根据配置修改了数据库连接，测试通过
[config.py 完整内容已归档，如需查看使用 read_file 工具]
```

**对话历史**（{len(middle_messages)}条消息）：
"""

        # 添加中间消息的简要内容
        for i, msg in enumerate(middle_messages[:20]):  # 最多20条
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # 每条最多200字符
            summary_prompt += f"\n[{role}] {content}..."

        if len(middle_messages) > 20:
            summary_prompt += f"\n... 还有 {len(middle_messages) - 20} 条消息"

        # 添加执行步骤
        summary_prompt += f"\n\n**执行步骤**（最近{len(recent_steps)}步）：\n"
        for i, step in enumerate(recent_steps):
            summary_prompt += f"\n步骤{i+1}: {step.thought[:150]}..."
            if step.actions:
                summary_prompt += (
                    f"\n  动作: {', '.join([a.action for a in step.actions])}"
                )

        summary_prompt += (
            "\n\n请生成摘要（500-800字符），注意适当卸载已完成目的的工具内容："
        )

        # 调用模型生成摘要
        try:
            summary_messages = [{"role": "user", "content": summary_prompt}]
            summary_response = await asyncio.wait_for(
                self.model_caller(summary_messages), timeout=30.0  # 30秒超时
            )

            # 清理摘要（移除可能的markdown格式）
            summary = summary_response.strip()
            if summary.startswith("```"):
                summary = "\n".join(summary.split("\n")[1:-1])

            # 限制长度
            if len(summary) > 1000:
                summary = summary[:1000] + "..."

            return summary
        except asyncio.TimeoutError:
            return "摘要生成超时，请查看完整历史"
        except Exception as e:
            return f"摘要生成失败: {str(e)}"

    async def _generate_three_part_summary(
        self, middle_messages: List[Dict], recent_steps: List[ReActStep]
    ) -> Dict[str, str]:
        """使用模型生成三块分类摘要"""
        summary_prompt = f"""请分析以下对话历史，生成三块分类摘要。

**对话历史**（{len(middle_messages)}条消息）：
"""

        # 添加中间消息的简要内容
        for i, msg in enumerate(middle_messages[:30]):  # 最多30条
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:300]  # 每条最多300字符
            summary_prompt += f"\n[{role}] {content}..."

        if len(middle_messages) > 30:
            summary_prompt += f"\n... 还有 {len(middle_messages) - 30} 条消息"

        summary_prompt += f"""

**要求**：生成三块摘要，返回JSON格式：

{{
  "file_content_summary": "文件内容摘要（200-300字）",
  "tool_execution_summary": "工具执行摘要（200-300字）",
  "keep_original_summary": "需要保留原样的重要信息（100-200字）"
}}

**各块说明**：

1. **file_content_summary**（文件内容摘要）：
   - 总结所有 read_file 操作
   - 格式：`读取了 config.py（数据库配置）、main.py（主程序）| 归档: .aacode/context/xxx.txt`
   - 必须保留归档路径
   - 如果没有文件读取，返回空字符串

2. **tool_execution_summary**（工具执行摘要）：
   - 总结 run_shell、search_files、list_files 等工具执行
   - 格式：`执行了3次测试（2次通过），搜索到10个匹配文件 | 归档: .aacode/context/xxx.txt`
   - 保留关键结果和归档路径
   - 如果没有工具执行，返回空字符串

3. **keep_original_summary**（重要信息保留）：
   - 包含未解决的错误
   - 包含关键决策和架构选择
   - 包含重要技术依赖和技术参数
   - 包含关键工具执行结果
   - 如果没有需要特别保留的，返回空字符串

**关键原则**：
- ✅ 必须保留所有归档路径（.aacode/context/xxx.txt）
- ✅ 已归档内容只保留摘要+路径，不保留详细内容
- ✅ 未解决的错误必须在 keep_original_summary 中
- ❌ 不要重复信息
- ❌ 不要保留已完成任务的详细输出

请返回JSON格式的三块摘要："""

        # 调用模型生成摘要
        try:
            summary_messages = [{"role": "user", "content": summary_prompt}]
            summary_response = await asyncio.wait_for(
                self.model_caller(summary_messages), timeout=60.0  # 60秒超时
            )

            # 解析JSON响应
            summaries = self._extract_json_from_response(summary_response)

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
                "tool_execution_summary": "摘要生成超时",
                "keep_original_summary": "",
            }
        except Exception as e:
            return {
                "file_content_summary": "",
                "tool_execution_summary": f"摘要生成失败: {str(e)}",
                "keep_original_summary": "",
            }

    def _extract_json_from_response(self, response: str) -> Optional[Dict]:
        """从模型响应中提取JSON（复用健壮的解析逻辑）"""
        import json
        import re

        # 使用与 _parse_response 相同的JSON解析模式
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
        """从思考中自动更新待办清单"""
        try:
            # 添加执行记录
            await todo_manager.add_execution_record(f"思考: {thought[:300]}...")

            # 检查是否完成事项
            completion_keywords = [
                "完成",
                "finished",
                "done",
                "实现",
                "创建",
                "编写",
                "添加",
                "修复",
                "解决",
                "测试通过",
                "验证",
                "部署",
            ]

            thought_lower = thought.lower()
            for keyword in completion_keywords:
                if keyword in thought_lower:
                    # 尝试标记相关待办事项为完成
                    # 这里可以添加更智能的匹配逻辑
                    pass

            # 检查是否需要添加新事项
            planning_keywords = [
                "需要",
                "下一步",
                "接下来",
                "计划",
                "准备",
                "将要",
                "打算",
                "考虑",
                "建议",
                "推荐",
            ]

            for keyword in planning_keywords:
                if keyword in thought_lower:
                    # 提取可能的任务描述
                    # 这里可以添加更智能的提取逻辑
                    pass

        except Exception as e:
            print(f"⚠️  更新待办清单失败: {e}")

    async def _update_todo_from_error(self, observation, todo_manager) -> None:
        """从错误观察中自动添加修复任务到待办清单 - 优化版：更精确的错误检测"""
        try:
            if not todo_manager:
                return

            # 1. 处理字典格式的observation
            if isinstance(observation, dict):
                # 特殊处理：run_shell 的返回
                # run_shell 总是返回 success=True（工具执行成功）
                # 需要检查 returncode 来判断命令是否成功
                if "returncode" in observation:
                    returncode = observation.get("returncode", 0)
                    if returncode == 0:
                        # 命令执行成功，不是错误
                        return
                    # returncode != 0，继续检查是否需要添加待办事项
                    # 但不是所有非零退出码都需要添加待办事项
                    # 例如：grep 没找到匹配（退出码1）是正常的
                    stderr = observation.get("stderr", "")
                    if stderr and any(
                        err in stderr.lower()
                        for err in ["error", "exception", "traceback", "failed"]
                    ):
                        # stderr 中有明确的错误信息，才添加待办事项
                        pass
                    else:
                        # 只是非零退出码，但没有明确错误，不添加待办事项
                        return

                # 如果明确标记为成功，直接返回
                if observation.get("success") is True and "error" not in observation:
                    return

                # 如果有 error 字段但 success=True，可能是超时等情况
                if observation.get("success") is True and "error" in observation:
                    # 检查是否是超时
                    if observation.get("timeout"):
                        # 超时可以添加待办事项
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
                "成功",
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
                "执行失败",
                "execution failed",
                "command failed",
                # 参数错误
                "参数验证失败",
                "parameter validation failed",
                # 权限错误
                "permission denied",
                "权限不足",
                # 工具执行异常
                "工具执行异常",
            ]

            has_error = any(indicator in obs_lower for indicator in error_indicators)

            # 如果没有明确的错误标识，但包含"error"关键词，进一步检查
            if not has_error and "error" in obs_lower:
                # 检查是否是真正的错误消息格式
                import re

                # 匹配 "error: xxx" 或 "错误: xxx" 格式
                if re.search(r"(error|错误)[:\s]+\w+", obs_lower):
                    has_error = True

            if not has_error:
                return

            # 6. 提取更详细的错误信息
            error_type, error_detail = self._extract_error_info(obs_str)

            # 7. 只有在错误类型明确时才添加待办事项
            if error_type != "未知错误":
                fix_task = f"{error_type}: {error_detail}"
                await todo_manager.add_todo_item(
                    item=fix_task, priority="high", category="错误修复"
                )

                # 不再打印"已自动添加待办事项"，因为 add_todo_item 已经打印了
                # 只在日志级别记录
                pass
            else:
                # 未知错误：不自动添加待办事项，避免噪音
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

        # 2. 尝试匹配命令执行失败（改进：更精确的匹配）
        if "命令执行失败" in observation or "command failed" in observation.lower():
            # 提取退出码
            exitcode_match = re.search(r"退出码[:\s]+(\d+)", observation)
            if exitcode_match:
                exitcode = exitcode_match.group(1)
                # 提取 stderr 或错误消息
                stderr_match = re.search(
                    r"错误输出[:\s]+(.+)", observation, re.IGNORECASE | re.DOTALL
                )
                if stderr_match:
                    stderr_text = stderr_match.group(1).strip()[:150]
                    return "命令执行失败", f"退出码 {exitcode}: {stderr_text}"
                return "命令执行失败", f"退出码 {exitcode}"

            # 没有退出码信息，尝试提取错误输出
            stderr_match = re.search(
                r"错误输出[:\s]+(.+)", observation, re.IGNORECASE | re.DOTALL
            )
            if stderr_match:
                return "命令执行失败", stderr_match.group(1).strip()[:150]

            return "命令执行失败", "命令返回非零退出码"

        # 3. 检查 returncode 或 exit code
        if "returncode" in observation.lower() or "exit code" in observation.lower():
            stderr_match = re.search(
                r"stderr[:\s]+(.+)", observation, re.IGNORECASE | re.DOTALL
            )
            if stderr_match:
                return "命令执行失败", stderr_match.group(1).strip()[:150]
            return "命令执行失败", "命令返回非零退出码"

        # 4. 尝试匹配参数错误
        if (
            "参数验证失败" in observation
            or "parameter validation failed" in observation.lower()
        ):
            # 提取参数名
            param_match = re.search(r"参数[:\s]+(\w+)", observation)
            if param_match:
                return "参数错误", f"参数 {param_match.group(1)} 验证失败"
            return "参数错误", observation[:150]

        # 5. 尝试匹配权限错误
        if "权限" in observation or "permission" in observation.lower():
            return "权限错误", observation[:150]

        # 6. 尝试匹配文件不存在
        if "不存在" in observation or "not found" in observation.lower():
            return "文件不存在", observation[:150]

        # 7. 未知错误
        return "未知错误", observation[:150]

    async def _generate_summary(self, recent_steps: List[ReActStep]) -> str:
        """生成步骤摘要 - 优化：包含更多关键信息"""
        summary_parts = []
        for i, step in enumerate(recent_steps):
            # 保留更多思考内容（从100提高到200字符）
            thought_preview = step.thought[:200] + (
                "..." if len(step.thought) > 200 else ""
            )
            summary_parts.append(f"\n### 步骤 {i + 1}")
            summary_parts.append(f"**思考**: {thought_preview}")

            if step.actions:
                summary_parts.append(
                    f"**动作**: {', '.join([a.action for a in step.actions])}"
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
            all_observations: Agent获取的完整观察结果
            all_observations_for_display: 用户看到的简化观察结果
            messages: 当前消息列表
        """
        # 1. 检查观察结果数量一致性
        if len(all_observations) != len(all_observations_for_display):
            print(f"⚠️  上下文一致性警告：观察结果数量不匹配")
            print(
                f"   Agent观察数: {len(all_observations)}, 用户观察数: {len(all_observations_for_display)}"
            )

        # 2. 检查token使用情况
        current_tokens = self._estimate_tokens(messages)
        if current_tokens > 5000:  # 警告阈值
            print(f"📊 上下文大小监控：当前约{current_tokens} tokens")

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

            print(f"   系统消息: {system_tokens} tokens")
            print(f"   用户消息: {user_tokens} tokens")
            print(f"   Assistant消息: {assistant_tokens} tokens")

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
                        print(f"✅ 归档路径一致性：动作{i+1}归档到 {archive_file}")
                else:
                    print(
                        f"⚠️  归档路径不一致：动作{i+1}的简化版本包含归档路径，但完整版本可能丢失"
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
            # 使用tiktoken精确计算
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
