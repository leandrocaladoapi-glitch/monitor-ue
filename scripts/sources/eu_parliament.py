#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/eu_parliament.py — Coletor do Parlamento Europeu.

Fontes oficiais:

1. European Parliament Open Data Portal — API oficial v2
   https://data.europarl.europa.eu/api/v2
   · /procedures (listagem de procedimentos legislativos, filtrável por
     parliamentary_term; JSON-LD)
   · /procedures/{id} (ficha completa: eventos, estágios, votações — consumida
     pelo motor legislativo em update_legislation.py)

   Evidência da sonda (18/09/2026):
   · /procedures?parliamentary_term=10&limit=N responde JSON-LD filtrado;
   · /procedures/2021-0106 devolve a ficha do AI Act com consists_of
     (PLENARY_VOTE, COMMITTEE_ADOPTING_REPORT, PLENARY_REFER_COMMITTEE_
     INTERINSTITUTIONAL_NEGOTIATIONS, PUBLICATION_OFFICIAL_JOURNAL, SIGNATURE),
     com activity_date e occured_at_stage — é dessa ficha que saem estágio,
     votações e datas, sem nunca estimar nada.

2. Legislative Train Schedule — site oficial do Parlamento com o estado
   editorial dos dossiês (canal de descoberta de procedimentos novos).

3. Sala de imprensa do Parlamento (newsroom) — comunicados oficiais.

Camadas de idioma: a coleta usa a versão inglesa (idioma técnico); a
identidade dos itens é o número do procedimento (ex.: 2021/0106(COD)).
"""
from .base import Canal, Fonte, TOPICOS_BUSCA_UE, registrar

API = "https://data.europarl.europa.eu/api/v2"
JSONLD = "application/ld%2Bjson"
TREM = "https://www.europarl.europa.eu/legislative-train"
NEWSROOM = "https://www.europarl.europa.eu/news/en"


@registrar
class EUParliament(Fonte):
    orgao = "eu_parliament"
    nome = "Parlamento Europeu — Open Data Portal v2 / Legislative Train"
    obrigatoria = True
    canais = [
        # Descoberta de procedimentos via API oficial v2 (JSON-LD). A busca
        # por texto é instável na API (sonda 18/09/2026: respostas 500/HTML
        # vazio em alguns parâmetros); o canal é opcional e tolerante. A
        # listagem por termo parlamentar é estável e serve de inventário.
        Canal(
            "API v2 — procedimentos do termo parlamentar corrente",
            f"{API}/procedures?parliamentary_term=10&limit=100&format={JSONLD}",
            formato="json", parser="eu:parse_ep_procedimentos",
            tipo_padrao="procedimento", obrigatorio=True,
            opcoes={"chaves_lista": ["data"]},
        ),
        Canal(
            "API v2 — procedimentos de IA (busca por texto)",
            f"{API}/procedures?text={{topico}}&limit=25&format={JSONLD}",
            formato="json", parser="eu:parse_ep_procedimentos",
            tipo_padrao="procedimento", obrigatorio=False,
            topicos=["artificial intelligence", "AI Act", "GPAI"],
            opcoes={"chaves_lista": ["data"]},
        ),
        # Legislative Train: dossiês digitais (descoberta oficial de arquivos)
        Canal(
            "Legislative Train — Europe fit for the digital age",
            TREM + "/theme-a-europe-fit-for-the-digital-age",
            formato="html", parser="eu:parse_legislative_train",
            tipo_padrao="dossie_parlamento", obrigatorio=False,
        ),
        Canal(
            "Legislative Train — unicidade e poderes de execução",
            TREM + "/file-artificial-intelligence-act",
            formato="html", parser="eu:parse_legislative_train",
            tipo_padrao="dossie_parlamento", obrigatorio=False,
        ),
        # Sala de imprensa (comunicados oficiais sobre IA etc.)
        Canal(
            "sala de imprensa — por tema",
            NEWSROOM + "/press-room?keywords={topico}",
            formato="html", parser="eu:parse_comissao_noticias",
            tipo_padrao="noticia", obrigatorio=False, topicos=TOPICOS_BUSCA_UE[:6],
            opcoes={"limite": 30},
        ),
    ]
