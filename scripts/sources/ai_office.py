#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/ai_office.py — Coletor da European AI Office (Comissão Europeia).

Fonte oficial: o portal da Comissão para o futuro digital
(digital-strategy.ec.europa.eu), onde a European AI Office publica:

  · notícias e comunicados sobre implementação do AI Act;
  · página da política do AI Act (regulatory framework);
  · página da AI Office e dos General-Purpose AI models;
  · Codes of Practice para GPAI;
  · guidelines, templates e requests for information.

Evidência da sonda (18/09/2026):
  · /en/news?type=5%7C13 (newsroom) responde sem autenticação, com itens
    datados e URL oficial (ex.: "Commission starts enforcing AI Act rules and
    new transparency requirements on 2 August", 31/07/2026);
  · o feed RSS do portal não está disponível publicamente (erro), então o
    canal correto é a listagem oficial em HTML (ordem de preferência 5 do
    projeto).

Filtro temático conservador do núcleo comum: só entra conteúdo com sinal claro
de IA/dados/AI Act; item duvidoso entra como "revisar" (curadoria).
"""
from .base import Canal, Fonte, registrar

PORTAL = "https://digital-strategy.ec.europa.eu"

# Canais oficiais ligados à implementação do AI Act (listagens server-rendered).
LISTAGENS = [
    ("notícias e comunicados do portal", PORTAL + "/en/news?type=5%7C13",
     "noticia"),
    ("página da AI Office (políticas e ações)", PORTAL + "/en/policies/ai-office",
     "institucional"),
    ("AI Act — quadro regulatório e implementação",
     PORTAL + "/en/policies/regulatory-framework-ai", "institucional"),
    ("General-Purpose AI — página oficial", PORTAL + "/en/policies/general-purpose-ai",
     "institucional"),
    ("AI Act — página do serviço", PORTAL + "/en/ai-act", "institucional"),
]


@registrar
class AIOffice(Fonte):
    orgao = "ai_office"
    nome = "European AI Office — Comissão Europeia (digital-strategy)"
    obrigatoria = True
    canais = [
        Canal(rotulo, url, formato="html", parser="eu:parse_comissao_noticias",
              tipo_padrao=tipo, obrigatorio=(i == 0), opcoes={"limite": 60})
        for i, (rotulo, url, tipo) in enumerate(LISTAGENS)
    ]
