
"""
A股连板回调策略 - Streamlit UI
一键运行：streamlit run streamlit_app.py

功能：
  - 同时展示 strict/normal/loose 三种模式选股结果
  - 大盘指数实时概览
  - 每只候选股票一键 AI 深度分析
"""
import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import os
import sys
import importlib.util

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="A股连板回调策略",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== 导入本地模块 ====================
def _load_module(filepath, module_name):
    """安全加载一个 .py 文件为模块"""
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # 注册到 sys.modules，避免重复加载
    spec.loader.exec_module(module)
    return module


@st.cache_resource
def load_modules():
    """加载选股new.py 和 AI.py（缓存，避免重复加载）"""
    base = os.path.dirname(os.path.abspath(__file__))

    screener = _load_module(os.path.join(base, "选股new.py"), "screener")
    ai_analyzer = _load_module(os.path.join(base, "AI.py"), "ai_analyzer")

    return screener, ai_analyzer


screener, ai_analyzer = load_modules()

# ==================== 名称/板块查询 ====================
import name_lookup

# ==================== 大盘数据 ====================
@st.cache_data(ttl=300)
def get_market_data():
    """获取三大指数最新数据（日线不足时自动用日内数据补涨跌幅）"""
    indices = {
        "上证指数": "000001.SS",
        "深证成指": "399001.SZ",
        "创业板指": "399006.SZ",
    }
    result = {}
    for name, code in indices.items():
        data = None
        for attempt in range(3):
            try:
                # 先拉日线
                df = yf.download(code, period="5d", progress=False)
                current = None
                pct = 0
                has_delta = False
                high_5d = None
                low_5d = None
                vol_ratio = 1

                if df is not None and len(df) >= 1:
                    current = float(df['Close'].iloc[-1])
                    high_5d = float(df['High'].max())
                    low_5d = float(df['Low'].min())

                    if len(df) >= 2:
                        prev = float(df['Close'].iloc[-2])
                        pct = (current / prev - 1) * 100
                        has_delta = True
                        vol_today = float(df['Volume'].iloc[-1])
                        vol_prev = float(df['Volume'].iloc[-2]) if len(df) >= 2 else vol_today
                        vol_ratio = vol_today / vol_prev if vol_prev > 0 else 1
                    else:
                        # 日线只有 1 行，用日内数据补涨跌幅
                        try:
                            intra = yf.download(code, period="1d", interval="5m", progress=False)
                            if intra is not None and len(intra) >= 2:
                                open_price = float(intra['Open'].iloc[0])
                                if open_price > 0:
                                    pct = (current / open_price - 1) * 100
                                    has_delta = True
                        except Exception:
                            pass

                    data = {
                        'code': code, 'price': round(current, 2),
                        'pct': round(pct, 2), 'has_delta': has_delta,
                        'high_5d': round(high_5d, 2) if high_5d else current,
                        'low_5d': round(low_5d, 2) if low_5d else current,
                        'vol_ratio': round(vol_ratio, 2),
                    }
                    break
            except Exception:
                if attempt < 2:
                    time.sleep(1.5)
        result[name] = data
    return result


