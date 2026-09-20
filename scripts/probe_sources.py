#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de endpoints oficiais (diagnóstico). Ver docstring de cabeçalho do
conjunto escolhido em CONJUNTOS."""
import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 monitor-legislativo-ia/1.0")
BROWSER = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Linux"',
}

# (orgao, rótulo, url, accept, modo) — modo: None | "curl"
BASE = [
    ("camara", "proposicoes", "https://dadosabertos.camara.leg.br/api/v2/proposicoes?siglaTipo=PL&ano=2026&itens=2&ordem=DESC&ordenarPor=id", "application/json", None),
    ("senado", "pesquisa", "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista?sigla=PL&ano=2026&v=7", "application/json", None),
    ("anpd", "api-search-noticias", "https://www.gov.br/anpd/++api++/@search?portal_type=News%20Item&b_size=5&sort_on=effective&sort_order=descending", "application/json", None),
]

DETALHE = [
    # ------------------------------------------------------- ANPD (restapi)
    ("anpd", "path-noticias", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/assuntos/noticias&b_size=5&sort_on=effective&sort_order=descending", "application/json", None),
    ("anpd", "path-regulacao", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/assuntos/regulacao&b_size=10&sort_on=effective&sort_order=descending", "application/json", None),
    ("anpd", "path-processo-regulatorio", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/assuntos/processo-regulatorio&b_size=5", "application/json", None),
    ("anpd", "path-consultas-publicas", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/assuntos/consultas-publicas&b_size=5", "application/json", None),
    ("anpd", "path-participacao", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/acesso-a-informacao/participacao-social&b_size=5", "application/json", None),
    ("anpd", "path-agenda-regulatoria", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/assuntos/agenda-regulatoria&b_size=5", "application/json", None),
    ("anpd", "path-fiscalizacao", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/assuntos/fiscalizacao&b_size=5", "application/json", None),
    ("anpd", "path-sandbox", "https://www.gov.br/anpd/++api++/@search?path=/pt-br/assuntos/sandbox-regulatorio&b_size=5", "application/json", None),
    ("anpd", "busca-tema-portal-type", "https://www.gov.br/anpd/++api++/@search?SearchableText=intelig%C3%AAncia%20artificial&portal_type=News%20Item&b_size=10", "application/json", None),
    ("anpd", "busca-consulta-publica", "https://www.gov.br/anpd/++api++/@search?SearchableText=consulta%20p%C3%BAblica&b_size=10&sort_on=effective&sort_order=descending", "application/json", None),
    ("anpd", "busca-resolucao", "https://www.gov.br/anpd/++api++/@search?SearchableText=resolu%C3%A7%C3%A3o&portal_type=File&b_size=10&sort_on=effective&sort_order=descending", "application/json", None),
    ("anpd", "tipos-portal", "https://www.gov.br/anpd/++api++/@types", "application/json", None),
    ("anpd", "noticias-html-curl", "https://www.gov.br/anpd/pt-br/assuntos/noticias", None, "curl"),

    # ------------------------------------------------------------------ CNJ
    ("cnj", "atos-search-param", "https://atos.cnj.jus.br/api/atos?search=inteligencia%20artificial", "application/json", None),
    ("cnj", "atos-ementa-param", "https://atos.cnj.jus.br/api/atos?ementa=inteligencia", "application/json", None),
    ("cnj", "atos-busca-param", "https://atos.cnj.jus.br/api/atos?busca=inteligencia", "application/json", None),
    ("cnj", "atos-palavra-param", "https://atos.cnj.jus.br/api/atos?palavra_chave=inteligencia", "application/json", None),
    ("cnj", "atos-tipo-resolucao", "https://atos.cnj.jus.br/api/atos?tipo=Resolu%C3%A7%C3%A3o&per_page=3", "application/json", None),
    ("cnj", "atos-ordenado", "https://atos.cnj.jus.br/api/atos?order=data_publicacao&sort=desc&per_page=3", "application/json", None),
    ("cnj", "atos-html-params", "https://atos.cnj.jus.br/atos", None, "curl"),
    ("cnj", "wp-posts-50", "https://www.cnj.jus.br/wp-json/wp/v2/posts?per_page=50&_fields=id,date,link,title,excerpt,type", "application/json", None),
    ("cnj", "wp-tipos", "https://www.cnj.jus.br/wp-json/wp/v2/types", "application/json", None),
    ("cnj", "wp-busca-ia-espaco", "https://www.cnj.jus.br/wp-json/wp/v2/posts?search=inteligencia&per_page=3&_fields=id,date,link,title", "application/json", None),
    ("cnj", "wp-busca-s-html", "https://www.cnj.jus.br/?s=intelig%C3%AAncia+artificial", None, "curl"),
    ("cnj", "consultas-publicas", "https://www.cnj.jus.br/consultas-publicas/", None, "curl"),

    # ------------------------------------------------------------------ DOU
    ("dou", "filtro-presidencia", "https://www.in.gov.br/consulta/-/buscar/dou?q=intelig%C3%AAncia%20artificial&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-01-2026&publishTo=17-09-2026&orgPrin=Presid%C3%AAncia%20da%20Rep%C3%BAblica", None, None),
    ("dou", "filtro-legislativo", "https://www.in.gov.br/consulta/-/buscar/dou?q=intelig%C3%AAncia%20artificial&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-01-2026&publishTo=17-09-2026&orgPrin=Atos%20do%20Poder%20Legislativo", None, None),
    ("dou", "filtro-arttype-lei", "https://www.in.gov.br/consulta/-/buscar/dou?q=&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-01-2026&publishTo=17-09-2026&orgPrin=Atos%20do%20Poder%20Legislativo&artType=Lei", None, None),
    ("dou", "filtro-mcti", "https://www.in.gov.br/consulta/-/buscar/dou?q=intelig%C3%AAncia%20artificial&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-01-2026&publishTo=17-09-2026&orgPrin=Minist%C3%A9rio%20da%20Ci%C3%AAncia%2C%20Tecnologia%20e%20Inova%C3%A7%C3%A3o", None, None),
    ("dou", "filtro-poder-judiciario", "https://www.in.gov.br/consulta/-/buscar/dou?q=resolu%C3%A7%C3%A3o&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-09-2026&publishTo=17-09-2026&orgPrin=Poder%20Judici%C3%A1rio&orgSub=Tribunal%20Superior%20Eleitoral", None, None),
    ("dou", "filtro-tse-resolucao-ia", "https://www.in.gov.br/consulta/-/buscar/dou?q=resolu%C3%A7%C3%A3o%20intelig%C3%AAncia%20artificial%20elei%C3%A7%C3%B5es&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-01-2026&publishTo=17-09-2026&orgPrin=Poder%20Judici%C3%A1rio", None, None),
    ("dou", "s1-mes-corrente", "https://www.in.gov.br/consulta/-/buscar/dou?q=&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-09-2026&publishTo=17-09-2026&s=do1", None, None),
    ("dou", "delivery-oficial", "https://www.in.gov.br/servicos/dou/", None, "curl"),

    # ------------------------------------------------- feeds RSS oficiais (gov.br)
    ("mcti", "noticias-rss-oficial", "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/RSS", "application/rss+xml", None),
    ("mcti", "noticias-rss-xml", "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/rss.xml", "application/rss+xml", None),
    ("mcti", "consultas-publicas", "https://www.gov.br/mcti/pt-br/acesso-a-informacao/participacao-social/consultas-publicas", None, None),
    ("mcti", "acoes-e-programas", "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/acoes-e-programas", None, None),
    ("planalto", "noticias-rss-oficial", "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias/RSS", "application/rss+xml", None),
    ("planalto", "noticias-rss-xml", "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias/rss.xml", "application/rss+xml", None),
    ("planalto", "noticias-pagina", "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias", None, None),
    ("cnj", "feed-rss-do-portal", "https://www.cnj.jus.br/feed/", "application/rss+xml", None),
    ("dou", "tse-resolucoes-titulo-orgsub", "https://www.in.gov.br/consulta/-/buscar/dou?q=RESOLU%C3%87%C3%83O&s=titulo&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-09-2026&publishTo=17-09-2026&orgPrin=Poder%20Judici%C3%A1rio&orgSub=Tribunal%20Superior%20Eleitoral", None, None),
    ("dou", "presidencia-decretos", "https://www.in.gov.br/consulta/-/buscar/dou?q=DECRETO&s=titulo&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=18-08-2026&publishTo=17-09-2026&orgPrin=Presid%C3%AAncia%20da%20Rep%C3%BAblica", None, None),

    # ------------------------------------------------------------------ TSE
    ("tse", "noticias-curl", "https://www.tse.jus.br/comunicacao/noticias", None, "curl"),
    ("tse", "noticias-urllib-browser", "https://www.tse.jus.br/comunicacao/noticias", None, None),
    ("tse", "rss-curl", "https://www.tse.jus.br/comunicacao/noticias/RSS", None, "curl"),
    ("tse", "restapi-curl", "https://www.tse.jus.br/++api++/@search?b_size=3&sort_on=effective&sort_order=descending", "application/json", "curl"),
    ("tse", "legislacao-curl", "https://www.tse.jus.br/legislacao/compilada", None, "curl"),
    ("tse", "ckan-curl", "https://dadosabertos.tse.jus.br/api/3/action/package_list", "application/json", "curl"),
    ("tse", "internet-api", "https://www.tse.jus.br/api/1.0/noticias", "application/json", "curl"),
    ("tse", "noticias-tse-jus-br-fontes", "https://www.tse.jus.br/++api++/comunicacao/noticias", "application/json", "curl"),

    # ------------------------------------------------------------- Planalto
    ("planalto", "planalto-lgpd", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/L13709.htm", None, None),
    ("planalto", "planalto-lgpd-curl", "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm", None, "curl"),
    ("planalto", "planalto-atos-2026", "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/lei/", None, None),
    ("planalto", "govbr-noticias-curl", "https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias", None, "curl"),
    ("planalto", "legislacao-portal-curl", "https://www4.planalto.gov.br/legislacao/", None, "curl"),
    ("planalto", "lexml-sru-v2", "https://www.lexml.gov.br/busca/SRU?operation=searchRetrieve&version=1.1&maximumRecords=3&query=%22inteligencia+artificial%22", "application/xml", "curl"),
    ("planalto", "lexml-sru-v3", "https://www.lexml.gov.br/sru?operation=searchRetrieve&version=1.1&maximumRecords=3&query=%22inteligencia%20artificial%22", "application/xml", "curl"),
    ("planalto", "lexml-busca-curl", "https://www.lexml.gov.br/busca/search?keyword=inteligencia+artificial", None, "curl"),
    ("planalto", "lexml-oai-curl", "https://www.lexml.gov.br/oai/request?verb=Identify", "application/xml", "curl"),
    ("planalto", "camara-legislacao-federal", "https://www.camara.leg.br/legislacao/", None, "curl"),

    # ------------------------------------------------------------------ MCTI
    ("mcti", "noticias-curl", "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias", None, "curl"),
    ("mcti", "noticias-curl-mes", "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/noticias-julho-outubro-2026", None, "curl"),
    ("mcti", "rss-noticias-curl", "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/RSS", None, "curl"),
    ("mcti", "portarias-curl", "https://www.gov.br/mcti/pt-br/acesso-a-informacao/legislacao/portarias", None, "curl"),
    ("mcti", "portarias-ano", "https://www.gov.br/mcti/pt-br/acesso-a-informacao/legislacao/portarias/2026", None, "curl"),
    ("mcti", "participa-consultas", "https://www.gov.br/participamaisbrasil/consultas-publicas", None, "curl"),
    ("mcti", "mcti-antigo", "https://www.mcti.gov.br/", None, "curl"),
    ("mcti", "dou-mcti-portarias", "https://www.in.gov.br/consulta/-/buscar/dou?q=intelig%C3%AAncia%20artificial&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-01-2026&publishTo=17-09-2026&orgPrin=Minist%C3%A9rio%20da%20Ci%C3%AAncia%2C%20Tecnologia%20e%20Inova%C3%A7%C3%A3o", None, None),
]

# Rodada 4: confirmar/corrigir os canais que o ensaio de 17/09/2026 mostrou
# incompletos (TSE só com DOU; MCTI sem notícias/portarias; Planalto sem atos da
# Presidência; CNJ com paginação ignorada) e testar as APIs Plone (++api++) dos
# portais gov.br, que são a mesma plataforma do ANPD (que responde bem).
RODADA4 = [
    # ---------- TSE: o ensaio tomou 403 onde a sonda (headers de navegador)
    # ---------- recebeu 200 — aqui os dois conjuntos de cabeçalhos são testados.
    ("tse", "noticias-headers-coletor", "https://www.tse.jus.br/comunicacao/noticias", None, "base"),
    ("tse", "noticias-headers-navegador", "https://www.tse.jus.br/comunicacao/noticias", None, None),
    ("tse", "noticias-pagina2", "https://www.tse.jus.br/comunicacao/noticias?b_start:int=20", None, "base"),
    ("tse", "noticias-raiz", "https://www.tse.jus.br/noticias", None, "base"),
    ("tse", "noticias-rss", "https://www.tse.jus.br/comunicacao/noticias/RSS", "application/rss+xml", "base"),
    ("tse", "restapi-headers-coletor", "https://www.tse.jus.br/++api++/@search?b_size=3&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("tse", "legislacao-resolucao", "https://www.tse.jus.br/legislacao/compilada/resolucao", None, "base"),
    ("tse", "atos-normativos", "https://www.tse.jus.br/legislacao/atos-normativos", None, "base"),
    ("tse", "ckan-package-search", "https://dadosabertos.tse.jus.br/api/3/action/package_search?q=inteligencia+artificial&rows=3", "application/json", "base"),

    # ---------- Planalto: atos da Presidência no DOU (Poder Executivo) e APIs
    ("planalto", "dou-executivo-presidencia", "https://www.in.gov.br/consulta/-/buscar/dou?q=intelig%C3%AAncia%20artificial&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-01-2026&publishTo=17-09-2026&orgPrin=Atos%20do%20Poder%20Executivo&orgSub=Presid%C3%AAncia%20da%20Rep%C3%BAblica", None, "base"),
    ("planalto", "dou-presidencia-arttype-decreto", "https://www.in.gov.br/consulta/-/buscar/dou?q=&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=18-08-2026&publishTo=17-09-2026&orgPrin=Presid%C3%AAncia%20da%20Rep%C3%BAblica&artType=Decreto", None, "base"),
    ("planalto", "api-noticias", "https://www.gov.br/planalto/++api++/@search?path=/planalto/pt-br/acompanhe-o-planalto/noticias&portal_type=Noticia&b_size=10&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("planalto", "api-noticias-sem-path", "https://www.gov.br/planalto/++api++/@search?portal_type=Noticia&b_size=10&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("planalto", "dou-leiturajornal", "https://www.in.gov.br/leiturajornal?data=17-09-2026&secao=do1", None, "base"),
    ("planalto", "www4-legislacao", "https://www4.planalto.gov.br/legislacao/", None, "base"),
    ("planalto", "www4-legislacao-api", "https://www4.planalto.gov.br/legislacao/++api++/@search?b_size=5&sort_on=effective&sort_order=descending", "application/json", "base"),

    # ---------- MCTI: APIs Plone do próprio portal (notícias, portarias, consultas)
    ("mcti", "api-noticias", "https://www.gov.br/mcti/++api++/@search?path=/mcti/pt-br/acompanhe-o-mcti/noticias&portal_type=Noticia&b_size=10&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("mcti", "api-noticias-sem-path", "https://www.gov.br/mcti/++api++/@search?portal_type=Noticia&b_size=10&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("mcti", "api-portarias", "https://www.gov.br/mcti/++api++/@search?path=/mcti/pt-br/acesso-a-informacao/legislacao/portarias&b_size=10&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("mcti", "api-consultas", "https://www.gov.br/mcti/++api++/@search?path=/mcti/pt-br/acesso-a-informacao/participacao-social&b_size=10&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("mcti", "api-tema-ia", "https://www.gov.br/mcti/++api++/@search?SearchableText=intelig%C3%AAncia%20artificial&b_size=10&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("mcti", "noticias-folder-mes", "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/noticias-julho-outubro-2026", None, "base"),
    ("mcti", "portarias-outros-atos", "https://www.gov.br/mcti/pt-br/acesso-a-informacao/legislacao/outros-atos-normativos", None, "base"),

    # ---------- CNJ: paginação da API de atos e do WP (o ensaio repetiu itens)
    ("cnj", "atos-page2", "https://atos.cnj.jus.br/api/atos?page=2", "application/json", "base"),
    ("cnj", "atos-offset", "https://atos.cnj.jus.br/api/atos?offset=10", "application/json", "base"),
    ("cnj", "atos-detalhe", "https://atos.cnj.jus.br/api/atos/7034", "application/json", "base"),
    ("cnj", "wp-page2", "https://www.cnj.jus.br/wp-json/wp/v2/posts?per_page=3&page=2&_fields=id,date,link,title", "application/json", "base"),
    ("cnj", "wp-page1", "https://www.cnj.jus.br/wp-json/wp/v2/posts?per_page=3&page=1&_fields=id,date,link,title", "application/json", "base"),
    ("cnj", "wp-pages-consultas", "https://www.cnj.jus.br/wp-json/wp/v2/pages?search=consulta%20p%C3%BAblica&per_page=5&_fields=id,date,link,title", "application/json", "base"),
    ("cnj", "wp-categorias", "https://www.cnj.jus.br/wp-json/wp/v2/categories?per_page=30&_fields=id,name,count", "application/json", "base"),

    # ---------- ANPD: RSS e API por pasta (o coletor já usa ++api++)
    ("anpd", "api-noticias", "https://www.gov.br/anpd/++api++/@search?path=/anpd/pt-br/assuntos/noticias&portal_type=News%20Item&b_size=5&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("anpd", "api-tema-ia", "https://www.gov.br/anpd/++api++/@search?SearchableText=intelig%C3%AAncia%20artificial&b_size=5&sort_on=effective&sort_order=descending", "application/json", "base"),
    ("anpd", "noticias-rss", "https://www.gov.br/anpd/pt-br/assuntos/noticias/RSS", "application/rss+xml", "base"),

    # ---------- DOU: alternativas estruturadas à busca HTML
    ("dou", "busca-formato-json", "https://www.in.gov.br/consulta/-/buscar/dou?q=intelig%C3%AAncia%20artificial&s=todos&exactDate=personalizado&sortType=0&delta=20&currentPage=1&publishFrom=01-09-2026&publishTo=17-09-2026&formato=json", "application/json", "base"),
    ("dou", "api-consulta-publicacao", "https://www.in.gov.br/api/consulta/publicacao?q=inteligencia+artificial", "application/json", "base"),
]

CONJUNTOS = {"base": BASE, "detalhe": DETALHE, "rodada4": RODADA4}


def fetch_curl(url, accept=None, timeout=45):
    cmd = ["curl", "-sS", "-m", str(timeout), "--compressed", "--http2",
           "-H", f"User-Agent: {UA}",
           "-H", "Accept-Language: pt-BR,pt;q=0.9,en;q=0.8",
           "-H", f"Accept: {accept or 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}",
           "-H", "Upgrade-Insecure-Requests: 1",
           "-w", "\n__STATUS__%{http_code}__%{content_type}__%{size_download}",
           url]
    t0 = time.monotonic()
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        raw = out.stdout
        rodape = raw.rsplit(b"__STATUS__", 1)
        if len(rodape) == 2:
            partes = rodape[1].decode("utf-8", "replace").split("__")
            corpo = rodape[0]
        else:
            partes, corpo = ["0", "", "0"], raw
        if out.returncode != 0:
            return {"status": "ERR", "ct": "", "body": corpo[:2000],
                    "erro": f"curl {out.returncode}: {out.stderr.decode()[:200]}",
                    "segundos": round(time.monotonic() - t0, 2), "final_url": url}
        return {"status": int(partes[0] or 0) or "ERR", "ct": partes[1],
                "body": corpo, "segundos": round(time.monotonic() - t0, 2), "final_url": url}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERR", "ct": "", "body": b"", "erro": f"{type(e).__name__}: {e}",
                "segundos": round(time.monotonic() - t0, 2), "final_url": url}


# Cabeçalhos exatamente como o coletor real (scripts/sources/base.py Cliente.get)
# monta. Serve para reproduzir no diagnóstico o que o ensaio encontra em campo
# (ex.: um portal que responde 200 para headers "de navegador" mas 403 para o
# conjunto completo — ou o contrário).
BASE = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, identity",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"Linux"',
}


def fetch(url, accept=None, timeout=45, modo=None):
    if modo == "curl":
        return fetch_curl(url, accept, timeout)
    if modo == "base":
        headers = dict(BASE)
    else:
        headers = dict(BROWSER)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                try:
                    raw = gzip.decompress(raw)
                except OSError:
                    pass
            return {"status": r.status, "ct": r.headers.get("Content-Type") or "",
                    "body": raw, "segundos": round(time.monotonic() - t0, 2), "final_url": r.geturl()}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "ct": (e.headers or {}).get("Content-Type", ""),
                "body": e.read()[:2000], "segundos": round(time.monotonic() - t0, 2),
                "final_url": getattr(e, "url", url)}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERR", "ct": "", "body": b"", "erro": f"{type(e).__name__}: {e}",
                "segundos": round(time.monotonic() - t0, 2), "final_url": url}


def descrever(body_bytes):
    """Resumo estrutural: contagens, primeiros títulos, sinais de bloqueio."""
    txt = body_bytes.decode("utf-8", "replace")
    info = {}
    if txt.lstrip()[:1] in "{[":
        try:
            d = json.loads(txt)
        except ValueError:
            d = None
        if isinstance(d, dict):
            for k in ("items_total", "total", "totalPages", "count"):
                if k in d:
                    info[k] = d[k]
            for k in ("items", "data", "results", "jsonArray"):
                v = d.get(k)
                if isinstance(v, list):
                    info[f"{k}_len"] = len(v)
                    titulos = []
                    for it in v[:3]:
                        if isinstance(it, dict):
                            t = (it.get("title") or it.get("titulo") or it.get("ementa")
                                 or it.get("number") or "")
                            if isinstance(t, dict):
                                t = t.get("rendered", "")
                            hier = it.get("hierarchyStr") or it.get("hierarchyList") or ""
                            titulos.append(f"{str(t)[:60]}|{str(hier)[:40]}")
                    info["amostra_titulos"] = titulos
        elif isinstance(d, list):
            info["lista_len"] = len(d)
    if "jsonArray" in txt and "jsonArray_len" not in info:
        m = re.search(r'"jsonArray":\s*(\d+)', txt)
        info["jsonArray_ref"] = m.group(1) if m else "presente"
        info["hits"] = len(re.findall(r'"urlTitle"', txt))
    if "TSPD" in txt or "APM_DO_NOT_TOUCH" in txt:
        info["bloqueio"] = "F5-TSPD (desafio JS)"
    if "403 Forbidden" in txt or "Access Denied" in txt:
        info["bloqueio"] = "403"
    if "<rss" in txt[:3000].lower() or "<feed" in txt[:3000].lower():
        info["feed"] = len(re.findall(r"<item[ >]|<entry[ >]", txt))
    if "<a href" in txt.lower():
        info["links"] = len(re.findall(r"<a\s[^>]*href", txt, re.I))
    return info


def canais_do_coletor(limite_por_canal=2):
    """URLs exatamente como os coletores as montam (diagnóstico de canal).

    Importa o registro de fontes do próprio projeto e devolve as URLs reais que
    cada canal consulta — é assim que se confere, com execução verdadeira, que
    a URL do canal responde e que o parser acha itens nela.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from sources import fontes_disponiveis, instanciar  # noqa: PLC0415

    alvos = []
    for orgao in sorted(fontes_disponiveis()):
        fonte = instanciar(orgao, logger=lambda *a, **k: None)
        for canal in fonte.canais:
            for i, (topico, url) in enumerate(canal.urls()):
                if i >= limite_por_canal:
                    break
                rotulo = canal.rotulo if not topico else f"{canal.rotulo} :: {topico[:24]}"
                accept = "application/json" if canal.formato == "json" else (
                    "application/rss+xml" if canal.formato == "rss" else None)
                alvos.append((orgao, rotulo, url, accept, "base"))
    return alvos


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", default="detalhe", choices=sorted(CONJUNTOS))
    ap.add_argument("--canais", action="store_true",
                    help="sonda as URLs reais de cada canal dos coletores")
    ap.add_argument("--orgao", action="append")
    ap.add_argument("--salvar-dir", default=None)
    ap.add_argument("--limite-exemplo", type=int, default=300)
    args = ap.parse_args(argv)

    base_alvos = (canais_do_coletor() if getattr(args, "canais", False)
                  else CONJUNTOS[args.conjunto])
    alvos = [c for c in base_alvos if not args.orgao or c[0] in args.orgao]
    os.makedirs(args.salvar_dir, exist_ok=True) if args.salvar_dir else None
    ok = 0
    for org, rotulo, url, accept, modo in alvos:
        res = fetch(url, accept, modo=modo)
        body = res.get("body") or b""
        info = descrever(body)
        print(f"\n=== [{org}] {rotulo} (modo={modo or 'urllib'})")
        print(f"    GET {url[:160]}")
        print(f"    status={res['status']} ct={res['ct'][:50]} bytes={len(body)} t={res['segundos']}s")
        if res.get("erro"):
            print(f"    erro={res['erro'][:200]}")
        print(f"    info: {json.dumps(info, ensure_ascii=False)[:600]}")
        print(f"    amostra: {re.sub(chr(92)+'s+', ' ', body.decode('utf-8','replace')[:args.limite_exemplo])}")
        if res["status"] == 200 and body:
            ok += 1
        if args.salvar_dir and body:
            nome = re.sub(r"[^a-zA-Z0-9_.-]", "_", f"{org}__{rotulo}")[:70]
            with open(os.path.join(args.salvar_dir, nome + ".txt"), "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\nSTATUS: {res['status']} CT: {res['ct']}\nINFO: "
                        f"{json.dumps(info, ensure_ascii=False)}\n---\n")
                f.write(body.decode("utf-8", "replace")[:30000])
    print(f"\n--- {ok}/{len(alvos)} responderam 200 ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
