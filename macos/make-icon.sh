#!/usr/bin/env bash
# Gera app/AppIcon.icns a partir de app/icon.svg (precisa do Google Chrome só para rasterizar o SVG).
set -euo pipefail
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP="$(mktemp -d)"
cat > "$TMP/i.html" <<H
<html><body style="margin:0;background:transparent">$(cat icon.svg)</body></html>
H
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 \
  --window-size=1024,1024 --screenshot="$TMP/icon.png" "file://$TMP/i.html" >/dev/null 2>&1
mkdir -p "$TMP/AppIcon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$TMP/icon.png" --out "$TMP/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$TMP/icon.png" --out "$TMP/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$TMP/AppIcon.iconset" -o AppIcon.icns
cp "$TMP/icon.png" icon.png
rm -rf "$TMP"
echo "AppIcon.icns gerado"