# ==================== 极速数据加载（CSV 缓存 + 今日注入 + 过期更新）====================
def load_all_recent_data(codes, lookback_days=30):
    """三步加载，保证实时性：

    1. 从本地 CSV 读历史数据（~5 秒）
    2. yfinance 拉最近 2 天（含今天）→ 注入每只股票（~30-60 秒）
    3. 如果 CSV 过期则全量更新 + 回写（~2-3 分钟，仅首次）

    每次运行都有今天的数据，CSV 新鲜时总计 ~40-70 秒。
    """
    DATA_DIR = screener.DATA_DIR
    all_data = {}
    failed = []

    today_int = int(datetime.now().strftime('%Y%m%d'))
    today_str = datetime.now().strftime('%Y-%m-%d')
    progress_bar = st.progress(0, text="📂 读取本地缓存...")
    total = len(codes)

    # ====== 第一步：从 CSV 读取历史数据 ======
    stale_count = 0
    has_today_count = 0  # 统计 CSV 已有今日数据的股票数
    for i, code in enumerate(codes):
        if (i + 1) % 1500 == 0:
            progress_bar.progress(0.2 * i / total, text=f"📂 读取缓存 {i}/{total}...")

        csv_path = os.path.join(DATA_DIR, f"{code}.csv")
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) < 100:
            failed.append(code)
            continue

        try:
            df = pd.read_csv(csv_path)
            if len(df) == 0:
                failed.append(code)
                continue

            latest_date_str = str(df['date'].iloc[-1])[:10]
            latest_date_int = int(latest_date_str.replace('-', ''))
            if today_int - latest_date_int > 2:
                stale_count += 1
            if latest_date_str == today_str:
                has_today_count += 1

            df = df.tail(lookback_days * 2).copy()
            stock_df = pd.DataFrame({
                'Close': df['close'].values,
                'Open': df['open'].values,
                'High': df['high'].values,
                'Low': df['low'].values,
                'Volume': df['volume'].values,
            }).dropna()

            if len(stock_df) >= 10:
                all_data[code] = stock_df
        except Exception:
            failed.append(code)

    today_coverage = has_today_count / len(all_data) if all_data else 0
    force_refresh = st.session_state.get('force_refresh', False)
    progress_bar.progress(0.25, text=f"📂 缓存: {len(all_data)} 只 ({stale_count} 只过期, 今日覆盖 {today_coverage:.0%})")

    # ====== 第二步：今日数据注入（强制刷新时必跑，正常时已有今日数据则跳过）======
    skip_injection = (not force_refresh) and (today_coverage > 0.95)
    injected = 0

    if force_refresh:
        st.session_state['force_refresh'] = False  # 用完即清

    if skip_injection:
        progress_bar.progress(0.40, text=f"📡 今日数据已齐全（{today_coverage:.0%}），跳过注入 ⚡")
    else:
        progress_bar.progress(0.28, text=f"📡 今日覆盖率 {today_coverage:.0%}，拉取最新数据...")
        BATCH_SIZE = 200
        batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]

        for i, batch in enumerate(batches):
            progress_bar.progress(0.28 + 0.12 * (i + 1) / len(batches),
                                  text=f"📡 今日注入 {i+1}/{len(batches)} 批...")
            try:
                hist = yf.download(tickers=batch, period="3d", progress=False)
                if hist is None or hist.empty:
                    continue
                try:
                    codes_in_batch = set(hist.columns.get_level_values(1))
                except Exception as e:
                    print(f"    批次 MultiIndex 解析失败: {e}")

                for code in batch:
                    if code not in codes_in_batch:
                        continue
                    try:
                        recent = hist.xs(code, level=1, axis=1)
                        recent = recent[recent['Close'].notna() & (recent['Close'] > 0)]
                        if len(recent) == 0:
                            continue

                        if code in all_data:
                            df = all_data[code]
                            new_rows = pd.DataFrame({
                                'Close': recent['Close'].values,
                                'Open': recent['Open'].values,
                                'High': recent['High'].values,
                                'Low': recent['Low'].values,
                                'Volume': recent['Volume'].values,
                            })
                            all_data[code] = pd.concat([df, new_rows], ignore_index=True).tail(60)
                        else:
                            all_data[code] = recent[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                        injected += 1
                    except Exception:
                        pass
            except Exception:
                pass

        progress_bar.progress(0.40, text=f"📡 今日数据注入: {injected} 只")

    # ====== 第三步：如果 CSV 过期，全量更新 + 回写 ======
    if stale_count > len(codes) * 0.3:
        progress_bar.progress(0.42, text=f"⏳ {stale_count} 只过期，全量更新...")

        batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
        updated = 0
        fresh_all_data = {}

        for i, batch in enumerate(batches):
            progress_bar.progress(0.42 + 0.54 * (i + 1) / len(batches),
                                  text=f"⏳ 全量更新 {i+1}/{len(batches)} 批...")
            try:
                hist = yf.download(tickers=batch, period="30d", progress=False)
                codes_in_batch = set()
                if hist is not None and not hist.empty:
                    try:
                        codes_in_batch = set(hist.columns.get_level_values(1))
                    except Exception:
                        pass

                for code in batch:
                    stock_data = None
                    if code in codes_in_batch:
                        try:
                            stock_data = hist.xs(code, level=1, axis=1)
                            if stock_data['Close'].dropna().empty:
                                stock_data = None
                        except Exception:
                            stock_data = None

                    if stock_data is not None and not stock_data.empty:
                        fresh_all_data[code] = stock_data
                        # 回写 CSV
                        try:
                            csv_path = os.path.join(DATA_DIR, f"{code}.csv")
                            df_old = pd.read_csv(csv_path)
                            new_rows = [
                                {'date': (idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10]),
                                 'open': row['Open'], 'high': row['High'],
                                 'low': row['Low'], 'close': row['Close'],
                                 'volume': int(row['Volume'])}
                                for idx, row in stock_data.iterrows() if row['Close'] > 0
                            ]
                            if new_rows:
                                df_new = pd.DataFrame(new_rows)
                                df_combined = pd.concat([df_old, df_new])
                                df_combined['date'] = pd.to_datetime(df_combined['date'])
                                df_combined = df_combined.drop_duplicates(subset=['date'], keep='last')
                                df_combined = df_combined.sort_values('date')
                                df_combined.to_csv(csv_path, index=False)
                                updated += 1
                        except Exception:
                            pass
            except Exception:
                pass

        for code, stock_data in fresh_all_data.items():
            all_data[code] = stock_data

        progress_bar.progress(0.96, text=f"✅ CSV 更新: {updated} 只")
        if updated > 0:
            st.toast(f"💾 {updated} 只股票CSV已刷新，下次秒开", icon="✅")

    progress_bar.progress(1.0, text=f"✅ 加载完成: {len(all_data)} 只 (今日注入 {injected})")
    progress_bar.empty()
    return all_data, failed


