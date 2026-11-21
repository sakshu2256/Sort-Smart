#!/bin/bash
# StopSortSmart.command — Double-click to stop the SortSmart server
cd "$(dirname "$0")"
echo "🛑 Stopping SortSmart..."

if [ -f .server.pid ]; then
    PID=$(cat .server.pid)
    kill "$PID" 2>/dev/null && echo "✓ Server (PID $PID) stopped." || echo "Server was not running."
    rm -f .server.pid
else
    # Fallback: kill anything on port 8000
    OLD_PID=$(lsof -ti:8000 2>/dev/null || true)
    if [ -n "$OLD_PID" ]; then
        kill "$OLD_PID" 2>/dev/null && echo "✓ Server stopped." || true
    else
        echo "No SortSmart server found running."
    fi
fi

echo ""
echo "Press Enter to close this window."
read
