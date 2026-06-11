"""
生成 A 股中文名映射文件
在你的 Mac 上运行：python3 generate_cn_names.py
"""
try:
    import akshare as ak
    import pandas as pd

    # 获取沪深A股实时行情（含中文名）
    print("正在从东方财富获取A股列表...")
    df = ak.stock_zh_a_spot_em()
    print(f"  获取到 {len(df)} 只股票")

    result = []
    for _, row in df.iterrows():
        code = str(row['代码'])
        if code.startswith('6'):
            full_code = f'{code}.SS'
        elif code.startswith(('0', '3')):
            full_code = f'{code}.SZ'
        else:
            continue
        result.append({'code': full_code, 'name': str(row['名称'])})

    df_out = pd.DataFrame(result)
    df_out.to_csv('stock_names_cn.csv', index=False, encoding='utf-8-sig')
    print(f'✅ 沪深A股: {len(df_out)} 只 → stock_names_cn.csv')
    print(df_out.head(10).to_string())

except ImportError:
    print("正在安装 akshare...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "akshare", "-q"])
    print("安装完成，请重新运行 python3 generate_cn_names.py")
