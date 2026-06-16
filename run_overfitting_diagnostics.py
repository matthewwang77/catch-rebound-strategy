#!/usr/bin/env python3
"""
全面过拟合诊断脚本
诊断 v6 四个模式的过拟合风险：
  1. 3×3 交叉验证矩阵（用最终 Stage 3 参数）
  2. 各模式的 Bootstrap 置信区间
  3. 各模式的 Permutation Test
  4. Walk-forward 时间序列分割
  5. 参数敏感性分析
  6. 综合过拟合评分
"""
import sys, os, json, time, warnings
import numpy as np
import pandas as pd
from datetime import timedelta

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.dirname(os.path.abspath(__file__))

import importlib.util
spec = importlib.util.spec_from_file_location("screener", os.path.join(BASE, "选股new_v5.py"))
screener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screener)

extract_all_events = screener.extract_all_events
evaluate_params_on_events = screener.evaluate_params_on_events
load_from_cache = screener.load_from_cache
get_limit_threshold = screener.get_limit_threshold
DATA_DIR = screener.DATA_DIR
OUTPUT_DIR = screener.OUTPUT_DIR
PARAMS = screener.PARAMS
SCREEN_MODES = screener.SCREEN_MODES

# ── 定义三个交叉验证周期 ──
PERIODS = {
    "A_熊市震荡": ("20230101", "20240630"),
    "B_牛市大涨": ("20240701", "20250630"),
    "C_震荡回调": ("20250701", "20260430"),
}

# ── 定义要测试的模式（从 SCREEN_MODES 取最终参数） ──
MODES_TO_TEST = {
    "BEAR": SCREEN_MODES["bear"],
    "STRICT": SCREEN_MODES["strict"],
    "LOOSE": SCREEN_MODES["loose"],
}

# ── 模式所属的训练周期 ──
MODE_TRAIN_PERIOD = {
    "BEAR": "A_熊市震荡",
    "STRICT": "C_震荡回调",
    "LOOSE": "C_震荡回调",
}

# ══════════════════════════════════════════════════════════════════════════════
# Step 0: 预提取所有周期的事件
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("🔬 v6 全面过拟合诊断")
print("=" * 70)

all_period_events = {}
for period_name, (start, end) in PERIODS.items():
    print(f"\n📊 预提取 {period_name} ({start}~{end}) 事件...")
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    hot_codes = []
    for fname in cache_files:
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 50: continue
        df_p = df[(df['trade_date'] >= start) & (df['trade_date'] <= end)]
        if len(df_p) == 0: continue
        if (df_p['pct_chg'] >= get_limit_threshold(code)).any():
            hot_codes.append(code)
    print(f"  {len(hot_codes)} 只涨停股")

    events = extract_all_events(hot_codes, start, end, min_series_len=2)
    all_period_events[period_name] = events
    print(f"  {len(events)} 个连板事件")

# ══════════════════════════════════════════════════════════════════════════════
# Step 1: 3×4 交叉验证矩阵（3个周期 × 4个模式）
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📊 STEP 1: 3×4 交叉验证矩阵（最终 Stage 3 参数）")
print("=" * 70)

