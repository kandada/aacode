#!/usr/bin/env python3
"""
项目initialized脚本
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from aacode.i18n import t


def init_project():
    """initialized项目环境"""
    print("🚀 Initializing AACode...")

    # 检查Python版本
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        sys.exit(1)

    print(f"✅ Python version: {sys.version}")

    # 检查是否已经在虚拟环境中
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        print("⚠️  Detected running inside a virtual environment")
        print("   It is recommended to run init.py with the system Python to create an independent .aacode virtual environment")
        response = input("Continue? (y/N): ").strip().lower()
        if response != "y":
            print("Exiting initialization")
            sys.exit(0)

    # Creating virtual environment
    venv_path = Path(".venv")
    if not venv_path.exists():
        print("📦 Creating virtual environment...")
        os.system(f"{sys.executable} -m venv .venv")
        print("✅ Virtual environment created")
    else:
        print("✅ Virtual environment already exists")

    # 安装依赖
    print("📥 Installing dependencies...")
    if os.name == "nt":  # Windows
        activate_cmd = ".venv\\Scripts\\activate"
        pip_cmd = ".venv\\Scripts\\pip"
    else:  # Unix/Linux/Mac
        activate_cmd = "source .venv/bin/activate"
        pip_cmd = ".venv/bin/pip"

    install_result = os.system(
        f"{pip_cmd} install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
    )
    if install_result == 0:
        print("✅ Dependencies installed")
    else:
        print("❌ Dependency installation failed")
        sys.exit(1)

    # 检查是否已存在.env配置文件
    env_file = Path(".env")
    config = {}
    config_exists = False

    if env_file.exists():
        print("\n📄 Detected existing .env configuration file")
        skip_choice = input("Skip model configuration and use existing config? (Y/n): ").strip().lower()
        if skip_choice in ["", "y", "yes"]:
            print("✅ Skipping model configuration, using existing config")
            # 读取现有配置  for后续步骤
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        config[key] = value

            # 标记配置已存在，跳过配置步骤
            config_exists = True
        else:
            print("🔧 Starting new model configuration")

    if not config_exists:
        # 设置环境变量提示
        print("\n🔧 Configure model settings:")
        print("Please configure your model settings:")

        # 交互式Get  user配置
        config = {}

        # 网关选择
        print("\nSelect gateway type:")
        print("1. Anthropic (supports MiniMax-M2.5)")
        print("2. OpenAI (supports DeepSeek, Kimi, GPT)")
        print("3. Custom")
        gateway_choice = input("Select (1/2/3): ").strip()

        if gateway_choice == "1":
            gateway = "anthropic"
            print("✅ Selected Anthropic gateway (supports MiniMax-M2.5)")
        elif gateway_choice == "2":
            gateway = "openai"
            print("✅ Selected OpenAI gateway")
        elif gateway_choice == "3":
            gateway = input("Enter gateway type (anthropic/openai): ").strip().lower()
            while gateway not in ["anthropic", "openai"]:
                print("❌ Gateway type must be 'anthropic' or 'openai'")
                gateway = input("Enter gateway type (anthropic/openai): ").strip().lower()
        else:
            gateway = "openai"

        config["LLM_GATEWAY"] = gateway

        # 模型选择
        print("\nPreset models:")
        print("1. deepseek-chat (OpenAI gateway)")
        print("2. MiniMax-M2.5 (Anthropic gateway, multimodal)")
        print("3. kimi-k2.5 (OpenAI gateway, multimodal)")
        print("4. gpt4 (OpenAI gateway)")
        print("5. Custom")
        model_choice = input("Select (1/2/3/4/5): ").strip()

        if model_choice == "1":
            model_name = "deepseek-chat"
        elif model_choice == "2":
            model_name = "MiniMax-M2.5"
        elif model_choice == "3":
            model_name = "kimi-k2.5"
            # 询问 user确认模型名称格式
            print(f"\n⚠️  Note: Kimi model name may have different formats")
            print(f"Default: {model_name}")
            custom_name = input(
                "If you need another format, enter model name (press Enter for default): "
            ).strip()
            if custom_name:
                model_name = custom_name
                print(f"✅ Using custom model name: {model_name}")
        elif model_choice == "4":
            model_name = "gpt4"
        elif model_choice == "5":
            model_name = input("Enter model name: ").strip()
            while not model_name:
                print("❌ Model name cannot be empty")
                model_name = input("Enter model name: ").strip()
        else:
            model_name = "deepseek-chat"

        config["LLM_MODEL_NAME"] = model_name

        # API URL (根据模型和网关自动设置默认值)
        print(f"\nModel '{model_name}' default API URL:")

        # 根据模型和网关设置默认URL
        model_lower = model_name.lower()
        if "minimax" in model_lower:
            if gateway == "anthropic":
                # MiniMax使 with Anthropic网关时，需要/anthropic端点（避免重复/v1）
                default_url = "https://api.minimax.chat/anthropic"
            else:
                # MiniMax使 with OpenAI网关时，使 with 标准/v1端点
                default_url = "https://api.minimax.chat/v1"
        elif "kimi" in model_lower:
            default_url = "https://api.moonshot.cn/v1"
            if gateway == "anthropic":
                default_url = "https://api.moonshot.cn/anthropic"
            else:
                default_url = "https://api.moonshot.cn/v1"
        elif "deepseek" in model_lower:
            # default_url = "https://api.deepseek.com/v1"
            if gateway == "anthropic":
                default_url = "https://api.deepseek.com/anthropic"
            else:
                default_url = "https://api.deepseek.com/v1"
        else:
            default_url = "https://api.openai.com/v1"

        print(f"Default: {default_url}")
        if "minimax" in model_lower and gateway == "anthropic":
            print(
                "💡 Tip: When using MiniMax with the Anthropic gateway, use the /anthropic endpoint to avoid duplicate /v1 path issues. Similar for other models."
            )
            # print("")

        url_choice = input("Press Enter for default URL, or enter a custom URL: ").strip()

        if url_choice:
            api_url = url_choice
        else:
            api_url = default_url

        # 检查MiniMax + Anthropic网关的URL兼容性
        if "minimax" in model_lower and gateway == "anthropic":
            # 如果 user输入了/v1结尾的URL，警告可能有问题
            if api_url.endswith("/v1") and not api_url.endswith("/v1/anthropic"):
                print(
                    f"\n⚠️  Warning: When using MiniMax with the Anthropic gateway, a URL ending with /v1 may cause duplicate path issues"
                )
                print(f"   Current URL: {api_url}")
                print(
                    f"   Suggested: {api_url}/anthropic or {api_url.replace('/v1', '/anthropic')}"
                )

                adjust_choice = (
                    input("Auto-adjust to /anthropic endpoint? (Y/n): ").strip().lower()
                )
                if adjust_choice in ["", "y", "yes"]:
                    # 自动调整URL
                    if api_url.endswith("/v1"):
                        api_url = api_url[:-3] + "/anthropic"
                    else:
                        api_url = api_url.rstrip("/") + "/anthropic"
                    print(f"✅ URL adjusted to: {api_url}")

        config["LLM_API_URL"] = api_url

        # API Key
        api_key = input("Enter LLM_API_KEY: ").strip()
        while not api_key:
            print("❌ API Key cannot be empty")
            api_key = input("Enter LLM_API_KEY: ").strip()
        config["LLM_API_KEY"] = api_key

        # 多模态支持检测和配置
        multimodal_models = ["minimax", "kimi"]
        is_multimodal = any(m in model_name.lower() for m in multimodal_models)

        if is_multimodal:
            print(f"\n✅ Model '{model_name}' supports multimodal")
            print("   Multimodal tools will automatically use this model")

            # 询问是否要启 with 多模态功能
            print("\n🔍 Multimodal feature configuration:")
            print("Multimodal features allow AI to understand images, videos, and UI designs")
            print("When enabled, the following tools are available:")
            print("  - understand_image: Understand image content")
            print("  - understand_video: Understand video content")
            print("  - understand_ui_design: Analyze UI designs")
            print("  - analyze_image_consistency: Analyze image consistency")

            enable_multimodal = input("Enable multimodal features? (Y/n): ").strip().lower()
            if enable_multimodal in ["", "y", "yes"]:
                config["LLM_MULTIMODAL"] = "true"
                print("✅ Multimodal features enabled")

                # 如果选择了Multimodal model，询问是否使 with 相同的API密钥
                use_same_key = (
                    input(
                        f"Use the same API key for multimodal calls? (If not, configure separately in aacode_config.yaml) (Y/n): "
                    )
                    .strip()
                    .lower()
                )
                if use_same_key in ["", "y", "yes"]:
                    print("✅ Will use the same API key")
                    # 不需要额外设置，代码会自动使 with 主模型的API密钥
                else:
                    # 询问多模态专 with API密钥
                    multimodal_key = input(
                        "Enter dedicated multimodal API key (press Enter to skip): "
                    ).strip()
                    if multimodal_key:
                        config["MULTIMODAL_API_KEY"] = multimodal_key
                        print("✅ Dedicated multimodal API key set")
            else:
                config["LLM_MULTIMODAL"] = "false"
                print("ℹ️  Multimodal features disabled")
        else:
            # 对于非Multimodal model，询问是否要启 with 多模态功能
            print("\n🔍 Multimodal feature configuration:")
            print("The selected model does not support multimodal")
            print("But you can enable multimodal features to use other models for image/video understanding")

            enable_multimodal = input("Enable multimodal features? (y/N): ").strip().lower()
            if enable_multimodal in ["y", "yes"]:
                config["LLM_MULTIMODAL"] = "true"
                print("✅ Multimodal features enabled")

                # 询问Multimodal model选择
                print("\nSelect multimodal model:")
                print("1. Kimi K2.5 (recommended, supports images and videos)")
                print("2. MiniMax M2.5 (supports images and videos)")
                print("3. Use main model (if supported)")
                multimodal_choice = input("Select (1/2/3): ").strip()

                if multimodal_choice == "1":
                    config["MULTIMODAL_MODEL"] = "moonshot_kimi_k2.5"
                    print("✅ Selected Kimi K2.5 as multimodal model")

                    # 询问API密钥
                    multimodal_key = input(
                        "Enter Kimi API key (press Enter to use main model key): "
                    ).strip()
                    if multimodal_key:
                        config["MULTIMODAL_API_KEY"] = multimodal_key
                        print("✅ Kimi API key set")

                elif multimodal_choice == "2":
                    config["MULTIMODAL_MODEL"] = "minimax_m2.5"
                    print("✅ Selected MiniMax M2.5 as multimodal model")

                    # 询问API密钥
                    multimodal_key = input(
                        "Enter MiniMax API key (press Enter to use main model key): "
                    ).strip()
                    if multimodal_key:
                        config["MULTIMODAL_API_KEY"] = multimodal_key
                        print("✅ MiniMax API key set")

                else:
                    print("ℹ️  Will attempt to use main model for multimodal calls")
            else:
                config["LLM_MULTIMODAL"] = "false"
                print("ℹ️  Multimodal features disabled")

    # 创建配置文件（只有当需要新配置时才创建）
    if not config_exists:
        config_file = Path(".env")
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(f"LLM_API_KEY={config['LLM_API_KEY']}\n")
            f.write(f"LLM_API_URL={config['LLM_API_URL']}\n")
            f.write(f"LLM_MODEL_NAME={config['LLM_MODEL_NAME']}\n")
            f.write(f"LLM_GATEWAY={config['LLM_GATEWAY']}\n")

            # 写入多模态配置
            if "LLM_MULTIMODAL" in config:
                f.write(f"LLM_MULTIMODAL={config['LLM_MULTIMODAL']}\n")

            if "MULTIMODAL_API_KEY" in config:
                f.write(f"MULTIMODAL_API_KEY={config['MULTIMODAL_API_KEY']}\n")

            if "MULTIMODAL_MODEL" in config:
                f.write(f"MULTIMODAL_MODEL={config['MULTIMODAL_MODEL']}\n")

        print(f"\n✅ Config saved to: {config_file}")
    else:
        print(f"\n✅ Using existing config: {env_file}")

    # 创建启动脚本
    if os.name == "nt":  # Windows
        script_content = f"""@echo off
{activate_cmd}
for /f "tokens=1,2 delims==" %%a in (.env) do set %%a=%%b
python main.py %%*
"""
        script_name = "run.bat"
    else:  # Unix/Linux/Mac
        script_content = f"""#!/bin/bash
{activate_cmd}
set -a
source .env
set +a
python main.py "$@"
"""
        script_name = "run.sh"

    with open(script_name, "w", encoding="utf-8") as f:
        f.write(script_content)

    if os.name != "nt":
        os.chmod(script_name, 0o755)

    print(f"\n🎯 Created launch script: {script_name}")

    # 创建激活脚本（  for手动Activating virtual environment）
    if os.name != "nt":  # Unix/Linux/Mac
        activate_script = "activate.sh"
        with open(activate_script, "w", encoding="utf-8") as f:
            f.write(f"""#!/bin/bash
