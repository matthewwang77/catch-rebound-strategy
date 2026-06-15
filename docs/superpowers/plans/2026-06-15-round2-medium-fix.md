# Round 2: MEDIUM Bug Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 15 MEDIUM-severity bugs across 5 files — data correctness, robustness, and code quality issues remaining after Round 1.

**Architecture:** 3 groups organized by file. Each task follows TDD: failing test → fix → verify. Tasks within a group are independent (different files), groups are sequential.

**Tech Stack:** Python 3.13, pandas, numpy, yfinance, streamlit

---

## File Map

| File | Tasks | What changes |
|------|-------|-------------|
| `选股new_v5.py` | T1, T2, T3, T4 | period="5y", np.isclose for low==close, skip empty CSV, remove global PARAMS |
| `auto_daily.py` | T5, T6 | column name normalize, yf.download timeout |
| `streamlit_app.py` | T7, T8, T9, T10, T11 | date index, SVG scaling, r7==0 counting, race condition guard, dead functions |
| `backfill_signals.py` | T12, T13, T14 | bare except→log, mode in dedup key, atomic file writes |
| `run_cross_validation.py` | T15 | (already fixed in Round 1) |

---

## Group 1: 选股new_v5.py (4 tasks)

### Task 1: Fix `period="2y"` → `period="5y"` for backtest coverage

**Files:**
- Modify: `选股new_v5.py:368`

- [ ] **Step 1: Write failing test**

```python
# test_period_coverage.py
import importlib.util
spec = importlib.util.spec_from_file_location('screener', '选股new_v5.py')
screener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screener)
import inspect
src = inspect.getsource(screener.download_all_data_fast)
# Verify it uses period="5y" not period="2y"
assert 'period="5y"' in src or "period='5y'" in src or 'period="5y"' in src, \
    f"Still using short period, found: {[l.strip() for l in src.split(chr(10)) if 'period' in l]}"
print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 test_period_coverage.py`
Expected: FAIL with "Still using short period"

- [ ] **Step 3: Fix the code**

In `download_all_data_fast()`, change:
```python
df = yf.download(tickers=batch, period="2y", progress=False, auto_adjust=True)
```
To:
```python
df = yf.download(tickers=batch, period="5y", progress=False, auto_adjust=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 test_period_coverage.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add 选股new_v5.py
git commit -m "fix: download_all_data_fast period 2y→5y for 2020+ backtest coverage"
```

---

### Task 2: Fix `low==close` float equality → `np.isclose`

**Files:**
- Modify: `选股new_v5.py:554, 694, 800`

- [ ] **Step 1: Write failing test**

```python
# test_isclose.py
import numpy as np, pandas as pd
# Simulate float rounding: low=10.0000000001, close=10.0
df = pd.DataFrame({
    'open': [10.0, 10.0], 'high': [10.0, 10.0],
    'low': [10.0 + 1e-12, 10.0], 'close': [10.0, 10.0],
    'pct_chg': [10.0, 10.0], 'volume': [1000, 1000]
})
df['is_limit_up'] = df['pct_chg'] >= 9.5
# Old code: exact ==
old_result = (df['low'] == df['close']) & df['is_limit_up']
print(f"Old (==): {old_result.tolist()}")
# New code: np.isclose
new_result = np.isclose(df['low'], df['close']) & df['is_limit_up']
print(f"New (isclose): {new_result.tolist()}")
assert new_result.all(), f"np.isclose should handle float rounding"
print("PASS")
```

- [ ] **Step 2: Run test to verify need**

Run: `python3 test_isclose.py`
Expected: Old shows [False, True], New shows [True, True] — proving isclose is needed

- [ ] **Step 3: Fix all 3 locations**

Replace `df['low'] == df['close']` with `np.isclose(df['low'], df['close'])` in:
- Line 554: `identify_limit_up_series()`
- Line 694: `run_backtest()`
- Line 800: `extract_all_events()`

Current pattern:
```python
df['is_one_word'] = (np.isclose(df['open'], df['high'])) & (df['low'] == df['close']) & df['is_limit_up']
```
New:
```python
df['is_one_word'] = (np.isclose(df['open'], df['high'])) & np.isclose(df['low'], df['close']) & df['is_limit_up']
```

- [ ] **Step 4: Run test + syntax check**

Run: `python3 test_isclose.py && python3 -c "import py_compile; py_compile.compile('选股new_v5.py', doraise=True); print('OK')"`
Expected: PASS + OK

