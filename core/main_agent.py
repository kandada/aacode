# 主Agent
# core/main_agent.py
"""
主Agent实现，负责协调任务和委托子任务
"""
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import os
from core.agent import BaseAgent
from core.react_loop import AsyncReActLoop
from core.multi_agent import MultiAgentSystem
from tools.atomic_tools import AtomicTools
from tools.code_tools import CodeTools
from tools.sandbox_tools import SandboxTools
from tools.web_tools import WebTools
from tools.todo_tools import TodoTools
from tools.incremental_tools import IncrementalTools
from utils.mcp_manager import MCPManager
from utils.session_manager import SessionManager
from utils.tool_registry import get_global_registry
from utils.tool_schemas import ALL_SCHEMAS
import openai
from core.sub_agent import SubAgent
import subprocess
from config import settings


class MainAgent(BaseAgent):
    """主Agent，负责复杂任务分解和协调"""

    def __init__(self,
                 project_path: Path,
                 context_manager: Any,
                 safety_guard: Any,
                 model_config: Dict,
                 **kwargs):

        # 初始化模型调用器
        model_caller = self._create_model_caller(model_config)

        # 初始化工具（主Agent有更多工具）
        tools = self._create_tools(project_path, safety_guard)

        # 系统提示
        system_prompt = """你是一个主AI编程助手，负责协调复杂的编码任务。

        请严格按照以下格式进行思考行动：
        
        Thought: 你的思考过程
        Action: 要执行的动作名称（必须是：read_file, write_file, run_shell, list_files, search_files, execute_python, run_tests, debug_code, delegate_task, check_task_status, get_project_status, create_sub_agent等可用工具中的一个，善用run_shell使用计算机能力，善用glob、grep、curl等，支持多数常见命令）
        Action Input: 动作输入（必须是JSON格式）

        例如：
        Thought: 我需要创建一个hello.py文件
        Action: write_file
        Action Input: {"path": "hello.py", "content": "print('Hello, World!')"}

        或者：
        Thought: 任务已完成
        Action:
        
        🌐 网络资源查询能力（重要！）：
        当你需要查询技术资料、API文档、最佳实践时，你应该：
        1. **优先使用fetch_url或curl命令直接访问官方文档**：
           - Python官方文档: https://docs.python.org/3/
           - Flask文档: https://flask.palletsprojects.com/
           - Django文档: https://docs.djangoproject.com/
           - FastAPI文档: https://fastapi.tiangolo.com/
           - React文档: https://react.dev/
           - Vue文档: https://vuejs.org/
           - Node.js文档: https://nodejs.org/docs/
           - MDN Web文档: https://developer.mozilla.org/
           - GitHub API: https://docs.github.com/
           - 其他常用技术网站csdn、知乎、腾讯云、阿里云文档等
           - 搜索引擎网站
        
        2. **按图索骥式查询流程**：
           - 第一步：使用fetch_url获取官方文档首页或目录页
           - 第二步：从返回的内容中找到相关章节的链接
           - 第三步：继续使用fetch_url访问具体章节
           - 第四步：提取所需信息并应用到代码中
        
        3. **搜索引擎作为补充**：
           - 当官方文档不够详细时，使用search_web搜索
           - 搜索关键词："{技术名} best practices"、"{技术名} tutorial"、"{技术名} example"
           - 优先查看Stack Overflow、GitHub、官方博客的结果
        
        4. **代码示例查询**：
           - 使用search_code工具在GitHub上搜索实际代码示例
           - 参考高星项目的实现方式
        
        示例查询流程：
        Thought: 我需要了解Flask的路由装饰器用法
        Action: fetch_url
        Action Input: {"url": "https://flask.palletsprojects.com/en/latest/quickstart/"}
        
        观察后：
        Thought: 文档中提到了更多高级用法，让我查看路由章节
        Action: fetch_url
        Action Input: {"url": "https://flask.palletsprojects.com/en/latest/api/#flask.Flask.route"}
        
        📚 多读多思考原则（最重要！）：
        1. **必读文档**: 
           - 任务开始时，首先使用 read_file 读取 init.md（项目规范）
           - 读取 README.md、requirements.txt 等关键文档
           - 查看项目结构映射文件（project_structure.md）
           - 读取必要的代码文件和其他相关的文件的全文进入上下文
        2. **充分搜索**: 
           - 使用 search_files 搜索相关代码和配置
           - 使用 list_files（或glob或grep命令） 了解完整的项目结构
           - 使用 search_web 搜索不熟悉的技术和最佳实践，或直接访问一些常用的官方文档网页
        3. **理解后行动**: 
           - 在充分理解项目结构和需求后再编写代码
           - 参考现有代码的风格和模式
           - 避免重复上下文中"重要错误历史"里的错误
        4. **持续学习**: 
           - 遇到错误时，先分析原因，搜索解决方案
           - 参考官方文档和最佳实践
           - 不要盲目重试相同的方法
        
         **自主解决问题能力**：
        当现有工具不足以完成任务时，你应该：
        1. **编写自定义代码**：使用 write_file 创建辅助脚本来解决特定问题
        2. **安装必要软件**：使用 run_shell 执行 pip install、apt-get install 等命令安装依赖
        3. **在沙箱中测试**：如果有沙箱工具，优先在沙箱中测试危险操作
        4. **创建临时工具**：编写一次性脚本来处理特殊需求（如数据转换、API调用等）
        5. **组合现有工具**：通过多个工具的组合使用来实现复杂功能
        
        **避免重复造轮子原则**：
        1. **优先修改现有文件**：当需要修改代码时，首先检查文件是否已存在，使用 read_file 读取现有内容，然后使用 incremental_update 或 write_file 修改
        2. **避免创建重复文件**：在创建新文件前，使用 list_files 或 search_files 检查是否已有类似功能的文件
        3. **复用现有代码**：查找项目中已有的类似实现，参考其模式和风格
        4. **使用增量更新**：对于代码修改，优先使用 incremental_update 工具而不是 write_file，这样可以保留原有结构
        
        示例场景：
        - 需要解析特殊格式文件 → 编写Python脚本处理
        - 需要调用外部API → 编写requests脚本
        - 需要特定库 → 先 pip install，再使用
        - 需要复杂数据处理 → 编写pandas/numpy脚本
        - 需要系统级操作 → 编写shell脚本执行
        
        可用工具：
        1.原子工具
        - read_file: 读取文件内容
        - write_file: 写入文件内容
        - run_shell: 执行shell命令
        - list_files: 列出文件
        - search_files: 搜索文件内容
        2.代码工具
        - execute_python: 执行Python代码
        - run_tests: 运行测试
        - debug_code: 调试代码
        3.管理工具
        - delegate_task: 委托任务给子Agent
        - check_task_status: 检查任务状态
        - get_project_status: 获取项目状态
        - create_sub_agent: 创建子Agent
        4.网络工具
        - search_web: 搜索互联网（searXNG引擎）
        - fetch_url: 获取网页内容（也可run_shell用curl等获取）
        - search_code: 搜索代码示例
        5.To-Do List工具
        - add_todo_item: 添加待办事项
        - mark_todo_completed: 标记待办事项为完成
        - update_todo_item: 更新待办事项
        - get_todo_summary: 获取待办清单摘要
        - list_todo_files: 列出待办清单文件
        - add_execution_record: 添加执行记录
         6.增量更新文件内容工具（推荐使用）
         - incremental_update: 增量更新文件（推荐用于代码更新，避免覆盖整个文件）
         - patch_file: 使用补丁更新文件（适用于精确修改）
         - get_file_diff: 获取文件差异（查看修改内容）
         
         **重要提示**：修改现有代码时，优先使用 incremental_update 而不是 write_file，这样可以：
         1. 保留原有代码结构
         2. 避免意外覆盖
         3. 更容易跟踪修改历史

          重要提示：
         1. 可以执行一个或多个Action（支持多个Action同时执行）
         2. Action必须是可用的工具名称之一
         3. Action Input必须是有效的JSON格式
         4. 任务完成后，Action字段留空
         5. 不要在Action中写代码块，只写工具名称
         
         多个Action格式示例：
         Thought: 我需要创建两个文件
         Action 1: write_file
         Action Input 1: {"path": "file1.py", "content": "print('hello')"}
         Action 2: write_file  
         Action Input 2: {"path": "file2.py", "content": "print('world')"}
         
         或者使用JSON格式：
         ```json
         {
           "thought": "我需要创建两个文件",
           "actions": [
             {
               "action": "write_file",
               "action_input": {"path": "file1.py", "content": "print('hello')"}
             },
             {
               "action": "write_file", 
               "action_input": {"path": "file2.py", "content": "print('world')"}
             }
           ]
         }
         ```

        代码质量和测试要求（重要！）：
        1. **测试驱动开发（TDD）**: 
           - 编写代码后**必须立即测试**，使用execute_python或run_tests工具
           - 不要只是"写完代码"就认为任务完成
           - 必须实际运行代码，验证功能正确性
        2. **错误必须修复**: 
           - 如果测试出现错误（ImportError、SyntaxError等），**必须继续迭代修复**
           - 不要在有错误的情况下声称"任务完成"
           - 持续迭代直到代码能够正常运行
        3. **动态更新TODO**: 
           - 发现错误时，添加新的待办事项（如"修复ImportError"）
           - 修复错误后，标记对应待办事项为完成
           - 保持待办清单与实际进度同步
        4. **增量更新**: 修改现有代码时，尽量只更新必要的部分，避免重写整个文件
        5. **全面测试**: 任务完成前必须进行全面的功能测试
        6. **错误处理**: 代码应包含适当的错误处理和边界情况检查
        7. **代码复用**: 优先使用现有代码和函数，避免重复造轮子
        8. **文档注释**: 为重要函数和类添加文档注释
        9. **性能考虑**: 编写高效、可维护的代码
        
        任务完成的标准（严格）：
        ✅ 代码已编写
        ✅ 代码已测试运行
        ✅ 所有错误已修复
        ✅ 功能验证通过
        ✅ 待办清单已更新
        ✅ 给出简要总结
        
        ❌ 只写完代码但未测试 → 任务未完成
        ❌ 测试出现错误但未修复 → 任务未完成
        ❌ 只完成了子步骤 → 任务未完成

        多语言支持：
        1. 项目可能包含多种编程语言，请根据文件扩展名识别语言
        2. 对于非Python代码，使用适当的语法和约定
        3. 跨语言调用时注意接口兼容性

        工作流程：
        1. 读取文档（init.md等） → 2. 分析需求 → 3. 制定计划 → 4. 编写代码 → 5. 立即测试 → 6. 修复问题 → 7. 全面验证 → 8. 简要报告"""

        super().__init__(
            agent_id="main",
            system_prompt=system_prompt,
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=kwargs.get('max_iterations', 50)
        )

        self.project_path = project_path
        self.safety_guard = safety_guard

        # 多Agent系统
        self.multi_agent_system = MultiAgentSystem(self, context_manager)

        # 子Agent注册表
        self.sub_agents: Dict[str, Any] = {}

        # 任务跟踪
        self.tasks: Dict[str, Dict] = {}
        
        # MCP管理器
        self.mcp_manager = MCPManager(project_path)
        
        # 会话管理器
        self.session_manager = SessionManager(project_path)
        
        # 移除复杂规划器，使用ReAct内置的动态规划

        # ReAct循环
        self.react_loop = AsyncReActLoop(
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=kwargs.get('max_iterations', settings.MAX_REACT_ITERATIONS),
            project_path=project_path,
            context_config=settings.context  # 传递上下文配置
        )

    def _create_model_caller(self, model_config: Dict):
        """创建模型调用器（支持流式输出）"""
        
        async def model_caller(messages: List[Dict]) -> str:
            try:
                # 使用提供的配置创建客户端
                api_key = model_config.get('api_key') or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
                base_url = model_config.get('base_url') or os.getenv("LLM_API_URL") or os.getenv("OPENAI_BASE_URL")
                model_name = model_config.get('name') or os.getenv("LLM_MODEL_NAME", "gpt-4")
                
                if not api_key:
                    # 回退到简单响应
                    return "错误：未设置API密钥。请设置 LLM_API_KEY 环境变量。"
                
                client = openai.OpenAI(
                    api_key=api_key,
                    base_url=base_url
                )
                
                # 确保消息格式正确
                formatted_messages = []
                for msg in messages:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    if role and content:
                        formatted_messages.append({
                            "role": role,
                            "content": content
                        })
                
                # 流式输出
                print("🤖 模型思考中", end="", flush=True)
                full_response = ""
                
                stream = client.chat.completions.create(
                    model=model_name,
                    messages=formatted_messages,
                    temperature=model_config.get('temperature', 0.1),
                    max_tokens=model_config.get('max_tokens', 8000),
                    stream=True  # 启用流式输出
                )
                
                # 处理流式响应 - 模型输出什么就打印什么
                for chunk in stream:
                    if chunk.choices[0].delta.content is not None:
                        content_chunk = chunk.choices[0].delta.content
                        full_response += content_chunk
                        # 实时打印
                        print(content_chunk, end="", flush=True)
                
                print()  # 换行
                return full_response if full_response is not None else ""
                
            except Exception as e:
                # 详细的错误信息
                error_msg = f"模型调用失败: {str(e)}"
                print(f"\n❌ {error_msg}")
                
                # 回退到简单的响应逻辑
                if len(messages) > 0:
                    last_msg = messages[-1].get('content', '').lower()
                    if '创建' in last_msg or 'create' in last_msg or 'hello' in last_msg:
                        return "我将创建一个hello world程序。\n\nAction: write_file\nAction Input: {\"path\": \"hello.py\", \"content\": \"print('Hello, World!')\"}"
                    elif '运行' in last_msg or 'run' in last_msg:
                        return "让我运行这个程序。\n\nAction: run_shell\nAction Input: {\"command\": \"python3 hello.py\"}"
                    elif '已完成' in last_msg or 'finish' in last_msg or 'action' not in last_msg:
                        return "任务已完成。\n\n"
                    else:
                        return "我需要分析当前情况并继续执行。\n\nAction: list_files\nAction Input: {\"pattern\": \"*\"}"
                return "任务完成。"
        
        return model_caller

    def _create_tools(self, project_path: Path, safety_guard) -> Dict[str, Any]:
        """创建工具集并注册到工具注册表"""

        atomic_tools = AtomicTools(project_path, safety_guard)
        code_tools = CodeTools(project_path, safety_guard)
        web_tools = WebTools(project_path, safety_guard)
        todo_tools = TodoTools(project_path, safety_guard)
        incremental_tools = IncrementalTools(project_path, safety_guard)

        # 主Agent的特殊工具
        tools = {
            # 原子工具
            "read_file": atomic_tools.read_file,
            "write_file": atomic_tools.write_file,
            "run_shell": atomic_tools.run_shell,
            "list_files": atomic_tools.list_files,
            "search_files": atomic_tools.search_files,

            # 代码工具
            "execute_python": code_tools.execute_python,
            "run_tests": code_tools.run_tests,
            "debug_code": code_tools.debug_code,

            # 网络工具
            "search_web": web_tools.search_web,
            "fetch_url": web_tools.fetch_url,
            "search_code": web_tools.search_code,

            # To-Do List工具
            "add_todo_item": todo_tools.add_todo_item,
            "mark_todo_completed": todo_tools.mark_todo_completed,
            "update_todo_item": todo_tools.update_todo_item,
            "get_todo_summary": todo_tools.get_todo_summary,
            "list_todo_files": todo_tools.list_todo_files,
            "add_execution_record": todo_tools.add_execution_record,

            # 增量更新工具
            "incremental_update": incremental_tools.incremental_update,
            "patch_file": incremental_tools.patch_file,
            "get_file_diff": incremental_tools.get_file_diff,

            # 管理工具
            "delegate_task": self.delegate_task,
            "check_task_status": self.check_task_status,
            "get_project_status": self.get_project_status,
            "create_sub_agent": self.create_sub_agent,
            
            # MCP工具
            "list_mcp_tools": self.list_mcp_tools,
            "call_mcp_tool": self.call_mcp_tool,
            "get_mcp_status": self.get_mcp_status,
            
            # 会话管理工具
            "new_session": self.new_session,
            "continue_session": self.continue_session,
            "list_sessions": self.list_sessions,
            "switch_session": self.switch_session,
            "delete_session": self.delete_session,
            "get_conversation_history": self.get_conversation_history,
            "get_session_stats": self.get_session_stats,
            
            # 动态规划已集成到ReAct循环中，移除复杂规划工具
        }

        # 可选：沙箱工具
        try:
            sandbox_tools = SandboxTools(project_path, safety_guard)
            tools.update({
                "run_in_sandbox": sandbox_tools.run_in_sandbox,
                "install_package": sandbox_tools.install_package,
                "call_mcp": sandbox_tools.call_mcp,
            })
        except:
            pass  # 沙箱工具可选

        # 注册工具到全局注册表
        registry = get_global_registry()
        for tool_name, tool_func in tools.items():
            if tool_name in ALL_SCHEMAS:
                registry.register(tool_func, ALL_SCHEMAS[tool_name])
        
        print(f"✅ 已注册 {len([t for t in tools.keys() if t in ALL_SCHEMAS])} 个工具到注册表")

        return tools

    async def execute(self,
                      task: str,
                      init_instructions: str = "",
                      task_dir: Optional[Path] = None,
                      max_iterations: int = 20,
                      project_analysis: str = "",
                      todo_manager: Optional[Any] = None) -> Dict[str, Any]:
        """
        执行任务

        Args:
            task: 任务描述
            init_instructions: 初始化指令
            task_dir: 任务目录
            max_iterations: 最大迭代次数
            project_analysis: 项目分析结果（类方法映射）
            todo_manager: to-do-list管理器

        Returns:
            执行结果
        """
        print(f"\n🤖 主Agent开始执行任务: {task}")
        self.start_time = asyncio.get_event_loop().time()
        
        # 创建会话并显示 session_id
        session_id = await self.session_manager.create_session(task)
        print(f"📋 会话ID: {session_id}")
        print(f"💡 提示: 使用 --session {session_id} 可以继续此会话")

        # 更新系统提示，包含项目分析结果
        analysis_section = ""
        if project_analysis and "失败" not in project_analysis:
            analysis_section = f"\n\n项目结构分析结果（类方法映射）:\n{project_analysis[:1500]}..."
            print("📊 项目分析结果已集成到系统提示中")
        
        full_system_prompt = f"{self.system_prompt}{analysis_section}\n\n项目初始化指令:\n{init_instructions}"
        self.conversation_history[0]['content'] = full_system_prompt

        # 添加任务描述
        self.conversation_history.append({
            "role": "user",
            "content": f"任务：{task}\n\n请参考项目结构分析结果，制定计划并执行。"
        })

        # 运行ReAct循环
        result = await self.react_loop.run(
            initial_prompt=full_system_prompt,
            task_description=task,
            todo_manager=todo_manager
        )

        # 更新统计
        self.iterations = len(self.react_loop.steps)

        return {
            **result,
            "session_id": session_id,
            "agent_stats": self.get_stats(),
            "execution_time": asyncio.get_event_loop().time() - self.start_time
        }

    async def delegate_task(self,
                            task_description: str,
                            agent_type: str = "general",
                            context_strategy: str = "isolated") -> Dict[str, Any]:
        """
        委托任务给子Agent

        Args:
            task_description: 任务描述
            agent_type: Agent类型 (general, code, test, research)
            context_strategy: 上下文策略 (isolated, shared, minimal)

        Returns:
            委托结果
        """
        task_id = f"subtask_{len(self.tasks)}_{datetime.now().timestamp():.0f}"

        print(f"🤝 委托任务给子Agent: {task_description[:50]}...")

        # 创建子任务记录
        self.tasks[task_id] = {
            "description": task_description,
            "agent_type": agent_type,
            "context_strategy": context_strategy,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "result": None
        }

        # 使用多Agent系统委托
        delegation_result = await self.multi_agent_system.delegate_task(
            task_description=task_description,
            task_type=agent_type,
            context_strategy=context_strategy
        )

        self.tasks[task_id]["status"] = "delegated"
        self.tasks[task_id]["delegation_result"] = delegation_result

        return {
            "task_id": task_id,
            "status": "delegated",
            "delegation_result": delegation_result
        }

    async def check_task_status(self, task_id: str) -> Dict[str, Any]:
        """检查任务状态"""
        if task_id not in self.tasks:
            return {"error": f"任务不存在: {task_id}"}

        task = self.tasks[task_id]

        # 检查子Agent状态
        if task["status"] == "delegated":
            if task_id in self.multi_agent_system.tasks:
                subtask = self.multi_agent_system.tasks[task_id]
                task["status"] = subtask.status
                task["result"] = subtask.result

        return {
            "task_id": task_id,
            "status": task["status"],
            "description": task["description"],
            "result": task.get("result"),
            "created_at": task["created_at"]
        }

    async def create_sub_agent(self,
                               agent_type: str = "code",
                               capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
        """创建子Agent"""
        agent_id = f"sub_{agent_type}_{len(self.sub_agents)}"

        # 根据类型选择系统提示
        if agent_type == "code":
            system_prompt = """你是一个专门的代码编写Agent。
            专注于：
            1. 编写高质量、可维护的代码
            2. 遵循最佳实践和编码规范
            3. 添加必要的注释和文档
            4. 编写单元测试
            5. 遵循越小且越简单原则，在完成任务的同时尽量不要对用户已有的代码做大调整
            6. 只更新代码文件中少量代码的时候，你尽量增量更新，而不是全量更新
            7. 尽量基于现有的代码进行扩写或改写，而不是重复造轮子，新建一个增强版的文件或代码块

            请使用提供的工具完成任务。"""
        elif agent_type == "test":
            system_prompt = """你是一个专门的测试Agent。
            专注于：
            1. 编写全面的测试用例
            2. 测试边界情况和异常处理
            3. 性能测试和压力测试
            4. 生成测试报告

            请使用提供的工具完成任务。"""
        elif agent_type == "research":
            system_prompt = """你是一个研究Agent。
            专注于：
            1. 查找和分析相关信息
            2. 整理研究笔记
            3. 生成研究报告
            4. 提供参考文献

            请使用提供的工具完成任务。"""
        else:
            system_prompt = """你是一个通用子Agent。
            请专注于完成指定的任务。"""

        # 创建子Agent
        sub_agent = SubAgent(
            agent_id=agent_id,
            system_prompt=system_prompt,
            model_caller=self.model_caller,
            tools=self.tools,  # 可以传递子集
            context_manager=self.context_manager,
            parent_agent_id=self.agent_id,
            max_iterations=self.max_iterations
        )

        self.sub_agents[agent_id] = sub_agent

        return {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": "created",
            "capabilities": capabilities if capabilities is not None else ["general"]
        }

    async def list_mcp_tools(self) -> Dict[str, Any]:
        """列出所有MCP工具"""
        try:
            tools_result = await self.mcp_manager.list_available_tools()
            return {
                "success": True,
                "tools": tools_result.get("tools", {}),
                "count": tools_result.get("count", 0),
                "connected_servers": tools_result.get("connected_servers", [])
            }
        except Exception as e:
            return {"error": f"获取MCP工具列表失败: {str(e)}"}
    
    async def call_mcp_tool(self, tool_name: str, arguments: Optional[Dict] = None) -> Dict[str, Any]:
        """调用MCP工具"""
        try:
            result = await self.mcp_manager.call_tool(tool_name, arguments or {})
            return result
        except Exception as e:
            return {"error": f"调用MCP工具失败: {str(e)}"}
    
    async def get_mcp_status(self) -> Dict[str, Any]:
        """获取MCP服务器状态"""
        try:
            status_result = await self.mcp_manager.get_server_status()
            return status_result
        except Exception as e:
            return {"error": f"获取MCP状态失败: {str(e)}"}
    
    async def new_session(self, task: str, title: Optional[str] = None) -> Dict[str, Any]:
        """创建新会话"""
        try:
            session_id = await self.session_manager.create_session(task, title)
            return {
                "success": True,
                "session_id": session_id,
                "message": "新会话已创建"
            }
        except Exception as e:
            return {"error": f"创建会话失败: {str(e)}"}
    
    async def continue_session(self, message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """继续当前会话或指定会话"""
        try:
            # 添加用户消息
            added = await self.session_manager.add_message("user", message)
            if not added:
                return {"error": "消息添加失败，可能超过token限制"}
            
            # 获取会话历史
            messages = await self.session_manager.get_messages(session_id)
            
            return {
                "success": True,
                "session_id": session_id or self.session_manager.current_session_id,
                "messages": messages,
                "conversation_preview": await self.session_manager.get_conversation_history()
            }
        except Exception as e:
            return {"error": f"继续会话失败: {str(e)}"}
    
    async def list_sessions(self) -> Dict[str, Any]:
        """列出所有会话"""
        try:
            sessions = await self.session_manager.list_sessions()
            return {
                "success": True,
                "sessions": sessions,
                "count": len(sessions)
            }
        except Exception as e:
            return {"error": f"获取会话列表失败: {str(e)}"}
    
    async def switch_session(self, session_id: str) -> Dict[str, Any]:
        """切换到指定会话"""
        try:
            success = await self.session_manager.switch_session(session_id)
            if success:
                return {
                    "success": True,
                    "session_id": session_id,
                    "message": "会话切换成功"
                }
            else:
                return {"error": f"会话不存在: {session_id}"}
        except Exception as e:
            return {"error": f"切换会话失败: {str(e)}"}
    
    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """删除会话"""
        try:
            success = await self.session_manager.delete_session(session_id)
            if success:
                return {
                    "success": True,
                    "session_id": session_id,
                    "message": "会话已删除"
                }
            else:
                return {"error": f"会话不存在: {session_id}"}
        except Exception as e:
            return {"error": f"删除会话失败: {str(e)}"}
    
    async def get_conversation_history(self, max_length: int = 10) -> Dict[str, Any]:
        """获取对话历史"""
        try:
            history = await self.session_manager.get_conversation_history(max_length)
            return {
                "success": True,
                "history": history
            }
        except Exception as e:
            return {"error": f"获取对话历史失败: {str(e)}"}
    
    # 移除复杂规划功能，使用ReAct内置的动态规划
    # 相关的create_plan、execute_plan_step、get_plan_status等方法已删除
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        try:
            stats = self.session_manager.get_session_stats()
            return {
                "success": True,
                "stats": stats
            }
        except Exception as e:
            return {"error": f"获取会话统计失败: {str(e)}"}
    
    async def get_project_status(self) -> Dict[str, Any]:
        """获取项目状态"""
        try:
            # 获取Git状态
            git_status = {}
            try:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    cwd=self.project_path
                )
                if result.returncode == 0:
                    git_status["changed_files"] = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
                    git_status["has_changes"] = bool(result.stdout.strip())
            except:
                git_status["error"] = "Git未初始化或不可用"

            # 统计文件
            file_count = 0
            total_size = 0
            for file_path in self.project_path.rglob("*"):
                if file_path.is_file():
                    file_count += 1
                    total_size += file_path.stat().st_size

            return {
                "project_path": str(self.project_path),
                "file_count": file_count,
                "total_size_bytes": total_size,
                "git_status": git_status,
                "active_tasks": len([t for t in self.tasks.values() if t["status"] != "completed"]),
                "sub_agents": len(self.sub_agents)
            }

        except Exception as e:
            return {"error": str(e)}


