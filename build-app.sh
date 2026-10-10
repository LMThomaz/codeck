#!/usr/bin/env bash
# Gera o "PR Pilot.app" (macOS 13+) e instala em /Applications (ou ~/Applications).
#   ./build-app.sh            compila, instala e abre
#   ./build-app.sh --no-install   só gera em dist/
# Precisa das Command Line Tools (xcode-select --install) — o mesmo pacote traz o swiftc e o python3.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/dist/PR Pilot.app"
VERSION="1.$(git -C "$DIR" rev-list --count HEAD 2>/dev/null || echo 0)"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
echo "Compilando…"
swiftc -O -swift-version 5 -target "$(uname -m)-apple-macos13.0" \
  -framework Cocoa -framework WebKit -framework ServiceManagement \
  "$DIR/app/PRPilot.swift" -o "$APP/Contents/MacOS/PR Pilot"
sed -e "s/__VERSION__/$VERSION/" -e "s/__BUILD__/${VERSION#1.}/" "$DIR/app/Info.plist" > "$APP/Contents/Info.plist"
cp "$DIR/server.py" "$DIR/index.html" "$APP/Contents/Resources/"
cp "$DIR/app/AppIcon.icns" "$APP/Contents/Resources/"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1   # assinatura local (ad-hoc), suficiente para rodar na própria máquina
echo "Gerado: $APP (v$VERSION)"

[ "${1:-}" = "--no-install" ] && exit 0

# O app passa a ser quem roda o piloto: o serviço antigo do install.sh sairia em duplicidade.
if launchctl print "gui/$(id -u)/dev.prpilot" >/dev/null 2>&1; then
  echo "Removendo o serviço em segundo plano antigo (o app assume)…"
  "$DIR/install.sh" uninstall >/dev/null
fi

DEST="/Applications"; [ -w "$DEST" ] || DEST="$HOME/Applications"
mkdir -p "$DEST"
osascript -e 'tell application "PR Pilot" to quit' >/dev/null 2>&1 || true
pkill -f "PR Pilot.app/Contents/Resources/server.py" 2>/dev/null || true
sleep 1
rm -rf "$DEST/PR Pilot.app"
ditto "$APP" "$DEST/PR Pilot.app"
echo "Instalado em $DEST/PR Pilot.app"
open "$DEST/PR Pilot.app"
