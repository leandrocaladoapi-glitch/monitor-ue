#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_site.py — Gera o site estático do Monitor Legislativo de IA a partir de /data/legislation.

Uso: python3 scripts/build_site.py
Saída: /docs (publicado pela Vercel; build = este script, output = docs/).

Sem dependências externas. Cada execução regenera todas as páginas a partir do
dataset versionado em /data/legislation (fonte única da verdade).
"""
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone

import dataviz as dv
from commercial_pages import business_html

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "legislation")
ASSETS = os.path.join(BASE, "scripts", "assets")
OUT = os.path.join(BASE, "docs")

# Domínio oficial (Vercel). Usado em canonical/OG/sitemap/navegação.
SITE_URL = "https://monitor-legislativo-five.vercel.app"
OLD_DOMAIN = "lcaladoferreira.github.io/monitor-legislativo"
SITE_NAME = "Monitor UE de IA"
TAGLINE = "Monitoramento público, documentado e auditável da legislação e da regulação de IA da União Europeia"

AUTHOR_NAME = "Leandro Calado"
AUTHOR_ORG = "LCF Consulting"
AUTHOR_URLS = [
    ("https://leandrocaladoferreira.com/", "Leandro Calado"),
    ("https://lcfconsulting.com.br/", "LCF Consulting"),
]
CONSULTING_URL = "https://lcfconsulting.com.br/"
DISCLAIMER = "Dados legislativos devem sempre ser conferidos nas fontes oficiais."
CTA_TEXT = "Precisa acompanhar impactos regulatórios de IA para sua empresa?"
CTA_SUB = "Inteligência regulatória, alertas legislativos e briefings para Public Affairs."

EXECUTION_DATE = "2026-09-08"  # atualizado dinamicamente a partir de updates.json
EXECUTION_RUN = {}
EXECUTION_TS = None  # fim (ou início) da última execução, em ISO — usado no selo de frescor


def _freshness_badge():
    """Selo no topo de todas as páginas: idade real da última execução.

    O valor absoluto é renderizado no build; o texto relativo (e o semáforo) é
    recalculado no navegador a cada visita — assim uma parada do cron aparece
    para o visitante, mesmo sem rebuild.
    """
    if not EXECUTION_TS:
        return ""
    rotulo = fmt_date(EXECUTION_TS) + " " + (re.search(r"T(\d{2}:\d{2})", EXECUTION_TS).group(1)
                                            if re.search(r"T(\d{2}:\d{2})", EXECUTION_TS) else "")
    return (f'<a class="fresh" href="{SITE_URL}/monitoramento/" data-freshness="{esc(EXECUTION_TS)}" '
            f'data-estado="ok" title="Idade da última execução do monitoramento (recalculada agora)">'
            f'<span class="dot"></span><span data-fresh-label>Última verificação: {esc(rotulo.strip())}</span>'
            f'</a>')


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def esc(t):
    if t is None:
        return ""
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# Slugs únicos por proposição (estáveis; só prefixa com a casa em colisão).
_SLUGS = {}


def build_slugs(props):
    global _SLUGS
    _SLUGS = {}
    base_count = {}
    for p in sorted(props, key=lambda x: x["id"]):
        base = re.sub(r"^ue_", "", p["id"]).replace("_", "-")
        base_count[base] = base_count.get(base, 0) + 1
    for p in sorted(props, key=lambda x: x["id"]):
        base = re.sub(r"^ue_", "", p["id"]).replace("_", "-")
        if base_count[base] > 1:
            casa = p["id"].split("_")[0]
            _SLUGS[p["id"]] = f"{casa}-{base}"
        else:
            _SLUGS[p["id"]] = base


def slugify_prop(pid):
    return _SLUGS.get(pid, re.sub(r"^ue_", "", pid).replace("_", "-"))


def prop_fs_path(pid):
    # caminho do arquivo no sistema (relativo a docs/)
    return f"procedimentos-legislativos/{slugify_prop(pid)}/index.html"


def fmt_date(d):
    if not d:
        return "—"
    try:
        dt = datetime.strptime(str(d)[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(d)


def ref_date():
    try:
        return datetime.strptime(EXECUTION_DATE[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return datetime(2026, 9, 8).date()


def days_ago(d):
    try:
        dt = datetime.strptime(str(d)[:10], "%Y-%m-%d").date()
        return (ref_date() - dt).days
    except (ValueError, TypeError):
        return None


def rel_label(d):
    n = days_ago(d)
    if n is None:
        return fmt_date(d)
    if n < 0:
        return fmt_date(d)
    if n == 0:
        return "Hoje"
    if n == 1:
        return "Ontem"
    return f"{n} dias atrás"


def score_class(s):
    if s >= 90:
        return "score-critico"
    if s >= 75:
        return "score-muito"
    if s >= 60:
        return "score-relevante"
    if s >= 40:
        return "score-monitorar"
    return "score-baixa"


def score_label(s):
    if s >= 90:
        return "CRÍTICO"
    if s >= 75:
        return "MUITO RELEVANTE"
    if s >= 60:
        return "RELEVANTE"
    if s >= 40:
        return "MONITORAR"
    return "BAIXA PRIORIDADE"


def status_group(p):
    s = (p.get("situacao") or "").lower()
    if "publicado no jornal oficial" in s:
        return "publicado_jo"
    if "assinado" in s:
        return "assinado"
    if any(k in s for k in ("rejeitad", "retirad", "repealed")):
        return "rejeitado"
    return "em_tramitacao"


STATUS_LABEL = {
    "em_tramitacao": ("Em tramitação", "status-active"),
    "assinado": ("Assinado — aguarda JO", "status-approved"),
    "publicado_jo": ("Publicado no Jornal Oficial", "status-law"),
    "rejeitado": ("Rejeitado/retirado", "status-archived"),
}


def cat_map():
    cats = load("categories.json")["categorias"]
    return {c["id"]: c for c in cats}


def prop_link(p):
    return f'{SITE_URL}/procedimentos-legislativos/{slugify_prop(p["id"])}/'


def prop_link_by_id(pid, by_id):
    p = by_id.get(pid)
    if p:
        return prop_link(p)
    return f"{SITE_URL}/procedimentos-legislativos/"


def changes_for_prop(pid, updates):
    out = [m for m in updates.get("mudancas", []) if m.get("proposicao") == pid]
    return sorted(out, key=lambda m: m.get("data", ""), reverse=True)


def guess_principal_id(p):
    """Relação de dossiê principal (sem equivalente na UE — procedimentos não
    têm apensação). Mantém o contrato para chamadores existentes."""
    if p.get("procedimento_vinculado"):
        return p["procedimento_vinculado"]
    return None


OFFICIAL_DOMAINS = (
    "europa.eu", "europarl.europa.eu", "consilium.europa.eu",
    "ec.europa.eu", "eur-lex.europa.eu", "data.europarl.europa.eu",
    "edpb.europa.eu", "edps.europa.eu", "digital-strategy.ec.europa.eu",
    "commission.europa.eu", "data.consilium.europa.eu",
)


def fonte_label(url):
    """Rotula honestamente: 'Fonte oficial' só para domínios oficiais."""
    u = (url or "").lower()
    if any(d in u for d in OFFICIAL_DOMAINS):
        return "Fonte oficial ↗"
    return "Fonte ↗"


def near_vote(p):
    """Heurística honesta de proximidade de votação (baseada na situação).

    Só considera sinais de iminência (sanção, pauta, plenário, redação final).
    Aprovações já ocorridas (ex.: 'aprovado na comissão em 2023') não contam.
    """
    s = (p.get("situacao") or "").lower()
    prox_terms = ["inscrito em pauta", "aguarda publicação", "aguarda confirmacao",
                  "trílogos em curso", "trilogos em curso",
                  "negociações interinstitucionais", "negociacoes interinstitucionais",
                  "aplicável a partir", "aplicável desde", "em vigor desde",
                  "aplicação faseada"]
    return any(t in s for t in prox_terms)


ROTULO_ORGAO = {
    "eu_parliament": "Parlamento Europeu",
    "eu_council": "Conselho da União Europeia",
    "eu_commission": "Comissão Europeia",
    "eurlex": "EUR-Lex / Jornal Oficial da UE",
    "ai_office": "European AI Office (Comissão Europeia)",
    "edpb": "EDPB — European Data Protection Board",
    "edps": "EDPS — European Data Protection Supervisor",
    "parlamento": "Parlamento Europeu (motor legislativo)",
    "eurlex": "EUR-Lex (motor legislativo)",
}


def change_prop_href(m, by_id):
    """Link do registro: procedimento ou ato publicado por instituição da UE."""
    pid = m.get("proposicao")
    if pid and pid in by_id:
        return prop_link(by_id[pid]), f'{by_id[pid]["tipo"]} {by_id[pid]["numero"]}/{by_id[pid]["ano"]}'
    if m.get("orgao") and m.get("url_oficial"):
        return m["url_oficial"], f'publicação de {ROTULO_ORGAO.get(m["orgao"], m["orgao"])}'
    return f"{SITE_URL}/procedimentos-legislativos/", "todos os procedimentos"


# ------------------------------------------------------------- JSON-LD base
def ld_website():
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "alternateName": "Monitor Legislativo e Regulatório de IA da União Europeia",
        "url": SITE_URL + "/",
        "description": TAGLINE,
        "inLanguage": "pt-BR",
    }


def ld_breadcrumbs(items):
    # items: [(nome, path_ou_None)]
    els = []
    for i, (nome, path) in enumerate(items, 1):
        el = {"@type": "ListItem", "position": i, "name": nome}
        if path is not None:
            el["item"] = SITE_URL + "/" + path
        els.append(el)
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": els}


def ld_collection(name, desc, path):
    return {"@context": "https://schema.org", "@type": "CollectionPage",
            "name": name, "description": desc, "url": SITE_URL + "/" + path,
            "inLanguage": "pt-BR",
            "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE_URL + "/"}}


def combine_ld(*blocks):
    return {"@context": "https://schema.org", "@graph": [b for b in blocks if b]}


# ---------------------------------------------------------------- layout
def _atos_footer_link():
    """Link para o atos.json (multi-órgão) só quando o dataset já existe.

    Antes da primeira execução multiórgão o arquivo não existe; um link fixo
    apontaria para 404 (o validador de links internos acusa isso). O domínio é
    lido no momento da renderização (`SITE_URL` do módulo), nunca no import:
    `build_site.py` troca o domínio para o oficial depois de importar este
    módulo, e um valor congelado no import publicaria o domínio antigo.
    """
    if os.path.exists(os.path.join(BASE, "data", "legislation", "atos.json")):
        return '<br>\n      <a href="{0}/data/atos.json">atos.json</a>'.format(SITE_URL)
    return ""


def page(title, desc, path, body, extra_head="", og_type="website", jsonld=None):
    canon = SITE_URL + "/" + path if path else SITE_URL + "/"
    nav_items = [
        ("", "Início"),
        ("procedimentos-legislativos/", "Procedimentos"),
        ("atualizacoes/", "Atualizações"),
        ("legislacao-e-atos/", "Legislação e atos"),
        ("timeline/", "Timeline"),
        ("atores-legislativos/", "Atores legislativos"),
        ("agenda/", "Agenda"),
        ("monitoramento/", "Monitoramento"),
        ("metodologia/", "Metodologia"),
        ("relatorio/", "Relatório"),
    ]
    nav_parts = []
    for u, l in nav_items:
        cls = ' class="active"' if path == u else ""
        nav_parts.append(f'<a href="{SITE_URL}/{u}"{cls}>{l}</a>')
    nav = "".join(nav_parts)
    ld = ""
    if jsonld:
        ld = '<script type="application/ld+json">' + json.dumps(jsonld, ensure_ascii=False) + "</script>"
    author_links = " · ".join(f'<a href="{u}">{n}</a>' for u, n in AUTHOR_URLS)
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canon}">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:locale" content="pt_BR">
<meta property="og:url" content="{canon}">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="{SITE_URL}/assets/style.css">
{extra_head}
{ld}
</head>
<body>
<header class="site">
  <div class="wrap nav">
    <div class="brand">
      <a href="{SITE_URL}/">{SITE_NAME}</a>
      <small>Inteligência Artificial · União Europeia</small>
    </div>
    <nav class="links" aria-label="Principal">{nav}</nav>
    {_freshness_badge()}
  </div>
</header>
<main>
{body}
</main>
<footer class="site">
  <div class="wrap cols">
    <div>
      <h4>Monitor UE de IA</h4>
      <p>{TAGLINE}. Dados estruturados, fontes oficiais e histórico de alterações versionados no repositório.</p>
      <p class="author-line">Projeto desenvolvido por {AUTHOR_NAME} / {AUTHOR_ORG} — {author_links}</p>
      <p class="disclaimer">{DISCLAIMER}</p>
    </div>
    <div>
      <h4>Dados</h4>
      <p><a href="{SITE_URL}/data/propositions.json">propositions.json</a><br>
      <a href="{SITE_URL}/data/laws.json">laws.json</a><br>
      <a href="{SITE_URL}/data/timeline.json">timeline.json</a><br>
      <a href="{SITE_URL}/data/updates.json">updates.json</a><br>
      <a href="{SITE_URL}/data/events.json">events.json</a><br>
      <a href="{SITE_URL}/data/parliamentarians.json">parliamentarians.json</a><br>
      <a href="{SITE_URL}/data/categories.json">categories.json</a><br>
      <a href="{SITE_URL}/data/monitoramento.json">monitoramento.json</a>{_atos_footer_link()}
      <span style="color:var(--muted)">(métricas do cron)</span></p>
    </div>
    <div>
      <h4>Metodologia</h4>
      <p>Última execução do monitoramento: <b>{fmt_date(EXECUTION_DATE)}</b>.<br>
      Fontes primárias: Parlamento Europeu, Conselho da UE, Comissão Europeia,<br>
      EUR-Lex/JO, European AI Office, EDPB e EDPS.<br>
      <a href="{SITE_URL}/metodologia/">Metodologia completa</a> ·
      <a href="{SITE_URL}/relatorio/">Relatório da execução</a></p>
    </div>
    <div>
      <h4>Aviso</h4>
      <p>Conteúdo informativo baseado em fontes oficiais. Não substitui os textos legais publicados no Jornal Oficial da União Europeia nem as fichas oficiais dos procedimentos.</p>
      <p class="cta-mini">{CTA_TEXT} <a href="{CONSULTING_URL}">Fale com a {AUTHOR_ORG} →</a></p>
    </div>
  </div>
</footer>
<script src="{SITE_URL}/assets/site.js" defer></script>
</body>
</html>"""


def write(path, content):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def tags_for_prop(p, cats):
    out = []
    sg = status_group(p)
    lbl, cls = STATUS_LABEL[sg]
    out.append(f'<span class="tag {cls}">{lbl}</span>')
    if p.get("revisao_pendente"):
        out.append('<span class="tag review">Aguardando curadoria</span>')
    for c in p.get("categorias", [])[:4]:
        if c in cats:
            out.append(f'<span class="tag cat">{esc(cats[c]["nome"])}</span>')
    return " ".join(out)


