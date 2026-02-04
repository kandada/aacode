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
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  检测到当前已在虚拟环境中")
        print("   建议在系统Python中运行init.py，以便创建独立的.aacode虚拟环境")
        response = input("是否继续? (y/N): ").strip().lower()
        if response != 'y':
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
    if os.name == 'nt':  # Windows
        activate_cmd = ".venv\\Scripts\\activate"
        pip_cmd = ".venv\\Scripts\\pip"
    else:  # Unix/Linux/Mac
        activate_cmd = "source .venv/bin/activate"
        pip_cmd = ".venv/bin/pip"
    
    install_result = os.system(f"{pip_cmd} install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple")
    if install_result == 0:
        print("✅ 依赖安装完成")
    else:
        print("❌ 依赖安装失败")
        sys.exit(1)
    
    # 设置环境变量提示
    print("\n🔧 设置模型配置:")
    print("请设置你的模型配置:")
    
    # 交互式获取用户配置
    config = {}
    
    # API URL
    print("\n常用模型URL:")
    print("1. OpenAI: https://api.openai.com/v1")
    print("2. DeepSeek: https://api.deepseek.com/v1") 
    print("3. 自定义")
    url_choice = input("选择(1/2/3)或直接输入URL: ").strip()
    
    if url_choice == "1":
        api_url = "https://api.openai.com/v1"
    elif url_choice == "2":
        api_url = "https://api.deepseek.com/v1"
    elif url_choice:
        api_url = url_choice
    else:
        api_url = input("请输入LLM_API_URL: ").strip()
        while not api_url:
            print("❌ API URL不能为空")
            api_url = input("请输入LLM_API_URL: ").strip()
    
    config["LLM_API_URL"] = api_url

    # API Key
    api_key = input("请输入LLM_API_KEY: ").strip()
    while not api_key:
        print("❌ API Key不能为空")
        api_key = input("请输入LLM_API_KEY: ").strip()
    config["LLM_API_KEY"] = api_key
    
    # Model Name
    print("\n常用模型名称:")
    print("1. gpt-4")
    print("2. gpt-3.5-turbo")
    print("3. deepseek-chat")
    print("4. 自定义")
    model_choice = input("选择(1/2/3/4)或直接输入模型名称: ").strip()
    
    if model_choice == "1":
        model_name = "gpt-4"
    elif model_choice == "2":
        model_name = "gpt-3.5-turbo"
    elif model_choice == "3":
        model_name = "deepseek-chat"
    elif model_choice:
        model_name = model_choice
    else:
        model_name = input("请输入LLM_MODEL_NAME: ").strip()
        while not model_name:
            print("❌ 模型名称不能为空")
            model_name = input("请输入LLM_MODEL_NAME: ").strip()
    
    config["LLM_MODEL_NAME"] = model_name
    
    # 创建配置文件
    config_file = Path(".env")
    with open(config_file, 'w') as f:
        f.write(f"LLM_API_KEY={config['LLM_API_KEY']}\n")
        f.write(f"LLM_API_URL={config['LLM_API_URL']}\n")
        f.write(f"LLM_MODEL_NAME={config['LLM_MODEL_NAME']}\n")
    
    print(f"\n✅ 配置已保存到: {config_file}")
    
    # 创建启动脚本
    if os.name == 'nt':  # Windows
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
    
    with open(script_name, 'w') as f:
        f.write(script_content)
    
    if os.name != 'nt':
        os.chmod(script_name, 0o755)
    
    print(f"\n🎯 创建了启动脚本: {script_name}")
    
    # 创建激活脚本（用于手动激活虚拟环境）
    if os.name != 'nt':  # Unix/Linux/Mac
        activate_script = "activate.sh"
        with open(activate_script, 'w') as f:
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
    if os.name == 'nt':
        print(f"   运行: {script_name} -p examples/my_project \"你的任务描述\"")
        print("   (脚本会自动激活虚拟环境)")
    else:
        print(f"   方法1: source activate.sh (然后运行: python main.py ...)")
        print(f"   方法2: ./{script_name} -p examples/my_project \"你的任务描述\"")
        print("   (脚本会自动激活虚拟环境)")
    
    print("\n2. 检查虚拟环境是否激活:")
    print("   运行: which python")
    print("   应该显示: .venv/bin/python")
    
    print("\n3. 运行AACode:")
    print("   python main.py -p examples/my_project \"你的任务描述\"")
    
    print("\n🎉 初始化完成!")
    print("\n⚠️  注意: init.py脚本不会自动激活当前shell的虚拟环境")
    print("   请按照上述指南手动激活")

if __name__ == "__main__":
    init_project()