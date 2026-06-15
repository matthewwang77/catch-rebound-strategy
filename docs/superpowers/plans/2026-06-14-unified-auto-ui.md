# Unified Auto-Mode UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 3-tab mode-switching UI with a single auto-detected mode view. All candidates auto-queue for AI analysis. Review page unified to single performance panel. Enhanced Tactical Terminal CSS.

**Architecture:** The screening page now reads `recommended_mode` from `latest_scan_results.json`, displays only those candidates in a single list, and auto-queues all for AI analysis. The review page merges mode-specific panels into one aggregated view. `auto_daily.py` runs only the auto-detected mode. CSS receives neon terminal enhancements.

**Tech Stack:** Streamlit, Python, CSS injection via `st.markdown(unsafe_allow_html=True)`

---

### Task 1: Simplify auto_daily.py to auto-mode only

**Files:**
- Modify: `auto_daily.py:16,60-172,176-220,224-298`

- [ ] **Step 1: Change MODES to only run auto-recommended mode**

Edit `auto_daily.py:16`:
```python
# 选股模式（v6: auto-detected single mode, 2026-06-14 unified UI）
MODES = ["auto"]  # detect_market_regime() picks the right mode
```

- [ ] **Step 2: Rewrite run_all_modes() to run only the recommended mode**

Replace `auto_daily.py:60-172` (entire `run_all_modes()` function):
```python
def run_all_modes():
    """v6 unified: 检测市场状态，只跑推荐模式。返回 dict。"""
    # 检测市场状态
    regime_info = None
    recommended_mode = "strict"  # fallback
    try:
        regime_info = screener.detect_market_regime()
        recommended_mode = regime_info['recommended_mode']
        print(f"市场状态: {regime_info['sentiment_label']} | "
              f"5日趋势: {regime_info['avg_trend']:+.1f}% | "
              f"推荐模式: {recommended_mode}")
        if regime_info['regime'] == 'bear':
            print("⚠️ 熊市环境 — 启用浅回调+极度缩量策略")
    except Exception as e:
        print(f"⚠️ 市场检测失败: {e}，使用 STRICT 模式")

    DATA_DIR = screener.DATA_DIR
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    codes = [f.replace('.csv', '') for f in cache_files]
    print(f"待扫描: {len(codes)} 只")

    # 从 CSV 加载数据
    all_data = {}
    today_str = datetime.now().strftime('%Y-%m-%d')
    for code in codes:
        csv_path = os.path.join(DATA_DIR, f"{code}.csv")
        if not os.path.exists(csv_path):
            continue
        try:
            df = pd.read_csv(csv_path)
            if len(df) == 0:
                continue
            df = df.tail(60).copy()
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            stock_df = pd.DataFrame({
                'Close': df['close'].values, 'Open': df['open'].values,
                'High': df['high'].values, 'Low': df['low'].values,
                'Volume': df['volume'].values,
            }, index=df.index).dropna()
            if len(stock_df) >= 10:
                all_data[code] = stock_df
        except Exception as e:
            print(f"  ⚠️ {code} 加载失败: {e}")
    print(f"缓存加载: {len(all_data)} 只")

    # 今日注入（轻量）
    print("注入今日数据...")
    BATCH_SIZE = 200
    batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
    injected = 0
    for i, batch in enumerate(batches):
        try:
            hist = yf.download(tickers=batch, period="3d", progress=False)
            if hist is None or hist.empty:
                continue
            try:
                codes_in_batch = set(hist.columns.get_level_values(1))
            except Exception:
                continue
            for code in batch:
                if code not in codes_in_batch:
                    continue
                try:
                    recent = hist.xs(code, level=1, axis=1)
                    recent = recent[recent['Close'].notna() & (recent['Close'] > 0)]
                    if len(recent) == 0:
                        continue
                    if code in all_data:
                        new_rows = recent[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                        all_data[code] = pd.concat([all_data[code], new_rows]).tail(60)
                    else:
                        all_data[code] = recent[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                    injected += 1
                except Exception as e:
                    print(f"  ⚠️ {code} 今日注入失败: {e}")
        except Exception as e:
            print(f"  ⚠️ 批次 {i+1}/{len(batches)} 下载失败: {e}")
    print(f"今日注入: {injected} 只")

    # 只跑推荐模式
    results = {}
    original = screener.PARAMS.copy()
    screener.PARAMS.update(screener.SCREEN_MODES[recommended_mode])

    candidates = []
    stats = {
        'total': len(all_data), 'has_data': 0, 'has_limit_up': 0,
        'consecutive_ok': 0, 'entity_ratio_ok': 0, 'pullback_days_ok': 0,
        'pullback_range_ok': 0, 'ma_ok': 0, 'volume_shrink_ok': 0,
        'yang_ok': 0, 'volume_expand_ok': 0, 'final': 0,
    }
    for code, stock_data in all_data.items():
        try:
            screener._screen_single_stock(code, stock_data, stats, candidates, recommended_mode)
        except Exception as e:
            print(f"  ⚠️ {code} 筛选失败: {e}")

    screener.PARAMS.update(original)
    results[recommended_mode] = candidates
    print(f"{recommended_mode}: {len(candidates)} 只候选")

    return results
```

