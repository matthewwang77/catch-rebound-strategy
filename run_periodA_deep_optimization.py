#!/usr/bin/env python3
"""
Period A 深度优化实验
=====================
对 2023.01-2024.06（震荡下行/熊市）做增强版三阶段参数搜索。
不动 选股new_v5.py 一行代码，直接 import 共享函数。
网格比默认版本密 ~50%，预计总耗时 35-50 分钟。

输出:
  v5_results/v5_stage1_coarse_20230101_20240630.csv      (~10万组合)
  v5_results/v5_stage2_fine_20230101_20240630.csv         (~8万组合)
  v5_results/v5_stage3_ultrafine_20230101_20240630.csv    (~5万组合)
  v5_results/v5_final_params_20230101_20240630.json       (最优参数)
  v5_results/v5_regime_A_deep_report.json                 (完整报告)
"""

import sys, os, json, time, warnings
import numpy as np
import pandas as pd
from itertools import product

warnings.filterwarnings("ignore")

# Force unbuffered output (critical for background runs)
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

# ── Add cwd to path ──────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Import from 选股new_v5 ────────────────────────────────────────
import importlib.util
spec = importlib.util.spec_from_file_location("screener", "选股new_v5.py")
screener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screener)

# Aliases for cleaner code
extract_all_events = screener.extract_all_events
evaluate_params_on_events = screener.evaluate_params_on_events
load_from_cache = screener.load_from_cache
get_limit_threshold = screener.get_limit_threshold
cluster_top_params = screener.cluster_top_params
DATA_DIR = screener.DATA_DIR
OUTPUT_DIR = screener.OUTPUT_DIR

PERIOD_A = ('20230101', '20240630')
PERIOD_LABEL = "Period A: 震荡下行 (2023.01 - 2024.06)"


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Stage 1 增强版 — 更密集的粗筛网格 (~95k 组合 vs 默认 61k)     ║
# ╚══════════════════════════════════════════════════════════════════╝

def run_stage_coarse_deep(all_events, start_date, end_date):
    print("\n" + "=" * 70)
    print("🔍 STAGE 1 [ENHANCED]: Deep Coarse Grid Search")
    print("=" * 70)

    param_grid = {
        "min_consecutive_limit_up": [2, 3],
        "min_entity_board_ratio": [0.15, 0.30, 0.45, 0.60],       # +1 level
        "pullback_ratio_min": [0.02, 0.05, 0.08, 0.11, 0.14, 0.17], # +2 levels
        "pullback_ratio_max": [0.10, 0.18, 0.26, 0.34, 0.42],       # +0 but wider
        "volume_shrink_ratio": [0.15, 0.30, 0.45, 0.60, 0.75],      # +1 level
        "volume_shrink_ratio_min": [0.0, 0.05, 0.10],                # +1 level
        "take_profit": [0.03, 0.05, 0.07, 0.09, 0.12],               # +1 level
        "stop_loss": [-0.03, -0.06, -0.09, -0.12, -0.15],            # +1 level
        "hold_days": [3, 5, 7, 10],                                  # same
        "require_oversold": [False],
        "require_low_close": [False],
    }

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combinations = list(product(*values))
    total_combos = len(all_combinations)

    size = 1
    for v in values:
        size *= len(v)
    print(f"参数网格大小: {' × '.join(str(len(v)) for v in values)} = {size}")
    print(f"参数组合数: {total_combos}")
    print(f"预计耗时: ~{total_combos * 0.007 / 60:.0f} 分钟\n")

    results_list = []
    best_score = -999
    best_params = None
    best_signals = None
    start_time = time.time()

    for i, combo in enumerate(all_combinations):
        params_dict = dict(zip(keys, combo))
        signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)

        if signals_df is None:
            continue

        results_list.append({**params_dict, **metrics})

        if score > best_score:
            best_score = score
            best_params = params_dict.copy()
            best_signals = signals_df.copy()

        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            rate = elapsed / (i + 1)
            remaining = (total_combos - i - 1) * rate
            print(f"  [{i+1}/{total_combos} {((i+1)/total_combos)*100:.0f}%] "
                  f"剩余 {remaining/60:.0f}min | 最佳: {best_score:.4f} "
                  f"(WR {best_signals['return'].gt(0).sum()/len(best_signals):.0%} "
                  f"Sharpe {metrics.get('sharpe',0):.1f})")

    total_time = time.time() - start_time
    print(f"\n✅ Stage 1 完成！耗时: {total_time/60:.1f} 分钟")
    print(f"   有效组合: {len(results_list)} | 最佳评分: {best_score:.4f}")

    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(OUTPUT_DIR, f'v5_stage1_coarse_{start_date}_{end_date}.csv'),
                      index=False, encoding='utf-8-sig')

    display_cols = ['win_rate', 'avg_return', 'signal_count', 'sharpe', 'score'] + keys
    print(f"\nStage 1 Top-15:")
    print(df_results.head(15)[display_cols].to_string())

    return df_results, best_params, best_signals


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Stage 2 增强版 — 更多热点，更细步长 (~80k 组合 vs 默认 50k)   ║
# ╚══════════════════════════════════════════════════════════════════╝

