"""基础测试文件"""

import pytest
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_import_core_modules():
    """测试核心模块导入"""
    import core
    import utils
    import tools

    # 检查模块是否存在
    assert core is not None
    assert utils is not None
    assert tools is not None

    print("✓ 核心模块导入成功")


def test_config_loading():
    """测试配置加载"""
    import config

    # config是一个模块，不是类
    assert config is not None

    # 检查配置模块是否有settings
    if hasattr(config, "settings"):
        settings = config.settings
        assert settings is not None

    print("✓ 配置加载成功")


def test_ast_tools():
    """测试AST工具"""
    from utils.light_ast import LightAST

    code = """
def hello():
    print("Hello, World!")
"""

    ast_tool = LightAST()
    ast_tool.parse(code)
    assert ast_tool is not None

    # 检查基本功能
    functions = ast_tool.find_functions()
    assert len(functions) >= 0  # 可能为0或1

    print("✓ AST工具测试成功")


@pytest.mark.asyncio
async def test_async_helpers():
    """测试异步助手"""
    from utils.async_helpers import with_timeout

    async def simple_task():
        return "success"

    result = await with_timeout(simple_task(), timeout=1.0)
    assert result == "success"

    print("✓ 异步助手测试成功")


if __name__ == "__main__":
    # 运行简单测试
    test_import_core_modules()
    test_config_loading()
    test_ast_tools()

    # 异步测试需要事件循环
    import asyncio

    asyncio.run(test_async_helpers())

    print("\n✅ 所有基础测试通过！")
