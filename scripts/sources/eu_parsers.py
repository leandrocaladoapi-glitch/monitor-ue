#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/eu_parsers.py — decodificadores dos formatos oficiais das fontes da UE.

Cada função converte uma resposta oficial (JSON-LD da API de Dados Abertos do
Parlamento, HTML de busca do EUR-Lex, listagem do registro público do Conselho,
listagens da Comissão/EDPB/EDPS) em itens normalizados:

    {titulo, link, data, descricao, + campos específicos}

Regras: nenhum campo é inventado — o que a fonte não traz fica ausente. Itens
sem título ou sem URL oficial são descartados. Todas as funções aceitam
`canal=`/`topico=`/`url=` opcionais (a assinatura é uniforme para o despacho
`eu:<funcao>` do núcleo comum).
"""
from __future__ import annotations

import re

from .base import data_eu, data_iso, limpar_texto

# Referências de procedimento interinstitucional: 2021/0106(COD), 2025/0393(CNS)…
RE_PROC_REF = re.compile(r"\b(\d{4})/(\d{3,4})\((COD|CNS|CONS|NLE|DEC|REG|INI|RES|IMM|APP|BUA|CWP)\)")
# CELEX: 32024R1689, 52021PC0206, 02024R1689-20260727, 62023CJ0289…
RE_CELEX = re.compile(r"\b(\d{1}[2-9]\d{3}[A-Z]{1,4}\d{3,4}(?:R\(\d+\))?|0\d{9}-\d{8}|6\d{9}[A-Z]{2}\d{4})\b")


def _limite(canal, padrao=60):
    return (canal.opcoes.get("limite", padrao) if canal else padrao)


# ---------------------------------------------------------------- Parlamento
def parse_ep_procedimentos(dados, canal=None, topico=None):
    """API v2 do Parlamento (/procedures) em JSON-LD → itens de procedimento.

    Formato verificado em execução real (18/09/2026):
      {"data": [{"id": "eli/dl/proc/2024-2526", "type": "Process",
                 "process_id": "2024-2526", "process_type": "RSP",
                 "label": "2024/2526(RSP)"}], "meta": {"total": N}}
    O título oficial completo não vem na listagem — a ficha completa do
    procedimento é obtida por update_legislation.py em /procedures/{id}.
    Aqui a listagem serve de descoberta de referências novas.
    """
    itens = []
    for it in (dados or {}).get("data", []) if isinstance(dados, dict) else []:
        if not isinstance(it, dict):
            continue
        pid = (it.get("process_id") or "").strip()
        label = limpar_texto(it.get("label") or "", 120)
        if not pid or not label:
            continue
        ano = pid.split("-")[0]
        itens.append({
            "titulo": f"European Parliament procedure {label}",
            "link": (f"https://data.europarl.europa.eu/api/v2/procedures/{pid}"
                     "?format=application/ld%2Bjson"),
            "data": None,
            "descricao": f"Procedure {label} (termo parlamentar; tipo {it.get('process_type') or '?'}).",
            "process_id": pid,
            "proc_ref": label,
        })
    return itens[:_limite(canal, 120)]


def parse_ep_procedimento(dados, proc_id=None, **_kw):
    """API v2 do Parlamento (/procedures/{id}) → registro rico do procedimento.

    Formato verificado: {"data": [{"id": "eli/dl/proc/2021-0106", ...,
      "consists_of": [{"id": "eli/dl/event/...", "activity_date": "2024-03-13",
        "activity_id": "...", "had_activity_type":
        "http://.../def/ep-activities/PLENARY_VOTE", "occured_at_stage":
        "http://.../procedure-phase/RDG1", ...}]}]}
    """
    blocos = (dados or {}).get("data") if isinstance(dados, dict) else None
    proc = blocos[0] if isinstance(blocos, list) and blocos else None
    if not isinstance(proc, dict):
        return None
    eventos = []
    for ev in proc.get("consists_of", []) or []:
        if not isinstance(ev, dict):
            continue
        tipo_uri = str(ev.get("had_activity_type") or "")
        tipo = tipo_uri.rsplit("/", 1)[-1] if tipo_uri else None
        fase_uri = str(ev.get("occured_at_stage") or "")
        fase = fase_uri.rsplit("/", 1)[-1] if fase_uri else None
        eventos.append({
            "activity_id": ev.get("activity_id") or ev.get("id"),
            "data": data_iso(ev.get("activity_date")),
            "tipo": tipo,
            "fase": fase,
            "docs": [d for d in (ev.get("based_on_a_realization_of") or [])
                     + (ev.get("decided_on_a_realization_of") or [])
                     + (ev.get("recorded_in_a_realization_of") or [])
                     if isinstance(d, str)],
        })
    eventos.sort(key=lambda e: (e.get("data") or "", e.get("activity_id") or ""))
    return {
        "id": proc.get("id"),
        "process_id": proc.get("process_id") or proc_id,
        "label": limpar_texto(proc.get("label") or "", 120),
        "process_type": proc.get("process_type"),
        "eventos": eventos,
        "tema": limpar_texto(proc.get("title") or proc.get("label") or "", 300),
    }


# ------------------------------------------------------------------- EUR-Lex
_TITULOS_GENERICOS = {
    "access to european union law", "easily find every piece of european",
    "european union law", "eur-lex access to european union law",
    "quick search", "advanced search", "latest updated documents",
    "about eur-lex", "how to use this site", "help", "user guide",
}


def _titulo_generico(titulo):
    """True para âncoras de navegação do site (não são resultados de busca)."""
    t = (titulo or "").strip().lower()
    if t in _TITULOS_GENERICOS:
        return True
    return (len(t) >= 12 and (
        t.startswith(("javascript", "#", "login", "register"))
        or t in ("eurovoc", "celex number", "document information")))


def parse_eurlex_busca(html, url="", canal=None, **_kw):
    """Busca oficial do EUR-Lex (search.html?text=…&type=quick) → itens.

    Estrutura: cada resultado traz uma âncora para
    legal-content/…?uri=CELEX:XXXXX com o título, seguida de metadados
    (CELEX number, OJ L, ELI, "Date of document", status "In force",
    "Latest consolidated version"). O parser é tolerante a variação de layout:
    âncora CELEX + janela de texto seguinte.
    """
    if not html or "CELEX" not in html:
        return []
    itens, vistos = [], set()
    for m in re.finditer(
            r'<a\s[^>]*href="([^"]*uri=CELEX:([A-Za-z0-9()\.\-]+)[^"]*)"[^>]*>(.*?)</a>',
            html, re.I | re.S):
        href, celex, interno = m.group(1), m.group(2), m.group(3)
        celex = celex.strip("()") or celex
        chave = celex.split("&")[0]
        if chave in vistos:
            continue
        titulo = limpar_texto(interno, 400)
        if len(titulo) < 12:
            # âncora secundária (PDF/HTML do mesmo documento): usa a 1ª ocorrência
            continue
        if _titulo_generico(titulo):
            # âncora de navegação/rodapé da página de busca — não é um resultado;
            # adotá-la injetaria um título "inline" não verificado no dataset.
            continue
        vistos.add(chave)
        trecho = html[m.end():m.end() + 3500]
        texto_trecho = limpar_texto(trecho, 1400)
        data = None
        md = re.search(r"Date of document:\s*(\d{2})/(\d{2})/(\d{4})", texto_trecho)
        if md:
            data = f"{md.group(3)}-{md.group(2)}-{md.group(1)}"
        consolid = None
        mc = re.search(r"Latest consolidated version:\s*\[([^\]]+)\]\(([^)]+)\)", trecho)
        if mc:
            consolid = mc.group(2)
        status = None
        if "In force" in texto_trecho[:900]:
            status = "In force"
        elif re.search(r"Not in force", texto_trecho[:900]):
            status = "Not in force"
        forma = None
        mf = re.search(r"Form:\s*([^<\n]{3,60})", texto_trecho)
        if mf:
            forma = mf.group(1).strip()
        itens.append({
            "titulo": titulo,
            "link": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{chave}",
            "data": data,
            "descricao": texto_trecho[:700] or None,
            "celex": chave,
            "tipo_ato": forma,
            "status": status,
            "url_consolidada": consolid,
        })
        if len(itens) >= _limite(canal, 60):
            break
    return itens


def parse_eurlex_rss(items, canal=None, **_kw):
    """Pós-processa o RSS oficial do EUR-Lex (display-feed.rss).

    O feed traz, no link/descrição, o CELEX e a ELI de cada ato publicado no
    JO. Extraímos o CELEX para o item (usado na deduplicação multilíngue e no
    link canônico) e descartamos corrigendas administrativas triviais.
    """
    out = []
    for it in items:
        link = it.get("link") or ""
        texto = f"{link} {it.get('descricao') or ''} {it.get('titulo') or ''}"
        m = RE_CELEX.search(texto.replace("%3A", ":"))
        if m:
            celex = m.group(1)
            it["celex"] = celex
            it.setdefault("link", f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}")
        out.append(it)
    return out


def parse_eurlex_consolidado(html, url="", canal=None, **_kw):
    """Página de metadados de um documento do EUR-Lex → 1 item (ato vigente).

    Usada para acompanhar versões consolidadas de atos âncora (ex.: AI Act):
    o título vem do <title>/<h1> e a data da última consolidação do conteúdo.
    """
    if not html:
        return []
    mt = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    titulo = limpar_texto(mt.group(1) if mt else "", 400)
    if not titulo:
        return []
    titulo = re.sub(r"\s*[-|]\s*EUR-Lex.*$", "", titulo, flags=re.I).strip() or titulo
    data = data_iso(re.search(r"(\d{4}-\d{2}-\d{2})", html).group(0)) \
        if re.search(r"(\d{4}-\d{2}-\d{2})", html) else None
    mcons = re.search(r"0\d{9}-\d{8}", html)
    item = {
        "titulo": titulo,
        "link": url.split("?")[0] or url,
        "data": data,
        "descricao": None,
    }
    if mcons:
        item["celex"] = mcons.group(0)
    return [item]


# ------------------------------------------------------------------ Conselho
def parse_consilium_registro(html, url="", canal=None, **_kw):
    """Listagem oficial do registro público do Conselho (últimos documentos).

    Estrutura server-rendered: âncora para
    data.consilium.europa.eu/doc/document/<DOC>/en/pdf com o título e, em
    seguida, tabela com Subject matters / Interinstitutional file / datas.
    Itens sem URL pública são ignorados (regra: toda entrada precisa de URL
    oficial verificável).
    """
    if not html or "data.consilium.europa.eu" not in html:
        return []
    itens, vistos = [], set()
    for m in re.finditer(
            r'<a\s[^>]*href="(https://data\.consilium\.europa\.eu/doc/document/([^"/]+)/[^"]*)"[^>]*>(.*?)</a>',
            html, re.I | re.S):
        href, docid, interno = m.group(1), m.group(2), m.group(3)
        if docid in vistos:
            continue
        titulo = limpar_texto(interno, 400)
        if len(titulo) < 10:
            continue
        vistos.add(docid)
        trecho = html[m.end():m.end() + 2200]
        texto_trecho = limpar_texto(trecho, 900)
        mif = RE_PROC_REF.search(texto_trecho)
        data = None
        md = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto_trecho)
        if md:
            data = f"{md.group(3)}-{md.group(2)}-{md.group(1)}"
        assuntos = None
        ms = re.search(r"Subject matters:\s*([^|<\n]{3,240})", texto_trecho)
        if ms:
            assuntos = ms.group(1).strip()
        desc = texto_trecho[:500]
        if assuntos:
            desc = f"Assuntos: {assuntos}. {desc}"[:700]
        itens.append({
            "titulo": titulo,
            "link": href,
            "data": data,
            "descricao": desc or None,
            "doc_id": docid,
            "arquivo_interinstitucional": f"{mif.group(1)}/{mif.group(2)}({mif.group(3)})" if mif else None,
            "tipo_ato": "documento do Conselho",
        })
        if len(itens) >= _limite(canal, 80):
            break
    return itens


# ------------------------------------------------------- Comissão / AI Office
def parse_comissao_noticias(html, url="", canal=None, **_kw):
    """Listagens server-rendered da Comissão (digital-strategy newsroom e
    afins) → itens com título, URL oficial e data ('17 September 2026')."""
    if not html:
        return []
    padrao = (canal.padrao_href if canal and canal.padrao_href
              else r"/en/(news|library|publication|policy-document)/[a-z0-9\-]{8,}")
    regex = re.compile(padrao)
    itens, vistos = [], set()
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        href, interno = m.group(1), m.group(2)
        if not regex.search(href):
            continue
        titulo = limpar_texto(interno, 300)
        if len(titulo) < 14:
            continue
        chave = href.split("#")[0]
        if chave in vistos:
            continue
        vistos.add(chave)
        trecho = html[m.end():m.end() + 1200]
        data = data_eu(re.search(r"\d{1,2}\s+[A-Za-zç]{3,9}\s+\d{4}", trecho))
        desc = limpar_texto(re.sub(r"<a\s[^>]*>.*?</a>", " ", trecho, flags=re.I | re.S), 500)
        desc = re.sub(r"^\s*[-–|]\s*", "", desc)
        itens.append({"titulo": titulo, "link": chave, "data": data,
                      "descricao": desc or None})
        if len(itens) >= _limite(canal, 60):
            break
    return itens


def parse_consultas_hys(html, url="", canal=None, **_kw):
    """Have Your Say (portal oficial de consultas da Comissão) → itens.

    Estrutura server-rendered: âncora
    /have-your-say/initiatives/<id>-<slug>_en; no bloco seguinte vêm o estágio
    ("Call for evidence: Open", "Draft act: Open", "Public consultation:
    Open"), o tema, o tipo de ato e o "Feedback period dd Month yyyy - dd
    Month yyyy". A data final do período é o deadline verificável.
    """
    if not html or "have-your-say/initiatives" not in html:
        return []
    itens, vistos = [], set()
    for m in re.finditer(
            r'<a\s[^>]*href="([^"]*/have-your-say/initiatives/(\d+)-[^"]+)"[^>]*>(.*?)</a>',
            html, re.I | re.S):
        href, ini_id, interno = m.group(1), m.group(2), m.group(3)
        if ini_id in vistos:
            continue
        # a âncora costuma repetir o título em elementos aninhados
        titulo = limpar_texto(interno, 300)
        vistos.add(ini_id)
        trecho = html[max(0, m.start() - 400):m.end() + 1600]
        texto = limpar_texto(trecho, 1600)
        if len(titulo) < 10:
            mt = re.search(r"Feedback period.*?(?:\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\s*-\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}))", texto)
            # usa o trecho seguinte como título alternativo
            titulo = limpar_texto(html[m.end():m.end() + 500], 200) or titulo
        periodo = None
        mp = re.search(r"Feedback period\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*-\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", texto)
        if mp:
            periodo = (data_eu(mp.group(1)), data_eu(mp.group(2)))
        estagio = None
        for rot in ("Call for evidence", "Public consultation", "Draft act",
                    "Commission adoption"):
            if rot in texto:
                estagio = rot
                break
        tipo_ato = None
        mt2 = re.search(r"Type of act\s*([A-Za-z \-]{3,60})", texto)
        if mt2:
            tipo_ato = mt2.group(1).strip()
        desc = texto[:600]
        itens.append({
            "titulo": titulo,
            "link": href if href.startswith("http") else f"https://ec.europa.eu{href}",
            "data": periodo[1] if periodo else None,
            "descricao": desc or None,
            "consulta_id": ini_id,
            "periodo_feedback": f"{periodo[0]} → {periodo[1]}" if periodo else None,
            "estagio": estagio,
            "tipo_ato": tipo_ato,
        })
        if len(itens) >= _limite(canal, 60):
            break
    return itens


# --------------------------------------------------------------- EDPB / EDPS
def parse_edpb_rss(items, canal=None, **_kw):
    """Pós-processa o RSS oficial do EDPB (feed/news_en)."""
    return items


def parse_edps_listagem(html, url="", canal=None, **_kw):
    """Listagens do EDPS (press releases, news, publications) → itens."""
    if not html:
        return []
    padrao = (canal.padrao_href if canal and canal.padrao_href
              else r"/(press-publications|data-protection)/[a-z0-9/\-]{10,}")
    regex = re.compile(padrao)
    itens, vistos = [], set()
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        href, interno = m.group(1), m.group(2)
        if not regex.search(href):
            continue
        titulo = limpar_texto(interno, 300)
        if len(titulo) < 14:
            continue
        chave = href.split("#")[0]
        if chave in vistos:
            continue
        vistos.add(chave)
        trecho = html[m.end():m.end() + 1200]
        data = data_eu(re.search(r"\d{1,2}\s+[A-Za-zç]{3,9}\s+\d{4}", trecho))
        desc = limpar_texto(re.sub(r"<a\s[^>]*>.*?</a>", " ", trecho, flags=re.I | re.S), 500)
        itens.append({"titulo": titulo, "link": chave, "data": data,
                      "descricao": desc or None})
        if len(itens) >= _limite(canal, 60):
            break
    return itens


# --------------------------------------------------------- Legislative Train
def parse_legislative_train(html, url="", canal=None, **_kw):
    """Legislative Train Schedule (site oficial do Parlamento) → arquivos.

    Cada 'carriage' é um dossiê com URL /file-<slug> e status; a página do
    arquivo cita o número do procedimento interinstitucional. Usada para
    descoberta de procedimentos novos (engine legislativa).
    """
    if not html:
        return []
    regex = re.compile(r'/legislative-train/[^"]*/file-[a-z0-9\-]{4,}')
    itens, vistos = [], set()
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        href, interno = m.group(1), m.group(2)
        if not regex.search(href):
            continue
        titulo = limpar_texto(interno, 250)
        if len(titulo) < 8:
            continue
        chave = href.split("#")[0]
        if chave in vistos:
            continue
        vistos.add(chave)
        trecho = html[m.end():m.end() + 800]
        texto = limpar_texto(trecho, 400)
        status = None
        ms = re.search(r"Status:\s*([A-Za-z \-]{3,40})", texto)
        if ms:
            status = ms.group(1).strip()
        itens.append({"titulo": titulo, "link": chave,
                      "data": data_eu(re.search(r"\d{4}-\d{2}-\d{2}", trecho)),
                      "descricao": texto[:400] or None,
                      "status_trem": status})
        if len(itens) >= _limite(canal, 80):
            break
    return itens
