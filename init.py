#!/usr/bin/env python3
"""
项目初始化脚本
"""

import os
import sys
from pathlib import Path


def init_project():
    """初始化项目环境"""
    print("🚀 初始化AACode程序...")

    # 检查Python版本
    if sys.version_info < (3, 8):
        print("❌ 需要Python 3.8或更高版本")
        sys.exit(1)

    print(f"✅ Python版本: {sys.version}")

    # 检查是否已经在虚拟环境中
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        print("⚠️  检测到当前已在虚拟环境中")
        print("   建议在系统Python中运行init.py，以便创建独立的.aacode虚拟环境")
        response = input("是否继续? (y/N): ").strip().lower()
        if response != "y":
            print("退出初始化")
            sys.exit(0)

    # 创建虚拟环境
    venv_path = Path(".venv")
    if not venv_path.exists():
        print("📦 创建虚拟环境...")
        os.system(f"{sys.executable} -m venv .venv")
        print("✅ 虚拟环境创建完成")
    else:
        print("✅ 虚拟环境已存在")

    # 安装依赖
    print("📥 安装依赖...")
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
        print("✅ 依赖安装完成")
    else:
        print("❌ 依赖安装失败")
        sys.exit(1)

    # 检查是否已存在.env配置文件
    env_file = Path(".env")
    config = {}
    config_exists = False

    if env_file.exists():
        print("\n📄 检测到已存在的.env配置文件")
        skip_choice = input("是否跳过模型配置，使用现有配置? (Y/n): ").strip().lower()
        if skip_choice in ["", "y", "yes"]:
            print("✅ 跳过模型配置，使用现有配置")
            # 读取现有配置用于后续步骤
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        config[key] = value

            # 标记配置已存在，跳过配置步骤
            config_exists = True
        else:
            print("🔧 开始配置新的模型设置")

    if not config_exists:
        # 设置环境变量提示
        print("\n🔧 设置模型配置:")
        print("请设置你的模型配置:")

        # 交互式获取用户配置
        config = {}

        # 网关选择
        print("\n选择网关类型:")
        print("1. Anthropic (支持MiniMax-M2.5)")
        print("2. OpenAI (支持DeepSeek、Kimi、GPT)")
        print("3. 自定义")
        gateway_choice = input("选择(1/2/3): ").strip()

        if gateway_choice == "1":
            gateway = "anthropic"
            print("✅ 选择Anthropic网关 (MiniMax-M2.5)")
        elif gateway_choice == "2":
            gateway = "openai"
            print("✅ 选择OpenAI网关")
        elif gateway_choice == "3":
            gateway = input("请输入网关类型 (anthropic/openai): ").strip().lower()
            while gateway not in ["anthropic", "openai"]:
                print("❌ 网关类型必须是 'anthropic' 或 'openai'")
                gateway = input("请输入网关类型 (anthropic/openai): ").strip().lower()
        else:
            gateway = "openai"

        config["LLM_GATEWAY"] = gateway

        # 模型选择
        print("\n预选模型:")
        print("1. deepseek-chat (OpenAI网关)")
        print("2. MiniMax-M2.5 (Anthropic网关，多模态)")
        print("3. kimi-k2.5 (OpenAI网关，多模态)")
        print("4. gpt4 (OpenAI网关)")
        print("5. 自定义")
        model_choice = input("选择(1/2/3/4/5): ").strip()

        if model_choice == "1":
            model_name = "deepseek-chat"
        elif model_choice == "2":
            model_name = "MiniMax-M2.5"
        elif model_choice == "3":
            model_name = "kimi-k2.5"
            # 询问用户确认模型名称格式
            print(f"\n⚠️  注意: Kimi模型名称可能有不同格式")
            print(f"默认使用: {model_name}")
            custom_name = input(
                "如果需要使用其他格式，请输入模型名称 (按Enter使用默认): "
            ).strip()
            if custom_name:
                model_name = custom_name
                print(f"✅ 使用自定义模型名称: {model_name}")
        elif model_choice == "4":
            model_name = "gpt4"
        elif model_choice == "5":
            model_name = input("请输入模型名称: ").strip()
            while not model_name:
                print("❌ 模型名称不能为空")
                model_name = input("请输入模型名称: ").strip()
        else:
            model_name = "deepseek-chat"

        config["LLM_MODEL_NAME"] = model_name

        # API URL (根据模型和网关自动设置默认值)
        print(f"\n模型 '{model_name}' 的默认API URL:")

        # 根据模型和网关设置默认URL
        model_lower = model_name.lower()
        if "minimax" in model_lower:
            if gateway == "anthropic":
                # MiniMax使用Anthropic网关时，需要/anthropic端点（避免重复/v1）
                default_url = "https://api.minimax.chat/anthropic"
            else:
                # MiniMax使用OpenAI网关时，使用标准/v1端点
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

        print(f"默认: {default_url}")
        if "minimax" in model_lower and gateway == "anthropic":
            print(
                "💡 提示: MiniMax使用Anthropic网关时，需要使用/anthropic端点，避免重复的/v1路径问题。其他模型类似"
            )
            # print("")

        url_choice = input("按Enter使用默认URL，或输入自定义URL: ").strip()

        if url_choice:
            api_url = url_choice
        else:
            api_url = default_url

        # 检查MiniMax + Anthropic网关的URL兼容性
        if "minimax" in model_lower and gateway == "anthropic":
            # 如果用户输入了/v1结尾的URL，警告可能有问题
            if api_url.endswith("/v1") and not api_url.endswith("/v1/anthropic"):
                print(
                    f"\n⚠️  警告: MiniMax使用Anthropic网关时，URL以/v1结尾可能导致重复路径问题"
                )
                print(f"   当前URL: {api_url}")
                print(
                    f"   建议使用: {api_url}/anthropic 或 {api_url.replace('/v1', '/anthropic')}"
                )

                adjust_choice = (
                    input("是否自动调整为/anthropic端点? (Y/n): ").strip().lower()
                )
                if adjust_choice in ["", "y", "yes"]:
                    # 自动调整URL
                    if api_url.endswith("/v1"):
                        api_url = api_url[:-3] + "/anthropic"
                    else:
                        api_url = api_url.rstrip("/") + "/anthropic"
                    print(f"✅ URL已调整为: {api_url}")

        config["LLM_API_URL"] = api_url

        # API Key
        api_key = input("请输入LLM_API_KEY: ").strip()
        while not api_key:
            print("❌ API Key不能为空")
            api_key = input("请输入LLM_API_KEY: ").strip()
        config["LLM_API_KEY"] = api_key

        # 多模态支持检测和配置
        multimodal_models = ["minimax", "kimi"]
        is_multimodal = any(m in model_name.lower() for m in multimodal_models)

        if is_multimodal:
            print(f"\n✅ 模型 '{model_name}' 支持多模态功能")
            print("   多模态工具将自动使用此模型")

            # 询问是否要启用多模态功能
            print("\n🔍 多模态功能配置:")
            print("多模态功能允许AI理解图片、视频和UI设计")
            print("启用后可以使用以下工具:")
            print("  - understand_image: 理解图片内容")
            print("  - understand_video: 理解视频内容")
            print("  - understand_ui_design: 分析UI设计")
            print("  - analyze_image_consistency: 分析图片一致性")

            enable_multimodal = input("是否启用多模态功能? (Y/n): ").strip().lower()
            if enable_multimodal in ["", "y", "yes"]:
                config["LLM_MULTIMODAL"] = "true"
                print("✅ 多模态功能已启用")

                # 如果选择了多模态模型，询问是否使用相同的API密钥
                use_same_key = (
                    input(
                        f"是否使用相同的API密钥进行多模态调用?（如果不使用，则自行在aacode_config.yaml中配置） (Y/n): "
                    )
                    .strip()
                    .lower()
                )
                if use_same_key in ["", "y", "yes"]:
                    print("✅ 将使用相同的API密钥")
                    # 不需要额外设置，代码会自动使用主模型的API密钥
                else:
                    # 询问多模态专用API密钥
                    multimodal_key = input(
                        "请输入多模态专用API密钥 (按Enter跳过): "
                    ).strip()
                    if multimodal_key:
                        config["MULTIMODAL_API_KEY"] = multimodal_key
                        print("✅ 多模态专用API密钥已设置")
            else:
                config["LLM_MULTIMODAL"] = "false"
                print("ℹ️  多模态功能已禁用")
        else:
            # 对于非多模态模型，询问是否要启用多模态功能
            print("\n🔍 多模态功能配置:")
            print("当前选择的模型不支持多模态功能")
            print("但你可以启用多模态功能，使用其他模型进行图片/视频理解")

            enable_multimodal = input("是否启用多模态功能? (y/N): ").strip().lower()
            if enable_multimodal in ["y", "yes"]:
                config["LLM_MULTIMODAL"] = "true"
                print("✅ 多模态功能已启用")

                # 询问多模态模型选择
                print("\n选择多模态模型:")
                print("1. Kimi K2.5 (推荐，支持图片和视频)")
                print("2. MiniMax M2.5 (支持图片和视频)")
                print("3. 使用主模型 (如果支持)")
                multimodal_choice = input("选择(1/2/3): ").strip()

                if multimodal_choice == "1":
                    config["MULTIMODAL_MODEL"] = "moonshot_kimi_k2.5"
                    print("✅ 选择Kimi K2.5作为多模态模型")

                    # 询问API密钥
                    multimodal_key = input(
                        "请输入Kimi API密钥 (按Enter使用主模型密钥): "
                    ).strip()
                    if multimodal_key:
                        config["MULTIMODAL_API_KEY"] = multimodal_key
                        print("✅ Kimi API密钥已设置")

                elif multimodal_choice == "2":
                    config["MULTIMODAL_MODEL"] = "minimax_m2.5"
                    print("✅ 选择MiniMax M2.5作为多模态模型")

                    # 询问API密钥
                    multimodal_key = input(
                        "请输入MiniMax API密钥 (按Enter使用主模型密钥): "
                    ).strip()
                    if multimodal_key:
                        config["MULTIMODAL_API_KEY"] = multimodal_key
                        print("✅ MiniMax API密钥已设置")

                else:
                    print("ℹ️  将尝试使用主模型进行多模态调用")
            else:
                config["LLM_MULTIMODAL"] = "false"
                print("ℹ️  多模态功能已禁用")

    # 创建配置文件（只有当需要新配置时才创建）
    if not config_exists:
        config_file = Path(".env")
        with open(config_file, "w") as f:
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

        print(f"\n✅ 配置已保存到: {config_file}")
    else:
        print(f"\n✅ 使用现有配置: {env_file}")

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

    with open(script_name, "w") as f:
        f.write(script_content)

    if os.name != "nt":
        os.chmod(script_name, 0o755)

    print(f"\n🎯 创建了启动脚本: {script_name}")

    # 创建激活脚本（用于手动激活虚拟环境）
    if os.name != "nt":  # Unix/Linux/Mac
        activate_script = "activate.sh"
        with open(activate_script, "w") as f:
            f.write(f"""#!/bin/bash
echo "激活AACode虚拟环境..."
{activate_cmd}
export AACODE_PROJECT_ROOT=$(pwd)
echo "✅ 虚拟环境已激活"
echo "项目根目录: $AACODE_PROJECT_ROOT"
""")
        os.chmod(activate_script, 0o755)
        print(f"🎯 创建了激活脚本: {activate_script}")
        print("  运行: source activate.sh 来激活虚拟环境")

    print("\n📋 使用指南:")
    print("1. 激活虚拟环境:")
    if os.name == "nt":
        print(f'   运行: {script_name} -p examples/my_project "你的任务描述"')
        print("   (脚本会自动激活虚拟环境)")
    else:
        print(f"   方法1: source activate.sh (然后运行: python main.py ...)")
        print(f'   方法2: ./{script_name} -p examples/my_project "你的任务描述"')
        print("   (脚本会自动激活虚拟环境)")

    print("\n2. 检查虚拟环境是否激活:")
    print("   运行: which python")
    print("   应该显示: .venv/bin/python")

    print("\n3. 运行AACode:")
    print('   python main.py -p examples/my_project "你的任务描述"')

    print("\n🎉 初始化完成!")
    print("\n⚠️  注意: init.py脚本不会自动激活当前shell的虚拟环境")
    print("   请按照上述指南手动激活")


if __name__ == "__main__":
    init_project()
