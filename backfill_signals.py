#!/usr/bin/env python3
"""
回填历史信号数据 — 一次性离线脚本。

功能:
  1. 从 results_archive/ 目录扫描所有历史 JSON 扫描结果，提取候选信号 → signal_tracker.csv
  2. 用 stock_data/ 本地 CSVs 计算每笔信号的实际 7 日收益（含止损/止盈模拟） → ai_memory.json
  3. 对比 AI 原始结论（opinion）与实际走势，自动打 verdict 标签（correct/wrong/missed/avoided 等）

使用场景:
  - 首次部署时，将历史扫描结果批量导入 AI 记忆库
  - 为 Streamlit 复盘页面提供历史数据支撑
  - 跑完即可删除，非持续运行脚本

数据流:
  results_archive/{YYYYMMDD}.json (历史扫描结果)
    → signal_tracker.csv (信号日志，去重)
    → check_return_v5_local() 调用 stock_data/{code}.csv 模拟持仓
    → ai_memory.json (AI 记忆库，含 verdict/returns)
"""

import json
import os
import sys
import time
import pandas as pd
from datetime import datetime

# ==================== 动态导入 screener 模块 ====================
# 选股new_v5.py 不是标准 Python 包，通过 importlib 动态加载。
# 这使得本脚本可以独立运行（不需要 pip install 这个项目），
# 同时复用 apply_trading_costs() 和 SCREEN_MODES 等核心函数。

# BASE = 本脚本所在目录（即项目根目录）
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import importlib

# 模块级缓存：只加载一次，后续调用复用
_screener = None

def _get_screener():
    """
    懒加载选股new_v5模块，返回模块对象。

    使用 importlib 从文件路径动态导入，避免循环依赖和包路径问题。
    模块缓存到全局变量 _screener，多次调用只加载一次。

    Returns:
        选股new_v5 模块对象，提供 apply_trading_costs() 和 SCREEN_MODES
    """
    global _screener
    if _screener is None:
        try:
            # 从文件路径创建模块规格
            spec = importlib.util.spec_from_file_location(
                "选股new_v5", os.path.join(BASE, "选股new_v5.py")
            )
            # 根据规格创建空模块，然后执行模块代码
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _screener = mod
        except Exception as e:
            print(f"❌ 加载 screener 模块失败: {e}")
            raise
    return _screener


# ==================== 本地版 check_return_v5 ====================
# 核心收益计算函数：模拟一笔交易的完整生命周期。
#
# 与 streamlit_app.py 中的 check_return_v5 逻辑完全一致，
# 区别在于本函数读取本地 stock_data/ CSVs 而非通过 yfinance 在线获取。
#
# 止损/止盈优先级规则（与选股new_v5.py run_backtest() 完全对齐）：
#   每日按以下顺序检查：
#   1. 开盘价检查：用毛收益与毛阈值比较（不使用净收益，因为交易成本不影响触及判断）
#   2. 盘中"距离优先"检查：
#      - 计算开盘价到止损价和止盈价的距离
#      - 距离更近的那一方优先检查
#      - 若两者同时触及，优先触发距离更近的那一方
#      - 盘中用实际 high/low 价判断（非 open），因为当日极端价格可能触及阈值

