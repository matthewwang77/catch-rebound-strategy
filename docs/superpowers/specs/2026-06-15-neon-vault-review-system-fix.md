# NEON VAULT 复盘系统全面修复 · 设计 Spec

> 2026-06-15 | 状态: 设计确认，待实施

## 1. 背景与问题

### 1.1 数据 bug：entry_date/entry_price 时点错配

`signal_date`（形态完成日）和 `entry_price`（扫描日价格）来自不同时间点，拼在一起算收益等于"时光机交易"。

例：000518.SZ — signal_date=6月3日（实际价格3.53~3.93），entry_price=3.14（6月13日扫描价）。系统模拟6月3日以3.14买入 → 6月4日开盘3.93 → +25%触发止盈。但6月3日股价从未到过3.14。

**根因**：`auto_daily.py:_run_ai_analysis()` 用 signal_date 作记录日期；`backfill_signals.py:main()` 用 signal_date + entry_price 算收益。两个值来自不同时间点。

### 1.2 裁决逻辑 bug

当前逻辑：return > 0 → correct，return < 0 → wrong。完全忽略AI的判断。

例：AI对002081.SZ说【放弃】，但股价涨了22% → 系统标✅正确。应该是🔶错失机会——AI判断错误。

### 1.3 UI 问题

- 市场状态栏冗余（已在后台auto处理）
- 绩效卡片布局平淡
- 收益曲线用 st.line_chart 太朴素
- AI记忆卡片缺乏结构化回顾信息

---

## 2. 数据模型修正

### 2.1 ai_memory.json 记录结构 (v2)

```json
{
  "002081.SZ": [
    {
      "date": "20260615",
      "signal_date": "20260529",
      "mode": "strict",
      "entry_price": 5.03,
      "pullback_pct": 13.7,
      "limit_days": 5,
      "analysis": "...",
      "sentiment": "冰点/观望",
      "position": "0成仓",
      "opinion": "【放弃】",
      "verified": false,
      "return_7d": null,
      "exit_reason": null,
      "exit_day": null,
      "verdict": null,
      "review_analysis": null,
      "what_happened": null,
      "why_wrong": null,
      "missed_signal": null,
      "lesson": null
    }
  ]
}
```

**关键变更**：
- `date` 现在是**扫描日**（用于收益验证），不再是 signal_date
- `signal_date` 保留为参考字段（形态完成日）
- `review_analysis` + 4个结构化回顾字段（仅7日回填后有值）
- `return_3d/5d` 移除 → 只保留 `return_7d`（7日回顾制）
- `exit_reason` / `exit_day` 新增

### 2.2 7日回顾结构（C方案）

AI执行7日全路径回顾后，填入以下5字段：

| 字段 | 内容 | 示例 |
|------|------|------|
| `what_happened` | 7日走势简述 | "第3天开盘跳空+22%触发止盈，缩量回调后放量反弹" |
| `why_wrong` | AI哪里分析错了 | "过度关注均线破位，忽略了涨停日最低价的强支撑" |
| `missed_signal` | 遗漏的关键信号 | "OBV未破前低+极度缩量(量比0.31)是蓄势信号" |
| `lesson` | 下次注意什么 | "缩倍阴+OBV不破前低=高概率反弹，不应简单放弃" |
| `verdict` | 最终裁决 | `correct` / `wrong` / `missed` / `avoided` / `noted` |

---

## 3. 裁决矩阵

| AI结论 | 实际走势 | Verdict | 颜色 | 标签 |
|---------|:-------:|---------|------|------|
| 【参与】 | 涨(触发止盈或到期正收益) | `correct` | #00ff88 | ✅ 准确预判 |
| 【参与】 | 跌(触发止损或到期负收益) | `wrong` | #ff3366 | ❌ 判断失误 |
| 【放弃】 | 涨 | `missed` | #ffb800 | 🔶 错失机会 |
| 【放弃】 | 跌 | `avoided` | #00cc66 | 🛡 正确规避 |
| 【观望】 | 涨 | `noted_up` | #7b2fff | 📝 偏保守 |
| 【观望】 | 跌 | `noted_down` | #7b2fff | 📝 偏准确 |

---

## 4. UI 设计规范

### 4.1 移除市场状态栏

删除 `streamlit_app.py` 中 `detect_market_regime()` 的结果展示栏（当前 L1926-1946）。市场数据继续在上方 st.metric 展示。

### 4.2 绩效总览面板（B 不对称布局）

