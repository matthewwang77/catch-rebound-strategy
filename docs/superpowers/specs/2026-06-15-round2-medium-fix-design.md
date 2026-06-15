# Round 2: MEDIUM Bug Fix

**Date**: 2026-06-15
**Status**: approved
**Scope**: 5 Python files (~6875 lines), focus on MEDIUM-severity issues

## Goal

After Round 1 (34 bugs fixed: 12 CRITICAL + 14 HIGH + 8 MEDIUM), fix remaining MEDIUM-severity issues that affect data correctness, robustness, or have measurable behavioral impact. Exclude pure code-style issues (naming, formatting, comments).

## Scope Filter

From Round 1's 126 findings, ~100 MEDIUM+LOW remain. Filter criteria:
- INCLUDE: data correctness, runtime safety, measurable performance impact
- EXCLUDE: pure style, naming conventions, comment improvements, cosmetic

## Target Groups

### Group 1: Data Correctness (6 items)
- `选股new_v5.py:368` — `period="2y"` insufficient for 2020+ backtest
- `选股new_v5.py:554` — `low==close` exact float equality for one-word detection
- `streamlit_app.py:1299` — DataFrame loses date index
- `streamlit_app.py:1889` — SVG bar scaling uses cumulative values instead of individual returns
- `streamlit_app.py:1966` — `r7==0` trades excluded from win/loss counts
- `auto_daily.py:103` — Assumes lowercase CSV column names

### Group 2: Robustness (5 items)
- `backfill_signals.py:176` — bare `except` swallows all errors
- `auto_daily.py:38/119/570` — yf.download has no timeout
- `streamlit_app.py:2405` — Race condition: two processes write signal_tracker.csv
- `选股new_v5.py:390` — Empty DataFrames written as garbage CSVs
- `backfill_signals.py:227` — Dedup key omits mode, losing multi-mode signals

### Group 3: Code Quality (4 items)
- `streamlit_app.py:1281-1642` — 3 dead functions (~300 lines) never called
- `选股new_v5.py:554/694/800` — `is_one_word` logic duplicated 3 times
- `选股new_v5.py:1853/2187` — Unnecessary `global PARAMS` declarations
- `backfill_signals.py:252/366` — Non-atomic file writes

## Not In Scope
- LOW-severity items (cosmetic, naming, dead imports)
- Architectural refactoring (monolithic file split, CSS extraction) — separate effort
- UI visual changes

## Success Criteria
- All 15 fixes applied
- All 5 files pass syntax check
- TDD regression tests pass
- No new bugs introduced
