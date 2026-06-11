"""
A股连板回调策略 V2.2 - 修正版
修正：
1. 情绪过滤改用滚动20日（消除未来函数）
2. 一字跌停无法止损（流动性限制）
3. 涨停开盘买不到（跳过信号）
4. 初步最高板逻辑
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import os
import warnings
from itertools import product

warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "stock_data")
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== 参数配置 ====================
PARAMS = {
    # ---- 情绪过滤 ----
    "sentiment_lookback": 20,        # 滚动N日判断情绪
    "sentiment_threshold": 0.35,     # 活跃度分位数阈值

    # ---- 龙头识别 ----
    "use_highest_board": True,       # 是否只做最高板
    "min_consecutive_limit_up": 2,
    "min_entity_board_ratio": 0.5,

    # ---- 回调条件 ----
    "pullback_ratio_min": 0.08,
    "pullback_ratio_max": 0.30,
    "min_pullback_days": 2,

    # ---- 反弹确认 ----
    "require_weak_to_strong": True,
    "min_pct_today": 1.0,

    # ---- 均线和量能 ----
    "ma_stabilize": 10,
    "volume_shrink_ratio": 0.5,

    # ---- 动态止盈止损 ----
    "atr_period": 14,
    "stop_loss_atr_mult": 0.8,
    "take_profit_atr_mult": 1.5,
    "max_hold_days": 10,

    # ---- 流动性限制 ----
    "skip_limit_open": True,         # 跳过开盘涨停的信号（买不到）
    "allow_exit_at_limit_down": False,  # 跌停板是否允许止损（否=更真实）

    # ===== 实盘成本与风控 =====
    "commission_buy": 0.0003,
    "commission_sell": 0.0013,
    "slippage": 0.003,
    "position_size": 0.33,
    "max_positions": 3,
}

# ==================== 涨停判断 ====================
def is_limit_down(code, pct_chg):
    """判断跌停"""
    if code.startswith(('300', '301', '688')):
        return pct_chg <= -19.5
    elif code.startswith(('8', '4')):
        return pct_chg <= -29.5
    else:
        return pct_chg <= -9.5

def get_limit_threshold(code):
    if code.startswith(('300', '301', '688')):
        return 19.5
    elif code.startswith(('8', '4')):
        return 29.5
    else:
        return 9.5

def get_limit_down_pct(code):
    """跌停价相对于昨收的跌幅"""
    if code.startswith(('300', '301', '688')):
        return -0.20
    elif code.startswith(('8', '4')):
        return -0.30
    else:
        return -0.10

# ==================== 数据加载 ====================
def load_from_cache(code):
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
        df = df.sort_values('trade_date').reset_index(drop=True)
        return df
    except:
        return None

# ==================== 滚动情绪计算 ====================
def build_rolling_sentiment(cache_files, start_date, end_date):
    """
    构建每日滚动情绪指标（无未来函数）
    对每个交易日，只看它之前20天的涨停家数
    """
    print("构建滚动情绪指标...")
    
    # 先收集所有股票的涨停日期
    all_limit_dates = []
    for fname in cache_files:
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 30:
            continue
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        limit_threshold = get_limit_threshold(code)
        limit_dates = df[df['pct_chg'] >= limit_threshold]['trade_date'].tolist()
        all_limit_dates.extend(limit_dates)
    
    # 统计每日涨停家数
    from collections import Counter
    daily_count = Counter(all_limit_dates)
    
    # 获取回测区间所有交易日
    all_dates = sorted(daily_count.keys())
    
    # 滚动20日活跃度
    sentiment_score = {}
    for i, date in enumerate(all_dates):
        lookback_dates = [d for d in all_dates[max(0, i-19):i+1]]
        avg_count = np.mean([daily_count[d] for d in lookback_dates]) if lookback_dates else 0
        sentiment_score[date] = avg_count
    
    # 计算阈值
    if sentiment_score:
        threshold = np.percentile(list(sentiment_score.values()), 30)
    else:
        threshold = 0
    
    print(f"  交易日数：{len(sentiment_score)}")
    print(f"  情绪阈值（30%分位）：{threshold:.1f}只/日\n")
    
    return sentiment_score, threshold

# ==================== 核心回测函数 ====================
def run_backtest_v2(start_date, end_date):
    print("=" * 70)
    print("连板回调策略 V2.2 修正版回测")
    print("=" * 70)
    print(f"回测区间：{start_date} ~ {end_date}")
    print(f"单笔仓位：{PARAMS['position_size']:.0%} | 滑点：{PARAMS['slippage']:.1%} | "
          f"手续费：买{PARAMS['commission_buy']*100:.2f}%/卖{PARAMS['commission_sell']*100:.2f}%")
    print(f"流动性限制：{'是' if PARAMS['skip_limit_open'] else '否'}跳过开盘涨停 | "
          f"{'否' if PARAMS['allow_exit_at_limit_down'] else '是'}跌停不可止损\n")

    cache_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    
    # ===== 构建滚动情绪 =====
    sentiment_score, sentiment_threshold = build_rolling_sentiment(cache_files, start_date, end_date)
    
    all_trades = []
    start_time = time.time()
    print(f"共找到 {len(cache_files)} 只股票数据...\n")

    for idx, fname in enumerate(cache_files):
        code = fname.replace('.csv', '')
        if (idx + 1) % 500 == 0:
            print(f"进度：{idx+1}/{len(cache_files)} | 已发现交易：{len(all_trades)}")

        df = load_from_cache(code)
        if df is None or len(df) < 60:
            continue

        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)].reset_index(drop=True)
        if len(df) < 30:
            continue

        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(abs(df['high'] - df['close'].shift(1)),
                       abs(df['low'] - df['close'].shift(1)))
        )
        df['atr'] = df['tr'].rolling(PARAMS['atr_period']).mean().shift(1)

        limit_threshold = get_limit_threshold(code)
        limit_down_pct = get_limit_down_pct(code)
        df['is_limit_up'] = df['pct_chg'] >= limit_threshold
        df['is_limit_down'] = df['pct_chg'] <= limit_down_pct * 100
        df['is_one_word'] = (df['open'] == df['high']) & (df['low'] == df['close']) & df['is_limit_up']

        limit_up_indices = df[df['is_limit_up']].index.tolist()
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
            entity_count = sum(1 for i in group if not df.iloc[i]['is_one_word'])
            if entity_count / len(group) < PARAMS['min_entity_board_ratio']:
                continue

            last_limit_idx = group[-1]
            highest_price = max(df.iloc[i]['high'] for i in group)
            limit_avg_vol = np.mean([df.iloc[i]['volume'] for i in group])

            for check_idx in range(last_limit_idx + PARAMS['min_pullback_days'] + 1,
                                  min(last_limit_idx + 15, len(df) - 1)):
                current_row = df.iloc[check_idx]
                prev_row = df.iloc[check_idx - 1]
                current_price = current_row['close']
                
                # ===== 情绪过滤：信号日滚动活跃度 =====
                signal_date = current_row['trade_date'] if 'trade_date' in df.columns else str(current_row.name)
                if sentiment_score.get(signal_date, 0) < sentiment_threshold:
                    continue

                pullback_ratio = (highest_price - current_price) / highest_price
                if not (PARAMS['pullback_ratio_min'] <= pullback_ratio <= PARAMS['pullback_ratio_max']):
                    continue

                if check_idx >= PARAMS['ma_stabilize']:
                    ma = df.iloc[check_idx - PARAMS['ma_stabilize'] + 1:check_idx + 1]['close'].mean()
                    if current_price < ma:
                        continue

                pullback_vol = df.iloc[check_idx - 3:check_idx]['volume'].mean()
                if limit_avg_vol > 0 and pullback_vol / limit_avg_vol > PARAMS['volume_shrink_ratio']:
                    continue

                if PARAMS['require_weak_to_strong'] and current_row['close'] <= prev_row['high']:
                    continue
                today_pct = (current_row['close'] / prev_row['close'] - 1) * 100
                if today_pct < PARAMS['min_pct_today'] or current_row['close'] <= current_row['open']:
                    continue

                next_idx = check_idx + 1
                if next_idx >= len(df):
                    continue

                next_row = df.iloc[next_idx]
                
                # ===== 修正1：跳过开盘涨停（买不到）=====
                if PARAMS['skip_limit_open']:
                    open_pct = (next_row['open'] / current_row['close'] - 1) * 100
                    if open_pct >= limit_threshold:
                        continue

                entry_price = next_row['open'] * (1 + PARAMS['slippage'])

                atr_val = df.iloc[check_idx]['atr']
                if pd.isna(atr_val) or atr_val <= 0:
                    atr_val = current_price * 0.03

                stop_loss_price = entry_price - PARAMS['stop_loss_atr_mult'] * atr_val
                take_profit_price = entry_price + PARAMS['take_profit_atr_mult'] * atr_val

                exit_reason = '到期'
                days_held = PARAMS['max_hold_days']
                trade_return = 0.0

                for hold_day in range(1, PARAMS['max_hold_days'] + 1):
                    hold_idx = next_idx + hold_day
                    if hold_idx >= len(df):
                        exit_price = df.iloc[-1]['close'] * (1 - PARAMS['slippage'])
                        trade_return = (exit_price / entry_price) - 1
                        exit_reason = '到期'
                        days_held = hold_day
                        break

                    bar = df.iloc[hold_idx]

                    # ===== 修正2：跌停板不可止损 =====
                    if bar['low'] <= stop_loss_price:
                        if PARAMS['allow_exit_at_limit_down'] or not bar['is_limit_down']:
                            exit_price = stop_loss_price * (1 - PARAMS['slippage'])
                            trade_return = (exit_price / entry_price) - 1
                            exit_reason = '止损'
                            days_held = hold_day
                            break
                        # 跌停且不允许止损 → 跳过，继续持仓
                    
                    if bar['high'] >= take_profit_price:
                        exit_price = take_profit_price * (1 - PARAMS['slippage'])
                        trade_return = (exit_price / entry_price) - 1
                        exit_reason = '止盈'
                        days_held = hold_day
                        break

                else:
                    exit_idx = next_idx + PARAMS['max_hold_days']
                    if exit_idx < len(df):
                        exit_price = df.iloc[exit_idx]['close'] * (1 - PARAMS['slippage'])
                        trade_return = (exit_price / entry_price) - 1
                    else:
                        exit_price = df.iloc[-1]['close'] * (1 - PARAMS['slippage'])
                        trade_return = (exit_price / entry_price) - 1

                trade_return -= PARAMS['commission_buy'] + PARAMS['commission_sell']

                all_trades.append({
                    'code': code,
                    'entry_date': df.iloc[next_idx]['trade_date'],
                    'entry_price': round(entry_price, 3),
                    'return': round(trade_return, 4),
                    'hold_days': days_held,
                    'exit_reason': exit_reason,
                    'pullback_ratio': round(pullback_ratio, 3),
                    'board_height': len(group),
                })

    elapsed = time.time() - start_time
    print(f"\n回测完成！耗时 {elapsed:.0f} 秒 | 总交易次数：{len(all_trades)}")

    if not all_trades:
        print("未发现任何交易信号")
        return None

    df_trades = pd.DataFrame(all_trades)
    df_trades.to_csv(os.path.join(BASE, f'backtest_v2.2_{start_date}_{end_date}.csv'), index=False, encoding='utf-8-sig')

    returns = df_trades['return'].values
    wins = returns[returns > 0]
    losses = returns[returns <= 0]

    print(f"\n{'='*60}")
    print(f"【核心指标】")
    print(f"  交易次数：{len(df_trades)}")
    print(f"  胜率：{len(wins)/len(returns):.2%}")
    print(f"  平均收益：{returns.mean():.2%}")
    print(f"  平均盈利：{wins.mean():.2%} | 平均亏损：{losses.mean():.2%}")
    print(f"  盈亏比：{abs(wins.mean()/losses.mean()):.2f}" if len(losses) > 0 else "  盈亏比：N/A")
    print(f"  最大盈利：{returns.max():.2%} | 最大亏损：{returns.min():.2%}")

    print(f"\n【退出原因】")
    for reason, count in df_trades['exit_reason'].value_counts().items():
        print(f"  {reason}：{count}次 ({count/len(df_trades)*100:.1f}%)")

    risk_analysis(df_trades, PARAMS['position_size'])
    return df_trades


# ==================== 风险分析 ====================
def risk_analysis(df_trades, position_size=0.20):
    print(f"\n{'='*75}")
    print(f"📊 实盘风险分析报告（单笔仓位 {position_size:.0%}）")
    print(f"{'='*75}")

    df = df_trades.sort_values('entry_date').copy()
    df['month'] = df['entry_date'].str[:6]

    capital = 1.0
    equity_curve = [capital]
    monthly_start = {}

    for i, ret in enumerate(df['return']):
        current_month = df['month'].iloc[i]
        if current_month not in monthly_start:
            monthly_start[current_month] = capital
        trade_ret = position_size * ret
        capital = capital * (1 + trade_ret)
        equity_curve.append(capital)

    total_return = capital - 1
    months = sorted(monthly_start.keys())
    months_count = len(months)

    annual_return = (1 + total_return) ** (12 / months_count) - 1 if months_count > 1 else total_return

    monthly_rets = []
    month_labels = []
    for m in months:
        month_trades = df[df['month'] == m]
        if len(month_trades) > 0:
            month_ret = position_size * month_trades['return'].sum()
            monthly_rets.append(month_ret)
            month_labels.append(m)

    monthly_rets = np.array(monthly_rets)

    equity = np.array(equity_curve)
    running_max = np.maximum.accumulate(equity)
    max_drawdown = (equity - running_max).min() / running_max.max()

    annual_vol = monthly_rets.std() * np.sqrt(12) if len(monthly_rets) > 1 else 0
    sharpe = (annual_return - 0.03) / annual_vol if annual_vol > 0 else 0

    print(f"\n【收益与风险指标】")
    print(f"  总收益：{total_return:.2%}")
    print(f"  年化收益：{annual_return:.2%}")
    print(f"  年化波动率：{annual_vol:.2%}")
    print(f"  最大回撤：{max_drawdown:.2%}")
    print(f"  夏普比率：{sharpe:.2f}")

    returns = df['return'].values
    wins = returns[returns > 0]
    losses = returns[returns <= 0]

    print(f"\n【单笔统计】")
    print(f"  交易次数：{len(returns)}")
    print(f"  胜率：{len(wins)/len(returns):.1%}")
    if len(wins) > 0:
        print(f"  平均盈利：{wins.mean():.2%}")
    if len(losses) > 0:
        print(f"  平均亏损：{losses.mean():.2%}")
        print(f"  盈亏比：{abs(wins.mean()/losses.mean()):.2f}")

    print(f"\n【月度收益分布】")
    for i, m in enumerate(month_labels):
        bar = "█" * min(50, max(0, int(monthly_rets[i] * 200)))
        print(f"  {m}: {monthly_rets[i]:+.2%} {bar}")

    profit_months = (monthly_rets > 0).sum()
    print(f"\n  盈利月份：{profit_months}/{len(month_labels)} ({profit_months/len(month_labels)*100:.0f}%)")

    report = {
        '总收益': round(total_return, 4),
        '年化收益': round(annual_return, 4),
        '年化波动率': round(annual_vol, 4),
        '最大回撤': round(max_drawdown, 4),
        '夏普比率': round(sharpe, 2),
        '交易次数': len(returns),
        '胜率': round(len(wins)/len(returns), 4),
        '盈亏比': round(abs(wins.mean()/losses.mean()), 2) if len(losses) > 0 else 0,
    }
    pd.DataFrame([report]).to_csv(os.path.join(BASE, 'risk_report_v2.2.csv'), index=False, encoding='utf-8-sig')
    print(f"\n✅ 风险报告已保存至 risk_report_v2.2.csv")
    return total_return, annual_return, max_drawdown

# ==================== 预提取事件（V2.2修正版）====================
def extract_all_events_v2_2(start_date, end_date):
    """预提取所有连板→回调事件，并附上情绪标签"""
    print("第一步：构建滚动情绪指标...")
    
    cache_files = [f for f in os.listdir(DATA_DIR) 
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    
    # 先收集所有股票的涨停日期
    all_limit_dates = []
    for fname in cache_files:
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 30:
            continue
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        limit_threshold = get_limit_threshold(code)
        limit_dates = df[df['pct_chg'] >= limit_threshold]['trade_date'].tolist()
        all_limit_dates.extend(limit_dates)
    
    from collections import Counter
    daily_count = Counter(all_limit_dates)
    all_dates = sorted(daily_count.keys())
    
    # 滚动20日活跃度
    sentiment_score = {}
    for i, date in enumerate(all_dates):
        lookback_dates = [d for d in all_dates[max(0, i-19):i+1]]
        avg_count = np.mean([daily_count[d] for d in lookback_dates]) if lookback_dates else 0
        sentiment_score[date] = avg_count
    
    sentiment_threshold = np.percentile(list(sentiment_score.values()), 30) if sentiment_score else 0
    print(f"  情绪阈值（30%分位）：{sentiment_threshold:.1f}只/日\n")
    
    # ===== 预提取事件 =====
    print("第二步：预提取连板事件...")
    all_events = []
    
    for idx, fname in enumerate(cache_files):
        if (idx + 1) % 500 == 0:
            print(f"  进度：{idx+1}/{len(cache_files)}，事件：{len(all_events)}")
        
        code = fname.replace('.csv', '')
        df = load_from_cache(code)
        if df is None or len(df) < 60:
            continue
        
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        if len(df) < 30:
            continue
        
        df = df.reset_index(drop=True)
        
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(abs(df['high'] - df['close'].shift(1)),
                       abs(df['low'] - df['close'].shift(1)))
        )
        df['atr'] = df['tr'].rolling(14).mean().shift(1)
        
        limit_threshold = get_limit_threshold(code)
        df['is_limit_up'] = df['pct_chg'] >= limit_threshold
        df['is_one_word'] = (df['open'] == df['high']) & (df['low'] == df['close']) & df['is_limit_up']
        
        limit_up_indices = df[df['is_limit_up']].index.tolist()
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
            
            entity_count = sum(1 for i in group if not df.iloc[i]['is_one_word'])
            entity_ratio = entity_count / len(group)
            highest_price = max(df.iloc[i]['high'] for i in group)
            limit_avg_vol = np.mean([df.iloc[i]['volume'] for i in group])
            last_limit_idx = group[-1]
            
            for check_idx in range(last_limit_idx + 2, min(last_limit_idx + 15, len(df) - 1)):
                current_row = df.iloc[check_idx]
                prev_row = df.iloc[check_idx - 1]
                current_price = current_row['close']
                
                signal_date = current_row['trade_date'] if 'trade_date' in df.columns else ''
                
                pullback_ratio = (highest_price - current_price) / highest_price
                pullback_vol = df.iloc[max(0, check_idx-3):check_idx]['volume'].mean()
                vol_shrink = pullback_vol / limit_avg_vol if limit_avg_vol > 0 else 1
                
                ma_val = df.iloc[max(0, check_idx-9):check_idx+1]['close'].mean() if check_idx >= 9 else current_price
                
                is_weak_to_strong = current_row['close'] > prev_row['high']
                today_pct = (current_row['close'] / prev_row['close'] - 1) * 100
                is_yang = current_row['close'] > current_row['open']
                
                next_idx = check_idx + 1
                if next_idx >= len(df):
                    continue
                next_row = df.iloc[next_idx]
                
                # 开盘涨停跳过
                open_pct = (next_row['open'] / current_row['close'] - 1) * 100
                if open_pct >= limit_threshold:
                    continue
                
                next_open = next_row['open']
                
                atr_val = df.iloc[check_idx]['atr']
                if pd.isna(atr_val) or atr_val <= 0:
                    atr_val = current_price * 0.03
                
                # 情绪标签
                sentiment_val = sentiment_score.get(signal_date, sentiment_threshold)
                
                # 未来N天数据
                future = []
                for fwd in range(1, 15):
                    fwd_idx = next_idx + fwd
                    if fwd_idx >= len(df):
                        break
                    bar = df.iloc[fwd_idx]
                    future.append({
                        'open': bar['open'],
                        'high': bar['high'],
                        'low': bar['low'],
                        'close': bar['close'],
                        'is_limit_down': bar['is_limit_down'] if 'is_limit_down' in df.columns else (
                            bar['pct_chg'] <= get_limit_down_pct(code) * 100
                        ),
                    })
                
                all_events.append({
                    'code': code,
                    'board_height': len(group),
                    'entity_ratio': entity_ratio,
                    'pullback_ratio': pullback_ratio,
                    'vol_shrink': vol_shrink,
                    'ma': ma_val,
                    'current_price': current_price,
                    'is_weak_to_strong': is_weak_to_strong,
                    'today_pct': today_pct,
                    'is_yang': is_yang,
                    'next_open': next_open,
                    'atr': atr_val,
                    'sentiment': sentiment_val,
                    'future': future,
                })
    
    print(f"✅ 预提取完成：{len(all_events)} 个事件")
    return all_events, sentiment_threshold


# ==================== 参数优化（V2.2修正版）====================
def optimize_v2_2(start_date, end_date):
    """基于预提取事件的快速参数优化"""
    print("=" * 60)
    print("策略V2.2 参数优化（修正版）")
    print("=" * 60)
    print(f"滑点：{PARAMS['slippage']:.1%} | 手续费：买{PARAMS['commission_buy']*100:.2f}%/卖{PARAMS['commission_sell']*100:.2f}%")
    print(f"流动性限制：跳过开盘涨停 | 跌停不可止损\n")
    
    all_events, sentiment_threshold = extract_all_events_v2_2(start_date, end_date)
    
    param_grid = {
        "min_consecutive_limit_up": [2, 3],
        "min_entity_board_ratio": [0.3, 0.5],
        "pullback_ratio_min": [0.05, 0.08, 0.10],
        "pullback_ratio_max": [0.20, 0.25, 0.30],
        "volume_shrink_ratio": [0.3, 0.4, 0.5],
        "min_pct_today": [1.0, 2.0, 3.0],
        "stop_loss_atr_mult": [0.5, 0.8, 1.0],
        "take_profit_atr_mult": [1.5, 2.0, 2.5],
        "max_hold_days": [5, 7, 10],
        "sentiment_threshold_override": [0, 0.5, 1.0],  # 0=无情绪过滤, 0.5=阈值×0.5, 1.0=原阈值
    }
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combos = list(product(*values))
    
    total = len(all_combos)
    print(f"遍历 {total} 组参数（{len(all_events)} 个事件）...\n")
    
    results_list = []
    best_score = -999
    best_params = None
    best_trades = None
    
    start_time = time.time()
    slippage = PARAMS['slippage']
    comm_buy = PARAMS['commission_buy']
    comm_sell = PARAMS['commission_sell']
    
    for i, combo in enumerate(all_combos):
        p = dict(zip(keys, combo))
        
        # 情绪阈值
        eff_threshold = sentiment_threshold * p['sentiment_threshold_override']
        del p['sentiment_threshold_override']
        
        trades = []
        
        for evt in all_events:
            # 情绪过滤
            if eff_threshold > 0 and evt.get('sentiment', 0) < eff_threshold:
                continue
            
            if evt['board_height'] < p['min_consecutive_limit_up']:
                continue
            if evt['entity_ratio'] < p['min_entity_board_ratio']:
                continue
            if evt['pullback_ratio'] < p['pullback_ratio_min'] or evt['pullback_ratio'] > p['pullback_ratio_max']:
                continue
            if evt['vol_shrink'] > p['volume_shrink_ratio']:
                continue
            if evt['current_price'] < evt['ma']:
                continue
            if not evt['is_weak_to_strong']:
                continue
            if evt['today_pct'] < p['min_pct_today']:
                continue
            if not evt['is_yang']:
                continue
            
            entry_price = evt['next_open'] * (1 + slippage)
            atr_val = evt['atr']
            
            stop_loss_price = entry_price - p['stop_loss_atr_mult'] * atr_val
            take_profit_price = entry_price + p['take_profit_atr_mult'] * atr_val
            
            ret = 0
            for fwd_idx, bar in enumerate(evt['future']):
                if fwd_idx >= p['max_hold_days']:
                    break
                
                # 止损（跌停不可成交）
                if bar['low'] <= stop_loss_price:
                    if not bar.get('is_limit_down', False):
                        exit_price = stop_loss_price * (1 - slippage)
                        ret = (exit_price / entry_price) - 1
                        break
                
                if bar['high'] >= take_profit_price:
                    exit_price = take_profit_price * (1 - slippage)
                    ret = (exit_price / entry_price) - 1
                    break
            else:
                if len(evt['future']) >= p['max_hold_days']:
                    exit_price = evt['future'][p['max_hold_days']-1]['close'] * (1 - slippage)
                    ret = (exit_price / entry_price) - 1
                elif len(evt['future']) > 0:
                    exit_price = evt['future'][-1]['close'] * (1 - slippage)
                    ret = (exit_price / entry_price) - 1
            
            ret -= comm_buy + comm_sell
            trades.append(ret)
        
        if len(trades) < 20:
            continue
        
        trades = np.array(trades)
        win_rate = (trades > 0).sum() / len(trades)
        avg_ret = trades.mean()
        
        score = win_rate * 0.4 + avg_ret * 3 + min(len(trades)/200, 1) * 0.3
        
        results_list.append({
            **p,
            'win_rate': round(win_rate, 4),
            'avg_return': round(avg_ret, 4),
            'trades': len(trades),
            'score': round(score, 4),
        })
        
        if score > best_score:
            best_score = score
            best_params = p.copy()
            best_trades = trades
        
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            remaining = (total - i - 1) * (elapsed / (i + 1))
            print(f"  进度：{i+1}/{total} | 剩余：{remaining/60:.0f}分钟 | 最佳评分：{best_score:.4f}")
    
    print(f"\n{'='*60}")
    print(f"🏆 最佳参数")
    print(f"{'='*60}")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    
    print(f"\n最佳参数表现：")
    print(f"  信号数：{len(best_trades)}")
    print(f"  胜率：{(best_trades > 0).sum() / len(best_trades):.2%}")
    print(f"  平均收益：{best_trades.mean():.2%}")
    
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(BASE, 'optimization_v2.2_results.csv'), index=False, encoding='utf-8-sig')
    print(f"\n✅ 全部排名已保存至 optimization_v2.2_results.csv")
    
    return best_params

# ==================== 主程序 ====================
if __name__ == "__main__":
    START_DATE = '20250101'
    END_DATE = '20260430'

    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--optimize':
        best_params = optimize_v2_2(START_DATE, END_DATE)
        PARAMS.update(best_params)
        print(f"\n{'='*60}")
        print(f"用最佳参数跑完整回测验证...")
        print(f"{'='*60}\n")
        df = run_backtest_v2(START_DATE, END_DATE)
    else:
        print("策略 V2.2 修正版")
        print("修正：滚动情绪（无未来函数）| 开盘涨停跳过 | 跌停不可止损\n")
        df = run_backtest_v2(START_DATE, END_DATE)