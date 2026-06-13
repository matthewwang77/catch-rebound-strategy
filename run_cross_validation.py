#!/usr/bin/env python3
"""
3×3 交叉验证矩阵
================
加载三个时段的最优参数，在每个时段的事件上回测，构建交叉验证矩阵。
输出：
  v5_results/v5_cross_validation_matrix.json  — 3×3 矩阵
  v5_results/v5_regime_adaptation_report.json  — 最终报告 + 建议
"""

import sys, os, json, time, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util
spec = importlib.util.spec_from_file_location("screener", "选股new_v5.py")
screener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screener)

extract_all_events = screener.extract_all_events
evaluate_params_on_events = screener.evaluate_params_on_events
load_from_cache = screener.load_from_cache
get_limit_threshold = screener.get_limit_threshold
calculate_v4_metrics = screener.calculate_v4_metrics
DATA_DIR = screener.DATA_DIR
OUTPUT_DIR = screener.OUTPUT_DIR

PERIODS = {
    'A': ('20230101', '20240630', '震荡下行（熊市）'),
    'B': ('20240701', '20250630', '牛市大涨'),
    'C': ('20250701', '20260430', '震荡回调'),
}


def load_best_params(period_name):
    """加载某个时段的最优参数"""
    start, end, _ = PERIODS[period_name]
    path = os.path.join(OUTPUT_DIR, f'v5_final_params_{start}_{end}.json')
    if not os.path.exists(path):
        print(f"⚠️ 参数文件不存在: {path}")
        return None
    with open(path) as f:
        data = json.load(f)
    return data['best_params']


def extract_period_events(period_name):
    """为某个时段预提取事件"""
    start, end, label = PERIODS[period_name]
    print(f"  提取 {period_name} 事件 ({label})...")

    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    hot_codes = []
    for fname in cache_files:
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 50: continue
        df_period = df[(df['trade_date'] >= start) & (df['trade_date'] <= end)]
        if len(df_period) == 0: continue
        limit_threshold = get_limit_threshold(code)
        if (df_period['pct_chg'] >= limit_threshold).any():
            hot_codes.append(code)

    events = extract_all_events(hot_codes, start, end, min_series_len=2)
    return events, hot_codes


def evaluate_params(events, params, label=""):
    """在给定事件集上评估参数，返回关键指标"""
    signals_df, metrics, score = evaluate_params_on_events(events, params, min_signals=5)
    if signals_df is None:
        return {'win_rate': None, 'avg_return': None, 'sharpe': None,
                'signal_count': 0, 'score': None, 'total_return': None,
                'profit_factor': None, 'max_dd': None}
    return {
        'win_rate': round(float(signals_df['return'].gt(0).mean()), 4),
        'avg_return': round(float(signals_df['return'].mean()), 4),
        'sharpe': round(float(metrics.get('sharpe', 0)), 2),
        'sortino': round(float(metrics.get('sortino', 0)), 2),
        'signal_count': len(signals_df),
        'score': round(float(score), 4),
        'total_return': round(float(signals_df['return'].sum()), 4),
        'profit_factor': round(float(metrics.get('profit_factor', 0)), 2),
        'max_dd': round(float(metrics.get('max_dd', 0)), 2),
    }