def change_card(m, by_id):
    href, rotulo = change_prop_href(m, by_id)
    return (
        f'<div class="change-item"><div class="when">{esc(rel_label(m["data"]))} · {fmt_date(m["data"])}'
        + (f' · {esc(m["tipo"])}' if m.get("tipo") else "")
        + f'</div><h3><a href="{href}">{esc(m["titulo"])}</a></h3>'
        f'<p>{esc(m["descricao"])}</p>'
        f'<p class="change-links"><a href="{href}">Ver {esc(rotulo)} →</a> · '
        f'<a href="{m["fonte_url"]}" target="_blank" rel="noopener">{fonte_label(m["fonte_url"])}</a></p></div>'
    )


def run_summary():
    """Resumo da última execução para blocos de verificação.

    Consolida as instituições do motor legislativo (Parlamento/EUR-Lex) com os
    conectores regulatórios registrados em `fontes_monitoradas`. Assim o
    relatório reflete exatamente o que a execução realmente consultou, sem
    hardcode de órgãos adicionais no HTML.
    """
    run = EXECUTION_RUN or {}
    dh = run.get("data_hora", EXECUTION_DATE)
    data = fmt_date(dh)
    hora = ""
    m = re.search(r"T(\d{2}:\d{2})", str(dh))
    if m:
        hora = m.group(1) + " (BRT)"

    fontes = list(run.get("fontes_consultadas", []) or [])
    fontes_monitoradas = run.get("fontes_monitoradas") or {}

    if isinstance(fontes_monitoradas, dict):
        for chave, info in fontes_monitoradas.items():
            # As instituições do motor legislativo já aparecem em fontes_consultadas.
            if chave in ("parlamento", "eurlex") or not info:
                continue
            rotulo = ROTULO_ORGAO.get(chave, str(chave).upper())
            endpoints = info.get("endpoints") or []
            if endpoints:
                for endpoint in endpoints:
                    fontes.append(f"{rotulo} — {endpoint}")
            else:
                fontes.append(rotulo)

    # Preserva ordem e remove duplicatas.
    fontes = list(dict.fromkeys(fontes))

    return {
        "data": data, "hora": hora or "—",
        "fontes": fontes,
        "verificadas": run.get("procedimentos_verificados", run.get("proposicoes_verificadas", "—")),
        "mudancas": run.get("mudancas_detectadas", "—"),
        "novas": run.get("novos_procedimentos", run.get("novas_proposicoes", 0)),
    }


# ---------------------------------------------------------------- páginas
def build_home(props, laws, events, updates, timeline, cats):
    by_id = {p["id"]: p for p in props}
    mudancas = sorted(updates["mudancas"], key=lambda m: m["data"], reverse=True)
    last24 = [m for m in mudancas if days_ago(m["data"]) == 0]
    last7 = [m for m in mudancas if days_ago(m["data"]) is not None and 0 <= days_ago(m["data"]) <= 7]
    rs = run_summary()

    def section_changes(title, sub, items, empty_msg):
        if items:
            cards = "".join(change_card(m, by_id) for m in items[:6])
        else:
            cards = f'<div class="note">{empty_msg}</div>'
        return (f'<h3 class="mini-title">{title}</h3><p class="section-sub">{sub}</p>{cards}')

    changes_24 = section_changes(
        "Últimas 24 horas", "Mudanças com data de evento nas últimas 24 horas.",
        last24, "Nenhuma mudança detectada nas últimas 24 horas. O monitoramento segue ativo — veja o histórico completo em Atualizações.")
    changes_7 = section_changes(
        "Últimos 7 dias", "Movimentações com data de evento nos últimos 7 dias.",
        [m for m in last7 if m not in last24],
        "Nenhuma outra mudança nos últimos 7 dias além das destacadas acima.")

    active = [p for p in props if status_group(p) == "em_tramitacao"]
    archived = [p for p in props if status_group(p) == "rejeitado"]
    to_sancao = [p for p in props if status_group(p) == "assinado"]
    laws_ok = [l for l in laws if "Em vigor" in l.get("status", "")]
    mv7 = len([m for m in mudancas if days_ago(m["data"]) is not None and days_ago(m["data"]) <= 7])
    mv30 = len([m for m in mudancas if days_ago(m["data"]) is not None and days_ago(m["data"]) <= 30])

    top = sorted(props, key=lambda p: -p["impacto"]["score"])[:6]
    top_html = "".join(
        f'<div class="card"><h3><a href="{prop_link(p)}">{esc(p["tipo"])} {p["numero"]}/{p["ano"]} — {esc(p["titulo"])}</a></h3>'
        f'<p>{esc((p.get("resumo") or p["ementa"])[:220])}…</p>'
        f'<div class="meta"><span class="score-badge {score_class(p["impacto"]["score"])}">Score {p["impacto"]["score"]}/100 · {esc(p["impacto"]["classificacao"].split(" (")[0])}</span>'
        f'{tags_for_prop(p, cats)}</div></div>'
        for p in top
    )

    near = [p for p in props if status_group(p) in ("em_tramitacao", "assinado") and near_vote(p)]
    near = sorted(near, key=lambda p: -p["impacto"]["score"])[:6]
    if near:
        near_html = "".join(
            f'<div class="card"><h3><a href="{prop_link(p)}">{esc(p["tipo"])} {p["numero"]}/{p["ano"]} — {esc(p["titulo"])}</a></h3>'
            f'<p><b>Situação:</b> {esc((p.get("situacao") or "")[:200])}</p>'
            f'<div class="meta"><span class="score-badge {score_class(p["impacto"]["score"])}">Score {p["impacto"]["score"]}/100</span>'
            f'{tags_for_prop(p, cats)}</div></div>'
            for p in near
        )
    else:
        near_html = '<div class="card"><p>Nenhum dossiê com data de aplicação, pauta ou negociação ativa confirmada nesta execução. Critério e limitações na <a href="' + SITE_URL + '/metodologia/">metodologia</a>.</p></div>'

    novas = [m for m in mudancas if (m.get("tipo") or "") == "nova proposição"
             and days_ago(m["data"]) is not None and days_ago(m["data"]) <= 30][:4]
    if novas:
        novas_html = "".join(change_card(m, by_id) for m in novas)
    else:
        novas_html = '<div class="note">Nenhum procedimento novo incorporado nos últimos 30 dias.</div>'

    laws_sorted = sorted([l for l in laws if l.get("data")], key=lambda l: l["data"], reverse=True)[:3]
    laws_html = "".join(
        f'<div class="card"><h3>{esc(l["tipo"])} {esc(l["numero"])} — {esc(l["nome"])}</h3>'
        f'<p><b>{fmt_date(l["data"])}</b> · {esc(l["status"])} · {esc(l["relacao_ia"][:160])}…</p>'
        f'<p style="margin-top:8px"><a href="{l["url"]}" target="_blank" rel="noopener">Texto oficial ↗</a></p></div>'
        for l in laws_sorted
    )

    agenda_soon = [e for e in events["eventos"] if e.get("janela") in ("proximos_7_dias", "proximos_30_dias")]
    agenda_html = "".join(
        f'<div class="card"><h3>{esc(e["titulo"])}</h3>'
        f'<p><b>{fmt_date(e.get("data_inicio"))}</b> · {esc(e["casa"])} · {esc(e["tipo"])}</p>'
        f'<p>{esc(e["tema"][:200])}</p></div>'
        for e in agenda_soon
    ) or '<div class="card"><p>Nenhum evento futuro confirmado nas fontes oficiais para o período. Consultas abertas no portal Have Your Say aparecem aqui assim que entram no período de feedback.</p></div>'

    cat_chips = " ".join(
        f'<a class="tag cat" href="{SITE_URL}/procedimentos-legislativos/">{esc(c["nome"])}</a>'
        for c in list(cats.values())[:12]
    )

    # faixa de saúde do monitoramento (alimentada pelo log de execuções)
    agora = datetime.now(timezone.utc)
    ts_ult = _parse_ts((EXECUTION_RUN or {}).get("fim") or (EXECUTION_RUN or {}).get("data_hora")) \
        if EXECUTION_RUN else None
    idade_h = round((agora - ts_ult).total_seconds() / 3600, 1) if ts_ult else None
    estado_h = ("ok" if (idade_h is not None and idade_h <= 30) else
                "atencao" if (idade_h is not None and idade_h <= 54) else
                "critico" if idade_h is not None else "atencao")
    idade_txt = ("—" if idade_h is None else
                 f"{idade_h:.1f} h" if idade_h < 48 else f"{idade_h / 24:.1f} dias")
    cob = (EXECUTION_RUN or {}).get("cobertura_pct")
    pend = (EXECUTION_RUN or {}).get("procedimentos_pendentes",
                                     (EXECUTION_RUN or {}).get("proposicoes_pendentes"))
    status_run = (EXECUTION_RUN or {}).get("status", "—")
    health_strip = f"""
<section class="block" id="saude"><div class="wrap">
  <h2 class="section-title">Saúde do monitoramento</h2>
  <p class="section-sub">Como está a automação do monitoramento: frescor, cobertura e volume.
  <a href="{SITE_URL}/monitoramento/">Ver o painel completo de métricas →</a></p>
  <div class="grid cols-4">
    <div class="metric {'green' if estado_h == 'ok' else 'yellow' if estado_h == 'atencao' else 'red'}"><div class="num">{idade_txt}</div><div class="lbl">Desde a última execução</div></div>
    <div class="metric blue"><div class="num">{f"{cob}%" if cob is not None else "—"}</div><div class="lbl">Cobertura da verificação</div></div>
    <div class="metric"><div class="num">{pend if pend is not None else "—"}</div><div class="lbl">Proposições pendentes</div></div>
    <div class="metric"><div class="num">{status_run.capitalize() if status_run else "—"}</div><div class="lbl">Status da última execução</div></div>
  </div>
  <p class="disclaimer" style="margin-top:10px">Métricas geradas a partir do log auditável do cron
  (<code>updates.json</code>) — reconstruídas a cada execução do site.</p>
</div></section>"""

    fontes_lista = "".join(f"<li>{esc(f)}</li>" for f in rs["fontes"][:8])
    verify_block = f"""
<section class="block" id="verificacao"><div class="wrap">
  <h2 class="section-title">Última verificação</h2>
  <p class="section-sub">Transparência operacional: quando verificamos, o que consultamos e o que mudou.</p>
  <div class="verify-box">
    <div class="verify-grid">
      <div><span class="v-lbl">Data</span><span class="v-val">{rs["data"]}</span></div>
      <div><span class="v-lbl">Hora</span><span class="v-val">{rs["hora"]}</span></div>
      <div><span class="v-lbl">Proposições verificadas</span><span class="v-val">{rs["verificadas"]}</span></div>
      <div><span class="v-lbl">Mudanças detectadas</span><span class="v-val">{rs["mudancas"]}</span></div>
      <div><span class="v-lbl">Novas proposições</span><span class="v-val">{rs["novas"]}</span></div>
    </div>
    <details class="verify-fontes"><summary>Fontes consultadas ({len(rs["fontes"])})</summary><ul>{fontes_lista or "<li>—</li>"}</ul></details>
    <p class="verify-note">{DISCLAIMER}</p>
  </div>
</div></section>"""

    body = f"""
<div class="hero"><div class="wrap">
  <div class="kicker">Sistema de inteligência legislativa e regulatória · Execução de {fmt_date(EXECUTION_DATE)}</div>
  <h1>Inteligência Artificial — Monitoramento Legislativo e Regulatório da União Europeia</h1>
  <p class="lead">Central pública de acompanhamento dos procedimentos legislativos, da legislação adotada e dos atos regulatórios das instituições da União Europeia sobre inteligência artificial — com AI Legislative Impact Score, timeline do AI Act, agenda oficial de consultas e registro auditável de mudanças.</p>
  <div class="updated">Última verificação das fontes oficiais: <b>{fmt_date(EXECUTION_DATE)}</b> · {len(props)} procedimentos monitorados · {len(laws)} atos mapeados · <a href="#o-que-mudou">veja o que mudou recentemente</a></div>
</div></div>

{verify_block}

{health_strip}

<section class="block" id="o-que-mudou"><div class="wrap">
  <h2 class="section-title">O que mudou na regulação de IA</h2>
  <p class="section-sub">Alterações recentes com impacto documentado. Nada é publicado sem fonte oficial. Quando não há mudança relevante, registramos apenas a verificação. <a href="{SITE_URL}/atualizacoes/">Histórico completo de atualizações →</a></p>
  {changes_24}
  <div style="margin-top:22px">{changes_7}</div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Dashboard</h2>
  <p class="section-sub">Indicadores do banco de procedimentos nesta execução.</p>
  <div class="grid cols-4">
    <div class="metric blue"><div class="num">{len(props)}</div><div class="lbl">Procedimentos monitorados</div></div>
    <div class="metric green"><div class="num">{len(active)}</div><div class="lbl">Em tramitação</div></div>
    <div class="metric"><div class="num">{len(archived)}</div><div class="lbl">Rejeitados/retirados</div></div>
    <div class="metric yellow"><div class="num">{len(to_sancao)}</div><div class="lbl">Assinados — aguardam JO</div></div>
    <div class="metric green"><div class="num">{len(laws_ok)}</div><div class="lbl">Atos em vigor mapeados</div></div>
    <div class="metric"><div class="num">{len(agenda_soon)}</div><div class="lbl">Eventos futuros previstos</div></div>
    <div class="metric"><div class="num">{mv7}</div><div class="lbl">Movimentações (7 dias)</div></div>
    <div class="metric"><div class="num">{mv30}</div><div class="lbl">Movimentações (30 dias)</div></div>
  </div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Dossiês de maior impacto agora</h2>
  <p class="section-sub">Ordenados pelo AI Legislative Impact Score — abrangência, estágio do procedimento, datas de aplicação e efeito regulatório. <a href="{SITE_URL}/procedimentos-legislativos/">Ver todos os procedimentos com filtros →</a></p>
  <div class="grid cols-3">{top_html}</div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Próximas etapas e datas de aplicação</h2>
  <p class="section-sub">Dossiês cuja situação oficial indica pauta de plenário, negociações em curso, assinatura pendente ou data de aplicação confirmada. Critério objetivo descrito na <a href="{SITE_URL}/metodologia/">metodologia</a>.</p>
  <div class="grid cols-3">{near_html}</div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Novos procedimentos (30 dias)</h2>
  <p class="section-sub">Dossiês incorporados ao monitoramento a partir das fontes oficiais. Registros automáticos aguardam curadoria editorial.</p>
  {novas_html}
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Normas recentes</h2>
  <p class="section-sub">Últimos atos mapeados. <a href="{SITE_URL}/legislacao-e-atos/">Toda a legislação e atos →</a></p>
  <div class="grid cols-3">{laws_html}</div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Estado da regulação de IA na União Europeia</h2>
  <p class="section-sub">Síntese editorial — fatos e interpretação separados. Análise completa na <a href="{SITE_URL}/relatorio/">página de relatório</a>.</p>
  <div class="note"><b>Em uma frase:</b> a União Europeia já tem seu marco geral de IA aprovado — o AI Act (Regulamento (UE) 2024/1689, procedimento 2021/0106(COD)) está em vigor desde 1º de agosto de 2024, com aplicação faseada concluída em 2 de agosto de 2026 (sistemas de alto risco e transparência) — e o centro de gravidade regulatório agora é a implementação: European AI Office, códigos de prática e guidelines para modelos de uso geral (GPAI), além do enforcement da EDPB e das autoridades nacionais.</div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Agenda legislativa de IA</h2>
  <p class="section-sub">Próximos eventos e marcos normativos. <a href="{SITE_URL}/agenda/">Agenda completa →</a></p>
  <div class="grid cols-3">{agenda_html}</div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Categorias temáticas</h2>
  <p class="section-sub">Classificação dos dossiês em até 30 categorias, do quadro geral do AI Act à soberania digital. Veja os filtros na página de procedimentos.</p>
  <div style="display:flex;gap:8px;flex-wrap:wrap">{cat_chips} <a class="tag cat" href="{SITE_URL}/procedimentos-legislativos/">+ todas</a></div>
</div></section>

<section class="block"><div class="wrap">
  <div class="cta-box">
    <div><h3>{CTA_TEXT}</h3><p>{CTA_SUB}</p></div>
    <a class="cta-btn" href="{CONSULTING_URL}">Falar com a {AUTHOR_ORG}</a>
  </div>
</div></section>
"""
    dataset_ld = {
        "@type": "Dataset",
        "name": "Monitor Legislativo e Regulatório de IA da União Europeia",
        "description": TAGLINE,
        "url": SITE_URL + "/",
        "keywords": ["AI Act", "regulação inteligência artificial União Europeia",
                     "regulação IA UE", "AI Act em português", "GPAI",
                     "European AI Office", "EU AI law"],
        "temporalCoverage": "2021/2026",
        "dateModified": EXECUTION_DATE,
        "creator": {"@type": "Organization", "name": SITE_NAME,
                    "url": SITE_URL + "/"},
    }
    jsonld = combine_ld(ld_website(), dataset_ld)
    write("index.html", page(
        "AI Act e regulação de IA na União Europeia — monitoramento legislativo e regulatório",
        "Acompanhe o AI Act (Regulamento (UE) 2024/1689) e toda a regulação de IA da União Europeia: procedimentos legislativos, atos adotados, implementação do AI Act, EDPB/EDPS, consultas públicas, timeline e agenda. Dados com fonte oficial.",
        "", body, jsonld=jsonld))


