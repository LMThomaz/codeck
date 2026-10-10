#!/usr/bin/env python3
"""Gera brand/logo.svg (marca com gradiente, sem fundo) e brand/icon.svg (ícone do app).

A marca do Commitdeck: um deck de cartões empilhados — cada cartão é um provedor (GitHub, Azure DevOps, os que vierem)
— e, no da frente, um grafo do git que desenha o "C": a branch sai de um commit, contorna e volta num merge (verde).
Tudo sai como <path> PREENCHIDO de polígonos (traços e círculos viram contorno aqui): o ThomSoft Setup desenha o logo
com um renderizador que não aceita filtros e é instável com stroke, e quando falha mostra o logo de demonstração.

    python3 brand/make-logo.py && bash brand/make-icons.sh
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def circle(cx, cy, r, n=72):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rrect(x, y, w, h, r, n=12):
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rotate(poly, deg, cx, cy):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in poly]


def arc_band(cx, cy, r, w, a0, a1, n=96):
    """Faixa grossa em arco (de a0 a a1 graus, sentido horário na tela)."""
    outer = [(cx + (r + w / 2) * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
              cy + (r + w / 2) * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    inner = [(cx + (r - w / 2) * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
              cy + (r - w / 2) * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    return outer + inner[::-1]


def polar(cx, cy, r, deg):
    return cx + r * math.cos(math.radians(deg)), cy + r * math.sin(math.radians(deg))


# desenho em 512; cartões giram em torno da base, como um leque curto
CARD = (92, 112, 300, 356, 58)
PIV = (242, 470)
back2 = rotate(rrect(*CARD), 16, *PIV)
back1 = rotate(rrect(*CARD), 8, *PIV)
front = rrect(*CARD)
# o "C": arco aberto à direita, de 40° a 320° (contornando pela esquerda)
GC, GR, GW = (240, 290), 92, 34
c_band = arc_band(*GC, GR, GW, 45, 315)
start, end = polar(*GC, GR, 45), polar(*GC, GR, 315)
mid = polar(*GC, GR, 180)
nodes = [circle(*start, 30), circle(*mid, 26)]
merge_ring, merge_dot = circle(*end, 34), circle(*end, 13)


def fit(polys, margin, size):
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    k = (size - 2 * margin) / max(max(xs) - min(xs), max(ys) - min(ys))
    ox = (size - k * (max(xs) - min(xs))) / 2 - k * min(xs)
    oy = (size - k * (max(ys) - min(ys))) / 2 - k * min(ys)
    return lambda p: [(ox + k * x, oy + k * y) for x, y in p]


def d(poly):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in poly) + " Z"


def svg(size, margin, icon):
    f = fit([back2, back1, front], margin, size)
    p = lambda poly, fill, extra="": f'<path d="{d(f(poly))}" fill="{fill}"{extra}/>'  # noqa: E731
    if icon:   # sobre o quadrado em gradiente: cartões brancos em camadas, grafo na cor da marca
        cards = [p(back2, "#FFFFFF", ' fill-opacity="0.32"'), p(back1, "#FFFFFF", ' fill-opacity="0.58"'), p(front, "#FFFFFF")]
        ink = "url(#ink)"
        bg = f'<rect x="{size * 0.0977:.0f}" y="{size * 0.0977:.0f}" width="{size * 0.8047:.0f}" height="{size * 0.8047:.0f}" rx="{size * 0.1807:.0f}" fill="url(#bg)"/>\n'
    else:      # sem fundo (instalador, site): cores sólidas, sem opacidade
        cards = [p(back2, "#B9C6FB"), p(back1, "#7F95F6"), p(front, "url(#g)")]
        ink = "#FFFFFF"
        bg = ""
    graph = [p(c_band, ink)] + [p(n, ink) for n in nodes] + [p(merge_ring, "#22C38E"), p(merge_dot, "#FFFFFF")]
    body = "\n".join(cards + graph)
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" fill="none" xmlns="http://www.w3.org/2000/svg">
{bg}{body}
<defs>
<linearGradient id="g" x1="0" y1="{size}" x2="{size}" y2="0" gradientUnits="userSpaceOnUse">
<stop stop-color="#6D4AF0"/>
<stop offset="1" stop-color="#2F8CF0"/>
</linearGradient>
<linearGradient id="ink" x1="0" y1="{size}" x2="{size}" y2="0" gradientUnits="userSpaceOnUse">
<stop stop-color="#5A36E6"/>
<stop offset="1" stop-color="#2F7FE8"/>
</linearGradient>
<linearGradient id="bg" x1="{size * 0.1:.0f}" y1="{size * 0.9:.0f}" x2="{size * 0.9:.0f}" y2="{size * 0.1:.0f}" gradientUnits="userSpaceOnUse">
<stop stop-color="#4B2FC9"/>
<stop offset="1" stop-color="#2F86EE"/>
</linearGradient>
</defs>
</svg>
'''


open(os.path.join(HERE, "logo.svg"), "w").write(svg(512, 14, False))
open(os.path.join(HERE, "icon.svg"), "w").write(svg(1024, 158, True))
print("✓ brand/logo.svg, brand/icon.svg")
