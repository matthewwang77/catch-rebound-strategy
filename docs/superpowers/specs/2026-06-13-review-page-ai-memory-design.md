# 复盘页面重设计 + AI 记忆系统 · 设计文档

**日期**: 2026-06-13
**状态**: 已确认

## 概述

重新设计复盘页面，核心新增 **AI 记忆系统**：每次 AI 分析自动存档，实际收益自动验证，再次分析时自动注入历史记忆形成闭环。同时删除手动选股复盘功能。

## 设计决策

| # | 决策 | 选择 |
|---|------|------|
| 1 | 记忆模式 | 股票维度 — 每只股票保留独立分析历史链 |
| 2 | 记忆注入 | 自动注入 — 分析时自动带历史分析+验证结果 |
| 3 | 复盘场景 | 查看历史AI分析+验证预测 + 全局绩效总览 |
| 4 | 手动选股 | 删除 |
| 5 | 风格 | 极简 NEON VAULT — 无框数字、左边框区分状态、四色系统 |

## 新增数据文件

### `ai_memory.json`

```json
{
  "002081.SZ": [
    {
      "date": "20260610",
      "mode": "strict",
      "entry_price": 12.34,
      "pullback_pct": 8.5,
      "limit_days": 3,
      "analysis": "## 量 · 成交量分析\n回调期间量能持续萎缩...",
      "sentiment": "启动期",
      "position": "3成",
      "opinion": "短线反弹可期",
      "verified": true,
      "return_3d": 5.2,
      "return_5d": null,
      "return_7d": null,
      "verdict": "correct"
    }
  ]
}
```

字段说明：
- `analysis`: AI 返回的完整 markdown
- `sentiment`/`position`/`opinion`: 从 AI 回复中正则提取
- `verified`: 是否已到验证时间（≥3天）
- `return_3d`/`5d`/`7d`: 实际收益（来自 signal_tracker 的 check_return）
- `verdict`: "correct" | "wrong" | null（待验）

### 与 signal_tracker.csv 的关系

- signal_tracker.csv 已有每只股票的信号记录（日期/代码/入场价/模式/回调/连板数）
- ai_memory.json 在此基础上增加 AI 分析内容 + 验证状态
- 验证时通过 (code, date) 关联两个数据源
- signal_tracker 是数据源，ai_memory 是展示层

## 复盘页面结构

```
┌──────────────────────────────────────────┐
│  Hero 数字行（纯文字，无卡片）              │
│  累计收益 +12.4%  胜率 65.2%  盈亏比 1.85  │
│  最大回撤 -8.2%                           │
│  小字：45胜/24负 · 均盈+3.2%/均亏-1.7%    │
├──────────────────────────────────────────┤
│  累计收益曲线（SVG/Altair 轻量图）          │
│  含回撤阴影标注                            │
├──────────────────────────────────────────┤
│  AI 记忆卡片列表                           │
│  ┌─ 002081.SZ 金螳螂 ──────────────────┐  │
│  │ 06-10 strict ¥12.34 回调8.5% 3D+5.2%│  │
│  │ ◆ AI判断摘要... 情绪:启动期 仓位:3成  │  │
│  │ [展开全文] [重新分析(带入记忆)] ✅     │  │
│  └──────────────────────────────────────┘  │
│  ...更多卡片...                            │
│                                           │
│  顶部筛选：全部 / ✅正确 / ◈偏差 / ⏳待验    │
└──────────────────────────────────────────┘
```

## 核心功能

### 1. AI 分析自动存档（修改 fast_ai_analysis 调用处）

在选股页面 AI 分析完成后，将结果写入 ai_memory.json：
- 按 (code, date) 去重
- 正则提取 sentiment/position/opinion
- verified 初始为 false

### 2. 自动验证（复盘页面加载时）

加载 ai_memory.json → 对 verified=false 且日期≥3天前的记录：
- 从 signal_tracker.csv 获取 entry_price
- 调用 check_return() 计算 3d/5d/7d 收益
- 3d_return > 0 → verdict = "correct", 否则 "wrong"
- 回写到 ai_memory.json

### 3. AI 记忆注入（修改 fast_ai_analysis 函数）

分析某只股票时：
- 从 ai_memory.json 查找该股票的历史记录
- 构建注入文本，追加到 system prompt：
  ```
  [历史分析记录]
  2026-06-10：AI判断"短线反弹可期"，建议3成仓位。3日后实际收益 +5.2% (✅正确)
  2026-06-01：AI判断"观望等待"。3日后实际收益 -1.8% (◈偏差)
  ```
- 发给 DeepSeek，让其做连续性分析

### 4. 绩效总览（Hero 数字行 + 曲线图）

数据来源：signal_tracker.csv + check_return()
- 累计收益：所有已验证信号的收益汇总
- 胜率：正收益信号数 / 总验证信号数
- 盈亏比：平均盈利 / 平均亏损（绝对值）
- 最大回撤：从累计收益序列计算
- 收益曲线：累计收益随时间变化（用 Streamlit line_chart 或 Altair）

### 5. 删除功能

- 删除 show_manual_review() 函数
- 删除 perform_manual_analysis() 函数
- 删除 display_manual_results() 函数
- 删除 save_manual_picks() 函数
- 删除 MANUAL_PICKS_FILE 常量
- 删除 manual_picks.csv 相关逻辑
- 删除 复盘页面中对手动选股的所有引用

## 设计原则

- **无框**: 数值不用卡片包裹，纯文字排版
- **细线**: 只用左边框 2px 区分验证状态（绿=正确 / 红=偏差 / 紫=待验）
- **留白**: 大间距、小字号、低透明度分割线
- **单色**: 只保留 cyan（数据）/ green（盈利/正确）/ red（亏损/偏差）/ purple（待验/中性）四色
- **字体**: JetBrains Mono 全局统一

## 涉及文件

| 文件 | 改动 |
|------|------|
| `streamlit_app.py` | 复盘页面重写、AI分析存档逻辑、记忆注入逻辑、删除手动选股 |
| `ai_memory.json` | 新增，AI 分析记忆存储 |
| `docs/superpowers/specs/2026-06-13-review-page-ai-memory-design.md` | 本设计文档 |

## 验证

```bash
streamlit run streamlit_app.py
```

检查点：
1. 侧边栏点"复盘" → 看到绩效总览 Hero 数字 + 收益曲线
2. 如果无历史数据 → 显示空状态提示
3. 在选股页点 AI 分析 → ai_memory.json 自动生成记录
4. ≥3天后打开复盘页 → 验证状态自动更新（✅/◈）
5. 对有历史记录的股票再次点 AI 分析 → prompt 包含历史记忆
6. 手动选股相关代码完全移除，无残留引用
7. 整体 NEON VAULT 风格一致
