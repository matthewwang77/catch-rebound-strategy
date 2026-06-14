# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A股连板回调策略 (A-share consecutive limit-up pullback strategy). Identifies stocks that had multiple consecutive limit-up days, experienced a pullback, and are poised for a rebound. Current production version is **v6**, backed by a three-stage funnel parameter optimization (~80k combinations), multi-period cross-validation, Bootstrap statistical tests, market-regime-adaptive parameter switching, AI memory system, and async analysis queue.

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

# Automated daily pipeline
python auto_daily.py                   # Full auto: screen → save JSON → git push (for Streamlit Cloud)
bash auto_update.sh                    # launchd-triggered incremental data update

# UI
streamlit run streamlit_app.py         # Launch the NEON VAULT trading dashboard
```

No test suite exists for this project. Validate changes by running `python 选股new_v5.py --today strict` and `python 选股new_v5.py --optimize`. The `.claude/settings.json` PostToolUse hook automatically runs `py_compile` on `.py` files after every Edit/Write, catching syntax errors immediately.

## Environment Variables

- `DEEPSEEK_API_KEY` — Required for AI analysis in Streamlit and auto_daily. Set in `~/.claude/settings.json` `env` block or via `export`. The DeepSeek endpoint is hardcoded as `DEEPSEEK_API_URL` in 选股new_v5.py line 1902.

## Architecture

### Core module: `选股new_v5.py` (2246 lines)

Monolithic strategy file containing the entire pipeline. Key sections in order:

1. **PARAMS dict** (line 33) — default strategy parameters. Overridden by `SCREEN_MODES` at runtime.
2. **COMMISSION dict** (line 58) — A-share trading costs (stamp tax 0.05% on sells, brokerage 0.025% both ways, transfer fee 0.001%, slippage 0.1%).
3. **V4Metrics dataclass + calculate_v4_metrics()** (line 81) — Computes Sharpe, Sortino, Calmar, max drawdown, VaR/CVaR, Ulcer Index, profit factor, expectancy from a signals DataFrame.
4. **Data layer** (line 243) — `generate_all_codes()`, `download_one_stock()`, `load_from_cache()`, `download_all_data_fast()`. Stocks cached as CSV in `stock_data/{code}.csv`.
5. **Signal detection** (line 531) — `identify_limit_up_series()` finds consecutive limit-up runs; `check_pullback_conditions()` validates pullback criteria against the current PARAMS.
6. **Backtest** (line 644) — `run_backtest()` simulates holding periods with take-profit/stop-loss exits, record-by-record.
7. **v5 optimization engine** (line 760) — `extract_all_events()` pre-extracts all limit-up events to avoid redundant scanning. Three-stage funnel: `run_stage_coarse()` → `run_stage_fine()` → `run_stage_ultrafine()`. Each stage narrows parameter ranges around best performers. Uses `cluster_top_params()` for k-means clustering of top results between stages.
8. **Statistical tests** (line 1496) — `cross_period_validation()`, `bootstrap_confidence()`, `permutation_test()`, `parameter_sensitivity()`, `walkforward_analysis_v5()`.
9. **SCREEN_MODES dict** (line 1849) — Two production modes with hardcoded optimal params from v5 optimization. Both have `require_oversold` and `require_low_close` set to `False` (eliminated during grid search — Simpson's paradox). LOOSE is a superset of STRICT (same `pullback_ratio_max`=0.40 and `volume_shrink_ratio`=0.67).
10. **`get_market_context()`** (line 1905) — Computes index returns and market sentiment level for AI analysis context. Returns a dict with `sentiment_tier` used by the Streamlit AI prompt.
11. **`_screen_single_stock()`** (line 1967) — Single-stock screening function used by both `screen_today()` and `auto_daily.py`'s `run_all_modes()`.
12. **CLI entry point** (line 2050) — argparse-style manual parsing of `sys.argv`.

### Automated pipeline: `auto_daily.py` (372 lines)

Self-contained daily screening script designed for launchd/cron scheduling:
- `run_all_modes()` — Loads cached CSVs from `stock_data/`, injects today's live data via yfinance batch download, then screens with both strict and loose modes via `screener._screen_single_stock()`.
- `save_results_json()` — Writes structured JSON to `latest_scan_results.json` (for Streamlit auto-load) + archived copy to `results_archive/{YYYYMMDD}.json`.
- `git_push_results()` — Auto-commits and pushes results to GitHub, triggering Streamlit Cloud redeploy.
- `format_message()` — Generates human-readable text log saved to `auto_logs/`.

Scheduling config (macOS launchd) is embedded as comments at end of file — 4 daily runs at 10:00, 11:30, 14:00, 15:00 on weekdays.

### Update helper: `auto_update.sh`

Minimal bash script called by launchd to run `update_today_data()` from 选股new_v5.py. Logs to `/tmp/grab_rebound_update.log`.

### UI: `streamlit_app.py` (2742 lines)

Dark-themed "NEON VAULT" Streamlit dashboard with two pages: 选股 (screening) and 复盘 (review).

**Design system (line 30):**
- `inject_design_system()` — CSS injection via `st.markdown(unsafe_allow_html=True)` with custom fonts (Orbitron, JetBrains Mono), dot grid background, scan lines, neon color palette (#00ff88, #ff6b35, #ffd700).

**Data loading (line 742 & 920):**
- `load_all_recent_data()` — Local mode: CSV cache → batch yfinance injection.
- `cloud_load_data()` — Cloud mode: gzip snapshot (`stock_snapshot.csv.gz`) → batch yfinance → today injection. Cached 24h via `@st.cache_data`.
- `load_latest_results()` (line 2016) — Auto-loads precomputed scan results from `latest_scan_results.json` (produced by `auto_daily.py`). Falls back to live screening if JSON is missing/stale.

**Screening (line 1365 & 1921):**
- `screen_all_modes()` — Runs both strict/loose screening on loaded data. Pre-filters stocks without recent limit-ups before detailed screening.
- `show_screening_results()` — Renders candidate cards with AI analysis expanders.

**AI Analysis (line 1040):**
- `fast_ai_analysis()` — DeepSeek API integration using the "量价形时" (volume-price-pattern-timing) four-dimension framework. Computes MACD(12,26,9), RSI(14), Bollinger Bands(20,2), OBV trend, and MFI(14) indicators locally before sending to DeepSeek. Includes 情绪档位 (sentiment tier) for position sizing advice. 800 max_tokens, 25s timeout. Accepts optional `memory_context` injected from AI memory system.

**AI Memory System (line 1612):**
- `ai_memory.json` — Persistent store of historical AI analyses, keyed by stock code.
- `save_ai_analysis_record()` — Archives each analysis with date, sentiment, position advice, opinion. Regex-extracts structured fields (仓位建议, 情绪档位, 最终结论) from free-text AI response. Deduplicates by (code, date).
- `auto_verify_memory()` — After ≥3 days, backfills actual returns (3d/5d/7d) via `check_return_v5()` and sets verdict to "correct" (positive) or "wrong" (negative). Also performs retroactive fix-up on old records missing sentiment extraction.
- `get_stock_memory_context()` — Builds a formatted history block for the most recent 5 records, injected into future AI prompts as `[历史分析记录]`.

**Async Analysis Queue (line 2034):**
- `_analysis_worker()` — Background daemon thread that consumes a FIFO `analysis_queue` from `st.session_state`. Calls `fast_ai_analysis()` with market context and memory context, stores results in `analysis_results`, auto-saves to AI memory.
- `start_analysis_queue(codes)` — Enqueues codes and starts a new worker thread only if none is already running (prevents duplicate threads). JS polling reads `analysis_current` and `analysis_progress` from session state for the progress bar UI.

**Review page (复盘) (line 1497 & 1788):**
- `check_return_v5()` — Simulates exit with take-profit/stop-loss for a given holding period. Returns dict with `return_pct`, `exit_reason`, `exit_date`, `hold_days_actual`.
- `compute_performance()` — Computes aggregate performance metrics from `signal_tracker.csv` using mode-specific TP/SL params from `SCREEN_MODES`. Supports mode filter and lookback window.
- `save_signals()` — Appends candidate signals to `signal_tracker.csv`.
- Dynamically imports `选股new_v5` as `screener` module via `_load_module()`.

### Stock name lookup: `name_lookup.py` (245 lines)

Three-tier lookup: `stock_names_cn.csv` (Chinese names) → `name_cache.csv` (yfinance cache) → live yfinance query. Includes English→Chinese sector translation dictionary.

### Tri-mode design (v6)

| Mode | Limit-ups | Win Rate | Sharpe | Use Case |
|------|-----------|----------|--------|----------|
| BEAR | ≥2 | 50.9% | 7.06 | 熊市/冰点/低迷 — 浅回调(6-11%)+极度缩量(41%)+快进快出(7天) |
| STRICT | ≥3 | 66.4% | 9.53 (IS) | 震荡市/启动期 — 高质量低频率 |
| LOOSE | ≥2 | 49.9% | 4.46 (IS) | 牛市/发酵/高潮 — 最泛化最稳健 🏆 |

**v6 关键发现**: BEAR 模式与 STRICT/LOOSE 有根本性差异 — `pullback_ratio_max` 从 0.40 砍到 0.11。在熊市中，默认参数（STRICT/LOOSE）夏普 -3.7，BEAR 模式提升至 +7.1。

**2026-06-14 过拟合诊断**: BULL 模式（原 Tier 5 强牛专属）IS Sharpe 19.56 → OOS 1.22，严重过拟合，已移除。
LOOSE 在牛市中 OOS Sharpe 7.29，是真正可复现的收益。LOOSE 是唯一 OOS > IS 且 Walk-forward OOS 优于 IS 的模式。

### Market regime detection (`detect_market_regime()`)

基于三大指数（上证/深证/创业板）5日趋势自动分档：
- 1档 冰点期 (< -2%) → BEAR (强制互斥)
- 2档 低迷期 (-2% ~ -0.5%) → BEAR (强制互斥)
- 3档 启动期 (-0.5% ~ +1%) → STRICT
- 4档 发酵期 (+1% ~ +3%) → LOOSE
- 5档 高潮期 (> +3%) → LOOSE

`screen_today()` 默认 `mode='auto'` 自动检测并切换。`auto_daily.py` 和 `streamlit_app.py` 均已集成。

### 过拟合诊断结论 (2026-06-14)

完整的 3×4 交叉验证 + Bootstrap + Walk-forward + 参数敏感性诊断（见 `run_overfitting_diagnostics.py` 和 `v5_results/v6_overfitting_diagnostics.json`）：

| 模式 | IS Sharpe | OOS Sharpe | Walk-forward | 参数稳健性 | 风险 |
|------|:---------:|:----------:|:------------:|:--------:|:----:|
| BEAR | 7.06 | 6.51 | — | 6/7关键 | 🟡 50 |
| STRICT | 9.53 | 1.24 | ✅ OOS > IS | 5/7关键 | 🔴 65 |
| LOOSE | 4.46 | 3.96 | ✅ OOS > IS | 2/7关键 | 🟢 25 |
| ~~BULL~~ | ~~19.56~~ | ~~1.22~~ | — | ~~6/7~~ | 🔴 已移除 |

**核心教训**: 三阶段漏斗优化（~200k组合）在单一周期上能找到极高分，但泛化能力差。LOOSE 用最简单的参数（最少优化）换来了最好的泛化。**过多的参数优化自由度 = 过拟合风险。**

**⚠️ 已知 Bug**: `permutation_test()` 只 shuffle 收益率序列，不改变均值/方差，导致 p 值恒为 ~0.9-1.0，检验无效。需修复为随机入场日期或 bootstrap 分布比较。

### Data files

- `stock_data/*.csv` — per-stock OHLCV cache (gitignored, too large)
- `stock_snapshot.csv.gz` — gzip snapshot of ~5200 stocks 30d history for cloud deployment
- `active_codes.txt` — filtered list of actively traded codes
- `latest_scan_results.json` — most recent daily scan output (produced by `auto_daily.py`, consumed by `streamlit_app.py`)
- `results_archive/{YYYYMMDD}.json` — daily archived scan results
- `signal_tracker.csv` — historical signal log (date, code, mode, entry_price, pullback_pct, limit_days)
- `ai_memory.json` — AI analysis memory store: per-stock records with sentiment, position, opinion, verified returns, verdict
- `stock_names_cn.csv` / `name_cache.csv` — stock name lookup tables
- `backtest_results/` — backtest signal CSVs and equity curves per version/period
- `v5_results/` — optimization stage outputs, bootstrap CIs, sensitivity analysis, cross-period validation
- `auto_logs/` — daily automated scan output text files
- `requirements.txt` — minimal deps (streamlit, yfinance, pandas, numpy, requests)
- `TASK1_算法改进.md` — pending algorithm improvement task based on HuaAn research. ⚠️ References `选股new.py` (legacy name) — apply to `选股new_v5.py`. Simpson's paradox warning included.

### Key design decisions

- **No database** — All data is CSV/JSON files on disk. Stock price cache in `stock_data/`, results in CSV/JSON.
- **yfinance as sole data source** — No AKShare or other Chinese data APIs. A-share codes use `.SS` (Shanghai) and `.SZ` (Shenzhen) suffixes.
- **Pre-extraction pattern for optimization** — `extract_all_events()` scans all stocks once to find limit-up series, then `evaluate_params_on_events()` replays different parameter sets against these events. This avoids re-downloading data for each parameter combination.
- **`require_oversold` and `require_low_close` are permanently False** — Both filters were eliminated during grid search (Simpson's paradox: they looked good in isolation but degraded multi-factor performance). The parameters remain in the dict for future experimentation but are never activated in production modes. TASK1_算法改进.md proposes re-adding them — verify with full backtest before activating.
- **Automated git-push pipeline** — `auto_daily.py` commits and pushes `latest_scan_results.json` + `results_archive/` to GitHub, which triggers Streamlit Cloud to redeploy with fresh results. This decouples data freshness from app load time.
- **AI memory closed loop** — Every AI analysis is archived, auto-verified against actual returns after 3+ days, and injected as context for future analyses of the same stock. This creates a self-improving feedback loop.
- **Syntax check hook** — `.claude/settings.json` has a PostToolUse hook that runs `py_compile` on `.py` files after every Edit/Write. No need to manually syntax-check — the hook catches errors immediately.
- **Async analysis pattern** — AI analysis runs in a background daemon thread with JS polling for progress. `start_analysis_queue()` checks for existing worker before spawning, preventing duplicate threads.

### Project-level skills

`.claude/skills/` contains symlinked agent skills (10 total):
- `developing-with-streamlit` — Streamlit-specific development guidance
- `schedule-it` — Scheduling/task automation patterns
- `ckm-banner-design`, `ckm-brand`, `ckm-design`, `ckm-design-system`, `ckm-slides`, `ckm-ui-styling` — Design system / branding skills
- `make-interfaces-feel-better`, `ui-ux-pro-max` — UI/UX improvement skills

`.superpowers/` — Superpowers development methodology artifacts (brainstorm sessions, etc.).

### Archived files

`archive/` contains older versions (`选股new_v3.py`, `选股new_v4.py`, `真实版V2.py`, `auto_daily.py` old version), historical optimization data, tools, and old backtest CSVs. Not used in current workflow.
