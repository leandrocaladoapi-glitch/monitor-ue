#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/cnj.py — Coletor do CNJ (Conselho Nacional de Justiça).

Fontes oficiais:
  · Sistema de Atos Normativos do CNJ — https://atos.cnj.jus.br/api/atos
    (API pública que alimenta o buscador de atos: tipo, número, data de
    publicação, situação, ementa e URL de detalhe de cada ato)
  · Portal do CNJ — https://www.cnj.jus.br/wp-json/wp/v2/posts
    (API de conteúdo do próprio portal: notícias oficiais com data e link)

Evidência da sonda (CI, 17/09/2026): a API de atos devolve os mesmos itens
quaisquer que sejam os parâmetros de busca testados (`q`, `search`, `busca`,
`ementa`, `palavra_chave`, `order`, `tipo`, `per_page`) — todos ignorados —,
sempre ordenados por data de publicação decrescente. Por isso o canal consulta
a listagem recente e o filtro temático é aplicado item a item pelo núcleo
comum; não há busca por tema a explorar. Paginação: `page=N` funciona (a sonda
da rodada 4 mostrou a página 2 trazendo atos mais antigos, sem repetir a 1),
enquanto `offset` é ignorado — por isso os canais extras usam `page`. O núcleo
comum descarta qualquer item repetido entre canais, então uma página que volte
igual à anterior não duplica nada no dataset.

O filtro temático é conservador: item sem sinal temático claro é descartado e
item duvidoso entra marcado como "revisar" (curadoria editorial).
"""
from .base import Canal, Fonte, registrar

ATOS = "https://atos.cnj.jus.br/api/atos"
WP = "https://www.cnj.jus.br/wp-json/wp/v2/posts"


@registrar
class CNJ(Fonte):
    orgao = "cnj"
    nome = "CNJ — Conselho Nacional de Justiça"
    obrigatoria = True
    canais = [
        Canal(
            "atos normativos recentes", ATOS, formato="json", parser="cnj_atos",
            tipo_padrao="ato_normativo",
        ),
        Canal(
            "atos normativos recentes (página 2)", ATOS, formato="json",
            parser="cnj_atos", tipo_padrao="ato_normativo", obrigatorio=False,
            opcoes={"params": {"page": 2}},
        ),
        Canal(
            "atos normativos recentes (página 3)", ATOS, formato="json",
            parser="cnj_atos", tipo_padrao="ato_normativo", obrigatorio=False,
            opcoes={"params": {"page": 3}},
        ),
        Canal(
            "notícias oficiais", WP, formato="json", parser="wp_json",
            tipo_padrao="noticia",
            opcoes={"params": {"per_page": 50, "_fields":
                               "id,date,link,title,excerpt,type"}},
        ),
        Canal(
            "notícias oficiais (página 2)", WP, formato="json", parser="wp_json",
            tipo_padrao="noticia", obrigatorio=False,
            opcoes={"params": {"per_page": 50, "page": 2, "_fields":
                               "id,date,link,title,excerpt,type"}},
        ),
    ]
