"""
每日自动选股 v6
用法: python auto_daily.py

v6新增: 市场自适应 — 自动检测熊市/牛市，切换最优参数
首次使用: 设置定时运行（见文件末尾说明）
"""
import yfinance as yf
import pandas as pd
import json
from datetime import datetime
import os
import sys
import importlib.util

# ==================== 加载模块 ====================
def _load_module(filepath, module_name):
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

BASE = os.path.dirname(os.path.abspath(__file__))  # project root
screener = _load_module(os.path.join(BASE, "选股new_v5.py"), "screener")


# ==================== 获取大盘数据 ====================
def get_market_summary():
    indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
    lines = []
    for name, code in indices.items():
        try:
            df = yf.download(code, period="5d", progress=False)
            if df is not None and len(df) >= 2:
                close_col = df['Close']
                if hasattr(close_col, 'iloc'):
                    cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                    prev = float(close_col.iloc[-2].item() if hasattr(close_col.iloc[-2], 'item') else close_col.iloc[-2])
                else:
                    cur = float(close_col.values[-1] if hasattr(close_col, 'values') else close_col[-1])
                    prev = float(close_col.values[-2] if hasattr(close_col, 'values') else close_col[-2])
                pct = (cur / prev - 1) * 100
                lines.append(f"{name}: {cur:.0f} ({pct:+.2f}%)")
            elif df is not None and len(df) == 1:
                close_col = df['Close']
                if hasattr(close_col, 'iloc'):
                    cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                else:
                    cur = float(close_col.values[-1] if hasattr(close_col, 'values') else close_col[-1])
                lines.append(f"{name}: {cur:.0f}")
        except Exception as e:
            lines.append(f"{name}: 获取失败 ({e})")
    return "\n".join(lines)


# ==================== 执行选股 ====================
def run_auto_mode():
    """只跑推荐模式（v6 unified: 检测市场状态，自动切换参数）。返回 dict。"""
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
    mode_params = screener.SCREEN_MODES.get(recommended_mode)
    if mode_params is None:
        print(f"⚠️ 未知模式 '{recommended_mode}'，回退到 STRICT")
        recommended_mode = "strict"
        mode_params = screener.SCREEN_MODES["strict"]
    screener.PARAMS.update(mode_params)

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

    return results, all_data


# ==================== 信号保存 ====================
def _save_signals(results):
    """将候选信号保存到 signal_tracker.csv（去重）。"""
    import csv
    from datetime import timedelta

    tracker_path = os.path.join(BASE, "signal_tracker.csv")
    new_rows = []
    for mode, candidates in results.items():
        for c in candidates:
            new_rows.append({
                'signal_date': str(c.get('signal_date', '')),
                'code': c.get('code', ''),
                'name': '',
                'sector': '',
                'mode': mode,
                'entry_price': round(float(c.get('price', 0)), 2),
                'pullback_pct': round(float(c.get('pullback_pct', 0)), 1),
                'limit_days': int(c.get('limit_days', 0)),
            })

    if not new_rows:
        return

    df_new = pd.DataFrame(new_rows)

    # 读取已有，去重: 同一(code, entry_price) 20天内不重复
    if os.path.exists(tracker_path):
        df_old = pd.read_csv(tracker_path)
        if len(df_old) > 0:
            df_old['signal_date'] = df_old['signal_date'].astype(str)
            keep_rows = []
            for _, row in df_new.iterrows():
                sig_date = str(row['signal_date'])
                code = row['code']
                entry_price = round(float(row['entry_price']), 2)
                try:
                    sig_dt = datetime.strptime(sig_date, '%Y%m%d')
                    cutoff_dt = sig_dt - timedelta(days=20)
                    cutoff_str = cutoff_dt.strftime('%Y%m%d')
                except ValueError:
                    keep_rows.append(True)
                    continue
                in_window = df_old[
                    (df_old['code'] == code) &
                    (df_old['entry_price'].round(2) == entry_price) &
                    (df_old['signal_date'] >= cutoff_str) &
                    (df_old['signal_date'] <= sig_date)
                ]
                keep_rows.append(len(in_window) == 0)
            df_new = df_new[keep_rows]
            if len(df_new) == 0:
                print("📁 信号无新增（全部重复）")
                return
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_combined = df_new
    else:
        df_combined = df_new

    df_combined.to_csv(tracker_path, index=False, encoding='utf-8-sig')
    print(f"📁 信号保存: {len(df_new)} 条新记录 → {tracker_path}")


