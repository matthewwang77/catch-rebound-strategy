"""
股票名称和板块查询模块（本地缓存）
首次查询走 yfinance API，后续从本地 CSV 缓存秒读
"""
import yfinance as yf
import pandas as pd
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
NAME_CACHE_FILE = os.path.join(BASE, "name_cache.csv")


def load_name_cache():
    """加载缓存的名称/板块数据"""
    if os.path.exists(NAME_CACHE_FILE) and os.path.getsize(NAME_CACHE_FILE) > 10:
        try:
            df = pd.read_csv(NAME_CACHE_FILE)
            if len(df) > 0:
                return df
        except Exception:
            pass
    return pd.DataFrame(columns=['code', 'name', 'sector', 'industry', 'market_cap'])


def save_name_cache(df):
    """保存名称缓存"""
    df.to_csv(NAME_CACHE_FILE, index=False, encoding='utf-8-sig')


def lookup_code(code, cache_df=None):
    """
    查询单只股票的名称和板块信息。
    先查缓存，缓存无则调 yfinance，结果自动缓存。

    返回 dict: {code, name, sector, industry, market_cap}
    """
    if cache_df is not None:
        match = cache_df[cache_df['code'] == code]
        if len(match) > 0 and isinstance(match.iloc[0].get('name', ''), str) and match.iloc[0]['name']:
            return match.iloc[0].to_dict()

    try:
        ticker = yf.Ticker(code)
        info = ticker.info

        result = {
            'code': code,
            'name': info.get('longName', info.get('shortName', '')),
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            'market_cap': info.get('marketCap', 0),
        }

        # 自动缓存
        updated_cache = load_name_cache()
        updated_cache = pd.concat([updated_cache, pd.DataFrame([result])], ignore_index=True)
        updated_cache = updated_cache.drop_duplicates(subset=['code'], keep='last')
        save_name_cache(updated_cache)

        return result
    except Exception:
        return {'code': code, 'name': '', 'sector': '', 'industry': '', 'market_cap': 0}


def batch_lookup(codes, max_fetch=20):
    """
    批量查询多只股票的名称和板块。
    优先从缓存读取，缺失的逐只调用 yfinance（限速）。

    参数:
        codes: 股票代码列表
        max_fetch: 最多新抓取数量（避免触发限速）

    返回 dict: {code: {name, sector, industry, market_cap}}
    """
    cache_df = load_name_cache()
    results = {}
    missing = []

    # 先从缓存获取
    for code in codes:
        match = cache_df[cache_df['code'] == code]
        if len(match) > 0 and isinstance(match.iloc[0].get('name', ''), str) and match.iloc[0]['name']:
            results[code] = match.iloc[0].to_dict()
        else:
            missing.append(code)

    # 缺失的逐只查询
    fetch_count = 0
    for code in missing:
        if fetch_count >= max_fetch:
            results[code] = {'code': code, 'name': '', 'sector': '', 'industry': '', 'market_cap': 0}
            continue

        try:
            ticker = yf.Ticker(code)
            info = ticker.info
            result = {
                'code': code,
                'name': info.get('longName', info.get('shortName', '')),
                'sector': info.get('sector', ''),
                'industry': info.get('industry', ''),
                'market_cap': info.get('marketCap', 0),
            }
            results[code] = result
            fetch_count += 1
            time.sleep(0.3)  # 限速
        except Exception:
            results[code] = {'code': code, 'name': '', 'sector': '', 'industry': '', 'market_cap': 0}

    # 保存缓存
    new_rows = [r for r in results.values() if r.get('name')]
    if new_rows:
        cache_df = pd.concat([cache_df, pd.DataFrame(new_rows)], ignore_index=True)
        cache_df = cache_df.drop_duplicates(subset=['code'], keep='last')
        save_name_cache(cache_df)

    return results


def get_sector_display(code, cache_df=None):
    """
    获取单只股票的简短显示信息。

    返回: (名称, 板块) 元组
    """
    info = lookup_code(code, cache_df)
    name = info.get('name', '') or ''
    sector = info.get('sector', '') or info.get('industry', '') or ''
    return name, sector
