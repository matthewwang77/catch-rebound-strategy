#!/usr/bin/env python3
"""
v7 历史模拟回填 — 从 2026-05-01 逐日模拟选股+AI分析+收益验证
================================================================
用 v7 优化参数（BEAR/STRICT/LOOSE），逐日模拟每个交易日：
  1. 重建历史市场环境 → 择模
  2. 截断每只股票数据到当日 → _screen_single_stock()
  3. DeepSeek AI 分析
  4. 写入 signal_tracker.csv + ai_memory.json + results_archive/

不改动现有代码。稳字优先。
"""

import sys, os, json, time, re, csv, traceback
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# ============================================================
# 辅助函数
# ============================================================

def truncate_df_to_date(df, target_date):
    """截断 DataFrame 到 target_date（含当日，不含未来数据）。

    Args:
        df: 含 'date' 列的 DataFrame (date 列已是 datetime 类型)
        target_date: str 'YYYY-MM-DD'
    Returns:
        截断后的 DataFrame 副本
    """
    target = pd.Timestamp(target_date)
    return df[df['date'] <= target].copy()


def _get_index_data_up_to(target_date_str):
    """下载三大指数在 target_date 之前的历史数据。

    Returns:
        dict: {'上证': df, '深证': df, '创业板': df}
        每个 df 以 date 为 index，含 Close 列
    """
    import yfinance as yf

    target_dt = pd.Timestamp(target_date_str)
    start_dt = target_dt - pd.Timedelta(days=45)

    indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
    result = {}
    for name, code in indices.items():
        try:
            df = yf.download(code, start=start_dt.strftime('%Y-%m-%d'),
                           end=(target_dt + pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                           progress=False)
            if df is not None and len(df) >= 2:
                result[name] = df
        except Exception:
            continue
    return result


def get_market_context_historical(target_date_str, index_data=None):
    """重建 target_date 当天的大盘快照字符串，格式与 get_market_context() 一致。

    Args:
        target_date_str: 'YYYY-MM-DD'
        index_data: 可选，预下载的指数数据 dict
    Returns:
        格式化字符串，含指数数据 + 情绪档位
    """
    if index_data is None:
        index_data = _get_index_data_up_to(target_date_str)

    target_dt = pd.Timestamp(target_date_str)
    parts = []
    trends = []

    for name, df in index_data.items():
        df_cut = df[df.index <= target_dt]
        if len(df_cut) < 2:
            parts.append(f"{name}: N/A")
            continue

        close_col = df_cut['Close']
        cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
        prev = float(close_col.iloc[-2].item() if hasattr(close_col.iloc[-2], 'item') else close_col.iloc[-2])
        pct = (cur / prev - 1) * 100
        parts.append(f"{name}: {cur:.0f} ({pct:+.2f}%)")

        if len(df_cut) >= 5:
            close_5d_ago = float(close_col.iloc[-5].item() if hasattr(close_col.iloc[-5], 'item') else close_col.iloc[-5])
            trend_5d = (cur / close_5d_ago - 1) * 100
            trends.append(trend_5d)

    market_str = " | ".join(parts) if parts else "大盘数据获取失败"

    sentiment = ""
    if len(trends) >= 2:
        avg_trend = sum(trends) / len(trends)
        up_count = sum(1 for t in trends if t > 0.5)
        down_count = sum(1 for t in trends if t < -0.5)

        if avg_trend > 3 and up_count >= len(trends):
            gear = "高潮期(5档) — 涨停铺天盖地，短期风险积聚，建议减仓或快进快出"
        elif avg_trend > 1 and up_count >= 2:
            gear = "发酵期(4档) — 涨停数增加势头良好，可适度参与，仓位3-5成"
        elif avg_trend > -0.5:
            gear = "启动期(3档) — 开始回暖零星涨停，谨慎入场，仓位2-3成"
        elif avg_trend > -2:
            gear = "低迷期(2档) — 涨停稀少破位频发，建议减仓或观望，仓位≤1成"
        else:
            gear = "冰点期(1档) — 几乎无涨停普跌，坚决不参与"

        sentiment = f"""5日趋势：{avg_trend:+.1f}%（{up_count}涨{down_count}跌）
市场情绪档位：{gear}"""
    else:
        sentiment = "情绪数据不足"

    return f"""【大盘环境】
{market_str}
{sentiment}"""


def detect_regime_historical(target_date_str, index_data=None):
    """重建 target_date 的市场环境，逻辑与 detect_market_regime() 一致。

    Returns:
        dict: {'regime', 'avg_trend', 'sentiment_tier', 'sentiment_label',
               'recommended_mode', 'up_count', 'down_count'}
    """
    if index_data is None:
        index_data = _get_index_data_up_to(target_date_str)

    target_dt = pd.Timestamp(target_date_str)
    trends = []

    for name, df in index_data.items():
        df_cut = df[df.index <= target_dt]
        if len(df_cut) < 5:
            continue
        close_col = df_cut['Close']
        cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
        close_5d_ago = float(close_col.iloc[-5].item() if hasattr(close_col.iloc[-5], 'item') else close_col.iloc[-5])
        trend_5d = (cur / close_5d_ago - 1) * 100
        trends.append(trend_5d)

    if len(trends) < 2:
        return {'regime': 'neutral', 'avg_trend': 0, 'sentiment_tier': 3,
                'sentiment_label': '数据不足，默认非熊市', 'recommended_mode': 'strict',
                'up_count': 0, 'down_count': 0}

    avg_trend = sum(trends) / len(trends)
    up_count = sum(1 for t in trends if t > 0.5)
    down_count = sum(1 for t in trends if t < -0.5)

    if avg_trend > 3 and up_count >= len(trends):
        tier, label = 5, "高潮期 — 短期风险积聚"
    elif avg_trend > 1 and up_count >= 2:
        tier, label = 4, "发酵期 — 势头良好"
    elif avg_trend > -0.5:
        tier, label = 3, "启动期 — 谨慎入场"
    elif avg_trend > -2:
        tier, label = 2, "低迷期 — 建议观望"
    else:
        tier, label = 1, "冰点期 — 坚决不参与"

    if avg_trend < -0.5:
        regime = 'bear'
        recommended_mode = 'bear'
    elif avg_trend > 1:
        regime = 'neutral'
        recommended_mode = 'loose'
    else:
        regime = 'neutral'
        recommended_mode = 'strict'

    return {
        'regime': regime,
        'avg_trend': round(avg_trend, 2),
        'sentiment_tier': tier,
        'sentiment_label': f"{tier}档: {label}",
        'recommended_mode': recommended_mode,
        'up_count': up_count,
        'down_count': down_count,
    }


# ============================================================
# 测试 (python simulate_v7_from_may.py --test)
# ============================================================

def test_truncate_df_to_date():
    """验证截断函数无未来信息泄露"""
    df = pd.DataFrame({
        'date': pd.to_datetime(['2026-04-28', '2026-04-29', '2026-04-30', '2026-05-01', '2026-05-02']),
        'close': [10, 11, 12, 13, 14],
    })
    result = truncate_df_to_date(df, '2026-04-30')
    assert len(result) == 3, f"Expected 3 rows, got {len(result)}"
    assert result.iloc[-1]['date'] == pd.Timestamp('2026-04-30'), \
        f"Last date should be 2026-04-30, got {result.iloc[-1]['date']}"
    assert '2026-04-30' in str(result.iloc[-1]['date']), "Should include target_date data"
    # 验证不包含未来数据
    assert '2026-05-01' not in result['date'].astype(str).str[:10].values
    print("  ✅ truncate_df_to_date 测试通过")


def test_market_context_today_consistency():
    """验证: target_date=今天时，输出格式与 get_market_context() 兼容"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("screener", os.path.join(BASE, "选股new_v5.py"))
    screener = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screener)

    today = pd.Timestamp.now().strftime('%Y-%m-%d')
    hist_ctx = get_market_context_historical(today)

    assert hist_ctx and len(hist_ctx) > 50, f"Historical context too short ({len(hist_ctx)} chars)"
    # 至少2个指数（创业板399006.SZ yfinance有时拉不到，与live行为一致）
    found = sum(1 for idx_name in ['上证', '深证', '创业板'] if idx_name in hist_ctx)
    assert found >= 2, f"Expected >=2 indices, found {found}. Context: {hist_ctx[:200]}"
    assert '大盘环境' in hist_ctx, "Missing 大盘环境 section"
    assert '情绪档位' in hist_ctx, "Missing 情绪档位"
    print(f"  ✅ get_market_context_historical 格式测试通过 ({len(hist_ctx)} chars)")


def test_detect_regime_historical():
    """验证输出格式与 detect_market_regime() 一致"""
    today = pd.Timestamp.now().strftime('%Y-%m-%d')
    result = detect_regime_historical(today)

    required_keys = ['regime', 'avg_trend', 'sentiment_tier', 'sentiment_label', 'recommended_mode']
    for k in required_keys:
        assert k in result, f"Missing key: {k}"
    assert result['regime'] in ('bear', 'neutral'), f"Invalid regime: {result['regime']}"
    assert isinstance(result['avg_trend'], (int, float)), f"avg_trend should be numeric"
    assert 1 <= result['sentiment_tier'] <= 5, f"tier out of range: {result['sentiment_tier']}"
    assert result['recommended_mode'] in ('bear', 'strict', 'loose'), \
        f"Invalid mode: {result['recommended_mode']}"
    print(f"  ✅ detect_regime_historical 测试通过: {result['sentiment_label']} → {result['recommended_mode']}")


def run_all_tests():
    print("=" * 60)
    print("🧪 运行测试...")
    print("=" * 60)
    test_truncate_df_to_date()
    test_market_context_today_consistency()
    test_detect_regime_historical()
    print("=" * 60)
    print("✅ 全部测试通过！")
    print("=" * 60)


# ============================================================
# AI Memory 读写
# ============================================================

def _load_ai_memory():
    path = os.path.join(BASE, 'ai_memory.json')
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _to_py(obj):
    """递归转换 numpy 类型为 Python 原生类型"""
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _to_py(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_py(v) for v in obj]
    return obj

def _save_ai_memory(memory):
    path = os.path.join(BASE, 'ai_memory.json')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_to_py(memory), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ============================================================
# Task 4: 加载 v7 参数
# ============================================================

def load_v7_params():
    """从 v5_results/ 加载 v7 三套优化参数。

    Returns:
        dict: {'bear': {...}, 'loose': {...}, 'strict': {...}}
    """
    v7_files = {
        'bear': 'v5_results/v5_final_params_20230101_20240630.json',
        'loose': 'v5_results/v5_final_params_20240701_20250630.json',
        'strict': 'v5_results/v5_final_params_20250701_20260430.json',
    }
    params = {}
    for mode, fpath in v7_files.items():
        full_path = os.path.join(BASE, fpath)
        if not os.path.exists(full_path):
            print(f"❌ v7 参数文件不存在: {full_path}")
            sys.exit(1)
        with open(full_path, encoding='utf-8') as f:
            data = json.load(f)
        bp = data['best_params']
        # 补全 v7 JSON 中没有的字段（选股需要但优化不涉及的）
        bp.setdefault('require_oversold', False)
        bp.setdefault('require_low_close', False)
        bp.setdefault('signal_today_yang', True)
        bp.setdefault('signal_volume_expand', 1.2)
        bp.setdefault('min_pullback_days', 2)
        bp.setdefault('max_pullback_days', 20)
        bp.setdefault('ma_stabilize', 10)
        bp.setdefault('volume_compare_days', 3)
        bp.setdefault('min_entity_board_ratio', 0.3)
        for fallback_key, fallback_val in [
            ('volume_shrink_ratio_min', bp.get('volume_shrink_ratio', 0.0) * 0.5),
            ('oversold_decline_threshold', 0.10),
            ('low_close_threshold', 0.5),
        ]:
            if fallback_key not in bp:
                bp[fallback_key] = fallback_val
        params[mode] = bp
        print(f"✅ 加载 v7 {mode}: pullback={bp['pullback_ratio_min']}-{bp['pullback_ratio_max']} "
              f"vol_shrink={bp['volume_shrink_ratio']} min_cons={bp['min_consecutive_limit_up']} "
              f"hold={bp['hold_days']} tp={bp['take_profit']} sl={bp['stop_loss']}")
    return params


# ============================================================
# Task 4b: 预加载 stock_data
# ============================================================

def preload_stock_cache():
    """预加载所有 stock_data/*.csv，返回 {code: DataFrame}。

    DataFrame 列: date (datetime), open, high, low, close, volume
    只加载有足够数据的股票（>=30行）。
    """
    data_dir = os.path.join(BASE, 'stock_data')
    cache_files = sorted([
        f for f in os.listdir(data_dir)
        if f.endswith('.csv') and os.path.getsize(os.path.join(data_dir, f)) > 100
    ])

    all_data = {}
    for fname in cache_files:
        code = fname.replace('.csv', '')
        try:
            df = pd.read_csv(os.path.join(data_dir, fname))
            df.columns = df.columns.str.lower()
            if 'date' not in df.columns:
                continue
            df['date'] = pd.to_datetime(df['date'])
            if len(df) < 30:
                continue
            all_data[code] = df
        except Exception:
            continue

    print(f"预加载: {len(all_data)} 只股票")
    return all_data


# ============================================================
# Task 5: 单日模拟
# ============================================================

def simulate_day(target_date_str, all_data, v7_params, screener, index_data):
    """模拟单个交易日的选股流程。

    Args:
        target_date_str: '2026-05-01'
        all_data: {code: DataFrame (full, not truncated)}
        v7_params: {'bear': {...}, 'loose': {...}, 'strict': {...}}
        screener: 选股new_v5 模块
        index_data: 预下载的指数数据 dict

    Returns:
        dict: {'date', 'mode', 'regime_info', 'candidates'}
    """
    # 1. 确定当日市场环境 → 择模
    regime_info = detect_regime_historical(target_date_str, index_data)
    mode = regime_info['recommended_mode']
    params = v7_params[mode]

    # 2. 备份并设置 PARAMS
    original_params = screener.PARAMS.copy()
    screener.PARAMS.update(params)

    # 3. 预过滤：只有近期出现过涨停的股票才扫描
    target_dt = pd.Timestamp(target_date_str)
    cutoff_dt = target_dt - pd.Timedelta(days=30)

    hot_codes = []
    for code, df in all_data.items():
        try:
            recent = df[(df['date'] >= cutoff_dt) & (df['date'] <= target_dt)]
            if len(recent) < 15:
                continue
            if len(recent) >= 2:
                pct_chg = recent['close'].pct_change() * 100
                if (pct_chg >= 9.5).any():
                    hot_codes.append(code)
        except Exception:
            continue

    print(f"  [{target_date_str}] 预过滤: {len(hot_codes)} 只近期有涨停 (模式={mode})")

    # 4. 逐股截断 + 筛选
    candidates = []
    stats = {
        'total': len(hot_codes), 'has_data': 0, 'has_limit_up': 0,
        'consecutive_ok': 0, 'entity_ratio_ok': 0, 'pullback_days_ok': 0,
        'pullback_range_ok': 0, 'ma_ok': 0, 'volume_shrink_ok': 0,
        'yang_ok': 0, 'volume_expand_ok': 0, 'final': 0,
    }

    for code in hot_codes:
        try:
            df = all_data[code]
            truncated = truncate_df_to_date(df, target_date_str)
            if len(truncated) < 15:
                continue

            # 转换为 _screen_single_stock 期望的格式 (Close/Open/High/Low/Volume)
            stock_df = pd.DataFrame({
                'Close': truncated['close'].values,
                'Open': truncated['open'].values,
                'High': truncated['high'].values,
                'Low': truncated['low'].values,
                'Volume': truncated['volume'].values,
            }, index=truncated['date'].values)

            if len(stock_df.dropna()) < 10:
                continue

            screener._screen_single_stock(code, stock_df, stats, candidates, mode)
        except Exception:
            continue

    # 5. 恢复 PARAMS
    screener.PARAMS.update(original_params)

    print(f"  [{target_date_str}] 选出: {len(candidates)} 只")

    return {
        'date': target_date_str,
        'mode': mode,
        'regime_info': regime_info,
        'candidates': candidates,
    }


# ============================================================
# Task 7: 存储函数
# ============================================================

def save_signal_to_tracker(day_str, candidate, mode):
    """追加一条信号到 signal_tracker.csv（20天内去重）。"""
    from datetime import timedelta

    tracker_path = os.path.join(BASE, 'signal_tracker.csv')

    existing = []
    if os.path.exists(tracker_path):
        with open(tracker_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            existing = list(reader)

    code = candidate['code']
    entry_price = candidate['price']
    signal_date_str = day_str.replace('-', '')

    # 去重: 20天内同 code + entry_price
    cutoff = pd.Timestamp(day_str) - timedelta(days=20)
    for row in existing:
        if len(row) >= 3 and row[2] == code:
            try:
                row_date = pd.Timestamp(row[0])
                row_price = float(row[4])
                if row_date >= cutoff and abs(row_price - entry_price) < 0.01:
                    return  # 重复
            except (ValueError, IndexError):
                pass

    new_row = [
        signal_date_str,
        str(candidate.get('signal_date', '')),
        code,
        mode,
        str(entry_price),
        str(candidate.get('pullback_pct', 0)),
        str(candidate.get('limit_days', 0)),
        '',
        '',
    ]
    existing.append(new_row)

    with open(tracker_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'signal_date', 'code', 'mode', 'entry_price',
                        'pullback_pct', 'limit_days', 'name', 'sector'])
        writer.writerows(existing)


def save_day_result_json(day_str, result):
    """保存当日结果到 results_archive/{YYYYMMDD}.json（兼容 auto_daily 格式）。"""
    archive_dir = os.path.join(BASE, 'results_archive')
    os.makedirs(archive_dir, exist_ok=True)

    date_compact = day_str.replace('-', '')

    output = {
        "scan_time": f"{day_str} 15:00",
        "scan_date": date_compact,
        "market": {},
        "regime": {
            "status": result['regime_info'].get('regime', 'neutral'),
            "label": result['regime_info'].get('sentiment_label', ''),
            "avg_trend": result['regime_info'].get('avg_trend', 0),
            "recommended_mode": result['mode'],
        },
        "modes": {
            result['mode']: {
                "count": len(result['candidates']),
                "candidates": [
                    {
                        "code": c['code'],
                        "price": c['price'],
                        "signal_date": c.get('signal_date', ''),
                        "pullback_pct": c.get('pullback_pct', 0),
                        "limit_days": c.get('limit_days', 0),
                        "entity_ratio": c.get('entity_ratio', 0),
                    }
                    for c in result['candidates']
                ],
            }
        },
    }

    path = os.path.join(archive_dir, f"{date_compact}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


# ============================================================
# Task 6: AI 分析（复制 auto_daily._run_ai_analysis 逻辑）
# ============================================================

def run_ai_analysis_historical(code, stock_df, candidate, market_context, mode,
                                scan_date_str, ai_memory, screener_mod):
    """对历史日期的候选股调用 DeepSeek API 分析。

    与 auto_daily._run_ai_analysis() 逻辑一致。
    """
    import requests

    signal_date_str = str(candidate.get('signal_date', ''))
    entry_price = float(candidate.get('price', 0))
    pullback_pct = float(candidate.get('pullback_pct', 0))
    limit_days = int(candidate.get('limit_days', 0))

    # 去重
    if code in ai_memory:
        for rec in ai_memory[code]:
            if rec.get("date") == scan_date_str:
                return None

    # 列名兼容
    if 'close' in stock_df.columns and 'Close' not in stock_df.columns:
        stock_df = stock_df.rename(columns={
            'open': 'Open', 'high': 'High', 'low': 'Low',
            'close': 'Close', 'volume': 'Volume'
        })

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

    if len(close) < 5:
        return None

    # 基础指标
    current_price = _s(close.iloc[-1])
    pct_chg = (current_price / _s(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
    ma5 = _s(close.rolling(5).mean().iloc[-1])
    ma10 = _s(close.rolling(10).mean().iloc[-1])
    ma20_val = _s(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else ma10
    vol_today = _s(volume.iloc[-1])
    vol_ma5 = _s(volume.rolling(5).mean().iloc[-1])
    recent_high_20 = _s(high.tail(20).max())

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
- 最新价：{current_price:.2f}（今日 {pct_chg:+.2f}%）| 均线：MA5={ma5:.2f} MA10={ma10:.2f} MA20={ma20_val:.2f}
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

    prompt = f"""{technical_data}

{market_context}

请按"量价形时"框架逐项分析，每项给出具体判断，最后给出：
- 反弹概率：低(≤30%) / 中(30-60%) / 高(≥60%)
- 仓位建议：X成仓（情绪档位）
- 最终结论：【参与 / 观望 / 放弃】"""

    try:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            print(f"    ⚠️ {code} AI 跳过: API Key 未配置")
            return None

        api_url = screener_mod.DEEPSEEK_API_URL

        max_retries = 2
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
                break
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    time.sleep(3)
            except requests.exceptions.ConnectionError:
                if attempt < max_retries - 1:
                    time.sleep(3)
        else:
            print(f"    ⚠️ {code} AI API 超时/连接失败（重试{max_retries}次）")
            return None

        if resp.status_code != 200:
            print(f"    ⚠️ {code} AI API HTTP {resp.status_code}")
            return None
        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            return None
        analysis_text = data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    ⚠️ {code} AI 异常: {e}")
        return None

    # 正则提取关键字段
    sentiment = ""
    position = ""
    opinion = ""
    try:
        m = re.search(r'仓位建议[：:]\s*(.+?)（(.+?)）', analysis_text)
        if m:
            position = m.group(1).strip().strip('*')
            sentiment = m.group(2).strip().strip('*')
        if not sentiment:
            sm = re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', analysis_text)
            if sm:
                sentiment = sm.group(1).strip().strip('*')
        for prefix in ['情绪档位：', '情绪档位:', '情绪档位']:
            if sentiment.startswith(prefix):
                sentiment = sentiment[len(prefix):].strip()
        om = re.search(r'最终结论[：:]\s*(.+?)(?:\n|$)', analysis_text)
        if om:
            opinion = om.group(1).strip().strip('*')
    except Exception:
        pass

    return {
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
    }


# ============================================================
# Task 9: main() — 完整模拟流程
# ============================================================

def main():
    print("=" * 70)
    print("🚀 v7 历史模拟回填 — 2026-05-01 → 2026-06-15")
    print("=" * 70)

    # ── 加载模块 ──
    print("\n📦 加载模块...")
    import importlib.util
    spec = importlib.util.spec_from_file_location("screener", os.path.join(BASE, "选股new_v5.py"))
    screener = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screener)
    print("✅ screener (选股new_v5) 加载完成")

    # ── 加载 v7 参数 ──
    v7_params = load_v7_params()

    # ── 预加载数据 ──
    all_data = preload_stock_cache()
    if len(all_data) < 1000:
        print(f"❌ 数据不足：仅 {len(all_data)} 只股票")
        sys.exit(1)

    # ── 交易日列表 ──
    trading_days = pd.bdate_range('2026-05-01', '2026-06-15')
    print(f"\n📅 交易日: {len(trading_days)} 天 ({trading_days[0].date()} ~ {trading_days[-1].date()})")

    # ── 预下载全时段指数数据（避免每天重复下载）──
    print("\n📊 预下载指数数据...")
    import yfinance as yf
    index_start = (trading_days[0] - pd.Timedelta(days=45)).strftime('%Y-%m-%d')
    index_end = (trading_days[-1] + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    index_data = {}
    for name, code in [("上证", "000001.SS"), ("深证", "399001.SZ"), ("创业板", "399006.SZ")]:
        try:
            df = yf.download(code, start=index_start, end=index_end, progress=False)
            if df is not None and len(df) >= 2:
                index_data[name] = df
                print(f"  ✅ {name}: {len(df)} 条")
            else:
                print(f"  ⚠️ {name}: 无数据")
        except Exception as e:
            print(f"  ⚠️ {name}: {e}")

    if len(index_data) < 2:
        print("❌ 指数数据不足，无法继续")
        sys.exit(1)

    # ── 加载 AI Memory ──
    ai_memory = _load_ai_memory()

    # ── 主循环 ──
    all_results = {}

    for day_idx, day in enumerate(trading_days):
        day_str = day.strftime('%Y-%m-%d')
        print(f"\n{'─'*50}")
        print(f"📅 [{day_idx+1}/{len(trading_days)}] {day_str}")
        print(f"{'─'*50}")

        # 筛选
        result = simulate_day(day_str, all_data, v7_params, screener, index_data)
        all_results[day_str] = result

        if not result['candidates']:
            print(f"  💤 无候选，跳过 AI 分析")
            # 仍然保存空结果 JSON
            save_day_result_json(day_str, result)
            continue

        # AI 分析
        print(f"  🤖 开始 AI 分析 ({len(result['candidates'])} 只)...")
        for i, cand in enumerate(result['candidates']):
            code = cand['code']
            # 准备截断后的 stock_df 给 AI 分析
            df = all_data.get(code)
            if df is None:
                continue
            truncated = truncate_df_to_date(df, day_str)
            stock_df_for_ai = pd.DataFrame({
                'Close': truncated['close'].values,
                'Open': truncated['open'].values,
                'High': truncated['high'].values,
                'Low': truncated['low'].values,
                'Volume': truncated['volume'].values,
            }, index=truncated['date'].values)

            market_ctx = get_market_context_historical(day_str, index_data)

            record = run_ai_analysis_historical(
                code, stock_df_for_ai, cand, market_ctx,
                result['mode'], day_str.replace('-', ''), ai_memory, screener
            )

            if record:
                if code not in ai_memory:
                    ai_memory[code] = []
                ai_memory[code].append(record)
                _save_ai_memory(ai_memory)
                print(f"    ✅ {code} AI 分析完成 ({i+1}/{len(result['candidates'])})")

            if i < len(result['candidates']) - 1:
                time.sleep(1.5)  # API 速率限制

        # 保存信号
        for cand in result['candidates']:
            save_signal_to_tracker(day_str, cand, result['mode'])

        # 保存当日 JSON
        save_day_result_json(day_str, result)

    # ── 事后收益验证 (Task 8) ──
    print(f"\n{'='*70}")
    print("💰 事后收益验证 (>7天前的信号)")
    print(f"{'='*70}")

    # 加载 backfill_signals 的收益计算函数
    spec_bf = importlib.util.spec_from_file_location("backfill", os.path.join(BASE, "backfill_signals.py"))
    backfill = importlib.util.module_from_spec(spec_bf)
    spec_bf.loader.exec_module(backfill)

    verify_count = 0
    for code, records in ai_memory.items():
        for rec in records:
            if rec.get('verified'):
                continue
            try:
                rec_date = pd.to_datetime(rec['date'], format='%Y%m%d')
            except (ValueError, KeyError):
                continue

            days_ago = (pd.Timestamp.now() - rec_date).days
            if days_ago < 7:
                continue

            # 计算7日收益
            mode = rec.get('mode', 'strict')
            params = v7_params.get(mode, v7_params['strict'])

            try:
                ret = backfill.check_return_v5_local(
                    code=code,
                    signal_date=rec.get('signal_date', rec['date']),
                    entry_price=rec.get('entry_price', 0),
                    hold_days=7,
                    take_profit=params['take_profit'],
                    stop_loss=params['stop_loss'],
                    data_dir=os.path.join(BASE, 'stock_data'),
                )

                if ret:
                    rec['return_7d'] = round(ret['return_pct'], 2)
                    rec['exit_reason'] = ret.get('exit_reason', '')
                    rec['exit_day'] = ret.get('exit_day', 0)
                    rec['verified'] = True

                    # 裁决
                    opinion = rec.get('opinion', '')
                    r7 = rec['return_7d']
                    if any(kw in opinion for kw in ['参与', '买入']):
                        rec['verdict'] = 'correct' if r7 > 0 else 'wrong'
                    elif any(kw in opinion for kw in ['放弃', '规避']):
                        rec['verdict'] = 'avoided' if r7 <= 0 else 'missed'
                    else:
                        rec['verdict'] = 'noted_up' if r7 > 0 else 'noted_down'

                    verify_count += 1
                    print(f"  ✅ {code} {rec['date']}: return_7d={r7:+.1f}% verdict={rec['verdict']}")
            except Exception as e:
                print(f"  ⚠️ {code} {rec.get('date', '?')} 收益计算失败: {e}")

    _save_ai_memory(ai_memory)
    print(f"\n✅ 收益验证完成: {verify_count} 条")

    # ── 更新 latest_scan_results.json ──
    last_day = trading_days[-1].strftime('%Y-%m-%d')
    if last_day in all_results:
        last_result = all_results[last_day]
        date_compact = last_day.replace('-', '')
        latest_output = {
            "scan_time": f"{last_day} 15:00",
            "scan_date": date_compact,
            "market": {},
            "regime": {
                "status": last_result['regime_info'].get('regime', 'neutral'),
                "label": last_result['regime_info'].get('sentiment_label', ''),
                "avg_trend": last_result['regime_info'].get('avg_trend', 0),
                "recommended_mode": last_result['mode'],
            },
            "modes": {
                last_result['mode']: {
                    "count": len(last_result['candidates']),
                    "candidates": [
                        {
                            "code": c['code'],
                            "price": c['price'],
                            "signal_date": c.get('signal_date', ''),
                            "pullback_pct": c.get('pullback_pct', 0),
                            "limit_days": c.get('limit_days', 0),
                            "entity_ratio": c.get('entity_ratio', 0),
                        }
                        for c in last_result['candidates']
                    ],
                }
            },
        }
        latest_path = os.path.join(BASE, 'latest_scan_results.json')
        with open(latest_path, 'w', encoding='utf-8') as f:
            json.dump(latest_output, f, ensure_ascii=False, indent=2)
        print(f"📁 latest_scan_results.json 更新 ({last_day}, {len(last_result['candidates'])} 只)")

    # ── 汇总 ──
    total_candidates = sum(len(r['candidates']) for r in all_results.values())
    days_with_signals = sum(1 for r in all_results.values() if len(r['candidates']) > 0)
    total_ai = sum(len(recs) for recs in ai_memory.values())

    print(f"\n{'='*70}")
    print(f"🏁 v7 历史模拟完成！")
    print(f"  交易日: {len(trading_days)}")
    print(f"  有信号的天数: {days_with_signals}")
    print(f"  总候选: {total_candidates}")
    print(f"  AI 分析: {total_ai} 条")
    print(f"  收益验证: {verify_count} 条")
    print(f"{'='*70}")


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    if '--test' in sys.argv:
        run_all_tests()
    else:
        main()