# ==================== AI 分析 ====================
AI_MEMORY_FILE = os.path.join(BASE, "ai_memory.json")


def _load_ai_memory():
    if not os.path.exists(AI_MEMORY_FILE):
        return {}
    try:
        with open(AI_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ai_memory(memory):
    with open(AI_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def _run_ai_analysis(code, stock_df, candidate, market_context, mode):
    """对单只候选股调用 DeepSeek API 进行量价形时分析，存入 ai_memory.json。"""
    import requests

    date_str = str(candidate.get('signal_date', datetime.now().strftime('%Y%m%d')))
    entry_price = float(candidate.get('price', 0))
    pullback_pct = float(candidate.get('pullback_pct', 0))
    limit_days = int(candidate.get('limit_days', 0))

    # 去重检查
    memory = _load_ai_memory()
    if code in memory:
        for rec in memory[code]:
            if rec.get("date") == date_str:
                return  # 已有同日记录

    # 列名兼容
    if 'close' in stock_df.columns and 'Close' not in stock_df.columns:
        stock_df = stock_df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})

    close = stock_df['Close'].dropna()
    high = stock_df['High'].dropna()
    low = stock_df['Low'].dropna()
    volume = stock_df['Volume'].dropna()
    o = stock_df['Open'].dropna()

    if len(close) < 5:
        return

    # 基础指标
    current_price = float(close.iloc[-1])
    pct_chg = (current_price / float(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
    ma5 = float(close.rolling(5).mean().iloc[-1])
    ma10 = float(close.rolling(10).mean().iloc[-1])
    ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else ma10
    vol_today = float(volume.iloc[-1])
    vol_ma5 = float(volume.rolling(5).mean().iloc[-1])
    recent_high_20 = float(high.tail(20).max())
    recent_low_20 = float(low.tail(20).min())

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_bar = 2 * (dif - dea)
    dif_val = float(dif.iloc[-1])
    dea_val = float(dea.iloc[-1])
    macd_bar_val = float(macd_bar.iloc[-1])
    if dif_val > dea_val:
        macd_trend = "金叉向上"
    elif dif_val < dea_val:
        macd_trend = "死叉向下"
    else:
        macd_trend = "粘合"

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    rsi_val = float(rsi.iloc[-1])

    # 布林带(20,2)
    bb_mid = float(close.rolling(20).mean().iloc[-1])
    bb_std = float(close.rolling(20).std().iloc[-1])
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # OBV
    close_diff_sign = (close.diff() > 0).astype(int) - (close.diff() < 0).astype(int)
    obv = (volume * close_diff_sign).cumsum()
    obv_now = float(obv.iloc[-1])
    obv_5d_ago = float(obv.iloc[-6]) if len(obv) >= 6 else float(obv.iloc[0])
    obv_trend = "上升（资金流入）" if obv_now > obv_5d_ago else "下降（资金流出）"

    # 涨停检测
    pct_chg_series = close.pct_change()
    limit_up_mask = pct_chg_series > 0.095
    limit_up_data = ""
    if limit_up_mask.any():
        lu_indices = close.index[limit_up_mask].tolist()
        last_lu_idx = lu_indices[-1]
        last_lu_close = float(close.loc[last_lu_idx])
        days_since = len(close) - close.index.get_loc(last_lu_idx) - 1
        vol_shrink = float(volume.iloc[-3:].mean() / float(volume.loc[last_lu_idx]) * 100) if last_lu_idx in volume.index else 100
        lu_date = str(last_lu_idx)[:10]
        limit_up_data = f"""
## 回调数据
- 最近涨停日：{lu_date}（推测{limit_days}连板）
- 距涨停日：{days_since} 天
- 回调幅度：{pullback_pct:.1f}%
- 缩量程度：近3日均量/涨停日量 = {vol_shrink:.0f}%"""

    technical_data = f"""【{code} 技术数据】

## 基础指标
- 最新价：{current_price:.2f}（今日 {pct_chg:+.2f}%）| 均线：MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20:.2f}
- 量比：今日/5日均量={vol_today/vol_ma5:.2f}x | 20日高={recent_high_20:.2f}

## 技术指标
- MACD(12,26,9)：DIF={dif_val:.3f} DEA={dea_val:.3f} 柱={macd_bar_val:+.3f} → {macd_trend}
- RSI(14)：{rsi_val:.1f}
- 布林(20,2)：上轨={bb_upper:.2f} 中轨={bb_mid:.2f} 下轨={bb_lower:.2f}
- OBV趋势：{obv_trend}{limit_up_data}"""

    system_prompt = """你是专精于A股连板回调策略的量化分析师。严格遵循"量价形时"四维分析框架：
【量】缩量挖坑（回调量<涨停量50%为佳），放量填坑（反弹需放量确认）
【价】首板不破涨停最低价，MA支撑体系层层验证
【形】缩量黄金坑、长下影弹簧线、缩倍阴、三阴不破阳、天外飞仙、金凤凰
【时】3-5天为黄金回调窗口，超过7天不恢复=明显走弱
最终给出【参与/观望/放弃】结论 + 仓位建议（对应情绪档位：冰点空仓/低迷1-2成/启动2-3成/发酵3-5成/高潮减仓）。"""

    prompt = f"""{technical_data}

{market_context}

请按"量价形时"框架逐项分析，每项给出具体判断，最后给出：
- 反弹概率：低(≤30%) / 中(30-60%) / 高(≥60%)
- 仓位建议：X成仓（情绪档位）
- 最终结论：【参与 / 观望 / 放弃】"""

    try:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            print(f"  ⚠️ {code} AI 跳过: API Key 未配置")
            return
        api_url = screener.DEEPSEEK_API_URL

        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 800,
            },
            timeout=25,
        )
        if resp.status_code != 200:
            print(f"  ⚠️ {code} AI API 错误: HTTP {resp.status_code}")
            return
        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            print(f"  ⚠️ {code} AI 返回异常格式")
            return
        analysis_text = data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ {code} AI 异常: {e}")
        return

    # 正则提取关键字段
    import re as _re
    sentiment = ""
    position = ""
    opinion = ""
    try:
        m = _re.search(r'仓位建议[：:]\s*(.+?)（(.+?)）', analysis_text)
        if m:
            position = m.group(1).strip().strip('*')
            sentiment = m.group(2).strip().strip('*')
        if not sentiment:
            sm = _re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', analysis_text)
            if sm:
                sentiment = sm.group(1).strip().strip('*')
        om = _re.search(r'最终结论[：:]\s*(.+?)(?:\n|$)', analysis_text)
        if om:
            opinion = om.group(1).strip().strip('*')
    except Exception:
        pass

    # 存入记忆
    memory = _load_ai_memory()
    if code not in memory:
        memory[code] = []
    memory[code].append({
        "date": date_str,
        "mode": mode,
        "entry_price": entry_price,
        "pullback_pct": pullback_pct,
        "limit_days": limit_days,
        "analysis": analysis_text,
        "sentiment": sentiment,
        "position": position,
        "opinion": opinion,
        "verified": False,
        "return_3d": None, "return_5d": None, "return_7d": None,
        "verdict": None,
    })
    _save_ai_memory(memory)
    print(f"  🤖 {code} AI 分析完成 → 记忆已保存")