- [ ] **Step 3: Update format_message() to remove mode-specific naming**

Replace `auto_daily.py:191`:
```python
    mode_names = {"strict": "◆ 严格", "loose": "◆ 宽松", "bear": "◆ 熊市"}
```

And update the loop at line 202 to iterate `results` directly (single mode).

- [ ] **Step 4: Update save_results_json() to handle single mode**

The function already iterates `results.items()` — no change needed structurally. But update the `modes` section comment at line 268 to note single-mode.

- [ ] **Step 5: Verify syntax and test run**

```bash
python3 -c "import py_compile; py_compile.compile('auto_daily.py', doraise=True); print('✅ syntax OK')"
```

- [ ] **Step 6: Commit**

```bash
git add auto_daily.py
git commit -m "refactor: auto_daily simplified to auto-detected single mode"
```

---

### Task 2: Rewrite screening page in streamlit_app.py

**Files:**
- Modify: `streamlit_app.py:2332-2492` (entire `if page == '◆ 选股':` block)

- [ ] **Step 1: Replace the entire screening page block (lines 2332-2492)**

Replace everything from `if page == '◆ 选股':` to the `elif page == '◆ 复盘':` with:

```python
    # ============ 选股页面 (v6 Unified Auto) ============
    if page == '◆ 选股':
        # 加载预计算选股结果
        if "cached_scan_data" not in st.session_state:
            st.session_state["cached_scan_data"] = load_latest_results()
        scan_data = st.session_state["cached_scan_data"]
        fresh = load_latest_results()
        if fresh and fresh.get("scan_time") != scan_data.get("scan_time") if scan_data else True:
            st.session_state["cached_scan_data"] = fresh
            scan_data = fresh

        # 判断当前时段
        now = china_now()
        wd = now.weekday()
        h, m = now.hour, now.minute
        is_trading = (wd < 5 and ((9 <= h < 11) or (h == 11 and m <= 30) or (13 <= h < 15)))
        is_post_close = (wd < 5 and h >= 15)

        if scan_data is None:
            st.info("◆ 等待首次定时扫描… 结果将在 10:00 / 11:30 / 14:00 / 15:00 自动出现")
            st.caption("💡 也可以手动运行: `python auto_daily.py`")
        else:
            # ── 市场状态卡片 ──
            regime = scan_data.get("regime", {})
            market = scan_data.get("market", {})
            rec_mode = regime.get("recommended_mode", "strict")
            modes = scan_data.get("modes", {})

            # Build compact market status line
            index_parts = []
            for name, data in market.items():
                pct = data.get("pct", 0)
                color = "#00ff88" if pct >= 0 else "#ff5050"
                sign = "+" if pct >= 0 else ""
                index_parts.append(
                    f'<span style="color:#aaa;font-size:0.5rem;">{name}</span> '
                    f'<span style="color:{color};font-size:0.55rem;">{data["price"]:.0f} {sign}{pct:.2f}%</span>'
                )

            sentiment_label = regime.get("label", "—")
            st.markdown(f"""
            <div class="market-status-card">
              <div class="market-index-row">
                {" · ".join(index_parts)}
              </div>
              <div class="market-sentiment">
                <span class="sentiment-tag">{sentiment_label}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ── 选股结果 ──
            candidates = modes.get(rec_mode, {}).get("candidates", [])
            st.markdown(f'<div class="section-label">◆ 选股结果 · {len(candidates)}只候选</div>',
                        unsafe_allow_html=True)

            if not candidates:
                st.info("◆ 当前无符合条件股票")
            else:
                # 首次加载：自动入队 AI 分析
                if "auto_queued" not in st.session_state:
                    codes = [c["code"] for c in candidates]
                    start_analysis_queue(codes)
                    st.session_state["auto_queued"] = True

                # 转移已完成的分析结果
                for code in list(st.session_state.analysis_results.keys()):
                    result = st.session_state.analysis_results[code]
                    if result:
                        st.session_state[f"analysis_result_{code}"] = result
                    del st.session_state.analysis_results[code]
                for code in list(st.session_state.analysis_errors.keys()):
                    st.session_state[f"analysis_result_{code}"] = f"❌ 分析失败: {st.session_state.analysis_errors[code]}"
                    del st.session_state.analysis_errors[code]

                # 名称查找
                codes = [c["code"] for c in candidates]
                name_info = name_lookup.batch_lookup(codes, max_fetch=5)

                for c in candidates:
                    code = c["code"]
                    info = name_info.get(code, {})
                    stock_name = info.get("name", "") or ""

                    # 分析状态
                    in_queue = code in st.session_state.analysis_queue
                    is_current = st.session_state.analysis_current == code
                    has_result = bool(st.session_state.get(f"analysis_result_{code}"))

                    if is_current:
                        status_html = '<span class="status-badge analyzing">🔄 分析中</span>'
                    elif in_queue:
                        status_html = '<span class="status-badge queued">⏳ 排队</span>'
                    elif has_result:
                        result_text = st.session_state.get(f"analysis_result_{code}", "")
                        # Quick parse for sentiment/position
                        import re
                        sent_match = re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', result_text)
                        pos_match = re.search(r'仓位[建议]*[：:]\s*(.+?)(?:\n|$)', result_text)
                        sentiment = sent_match.group(1).strip() if sent_match else "—"
                        position = pos_match.group(1).strip() if pos_match else "—"
                        status_html = f'<span class="status-badge done">🎯 {sentiment} · 💰 {position}</span>'
                    else:
                        status_html = '<span class="status-badge pending">⏳ 排队</span>'

                    with st.container():
                        col1, col2, col3, col4, col5, col6 = st.columns([1.6, 1.1, 1.0, 0.8, 0.8, 1.9])
                        with col1:
                            name_line = f"**`{code}`**"
                            if stock_name:
                                name_line += f"  {stock_name}"
                            st.markdown(name_line)
                        with col2:
                            st.metric("价格", f"{c['price']:.2f}")
                        with col3:
                            st.metric("回调", f"{c['pullback_pct']:.1f}%")
                        with col4:
                            st.metric("连板", f"{c['limit_days']}天")
                        with col5:
                            st.metric("实体板", f"{c.get('entity_ratio', 0):.0f}%")
                        with col6:
                            st.markdown(status_html, unsafe_allow_html=True)

                        # 展开完整 AI 分析
                        if has_result:
                            result_text = st.session_state[f"analysis_result_{code}"]
                            with st.expander(f"◆ {code} AI分析", expanded=False):
                                st.markdown(result_text)

                        st.divider()

            # ── AI 分析进度条 ──
            if st.session_state.analysis_running:
                queue_len = len(st.session_state.analysis_queue)
                total = len(candidates) if candidates else 1
                done = total - queue_len
                pct = done / total if total > 0 else 0
                current = st.session_state.analysis_current or "—"
                est_min = max(0, int(queue_len * 0.25))  # ~15s per analysis
                st.markdown(f"""
                <div class="analysis-progress-bar">
                  <div class="progress-header">
                    <span>🤖 AI分析进度</span>
                    <span>{done} / {total}</span>
                  </div>
                  <div class="progress-track">
                    <div class="progress-fill" style="width:{pct*100:.0f}%"></div>
                  </div>
                  <div class="progress-footer">当前: {current} · 预计剩余 {est_min}分钟</div>
                </div>
                """, unsafe_allow_html=True)

            # ── CSV 导出 ──
            if candidates:
                st.divider()
                df_export = pd.DataFrame(candidates)
                st.download_button(
                    label="◆ 导出 CSV",
                    data=df_export.to_csv(index=False, encoding="utf-8-sig"),
                    file_name=f"candidates_{china_now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
                current_scan_time = scan_data.get("scan_time", "")
                if st.session_state.get("_saved_scan_time") != current_scan_time:
                    save_signals(candidates)
                    st.session_state["_saved_scan_time"] = current_scan_time

    # ============ 复盘页面 ============
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True); print('✅ syntax OK')"
```

