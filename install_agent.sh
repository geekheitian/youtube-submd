#!/bin/zsh
# ============================================================
# BestPartners Agent 安装脚本
# 将 LaunchAgent 注册到 macOS，使调度器在登录后自动运行
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$PROJECT_DIR/com.yangkai.bestpartners.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_DEST="$LAUNCH_AGENTS_DIR/com.yangkai.bestpartners.plist"
LABEL="com.yangkai.bestpartners"
ENV_FILE="$PROJECT_DIR/.env"
SCHEDULER="$PROJECT_DIR/scheduler.py"

echo "=================================================="
echo "  BestPartners Agent 安装程序"
echo "=================================================="

# 1. 检查必要文件
echo ""
echo "1️⃣  检查文件..."
if [ ! -f "$PLIST_SRC" ]; then
    echo "❌ 找不到 plist 文件: $PLIST_SRC"
    exit 1
fi
if [ ! -f "$SCHEDULER" ]; then
    echo "❌ 找不到调度脚本: $SCHEDULER"
    exit 1
fi
echo "   ✅ 文件检查通过"

# 2. 检查 Python 路径
echo ""
echo "2️⃣  检查 Python..."
PYTHON_BIN="/opt/homebrew/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    echo "   ⚠️  未找到 $PYTHON_BIN，尝试 $(which python3)"
    PYTHON_BIN="$(which python3)"
fi
echo "   Python: $PYTHON_BIN"

# 3. 确保 .env 文件存在（包含 API Key）
echo ""
echo "3️⃣  检查 API Key 配置..."
if [ ! -f "$ENV_FILE" ]; then
    echo "   ⚠️  未找到 .env 文件，正在创建模板..."
    cat > "$ENV_FILE" << 'EOF'
# BestPartners 工具 API Key 配置
# 请填入你的真实 API Key

MINIMAX_API_KEY=your_minimax_api_key_here
# DASHSCOPE_API_KEY=your_dashscope_api_key_here
# YTSUBMD_BASE_DIR=/path/to/your/obsidian/vault
EOF
    echo "   📝 已创建 .env 模板: $ENV_FILE"
    echo "   ⚠️  请先编辑 .env 文件填入真实的 API Key，然后重新运行此脚本"
    echo ""
    echo "   编辑命令：open -a TextEdit '$ENV_FILE'"
    exit 0
else
    # 检查是否还是模板值
    if grep -q "your_minimax_api_key_here" "$ENV_FILE" 2>/dev/null; then
        echo "   ⚠️  .env 文件中还是模板值，请先填入真实的 MINIMAX_API_KEY"
        echo "   编辑命令：open -a TextEdit '$ENV_FILE'"
        exit 1
    fi
    echo "   ✅ .env 文件存在"
fi

# 4. 卸载已有版本（如果存在）
echo ""
echo "4️⃣  处理已有 Agent..."
if launchctl list "$LABEL" &>/dev/null; then
    echo "   检测到已运行的 Agent，正在停止..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    echo "   ✅ 已停止旧 Agent"
fi

# 5. 安装 plist
echo ""
echo "5️⃣  安装 LaunchAgent..."
mkdir -p "$LAUNCH_AGENTS_DIR"
cp "$PLIST_SRC" "$PLIST_DEST"
echo "   ✅ 已复制到: $PLIST_DEST"

# 6. 加载并启动
echo ""
echo "6️⃣  启动 Agent..."
launchctl load "$PLIST_DEST"
sleep 2

if launchctl list "$LABEL" &>/dev/null; then
    echo "   ✅ Agent 已成功启动！"
else
    echo "   ⚠️  Agent 可能未正常启动，请检查日志"
fi

# 7. 完成提示
echo ""
echo "=================================================="
echo "  ✅ 安装完成！"
echo "=================================================="
echo ""
echo "  调度时间：每天 09:00（可在 scheduler.py 顶部修改）"
echo "  日志文件：$PROJECT_DIR/scheduler.log"
echo ""
echo "  常用命令："
echo "    查看状态：launchctl list $LABEL"
echo "    查看日志：tail -f '$PROJECT_DIR/scheduler.log'"
echo "    停止 Agent：launchctl unload '$PLIST_DEST'"
echo "    卸载 Agent：./uninstall_agent.sh"
echo ""
