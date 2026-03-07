# 子Agent
# core/sub_agent.py
"""
子Agent实现，专注于特定任务
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
from core.agent import BaseAgent
from core.react_loop import AsyncReActLoop
import asyncio


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
        print(f"\n🔄 子Agent {self.agent_id} 开始任务")
        self.task_description = task
        self.start_time = float(asyncio.get_event_loop().time())

        # 重置会话历史
        self.reset()

        # 添加任务描述
        self.conversation_history.append(
            {
                "role": "user",
                "content": f"任务：{task}\n\n请专注于完成这个特定任务。完成后使用submit_result工具提交结果。",
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
                return {"error": "结果必须是字典格式"}

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

            print(f"✅ 子Agent {self.agent_id} 提交结果")

            return {
                "success": True,
                "result": result_with_metadata,
                "message": "结果提交成功",
            }

        except Exception as e:
            return {"error": f"提交结果失败: {str(e)}"}

    async def get_focused_tools(self) -> Dict[str, Any]:
        """获取聚焦的工具集（可根据Agent类型定制）"""
        # 基础工具集
        base_tools = ["read_file", "write_file", "search_files", "execute_python"]

        # 根据Agent ID判断类型
        if "test" in self.agent_id:
            base_tools.append("run_tests")
            base_tools.append("debug_code")

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