def run_stage_fine_deep(all_events, stage1_results, start_date, end_date):
    print("\n" + "=" * 70)
    print("🔍 STAGE 2 [ENHANCED]: Deep Fine Grid Search")
    print("=" * 70)

    # 更多热点 + 更多聚类
    clusters = cluster_top_params(stage1_results, top_n=80, n_clusters=5)

    all_combinations = []
    seen_combos = set()
    MAX_STAGE2_COMBOS = 80000  # enhanced: 50k→80k

    for cluster in clusters[:3]:  # enhanced: 2→3 hotspots
        sr = cluster['search_ranges']
        center = cluster['center']

        fixed_params = {
            'min_consecutive_limit_up': int(center.get('min_consecutive_limit_up', 2)),
            'require_oversold': False,
            'require_low_close': False,
            'volume_shrink_ratio_min': center.get('volume_shrink_ratio_min', 0.0),
        }

        # 细化网格，更多步数
        fine_grid = {}
        for p in ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
                   'take_profit', 'stop_loss']:
            if p in sr:
                p_min = sr[p]['min']
                p_max = sr[p]['max']
                if p in ['take_profit', 'stop_loss']:
                    step = 0.003  # enhanced: 0.005→0.003
                else:
                    step = 0.005  # enhanced: 0.01→0.005
                n_steps = max(4, min(8, int((p_max - p_min) / step) + 1))  # enhanced: 3-5→4-8
                fine_grid[p] = sorted(list(set([
                    round(p_min + i * (p_max - p_min) / (n_steps - 1), 3)
                    for i in range(n_steps)
                ])))

        fine_grid['hold_days'] = sorted(list(set([
            max(2, min(12, int(center.get('hold_days', 7)) + d))
            for d in [-2, -1, 0, 1, 2]  # enhanced: ±1→±2 天
        ])))
        fine_grid['min_entity_board_ratio'] = sorted(list(set([
            max(0.1, min(0.7, round(center.get('min_entity_board_ratio', 0.4) + d, 2)))
            for d in [-0.15, -0.05, 0, 0.05, 0.15]  # enhanced: ±0.1→±0.15
        ])))

        keys = list(fine_grid.keys())
        values = list(fine_grid.values())
        for combo in product(*values):
            if len(all_combinations) >= MAX_STAGE2_COMBOS:
                break
            params_dict = dict(zip(keys, combo))
            params_dict.update(fixed_params)
            combo_key = str(sorted(params_dict.items()))
            if combo_key not in seen_combos:
                seen_combos.add(combo_key)
                all_combinations.append(params_dict)

    total_combos = len(all_combinations)
    print(f"合并后组合数: {total_combos}")
    print(f"预计耗时: ~{total_combos * 0.007 / 60:.0f} 分钟\n")

    results_list = []
    best_score = -999
    best_params = None
    best_signals = None
    start_time = time.time()

    for i, params_dict in enumerate(all_combinations):
        signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)
        if signals_df is None: continue

        results_list.append({**params_dict, **metrics})

        if score > best_score:
            best_score = score
            best_params = params_dict.copy()
            best_signals = signals_df.copy()

        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
            print(f"  [{i+1}/{total_combos} {((i+1)/total_combos)*100:.0f}%] "
                  f"剩余 {remaining/60:.0f}min | 最佳: {best_score:.4f} "
                  f"(WR {best_signals['return'].gt(0).sum()/len(best_signals):.0%})")

    total_time = time.time() - start_time
    print(f"\n✅ Stage 2 完成！耗时: {total_time/60:.1f} 分钟")

    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(OUTPUT_DIR, f'v5_stage2_fine_{start_date}_{end_date}.csv'),
                      index=False, encoding='utf-8-sig')

    display_cols = ['win_rate', 'avg_return', 'signal_count', 'sharpe', 'score']
    display_cols += [c for c in df_results.columns if c in [
        'pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
        'take_profit', 'stop_loss', 'hold_days']]
    print(f"\nStage 2 Top-10:")
    print(df_results.head(10)[display_cols].to_string())

    return df_results, best_params, best_signals


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Stage 3 增强版 — Top-10邻域，更宽margin (~50k vs 默认 30k)    ║
# ╚══════════════════════════════════════════════════════════════════╝