def build_propositions(props, cats):
    rows = []
    years = sorted({str(p["ano"]) for p in props}, reverse=True)
    for p in sorted(props, key=lambda x: -x["impacto"]["score"]):
        sg = status_group(p)
        lbl, cls = STATUS_LABEL[sg]
        cats_csv = "," + ",".join(str(c) for c in p.get("categorias", [])) + ","
        search = " ".join(filter(None, [
            p["titulo"], p["ementa"], p.get("autor", {}).get("nome", ""),
            p.get("autor", {}).get("partido", "") or "",
            str(p["numero"]), str(p["ano"]), p["tipo"],
        ])).lower()
        docs = p.get("documentos", [])
        doc0 = docs[0]["url"] if docs else p.get("url_oficial", "#")
        cat_tags = "".join(
            '<span class="tag cat">' + esc(cats[c]["nome"]) + "</span>"
            for c in p.get("categorias", [])[:3] if c in cats)
        review = ' <span class="tag review">Aguardando curadoria</span>' if p.get("revisao_pendente") else ""
        ell = "…" if len(p["ementa"]) > 260 else ""
        rows.append(
            f'<div class="prop-row" data-prop data-casa="{esc(p["casa_origem"])}" data-ano="{p["ano"]}" '
            f'data-statusgroup="{sg}" data-cats="{cats_csv}" data-score="{p["impacto"]["score"]}" data-search="{esc(search)}">'
            f'<div class="head"><div><h3><a href="{prop_link(p)}">{esc(p["tipo"])} {p["numero"]}/{p["ano"]} — {esc(p["titulo"])}</a></h3>'
            f'<p class="ementa">{esc(p["ementa"][:260])}{ell}</p></div>'
            f'<span class="score-badge {score_class(p["impacto"]["score"])}">{p["impacto"]["score"]}/100</span></div>'
            f'<div class="tagsline"><span class="tag {cls}">{lbl}</span>{review}'
            f'<span class="tag">Autor: {esc(p.get("autor", {}).get("nome", "—"))}</span>'
            f'{cat_tags}'
            f'<span class="tag"><a href="{doc0}" target="_blank" rel="noopener">ficha oficial ↗</a></span></div></div>'
        )
    opts_ano = '<option value="">Todos os anos</option>' + "".join(f'<option value="{y}">{y}</option>' for y in years)
    opts_cat = '<option value="">Todas as categorias</option>' + "".join(
        f'<option value="{c["id"]}">{esc(c["nome"])}</option>' for c in cats.values())

    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Procedimentos</div>
  <h1>Procedimentos legislativos e regulatórios de IA na União Europeia</h1>
  <p class="sub">Todos os dossiês monitorados, com filtros por instituição, ano, situação, categoria e score. Cada ficha traz a referência interinstitucional oficial, estágio do procedimento, eventos, relatoria, documentos e fontes primárias.</p>
</div></div>
<section class="block"><div class="wrap">
  <div class="filters">
    <input id="f-q" class="search" type="search" placeholder="Buscar por referência, título, tema ou instituição…">
    <select id="f-casa"><option value="">Todas as instituições</option><option value="Comissão Europeia">Comissão Europeia</option><option value="Parlamento Europeu">Parlamento Europeu</option><option value="Conselho da UE">Conselho da UE</option></select>
    <select id="f-ano">{opts_ano}</select>
    <select id="f-status"><option value="">Toda situação</option><option value="em_tramitacao">Em tramitação</option><option value="assinado">Assinado — aguarda JO</option><option value="publicado_jo">Publicado no JO</option><option value="rejeitado">Rejeitado/retirado</option></select>
    <select id="f-cat">{opts_cat}</select>
    <select id="f-score"><option value="0">Qualquer score</option><option value="80">Score 80+</option><option value="60-79">Score 60–79</option><option value="low">Score &lt;60</option><option value="60">Score ≥ 60</option><option value="75">Score ≥ 75</option><option value="90">Score ≥ 90 (crítico)</option></select>
  </div>
  <p id="count" style="color:var(--muted);font-size:13px;margin-bottom:14px"></p>
  {"".join(rows)}
</div></section>"""
    jsonld = combine_ld(
        ld_collection("Procedimentos legislativos e regulatórios de IA da União Europeia",
                      "Lista completa e filtrável dos procedimentos da União Europeia sobre inteligência artificial, com AI Legislative Impact Score, estágio oficial e fontes oficiais.",
                      "procedimentos-legislativos/"),
        ld_breadcrumbs([("Início", ""), ("Procedimentos", None)]))
    write("procedimentos-legislativos/index.html", page(
        "Procedimentos de IA da União Europeia — AI Act e correlatos, estágio e score",
        "Lista completa e filtrável dos procedimentos legislativos e regulatórios da União Europeia sobre inteligência artificial: AI Act, atos delegados, resoluções e correlatos, com estágio oficial e fontes oficiais.",
        "procedimentos-legislativos/", body, jsonld=jsonld))


def seo_title_prop(p):
    ref = p.get("procedimento") or f'{p["tipo"]} {p["numero"]}/{p["ano"]}'
    if p.get("id") == "ue_2021_0106_cod":
        return "AI Act (2021/0106(COD)): situação atual, estágio e aplicação do Regulamento (UE) 2024/1689"
    return f"{ref}: {p['titulo']} — estágio do procedimento e datas | Monitor UE de IA"


def seo_desc_prop(p):
    ref = p.get("procedimento") or f'{p["tipo"]} {p["numero"]}/{p["ano"]}'
    base = f"Acompanhe o procedimento {ref} ({p['titulo']}): {(p.get('situacao') or '')[:110]}"
    return (base + " Estágio oficial, eventos, relatoria, documentos e fontes oficiais.")[:300]


def build_prop_pages(props, cats, updates):
    by_id = {p["id"]: p for p in props}
    for p in props:
        sg = status_group(p)
        lbl, cls = STATUS_LABEL[sg]
        autor = p.get("autor", {})
        kv = [
            ("Procedimento interinstitucional", esc(p.get("procedimento") or f'{p["tipo"]} {p["numero"]}/{p["ano"]}')),
            ("Instituições", f'{esc(p["casa_origem"])} → {esc(p.get("casa_atual", "—"))}'),
            ("Autor", f'{esc(autor.get("nome", "—"))}' + (f' ({esc(autor["partido"])}-{esc(autor["estado"])})' if autor.get("partido") else "")),
            ("Tipo de procedimento", esc(p.get("api_ep", {}).get("process_type") or p["tipo"])),
            ("Texto oficial (ementa)", esc(p["ementa"])),
            ("Situação", esc(p.get("situacao", "—"))),
            ("Comissão", esc(p.get("comissao_atual", "—"))),
        ]
        relator = p.get("relator")
        if relator:
            kv.append(("Relatoria", f'{esc(relator["nome"])}' + (f' ({esc(relator["partido"])})' if relator.get("partido") else "")))
        if p.get("ultima_movimentacao"):
            kv.append(("Última movimentação", f'{fmt_date(p["ultima_movimentacao"].get("data"))} — {esc(p["ultima_movimentacao"].get("descricao") or p["ultima_movimentacao"].get("evento", ""))}'))
        if p.get("proxima_etapa"):
            kv.append(("Próxima etapa provável", esc(p["proxima_etapa"])))

        princ_id = guess_principal_id(p)
        if princ_id and princ_id in by_id:
            q = by_id[princ_id]
            kv.append(("Dossiê vinculado", f'<a href="{prop_link(q)}">{esc(q.get("procedimento") or q["id"])} — {esc(q["titulo"])}</a>'))
        elif princ_id:
            kv.append(("Dossiê vinculado", esc(princ_id)))

        kv_html = "".join(f'<div class="kv"><dt>{k}</dt><dd>{v}</dd></div>' for k, v in kv)

        docs_html = "".join(
            f'<li>▸ <a href="{d["url"]}" target="_blank" rel="noopener">{esc(d["titulo"])}</a></li>'
            for d in p.get("documentos", []))
        rels = list(p.get("relacionamentos", []))
        rel_ids = [r for r in rels if r in by_id]
        rels_html = ""
        if rel_ids:
            items = "".join(
                f'<li>▸ <a href="{prop_link(by_id[r])}">{esc(by_id[r]["tipo"])} {by_id[r]["numero"]}/{by_id[r]["ano"]} — {esc(by_id[r]["titulo"])}</a></li>'
                for r in sorted(set(rel_ids)))
            total = p.get("total_apensados")
            note = ""
            rels_html = "<ul class=\"plain\">" + items + "</ul>" + note
        elif p.get("relacionamentos"):
            rels_html = "<p>" + esc("; ".join(p["relacionamentos"])) + "</p>"

        extra_sections = ""
        for key, heading in [("obrigacoes_criadas", "Obrigações criadas"), ("proibicoes", "Proibições"), ("orgaos_responsaveis", "Órgãos responsáveis pela fiscalização")]:
            if p.get(key):
                extra_sections += f'<div class="kv" style="margin-bottom:12px"><dt style="font-size:12px">{heading}</dt><dd>{esc(p[key])}</dd></div>'

        tl_html = "".join(
            f'<div class="tl-item"><div class="date">{fmt_date(t["data"])}</div>'
            f'<div class="desc">{esc(t["evento"])}</div>'
            f'<div class="src"><a href="{t["fonte"]}" target="_blank" rel="noopener">fonte ↗</a></div></div>'
            for t in p.get("timeline", []))
        if tl_html:
            tl_html = '<div class="timeline">' + tl_html + "</div>"
        else:
            tl_html = "<p style='color:var(--muted)'>Timeline a ser construída nas próximas execuções do monitoramento.</p>"

        fonts_extra = "".join(
            f'<li>▸ <a href="{f["url"]}" target="_blank" rel="noopener">{esc(f["titulo"])}</a></li>'
            for f in p.get("fontes_adicionais", []))

        cats_html = " ".join(f'<span class="tag cat">{esc(cats[c]["nome"])}</span>' for c in p.get("categorias", []) if c in cats)

        recent = changes_for_prop(p["id"], updates)[:5]
        if recent:
            recent_html = "".join(
                f'<div class="change-item"><div class="when">{esc(rel_label(m["data"]))} · {fmt_date(m["data"])}'
                + (f' · {esc(m["tipo"])}' if m.get("tipo") else "")
                + f'</div><h3>{esc(m["titulo"])}</h3><p>{esc(m["descricao"])}</p>'
                f'<p class="change-links"><a href="{m["fonte_url"]}" target="_blank" rel="noopener">{fonte_label(m["fonte_url"])}</a></p></div>'
                for m in recent
            )
        else:
            recent_html = "<p style='color:var(--muted)'>Nenhuma mudança registrada para este procedimento desde o início do monitoramento. O histórico completo está na página de <a href=\"" + SITE_URL + "/atualizacoes/\">atualizações</a>.</p>"

        review_note = ""
        if p.get("revisao_pendente"):
            review_note = ('<div class="note warn"><b>Aguardando curadoria:</b> registro criado automaticamente a partir '
                           "das fontes oficiais da União Europeia e ainda não revisado editorialmente. Título, categorias e "
                           "score são preliminares. Confira sempre a ficha oficial.</div>")

        impacto = p.get("impacto", {})
        detalhe = impacto.get("detalhe")
        if detalhe:
            det_rows = "".join(f"<li>{esc(k.replace('_', ' ').title())}: <b>{v}</b></li>" for k, v in detalhe.items())
            score_note = f"<details class='score-detail'><summary>Ver composição do score (automático)</summary><ul>{det_rows}</ul></details>"
        else:
            score_note = "<p class='score-note'>Score atribuído na curadoria de referência (rúbrica pública na <a href=\"" + SITE_URL + "/metodologia/\">metodologia</a>).</p>"

        body = f"""
<div class="page-head prop-page"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › <a href="{SITE_URL}/procedimentos-legislativos/">Procedimentos</a> › {esc(p.get("procedimento") or f'{p["tipo"]} {p["numero"]}/{p["ano"]}')}</div>
  <div class="identity">
    <div style="flex:1;min-width:260px">
      <h1>{esc(p["tipo"])} {p["numero"]}/{p["ano"]}</h1>
      <p class="sub" style="font-size:17px;color:var(--text);font-weight:600">{esc(p["titulo"])}</p>
      <p class="sub">{esc(p["ementa"])}</p>
      <div style="margin-top:10px"><span class="tag {cls}">{lbl}</span> {cats_html}</div>
    </div>
    <div class="score-box">
      <div class="big" style="color:var(--{'accent' if impacto.get('score', 0) >= 75 else 'accent-2' if impacto.get('score', 0) >= 50 else 'muted'})">{impacto.get("score", "—")}</div>
      <div class="cls">AI Legislative<br>Impact Score</div>
      <div class="score-badge {score_class(impacto.get('score', 0))}" style="margin-top:8px">{esc(impacto.get("classificacao", ""))}</div>
    </div>
  </div>
