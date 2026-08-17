#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
LABEL="com.cursor-usage.menubar"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG="$HOME/Library/Logs/cursor-usage-menubar.log"
ERR="$HOME/Library/Logs/cursor-usage-menubar.err.log"

ensure_venv() {
  if [[ ! -x "$PY" ]]; then
    python3 -m venv "$VENV"
  fi
  "$PY" -m pip install -q -r "$ROOT/requirements.txt"
}

cmd="${1:-run}"

case "$cmd" in
  run)
    ensure_venv
    exec "$PY" "$ROOT/run.py"
    ;;
  install)
    ensure_venv
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${PY}</string>
    <string>${ROOT}/run.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR}</string>
</dict>
</plist>
EOF
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "Installed $PLIST"
    ;;
  uninstall)
    if [[ -f "$PLIST" ]]; then
      launchctl unload "$PLIST" 2>/dev/null || true
      rm -f "$PLIST"
    fi
    pkill -f "$ROOT/run.py" 2>/dev/null || true
    echo "Uninstalled $LABEL"
    ;;
  status)
    echo "plist: $PLIST"
    if [[ -f "$PLIST" ]]; then echo "plist_exists: yes"; else echo "plist_exists: no"; fi
    if launchctl list "$LABEL" >/dev/null 2>&1; then echo "loaded: yes"; else echo "loaded: no"; fi
    if pgrep -f "$ROOT/run.py" >/dev/null 2>&1; then echo "running: yes"; else echo "running: no"; fi
    ;;
  *)
    echo "usage: $0 {run|install|uninstall|status}"
    exit 1
    ;;
esac
