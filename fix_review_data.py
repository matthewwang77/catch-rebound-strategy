#!/usr/bin/env python3
# 修复复盘数据工具：对 ai_memory.json 和 signal_tracker.csv 进行去重清洗，
# 并用各模式（BEAR/STRICT/LOOSE）的专属参数重新计算 return_7d，修正因时间错位导致的收益计算错误。
# 用法: python fix_review_data.py [--dry-run]
#   --dry-run: 仅预览修复结果，不写入任何文件

import json, os, sys, csv
import numpy as np
import pandas as pd

# 项目根目录绝对路径，所有文件路径以此为基准
BASE = os.path.dirname(os.path.abspath(__file__))


def _to_py(obj):
    # 递归将 numpy 标量/数组转换为 Python 原生类型，保证 json.dump 可序列化。
    # 在重算收益过程中可能产生 numpy float/int，直接序列化会报错，因此需要此递归转换。
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

# 从 选股new_v5.py 的 SCREEN_MODES 字典中动态加载各模式的回测参数。
# 使用 importlib 动态加载模块，避免循环导入，同时确保与生产环境参数完全一致。
# 返回格式: {'bear': {...}, 'strict': {...}, 'loose': {...}}
# 每个模式提取 hold_days（持仓天数）、take_profit（止盈阈值）、stop_loss（止损阈值）。
def _load_mode_params():
    # 使用 importlib 从文件路径动态加载模块，避免直接 import 导致循环依赖
    import importlib.util
    # 创建模块规格：指定模块名和文件路径
    spec = importlib.util.spec_from_file_location("screener", os.path.join(BASE, "选股new_v5.py"))
    screener = importlib.util.module_from_spec(spec)
    # 执行模块代码，加载所有函数和变量
    spec.loader.exec_module(screener)
    params = {}
    for mode in ['bear', 'strict', 'loose']:
        if mode in screener.SCREEN_MODES:
            m = screener.SCREEN_MODES[mode]
            # 只提取收益计算所需的核心参数，忽略无需的筛选参数
            params[mode] = {
                'hold_days': m['hold_days'],
                'take_profit': m['take_profit'],
                'stop_loss': m['stop_loss'],
            }
    return params

# 模块加载时立即执行，缓存为全局常量，后续函数复用
MODE_PARAMS = _load_mode_params()


# 加载 ai_memory.json 文件，返回字典。
# 文件不存在时返回空字典，避免后续操作报错。
# 数据结构: {股票代码: [记录列表], ...}，每条记录是一个包含 date/signal_date/mode/return_7d 等字段的字典。
def load_ai_memory():
    path = os.path.join(BASE, 'ai_memory.json')
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# 保存内存数据到 ai_memory.json，使用原子写入策略（先写临时文件，再 rename 覆盖）
# 防止写入过程中程序崩溃导致文件损坏。
def save_ai_memory(memory):
    path = os.path.join(BASE, 'ai_memory.json')
    tmp = path + '.tmp'  # 临时文件路径
    # 先写入临时文件，通过 _to_py 确保所有 numpy 类型已转为原生 Python 类型
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_to_py(memory), f, ensure_ascii=False, indent=2)
    # 原子替换：操作系统级别的 rename 保证要么完全成功，要么原文件完整保留
    os.replace(tmp, path)


# 对 ai_memory.json 中的记录按 (股票代码, 信号日期) 去重。
# 当同一股票在同一信号日期有多条分析记录时，保留 date（扫描/入场日期）最早的记录，
# 因为最早的记录最接近实际入场时间，其收益数据最准确。
# 返回: (去重后的 memory 字典, 移除的重复记录数)
def dedup_ai_memory(memory):
    removed = 0
    new_memory = {}
    for code, records in memory.items():
        seen = {}  # {signal_date: 当前保留的最早记录}
        for r in records:
            # signal_date 是连板检测日/信号触发日，优先使用；若无则回退到 date
            sig_date = r.get('signal_date', r.get('date', ''))
            if sig_date not in seen:
                # 首次遇到该 signal_date，直接保留
                seen[sig_date] = r
            elif r['date'] < seen[sig_date]['date']:
                # 当前记录的扫描日更早，替换之前保留的（更接近实际入场日）
                removed += 1
                seen[sig_date] = r
            else:
                # 当前记录更晚，丢弃当前记录
                removed += 1
        # 将去重后的记录列表赋值回去
        new_memory[code] = list(seen.values())
    return new_memory, removed


