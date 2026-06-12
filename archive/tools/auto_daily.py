"""
每日自动选股 + 微信推送
用法: python auto_daily.py

首次使用:
  1. 注册 Server酱: https://sct.ftqq.com/
  2. 获取 SendKey，填到下面的 SENDKEY
  3. 设置定时运行（见文件末尾说明）
"""
import yfinance as yf
import pandas as pd
from datetime import datetime
import os
import sys
import importlib.util
import requests

# ==================== 配置 ====================
# Server酱 SendKey（注册 https://sct.ftqq.com/ 获取，通过环境变量设置）
#   export SENDKEY="你的key"
SENDKEY = os.environ.get("SENDKEY", "")

# 选股模式（可改）
MODES = ["strict", "normal", "loose"]

# ==================== 加载模块 ====================
def _load_module(filepath, module_name):
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

BASE = os.path.dirname(os.path.abspath(__file__))
screener = _load_module(os.path.join(BASE, "选股new.py"), "screener")


# ==================== 获取大盘数据 ====================
def get_market_summary():
    indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
    lines = []
    for name, code in indices.items():
        try:
            df = yf.download(code, period="2d", progress=False)
            if df is not None and len(df) >= 2:
                cur = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                pct = (cur / prev - 1) * 100
                lines.append(f"{name}: {cur:.0f} ({pct:+.2f}%)")
            elif df is not None and len(df) == 1:
                cur = float(df['Close'].iloc[-1])
                lines.append(f"{name}: {cur:.0f}")
        except Exception as e:
            lines.append(f"{name}: 获取失败 ({e})")
    return "\n".join(lines)


