# 复盘界面绩效计算修复 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复复盘界面绩效计算的 4 个 bug（信号重复、hold_days 硬编码、回撤静态化、绩效标题误导）

**Architecture:** 数据修复脚本清理现有 ai_memory.json → 修 3 个源文件的硬编码 hold_days=7 → 修去重逻辑 → 修绩效总览 UI

**Tech Stack:** Python, pandas, json, csv (no new deps)

---

### Task 1: 数据修复脚本 `fix_review_data.py`

**Files:**
- Create: `fix_review_data.py`
- Modify (via script): `ai_memory.json`, `signal_tracker.csv`

- [ ] **Step 1: 写脚本骨架 + 去重 + 重算函数**

```python
#!/usr/bin/env python3
"""修复复盘数据：去重 + 用模式专属参数重算 return_7d。
用法: python fix_review_data.py [--dry-run]
"""

import json, os, sys, csv
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))

# 各模式专属参数（与 SCREEN_MODES 一致）
MODE_PARAMS = {
    'bear':   {'hold_days': 7,  'take_profit': 0.057, 'stop_loss': -0.103},
    'strict': {'hold_days': 10, 'take_profit': 0.051, 'stop_loss': -0.112},
    'loose':  {'hold_days': 7,  'take_profit': 0.05,  'stop_loss': -0.10},
}


def load_ai_memory():
    path = os.path.join(BASE, 'ai_memory.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_ai_memory(memory):
    path = os.path.join(BASE, 'ai_memory.json')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def dedup_ai_memory(memory):
    """按 (code, signal_date) 去重，保留 date 最早的记录。"""
    removed = 0
    new_memory = {}
    for code, records in memory.items():
        seen = {}
        for r in records:
            sig_date = r.get('signal_date', r.get('date', ''))
            if sig_date not in seen or r['date'] < seen[sig_date]['date']:
                if sig_date in seen:
                    removed += 1
                seen[sig_date] = r
        new_memory[code] = list(seen.values())
    return new_memory, removed


def dedup_signal_tracker():
    """按 (code, signal_date) 去重 signal_tracker.csv，保留最早的 date。"""
    tracker_path = os.path.join(BASE, 'signal_tracker.csv')
    if not os.path.exists(tracker_path):
        return 0
    df = pd.read_csv(tracker_path)
    original_len = len(df)
    df['date'] = df['date'].astype(str)
    df['signal_date'] = df['signal_date'].astype(str)
    df = df.sort_values('date').drop_duplicates(subset=['code', 'signal_date'], keep='first')
    df.to_csv(tracker_path, index=False, encoding='utf-8-sig')
    return original_len - len(df)


def recompute_returns(memory):
    """用模式专属参数重新计算所有记录的 return_7d。"""
    from backfill_signals import check_return_v5_local
    data_dir = os.path.join(BASE, 'stock_data')
    
    updated = 0
    for code, records in memory.items():
        for r in records:
            mode = r.get('mode', 'strict')
            mp = MODE_PARAMS.get(mode, MODE_PARAMS['strict'])
            
            ret = check_return_v5_local(
                code=code,
                signal_date=r.get('signal_date', r['date']),
                entry_price=r.get('entry_price', 0),
                hold_days=mp['hold_days'],
                take_profit=mp['take_profit'],
                stop_loss=mp['stop_loss'],
                data_dir=data_dir,
            )
            if ret:
                r7 = round(ret['return_pct'], 2)
                r['return_7d'] = r7
                r['exit_reason'] = ret.get('exit_reason', '')
                r['exit_day'] = ret.get('exit_day', 0)
                
                opinion = r.get('opinion', '')
                if any(kw in opinion for kw in ['参与', '买入']):
                    r['verdict'] = 'correct' if r7 > 0 else 'wrong'
                elif any(kw in opinion for kw in ['放弃', '规避']):
                    r['verdict'] = 'avoided' if r7 <= 0 else 'missed'
                else:
                    r['verdict'] = 'noted_up' if r7 > 0 else 'noted_down'
                
                r['verified'] = True
                updated += 1
    
    return updated


def main():
    dry_run = '--dry-run' in sys.argv
    
    print("=" * 60)
    print("复盘数据修复脚本")
    if dry_run:
        print("⚠️  DRY RUN 模式 — 不会写入文件")
    print("=" * 60)
    
    memory = load_ai_memory()
    total_before = sum(len(v) for v in memory.values())
    print(f"\n📂 加载 ai_memory.json: {len(memory)} 只股票, {total_before} 条记录")
    
    memory, removed = dedup_ai_memory(memory)
    total_after = sum(len(v) for v in memory.values())
    print(f"🔍 去重: {total_before} → {total_after} 条 (移除 {removed} 条重复)")
    
    updated = recompute_returns(memory)
    print(f"📊 重算收益: {updated} 条已更新")
    
    if not dry_run:
        save_ai_memory(memory)
        print("💾 ai_memory.json 已保存")
        tracker_removed = dedup_signal_tracker()
        print(f"🔍 signal_tracker.csv 去重: 移除 {tracker_removed} 条")
    else:
        print("\n⚠️  DRY RUN — 未写入文件。去掉 --dry-run 以实际执行。")
    
    print(f"\n{'=' * 60}")
    print("修复后数据:")
    for code, records in memory.items():
        for r in records:
            print(f"  {code} | {r['date']} | {r['mode']} | "
                  f"entry={r['entry_price']} | pullback={r['pullback_pct']}% | "
                  f"return={r.get('return_7d')}% | exit={r.get('exit_reason')} | "
                  f"verdict={r.get('verdict')}")
    print(f"\n共 {sum(len(v) for v in memory.values())} 条唯一信号")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: 干跑验证**

```bash
python fix_review_data.py --dry-run
```
Expected: 输出去重前后记录数，确认 15→~5-7 条。

- [ ] **Step 3: 正式运行**

```bash
python fix_review_data.py
```

- [ ] **Step 4: 验证数据正确性**

```bash
python -c "
import json
with open('ai_memory.json') as f:
    data = json.load(f)
