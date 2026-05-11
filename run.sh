#!/bin/bash
# OpenClaw Student CRM Standalone App Launcher

# Navigate to the App directory dynamically
cd "$(dirname "$0")"

# Start the FastAPI server
echo "🚀 正在啟動 Student CRM 獨立門戶..."
echo "📍 請在瀏覽器開啟：http://localhost:8888"

python3 main.py
