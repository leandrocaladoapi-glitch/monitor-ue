#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources/base.py — infraestrutura dos coletores multiórgão.

Este módulo é a base comum dos conectores das fontes oficiais de DOIS
monitores que compartilham este repositório:

  * Monitor Legislativo de IA no Brasil (ANPD, CNJ, TSE, DOU, Planalto, MCTI);
  * Monitor Legislativo e Regulatório de IA da União Europeia (Parlamento
    Europeu, Conselho da UE, Comissão Europeia, EUR-Lex, European AI Office,
    EDPB e EDPS).

Ele oferece:

  * cliente HTTP com timeout, retry, cache de execução, telemetria e respeito ao
    orçamento global da coleta (o mesmo de `update_legislation.py`);
  * decodificadores das formas oficiais usadas por essas fontes: RSS/Atom,
    JSON/JSON-LD de APIs oficiais e HTML de listagem oficial;
  * filtro temático conservador (IA, GPAI, AI Act, algoritmos, decisão
    automatizada, biometria, modelos fundacionais, infraestrutura digital,
    semicondutores…), que marca para revisão quando há dúvida em vez de
    classificar por conta própria;
  * modelo de item normalizado com URL oficial obrigatória e hash de texto, que
    é o que permite detectar mudança de texto/status entre execuções.

Regra inegociável do projeto: nada é inventado. Todo item gravado vem de uma
resposta oficial, com URL oficial registrada. Quando um canal não responde, a
fonte é marcada como falha/parcial — jamais é preenchida com dado estimado.

