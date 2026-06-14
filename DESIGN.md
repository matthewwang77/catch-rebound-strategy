# DESIGN.md — NEON VAULT v3

> 暗黑赛博终端美学：数据不冰冷，交易有温度。每一像素都在说"我是专业的"。

## 1. Visual Theme & Atmosphere

**Style**: Dark Neon Cyberpunk Terminal (暗黑霓虹赛博终端)
**Keywords**: 专业、冷峻、霓虹、数据密集、玻璃态、扫描线、未来感
**Tone**: 高对比度暗黑 — NOT 卡通化、NOT 廉价荧光、NOT 混乱信息
**Feel**: 像深夜盯着多屏交易台的 Bloomberg Terminal，但比它好看100倍。

**Interaction Tier**: L2 流畅交互（Scroll reveal + Hover glow + Nav transition）
**Dependencies**: CSS only（Streamlit 约束 — 无 GSAP/JS）

## 2. Color Palette & Roles

```css
:root {
  /* Backgrounds */
  --bg: #050508;
  --surface: #0A0B14;
  --card: #0D0D1E;

  /* Neon Accents */
  --green: #00FF88;    /* 主霓虹 — CTA / 活跃 / 上涨 */
  --cyan: #00F0FF;     /* 次霓虹 — 信息 / 链接 / 中性 */
  --purple: #7B2FFF;   /* 等待 / 排队 */
  --amber: #FFB800;    /* 警告 / 熊市标注 */
  --red: #FF3366;      /* 错误 / 下跌 / 止损 */

  /* Text */
  --text-primary: #E8E8E8;
  --text-secondary: #AAA;
  --text-tertiary: #666;

  /* Borders */
  --border-subtle: rgba(255,255,255,0.06);
  --border-glow: rgba(0,255,136,0.15);

  /* RGB for rgba() */
  --green-rgb: 0, 255, 136;
  --cyan-rgb: 0, 240, 255;
  --purple-rgb: 123, 47, 255;
  --amber-rgb: 255, 184, 0;
  --red-rgb: 255, 51, 102;
}
```

**Color Rules:**
- 所有颜色通过 CSS 变量引用，禁止硬编码 hex
- 同一区域只用一个强调色（绿/青/紫/琥/红 各司其职）
- 绿色=做多信号/盈利，红色=亏损/止损，琥珀=警告/熊市
- 背景层禁止使用任何饱和度>5%的颜色

## 3. Typography Rules

### Font Family
```css
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

--font-display: 'Orbitron', monospace;
--font-body: 'JetBrains Mono', monospace;
```

### Type Scale ⚠️ 硬性底线: 禁止 < 0.75rem

| Role | Font | Size | Weight | Color |
|------|------|------|--------|-------|
| Page Title h1 | Orbitron | 2.2rem | 700 | --green |
| Section Title h2 | Orbitron | 1.25rem | 600 | --text-primary |
| Card Title h3 | Orbitron | 0.95rem | 600 | --text-primary |
| Body / Card Text | JetBrains Mono | 0.8rem | 400 | --text-secondary |
| Metric Value (large) | JetBrains Mono | 1.6rem | 700 | --text-primary |
| Metric Value (small) | JetBrains Mono | 1.2rem | 600 | --text-primary |
| Metric Label | Orbitron | 0.75rem | 400 | --text-tertiary |
| Badge / Tag | JetBrains Mono | 0.78rem | 500 | varies |
| Progress / Status | JetBrains Mono | 0.78rem | 500 | --text-secondary |
| Sidebar Nav | Orbitron | 0.8rem | 600 | --text-secondary |
| Data Label | Orbitron | 0.75rem | 400 | --text-tertiary |

**Forbidden fonts**: Inter, Roboto, Arial, system-ui, Space Grotesk, system fonts

## 4. Component Stylings

### 4.1 Candidate Card
```css
.candidate-card {
  background: linear-gradient(135deg, rgba(13,13,30,0.95), rgba(8,8,20,0.9));
  border: 1px solid var(--border-glow);
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 10px;
  transition: all 0.2s ease;
}
.candidate-card:hover {
  border-color: rgba(var(--green-rgb), 0.35);
  box-shadow: 0 0 20px rgba(var(--green-rgb), 0.06);
  transform: translateY(-1px);
}
```
- Default: subtle border
- Hover: green glow + lift 1px
- AI inline strip at bottom, separated by hairline border

### 4.2 Market Status Card
```css
.market-status-card {
  background: linear-gradient(135deg, rgba(13,13,30,0.92), rgba(10,10,24,0.88));
  border: 1px solid rgba(var(--cyan-rgb), 0.15);
  border-radius: 10px;
  padding: 18px 24px;
  margin-bottom: 16px;
}
```
- Full-width with index data row + sentiment tag
- Index numbers: 0.9rem, green for up / red for down
- Sentiment tag: colored badge based on market regime

