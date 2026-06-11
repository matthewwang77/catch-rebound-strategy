"""
第二层：AI深度分析
输入：第一层筛选出的股票代码
输出：结构化的AI分析报告
"""
import yfinance as yf
import pandas as pd
from datetime import datetime
import requests
import os

# ==================== 配置区 ====================
# DeepSeek API 配置（注册地址：https://platform.deepseek.com，通过环境变量设置）
#   export DEEPSEEK_API_KEY="你的key"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# ==================== 创建日期文件夹 ====================
def create_date_folder():
    """创建以今天日期命名的文件夹"""
    today = datetime.now().strftime('%Y%m%d')
    folder_name = f"analysis_{today}"
    
    # 如果文件夹不存在则创建
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)
        print(f"📁 创建文件夹：{folder_name}")
    else:
        print(f"📁 使用已有文件夹：{folder_name}")
    
    return folder_name

# ==================== 1. 获取候选股实时数据 ====================
def get_stock_info(code):
    """获取一只股票的实时数据和技术指标"""
    try:
        ticker = yf.Ticker(code)
        
        # 最近60天日线数据（用于技术指标）
        df = ticker.history(period="60d")
        if df is None or len(df) == 0:
            return None
        
        # 最近几天数据
        recent = df.tail(10)
        
        # 计算技术指标
        close = df['Close']
        
        # 均线
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        
        # 成交量
        vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
        vol_ma20 = df['Volume'].rolling(20).mean().iloc[-1]
        vol_today = df['Volume'].iloc[-1]
        vol_yesterday = df['Volume'].iloc[-2] if len(df) >= 2 else vol_today
        
        # 涨跌幅
        pct_chg = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) >= 2 else 0
        
        # 振幅
        high_low_range = (df['High'].iloc[-1] / df['Low'].iloc[-1] - 1) * 100
        
        # 近期最高价和当前价格
        recent_high = df['High'].tail(20).max()
        current_price = close.iloc[-1]
        drawdown = (recent_high - current_price) / recent_high * 100
        
        # 整理成文本
        info = f"""
【{code} 技术数据】
- 今日收盘：{current_price:.2f}
- 今日涨跌幅：{pct_chg:.2f}%
- 今日振幅：{high_low_range:.2f}%
- 成交量/5日均量：{vol_today/vol_ma5:.2f}倍
- 成交量/20日均量：{vol_today/vol_ma20:.2f}倍
- 5日均线：{ma5:.2f}
- 10日均线：{ma10:.2f}
- 20日均线：{ma20:.2f}
- 近20日最高价：{recent_high:.2f}
- 距20日高点回撤：{drawdown:.2f}%
- 近5日走势：{recent['Close'].tail(5).tolist()}
"""
        return info
        
    except Exception as e:
        return f"获取 {code} 数据失败: {e}"

# ==================== 2. 获取同板块/题材联动信息 ====================
def get_sector_info(code):
    """获取简单板块信息（通过yfinance）"""
    try:
        ticker = yf.Ticker(code)
        info = ticker.info
        
        sector = info.get('sector', '未知')
        industry = info.get('industry', '未知')
        market_cap = info.get('marketCap', 0)
        
        return f"板块：{sector} | 行业：{industry} | 市值：{market_cap/1e8:.0f}亿"
    except:
        return "板块信息获取失败"

# ==================== 3. 调用DeepSeek API ====================
def analyze_with_ai(stock_code, technical_data, sector_info, market_context=""):
    """将股票数据喂给DeepSeek，获取深度分析"""
    
    prompt = f"""你是一位专业的A股短线分析师，专注于连板股的回调反弹策略。

以下是候选股票 {stock_code} 的详细数据，请进行深度分析：

{technical_data}

【板块信息】
{sector_info}

【市场环境】
{market_context}

请严格按照以下格式输出分析报告：

## 一、技术面评估
- 当前支撑位和压力位在哪里？给出具体价格
- 量价配合是否健康？
- 短期均线排列状态

## 二、反弹潜力评估
- 该股当前处于回调的什么阶段？（初期/中期/末期）
- 是否有止跌企稳信号？
- 反弹概率评估（低/中/高），并说明理由

## 三、风险提示
- 主要的下跌风险是什么？
- 有没有利空因素需要注意？

## 四、明日观察锚点
- 如果明天高开在哪个价位以上，可以高看一眼？
- 如果低开在哪个价位以下，应该放弃？
- 建议的入场区间

## 五、综合建议
- 该股在当前时点是否值得参与回调反弹？
- 如果参与，建议仓位比例（保守/激进）
- 止损位和止盈位的建议
"""
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "你是一位专业的A股短线分析师，分析风格务实、直接，不模棱两可。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            return f"API返回异常：{result}"
            
    except Exception as e:
        return f"API调用失败：{e}"

