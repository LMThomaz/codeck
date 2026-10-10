#!/usr/bin/env bash
# Gera os ícones das duas plataformas a partir de brand/icon.svg (precisa do Google Chrome só para rasterizar):
#   macos/AppIcon.icns · windows/PRPilot/app.ico · brand/icon.png
# brand/logo.svg (só a marca, sem fundo) vai direto para o instalador do Windows: só <path> + gradiente, sem
# filtros — o ThomSoft Setup cai no logo de demonstração quando não consegue desenhar o SVG.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP="$(mktemp -d)"
printf '<html><body style="margin:0;background:transparent">%s</body></html>' "$(cat "$ROOT/brand/icon.svg")" > "$TMP/i.html"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 \
  --window-size=1024,1024 --screenshot="$TMP/icon.png" "file://$TMP/i.html" >/dev/null 2>&1
cp "$TMP/icon.png" "$ROOT/brand/icon.png"
mkdir -p "$TMP/AppIcon.iconset"
for s in 16 32 128 256 512; do
  sips -z $s $s "$TMP/icon.png" --out "$TMP/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$TMP/icon.png" --out "$TMP/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$TMP/AppIcon.iconset" -o "$ROOT/macos/AppIcon.icns"
# .ico com PNGs embutidos (Windows Vista+)
python3 - "$TMP/icon.png" "$ROOT/windows/PRPilot/app.ico" <<'PY'
import struct, subprocess, sys, tempfile, os
src, dst = sys.argv[1], sys.argv[2]
sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = []
with tempfile.TemporaryDirectory() as d:
    for s in sizes:
        out = os.path.join(d, f"{s}.png")
        subprocess.run(["sips", "-z", str(s), str(s), src, "--out", out], check=True, capture_output=True)
        imgs.append(open(out, "rb").read())
off, dirs = 6 + 16 * len(sizes), b""
for s, data in zip(sizes, imgs):
    dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), off)
    off += len(data)
open(dst, "wb").write(struct.pack("<HHH", 0, 1, len(sizes)) + dirs + b"".join(imgs))
PY
rm -rf "$TMP"
echo "✓ macos/AppIcon.icns, windows/PRPilot/app.ico, brand/icon.png"