</div></div>
<section class="block"><div class="wrap">
  {review_note}
  <h2 class="section-title">O que mudou recentemente</h2>
  <p class="section-sub">Últimas mudanças detectadas para este procedimento.</p>
  {recent_html}
</div></section>
<section class="block"><div class="wrap">
  <span class="eyebrow">FATO OFICIAL · REGISTRO DO MONITOR</span>
  <h2 class="section-title">Identificação e tramitação</h2>
  <p class="section-sub">Dados confirmados em fonte oficial nesta execução. Campos não confirmados não são exibidos.</p>
  <div class="dl-grid">{kv_html}</div>
  <p style="margin-top:12px;font-size:13.5px"><a href="{esc(p["url_oficial"])}" target="_blank" rel="noopener">Abrir ficha oficial do procedimento ↗</a></p>
</div></section>
<section class="block"><div class="wrap">
  <span class="eyebrow">SÍNTESE EDITORIAL / INTERPRETAÇÃO</span>
  <h2 class="section-title">Resumo objetivo</h2>
  <p style="max-width:860px">{esc(p.get("resumo", p["ementa"]))}</p>
  {extra_sections}
  <div class="note" style="margin-top:16px"><b>Chance de impacto regulatório:</b> {esc(p.get("chance_impacto_regulatorio", "—"))}</div>
  {score_note}
</div></section>
{business_html(p)}
<section class="block"><div class="wrap">
  <h2 class="section-title">Documentos e textos</h2>
  <ul class="plain">{docs_html or '<li>—</li>'}</ul>
</div></section>
<section class="block"><div class="wrap">
  <h2 class="section-title">Procedimentos relacionados</h2>
  {rels_html or "<p style='color:var(--muted)'>Nenhuma relação formal registrada (dossiê independente).</p>"}
</div></section>
<section class="block"><div class="wrap">
  <h2 class="section-title">Timeline do procedimento</h2>
  {tl_html}
</div></section>
<section class="block"><div class="wrap">
  <h2 class="section-title">Fontes</h2>
  <ul class="plain">
    <li>▸ <a href="{esc(p["url_oficial"])}" target="_blank" rel="noopener">{esc(p["tipo"])} {p["numero"]}/{p["ano"]} — fonte oficial</a></li>
    {fonts_extra}
  </ul>
  <p class="disclaimer" style="margin-top:12px">{DISCLAIMER}</p>
</div></section>"""
        article_ld = {
            "@type": "Article",
            "headline": f'{p["tipo"]} {p["numero"]}/{p["ano"]} — {p["titulo"]}',
            "description": p["ementa"][:300],
            "url": prop_link(p),
            "dateModified": EXECUTION_DATE,
            "inLanguage": "pt-BR",
            "about": "Regulação de inteligência artificial da União Europeia",
            "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE_URL + "/"},
        }
        jsonld = combine_ld(
            article_ld,
            ld_breadcrumbs([("Início", ""), ("Procedimentos", "procedimentos-legislativos/"),
                            (p.get("procedimento") or f'{p["tipo"]} {p["numero"]}/{p["ano"]}', None)]))
        write(prop_fs_path(p["id"]), page(
            seo_title_prop(p), seo_desc_prop(p),
            prop_fs_path(p["id"]).replace("index.html", ""), body, og_type="article", jsonld=jsonld))


def build_updates(props, updates):
    by_id = {p["id"]: p for p in props}
    mudancas = sorted(updates.get("mudancas", []), key=lambda m: m["data"], reverse=True)
    items = []
    for m in mudancas:
        n = days_ago(m.get("data"))
        n = 9999 if n is None else n
        href, rotulo = change_prop_href(m, by_id)
        items.append(
            f'<div class="change-item" data-update data-days="{n}">'
            f'<div class="when">{esc(rel_label(m["data"]))} · {fmt_date(m["data"])}'
            + (f' · {esc(m["tipo"])}' if m.get("tipo") else "")
            + f'</div><h3><a href="{href}">{esc(m["titulo"])}</a></h3>'
            f'<p>{esc(m["descricao"])}</p>'
            f'<p class="change-links"><a href="{href}">Ver {esc(rotulo)} →</a> · '
            f'<a href="{m["fonte_url"]}" target="_blank" rel="noopener">{fonte_label(m["fonte_url"])}</a></p></div>'
        )
    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Atualizações</div>
  <h1>O que mudou na regulação de IA</h1>
  <p class="sub">Histórico cronológico das mudanças detectadas pelo monitoramento — eventos de procedimento, situação, relatoria, votações, assinatura, publicação no JO e novos dossiês. Ordenado pela data do evento (registros incorporados trazem a data original). Cada item aponta para o procedimento e para a fonte oficial.</p>
</div></div>
<section class="block"><div class="wrap">
  <div class="update-filters" role="group" aria-label="Filtrar por período">
    <button data-ufilter="0" class="uf-btn">Hoje</button>
    <button data-ufilter="7" class="uf-btn active">Últimos 7 dias</button>
    <button data-ufilter="30" class="uf-btn">Últimos 30 dias</button>
    <button data-ufilter="all" class="uf-btn">Todas</button>
  </div>
  <p id="u-count" style="color:var(--muted);font-size:13px;margin-bottom:14px"></p>
  {"".join(items) or '<div class="note">Nenhuma mudança registrada ainda.</div>'}
  <p class="disclaimer" style="margin-top:16px">{DISCLAIMER}</p>
</div></section>"""
    jsonld = combine_ld(
        ld_collection("Atualizações da regulação de IA na União Europeia",
                      "Histórico cronológico das mudanças legislativas e regulatórias de inteligência artificial detectadas pelo monitoramento.",
                      "atualizacoes/"),
        ld_breadcrumbs([("Início", ""), ("Atualizações", None)]))
    write("atualizacoes/index.html", page(
        "Atualizações da regulação de IA na União Europeia — o que mudou",
        "Histórico cronológico do monitoramento de IA da União Europeia: mudanças de hoje, dos últimos 7 e 30 dias — eventos de procedimento, votações, assinatura, publicação no JO e novos dossiês, com fonte oficial.",
        "atualizacoes/", body, jsonld=jsonld))


def build_metodologia(props, laws, updates):
    rs = run_summary()
    rubric_rows = "".join(
        f"<tr><td><b>{n}</b></td><td>0–{v}</td><td>{d}</td></tr>"
        for n, v, d in [
            ("Abrangência regulatória", 20, "Quadro horizontal da UE/AI Act (20) · pilar setorial amplo (12) · tema pontual (6) · simbólico (0–2)"),
            ("Estágio do procedimento", 15, "Publicado no JO/aplicável (15) · assinado (13) · adotado pelo plenário (12) · acordo provisório (11) · trílogos (10) · posição 1ª leitura (9) · relatório em comissão (8) · em comissão (6) · encaminhamento (4) · sem confirmação (2)"),
            ("Próximas datas aplicáveis", 10, "Data de aplicação/obrigação confirmada (10) · votação em pauta (10) · trílogos ativos (6) · agenda não confirmada (2)"),
            ("Regime do procedimento", 10, "Ato delegado/de execução (8) · legislativo ordinário COD (5) · especial CNS/CONS (5) · não legislativo NLE/INI (3) · resolução (2)"),
            ("Densidade do dossiê", 5, "5+ documentos oficiais (5) · 3–4 (3) · 1–2 (1) · nenhum (0)"),
            ("Impacto econômico", 15, "Mercado único/sanções milionárias (15) · custos p/ provedores e utilizadores (9) · moderado (5) · baixo (0–2)"),
            ("Impacto sobre direitos", 10, "Direitos fundamentais/dados/práticas proibidas (10) · trabalho/consumidor/saúde (6) · indireto (3) · nenhum (0)"),
            ("Alcance setorial", 5, "Multissetorial (5) · 2–3 setores (3) · 1 setor (1)"),
            ("Relevância institucional", 10, "Cria/governa autoridade da UE (10) · altera competências relevantes (6) · pontual (3) · nenhum (0)"),
        ])
    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Metodologia</div>
  <h1>Metodologia do monitoramento</h1>
  <p class="sub">Como coletamos, validamos e publicamos a legislação e a regulação de IA da União Europeia — com fontes, critérios, frequência e limitações declaradas.</p>
</div></div>
<section class="block"><div class="wrap">
  <h2 class="section-title">Fontes utilizadas</h2>
  <ul class="plain facts">
    <li>▸ <b>Parlamento Europeu</b> — Open Data Portal, API oficial v2 (procedimentos, eventos de procedimento, estágios, votações, assinatura e publicação no JO; JSON-LD) e <b>Legislative Train Schedule</b>. <code>/scripts/sources/eu_parliament.py</code></li>
    <li>▸ <b>EUR-Lex / Jornal Oficial da UE</b> — busca oficial pública (metadados de atos: CELEX, ELI, JO, status) e RSS oficial de publicações. <code>/scripts/sources/eurlex.py</code></li>
    <li>▸ <b>Conselho da UE</b> — registro público de documentos (últimos documentos, documentos legislativos preparatórios, com número de arquivo interinstitucional). <code>/scripts/sources/eu_council.py</code></li>
    <li>▸ <b>Comissão Europeia</b> — Press Corner (RSS oficial) e portal <b>Have Your Say</b> (consultas públicas e calls for evidence, com período de feedback). <code>/scripts/sources/eu_commission.py</code></li>
    <li>▸ <b>European AI Office</b> — portal digital-strategy da Comissão: implementação do AI Act, GPAI, códigos de prática e guidelines. <code>/scripts/sources/ai_office.py</code></li>
    <li>▸ <b>EDPB</b> — RSS oficial (notícias, guidelines adotadas, decisões coordenadas sobre IA/dados). <code>/scripts/sources/edpb.py</code></li>
    <li>▸ <b>EDPS</b> — press releases, notícias e publicações oficiais (opiniões e guidelines). <code>/scripts/sources/edps.py</code></li>
    <li>▸ <b>Bloqueio/indisponibilidade:</b> quando uma fonte oficial não responde ou muda de layout, o canal é registrado como <b>falho</b> no painel — a falha fica explícita, nunca escondida, e nada é preenchido com dado estimado.</li>
    <li>▸ <b>Imprensa</b> — apenas comunicados oficiais das próprias instituições (Press Corner do Parlamento/Comissão/Conselho); nunca imprensa de terceiros como fonte primária.</li>
  </ul>
  <h2 class="section-title" style="margin-top:26px">Frequência de atualização</h2>
  <p>Coleta automática <b>diária</b> (GitHub Action, horário de Bruxelas) com rebuild e validação do site. Última execução: <b>{rs["data"]}</b> às <b>{rs["hora"]}</b> — {rs["verificadas"]} fichas de procedimento verificadas, {rs["mudancas"]} mudanças detectadas. Execuções sem mudança relevante registram apenas a verificação.</p>
  <h2 class="section-title" style="margin-top:26px">Critérios de inclusão</h2>
  <ul class="plain facts">
    <li>▸ Procedimentos legislativos e não legislativos das instituições da UE sobre IA e temas correlatos: AI Act e seus atos delegados/de execução, IA generativa e modelos de uso geral (GPAI), deepfakes e conteúdo sintético, decisão automatizada, biometria e reconhecimento facial, plataformas digitais, dados pessoais, cibersegurança, computação/semicondutores e impactos setoriais (trabalho, direitos de autor, educação, saúde, defesa, segurança, eleições).</li>
    <li>▸ Legislação da UE diretamente relacionada a IA com efeito sobre sistemas de IA — laws.json contém apenas atos com relação direta (AI Act e correlatos), não o acervo digital completo.</li>
    <li>▸ Descobertas automáticas entram com flag <b>“aguardando curadoria”</b> e score preliminar conservador (nunca CRÍTICO automático). Falsos positivos são removidos na revisão.</li>
  </ul>
  <h2 class="section-title" style="margin-top:26px">AI Legislative Impact Score (0–100)</h2>
  <p>O score mede <b>importância regulatória para o monitoramento</b>, não mérito. Rúbrica pública e reproduzível (implementada em <code>scripts/scoring.py</code>):</p>
  <div style="overflow-x:auto;margin-top:12px"><table class="tbl"><thead><tr><th>Critério</th><th>Pontos</th><th>Como pontuar (resumo)</th></tr></thead><tbody>{rubric_rows}</tbody></table></div>
  <p style="margin-top:12px">Faixas: <b>90–100 CRÍTICO · 75–89 MUITO RELEVANTE · 60–74 RELEVANTE · 40–59 MONITORAR · 0–39 BAIXA PRIORIDADE</b>. O score mede apenas <b>impacto regulatório</b> — nunca aprovação, probabilidade ou posição política. Scores da curadoria de referência são preservados; scores nunca são inflados para gerar manchetes.</p>
  <h2 class="section-title" style="margin-top:26px">Como mudanças são detectadas</h2>
  <p>Antes de sobrescrever qualquer registro, o coletor compara o <b>estado anterior</b> (dataset versionado) com o <b>estado coletado</b> nas fontes oficiais. Cada alteração relevante gera um registro em <code>updates.json</code> com procedimento, campo alterado, valor anterior e novo, data do evento, data da detecção, fonte, URL oficial e timestamp da execução. Tipos monitorados: eventos de procedimento (encaminhamento, relatório, parecer, debate, emendas, votação, negociações interinstitucionais, acordo provisório), situação, relatoria, assinatura, publicação no JO, novos documentos oficiais e novos procedimentos. A identidade de cada dossiê é o <b>número de procedimento interinstitucional</b> (ex.: 2021/0106(COD)), compartilhado entre Parlamento, Conselho e Comissão — nunca o título.</p>
  <h2 class="section-title" style="margin-top:26px">Limitações</h2>
  <ul class="plain facts">
    <li>▸ Publicações no JO e eventos de procedimento podem levar horas ou dias para se refletir na API oficial; a confirmação final é sempre a ficha oficial e o texto publicado no EUR-Lex.</li>
    <li>▸ A API v2 do Parlamento não expõe documentos de reuniões (agenda de plenos/comissões) em formato público estável — a agenda futura do monitor usa as consultas oficiais do portal Have Your Say (limitação declarada).</li>
    <li>▸ O <b>EU Law Tracker</b> (law-tracker.europa.eu) exige autenticação para uso interativo e não possui API pública estável documentada; por isso não é usado como conector automático — o estado dos dossiês vem da API do Parlamento e do registro público do Conselho.</li>
    <li>▸ Itens de fontes regulatórias (AI Office, EDPB, EDPS, Comissão) são detectados automaticamente e entram marcados como <b>aguardando curadoria</b> quando o sinal temático é duvidoso; a confirmação jurídica final é sempre o texto oficial.</li>
    <li>▸ O monitoramento multiórgão é conservador por desenho: item sem sinal temático claro é descartado, item duvidoso entra como <b>revisar</b>, e órgão que não respondeu aparece como <b>falha</b> no painel — nunca como monitorado.</li>
    <li>▸ Registros automáticos (“aguardando curadoria”) podem conter título preliminar e categorias incompletas.</li>
  </ul>
  <h2 class="section-title" style="margin-top:26px">Política de correção</h2>
  <p>Erros são corrigidos no dataset com registro da correção em <code>updates.json</code> (nunca sobrescrita silenciosa). O histórico versionado no Git permite auditar qualquer alteração. <b>{DISCLAIMER}</b></p>
  <h2 class="section-title" style="margin-top:26px">Automação, orçamento de tempo e auditoria</h2>
  <p>A coleta roda <b>diariamente</b> (agendamentos da GitHub Action em horário compatível com Bruxelas; sujeitos a atraso do GitHub) com <b>orçamento de tempo</b> declarado:
  ao se aproximar do teto, o coletor para de iniciar novas consultas, grava o que já verificou e
  registra a execução como <b>parcial</b> — a cobertura de cada execução fica visível no
  <a href="{SITE_URL}/monitoramento/">painel de monitoramento</a>. A verificação segue ordem de
  prioridade (maior AI Legislative Impact Score primeiro; em empate, a matéria há mais tempo sem
  verificação), de modo que o excedente de uma execução é sempre o de menor prioridade e entra
  primeiro na seguinte. Fichas novas descobertas nas APIs entram com teto por execução, priorizando
  relevância temática, tipo de procedimento e recência.</p>
  <p style="margin-top:10px">Cada execução registra no <code>updates.json</code>: início e fim,
  duração, orçamento, cobertura, proposições pendentes, mudanças detectadas, novas proposições,
  chamadas HTTP (total, cache, falhas, tempo por endpoint e por fase), erros e a fotografia do banco
  ao final. O painel <a href="{SITE_URL}/monitoramento/">/monitoramento/</a> publica essas métricas
  a cada rebuild e recalcula no navegador a idade da última execução: <b>se o cron parar, o site
  avisa</b>. As mesmas métricas ficam em <code>data/monitoramento.json</code> para uso externo.</p>

  <h2 class="section-title" style="margin-top:26px">Monitoramento multiórgão: status por fonte</h2>
  <p>Cada execução consulta <b>sete fontes regulatórias obrigatórias</b> — European AI Office, EUR-Lex,
  Conselho da UE, Comissão Europeia, Parlamento Europeu, EDPB e EDPS — além do motor legislativo
  (Parlamento — Open Data Portal v2; EUR-Lex) — e grava, em <code>updates.json</code> (campo <code>fontes_monitoradas</code>),
  para cada órgão: <b>timestamp da última tentativa</b>, <b>timestamp da última execução
  bem-sucedida</b>, <b>status</b>, <b>itens consultados</b>, <b>novidades</b>, <b>erros</b> e os
  <b>endpoints oficiais</b> usados. O campo <code>status_global</code> resume o resultado:</p>
  <ul class="plain facts">
    <li>▸ <b>OK</b> — todos os órgãos obrigatórios consultados com sucesso.</li>
    <li>▸ <b>PARCIAL</b> — pelo menos uma fonte falhou; o dataset preserva o último estado verificado e a falha fica registrada e visível no <a href="{SITE_URL}/monitoramento/">painel</a>.</li>
    <li>▸ <b>FALHA</b> — execução incapaz de produzir dados confiáveis; nesse caso o workflow <b>não publica</b> (nenhum commit é feito com dados não confiáveis).</li>
  </ul>
  <p style="margin-top:10px">Cada fonte roda em um subprocesso com timeout próprio e retentativas: uma fonte lenta ou bloqueada
  não impede as outras, os resultados já coletados são persistidos e o erro é registrado no painel. Os itens desses
  órgãos ficam em <code>data/legislation/atos.json</code>, com URL oficial, fonte, data do evento, data de detecção
  e a execução responsável; alterações de texto ou de status de um item já conhecido geram novo registro em
  <code>updates.json</code> (histórico por item, sem sobrescrita silenciosa). O arquivo histórico completo de
  mudanças é rotacionado para <code>data/legislation/updates_arquivo.json</code> em vez de ser descartado.</p>
  <h2 class="section-title" style="margin-top:26px">Cobertura atual</h2>
  <p>{len(props)} procedimentos monitorados · {len(laws)} atos mapeados · {len(updates.get("mudancas", []))} mudanças registradas · última execução em {rs["data"]}.</p>
  <p style="margin-top:6px">Status global da última execução: <b>{(EXECUTION_RUN or {}).get("status_global") or "—"}</b> · fontes monitoradas: {len((EXECUTION_RUN or {}).get("fontes_monitoradas") or {})}.</p>
