"""
每日自动选股
用法: python auto_daily.py

首次使用: 设置定时运行（见文件末尾说明）
"""
import yfinance as yf
import pandas as pd
from datetime import datetime
import os
import sys
import importlib.util

# 选股模式
MODES = ["strict", "loose"]

# ==================== 加载模块 ====================
def _load_module(filepath, module_name):
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

BASE = os.path.dirname(os.path.abspath(__file__))  # project root
screener = _load_module(os.path.join(BASE, "选股new_v5.py"), "screener")


# ==================== 获取大盘数据 ====================
def get_market_summary():
    indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
    lines = []
    for name, code in indices.items():
        try:
            df = yf.download(code, period="2d", progress=False)
            if df is not None and len(df) >= 2:
                close_col = df['Close']
                if hasattr(close_col, 'iloc'):
                    cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                    prev = float(close_col.iloc[-2].item() if hasattr(close_col.iloc[-2], 'item') else close_col.iloc[-2])
                else:
                    cur = float(close_col.values[-1] if hasattr(close_col, 'values') else close_col[-1])
                    prev = float(close_col.values[-2] if hasattr(close_col, 'values') else close_col[-2])
                pct = (cur / prev - 1) * 100
                lines.append(f"{name}: {cur:.0f} ({pct:+.2f}%)")
            elif df is not None and len(df) == 1:
                close_col = df['Close']
                if hasattr(close_col, 'iloc'):
                    cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                else:
                    cur = float(close_col.values[-1] if hasattr(close_col, 'values') else close_col[-1])
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
            # 保留日期作为索引（_screen_single_stock 需要 DatetimeIndex 生成 trade_date）
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            stock_df = pd.DataFrame({
                'Close': df['close'].values, 'Open': df['open'].values,
                'High': df['high'].values, 'Low': df['low'].values,
                'Volume': df['volume'].values,
            }, index=df.index).dropna()
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
                        # 保留 DatetimeIndex，确保 _screen_single_stock 能生成正确的 trade_date
                        new_rows = recent[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                        all_data[code] = pd.concat([all_data[code], new_rows]).tail(60)
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
    mode_names = {"strict": "🔴严格", "loose": "🟢宽松"}

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


# ==================== JSON 结果保存 ====================
def save_results_json(results):
    """保存结构化 JSON 结果，供 Streamlit 自动加载"""
    import json

    now = datetime.now()
    # 解析大盘数据
    market = {}
    try:
        indices = {"上证": "000001.SS", "深证": "399001.SZ", "创业板": "399006.SZ"}
        for name, code in indices.items():
            df = yf.download(code, period="2d", progress=False)
            if df is not None and len(df) >= 2:
                close_col = df['Close']
                if hasattr(close_col, 'iloc'):
                    cur = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                    prev = float(close_col.iloc[-2].item() if hasattr(close_col.iloc[-2], 'item') else close_col.iloc[-2])
                else:
                    cur = float(close_col.values[-1] if hasattr(close_col, 'values') else close_col[-1])
                    prev = float(close_col.values[-2] if hasattr(close_col, 'values') else close_col[-2])
                market[name] = {
                    "price": round(cur, 2),
                    "pct": round((cur / prev - 1) * 100, 2),
                }
    except Exception:
        pass

    output = {
        "scan_time": now.strftime("%Y-%m-%d %H:%M"),
        "scan_date": now.strftime("%Y%m%d"),
        "market": market,
        "modes": {},
    }
    for mode, candidates in results.items():
        output["modes"][mode] = {
            "count": len(candidates),
            "candidates": [
                {
                    "code": c.get("code", c.get("代码", "")),
                    "price": c.get("price", c.get("最新价", 0)),
                    "signal_date": c.get("signal_date", ""),
                    "pullback_pct": c.get("pullback_pct", c.get("回调比", 0)),
                    "limit_days": c.get("limit_days", c.get("连板数", 0)),
                    "entity_ratio": c.get("entity_ratio", 0),
                }
                for c in candidates
            ],
        }

    # 保存最新结果（项目根目录）
    latest_path = os.path.join(BASE, "latest_scan_results.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 保存历史归档
    archive_dir = os.path.join(BASE, "results_archive")
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{now.strftime('%Y%m%d')}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(v["count"] for v in output["modes"].values())
    print(f"📁 JSON 保存: {latest_path} ({total} 只候选)")
    print(f"📁 历史归档: {archive_path}")


# ==================== 主流程 ====================
def git_push_results():
    """自动 commit + push 结果到 GitHub，供 Streamlit Cloud 更新"""
    import subprocess
    try:
        cwd = BASE
        # git add 结果文件
        subprocess.run(
            ["git", "add", "latest_scan_results.json", "results_archive/"],
            cwd=cwd, capture_output=True, timeout=10,
        )
        # git commit
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        result = subprocess.run(
            ["git", "commit", "-m", f"auto: scan results {ts}"],
            cwd=cwd, capture_output=True, timeout=10,
        )
        # 如果有变更才 push
        if b"nothing to commit" not in result.stdout and b"nothing to commit" not in result.stderr:
            subprocess.run(
                ["git", "push", "origin", "master"],
                cwd=cwd, capture_output=True, timeout=30,
            )
            print("✅ Git push 完成，Streamlit Cloud 将自动更新")
        else:
            print("📁 结果无变化，跳过 push")
    except Exception as e:
        print(f"⚠️ Git push 失败: {e}（不影响选股结果）")


def main():
    print("=" * 50)
    print(f"🚀 自动选股启动: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 选股
    results = run_all_modes()

    # 保存 JSON（供 Streamlit 读取）
    save_results_json(results)

    # 格式化消息
    msg = format_message(results)
    print("\n" + msg)

    # 保存文本日志
    result_dir = os.path.join(BASE, "auto_logs")
    os.makedirs(result_dir, exist_ok=True)
    result_path = os.path.join(result_dir, f"auto_result_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")
    with open(result_path, "w") as f:
        f.write(msg)

    # 自动 push 到 GitHub（Streamlit Cloud 更新）
    git_push_results()

    print("\n✅ 完成")


if __name__ == "__main__":
    main()

# ==================== 设置定时运行 ====================
#
# macOS (推荐 launchd):
#   1. 创建文件 ~/Library/LaunchAgents/com.grab_rebound.screen.plist
#   2. 内容如下（交易日 10:00 / 11:30 / 14:00 / 15:00 执行）:
#
#   <?xml version="1.0" encoding="UTF-8"?>
#   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
#     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
#   <plist version="1.0">
#   <dict>
#       <key>Label</key>
#       <string>com.grab_rebound.screen</string>
#       <key>ProgramArguments</key>
#       <array>
#           <string>/Users/mattsmacair/micromamba/bin/python3</string>
#           <string>/Users/mattsmacair/Desktop/Coding/量化模型/抓反弹策略/auto_daily.py</string>
#       </array>
#       <key>StartCalendarInterval</key>
#       <array>
#           <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
#           <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>30</integer></dict>
#           <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer></dict>
#           <dict><key>Hour</key><integer>15</key><key>Minute</key><integer>0</integer></dict>
#       </array>
#       <key>EnvironmentVariables</key>
#       <dict>
#           <key>DEEPSEEK_API_KEY</key>
#           <string>你的DeepSeekKey</string>
#       </dict>
#       <key>StandardOutPath</key>
#       <string>/tmp/grab_rebound_screen.log</string>
#       <key>StandardErrorPath</key>
#       <string>/tmp/grab_rebound_screen.err</string>
#   </dict>
#   </plist>
#
#   3. 加载: launchctl load ~/Library/LaunchAgents/com.grab_rebound.screen.plist
#   4. 卸载: launchctl unload ~/Library/LaunchAgents/com.grab_rebound.screen.plist
#
# 或者用 crontab:
#   1. crontab -e
#   2. 添加: 0 10 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
#           30 11 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
#           0 14 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
#           0 15 * * 1-5 cd /path/to/抓反弹策略 && python3 auto_daily.py