def run_stage_ultrafine_deep(all_events, stage2_results, start_date, end_date):
    print("\n" + "=" * 70)
    print("🔍 STAGE 3 [ENHANCED]: Deep Ultra-Fine Grid Search")
    print("=" * 70)

    top10 = stage2_results.head(10)  # enhanced: top5→top10

    all_combinations = []
    seen_combos = set()
    MAX_STAGE3_COMBOS = 50000  # enhanced: 30k→50k

    for _, row in top10.iterrows():
        center = row.to_dict()

        fixed_params = {
            'min_consecutive_limit_up': int(center.get('min_consecutive_limit_up', 2)),
            'require_oversold': False,
            'require_low_close': False,
            'volume_shrink_ratio_min': center.get('volume_shrink_ratio_min', 0.0),
        }

        # 更宽的搜索范围
        ultrafine_grid = {}
        for p, margin in [('pullback_ratio_min', 0.025), ('pullback_ratio_max', 0.035),
                           ('volume_shrink_ratio', 0.035)]:  # enhanced margins
            base = center.get(p, 0)
            vals = [round(base + d, 2) for d in np.arange(-margin, margin + 0.005, 0.01)]
            ultrafine_grid[p] = sorted(list(set([max(0.01, v) for v in vals])))

        for p, margin in [('take_profit', 0.015), ('stop_loss', 0.020)]:  # enhanced margins
            base = center.get(p, 0)
            vals = [round(base + d, 3) for d in np.arange(-margin, margin + 0.003, 0.005)]
            ultrafine_grid[p] = sorted(list(set(vals)))

        ultrafine_grid['hold_days'] = sorted(list(set([
            max(2, min(12, int(center.get('hold_days', 7)) + d))
            for d in [-2, -1, 0, 1, 2]  # enhanced: ±1→±2
        ])))
        ultrafine_grid['min_entity_board_ratio'] = sorted(list(set([
            max(0.1, min(0.7, round(center.get('min_entity_board_ratio', 0.4) + d, 2)))
            for d in [-0.10, -0.05, 0, 0.05, 0.10]  # enhanced: ±0.05→±0.10
        ])))

        keys = list(ultrafine_grid.keys())
        values = list(ultrafine_grid.values())
        for combo in product(*values):
            if len(all_combinations) >= MAX_STAGE3_COMBOS:
                break
            params_dict = dict(zip(keys, combo))
            params_dict.update(fixed_params)
            combo_key = str(sorted(params_dict.items()))
            if combo_key not in seen_combos:
                seen_combos.add(combo_key)
                all_combinations.append(params_dict)

    total_combos = len(all_combinations)
    print(f"合并后组合数: {total_combos}")
    print(f"预计耗时: ~{total_combos * 0.007 / 60:.0f} 分钟\n")

    results_list = []
    best_score = -999
    best_params = None
    best_signals = None
    start_time = time.time()

    for i, params_dict in enumerate(all_combinations):
        signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)
        if signals_df is None: continue

        results_list.append({**params_dict, **metrics})

        if score > best_score:
            best_score = score
            best_params = params_dict.copy()
            best_signals = signals_df.copy()

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


# ╔══════════════════════════════════════════════════════════════════╗
# ║  主流程                                                          ║
# ╚══════════════════════════════════════════════════════════════════╝