</div></section>"""
    jsonld = combine_ld(
        ld_collection("Metodologia do Monitor UE de IA",
                      "Fontes, frequência, critérios de inclusão, AI Legislative Impact Score, detecção de mudanças, limitações e política de correção.",
                      "metodologia/"),
        ld_breadcrumbs([("Início", ""), ("Metodologia", None)]))
    write("metodologia/index.html", page(
        "Metodologia — como monitoramos a regulação de IA da União Europeia",
        "Metodologia do Monitor UE de IA: fontes oficiais (Parlamento Europeu, EUR-Lex, Conselho, Comissão, AI Office, EDPB, EDPS), frequência diária, critérios de inclusão, AI Legislative Impact Score, detecção de mudanças e limitações.",
        "metodologia/", body, jsonld=jsonld))


def build_laws(laws):
    rows = "".join(
        f'<tr><td><b>{esc(l["tipo"])} {esc(l["numero"])}</b><br><small style="color:var(--muted)">{fmt_date(l["data"])}</small></td>'
        f'<td><b>{esc(l["nome"])}</b><br><span style="color:var(--muted);font-size:13px">CELEX {esc(l.get("celex", "—"))}{(" · " + esc(l["jornal_oficial"])) if l.get("jornal_oficial") else ""}</span></td>'
        f'<td style="font-size:13px">{esc((l.get("relacao_ia") or "")[:320])}</td>'
        f'<td><span class="tag">{esc(l["status"])}</span></td>'
        f'<td><a href="{l["url"]}" target="_blank" rel="noopener">link ↗</a></td></tr>'
        for l in sorted(laws, key=lambda x: x["data"] or "", reverse=True))
    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Legislação e atos</div>
  <h1>Legislação e atos da UE relacionados à IA</h1>
  <p class="sub">Atos jurídicos da União Europeia diretamente relacionados à inteligência artificial — AI Act e atos correlatos — com CELEX, referência do Jornal Oficial e status de vigência. Não é o acervo digital completo: só o que disciplina IA.</p>
</div></div>
<section class="block"><div class="wrap" style="overflow-x:auto">
  <table class="tbl">
    <thead><tr><th>Ato</th><th>Nome oficial</th><th>Relação com IA</th><th>Status</th><th>Fonte</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p class="disclaimer" style="margin-top:16px">{DISCLAIMER}</p>
</div></section>"""
    jsonld = combine_ld(
        ld_collection("Legislação e atos da UE sobre IA",
                      "Atos jurídicos da União Europeia diretamente relacionados à inteligência artificial: AI Act (Regulamento (UE) 2024/1689) e atos correlatos, com CELEX e fonte oficial.",
                      "legislacao-e-atos/"),
        ld_breadcrumbs([("Início", ""), ("Legislação e atos", None)]))
    write("legislacao-e-atos/index.html", page(
        "AI Act e legislação da UE sobre IA — atos vigentes, CELEX e status",
        "Legislação da União Europeia diretamente relacionada à inteligência artificial: AI Act (Regulamento (UE) 2024/1689) e atos correlatos, com CELEX, Jornal Oficial, status de vigência e fonte oficial.",
        "legislacao-e-atos/", body, jsonld=jsonld))


def build_timeline(timeline):
    items = sorted(timeline["eventos"], key=lambda e: e["data"] or "", reverse=True)
    tl = "".join(
        f'<div class="tl-item"><div class="date">{fmt_date(e["data"])} · {esc(e["casa"])}</div>'
        f'<div class="desc"><b>{esc(e["titulo"])}</b> — {esc(e["descricao"])}</div>'
        f'<div class="src">{("Dossiê: " + esc(e["proposicao"]) + " · ") if e.get("proposicao") else ""}<a href="{e["fonte_url"]}" target="_blank" rel="noopener">{esc(e["fonte_titulo"])} ↗</a></div></div>'
        for e in items)
    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Timeline</div>
  <h1>Timeline da regulação de IA na União Europeia</h1>
  <p class="sub">Histórico cronológico documentado — da proposta do AI Act (2021) à aplicação integral (2026). Cada evento traz instituição, dossiê e fonte oficial.</p>
</div></div>
<section class="block"><div class="wrap">
  <div class="timeline">{tl}</div>
</div></section>"""
    jsonld = combine_ld(
        ld_collection("Timeline da regulação de IA na União Europeia (2021–2026)",
                      "Linha do tempo documentada da regulação de inteligência artificial da União Europeia: do AI Act à implementação.",
                      "timeline/"),
        ld_breadcrumbs([("Início", ""), ("Timeline", None)]))
    write("timeline/index.html", page(
        "Timeline da regulação de IA na União Europeia (2021–2026)",
        "Linha do tempo documentada da regulação de IA da União Europeia: proposta do AI Act, trílogos, adoção, publicação no JO, entrada em vigor e aplicação faseada.",
        "timeline/", body, jsonld=jsonld))


def build_parliamentarians(parms, props):
    by_id = {p["id"]: p for p in props}
    cards = ""
    for m in parms:
        props_links = "".join(
            f'<a href="{prop_link(by_id[pid])}">{esc(by_id[pid]["tipo"])} {by_id[pid]["numero"]}/{by_id[pid]["ano"]}</a>'
            for pid in m.get("proposicoes_relacionadas", []) if pid in by_id)
        atu = "".join(f"<li>{esc(a)}</li>" for a in m.get("atuacao_ia", []))
        fonts = "".join(f'<li><a href="{f["url"]}" target="_blank" rel="noopener">{esc(f["titulo"])} ↗</a></li>' for f in m.get("fontes", []))
        casa = m.get("casa") or "Parlamento Europeu"
        cards += f"""
<div class="card">
  <h3>{esc(m["nome"])} <span class="tag">{esc(m["partido"])}-{esc(m["estado"])}</span> <span class="tag">{casa}</span></h3>
  <p><b>{esc(m["papel"])}</b></p>
  <ul class="plain" style="margin:10px 0 10px 0;color:var(--muted);font-size:13.5px">{atu}</ul>
  <p style="font-size:13px"><b>Matérias:</b> {props_links or "—"}</p>
  <p style="font-size:12.5px;margin-top:8px;color:var(--muted)">Fontes: {fonts}</p>
</div>"""
    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Atores legislativos</div>
  <h1>Atores legislativos da IA na União Europeia</h1>
  <p class="sub">Mapa de relatoria e condução dos dossiês de IA no Parlamento Europeu e nas demais instituições. Papéis só são registrados quando documentados em fonte oficial — não atribuímos juízo político sem fonte.</p>
</div></div>
<section class="block"><div class="wrap">
  <div class="grid cols-2">{cards}</div>
</div></section>"""
    jsonld = combine_ld(
        ld_collection("Atores legislativos da IA na União Europeia",
                      "Co-relatores, comissões e instituições que conduzem os dossiês de inteligência artificial no Parlamento Europeu e nas instituições da UE.",
                      "atores-legislativos/"),
        ld_breadcrumbs([("Início", ""), ("Atores legislativos", None)]))
    write("atores-legislativos/index.html", page(
        "Atores legislativos da IA na União Europeia — relatores e instituições",
        "Co-relatores, comissões e instituições que conduzem os dossiês de inteligência artificial na União Europeia (Parlamento Europeu, Comissão, Conselho), com atuação documentada em fonte oficial.",
        "atores-legislativos/", body, jsonld=jsonld))


def build_agenda(events):
    groups = {
        "proximos_7_dias": ("Próximos 7 dias", []),
        "proximos_30_dias": ("Próximos 30 dias", []),
        "sem_data_confirmada": ("Sem data confirmada (marcos previstos)", []),
    }
    for e in events["eventos"]:
        g = groups.get(e.get("janela"))
        if g:
            g[1].append(e)

    html = ""
    for key, (label, evts) in groups.items():
        if not evts:
            continue
        items = "".join(
            f'<div class="card"><h3>{esc(e["titulo"])}</h3>'
            f'<p><b>{fmt_date(e.get("data_inicio"))}{(" a " + fmt_date(e["data_fim"])) if e.get("data_fim") and e["data_fim"] != e.get("data_inicio") else ""}</b>'
            + (f' · {esc(e["hora"])}' if e.get("hora") else "") + f' · {esc(e["casa"])}'
            + (' <span class="tag review">Revisão pendente</span>' if e.get("origem") == "descoberta_automatica" else "")
            + f'</p>'
            f'<p><b>Local:</b> {esc(e.get("local", "—"))} · <b>Tipo:</b> {esc(e["tipo"])}</p>'
            f'<p>{esc(e["tema"])}</p>'
            f'<p style="margin-top:8px"><b>Relação com IA:</b> {esc(e["relacao_ia"])}</p>'
            f'<p style="margin-top:8px;font-size:12.5px"><a href="{e["fonte_url"]}" target="_blank" rel="noopener">{esc(e["fonte_titulo"])} ↗</a></p></div>'
            for e in evts)
        html += f'<div class="agenda-group"><h3>{label}</h3><div class="grid cols-2">{items}</div></div>'

    v = events.get("verificacao") or {
        "data": EXECUTION_DATE,
        "resultado": ("Agenda ainda não verificada por execução automática — "
                      "cada evento traz a fonte oficial de verificação."),
    }
    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Agenda</div>
  <h1>Agenda da regulação de IA na UE</h1>
  <p class="sub">Eventos futuros oficialmente documentados: consultas públicas com prazo de feedback (Comissão — Have Your Say) e marcos de aplicação do AI Act. Verificada em {fmt_date(v["data"])}.</p>
</div></div>
<section class="block"><div class="wrap">
  <div class="note warn"><b>Hoje ({fmt_date(v["data"])}):</b> {esc(v["resultado"])}</div>
  {html}
