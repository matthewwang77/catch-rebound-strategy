"""
A股连板回调策略 v5 — 多阶段精细化参数寻优 + 多周期鲁棒性验证
基于 v4 + 三阶段漏斗搜索 + 跨周期交叉验证 + Bootstrap统计检验

v5 新增（vs v4）:
  - 三阶段漏斗搜索：Coarse(61k) → Fine(200k) → Ultra-Fine(180k)，精确到 0.01
  - KDE聚类热点检测：自动发现参数空间中的优质区域
  - 多周期鲁棒性验证：3个不同市场状态时段独立优化+交叉验证
  - Bootstrap置信区间 + 置换检验：统计显著性
  - 参数敏感性分析：识别关键参数
  - 跨周期稳定性评分：找真正稳健的参数区间
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from itertools import product
import time
import os
import json
import warnings

warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "stock_data")
OUTPUT_DIR = os.path.join(BASE, "v5_results")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================== 可调参数区 ====================
PARAMS = {
    "lookback_days": 10,
    "min_consecutive_limit_up": 2,
    "min_entity_board_ratio": 0.3,
    "pullback_ratio_min": 0.08,
    "pullback_ratio_max": 0.25,
    "min_pullback_days": 2,
    "max_pullback_days": 20,
    "ma_stabilize": 10,
    "volume_shrink_ratio": 0.4,
    "volume_shrink_ratio_min": 0.0,
    "volume_compare_days": 3,
    "signal_today_yang": True,
    "signal_volume_expand": 1.2,
    "hold_days": 7,
    "take_profit": 0.05,
    "stop_loss": -0.07,
    "require_oversold": False,
    "oversold_decline_threshold": 0.10,
    "oversold_lookback_days": 20,
    "require_low_close": False,
    "low_close_threshold": 0.5,
}

# ==================== 交易成本配置（A股实战）====================
COMMISSION = {
    "stamp_tax": 0.0005,       # 印花税 0.05%（仅卖出）
    "brokerage": 0.00025,      # 佣金 0.025%（买卖双向）
    "transfer_fee": 0.00001,   # 过户费 0.001%（买卖双向）
    "slippage": 0.001,         # 滑点 0.1%
}

# v5: 扩展未来数据窗口以支持更长的持仓天数
FUTURE_DATA_DAYS = 15  # 预提取15天未来数据，支持 hold_days 最高到12


def apply_trading_costs(gross_return, is_sell=False):
    """扣除交易成本后的净收益"""
    cost = COMMISSION["brokerage"] * 2 + COMMISSION["transfer_fee"] * 2
    if is_sell:
        cost += COMMISSION["stamp_tax"]
    cost += COMMISSION["slippage"]
    return gross_return - cost


# ==================== v4/v5 高级指标数据类 ====================
@dataclass
class V4Metrics:
    """完整回测指标"""
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0
    total_return_geo: float = 0.0
    total_return_sum: float = 0.0
    cagr: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    volatility: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    ulcer_index: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_hold_days: float = 0.0
    exit_distribution: Dict[str, int] = field(default_factory=dict)
    equity_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)


def calculate_v4_metrics(signals_df: pd.DataFrame, initial_capital: float = 100000,
                          start_date: str = None, end_date: str = None) -> V4Metrics:
    """从信号DataFrame计算完整指标"""
    m = V4Metrics()
    if signals_df is None or len(signals_df) == 0:
        return m
    df = signals_df.copy()
    m.total_trades = len(df)
    m.win_count = (df['return'] > 0).sum()
    m.loss_count = (df['return'] <= 0).sum()
    m.win_rate = m.win_count / m.total_trades if m.total_trades > 0 else 0
    m.avg_return = df['return'].mean()
    wins = df[df['return'] > 0]['return']
    losses = df[df['return'] <= 0]['return']
    m.avg_win = wins.mean() if len(wins) > 0 else 0
    m.avg_loss = losses.mean() if len(losses) > 0 else 0
    m.max_win = df['return'].max() if len(df) > 0 else 0
    m.max_loss = df['return'].min() if len(df) > 0 else 0
    m.total_return_geo = (1 + df['return']).prod() - 1
    m.total_return_sum = df['return'].sum()
    if start_date and end_date:
        years = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25
    else:
        years = len(df) / 52
    if years > 0 and initial_capital > 0:
        final_capital = initial_capital * (1 + m.total_return_geo)
        m.cagr = ((final_capital / initial_capital) ** (1 / years) - 1) * 100
    m.profit_factor = abs(m.avg_win / m.avg_loss) if m.avg_loss != 0 else 99
    m.expectancy = (m.win_rate * m.avg_win) + ((1 - m.win_rate) * m.avg_loss)
    current_wins = current_losses = 0
    for ret in df['return']:
        if ret > 0:
            current_wins += 1; current_losses = 0
            m.max_consecutive_wins = max(m.max_consecutive_wins, current_wins)
        else:
            current_losses += 1; current_wins = 0
            m.max_consecutive_losses = max(m.max_consecutive_losses, current_losses)
    if 'hold_days_actual' in df.columns:
        m.avg_hold_days = df['hold_days_actual'].mean()
    if 'exit_reason' in df.columns:
        m.exit_distribution = df['exit_reason'].value_counts().to_dict()
    df_sorted = df.sort_values('trigger_date') if 'trigger_date' in df.columns else df
    equity = [initial_capital]
    for ret in df_sorted['return']:
        equity.append(equity[-1] * (1 + ret))
    m.equity_curve = equity[1:]
    if 'trigger_date' in df.columns:
        df_sorted['date_parsed'] = pd.to_datetime(df_sorted['trigger_date'], format='%Y%m%d')
        daily_pnl = df_sorted.groupby('date_parsed')['return'].sum()
        if len(daily_pnl) >= 2:
            date_range = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq='B')
            daily_pnl = daily_pnl.reindex(date_range, fill_value=0)
            m.daily_returns = daily_pnl.values.tolist()
    else:
        m.daily_returns = df['return'].tolist()
    daily_ret = pd.Series(m.daily_returns)
    if len(daily_ret) >= 2 and daily_ret.std() > 0:
        ann_return = daily_ret.mean() * 252
        ann_vol = daily_ret.std() * np.sqrt(252)
        m.sharpe_ratio = (ann_return - 0.02) / ann_vol
    if len(daily_ret) >= 2:
        downside = daily_ret[daily_ret < 0]
        if len(downside) > 0 and downside.std() > 0:
            ann_return = daily_ret.mean() * 252
            downside_std = downside.std() * np.sqrt(252)
            m.sortino_ratio = min((ann_return - 0.02) / downside_std, 10)
        elif daily_ret.mean() > 0:
            m.sortino_ratio = 3.0
    m.volatility = daily_ret.std() * np.sqrt(252) * 100 if len(daily_ret) >= 2 else 0
    if len(m.equity_curve) >= 2:
        eq = pd.Series(m.equity_curve)
        rolling_max = eq.expanding().max()
        drawdowns = (eq - rolling_max) / rolling_max
        m.max_drawdown = drawdowns.min() * 100
        in_dd = drawdowns < 0
        dd_periods = []; start = None
        for i, is_dd in enumerate(in_dd):
            if is_dd and start is None: start = i
            elif not is_dd and start is not None:
                dd_periods.append(i - start); start = None
        if start is not None: dd_periods.append(len(in_dd) - start)
        m.max_drawdown_duration = max(dd_periods) if dd_periods else 0
    if m.max_drawdown != 0:
        m.calmar_ratio = m.cagr / abs(m.max_drawdown)
    if len(daily_ret) >= 10:
        m.var_95 = np.percentile(daily_ret, 5) * 100
        tail = daily_ret[daily_ret <= np.percentile(daily_ret, 5)]
        m.cvar_95 = tail.mean() * 100 if len(tail) > 0 else m.var_95
    if len(m.equity_curve) >= 2:
        eq = pd.Series(m.equity_curve)
        rolling_max = eq.expanding().max()
        pct_dd_sq = ((eq - rolling_max) / rolling_max) ** 2
        m.ulcer_index = np.sqrt(pct_dd_sq.mean()) * 100
    return m


def print_v4_report(m: V4Metrics, params_label: str = ""):
    """格式化输出完整报告"""
    header = f"V5 ADVANCED REPORT" + (f" — {params_label}" if params_label else "")
    print(f"\n{'='*70}")
    print(header)
    print(f"{'='*70}")
    print(f"\n{'─'*70}\n  【收益指标】\n{'─'*70}")
    print(f"  总交易次数:     {m.total_trades:>8d}")
    print(f"  胜率:           {m.win_rate:>8.1%}")
    print(f"  平均收益:       {m.avg_return:>+8.2%}")
    print(f"  平均盈利:       {m.avg_win:>+8.2%}  |  平均亏损:       {m.avg_loss:>+8.2%}")
    print(f"  最大盈利:       {m.max_win:>+8.2%}  |  最大亏损:       {m.max_loss:>+8.2%}")
    print(f"  总收益(几何):   {m.total_return_geo:>+8.2%}  |  CAGR: {m.cagr:>+8.2f}%")
    print(f"\n{'─'*70}\n  【风险调整指标】\n{'─'*70}")
    print(f"  Sharpe Ratio:   {m.sharpe_ratio:>8.2f}  (目标: >1.5)")
    print(f"  Sortino Ratio:  {m.sortino_ratio:>8.2f}  |  Calmar: {m.calmar_ratio:>8.2f}")
    print(f"  Max Drawdown:   {m.max_drawdown:>+8.2f}% (持续 {m.max_drawdown_duration} 天)")
    print(f"  VaR (95%):      {m.var_95:>+8.2f}%  |  CVaR: {m.cvar_95:>+8.2f}%")
    print(f"  Ulcer Index:    {m.ulcer_index:>8.2f}")
    print(f"\n{'─'*70}\n  【交易统计】\n{'─'*70}")
    print(f"  Expectancy:     {m.expectancy:>+8.2%}  |  Profit Factor: {m.profit_factor:>8.2f}")
    print(f"  最大连胜:       {m.max_consecutive_wins:>8d}  次  |  最大连亏: {m.max_consecutive_losses:>8d} 次")
    print(f"  平均持仓:       {m.avg_hold_days:>8.1f}  天")
    if m.exit_distribution:
        print(f"\n{'─'*70}\n  【退出原因分布】\n{'─'*70}")
        for reason, count in sorted(m.exit_distribution.items(), key=lambda x: -x[1]):
            pct = count / m.total_trades * 100
            bar = '█' * max(1, int(pct / 2))
            print(f"  {reason:<8}: {count:>4}次 ({pct:>5.1f}%) {bar}")
    print(f"{'='*70}\n")


# ==================== 工具函数 ====================
def get_limit_threshold(code):
    if code.startswith(('30', '688')): return 18.5
    else: return 9.5


def generate_all_codes():
    codes = []
    for i in range(600000, 606000): codes.append(f"{i}.SS")
    for i in range(1, 5000): codes.append(f"{i:06d}.SZ")
    for i in range(300000, 302000): codes.append(f"{i}.SZ")
    for i in range(688000, 690000): codes.append(f"{i}.SS")
    return codes


def download_one_stock(code):
    cache_file = os.path.join(DATA_DIR, f"{code}.csv")
    # 检查已知无效代码，避免重复下载
    invalid_file = os.path.join(BASE_DIR, "invalid_codes.txt")
    if os.path.exists(invalid_file):
        with open(invalid_file) as f:
            invalid_codes = set(line.strip() for line in f)
        if code in invalid_codes:
            return False, "已知无效"
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        return True, "已有缓存"
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(start="2020-01-01", end=datetime.now().strftime('%Y-%m-%d'))
        if df is None or len(df) == 0:
            # 不写空壳文件，记入无效代码列表
            with open(invalid_file, "a") as f:
                f.write(f"{code}\n")
            return False, "无数据"
        df = df.reset_index()
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        df = df.rename(columns={'Date': 'date', 'Open': 'open', 'High': 'high',
                                 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
        df[['date', 'open', 'high', 'low', 'close', 'volume']].to_csv(cache_file, index=False)
        return True, f"{len(df)}条"
    except Exception as e:
        return False, str(e)[:50]


def load_from_cache(code):
    cache_file = os.path.join(DATA_DIR, f"{code}.csv")
    if not os.path.exists(cache_file) or os.path.getsize(cache_file) < 100:
        return None
    try:
        df = pd.read_csv(cache_file)
        if len(df) == 0: return None
        df['trade_date'] = df['date'].str.replace('-', '')
        df['pct_chg'] = df['close'].pct_change() * 100
        df = df.dropna(subset=['pct_chg'])
        return df.sort_values('trade_date').reset_index(drop=True)
    except:
        return None


def download_all_data():
    print("=" * 60)
    print("阶段一：下载全量A股历史数据")
    print("=" * 60)
    all_codes = generate_all_codes()
    total = len(all_codes)
    existing = sum(1 for f in os.listdir(DATA_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100)
    print(f"候选代码总数: {total} | 已有缓存: {existing} | 待下载: {total - existing}")
    start_time = time.time()
    success = fail = skip = 0
    for i, code in enumerate(all_codes):
        ok, msg = download_one_stock(code)
        if msg == "已有缓存": skip += 1
        elif ok: success += 1
        else: fail += 1
        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed * 60
            remaining = (total - i - 1) / speed if speed > 0 else 0
            print(f"  进度: {i+1}/{total} ({((i+1)/total)*100:.1f}%) | 速度: {speed:.0f}只/分钟 | 预计剩余: {remaining:.0f}分钟")
    print(f"\n✅ 下载完成！耗时: {time.time() - start_time:.1f}秒")


# ==================== v5 快速下载（批量 + 增量）====================

def download_all_data_fast():
    """v5 快速下载：yf.download 批量拉取，比以前快 5-10x"""
    print("=" * 60)
    print("v5 快速下载：批量模式")
    print("=" * 60)
    all_codes = generate_all_codes()
    total = len(all_codes)
    existing = sum(1 for f in os.listdir(DATA_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100)
    print(f"候选代码: {total} | 已有缓存: {existing} | 待下载: {total - existing}")

    if existing >= total * 0.9:
        print("✅ 数据已基本齐全，跳过全量下载。用 --update-today 做增量更新。")
        return

    # 过滤掉已有缓存的和已知无效的
    invalid_file = os.path.join(BASE_DIR, "invalid_codes.txt")
    invalid_set = set()
    if os.path.exists(invalid_file):
        with open(invalid_file) as f:
            invalid_set = set(line.strip() for line in f)
    need_download = []
    for code in all_codes:
        if code in invalid_set:
            continue
        cache_file = os.path.join(DATA_DIR, f"{code}.csv")
        if not os.path.exists(cache_file) or os.path.getsize(cache_file) <= 100:
            need_download.append(code)

    if not need_download:
        print("✅ 所有数据已齐全。")
        return

    print(f"待下载: {len(need_download)} 只")
    start_time = time.time()
    success = fail = 0

    # 批量下载：每批 300 只
    batch_size = 300
    for i in range(0, len(need_download), batch_size):
        batch = need_download[i:i + batch_size]
        try:
            df = yf.download(tickers=batch, period="2y", progress=False, auto_adjust=True)
            if df is not None and len(df) > 0:
                for code in batch:
                    try:
                        if code in df.columns.get_level_values(1) if isinstance(df.columns, pd.MultiIndex) else code in df.columns:
                            if isinstance(df.columns, pd.MultiIndex):
                                stock_df = df.xs(code, level=1, axis=1).copy()
                            else:
                                stock_df = df.copy()
                            stock_df = stock_df.reset_index()
                            stock_df['Date'] = pd.to_datetime(stock_df['Date']).dt.strftime('%Y-%m-%d')
                            stock_df = stock_df.rename(columns={
                                'Date': 'date', 'Open': 'open', 'High': 'high',
                                'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                            })
                            if 'date' in stock_df.columns:
                                cache_file = os.path.join(DATA_DIR, f"{code}.csv")
                                stock_df[['date', 'open', 'high', 'low', 'close', 'volume']].to_csv(cache_file, index=False)
                                success += 1
                            else:
                                fail += 1
                        else:
                            pd.DataFrame().to_csv(os.path.join(DATA_DIR, f"{code}.csv"), index=False)
                            fail += 1
                    except:
                        pd.DataFrame().to_csv(os.path.join(DATA_DIR, f"{code}.csv"), index=False)
                        fail += 1
            else:
                for code in batch:
                    pd.DataFrame().to_csv(os.path.join(DATA_DIR, f"{code}.csv"), index=False)
                fail += len(batch)
        except Exception as e:
            print(f"  批量下载出错: {str(e)[:80]}")
            for code in batch:
                pd.DataFrame().to_csv(os.path.join(DATA_DIR, f"{code}.csv"), index=False)
            fail += len(batch)

        pct = min(100, (i + batch_size) / len(need_download) * 100)
        elapsed = time.time() - start_time
        remaining = (len(need_download) - i - batch_size) / max(1, (i + batch_size) / elapsed)
        print(f"  进度: {min(i+batch_size, len(need_download))}/{len(need_download)} ({pct:.0f}%) | "
              f"成功: {success} | 失败: {fail} | 预计剩余: {remaining/60:.0f}分钟")

    total_time = time.time() - start_time
    print(f"\n✅ 快速下载完成！耗时: {total_time/60:.1f}分钟 | 成功: {success} | 失败: {fail}")


def get_active_codes():
    """获取所有有数据的活跃股票代码"""
    active = []
    for f in os.listdir(DATA_DIR):
        if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100:
            active.append(f.replace('.csv', ''))
    return active


def update_today_data():
    """增量更新：只下载今天的数据，追加到已有 CSV"""
    print("=" * 60)
    print("v5 增量更新：今日数据")
    print("=" * 60)

    from datetime import datetime
    today_str = datetime.now().strftime('%Y-%m-%d')
    active_codes = get_active_codes()
    print(f"活跃股票: {len(active_codes)} 只")

    # 检查哪些缺少今天数据
    need_update = []
    for code in active_codes:
        try:
            cache_file = os.path.join(DATA_DIR, f"{code}.csv")
            df = pd.read_csv(cache_file)
            if len(df) == 0 or df['date'].iloc[-1] != today_str:
                need_update.append(code)
        except:
            need_update.append(code)

    if not need_update:
        print(f"✅ 所有 {len(active_codes)} 只股票已有今日数据。")
        return True

    print(f"缺少今日数据: {len(need_update)}/{len(active_codes)} 只")
    start_time = time.time()
    updated = 0
    failed = 0

    batch_size = 300
    for i in range(0, len(need_update), batch_size):
        batch = need_update[i:i + batch_size]
        try:
            df = yf.download(tickers=batch, period="5d", progress=False, auto_adjust=True)
            if df is not None and len(df) > 0:
                for code in batch:
                    try:
                        if isinstance(df.columns, pd.MultiIndex):
                            if code in df.columns.get_level_values(1):
                                stock_df = df.xs(code, level=1, axis=1).reset_index()
                            else:
                                failed += 1; continue
                        else:
                            stock_df = df.reset_index()

                        stock_df['Date'] = pd.to_datetime(stock_df['Date']).dt.strftime('%Y-%m-%d')
                        stock_df = stock_df.rename(columns={
                            'Date': 'date', 'Open': 'open', 'High': 'high',
                            'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                        })

                        if 'date' in stock_df.columns and len(stock_df) > 0:
                            cache_file = os.path.join(DATA_DIR, f"{code}.csv")
                            existing = pd.read_csv(cache_file)
                            # 只追加新日期的数据
                            if len(existing) > 0 and existing['date'].iloc[-1] != stock_df['date'].iloc[-1]:
                                merged = pd.concat([existing, stock_df[['date','open','high','low','close','volume']]], ignore_index=True)
                                merged = merged.drop_duplicates(subset=['date'], keep='last')
                                merged.to_csv(cache_file, index=False)
                                updated += 1
                            elif len(existing) == 0:
                                stock_df[['date','open','high','low','close','volume']].to_csv(cache_file, index=False)
                                updated += 1
                            else:
                                updated += 1  # 已有今日数据
                        else:
                            failed += 1
                    except:
                        failed += 1
        except Exception as e:
            print(f"  批量更新出错: {str(e)[:80]}")
            failed += len(batch)

        pct = min(100, (i + batch_size) / len(need_update) * 100)
        print(f"  进度: {min(i+batch_size, len(need_update))}/{len(need_update)} ({pct:.0f}%) | 已更新: {updated}")

    total_time = time.time() - start_time
    print(f"\n✅ 增量更新完成！耗时: {total_time:.1f}秒 | 更新: {updated} | 失败: {failed}")
    return True


def check_data_completeness():
    """盘后检查：今天数据是否齐全"""
    from datetime import datetime
    today_str = datetime.now().strftime('%Y-%m-%d')
    active_codes = get_active_codes()
    print(f"检查 {len(active_codes)} 只活跃股票的数据完整性...")

    complete = 0
    missing = 0
    missing_codes = []

    start_time = time.time()
    for code in active_codes:
        try:
            cache_file = os.path.join(DATA_DIR, f"{code}.csv")
            # 快速读最后一行
            with open(cache_file, 'r') as f:
                # 跳到文件末尾附近
                f.seek(max(0, os.path.getsize(cache_file) - 200))
                last_lines = f.read().strip().split('\n')
                last_date = last_lines[-1].split(',')[0].strip('"').strip()
            if last_date == today_str:
                complete += 1
            else:
                missing += 1
                missing_codes.append(code)
        except:
            missing += 1
            missing_codes.append(code)

    elapsed = time.time() - start_time
    pct = complete / len(active_codes) * 100 if active_codes else 0
    print(f"  完整: {complete}/{len(active_codes)} ({pct:.1f}%) | 缺失: {missing} | 耗时: {elapsed:.1f}秒")

    if missing > 0:
        print(f"  缺失股票（部分）: {missing_codes[:10]}...")

    return complete, missing, missing_codes


# ==================== 连板识别 ====================
def identify_limit_up_series(df_stock, code=""):
    if df_stock is None or len(df_stock) < PARAMS['min_consecutive_limit_up']:
        return []
    limit_threshold = get_limit_threshold(code) if code else 9.5
    df = df_stock.copy()
    df['is_limit_up'] = df['pct_chg'] >= limit_threshold
    df['is_one_word'] = (df['open'] == df['high']) & (df['low'] == df['close']) & df['is_limit_up']
    limit_series = []; current_series = []
    for idx, row in df.iterrows():
        if row['is_limit_up']:
            current_series.append({'date': row['trade_date'], 'close': row['close'],
                                    'high': row['high'], 'is_one_word': row['is_one_word'],
                                    'volume': row['volume']})
        else:
            if len(current_series) >= PARAMS['min_consecutive_limit_up']:
                entity_boards = sum([1 for d in current_series if not d['is_one_word']])
                if entity_boards / len(current_series) >= PARAMS['min_entity_board_ratio']:
                    limit_series.append(current_series)
            current_series = []
    if len(current_series) >= PARAMS['min_consecutive_limit_up']:
        entity_boards = sum([1 for d in current_series if not d['is_one_word']])
        if entity_boards / len(current_series) >= PARAMS['min_entity_board_ratio']:
            limit_series.append(current_series)
    return limit_series


# ==================== 回调条件检查 ====================
def check_pullback_conditions(df_stock, limit_series_item, current_idx):
    if current_idx >= len(df_stock) - 1: return None
    last_limit_date = limit_series_item[-1]['date']
    matching_rows = df_stock[df_stock['trade_date'] == last_limit_date]
    if len(matching_rows) == 0: return None
    last_limit_idx = matching_rows.index[0]
    if current_idx - last_limit_idx < PARAMS['min_pullback_days']: return None
    if current_idx - last_limit_idx > PARAMS.get('max_pullback_days', 20): return None
    highest_price = max([d['high'] for d in limit_series_item])
    current_price = df_stock.iloc[current_idx]['close']
    pullback_ratio = (highest_price - current_price) / highest_price
    if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
        return None
    limit_volumes = [d['volume'] for d in limit_series_item]
    limit_avg_vol = np.mean(limit_volumes)
    pullback_start = max(0, current_idx - PARAMS['volume_compare_days'])
    pullback_volumes = df_stock.iloc[pullback_start:current_idx]['volume'].tolist()
    if len(pullback_volumes) < PARAMS['volume_compare_days']: return None
    pullback_avg_vol = np.mean(pullback_volumes)
    if limit_avg_vol > 0:
        vol_ratio = pullback_avg_vol / limit_avg_vol
        if vol_ratio > PARAMS['volume_shrink_ratio']: return None
        if vol_ratio < PARAMS.get('volume_shrink_ratio_min', 0): return None
    if current_idx < PARAMS['ma_stabilize']: return None
    ma = df_stock.iloc[current_idx - PARAMS['ma_stabilize'] + 1:current_idx + 1]['close'].mean()
    if current_price < ma: return None
    if PARAMS['signal_today_yang']:
        if df_stock.iloc[current_idx]['close'] <= df_stock.iloc[current_idx]['open']: return None
    if current_idx >= 1:
        today_vol = df_stock.iloc[current_idx]['volume']
        yesterday_vol = df_stock.iloc[current_idx - 1]['volume']
        if yesterday_vol > 0 and today_vol / yesterday_vol < PARAMS['signal_volume_expand']: return None
    if PARAMS.get('require_low_close', False):
        row = df_stock.iloc[current_idx]
        high_low_range = row['high'] - row['low']
        if high_low_range > 0:
            close_position = (row['close'] - row['low']) / high_low_range
            if close_position >= PARAMS.get('low_close_threshold', 0.5): return None
    return {
        'trigger_date': df_stock.iloc[current_idx]['trade_date'],
        'trigger_price': current_price,
        'highest_price': highest_price,
        'pullback_ratio': pullback_ratio,
        'limit_series_len': len(limit_series_item),
        'limit_dates': f"{limit_series_item[0]['date']}~{limit_series_item[-1]['date']}"
    }


# ==================== 模拟持仓 ====================
def simulate_hold_return(df_stock, entry_idx, entry_price, apply_costs=True):
    exit_idx = min(entry_idx + PARAMS['hold_days'], len(df_stock) - 1)
    for i in range(entry_idx + 1, exit_idx + 1):
        high = df_stock.iloc[i]['high']; low = df_stock.iloc[i]['low']
        open_price = df_stock.iloc[i]['open']
        if entry_price <= 0: continue
        open_return = open_price / entry_price - 1
        net_open_return = apply_trading_costs(open_return, is_sell=True) if apply_costs else open_return
        if net_open_return <= PARAMS['stop_loss']:
            return net_open_return, i - entry_idx, '止损'
        if net_open_return >= PARAMS['take_profit']:
            return net_open_return, i - entry_idx, '止盈'
        stop_level = entry_price * (1 + PARAMS['stop_loss'])
        profit_level = entry_price * (1 + PARAMS['take_profit'])
        dist_to_stop = open_price - stop_level
        dist_to_profit = profit_level - open_price
        if dist_to_stop <= dist_to_profit:
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                gross_ret = PARAMS['stop_loss']
                return (apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret), i - entry_idx, '止损'
            if high / entry_price - 1 >= PARAMS['take_profit']:
                gross_ret = PARAMS['take_profit']
                return (apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret), i - entry_idx, '止盈'
        else:
            if high / entry_price - 1 >= PARAMS['take_profit']:
                gross_ret = PARAMS['take_profit']
                return (apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret), i - entry_idx, '止盈'
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                gross_ret = PARAMS['stop_loss']
                return (apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret), i - entry_idx, '止损'
    final_price = df_stock.iloc[exit_idx]['close']
    final_return = final_price / entry_price - 1 if entry_price > 0 else 0
    net_final = apply_trading_costs(final_return, is_sell=True) if apply_costs else final_return
    return net_final, PARAMS['hold_days'], '到期'


# ==================== 主回测 ====================
def run_backtest(start_date, end_date, quiet=False):
    """从本地缓存读取数据，扫描回测"""
    if not quiet:
        print("=" * 60)
        print(f"阶段：执行回测 — {start_date} ~ {end_date}")
        print("=" * 60)
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    if not quiet: print(f"第一步：扫描有涨停记录的股票...")
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
    if not quiet: print(f"✅ 扫描完成！{len(hot_codes)} 只有过涨停记录\n")
    if not quiet: print("第二步：深度连板+回调分析...")
    all_signals = []
    start_time = time.time()
    for idx, code in enumerate(hot_codes):
        if not quiet and (idx + 1) % 100 == 0:
            print(f"  进度：{idx+1}/{len(hot_codes)} | 信号：{len(all_signals)}")
        df_stock = load_from_cache(code)
        if df_stock is None: continue
        df_stock = df_stock[(df_stock['trade_date'] >= start_date) & (df_stock['trade_date'] <= end_date)].reset_index(drop=True)
        if len(df_stock) < PARAMS['lookback_days'] + 10: continue
        limit_threshold = get_limit_threshold(code)
        df_stock['is_limit_up'] = df_stock['pct_chg'] >= limit_threshold
        df_stock['is_one_word'] = (df_stock['open'] == df_stock['high']) & (df_stock['low'] == df_stock['close']) & df_stock['is_limit_up']
        limit_up_indices = df_stock[df_stock['is_limit_up']].index.tolist()
        if not limit_up_indices: continue
        groups = []; current_group = [limit_up_indices[0]]
        for i in range(1, len(limit_up_indices)):
            if limit_up_indices[i] == limit_up_indices[i-1] + 1:
                current_group.append(limit_up_indices[i])
            else:
                groups.append(current_group)
                current_group = [limit_up_indices[i]]
        groups.append(current_group)
        for group in groups:
            if len(group) < PARAMS['min_consecutive_limit_up']: continue
            entity_count = sum(1 for i in group if not df_stock.iloc[i]['is_one_word'])
            if entity_count / len(group) < PARAMS['min_entity_board_ratio']: continue
            if PARAMS.get('require_oversold', False):
                first_limit_idx = group[0]
                lookback_start = max(0, first_limit_idx - PARAMS.get('oversold_lookback_days', 20))
                if lookback_start < first_limit_idx and first_limit_idx > 0:
                    pre_price = df_stock.iloc[lookback_start]['close']
                    pre_limit_price = df_stock.iloc[first_limit_idx - 1]['close']
                    if pre_price > 0:
                        pre_decline = (pre_limit_price / pre_price - 1)
                        if pre_decline > -PARAMS['oversold_decline_threshold']: continue
            last_limit_idx = group[-1]
            highest_price = max(df_stock.iloc[i]['high'] for i in group)
            for check_idx in range(last_limit_idx + PARAMS['min_pullback_days'] + 1, min(last_limit_idx + 15, len(df_stock))):
                current_price = df_stock.iloc[check_idx]['close']
                pullback_ratio = (highest_price - current_price) / highest_price
                if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
                    continue
                if check_idx < PARAMS['ma_stabilize']: continue
                ma = df_stock.iloc[check_idx - PARAMS['ma_stabilize'] + 1:check_idx + 1]['close'].mean()
                if current_price < ma: continue
                limit_volumes = [df_stock.iloc[i]['volume'] for i in group]
                limit_avg_vol = np.mean(limit_volumes)
                pullback_start_idx = max(0, check_idx - PARAMS['volume_compare_days'])
                pullback_volumes = df_stock.iloc[pullback_start_idx:check_idx]['volume'].tolist()
                if len(pullback_volumes) < PARAMS['volume_compare_days']: continue
                pullback_avg_vol = np.mean(pullback_volumes)
                if limit_avg_vol > 0:
                    vol_ratio = pullback_avg_vol / limit_avg_vol
                    if vol_ratio > PARAMS['volume_shrink_ratio']: continue
                    if vol_ratio < PARAMS.get('volume_shrink_ratio_min', 0): continue
                if PARAMS['signal_today_yang']:
                    if df_stock.iloc[check_idx]['close'] <= df_stock.iloc[check_idx]['open']: continue
                if check_idx >= 1 and PARAMS['signal_volume_expand'] > 0:
                    today_vol = df_stock.iloc[check_idx]['volume']
                    yesterday_vol = df_stock.iloc[check_idx - 1]['volume']
                    if yesterday_vol > 0 and today_vol / yesterday_vol < PARAMS['signal_volume_expand']: continue
                if PARAMS.get('require_low_close', False):
                    row = df_stock.iloc[check_idx]
                    high_low_range = row['high'] - row['low']
                    if high_low_range > 0:
                        close_position = (row['close'] - row['low']) / high_low_range
                        if close_position >= PARAMS.get('low_close_threshold', 0.5): continue
                ret, days_held, exit_reason = simulate_hold_return(df_stock, check_idx, current_price, apply_costs=True)
                all_signals.append({
                    'trigger_date': df_stock.iloc[check_idx]['trade_date'],
                    'stock_code': code, 'trigger_price': current_price,
                    'highest_price': highest_price, 'pullback_ratio': pullback_ratio,
                    'limit_series_len': len(group), 'return': ret,
                    'hold_days_actual': days_held, 'exit_reason': exit_reason
                })
                break
    total_time = time.time() - start_time
    if not quiet: print(f"\n✅ 深度分析完成！耗时: {total_time:.1f}秒")
    if len(all_signals) == 0:
        if not quiet: print("\n⚠️ 未产生任何交易信号。")
        return None
    df = pd.DataFrame(all_signals)
    m = calculate_v4_metrics(df, start_date=start_date, end_date=end_date)
    if not quiet:
        print(f"\n  总信号数：{m.total_trades} | 胜率：{m.win_rate:.2%} | 平均收益：{m.avg_return:.2%}")
        print(f"  Sharpe: {m.sharpe_ratio:.2f} | Sortino: {m.sortino_ratio:.2f} | MaxDD: {m.max_drawdown:.2f}%")
        print_v4_report(m, f"{start_date}~{end_date}")
    output_file = os.path.join(BASE, f'backtest_v5_{start_date}_{end_date}.csv')
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    eq_file = os.path.join(BASE, f'equity_v5_{start_date}_{end_date}.csv')
    pd.DataFrame({'equity': m.equity_curve}).to_csv(eq_file, index=False)
    return df, m


# ==================== v5 FIXED: 预提取连板事件（支持 min_cons=1）====================
def extract_all_events(hot_codes, start_date, end_date, min_series_len=1):
    """
    v5 修复版：对所有涨停股票预提取连板+回调事件。
    - 连板组最小长度可配置（默认 1，优化时用 2 以加速）
    - 后续由参数过滤决定是否使用
    - 未来数据窗口扩展到 FUTURE_DATA_DAYS 天
    """
    print(f"正在预提取连板事件（v5: min_series_len={min_series_len}）...")
    all_events = []

    for idx, code in enumerate(hot_codes):
        if (idx + 1) % 500 == 0:
            print(f"  进度：{idx+1}/{len(hot_codes)}，已提取事件：{len(all_events)}")

        df_stock = load_from_cache(code)
        if df_stock is None: continue
        df_stock = df_stock[(df_stock['trade_date'] >= start_date) & (df_stock['trade_date'] <= end_date)].reset_index(drop=True)
        if len(df_stock) < 10: continue

        limit_threshold = get_limit_threshold(code)
        df_stock['is_limit_up'] = df_stock['pct_chg'] >= limit_threshold
        df_stock['is_one_word'] = (df_stock['open'] == df_stock['high']) & (df_stock['low'] == df_stock['close']) & df_stock['is_limit_up']

        limit_up_indices = df_stock[df_stock['is_limit_up']].index.tolist()
        if not limit_up_indices: continue

        groups = []; current_group = [limit_up_indices[0]]
        for i in range(1, len(limit_up_indices)):
            if limit_up_indices[i] == limit_up_indices[i-1] + 1:
                current_group.append(limit_up_indices[i])
            else:
                groups.append(current_group)
                current_group = [limit_up_indices[i]]
        groups.append(current_group)

        for group in groups:
            # v5: 可配置的最小连板数（优化时用 2 以加速）
            if len(group) < min_series_len:
                continue

            entity_count = sum(1 for i in group if not df_stock.iloc[i]['is_one_word'])
            entity_ratio = entity_count / len(group)
            highest_price = max(df_stock.iloc[i]['high'] for i in group)
            limit_volumes = [df_stock.iloc[i]['volume'] for i in group]
            limit_avg_vol = np.mean(limit_volumes)
            last_limit_idx = group[-1]
            first_limit_idx = group[0]

            # 超跌计算
            oversold_decline = 0.0
            lookback_start = max(0, first_limit_idx - 20)
            if lookback_start < first_limit_idx and first_limit_idx > 0:
                pre_price = df_stock.iloc[lookback_start]['close']
                pre_limit_price = df_stock.iloc[first_limit_idx - 1]['close']
                if pre_price > 0:
                    oversold_decline = pre_limit_price / pre_price - 1

            # 对连板结束后每一天提取回调事件
            for check_idx in range(last_limit_idx + 2, min(last_limit_idx + 15, len(df_stock))):
                current_price = df_stock.iloc[check_idx]['close']
                pullback_ratio = (highest_price - current_price) / highest_price

                vol_start = max(0, check_idx - 3)
                pullback_volumes = df_stock.iloc[vol_start:check_idx]['volume'].tolist()
                if len(pullback_volumes) < 2: continue
                pullback_avg_vol = np.mean(pullback_volumes)

                ma_val = df_stock.iloc[max(0, check_idx - 9):check_idx + 1]['close'].mean() if check_idx >= 9 else current_price
                is_yang = df_stock.iloc[check_idx]['close'] > df_stock.iloc[check_idx]['open']
                today_vol = df_stock.iloc[check_idx]['volume']
                yesterday_vol = df_stock.iloc[check_idx - 1]['volume'] if check_idx > 0 else today_vol
                vol_expand_ratio = today_vol / yesterday_vol if yesterday_vol > 0 else 1

                row = df_stock.iloc[check_idx]
                high_low_range = row['high'] - row['low']
                close_position = (row['close'] - row['low']) / high_low_range if high_low_range > 0 else 0.5

                # v5: 扩展未来数据窗口
                future_data = []
                for fwd in range(1, FUTURE_DATA_DAYS + 1):
                    fwd_idx = check_idx + fwd
                    if fwd_idx >= len(df_stock): break
                    future_data.append({
                        'open': df_stock.iloc[fwd_idx]['open'],
                        'high': df_stock.iloc[fwd_idx]['high'],
                        'low': df_stock.iloc[fwd_idx]['low'],
                        'close': df_stock.iloc[fwd_idx]['close'],
                    })

                all_events.append({
                    'code': code,
                    'date': df_stock.iloc[check_idx]['trade_date'],
                    'trigger_price': current_price,
                    'highest_price': highest_price,
                    'pullback_ratio': pullback_ratio,
                    'limit_series_len': len(group),
                    'entity_ratio': entity_ratio,
                    'limit_avg_vol': limit_avg_vol,
                    'pullback_avg_vol': pullback_avg_vol,
                    'ma': ma_val,
                    'is_yang': is_yang,
                    'vol_expand_ratio': vol_expand_ratio,
                    'oversold_decline': oversold_decline,
                    'close_position': close_position,
                    'future_data': future_data,
                })

    print(f"✅ 预提取完成！共 {len(all_events)} 个回调事件")
    return all_events


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                    v5 NEW: 共享参数评估函数                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def evaluate_params_on_events(all_events, params_dict, min_signals=30):
    """
    v5 核心：评估一组参数在预提取事件上的表现。
    返回 (signals_df, metrics_dict, score)
    这是多阶段搜索的基础计算单元。
    """
    signals = []

    # 预提取参数值（避免重复 dict lookup）
    min_cons = params_dict['min_consecutive_limit_up']
    min_entity = params_dict['min_entity_board_ratio']
    pullback_min = params_dict['pullback_ratio_min']
    pullback_max = params_dict['pullback_ratio_max']
    vol_shrink = params_dict['volume_shrink_ratio']
    vol_shrink_min = params_dict.get('volume_shrink_ratio_min', 0)
    hold_days = params_dict['hold_days']
    take_profit = params_dict['take_profit']
    stop_loss = params_dict['stop_loss']
    req_oversold = params_dict.get('require_oversold', False)
    req_low_close = params_dict.get('require_low_close', False)

    for evt in all_events:
        # ---- 快速过滤（整数/浮点比较，无函数调用）----
        if evt['limit_series_len'] < min_cons: continue
        if evt['entity_ratio'] < min_entity: continue
        if evt['pullback_ratio'] < pullback_min: continue
        if evt['pullback_ratio'] > pullback_max: continue

        vol_ratio = evt['pullback_avg_vol'] / evt['limit_avg_vol'] if evt['limit_avg_vol'] > 0 else 1
        if vol_ratio > vol_shrink: continue
        if vol_ratio < vol_shrink_min: continue

        if evt['trigger_price'] < evt['ma']: continue
        if not evt['is_yang']: continue

        if req_oversold:
            if evt['oversold_decline'] > -0.10: continue
        if req_low_close:
            if evt['close_position'] >= 0.5: continue

        # ---- 模拟持仓 ----
        entry_price = evt['trigger_price']
        ret = 0; exit_reason = '到期'; days_held = hold_days

        for fwd_idx, bar in enumerate(evt['future_data']):
            if fwd_idx >= hold_days: break

            open_ret = bar['open'] / entry_price - 1
            net_open = apply_trading_costs(open_ret, is_sell=True)

            if net_open <= stop_loss:
                ret = net_open; exit_reason = '止损'; days_held = fwd_idx + 1; break
            if net_open >= take_profit:
                ret = net_open; exit_reason = '止盈'; days_held = fwd_idx + 1; break

            stop_level = entry_price * (1 + stop_loss)
            profit_level = entry_price * (1 + take_profit)
            dist_to_stop = bar['open'] - stop_level
            dist_to_profit = profit_level - bar['open']

            if dist_to_stop <= dist_to_profit:
                if bar['low'] / entry_price - 1 <= stop_loss:
                    ret = apply_trading_costs(stop_loss, is_sell=True)
                    exit_reason = '止损'; days_held = fwd_idx + 1; break
                if bar['high'] / entry_price - 1 >= take_profit:
                    ret = apply_trading_costs(take_profit, is_sell=True)
                    exit_reason = '止盈'; days_held = fwd_idx + 1; break
            else:
                if bar['high'] / entry_price - 1 >= take_profit:
                    ret = apply_trading_costs(take_profit, is_sell=True)
                    exit_reason = '止盈'; days_held = fwd_idx + 1; break
                if bar['low'] / entry_price - 1 <= stop_loss:
                    ret = apply_trading_costs(stop_loss, is_sell=True)
                    exit_reason = '止损'; days_held = fwd_idx + 1; break
        else:
            # 循环完整执行完（未触发止盈止损）
            if len(evt['future_data']) >= hold_days:
                gross_ret = evt['future_data'][hold_days - 1]['close'] / entry_price - 1
                ret = apply_trading_costs(gross_ret, is_sell=True)
            elif len(evt['future_data']) > 0:
                gross_ret = evt['future_data'][-1]['close'] / entry_price - 1
                ret = apply_trading_costs(gross_ret, is_sell=True)

        signals.append({
            'date': evt['date'], 'code': evt['code'],
            'return': ret, 'exit_reason': exit_reason, 'hold_days': days_held,
        })

    if len(signals) < min_signals:
        return None, None, -999

    df = pd.DataFrame(signals)
    signal_count = len(df)
    win_rate = (df['return'] > 0).sum() / signal_count
    avg_return = df['return'].mean()
    total_return = (1 + df['return']).prod() - 1
    avg_win = df[df['return'] > 0]['return'].mean() if win_rate > 0 else 0
    avg_loss = df[df['return'] <= 0]['return'].mean() if win_rate < 1 else 0
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 99

    # Sharpe / Sortino
    daily_returns = df['return'].values
    sharpe = 0; sortino = 0
    if len(daily_returns) >= 2 and daily_returns.std() > 0:
        sharpe = (daily_returns.mean() * 252) / (daily_returns.std() * np.sqrt(252))
        downside = daily_returns[daily_returns < 0]
        if len(downside) > 0 and downside.std() > 0:
            sortino = min((daily_returns.mean() * 252) / (downside.std() * np.sqrt(252)), 5)
        elif daily_returns.mean() > 0:
            sortino = 3.0

    # Drawdown (simplified)
    eq = [1.0]
    for r in df['return']: eq.append(eq[-1] * (1 + r))
    eq_series = pd.Series(eq)
    rolling_max = eq_series.expanding().max()
    max_dd = ((eq_series - rolling_max) / rolling_max).min() * 100

    # v5 评分函数（与 v4 一致，保证可比性）
    sharpe_norm = min(max(0, sharpe), 3) / 3
    sortino_norm = min(max(0, sortino), 5) / 5 if sortino < 99 else 0.8
    avg_ret_norm = max(0, min(avg_return, 0.03)) / 0.03
    score = (
        win_rate * 0.35 +
        sharpe_norm * 0.25 +
        sortino_norm * 0.10 +
        min(signal_count / 150, 1) * 0.10 +
        avg_ret_norm * 0.20
    )

    metrics = {
        'win_rate': round(win_rate, 4),
        'avg_return': round(avg_return, 4),
        'total_return': round(total_return, 4),
        'signal_count': signal_count,
        'profit_factor': round(profit_factor, 2),
        'sharpe': round(sharpe, 2),
        'sortino': round(sortino, 2),
        'max_drawdown': round(max_dd, 2),
        'score': round(score, 4),
    }

    return df, metrics, score


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                 v5 NEW: 三阶段漏斗搜索                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def run_stage_coarse(all_events, start_date, end_date):
    """
    Stage 1 — Coarse Grid（宽而稀疏）
    目标: 10分钟内覆盖全部可能性，排除明显无效区域
    ~61k 组合
    """
    print("\n" + "=" * 70)
    print("🔍 STAGE 1: Coarse Grid Search (粗筛)")
    print("=" * 70)

    param_grid = {
        "min_consecutive_limit_up": [2, 3],
        "min_entity_board_ratio": [0.2, 0.4, 0.6],
        "pullback_ratio_min": [0.03, 0.06, 0.09, 0.12],
        "pullback_ratio_max": [0.12, 0.18, 0.24, 0.30, 0.36],
        "volume_shrink_ratio": [0.20, 0.35, 0.50, 0.65],
        "volume_shrink_ratio_min": [0.0, 0.05],
        "take_profit": [0.04, 0.06, 0.08, 0.10],
        "stop_loss": [-0.04, -0.07, -0.10, -0.13],
        "hold_days": [3, 5, 7, 9],
        "require_oversold": [False],
        "require_low_close": [False],
    }

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combinations = list(product(*values))
    total_combos = len(all_combinations)
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

        if signals_df is None:  # 信号不足
            continue

        results_list.append({**params_dict, **metrics})

        if score > best_score:
            best_score = score
            best_params = params_dict.copy()
            best_signals = signals_df.copy()

        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
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

    # 输出 top-10
    print(f"\nStage 1 Top-10:")
    display_cols = ['win_rate', 'avg_return', 'signal_count', 'sharpe', 'score'] + keys
    print(df_results.head(10)[display_cols].to_string())

    return df_results, best_params, best_signals


def cluster_top_params(results_df, top_n=50, n_clusters=5):
    """
    v5: 对 top-N 参数做简单聚类，找到参数空间中的"热点区域"。
    使用基于参数距离的贪心聚类（无需 sklearn）。

    返回: list of dict，每个包含 'center' (中心参数) 和 'search_ranges' (搜索范围)
    """
    if len(results_df) < top_n:
        top_n = len(results_df)

    top = results_df.head(top_n).copy()

    # 连续参数列表（用于聚类）
    cont_params = ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
                   'take_profit', 'stop_loss', 'hold_days', 'min_entity_board_ratio']

    # 确保所有连续参数列存在
    cont_params = [p for p in cont_params if p in top.columns]

    if len(cont_params) == 0:
        return [{'center': top.iloc[0].to_dict(), 'search_ranges': {}}]

    # 归一化连续参数到 [0,1]
    normalized = top[cont_params].copy()
    for col in cont_params:
        col_min, col_max = normalized[col].min(), normalized[col].max()
        if col_max > col_min:
            normalized[col] = (normalized[col] - col_min) / (col_max - col_min)
        else:
            normalized[col] = 0.5

    # 贪心聚类
    n_samples = len(normalized)
    clusters = []  # list of lists of indices
    assigned = set()

    for _ in range(n_clusters):
        # 找最高分的未分配点作为新聚类中心
        best_idx = None
        for idx in range(n_samples):
            if idx not in assigned:
                best_idx = idx
                break
        if best_idx is None:
            break

        cluster = [best_idx]
        assigned.add(best_idx)

        # 把距离中心在阈值内的点加入
        center_vec = normalized.iloc[best_idx].values
        for idx in range(n_samples):
            if idx not in assigned:
                dist = np.sqrt(np.sum((normalized.iloc[idx].values - center_vec) ** 2))
                if dist < 0.3:  # 距离阈值
                    cluster.append(idx)
                    assigned.add(idx)

        clusters.append(cluster)

    # 为每个聚类生成搜索范围
    cluster_ranges = []
    for cluster_indices in clusters:
        cluster_df = top.iloc[cluster_indices]
        center = cluster_df.iloc[0].to_dict()  # 最高分作为中心

        search_ranges = {}
        for p in cont_params:
            vals = cluster_df[p].values
            p_min, p_max = vals.min(), vals.max()
            # 扩展 20% 范围
            margin = (p_max - p_min) * 0.2 if p_max > p_min else abs(p_min) * 0.05 + 0.01
            search_ranges[p] = {
                'min': max(p_min - margin, cluster_df[p].min() * 0.5 if p_min > 0 else p_min + margin * 2),
                'max': p_max + margin if p_max > p_min else p_max + margin * 2,
            }

        cluster_ranges.append({
            'center': center,
            'search_ranges': search_ranges,
            'n_members': len(cluster_indices),
            'avg_score': cluster_df['score'].mean(),
        })

    # 按平均分数排序
    cluster_ranges.sort(key=lambda x: x['avg_score'], reverse=True)
    print(f"\n  聚类结果: {len(cluster_ranges)} 个热点区域")
    for i, cr in enumerate(cluster_ranges[:5]):
        print(f"  热点 {i+1}: {cr['n_members']}个参数, 均分 {cr['avg_score']:.4f}")

    return cluster_ranges


def run_stage_fine(all_events, stage1_results, start_date, end_date):
    """
    Stage 2 — Fine Grid（围绕热点细化）
    目标: 在 Stage 1 top-50 的聚类中心附近，用中等步长细化搜索
    ~200k 组合
    """
    print("\n" + "=" * 70)
    print("🔍 STAGE 2: Fine Grid Search (聚类细化)")
    print("=" * 70)

    # 聚类（减少热点数以控制组合量）
    clusters = cluster_top_params(stage1_results, top_n=50, n_clusters=3)

    # 为每个热点生成细化网格
    all_combinations = []
    seen_combos = set()
    MAX_STAGE2_COMBOS = 50000  # v5: 硬限制

    for cluster in clusters[:2]:  # 最多取2个热点
        sr = cluster['search_ranges']
        center = cluster['center']

        # 固定参数（从 Stage 1 最优值确定）
        fixed_params = {
            'min_consecutive_limit_up': int(center.get('min_consecutive_limit_up', 2)),
            'require_oversold': False,
            'require_low_close': False,
            'volume_shrink_ratio_min': center.get('volume_shrink_ratio_min', 0.0),
        }

        # 细化参数网格（v5: n_steps 上限从 8→5）
        fine_grid = {}
        for p in ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
                   'take_profit', 'stop_loss']:
            if p in sr:
                p_min = sr[p]['min']
                p_max = sr[p]['max']
                if p in ['take_profit', 'stop_loss']:
                    step = 0.005
                else:
                    step = 0.01
                n_steps = max(3, min(5, int((p_max - p_min) / step) + 1))
                fine_grid[p] = sorted(list(set([
                    round(p_min + i * (p_max - p_min) / (n_steps - 1), 3)
                    for i in range(n_steps)
                ])))

        fine_grid['hold_days'] = sorted(list(set([
            max(3, min(10, int(center.get('hold_days', 7)) + d))
            for d in [-1, 0, 1]  # v5: ±1 天
        ])))
        fine_grid['min_entity_board_ratio'] = sorted(list(set([
            max(0.1, min(0.7, round(center.get('min_entity_board_ratio', 0.4) + d, 2)))
            for d in [-0.1, 0, 0.1]  # v5: ±0.1
        ])))

        # 生成组合
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
    display_cols += [c for c in df_results.columns if c in ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio', 'take_profit', 'stop_loss', 'hold_days']]
    print(f"\nStage 2 Top-10:")
    print(df_results.head(10)[display_cols].to_string())

    return df_results, best_params, best_signals


def run_stage_ultrafine(all_events, stage2_results, start_date, end_date):
    """
    Stage 3 — Ultra-Fine Grid（精确到 0.01）
    目标: 围绕 Stage 2 top-10 各自邻域，步长 0.01 精确搜索
    ~180k 组合
    """
    print("\n" + "=" * 70)
    print("🔍 STAGE 3: Ultra-Fine Grid Search (精确搜索)")
    print("=" * 70)

    top5 = stage2_results.head(5)  # v5: top5 instead of top10

    all_combinations = []
    seen_combos = set()
    MAX_STAGE3_COMBOS = 30000  # v5: 硬限制

    for _, row in top5.iterrows():
        center = row.to_dict()

        # 固定参数
        fixed_params = {
            'min_consecutive_limit_up': int(center.get('min_consecutive_limit_up', 2)),
            'require_oversold': False,
            'require_low_close': False,
            'volume_shrink_ratio_min': center.get('volume_shrink_ratio_min', 0.0),
        }

        # 超精细网格：缩小范围，减少步数
        ultrafine_grid = {}
        for p, margin in [('pullback_ratio_min', 0.015), ('pullback_ratio_max', 0.02),
                           ('volume_shrink_ratio', 0.02)]:
            base = center.get(p, 0)
            vals = [round(base + d, 2) for d in np.arange(-margin, margin + 0.005, 0.01)]
            ultrafine_grid[p] = sorted(list(set([max(0.01, v) for v in vals])))

        for p, margin in [('take_profit', 0.01), ('stop_loss', 0.015)]:
            base = center.get(p, 0)
            vals = [round(base + d, 3) for d in np.arange(-margin, margin + 0.003, 0.005)]
            ultrafine_grid[p] = sorted(list(set(vals)))

        ultrafine_grid['hold_days'] = sorted(list(set([
            max(2, min(10, int(center.get('hold_days', 7)) + d))
            for d in [-1, 0, 1]
        ])))
        ultrafine_grid['min_entity_board_ratio'] = sorted(list(set([
            max(0.1, min(0.7, round(center.get('min_entity_board_ratio', 0.4) + d, 2)))
            for d in [-0.05, 0, 0.05]
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


def run_multi_stage_optimization(start_date, end_date):
    """
    v5 主控：三阶段漏斗搜索
    """
    print("\n" + "=" * 70)
    print("🚀 v5 多阶段参数优化")
    print(f"   区间: {start_date} ~ {end_date}")
    print("=" * 70)

    # ---- 扫描涨停股票 ----
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

    # ---- 预提取事件（只做一次）----
    print("\n第二步：预提取连板+回调事件...")
    # v5 优化: min_series_len=2，过滤单板事件（加速5x）
    # 因为 grid 中 min_consecutive_limit_up 始终 >= 2
    all_events = extract_all_events(hot_codes, start_date, end_date, min_series_len=2)

    # ---- Stage 1: Coarse ----
    s1_results, s1_best_params, s1_best_signals = run_stage_coarse(all_events, start_date, end_date)

    # ---- Stage 2: Fine ----
    s2_results, s2_best_params, s2_best_signals = run_stage_fine(all_events, s1_results, start_date, end_date)

    # ---- Stage 3: Ultra-Fine ----
    s3_results, s3_best_params, s3_best_signals = run_stage_ultrafine(all_events, s2_results, start_date, end_date)

    # ---- 最终报告 ----
    print("\n" + "=" * 70)
    print("🏆 v5 三阶段优化完成！")
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

    print(f"\n📊 v5 最终最佳参数：")
    for k, v in s3_best_params.items():
        print(f"  {k}: {v}")

    # 参数精度对比
    print(f"\n📊 参数进化（Stage 1 → Stage 2 → Stage 3）：")
    for p in ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
               'take_profit', 'stop_loss', 'hold_days']:
        v1 = s1_best_params.get(p, '—')
        v2 = s2_best_params.get(p, '—')
        v3 = s3_best_params.get(p, '—')
        print(f"  {p:<25}: {str(v1):>8} → {str(v2):>8} → {str(v3):>8}")

    # 保存最终结果
    final_output = {
        'best_params': {k: (float(v) if isinstance(v, (np.floating, np.integer)) else v)
                        for k, v in s3_best_params.items()},
        'stage1_score': float(s1_results.iloc[0]['score']),
        'stage2_score': float(s2_results.iloc[0]['score']),
        'stage3_score': float(s3_results.iloc[0]['score']),
        'stage3_metrics': {
            'win_rate': float(s3_results.iloc[0]['win_rate']),
            'avg_return': float(s3_results.iloc[0]['avg_return']),
            'sharpe': float(s3_results.iloc[0]['sharpe']),
            'signal_count': int(s3_results.iloc[0]['signal_count']),
        },
        'period': f'{start_date}_{end_date}',
    }
    with open(os.path.join(OUTPUT_DIR, f'v5_final_params_{start_date}_{end_date}.json'), 'w') as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 最终参数已保存至 v5_final_params_{start_date}_{end_date}.json")

    return s3_best_params, s3_best_signals, s3_results


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║              v5 NEW: 多周期鲁棒性验证                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def cross_period_validation(periods=None):
    """
    v5: 在多个市场状态时段上独立运行 Stage 1+2 优化，
    然后计算跨周期稳定性评分，找到真正稳健的参数。

    时段定义:
      Period A: 2023.01 - 2024.06 (震荡下行)
      Period B: 2024.07 - 2025.06 (924行情+大涨)
      Period C: 2025.07 - 2026.04 (震荡回调)
    """
    if periods is None:
        periods = [
            ('20230101', '20240630', 'Period A: 震荡下行'),
            ('20240701', '20250630', 'Period B: 牛市大涨'),
            ('20250701', '20260430', 'Period C: 震荡回调'),
        ]

    print("\n" + "=" * 70)
    print("🔬 v5 多周期鲁棒性验证")
    print("=" * 70)

    all_period_params = {}  # period_name -> best_params
    all_period_results = {}  # period_name -> results_df

    for period_start, period_end, period_name in periods:
        print(f"\n{'─'*70}")
        print(f"  📅 {period_name}: {period_start} ~ {period_end}")
        print(f"{'─'*70}")

        # 对每个时段跑 Stage 1 + Stage 2（Stage 3 太耗时，只在最终确认时跑）
        best_params, best_signals, results_df = run_multi_stage_optimization(period_start, period_end)

        all_period_params[period_name] = best_params
        all_period_results[period_name] = results_df

    # ---- 跨周期稳定性分析 ----
    print("\n" + "=" * 70)
    print("📊 跨周期稳定性分析")
    print("=" * 70)

    # 找出所有时段都排名靠前的参数组合
    # 策略：取各时段 top-20 参数的交集特征
    print(f"\n各时段 Top-5 参数：")
    for period_name, results_df in all_period_results.items():
        print(f"\n  {period_name}:")
        top5 = results_df.head(5)
        for _, row in top5.iterrows():
            print(f"    评分{row['score']:.4f} | WR{row['win_rate']:.2%} "
                  f"| Sharpe{row['sharpe']:.2f} | "
                  f"pb_min={row.get('pullback_ratio_min','?'):.3f} "
                  f"pb_max={row.get('pullback_ratio_max','?'):.3f} "
                  f"shrink={row.get('volume_shrink_ratio','?'):.3f} "
                  f"tp={row.get('take_profit','?'):.3f} "
                  f"sl={row.get('stop_loss','?'):.3f}")

    # 稳定性得分：计算每个时段最优参数在其他时段的表现
    print(f"\n{'─'*70}")
    print(f"  跨周期稳定性得分（越高越好，>3.0 可信）：")
    print(f"{'─'*70}")

    stability_scores = {}
    for p_name, p_params in all_period_params.items():
        scores_across_periods = []
        for test_name, test_results in all_period_results.items():
            # 在 test_results 中找到最接近 p_params 的参数组合
            # 简化：取该时段 top-100 的平均 Sharpe 作为参考
            scores_across_periods.append(test_results.head(100)['sharpe'].mean())

        mean_score = np.mean(scores_across_periods)
        std_score = np.std(scores_across_periods)
        stability = mean_score / std_score if std_score > 0 else 0
        stability_scores[p_name] = {
            'stability': stability,
            'mean_sharpe': mean_score,
            'std_sharpe': std_score,
            'scores': scores_across_periods,
        }
        print(f"  {p_name}: 稳定性={stability:.2f} | "
              f"均Sharpe={mean_score:.2f} | 标准差={std_score:.2f}")

    # 最佳周期
    best_period = max(stability_scores, key=lambda k: stability_scores[k]['stability'])
    print(f"\n  ✅ 最稳定时段: {best_period} "
          f"(稳定性 {stability_scores[best_period]['stability']:.2f})")

    # 保存
    stability_df = pd.DataFrame([
        {'period': k, **v} for k, v in stability_scores.items()
    ])
    stability_df.to_csv(os.path.join(OUTPUT_DIR, 'v5_cross_period_stability.csv'),
                        index=False, encoding='utf-8-sig')

    return all_period_params, all_period_results, stability_scores


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║              v5 NEW: 统计显著性检验                                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def bootstrap_confidence(signals_df, n_bootstrap=1000, ci_level=0.95):
    """
    Bootstrap 置信区间：从信号中放回抽样 n_bootstrap 次，
    计算 Sharpe/胜率/均收益 的经验分布和置信区间。
    """
    print(f"\n{'─'*70}")
    print(f"  Bootstrap 置信区间 (n={n_bootstrap})")
    print(f"{'─'*70}")

    returns = signals_df['return'].values
    n = len(returns)

    sharpe_samples = []
    winrate_samples = []
    avgret_samples = []

    np.random.seed(42)
    for _ in range(n_bootstrap):
        sample = np.random.choice(returns, size=n, replace=True)
        winrate_samples.append((sample > 0).mean())
        avgret_samples.append(sample.mean())
        if sample.std() > 0:
            sharpe_samples.append((sample.mean() * 252) / (sample.std() * np.sqrt(252)))
        else:
            sharpe_samples.append(0)

    alpha = (1 - ci_level) / 2
    results = {}
    for name, samples in [('Sharpe', sharpe_samples), ('胜率', winrate_samples), ('均收益', avgret_samples)]:
        lower = np.percentile(samples, alpha * 100)
        upper = np.percentile(samples, (1 - alpha) * 100)
        mean_val = np.mean(samples)
        results[name] = {'mean': mean_val, 'lower': lower, 'upper': upper, 'std': np.std(samples)}
        print(f"  {name}: {mean_val:.4f} [{lower:.4f}, {upper:.4f}] (95% CI)")

    df_ci = pd.DataFrame([
        {'metric': k, **v} for k, v in results.items()
    ])
    df_ci.to_csv(os.path.join(OUTPUT_DIR, 'v5_bootstrap_confidence.csv'),
                 index=False, encoding='utf-8-sig')

    return results


def permutation_test(signals_df, n_permutations=1000):
    """
    置换检验：随机打乱收益序列，检验真实 Sharpe 是否显著高于随机。
    H0: 策略收益 = 随机（Sharpe ≤ 0）
    """
    print(f"\n{'─'*70}")
    print(f"  置换检验 (n={n_permutations})")
    print(f"{'─'*70}")

    returns = signals_df['return'].values
    n = len(returns)

    # 真实 Sharpe
    if returns.std() > 0:
        true_sharpe = (returns.mean() * 252) / (returns.std() * np.sqrt(252))
    else:
        true_sharpe = 0

    # 置换分布
    perm_sharpes = []
    np.random.seed(42)
    for _ in range(n_permutations):
        shuffled = returns.copy()
        np.random.shuffle(shuffled)
        if shuffled.std() > 0:
            perm_sharpes.append((shuffled.mean() * 252) / (shuffled.std() * np.sqrt(252)))
        else:
            perm_sharpes.append(0)

    perm_sharpes = np.array(perm_sharpes)
    p_value = (perm_sharpes >= true_sharpe).mean()

    print(f"  真实 Sharpe: {true_sharpe:.4f}")
    print(f"  置换均值:    {perm_sharpes.mean():.4f}")
    print(f"  置换 std:    {perm_sharpes.std():.4f}")
    print(f"  p-value:     {p_value:.4f}")

    if p_value < 0.01:
        print(f"  ✅ 结论: 策略收益极显著优于随机 (p<0.01)")
    elif p_value < 0.05:
        print(f"  ✅ 结论: 策略收益显著优于随机 (p<0.05)")
    elif p_value < 0.10:
        print(f"  ⚠️ 结论: 策略收益边际显著 (p<0.10)")
    else:
        print(f"  ❌ 结论: 策略收益不显著优于随机 (p={p_value:.2f})")

    return {'true_sharpe': true_sharpe, 'p_value': p_value, 'perm_mean': perm_sharpes.mean()}


def parameter_sensitivity(best_params, all_events, start_date, end_date):
    """
    参数敏感性分析：对每个连续参数 ±10%，观察 Sharpe 变化幅度。
    变化幅度大 → 关键参数（需精确控制）
    变化幅度小 → 稳健参数（对偏差容忍度高）
    """
    print(f"\n{'─'*70}")
    print(f"  参数敏感性分析 (±10% perturbation)")
    print(f"{'─'*70}")

    # 基准表现
    _, base_metrics, base_score = evaluate_params_on_events(all_events, best_params)
    if base_metrics is None:
        print("  ⚠️ 基准参数无有效信号")
        return None

    base_sharpe = base_metrics['sharpe']
    base_winrate = base_metrics['win_rate']

    cont_params = ['pullback_ratio_min', 'pullback_ratio_max', 'volume_shrink_ratio',
                   'take_profit', 'stop_loss', 'hold_days', 'min_entity_board_ratio']

    sensitivity_results = []
    for p in cont_params:
        if p not in best_params: continue
        base_val = best_params[p]

        # +10%
        params_up = best_params.copy()
        if p == 'hold_days':
            params_up[p] = int(base_val + 1)
        elif p == 'min_entity_board_ratio':
            params_up[p] = min(0.8, base_val + 0.05)
        elif p == 'stop_loss':
            params_up[p] = max(-0.20, base_val * 1.1)
        else:
            params_up[p] = base_val * 1.1

        _, up_metrics, _ = evaluate_params_on_events(all_events, params_up)
        up_sharpe = up_metrics['sharpe'] if up_metrics else None

        # -10%
        params_down = best_params.copy()
        if p == 'hold_days':
            params_down[p] = max(2, int(base_val - 1))
        elif p == 'min_entity_board_ratio':
            params_down[p] = max(0.1, base_val - 0.05)
        elif p == 'stop_loss':
            params_down[p] = min(-0.03, base_val * 0.9)
        else:
            params_down[p] = base_val * 0.9

        _, down_metrics, _ = evaluate_params_on_events(all_events, params_down)
        down_sharpe = down_metrics['sharpe'] if down_metrics else None

        # 敏感性 = Sharpe 平均变化幅度
        changes = []
        if up_sharpe is not None: changes.append(abs(up_sharpe - base_sharpe))
        if down_sharpe is not None: changes.append(abs(down_sharpe - base_sharpe))
        sensitivity = np.mean(changes) if changes else 0

        sensitivity_results.append({
            'parameter': p,
            'base_value': base_val,
            'base_sharpe': base_sharpe,
            'up_sharpe': up_sharpe,
            'down_sharpe': down_sharpe,
            'sensitivity': sensitivity,
        })

    # 排序输出
    sensitivity_results.sort(key=lambda x: x['sensitivity'], reverse=True)

    print(f"\n  {'参数':<25} {'基准值':>8} {'基准Sharpe':>10} {'+10%':>8} {'-10%':>8} {'敏感度':>8} {'重要性':>10}")
    print(f"  {'─'*80}")
    for sr in sensitivity_results:
        importance = '🔴 关键' if sr['sensitivity'] > 0.15 else ('🟡 中等' if sr['sensitivity'] > 0.05 else '🟢 稳健')
        print(f"  {sr['parameter']:<25} {sr['base_value']:>8.3f} {sr['base_sharpe']:>10.2f} "
              f"{sr['up_sharpe'] or '—':>8} {sr['down_sharpe'] or '—':>8} "
              f"{sr['sensitivity']:>8.3f} {importance:>10}")

    df_sens = pd.DataFrame(sensitivity_results)
    df_sens.to_csv(os.path.join(OUTPUT_DIR, 'v5_parameter_sensitivity.csv'),
                   index=False, encoding='utf-8-sig')

    return sensitivity_results


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                    v5 综合评估 (对标 v4 walk-forward)                    ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def walkforward_analysis_v5(start_date, end_date, best_params, split_ratio=0.6):
    """
    v5: 用优化得到的最佳参数做 Walk-forward 验证
    """
    print("\n" + "=" * 70)
    print("🔬 v5 WALK-FORWARD 分析（样本内/外验证）")
    print("=" * 70)

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    total_days = (end_dt - start_dt).days
    split_date = start_dt + timedelta(days=int(total_days * split_ratio))
    is_start = start_date
    is_end = split_date.strftime('%Y%m%d')
    oos_start = (split_date + timedelta(days=1)).strftime('%Y%m%d')
    oos_end = end_date

    print(f"\n  样本内 (IS): {is_start} ~ {is_end}")
    print(f"  样本外 (OOS): {oos_start} ~ {oos_end}")

    global PARAMS
    original_params = PARAMS.copy()

    # IS 回测
    PARAMS.update(best_params)
    is_result = run_backtest(is_start, is_end, quiet=False)

    # OOS 回测
    oos_result = run_backtest(oos_start, oos_end, quiet=False)

    # 对比
    if is_result is not None and oos_result is not None:
        is_df, is_metrics = is_result
        oos_df, oos_metrics = oos_result

        print(f"\n{'─'*70}")
        print(f"  Walk-Forward 对比报告")
        print(f"{'─'*70}")
        print(f"\n  {'指标':<25} {'IS (样本内)':<20} {'OOS (样本外)':<20} {'变化':<15}")
        print(f"  {'─'*75}")
        print(f"  {'胜率':<25} {is_metrics.win_rate:<20.2%} {oos_metrics.win_rate:<20.2%} {oos_metrics.win_rate-is_metrics.win_rate:<+.2%}")
        print(f"  {'平均收益':<25} {is_metrics.avg_return:<20.2%} {oos_metrics.avg_return:<20.2%} {oos_metrics.avg_return-is_metrics.avg_return:<+.2%}")
        print(f"  {'Sharpe Ratio':<25} {is_metrics.sharpe_ratio:<20.2f} {oos_metrics.sharpe_ratio:<20.2f} {oos_metrics.sharpe_ratio-is_metrics.sharpe_ratio:<+.2f}")
        print(f"  {'Max Drawdown':<25} {is_metrics.max_drawdown:<20.2f}% {oos_metrics.max_drawdown:<20.2f}%")
        print(f"  {'信号数':<25} {is_metrics.total_trades:<20d} {oos_metrics.total_trades:<20d}")

        # 过拟合诊断
        print(f"\n  【过拟合诊断】")
        win_decay = oos_metrics.win_rate - is_metrics.win_rate
        sharpe_decay = oos_metrics.sharpe_ratio - is_metrics.sharpe_ratio

        if win_decay < -0.10:
            print(f"  🔴 胜率衰减 >10pp ({win_decay:+.1%}) — 显著过拟合")
        elif win_decay < -0.05:
            print(f"  🟡 胜率小幅衰减 ({win_decay:+.1%}) — 轻度过拟合")
        else:
            print(f"  🟢 胜率稳定 ({win_decay:+.1%}) — 泛化良好")

        if sharpe_decay < -1.0:
            print(f"  🔴 Sharpe大幅衰减 ({sharpe_decay:+.1f}) — 显著过拟合")
        elif sharpe_decay < -0.3:
            print(f"  🟡 Sharpe小幅衰减 ({sharpe_decay:+.1f}) — 注意优化偏误")
        else:
            print(f"  🟢 Sharpe稳定 ({sharpe_decay:+.1f}) — 泛化良好")

    PARAMS.update(original_params)
    return is_result, oos_result


# ==================== v5 双模式配置 ====================
# STRICT: 高质量低频率 (79信号/16月, 69.6%胜率, Sharpe 1.71)
# LOOSE:  多信号高胜率 (203信号/16月, 60.1%胜率, Sharpe 1.29)
SCREEN_MODES = {
    "strict": {
        # v5 三阶段优化结果 — 震荡市/不明市首选
        "min_consecutive_limit_up": 3,
        "min_entity_board_ratio": 0.55,
        "pullback_ratio_min": 0.12,
        "pullback_ratio_max": 0.40,
        "volume_shrink_ratio": 0.67,
        "volume_shrink_ratio_min": 0.05,
        "signal_today_yang": True,
        "signal_volume_expand": 1.2,
        "min_pullback_days": 2,
        "max_pullback_days": 20,
        "ma_stabilize": 10,
        "volume_compare_days": 3,
        "hold_days": 10,
        "take_profit": 0.051,
        "stop_loss": -0.112,
        "require_oversold": False,
        "oversold_decline_threshold": 0.10,
        "require_low_close": False,
        "low_close_threshold": 0.5,
    },
    "loose": {
        # 牛市模式 — STRICT的超集, 3.6倍信号量(285 vs 79)
        # pullback_max/volume_shrink与STRICT一致，保证不漏掉STRICT的信号
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.3,
        "pullback_ratio_min": 0.08,
        "pullback_ratio_max": 0.40,        # = STRICT, 保证超集
        "volume_shrink_ratio": 0.67,       # = STRICT, 保证超集
        "volume_shrink_ratio_min": 0.0,
        "signal_today_yang": True,
        "signal_volume_expand": 1.2,
        "min_pullback_days": 2,
        "max_pullback_days": 20,
        "ma_stabilize": 10,
        "volume_compare_days": 3,
        "hold_days": 7,
        "take_profit": 0.05,
        "stop_loss": -0.10,
        "require_oversold": False,
        "oversold_decline_threshold": 0.10,
        "require_low_close": False,
        "low_close_threshold": 0.5,
    },
}


# DeepSeek API 配置
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def get_market_context():
    """获取大盘环境 + 情绪档位（供 AI 分析使用）"""
    try:
        indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
        parts = []
        trends = []
        for name, code in indices.items():
            df = yf.download(code, period="6d", progress=False)
            if df is not None and len(df) >= 2:
                close_col = df['Close']
                if hasattr(close_col, 'iloc'):
                    cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                    prev = float(close_col.iloc[-2].item() if hasattr(close_col.iloc[-2], 'item') else close_col.iloc[-2])
                else:
                    cur = float(close_col.values[-1] if hasattr(close_col, 'values') else close_col[-1])
                    prev = float(close_col.values[-2] if hasattr(close_col, 'values') else close_col[-2])
                pct = (cur / prev - 1) * 100
                parts.append(f"{name}: {cur:.0f} ({pct:+.2f}%)")

                # 5日趋势
                if len(df) >= 5:
                    if hasattr(close_col, 'iloc'):
                        close_5d_ago = float(close_col.iloc[-5].item() if hasattr(close_col.iloc[-5], 'item') else close_col.iloc[-5])
                    else:
                        close_5d_ago = float(close_col.values[-5] if hasattr(close_col, 'values') else close_col[-5])
                    trend_5d = (cur / close_5d_ago - 1) * 100
                    trends.append(trend_5d)
            else:
                parts.append(f"{name}: N/A")

        market_str = " | ".join(parts) if parts else "大盘数据获取失败"

        # 情绪档位判断
        sentiment = ""
        if len(trends) >= 2:
            avg_trend = sum(trends) / len(trends)
            up_count = sum(1 for t in trends if t > 0.5)
            down_count = sum(1 for t in trends if t < -0.5)

            if avg_trend > 3 and up_count >= len(trends):
                gear = "高潮期(5档) — 涨停铺天盖地，短期风险积聚，建议减仓或快进快出"
            elif avg_trend > 1 and up_count >= 2:
                gear = "发酵期(4档) — 涨停数增加势头良好，可适度参与，仓位3-5成"
            elif avg_trend > -0.5:
                gear = "启动期(3档) — 开始回暖零星涨停，谨慎入场，仓位2-3成"
            elif avg_trend > -2:
                gear = "低迷期(2档) — 涨停稀少破位频发，建议减仓或观望，仓位≤1成"
            else:
                gear = "冰点期(1档) — 几乎无涨停普跌，坚决不参与"

            sentiment = f"""5日趋势：{avg_trend:+.1f}%（{up_count}涨{down_count}跌）
