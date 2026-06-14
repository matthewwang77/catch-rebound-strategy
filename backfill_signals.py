#!/usr/bin/env python3
"""
回填历史信号数据：
  1. 从 results_archive/ 提取所有历史候选信号 → signal_tracker.csv
  2. 用 stock_data/ 本地 CSVs 计算实际 3d/5d/7d 收益 → ai_memory.json

一次性脚本。跑完即可删除。
"""

import json
import os
import sys
import time
import pandas as pd
from datetime import datetime

# 动态导入 screener 模块
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import importlib

_screener = None

def _get_screener():
    global _screener
    if _screener is None:
        try:
            spec = importlib.util.spec_from_file_location(
                "选股new_v5", os.path.join(BASE, "选股new_v5.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _screener = mod
        except Exception as e:
            print(f"❌ 加载 screener 模块失败: {e}")
            raise
    return _screener


# ==================== 本地版 check_return_v5 ====================

def check_return_v5_local(code, signal_date, entry_price, hold_days, take_profit, stop_loss, data_dir):
    """
    离线版 check_return_v5 — 使用 stock_data/ CSVs 而非 yfinance。
    与 streamlit_app.py check_return_v5 逻辑一致（止损/止盈/到期）。
    返回: {'return_pct': float, 'exit_day': int, 'exit_reason': str} 或 None
    """
    screener = _get_screener()
    csv_path = os.path.join(data_dir, f"{code}.csv")
    if not os.path.exists(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path)
        if df.empty or len(df) < 2:
            return None

        # 解析日期
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        # 标准化列名
        rename_map = {}
        for col in df.columns:
            cl = col.lower()
            if cl == "open":
                rename_map[col] = "open"
            elif cl == "high":
                rename_map[col] = "high"
            elif cl == "low":
                rename_map[col] = "low"
            elif cl == "close":
                rename_map[col] = "close"
            elif cl == "volume":
                rename_map[col] = "volume"
        if rename_map:
            df = df.rename(columns=rename_map)

        # 找到 signal_date 之后的第一根 bar
        dt_str = str(signal_date)
        try:
            start_dt = pd.Timestamp(datetime.strptime(dt_str, "%Y%m%d"))
        except ValueError:
            return None

        mask = df.index >= start_dt
        if not mask.any():
            return None

        entry_idx = mask.argmax()
        if entry_idx + 1 >= len(df):
            return None

        effective_hold = min(hold_days, len(df) - 1 - entry_idx)
        if effective_hold <= 0:
            return None

        exit_idx_limit = min(entry_idx + hold_days, len(df) - 1)

        for i in range(entry_idx + 1, exit_idx_limit + 1):
            row = df.iloc[i]
            try:
                high, low = row["high"], row["low"]
                open_price = row["open"]
            except (KeyError, IndexError):
                continue

            if entry_price <= 0:
                continue

            # 开盘检查
            open_return = open_price / entry_price - 1
            net_open = screener.apply_trading_costs(open_return, is_sell=True)
            if net_open <= stop_loss:
                return {
                    "return_pct": round(net_open * 100, 2),
                    "exit_day": i - entry_idx,
                    "exit_reason": "止损",
                }
            if net_open >= take_profit:
                return {
                    "return_pct": round(net_open * 100, 2),
                    "exit_day": i - entry_idx,
                    "exit_reason": "止盈",
                }

            # 盘中距离优先检查（与回测完全一致）
            stop_level = entry_price * (1 + stop_loss)
            profit_level = entry_price * (1 + take_profit)
            dist_to_stop = open_price - stop_level
            dist_to_profit = profit_level - open_price

            if dist_to_stop <= dist_to_profit:
                if low / entry_price - 1 <= stop_loss:
                    net = screener.apply_trading_costs(stop_loss, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止损",
                    }
                if high / entry_price - 1 >= take_profit:
                    net = screener.apply_trading_costs(take_profit, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止盈",
                    }
            else:
                if high / entry_price - 1 >= take_profit:
                    net = screener.apply_trading_costs(take_profit, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止盈",
                    }
                if low / entry_price - 1 <= stop_loss:
                    net = screener.apply_trading_costs(stop_loss, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止损",
                    }

        # 到期退出
        final_price = df.iloc[exit_idx_limit]["close"]
        final_return = final_price / entry_price - 1 if entry_price > 0 else 0
        net_final = screener.apply_trading_costs(final_return, is_sell=True)
        is_truncated = effective_hold < hold_days
        return {
            "return_pct": round(net_final * 100, 2),
            "exit_day": effective_hold,
            "exit_reason": "到期(截断)" if is_truncated else "到期",
        }

    except Exception:
        return None


# ==================== 主逻辑 ====================

def main():
    screener = _get_screener()
    archive_dir = os.path.join(BASE, "results_archive")
    data_dir = os.path.join(BASE, "stock_data")
    tracker_path = os.path.join(BASE, "signal_tracker.csv")
    memory_path = os.path.join(BASE, "ai_memory.json")
    valid_modes = set(screener.SCREEN_MODES.keys())

    # ---- Step 1: 收集所有历史候选信号 ----
    print("📂 扫描 results_archive/ ...")
    all_signals = {}  # key: (code, signal_date, round(price,2)) → signal dict

    for fname in sorted(os.listdir(archive_dir)):
        if not fname.endswith(".json"):
            continue

        fpath = os.path.join(archive_dir, fname)
        with open(fpath) as f:
            data = json.load(f)

        scan_date = data.get("scan_date", "")
        if not scan_date:
            # 从文件名推断
            stem = fname.replace(".json", "")
            if len(stem) == 8 and stem.isdigit():
                scan_date = stem
            else:
                continue

        n_candidates = 0
        for mode, mode_data in data.get("modes", {}).items():
            if mode not in valid_modes:
                print(f"  ⏭️ 跳过无效模式: {mode}")
                continue

            for c in mode_data.get("candidates", []):
                code = c.get("code", "")
                price = c.get("price", 0)
                if not code or price <= 0:
                    continue

                signal_date = c.get("signal_date", scan_date)
                if not signal_date:
                    signal_date = scan_date

                key = (code, scan_date, round(float(price), 2))
                if key not in all_signals:
                    all_signals[key] = {
                        "date": scan_date,           # ✅ 扫描日 = 入场日期
                        "signal_date": signal_date,  # 形态完成日（参考）
                        "code": code,
                        "name": "",
                        "sector": "",
                        "mode": mode,
                        "entry_price": round(float(price), 2),
                        "pullback_pct": c.get("pullback_pct", 0),
                        "limit_days": c.get("limit_days", 0),
                    }
                    n_candidates += 1

        print(f"  ✅ {fname} — {n_candidates} 个新信号")

    signals_list = list(all_signals.values())
    print(f"\n📊 总计去重后: {len(signals_list)} 条信号")

    # ---- Step 2: 写 signal_tracker.csv ----
    df_signals = pd.DataFrame(signals_list)
    # 确保列顺序
    cols = ["date", "signal_date", "code", "mode", "entry_price", "pullback_pct", "limit_days", "name", "sector"]
    df_signals = df_signals[cols]
    df_signals.to_csv(tracker_path, index=False, encoding="utf-8-sig")
    print(f"✅ signal_tracker.csv — {len(df_signals)} 行")

    # ---- Step 3: 计算实际收益 + 填充 ai_memory.json ----
    print("\n🧮 计算实际收益 ...")
    memory = {}
    if os.path.exists(memory_path):
        try:
            with open(memory_path) as f:
                memory = json.load(f)
        except Exception:
            memory = {}

    mode_params_cache = {}
    backfill_count = 0

    for key, sig in all_signals.items():
        code = sig["code"]
        entry_date = sig["date"]          # ✅ 扫描日 = 入场日期
        signal_date = sig.get("signal_date", "")
        entry_price = sig["entry_price"]
        mode = sig["mode"]

        # 取模式参数
        if mode not in mode_params_cache:
            mp = screener.SCREEN_MODES.get(mode, screener.SCREEN_MODES.get("strict", {}))
            mode_params_cache[mode] = {
                "take_profit": mp.get("take_profit", 0.05),
                "stop_loss": mp.get("stop_loss", -0.10),
            }
        params = mode_params_cache[mode]

        # 检查是否已有同日同代码记录
        existing_dates = set()
        if code in memory:
            existing_dates = {r.get("date") for r in memory[code]}
        if entry_date in existing_dates:
            continue

        # 只对有 stock_data 本地文件的信号计算
        csv_path = os.path.join(data_dir, f"{code}.csv")
        if not os.path.exists(csv_path):
            continue

        # ✅ 只用扫描日 + 7日持有期算收益
        ret7 = check_return_v5_local(
            code, entry_date, entry_price, 7,
            params["take_profit"], params["stop_loss"], data_dir,
        )

        r7_val = ret7["return_pct"] if ret7 else None

        # ✅ 裁决逻辑：对比AI结论 vs 实际走势
        opinion = sig.get("opinion", "")
        if r7_val is not None and r7_val > 0:
            if '参与' in str(opinion):
                verdict = 'correct'
            elif '放弃' in str(opinion):
                verdict = 'missed'
            elif '观望' in str(opinion):
                verdict = 'noted_up'
            else:
                verdict = 'correct'  # fallback: 涨了就是好
        elif r7_val is not None and r7_val < 0:
            if '参与' in str(opinion):
                verdict = 'wrong'
            elif '放弃' in str(opinion):
                verdict = 'avoided'
            elif '观望' in str(opinion):
                verdict = 'noted_down'
            else:
                verdict = 'wrong'
        else:
            verdict = None

        record = {
            "date": entry_date,
            "signal_date": signal_date,
            "mode": mode,
            "entry_price": entry_price,
            "pullback_pct": sig["pullback_pct"],
            "limit_days": sig["limit_days"],
            "analysis": (
                f"[历史回填记录 — 未执行AI分析]\n"
                f"- 扫描日: {entry_date}\n"
                f"- 形态完成日: {signal_date}\n"
                f"- 入场价: {entry_price:.2f}\n"
                f"- 模式: {mode}\n"
                f"- 7日收益: {r7_val if r7_val is not None else 'N/A'}%\n"
            ),
            "sentiment": "历史回填",
            "position": "历史回填",
            "opinion": "历史回填",
            "verified": r7_val is not None,
            "return_7d": round(r7_val, 2) if r7_val is not None else None,
            "exit_reason": ret7.get("exit_reason", "") if ret7 else "",
            "exit_day": ret7.get("exit_day", 0) if ret7 else 0,
            "verdict": verdict,
            "review_analysis": None,
            "what_happened": None,
            "why_wrong": None,
            "missed_signal": None,
            "lesson": None,
        }

        if code not in memory:
            memory[code] = []
        memory[code].append(record)
        backfill_count += 1

        exit_info = ret7["exit_reason"] if ret7 else "N/A"
        ret_info = f"{r7_val:+.1f}%" if r7_val is not None else "N/A"
        print(f"  [{backfill_count}] {code} {entry_date} {mode} → 7d:{ret_info} {exit_info} | verdict={verdict}")

    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

    total_records = sum(len(v) for v in memory.values())
    print(f"\n✅ ai_memory.json — {len(memory)} 只股票, {total_records} 条记录")
    print(f"   其中新增回填: {backfill_count} 条")
    print(f"\n🎉 回填完成！")


if __name__ == "__main__":
    main()