def check_return_v5_local(code, entry_date, entry_price, hold_days, take_profit, stop_loss, data_dir):
    """
    离线版 check_return_v5 — 使用本地 stock_data/ CSVs 模拟持仓退出。

    模拟逻辑（逐日遍历，与回测引擎完全一致）：
      1. 从入场日次日起，逐日检查开盘价是否触发止损/止盈（毛收益 vs 毛阈值）
      2. 若开盘未触发，进入盘中距离优先检查：
         a. 计算 dist_to_stop = 开盘价 - 止损价水平
         b. 计算 dist_to_profit = 止盈价水平 - 开盘价
         c. 若 dist_to_stop <= dist_to_profit（止损更近），优先检查止损，再检查止盈
         d. 若 dist_to_profit < dist_to_stop（止盈更近），优先检查止盈，再检查止损
      3. 若持有期内未触发任何条件，持有期满后以收盘价退出

    为什么用"距离优先"规则？
      在真实交易中，价格总是先触及距离更近的价位。
      如果不分优先级、先检查止损再检查止盈，会导致止损被过度触发，
      因为在某些交易日开盘价同时远离两者时，检查顺序会影响结果。

    Args:
        code: 股票代码（如 "000001.SZ"），用于定位 CSV 文件
        entry_date: 入场日期，格式 YYYYMMDD（即扫描/信号生成日）
        entry_price: 入场价格（float）
        hold_days: 最大持有天数（int），如 7 表示持有 7 个交易日
        take_profit: 止盈阈值（如 0.05 表示 +5%）
        stop_loss: 止损阈值（如 -0.10 表示 -10%），注意是负数
        data_dir: stock_data/ 目录路径

    Returns:
        dict: {
            "return_pct": float,    # 净收益率（%），已扣除交易成本
            "exit_day": int,        # 第几天退出（1=入场次日，...，hold_days=到期）
            "exit_reason": str,     # "止损"/"止盈"/"到期"/"到期(截断)"
        }
        或 None（数据缺失、日期无效等异常情况）
    """
    screener = _get_screener()
    csv_path = os.path.join(data_dir, f"{code}.csv")
    if not os.path.exists(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path)
        if df.empty or len(df) < 2:
            return None

        # 解析日期列并设为索引，按时间排序
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

        # ---- 列名标准化：兼容大小写差异 ----
        # stock_data/ 中的 CSV 可能由不同来源生成，列名大小写不统一
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

        # ---- 定位入场日期在 DataFrame 中的位置 ----
        # 入场日 = 扫描日，从入场日次日起开始检查止损/止盈
        dt_str = str(entry_date)
        try:
            start_dt = pd.Timestamp(datetime.strptime(dt_str, "%Y%m%d"))
        except ValueError:
            return None

        # 找到 >= start_dt 的第一个交易日
        mask = df.index >= start_dt
        if not mask.any():
            return None

        # argmax() 返回第一个 True 的索引位置
        entry_idx = mask.argmax()
        # 入场日必须是倒数第二天或更早（至少还需要1天才能退出）
        if entry_idx + 1 >= len(df):
            return None

        # 实际可持有天数：min(设定持有天数, 数据剩余长度)
        effective_hold = min(hold_days, len(df) - 1 - entry_idx)
        if effective_hold <= 0:
            return None

        # 持有期最后一天的索引（以 0 为起始）
        exit_idx_limit = min(entry_idx + hold_days, len(df) - 1)

        # ---- 逐日遍历：从入场次日起，每天检查退出条件 ----
        for i in range(entry_idx + 1, exit_idx_limit + 1):
            row = df.iloc[i]
            try:
                high, low = row["high"], row["low"]
                open_price = row["open"]
            except (KeyError, IndexError):
                continue

            if entry_price <= 0:
                continue

            # ==================================================================
            # 阶段 1: 开盘价检查（H5修复：用毛收益与毛阈值比较）
            #
            # 为什么用毛收益？
            #   交易成本只在退出时扣除一次，不影响"是否触及"的判断。
            #   如果以净收益判断，会导致止损线被"抬高"（如 -10% 止损实际在 -9.5% 就触发），
            #   与回测逻辑不一致。
            # ==================================================================
            open_return = open_price / entry_price - 1  # 毛收益率（未扣成本）
            if open_return <= stop_loss:
                # 开盘直接触及止损 → 立即退出
                net = screener.apply_trading_costs(open_return, is_sell=True)
                return {
                    "return_pct": round(net * 100, 2),
                    "exit_day": i - entry_idx,
                    "exit_reason": "止损",
                }
            if open_return >= take_profit:
                # 开盘直接触及止盈 → 立即退出
                net = screener.apply_trading_costs(open_return, is_sell=True)
                return {
                    "return_pct": round(net * 100, 2),
                    "exit_day": i - entry_idx,
                    "exit_reason": "止盈",
                }

            # ==================================================================
            # 阶段 2: 盘中"距离优先"检查（与回测引擎完全一致）
            #
            # 计算开盘价到止损/止盈价的距离，距离更近的一方优先检查。
            # 这模拟了真实交易中价格总是先触及更近价位的规律。
            #
            # 注意：
            #   - 止损价 = entry_price * (1 + stop_loss)，注意 stop_loss 是负数
            #   - 止盈价 = entry_price * (1 + take_profit)
            #   - dist_to_stop 小 → 开盘价更接近止损价 → 优先检查止损
            #   - dist_to_profit 小 → 开盘价更接近止盈价 → 优先检查止盈
            # ==================================================================
            stop_level = entry_price * (1 + stop_loss)      # 止损价格水平
            profit_level = entry_price * (1 + take_profit)  # 止盈价格水平
            dist_to_stop = open_price - stop_level          # 距离止损价
            dist_to_profit = profit_level - open_price      # 距离止盈价

            if dist_to_stop <= dist_to_profit:
                # 止损更近（或等距）：优先检查止损
                # 用 low/entry_price - 1 判断，因为止损需要价格下跌触及
                if low / entry_price - 1 <= stop_loss:
                    # 按止损阈值计算收益（不是实际 low 价，与回测一致）
                    net = screener.apply_trading_costs(stop_loss, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止损",
                    }
                # 止损未触发，再检查止盈
                if high / entry_price - 1 >= take_profit:
                    net = screener.apply_trading_costs(take_profit, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止盈",
                    }
            else:
                # 止盈更近：优先检查止盈
                # 用 high/entry_price - 1 判断，因为止盈需要价格上涨触及
                if high / entry_price - 1 >= take_profit:
                    net = screener.apply_trading_costs(take_profit, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止盈",
                    }
                # 止盈未触发，再检查止损
                if low / entry_price - 1 <= stop_loss:
                    net = screener.apply_trading_costs(stop_loss, is_sell=True)
                    return {
                        "return_pct": round(net * 100, 2),
                        "exit_day": i - entry_idx,
                        "exit_reason": "止损",
                    }

        # ---- 持有期到期退出 ----
        # 所有交易日均未触发止损/止盈，以最后一个有效交易日的收盘价退出
        final_price = df.iloc[exit_idx_limit]["close"]
        final_return = final_price / entry_price - 1 if entry_price > 0 else 0
        net_final = screener.apply_trading_costs(final_return, is_sell=True)
        # 如果数据不足（实际持有天数 < 设定持有天数），标记为"截断"
        is_truncated = effective_hold < hold_days
        return {
            "return_pct": round(net_final * 100, 2),
            "exit_day": effective_hold,
            "exit_reason": "到期(截断)" if is_truncated else "到期",
        }

    except Exception as e:
        import sys
        print(f"  ⚠️ check_return_v5_local 异常: {e}", file=sys.stderr)
        return None


