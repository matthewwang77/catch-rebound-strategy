# NEON VAULT 选股页面 UI 美化 + Bug 修复 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对 `streamlit_app.py` 进行 6 项改动——4 项 UI 美化 + 2 项 Bug 修复——使 NEON VAULT 选股页面更美观、更可靠。

**Architecture:** 所有改动集中在 `streamlit_app.py`。不改 `选股new_v5.py`。CSS 在 `inject_design_system()` 中新增；页面结构在 `main()` 中调整；AI 分析流程重构为统一入口。

**Tech Stack:** Python 3, Streamlit, CSS (via st.markdown unsafe_allow_html), session_state

---

### Task 1: CSS — 新增所有新组件的样式规则

**Files:**
- Modify: `streamlit_app.py:29-437` (`inject_design_system()`)

在 `inject_design_system()` 的 `</style>` 结束标签之前（约 430 行）插入以下 CSS：

- [ ] **Step 1: 添加导航卡片 CSS**

```css
/* === NAV CARDS (sidebar) === */
.nav-card-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.nav-card {
  flex: 1;
  padding: 14px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: rgba(10,11,20,0.8);
  text-align: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
  color: #6666AA;
  cursor: pointer;
  transition: all 0.25s ease;
  user-select: none;
}
.nav-card:hover {
  background: rgba(0,240,255,0.04);
  border-color: rgba(0,240,255,0.25);
  color: #00F0FF;
  transform: translateY(-1px);
}
.nav-card.active {
  background: rgba(0,240,255,0.08);
  border-color: rgba(0,240,255,0.55);
  color: #00F0FF;
  box-shadow: 0 0 14px rgba(0,240,255,0.1), inset 0 0 12px rgba(0,240,255,0.03);
  transform: scale(1.02);
}
.nav-card .card-icon {
  font-size: 1.1rem;
  display: block;
  margin-bottom: 4px;
}
.nav-card .card-label {
  font-size: 0.6rem;
  letter-spacing: 0.06em;
  opacity: 0.7;
}
```

- [ ] **Step 2: 添加模式胶囊 CSS**

```css
/* === MODE PILLS === */
.mode-pills-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 8px 0 12px 0;
}
.mode-pills-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  color: #5555AA;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.mode-pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  padding: 4px 12px;
  border-radius: 14px;
  cursor: help;
  transition: all 0.2s;
}
.mode-pill.strict {
  background: rgba(255,51,102,0.08);
  border: 1px solid rgba(255,51,102,0.22);
  color: #FF3366;
}
.mode-pill.strict:hover {
  background: rgba(255,51,102,0.14);
  border-color: rgba(255,51,102,0.4);
  box-shadow: 0 0 8px rgba(255,51,102,0.1);
}
.mode-pill.loose {
  background: rgba(0,255,136,0.06);
  border: 1px solid rgba(0,255,136,0.18);
  color: #00FF88;
}
.mode-pill.loose:hover {
  background: rgba(0,255,136,0.12);
  border-color: rgba(0,255,136,0.35);
  box-shadow: 0 0 8px rgba(0,255,136,0.08);
}
```

- [ ] **Step 3: 添加状态栏 CSS**

```css
/* === NEON STATUS BAR === */
.neon-status-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 18px;
  border-radius: 8px;
  font-family: 'JetBrains Mono', monospace;
  margin: 10px 0 14px 0;
}
.neon-status-bar.closed {
  background: rgba(0,240,255,0.025);
  border: 1px solid rgba(0,240,255,0.2);
}
.neon-status-bar.trading {
  background: rgba(255,184,0,0.025);
  border: 1px solid rgba(255,184,0,0.22);
}
.neon-status-bar .status-icon { font-size: 1rem; }
.neon-status-bar .status-text { font-size: 0.7rem; }
.neon-status-bar.closed .status-text { color: #00F0FF; }
.neon-status-bar.trading .status-text { color: #FFB800; }
.neon-status-bar .status-spacer { flex: 1; }
.neon-status-bar .status-label { font-size: 0.55rem; color: #6666AA; }
.neon-status-bar .status-time { font-size: 0.65rem; color: #9999CC; }
.pulse-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.pulse-dot.cyan {
  background: #00F0FF;
  box-shadow: 0 0 6px #00F0FF;
}
.pulse-dot.amber {
  background: #FFB800;
  box-shadow: 0 0 6px #FFB800;
}
@keyframes pulse-dot-anim {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
```