cv_results = {}
for mode_name, mode_params in MODES_TO_TEST.items():
    cv_results[mode_name] = {}
    for period_name, (start, end) in PERIODS.items():
        events = all_period_events[period_name]
        is_in_sample = (MODE_TRAIN_PERIOD[mode_name] == period_name)

        # 构建参数字典
        params = {
            'min_consecutive_limit_up': mode_params['min_consecutive_limit_up'],
            'min_entity_board_ratio': mode_params['min_entity_board_ratio'],
            'pullback_ratio_min': mode_params['pullback_ratio_min'],
            'pullback_ratio_max': mode_params['pullback_ratio_max'],
            'volume_shrink_ratio': mode_params['volume_shrink_ratio'],
            'volume_shrink_ratio_min': mode_params.get('volume_shrink_ratio_min', 0.0),
            'take_profit': mode_params['take_profit'],
            'stop_loss': mode_params['stop_loss'],
            'hold_days': mode_params['hold_days'],
            'require_oversold': mode_params.get('require_oversold', False),
            'require_low_close': mode_params.get('require_low_close', False),
        }

        signals_df, metrics, score = evaluate_params_on_events(events, params)

        tag = "🟢 IS" if is_in_sample else "🔵 OOS"
        if signals_df is not None and metrics is not None:
            cv_results[mode_name][period_name] = {
                'win_rate': metrics['win_rate'],
                'avg_return': metrics['avg_return'],
                'sharpe': metrics['sharpe'],
                'signal_count': metrics['signal_count'],
                'score': score,
                'is_in_sample': is_in_sample,
            }
            print(f"  [{mode_name:7s} → {period_name:12s}] {tag} | "
                  f"WR={metrics['win_rate']:.1%} | Sharpe={metrics['sharpe']:.2f} | "
                  f"信号={metrics['signal_count']:4d} | Score={score:.4f}")
        else:
            cv_results[mode_name][period_name] = None
            print(f"  [{mode_name:7s} → {period_name:12s}] {tag} | ❌ 无有效信号")

# ── 计算交叉验证统计 ──
print(f"\n{'─'*70}")
print(f"  交叉验证汇总")
print(f"{'─'*70}")

for mode_name in MODES_TO_TEST:
    is_vals = []
    oos_vals = []
    for period_name in PERIODS:
        r = cv_results[mode_name][period_name]
        if r is None: continue
        if r['is_in_sample']:
            is_vals.append(r)
        else:
            oos_vals.append(r)

    if is_vals and oos_vals:
        is_sharpe = np.mean([v['sharpe'] for v in is_vals])
        oos_sharpe = np.mean([v['sharpe'] for v in oos_vals])
        is_wr = np.mean([v['win_rate'] for v in is_vals])
        oos_wr = np.mean([v['win_rate'] for v in oos_vals])

        sharpe_decay = oos_sharpe - is_sharpe
        wr_decay = oos_wr - is_wr

        # 过拟合判断
        if sharpe_decay < -1.0 or oos_sharpe < 0:
            of_status = "🔴 严重过拟合"
        elif sharpe_decay < -0.3 or wr_decay < -0.05:
            of_status = "🟡 轻微过拟合"
        else:
            of_status = "🟢 泛化良好"

        print(f"  {mode_name:7s}: IS Sharpe={is_sharpe:.2f} | OOS Sharpe={oos_sharpe:.2f} | "
              f"ΔSharpe={sharpe_decay:+.2f} | IS WR={is_wr:.1%} | OOS WR={oos_wr:.1%} | "
              f"ΔWR={wr_decay:+.1%} → {of_status}")
    elif is_vals:
        print(f"  {mode_name:7s}: IS Sharpe={np.mean([v['sharpe'] for v in is_vals]):.2f} | 无 OOS 数据")

# ══════════════════════════════════════════════════════════════════════════════
# Step 2: 各模式 Bootstrap + Permutation Test
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📊 STEP 2: Bootstrap 置信区间 + Permutation Test（各自训练周期）")
print("=" * 70)

bootstrap_results = {}
permutation_results = {}

