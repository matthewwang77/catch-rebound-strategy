#!/usr/bin/env python3
"""
通用深度优化脚本 — 对任意时段跑增强版三阶段参数搜索。
用法: python run_deep_optimization.py <start_date> <end_date> [label]

不动 选股new_v5.py 一行代码，直接 import 共享函数。
网格比默认版本密 ~50%，预计总耗时 25-40 分钟。
"""

import sys, os, json, time, warnings
import numpy as np
import pandas as pd
from itertools import product

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
cluster_top_params = screener.cluster_top_params
DATA_DIR = screener.DATA_DIR
OUTPUT_DIR = screener.OUTPUT_DIR


def run_stage_coarse_deep(all_events, start_date, end_date):
    print("\n" + "=" * 70)
    print("🔍 STAGE 1 [ENHANCED]: Deep Coarse Grid Search")
    print("=" * 70)

    param_grid = {
        "min_consecutive_limit_up": [2, 3],
        "min_entity_board_ratio": [0.2, 0.4, 0.6],
        "pullback_ratio_min": [0.03, 0.07, 0.11, 0.15],
        "pullback_ratio_max": [0.12, 0.22, 0.32, 0.42],
        "volume_shrink_ratio": [0.20, 0.40, 0.60, 0.80],
        "volume_shrink_ratio_min": [0.0, 0.05, 0.10],
        "take_profit": [0.03, 0.06, 0.09, 0.12],
        "stop_loss": [-0.04, -0.08, -0.12, -0.16],
        "hold_days": [3, 5, 7, 10],
        "require_oversold": [False],
        "require_low_close": [False],
    }

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combinations = list(product(*values))
    total_combos = len(all_combinations)
    size = 1
    for v in values: size *= len(v)
    print(f"参数网格: {' × '.join(str(len(v)) for v in values)} = {size}")
    print(f"预计耗时: ~{total_combos * 0.007 / 60:.0f} 分钟\n")

    results_list, best_score, best_params, best_signals = [], -999, None, None
    start_time = time.time()

    for i, combo in enumerate(all_combinations):
        params_dict = dict(zip(keys, combo))
        signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)
        if signals_df is None: continue
        results_list.append({**params_dict, **metrics})
        if score > best_score:
            best_score, best_params, best_signals = score, params_dict.copy(), signals_df.copy()
        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
            print(f"  [{i+1}/{total_combos} {((i+1)/total_combos)*100:.0f}%] "
                  f"剩余 {remaining/60:.0f}min | 最佳: {best_score:.4f} "
                  f"(WR {best_signals['return'].gt(0).sum()/len(best_signals):.0%})")

    total_time = time.time() - start_time
    print(f"\n✅ Stage 1 完成！耗时: {total_time/60:.1f} 分钟 | 有效: {len(results_list)} | 最佳: {best_score:.4f}")
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(OUTPUT_DIR, f'v5_stage1_coarse_{start_date}_{end_date}.csv'),
                      index=False, encoding='utf-8-sig')
    display_cols = ['win_rate', 'avg_return', 'signal_count', 'sharpe', 'score'] + keys
    print(f"\nStage 1 Top-10:\n{df_results.head(10)[display_cols].to_string()}")
    return df_results, best_params, best_signals


