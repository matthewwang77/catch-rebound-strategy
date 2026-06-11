"""
股票名称和板块查询模块
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
        # 如果有板块列，也加载
        if 'sector_cn' in df_cn.columns:
            for _, row in df_cn.iterrows():
                _cn_names[row['code']] = str(row['name'])
    except Exception:
        pass

# ---- 板块英文→中文翻译 ----
_SECTOR_CN = {
    "Real Estate": "房地产",
    "Technology": "科技",
    "Financial Services": "金融服务",
    "Basic Materials": "基础材料",
    "Industrials": "工业",
    "Consumer Cyclical": "周期性消费",
    "Consumer Defensive": "防御性消费",
    "Healthcare": "医疗保健",
    "Energy": "能源",
    "Utilities": "公用事业",
    "Communication Services": "通信服务",
    "Banks - Regional": "区域银行",
    "Banks - Diversified": "综合银行",
    "Chemicals": "化工",
    "Drug Manufacturers": "制药",
    "Software": "软件",
    "Hardware": "硬件",
    "Semiconductors": "半导体",
    "Auto Manufacturers": "汽车制造",
    "Building Materials": "建材",
    "Metals & Mining": "金属矿业",
    "Oil & Gas": "石油天然气",
    "Insurance": "保险",
    "Telecom": "电信",
    "Transportation": "交通运输",
    "Food": "食品",
    "Beverages": "饮料",
    "Textiles": "纺织",
    "Machinery": "机械",
    "Electrical": "电气设备",
    "Construction": "建筑工程",
    "Pharmaceuticals": "医药",
    "Medical Devices": "医疗器械",
    "Biotechnology": "生物科技",
    "Aerospace & Defense": "航天国防",
    "Electronic Components": "电子元器件",
    "Steel": "钢铁",
    "Coal": "煤炭",
    "Paper": "造纸",
    "Agriculture": "农业",
    "Retail": "零售",
    "Entertainment": "娱乐",
    "Media": "传媒",
    "Education": "教育",
    "Environmental": "环保",
    "Real Estate Services": "房地产服务",
    "Restaurants": "餐饮",
    "Hotels": "酒店",
    "Tobacco": "烟草",
    "Packaging": "包装",
    "Medical Care": "医疗服务",
    "Information Technology": "信息技术",
    "Furnishings": "家具",
    "Apparel": "服装",
    "Travel": "旅游",
    "Logistics": "物流",
    "Shipping": "航运",
    "Railways": "铁路",
    "Aviation": "航空",
}


def _translate_sector(sector, industry):
    """将英文板块/行业翻译成中文"""
    parts = []
    if sector and sector in _SECTOR_CN:
        parts.append(_SECTOR_CN[sector])
    elif sector:
        parts.append(sector)  # 没翻译就用英文
    if industry and industry in _SECTOR_CN:
        parts.append(_SECTOR_CN[industry])
    elif industry:
        parts.append(industry)
    return " / ".join(parts) if parts else ""


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
    return pd.DataFrame(columns=['code', 'name', 'sector', 'industry', 'market_cap'])


def save_name_cache(df):
    """保存名称缓存"""
    df.to_csv(NAME_CACHE_FILE, index=False, encoding='utf-8-sig')


def lookup_code(code, cache_df=None):
    """
    查询单只股票的名称和板块信息。
    优先级：中文名文件 > 缓存 > yfinance

    返回 dict: {code, name, sector, industry, market_cap}
    """
    # 1. 中文名文件
    cn_name = _get_cn_name(code)

    # 2. 缓存（板块信息）
    if cache_df is not None:
        match = cache_df[cache_df['code'] == code]
        if len(match) > 0:
            cached = match.iloc[0].to_dict()
            if cn_name:
                cached['name'] = cn_name  # 用中文名覆盖
            if cached.get('name'):
                return cached

    # 3. yfinance 查询
    try:
        ticker = yf.Ticker(code)
        info = ticker.info

        name = cn_name or info.get('longName', info.get('shortName', ''))
        sector_en = info.get('sector', '')
        industry_en = info.get('industry', '')
        result = {
            'code': code,
            'name': name,
            'sector': sector_en,
            'sector_cn': _translate_sector(sector_en, industry_en),
            'industry': industry_en,
            'market_cap': info.get('marketCap', 0),
        }

        # 自动缓存
        updated_cache = load_name_cache()
        updated_cache = pd.concat([updated_cache, pd.DataFrame([result])], ignore_index=True)
        updated_cache = updated_cache.drop_duplicates(subset=['code'], keep='last')
        save_name_cache(updated_cache)

        return result
    except Exception:
        return {'code': code, 'name': cn_name, 'sector': '', 'sector_cn': '', 'industry': '', 'market_cap': 0}


def batch_lookup(codes, max_fetch=20):
    """
    批量查询多只股票的名称和板块。
    优先中文名文件 > 缓存 > yfinance。

    返回 dict: {code: {name, sector, industry, market_cap}}
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
            # 有中文名但没有缓存，直接返回中文名
            results[code] = {'code': code, 'name': cn_name, 'sector': '', 'sector_cn': '', 'industry': '', 'market_cap': 0}
        else:
            missing.append(code)

    # 缺失的逐只查询 yfinance
    fetch_count = 0
    for code in missing:
        if fetch_count >= max_fetch:
            results[code] = {'code': code, 'name': '', 'sector': '', 'sector_cn': '', 'industry': '', 'market_cap': 0}
            continue

        try:
            ticker = yf.Ticker(code)
            info = ticker.info
            sector_en = info.get('sector', '')
            industry_en = info.get('industry', '')
            result = {
                'code': code,
                'name': info.get('longName', info.get('shortName', '')),
                'sector': sector_en,
                'sector_cn': _translate_sector(sector_en, industry_en),
                'industry': industry_en,
                'market_cap': info.get('marketCap', 0),
            }
            results[code] = result
            fetch_count += 1
            time.sleep(0.3)
        except Exception:
            results[code] = {'code': code, 'name': '', 'sector': '', 'sector_cn': '', 'industry': '', 'market_cap': 0}

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
