#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_site_eu.py — Validações automáticas do Monitor UE de IA (exclusivo).

Detecta:
  - JSON inválido em data/legislation-eu
  - proposições duplicadas (id e chave)
  - URLs oficiais ausentes ou inválidas
  - scores fora da faixa
  - páginas HTML sem <title> ou sem canonical
  - canonical/sitemap/robots apontando para domínio errado (deve ser https://monitor-ue.vercel.app)
  - links internos quebrados
  - referências remanescentes a domínios antigos (monitor.lcfconsulting.com.br, monitor-legislativo-five.vercel.app, lcaladoferreira.github.io)
  - conteúdo de fontes brasileiras (senado.leg.br, camara.leg.br, planalto.gov.br, in.gov.br, ANPD, CNJ, TSE) no dataset ou nas páginas
  - domínio antigo em QUALQUER arquivo do repositório fora das guardas de migração

Uso: python3 scripts/validate_site_eu.py
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "legislation-eu")
OUT = os.path.join(BASE, "docs")
OLD_DOMAINS = [
    "lcaladoferreira.github.io/monitor-legislativo",
    "monitor.lcfconsulting.com.br",
    "monitor-legislativo-five.vercel.app",
]
EXPECTED_DOMAIN = "https://monitor-ue.vercel.app"
# Marcadores de fontes/legislação brasileira — proibidos no dataset e nas
# páginas: este repositório é EXCLUSIVO da União Europeia.
BR_MARKERS = [
    "senado.leg.br",
    "camara.leg.br",
    "planalto.gov.br",
    "in.gov.br",
    "anpd.gov.br",
    "cnj.jus.br",
    "tse.jus.br",
    "congressonacional.leg.br",
]
# Arquivos onde o domínio antigo aparece APENAS como guarda de migração
# (listas de bloqueio/redirect/teste) — qualquer outro arquivo é erro.
OLD_DOMAIN_GUARD_FILES = {
    "scripts/build_site.py",
    "scripts/build_site_eu.py",
    "scripts/build_site_eu_core.py",
    "scripts/update_legislation_eu.py",
    "scripts/validate_site_eu.py",
    "tests/test_site_contract_ue.py",
    "tests/test_fontes_ue.py",
    "tests/browser_smoke.cjs",
    "vercel.json",
}
TEXT_SUFFIXES = (
    ".py", ".json", ".yml", ".yaml", ".md", ".txt", ".xml", ".html",
    ".js", ".cjs", ".css", ".svg", ".example", ".gitignore",
)


def site_url():
    """Lê o SITE_URL canônico de scripts/build_site.py (fonte única)."""
    candidates = [
        os.path.join(BASE, "scripts", "build_site.py"),
        os.path.join(BASE, "scripts", "build_site_eu.py"),
    ]
    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        with open(candidate, encoding="utf-8") as f:
            content = f.read()
            m = re.search(r'SITE_URL\s*=\s*\"([^\"]+)\"', content)
            if m:
                return m.group(1).rstrip("/")
    raise SystemExit("SITE_URL não encontrado em scripts/build_site.py")


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def load_json(path, rep, label):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        rep.err(f"{label}: arquivo não encontrado ({path})")
    except json.JSONDecodeError as e:
        rep.err(f"{label}: JSON inválido — {e}")
    return None


def band(score):
    if score >= 90:
        return "CRÍTICO"
    if score >= 75:
        return "MUITO RELEVANTE"
    if score >= 60:
        return "RELEVANTE"
    if score >= 40:
        return "MONITORAR"
    return "BAIXA PRIORIDADE"


