#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point do build do MONITOR UE exclusivo (compatibilidade).

Gera o site da União Europeia em docs/ (raiz) com canonical/OG/sitemap
sob https://monitor-ue.vercel.app/ — este repositório agora é exclusivo
da UE. Mantido para compatibilidade com workflows antigos que chamavam
build_site_eu.py; agora produz o mesmo resultado que build_site.py.
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
]

_core.SITE_URL = SITE_URL
_core.OUT = os.path.join(BASE, "docs")
_core.DATA = os.path.join(BASE, "data", "legislation-eu")
_core.SITE_NAME = "Monitor UE de IA"
_core.TAGLINE = "Monitoramento público, documentado e auditável da legislação e da regulação de IA da União Europeia"

_ai_visibility.install(_core)
_google_ai_citation.install(_core)
_commercial.install(_core)

for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


def _assert_domain_migration():
    critical = ["sitemap.xml", "robots.txt", "llms.txt", "llms-full.txt",
                "ai-content.md", "agent-permissions.json", "mcp-actions.json",
                "index.html"]
    problems = []
    for rel in critical:
        path = os.path.join(_core.OUT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            content = f.read()
        for old in OLD_SITE_URLS:
            if old in content:
                problems.append(f"{rel} contém {old}")
                break
    if problems:
        raise RuntimeError(
            "Build bloqueado: domínio antigo ainda presente em: " + "; ".join(problems)
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
    print(f"OK: site UE exclusivo validado em {SITE_URL}")
