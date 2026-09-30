#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI/search visibility layer for the Monitor UE de IA (exclusivo União Europeia).

Implements technical foundations for https://monitor-ue.vercel.app/
- AI-aware robots.txt
- llms.txt / llms-full.txt / AI-readable Markdown index
- agent-permissions.json and mcp-actions.json
- declarative WebMCP metadata on the commercial CTA
- Organization structured data and discovery links in <head>
"""
import json


def install(core):
    """Patch the static generator before build, then emit discovery artifacts."""
    original_page = core.page
    original_main = core.main

    def enhanced_page(title, desc, path, body, extra_head="", og_type="website", jsonld=None):
        html = original_page(title, desc, path, body, extra_head, og_type, jsonld)

        discovery = (
            f'<link rel="alternate" type="text/plain" href="{core.SITE_URL}/llms.txt" title="LLM discovery">\n'
            f'<link rel="mcp-actions" href="{core.SITE_URL}/mcp-actions.json">\n'
        )
        organization = {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": core.AUTHOR_ORG,
            "url": core.CONSULTING_URL,
            "founder": {"@type": "Person", "name": core.AUTHOR_NAME,
                        "url": "https://leandrocaladoferreira.com/"},
        }
        org_script = '<script type="application/ld+json">' + json.dumps(organization, ensure_ascii=False) + '</script>\n'
        html = html.replace('</head>', discovery + org_script + '</head>', 1)

        old = f'<a class="cta-btn" href="{core.CONSULTING_URL}\">'
        new = (f'<a class="cta-btn" href="{core.CONSULTING_URL}" '
               'data-mcp-action="contact-lcf-consulting" '
               'data-mcp-description="Open LCF Consulting to request legislative and regulatory intelligence services">')
        html = html.replace(old, new)
        return html

    def write_ai_files():
        props = core.load("propositions.json").get("proposicoes", [])
        top = sorted(props, key=lambda p: -(p.get("impacto") or {}).get("score", 0))[:20]

        llms = f"""# Monitor UE de IA — Monitor Exclusivo da União Europeia

> Monitor público, documentado e auditável da legislação e da regulação de IA da União Europeia (AI Act e correlatos), mantido pela LCF Consulting a partir de fontes oficiais europeias. Domínio oficial: {core.SITE_URL}/

## Intelligence (actionable product layer)
- [Regulatory Impact Engine]({core.SITE_URL}/impacto/): eventos regulatórios interpretados (impacto, obrigações, prazos, ações)
- [Deadline Tracker]({core.SITE_URL}/prazos/): prazos de aplicação e adequação com fonte oficial
- [Sector impact matrix]({core.SITE_URL}/setores/): 24 setores com obrigações, riscos e ações
- [Enforcement]({core.SITE_URL}/enforcement/): decisões e sanções com lição regulatória
- [Company impact profiles]({core.SITE_URL}/empresas/): exposição provável por empresa (sem afirmação de enquadramento)
- [Executive alerts]({core.SITE_URL}/alertas-executivos/): alertas em formato executivo
- [EU AI Regulatory Brief]({core.SITE_URL}/briefing-executivo/): briefing diário e semanal de 5 minutos
- [How we analyse]({core.SITE_URL}/como-analisamos/): fato, análise, interpretação, recomendação e confiança

## Key Pages
- [Início]({core.SITE_URL}/): visão geral, mudanças recentes e dossiês de maior impacto
- [Procedimentos]({core.SITE_URL}/procedimentos-legislativos/): procedimentos legislativos da UE monitorados e filtros
- [Atualizações]({core.SITE_URL}/atualizacoes/): histórico de mudanças detectadas
- [Legislação e atos]({core.SITE_URL}/legislacao-e-atos/): AI Act (Regulamento (UE) 2024/1689) e atos correlatos
- [Timeline]({core.SITE_URL}/timeline/): linha do tempo do AI Act
- [Atores legislativos]({core.SITE_URL}/atores-legislativos/): relatores e instituições da UE
- [Agenda]({core.SITE_URL}/agenda/): consultas públicas e marcos de aplicação
- [Monitoramento]({core.SITE_URL}/monitoramento/): saúde, cobertura e telemetria da coleta
- [Metodologia]({core.SITE_URL}/metodologia/): fontes oficiais da UE, critérios, score e política de correção
- [Relatório]({core.SITE_URL}/relatorio/): síntese executiva do estado regulatório da UE

