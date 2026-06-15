# 统一 Auto 模式 UI 重设计

**日期**: 2026-06-14
**状态**: 已确认

## Context

v6 的市场自适应系统 (`detect_market_regime()`) 已能自动选择最优模式 (BEAR/STRICT/LOOSE)。当前 UI 仍然以三 Tab 展示所有模式的候选，用户需要手动切换、手动点击 AI 分析按钮。这违背了"自动"的核心理念。

**目标**: 选股页面从三模式 Tab 切换 → 单一 auto 模式结果页。所有候选自动触发 AI 分析并存入记忆。复盘页面从分模式展示 → 统一绩效面板。

## Aesthetic Direction: 「战术终端」Tactical Terminal

2087 年 A 股战术指挥中心 — 军事级数据终端 × 赛博朋克霓虹。

| 维度 | 当前 | 增强后 |
|------|------|--------|
| 主色 | `#00ff88` | 保持 + 辉光 |
| 强调 | `#ff6b35` | 保持 + 脉冲动画 |
| 点缀(新) | — | `#00e5ff` 电光青 |
| 背景 | `#0a0e14` | `#060b10` 虚空黑 → `#0d1520` 面板 |
| 字体 | Orbitron + JetBrains Mono | 保持 |
| 氛围 | 点阵网格 + 扫描线 | 增强: 噪点纹理、斜角几何分割线、边框辉光 |
| 动效 | 静态 | 卡片 hover 辉光、进度条脉冲、数据淡入 |

**记忆点**: 这不是 dashboard，这是交易终端。

## Changes

### 1. 选股页面 (streamlit_app.py main() 选股分支)

**移除**:
- 三 Tab 布局 (`st.tabs([STRICT, LOOSE, BEAR])`)
- 每只股票的 `"AI分析"` 手动按钮
- 模式名称在结果区的显示（如 "LOOSE · 23只"）

**新增**:
- **市场状态卡片** (替代当前 `regime_info` 的简单文本): 三大指数 + 涨跌幅 + 情绪档位，一行排列，紧凑无冗余
- **统一候选列表**: 从 `latest_scan_results.json` 读取 `recommended_mode` 对应的候选。每行显示代码、名称、价格、回调%、连板数、实体%
- **全自动 AI 分析**: 页面首次加载时，所有候选自动调用 `start_analysis_queue(codes)`。无需用户点击按钮
- **内联 AI 结果**: 分析完成后，在对应股票行下方直接展开摘要（情绪档位 + 仓位建议 + 结论摘要），替代当前独立的 expander
- **AI 分析进度条**: 顶部固定位置，显示 "正在分析 X/N · 当前: {code} · 预计剩余 N 分钟"
- **分析状态标签**: 每行右侧显示 `⏳排队中 / 🔄分析中 / 🟢乐观仓位X / 🔴谨慎 / ✅已完成`

**不变**:
- 大盘指数加载 (`get_market_context()`)
- 市场状态检测 (`detect_market_regime()`)
- 背景工作线程 (`_analysis_worker`)
- JS 轮询机制
- CSV 导出按钮

**数据流**:
```
页面加载 → load_latest_results() → 取 recommended_mode 的 candidates
  → start_analysis_queue(all_codes) → 后台线程分析
  → JS 轮询刷新 → 完成后内联显示摘要
  → save_ai_analysis_record() 自动存入 ai_memory.json
```

### 2. 复盘页面 (streamlit_app.py 复盘分支)

**移除**:
- STRICT / LOOSE 双列布局
- `compute_performance(mode_filter='strict')` / `compute_performance(mode_filter='loose')` 分别调用

**改为**:
- **统一绩效面板**: `compute_performance(mode_filter=None)` 跨模式聚合
- 四指标卡片: 累计收益、胜率、盈亏比、最大回撤
- 一条收益曲线（全部信号聚合）
- 退出原因统计（到期/止盈/止损）
- AI 记忆浏览器保持不变

### 3. 介绍页面 (streamlit_app.py 介绍分支)

文字更新: 强调 "市场自适应"、"全自动 AI 分析"、"记忆闭环验证"。

### 4. auto_daily.py

`run_all_modes()` 改为:
```python
def run_all_modes():
    regime_info = screener.detect_market_regime()
    mode = regime_info['recommended_mode']
    # 只跑推荐模式
    results = {mode: screen_with_mode(mode)}
    return results
```

`latest_scan_results.json` 结构简化 — `modes` 只包含一个条目，`regime` 字段保留。

### 5. CSS 增强 (inject_design_system)

在现有 CSS 基础上添加:
- 噪点纹理 overlay (`.noise-overlay`)
- 斜角几何分割线 (`.tactical-divider`)
- 卡片边框辉光 (`.card-glow`)
- 进度条脉冲动画 (`.progress-pulse`)
- 数据淡入 staggered (`.fade-in`)
- 电光青强调色 utility (`.accent-cyan`)

## Verification

1. `streamlit run streamlit_app.py` → 确认选股页为单一列表
2. 确认所有候选自动进入 AI 分析队列
3. 确认分析完成后内联显示摘要
4. 确认 `ai_memory.json` 有新记录
5. 切换到复盘页 → 确认统一绩效面板
6. `python auto_daily.py` → 确认只跑推荐模式
