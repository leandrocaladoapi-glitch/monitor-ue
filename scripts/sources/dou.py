#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/dou.py — Coletor do Diário Oficial da União (Imprensa Nacional).

Fonte oficial: busca oficial em https://www.in.gov.br/consulta/-/buscar/dou
(a mesma consulta usada pelo site do DOU). A página devolve, em um
`<script type="application/json">`, o array `jsonArray` com título, data,
tipo de ato, hierarquia do órgão, página e o identificador que forma a URL
oficial do ato (`https://www.in.gov.br/web/dou/-/<urlTitle>`).

Canais: um por tema monitorado (IA, algoritmos, proteção de dados, data
centers, semicondutores, biometria, plataformas digitais, nuvem…), em janela
de datas. Cada execução reconsulta a janela e compara com o estado anterior
(atos.json): item novo, alteração de texto ou de status viram registro em
updates.json; ids repetidos são deduplicados.

Não há escrita/estimativa: se a busca não responder, a fonte é marcada como
falha no painel; nenhum ato é criado sem URL oficial do DOU.
"""
from .base import Canal, Fonte, TOPICOS_BUSCA, registrar

BUSCA = "https://www.in.gov.br/consulta/-/buscar/dou"

# Tipos de ato que interessam ao monitor temático (documentado para curadoria).
TIPOS_ATO_INTERESSE = (
    "Lei", "Lei Complementar", "Decreto", "Decreto-Lei", "Decreto Legislativo",
    "Medida Provisória", "Portaria", "Resolução", "Resolução Conjunta",
    "Instrução Normativa", "Provimento", "Enunciado", "Nota Técnica",
    "Consulta Pública", "Edital", "Ato", "Despacho", "Extrato",
)


def url_busca(termo, dias=7, delta=50, extra=None):
    """Monta a URL oficial de busca do DOU para um termo (expressão exata)."""
    from urllib.parse import urlencode

    from .base import BRT, datetime
    hoje = datetime.now(BRT).date()
    inicio = hoje - __import__("datetime").timedelta(days=dias)
    params = {
        "q": f'"{termo}"',
        "s": "todos",
        "exactDate": "personalizado",
        "sortType": "0",
        "delta": str(delta),
        "currentPage": "1",
        "publishFrom": inicio.strftime("%d-%m-%Y"),
        "publishTo": hoje.strftime("%d-%m-%Y"),
    }
    if extra:
        params.update(extra)
    return f"{BUSCA}?{urlencode(params)}"


@registrar
class DOU(Fonte):
    orgao = "dou"
    nome = "DOU — Diário Oficial da União (Imprensa Nacional)"
    obrigatoria = True
    canais = [
        Canal(
            "busca por tema (7 dias)", BUSCA, formato="html", parser="dou_embutido",
            tipo_padrao="publicacao", topicos=TOPICOS_BUSCA, dias=7,
            padrao_href=r"/web/dou/-/",
            url_template=(BUSCA + "?q=%22{topico}%22&s=todos&exactDate=personalizado"
                                  "&sortType=0&delta=50&currentPage=1"
                                  "&publishFrom={from}&publishTo={to}"),
        ),
    ]
