#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI/search visibility layer for the Monitor Legislativo de IA.

Implements technical foundations without changing title/H1/keyword targeting:
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

        # Declarative WebMCP on the existing high-value task: contacting LCF Consulting.
        old = f'<a class="cta-btn" href="{core.CONSULTING_URL}">'
        new = (f'<a class="cta-btn" href="{core.CONSULTING_URL}" '
               'data-mcp-action="contact-lcf-consulting" '
               'data-mcp-description="Open LCF Consulting to request legislative and regulatory intelligence services">')
        html = html.replace(old, new)
        return html

    def write_ai_files():
        props = core.load("propositions.json").get("proposicoes", [])
        top = sorted(props, key=lambda p: -(p.get("impacto") or {}).get("score", 0))[:20]

        llms = f"""# Monitor Legislativo de IA

> Monitor público e auditável da legislação brasileira de Inteligência Artificial, mantido pela LCF Consulting a partir de fontes oficiais.

## Key Pages
- [Início]({core.SITE_URL}/): visão geral, mudanças recentes e matérias de maior impacto
- [Proposições]({core.SITE_URL}/proposicoes/): projetos de lei monitorados e filtros
- [Atualizações]({core.SITE_URL}/atualizacoes/): histórico de mudanças detectadas
- [Leis e normas]({core.SITE_URL}/leis/): normas vigentes relacionadas a IA
- [Agenda]({core.SITE_URL}/agenda/): eventos e marcos futuros
- [Monitoramento]({core.SITE_URL}/monitoramento/): saúde, cobertura e telemetria da coleta
- [Metodologia]({core.SITE_URL}/metodologia/): fontes, critérios, score e política de correção
- [Relatório]({core.SITE_URL}/relatorio/): síntese executiva do estado regulatório

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

## Commercial
- [Diagnóstico regulatório]({core.SITE_URL}/diagnostico/): solicite uma conversa sobre exposição regulatória.
- [Soluções]({core.SITE_URL}/solucoes/): escopos de contratação.
- [Briefing executivo]({core.SITE_URL}/briefing-executivo/): amostra com fonte oficial e interpretação separadas.
"""
        core.write("llms.txt", llms)

        prop_lines = []
        for p in top:
            score = (p.get("impacto") or {}).get("score", 0)
            slug = core.slugify_prop(p["id"])
            title = f'{p.get("tipo", "")} {p.get("numero", "")}/{p.get("ano", "")} — {p.get("titulo", "")}'
            situation = (p.get("situacao") or "").replace("\n", " ")[:280]
            prop_lines.append(f'- [{title}]({core.SITE_URL}/proposicoes/{slug}/) — score {score}/100; situação: {situation}')

        llms_full = llms + "\n## High-impact monitored propositions\n" + "\n".join(prop_lines) + f"""

## Source and trust policy
Facts are grounded in primary sources including Câmara dos Deputados, Senado Federal, Congresso Nacional, Planalto, Diário Oficial da União, TSE, CNJ and ANPD. Automatic discoveries can be flagged as awaiting editorial review. Corrections are recorded rather than silently overwritten.

Last build reference: {core.EXECUTION_DATE}.
"""
        core.write("llms-full.txt", llms_full)

        md = f"""# Monitor Legislativo de IA — AI-readable index

Canonical site: {core.SITE_URL}/

## What this site provides
Public, structured monitoring of Brazilian federal legislation and regulation related to artificial intelligence. The site is statically generated, so the core content is available in HTML without requiring client-side JavaScript.

## Main collections
- Propositions: {core.SITE_URL}/proposicoes/
- Recent changes: {core.SITE_URL}/atualizacoes/
- Laws and regulations: {core.SITE_URL}/leis/
- Timeline: {core.SITE_URL}/timeline/
- Parliamentary actors: {core.SITE_URL}/parlamentares/
- Agenda: {core.SITE_URL}/agenda/
- Monitoring health: {core.SITE_URL}/monitoramento/
- Methodology: {core.SITE_URL}/metodologia/
- Executive report: {core.SITE_URL}/relatorio/

## Machine-readable feeds
- {core.SITE_URL}/data/propositions.json
- {core.SITE_URL}/data/updates.json
- {core.SITE_URL}/data/laws.json
- {core.SITE_URL}/data/events.json
- {core.SITE_URL}/data/timeline.json
- {core.SITE_URL}/data/parliamentarians.json
- {core.SITE_URL}/data/categories.json
- {core.SITE_URL}/data/monitoramento.json

## Usage
Public reading and citation are allowed. Legislative facts should be verified against the linked primary official source before high-stakes use. For commercial monitoring or briefings, use https://lcfconsulting.com.br/.
"""
        core.write("ai-content.md", md)

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
                    "description": "Open LCF Consulting to request legislative and regulatory intelligence services.",
                    "method": "declarative",
                    "element": "a[data-mcp-action='contact-lcf-consulting']",
                    "endpoint": core.CONSULTING_URL,
                },
                {
                    "id": "read-legislative-updates",
                    "name": "Read legislative updates feed",
                    "description": "Retrieve the public structured feed of detected legislative changes.",
                    "method": "GET",
                    "endpoint": f"{core.SITE_URL}/data/updates.json",
                },
                {
                    "id": "read-propositions",
                    "name": "Read monitored propositions",
                    "description": "Retrieve the public structured feed of monitored AI-related propositions.",
                    "method": "GET",
                    "endpoint": f"{core.SITE_URL}/data/propositions.json",
                },
            ],
        }
        core.write("mcp-actions.json", json.dumps(mcp, ensure_ascii=False, indent=2) + "\n")

        agents_md = f"""# AGENTS.md — Monitor Legislativo de IA

Canonical: {core.SITE_URL}/

## Purpose
Provide public, traceable intelligence about Brazilian AI legislation and regulation.

## Preferred sources for agents
1. {core.SITE_URL}/llms.txt
2. {core.SITE_URL}/ai-content.md
3. {core.SITE_URL}/data/updates.json
4. {core.SITE_URL}/data/propositions.json
5. Official-source links contained in each record

## Rules
- Treat official-source URLs as the final authority for legislative facts.
- Do not infer a vote, sanction, veto, rapporteur or legal effect that is not present in the data/source.
- Records marked as awaiting curation are preliminary.
- Public content is readable without authentication.
- Commercial requests go to {core.SITE_URL}/diagnostico/.
"""
        core.write("AGENTS.md", agents_md)

        robots = f"""# Search and AI crawler policy — generated {core.EXECUTION_DATE}
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
        print("OK: AEO/SEO/agentic discovery files generated.")

    core.page = enhanced_page
    core.main = enhanced_main