- [ ] **Step 3: Commit**

```bash
git add streamlit_app.py
git commit -m "feat: unified single-view screening page with auto AI analysis queue"
```

---

### Task 3: Unify review page to single performance panel

**Files:**
- Modify: `streamlit_app.py:2499-2561` (performance overview section)

- [ ] **Step 1: Replace the dual-mode performance section**

Replace lines 2499-2561 (from `# === 绩效总览 ===` to the `st.divider()` before AI memory browser):

```python
        # === 绩效总览 (v6 Unified) ===
        perf = compute_performance(mode_filter=None, days_window=30)

        if perf:
            ret_color = "#00FF88" if perf['total_return'] >= 0 else "#FF5050"
            pf_display = "无损" if perf['profit_factor'] >= 999 else f"{perf['profit_factor']:.2f}"
            st.markdown(f"""
            <div class="perf-panel">
              <div class="section-label">◆ 绩效总览 (近30天)</div>
              <div class="perf-grid">
                <div class="perf-card">
                  <div class="perf-label">累计收益</div>
                  <div class="perf-value" style="color:{ret_color}">{perf['total_return']:+.1f}%</div>
                </div>
                <div class="perf-card">
                  <div class="perf-label">胜率</div>
                  <div class="perf-value" style="color:#D0D0E8">{perf['win_rate']:.0%}</div>
                </div>
                <div class="perf-card">
                  <div class="perf-label">盈亏比</div>
                  <div class="perf-value" style="color:#FFD700">{pf_display}</div>
                </div>
                <div class="perf-card">
                  <div class="perf-label">最大回撤</div>
                  <div class="perf-value" style="color:#FF6B6B">-{perf['max_drawdown']:.1f}%</div>
                </div>
              </div>
              <div class="perf-detail">
                {perf['wins']}胜/{perf['losses']}负 · 均盈+{perf['avg_win']:.1f}% · 均亏-{perf['avg_loss']:.1f}% · 共{perf['total_trades']}笔
              </div>
            </div>
            """, unsafe_allow_html=True)

            # 收益曲线
            if perf['cum_returns'] and len(perf['cum_returns']) >= 3:
                chart_df = perf.get('chart_df',
                    pd.DataFrame({'累计收益%': perf['cum_returns']})
                )
                st.line_chart(chart_df, height=140, use_container_width=True)
                exit_info = perf.get('exit_reasons', {})
                if exit_info:
                    parts = [f"{k}{v}次" for k, v in sorted(exit_info.items())]
                    st.caption(f"持有{perf.get('hold_days','?')}天 · {' · '.join(parts)}")
            else:
                st.caption(f"数据不足（{len(perf.get('cum_returns',[]))}笔），继续积累")
        else:
            st.markdown("""
            <div class="perf-panel" style="text-align:center;opacity:0.5">
              <div class="section-label">◆ 绩效总览</div>
              <p style="color:#333355;font-size:0.55rem;">暂无信号数据，信号需要持有期+4天后验证</p>
            </div>
            """, unsafe_allow_html=True)

        st.divider()
```

