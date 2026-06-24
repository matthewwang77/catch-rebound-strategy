# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A股连板回调策略 (A-share consecutive limit-up pullback strategy). Identifies stocks that had multiple consecutive limit-up days, experienced a pullback, and are poised for a rebound. Current production version is **v7** (v7 re-optimized parameters deployed 2026-06-15 across all three SCREEN_MODES, backed by three-stage funnel optimization ~200k combinations, multi-period cross-validation, Bootstrap statistical tests, market-regime-adaptive parameter switching, AI memory closed-loop with 7-day post-mortem reviews, market news system, and fully automated daily pipeline).

## Commands

```bash
# Data management
python 选股new_v5.py --download        # Batch download all A-share data (~15k stocks)
python 选股new_v5.py --update-today    # Incremental update for today's data
python 选股new_v5.py --check-data      # Check data completeness

# Stock screening (v7: all modes require ≥3 limit-ups)
python 选股new_v5.py --today strict    # Screen with STRICT params
python 选股new_v5.py --today loose     # Screen with LOOSE params
python 选股new_v5.py --today bear      # Screen with BEAR params

# Backtesting & optimization
python 选股new_v5.py --optimize        # Run three-stage parameter optimization
python 选股new_v5.py --full            # Full pipeline: baseline + optimize + bootstrap + walk-forward + compare
python 选股new_v5.py --cross-period    # Multi-period robustness validation
python 选股new_v5.py                   # Default: single-period three-stage optimization

# Automated daily pipeline
python auto_daily.py                   # Full auto: screen → AI analysis → save JSON → 7d review → maintenance → git push
bash auto_update.sh                    # launchd-triggered incremental data update

# Historical simulation
python simulate_v7_from_may.py         # v7 backfill: replay from 2026-05-01 with v7 params + AI analysis

# Data utilities
python backfill_signals.py             # Backfill historical signals from results_archive/
python fix_review_data.py [--dry-run]  # Dedupe + recompute 7d returns using mode-specific params

# Market news & data
python market_news.py                  # Fetch + AI-analyze today's market news (5 sources)
python auto_daily.py --check-market    # Diagnose all market data sources (AKShare/yfinance/JSON)
python auto_daily.py --refresh-market  # Update latest_scan_results.json with actual closing prices (run after 15:30)

# UI
streamlit run streamlit_app.py         # Launch the NEON VAULT trading dashboard
```

No test suite exists for this project. Validate changes by running `python 选股new_v5.py --today strict` and `python 选股new_v5.py --optimize`. The `.claude/settings.json` PostToolUse hook automatically runs `py_compile` on `.py` files after every Edit/Write, catching syntax errors immediately.

### Standalone analysis scripts (import `选股new_v5` as a module via `importlib`)

| Script | Purpose |
|--------|---------|
| `run_overfitting_diagnostics.py` | Full overfitting diagnosis (3×4 cross-validation, bootstrap, permutation, walk-forward, sensitivity) |
| `run_cross_validation.py` | Multi-period cross-validation run |
| `run_deep_optimization.py` | Deep parameter optimization (three-stage funnel, all periods) |
| `run_periodA_deep_optimization.py` | Deep optimization on Period A only |
| `run_periodB_stage23.py` | Stage 2+3 optimization on Period B |
| `simulate_v7_from_may.py` | Replay v7 screening from 2026-05-01 — reconstructs market context per-day, truncates stock data to avoid look-ahead, screens with v7 params, runs AI analysis, writes to signal_tracker/ai_memory/results_archive |

## Environment Variables

- `DEEPSEEK_API_KEY` — Required for AI analysis in Streamlit, auto_daily, simulate_v7_from_may, and market_news. Set in `~/.claude/settings.json` `env` block or via `export`. The DeepSeek endpoint is hardcoded as `DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"` in 选股new_v5.py.
- `.claude/settings.local.json` — Project-local settings file (gitignored). Overrides `.claude/settings.json` for machine-specific config (Python paths, env vars, hooks). Currently has PostToolUse hooks for py_compile and custom permissions.

## Architecture

### Core module: `选股new_v5.py` (2563 lines)

Monolithic strategy file containing the entire pipeline. Key sections in order (line numbers approximate — this file evolves frequently):