# ==================== 云端数据加载（Streamlit Cloud 无本地CSV时使用）====================
@st.cache_data(ttl=3600)
def cloud_load_data():
    """云端模式：从 yfinance 批量下载近期数据，缓存1小时。

    下载近30天数据用于筛选，比本地模式慢但能在 Streamlit Cloud 上运行。
    首次约2-4分钟，缓存后秒开。
    """
    # 生成代码列表（云端用精简列表，减少下载量）
    codes = []
    # 上海主板
    for i in range(600000, 606000):
        codes.append(f"{i}.SS")
    # 深圳主板+中小板
    for i in range(1, 5000):
        codes.append(f"{i:06d}.SZ")
    # 创业板
    for i in range(300000, 302000):
        codes.append(f"{i}.SZ")
    # 科创板
    for i in range(688000, 690000):
        codes.append(f"{i}.SS")

    # 云端模式：扫描最活跃的 ~2000 只股票
    codes = []
    # 上海主板: 600000-603999（最活跃段）
    for i in range(600000, 604000):
        codes.append(f"{i}.SS")
    # 深圳主板: 000001-002999
    for i in range(1, 3000):
        codes.append(f"{i:06d}.SZ")
    # 创业板: 300000-301000
    for i in range(300000, 301000):
        codes.append(f"{i}.SZ")
    # 科创板: 688000-688600
    for i in range(688000, 688600):
        codes.append(f"{i}.SS")

    st.info(f"☁️ 云端模式：扫描 {len(codes)} 只A股（分批下载，约60-90秒）")

    all_data = {}
    BATCH_SIZE = 200
    batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
    total_batches = len(batches)

    progress_bar = st.progress(0, text=f"☁️ 第 1/{total_batches} 批...")

    for i, batch in enumerate(batches):
        progress_bar.progress(
            (i + 1) / total_batches,
            text=f"☁️ 下载第 {i+1}/{total_batches} 批 ({len(batch)}只)..."
        )
        try:
            hist = yf.download(tickers=batch, period="30d", progress=False, timeout=30)
            if hist is None or hist.empty:
                continue
            try:
                level_codes = set(hist.columns.get_level_values(1))
            except Exception:
                continue
            for code in batch:
                if code not in level_codes:
                    continue
                try:
                    stock_data = hist.xs(code, level=1, axis=1)
                    stock_data = stock_data[stock_data['Close'].notna() & (stock_data['Close'] > 0)]
                    if len(stock_data) >= 10:
                        all_data[code] = stock_data[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                except Exception:
                    pass
        except Exception:
            pass

    progress_bar.empty()
    return all_data


# ==================== 快速 AI 分析（跳过板块信息，用已下载数据）====================
def fast_ai_analysis(code, stock_df, market_context=""):
    """基于已下载的30天数据 + DeepSeek API 快速分析（比 AI.py 快 3-5 秒）"""
    import requests

    # ---- 从已下载数据计算技术指标 ----
    close = stock_df['Close'].dropna()
    high = stock_df['High'].dropna()
    low = stock_df['Low'].dropna()
    volume = stock_df['Volume'].dropna()

    if len(close) < 5:
        return None

    current_price = close.iloc[-1]
    prev_close = close.iloc[-2] if len(close) >= 2 else current_price
    pct_chg = (current_price / prev_close - 1) * 100
    amplitude = (high.iloc[-1] / low.iloc[-1] - 1) * 100

    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else ma10

    vol_today = volume.iloc[-1]
    vol_ma5 = volume.rolling(5).mean().iloc[-1]
    recent_high = high.tail(20).max()
    drawdown = (recent_high - current_price) / recent_high * 100

    recent_closes = close.tail(5).tolist()

    technical_data = f"""
【{code} 技术数据】
- 最新价：{current_price:.2f}（今日涨跌 {pct_chg:+.2f}%）
- 今日振幅：{amplitude:.1f}%
- 量比(5日均量)：{vol_today/vol_ma5:.2f}x
- MA5/MA10/MA20：{ma5:.2f} / {ma10:.2f} / {ma20:.2f}
- 近20日最高：{recent_high:.2f}（当前回撤 {drawdown:.1f}%）
- 近5日收盘：{recent_closes}
"""

    # ---- 构造精简 prompt（max_tokens 800，比原来 2000 快一半）----
    prompt = f"""你是A股短线分析师。请简洁分析 {code}：

{technical_data}
{market_context}

请用以下格式（每项2-3句话，不要展开）：

## 一、技术面
- 支撑/压力位（给具体价格）
- 量价状态

## 二、反弹判断
- 回调阶段（初期/中期/末期）
- 反弹概率（低/中/高）+ 一句话理由

## 三、风险
- 主要风险（一句话）

## 四、明日锚点
- 高开可关注价 / 低开应放弃价
- 建议入场区间

## 五、综合
- 是否参与 + 仓位建议 + 止盈止损位"""

    try:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        api_url = ai_analyzer.DEEPSEEK_API_URL

        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": "你是务实直接的A股短线分析师，回答简洁不模棱两可。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 800,
            },
            timeout=25,
        )
        data = resp.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        return f"API异常：{data}"
    except Exception as e:
        return f"AI调用失败：{e}"


# ==================== 多模式筛选 ====================
def screen_all_modes(all_data):
    """用 strict/normal/loose 三种参数分别筛选，返回 {mode: [候选列表]}"""
    modes = ["strict", "normal", "loose"]
    results = {}
    all_stats = {}

    for mode in modes:
        params = screener.SCREEN_MODES[mode].copy()

        # 保存+设置全局 PARAMS
        original = screener.PARAMS.copy()
        screener.PARAMS.update(params)

        candidates = []
        stats = {
            'total': len(all_data),
            'has_data': 0,
            'has_limit_up': 0,
            'consecutive_ok': 0,
            'entity_ratio_ok': 0,
            'pullback_days_ok': 0,
            'pullback_range_ok': 0,
            'ma_ok': 0,
            'volume_shrink_ok': 0,
            'yang_ok': 0,
            'volume_expand_ok': 0,
            'final': 0,
        }

        for code, stock_data in all_data.items():
            try:
                screener._screen_single_stock(code, stock_data, stats, candidates, mode)
            except Exception:
                pass

        # 恢复 PARAMS
        screener.PARAMS.update(original)

        results[mode] = candidates
        all_stats[mode] = stats

    return results, all_stats


