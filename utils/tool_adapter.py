"""
工具 Schema → API 原生 Tool Calling 格式转换适配器

将 ToolSchema 定义转换为 OpenAI / Anthropic 原生 tools 格式，
 with 于在 API 调 with 时传入 tools 参数，启 with 原生 Function Calling。
"""

import sys
from pathlib import Path
from typing import Dict, List, Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from .tool_registry import ToolSchema
else:
    from .tool_registry import ToolSchema


_TYPE_MAP_JSON_SCHEMA = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _build_json_schema_properties(
    schema: ToolSchema,
) -> tuple[dict, list]:
    """从 ToolSchema 构建 JSON Schema 的 properties 和 required 列表"""
    properties = {}
    required = []
    for param in schema.parameters:
        json_type = _TYPE_MAP_JSON_SCHEMA.get(param.type, "string")
        prop: dict = {"type": json_type, "description": param.description}
        if param.default is not None:
            prop["default"] = param.default
        properties[param.name] = prop
        if param.required:
            required.append(param.name)
    return properties, required


def to_openai_tools(schemas: Dict[str, ToolSchema]) -> list:
    """
    将 ToolSchema 字典转换为 OpenAI native tools 格式

    Args:
        schemas: {"run_shell": ToolSchema, ...}

    Returns:
        [{"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}, ...]
    """
    tools = []
    for name, schema in schemas.items():
        properties, required = _build_json_schema_properties(schema)
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": schema.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return tools


def to_anthropic_tools(schemas: Dict[str, ToolSchema]) -> list:
    """
    将 ToolSchema 字典转换为 Anthropic native tools 格式

    Args:
        schemas: {"run_shell": ToolSchema, ...}

    Returns:
        [{"name": "...", "description": "...", "input_schema": {"type": "object", ...}}, ...]
    """
    tools = []
    for name, schema in schemas.items():
        properties, required = _build_json_schema_properties(schema)
        tools.append({
            "name": name,
            "description": schema.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        })
    return tools
