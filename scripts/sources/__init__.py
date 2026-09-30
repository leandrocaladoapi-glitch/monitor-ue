#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sources/__init__.py — catálogo dos coletores oficiais da União Europeia.

Este repositório é exclusivo do monitor da União Europeia: o motor está em
`scripts/update_legislation_eu.py` (procedimentos interinstitucionais) e este
pacote acrescenta eu_parliament, eurlex, eu_council, eu_commission, ai_office,
edpb e edps.

Contrato único: `Fonte.coletar(ctx, resultado)` devolve itens normalizados
(título, data, URL oficial, descrição) ou levanta `FonteIndisponivel` — nunca
preenche lacunas com dado estimado.
"""
from .base import (  # noqa: F401
    Canal, Cliente, ContextoFonte, Fonte, FonteIndisponivel, OrcamentoEsgotado,
    ResultadoFonte, classificar_relevancia, fontes_disponiveis, instanciar,
    registrar, TOPICOS_BUSCA_UE,
)

# Importa os módulos para registrar as fontes no catálogo (efeito de importação).
from . import (  # noqa: E402,F401
    ai_office, edpb, edps, eu_commission, eu_council, eu_parliament, eurlex,
)

__all__ = ["Canal", "Cliente", "ContextoFonte", "Fonte", "FonteIndisponivel",
           "OrcamentoEsgotado", "ResultadoFonte", "classificar_relevancia",
           "fontes_disponiveis", "instanciar", "registrar", "TOPICOS_BUSCA_UE",
           "ai_office", "edpb", "edps", "eu_commission", "eu_council",
           "eu_parliament", "eurlex"]
