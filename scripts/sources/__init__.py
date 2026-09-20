#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sources/__init__.py — catálogo dos coletores de fontes oficiais da UE.

O motor legislativo (procedimentos do Parlamento Europeu) roda em
`scripts/update_legislation.py` (camada legislativa, como na arquitetura
original). Este pacote acrescenta os conectores regulatórios multiórgão:

    eu_parliament · eurlex · eu_council · eu_commission · ai_office
    edpb · edps

Todos seguem o mesmo contrato: `Fonte.coletar(ctx, resultado)` devolve itens
normalizados (título, data, URL oficial, descrição) ou levanta
`FonteIndisponivel` — nunca preenche lacunas com dado estimado. Fontes
brasileiras (ANPD, CNJ, TSE, DOU, Planalto, MCTI, Câmara, Senado) foram
removidas deste monitor.
"""
from .base import (  # noqa: F401
    Canal, Cliente, ContextoFonte, Fonte, FonteIndisponivel, OrcamentoEsgotado,
    ResultadoFonte, classificar_relevancia, fontes_disponiveis, instanciar,
    registrar, TOPICOS_BUSCA,
)

# Importa os módulos para registrar as fontes no catálogo (efeito de importação).
from . import (  # noqa: E402,F401
    ai_office, edpb, edps, eu_commission, eu_council, eu_parliament, eurlex,
)

__all__ = ["Canal", "Cliente", "ContextoFonte", "Fonte", "FonteIndisponivel",
           "OrcamentoEsgotado", "ResultadoFonte", "classificar_relevancia",
           "fontes_disponiveis", "instanciar", "registrar", "TOPICOS_BUSCA",
           "ai_office", "edpb", "edps", "eu_commission", "eu_council",
           "eu_parliament", "eurlex"]