</div></section>"""
    jsonld = combine_ld(
        ld_collection("Agenda da regulação de IA na União Europeia",
                      "Agenda oficial de consultas públicas e marcos de aplicação do AI Act: prazos de feedback, datas de aplicabilidade e eventos documentados.",
                      "agenda/"),
        ld_breadcrumbs([("Início", ""), ("Agenda", None)]))
    write("agenda/index.html", page(
        "Agenda da regulação de IA na UE — consultas e marcos de aplicação",
        "Agenda oficial da regulação de IA na União Europeia: consultas públicas em andamento (Have Your Say), prazos de feedback e marcos de aplicabilidade do AI Act.",
        "agenda/", body, jsonld=jsonld))


def build_report(props, laws, updates, events):
    run = (updates.get("execucoes") or [{}])[0] or {}
    top5 = [
        ("Aplicação integral do AI Act a partir de 2 de agosto de 2026",
         "Com a entrada da fase de sistemas de alto risco (36 meses após a entrada em vigor), o AI Act (Regulamento (UE) 2024/1689) atinge aplicação integral da maioria das regras — e a Comissão anunciou o início da aplicação das novas regras de transparência na mesma data (comunicado de 31/07/2026)."),
        ("Plataformas e IA generativa sob o DSA: ChatGPT, Reddit e Roblox designados",
         "Em 31/08/2026 a Comissão designou novos serviços sob o Digital Services Act, estendendo as obrigações de transparência e gestão de riscos a plataformas com forte componente de IA generativa."),
        ("Parlamento aprova resolução sobre direitos de autor e IA generativa",
         "Em 10 de março de 2026 o Plenário adotou a resolução 'Copyright and generative artificial intelligence' (2025/2058(INI); P10_TA(2026)0066), sinalizando o debate sobre a política de conformidade de direitos de autor do art. 53 do AI Act."),
        ("Enforcement de dados e IA nas autoridades nacionais sob coordenação do EDPB",
         "O EDPB registra decisões relevantes em 2026 — entre elas multas da CNIL francesa a EXTIA (€300 mil, 11/09/2026) e ao Hôpital Privé de la Loire (€500 mil, 09/09/2026) — mostrando o regime de dados como complemento aplicado do AI Act."),
        ("Consulta pública sobre infraestrutura de dados de saúde (EHDS/HealthData@EU)",
         "A Comissão mantém aberto até 29/09/2026 o feedback sobre requisitos técnicos do HealthData@EU — infraestrutura de dados que fundamenta aplicações de IA na saúde na UE."),
    ]
    top5_html = "".join(
        f'<div class="change-item"><div class="when">#{i+1}</div><h3>{esc(t)}</h3><p>{esc(d)}</p></div>'
        for i, (t, d) in enumerate(top5))

    facts = [
        "O AI Act foi adotado pelo Parlamento em 13/03/2024 com 523 votos a favor, 46 contra e 49 abstenções (TA-9-2024-0138), e aprovado definitivamente pelo Conselho em 21/05/2024 (fichas oficiais e comunicados institucionais).",
        "O procedimento interinstitucional é o 2021/0106(COD), com proposta da Comissão (COM/2021/206 final) e co-relatoria de Brando Benifei (S&D/IMCO) e Dragoș Tudorache (Renew/LIBE).",
        "O Regulamento (UE) 2024/1689 foi publicado no JO L de 12/07/2024, entrou em vigor em 01/08/2024 e tem aplicação faseada: proibições (02/02/2025), GPAI (02/08/2025) e sistemas de alto risco/aplicação integral (02/08/2026) — datas documentadas nos comunicados oficiais.",
        "A versão consolidada do AI Act no EUR-Lex reflete alterações posteriores à publicação original (consolidada em 27/07/2026), típica do processo de corrigendas.",
        "O Parlamento adotou em 10/03/2026 a resolução sobre direitos de autor e IA generativa (2025/2058(INI); P10_TA(2026)0066), registrada no EUR-Lex.",
        "A Comissão anunciou (31/07/2026) o início da aplicação das regras do AI Act e das novas regras de transparência a partir de 2 de agosto de 2026, e designou (31/08/2026) ChatGPT, Reddit e Roblox sob o DSA.",
        "O EDPB publica em seu feed oficial as decisões recentes do enforcement de dados na UE, incluindo multas da CNIL em setembro de 2026 (EXTIA €300 mil; Hôpital Privé de la Loire €500 mil).",
    ]
    interps = [
        "O centro de gravidade regulatório mudou: com a aplicação integral concluída em agosto de 2026, o debate migra da legislação para a implementação — guidelines, códigos de prática de GPAI, market surveillance e enforcement.",
        "A European AI Office torna-se o ator mais observado do ecossistema: é dela que saem os atos e práticas que detalham as obrigações de modelos de uso geral, e cada publicação sua tem efeito extraterritorial sobre provedores.",
        "A relação entre AI Act e GDPR será testada no enforcement: decisões recentes do EDPB/CNIL sobre dados e sistemas de IA indicam aplicação coordenada dos dois regimes.",
        "Direitos de autor e treinamento de modelos é o conflito não resolvido do ecossistema GPAI — a resolução de março de 2026 indica que o Parlamento voltará ao tema, potencialmente em revisão do AI Act.",
        "Atos delegados e de execução (REG) tenderão a dominar o pipeline legislativo de IA nos próximos anos; o monitor cobre esse tipo de procedimento com o mesmo rigor.",
    ]
    run_hour = ""
    m = re.search(r"T(\d{2}:\d{2})", str(run.get("data_hora", "")))
    if m:
        run_hour = f" às {m.group(1)} (BRT)"

    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Relatório</div>
  <h1>Relatório da execução e Estado da Regulação</h1>
  <p class="sub">MONITORING REPORT da execução de {fmt_date(run.get("data_hora"))}{run_hour} e síntese editorial do cenário regulatório. Metodologia completa em <a href="{SITE_URL}/metodologia/">/metodologia/</a>.</p>
</div></div>

<section class="block"><div class="wrap">
  <h2 class="section-title">Estado da regulação de IA na União Europeia — resumo executivo</h2>
  <p class="section-sub">Fatos (com fonte) e interpretação (análise editorial) rigorosamente separados.</p>
  <h3 style="margin:14px 0 8px;font-size:16px">Fatos documentados</h3>
  <ul class="plain facts">{"".join(f"<li>▸ {esc(f)}</li>" for f in facts)}</ul>
  <h3 style="margin:20px 0 8px;font-size:16px">Interpretação editorial</h3>
  <ul class="plain interp">{"".join(f"<li>▸ {esc(i)}</li>" for i in interps)}</ul>
  <div class="note" style="margin-top:18px"><b>Resposta direta:</b> o ato central é o <b>AI Act (Regulamento (UE) 2024/1689)</b> — adotado, publicado e com aplicação faseada concluída em 02/08/2026. O que está "em tramitação" agora são os atos correlatos: atos delegados/de execução, códigos de prática de GPAI e o enforcement coordenado (AI Office, EDPB, autoridades nacionais). Para impacto regulatório imediato, acompanhamos AI Office e EDPB; para o pipeline legislativo, os procedimentos REG e a revisão do quadro de GPAI.</div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Top 5 desenvolvimentos legislativos de IA</h2>
  <p class="section-sub">Ordenados por impacto regulatório nesta execução.</p>
  {top5_html}
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">MONITORING REPORT — execução de {fmt_date(run.get("data_hora"))}{run_hour}</h2>
  <div class="dl-grid" style="grid-template-columns:repeat(auto-fit,minmax(300px,1fr))">
    <div class="kv"><dt>Data/hora da execução</dt><dd>{fmt_date(run.get("data_hora"))}{run_hour}</dd></div>
    <div class="kv"><dt>Procedimentos verificados</dt><dd>{run.get("procedimentos_verificados", run.get("proposicoes_verificadas", "—"))} (fichas oficiais e fontes abertas)</dd></div>
    <div class="kv"><dt>Procedimentos atualizados</dt><dd>{run.get("procedimentos_atualizados", run.get("proposicoes_atualizadas", run.get("novas_proposicoes", "—")))}</dd></div>
    <div class="kv"><dt>Novos procedimentos cadastrados</dt><dd>{run.get("novos_procedimentos", run.get("novas_proposicoes", "—"))}</dd></div>
    <div class="kv"><dt>Mudanças detectadas</dt><dd>{run.get("mudancas_detectadas", "—")}</dd></div>
    <div class="kv"><dt>Novas leis/regulamentos mapeados</dt><dd>{run.get("novas_leis_regulamentos", "—")}</dd></div>
    <div class="kv"><dt>Fontes consultadas</dt><dd>{"".join(esc(s) + "<br>" for s in run.get("fontes_consultadas", []))}</dd></div>
    <div class="kv"><dt>Erros encontrados</dt><dd>{esc("; ".join((run.get("erros") or [])[:5])) or "Nenhum erro de build. Lacunas de dados marcadas explicitamente nos registros."}</dd></div>
  </div>
  <p style="margin-top:12px"><a href="{SITE_URL}/atualizacoes/">Ver histórico completo de atualizações →</a></p>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Metodologia e política de qualidade</h2>
  <ul class="plain facts">
    <li>▸ <b>Fontes primárias obrigatórias:</b> cada fato relevante cita a URL oficial (Parlamento Europeu, EUR-Lex, Conselho, Comissão, AI Office, EDPB, EDPS). Imprensa institucional é usada apenas como fonte complementar citada; nunca imprensa de terceiros como fonte primária.</li>
    <li>▸ <b>Chave primária:</b> número de procedimento interinstitucional normalizado (ex.: ue_2021_0106_cod para o 2021/0106(COD)). Nenhuma duplicata é criada; execuções futuras atualizam os mesmos registros.</li>
    <li>▸ <b>AI Legislative Impact Score (0-100):</b> mede impacto regulatório — abrangência, estágio do procedimento, datas de aplicação confirmadas, regime do procedimento, densidade do dossiê, efeito econômico, impacto sobre direitos, alcance setorial e relevância institucional. Faixas: 90-100 crítico, 75-89 muito relevante, 60-74 relevante, 40-59 monitorar, 0-39 baixa prioridade. <b>Não mede</b> probabilidade de aprovação nem posição política. Scores não são manipulados para inflacionar manchetes.</li>
    <li>▸ <b>Proibido:</b> inventar proposições, tramitações, datas, autores, pareceres, probabilidades ou posições políticas sem evidência documental.</li>
    <li>▸ <b>Controle de alterações:</b> o dataset é versionado no Git; mudanças de situação geram registro em updates.json com status anterior, status novo, data e fonte.</li>
    <li>▸ <b>Execuções futuras:</b> carregar o estado anterior → consultar fontes oficiais → detectar mudanças → atualizar registros e páginas → validar build → publicar. Se nada mudou, registra-se apenas a verificação.</li>
  </ul>
  <p style="margin-top:12px"><a href="{SITE_URL}/metodologia/">Metodologia completa e detalhada →</a></p>
</div></section>"""
    jsonld = combine_ld(
        {"@type": "Article", "headline": "Relatório da execução e Estado da Regulação de IA na União Europeia",
         "description": "Relatório executivo do monitoramento legislativo de IA: fatos documentados, interpretação editorial e top 5 desenvolvimentos.",
         "url": SITE_URL + "/relatorio/", "dateModified": EXECUTION_DATE, "inLanguage": "pt-BR",
         "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE_URL + "/"}},
        ld_breadcrumbs([("Início", ""), ("Relatório", None)]))
    write("relatorio/index.html", page(
        "Relatório e Estado da Regulação de IA na União Europeia",
        "Relatório executivo do monitoramento de IA da União Europeia: fatos documentados, interpretação editorial, top 5 desenvolvimentos e metodologia auditável.",
        "relatorio/", body, jsonld=jsonld))


# ============================================================ DataViz painel
def _date_only(s):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else None


def _parse_ts(s):
    """Interpreta timestamps do dataset (ISO com/sem fuso; datas puras)."""
    if not s:
        return None
    s = str(s)
    for fmt, corte in (("%Y-%m-%dT%H:%M:%S%z", 25), ("%Y-%m-%dT%H:%M:%S", 19),
                       ("%Y-%m-%d", 10)):
        try:
            dt = datetime.strptime(s[:corte], fmt)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=-3)))  # BRT
        return dt.astimezone(timezone.utc)
    return None


def _status_run(ex, agora):
    s = ex.get("status")
    ts = _parse_ts(ex.get("fim") or ex.get("data_hora"))
    if s == "em_andamento":
        # checkpoint de uma execução que não fechou: interrompida pelo job
        if ts and (agora - ts).total_seconds() > 3 * 3600:
            return "interrompida"
        return "em_andamento"
    if s in ("concluida", "parcial", "falhou", "interrompida"):
        return s
    return "concluida" if ex.get("tipo") == "bootstrap" else "concluida"


def _status_run_label(st):
    return {
        "concluida": ("Concluída", "ok"),
        "parcial": ("Parcial (orçamento de tempo)", "parcial"),
        "interrompida": ("Interrompida", "falha"),
        "em_andamento": ("Em andamento", "parcial"),
        "falhou": ("Falhou", "falha"),
    }.get(st, (st, "ok"))


def _latencia_media(latencias, limite=30):
    """Média de latência de detecção, ignorando incorporações históricas em lote."""
    vals = [l for l in latencias if l <= limite]
    return round(sum(vals) / len(vals), 1) if vals else None


