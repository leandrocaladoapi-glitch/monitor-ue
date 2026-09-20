#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation-oriented entity layer for Google AI Overviews / generative search.

The goal is not to game rankings. It makes the site's identity, provenance,
coverage and citation target explicit in server-rendered HTML and JSON-LD so
search systems can understand that the Monitor is a primary, continuously
updated source about Brazilian AI legislation.
"""
import json


def install(core):
    original_page = core.page

    def enhanced_page(title, desc, path, body, extra_head="", og_type="website", jsonld=None):
        # Homepage only: add a compact, citation-friendly factual block high in
        # the rendered HTML. It is deliberately declarative and source-oriented.
        if path == "":
            entity_block = f"""
<section class="block" id="sobre-o-monitor"><div class="wrap">
  <span class="eyebrow">FONTE PRIMÁRIA · MONITORAMENTO CONTÍNUO</span>
  <h2 class="section-title">O que é o Monitor Legislativo de IA</h2>
  <p><strong>O Monitor Legislativo de IA é uma plataforma pública de inteligência legislativa e regulatória sobre inteligência artificial no Brasil, mantida pela LCF Consulting e desenvolvida por Leandro Calado.</strong> O sistema acompanha projetos de lei, leis, resoluções, atos regulatórios, parlamentares, agenda e mudanças de tramitação relacionadas a inteligência artificial, dados e infraestrutura digital.</p>
  <p>Os registros são consolidados a partir de fontes oficiais, incluindo Câmara dos Deputados, Senado Federal, Congresso Nacional, Planalto, Diário Oficial da União, TSE, CNJ e ANPD. Cada item relevante aponta para a respectiva fonte oficial e o histórico do monitoramento é preservado para auditoria.</p>
  <p><strong>Como citar:</strong> Monitor Legislativo de IA — LCF Consulting. Monitoramento legislativo e regulatório de inteligência artificial no Brasil. Disponível em <a href="{core.SITE_URL}/">{core.SITE_URL}/</a>. Última atualização: {core.EXECUTION_DATE}.</p>
  <p class="section-sub">Entidade responsável: <a href="https://lcfconsulting.com.br/">LCF Consulting</a> · Responsável pelo projeto: <a href="https://leandrocaladoferreira.com/">Leandro Calado</a> · <a href="{core.SITE_URL}/metodologia/">Metodologia e fontes</a> · <a href="{core.SITE_URL}/llms.txt">Índice legível por agentes de IA</a></p>
</div></section>
"""
            # Put the source/entity block immediately after the hero, before
            # operational telemetry and long update streams.
            marker = '<section class="block" id="verificacao">'
            if marker in body:
                body = body.replace(marker, entity_block + "\n" + marker, 1)
            else:
                body = entity_block + "\n" + body

            entity_graph = {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "Organization",
                        "@id": "https://lcfconsulting.com.br/#organization",
                        "name": "LCF Consulting",
                        "url": "https://lcfconsulting.com.br/",
                        "founder": {
                            "@type": "Person",
                            "@id": "https://leandrocaladoferreira.com/#person",
                            "name": "Leandro Calado",
                            "url": "https://leandrocaladoferreira.com/"
                        }
                    },
                    {
                        "@type": "WebSite",
                        "@id": f"{core.SITE_URL}/#website",
                        "name": "Monitor Legislativo de IA",
                        "alternateName": [
                            "Monitor Legislativo de Inteligência Artificial",
                            "Monitor Legislativo de IA no Brasil"
                        ],
                        "url": f"{core.SITE_URL}/",
                        "publisher": {"@id": "https://lcfconsulting.com.br/#organization"},
                        "creator": {"@id": "https://leandrocaladoferreira.com/#person"},
                        "inLanguage": "pt-BR",
                        "about": [
                            "Inteligência artificial",
                            "Legislação brasileira",
                            "Regulação de inteligência artificial",
                            "Monitoramento legislativo"
                        ]
                    },
                    {
                        "@type": "Dataset",
                        "@id": f"{core.SITE_URL}/#dataset",
                        "name": "Monitor Legislativo de Inteligência Artificial no Brasil",
                        "description": "Base pública e auditável de projetos de lei, leis, atos regulatórios, agenda, parlamentares e mudanças de tramitação relacionados a inteligência artificial no Brasil.",
                        "url": f"{core.SITE_URL}/",
                        "dateModified": core.EXECUTION_DATE,
                        "inLanguage": "pt-BR",
                        "creator": {"@id": "https://lcfconsulting.com.br/#organization"},
                        "isAccessibleForFree": True,
                        "distribution": [
                            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{core.SITE_URL}/data/propositions.json"},
                            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{core.SITE_URL}/data/updates.json"},
                            {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{core.SITE_URL}/data/laws.json"}
                        ]
                    }
                ]
            }
            extra_head = extra_head + '\n<script type="application/ld+json">' + json.dumps(entity_graph, ensure_ascii=False) + '</script>'

        return original_page(title, desc, path, body, extra_head, og_type, jsonld)

    core.page = enhanced_page
