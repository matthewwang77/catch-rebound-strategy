"""
补充股票板块信息到 stock_names_cn.csv
需要国内网络，在你的 Mac 上运行。
"""
import pandas as pd
import json
import requests
import time

# 读取现有中文名
df = pd.read_csv("stock_names_cn.csv")
print(f"现有 {len(df)} 只")

# 用东方财富API批量获取板块
# 每次取500只
all_data = []
for i in range(0, len(df), 200):
    batch = df.iloc[i:i+200]
    codes_str = ",".join(batch['code'].str.replace('.SS','.SH').str.replace('.SZ','.SZ'))
    # 转为东方财富格式
    em_codes = []
    for _, row in batch.iterrows():
        code = row['code']
        if code.endswith('.SS'):
            em_codes.append(f"1.{code[:6]}")
        else:
            em_codes.append(f"0.{code[:6]}")

    try:
        url = f"http://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f12,f14,f100&secids={','.join(em_codes[:100])}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = resp.json()
        if data and 'data' in data and data['data'] and 'diff' in data['data']:
            for item in data['data']['diff']:
                raw = item['f12']
                suffix = '.SS' if raw.startswith('6') else '.SZ'
                all_data.append({
                    'code': f'{raw}{suffix}',
                    'name': item.get('f14', ''),
                    'sector_cn': item.get('f100', '')
                })
    except Exception as e:
        print(f"  批次{i}失败: {e}")
    time.sleep(0.3)
    if i % 1000 == 0:
        print(f"  已处理 {i}...")

if all_data:
    df_new = pd.DataFrame(all_data)
    # 合并到现有
    df_out = df.merge(df_new[['code','sector_cn']], on='code', how='left')
    df_out['sector_cn'] = df_out['sector_cn'].fillna('')
    df_out.to_csv('stock_names_cn.csv', index=False, encoding='utf-8-sig')
    has_sector = (df_out['sector_cn'] != '').sum()
    print(f"✅ 更新完成: {has_sector}/{len(df_out)} 只有板块")
else:
    print("❌ 未获取到板块数据")
