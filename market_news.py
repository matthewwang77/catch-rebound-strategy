#!/usr/bin/env python3
"""
市场新闻模块：多源获取 + AI筛选分析 + 存储 + 注入选股prompt

数据源: 东方财富(AKShare) + 财联社(CLS API) + Yahoo Finance(yfinance)
输出: market_news.json (最新) + news_archive/YYYYMMDD.json (历史归档)
"""

import json
import os
import re
import time
import requests

from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
NEWS_JSON_PATH = os.path.join(BASE_DIR, "market_news.json")
NEWS_ARCHIVE_DIR = os.path.join(BASE_DIR, "news_archive")

# ── A股相关性关键词（用于预过滤） ──
RELEVANCE_KEYWORDS = [
    "A股", "上证", "深证", "创业板", "科创", "北交所", "大盘",
    "央行", "降息", "降准", "MLF", "LPR", "利率", "逆回购",
    "板块", "涨停", "跌停", "成交额", "北上资金", "外资", "主力",
    "人民币", "汇率", "PMI", "CPI", "GDP", "社融", "M2",
    "新能源", "半导体", "芯片", "消费", "医药", "地产", "汽车",
    "证券", "保险", "银行", "煤炭", "有色", "军工", "白酒",
    "人工智能", "算力", "机器人", "低空", "固态电池",
    "证监会", "国务院", "财政部", "发改委", "工信部",
    "ETF", "基金", "增持", "减持", "回购",
    "关税", "贸易", "制裁", "出口", "进口",
]


# ──────────────────────────────────────────────
# 数据获取
# ──────────────────────────────────────────────

def fetch_news_eastmoney() -> list[dict]:
    """从东方财富7x24快讯获取今日新闻（via AKShare）。

    Returns:
        标准化新闻列表: [{title, summary, time, source, url}, ...]
        失败时返回空列表。
    """
    try:
        import akshare as ak
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return []

        today_str = datetime.now().strftime("%Y-%m-%d")
        results = []
        for _, row in df.iterrows():
            title = str(row.get("标题", "")).strip()
            summary = str(row.get("摘要", "")).strip()
            time_str = str(row.get("发布时间", "")).strip()

            if not title:
                continue

            # 只保留今天的新闻
            if time_str and today_str not in time_str:
                continue

            results.append({
                "title": title,
                "summary": summary,
                "time": time_str,
                "source": "东方财富",
                "url": "https://finance.eastmoney.com/",
            })

        return results[:60]  # 上限60条
    except Exception as e:
        print(f"  [market_news] 东方财富获取失败: {e}")
        return []


def fetch_news_cls() -> list[dict]:
    """从财联社获取今日快讯（直接API调用，无需akshare）。

    Returns:
        标准化新闻列表，失败时返回空列表。
    """
    try:
        url = "https://www.cls.cn/v1/roll/get_roll_list"
        params = {"app": "CailianpressWeb", "os": "web", "rn": 30}
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.cls.cn/",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        roll_data = data.get("data", {}).get("roll_data", [])
        if not roll_data:
            return []

        today_str = datetime.now().strftime("%Y-%m-%d")
        results = []
        for item in roll_data:
            title = str(item.get("title", "")).strip()
            content = str(item.get("content", "")).strip()
            ctime = item.get("ctime", 0)  # Unix timestamp

            if not title:
                continue

            # 转换时间戳
            try:
                time_str = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError):
                time_str = ""

            # 只保留今天的
            if time_str and today_str not in time_str:
                continue

            news_id = str(item.get("id", ""))
            url = f"https://www.cls.cn/detail/{news_id}" if news_id else "https://www.cls.cn/"

            results.append({
                "title": title,
                "summary": content[:300] if content else "",
                "time": time_str,
                "source": "财联社",
                "url": url,
            })

        return results[:30]
    except Exception as e:
        print(f"  [market_news] 财联社获取失败: {e}")
        return []


