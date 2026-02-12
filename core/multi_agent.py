# core/multi_agent.py
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json


@dataclass
class AgentTask:
    """Agent任务定义"""

    id: str
    description: str
    parent_id: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[Dict] = None
    created_at: float = 0.0


class MultiAgentSystem:
    """多Agent协作系统"""

    def __init__(self, main_agent, context_manager):
        self.main_agent = main_agent
        self.context_manager = context_manager
        self.sub_agents: Dict[str, Any] = {}
        self.tasks: Dict[str, AgentTask] = {}

        # 任务队列
        self.task_queue = asyncio.Queue()

    async def delegate_task(
        self,
        task_description: str,
        task_type: str = "code_analysis",
        context_strategy: str = "isolated",
    ) -> Dict[str, Any]:
        """
        委托任务给子Agent

        Args:
            task_description: 任务描述
            task_type: 任务类型
            context_strategy: 上下文策略 (isolated, shared, minimal)

        Returns:
            任务结果
        """
        task_id = f"task_{len(self.tasks)}_{int(asyncio.get_event_loop().time())}"

        task = AgentTask(
            id=task_id,
            description=task_description,
            parent_id="main",
            status="pending",
            created_at=asyncio.get_event_loop().time(),
        )

        self.tasks[task_id] = task

        # 根据策略创建子Agent上下文
        context = await self._prepare_subagent_context(context_strategy)

        # 创建子Agent
        sub_agent = await self._create_subagent(
            task_id=task_id,
            task_description=task_description,
            context=context,
            task_type=task_type,
        )

        self.sub_agents[task_id] = sub_agent

        # 异步执行任务
        asyncio.create_task(self._execute_subtask(sub_agent, task))

        return {
            "task_id": task_id,
            "status": "delegated",
            "message": f"任务已委托给子Agent {task_id}",
        }

    async def _prepare_subagent_context(self, strategy: str) -> str:
        """准备子Agent上下文"""
        if strategy == "isolated":
            # 独立上下文，只传递任务描述
            return "独立任务执行上下文"

        elif strategy == "shared":
            # 共享完整上下文
            return await self.context_manager.get_context()

        elif strategy == "minimal":
            # 最小上下文，只传递必要信息
            return await self.context_manager.get_compact_context()

        else:
            return "默认上下文"

    async def _create_subagent(
        self, task_id: str, task_description: str, context: str, task_type: str
    ):
        """创建子Agent"""
        # 根据任务类型配置子Agent
        if task_type == "code_analysis":
            prompt = f"""你是一个代码分析专家。
任务：{task_description}

请专注于代码分析，提供：
1. 代码结构分析
2. 潜在问题
3. 改进建议
4. 具体代码示例

请使用JSON格式返回结果。"""

        elif task_type == "testing":
            prompt = f"""你是一个测试专家。
任务：{task_description}

请专注于：
1. 编写测试用例
2. 测试覆盖率分析
3. 边缘情况测试
4. 性能测试建议

请使用JSON格式返回结果。"""

        else:
            prompt = f"""执行任务：{task_description}

上下文：
{context}"""

        # 创建简化的子Agent
        sub_agent = {
            "id": task_id,
            "prompt": prompt,
            "context": context,
            "tools": ["read_file", "search_files", "execute_python"],
            "max_iterations": 10,
        }

        return sub_agent

    async def _execute_subtask(self, sub_agent: Dict, task: AgentTask):
        """执行子任务"""
        try:
            task.status = "running"

            # 这里可以实际运行一个简化的Agent
            # 为了示例，我们模拟一个结果
            await asyncio.sleep(2)  # 模拟处理时间

            result = {
                "analysis": "代码分析完成",
                "issues": ["发现3个潜在问题"],
                "suggestions": ["建议1", "建议2"],
                "code_examples": ["示例代码"],
            }

            task.result = result
            task.status = "completed"

            # 通知主Agent
            await self._notify_main_agent(task)

        except Exception as e:
            task.status = "failed"
            task.result = {"error": str(e)}

    async def _notify_main_agent(self, task: AgentTask):
        """通知主Agent任务完成"""
        # 这里可以实现实际的通知机制
        print(f"📨 子任务完成: {task.id}")
        print(f"结果: {task.result}")