echo "Activating AACode virtual environment..."
{activate_cmd}
export AACODE_PROJECT_ROOT=$(pwd)
echo "✅ Virtual environment activated"
echo "Project root: $AACODE_PROJECT_ROOT"
""")
        os.chmod(activate_script, 0o755)
        print(f"🎯 Created activate script: {activate_script}")
        print("  Run: source activate.sh to activate virtual environment")

    print("\n📋 Usage Guide:")
    print("1. Activating virtual environment:")
    if os.name == "nt":
        print(f'   Running: {script_name} -p examples/my_project "your task"')
        print("   (The script will automatically activate the virtual environment)")
    else:
        print(f"   Method 1: source activate.sh (then run: python main.py ...)")
        print(f'   Method 2: ./{script_name} -p examples/my_project "your task"')
        print("   (The script will automatically activate the virtual environment)")

    print("\n2. Check if virtual environment is activated:")
    print("   Running: which python")
    print("   Should show: .venv/bin/python")

    print("\n3. Run AACode:")
    print('   python main.py -p examples/my_project "your task"')

    print("\n🎉 Initialization complete!")
    print("\n⚠️  Note: init.py does not automatically activate the virtual environment in the current shell")
    print("   Please manually activate following the guide above")


if __name__ == "__main__":
    init_project()
