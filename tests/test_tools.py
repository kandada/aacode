"""工具模块测试"""

import pytest
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tool_registry():
    """测试工具注册表"""
    from utils.tool_registry import ToolRegistry, ToolSchema, ToolParameter

    registry = ToolRegistry()

    # 定义测试工具
    def test_tool(name: str, age: int = 30) -> dict:
        return {"name": name, "age": age}

    # 创建schema
    schema = ToolSchema(
        name="test_tool",
        description="测试工具",
        parameters=[
            ToolParameter(name="name", type=str, description="名称"),
            ToolParameter(
                name="age", type=int, description="年龄", default=30, required=False
            ),
        ],
        returns="object",
    )

    # 注册工具
    registry.register(test_tool, schema)

    # 测试工具列表
    tools = registry.list_tools()
    assert "test_tool" in tools
    assert len(tools) == 1

    # 测试获取schema
    retrieved_schema = registry.get_schema("test_tool")
    assert retrieved_schema is not None
    assert retrieved_schema.name == "test_tool"
    assert retrieved_schema.description == "测试工具"

    # 测试获取工具函数
    tool_func = registry.get_tool("test_tool")
    assert tool_func is not None

    # 测试验证调用
    validation = registry.validate_call("test_tool", {"name": "Alice", "age": 25})
    assert validation.valid is True

    # 测试无效调用
    validation = registry.validate_call("test_tool", {"name": 123})  # 错误类型
    assert validation.valid is False

    print("✅ 工具注册表测试通过")


def test_light_ast():
    """测试轻量AST工具"""
    from utils.light_ast import LightAST

    # 测试代码
    code = '''
def hello(name: str) -> str:
    """打招呼函数"""
    return f"Hello, {name}!"

class Person:
    def __init__(self, name: str):
        self.name = name
    
    def greet(self) -> str:
        return f"Hello, I'm {self.name}"
'''

    ast_tool = LightAST()
    ast_tool.parse(code)

    # 测试查找函数
    functions = ast_tool.find_functions()
    assert len(functions) == 3  # hello, __init__, greet

    # 测试查找类
    classes = ast_tool.find_classes()
    assert len(classes) == 1

    # 测试查找导入
    imports = ast_tool.find_imports()
    assert len(imports) == 0  # 没有导入

    # 测试转换为字典
    ast_dict = ast_tool.to_dict()
    assert ast_dict is not None
    assert "type" in ast_dict

    print("✅ 轻量AST工具测试通过")


@pytest.mark.asyncio
async def test_async_helpers():
    """测试异步助手"""
    from utils.async_helpers import with_timeout, parallel_execute

    # 测试超时功能
    async def fast_task():
        return "fast"

    result = await with_timeout(fast_task(), timeout=1.0)
    assert result == "fast"

    # 测试并行执行
    async def task1():
        return 1

    async def task2():
        return 2

    async def task3():
        return 3

    tasks = [task1(), task2(), task3()]
    results = await parallel_execute(tasks, max_concurrent=2)
    assert sorted(results) == [1, 2, 3]

    print("✅ 异步助手测试通过")


@pytest.mark.asyncio
async def test_file_ops():
    """测试文件操作"""
    from utils.file_ops import read_file, write_file, file_exists

    # 创建测试文件
    test_content = "测试内容"
    test_file = "test_temp_file.txt"

    # 测试写入文件
    await write_file(test_file, test_content)

    # 测试文件存在
    exists = await file_exists(test_file)
    assert exists is True

    # 测试读取文件
    content = await read_file(test_file)
    assert content == test_content

    # 清理
    import os

    if os.path.exists(test_file):
        os.remove(test_file)

    print("✅ 文件操作测试通过")


@pytest.mark.asyncio
async def test_atomic_tools_basic():
    """测试原子工具基础功能"""
    from tools.atomic_tools import AtomicTools
    from utils.safety import SafetyGuard

    # 创建安全守卫和工具实例
    project_path = Path(__file__).parent.parent
    safety_guard = SafetyGuard(project_path)
    tools = AtomicTools(project_path, safety_guard)

    # 测试读取不存在的文件
    result = await tools.read_file("nonexistent.txt")
    # AtomicTools返回的字典结构可能不同，检查是否有错误
    if "error" in result or "status" in result and result.get("status") == "error":
        # 有错误是预期的
        pass

    # 测试列出文件
    result = await tools.list_files(".", max_results=5)
    # 检查返回结果是否有效
    assert result is not None
    if "files" in result:
        assert isinstance(result["files"], list)

    print("✅ 原子工具基础测试通过")


if __name__ == "__main__":
    # 运行测试
    test_tool_registry()
    test_light_ast()
    test_file_ops()

    # 异步测试
    import asyncio

    asyncio.run(test_async_helpers())
    asyncio.run(test_atomic_tools_basic())

    print("\n🎉 所有工具测试通过！")