for mode_name, mode_params in MODES_TO_TEST.items():
    train_period = MODE_TRAIN_PERIOD[mode_name]
    start, end = PERIODS[train_period]
    events = all_period_events[train_period]

    print(f"\n  ── {mode_name} (训练周期: {train_period}) ──")

    # 获取该模式在自己的训练周期中的信号
    params = {
        'min_consecutive_limit_up': mode_params['min_consecutive_limit_up'],
        'min_entity_board_ratio': mode_params['min_entity_board_ratio'],
        'pullback_ratio_min': mode_params['pullback_ratio_min'],
        'pullback_ratio_max': mode_params['pullback_ratio_max'],
        'volume_shrink_ratio': mode_params['volume_shrink_ratio'],
        'volume_shrink_ratio_min': mode_params.get('volume_shrink_ratio_min', 0.0),
        'take_profit': mode_params['take_profit'],
        'stop_loss': mode_params['stop_loss'],
        'hold_days': mode_params['hold_days'],
        'require_oversold': mode_params.get('require_oversold', False),
        'require_low_close': mode_params.get('require_low_close', False),
    }

    signals_df, metrics, score = evaluate_params_on_events(events, params)

    if signals_df is None or len(signals_df) < 10:
        print(f"  ⚠️ 信号不足，跳过统计检验")
        bootstrap_results[mode_name] = None
        permutation_results[mode_name] = None
        continue

    returns = signals_df['return'].values
    n_signals = len(returns)

    # ── Bootstrap ──
    np.random.seed(42)
    n_bootstrap = 2000
    sharpe_samples, wr_samples, avgret_samples = [], [], []
    for _ in range(n_bootstrap):
        sample = np.random.choice(returns, size=n_signals, replace=True)
        wr_samples.append((sample > 0).mean())
        avgret_samples.append(sample.mean())
        if sample.std() > 0:
            sharpe_samples.append((sample.mean() * 252) / (sample.std() * np.sqrt(252)))
        else:
            sharpe_samples.append(0)

    bs = {}
    for name, samples in [('sharpe', sharpe_samples), ('win_rate', wr_samples), ('avg_return', avgret_samples)]:
        lower = np.percentile(samples, 2.5)
        upper = np.percentile(samples, 97.5)
        mean_val = np.mean(samples)
        bs[name] = {'mean': float(mean_val), 'lower': float(lower), 'upper': float(upper),
                     'std': float(np.std(samples))}
        print(f"  Bootstrap {name}: {mean_val:.4f} [{lower:.4f}, {upper:.4f}] (95% CI)")

    bootstrap_results[mode_name] = bs

    # ── Bootstrap 显著性检验 (H2修复: 替换 shuffle 为 bootstrap+centering) ──
    if returns.std() > 0:
        true_sharpe = (returns.mean() * 252) / (returns.std() * np.sqrt(252))
    else:
        true_sharpe = 0

    ret_mean = returns.mean()
    np.random.seed(42)
    n_perm = 2000
    perm_sharpes = []
    for _ in range(n_perm):
        # Bootstrap: 带放回抽样 + 中心化 (强制 H0: Sharpe=0)
        sample = np.random.choice(returns, size=n_signals, replace=True)
        sample_centered = sample - ret_mean
        if sample_centered.std() > 0:
            perm_sharpes.append((sample_centered.mean() * 252) / (sample_centered.std() * np.sqrt(252)))
        else:
            perm_sharpes.append(0)

    perm_sharpes = np.array(perm_sharpes)
    p_value = float((perm_sharpes >= true_sharpe).mean())

    pt = {'true_sharpe': float(true_sharpe), 'p_value': p_value,
          'perm_mean': float(perm_sharpes.mean()), 'perm_std': float(perm_sharpes.std()),
          'n_signals': n_signals}

    if p_value < 0.01:
        pt['conclusion'] = "极显著 (p<0.01)"
    elif p_value < 0.05:
        pt['conclusion'] = "显著 (p<0.05)"
    elif p_value < 0.10:
        pt['conclusion'] = "边际显著 (p<0.10)"
    else:
        pt['conclusion'] = f"不显著 (p={p_value:.2f})"

    permutation_results[mode_name] = pt
    print(f"  Permutation: true Sharpe={true_sharpe:.2f} | perm mean={perm_sharpes.mean():.2f} | "
          f"p={p_value:.4f} → {pt['conclusion']}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 3: Walk-forward 时间序列分割检验
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📊 STEP 3: Walk-forward 时间序列分割（IS 60% / OOS 40%）")
print("=" * 70)

walkforward_results = {}

for mode_name, mode_params in MODES_TO_TEST.items():
    train_period = MODE_TRAIN_PERIOD[mode_name]
    start, end = PERIODS[train_period]

    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    total_days = (end_dt - start_dt).days
    split_date = start_dt + timedelta(days=int(total_days * 0.6))
    is_start = start
    is_end = split_date.strftime('%Y%m%d')
    oos_start = (split_date + timedelta(days=1)).strftime('%Y%m%d')
    oos_end = end

    print(f"\n  ── {mode_name} ({train_period}) ──")
    print(f"  IS: {is_start} ~ {is_end} | OOS: {oos_start} ~ {oos_end}")

    # 重建事件（分 IS/OOS）
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]

    params = {
        'min_consecutive_limit_up': mode_params['min_consecutive_limit_up'],
        'min_entity_board_ratio': mode_params['min_entity_board_ratio'],
        'pullback_ratio_min': mode_params['pullback_ratio_min'],
        'pullback_ratio_max': mode_params['pullback_ratio_max'],
        'volume_shrink_ratio': mode_params['volume_shrink_ratio'],
        'volume_shrink_ratio_min': mode_params.get('volume_shrink_ratio_min', 0.0),
        'take_profit': mode_params['take_profit'],
        'stop_loss': mode_params['stop_loss'],
        'hold_days': mode_params['hold_days'],
        'require_oversold': mode_params.get('require_oversold', False),
        'require_low_close': mode_params.get('require_low_close', False),
    }

    is_events = None
    oos_events = None

    try:
        hot_codes_is = []
        hot_codes_oos = []
        for fname in cache_files:
            code = fname.replace('.csv', '')
            df = load_from_cache(code)
            if df is None or len(df) < 50: continue
            df_is = df[(df['trade_date'] >= is_start) & (df['trade_date'] <= is_end)]
            df_oos = df[(df['trade_date'] >= oos_start) & (df['trade_date'] <= oos_end)]
            if len(df_is) > 0 and (df_is['pct_chg'] >= get_limit_threshold(code)).any():
                hot_codes_is.append(code)
            if len(df_oos) > 0 and (df_oos['pct_chg'] >= get_limit_threshold(code)).any():
                hot_codes_oos.append(code)

        is_events = extract_all_events(hot_codes_is, is_start, is_end, min_series_len=2)
        oos_events = extract_all_events(hot_codes_oos, oos_start, oos_end, min_series_len=2)

        _, is_metrics, is_score = evaluate_params_on_events(is_events, params)
        _, oos_metrics, oos_score = evaluate_params_on_events(oos_events, params)

        if is_metrics and oos_metrics:
            is_sharpe = is_metrics['sharpe']
            oos_sharpe = oos_metrics['sharpe']
            is_wr = is_metrics['win_rate']
            oos_wr = oos_metrics['win_rate']
            sharpe_decay = oos_sharpe - is_sharpe
            wr_decay = oos_wr - is_wr

            wf = {
                'is': {'sharpe': is_sharpe, 'win_rate': is_wr, 'avg_return': is_metrics['avg_return'],
                       'signal_count': is_metrics['signal_count']},
                'oos': {'sharpe': oos_sharpe, 'win_rate': oos_wr, 'avg_return': oos_metrics['avg_return'],
                        'signal_count': oos_metrics['signal_count']},
                'sharpe_decay': sharpe_decay,
                'wr_decay': wr_decay,
            }

            if sharpe_decay < -1.0:
                wf['verdict'] = "🔴 时间序列过拟合"
            elif sharpe_decay < -0.3:
                wf['verdict'] = "🟡 轻微时间衰减"
            else:
                wf['verdict'] = "🟢 时间稳健"

            walkforward_results[mode_name] = wf

            print(f"  IS:  Sharpe={is_sharpe:.2f} | WR={is_wr:.1%} | 信号={is_metrics['signal_count']}")
            print(f"  OOS: Sharpe={oos_sharpe:.2f} | WR={oos_wr:.1%} | 信号={oos_metrics['signal_count']}")
            print(f"  ΔSharpe={sharpe_decay:+.2f} | ΔWR={wr_decay:+.1%} → {wf['verdict']}")
        else:
            print(f"  ⚠️ IS或OOS无有效信号")
            walkforward_results[mode_name] = None

    except Exception as e:
        print(f"  ❌ Walk-forward 失败: {e}")
        walkforward_results[mode_name] = None