- [ ] **Step 2: Update AI memory browser re-analyze button**

The re-analyze button in the memory browser calls `start_analysis_queue([code])` — this is already compatible. No changes needed.

- [ ] **Step 3: Verify syntax**

```bash
python3 -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True); print('✅ syntax OK')"
```

- [ ] **Step 4: Commit**

```bash
git add streamlit_app.py
git commit -m "feat: unified review page with single performance panel"
```

---

### Task 4: Update intro page text

**Files:**
- Modify: `streamlit_app.py:2687+` (intro page section)

- [ ] **Step 1: Update intro page content**

Find the intro page section (`elif page == '◆ 介绍':`) and update the strategy description to reflect v6 unified auto mode. Key text changes:
- Mention "市场自适应 — 自动检测熊市/震荡/牛市，切换最优参数"
- Mention "全自动 AI 分析 — 所有候选自动深度分析，无需手动触发"
- Mention "AI 记忆闭环 — 历史分析存档 + 自动验证 + 上下文注入"
- Remove references to "strict/loose 两种模式"

```python
    elif page == '◆ 介绍':
        st.header("◆ NEON VAULT · 战术终端")
        st.markdown("""
        <div class="intro-section">
          <h3>A股连板回调策略 v6</h3>
          <p>识别连续涨停后缩量回调的股票，在回调企稳时介入，博取反弹收益。</p>
          <p>基于「量价形时」四维分析框架，由 DeepSeek 提供深度 AI 诊断。</p>

          <h4>◆ 核心特色</h4>
          <ul>
            <li><strong>市场自适应</strong> — 三大指数5日趋势自动检测，熊市/震荡/牛市切换最优参数</li>
            <li><strong>全自动 AI 分析</strong> — 所有候选股票自动深度诊断，无需手动触发</li>
            <li><strong>AI 记忆闭环</strong> — 每笔分析存档，3天后自动验证收益，历史上下文注入未来分析</li>
            <li><strong>三阶段参数优化</strong> — ~200k组合 × 多周期交叉验证 × Bootstrap统计检验</li>
            <li><strong>全自动日频扫描</strong> — 每交易日4次定时扫描 + git自动推送</li>
          </ul>

          <h4>◆ 数据来源</h4>
          <p>yfinance (Yahoo Finance) · ~5,200只A股 · 本地CSV缓存</p>

          <h4>◆ 扫描时间</h4>
          <p>每个交易日 10:00 / 11:30 / 14:00 / 15:00</p>
        </div>
        """, unsafe_allow_html=True)
```

