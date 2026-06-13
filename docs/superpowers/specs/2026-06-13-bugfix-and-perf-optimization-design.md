# 复盘页面修Bug + 性能优化 · 设计文档

**日期**: 2026-06-13
**状态**: 已确认

## 概述

修复4个线上问题：(1) 累计收益显示 -1401%（计算错误），(2) AI记忆记录格式混乱，(3) app性能卡顿，(4) AI分析中切换页面显示异常。

## 设计决策

| # | 决策 | 选择 |
|---|------|------|
| 1 | 绩效指标范围 | 核心四件套：累计收益、胜率、盈亏比、最大回撤 |
| 2 | 绩效模式 | strict/loose 分离 + 近30天窗口，各配独立收益曲线 |
| 3 | AI卡片摘要 | 结论摘要模式：显示 opinion + sentiment + position，不截取原始markdown |
| 4 | 性能优化 | 方案C：后台线程 + 分析队列 + JS自动轮询 + 全局进度条 |
| 5 | 导航修复 | 方案C自然消除根因，重新分析按钮不再强制跳转 |

---

## 一、绩效计算修复 + 模式分离

### Bug根因

`compute_performance()` 使用算术加法累加百分比：`running += r['return_3d']`。例如5个+3%和一个-20%，算术和为 -5%，实际复合收益为 `(1.03^5 * 0.8 - 1)*100 = -10.3%`。几百笔交易累加后产生不可能的值（-1401%）。

附加问题：
- 所有模式（strict/loose/normal）混在一起，同一股票同一天可能重复计数
- 无时间窗口，CNY全历史信号都参与计算
- 0%收益被计为亏损
- `show_signal_review()` 中 `:.2%` 格式符双倍编码（5.0 → "500.00%"）

### 修复方案

**函数签名改为：**
```python
def compute_performance(mode_filter=None, days_window=30):
```

**复合收益：**
```python
equity = 1.0
for r in returns:
    equity *= (1 + r['return_3d'] / 100)
total_return = (equity - 1) * 100
```

**过滤逻辑：**
```python
cutoff = today_int - days_window
if mode_filter:
    df = df[df['mode'] == mode_filter]
df = df[df['signal_date'] >= cutoff]
```

**最大回撤在真实equity曲线上计算：**
```python
peak = 1.0
max_dd = 0.0
for eq in equity_curve:
    peak = max(peak, eq)
    dd = (peak - eq) / peak * 100
    max_dd = max(max_dd, dd)
```

**`show_signal_review()` 格式修复：**
```python
# 旧: f"{sum(gains)/len(gains):+.2%}"  → 5.0显示为"500.00%"
# 新: f"{sum(gains)/len(gains):+.2f}%" → 5.0显示为"+5.00%"
```

### 复盘页面渲染

```
◆ STRICT (近30天)                    ◆ LOOSE (近30天)
累计收益 +8.4%  胜率 69%            累计收益 +12.1%  胜率 60%
盈亏比 2.1  最大回撤 -5.2%           盈亏比 1.5  最大回撤 -8.7%
6胜/3负                              15胜/10负
📈 累计收益曲线 (line_chart)           📈 累计收益曲线 (line_chart)
```

- strict 曲线用 cyan 色，loose 用 purple 色
- 数据点 <3 笔 → 显示 "数据不足，继续积累"
- 30天内无数据 → "暂无数据，等待信号积累"

---

## 二、AI记忆格式修正

### Bug根因

1. **情绪提取失败**：正则 `情绪档位[：:]` 在AI输出中匹配不到，因为AI把情绪放在了 `仓位建议：0成仓（冰点/观望）` 的括号内
2. **仓位带 markdown 残留**：AI 输出 `**仓位建议：0成仓（冰点/观望）**`，正则 `(.+?)(?:\n|$)` 吞掉了尾部的 `**`
3. **卡片预览原始markdown**：`analysis[:120]` 直接截取 `## 一、量（Volume）\n- **回调缩量评估**...`，在纯文本卡片里乱码

### 修复方案

**合并正则一行两抓：**
```python
m = _re.search(r'仓位建议[：:]\s*(.+?)（(.+?)）', analysis_text)
if m:
    position = m.group(1).strip().rstrip('*')   # "0成仓"
    sentiment = m.group(2).strip().rstrip('*')  # "冰点/观望"
```

**备用提取（如果括号格式不匹配）：**
```python
# 独立行：情绪档位：XXX
sm = _re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$|\*\*)', analysis_text)
```

**意见提取（已有，加固去 markdown）：**
```python
om = _re.search(r'最终结论[：:]\s*(.+?)(?:\n|$|\*\*)', analysis_text)
opinion = om.group(1).strip().rstrip('*') if om else ""
```

**卡片显示改为结论摘要：**
```
旧：◆ ## 一、量（Volume）\n- **回调缩量评估：不足**...（raw markdown）
新：◆ 【放弃】 · 冰点/观望 · 0成仓
```

渲染代码：
```html
<div style="...">
  <span style="color:#00F0FF">◆</span>
  <span style="color:#D0D0E8">{opinion}</span>
  <span style="color:#555577">·</span>
  <span style="color:#9B6FFF">{sentiment}</span>
  <span style="color:#555577">·</span>
  <span style="color:#8888AA">{position}</span>
</div>
```

