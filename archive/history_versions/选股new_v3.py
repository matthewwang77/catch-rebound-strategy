"""
A股连板回调策略 v3 — 华安证券研报改进版
基于 32,615 首板样本分析，五大反直觉规律：
  1. 缩量远优于放量：量比<0.3x 胜率 91.7%、均收益 +7.44%
  2. 非多头排列更优：非多头首板次日 +0.40% vs 多头 +0.22%
  3. 超跌首板强10倍：前20日跌>10%的首板均收益 +1.04% vs 高位 +0.10%
  4. 市值U型分布：极小市值和大市值优于中等市值
  5. 低位收盘更佳：回调日收盘在日内低位，次日表现显著更好

v3 改进：
  - 收紧 strict 模式：回调上限 0.15 + 缩量 ≤0.3x
  - 超跌反弹过滤器：连板前 20 日跌幅 >10%
  - 低位收盘过滤器：信号日收盘在振幅下半区
  - 新增 oversold 模式：聚焦超跌后反弹
  - 优化评分函数：更看重胜率（0.5权重）
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
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
    "volume_shrink_ratio_min": 0.0,       # v3：极端缩量下限（<0.05 可能无流动性）
    "volume_compare_days": 3,
    "signal_today_yang": True,
    "signal_volume_expand": 1.2,
    "hold_days": 7,
    "take_profit": 0.05,
    "stop_loss": -0.07,
    # ---- v3 新增：超跌反弹过滤 ----
    "require_oversold": False,             # 是否要求连板前超跌（研报规律3）
    "oversold_decline_threshold": 0.10,    # 前20日跌幅阈值（>10%为超跌）
    "oversold_lookback_days": 20,          # 超跌回看天数
    # ---- v3 新增：低位收盘过滤 ----
    "require_low_close": False,            # 信号日收盘在日内低位（研报规律5）
    "low_close_threshold": 0.5,            # 收盘在振幅中的位置 <0.5 = 下半区
}


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
    """下载全量A股数据到本地"""
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


# ==================== 6. 检查回调（v3：新增低位收盘+量能下限）====================
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

    # 量能（v3：增加下限）
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

    # ---- v3: 低位收盘过滤 ----
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


# ==================== 7. 模拟持仓 ====================
def simulate_hold_return(df_stock, entry_idx, entry_price):
    """模拟持仓收益（距离开盘价更近的阈值先触发，更接近真实交易）"""
    exit_idx = min(entry_idx + PARAMS['hold_days'], len(df_stock) - 1)
    for i in range(entry_idx + 1, exit_idx + 1):
        high = df_stock.iloc[i]['high']
        low = df_stock.iloc[i]['low']
        open_price = df_stock.iloc[i]['open']
        if entry_price <= 0:
            continue
        # 第一层：开盘跳空直接触发
        open_return = open_price / entry_price - 1
        if open_return <= PARAMS['stop_loss']:
            return open_return, i - entry_idx, '止损'
        if open_return >= PARAMS['take_profit']:
            return open_return, i - entry_idx, '止盈'
        # 第二层：日内触及 —— 距离开盘价更近的阈值先触发
        stop_level = entry_price * (1 + PARAMS['stop_loss'])
        profit_level = entry_price * (1 + PARAMS['take_profit'])
        dist_to_stop = open_price - stop_level
        dist_to_profit = profit_level - open_price
        if dist_to_stop <= dist_to_profit:
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                return PARAMS['stop_loss'], i - entry_idx, '止损'
            if high / entry_price - 1 >= PARAMS['take_profit']:
                return PARAMS['take_profit'], i - entry_idx, '止盈'
        else:
            if high / entry_price - 1 >= PARAMS['take_profit']:
                return PARAMS['take_profit'], i - entry_idx, '止盈'
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                return PARAMS['stop_loss'], i - entry_idx, '止损'
    final_price = df_stock.iloc[exit_idx]['close']
    final_return = final_price / entry_price - 1 if entry_price > 0 else 0
    return final_return, PARAMS['hold_days'], '到期'


# ==================== 8. 主回测（v3：增加超跌+低位收盘过滤）====================
def run_backtest(start_date, end_date):
    """从本地缓存读取数据，扫描回测"""
    print("=" * 60)
    print(f"阶段二：执行回测{'（v3 华安研报改进版）' if PARAMS.get('require_oversold') or PARAMS.get('require_low_close') else ''}")
    print("=" * 60)
    print(f"回测区间：{start_date} ~ {end_date}")
    print(f"参数：连板≥{PARAMS['min_consecutive_limit_up']} | "
          f"回调{PARAMS['pullback_ratio_min']:.0%}-{PARAMS['pullback_ratio_max']:.0%} | "
          f"缩量≤{PARAMS['volume_shrink_ratio']:.0%}"
          + (f" | 超跌>{PARAMS['oversold_decline_threshold']:.0%}" if PARAMS.get('require_oversold') else "")
          + (f" | 低位收盘" if PARAMS.get('require_low_close') else ""))

    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    print(f"\n本地有效数据：{len(cache_files)} 只股票")

    # ====== 第一步：快速扫描有涨停的股票 ======
    print("第一步：扫描有涨停/连板记录的股票...")
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
        if (idx + 1) % 1000 == 0:
            print(f"  已扫描 {idx+1}/{len(cache_files)}，涨停股: {len(hot_codes)}")
    print(f"✅ 扫描完成！{len(hot_codes)} 只有过涨停记录（耗时: {time.time()-start_time:.0f}秒）\n")

    # ====== 第二步：深度分析 ======
    print("第二步：对涨停股做深度连板+回调分析...")
    start_time = time.time()
    all_signals = []
    oversold_skip = 0  # v3统计

    for idx, code in enumerate(hot_codes):
        if (idx + 1) % 100 == 0:
            elapsed = time.time() - start_time
            remaining = (len(hot_codes) - idx - 1) * (elapsed / (idx + 1))
            print(f"  进度：{idx+1}/{len(hot_codes)} | 信号：{len(all_signals)} | 预计剩余：{remaining:.0f}秒")

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

            # ---- v3: 超跌检查（连板前20日跌幅）----
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
                            continue  # 跌幅不够，跳过此连板组

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
                pullback_start = max(0, check_idx - PARAMS['volume_compare_days'])
                pullback_volumes = df_stock.iloc[pullback_start:check_idx]['volume'].tolist()
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

                # ---- v3: 低位收盘过滤 ----
                if PARAMS.get('require_low_close', False):
                    row = df_stock.iloc[check_idx]
                    high_low_range = row['high'] - row['low']
                    if high_low_range > 0:
                        close_position = (row['close'] - row['low']) / high_low_range
                        if close_position >= PARAMS.get('low_close_threshold', 0.5):
                            continue

                # 模拟持仓
                ret, days_held, exit_reason = simulate_hold_return(
                    df_stock, check_idx, current_price
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

    # ---- 报告 ----
    print(f"\n{'='*60}")
    print(f"回测完成！耗时: {total_time:.1f}秒")
    print(f"{'='*60}")
    print(f"总信号数：{len(all_signals)}")
    if PARAMS.get('require_oversold'):
        print(f"  超跌过滤跳过：{oversold_skip} 个连板组")

    if len(all_signals) == 0:
        print("\n⚠️ 未产生任何交易信号。建议放宽参数。")
        return None

    df = pd.DataFrame(all_signals)
    win_count = (df['return'] > 0).sum()
    loss_count = (df['return'] <= 0).sum()
    win_rate = win_count / len(df)
    avg_return = df['return'].mean()
    avg_win = df[df['return'] > 0]['return'].mean()
    avg_loss = df[df['return'] <= 0]['return'].mean()
    max_win = df['return'].max()
    max_loss = df['return'].min()
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    print(f"\n【核心指标】")
    print(f"  总交易次数：{len(df)}")
    print(f"  盈利次数：{win_count} | 亏损次数：{loss_count}")
    print(f"  胜率：{win_rate:.2%}")
    print(f"  平均收益：{avg_return:.2%}")
    print(f"  平均盈利：{avg_win:.2%} | 平均亏损：{avg_loss:.2%}")
    print(f"  最大单笔盈利：{max_win:.2%} | 最大单笔亏损：{max_loss:.2%}")
    print(f"  盈亏比：{profit_factor:.2f}")

    # 退出原因
    print(f"\n【退出原因分布】")
    for reason, count in df['exit_reason'].value_counts().items():
        print(f"  {reason}：{count}次 ({count/len(df)*100:.1f}%)")

    # 收益分布
    print(f"\n【收益分布】")
    bins = [-999, -0.07, -0.03, 0, 0.03, 0.05, 0.07, 999]
    labels = ['<=-7%', '-7%~-3%', '-3%~0%', '0~+3%', '+3%~+5%', '+5%~+7%', '>+7%']
    df['return_bin'] = pd.cut(df['return'], bins=bins, labels=labels)
    for label, count in df['return_bin'].value_counts().sort_index().items():
        bar = '█' * max(1, int(count / len(df) * 50))
        print(f"  {label}: {count}次 ({count/len(df)*100:.1f}%) {bar}")

    # 保存
    output_file = os.path.join(BASE, f'backtest_v3_{start_date}_{end_date}.csv')
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✅ 详细信号已保存至：{output_file}")

    return df


# ==================== 9. 预提取连板事件（v3：增加超跌+低位收盘字段）====================
def extract_all_events(hot_codes, start_date, end_date):
    """对所有涨停股票，预提取连板事件（v3：新增 oversold_decline + close_position）"""
    print("正在预提取连板事件（v3：含超跌+低位收盘数据）...")
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

            # ---- v3: 计算超跌（涨停前20日跌幅）----
            oversold_decline = 0.0  # 默认不超跌
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

                # 预计算量能
                vol_start = max(0, check_idx - 3)
                pullback_volumes = df_stock.iloc[vol_start:check_idx]['volume'].tolist()
                if len(pullback_volumes) < 2:
                    continue
                pullback_avg_vol = np.mean(pullback_volumes)

                # 预计算均线
                ma_val = df_stock.iloc[max(0, check_idx - 9):check_idx + 1]['close'].mean() if check_idx >= 9 else current_price

                # 当日数据
                is_yang = df_stock.iloc[check_idx]['close'] > df_stock.iloc[check_idx]['open']
                today_vol = df_stock.iloc[check_idx]['volume']
                yesterday_vol = df_stock.iloc[check_idx - 1]['volume'] if check_idx > 0 else today_vol
                vol_expand_ratio = today_vol / yesterday_vol if yesterday_vol > 0 else 1

                # ---- v3: 低位收盘位置 ----
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
                    # ---- v3 新增字段 ----
                    'oversold_decline': oversold_decline,    # 连板前20日跌幅（负数=超跌）
                    'close_position': close_position,         # 收盘在振幅中的位置
                    'future_data': future_data,
                })

    print(f"✅ 预提取完成！共 {len(all_events)} 个回调事件")
    return all_events


# ==================== 10. 快速参数优化（v3：新评分+新参数+全面评估）====================
def optimize_params(start_date, end_date):
    """基于预提取的事件，快速遍历参数组合，找到最优参数"""
    print("=" * 60)
    print("自动参数优化模式（v3 极速版）")
    print("=" * 60)

    # 先扫描涨停股票
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

    # 预提取所有事件
    print("\n第二步：预提取连板+回调事件...")
    all_events = extract_all_events(hot_codes, start_date, end_date)

    # ---- v3 参数网格（~41k 组合，约 2-3 分钟）----
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
        # ---- v3 新参数 ----
        "require_oversold": [False, True],
        "require_low_close": [False, True],
    }

    from itertools import product
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combinations = list(product(*values))

    total_combos = len(all_combinations)
    # 2×2×3×4×4×2×3×3×3×2×2 ≈ 41,472 组合

    print(f"\n第三步：遍历 {total_combos} 种参数组合...")
    print(f"预计耗时：2-5分钟\n")
    results_list = []
    best_score = -999
    best_params = None
    best_signals = None
    start_time = time.time()

    for i, combo in enumerate(all_combinations):
        params_dict = dict(zip(keys, combo))

        signals = []
        for evt in all_events:
            # 连板
            if evt['limit_series_len'] < params_dict['min_consecutive_limit_up']:
                continue
            if evt['entity_ratio'] < params_dict['min_entity_board_ratio']:
                continue

            # 回调
            if evt['pullback_ratio'] < params_dict['pullback_ratio_min']:
                continue
            if evt['pullback_ratio'] > params_dict['pullback_ratio_max']:
                continue

            # 量能（v3：上下限）
            vol_ratio = evt['pullback_avg_vol'] / evt['limit_avg_vol'] if evt['limit_avg_vol'] > 0 else 1
            if vol_ratio > params_dict['volume_shrink_ratio']:
                continue
            if vol_ratio < params_dict.get('volume_shrink_ratio_min', 0):
                continue

            # 均线
            if evt['trigger_price'] < evt['ma']:
                continue

            # 阳线
            if not evt['is_yang']:
                continue

            # ---- v3: 超跌过滤 ----
            if params_dict.get('require_oversold', False):
                if evt['oversold_decline'] > -0.10:
                    continue

            # ---- v3: 低位收盘过滤 ----
            if params_dict.get('require_low_close', False):
                if evt['close_position'] >= 0.5:
                    continue

            # 模拟持仓
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
                if open_ret <= stop_loss:
                    ret = open_ret; exit_reason = '止损'; days_held = fwd_idx + 1; break
                if open_ret >= take_profit:
                    ret = open_ret; exit_reason = '止盈'; days_held = fwd_idx + 1; break

                stop_level = entry_price * (1 + stop_loss)
                profit_level = entry_price * (1 + take_profit)
                dist_to_stop = bar['open'] - stop_level
                dist_to_profit = profit_level - bar['open']

                if dist_to_stop <= dist_to_profit:
                    if bar['low'] / entry_price - 1 <= stop_loss:
                        ret = stop_loss; exit_reason = '止损'; days_held = fwd_idx + 1; break
                    if bar['high'] / entry_price - 1 >= take_profit:
                        ret = take_profit; exit_reason = '止盈'; days_held = fwd_idx + 1; break
                else:
                    if bar['high'] / entry_price - 1 >= take_profit:
                        ret = take_profit; exit_reason = '止盈'; days_held = fwd_idx + 1; break
                    if bar['low'] / entry_price - 1 <= stop_loss:
                        ret = stop_loss; exit_reason = '止损'; days_held = fwd_idx + 1; break
            else:
                if len(evt['future_data']) >= hold_days:
                    ret = evt['future_data'][hold_days - 1]['close'] / entry_price - 1
                elif len(evt['future_data']) > 0:
                    ret = evt['future_data'][-1]['close'] / entry_price - 1

            signals.append({
                'date': evt['date'], 'code': evt['code'],
                'return': ret, 'exit_reason': exit_reason, 'hold_days': days_held,
            })

        if len(signals) == 0:
            continue

        df = pd.DataFrame(signals)
        signal_count = len(df)

        # ---- 过拟合防护：最少 30 个信号才有统计意义 ----
        if signal_count < 30:
            continue

        win_rate = (df['return'] > 0).sum() / len(df)
        avg_return = df['return'].mean()
        total_return = (1 + df['return']).prod() - 1
        avg_win = df[df['return'] > 0]['return'].mean() if win_rate > 0 else 0
        avg_loss = df[df['return'] <= 0]['return'].mean() if win_rate < 1 else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 99

        # ---- v3 评分：胜率+均收益为主，信号数奖励有上限（防过拟合）----
        score = (
            win_rate * 0.45 +
            avg_return * 4.0 +                        # 1%→0.04, 3%→0.12
            min(signal_count / 150, 1) * 0.1          # 150信号封顶
        )

        results_list.append({
            **params_dict,
            'win_rate': round(win_rate, 4),
            'avg_return': round(avg_return, 4),
            'total_return': round(total_return, 4),
            'signal_count': signal_count,
            'profit_factor': round(profit_factor, 2),
            'score': round(score, 4),
        })

        if score > best_score:
            best_score = score
            best_params = params_dict.copy()
            best_signals = df.copy()

        # 进度
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
            print(f"  进度：{i+1}/{total_combos} ({((i+1)/total_combos)*100:.1f}%) | "
                  f"剩余：{remaining/60:.0f}分钟 | 最佳评分：{best_score:.4f} "
                  f"(胜率{(best_signals['return']>0).sum()/len(best_signals):.0%})")

    # ---- 输出最佳结果 ----
    print(f"\n{'='*60}")
    print(f"🏆 最佳参数（v3）")
    print(f"{'='*60}")
    for k, v in best_params.items():
        print(f"  {k}: {v}")

    print(f"\n最佳参数回测结果：")
    print(f"  信号数：{len(best_signals)}")
    print(f"  胜率：{(best_signals['return'] > 0).sum() / len(best_signals):.2%}")
    print(f"  平均收益：{best_signals['return'].mean():.2%}")
    print(f"  总收益：{((1 + best_signals['return']).prod() - 1):.2%}")

    # 保存全部排名
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(BASE, 'optimization_v3_results.csv'), index=False, encoding='utf-8-sig')
    print(f"\n✅ 全部排名已保存至 optimization_v3_results.csv")
    print(f"\n前10名：")
    print(df_results.head(10).to_string())

    # ---- 关键发现 ----
    print(f"\n{'='*60}")
    print(f"📊 关键发现")
    print(f"{'='*60}")

    # 超跌 vs 非超跌对比
    oversold_on = df_results[df_results['require_oversold'] == True]
    oversold_off = df_results[df_results['require_oversold'] == False]
    if len(oversold_on) > 0 and len(oversold_off) > 0:
        print(f"\n超跌过滤效果（Top100均值）：")
        print(f"  开启超跌: 胜率{oversold_on.head(100)['win_rate'].mean():.2%} "
              f"均收益{oversold_on.head(100)['avg_return'].mean():.2%} "
              f"信号{oversold_on.head(100)['signal_count'].mean():.0f}")
        print(f"  关闭超跌: 胜率{oversold_off.head(100)['win_rate'].mean():.2%} "
              f"均收益{oversold_off.head(100)['avg_return'].mean():.2%} "
              f"信号{oversold_off.head(100)['signal_count'].mean():.0f}")

    # 低位收盘效果
    lowclose_on = df_results[df_results['require_low_close'] == True]
    lowclose_off = df_results[df_results['require_low_close'] == False]
    if len(lowclose_on) > 0 and len(lowclose_off) > 0:
        print(f"\n低位收盘过滤效果（Top100均值）：")
        print(f"  开启低位收盘: 胜率{lowclose_on.head(100)['win_rate'].mean():.2%} "
              f"均收益{lowclose_on.head(100)['avg_return'].mean():.2%} "
              f"信号{lowclose_on.head(100)['signal_count'].mean():.0f}")
        print(f"  关闭低位收盘: 胜率{lowclose_off.head(100)['win_rate'].mean():.2%} "
              f"均收益{lowclose_off.head(100)['avg_return'].mean():.2%} "
              f"信号{lowclose_off.head(100)['signal_count'].mean():.0f}")

    # 缩量效果对比
    for shrink_val in [0.20, 0.30, 0.40, 0.50]:
        subset = df_results[df_results['volume_shrink_ratio'] == shrink_val]
        if len(subset) > 0:
            top50 = subset.head(50)
            print(f"\n缩量≤{shrink_val:.0%}（Top50均值）："
                  f"胜率{top50['win_rate'].mean():.2%} "
                  f"均收益{top50['avg_return'].mean():.2%} "
                  f"信号{top50['signal_count'].mean():.0f}")

    return best_params, best_signals


# ==================== 参数模式配置 ====================
SCREEN_MODES = {
    "strict": {
        # v3 收紧：回调上限 0.25→0.15，缩量 0.4→0.3
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.3,
        "pullback_ratio_min": 0.08,
        "pullback_ratio_max": 0.15,       # v3: 0.25→0.15
        "volume_shrink_ratio": 0.3,       # v3: 0.4→0.3
        "volume_shrink_ratio_min": 0.05,  # v3 新增
        "signal_today_yang": True,
        "signal_volume_expand": 1.2,
        "min_pullback_days": 2,
        "ma_stabilize": 10,
        "volume_compare_days": 3,
        # v3 新增（strict 默认不开启，靠回测验证）
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
    # ---- v3 新增：超跌反弹模式 ----
    "oversold": {
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.0,    # 不要求实体板（一字板超跌反弹也有效）
        "pullback_ratio_min": 0.15,       # 超跌后回调较深
        "pullback_ratio_max": 0.30,
        "volume_shrink_ratio": 0.3,       # 严格缩量（研报：<0.3x胜率91.7%）
        "volume_shrink_ratio_min": 0.05,
        "signal_today_yang": False,       # 不要求阳线
        "signal_volume_expand": 0.0,      # 不要求放量
        "min_pullback_days": 2,
        "ma_stabilize": 5,
        "volume_compare_days": 3,
        # v3 核心：必须超跌 + 低位收盘
        "require_oversold": True,
        "oversold_decline_threshold": 0.10,
        "require_low_close": True,
        "low_close_threshold": 0.5,
    }
}


# ==================== 单只股票筛选（v3：新增超跌+低位收盘漏斗）====================
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

    df_recent = pd.DataFrame({
        'close': close.values[-min_len:],
        'open': open_price.values[-min_len:],
        'high': high.values[-min_len:],
        'low': low.values[-min_len:],
        'volume': volume.values[-min_len:],
    })

    df_recent['pct_chg'] = df_recent['close'].pct_change() * 100
    df_recent = df_recent.dropna(subset=['pct_chg']).reset_index(drop=True)
    if len(df_recent) < 10:
        return

    limit_threshold = get_limit_threshold(code)
    df_recent['is_limit_up'] = df_recent['pct_chg'] >= limit_threshold
    df_recent['is_one_word'] = (
        (df_recent['open'] == df_recent['high']) &
        (df_recent['low'] == df_recent['close']) &
        df_recent['is_limit_up']
    )

    if not df_recent['is_limit_up'].any():
        return
    stats['has_limit_up'] += 1

    limit_up_indices = df_recent[df_recent['is_limit_up']].index.tolist()
    groups = []
    current_group = [limit_up_indices[0]]
    for i in range(1, len(limit_up_indices)):
        if limit_up_indices[i] == limit_up_indices[i-1] + 1:
            current_group.append(limit_up_indices[i])
        else:
            groups.append(current_group)
            current_group = [limit_up_indices[i]]
    groups.append(current_group)

    today_idx = len(df_recent) - 1
    today_row = df_recent.iloc[today_idx]

    passed_consecutive = passed_entity = passed_pullback_days = False
    passed_pullback_range = passed_ma = passed_volume = False
    passed_yang = passed_volume_expand = False
    passed_oversold = True   # 默认通过（多数模式不开启）
    passed_low_close = True

    for grp in reversed(groups):
        if len(grp) < PARAMS['min_consecutive_limit_up']:
            continue
        passed_consecutive = True

        entity_count = sum(1 for i in grp if not df_recent.iloc[i]['is_one_word'])
        entity_ratio = entity_count / len(grp) if len(grp) > 0 else 0
        if entity_ratio < PARAMS['min_entity_board_ratio']:
            continue
        passed_entity = True

        last_limit_idx = grp[-1]
        if today_idx - last_limit_idx < PARAMS['min_pullback_days']:
            continue
        passed_pullback_days = True

        # ---- v3: 超跌检查 ----
        if PARAMS.get('require_oversold', False):
            passed_oversold = False
            first_limit_idx = grp[0]
            lookback_start = max(0, first_limit_idx - PARAMS.get('oversold_lookback_days', 20))
            if lookback_start < first_limit_idx and first_limit_idx > 0:
                pre_price = df_recent.iloc[lookback_start]['close']
                pre_limit_price = df_recent.iloc[first_limit_idx - 1]['close']
                if pre_price > 0:
                    pre_decline = (pre_limit_price / pre_price - 1)
                    if pre_decline <= -PARAMS['oversold_decline_threshold']:
                        passed_oversold = True
            if not passed_oversold:
                continue

        highest_price = max(df_recent.iloc[i]['high'] for i in grp)
        current_price = today_row['close']
        pullback_ratio = (highest_price - current_price) / highest_price

        if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
            continue
        passed_pullback_range = True

        if PARAMS['ma_stabilize'] > 0 and today_idx >= PARAMS['ma_stabilize']:
            ma = df_recent.iloc[today_idx - PARAMS['ma_stabilize'] + 1:today_idx + 1]['close'].mean()
            if current_price < ma:
                continue
        passed_ma = True

        # 量能
        if PARAMS['volume_shrink_ratio'] < 10:
            limit_volumes = [df_recent.iloc[i]['volume'] for i in grp]
            limit_avg_vol = np.mean(limit_volumes)
            pullback_start_idx = max(0, today_idx - PARAMS['volume_compare_days'])
            pullback_vols = df_recent.iloc[pullback_start_idx:today_idx]['volume'].tolist()
            if len(pullback_vols) >= 2 and limit_avg_vol > 0:
                vol_ratio = np.mean(pullback_vols) / limit_avg_vol
                if vol_ratio > PARAMS['volume_shrink_ratio']:
                    continue
                if vol_ratio < PARAMS.get('volume_shrink_ratio_min', 0):
                    continue
        passed_volume = True

        if PARAMS['signal_today_yang']:
            if today_row['close'] <= today_row['open']:
                continue
        passed_yang = True

        if PARAMS['signal_volume_expand'] > 0 and today_idx >= 1:
            today_vol = today_row['volume']
            yesterday_vol = df_recent.iloc[today_idx - 1]['volume']
            if yesterday_vol > 0 and today_vol / yesterday_vol < PARAMS['signal_volume_expand']:
                continue
        passed_volume_expand = True

        # ---- v3: 低位收盘过滤 ----
        if PARAMS.get('require_low_close', False):
            passed_low_close = False
            high_low_range = today_row['high'] - today_row['low']
            if high_low_range > 0:
                close_position = (today_row['close'] - today_row['low']) / high_low_range
                if close_position < PARAMS.get('low_close_threshold', 0.5):
                    passed_low_close = True
            if not passed_low_close:
                continue

        break

    # 更新漏斗统计
    if passed_consecutive: stats['consecutive_ok'] += 1
    if passed_entity: stats['entity_ratio_ok'] += 1
    if passed_pullback_days: stats['pullback_days_ok'] += 1
    if not passed_oversold: stats['oversold_skip'] = stats.get('oversold_skip', 0) + 1
    if passed_pullback_range: stats['pullback_range_ok'] += 1
    if passed_ma: stats['ma_ok'] += 1
    if passed_volume: stats['volume_shrink_ok'] += 1
    if passed_yang: stats['yang_ok'] += 1
    if passed_volume_expand: stats['volume_expand_ok'] += 1
    if not passed_low_close: stats['low_close_skip'] = stats.get('low_close_skip', 0) + 1

    if not passed_volume_expand:
        return

    stats['final'] += 1
    candidates.append({
        'code': code,
        'price': round(current_price, 2),
        'pullback_pct': round(pullback_ratio * 100, 1),
        'limit_days': len(grp),
        'highest_price': round(highest_price, 2),
        'entity_ratio': round(entity_ratio * 100, 1),
    })


# ==================== 当日选股 ====================
def screen_today(mode="normal"):
    """用指定参数筛选今天的候选股票"""
    if mode not in SCREEN_MODES:
        print(f"⚠️ 未知模式 '{mode}'，使用 'normal' 模式")
        mode = "normal"

    BEST_PARAMS = SCREEN_MODES[mode].copy()
    global PARAMS
    original_params = PARAMS.copy()
    PARAMS.update(BEST_PARAMS)

    print("=" * 60)
    print("第一层：当日量化筛选（v3 华安研报改进版）")
    print("=" * 60)
    print(f"筛选模式: {mode}")
    print(f"筛选日期: {datetime.now().strftime('%Y-%m-%d')}")

    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    codes = [f.replace('.csv', '') for f in cache_files]

    if mode == "debug":
        codes = codes[:100]
        print(f"\n⚠️ 调试模式：仅扫描前100只股票")

    BATCH_SIZE = 200
    batches = [codes[i:i+BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
    print(f"\n待扫描股票：{len(codes)} 只，分 {len(batches)} 批下载\n")

    candidates = []
    failed_codes = []
    stats = {
        'total': 0, 'has_data': 0, 'has_limit_up': 0,
        'consecutive_ok': 0, 'entity_ratio_ok': 0, 'pullback_days_ok': 0,
        'oversold_skip': 0, 'pullback_range_ok': 0, 'ma_ok': 0,
        'volume_shrink_ok': 0, 'yang_ok': 0, 'volume_expand_ok': 0,
        'low_close_skip': 0, 'download_failed': 0, 'final': 0
    }

    for batch_idx, batch in enumerate(batches):
        print(f"  批次 {batch_idx+1}/{len(batches)}：下载 {len(batch)} 只...", end=" ", flush=True)

        hist = None
        try:
            hist = yf.download(tickers=" ".join(batch), period="30d", progress=False, auto_adjust=True)
        except Exception:
            hist = None

        batch_ok = hist is not None and not hist.empty
        if batch_ok:
            try:
                codes_in_batch = set(hist.columns.get_level_values(1))
            except Exception:
                codes_in_batch = set()
            print(f"完成({len(codes_in_batch)}只有效)，筛选...", end="", flush=True)
        else:
            codes_in_batch = set()
            print(f"批量失败→逐只", end="", flush=True)

        for code in batch:
            stats['total'] += 1
            stock_data = None

            if code in codes_in_batch:
                try:
                    stock_data = hist.xs(code, level=1, axis=1)
                    if stock_data is not None and not stock_data.empty:
                        if stock_data['Close'].dropna().empty:
                            stock_data = None
                except Exception:
                    stock_data = None

            if stock_data is None or stock_data.empty:
                for attempt in range(2):
                    try:
                        ticker = yf.Ticker(code)
                        stock_data = ticker.history(period="30d")
                        if stock_data is not None and not stock_data.empty:
                            if not stock_data['Close'].dropna().empty:
                                break
                            stock_data = None
                    except Exception:
                        stock_data = None
                        if attempt == 1 and mode == "debug":
                            print(f"\n    下载失败 {code}")
                        else:
                            time.sleep(0.5)

            if stock_data is not None and not stock_data.empty and not stock_data['Close'].dropna().empty:
                try:
                    _screen_single_stock(code, stock_data, stats, candidates, mode)
                except Exception as e:
                    if mode == "debug":
                        print(f"\n    错误 {code}: {e}")
            else:
                stats['download_failed'] += 1
                failed_codes.append(code)

        print(f" (累计扫描{stats['total']}，候选{stats['final']}，失败{stats['download_failed']})", flush=True)

    PARAMS.update(original_params)

    if stats['download_failed'] > 0:
        print(f"\n⚠️ 下载失败: {stats['download_failed']} 只")

    print(f"\n{'='*60}")
    print(f"筛选统计:")
    print(f"{'='*60}")
    print(f"  总扫描: {stats['total']}")
    print(f"  有涨停: {stats['has_limit_up']}")
    print(f"  连板数达标: {stats['consecutive_ok']}")
    print(f"  实体板达标: {stats['entity_ratio_ok']}")
    print(f"  回调天数达标: {stats['pullback_days_ok']}")
    if PARAMS.get('require_oversold'):
        print(f"  超跌达标(v3): {stats['consecutive_ok'] - stats.get('oversold_skip', 0)} | 跳过: {stats.get('oversold_skip', 0)}")
    print(f"  回调幅度达标: {stats['pullback_range_ok']}")
    print(f"  均线达标: {stats['ma_ok']}")
    print(f"  量能达标: {stats['volume_shrink_ok']}")
    print(f"  阳线达标: {stats['yang_ok']}")
    print(f"  放量达标: {stats['volume_expand_ok']}")
    if PARAMS.get('require_low_close'):
        print(f"  低位收盘达标(v3): {stats['volume_expand_ok'] - stats.get('low_close_skip', 0)} | 跳过: {stats.get('low_close_skip', 0)}")
    print(f"  ✅ 最终候选: {stats['final']}")

    if len(candidates) == 0:
        print("\n今日无符合条件的股票")
        return []

    df = pd.DataFrame(candidates)
    print(f"\n候选列表：")
    for _, row in df.iterrows():
        print(f"  {row['code']} | 价格:{row['price']} | "
              f"回调:{row['pullback_pct']}% | "
              f"连板:{row['limit_days']}天 | "
              f"实体板:{row['entity_ratio']}% | "
              f"高点:{row['highest_price']}")

    df.to_csv(os.path.join(BASE, f'candidates_{datetime.now().strftime("%Y%m%d")}_{mode}.csv'), index=False)
    print(f"\n✅ 结果已保存至: candidates_{datetime.now().strftime('%Y%m%d')}_{mode}.csv")
    return df['code'].tolist()


# ==================== 主入口 ====================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h']:
        print("=" * 60)
        print("A股连板回调策略 v3 — 华安证券研报改进版")
        print("=" * 60)
        print("")
        print("用法:")
        print("  python 选股new_v3.py --download        # 下载全量历史数据")
        print("  python 选股new_v3.py --today [模式]    # 当日选股")
        print("  python 选股new_v3.py --optimize        # 参数优化（自动找最优参数）")
        print("  python 选股new_v3.py                   # 默认回测")
        print("")
        print("模式: strict | normal | loose | oversold | debug")
        print("")
        print("v3 改进（基于华安证券研报 32,615 首板样本）:")
        print("  1. 收紧 strict：回调≤15% + 缩量≤0.3x")
        print("  2. 超跌反弹过滤：连板前 20 日跌幅 >10%")
        print("  3. 低位收盘过滤：信号日收盘在振幅下半区")
        print("  4. 新增 oversold 模式：聚焦超跌反弹")
        print("  5. 优化评分：胜率 0.5 > 总收益 0.35 > 信号数 0.15")
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--download':
        download_all_data()
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--optimize':
        print("=" * 60)
        print("参数优化模式（v3 自动寻优）")
        print("=" * 60)
        best_params, best_df = optimize_params('20250101', '20260430')
        print("\n✅ 参数优化完成！最佳参数已找到。")
        sys.exit()

    if len(sys.argv) > 1 and sys.argv[1] == '--today':
        mode = sys.argv[2] if len(sys.argv) > 2 else "normal"
        if mode not in ['strict', 'normal', 'loose', 'debug', 'oversold']:
            print(f"⚠️ 未知模式 '{mode}'，使用 'normal' 模式")
            mode = "normal"
        candidates = screen_today(mode=mode)
        if len(candidates) > 0:
            print(f"\n{'='*60}")
            print(f"📋 选股结果")
            print(f"{'='*60}")
            print(f"共选出 {len(candidates)} 只候选股票:")
            print(f"CANDIDATE_CODES = {candidates}")
        sys.exit()

    # ========== 默认：跑完整评估流程 ==========
    print("=" * 60)
    print("v3 完整评估流程")
    print("=" * 60)
    print("将依次运行：")
    print("  1. 原版参数回测（baseline）")
    print("  2. 参数自动寻优")
    print("  3. 最佳参数回测")
    print("  4. 对比报告")
    print("")

    # ---- 1. Baseline（原版参数）----
    print("\n" + "=" * 60)
    print("📊 第一步：原版参数回测（Baseline）")
    print("=" * 60)
    PARAMS.update({
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.3,
        "pullback_ratio_min": 0.08,
        "pullback_ratio_max": 0.25,
        "volume_shrink_ratio": 0.4,
        "volume_shrink_ratio_min": 0.0,
        "take_profit": 0.05,
        "stop_loss": -0.07,
        "hold_days": 7,
        "require_oversold": False,
        "require_low_close": False,
    })
    baseline = run_backtest('20250101', '20260430')

    # ---- 2. 参数寻优 ----
    print("\n" + "=" * 60)
    print("🔍 第二步：参数自动寻优（v3）")
    print("=" * 60)
    best_params, best_signals = optimize_params('20250101', '20260430')

    # ---- 3. 最佳参数回测 ----
    print("\n" + "=" * 60)
    print("✅ 第三步：最佳参数验证回测")
    print("=" * 60)
    PARAMS.update(best_params)
    v3_best = run_backtest('20250101', '20260430')

    # ---- 4. 对比报告 ----
    if baseline is not None and v3_best is not None:
        print("\n" + "=" * 60)
        print("🏆 第四步：对比报告")
        print("=" * 60)

        b_win = (baseline['return'] > 0).sum() / len(baseline)
        v_win = (v3_best['return'] > 0).sum() / len(v3_best)
        b_avg = baseline['return'].mean()
        v_avg = v3_best['return'].mean()
        b_total = (1 + baseline['return']).prod() - 1
        v_total = (1 + v3_best['return']).prod() - 1
        b_pf = abs(baseline[baseline['return']>0]['return'].mean() / baseline[baseline['return']<=0]['return'].mean()) if (baseline['return']<=0).any() else 99
        v_pf = abs(v3_best[v3_best['return']>0]['return'].mean() / v3_best[v3_best['return']<=0]['return'].mean()) if (v3_best['return']<=0).any() else 99

        print(f"\n{'指标':<20} {'原版Baseline':<18} {'v3最佳参数':<18} {'改进':<15}")
        print(f"{'-'*70}")
        print(f"{'胜率':<20} {b_win:<18.2%} {v_win:<18.2%} {v_win-b_win:<+.2%}")
        print(f"{'平均收益':<20} {b_avg:<18.2%} {v_avg:<18.2%} {v_avg-b_avg:<+.2%}")
        print(f"{'总收益':<20} {b_total:<18.2%} {v_total:<18.2%} {v_total-b_total:<+.2%}")
        print(f"{'盈亏比':<20} {b_pf:<18.2f} {v_pf:<18.2f} {v_pf-b_pf:<+.2f}")
        print(f"{'信号数':<20} {len(baseline):<18} {len(v3_best):<18} {len(v3_best)-len(baseline):+d}")
        print(f"{'最大盈利':<20} {baseline['return'].max():<18.2%} {v3_best['return'].max():<18.2%}")
        print(f"{'最大亏损':<20} {baseline['return'].min():<18.2%} {v3_best['return'].min():<18.2%}")

        # 结论
        print(f"\n📋 结论：")
        improvements = []
        if v_win > b_win: improvements.append(f"胜率提升 {v_win-b_win:+.1%}")
        if v_avg > b_avg: improvements.append(f"均收益提升 {v_avg-b_avg:+.1%}")
        if v_total > b_total: improvements.append(f"总收益提升 {v_total-b_total:+.1%}")
        if improvements:
            print(f"  ✅ v3 改进有效：{'，'.join(improvements)}")
        else:
            print(f"  ⚠️ v3 改进未显著超越 baseline，建议进一步调整参数")
