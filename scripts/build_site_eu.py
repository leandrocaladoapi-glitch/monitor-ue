#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Entry point do build do MONITOR UE (seção adicional do site).

Gera o site da União Europeia em docs/uniao-europeia/ com canonical/OG/
sitemap sob https://monitor.lcfconsulting.com.br/uniao-europeia — o monitor
brasileiro permanece na raiz (scripts/build_site.py), intacto. Este build não
gera a camada comercial (produto do monitor BR) nem os arquivos AEO da raiz.
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

import build_site_eu_core as _core
import ai_visibility_eu as _ai_visibility
import google_ai_citation_eu as _google_ai_citation

SITE_URL = "https://monitor.lcfconsulting.com.br/uniao-europeia"
OLD_SITE_URL = "https://monitor-legislativo-five.vercel.app"

# Domínio + prefixo da seção EU em toda a geração (canonical, OG, sitemap,
# navegação, JSON-LD, links de dados). OUT sob docs/uniao-europeia/.
_core.SITE_URL = SITE_URL
_core.OUT = os.path.join(BASE, "docs", "uniao-europeia")
_core.DATA = os.path.join(BASE, "data", "legislation-eu")
_ai_visibility.install(_core)
_google_ai_citation.install(_core)

# Preserva compatibilidade para qualquer código/teste que importe o módulo.
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


def _assert_domain_migration():
    """Falha o build se qualquer artefato crítico ainda publicar o domínio antigo."""
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
        if OLD_SITE_URL in content:
            problems.append(rel)
    if problems:
        raise RuntimeError(
            "Build bloqueado: domínio antigo ainda presente em: " + ", ".join(problems)
        )

    sitemap = os.path.join(_core.OUT, "sitemap.xml")
    if not os.path.isfile(sitemap):
        raise RuntimeError("Build bloqueado: docs/uniao-europeia/sitemap.xml não foi gerado")
    with open(sitemap, encoding="utf-8") as f:
        xml = f.read()
    if f"<loc>{SITE_URL}/" not in xml:
        raise RuntimeError("Build bloqueado: sitemap.xml não usa o domínio oficial da seção UE")


if __name__ == "__main__":
    _core.main()
    _assert_domain_migration()
    print(f"OK: sitemap e arquivos críticos validados em {SITE_URL}")
