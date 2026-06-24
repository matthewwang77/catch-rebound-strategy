#!/usr/bin/env python3
"""Cross-validate ai_memory.json entry_prices against stock_data/ close prices.
For any record where |entry_price - actual_close| > 1%, recompute returns.
Idempotent — safe to re-run. Creates backup before writing. Supports --dry-run."""
import json, os, sys, importlib.util
from datetime import datetime
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DRY_RUN = '--dry-run' in sys.argv

# Dynamically import project modules
spec = importlib.util.spec_from_file_location("backfill_signals", os.path.join(BASE, "backfill_signals.py"))
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)

spec2 = importlib.util.spec_from_file_location("screener", os.path.join(BASE, "选股new_v5.py"))
screener = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(screener)

DATA_DIR = os.path.join(BASE, "stock_data")
AI_MEMORY = os.path.join(BASE, "ai_memory.json")

# Backup
if not DRY_RUN:
    import shutil
    backup_path = AI_MEMORY + f".bak.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(AI_MEMORY, backup_path)
    print(f"Backup: {backup_path}")

with open(AI_MEMORY, "r") as f:
    memory = json.load(f)

total_records = sum(len(records) for records in memory.values())
print(f"Loaded {len(memory)} stocks, {total_records} records")

fixed_count = 0
audit_lines = []
for code, records in memory.items():
    csv_path = os.path.join(DATA_DIR, f"{code}.csv")
    if not os.path.exists(csv_path):
        continue
    try:
        stock_df = pd.read_csv(csv_path)
        stock_df['date'] = stock_df['date'].astype(str)
    except Exception as e:
        audit_lines.append(f"SKIP {code}: cannot read CSV — {e}")
        continue

    for rec in records:
        entry_price = rec.get('entry_price', 0)
        if entry_price is None or entry_price == 0:
            continue
        entry_date = str(rec.get('date', ''))
        mode = rec.get('mode', 'strict')
        if not entry_date:
            continue

        # Try exact match first, then hyphenated format
        row_mask = stock_df['date'] == entry_date
        if not row_mask.any() and len(entry_date) == 8:
            alt_date = f"{entry_date[:4]}-{entry_date[4:6]}-{entry_date[6:]}"
            row_mask = stock_df['date'] == alt_date
        if not row_mask.any():
            audit_lines.append(f"SKIP {code} {entry_date}: date not in stock_data")
            continue

        actual_close = float(stock_df.loc[row_mask, 'close'].iloc[0])
        if actual_close <= 0 or pd.isna(actual_close):
            audit_lines.append(f"SKIP {code} {entry_date}: close={actual_close}")
            continue

        if abs(entry_price - actual_close) / actual_close <= 0.01:
            continue  # Already correct

        pct_off = (entry_price - actual_close) / actual_close * 100
        audit_lines.append(
            f"FIX {code} {entry_date}: entry_price {entry_price:.2f}→{actual_close:.2f} "
            f"(off by {pct_off:+.1f}%)"
        )

        if DRY_RUN:
            fixed_count += 1
            continue

        rec['entry_price'] = round(actual_close, 2)

        # Recompute returns with correct entry_price
        mp = screener.SCREEN_MODES.get(mode, {})
        hold_days = mp.get('hold_days', 7)
        take_profit = mp.get('take_profit', 0.054)
        stop_loss = mp.get('stop_loss', -0.09)

        try:
            result = backfill.check_return_v5_local(
                code, entry_date, actual_close,
                hold_days, take_profit, stop_loss, DATA_DIR
            )
            rec['return_7d'] = round(result['return_pct'], 2)
            rec['exit_reason'] = result['exit_reason']
            rec['exit_day'] = result['exit_day']
            rec['verified'] = True

            # Recompute verdict
            opinion = rec.get('opinion', '')
            ret = rec['return_7d']
            if '参与' in str(opinion):
                rec['verdict'] = 'correct' if ret > 0 else 'wrong'
            elif '放弃' in str(opinion):
                rec['verdict'] = 'missed' if ret > 0 else 'avoided'
            else:
                rec['verdict'] = 'noted_up' if ret > 0 else 'noted_down'
            audit_lines[-1] += f" → ret={rec['return_7d']:.1f}%, verdict={rec['verdict']}"
        except Exception as e:
            audit_lines[-1] += f" → recompute FAILED: {e}"
        fixed_count += 1

print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Fixed: {fixed_count} records")
for line in audit_lines:
    print(f"  {line}")

if not DRY_RUN and fixed_count > 0:
    # Atomic write
    tmp_path = AI_MEMORY + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp_path, AI_MEMORY)
    print(f"\nSaved ai_memory.json ({len(memory)} stocks, {sum(len(v) for v in memory.values())} records)")
elif DRY_RUN:
    print("\nDRY RUN — no changes written")
