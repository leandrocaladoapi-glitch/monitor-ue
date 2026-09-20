#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sources/__init__.py — catálogo dos coletores multiórgão (BR + UE).

Dois monitores compartilham esta infraestrutura:

  * Monitor Legislativo de IA no Brasil — Câmara e Senado continuam em
    `scripts/update_legislation.py` (coletores originais, intocados); este
    pacote acrescenta ANPD, CNJ, TSE, DOU, Planalto e MCTI.
  * Monitor Legislativo e Regulatório de IA da União Europeia — motor em
    `scripts/update_legislation_eu.py` (procedimentos interinstitucionais);
    este pacote acrescenta eu_parliament, eurlex, eu_council, eu_commission,
    ai_office, edpb e edps.

Todos seguem o mesmo contrato: `Fonte.coletar(ctx, resultado)` devolve itens
normalizados (título, data, URL oficial, descrição) ou levanta
`FonteIndisponivel` — nunca preenche lacunas com dado estimado.
"""
from .base import (  # noqa: F401
    Canal, Cliente, ContextoFonte, Fonte, FonteIndisponivel, OrcamentoEsgotado,
    ResultadoFonte, classificar_relevancia, fontes_disponiveis, instanciar,
    registrar, TOPICOS_BUSCA, TOPICOS_BUSCA_UE,
)

# Importa os módulos para registrar as fontes no catálogo (efeito de importação).
from . import (  # noqa: E402,F401
    anpd, cnj, tse, dou, planalto, mcti,
    ai_office, edpb, edps, eu_commission, eu_council, eu_parliament, eurlex,
)

__all__ = ["Canal", "Cliente", "ContextoFonte", "Fonte", "FonteIndisponivel",
           "OrcamentoEsgotado", "ResultadoFonte", "classificar_relevancia",
           "fontes_disponiveis", "instanciar", "registrar", "TOPICOS_BUSCA",
           "TOPICOS_BUSCA_UE", "anpd", "cnj", "tse", "dou", "planalto", "mcti",
           "ai_office", "edpb", "edps", "eu_commission", "eu_council",
           "eu_parliament", "eurlex"]
