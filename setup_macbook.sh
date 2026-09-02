#!/bin/bash
# ==========================================
# StudentCRM 跨平台自動建置與依賴配置腳本
# 目標：供 MacBook Air 無痛移植使用
# ==========================================

echo "🍏 開始配置 StudentCRM 運行環境..."

# 1. 檢查 Python 版本 (核心依賴)
if command -v python3 &>/dev/null; then
    echo "✅ Python3 已安裝: $(python3 --version)"
else
    echo "❌ 尚未安裝 Python3，請透過 Homebrew 安裝: brew install python3"
    exit 1
fi

# 2. 檢查 Node.js 狀態 (符合教練指示之「Node 版本要求」)
# StudentCRM 後端主要為 Python，但若需聯動周邊 OpenClaw/Paperclip SPA，則強烈建議 Node 18+
if command -v node &>/dev/null; then
    echo "✅ Node.js 已安裝: $(node --version)"
else
    echo "⚠️ 尚未安裝 Node.js。若需運行 OpenClaw 完整生態系，建議安裝 v18 以上版本。"
fi

# 3. 安裝 Python 依賴包 (Requirements)
echo "📦 正在安裝相依套件..."
pip3 install fastapi uvicorn jinja2 pyyaml markdown pyobjc python-dotenv

# 4. macOS 隱私與安全限制解綁
APP_DIR="$(dirname "$0")/StudentCRM.app"
if [ -d "$APP_DIR" ]; then
    echo "🔓 正在解除 macOS 對 StudentCRM.app 的 Quarantine 隔離鎖..."
    xattr -cr "$APP_DIR"
fi

# 5. 環境變數 (.env) 結構建立
ENV_FILE="$(dirname "$0")/.env.example"
echo "📝 正在建立環境變數範本 ($ENV_FILE)..."
cat <<EOT > "$ENV_FILE"
# ==========================================
# StudentCRM 環境變數設定檔 (.env)
# ==========================================
# 若未填寫，系統將自動向上尋找包含 OpenClaw 的目錄作為根目錄。
# 您亦可手動指定 OpenClaw 筆記資料夾的絕對路徑：
# OPEN_CLAW_BASE_DIR=/Users/your_username/Projects/00.AI-Notes_Local

# 附加的設定檔路徑 (未來擴充用)
# STUDENT_DATA_PATH=OpenClaw/Data/students.json
EOT

echo "✅ 依賴建置與相容性檢查完成！"
echo "👉 您現在可以直接執行 ./run.sh 或雙擊 StudentCRM.app 來啟動系統了。"