- [ ] **Step 4: 添加 AI 摘要条 + 展开器 CSS**

```css
/* === AI ANALYSIS EXPANDER === */
.ai-summary-strip {
  display: flex;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(0,240,255,0.06);
  flex-wrap: wrap;
}
.ai-summary-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  padding: 5px 10px;
  border-radius: 6px;
  white-space: nowrap;
}
.ai-summary-badge.sentiment { background: rgba(0,240,255,0.08); color: #00F0FF; }
.ai-summary-badge.position { background: rgba(0,255,136,0.08); color: #00FF88; }
.ai-summary-badge.opinion  { background: rgba(123,47,255,0.08); color: #7B2FFF; }
```

- [ ] **Step 5: 验证 CSS** — 运行 `streamlit run streamlit_app.py`，F12 检查 CSS 是否加载

---

### Task 2: 侧边栏导航 — radio → 大卡片按钮

**Files:**
- Modify: `streamlit_app.py:1806-1809` (替换 radio)

- [ ] **Step 1: 替换侧边栏导航代码**

将 lines 1806-1809：
```python
        st.radio("◆ 导航", ["◆ 选股", "◆ 复盘"], key="nav_page",
                 help="切换选股和复盘界面")
```

替换为：
```python
        # 导航卡片（大卡片式切换）
        current_page = st.session_state.get("nav_page", "◆ 选股")
        col_a, col_b = st.columns(2)
        with col_a:
            active_a = "active" if current_page == "◆ 选股" else ""
            if st.button(
                "📊\n选股",
                key="nav_stock",
                use_container_width=True,
                type="primary" if current_page == "◆ 选股" else "secondary",
            ):
                st.session_state["nav_page"] = "◆ 选股"
                st.rerun()
        with col_b:
            active_b = "active" if current_page == "◆ 复盘" else ""
            if st.button(
                "📋\n复盘",
                key="nav_review",
                use_container_width=True,
                type="primary" if current_page == "◆ 复盘" else "secondary",
            ):
                st.session_state["nav_page"] = "◆ 复盘"
                st.rerun()
```

- [ ] **Step 2: 验证** — 启动 app，确认点击两个按钮能正常切换页面，按钮高亮正确

---

### Task 3: 模式展示 — 从侧边栏移到选股页面为胶囊标签

**Files:**
- Modify: `streamlit_app.py:1811-1813` (删除侧边栏模式描述)
- Modify: `streamlit_app.py:1907` (在选股页插入胶囊标签)

- [ ] **Step 1: 删除侧边栏"两种模式"文字**

将 lines 1811-1813：
```python
        st.markdown("**◆ 两种模式（v5 优化参数）**")
        st.markdown("- **STRICT** 严格 — 需3连板，~5信号/月，胜率70%，Sharpe 1.71")
        st.markdown("- **LOOSE** 宽松 — 需2连板，~18信号/月，胜率61%，Sharpe 1.54（STRICT超集）")
```

替换为删除后的空行（只保留 `st.divider()`）。

- [ ] **Step 2: 在选股页面插入胶囊标签**

在 line 1906（`st.caption(...)` 之后，`# 两种模式 Tab 展示` 之前）插入：

```python
            # 筛选模式胶囊标签
            total_strict = modes.get('strict', {}).get('count', 0)
            total_loose = modes.get('loose', {}).get('count', 0)
            st.markdown(f"""
            <div class="mode-pills-row">
              <span class="mode-pills-label">筛选模式</span>
              <span class="mode-pill strict" title="3连板 | 胜率70% | Sharpe 1.71 → 震荡市首选">{'🔴'} STRICT · {total_strict}只</span>
              <span class="mode-pill loose" title="2连板 | 胜率60% | Sharpe 1.29 → 牛市/强趋势 · STRICT超集">{'🟢'} LOOSE · {total_loose}只</span>
            </div>
            """, unsafe_allow_html=True)
```

- [ ] **Step 3: 验证** — 确认侧边栏不再显示模式描述，选股页显示两个胶囊标签

---