def run_stage_fine_deep(all_events, stage1_results, start_date, end_date):
    print("\n" + "=" * 70)
    print("🔍 STAGE 2 [ENHANCED]: Deep Fine Grid Search")
    print("=" * 70)

    clusters = cluster_top_params(stage1_results, top_n=80, n_clusters=5)
    all_combinations, seen_combos = [], set()
    MAX_STAGE2_COMBOS = 80000

    for cluster in clusters[:3]:
        sr, center = cluster['search_ranges'], cluster['center']
        fixed_params = {
            'min_consecutive_limit_up': int(center.get('min_consecutive_limit_up', 2)),
            'require_oversold': False, 'require_low_close': False,
            'volume_shrink_ratio_min': center.get('volume_shrink_ratio_min', 0.0),
        }
        fine_grid = {}
        for p in ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
                   'take_profit', 'stop_loss']:
            if p in sr:
                p_min, p_max = sr[p]['min'], sr[p]['max']
                step = 0.003 if p in ['take_profit', 'stop_loss'] else 0.005
                n_steps = max(4, min(8, int((p_max - p_min) / step) + 1))
                fine_grid[p] = sorted(list(set([
                    round(p_min + i * (p_max - p_min) / (n_steps - 1), 3)
                    for i in range(n_steps)])))
        fine_grid['hold_days'] = sorted(list(set([
            max(2, min(12, int(center.get('hold_days', 7)) + d))
            for d in [-2, -1, 0, 1, 2]])))
        fine_grid['min_entity_board_ratio'] = sorted(list(set([
            max(0.1, min(0.7, round(center.get('min_entity_board_ratio', 0.4) + d, 2)))
            for d in [-0.15, -0.05, 0, 0.05, 0.15]])))
        keys, values = list(fine_grid.keys()), list(fine_grid.values())
        for combo in product(*values):
            if len(all_combinations) >= MAX_STAGE2_COMBOS: break
            params_dict = dict(zip(keys, combo))
            params_dict.update(fixed_params)
            combo_key = str(sorted(params_dict.items()))
            if combo_key not in seen_combos:
                seen_combos.add(combo_key)
                all_combinations.append(params_dict)

    total_combos = len(all_combinations)
    print(f"合并后组合数: {total_combos} | 预计耗时: ~{total_combos * 0.007 / 60:.0f} 分钟\n")

    results_list, best_score, best_params, best_signals = [], -999, None, None
    start_time = time.time()
    for i, params_dict in enumerate(all_combinations):
        signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)
        if signals_df is None: continue
        results_list.append({**params_dict, **metrics})
        if score > best_score:
            best_score, best_params, best_signals = score, params_dict.copy(), signals_df.copy()
        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
            print(f"  [{i+1}/{total_combos} {((i+1)/total_combos)*100:.0f}%] "
                  f"剩余 {remaining/60:.0f}min | 最佳: {best_score:.4f}")

    total_time = time.time() - start_time
    print(f"\n✅ Stage 2 完成！耗时: {total_time/60:.1f} 分钟")
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(OUTPUT_DIR, f'v5_stage2_fine_{start_date}_{end_date}.csv'),
                      index=False, encoding='utf-8-sig')
    return df_results, best_params, best_signals


def run_stage_ultrafine_deep(all_events, stage2_results, start_date, end_date):
    print("\n" + "=" * 70)
    print("🔍 STAGE 3 [ENHANCED]: Deep Ultra-Fine Grid Search")
    print("=" * 70)

    top10 = stage2_results.head(10)
    all_combinations, seen_combos = [], set()
    MAX_STAGE3_COMBOS = 50000

    for _, row in top10.iterrows():
        center = row.to_dict()
        fixed_params = {
            'min_consecutive_limit_up': int(center.get('min_consecutive_limit_up', 2)),
            'require_oversold': False, 'require_low_close': False,
            'volume_shrink_ratio_min': center.get('volume_shrink_ratio_min', 0.0),
        }
        ultrafine_grid = {}
        for p, margin in [('pullback_ratio_min', 0.025), ('pullback_ratio_max', 0.035),
                           ('volume_shrink_ratio', 0.035)]:
            base = center.get(p, 0)
            vals = [round(base + d, 2) for d in np.arange(-margin, margin + 0.005, 0.01)]
            ultrafine_grid[p] = sorted(list(set([max(0.01, v) for v in vals])))
        for p, margin in [('take_profit', 0.015), ('stop_loss', 0.020)]:
            base = center.get(p, 0)
            vals = [round(base + d, 3) for d in np.arange(-margin, margin + 0.003, 0.005)]
            ultrafine_grid[p] = sorted(list(set(vals)))
        ultrafine_grid['hold_days'] = sorted(list(set([
            max(2, min(12, int(center.get('hold_days', 7)) + d))
            for d in [-2, -1, 0, 1, 2]])))
        ultrafine_grid['min_entity_board_ratio'] = sorted(list(set([
            max(0.1, min(0.7, round(center.get('min_entity_board_ratio', 0.4) + d, 2)))
            for d in [-0.10, -0.05, 0, 0.05, 0.10]])))
        keys, values = list(ultrafine_grid.keys()), list(ultrafine_grid.values())
        for combo in product(*values):
            if len(all_combinations) >= MAX_STAGE3_COMBOS: break
            params_dict = dict(zip(keys, combo))
            params_dict.update(fixed_params)
            combo_key = str(sorted(params_dict.items()))
            if combo_key not in seen_combos:
                seen_combos.add(combo_key)
                all_combinations.append(params_dict)

    total_combos = len(all_combinations)
    print(f"合并后组合数: {total_combos} | 预计耗时: ~{total_combos * 0.007 / 60:.0f} 分钟\n")

    results_list, best_score, best_params, best_signals = [], -999, None, None
    start_time = time.time()
    for i, params_dict in enumerate(all_combinations):
        signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)
        if signals_df is None: continue
        results_list.append({**params_dict, **metrics})
        if score > best_score:
            best_score, best_params, best_signals = score, params_dict.copy(), signals_df.copy()
        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
            print(f"  [{i+1}/{total_combos} {((i+1)/total_combos)*100:.0f}%] "
                  f"剩余 {remaining/60:.0f}min | 最佳: {best_score:.4f}")

    total_time = time.time() - start_time
    print(f"\n✅ Stage 3 完成！耗时: {total_time/60:.1f} 分钟")
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(OUTPUT_DIR, f'v5_stage3_ultrafine_{start_date}_{end_date}.csv'),
                      index=False, encoding='utf-8-sig')
    return df_results, best_params, best_signals


