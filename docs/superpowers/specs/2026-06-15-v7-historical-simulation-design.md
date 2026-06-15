# v7 历史模拟回填系统 — 设计文档

**日期**: 2026-06-15
**状态**: 已确认
**方案**: A — 逐日实时模拟

## 目的

用 v7 优化参数（BEAR/STRICT/LOOSE），逐日模拟 2026年5月1日至6月15日的筛选→AI分析→收益验证全流程，将结果填入复盘界面。目标是积累足够的 AI 分析历史数据，让 AI 能够从过去判断中学习。

## 核心约束

- **稳字优先**：不追求速度，追求与真实选股逻辑的 100% 一致性
- **无未来信息泄露**：每个历史日期的筛选只用当日及之前的数据
- **不改动现有代码**：独立脚本 `simulate_v7_from_may.py`，复用现有函数

## 架构

```
simulate_v7_from_may.py  (独立脚本)
│
├─ Step 0: 清除旧 v6 数据
├─ Step 1: 加载 v7 三套参数
├─ Step 2: 主循环 (32个交易日)
│   ├─ 重建历史市场环境 → 择模
│   ├─ 预过滤 (近期有涨停)
│   ├─ 逐股截断 → _screen_single_stock()
│   └─ AI 分析 → 写入存储
├─ Step 3: 事后收益验证 (>7天的信号)
└─ Step 4: 生成 results_archive JSON
```

## 数据流

```
stock_data/*.csv (5212只)
    │
    ├─→ truncate_df_to_date(df, target_date)
    │       │
    │       └─→ _screen_single_stock(code, truncated_df, params)
    │               │
    │               └─→ candidates[]
    │
    ├─→ yfinance 指数历史数据
    │       │
    │       ├─→ detect_regime_historical(target_date)
    │       │       → 决定用 BEAR/STRICT/LOOSE 哪套参数
    │       │
    │       └─→ get_market_context_historical(target_date)
    │               → AI 分析上下文
    │
    └─→ candidates[]
            │
            ├─→ _run_ai_analysis() → ai_memory.json
            ├─→ _save_signals() → signal_tracker.csv
            └─→ results_archive/{YYYYMMDD}.json
```

## 关键函数设计

### truncate_df_to_date(df, target_date)
截断 DataFrame 到 target_date（含当日数据，不含未来数据）。
- 输入：完整 stock DataFrame, 目标日期 "YYYY-MM-DD"
- 输出：截断后的 DataFrame
- 验证：截断后最后一个日期 ≤ target_date

### get_market_context_historical(target_date, index_data)
重建 target_date 的大盘快照字符串，格式与 `get_market_context()` 一致。
- 用 yfinance 下载三大指数在 target_date 前 30 天数据
- 计算 target_date 当天的：当前价、当日涨跌幅、5日趋势
- 返回：与 `get_market_context()` 完全一致的格式化字符串

### detect_regime_historical(target_date, index_data)
重建 target_date 的市场环境，返回推荐模式。
- 与 `detect_market_regime()` 逻辑一致
- 返回：{'regime', 'avg_trend', 'sentiment_tier', 'recommended_mode'}

## 存储格式

### signal_tracker.csv
列: date, signal_date, code, mode, entry_price, pullback_pct, limit_days, name, sector

### ai_memory.json
每条记录包含: date, signal_date, mode, entry_price, pullback_pct, limit_days, analysis, sentiment, position, opinion, verified, return_7d, exit_reason, exit_day, verdict

### results_archive/{YYYYMMDD}.json
与 auto_daily.py 输出格式一致: scan_date, modes.{mode}.candidates[]

## 开发工作流 + Superpowers 技能

| 阶段 | 技能 | 用途 |
|------|------|------|
| 设计 | `superpowers:brainstorming` | ✅ 已完成，产出本文档 |
| 规划 | `superpowers:writing-plans` | 下一步：详细实现计划 |
| 开发 | `superpowers:subagent-driven-development` | 并行开发：脚本主体 + 历史市场函数 + 数据清理 |
| 调试 | `superpowers:systematic-debugging` | 问题根因分析 |
| TDD | `superpowers:test-driven-development` | 截断函数、市场重建等关键逻辑先写测试再实现 |
| 审查 | memory 4-agent 并行审查工作流 | 代码完成后全量审查 → 去重 → 修复 |
| 验收 | `superpowers:verification-before-completion` | 语法+导入+回归+端到端 |

## 验收标准

1. **无未来信息泄露**: 任意日期筛选，截断后最后 bar 日期 ≤ 目标日期
2. **今日一致性**: 今天日期的模拟结果应与 `python 选股new_v5.py --today auto` 一致
3. **存储完整性**: signal_tracker.csv 和 ai_memory.json 记录数与 candidates 一致
4. **复盘可展示**: streamlit 复盘页能看到 5 月至今的信号+裁决
5. **AI 分析完整**: ai_memory.json 每条记录有 sentiment/position/opinion
6. **收益可验证**: >7天前的信号有 return_7d/exit_reason/verdict
7. **JSON 格式兼容**: results_archive JSON 可被 auto_daily.py 格式通知读取

## 预计耗时

| 步骤 | 预估 |
|------|------|
| 清除旧数据 | 1 min |
| 32日逐日筛选 | 10-15 min (预过滤后每日 ~200-500 股) |
| AI 分析 (DeepSeek API) | 20-40 min (取决于候选数量) |
| 收益验证 | 2 min |
| **总计** | **30-60 min** |

## 风险

- **候选数量不确定**: v7 LOOSE (pullback_max=0.09) 在 5 月可能也选不出票。如果整个周期 0 候选，复盘页将没有数据。备选：如果某日 0 候选，记录空结果但继续。
- **API 速率限制**: DeepSeek 可能有并发限制，需要 1.5s 间隔 + 重试机制。
- **数据缺失**: 部分股票在 5 月可能已退市/停牌，CSV 文件可能不足，需跳过。