def fetch_news_yahoo() -> list[dict]:
    """从Yahoo Finance获取中国市场相关新闻（英文）。

    Returns:
        标准化新闻列表，失败时返回空列表。
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker("000001.SS")
        raw = ticker.news
        if not raw:
            return []

        results = []
        cutoff = time.time() - 86400  # 24小时内

        for item in raw:
            title = str(item.get("title", "")).strip()
            publisher = item.get("publisher", "Yahoo")
            link = item.get("link", "")
            pub_time = item.get("providerPublishTime", 0)

            if not title:
                continue

            # 过滤太旧的
            if pub_time and pub_time < cutoff:
                continue

            try:
                time_str = datetime.fromtimestamp(int(pub_time)).strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError):
                time_str = ""

            summary = ""
            if "summary" in item:
                summary = str(item["summary"])[:300]

            results.append({
                "title": title,
                "summary": summary,
                "time": time_str,
                "source": f"Yahoo/{publisher}",
                "url": link,
            })

        return results[:15]
    except Exception as e:
        print(f"  [market_news] Yahoo Finance获取失败: {e}")
        return []


# ──────────────────────────────────────────────
# 预处理
# ──────────────────────────────────────────────

def _prefilter_news(news_list: list[dict]) -> list[dict]:
    """关键词预过滤：只保留与A股市场相关的新闻。

    Args:
        news_list: 原始新闻列表

    Returns:
        过滤后的新闻列表（至少匹配一个关键词）。
    """
    if not news_list:
        return []

    filtered = []
    for item in news_list:
        text = (item.get("title", "") + " " + item.get("summary", "")).lower()
        for kw in RELEVANCE_KEYWORDS:
            if kw.lower() in text:
                filtered.append(item)
                break

    return filtered


def deduplicate_news(news_list: list[dict]) -> list[dict]:
    """标题相似度去重。两条标题共享 >70% 词汇时视为重复，保留摘要更长的一条。

    Args:
        news_list: 新闻列表

    Returns:
        去重后的新闻列表。
    """
    if len(news_list) <= 1:
        return news_list

    def _tokenize(title: str) -> set[str]:
        """简单分词：按2-gram切割中文字符。"""
        chars = re.findall(r"[一-鿿]+", title)
        text = "".join(chars)
        # 2-gram
        grams = {text[i : i + 2] for i in range(len(text) - 1)} if len(text) >= 2 else {text}
        return grams

    # 按摘要长度降序排列（优先保留内容更丰富的）
    sorted_news = sorted(news_list, key=lambda x: len(x.get("summary", "")), reverse=True)
    kept = []

    for item in sorted_news:
        title = item.get("title", "")
        tokens = _tokenize(title)
        if not tokens:
            kept.append(item)
            continue

        is_dup = False
        for existing in kept:
            existing_tokens = _tokenize(existing.get("title", ""))
            if not existing_tokens:
                continue
            # Jaccard 相似度
            overlap = len(tokens & existing_tokens)
            union = len(tokens | existing_tokens)
            if union > 0 and overlap / union > 0.7:
                is_dup = True
                break

        if not is_dup:
            kept.append(item)

    return kept


# ──────────────────────────────────────────────
# AI 分析
# ──────────────────────────────────────────────

def ai_select_and_analyze_news(news_list: list[dict]) -> dict | None:
    """调用 DeepSeek 从新闻列表中选出对A股影响最大的10条，并逐一分析。

    Args:
        news_list: 预处理后的新闻列表（建议20-80条）

    Returns:
        符合 market_news.json 结构的数据，AI调用失败返回 None。
    """
    if not news_list or len(news_list) < 3:
        print("  [market_news] 新闻数量不足（<3），跳过AI分析")
        return None

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("  [market_news] DEEPSEEK_API_KEY 未设置，跳过AI分析")
        return None

    # 格式化新闻列表
    news_text_parts = []
    for i, item in enumerate(news_list, 1):
        source = item.get("source", "未知")
        title = item.get("title", "")
        summary = item.get("summary", "")[:200]
        time_str = item.get("time", "")
        news_text_parts.append(
            f"{i}. [{source}] {time_str}\n   标题：{title}\n   摘要：{summary}"
        )

    news_text = "\n".join(news_text_parts)

    prompt = f"""你是一名A股市场新闻分析师。从以下今日快讯中，选出对A股市场影响最大的10条新闻，并对每条进行深度分析。

筛选标准：
- 对大盘指数（上证/深证/创业板）有直接影响的政策、数据、事件优先
- 对具体行业板块有重大影响的新闻次之
- 外资动向、资金流向类信息值得关注
- 避免：个股公告类（除非是超大市值龙头如茅台、宁德时代级别）

请以严格JSON格式输出（不要markdown代码块，不要其他文字）：

{{
  "market_summary": "一段话总结今日整体市场消息面，2-3句话",
  "sentiment_impact": "偏多/偏空/中性",
  "news": [
    {{
      "index": 1,
      "ai_summary": "一句话概括（20字以内）",
      "impact_analysis": "对A股市场的影响分析（80字以内）",
      "affected_sectors": ["板块1", "板块2"],
      "affected_stocks": ["000001.SZ", "600000.SS"],
      "importance": 9
    }}
  ]
}}

importance 1-10: 10=超级重磅（降息降准/重大政策转向），5=中等影响，1=边角料。

现在开始筛选：

