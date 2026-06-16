# 策略盈亏显示 + 信号去重移除 设计文档

> **日期**: 2026-06-16
> **状态**: 已确认

## 目标

1. 复盘页面将"7日收益"显示改为策略模拟盈亏（止盈/止损/到期），附带退出原因和退出天数
2. 移除 `_save_signals()` 中的 20 天价格去重逻辑，每次信号独立记录

## 背景

`check_return_v5_local()` 早已使用策略参数（take_profit/stop_loss/hold_days）逐日模拟交易，计算真实策略盈亏。但字段名 `return_7d` 和 UI 显示 "7d +4.9%" 有误导性，让人以为是简单 7 日涨跌幅。实际数据已经是策略盈亏。

## 改动

### 文件 1: `streamlit_app.py` — 复盘页面显示

**记忆卡片 metric 行**（~line 2778-2785）：

```
旧: 7d +4.9% | 止损 Day2
新: 策略 +4.9% · 🎯止盈 Day3
```

退出原因映射：
- `止盈` → 🎯止盈（绿色）
- `止损` → 🛑止损（红色）
- `到期` / `到期(截断)` → ⏰到期（黄色）

**绩效总览标题**（~line 2653-2655）：
- "累计收益" → "策略收益"
- hold_info 标签保持不变（已显示持有天数）

### 文件 2: `auto_daily.py` — 去重移除

**`_save_signals()` 函数**：删除 20 天窗口去重逻辑（约 15 行），只保留同日同代码同模式去重。

### 文件 3: `auto_daily.py` — AI 记忆上下文

**`_get_stock_memory_context()`**：将 "7日后 +4.9% ✅准确预判" 改为 "策略 +4.9% · 止盈Day3 ✅准确预判"（同理 wrong/missed/avoided）。

### 文件 4: `streamlit_app.py` — 选股页面 AI 记忆上下文

**`get_stock_memory_context()`**（streamlit 中的副本）：同上改动。

## 不需要改的

- `ai_memory.json` 字段名 `return_7d`：改名需要数据迁移，风险大于收益。保持字段名，只改 UI 显示。
- `check_return_v5_local()`：计算逻辑不变。
- `_auto_maintenance()`：验证逻辑不变。
- `backfill_signals.py`：回填逻辑不变。

## 验证

```bash
python auto_daily.py                    # 干跑确认无报错
streamlit run streamlit_app.py          # UI 检查复盘页卡片
```