# ==================== 执行选股 ====================
def run_all_modes():
    """运行三种模式选股，返回 dict"""
    DATA_DIR = screener.DATA_DIR
    cache_files = [f for f in os.listdir(DATA_DIR)
                   if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
    codes = [f.replace('.csv', '') for f in cache_files]
    print(f"待扫描: {len(codes)} 只")

    # 从 CSV 加载数据
    all_data = {}
    today_str = datetime.now().strftime('%Y-%m-%d')
    for code in codes:
        csv_path = os.path.join(DATA_DIR, f"{code}.csv")
        if not os.path.exists(csv_path):
            continue
        try:
            df = pd.read_csv(csv_path)
            if len(df) == 0:
                continue
            df = df.tail(60).copy()
            stock_df = pd.DataFrame({
                'Close': df['close'].values, 'Open': df['open'].values,
                'High': df['high'].values, 'Low': df['low'].values,
                'Volume': df['volume'].values,
            }).dropna()
            if len(stock_df) >= 10:
                all_data[code] = stock_df
        except Exception as e:
            print(f"  ⚠️ {code} 加载失败: {e}")
    print(f"缓存加载: {len(all_data)} 只")

    # 今日注入（轻量）
    print("注入今日数据...")
    BATCH_SIZE = 200
    batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
    injected = 0
    for i, batch in enumerate(batches):
        try:
            hist = yf.download(tickers=batch, period="3d", progress=False)
            if hist is None or hist.empty:
                continue
            try:
                codes_in_batch = set(hist.columns.get_level_values(1))
            except Exception:
                continue
            for code in batch:
                if code not in codes_in_batch:
                    continue
                try:
                    recent = hist.xs(code, level=1, axis=1)
                    recent = recent[recent['Close'].notna() & (recent['Close'] > 0)]
                    if len(recent) == 0:
                        continue
                    if code in all_data:
                        new_rows = pd.DataFrame({
                            'Close': recent['Close'].values, 'Open': recent['Open'].values,
                            'High': recent['High'].values, 'Low': recent['Low'].values,
                            'Volume': recent['Volume'].values,
                        })
                        all_data[code] = pd.concat([all_data[code], new_rows], ignore_index=True).tail(60)
                    else:
                        all_data[code] = recent[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                    injected += 1
                except Exception as e:
                    print(f"  ⚠️ {code} 今日注入失败: {e}")
        except Exception as e:
            print(f"  ⚠️ 批次 {i+1}/{len(batches)} 下载失败: {e}")
    print(f"今日注入: {injected} 只")

    # 三种模式筛选
    results = {}
    for mode in MODES:
        original = screener.PARAMS.copy()
        screener.PARAMS.update(screener.SCREEN_MODES[mode])

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
            except Exception as e:
                print(f"  ⚠️ {code} 筛选失败: {e}")

        screener.PARAMS.update(original)
        results[mode] = candidates
        print(f"{mode}: {len(candidates)} 只候选")

    return results


# ==================== 格式化消息 ====================
def format_message(results):
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    market = get_market_summary()

    total = sum(len(v) for v in results.values())
    mode_names = {"strict": "🔴严格", "normal": "🟡正常", "loose": "🟢宽松"}

    lines = [
        f"📈 A股连板回调 · {today}",
        "",
        "━━ 📊 大盘 ━━",
        market,
        "",
        f"━━ 📋 选股结果（共 {total} 只）━━",
    ]

    for mode in MODES:
        name = mode_names.get(mode, mode)
        cands = results[mode]
        if cands:
            lines.append(f"\n{name} ({len(cands)}只):")
            for c in cands:
                lines.append(
                    f"  {c['code']} | {c['price']:.2f}元 | "
                    f"回调{c['pullback_pct']:.1f}% | "
                    f"{c['limit_days']}连板 | "
                    f"实体{c['entity_ratio']:.0f}%"
                )
        else:
            lines.append(f"\n{name}: 无候选")

    if total == 0:
        lines.append("\n💤 今日无信号，休息。")

    return "\n".join(lines)


# ==================== 微信推送 ====================
def send_wechat(title, content):
    """通过 Server酱 推送到微信"""
    if not SENDKEY:
        print("\n⚠️ 未设置 SENDKEY，跳过微信推送")
        print("  注册 https://sct.ftqq.com/ 获取 SendKey")
        return False

    try:
        url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
        resp = requests.post(url, data={
            "title": title,
            "desp": content,
        }, timeout=15)
        result = resp.json()
        if result.get("code") == 0:
            print("✅ 微信推送成功")
            return True
        else:
            print(f"❌ 推送失败: {result}")
            return False
    except Exception as e:
        print(f"❌ 推送异常: {e}")
        return False


# ==================== 主流程 ====================
def main():
    print("=" * 50)
    print(f"🚀 自动选股启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 选股
    results = run_all_modes()

    # 格式化消息
    msg = format_message(results)
    print("\n" + msg)

    # 推送微信
    total = sum(len(v) for v in results.values())
    emoji = "🔔" if total > 0 else "💤"
    send_wechat(f"{emoji} 选股结果 {datetime.now().strftime('%m/%d')}", msg)

    # 保存本地
    result_dir = os.path.join(BASE, "auto_results")
    os.makedirs(result_dir, exist_ok=True)
    result_path = os.path.join(result_dir, f"auto_result_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")
    with open(result_path, "w") as f:
        f.write(msg)
    print("\n✅ 完成")


if __name__ == "__main__":
    main()

# ==================== 设置定时运行 ====================
#
# macOS (推荐 launchd):
#   1. 创建文件 ~/Library/LaunchAgents/com.stock.screen.plist
#   2. 内容如下（每天 15:30 执行）:
#
#   <?xml version="1.0" encoding="UTF-8"?>
#   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
#     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
#   <plist version="1.0">
#   <dict>
#       <key>Label</key>
#       <string>com.stock.screen</string>
#       <key>ProgramArguments</key>
#       <array>
#           <string>/Users/mattsmacair/micromamba/bin/python3</string>
#           <string>/Users/mattsmacair/Desktop/Coding/量化模型/抓反弹策略/auto_daily.py</string>
#       </array>
#       <key>StartCalendarInterval</key>
#       <dict>
#           <key>Hour</key><integer>15</integer>
#           <key>Minute</key><integer>30</integer>
#       </dict>
#       <key>EnvironmentVariables</key>
#       <dict>
#           <key>SENDKEY</key>
#           <string>你的SendKey</string>
#           <key>DEEPSEEK_API_KEY</key>
#           <string>你的DeepSeekKey</string>
#       </dict>
#       <key>StandardOutPath</key>
#       <string>/tmp/stock_screen.log</string>
#       <key>StandardErrorPath</key>
#       <string>/tmp/stock_screen.err</string>
#   </dict>
#   </plist>
#
#   3. 加载: launchctl load ~/Library/LaunchAgents/com.stock.screen.plist
#   4. 卸载: launchctl unload ~/Library/LaunchAgents/com.stock.screen.plist
#
# 或者用 crontab:
#   1. crontab -e
#   2. 添加: 30 15 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py >> /tmp/stock.log 2>&1