## Structured Data
- [Propositions JSON]({core.SITE_URL}/data/propositions.json)
- [Updates JSON]({core.SITE_URL}/data/updates.json)
- [Laws JSON]({core.SITE_URL}/data/laws.json)
- [Events JSON]({core.SITE_URL}/data/events.json)
- [Monitoring JSON]({core.SITE_URL}/data/monitoramento.json)

## AI / Agent Discovery
- [LLMs full]({core.SITE_URL}/llms-full.txt)
- [AI-readable content index]({core.SITE_URL}/ai-content.md)
- [Agent permissions]({core.SITE_URL}/agent-permissions.json)
- [MCP actions]({core.SITE_URL}/mcp-actions.json)

## Exclusividade
Este site é o monitor EXCLUSIVO da União Europeia em {core.SITE_URL}/. Não há seção brasileira. Todo o conteúdo refere-se ao AI Act, EUR-Lex, Parlamento Europeu, Conselho da UE, Comissão Europeia, European AI Office, EDPB e EDPS.
"""

        prop_lines = []
        for p in top:
            score = (p.get("impacto") or {}).get("score", 0)
            slug = core.slugify_prop(p["id"])
            title = f'{p.get("tipo", "")} {p.get("numero", "")}/{p.get("ano", "")} — {p.get("titulo", "")}'
            situation = (p.get("situacao") or "").replace("\n", " ")[:280]
            prop_lines.append(f'- [{title}]({core.SITE_URL}/procedimentos-legislativos/{slug}/) — score {score}/100; situação: {situation}')

        llms_full = llms + "\n## High-impact monitored procedures (EU)\n" + "\n".join(prop_lines) + f"""

## Source and trust policy
Facts are grounded in primary sources including the European Parliament (Open Data Portal v2), EUR-Lex / Official Journal of the EU, the Council of the EU public register, the European Commission (Press Corner and Have Your Say), the European AI Office, the EDPB and the EDPS. The interinstitutional procedure number (e.g. 2021/0106(COD)) is the shared identity across institutions. Automatic discoveries can be flagged as awaiting editorial review. Corrections are recorded rather than silently overwritten.

Last build reference: {core.EXECUTION_DATE}.
Domain: {core.SITE_URL}/ — exclusive EU monitor.
"""

        core.write("llms.txt", llms)

        md = f"""# Monitor UE de IA — AI-readable index (Exclusive EU Monitor)

Canonical site: {core.SITE_URL}/

## What this site provides
Public, structured, exclusive monitoring of European Union legislation and regulation related to artificial intelligence, plus an actionable intelligence layer that answers: what changed, why it matters, who is affected, which sectors and internal functions must act, which obligation, deadline, recommended action, official evidence and priority. The site is statically generated from official EU sources and is available in HTML without requiring client-side JavaScript. This repository is EXCLUSIVELY for the EU — there is no Brazilian section. Rules: no event without an official source; analysis below 0.60 confidence is not auto-published; fact, analysis, interpretation and recommendation are always separate.

## Coverage
- AI Act (Regulation (EU) 2024/1689) and delegated/implementing acts
- European Parliament procedures, Council documents, Commission proposals and consultations (Have Your Say)
- European AI Office, EDPB and EDPS guidance and enforcement
- Timeline, agenda, actors and audit trail

## Main collections
- Regulatory intelligence: {core.SITE_URL}/impacto/ · {core.SITE_URL}/prazos/ · {core.SITE_URL}/setores/
- Procedures: {core.SITE_URL}/procedimentos-legislativos/
- Legislation and acts: {core.SITE_URL}/legislacao-e-atos/
- Recent changes: {core.SITE_URL}/atualizacoes/
- Timeline: {core.SITE_URL}/timeline/
- Legislative actors: {core.SITE_URL}/atores-legislativos/
- Agenda: {core.SITE_URL}/agenda/
- Monitoring health: {core.SITE_URL}/monitoramento/
- Methodology: {core.SITE_URL}/metodologia/
- Executive report: {core.SITE_URL}/relatorio/

