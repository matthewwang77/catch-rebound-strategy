"""
补充股票板块到 stock_names_cn.csv（腾讯API）
"""
import pandas as pd, requests, time

df = pd.read_csv("stock_names_cn.csv")
if 'sector_cn' not in df.columns:
    df['sector_cn'] = ''

# 腾讯API字段: 第14位是行业
BATCH = 60
updated = 0
for i in range(0, len(df), BATCH):
    batch = df.iloc[i:i+BATCH]
    qt = []
    code_map = {}
    for _, row in batch.iterrows():
        c = row['code']
        qt_code = f"sh{c[:6]}" if c.endswith('.SS') else f"sz{c[:6]}"
        qt.append(qt_code)
        code_map[qt_code] = c

    try:
        url = f"http://qt.gtimg.cn/q={','.join(qt)}"
        resp = requests.get(url, timeout=15)
        resp.encoding = 'gbk'
        for line in resp.text.strip().split('\n'):
            if '~' not in line: continue
            parts = line.split('~')
            if len(parts) < 15: continue
            # 提取代码和行业
            raw_code = parts[2]
            industry = parts[13] if len(parts) > 13 else ''
            if raw_code and industry and industry.strip():
                suffix = '.SS' if raw_code.startswith('6') else '.SZ'
                full_code = f'{raw_code}{suffix}'
                idx = df[df['code'] == full_code].index
                if len(idx) > 0:
                    df.at[idx[0], 'sector_cn'] = industry.strip()
                    updated += 1
    except Exception as e:
        pass
    time.sleep(0.2)
    if i % 2000 == 0:
        print(f"  {i}/{len(df)}... 已更新{updated}")

df.to_csv('stock_names_cn.csv', index=False, encoding='utf-8-sig')
has = (df['sector_cn'] != '').sum()
print(f"✅ 有板块: {has}/{len(df)}")
if has > 0:
    print(df[df['sector_cn']!=''][['code','name','sector_cn']].head(10).to_string())