# ==================== 格式化消息 ====================
def format_message(results):
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    market = get_market_summary()

    # v6: 添加市场状态
    regime_note = ""
    try:
        regime_info = screener.detect_market_regime()
        regime_note = f"\n  市场状态: {regime_info['sentiment_label']} | 推荐模式: {regime_info['recommended_mode']}"
        if regime_info['regime'] == 'bear':
            regime_note += "\n  ⚠️ 熊市环境 — 熊市信号请谨慎参与"
    except Exception:
        pass

    total = sum(len(v) for v in results.values())
    mode_names = {"strict": "🔴严格", "loose": "🟢宽松", "bear": "🐻熊市"}

    lines = [
        f"📈 A股连板回调 v6 · {today}",
        "",
        "━━ 📊 大盘 ━━",
        market + regime_note,
        "",
        f"━━ 📋 选股结果（共 {total} 只）━━",
    ]

    for mode, cands in results.items():
        name = mode_names.get(mode, mode)
        if cands:
            lines.append(f"\n{name} ({len(cands)}只):")
            for c in cands:
                lines.append(
                    f"  {c['code']} | {c['price']:.2f}元 | "
                    f"回调{c['pullback_pct']:.1f}% | "
                    f"{c['limit_days']}连板 | "
                    f"实体{c['entity_ratio']:.0f}%"
                )
        else:
            lines.append(f"\n{name}: 无候选")

    if total == 0:
        lines.append("\n💤 今日无信号，休息。")

    return "\n".join(lines)


