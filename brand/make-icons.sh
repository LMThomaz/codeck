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
# .ico no formato clássico: BMP 32 bits (com alfa) até 128 px e PNG só no de 256 — é o que o Explorer, a barra de
# tarefas e o System.Drawing.Icon leem sem surpresa (PNG em tamanho pequeno às vezes sai em branco ou é ignorado).
python3 - "$TMP/icon.png" "$ROOT/windows/PRPilot/app.ico" <<'PY'
import os, struct, subprocess, sys, tempfile, zlib
src, dst = sys.argv[1], sys.argv[2]

def read_png(path):
    data = open(path, "rb").read()
    pos, w, h, idat, ctype = 8, 0, 0, b"", 0
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", chunk[:10])
            assert depth == 8 and ctype in (2, 6), "PNG precisa ser RGB/RGBA 8 bits"
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + n
    bpp = 4 if ctype == 6 else 3
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p_ = a + b - c; pa, pb, pc = abs(p_ - a), abs(p_ - b), abs(p_ - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line if bpp == 4 else bytearray(v for i in range(w) for v in (*line[i*3:i*3+3], 255)))
        prev = line
    return w, h, rows

def bmp_entry(w, h, rows):
    head = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = b"".join(bytes(v for i in range(w) for v in (r[i*4+2], r[i*4+1], r[i*4], r[i*4+3])) for r in reversed(rows))
    mask_row = ((w + 31) // 32) * 4
    return head + pixels + b"\0" * (mask_row * h)

sizes, entries = [16, 20, 24, 32, 40, 48, 64, 128, 256], []
with tempfile.TemporaryDirectory() as d:
    for s in sizes:
        out = os.path.join(d, f"{s}.png")
        subprocess.run(["sips", "-z", str(s), str(s), src, "--out", out], check=True, capture_output=True)
        entries.append(open(out, "rb").read() if s == 256 else bmp_entry(*read_png(out)))
off, dirs = 6 + 16 * len(sizes), b""
for s, data in zip(sizes, entries):
    dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), off)
    off += len(data)
open(dst, "wb").write(struct.pack("<HHH", 0, 1, len(sizes)) + dirs + b"".join(entries))
PY
rm -rf "$TMP"
echo "✓ macos/AppIcon.icns, windows/PRPilot/app.ico, brand/icon.png"
