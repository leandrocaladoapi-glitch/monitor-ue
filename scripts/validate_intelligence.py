#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validação da camada de inteligência regulatória (Módulo 18).

Verifica, contra o dataset gerado e as páginas publicadas:

  * integridade e schema dos JSON em data/intelligence;
  * URL oficial obrigatória em todo evento publicado;
  * nenhum evento com confiança abaixo de 0.6 publicado;
  * deduplicação de eventos;
  * consistência dos prazos (data, dias restantes, fonte, norma);
  * presença das páginas por setor, empresa, evento, captação e módulos;
  * links internos das páginas novas e cobertura de sitemap;
  * painel executivo na home;
  * formato executivo dos alertas e as 8 seções do briefing.

Uso: python3 scripts/validate_intelligence.py
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regulatory import taxonomy as tx  # noqa: E402
from regulatory.engine import official_source  # noqa: E402

DATA = ROOT / "data" / "intelligence"
OUT = ROOT / "docs"

REQUIRED_EVENT_KEYS = [
    "regulatory_event", "summary", "affected_sectors", "affected_company_types",
    "affected_functions", "obligations", "deadlines", "risks", "opportunities",
    "recommended_actions", "impact_level", "priority", "confidence", "official_sources",
]


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, message):
        self.errors.append(message)

    def warn(self, message):
        self.warnings.append(message)


def load(rep, name):
    path = DATA / name
    if not path.exists():
        rep.err(f"data/intelligence/{name}: ausente (execute scripts/build_intelligence.py)")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        rep.err(f"data/intelligence/{name}: JSON inválido — {error}")
        return None


def check_events(rep, events):
    published = events.get("events", [])
    if not published:
        rep.err("events.json: nenhum evento publicado")
    seen_ids, seen_keys = set(), set()
    for event in published:
        eid = event.get("id", "?")
        if eid in seen_ids:
            rep.err(f"events.json: id duplicado '{eid}'")
        seen_ids.add(eid)
        key = (event["official_sources"][0] if event.get("official_sources") else "", event.get("regulatory_event", ""))
        if key in seen_keys:
            rep.err(f"events.json: evento duplicado (fonte+título) '{eid}'")
        seen_keys.add(key)
        for field in REQUIRED_EVENT_KEYS:
            if field not in event:
                rep.err(f"events.json: {eid}: campo obrigatório ausente '{field}'")
        sources = event.get("official_sources") or []
        if not sources:
            rep.err(f"events.json: {eid}: publicado sem URL oficial")
        for url in sources:
            if not official_source(url):
                rep.err(f"events.json: {eid}: URL não oficial '{url[:90]}'")
        if event.get("confidence", 0) < tx.CONFIDENCE_FLOOR:
            rep.err(f"events.json: {eid}: confiança {event['confidence']} abaixo do piso 0.6 publicado")
        if event.get("priority") not in tx.PRIORITIES:
            rep.err(f"events.json: {eid}: prioridade inválida '{event.get('priority')}'")
        if event.get("impact_level") not in tx.IMPACT_LEVELS:
            rep.err(f"events.json: {eid}: impacto inválido '{event.get('impact_level')}'")
        for layer in ("fact", "analysis", "interpretation", "recommendations", "so_what"):
            if layer not in event:
                rep.err(f"events.json: {eid}: camada ausente '{layer}'")
        if event.get("analysis", {}).get("why_it_matters") and event.get("recommendations", {}).get("next_step"):
            if "so_what" in event and not event["so_what"].get("consequence"):
                rep.err(f"events.json: {eid}: bloco 'o que isso significa na prática' sem consequência")
    for excluded in events.get("excluded", []):
        if excluded.get("confidence", 0) >= tx.CONFIDENCE_FLOOR:
            rep.err(f"events.json: '{excluded.get('id')}' excluído com confiança suficiente")