- [ ] **Step 2: Verify syntax and commit**

```bash
python3 -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True); print('✅ syntax OK')"
git add streamlit_app.py
git commit -m "docs: update intro page for v6 unified auto mode"
```

---

### Task 5: Enhance CSS with Tactical Terminal aesthetic

**Files:**
- Modify: `streamlit_app.py:30-600` (inject_design_system function, CSS portion)

- [ ] **Step 1: Add new CSS classes for the unified UI**

Add the following CSS blocks inside `inject_design_system()`'s `<style>` tag, after the existing styles:

```css
/* === TACTICAL TERMINAL ENHANCEMENTS === */

/* Market Status Card */
.market-status-card {
  background: linear-gradient(135deg, rgba(0,255,136,0.03) 0%, rgba(0,15,10,0.6) 100%);
  border: 1px solid rgba(0,255,136,0.1);
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.market-index-row {
  font-family: 'JetBrains Mono', monospace;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.market-sentiment {
  flex-shrink: 0;
}
.sentiment-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.5rem;
  color: #00ff88;
  background: rgba(0,255,136,0.06);
  border: 1px solid rgba(0,255,136,0.2);
  border-radius: 3px;
  padding: 3px 10px;
}

/* Section Label */
.section-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.65rem;
  color: #00ff88;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(0,255,136,0.08);
}

/* Status Badges */
.status-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.45rem;
  padding: 2px 8px;
  border-radius: 3px;
  white-space: nowrap;
}
.status-badge.analyzing {
  color: #00e5ff;
  background: rgba(0,229,255,0.06);
  border: 1px solid rgba(0,229,255,0.2);
  animation: pulse-glow 1.5s ease-in-out infinite;
}
.status-badge.queued {
  color: #666;
  background: rgba(100,100,100,0.05);
  border: 1px solid rgba(100,100,100,0.15);
}
.status-badge.done {
  color: #ffd700;
  background: rgba(255,215,0,0.05);
  border: 1px solid rgba(255,215,0,0.2);
}
.status-badge.pending {
  color: #888;
  background: transparent;
  border: 1px dashed rgba(100,100,100,0.2);
}

/* Analysis Progress Bar */
.analysis-progress-bar {
  background: rgba(0,255,136,0.02);
  border: 1px solid rgba(0,255,136,0.08);
  border-radius: 6px;
  padding: 12px 16px;
  margin: 10px 0 16px 0;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.5rem;
  color: #00ff88;
  margin-bottom: 6px;
}
.progress-track {
  height: 3px;
  background: rgba(0,255,136,0.06);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #00ff88, #00e5ff);
  border-radius: 2px;
  transition: width 0.5s ease;
  animation: pulse-glow 2s ease-in-out infinite;
}
.progress-footer {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.42rem;
  color: #555;
  margin-top: 4px;
}

/* Performance Panel */
.perf-panel {
  background: rgba(0,15,10,0.4);
  border: 1px solid rgba(0,255,136,0.06);
  border-radius: 6px;
  padding: 14px 18px;
  margin-bottom: 12px;
}
.perf-grid {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  margin: 10px 0;
}
.perf-card {
  min-width: 80px;
}
.perf-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.42rem;
  color: #555;
  margin-bottom: 2px;
}
.perf-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.1rem;
  font-weight: bold;
}
.perf-detail {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.42rem;
  color: #444;
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px solid rgba(0,255,136,0.04);
}

/* Intro Section */
.intro-section {
  font-family: 'JetBrains Mono', monospace;
  color: #aaa;
  font-size: 0.55rem;
  line-height: 1.7;
}
.intro-section h3 {
  color: #00ff88;
  font-family: 'Orbitron', sans-serif;
  font-size: 0.9rem;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.intro-section h4 {
  color: #00e5ff;
  font-size: 0.6rem;
  letter-spacing: 0.04em;
  margin-top: 16px;
  margin-bottom: 6px;
}
.intro-section ul {
  list-style: none;
  padding-left: 0;
}
.intro-section li {
  padding: 3px 0;
}
.intro-section li::before {
  content: "◆ ";
  color: #00ff88;
}

/* Animations */
@keyframes pulse-glow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* Noise overlay (subtle texture on dark bg) */
.stApp::before {
  content: "";
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.015'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 9999;
}

/* Tactical divider */
.tactical-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,255,136,0.1), transparent);
  margin: 8px 0;
}
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import py_compile; py_compile.compile('streamlit_app.py', doraise=True); print('✅ syntax OK')"
```