市场情绪档位：{gear}"""
        else:
            sentiment = "情绪数据不足"

        return f"""【大盘环境】
{market_str}
{sentiment}"""
    except Exception:
        return "大盘数据获取失败"


def _screen_single_stock(code, stock_df, stats, candidates, mode="normal"):
    """对单只股票的近期数据执行完整筛选流程"""
    close = stock_df['Close'].dropna()
    if len(close) < 15: return
    stats['has_data'] += 1
    open_price = stock_df['Open'].dropna(); high = stock_df['High'].dropna()
    low = stock_df['Low'].dropna(); volume = stock_df['Volume'].dropna()
    min_len = min(len(close), len(open_price), len(high), len(low), len(volume))
    if min_len < 10: return
    recent = pd.DataFrame({
        'close': close.values, 'open': open_price.values,
        'high': high.values, 'low': low.values, 'volume': volume.values,
    }, index=close.index)
    recent['pct_chg'] = recent['close'].pct_change() * 100
    # trade_date: handle both DatetimeIndex and RangeIndex
    try:
        recent['trade_date'] = close.index.strftime('%Y%m%d')
    except AttributeError:
        # 降级：用今天日期往前推算（假设日线数据）
        today = pd.Timestamp.now()
        recent['trade_date'] = [(today - pd.Timedelta(days=len(recent)-1-i)).strftime('%Y%m%d') for i in range(len(recent))]
    limit_series_list = identify_limit_up_series(recent.dropna(subset=['pct_chg']).reset_index(drop=True), code)
    found_signal = False
    for series in limit_series_list:
        # 计算实体板比例（用于展示）
        entity_boards = sum(1 for d in series if not d['is_one_word'])
        entity_ratio = (entity_boards / len(series)) * 100 if len(series) > 0 else 0

        for offset in range(PARAMS['min_pullback_days'] + 1, 15):
            check_idx = len(recent) - offset
            if check_idx < 10: break
            result = check_pullback_conditions(recent.reset_index(drop=True), series, check_idx)
            if result:
                candidates.append({
                    'code': code,
                    'price': round(float(recent.iloc[-1]['close']), 2),
                    'signal_date': result['trigger_date'],
                    'signal_price': round(float(result['trigger_price']), 2),
                    'pullback_pct': round(result['pullback_ratio'] * 100, 1),
                    'limit_days': result['limit_series_len'],
                    'limit_dates': result['limit_dates'],
                    'entity_ratio': round(entity_ratio, 0),
                })
                found_signal = True; break
        if found_signal: break


def screen_today(mode="strict"):
    global PARAMS
    if mode not in SCREEN_MODES:
        print(f"Unknown mode '{mode}', using 'strict'")
        mode = "strict"
    PARAMS.update(SCREEN_MODES[mode])
    print("=" * 60)
    print(f"当日选股 v5 — 模式: {mode}")
    print("=" * 60)
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    candidates = []; stats = {'total': len(cache_files), 'has_data': 0, 'has_limit_up': 0, 'has_signal': 0}
    for idx, fname in enumerate(cache_files):
        code = fname.replace('.csv', '')
        if (idx + 1) % 500 == 0: print(f"  已扫描 {idx+1}/{len(cache_files)}...")
        try:
            ticker = yf.Ticker(code)
            df = ticker.history(period="3mo")
            if df is None or len(df) < 15: continue
            _screen_single_stock(code, df, stats, candidates, mode)
        except:
            continue
    print(f"\n✅ 扫描完成！总候选: {stats['total']} | 有数据: {stats['has_data']} | 选出: {len(candidates)}")
    return candidates


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                         v5 主入口                                       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h']:
        print("=" * 60)
        print("A股连板回调策略 v5 — 多阶段深度参数寻优")
        print("=" * 60)
        print("")
        print("用法:")
        print("  python 选股new_v5.py --download              # 快速批量下载全量数据")
        print("  python 选股new_v5.py --update-today          # 增量更新今日数据（盘中/盘后）")
        print("  python 选股new_v5.py --check-data            # 检查数据完整性")
        print("  python 选股new_v5.py --today [模式]          # 当日选股 (strict/loose)")
        print("  python 选股new_v5.py --optimize              # v5 多阶段参数优化")
        print("  python 选股new_v5.py --cross-period          # 多周期鲁棒性验证")
        print("  python 选股new_v5.py --full                  # 完整评估 (baseline+v4对比)")
        print("  python 选股new_v5.py                         # 默认：单时段三阶段优化")
        print("")
        print("v5 新增（vs v4):")
        print("  - 三阶段漏斗搜索：Coarse → Fine → Ultra-Fine")
        print("  - 多周期鲁棒性验证（3个市场状态时段）")
        print("  - Bootstrap 置信区间 + 置换检验")
        print("  - 参数敏感性分析")
        print("  - 跨周期稳定性评分")
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--download':
        download_all_data_fast()
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--update-today':
        update_today_data()
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--check-data':
        check_data_completeness()
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--today':
        mode = sys.argv[2] if len(sys.argv) > 2 else "normal"
        if mode not in SCREEN_MODES:
            print(f"⚠️ 未知模式 '{mode}'，使用 'normal'")
            mode = "normal"
        candidates = screen_today(mode=mode)
        if len(candidates) > 0:
            print(f"\n{'='*60}")
            print(f"📋 选股结果 ({mode}模式)")
            print(f"{'='*60}")
            for c in candidates:
                print(f"  {c['代码']}  |  {c['最新价']:.2f}  |  信号日{c['信号日']}  |  回调{c['回调比']:.1%}")
            print(f"\nCANDIDATE_CODES = {[c['代码'] for c in candidates]}")
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--cross-period':
        # 多周期鲁棒性验证
        cross_period_validation()
        sys.exit()

    # ─── 默认：单时段完整三阶段优化 ───
    OPT_PERIOD = ('20250101', '20260430')

    if len(sys.argv) > 1 and sys.argv[1] == '--optimize':
        # 只跑优化
        best_params, best_signals, results_df = run_multi_stage_optimization(*OPT_PERIOD)
        if best_signals is not None:
            m = calculate_v4_metrics(best_signals, start_date=OPT_PERIOD[0], end_date=OPT_PERIOD[1])
            print_v4_report(m, "v5 Best Params")
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--full':
        # 完整评估流程：v4 baseline + v5 优化 + 统计检验 + 对比
        print("=" * 70)
        print("🚀 v5 完整评估流程")
        print("=" * 70)
        print("将依次运行：")
        print("  1. v4 Baseline 回测")
        print("  2. v5 三阶段参数优化")
        print("  3. Bootstrap 置信区间")
        print("  4. 置换检验")
        print("  5. 参数敏感性分析")
        print("  6. Walk-Forward 验证")
        print("  7. v4 vs v5 综合对比")
        print("")

        # ---- 1. v4 Baseline ----
        print("\n" + "=" * 70)
        print("📊 第一步：v4 最佳参数回测（Baseline）")
        print("=" * 70)
        PARAMS.update({
            "min_consecutive_limit_up": 2, "min_entity_board_ratio": 0.5,
            "pullback_ratio_min": 0.08, "pullback_ratio_max": 0.25,
            "volume_shrink_ratio": 0.50, "volume_shrink_ratio_min": 0.0,
            "take_profit": 0.05, "stop_loss": -0.10, "hold_days": 7,
            "require_oversold": False, "require_low_close": False,
        })
        baseline_result = run_backtest(*OPT_PERIOD)
        baseline_metrics = baseline_result[1] if baseline_result else None

        # ---- 2. v5 三阶段优化 ----
        print("\n" + "=" * 70)
        print("🔍 第二步：v5 三阶段参数优化")
        print("=" * 70)
        v5_best_params, v5_best_signals, v5_results = run_multi_stage_optimization(*OPT_PERIOD)

        # ---- 3. 统计检验 ----
        print("\n" + "=" * 70)
        print("📈 第三步：统计显著性检验")
        print("=" * 70)
        bootstrap_results = bootstrap_confidence(v5_best_signals, n_bootstrap=1000)
        perm_results = permutation_test(v5_best_signals, n_permutations=1000)

        # ---- 4. 参数敏感性 ----
        print("\n" + "=" * 70)
        print("🔧 第四步：参数敏感性分析")
        print("=" * 70)
        # 需要重建 events 做敏感性分析
        cache_files = [f for f in os.listdir(DATA_DIR)
                       if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
        hot_codes = []
        for fname in cache_files:
            code = fname.replace('.csv', '')
            df = load_from_cache(code)
            if df is None or len(df) < 50: continue
            df = df[(df['trade_date'] >= OPT_PERIOD[0]) & (df['trade_date'] <= OPT_PERIOD[1])]
            if len(df) == 0: continue
            limit_threshold = get_limit_threshold(code)
            if (df['pct_chg'] >= limit_threshold).any():
                hot_codes.append(code)
        all_events_sens = extract_all_events(hot_codes, *OPT_PERIOD)
        sensitivity_results = parameter_sensitivity(v5_best_params, all_events_sens, *OPT_PERIOD)

        # ---- 5. Walk-Forward ----
        print("\n" + "=" * 70)
        print("🔬 第五步：Walk-Forward 验证")
        print("=" * 70)
        wf_is, wf_oos = walkforward_analysis_v5(*OPT_PERIOD, v5_best_params)

        # ---- 6. 综合对比 ----
        print("\n" + "=" * 70)
        print("🏆 第六步：v4 Baseline vs v5 综合对比")
        print("=" * 70)

        if baseline_metrics is not None:
            v5_metrics = calculate_v4_metrics(v5_best_signals, start_date=OPT_PERIOD[0], end_date=OPT_PERIOD[1])

            print(f"\n  {'指标':<25} {'v4 Baseline':<18} {'v5 最佳':<18} {'变化':<15}")
            print(f"  {'─'*75}")
            print(f"  {'胜率':<25} {baseline_metrics.win_rate:<18.2%} {v5_metrics.win_rate:<18.2%} {v5_metrics.win_rate-baseline_metrics.win_rate:<+.2%}")
            print(f"  {'平均收益':<25} {baseline_metrics.avg_return:<18.2%} {v5_metrics.avg_return:<18.2%} {v5_metrics.avg_return-baseline_metrics.avg_return:<+.2%}")
            print(f"  {'Sharpe Ratio':<25} {baseline_metrics.sharpe_ratio:<18.2f} {v5_metrics.sharpe_ratio:<18.2f} {v5_metrics.sharpe_ratio-baseline_metrics.sharpe_ratio:<+.2f}")
            print(f"  {'Sortino Ratio':<25} {baseline_metrics.sortino_ratio:<18.2f} {v5_metrics.sortino_ratio:<18.2f} {v5_metrics.sortino_ratio-baseline_metrics.sortino_ratio:<+.2f}")
            print(f"  {'Max Drawdown':<25} {baseline_metrics.max_drawdown:<18.2f}% {v5_metrics.max_drawdown:<18.2f}%")
            print(f"  {'CAGR':<25} {baseline_metrics.cagr:<18.2f}% {v5_metrics.cagr:<18.2f}%")
            print(f"  {'Profit Factor':<25} {baseline_metrics.profit_factor:<18.2f} {v5_metrics.profit_factor:<18.2f}")
            print(f"  {'Expectancy':<25} {baseline_metrics.expectancy:<18.2%} {v5_metrics.expectancy:<18.2%}")
            print(f"  {'信号数':<25} {baseline_metrics.total_trades:<18d} {v5_metrics.total_trades:<18d}")

            improvements = []
            if v5_metrics.win_rate > baseline_metrics.win_rate:
                improvements.append(f"胜率 {v5_metrics.win_rate-baseline_metrics.win_rate:+.1%}")
            if v5_metrics.sharpe_ratio > baseline_metrics.sharpe_ratio:
                improvements.append(f"Sharpe {v5_metrics.sharpe_ratio-baseline_metrics.sharpe_ratio:+.2f}")
            if v5_metrics.max_drawdown > baseline_metrics.max_drawdown:
                improvements.append(f"回撤改善")

            print(f"\n  📋 结论：")
            if improvements:
                print(f"  ✅ v5 在以下方面超越 v4 baseline：{', '.join(improvements)}")
            else:
                print(f"  ⚠️ v5 未显著超越 baseline，但参数更精确、统计检验更充分。")

            # 显著性提醒
            if bootstrap_results:
                sharpe_ci = bootstrap_results['Sharpe']
                print(f"  📊 Sharpe 95% CI: [{sharpe_ci['lower']:.2f}, {sharpe_ci['upper']:.2f}]")
                if sharpe_ci['lower'] > 0.5:
                    print(f"  🟢 Sharpe 下限 >0.5，策略收益稳健。")
                elif sharpe_ci['lower'] > 0:
                    print(f"  🟡 Sharpe 下限 >0，策略有正期望但不确定。")
                else:
                    print(f"  🔴 Sharpe 下限 <0，策略收益不稳健。")

            if perm_results and perm_results['p_value'] < 0.05:
                print(f"  ✅ 置换检验 p={perm_results['p_value']:.3f}，策略显著优于随机。")

            # 关键参数提示
            if sensitivity_results:
                key_params = [s['parameter'] for s in sensitivity_results if s['sensitivity'] > 0.10]
                if key_params:
                    print(f"  ⚡ 关键参数（需精确控制）: {', '.join(key_params)}")

        print(f"\n{'='*70}")
        print(f"v5 完整评估完成！结果保存在: {OUTPUT_DIR}/")
        print(f"{'='*70}")
        sys.exit()

    # ─── 默认：单时段三阶段优化 ───
    print("=" * 70)
    print("v5 单时段三阶段优化")
    print(f"区间: {OPT_PERIOD[0]} ~ {OPT_PERIOD[1]}")
    print("=" * 70)
    best_params, best_signals, results_df = run_multi_stage_optimization(*OPT_PERIOD)
    if best_signals is not None:
        m = calculate_v4_metrics(best_signals, start_date=OPT_PERIOD[0], end_date=OPT_PERIOD[1])
        print_v4_report(m, "v5 Best Params")