# ==================== 主逻辑 ====================
# 回填流程（一次性离线脚本）：
#   Step 1: 扫描 results_archive/ 目录，从所有历史 JSON 文件中提取候选信号
#   Step 2: 将去重后的信号写入 signal_tracker.csv
#   Step 3: 逐笔信号计算实际 7 日收益，生成 AI memory 记录并写入 ai_memory.json

def main():
    """
    回填历史信号主函数。

    执行流程:
      1. 扫描 results_archive/ 中所有 {YYYYMMDD}.json 文件
         - 解析 JSON，提取 mode → candidates 列表
         - 以 (code, scan_date, entry_price, mode) 四元组去重
         - 仅保留 SCREEN_MODES 中定义的有效模式（排除过时模式）
      2. 将去重信号写入 signal_tracker.csv（原子替换 .tmp → 正式文件）
      3. 逐笔计算实际收益并写入 ai_memory.json：
         - 从 SCREEN_MODES 获取每只股票对应模式的持有参数
         - 调用 check_return_v5_local() 模拟持仓到退出
         - 对比 AI 原始结论与实际走势，自动打 verdict 标签
         - 对不存在 opinion 的信号，verdict 设为 None（不猜测）
         - 对已有同日同代码记录，跳过不重复写入
         - 通过 .tmp 原子替换保证写入安全
    """
    screener = _get_screener()
    archive_dir = os.path.join(BASE, "results_archive")
    data_dir = os.path.join(BASE, "stock_data")
    tracker_path = os.path.join(BASE, "signal_tracker.csv")
    memory_path = os.path.join(BASE, "ai_memory.json")
    # 仅处理当前 SCREEN_MODES 中定义的有效模式（如 bear/strict/loose）
    valid_modes = set(screener.SCREEN_MODES.keys())

    # ==================================================================
    # Step 1: 收集所有历史候选信号
    # ==================================================================
    # 遍历 results_archive/ 中所有 {YYYYMMDD}.json 文件，
    # 解析 JSON 结构: { "scan_date": "YYYYMMDD", "modes": { "strict": { "candidates": [...] }, ... } }
    # 以 (code, scan_date, entry_price_rounded, mode) 四元组作为去重 key
    print("📂 扫描 results_archive/ ...")
    all_signals = {}  # key: (code, signal_date, round(price,2)) → signal dict

    for fname in sorted(os.listdir(archive_dir)):
        if not fname.endswith(".json"):
            continue

        fpath = os.path.join(archive_dir, fname)
        with open(fpath, encoding='utf-8') as f:
            data = json.load(f)

        # 优先使用 JSON 中的 scan_date 字段，缺失时从文件名推断
        scan_date = data.get("scan_date", "")
        if not scan_date:
            # 从文件名推断扫描日期（文件名格式: YYYYMMDD.json）
            stem = fname.replace(".json", "")
            if len(stem) == 8 and stem.isdigit():
                scan_date = stem
            else:
                continue

        n_candidates = 0
        for mode, mode_data in data.get("modes", {}).items():
            # 跳过已从 SCREEN_MODES 中移除的过时模式（如已废弃的 bull 模式）
            if mode not in valid_modes:
                print(f"  ⏭️ 跳过无效模式: {mode}")
                continue

            for c in mode_data.get("candidates", []):
                code = c.get("code", "")
                price = c.get("price", 0)
                if not code or price <= 0:
                    continue

                # 信号日期优先用候选的 signal_date，空则回退到扫描日
                signal_date = c.get("signal_date", scan_date)
                if not signal_date:
                    signal_date = scan_date

                # 四元组去重 key：同代码+同日+同价+同模式视为重复信号
                key = (code, scan_date, round(float(price), 2), mode)
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

    # ==================================================================
    # Step 2: 写 signal_tracker.csv
    # ==================================================================
    # 原子替换：先写 .tmp 文件，成功后再 rename 覆盖正式文件。
    # 这是为了防止写入过程中程序崩溃导致 CSV 损坏。
    df_signals = pd.DataFrame(signals_list)
    # 确保列顺序固定，便于后续人工查阅和脚本解析
    cols = ["date", "signal_date", "code", "mode", "entry_price", "pullback_pct", "limit_days", "name", "sector"]
    df_signals = df_signals[cols]
    tmp_path = tracker_path + ".tmp"
    df_signals.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    os.replace(tmp_path, tracker_path)
    print(f"✅ signal_tracker.csv — {len(df_signals)} 行")

    # ==================================================================
    # Step 3: 计算实际收益 + 填充 ai_memory.json
    # ==================================================================
    # 核心逻辑：
    #   a) 加载现有 ai_memory.json（如果存在）
    #   b) 对每笔信号，用对应模式的持有参数模拟持仓
    #   c) 结合 AI 原始结论（opinion）与实际收益，自动打 verdict 标签
    #   d) 原子替换写入 ai_memory.json
    print("\n🧮 计算实际收益 ...")
    memory = {}
    if os.path.exists(memory_path):
        try:
            with open(memory_path, encoding='utf-8') as f:
                memory = json.load(f)
        except Exception:
            memory = {}

    # 缓存各模式的持有参数（避免每条信号重复查询 SCREEN_MODES）
    mode_params_cache = {}
    backfill_count = 0

    for key, sig in all_signals.items():
        code = sig["code"]
        entry_date = sig["date"]          # ✅ 扫描日 = 入场日期
        signal_date = sig.get("signal_date", "")
        entry_price = sig["entry_price"]
        mode = sig["mode"]

        # 获取该模式对应的止损/止盈/持有天数参数
        if mode not in mode_params_cache:
            mp = screener.SCREEN_MODES.get(mode, screener.SCREEN_MODES.get("strict", {}))
            mode_params_cache[mode] = {
                "take_profit": mp.get("take_profit", 0.05),   # 默认 +5%
                "stop_loss": mp.get("stop_loss", -0.10),      # 默认 -10%
                "hold_days": mp.get("hold_days", 7),          # 默认 7 天
            }
        params = mode_params_cache[mode]

        # ---- 去重检查：跳过同日同代码已有记录 ----
        existing_dates = set()
        if code in memory:
            existing_dates = {r.get("date") for r in memory[code]}
        if entry_date in existing_dates:
            continue

        # ---- 仅对本地有 CSV 数据的股票计算收益 ----
        csv_path = os.path.join(data_dir, f"{code}.csv")
        if not os.path.exists(csv_path):
            continue

        # 用对应模式的持有参数模拟 7 日持仓退出
        ret7 = check_return_v5_local(
            code, entry_date, entry_price, params["hold_days"],
            params["take_profit"], params["stop_loss"], data_dir,
        )

        r7_val = ret7["return_pct"] if ret7 else None

        # ================================================================
        # 裁决逻辑（裁决矩阵 / Verdict Matrix）：对比 AI 结论 vs 实际走势
        #
        # 6 种 verdict:
        #   correct    — AI 说"参与"，实际涨了 → 正确判断
        #   wrong      — AI 说"参与"，实际跌了 → 错误判断
        #   missed     — AI 说"放弃"，实际涨了 → 错过好票
        #   avoided    — AI 说"放弃"，实际跌了 → 正确规避
        #   noted_up   — AI"观望"，实际涨了 → 中性记录（涨）
        #   noted_down — AI"观望"，实际跌了 → 中性记录（跌）
        #
        # C9 修复: 无 opinion 时不猜测 verdict，设为 None。
        # 这与 auto_daily._compute_verdict 的行为一致——
        # 历史回填的记录没有真实 AI 分析，不应该被自动裁决。
        # ================================================================
        opinion = sig.get("opinion", "")
        if not opinion:
            verdict = None
        elif r7_val is not None and r7_val > 0:
            # 实际上涨 → 判断 AI 的正确性
            if '参与' in str(opinion):
                verdict = 'correct'
            elif '放弃' in str(opinion):
                verdict = 'missed'       # AI 错过了赚钱机会
            elif '观望' in str(opinion):
                verdict = 'noted_up'
            else:
                verdict = 'correct'       # fallback: 涨了就是好
        elif r7_val is not None and r7_val < 0:
            # 实际下跌 → 判断 AI 的准确性
            if '参与' in str(opinion):
                verdict = 'wrong'         # AI 判断失误
            elif '放弃' in str(opinion):
                verdict = 'avoided'       # AI 正确规避了亏损
            elif '观望' in str(opinion):
                verdict = 'noted_down'
            else:
                verdict = 'wrong'
        else:
            # 收益结果为 None（数据缺失），不裁决
            verdict = None

        # ---- 构造 AI memory 记录 ----
        # 历史回填的记录使用占位文字（"历史回填"），与实时 AI 分析记录区分
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
            "verified": r7_val is not None,                    # 是否成功计算出收益
            "return_7d": round(r7_val, 2) if r7_val is not None else None,
            "exit_reason": ret7.get("exit_reason", "") if ret7 else "",
            "exit_day": ret7.get("exit_day", 0) if ret7 else 0,
            "verdict": verdict,
            # 复盘字段预留为 None，后续可在 Streamlit 界面中手动填写
            "review_analysis": None,
            "what_happened": None,
            "why_wrong": None,
            "missed_signal": None,
            "lesson": None,
        }

        # 按股票代码分组存储：memory[code] = [record1, record2, ...]
        if code not in memory:
            memory[code] = []
        memory[code].append(record)
        backfill_count += 1

        exit_info = ret7["exit_reason"] if ret7 else "N/A"
        ret_info = f"{r7_val:+.1f}%" if r7_val is not None else "N/A"
        print(f"  [{backfill_count}] {code} {entry_date} {mode} → 7d:{ret_info} {exit_info} | verdict={verdict}")

    # ---- 原子替换写入 ai_memory.json ----
    # 先写 .tmp 文件，成功后再 rename 覆盖正式文件，防止写入中断导致 JSON 损坏
    tmp_memory_path = memory_path + ".tmp"
    with open(tmp_memory_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    os.replace(tmp_memory_path, memory_path)

    total_records = sum(len(v) for v in memory.values())
    print(f"\n✅ ai_memory.json — {len(memory)} 只股票, {total_records} 条记录")
    print(f"   其中新增回填: {backfill_count} 条")
    print(f"\n🎉 回填完成！")


if __name__ == "__main__":
    main()