# ==================== JSON 结果保存 ====================
def save_results_json(results):
    """保存结构化 JSON 结果，供 Streamlit 自动加载。v6: 包含市场状态。"""
    import json

    now = datetime.now()
    # 解析大盘数据
    market = {}
    try:
        indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
        for name, code in indices.items():
            df = yf.download(code, period="5d", progress=False)
            if df is not None and len(df) >= 2:
                close_col = df['Close']
                if hasattr(close_col, 'iloc'):
                    cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                    prev = float(close_col.iloc[-2].item() if hasattr(close_col.iloc[-2], 'item') else close_col.iloc[-2])
                else:
                    cur = float(close_col.values[-1] if hasattr(close_col, 'values') else close_col[-1])
                    prev = float(close_col.values[-2] if hasattr(close_col, 'values') else close_col[-2])
                market[name] = {
                    "price": round(cur, 2),
                    "pct": round((cur / prev - 1) * 100, 2),
                }
    except Exception:
        pass

    # v6: 市场状态检测
    regime = {}
    try:
        regime = screener.detect_market_regime()
    except Exception:
        regime = {'regime': 'unknown', 'sentiment_label': '检测失败'}

    output = {
        "scan_time": now.strftime("%Y-%m-%d %H:%M"),
        "scan_date": now.strftime("%Y%m%d"),
        "market": market,
        "regime": {
            "status": regime.get('regime', 'unknown'),
            "label": regime.get('sentiment_label', ''),
            "avg_trend": regime.get('avg_trend', 0),
            "recommended_mode": regime.get('recommended_mode', 'strict'),
        },
        "modes": {},
    }
    for mode, candidates in results.items():
        output["modes"][mode] = {
            "count": len(candidates),
            "candidates": [
                {
                    "code": c.get("code", c.get("代码", "")),
                    "price": c.get("price", c.get("最新价", 0)),
                    "signal_date": c.get("signal_date", ""),
                    "pullback_pct": c.get("pullback_pct", c.get("回调比", 0)),
                    "limit_days": c.get("limit_days", c.get("连板数", 0)),
                    "entity_ratio": c.get("entity_ratio", 0),
                }
                for c in candidates
            ],
        }

    # 保存最新结果（项目根目录）
    latest_path = os.path.join(BASE, "latest_scan_results.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 保存历史归档
    archive_dir = os.path.join(BASE, "results_archive")
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{now.strftime('%Y%m%d')}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(v["count"] for v in output["modes"].values())
    print(f"📁 JSON 保存: {latest_path} ({total} 只候选)")
    print(f"📁 历史归档: {archive_path}")


# ==================== 主流程 ====================
def git_push_results():
    """自动 commit + push 结果到 GitHub，供 Streamlit Cloud 更新"""
    import subprocess
    try:
        cwd = BASE
        # git add 结果文件
        subprocess.run(
            ["git", "add", "latest_scan_results.json", "results_archive/"],
            cwd=cwd, capture_output=True, timeout=10,
        )
        # git commit
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        result = subprocess.run(
            ["git", "commit", "-m", f"auto: scan results {ts}"],
            cwd=cwd, capture_output=True, timeout=10,
        )
        # 如果有变更才 push
        if b"nothing to commit" not in result.stdout and b"nothing to commit" not in result.stderr:
            subprocess.run(
                ["git", "push", "origin", "master"],
                cwd=cwd, capture_output=True, timeout=30,
            )
            print("✅ Git push 完成，Streamlit Cloud 将自动更新")
        else:
            print("📁 结果无变化，跳过 push")
    except Exception as e:
        print(f"⚠️ Git push 失败: {e}（不影响选股结果）")


def main():
    # 周末跳过（A股周一至周五交易）
    now = datetime.now()
    if now.weekday() >= 5:  # 5=Sat, 6=Sun
        print(f"⏭️ 周末休市，跳过: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        return

    print("=" * 50)
    print(f"🚀 自动选股启动: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 选股
    results, all_data = run_auto_mode()

    # 保存 JSON（供 Streamlit 读取）
    save_results_json(results)

    # 保存信号到跟踪文件（供复盘页面使用）
    _save_signals(results)

    # AI 分析（仅对推荐模式的候选）
    try:
        market_context = screener.get_market_context()
    except Exception:
        market_context = "大盘数据获取失败"
    for mode, candidates in results.items():
        if not candidates:
            continue
        print(f"\n🤖 AI 分析开始: {mode} 模式 {len(candidates)} 只候选")
        for i, c in enumerate(candidates):
            code = c.get('code', '')
            stock_df = all_data.get(code)
            if stock_df is None or len(stock_df) < 5:
                print(f"  ⚠️ {code} 数据不足，跳过 AI")
                continue
            print(f"  [{i+1}/{len(candidates)}] {code} ...")
            _run_ai_analysis(code, stock_df, c, market_context, mode)
        print(f"✅ AI 分析完成: {mode}")

    # 格式化消息
    msg = format_message(results)
    print("\n" + msg)

    # 保存文本日志
    result_dir = os.path.join(BASE, "auto_logs")
    os.makedirs(result_dir, exist_ok=True)
    result_path = os.path.join(result_dir, f"auto_result_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")
    with open(result_path, "w") as f:
        f.write(msg)

    # 自动 push 到 GitHub（Streamlit Cloud 更新）
    git_push_results()

    print("\n✅ 完成")


if __name__ == "__main__":
    main()

# ==================== 设置定时运行 ====================
#
# macOS (推荐 launchd):
#   1. 创建文件 ~/Library/LaunchAgents/com.grab_rebound.screen.plist
#   2. 内容如下（交易日 10:00 / 11:30 / 14:00 / 15:00 执行）:
#
#   <?xml version="1.0" encoding="UTF-8"?>
#   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
#     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
#   <plist version="1.0">
#   <dict>
#       <key>Label</key>
#       <string>com.grab_rebound.screen</string>
#       <key>ProgramArguments</key>
#       <array>
#           <string>/Users/mattsmacair/micromamba/bin/python3</string>
#           <string>/Users/mattsmacair/Desktop/Coding/量化模型/抓反弹策略/auto_daily.py</string>
#       </array>
#       <key>StartCalendarInterval</key>
#       <array>
#           <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
#           <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>30</integer></dict>
#           <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer></dict>
#           <dict><key>Hour</key><integer>15</key><key>Minute</key><integer>0</integer></dict>
#       </array>
#       <key>EnvironmentVariables</key>
#       <dict>
#           <key>DEEPSEEK_API_KEY</key>
#           <string>你的DeepSeekKey</string>
#       </dict>
#       <key>StandardOutPath</key>
#       <string>/tmp/grab_rebound_screen.log</string>
#       <key>StandardErrorPath</key>
#       <string>/tmp/grab_rebound_screen.err</string>
#   </dict>
#   </plist>
#
#   3. 加载: launchctl load ~/Library/LaunchAgents/com.grab_rebound.screen.plist
#   4. 卸载: launchctl unload ~/Library/LaunchAgents/com.grab_rebound.screen.plist
#
# 或者用 crontab:
#   1. crontab -e
#   2. 添加: 0 10 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
#           30 11 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
#           0 14 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
#           0 15 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
