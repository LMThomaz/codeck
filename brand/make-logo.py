#!/usr/bin/env python3
"""Gera brand/logo.svg (marca com gradiente, sem fundo) e brand/icon.svg (ícone do app).

A marca: um grafo do git que forma o "P" de PR Pilot — a branch principal é a haste; uma branch sai dela, ganha um
commit e volta num merge (em verde) no topo, desenhando a barriga do P. Tudo sai como <path> PREENCHIDO de polígonos (traços e círculos viram contorno aqui): o
ThomSoft Setup desenha o logo com um renderizador que não aceita filtros e é instável com stroke, e quando falha
mostra o logo de demonstração (foi o que aconteceu com o primeiro logo).

    python3 brand/make-logo.py && bash brand/make-icons.sh
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
W = 68  # espessura dos ramos


def bezier(p0, p1, p2, p3, n=48):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def thick(pts, w=W):
    """Contorno de uma linha grossa (pontas retas — ficam cobertas pelos nós)."""
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        x0, y0 = pts[max(i - 1, 0)]
        x1, y1 = pts[min(i + 1, len(pts) - 1)]
        L = math.hypot(x1 - x0, y1 - y0) or 1
        nx, ny = -(y1 - y0) / L * w / 2, (x1 - x0) / L * w / 2
        left.append((x + nx, y + ny))
        right.append((x - nx, y - ny))
    return left + right[::-1]


def circle(cx, cy, r, n=72):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


# desenho livre; o encaixe no quadrado de 512 vem depois
S, J, R, T = (150, 466), (150, 306), (382, 188), (150, 70)   # 1º commit, saída da branch, commit da branch, merge
shapes = [
    thick([S, T]),                                                   # branch principal (a haste do P)
    thick(bezier(J, (240, 306), (382, 282), R)),                     # a branch saindo…
    thick(bezier(R, (382, 96), (240, 70), T)),                      # …e voltando no merge (a barriga do P)
    circle(*S, 58), circle(*R, 58),                                  # commits
]
merge_ring, merge_dot = circle(*T, 64), circle(*T, 25)


def fit(polys, margin):
    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    k = (512 - 2 * margin) / max(max(xs) - min(xs), max(ys) - min(ys))
    ox = (512 - k * (max(xs) - min(xs))) / 2 - k * min(xs)
    oy = (512 - k * (max(ys) - min(ys))) / 2 - k * min(ys)
    return lambda p: [(ox + k * x, oy + k * y) for x, y in p]


def d(poly):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in poly) + " Z"


def svg(size, margin, mark_fill, background):
    f = fit(shapes + [merge_ring], margin)
    if size != 512:  # ícone: a marca ocupa o miolo do quadrado arredondado
        s = size / 512
        g = f
        f = lambda p: [(x * s, y * s) for x, y in g(p)]  # noqa: E731
    body = "\n".join(f'<path d="{d(f(p))}" fill="{mark_fill}"/>' for p in shapes)
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" fill="none" xmlns="http://www.w3.org/2000/svg">
{background}{body}
<path d="{d(f(merge_ring))}" fill="#22C38E"/>
<path d="{d(f(merge_dot))}" fill="#FFFFFF"/>
<defs>
<linearGradient id="g" x1="0" y1="{size}" x2="{size}" y2="0" gradientUnits="userSpaceOnUse">
<stop stop-color="#6D4AF0"/>
<stop offset="1" stop-color="#2F8CF0"/>
</linearGradient>
<linearGradient id="bg" x1="100" y1="924" x2="924" y2="100" gradientUnits="userSpaceOnUse">
<stop stop-color="#4B2FC9"/>
<stop offset="1" stop-color="#2F86EE"/>
</linearGradient>
</defs>
</svg>
'''


open(os.path.join(HERE, "logo.svg"), "w").write(svg(512, 20, "url(#g)", ""))
open(os.path.join(HERE, "icon.svg"), "w").write(
    svg(1024, 116, "#FFFFFF", '<rect x="100" y="100" width="824" height="824" rx="185" fill="url(#bg)"/>\n'))
print("✓ brand/logo.svg, brand/icon.svg")