缺失字段则不显示对应的 `·` 分隔符。

**旧数据回溯：** `auto_verify_memory()` 加载时对已有记录重新提取 sentiment/position，覆盖空值和 `**` 残留。

---

## 三、性能优化（方案C：异步队列）

### 架构

```
用户点击 AI分析 → 加入队列 → 后台线程逐条处理 → 结果写入 session_state
                     ↓                              ↓
              用户自由切换页面            JS轮询(2s)自动rerun展示结果
```

### 数据结构（session_state）

```python
"analysis_queue": []         # 待分析 code 列表
"analysis_results": {}       # {code: analysis_text} 已完成
"analysis_running": False    # 队列是否在运行
"analysis_current": None     # 当前正在分析的 code
"analysis_errors": {}        # {code: error_msg} 失败的
```

### 后台工作线程

```python
import threading

def _analysis_worker():
    """后台线程：逐条消费队列"""
    while True:
        if not st.session_state.analysis_queue:
            break
        code = st.session_state.analysis_queue.pop(0)
        st.session_state.analysis_current = code
        try:
            stock_df = ...  # 获取数据
            market_ctx = screener.get_market_context()
            memory_context = get_stock_memory_context(code)
            result = fast_ai_analysis(code, stock_df, market_ctx, memory_context)
            st.session_state.analysis_results[code] = result
            # 自动存档
            save_ai_analysis_record(code=code, date_str=..., mode=..., ...)
        except Exception as e:
            st.session_state.analysis_errors[code] = str(e)
            st.session_state.analysis_results[code] = None
    st.session_state.analysis_running = False
    st.session_state.analysis_current = None

# 启动
thread = threading.Thread(target=_analysis_worker, daemon=True)
thread.start()
```

### JS自动轮询

```python
if st.session_state.analysis_running:
    st.markdown("""
    <script>
    (function() {
        if (window._analysisPollTimer) return;
        window._analysisPollTimer = setInterval(() => {
            window.parent.postMessage({type: 'streamlit:rerun'}, '*');
        }, 2000);
    })();
    </script>
    """, unsafe_allow_html=True)
```

分析完成后清除（通过检测 `analysis_running == False`，不注入 script）。

### 全局进度条

```python
if st.session_state.analysis_running:
    current = st.session_state.analysis_current or "..."
    queue_len = len(st.session_state.analysis_queue)
    done = len(st.session_state.analysis_results)
    st.markdown(f"""
    <div style="padding:6px 0;font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#00F0FF;
                border-bottom:1px solid rgba(0,240,255,0.08);margin-bottom:8px">
      ◆ 分析中: {current} · 队列剩余 {queue_len} 只
      <span style="color:#555577">{"·" * (done % 4 + 1)}</span>
    </div>
    """, unsafe_allow_html=True)
```

### 重新分析按钮行为变更

```python
# 旧：强制跳转到选股页
if st.button("🔄 重新分析(带入记忆)", key=f"reanalyze_{code}_{rec['date']}"):
    st.session_state[f"analyze_{code}"] = True
    st.session_state["nav_page"] = "◆ 选股"
    st.rerun()

# 新：加入队列 + 就地反馈
if st.button("🔄 重新分析(带入记忆)", key=f"reanalyze_{code}_{rec['date']}"):
    if code not in st.session_state.analysis_queue:
        st.session_state.analysis_queue.append(code)
    st.session_state.analysis_running = True
    if not hasattr(st, '_worker_started'):
        thread = threading.Thread(target=_analysis_worker, daemon=True)
        thread.start()
    st.success(f"已加入分析队列")
```

---

## 四、导航修复

方案C自然解决了所有导航问题：

| 旧问题 | 如何解决 |
|--------|---------|
| `ai_placeholder` 绑定到旧渲染树，切换页面后丢失 | 不再用 `st.empty()` 占位，结果存入 session_state 驱动渲染 |
| 分析期间切换页面 → 状态丢失 | 后台线程不依赖当前页面，切回来自动从 session_state 读取 |
| `st.rerun()` 链条破坏上下文 | 不再链式 rerun，改用 JS 轮询触发自然刷新 |
| 重新分析强制跳转 | 改为加入队列 + 行内反馈，保持在当前页面 |

旧 `analyze_{code}` 标记机制完全废弃，被 `analysis_queue` + `analysis_results` 替代。

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `streamlit_app.py` | `compute_performance()` 重写、`save_ai_analysis_record()` 正则修复、AI分析入口改为队列模式、复盘页面渲染更新、全局进度条、`show_signal_review()` 格式修复 |
| `ai_memory.json` | `auto_verify_memory()` 回溯修复旧记录的 sentiment/position |

---

## 霓虹风格要点

- 四色系统：cyan `#00F0FF`（strict/数据）、purple `#9B6FFF`（loose/待验）、green `#00FF88`（盈利/正确）、red `#FF5050`（亏损/偏差）
- 全局进度条：极细 `1px solid rgba(0,240,255,0.08)` 底边线，JetBrains Mono 0.5rem
- 绩效数字：无卡片包裹，纯文字排版，1.3rem 粗体数值 + 0.5rem 灰色标签
- 记忆卡片：左边框 2px 区分状态，hover 微亮
- 数据不足/空状态：居中灰色提示，不出错不报红