# ==================== 信号追踪 ====================
SIGNAL_FILE = "signal_tracker.csv"

def save_signals(all_candidates):
    """将今日候选保存到信号追踪文件（去重）"""
    if not all_candidates:
        return

    today = datetime.now().strftime('%Y%m%d')

    # 批量获取名称/板块
    codes = [c['code'] for c in all_candidates]
    name_info = name_lookup.batch_lookup(codes, max_fetch=10)

    new_rows = []
    for c in all_candidates:
        info = name_info.get(c['code'], {})
        new_rows.append({
            'signal_date': today,
            'code': c['code'],
            'name': info.get('name', '') or '',
            'sector': info.get('sector', '') or info.get('industry', '') or '',
            'mode': c.get('mode', ''),
            'entry_price': c['price'],
            'pullback_pct': c['pullback_pct'],
            'limit_days': c['limit_days'],
        })

    df_new = pd.DataFrame(new_rows)

    # 读取已有记录，去重
    if os.path.exists(SIGNAL_FILE):
        df_old = pd.read_csv(SIGNAL_FILE)
        # 同一天同一只股票不重复
        existing = set(zip(df_old['signal_date'].astype(str), df_old['code']))
        df_new = df_new[~df_new.apply(lambda r: (r['signal_date'], r['code']) in existing, axis=1)]
        if len(df_new) == 0:
            return
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new

    df_combined.to_csv(SIGNAL_FILE, index=False, encoding='utf-8-sig')


def show_signal_review():
    """信号复盘面板：查看历史信号的实际表现"""
    if not os.path.exists(SIGNAL_FILE):
        st.info("📋 暂无历史信号。选股后会自动记录。")
        return

    df = pd.read_csv(SIGNAL_FILE)
    if len(df) == 0:
        st.info("📋 暂无历史信号。")
        return

    # ---- 统计卡片 ----
    total = len(df)
    dates = sorted(df['signal_date'].astype(str).unique())
    # 安全格式化日期
    first_date = str(dates[0])
    last_date = str(dates[-1])
    first_str = f"{first_date[:4]}-{first_date[4:6]}-{first_date[6:]}" if len(first_date) >= 8 else first_date
    last_str = f"{last_date[:4]}-{last_date[4:6]}-{last_date[6:]}" if len(last_date) >= 8 else last_date
    st.caption(f"📋 共 {total} 条信号，{len(dates)} 个交易日（{first_str} ~ {last_str}）")

    col1, col2, col3, col4 = st.columns(4)

    # 查找有足够天数来复盘（≥3 天前）
    today_int = int(datetime.now().strftime('%Y%m%d'))
    reviewable = df[df['signal_date'].apply(lambda d: today_int - int(str(d)) >= 3)]

    with col1:
        st.metric("总信号", total)
    with col2:
        st.metric("可复盘(≥3天)", len(reviewable))
    with col3:
        if len(reviewable) > 0:
            # 尝试计算 3 日收益
            gains = []
            for _, row in reviewable.iterrows():
                ret = check_return(row['code'], row['signal_date'], row['entry_price'], 3)
                if ret is not None:
                    gains.append(ret)
            if gains:
                win_rate = sum(1 for g in gains if g > 0) / len(gains)
                st.metric("3日胜率", f"{win_rate:.0%}")
            else:
                st.metric("3日胜率", "—")
        else:
            st.metric("3日胜率", "—")
    with col4:
        if len(reviewable) > 0 and gains:
            st.metric("3日均收益", f"{sum(gains)/len(gains):+.2%}")
        else:
            st.metric("3日均收益", "—")

    # ---- 详细表格 ----
    if len(reviewable) > 0:
        st.subheader("📊 最近信号详情")

        rows = []
        for _, row in reviewable.tail(30).iterrows():
            code = row['code']
            sdate = str(row['signal_date'])
            price = row['entry_price']
            ret3 = check_return(code, sdate, price, 3)
            ret5 = check_return(code, sdate, price, 5)
            ret7 = check_return(code, sdate, price, 7)

            d3 = f"{ret3:+.1f}%" if ret3 is not None else "—"
            d5 = f"{ret5:+.1f}%" if ret5 is not None else "—"
            d7 = f"{ret7:+.1f}%" if ret7 is not None else "—"

            # 颜色标记
            d3_icon = "🟢" if (ret3 or 0) > 0 else ("🔴" if (ret3 or 0) < 0 else "⚪")
            d5_icon = "🟢" if (ret5 or 0) > 0 else ("🔴" if (ret5 or 0) < 0 else "⚪")

            stock_name = row.get('name', '') or ''
            stock_sector = row.get('sector', '') or ''
            rows.append({
                '日期': f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}",
                '代码': code,
                '名称': stock_name,
                '板块': stock_sector,
                '模式': row.get('mode', ''),
                '入场价': f"{price:.2f}",
                '回调': f"{row['pullback_pct']:.1f}%",
                '3日': f"{d3_icon} {d3}",
                '5日': f"{d5_icon} {d5}",
                '7日': d7,
            })

        df_show = pd.DataFrame(rows)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # 模式胜率对比
        st.subheader("📊 各模式胜率对比")
        mode_stats = []
        for mode in reviewable['mode'].unique():
            if pd.isna(mode) or not mode:
                continue
            sub = reviewable[reviewable['mode'] == mode]
            gains = []
            for _, row in sub.iterrows():
                ret = check_return(row['code'], str(row['signal_date']), row['entry_price'], 3)
                if ret is not None:
                    gains.append(ret)
            if gains:
                mode_stats.append({
                    '模式': mode,
                    '信号数': len(sub),
                    '3日胜率': f"{sum(1 for g in gains if g>0)/len(gains):.0%}",
                    '3日均收益': f"{sum(gains)/len(gains):+.2%}",
                    '最佳': f"{max(gains):+.1%}",
                    '最差': f"{min(gains):+.1%}",
                })
        if mode_stats:
            st.dataframe(pd.DataFrame(mode_stats), use_container_width=True, hide_index=True)

        # 板块表现对比
        if 'sector' in reviewable.columns:
            st.subheader("📊 板块表现对比")
            sector_data = []
            for sector in reviewable['sector'].dropna().unique():
                if not sector or sector == '':
                    continue
                sub = reviewable[reviewable['sector'] == sector]
                gains = []
                for _, r in sub.iterrows():
                    ret = check_return(r['code'], str(r['signal_date']), r['entry_price'], 3)
                    if ret is not None:
                        gains.append(ret)
                if gains:
                    sector_data.append({
                        '板块': sector,
                        '信号数': len(sub),
                        '3日胜率': f"{sum(1 for g in gains if g>0)/len(gains):.0%}",
                        '3日均收益': f"{sum(gains)/len(gains):+.2%}",
                    })
            if sector_data:
                st.dataframe(pd.DataFrame(sector_data), use_container_width=True, hide_index=True)
    else:
        st.info("最近3天内的信号需要再等等才能复盘。")

    # 刷新按钮
    if st.button("🔄 刷新复盘数据", key="refresh_review"):
        st.cache_data.clear()
        st.rerun()