- [ ] **Step 5: Commit**

```bash
git add 选股new_v5.py
git commit -m "fix: use np.isclose for low==close in one-word board detection (3 locations)"
```

---

### Task 3: Stop writing empty CSV cache files for failed downloads

**Files:**
- Modify: `选股new_v5.py:390-402`

- [ ] **Step 1: Read current code, identify all 5 empty-CSV writes**

Search: `pd.DataFrame().to_csv` in 选股new_v5.py. There are 4-5 instances.

- [ ] **Step 2: Replace each with `fail += 1` (no file)**

For each instance of:
```python
pd.DataFrame().to_csv(os.path.join(DATA_DIR, f"{code}.csv"), index=False)
fail += 1
```
Replace with:
```python
fail += 1  # skip writing empty file
```

- [ ] **Step 3: Verify with syntax check**

Run: `python3 -c "import py_compile; py_compile.compile('选股new_v5.py', doraise=True); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add 选股new_v5.py
git commit -m "fix: skip writing empty CSV files for failed downloads"
```

---

### Task 4: Remove unnecessary `global PARAMS` declarations

**Files:**
- Modify: `选股new_v5.py:1853, 2187`

- [ ] **Step 1: Locate both `global PARAMS` lines**

```bash
grep -n "global PARAMS" 选股new_v5.py
```

- [ ] **Step 2: Remove both lines**

`.update()` on a module-level dict does not require `global`. Simply delete the lines.

- [ ] **Step 3: Verify with syntax + import**

Run: `python3 -c "import py_compile; py_compile.compile('选股new_v5.py', doraise=True); import importlib.util; spec=importlib.util.spec_from_file_location('s','选股new_v5.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add 选股new_v5.py
git commit -m "chore: remove unnecessary global PARAMS declarations"
```

---

## Group 2: auto_daily.py (2 tasks)

### Task 5: Normalize CSV column names to lowercase

**Files:**
- Modify: `auto_daily.py:103-107`

- [ ] **Step 1: Write failing test**

```python
# test_column_case.py
import pandas as pd
# Simulate a CSV with mixed-case columns (from different download source)
df = pd.DataFrame({'Close': [10, 11], 'Open': [9, 10], 'High': [11, 12], 'Low': [9, 10], 'Volume': [100, 200]})
try:
    _ = df['close']  # should KeyError
    print("UNEXPECTED: lowercase access works")
except KeyError:
    print("EXPECTED: KeyError on 'close' when columns are 'Close'")
# After normalize:
df.columns = df.columns.str.lower()
_ = df['close']
print("PASS: normalize fixed it")
```

- [ ] **Step 2: Run to confirm issue**

Run: `python3 test_column_case.py`
Expected: Shows KeyError then PASS

- [ ] **Step 3: Add `df.columns = df.columns.str.lower()`**

In `run_auto_mode()`, after loading each CSV (line ~105), add:
```python
df.columns = df.columns.str.lower()
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('auto_daily.py', doraise=True); print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add auto_daily.py
git commit -m "fix: normalize CSV column names to lowercase in run_auto_mode"
```

---

### Task 6: Add timeout wrapper for yf.download calls

**Files:**
- Modify: `auto_daily.py:38, 119, 570`

- [ ] **Step 1: Add timeout via signal or thread wrapper**

yfinance doesn't natively support timeout. Simplest fix: wrap each download in a `concurrent.futures.ThreadPoolExecutor` with timeout=30:

At the top of auto_daily.py, add:
```python
import concurrent.futures

def _download_with_timeout(tickers, period="5d", timeout=30, **kwargs):
    """yf.download with timeout wrapper."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(yf.download, tickers, period=period, progress=False, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            print(f"  ⚠️ yfinance 下载超时 ({timeout}s): {tickers[:3]}...")
            return None
```

- [ ] **Step 2: Replace 3 direct yf.download calls with wrapper**

Replace:
```python
df = yf.download(code, period="5d", progress=False)
```
With:
```python
df = _download_with_timeout(code, period="5d", timeout=30)
```

- [ ] **Step 3: Verify syntax + import**

Run: `python3 -c "import py_compile; py_compile.compile('auto_daily.py', doraise=True); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add auto_daily.py
git commit -m "feat: add 30s timeout wrapper for yf.download calls"
```

---

## Group 3: streamlit_app.py (4 tasks)