seen = set()
for code, records in data.items():
    for r in records:
        key = (code, r.get('signal_date'))
        assert key not in seen, f'重复: {key}'
        seen.add(key)
print(f'✅ 去重通过: {len(seen)} 条唯一信号')
"
```

- [ ] **Step 5: Commit**

```bash
git add fix_review_data.py ai_memory.json signal_tracker.csv
git commit -m "fix: 数据修复脚本 — 去重+模式专属参数重算收益"
```

---

### Task 2: 修复 `auto_daily.py` hold_days 硬编码

**Files:**
- Modify: `auto_daily.py:894`

- [ ] **Step 1: 修改第 894 行**

```python
# Before:
ret7 = check_return_v5_local(code, date, entry_price, 7, tp, sl, screener.DATA_DIR)

# After:
ret7 = check_return_v5_local(code, date, entry_price, mp.get('hold_days', 7), tp, sl, screener.DATA_DIR)
```

- [ ] **Step 2: 语法检查 + Commit**

```bash
python -c "import py_compile; py_compile.compile('auto_daily.py', doraise=True)"
git add auto_daily.py
git commit -m "fix: auto_daily 使用模式专属 hold_days 而非硬编码7"
```

---

### Task 3: 修复 `simulate_v7_from_may.py` hold_days + 去重

**Files:**
- Modify: `simulate_v7_from_may.py:967` (hold_days)
- Modify: `simulate_v7_from_may.py:579-583` (去重键)
- Modify: `simulate_v7_from_may.py:489-497` (去重键)

- [ ] **Step 1: 修改收益验证 — 第 967 行**

```python
# Before:
hold_days=7,

# After:
hold_days=params.get('hold_days', 7),
```

- [ ] **Step 2: 修改 AI 记录去重 — 第 579-583 行**

```python
# Before:
if rec.get("date") == scan_date_str:

# After:
if rec.get("signal_date") == signal_date_str:
```

- [ ] **Step 3: 修改 signal_tracker 去重 — 第 489-497 行**

```python
# Before (按 entry_price):
if row_date >= cutoff and abs(row_price - entry_price) < 0.01:
    return

# After (按 signal_date):
row_sig_date = row[1] if len(row) > 1 else ''
if row_sig_date == signal_date_str:
    return
