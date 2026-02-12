# Agent基类
# core/agent.py
"""
Agent基类，提供所有Agent共享的基础功能
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable, Awaitable
from pathlib import Path
import inspect
import re
import json


class BaseAgent(ABC):
    """所有Agent的基类"""

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        model_caller: Callable[[List[Dict]], Awaitable[str]],
        tools: Dict[str, Callable],
        context_manager: Any,
        max_iterations: int = 20,
    ):

        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.model_caller = model_caller
        self.tools = tools
        self.context_manager = context_manager
        self.max_iterations = max_iterations

        # 会话历史
        self.conversation_history: List[Dict] = [
            {"role": "system", "content": system_prompt}
        ]

        # 执行统计
        self.iterations = 0
        self.tool_calls = 0
        self.start_time = None

    @abstractmethod
    async def execute(
        self,
        task: str,
        init_instructions: str = "",
        task_dir: Optional[Path] = None,
        max_iterations: int = 20,
    ) -> Dict[str, Any]:
        """执行任务（子类必须实现）"""
        pass

    async def call_model(self, messages: List[Dict]) -> str:
        """调用模型"""
        try:
            return await self.model_caller(messages)
        except Exception as e:
            raise Exception(f"模型调用失败: {str(e)}")

    async def call_tool(self, tool_name: str, tool_input: Dict) -> Any:
        """调用工具"""
        if tool_name not in self.tools:
            return {"error": f"工具不存在: {tool_name}"}

        tool_func = self.tools[tool_name]

        try:
            # 检查是否是异步函数
            if inspect.iscoroutinefunction(tool_func):
                result = await tool_func(**tool_input)
            else:
                # 同步函数包装为异步
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: tool_func(**tool_input)
                )

            self.tool_calls += 1
            return result

        except Exception as e:
            return {"error": f"工具执行失败: {str(e)}"}

    def get_stats(self) -> Dict[str, Any]:
        """获取Agent统计信息"""
        return {
            "agent_id": self.agent_id,
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "history_length": len(self.conversation_history),
        }

    def reset(self):
        """重置Agent状态"""
        self.conversation_history = [{"role": "system", "content": self.system_prompt}]
        self.iterations = 0
        self.tool_calls = 0
        self.start_time = None

    async def _parse_model_response(self, response: str) -> tuple:
        """解析模型响应（增强健壮性）"""
        # 方法1: 尝试解析标准JSON块
        json_patterns = [
            r"```json\n(.*?)\n```",  # 标准json块
            r"```JSON\n(.*?)\n```",  # 大写JSON
            r"```\n(.*?)\n```",  # 无语言标记
            r"```json\s*\n(.*?)(?:\n```|$)",  # 不严格的结束标记
        ]

        for pattern in json_patterns:
            json_match = re.search(pattern, response, re.DOTALL)
            if json_match:
                try:
                    json_content = json_match.group(1).strip()
                    data = json.loads(json_content)
                    thought = (
                        data.get("thought")
                        or data.get("thinking")
                        or data.get("reasoning")
                    )
                    action = (
                        data.get("action") or data.get("tool") or data.get("function")
                    )
                    action_input = (
                        data.get("action_input")
                        or data.get("input")
                        or data.get("parameters")
                    )

                    if thought and (action is not None):  # 允许action为空字符串
                        return (thought, action, action_input)
                except json.JSONDecodeError:
                    continue

        # 方法2: 尝试直接解析整个响应为JSON
        try:
            data = json.loads(response.strip())
            thought = (
                data.get("thought") or data.get("thinking") or data.get("reasoning")
            )
            action = data.get("action") or data.get("tool") or data.get("function")
            action_input = (
                data.get("action_input") or data.get("input") or data.get("parameters")
            )

            if thought and (action is not None):
                return (thought, action, action_input)
        except json.JSONDecodeError:
            pass

        # 方法3: 查找纯JSON对象（无代码块）
        json_obj_match = re.search(
            r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response, re.DOTALL
        )
        if json_obj_match:
            try:
                json_content = json_obj_match.group(0)
                data = json.loads(json_content)
                thought = (
                    data.get("thought") or data.get("thinking") or data.get("reasoning")
                )
                action = data.get("action") or data.get("tool") or data.get("function")
                action_input = (
                    data.get("action_input")
                    or data.get("input")
                    or data.get("parameters")
                )

                if thought and (action is not None):
                    return (thought, action, action_input)
            except json.JSONDecodeError:
                pass

        # 方法4: 解析结构化文本格式
        lines = response.strip().split("\n")
        thought = None
        action = None
        action_input = None

        # 支持多种键名格式
        thought_keys = ["Thought:", "思考:", "Thinking:", "Reasoning:", "分析:"]
        action_keys = ["Action:", "动作:", "Tool:", "Function:", "工具:"]
        action_input_keys = [
            "Action Input:",
            "Action_Input:",
            "动作输入:",
            "Input:",
            "输入:",
            "Parameters:",
            "参数:",
        ]

        current_section = None

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # 检测部分标题
            section_found = False
            for key in thought_keys:
                if line_stripped.startswith(key):
                    thought = line_stripped[len(key) :].strip()
                    current_section = "thought"
                    section_found = True
                    break

            if not section_found:
                for key in action_keys:
                    if line_stripped.startswith(key):
                        action = line_stripped[len(key) :].strip()
                        current_section = "action"
                        section_found = True
                        break

            if not section_found:
                for key in action_input_keys:
                    if line_stripped.startswith(key):
                        input_content = line_stripped[len(key) :].strip()
                        # 尝试解析为JSON
                        try:
                            action_input = json.loads(input_content)
                        except:
                            action_input = {"input": input_content}
                        current_section = "action_input"
                        section_found = True
                        break

            # 如果没有检测到标题，继续当前部分的内容
            if not section_found and current_section:
                if current_section == "thought" and thought:
                    thought += " " + line_stripped
                elif current_section == "action" and action:
                    action += " " + line_stripped

        # 如果没有找到thought，使用响应的前200个字符
        if not thought:
            thought = response[:200] + "..." if len(response) > 200 else response

        # 清理action
        if action:
            action = action.strip("`\"' ")  # 移除可能的代码块标记和引号

        return thought, action, action_input
