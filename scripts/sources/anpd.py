#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/anpd.py — Coletor da ANPD (Autoridade Nacional de Proteção de Dados).

Fonte oficial: API de conteúdo (plone.restapi) que serve o próprio portal da
ANPD em https://www.gov.br/anpd. É a mesma API que o site usa para renderizar
as páginas — não é scraping de HTML: os itens vêm estruturados (`@id`, `title`,
`description`, `effective`), com data e URL oficial.

Canais:
  · notícias recentes        @search portal_type=News Item (ordenado por data)
  · notícias por tema        @search SearchableText=<tema> (IA, dados, biometria…)
  · regulação/normas         @search path=/pt-br/assuntos/regulacao
  · consultas e participação @search SearchableText=consulta pública / tomada de subsídios
  · atos normativos (arquivos) @search portal_type=File (resoluções em PDF)
  · fiscalização e agenda regulatória @search path=<pasta oficial> (opcionais)

Nada é inventado: se a API não responde, a fonte é marcada como falha e o
evento é registrado no painel; nenhum item é criado por dedução.
"""
from .base import (Canal, Fonte, TOPICOS_BUSCA, registrar)

API = "https://www.gov.br/anpd/++api++/@search"
NOTICIAS = "News Item"


def _ordenado(**params):
    p = {"b_size": 50, "sort_on": "effective", "sort_order": "descending"}
    p.update(params)
    return p


@registrar
class ANPD(Fonte):
    orgao = "anpd"
    nome = "ANPD — Autoridade Nacional de Proteção de Dados"
    obrigatoria = True
    canais = [
        Canal(
            "notícias recentes", API, formato="json", parser="plone_search",
            tipo_padrao="noticia",
            opcoes={"params": _ordenado(portal_type=NOTICIAS)},
        ),
        Canal(
            "notícias por tema", API, formato="json", parser="plone_search",
            tipo_padrao="noticia", topicos=TOPICOS_BUSCA,
            url_template=(API + "?SearchableText={topico}&portal_type="
                          "News%20Item&b_size=20&sort_on=effective&sort_order=descending"),
        ),
        Canal(
            "regulação e normas", API, formato="json", parser="plone_search",
            tipo_padrao="regulamento",
            opcoes={"params": _ordenado(path="/pt-br/assuntos/regulacao")},
        ),
        Canal(
            "consultas públicas", API, formato="json", parser="plone_search",
            tipo_padrao="consulta_publica", obrigatorio=False,
            opcoes={"params": _ordenado(SearchableText="consulta pública")},
        ),
        Canal(
            "tomada de subsídios", API, formato="json", parser="plone_search",
            tipo_padrao="consulta_publica", obrigatorio=False,
            opcoes={"params": _ordenado(SearchableText="tomada de subsídios")},
        ),
        Canal(
            "atos normativos (arquivos)", API, formato="json", parser="plone_search",
            tipo_padrao="ato_normativo", obrigatorio=False,
            opcoes={"params": _ordenado(portal_type="File", SearchableText="resolução")},
        ),
        # Pastas oficiais do portal da ANPD confirmadas na sonda (17/09/2026):
        # /pt-br/assuntos/fiscalizacao e /pt-br/assuntos/agenda-regulatoria
        # respondem 200 na API de conteúdo. São canais opcionais: se a pasta
        # ficar vazia ou o portal responder mal, isso aparece no painel sem
        # afetar o resto da fonte (nada é inventado).
        Canal(
            "fiscalização (pasta oficial)", API, formato="json", parser="plone_search",
            tipo_padrao="fiscalizacao", obrigatorio=False,
            opcoes={"params": _ordenado(path="/pt-br/assuntos/fiscalizacao")},
        ),
        Canal(
            "agenda regulatória (pasta oficial)", API, formato="json",
            parser="plone_search", tipo_padrao="agenda_regulatoria", obrigatorio=False,
            opcoes={"params": _ordenado(path="/pt-br/assuntos/agenda-regulatoria")},
        ),
    ]
