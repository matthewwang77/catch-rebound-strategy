"""
生成 A 股中文名映射文件
在你的 Mac 上运行：python3 generate_cn_names.py
"""
import requests
import pandas as pd
import json
import time

all_stocks = []

for page in [1, 2, 3, 4, 5]:
    url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn={page}&pz=1000&po=1&np=1&fltt=2&invt=2"
        "&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
        "&fields=f12,f14"
    )
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=15,
        )
        text = resp.text
        if text.startswith("jQuery"):
            text = text[text.index("(") + 1 : text.rindex(")")]
        data = json.loads(text)
        items = data.get("data", {}).get("diff", [])
        for item in items:
            raw = item["f12"]
            suffix = ".SS" if raw.startswith("6") else ".SZ"
            all_stocks.append({"code": f"{raw}{suffix}", "name": item["f14"]})
        print(f"  第{page}页: {len(items)} 只")
    except Exception as e:
        print(f"  第{page}页失败: {e}")
    time.sleep(0.3)

df = pd.DataFrame(all_stocks)
df.to_csv("stock_names_cn.csv", index=False, encoding="utf-8-sig")
print(f"\n✅ 共 {len(df)} 只A股中文名 → stock_names_cn.csv")
print(df.head(10).to_string())
