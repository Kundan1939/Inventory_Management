#!/usr/bin/env bash
# IT Asset Manager — One-line Auto-Registration Script (macOS / Linux)
# Usage:
#   curl -sSL http://<SERVER_IP>:5000/agent.sh | bash -s -- --key <ASSET_API_KEY> [options]

set -e

KEY=""
SERVER="http://127.0.0.1:5000"
EXTRA_ARGS=()

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --key) KEY="$2"; shift ;;
        --server) SERVER="$2"; shift ;;
        *) EXTRA_ARGS+=("$1") ;;
    esac
    shift
done

if [ -z "$KEY" ]; then
    echo "❌ Error: --key <ASSET_API_KEY> is required."
    echo "Usage: curl -sSL $SERVER/agent.sh | bash -s -- --key YOUR_API_KEY"
    exit 1
fi

PYTHON_BIN=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Error: Python 3 is required to run the auto-discovery agent."
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "💡 On macOS, run: xcode-select --install (or install python3 via brew)"
    else
        echo "💡 On Ubuntu/Linux, run: sudo apt update && sudo apt install -y python3"
    fi
    exit 1
fi

TMP_SCRIPT=$(mktemp /tmp/asset_agent_XXXXXX.py)
trap 'rm -f "$TMP_SCRIPT"' EXIT

echo "📥 Fetching agent from $SERVER..."
curl -sSL "$SERVER/agent.py" -o "$TMP_SCRIPT"

echo "⚡ Running hardware discovery agent..."
"$PYTHON_BIN" "$TMP_SCRIPT" --server "$SERVER" --key "$KEY" "${EXTRA_ARGS[@]}"
