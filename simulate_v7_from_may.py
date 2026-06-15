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
# 主入口
# ============================================================

if __name__ == "__main__":
    if '--test' in sys.argv:
        run_all_tests()
    else:
        print("Usage: python simulate_v7_from_may.py --test  (run tests)")
        print("       python simulate_v7_from_may.py         (run full simulation — NOT YET IMPLEMENTED)")
        sys.exit(1)
