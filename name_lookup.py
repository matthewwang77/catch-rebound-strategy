"""
股票名称查询模块
优先使用中文名文件（stock_names_cn.csv），其次本地缓存，最后 yfinance。
"""
import yfinance as yf
import pandas as pd
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
NAME_CACHE_FILE = os.path.join(BASE, "name_cache.csv")
CN_NAMES_FILE = os.path.join(BASE, "stock_names_cn.csv")

# ---- 中文名映射（模块加载时读取）----
_cn_names = {}
if os.path.exists(CN_NAMES_FILE):
    try:
        df_cn = pd.read_csv(CN_NAMES_FILE)
        for _, row in df_cn.iterrows():
            _cn_names[row['code']] = str(row['name'])
    except Exception:
        pass


def _get_cn_name(code):
    """从中文名文件获取名称"""
    return _cn_names.get(code, '')


def load_name_cache():
    """加载缓存的名称/板块数据"""
    if os.path.exists(NAME_CACHE_FILE) and os.path.getsize(NAME_CACHE_FILE) > 10:
        try:
            df = pd.read_csv(NAME_CACHE_FILE)
            if len(df) > 0:
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=['code', 'name'])


def save_name_cache(df):
    """保存名称缓存"""
    df.to_csv(NAME_CACHE_FILE, index=False, encoding='utf-8-sig')


def lookup_code(code, cache_df=None):
    """
    查询单只股票的名称。
    优先级：中文名文件 > 缓存 > yfinance

    返回 dict: {code, name}
    """
    # 1. 中文名文件
    cn_name = _get_cn_name(code)

    # 2. 缓存
    if cache_df is not None:
        match = cache_df[cache_df['code'] == code]
        if len(match) > 0:
            cached = match.iloc[0].to_dict()
            if cn_name:
                cached['name'] = cn_name
            if cached.get('name'):
                return cached

    # 3. yfinance 查询
    try:
        ticker = yf.Ticker(code)
        info = ticker.info

        name = cn_name or info.get('longName', info.get('shortName', ''))
        result = {'code': code, 'name': name}

        # 自动缓存
        if name:
            updated_cache = load_name_cache()
            updated_cache = pd.concat([updated_cache, pd.DataFrame([result])], ignore_index=True)
            updated_cache = updated_cache.drop_duplicates(subset=['code'], keep='last')
            save_name_cache(updated_cache)

        return result
    except Exception:
        return {'code': code, 'name': cn_name}


def batch_lookup(codes, max_fetch=20):
    """
    批量查询多只股票的名称。
    优先中文名文件 > 缓存 > yfinance。

    返回 dict: {code: {name}}
    """
    cache_df = load_name_cache()
    results = {}
    missing = []

    for code in codes:
        cn_name = _get_cn_name(code)
        match = cache_df[cache_df['code'] == code]
        if len(match) > 0 and isinstance(match.iloc[0].get('name', ''), str) and match.iloc[0]['name']:
            r = match.iloc[0].to_dict()
            if cn_name:
                r['name'] = cn_name
            results[code] = r
        elif cn_name:
            results[code] = {'code': code, 'name': cn_name}
        else:
            missing.append(code)

    # 缺失的逐只查询 yfinance
    fetch_count = 0
    for code in missing:
        if fetch_count >= max_fetch:
            results[code] = {'code': code, 'name': ''}
            continue

        try:
            ticker = yf.Ticker(code)
            info = ticker.info
            result = {
                'code': code,
                'name': info.get('longName', info.get('shortName', '')),
            }
            results[code] = result
            fetch_count += 1
            time.sleep(0.3)
        except Exception:
            results[code] = {'code': code, 'name': ''}

    # 保存缓存
    new_rows = [r for r in results.values() if r.get('name')]
    if new_rows:
        cache_df = pd.concat([cache_df, pd.DataFrame(new_rows)], ignore_index=True)
        cache_df = cache_df.drop_duplicates(subset=['code'], keep='last')
        save_name_cache(cache_df)

    return results


