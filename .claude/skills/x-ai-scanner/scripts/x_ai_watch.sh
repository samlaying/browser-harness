#!/usr/bin/env bash
# X AI 巡检 —— 持续运转调度器
#
# 循环：扫描 → 导出报告 → 休息 N 分钟。Ctrl-C 停止。
# 每次"扫描"本身是短会话（受 XAI_MAX_SECS / boundary_hit 约束，自然不会久占浏览器），
# 这是反封的关键：短频次、像人，而不是长时间挂着刷。
#
# 环境变量：
#   XAI_INTERVAL   两次扫描间隔分钟数（默认 45）
#   XAI_MAX_ROUNDS 单次最多滚几轮（默认 30；boundary_hit 会提前停）
#   XAI_MAX_SECS   单次会话秒数上限（默认 300）
#   XAI_MAX_NEW    单次最多抓多少新推文（默认 120）
#   XAI_MAX_ITERS  最多跑几轮（默认 0=无限；设 8 ≈ 半天@90min）

set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
SCAN="$DIR/x_ai_scan.py"
EXPORT="$DIR/x_ai_export.py"
INTERVAL="${XAI_INTERVAL:-45}"
MAX_ITERS="${XAI_MAX_ITERS:-0}"

i=0
while true; do
    i=$((i+1))
    echo "============================================================"
    echo "▶ 第 $i 轮巡检  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "============================================================"
    browser-harness < "$SCAN"
    python3 "$EXPORT" >/dev/null 2>&1 || echo "(导出跳过)"
    if [ "$MAX_ITERS" -gt 0 ] && [ "$i" -ge "$MAX_ITERS" ]; then
        echo "🏁 已跑满 $MAX_ITERS 轮，结束。"
        break
    fi
    echo "💤 休息 ${INTERVAL} 分钟后进行下一轮…  (Ctrl-C 退出)"
    sleep "${INTERVAL}m"
done
