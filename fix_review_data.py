#!/usr/bin/env python3
"""修复复盘数据：去重 + 用模式专属参数重算 return_7d。

用法: python fix_review_data.py [--dry-run]
"""

import json, os, sys, csv
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))


def _to_py(obj):
    """递归转换 numpy 类型为 Python 原生类型，确保 JSON 可序列化。"""
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

# 各模式专属参数（与 SCREEN_MODES 一致）
MODE_PARAMS = {
    'bear':   {'hold_days': 7,  'take_profit': 0.057, 'stop_loss': -0.103},
    'strict': {'hold_days': 10, 'take_profit': 0.051, 'stop_loss': -0.112},
    'loose':  {'hold_days': 7,  'take_profit': 0.05,  'stop_loss': -0.10},
}


def load_ai_memory():
    path = os.path.join(BASE, 'ai_memory.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_ai_memory(memory):
    path = os.path.join(BASE, 'ai_memory.json')
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_to_py(memory), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def dedup_ai_memory(memory):
    """按 (code, signal_date) 去重，保留 date 最早的记录。"""
    removed = 0
    new_memory = {}
    for code, records in memory.items():
        seen = {}
        for r in records:
            sig_date = r.get('signal_date', r.get('date', ''))
            if sig_date not in seen:
                seen[sig_date] = r
            elif r['date'] < seen[sig_date]['date']:
                # 当前记录更早，替换之前保留的
                removed += 1
                seen[sig_date] = r
            else:
                # 当前记录更晚，丢弃
                removed += 1
        new_memory[code] = list(seen.values())
    return new_memory, removed


def dedup_signal_tracker():
    """按 (code, signal_date) 去重 signal_tracker.csv，保留最早的 date。"""
    tracker_path = os.path.join(BASE, 'signal_tracker.csv')
    if not os.path.exists(tracker_path):
        return 0
    df = pd.read_csv(tracker_path)
    original_len = len(df)
    df['date'] = df['date'].astype(str)
    df['signal_date'] = df['signal_date'].astype(str)
    df = df.sort_values('date').drop_duplicates(subset=['code', 'signal_date'], keep='first')
    df.to_csv(tracker_path, index=False, encoding='utf-8')
    return original_len - len(df)


def recompute_returns(memory):
    """用模式专属参数重新计算所有记录的 return_7d。"""
    from backfill_signals import check_return_v5_local
    data_dir = os.path.join(BASE, 'stock_data')

    updated = 0
    for code, records in memory.items():
        for r in records:
            mode = r.get('mode', 'strict')
            mp = MODE_PARAMS.get(mode, MODE_PARAMS['strict'])

            ret = check_return_v5_local(
                code=code,
                signal_date=r.get('signal_date', r['date']),
                entry_price=r.get('entry_price', 0),
                hold_days=mp['hold_days'],
                take_profit=mp['take_profit'],
                stop_loss=mp['stop_loss'],
                data_dir=data_dir,
            )
            if ret:
                r7 = round(ret['return_pct'], 2)
                r['return_7d'] = r7
                r['exit_reason'] = ret.get('exit_reason', '')
                r['exit_day'] = ret.get('exit_day', 0)

                opinion = r.get('opinion') or ''
                if any(kw in opinion for kw in ['参与', '买入']):
                    r['verdict'] = 'correct' if r7 > 0 else 'wrong'
                elif any(kw in opinion for kw in ['放弃', '规避']):
                    r['verdict'] = 'avoided' if r7 <= 0 else 'missed'
                else:
                    r['verdict'] = 'noted_up' if r7 > 0 else 'noted_down'

                r['verified'] = True
                updated += 1

    return updated


def main():
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print("复盘数据修复脚本")
    if dry_run:
        print("⚠️  DRY RUN 模式 — 不会写入文件")
    print("=" * 60)

    memory = load_ai_memory()
    total_before = sum(len(v) for v in memory.values())
    print(f"\n📂 加载 ai_memory.json: {len(memory)} 只股票, {total_before} 条记录")

    memory, removed = dedup_ai_memory(memory)
    total_after = sum(len(v) for v in memory.values())
    print(f"🔍 去重: {total_before} → {total_after} 条 (移除 {removed} 条重复)")

    updated = recompute_returns(memory)
    print(f"📊 重算收益: {updated} 条已更新")

    if not dry_run:
        save_ai_memory(memory)
        print("💾 ai_memory.json 已保存")
        tracker_removed = dedup_signal_tracker()
        print(f"🔍 signal_tracker.csv 去重: 移除 {tracker_removed} 条")
    else:
        print("\n⚠️  DRY RUN — 未写入文件。去掉 --dry-run 以实际执行。")

    print(f"\n{'=' * 60}")
    print("修复后数据:")
    for code, records in memory.items():
        for r in records:
            print(f"  {code} | {r['date']} | {r['mode']} | "
                  f"entry={r['entry_price']} | pullback={r['pullback_pct']}% | "
                  f"return={r.get('return_7d')}% | exit={r.get('exit_reason')} | "
                  f"verdict={r.get('verdict')}")
    print(f"\n共 {sum(len(v) for v in memory.values())} 条唯一信号")


if __name__ == '__main__':
    main()