Multilinguismo: a coleta usa o inglês como idioma técnico preferencial e a
deduplicação é feita por identificador oficial (CELEX, número de procedimento
interinstitucional, id de documento, URL canônica) — nunca por tradução de
título. Versões linguísticas do mesmo documento não são contadas duas vezes.
"""
from __future__ import annotations

import gzip
import hashlib
import html as html_mod
import json
import os
import re
import ssl
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
UA_PADRAO = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/124.0 Safari/537.36 monitor-legislativo-ia/1.0 monitor-ia-ue/1.0 "
             "(+https://monitor.lcfconsulting.com.br)")


# --------------------------------------------------------------------- erros
class FonteIndisponivel(RuntimeError):
    """Nenhum canal da fonte respondeu com dados utilizáveis."""


class OrcamentoEsgotado(RuntimeError):
    """O tempo reservado para a fonte (ou para a coleta inteira) acabou."""


# Termos de busca usados nas consultas por assunto das fontes oficiais.
# São termos temáticos (o filtro fino é aplicado item a item, depois).
# TOPICOS_BUSCA = tópicos do monitor BR (em português, idioma das fontes);
# TOPICOS_BUSCA_UE = tópicos do monitor UE (em inglês, idioma técnico).
TOPICOS_BUSCA = [
    "inteligência artificial",
    "algoritmo",
    "proteção de dados",
    "reconhecimento facial",
    "biometria",
    "deepfake",
    "plataformas digitais",
    "semicondutor",
    "computação em nuvem",
    "data center",
]

TOPICOS_BUSCA_UE = [
    "artificial intelligence",
    "AI Act",
    "general-purpose AI",
    "GPAI",
    "foundation model",
    "generative AI",
    "deepfake",
    "facial recognition",
    "biometrics",
    "automated decision-making",
    "algorithm",
    "AI governance",
    "data centre",
    "semiconductor",
    "cloud",
]


# --------------------------------------------------------------- tema/filtro
# Padrões avaliados sobre texto normalizado (minúsculo, sem acento).
FORTE_PATTERNS = [
    # --- núcleo temático de IA (termos específicos; a sigla isolada "AI" é
    #     tratada como sinal fraco para evitar falso positivo em inglês)
    r"artificial intelligence", r"inteligencia artificial", r"\bai act\b", r"\bai office\b", r"\bai safety\b",
    r"\bai governance\b", r"\bai literacy\b", r"\bai regulatory sandbox",
    r"\bai systems?\b", r"artificial intelligence systems?", r"\bai model",
    r"general[- ]purpose ai", r"\bgpai\b", r"foundation models?", r"frontier models?",
    r"generative ai", r"generative artificial intelligence",
    r"large language model", r"\bllms?\b", r"machine learning", r"deep learning",
    r"neural network", r"\bchatbots?\b", r"\bai agents?\b", r"autonomous ai",
    r"high[- ]risk ai", r"high[- ]risk artificial intelligence",
    r"prohibited ai practices?", r"ai transparency", r"ai auditing",
    r"systemic risk", r"training data", r"model training", r"model evaluation",
    r"compute", r"ai compute", r"sovereign ai",
    # --- temas correlatos monitorados
    r"deepfake", r"synthetic content", r"synthetic media", r"ai[- ]generated content",
    r"facial recognition", r"biometric identification", r"remote biometric identification",
    r"biometrics", r"emotion recognition", r"real[- ]time remote biometric",
    r"automated decision[- ]making", r"automated decision making", r"solely automated decision",
    r"algorithmic decision[- ]making", r"algorithmic transparency", r"\balgorithms?\b",
    r"algorithmic system", r"decision[- ]making algorithm",
    r"data protection", r"personal data", r"\bgdpr\b", r"\bprivacy\b",
    r"semiconductor", r"microchip", r"\bchips?\b", r"advanced packaging",
    r"high[- ]performance computing", r"supercomput", r"exascale", r"quantum comput",
    r"data cent(er|re)", r"datacent", r"\bcloud\b", r"cloud infrastructure",
    r"digital sovereignty", r"data sovereignty",
    r"disinformation", r"misinformation", r"\bdesinformation\b",
    r"cybersecurity", r"cyber security",
    r"\brobot", r"autonomous system", r"internet of things", r"\biot\b",
    # --- bloco BR (preservado do monitor brasileiro; texto em português)
    r"\bia\b", r"ia generativa", r"inteligencia artificial generativa",
    r"modelo de linguagem", r"modelos? fundaciona",
    r"aprendizado de maquina", r"aprendizado profundo",
    r"rede[s]? neural", r"redes neurais",
    r"conteudo sintetico", r"midia sintetica", r"midia gerada",
    r"reconhecimento facial", r"reconhecimento biometrico", r"biometria",
    r"decisao automatizada", r"decisoes automatizadas", r"decisao algorítmica",
    r"decisoes algoritmicas", r"tomada de decisao automat", r"sistema de decisao automat",
    r"governanca de ia", r"governanca algoritmica", r"governanca de dados",
    r"moderacao algoritmica", r"moderacao de conteudo", r"curadoria algoritmica",
    r"algoritmo[s]?", r"algoritmic",
    r"plataformas digitais", r"big tech", r"rede social", r"redes sociais",
    r"sandbox regulatorio", r"regulacao de ia", r"regulamentacao da ia",
    r"protecao de dados", r"dados pessoais", r"\blgpd\b", r"titular de dados", r"autoridade nacional de protecao de dados",
    r"direitos digitais", r"desinformacao", r"integridade da informacao",
    r"litografia", r"centro de dados", r"data center",
    r"computacao em nuvem", r"nuvem computacional", r"infraestrutura digital",
    r"transformacao digital", r"soberania digital", r"soberania de dados",
    r"automacao", r"internet das coisas",
    r"ciberseguranca", r"seguranca cibernetica",
    r"cadastro positivo|scoring|pontuacao de credito",
]
# Sinais temáticos mais fracos: exigem confirmação (entram como "revisar").
REVISAR_PATTERNS = [
    # a sigla isolada "ai"/"AI" é sinal fraco (falso positivo em inglês: "said",
    # "maintain" não casam por \b, mas "AI" sem contexto também não basta)
    r"\bai\b", r"\bml\b",
    r"technology", r"digital", r"innovation", r"data science", r"open data",
    r"software", r"startup", r"platform", r"internet", r"online",
    # --- bloco BR (preservado)
    r"tecnologia", r"inovacao", r"ciencia de dados", r"dados abertos",
    r"plataforma", r"escaneamento",
]

_FORTE_RE = [re.compile(p) for p in FORTE_PATTERNS]
_REVISAR_RE = [re.compile(p) for p in REVISAR_PATTERNS]


def normalizar(texto):
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = t.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).strip().lower()


def classificar_relevancia(*textos):
    """'forte', 'revisar' ou None — nunca inventa: sem sinal claro, descarta."""
    txt = normalizar(" ".join(str(t or "") for t in textos))
    if not txt:
        return None
    if any(r.search(txt) for r in _FORTE_RE):
        return "forte"
    if any(r.search(txt) for r in _REVISAR_RE):
        return "revisar"
    return None


def limpar_texto(valor, limite=600):
    """Converte HTML em texto plano (sem tags, sem entidades) e normaliza espaços."""
    if not valor:
        return ""
    t = re.sub(r"<[^>]+>", " ", str(valor))
    t = html_mod.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limite]


def url_canonica(url):
    """Chave de identidade de um item: URL oficial sem esquema/query/fragmento.

    Usada para não contar duas vezes o mesmo item quando ele aparece em canais
    diferentes (ex.: página 1 e página 2 de uma listagem que ignora paginação).
    """
    alvo = (url or "").strip().lower()
    alvo = re.sub(r"^https?://", "", alvo)
    alvo = re.sub(r"^www\.", "", alvo)
    alvo = alvo.split("#")[0].split("?")[0].rstrip("/")
    return alvo


def hash_texto(*partes):
    base = normalizar(" | ".join(str(p or "") for p in partes))
    return "sha1:" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


MESES_EN = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
            "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
            "jul": 7, "aug": 8, "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def data_eu(texto):
    """'17 September 2026' / 'September 17, 2026' → '2026-09-17'. Sem data → None."""
    if not texto:
        return None
    s = normalizar(str(texto))
    m = re.search(r"(\d{1,2})\s+([a-z]{3,9})\s+(\d{4})", s)
    if m:
        mes = MESES_EN.get(m.group(2))
        if mes:
            try:
                return date(int(m.group(3)), mes, int(m.group(1))).isoformat()
            except ValueError:
                return None
    m = re.search(r"([a-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        mes = MESES_EN.get(m.group(1))
        if mes:
            try:
                return date(int(m.group(3)), mes, int(m.group(2))).isoformat()
            except ValueError:
                return None
    return None


def data_iso(valor, formatos=None):
    """Extrai 'YYYY-MM-DD' de strings oficiais (RSS, JSON, HTML). Sem data → None."""
    if not valor:
        return None
    if isinstance(valor, (int, float)):
        try:
            return datetime.fromtimestamp(float(valor), BRT).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    s = str(valor).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if m:
        d, mo, a = (int(x) for x in m.groups())
        try:
            return date(a, mo, d).isoformat()
        except ValueError:
            return None
    return None


# ------------------------------------------------------------------ HTTP
class Resposta:
    __slots__ = ("url", "status", "content_type", "texto", "segundos", "erro", "url_final")

    def __init__(self, url, status=None, content_type="", texto="", segundos=0.0,
                 erro=None, url_final=None):
        self.url = url
        self.status = status
        self.content_type = content_type
        self.texto = texto
        self.segundos = segundos
        self.erro = erro
        self.url_final = url_final or url

    @property
    def ok(self):
        return self.status is not None and 200 <= self.status < 300

    def json(self):
        try:
            return json.loads(self.texto)
        except (ValueError, TypeError):
            return None


class Cliente:
    """Cliente HTTP enxuto (stdlib) com retry, cache, telemetria e orçamento.

    `orcamento` é um objeto opcional com `.checar()`/`.restante()` (o Budget do
    coletor legislativo). Sem ele, só valem `timeout` e `retries`.
    """

    def __init__(self, timeout=25, retries=3, orcamento=None, ua=UA_PADRAO, logger=print):
        self.timeout = timeout
        self.retries = max(1, retries)
        self.orcamento = orcamento
        self.ua = ua
        self.log = logger
        self._cache = {}
        self._lock = threading.Lock()
        self.stats = {"chamadas": 0, "falhas": 0, "cache": 0, "tempo_total": 0.0,
                      "por_endpoint": {}}

    # -------------------------------------------------------------- telemetria
    @staticmethod
    def rotulo_endpoint(url):
        try:
            p = urllib.parse.urlparse(url)
        except ValueError:
            return "desconhecido"
        host = p.netloc.replace("www.", "")
        return f"{host}{p.path}"[:80]

    def _stat(self, url, campo, valor=1):
        ep = self.stats["por_endpoint"].setdefault(
            self.rotulo_endpoint(url), {"chamadas": 0, "falhas": 0, "tempo_total": 0.0})
        ep[campo] = ep.get(campo, 0) + valor

    def resumo_stats(self):
        return {
            "chamadas": self.stats["chamadas"],
            "falhas": self.stats["falhas"],
            "cache": self.stats["cache"],
            "tempo_total": round(self.stats["tempo_total"], 2),
            "por_endpoint": {k: {"chamadas": v["chamadas"], "falhas": v["falhas"],
                                 "tempo_total": round(v["tempo_total"], 2)}
                             for k, v in sorted(self.stats["por_endpoint"].items())},
        }

    # ------------------------------------------------------------------ fetch
    def get(self, url, accept=None, timeout=None, cache=True, headers=None,
            retry_403=False):
        chave = (url, accept or "")
        if cache:
            with self._lock:
                if chave in self._cache:
                    self.stats["cache"] += 1
                    return self._cache[chave]

        if self.orcamento is not None:
            try:
                self.orcamento.checar()
            except Exception as e:  # orçamento global esgotado
                raise OrcamentoEsgotado(str(e)) from e

        espera = timeout or self.timeout
        if self.orcamento is not None:
            espera = max(5, min(espera, self.orcamento.restante() - 30))

        hdrs = {
            "User-Agent": self.ua,
            "Accept": accept or ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                                 "image/avif,image/webp,*/*;q=0.8"),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, identity",
            # Cabeçalhos de navegador: vários portais oficiais (ex.: TSE) recusam
            # requisições sem eles. Não mudam o conteúdo — apenas permitem a
            # leitura da mesma página pública que qualquer cidadão acessa.
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
        }
        if headers:
            hdrs.update(headers)

        ultimo_erro = None
        for tentativa in range(self.retries):
            t0 = time.monotonic()
            with self._lock:
                self.stats["chamadas"] += 1
            try:
                req = urllib.request.Request(url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=int(espera),
                                            context=ssl.create_default_context()) as r:
                    raw = r.read()
                    if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                        try:
                            raw = gzip.decompress(raw)
                        except OSError:
                            pass
                    texto = raw.decode("utf-8", "replace")
                    resp = Resposta(url, r.status, r.headers.get("Content-Type") or "",
                                    texto, round(time.monotonic() - t0, 2),
                                    url_final=r.geturl())
            except urllib.error.HTTPError as e:
                texto = ""
                try:
                    texto = e.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    pass
                resp = Resposta(url, e.code, (e.headers or {}).get("Content-Type", ""),
                                texto, round(time.monotonic() - t0, 2),
                                erro=f"HTTP {e.code}")
            except Exception as e:  # noqa: BLE001 — rede instável: registra e tenta de novo
                resp = Resposta(url, None, "", "", round(time.monotonic() - t0, 2),
                                erro=f"{type(e).__name__}: {e}")

            with self._lock:
                self.stats["tempo_total"] += time.monotonic() - t0
            self._stat(url, "chamadas")
            self._stat(url, "tempo_total", round(time.monotonic() - t0, 2))

            if resp.ok:
                if cache:
                    with self._lock:
                        self._cache[chave] = resp
                return resp
            ultimo_erro = resp.erro or f"HTTP {resp.status}"
            with self._lock:
                self.stats["falhas"] += 1
            self._stat(url, "falhas")
            if resp.status in (400, 401, 404, 410):
                break  # erro determinístico: não adianta repetir
            if resp.status == 403 and not retry_403:
                break  # bloqueio do portal: repetir de imediato não resolve
            if tentativa + 1 < self.retries:
                # 403 de WAF (portal que limita rajadas do mesmo IP) merece uma
                # espera maior: a mesma URL volta a responder depois de alguns
                # segundos — evidência das sondas do TSE em 17/09/2026.
                time.sleep(20 if resp.status == 403 else 1.5 * (tentativa + 1))
        self.log(f"    [aviso] falha ao consultar {url[:120]} ({ultimo_erro})")
        return resp

    def get_json(self, url, **kw):
        resp = self.get(url, accept="application/json", **kw)
        if not resp.ok:
            return None
        return resp.json()

    def get_texto(self, url, **kw):
        resp = self.get(url, **kw)
        return resp.texto if resp.ok else None

    # --------------------------------------------------- variações por formato
    def get_rss(self, url, **kw):
        """RSS/Atom → lista de dicts {titulo, link, data, descricao}."""
        resp = self.get(url, accept="application/rss+xml, application/xml;q=0.9, */*;q=0.8", **kw)
        if not resp.ok:
            raise FonteIndisponivel(f"RSS indisponível: {url} ({resp.erro or resp.status})")
        itens = parse_rss(resp.texto)
        if not itens:
            raise FonteIndisponivel(f"RSS sem itens reconhecíveis: {url}")
        return itens


# ------------------------------------------------------------ parsers
def parse_rss(xml_texto, base_url=""):
    """RSS 2.0 e Atom → itens normalizados (sem inventar campos ausentes)."""
    if not xml_texto or "<" not in xml_texto:
        return []
    try:
        raiz = ET.fromstring(xml_texto.encode("utf-8", "replace"))
    except ET.ParseError:
        # Alguns feeds do gov.br vêm com entidades HTML soltas; tolera e tenta de novo
        limpo = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", xml_texto)
        try:
            raiz = ET.fromstring(limpo.encode("utf-8", "replace"))
        except ET.ParseError:
            return []
    itens = []
    for no in raiz.iter():
        tag = no.tag.split("}")[-1].lower()
        if tag not in ("item", "entry"):
            continue

        def _txt(*nomes):
            for filho in list(no):
                if filho.tag.split("}")[-1].lower() in nomes:
                    if filho.text:
                        return filho.text.strip()
                    if filho.attrib.get("href"):
                        return filho.attrib["href"].strip()
            return None

        link = _txt("link") or ""
        if not link:
            for filho in list(no):
                if filho.tag.split("}")[-1].lower() == "link" and filho.attrib.get("href"):
                    link = filho.attrib["href"]
        if link and base_url and link.startswith("/"):
            link = urllib.parse.urljoin(base_url, link)
        descricao = limpar_texto(_txt("description", "summary", "encoded", "content") or "", 600)
        data = _txt("pubdate", "published", "updated", "date", "dc:date") \
            or _txt("pubDate", "published", "updated", "date")
        try:
            # RFC 822 (padrão RSS: "Fri, 11 Sep 2026 12:00:00 +0000")
            from email.utils import parsedate_to_datetime
            data = parsedate_to_datetime(data).date().isoformat() if data else None
        except (TypeError, ValueError):
            data = data_iso(data) or data_eu(data)
        itens.append({
            "titulo": limpar_texto(_txt("title") or "", 300),
            "link": link,
            "data": data,
            "descricao": descricao,
        })
    return [i for i in itens if i.get("titulo")]


def parse_html_links(html, base_url, padrao_href, limite=80, descricao_apos=1200):
    """Extrai itens de uma listagem HTML (padrão dos sites Plone do gov.br).

    Para cada âncora que casa com `padrao_href`, monta título (texto da âncora),
    URL absoluta, data (dd/mm/aaaa próxima) e descrição (texto seguinte, limpo).
    É deliberadamente tolerante: se um item não tem data, o campo fica ausente.
    """
    if not html:
        return []
    regex = re.compile(padrao_href)
    itens, vistos = [], set()
    for m in re.finditer(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        href, interno = m.group(1), m.group(2)
        if not regex.search(href):
            continue
        titulo = limpar_texto(interno, 300)
        if len(titulo) < 12:
            continue
        url = urllib.parse.urljoin(base_url, href)
        chave = url.split("#")[0]
        if chave in vistos:
            continue
        vistos.add(chave)
        trecho = html[m.end():m.end() + descricao_apos]
        data = (data_eu(re.search(r"\d{1,2}\s+[A-Za-zç]{3,9}\s+\d{4}", trecho))
                if data_eu(re.search(r"\d{1,2}\s+[A-Za-zç]{3,9}\s+\d{4}", trecho))
                else (data_iso(re.search(r"\d{2}/\d{2}/\d{4}", trecho).group(0))
                      if re.search(r"\d{2}/\d{2}/\d{4}", trecho) else None))
        texto = limpar_texto(re.sub(r"<a\s[^>]*>.*?</a>", " ", trecho, flags=re.I | re.S), 600)
        texto = re.sub(r"^\s*[-–|]\s*", "", texto)
        itens.append({"titulo": titulo, "link": chave, "data": data, "descricao": texto})
        if len(itens) >= limite:
            break
    return itens


# ------------------------------------- decodificadores BR (gov.br / DOU / CNJ)
def parse_dou_json(dados):
    """Busca do DOU (in.gov.br) em JSON → itens com URL oficial.

    O endpoint responde com um envelope cujo array de resultados aparece ora como
    `jsonArray`, ora aninhado (`resultado`, `items`). O parser aceita as variações
    e descarta o que não tiver título ou link oficial.
    """
    if not dados:
        return []
    lista = None
    if isinstance(dados, list):
        lista = dados
    elif isinstance(dados, dict):
        for chave in ("jsonArray", "itens", "items", "results", "resultado", "content"):
            valor = dados.get(chave)
            if isinstance(valor, list):
                lista = valor
                break
            if isinstance(valor, dict):
                for sub in ("jsonArray", "itens", "items", "results"):
                    if isinstance(valor.get(sub), list):
                        lista = valor[sub]
                        break
            if lista is not None:
                break
    if not lista:
        return []
    itens = []
    for it in lista:
        if not isinstance(it, dict):
            continue
        titulo = limpar_texto(it.get("title") or it.get("titulo") or it.get("nome") or "", 400)
        href = (it.get("href") or it.get("url") or it.get("link") or "").strip()
        if not titulo or not href:
            continue
        if href.startswith("/"):
            href = urllib.parse.urljoin("https://www.in.gov.br/", href)
        resumo = limpar_texto(it.get("abstract") or it.get("content") or it.get("descricao")
                              or it.get("ementa") or "", 900)
        orgao = limpar_texto(it.get("pubName") or it.get("orgao") or it.get("hierarchyStr")
                             or it.get("hierarchyList") or "", 200)
        itens.append({
            "titulo": titulo,
            "link": href.split("#")[0],
            "data": data_iso(it.get("pubDate") or it.get("date") or it.get("data")
                             or it.get("dataPublicacao")),
            "descricao": (resumo + (f" · {orgao}" if orgao else ""))[:900],
            "tipo_ato": limpar_texto(it.get("artType") or it.get("type") or "", 80) or None,
            "secao": limpar_texto(it.get("pubName") or "", 80) or None,
        })
    return itens


def parse_plone_search(dados):
    """plone.restapi (@search / pasta) → itens oficiais de sites gov.br (Volto).

    Cada item traz `@id` (URL oficial), `title`, `description` e `effective`.
    Itens que não são conteúdo editorial (imagens, arquivos de layout) são
    descartados: só entram tipos com título e URL de página.
    """
    if not isinstance(dados, dict):
        return []
    itens = []
    for it in (dados.get("items") or []):
        if not isinstance(it, dict):
            continue
        url = (it.get("@id") or "").strip()
        titulo = limpar_texto(it.get("title") or "", 300)
        if not url or not titulo:
            continue
        tipo = it.get("@type") or ""
        if tipo in ("Image", "Image Container"):
            continue
        if re.search(r"\.(png|jpe?g|gif|webp|svg|ico)$", url, re.I):
            continue
        itens.append({
            "titulo": titulo,
            "link": url.split("#")[0],
            "data": data_iso(it.get("effective") or it.get("created") or it.get("modified")),
            "descricao": limpar_texto(it.get("description") or "", 600),
            "tipo_ato": tipo or None,
            "orgao_item": limpar_texto(it.get("head_title") or "", 120) or None,
        })
    return itens


def parse_cnj_atos(dados):
    """API oficial do Sistema de Atos Normativos do CNJ (atos.cnj.jus.br).

    Formato: {"data": [{id, tipo, numero, data_publicacao, situacao, ementa,
    observacao, url_ato, ...}], "total": n}. O título é montado com os campos
    oficiais (nunca inventado); a ementa vem do próprio ato.
    """
    if not isinstance(dados, dict):
        return []
    itens = []
    for ato in (dados.get("data") or []):
        if not isinstance(ato, dict) or not ato.get("id"):
            continue
        tipo = limpar_texto(ato.get("tipo") or "Ato", 60)
        numero = limpar_texto(ato.get("numero") or "", 30)
        titulo = f"{tipo} CNJ nº {numero}" if numero else f"{tipo} CNJ"
        ementa = limpar_texto(ato.get("ementa") or "", 800)
        situacao = limpar_texto(ato.get("situacao") or "", 60)
        obs = limpar_texto(ato.get("observacao") or "", 200)
        descricao = " ".join(x for x in (ementa, f"Situação: {situacao}." if situacao else "",
                                         obs) if x)
        itens.append({
            "titulo": titulo,
            "link": f"https://atos.cnj.jus.br/atos/detalhar/{ato['id']}",
            "data": data_iso(ato.get("data_publicacao")),
            "descricao": descricao[:900],
            "tipo_ato": tipo,
            "situacao": situacao or None,
        })
    return itens


DOU_RE_SCRIPT = re.compile(
    r'<script[^>]+id="[^"]*BuscaDouPortlet_params"[^>]*>(.*?)</script>', re.I | re.S)


def parse_dou_embutido(html):
    """Extrai o JSON de resultados embutido na página de busca do DOU.

    A busca do in.gov.br devolve HTML com um <script type="application/json">
    contendo {"jsonArray": [...]}. Cada resultado tem `title`, `urlTitle`,
    `pubDate`, `content`, `artType` e `hierarchyStr` — é daí que saem o título,
    a data, o órgão e a URL oficial do ato.
    """
    if not html:
        return []
    m = DOU_RE_SCRIPT.search(html)
    if not m:
        return []
    bruto = html_mod.unescape(m.group(1)).strip()
    try:
        dados = json.loads(bruto)
    except ValueError:
        return []
    itens = []
    for it in (dados.get("jsonArray") or []):
        if not isinstance(it, dict):
            continue
        titulo = limpar_texto(it.get("title") or "", 400)
        url_title = (it.get("urlTitle") or "").strip()
        if not titulo or not url_title:
            continue
        hierarquia = limpar_texto(it.get("hierarchyStr") or it.get("hierarchyList") or "", 240)
        art_type = limpar_texto(it.get("artType") or "", 80)
        conteudo = limpar_texto(it.get("content") or "", 900)
        itens.append({
            "titulo": titulo,
            "link": f"https://www.in.gov.br/web/dou/-/{url_title}",
            "data": data_iso(it.get("pubDate")),
            "descricao": " ".join(x for x in (conteudo,
                                              f"({art_type} — {hierarquia})" if hierarquia else "")
                                 if x)[:900],
            "tipo_ato": art_type or None,
            "hierarquia": hierarquia or None,
            "secao": (it.get("pubName") or None),
            "edicao": it.get("editionNumber") or None,
            "id_dou": it.get("classPK") or None,
        })
    return itens


def html_para_texto_blocos(html, padrao_href, base_url="https://www.in.gov.br/", limite=50):
    """Fallback: extrai resultados da busca do DOU direto do HTML.

    Cada resultado tem um link `/web/dou/-/<slug>`; o título vem da âncora e o
    resumo do bloco seguinte. Usado só quando o endpoint JSON não está disponível.
    """
    if not html:
        return []
    itens, vistos = [], set()
    for m in re.finditer(r'<a[^>]+href="(/web/dou/-/[^"#?]+)"[^>]*>(.*?)</a>', html, re.I | re.S):
        href, interno = m.group(1), m.group(2)
        titulo = limpar_texto(interno, 400)
        if len(titulo) < 10 or href in vistos:
            continue
        vistos.add(href)
        trecho = html[m.end():m.end() + 1500]
        texto = limpar_texto(trecho, 700)
        data = data_iso(re.search(r"\d{2}/\d{2}/\d{4}", trecho).group(0)) if re.search(
            r"\d{2}/\d{2}/\d{4}", trecho) else None
        itens.append({"titulo": titulo, "link": urllib.parse.urljoin(base_url, href),
                      "data": data, "descricao": texto})
        if len(itens) >= limite:
            break
    return itens



# ------------------------------------------------------- modelo de canal/fonte
class Canal:
    """Um endpoint oficial de uma fonte (RSS, JSON de API ou listagem HTML).

    formato:
      rss      — feed oficial
      json     — API oficial em JSON (com `parser` específico)
      html     — listagem oficial em HTML (com `padrao_href`)
    opcoes:
      parser           — "wp_json" | "lista_json" | "generico" | "eu:<funcao>"
      padrao_href      — regex de href (formato html)
      paginas          — nº de páginas (listagens paginadas por ?b_start:int=N)
      passo            — itens por página
      accept           — cabeçalho Accept
      obrigatorio      — se False, a falha do canal não derruba a fonte
      extrai          — função(opcional) items → items (pós-processamento)
      topicos         — termos usados em canais de busca (montam a URL)
      url_template    — URL com {topico} para canais de busca por tema
    """

    def __init__(self, rotulo, url, formato="html", parser="generico", padrao_href=None,
                 paginas=1, passo=20, accept=None, obrigatorio=True, extrai=None,
                 topicos=None, url_template=None, tipo_padrao=None, opcoes=None,
                 filtro_tema=None, dias=None):
        self.rotulo = rotulo
        self.url = url
        self.formato = formato
        self.parser = parser
        self.padrao_href = padrao_href
        self.paginas = max(1, int(paginas))
        self.passo = passo
        self.accept = accept
        self.obrigatorio = obrigatorio
        self.extrai = extrai
        self.topicos = topicos or []
        self.url_template = url_template or url
        self.tipo_padrao = tipo_padrao
        self.opcoes = opcoes or {}
        # `filtro_tema`: função(item) -> bool aplicada ao resultado do canal
        # (ex.: manter só itens cuja hierarquia do DOU é do órgão monitorado)
        self.filtro_tema = filtro_tema
        self.dias = dias  # janela de datas para canais de busca (DOU)

    def _com_params(self, url):
        extras = self.opcoes.get("params") or {}
        if not extras:
            return url
        sep = "&" if "?" in url else "?"
        return url + sep + urllib.parse.urlencode(extras)

    def urls(self):
        """Gera (tópico, url) do canal.

        Suporta {topico}, {year}/{prev_year} (ano), janelas {from}/{to}
        (DD-MM-AAAA) e {from_eu}/{to_eu} (DD/MM/AAAA) e paginação via
        `opcoes["param_pagina"]` (ex.: "page" → ?page=N).
        """
        hoje = datetime.now(BRT).date()
        inicio = hoje - timedelta(days=self.dias if self.dias else 30)
        ctx = {"from": inicio.strftime("%d-%m-%Y"), "to": hoje.strftime("%d-%m-%Y"),
               "from_eu": inicio.strftime("%d/%m/%Y"), "to_eu": hoje.strftime("%d/%m/%Y"),
               "year": hoje.year, "prev_year": hoje.year - 1}
        param_pag = self.opcoes.get("param_pagina")
        if self.topicos:
            for t in self.topicos:
                yield t, self._com_params(
                    self.url_template.format(topico=urllib.parse.quote(t), **ctx))
            return
        for i in range(self.paginas):
            base = self.url_template.format(topico="", **ctx)
            if param_pag and i > 0:
                sep = "&" if "?" in base else "?"
                base = f"{base}{sep}{urllib.parse.quote(param_pag)}={i + 1}"
            yield None, self._com_params(base)


class ResultadoFonte:
    """Resultado da coleta de uma fonte (itens + saúde + telemetria)."""

    def __init__(self, orgao, nome):
        self.orgao = orgao
        self.nome = nome
        self.itens = []
        self.tentativa_em = datetime.now(BRT).isoformat(timespec="seconds")
        self.duracao = 0.0
        self.canais_ok = []
        self.canais_falhos = []          # todas as falhas (visíveis no painel)
        self.canais_falhos_obrigatorios = []
        self.canais_opcionais_falhos = []
        self.endpoints = []
        self.erros = []
        self.itens_consultados = 0
        self.itens_relevantes = 0
        self.itens_descartados = 0
        self.itens_duplicados = 0
        self.revisao_pendente = 0
        self.ultima_execucao_ok = None
        self.parcial_por_orcamento = False
        self.canais_detalhe = []

    @property
    def status(self):
        """ok · parcial · falha — calculado só com os canais obrigatórios.

        Um canal opcional que falha (ex.: portal com bloqueio anti-bot) fica
        registrado em `canais_opcionais_falhos` e no painel, mas não rebaixa a
        fonte quando ela cumpriu o que é obrigatório pela via oficial.
        """
        if not self.canais_ok:
            return "falha"
        if self.canais_falhos_obrigatorios or self.parcial_por_orcamento:
            return "parcial"
        return "ok"

    def erro_resumo(self):
        return "; ".join(self.erros[:4]) or None

    def como_dict(self, novidades=0):
        return {
            "nome": self.nome,
            "status": self.status,
            "ultima_tentativa": self.tentativa_em,
            "ultima_execucao_ok": self.ultima_execucao_ok,
            "itens_consultados": self.itens_consultados,
            "itens_relevantes": self.itens_relevantes,
            "itens_descartados": self.itens_descartados,
            "itens_duplicados": self.itens_duplicados,
            "revisao_pendente": self.revisao_pendente,
            "novidades": novidades,
            "erros": len(self.erros),
            "duracao_segundos": round(self.duracao, 1),
            "endpoints": self.endpoints,
            "canais_detalhe": self.canais_detalhe,
            "canais_ok": self.canais_ok,
            "canais_falhos": self.canais_falhos,
            "canais_falhos_obrigatorios": self.canais_falhos_obrigatorios,
            "canais_opcionais_falhos": self.canais_opcionais_falhos,
            "erro_detalhe": self.erro_resumo(),
        }


class ContextoFonte:
    """Contexto de execução de uma fonte: cliente HTTP, tempo e log prefixado."""

    def __init__(self, orgao, timeout_s=180, orcamento=None, dry_run=False, ua=UA_PADRAO,
                 logger=print, timeout_http=25, retries=3):
        self.orgao = orgao
        self.timeout_s = max(10, int(timeout_s))
        self.t0 = time.monotonic()
        self.orcamento = orcamento
        self.dry_run = dry_run
        self.cliente = Cliente(timeout=timeout_http, retries=retries, orcamento=orcamento,
                               ua=ua, logger=logger)
        self.log = logger

    def restante(self):
        return max(0.0, self.timeout_s - (time.monotonic() - self.t0))

    def expirado(self, folga=0.0):
        if self.restante() <= folga:
            return True
        if self.orcamento is not None:
            return self.orcamento.expirado()
        return False

    def checar(self, folga=0.0):
        if self.expirado(folga):
            raise OrcamentoEsgotado(
                f"tempo da fonte '{self.orgao}' esgotado ({self.timeout_s}s)")


class Fonte:
    """Conector de um órgão. Subclasses declaram `canais` e (se preciso) `parser`."""

    orgao = "?"
    nome = "?"
    obrigatoria = True
    canais = ()
    # `repetir_403`: portais com WAF que bloqueiam rajadas do mesmo IP (TSE)
    # voltam a responder depois de alguns segundos — a fonte que liga esta opção
    # aceita repetir a chamada com espera maior antes de marcar o canal falho.
    repetir_403 = False

    def __init__(self, logger=print):
        self.log = logger

    # ---------------------------------------------------------------- coleta
    def coletar(self, ctx: ContextoFonte, resultado: ResultadoFonte):
        resultado.canais_detalhe = resultado.canais_detalhe or []
        for canal in self.canais:
            if ctx.expirado(5):
                resultado.parcial_por_orcamento = True
                resultado.erros.append(f"tempo esgotado antes do canal '{canal.rotulo}'")
                self._marca_falha(resultado, canal)
                continue
            resultado.endpoints.append(canal.url)
            try:
                itens = self._coletar_canal(ctx, canal)
            except OrcamentoEsgotado as e:
                resultado.parcial_por_orcamento = True
                resultado.erros.append(f"{canal.rotulo}: {e}")
                self._marca_falha(resultado, canal)
                continue
            except FonteIndisponivel as e:
                resultado.erros.append(f"{canal.rotulo}: {e}")
                self._marca_falha(resultado, canal)
                continue
            except Exception as e:  # noqa: BLE001 — um canal não derruba a fonte
                resultado.erros.append(f"{canal.rotulo}: {type(e).__name__}: {e}")
                self._marca_falha(resultado, canal)
                continue

            resultado.canais_ok.append(canal.rotulo)
            self.log(f"    · {canal.rotulo}: {len(itens)} itens")
            detalhe = {"canal": canal.rotulo, "url": canal.url,
                       "itens_brutos": len(itens),
                       "amostra_hierarquia": sorted({
                           (i.get("hierarquia") or "")[:60] for i in itens if i.get("hierarquia")
                       })[:3]}
            resultado.canais_detalhe.append(detalhe)
            self._absorver(resultado, itens, canal)
            detalhe["itens_relevantes"] = len(resultado.itens) - self._itens_antes

        if not resultado.canais_ok:
            raise FonteIndisponivel(
                "nenhum canal respondeu — " + (resultado.erro_resumo() or "sem detalhe"))

    @staticmethod
    def _marca_falha(resultado, canal):
        resultado.canais_falhos.append(canal.rotulo)
        if canal.obrigatorio:
            resultado.canais_falhos_obrigatorios.append(canal.rotulo)
        else:
            resultado.canais_opcionais_falhos.append(canal.rotulo)

    def _absorver(self, resultado, itens, canal):
        self._itens_antes = len(resultado.itens)
        if not hasattr(self, "_vistos"):
            self._vistos = set()
        for item in itens:
            resultado.itens_consultados += 1
            if not item.get("link") or not item.get("titulo"):
                continue
            chave = url_canonica(item.get("link"))
            if chave and chave in self._vistos:
                # Mesmo item já absorvido por outro canal desta fonte
                # (paginação ignorada pelo servidor, feeds repetidos etc.):
                # conta uma vez só — nada é duplicado no dataset nem no painel.
                resultado.itens_duplicados += 1
                continue
            if chave:
                self._vistos.add(chave)
            rel = classificar_relevancia(item.get("titulo"), item.get("descricao"))
            if not rel:
                resultado.itens_descartados += 1
                continue
            item.setdefault("tipo", canal.tipo_padrao or "publicacao")
            item["orgao"] = self.orgao
            item["fonte"] = f"{self.nome} — {canal.rotulo}"
            item["canal"] = canal.rotulo
            item["relevancia"] = rel
            item["revisao_pendente"] = rel == "revisar"
            item["url_oficial"] = item.pop("link")
            item["id"] = self.id_item(item)
            item["texto_hash"] = hash_texto(item.get("titulo"), item.get("descricao"))
            resultado.itens_relevantes += 1
            if item["revisao_pendente"]:
                resultado.revisao_pendente += 1
            resultado.itens.append(item)

    # -------------------------------------------------------------- helpers
    def id_item(self, item):
        """Id estável: derivado da URL oficial (nunca do conteúdo, que muda)."""
        url = item.get("url_oficial") or ""
        slug = re.sub(r"^https?://(www\.)?", "", url).split("?")[0].rstrip("/")
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").lower()
        return f"{self.orgao}_{slug[:110]}"

    def _coletar_canal(self, ctx, canal):
        if canal.formato == "rss":
            return self._coletar_rss(ctx, canal)
        if canal.formato == "json":
            return self._coletar_json(ctx, canal)
        return self._coletar_html(ctx, canal)

    def _coletar_rss(self, ctx, canal):
        itens = []
        for _topico, url in canal.urls():
            ctx.checar(5)
            itens += ctx.cliente.get_rss(url, retry_403=self.repetir_403)
        return self._pos_processar(itens, canal)

    def _coletar_json(self, ctx, canal):
        itens = []
        for topico, url in canal.urls():
            ctx.checar(5)
            cabecalhos = {"X-Requested-With": "XMLHttpRequest"} if canal.opcoes.get("ajax") else None
            if canal.accept and canal.accept != "application/json":
                resp = ctx.cliente.get(url, accept=canal.accept, headers=cabecalhos,
                                   retry_403=self.repetir_403)
                dados = resp.json() if resp.ok else None
            else:
                dados = ctx.cliente.get_json(url, headers=cabecalhos)
            if dados is None:
                raise FonteIndisponivel(f"JSON indisponível: {url}")
            itens += self._parser_json(dados, canal, topico)
        return self._pos_processar(itens, canal)

    def _parser_json(self, dados, canal, topico=None):
        parser = canal.parser
        if parser and parser.startswith("eu:"):
            import eu_parsers
            fn = getattr(eu_parsers, parser[3:])
            return fn(dados, canal=canal, topico=topico)
        if parser == "wp_json":
            return self._parse_wp_json(dados)
        if parser == "lista_json":
            return self._parse_lista_json(dados, canal)
        # genérico: tenta os formatos conhecidos
        return parse_dou_json(dados) or self._parse_lista_json(dados, canal)

    @staticmethod
    def _parse_wp_json(dados):
        itens = []
        for post in dados if isinstance(dados, list) else []:
            if not isinstance(post, dict):
                continue
            titulo = limpar_texto((post.get("title") or {}).get("rendered")
                                  if isinstance(post.get("title"), dict) else post.get("title"), 300)
            link = post.get("link") or post.get("guid", {}).get("rendered") if isinstance(
                post.get("guid"), dict) else post.get("link")
            resumo = limpar_texto((post.get("excerpt") or {}).get("rendered")
                                  if isinstance(post.get("excerpt"), dict) else post.get("excerpt"), 600)
            itens.append({"titulo": titulo, "link": link or "",
                          "data": data_iso(post.get("date") or post.get("modified")),
                          "descricao": resumo,
                          "tipo_ato": (post.get("type") or None)})
        return itens

    @staticmethod
    def _parse_lista_json(dados, canal):
        """JSON de API genérico: procura uma lista de dicts com título e link."""
        lista = None
        if isinstance(dados, list):
            lista = dados
        elif isinstance(dados, dict):
            chaves = canal.opcoes.get("chaves_lista") or (
                "dados", "items", "itens", "results", "resultados", "content", "data", "list")
            for ch in chaves:
                if isinstance(dados.get(ch), list):
                    lista = dados[ch]
                    break
        itens = []
        for it in lista or []:
            if not isinstance(it, dict):
                continue
            titulo = None
            for ch in ("titulo", "title", "nome", "name", "descricao", "description", "ementa"):
                if it.get(ch):
                    titulo = limpar_texto(it[ch], 300)
                    break
            link = None
            for ch in ("link", "url", "url_oficial", "href", "permalink", "uri"):
                if it.get(ch):
                    link = str(it[ch]).strip()
                    break
            if not titulo or not link:
                continue
            data = None
            for ch in ("data", "date", "data_publicacao", "published", "pubDate", "metadata_modified"):
                data = data_iso(it.get(ch))
                if data:
                    break
            descricao = ""
            for ch in ("descricao", "description", "resumo", "abstract", "summary", "ementa"):
                if it.get(ch):
                    descricao = limpar_texto(it[ch], 600)
                    break
            itens.append({"titulo": titulo, "link": link, "data": data, "descricao": descricao})
        return itens

    def _coletar_html(self, ctx, canal):
        itens = []
        for _topico, url in canal.urls():
            ctx.checar(5)
            resp = ctx.cliente.get(url, retry_403=self.repetir_403)
            if not resp.ok:
                raise FonteIndisponivel(f"HTML indisponível: {url} ({resp.erro or resp.status})")
            html = resp.texto
            if canal.parser and canal.parser.startswith("eu:"):
                import eu_parsers
                fn = getattr(eu_parsers, canal.parser[3:])
                extraidos = fn(html, url=url, canal=canal)
                if not extraidos and len(html) > 5000:
                    # Página existe mas nenhum item foi reconhecido: ou o layout
                    # mudou, ou a página é um desafio anti-bot. Nos dois casos o
                    # correto é falhar o canal (nunca fingir que não há novidade).
                    raise FonteIndisponivel(
                        f"listagem sem itens reconhecíveis ({len(html)} bytes): {url}")
                itens += extraidos
            else:
                if not canal.padrao_href:
                    raise FonteIndisponivel(f"canal HTML sem padrao_href: {canal.rotulo}")
                extraidos = parse_html_links(html, url, canal.padrao_href,
                                             limite=canal.opcoes.get("limite", 60))
                if not extraidos and len(html) > 5000:
                    # Página existe mas nenhum item foi reconhecido: ou o layout
                    # mudou, ou a página é um desafio anti-bot. Nos dois casos o
                    # correto é falhar o canal (nunca fingir que não há novidade).
                    raise FonteIndisponivel(
                        f"listagem sem itens reconhecíveis ({len(html)} bytes): {url}")
                itens += extraidos
        return self._pos_processar(itens, canal)

    def _pos_processar(self, itens, canal):
        if canal.extrai:
            itens = canal.extrai(itens, canal)
        if canal.filtro_tema:
            itens = [i for i in itens if canal.filtro_tema(i)]
        return [i for i in itens if i.get("titulo") and i.get("link")]


# --------------------------------------------------------------- registro
_REGISTRO = {}


def registrar(classe):
    """Decorador que registra uma fonte no catálogo do coletor."""
    inst = classe(logger=lambda *_: None)
    _REGISTRO[inst.orgao] = classe
    return classe


def fontes_disponiveis():
    return sorted(_REGISTRO)


def instanciar(orgao, logger=print):
    if orgao not in _REGISTRO:
        raise KeyError(f"fonte desconhecida: {orgao} (disponíveis: {', '.join(fontes_disponiveis())})")
    return _REGISTRO[orgao](logger=logger)
