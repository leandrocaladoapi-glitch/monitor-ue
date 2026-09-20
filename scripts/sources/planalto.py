#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/planalto.py — Coletor da Presidência da República (Planalto).

Atos presidenciais (leis sancionadas, decretos, medidas provisórias, vetos,
decreto legislativo) são publicados oficialmente no Diário Oficial da União.
Este coletor usa a **busca oficial do DOU** e restringe, item a item, aos atos
de competência presidencial:

  · "Atos do Poder Legislativo" (leis sancionadas, decretos legislativos, vetos)
  · "Presidência da República"  (decretos, medidas provisórias, mensagens)

A janela de busca é de 90 dias (atos presidenciais sobre os temas monitorados são
raros: em 30 dias a consulta "Presidência da República" volta vazia com
frequência; com 90 dias o mesmo canal encontra os atos do trimestre).

A coluna `hierarchyStr` devolvida pela própria Imprensa Nacional é usada como
filtro — não há heurística sobre texto livre nem criação de ato sem URL
oficial. Também é consultado o portal do Planalto (gov.br/planalto) quando
acessível; se o portal estiver indisponível para o robô, o canal é registrado
como falho e o painel mostra exatamente isso (nada é preenchido no lugar).

Canais:
  · atos do Poder Legislativo por tema (leis, decretos legislativos, vetos)
  · atos da Presidência por tema       (decretos, medidas provisórias)
"""
import urllib.parse

from .base import Canal, Fonte, TOPICOS_BUSCA, normalizar, registrar

BUSCA = "https://www.in.gov.br/consulta/-/buscar/dou"

# Órgãos principais do DOU que publicam atos da Presidência/Planalto.
ORGAO_LEGISLATIVO = "Atos do Poder Legislativo"
ORGAO_PRESIDENCIA = "Presidência da República"

# Tipos de ato presidencial monitorados (rótulos exatos do DOU).
TIPOS_ATO = ("Lei", "Lei Complementar", "Decreto", "Decreto-Lei",
             "Decreto Legislativo", "Medida Provisória", "Mensagem")

TIPOS_NORMALIZADOS = {normalizar(t) for t in TIPOS_ATO}


def _hierarquia_ok(item, prefixos):
    hier = normalizar(item.get("hierarquia") or "")
    return any(hier.startswith(normalizar(p)) for p in prefixos)


def _tipo_ok(item):
    tipo = normalizar(item.get("tipo_ato") or "")
    return any(tipo.startswith(t) for t in TIPOS_NORMALIZADOS)


def _filtro_presidencia_legislativo(item):
    """Atos do Poder Legislativo (sanção/veto de lei)."""
    return _hierarquia_ok(item, [ORGAO_LEGISLATIVO]) and _tipo_ok(item)


def _filtro_presidencia_direta(item):
    """Atos da Presidência da República (decreto, medida provisória, mensagem)."""
    return _hierarquia_ok(item, [ORGAO_PRESIDENCIA]) and _tipo_ok(item)


NOTICIAS = "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias"


def _canal(rotulo, org_prin, filtro, topicos, tipo_padrao):
    # Os rótulos do DOU têm acento e espaço: vão percent-encoded (a URL precisa
    # ser ASCII — sem isso o cliente HTTP recusa a requisição).
    org = urllib.parse.quote(org_prin, safe="")
    return Canal(
        rotulo, BUSCA, formato="html", parser="dou_embutido", tipo_padrao=tipo_padrao,
        topicos=topicos, dias=90, filtro_tema=filtro, padrao_href=r"/web/dou/-/",
        url_template=(BUSCA + "?q=%22{topico}%22&s=todos&exactDate=personalizado"
                              "&sortType=0&delta=50&currentPage=1"
                              "&publishFrom={from}&publishTo={to}&orgPrin=" + org),
    )


@registrar
class Planalto(Fonte):
    orgao = "planalto"
    nome = "Planalto — Presidência da República"
    obrigatoria = True
    canais = [
        _canal("atos do Poder Legislativo (leis, vetos)", ORGAO_LEGISLATIVO,
               _filtro_presidencia_legislativo, TOPICOS_BUSCA, "lei"),
        _canal("atos da Presidência (decretos, MPs)", ORGAO_PRESIDENCIA,
               _filtro_presidencia_direta, TOPICOS_BUSCA, "decreto"),
        # Portal do Planalto: pode estar protegido por WAF para robôs; se estiver,
        # o canal entra como falho (transparência), sem substituir a fonte oficial.
        # O feed RSS oficial dá o mesmo conteúdo em formato estruturado.
        Canal(
            "notícias do Planalto (RSS oficial)", NOTICIAS + "/RSS",
            formato="rss", parser="rss", obrigatorio=False, tipo_padrao="noticia",
        ),
        Canal(
            "notícias do Planalto (página oficial)", NOTICIAS,
            formato="html", parser="plone_html", obrigatorio=False,
            tipo_padrao="noticia",
            padrao_href=r"planalto/pt-br/acompanhe-o-planalto/noticias/[a-z0-9-]{8,}",
        ),
    ]
