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
import threading
import re

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


    /* === TACTICAL TERMINAL ENHANCEMENTS (v6 Unified) === */

    .market-status-card {
      background: linear-gradient(135deg, rgba(0,255,136,0.03) 0%, rgba(0,15,10,0.6) 100%);
      border: 1px solid rgba(0,255,136,0.1);
      border-radius: 6px;
      padding: 12px 16px;
      margin-bottom: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .market-index-row {
      font-family: 'JetBrains Mono', monospace;
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
    }
    .market-sentiment { flex-shrink: 0; }
    .sentiment-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.5rem;
      color: #00ff88;
      background: rgba(0,255,136,0.06);
      border: 1px solid rgba(0,255,136,0.2);
      border-radius: 3px;
      padding: 3px 10px;
    }

    .section-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.65rem;
      color: #00ff88;
      letter-spacing: 0.06em;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid rgba(0,255,136,0.08);
    }

    .status-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.45rem;
      padding: 2px 8px;
      border-radius: 3px;
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

    .analysis-progress-bar {
      background: rgba(0,255,136,0.02);
      border: 1px solid rgba(0,255,136,0.08);
      border-radius: 6px;
      padding: 12px 16px;
      margin: 10px 0 16px 0;
    }
    .progress-header {
      display: flex;
      justify-content: space-between;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.5rem;
      color: #00ff88;
      margin-bottom: 6px;
    }
    .progress-track {
      height: 3px;
      background: rgba(0,255,136,0.06);
      border-radius: 2px;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #00ff88, #00e5ff);
      border-radius: 2px;
      transition: width 0.5s ease;
      animation: pulse-glow 2s ease-in-out infinite;
    }
    .progress-footer {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.42rem;
      color: #555;
      margin-top: 4px;
    }

    .perf-panel {
      background: rgba(0,15,10,0.4);
      border: 1px solid rgba(0,255,136,0.06);
      border-radius: 6px;
      padding: 14px 18px;
      margin-bottom: 12px;
    }
    .perf-grid {
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
      margin: 10px 0;
    }
    .perf-card { min-width: 80px; }
    .perf-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.42rem;
      color: #555;
      margin-bottom: 2px;
    }
    .perf-value {
      font-family: 'JetBrains Mono', monospace;
      font-size: 1.1rem;
      font-weight: bold;
    }
    .perf-detail {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.42rem;
      color: #444;
      margin-top: 4px;
      padding-top: 8px;
      border-top: 1px solid rgba(0,255,136,0.04);
    }

    .intro-section {
      font-family: 'JetBrains Mono', monospace;
      color: #aaa;
      font-size: 0.55rem;
      line-height: 1.7;
    }
    .intro-section h3 {
      color: #00ff88;
      font-family: 'Orbitron', sans-serif;
      font-size: 0.9rem;
      letter-spacing: 0.06em;
      margin-bottom: 8px;
    }
    .intro-section h4 {
      color: #00e5ff;
      font-size: 0.6rem;
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
            entry_price = round(float(row['entry_price']), 2)

            try:
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


@st.cache_data(ttl=300, show_spinner=False)
def check_return_v5(code, signal_date, entry_price, hold_days, take_profit, stop_loss):
    """yfinance版 simulate_hold_return()。

    拉取OHLCV数据，从signal_date后逐日迭代，应用止损/止盈/到期退出
    逻辑和交易成本，与回测引擎完全一致。

    Returns: {'return_pct': float, 'exit_day': int, 'exit_reason': str}
             exit_reason: '止损' / '止盈' / '到期'
             None: 数据不足或出错
    """
    try:
        start_dt = datetime.strptime(str(signal_date), '%Y%m%d')
        fetch_start = start_dt - pd.Timedelta(days=3)
        fetch_end = start_dt + pd.Timedelta(days=hold_days + 5)

        ticker = yf.Ticker(code)
        df = ticker.history(start=fetch_start.strftime('%Y-%m-%d'),
                           end=fetch_end.strftime('%Y-%m-%d'))
        if df is None or len(df) < 2:
            return None

        # 展平MultiIndex列
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns={'Open': 'open', 'High': 'high',
                                'Low': 'low', 'Close': 'close',
                                'Volume': 'volume'})
        df_sorted = df.sort_index()

        # 找到signal_date之后的第一个bar（入场bar）
        mask = df_sorted.index >= pd.Timestamp(start_dt)
        if not mask.any():
            return None
        entry_idx = mask.argmax()
        # 如果完整持有期数据不足，用现有数据做截断模拟
        if entry_idx + 1 >= len(df_sorted):
            return None  # 连1个交易日的向前数据都没有
        effective_hold = min(hold_days, len(df_sorted) - 1 - entry_idx)

        exit_idx_limit = min(entry_idx + hold_days, len(df_sorted) - 1)
        for i in range(entry_idx + 1, exit_idx_limit + 1):
            row = df_sorted.iloc[i]
            high, low, open_price = row['high'], row['low'], row['open']
            if entry_price <= 0:
                continue

            # 开盘检查
            open_return = open_price / entry_price - 1
            net_open = screener.apply_trading_costs(open_return, is_sell=True)
            if net_open <= stop_loss:
                return {'return_pct': round(net_open * 100, 2),
                        'exit_day': i - entry_idx, 'exit_reason': '止损'}
            if net_open >= take_profit:
                return {'return_pct': round(net_open * 100, 2),
                        'exit_day': i - entry_idx, 'exit_reason': '止盈'}

            # 盘中距离优先检查（与回测完全一致）
            stop_level = entry_price * (1 + stop_loss)
            profit_level = entry_price * (1 + take_profit)
            dist_to_stop = open_price - stop_level
            dist_to_profit = profit_level - open_price

            if dist_to_stop <= dist_to_profit:
                if low / entry_price - 1 <= stop_loss:
                    net = screener.apply_trading_costs(stop_loss, is_sell=True)
                    return {'return_pct': round(net * 100, 2),
                            'exit_day': i - entry_idx, 'exit_reason': '止损'}
                if high / entry_price - 1 >= take_profit:
                    net = screener.apply_trading_costs(take_profit, is_sell=True)
                    return {'return_pct': round(net * 100, 2),
                            'exit_day': i - entry_idx, 'exit_reason': '止盈'}
            else:
                if high / entry_price - 1 >= take_profit:
                    net = screener.apply_trading_costs(take_profit, is_sell=True)
                    return {'return_pct': round(net * 100, 2),
                            'exit_day': i - entry_idx, 'exit_reason': '止盈'}
                if low / entry_price - 1 <= stop_loss:
                    net = screener.apply_trading_costs(stop_loss, is_sell=True)
                    return {'return_pct': round(net * 100, 2),
                            'exit_day': i - entry_idx, 'exit_reason': '止损'}

        # 到期退出（或截断退出：数据不足以跑满持有期）
        final_price = df_sorted.iloc[exit_idx_limit]['close']
        final_return = final_price / entry_price - 1 if entry_price > 0 else 0
        net_final = screener.apply_trading_costs(final_return, is_sell=True)
        is_truncated = effective_hold < hold_days
        return {'return_pct': round(net_final * 100, 2),
                'exit_day': effective_hold,
                'exit_reason': '到期(截断)' if is_truncated else '到期'}
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
                # 使用 check_return_v5 验证（loose 模式默认参数）
                loose_params = screener.SCREEN_MODES['loose']
                ret3 = check_return_v5(code, sdate, entry_price, 3,
                                       loose_params['take_profit'], loose_params['stop_loss'])
                ret5 = check_return_v5(code, sdate, entry_price, 5,
                                       loose_params['take_profit'], loose_params['stop_loss'])
                ret7 = check_return_v5(code, sdate, entry_price, 7,
                                       loose_params['take_profit'], loose_params['stop_loss'])
                rec["return_3d"] = round(ret3['return_pct'], 2) if ret3 is not None else None
                rec["return_5d"] = round(ret5['return_pct'], 2) if ret5 is not None else None
                rec["return_7d"] = round(ret7['return_pct'], 2) if ret7 is not None else None
                rec["verified"] = True
                if ret3 is not None:
                    rec["verdict"] = "correct" if ret3['return_pct'] > 0 else "wrong"
                changed = True
            except Exception:
                pass
    # 回溯修复：对 sentiment 为空的旧记录重新提取
    for code, records in memory.items():
        for rec in records:
            if rec.get("sentiment"):
                continue  # 已正确提取（sentiment非空）
            try:
                analysis_text = rec.get("analysis", "")
                if not analysis_text:
                    continue
                import re as _re2
                m = _re2.search(r'仓位建议[：:]\s*(.+?)（(.+?)）', analysis_text)
                if m:
                    rec["position"] = m.group(1).strip().strip('*')
                    rec["sentiment"] = m.group(2).strip().strip('*')
                if not rec.get("sentiment"):
                    sm = _re2.search(r'情绪档位[：:]\s*(.+?)(?:\n|$|\*\*)', analysis_text)
                    if sm:
                        rec["sentiment"] = sm.group(1).strip().strip('*')
                if not rec.get("opinion"):
                    om = _re2.search(r'最终结论[：:]\s*(.+?)(?:\n|$|\*\*)', analysis_text)
                    if om:
                        rec["opinion"] = om.group(1).strip().strip('*')
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
    - 使用模式专属的止盈/止损/持仓参数（从 SCREEN_MODES）
    - 使用 check_return_v5() 模拟真实持仓退出
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

        # 获取模式专属的出场参数
        mode_params = screener.SCREEN_MODES.get(
            mode_filter,
            screener.SCREEN_MODES['loose']  # 默认用 loose 参数
        )
        hold_days = mode_params.get('hold_days', 7)
        take_profit = mode_params.get('take_profit', 0.05)
        stop_loss = mode_params.get('stop_loss', -0.10)

        # 计算每条已验证信号的收益
        returns = []
        wins = 0
        losses = 0
        for _, row in df.iterrows():
            sdate = str(row['signal_date'])
            # 信号需要足够的向前数据：hold_days个交易日 ≈ hold_days+4个自然日
            if today_int - int(sdate) < hold_days + 4:
                continue  # 持有期尚未结束
            entry_price = row['entry_price']
            if entry_price <= 0:
                continue
            result = check_return_v5(
                row['code'], sdate, entry_price,
                hold_days, take_profit, stop_loss
            )
            if result is not None:
                returns.append({
                    'date': sdate,
                    'code': row['code'],
                    'mode': row.get('mode', ''),
                    'return_pct': result['return_pct'],
                    'exit_day': result['exit_day'],
                    'exit_reason': result['exit_reason'],
                })
                if result['return_pct'] > 0:
                    wins += 1
                elif result['return_pct'] < 0:
                    losses += 1
                # ret == 0 不计入胜负

        if not returns:
            return None

        total_trades = wins + losses
        win_rate = wins / total_trades if total_trades > 0 else 0
        avg_win = sum(r['return_pct'] for r in returns if r['return_pct'] > 0) / wins if wins > 0 else 0
        avg_loss = abs(sum(r['return_pct'] for r in returns if r['return_pct'] < 0) / losses) if losses > 0 else 0
        profit_factor = (avg_win * wins) / (avg_loss * losses) if (avg_loss * losses) > 0 else float('inf')
        if profit_factor == float('inf'):
            profit_factor = 999.99

        # 按日期排序（关键！确保权益曲线按时间顺序）
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

        # 构建带日期索引的DataFrame（图表用）
        chart_df = pd.DataFrame(
            {'累计收益%': cum_returns},
            index=pd.Index(dates_for_chart, name='日期')
        )

        # 退出方式统计
        exit_reasons = {}
        for r in returns:
            reason = r.get('exit_reason', '未知')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

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
            'chart_df': chart_df,
            'returns': returns,
            'exit_reasons': exit_reasons,
            'hold_days': hold_days,
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
        return data
    except Exception:
        return None


