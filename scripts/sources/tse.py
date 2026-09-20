#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/tse.py — Coletor do TSE (Tribunal Superior Eleitoral).

Fontes oficiais (as duas provadas em execução real na CI):

1. API de conteúdo do próprio portal do TSE (plone.restapi) — a mesma API que o
   site usa para renderizar as páginas. Devolve itens estruturados (`@id` = URL
   oficial, `title`, `description`, `effective`):
     · notícias  — portal_type=Noticia  (18.650 itens no acervo)
     · atos      — path=/legislacao     (21.226 atos, type_title "Ato":
       resoluções, portarias, instruções publicadas pelo Tribunal)

2. Busca oficial do Diário Oficial da União (Imprensa Nacional) — resoluções e
   atos do TSE também são publicados na Seção 1 sob "Poder Judiciário/Tribunal
   Superior Eleitoral"; a hierarquia devolvida pelo próprio DOU é conferida item
   a item antes de entrar no dataset.

Evidência da sonda (CI, 17/09/2026):
  · `++api++/@search` responde 200 JSON com os cabeçalhos do coletor quando é a
    primeira consulta daquele IP no período; depois do uso seguido (as sondas
    fazem ~9 chamadas antes do ensaio) o WAF do portal passa a devolver 403 —
    por isso o coletor repete a chamada 403 com espera de 20s e, se ainda
    assim falhar, o canal aparece como falho no painel (nada é inventado). As
    páginas HTML equivalentes (`/comunicacao/noticias`, `/legislacao/compilada`)
    alternam do mesmo modo, então não são usadas.
  · a busca do DOU com `s=titulo` devolveu zero para `orgPrin=Poder Judiciário`;
    com `s=todos` + `orgSub=Tribunal Superior Eleitoral` devolve os atos do TSE.

Nada é inventado: canal que não responde entra como falho no painel; item sem
sinal temático claro é descartado e item duvidoso entra marcado como "revisar".
"""
from .base import (Canal, Fonte, TOPICOS_BUSCA, normalizar, registrar)

API = "https://www.tse.jus.br/++api++/@search"
BUSCA = "https://www.in.gov.br/consulta/-/buscar/dou"
ORGAO_JUDICIARIO = "Poder Judiciário"
TSE_CHAVES = ("tribunal superior eleitoral", "justica eleitoral")

# Listagem ordenada por data (mais recentes primeiro), como o coletor da ANPD.
ATOS_NO_PORTAL = {
    "b_size": 50, "sort_on": "effective", "sort_order": "descending",
    "path": "/legislacao",
}
NOTICIAS_NO_PORTAL = {
    "b_size": 50, "sort_on": "effective", "sort_order": "descending",
    "portal_type": "Noticia",
}


def _filtro_tse(item):
    """Mantém apenas atos cuja hierarquia do DOU é do TSE/Justiça Eleitoral."""
    hier = normalizar(item.get("hierarquia") or "")
    return any(c in hier for c in TSE_CHAVES)


def _filtro_resolucao_tse(item):
    """Atos do TSE que são resolução (norma que o monitoramento persegue).

    É `startswith` porque o DOU rotula ora "Resolução", ora "Resolução
    Conjunta"/"Resolução Administrativa" — todos são atos normativos do TSE.
    """
    return _filtro_tse(item) and normalizar(item.get("tipo_ato") or "").startswith(
        normalizar("Resolução"))


@registrar
class TSE(Fonte):
    orgao = "tse"
    nome = "TSE — Tribunal Superior Eleitoral"
    obrigatoria = True
    repetir_403 = True
    canais = [
        # ------------------------------------------------- API do portal (JSON)
        Canal(
            "atos normativos (portal oficial)", API, formato="json",
            parser="plone_search", tipo_padrao="ato_normativo", obrigatorio=False,
            opcoes={"params": dict(ATOS_NO_PORTAL)},
        ),
        Canal(
            "notícias oficiais (portal oficial)", API, formato="json",
            parser="plone_search", tipo_padrao="noticia", obrigatorio=False,
            opcoes={"params": dict(NOTICIAS_NO_PORTAL)},
        ),
        Canal(
            "atos e notícias por tema (portal oficial)", API, formato="json",
            parser="plone_search", tipo_padrao="ato_normativo",
            obrigatorio=False, topicos=TOPICOS_BUSCA,
            url_template=(API + "?SearchableText={topico}&b_size=20"
                                "&sort_on=effective&sort_order=descending"),
        ),
        # ----------------------------------------------------------- DOU (HTML)
        Canal(
            "atos do TSE por tema (DOU)", BUSCA, formato="html", parser="dou_embutido",
            tipo_padrao="ato_normativo", topicos=TOPICOS_BUSCA, dias=90,
            filtro_tema=_filtro_tse, padrao_href=r"/web/dou/-/",
            url_template=(BUSCA + "?q=%22{topico}%22&s=todos&exactDate=personalizado"
                                  "&sortType=0&delta=50&currentPage=1"
                                  "&publishFrom={from}&publishTo={to}&orgPrin="
                                  "Poder%20Judici%C3%A1rio"),
        ),
        Canal(
            "resoluções do TSE (DOU, órgão/subórgão)", BUSCA, formato="html",
            parser="dou_embutido", tipo_padrao="resolucao", dias=90,
            filtro_tema=_filtro_resolucao_tse, padrao_href=r"/web/dou/-/",
            url_template=(BUSCA + "?q=RESOLU%C3%87%C3%83O&s=todos"
                                  "&exactDate=personalizado&sortType=0&delta=50"
                                  "&currentPage=1&publishFrom={from}&publishTo={to}"
                                  "&orgPrin=Poder%20Judici%C3%A1rio"
                                  "&orgSub=Tribunal%20Superior%20Eleitoral"),
        ),
    ]