# ==================== 4. 分析单只股票 ====================
def analyze_single_stock(stock_code, folder_name, market_context=""):
    """对单只候选股票执行完整分析流程"""
    print(f"\n{'='*60}")
    print(f"正在分析：{stock_code}")
    print(f"{'='*60}")
    
    # 获取技术数据
    print("  📊 获取技术数据...")
    technical_data = get_stock_info(stock_code)
    if technical_data is None:
        print(f"  ❌ 获取数据失败，跳过")
        return None
    
    # 获取板块信息
    print("  📋 获取板块信息...")
    sector_info = get_sector_info(stock_code)
    
    # 调用AI分析
    print("  🤖 调用AI深度分析...")
    analysis = analyze_with_ai(stock_code, technical_data, sector_info, market_context)
    
    # 保存报告到日期文件夹
    report_filename = f"{stock_code.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path = os.path.join(folder_name, report_filename)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"股票：{stock_code}\n")
        f.write(f"分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*60}\n\n")
        f.write(analysis)
    
    print(f"  ✅ 分析报告已保存至：{report_path}")
    
    return analysis

# ==================== 5. 市场环境评估 ====================
def get_market_context():
    """获取当前大盘环境简述"""
    try:
        # 上证指数
        sh = yf.Ticker("000001.SS")
        sh_df = sh.history(period="5d")
        
        # 创业板
        cy = yf.Ticker("399006.SZ")
        cy_df = cy.history(period="5d")
        
        context = f"""
上证指数近5日：{sh_df['Close'].tolist()}
创业板指近5日：{cy_df['Close'].tolist()}
市场情绪判断：请根据以上数据判断当前市场偏强还是偏弱。
"""
        return context
    except:
        return "市场数据获取失败"

# ==================== 6. 生成汇总报告 ====================
def generate_summary_report(all_reports, folder_name, candidate_codes):
    """生成汇总报告，包含所有股票分析的要点"""
    summary_path = os.path.join(folder_name, f"summary_{datetime.now().strftime('%Y%m%d')}.txt")
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"{'='*60}\n")
        f.write(f"AI深度分析汇总报告\n")
        f.write(f"分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"分析股票数量：{len(candidate_codes)} 只\n")
        f.write(f"成功分析：{len(all_reports)} 只\n")
        f.write(f"失败：{len(candidate_codes) - len(all_reports)} 只\n")
        f.write(f"{'='*60}\n\n")
        
        for code in candidate_codes:
            if code in all_reports:
                f.write(f"\n{'='*60}\n")
                f.write(f"【{code}】分析摘要\n")
                f.write(f"{'='*60}\n")
                # 提取报告的前1000字作为摘要
                report_preview = all_reports[code][:1000]
                f.write(report_preview)
                f.write("\n...(完整报告见单独文件)\n")
            else:
                f.write(f"\n【{code}】分析失败\n")
    
    print(f"\n📊 汇总报告已保存至：{summary_path}")

# ==================== 7. 主流程 ====================
def run_ai_analysis(candidate_codes):
    """
    对候选股票列表逐一进行AI深度分析
    
    参数：
        candidate_codes: 股票代码列表，如 ['000001.SZ', '600000.SS']
    """
    print("=" * 60)
    print("第二层：AI深度分析")
    print("=" * 60)
    print(f"候选股票：{len(candidate_codes)} 只")
    print(f"候选列表：{candidate_codes}")
    
    # 创建日期文件夹
    folder_name = create_date_folder()
    
    # 获取市场环境
    print("\n📈 获取大盘环境...")
    market_context = get_market_context()
    
    # 保存市场环境到文件
    market_file = os.path.join(folder_name, f"market_context_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(market_file, 'w', encoding='utf-8') as f:
        f.write(f"市场环境快照\n分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*60}\n")
        f.write(market_context)
    print(f"  💾 市场环境已保存至：{market_file}")
    
    # 逐只分析
    all_reports = {}
    for code in candidate_codes:
        report = analyze_single_stock(code, folder_name, market_context)
        if report:
            all_reports[code] = report
    
    # 生成汇总报告
    if all_reports:
        generate_summary_report(all_reports, folder_name, candidate_codes)
    
    # 最终输出
    print(f"\n{'='*60}")
    print(f"🎉 分析完成！")
    print(f"📁 所有文件已保存至文件夹：{folder_name}")
    print(f"📊 共生成 {len(all_reports)} 份个股分析报告 + 1 份汇总报告")
    print(f"{'='*60}")
    
    # 打印预览
    for code, report in all_reports.items():
        print(f"\n--- {code} 分析预览 ---")
        print(report[:500])  # 打印前500字预览
        print(f"...(完整报告见 {folder_name} 文件夹)")
    
    return all_reports

# ==================== 运行入口 ====================
if __name__ == "__main__":
    # 候选股票列表（从第一层筛选结果中获取）
    # 示例：假设今天量化模型选了这几只
    CANDIDATE_CODES = ['000567.SZ', '000402.SZ']
    
    print("⚠️ 请先确保 DEEPSEEK_API_KEY 为你的真实API Key")
    print("⚠️ 请替换 CANDIDATE_CODES 为第一层筛选出的股票\n")
    
    if not DEEPSEEK_API_KEY:
        print("❌ 请先设置 DeepSeek API Key 环境变量:")
        print("   export DEEPSEEK_API_KEY=\"你的key\"")
        print("   注册地址：https://platform.deepseek.com")
    else:
        run_ai_analysis(CANDIDATE_CODES)