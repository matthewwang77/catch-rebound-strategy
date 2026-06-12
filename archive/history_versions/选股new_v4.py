"""
A股连板回调策略 v4 — 专业量化回测框架
基于 v3（华安证券研报改进版）+ backtesting-trading-strategies skill 最佳实践

v4 新增：
  - 高级风险指标：Sharpe, Sortino, Calmar, Max Drawdown, CAGR, VaR/CVaR
  - 最大连胜/连亏、Expectancy、Ulcer Index
  - 手续费+滑点建模（A股 印花税+佣金+过户费）
  - Walk-forward 分析（样本内/外分离验证，防过拟合）
  - 资金曲线生成
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import time
import os
import warnings

warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "stock_data")
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== 可调参数区 ====================
PARAMS = {
    "lookback_days": 10,
    "min_consecutive_limit_up": 2,
    "min_entity_board_ratio": 0.3,
    "pullback_ratio_min": 0.08,
    "pullback_ratio_max": 0.25,
    "min_pullback_days": 2,
    "ma_stabilize": 10,
    "volume_shrink_ratio": 0.4,
    "volume_shrink_ratio_min": 0.0,
    "volume_compare_days": 3,
    "signal_today_yang": True,
    "signal_volume_expand": 1.2,
    "hold_days": 7,
    "take_profit": 0.05,
    "stop_loss": -0.07,
    # 超跌反弹过滤
    "require_oversold": False,
    "oversold_decline_threshold": 0.10,
    "oversold_lookback_days": 20,
    # 低位收盘过滤
    "require_low_close": False,
    "low_close_threshold": 0.5,
}

# ==================== v4: 交易成本配置（A股实战）====================
COMMISSION = {
    "stamp_tax": 0.0005,       # 印花税 0.05%（仅卖出）
    "brokerage": 0.00025,      # 佣金 0.025%（买卖双向）
    "transfer_fee": 0.00001,   # 过户费 0.001%（买卖双向）
    "slippage": 0.001,         # 滑点 0.1%（最小变动单位/价格）
}


def apply_trading_costs(gross_return, is_sell=False):
    """扣除交易成本后的净收益"""
    cost = COMMISSION["brokerage"] * 2  # 买卖佣金
    cost += COMMISSION["transfer_fee"] * 2  # 买卖过户费
    if is_sell:
        cost += COMMISSION["stamp_tax"]  # 卖出印花税
    cost += COMMISSION["slippage"]  # 滑点
    return gross_return - cost


# ==================== v4: 高级指标数据类 ====================
@dataclass
class V4Metrics:
    """v4 完整回测指标"""
    # 基础
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0

    # 收益
    avg_return: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0
    total_return_geo: float = 0.0  # 几何复利
    total_return_sum: float = 0.0  # 简单求和
    cagr: float = 0.0              # 年化复利

    # 风险调整
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    volatility: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    ulcer_index: float = 0.0

    # 交易统计
    profit_factor: float = 0.0
    expectancy: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_hold_days: float = 0.0

    # 退出分布
    exit_distribution: Dict[str, int] = field(default_factory=dict)

    # 资金曲线
    equity_curve: List[float] = field(default_factory=list)
    daily_returns: List[float] = field(default_factory=list)


def calculate_v4_metrics(signals_df: pd.DataFrame, initial_capital: float = 100000,
                          start_date: str = None, end_date: str = None) -> V4Metrics:
    """从信号DataFrame计算v4完整指标"""
    m = V4Metrics()

    if signals_df is None or len(signals_df) == 0:
        return m

    df = signals_df.copy()

    # ---- 基础统计 ----
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

    # ---- CAGR ----
    if start_date and end_date:
        years = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days / 365.25
    else:
        years = len(df) / 52  # 粗略估计：每52笔交易=1年
    if years > 0 and initial_capital > 0:
        final_capital = initial_capital * (1 + m.total_return_geo)
        m.cagr = ((final_capital / initial_capital) ** (1 / years) - 1) * 100

    # ---- 盈亏比 ----
    m.profit_factor = abs(m.avg_win / m.avg_loss) if m.avg_loss != 0 else 99

    # ---- Expectancy ----
    m.expectancy = (m.win_rate * m.avg_win) + ((1 - m.win_rate) * m.avg_loss)

    # ---- 连胜/连亏 ----
    current_wins = current_losses = 0
    for ret in df['return']:
        if ret > 0:
            current_wins += 1
            current_losses = 0
            m.max_consecutive_wins = max(m.max_consecutive_wins, current_wins)
        else:
            current_losses += 1
            current_wins = 0
            m.max_consecutive_losses = max(m.max_consecutive_losses, current_losses)

    # ---- 持仓天数 ----
    if 'hold_days_actual' in df.columns:
        m.avg_hold_days = df['hold_days_actual'].mean()

    # ---- 退出分布 ----
    if 'exit_reason' in df.columns:
        m.exit_distribution = df['exit_reason'].value_counts().to_dict()

    # ---- 资金曲线 ----
    df_sorted = df.sort_values('trigger_date') if 'trigger_date' in df.columns else df
    equity = [initial_capital]
    for ret in df_sorted['return']:
        equity.append(equity[-1] * (1 + ret))
    m.equity_curve = equity[1:]  # 去掉初始值

    # ---- 日收益率（用于 Sharpe/Sortino/Volatility）----
    # 按日期聚合（同一天可能多笔信号）
    if 'trigger_date' in df.columns:
        df_sorted['date_parsed'] = pd.to_datetime(df_sorted['trigger_date'], format='%Y%m%d')
        daily_pnl = df_sorted.groupby('date_parsed')['return'].sum()
        # 填充无交易日
        if len(daily_pnl) >= 2:
            date_range = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq='B')
            daily_pnl = daily_pnl.reindex(date_range, fill_value=0)
            m.daily_returns = daily_pnl.values.tolist()
    else:
        m.daily_returns = df['return'].tolist()

    daily_ret = pd.Series(m.daily_returns)

    # ---- Sharpe Ratio (年化) ----
    if len(daily_ret) >= 2 and daily_ret.std() > 0:
        ann_return = daily_ret.mean() * 252
        ann_vol = daily_ret.std() * np.sqrt(252)
        m.sharpe_ratio = (ann_return - 0.02) / ann_vol  # 无风险利率 2%

    # ---- Sortino Ratio ----
    if len(daily_ret) >= 2:
        downside = daily_ret[daily_ret < 0]
        if len(downside) > 0 and downside.std() > 0:
            ann_return = daily_ret.mean() * 252
            downside_std = downside.std() * np.sqrt(252)
            m.sortino_ratio = min((ann_return - 0.02) / downside_std, 10)  # 封顶10
        elif daily_ret.mean() > 0:
            m.sortino_ratio = 3.0  # 无下行波动时设为合理值

    # ---- Volatility (年化) ----
    m.volatility = daily_ret.std() * np.sqrt(252) * 100 if len(daily_ret) >= 2 else 0

    # ---- Max Drawdown ----
    if len(m.equity_curve) >= 2:
        eq = pd.Series(m.equity_curve)
        rolling_max = eq.expanding().max()
        drawdowns = (eq - rolling_max) / rolling_max
        m.max_drawdown = drawdowns.min() * 100

        # Drawdown 持续时间
        in_dd = drawdowns < 0
        dd_periods = []
        start = None
        for i, is_dd in enumerate(in_dd):
            if is_dd and start is None:
                start = i
            elif not is_dd and start is not None:
                dd_periods.append(i - start)
                start = None
        if start is not None:
            dd_periods.append(len(in_dd) - start)
        m.max_drawdown_duration = max(dd_periods) if dd_periods else 0

    # ---- Calmar Ratio ----
    if m.max_drawdown != 0:
        m.calmar_ratio = m.cagr / abs(m.max_drawdown)

    # ---- VaR / CVaR ----
    if len(daily_ret) >= 10:
        m.var_95 = np.percentile(daily_ret, 5) * 100
        tail = daily_ret[daily_ret <= np.percentile(daily_ret, 5)]
        m.cvar_95 = tail.mean() * 100 if len(tail) > 0 else m.var_95

    # ---- Ulcer Index ----
    if len(m.equity_curve) >= 2:
        eq = pd.Series(m.equity_curve)
        rolling_max = eq.expanding().max()
        pct_dd_sq = ((eq - rolling_max) / rolling_max) ** 2
        m.ulcer_index = np.sqrt(pct_dd_sq.mean()) * 100

    return m


def print_v4_report(m: V4Metrics, params_label: str = ""):
    """格式化输出 v4 完整报告"""
    header = f"V4 ADVANCED REPORT" + (f" — {params_label}" if params_label else "")
    print(f"\n{'='*70}")
    print(header)
    print(f"{'='*70}")

    print(f"\n{'─'*70}")
    print(f"  【收益指标】")
    print(f"{'─'*70}")
    print(f"  总交易次数:     {m.total_trades:>8d}")
    print(f"  胜率:           {m.win_rate:>8.1%}")
    print(f"  平均收益:       {m.avg_return:>+8.2%}")
    print(f"  平均盈利:       {m.avg_win:>+8.2%}  |  平均亏损:       {m.avg_loss:>+8.2%}")
    print(f"  最大盈利:       {m.max_win:>+8.2%}  |  最大亏损:       {m.max_loss:>+8.2%}")
    print(f"  总收益(几何):   {m.total_return_geo:>+8.2%}  |  总收益(简单):   {m.total_return_sum:>+8.2%}")
    print(f"  CAGR (年化):    {m.cagr:>+8.2f}%")

    print(f"\n{'─'*70}")
    print(f"  【风险调整指标】")
    print(f"{'─'*70}")
    print(f"  Sharpe Ratio:   {m.sharpe_ratio:>8.2f}  (目标: >1.5)")
    print(f"  Sortino Ratio:  {m.sortino_ratio:>8.2f}  (只看下行风险)")
    print(f"  Calmar Ratio:   {m.calmar_ratio:>8.2f}  (CAGR/|MaxDD|)")
    print(f"  Max Drawdown:   {m.max_drawdown:>+8.2f}% (持续 {m.max_drawdown_duration} 天)")
    print(f"  Volatility:     {m.volatility:>8.2f}%  (年化)")
    print(f"  VaR (95%):      {m.var_95:>+8.2f}%")
    print(f"  CVaR (95%):     {m.cvar_95:>+8.2f}% (尾部期望)")
    print(f"  Ulcer Index:    {m.ulcer_index:>8.2f}")

    print(f"\n{'─'*70}")
    print(f"  【交易统计】")
    print(f"{'─'*70}")
    print(f"  Expectancy:     {m.expectancy:>+8.2%}  (单笔期望)")
    print(f"  Profit Factor:  {m.profit_factor:>8.2f}")
    print(f"  最大连胜:       {m.max_consecutive_wins:>8d}  次")
    print(f"  最大连亏:       {m.max_consecutive_losses:>8d}  次")
    print(f"  平均持仓:       {m.avg_hold_days:>8.1f}  天")

    if m.exit_distribution:
        print(f"\n{'─'*70}")
        print(f"  【退出原因分布】")
        print(f"{'─'*70}")
        for reason, count in sorted(m.exit_distribution.items(), key=lambda x: -x[1]):
            pct = count / m.total_trades * 100
            bar = '█' * max(1, int(pct / 2))
            print(f"  {reason:<8}: {count:>4}次 ({pct:>5.1f}%) {bar}")

    print(f"{'='*70}\n")


# ==================== 工具函数 ====================
def get_limit_threshold(code):
    """根据股票代码返回涨跌停阈值（区分板块）"""
    if code.startswith(('30', '688')):
        return 18.5   # 创业板/科创板 20% 涨跌停
    else:
        return 9.5    # 主板 10% 涨跌停


# ==================== 1. 生成全A股代码列表 ====================
def generate_all_codes():
    """生成全A股候选代码"""
    codes = []
    for i in range(600000, 606000):
        codes.append(f"{i}.SS")
    for i in range(1, 5000):
        codes.append(f"{i:06d}.SZ")
    for i in range(300000, 302000):
        codes.append(f"{i}.SZ")
    for i in range(688000, 690000):
        codes.append(f"{i}.SS")
    return codes


# ==================== 2. 下载单只股票到本地 ====================
def download_one_stock(code):
    """下载一只股票的历史数据，保存到本地csv"""
    cache_file = os.path.join(DATA_DIR, f"{code}.csv")
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        return True, "已有缓存"
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(start="2020-01-01", end=datetime.now().strftime('%Y-%m-%d'))
        if df is None or len(df) == 0:
            pd.DataFrame().to_csv(cache_file, index=False)
            return False, "无数据（退市/停牌）"
        df = df.reset_index()
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        df = df.rename(columns={
            'Date': 'date', 'Open': 'open', 'High': 'high',
            'Low': 'low', 'Close': 'close', 'Volume': 'volume',
        })
        df[['date', 'open', 'high', 'low', 'close', 'volume']].to_csv(cache_file, index=False)
        return True, f"{len(df)}条"
    except Exception as e:
        return False, str(e)[:50]


# ==================== 3. 从本地读取 ====================
def load_from_cache(code):
    """从本地缓存读取股票数据"""
    cache_file = os.path.join(DATA_DIR, f"{code}.csv")
    if not os.path.exists(cache_file) or os.path.getsize(cache_file) < 100:
        return None
    try:
        df = pd.read_csv(cache_file)
        if len(df) == 0:
            return None
        df['trade_date'] = df['date'].str.replace('-', '')
        df['pct_chg'] = df['close'].pct_change() * 100
        df = df.dropna(subset=['pct_chg'])
        return df.sort_values('trade_date').reset_index(drop=True)
    except:
        return None


# ==================== 4. 下载全部数据 ====================
def download_all_data():
    """下载全量A股历史数据到本地"""
    print("=" * 60)
    print("阶段一：下载全量A股历史数据")
    print("=" * 60)
    all_codes = generate_all_codes()
    total = len(all_codes)
    existing = sum(1 for f in os.listdir(DATA_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100)
    print(f"候选代码总数: {total}")
    print(f"已有本地缓存: {existing}")
    print(f"待下载: {total - existing}")
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
            print(f"  进度: {i+1}/{total} ({((i+1)/total)*100:.1f}%) | "
                  f"速度: {speed:.0f}只/分钟 | 预计剩余: {remaining:.0f}分钟 | "
                  f"成功: {success} | 缓存: {skip} | 失败: {fail}")
    total_time = time.time() - start_time
    print(f"\n✅ 下载完成！耗时: {total_time/60:.1f}分钟")


# ==================== 5. 识别连板 ====================
def identify_limit_up_series(df_stock, code=""):
    """识别连板序列"""
    if df_stock is None or len(df_stock) < PARAMS['min_consecutive_limit_up']:
        return []
    limit_threshold = get_limit_threshold(code) if code else 9.5
    df = df_stock.copy()
    df['is_limit_up'] = df['pct_chg'] >= limit_threshold
    df['is_one_word'] = (
        (df['open'] == df['high']) &
        (df['low'] == df['close']) &
        df['is_limit_up']
    )
    limit_series = []
    current_series = []
    for idx, row in df.iterrows():
        if row['is_limit_up']:
            current_series.append({
                'date': row['trade_date'], 'close': row['close'],
                'high': row['high'], 'is_one_word': row['is_one_word'],
                'volume': row['volume']
            })
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


# ==================== 6. 检查回调条件 ====================
def check_pullback_conditions(df_stock, limit_series_item, current_idx):
    """检查回调条件"""
    if current_idx >= len(df_stock) - 1:
        return None

    last_limit_date = limit_series_item[-1]['date']
    matching_rows = df_stock[df_stock['trade_date'] == last_limit_date]
    if len(matching_rows) == 0:
        return None
    last_limit_idx = matching_rows.index[0]

    if current_idx - last_limit_idx < PARAMS['min_pullback_days']:
        return None

    highest_price = max([d['high'] for d in limit_series_item])
    current_price = df_stock.iloc[current_idx]['close']
    pullback_ratio = (highest_price - current_price) / highest_price

    if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
        return None

    # 量能
    limit_volumes = [d['volume'] for d in limit_series_item]
    limit_avg_vol = np.mean(limit_volumes)
    pullback_start = max(0, current_idx - PARAMS['volume_compare_days'])
    pullback_volumes = df_stock.iloc[pullback_start:current_idx]['volume'].tolist()
    if len(pullback_volumes) < PARAMS['volume_compare_days']:
        return None
    pullback_avg_vol = np.mean(pullback_volumes)
    if limit_avg_vol > 0:
        vol_ratio = pullback_avg_vol / limit_avg_vol
        if vol_ratio > PARAMS['volume_shrink_ratio']:
            return None
        if vol_ratio < PARAMS.get('volume_shrink_ratio_min', 0):
            return None

    # 均线
    if current_idx < PARAMS['ma_stabilize']:
        return None
    ma = df_stock.iloc[current_idx - PARAMS['ma_stabilize'] + 1:current_idx + 1]['close'].mean()
    if current_price < ma:
        return None

    # 阳线
    if PARAMS['signal_today_yang']:
        if df_stock.iloc[current_idx]['close'] <= df_stock.iloc[current_idx]['open']:
            return None

    # 放量
    if current_idx >= 1:
        today_vol = df_stock.iloc[current_idx]['volume']
        yesterday_vol = df_stock.iloc[current_idx - 1]['volume']
        if yesterday_vol > 0 and today_vol / yesterday_vol < PARAMS['signal_volume_expand']:
            return None

    # 低位收盘过滤
    if PARAMS.get('require_low_close', False):
        row = df_stock.iloc[current_idx]
        high_low_range = row['high'] - row['low']
        if high_low_range > 0:
            close_position = (row['close'] - row['low']) / high_low_range
            if close_position >= PARAMS.get('low_close_threshold', 0.5):
                return None

    return {
        'trigger_date': df_stock.iloc[current_idx]['trade_date'],
        'trigger_price': current_price,
        'highest_price': highest_price,
        'pullback_ratio': pullback_ratio,
        'limit_series_len': len(limit_series_item),
        'limit_dates': f"{limit_series_item[0]['date']}~{limit_series_item[-1]['date']}"
    }


# ==================== 7. 模拟持仓（v4: 加入手续费+滑点）====================
def simulate_hold_return(df_stock, entry_idx, entry_price, apply_costs=True):
    """模拟持仓收益。v4: 加入A股真实交易成本"""
    exit_idx = min(entry_idx + PARAMS['hold_days'], len(df_stock) - 1)
    for i in range(entry_idx + 1, exit_idx + 1):
        high = df_stock.iloc[i]['high']
        low = df_stock.iloc[i]['low']
        open_price = df_stock.iloc[i]['open']
        if entry_price <= 0:
            continue

        # 第一层：开盘跳空直接触发
        open_return = open_price / entry_price - 1
        if apply_costs:
            net_open_return = apply_trading_costs(open_return, is_sell=True)
        else:
            net_open_return = open_return

        if net_open_return <= PARAMS['stop_loss']:
            return net_open_return, i - entry_idx, '止损'
        if net_open_return >= PARAMS['take_profit']:
            return net_open_return, i - entry_idx, '止盈'

        # 第二层：日内触及 —— 距离开盘价更近的阈值先触发
        stop_level = entry_price * (1 + PARAMS['stop_loss'])
        profit_level = entry_price * (1 + PARAMS['take_profit'])
        dist_to_stop = open_price - stop_level
        dist_to_profit = profit_level - open_price

        if dist_to_stop <= dist_to_profit:
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                gross_ret = PARAMS['stop_loss']
                net_ret = apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret
                return net_ret, i - entry_idx, '止损'
            if high / entry_price - 1 >= PARAMS['take_profit']:
                gross_ret = PARAMS['take_profit']
                net_ret = apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret
                return net_ret, i - entry_idx, '止盈'
        else:
            if high / entry_price - 1 >= PARAMS['take_profit']:
                gross_ret = PARAMS['take_profit']
                net_ret = apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret
                return net_ret, i - entry_idx, '止盈'
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                gross_ret = PARAMS['stop_loss']
                net_ret = apply_trading_costs(gross_ret, is_sell=True) if apply_costs else gross_ret
                return net_ret, i - entry_idx, '止损'

    final_price = df_stock.iloc[exit_idx]['close']
    final_return = final_price / entry_price - 1 if entry_price > 0 else 0
    if apply_costs:
        net_final = apply_trading_costs(final_return, is_sell=True)
    else:
        net_final = final_return
    return net_final, PARAMS['hold_days'], '到期'


# ==================== 8. 主回测（v4: 输出高级指标）====================
def run_backtest(start_date, end_date, quiet=False):
    """从本地缓存读取数据，扫描回测（v4: 增强报告）"""
    if not quiet:
        print("=" * 60)
        print(f"阶段二：执行回测（v4 专业版）")
        print("=" * 60)
        print(f"回测区间：{start_date} ~ {end_date}")
        print(f"参数：连板≥{PARAMS['min_consecutive_limit_up']} | "
              f"回调{PARAMS['pullback_ratio_min']:.0%}-{PARAMS['pullback_ratio_max']:.0%} | "
              f"缩量≤{PARAMS['volume_shrink_ratio']:.0%}"
              + (f" | 超跌>{PARAMS['oversold_decline_threshold']:.0%}" if PARAMS.get('require_oversold') else "")
              + (f" | 低位收盘" if PARAMS.get('require_low_close') else "")
              + f" | 手续费: {COMMISSION['stamp_tax']*100:.2f}%印花+{COMMISSION['brokerage']*100:.2f}%佣金")

    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]

    # 第一步：扫描涨停股
    if not quiet:
        print(f"\n第一步：扫描有涨停/连板记录的股票...")
    hot_codes = []
    start_time = time.time()
    for idx, fname in enumerate(cache_files):
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 50:
            continue
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        if len(df) == 0:
            continue
        limit_threshold = get_limit_threshold(code)
        if (df['pct_chg'] >= limit_threshold).any():
            hot_codes.append(code)
    if not quiet:
        print(f"✅ 扫描完成！{len(hot_codes)} 只有过涨停记录\n")

    # 第二步：深度分析
    if not quiet:
        print("第二步：对涨停股做深度连板+回调分析...")
    all_signals = []
    oversold_skip = 0

    for idx, code in enumerate(hot_codes):
        if not quiet and (idx + 1) % 100 == 0:
            print(f"  进度：{idx+1}/{len(hot_codes)} | 信号：{len(all_signals)}")

        df_stock = load_from_cache(code)
        if df_stock is None:
            continue
        df_stock = df_stock[
            (df_stock['trade_date'] >= start_date) &
            (df_stock['trade_date'] <= end_date)
        ].reset_index(drop=True)
        if len(df_stock) < PARAMS['lookback_days'] + 10:
            continue

        limit_threshold = get_limit_threshold(code)
        df_stock['is_limit_up'] = df_stock['pct_chg'] >= limit_threshold
        df_stock['is_one_word'] = (
            (df_stock['open'] == df_stock['high']) &
            (df_stock['low'] == df_stock['close']) &
            df_stock['is_limit_up']
        )

        limit_up_indices = df_stock[df_stock['is_limit_up']].index.tolist()
        if not limit_up_indices:
            continue

        groups = []
        current_group = [limit_up_indices[0]]
        for i in range(1, len(limit_up_indices)):
            if limit_up_indices[i] == limit_up_indices[i-1] + 1:
                current_group.append(limit_up_indices[i])
            else:
                groups.append(current_group)
                current_group = [limit_up_indices[i]]
        groups.append(current_group)

        for group in groups:
            if len(group) < PARAMS['min_consecutive_limit_up']:
                continue
            entity_count = sum(1 for i in group if not df_stock.iloc[i]['is_one_word'])
            if entity_count / len(group) < PARAMS['min_entity_board_ratio']:
                continue

            # 超跌检查
            if PARAMS.get('require_oversold', False):
                first_limit_idx = group[0]
                lookback_start = max(0, first_limit_idx - PARAMS.get('oversold_lookback_days', 20))
                if lookback_start < first_limit_idx and first_limit_idx > 0:
                    pre_price = df_stock.iloc[lookback_start]['close']
                    pre_limit_price = df_stock.iloc[first_limit_idx - 1]['close']
                    if pre_price > 0:
                        pre_decline = (pre_limit_price / pre_price - 1)
                        if pre_decline > -PARAMS['oversold_decline_threshold']:
                            oversold_skip += 1
                            continue

            last_limit_idx = group[-1]
            highest_price = max(df_stock.iloc[i]['high'] for i in group)

            for check_idx in range(last_limit_idx + PARAMS['min_pullback_days'] + 1,
                                   min(last_limit_idx + 15, len(df_stock))):
                current_price = df_stock.iloc[check_idx]['close']
                pullback_ratio = (highest_price - current_price) / highest_price

                if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
                    continue
                if check_idx < PARAMS['ma_stabilize']:
                    continue
                ma = df_stock.iloc[check_idx - PARAMS['ma_stabilize'] + 1:check_idx + 1]['close'].mean()
                if current_price < ma:
                    continue

                # 量能
                limit_volumes = [df_stock.iloc[i]['volume'] for i in group]
                limit_avg_vol = np.mean(limit_volumes)
                pullback_start_idx = max(0, check_idx - PARAMS['volume_compare_days'])
                pullback_volumes = df_stock.iloc[pullback_start_idx:check_idx]['volume'].tolist()
                if len(pullback_volumes) < PARAMS['volume_compare_days']:
                    continue
                pullback_avg_vol = np.mean(pullback_volumes)
                if limit_avg_vol > 0:
                    vol_ratio = pullback_avg_vol / limit_avg_vol
                    if vol_ratio > PARAMS['volume_shrink_ratio']:
                        continue
                    if vol_ratio < PARAMS.get('volume_shrink_ratio_min', 0):
                        continue

                # 阳线
                if PARAMS['signal_today_yang']:
                    if df_stock.iloc[check_idx]['close'] <= df_stock.iloc[check_idx]['open']:
                        continue

                # 放量
                if check_idx >= 1 and PARAMS['signal_volume_expand'] > 0:
                    today_vol = df_stock.iloc[check_idx]['volume']
                    yesterday_vol = df_stock.iloc[check_idx - 1]['volume']
                    if yesterday_vol > 0 and today_vol / yesterday_vol < PARAMS['signal_volume_expand']:
                        continue

                # 低位收盘过滤
                if PARAMS.get('require_low_close', False):
                    row = df_stock.iloc[check_idx]
                    high_low_range = row['high'] - row['low']
                    if high_low_range > 0:
                        close_position = (row['close'] - row['low']) / high_low_range
                        if close_position >= PARAMS.get('low_close_threshold', 0.5):
                            continue

                # 模拟持仓（v4: 含手续费）
                ret, days_held, exit_reason = simulate_hold_return(
                    df_stock, check_idx, current_price, apply_costs=True
                )

                all_signals.append({
                    'trigger_date': df_stock.iloc[check_idx]['trade_date'],
                    'stock_code': code,
                    'trigger_price': current_price,
                    'highest_price': highest_price,
                    'pullback_ratio': pullback_ratio,
                    'limit_series_len': len(group),
                    'return': ret,
                    'hold_days_actual': days_held,
                    'exit_reason': exit_reason
                })
                break  # 每个连板事件只取第一个触发日

    total_time = time.time() - start_time

    if not quiet:
        print(f"\n✅ 深度分析完成！耗时: {total_time:.1f}秒")

    if len(all_signals) == 0:
        if not quiet:
            print("\n⚠️ 未产生任何交易信号。建议放宽参数。")
        return None

    df = pd.DataFrame(all_signals)

    # ---- v4: 计算完整指标 ----
    m = calculate_v4_metrics(df, start_date=start_date, end_date=end_date)

    if not quiet:
        print(f"\n  v4基础指标：")
        print(f"    总信号数：{m.total_trades}")
        if PARAMS.get('require_oversold'):
            print(f"    超跌过滤跳过：{oversold_skip} 个连板组")
        print(f"    胜率：{m.win_rate:.2%} | 平均收益：{m.avg_return:.2%}")
        print(f"    平均盈利：{m.avg_win:.2%} | 平均亏损：{m.avg_loss:.2%}")
        print(f"    盈亏比：{m.profit_factor:.2f}")

        # 收益分布
        print(f"\n  【收益分布】")
        bins = [-999, -0.07, -0.03, 0, 0.03, 0.05, 0.07, 999]
        labels = ['<=-7%', '-7%~-3%', '-3%~0%', '0~+3%', '+3%~+5%', '+5%~+7%', '>+7%']
        df_bin = df.copy()
        df_bin['return_bin'] = pd.cut(df_bin['return'], bins=bins, labels=labels)
        for label, count in df_bin['return_bin'].value_counts().sort_index().items():
            bar = '█' * max(1, int(count / len(df) * 50))
            print(f"    {label}: {count}次 ({count/len(df)*100:.1f}%) {bar}")

        # v4 完整报告
        print_v4_report(m, f"{start_date}~{end_date}")

    # 保存
    output_file = os.path.join(BASE, f'backtest_v4_{start_date}_{end_date}.csv')
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    # 保存资金曲线
    eq_file = os.path.join(BASE, f'equity_v4_{start_date}_{end_date}.csv')
    pd.DataFrame({'equity': m.equity_curve}).to_csv(eq_file, index=False)
    if not quiet:
        print(f"✅ 信号已保存至：{output_file}")
        print(f"✅ 资金曲线已保存至：{eq_file}")

    return df, m


# ==================== 9. 预提取连板事件 ====================
def extract_all_events(hot_codes, start_date, end_date):
    """对所有涨停股票，预提取连板事件"""
    print("正在预提取连板事件...")
    all_events = []

    for idx, code in enumerate(hot_codes):
        if (idx + 1) % 500 == 0:
            print(f"  进度：{idx+1}/{len(hot_codes)}，已提取事件：{len(all_events)}")

        df_stock = load_from_cache(code)
        if df_stock is None:
            continue
        df_stock = df_stock[
            (df_stock['trade_date'] >= start_date) &
            (df_stock['trade_date'] <= end_date)
        ].reset_index(drop=True)
        if len(df_stock) < 10:
            continue

        limit_threshold = get_limit_threshold(code)
        df_stock['is_limit_up'] = df_stock['pct_chg'] >= limit_threshold
        df_stock['is_one_word'] = (
            (df_stock['open'] == df_stock['high']) &
            (df_stock['low'] == df_stock['close']) &
            df_stock['is_limit_up']
        )

        limit_up_indices = df_stock[df_stock['is_limit_up']].index.tolist()
        if not limit_up_indices:
            continue

        groups = []
        current_group = [limit_up_indices[0]]
        for i in range(1, len(limit_up_indices)):
            if limit_up_indices[i] == limit_up_indices[i-1] + 1:
                current_group.append(limit_up_indices[i])
            else:
                groups.append(current_group)
                current_group = [limit_up_indices[i]]
        groups.append(current_group)

        for group in groups:
            if len(group) < 2:
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
                if len(pullback_volumes) < 2:
                    continue
                pullback_avg_vol = np.mean(pullback_volumes)

                ma_val = df_stock.iloc[max(0, check_idx - 9):check_idx + 1]['close'].mean() if check_idx >= 9 else current_price

                is_yang = df_stock.iloc[check_idx]['close'] > df_stock.iloc[check_idx]['open']
                today_vol = df_stock.iloc[check_idx]['volume']
                yesterday_vol = df_stock.iloc[check_idx - 1]['volume'] if check_idx > 0 else today_vol
                vol_expand_ratio = today_vol / yesterday_vol if yesterday_vol > 0 else 1

                row = df_stock.iloc[check_idx]
                high_low_range = row['high'] - row['low']
                close_position = (row['close'] - row['low']) / high_low_range if high_low_range > 0 else 0.5

                # 后续N天数据（用于模拟持仓）
                future_data = []
                for fwd in range(1, 11):
                    fwd_idx = check_idx + fwd
                    if fwd_idx >= len(df_stock):
                        break
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


# ==================== 10. v4 参数优化（多指标评分）====================
def optimize_params(start_date, end_date):
    """v4: 基于多指标的参数寻优（Sharpe/Sortino 权重）"""
    print("=" * 60)
    print("v4 参数优化模式")
    print("=" * 60)

    # 扫描涨停股票
    print("第一步：扫描涨停股票...")
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    hot_codes = []
    for fname in cache_files:
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 50:
            continue
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        if len(df) == 0:
            continue
        limit_threshold = get_limit_threshold(code)
        if (df['pct_chg'] >= limit_threshold).any():
            hot_codes.append(code)
    print(f"✅ 涨停股票：{len(hot_codes)} 只")

    # 预提取
    print("\n第二步：预提取连板+回调事件...")
    all_events = extract_all_events(hot_codes, start_date, end_date)

    # 参数网格
    param_grid = {
        "min_consecutive_limit_up": [2, 3],
        "min_entity_board_ratio": [0.3, 0.5],
        "pullback_ratio_min": [0.05, 0.08, 0.10],
        "pullback_ratio_max": [0.12, 0.15, 0.20, 0.25],
        "volume_shrink_ratio": [0.20, 0.30, 0.40, 0.50],
        "volume_shrink_ratio_min": [0.0, 0.05],
        "take_profit": [0.05, 0.07, 0.10],
        "stop_loss": [-0.05, -0.07, -0.10],
        "hold_days": [3, 5, 7],
        "require_oversold": [False, True],
        "require_low_close": [False, True],
    }

    from itertools import product
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combinations = list(product(*values))
    total_combos = len(all_combinations)

    print(f"\n第三步：遍历 {total_combos} 种参数组合...")
    print(f"预计耗时：2-5分钟\n")
    results_list = []
    best_score = -999
    best_params = None
    best_signals = None
    best_metrics = None
    start_time = time.time()

    for i, combo in enumerate(all_combinations):
        params_dict = dict(zip(keys, combo))

        signals = []
        for evt in all_events:
            if evt['limit_series_len'] < params_dict['min_consecutive_limit_up']:
                continue
            if evt['entity_ratio'] < params_dict['min_entity_board_ratio']:
                continue
            if evt['pullback_ratio'] < params_dict['pullback_ratio_min']:
                continue
            if evt['pullback_ratio'] > params_dict['pullback_ratio_max']:
                continue

            vol_ratio = evt['pullback_avg_vol'] / evt['limit_avg_vol'] if evt['limit_avg_vol'] > 0 else 1
            if vol_ratio > params_dict['volume_shrink_ratio']:
                continue
            if vol_ratio < params_dict.get('volume_shrink_ratio_min', 0):
                continue

            if evt['trigger_price'] < evt['ma']:
                continue
            if not evt['is_yang']:
                continue

            if params_dict.get('require_oversold', False):
                if evt['oversold_decline'] > -0.10:
                    continue
            if params_dict.get('require_low_close', False):
                if evt['close_position'] >= 0.5:
                    continue

            # 模拟持仓（v4: 含手续费）
            entry_price = evt['trigger_price']
            hold_days = params_dict['hold_days']
            take_profit = params_dict['take_profit']
            stop_loss = params_dict['stop_loss']

            ret = 0
            exit_reason = '到期'
            days_held = hold_days

            for fwd_idx, bar in enumerate(evt['future_data']):
                if fwd_idx >= hold_days:
                    break

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
                        gross_ret = stop_loss
                        ret = apply_trading_costs(gross_ret, is_sell=True)
                        exit_reason = '止损'; days_held = fwd_idx + 1; break
                    if bar['high'] / entry_price - 1 >= take_profit:
                        gross_ret = take_profit
                        ret = apply_trading_costs(gross_ret, is_sell=True)
                        exit_reason = '止盈'; days_held = fwd_idx + 1; break
                else:
                    if bar['high'] / entry_price - 1 >= take_profit:
                        gross_ret = take_profit
                        ret = apply_trading_costs(gross_ret, is_sell=True)
                        exit_reason = '止盈'; days_held = fwd_idx + 1; break
                    if bar['low'] / entry_price - 1 <= stop_loss:
                        gross_ret = stop_loss
                        ret = apply_trading_costs(gross_ret, is_sell=True)
                        exit_reason = '止损'; days_held = fwd_idx + 1; break
            else:
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

        if len(signals) == 0:
            continue

        df = pd.DataFrame(signals)
        signal_count = len(df)

        # 过拟合防护：最少 30 个信号
        if signal_count < 30:
            continue

        win_rate = (df['return'] > 0).sum() / len(df)
        avg_return = df['return'].mean()
        total_return = (1 + df['return']).prod() - 1
        avg_win = df[df['return'] > 0]['return'].mean() if win_rate > 0 else 0
        avg_loss = df[df['return'] <= 0]['return'].mean() if win_rate < 1 else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 99

        # ---- v4 新增: 计算 Sharpe 和 Sortino ----
        # 日均收益（简化：按信号排序窗口计算）
        daily_returns = df['return'].values
        sharpe = 0
        sortino = 0
        if len(daily_returns) >= 2 and daily_returns.std() > 0:
            # 模拟日收益率（用信号间距估算）
            sharpe = (daily_returns.mean() * 252) / (daily_returns.std() * np.sqrt(252))
            downside = daily_returns[daily_returns < 0]
            if len(downside) > 0 and downside.std() > 0:
                sortino = min((daily_returns.mean() * 252) / (downside.std() * np.sqrt(252)), 5)
            elif daily_returns.mean() > 0:
                sortino = 3.0  # 无下行波动

        # ---- v4 评分（多指标复合，所有项归一化到 [0,1] 防爆炸）----
        sharpe_norm = min(max(0, sharpe), 3) / 3          # Sharpe 封顶3→归一化
        sortino_norm = min(max(0, sortino), 5) / 5 if sortino < 99 else 0.8  # Sortino封顶5
        avg_ret_norm = max(0, min(avg_return, 0.03)) / 0.03  # 均收益封顶3%
        score = (
            win_rate * 0.35 +
            sharpe_norm * 0.25 +
            sortino_norm * 0.10 +
            min(signal_count / 150, 1) * 0.10 +
            avg_ret_norm * 0.20
        )

        results_list.append({
            **params_dict,
            'win_rate': round(win_rate, 4),
            'avg_return': round(avg_return, 4),
            'total_return': round(total_return, 4),
            'signal_count': signal_count,
            'profit_factor': round(profit_factor, 2),
            'sharpe': round(sharpe, 2),
            'sortino': round(sortino, 2),
            'score': round(score, 4),
        })

        if score > best_score:
            best_score = score
            best_params = params_dict.copy()
            best_signals = df.copy()

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
            print(f"  进度：{i+1}/{total_combos} ({((i+1)/total_combos)*100:.1f}%) | "
                  f"剩余：{remaining/60:.0f}分钟 | 最佳评分：{best_score:.4f} "
                  f"(胜率{(best_signals['return']>0).sum()/len(best_signals):.0%} "
                  f"Sharpe{sharpe:.1f})")

    # ---- 输出 ----
    print(f"\n{'='*60}")
    print(f"🏆 v4 最佳参数")
    print(f"{'='*60}")
    for k, v in best_params.items():
        print(f"  {k}: {v}")

    # 计算最佳参数的高级指标
    best_metrics = calculate_v4_metrics(best_signals, start_date=start_date, end_date=end_date)

    print(f"\n最佳参数回测结果：")
    print(f"  信号数：{len(best_signals)}")
    print(f"  胜率：{best_metrics.win_rate:.2%}")
    print(f"  平均收益：{best_metrics.avg_return:.2%}")
    print(f"  Sharpe: {best_metrics.sharpe_ratio:.2f} | Sortino: {best_metrics.sortino_ratio:.2f}")
    print(f"  Max Drawdown: {best_metrics.max_drawdown:.2f}%")
    print(f"  总收益(几何): {best_metrics.total_return_geo:.2%}")

    # 保存
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(BASE, 'optimization_v4_results.csv'), index=False, encoding='utf-8-sig')
    print(f"\n✅ 全部排名已保存至 optimization_v4_results.csv")
    print(f"\n前10名：")
    print(df_results.head(10)[['win_rate', 'avg_return', 'signal_count', 'sharpe', 'sortino', 'score'] + keys].to_string())

    # 关键发现
    print(f"\n{'='*60}")
    print(f"📊 v4 关键发现")
    print(f"{'='*60}")

    # 超跌效果
    oversold_on = df_results[df_results['require_oversold'] == True]
    oversold_off = df_results[df_results['require_oversold'] == False]
    if len(oversold_on) > 0 and len(oversold_off) > 0:
        print(f"\n超跌过滤 Top100均值：")
        print(f"  开启: 胜率{oversold_on.head(100)['win_rate'].mean():.2%} "
              f"均收益{oversold_on.head(100)['avg_return'].mean():.2%} "
              f"Sharpe{oversold_on.head(100)['sharpe'].mean():.2f} "
              f"信号{oversold_on.head(100)['signal_count'].mean():.0f}")
        print(f"  关闭: 胜率{oversold_off.head(100)['win_rate'].mean():.2%} "
              f"均收益{oversold_off.head(100)['avg_return'].mean():.2%} "
              f"Sharpe{oversold_off.head(100)['sharpe'].mean():.2f} "
              f"信号{oversold_off.head(100)['signal_count'].mean():.0f}")

    # 低位收盘效果
    lowclose_on = df_results[df_results['require_low_close'] == True]
    lowclose_off = df_results[df_results['require_low_close'] == False]
    if len(lowclose_on) > 0 and len(lowclose_off) > 0:
        print(f"\n低位收盘过滤 Top100均值：")
        print(f"  开启: 胜率{lowclose_on.head(100)['win_rate'].mean():.2%} "
              f"均收益{lowclose_on.head(100)['avg_return'].mean():.2%} "
              f"信号{lowclose_on.head(100)['signal_count'].mean():.0f}")
        print(f"  关闭: 胜率{lowclose_off.head(100)['win_rate'].mean():.2%} "
              f"均收益{lowclose_off.head(100)['avg_return'].mean():.2%} "
              f"信号{lowclose_off.head(100)['signal_count'].mean():.0f}")

    return best_params, best_signals, best_metrics


# ==================== 11. v4 Walk-Forward 分析 ====================
def walkforward_analysis(start_date, end_date, split_ratio=0.6):
    """
    Walk-forward 分析：样本内 → 样本外验证
    1. 前 split_ratio 作为样本内（IS），优化参数
    2. 后 (1-split_ratio) 作为样本外（OOS），用 IS 最佳参数做纯预测
    3. 对比 IS vs OOS 性能 → 检测过拟合
    """
    print("\n" + "=" * 70)
    print("🔬 v4 WALK-FORWARD 分析（样本内/外验证）")
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
    print(f"  划分比例: {split_ratio:.0%}/{1-split_ratio:.0%}")

    # ---- Step 1: IS 优化 ----
    print(f"\n{'─'*70}")
    print(f"  第一步：样本内参数优化")
    print(f"{'─'*70}")

    global PARAMS, COMMISSION
    original_params = PARAMS.copy()

    best_params, is_signals, is_metrics = optimize_params(is_start, is_end)

    # ---- Step 2: OOS 回测（用 IS 最佳参数）----
    print(f"\n{'─'*70}")
    print(f"  第二步：样本外验证（用IS最佳参数）")
    print(f"{'─'*70}")

    PARAMS.update(best_params)
    oos_result = run_backtest(oos_start, oos_end)
    if oos_result is not None:
        oos_df, oos_metrics = oos_result
    else:
        oos_df, oos_metrics = None, None

    # ---- Step 3: 对比 ----
    print(f"\n{'─'*70}")
    print(f"  Walk-Forward 对比报告")
    print(f"{'─'*70}")

    if is_metrics is not None and oos_metrics is not None:
        print(f"\n  {'指标':<25} {'IS (样本内)':<20} {'OOS (样本外)':<20} {'衰减':<15}")
        print(f"  {'─'*75}")
        is_win = is_metrics.win_rate
        oos_win = oos_metrics.win_rate
        print(f"  {'胜率':<25} {is_win:<20.2%} {oos_win:<20.2%} {(oos_win-is_win):<+.2%}")

        is_avg = is_metrics.avg_return
        oos_avg = oos_metrics.avg_return
        print(f"  {'平均收益':<25} {is_avg:<20.2%} {oos_avg:<20.2%} {(oos_avg-is_avg):<+.2%}")

        is_sharpe = is_metrics.sharpe_ratio
        oos_sharpe = oos_metrics.sharpe_ratio
        print(f"  {'Sharpe Ratio':<25} {is_sharpe:<20.2f} {oos_sharpe:<20.2f} {(oos_sharpe-is_sharpe):<+.2f}")

        is_sortino = is_metrics.sortino_ratio
        oos_sortino = oos_metrics.sortino_ratio
        print(f"  {'Sortino Ratio':<25} {is_sortino:<20.2f} {oos_sortino:<20.2f} {(oos_sortino-is_sortino):<+.2f}")

        is_dd = is_metrics.max_drawdown
        oos_dd = oos_metrics.max_drawdown
        print(f"  {'Max Drawdown':<25} {is_dd:<20.2f}% {oos_dd:<20.2f}% {-(oos_dd+is_dd):<+.2f}%")

        is_ntrades = is_metrics.total_trades
        oos_ntrades = oos_metrics.total_trades
        print(f"  {'信号数':<25} {is_ntrades:<20d} {oos_ntrades:<20d} {oos_ntrades-is_ntrades:<+d}")

        # ---- 过拟合判定 ----
        print(f"\n  {'─'*75}")
        print(f"  【过拟合诊断】")

        issues = []
        # 1. 胜率衰减
        win_decay = (oos_win - is_win)
        if win_decay < -0.10:
            issues.append(f"🔴 胜率衰减 >10pp ({win_decay:+.1%}) — 显著过拟合")
        elif win_decay < -0.05:
            issues.append(f"🟡 胜率小幅衰减 ({win_decay:+.1%}) — 轻度过拟合")
        else:
            issues.append(f"🟢 胜率稳定 ({win_decay:+.1%}) — 泛化良好")

        # 2. Sharpe 衰减
        sharpe_decay = (oos_sharpe - is_sharpe)
        if sharpe_decay < -1.0:
            issues.append(f"🔴 Sharpe大幅衰减 ({sharpe_decay:+.1f}) — 显著过拟合")
        elif sharpe_decay < -0.3:
            issues.append(f"🟡 Sharpe小幅衰减 ({sharpe_decay:+.1f}) — 注意优化偏误")
        else:
            issues.append(f"🟢 Sharpe稳定 ({sharpe_decay:+.1f}) — 泛化良好")

        for issue in issues:
            print(f"    {issue}")

        if len([i for i in issues if i.startswith('🟢')]) >= 2:
            print(f"\n  ✅ 结论：策略泛化能力良好，可用于实盘。")
        elif len([i for i in issues if i.startswith('🔴')]) >= 1:
            print(f"\n  ⚠️ 结论：存在明显过拟合，建议减少参数数量或增大样本内区间。")
        else:
            print(f"\n  ⚡ 结论：策略有一定泛化能力，但需持续监控样本外表现。")

    elif oos_result is None:
        print(f"  ⚠️ 样本外无信号，无法评估。可能参数过拟合或区间太短。")
    else:
        print(f"  ⚠️ 样本内无信号，无法完成分析。")

    # 恢复
    PARAMS.update(original_params)
    print(f"\n{'='*70}\n")

    return best_params, is_metrics, oos_metrics


# ==================== 参数模式配置 ====================
SCREEN_MODES = {
    "strict": {
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.3,
        "pullback_ratio_min": 0.08,
        "pullback_ratio_max": 0.15,
        "volume_shrink_ratio": 0.3,
        "volume_shrink_ratio_min": 0.05,
        "signal_today_yang": True,
        "signal_volume_expand": 1.2,
        "min_pullback_days": 2,
        "ma_stabilize": 10,
        "volume_compare_days": 3,
        "require_oversold": False,
        "oversold_decline_threshold": 0.10,
        "require_low_close": False,
        "low_close_threshold": 0.5,
    },
    "normal": {
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.15,
        "pullback_ratio_min": 0.05,
        "pullback_ratio_max": 0.30,
        "volume_shrink_ratio": 0.6,
        "volume_shrink_ratio_min": 0.0,
        "signal_today_yang": False,
        "signal_volume_expand": 1.0,
        "min_pullback_days": 1,
        "ma_stabilize": 10,
        "volume_compare_days": 3,
        "require_oversold": False,
        "oversold_decline_threshold": 0.10,
        "require_low_close": False,
        "low_close_threshold": 0.5,
    },
    "loose": {
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.0,
        "pullback_ratio_min": 0.02,
        "pullback_ratio_max": 0.40,
        "volume_shrink_ratio": 1.2,
        "volume_shrink_ratio_min": 0.0,
        "signal_today_yang": False,
        "signal_volume_expand": 0.0,
        "min_pullback_days": 1,
        "ma_stabilize": 5,
        "volume_compare_days": 2,
        "require_oversold": False,
        "oversold_decline_threshold": 0.10,
        "require_low_close": False,
        "low_close_threshold": 0.5,
    },
    "debug": {
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.0,
        "pullback_ratio_min": -1.0,
        "pullback_ratio_max": 10.0,
        "volume_shrink_ratio": 10.0,
        "volume_shrink_ratio_min": 0.0,
        "signal_today_yang": False,
        "signal_volume_expand": 0.0,
        "min_pullback_days": 0,
        "ma_stabilize": 0,
        "volume_compare_days": 1,
        "require_oversold": False,
        "oversold_decline_threshold": 0.10,
        "require_low_close": False,
        "low_close_threshold": 0.5,
    },
    "oversold": {
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.0,
        "pullback_ratio_min": 0.15,
        "pullback_ratio_max": 0.30,
        "volume_shrink_ratio": 0.3,
        "volume_shrink_ratio_min": 0.05,
        "signal_today_yang": False,
        "signal_volume_expand": 0.0,
        "min_pullback_days": 2,
        "ma_stabilize": 5,
        "volume_compare_days": 3,
        "require_oversold": True,
        "oversold_decline_threshold": 0.10,
        "require_low_close": True,
        "low_close_threshold": 0.5,
    }
}


# ==================== 单只股票筛选 ====================
def _screen_single_stock(code, stock_df, stats, candidates, mode="normal"):
    """对单只股票的近期数据执行完整筛选流程"""
    close = stock_df['Close'].dropna()
    if len(close) < 15:
        return
    stats['has_data'] += 1

    open_price = stock_df['Open'].dropna()
    high = stock_df['High'].dropna()
    low = stock_df['Low'].dropna()
    volume = stock_df['Volume'].dropna()

    min_len = min(len(close), len(open_price), len(high), len(low), len(volume))
    if min_len < 10:
        return

    recent = pd.DataFrame({
        'close': close.values, 'open': open_price.values,
        'high': high.values, 'low': low.values, 'volume': volume.values,
    }, index=close.index)

    recent['pct_chg'] = recent['close'].pct_change() * 100
    recent['trade_date'] = close.index.strftime('%Y%m%d')
    limit_series_list = identify_limit_up_series(recent.dropna(subset=['pct_chg']).reset_index(drop=True), code)

    found_signal = False
    for series in limit_series_list:
        last_date = series[-1]['date']
        for offset in range(PARAMS['min_pullback_days'] + 1, 15):
            check_idx = len(recent) - offset
            if check_idx < 10:
                break
            if recent.index[check_idx - 1] < 0:
                break
            result = check_pullback_conditions(recent.reset_index(drop=True), series, check_idx)
            if result:
                candidates.append({
                    '代码': code,
                    '最新价': recent.iloc[-1]['close'],
                    '信号日': result['trigger_date'],
                    '信号价': result['trigger_price'],
                    '回调比': result['pullback_ratio'],
                    '连板数': result['limit_series_len'],
                    '连板日期': result['limit_dates'],
                })
                found_signal = True
                break
        if found_signal:
            break


# ==================== 当日选股 ====================
def screen_today(mode="normal"):
    """当日选股（v4: 使用 PARAMS 中的当前参数）"""
    global PARAMS
    PARAMS.update(SCREEN_MODES.get(mode, SCREEN_MODES['normal']))
    PARAMS.update({
        "hold_days": 7, "take_profit": 0.05, "stop_loss": -0.07,
    })

    print("=" * 60)
    print(f"当日选股 v4 — 模式: {mode}")
    print("=" * 60)

    import yfinance as yf
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]

    today = datetime.now().strftime('%Y-%m-%d')
    print(f"正在获取今日行情...")
    candidates = []
    stats = {'total': len(cache_files), 'has_data': 0, 'has_limit_up': 0, 'has_signal': 0}

    for idx, fname in enumerate(cache_files):
        code = fname.replace('.csv', '')
        if (idx + 1) % 500 == 0:
            print(f"  已扫描 {idx+1}/{len(cache_files)}...")

        try:
            ticker = yf.Ticker(code)
            df = ticker.history(period="3mo")
            if df is None or len(df) < 15:
                continue
            _screen_single_stock(code, df, stats, candidates, mode)
        except:
            continue

    print(f"\n✅ 扫描完成！")
    print(f"  总候选: {stats['total']} | 有数据: {stats['has_data']} | 选出: {len(candidates)}")
    return candidates


# ==================== 主入口 ====================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h']:
        print("=" * 60)
        print("A股连板回调策略 v4 — 专业量化回测框架")
        print("=" * 60)
        print("")
        print("用法:")
        print("  python 选股new_v4.py --download         # 下载全量历史数据")
        print("  python 选股new_v4.py --today [模式]     # 当日选股")
        print("  python 选股new_v4.py --optimize         # 参数优化")
        print("  python 选股new_v4.py --walkforward      # Walk-forward分析")
        print("  python 选股new_v4.py                    # 完整评估流程")
        print("")
        print("模式: strict | normal | loose | oversold | debug")
        print("")
        print("v4 新增（基于 backtesting-trading-strategies skill):")
        print("  - Sharpe/Sortino/Calmar 风险调整指标")
        print("  - Max Drawdown + VaR/CVaR 尾部风险")
        print("  - A股真实手续费建模（印花税+佣金+过户费+滑点）")
        print("  - Walk-forward 样本内/外验证")
        print("  - 资金曲线 + Expectancy + Ulcer Index")
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--download':
        download_all_data()
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--optimize':
        print("=" * 60)
        print("v4 参数优化模式")
        print("=" * 60)
        best_params, best_df, best_metrics = optimize_params('20250101', '20260430')
        print("\n✅ 参数优化完成！")
        if best_metrics:
            print_v4_report(best_metrics, "Best Params")
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
            print(f"\n共选出 {len(candidates)} 只候选股票:")
            codes = [c['代码'] for c in candidates]
            print(f"CANDIDATE_CODES = {codes}")
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--walkforward':
        walkforward_analysis('20250101', '20260430', split_ratio=0.6)
        sys.exit()

    # ========== 默认：完整评估流程 ==========
    print("=" * 60)
    print("v4 完整评估流程")
    print("=" * 60)
    print("将依次运行：")
    print("  1. v3 最佳参数回测（Baseline）")
    print("  2. v4 参数自动寻优（含Sharpe/Sortino评分）")
    print("  3. v4 最佳参数回测")
    print("  4. Walk-Forward 样本内/外验证")
    print("  5. 综合对比报告")
    print("")

    # ---- 1. Baseline ----
    print("\n" + "=" * 60)
    print("📊 第一步：v3 最佳参数回测（Baseline）")
    print("=" * 60)
    PARAMS.update({
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.5,
        "pullback_ratio_min": 0.08,
        "pullback_ratio_max": 0.25,
        "volume_shrink_ratio": 0.50,
        "volume_shrink_ratio_min": 0.0,
        "take_profit": 0.05,
        "stop_loss": -0.10,
        "hold_days": 7,
        "require_oversold": False,
        "require_low_close": False,
    })
    baseline_result = run_backtest('20250101', '20260430')
    if baseline_result is not None:
        baseline_df, baseline_metrics = baseline_result
    else:
        baseline_df, baseline_metrics = None, None

    # ---- 2. v4 参数寻优 ----
    print("\n" + "=" * 60)
    print("🔍 第二步：v4 参数自动寻优")
    print("=" * 60)
    best_params, best_signals, best_metrics = optimize_params('20250101', '20260430')

    # ---- 3. v4 最佳参数回测 ----
    print("\n" + "=" * 60)
    print("✅ 第三步：v4 最佳参数验证回测")
    print("=" * 60)
    PARAMS.update(best_params)
    v4_result = run_backtest('20250101', '20260430')
    if v4_result is not None:
        v4_df, v4_metrics = v4_result
    else:
        v4_df, v4_metrics = None, None

    # ---- 4. Walk-Forward ----
    print("\n" + "=" * 60)
    print("🔬 第四步：Walk-Forward 验证")
    print("=" * 60)
    wf_params, is_metrics, oos_metrics = walkforward_analysis('20250101', '20260430', split_ratio=0.6)

    # ---- 5. 综合对比 ----
    if baseline_metrics is not None and v4_metrics is not None:
        print("\n" + "=" * 70)
        print("🏆 第五步：v3 Baseline vs v4 综合对比")
        print("=" * 70)

        print(f"\n  {'指标':<25} {'v3 Baseline':<18} {'v4 最佳':<18} {'变化':<15}")
        print(f"  {'─'*75}")
        print(f"  {'胜率':<25} {baseline_metrics.win_rate:<18.2%} {v4_metrics.win_rate:<18.2%} {v4_metrics.win_rate-baseline_metrics.win_rate:<+.2%}")
        print(f"  {'平均收益':<25} {baseline_metrics.avg_return:<18.2%} {v4_metrics.avg_return:<18.2%} {v4_metrics.avg_return-baseline_metrics.avg_return:<+.2%}")
        print(f"  {'Sharpe Ratio':<25} {baseline_metrics.sharpe_ratio:<18.2f} {v4_metrics.sharpe_ratio:<18.2f} {v4_metrics.sharpe_ratio-baseline_metrics.sharpe_ratio:<+.2f}")
        print(f"  {'Sortino Ratio':<25} {baseline_metrics.sortino_ratio:<18.2f} {v4_metrics.sortino_ratio:<18.2f} {v4_metrics.sortino_ratio-baseline_metrics.sortino_ratio:<+.2f}")
        print(f"  {'Max Drawdown':<25} {baseline_metrics.max_drawdown:<18.2f}% {v4_metrics.max_drawdown:<18.2f}% {-(v4_metrics.max_drawdown+baseline_metrics.max_drawdown):<+.2f}%")
        print(f"  {'Profit Factor':<25} {baseline_metrics.profit_factor:<18.2f} {v4_metrics.profit_factor:<18.2f} {v4_metrics.profit_factor-baseline_metrics.profit_factor:<+.2f}")
        print(f"  {'Expectancy':<25} {baseline_metrics.expectancy:<18.2%} {v4_metrics.expectancy:<18.2%} {v4_metrics.expectancy-baseline_metrics.expectancy:<+.2%}")
        print(f"  {'Max Consec Loss':<25} {baseline_metrics.max_consecutive_losses:<18d} {v4_metrics.max_consecutive_losses:<18d}")
        print(f"  {'信号数':<25} {baseline_metrics.total_trades:<18d} {v4_metrics.total_trades:<18d} {v4_metrics.total_trades-baseline_metrics.total_trades:<+d}")

        # 最终结论
        print(f"\n  {'─'*75}")
        print(f"  📋 最终结论：")
        improvements = []
        if v4_metrics.win_rate > baseline_metrics.win_rate:
            improvements.append(f"胜率 {v4_metrics.win_rate-baseline_metrics.win_rate:+.1%}")
        if v4_metrics.sharpe_ratio > baseline_metrics.sharpe_ratio:
            improvements.append(f"Sharpe {v4_metrics.sharpe_ratio-baseline_metrics.sharpe_ratio:+.2f}")
        if v4_metrics.max_drawdown > -0.01 and v4_metrics.max_drawdown > baseline_metrics.max_drawdown:
            improvements.append(f"回撤改善")

        if improvements:
            print(f"  ✅ v4 在以下方面超越 baseline：{', '.join(improvements)}")
        else:
            print(f"  ⚠️ v4 未显著超越 baseline，但提供了更全面的风险指标和过拟合验证。")

        # Walk-forward 状态
        if oos_metrics is not None:
            oos_win = oos_metrics.win_rate
            is_win_val = is_metrics.win_rate if is_metrics else 0
            if oos_win > 0.5 and abs(oos_win - is_win_val) < 0.1:
                print(f"  🟢 Walk-forward 验证通过：样本外胜率 {oos_win:.1%}，策略可泛化。")
            else:
                print(f"  🟡 Walk-forward 提示关注：样本外胜率 {oos_win:.1%}，建议持续跟踪。")

    print(f"\n{'='*70}")
    print(f"v4 评估完成！")
    print(f"{'='*70}")
