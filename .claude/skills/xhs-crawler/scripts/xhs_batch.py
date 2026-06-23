#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书批量爬虫 — browser-harness (CDP) 自包含编排脚本

管道用法（harness 自动注入 js/cdp/ensure_daemon 等 globals）：
    XHS_KEYWORD="咖啡" XHS_TARGET=20 browser-harness < scripts/xhs_batch.py

环境变量：
    XHS_KEYWORD    搜索词（必填）
    XHS_TARGET     目标篇数（默认 20）
    XHS_OUTDIR     输出目录（默认 xhs_data/{date}_{keyword}）
    XHS_MAX_RETRY  单篇重试次数（默认 2）

健壮性：断点续爬(state.json) + 增量落盘 + 单篇重试 + 每5篇健康检查。

设计约束：本脚本经 harness `exec(code, globals())` 执行，js/cdp 在同一 globals。
故：① 不能跨文件 import 需要 js/cdp 的逻辑；② 入口由 'js' in dir() 守卫，
   这样 pytest 可直接 import 纯函数做单测而不触发 run_batch。

纯函数（无 js/cdp 依赖，可单测）：encode_keyword / waterfall_sort / compute_threads
                            / load_state / save_state / default_state / seed_done_from_disk
"""

import os, sys, json, time, random, glob, datetime
import urllib.parse


# ── 纯函数占位（后续 Task 填充） ─────────────────────────
# encode_keyword / waterfall_sort / compute_threads / 状态 IO — 见 Task 2-5


# ── DOM/编排函数占位（后续 Task 填充） ───────────────────
# safe_js / safe_cdp / jitter / verify_click_target / click_card_with_verify
# / wait_mask_gone / collect_cards / get_card_rect / close_overlay
# / delay_* / wait_for_comments / extract_note / health_check — 见 Task 6-9


def run_batch():
    """主编排：导航搜索页 → 收卡片排序 → 断点续爬 → 逐篇重试增量落盘 → 健康检查。
    见 Task 9。"""
    print("[xhs_batch] run_batch() 尚未实现（骨架）", flush=True)


# ── 入口 ─────────────────────────────────────────────────
# harness exec 时 js/cdp 在 dir()；pytest import 时不在 → 不触发 run_batch。
if 'js' in dir() and 'cdp' in dir():
    run_batch()