# ==================== 异步分析队列 ====================
def _analysis_worker():
    """后台线程：逐条消费分析队列，调用 DeepSeek API"""
    while True:
        if not st.session_state.analysis_queue:
            break
        code = st.session_state.analysis_queue.pop(0)
        st.session_state.analysis_current = code
        try:
            # 获取股票数据
            stock_df = None
            csv_path = os.path.join(screener.DATA_DIR, f"{code}.csv")
            if os.path.exists(csv_path):
                stock_df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            else:
                try:
                    stock_df = yf.Ticker(code).history(period="3mo")
                except Exception:
                    stock_df = None

            market_ctx = screener.get_market_context()
            memory_context = get_stock_memory_context(code)
            result = fast_ai_analysis(code, stock_df, market_ctx, memory_context)
            st.session_state.analysis_results[code] = result

            # 自动存档
            if result:
                try:
                    today_str = china_now().strftime('%Y%m%d')
                    save_ai_analysis_record(
                        code=code,
                        date_str=today_str,
                        mode="",
                        entry_price=0,
                        pullback_pct=0,
                        limit_days=0,
                        analysis_text=result,
                    )
                except Exception:
                    pass
        except Exception as e:
            st.session_state.analysis_errors[code] = str(e)
            st.session_state.analysis_results[code] = None
    st.session_state.analysis_running = False
    st.session_state.analysis_current = None


