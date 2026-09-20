#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/eu_commission.py — Coletor da Comissão Europeia.

Fontes oficiais:

1. Press Corner da Comissão — RSS oficial
   https://ec.europa.eu/commission/presscorner/api/rss?language=en
   Evidência da sonda (18/09/2026): feed ativo com comunicados oficiais
   (título, data, área temática e URL oficial do comunicado).

2. Have Your Say — portal oficial de consultas públicas e chamadas por
   evidências da Comissão (Better Regulation):
   https://ec.europa.eu/info/law/better-regulation/have-your-say/
   A listagem é server-rendered e traz estágio (call for evidence, draft act,
   public consultation), tipo de ato (incluindo *delegated acts* e
   *implementing acts*) e o período de feedback — de onde sai o deadline
   verificável da consulta. Evidência da sonda (18/09/2026): listagem responde
   sem autenticação, com 4116 iniciativas e paginação.

Nada de imprensa de terceiros: só canais da própria Comissão.
"""
from .base import Canal, Fonte, TOPICOS_BUSCA, registrar

PRESSCORNER = "https://ec.europa.eu/commission/presscorner/api/rss?language=en"
HYS = "https://ec.europa.eu/info/law/better-regulation/have-your-say/initiatives_en"


@registrar
class EUCommission(Fonte):
    orgao = "eu_commission"
    nome = "Comissão Europeia — Press Corner e Have Your Say"
    obrigatoria = True
    canais = [
        Canal(
            "comunicados oficiais (Press Corner, RSS)",
            PRESSCORNER,
            formato="rss", parser="rss",
            tipo_padrao="comunicado",
        ),
        Canal(
            "consultas públicas e calls for evidence (Have Your Say)",
            HYS + "?page=1",
            formato="html", parser="eu:parse_consultas_hys",
            tipo_padrao="consulta_publica",
            opcoes={"param_pagina": "page", "limite": 40},
        ),
        Canal(
            "consultas públicas (Have Your Say, página 2)",
            HYS + "?page=2",
            formato="html", parser="eu:parse_consultas_hys",
            tipo_padrao="consulta_publica", obrigatorio=False,
            opcoes={"param_pagina": "page", "limite": 40},
        ),
        Canal(
            "consultas por tema (Have Your Say, keywords)",
            HYS + "?keywords={topico}",
            formato="html", parser="eu:parse_consultas_hys",
            tipo_padrao="consulta_publica", obrigatorio=False,
            topicos=["artificial intelligence", "AI Act", "GPAI", "algorithm",
                     "facial recognition", "data centre"],
            opcoes={"limite": 30},
        ),
    ]
