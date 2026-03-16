#!/bin/bash
# BestPartners 视频摘要工具 - Shell 包装器

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/bestpartners_tool.py"

# 确保使用正确的 Python
PYTHON=$(which python3)

# 执行
exec $PYTHON "$PYTHON_SCRIPT" "$@"