def main():
    print("=" * 70)
    print("🔬 3×3 交叉验证矩阵")
    print("=" * 70)

    # ── Step 1: 加载所有参数 ──
    print("\n📂 加载参数集...")
    all_params = {}
    for p_name in ['A', 'B', 'C']:
        params = load_best_params(p_name)
        if params is None:
            print(f"  ❌ {p_name} 参数加载失败！")
            sys.exit(1)
        all_params[p_name] = params
        pullback = f"回调{params['pullback_ratio_min']:.0%}-{params['pullback_ratio_max']:.0%}"
        print(f"  ✅ {p_name}: {pullback} | "
              f"缩量{params['volume_shrink_ratio']:.0%} | "
              f"连板≥{params['min_consecutive_limit_up']} | "
              f"持有{params['hold_days']}天 | "
              f"TP{params['take_profit']:.1%} SL{params['stop_loss']:.1%}")

    # ── Step 2: 提取各时段事件 ──
    print("\n📊 提取各时段事件...")
    all_events = {}
    for p_name in ['A', 'B', 'C']:
        events, hot_codes = extract_period_events(p_name)
        all_events[p_name] = events
        print(f"  ✅ {p_name}: {len(hot_codes)} 只涨停股 → {len(events)} 个回调事件")

    # ── Step 3: 3×3 交叉评估 ──
    print("\n" + "=" * 70)
    print("🧪 3×3 交叉评估（行=参数集, 列=测试时段）")
    print("=" * 70)

    matrix = {}
    for param_name in ['A', 'B', 'C']:
        matrix[param_name] = {}
        for test_period in ['A', 'B', 'C']:
            _, _, label = PERIODS[test_period]
            print(f"\n  评估: {param_name}参数 → {test_period}时段 ({label})...")
            result = evaluate_params(all_events[test_period], all_params[param_name])
            matrix[param_name][test_period] = result
            if result['win_rate'] is not None:
                print(f"    胜率{result['win_rate']:.1%} | "
                      f"均收益{result['avg_return']:+.1%} | "
                      f"夏普{result['sharpe']:.1f} | "
                      f"信号{result['signal_count']} | "
                      f"评分{result['score']:.4f}")
            else:
                print(f"    ❌ 信号不足")

    # ── Step 4: 分析 ──
    print("\n" + "=" * 70)
    print("📊 分析结果")
    print("=" * 70)

    # 4a. 对角线（原地表现）
    print("\n🏠 原地表现（对角线上，参数在自己时段的表现）：")
    for p_name in ['A', 'B', 'C']:
        r = matrix[p_name][p_name]
        print(f"  {p_name}参数在{p_name}时段: "
              f"胜率{r['win_rate']:.1%} | 夏普{r['sharpe']:.1f} | 信号{r['signal_count']}")

    # 4b. 参数敏感度：A参数在ABC的表现差异
    print("\n📐 参数集敏感度（同一个参数集在不同时段的变异系数）：")
    for p_name in ['A', 'B', 'C']:
        sharpes = [matrix[p_name][p]['sharpe'] for p in ['A', 'B', 'C']
                   if matrix[p_name][p]['sharpe'] is not None]
        if len(sharpes) >= 2:
            cv = np.std(sharpes) / abs(np.mean(sharpes)) if abs(np.mean(sharpes)) > 0.01 else 999
            print(f"  {p_name}参数: Sharpe变异系数 {cv:.2f} | 各期Sharpe: {sharpes}")

    # 4c. 最佳匹配
    print("\n🎯 最佳参数-时段匹配：")
    for test_p in ['A', 'B', 'C']:
        best_param = max(['A', 'B', 'C'],
                         key=lambda p: matrix[p][test_p]['sharpe']
                         if matrix[p][test_p]['sharpe'] is not None else -999)
        r = matrix[best_param][test_p]
        print(f"  {test_p}时段: 最佳参数={best_param} (夏普{r['sharpe']:.1f}, 胜率{r['win_rate']:.1%})")

    # 4d. 关键问题：A参数能救熊市吗？
    print("\n" + "─" * 70)
    print("🔑 关键问题：熊市能救吗？")
    print("─" * 70)
    a_in_a = matrix['A']['A']
    b_in_a = matrix['B']['A']
    c_in_a = matrix['C']['A']

    print(f"  默认参数(B)在熊市: 夏普{b_in_a['sharpe']:.1f}, 胜率{b_in_a['win_rate']:.1%}")
    print(f"  熊市参数(A)在熊市: 夏普{a_in_a['sharpe']:.1f}, 胜率{a_in_a['win_rate']:.1%}")

    if a_in_a['sharpe'] is not None and a_in_a['sharpe'] > 0:
        improvement = a_in_a['sharpe'] - (b_in_a['sharpe'] if b_in_a['sharpe'] is not None else 0)
        if improvement > 1:
            print(f"  ✅ 结论：熊市参数显著改善！夏普提升 {improvement:+.1f}")
            print(f"     熊市不是无解的——需要专属参数（浅回调+极度缩量+快进快出）")
            conclusion = "market_adaptive"
        else:
            print(f"  🟡 结论：熊市参数有改善但不大。建议保守处理。")
            conclusion = "cautious"
    else:
        print(f"  ❌ 结论：即使专属参数也无法在熊市盈利。熊市应空仓。")
        conclusion = "bear_sit_out"

    # 4e. 牛市是否需要不同参数
    print("\n" + "─" * 70)
    print("🔑 关键问题：牛市需要更松的参数吗？")
    print("─" * 70)
    b_in_b = matrix['B']['B']
    a_in_b = matrix['A']['B']
    print(f"  牛市参数(B)在牛市: 夏普{b_in_b['sharpe']:.1f}, 胜率{b_in_b['win_rate']:.1%}, 信号{b_in_b['signal_count']}")
    print(f"  熊市参数(A)在牛市: 夏普{a_in_b['sharpe']:.1f}, 胜率{a_in_b['win_rate']:.1%}, 信号{a_in_b['signal_count']}")

    # 4f. 统一参数 vs 自适应参数
    print("\n" + "─" * 70)
    print("🔑 模拟：统一参数 vs 市场自适应参数")
    print("─" * 70)

    # 统一参数（用B参数代表，因为原来默认优化就是牛市附近）
    unified = {
        'A': matrix['B']['A']['sharpe'] if matrix['B']['A']['sharpe'] is not None else -99,
        'B': matrix['B']['B']['sharpe'] if matrix['B']['B']['sharpe'] is not None else -99,
        'C': matrix['B']['C']['sharpe'] if matrix['B']['C']['sharpe'] is not None else -99,
    }
    # 自适应参数（每个时段用自己的最佳参数）
    adaptive = {
        'A': matrix['A']['A']['sharpe'] if matrix['A']['A']['sharpe'] is not None else -99,
        'B': max(matrix[p]['B']['sharpe'] for p in ['A', 'B', 'C']
                 if matrix[p]['B']['sharpe'] is not None),
        'C': max(matrix[p]['C']['sharpe'] for p in ['A', 'B', 'C']
                 if matrix[p]['C']['sharpe'] is not None),
    }
    adaptive_params = {
        'A': 'A',
        'B': max(['A', 'B', 'C'], key=lambda p: matrix[p]['B']['sharpe']
                 if matrix[p]['B']['sharpe'] is not None else -999),
        'C': max(['A', 'B', 'C'], key=lambda p: matrix[p]['C']['sharpe']
                 if matrix[p]['C']['sharpe'] is not None else -999),
    }

    print(f"  统一参数（B）: A={unified['A']:.1f}, B={unified['B']:.1f}, C={unified['C']:.1f}  "
          f"均值={np.mean(list(unified.values())):.1f}")
    print(f"  自适应参数:    A={adaptive['A']:.1f}, B={adaptive['B']:.1f}, C={adaptive['C']:.1f}  "
          f"均值={np.mean(list(adaptive.values())):.1f}")
    print(f"  自适应参数来源: A→{adaptive_params['A']}参数, "
          f"B→{adaptive_params['B']}参数, "
          f"C→{adaptive_params['C']}参数")

    if np.mean(list(adaptive.values())) > np.mean(list(unified.values())):
        print(f"  ✅ 自适应参数优于统一参数！均夏普提升 {np.mean(list(adaptive.values())) - np.mean(list(unified.values())):+.1f}")
    else:
        print(f"  ⚠️ 自适应参数未优于统一参数。可能不需要做市场切换。")

    # ── Step 5: 生成推荐配置 ──
    print("\n" + "=" * 70)
    print("📋 推荐的市场自适应配置")
    print("=" * 70)

    # 根据最佳匹配推荐
    recommendation = {
        'conclusion': conclusion,
        'adaptive_params_map': adaptive_params,
        'matrix': {},
        'recommended_modes': {},
    }

    for p_name in ['A', 'B', 'C']:
        best_p = adaptive_params[p_name]
        rec_params = all_params[best_p]
        start, end, label = PERIODS[p_name]
        recommendation['recommended_modes'][p_name] = {
            'period': f'{start}_{end}',
            'label': label,
            'use_params_from': best_p,
            'params': rec_params,
        }
        # 简化矩阵
        recommendation['matrix'][p_name] = {
            f'tested_with_{tp}_params': {
                'win_rate': matrix[tp][p_name]['win_rate'],
                'sharpe': matrix[tp][p_name]['sharpe'],
                'avg_return': matrix[tp][p_name]['avg_return'],
                'signal_count': matrix[tp][p_name]['signal_count'],
            }
            for tp in ['A', 'B', 'C']
        }

    # 完整矩阵
    full_matrix = {}
    for param_name in ['A', 'B', 'C']:
        full_matrix[f'params_{param_name}'] = {}
        for test_p in ['A', 'B', 'C']:
            full_matrix[f'params_{param_name}'][f'test_{test_p}'] = matrix[param_name][test_p]

    output = {
        'experiment': '3x3 Cross-Validation Matrix',
        'periods': {k: {'range': f'{v[0]}_{v[1]}', 'label': v[2]} for k, v in PERIODS.items()},
        'params': {p: all_params[p] for p in ['A', 'B', 'C']},
        'full_matrix': full_matrix,
        'analysis': {
            'conclusion': conclusion,
            'adaptive_sharpe_mean': round(np.mean(list(adaptive.values())), 2),
            'unified_sharpe_mean': round(np.mean(list(unified.values())), 2),
            'adaptive_better': np.mean(list(adaptive.values())) > np.mean(list(unified.values())),
        },
        'recommendation': recommendation,
    }

    # 保存
    matrix_path = os.path.join(OUTPUT_DIR, 'v5_cross_validation_matrix.json')
    with open(matrix_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 交叉验证矩阵已保存至 {matrix_path}")

    report_path = os.path.join(OUTPUT_DIR, 'v5_regime_adaptation_report.json')
    with open(report_path, 'w') as f:
        json.dump(recommendation, f, indent=2, ensure_ascii=False)
    print(f"✅ 市场自适应报告已保存至 {report_path}")

    # ── Step 6: 输出可复制的模式配置 ──
    print("\n" + "=" * 70)
    print("📝 可复制到 SCREEN_MODES 的配置：")
    print("=" * 70)
    for p_name in ['A', 'B', 'C']:
        params = all_params[adaptive_params[p_name]]
        _, _, label = PERIODS[p_name]
        mode_name = {'A': 'bear', 'B': 'bull', 'C': 'choppy'}[p_name]
        print(f"""
    # {label}
    "{mode_name}": {{
        "min_consecutive_limit_up": {params['min_consecutive_limit_up']},
        "min_entity_board_ratio": {params['min_entity_board_ratio']},
        "pullback_ratio_min": {params['pullback_ratio_min']},
        "pullback_ratio_max": {params['pullback_ratio_max']},
        "volume_shrink_ratio": {params['volume_shrink_ratio']},
        "volume_shrink_ratio_min": {params['volume_shrink_ratio_min']},
        "take_profit": {params['take_profit']},
        "stop_loss": {params['stop_loss']},
        "hold_days": {params['hold_days']},
        "require_oversold": False,
        "require_low_close": False,
    }},""")

    print("\n" + "=" * 70)
    print("🏁 交叉验证完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
