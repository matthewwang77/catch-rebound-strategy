# NEON VAULT 选股页面 UI 美化 + Bug 修复 · 设计文档

**日期**: 2026-06-13  
**状态**: 已确认  

## 概述

对 `streamlit_app.py` 中 NEON VAULT 仪表盘的选股页面进行 6 项改进：
4 项 UI 美化 + 2 项 Bug 修复。所有改动集中在 `streamlit_app.py`，不动 `选股new_v5.py`。

## 设计决策（经由 brainstorm 确认）

| # | 项 | 方案 | 用户选择 |
|---|-----|------|---------|
| 1 | 侧边栏导航 | 大卡片式 · 两张横向卡片，选中发光 | C |
| 2 | 模式展示 | 胶囊标签行 · `[🔴STRICT]` `[🟢LOOSE]` hover 详情 | B |
| 3 | 状态栏 | Neon 横幅 · cyan 边框，收盘/盘中双态 pulse | A |
| 4 | AI 加载残留 | st.empty() placeholder 显式清除 | 直接修 |
| 5 | 切换 tab 丢股票 | scan_data 缓存 session_state | 直接修 |
| 6 | AI 分析展示 | 顶部摘要条 · 情绪 + 仓位 + 观点 | A |

---

## 详细设计

### 1. 侧边栏导航 · 大卡片式

**现状**: `st.radio("◆ 导航", ["◆ 选股", "◆ 复盘"], key="nav_page")` — Streamlit 默认小圆点 radio。

**改为**: 
- 用 `st.columns(2)` + `st.button` 实现两张横向卡片
- CSS 做成 neon-pill 卡片样式：选中态 cyan 发光边框 + 背景高亮 + scale(1.02)，未选中态暗色半透明
- 按钮 `on_click` 回调切换 `st.session_state.nav_page` 并 `st.rerun()`
- 移除原 `st.radio`

**CSS 要点**:
- `border: 1px solid rgba(0,240,255,0.6)` 选中态
- `box-shadow: 0 0 12px rgba(0,240,255,0.15)`  
- `transition: all 0.2s ease`
- 非选中态 `border-color: transparent; opacity: 0.5`

### 2. 模式展示 · 胶囊标签行

**现状**: 侧边栏纯文字 markdown。

**改为**:
- 从侧边栏删除"两种模式"文字
- 在选股页面标题下方添加一行胶囊标签
- 两个 `st.markdown(unsafe_allow_html=True)` 渲染的 HTML pills
- 每个 pill 显示模式名 + 连板数，`title` 属性含完整信息（胜率、Sharpe）
- STRICT: `rgba(255,51,102,0.08)` 底 + `#FF3366` 字
- LOOSE: `rgba(0,255,136,0.06)` 底 + `#00FF88` 字

**HTML 结构**:
```html
<span class="mode-pill strict" title="3连板 | 胜率70% | Sharpe 1.71">🔴 STRICT</span>
<span class="mode-pill loose" title="2连板 | 胜率60% | Sharpe 1.29">🟢 LOOSE</span>
```

### 3. 扫描状态栏 · Neon 横幅

**现状**: `st.success()` / `st.info()` / `st.caption()` — 系统默认色。

**改为**: 统一用自定义 HTML 横幅
- 收盘后: cyan 边框 + `✅` + "今日最终结果（收盘后）" + 时间戳 + 绿色 pulse dot
- 盘中: amber (#FFB800) 边框 + `🔄` + "盘中实时结果" + 时间戳 + amber pulse dot  
- 非交易时段: 灰色低调文字

**HTML 结构**:
```html
<div class="neon-status-bar closed">
  <span class="icon">✅</span>
  <span class="text">今日最终结果（收盘后）</span>
  <span class="spacer"></span>
  <span class="label">扫描时间</span>
  <span class="time">2026-06-12 20:04</span>
  <span class="pulse-dot cyan"></span>
</div>
```

### 4. 修复 AI 加载文字不消失

**根因**: `st.write("正在对...")` 在同步阻塞调用前输出，依赖 Streamlit 自动 rerun 清除。存在两个处理路径可能互相干扰。

**修复**:
- 用 `placeholder = st.empty()` 替代 `st.write`
- 分析完成后显式调用 `placeholder.empty()`
- 统一 AI 分析处理入口：在 `if page == '◆ 选股'` 块顶部（渲染列表之前）集中处理所有 `analyze_{code}=True` 的请求
- 处理完 `st.rerun()` 确保下一帧干净

### 5. 修复切换面板股票消失

**根因**: AI 分析同步阻塞期间，页面无法响应用户交互。切换 tab 的 queue 事件要等阻塞结束才处理。

**修复**:
- `scan_data` 首次加载后存入 `st.session_state["cached_scan_data"]`，切换 tab 不丢失
- 候选列表渲染与 AI 分析状态完全解耦 —— 分析在列表渲染之前独立处理
- 保留 `load_latest_results()` 作为 fallback

**代码结构调整**:
```
if page == '◆ 选股':
    1. 处理所有待处理 AI 请求 (最顶部)
    2. load/cache scan_data
    3. 渲染状态栏 + 模式 pills
    4. 渲染候选列表
    5. 渲染 AI 分析结果 (expander)
```

### 6. AI 分析展示 · 顶部摘要条

**现状**: `st.expander(f"◆ {code} AI分析报告", expanded=True)` 直接 dump 长 markdown。

**改为**:
- expander 标题行下方插入摘要条：三个小胶囊显示 `情绪档位` / `仓位建议` / `一句话观点`
- 从 AI 返回的 markdown 中提取这些信息（正则匹配或要求 DeepSeek 返回固定格式）
- expander 右上角加复制按钮（`st.button` + `pyperclip` 或 `st.code` 变通）
- CSS 美化 expander 边框为 neon 风格

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `streamlit_app.py` | 导航、模式 pills、状态栏、AI 分析流程重构、展示优化 |
| `streamlit_app.py` (CSS `inject_design_system()`) | 新增导航卡片、模式 pills、状态栏、AI 展开器的 CSS 规则 |
| `docs/superpowers/specs/2026-06-13-neon-vault-ui-polish-design.md` | 本设计文档 |

---

## 验证

```bash
streamlit run streamlit_app.py
```

检查点:
1. 侧边栏导航是否两张 neon 卡片按钮
2. 选股页面顶部是否有 STRICT/LOOSE 胶囊标签
3. 状态栏是否 neon 风格（收盘 cyan / 盘中 amber）
4. AI 分析完成后加载文字是否立即消失
5. AI 分析期间切换 选股→复盘→选股 → 列表是否还在
6. AI 展开器是否有摘要条 + 复制按钮
