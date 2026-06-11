# loose_params_screen.py
import yfinance as yf
import pandas as pd
import numpy as np

# 宽松参数（适应震荡市）
LOOSE_PARAMS = {
    "min_consecutive_limit_up": 2,
    "min_entity_board_ratio": 0.1,      # 放宽到10%实体板即可
    "pullback_ratio_min": 0.03,          # 放宽到3%回调
    "pullback_ratio_max": 0.35,          # 放宽到35%
    "min_pullback_days": 1,              # 回调1天即可
    "ma_stabilize": 10,
    "volume_shrink_ratio": 0.8,          # 大幅放宽量能要求
    "volume_compare_days": 3,
    "signal_today_yang": False,          # 不要求阳线
    "signal_volume_expand": 0.8,         # 不要求放量，缩量也行
}

# 超宽松参数（找任何有连板回调迹象的）
ULTRA_LOOSE = {
    "min_consecutive_limit_up": 2,
    "min_entity_board_ratio": 0.0,       # 不要求实体板
    "pullback_ratio_min": 0.01,           # 回调1%就算
    "pullback_ratio_max": 0.40,
    "min_pullback_days": 1,
    "ma_stabilize": 5,                    # 5日均线
    "volume_shrink_ratio": 1.5,           # 不限制量能
    "volume_compare_days": 3,
    "signal_today_yang": False,
    "signal_volume_expand": 0.0,
}

def quick_screen_with_params(params, name="默认"):
    """用指定参数筛选"""
    print(f"\n{'='*60}")
    print(f"使用 {name} 参数筛选")
    print(f"{'='*60}")
    
    test_codes = [
        '301235.SZ', '301248.SZ', '600156.SS', '002971.SZ', '600707.SS',
        '002871.SZ', '600135.SS', '002812.SZ', '688539.SS', '688268.SS'
    ]
    
    results = []
    
    for i in range(0, len(test_codes), 5):
        batch = test_codes[i:i+5]
        hist = yf.download(tickers=batch, period="30d", progress=False)
        if hist is None or hist.empty:
            continue
        try:
            codes_in_batch = set(hist.columns.get_level_values(1))
        except Exception:
            codes_in_batch = set()
        
        for code in batch:
            if codes_in_batch and code not in codes_in_batch:
                continue
            try:
                stock_data = hist.xs(code, level=1, axis=1)
                close = stock_data['Close'].dropna()
                open_price = stock_data['Open'].dropna()
                high = stock_data['High'].dropna()
                volume = stock_data['Volume'].dropna()
                
                if len(close) < 10:
                    continue
                
                df = pd.DataFrame({
                    'close': close.values,
                    'open': open_price.values,
                    'high': high.values,
                    'volume': volume.values,
                })
                
                df['pct_chg'] = df['close'].pct_change() * 100
                df = df.dropna().reset_index(drop=True)
                
                # 涨停阈值
                limit_threshold = 18.5 if code.startswith(('30', '688')) else 9.5
                df['is_limit_up'] = df['pct_chg'] >= limit_threshold
                df['is_one_word'] = (df['open'] == df['high']) & df['is_limit_up']
                
                # 找连板
                limit_idx = df[df['is_limit_up']].index.tolist()
                if len(limit_idx) < params['min_consecutive_limit_up']:
                    continue
                
                # 找最后一组
                groups = []
                current = [limit_idx[0]]
                for j in range(1, len(limit_idx)):
                    if limit_idx[j] == limit_idx[j-1] + 1:
                        current.append(limit_idx[j])
                    else:
                        if len(current) >= params['min_consecutive_limit_up']:
                            groups.append(current)
                        current = [limit_idx[j]]
                if len(current) >= params['min_consecutive_limit_up']:
                    groups.append(current)
                
                if not groups:
                    continue
                
                latest = groups[-1]
                entity_ratio = sum(1 for j in latest if not df.iloc[j]['is_one_word']) / len(latest)
                
                if entity_ratio < params['min_entity_board_ratio']:
                    continue
                
                last_limit = latest[-1]
                today = len(df) - 1
                
                if today - last_limit < params['min_pullback_days']:
                    continue
                
                highest = max(df.iloc[j]['high'] for j in latest)
                current_price = df.iloc[today]['close']
                pullback = (highest - current_price) / highest
                
                if pullback < params['pullback_ratio_min'] or pullback > params['pullback_ratio_max']:
                    continue
                
                # 均线
                ma_period = params['ma_stabilize']
                if today >= ma_period:
                    ma = df.iloc[today-ma_period+1:today+1]['close'].mean()
                    if current_price < ma:
                        continue
                
                # 阳线
                if params['signal_today_yang'] and df.iloc[today]['close'] <= df.iloc[today]['open']:
                    continue
                
                # 量能
                if params['signal_volume_expand'] > 0 and today > 0:
                    vol_ratio = df.iloc[today]['volume'] / df.iloc[today-1]['volume']
                    if vol_ratio < params['signal_volume_expand']:
                        continue
                
                results.append({
                    'code': code,
                    'pullback': round(pullback * 100, 1),
                    'limit_days': len(latest),
                    'current_price': round(current_price, 2),
                    'highest': round(highest, 2)
                })
                
            except:
                continue
    
    # 输出结果
    print(f"\n找到 {len(results)} 只候选股票:")
    for r in results:
        print(f"  {r['code']} | 回调 {r['pullback']}% | "
              f"连板 {r['limit_days']}天 | "
              f"现价 {r['current_price']} (高点 {r['highest']})")
    
    return results

if __name__ == "__main__":
    # 测试不同参数
    quick_screen_with_params(LOOSE_PARAMS, "宽松参数")
    quick_screen_with_params(ULTRA_LOOSE, "超宽松参数")