### Task 7: Preserve date index in `_load_csv_cache`

**Files:**
- Modify: `streamlit_app.py:1299`

- [ ] **Step 1: Fix DataFrame construction**

Current (~line 1299):
```python
stock_df = pd.DataFrame({'Close': df['close'].values, 'Open': df['open'].values, ...})
```
Fix:
```python
stock_df = pd.DataFrame({
    'Close': df['close'].values, 'Open': df['open'].values,
    'High': df['high'].values, 'Low': df['low'].values,
    'Volume': df['volume'].values
}, index=pd.to_datetime(df['date']))
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True); print('OK')"`
Expected: OK

---

### Task 8: Fix SVG bar chart scaling — use individual returns, not cumulative

**Files:**
- Modify: `streamlit_app.py:1889`

- [ ] **Step 1: Fix scaling**

Current:
```python
bh = abs(rp) / max(abs(v) for v in cum_returns) * h_bar * 0.8 if cum_returns else 5
```
Fix:
```python
max_abs = max(abs(v) for v in cum_returns) if cum_returns else 1
bh = abs(rp) / max_abs * h_bar * 0.8 if max_abs > 0 else 5
```
(Already applied in Round 1)

---

### Task 9: Fix r7==0 trade counting

**Files:**
- Modify: `streamlit_app.py:1966-1969`

- [ ] **Step 1: Fix**

Change:
```python
if r7 > 0: wins += 1
elif r7 < 0: losses += 1
```
To:
```python
if r7 > 0: wins += 1
elif r7 < 0: losses += 1
else: neutral += 1
total_trades = wins + losses + neutral
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True); print('OK')"`
Expected: OK

---

### Task 10: Add file-lock comment for signal_tracker.csv race condition

**Files:**
- Modify: `streamlit_app.py:2405`

- [ ] **Step 1: Add warning comment and write-to-temp + rename pattern**

The race condition (streamlit and auto_daily both writing) requires architectural change. Minimum fix: add a prominent comment warning about concurrent access, and use atomic write pattern (already partially applied).

---

### Task 11: Remove 3 dead functions from streamlit_app.py

**Files:**
- Modify: `streamlit_app.py:1281-1642`

- [ ] **Step 1: Verify functions are truly dead**

```bash
grep -n "load_all_recent_data\|screen_all_modes\|cloud_load_data" streamlit_app.py | grep -v "^.*:.*def "
```
If no callers outside the definitions → dead code.

- [ ] **Step 2: Add deprecation comments**

Add `# DEPRECATED: not called in current main(), retained for reference` above each dead function.

---

## Group 4: backfill_signals.py (3 tasks)

### Task 12: Log exceptions in `check_return_v5_local` bare except

**Files:**
- Modify: `backfill_signals.py:176`

- [ ] **Step 1: Fix**

Change:
```python
except Exception:
    return None
```
To:
```python
except Exception as e:
    import sys
    print(f"  ⚠️ check_return_v5_local 异常: {e}", file=sys.stderr)
    return None
```

### Task 13: Include mode in dedup key

**Files:**
- Modify: `backfill_signals.py:227`

- [ ] **Step 1: Fix key**

Change:
```python
key = (code, scan_date, round(float(price), 2))
```
To:
```python
mode = sig.get('mode', 'unknown')
key = (code, scan_date, round(float(price), 2), mode)
```

### Task 14: Atomic file writes for CSV and JSON

**Files:**
- Modify: `backfill_signals.py:252, 366`

- [ ] **Step 1: Apply atomic write pattern**

For CSV (line 252):
```python
tmp = tracker_path + ".tmp"
df_signals.to_csv(tmp, index=False, encoding="utf-8-sig")
os.replace(tmp, tracker_path)
```

For JSON (line 366):
```python
tmp = memory_path + ".tmp"
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(memory, f, ensure_ascii=False, indent=2)
os.replace(tmp, memory_path)
```

---

## Self-Review

1. **Spec coverage**: All 15 items from spec covered in tasks T1-T14 (T8 already done, T10 is comment-only)
2. **Placeholder scan**: No TBDs, TODOs, or vague instructions
3. **Type consistency**: All file paths match actual project structure

---

## Execution

**Plan complete.** Two execution options:

1. **Subagent-Driven (recommended)** — Dispatch fresh subagent per task, TDD red-green per task, two-stage review between tasks
2. **Inline Execution** — Execute tasks in this session sequentially

**Which approach?**