### Task 4: 扫描状态栏 — 替换为 Neon 横幅

**Files:**
- Modify: `streamlit_app.py:1900-1905`

- [ ] **Step 1: 替换状态栏代码**

将 lines 1900-1905 (st.success/info/caption) 替换为：

```python
            # Neon 状态栏
            scan_time = scan_data.get("scan_time", "未知")
            if is_post_close:
                status_html = f"""
                <div class="neon-status-bar closed">
                  <span class="status-icon">✅</span>
                  <span class="status-text">今日最终结果（收盘后）</span>
                  <span class="status-spacer"></span>
                  <span class="status-label">扫描时间</span>
                  <span class="status-time">{scan_time}</span>
                  <span class="pulse-dot cyan"></span>
                </div>"""
            elif is_trading:
                status_html = f"""
                <div class="neon-status-bar trading">
                  <span class="status-icon">🔄</span>
                  <span class="status-text">盘中实时结果（每5分钟刷新）</span>
                  <span class="status-spacer"></span>
                  <span class="status-label">最近扫描</span>
                  <span class="status-time">{scan_time}</span>
                  <span class="pulse-dot amber"></span>
                </div>"""
            else:
                status_html = f"""
                <div class="neon-status-bar" style="border:1px solid rgba(100,100,140,0.1);background:rgba(100,100,140,0.01)">
                  <span class="status-icon" style="opacity:0.5">⏸</span>
                  <span class="status-text" style="color:#555577">市场已收盘</span>
                  <span class="status-spacer"></span>
                  <span class="status-label">最近扫描</span>
                  <span class="status-time" style="color:#555577">{scan_time}</span>
                </div>"""
            st.markdown(status_html, unsafe_allow_html=True)
```

- [ ] **Step 2: 验证** — 根据当前时段检查状态栏颜色（收盘 cyan / 盘中 amber / 闭市灰）

---

### Task 5: AI 分析流程重构 — 修复加载残留 + 股票消失 Bug

**Files:**
- Modify: `streamlit_app.py:1948-1986` (AI 分析处理逻辑)
- Modify: `streamlit_app.py:1882` (scan_data 缓存)

**策略**: 
- 在处理任何候选渲染之前集中处理 AI 请求
- 用 `st.empty()` placeholder 控制加载文字
- scan_data 缓存到 session_state

- [ ] **Step 1: 缓存 scan_data 到 session_state**

在 `if page == '◆ 选股'` 分支中，将：
```python
        scan_data = load_latest_results()
```

改为：
```python
        # 缓存 scan_data 到 session_state（切换tab不丢失）
        if "cached_scan_data" not in st.session_state:
            st.session_state["cached_scan_data"] = load_latest_results()
        scan_data = st.session_state["cached_scan_data"]
        # 每次也检查是否有新数据（定时扫描更新）
        fresh = load_latest_results()
        if fresh and fresh.get("scan_time") != scan_data.get("scan_time"):
            st.session_state["cached_scan_data"] = fresh
            scan_data = fresh
```

- [ ] **Step 2: 集中处理 AI 请求（在渲染列表之前）**

在状态栏之后、Tab 展示之前（约 line 1907 之后），插入统一 AI 分析处理入口：

```python
            # === 统一 AI 分析处理（在所有候选渲染之前）===
            ai_placeholder = st.empty()
            codes_to_analyze = [k.replace("analyze_", "") for k in st.session_state 
                               if k.startswith("analyze_") and st.session_state[k]]
            for code in codes_to_analyze:
                ai_placeholder.markdown(
                    f"<div style='padding:12px 16px;background:rgba(0,240,255,0.04);"
                    f"border:1px solid rgba(0,240,255,0.12);border-radius:8px;"
                    f"font-family:monospace;font-size:0.7rem;color:#00F0FF'>"
                    f"◆ 正在对 <b>{code}</b> 进行AI深度分析（约8-15秒）...</div>",
                    unsafe_allow_html=True
                )
                try:
                    stock_df = None
                    csv_path = os.path.join(screener.DATA_DIR, f"{code}.csv")
                    if os.path.exists(csv_path):
                        df = pd.read_csv(csv_path).tail(60)
                        stock_df = pd.DataFrame({
                            "Close": df["close"].values,
                            "Open": df["open"].values,
                            "High": df["high"].values,
                            "Low": df["low"].values,
                            "Volume": df["volume"].values,
                        }).dropna()
                    if stock_df is None or len(stock_df) < 10:
                        try:
                            ticker = yf.Ticker(code)
                            df_yf = ticker.history(period="3mo")
                            if df_yf is not None and len(df_yf) >= 10:
                                stock_df = df_yf[['Open','High','Low','Close','Volume']].dropna()
                        except Exception:
                            pass
                    market_ctx = screener.get_market_context()
                    analysis = fast_ai_analysis(code, stock_df, market_ctx)
                    if analysis:
                        st.session_state[f"analysis_result_{code}"] = analysis
                    st.session_state[f"analyze_{code}"] = False
                except Exception as e:
                    st.session_state[f"analyze_{code}"] = False
                ai_placeholder.empty()
                st.rerun()
```

