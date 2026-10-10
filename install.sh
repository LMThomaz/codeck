#!/usr/bin/env bash
# Instala o PR Pilot como serviço do usuário no macOS (launchd): sobe no login e reinicia se cair.
#   ./install.sh            instala/reinicia
#   ./install.sh uninstall  remove o serviço (os dados ficam)
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="dev.prpilot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3)"
DOMAIN="gui/$(id -u)"

# versões antigas usavam outro label
for old in "$HOME"/Library/LaunchAgents/com.*.prpilot.plist; do
  [ -e "$old" ] || continue
  launchctl bootout "$DOMAIN/$(basename "$old" .plist)" 2>/dev/null || true
  rm -f "$old"
done
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true

if [ "${1:-}" = "uninstall" ]; then
  rm -f "$PLIST"
  echo "Serviço removido. Dados continuam em ~/Library/Application Support/PR Pilot."
  exit 0
fi

mkdir -p "$HOME/Library/Application Support/PR Pilot"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/server.py</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Application Support/PR Pilot/pr-pilot.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Application Support/PR Pilot/pr-pilot.log</string>
</dict></plist>
PL
launchctl bootstrap "$DOMAIN" "$PLIST"
PORT="$("$PY" -c "import json,sys;print(json.load(open(sys.argv[1])).get('port',47821))" "$HOME/Library/Application Support/PR Pilot/config.json" 2>/dev/null || echo 47821)"
echo "Rodando em http://127.0.0.1:$PORT  (log: ~/Library/Application Support/PR Pilot/pr-pilot.log)"
echo "Remover: ./install.sh uninstall"
