#!/bin/bash
# A股数据自动更新脚本
# 由 launchd 每小时触发一次，数据已齐则秒退
# 日志: /tmp/grab_rebound_update.log

LOG="/tmp/grab_rebound_update.log"
PYTHON="/Users/mattsmacair/micromamba/bin/python"
SCRIPT="/Users/mattsmacair/Desktop/Coding/量化模型/抓反弹策略/选股new_v5.py"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting update..." >> "$LOG"
cd "/Users/mattsmacair/Desktop/Coding/量化模型/抓反弹策略" || exit 1
$PYTHON -c "from 选股new_v5 import update_today_data; update_today_data()" >> "$LOG" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done." >> "$LOG"