**布局**：左侧大块（flex:2）= 累计收益 + 盈利笔数标签；右侧竖列（flex:1）= 胜率/盈亏比/回撤三行紧凑排列。

**CSS 类**：`.perf-panel-v2`

```
┌──────────────────────────────┬──────────┐
│  ◆ 累计收益 (30日)           │  胜率     │
│  +58.3%                      │  66.7%    │
│  +12笔盈利                   ├──────────┤
│                              │  盈亏比   │
│                              │  3.2      │
│                              ├──────────┤
│                              │  回撤     │
│                              │  -8.5%    │
└──────────────────────────────┴──────────┘
```

**颜色规则**：
- 累计收益：正=#00ff88，负=#ff3366
- 胜率：中性 #00f0ff
- 盈亏比：#ffd700
- 回撤：#ff3366

### 4.3 收益曲线（C 双图组合）

自定义 SVG，替代 `st.line_chart`。

**上图**：累计收益曲线 — 发光折线（`#00ff88`，filter glow）+ 渐变填充 + 暗网格参考线
**下图**：逐笔盈亏柱状 — 绿柱=盈利，红柱=亏损，半透明

**数据来源**：从 `ai_memory.json` 所有已验证记录的 `return_7d` 按 `date` 排序累计。

### 4.4 AI 记忆卡片（D+ 宽松版）

**CSS 类**：`.memory-card-v4`

**结构**：
```
┃ ◆ 002081.SZ  金螳螂  2026-06-13  [🔶 错失机会]    ◆ 【放弃】
┃ 入场 ¥5.03  |  回调 13.7%  |  连板 5天  |  7d +22.2%  |  止盈 Day3
┃ ─────────────────────────────────────────────
┃ 📝 教训：过度关注均线破位，忽略了涨停日最低价5.29的强支撑...
```

**裁决色条**（左边框3px）：
- `correct` → #00ff88
- `wrong` → #ff3366
- `missed` → #ffb800
- `avoided` → #00cc66
- `noted_up/down` → #7b2fff
- 待验证 → #444466

**待验证卡片**（无7日数据时）：
- 精简显示：代码+名称+日期+AI结论+入场信息
- 左边框灰色 + "⏳ X天后可回顾"

---

## 5. 实现范围

### auto_daily.py
- `_run_ai_analysis()`: date_str 改为 `datetime.now()`；新增 signal_date 字段
- `_auto_maintenance()`: 
  - 只做7日回顾（删掉3d/5d逻辑）
  - 数据计算：用 `check_return_v5_local(code, date, entry_price, 7, tp, sl)` 得到 return_7d + exit_reason + exit_day
  - AI回顾：将7日OHLCV数据 + 原始AI分析 + 客观结果 发给DeepSeek，产出5字段结构化回顾
  - 裁决逻辑使用裁决矩阵

### backfill_signals.py
- 使用 `scan_date`（归档JSON的顶层字段）而非 `signal_date` 做收益计算
- 只算7日收益
- 裁决逻辑使用裁决矩阵

### streamlit_app.py
- **删除**：市场状态栏 HTML block（L1926-1946）
- **新增**：`.perf-panel-v2` CSS + HTML（不对称布局）
- **新增**：SVG双图收益曲线（替代 st.line_chart）
- **重写**：`.memory-card-v4` CSS + 卡片HTML渲染（5字段结构 + 裁决色条）
- **更新**：`compute_performance()` — 改用 return_7d
- **更新**：`load_ai_memory()` 等函数 — 适配新字段

---

## 6. 验证

```bash
# 1. 检查裁决逻辑
python3 -c "
opinions = ['【参与】', '【放弃】', '【观望】']
returns = [5.0, -3.0]
# 验证6种组合的verdict正确
"

# 2. 修正旧数据
python backfill_signals.py

# 3. 检查 ai_memory.json 字段完整性
python3 -c "
import json
m = json.load(open('ai_memory.json'))
for code, records in m.items():
    for r in records:
        required = ['date','signal_date','opinion','return_7d','verdict']
        missing = [k for k in required if k not in r]
        if missing: print(f'{code}: 缺字段 {missing}')
"

# 4. UI验收
streamlit run streamlit_app.py
# 检查：
# - 无市场状态栏
# - 绩效面板B不对称布局，累计收益最大
# - SVG曲线+柱状图正常渲染
# - 记忆卡片左边框颜色对应verdict
# - 5字段回顾在已验证卡片中展示
# - 待验证卡片显示倒计时
```