### 4.3 AI Badge (inline strip)
```css
.ai-badge {
  padding: 4px 12px;
  border-radius: 6px;
  font-family: var(--font-body);
  font-size: 0.78rem;
}
.ai-badge.opinion { color: #ffd700; background: rgba(255,215,0,0.08); border: 1px solid rgba(255,215,0,0.2); }
.ai-badge.sentiment { color: #00f0ff; background: rgba(0,240,255,0.08); border: 1px solid rgba(0,240,255,0.2); }
.ai-badge.position { color: #ff6b35; background: rgba(255,107,53,0.08); border: 1px solid rgba(255,107,53,0.2); }
```

### 4.4 Performance Card (复盘)
```css
.perf-card {
  background: linear-gradient(135deg, rgba(13,13,30,0.92), rgba(10,10,24,0.88));
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}
.perf-value { font-size: 1.6rem; font-weight: 700; }
.perf-label { font-size: 0.78rem; color: #666; text-transform: uppercase; }
```
- Positive values: green, negative: red
- 4-card grid layout

### 4.5 AI Memory Card
```css
.memory-card {
  background: rgba(13,13,30,0.8);
  border-left: 3px solid var(--green);
  border-radius: 0 8px 8px 0;
  padding: 14px 18px;
  margin-bottom: 8px;
}
```
- Left border accent by verdict: green = correct, red = wrong, purple = pending
- Verdict badge prominent

### 4.6 Navigation Card (Sidebar)
```css
.nav-card {
  background: rgba(13,13,30,0.6);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 12px 16px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.nav-card.active {
  border-color: rgba(var(--green-rgb), 0.3);
  background: rgba(var(--green-rgb), 0.05);
}
```
- Active: green border + subtle green tint
- Hover: border brightens

## 5. Layout Principles

- **Single column, card-based** — Streamlit 天然垂直流
- **间距梯度**: 8px (tight) → 12px (normal) → 16px (section gap) → 24px (page gap)
- **容器宽度**: max-width 1200px center aligned（Streamlit 默认宽布局）
- **Card padding**: 16px-20px internal, 10-16px between cards
- **数据密集但可读** — 关键数字大而醒目，辅助信息小但不低于 0.75rem
- **Section 之间用 label 分隔**（如 `◆ 选股结果 · 5只候选`）

## 6. Depth & Elevation

Streamlit 环境下用 border + subtle gradient 模拟层次（无法用 box-shadow 做厚阴影）:

| Level | 用途 | 实现 |
|-------|------|------|
| 0 | 页面背景 | `--bg` + dot grid + scanlines |
| 1 | Card / surface | `linear-gradient(surface, dark)` + 1px hairline border |
| 2 | Hover / Active | border 加亮 + subtle glow + translateY(-1px) |
| 3 | Market card (重点) | slightly brighter border + larger padding |

**不使用 box-shadow** — 在 Streamlit markdown 容器里可能被裁切。用 border 代替。

## 7. Animation & Interaction

### L2 动效清单

| 类别 | 实现 |
|------|------|
| **H1 标题** | 静态（Streamlit 不需要 hero 动画） |
| **Card 入场** | `fadeUp` keyframe — opacity 0→1 + translateY(20→0)，stagger 0.05s |
| **Card hover** | border 变亮 + translateY(-1px) + subtle green glow，0.2s ease |
| **AI 进度条** | shimmer 动画 + pulse glow |
| **Market status dot** | breathing pulse（交易中=green, 休市=dim）|
| **数字变化** | 无动画（Streamlit 限制）|

### Keyframes
```css
@keyframes fadeUp { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }
@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
@keyframes pulseGlow { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
```

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; }
}
```

## 8. Do's and Don'ts

### Do's
1. ✅ 所有字号 ≥ 0.75rem
2. ✅ 所有颜色通过 CSS 变量引用
3. ✅ 数据数字右对齐或用等宽字体
4. ✅ 上涨用绿色(#00ff88)，下跌用红色(#ff3366)，忠于交易终端惯例
5. ✅ Card 之间有明确边界（border 或 padding gap）
6. ✅ Hover 状态必须可见（border change or subtle glow）
7. ✅ 重要信息（AI 结论、收益）用 badge 高亮

### Don'ts
1. ❌ 禁止字号 < 0.75rem（CSS 全局 enforce）
2. ❌ 禁止硬编码颜色（必须用 var(--xxx)）
3. ❌ 禁止紫色-粉色渐变（AI slop 标配，极度 cliché）
4. ❌ 禁止 Inter/Roboto/Arial 等通用字体
5. ❌ 禁止纯色块占位图
6. ❌ 禁止 emoji 代替图标（Orbitron 风格下违和）
7. ❌ 禁止 box-shadow 做大面积投影（Streamlit 裁切风险）
8. ❌ 禁止 filter: blur() 在滚动元素上
9. ❌ 禁止 backdrop-filter 大面积使用（性能杀手）

## 9. Responsive Behavior

- **Desktop (≥768px)**: 完整布局, cards full-width within 1200px container
- **Mobile (<768px)**: 
  - Card padding 减小到 12px
  - Metric grid 变为 2列
  - 字号缩放到移动端舒适尺寸（body 0.8rem 不变，metric 1.2rem）
  - Sidebar 默认折叠（Streamlit 原生行为）
- **触摸目标**: ≥ 44×44px for interactive elements
