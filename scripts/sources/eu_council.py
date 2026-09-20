#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/eu_council.py — Coletor do Conselho da União Europeia.

Fontes oficiais:

1. Registro público de documentos do Conselho (Document register)
   https://www.consilium.europa.eu/en/documents/public-register/
   A listagem "Latest documents" é server-rendered e traz, para cada documento:
   título, URL oficial do PDF (data.consilium.europa.eu/doc/document/…), assuntos,
   **número do arquivo interinstitucional** (ex.: 2021/0106(COD)) e datas.
   Evidência da sonda (18/09/2026): a listagem responde sem desafio anti-bot e
   os números interinstitucionais aparecem por documento — é a chave que
   relaciona documentos do Conselho aos mesmos dossiês do Parlamento e da
   Comissão.

2. EU Law Tracker (law-tracker.europa.eu) — o tracker oficial dos arquivos
   legislativos em curso (Conselho/Parlamento/Comissão). A sonda confirmou que
   a aplicação exige login para o uso interativo; não há API pública estável
   documentada — por isso NÃO é usado como canal automático (documentado no
   painel de fontes). O estado dos arquivos vem do Parlamento (Open Data) e do
   registro público do Conselho.

O número de arquivo interinstitucional é preservado em cada item
(`arquivo_interinstitucional`) e é a identidade compartilhada entre as
instituições no dataset.
"""
from .base import Canal, Fonte, TOPICOS_BUSCA, registrar

REGISTRO = "https://www.consilium.europa.eu/en/documents/public-register"


@registrar
class EUCouncil(Fonte):
    orgao = "eu_council"
    nome = "Conselho da UE — Registro público de documentos"
    obrigatoria = True
    canais = [
        Canal(
            "últimos documentos adicionados ao registro",
            REGISTRO + "/latest/",
            formato="html", parser="eu:parse_consilium_registro",
            tipo_padrao="documento_conselho", obrigatorio=True,
            opcoes={"limite": 120},
        ),
        # páginas adicionais da listagem (se o servidor aceitar ?page=N)
        Canal(
            "últimos documentos (página 2)",
            REGISTRO + "/latest/?page=2",
            formato="html", parser="eu:parse_consilium_registro",
            tipo_padrao="documento_conselho", obrigatorio=False,
            opcoes={"limite": 80},
        ),
        Canal(
            "documentos legislativos preparatórios (página 1)",
            REGISTRO + "/preparatory-legislative-documents/",
            formato="html", parser="eu:parse_consilium_registro",
            tipo_padrao="documento_conselho", obrigatorio=False,
            opcoes={"limite": 80},
        ),
    ]