- [ ] **Step 3: 删除候选循环内的旧 AI 分析代码**

删除 lines 1950-1982（每个候选内的 `if analyze_{code}: ... st.write(...) ... fast_ai_analysis(...)` 块），保留按钮：
```python
                            with col6:
                                btn_key = f"ai_{mode}_{code}"
                                if st.button(f"◆ AI分析", key=btn_key, use_container_width=True):
                                    st.session_state[f"analyze_{code}"] = True
```

- [ ] **Step 4: 增强 AI 结果显示（摘要条 + 复制）**

替换 lines 1984-1986 的简单 expander 为：

```python
                            if st.session_state.get(f"analysis_result_{code}"):
                                with st.expander(f"◆ {code} {stock_name} — AI分析报告", expanded=True):
                                    result_text = st.session_state[f"analysis_result_{code}"]
                                    # 提取摘要信息
                                    import re
                                    sentiment_match = re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', result_text)
                                    position_match = re.search(r'仓位[建议]*[：:]\s*(.+?)(?:\n|$)', result_text)
                                    sentiment = sentiment_match.group(1).strip() if sentiment_match else "—"
                                    position = position_match.group(1).strip() if position_match else "—"
                                    st.markdown(f"""
                                    <div class="ai-summary-strip">
                                      <span class="ai-summary-badge sentiment">🎯 情绪: {sentiment}</span>
                                      <span class="ai-summary-badge position">💰 仓位: {position}</span>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    st.markdown(result_text)
                                    # 复制：st.code 自带复制按钮
                                    with st.expander("📋 复制全文"):
                                        st.code(result_text, language=None)
```

`st.code(language=None)` 自带 Streamlit 原生复制按钮，无需额外实现。

- [ ] **Step 5: 验证** — 
  1. 点击 AI 分析 → 加载文字出现 → 分析完成后立即消失
  2. 分析期间切 选股→复盘→选股 → 列表还在
  3. 展开的 AI 结果显示摘要条 + 可复制 code block

---

### Task 6: 清理旧路径残留 + 端到端验证

**Files:**
- Modify: `streamlit_app.py` (检查是否有 `show_screening_results` 旧路径残留)

- [ ] **Step 1: 检查旧路径**

搜索 `show_screening_results` 是否在 main() 中被调用。如果 `load_latest_results()` 返回 None 时有 fallback 调用，确认该路径也使用相同的状态栏 + 模式 pills 样式。

- [ ] **Step 2: 端到端验证**

```bash
streamlit run streamlit_app.py
```

手动检查清单：
- [ ] 侧边栏：两张按钮卡片，选中态发光，点击切换正常
- [ ] 选股页：顶部有 STRICT/LOOSE 胶囊标签（hover 显示详情）
- [ ] 选股页：状态栏是 neon 风格（颜色随时段变化）
- [ ] AI 分析：点击 → 加载提示 → 完成 → 提示消失 → 结果显示摘要条
- [ ] AI 分析：可复制全文（st.code 带复制按钮）
- [ ] 切换 tab：分析期间切 选股→复盘→选股 → 列表不消失
- [ ] 整体：NEON VAULT 暗色主题一致

- [ ] **Step 3: git commit**

```bash
git add streamlit_app.py docs/superpowers/
git commit -m "feat: NEON VAULT UI polish — nav cards, mode pills, neon status bar, AI flow fix, summary strip"
```
