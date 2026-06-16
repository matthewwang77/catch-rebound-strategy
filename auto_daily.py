"""
每日自动选股 v6
用法: python auto_daily.py

v6新增: 市场自适应 — 自动检测熊市/牛市，切换最优参数
首次使用: 设置定时运行（见文件末尾说明）
"""
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
import os
import sys
import time as _time
import importlib.util
import concurrent.futures

# ==================== 加载模块 ====================
def _load_module(filepath, module_name):
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

BASE = os.path.dirname(os.path.abspath(__file__))  # project root
screener = _load_module(os.path.join(BASE, "选股new_v5.py"), "screener")


# ==================== yf.download 超时保护 ====================
def _download_with_timeout(tickers, period="5d", timeout=30, **kwargs):
    """yf.download with timeout protection."""
    import traceback as _traceback
    # Remove progress from kwargs to avoid duplicate keyword arg
    kwargs.pop('progress', None)
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = ex.submit(yf.download, tickers, period=period, progress=False, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            ticker_str = tickers if isinstance(tickers, str) else ','.join(tickers[:3])
            print(f"  ⚠️ yfinance 下载超时 ({timeout}s): {ticker_str}")
            return None
        except Exception as e:
            ticker_str = tickers if isinstance(tickers, str) else ','.join(tickers[:3])
            print(f"  ⚠️ yfinance 下载失败: {e}")
            _traceback.print_exc()
            return None
    finally:
        ex.shutdown(wait=False)  # 不等待后台线程，避免阻塞 pipeline


# ==================== 获取大盘数据 ====================
def get_market_summary():
    indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
    lines = []
    for name, code in indices.items():
        try:
            df = _download_with_timeout(code, period="5d", timeout=30)
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
            df.columns = df.columns.str.lower()
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
            hist = _download_with_timeout(tickers=batch, period="3d", timeout=30)
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


def _get_stock_memory_context(code):
    """获取某只股票的历史分析上下文，用于注入 AI prompt。含自我反思。

    当历史记录中有 verdict=missed 或 wrong 时，注入反思提示帮助 AI 学习。
    返回格式化文本或 None。
    """
    memory = _load_ai_memory()
    if code not in memory or not memory[code]:
        return None
    records = memory[code]
    lines = ["[历史分析记录 · 含反思]"]
    has_mistakes = False

    for rec in records[-5:]:  # 最多取最近5条
        sdate = rec.get("date", "未知")
        if len(sdate) >= 8:
            sdate = f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}"
        sentiment = rec.get("sentiment", "")
        position = rec.get("position", "")
        opinion = rec.get("opinion", "")
        verdict = rec.get("verdict", "")
        ret7 = rec.get("return_7d")
        lesson = rec.get("lesson", "")
        missed_signal = rec.get("missed_signal", "")

        # 构建摘要
        summary_parts = [f"情绪:{sentiment}", f"仓位:{position}"]
        if opinion:
            summary_parts.append(f"结论:{opinion}")

        if verdict == "correct":
            summary_parts.append(f"7日后 +{ret7}% ✅准确预判")
        elif verdict == "wrong":
            has_mistakes = True
            summary_parts.append(f"7日后 {ret7}% ❌判断失误")
        elif verdict == "missed":
            has_mistakes = True
            summary_parts.append(f"7日后 +{ret7}% 🔶错失机会")
        elif verdict == "avoided":
            summary_parts.append(f"7日后 {ret7}% 🛡正确规避")
        else:
            summary_parts.append("(⏳待验证)")

        lines.append(f"- {sdate}: {' | '.join(summary_parts)}")

        # 追加反思教训
        if lesson and verdict in ('missed', 'wrong'):
            lines.append(f"  ⚠️ 教训：{lesson}")
        if missed_signal and verdict in ('missed', 'wrong'):
            lines.append(f"  🔍 遗漏信号：{missed_signal}")

    # 如果有错误记录，追加全局反思提示
    if has_mistakes:
        lines.append("\n⚠️ 注意：你之前对该股有判断失误。请反思之前的遗漏信号，本次分析更加谨慎。")

    return "\n".join(lines)


