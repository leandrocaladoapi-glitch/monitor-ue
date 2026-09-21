#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonda de endpoints oficiais da União Europeia (diagnóstico).

Consulta, com evidência salva em out/, os endpoints oficiais usados (e os
candidatos documentados) por cada fonte do monitor UE:

  * Parlamento Europeu — Open Data Portal v2 (procedures, ficha do AI Act);
  * EUR-Lex — busca oficial e RSS do Jornal Oficial;
  * Conselho da UE — registro público (últimos documentos);
  * Comissão Europeia — Press Corner (RSS) e Have Your Say;
  * European AI Office — portal digital-strategy (newsroom e páginas do AI Act);
  * EDPB — feed oficial; EDPS — press releases, notícias e publicações;
  * Legislative Train (descoberta de dossiês).

Uso: python3 scripts/probe_sources.py --conjunto eu --salvar-dir out/probe
     python3 scripts/probe_sources.py --canais   (URLs reais de cada canal)
"""
import argparse
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
      "Chrome/124.0 Safari/537.36 monitor-ia-ue/1.0")
BROWSER = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.9,application/ld+json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en;q=0.9,pt-BR;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

JSONLD = "application/ld%2Bjson"

# (orgao, rótulo, url, accept, modo) — modo: None | "curl"
EU = [
    # ------------------------------------------- Parlamento (Open Data v2)
    ("eu_parliament", "api-v2-procedimentos-termo10",
     f"https://data.europarl.europa.eu/api/v2/procedures?parliamentary_term=10&limit=2&format={JSONLD}",
     "application/ld+json", None),
    ("eu_parliament", "api-v2-ficha-ai-act",
     f"https://data.europarl.europa.eu/api/v2/procedures/2021-0106?format={JSONLD}",
     "application/ld+json", None),
    ("eu_parliament", "api-v2-procedimentos-termo9",
     f"https://data.europarl.europa.eu/api/v2/procedures?parliamentary_term=9&limit=2&format={JSONLD}",
     "application/ld+json", None),
    ("eu_parliament", "api-v2-busca-texto",
     f"https://data.europarl.europa.eu/api/v2/procedures?text=artificial+intelligence&limit=2&format={JSONLD}",
     "application/ld+json", None),
    ("eu_parliament", "legislative-train-digital",
     "https://www.europarl.europa.eu/legislative-train/theme-a-europe-fit-for-the-digital-age",
     None, None),
    ("eu_parliament", "sala-imprensa",
     "https://www.europarl.europa.eu/news/en", None, None),
    # ------------------------------------------------- EUR-Lex / JO
    ("eurlex", "busca-oficial-ia",
     "https://eur-lex.europa.eu/search.html?text=%22artificial%20intelligence%22&scope=EURLEX&type=quick&amount=5&page=1",
     None, None),
    ("eurlex", "rss-jo-serie-l",
     "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222",
     "application/rss+xml", None),
    ("eurlex", "ai-act-consolidado",
     "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727",
     None, None),
    # ------------------------------------------------- Conselho da UE
    ("eu_council", "registro-ultimos-documentos",
     "https://www.consilium.europa.eu/en/documents/public-register/latest/",
     None, None),
    ("eu_council", "registro-docs-preparatorios",
     "https://www.consilium.europa.eu/en/documents/public-register/preparatory-legislative-documents/",
     None, None),
    ("eu_council", "pdf-data-consilium",
     "https://data.consilium.europa.eu/doc/document/ST-5663-2025-INIT/en/pdf",
     "application/pdf", None),
    # ------------------------------------------------- Comissão Europeia
    ("eu_commission", "presscorner-rss",
     "https://ec.europa.eu/commission/presscorner/api/rss?language=en",
     "application/rss+xml", None),
    ("eu_commission", "have-your-say-pag1",
     "https://ec.europa.eu/info/law/better-regulation/have-your-say/initiatives_en?page=1",
     None, None),
    ("eu_commission", "have-your-say-pag2",
     "https://ec.europa.eu/info/law/better-regulation/have-your-say/initiatives_en?page=2",
     None, None),
    # ------------------------------------------------- European AI Office
    ("ai_office", "newsroom-news-digibytes",
     "https://digital-strategy.ec.europa.eu/en/news?type=5%7C13", None, None),
    ("ai_office", "pagina-ai-office",
     "https://digital-strategy.ec.europa.eu/en/policies/ai-office", None, None),
    ("ai_office", "ai-act-quadro-regulatorio",
     "https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai",
     None, None),
    ("ai_office", "gpai-pagina",
     "https://digital-strategy.ec.europa.eu/en/policies/general-purpose-ai",
     None, None),
    ("ai_office", "ai-act-pagina",
     "https://digital-strategy.ec.europa.eu/en/ai-act", None, None),
    # ------------------------------------------------- EDPB / EDPS
    ("edpb", "feed-noticias",
     "https://www.edpb.europa.eu/feed/news_en", "application/rss+xml", None),
    ("edps", "press-releases",
     "https://www.edps.europa.eu/press-publications/press-news/press-releases_en",
     None, None),
    ("edps", "noticias",
     "https://www.edps.europa.eu/press-publications/press-news/news_en",
     None, None),
    ("edps", "publicacoes",
     "https://www.edps.europa.eu/data-protection/our-work/publications_en",
     None, None),
    # ------------------------- candidatos documentados como limitação (evidência)
    ("eu_parliament", "api-v2-plenary-meetings-agenda",
     f"https://data.europarl.europa.eu/api/v2/plenary-meetings?limit=2&format={JSONLD}",
     "application/ld+json", None),
    ("eu_parliament", "api-v2-committeemeetings-agenda",
     f"https://data.europarl.europa.eu/api/v2/committeemeetings?limit=2&format={JSONLD}",
     "application/ld+json", None),
]

CONJUNTOS = {"eu": EU, "base": EU, "detalhe": EU, "rodada4": EU}




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