# ══════════════════════════════════════════════════════════════════════════════
# Step 4: 参数稳定性（在各自训练周期）
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📊 STEP 4: 参数敏感性分析（±10% 扰动）")
print("=" * 70)

sensitivity_results = {}

for mode_name, mode_params in MODES_TO_TEST.items():
    train_period = MODE_TRAIN_PERIOD[mode_name]
    events = all_period_events[train_period]

    print(f"\n  ── {mode_name} ({train_period}) ──")

    params = {
        'min_consecutive_limit_up': mode_params['min_consecutive_limit_up'],
        'min_entity_board_ratio': mode_params['min_entity_board_ratio'],
        'pullback_ratio_min': mode_params['pullback_ratio_min'],
        'pullback_ratio_max': mode_params['pullback_ratio_max'],
        'volume_shrink_ratio': mode_params['volume_shrink_ratio'],
        'volume_shrink_ratio_min': mode_params.get('volume_shrink_ratio_min', 0.0),
        'take_profit': mode_params['take_profit'],
        'stop_loss': mode_params['stop_loss'],
        'hold_days': mode_params['hold_days'],
        'require_oversold': mode_params.get('require_oversold', False),
        'require_low_close': mode_params.get('require_low_close', False),
    }

    _, base_metrics, base_score = evaluate_params_on_events(events, params)
    if base_metrics is None:
        print(f"  ⚠️ 基准参数无有效信号")
        sensitivity_results[mode_name] = None
        continue

    base_sharpe = base_metrics['sharpe']
    print(f"  基准: Sharpe={base_sharpe:.2f} | WR={base_metrics['win_rate']:.1%} | 信号={base_metrics['signal_count']}")

    cont_params = ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
                   'take_profit', 'stop_loss', 'hold_days', 'min_entity_board_ratio']

    sens_list = []
    for p in cont_params:
        if p not in params: continue
        base_val = params[p]

        # +10%
        params_up = params.copy()
        if p == 'hold_days':
            params_up[p] = int(base_val + 1)
        elif p == 'min_entity_board_ratio':
            params_up[p] = min(0.8, base_val + 0.05)
        elif p == 'stop_loss':
            params_up[p] = max(-0.20, base_val * 1.1)
        else:
            params_up[p] = round(base_val * 1.1, 3)

        _, up_metrics, _ = evaluate_params_on_events(events, params_up)
        up_sharpe = up_metrics['sharpe'] if up_metrics else None

        # -10%
        params_down = params.copy()
        if p == 'hold_days':
            params_down[p] = max(2, int(base_val - 1))
        elif p == 'min_entity_board_ratio':
            params_down[p] = max(0.1, base_val - 0.05)
        elif p == 'stop_loss':
            params_down[p] = min(-0.03, base_val * 0.9)
        else:
            params_down[p] = round(base_val * 0.9, 3)

        _, down_metrics, _ = evaluate_params_on_events(events, params_down)
        down_sharpe = down_metrics['sharpe'] if down_metrics else None

        changes = []
        if up_sharpe is not None: changes.append(abs(up_sharpe - base_sharpe))
        if down_sharpe is not None: changes.append(abs(down_sharpe - base_sharpe))
        sensitivity = float(np.mean(changes)) if changes else 0

        importance = '🔴关键' if sensitivity > 0.15 else ('🟡中等' if sensitivity > 0.05 else '🟢稳健')
        sens_list.append({
            'parameter': p, 'base_value': base_val, 'sensitivity': sensitivity,
            'up_sharpe': up_sharpe, 'down_sharpe': down_sharpe, 'importance': importance,
        })

    sens_list.sort(key=lambda x: x['sensitivity'], reverse=True)
    for s in sens_list:
        print(f"  {s['parameter']:<25} base={s['base_value']:<8} sens={s['sensitivity']:.3f} "
              f"up={s['up_sharpe'] or '—':<8} down={s['down_sharpe'] or '—':<8} → {s['importance']}")

    sensitivity_results[mode_name] = sens_list

