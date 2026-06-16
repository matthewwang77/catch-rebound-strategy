#!/usr/bin/env python3
"""
回填缺失的 AI 分析：从 signal_tracker.csv 读取所有信号，
对 ai_memory.json 中缺少真实分析的信号，按时间顺序逐一调用 DeepSeek。
同一股票的历史分析自动作为上下文注入后续分析。
"""

import json
import os
import sys
import time as _time
import re as _re
import pandas as pd
import requests
import importlib.util
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

# 加载 screener 模块
spec = importlib.util.spec_from_file_location("screener", os.path.join(BASE, "选股new_v5.py"))
screener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screener)

# 加载 market_news
import market_news

AI_MEMORY_FILE = os.path.join(BASE, "ai_memory.json")
SIGNAL_FILE = os.path.join(BASE, "signal_tracker.csv")
DATA_DIR = screener.DATA_DIR


def load_ai_memory():
    if not os.path.exists(AI_MEMORY_FILE):
        return {}
    try:
        with open(AI_MEMORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_ai_memory(memory):
    tmp_path = AI_MEMORY_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, AI_MEMORY_FILE)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def get_stock_memory_context(code, memory):
    """获取某股票的历史分析上下文（同 auto_daily.py 逻辑）"""
    if code not in memory or not memory[code]:
        return None
    records = memory[code]
    lines = ["[历史分析记录 · 含反思]"]
    has_mistakes = False
    success_lessons = []

    for rec in records[-5:]:
        sdate = rec.get("date", "未知")
        if len(sdate) == 8:
            sdate = f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}"
        sentiment = rec.get("sentiment", "")
        position = rec.get("position", "")
        opinion = rec.get("opinion", "")
        verdict = rec.get("verdict", "")
        ret7 = rec.get("return_7d")
        lesson = rec.get("lesson", "")

        summary_parts = [f"情绪:{sentiment}", f"仓位:{position}"]
        if opinion:
            summary_parts.append(f"结论:{opinion}")

        if verdict == "correct":
            summary_parts.append(f"策略 +{ret7}% ✅准确预判")
            if lesson:
                success_lessons.append(lesson)
        elif verdict == "wrong":
            has_mistakes = True
            summary_parts.append(f"策略 {ret7}% ❌判断失误")
        elif verdict == "missed":
            has_mistakes = True
            summary_parts.append(f"策略 +{ret7}% 🔶错失机会")
        elif verdict == "avoided":
            summary_parts.append(f"策略 {ret7}% 🛡正确规避")
            if lesson:
                success_lessons.append(lesson)
        else:
            summary_parts.append("(⏳待验证)")

        lines.append(f"- {sdate}: {' | '.join(summary_parts)}")

        if lesson:
            tag = "💡 成功经验" if verdict in ('correct', 'avoided') else "⚠️ 教训"
            lines.append(f"  {tag}：{lesson}")

    if has_mistakes:
        lines.append("\n⚠️ 注意：你之前对该股有判断失误。请反思之前的遗漏信号，本次分析更加谨慎。")
    if success_lessons:
        lines.append(f"\n💡 成功经验（上次正确的做法，可复制）：{'；'.join(success_lessons[-2:])}")

    return "\n".join(lines)