# 对 signal_tracker.csv 按 (code, signal_date) 去重，保留 date 最早的记录。
# signal_tracker.csv 是历史信号跟踪表，与 ai_memory.json 数据结构相似但为扁平的 CSV 格式。
# 使用 pandas 的 drop_duplicates 高效去重。
# 返回移除的重复行数。
def dedup_signal_tracker():
    tracker_path = os.path.join(BASE, 'signal_tracker.csv')
    if not os.path.exists(tracker_path):
        return 0
    df = pd.read_csv(tracker_path)
    original_len = len(df)
    # 统一转为字符串以避免类型不匹配导致去重失败
    df['date'] = df['date'].astype(str)
    df['signal_date'] = df['signal_date'].astype(str)
    # 按 date 升序排序后，drop_duplicates(keep='first') 保留最早的记录
    df = df.sort_values('date').drop_duplicates(subset=['code', 'signal_date'], keep='first')
    df.to_csv(tracker_path, index=False, encoding='utf-8')
    return original_len - len(df)


# 核心修复函数：用各模式专属参数重新计算所有记录的 return_7d 和 verdict（裁决标签）。
#
# 修复逻辑:
# 1. 使用记录的 date（扫描/入场日）而非 signal_date（连板检测日）作为回测起点。
#    因为 signal_date 可能与实际入场日相差数天，导致收益计算完全错误。
# 2. 根据每条记录所属的 mode（bear/strict/loose），从 MODE_PARAMS 获取对应的
#    hold_days/take_profit/stop_loss 参数，而非使用单一默认参数。
# 3. 调用 backfill_signals.check_return_v5_local 模拟实际交易：
#    以 entry_price 入场，按模式参数持有 hold_days 天，期间检查止盈/止损条件。
# 4. 计算完毕后，根据 AI 的原始 opinion（观点）和实际收益方向，自动重新判定 verdict:
#    - opinion 含 "参与"/"买入" 且收益>0 → correct（AI正确推荐，赚钱）
#    - opinion 含 "参与"/"买入" 且收益<=0 → wrong（AI错误推荐，亏钱）
#    - opinion 含 "放弃"/"规避" 且收益<=0 → avoided（AI正确规避，避免亏损）
#    - opinion 含 "放弃"/"规避" 且收益>0 → missed（AI错误规避，错过机会）
#    - 无明确观点 → noted_up（中性观察，涨了）或 noted_down（中性观察，跌了）
# 5. 返回实际更新的记录数。
def recompute_returns(memory):
    # 从 backfill_signals 导入回测函数，避免模块级导入导致循环依赖
    from backfill_signals import check_return_v5_local
    data_dir = os.path.join(BASE, 'stock_data')

    updated = 0
    for code, records in memory.items():
        for r in records:
            # 获取记录所属模式的参数，找不到则默认使用 strict 模式
            mode = r.get('mode', 'strict')
            mp = MODE_PARAMS.get(mode, MODE_PARAMS['strict'])

            # ✅ 关键修复：使用 date（扫描/入场日），而非 signal_date（连板检测日）
            # signal_date 与 entry_price 可能相差数天，导致收益计算完全错误
            entry_date = r['date']  # 扫描日 = 实际入场日
            ret = check_return_v5_local(
                code=code,
                entry_date=entry_date,
                entry_price=r.get('entry_price', 0),
                hold_days=mp['hold_days'],
                take_profit=mp['take_profit'],
                stop_loss=mp['stop_loss'],
                data_dir=data_dir,
            )
            if ret:  # 回测成功（数据充足、日期有效）
                r7 = round(ret['return_pct'], 2)  # 百分比收益，保留2位小数
                r['return_7d'] = r7
                r['exit_reason'] = ret.get('exit_reason', '')  # 离场原因：止盈/止损/到期
                r['exit_day'] = ret.get('exit_day', 0)  # 实际离场天数

                # 根据 AI 原始观点与实际收益方向，自动判定 verdict（裁决标签）
                opinion = r.get('opinion') or ''
                if any(kw in opinion for kw in ['参与', '买入']):
                    # AI 推荐买入：赚了=正确，亏了=错误
                    r['verdict'] = 'correct' if r7 > 0 else 'wrong'
                elif any(kw in opinion for kw in ['放弃', '规避']):
                    # AI 建议规避：跌了=正确规避，涨了=错误规避（错过机会）
                    r['verdict'] = 'avoided' if r7 <= 0 else 'missed'
                else:
                    # AI 没有明确的买卖观点，标注为中性观察
                    r['verdict'] = 'noted_up' if r7 > 0 else 'noted_down'

                r['verified'] = True  # 标记已回测验证
                updated += 1

    return updated