def main():
    if len(sys.argv) < 3:
        print("用法: python run_deep_optimization.py <start_date> <end_date> [label]")
        print("例如: python run_deep_optimization.py 20240701 20250630 'Period B: 牛市大涨'")
        sys.exit(1)

    start_date, end_date = sys.argv[1], sys.argv[2]
    label = sys.argv[3] if len(sys.argv) > 3 else f"{start_date}_{end_date}"

    print("=" * 70)
    print(f"🔬 深度优化实验: {label}")
    print(f"   区间: {start_date} ~ {end_date}")
    print("=" * 70)

    # Step 1: 扫描涨停股票
    print("\n第一步：扫描涨停股票...")
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    hot_codes = []
    for fname in cache_files:
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 50: continue
        df_period = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        if len(df_period) == 0: continue
        limit_threshold = get_limit_threshold(code)
        if (df_period['pct_chg'] >= limit_threshold).any():
            hot_codes.append(code)
    print(f"✅ 涨停股票：{len(hot_codes)} 只")

    # Step 2: 预提取事件
    print("\n第二步：预提取连板+回调事件...")
    all_events = extract_all_events(hot_codes, start_date, end_date, min_series_len=2)
    print(f"✅ 共 {len(all_events)} 个事件")

    # Step 3: 三阶段优化
    t_start = time.time()
    s1_results, s1_best_params, s1_best_signals = run_stage_coarse_deep(all_events, start_date, end_date)
    s2_results, s2_best_params, s2_best_signals = run_stage_fine_deep(all_events, s1_results, start_date, end_date)
    s3_results, s3_best_params, s3_best_signals = run_stage_ultrafine_deep(all_events, s2_results, start_date, end_date)
    total_time = time.time() - t_start

    # Step 4: 报告
    print("\n" + "=" * 70)
    print(f"🏆 {label} 深度优化完成！总耗时: {total_time/60:.1f} 分钟")
    print("=" * 70)
    print(f"  Stage 1: 评分 {s1_results.iloc[0]['score']:.4f} | WR {s1_results.iloc[0]['win_rate']:.2%} | Sharpe {s1_results.iloc[0]['sharpe']:.2f}")
    print(f"  Stage 2: 评分 {s2_results.iloc[0]['score']:.4f} | WR {s2_results.iloc[0]['win_rate']:.2%} | Sharpe {s2_results.iloc[0]['sharpe']:.2f}")
    print(f"  Stage 3: 评分 {s3_results.iloc[0]['score']:.4f} | WR {s3_results.iloc[0]['win_rate']:.2%} | Sharpe {s3_results.iloc[0]['sharpe']:.2f}")

    print(f"\n📊 最优参数：")
    for k, v in s3_best_params.items():
        print(f"  {k}: {v}")

    # 保存
    final_output = {
        'period': f'{start_date}_{end_date}',
        'period_label': label,
        'best_params': {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                        for k, v in s3_best_params.items()},
        'stage1_score': float(s1_results.iloc[0]['score']),
        'stage2_score': float(s2_results.iloc[0]['score']),
        'stage3_score': float(s3_results.iloc[0]['score']),
        'stage3_metrics': {
            'win_rate': float(s3_results.iloc[0]['win_rate']),
            'avg_return': float(s3_results.iloc[0]['avg_return']),
            'sharpe': float(s3_results.iloc[0]['sharpe']),
            'sortino': float(s3_results.iloc[0].get('sortino', 0)),
            'max_drawdown': float(s3_results.iloc[0].get('max_dd', 0)),
            'signal_count': int(s3_results.iloc[0]['signal_count']),
            'profit_factor': float(s3_results.iloc[0].get('profit_factor', 0)),
        },
        'total_time_minutes': round(total_time / 60, 1),
        'enhanced_grid': True,
    }
    json_path = os.path.join(OUTPUT_DIR, f'v5_final_params_{start_date}_{end_date}.json')
    with open(json_path, 'w') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 最优参数已保存至 {json_path}")


if __name__ == "__main__":
    main()