```

- [ ] **Step 4: 验证 + Commit**

```bash
python -c "import py_compile; py_compile.compile('simulate_v7_from_may.py', doraise=True)"
python simulate_v7_from_may.py --test
git add simulate_v7_from_may.py
git commit -m "fix: simulate_v7 去重键改为 (code, signal_date) + 模式专属 hold_days"
```

---

### Task 4: 修复 `streamlit_app.py` 绩效总览

**Files:**
- Modify: `streamlit_app.py:2023` (hold_days dict)
- Modify: `streamlit_app.py:2446` (标题)
- Modify: `streamlit_app.py:2483` (字幕)

- [ ] **Step 1: `compute_performance()` 中收集 mode_hold_days**

在循环中加入 mode → hold_days 映射，在 return dict 中加入 `'mode_hold_days'` 字段。

- [ ] **Step 2: 修改绩效总览标题 — 第 2446 行**

```python
# Before:
<div class="section-label">◆ 绩效总览 (近30天 · 7日持有)</div>

# After:
hold_info = ' · '.join(f"{m.upper()}{d}日" for m, d in sorted(perf.get('mode_hold_days', {'': 7}).items())) if perf.get('mode_hold_days') else "7日持有"

f'<div class="section-label">◆ 绩效总览 (近30天 · {hold_info})</div>'
```

- [ ] **Step 3: 修改字幕 — 第 2483 行**

```python
# Before:
f"◆ 7日持有 · {' · '.join(parts)}"

# After:
f"◆ {' · '.join(f'{m.upper()}{d}日' for m, d in sorted(perf.get('mode_hold_days', {}).items()))} · {' · '.join(parts)}"
```

- [ ] **Step 4: 语法检查 + Commit**

```bash
python -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True)"
git add streamlit_app.py
git commit -m "fix: 绩效总览动态显示各模式实际持有天数"
```

---

### Task 5: 4-agent 并行代码审查

- [ ] **Step 1: 启动 4 个 Explore agent 并行审查**

Agent A: 审查 `fix_review_data.py` — 去重逻辑 + 收益重算正确性
Agent B: 审查 `auto_daily.py` + `simulate_v7_from_may.py` — hold_days 修复 + 去重键一致性
Agent C: 审查 `streamlit_app.py` — compute_performance 改动 + UI 显示
Agent D: 全量搜索硬编码 `hold_days=7` — 确保无遗漏

- [ ] **Step 2: 去重发现的 issue，修复**

- [ ] **Step 3: Commit 修复**

---

### Task 6: Verification before completion

- [ ] **Step 1: 运行数据修复脚本**

```bash
python fix_review_data.py
```

- [ ] **Step 2: 检查去重 + verified + STRICT hold_days=10**

```bash
python -c "
import json
with open('ai_memory.json') as f:
    data = json.load(f)
seen = set()
for code, records in data.items():
    for r in records:
        key = (code, r.get('signal_date'))
        assert key not in seen, f'DUPLICATE: {key}'
        seen.add(key)
        assert r['verified'] == True
        assert r['return_7d'] is not None
        if r['mode'] == 'strict':
            assert r['exit_day'] <= 10, f'STRICT exit_day > 10'
print(f'✅ {len(seen)} 条唯一信号, 全部验证通过')
"
```

- [ ] **Step 3: signal_tracker 与 ai_memory 一致性**

```bash
python -c "
import pandas as pd, json
df = pd.read_csv('signal_tracker.csv')
with open('ai_memory.json') as f:
    mem = json.load(f)
mem_pairs = set()
for records in mem.values():
    for r in records:
        mem_pairs.add((r['code'], r.get('signal_date', '')))
csv_pairs = set(zip(df['code'], df['signal_date'].astype(str)))
print(f'signal_tracker: {len(df)} rows, ai_memory: {len(mem_pairs)} unique')
print(f'一致: {mem_pairs == csv_pairs}')
"
```

- [ ] **Step 4: 语法全量检查**

```bash
python -c "import py_compile; py_compile.compile('fix_review_data.py', doraise=True)"
python -c "import py_compile; py_compile.compile('auto_daily.py', doraise=True)"
python -c "import py_compile; py_compile.compile('simulate_v7_from_may.py', doraise=True)"
python -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True)"
```

- [ ] **Step 5: Streamlit 导入验证**

```bash
python -c "import streamlit_app; print('✅ imports OK')"
```

- [ ] **Step 6: 最终 Commit**

```bash
git add -A
git commit -m "chore: verification-before-completion 全部通过 — 复盘绩效修复完成"
```
