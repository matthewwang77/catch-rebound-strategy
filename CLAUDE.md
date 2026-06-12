# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A股连板回调策略 (A-share consecutive limit-up pullback strategy). Identifies stocks that had multiple consecutive limit-up days, experienced a pullback, and are poised for a rebound. Current production version is **v5**, backed by a three-stage funnel parameter optimization (~80k combinations), multi-period cross-validation, and Bootstrap statistical tests.

## Commands

```bash
# Data management
python 选股new_v5.py --download        # Batch download all A-share data (~15k stocks)
python 选股new_v5.py --update-today    # Incremental update for today's data
python 选股new_v5.py --check-data      # Check data completeness

# Stock screening
python 选股new_v5.py --today strict    # Screen with STRICT params (3 limit-ups, high quality)
python 选股new_v5.py --today loose     # Screen with LOOSE params (2 limit-ups, more signals)

# Backtesting & optimization
python 选股new_v5.py --optimize        # Run three-stage parameter optimization
python 选股new_v5.py --full            # Full pipeline: baseline + optimize + bootstrap + walk-forward + compare
python 选股new_v5.py --cross-period    # Multi-period robustness validation
python 选股new_v5.py                   # Default: single-period three-stage optimization

# UI
streamlit run streamlit_app.py         # Launch the NEON VAULT trading dashboard
```

No test suite exists for this project. Validate changes by running `python 选股new_v5.py --today strict` and `python 选股new_v5.py --optimize`.

## Architecture

### Core module: `选股new_v5.py` (2206 lines)

Monolithic strategy file containing the entire pipeline. Key sections in order:

1. **PARAMS dict** (line 33) — default strategy parameters. Overridden by `SCREEN_MODES` at runtime.
2. **COMMISSION dict** (line 58) — A-share trading costs (stamp tax 0.05% on sells, brokerage 0.025% both ways, transfer fee 0.001%, slippage 0.1%).
3. **V4Metrics dataclass + calculate_v4_metrics()** (line 81) — Computes Sharpe, Sortino, Calmar, max drawdown, VaR/CVaR, Ulcer Index, profit factor, expectancy from a signals DataFrame.
4. **Data layer** (line 243) — `generate_all_codes()`, `download_one_stock()`, `load_from_cache()`, `download_all_data_fast()`. Stocks cached as CSV in `stock_data/{code}.csv`.
5. **Signal detection** (line 531) — `identify_limit_up_series()` finds consecutive limit-up runs; `check_pullback_conditions()` validates pullback criteria against the current PARAMS.
6. **Backtest** (line 644) — `run_backtest()` simulates holding periods with take-profit/stop-loss exits, record-by-record.
7. **v5 optimization engine** (line 760) — `extract_all_events()` pre-extracts all limit-up events to avoid redundant scanning. Three-stage funnel: `run_stage_coarse()` → `run_stage_fine()` → `run_stage_ultrafine()`. Each stage narrows parameter ranges around best performers.
8. **Statistical tests** (line 1496) — `cross_period_validation()`, `bootstrap_confidence()`, `permutation_test()`, `parameter_sensitivity()`, `walkforward_analysis_v5()`.
9. **SCREEN_MODES dict** (line 1849) — Two production modes with hardcoded optimal params from v5 optimization. **LOOSE is a strict superset of STRICT** (same `pullback_ratio_max` and `volume_shrink_ratio`; differs only in `min_consecutive_limit_up` 2→3, `min_entity_board_ratio` 0.3→0.55, `pullback_ratio_min` 0.08→0.12).
10. **CLI entry point** (line 2050) — argparse-style manual parsing of `sys.argv`.

### UI: `streamlit_app.py` (1806 lines)

Dark-themed "NEON VAULT" Streamlit dashboard. Key sections:
- `inject_design_system()` — CSS injection via `st.markdown(unsafe_allow_html=True)` with custom fonts (Orbitron, JetBrains Mono)
- `cloud_load_data()` — Hybrid data loading: gzip snapshot → batch yfinance → today injection. Cached 24h via `@st.cache_data`.
- `screen_all_modes()` — Runs both strict/loose screening on loaded data. Pre-filters stocks without recent limit-ups before detailed screening.
- `fast_ai_analysis()` — DeepSeek API integration for per-stock AI analysis (800 max_tokens, 25s timeout).
- Dynamically imports `选股new_v5` as `screener` module via `_load_module()`.

### Stock name lookup: `name_lookup.py`

Three-tier lookup: `stock_names_cn.csv` (Chinese names) → `name_cache.csv` (yfinance cache) → live yfinance query. Includes English→Chinese sector translation dictionary.

### Dual-mode design

| Mode | Limit-ups | Signals/16mo | Win Rate | Sharpe | Use Case |
|------|-----------|-------------|----------|--------|----------|
| STRICT | ≥3 | 79 | 69.6% | 1.71 | 震荡市/不明 |
| LOOSE | ≥2 | 285 | 61.1% | 1.54 | 牛市/强趋势 |

### Data files

- `stock_data/*.csv` — per-stock OHLCV cache (gitignored, too large)
- `active_codes.txt` — filtered list of actively traded codes
- `latest_scan_results.json` — most recent daily scan output
- `signal_tracker.csv` — historical signal log (date, code, mode, entry_price, pullback_pct, limit_days)
- `backtest_results/` — backtest signal CSVs and equity curves per version/period
- `v5_results/` — optimization stage outputs, bootstrap CIs, sensitivity analysis, cross-period validation
- `auto_logs/` — daily automated scan output text files

### Key design decisions

- **No database** — All data is CSV files on disk. Stock price cache in `stock_data/`, results in CSV/JSON.
- **yfinance as sole data source** — No AKShare or other Chinese data APIs. A-share codes use `.SS` (Shanghai) and `.SZ` (Shenzhen) suffixes.
- **Pre-extraction pattern for optimization** — `extract_all_events()` scans all stocks once to find limit-up series, then `evaluate_params_on_events()` replays different parameter sets against these events. This avoids re-downloading data for each parameter combination.
- **`require_oversold` and `require_low_close` are permanently False** — Both filters were eliminated during grid search (Simpson's paradox: they looked good in isolation but degraded multi-factor performance).
- **Syntax check hook** — `.claude/settings.json` has a PostToolUse hook that runs `py_compile` on `.py` files after every Edit/Write.

### Archived files

`archive/` contains older versions (`选股new_v3.py`, `选股new_v4.py`, `真实版V2.py`, `auto_daily.py`), historical optimization data, tools, and old backtest CSVs. Not used in current workflow.