def metricas_monitoramento(props, laws, events, updates):
    """Métricas do painel de monitoramento (também exportadas em JSON)."""
    agora = datetime.now(timezone.utc)
    execs = []
    for ex in updates.get("execucoes", []):
        ts = _parse_ts(ex.get("data_hora") or ex.get("fim"))
        fim = _parse_ts(ex.get("fim"))
        http = ex.get("http") or {}
        execs.append({
            "id": ex.get("id"),
            "data_hora": ex.get("data_hora"),
            "fim": ex.get("fim"),
            "ts": ts.isoformat() if ts else None,
            "ts_fim": fim.isoformat() if fim else None,
            "idade_horas": round((agora - (fim or ts)).total_seconds() / 3600, 1)
            if (fim or ts) else None,
            "tipo": ex.get("tipo"),
            "status": _status_run(ex, agora),
            "duracao_segundos": ex.get("duracao_segundos"),
            "orcamento_segundos": ex.get("orcamento_segundos"),
            "verificadas": ex.get("procedimentos_verificados", ex.get("proposicoes_verificadas")),
            "monitoradas": ex.get("procedimentos_monitorados", ex.get("proposicoes_monitoradas")),
            "pendentes": ex.get("procedimentos_pendentes", ex.get("proposicoes_pendentes")),
            "atualizadas": ex.get("procedimentos_atualizados", ex.get("proposicoes_atualizadas")),
            "novas": ex.get("novos_procedimentos", ex.get("novas_proposicoes")),
            "mudancas": ex.get("mudancas_detectadas"),
            "eventos": ex.get("eventos_adicionados"),
            "cobertura_pct": ex.get("cobertura_pct"),
            "erros": len(ex.get("erros") or []),
            "chamadas_http": http.get("chamadas"),
            "cache_http": http.get("cache"),
            "falhas_http": http.get("falhas"),
            "tempo_rede_s": http.get("tempo_total"),
            "por_endpoint": http.get("por_endpoint") or {},
            "fases_segundos": ex.get("fases_segundos") or {},
            "snapshot": ex.get("snapshot_dataset") or {},
            "fontes": len(ex.get("fontes_consultadas") or []),
            "engine": ex.get("motor") or {},
            # monitoramento multiórgão: saúde por fonte + status global
            "status_global": ex.get("status_global"),
            "fontes_monitoradas": ex.get("fontes_monitoradas") or {},
            "fontes_falha": ex.get("fontes_falha") or [],
            "fontes_parciais": ex.get("fontes_parciais") or [],
            "http_fontes": ex.get("http_fontes") or {},
            "mudancas_multiorgao": ex.get("mudancas_multiorgao"),
        })
    execs.sort(key=lambda e: (e["ts"] or ""), reverse=True)
    ultima = execs[0] if execs else {}
    com_metricas = [e for e in execs if e.get("cobertura_pct") is not None]
    concluidas = [e for e in execs if e["status"] in ("concluida", "parcial")]

    # dataset
    revisao = [p for p in props if p.get("revisao_pendente")]
    por_status, por_casa, por_ano, por_faixa = {}, {}, {}, {}
    for p in props:
        sg = status_group(p)
        por_status[sg] = por_status.get(sg, 0) + 1
        casa = p.get("casa_origem") or "União Europeia"
        por_casa[casa] = por_casa.get(casa, 0) + 1
        por_ano[str(p.get("ano"))] = por_ano.get(str(p.get("ano")), 0) + 1
        sc = (p.get("impacto") or {}).get("score", 0) or 0
        faixa = ("90–100" if sc >= 90 else "75–89" if sc >= 75 else "60–74" if sc >= 60
                 else "40–59" if sc >= 40 else "0–39")
        por_faixa[faixa] = por_faixa.get(faixa, 0) + 1
    cats = cat_map()
    por_categoria = {}
    for p in props:
        for c in p.get("categorias", []) or []:
            nome = (cats.get(c) or {}).get("nome")
            if nome:
                por_categoria[nome] = por_categoria.get(nome, 0) + 1

    # mudanças
    mud = updates.get("mudancas", [])
    por_tipo, por_mes, por_dia, latencias, incorporados = {}, {}, {}, [], 0
    for m in mud:
        t = m.get("tipo") or "não classificado"
        por_tipo[t] = por_tipo.get(t, 0) + 1
        d = _date_only(m.get("data"))
        if d:
            por_mes[d[:7]] = por_mes.get(d[:7], 0) + 1
            por_dia[d] = por_dia.get(d, 0) + 1
        det = _date_only(m.get("data_deteccao"))
        if d and det:
            delta = (datetime.strptime(det, "%Y-%m-%d")
                     - datetime.strptime(d, "%Y-%m-%d")).days
            latencias.append(delta)
            if delta > 30:
                incorporados += 1
    meses = sorted(por_mes)[-12:]

    def _serie(campo):
        """Série por execução — ignora execuções sem o campo (dado ausente ≠ zero)."""
        return [e.get(campo) for e in reversed(execs) if e.get(campo) is not None]

    serie_cob = _serie("cobertura_pct")
    serie_mud = _serie("mudancas")
    serie_novas = _serie("novas")
    serie_http = _serie("chamadas_http")
    serie_dur = _serie("duracao_segundos")
    serie_mon = _serie("monitoradas")
    serie_cache = _serie("cache_http")
    com_metricas_ts = [e for e in reversed(execs) if e.get("cobertura_pct") is not None]
    base_rot = com_metricas_ts or list(reversed(execs))
    rotulos = [(e["data_hora"] or "")[5:10].replace("-", "/") for e in base_rot]

    frescor_h = ultima.get("idade_horas")
    if frescor_h is None:
        estado_frescor = "sem_dados"
    elif frescor_h <= 30:
        estado_frescor = "ok"
    elif frescor_h <= 54:
        estado_frescor = "atencao"
    else:
        estado_frescor = "critico"

    alertas = []

    def alerta(nivel, titulo, detalhe):
        alertas.append({"nivel": nivel, "titulo": titulo, "detalhe": detalhe})

    if estado_frescor == "critico":
        alerta("critico", "Monitoramento desatualizado",
               f"Última execução há {frescor_h:.0f} horas (limite esperado: 24h). "
               "Verifique a aba Actions do repositório.")
    elif estado_frescor == "atencao":
        alerta("atencao", "Execução atrasada",
               f"Última execução há {frescor_h:.0f} horas. Há quatro agendamentos diários; confira o histórico de execuções.")
    else:
        alerta("ok", "Monitoramento em dia",
               f"Última execução há {frescor_h:.0f}h." if frescor_h is not None else "—")
    if ultima.get("status") == "interrompida":
        alerta("critico", "Última execução interrompida",
               "A coleta começou mas não fechou (provável estouro de tempo do job). "
               "O site mostra o último estado verificado.")
    elif ultima.get("status") == "parcial":
        alerta("atencao", "Última execução foi parcial",
               f"{ultima.get('pendentes', 0)} proposição(ões) ficaram para a próxima "
               f"execução (cobertura {ultima.get('cobertura_pct')}%).")
    if ultima.get("erros"):
        alerta("atencao", f"{ultima['erros']} erro(s) na última execução",
               "Cada erro guarda a proposição e a URL oficial; ver updates.json.")
    fontes_falha = ultima.get("fontes_falha") or []
    fontes_parciais = ultima.get("fontes_parciais") or []
    status_global = ultima.get("status_global")
    nomes_fontes = {k: (v or {}).get("nome") or k
                    for k, v in (ultima.get("fontes_monitoradas") or {}).items()}
    if status_global == "FALHA":
        alerta("critico", "Coleta multiórgão sem dados confiáveis",
               "Nenhuma fonte obrigatória respondeu nesta execução"
               + (f" (falhas: {', '.join(fontes_falha)})." if fontes_falha else ".")
               + " O último estado verificado do dataset segue publicado.")
    elif status_global == "PARCIAL":
        alerta("atencao", "Monitoramento parcial — fonte não consultada",
               "Fontes com falha nesta execução: "
               + ", ".join(f"{o} ({nomes_fontes.get(o, o)})" for o in fontes_falha)
               if fontes_falha else
               "Fontes fora do esperado nesta execução: " + ", ".join(fontes_parciais))
    elif status_global == "OK" and ultima:
        alerta("ok", "Todas as fontes obrigatórias foram consultadas",
               "Parlamento Europeu, EUR-Lex, Conselho da UE, Comissão Europeia, "
               "European AI Office, EDPB e EDPS.")
    if fontes_parciais and status_global != "PARCIAL":
        alerta("atencao", f"{len(fontes_parciais)} fonte(s) com cobertura parcial",
               ", ".join(f"{o} ({nomes_fontes.get(o, o)})" for o in fontes_parciais)
               + " — ver o quadro por órgão abaixo.")
    if revisao:
        alerta("atencao", f"{len(revisao)} proposições aguardam curadoria",
               "Registros automáticos têm score preliminar e categorias incompletas.")

    por_endpoint = ultima.get("por_endpoint") or {}
    return {
        "gerado_em": EXECUTION_DATE,
        "execucoes": execs,
        "ultima": ultima,
        "frescor": {"horas": frescor_h, "estado": estado_frescor,
                    "cron_utc": "10:17, 13:43, 17:43, 21:43", "cron_brt": "07:17, 10:43, 14:43, 18:43"},
        "kpis": {
            "execucoes_registradas": len(execs),
            "execucoes_com_metricas": len(com_metricas),
            "execucoes_ok": len(concluidas),
            "cobertura_media": round(sum(e["cobertura_pct"] for e in com_metricas)
                                     / len(com_metricas), 1) if com_metricas else None,
            "mudancas_total": len(mud),
            "mudancas_30d": len([m for m in mud
                                 if (days_ago(m.get("data")) or 9999) <= 30]),
            # latência em regime diário (≤30 dias); incorporações históricas contadas à parte
            "latencia_media_dias": _latencia_media(latencias),
            "incorporacoes_historicas": incorporados,
            "fontes_monitoradas": len(ultima.get("fontes_monitoradas") or {}),
            "fontes_falha": len(ultima.get("fontes_falha") or []),
            "fontes_parciais": len(ultima.get("fontes_parciais") or []),
            "status_global": ultima.get("status_global"),
            "procedimentos": len(props),
            "proposicoes": len(props),
            "curadoria_pendente": len(revisao),
            "normas": len(laws),
            "eventos_futuros": len([e for e in events.get("eventos", [])
                                    if e.get("janela") in ("proximos_7_dias", "proximos_30_dias")]),
        },
        "series": {
            "rotulos": rotulos,
            "cobertura_pct": serie_cob,
            "mudancas": serie_mud,
            "novas": serie_novas,
            "chamadas_http": serie_http,
            "cache_http": serie_cache,
            "duracao_s": serie_dur,
            "monitoradas": serie_mon,
        },
        "dataset": {
            "por_status": por_status, "por_casa": por_casa, "por_ano": por_ano,
            "por_faixa_score": por_faixa, "por_categoria": por_categoria,
            "revisao_pendente": len(revisao),
        },
        "mudancas": {
            "total": len(mud), "por_tipo": por_tipo, "por_mes": por_mes,
            "por_dia": por_dia, "latencia_media_dias": _latencia_media(latencias),
            "incorporacoes_historicas": incorporados,
        },
        "http_por_endpoint": por_endpoint,
        "alertas": alertas,
    }