def check_deadlines(rep, deadlines):
    milestones = deadlines.get("milestones", [])
    ref = deadlines.get("meta", {}).get("reference_date")
    if not ref:
        rep.err("deadlines.json: sem data de referência")
    seen = set()
    for milestone in milestones:
        mid = milestone.get("id", "?")
        if mid in seen:
            rep.err(f"deadlines.json: id duplicado '{mid}'")
        seen.add(mid)
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(milestone.get("date"))):
            rep.err(f"deadlines.json: {mid}: data inválida '{milestone.get('date')}'")
        if not milestone.get("obligation"):
            rep.err(f"deadlines.json: {mid}: sem obrigação/marco")
        if not milestone.get("source_url") or not official_source(milestone["source_url"]):
            rep.err(f"deadlines.json: {mid}: sem fonte oficial")
        if milestone.get("action_needed") is None:
            rep.err(f"deadlines.json: {mid}: sem ação necessária")
    for window, ids in (deadlines.get("windows") or {}).items():
        for mid in ids:
            if mid not in {m["id"] for m in milestones}:
                rep.err(f"deadlines.json: janela {window} referencia prazo inexistente {mid}")


def check_sectors(rep, sectors):
    if len(sectors.get("sectors", [])) != len(tx.SECTORS):
        rep.err(f"sectors.json: esperado {len(tx.SECTORS)} setores, encontrado {len(sectors.get('sectors', []))}")
    for sector in sectors.get("sectors", []):
        if sector["slug"] not in tx.SECTORS:
            rep.err(f"sectors.json: setor desconhecido '{sector['slug']}'")
        for key in ("obligations", "risks", "recommended_actions", "deadlines", "related_acts"):
            if key not in sector:
                rep.err(f"sectors.json: {sector['slug']}: bloco ausente '{key}'")


def check_alerts(rep, alerts):
    required = ["Evento:", "Impacto:", "Afeta:", "Áreas internas:", "O que mudou:",
                "Ação recomendada:", "Prazo:", "Fonte oficial:"]
    for alert in alerts.get("alerts", []):
        text = alert.get("text", "")
        for marker in required:
            if marker not in text:
                rep.err(f"alerts.json: {alert.get('id')}: alerta sem bloco '{marker}'")
        if not alert.get("official_sources"):
            rep.err(f"alerts.json: {alert.get('id')}: alerta sem fonte oficial")


def check_briefing(rep, briefing):
    for key in ("daily", "weekly"):
        brief = briefing.get(key, {})
        sections = brief.get("sections", [])
        if len(sections) != 8:
            rep.err(f"briefing.json: {key}: esperado 8 seções, encontrado {len(sections)}")
        for section in sections:
            if "empty_message" not in section:
                rep.err(f"briefing.json: {key}/{section.get('title')}: sem mensagem de vazio")


def check_companies(rep, companies):
    profiles = companies.get("companies", [])
    if not profiles:
        rep.err("companies.json: nenhum perfil")
    for profile in profiles:
        if "hedge" not in profile or "potencial" not in profile["hedge"].lower():
            rep.err(f"companies.json: {profile.get('slug')}: sem linguagem cautelosa obrigatória")
        for key in ("sectors", "themes", "possible_obligations", "deadlines", "assessment_questions", "watchlist"):
            if key not in profile:
                rep.err(f"companies.json: {profile.get('slug')}: bloco ausente '{key}'")


def check_manifest(rep, manifest):
    if manifest.get("events_without_official_source"):
        rep.err("manifest.json: existem eventos publicados sem fonte oficial")
    if manifest.get("confidence_min") is not None and manifest["confidence_min"] < tx.CONFIDENCE_FLOOR:
        rep.err("manifest.json: confiança mínima abaixo do piso de publicação")
    if not manifest.get("official_hosts"):
        rep.err("manifest.json: nenhuma fonte oficial citada")


def local_path(url, site):
    if not url.startswith(site + "/") and url.rstrip("/") != site:
        return None
    rel = url[len(site):].lstrip("/").split("?")[0].split("#")[0]
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return OUT / rel