# 主入口函数：编排整个修复流程（加载 → 去重 → 重算收益 → 保存）。
# 支持 --dry-run 参数：仅预览不写入文件，用于验证修复逻辑是否正确。
# 修复流程:
# 1. 加载 ai_memory.json
# 2. 对 ai_memory.json 按 (code, signal_date) 去重
# 3. 用模式专属参数重新计算所有记录的 return_7d 和 verdict
# 4. [非 dry-run] 保存修复后的 ai_memory.json + 去重 signal_tracker.csv
# 5. 打印修复后的完整数据摘要
def main():
    # 检查命令行参数中是否有 --dry-run 标志
    dry_run = '--dry-run' in sys.argv

    print("=" * 60)
    print("复盘数据修复脚本")
    if dry_run:
        print("⚠️  DRY RUN 模式 — 不会写入文件")
    print("=" * 60)

    # 第1步：加载当前数据
    memory = load_ai_memory()
    total_before = sum(len(v) for v in memory.values())
    print(f"\n📂 加载 ai_memory.json: {len(memory)} 只股票, {total_before} 条记录")

    # 第2步：去重 —— 同一 (code, signal_date) 只保留最早的记录
    memory, removed = dedup_ai_memory(memory)
    total_after = sum(len(v) for v in memory.values())
    print(f"🔍 去重: {total_before} → {total_after} 条 (移除 {removed} 条重复)")

    # 第3步：用模式专属参数重算所有 return_7d 和 verdict
    updated = recompute_returns(memory)
    print(f"📊 重算收益: {updated} 条已更新")

    # 第4步：仅在非 dry-run 模式下写入文件
    if not dry_run:
        save_ai_memory(memory)
        print("💾 ai_memory.json 已保存")
        # 同步去重 signal_tracker.csv，保持两个数据源一致
        tracker_removed = dedup_signal_tracker()
        print(f"🔍 signal_tracker.csv 去重: 移除 {tracker_removed} 条")
    else:
        print("\n⚠️  DRY RUN — 未写入文件。去掉 --dry-run 以实际执行。")

    # 第5步：打印修复后的完整数据，方便人工核对
    print(f"\n{'=' * 60}")
    print("修复后数据:")
    for code, records in memory.items():
        for r in records:
            print(f"  {code} | {r['date']} | {r['mode']} | "
                  f"entry={r['entry_price']} | pullback={r['pullback_pct']}% | "
                  f"return={r.get('return_7d')}% | exit={r.get('exit_reason')} | "
                  f"verdict={r.get('verdict')}")
    print(f"\n共 {sum(len(v) for v in memory.values())} 条唯一信号")


# 脚本入口：直接运行时执行 main()
if __name__ == '__main__':
    main()
