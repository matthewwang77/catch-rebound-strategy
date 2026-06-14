#!/usr/bin/env python3
"""
Period B Stages 2+3 补跑 — 从已有 Stage 1 结果继续。
Stage 1 最佳: WR 79.2%, Sharpe 12.13, pullback 15-22%
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

START, END = '20240701', '20250630'
LABEL = "Period B: 牛市大涨"

# ── Load Stage 1 results ──
print("=" * 60)
print(f"📂 加载 Stage 1 结果...")
s1_path = os.path.join(OUTPUT_DIR, f'v5_stage1_coarse_{START}_{END}.csv')
if not os.path.exists(s1_path):
    print(f"❌ 找不到 {s1_path}")
    sys.exit(1)
s1_results = pd.read_csv(s1_path).sort_values('score', ascending=False)
print(f"✅ Stage 1: {len(s1_results)} 条 | 最佳评分 {s1_results.iloc[0]['score']:.4f} | WR {s1_results.iloc[0]['win_rate']:.1%}")

# ── Extract events ──
print("\n📊 预提取 Period B 事件...")
cache_files = [f for f in os.listdir(DATA_DIR)
               if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
hot_codes = []
for fname in cache_files:
    code = fname.replace('.csv', '')
    df = load_from_cache(code)
    if df is None or len(df) < 50: continue
    df_p = df[(df['trade_date'] >= START) & (df['trade_date'] <= END)]
    if len(df_p) == 0: continue
    if (df_p['pct_chg'] >= get_limit_threshold(code)).any():
        hot_codes.append(code)
print(f"✅ {len(hot_codes)} 只涨停股")

all_events = extract_all_events(hot_codes, START, END, min_series_len=2)
print(f"✅ {len(all_events)} 个事件")

# ── Stage 2 Enhanced ──
t0 = time.time()
print("\n" + "=" * 60)
print("🔍 STAGE 2 [ENHANCED]")
print("=" * 60)

clusters = cluster_top_params(s1_results, top_n=80, n_clusters=5)
all_combos, seen = [], set()
MAX_S2 = 80000

for cluster in clusters[:3]:
    sr, center = cluster['search_ranges'], cluster['center']
    fixed = {
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
    for combo in product(*list(fine_grid.values())):
        if len(all_combos) >= MAX_S2: break
        d = dict(zip(list(fine_grid.keys()), combo))
        d.update(fixed)
        k = str(sorted(d.items()))
        if k not in seen:
            seen.add(k)
            all_combos.append(d)

print(f"组合数: {len(all_combos)} | 预计 ~{len(all_combos)*0.03/60:.0f}min")
results_s2, best_score, best_params, best_signals = [], -999, None, None
for i, params_dict in enumerate(all_combos):
    signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)
    if signals_df is None: continue
    results_s2.append({**params_dict, **metrics})
    if score > best_score:
        best_score, best_params, best_signals = score, params_dict.copy(), signals_df.copy()
    if (i+1) % 200 == 0:
        elapsed = time.time() - t0
        rate = elapsed / (i+1)
        remaining = (len(all_combos) - i - 1) * rate
        print(f"  [{i+1}/{len(all_combos)} {(i+1)/len(all_combos)*100:.0f}%] "
              f"剩余 {remaining/60:.0f}min | 最佳: {best_score:.4f}")

t_s2 = time.time() - t0
print(f"\n✅ Stage 2 完成！{t_s2/60:.1f}min | 最佳评分 {best_score:.4f}")
s2_df = pd.DataFrame(results_s2).sort_values('score', ascending=False)
s2_df.to_csv(os.path.join(OUTPUT_DIR, f'v5_stage2_fine_{START}_{END}.csv'), index=False, encoding='utf-8-sig')

# ── Stage 3 Enhanced ──
print("\n" + "=" * 60)
print("🔍 STAGE 3 [ENHANCED]")
print("=" * 60)

top10 = s2_df.head(10)
all_combos_s3, seen_s3 = [], set()
MAX_S3 = 50000

for _, row in top10.iterrows():
    center = row.to_dict()
    fixed = {
        'min_consecutive_limit_up': int(center.get('min_consecutive_limit_up', 2)),
        'require_oversold': False, 'require_low_close': False,
        'volume_shrink_ratio_min': center.get('volume_shrink_ratio_min', 0.0),
    }
    ugrid = {}
    for p, margin in [('pullback_ratio_min', 0.025), ('pullback_ratio_max', 0.035),
                       ('volume_shrink_ratio', 0.035)]:
        base = center.get(p, 0)
        vals = [round(base + d, 2) for d in np.arange(-margin, margin + 0.005, 0.01)]
        ugrid[p] = sorted(list(set([max(0.01, v) for v in vals])))
    for p, margin in [('take_profit', 0.015), ('stop_loss', 0.020)]:
        base = center.get(p, 0)
        vals = [round(base + d, 3) for d in np.arange(-margin, margin + 0.003, 0.005)]
        ugrid[p] = sorted(list(set(vals)))
    ugrid['hold_days'] = sorted(list(set([
        max(2, min(12, int(center.get('hold_days', 7)) + d))
        for d in [-2, -1, 0, 1, 2]])))
    ugrid['min_entity_board_ratio'] = sorted(list(set([
        max(0.1, min(0.7, round(center.get('min_entity_board_ratio', 0.4) + d, 2)))
        for d in [-0.10, -0.05, 0, 0.05, 0.10]])))
    for combo in product(*list(ugrid.values())):
        if len(all_combos_s3) >= MAX_S3: break
        d = dict(zip(list(ugrid.keys()), combo))
        d.update(fixed)
        k = str(sorted(d.items()))
        if k not in seen_s3:
            seen_s3.add(k)
            all_combos_s3.append(d)

print(f"组合数: {len(all_combos_s3)} | 预计 ~{len(all_combos_s3)*0.03/60:.0f}min")
t0_s3 = time.time()
results_s3, best_score_s3, best_params_s3, best_signals_s3 = [], -999, None, None
for i, params_dict in enumerate(all_combos_s3):
    signals_df, metrics, score = evaluate_params_on_events(all_events, params_dict)
    if signals_df is None: continue
    results_s3.append({**params_dict, **metrics})
    if score > best_score_s3:
        best_score_s3, best_params_s3, best_signals_s3 = score, params_dict.copy(), signals_df.copy()
    if (i+1) % 200 == 0:
        elapsed = time.time() - t0_s3
        remaining = (len(all_combos_s3) - i - 1) * (elapsed / (i+1))
        print(f"  [{i+1}/{len(all_combos_s3)} {(i+1)/len(all_combos_s3)*100:.0f}%] "
              f"剩余 {remaining/60:.0f}min | 最佳: {best_score_s3:.4f}")

t_s3 = time.time() - t0_s3
total = (time.time() - t0) / 60
print(f"\n✅ Stage 3 完成！{t_s3/60:.1f}min | 总耗时 {total:.1f}min")

s3_df = pd.DataFrame(results_s3).sort_values('score', ascending=False)
s3_df.to_csv(os.path.join(OUTPUT_DIR, f'v5_stage3_ultrafine_{START}_{END}.csv'), index=False, encoding='utf-8-sig')

# ── Save ──
print(f"\n🏆 Period B 最终参数：")
for k, v in best_params_s3.items():
    print(f"  {k}: {v}")

print(f"\n  S1→S2→S3: {s1_results.iloc[0]['score']:.4f} → {best_score:.4f} → {best_score_s3:.4f}")
print(f"  WR: {s1_results.iloc[0]['win_rate']:.1%} → {s2_df.iloc[0]['win_rate']:.1%} → {s3_df.iloc[0]['win_rate']:.1%}")
print(f"  Sharpe: {s1_results.iloc[0]['sharpe']:.1f} → {s2_df.iloc[0]['sharpe']:.1f} → {s3_df.iloc[0]['sharpe']:.1f}")

final = {
    'period': f'{START}_{END}',
    'period_label': LABEL,
    'best_params': {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                    for k, v in best_params_s3.items()},
    'stage1_score': float(s1_results.iloc[0]['score']),
    'stage2_score': float(best_score),
    'stage3_score': float(best_score_s3),
    'stage3_metrics': {
        'win_rate': float(s3_df.iloc[0]['win_rate']),
        'avg_return': float(s3_df.iloc[0]['avg_return']),
        'sharpe': float(s3_df.iloc[0]['sharpe']),
        'signal_count': int(s3_df.iloc[0]['signal_count']),
    },
    'total_time_minutes': round(total, 1),
    'enhanced_grid': True,
    'full_3_stage': True,
}
with open(os.path.join(OUTPUT_DIR, f'v5_final_params_{START}_{END}.json'), 'w') as f:
    json.dump(final, f, indent=2, ensure_ascii=False)
print(f"\n✅ 已保存 v5_final_params_{START}_{END}.json")