def build_monitoramento(props, laws, events, updates, met):
    exs = met["execucoes"]
    ultima = met["ultima"] or {}
    kpis = met["kpis"]
    ser = met["series"]

    def kpi(num, lbl, cor=""):
        cls = f"metric {cor}".strip()
        return f'<div class="{cls}"><div class="num">{num}</div><div class="lbl">{lbl}</div></div>'

    frescor = met["frescor"]
    cor_frescor = {"ok": "green", "atencao": "yellow", "critico": "red"}.get(frescor["estado"], "")
    idade = frescor["horas"]
    idade_txt = "—" if idade is None else (f"{idade:.1f} h" if idade < 48 else f"{idade / 24:.1f} dias")

    alertas_html = "".join(
        f'<div class="alert {a["nivel"]}"><b>{esc(a["titulo"])}</b><span>{esc(a["detalhe"])}</span></div>'
        for a in met["alertas"])

    # --- monitoramento por órgão (fonte obrigatória que falhou fica explícita)
    fontes_ordem = ["parlamento", "eurlex_motor", "ai_office", "eurlex",
                    "eu_council", "eu_commission", "eu_parliament", "edpb", "edps"]
    fontes_ult = ultima.get("fontes_monitoradas") or {}
    linhas_fontes, ok_fontes = [], 0
    for chave in [f for f in fontes_ordem if f in fontes_ult] + \
            [f for f in sorted(fontes_ult) if f not in fontes_ordem]:
        f = fontes_ult.get(chave) or {}
        st = f.get("status") or "—"
        rotulo_st, classe_st = {"ok": ("OK", "green"), "parcial": ("Parcial", "yellow"),
                                "falha": ("FALHA", "red")}.get(st, (st, "red"))
        if st == "ok":
            ok_fontes += 1
        endpoints = f.get("endpoints") or []
        ep_txt = "<br>".join(
            f'<a href="{esc(u)}" target="_blank" rel="noopener">{esc(u[:78])}</a>'
            for u in endpoints[:3]) or "—"
        canais_falhos = f.get("canais_falhos") or []
        detalhe = f.get("erro_detalhe") or ""
        if canais_falhos and st != "ok":
            detalhe = "canais com falha: " + ", ".join(canais_falhos[:4]) + \
                      (f" · {detalhe}" if detalhe else "")
        novidades = f.get("novidades")
        linhas_fontes.append(
            f'<tr><td><b>{esc(f.get("nome") or chave)}</b><br><span style="color:var(--muted);'
            f'font-size:12px">{esc(chave)}</span></td>'
            f'<td><span class="run-status {classe_st}">{esc(rotulo_st)}</span>'
            + (f'<br><span style="font-size:12px;color:var(--muted)">'
               f'{esc(detalhe[:170])}</span>' if detalhe else "")
            + f'</td>'
            f'<td>{esc((f.get("ultima_tentativa") or "—")[:16].replace("T", " "))}</td>'
            f'<td>{esc((f.get("ultima_execucao_ok") or "—")[:16].replace("T", " "))}</td>'
            f'<td>{f.get("itens_consultados", "—")}</td>'
            f'<td>{novidades if novidades is not None else "—"}</td>'
            f'<td>{f.get("erros", 0)}</td><td style="font-size:12px">{ep_txt}</td></tr>')
    total_fontes = len([f for f in fontes_ult.values() if f])
    status_global_txt = (ultima.get("status_global") or "—")
    cor_global = {"OK": "green", "PARCIAL": "yellow", "FALHA": "red"}.get(
        status_global_txt, "")
    quadro_fontes = f'''
<section class="block"><div class="wrap">
  <h2 class="section-title">Monitoramento por órgão</h2>
  <p class="section-sub">Status obrigatório de cada fonte na última execução: quando foi a última
  tentativa, quando foi a última execução bem-sucedida, quantos itens foram consultados, quantas
  novidades apareceram, quantos erros e quais endpoints oficiais foram usados.
  <b>Fonte que não respondeu aparece como falha</b> — nunca como monitorada.</p>
  <div class="grid cols-4" style="margin-bottom:16px">
    {kpi(f"{ok_fontes}/{total_fontes}" if total_fontes else "—", "Fontes OK na última execução")}
    {kpi(status_global_txt, "Status global da coleta", cor_global)}
    {kpi(len(ultima.get("fontes_falha") or []), "Fontes com falha")}
    {kpi(len(ultima.get("fontes_parciais") or []), "Fontes parciais")}
  </div>
  <div class="table-wrap" style="overflow-x:auto">
  <table class="table"><thead><tr>
    <th>Órgão</th><th>Status</th><th>Última tentativa</th><th>Última execução OK</th>
    <th>Itens consultados</th><th>Novidades</th><th>Erros</th><th>Endpoints oficiais</th>
  </tr></thead><tbody>
  {"".join(linhas_fontes) or "<tr><td colspan='8'>Sem registro de fontes nesta execução.</td></tr>"}
  </tbody></table></div>
  <p class="disclaimer" style="margin-top:10px">Status global: <b>OK</b> = todos os órgãos
  obrigatórios consultados; <b>PARCIAL</b> = ao menos uma fonte falhou (o dataset preserva o último
  estado verificado e a falha fica registrada em <code>updates.json</code>);
  <b>FALHA</b> = execução incapaz de produzir dados confiáveis — nesse caso nada é publicado.
  O detalhe por canal (o que respondeu e o que não respondeu) está em
  <code>data/legislation/updates.json</code>.</p>
</div></section>
'''

    # --- séries temporais
    tem_series = len([v for v in ser["cobertura_pct"] if v is not None]) >= 1
    linha_cob = ""
    if tem_series:
        linha_cob = dv.line_chart(
            ser["rotulos"],
            [{"nome": "Cobertura da verificação (%)", "valores": ser["cobertura_pct"],
              "cor": "accent", "area": True}],
            y_max=100, unidade="%")
    grafico_dur = dv.line_chart(
        ser["rotulos"],
        [{"nome": "Duração da coleta (s)", "valores": ser["duracao_s"], "cor": "azul", "area": True},
         {"nome": "Orçamento (s)", "valores": [(ultima.get("orcamento_segundos") or 1500)] * len(ser["rotulos"]),
          "cor": "amarelo"}],
        unidade="s") if tem_series else ""
    grafico_mon = dv.line_chart(
        ser["rotulos"], [{"nome": "Proposições monitoradas", "valores": ser["monitoradas"],
                          "cor": "roxo", "area": True}]) if tem_series else ""
    grafico_mud = dv.bar_chart(list(zip(ser["rotulos"], ser["mudancas"])), color="accent",
                               unidade="mudanças") if tem_series else ""
    grafico_http = dv.bar_chart(list(zip(ser["rotulos"], ser["chamadas_http"])), color="azul",
                                unidade="chamadas") if tem_series else ""
    grafico_novas = dv.bar_chart(list(zip(ser["rotulos"], ser["novas"])), color="roxo",
                                 unidade="novas") if tem_series else ""
    n_exec_met = len([v for v in ser["cobertura_pct"] if v is not None])
    if not tem_series:
        aviso_series = ('<div class="note warn"><b>Sem métricas por execução ainda.</b> As métricas '
                        'de cobertura, duração e volume de consultas passaram a ser registradas em '
                        '10/09/2026; os gráficos aparecem na próxima execução do cron.</div>')
    elif n_exec_met == 1:
        aviso_series = ('<div class="note"><b>Primeira execução com métricas completas.</b> '
                        'A partir da próxima execução do cron as séries ganham comparação '
                        'histórica (cobertura, duração e volume de consultas por dia).</div>')
    else:
        aviso_series = ""

    # --- composição do dataset
    faixas = ["90–100", "75–89", "60–74", "40–59", "0–39"]
    barras_faixa = dv.bar_chart_h([(f"{f} pontos", met["dataset"]["por_faixa_score"].get(f, 0))
                                   for f in faixas], color="azul")
    anos = sorted(met["dataset"]["por_ano"])[-10:]
    barras_ano = dv.bar_chart([(a, met["dataset"]["por_ano"].get(a, 0)) for a in anos],
                              color="roxo", unidade="proposições")
    barras_cat = dv.bar_chart_h(
        sorted(met["dataset"]["por_categoria"].items(), key=lambda kv: -kv[1])[:10])
    status_lbl = {"em_tramitacao": ("Em tramitação", "accent"), "arquivada": ("Arquivada", "cinza"),
                  "a_sancao": ("À sanção", "amarelo"), "aprovada_lei": ("Convertida em lei", "roxo")}
    itens_status = [(status_lbl.get(k, (k, "cinza"))[0], v, status_lbl.get(k, ("", "cinza"))[1])
                    for k, v in sorted(met["dataset"]["por_status"].items(), key=lambda kv: -kv[1])]
    composicao = dv.stacked_bar(itens_status) + dv.stacked_legenda(itens_status)
    itens_curadoria = [("Curadoria concluída", kpis["procedimentos"] - kpis["curadoria_pendente"], "accent"),
                       ("Aguardando curadoria", kpis["curadoria_pendente"], "amarelo")]
    curadoria = dv.stacked_bar(itens_curadoria) + dv.stacked_legenda(itens_curadoria)

    # --- mudanças
    tipos = sorted(met["mudancas"]["por_tipo"].items(), key=lambda kv: -kv[1])[:10]
    barras_tipo = dv.bar_chart_h([(t.capitalize(), v) for t, v in tipos], color="amarelo")
    meses = sorted(met["mudancas"]["por_mes"])[-12:]
    barras_mes = dv.bar_chart([(m[5:] + "/" + m[2:4], met["mudancas"]["por_mes"][m]) for m in meses],
                              color="accent", unidade="mudanças", rotulo_max=6)
    calendario = dv.heatmap(met["mudancas"]["por_dia"], semanas=26,
                            fim=datetime.now(timezone(timedelta(hours=-3))).date())

    # --- tabela de execuções
    linhas = []
    for e in exs[:15]:
        lbl, cls = _status_run_label(e["status"])
        dur = f'{e["duracao_segundos"]}s' if e.get("duracao_segundos") else "—"
        cob = f'{e["cobertura_pct"]}%' if e.get("cobertura_pct") is not None else "—"
        http_txt = (f'{e["chamadas_http"]}' if e.get("chamadas_http") is not None else "—")
        linhas.append(
            f'<tr><td>{esc((e["data_hora"] or "")[:16].replace("T", " "))}</td>'
            f'<td><span class="run-status {cls}">{esc(lbl)}</span></td>'
            f'<td>{dur}</td><td>{e.get("verificadas") if e.get("verificadas") is not None else "—"}</td>'
            f'<td>{cob}</td><td>{e.get("novas") if e.get("novas") is not None else "—"}</td>'
            f'<td>{e.get("mudancas") if e.get("mudancas") is not None else "—"}</td>'
            f'<td>{http_txt}</td><td>{e["erros"]}</td></tr>')

    # --- custo por endpoint (última execução)
    eps = sorted(met["http_por_endpoint"].items(), key=lambda kv: -kv[1].get("chamadas", 0))[:8]
    barras_ep = dv.bar_chart_h([(k, v.get("chamadas", 0)) for k, v in eps], color="azul") if eps else \
        '<p class="sub">Sem telemetria de rede nesta execução.</p>'

    body = f"""
<div class="page-head"><div class="wrap">
  <div class="crumbs"><a href="{SITE_URL}/">Início</a> › Monitoramento</div>
  <h1>Painel de monitoramento</h1>
  <p class="sub">Métricas operacionais do monitoramento legislativo — atualizadas automaticamente
  a cada rebuild do site (cron diário às {frescor['cron_brt']} BRT / {frescor['cron_utc']} UTC).
  Serve para auditar se a coleta está rodando, quanto do banco foi verificado, o que mudou e
  quanto custou em consultas às APIs oficiais.</p>
</div></div>

<section class="block"><div class="wrap">
  <h2 class="section-title">Saúde do monitoramento</h2>
  <p class="section-sub">Sinais automáticos calculados a partir do histórico de execuções
  (<code>data/legislation/updates.json</code>).</p>
  <div data-freshness-panel="{esc((ultima.get('fim') or ultima.get('data_hora')) or '')}">
  {alertas_html}
  </div>
  <div class="grid cols-4" style="margin-top:16px">
    {kpi(idade_txt, "Desde a última execução", cor_frescor)}
    {kpi(f'{ultima.get("cobertura_pct")}%' if ultima.get("cobertura_pct") is not None else "—",
         "Cobertura da última execução", "")}
    {kpi(ultima.get("pendentes", "—"), "Proposições pendentes", "")}
    {kpi(kpis["cobertura_media"] if kpis["cobertura_media"] is not None else "—",
         "Cobertura média (histórico)", "")}
    {kpi(kpis["execucoes_registradas"], "Execuções registradas")}
    {kpi(ultima.get("status", "—").capitalize() if ultima else "—", "Status da última execução")}
    {kpi(kpis["mudancas_30d"], "Mudanças (30 dias)")}
    {kpi(kpis["curadoria_pendente"], "Aguardando curadoria")}
  </div>
  <p class="disclaimer" style="margin-top:12px">A idade desde a última execução é recalculada no
  seu navegador a cada visita — se o painel ficar vermelho, o cron parou.</p>
</div></section>
{quadro_fontes}

<section class="block"><div class="wrap">
  <h2 class="section-title">Evolução por execução</h2>
  <p class="section-sub">Cada barra/ponto é uma execução do coletor. O site é reconstruído após
  cada execução, então este painel acompanha o cron.</p>
  {aviso_series}
  <div class="grid cols-2">
    <div class="chart-card"><h3>Cobertura da verificação</h3>
      <p class="sub">Percentual das proposições monitoradas efetivamente consultadas na execução.</p>
      {linha_cob or '<p class="sub">—</p>'}</div>
    <div class="chart-card"><h3>Duração da coleta × orçamento</h3>
      <p class="sub">Tempo gasto na coleta e teto configurado (evita estourar o job).</p>
      {grafico_dur or '<p class="sub">—</p>'}
      {dv.legenda([{"nome": "Duração da coleta", "cor": "azul"}, {"nome": "Orçamento", "cor": "amarelo"}]) if grafico_dur else ""}</div>
  </div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Volume de trabalho</h2>
  <p class="section-sub">Quanto o monitoramento verifica, descobre e registra em cada execução.</p>
  <div class="grid cols-2">
    <div class="chart-card"><h3>Proposições monitoradas</h3>
      <p class="sub">Tamanho do banco de proposições ao fim de cada execução.</p>{grafico_mon or '<p class="sub">—</p>'}</div>
    <div class="chart-card"><h3>Chamadas às APIs oficiais</h3>
      <p class="sub">Consultas HTTP feitas às fontes oficiais da UE por execução.</p>{grafico_http or '<p class="sub">—</p>'}</div>
    <div class="chart-card"><h3>Mudanças detectadas</h3>
      <p class="sub">Alterações registradas com fonte oficial (relator, situação, pauta, votação, apensação…).</p>{grafico_mud or '<p class="sub">—</p>'}</div>
    <div class="chart-card"><h3>Novas proposições</h3>
      <p class="sub">Fichas novas incorporadas ao banco em cada execução.</p>{grafico_novas or '<p class="sub">—</p>'}</div>
  </div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Composição do banco legislativo</h2>
  <p class="section-sub">Fotografia do dataset publicado nesta execução.</p>
  <div class="chart-card"><h3>Situação dos procedimentos ({kpis['procedimentos']} monitorados)</h3>{composicao}</div>
  <div class="grid cols-2" style="margin-top:16px">
    <div class="chart-card"><h3>Faixas do AI Legislative Impact Score</h3>
      <p class="sub">Distribuição das proposições por prioridade de acompanhamento.</p>{barras_faixa}</div>
    <div class="chart-card"><h3>Por ano de apresentação</h3>
      <p class="sub">Últimos anos representados no banco.</p>{barras_ano}</div>
    <div class="chart-card"><h3>Temas mais frequentes</h3>
      <p class="sub">Categorias temáticas atribuídas às proposições monitoradas.</p>{barras_cat}</div>
    <div class="chart-card"><h3>Curadoria</h3>
      <p class="sub">Registros automáticos aguardando revisão editorial (score preliminar).</p>{curadoria}</div>
  </div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Atividade legislativa detectada</h2>
  <p class="section-sub">O que o monitoramento registrou desde a primeira execução
  ({kpis['mudancas_total']} mudanças; {kpis['latencia_media_dias'] or '—'} dias em média entre o
  evento e a detecção, considerando apenas eventos captados pela rotina diária —
  {kpis['incorporacoes_historicas']} registros históricos foram incorporados em lote).</p>
  <div class="chart-card"><h3>Mudanças por dia</h3>
    <p class="sub">Calendário dos últimos 6 meses — quanto mais escuro, mais mudanças no dia.</p>
    {calendario}</div>
  <div class="grid cols-2" style="margin-top:16px">
    <div class="chart-card"><h3>Mudanças por mês</h3>{barras_mes}</div>
    <div class="chart-card"><h3>Tipo de mudança</h3>
      <p class="sub">Classificação automática a partir do despacho oficial.</p>{barras_tipo}</div>
  </div>
</div></section>

<section class="block"><div class="wrap">
  <h2 class="section-title">Histórico de execuções</h2>
  <p class="section-sub">Log auditável do cron. Cada linha é uma execução registrada pelo coletor.</p>
  <div style="overflow-x:auto"><table class="tbl">
    <thead><tr><th>Início (UTC−3)</th><th>Status</th><th>Duração</th><th>Verificadas</th>
    <th>Cobertura</th><th>Novas</th><th>Mudanças</th><th>HTTP</th><th>Erros</th></tr></thead>
    <tbody>{''.join(linhas)}</tbody></table></div>
  <div class="grid cols-2" style="margin-top:18px">
    <div class="chart-card"><h3>Custo por endpoint (última execução)</h3>
      <p class="sub">Chamadas HTTP por endpoint oficial — base para otimizar a coleta.</p>
      {barras_ep}</div>
    <div class="chart-card"><h3>Tempos por fase</h3>
      <p class="sub">Distribuição do tempo da coleta entre atualização, descoberta e agenda.</p>
      {dv.bar_chart_h([(k.replace('_', ' ').capitalize(), round(v)) for k, v in
                       sorted((ultima.get('fases_segundos') or {}).items(), key=lambda kv: -kv[1])],
                      color='roxo') or '<p class="sub">Sem telemetria de fases nesta execução.</p>'}
    </div>
  </div>
  <p class="disclaimer" style="margin-top:14px">Métricas derivadas de <code>updates.json</code>
  (histórico auditável). Números de execuções anteriores a 10/09/2026 aparecem como “—” quando o
  campo não era coletado. {DISCLAIMER}</p>
</div></section>
"""
    jsonld = combine_ld(
        ld_collection("Painel de monitoramento do Monitor Legislativo de IA",
                      "Métricas operacionais do monitoramento legislativo de IA: frescor, cobertura, "
                      "mudanças detectadas, custo em consultas e histórico de execuções do cron.",
                      "monitoramento/"),
        ld_breadcrumbs([("Início", ""), ("Monitoramento", None)]))
    write("monitoramento/index.html", page(
        "Painel de monitoramento — métricas do cron e da coleta de IA",
        "Métricas do monitoramento de IA da União Europeia: frescor da última execução, cobertura "
        "da verificação, mudanças detectadas, chamadas às fontes oficiais da UE e "
        "histórico auditável do cron diário.",
        "monitoramento/", body, jsonld=jsonld))
    return met

def build_sitemap(paths):
    today = EXECUTION_DATE
    urls = "".join(
        f"<url><loc>{SITE_URL}/{p}</loc><lastmod>{today}</lastmod></url>"
        for p in paths)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")


def main():
    global EXECUTION_DATE, EXECUTION_RUN, EXECUTION_TS
    props = load("propositions.json")["proposicoes"]
    laws = load("laws.json")["normas"]
    events = load("events.json")
    updates = load("updates.json")
    timeline = load("timeline.json")
    cats = cat_map()

    EXECUTION_DATE = updates.get("meta", {}).get("execucao", EXECUTION_DATE) or EXECUTION_DATE
    if updates.get("execucoes"):
        EXECUTION_RUN = updates["execucoes"][0]
    EXECUTION_TS = EXECUTION_RUN.get("fim") or EXECUTION_RUN.get("data_hora")

    build_slugs(props)

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    shutil.copytree(os.path.join(BASE, "data", "legislation"), os.path.join(OUT, "data"))
    shutil.copytree(ASSETS, os.path.join(OUT, "assets"))

    build_home(props, laws, events, updates, timeline, cats)
    build_propositions(props, cats)
    build_prop_pages(props, cats, updates)
    build_updates(props, updates)
    build_laws(laws)
    build_timeline(timeline)
    build_parliamentarians(load("parliamentarians.json")["parlamentares"], props)
    build_agenda(events)
    build_metodologia(props, laws, updates)
    build_report(props, laws, updates, events)

    # Painel de monitoramento (DataViz) — alimentado pelo log de execuções do cron
    met = metricas_monitoramento(props, laws, events, updates)
    build_monitoramento(props, laws, events, updates, met)
    write("data/monitoramento.json", json.dumps(met, ensure_ascii=False, indent=2) + "\n")

    paths = ["", "procedimentos-legislativos/", "atualizacoes/", "legislacao-e-atos/",
             "timeline/", "atores-legislativos/",
             "agenda/", "monitoramento/", "metodologia/", "relatorio/"]
    paths += [prop_fs_path(p["id"]).replace("index.html", "") for p in props]
    build_sitemap(paths)

    n_pages = 10 + len(props)
    print(f"OK: site gerado em docs/ — {n_pages} páginas, {len(paths)} URLs no sitemap.")


if __name__ == "__main__":
    main()

