#!/bin/bash
echo "激活AACode虚拟环境..."
source .venv/bin/activate
export AACODE_PROJECT_ROOT=$(pwd)
echo "✅ 虚拟环境已激活"
echo "项目根目录: $AACODE_PROJECT_ROOT"
