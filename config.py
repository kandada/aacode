# 配置管理
# config.py
"""
配置管理
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional, List
import yaml


@dataclass
class ModelConfig:
    """模型配置"""
    name: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 8000

    def __post_init__(self):
        # 环境变量优先，yaml配置作为后备
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or self.api_key
        self.base_url = os.getenv("LLM_API_URL") or os.getenv("OPENAI_BASE_URL") or self.base_url or "https://api.openai.com/v1"
        self.name = os.getenv("LLM_MODEL_NAME") or self.name or "gpt-4"


@dataclass
class ToolConfig:
    """工具配置"""
    # 原子工具
    enable_file_ops: bool = True
    enable_shell: bool = True
    enable_search: bool = True

    # 沙箱工具
    enable_sandbox: bool = False
    sandbox_type: str = "docker"  # docker, vm, local

    # 网络工具
    enable_web_search: bool = True
    search_engine: str = "searxng"
    search_api_url: Optional[str] = None

    # 代码工具
    enable_code_execution: bool = True
    enable_testing: bool = True
    max_execution_time: int = 60


@dataclass
class SafetyConfig:
    """安全配置"""
    enable_safety_guard: bool = True
    restrict_to_project: bool = True
    allow_network: bool = False
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    dangerous_command_action: str = "reject"  # reject, ask, log


@dataclass
class ContextConfig:
    """上下文配置"""
    strategy: str = "file_based"  # file_based, memory, hybrid
    max_context_length: int = 16000
    compact_threshold: int = 12000
    history_compression: bool = True
    use_vector_store: bool = False
    # 新增：上下文缩减配置
    compact_trigger_tokens: int = 8000      # 触发缩减的token数阈值
    compact_keep_messages: int = 20         # 缩减后保留的消息数
    compact_keep_rounds: int = 8            # 缩减后保留的对话轮数（最近N轮）
    compact_summary_steps: int = 10         # 摘要包含的步骤数
    compact_protect_first_rounds: int = 3   # 保护前N轮（任务规划、初始理解）


@dataclass
class AgentConfig:
    """Agent配置"""
    max_react_iterations: int = 50
    max_sub_agent_iterations: int = 30
    enable_auto_planning: bool = True
    enable_todo_tracking: bool = True


@dataclass
class MCPConfig:
    """MCP服务器配置"""
    enabled: bool = True
    # STD类型MCP服务器配置
    # 注意：具体配置从aacode_config.yaml文件加载，这里只保留空列表
    std_servers: List[Dict[str, Any]] = field(default_factory=list)
    # SSE类型MCP服务器配置
    # 注意：具体配置从aacode_config.yaml文件加载，这里只保留空列表
    sse_servers: List[Dict[str, Any]] = field(default_factory=list)
    # 通用配置
    auto_connect: bool = True
    connection_timeout: int = 30
    max_retries: int = 3


@dataclass
class OutputConfig:
    """输出处理配置"""
    # 截断阈值（放宽限制，减少过度截断）
    test_output_threshold: int = 15000      # 测试输出阈值（从10000放宽）
    code_content_threshold: int = 30000     # 代码内容阈值（从20000放宽）
    normal_output_threshold: int = 15000     # 普通输出阈值（放宽以支持长HTML内容）
    
    # 预览长度（增加预览内容）
    test_output_preview: int = 5000         # 测试输出预览长度（从3000增加）
    code_content_preview: int = 8000        # 代码内容预览长度（从5000增加）
    normal_output_preview: int = 3000       # 普通输出预览长度（从2000增加）
    
    # 测试摘要
    test_summary_enabled: bool = True       # 是否启用测试摘要
    test_summary_max_lines: int = 20        # 摘要最大行数


@dataclass
class TimeoutConfig:
    """超时配置"""
    shell_command: int = 30         # Shell命令执行超时（秒）
    tool_execution: int = 60        # 工具执行超时（秒）
    model_summary: int = 30         # 模型摘要生成超时（秒）
    file_search: int = 5            # 文件搜索超时（秒）
    code_execution: int = 60        # 代码执行超时（秒）
    sandbox_command: int = 120      # 沙箱命令超时（秒）
    web_request: int = 30           # 网络请求超时（秒）


@dataclass
class LimitsConfig:
    """限制配置"""
    max_file_list_results: int = 100    # 文件列表最大结果数
    max_search_results: int = 20        # 搜索最大结果数
    max_retries: int = 3                # 最大重试次数
    shell_output_preview: int = 200     # Shell输出预览长度（字符）
    max_auto_read_lines: int = 200      # 超过此行数时提供分段建议
    structure_preview_lines: int = 50   # 结构预览显示的行数
    max_context_files: int = 50         # 上下文中显示的最大文件数
    prioritize_file_types: bool = True  # 是否优先显示重要文件类型


@dataclass
class SkillsConfig:
    """Skills配置"""
    enabled: bool = True                # 是否启用skills功能
    skills_dir: str = "skills"          # Skills目录（相对于项目根目录）
    auto_discover: bool = True          # 是否自动发现skills
    enabled_skills: List[str] = field(default_factory=list)  # 默认启用的skills列表（空列表，从文件加载）
    # Skills元数据配置 - 用于渐进式披露，提高token效率
    # 格式：skill_name: {name: 显示名称, description: 简短描述, trigger_keywords: [关键词列表]}
    # 注意：具体配置从skills/skills_metadata.yaml文件加载，这里只保留空字典
    skills_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class MultimodalModelConfig:
    """单个多模态模型配置"""
    name: str = ""
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    vision: bool = True
    video: bool = False
    max_image_size: int = 10485760  # 10MB
    max_video_size: int = 104857600  # 100MB
    supported_formats: Dict[str, List[str]] = field(default_factory=lambda: {
        "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
        "videos": [".mp4", ".avi", ".mov", ".mkv", ".webm"]
    })


@dataclass
class MultimodalConfig:
    """多模态模型配置"""
    enabled: bool = True               # 是否启用多模态功能
    default_model: str = "moonshot_kimi_k2.5"  # 默认使用的多模态模型
    models: Dict[str, Any] = field(default_factory=lambda: {
        "moonshot_kimi_k2.5": {
            "name": "kimi-k2.5",
            "provider": "moonshot",
            "base_url": "https://api.moonshot.cn/v1",
            "api_key": "",
            "vision": True,
            "video": True,
            "max_image_size": 10485760,
            "max_video_size": 104857600,
            "supported_formats": {
                "images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
                "videos": [".mp4", ".avi", ".mov", ".mkv", ".webm"]
            }
        }
    })


class Settings:
    """全局设置"""

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "aacode_config.yaml"
        self.config_path = Path(self.config_file)

        # 默认配置
        self.model = ModelConfig()
        self.tools = ToolConfig()
        self.safety = SafetyConfig()
        self.context = ContextConfig()
        self.agent = AgentConfig()
        self.mcp = MCPConfig()  # MCP配置
        self.output = OutputConfig()  # 输出配置
        self.timeouts = TimeoutConfig()  # 超时配置
        self.limits = LimitsConfig()  # 限制配置
        self.skills = SkillsConfig()  # Skills配置
        self.multimodal = MultimodalConfig()  # 多模态配置

        # 从文件加载配置
        self.load_config()
        
        # 从环境变量更新配置（环境变量优先）
        self._load_from_env()

    def load_config(self):
        """从文件加载配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)

                # 更新配置
                if config_data:
                    self._update_from_dict(config_data)
            except Exception as e:
                print(f"⚠️ 配置文件加载失败: {e}")

    def save_config(self):
        """保存配置到文件"""
        config_data = {
            "model": asdict(self.model),
            "tools": asdict(self.tools),
            "safety": asdict(self.safety),
            "context": asdict(self.context),
            "mcp": asdict(self.mcp),
            "skills": asdict(self.skills)
        }

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            print(f"⚠️ 配置文件保存失败: {e}")

    def _load_from_env(self):
        """从环境变量加载配置（环境变量优先）"""
        # 环境变量优先，覆盖yaml配置
        search_api_url = os.getenv("SEARCHXNG_URL")
        if search_api_url:
            self.tools.search_api_url = search_api_url
            self.tools.enable_web_search = True

    def _update_from_dict(self, config_dict: Dict[str, Any]):
        """从字典更新配置"""
        for section, values in config_dict.items():
            if section == "output":
                # 特殊处理output配置（嵌套结构）
                if isinstance(values, dict):
                    # 处理truncate_thresholds
                    if "truncate_thresholds" in values:
                        thresholds = values["truncate_thresholds"]
                        if "test_output" in thresholds:
                            self.output.test_output_threshold = thresholds["test_output"]
                        if "code_content" in thresholds:
                            self.output.code_content_threshold = thresholds["code_content"]
                        if "normal_output" in thresholds:
                            self.output.normal_output_threshold = thresholds["normal_output"]
                    
                    # 处理preview_lengths
                    if "preview_lengths" in values:
                        previews = values["preview_lengths"]
                        if "test_output" in previews:
                            self.output.test_output_preview = previews["test_output"]
                        if "code_content" in previews:
                            self.output.code_content_preview = previews["code_content"]
                        if "normal_output" in previews:
                            self.output.normal_output_preview = previews["normal_output"]
                    
                    # 处理test_summary
                    if "test_summary" in values:
                        summary = values["test_summary"]
                        if "enabled" in summary:
                            self.output.test_summary_enabled = summary["enabled"]
                        if "max_summary_lines" in summary:
                            self.output.test_summary_max_lines = summary["max_summary_lines"]
            elif section == "timeouts":
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
            
            # 加载skills/skills_metadata.yaml作为元数据源（优先级高于aacode_config.yaml中的配置）
            self._load_skills_metadata_from_file()
            
            if section == "multimodal":
                # 处理多模态配置
                if isinstance(values, dict):
                    for key, value in values.items():
                        if hasattr(self.multimodal, key):
                            setattr(self.multimodal, key, value)
            elif section == "model":
                pass  # model已在上面处理
            elif hasattr(self, section):
                section_obj = getattr(self, section)
                if hasattr(section_obj, '__dataclass_fields__'):
                    for key, value in values.items():
                        if hasattr(section_obj, key):
                            setattr(section_obj, key, value)

    @property
    def DEFAULT_MODEL(self):
        """获取默认模型配置"""
        # 环境变量优先，yaml配置作为后备
        return {
            "name": os.getenv("LLM_MODEL_NAME") or self.model.name or "deepseek-chat",
            "api_key": os.getenv("LLM_API_KEY") or self.model.api_key,
            "base_url": os.getenv("LLM_API_URL") or self.model.base_url,
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_tokens
        }
    
    @property
    def MAX_REACT_ITERATIONS(self):
        """获取最大React迭代次数"""
        return self.agent.max_react_iterations
    
    @property
    def MAX_SUB_AGENT_ITERATIONS(self):
        """获取子Agent最大迭代次数"""
        return self.agent.max_sub_agent_iterations

    def _load_skills_metadata_from_file(self):
        """从skills/skills_metadata.yaml加载配置（优先级最高）"""
        project_root = Path(__file__).parent
        skills_metadata_file = project_root / "skills" / "skills_metadata.yaml"
        
        if skills_metadata_file.exists():
            try:
                with open(skills_metadata_file, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
                
                if file_config and isinstance(file_config, dict):
                    # 读取enabled列表（文件优先）
                    file_enabled = file_config.get('enabled', [])
                    if file_enabled:
                        self.skills.enabled_skills = file_enabled
                    
                    # 读取metadata（文件优先）
                    file_metadata = file_config.get('metadata', {})
                    if file_metadata:
                        self.skills.skills_metadata = file_metadata
            except Exception as e:
                print(f"⚠️ Skills配置文件加载失败: {e}")


# 全局设置实例
settings = Settings()