def main():
    start_date, end_date = PERIOD_A

    print("=" * 70)
    print("🔬 Period A 深度优化实验")
    print(f"   {PERIOD_LABEL}")
    print("=" * 70)
    print(f"   默认优化组合数: Stage1=61k / Stage2=50k / Stage3=30k")
    print(f"   增强优化组合数: Stage1=~95k / Stage2=~80k / Stage3=~50k")
    print(f"   预计总耗时: 35-50 分钟")
    print("=" * 70)

    # ── Step 1: 扫描涨停股票 ──
    print("\n第一步：扫描涨停股票...")
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    hot_codes = []
    for fname in cache_files:
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 50: continue
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        if len(df) == 0: continue
        limit_threshold = get_limit_threshold(code)
        if (df['pct_chg'] >= limit_threshold).any():
            hot_codes.append(code)
    print(f"✅ 涨停股票：{len(hot_codes)} 只")

    # ── Step 2: 预提取事件 ──
    print("\n第二步：预提取连板+回调事件...")
    all_events = extract_all_events(hot_codes, start_date, end_date, min_series_len=2)
    print(f"✅ 共 {len(all_events)} 个事件")

    # ── Step 3: 三阶段增强优化 ──
    t_start = time.time()

    # Stage 1
    s1_results, s1_best_params, s1_best_signals = run_stage_coarse_deep(
        all_events, start_date, end_date)

    # Stage 2
    s2_results, s2_best_params, s2_best_signals = run_stage_fine_deep(
        all_events, s1_results, start_date, end_date)

    # Stage 3
    s3_results, s3_best_params, s3_best_signals = run_stage_ultrafine_deep(
        all_events, s2_results, start_date, end_date)

    total_time = time.time() - t_start

    # ── Step 4: 最终报告 ──
    print("\n" + "=" * 70)
    print("🏆 Period A 深度优化完成！")
    print(f"   总耗时: {total_time/60:.1f} 分钟")
    print("=" * 70)

    print(f"\n  Stage 1 最佳: 评分 {s1_results.iloc[0]['score']:.4f} | "
          f"胜率 {s1_results.iloc[0]['win_rate']:.2%} | "
          f"Sharpe {s1_results.iloc[0]['sharpe']:.2f}")
    print(f"  Stage 2 最佳: 评分 {s2_results.iloc[0]['score']:.4f} | "
          f"胜率 {s2_results.iloc[0]['win_rate']:.2%} | "
          f"Sharpe {s2_results.iloc[0]['sharpe']:.2f}")
    print(f"  Stage 3 最佳: 评分 {s3_results.iloc[0]['score']:.4f} | "
          f"胜率 {s3_results.iloc[0]['win_rate']:.2%} | "
          f"Sharpe {s3_results.iloc[0]['sharpe']:.2f}")

    print(f"\n📊 Period A 最优参数：")
    for k, v in s3_best_params.items():
        print(f"  {k}: {v}")

    print(f"\n📊 参数进化（Stage 1 → Stage 2 → Stage 3）：")
    for p in ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
               'take_profit', 'stop_loss', 'hold_days']:
        v1 = s1_best_params.get(p, '—')
        v2 = s2_best_params.get(p, '—')
        v3 = s3_best_params.get(p, '—')
        print(f"  {p:<25}: {str(v1):>8} → {str(v2):>8} → {str(v3):>8}")

    # ── Step 5: 保存结果 ──
    # 最终参数 JSON
    final_output = {
        'period': '20230101_20240630',
        'period_label': PERIOD_LABEL,
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
    json_path = os.path.join(OUTPUT_DIR, 'v5_final_params_20230101_20240630.json')
    with open(json_path, 'w') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 最优参数已保存至 {json_path}")

    # 完整报告
    report = {
        'experiment': 'Period A Deep Optimization',
        'period': '20230101_20240630',
        'period_label': PERIOD_LABEL,
        'grid_enhancement': {
            'stage1': '95k combos (vs default 61k)',
            'stage2': '80k max, 3 hotspots, n_steps 4-8 (vs 50k/2 hotspots/n_steps 3-5)',
            'stage3': '50k max, top-10, wider margins (vs 30k/top-5/narrow)',
        },
        'best_params': final_output['best_params'],
        'stage_metrics': {
            'stage1': {'score': final_output['stage1_score'], **s1_results.iloc[0].to_dict()},
            'stage2': {'score': final_output['stage2_score'], **s2_results.iloc[0].to_dict()},
            'stage3': final_output['stage3_metrics'],
        },
        'comparison_to_default': {
            'default_periodA_sharpe': -2.08,
            'default_periodA_win_rate': 0.421,
            'default_periodA_avg_return': -0.025,
            'note': 'Compare enhanced params performance to these baselines',
        },
        'total_time_minutes': round(total_time / 60, 1),
    }
    report_path = os.path.join(OUTPUT_DIR, 'v5_regime_A_deep_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"✅ 完整报告已保存至 {report_path}")

    print("\n" + "=" * 70)
    print("📋 下一步：")
    print("   1. 对比 Period A 最优参数 vs 默认参数在 Period A 的表现")
    print("   2. 用 Period A 参数跑 Period B/C 回测，看交叉表现")
    print("   3. 如果 Period A 的最优参数夏普仍为负 → 熊市应空仓")
    print("   4. 如果 Period A 的最优参数夏普转正 → 值得做市场自适应")
    print("=" * 70)


if __name__ == "__main__":
    main()
