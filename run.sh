#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  SortSmart — Run Script
#  Double-click SortSmart.command to launch this.
#  Shows live server logs in this Terminal window.
#  Press Ctrl+C (or close Terminal) to stop.
# ══════════════════════════════════════════════════════════════════

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Colours ───────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; N='\033[0m'

clear
echo ""
echo -e "${C}╔══════════════════════════════════════════╗${N}"
echo -e "${C}║      🌿  SortSmart AI Launcher  🌿        ║${N}"
echo -e "${C}╚══════════════════════════════════════════╝${N}"
echo ""

# ── 1. Kill anything already on port 8000 ────────────────────────
OLD=$(lsof -ti:8000 2>/dev/null || true)
if [ -n "$OLD" ]; then
    echo -e "${Y}► Stopping old server on port 8000...${N}"
    kill $OLD 2>/dev/null || true
    sleep 1
fi

# ── 2. Start Ollama if not running ───────────────────────────────
echo -e "${Y}► Checking Ollama...${N}"
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e "  Starting Ollama service..."
    /opt/homebrew/bin/brew services start ollama 2>/dev/null || \
    /opt/homebrew/bin/ollama serve &>/tmp/ollama.log &
    echo -n "  Waiting for Ollama"
    for i in $(seq 1 20); do
        sleep 1
        if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
            echo " ✓"; break
        fi
        echo -n "."
    done
else
    echo -e "  ${G}✓ Ollama already running${N}"
fi

# ── 3. Check LLaVA model ─────────────────────────────────────────
echo -e "${Y}► Checking LLaVA model...${N}"
if /opt/homebrew/bin/ollama list 2>/dev/null | grep -q "llava"; then
    echo -e "  ${G}✓ LLaVA ready${N}"
else
    echo -e "  Downloading LLaVA (4.7 GB) — only needed once..."
    /opt/homebrew/bin/ollama pull llava
fi

# ── 4. Python venv ───────────────────────────────────────────────
echo -e "${Y}► Checking Python environment...${N}"
if [ ! -d ".venv" ]; then
    echo -e "  Creating virtual environment..."
    python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
echo -e "  ${G}✓ Python ready${N}"

# ── 5. Get local IP ──────────────────────────────────────────────
IP=$(ipconfig getifaddr en0 2>/dev/null || \
     ipconfig getifaddr en1 2>/dev/null || \
     echo "YOUR_IP")

# ── 6. Launch server ─────────────────────────────────────────────
echo ""
echo -e "${G}╔══════════════════════════════════════════╗${N}"
echo -e "${G}║        🚀  SortSmart is LIVE!  🚀         ║${N}"
echo -e "${G}╠══════════════════════════════════════════╣${N}"
echo -e "${G}║  💻  http://localhost:8000               ║${N}"
echo -e "${G}║  📱  http://${IP}:8000             ║${N}"
echo -e "${G}╠══════════════════════════════════════════╣${N}"
echo -e "${G}║  Close this window to STOP the server    ║${N}"
echo -e "${G}╚══════════════════════════════════════════╝${N}"
echo ""

# Open browser
sleep 1
open http://localhost:8000 2>/dev/null || true

echo -e "${C}── Live logs (close window to stop) ─────────────${N}"
echo ""

# ── Run server IN FOREGROUND (visible in this Terminal) ───────────
exec .venv/bin/python web_app.py --host 0.0.0.0 --port 8000