def check_data(rep):
    props_f = load_json(os.path.join(DATA, "propositions.json"), rep, "propositions.json")
    laws_f = load_json(os.path.join(DATA, "laws.json"), rep, "laws.json")
    tl_f = load_json(os.path.join(DATA, "timeline.json"), rep, "timeline.json")
    pm_f = load_json(os.path.join(DATA, "parliamentarians.json"), rep, "parliamentarians.json")
    ev_f = load_json(os.path.join(DATA, "events.json"), rep, "events.json")
    up_f = load_json(os.path.join(DATA, "updates.json"), rep, "updates.json")
    cat_f = load_json(os.path.join(DATA, "categories.json"), rep, "categories.json")

    props = (props_f or {}).get("proposicoes", [])
    seen, dup = set(), set()
    for p in props:
        if p.get("id") in seen:
            dup.add(p.get("id"))
        seen.add(p.get("id"))
    for d in sorted(dup):
        rep.err(f"propositions.json: id duplicado '{d}'")
    seen2 = {}
    for p in props:
        key = (p.get("casa_origem"), p.get("tipo"), p.get("numero"), p.get("ano"))
        if key in seen2:
            rep.err(f"propositions.json: proposição duplicada {key} ({seen2[key]} x {p.get('id')})")
        seen2[key] = p.get("id")
    required = ["id", "tipo", "numero", "ano", "titulo", "ementa", "casa_origem", "situacao", "url_oficial"]
    for p in props:
        for field in required:
            if not p.get(field):
                rep.err(f"propositions.json: {p.get('id')}: campo obrigatório ausente '{field}'")
        url = p.get("url_oficial") or ""
        if url and not re.match(r"https?://", url):
            rep.err(f"propositions.json: {p.get('id')}: url_oficial inválida '{url}'")
        imp = p.get("impacto") or {}
        s = imp.get("score")
        if not isinstance(s, int) or not (0 <= s <= 100):
            rep.err(f"propositions.json: {p.get('id')}: score inválido ({s!r})")
        elif not str(imp.get("classificacao", "")).startswith(band(s)):
            rep.err(f"propositions.json: {p.get('id')}: classificação '{imp.get('classificacao')}' incompatível com score {s} (esperado {band(s)}...)")
    prop_ids = {p.get("id") for p in props}
    for m in (up_f or {}).get("mudancas", []):
        if m.get("proposicao") and m["proposicao"] not in prop_ids:
            rep.warn(f"updates.json: mudança '{(m.get('titulo') or '')[:60]}' referencia proposição inexistente '{m.get('proposicao')}'")
        if not m.get("fonte_url"):
            rep.warn(f"updates.json: mudança sem fonte_url ('{(m.get('titulo') or '')[:60]}')")
    if not (up_f or {}).get("execucoes"):
        rep.err("updates.json: sem registros de execução")
    for label, items, url_field in (
            ("laws.json", (laws_f or {}).get("normas", []), "url"),
            ("parliamentarians.json", (pm_f or {}).get("parlamentares", []), None),
            ("events.json", (ev_f or {}).get("eventos", []), "fonte_url")):
        ids = [x.get("id") for x in items]
        if len(ids) != len(set(ids)):
            rep.err(f"{label}: ids duplicados")
        for x in items:
            if url_field and not (x.get(url_field) or "").startswith("http"):
                rep.warn(f"{label}: {x.get('id')}: {url_field} ausente/inválida")
    for e in (tl_f or {}).get("eventos", []):
        if not (e.get("fonte_url") or "").startswith("http"):
            rep.warn(f"timeline.json: evento '{(e.get('titulo') or '')[:50]}' sem fonte_url válida")
    cats = (cat_f or {}).get("categorias", [])
    if len({c.get("id") for c in cats}) != len(cats):
        rep.err("categories.json: ids duplicados")
    return props


def local_path_for_url(url, site):
    if not url.startswith(site):
        return None
    rel = url[len(site):].split("?", 1)[0].split("#", 1)[0]
    if rel.startswith("/"):
        rel = rel[1:]
    if rel == "" or rel.endswith("/"):
        rel = rel + "index.html" if rel else "index.html"
    return os.path.join(OUT, rel)


def check_docs(rep, site):
    if not os.path.isdir(OUT):
        rep.err(f"docs/: diretório não encontrado (execute build_site.py) — esperado em {OUT}")
        return
    html_files = []
    for root, _, files in os.walk(OUT):
        for fn in files:
            if fn.endswith(".html"):
                html_files.append(os.path.join(root, fn))
    if not html_files:
        rep.err("docs/: nenhuma página HTML encontrada")
        return
    href_re = re.compile(r'href="([^"]+)"')
    for path in sorted(html_files):
        with open(path, encoding="utf-8", errors="replace") as f:
            html = f.read()
        rel = os.path.relpath(path, OUT)
        # ignora pasta legada uniao-europeia se ainda existir (será removida)
        if rel.startswith("uniao-europeia" + os.sep) or rel.startswith("proposicoes" + os.sep):
            # proposicoes é legado brasileiro — se existir, é erro de exclusividade
            if rel.startswith("proposicoes"):
                rep.err(f"docs/{rel}: pasta legada brasileira encontrada — site deve ser exclusivo UE")
                continue
        m = re.search(r"<title>(.*?)</title>", html, re.S)
        if not m or not m.group(1).strip():
            rep.err(f"docs/{rel}: sem <title>")
        mc = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        if not mc:
            rep.err(f"docs/{rel}: sem canonical")
        elif not mc.group(1).startswith(site + "/") and mc.group(1).rstrip("/") != site:
            rep.err(f"docs/{rel}: canonical fora do domínio oficial {EXPECTED_DOMAIN} ({mc.group(1)[:120]})")
        for old in OLD_DOMAINS:
            if old in html and "OLD_DOMAIN" not in html:
                # permite se for parte do novo? não
                if old != EXPECTED_DOMAIN.replace("https://", ""):
                    rep.err(f"docs/{rel}: contém referência ao domínio antigo {old}")
                    break
        if rel not in ("app/index.html", "login/index.html") and re.search(r'<meta name="robots" content="[^"]*noindex', html):
            rep.err(f"docs/{rel}: contém noindex (bloqueia indexação)")
        for href in href_re.findall(html):
            if href.startswith(site):
                lp = local_path_for_url(href, site)
                if lp and not os.path.exists(lp):
                    rep.err(f"docs/{rel}: link interno quebrado → {href[len(site):][:120]}")
    robots = os.path.join(OUT, "robots.txt")
    try:
        with open(robots, encoding="utf-8") as f:
            rtxt = f.read()
        for old in OLD_DOMAINS:
            if old in rtxt:
                rep.err(f"robots.txt: aponta para o domínio antigo {old}")
        if f"Sitemap: {site}/sitemap.xml" not in rtxt:
            rep.err(f"robots.txt: sem Sitemap para o domínio oficial {site}")
    except FileNotFoundError:
        rep.err("robots.txt: ausente")
    sm = os.path.join(OUT, "sitemap.xml")
    try:
        with open(sm, encoding="utf-8") as f:
            stxt = f.read()
        for old in OLD_DOMAINS:
            if old in stxt:
                rep.err(f"sitemap.xml: contém URLs do domínio antigo {old}")
        root = ET.fromstring(stxt)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [u.text for u in root.findall("s:url/s:loc", ns)]
        if not urls:
            rep.err("sitemap.xml: nenhuma URL encontrada")
        for u in urls:
            if not u.startswith(site + "/") and u.rstrip("/") != site:
                rep.err(f"sitemap.xml: URL fora do domínio oficial {EXPECTED_DOMAIN} ({u[:120]})")
            lp = local_path_for_url(u, site)
            if lp and not os.path.exists(lp):
                rep.err(f"sitemap.xml: URL sem arquivo correspondente ({u[len(site):][:120]})")
        if len(urls) != len(set(urls)):
            rep.err("sitemap.xml: URLs duplicadas")
    except FileNotFoundError:
        rep.err("sitemap.xml: ausente")
    except ET.ParseError as e:
        rep.err(f"sitemap.xml: XML inválido — {e}")