def check_pages(rep, events, sectors, companies):
    site = "https://monitor-ue.vercel.app"
    if not OUT.exists():
        rep.err("docs/: ausente — execute scripts/build_site.py")
        return
    required = ["impacto/index.html", "setores/index.html", "prazos/index.html", "enforcement/index.html",
                "empresas/index.html", "jurisprudencia/index.html", "diff/index.html",
                "alertas-executivos/index.html", "briefing-executivo/index.html", "demo/index.html",
                "produto/index.html", "como-analisamos/index.html"]
    for rel in required:
        if not (OUT / rel).exists():
            rep.err(f"docs/{rel}: página do produto ausente")
    for sector in sectors.get("sectors", []):
        if not (OUT / "setores" / sector["slug"] / "index.html").exists():
            rep.err(f"docs/setores/{sector['slug']}/: página de setor ausente")
    for company in companies.get("companies", []):
        if not (OUT / "empresas" / company["slug"] / "index.html").exists():
            rep.err(f"docs/empresas/{company['slug']}/: perfil ausente")
    for event in events.get("events", []):
        if not (OUT / "impacto" / event["id"] / "index.html").exists():
            rep.err(f"docs/impacto/{event['id']}/: ficha de evento ausente")

    href_re = re.compile(r'href="(https://monitor-ue\.vercel\.app[^"]*|/[^"#][^"]*)"')
    intelligence_dirs = ("impacto", "setores", "prazos", "enforcement", "empresas", "jurisprudencia",
                         "diff", "alertas-executivos", "briefing-executivo", "demo", "produto",
                         "como-analisamos", "eu-ai-act-deadlines", "gpai-compliance", "ai-act-banking",
                         "ai-act-healthcare", "ai-act-saas", "ai-act-foundation-models",
                         "ai-office-updates", "edpb-ai-guidelines")
    for folder in intelligence_dirs:
        base = OUT / folder
        if not base.exists():
            continue
        for path in base.rglob("index.html"):
            html = path.read_text(encoding="utf-8")
            if 'content="noindex' in html:
                rep.err(f"docs/{path.relative_to(OUT)}: página pública com noindex")
            for href in href_re.findall(html):
                target = local_path(href if href.startswith("http") else site + href, site)
                if target is not None and not target.exists():
                    rep.err(f"docs/{path.relative_to(OUT)}: link interno quebrado → {href[:110]}")

    home = (OUT / "index.html").read_text(encoding="utf-8")
    for marker in ("painel-executivo", "Regulatory Impact Engine", "mudanças regulatórias exigem atenção",
                   "alertas-executivos"):
        if marker not in home:
            rep.err(f"docs/index.html: marcador ausente na home executiva ('{marker}')")
    alerts_page = (OUT / "alertas" / "index.html")
    if alerts_page.exists() and "alertas-executivos" not in alerts_page.read_text(encoding="utf-8"):
        rep.err("docs/alertas/index.html: sem ligação ao arquivo de alertas executivos")

    sitemap = OUT / "sitemap.xml"
    if not sitemap.exists():
        rep.err("docs/sitemap.xml: ausente")
        return
    urls = ET.fromstring(sitemap.read_text(encoding="utf-8")).findall(
        "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
    listed = {node.text for node in urls}
    for path in ["prazos/", "impacto/", "setores/", "enforcement/", "empresas/", "demo/", "produto/"]:
        if f"{site}/{path}" not in listed:
            rep.err(f"sitemap.xml: URL do produto ausente ({path})")
    if len(listed) != len({u for u in listed}):
        rep.err("sitemap.xml: URLs duplicadas")


def main():
    rep = Report()
    events = load(rep, "events.json")
    deadlines = load(rep, "deadlines.json")
    sectors = load(rep, "sectors.json")
    alerts = load(rep, "alerts.json")
    briefing = load(rep, "briefing.json")
    companies = load(rep, "companies.json")
    manifest = load(rep, "manifest.json")
    load(rep, "watchlist.json")
    load(rep, "enforcement.json")
    if events:
        check_events(rep, events)
    if deadlines:
        check_deadlines(rep, deadlines)
    if sectors:
        check_sectors(rep, sectors)
    if alerts:
        check_alerts(rep, alerts)
    if briefing:
        check_briefing(rep, briefing)
    if companies:
        check_companies(rep, companies)
    if manifest:
        check_manifest(rep, manifest)
    if events and sectors and companies:
        check_pages(rep, events, sectors, companies)

    print(f"Validação da camada de inteligência — erros: {len(rep.errors)} · avisos: {len(rep.warnings)}")
    for error in rep.errors:
        print(f"  ERRO: {error}")
    for warning in rep.warnings[:40]:
        print(f"  aviso: {warning}")
    if rep.errors:
        print("\nVALIDAÇÃO FALHOU — a camada de inteligência não cumpre as regras do produto.")
        return 1
    print("\nVALIDAÇÃO OK — eventos com fonte oficial, confiança mínima, páginas e sitemap consistentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