1. **PARAMS dict** (line 33) — default strategy parameters. Overridden by `SCREEN_MODES` at runtime.
2. **COMMISSION dict** (line 58) — A-share trading costs (stamp tax 0.05% on sells, brokerage 0.025% both ways, transfer fee 0.001%, slippage 0.1%).
3. **V4Metrics dataclass + calculate_v4_metrics()** (line 81) — Computes Sharpe, Sortino, Calmar, max drawdown, VaR/CVaR, Ulcer Index, profit factor, expectancy from a signals DataFrame.
4. **Data layer** (line 243) — `generate_all_codes()`, `download_one_stock()`, `load_from_cache()`, `download_all_data_fast()`. Stocks cached as CSV in `stock_data/{code}.csv`.
5. **Signal detection** (line 542) — `identify_limit_up_series()` finds consecutive limit-up runs; `check_pullback_conditions()` validates pullback criteria against the current PARAMS.
6. **Backtest** (line 656) — `run_backtest()` simulates holding periods with take-profit/stop-loss exits, record-by-record.
7. **v5 optimization engine** (line 773) — `extract_all_events()` pre-extracts all limit-up events to avoid redundant scanning. Three-stage funnel: `run_stage_coarse()` → `run_stage_fine()` → `run_stage_ultrafine()`. Each stage narrows parameter ranges around best performers. Uses `cluster_top_params()` for k-means clustering of top results between stages.
8. **Statistical tests** (line 1539) — `cross_period_validation()`, `bootstrap_confidence()`, `permutation_test()`, `parameter_sensitivity()`, `walkforward_analysis_v5()`.
9. **SCREEN_MODES dict** (line 1908) — Three production modes (BEAR/STRICT/LOOSE) with **v7 re-optimized params** (2026-06-15). All three modes now require **≥3 consecutive limit-ups**. All have `require_oversold` and `require_low_close` set to `False` (eliminated during grid search — Simpson's paradox).
10. **`detect_market_regime()`** (line 2163) — Computes 三大指数 5-day trends, returns recommended mode for auto-screening.
11. **`get_market_context()`** (line 2084) — Computes index returns and market sentiment level for AI analysis context. Returns a dict with `sentiment_tier` used by the Streamlit AI prompt.
12. **`_screen_single_stock()`** (line 2249) — Single-stock screening function used by both `screen_today()` and `auto_daily.py`'s `run_auto_mode()`.
13. **CLI entry point** (line ~2350) — argparse-style manual parsing of `sys.argv`.

### Automated pipeline: `auto_daily.py` (1290 lines)

Self-contained daily screening script designed for launchd/cron scheduling. Major expansion in June 2026 (was 372 lines):

- **`run_auto_mode()`** (line 105) — Market regime detection → CSV cache loading → batch yfinance today-injection → screening via `screener._screen_single_stock()`.
- **`_save_signals()`** (line 219) — Appends to `signal_tracker.csv` (dedup by code+date).
- **AI analysis** (line 365) — `_run_ai_analysis()` computes MACD(12,26,9), RSI(14), Bollinger Bands(20,2), OBV trend, and MFI(14) indicators locally, then sends to DeepSeek with the "量价形时" (volume-price-pattern-timing) four-dimension framework. Includes 情绪档位 (sentiment tier) for position sizing advice. 3000 max_tokens, 25s timeout, 3 retries. Results saved to `ai_memory.json`.
- **AI 7-day post-mortem review** (line 854) — `_run_ai_review()` performs retrospective analysis on signals ≥7 days old: checks what happened, why the AI was right/wrong, what signals were missed, and extracts lessons. Feeds back into `ai_memory.json` for the closed-loop learning system.
- **Verdict logic** (line 829) — `_compute_verdict()` assigns verdicts (correct/wrong/missed/avoided/noted_up/noted_down) based on AI opinion vs actual 7d return.
- **`_auto_maintenance()`** (line 1031) — Runs 7-day review on all un-reviewed records, verifies returns, performs retroactive sentiment fix-up on old records.
- **`save_results_json()`** (line 679) — Writes `latest_scan_results.json` + `results_archive/{YYYYMMDD}.json`.
- **`git_push_results()`** (line 794) — Auto-commits and pushes to GitHub, triggering Streamlit Cloud redeploy.
- **`format_message()`** (line 632) — Human-readable text log saved to `auto_logs/`.

Scheduling config (macOS launchd) embedded as comments at end of file — 4 daily runs at 10:00, 11:30, 14:00, 15:00 on weekdays.

### Market news system: `market_news.py` (532 lines)

Multi-source market news aggregation + AI analysis, integrated into Streamlit as a dedicated page:

- **3 data sources**: 东方财富 (via AKShare `stock_info_global_em()`), 财联社 (CLS API), Yahoo Finance news
- **Relevance pre-filtering**: ~50 A-share relevance keywords (板块, 涨停, 央行, 降息, etc.) — only news matching at least one keyword passes through
- **AI analysis**: Sends filtered news to DeepSeek for: sentiment classification (偏多/偏空/中性), top 10 key stories with impact analysis, thematic summary, overnight US market wrap
- **Output**: `market_news.json` (latest) + `news_archive/YYYYMMDD.json` (historical archives)
- **Streamlit integration**: Dedicated "📰 新闻" page reads from `market_news.json`, displays AI-curated top stories with sentiment badges, thematic categorization, and source attribution. News sentiment is injected into the screening AI prompt as market context.
- Run standalone: `python market_news.py`

### UI: `streamlit_app.py` (3026 lines)

Dark-themed "NEON VAULT" Streamlit dashboard with three pages: 选股 (screening), 复盘 (review), 新闻 (news).

**Design system (line 30):**
- `inject_design_system()` — CSS injection via `st.markdown(unsafe_allow_html=True)` with custom fonts (Orbitron, JetBrains Mono), dot grid background, scan lines, neon color palette (#00ff88, #ff6b35, #ffd700). Full spec in [DESIGN.md](DESIGN.md).

**Data loading (line 742 & 920):**
- `load_all_recent_data()` — Local mode: CSV cache → batch yfinance injection.
- `cloud_load_data()` — Cloud mode: gzip snapshot (`stock_snapshot.csv.gz`) → batch yfinance → today injection. Cached 24h via `@st.cache_data`.
- `load_latest_results()` (line 2016) — Auto-loads precomputed scan results from `latest_scan_results.json` (produced by `auto_daily.py`). Falls back to live screening if JSON is missing/stale.

**Screening (line 1365 & 1921):**
- `screen_all_modes()` — Runs strict/loose screening on loaded data. Pre-filters stocks without recent limit-ups before detailed screening.
- `show_screening_results()` — Renders candidate cards with AI analysis expanders.

**News page (line 2860):**
- Reads precomputed news from `market_news.json` (produced by `market_news.py` or `auto_daily.py`). Displays AI-curated top stories with sentiment badges, thematic cards, and source links.

**AI Analysis (read from cache, NOT live):**
- Streamlit reads precomputed AI analysis from `ai_memory.json` (produced by `auto_daily.py`). No live API calls, no worker threads. This decouples AI computation from UI rendering — analysis runs in the daily pipeline, UI displays cached results instantly.
- Fallback: if `ai_memory.json` lacks a record, checks `st.session_state` for any live analysis result (legacy compatibility).

**AI Memory System (line 1612):**
- `ai_memory.json` — Persistent store of historical AI analyses, keyed by stock code. Each record includes: date, sentiment, position advice, opinion, entry price, pullback%, limit days, mode, precomputed returns (3d/5d/7d), exit reason, verdict, and structured review fields (`what_happened`, `why_wrong`, `missed_signal`, `lesson`).
- `save_ai_analysis_record()` — Archives each analysis with date, sentiment, position advice, opinion. Regex-extracts structured fields (仓位建议, 情绪档位, 最终结论) from free-text AI response. Deduplicates by (code, date).
- `auto_verify_memory()` — After ≥7 days, backfills actual returns (3d/5d/7d) via `check_return_v5_local()` (imported from `backfill_signals.py`) and sets verdict. Also performs retroactive fix-up on old records missing sentiment extraction.
- `get_stock_memory_context()` — Builds a formatted history block for the most recent 5 records, injected into future AI prompts as `[历史分析记录]`. When history contains wrong/missed verdicts, injects reflection prompts to help AI learn from past mistakes.
- **Verdict matrix (裁决矩阵)**: 6 verdict types — `correct` (AI was right, made money), `wrong` (AI was wrong, lost money), `missed` (good stock AI missed), `avoided` (correctly avoided a loser), `noted_up`/`noted_down` (neutral observation). Verdict badges are color-coded in the UI (green=correct, red=wrong, amber=missed, purple=noted).

**Review page (复盘) (line 1497 & 1921):**
- `check_return_v5_local()` (in `backfill_signals.py`) — Simulates exit with take-profit/stop-loss for a given holding period. Returns dict with `return_pct`, `exit_reason`, `exit_date`, `hold_days_actual`. Imported by `auto_daily.py` for AI memory verification.
- `compute_performance()` — Computes aggregate performance from `ai_memory.json` precomputed returns (7d). Supports mode filter and lookback window. No longer calls yfinance live.
- `save_signals()` — Appends candidate signals to `signal_tracker.csv`.
- Dynamically imports `选股new_v5` as `screener` module via `_load_module()`.
- **Verdict matrix cards**: Memory records displayed as styled cards with color-coded verdict badges. 7-day structured review fields expandable in detail view.
- **AI memory delete**: Individual records can be deleted from the UI with confirmation.

### Stock name lookup: `name_lookup.py` (140 lines)

Three-tier lookup: `stock_names_cn.csv` (Chinese names) → `name_cache.csv` (yfinance cache) → live yfinance query. Includes English→Chinese sector translation dictionary.

### Data fix utility: `fix_review_data.py` (169 lines)

Deduplicates `ai_memory.json` records and recomputes `return_7d` using mode-specific take-profit/stop-loss/hold-days parameters (each SCREEN_MODE has different exit rules). Run with `--dry-run` to preview changes.

### Tri-mode design (v7, deployed 2026-06-15)

All three modes now require **≥3 consecutive limit-ups** (v7 change — was ≥2 for bear/loose in v6).

| Mode | Optimized On | Key Innovation | Use Case |
|------|-------------|----------------|----------|
| BEAR | Period A (2023-2024, 熊市震荡) | 浅回调(1-11%) + 极度缩量(55%) + 超快持有(3d) + 高止盈(9.6%) | 熊市/冰点/低迷 — forced by regime detection |
| STRICT | Period C (2025.07-2026.04, 震荡回调) | 中等回调上限(27%) + 严格缩量(36%) + 阳线信号 + 12d持有 | 震荡市/启动期 — high quality, lower frequency |
| LOOSE | Period B (2024.07-2025.06, 牛市大涨) | 极紧回调上限(9%) + 宽止损(-17.3%) + 紧止盈(4.2%) + 12d持有 | 牛市/发酵/高潮 — 🏆 most generalizable |

**v7 fixes (June 15 re-optimization)**: Fixed three backtest engine bugs that inflated pre-v7 results:
1. `for-else` clause misindentation causing stop-loss bypass on certain paths
2. Sharpe ratio inflated by using raw returns instead of excess returns (vs risk-free rate)
3. Stop-loss not triggering on the same day as entry

After fixes, the three modes were re-optimized on their respective market periods (A/B/C). All modes converged to ≥3 limit-ups as optimal. The v6 BULL mode was removed earlier (2026-06-14) due to severe overfitting (IS Sharpe 19.56 → OOS 1.22).

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

**核心教训**: 三阶段漏斗优化（~200k组合）在单一周期上能找到极高分，但泛化能力差。LOOSE 用最简单的参数（最少优化）换来了最好的泛化。**过多的参数优化自由度 = 过拟合风险。** Note: these v6 IS/OOS numbers predate the v7 backtest bug fixes and may be inflated.

### Key design decisions

- **No database** — All data is CSV/JSON files on disk. Stock price cache in `stock_data/`, results in CSV/JSON.
- **yfinance as sole price data source** — A-share codes use `.SS` (Shanghai) and `.SZ` (Shenzhen) suffixes. AKShare is used only for market news (东方财富 source), not for price data.
- **Pre-extraction pattern for optimization** — `extract_all_events()` scans all stocks once to find limit-up series, then `evaluate_params_on_events()` replays different parameter sets against these events. This avoids re-downloading data for each parameter combination.
- **`require_oversold` and `require_low_close` are permanently False** — Both filters were eliminated during grid search (Simpson's paradox: they looked good in isolation but degraded multi-factor performance). The parameters remain in the dict for future experimentation but are never activated in production modes. See [docs/TASK1_算法改进.md](docs/TASK1_算法改进.md) — verify with full backtest before reactivating.
- **Automated git-push pipeline** — `auto_daily.py` commits and pushes `latest_scan_results.json` + `results_archive/` to GitHub, which triggers Streamlit Cloud to redeploy with fresh results. Decouples data freshness from app load time.
- **AI memory closed loop** — Every AI analysis is archived → auto-verified against actual returns after 7+ days → 7-day post-mortem review performed → injected as context for future analyses of the same stock. Self-improving feedback loop with structured lessons learned.
- **AI analysis runs in auto_daily.py, NOT Streamlit** — All AI analysis is precomputed by `auto_daily.py` and stored in `ai_memory.json`. Streamlit reads cached results directly. This avoids API costs on every page load, eliminates timeout issues, and decouples computation from rendering.
- **Market news decoupled from screening** — News is fetched and analyzed separately (`market_news.py` or `auto_daily.py`) and stored in `market_news.json`. Streamlit reads cached results. News sentiment is injected into screening AI prompts.
- **Syntax check hook** — `.claude/settings.json` has a PostToolUse hook that runs `py_compile` on `.py` files after every Edit/Write. No need to manually syntax-check — the hook catches errors immediately.
- **v7 all modes require ≥3 limit-ups** — The June 15 re-optimization (after fixing three backtest bugs) found that 3-limit-up stocks outperform 2-limit-up across all market regimes.

### Known Issues (2026-06-23)

**P0 — `signal_date` bug in return calculations**: `fix_review_data.py` passes `signal_date=r.get('signal_date', r['date'])` to `check_return_v5_local()`, but `ai_memory.json` records use `date` not `signal_date`. This causes some records to get wrong `return_7d` values (e.g. 001299.SZ shows -12.49% instead of ~+5.4%). Fix: always use `r['date']`. See [docs/superpowers/plans/2026-06-23-five-bug-fixes.md](docs/superpowers/plans/2026-06-23-five-bug-fixes.md) for the full fix plan.

**P1 — `permutation_test()` is ineffective**: Only shuffles return sequences without changing mean/variance, producing p-values ~0.9-1.0 regardless of actual significance. Needs rewrite to random entry dates or bootstrap distribution comparison.

**P1 — `market_news.py` not yet integrated into `auto_daily.py`**: News must be run separately. The five-bug-fixes plan adds it to the auto pipeline.

**P2 — Streamlit lacks data staleness banners**: The UI shows cached data without warning when it's >24h old.

See the full five-bug-fixes plan for detailed steps and verification commands.

### Data files

- `stock_data/*.csv` — per-stock OHLCV cache (gitignored, too large)
- `stock_snapshot.csv.gz` — gzip snapshot of ~5200 stocks 30d history for cloud deployment
- `active_codes.txt` — filtered list of actively traded codes
- `latest_scan_results.json` — most recent daily scan output (produced by `auto_daily.py`, consumed by `streamlit_app.py`)
- `results_archive/{YYYYMMDD}.json` — daily archived scan results
- `signal_tracker.csv` — historical signal log (date, code, mode, entry_price, pullback_pct, limit_days)
- `ai_memory.json` — AI analysis memory store: per-stock records with sentiment, position, opinion, verified returns, verdict, 7-day structured review
- `market_news.json` — latest AI-curated market news (produced by `market_news.py` or `auto_daily.py`)
- `news_archive/YYYYMMDD.json` — historical news archives
- `stock_names_cn.csv` / `name_cache.csv` — stock name lookup tables
- `backtest_results/` — backtest signal CSVs and equity curves per version/period
- `v5_results/` — optimization stage outputs, bootstrap CIs, sensitivity analysis, cross-period validation, regime adaptation report
- `auto_logs/` — daily automated scan output text files
- `requirements.txt` — minimal deps (streamlit, yfinance, pandas, numpy, requests, akshare)
- `docs/TASK1_算法改进.md` — pending algorithm improvement task based on HuaAn research. ⚠️ References `选股new.py` (legacy name) — apply to `选股new_v5.py`. Simpson's paradox warning included.
- `docs/回测数据总览.md` — Historical backtest results overview and key findings
- `DESIGN.md` — NEON VAULT v3 design system spec: color palette, typography (Orbitron + JetBrains Mono), component styles, layout principles, animation rules, dos/don'ts. Authoritative reference for all UI changes.
- `docs/superpowers/specs/` — 12 design specs
- `docs/superpowers/plans/` — 8 implementation plans
- `archive/` — older versions (`选股new_v3.py`, `选股new_v4.py`, etc.) and historical data (not used in current workflow)
- `.gitignore` — Excludes `stock_data/`, `candidates_*.csv`, `.agents/`, `.playwright-mcp/`, `.env`
- `skills-lock.json` — Tracks installed skill sources and content hashes for reproducibility

### Project-level skills

11 project skills installed across two locations (see `skills-lock.json` for version hashes):

**`.agents/skills/` (10 skills):**
- `developing-with-streamlit` — Streamlit-specific development guidance
- `schedule-it` — Scheduling/task automation patterns
- `ckm-banner-design`, `ckm-brand`, `ckm-design`, `ckm-design-system`, `ckm-slides`, `ckm-ui-styling` — Design system / branding skills
- `make-interfaces-feel-better`, `ui-ux-pro-max` — UI/UX improvement skills

**`.claude/skills/` (1 skill):**
- `web-design` — Web design skill (full cloned repo)
