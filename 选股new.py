"""
A股连板回调策略 - 全量下载 + 回测一体化
首次运行：下载全量数据到本地（约40-60分钟）
后续运行：直接从本地读取，秒级回测

v2 修复：
  - 信号去重：每个连板事件只取第一个触发日
  - 止盈止损公平化：按距离开盘价近的先触发
  - 板块涨跌停阈值：区分主板10%/科创创业板20%
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
    "volume_compare_days": 3,
    "signal_today_yang": True,
    "signal_volume_expand": 1.2,
    "hold_days": 7,
    "take_profit": 0.05,
    "stop_loss": -0.07,
}


# ==================== 工具函数 ====================
def get_limit_threshold(code):
    """根据股票代码返回涨跌停阈值（修复3：区分板块）"""
    if code.startswith(('30', '688')):
        return 18.5   # 创业板/科创板 20% 涨跌停
    else:
        return 9.5    # 主板 10% 涨跌停


# ==================== 1. 生成全A股代码列表 ====================
def generate_all_codes():
    """生成全A股候选代码"""
    codes = []

    # 上海主板 600000-605999
    for i in range(600000, 606000):
        codes.append(f"{i}.SS")

    # 深圳主板+中小板 000001-004999
    for i in range(1, 5000):
        codes.append(f"{i:06d}.SZ")

    # 创业板 300000-301999
    for i in range(300000, 302000):
        codes.append(f"{i}.SZ")

    # 科创板 688000-689999
    for i in range(688000, 690000):
        codes.append(f"{i}.SS")

    return codes

# ==================== 2. 下载单只股票到本地 ====================
def download_one_stock(code):
    """下载一只股票的历史数据，保存到本地csv"""
    cache_file = os.path.join(DATA_DIR, f"{code}.csv")

    # 如果已存在且不是空文件，跳过
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        return True, "已有缓存"

    try:
        ticker = yf.Ticker(code)
        df = ticker.history(start="2020-01-01", end=datetime.now().strftime('%Y-%m-%d'))

        if df is None or len(df) == 0:
            # 写个空文件标记，避免重复尝试
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

    # 统计已有缓存
    existing = sum(1 for f in os.listdir(DATA_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100)
    print(f"候选代码总数: {total}")
    print(f"已有本地缓存: {existing}")
    print(f"待下载: {total - existing}")
    print(f"数据目录: {os.path.abspath(DATA_DIR)}/")
    print(f"预计首次下载时间: 40-60分钟\n")

    success = 0
    fail = 0
    skip = 0

    start_time = time.time()

    for i, code in enumerate(all_codes):
        ok, msg = download_one_stock(code)

        if msg == "已有缓存":
            skip += 1
        elif ok:
            success += 1
        else:
            fail += 1

        # 每200只显示进度
        if (i + 1) % 200 == 0:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed * 60
            remaining = (total - i - 1) / speed if speed > 0 else 0
            print(f"  进度: {i+1}/{total} ({((i+1)/total)*100:.1f}%) | "
                  f"速度: {speed:.0f}只/分钟 | 预计剩余: {remaining:.0f}分钟 | "
                  f"成功: {success} | 缓存: {skip} | 失败: {fail}")

    total_time = time.time() - start_time
    print(f"\n✅ 下载完成！耗时: {total_time/60:.1f}分钟")
    print(f"   成功: {success} | 已有缓存: {skip} | 失败(退市等): {fail}")
    print(f"   有效数据约: {success + skip} 只股票\n")

# ==================== 5. 识别连板 ====================
def identify_limit_up_series(df_stock, code=""):
    """识别连板序列（修复3：支持区分板块涨跌停阈值）"""
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
                'date': row['trade_date'],
                'close': row['close'],
                'high': row['high'],
                'is_one_word': row['is_one_word'],
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

# ==================== 6. 检查回调 ====================
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

    limit_volumes = [d['volume'] for d in limit_series_item]
    limit_avg_vol = np.mean(limit_volumes)

    pullback_start = max(0, current_idx - PARAMS['volume_compare_days'])
    pullback_volumes = df_stock.iloc[pullback_start:current_idx]['volume'].tolist()
    if len(pullback_volumes) < PARAMS['volume_compare_days']:
        return None

    pullback_avg_vol = np.mean(pullback_volumes)
    if limit_avg_vol > 0 and pullback_avg_vol / limit_avg_vol > PARAMS['volume_shrink_ratio']:
        return None

    if current_idx < PARAMS['ma_stabilize']:
        return None
    ma = df_stock.iloc[current_idx - PARAMS['ma_stabilize'] + 1:current_idx + 1]['close'].mean()
    if current_price < ma:
        return None

    if PARAMS['signal_today_yang']:
        if df_stock.iloc[current_idx]['close'] <= df_stock.iloc[current_idx]['open']:
            return None

    if current_idx >= 1:
        today_vol = df_stock.iloc[current_idx]['volume']
        yesterday_vol = df_stock.iloc[current_idx - 1]['volume']
        if yesterday_vol > 0 and today_vol / yesterday_vol < PARAMS['signal_volume_expand']:
            return None

    return {
        'trigger_date': df_stock.iloc[current_idx]['trade_date'],
        'trigger_price': current_price,
        'highest_price': highest_price,
        'pullback_ratio': pullback_ratio,
        'limit_series_len': len(limit_series_item),
        'limit_dates': f"{limit_series_item[0]['date']}~{limit_series_item[-1]['date']}"
    }

# ==================== 7. 模拟持仓（修复2：公平止盈止损）====================
def simulate_hold_return(df_stock, entry_idx, entry_price):
    """模拟持仓收益（修复2：距离开盘价更近的阈值先触发，更接近真实交易）"""
    exit_idx = min(entry_idx + PARAMS['hold_days'], len(df_stock) - 1)

    for i in range(entry_idx + 1, exit_idx + 1):
        high = df_stock.iloc[i]['high']
        low = df_stock.iloc[i]['low']
        open_price = df_stock.iloc[i]['open']

        if entry_price <= 0:
            continue

        # 第一层：开盘跳空直接触发（确定性事件，优先判断）
        open_return = open_price / entry_price - 1
        if open_return <= PARAMS['stop_loss']:
            return open_return, i - entry_idx, '止损'
        if open_return >= PARAMS['take_profit']:
            return open_return, i - entry_idx, '止盈'

        # 第二层：日内触及 —— 距离开盘价更近的阈值先触发
        stop_level = entry_price * (1 + PARAMS['stop_loss'])
        profit_level = entry_price * (1 + PARAMS['take_profit'])

        dist_to_stop = open_price - stop_level    # 开盘到止损价的距离
        dist_to_profit = profit_level - open_price  # 开盘到止盈价的距离

        if dist_to_stop <= dist_to_profit:
            # 止损价更近（或等距）：先触及止损
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                return PARAMS['stop_loss'], i - entry_idx, '止损'
            if high / entry_price - 1 >= PARAMS['take_profit']:
                return PARAMS['take_profit'], i - entry_idx, '止盈'
        else:
            # 止盈价更近：先触及止盈
            if high / entry_price - 1 >= PARAMS['take_profit']:
                return PARAMS['take_profit'], i - entry_idx, '止盈'
            if low / entry_price - 1 <= PARAMS['stop_loss']:
                return PARAMS['stop_loss'], i - entry_idx, '止损'

    final_price = df_stock.iloc[exit_idx]['close']
    final_return = final_price / entry_price - 1 if entry_price > 0 else 0
    return final_return, PARAMS['hold_days'], '到期'

# ==================== 8. 主回测（修复1+3：信号去重 + 板块阈值）====================
def run_backtest(start_date, end_date):
    """从本地缓存读取数据，向量化扫描（修复1：每连板事件只取首个触发日；修复3：区分板块涨跌停）"""
    print("=" * 60)
    print("阶段二：执行回测（向量化加速版）")
    print("=" * 60)
    print(f"回测区间：{start_date} ~ {end_date}")
    print(f"参数：连板≥{PARAMS['min_consecutive_limit_up']} | "
          f"回调{PARAMS['pullback_ratio_min']:.0%}-{PARAMS['pullback_ratio_max']:.0%}")

    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]

    print(f"\n本地有效数据：{len(cache_files)} 只股票")

    # ====== 第一步：快速扫描，找出有涨停记录的股票（修复3：区分板块）======
    print("第一步：扫描有涨停/连板记录的股票...")
    hot_codes = []

    start_time = time.time()
    for idx, fname in enumerate(cache_files):
        code = fname.replace('.csv', '')
        df = load_from_cache(code)

        if df is None or len(df) < 50:
            continue

        # 只看回测区间内的数据
        df = df[(df['trade_date'] >= start_date) & (df['trade_date'] <= end_date)]
        if len(df) == 0:
            continue

        # 修复3：根据板块使用对应的涨停阈值
        limit_threshold = get_limit_threshold(code)
        has_limit_up = (df['pct_chg'] >= limit_threshold).any()

        if has_limit_up:
            hot_codes.append(code)

        if (idx + 1) % 1000 == 0:
            print(f"  已扫描 {idx+1}/{len(cache_files)}，涨停股: {len(hot_codes)}")

    print(f"✅ 扫描完成！{len(hot_codes)} 只有过涨停记录（耗时: {time.time()-start_time:.0f}秒）\n")

    # ====== 第二步：只对涨停过的股票做深度分析 ======
    print("第二步：对涨停股做深度连板+回调分析...")

    start_dt = datetime.strptime(start_date, '%Y%m%d')
    end_dt = datetime.strptime(end_date, '%Y%m%d')

    all_signals = []
    start_time = time.time()

    for idx, code in enumerate(hot_codes):
        if (idx + 1) % 100 == 0:
            elapsed = time.time() - start_time
            remaining = (len(hot_codes) - idx - 1) * (elapsed / (idx + 1))
            print(f"  进度：{idx+1}/{len(hot_codes)} | 已发现信号：{len(all_signals)} | 预计剩余：{remaining:.0f}秒")

        df_stock = load_from_cache(code)
        if df_stock is None:
            continue

        # 截取回测区间
        df_stock = df_stock[
            (df_stock['trade_date'] >= start_date) &
            (df_stock['trade_date'] <= end_date)
        ].reset_index(drop=True)

        if len(df_stock) < PARAMS['lookback_days'] + 10:
            continue

        # 修复3：根据板块使用对应的涨停阈值
        limit_threshold = get_limit_threshold(code)

        # 向量化标注涨停和一字板
        df_stock['is_limit_up'] = df_stock['pct_chg'] >= limit_threshold
        df_stock['is_one_word'] = (
            (df_stock['open'] == df_stock['high']) &
            (df_stock['low'] == df_stock['close']) &
            df_stock['is_limit_up']
        )

        # 找连板序列（向量化找连续涨停段）
        limit_up_indices = df_stock[df_stock['is_limit_up']].index.tolist()

        # 分组连续涨停
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

        # 对每个连板组，检查后面的回调
        for group in groups:
            if len(group) < PARAMS['min_consecutive_limit_up']:
                continue

            # 实体板比例
            entity_count = sum(1 for i in group if not df_stock.iloc[i]['is_one_word'])
            if entity_count / len(group) < PARAMS['min_entity_board_ratio']:
                continue

            last_limit_idx = group[-1]
            highest_price = max(df_stock.iloc[i]['high'] for i in group)

            # 修复1：按天顺序检查回调，找到第一个触发日即停止（每个连板事件最多产生1个信号）
            for check_idx in range(last_limit_idx + PARAMS['min_pullback_days'] + 1, min(last_limit_idx + 15, len(df_stock))):
                current_price = df_stock.iloc[check_idx]['close']
                pullback_ratio = (highest_price - current_price) / highest_price

                # 回调幅度
                if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
                    continue

                # 均线
                if check_idx < PARAMS['ma_stabilize']:
                    continue
                ma = df_stock.iloc[check_idx - PARAMS['ma_stabilize'] + 1:check_idx + 1]['close'].mean()
                if current_price < ma:
                    continue

                # 量能萎缩
                limit_volumes = [df_stock.iloc[i]['volume'] for i in group]
                limit_avg_vol = np.mean(limit_volumes)

                pullback_start = max(0, check_idx - PARAMS['volume_compare_days'])
                pullback_volumes = df_stock.iloc[pullback_start:check_idx]['volume'].tolist()
                if len(pullback_volumes) < PARAMS['volume_compare_days']:
                    continue
                pullback_avg_vol = np.mean(pullback_volumes)

                if limit_avg_vol > 0 and pullback_avg_vol / limit_avg_vol > PARAMS['volume_shrink_ratio']:
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

                # 修复1：找到第一个触发日后立即停止，避免同一回调事件产生多个信号
                break

    total_time = time.time() - start_time

    # ---- 报告部分 ----
    print(f"\n{'='*60}")
    print(f"回测完成！耗时: {total_time:.1f}秒")
    print(f"{'='*60}")
    print(f"总信号数：{len(all_signals)}")

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
    exit_dist = df['exit_reason'].value_counts()
    for reason, count in exit_dist.items():
        print(f"  {reason}：{count}次 ({count/len(df)*100:.1f}%)")

    # 保存
    output_file = os.path.join(BASE, f'backtest_signals_{start_date}_{end_date}.csv')
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✅ 详细信号已保存至：{output_file}")

    return df

# ==================== 9. 预提取连板事件（修复3：区分板块涨跌停）====================
def extract_all_events(hot_codes, start_date, end_date):
    """对所有涨停股票，预先提取连板事件（只跑一次）（修复3：区分板块涨跌停阈值）"""
    print("正在预提取连板事件...")
    all_events = []  # 每个事件: {code, last_limit_idx, highest_price, limit_volumes, ...}

    start_dt = datetime.strptime(start_date, '%Y%m%d')
    end_dt = datetime.strptime(end_date, '%Y%m%d')

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

        # 修复3：根据板块使用对应的涨停阈值
        limit_threshold = get_limit_threshold(code)

        # 标注涨停
        df_stock['is_limit_up'] = df_stock['pct_chg'] >= limit_threshold
        df_stock['is_one_word'] = (
            (df_stock['open'] == df_stock['high']) &
            (df_stock['low'] == df_stock['close']) &
            df_stock['is_limit_up']
        )

        limit_up_indices = df_stock[df_stock['is_limit_up']].index.tolist()
        if not limit_up_indices:
            continue

        # 分组连续涨停
        groups = []
        current_group = [limit_up_indices[0]]
        for i in range(1, len(limit_up_indices)):
            if limit_up_indices[i] == limit_up_indices[i-1] + 1:
                current_group.append(limit_up_indices[i])
            else:
                groups.append(current_group)
                current_group = [limit_up_indices[i]]
        groups.append(current_group)

        # 对每个连板组，提取关键信息
        for group in groups:
            if len(group) < 2:  # 至少2连板（优化时会再筛选）
                continue

            entity_count = sum(1 for i in group if not df_stock.iloc[i]['is_one_word'])
            entity_ratio = entity_count / len(group)
            highest_price = max(df_stock.iloc[i]['high'] for i in group)
            limit_volumes = [df_stock.iloc[i]['volume'] for i in group]
            limit_avg_vol = np.mean(limit_volumes)

            last_limit_idx = group[-1]

            # 对于连板结束后的每一天（第2到第14天），预计算回调数据
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

                # 预计算当日数据
                is_yang = df_stock.iloc[check_idx]['close'] > df_stock.iloc[check_idx]['open']
                today_vol = df_stock.iloc[check_idx]['volume']
                yesterday_vol = df_stock.iloc[check_idx - 1]['volume'] if check_idx > 0 else today_vol
                vol_expand_ratio = today_vol / yesterday_vol if yesterday_vol > 0 else 1

                # 后续N天数据（用于模拟持仓）
                future_data = []
                for fwd in range(1, 11):  # 最多看10天
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
                    'future_data': future_data,
                })

    print(f"✅ 预提取完成！共 {len(all_events)} 个回调事件")
    return all_events


# ==================== 10. 快速参数优化（修复2：公平止盈止损 + 修复3：板块阈值）====================
def optimize_params(start_date, end_date):
    """基于预提取的事件，快速遍历参数组合（修复2+3）"""
    print("=" * 60)
    print("自动参数优化模式（极速版）")
    print("=" * 60)

    # 先扫描涨停股票（修复3：区分板块涨跌停阈值）
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
        # 修复3：根据板块使用对应的涨停阈值
        limit_threshold = get_limit_threshold(code)
        if (df['pct_chg'] >= limit_threshold).any():
            hot_codes.append(code)
    print(f"✅ 涨停股票：{len(hot_codes)} 只")

    # 预提取所有事件（只跑一次，之后全部用这个）
    print("\n第二步：预提取连板+回调事件（只跑一次）...")
    all_events = extract_all_events(hot_codes, start_date, end_date)

    # ---- 参数网格 ----
    param_grid = {
        "min_consecutive_limit_up": [2,3,4],
        "min_entity_board_ratio": [0.3, 0.5,0.7],
        "pullback_ratio_min": [0.05, 0.08, 0.10, 0.15],
        "pullback_ratio_max": [0.15, 0.20, 0.25, 0.30],
        "volume_shrink_ratio": [0.40, 0.50, 0.60, 0.70,0.80],
        "take_profit": [0.05,0.06,0.07,0.08,0.09,0.10],
        "stop_loss": [-0.05,-0.07,-0.15,-0.2],
        "hold_days": [3,5,7],
    }

    from itertools import product
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    all_combinations = list(product(*values))

    total_combos = len(all_combinations)
    print(f"\n第三步：遍历 {total_combos} 种参数组合...")
    print(f"预计耗时：1-3分钟\n")

    results_list = []
    best_score = -999
    best_params = None
    best_signals = None

    start_time = time.time()

    for i, combo in enumerate(all_combinations):
        params_dict = dict(zip(keys, combo))

        # 用预提取的事件快速筛选
        signals = []

        for evt in all_events:
            # 连板条件
            if evt['limit_series_len'] < params_dict['min_consecutive_limit_up']:
                continue
            if evt['entity_ratio'] < params_dict['min_entity_board_ratio']:
                continue

            # 回调条件
            if evt['pullback_ratio'] < params_dict['pullback_ratio_min']:
                continue
            if evt['pullback_ratio'] > params_dict['pullback_ratio_max']:
                continue

            # 量能
            vol_ratio = evt['pullback_avg_vol'] / evt['limit_avg_vol'] if evt['limit_avg_vol'] > 0 else 1
            if vol_ratio > params_dict['volume_shrink_ratio']:
                continue

            # 均线（简化：-1表示可忽略，实际已预计算）
            if evt['trigger_price'] < evt['ma']:
                continue

            # 阳线
            if not evt['is_yang']:
                continue

            # 模拟持仓（修复2：距离开盘价更近的阈值先触发）
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

                # 第一层：开盘跳空直接触发
                open_ret = bar['open'] / entry_price - 1
                if open_ret <= stop_loss:
                    ret = open_ret
                    exit_reason = '止损'
                    days_held = fwd_idx + 1
                    break
                if open_ret >= take_profit:
                    ret = open_ret
                    exit_reason = '止盈'
                    days_held = fwd_idx + 1
                    break

                # 第二层：日内触及 —— 距离开盘价更近的阈值先触发
                stop_level = entry_price * (1 + stop_loss)
                profit_level = entry_price * (1 + take_profit)

                dist_to_stop = bar['open'] - stop_level
                dist_to_profit = profit_level - bar['open']

                if dist_to_stop <= dist_to_profit:
                    # 止损更近：先检查止损
                    if bar['low'] / entry_price - 1 <= stop_loss:
                        ret = stop_loss
                        exit_reason = '止损'
                        days_held = fwd_idx + 1
                        break
                    if bar['high'] / entry_price - 1 >= take_profit:
                        ret = take_profit
                        exit_reason = '止盈'
                        days_held = fwd_idx + 1
                        break
                else:
                    # 止盈更近：先检查止盈
                    if bar['high'] / entry_price - 1 >= take_profit:
                        ret = take_profit
                        exit_reason = '止盈'
                        days_held = fwd_idx + 1
                        break
                    if bar['low'] / entry_price - 1 <= stop_loss:
                        ret = stop_loss
                        exit_reason = '止损'
                        days_held = fwd_idx + 1
                        break
            else:
                # 到期退出
                if len(evt['future_data']) >= hold_days:
                    ret = evt['future_data'][hold_days - 1]['close'] / entry_price - 1
                elif len(evt['future_data']) > 0:
                    ret = evt['future_data'][-1]['close'] / entry_price - 1

            signals.append({
                'date': evt['date'],
                'code': evt['code'],
                'return': ret,
                'exit_reason': exit_reason,
                'hold_days': days_held,
            })

        if len(signals) == 0:
            continue

        # 统计
        df = pd.DataFrame(signals)
        win_rate = (df['return'] > 0).sum() / len(df)
        avg_return = df['return'].mean()
        total_return = (1 + df['return']).prod() - 1
        signal_count = len(df)

        score = win_rate * 0.3 + max(total_return, -1) * 0.5 + min(signal_count / 200, 1) * 0.2

        results_list.append({
            **params_dict,
            'win_rate': round(win_rate, 4),
            'avg_return': round(avg_return, 4),
            'total_return': round(total_return, 4),
            'signal_count': signal_count,
            'score': round(score, 4),
        })

        if score > best_score:
            best_score = score
            best_params = params_dict.copy()
            best_signals = df.copy()

        # 每20组打印进度
        if (i + 1) % 20 == 0:
            elapsed = time.time() - start_time
            remaining = (total_combos - i - 1) * (elapsed / (i + 1))
            print(f"  进度：{i+1}/{total_combos} | 预计剩余：{remaining/60:.0f}分钟 | 当前最佳：{best_score:.4f}")

    # ---- 输出 ----
    print(f"\n{'='*60}")
    print(f"🏆 最佳参数")
    print(f"{'='*60}")
    for k, v in best_params.items():
        print(f"  {k}: {v}")

    print(f"\n最佳参数回测结果：")
    print(f"  信号数：{len(best_signals)}")
    print(f"  胜率：{(best_signals['return'] > 0).sum() / len(best_signals):.2%}")
    print(f"  总收益：{((1 + best_signals['return']).prod() - 1):.2%}")

    # 保存全部排名
    df_results = pd.DataFrame(results_list).sort_values('score', ascending=False)
    df_results.to_csv(os.path.join(BASE, 'optimization_results.csv'), index=False, encoding='utf-8-sig')
    print(f"\n✅ 全部排名已保存至 optimization_results.csv")
    print(f"\n前10名：")
    print(df_results.head(10).to_string())

    return best_params, best_signals

# 在 PARAMS 定义之后，添加参数模式配置
# ==================== 参数模式配置 ====================
SCREEN_MODES = {
    "strict": {  # 严格模式（历史回测最优）
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.3,
        "pullback_ratio_min": 0.08,
        "pullback_ratio_max": 0.25,
        "volume_shrink_ratio": 0.4,
        "signal_today_yang": True,
        "signal_volume_expand": 1.2,
        "min_pullback_days": 2,
        "ma_stabilize": 10,
        "volume_compare_days": 3,
    },
    "normal": {  # 正常模式（放宽实体板和阳线要求）
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.15,
        "pullback_ratio_min": 0.05,
        "pullback_ratio_max": 0.30,
        "volume_shrink_ratio": 0.6,
        "signal_today_yang": False,
        "signal_volume_expand": 1.0,
        "min_pullback_days": 1,
        "ma_stabilize": 10,
        "volume_compare_days": 3,
    },
    "loose": {  # 宽松模式（找任何连板回调迹象）
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.0,
        "pullback_ratio_min": 0.02,
        "pullback_ratio_max": 0.40,
        "volume_shrink_ratio": 1.2,
        "signal_today_yang": False,
        "signal_volume_expand": 0.0,
        "min_pullback_days": 1,
        "ma_stabilize": 5,
        "volume_compare_days": 2,
    },
    "debug": {  # 调试模式（几乎不过滤，看所有有连板的股票）
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.0,
        "pullback_ratio_min": -1.0,
        "pullback_ratio_max": 10.0,
        "volume_shrink_ratio": 10.0,
        "signal_today_yang": False,
        "signal_volume_expand": 0.0,
        "min_pullback_days": 0,
        "ma_stabilize": 0,
        "volume_compare_days": 1,
    }
}


# ==================== 单只股票筛选（批量/逐只共用）====================
def _screen_single_stock(code, stock_df, stats, candidates, mode="normal"):
    """对单只股票的近期数据执行完整筛选流程（供批量+逐只两种路径共用）

    Args:
        code: 股票代码
        stock_df: DataFrame，需包含 [Open, High, Low, Close, Volume] 列
        stats: 统计字典（原地修改）
        candidates: 候选列表（原地修改）
        mode: 筛选模式
    """
    close = stock_df['Close'].dropna()
    if len(close) < 15:
        return

    stats['has_data'] += 1

    open_price = stock_df['Open'].dropna()
    high = stock_df['High'].dropna()
    low = stock_df['Low'].dropna()
    volume = stock_df['Volume'].dropna()

    # 对齐长度
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

    # 涨停标注（区分主板和创业板/科创板）
    limit_threshold = get_limit_threshold(code)

    df_recent['is_limit_up'] = df_recent['pct_chg'] >= limit_threshold
    df_recent['is_one_word'] = (
        (df_recent['open'] == df_recent['high']) &
        (df_recent['low'] == df_recent['close']) &
        df_recent['is_limit_up']
    )

    # 检查是否有涨停
    if not df_recent['is_limit_up'].any():
        return

    stats['has_limit_up'] += 1

    # 找最近一次连板
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

    # 从最新到最旧遍历每个连板组，找到第一个满足今日回调条件的
    today_idx = len(df_recent) - 1
    today_row = df_recent.iloc[today_idx]

    # 跟踪此股票在各筛选阶段是否达标（用于漏斗统计）
    passed_consecutive = False
    passed_entity = False
    passed_pullback_days = False
    passed_pullback_range = False
    passed_ma = False
    passed_volume = False
    passed_yang = False
    passed_volume_expand = False

    for grp in reversed(groups):  # 最新连板组优先
        if len(grp) < PARAMS['min_consecutive_limit_up']:
            continue
        passed_consecutive = True

        # 实体板比例
        entity_count = sum(1 for i in grp if not df_recent.iloc[i]['is_one_word'])
        entity_ratio = entity_count / len(grp) if len(grp) > 0 else 0
        if entity_ratio < PARAMS['min_entity_board_ratio']:
            continue
        passed_entity = True

        last_limit_idx = grp[-1]
        if today_idx - last_limit_idx < PARAMS['min_pullback_days']:
            continue
        passed_pullback_days = True

        highest_price = max(df_recent.iloc[i]['high'] for i in grp)
        current_price = today_row['close']
        pullback_ratio = (highest_price - current_price) / highest_price

        if pullback_ratio < PARAMS['pullback_ratio_min'] or pullback_ratio > PARAMS['pullback_ratio_max']:
            continue
        passed_pullback_range = True

        # 均线
        if PARAMS['ma_stabilize'] > 0 and today_idx >= PARAMS['ma_stabilize']:
            ma = df_recent.iloc[today_idx - PARAMS['ma_stabilize'] + 1:today_idx + 1]['close'].mean()
            if current_price < ma:
                continue
        passed_ma = True

        # 量能萎缩检查
        if PARAMS['volume_shrink_ratio'] < 10:  # 不是调试模式
            limit_volumes = [df_recent.iloc[i]['volume'] for i in grp]
            limit_avg_vol = np.mean(limit_volumes)

            pullback_start_idx = max(0, today_idx - PARAMS['volume_compare_days'])
            pullback_vols = df_recent.iloc[pullback_start_idx:today_idx]['volume'].tolist()
            if len(pullback_vols) >= 2:
                pullback_avg_vol = np.mean(pullback_vols)
                if limit_avg_vol > 0 and pullback_avg_vol / limit_avg_vol > PARAMS['volume_shrink_ratio']:
                    continue
        passed_volume = True

        # 阳线检查
        if PARAMS['signal_today_yang']:
            if today_row['close'] <= today_row['open']:
                continue
        passed_yang = True

        # 放量检查
        if PARAMS['signal_volume_expand'] > 0 and today_idx >= 1:
            today_vol = today_row['volume']
            yesterday_vol = df_recent.iloc[today_idx - 1]['volume']
            if yesterday_vol > 0 and today_vol / yesterday_vol < PARAMS['signal_volume_expand']:
                continue
        passed_volume_expand = True

        # 全部通过！
        break

    # ---- 更新漏斗统计 ----
    if passed_consecutive:
        stats['consecutive_ok'] += 1
    if passed_entity:
        stats['entity_ratio_ok'] += 1
    if passed_pullback_days:
        stats['pullback_days_ok'] += 1
    if passed_pullback_range:
        stats['pullback_range_ok'] += 1
    if passed_ma:
        stats['ma_ok'] += 1
    if passed_volume:
        stats['volume_shrink_ok'] += 1
    if passed_yang:
        stats['yang_ok'] += 1
    if passed_volume_expand:
        stats['volume_expand_ok'] += 1

    if not passed_volume_expand:
        return

    # 通过所有筛选
    stats['final'] += 1
    candidates.append({
        'code': code,
        'price': round(current_price, 2),
        'pullback_pct': round(pullback_ratio * 100, 1),
        'limit_days': len(grp),
        'highest_price': round(highest_price, 2),
        'entity_ratio': round(entity_ratio * 100, 1),
    })


# ==================== 当日选股（批量加速 + 逐只容错）====================
def screen_today(mode="normal"):
    """用指定参数筛选今天的候选股票

    参数:
        mode: 筛选模式 - 'strict'(严格), 'normal'(正常), 'loose'(宽松), 'debug'(调试)

    容错机制：批量下载失败时自动降级为逐只下载，单只失败不影响同批次其他股票。
    """

    # 获取对应模式的参数
    if mode not in SCREEN_MODES:
        print(f"⚠️ 未知模式 '{mode}'，使用 'normal' 模式")
        mode = "normal"

    BEST_PARAMS = SCREEN_MODES[mode].copy()

    global PARAMS
    original_params = PARAMS.copy()
    PARAMS.update(BEST_PARAMS)

    print("=" * 60)
    print("第一层：当日量化筛选（批量加速版）")
    print("=" * 60)
    print(f"筛选模式: {mode}")
    print(f"筛选日期: {datetime.now().strftime('%Y-%m-%d')}")
    print(f"参数配置:")
    print(f"  连板≥{BEST_PARAMS['min_consecutive_limit_up']}天")
    print(f"  实体板比例≥{BEST_PARAMS['min_entity_board_ratio']:.0%}")
    print(f"  回调幅度: {BEST_PARAMS['pullback_ratio_min']:.0%} - {BEST_PARAMS['pullback_ratio_max']:.0%}")
    print(f"  回调天数≥{BEST_PARAMS['min_pullback_days']}天")
    print(f"  缩量要求: ≤{BEST_PARAMS['volume_shrink_ratio']:.0%}")
    print(f"  今日阳线: {'是' if BEST_PARAMS['signal_today_yang'] else '否'}")
    print(f"  放量要求: ≥{BEST_PARAMS['signal_volume_expand']:.1f}倍" if BEST_PARAMS['signal_volume_expand'] > 0 else "  放量要求: 无")

    # 获取代码列表
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    codes = [f.replace('.csv', '') for f in cache_files]

    # 调试模式下只扫描前100只（加快速度）
    if mode == "debug":
        codes = codes[:100]
        print(f"\n⚠️ 调试模式：仅扫描前100只股票")

    # 分批下载，每批200只
    BATCH_SIZE = 200
    batches = [codes[i:i+BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]

    print(f"\n待扫描股票：{len(codes)} 只，分 {len(batches)} 批下载\n")

    candidates = []
    failed_codes = []  # 记录下载失败的股票代码
    stats = {
        'total': 0,
        'has_data': 0,
        'has_limit_up': 0,
        'consecutive_ok': 0,
        'entity_ratio_ok': 0,
        'pullback_days_ok': 0,
        'pullback_range_ok': 0,
        'ma_ok': 0,
        'volume_shrink_ok': 0,
        'yang_ok': 0,
        'volume_expand_ok': 0,
        'download_failed': 0,  # 新增：下载失败的股票数
        'final': 0
    }

    for batch_idx, batch in enumerate(batches):
        print(f"  批次 {batch_idx+1}/{len(batches)}：下载 {len(batch)} 只...", end=" ", flush=True)

        # ---- 路径A：批量下载（yf.download 比 yf.Tickers 更稳定，无效代码自动跳过）----
        hist = None
        try:
            hist = yf.download(
                tickers=" ".join(batch),
                period="30d",
                progress=False,
                auto_adjust=True,
            )
        except Exception:
            hist = None

        # 逐只处理：先尝试从批量结果提取，提取不到则单独下载
        batch_ok = hist is not None and not hist.empty
        if batch_ok:
            # 获取批量结果中实际包含的代码集合（MultiIndex level 1）
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

            # 优先从批量结果提取
            if code in codes_in_batch:
                try:
                    stock_data = hist.xs(code, level=1, axis=1)
                    # 批量结果中可能存在但全是 NaN（退市股），视为实质无效
                    if stock_data is not None and not stock_data.empty:
                        if stock_data['Close'].dropna().empty:
                            stock_data = None
                except Exception:
                    stock_data = None

            # 批量中提取不到或实质无效 → 单独下载（最多重试2次）
            if stock_data is None or stock_data.empty:
                for attempt in range(2):
                    try:
                        ticker = yf.Ticker(code)
                        stock_data = ticker.history(period="30d")
                        if stock_data is not None and not stock_data.empty:
                            if not stock_data['Close'].dropna().empty:
                                break  # 成功拿到有效数据
                            stock_data = None  # 全 NaN，继续重试
                    except Exception:
                        stock_data = None
                        if attempt == 1:
                            if mode == "debug":
                                print(f"\n    下载失败 {code}")
                        else:
                            time.sleep(0.5)

            # 执行筛选（只对有实质数据的股票）
            if stock_data is not None and not stock_data.empty and not stock_data['Close'].dropna().empty:
                try:
                    _screen_single_stock(code, stock_data, stats, candidates, mode)
                except Exception as e:
                    if mode == "debug":
                        print(f"\n    错误 {code}: {e}")
            else:
                # 下载彻底失败（批量+单独都拿不到有效数据）
                stats['download_failed'] += 1
                failed_codes.append(code)
                if mode == "debug":
                    print(f"\n    无数据 {code}")

        print(f" (累计扫描{stats['total']}，候选{stats['final']}，失败{stats['download_failed']})", flush=True)

    # 恢复原参数
    PARAMS.update(original_params)

    # 输出统计信息
    # 输出失败汇总
    if stats['download_failed'] > 0:
        print(f"\n⚠️ 下载失败: {stats['download_failed']} 只 ({stats['download_failed']/stats['total']*100:.1f}%)")
        if len(failed_codes) <= 20:
            print(f"   失败代码: {', '.join(failed_codes)}")
        else:
            print(f"   失败代码(前20): {', '.join(failed_codes[:20])} ...")

    print(f"\n{'='*60}")
    print(f"筛选统计:")
    print(f"{'='*60}")
    print(f"  总扫描: {stats['total']}")
    print(f"  下载成功: {stats['has_data']} | 下载失败: {stats['download_failed']}")
    print(f"  有涨停: {stats['has_limit_up']}")
    print(f"  连板数达标: {stats['consecutive_ok']}")
    print(f"  实体板达标: {stats['entity_ratio_ok']}")
    print(f"  回调天数达标: {stats['pullback_days_ok']}")
    print(f"  回调幅度达标: {stats['pullback_range_ok']}")
    print(f"  均线达标: {stats['ma_ok']}")
    print(f"  量能达标: {stats['volume_shrink_ok']}")
    print(f"  阳线达标: {stats['yang_ok']}")
    print(f"  放量达标: {stats['volume_expand_ok']}")
    print(f"  ✅ 最终候选: {stats['final']}")

    print(f"\n{'='*60}")
    print(f"筛选完成！共找到 {len(candidates)} 只候选股票")
    print(f"{'='*60}")

    if len(candidates) == 0:
        print("\n今日无符合条件的股票")
        print("\n建议:")
        print("  1. 使用宽松模式: python 选股new.py --today loose")
        print("  2. 使用调试模式查看所有有连板的股票: python 选股new.py --today debug")
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

    # 显示帮助信息
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h']:
        print("=" * 60)
        print("A股连板回调策略 - 使用说明 (v2)")
        print("=" * 60)
        print("")
        print("用法:")
        print("  python 选股new.py --download        # 下载全量历史数据（首次运行）")
        print("  python 选股new.py --today [模式]    # 当日选股")
        print("  python 选股new.py --optimize        # 参数优化（基于历史数据）")
        print("  python 选股new.py                   # 默认回测（2025-2026）")
        print("")
        print("当日选股模式:")
        print("  strict   - 严格模式（历史回测最优参数）")
        print("  normal   - 正常模式（推荐日常使用）")
        print("  loose    - 宽松模式（市场弱势时使用）")
        print("  debug    - 调试模式（查看所有连板股票，不过滤）")
        print("")
        print("v2 修复说明:")
        print("  1. 信号去重：每个连板事件只取第一个触发日")
        print("  2. 止盈止损公平化：距开盘价近的阈值先触发")
        print("  3. 板块涨跌停阈值：自动区分主板10%/科创创业板20%")
        print("")
        print("示例:")
        print("  python 选股new.py --today normal")
        print("  python 选股new.py --today loose")
        print("  python 选股new.py --today debug")
        exit()

    # 下载全量数据
    if len(sys.argv) > 1 and sys.argv[1] == '--download':
        download_all_data()
        exit()

    # 参数优化
    if len(sys.argv) > 1 and sys.argv[1] == '--optimize':
        print("=" * 60)
        print("参数优化模式")
        print("=" * 60)
        print("将在历史数据上寻找最优参数组合...")
        best_params, best_df = optimize_params('20250101', '20260430')
        print("\n✅ 参数优化完成！")
        print("建议将优化后的参数更新到 SCREEN_MODES['strict'] 中")
        exit()

    # 当日选股
    if len(sys.argv) > 1 and sys.argv[1] == '--today':
        # 获取模式参数，默认 normal
        mode = sys.argv[2] if len(sys.argv) > 2 else "normal"

        # 验证模式有效性
        if mode not in ['strict', 'normal', 'loose', 'debug']:
            print(f"⚠️ 未知模式 '{mode}'，使用 'normal' 模式")
            print("可用模式: strict, normal, loose, debug")
            mode = "normal"

        candidates = screen_today(mode=mode)

        if len(candidates) > 0:
            print(f"\n{'='*60}")
            print(f"📋 选股结果")
            print(f"{'='*60}")
            print(f"共选出 {len(candidates)} 只候选股票:")
            print(f"CANDIDATE_CODES = {candidates}")
            print(f"\n下一步：")
            print(f"  1. 复制上面的代码到 ai_analysis.py")
            print(f"  2. 运行深度分析: python ai_analysis.py")
        else:
            print(f"\n⚠️ 当前模式 '{mode}' 下无符合条件的股票")
            print(f"\n建议尝试:")
            print(f"  python 选股new.py --today loose   # 宽松模式")
            print(f"  python 选股new.py --today debug   # 调试模式（查看所有连板股）")
        exit()

    # 默认：普通回测
    print("=" * 60)
    print("默认模式：执行历史回测 (v2)")
    print("=" * 60)
    print("提示：使用 python 选股new.py --help 查看所有功能")
    print("")

    # 使用历史回测参数
    PARAMS.update({
        "min_consecutive_limit_up": 2,
        "min_entity_board_ratio": 0.3,
        "pullback_ratio_min": 0.08,
        "pullback_ratio_max": 0.25,
        "volume_shrink_ratio": 0.4,
        "take_profit": 0.05,
        "stop_loss": -0.07,
        "hold_days": 7,
    })

    results = run_backtest('20250101', '20260430')

# 查看帮助 python 选股new.py --help

# 下载数据（首次运行）python 选股new.py --download

# 正常模式选股（推荐）python 选股new.py --today normal

# 宽松模式选股（市场不好时）python 选股new.py --today loose

# 调试模式（看所有连板股）python 选股new.py --today debug

# 严格模式（历史最优参数）python 选股new.py --today strict

# 参数优化 python 选股new.py --optimize

# 默认回测 python 选股new.py
