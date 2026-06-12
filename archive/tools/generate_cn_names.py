"""
生成 A 股中文名映射文件 — 使用腾讯财经 API
"""
import requests, time, pandas as pd, os

# 从本地 stock_data 已有CSV获取代码列表
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock_data")
codes = []
for f in os.listdir(DATA_DIR):
    if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100:
        codes.append(f.replace('.csv', ''))

print(f"本地已有 {len(codes)} 只股票的CSV数据")

# 腾讯行情API：一次最多约60只
# 格式: sh600000,sz000001
result = []
BATCH = 50

for i in range(0, len(codes), BATCH):
    batch = codes[i:i+BATCH]
    # 转换为腾讯格式
    qt_codes = []
    for c in batch:
        if c.endswith('.SS'):
            qt_codes.append(f"sh{c[:6]}")
        elif c.endswith('.SZ'):
            qt_codes.append(f"sz{c[:6]}")

    if not qt_codes:
        continue

    url = f"http://qt.gtimg.cn/q={','.join(qt_codes)}"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = 'gbk'
        for line in resp.text.strip().split('\n'):
            if '~' not in line:
                continue
            parts = line.split('~')
            if len(parts) >= 2:
                raw_code = parts[2] if len(parts) > 2 else ''
                name = parts[1] if len(parts) > 1 else ''
                if raw_code and name:
                    suffix = '.SS' if raw_code.startswith('6') else '.SZ'
                    result.append({'code': f'{raw_code}{suffix}', 'name': name})
    except Exception as e:
        print(f"  批次 {i//BATCH + 1} 失败: {e}")

    if (i // BATCH + 1) % 20 == 0:
        print(f"  已处理 {i+len(batch)}/{len(codes)} 只...")
    time.sleep(0.2)

df = pd.DataFrame(result)
df = df.drop_duplicates(subset=['code'], keep='last')
df.to_csv('stock_names_cn.csv', index=False, encoding='utf-8-sig')
print(f'\n✅ {len(df)} 只A股中文名 → stock_names_cn.csv')
print(df.head(10).to_string())
