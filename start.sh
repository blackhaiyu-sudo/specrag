#!/bin/bash
# SpecRAG 启动脚本
# 设置必要的环境变量和启动应用
#
# 用法:
#   ./start.sh          # 生产模式
#   ./start.sh dev      # 研发模式
#   ./start.sh --dev    # 研发模式

# 解析命令行参数
MODE="production"
if [[ "$1" == "dev" ]] || [[ "$1" == "--dev" ]]; then
    MODE="development"
    export DEBUG=True
    echo "研发模式已启用"
else
    export DEBUG=False
    echo "生产模式已启用"
fi

# 设置 OpenMP 环境变量 (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    export LDFLAGS="-L/opt/homebrew/opt/libomp/lib"
    export CPPFLAGS="-I/opt/homebrew/opt/libomp/include"
    export DYLD_LIBRARY_PATH="/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH"
fi

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "虚拟环境已激活"
else
    echo "警告: 未找到虚拟环境 (.venv)"
fi

# 启动应用
echo "启动 SpecRAG ($MODE 模式)..."
python app.py
