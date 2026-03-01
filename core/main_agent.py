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
from core.prompts import SYSTEM_PROMPT_FOR_MAIN_AGENT
from tools.atomic_tools import AtomicTools
from tools.code_tools import CodeTools
from tools.sandbox_tools import SandboxTools
from tools.web_tools import WebTools
from tools.todo_tools import TodoTools
from tools.incremental_tools import IncrementalTools
from utils.mcp_manager import MCPManager
from utils.session_manager import SessionManager
from utils.tool_registry import get_global_registry
from utils.tool_schemas import get_all_schemas, get_schema
from tools.skills_tools import SkillsManager
from tools.multimodal_tools import MultimodalTools, get_multimodal_tools_schema
from core.sub_agent import SubAgent
import subprocess
import openai
from config import settings


class MainAgent(BaseAgent):
    """主Agent，负责复杂任务分解和协调"""

    def __init__(
        self,
        project_path: Path,
        context_manager: Any,
        safety_guard: Any,
        model_config: Dict,
        **kwargs,
    ):

        # 初始化模型调用器
        model_caller = self._create_model_caller(model_config)

        # 先初始化skills_manager，因为_create_tools需要它
        # 从配置中获取skills配置
        skills_config = (
            {"skills_metadata": settings.skills.skills_metadata}
            if hasattr(settings.skills, "skills_metadata")
            else {}
        )
        self.skills_manager = SkillsManager(project_path, skills_config)

        # 初始化工具（主Agent有更多工具）
        tools = self._create_tools(project_path, safety_guard)

        super().__init__(
            agent_id="main",
            system_prompt="",  # 先设置为空，稍后更新
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=kwargs.get("max_iterations", 50),
        )
        
        # 初始化技能（需要在super().__init__之后，因为需要self.tools）
        self._init_skills()
        
        # 获取 Skills 工具名列表（用于提示词）- 在初始化技能之后
        skills_tools_list = self._get_skills_tool_names(self.tools)
        
        # 系统提示（替换占位符，使用 replace 避免大括号转义问题）
        system_prompt = SYSTEM_PROMPT_FOR_MAIN_AGENT.replace('{skills_tools_list}', skills_tools_list)
        example_tool = skills_tools_list.split(',')[0] if ',' in skills_tools_list else "playwright_browser_automation"
        system_prompt = system_prompt.replace('{skills_example}', example_tool)
        
        # 更新系统提示词
        self.system_prompt = system_prompt

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

        # Skills管理器已经在__init__开头初始化了

        # 会话管理器
        self.session_manager = SessionManager(project_path)

        # ReAct循环
        self.react_loop = AsyncReActLoop(
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=kwargs.get("max_iterations", settings.MAX_REACT_ITERATIONS),
            project_path=project_path,
            context_config=settings.context,
        )

    def _get_skills_tool_names(self, tools: Dict[str, Any] = None) -> str:
        """获取Skills相关工具名列表（用于提示词）"""
        if tools is None:
            tools = getattr(self, 'tools', {})
        skill_tools = []
        
        # 动态获取技能名称列表
        skill_names = []
        if hasattr(self, 'skills_manager'):
            skill_names = self.skills_manager.list_enabled_skills()
        
        # 如果无法动态获取，使用后备方法
        if not skill_names:
            # 方法1：从配置获取
            from config import settings
            if hasattr(settings, 'skills') and hasattr(settings.skills, 'skills_metadata'):
                skill_names = list(settings.skills.skills_metadata.keys())
            
            # 方法2：从skills目录获取
            if not skill_names and hasattr(self, 'project_path'):
                import os
                skills_dir = self.project_path / "skills"
                if os.path.exists(skills_dir):
                    for item in os.listdir(skills_dir):
                        if os.path.isdir(os.path.join(skills_dir, item)) and not item.startswith('.'):
                            skill_names.append(item)
        
        # 识别skills工具
        for tool_name in tools.keys():
            # 检查工具名是否包含任何技能名称
            for skill_name in skill_names:
                if skill_name in tool_name:
                    skill_tools.append(tool_name)
                    break
        
        return ', '.join(sorted(skill_tools)) if skill_tools else "无"

    async def _list_skills(self, include_details: bool = False) -> Dict[str, Any]:
        """列出所有可用的skills（支持渐进式披露）

        Args:
            include_details: 是否包含详细参数信息（默认只返回元数据）
        """
        try:
            enabled_list = self.skills_manager.list_enabled_skills()
            skills_info = []

            for skill_name in enabled_list:
                skill_info = self.skills_manager.loaded_skills.get(skill_name)
                if skill_info:
                    # 基础元数据（总是返回）
                    skill_data = {
                        "name": skill_name,
                        "display_name": skill_info.display_name or skill_name,
                        "description": skill_info.description,
                        "trigger_keywords": skill_info.trigger_keywords,
                        "usage_guide": skill_info.usage_guide,
                        "metadata_loaded": skill_info.metadata_loaded,
                        "full_instruction_loaded": skill_info.full_instruction_loaded,
                    }

                    # 如果需要详细信息，加载完整指令
                    if include_details and not skill_info.full_instruction_loaded:
                        self.skills_manager._load_full_instruction(skill_name)
                        skill_info = self.skills_manager.loaded_skills.get(skill_name)

                    # 添加详细信息
                    if include_details and skill_info and skill_info.full_instruction_loaded:
                        schema = self.skills_manager.get_skill_schema(skill_name)
                        if schema:
                            skill_data["parameters"] = [
                                p.name for p in schema.parameters
                            ]
                            skill_data["parameter_details"] = [
                                {
                                    "name": p.name,
                                    "type": str(p.type),
                                    "required": p.required,
                                    "description": p.description,
                                }
                                for p in schema.parameters
                            ]
                            skill_data["examples"] = (
                                schema.examples if hasattr(schema, "examples") else []
                            )

                    skills_info.append(skill_data)

            return {
                "success": True,
                "skills": skills_info,
                "count": len(skills_info),
                "metadata_only": not include_details,
                "token_efficiency_note": "使用include_details=true获取完整信息（消耗更多tokens）",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_skill_info(self, skill_name: str) -> Dict[str, Any]:
        """获取特定skill的详细信息（按需加载完整指令）"""
        try:
            # 确保技能已完全加载
            if skill_name in self.skills_manager.loaded_skills:
                skill_info = self.skills_manager.loaded_skills[skill_name]
                if not skill_info.full_instruction_loaded:
                    self.skills_manager._load_full_instruction(skill_name)

            schema = self.skills_manager.get_skill_schema(skill_name)
            if not schema:
                return {"success": False, "error": f"Skill不存在: {skill_name}"}

            # 获取技能元数据
            skill_info = self.skills_manager.loaded_skills.get(skill_name)

            # 清理描述
            desc = schema.description.strip()
            if desc.startswith("# "):
                desc = desc[2:]
            elif desc.startswith("## "):
                desc = desc[3:]

            params_info = []
            for param in schema.parameters:
                param_info = {
                    "name": param.name,
                    "type": (
                        param.type.__name__
                        if hasattr(param.type, "__name__")
                        else str(param.type)
                    ),
                    "required": param.required,
                    "description": param.description,
                }
                if hasattr(param, "default") and param.default is not None:
                    param_info["default"] = param.default
                params_info.append(param_info)

            result = {
                "success": True,
                "name": skill_name,
                "description": desc,
                "full_md_content": skill_info.full_md_content if skill_info and skill_info.full_md_content else desc,
                "parameters": params_info,
                "examples": schema.examples if hasattr(schema, "examples") else [],
                "loading_info": {"loaded_on_demand": True},
            }

            # 添加元数据信息（如果可用）
            if skill_info:
                result["display_name"] = skill_info.display_name or skill_name
                result["trigger_keywords"] = skill_info.trigger_keywords
                result["usage_guide"] = skill_info.usage_guide
                result["loading_info"]["metadata_loaded"] = skill_info.metadata_loaded
                result["loading_info"][
                    "full_instruction_loaded"
                ] = skill_info.full_instruction_loaded

                # 添加skill对应的工具列表（渐进式披露：让模型知道有哪些工具可用）
                if skill_info.functions:
                    tools_info = []
                    for func_name, func_details in skill_info.functions.items():
                        tool_name = f"{skill_name}_{func_name}"
                        # 直接从 func_details 获取参数信息
                        tool_params = []
                        for param_name, param_details in func_details.get("parameters", {}).items():
                            tool_params.append({
                                "name": param_name,
                                "type": "str",  # 统一使用 str 类型
                                "required": param_details.get("required", False),
                                "description": param_details.get("description", ""),
                                "default": param_details.get("default")
                            })
                        tools_info.append({
                            "name": tool_name,
                            "description": f"执行 {func_name} 操作",
                            "parameters": tool_params,
                            "examples": func_details.get("examples", [])
                        })
                    result["tools"] = tools_info

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _init_skills(self):
        """初始化skills（支持渐进式披露）"""
        if not settings.skills.enabled:
            print("ℹ️ Skills功能已禁用")
            return

        if not settings.skills.auto_discover:
            print("ℹ️ Skills自动发现已禁用")
            return

        # 渐进式披露：启动时只加载元数据
        discovered = self.skills_manager.discover_skills(load_full_instructions=False)
        if not discovered:
            print("ℹ️ 未发现任何Skills")
            return

        print(f"🔍 发现 {len(discovered)} 个Skills（仅元数据）")

        # 打印skills元数据信息
        for skill_name, skill_info in discovered.items():
            status = "✅" if skill_info.metadata_loaded else "⚠️"
            desc = (
                skill_info.description[:50] + "..."
                if len(skill_info.description) > 50
                else skill_info.description
            )
            print(f"   {status} {skill_name}: {desc}")

        # 自动启用在skills_metadata.yaml中配置了元数据的skill
        # 只有配置了元数据的skill才会被启用，符合渐进式披露原则
        configured_skills = list(settings.skills.skills_metadata.keys())
        enabled = [s for s in configured_skills if s in discovered]
        self.skills_manager.enable_skills(enabled)
        print(f"✅ 已自动启用 {len(enabled)} 个Skills（基于skills_metadata.yaml配置）")
        enabled_list = self.skills_manager.list_enabled_skills()
        print(f"✅ 启用 {len(enabled_list)} 个Skills: {', '.join(enabled_list)}")

        # 注册skill工具到注册表并添加到Agent工具字典
        # 渐进式披露：启动时加载完整指令以便注册所有函数
        registry = get_global_registry()
        tool_count = 0
        
        for skill_name in enabled_list:
            # 加载完整指令以发现所有函数
            self.skills_manager._load_full_instruction(skill_name)
            
            skill_info = self.skills_manager.loaded_skills.get(skill_name)
            if not skill_info:
                continue
            
            # 检查是否有多函数支持
            if skill_info.functions:
                # 为每个函数创建独立工具
                for func_name, func_info in skill_info.functions.items():
                    tool_name = f"{skill_name}_{func_name}"
                    
                    # 创建简化的schema
                    from utils.tool_schemas import get_schema
                    schema = get_schema(tool_name, self.skills_manager)
                    
                    # 手动创建schema覆盖参数
                    from utils.tool_registry import ToolSchema, ToolParameter
                    params = []
                    for param_name, param_info in func_info.get("parameters", {}).items():
                        param = ToolParameter(
                            name=param_name,
                            type=str,
                            required=param_info.get("required", False),
                            default=param_info.get("default"),
                            description=param_info.get("description", ""),
                        )
                        params.append(param)
                    
                    schema = ToolSchema(
                        name=tool_name,
                        description=f"{skill_info.description} - 函数: {func_name}",
                        parameters=params,
                        examples=func_info.get("examples", [])
                    )
                    
                    func = self._create_skill_executor(skill_name, func_name)
                    registry.register(func, schema)
                    self.tools[tool_name] = func
                    tool_count += 1
            else:
                # 兼容：单函数skill
                schema = self.skills_manager.get_skill_schema(skill_name)
                if schema:
                    func = self._create_skill_executor(skill_name)
                    registry.register(func, schema)
                    self.tools[skill_name] = func
                    tool_count += 1

        print(f"✅ 已注册 {tool_count} 个Skill工具函数（支持多功能）")

    def _create_skill_executor(self, skill_name: str, func_name: str = None):
        """创建skill执行函数"""

        async def executor(**kwargs):
            return await self.skills_manager.execute_skill(skill_name, func_name=func_name, **kwargs)

        return executor

    def _create_model_caller(self, model_config: Dict):
        """创建模型调用器（支持流式输出）"""

        async def model_caller(messages: List[Dict]) -> str:
            try:
                # 使用提供的配置创建客户端
                api_key = (
                    model_config.get("api_key")
                    or os.getenv("LLM_API_KEY")
                    or os.getenv("OPENAI_API_KEY")
                )
                base_url = (
                    model_config.get("base_url")
                    or os.getenv("LLM_API_URL")
                    or os.getenv("OPENAI_BASE_URL")
                )
                model_name = model_config.get("name") or os.getenv(
                    "LLM_MODEL_NAME", "gpt-4"
                )

                if not api_key:
                    # 回退到简单响应
                    return "错误：未设置API密钥。请设置 LLM_API_KEY 环境变量。"

                client = openai.OpenAI(api_key=api_key, base_url=base_url)

                # 确保消息格式正确
                formatted_messages = []
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role and content:
                        formatted_messages.append({"role": role, "content": content})

                # 流式输出
                print("🤖 模型思考中", end="", flush=True)
                full_response = ""

                stream = client.chat.completions.create(
                    model=model_name,
                    messages=formatted_messages,
                    temperature=model_config.get("temperature", 0.1),
                    max_tokens=model_config.get("max_tokens", 8000),
                    stream=True,  # 启用流式输出
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
                
                # 检查是否为认证错误
                error_str = str(e).lower()
                if "401" in error_str or "authentication" in error_str or "invalid api key" in error_str:
                    print("\n🔑 API认证失败！请检查：")
                    print("1. API密钥是否正确")
                    print("2. 环境变量 LLM_API_KEY 是否设置")
                    print("3. API密钥是否有权限")
                    print("4. API服务是否可用")
                    print("\n💡 建议：")
                    print("- 运行 `export LLM_API_KEY=your_api_key` 设置环境变量")
                    print("- 检查API密钥是否过期或被撤销")
                    print("- 确认API服务端点是否正确")
                    # 抛出异常，停止执行
                    raise RuntimeError(f"API认证失败: {error_msg}")
                
                # 检查是否为网络错误
                elif "connection" in error_str or "timeout" in error_str or "network" in error_str:
                    print("\n🌐 网络连接失败！请检查：")
                    print("1. 网络连接是否正常")
                    print("2. API服务端点是否可达")
                    print("3. 防火墙或代理设置")
                    print("\n💡 建议：")
                    print("- 检查网络连接")
                    print("- 确认API服务URL是否正确")
                    print("- 尝试使用 `curl` 测试API端点")
                    # 抛出异常，停止执行
                    raise RuntimeError(f"网络连接失败: {error_msg}")
                
                # 检查是否为配额错误
                elif "quota" in error_str or "limit" in error_str or "rate limit" in error_str:
                    print("\n📊 API配额或限制错误！请检查：")
                    print("1. API配额是否用完")
                    print("2. 是否达到速率限制")
                    print("3. 账户余额是否充足")
                    print("\n💡 建议：")
                    print("- 检查API使用情况")
                    print("- 等待配额重置")
                    print("- 升级API套餐")
                    # 抛出异常，停止执行
                    raise RuntimeError(f"API配额错误: {error_msg}")
                
                # 其他错误，提供通用建议
                else:
                    print("\n⚠️  模型调用遇到问题！请检查：")
                    print("1. API服务状态")
                    print("2. 模型名称是否正确")
                    print("3. 请求参数是否有效")
                    print("\n💡 建议：")
                    print("- 查看错误详情")
                    print("- 检查API文档")
                    print("- 联系技术支持")
                    # 抛出异常，停止执行
                    raise RuntimeError(f"模型调用错误: {error_msg}")

        return model_caller

    def _create_tools(self, project_path: Path, safety_guard) -> Dict[str, Any]:
        """创建工具集并注册到工具注册表"""

        atomic_tools = AtomicTools(project_path, safety_guard)
        code_tools = CodeTools(project_path, safety_guard)
        web_tools = WebTools(project_path, safety_guard)
        todo_tools = TodoTools(project_path, safety_guard)
        incremental_tools = IncrementalTools(project_path, safety_guard)
        
        # 保存web_tools引用以便后续清理
        self.web_tools = web_tools
        
        # 包装fetch_url函数以保存结果
        async def wrapped_fetch_url(url: str, timeout: Optional[int] = None, max_content_length: int = 100000, **kwargs) -> Dict[str, Any]:
            # 调用原始fetch_url函数
            result = await web_tools.fetch_url(url, timeout, max_content_length, **kwargs)
            
            # 如果成功获取到内容，保存到上下文文件
            if result.get("success") and "content" in result:
                try:
                    # 创建上下文目录
                    context_dir = project_path / ".aacode" / "context"
                    context_dir.mkdir(parents=True, exist_ok=True)
                    
                    # 保存结果到web_fetch_result.txt
                    result_file = context_dir / "web_fetch_result.txt"
                    result_file.write_text(result["content"], encoding="utf-8")
                    print(f"📁 已保存web_fetch结果到: {result_file.relative_to(project_path)}")
                except Exception as e:
                    print(f"⚠️  保存web_fetch结果失败: {str(e)}")
            
            return result
        """创建工具集并注册到工具注册表"""

        atomic_tools = AtomicTools(project_path, safety_guard)
        code_tools = CodeTools(project_path, safety_guard)
        web_tools = WebTools(project_path, safety_guard)
        todo_tools = TodoTools(project_path, safety_guard)
        incremental_tools = IncrementalTools(project_path, safety_guard)
        
        # 保存web_tools引用以便后续清理
        self.web_tools = web_tools

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
            "fetch_url": wrapped_fetch_url,
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
            # Skills查询工具
            "list_skills": self._list_skills,
            "get_skill_info": self._get_skill_info,
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
            tools.update(
                {
                    "run_in_sandbox": sandbox_tools.run_in_sandbox,
                    "install_package": sandbox_tools.install_package,
                    "call_mcp": sandbox_tools.call_mcp,
                }
            )
        except:
            pass  # 沙箱工具可选

        # 多模态工具（图片/视频理解）
        multimodal_tools = MultimodalTools(project_path)
        if getattr(settings.multimodal, "enabled", True):
            tools.update(
                {
                    "understand_image": multimodal_tools.understand_image,
                    "understand_video": multimodal_tools.understand_video,
                    "understand_ui_design": multimodal_tools.understand_ui_design,
                    "analyze_image_consistency": multimodal_tools.analyze_image_consistency,
                }
            )

        # 注册工具到全局注册表
        registry = get_global_registry()
        registered_count = 0

        for tool_name, tool_func in tools.items():
            # 使用动态schema获取函数
            schema = get_schema(tool_name, self.skills_manager)
            if schema:
                registry.register(tool_func, schema)
                registered_count += 1

        # 注册多模态工具的schema
        from utils.tool_registry import ToolSchema, ToolParameter
        multimodal_schema = get_multimodal_tools_schema()
        for schema_dict in multimodal_schema:
            func_name = schema_dict["function"]["name"]
            if func_name in tools:
                func_def = schema_dict["function"]
                params_def = func_def.get("parameters", {})
                properties = params_def.get("properties", {})
                required_fields = params_def.get("required", [])
                
                # 将字典转换为 ToolSchema
                schema = ToolSchema(
                    name=func_name,
                    description=func_def.get("description", ""),
                    parameters=[
                        ToolParameter(
                            name=pname,
                            type=str,
                            required=pname in required_fields,
                            description=properties[pname].get("description", "")
                        )
                        for pname in properties.keys()
                    ]
                )
                registry.register(tools[func_name], schema)
                registered_count += 1

        print(f"✅ 已注册 {registered_count} 个工具到注册表")

        return tools

    async def execute(
        self,
        task: str,
        init_instructions: str = "",
        task_dir: Optional[Path] = None,
        max_iterations: int = 20,
        project_analysis: str = "",
        todo_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
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
            analysis_section = (
                f"\n\n项目结构分析结果（类方法映射）:\n{project_analysis[:1500]}..."
            )
            print("📊 项目分析结果已集成到系统提示中")

        full_system_prompt = f"{self.system_prompt}{analysis_section}\n\n项目初始化指令:\n{init_instructions}"
        self.conversation_history[0]["content"] = full_system_prompt

        # 添加任务描述
        self.conversation_history.append(
            {
                "role": "user",
                "content": f"任务：{task}\n\n请参考项目结构分析结果，制定计划并执行。",
            }
        )

        # 运行ReAct循环
        try:
            result = await self.react_loop.run(
                initial_prompt=full_system_prompt,
                task_description=task,
                todo_manager=todo_manager,
            )
        except asyncio.CancelledError:
            # 任务被取消，重新抛出以便上层处理
            raise
        except Exception as e:
            # 记录错误
            print(f"❌ ReAct循环执行失败: {e}")
            import traceback
            traceback.print_exc()
            # 重新抛出异常
            raise
        finally:
            # 确保资源被清理，即使发生异常
            try:
                if hasattr(self, 'web_tools'):
                    await self.web_tools.cleanup()
            except Exception as e:
                print(f"⚠️  清理web_tools时出错: {e}")

        # 更新统计
        self.iterations = len(self.react_loop.steps)

        return {
            **result,
            "session_id": session_id,
            "agent_stats": self.get_stats(),
            "execution_time": asyncio.get_event_loop().time() - self.start_time,
        }

    async def delegate_task(
        self,
        task_description: str,
        agent_type: str = "general",
        context_strategy: str = "isolated",
    ) -> Dict[str, Any]:
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
            "result": None,
        }

        # 使用多Agent系统委托
        delegation_result = await self.multi_agent_system.delegate_task(
            task_description=task_description,
            task_type=agent_type,
            context_strategy=context_strategy,
        )

        self.tasks[task_id]["status"] = "delegated"
        self.tasks[task_id]["delegation_result"] = delegation_result

        return {
            "task_id": task_id,
            "status": "delegated",
            "delegation_result": delegation_result,
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
            "created_at": task["created_at"],
        }

    async def create_sub_agent(
        self, agent_type: str = "code", capabilities: Optional[List[str]] = None
    ) -> Dict[str, Any]:
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
            max_iterations=self.max_iterations,
        )

        self.sub_agents[agent_id] = sub_agent

        return {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": "created",
            "capabilities": capabilities if capabilities is not None else ["general"],
        }

    async def list_mcp_tools(self) -> Dict[str, Any]:
        """列出所有MCP工具"""
        try:
            tools_result = await self.mcp_manager.list_available_tools()
            return {
                "success": True,
                "tools": tools_result.get("tools", {}),
                "count": tools_result.get("count", 0),
                "connected_servers": tools_result.get("connected_servers", []),
            }
        except Exception as e:
            return {"error": f"获取MCP工具列表失败: {str(e)}"}

    async def call_mcp_tool(
        self, tool_name: str, arguments: Optional[Dict] = None
    ) -> Dict[str, Any]:
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

    async def new_session(
        self, task: str, title: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建新会话"""
        try:
            session_id = await self.session_manager.create_session(task, title)
            return {
                "success": True,
                "session_id": session_id,
                "message": "新会话已创建",
            }
        except Exception as e:
            return {"error": f"创建会话失败: {str(e)}"}

    async def continue_session(
        self, message: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
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
                "conversation_preview": await self.session_manager.get_conversation_history(),
            }
        except Exception as e:
            return {"error": f"继续会话失败: {str(e)}"}

    async def list_sessions(self) -> Dict[str, Any]:
        """列出所有会话"""
        try:
            sessions = await self.session_manager.list_sessions()
            return {"success": True, "sessions": sessions, "count": len(sessions)}
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
                    "message": "会话切换成功",
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
                    "message": "会话已删除",
                }
            else:
                return {"error": f"会话不存在: {session_id}"}
        except Exception as e:
            return {"error": f"删除会话失败: {str(e)}"}

    async def get_conversation_history(self, max_length: int = 10) -> Dict[str, Any]:
        """获取对话历史"""
        try:
            history = await self.session_manager.get_conversation_history(max_length)
            return {"success": True, "history": history}
        except Exception as e:
            return {"error": f"获取对话历史失败: {str(e)}"}

    # 移除复杂规划功能，使用ReAct内置的动态规划
    # 相关的create_plan、execute_plan_step、get_plan_status等方法已删除

    async def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        try:
            stats = self.session_manager.get_session_stats()
            return {"success": True, "stats": stats}
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
                    cwd=self.project_path,
                )
                if result.returncode == 0:
                    git_status["changed_files"] = (
                        len(result.stdout.strip().split("\n"))
                        if result.stdout.strip()
                        else 0
                    )
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
                "active_tasks": len(
                    [t for t in self.tasks.values() if t["status"] != "completed"]
                ),
                "sub_agents": len(self.sub_agents),
            }

        except Exception as e:
            return {"error": str(e)}
    
    def __del__(self):
        """析构函数，确保资源被清理"""
        try:
            if hasattr(self, 'web_tools'):
                # 尝试同步清理
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，安排异步清理
                    asyncio.create_task(self.web_tools.cleanup())
                else:
                    # 否则同步清理
                    loop.run_until_complete(self.web_tools.cleanup())
        except:
            pass  # 忽略析构函数中的错误
