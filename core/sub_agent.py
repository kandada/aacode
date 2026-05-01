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
        **kwargs,
    ):

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

        # 创建专用的ReAct循环
        self.react_loop = AsyncReActLoop(
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=kwargs.get("max_iterations", 15),
        )

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
                "content": f"Task: {task}\n\nPlease focus on completing this specific task. Use submit_result tool to submit the result when done.",
            }
        )

        # 运行ReAct循环
        result = await self.react_loop.run(
            initial_prompt=self.system_prompt, task_description=task
        )

        # 更新统计
        self.iterations = len(self.react_loop.steps)

        execution_time = 0.0
        if self.start_time is not None:
            execution_time = asyncio.get_event_loop().time() - self.start_time

        return {
            **result,
            "agent_id": self.agent_id,
            "task": task,
            "agent_stats": self.get_stats(),
            "execution_time": execution_time,
        }

    async def submit_result(self, result: Dict) -> Dict[str, Any]:
        """提交任务结果（用于结构化输出）"""
        try:
            # 验证结果格式
            if not isinstance(result, dict):
                return {"error": "Result must be dict format"}

            # 添加元数据
            result_with_metadata = {
                **result,
                "agent_id": self.agent_id,
                "parent_agent_id": self.parent_agent_id,
                "task_description": self.task_description,
                "submitted_at": asyncio.get_event_loop().time(),
                "iterations": self.iterations,
                "tool_calls": self.tool_calls,
            }

            print(f"✅ SubAgent {self.agent_id} submitted result")

            return {
                "success": True,
                "result": result_with_metadata,
                "message": "Result submitted successfully",
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
