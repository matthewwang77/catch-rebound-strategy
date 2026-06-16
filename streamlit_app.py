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
import re
import market_news

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
      font-size: 2.2rem !important;
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
      font-size: 1.25rem !important;
      color: #00F0FF !important;
      border-left: 3px solid #00F0FF;
      padding-left: 12px !important;
    }

    h3 {
      font-weight: 600 !important;
      font-size: 0.95rem !important;
      color: #B0B0D0 !important;
    }

    /* === BODY TEXT === */
    /* NOTE: span is intentionally excluded to preserve Material Icons font */
    p, div, label, caption, li, td, th, button {
      font-family: 'JetBrains Mono', 'SF Mono', monospace !important;
    }

    [data-testid="stCaption"] {
      font-family: 'JetBrains Mono', 'SF Mono', monospace !important;
      font-size: 0.8rem !important;
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
      font-size: 0.9rem !important;
      letter-spacing: 0.1em !important;
    }

    [data-testid="stSidebar"] p { font-size: 0.8rem; color: #7777AA; line-height: 1.7; }

    [data-testid="stSidebar"] [data-testid="stRadio"] label {
      font-family: 'JetBrains Mono', monospace !important;
      font-size: 0.8rem;
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
      font-size: 0.75rem !important;
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
      font-size: 0.78rem !important;
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
      font-size: 0.75rem !important;
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
      font-size: 0.8rem !important;
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
      font-size: 0.75rem !important;
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
      font-size: 0.8rem;
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
      font-size: 0.8rem;
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
      font-size: 0.75rem;
      color: #5555AA;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .mode-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
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
    .mode-pill.bear {
      background: rgba(255,165,0,0.08);
      border: 1px solid rgba(255,165,0,0.25);
      color: #FFA500;
    }
    .mode-pill.bear:hover {
      background: rgba(255,165,0,0.14);
      border-color: rgba(255,165,0,0.45);
      box-shadow: 0 0 8px rgba(255,165,0,0.1);
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
    .neon-status-bar .status-text { font-size: 0.8rem; }
    .neon-status-bar.closed .status-text { color: #00F0FF; }
    .neon-status-bar.trading .status-text { color: #FFB800; }
    .neon-status-bar .status-spacer { flex: 1; }
    .neon-status-bar .status-label { font-size: 0.75rem; color: #6666AA; }
    .neon-status-bar .status-time { font-size: 0.78rem; color: #9999CC; }
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
      font-size: 0.78rem;
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
      font-size: 0.8rem;
      color: #7777AA;
      padding: 10px 12px;
      border-radius: 8px;
      background: rgba(0,240,255,0.02);
      border: 1px solid rgba(0,240,255,0.06);
      line-height: 1.8;
    }
    .sidebar-data-status .stat-label {
      color: #555588;
      font-size: 0.75rem;
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


    /* === TACTICAL TERMINAL ENHANCEMENTS (v6 Unified) === */

    .market-status-card {
      background: linear-gradient(135deg, rgba(0,255,136,0.03) 0%, rgba(0,15,10,0.6) 100%);
      border: 1px solid rgba(0,255,136,0.15);
      border-radius: 8px;
      padding: 18px 24px;
      margin-bottom: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .market-index-row {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      color: #e0e0e0;
    }
    .market-sentiment { flex-shrink: 0; }
    .sentiment-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      color: #00ff88;
      background: rgba(0,255,136,0.06);
      border: 1px solid rgba(0,255,136,0.2);
      border-radius: 4px;
      padding: 4px 14px;
    }

    .section-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
      color: #00ff88;
      letter-spacing: 0.06em;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid rgba(0,255,136,0.08);
    }

    .status-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      padding: 4px 10px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .status-badge.analyzing {
      color: #00e5ff;
      background: rgba(0,229,255,0.06);
      border: 1px solid rgba(0,229,255,0.2);
      animation: pulse-glow 1.5s ease-in-out infinite;
    }
    .status-badge.queued {
      color: #666;
      background: rgba(100,100,100,0.05);
      border: 1px solid rgba(100,100,100,0.15);
    }
    .status-badge.done {
      color: #ffd700;
      background: rgba(255,215,0,0.05);
      border: 1px solid rgba(255,215,0,0.2);
    }
    .status-badge.pending {
      color: #888;
      background: transparent;
      border: 1px dashed rgba(100,100,100,0.2);
    }

    /* ── 候选卡片 v3 ── */
    .candidate-card {
      background: linear-gradient(135deg, rgba(13,13,30,0.95), rgba(8,8,20,0.9));
      border: 1px solid rgba(0,255,136,0.12);
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 10px;
      transition: all 0.2s ease;
      animation: fadeUp 0.4s ease both;
    }
    .candidate-card:nth-child(1) { animation-delay: 0s; }
    .candidate-card:nth-child(2) { animation-delay: 0.05s; }
    .candidate-card:nth-child(3) { animation-delay: 0.1s; }
    .candidate-card:nth-child(4) { animation-delay: 0.15s; }
    .candidate-card:nth-child(5) { animation-delay: 0.2s; }
    .candidate-card:hover {
      border-color: rgba(0,255,136,0.35);
      box-shadow: 0 0 20px rgba(0,255,136,0.06);
      transform: translateY(-1px);
    }
    .candidate-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    .candidate-code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9rem;
      font-weight: 700;
      color: #00ff88;
    }
    .candidate-name {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      color: #aaa;
    }
    .candidate-mode {
      margin-left: auto;
      font-family: 'Orbitron', monospace;
      font-size: 0.75rem;
      padding: 3px 10px;
      border-radius: 4px;
      background: rgba(0,255,136,0.08);
      color: #00ff88;
      letter-spacing: 0.5px;
    }
    .candidate-metrics {
      display: flex;
      gap: 16px;
      margin-bottom: 12px;
    }
    .mini-metric {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .mini-label {
      font-family: 'Orbitron', monospace;
      font-size: 0.75rem;
      color: #666;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .mini-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.95rem;
      font-weight: 600;
      color: #e0e0e0;
    }
    .candidate-ai {
      border-top: 1px solid rgba(255,255,255,0.05);
      padding-top: 10px;
    }
    .ai-inline-strip {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .ai-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      padding: 4px 12px;
      border-radius: 6px;
    }
    /* AI 判断：按结论着色 — 绿=参与, 琥珀=观望, 红=放弃 */
    .ai-badge.opinion { color: #ffd700; background: rgba(255,215,0,0.08); border: 1px solid rgba(255,215,0,0.2); }
    .ai-badge.opinion.opinion-participate { color: #00ff88; background: rgba(0,255,136,0.08); border: 1px solid rgba(0,255,136,0.25); }
    .ai-badge.opinion.opinion-wait { color: #ffb800; background: rgba(255,184,0,0.08); border: 1px solid rgba(255,184,0,0.25); }
    .ai-badge.opinion.opinion-skip { color: #ff3366; background: rgba(255,51,102,0.08); border: 1px solid rgba(255,51,102,0.25); }
    .ai-badge.sentiment { color: #00f0ff; background: rgba(0,240,255,0.08); border: 1px solid rgba(0,240,255,0.2); }
    .ai-badge.position { color: #ff6b35; background: rgba(255,107,53,0.08); border: 1px solid rgba(255,107,53,0.2); }

    .analysis-progress-bar {
      background: rgba(0,255,136,0.02);
      border: 1px solid rgba(0,255,136,0.1);
      border-radius: 8px;
      padding: 14px 18px;
      margin: 10px 0 16px 0;
    }
    .progress-header {
      display: flex;
      justify-content: space-between;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      color: #00ff88;
      margin-bottom: 8px;
    }
    .progress-track {
      height: 6px;
      background: rgba(0,255,136,0.06);
      border-radius: 3px;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #00ff88, #00e5ff);
      border-radius: 3px;
      transition: width 0.5s ease;
      animation: pulse-glow 2s ease-in-out infinite;
    }
    .progress-footer {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      color: #888;
      margin-top: 6px;
    }

    .perf-panel {
      background: rgba(0,15,10,0.4);
      border: 1px solid rgba(0,255,136,0.08);
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 12px;
    }
    .perf-grid {
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
      margin: 10px 0;
    }
    .perf-card { min-width: 100px; text-align: center; }
    .perf-label {
      font-family: 'Orbitron', monospace;
      font-size: 0.78rem;
      color: #666;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .perf-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.6rem;
      font-weight: 700;
    }
    .perf-detail {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      color: #888;
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid rgba(0,255,136,0.06);
    }

    /* ── AI 记忆卡片 (复盘页) ── */
    .memory-card-v3 {
      background: rgba(13,13,30,0.85);
      border-left: 3px solid var(--green);
      border-radius: 0 8px 8px 0;
      padding: 14px 18px;
      margin-bottom: 8px;
      border-top: 1px solid rgba(255,255,255,0.04);
      border-right: 1px solid rgba(255,255,255,0.04);
      border-bottom: 1px solid rgba(255,255,255,0.04);
      transition: all 0.2s ease;
    }
    .memory-card-v3:hover {
      background: rgba(13,13,30,0.95);
      transform: translateX(2px);
    }
    .memory-card-v3.verdict-correct {
      border-left-color: #00ff88;
    }
    .memory-card-v3.verdict-wrong {
      border-left-color: #ff3366;
    }
    .memory-card-v3.verdict-pending {
      border-left-color: #7b2fff;
    }
    .memory-verdict-badge {
      font-family: 'Orbitron', monospace;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 3px 10px;
      border-radius: 4px;
      display: inline-block;
    }
    .memory-verdict-badge.correct {
      color: #00ff88;
      background: rgba(0,255,136,0.08);
      border: 1px solid rgba(0,255,136,0.2);
    }
    .memory-verdict-badge.wrong {
      color: #ff3366;
      background: rgba(255,51,102,0.08);
      border: 1px solid rgba(255,51,102,0.2);
    }
    .memory-verdict-badge.pending {
      color: #7b2fff;
      background: rgba(123,47,255,0.08);
      border: 1px solid rgba(123,47,255,0.2);
    }
    .memory-meta-row {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.78rem;
      color: #888;
      margin: 8px 0;
    }
    .memory-returns-row {
      display: flex;
      gap: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.8rem;
    }
    .memory-ret-badge {
      padding: 2px 8px;
      border-radius: 3px;
      font-weight: 600;
    }
    .memory-ret-badge.positive {
      color: #00ff88;
      background: rgba(0,255,136,0.06);
    }
    .memory-ret-badge.negative {
      color: #ff3366;
      background: rgba(255,51,102,0.06);
    }

    .intro-section {
      font-family: 'JetBrains Mono', monospace;
      color: #aaa;
      font-size: 0.8rem;
      line-height: 1.7;
    }
    .intro-section h3 {
      color: #00ff88;
      font-family: 'Orbitron', sans-serif;
      font-size: 0.95rem;
      letter-spacing: 0.06em;
      margin-bottom: 8px;
    }
    .intro-section h4 {
      color: #00e5ff;
      font-size: 0.8rem;
      letter-spacing: 0.04em;
      margin-top: 16px;
      margin-bottom: 6px;
    }
    .intro-section ul { list-style: none; padding-left: 0; }
    .intro-section li { padding: 3px 0; }
    .intro-section li::before { content: "◆ "; color: #00ff88; }

    @keyframes pulse-glow {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }

    /* ═══════════════════════════════════════════════════════════
       v6.1 复盘系统升级 — 绩效面板v2 + SVG曲线 + 记忆卡片v4
       ═══════════════════════════════════════════════════════════ */

    /* ── 绩效面板 v2 (不对称B布局) ── */
    .perf-panel-v2 {
      display: flex;
      gap: 16px;
      align-items: stretch;
      margin-bottom: 16px;
    }
    .perf-hero {
      flex: 2;
      background: linear-gradient(135deg, rgba(0,255,136,0.06), rgba(0,255,136,0.01));
      border: 1px solid rgba(0,255,136,0.18);
      border-radius: 10px;
      padding: 24px 28px;
      text-align: center;
      display: flex;
      flex-direction: column;
      justify-content: center;
      transition: all 0.3s ease;
    }
    .perf-hero:hover {
      border-color: rgba(0,255,136,0.35);
      box-shadow: 0 0 24px rgba(0,255,136,0.08);
    }
    .perf-hero-label {
      font-family: 'Orbitron', monospace;
      font-size: 0.72rem;
      color: #555;
      text-transform: uppercase;
      letter-spacing: 2px;
      margin-bottom: 8px;
    }
    .perf-hero-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 2.8rem;
      font-weight: 900;
      text-shadow: 0 0 20px rgba(0,255,136,0.2);
      margin: 6px 0;
    }
    .perf-hero-sub {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      padding: 4px 14px;
      border-radius: 14px;
      display: inline-block;
      margin: 0 auto;
      width: fit-content;
    }
    .perf-side {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .perf-side-item {
      flex: 1;
      background: rgba(13,13,30,0.85);
      border: 1px solid rgba(255,255,255,0.05);
      border-radius: 8px;
      padding: 14px 16px;
      text-align: center;
      transition: all 0.2s ease;
    }
    .perf-side-item:hover {
      border-color: rgba(255,255,255,0.12);
    }
    .perf-side-label {
      font-family: 'Orbitron', monospace;
      font-size: 0.65rem;
      color: #555;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 4px;
    }
    .perf-side-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.3rem;
      font-weight: 700;
    }
    .perf-detail-row {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      color: #888;
      text-align: center;
      padding-top: 12px;
      margin-top: 8px;
      border-top: 1px solid rgba(255,255,255,0.04);
    }

    /* ── SVG 收益曲线 ── */
    .chart-container {
      background: linear-gradient(135deg, rgba(0,255,136,0.04), rgba(0,240,255,0.02));
      border: 1px solid rgba(0,255,136,0.08);
      border-radius: 8px;
      padding: 16px 20px;
      margin: 12px 0;
    }
    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
    }

    /* ── 记忆卡片 v4 (D+宽松版) ── */
    .memory-card-v4 {
      background: rgba(13,13,30,0.9);
      border-radius: 0 8px 8px 0;
      padding: 18px 22px;
      margin-bottom: 14px;
      border-top: 1px solid rgba(255,255,255,0.04);
      border-right: 1px solid rgba(255,255,255,0.04);
      border-bottom: 1px solid rgba(255,255,255,0.04);
      transition: all 0.2s ease;
    }
    .memory-card-v4:hover {
      background: rgba(13,13,30,0.97);
      transform: translateX(2px);
    }
    .memory-card-v4.vc-correct    { border-left: 3px solid #00ff88; }
    .memory-card-v4.vc-wrong      { border-left: 3px solid #ff3366; }
    .memory-card-v4.vc-missed     { border-left: 3px solid #ffb800; }
    .memory-card-v4.vc-avoided    { border-left: 3px solid #00cc66; }
    .memory-card-v4.vc-noted_up   { border-left: 3px solid #7b2fff; }
    .memory-card-v4.vc-noted_down { border-left: 3px solid #7b2fff; }
    .memory-card-v4.vc-pending    { border-left: 3px solid #444466; }

    .mem-header-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      flex-wrap: wrap;
      gap: 8px;
    }
    .mem-code { font-family: 'JetBrains Mono', monospace; color: #00ff88; font-size: 0.9rem; font-weight: 700; }
    .mem-name { font-family: 'JetBrains Mono', monospace; color: #CCC; font-size: 0.8rem; }
    .mem-date { font-family: 'JetBrains Mono', monospace; color: #666; font-size: 0.72rem; }
    .mem-opinion { font-size: 0.8rem; font-weight: 600; }

    .mem-verdict-badge {
      font-family: 'Orbitron', monospace;
      font-size: 0.72rem;
      font-weight: 600;
      padding: 4px 12px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .mem-verdict-badge.correct    { color: #00ff88; background: rgba(0,255,136,0.1);  border: 1px solid rgba(0,255,136,0.2); }
    .mem-verdict-badge.wrong      { color: #ff3366; background: rgba(255,51,102,0.1);  border: 1px solid rgba(255,51,102,0.2); }
    .mem-verdict-badge.missed     { color: #ffb800; background: rgba(255,184,0,0.1);   border: 1px solid rgba(255,184,0,0.25); }
    .mem-verdict-badge.avoided    { color: #00cc66; background: rgba(0,204,102,0.1);   border: 1px solid rgba(0,204,102,0.2); }
    .mem-verdict-badge.noted_up   { color: #7b2fff; background: rgba(123,47,255,0.1);  border: 1px solid rgba(123,47,255,0.2); }
    .mem-verdict-badge.noted_down { color: #7b2fff; background: rgba(123,47,255,0.1);  border: 1px solid rgba(123,47,255,0.2); }
    .mem-verdict-badge.pending    { color: #666;    background: rgba(100,100,100,0.05); border: 1px solid rgba(100,100,100,0.15); }

    .mem-metrics-row {
      display: flex;
      gap: 20px;
      font-size: 0.78rem;
      color: #888;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .mem-review-row {
      border-top: 1px solid rgba(255,255,255,0.05);
      padding-top: 12px;
      font-size: 0.78rem;
      color: #888;
      line-height: 1.6;
    }
    .mem-review-label { font-weight: 600; }
    .mem-review-label.missed { color: #ffb800; }
    .mem-review-label.lesson { color: #00ff88; }
    .mem-review-label.wrong  { color: #ff3366; }

    /* ── 新闻总览卡片 ── */
    .news-summary-card {
      background: rgba(13,13,30,0.9);
      border: 1px solid rgba(0,240,255,0.1);
      border-radius: 10px;
      padding: 18px 22px;
      margin-bottom: 18px;
      display: flex;
      align-items: flex-start;
      gap: 16px;
      flex-wrap: wrap;
    }
    .news-summary-text {
      flex: 1;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      color: #CCC;
      line-height: 1.7;
      min-width: 280px;
    }
    .news-sentiment-badge {
      font-family: 'Orbitron', monospace;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 6px;
      white-space: nowrap;
      border: 1px solid;
    }

    /* ── 新闻卡片 v1 ── */
    .news-card {
      background: rgba(13,13,30,0.85);
      border-radius: 0 8px 8px 0;
      padding: 16px 20px;
      margin-bottom: 12px;
      border-top: 1px solid rgba(255,255,255,0.04);
      border-right: 1px solid rgba(255,255,255,0.04);
      border-bottom: 1px solid rgba(255,255,255,0.04);
      border-left: 3px solid rgba(0,240,255,0.2);
      transition: all 0.2s ease;
    }
    .news-card:hover {
      background: rgba(13,13,30,0.95);
      border-left-color: rgba(0,240,255,0.5);
      transform: translateX(2px);
    }
    .news-card-header {
      margin-bottom: 10px;
    }
    .news-card-title-row {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 8px;
    }
    .news-title-text {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      font-weight: 600;
      color: #E8E8E8;
      line-height: 1.5;
      flex: 1;
    }
    .news-importance {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
      color: #ffb800;
      letter-spacing: 2px;
      white-space: nowrap;
      padding-top: 2px;
    }
    .news-source-badge {
      font-family: 'Orbitron', monospace;
      font-size: 0.7rem;
      font-weight: 600;
      padding: 2px 10px;
      border-radius: 4px;
      white-space: nowrap;
    }
    .news-time {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: #666;
    }
    .news-read-link {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      color: #00F0FF;
      text-decoration: none;
      transition: all 0.2s;
    }
    .news-read-link:hover {
      color: #00FF88;
      text-decoration: underline;
    }
    .news-card-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .news-meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .news-sector-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      padding: 3px 10px;
      border-radius: 4px;
      background: rgba(0,240,255,0.06);
      border: 1px solid rgba(0,240,255,0.15);
      color: #00F0FF;
      white-space: nowrap;
    }
    .news-stock-code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.7rem;
      padding: 2px 8px;
      border-radius: 3px;
      background: rgba(0,255,136,0.05);
      border: 1px solid rgba(0,255,136,0.12);
      color: #00FF88;
      white-space: nowrap;
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
    """获取三大指数最新数据（包含涨跌幅）。

    优先从 latest_scan_results.json 读取已修正的涨幅（处理 Yahoo 数据缺口），
    实时价格仍从 yfinance 获取。
    """
    import json as _json

    # 预读 JSON 中的修正涨幅
    json_pct = {}
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "latest_scan_results.json")
        if os.path.exists(json_path):
            with open(json_path) as f:
                scan = _json.load(f)
            market_json = scan.get("market", {})
            # JSON key → 显示名称 映射 (JSON: "上证"/"深证"/"创业板")
            _key_map = {"上证": "上证指数", "深证": "深证成指", "创业板": "创业板指"}
            for json_key, display_name in _key_map.items():
                m = market_json.get(json_key, {})
                if "pct" in m:
                    json_pct[display_name] = m["pct"]
    except Exception:
        pass

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

                    # 优先读 JSON 中的修正涨幅（已处理 Yahoo 数据缺口）
                    if name in json_pct and json_pct[name] is not None:
                        pct = json_pct[name]
                    else:
                        # 检测 Yahoo 日期缺口：若最后两点间隔 > 2 自然日，用个股推算
                        idx_dates = df.index
                        gap_days = (idx_dates[-1] - idx_dates[-2]).days
                        if gap_days > 2:
                            try:
                                _mkt = {"上证指数": "sh", "深证成指": "sz", "创业板指": "cyb"}.get(name)
                                stock_pct = screener._estimate_index_daily_pct(market=_mkt)
                                if stock_pct is not None:
                                    pct = round(stock_pct, 2)
                                else:
                                    pct = round((current / prev - 1) * 100, 2)
                            except Exception:
                                pct = round((current / prev - 1) * 100, 2)
                        else:
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
                    # 降级：优先读 JSON 修正涨幅，其次用 fast_info.previousClose
                    if name in json_pct and json_pct[name] is not None:
                        pct = json_pct[name]
                        has_delta = True
                    else:
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
            }, index=pd.to_datetime(df['date'].values)).dropna()
            if len(stock_df) >= 10:
                all_data[code] = stock_df
        except Exception:
            failed.append(code)
    return all_data, failed


def load_all_recent_data(codes, lookback_days=30):
    # DEPRECATED: not called in main(), retained for reference
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
    # DEPRECATED: not called in main(), retained for reference
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
        except Exception: pass

    progress_bar.progress(100, text=f"▸ 100% 完成: {len(all_data)}只, 今日涨停{limit_up_count}只")
    progress_bar.empty()
    return all_data

# fast_ai_analysis 已移除 — AI 分析在 auto_daily.py 后台完成
# check_return / check_return_v5 已移除 — 收益验证在 auto_daily.py 后台完成

# ==================== 多模式筛选 ====================
def screen_all_modes(all_data):
    # DEPRECATED: not called in main(), retained for reference
    """用 strict/loose/bear 三种参数分别筛选，返回 {mode: [候选列表]}"""
    modes = ["strict", "loose", "bear"]
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
            threshold = 18.5 if code.startswith(('30', '688', '689')) else 9.5
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
SIGNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_tracker.csv")

def save_signals(all_candidates):
    """将今日候选保存到信号追踪文件（去重）"""
    if not all_candidates:
        return

    # 批量获取名称/板块
    codes = [c.get('代码', c.get('code', '')) for c in all_candidates]
    name_info = name_lookup.batch_lookup(codes, max_fetch=10)

    new_rows = []
    for c in all_candidates:
        info = name_info.get(c.get('代码', c.get('code', '')), {})
        new_rows.append({
            'signal_date': c.get('signal_date', china_now().strftime('%Y%m%d')),
            'code': c.get('代码', c.get('code', '')),
            'name': info.get('name', '') or '',
            'sector': '',
            'mode': c.get('mode', ''),
            'entry_price': c.get('price', c.get('最新价', 0)),
            'pullback_pct': c.get('pullback_pct', c.get('回调比', 0)),
            'limit_days': c.get('limit_days', c.get('连板数', 0)),
        })

    df_new = pd.DataFrame(new_rows)

    # 读取已有记录，去重 — 同一(code, entry_price)在20天窗口内不重复
    if os.path.exists(SIGNAL_FILE):
        df_old = pd.read_csv(SIGNAL_FILE)
        df_old['signal_date'] = df_old['signal_date'].astype(str)

        keep_rows = []
        for _, row in df_new.iterrows():
            sig_date = str(row['signal_date'])
            code = row['code']

            try:
                entry_price = round(float(row['entry_price']), 2)
                sig_dt = datetime.strptime(sig_date, '%Y%m%d')
                cutoff_dt = sig_dt - timedelta(days=20)
                cutoff_str = cutoff_dt.strftime('%Y%m%d')
            except ValueError:
                keep_rows.append(True)
                continue

            in_window = df_old[
                (df_old['code'] == code) &
                (df_old['entry_price'].round(2) == entry_price) &
                (df_old['signal_date'] >= cutoff_str) &
                (df_old['signal_date'] <= sig_date)
            ]
            keep_rows.append(len(in_window) == 0)

        df_new = df_new[keep_rows]
        if len(df_new) == 0:
            return
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new

    df_combined.to_csv(SIGNAL_FILE, index=False, encoding='utf-8-sig')


# ==================== AI 记忆系统 ====================
AI_MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_memory.json")

def load_ai_memory():
    """加载 AI 记忆文件。返回 dict {code: [records]}。不存在则返回 {}。"""
    if not os.path.exists(AI_MEMORY_FILE):
        return {}
    try:
        with open(AI_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}
    except Exception:
        return {}

def save_ai_memory(memory):
    """保存 AI 记忆到文件（原子写入，防止并发损坏）"""
    tmp_path = AI_MEMORY_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, AI_MEMORY_FILE)  # POSIX 原子操作

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
        # 优先从仓位行同时提取仓位和情绪：仓位建议：0成仓（冰点/观望）
        m = _re.search(r'仓位建议[：:]\s*(.+?)（(.+?)）', analysis_text)
        if m:
            position = m.group(1).strip().strip('*')   # "0成仓"
            sentiment = m.group(2).strip().strip('*')  # "冰点/观望"
        else:
            # 备用：独立提取（无括号格式）
            pm = _re.search(r'仓位[建议]*[：:]\s*(.+?)(?:\n|$|\*\*)', analysis_text)
            if pm:
                position = pm.group(1).strip().strip('*')
        # 情绪备用提取
        if not sentiment:
            sm = _re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$|\*\*)', analysis_text)
            if sm:
                sentiment = sm.group(1).strip().strip('*')
        # 最终结论
        om = _re.search(r'最终结论[：:]\s*(.+?)(?:\n|$|\*\*)', analysis_text)
        if om:
            opinion = om.group(1).strip().strip('*')
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

def get_stock_memory_context(code):
    """获取某只股票的历史分析上下文，用于注入 AI prompt。含自我反思。

    当历史记录中有 verdict=missed 或 wrong 时，注入反思提示帮助 AI 学习。
    返回格式化文本或 None。
    """
    memory = load_ai_memory()
    if code not in memory or not memory[code]:
        return None
    records = memory[code]
    lines = ["[历史分析记录 · 含反思]"]
    has_mistakes = False

    for rec in records[-5:]:  # 最多取最近5条
        sdate = rec.get("date", "未知")
        if len(sdate) == 8:
            sdate = f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}"
        sentiment = rec.get("sentiment", "")
        position = rec.get("position", "")
        opinion = rec.get("opinion", "")
        verdict = rec.get("verdict", "")
        ret7 = rec.get("return_7d")
        lesson = rec.get("lesson", "")
        why_wrong = rec.get("why_wrong", "")
        missed_signal = rec.get("missed_signal", "")

        # 构建摘要
        summary_parts = [f"情绪:{sentiment}", f"仓位:{position}"]
        if opinion:
            summary_parts.append(f"结论:{opinion}")

        if verdict == "correct":
            summary_parts.append(f"7日后 +{ret7}% ✅准确预判")
        elif verdict == "wrong":
            has_mistakes = True
            summary_parts.append(f"7日后 {ret7}% ❌判断失误")
        elif verdict == "missed":
            has_mistakes = True
            summary_parts.append(f"7日后 +{ret7}% 🔶错失机会")
        elif verdict == "avoided":
            summary_parts.append(f"7日后 {ret7}% 🛡正确规避")
        else:
            summary_parts.append("(⏳待验证)")

        lines.append(f"- {sdate}: {' | '.join(summary_parts)}")

        # 追加反思教训
        if lesson and verdict in ('missed', 'wrong'):
            lines.append(f"  ⚠️ 教训：{lesson}")
        if missed_signal and verdict in ('missed', 'wrong'):
            lines.append(f"  🔍 遗漏信号：{missed_signal}")

    # 如果有错误记录，追加全局反思提示
    if has_mistakes:
        lines.append("\n⚠️ 注意：你之前对该股有判断失误。请反思之前的遗漏信号，本次分析更加谨慎。")

    return "\n".join(lines)

def _build_svg_chart(cum_returns, returns_list, line_color="#00ff88"):
    """构建 SVG 双图收益曲线：上=累计曲线+填充，下=逐笔柱状。"""
    if not cum_returns or len(cum_returns) < 2:
        return ""

    n = len(cum_returns)
    w, h_top, h_bar = 400, 80, 36
    total_h = h_top + h_bar + 8
    pad_l, pad_r = 4, 4

    # 累计曲线数据
    mn = min(cum_returns)
    mx = max(cum_returns)
    rng = max(mx - mn, 1)

    def x_pos(i):
        return pad_l + (w - pad_l - pad_r) * i / (n - 1)

    def y_pos(val, h):
        return h * (1 - (val - mn) / rng) * 0.85 + h * 0.075

    # 曲线路径
    path_parts = []
    for i, v in enumerate(cum_returns):
        cmd = "M" if i == 0 else "L"
        path_parts.append(f"{cmd}{x_pos(i):.1f},{y_pos(v,h_top):.1f}")

    line_path = " ".join(path_parts)

    # 填充区域
    area_path = f"{line_path} L{x_pos(n-1):.1f},{h_top} L{x_pos(0):.1f},{h_top} Z"

    # 网格线
    grid_y = [h_top * 0.25, h_top * 0.5, h_top * 0.75]
    grid_lines = ""
    for gy in grid_y:
        grid_lines += f'<line x1="{pad_l}" y1="{gy:.0f}" x2="{w-pad_r}" y2="{gy:.0f}" stroke="rgba(255,255,255,0.04)" stroke-dasharray="4,4"/>'

    # 逐笔柱状
    bars = ""
    bar_w = max(6, (w - pad_l - pad_r) / n * 0.7)
    gap = (w - pad_l - pad_r) / n
    for i, r in enumerate(returns_list):
        rp = r.get('return_pct', r) if isinstance(r, dict) else r
        bx = pad_l + gap * i + (gap - bar_w) / 2
        max_abs = max(abs(rp) for rp in returns_list) if returns_list else 1
        bh = abs(rp) / max_abs * h_bar * 0.8 if max_abs > 0 else 5
        bh = max(3, min(bh, h_bar - 4))
        color = "rgba(0,255,136,0.55)" if rp > 0 else "rgba(255,51,102,0.4)"
        by = (h_bar - bh) / 2 if rp > 0 else h_bar / 2
        bars += f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="2" fill="{color}"/>'

    return f"""
    <div class="chart-container">
      <div class="chart-header">
        <span style="color:#666;text-transform:uppercase;letter-spacing:1px">收益曲线</span>
        <span style="color:{line_color};font-weight:700">{cum_returns[-1]:+.1f}%</span>
      </div>
      <svg viewBox="0 0 {w} {total_h}" style="width:100%;height:auto;display:block">
        <defs>
          <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="{line_color}" stop-opacity="0.18"/>
            <stop offset="100%" stop-color="{line_color}" stop-opacity="0"/>
          </linearGradient>
          <filter id="lineGlow">
            <feGaussianBlur stdDeviation="1.5" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>
        <!-- 累计曲线区域 -->
        {grid_lines}
        <path d="{area_path}" fill="url(#chartFill)"/>
        <path d="{line_path}" fill="none" stroke="{line_color}" stroke-width="1.8" filter="url(#lineGlow)"/>
        <!-- 分隔线 -->
        <line x1="0" y1="{h_top}" x2="{w}" y2="{h_top}" stroke="rgba(255,255,255,0.05)"/>
        <!-- 逐笔柱状区域 -->
        {bars}
      </svg>
    </div>"""


def compute_performance(mode_filter=None, days_window=30):
    """从 ai_memory.json 预计算数据中读取绩效指标（不再调用 yfinance）。

    - mode_filter: 'strict' / 'loose' / None(全部)
    - days_window: 只看最近N天的记录（自然日）
    - 使用 ai_memory.json 中预计算的 return_7d
    """
    memory = load_ai_memory()
    if not memory:
        return None
    try:
        today_int = int(china_now().strftime('%Y%m%d'))
        cutoff_date = china_now() - timedelta(days=days_window)
        cutoff = int(cutoff_date.strftime('%Y%m%d'))

        # 展平所有已验证的记录
        returns = []
        wins = 0
        losses = 0
        neutral = 0
        mode_hold_days = {}
        for code, records in memory.items():
            for r in records:
                date = str(r.get('date', ''))
                if len(date) < 8:
                    continue
                if int(date) < cutoff:
                    continue
                mode = r.get('mode', '')
                if mode_filter and mode != mode_filter:
                    continue
                # 收集各模式的实际持有天数
                if mode and mode not in mode_hold_days:
                    mode_hold_days[mode] = screener.SCREEN_MODES.get(mode, {}).get('hold_days', 7)
                # 使用预计算的 7d 收益
                r7 = r.get('return_7d')
                if r7 is None:
                    if today_int - int(date) < 7:
                        continue
                    continue  # 超过7天但无数据，跳过
                returns.append({
                    'date': date,
                    'code': code,
                    'mode': mode,
                    'return_pct': r7,
                    'exit_reason': r.get('exit_reason', ''),
                })
                if r7 > 0:
                    wins += 1
                elif r7 < 0:
                    losses += 1
                else:
                    neutral += 1

        if not returns:
            return None

        total_trades = wins + losses + neutral
        win_rate = wins / total_trades if total_trades > 0 else 0
        avg_win = sum(r['return_pct'] for r in returns if r['return_pct'] > 0) / wins if wins > 0 else 0
        avg_loss = abs(sum(r['return_pct'] for r in returns if r['return_pct'] < 0) / losses) if losses > 0 else 0
        profit_factor = (avg_win * wins) / (avg_loss * losses) if (avg_loss * losses) > 0 else 999.99

        returns.sort(key=lambda r: r['date'])

        # 复合收益曲线
        equity = 1.0
        cum_returns = []
        dates_for_chart = []
        peak = 1.0
        max_dd = 0.0
        for r in returns:
            equity *= (1 + r['return_pct'] / 100)
            cum_returns.append(round((equity - 1) * 100, 2))
            d = r['date']
            dates_for_chart.append(f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) >= 8 else d)
            peak = max(peak, equity)
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

        total_return = round((equity - 1) * 100, 2)
        chart_df = pd.DataFrame(
            {'累计收益%': cum_returns},
            index=pd.Index(dates_for_chart, name='日期')
        )

        exit_reasons = {}
        for r in returns:
            reason = r.get('exit_reason', '')
            if reason:
                exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

        return {
            'total_return': total_return,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'neutral': neutral,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'max_drawdown': round(max_dd, 2),
            'cum_returns': cum_returns,
            'chart_df': chart_df,
            'returns': returns,
            'exit_reasons': exit_reasons,
            'mode_hold_days': mode_hold_days,
        }
    except Exception:
        return None


# ==================== 选股结果展示 ====================

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
        # 防御性过滤：只保留 SCREEN_MODES 中存在的模式（移除旧版 bull 等）
        valid_modes = set(screener.SCREEN_MODES.keys())
        data["modes"] = {k: v for k, v in data["modes"].items() if k in valid_modes}
        if not data["modes"]:
            return None
        # 规范化旧版 regime.status (旧版可能是 "bull")
        regime = data.get("regime", {})
        if regime.get("status") not in ("bear", "neutral"):
            regime["status"] = "neutral"
            if regime.get("recommended_mode") not in valid_modes:
                regime["recommended_mode"] = "strict"
        return data
    except Exception:
        return None





# ==================== AI 标签格式化 ====================
def _format_ai_badges(opinion, sentiment, position):
    """将 AI 分析的三要素格式化为自解释的彩色标签。

    Args:
        opinion: AI 最终结论，如 "【参与】" / "【观望】" / "【放弃】"
        sentiment: 市场情绪/大盘环境，如 "发酵期4档" / "谨慎" / "冰点"
        position: 仓位建议，如 "3成仓" / "0成仓" / "半仓"
    Returns:
        HTML string: 三枚标签组成的 inline strip
    """
    # ── 1. 判断标签（带颜色） ──
    op = opinion.strip().strip('【】◆ ').strip()
    if any(kw in op for kw in ['参与', '买入', '做多']):
        op_cls, op_icon, op_label = 'opinion-participate', '✅', f'判断: {op}'
    elif any(kw in op for kw in ['放弃', '卖出', '规避', '不做']):
        op_cls, op_icon, op_label = 'opinion-skip', '❌', f'判断: {op}'
    else:
        # 观望 或 空值
        op_cls, op_icon = 'opinion-wait', '⏸️'
        op_label = f'判断: {op}' if op else '判断: 待定'

    # ── 2. 大盘标签 ──
    st = sentiment.strip().strip('*').strip()
    if st and st not in ('—', 'N/A', ''):
        # 补全截断的档位描述：如 "发酵期4" → "发酵期4档"
        if re.search(r'[档期]\d$', st) and not st.endswith('档'):
            st += '档'
        st_label = f'大盘: {st}'
    else:
        st_label = '大盘: —'

    # ── 3. 仓位标签 ──
    ps = position.strip().strip('*').strip()
    if ps and ps not in ('—', 'N/A', ''):
        ps_label = f'仓位: {ps}' if '仓' not in ps else f'仓位: {ps.replace("仓", "")}成'
        # 避免 "仓位: 3成成"
        if ps_label.endswith('成成'):
            ps_label = ps_label[:-1]
    else:
        ps_label = '仓位: —'

    return (
        f'<div class="ai-inline-strip">'
        f'<span class="ai-badge opinion {op_cls}">{op_icon} {op_label}</span>'
        f'<span class="ai-badge sentiment">📊 {st_label}</span>'
        f'<span class="ai-badge position">💰 {ps_label}</span>'
        f'</div>'
    )


# ==================== 工具函数 ====================
@st.cache_data(ttl=86400, show_spinner=False)
def _resolve_news_stock_name(code):
    """解析股票/ETF名称（模块级缓存）。本地CSV优先，yfinance兜底。"""
    # try local CSV
    cn = name_lookup._get_cn_name(code)
    if cn:
        return cn
    # try .SH→.SS / .SS→.SH variants
    for attempt in [code.replace(".SH", ".SS"), code.replace(".SS", ".SH")]:
        cn = name_lookup._get_cn_name(attempt)
        if cn:
            return cn
    # try name cache
    cache_df = name_lookup.load_name_cache()
    for attempt in [code, code.replace(".SH", ".SS"), code.replace(".SS", ".SH")]:
        m = cache_df[cache_df['code'] == attempt]
        if len(m) > 0 and m.iloc[0].get('name'):
            return str(m.iloc[0]['name'])
    # yfinance fallback (for ETFs etc.)
    try:
        import yfinance as yf
        info = yf.Ticker(code).info
        return info.get('longName') or info.get('shortName') or ''
    except Exception:
        return ''


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
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;padding:4px 12px;border-radius:10px;
                   background:rgba(0,240,255,0.06);border:1px solid rgba(0,240,255,0.12);color:#00F0FF">
        📅 {date_str}</span>
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;padding:4px 12px;border-radius:10px;
                   background:rgba(123,47,255,0.06);border:1px solid rgba(123,47,255,0.12);color:#9B6FFF">
        🕐 {time_str}</span>
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.78rem;padding:4px 12px;border-radius:10px;
                   background:rgba(0,240,255,0.04);border:1px solid rgba(0,240,255,0.08);color:#8888BB">
        {market_status}</span>
      <span style="font-family:'JetBrains Mono',monospace;font-size:0.75rem;color:#777">{scan_info}</span>
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
            ("nav_news", "📰 新闻", "◆ 新闻"),
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
                        <div style="font-family:monospace;font-size:0.78rem;color:#555588;margin-top:6px;text-align:right">
                          最近扫描 <span style="color:#7777AA">{scan_time}</span>
                        </div>""", unsafe_allow_html=True)
                except Exception:
                    pass
        except Exception:
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

    # ============ 选股页面 (v6 Unified Auto) ============
    if page == '◆ 选股':
        # 加载预计算选股结果
        fresh = load_latest_results()
        if "cached_scan_data" not in st.session_state:
            st.session_state["cached_scan_data"] = fresh
        scan_data = st.session_state["cached_scan_data"]
        if fresh and fresh.get("scan_time") != (scan_data or {}).get("scan_time"):
            st.session_state["cached_scan_data"] = fresh
            scan_data = fresh
            st.session_state.pop("auto_queued", None)  # reset so new candidates get auto-queued

        # 判断当前时段
        now = china_now()
        wd = now.weekday()
        h, m = now.hour, now.minute
        is_trading = (wd < 5 and ((9 <= h < 11) or (h == 11 and m <= 30) or (13 <= h < 15)))
        is_post_close = (wd < 5 and h >= 15)

        if scan_data is None:
            st.info("◆ 等待首次定时扫描… 结果将在 10:00 / 11:30 / 14:00 / 15:00 自动出现")
            st.caption("💡 也可以手动运行: `python auto_daily.py`")
        else:
            # ── 市场状态卡片 ──
            regime = scan_data.get("regime", {})
            market = scan_data.get("market", {})
            rec_mode = regime.get("recommended_mode", "strict")
            modes = scan_data.get("modes", {})

            # Build compact market status line
            index_parts = []
            for name, data in market.items():
                pct = data.get("pct", 0)
                color = "#00ff88" if pct >= 0 else "#ff5050"
                sign = "+" if pct >= 0 else ""
                index_parts.append(
                    f'<span style="color:#888;font-size:0.75rem;">{name}</span> '
                    f'<span style="color:{color};font-size:0.85rem;">{data["price"]:.0f} {sign}{pct:.2f}%</span>'
                )

            sentiment_label = regime.get("label", "—")
            st.markdown(f"""
            <div class="market-status-card">
              <div class="market-index-row">
                {" · ".join(index_parts) if index_parts else "—"}
              </div>
              <div class="market-sentiment">
                <span class="sentiment-tag">{sentiment_label}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ── 选股结果 ──
            candidates = modes.get(rec_mode, {}).get("candidates", [])
            st.markdown(f'<div class="section-label">◆ 选股结果 · {len(candidates)}只候选</div>',
                        unsafe_allow_html=True)

            if not candidates:
                st.info("◆ 当前无符合条件股票")
            else:
                # ── 从 ai_memory.json 加载预计算的分析结果（auto_daily.py 产出）──
                ai_memory = load_ai_memory()

                # 名称查找
                codes = [c["code"] for c in candidates]
                name_info = name_lookup.batch_lookup(codes, max_fetch=min(len(codes), 10))

                # ── 构建候选卡片 HTML ──
                for c in candidates:
                    code = c["code"]
                    signal_date = str(c.get("signal_date", ""))
                    info = name_info.get(code, {})
                    stock_name = info.get("name", "") or ""

                    # ── 优先从 ai_memory.json 读取预计算分析 ──
                    ai_strip = None
                    analysis_text = None  # 完整AI分析文本（用于下方expander）
                    if code in ai_memory:
                        # 取最近的非回填记录（按日期倒序）
                        records = sorted(ai_memory[code], key=lambda r: str(r.get("date", "")), reverse=True)
                        for rec in records:
                            sentiment = rec.get("sentiment", "")
                            if sentiment == "历史回填":
                                continue
                            opinion = rec.get("opinion", "")
                            position = rec.get("position", "")
                            ai_strip = _format_ai_badges(opinion, sentiment, position)
                            # 同时获取完整分析文本
                            txt = rec.get("analysis", "")
                            if txt and "历史回填记录" not in txt:
                                analysis_text = txt
                            break
                        if ai_strip is None:
                            ai_strip = '<span class="status-badge pending">📋 待AI分析</span>'

                    # ── 回退：检查 worker 实时分析结果 ──
                    if ai_strip is None:
                        has_result = bool(st.session_state.get(f"analysis_result_{code}"))
                        if has_result:
                            result_text = st.session_state.get(f"analysis_result_{code}", "")
                            sent_match = re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', result_text)
                            pos_match = re.search(r'仓位[建议]*[：:]\s*(.+?)(?:\n|$)', result_text)
                            op_match = re.search(r'最终结论[：:]\s*(.+?)(?:\n|$)', result_text)
                            sentiment = sent_match.group(1).strip() if sent_match else "—"
                            position = pos_match.group(1).strip() if pos_match else "—"
                            opinion = op_match.group(1).strip() if op_match else "—"
                            ai_strip = _format_ai_badges(opinion, sentiment, position)
                            analysis_text = result_text
                        else:
                            ai_strip = '<span class="status-badge pending">📋 待AI分析</span>'

                    card_html = f"""
                    <div class="candidate-card">
                      <div class="candidate-header">
                        <span class="candidate-code">◆ {code}</span>
                        <span class="candidate-name">{stock_name}</span>
                        <span class="candidate-mode">{rec_mode.upper()}</span>
                      </div>
                      <div class="candidate-metrics">
                        <div class="mini-metric">
                          <span class="mini-label">价格</span>
                          <span class="mini-value">¥{c['price']:.2f}</span>
                        </div>
                        <div class="mini-metric">
                          <span class="mini-label">回调</span>
                          <span class="mini-value">{c['pullback_pct']:.1f}%</span>
                        </div>
                        <div class="mini-metric">
                          <span class="mini-label">连板</span>
                          <span class="mini-value">{c['limit_days']}天</span>
                        </div>
                        <div class="mini-metric">
                          <span class="mini-label">实体比</span>
                          <span class="mini-value">{c.get('entity_ratio', 0):.0f}%</span>
                        </div>
                      </div>
                      <div class="candidate-ai">
                        {ai_strip}
                      </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)

                    # ── 完整 AI 分析 expander（紧跟在卡片下方）──
                    if analysis_text:
                        with st.expander(f"📖 {code} {stock_name} 完整AI分析", expanded=False):
                            st.markdown(analysis_text)


            # ── CSV 导出 ──
            if candidates:
                st.divider()
                df_export = pd.DataFrame(candidates)
                st.download_button(
                    label="◆ 导出 CSV",
                    data=df_export.to_csv(index=False, encoding="utf-8-sig"),
                    file_name=f"candidates_{china_now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
                current_scan_time = scan_data.get("scan_time", "")
                if st.session_state.get("_saved_scan_time") != current_scan_time:
                    for c in candidates:
                        c.setdefault('mode', rec_mode)
                    save_signals(candidates)
                    st.session_state["_saved_scan_time"] = current_scan_time

    # ============ 复盘页面 ============
    elif page == '◆ 复盘':

        # === 绩效总览 (v6 Unified) ===
        perf = compute_performance(mode_filter=None, days_window=30)

        if perf:
            ret_color = "#00FF88" if perf['total_return'] >= 0 else "#FF5050"
            pf_display = "无损" if perf['profit_factor'] >= 999 else f"{perf['profit_factor']:.2f}"
            win_label = f"+{perf['wins']}笔盈利" if perf['wins'] > 0 else ""

            # ── 绩效面板 v2: B不对称布局 ──
            hold_info = ' · '.join(f"{m.upper()}{d}日" for m, d in sorted(perf.get('mode_hold_days', {}).items())) if perf.get('mode_hold_days') else "持有"
            st.markdown(f"""
            <div class="section-label">◆ 绩效总览 (近30天 · {hold_info})</div>
            <div class="perf-panel-v2">
              <div class="perf-hero">
                <div class="perf-hero-label">累计收益</div>
                <div class="perf-hero-value" style="color:{ret_color}">{perf['total_return']:+.1f}%</div>
                {f'<div class="perf-hero-sub" style="color:#00ff88;background:rgba(0,255,136,0.08);border:1px solid rgba(0,255,136,0.15)">{win_label}</div>' if win_label else ''}
              </div>
              <div class="perf-side">
                <div class="perf-side-item">
                  <div class="perf-side-label">胜率</div>
                  <div class="perf-side-value" style="color:#00f0ff">{perf['win_rate']:.0%}</div>
                </div>
                <div class="perf-side-item">
                  <div class="perf-side-label">盈亏比</div>
                  <div class="perf-side-value" style="color:#ffd700">{pf_display}</div>
                </div>
                <div class="perf-side-item">
                  <div class="perf-side-label">最大回撤</div>
                  <div class="perf-side-value" style="color:#ff3366">-{perf['max_drawdown']:.1f}%</div>
                </div>
              </div>
            </div>
            <div class="perf-detail-row">
              {perf['wins']}胜/{perf['losses']}负{(' · ' + str(perf['neutral']) + '平') if perf.get('neutral', 0) > 0 else ''} · 均盈+{perf['avg_win']:.1f}% · 均亏-{perf['avg_loss']:.1f}% · 共{perf['total_trades']}笔
            </div>
            """, unsafe_allow_html=True)

            # ── SVG 双图收益曲线 ──
            if perf['cum_returns'] and len(perf['cum_returns']) >= 3:
                returns_list = perf['returns']
                cum_vals = perf['cum_returns']
                # 生成SVG
                svg_html = _build_svg_chart(cum_vals, returns_list, ret_color)
                st.markdown(svg_html, unsafe_allow_html=True)
                exit_info = perf.get('exit_reasons', {})
                if exit_info:
                    parts = [f"{k}{v}次" for k, v in sorted(exit_info.items())]
                    hold_str = ' · '.join(f"{m.upper()}{d}日" for m, d in sorted(perf.get('mode_hold_days', {}).items())) if perf.get('mode_hold_days') else "持有"
                    st.caption(f"◆ {hold_str} · {' · '.join(parts)}")
            else:
                st.caption(f"数据不足（{len(perf.get('cum_returns',[]))}笔），继续积累")
        else:
            st.markdown("""
            <div class="perf-panel" style="text-align:center;opacity:0.5">
              <div class="section-label">◆ 绩效总览</div>
              <p style="color:#555;font-size:0.78rem;">暂无信号数据，信号需要持有期+4天后验证</p>
            </div>
            """, unsafe_allow_html=True)

        st.divider()

        # === AI 记忆浏览器 ===
        memory = load_ai_memory()
        if memory:
            # 批量获取中文名
            all_codes_in_memory = list(memory.keys())
            stock_names = name_lookup.batch_lookup(all_codes_in_memory, max_fetch=len(all_codes_in_memory))
            # 展平所有记录并排序
            all_records = []
            for code, records in memory.items():
                for rec in records:
                    all_records.append({**rec, 'code': code})
            all_records.sort(key=lambda r: r.get('date', ''), reverse=True)

            # 筛选器
            verdict_filter = st.selectbox(
                "验证状态", ["全部", "✅ 准确预判", "❌ 判断失误", "🔶 错失机会", "🛡 正确规避", "📝 观望", "⏳ 待验证"],
                key="mem_filter", label_visibility="collapsed"
            )
            filtered = all_records
            if verdict_filter == "✅ 准确预判":
                filtered = [r for r in filtered if r.get('verdict') == 'correct']
            elif verdict_filter == "❌ 判断失误":
                filtered = [r for r in filtered if r.get('verdict') == 'wrong']
            elif verdict_filter == "🔶 错失机会":
                filtered = [r for r in filtered if r.get('verdict') == 'missed']
            elif verdict_filter == "🛡 正确规避":
                filtered = [r for r in filtered if r.get('verdict') == 'avoided']
            elif verdict_filter == "📝 观望":
                filtered = [r for r in filtered if r.get('verdict') in ('noted_up', 'noted_down')]
            elif verdict_filter == "⏳ 待验证":
                filtered = [r for r in filtered if r.get('verdict') is None]

            st.caption(f"◆ {len(filtered)} 条分析记录")

            # 渲染记忆卡片 (v4 D+宽松版)
            for rec in filtered[:30]:
                code = rec['code']
                verdict = rec.get('verdict')
                # 裁决类型 → CSS class + 标签
                verdict_map = {
                    'correct':    ('vc-correct',    'correct',    '✅ 准确预判'),
                    'wrong':      ('vc-wrong',      'wrong',      '❌ 判断失误'),
                    'missed':     ('vc-missed',     'missed',     '🔶 错失机会'),
                    'avoided':    ('vc-avoided',    'avoided',    '🛡 正确规避'),
                    'noted_up':   ('vc-noted_up',   'noted_up',   '📝 偏保守'),
                    'noted_down': ('vc-noted_down', 'noted_down', '📝 偏准确'),
                }
                vc_class, vb_class, vlabel = verdict_map.get(verdict, ('vc-pending', 'pending', '⏳ 待验证'))

                sdate = rec.get('date', '')
                sdate_display = f"{sdate[:4]}-{sdate[4:6]}-{sdate[6:]}" if len(sdate) >= 8 else sdate

                ret7_val = rec.get('return_7d')
                exit_reason = rec.get('exit_reason', '')
                exit_day = rec.get('exit_day', 0)

                analysis_full = rec.get('analysis', '')
                opinion = rec.get('opinion', '')
                sentiment = rec.get('sentiment', '')
                position = rec.get('position', '')

                # 回顾字段
                what_happened = rec.get('what_happened', '')
                why_wrong = rec.get('why_wrong', '')
                missed_signal = rec.get('missed_signal', '')
                lesson = rec.get('lesson', '')

                # 股票中文名
                name_info = stock_names.get(code, {})
                stock_name = name_info.get('name', '') if isinstance(name_info, dict) else str(name_info) if name_info else ''

                # 收益显示
                if ret7_val is not None:
                    ret_color_7d = "#00ff88" if ret7_val > 0 else ("#ff3366" if ret7_val < 0 else "#888")
                    ret_display = f'<span style="color:{ret_color_7d};font-weight:600">7d {ret7_val:+.1f}%</span>'
                    exit_display = f'<span style="color:#888">{exit_reason} Day{exit_day}</span>' if exit_reason else ''
                else:
                    ret_display = '<span style="color:#666">⏳ 待验证</span>'
                    exit_display = ''

                # AI结论颜色
                if '参与' in str(opinion):
                    op_color = '#00ff88'
                elif '放弃' in str(opinion):
                    op_color = '#ff3366'
                else:
                    op_color = '#ffb800'

                # 构建回顾行
                review_html = ''
                if verdict and verdict != 'pending':
                    review_parts = []
                    if lesson:
                        review_parts.append(f'<span class="mem-review-label lesson">💡 教训：</span><span style="color:#aaa">{lesson}</span>')
                    elif what_happened:
                        review_parts.append(f'<span style="color:#888">📖 {what_happened[:120]}{"..." if len(what_happened)>120 else ""}</span>')
                    if missed_signal:
                        review_parts.append(f'<span class="mem-review-label missed">🔍 遗漏信号：</span><span style="color:#aaa">{missed_signal[:100]}</span>')
                    if review_parts:
                        review_html = '<br>'.join(review_parts)

                st.markdown(f"""
                <div class="memory-card-v4 {vc_class}">
                  <div class="mem-header-row">
                    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
                      <span class="mem-code">◆ {code}</span>
                      <span class="mem-name">{stock_name}</span>
                      <span class="mem-date">{sdate_display}</span>
                      <span class="mem-verdict-badge {vb_class}">{vlabel}</span>
                      <span style="font-family:'JetBrains Mono',monospace;color:#666;font-size:0.75rem">{rec.get('mode', '').upper()}</span>
                    </div>
                    <span class="mem-opinion" style="color:{op_color}">◆ {opinion}</span>
                  </div>
                  <div class="mem-metrics-row">
                    <span>入场 ¥{rec.get('entry_price', 0):.2f}</span>
                    <span>回调 {rec.get('pullback_pct', 0):.1f}%</span>
                    <span>连板 {rec.get('limit_days', 0)}天</span>
                    {ret_display}
                    {exit_display}
                  </div>
                  {f'<div class="mem-review-row">{review_html}</div>' if review_html else ''}
                </div>
                """, unsafe_allow_html=True)

                # 可展开完整分析
                with st.expander(f"📖 {code} 完整分析", expanded=False):
                    if analysis_full:
                        st.markdown(analysis_full)
                    # 展示结构化回顾字段
                    if what_happened or why_wrong or missed_signal or lesson:
                        st.divider()
                        st.caption("◆ 7日回顾分析")
                        if what_happened:
                            st.caption(f"📖 走势回顾：{what_happened}")
                        if why_wrong:
                            st.caption(f"🔍 判断复盘：{why_wrong}")
                        if missed_signal:
                            st.caption(f"⚠️ 遗漏信号：{missed_signal}")
                        if lesson:
                            st.caption(f"💡 教训：{lesson}")
                    col_del, _ = st.columns([1, 3])
                    with col_del:
                        if st.button(f"🗑 删除记录", key=f"delete_mem_{code}_{rec['date']}", type="secondary"):
                            memory = load_ai_memory()
                            if code in memory:
                                memory[code] = [r for r in memory[code] if r.get("date") != rec["date"]]
                                if not memory[code]:
                                    del memory[code]
                                save_ai_memory(memory)
                            st.toast(f"已删除 {code} 记录", icon="🗑")
                            st.rerun()
        else:
            st.markdown("""
            <div style="padding:30px 0;text-align:center;font-family:'JetBrains Mono',monospace;font-size:0.8rem;color:#444466">
              ◆ AI 记忆为空<br>
              <span style="font-size:0.78rem;color:#333355">在选股页对候选股票使用 AI 分析后，记录会出现在这里</span>
            </div>
            """, unsafe_allow_html=True)

    elif page == '◆ 新闻':
        st.header("◆ 今日市场要闻")

        news_data = market_news.load_market_news()

        if news_data:
            date_str = news_data.get("date", "")
            date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}" if len(date_str) >= 8 else date_str

            # 市场情绪总览
            sentiment = news_data.get("sentiment_impact", "中性")
            sentiment_color = {"偏多": "#00ff88", "偏空": "#ff3366", "中性": "#ffb800"}.get(sentiment, "#888")

            st.markdown(f"""
            <div class="section-label">◆ 新闻总览 · {date_display}</div>
            <div class="news-summary-card">
              <div class="news-summary-text">{news_data.get('market_summary', '')}</div>
              <div class="news-sentiment-badge" style="background:{sentiment_color}15;border-color:{sentiment_color}40;color:{sentiment_color}">
                ◆ 今日情绪：{sentiment}
              </div>
            </div>
            """, unsafe_allow_html=True)

            news_list = news_data.get("news", [])
            st.caption(f"◆ {len(news_list)} 条重点新闻")

            for i, item in enumerate(news_list):
                title = item.get("title", "")
                source = item.get("source", "")
                time_str = item.get("time", "")
                url = item.get("url", "")
                ai_summary = item.get("ai_summary", "")
                impact_analysis = item.get("impact_analysis", "")
                sectors = item.get("affected_sectors", [])
                stocks = item.get("affected_stocks", [])
                importance = item.get("importance", 5)
                import_display = "◆" * min(10, max(1, importance // 1))

                # Source badge color
                source_colors = {
                    "东方财富": "#e63946",
                    "财联社": "#457b9d",
                    "Yahoo Finance": "#7b2fff",
                }
                src_color = source_colors.get(source, "#666")

                # Sector pills
                sector_pills = " ".join([
                    f'<span class="news-sector-pill">{s}</span>'
                    for s in sectors[:5]
                ])

                # Stock codes with Chinese names
                stock_items = []
                for s in stocks[:5]:
                    name = _resolve_news_stock_name(s)
                    display = f"{s} {name}" if name else s
                    stock_items.append(f'<span class="news-stock-code">{display}</span>')
                stock_codes_display = " ".join(stock_items)

                # Render card
                st.markdown(f"""
                <div class="news-card">
                  <div class="news-card-header">
                    <div class="news-card-title-row">
                      <span class="news-importance">{import_display}</span>
                      <span class="news-title-text">{title}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                      <span class="news-source-badge" style="background:{src_color}20;border:1px solid {src_color}40;color:{src_color}">{source}</span>
                      <span class="news-time">{time_str}</span>
                      {f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="news-read-link">📄 阅读原文</a>' if url else ''}
                    </div>
                  </div>
                  <div class="news-card-meta">
                    {f'<div class="news-meta-row">{sector_pills}</div>' if sectors else ''}
                    {f'<div class="news-meta-row">{stock_codes_display}</div>' if stocks else ''}
                  </div>
                </div>
                """, unsafe_allow_html=True)

                # Expandable AI analysis
                with st.expander(f"📖 AI 分析 · {title[:30]}...", expanded=False):
                    st.markdown(f"**一句话总结：** {ai_summary}")
                    st.divider()
                    st.markdown(f"**影响分析：** {impact_analysis}")
                    if sectors:
                        st.caption(f"影响板块：{'、'.join(sectors)}")
                    if stocks:
                        stock_names = []
                        for sc in stocks:
                            nm = _resolve_news_stock_name(sc)
                            stock_names.append(f"{sc} {nm}" if nm else sc)
                        st.caption(f"关注个股：{'、'.join(stock_names)}")
                    if url:
                        st.markdown(f"[阅读原文 →]({url})")

        else:
            st.markdown("""
            <div style="padding:30px 0;text-align:center;font-family:'JetBrains Mono',monospace;font-size:0.8rem;color:#444466">
              ◆ 暂无今日新闻数据<br>
              <span style="font-size:0.78rem;color:#333355">新闻将在每日自动扫描时生成</span>
            </div>
            """, unsafe_allow_html=True)

    elif page == '◆ 介绍':
        st.header("◆ NEON VAULT · 战术终端")
        st.markdown("""
        <div class="intro-section">
          <h3>A股连板回调策略 v7</h3>
          <p>识别连续涨停后缩量回调的股票，在回调企稳时介入，博取反弹收益。</p>
          <p>基于「量价形时」四维分析框架，由 DeepSeek 提供深度 AI 诊断。</p>

          <h4>◆ 三模式市场自适应</h4>
          <p>三大指数（上证/深证/创业板）5日趋势自动分5档，匹配最优策略参数：</p>
          <table style="width:100%; border-collapse:collapse; margin:12px 0;">
            <tr style="background:rgba(0,240,255,0.08);">
              <th style="padding:8px 12px; text-align:left;">模式</th>
              <th style="padding:8px 12px; text-align:center;">连板</th>
              <th style="padding:8px 12px; text-align:left;">适用市场</th>
              <th style="padding:8px 12px; text-align:left;">核心差异</th>
            </tr>
            <tr>
              <td style="padding:8px 12px;">🐻 BEAR</td>
              <td style="padding:8px 12px; text-align:center;">≥3</td>
              <td style="padding:8px 12px;">冰点 / 低迷</td>
              <td style="padding:8px 12px;">浅回调≤11% + 极度缩量 + 快进快出7天</td>
            </tr>
            <tr style="background:rgba(0,240,255,0.04);">
              <td style="padding:8px 12px;">🎯 STRICT</td>
              <td style="padding:8px 12px; text-align:center;">≥3</td>
              <td style="padding:8px 12px;">震荡 / 启动</td>
              <td style="padding:8px 12px;">高质量低频率，严标准，WR 72%</td>
            </tr>
            <tr>
              <td style="padding:8px 12px;">🏆 LOOSE</td>
              <td style="padding:8px 12px; text-align:center;">≥3</td>
              <td style="padding:8px 12px;">发酵 / 高潮</td>
              <td style="padding:8px 12px;">最泛化最稳健，WR 93%，OOS &gt; IS 🏆</td>
            </tr>
          </table>
          <p style="font-size:0.85em; opacity:0.7;">※ BULL模式已在v7移除（IS夏普19.56→OOS 1.22，严重过拟合）</p>

          <h4>◆ 核心功能</h4>
          <ul>
            <li><strong>市场自适应</strong> — 三大指数5日趋势自动分5档，熊市/震荡/牛市切换最优参数</li>
            <li><strong>全自动 AI 分析</strong> — 所有候选股票自动深度诊断（量价形时四维框架），无需手动触发</li>
            <li><strong>AI 记忆闭环</strong> — 7天自动验证收益，裁决矩阵（正确/错误/遗漏/避开），历史上下文注入</li>
            <li><strong>📰 每日新闻</strong> — 东方财富 + 财联社 + Yahoo 三源汇聚，AI 精选 Top 10 + 影响分析</li>
            <li><strong>历史回填 v7</strong> — 2025年5月至今全量历史数据回填，去重 + 收益验证 + 结构化复盘</li>
            <li><strong>全自动日频扫描</strong> — 每交易日4次定时扫描 + git自动推送 + Streamlit Cloud自动部署</li>
          </ul>

          <h4>◆ 数据来源</h4>
          <p>股价：yfinance · ~5,200只A股 · 本地CSV缓存</p>
          <p>新闻：东方财富(AKShare) · 财联社(CLS API) · Yahoo Finance</p>

          <h4>◆ 扫描时间</h4>
          <p>每个交易日 10:00 / 11:30 / 14:00 / 15:00</p>

          <h4>◆ 参数优化</h4>
          <p>三阶段漏斗优化（~200k组合）→ 多周期交叉验证 → Bootstrap统计检验 → Walk-forward分析</p>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
