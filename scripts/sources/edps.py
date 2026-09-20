#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/edps.py — Coletor do EDPS (European Data Protection Supervisor).

Fontes oficiais:
  · Press & News — https://www.edps.europa.eu/press-publications/press-news_en
    (listagem server-rendered com comunicados, opiniões e notícias oficiais)
  · Publicações — https://www.edps.europa.eu/data-protection/our-work/publications_en
    (opinions, formal comments, guidelines, tech diplomacy papers)

Evidência da sonda (18/09/2026): o RSS raiz (rss.xml) não está disponível; as
listagens oficiais respondem normalmente — canal HTML conservador (ordem de
preferência 5). Filtro temático de IA/dados/decisão automatizada aplicado
item a item pelo núcleo comum.
"""
from .base import Canal, Fonte, registrar

BASE_EDPS = "https://www.edps.europa.eu"


@registrar
class EDPS(Fonte):
    orgao = "edps"
    nome = "EDPS — European Data Protection Supervisor"
    obrigatoria = True
    canais = [
        Canal(
            "press releases (listagem oficial)",
            BASE_EDPS + "/press-publications/press-news/press-releases_en",
            formato="html", parser="eu:parse_edps_listagem",
            tipo_padrao="comunicado", opcoes={"limite": 50},
        ),
        Canal(
            "notícias oficiais (listagem)",
            BASE_EDPS + "/press-publications/press-news/news_en",
            formato="html", parser="eu:parse_edps_listagem",
            tipo_padrao="noticia", obrigatorio=False, opcoes={"limite": 50},
        ),
        Canal(
            "publicações (opiniões e guidelines)",
            BASE_EDPS + "/data-protection/our-work/publications_en",
            formato="html", parser="eu:parse_edps_listagem",
            tipo_padrao="orientacao", obrigatorio=False, opcoes={"limite": 50},
        ),
    ]
