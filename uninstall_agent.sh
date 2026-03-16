#!/bin/zsh
# ============================================================
# BestPartners Agent 卸载脚本
# ============================================================

set -e

LABEL="com.yangkai.bestpartners"
PLIST_DEST="$HOME/Library/LaunchAgents/com.yangkai.bestpartners.plist"

echo "=================================================="
echo "  BestPartners Agent 卸载程序"
echo "=================================================="
echo ""

# 停止并卸载
if launchctl list "$LABEL" &>/dev/null; then
    echo "正在停止 Agent..."
    launchctl unload "$PLIST_DEST" 2>/dev/null && echo "✅ 已停止" || echo "⚠️ 停止时出现警告"
else
    echo "Agent 当前未运行"
fi

# 删除 plist 文件
if [ -f "$PLIST_DEST" ]; then
    rm "$PLIST_DEST"
    echo "✅ 已删除: $PLIST_DEST"
else
    echo "ℹ️  plist 文件不存在，可能已被删除"
fi

echo ""
echo "✅ 卸载完成。调度器已不再自动运行。"
echo ""
echo "注意：日志文件和 .env 文件未被删除，如需清理请手动执行。"
