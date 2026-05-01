# 工具注册表 - Tool Registry
# utils/tool_registry.py
"""
工具注册表系统
提供工具schema定义、参数验证和文档生成功能
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Tuple, Set
from difflib import get_close_matches


@dataclass
class ToolParameter:
    """工具参数定义"""

    name: str
    type: type
    required: bool = True
    default: Any = None
    description: str = ""
    example: Any = None
    aliases: List[str] = field(default_factory=list)  # 参数别名

    def validate(self, value: Any) -> Tuple[bool, Optional[str]]:
        """验证参数值"""
        # 检查类型
        if value is not None and not isinstance(value, self.type):
            return (
                False,
                f"Parameter '{self.name}' expected type {self.type.__name__}, got {type(value).__name__}",
            )
        return True, None


@dataclass
class ToolSchema:
    """工具schema定义"""

    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    returns: str = ""

    def validate(self, input_params: Dict) -> Tuple[bool, Optional[str]]:
        """验证输入参数（支持参数别名和自动映射）"""
        if input_params is None:
            input_params = {}

        # 创建参数别名映射
        normalized_params = {}
        param_map = {}  # 原始参数名 -> 标准参数名
        unknown_params = []  # 记录未知参数

        for param in self.parameters:
            param_map[param.name] = param.name
            for alias in param.aliases:
                param_map[alias] = param.name

        # 规范化输入参数（支持别名）
        for input_key, input_value in input_params.items():
            if input_key in param_map:
                standard_name = param_map[input_key]
                normalized_params[standard_name] = input_value
            else:
                # 记录未知参数
                unknown_params.append(input_key)
                normalized_params[input_key] = input_value

        # 检查必需参数
        missing_params = []
        for param in self.parameters:
            if param.required and param.name not in normalized_params:
                if param.default is None:
                    missing_params.append(param.name)

        if missing_params:
            error_msg = f"❌ Missing required parameters: {', '.join(missing_params)}\n\n"
            error_msg += "📋 Parameter details:\n"
            for param_name in missing_params:
                param = next(p for p in self.parameters if p.name == param_name)
                aliases_str = (
                    f" (aliases: {', '.join(param.aliases)})" if param.aliases else ""
                )
                error_msg += f"  • {param.name}{aliases_str} ({param.type.__name__})\n"
                error_msg += f"    {param.description}\n"
                if param.example is not None:
                    error_msg += f"    💡 Example: {param.example}\n"
            return False, error_msg

        # 检查参数类型
        type_errors = []
        for param_name, param_value in normalized_params.items():
            # 查找参数定义
            param_def = next((p for p in self.parameters if p.name == param_name), None)
            if param_def:
                valid, error = param_def.validate(param_value)
                if not valid:
                    type_errors.append(error)

        if type_errors:
            return False, "\n".join([e for e in type_errors if e])

        return True, None

    def normalize_params(self, input_params: Dict) -> Dict:
        """规范化参数（将别名转换为标准名称）"""
        if input_params is None:
            return {}

        normalized = {}
        param_map = {}

        for param in self.parameters:
            param_map[param.name] = param.name
            for alias in param.aliases:
                param_map[alias] = param.name

        for input_key, input_value in input_params.items():
            if input_key in param_map:
                standard_name = param_map[input_key]
                normalized[standard_name] = input_value
            else:
                normalized[input_key] = input_value

        return normalized

    def get_documentation(self) -> str:
        """生成工具文档"""
        doc = f"## {self.name}\n\n"
        doc += f"{self.description}\n\n"

        if self.parameters:
            doc += "### Parameters\n\n"
            for param in self.parameters:
                required_str = "Required" if param.required else "Optional"
                default_str = (
                    f", default: {param.default}" if param.default is not None else ""
                )

                # 添加别名信息
                aliases_str = ""
                if param.aliases:
                    aliases_str = f" (aliases: {', '.join(param.aliases)})"

                doc += f"- **{param.name}**{aliases_str} ({param.type.__name__}, {required_str}{default_str})\n"
                doc += f"  {param.description}\n"
                if param.example is not None:
                    doc += f"  Example: `{param.example}`\n"
                doc += "\n"

        if self.returns:
            doc += f"### Return Value\n\n{self.returns}\n\n"

        if self.examples:
            doc += "### Usage Examples\n\n"
            for i, example in enumerate(self.examples, 1):
                doc += f"Example {i}:\n```python\n"
                doc += f"{self.name}("
                params = [f"{k}={repr(v)}" for k, v in example.items()]
                doc += ", ".join(params)
                doc += ")\n```\n\n"

        return doc


@dataclass
class ValidationResult:
    """验证结果"""

    valid: bool
    error_message: Optional[str] = None
    missing_params: List[str] = field(default_factory=list)
    type_errors: Dict[str, str] = field(default_factory=dict)


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: Dict[str, ToolSchema] = {}

    def register(self, tool_func: Callable, schema: ToolSchema):
        """注册工具及其schema"""
        self.tools[schema.name] = tool_func
        self.schemas[schema.name] = schema

    def get_schema(self, tool_name: str) -> Optional[ToolSchema]:
        """Get 工具schema"""
        return self.schemas.get(tool_name)

    def get_tool(self, tool_name: str) -> Optional[Callable]:
        """Get 工具函数"""
        return self.tools.get(tool_name)

    def validate_call(self, tool_name: str, params: Dict) -> ValidationResult:
        """验证工具调 with """
        schema = self.get_schema(tool_name)
        if not schema:
            return ValidationResult(
                valid=False, error_message=f"Tool '{tool_name}' not found"
            )

        valid, error_msg = schema.validate(params)
        return ValidationResult(valid=valid, error_message=error_msg)

    def get_documentation(self, tool_name: str) -> str:
        """Get 工具文档"""
        schema = self.get_schema(tool_name)
        if not schema:
            return f"Tool '{tool_name}' not found"
        return schema.get_documentation()

    def list_tools(self) -> List[str]:
        """列出所有工具"""
        return sorted(self.schemas.keys())

    def get_all_documentation(self) -> str:
        """Get 所有工具的文档"""
        doc = "# Available Tools\n\n"
        for tool_name in self.list_tools():
            doc += self.get_documentation(tool_name)
            doc += "\n---\n\n"
        return doc

    def suggest_similar_tools(
        self, tool_name: str, max_suggestions: int = 3
    ) -> List[str]:
        """建议相似的工具名称"""
        all_tools = self.list_tools()
        matches = get_close_matches(tool_name, all_tools, n=max_suggestions, cutoff=0.6)
        return matches

    def format_tool_not_found_error(self, tool_name: str) -> str:
        """格式化工具不存在的错误消息"""
        error_msg = f"Error: Unknown tool '{tool_name}'\n\n"

        # 建议相似的工具
        similar = self.suggest_similar_tools(tool_name)
        if similar:
            error_msg += f"Did you mean one of the following tools?\n"
            for tool in similar:
                error_msg += f"  - {tool}\n"
            error_msg += "\n"

        # 列出所有可 with 工具
        error_msg += "Available tools:\n"
        for tool in self.list_tools():
            schema = self.get_schema(tool)
            if schema and schema.description:
                error_msg += f"  - {tool}: {schema.description[:60]}...\n"

        return error_msg


# 全局工具注册表实例
_global_registry = ToolRegistry()


def get_global_registry() -> ToolRegistry:
    """Get 全局工具注册表"""
    return _global_registry