@st.cache_data(ttl=600)
def check_return(code, signal_date, entry_price, hold_days):
    """检查信号持有 N 天后的实际收益"""
    try:
        start_dt = datetime.strptime(str(signal_date), '%Y%m%d')
        end_dt = start_dt + pd.Timedelta(days=hold_days + 5)  # 多拉几天

        ticker = yf.Ticker(code)
        df = ticker.history(start=start_dt.strftime('%Y-%m-%d'),
                           end=end_dt.strftime('%Y-%m-%d'))
        if df is None or len(df) < hold_days + 1:
            return None

        # 取第 hold_days 天的收盘价（跳过信号日）
        exit_price = df['Close'].iloc[min(hold_days, len(df) - 1)]
        if exit_price <= 0 or entry_price <= 0:
            return None
        return (exit_price / entry_price - 1) * 100
    except Exception:
        return None


# ==================== 手动选股复盘 ====================
MANUAL_PICKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_picks.csv")


def save_manual_picks(results):
    """保存手动选股结果到 manual_picks.csv（去重）"""
    if not results:
        return
    df_new = pd.DataFrame(results)
    if os.path.exists(MANUAL_PICKS_FILE) and os.path.getsize(MANUAL_PICKS_FILE) > 10:
        df_old = pd.read_csv(MANUAL_PICKS_FILE)
        existing = set(zip(df_old['date'].astype(str), df_old['code']))
        df_new = df_new[~df_new.apply(lambda r: (str(r['date']), r['code']) in existing, axis=1)]
        if len(df_new) == 0:
            return
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new
    df_combined.to_csv(MANUAL_PICKS_FILE, index=False, encoding='utf-8-sig')


