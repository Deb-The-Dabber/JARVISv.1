#!/usr/bin/env bash
# Start Jarvis web server for phone access (Tailscale or local Wi‑Fi).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/venv/bin/activate"
fi

if command -v tailscale >/dev/null 2>&1; then
  TS_IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  if [[ -n "$TS_IP" ]]; then
    echo "Tailscale IP: $TS_IP"
    echo "Phone URL:    http://${TS_IP}:${JARVIS_PORT:-8002}"
  fi
fi

export JARVIS_PORT=8002

echo "Starting server (Ctrl+C to stop)..."
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -dims python "$ROOT/server.py"
else
  exec python "$ROOT/server.py"
fi
