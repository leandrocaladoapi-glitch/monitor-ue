#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dataviz.py — Gráficos SVG inline para o Monitor Legislativo de IA.

Sem dependências externas (apenas stdlib) e sem JavaScript: cada gráfico é um
`<svg>` gerado no build a partir do dataset. Os gráficos usam as variáveis de
cor do site (style.css), funcionam no tema escuro e trazem `<title>` para
acessibilidade.

Funções públicas:
    bar_chart(items)         barras verticais (séries temporais curtas)
    bar_chart_h(items)       barras horizontais (rankings, composição)
    line_chart(labels, series) séries de linhas (cobertura, volume)
    stacked_bar(items)       barra única empilhada (composição de um total)
    heatmap(dias)            calendário de intensidade (mudanças por dia)
"""
import html

PALETA = {
    "accent": "var(--accent)",
    "azul": "var(--accent-2)",
    "amarelo": "var(--warn)",
    "vermelho": "var(--danger)",
    "roxo": "#a371f7",
    "cinza": "var(--muted)",
}
CORES = list(PALETA.values())


def esc(t):
    return html.escape(str(t), quote=True)


def _fmt(v):
    if isinstance(v, float):
        return f"{v:,.1f}".replace(",", " ") if v % 1 else f"{int(v)}"
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return str(v)


# --------------------------------------------------------------- barras verticais
def bar_chart(items, width=720, height=190, color="accent", unidade="",
              mostrar_valores=True, rotulo_max=14):
    """items: [(rótulo, valor)] em ordem cronológica."""
    items = [(str(r), float(v or 0)) for r, v in items][-14:]
    if not items:
        return ""
    vmax = max([v for _r, v in items] + [1])
    pad_e, pad_d, pad_b, pad_t = 38, 8, 34, 22
    n = len(items)
    passo = (width - pad_e - pad_d) / n
    largura = passo * 0.62
    partes = []
    # linhas de grade + eixo Y
    for i in range(3):
        y = pad_t + (height - pad_t - pad_b) * i / 2
        val = vmax * (1 - i / 2)
        partes.append(f'<line x1="{pad_e}" y1="{y:.1f}" x2="{width - pad_d}" y2="{y:.1f}" '
                      f'stroke="var(--border)" stroke-dasharray="3 3"/>')
        partes.append(f'<text x="{pad_e - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="10" '
                      f'fill="var(--muted)">{_fmt(val)}</text>')
    for i, (rot, val) in enumerate(items):
        h = (val / vmax) * (height - pad_t - pad_b)
        x = pad_e + i * passo + (passo - largura) / 2
        y = height - pad_b - h
        partes.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{largura:.1f}" '
                      f'height="{max(h, 0.6):.1f}" rx="2" fill="{PALETA.get(color, color)}">'
                      f'<title>{esc(rot)}: {_fmt(val)}</title></rect>')
        if mostrar_valores and val:
            partes.append(f'<text x="{x + largura / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" '
                          f'font-size="10" fill="var(--muted)">{_fmt(val)}</text>')
        lbl = rot if len(rot) <= rotulo_max else rot[:rotulo_max - 1] + "…"
        partes.append(f'<text x="{x + largura / 2:.1f}" y="{height - pad_b + 13:.1f}" '
                      f'text-anchor="middle" font-size="10" fill="var(--muted)">{esc(lbl)}</text>')
    if unidade:
        partes.append(f'<text x="{pad_e - 6}" y="{pad_t - 8}" text-anchor="end" font-size="10" '
                      f'fill="var(--muted)">{esc(unidade)}</text>')
    return (f'<svg class="dv" viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(partes)}</svg>')


# ------------------------------------------------------------- barras horizontais
def bar_chart_h(items, width=720, bar_height=24, gap=6, color="accent", rotulo_max=34):
    """items: [(rótulo, valor)] já ordenados do maior para o menor."""
    if not items:
        return ""
    items = [(str(r), float(v or 0)) for r, v in items]
    vmax = max([v for _r, v in items] + [1])
    altura = len(items) * (bar_height + gap) + 6
    largura_rot = 250
    largura_barra = width - largura_rot - 60
    partes = []
    for i, (rot, val) in enumerate(items):
        y = i * (bar_height + gap) + 3
        w = max((val / vmax) * largura_barra, 1.5)
        lbl = rot if len(rot) <= rotulo_max else rot[:rotulo_max - 1] + "…"
        partes.append(f'<text x="0" y="{y + bar_height * 0.68:.1f}" font-size="11.5" '
                      f'fill="var(--text)">{esc(lbl)}</text>')
        partes.append(f'<rect x="{largura_rot}" y="{y}" width="{w:.1f}" height="{bar_height}" '
                      f'rx="3" fill="{PALETA.get(color, color)}" opacity="0.85">'
                      f'<title>{esc(rot)}: {_fmt(val)}</title></rect>')
        partes.append(f'<text x="{largura_rot + w + 6:.1f}" y="{y + bar_height * 0.68:.1f}" '
                      f'font-size="11" font-weight="700" fill="var(--muted)">{_fmt(val)}</text>')
    return (f'<svg class="dv" viewBox="0 0 {width} {altura}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(partes)}</svg>')


# ------------------------------------------------------------------- linhas
def line_chart(labels, series, width=720, height=210, y_max=None, unidade=""):
    """series: [{"nome": str, "valores": [...], "cor": "accent", "area": bool}]"""
    pontos = max([len(s["valores"]) for s in series] + [0])
    if not pontos:
        return ""
    pad_e, pad_d, pad_b, pad_t = 42, 12, 34, 26
    y_max = y_max or max([max(s["valores"]) for s in series if s["valores"]] + [1]) * 1.12
    largura = width - pad_e - pad_d
    altura = height - pad_t - pad_b
    partes = []
    for i in range(3):
        y = pad_t + altura * i / 2
        partes.append(f'<line x1="{pad_e}" y1="{y:.1f}" x2="{width - pad_d}" y2="{y:.1f}" '
                      f'stroke="var(--border)" stroke-dasharray="3 3"/>')
        partes.append(f'<text x="{pad_e - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="10" '
                      f'fill="var(--muted)">{_fmt(y_max * (1 - i / 2))}</text>')
    passo = largura / max(1, pontos - 1)

    def px(i):
        return pad_e + (i * passo if pontos > 1 else largura / 2)

    def py(v):
        return pad_t + altura - (min(v, y_max) / y_max) * altura

    for k, s in enumerate(series):
        vals = s["valores"]
        cor = PALETA.get(s.get("cor", ""), s.get("cor") or CORES[k % len(CORES)])
        d = " ".join(f"{'M' if i == 0 else 'L'}{px(i):.1f},{py(v):.1f}"
                     for i, v in enumerate(vals))
        if s.get("area") and pontos > 1:
            partes.append(f'<path d="{d} L{px(len(vals) - 1):.1f},{pad_t + altura:.1f} '
                          f'L{px(0):.1f},{pad_t + altura:.1f} Z" fill="{cor}" opacity="0.12"/>')
        partes.append(f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="2.2" '
                      f'stroke-linejoin="round"/>')
        for i, v in enumerate(vals):
            partes.append(f'<circle cx="{px(i):.1f}" cy="{py(v):.1f}" r="3" fill="{cor}">'
                          f'<title>{esc(s["nome"])} — {esc(labels[i] if i < len(labels) else "")}: '
                          f'{_fmt(v)}</title></circle>')
    # rótulos do eixo X (no máximo 6)
    if labels:
        idx = sorted({round(i * (len(labels) - 1) / max(1, min(5, len(labels) - 1)))
                      for i in range(min(6, len(labels)))})
        for i in idx:
            partes.append(f'<text x="{px(i):.1f}" y="{height - pad_b + 14:.1f}" '
                          f'text-anchor="middle" font-size="10" fill="var(--muted)">'
                          f'{esc(labels[i])}</text>')
    if unidade:
        partes.append(f'<text x="{pad_e - 6}" y="{pad_t - 10}" text-anchor="end" font-size="10" '
                      f'fill="var(--muted)">{esc(unidade)}</text>')
    return (f'<svg class="dv" viewBox="0 0 {width} {height}" role="img" '
            f'preserveAspectRatio="xMidYMid meet">{"".join(partes)}</svg>')


def legenda(series):
    itens = "".join(
        f'<span class="dv-leg-item"><i style="background:{PALETA.get(s.get("cor", ""), s.get("cor") or CORES[i % len(CORES)])}"></i>'
        f'{esc(s["nome"])}</span>'
        for i, s in enumerate(series))
    return f'<div class="dv-legenda">{itens}</div>' if itens else ""


# ------------------------------------------------------- barra empilhada única
def stacked_bar(items, width=720, altura=26):
    """items: [(rótulo, valor, cor)] — composição de um total."""
    itens = [(str(r), float(v or 0), PALETA.get(c, c)) for r, v, c in items]
    total = sum(v for _r, v, _c in itens) or 1
    partes, x = [], 0.0
    for rot, val, cor in itens:
        w = (val / total) * width
        partes.append(f'<rect x="{x:.1f}" y="0" width="{max(w - 1, 0):.1f}" height="{altura}" '
                      f'rx="3" fill="{cor}" opacity="0.85"><title>{esc(rot)}: {_fmt(val)} '
                      f'({val / total * 100:.0f}%)</title></rect>')
        x += w
    return (f'<svg class="dv" viewBox="0 0 {width} {altura}" role="img" '
            f'preserveAspectRatio="none">{"".join(partes)}</svg>')


def stacked_legenda(items):
    itens = "".join(
        f'<span class="dv-leg-item"><i style="background:{PALETA.get(c, c)}"></i>{esc(r)} '
        f'<b>{_fmt(v)}</b></span>' for r, v, c in items)
    return f'<div class="dv-legenda">{itens}</div>'


# --------------------------------------------------------------- calendário
def heatmap(dias, width=720, cell=13, gap=3, semanas=26, fim=None):
    """dias: {ISO date: valor}; desenha as últimas `semanas` semanas até `fim`."""
    if not dias:
        return ""
    from datetime import date, timedelta  # import local: módulo também usado em build

    fim = fim or date.fromisoformat(sorted(dias)[-1])
    fim = fim + timedelta(days=(6 - fim.weekday()))  # fecha a semana (domingo)
    inicio = fim - timedelta(days=semanas * 7 - 1)
    vmax = max(dias.values()) or 1
    rotulos = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    partes, meses, ultimo_mes = [], [], None
    for s in range(semanas):
        for d in range(7):
            dia = inicio + timedelta(days=s * 7 + d)
            chave = dia.isoformat()
            v = dias.get(chave, 0)
            x = s * (cell + gap)
            y = d * (cell + gap) + 14
            if d == 0 and dia.month != ultimo_mes and dia.day <= 7:
                ultimo_mes = dia.month
                meses.append((x, dia.strftime("%b")))
            if v:
                intensidade = 0.25 + 0.75 * (v / vmax)
                cor, op = "var(--accent)", f"{intensidade:.2f}"
            else:
                cor, op = "var(--border)", "0.55"
            partes.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" '
                          f'fill="{cor}" opacity="{op}"><title>{chave}: {_fmt(v)} mudança(s)'
                          f'</title></rect>')
    for x, nome in meses:
        partes.append(f'<text x="{x}" y="10" font-size="10" fill="var(--muted)">{esc(nome)}</text>')
    for d, nome in enumerate(rotulos):
        if d % 2 == 0:
            partes.append(f'<text x="-8" y="{d * (cell + gap) + 14 + cell * 0.75:.0f}" '
                          f'text-anchor="end" font-size="9.5" fill="var(--muted)">{esc(nome)}</text>')
    altura = 7 * (cell + gap) + 16
    return (f'<svg class="dv" viewBox="-34 0 {width + 34} {altura}" role="img">'
            f'{"".join(partes)}</svg>')