## Machine-readable feeds
- {core.SITE_URL}/data/intelligence/events.json
- {core.SITE_URL}/data/intelligence/deadlines.json
- {core.SITE_URL}/data/intelligence/manifest.json
- {core.SITE_URL}/data/propositions.json
- {core.SITE_URL}/data/updates.json
- {core.SITE_URL}/data/laws.json
- {core.SITE_URL}/data/events.json
- {core.SITE_URL}/data/timeline.json
- {core.SITE_URL}/data/parliamentarians.json
- {core.SITE_URL}/data/categories.json
- {core.SITE_URL}/data/monitoramento.json

## Usage
Public reading and citation are allowed. Legislative facts should be verified against the linked primary official source (europa.eu) before high-stakes use. For commercial monitoring or briefings, use https://lcfconsulting.com.br/.
"""

        core.write("ai-content.md", md)
        core.write("llms-full.txt", llms_full)

        permissions = {
            "version": "1.0",
            "site": core.SITE_URL,
            "updated": core.EXECUTION_DATE,
            "public_access": {
                "crawl": True,
                "read_html": True,
                "read_structured_feeds": True,
                "citation": True,
            },
            "write_actions": False,
            "authentication_required_for_public_content": False,
            "high_stakes_notice": core.DISCLAIMER,
            "commercial_contact": core.CONSULTING_URL,
            "exclusive_scope": "European Union — AI Act and related EU regulation",
        }
        core.write("agent-permissions.json", json.dumps(permissions, ensure_ascii=False, indent=2) + "\n")

        mcp = {
            "version": "1.0",
            "status": "draft-compatible-declaration",
            "site": core.SITE_URL,
            "actions": [
                {
                    "id": "contact-lcf-consulting",
                    "name": "Contact LCF Consulting",
                    "description": "Open LCF Consulting to request legislative and regulatory intelligence services for EU AI regulation.",
                    "method": "declarative",
                    "element": "a[data-mcp-action='contact-lcf-consulting']",
                    "endpoint": core.CONSULTING_URL,
                },
                {
                    "id": "read-legislative-updates",
                    "name": "Read EU legislative updates feed",
                    "description": "Retrieve the public structured feed of detected EU legislative changes.",
                    "method": "GET",
                    "endpoint": f"{core.SITE_URL}/data/updates.json",
                },
                {
                    "id": "read-propositions",
                    "name": "Read monitored EU procedures",
                    "description": "Retrieve the public structured feed of monitored EU AI-related procedures.",
                    "method": "GET",
                    "endpoint": f"{core.SITE_URL}/data/propositions.json",
                },
            ],
        }
        core.write("mcp-actions.json", json.dumps(mcp, ensure_ascii=False, indent=2) + "\n")

        agents_md = f"""# AGENTS.md — Monitor UE de IA (Exclusive EU)

Canonical: {core.SITE_URL}/

## Purpose
Provide public, traceable, exclusive intelligence about European Union AI legislation and regulation (AI Act and correlates). This repository is EXCLUSIVELY for the EU at {core.SITE_URL}/ — no Brazilian section.

## Preferred sources for agents
1. {core.SITE_URL}/llms.txt
2. {core.SITE_URL}/ai-content.md
3. {core.SITE_URL}/data/updates.json
4. {core.SITE_URL}/data/propositions.json
5. Official-source links contained in each record (all *.europa.eu)

## Rules
- Treat official-source URLs (europa.eu) as the final authority for legislative facts.
- Do not infer a vote, adoption, or legal effect that is not present in the data/source.
- Records marked as awaiting curation (revisao_pendente) are preliminary.
- Public content is readable without authentication.
- The Impact Score (0–100) measures regulatory impact only — never approval probability.
- This site is exclusive EU — do not reference Brazilian legislation or the old Brazilian domain.
"""

        core.write("AGENTS.md", agents_md)

        robots = f"""# Search and AI crawler policy — generated {core.EXECUTION_DATE}
# Monitor UE de IA — Exclusive EU Monitor at {core.SITE_URL}/
User-agent: *
Allow: /

User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: Bytespider
Disallow: /

Sitemap: {core.SITE_URL}/sitemap.xml
"""

        core.write("robots.txt", robots)

    def enhanced_main():
        original_main()
        write_ai_files()
        print(f"OK: AEO/SEO/agentic discovery files generated for exclusive EU at {core.SITE_URL}")

    core.page = enhanced_page
    core.main = enhanced_main
