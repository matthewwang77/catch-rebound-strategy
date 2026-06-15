# 复盘界面绩效计算修复 — 设计文档

**日期**: 2026-06-16
**状态**: 已确认
**方案**: 修复现有数据 + 修复代码

## 目的

修复复盘界面"绩效总览"的 4 个 bug：

1. **信号重复生成**: 同一连板事件在多个扫描日被当成独立信号
2. **回撤百分比不更新**: pullback_pct 始终是首次触发值，不随价格变动
3. **STRICT 模式持有天数错误**: return_7d 用 hold_days=7 计算，但 STRICT 策略定义是 hold_days=10
4. **绩效总览标题误导**: 固定显示"7日持有"，不反映各模式实际持有期

## 根因分析

### Bug 1: 信号去重失效

**去重键错配**:
- `ai_memory.json`: `(code, date)` — `date` 是扫描日期，不是信号日期
- `signal_tracker.csv`: `(code, entry_price)` 20天内 — `entry_price` 随市场价格天天变化

**正确去重键**: `(code, signal_date)` — signal_date 是连板事件的结束日，唯一标识一次交易机会

### Bug 2: 回撤静态化

`simulate_v7_from_may.py` 在逐日模拟中，每次重新触发信号时 pullback_pct 仍使用首次计算的值，未更新为当日的实际回撤。

**修复后**: 保留首次信号即可，首次信号的回撤百分比是正确的（信号触发当日的真实回撤）。

### Bug 3: STRICT hold_days

| 位置 | 当前 | 应为 |
|------|------|------|
| `auto_daily._auto_maintenance()` | `check_return_v5_local(..., 7, ...)` | `hold_days=mode_config['hold_days']` |
| `simulate_v7_from_may.py` main() | `hold_days=7` | `hold_days=params['hold_days']` |

STRICT 策略 `hold_days=10`，BEAR/LOOSE `hold_days=7`。

### Bug 4: 绩效标题

`compute_performance()` 返回 `{'hold_days': 7}` 写死。修复后从数据中读取实际模式。

## 修复方案

### 改动 1: 统一去重键 `(code, signal_date)`

**影响文件**:
- `ai_memory.json` — 清理重复记录，保留每组 (code, signal_date) 中 date 最早的
- `signal_tracker.csv` — 同理去重
- `simulate_v7_from_may.py` — 生成信号前检查 `(code, signal_date)` 是否已存在
- `auto_daily.py` — 同上

### 改动 2: 模式专属收益计算参数

```python
# 从 SCREEN_MODES 读取各模式参数
MODE_PARAMS = {
    'bear':   {'hold_days': 7,  'take_profit': 0.057, 'stop_loss': -0.103},
    'strict': {'hold_days': 10, 'take_profit': 0.051, 'stop_loss': -0.112},
    'loose':  {'hold_days': 7,  'take_profit': 0.05,  'stop_loss': -0.10},
}
```

**影响文件**:
- `auto_daily._auto_maintenance()` — 根据记录的 mode 选择参数
- `simulate_v7_from_may.py` main() — 同上
- `backfill_signals.py` — 不改（`check_return_v5_local` 本身接受 hold_days/take_profit/stop_loss 参数，逻辑正确）

### 改动 3: 绩效总览显示真实持有期

**影响文件**: `streamlit_app.py`

- `compute_performance()` — 从 ai_memory 记录中读取 mode-specific hold_days
- 绩效总览 UI — 标题改为动态显示各模式持有天数

### 改动 4: 数据修复脚本（一次性）

**新建文件**: `fix_review_data.py`

功能：
1. 加载 `ai_memory.json`
2. 按 `(code, signal_date)` 去重，保留 date 最早的记录
3. 用模式专属参数重新调用 `check_return_v5_local()` 计算 return_7d
4. 更新 exit_reason, exit_day, verdict
5. 保存回 `ai_memory.json`
6. 同步去重 `signal_tracker.csv`

去重后预期: 15 条 → ~5-7 条唯一信号

## 不改的部分

- `check_return_v5_local()` in `backfill_signals.py` — 逻辑正确，逐日检查止盈止损 + 交易成本，与策略 backtest 一致
- `compute_performance()` 的聚合逻辑 — 几何复合、最大回撤计算无误
- `simulate_hold_return()` in 选股new_v5.py — 回测引擎正确

## 验收标准

1. `ai_memory.json` 中不再有重复的 `(code, signal_date)` 组合
2. STRICT 模式记录的 return_7d 用 hold_days=10 计算
3. BEAR/LOOSE 模式记录的 return_7d 用 hold_days=7 计算
4. 绩效总览显示正确交易笔数（≈5-7 笔，不是 15 笔虚高）
5. `signal_tracker.csv` 行数与 ai_memory 唯一信号数一致
6. `python fix_review_data.py` 运行无报错
7. Streamlit 复盘页显示正确数据
