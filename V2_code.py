"""
A股连板回调策略 V2.0 - 回测 + 参数优化
分层架构：市场情绪 → 龙头识别 → 低吸时机
修正：次日开盘价成交、ATR动态止盈止损、区分涨跌停板
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import os
import warnings
from itertools import product

warnings.filterwarnings('ignore')

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "stock_data")
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== 默认参数 ====================
PARAMS = {
    # ---- 市场情绪 ----
    "min_daily_limit_up": 40,
    "min_highest_board": 3,
    
    # ---- 龙头识别 ----
    "require_highest_board": True,
    "min_consecutive_limit_up": 2,
    "min_entity_board_ratio": 0.5,
    
    # ---- 回调条件 ----
    "pullback_ratio_min": 0.08,
    "pullback_ratio_max": 0.25,
    "min_pullback_days": 2,
    
    # ---- 反弹确认 ----
    "require_weak_to_strong": True,
    "min_pct_today": 2.0,
    
    # ---- 均线和量能 ----
    "ma_stabilize": 10,
    "volume_shrink_ratio": 0.4,
    
    # ---- 动态止盈止损 ----
    "atr_period": 14,
    "stop_loss_atr_mult": 0.8,
    "take_profit_atr_mult": 2.5,
    "max_hold_days": 7,
}

# ==================== 涨停判断 ====================
def get_limit_threshold(code):
    """获取涨停阈值"""
    if code.startswith('300') or code.startswith('301') or code.startswith('688'):
        return 19.5
    elif code.startswith('8') or code.startswith('4'):
        return 29.5
    else:
        return 9.5

# ==================== 从本地缓存读取 ====================
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

# ==================== 核心回测函数 ====================
def run_backtest_v2(start_date, end_date):
    """
    V2回测：遍历本地缓存，找连板龙头回调信号，模拟交易
    修正：次日开盘价成交
    """
    print("=" * 60)
    print("策略V2 回测")
    print("=" * 60)
    print(f"区间：{start_date} ~ {end_date}")
    print(f"连板≥{PARAMS['min_consecutive_limit_up']} | "
          f"回调{PARAMS['pullback_ratio_min']:.0%}-{PARAMS['pullback_ratio_max']:.0%} | "
          f"缩量≤{PARAMS['volume_shrink_ratio']:.0%} | "
          f"弱转强 | ATR动态止盈止损\n")
    
    cache_files = [f for f in os.listdir(DATA_DIR) 
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    
    start_dt = datetime.strptime(start_date, '%Y%m%d')
    end_dt = datetime.strptime(end_date, '%Y%m%d')
    
    all_trades = []
    
    print(f"扫描 {len(cache_files)} 只股票...")
    start_time = time.time()
    
    for idx, fname in enumerate(cache_files):
        code = fname.replace('.csv', '')
        
        if (idx + 1) % 500 == 0:
            elapsed = time.time() - start_time
            print(f"  进度：{idx+1}/{len(cache_files)} | 已发现交易：{len(all_trades)} | 耗时：{elapsed:.0f}秒")
        
        df = load_from_cache(code)
        if df is None or len(df) < 60:
            continue
        
        # 截取回测区间
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        if len(df) < 30:
            continue
        
        df = df.reset_index(drop=True)
        
        # 计算ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(PARAMS['atr_period']).mean()
        
        # 涨停标注
        limit_threshold = get_limit_threshold(code)
        df['is_limit_up'] = df['pct_chg'] >= limit_threshold
        df['is_one_word'] = (
            (df['open'] == df['high']) & 
            (df['low'] == df['close']) & 
            df['is_limit_up']
        )
        
        # 找连板序列
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
        
        # 对每个连板组检查回调
        for group in groups:
            if len(group) < PARAMS['min_consecutive_limit_up']:
                continue
            
            # 实体板比例
            entity_count = sum(1 for i in group if not df.iloc[i]['is_one_word'])
            if entity_count / len(group) < PARAMS['min_entity_board_ratio']:
                continue
            
            last_limit_idx = group[-1]
            highest_price = max(df.iloc[i]['high'] for i in group)
            
            # 连板期平均换手（用成交量近似）
            limit_avg_vol = np.mean([df.iloc[i]['volume'] for i in group])
            
            # 检查回调日
            for check_idx in range(last_limit_idx + PARAMS['min_pullback_days'] + 1, 
                                   min(last_limit_idx + 15, len(df) - 1)):  # -1 确保有次日数据
                
                current_row = df.iloc[check_idx]
                prev_row = df.iloc[check_idx - 1]
                current_price = current_row['close']
                
                # 回调幅度
                pullback_ratio = (highest_price - current_price) / highest_price
                if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
                    continue
                
                # 均线
                if check_idx >= PARAMS['ma_stabilize']:
                    ma = df.iloc[check_idx - PARAMS['ma_stabilize'] + 1:check_idx + 1]['close'].mean()
                    if current_price < ma:
                        continue
                
                # 量能萎缩
                pullback_vol = df.iloc[check_idx - 3:check_idx]['volume'].mean()
                if limit_avg_vol > 0 and pullback_vol / limit_avg_vol > PARAMS['volume_shrink_ratio']:
                    continue
                
                # 弱转强
                if PARAMS['require_weak_to_strong']:
                    if current_row['close'] <= prev_row['high']:
                        continue
                
                # 今日涨幅
                today_pct = (current_row['close'] / prev_row['close'] - 1) * 100
                if today_pct < PARAMS['min_pct_today']:
                    continue
                
                # 阳线
                if current_row['close'] <= current_row['open']:
                    continue
                
                # ===== 模拟交易（次日开盘价成交）=====
                next_idx = check_idx + 1
                if next_idx >= len(df):
                    continue
                
                entry_price = df.iloc[next_idx]['open']  # 次日开盘价
                atr_val = df.iloc[check_idx]['atr']
                if pd.isna(atr_val) or atr_val <= 0:
                    atr_val = current_price * 0.03
                
                # 动态止盈止损
                stop_loss_price = entry_price - PARAMS['stop_loss_atr_mult'] * atr_val
                take_profit_price = entry_price + PARAMS['take_profit_atr_mult'] * atr_val
                
                # 模拟持仓
                ret = 0
                exit_reason = '到期'
                days_held = PARAMS['max_hold_days']
                
                for hold_day in range(1, PARAMS['max_hold_days'] + 1):
                    hold_idx = next_idx + hold_day
                    if hold_idx >= len(df):
                        days_held = hold_day
                        ret = df.iloc[-1]['close'] / entry_price - 1
                        exit_reason = '到期'
                        break
                    
                    bar = df.iloc[hold_idx]
                    
                    # 止损止盈
                    if bar['low'] <= stop_loss_price:
                        ret = stop_loss_price / entry_price - 1
                        days_held = hold_day
                        exit_reason = '止损'
                        break
                    if bar['high'] >= take_profit_price:
                        ret = take_profit_price / entry_price - 1
                        days_held = hold_day
                        exit_reason = '止盈'
                        break
                else:
                    ret = df.iloc[next_idx + PARAMS['max_hold_days']]['close'] / entry_price - 1
                
                all_trades.append({
                    'code': code,
                    'entry_date': df.iloc[next_idx]['trade_date'],
                    'entry_price': round(entry_price, 2),
                    'exit_reason': exit_reason,
                    'return': round(ret, 4),
                    'hold_days': days_held,
                    'pullback_ratio': round(pullback_ratio, 3),
                    'board_height': len(group),
                    'highest_price': round(highest_price, 2),
                })
    
    # ---- 报告 ----
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"回测完成！耗时 {elapsed:.0f}秒")
    print(f"{'='*60}")
    
    if len(all_trades) == 0:
        print("⚠️ 无交易信号")
        return None
    
    df = pd.DataFrame(all_trades)
    
    win_count = (df['return'] > 0).sum()
    loss_count = (df['return'] <= 0).sum()
    win_rate = win_count / len(df)
    
    avg_ret = df['return'].mean()
    avg_win = df[df['return'] > 0]['return'].mean()
    avg_loss = df[df['return'] <= 0]['return'].mean()
    total_ret = (1 + df['return']).prod() - 1
    
    print(f"\n【核心指标】")
    print(f"  交易次数：{len(df)}")
    print(f"  胜率：{win_rate:.2%}")
    print(f"  平均收益：{avg_ret:.2%}")
    print(f"  平均盈利：{avg_win:.2%} | 平均亏损：{avg_loss:.2%}")
    print(f"  盈亏比：{abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "  盈亏比：N/A")
    print(f"  总收益：{total_ret:.2%}")
    print(f"  最大盈利：{df['return'].max():.2%} | 最大亏损：{df['return'].min():.2%}")
    
    print(f"\n【退出原因】")
    for reason, count in df['exit_reason'].value_counts().items():
        print(f"  {reason}：{count}次 ({count/len(df)*100:.1f}%)")
    
    df.to_csv(os.path.join(BASE, f'backtest_v2_{start_date}_{end_date}.csv'), index=False, encoding='utf-8-sig')
    print(f"\n✅ 结果已保存至 backtest_v2_{start_date}_{end_date}.csv")
    
    return df

## ==================== 预提取事件 ====================
def extract_all_events_v2(start_date, end_date):
    """预提取所有连板→回调事件（只跑一次）"""
    print("预提取连板事件（只跑一次）...")
    
    cache_files = [f for f in os.listdir(DATA_DIR) 
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    
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
        
        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(14).mean()
        
        # 涨停标注
        limit_threshold = get_limit_threshold(code)
        df['is_limit_up'] = df['pct_chg'] >= limit_threshold
        df['is_one_word'] = (
            (df['open'] == df['high']) & 
            (df['low'] == df['close']) & 
            df['is_limit_up']
        )
        
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
                
                pullback_ratio = (highest_price - current_price) / highest_price
                pullback_vol = df.iloc[max(0, check_idx-3):check_idx]['volume'].mean()
                vol_shrink = pullback_vol / limit_avg_vol if limit_avg_vol > 0 else 1
                
                # 均线
                ma_val = df.iloc[max(0, check_idx-9):check_idx+1]['close'].mean() if check_idx >= 9 else current_price
                
                # 弱转强
                is_weak_to_strong = current_row['close'] > prev_row['high']
                today_pct = (current_row['close'] / prev_row['close'] - 1) * 100
                is_yang = current_row['close'] > current_row['open']
                
                # 次日开盘价
                next_idx = check_idx + 1
                if next_idx >= len(df):
                    continue
                next_open = df.iloc[next_idx]['open']
                
                atr_val = df.iloc[check_idx]['atr']
                if pd.isna(atr_val) or atr_val <= 0:
                    atr_val = current_price * 0.03
                
                # 未来N天数据（最多10天）
                future = []
                for fwd in range(1, 11):
                    fwd_idx = next_idx + fwd
                    if fwd_idx >= len(df):
                        break
                    future.append({
                        'open': df.iloc[fwd_idx]['open'],
                        'high': df.iloc[fwd_idx]['high'],
                        'low': df.iloc[fwd_idx]['low'],
                        'close': df.iloc[fwd_idx]['close'],
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
                    'future': future,
                })
    
    print(f"✅ 预提取完成：{len(all_events)} 个事件")
    return all_events

# ==================== 快速参数优化 ====================
def optimize_v2(start_date, end_date):
    """基于预提取事件的快速参数优化"""
    print("=" * 60)
    print("策略V2 参数优化（极速版）")
    print("=" * 60)
    
    # 第一步：预提取事件
    print("\n第一步：预提取连板→回调事件...")
    all_events = extract_all_events_v2(start_date, end_date)
    
    # 第二步：参数网格
    param_grid = {
        "min_consecutive_limit_up": [2, 3],
        "min_entity_board_ratio": [0.3, 0.5],
        "pullback_ratio_min": [0.05, 0.08, 0.10],
        "pullback_ratio_max": [0.20, 0.25, 0.30],
        "volume_shrink_ratio": [0.4, 0.5, 0.6],
        "min_pct_today": [1.0, 2.0, 3.0],
        "stop_loss_atr_mult": [0.5, 0.8, 1.0],
        "take_profit_atr_mult": [1.5, 2.0, 2.5],
        "max_hold_days": [5, 7, 10],
    }
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combos = list(product(*values))
    
    total = len(all_combos)
    print(f"\n第二步：遍历 {total} 组参数（在 {len(all_events)} 个事件上筛选）...")
    print(f"预计耗时：1-2分钟\n")
    
    results_list = []
    best_score = -999
    best_params = None
    
    start_time = time.time()
    
    for i, combo in enumerate(all_combos):
        p = dict(zip(keys, combo))
        
        trades = []
        
        for evt in all_events:
            # 连板条件
            if evt['board_height'] < p['min_consecutive_limit_up']:
                continue
            if evt['entity_ratio'] < p['min_entity_board_ratio']:
                continue
            # 回调
            if evt['pullback_ratio'] < p['pullback_ratio_min'] or evt['pullback_ratio'] > p['pullback_ratio_max']:
                continue
            # 量能
            if evt['vol_shrink'] > p['volume_shrink_ratio']:
                continue
            # 均线
            if evt['current_price'] < evt['ma']:
                continue
            # 弱转强
            if not evt['is_weak_to_strong']:
                continue
            # 涨幅
            if evt['today_pct'] < p['min_pct_today']:
                continue
            # 阳线
            if not evt['is_yang']:
                continue
            
            # 模拟交易
            entry_price = evt['next_open']
            atr_val = evt['atr']
            
            stop_loss = entry_price - p['stop_loss_atr_mult'] * atr_val
            take_profit = entry_price + p['take_profit_atr_mult'] * atr_val
            
            ret = 0
            days_held = p['max_hold_days']
            exit_reason = '到期'
            
            for fwd_idx, bar in enumerate(evt['future']):
                if fwd_idx >= p['max_hold_days']:
                    break
                if bar['low'] <= stop_loss:
                    ret = stop_loss / entry_price - 1
                    exit_reason = '止损'
                    days_held = fwd_idx + 1
                    break
                if bar['high'] >= take_profit:
                    ret = take_profit / entry_price - 1
                    exit_reason = '止盈'
                    days_held = fwd_idx + 1
                    break
            else:
                if len(evt['future']) >= p['max_hold_days']:
                    ret = evt['future'][p['max_hold_days']-1]['close'] / entry_price - 1
                elif len(evt['future']) > 0:
                    ret = evt['future'][-1]['close'] / entry_price - 1
            
            trades.append({'return': ret, 'exit_reason': exit_reason})
        
        if len(trades) == 0:
            continue
        
        df_t = pd.DataFrame(trades)
        win_rate = (df_t['return'] > 0).sum() / len(df_t)
        avg_ret = df_t['return'].mean()
        total_ret = (1 + df_t['return']).prod() - 1
        
        # 评分：总收益50% + 胜率30% + 交易数20%
        score = total_ret * 0.5 + win_rate * 0.3 + min(len(df_t)/100, 1) * 0.2
        
        results_list.append({
            **p,
            'win_rate': round(win_rate, 4),
            'avg_return': round(avg_ret, 4),
            'total_return': round(total_ret, 4),
            'trades': len(df_t),
            'score': round(score, 4),
        })
        
        if score > best_score:
            best_score = score
            best_params = p.copy()
        
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            remaining = (total - i - 1) * (elapsed / (i + 1))
            print(f"  进度：{i+1}/{total} | 剩余：{remaining/60:.0f}分钟 | 最佳：{best_score:.4f}")
    
    print(f"\n{'='*60}")
    print(f"🏆 最佳参数")
    print(f"{'='*60}")
    for k, v in best_params.items():
        print(f"  {k}: {v}")
    
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(BASE, 'optimization_v2_results.csv'), index=False, encoding='utf-8-sig')
    print(f"\n✅ 已保存至 optimization_v2_results.csv")
    print(f"\n前10名：")
    print(df_results.head(10).to_string())
    
    return best_params

# ==================== 主入口 ====================
if __name__ == "__main__":
    import sys
    
    START_DATE = '20250101'
    END_DATE = '20260430'
    
    if len(sys.argv) > 1 and sys.argv[1] == '--optimize':
        optimize_v2(START_DATE, END_DATE)
    else:
        df = run_backtest_v2(START_DATE, END_DATE)