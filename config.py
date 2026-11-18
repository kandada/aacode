from __future__ import annotations

# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

# 配置管理
# config.py
"""
配置管理
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional, List
import yaml
import platformdirs
from aacode.i18n import t

# Safe defaults for legacy configs that stored these values as 0. Most modern
# coding models have a ~1M-token window; 32k is a conservative completion cap
# that is supported by common coding endpoints.
DEFAULT_CONTEXT_WINDOW = 1_000_000
DEFAULT_MAX_OUTPUT_TOKENS = 32_000


@dataclass
class ModelConfig:
    """模型配置"""

    name: str = "deepseek-chat"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 96000
    gateway: str = "openai"  # openai, anthropic
    multimodal: bool = False  # 是否supports multimodal
    # Per-route context metadata. These are optional for old config files and
    # are resolved from the selected entry in ``models`` when available.
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    default_model: str = ""
    models: Dict[str, Any] = field(default_factory=dict)
    pricing: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # 环境变量优先，yaml配置作为后备
        self.api_key = (
            os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or self.api_key
        )
        # 先不设置默认base_url，让_auto_detect_model_config根据模型名称决定
        self.base_url = (
            os.getenv("LLM_API_URL") or os.getenv("OPENAI_BASE_URL") or self.base_url
        )
        self.name = os.getenv("LLM_MODEL_NAME") or self.name or "deepseek-chat"
        self.gateway = os.getenv("LLM_GATEWAY") or self.gateway or "openai"

        # 多模态配置（环境变量优先）
        llm_multimodal = os.getenv("LLM_MULTIMODAL")
        if llm_multimodal is not None:
            # 环境变量可以覆盖自动检测
            self.multimodal = llm_multimodal.lower() in ["true", "1", "yes", "on"]
        else:
            # 根据模型名称自动设置多模态和网关
            self._auto_detect_model_config()

    def _auto_detect_model_config(self):
        """根据模型名称自动检测配置"""
        model_lower = self.name.lower()

        # 检查 user是否通过环境变量显式设置了网关
        user_explicit_gateway = os.getenv("LLM_GATEWAY")

        # Multimodal model检测（只有明确supports multimodal的模型）
        # 重置为默认值，然后根据模型名称检测
        self.multimodal = False  # 默认不是多模态

        # 更灵活的Multimodal model检测，支持多种名称格式
        model_lower_clean = model_lower.replace("-", "_").replace(" ", "_")

        # 检测Kimi模型（支持多种格式）
        kimi_patterns = ["kimi", "moonshot"]
        is_kimi = any(pattern in model_lower_clean for pattern in kimi_patterns)

        # 检测MiniMax模型
        minimax_patterns = ["minimax", "minimaxi"]
        is_minimax = any(pattern in model_lower_clean for pattern in minimax_patterns)

        # 检测DeepSeek模型
        is_deepseek = "deepseek" in model_lower

        if is_kimi or is_minimax:
            self.multimodal = True
            print(f"🔍 Multimodal model detected: {self.name} (format: {model_lower_clean})")

        # 根据 user是否显式设置网关来决定 lines为
        if user_explicit_gateway:
            #  user显式设置了网关，只根据网关类型选择URL，不覆盖网关本身
            gateway = user_explicit_gateway.lower()
            if is_minimax:
                if gateway == "anthropic":
                    if not self.base_url or "openai" in self.base_url:
                        self.base_url = "https://api.minimax.chat/anthropic"
                    elif "minimax" in self.base_url:
                        self.base_url = self._adjust_url_for_anthropic(self.base_url)
                else:  # openai
                    if not self.base_url or "anthropic" in self.base_url:
                        self.base_url = "https://api.minimax.chat/v1"
            elif is_kimi:
                if gateway == "anthropic":
                    if not self.base_url or "openai" in self.base_url:
                        self.base_url = "https://api.moonshot.cn/anthropic"
                    elif "moonshot" in self.base_url:
                        self.base_url = self._adjust_url_for_anthropic(self.base_url)
                else:  # openai
                    if not self.base_url or "anthropic" in self.base_url:
                        self.base_url = "https://api.moonshot.cn/v1"
            elif is_deepseek:
                if gateway == "anthropic":
                    if not self.base_url or "openai" in self.base_url:
                        self.base_url = "https://api.deepseek.com/anthropic"
                    elif "deepseek" in self.base_url:
                        self.base_url = self._adjust_url_for_anthropic(self.base_url)
                else:  # openai
                    if not self.base_url or "anthropic" in self.base_url:
                        self.base_url = "https://api.deepseek.com/v1"
            elif "gpt" in model_lower and gateway == "anthropic":
                # GPT模型使 with Anthropic网关时，指向Anthropic官方API
                if not self.base_url or "openai" in self.base_url:
                    self.base_url = "https://api.anthropic.com"
            elif "claude" in model_lower:
                # Claude模型默认使 with Anthropic网关
                if gateway == "anthropic":
                    if not self.base_url or "openai" in self.base_url:
                        self.base_url = "https://api.anthropic.com"
                else:  # openai
                    if not self.base_url or "anthropic" in self.base_url:
                        self.base_url = "https://api.openai.com/v1"
        else:
            #  user没有显式设置网关，使 with 默认 lines为
            if is_minimax:
                self.gateway = "anthropic"
                if not self.base_url or "openai" in self.base_url:
                    self.base_url = "https://api.minimax.chat/anthropic"
                elif "minimax" in self.base_url:
                    self.base_url = self._adjust_url_for_anthropic(self.base_url)
            elif is_kimi:
                self.gateway = "openai"
                if not self.base_url or "anthropic" in self.base_url:
                    self.base_url = "https://api.moonshot.cn/v1"
            elif is_deepseek:
                self.gateway = "openai"
                if not self.base_url or "anthropic" in self.base_url:
                    self.base_url = "https://api.deepseek.com/v1"
            elif "claude" in model_lower:
                # Claude模型默认使 with Anthropic网关
                self.gateway = "anthropic"
                if not self.base_url or "openai" in self.base_url:
                    self.base_url = "https://api.anthropic.com"
            elif "gpt" in model_lower:
                self.gateway = "openai"
                if (
                    not self.base_url
                    or "minimax" in self.base_url
                    or "moonshot" in self.base_url
                ):
                    self.base_url = "https://api.openai.com/v1"

    def _adjust_url_for_anthropic(self, base_url: str) -> str:
        """调整URL以适配Anthropic SDK"""
        if base_url.endswith("/v1"):
            return base_url[:-3] + "/anthropic"
        elif base_url.endswith("/v1/anthropic"):
            return base_url.replace("/v1/anthropic", "/anthropic")
        elif not base_url.endswith("/anthropic"):
            return base_url.rstrip("/") + "/anthropic"
        return base_url


@dataclass
class ToolConfig:
    """工具配置"""

    # 原子工具
    enable_shell: bool = True
    enable_search: bool = True

    # 沙箱工具
    enable_sandbox: bool = False
    sandbox_type: str = "docker"  # docker, vm, local

    # 网络工具
    enable_web_search: bool = True
    search_engine: str = "searxng"
    search_api_url: Optional[str] = None
    search_api_key: Optional[str] = None
    enable_fallback_scrape: bool = True

    # 浏览器工具（fastbrowser）——默认全自动，用户零配置
    chrome_path: Optional[str] = None  # 空 = 自动探测（CHROME_PATH env → 系统常见路径）
    cdp_url: Optional[str] = None      # 空 = 自动启动 Chromium；非空 = 连接已有 Chrome
    browser_headless: bool = True
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 800

    # 代码工具
    enable_code_execution: bool = True
    enable_testing: bool = True
    max_execution_time: int = 60

    # 工具 schema 分组：auto / core / web / full
    tool_profile: str = "auto"
    enable_media_tools: bool = True
    enable_mcp_tools: bool = True


@dataclass
class SafetyConfig:
    """安全配置"""

    enable_safety_guard: bool = True
    restrict_to_project: bool = False
    allow_network: bool = True
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    dangerous_command_action: str = "ask"  # reject, ask, log — ask 模式下危险命令弹窗确认
    unknown_command_action: str = "allow"  # reject, ask, allow — 未在白名单/ PATH 中的命令


@dataclass
class ContextConfig:
    """上下文配置"""

    strategy: str = "file_based"  # file_based, memory, hybrid
    max_context_length: int = DEFAULT_CONTEXT_WINDOW
    compact_threshold: int = 12000
    history_compression: bool = True
    use_vector_store: bool = False
    # 新增：上下文缩减配置
    compact_trigger_tokens: int = 512000  # 触发缩减的token数阈值
    compact_keep_rounds: int = 10  # 退化场景：缩减后保留的对话轮数（最近N轮）
    compact_summary_steps: int = 10  # 摘要包含的步骤数
    compact_protect_first_rounds: int = 1  # 保护前N轮（只保留 system prompt，其余由 AI 摘要承载）
    compact_protect_user_rounds: int = 2  # 保护最近N条用户消息及附带消息（确保最新上下文完整）

    # ── 新一代上下文策略（质量优先，同时保留成本上限） ──
    # trigger = min(window * window_ratio, window - output - headroom)
    # 默认沿用 DSH 的质量优先比例：尽量用满窗口，而不是固定 100k。
    window_ratio: float = 0.8
    headroom_tokens: int = 65536
    retain_ratio: float = 0.16
    # 绝对保留值；设置后覆盖 retain_ratio。
    retain_tokens: Optional[int] = None
    # 可选成本上限。默认 None = 只按窗口比例；设置后 trigger 取两者较小值。
    cost_ceiling_tokens: Optional[int] = None

    # 旧字段保留用于兼容；新逻辑使用上面的 window_ratio/headroom/retain。
    retrieval_trigger_tokens: int = 0
    retrieval_keep_tokens: int = 0
    retrieval_keep_recent_user_messages: int = 2
    retrieval_keep_min_rounds: int = 4

    # 工具结果治理
    inline_tool_tokens: int = 6000
    inline_head_chars: int = 8000
    inline_tail_chars: int = 4000
    prune_enabled: bool = True
    prune_threshold_chars: int = 8192
    prune_head_chars: int = 4096
    prune_tail_chars: int = 1024
    prune_min_rounds: int = 4

    # 结构化摘要（与检索式 cutoff 结合）
    summary_mode: str = "adaptive"  # off | always | adaptive
    summary_min_shadow_tokens: int = 30000
    summary_max_tokens: int = 2000
    summary_provider: str = ""
    summary_model: str = ""

    # 失效恢复与任务预算
    overflow_retries: int = 1
    task_input_token_budget: int = 0  # 0 = 不限制
    task_output_token_budget: int = 0

    # 循环与重复调用防护
    repeat_tool_enabled: bool = True
    repeat_tool_thresholds: List[int] = field(default_factory=lambda: [3, 5, 8])
    read_cache_enabled: bool = True


@dataclass
class AgentConfig:
    """Agent配置"""

    max_react_iterations: int = 300
    max_sub_agent_iterations: int = 100
    enable_auto_planning: bool = True
    enable_todo_tracking: bool = True
    # Subagent safety/cost policy.
    max_sub_agent_depth: int = 2
    max_sub_agent_concurrency: int = 3
    subagent_model: str = ""
    subagent_input_token_budget: int = 400000
    subagent_output_token_budget: int = 60000
    subagent_timeout_seconds: int = 600


@dataclass
class MCPConfig:
    """MCP server配置"""

    enabled: bool = True
    # STD类型MCP server配置
    # 注意：具体配置从aacode_config.yaml文件加载，这里只保留空列表
    std_servers: List[Dict[str, Any]] = field(default_factory=list)
    # SSE类型MCP server配置
    # 注意：具体配置从aacode_config.yaml文件加载，这里只保留空列表
    sse_servers: List[Dict[str, Any]] = field(default_factory=list)
    # 通 with 配置
    auto_connect: bool = True
    connection_timeout: int = 30
    max_retries: int = 1  # 工具调用重试次数。设为1=不重试，失败由模型决策
@dataclass
class OutputConfig:
    """输出处理配置（自适应截断 — 基于剩余上下文预算）"""

    budget_ratio: float = 0.6  # 工具输出最多占用剩余预算的比例
    max_preview_tokens: int = 2000  # 预览最多 token 数
    display_preview_chars: int = 3000  # 用户终端显示预览字符数


@dataclass
class TimeoutConfig:
    """timeout配置"""

    tool_default: int = 300  # 通用工具执行timeout（秒），防挂起兜底
    shell_command: int = 30  # Shell命令executetimeout（秒）
    model_summary: int = 30  # 模型摘要生成timeout（秒）
    file_search: int = 5  # 文件搜索timeout（秒）
    code_execution: int = 60  # 代码executetimeout（秒）
    sandbox_command: int = 120  # 沙箱命令timeout（秒）
    web_request: int = 30  # 网络请求timeout（秒）


@dataclass
class LimitsConfig:
    """限制配置"""

    max_file_list_results: int = 100  # 文件列表最大结果数
    max_search_results: int = 20  # 搜索最大结果数
    max_retries: int = 1  # 工具调用重试次数。设为1=不重试，失败由模型自行决策
    skill_max_result_chars: int = 5000  # skill 返回结果最大字符数，超过则截断并存入 .aacode/extracts/
    shell_output_preview: int = 200  # Shell输出预览长度（字符）
    max_auto_read_lines: int = 200  # 超过此 lines数时提供分段建议
    structure_preview_lines: int = 50  # 结构预览显示的 lines数
    max_context_files: int = 50  # 上下文中显示的最大文件数
    prioritize_file_types: bool = True  # 是否优先显示重要文件类型


@dataclass
class DiffHookConfig:
    """隐式 diff 钩子配置 — 在 run_shell 执行后自动检测文件变更并反馈"""

    enabled: bool = False
    small_change_threshold: int = 10          # ≤N 行 → diff；>N 行 → diff_preview
    max_tracked_files: int = 50               # 关注文件集合上限（LRU）
    max_diff_lines: int = 60                  # diff 最大行数（超限截断）
    max_total_changes_lines: int = 200        # 批量反馈总行数上限
    fs_scan_max_files: int = 5000             # 策略B 文件系统扫描硬上限
    fs_scan_dir_entry_threshold: int = 1000   # 策略B 目录条目数阈值（超过则跳过子树）
    watched_extensions: tuple = (
        ".py", ".js", ".ts", ".jsx", ".tsx",
        ".go", ".rs", ".java", ".c", ".cpp",
        ".h", ".hpp", ".yaml", ".yml", ".json",
        ".toml", ".md", ".txt", ".sh", ".bash",
        ".html", ".css", ".scss", ".less",
    )
    fs_ignore_dirs: tuple = (
        ".git", ".aacode", "node_modules", "__pycache__",
        ".venv", "venv", ".tox", "dist", "build",
        ".egg-info", ".mypy_cache", ".pytest_cache",
        ".idea", ".vscode", ".ruff_cache", ".direnv",
    )

    def __post_init__(self):
        if isinstance(self.watched_extensions, list):
            self.watched_extensions = tuple(self.watched_extensions)
        if isinstance(self.fs_ignore_dirs, list):
            self.fs_ignore_dirs = tuple(self.fs_ignore_dirs)


@dataclass
class SkillsConfig:
    """Skills配置"""

    enabled: bool = True
    skills_dir: str = "skills"
    auto_discover: bool = True


@dataclass
class MultimodalModelConfig:
    """单个Multimodal model配置"""

    name: str = ""
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    vision: bool = True
    video: bool = False
    max_image_size: int = 10485760  # 10MB
    max_video_size: int = 104857600  # 100MB
    supported_formats: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
            "videos": [".mp4", ".avi", ".mov", ".mkv", ".webm"],
        }
    )


@dataclass
class MultimodalConfig:
    """Multimodal model配置"""

    enabled: bool = True  # 是否启 with 多模态功能
    default_model: str = "moonshot_kimi_k2.5"  # 默认使 with 的Multimodal model
    models: Dict[str, Any] = field(
        default_factory=lambda: {
            "moonshot_kimi_k2.5": {
                "name": "kimi-k2.5",
                "provider": "moonshot",
                "gateway": "openai",
                "base_url": "https://api.moonshot.cn/v1",
                "api_key": "",
                "vision": True,
                "video": True,
                "max_image_size": 10485760,
                "max_video_size": 104857600,
                "supported_formats": {
                    "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
                    "videos": [".mp4", ".avi", ".mov", ".mkv", ".webm"],
                },
            },
            "minimax_m2.5": {
                "name": "MiniMax-M2.5",
                "provider": "minimax",
                "gateway": "anthropic",
                "base_url": "https://api.minimax.chat/anthropic",
                "api_key": "",
                "vision": True,
                "video": True,
                "max_image_size": 10485760,
                "max_video_size": 104857600,
                "supported_formats": {
                    "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
                    "videos": [".mp4", ".avi", ".mov", ".mkv", ".webm"],
                },
            },
        }
    )


class Settings:
    """全局设置"""

    @staticmethod
    def _find_config_file(
        config_file: Optional[str] = None,
    ) -> tuple[Optional[Path], str]:
        """
        多级回退查找配置文件
        返回 (config_path, source) 元组
        source 表示配置来源: "explicit", "cwd", "home", "package", "none"
        """
        if config_file:
            path = Path(config_file)
            if path.exists():
                return path, "explicit"
            return None, "none"

        # 环境变量指定配置文件（客户端开发模式 with ）
        env_config = os.getenv("AACODE_CONFIG_FILE")
        if env_config:
            path = Path(env_config)
            if path.exists():
                return path, "explicit"

        config_dir = Path(platformdirs.user_config_dir("com.aacode", roaming=True))
        candidates = [
            (Path.cwd() / "aacode_config.yaml", "cwd"),
            (config_dir / "aacode_config.yaml", "platformdirs"),
            (Path(__file__).parent / "aacode_config.yaml", "package"),
            (Path.home() / ".aacode" / "aacode_config.yaml", "home"),
        ]

        for path, source in candidates:
            if path.exists():
                return path, source

        return None, "none"

    def __init__(self, config_file: Optional[str] = None):
        self.config_path, self.config_source = self._find_config_file(config_file)
        self._explicit_config_file = config_file

        # 默认配置
        self.model = ModelConfig()
        self.tools = ToolConfig()
        self.safety = SafetyConfig()
        self.context = ContextConfig()
        self.agent = AgentConfig()
        self.mcp = MCPConfig()  # MCP配置
        self.output = OutputConfig()  # 输出配置
        self.timeouts = TimeoutConfig()  # timeout配置
        self.limits = LimitsConfig()  # 限制配置
        self.skills = SkillsConfig()  # Skills配置
        self.multimodal = MultimodalConfig()  # 多模态配置
        self.diff_hook = DiffHookConfig()  # diff 钩子配置
        self.pricing: Dict[str, Any] = {}  # 模型价格表（按模型名/键）
        self.language: str = "en"    # 语言 en / zh

        # 从文件加载配置
        self.load_config()

        # 从环境变量更新配置（环境变量优先）
        self._load_from_env()
        self._normalize_compat_settings()

        # initialized i18n
        from aacode.i18n import init as i18n_init
        i18n_init(self.language)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """深度合并两个字典：override 的值优先，base 中缺失的 key 被补充进去"""
        result = override.copy()
        for key, value in base.items():
            if key not in result:
                result[key] = value
            elif isinstance(value, dict) and isinstance(result[key], dict):
                result[key] = Settings._deep_merge(value, result[key])
        return result

    def _merge_with_defaults(self, user_config: dict) -> dict:
        """将包内默认 YAML 中的缺失字段合并到用户配置中（不覆盖已有值）"""
        pkg_config_path = Path(__file__).parent / "aacode_config.yaml"
        if not pkg_config_path.exists():
            return user_config
        with open(pkg_config_path, "r", encoding="utf-8") as f:
            default_config = yaml.safe_load(f) or {}
        return self._deep_merge(default_config, user_config)

    def load_config(self):
        """从文件加载配置"""
        if not self.config_path or not self.config_path.exists():
            if self._explicit_config_file is None:
                pkg_config = Path(__file__).parent / "aacode_config.yaml"
                if pkg_config.exists():
                    target_dir = Path(platformdirs.user_config_dir("com.aacode", roaming=True))
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_path = target_dir / "aacode_config.yaml"
                    shutil.copy(pkg_config, target_path)
                    self.config_path = target_path
                    self.config_source = "platformdirs"
                    print(f"Config saved to {target_path}")

        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)

                if config_data is None:
                    config_data = {}

                # 对非 package 来源的配置做缺失字段合并（老用户升级兼容）
                if self.config_source not in ("package", "none"):
                    merged = self._merge_with_defaults(config_data)
                    if merged != config_data:
                        config_data = merged
                        try:
                            with open(self.config_path, "w", encoding="utf-8") as f:
                                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                        except Exception as e:
                            print(t("config.save_error", e=str(e)))

                # Migrate pre-1.9 context settings: the old fixed retrieval
                # trigger/keep values were cost-first and prevented using the
                # model window. Unless a new cost ceiling was explicitly set,
                # move those sessions to the window-ratio policy.
                try:
                    ctx = config_data.get("context") if isinstance(config_data, dict) else None
                    if isinstance(ctx, dict) and "cost_ceiling_tokens" not in ctx:
                        if int(ctx.get("retrieval_trigger_tokens") or 0) > 0:
                            ctx["retrieval_trigger_tokens"] = 0
                            ctx["retrieval_keep_tokens"] = 0
                            ctx.setdefault("window_ratio", 0.8)
                            ctx.setdefault("headroom_tokens", 65536)
                            ctx.setdefault("retain_ratio", 0.16)
                            with open(self.config_path, "w", encoding="utf-8") as f:
                                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                except Exception:
                    pass

                # 更新配置
                if config_data:
                    self._update_from_dict(config_data)
                    self._normalize_compat_settings()
            except Exception as e:
                print(t("config.load_error", e=str(e)))

    def save_config(self):
        """保存配置到文件"""
        config_data = {
            "language": self.language,
            "model": asdict(self.model),
            "tools": asdict(self.tools),
            "safety": asdict(self.safety),
            "context": asdict(self.context),
            "agent": asdict(self.agent),
            "output": asdict(self.output),
            "timeouts": asdict(self.timeouts),
            "limits": asdict(self.limits),
            "mcp": asdict(self.mcp),
            "skills": asdict(self.skills),
            "multimodal": asdict(self.multimodal),
            "diff_hook": asdict(self.diff_hook),
        }

        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            print(t("config.save_error", e=str(e)))

    def _load_from_env(self):
        """从环境变量加载配置（环境变量优先）"""
        # 环境变量优先，覆盖yaml配置

        # 模型配置
        llm_api_key = os.getenv("LLM_API_KEY")
        if llm_api_key:
            self.model.api_key = llm_api_key
        llm_api_url = os.getenv("LLM_API_URL")
        if llm_api_url:
            self.model.base_url = llm_api_url
        llm_model_name = os.getenv("LLM_MODEL_NAME")
        if llm_model_name:
            self.model.name = llm_model_name
        llm_gateway = os.getenv("LLM_GATEWAY")
        if llm_gateway:
            self.model.gateway = llm_gateway

        # 多模态配置
        llm_multimodal = os.getenv("LLM_MULTIMODAL")
        if llm_multimodal is not None:
            # 触发ModelConfig的__post_init__重新加载
            self.model.multimodal = llm_multimodal.lower() in ["true", "1", "yes", "on"]

        # Multimodal model选择
        multimodal_model = os.getenv("MULTIMODAL_MODEL")
        if multimodal_model and multimodal_model in self.multimodal.models:
            self.multimodal.default_model = multimodal_model

        # 多模态API密钥
        multimodal_api_key = os.getenv("MULTIMODAL_API_KEY")
        if multimodal_api_key and multimodal_model in self.multimodal.models:
            self.multimodal.models[multimodal_model]["api_key"] = multimodal_api_key

        # 搜索配置
        search_api_url = os.getenv("SEARCHXNG_URL")
        if search_api_url:
            self.tools.search_api_url = search_api_url
            self.tools.enable_web_search = True
        search_api_key = os.getenv("SEARCH_API_KEY") or os.getenv("SEARCHXNG_API_KEY")
        if search_api_key:
            self.tools.search_api_key = search_api_key

        # 浏览器工具（fastbrowser）
        chrome_path = os.getenv("CHROME_PATH")
        if chrome_path:
            self.tools.chrome_path = chrome_path
        cdp_url = os.getenv("FASTBROWSER_CDP_URL")
        if cdp_url:
            self.tools.cdp_url = cdp_url

        # 语言配置
        lang = os.getenv("AACODE_LANG")
        if lang and lang in ("en", "zh"):
            self.language = lang

    def _update_from_dict(self, config_dict: Dict[str, Any]):
        """从字典更新配置"""
        for section, values in config_dict.items():
            if section == "timeouts":
                # 处理timeouts配置
                if isinstance(values, dict):
                    for key, value in values.items():
                        if hasattr(self.timeouts, key):
                            setattr(self.timeouts, key, value)
            elif section == "limits":
                # 处理limits配置
                if isinstance(values, dict):
                    for key, value in values.items():
                        if hasattr(self.limits, key):
                            setattr(self.limits, key, value)
            elif section == "mcp":
                # 处理MCP配置
                if isinstance(values, dict):
                    for key, value in values.items():
                        if hasattr(self.mcp, key):
                            setattr(self.mcp, key, value)
            elif section == "skills":
                # 处理Skills配置
                if isinstance(values, dict):
                    for key, value in values.items():
                        if hasattr(self.skills, key):
                            setattr(self.skills, key, value)
            elif section == "diff_hook":
                # 处理diff_hook配置
                if isinstance(values, dict):
                    for key, value in values.items():
                        if hasattr(self.diff_hook, key):
                            setattr(self.diff_hook, key, value)
                    if hasattr(self.diff_hook, "__post_init__"):
                        self.diff_hook.__post_init__()

            if section == "multimodal":
                # 处理多模态配置
                if isinstance(values, dict):
                    for key, value in values.items():
                        if hasattr(self.multimodal, key):
                            setattr(self.multimodal, key, value)
            elif section == "model":
                # 处理model配置（支持列表+扁平两种结构）
                if isinstance(values, dict):
                    # 保留完整模型目录，供路由解析和价格表使用。
                    if isinstance(values.get("models"), dict):
                        self.model.models = values["models"]
                    if values.get("default_model"):
                        self.model.default_model = str(values["default_model"])
                    if isinstance(values.get("pricing"), dict):
                        self.model.pricing = values["pricing"]
                    # 优先从列表结构读取（models + default_model）
                    if "models" in values and "default_model" in values:
                        default_key = values["default_model"]
                        models = values.get("models", {})
                        if isinstance(models, dict) and default_key in models:
                            model_entry = models[default_key]
                            if isinstance(model_entry, dict):
                                for k, v in model_entry.items():
                                    if hasattr(self.model, k):
                                        setattr(self.model, k, v)
                    # 扁平字段（temperature / max_tokens / 向后兼容）
                    for key, value in values.items():
                        if key in ("models", "default_model", "pricing"):
                            continue
                        if hasattr(self.model, key):
                            setattr(self.model, key, value)
            elif section == "pricing":
                if isinstance(values, dict):
                    self.pricing = values
            elif section == "language":
                self.language = str(values) if values else "en"
            elif hasattr(self, section):
                section_obj = getattr(self, section)
                if hasattr(section_obj, "__dataclass_fields__"):
                    for key, value in values.items():
                        if hasattr(section_obj, key):
                            setattr(section_obj, key, value)

    def _normalize_compat_settings(self) -> None:
        """Repair legacy null/zero values in memory without rewriting YAML.

        Old configs often stored zero for values that were introduced later, or
        null for optional policy fields. Runtime code should see the same safe
        defaults as a freshly generated config.
        """
        def _as_int(value: Any, default: int) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def _as_float(value: Any, default: float) -> float:
            try:
                number = float(value)
                return number if number > 0 else default
            except (TypeError, ValueError):
                return default

        if _as_int(self.model.max_tokens, 0) <= 0:
            self.model.max_tokens = DEFAULT_MAX_OUTPUT_TOKENS
        if self.model.context_window is not None and _as_int(self.model.context_window, 0) <= 0:
            self.model.context_window = None
        if self.model.max_output_tokens is not None and _as_int(self.model.max_output_tokens, 0) <= 0:
            self.model.max_output_tokens = None

        if _as_int(self.context.max_context_length, 0) <= 0:
            self.context.max_context_length = DEFAULT_CONTEXT_WINDOW
        ratio = _as_float(self.context.window_ratio, 0.8)
        self.context.window_ratio = ratio if ratio <= 1 else 0.8
        self.context.headroom_tokens = max(0, _as_int(self.context.headroom_tokens, 65536))
        retain = _as_float(self.context.retain_ratio, 0.16)
        self.context.retain_ratio = retain if retain < self.context.window_ratio else 0.16
        mode = str(self.context.summary_mode or "adaptive").lower()
        self.context.summary_mode = (
            mode if mode in ("off", "adaptive", "always") else "adaptive"
        )
        for key in ("compact_trigger_tokens", "compact_keep_rounds", "compact_protect_first_rounds", "compact_protect_user_rounds"):
            setattr(self.context, key, max(0, _as_int(getattr(self.context, key, 0), 0)))

    def get_model_profile(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Resolve the effective config for one model name/key.

        The flat ``model`` section remains the fallback for old configs. A
        matching entry in ``model.models`` overrides route metadata such as
        ``context_window``, ``max_output_tokens`` and ``pricing``.
        """
        target = name or os.getenv("LLM_MODEL_NAME") or self.model.name
        entry: Dict[str, Any] = {}
        models = self.model.models if isinstance(self.model.models, dict) else {}
        if models:
            for key, candidate in models.items():
                if not isinstance(candidate, dict):
                    continue
                candidate_name = str(candidate.get("name") or key)
                if target in (key, candidate_name):
                    entry = dict(candidate)
                    break
            if not entry and self.model.default_model in models:
                candidate = models[self.model.default_model]
                if isinstance(candidate, dict):
                    entry = dict(candidate)
        def _positive_int(value: Any) -> Optional[int]:
            """Treat 0/negative/empty legacy values as unset."""
            try:
                number = int(value)
            except (TypeError, ValueError):
                return None
            return number if number > 0 else None

        # Old configs may contain context_window/max_output_tokens/max_tokens
        # as 0. Treat those as unset and resolve safe defaults; otherwise the
        # value propagates to the API as max_tokens=0 and requests fail.
        entry_context = _positive_int(
            entry.get("context_window") or entry.get("contextWindow")
        )
        entry_max_output = _positive_int(
            entry.get("max_output_tokens") or entry.get("maxOutputTokens")
        )
        entry_max_tokens = _positive_int(entry.get("max_tokens"))
        base_max_tokens = (
            _positive_int(self.model.max_tokens) or DEFAULT_MAX_OUTPUT_TOKENS
        )
        max_tokens = entry_max_tokens or entry_max_output or base_max_tokens
        max_output_tokens = (
            entry_max_output
            or entry_max_tokens
            or _positive_int(self.model.max_output_tokens)
            or DEFAULT_MAX_OUTPUT_TOKENS
        )
        context_window = (
            entry_context
            or _positive_int(self.model.context_window)
            or int(self.context.max_context_length or DEFAULT_CONTEXT_WINDOW)
        )

        merged = {
            "name": entry.get("name") or self.model.name or "deepseek-chat",
            "api_key": os.getenv("LLM_API_KEY") or entry.get("api_key") or self.model.api_key,
            "base_url": os.getenv("LLM_API_URL") or entry.get("base_url") or self.model.base_url,
            "temperature": self.model.temperature,
            "max_tokens": max_tokens,
            "context_window": context_window,
            "max_output_tokens": max_output_tokens,
            "gateway": os.getenv("LLM_GATEWAY") or entry.get("gateway") or self.model.gateway or "openai",
            "multimodal": bool(entry.get("multimodal", self.model.multimodal)),
        }
        pricing = entry.get("pricing")
        if not isinstance(pricing, dict):
            pricing = (self.model.pricing or {}).get(str(merged.get("name"))) or (self.model.pricing or {}).get(str(target)) or {}
        merged["pricing"] = pricing
        return merged

    @property
    def DEFAULT_MODEL(self):
        """Get 默认模型配置"""
        return self.get_model_profile()

    @property
    def MAX_REACT_ITERATIONS(self):
        """Get 最大React迭代次数"""
        return self.agent.max_react_iterations

    @property
    def MAX_SUB_AGENT_ITERATIONS(self):
        """Get SubAgent最大迭代次数"""
        return self.agent.max_sub_agent_iterations

    def validate(self) -> List[str]:
        """验证配置，返回错误消息列表"""
        errors = []

        # 检查必需的API密钥
        if (
            not self.model.api_key
            and not os.getenv("LLM_API_KEY")
            and not os.getenv("OPENAI_API_KEY")
        ):
            errors.append(
                "LLM API key not configured. Please set the environment variable LLM_API_KEY or OPENAI_API_KEY, or set model.api_key in the config file"
            )

        # 检查多模态配置（如果启 with 且当前模型是多模态的）
        # 只有当多模态功能启 with 且当前模型是Multimodal model时才检查多模态API密钥
        if self.multimodal.enabled and self.model.multimodal:
            for model_name, model_config in self.multimodal.models.items():
                # 只检查与当前模型相关的多模态配置
                model_lower = self.model.name.lower()
                config_name = model_config.get("name", "").lower()

                # 如果当前模型名称包含多模态配置的名称，则检查该配置
                if config_name in model_lower or model_lower in config_name:
                    if model_config.get("api_key") == "" and not os.getenv(
                        f"{model_config.get('provider', '').upper()}_API_KEY"
                    ):
                        errors.append(
                            f"Multimodal model {model_name} is missing an API key. Please set the environment variable {model_config.get('provider', '').upper()}_API_KEY or set it in the config file"
                        )

        # 检查搜索配置（如果启 with ）
        if (
            self.tools.enable_web_search
            and not self.tools.search_api_url
            and not os.getenv("SEARCHXNG_URL")
        ):
            errors.append(
                "Web search is enabled but the search API URL is not configured. Please set the SEARCHXNG_URL environment variable or set tools.search_api_url in the config file"
            )

        # Context policy sanity: ratios and retention must be coherent.
        try:
            ratio = float(self.context.window_ratio)
            retain_ratio = float(self.context.retain_ratio)
            if not (0 < ratio <= 1):
                errors.append("context.window_ratio must be in (0, 1]")
            if not (0 < retain_ratio < ratio):
                errors.append("context.retain_ratio must be in (0, window_ratio)")
            if int(self.context.headroom_tokens) < 0:
                errors.append("context.headroom_tokens must be non-negative")
            if str(self.context.summary_mode).lower() not in ("off", "adaptive", "always"):
                errors.append("context.summary_mode must be off, adaptive, or always")
        except (TypeError, ValueError):
            errors.append("context window/retain ratios and headroom must be numeric")

        # The model must have room for the reserved output plus compaction headroom.
        profile = self.get_model_profile()
        try:
            window = int(profile.get("context_window") or 1_000_000)
            output = int(profile.get("max_output_tokens") or profile.get("max_tokens") or 0)
            headroom = int(self.context.headroom_tokens or 0)
            if window <= 0:
                errors.append("Model context_window must be a positive integer")
            elif output + headroom >= window:
                errors.append(
                    f"Model context_window ({window}) is too small for "
                    f"max_output_tokens ({output}) + headroom ({headroom}); "
                    "reduce the output cap or headroom, or choose a larger-window model"
                )
        except (TypeError, ValueError):
            errors.append("Model context_window / max_output_tokens must be integers")

        return errors

    def get_validated_config(self) -> Dict[str, Any]:
        """Get 验证后的配置（如果验证失败则抛出异常）"""
        errors = self.validate()
        if errors:
            raise ValueError(
                f"Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
            )

        return {
            "model": asdict(self.model),
            "tools": asdict(self.tools),
            "safety": asdict(self.safety),
            "context": asdict(self.context),
            "agent": asdict(self.agent),
            "mcp": asdict(self.mcp),
            "output": asdict(self.output),
            "timeouts": asdict(self.timeouts),
            "limits": asdict(self.limits),
            "skills": asdict(self.skills),
            "multimodal": asdict(self.multimodal),
            "diff_hook": asdict(self.diff_hook),
        }


# 全局设置实例
settings = Settings()
