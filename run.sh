#!/bin/bash
cd "$(dirname "$0")"
echo "🚀 启动 A股连板回调策略..."
streamlit run streamlit_app.py
