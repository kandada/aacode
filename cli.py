#!/usr/bin/env python3
"""
aacode CLI - Command Line Interface
支持 pip install 后通过 aacode init / aacode run 运行
"""

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path


def is_git_clone_mode():
    """检测是否在 git clone 模式下运行（存在 __pycache__ 或特定标记）"""
    return Path("aacode_config.yaml").exists() and Path("init.py").exists()


def is_pip_installed_mode():
    """检测是否通过 pip 安装模式运行"""
    try:
        import aacode

        return Path(aacode.__file__).parent.parent != Path.cwd() / "aacode"
    except ImportError:
        return False


def run_init_git_clone():
    """git clone 模式：执行原始的 init.py"""
    from aacode.init import init_project

    init_project()


def run_init_pip():
    """pip 安装模式：引导用户配置"""
    print("🚀 AACode 初始化向导\n")

    home_aacode_dir = Path.home() / ".aacode"
    home_aacode_dir.mkdir(exist_ok=True)

    config_file = home_aacode_dir / "aacode_config.yaml"
    pkg_config = Path(__file__).parent / "aacode_config.yaml"

    if not config_file.exists() and pkg_config.exists():
        shutil.copy(pkg_config, config_file)
        print(f"✅ 已创建默认配置: {config_file}")

    print("\n🔧 请配置你的 API Key：")
    print("在 ~/.aacode/aacode_config.yaml 中设置 model.api_key")
    print("或设置环境变量 LLM_API_KEY\n")

    api_key = input("请输入 API Key (或直接按 Enter 使用环境变量): ").strip()
    if api_key:
        env_file = home_aacode_dir / ".env"
        with open(env_file, "a") as f:
            f.write(f"\nLLM_API_KEY={api_key}\n")
        print(f"✅ 已保存到 {env_file}")

    print("\n✅ 初始化完成！运行 'aacode run' 开始使用")


def run_main_async(args):
    """调用 main.py 中的异步主函数"""
    from aacode.main import main as main_async
    import sys

    old_argv = sys.argv
    try:
        sys.argv = ["aacode"] + args
        asyncio.run(main_async())
    finally:
        sys.argv = old_argv


def main():
    """CLI 主入口"""
    if len(sys.argv) < 2:
        print("aacode - AI Coding Assistant")
        print("\nUsage:")
        print("  aacode init    初始化配置")
        print("  aacode run     运行程序")
        print("\nOr use: python -m aacode [init|run]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        if is_git_clone_mode():
            run_init_git_clone()
        else:
            run_init_pip()

    elif command == "run":
        run_main_async(sys.argv[2:])

    elif command == "--help" or command == "-h":
        print("aacode - AI Coding Assistant")
        print("\nUsage:")
        print("  aacode init    初始化配置")
        print("  aacode run     运行程序")
        print('\n  aacode run -p /path/to/project "task description"')
        print("  aacode run --interactive")

    else:
        print(f"Unknown command: {command}")
        print("Use: aacode init | aacode run")
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