def _run_ai_analysis(code, stock_df, candidate, market_context, mode):
    """对单只候选股调用 DeepSeek API 进行量价形时分析，存入 ai_memory.json。"""
    import requests

    # ✅ 用扫描日（今天）作记录日期，signal_date 保留为参考
    scan_date_str = datetime.now().strftime('%Y%m%d')
    signal_date_str = str(candidate.get('signal_date', ''))
    entry_price = float(candidate.get('price', 0))
    pullback_pct = float(candidate.get('pullback_pct', 0))
    limit_days = int(candidate.get('limit_days', 0))

    # 去重检查：同日同代码不重复（用扫描日）
    memory = _load_ai_memory()
    if code in memory:
        for rec in memory[code]:
            if rec.get("date") == scan_date_str and rec.get("sentiment") != "历史回填":
                return  # 已有同日真实分析记录

    # 列名兼容
    if 'close' in stock_df.columns and 'Close' not in stock_df.columns:
        stock_df = stock_df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})

    # 安全标量转换（处理 .iloc[-1] 返回 Series 的情况）
    def _s(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            if hasattr(v, 'iloc'):
                return float(v.iloc[0])
            if hasattr(v, 'values'):
                return float(v.values[0])
            raise

    close = stock_df['Close'].dropna()
    high = stock_df['High'].dropna()
    low = stock_df['Low'].dropna()
    volume = stock_df['Volume'].dropna()
    o = stock_df['Open'].dropna()

    if len(close) < 5:
        return

    # 基础指标
    current_price = _s(close.iloc[-1])
    pct_chg = (current_price / _s(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
    ma5 = _s(close.rolling(5).mean().iloc[-1])
    ma10 = _s(close.rolling(10).mean().iloc[-1])
    ma20 = _s(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else ma10
    vol_today = _s(volume.iloc[-1])
    vol_ma5 = _s(volume.rolling(5).mean().iloc[-1])
    recent_high_20 = _s(high.tail(20).max())
    recent_low_20 = _s(low.tail(20).min())

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_bar = 2 * (dif - dea)
    dif_val = _s(dif.iloc[-1])
    dea_val = _s(dea.iloc[-1])
    macd_bar_val = _s(macd_bar.iloc[-1])
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
    rsi_val = _s(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    # 布林带(20,2)
    bb_mid = _s(close.rolling(20).mean().iloc[-1])
    bb_std = _s(close.rolling(20).std().iloc[-1])
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # OBV
    close_diff_sign = (close.diff() > 0).astype(int) - (close.diff() < 0).astype(int)
    obv = (volume * close_diff_sign).cumsum()
    obv_now = _s(obv.iloc[-1])
    obv_5d_ago = _s(obv.iloc[-6]) if len(obv) >= 6 else _s(obv.iloc[0])
    obv_trend = "上升（资金流入）" if obv_now > obv_5d_ago else "下降（资金流出）"

    # 涨停检测
    pct_chg_series = close.pct_change()
    limit_up_mask = pct_chg_series > 0.095
    limit_up_data = ""
    if limit_up_mask.any():
        lu_indices = close.index[limit_up_mask].tolist()
        last_lu_idx = lu_indices[-1]
        last_lu_close = _s(close.loc[last_lu_idx])
        days_since = len(close) - close.index.get_loc(last_lu_idx) - 1
        vol_shrink = _s(volume.iloc[-3:].mean() / _s(volume.loc[last_lu_idx]) * 100) if last_lu_idx in volume.index else 100
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
- 量比：今日/5日均量={f"{vol_today/vol_ma5:.2f}x" if vol_ma5 > 0 else "N/A"} | 20日高={recent_high_20:.2f}

## 技术指标
- MACD(12,26,9)：DIF={dif_val:.3f} DEA={dea_val:.3f} 柱={macd_bar_val:+.3f} → {macd_trend}
- RSI(14)：{rsi_val:.1f}
- 布林(20,2)：上轨={bb_upper:.2f} 中轨={bb_mid:.2f} 下轨={bb_lower:.2f}
- OBV趋势：{obv_trend}{limit_up_data}"""

    system_prompt = """你是A股连板回调策略量化分析师。严格遵循"量价形时"框架，控制在250字以内，必须包含最终结论。

格式要求（每项1-2句话）：
- 量：缩量程度+资金流向
- 价：均线支撑+关键位
- 形：匹配形态
- 时：回调天数+窗口评估
- 仓位建议：X成仓（情绪档位）
- 最终结论：【参与 / 观望 / 放弃】

⚠️ 最终结论和仓位建议必须出现，缺一不可。"""

    # 获取该股历史记忆（含裁决+教训）
    memory_context = _get_stock_memory_context(code)

    prompt = f"""{technical_data}

{market_context}"""

    if memory_context:
        prompt += f"""

{memory_context}"""

    prompt += """

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

        # 带重试的 API 调用
        max_retries = 2
        last_error = None
        for attempt in range(max_retries):
            try:
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
                        "max_tokens": 3000,
                    },
                    timeout=25,
                )
                break  # 成功则跳出重试循环
            except requests.exceptions.Timeout:
                last_error = "超时"
                if attempt < max_retries - 1:
                    _time.sleep(3)
            except requests.exceptions.ConnectionError:
                last_error = "连接错误"
                if attempt < max_retries - 1:
                    _time.sleep(3)
        else:
            # 全部重试失败
            print(f"  ⚠️ {code} AI API 异常: {last_error}（重试{max_retries}次后放弃）")
            return

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
        # 清理 sentiment 前缀
        for prefix in ['情绪档位：', '情绪档位:', '情绪档位']:
            if sentiment.startswith(prefix):
                sentiment = sentiment[len(prefix):].strip()
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
        "date": scan_date_str,
        "signal_date": signal_date_str,
        "mode": mode,
        "entry_price": entry_price,
        "pullback_pct": pullback_pct,
        "limit_days": limit_days,
        "analysis": analysis_text,
        "sentiment": sentiment,
        "position": position,
        "opinion": opinion,
        "verified": False,
        "return_7d": None,
        "exit_reason": None,
        "exit_day": None,
        "verdict": None,
        "review_analysis": None,
        "what_happened": None,
        "why_wrong": None,
        "missed_signal": None,
        "lesson": None,
    })
    _save_ai_memory(memory)


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
                    f"实体{c.get('entity_ratio', 0):.0f}%"
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
            df = _download_with_timeout(code, period="5d", timeout=30)
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
                ["git", "push", "origin", subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True).stdout.decode().strip() or "master"],
                cwd=cwd, capture_output=True, timeout=30,
            )
            print("✅ Git push 完成，Streamlit Cloud 将自动更新")
        else:
            print("📁 结果无变化，跳过 push")
    except Exception as e:
        print(f"⚠️ Git push 失败: {e}（不影响选股结果）")


