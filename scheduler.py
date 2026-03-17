#!/usr/bin/env python3
"""
youtube-submd 定时调度 Agent

作为守护进程持续运行，按设定时间自动调用统一订阅入口。
可通过以下方式使用：
  - 手动运行：python3 scheduler.py
  - 后台运行：python3 scheduler.py &
  - 通过 LaunchAgent 自动管理（推荐）

日志输出到：scheduler.log（同目录）
"""

import os
import sys
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

# ===================================================
# 配置常量（根据需要修改）
# ===================================================

# 每天运行的时间（24小时制）
RUN_TIME = "09:00"

# 每次检查最新视频数量（已处理的会自动跳过）
LIMIT = 5

# 是否在启动时立即运行一次
RUN_ON_START = True

# ===================================================

PROJECT_DIR = Path(__file__).parent.resolve()
LOG_FILE = PROJECT_DIR / "scheduler.log"
TOOL_SCRIPT = PROJECT_DIR / "subscription_runner.py"
PYTHON_BIN = sys.executable


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("scheduler")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 文件 handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


SUBSCRIPTIONS_CONFIG = PROJECT_DIR / "subscriptions.yaml"


def run_tool(logger: logging.Logger) -> None:
    """调用统一入口脚本，捕获所有错误避免守护进程崩溃。"""
    if SUBSCRIPTIONS_CONFIG.exists():
        cmd = [PYTHON_BIN, str(TOOL_SCRIPT), "--all-subscriptions"]
        logger.info("subscriptions.yaml 存在，使用统一订阅模式: --all-subscriptions")
    else:
        cmd = [PYTHON_BIN, str(TOOL_SCRIPT), "--all-subscriptions"]
        logger.info("未找到 subscriptions.yaml，仍尝试使用统一订阅入口")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=False,      # 让工具自己打印输出
            timeout=1800,              # 最大运行 30 分钟
        )
        if result.returncode == 0:
            logger.info("运行完成 ✅")
        else:
            logger.warning(f"工具退出码非零: {result.returncode}")
    except subprocess.TimeoutExpired:
        logger.error("超时（30分钟），已终止")
    except FileNotFoundError:
        logger.error(f"找不到工具脚本: {TOOL_SCRIPT}")
    except Exception as e:
        logger.error(f"运行异常: {e}")


def parse_run_time(time_str: str) -> tuple[int, int]:
    """解析 HH:MM 格式的时间字符串"""
    try:
        h, m = time_str.split(":")
        return int(h), int(m)
    except Exception:
        raise ValueError(f"无效的时间格式: {time_str!r}，请使用 HH:MM（例如 09:00）")


def main() -> None:
    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("youtube-submd 调度 Agent 启动")
    logger.info(f"Python: {PYTHON_BIN}")
    logger.info(f"工具路径: {TOOL_SCRIPT}")
    logger.info(f"每日运行时间: {RUN_TIME}")
    logger.info(f"默认处理视频数: {LIMIT}")
    logger.info("=" * 50)

    if not TOOL_SCRIPT.exists():
        logger.error(f"工具脚本不存在: {TOOL_SCRIPT}")
        sys.exit(1)

    run_hour, run_minute = parse_run_time(RUN_TIME)

    if RUN_ON_START:
        logger.info("RUN_ON_START=True，立即执行一次...")
        run_tool(logger)

    logger.info(f"进入调度循环，等待每天 {RUN_TIME} 执行...")

    last_run_date = datetime.now().date() if RUN_ON_START else None

    while True:
        now = datetime.now()
        today = now.date()

        # 到达设定时间且今天尚未运行
        if now.hour == run_hour and now.minute == run_minute and last_run_date != today:
            last_run_date = today
            run_tool(logger)

        # 每 30 秒检查一次
        time.sleep(30)


if __name__ == "__main__":
    main()
