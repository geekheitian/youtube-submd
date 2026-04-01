#!/bin/bash
# youtumd Shell 包装器

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/youtumd.py"

# 确保使用正确的 Python
PYTHON=$(which python3)

# 执行
exec $PYTHON "$PYTHON_SCRIPT" "$@"
