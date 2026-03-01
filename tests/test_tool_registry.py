import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.tool_registry import ToolParameter, ToolSchema, ToolRegistry


class TestToolRegistry:
    """测试工具注册表"""

    def test_tool_parameter_creation(self):
        """测试工具参数创建"""
        param = ToolParameter(
            name="test_param",
            type=str,
            required=True,
            description="A test parameter"
        )
        
        assert param.name == "test_param"
        assert param.type == str
        assert param.required is True
        assert param.description == "A test parameter"

    def test_tool_parameter_validate_correct_type(self):
        """测试参数类型验证"""
        param = ToolParameter(name="test_param", type=str)
        
        is_valid, error = param.validate("hello")
        assert is_valid is True
        assert error is None

    def test_tool_parameter_validate_wrong_type(self):
        """测试参数类型验证失败"""
        param = ToolParameter(name="test_param", type=str)
        
        is_valid, error = param.validate(123)
        assert is_valid is False
        assert "期望类型为 str" in error

    def test_tool_parameter_validate_none(self):
        """测试参数为None的情况"""
        param = ToolParameter(name="test_param", type=str, required=False)
        
        is_valid, error = param.validate(None)
        assert is_valid is True

    def test_tool_schema_creation(self):
        """测试工具schema创建"""
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="param1", type=str),
                ToolParameter(name="param2", type=int, required=False)
            ]
        )
        
        assert schema.name == "test_tool"
        assert len(schema.parameters) == 2

    def test_tool_schema_validate(self):
        """测试工具schema验证"""
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="param1", type=str, required=True),
                ToolParameter(name="param2", type=int, required=False)
            ]
        )
        
        is_valid, error = schema.validate({"param1": "hello", "param2": 42})
        assert is_valid is True
        
        is_valid, error = schema.validate({"param1": "hello", "param2": "not an int"})
        assert is_valid is False

    def test_tool_schema_validate_missing_required(self):
        """测试缺少必需参数"""
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="param1", type=str, required=True)
            ]
        )
        
        is_valid, error = schema.validate({})
        assert is_valid is False
        assert "缺少必需参数" in error

    def test_tool_schema_with_aliases(self):
        """测试参数别名"""
        param = ToolParameter(
            name="file_path",
            type=str,
            aliases=["path", "f"]
        )
        
        is_valid, _ = param.validate("test.txt")
        assert is_valid is True

    def test_tool_registry_creation(self):
        """测试工具注册表创建"""
        registry = ToolRegistry()
        
        assert registry is not None
        assert len(registry.tools) == 0

    def test_tool_registry_register(self):
        """测试工具注册"""
        registry = ToolRegistry()

        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters=[]
        )
        
        # 创建一个模拟的工具函数
        def test_tool_func():
            return "test"
        
        registry.register(test_tool_func, schema)
        
        assert "test_tool" in registry.tools

    def test_tool_registry_get(self):
        """测试获取工具"""
        registry = ToolRegistry()
        
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters=[]
        )
        
        # 创建一个模拟的工具函数
        def test_tool_func():
            return "test"
        
        registry.register(test_tool_func, schema)
        retrieved = registry.get_tool("test_tool")
        
        assert retrieved is not None
        assert retrieved == test_tool_func

    def test_tool_registry_list_tools(self):
        """测试列出所有工具"""
        registry = ToolRegistry()
        
        schema1 = ToolSchema(name="tool1", description="Tool 1")
        schema2 = ToolSchema(name="tool2", description="Tool 2")
        
        # 创建模拟的工具函数
        def tool1_func():
            return "tool1"
        
        def tool2_func():
            return "tool2"
        
        registry.register(tool1_func, schema1)
        registry.register(tool2_func, schema2)
        
        tools = registry.list_tools()
        
        assert len(tools) == 2
        assert "tool1" in tools
        assert "tool2" in tools