- [ ] **Step 3: Commit**

```bash
git add streamlit_app.py
git commit -m "style: Tactical Terminal neon aesthetic enhancements"
```

---

### Task 6: End-to-end verification

- [ ] **Step 1: Run streamlit syntax check on all modified files**

```bash
python3 -c "
import py_compile
for f in ['streamlit_app.py', 'auto_daily.py']:
    py_compile.compile(f, doraise=True)
    print(f'✅ {f} syntax OK')
"
```

- [ ] **Step 2: Quick module import test (no UI rendering)**

```bash
python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('screener', '选股new_v5.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('✅ 选股new_v5.py import OK')
print(f'Modes: {list(mod.SCREEN_MODES.keys())}')
print(f'Regime detection test...')
try:
    r = mod.detect_market_regime()
    print(f'  regime={r[\"regime\"]} tier={r[\"sentiment_tier\"]} mode={r[\"recommended_mode\"]}')
except Exception as e:
    print(f'  regime detection failed (expected offline): {e}')
"
```

- [ ] **Step 3: Verify auto_daily module loads**

```bash
python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('auto', 'auto_daily.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('✅ auto_daily.py import OK')
print(f'MODES: {mod.MODES}')
"
```

- [ ] **Step 4: Verify signal_tracker and ai_memory compatibility**

```bash
python3 -c "
import csv, json, os
# signal_tracker still has mode column — unchanged
if os.path.exists('signal_tracker.csv'):
    with open('signal_tracker.csv') as f:
        reader = csv.DictReader(f)
        modes_seen = set()
        for row in reader:
            modes_seen.add(row.get('mode', ''))
    print(f'✅ signal_tracker.csv OK — modes: {modes_seen}')
else:
    print('⚠️ signal_tracker.csv does not exist (new install?)')

# ai_memory.json still valid
if os.path.exists('ai_memory.json'):
    with open('ai_memory.json') as f:
        mem = json.load(f)
    print(f'✅ ai_memory.json OK — {len(mem)} stocks tracked')
"
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: end-to-end verification of unified auto-mode UI"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ Single-view screening page: Task 2
- ✅ Auto AI analysis queue: Task 2
- ✅ No mode name in header: Task 2 (uses `section-label` with count only)
- ✅ Unified review panel: Task 3
- ✅ Intro page update: Task 4
- ✅ auto_daily.py simplified: Task 1
- ✅ Tactical Terminal CSS: Task 5

**2. Placeholder scan:** Zero TBD/TODO/fill-in-later detected.

**3. Type consistency:** `start_analysis_queue()` signature unchanged. `compute_performance()` already accepts `mode_filter=None`. `load_latest_results()` return format unchanged. All interfaces compatible.
