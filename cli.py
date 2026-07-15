#!/usr/bin/env python3
# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.

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
sys.path.insert(0, str(Path(__file__).parent.parent))
import yaml
from aacode.i18n import t
from aacode.utils.colors import style, GREEN


PRESET_MODELS = {
    "1": {
        "key": "deepseek",
        "name": "deepseek-chat",
        "gateway": "openai",
        "base_url": "https://api.deepseek.com/v1",
    },
    "2": {
        "key": "moonshot_kimi_k2.5",
        "name": "kimi-k2.5",
        "gateway": "openai",
        "base_url": "https://api.moonshot.cn/v1",
    },
    "3": {
        "key": "minimax_m2.5",
        "name": "MiniMax-M2.5",
        "gateway": "anthropic",
        "base_url": "https://api.minimax.chat/anthropic",
    },
}


def _write_env(env_file: Path, updates: dict):
    """去重更新写入 .env（保留已有其它键，覆盖同名键）"""
    existing = {}
    order = []
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            k = k.strip()
            if k not in existing:
                order.append(k)
            existing[k] = v.strip()
    for k, v in updates.items():
        if k not in existing:
            order.append(k)
        existing[k] = v
    lines = [f"{k}={existing[k]}" for k in order]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_file, 0o600)
    except OSError:
        pass


def _update_yaml_model(config_file: Path, model: dict, api_key: str):
    """读-改-写 yaml：设置 default_model 及对应模型条目的 api_key/name/base_url/gateway"""
    data = {}
    if config_file.exists():
        try:
            data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    model_section = data.get("model")
    if not isinstance(model_section, dict):
        model_section = {}
    models = model_section.get("models")
    if not isinstance(models, dict):
        models = {}
    key = model["key"]
    entry = models.get(key) if isinstance(models.get(key), dict) else {}
    entry.update(
        {
            "name": model["name"],
            "gateway": model["gateway"],
            "base_url": model["base_url"],
            "api_key": api_key,
        }
    )
    models[key] = entry
    model_section["models"] = models
    model_section["default_model"] = key
    data["model"] = model_section
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    try:
        os.chmod(config_file, 0o600)
    except OSError:
        pass


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
    """pip 安装模式：引导用户配置，持久化到 com.aacode/aacode_config.yaml 与 .env"""
    import platformdirs
    print("🚀 AACode Initialization Wizard\n")

    config_dir = Path(platformdirs.user_config_dir("com.aacode", roaming=True))
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "aacode_config.yaml"
    pkg_config = Path(__file__).parent / "aacode_config.yaml"

    if not config_file.exists() and pkg_config.exists():
        shutil.copy(pkg_config, config_file)
        print(style(t("cli.save_config", file=config_file), fg=GREEN))

    print("\nSelect model:")
    print("1. deepseek-chat (OpenAI gateway)")
    print("2. kimi-k2.5 (OpenAI gateway, multimodal)")
    print("3. MiniMax-M2.5 (Anthropic gateway, multimodal)")
    print("4. Custom")
    choice = input("Select (1/2/3/4): ").strip()

    if choice in PRESET_MODELS:
        model = dict(PRESET_MODELS[choice])
    else:
        name = input("Enter model name: ").strip()
        while not name:
            print("❌ Model name cannot be empty")
            name = input("Enter model name: ").strip()
        gateway = input("Enter gateway (openai/anthropic) [openai]: ").strip().lower() or "openai"
        while gateway not in ("openai", "anthropic"):
            print("❌ Gateway must be 'openai' or 'anthropic'")
            gateway = input("Enter gateway (openai/anthropic) [openai]: ").strip().lower() or "openai"
        base_url = input("Enter base_url: ").strip()
        while not base_url:
            print("❌ base_url cannot be empty")
            base_url = input("Enter base_url: ").strip()
        model = {"key": "custom", "name": name, "gateway": gateway, "base_url": base_url}

    print(f"\n✅ Selected model: {model['name']} ({model['gateway']}, {model['base_url']})")

    api_key = input("\nEnter API Key: ").strip()
    while not api_key:
        print("❌ API Key cannot be empty")
        api_key = input("Enter API Key: ").strip()

    _update_yaml_model(config_file, model, api_key)
    print(style(t("cli.save_config", file=config_file), fg=GREEN))

    env_file = config_dir / ".env"
    _write_env(
        env_file,
        {
            "LLM_API_KEY": api_key,
            "LLM_API_URL": model["base_url"],
            "LLM_MODEL_NAME": model["name"],
            "LLM_GATEWAY": model["gateway"],
        },
    )
    print(style(t("cli.save_env", file=env_file), fg=GREEN))

    print("\n✅ Initialization complete! Run 'aacode run' to start")


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
    """CLI main entry point"""
    if len(sys.argv) < 2:
        run_main_async([])
        return 0

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
        print("  aacode init        Initialize configuration")
        print("  aacode              进入交互会话模式（在当前目录）")
        print("  aacode <task>       在当前目录执行任务")
        print("  aacode run <task>   在当前目录执行任务")
        print('\n  aacode -p /path/to/project "task description"')
        print("  aacode --interactive")
        print("\n提示: 建议用引号包裹任务描述，如 aacode \"write a hello world program\"")

    else:
        run_main_async(sys.argv[1:])

    return 0


if __name__ == "__main__":
    sys.exit(main())
