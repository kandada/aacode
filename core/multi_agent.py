# core/multi_agent.py
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
from aacode.i18n import t


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
            "message": f"Task delegated to sub-agent {task_id}",
        }

    async def _prepare_subagent_context(self, strategy: str) -> str:
        """准备子Agent上下文"""
        if strategy == "isolated":
            # 独立上下文，只传递任务描述
            return "Independent task execution context"

        elif strategy == "shared":
            # 共享完整上下文
            return await self.context_manager.get_context()

        elif strategy == "minimal":
            # 最小上下文，只传递必要信息
            return await self.context_manager.get_compact_context()

        else:
            return "Default context"

    async def _create_subagent(
        self, task_id: str, task_description: str, context: str, task_type: str
    ):
        """创建子Agent"""
        # 根据任务类型配置子Agent
        if task_type == "code_analysis":
            prompt = f"""You are a code analysis expert.
Task: {task_description}

Please focus on code analysis, providing:
1. Code structure analysis
2. Potential issues
3. Improvement suggestions
4. Specific code examples

Please return results in JSON format."""

        elif task_type == "testing":
            prompt = f"""You are a testing expert.
Task: {task_description}

Please focus on:
1. Writing test cases
2. Test coverage analysis
3. Edge case testing
4. Performance testing suggestions

Please return results in JSON format."""

        else:
            prompt = f"""Execute task: {task_description}

Context:
{context}"""

        # 创建简化的子Agent
        sub_agent = {
            "id": task_id,
            "prompt": prompt,
            "context": context,
            "tools": ["run_shell"],
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
                "analysis": "Code analysis complete",
                "issues": ["Found 3 potential issues"],
                "suggestions": ["Suggestion 1", "Suggestion 2"],
                "code_examples": ["Example code"],
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
        print(t("multi.task_done", id=task.id))
        print(t("multi.task_result", result=task.result))
