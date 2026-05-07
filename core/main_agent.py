# 主Agent
# core/main_agent.py
"""
主Agent实现，负责协调任务和委托子任务
"""

import asyncio
import json
import re
import sys
from aacode.i18n import t
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import os
import subprocess
import openai
import anthropic

# ─── 流式输出架构说明 ───────────────────────────────────────────
# 
# 数据流：Python stdout → Rust read_line() → Tauri emit → 前端 JS
#
# 两种输出模式（由 _is_tty 决定）：
#   1. TTY 模式（CLI 终端直接运 lines）：
#      - print(text, end="") 逐字追加，不加换 lines，终端实时显示
#      -  user在终端直接看到流式输出
#
#   2. 管道模式（Tauri 桌面客户端通过子进程调 with ）：
#      - Rust 端 with  read_line() 按 lines读取 stdout
#      - read_line() 需要 \n 才能返回一 lines，所以 print(text) 必须加换 lines
#      - 但模型 token 本身可能包含 \n（如表格 lines间换 lines），这个 \n 会和
#        print 加的 \n 混淆，导致 Rust 端无法区分
#      - 解决方案：_stream_print 在管道模式下将 token 中的 \n 转义为 \x00，
#        Rust 端 read_line 后 trim 掉 print 加的 \n，再将 \x00 还原为 \n
#      - 这样前端收到的 content 就是模型的原始 token，换 lines信息不失真
#
# 系统日志 lines（如 "🤖 模型思考中"、"📋 Observation:" 等）：
#   - 直接 with  print() 输出，不经过 _stream_print
#   - Rust 端 trim 后发送给前端，前端通过 emoji 前缀识别并加 \n 分 lines
#   - 注意：不要 with  _stream_print 输出系统标记 lines，否则 \x00 转义会干扰前端识别
#
# ⚠️ 重要：不要修改 TTY 模式下的 end=""  lines为，这是终端流式显示所必需的
# ⚠️ 重要：不要去掉管道模式下的 \x00 转义，否则表格等多 lines内容会渲染失败
# ─────────────────────────────────────────────────────────────────

_is_tty = sys.stdout.isatty()

def _stream_print(text, newline_after=False):
    """
    流式输出模型 token。
    
    - TTY 模式：逐字追加（end=""），终端实时显示
    - 管道模式：token 中 \\n 转义为 \\x00 后 print（带换 lines），
      Rust read_line() 读取后还原 \\x00 → \\n，去掉 print 加的末尾 \\n
    
    Only for model streaming token output. System marker lines (emoji prefix) should use print() directly.
    """
    if _is_tty:
        print(text, end="", flush=True)
    else:
        # 管道模式：转义 token 中的 \n 为 \x00，避免和 print 自动加的 \n 混淆
        # Rust 端 read_line() 读到一 lines后：trim 末尾 \n → 还原 \x00 → \n → 发送给前端
        escaped = text.replace('\n', '\x00')
        print(escaped, flush=True)
    if newline_after and _is_tty:
        print()

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from core.agent import BaseAgent
    from core.react_loop import AsyncReActLoop
    from core.multi_agent import MultiAgentSystem
    from core.prompts import SYSTEM_PROMPT_FOR_MAIN_AGENT
    from tools.atomic_tools import AtomicTools
    from tools.code_tools import CodeTools
    from tools.sandbox_tools import SandboxTools
    from tools.web_tools import WebTools
    from tools.todo_tools import TodoTools
    from utils.mcp_manager import MCPManager
    from utils.session_manager import SessionManager
    from utils.tool_registry import get_global_registry
    from utils.tool_schemas import get_all_schemas, get_schema
    from tools.skills_tools import SkillsManager, SkillInfo
    from tools.multimodal_tools import MultimodalTools, get_multimodal_tools_schema
    from core.sub_agent import SubAgent
    from config import settings