# ══════════════════════════════════════════════════════════════════════════════
# Step 5: 综合过拟合评分
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📊 STEP 5: 综合过拟合评分")
print("=" * 70)

def of_risk_score(cv, bs, pt, wf, sens):
    """综合评估过拟合风险，返回 0-100 分（越高越可能过拟合）"""
    risk = 0
    reasons = []

    # 1. 交叉验证：OOS Sharpe 显著低于 IS
    if cv:
        is_sharpes = []
        oos_sharpes = []
        for period_name in PERIODS:
            r = cv.get(period_name)
            if r is None: continue
            if r['is_in_sample']:
                is_sharpes.append(r['sharpe'])
            else:
                oos_sharpes.append(r['sharpe'])
        if is_sharpes and oos_sharpes:
            is_mean = np.mean(is_sharpes)
            oos_mean = np.mean(oos_sharpes)
            sharpe_decay = oos_mean - is_mean
            if sharpe_decay < -2:
                risk += 30
                reasons.append(f"交叉验证 Sharpe 严重衰减 ({sharpe_decay:+.1f})")
            elif sharpe_decay < -0.5:
                risk += 15
                reasons.append(f"交叉验证 Sharpe 轻微衰减 ({sharpe_decay:+.1f})")
            if oos_mean < 0:
                risk += 30
                reasons.append(f"OOS Sharpe 为负 ({oos_mean:.1f})")

    # 2. Permutation test
    if pt:
        if pt['p_value'] > 0.10:
            risk += 25
            reasons.append(f"Permutation p={pt['p_value']:.2f}（不显著）")
        elif pt['p_value'] > 0.05:
            risk += 10
            reasons.append(f"Permutation p={pt['p_value']:.2f}（边际显著）")

    # 3. Bootstrap 置信区间下限
    if bs:
        if bs['sharpe']['lower'] < 0:
            risk += 15
            reasons.append(f"Bootstrap Sharpe 下限为负 ({bs['sharpe']['lower']:.1f})")

    # 4. Walk-forward 衰减
    if wf:
        if wf['sharpe_decay'] < -1.0:
            risk += 20
            reasons.append(f"Walk-forward Sharpe 衰减 ({wf['sharpe_decay']:+.1f})")
        elif wf['sharpe_decay'] < -0.3:
            risk += 8
            reasons.append(f"Walk-forward 轻微衰减 ({wf['sharpe_decay']:+.1f})")

    # 5. 参数敏感性（高敏感参数数量）
    if sens:
        high_sens = sum(1 for s in sens if s['sensitivity'] > 0.15)
        if high_sens >= 3:
            risk += 10
            reasons.append(f"{high_sens}个高敏感参数")

    return min(risk, 100), reasons