def compute_technical_indicators(df, signal_date_str):
    """计算截至 signal_date 的所有技术指标"""
    df = df.copy()
    df = df.sort_index()

    # 截断到 signal_date（含当天）
    try:
        cutoff = pd.Timestamp(datetime.strptime(signal_date_str, "%Y%m%d"))
    except ValueError:
        return None
    mask = df.index <= cutoff
    df = df[mask]
    if len(df) < 20:
        return None

    close = df['close'].dropna()
    high = df['high'].dropna()
    low = df['low'].dropna()
    volume = df['volume'].dropna()
    o = df['open'].dropna()

    if len(close) < 5:
        return None

    def _s(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            if hasattr(v, 'iloc'):
                return float(v.iloc[0])
            return float(v.values[0])

    current_price = _s(close.iloc[-1])
    pct_chg = (current_price / _s(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else 0
    ma5 = _s(close.rolling(5).mean().iloc[-1])
    ma10 = _s(close.rolling(10).mean().iloc[-1])
    ma20 = _s(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else ma10
    vol_today = _s(volume.iloc[-1])
    vol_ma5 = _s(volume.rolling(5).mean().iloc[-1])
    recent_high_20 = _s(high.tail(20).max())
    recent_low_20 = _s(low.tail(20).min())

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_bar = 2 * (dif - dea)
    dif_val = _s(dif.iloc[-1])
    dea_val = _s(dea.iloc[-1])
    macd_bar_val = _s(macd_bar.iloc[-1])
    if dif_val > dea_val:
        macd_trend = "金叉向上"
    elif dif_val < dea_val:
        macd_trend = "死叉向下"
    else:
        macd_trend = "粘合"

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))
    rsi_val = _s(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    # 布林带(20,2)
    bb_mid = _s(close.rolling(20).mean().iloc[-1])
    bb_std = _s(close.rolling(20).std().iloc[-1])
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # OBV
    close_diff_sign = (close.diff() > 0).astype(int) - (close.diff() < 0).astype(int)
    obv = (volume * close_diff_sign).cumsum()
    obv_now = _s(obv.iloc[-1])
    obv_5d_ago = _s(obv.iloc[-6]) if len(obv) >= 6 else _s(obv.iloc[0])
    obv_trend = "上升（资金流入）" if obv_now > obv_5d_ago else "下降（资金流出）"

    # 涨停检测
    pct_chg_series = close.pct_change()
    limit_up_mask = pct_chg_series > 0.095
    limit_up_data = ""
    if limit_up_mask.any():
        lu_indices = close.index[limit_up_mask].tolist()
        last_lu_idx = lu_indices[-1]
        last_lu_close = _s(close.loc[last_lu_idx])
        days_since = len(close) - close.index.get_loc(last_lu_idx) - 1
        vol_shrink = _s(volume.iloc[-3:].mean() / _s(volume.loc[last_lu_idx]) * 100) if last_lu_idx in volume.index else 100
        lu_date = str(last_lu_idx)[:10]
        limit_up_data = f"""
## 回调数据
- 最近涨停日：{lu_date}
- 距涨停日：{days_since} 天
- 缩量程度：近3日均量/涨停日量 = {vol_shrink:.0f}%"""

    return {
        "current_price": current_price,
        "pct_chg": pct_chg,
        "ma5": ma5, "ma10": ma10, "ma20": ma20,
        "vol_today": vol_today, "vol_ma5": vol_ma5,
        "recent_high_20": recent_high_20, "recent_low_20": recent_low_20,
        "dif_val": dif_val, "dea_val": dea_val, "macd_bar_val": macd_bar_val,
        "macd_trend": macd_trend,
        "rsi_val": rsi_val,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
        "obv_trend": obv_trend,
        "limit_up_data": limit_up_data,
    }


def build_technical_prompt(code, signal_date_str, mode, entry_price, pullback_pct, limit_days, indicators):
    """构建技术数据 prompt"""
    ind = indicators
    return f"""【{code} 技术数据 · 信号日 {signal_date_str}】

## 基础指标
- 信号日收盘价：{ind['current_price']:.2f}（当日 {ind['pct_chg']:+.2f}%）| 均线：MA5={ind['ma5']:.2f} MA10={ind['ma10']:.2f} MA20={ind['ma20']:.2f}
- 量比：当日/5日均量={f"{ind['vol_today']/ind['vol_ma5']:.2f}x" if ind['vol_ma5'] > 0 else "N/A"} | 20日高={ind['recent_high_20']:.2f}

## 技术指标
- MACD(12,26,9)：DIF={ind['dif_val']:.3f} DEA={ind['dea_val']:.3f} 柱={ind['macd_bar_val']:+.3f} → {ind['macd_trend']}
- RSI(14)：{ind['rsi_val']:.1f}
- 布林(20,2)：上轨={ind['bb_upper']:.2f} 中轨={ind['bb_mid']:.2f} 下轨={ind['bb_lower']:.2f}
- OBV趋势：{ind['obv_trend']}

## 入场信息
- 入场价：¥{entry_price:.2f} | 模式：{mode}
- 回调幅度：{pullback_pct:.1f}% | 连板数：{limit_days}天{ind['limit_up_data']}"""


def analyze_single_signal(code, signal_date_str, mode, entry_price, pullback_pct, limit_days, memory):
    """对单个信号调用 DeepSeek API 进行分析"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print(f"  ⚠️ {code} 跳过: DEEPSEEK_API_KEY 未设置")
        return None

    # 加载截至信号日的数据
    csv_path = os.path.join(DATA_DIR, f"{code}.csv")
    if not os.path.exists(csv_path):
        print(f"  ⚠️ {code} 跳过: 无本地CSV数据")
        return None

    try:
        df = pd.read_csv(csv_path)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
    except Exception as e:
        print(f"  ⚠️ {code} CSV加载失败: {e}")
        return None

    indicators = compute_technical_indicators(df, signal_date_str)
    if indicators is None:
        print(f"  ⚠️ {code} 跳过: 信号日数据不足")
        return None

    technical_data = build_technical_prompt(code, signal_date_str, mode, entry_price, pullback_pct, limit_days, indicators)

    system_prompt = """你是A股连板回调策略量化分析师。严格遵循"量价形时"框架，控制在250字以内，必须包含最终结论。

格式要求（每项1-2句话）：
- 量：缩量程度+资金流向
- 价：均线支撑+关键位
- 形：匹配形态
- 时：回调天数+窗口评估
- 仓位建议：X成仓（情绪档位）
- 最终结论：【参与 / 观望 / 放弃】

⚠️ 最终结论和仓位建议必须出现，缺一不可。"""

    # 历史记忆上下文
    memory_context = get_stock_memory_context(code, memory)

    # 尝试加载信号日的市场新闻
    news_context = ""
    try:
        archive_path = os.path.join(BASE, "news_archive", f"{signal_date_str}.json")
        if os.path.exists(archive_path):
            with open(archive_path, encoding="utf-8") as f:
                news_data = json.load(f)
            sentiment = news_data.get("sentiment_impact", "未知")
            summary = news_data.get("market_summary", "")
            news_context = f"\n【信号日市场环境】\n- 消息面情绪：{sentiment}\n- 市场综述：{summary}\n"
            headlines = news_data.get("news", [])[:3]
            if headlines:
                news_context += "- 重点新闻：\n"
                for h in headlines:
                    news_context += f"  · [{h.get('source','')}] {h.get('title','')} — {h.get('ai_summary','')}\n"
    except Exception:
        pass

    prompt = f"""{technical_data}

【历史记忆】
暂无（首次分析）"""

    if memory_context:
        prompt = f"""{technical_data}

{memory_context}"""

    if news_context:
        prompt += f"\n{news_context}"

    prompt += """
请按"量价形时"框架逐项分析，每项给出具体判断，最后给出：
- 反弹概率：低(≤30%) / 中(30-60%) / 高(≥60%)
- 仓位建议：X成仓（情绪档位）
- 最终结论：【参与 / 观望 / 放弃】"""

    try:
        api_url = screener.DEEPSEEK_API_URL
        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 3000,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            print(f"  ⚠️ {code} API HTTP {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        if "choices" not in data or len(data["choices"]) == 0:
            print(f"  ⚠️ {code} API 返回异常格式")
            return None

        analysis_text = data["choices"][0]["message"]["content"]
        return analysis_text

    except Exception as e:
        print(f"  ⚠️ {code} API 异常: {e}")
        return None


def main():
    print("=" * 60)
    print("🔧 AI 分析回填 · 按时间顺序（先分析先存，作为后续上下文）")
    print("=" * 60)

    # 加载信号
    df = pd.read_csv(SIGNAL_FILE)
    df['signal_date'] = df['signal_date'].astype(str)
    print(f"\n📂 signal_tracker.csv: {len(df)} 条信号")

    # 加载记忆
    memory = load_ai_memory()
    total_before = sum(len(v) for v in memory.values())
    print(f"📂 ai_memory.json: {total_before} 条记录")

    # 找出缺失真实分析的信号
    missing = []
    for _, row in df.iterrows():
        code = row['code']
        date = str(row['signal_date'])
        mode = row.get('mode', '')

        # 检查是否已有真实分析
        has_real = False
        if code in memory:
            for rec in memory[code]:
                if rec.get('date') == date and rec.get('sentiment') != '历史回填':
                    has_real = True
                    break
        if not has_real:
            missing.append({
                'code': code,
                'signal_date': date,
                'mode': mode,
                'entry_price': float(row.get('entry_price', 0)),
                'pullback_pct': float(row.get('pullback_pct', 0)),
                'limit_days': int(row.get('limit_days', 0)),
            })

    # 按信号日排序
    missing.sort(key=lambda x: x['signal_date'])
    print(f"🔍 需要分析: {len(missing)} 条（按时间排序）")

    if not missing:
        print("✅ 所有信号已有 AI 分析")
        return

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("❌ DEEPSEEK_API_KEY 未设置，无法继续")
        return

    print(f"\n🤖 开始分析（共 {len(missing)} 条）...\n")

    ok, fail = 0, 0
    for i, sig in enumerate(missing):
        code = sig['code']
        date = sig['signal_date']
        mode = sig['mode']
        entry_price = sig['entry_price']
        pullback_pct = sig['pullback_pct']
        limit_days = sig['limit_days']

        # 重新加载记忆（前面的分析已存入）
        if i > 0 and i % 3 == 0:
            memory = load_ai_memory()

        print(f"[{i+1}/{len(missing)}] {code} {date} {mode} ...", end=" ", flush=True)

        analysis_text = analyze_single_signal(
            code, date, mode, entry_price, pullback_pct, limit_days, memory
        )

        if analysis_text is None:
            fail += 1
            print("❌")
            continue

        # 提取关键字段
        sentiment = ""
        position = ""
        opinion = ""
        try:
            m = _re.search(r'仓位建议[：:]\s*(.+?)（(.+?)）', analysis_text)
            if m:
                position = m.group(1).strip().strip('*')
                sentiment = m.group(2).strip().strip('*')
            if not sentiment:
                sm = _re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', analysis_text)
                if sm:
                    sentiment = sm.group(1).strip().strip('*')
            for prefix in ['情绪档位：', '情绪档位:', '情绪档位']:
                if sentiment.startswith(prefix):
                    sentiment = sentiment[len(prefix):].strip()
            om = _re.search(r'最终结论[：:]\s*(.+?)(?:\n|$)', analysis_text)
            if om:
                opinion = om.group(1).strip().strip('*')
        except Exception:
            pass

        # 存入记忆
        memory = load_ai_memory()
        if code not in memory:
            memory[code] = []

        # 去重：同日同代码不重复
        dup = False
        for rec in memory[code]:
            if rec.get('date') == date:
                rec['analysis'] = analysis_text
                rec['sentiment'] = sentiment
                rec['position'] = position
                rec['opinion'] = opinion
                dup = True
                break

        if not dup:
            memory[code].append({
                "date": date,
                "mode": mode,
                "entry_price": entry_price,
                "pullback_pct": pullback_pct,
                "limit_days": limit_days,
                "analysis": analysis_text,
                "sentiment": sentiment,
                "position": position,
                "opinion": opinion,
                "verified": False,
                "return_7d": None,
                "exit_reason": None,
                "exit_day": None,
                "verdict": None,
                "review_analysis": None,
                "review_quality": None,
                "what_happened": None,
                "why_wrong": None,
                "missed_signal": None,
                "lesson": None,
            })

        save_ai_memory(memory)
        ok += 1
        opinion_short = opinion[:20] if opinion else "?"
        print(f"✅ [{opinion_short}]")

        # 限流
        if i < len(missing) - 1:
            _time.sleep(1.5)

    total_after = sum(len(v) for v in load_ai_memory().values())
    print(f"\n{'='*60}")
    print(f"✅ 完成: {ok} 成功, {fail} 失败")
    print(f"📂 ai_memory.json: {total_before} → {total_after} 条记录")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
