#!/bin/zsh

# ========================================================
# BestPartners 视频摘要工具 - 自动化运行脚本
# ========================================================

# 1. 加载环境变量 (API Key 等)
#    注意：Cron 运行时不会加载 .zshrc/.bash_profile，必须显式加载
#    如果您的 API Key 定义在其他文件，请修改此处
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc"
[ -f "$HOME/.bash_profile" ] && source "$HOME/.bash_profile"

# 2. 设置项目路径
PROJECT_DIR="/Users/yangkai/projects/youtube-submd"
cd "$PROJECT_DIR" || exit 1

# 3. 设置日志文件
LOG_FILE="$PROJECT_DIR/automation.log"
echo "==================================================" >> "$LOG_FILE"
echo "Starting automated run: $(date)" >> "$LOG_FILE"
echo "==================================================" >> "$LOG_FILE"

# 4. 运行 Python 脚本
#    使用 --limit 5 检查最新视频
#    使用 --no-color 避免日志中出现乱码 (如果脚本支持的话，目前脚本没这个参数，忽略)
/opt/homebrew/bin/python3 bestpartners_tool.py --limit 5 >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

echo "Finished at: $(date) with exit code $EXIT_CODE" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

exit $EXIT_CODE
