#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point do build EXCLUSIVO UE — Monitor da União Europeia.

Gera o site completo da UE na raiz /docs com domínio oficial
https://monitor-ue.vercel.app/ a partir de /data/legislation-eu.
Este repositório agora é exclusivo da União Europeia — não há mais
monitor brasileiro na raiz.
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

import build_site_eu_core as _core
import ai_visibility_eu as _ai_visibility
import google_ai_citation_eu as _google_ai_citation
import commercial_pages as _commercial

SITE_URL = "https://monitor-ue.vercel.app"
OLD_SITE_URLS = [
    "https://monitor.lcfconsulting.com.br",
    "https://monitor.lcfconsulting.com.br/uniao-europeia",
    "https://monitor-legislativo-five.vercel.app",
    "lcaladoferreira.github.io/monitor-legislativo",
]

# Domínio + dataset exclusivos UE em toda a geração
_core.SITE_URL = SITE_URL
_core.OUT = os.path.join(BASE, "docs")
_core.DATA = os.path.join(BASE, "data", "legislation-eu")
_core.SITE_NAME = "Monitor UE de IA"
_core.TAGLINE = "Monitoramento público, documentado e auditável da legislação e da regulação de IA da União Europeia"

_ai_visibility.install(_core)
_google_ai_citation.install(_core)
_commercial.install(_core)

# Preserva compatibilidade para qualquer código/teste que importe build_site.
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


def _assert_domain_migration():
    """Falha o build se qualquer artefato crítico ainda publicar domínio antigo."""
    critical = [
        "sitemap.xml",
        "robots.txt",
        "llms.txt",
        "llms-full.txt",
        "ai-content.md",
        "agent-permissions.json",
        "mcp-actions.json",
        "index.html",
    ]
    problems = []
    for rel in critical:
        path = os.path.join(_core.OUT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            content = f.read()
        for old in OLD_SITE_URLS:
            # ignora se o old for substring do novo? Não, queremos bloquear todos antigos
            if old in content and old != SITE_URL:
                # evita falso positivo quando old está contido no novo? não se aplica aqui
                problems.append(f"{rel} contém {old}")
                break
    if problems:
        raise RuntimeError(
            "Build bloqueado: domínio antigo ainda presente: " + "; ".join(problems)
        )

    sitemap = os.path.join(_core.OUT, "sitemap.xml")
    if not os.path.isfile(sitemap):
        raise RuntimeError("Build bloqueado: docs/sitemap.xml não foi gerado")
    with open(sitemap, encoding="utf-8") as f:
        xml = f.read()
    if f"<loc>{SITE_URL}/" not in xml:
        raise RuntimeError(f"Build bloqueado: sitemap.xml não usa o domínio oficial {SITE_URL}")


if __name__ == "__main__":
    _core.main()
    _assert_domain_migration()
    print(f"OK: site UE exclusivo validado em {SITE_URL} — {len(OLD_SITE_URLS)} domínios antigos verificados")