def display_manual_results(results, picked_date_str):
    """展示手动选股分析结果"""
    total = len(results)
    matched = sum(1 for r in results if r.get('system_picked'))

    st.subheader("📊 分析结果")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("手动输入", total)
    with col2:
        st.metric("系统也选中", matched)
    with col3:
        st.metric("匹配率", f"{matched/total:.0%}" if total > 0 else "—")

    # 详细表格
    rows = []
    for r in results:
        rows.append({
            '代码': r['code'],
            '名称': r.get('name', '') or '',
            '板块': r.get('sector', '') or '',
            '系统选中': '✅' if r.get('system_picked') else '❌',
            '系统模式': r.get('system_mode', '') or '—',
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # 逐只AI分析报告
    for r in results:
        analysis_text = r.get('ai_analysis', '')
        if analysis_text:
            with st.expander(f"🤖 {r['code']} {r.get('name', '')} - AI分析报告"):
                st.markdown(analysis_text)

    # 保存
    save_manual_picks(results)
    st.success(f"✅ 已保存 {len(results)} 条手动选股记录")


def perform_manual_analysis(codes, signal_date_str):
    """对手动输入的股票列表执行AI分析"""
    progress = st.progress(0, text="准备分析...")

    all_data = st.session_state.get('all_data', {})
    results = []

    for i, code in enumerate(codes):
        progress.progress((i + 1) / len(codes), text=f"正在分析 {code} ({i+1}/{len(codes)})...")

        # 获取股票数据
        if code in all_data:
            stock_df = all_data[code]
        else:
            try:
                ticker = yf.Ticker(code)
                stock_df = ticker.history(period="30d")
                if stock_df is None or len(stock_df) < 5:
                    st.warning(f"⚠️ {code} 数据不足，跳过")
                    continue
            except Exception:
                st.warning(f"⚠️ {code} 数据获取失败，跳过")
                continue

        # 检查系统是否会选中（用三种模式分别测试）
        system_picked = False
        system_mode = ""
        for mode in ["strict", "normal", "loose"]:
            params = screener.SCREEN_MODES[mode].copy()
            original = screener.PARAMS.copy()
            screener.PARAMS.update(params)
            test_candidates = []
            test_stats = {'total': 1, 'has_data': 0, 'has_limit_up': 0, 'consecutive_ok': 0,
                          'entity_ratio_ok': 0, 'pullback_days_ok': 0, 'pullback_range_ok': 0,
                          'ma_ok': 0, 'volume_shrink_ok': 0, 'yang_ok': 0, 'volume_expand_ok': 0, 'final': 0}
            try:
                screener._screen_single_stock(code, stock_df, test_stats, test_candidates, mode)
                if len(test_candidates) > 0:
                    system_picked = True
                    system_mode = mode
                    screener.PARAMS.update(original)
                    break
            except Exception:
                pass
            finally:
                screener.PARAMS.update(original)

        # AI分析
        analysis = None
        try:
            market_ctx = ai_analyzer.get_market_context()
            analysis = fast_ai_analysis(code, stock_df, market_ctx)
        except Exception:
            pass

        # 获取名称/板块
        info = name_lookup.lookup_code(code)

        results.append({
            'date': signal_date_str,
            'code': code,
            'name': info.get('name', '') or '',
            'sector': info.get('sector', '') or info.get('industry', '') or '',
            'system_picked': system_picked,
            'system_mode': system_mode,
            'ai_analysis': analysis or '',
        })

    progress.empty()

    if results:
        display_manual_results(results, signal_date_str)
    else:
        st.warning("没有成功分析任何股票")


def show_manual_review():
    """手动选股复盘界面"""
    st.subheader("📝 输入你想复盘的股票")

    col1, col2 = st.columns([3, 1])
    with col1:
        manual_input = st.text_area(
            "输入股票代码（每行一个，如 600000.SS / 000001.SZ / 300750.SZ）",
            height=120,
            placeholder="600000.SS\n000001.SZ\n300750.SZ",
            key="manual_stock_input"
        )
    with col2:
        review_date = st.date_input("复盘日期", value=datetime.now(), key="manual_review_date")
        if st.button("🔍 开始分析", type="primary", use_container_width=True, key="manual_analyze_btn"):
            if manual_input.strip():
                st.session_state['trigger_manual_analysis'] = True
                st.session_state['manual_codes'] = [c.strip() for c in manual_input.split('\n') if c.strip()]
                st.session_state['manual_date'] = review_date.strftime('%Y%m%d')
            else:
                st.warning("请输入至少一只股票代码")

    # 触发分析
    if st.session_state.get('trigger_manual_analysis') and st.session_state.get('manual_codes'):
        codes = st.session_state['manual_codes']
        signal_date = st.session_state['manual_date']
        st.divider()
        perform_manual_analysis(codes, signal_date)
        st.session_state['trigger_manual_analysis'] = False  # 重置

    # 历史手动选股回顾
    if os.path.exists(MANUAL_PICKS_FILE) and os.path.getsize(MANUAL_PICKS_FILE) > 10:
        st.divider()
        st.subheader("📊 历史手动选股回顾")
        try:
            df_hist = pd.read_csv(MANUAL_PICKS_FILE)
            if len(df_hist) > 0:
                st.caption(f"共 {len(df_hist)} 条手动选股记录")

                # 计算收益（仅对 ≥3 天前的记录）
                today_int = int(datetime.now().strftime('%Y%m%d'))
                hist_rows = []
                for _, row in df_hist.tail(30).iterrows():
                    sdate = str(row['date'])
                    if len(sdate) >= 8 and today_int - int(sdate) >= 3:
                        ret3 = check_return(row['code'], sdate, 0, 3)  # 手动的没有 entry_price，用 0 跳过
                        # 尝试用当前收盘价
                        try:
                            ticker = yf.Ticker(row['code'])
                            hist_df = ticker.history(
                                start=f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}",
                                end=f"{int(sdate[:4])+1}-{sdate[4:6]}-{sdate[6:]}",
                            )
                            if hist_df is not None and len(hist_df) >= 2:
                                entry_p = hist_df['Close'].iloc[0]
                                ret = check_return(row['code'], sdate, entry_p, 3)
                            else:
                                ret = None
                        except Exception:
                            ret = None
                        ret_str = f"{ret:+.1f}%" if ret is not None else "—"
                    else:
                        ret_str = "⏳"

                    hist_rows.append({
                        '日期': f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}" if len(sdate) >= 8 else sdate,
                        '代码': row['code'],
                        '名称': row.get('name', '') or '',
                        '板块': row.get('sector', '') or '',
                        '系统选中': '✅' if row.get('system_picked') else '❌',
                        '3日收益': ret_str,
                    })

                if hist_rows:
                    st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)
        except Exception as e:
            st.caption(f"读取历史记录失败: {e}")


