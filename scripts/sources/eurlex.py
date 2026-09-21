#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/eurlex.py — Coletor do EUR-Lex + Jornal Oficial da União Europeia.

O EUR-Lex é a publicação oficial do direito da UE. O webservice SOAP do
EUR-Lex exige credencial; conforme a ordem de preferência do projeto, usamos
as vias públicas oficiais equivalentes:

1. Busca oficial do EUR-Lex (search.html?text=…&type=quick&scope=EURLEX) — a
   mesma consulta do site, com resultados server-rendered contendo CELEX,
   ELI, data do documento, referência do JO, status ("In force") e link da
   última versão consolidada. Evidência da sonda (18/09/2026): a busca por
   "artificial intelligence" devolve o AI Act (32024R1689) com todos esses
   campos — parseáveis de forma estável.

2. RSS oficial do EUR-Lex — display-feed.rss (ex.: rssId=222, atos do JO
   série L), para publicação de novos atos no Jornal Oficial.

Canais:
  · busca por tema (ano corrente e anterior) — legislação relacionada a IA
  · atos do JO série L (RSS oficial)
  · fichas de atos âncora (AI Act consolidado) — acompanhamento de mudanças

CELEX é preservado como identificador em todo item. Versões linguísticas não
geram itens duplicados: a identidade é o CELEX/URL canônica e a coleta usa a
versão inglesa.
"""
from .base import Canal, Fonte, TOPICOS_BUSCA_UE, registrar
from .eu_parsers import parse_eurlex_rss

EURLEX = "https://eur-lex.europa.eu"

# Título consolidado do AI Act (ato âncora do monitor).
AI_ACT_CONSOLIDADO = (EURLEX + "/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727")


@registrar
class EurLex(Fonte):
    orgao = "eurlex"
    nome = "EUR-Lex — Jornal Oficial da União Europeia (Publications Office)"
    obrigatoria = True
    canais = [
        Canal(
            "busca por tema (legislação do ano corrente)",
            (EURLEX + "/search.html?text=%22{topico}%22&scope=EURLEX&type=quick"
                      "&amount=25&page=1&DD_YEAR={year}"),
            formato="html", parser="eu:parse_eurlex_busca",
            tipo_padrao="ato_ue", topicos=TOPICOS_BUSCA_UE[:8],
        ),
        Canal(
            "busca por tema (legislação do ano anterior)",
            (EURLEX + "/search.html?text=%22{topico}%22&scope=EURLEX&type=quick"
                      "&amount=25&page=1&DD_YEAR={prev_year}"),
            formato="html", parser="eu:parse_eurlex_busca",
            tipo_padrao="ato_ue", obrigatorio=False, topicos=TOPICOS_BUSCA_UE[:8],
        ),
        Canal(
            "atos do Jornal Oficial — série L (RSS oficial)",
            EURLEX + "/EN/display-feed.rss?rssId=222",
            formato="rss", parser="rss", extrai=None,
            tipo_padrao="publicacao_jo", obrigatorio=False,
            opcoes={"pos": "eu:parse_eurlex_rss"},
        ),
        Canal(
            "AI Act — versão consolidada (ato âncora)",
            AI_ACT_CONSOLIDADO,
            formato="html", parser="eu:parse_eurlex_consolidado",
            tipo_padrao="norma_vigente", obrigatorio=False,
        ),
    ]