print(f"\n{'模式':<8} {'交叉验证':<12} {'Permutation':<14} {'Bootstrap':<14} {'Walk-forward':<14} {'参数稳定':<10} {'综合风险':<10}")
print(f"{'─'*85}")

final_report = {}
for mode_name in MODES_TO_TEST:
    cv = cv_results.get(mode_name, {})
    bs = bootstrap_results.get(mode_name)
    pt = permutation_results.get(mode_name)
    wf = walkforward_results.get(mode_name)
    sens = sensitivity_results.get(mode_name)
    risk, reasons = of_risk_score(cv, bs, pt, wf, sens)

    # 简短摘要
    cv_summary = "—"
    if cv:
        oos_sharpes = [v['sharpe'] for v in cv.values() if v and not v.get('is_in_sample')]
        if oos_sharpes:
            cv_summary = f"OOS {np.mean(oos_sharpes):.2f}"
    pt_summary = f"p={pt['p_value']:.3f}" if pt else "—"
    bs_summary = f"[{bs['sharpe']['lower']:.1f},{bs['sharpe']['upper']:.1f}]" if bs else "—"
    wf_summary = wf['verdict'] if wf else "—"
    sens_summary = f"{sum(1 for s in sens if s['sensitivity']>0.15)}关键" if sens else "—"

    if risk >= 50:
        risk_label = f"🔴 {risk}分"
    elif risk >= 25:
        risk_label = f"🟡 {risk}分"
    else:
        risk_label = f"🟢 {risk}分"

    print(f"{mode_name:<8} {cv_summary:<12} {pt_summary:<14} {bs_summary:<14} {wf_summary:<14} {sens_summary:<10} {risk_label:<10}")

    if reasons:
        for r in reasons:
            print(f"         ↳ {r}")

    final_report[mode_name] = {
        'risk_score': risk,
        'risk_label': risk_label,
        'reasons': reasons,
        'cv_summary': cv_summary,
        'permutation': pt,
        'bootstrap': bs,
        'walkforward': wf,
        'sensitivity_summary': sens_summary,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 保存完整报告
# ══════════════════════════════════════════════════════════════════════════════
output = {
    'diagnostic_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
    'cross_validation_matrix': {
        mode_name: {
            period_name: cv_results[mode_name].get(period_name)
            for period_name in PERIODS
        }
        for mode_name in MODES_TO_TEST
    },
    'bootstrap': {
        mode_name: bootstrap_results.get(mode_name)
        for mode_name in MODES_TO_TEST
    },
    'permutation': {
        mode_name: permutation_results.get(mode_name)
        for mode_name in MODES_TO_TEST
    },
    'walkforward': {
        mode_name: walkforward_results.get(mode_name)
        for mode_name in MODES_TO_TEST
    },
    'sensitivity': {
        mode_name: [
            {'parameter': s['parameter'], 'base_value': s['base_value'],
             'sensitivity': s['sensitivity'], 'importance': s['importance']}
            for s in (sensitivity_results.get(mode_name) or [])
        ]
        for mode_name in MODES_TO_TEST
    },
    'final_report': final_report,
}

output_path = os.path.join(OUTPUT_DIR, 'v6_overfitting_diagnostics.json')
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"\n✅ 完整报告已保存: {output_path}")

# ── 打印最终结论 ──
print("\n" + "=" * 70)
print("🏁 最终结论")
print("=" * 70)

worst_mode = max(final_report.items(), key=lambda x: x[1]['risk_score'])
print(f"\n  ⚠️ 最高过拟合风险: {worst_mode[0]} ({worst_mode[1]['risk_label']})")

all_good = all(v['risk_score'] < 25 for v in final_report.values())
if all_good:
    print(f"  ✅ 所有模式过拟合风险均较低，可以放心使用。")
else:
    print(f"  ⚠️ 存在过拟合风险的模式，建议：")
    for mode_name, report in final_report.items():
        if report['risk_score'] >= 50:
            print(f"    - {mode_name}: {report['risk_label']} — 建议减少参数优化自由度或增加样本外验证")
        elif report['risk_score'] >= 25:
            print(f"    - {mode_name}: {report['risk_label']} — 持续监控实盘表现")

print("\n✅ 诊断完成")
