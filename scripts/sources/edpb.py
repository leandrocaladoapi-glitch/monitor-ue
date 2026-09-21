#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/edpb.py — Coletor do EDPB (European Data Protection Board).

Fonte oficial: RSS do próprio EDPB — https://www.edpb.europa.eu/feed/news_en
Evidência da sonda (18/09/2026): feed ativo com notícias, guidelines adotadas
em plenário, decisões coordenadas e publicações (título, link oficial, data,
descrição rica).

Escopo temático: apenas conteúdo relacionado a IA/dados/decisão automatizada
(guidelines sobre IA generativa, scraping, biometria, decisões automatizadas,
enforcement com impacto sobre sistemas de IA). O filtro conservador do núcleo
comum aplica-se item a item — não importa todo o conteúdo de proteção de
dados indiscriminadamente.
"""
from .base import Canal, Fonte, registrar

FEED = "https://www.edpb.europa.eu/feed/news_en"


@registrar
class EDPB(Fonte):
    orgao = "edpb"
    nome = "EDPB — European Data Protection Board"
    obrigatoria = True
    canais = [
        Canal(
            "notícias e guidelines (RSS oficial)",
            FEED,
            formato="rss", parser="rss",
            tipo_padrao="orientacao",
        ),
    ]