# ==================== 主界面 ====================
def main():
    st.title("📈 A股连板回调策略")

    # 实时时间戳
    now = datetime.now()
    market_status = ""
    weekday = now.weekday()
    hour = now.hour
    if weekday >= 5:
        market_status = "🔵 周末休市"
    elif hour < 9 or (hour == 9 and now.minute < 30):
        market_status = "⏳ 盘前"
    elif hour < 11 or (hour == 11 and now.minute <= 30):
        market_status = "🟢 交易中"
    elif hour < 13:
        market_status = "⏸ 午休"
    elif hour < 15:
        market_status = "🟢 交易中"
    elif hour < 16:
        market_status = "🟡 刚收盘（数据更新中）"
    else:
        market_status = "🔴 已收盘"

    st.caption(f"🕐 {now.strftime('%Y-%m-%d %H:%M')}  {market_status}"
               + ("  |  收盘后点「强制刷新」获取最终数据" if market_status in ["🟡 刚收盘（数据更新中）", "🔴 已收盘"] else ""))

    # ---- 侧边栏 ----
    with st.sidebar:
        st.header("⚙️ 控制面板")

        st.markdown("""
        **策略说明**
        寻找连板后回调企稳的股票，在缩量止跌、
        放量反弹时介入，捕捉龙回头机会。
        """)

        st.divider()

        if st.button("🚀 开始当日选股", type="primary", use_container_width=True):
            st.session_state['trigger_scan'] = True

        if st.button("🔄 重新扫描", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        if st.button("🔄 强制刷新（收盘后用）", use_container_width=True,
                     help="跳过缓存检查，强制拉取今日最新收盘数据"):
            st.session_state['trigger_scan'] = True
            st.session_state['force_refresh'] = True
            st.rerun()

        st.divider()

        st.markdown("**三种模式说明**")
        st.markdown("- 🔴 **严格**: 历史回测最优参数，信号少但精准")
        st.markdown("- 🟡 **正常**: 放宽实体板/阳线要求，日常推荐")
        st.markdown("- 🟢 **宽松**: 几乎只保留连板+回调条件，弱势市场用")

        st.divider()
        st.caption(f"Powered by DeepSeek AI")

    # ---- 大盘概览 ----
    st.header("📊 大盘概况")
    market = get_market_data()

    cols = st.columns(3)
    for i, (name, data) in enumerate(market.items()):
        with cols[i]:
            if data:
                delta_str = f"{data['pct']:+.2f}%" if data.get('has_delta', True) else "—"
                st.metric(
                    label=name,
                    value=f"{data['price']:.0f}",
                    delta=delta_str,
                )
                st.caption(
                    f"5日高 {data['high_5d']:.0f} | "
                    f"5日低 {data['low_5d']:.0f} | "
                    f"量比 {data['vol_ratio']:.1f}x"
                )
            else:
                st.metric(label=name, value="获取失败")
    st.divider()

    # ---- 选股结果 ----
    if 'trigger_scan' not in st.session_state:
        st.info("👈 点击左侧 **开始当日选股** 按钮启动扫描")
        return

    force_refresh = st.session_state.get('force_refresh', False)

    # 如果已有缓存结果，直接复用（点 AI 分析时不重新扫描 5000+ CSV）
    if not force_refresh and 'cached_results' in st.session_state and 'cached_all_stats' in st.session_state:
        all_data = st.session_state.get('all_data', {})
        results = st.session_state['cached_results']
        all_stats = st.session_state['cached_all_stats']
    else:
        # 获取代码列表
        DATA_DIR = screener.DATA_DIR
        if os.path.isdir(DATA_DIR):
            cache_files = [
                f for f in os.listdir(DATA_DIR)
                if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100
            ]
            codes = [f.replace('.csv', '') for f in cache_files]
        else:
            cache_files = []
            codes = []

        if len(codes) > 100:
            # 本地模式：从 CSV 缓存极速加载（秒级）
            with st.spinner("正在从本地缓存加载数据..."):
                all_data, failed_codes = load_all_recent_data(codes)

            st.session_state['all_data'] = all_data
            st.success(f"✅ 数据加载完成：{len(all_data)} 只有效数据（本地缓存，秒级）"
                       + (f"，{len(failed_codes)} 只失败" if failed_codes else ""))
        else:
            # 云端模式：没有本地 CSV，从 yfinance 批量下载
            st.info("☁️ 云端模式：从网络加载数据（首次较慢，后续秒开）")
            all_data = cloud_load_data()
            st.session_state['all_data'] = all_data
            st.success(f"✅ 云端数据加载完成：{len(all_data)} 只")

        # 三模式筛选
        st.write("🔍 正在用三种模式筛选...")
        results, all_stats = screen_all_modes(all_data)

        # 缓存筛选结果，后续点 AI 分析时不再重复扫描
        st.session_state['cached_results'] = results
        st.session_state['cached_all_stats'] = all_stats
        if force_refresh:
            st.session_state['force_refresh'] = False

    # ---- 结果展示 ----
    st.header("📋 选股结果")

    tabs = st.tabs([
        f"🔴 严格模式 ({len(results['strict'])}只)",
        f"🟡 正常模式 ({len(results['normal'])}只)",
        f"🟢 宽松模式 ({len(results['loose'])}只)",
    ])

    for tab_idx, mode in enumerate(["strict", "normal", "loose"]):
        with tabs[tab_idx]:
            candidates = results[mode]
            stats = all_stats[mode]

            if not candidates:
                st.info(f"当前模式无符合条件的股票")
                with st.expander("📊 筛选漏斗"):
                    st.write(f"总扫描: {stats['total']} → 有涨停: {stats['has_limit_up']} → "
                             f"连板达标: {stats['consecutive_ok']} → 实体板达标: {stats['entity_ratio_ok']} → "
                             f"回调天数: {stats['pullback_days_ok']} → 回调幅度: {stats['pullback_range_ok']} → "
                             f"均线: {stats['ma_ok']} → 量能: {stats['volume_shrink_ok']} → "
                             f"阳线: {stats['yang_ok']} → 放量: {stats['volume_expand_ok']} → "
                             f"最终: {stats['final']}")
                continue

            # 显示每只候选
            # 批量加载名称/板块缓存
            candidate_codes = [c['code'] for c in candidates]
            name_info = name_lookup.batch_lookup(candidate_codes, max_fetch=5)

            for code_data in candidates:
                code = code_data['code']
                info = name_info.get(code, {})
                stock_name = info.get('name', '') or ''
                stock_sector = info.get('sector', '') or info.get('industry', '') or ''

                with st.container():
                    col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1.2, 0.9, 0.9, 0.9, 1.5])

                    with col1:
                        name_line = f"**`{code}`**"
                        if stock_name:
                            name_line += f"  {stock_name}"
                        st.markdown(name_line)
                        if stock_sector:
                            st.caption(f"🏷 {stock_sector}")
                    with col2:
                        st.metric("价格", f"{code_data['price']:.2f}")
                    with col3:
                        st.metric("回调", f"{code_data['pullback_pct']:.1f}%")
                    with col4:
                        st.metric("连板", f"{code_data['limit_days']}天")
                    with col5:
                        st.metric("实体板", f"{code_data['entity_ratio']:.0f}%")
                    with col6:
                        # 跨模式共享：任何 Tab 点 AI 都触发同一 analyze_{code}
                        btn_key = f"ai_{mode}_{code}"
                        if st.button(f"🤖 AI分析", key=btn_key, use_container_width=True):
                            st.session_state[f'analyze_{code}'] = True

                    # AI 分析区域（跨模式共享，点一次三个 Tab 都展开）
                    if st.session_state.get(f'analyze_{code}'):
                        with st.spinner(f"🤖 正在对 {code} 进行AI深度分析（约8-15秒）..."):
                            try:
                                # 用已下载的 30 天数据 + 精简 prompt，比 AI.py 快一倍
                                stock_df = st.session_state.get('all_data', {}).get(code)
                                market_ctx = ai_analyzer.get_market_context()
                                analysis = fast_ai_analysis(code, stock_df, market_ctx)

                                if analysis:
                                    st.session_state[f'analysis_result_{code}'] = analysis
                                    st.session_state[f'analyze_{code}'] = False  # 分析完成，重置触发
                            except Exception as e:
                                st.error(f"分析失败: {e}")
                                st.session_state[f'analyze_{code}'] = False

                    if st.session_state.get(f'analysis_result_{code}'):
                        with st.expander(f"📝 {code} AI分析报告", expanded=True):
                            st.markdown(st.session_state[f'analysis_result_{code}'])

                    st.divider()

            # 漏斗统计
            with st.expander("📊 筛选漏斗详情"):
                stages = [
                    ("总扫描", stats['total']),
                    ("有涨停", stats['has_limit_up']),
                    ("连板数达标", stats['consecutive_ok']),
                    ("实体板达标", stats['entity_ratio_ok']),
                    ("回调天数", stats['pullback_days_ok']),
                    ("回调幅度", stats['pullback_range_ok']),
                    ("均线达标", stats['ma_ok']),
                    ("量能达标", stats['volume_shrink_ok']),
                    ("阳线达标", stats['yang_ok']),
                    ("放量达标", stats['volume_expand_ok']),
                    ("✅ 最终候选", stats['final']),
                ]
                cols_funnel = st.columns(len(stages))
                for i, (label, val) in enumerate(stages):
                    with cols_funnel[i]:
                        st.metric(label, val)

    # ---- 导出 ----
    st.divider()
    if any(len(v) > 0 for v in results.values()):
        all_candidates = []
        for mode in ["strict", "normal", "loose"]:
            for c in results[mode]:
                all_candidates.append({**c, 'mode': mode})
        df_export = pd.DataFrame(all_candidates)
        st.download_button(
            label="📥 导出 CSV",
            data=df_export.to_csv(index=False, encoding='utf-8-sig'),
            file_name=f"candidates_all_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

        # 自动保存到信号追踪
        save_signals(all_candidates)

    # ---- 信号复盘 ----
    st.divider()
    st.header("📋 信号复盘")
    show_signal_review()

    # ---- 手动选股复盘 ----
    st.divider()
    st.header("✍️ 手动选股复盘")
    show_manual_review()


if __name__ == "__main__":
    main()