# ==================== 裁决逻辑 ====================

def _compute_verdict(opinion, return_7d):
    """根据AI结论和实际7日收益计算裁决。

    裁决矩阵:
      AI【参与】+ 涨 → correct    AI【参与】+ 跌 → wrong
      AI【放弃】+ 涨 → missed     AI【放弃】+ 跌 → avoided
      AI【观望】+ 涨 → noted_up   AI【观望】+ 跌 → noted_down
    """
    if return_7d is None:
        return None
    is_up = return_7d > 0
    is_down = return_7d < 0
    opinion_str = str(opinion)

    if '参与' in opinion_str:
        return 'correct' if is_up else ('wrong' if is_down else None)
    elif '放弃' in opinion_str:
        return 'missed' if is_up else ('avoided' if is_down else None)
    elif '观望' in opinion_str:
        return 'noted_up' if is_up else ('noted_down' if is_down else None)
    return None


# ==================== AI 7日回顾分析 ====================

def _run_ai_review(code, record, ret7, take_profit, stop_loss, entry_price, mode):
    """调用 DeepSeek API 进行7日全路径回顾分析，产出5字段结构化复盘。"""
    import requests

    # 读取该股票的CSV数据，提取7日OHLCV
    csv_path = os.path.join(screener.DATA_DIR, f"{code}.csv")
    if not os.path.exists(csv_path):
        return

    try:
        df = pd.read_csv(csv_path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()

        entry_date = record.get('date', '')
        start_dt = pd.Timestamp(datetime.strptime(str(entry_date), '%Y%m%d'))
        mask = df.index > start_dt
        if not mask.any():
            return

        # 取最近7个交易日（到验证日为止）
        end_idx = mask.argmax() + min(10, len(df) - mask.argmax())
        recent = df.iloc[mask.argmax():end_idx]
        if len(recent) < 3:
            return

        # 构建7日走势数据
        ohlcv_lines = []
        for idx, row in recent.iterrows():
            ohlcv_lines.append(
                f"{idx.strftime('%m-%d')} | O:{float(row['open']):.2f} H:{float(row['high']):.2f} "
                f"L:{float(row['low']):.2f} C:{float(row['close']):.2f} V:{int(row['volume']):,}"
            )
        ohlcv_text = '\n'.join(ohlcv_lines[:12])  # 最多12行

    except Exception as e:
        print(f"  ⚠️ {code} 读取CSV失败: {e}")
        return

    return_pct = ret7.get('return_pct', 0) if ret7 else 0
    exit_reason = ret7.get('exit_reason', '?') if ret7 else '?'
    exit_day = ret7.get('exit_day', 0) if ret7 else 0

    review_prompt = f"""你是A股连板回调策略的复盘专家。以下是你7天前对【{code}】的分析，现在7天过去了，请做全路径回顾。

【7日前AI原始分析】
{record.get('analysis', '(无)')}

【入场信息】
- 入场日：{entry_date} | 入场价：¥{entry_price:.2f}
- 模式：{mode} | 止盈：+{take_profit*100:.0f}% | 止损：{stop_loss*100:.0f}%

【7日实际走势（逐日OHLCV）】
{ohlcv_text}

【客观结果】
- 7日收益：{return_pct:+.2f}% | 退出原因：{exit_reason} | 退出日：第{exit_day}天

请按以下5个字段输出回顾（每字段2-4句话，简洁有力）：

1. what_happened：这7天实际走势简述（涨跌节奏、关键转折日、触发了什么）
2. why_wrong：上次分析哪里判断错了/对了（复盘预测偏差的根源）
3. missed_signal：遗漏了什么关键信号（哪些量/价/形/时的信号被忽略了）
4. lesson：下次遇到类似情况该怎么做（可操作的教训）
5. verdict：从以下选一个 — 准确预判 / 判断失误 / 错失机会 / 正确规避 / 偏保守 / 偏准确

输出格式：
【走势回顾】<内容>
【判断复盘】<内容>
【遗漏信号】<内容>
【教训】<内容>
【裁决】<选一个>"""

    try:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return
        api_url = screener.DEEPSEEK_API_URL

        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是A股量化复盘专家。输出简洁、结构化、有具体数据支撑。每个字段2-4句话。"},
                    {"role": "user", "content": review_prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 1000,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            print(f"  ⚠️ {code} AI回顾 HTTP {resp.status_code}")
            return

        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            return

        review_text = data["choices"][0]["message"]["content"]
        record['review_analysis'] = review_text

        # 解析5字段
        import re as _re
        patterns = {
            'what_happened': r'【走势回顾】\s*(.*?)(?=【判断复盘】|$)',
            'why_wrong': r'【判断复盘】\s*(.*?)(?=【遗漏信号】|$)',
            'missed_signal': r'【遗漏信号】\s*(.*?)(?=【教训】|$)',
            'lesson': r'【教训】\s*(.*?)(?=【裁决】|$)',
            'verdict_raw': r'【裁决】\s*(.*?)$',
        }
        for key, pat in patterns.items():
            m = _re.search(pat, review_text, _re.DOTALL)
            if m:
                val = m.group(1).strip()
                if key == 'verdict_raw':
                    # 映射裁决文本到 verdict 枚举
                    v = val
                    if '错失机会' in v:
                        record['verdict'] = 'missed'
                    elif '判断失误' in v:
                        record['verdict'] = 'wrong'
                    elif '准确预判' in v:
                        record['verdict'] = 'correct'
                    elif '正确规避' in v:
                        record['verdict'] = 'avoided'
                    elif '偏保守' in v:
                        record['verdict'] = 'noted_up'
                    elif '偏准确' in v:
                        record['verdict'] = 'noted_down'
                else:
                    record[key] = val

        print(f"  ✅ {code} AI回顾完成 → {record.get('verdict', '?')}")

    except Exception as e:
        print(f"  ⚠️ {code} AI回顾异常: {e}")


# ==================== 后台维护 ====================

def _auto_maintenance():
    """每次运行时自动维护：7日收益验证 + AI回顾分析 + 补全中文名。"""
    from datetime import datetime as _dt
    import requests
    today_str = _dt.now().strftime('%Y%m%d')

    memory = _load_ai_memory()
    verify_count = 0
    review_count = 0
    name_count = 0

    # --- 1. 7日收益验证 + AI回顾分析 ---
    for code, records in memory.items():
        for r in records:
            date = r.get('date', '')
            try:
                days_ago = (_dt.now() - _dt.strptime(date, '%Y%m%d')).days
            except (ValueError, TypeError):
                continue

            # 提前获取模式配置（用于持有期门控）
            mode = r.get('mode', 'strict')
            mp = screener.SCREEN_MODES.get(mode, screener.SCREEN_MODES.get('strict', {}))

            # 只做回顾（≥持有期天数后才触发）
            if days_ago < mp.get('hold_days', 7):
                continue
            if r.get('verified'):
                continue
            if r.get('sentiment') == '历史回填':
                continue

            entry_price = r.get('entry_price', 0)
            if entry_price <= 0:
                continue
            tp = mp.get('take_profit', 0.05)
            sl = mp.get('stop_loss', -0.10)

            # 本地 CSV 计算7日收益
            from backfill_signals import check_return_v5_local
            ret7 = check_return_v5_local(code, date, entry_price, mp.get('hold_days', 7), tp, sl, screener.DATA_DIR)

            r7 = ret7.get('return_pct') if ret7 else None
            r['return_7d'] = round(r7, 2) if r7 is not None else None
            r['exit_reason'] = ret7.get('exit_reason', '') if ret7 else ''
            r['exit_day'] = ret7.get('exit_day', 0) if ret7 else 0
            r['verdict'] = _compute_verdict(r.get('opinion', ''), r7)
            r['verified'] = True
            verify_count += 1

            # --- AI 7日全路径回顾分析 ---
            if r7 is not None:
                try:
                    _run_ai_review(code, r, ret7, tp, sl, entry_price, mode)
                    review_count += 1
                except Exception as e:
                    print(f"  ⚠️ {code} AI回顾失败: {e}")

    if verify_count > 0 or review_count > 0:
        _save_ai_memory(memory)
        print(f"🔍 收益验证: {verify_count} 条 | 🤖 AI回顾: {review_count} 条")

    # --- 2. 补全中文名 ---
    import csv as _csv
    import name_lookup as _nl
    tracker_path = os.path.join(BASE, "signal_tracker.csv")
    if os.path.exists(tracker_path):
        df = pd.read_csv(tracker_path)
        # 找出所有 name 为空的 code
        empty_name_codes = df[df['name'].isna() | (df['name'] == '')]['code'].unique().tolist()
        if empty_name_codes:
            names_raw = _nl.batch_lookup(empty_name_codes, max_fetch=len(empty_name_codes))
            names = {}
            for c, val in names_raw.items():
                if isinstance(val, dict):
                    names[c] = val.get('name', '')
                else:
                    names[c] = str(val) if val else ''
            # C5修复: 只更新空名称，不覆盖已有名称
            mask = df['name'].isna() | (df['name'] == '')
            df.loc[mask, 'name'] = df.loc[mask, 'code'].map(names).fillna('')
            df.to_csv(tracker_path, index=False, encoding='utf-8-sig')
            name_count = len([n for n in names.values() if n])
            print(f"📛 中文名补全: {name_count} 只")


def main():
    # 周末跳过（A股周一至周五交易）
    now = datetime.now()
    if now.weekday() >= 5:  # 5=Sat, 6=Sun
        print(f"⏭️ 周末休市，跳过: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        return

    print("=" * 50)
    print(f"🚀 自动选股启动: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 后台维护：验证旧记录 + 补全中文名
    try:
        _auto_maintenance()
    except Exception as e:
        print(f"⚠️ 后台维护失败: {e}（不影响选股）")

    # 选股
    results, all_data = run_auto_mode()

    # 保存 JSON（供 Streamlit 读取）
    save_results_json(results)

    # 保存信号到跟踪文件（供复盘页面使用）
    _save_signals(results)

    # AI 分析（对每个候选逐只分析，单只失败不中断）
    try:
        market_context = screener.get_market_context()
    except Exception:
        market_context = "大盘数据获取失败"
    for mode, candidates in results.items():
        if not candidates:
            continue
        print(f"\n🤖 AI 分析开始: {mode} 模式 {len(candidates)} 只候选")
        ai_ok, ai_fail = 0, 0
        for i, c in enumerate(candidates):
            code = c.get('code', '')
            stock_df = all_data.get(code)
            if stock_df is None or len(stock_df) < 5:
                print(f"  ⚠️ [{i+1}/{len(candidates)}] {code} 数据不足，跳过 AI")
                ai_fail += 1
                continue
            print(f"  🤖 [{i+1}/{len(candidates)}] {code} AI分析中 ...", end=" ", flush=True)
            try:
                _run_ai_analysis(code, stock_df, c, market_context, mode)
                ai_ok += 1
                print("✅")
            except Exception as e:
                ai_fail += 1
                print(f"❌ {e}")
            # 限流延迟（最后一支不加）
            if i < len(candidates) - 1:
                _time.sleep(1.5)
        print(f"✅ AI 分析完成: {mode} — 成功 {ai_ok}/{len(candidates)}, 失败 {ai_fail}")

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
