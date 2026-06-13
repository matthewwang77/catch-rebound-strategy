"""
A股连板回调策略 - Streamlit UI  |  NEON VAULT Edition
一键运行：streamlit run streamlit_app.py

功能：
  - 同时展示 strict/loose 两种模式选股结果（v5 参数）
  - 大盘指数实时概览
  - 每只候选股票一键 AI 深度分析
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import json
from datetime import datetime, timedelta
import time
import os
import sys
import importlib.util

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="A股连板回调策略 · NEON VAULT",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==================== 🎨 NEON VAULT 设计系统 ====================
def inject_design_system():
    """注入完整的设计系统 CSS —— Cyber Trading Terminal 美学

    使用 st.markdown(unsafe_allow_html=True) 注入 <style> + Google Fonts。
    这是 Streamlit 社区验证的 CSS 注入方式，st.html() 会过滤掉 style 标签。
    """
    css = r"""
    <style>
    /* ============================================================
       NEON VAULT v2 — Quantum Trading Terminal
       ============================================================ */

    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=Share+Tech+Mono&display=swap');

    :root {
      --cyan: #00F0FF;
      --purple: #7B2FFF;
      --green: #00FF88;
      --red: #FF3366;
      --amber: #FFB800;
      --bg: #050508;
      --surface: #0A0B14;
      --card: rgba(13, 13, 30, 0.9);
    }

    /* === BASE === */
    html, body, #root, [data-testid="stAppViewContainer"] {
      background: #050508 !important;
      color: #D0D0E8 !important;
    }

    body {
      font-family: 'JetBrains Mono', 'SF Mono', monospace !important;
    }

    /* === ANIMATED DOT GRID BACKGROUND === */
    [data-testid="stAppViewContainer"] {
      background-color: #050508 !important;
      background-image:
        radial-gradient(circle, rgba(0,240,255,0.06) 1px, transparent 1px),
        radial-gradient(circle at 20% 30%, rgba(123,47,255,0.04) 0%, transparent 50%),
        radial-gradient(circle at 80% 70%, rgba(0,240,255,0.03) 0%, transparent 50%),
        radial-gradient(circle at 50% 10%, rgba(0,240,255,0.05) 0%, transparent 40%);
      background-size: 20px 20px, 100% 100%, 100% 100%, 100% 100%;
      background-position: 0 0, 0 0, 0 0, 0 0;
    }

    /* === SCAN LINES === */
    [data-testid="stAppViewContainer"]::after {
      content: '';
      position: fixed;
      inset: 0;
      background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.025) 2px, rgba(0,0,0,0.025) 4px);
      pointer-events: none;
      z-index: 99999;
    }

    /* === SCROLLBAR === */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: #050508; }
    ::-webkit-scrollbar-thumb { background: rgba(0,240,255,0.15); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(0,240,255,0.35); }

    /* === HEADINGS === */
    h1, h2, h3 {
      font-family: 'Orbitron', 'Helvetica Neue', sans-serif !important;
      text-transform: uppercase;
      letter-spacing: 0.05em !important;
    }

    h1 {
      font-weight: 900 !important;
      font-size: 2.4rem !important;
      text-align: center;
      background: linear-gradient(135deg, #00F0FF 0%, #00E5FF 25%, #7B2FFF 60%, #C44AFF 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      filter: drop-shadow(0 0 18px rgba(0,240,255,0.3));
      padding: 0.25rem 0 0.5rem;
      margin-bottom: 0;
      border-bottom: 2px solid rgba(0,240,255,0.12);
    }

    h2 {
      font-weight: 700 !important;
      font-size: 1.15rem !important;
      color: #00F0FF !important;
      border-left: 3px solid #00F0FF;
      padding-left: 12px !important;
    }

    h3 {
      font-weight: 600 !important;
      font-size: 0.9rem !important;
      color: #B0B0D0 !important;
    }

    /* === BODY TEXT === */
    /* NOTE: span is intentionally excluded to preserve Material Icons font */
    p, div, label, caption, li, td, th, button {
      font-family: 'JetBrains Mono', 'SF Mono', monospace !important;
    }

    [data-testid="stCaption"] {
      font-family: 'JetBrains Mono', 'SF Mono', monospace !important;
      font-size: 0.7rem !important;
      color: #6666AA !important;
    }

    /* === SIDEBAR === */
    [data-testid="stSidebar"] {
      background: linear-gradient(180deg, rgba(8,8,20,0.995) 0%, rgba(5,5,14,0.995) 100%) !important;
      border-right: 1px solid rgba(0,240,255,0.06) !important;
      box-shadow: 2px 0 30px rgba(0,240,255,0.02);
    }

    [data-testid="stSidebar"] h3 {
      font-family: 'Orbitron', sans-serif !important;
      color: #00F0FF !important;
      font-size: 0.85rem !important;
      letter-spacing: 0.1em !important;
    }

    [data-testid="stSidebar"] p { font-size: 0.7rem; color: #7777AA; line-height: 1.7; }

    [data-testid="stSidebar"] [data-testid="stRadio"] label {
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 0.75rem;
      color: #7777AA;
      padding: 10px 14px !important;
      border-radius: 6px;
      border: 1px solid transparent;
      transition: all 0.2s;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
      background: rgba(0,240,255,0.04);
      border-color: rgba(0,240,255,0.2);
      color: #00F0FF;
    }

    [data-testid="stSidebar"] hr { border-color: rgba(0,240,255,0.06) !important; }

    /* === METRIC CARDS === */
    [data-testid="stMetric"] {
      background: linear-gradient(135deg, rgba(13,13,30,0.95) 0%, rgba(10,10,22,0.95) 100%) !important;
      border: 1px solid rgba(0,240,255,0.1) !important;
      border-radius: 12px !important;
      padding: 16px 20px !important;
      position: relative;
      overflow: hidden;
      transition: all 0.3s ease;
    }

    /* Corner accent */
    [data-testid="stMetric"]::before {
      content: '';
      position: absolute;
      top: 0; right: 0;
      width: 30px; height: 30px;
      border-top: 2px solid rgba(0,240,255,0.2);
      border-right: 2px solid rgba(0,240,255,0.2);
      border-radius: 0 12px 0 0;
      transition: all 0.3s ease;
    }

    /* Bottom glow bar */
    [data-testid="stMetric"]::after {
      content: '';
      position: absolute;
      bottom: 0; left: 10%; right: 10%;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(0,240,255,0.3), transparent);
      opacity: 0;
      transition: opacity 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
      border-color: rgba(0,240,255,0.3) !important;
      box-shadow: 0 0 20px rgba(0,240,255,0.15), 0 0 60px rgba(0,240,255,0.05), inset 0 0 30px rgba(0,240,255,0.02);
      transform: translateY(-2px);
    }
    [data-testid="stMetric"]:hover::after { opacity: 1; }
    [data-testid="stMetric"]:hover::before {
      border-color: rgba(0,240,255,0.5);
      box-shadow: 0 0 8px rgba(0,240,255,0.2);
    }

    [data-testid="stMetric"] label {
      font-family: 'Orbitron', sans-serif !important;
      font-size: 0.6rem !important;
      font-weight: 700 !important;
      color: #6666AA !important;
      letter-spacing: 0.1em !important;
    }

    [data-testid="stMetricValue"] {
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 1.8rem !important;
      font-weight: 700 !important;
      color: #E8E8FF !important;
      text-shadow: 0 0 8px rgba(0,240,255,0.15);
    }

    [data-testid="stMetricDelta"] {
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 0.9rem !important;
      font-weight: 600;
    }

    /* === BUTTONS === */
    .stButton > button {
      font-family: 'Orbitron', sans-serif !important;
      font-weight: 600 !important;
      font-size: 0.7rem !important;
      letter-spacing: 0.08em !important;
      text-transform: uppercase;
      border-radius: 8px !important;
      padding: 12px 24px !important;
      transition: all 0.3s ease !important;
    }

    button[kind="primary"] {
      background: linear-gradient(135deg, rgba(0,240,255,0.12), rgba(123,47,255,0.12)) !important;
      border: 1px solid rgba(0,240,255,0.4) !important;
      color: #00F0FF !important;
    }
    button[kind="primary"]:hover {
      background: linear-gradient(135deg, rgba(0,240,255,0.22), rgba(123,47,255,0.22)) !important;
      box-shadow: 0 0 20px rgba(0,240,255,0.3), 0 0 50px rgba(0,240,255,0.1) !important;
      transform: translateY(-2px);
      border-color: #00F0FF !important;
    }

    button[kind="secondary"] {
      background: rgba(13,13,30,0.8) !important;
      border: 1px solid rgba(0,240,255,0.08) !important;
      color: #7777AA !important;
    }
    button[kind="secondary"]:hover {
      background: rgba(0,240,255,0.05) !important;
      border-color: rgba(0,240,255,0.2) !important;
      color: #00F0FF !important;
    }

    .stDownloadButton > button {
      font-family: 'Orbitron', sans-serif !important;
      background: rgba(0,255,136,0.06) !important;
      border: 1px solid rgba(0,255,136,0.25) !important;
      color: #00FF88 !important;
      border-radius: 8px !important;
    }
    .stDownloadButton > button:hover {
      background: rgba(0,255,136,0.12) !important;
      box-shadow: 0 0 15px rgba(0,255,136,0.2) !important;
      border-color: #00FF88 !important;
    }

    /* === TABS === */
    [data-baseweb="tab-list"] {
      background: rgba(10,10,24,0.5) !important;
      border-radius: 10px !important;
      padding: 3px !important;
      gap: 3px !important;
      border: 1px solid rgba(0,240,255,0.06);
    }
    [data-baseweb="tab"] {
      font-family: 'Orbitron', sans-serif !important;
      font-size: 0.65rem !important;
      font-weight: 600 !important;
      letter-spacing: 0.06em !important;
      text-transform: uppercase;
      color: #6666AA !important;
      border-radius: 8px !important;
      padding: 10px 22px !important;
      border: 1px solid transparent;
    }
    [data-baseweb="tab"]:hover { color: #00F0FF; background: rgba(0,240,255,0.03); }
    [data-baseweb="tab"][aria-selected="true"] {
      color: #00F0FF !important;
      background: rgba(0,240,255,0.07) !important;
      border-color: rgba(0,240,255,0.35) !important;
      box-shadow: 0 0 15px rgba(0,240,255,0.2);
    }

    /* === EXPANDERS === */
    [data-testid="stExpander"] {
      background: rgba(13,13,30,0.9) !important;
      border: 1px solid rgba(0,240,255,0.08) !important;
      border-radius: 10px !important;
      margin: 6px 0;
      transition: all 0.3s ease;
    }
    [data-testid="stExpander"]:hover { border-color: rgba(0,240,255,0.2); }
    [data-testid="stExpander"] summary {
      font-size: 0.72rem !important;
      font-weight: 600;
      color: #00F0FF !important;
      padding: 10px 16px !important;
      display: flex !important;
      align-items: center;
    }
    /* Expander icon styling */
    [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {
      font-size: 1.1rem !important;
      color: #00F0FF !important;
      margin-right: 6px;
    }

    /* === TABLES === */
    [data-testid="stDataFrame"] {
      border: 1px solid rgba(0,240,255,0.06) !important;
      border-radius: 10px !important;
      background: rgba(13,13,30,0.85) !important;
      overflow: hidden;
    }
    [data-testid="stDataFrame"] thead th {
      font-family: 'Orbitron', sans-serif !important;
      font-size: 0.6rem !important;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #00F0FF !important;
      background: rgba(0,240,255,0.03) !important;
      border-bottom: 1px solid rgba(0,240,255,0.15) !important;
      padding: 12px 16px !important;
    }
    [data-testid="stDataFrame"] tbody td {
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 0.72rem;
      color: #D0D0E8;
      padding: 10px 16px;
      border-bottom: 1px solid rgba(255,255,255,0.02);
    }
    [data-testid="stDataFrame"] tbody tr:hover td { background: rgba(0,240,255,0.025); }

    /* === PROGRESS === */
    .stProgress > div > div {
      background: linear-gradient(90deg, #00F0FF, #7B2FFF) !important;
      border-radius: 2px;
      box-shadow: 0 0 6px rgba(0,240,255,0.3);
    }
    .stProgress > div {
      background: rgba(0,240,255,0.04) !important;
      border-radius: 2px;
      border: 1px solid rgba(0,240,255,0.06);
    }

    /* === DIVIDERS === */
    hr, [data-testid="stDivider"] {
      border: none !important;
      height: 1px !important;
      background: linear-gradient(90deg, transparent, rgba(0,240,255,0.12) 20%, rgba(0,240,255,0.25) 50%, rgba(0,240,255,0.12) 80%, transparent) !important;
    }

    /* === INPUTS === */
    input[data-testid="stTextInput"], textarea {
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 0.75rem;
      background: rgba(8,8,20,0.8) !important;
      border: 1px solid rgba(0,240,255,0.08) !important;
      border-radius: 8px !important;
      color: #D0D0E8 !important;
    }
    input[data-testid="stTextInput"]:focus, textarea:focus {
      border-color: rgba(0,240,255,0.35) !important;
      box-shadow: 0 0 15px rgba(0,240,255,0.08) !important;
    }
    textarea::placeholder { color: #444477; }

    /* === ALERTS === */
    [data-testid="stAlert"] {
      font-family: 'JetBrains Mono', monospace !important;
      border-radius: 10px !important;
      border: 1px solid rgba(0,240,255,0.06) !important;
      background: rgba(13,13,30,0.85) !important;
    }

    [data-testid="stNotification"] {
      background: rgba(8,8,24,0.98) !important;
      border: 1px solid rgba(0,240,255,0.35) !important;
      border-radius: 10px !important;
      backdrop-filter: blur(20px);
    }

    /* === ANIMATIONS === */
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes scanPulse {
      0%, 100% { border-color: rgba(0,240,255,0.1); }
      50% { border-color: rgba(0,240,255,0.35); }
    }

    [data-testid="stMetric"] { animation: fadeUp 0.5s ease-out both; }
    [data-testid="stMetric"]:nth-child(1) { animation-delay: 0.05s; }
    [data-testid="stMetric"]:nth-child(2) { animation-delay: 0.1s; }
    [data-testid="stMetric"]:nth-child(3) { animation-delay: 0.15s; }

    @media (max-width: 768px) {
      h1 { font-size: 1.6rem !important; }
      [data-testid="stMetricValue"] { font-size: 1.3rem !important; }
    }

    /* === NAV CARDS (sidebar) — 大卡片 === */
    .nav-card {
      padding: 20px 12px;
      border-radius: 12px;
      border: 1px solid rgba(0,240,255,0.08);
      background: rgba(10,11,20,0.9);
      text-align: center;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      color: #555588;
      cursor: pointer;
      transition: all 0.25s ease;
      user-select: none;
      margin-bottom: 6px;
    }
    .nav-card:hover {
      background: rgba(0,240,255,0.05);
      border-color: rgba(0,240,255,0.3);
      color: #00F0FF;
      transform: translateY(-2px);
      box-shadow: 0 4px 20px rgba(0,240,255,0.06);
    }
    .nav-card.active {
      background: rgba(0,240,255,0.1);
      border-color: rgba(0,240,255,0.6);
      color: #00F0FF;
      box-shadow: 0 0 20px rgba(0,240,255,0.12), inset 0 0 20px rgba(0,240,255,0.04);
    }
    .nav-card .card-icon {
      font-size: 1.5rem;
      display: block;
      margin-bottom: 6px;
    }
    .nav-card .card-label {
      font-size: 0.7rem;
      letter-spacing: 0.08em;
    }

    /* === MODE PILLS === */
    .mode-pills-row {
      display: flex;
      gap: 8px;
      align-items: center;
      margin: 8px 0 12px 0;
    }
    .mode-pills-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.55rem;
      color: #5555AA;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .mode-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.6rem;
      padding: 4px 12px;
      border-radius: 14px;
      cursor: help;
      transition: all 0.2s;
    }
    .mode-pill.strict {
      background: rgba(255,51,102,0.08);
      border: 1px solid rgba(255,51,102,0.22);
      color: #FF3366;
    }
    .mode-pill.strict:hover {
      background: rgba(255,51,102,0.14);
      border-color: rgba(255,51,102,0.4);
      box-shadow: 0 0 8px rgba(255,51,102,0.1);
    }
    .mode-pill.loose {
      background: rgba(0,255,136,0.06);
      border: 1px solid rgba(0,255,136,0.18);
      color: #00FF88;
    }
    .mode-pill.loose:hover {
      background: rgba(0,255,136,0.12);
      border-color: rgba(0,255,136,0.35);
      box-shadow: 0 0 8px rgba(0,255,136,0.08);
    }

    /* === NEON STATUS BAR === */
    .neon-status-bar {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 18px;
      border-radius: 8px;
      font-family: 'JetBrains Mono', monospace;
      margin: 10px 0 14px 0;
    }
    .neon-status-bar.closed {
      background: rgba(0,240,255,0.025);
      border: 1px solid rgba(0,240,255,0.2);
    }
    .neon-status-bar.trading {
      background: rgba(255,184,0,0.025);
      border: 1px solid rgba(255,184,0,0.22);
    }
    .neon-status-bar .status-icon { font-size: 1rem; }
    .neon-status-bar .status-text { font-size: 0.7rem; }
    .neon-status-bar.closed .status-text { color: #00F0FF; }
    .neon-status-bar.trading .status-text { color: #FFB800; }
    .neon-status-bar .status-spacer { flex: 1; }
    .neon-status-bar .status-label { font-size: 0.55rem; color: #6666AA; }
    .neon-status-bar .status-time { font-size: 0.65rem; color: #9999CC; }
    .pulse-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .pulse-dot.cyan {
      background: #00F0FF;
      box-shadow: 0 0 6px #00F0FF;
    }
    .pulse-dot.amber {
      background: #FFB800;
      box-shadow: 0 0 6px #FFB800;
    }

    /* === AI ANALYSIS EXPANDER === */
    .ai-summary-strip {
      display: flex;
      gap: 10px;
      padding: 12px 16px;
      border-bottom: 1px solid rgba(0,240,255,0.08);
      flex-wrap: wrap;
      background: rgba(0,240,255,0.015);
      border-radius: 8px 8px 0 0;
    }
    .ai-summary-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.62rem;
      padding: 6px 12px;
      border-radius: 6px;
      white-space: nowrap;
      letter-spacing: 0.04em;
    }
    .ai-summary-badge.sentiment {
      background: rgba(0,240,255,0.08);
      border: 1px solid rgba(0,240,255,0.15);
      color: #00F0FF;
    }
    .ai-summary-badge.position {
      background: rgba(0,255,136,0.08);
      border: 1px solid rgba(0,255,136,0.15);
      color: #00FF88;
    }
    .ai-summary-badge.opinion {
      background: rgba(123,47,255,0.08);
      border: 1px solid rgba(123,47,255,0.15);
      color: #7B2FFF;
    }

    /* === SIDEBAR DATA STATUS === */
    .sidebar-data-status {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.62rem;
      color: #7777AA;
      padding: 10px 12px;
      border-radius: 8px;
      background: rgba(0,240,255,0.02);
      border: 1px solid rgba(0,240,255,0.06);
      line-height: 1.8;
    }
    .sidebar-data-status .stat-label {
      color: #555588;
      font-size: 0.55rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }
    .sidebar-data-status .stat-value {
      color: #9999CC;
    }
    .sidebar-data-status .stat-highlight {
      color: #00F0FF;
    }

    /* === 复盘页面: 记忆卡片 hover === */
    .memory-card-hover {
      transition: background 0.2s;
    }
    .memory-card-hover:hover {
      background: rgba(0,240,255,0.02);
    }

    </style>
    """

    # st.markdown(unsafe_allow_html=True) 是 Streamlit 中注入 <style> 的可靠方式
    st.markdown(css, unsafe_allow_html=True)


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
    """加载选股new_v5.py（缓存，避免重复加载）"""
    base = os.path.dirname(os.path.abspath(__file__))

    screener = _load_module(os.path.join(base, "选股new_v5.py"), "screener")

    return screener


screener = load_modules()

# ==================== 北京时间工具 ====================
from zoneinfo import ZoneInfo
TZ_CHINA = ZoneInfo("Asia/Shanghai")

def china_now():
    """返回北京时间 datetime"""
    return datetime.now(TZ_CHINA)

def china_today_str():
    """返回北京时间日期字符串 YYYYMMDD"""
    return china_now().strftime('%Y%m%d')

def china_today_dtstr():
    """返回北京时间日期字符串 YYYY-MM-DD"""
    return china_now().strftime('%Y-%m-%d')

# ==================== 名称/板块查询 ====================
import name_lookup

# ==================== 大盘数据 ====================
@st.cache_data(ttl=300, show_spinner=False)
def get_market_data():
    """获取三大指数最新数据（包含涨跌幅）"""
    indices = {
        "上证指数": "000001.SS",
        "深证成指": "399001.SZ",
        "创业板指": "399006.SZ",
    }
    result = {}
    for name, code in indices.items():
        data = None
        for attempt in range(2):
            try:
                ticker = yf.Ticker(code)
                # 同时获取日线数据（用于涨跌幅和5日高低）
                df = ticker.history(period="1mo")
                has_history = df is not None and len(df) >= 2

                # 获取当前价格
                current = None
                try:
                    info = ticker.fast_info
                    current = info.get('lastPrice') or info.get('regularMarketPrice')
                except Exception:
                    pass
                if not current and has_history:
                    current = float(df['Close'].iloc[-1])
                if not current:
                    continue

                current = float(current)
                high_5d = float(df['High'].tail(5).max()) if has_history else current
                low_5d = float(df['Low'].tail(5).min()) if has_history else current

                if has_history:
                    prev = float(df['Close'].iloc[-2])
                    pct = round((current / prev - 1) * 100, 2)
                    has_delta = True
                    vol_today = float(df['Volume'].iloc[-1])
                    vol_prev = float(df['Volume'].iloc[-2])
                    if vol_prev > 0 and vol_today > 0:
                        ratio = vol_today / vol_prev
                        vol_ratio = round(max(0.01, min(ratio, 100)), 2)
                    else:
                        vol_ratio = 1
                else:
                    # 降级：从 fast_info.previousClose 算涨跌
                    try:
                        prev_close = info.get('previousClose')
                        if prev_close and float(prev_close) > 0:
                            pct = round((current / float(prev_close) - 1) * 100, 2)
                            has_delta = True
                        else:
                            pct, has_delta = 0, False
                    except Exception:
                        pct, has_delta = 0, False
                    vol_ratio = 1

                data = {
                    'code': code, 'price': round(current, 2),
                    'pct': pct, 'has_delta': has_delta,
                    'high_5d': round(high_5d, 2),
                    'low_5d': round(low_5d, 2),
                    'vol_ratio': vol_ratio,
                }
                break
            except Exception:
                time.sleep(1)
        result[name] = data
    return result


# ==================== 极速数据加载（CSV 缓存 + 今日注入 + 过期更新）====================

@st.cache_data(ttl=1800)
def _load_csv_cache(codes_tuple, lookback_days, today_str):
    """纯数据加载，被 st.cache_data 缓存。30 分钟内秒开。"""
    codes = list(codes_tuple)
    DATA_DIR = screener.DATA_DIR
    all_data = {}
    failed = []

    for code in codes:
        csv_path = os.path.join(DATA_DIR, f"{code}.csv")
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) < 100:
            failed.append(code)
            continue
        try:
            df = pd.read_csv(csv_path)
            if len(df) == 0:
                failed.append(code)
                continue
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
    return all_data, failed


def load_all_recent_data(codes, lookback_days=30):
    """三步加载 + 0-100% 进度条"""

    DATA_DIR = screener.DATA_DIR
    today_str = china_now().strftime('%Y-%m-%d')
    today_int = int(china_now().strftime('%Y%m%d'))
    total = len(codes)
    progress_bar = st.progress(0, text="▸ 0% 读取本地缓存...")
    BATCH_SIZE = 200

    # ====== 第一阶段: 0% → 25% 读CSV缓存 ======
    all_data, failed = _load_csv_cache(tuple(codes), lookback_days, today_str)
    progress_bar.progress(15, text=f"▸ 15% 缓存读取完成: {len(all_data)} 只")

    # ====== 第二阶段: 15% → 25% 检查数据新鲜度 ======
    stale_count = 0
    has_today_count = 0
    check_total = len(all_data)
    for i, code in enumerate(all_data):
        if (i + 1) % 1000 == 0:
            progress_bar.progress(15 + int(10 * (i + 1) / check_total),
                                  text=f"▸ {15 + int(10*(i+1)/check_total)}% 检查数据新鲜度 {i+1}/{check_total}...")
        csv_path = os.path.join(DATA_DIR, f"{code}.csv")
        try:
            df = pd.read_csv(csv_path)
            latest_date_str = str(df['date'].iloc[-1])[:10]
            if today_int - int(latest_date_str.replace('-', '')) > 2:
                stale_count += 1
            if latest_date_str == today_str:
                has_today_count += 1
        except Exception:
            pass

    today_coverage = has_today_count / len(all_data) if all_data else 0
    force_refresh = st.session_state.get('force_refresh', False)
    if force_refresh:
        st.session_state['force_refresh'] = False

    progress_bar.progress(25, text=f"▸ 25% 数据检查: {len(all_data)}只 | 今日覆盖{today_coverage:.0%} | {stale_count}只过期")

    # ====== 第三阶段: 25% → 70% 今日数据注入 ======
    skip_injection = (not force_refresh) and (today_coverage > 0.95)
    injected = 0

    if skip_injection:
        progress_bar.progress(70, text=f"▸ 70% 今日数据已齐全({today_coverage:.0%}) ⚡跳过注入")
    else:
        progress_bar.progress(28, text=f"▸ 28% 今日覆盖率{today_coverage:.0%}，拉取最新数据...")
        batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]

        for i, batch in enumerate(batches):
            pct = 28 + int(40 * (i + 1) / len(batches))
            progress_bar.progress(pct, text=f"▸ {pct}% 今日注入 {i+1}/{len(batches)} 批 ({injected}只)...")
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
                            df = all_data[code]
                            new_rows = pd.DataFrame({
                                'Close': recent['Close'].values, 'Open': recent['Open'].values,
                                'High': recent['High'].values, 'Low': recent['Low'].values,
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
        progress_bar.progress(70, text=f"▸ 70% 今日注入完成: {injected} 只")

    # ====== 第四阶段: 70% → 99% 全量刷新（仅过期>30%时触发）======
    if stale_count > len(codes) * 0.3:
        progress_bar.progress(72, text=f"▸ 72% {stale_count}只过期，全量更新中...")
        batches = [codes[i:i + BATCH_SIZE] for i in range(0, len(codes), BATCH_SIZE)]
        updated = 0

        for i, batch in enumerate(batches):
            pct = 72 + int(26 * (i + 1) / len(batches))
            progress_bar.progress(pct, text=f"▸ {pct}% 全量更新 {i+1}/{len(batches)} 批 ({updated}只)...")
            try:
                hist = yf.download(tickers=batch, period="30d", progress=False)
                codes_in_batch = set()
                if hist is not None and not hist.empty:
                    try:
                        codes_in_batch = set(hist.columns.get_level_values(1))
                    except Exception:
                        pass
                for code in batch:
                    if code not in codes_in_batch:
                        continue
                    try:
                        stock_data = hist.xs(code, level=1, axis=1)
                        if stock_data['Close'].dropna().empty:
                            continue
                        csv_path = os.path.join(DATA_DIR, f"{code}.csv")
                        df_old = pd.read_csv(csv_path)
                        new_rows = [
                            {'date': (idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)[:10]),
                             'open': row['Open'], 'high': row['High'],
                             'low': row['Low'], 'close': row['Close'], 'volume': int(row['Volume'])}
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
        progress_bar.progress(98, text=f"▸ 98% CSV更新完成: {updated}只")
        if updated > 0:
            st.toast(f"◆ {updated} 只股票CSV已刷新，下次秒开", icon="✅")
    else:
        progress_bar.progress(98, text=f"▸ 98% CSV无需全量更新(过期{stale_count}只≤30%)")

    # ====== 完成 ======
    progress_bar.progress(100, text=f"▸ 100% 加载完成: {len(all_data)} 只 (注入{injected}只)")
    progress_bar.empty()
    return all_data, failed


# ==================== 云端数据加载（Streamlit Cloud 无本地CSV时使用）====================
@st.cache_data(ttl=86400, show_spinner=False)
def cloud_load_data(version="v5"):
    """云端模式：快照优先 + 5检查点刷新。缓存24h"""
    _ = version
    all_data = {}
    base_dir = os.path.dirname(os.path.abspath(__file__))
    snapshot_path = os.path.join(base_dir, "stock_snapshot.csv.gz")
    codes_path = os.path.join(base_dir, "active_codes.txt")
    progress_bar = st.progress(0, text="▸ 0% 云端加载...")

    # ====== 1. 快照加载（秒读） ======
    if os.path.exists(snapshot_path):
        try:
            df = pd.read_csv(snapshot_path, compression='gzip')
            loaded = 0
            for code, group in df.groupby('code'):
                group = group.sort_values('date').tail(30)
                g = group.sort_values('date').tail(30).reset_index(drop=True)
                dates = pd.to_datetime(g['date']).values
                stock_df = pd.DataFrame({
                    'Close':  pd.to_numeric(g['close'], errors='coerce').values,
                    'Open':   pd.to_numeric(g['open'], errors='coerce').values,
                    'High':   pd.to_numeric(g['high'], errors='coerce').values,
                    'Low':    pd.to_numeric(g['low'], errors='coerce').values,
                    'Volume': pd.to_numeric(g['volume'], errors='coerce').values,
                }, index=dates).dropna()
                if len(stock_df) >= 10:
                    all_data[code] = stock_df
                    loaded += 1
            progress_bar.progress(15, text=f"▸ 15% 快照加载: {loaded}只")
        except Exception as e:
            progress_bar.progress(5, text=f"▸ 5% 快照失败: {str(e)[:60]}")

    # ====== 2. yfinance 下载（目前直接下载，等快照稳定后再启加快照） ======
    if len(all_data) < 99999:
        # 用 active_codes.txt 而不是生成 15000 只
        if os.path.exists(codes_path):
            with open(codes_path) as f:
                codes = [l.strip() for l in f if l.strip()]
        else:
            codes = []
            for i in range(600000, 606000): codes.append(f"{i}.SS")
            for i in range(1, 5000): codes.append(f"{i:06d}.SZ")
            for i in range(300000, 302000): codes.append(f"{i}.SZ")
            for i in range(688000, 690000): codes.append(f"{i}.SS")

        BATCH = 300
        total_batches = len(codes) // BATCH + 1
        downloaded = 0
        for i in range(0, len(codes), BATCH):
            batch = codes[i:i+BATCH]
            batch_num = i // BATCH + 1
            pct = 5 + int(40 * batch_num / total_batches)
            progress_bar.progress(pct, text=f"▸ {pct}% 下载 {batch_num}/{total_batches} 批 ({downloaded}只)...")
            try:
                hist = yf.download(tickers=batch, period="30d", progress=False, auto_adjust=False)
                if hist is None or hist.empty: continue
                try: batch_codes = set(hist.columns.get_level_values(1))
                except Exception: continue
                for code in batch:
                    if code not in batch_codes: continue
                    try:
                        recent = hist.xs(code, level=1, axis=1)
                        recent = recent[recent['Close'].notna() & (recent['Close'] > 0)]
                        if len(recent) < 10: continue
                        stock_df = recent[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
                        all_data[code] = stock_df
                        downloaded += 1
                    except Exception: pass
            except Exception: pass
        progress_bar.progress(45, text=f"▸ 45% 下载完成: {len(all_data)} 只")

    # ====== 3. 今日数据注入 ======
    codes = list(all_data.keys())
    BATCH = 300
    total_batches = len(codes) // BATCH + 1
    injected = 0
    for i in range(0, len(codes), BATCH):
        batch = codes[i:i+BATCH]
        batch_num = i // BATCH + 1
        pct = 45 + int(50 * batch_num / total_batches)
        progress_bar.progress(pct, text=f"▸ {pct}% 注入今日数据 {batch_num}/{total_batches} 批 ({injected}只)...")
        try:
            hist = yf.download(tickers=batch, period="3d", progress=False, auto_adjust=False)
            if hist is None or hist.empty: continue
            try: batch_codes = set(hist.columns.get_level_values(1))
            except Exception: continue
            for code in batch:
                if code not in batch_codes: continue
                try:
                    recent = hist.xs(code, level=1, axis=1)
                    recent = recent[recent['Close'].notna() & (recent['Close'] > 0)]
                    if len(recent) == 0: continue
                    new_rows = pd.DataFrame({
                        'Close': recent['Close'].values, 'Open': recent['Open'].values,
                        'High': recent['High'].values, 'Low': recent['Low'].values,
                        'Volume': recent['Volume'].values,
                    })
                    if code in all_data:
                        all_data[code] = pd.concat([all_data[code], new_rows]).tail(40)
                    injected += 1
                except Exception: pass
        except Exception: pass

    # ====== 4. 数据质量检查 ======
    limit_up_count = 0
    for code, df in all_data.items():
        try:
            close = df['Close'].values
            if len(close) >= 2:
                pct = (close[-1] / close[-2] - 1) * 100
                if pct >= 9.5: limit_up_count += 1
        except: pass

    progress_bar.progress(100, text=f"▸ 100% 完成: {len(all_data)}只, 今日涨停{limit_up_count}只")
    progress_bar.empty()
    return all_data


# ==================== 快速 AI 分析（跳过板块信息，用已下载数据）====================
def fast_ai_analysis(code, stock_df, market_context="", memory_context=None):
    """v2: 四维框架（量价形时）+ 经典战法匹配 + DeepSeek API。memory_context 为历史分析上下文。"""
    import requests

    # ---- 列名兼容（CSV 小写 / yfinance 首字母大写）----
    if 'close' in stock_df.columns and 'Close' not in stock_df.columns:
        stock_df = stock_df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})

    # ---- 数据提取 ----
    close = stock_df['Close'].dropna()
    high = stock_df['High'].dropna()
    low = stock_df['Low'].dropna()
    volume = stock_df['Volume'].dropna()
    open_price = stock_df['Open'].dropna()

    if len(close) < 5:
        return None

    # ========== 基础指标 ==========
    current_price = close.iloc[-1]
    prev_close = close.iloc[-2] if len(close) >= 2 else current_price
    pct_chg = (current_price / prev_close - 1) * 100
    amplitude = (high.iloc[-1] / low.iloc[-1] - 1) * 100

    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else ma10
    ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None

    vol_today = volume.iloc[-1]
    vol_ma5 = volume.rolling(5).mean().iloc[-1]
    vol_ma20 = volume.rolling(20).mean().iloc[-1] if len(volume) >= 20 else vol_ma5
    recent_high_20 = high.tail(20).max()
    recent_low_20 = low.tail(20).min()
    drawdown_20 = (recent_high_20 - current_price) / recent_high_20 * 100

    # ========== MACD (12,26,9) ==========
    if len(close) >= 26:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        macd_bar = 2 * (dif - dea)
        dif_val = dif.iloc[-1]
        dea_val = dea.iloc[-1]
        macd_bar_val = macd_bar.iloc[-1]
        dif_prev = dif.iloc[-3] if len(dif) >= 3 else dif.iloc[-1]
        if dif_val > dea_val and dif_val > dif_prev:
            macd_trend = "金叉向上 ↑"
        elif dif_val < dea_val:
            macd_trend = "死叉向下 ↓"
        else:
            macd_trend = "粘合 →"
        macd_ok = True
    else:
        dif_val = dea_val = macd_bar_val = None
        macd_trend = "数据不足"
        macd_ok = False

    # ========== RSI(14) ==========
    if len(close) >= 14:
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        if rsi_val < 30:
            rsi_status = "超卖（反弹动能积蓄）"
        elif rsi_val > 70:
            rsi_status = "超买（追高风险）"
        else:
            rsi_status = "中性"
    else:
        rsi_val = None
        rsi_status = "数据不足"

    # ========== 布林带(20,2) ==========
    if len(close) >= 20:
        bb_mid = close.rolling(20).mean().iloc[-1]
        bb_std = close.rolling(20).std().iloc[-1]
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_width = (bb_upper - bb_lower) / bb_mid * 100 if bb_mid > 0 else 0
        if bb_upper != bb_lower:
            bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) * 100
        else:
            bb_position = 50
        if bb_position < 20:
            bb_status = f"下轨附近（超跌反弹机会）"
        elif bb_position > 80:
            bb_status = f"上轨附近（追高风险）"
        else:
            bb_status = f"中轨附近"
    else:
        bb_upper = bb_mid = bb_lower = bb_position = bb_width = None
        bb_status = "数据不足"

    # ========== OBV 趋势 ==========
    if len(close) >= 10:
        close_diff_sign = (close.diff() > 0).astype(int) - (close.diff() < 0).astype(int)
        obv = (volume * close_diff_sign).cumsum()
        obv_now = obv.iloc[-1]
        obv_5d_ago = obv.iloc[-6] if len(obv) >= 6 else obv.iloc[0]
        if obv_now > obv_5d_ago:
            obv_trend = "上升（资金流入）↑"
        else:
            obv_trend = "下降（资金流出）↓"
    else:
        obv_trend = "数据不足"

    # ========== MFI(14) 资金流量指标 ==========
    if len(close) >= 15:
        tp = (high + low + close) / 3
        rmf = tp * volume
        pos_flow = rmf.where(tp > tp.shift(1), 0)
        neg_flow = rmf.where(tp < tp.shift(1), 0)
        pos_sum = pos_flow.rolling(14).sum()
        neg_sum = neg_flow.rolling(14).sum()
        # avoid div by zero
        neg_sum_safe = neg_sum.replace(0, 1e-9)
        mfi = 100 - (100 / (1 + pos_sum / neg_sum_safe))
        mfi_val = mfi.iloc[-1]
        if mfi_val < 20:
            mfi_status = "超卖（资金流入）"
        elif mfi_val > 80:
            mfi_status = "超买（资金流出）"
        else:
            mfi_status = "中性"
    else:
        mfi_val = None
        mfi_status = "数据不足"

    # ========== 连板回调专属指标 ==========
    # 找涨停日（A股10%涨跌幅，用9.5%容差）
    pct_chg_series = close.pct_change()
    limit_up_mask = pct_chg_series > 0.095
    limit_up_indices = close.index[limit_up_mask].tolist()

    if limit_up_indices:
        last_lu_idx = limit_up_indices[-1]
        last_lu_close = close.loc[last_lu_idx]
        last_lu_low = low.loc[last_lu_idx] if last_lu_idx in low.index else None
        last_lu_vol = volume.loc[last_lu_idx] if last_lu_idx in volume.index else None

        # 距最后涨停天数
        pos_now = close.index.get_loc(close.index[-1])
        pos_lu = close.index.get_loc(last_lu_idx)
        days_since_limit = pos_now - pos_lu

        # 回调幅度（从涨停日收盘算）
        pullback_pct = (last_lu_close - current_price) / last_lu_close * 100

        # 缩量程度：近3日均量 / 涨停日量
        if last_lu_vol and last_lu_vol > 0:
            recent_avg_vol = volume.iloc[-3:].mean()
            vol_shrink_ratio = recent_avg_vol / last_lu_vol * 100
        else:
            vol_shrink_ratio = None

        # 是否跌破涨停日最低
        if last_lu_low is not None:
            broke_low = current_price < last_lu_low
        else:
            broke_low = None

        # 连板识别：涨停日前是否有连续涨停
        consecutive_lu = 1
        for i in range(len(limit_up_indices) - 2, -1, -1):
            prev_pos = close.index.get_loc(limit_up_indices[i])
            curr_pos = close.index.get_loc(limit_up_indices[i + 1])
            if curr_pos - prev_pos == 1:
                consecutive_lu += 1
            else:
                break
    else:
        days_since_limit = None
        pullback_pct = None
        vol_shrink_ratio = None
        last_lu_low = None
        broke_low = None
        consecutive_lu = 0

    # ========== 构造结构化 technical_data ==========
    lines = []
    lines.append(f"【{code} 技术数据】")
    lines.append("")
    lines.append("## 基础指标")
    lines.append(f"- 最新价：{current_price:.2f}（今日 {pct_chg:+.2f}%）| 振幅 {amplitude:.1f}%")
    lines.append(f"- 均线：MA5={ma5:.2f}  MA10={ma10:.2f}  MA20={ma20:.2f}" + (f"  MA60={ma60:.2f}" if ma60 else ""))
    lines.append(f"- 量比：今日/5日均量={vol_today/vol_ma5:.2f}x | 20日高={recent_high_20:.2f}  回撤={drawdown_20:.1f}%")
    lines.append("")
    lines.append("## 技术指标")
    if macd_ok:
        lines.append(f"- MACD(12,26,9)：DIF={dif_val:.3f}  DEA={dea_val:.3f}  柱={macd_bar_val:+.3f}  → {macd_trend}")
    else:
        lines.append(f"- MACD：{macd_trend}")
    lines.append(f"- RSI(14)：{rsi_val:.1f} → {rsi_status}" if rsi_val is not None else f"- RSI(14)：{rsi_status}")
    if bb_upper is not None:
        lines.append(f"- 布林(20,2)：上轨={bb_upper:.2f}  中轨={bb_mid:.2f}  下轨={bb_lower:.2f}  带宽={bb_width:.1f}%")
        lines.append(f"  价格位置：{bb_position:.0f}% → {bb_status}")
    else:
        lines.append(f"- 布林(20,2)：{bb_status}")
    lines.append(f"- OBV趋势：{obv_trend}")
    lines.append(f"- MFI(14)：{mfi_val:.1f} → {mfi_status}" if mfi_val is not None else f"- MFI(14)：{mfi_status}")
    lines.append("")
    lines.append("## 回调数据")
    if days_since_limit is not None:
        lu_date = str(last_lu_idx)[:10] if hasattr(last_lu_idx, 'strftime') else str(last_lu_idx)[:10]
        lines.append(f"- 最近涨停日：{lu_date}（{consecutive_lu}连板）")
        lines.append(f"- 距涨停日：{days_since_limit} 天" + (" ← 黄金窗口(3-5天)" if 3 <= days_since_limit <= 5 else (" ← 时间偏长，警惕走弱" if days_since_limit > 7 else "")))
        lines.append(f"- 回调幅度：{pullback_pct:.1f}%（从涨停日收盘价算）")
        if vol_shrink_ratio is not None:
            tag = " ← 缩量充分" if vol_shrink_ratio < 50 else (" ← 缩量不足" if vol_shrink_ratio >= 80 else "")
            lines.append(f"- 缩量程度：近3日均量/涨停日量 = {vol_shrink_ratio:.0f}%{tag}")
        if last_lu_low is not None:
            if broke_low:
                lines.append(f"- 涨停日最低={last_lu_low:.2f} | ⚠️ 已跌破！（强退出信号）")
            else:
                lines.append(f"- 涨停日最低={last_lu_low:.2f} | 未跌破（防线有效）")
    else:
        lines.append("- 近期无涨停日数据")
    technical_data = "\n".join(lines)

    # ========== System Prompt ==========
    system_prompt = """你是专精于A股连板回调策略的量化分析师。你严格遵循"量价形时"四维分析框架：

【量】缩量挖坑（回调量<涨停量50%为佳），放量填坑（反弹需放量确认）
【价】首板不破涨停最低价（多板以首板收盘价为防线），MA支撑体系层层验证
【形】缩量黄金坑、长下影弹簧线、缩倍阴、三阴不破阳、天外飞仙、金凤凰
【时】3-5天为黄金回调窗口，超过7天不恢复=明显走弱

经典战法库：
- 缩倍阴：中低位首板后，回调不破涨停低点，缩量至<50%，3日内放量阳线突破阴线高点=入场
- 三阴不破阳：涨停后3根缩量阴线，收盘逐日下降但不破涨停最低价，放量阳线反包=入场
- 天外飞仙：3连板后放量阴线，缩量整理不破该阴线低点，再涨停突破=入场
- 金凤凰：回调始终在涨停价上方，持续缩量，下一涨停确认调整结束=入场

你的分析务实直接，给具体价格位而非模糊描述。每个判断都有明确的技术依据。
仓位建议根据市场情绪档位动态调整（冰点空仓/低迷1-2成/启动2-3成/发酵3-5成/高潮减仓）。"""

    # ========== User Prompt ==========
    prompt = f"""{technical_data}

{market_context}

请按以下"量价形时"框架逐项分析，每项给出具体判断：

## 一、量（Volume）
- 回调缩量评估（充分/不足/异常放量）+ 缩量比
- OBV/MFI 资金流向判断
- 量价配合状态（底背离=看涨 / 同步下跌=观望 / 放量止跌=积极）

## 二、价（Price）
- 关键支撑位（给具体价格）：涨停日最低/MA5/MA10/MA20
- 关键压力位（给具体价格）：近期高点/均线压制位
- 是否跌破防线？跌破后的严重程度评估

## 三、形（Pattern）
- 当前K线形态描述
- 匹配哪种经典战法？（缩倍阴/三阴不破阳/天外飞仙/金凤凰/无匹配）
- 形态完成度评估（%）

## 四、时（Time）
- 回调阶段判断（初期/中期/末期）
- 时间窗口评估（黄金窗口内/偏长/超时）+ 是否还有效

## 五、综合判断
- 反弹概率：低(≤30%) / 中(30-60%) / 高(≥60%)
- 明日锚点：高开 >X.XX 可关注 / 低开 <X.XX 应放弃
- 建议入场区间：X.XX - X.XX
- 止损体系：紧止损 X.XX / 主止损 X.XX / 硬止损 X.XX
- 止盈目标：TP1 X.XX (1.5R) / TP2 X.XX (2R)
- 仓位建议：X成仓（对应情绪档位）
- 风险报酬比：≥1:2 才值得参与

## 六、风险
- 主要风险（1-2条具体描述）
- 一票否决条件（出现什么情况绝对不能参与）

最终结论：【参与 / 观望 / 放弃】"""

    # ========== 调用 DeepSeek API ==========
    try:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            return "## ⚠️ API Key 未配置\n\n请在环境变量中设置 `DEEPSEEK_API_KEY`。\n\n**设置方法**：\n```bash\nexport DEEPSEEK_API_KEY=\"sk-xxxxxxxx\"\n```\n\n或在 `~/.claude/settings.json` 中添加 `env` 配置。"
        api_url = screener.DEEPSEEK_API_URL

        # 注入 AI 记忆上下文
        full_system = system_prompt
        if memory_context:
            full_system += f"\n\n{memory_context}\n\n请结合以上历史分析记录和实际验证结果，对本次信号做连续性分析。如果历史判断正确/错误，请说明原因并调整本次判断。"

        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 1500,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return f"## ⚠️ API 请求失败 (HTTP {resp.status_code})\n\nDeepSeek API 返回了错误状态码。请检查 API Key 是否有效。\n\n错误详情：`{resp.text[:200]}`"
        data = resp.json()
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        return f"## ⚠️ API 返回异常\n\nDeepSeek 返回了非预期格式的响应：\n```\n{str(data)[:300]}\n```"
    except requests.exceptions.Timeout:
        return "## ⚠️ API 请求超时\n\nDeepSeek API 在 30 秒内未响应。请稍后重试。"
    except requests.exceptions.ConnectionError:
        return "## ⚠️ 网络连接失败\n\n无法连接到 DeepSeek API。请检查网络连接。"
    except Exception as e:
        return f"## ⚠️ AI 分析异常\n\n```\n{type(e).__name__}: {e}\n```\n\n请稍后重试或联系开发者。"


# ==================== 多模式筛选 ====================
def screen_all_modes(all_data):
    """用 strict/loose 两种参数分别筛选，返回 {mode: [候选列表]}"""
    modes = ["strict", "loose"]
    results = {}
    all_stats = {}

    # 预筛选：快速排除近20天没有涨停的股票（消除大部分无效计算）
    active_stocks = {}
    for code, stock_data in all_data.items():
        try:
            close = stock_data['Close'].values
            if len(close) < 3:
                continue
            # 快速检查最近20天是否有涨停
            has_limit = False
            threshold = 18.5 if code.startswith(('30', '688')) else 9.5
            for i in range(max(1, len(close) - 20), len(close)):
                if close[i] > 0 and close[i-1] > 0:
                    chg = (close[i] / close[i-1] - 1) * 100
                    if chg >= threshold:
                        has_limit = True
                        break
            if has_limit:
                active_stocks[code] = stock_data
        except Exception:
            pass

    for mode in modes:
        params = screener.SCREEN_MODES[mode].copy()

        # 保存+设置全局 PARAMS
        original = screener.PARAMS.copy()
        screener.PARAMS.update(params)

        candidates = []
        stats = {
            'total': len(active_stocks),
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

        for code, stock_data in active_stocks.items():
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

    today = china_now().strftime('%Y%m%d')

    # 批量获取名称/板块
    codes = [c.get('代码', c.get('code', '')) for c in all_candidates]
    name_info = name_lookup.batch_lookup(codes, max_fetch=10)

    new_rows = []
    for c in all_candidates:
        info = name_info.get(c.get('代码', c.get('code', '')), {})
        new_rows.append({
            'signal_date': today,
            'code': c.get('代码', c.get('code', '')),
            'name': info.get('name', '') or '',
            'sector': info.get('sector_cn', '') or info.get('sector', '') or info.get('industry', '') or '',
            'mode': c.get('mode', ''),
            'entry_price': c.get('price', c.get('最新价', 0)),
            'pullback_pct': c.get('pullback_pct', c.get('回调比', 0)),
            'limit_days': c.get('limit_days', c.get('连板数', 0)),
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
        st.info("◆ 暂无历史信号。选股后会自动记录。")
        return

    df = pd.read_csv(SIGNAL_FILE)
    if len(df) == 0:
        st.info("◆ 暂无历史信号。")
        return

    # ---- 统计卡片 ----
    total = len(df)
    dates = sorted(df['signal_date'].astype(str).unique())
    # 安全格式化日期
    first_date = str(dates[0])
    last_date = str(dates[-1])
    first_str = f"{first_date[:4]}-{first_date[4:6]}-{first_date[6:]}" if len(first_date) >= 8 else first_date
    last_str = f"{last_date[:4]}-{last_date[4:6]}-{last_date[6:]}" if len(last_date) >= 8 else last_date
    st.caption(f"◆ 共 {total} 条信号，{len(dates)} 个交易日（{first_str} ~ {last_str}）")

    col1, col2, col3, col4 = st.columns(4)

    # 查找有足够天数来复盘（≥3 天前）
    today_int = int(china_now().strftime('%Y%m%d'))
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
            st.metric("3日均收益", f"{sum(gains)/len(gains):+.2f}%")
        else:
            st.metric("3日均收益", "—")

    # ---- 详细表格 ----
    if len(reviewable) > 0:
        st.subheader("◆ 最近信号详情")

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
            d3_icon = "◆" if (ret3 or 0) > 0 else ("◈" if (ret3 or 0) < 0 else "◇")
            d5_icon = "◆" if (ret5 or 0) > 0 else ("◈" if (ret5 or 0) < 0 else "◇")

            stock_name = row.get('name', '') or ''
            rows.append({
                '日期': f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}",
                '代码': code,
                '名称': stock_name,
                '模式': row.get('mode', ''),
                '入场价': f"{price:.2f}",
                '回调': f"{row['pullback_pct']:.1f}%",
                '3日': f"{d3_icon} {d3}",
                '5日': f"{d5_icon} {d5}",
                '7日': d7,
            })

        df_show = pd.DataFrame(rows)
        st.dataframe(
            df_show, use_container_width=True, hide_index=True,
            column_config={
                "回调": st.column_config.TextColumn(width="small"),
            },
        )

        # 模式胜率对比
        st.subheader("◆ 各模式胜率对比")
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
                    '3日均收益': f"{sum(gains)/len(gains):+.2f}%",
                    '最佳': f"{max(gains):+.1f}%",
                    '最差': f"{min(gains):+.1f}%",
                })
        if mode_stats:
            st.dataframe(pd.DataFrame(mode_stats), use_container_width=True, hide_index=True)

    else:
        st.info("◆ 最近3天内的信号需要再等等才能复盘。")

    # 刷新按钮
    if st.button("◆ 刷新复盘数据", key="refresh_review"):
        st.rerun()


@st.cache_data(ttl=600, show_spinner=False)
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


# ==================== AI 记忆系统 ====================
AI_MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_memory.json")

def load_ai_memory():
    """加载 AI 记忆文件。返回 dict {code: [records]}。不存在则返回 {}。"""
    if not os.path.exists(AI_MEMORY_FILE):
        return {}
    try:
        with open(AI_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_ai_memory(memory):
    """保存 AI 记忆到文件"""
    with open(AI_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def save_ai_analysis_record(code, date_str, mode, entry_price, pullback_pct, limit_days, analysis_text):
    """保存单条 AI 分析记录。按 (code, date) 去重。"""
    memory = load_ai_memory()
    if code not in memory:
        memory[code] = []
    # 去重：同一天同一只股票不重复
    for rec in memory[code]:
        if rec.get("date") == date_str:
            return  # 已存在，跳过
    # 正则提取 AI 回复中的关键字段
    import re as _re
    sentiment = ""
    position = ""
    opinion = ""
    try:
        sm = _re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', analysis_text)
        if sm: sentiment = sm.group(1).strip()
        pm = _re.search(r'仓位[建议]*[：:]\s*(.+?)(?:\n|$)', analysis_text)
        if pm: position = pm.group(1).strip()
        om = _re.search(r'最终结论[：:]\s*(.+?)(?:\n|$)', analysis_text)
        if om: opinion = om.group(1).strip()
    except Exception:
        pass
    memory[code].append({
        "date": date_str,
        "mode": mode,
        "entry_price": entry_price,
        "pullback_pct": pullback_pct,
        "limit_days": limit_days,
        "analysis": analysis_text,
        "sentiment": sentiment,
        "position": position,
        "opinion": opinion,
        "verified": False,
        "return_3d": None,
        "return_5d": None,
        "return_7d": None,
        "verdict": None,
    })
    save_ai_memory(memory)

def auto_verify_memory():
    """自动验证：对 verified=False 且 ≥3天前的记录，计算实际收益并回写 verdict"""
    memory = load_ai_memory()
    if not memory:
        return
    today_int = int(china_now().strftime('%Y%m%d'))
    changed = False
    for code, records in memory.items():
        for rec in records:
            if rec.get("verified"):
                continue
            try:
                sdate = str(rec["date"])
                if len(sdate) < 8:
                    continue
                if today_int - int(sdate) < 3:
                    continue  # 还没到验证时间
                entry_price = rec.get("entry_price", 0)
                # 如果 entry_price 为 0，尝试从 signal_tracker 获取
                if entry_price == 0 and os.path.exists(SIGNAL_FILE):
                    try:
                        df_sig = pd.read_csv(SIGNAL_FILE)
                        match = df_sig[(df_sig['code'] == code) & (df_sig['signal_date'].astype(str) == sdate)]
                        if len(match) > 0:
                            entry_price = match.iloc[0]['entry_price']
                    except Exception:
                        pass
                if entry_price <= 0:
                    continue
                ret3 = check_return(code, sdate, entry_price, 3)
                ret5 = check_return(code, sdate, entry_price, 5)
                ret7 = check_return(code, sdate, entry_price, 7)
                rec["return_3d"] = round(ret3, 2) if ret3 is not None else None
                rec["return_5d"] = round(ret5, 2) if ret5 is not None else None
                rec["return_7d"] = round(ret7, 2) if ret7 is not None else None
                rec["verified"] = True
                if ret3 is not None:
                    rec["verdict"] = "correct" if ret3 > 0 else "wrong"
                changed = True
            except Exception:
                pass
    if changed:
        save_ai_memory(memory)

def get_stock_memory_context(code):
    """获取某只股票的历史分析上下文，用于注入 AI prompt。返回格式化文本或 None。"""
    memory = load_ai_memory()
    if code not in memory or not memory[code]:
        return None
    records = memory[code]
    lines = ["[历史分析记录]"]
    for rec in records[-5:]:  # 最多取最近5条
        sdate = rec.get("date", "未知")
        if len(sdate) >= 8:
            sdate = f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}"
        sentiment = rec.get("sentiment", "")
        position = rec.get("position", "")
        opinion = rec.get("opinion", "")
        verdict = rec.get("verdict", "")
        ret3 = rec.get("return_3d")
        # 构建摘要
        summary_parts = [f"情绪:{sentiment}", f"仓位:{position}"]
        if opinion:
            summary_parts.append(f"结论:{opinion}")
        if verdict == "correct":
            summary_parts.append(f"3日后实际收益 +{ret3}% (✅预测正确)")
        elif verdict == "wrong":
            ret_str = f"{ret3}%" if ret3 is not None else "?"
            summary_parts.append(f"3日后实际收益 {ret_str} (◈预测偏差)")
        else:
            summary_parts.append("(⏳待验证)")
        lines.append(f"- {sdate}: {' | '.join(summary_parts)}")
    return "\n".join(lines)

def compute_performance(mode_filter=None, days_window=30):
    """从 signal_tracker.csv 计算绩效指标。
    - mode_filter: 'strict' / 'loose' / None(全部)
    - days_window: 只看最近N天的信号（自然日）
    - 使用复合收益计算
    """
    if not os.path.exists(SIGNAL_FILE):
        return None
    try:
        df = pd.read_csv(SIGNAL_FILE)
        if len(df) == 0:
            return None
        today_int = int(china_now().strftime('%Y%m%d'))
        cutoff_date = china_now() - timedelta(days=days_window)
        cutoff = int(cutoff_date.strftime('%Y%m%d'))

        # 过滤模式
        if mode_filter:
            df = df[df['mode'] == mode_filter]
        if len(df) == 0:
            return None

        # 过滤时间窗口
        df = df[df['signal_date'].astype(str).str.len() >= 8]
        df = df[df['signal_date'].astype(int) >= cutoff]
        if len(df) == 0:
            return None

        # 计算每条已验证信号的收益
        returns = []
        wins = 0
        losses = 0
        for _, row in df.iterrows():
            sdate = str(row['signal_date'])
            if today_int - int(sdate) < 3:
                continue  # 未到验证时间
            ret = check_return(row['code'], sdate, row['entry_price'], 3)
            if ret is not None:
                returns.append({
                    'date': sdate,
                    'code': row['code'],
                    'mode': row.get('mode', ''),
                    'return_3d': ret,
                })
                if ret > 0:
                    wins += 1
                elif ret < 0:
                    losses += 1
                # ret == 0 不计入胜负

        if not returns:
            return None

        total_trades = wins + losses
        win_rate = wins / total_trades if total_trades > 0 else 0
        avg_win = sum(r['return_3d'] for r in returns if r['return_3d'] > 0) / wins if wins > 0 else 0
        avg_loss = abs(sum(r['return_3d'] for r in returns if r['return_3d'] < 0) / losses) if losses > 0 else 0
        profit_factor = (avg_win * wins) / (avg_loss * losses) if (avg_loss * losses) > 0 else float('inf')
        if profit_factor == float('inf'):
            profit_factor = 999.99  # 无损情况避免HTML渲染为"inf"

        # 复合收益曲线（关键修复：compound returns）
        equity = 1.0
        cum_returns = []
        peak = 1.0
        max_dd = 0.0
        for r in returns:
            equity *= (1 + r['return_3d'] / 100)
            cum_returns.append(round((equity - 1) * 100, 2))
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        total_return = round((equity - 1) * 100, 2)

        return {
            'total_return': total_return,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': round(max_dd, 2),
            'cum_returns': cum_returns,
            'returns': returns,
        }
    except Exception:
        return None


# ==================== 选股结果展示 ====================
def show_screening_results(results, all_stats):
    st.header("◆ 选股结果")

    tabs = st.tabs([
        f"◆ STRICT 严格 ({len(results['strict'])}只)",
        f"◇ LOOSE 宽松 ({len(results['loose'])}只)",
    ])

    for tab_idx, mode in enumerate(["strict", "loose"]):
        with tabs[tab_idx]:
            candidates = results[mode]
            stats = all_stats[mode]

            if not candidates:
                st.info(f"◆ 当前模式无符合条件的股票")
                with st.expander("◆ 筛选漏斗"):
                    st.write(f"总扫描: {stats['total']} → 有涨停: {stats['has_limit_up']} → "
                             f"连板达标: {stats['consecutive_ok']} → 实体板达标: {stats['entity_ratio_ok']} → "
                             f"回调天数: {stats['pullback_days_ok']} → 回调幅度: {stats['pullback_range_ok']} → "
                             f"均线: {stats['ma_ok']} → 量能: {stats['volume_shrink_ok']} → "
                             f"阳线: {stats['yang_ok']} → 放量: {stats['volume_expand_ok']} → "
                             f"最终: {stats['final']}")
                continue

            candidate_codes = [c.get('代码', c.get('code', '')) for c in candidates]
            name_info = name_lookup.batch_lookup(candidate_codes, max_fetch=5)

            for code_data in candidates:
                code = code_data['code']
                info = name_info.get(code, {})
                stock_name = info.get('name', '') or ''
                with st.container():
                    col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1.2, 1.1, 0.9, 0.9, 1.3])

                    with col1:
                        name_line = f"**`{code}`**"
                        if stock_name:
                            name_line += f"  {stock_name}"
                        st.markdown(name_line)
                    with col2:
                        st.metric("价格", f"{code_data['price']:.2f}")
                    with col3:
                        st.metric("回调", f"{code_data['pullback_pct']:.1f}%")
                    with col4:
                        st.metric("连板", f"{code_data['limit_days']}天")
                    with col5:
                        st.metric("实体板", f"{code_data['entity_ratio']:.0f}%")
                    with col6:
                        btn_key = f"ai_{mode}_{code}"
                        if st.button(f"◆ AI分析", key=btn_key, use_container_width=True):
                            st.session_state[f'analyze_{code}'] = True

                    # AI 分析结果（统一入口在处理，此处仅显示）
                    if st.session_state.get(f'analysis_result_{code}'):
                        with st.expander(f"◆ {code} AI分析报告", expanded=True):
                            st.markdown(st.session_state[f'analysis_result_{code}'])

                    st.divider()

            with st.expander("◆ 筛选漏斗详情"):
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
                    ("◆ 最终候选", stats['final']),
                ]
                cols_funnel = st.columns(len(stages))
                for i, (label, val) in enumerate(stages):
                    with cols_funnel[i]:
                        st.metric(label, val)

    st.divider()
    if any(len(v) > 0 for v in results.values()):
        all_candidates = []
        for mode in ["strict", "loose"]:
            for c in results[mode]:
                all_candidates.append({**c, 'mode': mode})
        df_export = pd.DataFrame(all_candidates)
        st.download_button(
            label="◆ 导出 CSV",
            data=df_export.to_csv(index=False, encoding='utf-8-sig'),
            file_name=f"candidates_all_{china_now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
        save_signals(all_candidates)


# ==================== 自动加载结果 ====================
def load_latest_results():
    """从 JSON 文件加载预计算选股结果。返回 dict 或 None。"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "latest_scan_results.json")
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 验证基本结构
        if "modes" not in data:
            return None
        return data
    except Exception:
        return None


# ==================== 主界面 ====================
def main():
    # 注入设计系统 CSS
    inject_design_system()

    # 标题栏
    st.title("◆ NEON VAULT")

    # 实时时间戳 + 状态
    now = china_now()
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

    # 时间戳 Neon 胶囊条
    date_str = now.strftime('%m-%d')
    time_str = now.strftime('%H:%M')
    scan_info = " | 定时扫描: 10:00 / 11:30 / 14:00 / 15:00" if weekday < 5 else ""
    st.markdown(f"""
    <div style="display:flex;gap:8px;align-items:center;margin:4px 0 6px 0;flex-wrap:wrap">
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.58rem;padding:3px 10px;border-radius:10px;
                   background:rgba(0,240,255,0.06);border:1px solid rgba(0,240,255,0.12);color:#00F0FF">
        📅 {date_str}</span>
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.58rem;padding:3px 10px;border-radius:10px;
                   background:rgba(123,47,255,0.06);border:1px solid rgba(123,47,255,0.12);color:#9B6FFF">
        🕐 {time_str}</span>
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.58rem;padding:3px 10px;border-radius:10px;
                   background:rgba(0,240,255,0.04);border:1px solid rgba(0,240,255,0.08);color:#8888BB">
        {market_status}</span>
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.52rem;color:#555577">{scan_info}</span>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ---- 侧边栏 ----
    with st.sidebar:
        st.markdown("### ◆ 控制面板")

        # 导航卡片（纵向堆叠）
        current_page = st.session_state.get("nav_page", "◆ 选股")
        nav_pages = [
            ("nav_stock", "📊 选股", "◆ 选股"),
            ("nav_review", "📋 复盘", "◆ 复盘"),
            ("nav_intro", "📖 介绍", "◆ 介绍"),
        ]
        for key, label, page_val in nav_pages:
            is_active = current_page == page_val
            if is_active:
                st.markdown(f"""
                <div class="nav-card active">
                  <span style="font-size:1.1rem">{label}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                if st.button(label, key=key, use_container_width=True):
                    st.session_state["nav_page"] = page_val
                    st.rerun()

        st.divider()

        # 数据新鲜度
        st.markdown("**◆ 数据状态**")
        try:
            import time as _time
            DATA_DIR = screener.DATA_DIR
            csv_files = []
            if os.path.isdir(DATA_DIR):
                csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv') and os.path.getsize(os.path.join(DATA_DIR, f)) > 100]
            base_dir = os.path.dirname(os.path.abspath(__file__))
            snapshot_path = os.path.join(base_dir, "stock_snapshot.csv.gz")
            has_snapshot = os.path.exists(snapshot_path)
            if csv_files:
                newest = max(os.path.getmtime(os.path.join(DATA_DIR, f)) for f in csv_files)
                age_seconds = _time.time() - newest
                if age_seconds < 3600: data_age = f"{int(age_seconds/60)}分钟前"
                elif age_seconds < 86400: data_age = f"{int(age_seconds/3600)}小时前"
                else: data_age = f"{int(age_seconds/86400)}天前"
                data_status_html = f"""
                <div class="sidebar-data-status">
                  <span class="stat-label">模式</span> <span class="stat-highlight">💾 本地</span><br>
                  <span class="stat-label">股票</span> <span class="stat-value">{len(csv_files)} 只</span><br>
                  <span class="stat-label">更新</span> <span class="stat-value">{data_age}</span>
                </div>"""
            elif has_snapshot:
                data_status_html = """
                <div class="sidebar-data-status">
                  <span class="stat-label">模式</span> <span class="stat-highlight">☁️ 云端</span><br>
                  <span class="stat-label">数据</span> <span class="stat-value">快照 + yfinance</span>
                </div>"""
            else:
                data_status_html = """
                <div class="sidebar-data-status" style="border-color:rgba(255,51,102,0.2);background:rgba(255,51,102,0.03)">
                  <span class="stat-label">状态</span> <span style="color:#FF3366">⚠️ 无数据</span>
                </div>"""
            st.markdown(data_status_html, unsafe_allow_html=True)
            # 显示最近扫描时间
            json_path = os.path.join(base_dir, "latest_scan_results.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, "r") as f:
                        scan_info = json.load(f)
                    scan_time = scan_info.get("scan_time", "")
                    if scan_time:
                        st.markdown(f"""
                        <div style="font-family:monospace;font-size:0.55rem;color:#555588;margin-top:6px;text-align:right">
                          最近扫描 <span style="color:#7777AA">{scan_time}</span>
                        </div>""", unsafe_allow_html=True)
                except Exception:
                    pass
        except:
            st.warning("⚠️ 无法检测")


    # ---- 大盘概览 ----
    st.header("◆ 大盘概况")
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
                    f"5日高 {data['high_5d']:.0f}  |  "
                    f"5日低 {data['low_5d']:.0f}"
                )
            else:
                st.metric(label=name, value="—")
    st.divider()

    # 获取当前页面
    page = st.session_state.get('nav_page', '◆ 选股')

    # ============ 选股页面 ============
    if page == '◆ 选股':
        # 加载预计算选股结果（缓存到 session_state，切换 tab 不丢失）
        if "cached_scan_data" not in st.session_state:
            st.session_state["cached_scan_data"] = load_latest_results()
        scan_data = st.session_state["cached_scan_data"]
        fresh = load_latest_results()
        if fresh and fresh.get("scan_time") != scan_data.get("scan_time"):
            st.session_state["cached_scan_data"] = fresh
            scan_data = fresh

        # 判断当前时段
        now = china_now()
        wd = now.weekday()
        h, m = now.hour, now.minute
        is_trading = (wd < 5 and ((9 <= h < 11) or (h == 11 and m <= 30) or (13 <= h < 15)))
        is_post_close = (wd < 5 and h >= 15)

        if scan_data is None:
            # 还没有任何扫描结果
            st.info("◆ 等待首次定时扫描… 结果将在 10:00 / 11:30 / 14:00 / 15:00 自动出现")
            st.caption("💡 也可以手动运行: `python archive/tools/auto_daily.py`")
        else:
            st.header("◆ 选股结果")

            # Neon 状态栏
            scan_time = scan_data.get("scan_time", "未知")
            modes = scan_data.get("modes", {})
            if is_post_close:
                status_class = "closed"
                status_icon = "✅"
                status_text = "今日最终结果（收盘后）"
            elif is_trading:
                status_class = "trading"
                status_icon = "🔄"
                status_text = "盘中实时结果（每5分钟刷新）"
            else:
                status_class = ""
                status_icon = "⏸"
                status_text = "市场已收盘"
            pulse_html = (
                '<span class="pulse-dot cyan"></span>' if is_post_close
                else '<span class="pulse-dot amber"></span>' if is_trading
                else ""
            )
            st.markdown(f"""
            <div class="neon-status-bar {status_class}">
              <span class="status-icon">{status_icon}</span>
              <span class="status-text">{status_text}</span>
              <span class="status-spacer"></span>
              <span class="status-label">扫描时间</span>
              <span class="status-time">{scan_time}</span>
              {pulse_html}
            </div>
            """, unsafe_allow_html=True)

            # 模式信息已移至 📖 介绍页面

            # === 统一 AI 分析处理（在候选渲染之前集中处理所有待处理请求）===
            ai_placeholder = st.empty()
            codes_to_analyze = [k.replace("analyze_", "") for k in st.session_state
                               if k.startswith("analyze_") and st.session_state[k]]
            # 构建 code → candidate info 的快速查找表
            candidate_info = {}
            for m_name, m_data in modes.items():
                if not isinstance(m_data, dict):
                    continue
                m_candidates = m_data.get('candidates', m_data.get('候选', []))
                if not isinstance(m_candidates, list):
                    continue
                for c in m_candidates:
                    if not isinstance(c, dict):
                        continue
                    c_code = c.get('code', c.get('代码', ''))
                    if c_code:
                        candidate_info[c_code] = {
                            'mode': m_name,
                            'price': c.get('price', c.get('最新价', 0)),
                            'pullback_pct': c.get('pullback_pct', c.get('回调比', 0)),
                            'limit_days': c.get('limit_days', c.get('连板数', 0)),
                        }
            for code in codes_to_analyze:
                ai_placeholder.markdown(
                    f"<div style='padding:14px 20px;background:rgba(0,240,255,0.05);"
                    f"border:1px solid rgba(0,240,255,0.2);border-radius:10px;"
                    f"font-family:\"JetBrains Mono\",monospace;font-size:0.72rem;color:#00F0FF;"
                    f"box-shadow:0 0 20px rgba(0,240,255,0.06)'>"
                    f"<span style='display:inline-block;animation:pulse-dot-anim 1.2s ease-in-out infinite;"
                    f"width:10px;height:10px;border-radius:50%;background:#00F0FF;"
                    f"margin-right:10px;box-shadow:0 0 8px #00F0FF'></span>"
                    f"◆ 正在对 <b>{code}</b> 进行AI深度分析（约8-15秒）...</div>",
                    unsafe_allow_html=True
                )
                try:
                    stock_df = None
                    csv_path = os.path.join(screener.DATA_DIR, f"{code}.csv")
                    if os.path.exists(csv_path):
                        df = pd.read_csv(csv_path).tail(60)
                        stock_df = pd.DataFrame({
                            "Close": df["close"].values,
                            "Open": df["open"].values,
                            "High": df["high"].values,
                            "Low": df["low"].values,
                            "Volume": df["volume"].values,
                        }).dropna()
                    if stock_df is None or len(stock_df) < 10:
                        try:
                            ticker = yf.Ticker(code)
                            df_yf = ticker.history(period="3mo")
                            if df_yf is not None and len(df_yf) >= 10:
                                stock_df = df_yf[['Open','High','Low','Close','Volume']].dropna()
                        except Exception:
                            pass
                    market_ctx = screener.get_market_context()
                    # 获取 AI 历史记忆上下文
                    memory_context = get_stock_memory_context(code)
                    analysis = fast_ai_analysis(code, stock_df, market_ctx, memory_context=memory_context)
                    if analysis:
                        st.session_state[f"analysis_result_{code}"] = analysis
                        # 自动存档到 AI 记忆
                        try:
                            cinfo = candidate_info.get(code, {})
                            save_ai_analysis_record(
                                code=code,
                                date_str=china_now().strftime('%Y%m%d'),
                                mode=cinfo.get('mode', ''),
                                entry_price=cinfo.get('price', 0),
                                pullback_pct=cinfo.get('pullback_pct', 0),
                                limit_days=int(cinfo.get('limit_days', 0)),
                                analysis_text=analysis,
                            )
                        except Exception:
                            pass  # 存档失败不影响主流程
                    st.session_state[f"analyze_{code}"] = False
                except Exception:
                    st.session_state[f"analyze_{code}"] = False
                ai_placeholder.empty()
                st.rerun()

            tab_labels = [
                f"STRICT 严格 ({modes.get('strict', {}).get('count', 0)}只)",
                f"LOOSE 宽松 ({modes.get('loose', {}).get('count', 0)}只)",
            ]
            tabs = st.tabs(tab_labels)

            for tab_idx, mode in enumerate(["strict", "loose"]):
                with tabs[tab_idx]:
                    mode_data = modes.get(mode, {})
                    candidates = mode_data.get("candidates", [])
                    if not candidates:
                        st.info(f"当前 {mode.upper()} 模式无符合条件的股票")
                        continue

                    codes = [c["code"] for c in candidates]
                    name_info = name_lookup.batch_lookup(codes, max_fetch=5)

                    for c in candidates:
                        code = c["code"]
                        info = name_info.get(code, {})
                        stock_name = info.get("name", "") or ""
                        with st.container():
                            col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1.2, 1.1, 0.9, 0.9, 1.3])
                            with col1:
                                name_line = f"**`{code}`**"
                                if stock_name:
                                    name_line += f"  {stock_name}"
                                st.markdown(name_line)
                            with col2:
                                st.metric("价格", f"{c['price']:.2f}")
                            with col3:
                                st.metric("回调", f"{c['pullback_pct']:.1f}%")
                            with col4:
                                st.metric("连板", f"{c['limit_days']}天")
                            with col5:
                                st.metric("实体板", f"{c.get('entity_ratio', 0):.0f}%")
                            with col6:
                                btn_key = f"ai_{mode}_{code}"
                                if st.button(f"◆ AI分析", key=btn_key, use_container_width=True):
                                    st.session_state[f"analyze_{code}"] = True

                            # AI 分析结果（统一入口已处理，此处仅显示）
                            if st.session_state.get(f"analysis_result_{code}"):
                                result_text = st.session_state[f"analysis_result_{code}"]
                                with st.expander(f"◆ {code} AI分析报告", expanded=True):
                                    # 提取摘要
                                    import re
                                    sentiment_match = re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', result_text)
                                    position_match = re.search(r'仓位[建议]*[：:]\s*(.+?)(?:\n|$)', result_text)
                                    sentiment = sentiment_match.group(1).strip() if sentiment_match else "—"
                                    position = position_match.group(1).strip() if position_match else "—"
                                    st.markdown(f"""
                                    <div class="ai-summary-strip">
                                      <span class="ai-summary-badge sentiment">🎯 情绪档位: {sentiment}</span>
                                      <span class="ai-summary-badge position">💰 仓位建议: {position}</span>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    st.markdown(result_text)
                                    with st.expander("📋 复制全文"):
                                        st.code(result_text, language=None)

                            st.divider()

            # 导出 CSV
            all_candidates = []
            for mode in ["strict", "loose"]:
                for c in modes.get(mode, {}).get("candidates", []):
                    all_candidates.append({**c, "mode": mode})
            if all_candidates:
                st.divider()
                df_export = pd.DataFrame(all_candidates)
                st.download_button(
                    label="◆ 导出 CSV",
                    data=df_export.to_csv(index=False, encoding="utf-8-sig"),
                    file_name=f"candidates_all_{china_now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
                save_signals(all_candidates)

    # ============ 复盘页面 ============
    elif page == '◆ 复盘':
        # 自动验证 AI 记忆
        auto_verify_memory()

        # === 绩效总览 ===
        perf = compute_performance()
        if perf:
            return_color = '#00FF88' if perf['total_return'] >= 0 else '#FF5050'
            st.markdown(f"""
            <div style="display:flex;align-items:baseline;gap:36px;padding:4px 0 10px 0;flex-wrap:wrap">
              <div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#555577;letter-spacing:0.08em;margin-bottom:4px">累计收益</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:1.3rem;color:{return_color};font-weight:bold">{perf['total_return']:+.1f}%</div>
              </div>
              <div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#555577;letter-spacing:0.08em;margin-bottom:4px">胜率</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:1.3rem;color:#D0D0E8;font-weight:bold">{perf['win_rate']:.0%}</div>
              </div>
              <div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#555577;letter-spacing:0.08em;margin-bottom:4px">盈亏比</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:1.3rem;color:#D0D0E8;font-weight:bold">{perf['profit_factor']:.2f}</div>
              </div>
              <div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#555577;letter-spacing:0.08em;margin-bottom:4px">最大回撤</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:1.3rem;color:#FF6B6B;font-weight:bold">-{perf['max_drawdown']:.1f}%</div>
              </div>
            </div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.48rem;color:#444466;margin-bottom:12px">
              {perf['wins']}胜 / {perf['losses']}负 &nbsp;·&nbsp; 均盈+{perf['avg_win']:.1f}% / 均亏-{perf['avg_loss']:.1f}% &nbsp;·&nbsp; 总{perf['total_trades']}笔
            </div>
            """, unsafe_allow_html=True)

            # 收益曲线
            if perf['cum_returns'] and len(perf['cum_returns']) > 1:
                chart_df = pd.DataFrame({'累计收益%': perf['cum_returns']})
                st.line_chart(chart_df, height=160, use_container_width=True)
        else:
            st.markdown("""
            <div style="padding:40px 0;text-align:center;font-family:'JetBrains Mono',monospace;font-size:0.65rem;color:#444466">
              ◆ 暂无绩效数据<br>
              <span style="font-size:0.5rem;color:#333355">信号需 ≥3天 才能验证收益</span>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # === AI 记忆浏览器 ===
        memory = load_ai_memory()
        if memory:
            # 展平所有记录并排序
            all_records = []
            for code, records in memory.items():
                for rec in records:
                    all_records.append({**rec, 'code': code})
            all_records.sort(key=lambda r: r.get('date', ''), reverse=True)

            # 筛选器
            verdict_filter = st.selectbox(
                "验证状态", ["全部", "✅ 正确", "◈ 偏差", "⏳ 待验"],
                key="mem_filter", label_visibility="collapsed"
            )
            filtered = all_records
            if verdict_filter == "✅ 正确":
                filtered = [r for r in filtered if r.get('verdict') == 'correct']
            elif verdict_filter == "◈ 偏差":
                filtered = [r for r in filtered if r.get('verdict') == 'wrong']
            elif verdict_filter == "⏳ 待验":
                filtered = [r for r in filtered if r.get('verdict') is None]

            st.caption(f"◆ {len(filtered)} 条分析记录")

            # 渲染记忆卡片
            for rec in filtered[:30]:
                code = rec['code']
                verdict = rec.get('verdict')
                if verdict == 'correct':
                    border_color = "rgba(0,255,136,0.3)"
                    badge_html = '<span style="font-size:0.48rem;color:#00FF88;background:rgba(0,255,136,0.06);padding:1px 6px;border-radius:3px">✅</span>'
                elif verdict == 'wrong':
                    border_color = "rgba(255,80,80,0.25)"
                    badge_html = '<span style="font-size:0.48rem;color:#FF6B6B;background:rgba(255,80,80,0.05);padding:1px 6px;border-radius:3px">◈</span>'
                else:
                    border_color = "rgba(123,47,255,0.25)"
                    badge_html = '<span style="font-size:0.48rem;color:#9B6FFF;background:rgba(123,47,255,0.05);padding:1px 6px;border-radius:3px">⏳</span>'

                sdate = rec.get('date', '')
                sdate_display = f"{sdate[4:6]}-{sdate[6:]}" if len(sdate) >= 8 else sdate

                ret3_val = rec.get('return_3d')
                if ret3_val is not None:
                    ret3_str = f"{ret3_val:+.1f}%"
                    ret3_color = "#00FF88" if ret3_val > 0 else ("#FF5050" if ret3_val < 0 else "#444466")
                else:
                    ret3_str = "待验"
                    ret3_color = "#444466"

                analysis_full = rec.get('analysis', '')
                analysis_preview = analysis_full[:120]
                sentiment = rec.get('sentiment', '')
                position = rec.get('position', '')

                st.markdown(f"""
                <div style="border-left:2px solid {border_color};padding:8px 14px;margin-bottom:6px;background:rgba(10,11,20,0.5)">
                  <div style="display:flex;align-items:center;justify-content:space-between">
                    <div style="display:flex;align-items:center;gap:10px">
                      <span style="font-family:'JetBrains Mono',monospace;color:#D0D0E8;font-size:0.72rem">{code}</span>
                      {badge_html}
                      <span style="font-family:'JetBrains Mono',monospace;color:#555577;font-size:0.5rem">{rec.get('mode', '')}</span>
                    </div>
                    <span style="font-family:'JetBrains Mono',monospace;color:#444466;font-size:0.5rem">{sdate_display}</span>
                  </div>
                  <div style="display:flex;gap:14px;margin-top:4px;font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#555577;flex-wrap:wrap">
                    <span>¥{rec.get('entry_price', 0):.2f}</span>
                    <span>回调 {rec.get('pullback_pct', 0):.1f}%</span>
                    <span>3D <span style="color:{ret3_color}">{ret3_str}</span></span>
                    {f'<span>情绪: {sentiment}</span>' if sentiment else ''}
                    {f'<span>仓位: {position}</span>' if position else ''}
                  </div>
                  <div style="margin-top:4px;font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#666688;line-height:1.5">
                    <span style="color:#00F0FF">◆</span> {analysis_preview}{'...' if len(analysis_full) > 120 else ''}
                  </div>
                </div>
                """, unsafe_allow_html=True)

                # 可展开完整分析 + 重新分析按钮
                with st.expander(f"📖 完整分析", expanded=False):
                    st.markdown(analysis_full)
                    if st.button(f"🔄 重新分析(带入记忆)", key=f"reanalyze_{code}_{rec['date']}"):
                        st.session_state[f"analyze_{code}"] = True
                        st.session_state["nav_page"] = "◆ 选股"  # 切换到选股页执行分析
                        st.rerun()
        else:
            st.markdown("""
            <div style="padding:30px 0;text-align:center;font-family:'JetBrains Mono',monospace;font-size:0.65rem;color:#444466">
              ◆ AI 记忆为空<br>
              <span style="font-size:0.5rem;color:#333355">在选股页对候选股票使用 AI 分析后，记录会出现在这里</span>
            </div>
            """, unsafe_allow_html=True)

    elif page == '◆ 介绍':
        st.header("◆ 策略介绍")

        # 两种模式说明
        st.subheader("◆ 筛选模式")
        col_s, col_l = st.columns(2)
        with col_s:
            st.markdown("""
            <div style="background:rgba(255,51,102,0.04);border:1px solid rgba(255,51,102,0.2);border-radius:12px;padding:20px;height:100%">
              <div style="font-family:'JetBrains Mono',monospace;font-size:1rem;color:#FF3366;margin-bottom:12px">🔴 STRICT 严格</div>
              <table style="font-family:'JetBrains Mono',monospace;font-size:0.65rem;color:#9999BB;width:100%;line-height:2">
                <tr><td style="color:#6666AA">连板要求</td><td style="color:#FF3366">≥3 连板</td></tr>
                <tr><td style="color:#6666AA">实体板比例</td><td>≥55%</td></tr>
                <tr><td style="color:#6666AA">回调幅度</td><td>12% ~ 40%</td></tr>
                <tr><td style="color:#6666AA">缩量要求</td><td>≤67%</td></tr>
                <tr><td style="color:#6666AA">胜率</td><td style="color:#00FF88">69.6%</td></tr>
                <tr><td style="color:#6666AA">Sharpe</td><td style="color:#00F0FF">1.71</td></tr>
                <tr><td style="color:#6666AA">适用</td><td>震荡市 / 方向不明</td></tr>
              </table>
            </div>""", unsafe_allow_html=True)
        with col_l:
            st.markdown("""
            <div style="background:rgba(0,255,136,0.04);border:1px solid rgba(0,255,136,0.2);border-radius:12px;padding:20px;height:100%">
              <div style="font-family:'JetBrains Mono',monospace;font-size:1rem;color:#00FF88;margin-bottom:12px">🟢 LOOSE 宽松</div>
              <table style="font-family:'JetBrains Mono',monospace;font-size:0.65rem;color:#9999BB;width:100%;line-height:2">
                <tr><td style="color:#6666AA">连板要求</td><td style="color:#00FF88">≥2 连板</td></tr>
                <tr><td style="color:#6666AA">实体板比例</td><td>≥30%</td></tr>
                <tr><td style="color:#6666AA">回调幅度</td><td>8% ~ 40%</td></tr>
                <tr><td style="color:#6666AA">缩量要求</td><td>≤67%</td></tr>
                <tr><td style="color:#6666AA">胜率</td><td style="color:#00FF88">60.1%</td></tr>
                <tr><td style="color:#6666AA">Sharpe</td><td style="color:#00F0FF">1.29</td></tr>
                <tr><td style="color:#6666AA">适用</td><td>牛市 / 强趋势</td></tr>
              </table>
              <div style="font-family:'JetBrains Mono',monospace;font-size:0.55rem;color:#00FF88;margin-top:8px;padding:4px 8px;background:rgba(0,255,136,0.06);border-radius:4px">↳ STRICT 的超集（回调/缩量参数一致）</div>
            </div>""", unsafe_allow_html=True)

        st.divider()

        # 交易成本
        st.subheader("◆ 交易成本（A股）")
        st.markdown("""
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;color:#7777AA;line-height:2">
          <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(0,240,255,0.06)">
            <span>印花税（卖出）</span><span style="color:#FF3366">0.05%</span></div>
          <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(0,240,255,0.06)">
            <span>佣金（双向）</span><span style="color:#FFB800">0.025%</span></div>
          <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(0,240,255,0.06)">
            <span>过户费</span><span style="color:#FFB800">0.001%</span></div>
          <div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid rgba(0,240,255,0.06)">
            <span>滑点估算</span><span style="color:#FFB800">0.1%</span></div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;margin-top:4px;background:rgba(0,240,255,0.03);border-radius:4px;padding:6px 8px">
            <span style="color:#00F0FF">合计往返</span><span style="color:#00F0FF">≈0.30%</span></div>
        </div>""", unsafe_allow_html=True)

        st.divider()

        # v5 优化说明
        st.subheader("◆ v5 优化引擎")
        st.markdown("""
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;color:#7777AA;line-height:2">
          <p><span style="color:#00F0FF">三阶段漏斗</span> — 粗筛(~80k组合) → 精筛(前50聚类) → 超精细(局部搜索)</p>
          <p><span style="color:#00F0FF">多周期验证</span> — 跨3个时间段交叉验证，避免过拟合</p>
          <p><span style="color:#00F0FF">Bootstrap</span> — 1000次重采样，95%置信区间</p>
          <p><span style="color:#00F0FF">Walk-Forward</span> — 滚动窗口前向分析，验证时间稳定性</p>
          <p style="margin-top:8px;padding:8px;background:rgba(255,184,0,0.04);border:1px solid rgba(255,184,0,0.12);border-radius:6px;color:#FFB800">
            ⚠️ <code>require_oversold</code> 和 <code>require_low_close</code> 永久关闭——辛普森悖论：单因子有效但多因子组合中逆转。
          </p>
          <p style="margin-top:4px;color:#555577;font-size:0.55rem">
            参考：华安证券研报 — 32,615个首板样本分析
          </p>
        </div>""", unsafe_allow_html=True)

        st.divider()

        # 数据来源
        st.subheader("◆ 数据与调度")
        st.markdown("""
        <div style="font-family:'JetBrains Mono',monospace;font-size:0.6rem;color:#7777AA;line-height:2">
          <p><span style="color:#6666AA">数据源</span> yfinance (Yahoo Finance)</p>
          <p><span style="color:#6666AA">缓存</span> ~5,200 只A股 / CSV 格式</p>
          <p><span style="color:#6666AA">定时扫描</span> 交易日 10:00 / 11:30 / 14:00 / 15:00</p>
          <p><span style="color:#6666AA">自动推送</span> scan → JSON → git push → Streamlit Cloud</p>
          <p><span style="color:#6666AA">AI 分析</span> DeepSeek API · 量价形时四维框架</p>
        </div>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