{news_text}"""

    # 尝试导入 screener 获取 API URL
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "screener", os.path.join(BASE_DIR, "选股new_v5.py")
        )
        screener = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(screener)
        api_url = getattr(screener, "DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    except Exception:
        api_url = "https://api.deepseek.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是A股市场新闻分析师。只输出JSON，不要其他内容。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 3000,
    }

    for attempt in range(2):
        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            body = resp.json()
            content = body["choices"][0]["message"]["content"].strip()

            # 尝试直接解析JSON
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # 尝试从 markdown 代码块提取
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
                if match:
                    result = json.loads(match.group(1))
                else:
                    # 尝试找到第一个 { 到最后一个 }
                    match = re.search(r"\{.*\}", content, re.DOTALL)
                    if match:
                        result = json.loads(match.group(0))
                    else:
                        print(f"  [market_news] AI返回无法解析JSON (attempt {attempt+1})")
                        if attempt == 0:
                            continue
                        return None

            # 后处理：用 index 匹配回原始新闻的 title/url/time
            news_out = result.get("news", [])
            enriched = []
            for item in news_out:
                idx = item.get("index", 0) - 1  # 1-based → 0-based
                if 0 <= idx < len(news_list):
                    original = news_list[idx]
                    enriched.append({
                        "title": original.get("title", ""),
                        "source": original.get("source", ""),
                        "url": original.get("url", ""),
                        "time": original.get("time", ""),
                        "ai_summary": item.get("ai_summary", ""),
                        "impact_analysis": item.get("impact_analysis", ""),
                        "affected_sectors": item.get("affected_sectors", []),
                        "affected_stocks": item.get("affected_stocks", []),
                        "importance": item.get("importance", 5),
                    })

            # 按 importance 降序
            enriched.sort(key=lambda x: x.get("importance", 0), reverse=True)

            return {
                "date": datetime.now().strftime("%Y%m%d"),
                "market_summary": result.get("market_summary", ""),
                "sentiment_impact": result.get("sentiment_impact", "中性"),
                "news": enriched[:10],
            }

        except Exception as e:
            print(f"  [market_news] AI调用失败 (attempt {attempt+1}): {e}")
            if attempt == 0:
                time.sleep(3)
            else:
                return None

    return None


def get_news_context_for_prompt() -> str | None:
    """构建注入选股AI prompt的新闻摘要。

    Returns:
        格式化文本（~500字）或 None（无新闻数据时）。
    """
    news_data = load_market_news()
    if not news_data:
        return None

    parts = []
    parts.append("【今日要闻】")

    summary = news_data.get("market_summary", "")
    sentiment = news_data.get("sentiment_impact", "中性")
    if summary:
        parts.append(f"整体来看，{summary}（消息面情绪：{sentiment}）")

    all_news = news_data.get("news", [])
    if all_news:
        parts.append("\n重点新闻：")
        for i, item in enumerate(all_news[:5], 1):
            title = item.get("title", "")
            ai_summary = item.get("ai_summary", "")
            sectors = "、".join(item.get("affected_sectors", [])[:3])
            impact = item.get("impact_analysis", "")
            # 截断太长的 impact
            if len(impact) > 60:
                impact = impact[:60] + "..."

            line = f"{i}. [{item.get('source', '')}] {title}"
            if ai_summary:
                line += f" — {ai_summary}"
            if sectors:
                line += f" | 影响: {sectors}"
            parts.append(line)

    return "\n".join(parts)


# ──────────────────────────────────────────────
# 存储
# ──────────────────────────────────────────────

def save_market_news(news_data: dict):
    """保存新闻数据到 market_news.json 和 news_archive/。

    Args:
        news_data: 符合数据结构的新闻数据
    """
    os.makedirs(NEWS_ARCHIVE_DIR, exist_ok=True)

    json_str = json.dumps(news_data, ensure_ascii=False, indent=2)

    # 原子写入最新文件
    tmp_path = NEWS_JSON_PATH + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(json_str)
        os.replace(tmp_path, NEWS_JSON_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    # 归档
    date_str = news_data.get("date", datetime.now().strftime("%Y%m%d"))
    archive_path = os.path.join(NEWS_ARCHIVE_DIR, f"{date_str}.json")
    try:
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(json_str)
    except Exception as e:
        print(f"  [market_news] 归档失败: {e}")


def load_market_news() -> dict | None:
    """加载最新的市场新闻。

    Returns:
        新闻数据字典，文件不存在或日期不匹配时返回 None。
    """
    if not os.path.exists(NEWS_JSON_PATH):
        return None

    try:
        with open(NEWS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # 检查是否为今日数据
    today = datetime.now().strftime("%Y%m%d")
    if data.get("date", "") != today:
        return None

    return data
