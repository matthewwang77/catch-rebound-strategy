import yfinance as yf
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "stock_data")
cache_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
codes = [f.replace('.csv', '') for f in cache_files]

# 测试第一批200只
batch = codes[:200]
hist = yf.download(tickers=batch, period="5d", progress=False)

# 看看实际下载到了多少只
if hist is not None and not hist.empty:
    try:
        valid = set(hist.columns.get_level_values(1))
        print(f"请求 {len(batch)} 只，实际获取 {len(valid)} 只")
    except Exception as e:
        print(f"列解析失败: {e}")
else:
    print("批量下载完全失败")
