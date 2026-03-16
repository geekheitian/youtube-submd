#!/bin/bash
# 快速运行脚本 - 放在 PATH 中或创建别名

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

cd "$BASE_DIR"

# 默认获取 BestPartners 最新视频
python3 "$SCRIPT_DIR/bestpartners_tool.py" "$@"