else:
    from .agent import BaseAgent
    from .react_loop import AsyncReActLoop
    from .multi_agent import MultiAgentSystem
    from .prompts import SYSTEM_PROMPT_FOR_MAIN_AGENT
    from ..tools.atomic_tools import AtomicTools
    from ..tools.code_tools import CodeTools
    from ..tools.sandbox_tools import SandboxTools
    from ..tools.web_tools import WebTools
    from ..tools.todo_tools import TodoTools
    from ..utils.mcp_manager import MCPManager
    from ..utils.session_manager import SessionManager
    from ..utils.tool_registry import get_global_registry
    from ..utils.tool_schemas import get_all_schemas, get_schema
    from ..tools.skills_tools import SkillsManager, SkillInfo
    from ..tools.multimodal_tools import MultimodalTools, get_multimodal_tools_schema
    from .sub_agent import SubAgent
    from ..config import settings


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

        # initialized模型调用器
        model_caller = self._create_model_caller(model_config)

        # 先initializedskills_manager，因为_create_tools需要它
        self.skills_manager = SkillsManager(project_path)

        # initialized工具（主Agent有更多工具）
        tools = self._create_tools(project_path, safety_guard)

        super().__init__(
            agent_id="main",
            system_prompt="",  # 先设置为空，稍后更新
            model_caller=model_caller,
            tools=tools,
            context_manager=context_manager,
            max_iterations=kwargs.get("max_iterations", 50),
        )

        # initialized技能（需要在super().__init__之后，因为需要self.tools）
        self._init_skills()

        # 生成 Skills 列表（for 系统提示词）
        skills_list = self.skills_manager.get_skills_list_for_prompt()

        # 系统提示（替换占位符）
        system_prompt = SYSTEM_PROMPT_FOR_MAIN_AGENT.replace(
            "{skills_list}", skills_list
        )

        # 注入项目目录信息到系统提示词
        system_prompt += f"\n\n## Working Directory\nYour current working directory is: {project_path.absolute()}\nAll file operations should use paths relative to this directory."

        # 更新系统提示词
        self.system_prompt = system_prompt

        self.project_path = project_path
        self.safety_guard = safety_guard

        # 多Agent系统
        self.multi_agent_system = MultiAgentSystem(self, context_manager)

        # SubAgent注册表
        self.sub_agents: Dict[str, Any] = {}

        # 任务跟踪
        self.tasks: Dict[str, Dict] = {}

        # MCP管理器
        self.mcp_manager = MCPManager(project_path)

        # Skills管理器已经在__init__开头initialized了

        # 会话管理器
        self.session_manager = SessionManager(project_path)

        # ReAct循环
        self.react_loop = AsyncReActLoop(
            model_caller=model_caller,
            tools=self.tools,
            context_manager=context_manager,
            max_iterations=kwargs.get("max_iterations", settings.MAX_REACT_ITERATIONS),
            project_path=project_path,
            context_config=settings.context,
        )

    async def _finalize_task(self, summary: str, **kwargs) -> Dict[str, Any]:
        """结束当前任务"""
        return {"status": "completed", "summary": summary}

    # ------------------------------------------------------------------ #
    #  run_skills  —  统一技能入口，三种模式（仿 fastclaw）
    # ------------------------------------------------------------------ #

    _LIST_MODES = {None, "", "__list__", "list", "--list", "-l", "/list", "ls"}
    _INFO_MODES = {"__info__", "info", "--info", "-i", "/info"}

    async def _run_skills(self, skill_name: str = None, params: dict = None) -> str:
        """
        统一技能入口，三种模式：

          1. run_skills("__list__")                        — 列出所有技能
          2. run_skills("__info__", {"skill_name":"pandas"})— 查看技能详情
          3. run_skills("pandas", {"code":"df.describe()"}) — 执行技能

          多函数 skill 在 params 中传 "func":
            run_skills("playwright", {"func":"browser_automation", "url":"..."})
        """
        if not hasattr(self, 'skills_manager'):
            return "Error: Skills manager not initialized"
        if not self.skills_manager.loaded_skills:
            self._init_skills()

        params = params or {}
        sname = skill_name.strip() if skill_name else None

        if not sname:
            sname = params.pop("skill_name", None) or params.pop("name", None)
        if sname and isinstance(sname, str):
            sname = sname.strip()

        # ---- help 模式 ----
        if sname == "help":
            return self._run_skills_help()

        # ---- 模式1: 列出全部 skill ----
        if sname in self._LIST_MODES:
            return self._format_skills_list()

        # ---- 模式2: 查看 skill 详情 ----
        if sname in self._INFO_MODES:
            return self._format_skill_detail(params)

        # ---- 模式3: 执行 skill ----
        if sname not in self.skills_manager.loaded_skills:
            return f"Error: Skill '{skill_name}' not found"
        if sname not in self.skills_manager.enabled_skills:
            return f"Error: Skill '{skill_name}' not enabled"

        func_name = params.pop("func", None)
        try:
            result = await self.skills_manager.execute_skill(
                sname, func_name=func_name, **params
            )
            if isinstance(result, dict):
                if result.get("success"):
                    return str(result.get("result", result))
                return f"Error: {result.get('error', str(result))}"
            return str(result)
        except Exception as e:
            return f"Error executing skill '{skill_name}': {str(e)}"

    # ---- 辅助方法 ----

    def _run_skills_help(self) -> str:
        return (
            "run_skills — 三种模式:\n\n"
            "1. 列表: run_skills(\"__list__\")\n"
            "2. 详情: run_skills(\"__info__\", {\"skill_name\": \"pandas\"})\n"
            "3. 执行: run_skills(\"pandas\", {\"code\": \"df.describe()\"})\n\n"
            "多函数 skill: 'func' 放在 params 中\n"
            "  run_skills(\"playwright\", {\"func\": \"browser_automation\", \"url\": \"...\"})"
        )

    def _format_skills_list(self) -> str:
        enabled = self.skills_manager.list_enabled_skills()
        if not enabled:
            return "暂无可用技能"
        lines = ["可用技能列表:"]
        for name in enabled:
            info = self.skills_manager.loaded_skills.get(name)
            if info:
                lines.append(f"- {name}: {info.description}")
        return "\n".join(lines)

    def _format_skill_detail(self, params: dict) -> str:
        target = params.get("skill_name") or params.get("name") or ""
        if not target:
            return "Error: skill_name is required for __info__ mode"
        if target not in self.skills_manager.loaded_skills:
            return f"Error: Skill '{target}' not found"
        self.skills_manager._load_full_instruction(target)
        info = self.skills_manager.loaded_skills[target]
        md_path = Path(info.skill_dir) / "SKILL.md"
        if md_path.exists():
            return md_path.read_text(encoding="utf-8")
        return f"Skill: {target}\nDescription: {info.description}"

    def _init_skills(self):
        """初始化 skills——从 SKILL.md 自动发现，不依赖 yaml，不注册 per-function 工具"""
        if not settings.skills.enabled:
            print(t("skills.disabled"))
            return

        if not settings.skills.auto_discover:
            print(t("skills.auto_discover_disabled"))
            return

        discovered = self.skills_manager.discover_skills(load_full_instructions=False)
        if not discovered:
            print(t("skills.none_found"))
            return

        print(t("skills.discovered", count=len(discovered)))

        for skill_name, skill_info in discovered.items():
            desc = (
                skill_info.description[:50] + "..."
                if len(skill_info.description) > 50
                else skill_info.description
            )
            print(t("skills.skill_item", name=skill_name, desc=desc))

        # 自动启用所有发现的 skill
        enabled = list(discovered.keys())
        self.skills_manager.enable_skills(enabled)
        print(t("skills.enabled_count", count=len(enabled)))
        enabled_list = self.skills_manager.list_enabled_skills()
        print(t("skills.enabled_list", count=len(enabled_list), list=', '.join(enabled_list)))

        # 预加载所有技能的完整信息（供 __info__ 和 execute 使用）
        for skill_name in enabled_list:
            self.skills_manager._load_full_instruction(skill_name)

        print(t("skills.registered_tools", count=0))

    def _create_model_caller(self, model_config: Dict):
        """创建模型调 with 器（支持流式输出、多网关、原生 Function Calling）"""

        from aacode.utils.tool_adapter import to_openai_tools, to_anthropic_tools
        from aacode.utils.tool_schemas import get_all_schemas

        async def model_caller(messages: List[Dict]) -> Dict[str, Any]:
            """调 with 模型，返回 {"text": str, "tool_calls": list}"""
            native_tools = None
            try:
                all_schemas = get_all_schemas()
                if all_schemas:
                    gateway = model_config.get("gateway", "openai")
                    if gateway == "anthropic":
                        native_tools = to_anthropic_tools(all_schemas)
                    else:
                        native_tools = to_openai_tools(all_schemas)
            except Exception:
                native_tools = None

            try:
                # 使 with 提供的配置创建客户端
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
                model_name = (
                    model_config.get("name")
                    or os.getenv("LLM_MODEL_NAME", "deepseek-chat")
                    or "deepseek-chat"
                )
                gateway = model_config.get("gateway", "openai")

                if not api_key:
                    # API Key 未设置，抛出异常让 react_loop 显示错误
                    error_msg = "❌ API Key not configured! Please configure the API Key in client Settings, or run 'aacode init' to set it up."
                    print(error_msg)
                    raise RuntimeError(error_msg)

                # 确保base_url不为None，根据模型名称和网关类型设置默认URL
                if not base_url:
                    model_lower = model_name.lower() if model_name else ""
                    if gateway == "anthropic":
                        # 根据模型选择正确的Anthropic兼容端点
                        if "minimax" in model_lower:
                            base_url = "https://api.minimax.chat/anthropic"
                        elif "deepseek" in model_lower:
                            base_url = "https://api.deepseek.com/anthropic"
                        elif "kimi" in model_lower or "moonshot" in model_lower:
                            base_url = "https://api.moonshot.cn/anthropic"
                        elif "claude" in model_lower:
                            base_url = "https://api.anthropic.com"
                        else:
                            base_url = "https://api.anthropic.com"
                    else:
                        if "minimax" in model_lower:
                            base_url = "https://api.minimax.chat/v1"
                        elif "deepseek" in model_lower:
                            base_url = "https://api.deepseek.com/v1"
                        elif "kimi" in model_lower or "moonshot" in model_lower:
                            base_url = "https://api.moonshot.cn/v1"
                        elif "claude" in model_lower:
                            base_url = "https://api.openai.com/v1"
                        else:
                            base_url = "https://api.openai.com/v1"

                # 根据网关类型创建客户端
                if gateway == "anthropic":
                    return await self._call_anthropic_api(
                        api_key, base_url, model_name, messages, model_config,
                        tools=native_tools,
                    )
                else:
                    return await self._call_openai_api(
                        api_key, base_url, model_name, messages, model_config,
                        tools=native_tools,
                    )

            except Exception as e:
                # 详细的错误信息
                error_msg = f"Model call failed: {str(e)}"
                print(f"\n❌ {error_msg}")

                # 检查是否为认证错误
                error_str = str(e).lower()
                if (
                    "401" in error_str
                    or "authentication" in error_str
                    or "invalid api key" in error_str
                ):
                    print("\n🔑 API authentication failed! Check:")
                    print("1. Is API key correct")
                    print("2. Is LLM_API_KEY env var set")
                    print("3. Does API key have proper permissions")
                    print("4. Is API service available")
                    print("\n💡 Suggestions:")
                    print("- Run `export LLM_API_KEY=your_api_key`")
                    print("- Check if API key is expired or revoked")
                    print("- Verify API endpoint is correct")
                    # 抛出异常，停止execute
                    raise RuntimeError(f"API authentication failed: {error_msg}")

                # 检查是否为网络错误
                elif (
                    "connection" in error_str
                    or "timeout" in error_str
                    or "network" in error_str
                ):
                    print("\n🌐 Network connection failed! Check:")
                    print("1. Is network working")
                    print("2. Is API endpoint reachable")
                    print("3. Firewall or proxy settings")
                    print("\n💡 Suggestions:")
                    print("- Check network connection")
                    print("- Verify API service URL is correct")
                    print("- Try `curl` to test API endpoint")
                    # 抛出异常，停止execute
                    raise RuntimeError(f"Network connection failed: {error_msg}")

                # 检查是否为配额错误
                elif (
                    "quota" in error_str
                    or "limit" in error_str
                    or "rate limit" in error_str
                ):
                    print("\n📊 API quota or limit error! Check:")
                    print("1. Is API quota exhausted")
                    print("2. Is rate limit reached")
                    print("3. Is account balance sufficient")
                    print("\n💡 Suggestions:")
                    print("- Check API usage")
                    print("- Wait for quota reset")
                    print("- Upgrade API plan")
                    # 抛出异常，停止execute
                    raise RuntimeError(f"API quota error: {error_msg}")

                # 其他错误，提供通用建议
                else:
                    print("\n⚠️  Model call error! Check:")
                    print("1. API service status")
                    print("2. Is model name correct")
                    print("3. Are request parameters valid")
                    print("\n💡 Suggestions:")
                    print("- Check error details")
                    print("- Check API documentation")
                    print("- Contact technical support")
                    # 抛出异常，停止execute
                    raise RuntimeError(f"Model call error: {error_msg}")

        return model_caller

    async def _call_openai_api(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        messages: List[Dict],
        model_config: Dict,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """调 with OpenAI兼容API，返回 {"text": str, "tool_calls": list}"""
        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

        # 确保消息格式正确
        formatted_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            entry = {"role": role, "content": content}
            if "tool_calls" in msg:
                entry["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg:
                entry["tool_call_id"] = msg["tool_call_id"]
            if "reasoning_content" in msg:
                entry["reasoning_content"] = msg["reasoning_content"]
            if role and (content or msg.get("tool_calls") or msg.get("tool_call_id")):
                formatted_messages.append(entry)

        # 处理不同模型的temperature限制
        temperature = model_config.get("temperature", 0.1)
        model_lower = model_name.lower() if model_name else ""
        # Kimi模型只接受temperature=1
        if "kimi" in model_lower or "moonshot" in model_lower:
            temperature = 1.0

        # 流式输出
        if _is_tty:
            _stream_print(t("model.thinking"))
        full_response = ""
        tool_calls_accumulator: Dict[int, Dict[str, str]] = {}
        self._tool_call_progress: Dict[int, Dict] = {}

        create_kwargs: dict = {
            "model": model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": model_config.get("max_tokens", 8000),
            "stream": True,
        }
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = "auto"

        stream = await client.chat.completions.create(**create_kwargs)

        # ─── 流式响应处理 ───
        thinking_printed = False
        thinking_content = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta
            # 处理 reasoning_content
            reasoning = getattr(delta, 'reasoning_content', None)
            if reasoning:
                if not thinking_printed:
                    print("💭 Thinking process:", flush=True)
                    thinking_printed = True
                thinking_content += reasoning
                _stream_print(reasoning)
            # 处理正常内容
            if delta.content is not None:
                if thinking_printed:
                    print("\nThought: ", end="", flush=True) if _is_tty else print("\nThought: ", flush=True)
                    thinking_printed = False
                full_response += delta.content
                _stream_print(delta.content)
            # 处理 tool_calls (流式累积)
            if delta.tool_calls:
                if not hasattr(self, '_tool_call_progress'):
                    self._tool_call_progress: Dict[int, Dict] = {}
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_accumulator:
                        tool_calls_accumulator[idx] = {
                            "id": "",
                            "function_name": "",
                            "function_arguments": "",
                        }
                    acc = tool_calls_accumulator[idx]
                    if idx not in self._tool_call_progress:
                        self._tool_call_progress[idx] = {"name": "", "last_report": 0}
                    progress = self._tool_call_progress[idx]
                    if tc_delta.id:
                        acc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            acc["function_name"] += tc_delta.function.name
                            if not progress.get("_name_printed"):
                                progress["name"] += tc_delta.function.name
                                fn = progress["name"]
                                print(f"🛠️ Building tool call: {fn}(...)", flush=True)
                                progress["_name_printed"] = True
                        if tc_delta.function.arguments:
                            chunk = tc_delta.function.arguments
                            acc["function_arguments"] += chunk
                            current_len = len(acc["function_arguments"])
                            if current_len - progress["last_report"] >= 500:
                                fn = progress["name"] or "?"
                                print(f"  ⏳ building args ({current_len} chars for {fn})", flush=True)
                                progress["last_report"] = current_len - (current_len % 500)

        if _is_tty:
            print()  # CLI newline

        # ─── 构建 tool_calls 列表 ───
        tool_calls_list = []
        for idx in sorted(tool_calls_accumulator.keys()):
            tc = tool_calls_accumulator[idx]
            if tc["function_name"]:
                tool_calls_list.append({
                    "id": tc["id"],
                    "name": tc["function_name"],
                    "arguments": tc["function_arguments"],
                })

        # ─── thinking 内容拼接到返回值 ───
        if thinking_content:
            clean_response = full_response.lstrip('\n')
            # 剥离模型 content 中可能自带的思考前缀（各模型表现不同）
            thinking_prefixes = [
                r'^Thought[:\s\n]*', r'^💭\s*Thinking process[:\s\n]*',
                r'^THINKING[:\s\n]*', r'^thinking[:\s\n]*', r'^reasoning[:\s\n]*',
            ]
            for pat in thinking_prefixes:
                clean_response = re.sub(pat, '', clean_response, flags=re.IGNORECASE).lstrip('\n')
            if clean_response.strip():
                full_response = f"💭 Thinking process:\n{thinking_content}\n\nThought: {clean_response}"
            else:
                full_response = f"💭 Thinking process:\n{thinking_content}"

        return {
            "text": full_response if full_response is not None else "",
            "tool_calls": tool_calls_list,
            "reasoning_content": thinking_content if thinking_content else None,
        }

    async def _call_anthropic_api(
        self,
        api_key: str,
        base_url: str,
        model_name: str,
        messages: List[Dict],
        model_config: Dict,
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """调 with 真正的Anthropic兼容API（如MiniMax），返回 {"text": str, "tool_calls": list}"""
        # 处理Anthropic兼容端点的URL格式调整
        # MiniMax、DeepSeek、Kimi的Anthropic兼容端点需要特殊处理
        adjusted_base_url = base_url

        # 检查是否是Anthropic兼容端点（MiniMax、DeepSeek、Kimi）
        if base_url and any(
            provider in base_url.lower()
            for provider in ["minimax", "deepseek", "moonshot"]
        ):
            # Anthropic SDK会自动添加/v1/messages，所以我们需要确保base_url正确
            if base_url.endswith("/v1"):
                # /v1 会导致重复的/v1路径，改为 /anthropic
                adjusted_base_url = base_url[:-3] + "/anthropic"
                print(t("net.adjust_url_dup", old=base_url, new=adjusted_base_url))
            elif base_url.endswith("/v1/anthropic"):
                # 已经是 /v1/anthropic，这会导致重复/v1，需要调整
                # Anthropic SDK会添加/v1/messages，所以实际路径会是 /v1/anthropic/v1/messages
                # 应该改为 /anthropic
                adjusted_base_url = base_url.replace("/v1/anthropic", "/anthropic")
                print(t("net.adjust_url_path", old=base_url, new=adjusted_base_url))
            elif not base_url.endswith("/anthropic"):
                # 确保以 /anthropic 结尾
                adjusted_base_url = base_url.rstrip("/") + "/anthropic"
                print(t("net.add_anthropic_path", old=base_url, new=adjusted_base_url))

        # 使 with  AsyncAnthropic 客户端（对标 OpenAI 的 AsyncOpenAI）
        client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=adjusted_base_url,
        )

        # Anthropic格式的消息转换
        system_message = ""
        formatted_messages = []

        def _make_anth_content(content_val, content_type="text", **extra) -> dict:
            block = {"type": content_type}
            if content_type == "text":
                block["text"] = str(content_val) if content_val else ""
            elif content_type == "tool_result":
                block["tool_use_id"] = extra.get("tool_use_id", "")
                block["content"] = str(content_val) if content_val else ""
            elif content_type == "tool_use":
                block["id"] = extra.get("id", "")
                block["name"] = extra.get("name", "")
                block["input"] = extra.get("input", {})
            return block

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_message = content
                continue
            if role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                formatted_messages.append({
                    "role": "user",
                    "content": [_make_anth_content(content, "tool_result", tool_use_id=tool_call_id)],
                })
                continue
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    blocks = []
                    if content:
                        blocks.append(_make_anth_content(content, "text"))
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        args = func.get("arguments", "{}")
                        if isinstance(args, str):
                            try: args = json.loads(args)
                            except json.JSONDecodeError: args = {}
                        blocks.append(_make_anth_content(None, "tool_use",
                            id=tc.get("id", ""), name=func.get("name", ""), input=args))
                    formatted_messages.append({"role": "assistant", "content": blocks})
                elif content:
                    formatted_messages.append({"role": "assistant", "content": content})
                continue
            if content:
                formatted_messages.append({"role": "user", "content": content})

        # Async 流式调 with 
        if _is_tty:
            _stream_print(t("model.thinking"))
        response = ""
        thinking_content = ""
        tool_calls_list = []

        async def _do_stream():
            nonlocal response, thinking_content, tool_calls_list
            stream_kwargs = {
                "model": model_name,
                "max_tokens": model_config.get("max_tokens", 8000),
                "temperature": model_config.get("temperature", 0.1),
                "messages": formatted_messages,
            }
            if system_message:
                stream_kwargs["system"] = system_message
            if tools:
                stream_kwargs["tools"] = tools

            async with client.messages.stream(**stream_kwargs) as stream:
                thinking_printed = False
                async for event in stream:
                    event_type = getattr(event, 'type', '')
                    if event_type == 'content_block_start':
                        block = getattr(event, 'content_block', None)
                        if block:
                            bt = getattr(block, 'type', '')
                            if bt == 'thinking':
                                if not thinking_printed:
                                    print("💭 Thinking process:", flush=True)
                                    thinking_printed = True
                            elif bt == 'text' and thinking_printed:
                                print("\nThought: ", end="", flush=True) if _is_tty else print("\nThought: ", flush=True)
                                thinking_printed = False
                    elif event_type == 'content_block_delta':
                        delta = getattr(event, 'delta', None)
                        if delta:
                            dt = getattr(delta, 'type', '')
                            if dt == 'thinking_delta':
                                chunk = getattr(delta, 'thinking', '')
                                if chunk: thinking_content += chunk; _stream_print(chunk)
                            elif dt == 'text_delta':
                                chunk = getattr(delta, 'text', '')
                                if chunk: response += chunk; _stream_print(chunk)

                #  with  get_final_message Get 完整的 tool_use（非流式解析，可靠）
                final = await stream.get_final_message()
                for block in final.content:
                    if getattr(block, 'type', '') == 'tool_use':
                        tool_calls_list.append({
                            "id": getattr(block, 'id', ''),
                            "name": getattr(block, 'name', ''),
                            "arguments": getattr(block, 'input', {}),
                        })

        try:
            await _do_stream()
        except Exception:
            # 流式失败 → 降级非流式
            try:
                response = ""; thinking_content = ""; tool_calls_list = []
                create_kwargs = {
                    "model": model_name,
                    "max_tokens": model_config.get("max_tokens", 8000),
                    "temperature": model_config.get("temperature", 0.1),
                    "messages": formatted_messages,
                }
                if system_message:
                    create_kwargs["system"] = system_message
                if tools:
                    create_kwargs["tools"] = tools
                message = await client.messages.create(**create_kwargs)
                for block in message.content:
                    bt = getattr(block, 'type', '')
                    if bt == 'thinking':
                        chunk = getattr(block, 'thinking', '')
                        if chunk: print("💭 Thinking process:", flush=True); print(chunk, flush=True); thinking_content += chunk
                    elif bt == 'text':
                        chunk = getattr(block, 'text', '')
                        if chunk:
                            print("Thought:", flush=True)
                            print(chunk, flush=True)
                            response += chunk
                    elif bt == 'tool_use':
                        tool_calls_list.append({
                            "id": getattr(block, 'id', ''),
                            "name": getattr(block, 'name', ''),
                            "arguments": getattr(block, 'input', {}),
                        })
            except Exception:
                pass

        # thinking 拼接
        if thinking_content:
            clean_resp = response.lstrip('\n')
            if clean_resp.startswith('Thought:'):
                clean_resp = clean_resp[len('Thought:'):].lstrip()
            if clean_resp.strip():
                response = f"💭 Thinking process:\n{thinking_content}\n\nThought: {clean_resp}"
            else:
                response = f"💭 Thinking process:\n{thinking_content}"

        print()
        return {"text": response, "tool_calls": tool_calls_list}

    def _create_tools(self, project_path: Path, safety_guard) -> Dict[str, Any]:
        """创建工具集并注册到工具注册表"""

        atomic_tools = AtomicTools(project_path, safety_guard)
        code_tools = CodeTools(project_path, safety_guard)
        web_tools = WebTools(project_path, safety_guard)
        todo_tools = TodoTools(project_path, safety_guard)

        # 保存web_tools引 with 以便后续清理
        self.web_tools = web_tools

        # 包装fetch_url函数以保存结果
        async def wrapped_fetch_url(
            url: str,
            timeout: Optional[int] = None,
            max_content_length: int = 100000,
            **kwargs,
        ) -> Dict[str, Any]:
            # 调 with 原始fetch_url函数
            result = await web_tools.fetch_url(
                url, timeout, max_content_length, **kwargs
            )

            # 如果成功Get 到内容，保存到上下文文件
            if result.get("success") and "content" in result:
                try:
                    # 创建上下文目录
                    context_dir = project_path / ".aacode" / "context"
                    context_dir.mkdir(parents=True, exist_ok=True)

                    # 保存结果到web_fetch_result.txt
                    result_file = context_dir / "web_fetch_result.txt"
                    result_file.write_text(result["content"], encoding="utf-8")
                    print(
                        f"📁 Saved web_fetch result to: {result_file.relative_to(project_path)}"
                    )
                except Exception as e:
                    print(t("web.save_fetch_fail", e=str(e)))

            return result

        # 主Agent的特殊工具
        tools = {
            # 原子工具
            "run_shell": atomic_tools.run_shell,
            # 任务控制工具
            "finalize_task": self._finalize_task,
            "run_skills": self._run_skills,
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
            # 管理工具
            "delegate_task": self.delegate_task,
            "create_sub_agent": self.create_sub_agent,
            # MCP工具
            "list_mcp_tools": self.list_mcp_tools,
            "call_mcp_tool": self.call_mcp_tool,
            "get_mcp_status": self.get_mcp_status,
            # Skills查询工具 — 通过 run_skills 的统一入口实现三模式
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
            # 使 with 动态schemaGet 函数
            schema = get_schema(tool_name)
            if schema:
                registry.register(tool_func, schema)
                registered_count += 1

        # 注册多模态工具的schema
        from ..utils.tool_registry import ToolSchema, ToolParameter

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
                            description=properties[pname].get("description", ""),
                        )
                        for pname in properties.keys()
                    ],
                )
                registry.register(tools[func_name], schema)
                registered_count += 1

        print(t("tools.registered", count=registered_count))

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
        execute任务

        Args:
            task: 任务描述
            init_instructions: initialized指令
            task_dir: 任务目录
            max_iterations: 最大迭代次数
            project_analysis: 项目分析结果（类方法映射）
            todo_manager: to-do-list管理器

        Returns:
            execute结果
        """
        print(t("agent.start_task", task=task))
        self.start_time = asyncio.get_event_loop().time()

        # 如果已有当前会话，复 with ；否则创建新会话
        if self.session_manager.current_session_id:
            session_id = self.session_manager.current_session_id
            print(t("agent.session_reuse", id=session_id))
        else:
            session_id = await self.session_manager.create_session(task)
            print(t("agent.session_reuse", id=session_id))
        print(t("agent.session_hint", id=session_id))

        # 更新系统提示，包含项目分析结果
        analysis_section = ""
        if project_analysis and "failed" not in project_analysis.lower():
            analysis_section = (
                f"\n\nProject structure analysis (class-method mapping):\n{project_analysis[:1500]}..."
            )
            print(t("context.analysis_integrated"))

        full_system_prompt = f"{self.system_prompt}{analysis_section}\n\nProject init instructions:\n{init_instructions}"
        self.conversation_history[0]["content"] = full_system_prompt

        # 添加任务描述
        self.conversation_history.append(
            {
                "role": "user",
                "content": f"Task: {task}\n\nPlease reference the project structure analysis to create a plan and execute.",
            }
        )

        # ─── 加载同一会话的历史消息（多轮任务上下文衔接） ───
        # 从 session_manager Get 当前会话的历史消息（不含 system 消息）
        # 传给 react_loop.run，让模型在后续轮次中能看到之前的对话
        # ⚠️ 这是多轮任务上下文衔接的关键，不要去掉
        history_messages = await self.session_manager.get_messages(include_system=False)
        # 过滤掉当前任务的消息（还没保存，避免重复）
        # 历史消息是之前轮次保存的，当前任务的消息在 execute 结束后才保存

        # 运 linesReAct循环
        try:
            result = await self.react_loop.run(
                initial_prompt=full_system_prompt,
                task_description=task,
                todo_manager=todo_manager,
                history_messages=history_messages if history_messages else None,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(t("agent.react_loop_failed", e=str(e)))
            import traceback
            traceback.print_exc()
            raise
        finally:
            try:
                if hasattr(self, "web_tools"):
                    await self.web_tools.cleanup()
            except Exception as e:
                print(t("agent.clean_web_tools", e=str(e)))

        # 把 react_loop 的对话历史保存到 session_manager
        # ─── 保存会话历史 ───────────────────────────────────────────
        # step.thought 的内容来自 _call_openai_api 的 full_response，格式为：
        #   有 thinking 时: "💭 思考过程:\n{thinking内容}\n\nThought: {正式回复}"
        #   无 thinking 时: "{正式回复}"（纯文本，可能有 Thought: 前缀也可能没有）
        #
        # ⚠️ 必须保留完整的 thinking 内容，不要清理掉：
        #   1. 历史记录需要显示 thinking（前端 parseAssistantMessage 能正确解析）
        #   2. thinking 内容在 react_loop 运 lines时上下文中也是完整的
        #      （messages.append  with 的是原始 response，包含 thinking）
        #   3. 去掉 thinking 会导致历史记录不完整， user看不到模型的推理过程
        #
        # ✅ 任务完成标记只存纯标记，不带内容（内容已在最后一个 step 中保存）
        # ─────────────────────────────────────────────────────────────
        try:
            # 先保存 user任务消息（如果还没有）
            has_user_msg = any(
                m.role == "user" and m.content == task
                for m in self.session_manager.current_messages
            )
            if not has_user_msg:
                await self.session_manager.add_message("user", task)

            steps = self.react_loop.steps
            for step in steps:
                #  with  raw_response（完整模型响应，含 thinking）保存，而非 step.thought（只有 thought 部分）
                # raw_response 格式：有 thinking 时 "💭 思考过程:\n{thinking}\n\nThought: {content}"
                #                   无 thinking 时 "{content}"
                thought_content = step.raw_response or step.thought
                # 确保有可识别的前缀（前端 parseAssistantMessage 依赖前缀识别类型）
                if not thought_content.startswith("Thought:") and not thought_content.startswith("💭 Thinking process"):
                    thought_content = f"Thought: {thought_content}"
                if step.actions:
                    actions_parts = []
                    for a in step.actions:
                        part = f"Action: {a.action}"
                        if a.action_input:
                            import json as _json
                            part += f"\nAction Input: {_json.dumps(a.action_input, ensure_ascii=False)[:500]}"
                        if a.observation:
                            part += f"\nObservation: {a.observation[:2000]}"
                        actions_parts.append(part)
                    thought_content = f"{thought_content}\n\n" + "\n\n".join(actions_parts)
                await self.session_manager.add_message("assistant", thought_content)

            # ⚠️ 只存纯标记，不要带 summary 内容，否则和最后一个 step 重复
            await self.session_manager.add_message("assistant", "✅ Task completed")
            await self.session_manager._save_session()
            # 追加保存结构化消息（含 tool_calls / reasoning_content），  for多轮 API 上下文
            if hasattr(self.react_loop, 'last_messages') and self.react_loop.last_messages:
                await self.session_manager._save_structured_messages(self.react_loop.last_messages)
            self.session_manager._save_sessions_index()
        except Exception as e:
            print(t("error.save_session", e=str(e)))

        # 更新统计
        self.iterations = len(self.react_loop.steps)

        execution_time = 0.0
        if self.start_time is not None:
            execution_time = asyncio.get_event_loop().time() - self.start_time

        return {
            **result,
            "session_id": session_id,
            "agent_stats": self.get_stats(),
            "execution_time": execution_time,
        }

    async def delegate_task(
        self,
        task_description: str,
        agent_type: str = "general",
        context_strategy: str = "isolated",
    ) -> Dict[str, Any]:
        """
        委托任务给SubAgent

        Args:
            task_description: 任务描述
            agent_type: Agent类型 (general, code, test, research)
            context_strategy: 上下文策略 (isolated, shared, minimal)

        Returns:
            委托结果
        """
        task_id = f"subtask_{len(self.tasks)}_{datetime.now().timestamp():.0f}"

        print(t("subagent.task_start", id=task_description[:50]))

        # 创建子任务记录
        self.tasks[task_id] = {
            "description": task_description,
            "agent_type": agent_type,
            "context_strategy": context_strategy,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "result": None,
        }

        # 使 with 多Agent系统委托
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
            return {"error": f"Task not found: {task_id}"}

        task = self.tasks[task_id]

        # 检查SubAgent状态
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
        """创建SubAgent"""
        agent_id = f"sub_{agent_type}_{len(self.sub_agents)}"

        # 根据类型选择系统提示
        if agent_type == "code":
            system_prompt = """You are a specialized code-writing agent.
            Focus on:
            1. Write high-quality, maintainable code
            2. Follow best practices and coding standards
            3. Add necessary comments and documentation
            4. Write unit tests
            5. Keep it simple: complete the task with minimal changes to existing code
            6. Prefer incremental updates over full rewrites for small code changes
            7. Extend or modify existing code rather than creating new redundant files

            Use the provided tools to complete your task."""
        elif agent_type == "test":
            system_prompt = """You are a specialized testing agent.
            Focus on:
            1. Write comprehensive test cases
            2. Test edge cases and exception handling
            3. Performance and stress testing
            4. Generate test reports

            Use the provided tools to complete your task."""
        elif agent_type == "research":
            system_prompt = """You are a research agent.
            Focus on:
            1. Analyze requirements and scope
            2. Search for relevant documentation and best practices
            3. Provide comprehensive analysis and recommendations

            Use the provided tools to complete your task."""
        else:
            system_prompt = """You are a general-purpose sub-agent.
            Focus on completing the assigned task efficiently.
            Use the provided tools to complete your task."""

        # 注入项目目录信息到子代理系统提示词
        project_path_str = f"\n\nYour current working directory is: {self.project_path.absolute()}\nAll file operations should use paths relative to this directory."
        system_prompt += project_path_str

        # 创建SubAgent
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
            return {"error": f"Get MCPtool list failed: {str(e)}"}

    async def call_mcp_tool(
        self, tool_name: str, arguments: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """调 with MCP工具"""
        try:
            result = await self.mcp_manager.call_tool(tool_name, arguments or {})
            return result
        except Exception as e:
            return {"error": f"MCP tool call failed: {str(e)}"}

    async def get_mcp_status(self) -> Dict[str, Any]:
        """Get MCP server状态"""
        try:
            status_result = await self.mcp_manager.get_server_status()
            return status_result
        except Exception as e:
            return {"error": f"Get MCP status failed: {str(e)}"}

    async def new_session(
        self, task: str, title: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建新会话"""
        try:
            session_id = await self.session_manager.create_session(task, title)
            return {
                "success": True,
                "session_id": session_id,
                "message": "New session created",
            }
        except Exception as e:
            return {"error": f"Create session failed: {str(e)}"}

    async def continue_session(
        self, message: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """继续当前会话或指定会话"""
        try:
            # 添加 user消息
            added = await self.session_manager.add_message("user", message)
            if not added:
                return {"error": "Message add failed, possibly exceeding token limit"}

            # Get 会话历史
            messages = await self.session_manager.get_messages(session_id)

            return {
                "success": True,
                "session_id": session_id or self.session_manager.current_session_id,
                "messages": messages,
                "conversation_preview": await self.session_manager.get_conversation_history(),
            }
        except Exception as e:
            return {"error": f"Continue session failed: {str(e)}"}

    async def list_sessions(self) -> Dict[str, Any]:
        """列出所有会话"""
        try:
            sessions = await self.session_manager.list_sessions()
            return {"success": True, "sessions": sessions, "count": len(sessions)}
        except Exception as e:
            return {"error": f"Get session list failed: {str(e)}"}

    async def switch_session(self, session_id: str) -> Dict[str, Any]:
        """切换到指定会话"""
        try:
            success = await self.session_manager.switch_session(session_id)
            if success:
                return {
                    "success": True,
                    "session_id": session_id,
                    "message": "Session switched successfully",
                }
            else:
                return {"error": f"Session not found: {session_id}"}
        except Exception as e:
            return {"error": f"Switch session failed: {str(e)}"}

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """删除会话"""
        try:
            success = await self.session_manager.delete_session(session_id)
            if success:
                return {
                    "success": True,
                    "session_id": session_id,
                    "message": "Session deleted",
                }
            else:
                return {"error": f"Session not found: {session_id}"}
        except Exception as e:
            return {"error": f"Delete session failed: {str(e)}"}

    async def get_conversation_history(self, max_length: int = 10) -> Dict[str, Any]:
        """Get 对话历史"""
        try:
            history = await self.session_manager.get_conversation_history(max_length)
            return {"success": True, "history": history}
        except Exception as e:
            return {"error": f"Get conversation history failed: {str(e)}"}

    # 移除复杂规划功能，使 with ReAct内置的动态规划
    # 相关的create_plan、execute_plan_step、get_plan_status等方法已删除

    async def get_session_stats(self) -> Dict[str, Any]:
        """Get 会话统计信息"""
        try:
            stats = self.session_manager.get_session_stats()
            return {"success": True, "stats": stats}
        except Exception as e:
            return {"error": f"Get session stats failed: {str(e)}"}

    async def get_project_status(self) -> Dict[str, Any]:
        """Get 项目状态"""
        try:
            # Get Git状态
            git_status = {}
            try:
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True,
                    text=True,
                    cwd=self.project_path,
                )
                if result.returncode == 0:
                    if result.stdout.strip():
                        git_status["changed_files"] = len(
                            result.stdout.strip().split("\n")
                        )
                    else:
                        git_status["changed_files"] = 0
                    git_status["has_changes"] = bool(result.stdout.strip())
            except:
                git_status["error"] = "Git not initialized or unavailable"

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
        """析构函数 - 不再尝试异步清理，避免 Windows 上 _sock.fileno() 错误刷屏。
        资源清理由 execute() 的 finally 块中 web_tools.cleanup() 完成。"""
        pass
