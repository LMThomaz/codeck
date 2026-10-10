#!/usr/bin/env bash
# Gera o "PR Pilot.app" (universal: Apple Silicon + Intel, macOS 13+).
#   scripts/build-macos.sh               gera em dist/ e instala em /Applications (ou ~/Applications)
#   scripts/build-macos.sh --no-install  só gera em dist/
# Precisa das Command Line Tools (xcode-select --install): trazem o swiftc e o python3 que o app usa.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/PR Pilot.app"
line="$(sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+)\+([0-9]+)$/\1 \2/p' "$ROOT/VERSION")"
[ -n "$line" ] || { echo "VERSION precisa ser x.y.z+N" >&2; exit 1; }
read -r VERSION BUILD <<< "$line"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/backend"
echo "Compilando $VERSION ($BUILD)…"
tmp="$(mktemp -d)"
for arch in arm64 x86_64; do
  swiftc -O -swift-version 5 -target "$arch-apple-macos13.0" \
    -framework Cocoa -framework WebKit -framework ServiceManagement -framework UserNotifications \
    "$ROOT/macos/PRPilot.swift" -o "$tmp/PRPilot-$arch"
done
lipo -create "$tmp/PRPilot-arm64" "$tmp/PRPilot-x86_64" -output "$APP/Contents/MacOS/PR Pilot"
rm -rf "$tmp"
sed -e "s/__VERSION__/$VERSION/" -e "s/__BUILD__/$BUILD/" "$ROOT/macos/Info.plist" > "$APP/Contents/Info.plist"
cp "$ROOT/backend/server.py" "$ROOT/backend/index.html" "$APP/Contents/Resources/backend/"
cp "$ROOT/macos/AppIcon.icns" "$APP/Contents/Resources/"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1   # assinatura ad-hoc (o app não é notarizado)
codesign --verify --deep --strict "$APP"
echo "Gerado: $APP"

[ "${1:-}" = "--no-install" ] && exit 0

# versões antigas rodavam como serviço do launchd; o app assume
for label in dev.prpilot com.thomaz.prpilot; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/$label.plist"
done
DEST="/Applications"; [ -w "$DEST" ] || DEST="$HOME/Applications"
mkdir -p "$DEST"
osascript -e 'tell application "PR Pilot" to quit' >/dev/null 2>&1 || true
sleep 2
rm -rf "$DEST/PR Pilot.app"
ditto "$APP" "$DEST/PR Pilot.app"
echo "Instalado em $DEST/PR Pilot.app"
open "$DEST/PR Pilot.app"