def start_analysis_queue(codes):
    """将 codes 加入队列并启动后台线程"""
    for code in codes:
        if code not in st.session_state.analysis_queue:
            st.session_state.analysis_queue.append(code)
    # 清除旧结果
    for code in codes:
        st.session_state.analysis_results.pop(code, None)
        st.session_state.analysis_errors.pop(code, None)
        st.session_state.pop(f"analysis_result_{code}", None)

    # 只在没有运行中的worker时才启动新线程
    if not st.session_state.analysis_running:
        st.session_state.analysis_running = True
        thread = threading.Thread(target=_analysis_worker, daemon=True)
        thread.start()


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

    # v6: 市场状态检测
    try:
        regime = screener.detect_market_regime()
        is_bear = regime['regime'] == 'bear'
        regime_color = "#FFA500" if is_bear else "#00FF88"
        regime_icon = "🐻" if is_bear else "🐂"
        regime_bg = "rgba(255,165,0,0.06)" if is_bear else "rgba(0,255,136,0.04)"
        regime_border = "rgba(255,165,0,0.2)" if is_bear else "rgba(0,255,136,0.12)"
        st.markdown(f"""
        <div style="display:flex;align-items:center;gap:10px;padding:8px 16px;margin:8px 0;border-radius:8px;
                    background:{regime_bg};border:1px solid {regime_border};
                    font-family:'JetBrains Mono',monospace;font-size:0.55rem;color:#8888AA">
          <span style="font-size:1rem">{regime_icon}</span>
          <span style="color:{regime_color}">{regime.get("label", "—")}</span>
          <span>| 5日趋势 <span style="color:{regime_color}">{regime['avg_trend']:+.1f}%</span></span>
          <span>| 推荐模式 <span style="color:{regime_color}">{regime['recommended_mode'].upper()}</span></span>
          {f'<span style="color:#FFA500">| ⚠️ 熊市环境 — 已启用浅回调+极度缩量策略</span>' if is_bear else ''}
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        pass
    if "analysis_queue" not in st.session_state:
        st.session_state.analysis_queue = []
    if "analysis_results" not in st.session_state:
        st.session_state.analysis_results = {}
    if "analysis_running" not in st.session_state:
        st.session_state.analysis_running = False
    if "analysis_current" not in st.session_state:
        st.session_state.analysis_current = None
    if "analysis_errors" not in st.session_state:
        st.session_state.analysis_errors = {}

    # === 全局分析进度条（所有页面可见） ===
    if st.session_state.analysis_running:
        current = st.session_state.analysis_current or "..."
        queue_len = len(st.session_state.analysis_queue)
        # Count completed results
        done_count = len([k for k in st.session_state.analysis_results if st.session_state.analysis_results[k] is not None])
        dots = "·" * ((done_count % 4) + 1)
        st.markdown(f"""
        <div style="padding:6px 0;font-family:'JetBrains Mono',monospace;font-size:0.5rem;color:#00F0FF;
                    border-bottom:1px solid rgba(0,240,255,0.08);margin-bottom:8px;display:flex;align-items:center;gap:8px">
          <span>◆ 分析中: {current} · 队列剩余 {queue_len} 只</span>
          <span style="color:#555577">{dots}</span>
        </div>
        """, unsafe_allow_html=True)

        # JS 自动轮询
        st.markdown("""
        <script>
        (function() {
            if (window._analysisPollTimer) return;
            window._analysisPollTimer = setInterval(() => {
                window.parent.postMessage({type: 'streamlit:rerun'}, '*');
            }, 2500);
        })();
        </script>
        """, unsafe_allow_html=True)

    # 清除轮询（分析完成时）
    if not st.session_state.analysis_running and not st.session_state.analysis_queue:
        st.markdown("""
        <script>
        if (window._analysisPollTimer) {
            clearInterval(window._analysisPollTimer);
            window._analysisPollTimer = null;
        }
        </script>
        """, unsafe_allow_html=True)

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
                    f'<span style="color:#777;font-size:0.5rem;">{name}</span> '
                    f'<span style="color:{color};font-size:0.55rem;">{data["price"]:.0f} {sign}{pct:.2f}%</span>'
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
                # 首次加载：自动入队 AI 分析
                if "auto_queued" not in st.session_state:
                    codes = [c["code"] for c in candidates]
                    start_analysis_queue(codes)
                    st.session_state["auto_queued"] = True

                # 转移已完成的分析结果
                for code in list(st.session_state.analysis_results.keys()):
                    result = st.session_state.analysis_results[code]
                    if result:
                        st.session_state[f"analysis_result_{code}"] = result
                    del st.session_state.analysis_results[code]
                for code in list(st.session_state.analysis_errors.keys()):
                    st.session_state[f"analysis_result_{code}"] = f"❌ 分析失败: {st.session_state.analysis_errors[code]}"
                    del st.session_state.analysis_errors[code]

                # 名称查找
                codes = [c["code"] for c in candidates]
                name_info = name_lookup.batch_lookup(codes, max_fetch=5)

                for c in candidates:
                    code = c["code"]
                    info = name_info.get(code, {})
                    stock_name = info.get("name", "") or ""

                    # 分析状态
                    in_queue = code in st.session_state.analysis_queue
                    is_current = st.session_state.analysis_current == code
                    has_result = bool(st.session_state.get(f"analysis_result_{code}"))

                    if is_current:
                        status_html = '<span class="status-badge analyzing">🔄 分析中</span>'
                    elif in_queue:
                        status_html = '<span class="status-badge queued">⏳ 排队</span>'
                    elif has_result:
                        result_text = st.session_state.get(f"analysis_result_{code}", "")
                        # Quick parse for sentiment/position
                        sent_match = re.search(r'情绪档位[：:]\s*(.+?)(?:\n|$)', result_text)
                        pos_match = re.search(r'仓位[建议]*[：:]\s*(.+?)(?:\n|$)', result_text)
                        sentiment = sent_match.group(1).strip() if sent_match else "—"
                        position = pos_match.group(1).strip() if pos_match else "—"
                        status_html = f'<span class="status-badge done">🎯 {sentiment} · 💰 {position}</span>'
                    else:
                        status_html = '<span class="status-badge pending">⏳ 排队</span>'

                    with st.container():
                        col1, col2, col3, col4, col5, col6 = st.columns([1.6, 1.1, 1.0, 0.8, 0.8, 1.9])
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
                            st.markdown(status_html, unsafe_allow_html=True)

                        # 展开完整 AI 分析
                        if has_result:
                            result_text = st.session_state[f"analysis_result_{code}"]
                            with st.expander(f"◆ {code} AI分析", expanded=False):
                                st.markdown(result_text)

                        st.divider()

            # ── AI 分析进度条 ──
            if st.session_state.analysis_running:
                queue_len = len(st.session_state.analysis_queue)
                total = len(candidates) if candidates else 1
                done = max(0, total - queue_len)
                pct = min(100, done / total * 100) if total > 0 else 0
                current = st.session_state.analysis_current or "—"
                est_min = max(0, int(queue_len * 0.25))
                st.markdown(f"""
                <div class="analysis-progress-bar">
                  <div class="progress-header">
                    <span>🤖 AI分析进度</span>
                    <span>{done} / {total}</span>
                  </div>
                  <div class="progress-track">
                    <div class="progress-fill" style="width:{pct:.0f}%"></div>
                  </div>
                  <div class="progress-footer">当前: {current} · 预计剩余 {est_min}分钟</div>
                </div>
                """, unsafe_allow_html=True)

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
        # 自动验证 AI 记忆
        auto_verify_memory()

        # === 绩效总览 (v6 Unified) ===
        perf = compute_performance(mode_filter=None, days_window=30)

        if perf:
            ret_color = "#00FF88" if perf['total_return'] >= 0 else "#FF5050"
            pf_display = "无损" if perf['profit_factor'] >= 999 else f"{perf['profit_factor']:.2f}"
            st.markdown(f"""
            <div class="perf-panel">
              <div class="section-label">◆ 绩效总览 (近30天)</div>
              <div class="perf-grid">
                <div class="perf-card">
                  <div class="perf-label">累计收益</div>
                  <div class="perf-value" style="color:{ret_color}">{perf['total_return']:+.1f}%</div>
                </div>
                <div class="perf-card">
                  <div class="perf-label">胜率</div>
                  <div class="perf-value" style="color:#D0D0E8">{perf['win_rate']:.0%}</div>
                </div>
                <div class="perf-card">
                  <div class="perf-label">盈亏比</div>
                  <div class="perf-value" style="color:#FFD700">{pf_display}</div>
                </div>
                <div class="perf-card">
                  <div class="perf-label">最大回撤</div>
                  <div class="perf-value" style="color:#FF6B6B">-{perf['max_drawdown']:.1f}%</div>
                </div>
              </div>
              <div class="perf-detail">
                {perf['wins']}胜/{perf['losses']}负 · 均盈+{perf['avg_win']:.1f}% · 均亏-{perf['avg_loss']:.1f}% · 共{perf['total_trades']}笔
              </div>
            </div>
            """, unsafe_allow_html=True)

            # 收益曲线
            if perf['cum_returns'] and len(perf['cum_returns']) >= 3:
                chart_df = perf.get('chart_df',
                    pd.DataFrame({'累计收益%': perf['cum_returns']})
                )
                st.line_chart(chart_df, height=140, use_container_width=True)
                exit_info = perf.get('exit_reasons', {})
                if exit_info:
                    parts = [f"{k}{v}次" for k, v in sorted(exit_info.items())]
                    st.caption(f"持有{perf.get('hold_days','?')}天 · {' · '.join(parts)}")
            else:
                st.caption(f"数据不足（{len(perf.get('cum_returns',[]))}笔），继续积累")
        else:
            st.markdown("""
            <div class="perf-panel" style="text-align:center;opacity:0.5">
              <div class="section-label">◆ 绩效总览</div>
              <p style="color:#555;font-size:0.55rem;">暂无信号数据，信号需要持有期+4天后验证</p>
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
                sentiment = rec.get('sentiment', '')
                position = rec.get('position', '')
                opinion = rec.get('opinion', '')

                # 构建结论摘要
                summary_parts = []
                if opinion:
                    if "参与" in opinion:
                        opinion_color = "#00FF88"
                    elif "放弃" in opinion:
                        opinion_color = "#FF5050"
                    else:
                        opinion_color = "#D0D0E8"
                    summary_parts.append(f'<span style="color:{opinion_color}">{opinion}</span>')
                if sentiment:
                    summary_parts.append(f'<span style="color:#9B6FFF">{sentiment}</span>')
                if position:
                    summary_parts.append(f'<span style="color:#8888AA">{position}</span>')

                summary_html = ' <span style="color:#555577">·</span> '.join(summary_parts) if summary_parts else '<span style="color:#444466">无摘要</span>'

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
                  <div style="margin-top:4px;font-family:'JetBrains Mono',monospace;font-size:0.5rem;line-height:1.5">
                    <span style="color:#00F0FF">◆</span> {summary_html}
                  </div>
                </div>
                """, unsafe_allow_html=True)

                # 可展开完整分析 + 重新分析 + 删除按钮
                with st.expander(f"📖 完整分析", expanded=False):
                    st.markdown(analysis_full)
                    col_re, col_del = st.columns([3, 1])
                    with col_re:
                        if st.button(f"🔄 重新分析(带入记忆)", key=f"reanalyze_{code}_{rec['date']}"):
                            start_analysis_queue([code])
                            st.toast(f"◆ {code} 已加入分析队列", icon="◆")
                            st.rerun()
                    with col_del:
                        if st.button(f"🗑 删除", key=f"delete_mem_{code}_{rec['date']}", type="secondary"):
                            memory = load_ai_memory()
                            if code in memory:
                                memory[code] = [r for r in memory[code] if r.get("date") != rec["date"]]
                                if not memory[code]:
                                    del memory[code]
                                save_ai_memory(memory)
                            st.toast(f"◆ {code} 记忆已删除", icon="🗑")
                            st.rerun()
        else:
            st.markdown("""
            <div style="padding:30px 0;text-align:center;font-family:'JetBrains Mono',monospace;font-size:0.65rem;color:#444466">
              ◆ AI 记忆为空<br>
              <span style="font-size:0.5rem;color:#333355">在选股页对候选股票使用 AI 分析后，记录会出现在这里</span>
            </div>
            """, unsafe_allow_html=True)

    elif page == '◆ 介绍':
        st.header("◆ NEON VAULT · 战术终端")
        st.markdown("""
        <div class="intro-section">
          <h3>A股连板回调策略 v6</h3>
          <p>识别连续涨停后缩量回调的股票，在回调企稳时介入，博取反弹收益。</p>
          <p>基于「量价形时」四维分析框架，由 DeepSeek 提供深度 AI 诊断。</p>

          <h4>◆ 核心特色</h4>
          <ul>
            <li><strong>市场自适应</strong> — 三大指数5日趋势自动检测，熊市/震荡/牛市切换最优参数</li>
            <li><strong>全自动 AI 分析</strong> — 所有候选股票自动深度诊断，无需手动触发</li>
            <li><strong>AI 记忆闭环</strong> — 每笔分析存档，3天后自动验证收益，历史上下文注入未来分析</li>
            <li><strong>三阶段参数优化</strong> — ~200k组合 × 多周期交叉验证 × Bootstrap统计检验</li>
            <li><strong>全自动日频扫描</strong> — 每交易日4次定时扫描 + git自动推送</li>
          </ul>

          <h4>◆ 数据来源</h4>
          <p>yfinance (Yahoo Finance) · ~5,200只A股 · 本地CSV缓存</p>

          <h4>◆ 扫描时间</h4>
          <p>每个交易日 10:00 / 11:30 / 14:00 / 15:00</p>
        </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
