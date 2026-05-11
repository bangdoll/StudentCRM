#!/bin/bash
# StudentCRM 一鍵安裝 (在新 Mac 上執行一次即可)
echo "🍎 正在安裝 StudentCRM 所需套件..."
pip3 install fastapi uvicorn jinja2 pyyaml markdown pyobjc
echo "🔓 正在解除 macOS 安全限制..."
xattr -cr "$(dirname "$0")/StudentCRM.app"
echo "✅ 安裝完成！現在可以雙擊 StudentCRM.app 啟動了"
open "$(dirname "$0")/StudentCRM.app"