def check_markers(rep, base_dir, label):
    """Bloqueia marcadores de fontes/legislação brasileiras no dataset UE."""
    if not os.path.isdir(base_dir):
        return
    for root, _, files in os.walk(base_dir):
        for fn in files:
            p = os.path.join(root, fn)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue
            low = content.lower()
            for marker in BR_MARKERS:
                if marker in low:
                    rep.err(f"{label}/{os.path.relpath(p, base_dir)}: conteúdo brasileiro "
                            f"proibido ('{marker}') — repositório exclusivo da UE")


def check_all_generated(rep, site):
    """Varre TODOS os arquivos gerados em docs/ (não só HTML) procurando
    domínios antigos ou fontes brasileiras."""
    if not os.path.isdir(OUT):
        return
    for root, _, files in os.walk(OUT):
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, OUT)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue
            low = content.lower()
            for old in OLD_DOMAINS:
                if old in low:
                    rep.err(f"docs/{rel}: contém o domínio antigo {old}")
            for marker in BR_MARKERS:
                if marker in low:
                    rep.err(f"docs/{rel}: conteúdo brasileiro proibido ('{marker}') "
                            f"— site exclusivo da UE em {site}")


def main():
    site = site_url()
    rep = Report()
    print(f"Validando site UE exclusivo (domínio oficial: {site}) ...")
    if site != EXPECTED_DOMAIN:
        rep.err(f"SITE_URL deve ser {EXPECTED_DOMAIN}, encontrado {site}")
    for old in OLD_DOMAINS:
        if old in site:
            rep.err(f"SITE_URL ainda aponta para domínio antigo {old}")
    check_data(rep)
    check_markers(rep, DATA, "data/legislation-eu")
    check_docs(rep, site)
    check_all_generated(rep, site)
    # Varredura estrita de todo o repositório: o domínio antigo só é permitido
    # como literal de guarda (listas de bloqueio/redirect/teste). Qualquer
    # outro arquivo — fonte, dado, doc ou workflow — é erro de exclusividade.
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".vercel", ".private")]
        for fn in files:
            if fn.endswith((".pyc", ".pyo")):
                continue
            if not fn.endswith(TEXT_SUFFIXES):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, BASE).replace(os.sep, "/")
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue
            for old in OLD_DOMAINS:
                if old in content and rel not in OLD_DOMAIN_GUARD_FILES:
                    rep.err(f"{rel}: contém referência ao domínio antigo {old} "
                            f"— site deve ser exclusivo de {EXPECTED_DOMAIN}")
    print(f"\nErros: {len(rep.errors)} · Avisos: {len(rep.warnings)}")
    for e in rep.errors:
        print(f"  ERRO: {e}")
    for w in rep.warnings[:50]:
        print(f"  aviso: {w}")
    if len(rep.warnings) > 50:
        print(f"  ... +{len(rep.warnings) - 50} avisos")
    if rep.errors:
        print("\nVALIDAÇÃO FALHOU — site não é exclusivo UE em https://monitor-ue.vercel.app/")
        return 1
    print(f"\nVALIDAÇÃO OK — exclusivo UE em {EXPECTED_DOMAIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
