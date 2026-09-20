#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_legislation.py — Motor legislativo do Monitor UE (procedimentos).

Camada anterior ao build: consulta as fontes oficiais da União Europeia,
compara com o estado anterior versionado em /data/legislation, registra
mudanças em updates.json e atualiza o dataset (fonte única da verdade).
Depois disso, `python3 scripts/build_site.py` regenera o site.

Uso:
    python3 scripts/update_legislation.py                    # execução completa
    python3 scripts/update_legislation.py --dry-run          # consulta e relata, sem gravar
    python3 scripts/update_legislation.py --budget-min 25    # teto de tempo da coleta
    python3 scripts/update_legislation.py --max-novas 25     # teto de fichas novas por execução
    python3 scripts/update_legislation.py --limite 60        # verificar apenas as 60 prioritárias

Orçamento de tempo (obrigatório para a automação): a coleta tem um teto de
duração (padrão 25 min, configurável por `--budget-min` ou pela variável
`MONITOR_BUDGET_SEGUNDOS`). Ao se aproximar do teto, o coletor para de iniciar
novas consultas, **persiste o que já foi verificado** e registra a execução com
status `parcial` — o site é reconstruído e publicado de qualquer forma.

Sem dependências externas (apenas stdlib). É terminantemente proibido inventar
dados: tudo que este script grava vem de resposta oficial das fontes abaixo.
Campos não confirmados ficam ausentes.

Fontes oficiais consultadas:
  Parlamento Europeu — Open Data Portal, API oficial v2
    /procedures                      (listagem de procedimentos; JSON-LD)
    /procedures/{process_id}         (ficha completa: eventos, estágios,
                                     votações, assinatura, publicação no JO)
    Evidência da sonda (18/09/2026): a ficha do AI Act (2021-0106) devolve
    consists_of com activity_date, tipo de atividade (REFERRAL,
    COMMITTEE_ADOPTING_REPORT, PLENARY_VOTE, SIGNATURE,
    PUBLICATION_OFFICIAL_JOURNAL…) e occurred_at_stage (RDG1…) — é dessa ficha
    que saem estágio, votações e datas, sem nunca estimar nada.
  EUR-Lex — busca oficial pública (search.html?type=quick&scope=EURLEX)
    Resultados com CELEX, forma do ato, data e referência de procedimento
    interinstitucional; usada na descoberta de procedimentos novos e para
    completar o título oficial quando a ficha do Parlamento não o traz.
  Parlamento Europeu — Legislative Train Schedule
    Fichas editoriais oficiais por dossiê; usadas (com limite) para descobrir
    arquivos interinstitucionais novos.
  Comissão Europeia — Have Your Say (Better Regulation)
    Listagem oficial de consultas públicas/calls for evidence com período de
    feedback futuro — é a agenda oficial verificável (os endpoints de reuniões
    do Parlamento na API v2 retornam corpo vazio — limitação documentada).

Além do motor legislativo, a mesma execução roda os conectores regulatórios
multiórgão de `scripts/sources` (European AI Office, EUR-Lex/JO, Conselho,
Comissão, Parlamento, EDPB e EDPS) em subprocessos isolados com timeout
próprio — ver `scripts/update_sources_eu.py`. Os itens dessas fontes ficam em
data/legislation/atos.json, as mudanças em updates.json e a saúde de cada
fonte em `fontes_monitoradas` (com `status_global`: OK · PARCIAL · FALHA).

Identidade dos dossiês: o **número de procedimento interinstitucional**
(ex.: 2021/0106(COD)) é a chave compartilhada entre Parlamento, Conselho e
Comissão. Os ids do dataset são normalizados como `ue_<ano>_<numero>_<tipo>`
(ex.: `ue_2021_0106_cod`) e nunca derivam do título.
"""
import argparse
import json
import os
import re
import shutil
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scoring_eu import compute_impact_score  # noqa: E402
from sources.eu_parsers import (  # noqa: E402
    RE_PROC_REF, parse_ep_procedimento, parse_eurlex_busca,
    parse_legislative_train, parse_consultas_hys,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "legislation-eu")   # dataset do monitor UE (o BR permanece em data/legislation)

EP_API = "https://data.europarl.europa.eu/api/v2"
JSONLD = "application/ld%2Bjson"
EURLEX = "https://eur-lex.europa.eu"
HYS = "https://ec.europa.eu/info/law/better-regulation/have-your-say/initiatives_en"
TRAIN_THEMES = [
    "https://www.europarl.europa.eu/legislative-train/theme-a-europe-fit-for-the-digital-age",
]
DOCEO = "https://www.europarl.europa.eu/doceo/document"

BRT = timezone(timedelta(hours=-3))
UA = {"User-Agent": "monitor-ia-ue/1.0 (+https://monitor.lcfconsulting.com.br)",
      "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}

OLD_DOMAIN = "lcaladoferreira.github.io/monitor-legislativo"

# ---------------------------------------------------------------- orçamento
# Por que isto existe: o dataset cresce a cada execução (mais procedimentos =
# mais fichas para consultar). Sem teto de tempo, a coleta pode passar do
# limite do job do GitHub Actions ANTES do rebuild/commit — o site ficaria
# congelado na execução anterior. O orçamento garante que a execução sempre
# termine a tempo de publicar (mesmo que parcialmente).
def _env_int(nome, padrao):
    try:
        return int(os.environ.get(nome, "") or padrao)
    except ValueError:
        return padrao


BUDGET_S = _env_int("MONITOR_BUDGET_SEGUNDOS", 25 * 60)   # teto da coleta
MARGEM_FINAL_S = 90          # reserva para persistir e imprimir o resumo
MAX_NOVAS = _env_int("MONITOR_MAX_NOVAS", 25)             # fichas novas por execução
MAX_PROPS = _env_int("MONITOR_MAX_PROPS", 0)              # 0 = sem limite
WORKERS = max(1, _env_int("MONITOR_WORKERS", 5))          # threads de coleta
HTTP_CONCORRENCIA = max(1, _env_int("MONITOR_HTTP_CONCORRENCIA", 4))
HTTP_TIMEOUT = _env_int("MONITOR_HTTP_TIMEOUT", 20)
HTTP_RETRIES = max(1, _env_int("MONITOR_HTTP_RETRIES", 2))
TRAIN_MAX_PAGINAS = _env_int("MONITOR_TRAIN_PAGINAS", 8)  # fichas do Train por execução


class BudgetExceeded(RuntimeError):
    """Levantada quando o orçamento de tempo da coleta se esgota."""


class Budget:
    """Relógio monotônico compartilhado pelas threads.

    `margem` é a reserva final: quando o tempo restante cai abaixo dela, o
    coletor para de iniciar consultas e fecha a execução graciosamente.
    """

    def __init__(self, segundos, margem=None):
        self.limite = int(segundos)
        self.margem = MARGEM_FINAL_S if margem is None else margem
        self._t0 = time.monotonic()

    def decorrido(self):
        return time.monotonic() - self._t0

    def restante(self):
        return max(0.0, self.limite - self.decorrido())

    def expirado(self, folga=0):
        # A margem final (reserva p/ build/commit) integra o limiar: sem isso o
        # motor consome o tempo reservado e o run perde a gravação do dataset.
        return self.restante() <= (self.margem + max(0, folga))

    def checar(self, folga=0):
        if self.expirado(folga):
            raise BudgetExceeded(
                f"orçamento de {self.limite}s esgotado "
                f"({int(self.decorrido())}s decorridos)")

    def pausa(self, segundos):
        if segundos <= 0:
            return
        fim = time.monotonic() + min(segundos, max(0, self.restante() - self.margem))
        while time.monotonic() < fim:
            time.sleep(min(0.5, max(0.01, fim - time.monotonic())))


BUDGET = Budget(BUDGET_S)

# Tipos de procedimento interinstitucional monitorados (sufixo da referência).
# COD/CNS/CONS = legislativos; NLE/INI/RES = não legislativos (consultas,
# iniciativas próprias, resoluções); REG = aprovação de atos delegados/de
# execução; DEC/BUA = orçamentários (monitorados só com relevância forte).
TIPO_PROC_PT = {
    "COD": "procedimento legislativo ordinário",
    "CNS": "procedimento legislativo especial (consulta)",
    "CONS": "procedimento legislativo especial (cooperação)",
    "NLE": "procedimento não legislativo",
    "INI": "iniciativa própria do Parlamento",
    "RES": "resolução do Parlamento",
    "REG": "aprovação de ato delegado/de execução",
    "DEC": "procedimento orçamentário",
    "APP": "aprovação",
    "BUA": "procedimento orçamentário",
    "CWP": "procedimento orçamentário",
}
TIPOS_LEGISLATIVOS = {"COD", "CNS", "CONS"}
TIPOS_SECUNDARIOS = {"NLE", "INI", "RES", "REG"}

# --- Relevância temática (texto normalizado: minúsculo, sem acento; inglês) ---
STRONG_PATTERNS = [
    r"artificial intelligence", r"\bai act\b", r"\bai office\b", r"\bai safety\b",
    r"\bai governance\b", r"\bai literacy\b", r"\bai regulatory sandbox",
    r"\bai systems?\b", r"artificial intelligence systems?", r"\bai model",
    r"general[- ]purpose ai", r"\bgpai\b", r"foundation models?", r"frontier models?",
    r"generative ai", r"generative artificial intelligence",
    r"large language models?", r"\bllms?\b", r"machine learning", r"deep learning",
    r"neural networks?", r"\bchatbots?\b", r"\bai agents?\b", r"autonomous ai",
    r"high[- ]risk ai", r"prohibited ai practices?", r"ai transparency",
    r"ai auditing", r"training data", r"model training", r"model evaluation",
    r"deepfake", r"synthetic content", r"synthetic media", r"ai[- ]generated content",
    r"facial recognition", r"remote biometric identification", r"biometrics",
    r"emotion recognition", r"automated decision[- ]making", r"algorithmic decision",
    r"algorithmic transparency", r"data protection", r"personal data", r"\bgdpr\b",
    r"cybersecurity", r"data cent(er|re)s?", r"semiconductors?", r"\bchips act\b",
    r"high[- ]performance computing", r"supercomput", r"quantum comput",
    r"digital services act", r"digital markets act", r"\bdsa\b.*platform",
    r"\beprivacy\b", r"\bdata act\b", r"\bdata governance act\b",
]
MEDIUM_PATTERNS = [
    r"\balgorithm", r"automat", r"robot", r"internet of things", r"\biot\b",
    r"\bprivacy\b", r"\bcookies?\b", r"cyber", r"\bcloud\b", r"\bchip",
    r"\bdigital\b", r"\bplatform", r"online environment", r"\bonline\b",
]
# Termos de infraestrutura/tecnologia que isoladamente geram revisão pendente
# (evitar falso positivo em inglês — "digital" aparece em quase todo ato).
# Importante: cada padrão aqui também precisa existir em MEDIUM_PATTERNS.
INFRA_ONLY = [r"\bdigital\b", r"\bplatform", r"\bonline\b", r"\bcloud\b", r"\bchip",
              r"cyber", r"\bcookies?\b", r"online environment"]

STRONG_RE = [re.compile(p) for p in STRONG_PATTERNS]
MEDIUM_RE = [re.compile(p) for p in MEDIUM_PATTERNS]
INFRA_RE = [re.compile(p) for p in INFRA_ONLY]

FONTES_PARLAMENTO = [
    "Parlamento Europeu — Open Data Portal v2 (procedures, ficha do dossiê)",
    "Parlamento Europeu — Open Data Portal v2 (eventos do procedimento)",
    "Parlamento Europeu — Legislative Train Schedule",
    "Parlamento Europeu — textos adotados (DOCEO, via eventos)",
]
FONTES_EURLEX = [
    "EUR-Lex — busca oficial (metadados de atos)",
    "EUR-Lex — busca oficial (descoberta de procedimentos)",
]
FONTES_HYS = [
    "Comissão Europeia — Have Your Say (agenda de consultas)",
]

# Termos usados na descoberta por busca oficial (inglês, idioma técnico).
KEYWORDS_DESCOBERTA = [
    "artificial intelligence",
    "AI Act",
    "general-purpose AI",
    "deepfake",
    "facial recognition",
    "automated decision-making",
    "foundation models",
]


def norm(t):
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode("ascii")
    return t.lower()


_CURL_BIN = shutil.which("curl")
_HTTP_SEM = threading.BoundedSemaphore(HTTP_CONCORRENCIA)  # concorrência máxima de HTTP
_HTTP_LOCK = threading.Lock()
_HTTP_CACHE = {}          # url -> payload (evita consultar a mesma ficha 2x na execução)
_HTTP_STATS = {"chamadas": 0, "cache": 0, "falhas": 0, "tempo_total": 0.0,
               "por_endpoint": {}}


def endpoint_label(url):
    """Rótulo estável do endpoint (sem ids), usado nas métricas de custo."""
    try:
        partes = urllib.parse.urlparse(url)
    except ValueError:
        return "desconhecido"
    host = partes.netloc.lower()
    if "europarl" in host:
        casa = "parlamento"
    elif "eur-lex" in host:
        casa = "eurlex"
    elif "ec.europa.eu" in host or "commission" in host:
        casa = "comissao"
    else:
        casa = "outro"
    seg = [p for p in partes.path.split("/") if p]
    limpos = []
    for p in seg:
        limpos.append("{id}" if p.isdigit() or re.match(r"^\d{4}-\d{3,4}$", p) else p)
    return f"{casa}:" + "/".join(limpos[:3]) if limpos else casa


def _stat_endpoint(url, campo, valor=1):
    with _HTTP_LOCK:
        ep = _HTTP_STATS["por_endpoint"].setdefault(
            endpoint_label(url), {"chamadas": 0, "falhas": 0, "tempo_total": 0.0})
        ep[campo] = ep.get(campo, 0) + valor


def http_stats():
    """Métricas de rede da execução (para o painel de monitoramento)."""
    with _HTTP_LOCK:
        return {
            "chamadas": _HTTP_STATS["chamadas"],
            "cache": _HTTP_STATS["cache"],
            "falhas": _HTTP_STATS["falhas"],
            "tempo_total": round(_HTTP_STATS["tempo_total"], 2),
            "por_endpoint": {k: {"chamadas": v["chamadas"], "falhas": v["falhas"],
                                 "tempo_total": round(v["tempo_total"], 2)}
                             for k, v in sorted(_HTTP_STATS["por_endpoint"].items())},
        }


def _http_urllib(url, timeout, as_text=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        bruto = r.read()
    enc = (r.headers.get_content_charset() or "utf-8") if hasattr(r, "headers") else "utf-8"
    if as_text:
        return bruto.decode(enc, errors="replace")
    return json.loads(bruto.decode(enc, errors="replace"))


def _http_curl(url, timeout, as_text=False):
    import subprocess
    out = subprocess.run(
        [_CURL_BIN, "-sS", "-L", "-m", str(timeout),
         "-H", f"Accept: {UA['Accept']}", "-H", f"User-Agent: {UA['User-Agent']}", url],
        capture_output=True, text=True, timeout=timeout + 5)
    if out.returncode != 0:
        raise RuntimeError(f"curl exit {out.returncode}: {(out.stderr or '')[:120]}")
    if as_text:
        return out.stdout
    return json.loads(out.stdout)


def http_get_json(url, timeout=None, retries=None, cache=True):
    """GET → JSON (dict/list). Usa o cache de execução e respeita o orçamento."""
    return _http_get(url, timeout=timeout, retries=retries, cache=cache, as_text=False)


def http_get_text(url, timeout=None, retries=None, cache=True):
    """GET → texto (HTML/RSS). Mesmo orçamento, cache e telemetria do JSON."""
    return _http_get(url, timeout=timeout, retries=retries, cache=cache, as_text=True)


def _http_get(url, timeout=None, retries=None, cache=True, as_text=False):
    timeout = HTTP_TIMEOUT if timeout is None else timeout
    retries = HTTP_RETRIES if retries is None else retries
    if cache:
        with _HTTP_LOCK:
            if url in _HTTP_CACHE:
                _HTTP_STATS["cache"] += 1
                return _HTTP_CACHE[url]
    last_err = None
    for attempt in range(retries):
        BUDGET.checar()
        t0 = time.monotonic()
        try:
            with _HTTP_SEM:
                espera = max(5, min(timeout, BUDGET.restante() - BUDGET.margem))
                if espera <= 0:
                    raise BudgetExceeded("orçamento esgotado durante a espera")
                with _HTTP_LOCK:
                    _HTTP_STATS["chamadas"] += 1
                if _CURL_BIN:
                    payload = _http_curl(url, int(espera), as_text=as_text)
                else:
                    payload = _http_urllib(url, int(espera), as_text=as_text)
            with _HTTP_LOCK:
                _HTTP_STATS["tempo_total"] += time.monotonic() - t0
                if cache:
                    _HTTP_CACHE[url] = payload
            _stat_endpoint(url, "chamadas")
            _stat_endpoint(url, "tempo_total", round(time.monotonic() - t0, 2))
            return payload
        except BudgetExceeded:
            raise
        except Exception as e:  # noqa: BLE001 - rede instável; registra e tenta de novo
            last_err = e
            with _HTTP_LOCK:
                _HTTP_STATS["tempo_total"] += time.monotonic() - t0
                _HTTP_STATS["falhas"] += 1
            _stat_endpoint(url, "falhas")
            if attempt + 1 < retries:
                BUDGET.pausa(2 * (attempt + 1))
    print(f"  [aviso] falha após {retries} tentativas: {url[:110]} ({last_err})", flush=True)
    return None


def polite_pause():
    BUDGET.pausa(0.3)


def relevance(text):
    """Classifica relevância temática: 'forte', 'media', 'infra' ou None.

    A sigla isolada "AI" não conta como sinal forte (falso positivo em inglês:
    "said", "maintain"…). Sinais fracos combinados com contexto técnico valem
    'media'; infraestrutura isolada vira 'infra' (revisão pendente).
    """
    t = norm(text)
    if any(r.search(t) for r in STRONG_RE):
        return "forte"
    medium_hit = any(re.search(p, t) for p in MEDIUM_PATTERNS if p not in INFRA_ONLY)
    if medium_hit:
        return "media"
    if any(r.search(t) for r in INFRA_RE):
        return "infra"
    return None


# ------------------------------------------------------------------ IO base
def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def today_brt():
    return datetime.now(BRT)


def parse_run_date(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:25] if "%z" in fmt else s[:19], fmt)
            return dt.date().isoformat()
        except (ValueError, TypeError):
            continue
    return None


def date_only(dt_str):
    if not dt_str:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(dt_str).strip())
    return m.group(1) if m else None


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


# ------------------------------------------- procedimentos: ids e referências
def proc_ref_de_dataset_id(dataset_id):
    """'ue_2021_0106_cod' → '2021/0106(COD)'. Sem tipo conhecido → com o que houver."""
    m = re.match(r"^ue_(\d{4})_(\d{3,4})(?:_([a-z]{2,4}))?$", dataset_id or "")
    if not m:
        return None
    ano, num, tipo = m.groups()
    return f"{ano}/{num}({(tipo or '').upper()})" if tipo else f"{ano}/{num}"


def dataset_id_de_proc_ref(ref):
    """'2021/0106(COD)' → 'ue_2021_0106_cod' (normalização canônica do dataset)."""
    if not ref:
        return None
    m = RE_PROC_REF.search(ref)
    if not m:
        return None
    ano, num, tipo = m.group(1), m.group(2), m.group(3).lower()
    return f"ue_{ano}_{num}_{tipo}"


def process_id_de_ref(ref):
    """'2021/0106(COD)' → '2021-0106' (id usado na API v2 do Parlamento)."""
    m = RE_PROC_REF.search(ref or "")
    if not m:
        m2 = re.match(r"^(\d{4})-(\d{3,4})$", (ref or "").strip())
        return f"{m2.group(1)}-{m2.group(2)}" if m2 else None
    return f"{m.group(1)}-{m.group(2)}"


# ------------------------------------------------- APIs Parlamento / EUR-Lex
def ep_list_procedimentos(termo=10, limit=100, offset=0):
    """Listagem de procedimentos por termo parlamentar (JSON-LD oficial)."""
    url = (f"{EP_API}/procedures?parliamentary_term={termo}&limit={limit}"
           f"&offset={offset}&format={JSONLD}")
    d = http_get_json(url, retries=2)
    polite_pause()
    if not d:
        return []
    return d.get("data", []) or []


def ep_ficha(process_id):
    """Ficha completa do procedimento na API oficial (eventos, estágios, docs)."""
    url = f"{EP_API}/procedures/{process_id}?format={JSONLD}"
    d = http_get_json(url, retries=2)
    polite_pause()
    if not d:
        return None
    return parse_ep_procedimento(d, proc_id=process_id)


def eurlex_busca(query, ano=None, pagina=1, amount=25):
    """Busca oficial pública do EUR-Lex (HTML server-rendered) → itens."""
    q = urllib.parse.quote(query)
    url = (f"{EURLEX}/search.html?text={q}&scope=EURLEX&type=quick&amount={amount}"
           f"&page={pagina}")
    if ano:
        url += f"&DD_YEAR={ano}"
    html = http_get_text(url, retries=2)
    polite_pause()
    if not html:
        return []
    return parse_eurlex_busca(html, url=url)


def train_fichas(theme_url, limite=60):
    """Listagem de dossiês de um tema do Legislative Train (site oficial)."""
    html = http_get_text(theme_url, retries=2)
    polite_pause()
    if not html:
        return []
    return parse_legislative_train(html, url=theme_url)[:limite]


def train_ficha_html(url):
    html = http_get_text(url, retries=1)
    polite_pause()
    return html


def hys_listagem(pagina=1):
    """Listagem oficial de consultas/calls for evidence (Have Your Say)."""
    html = http_get_text(f"{HYS}?page={pagina}", retries=2)
    polite_pause()
    if not html:
        return []
    return parse_consultas_hys(html, url=HYS, canal=None)


def doceo_url(doc_id):
    """URL oficial do DOCEO para textos adotados/relatórios (A-, TA-, PV-, CRE-).

    Só constrói URL para ids cujo padrão é o esquema estável do DOCEO; outros
    ids (comissões, AD-) ficam sem URL — nada de link estimado.
    """
    if re.match(r"^(TA|A|PV|CRE)-\d-\d{4}-\d{4}(-\w+)*$", doc_id or ""):
        return f"{DOCEO}/{doc_id}_EN.html"
    return None


# ------------------------------------------------------- tipos de mudança
# Tipos de atividade da API v2 do Parlamento → rótulo PT (factual).
EVENTO_TIPO_PT = {
    "REFERRAL": "encaminhamento à comissão",
    "COMMITTEE_TABLING_REPORT": "relatório apresentado na comissão",
    "COMMITTEE_ADOPTING_REPORT": "relatório adotado na comissão",
    "COMMITTEE_TABLING_OPINION": "parecer apresentado na comissão",
    "COMMITTEE_ADOPTING_OPINION": "parecer adotado na comissão",
    "COMMITTEE_APPROVE_PROVISIONAL_AGREEMENT": "acordo provisório aprovado",
    "PLENARY_DEBATE": "debate no plenário",
    "PLENARY_AMEND": "emendas no plenário",
    "PLENARY_AMEND_PROPOSAL": "propostas de emenda no plenário",
    "PLENARY_VOTE": "votação no plenário",
    "PLENARY_VOTE_RESULTS": "resultado de votação no plenário",
    "PLENARY_REFER_COMMITTEE_INTERINSTITUTIONAL_NEGOTIATIONS":
        "abertura de negociações interinstitucionais",
    "TABLING_PLENARY": "inscrição em pauta do plenário",
    "SIGNATURE": "assinatura formal",
    "PUBLICATION_OFFICIAL_JOURNAL": "publicação no Jornal Oficial",
}


def label_evento(tipo):
    if not tipo:
        return "movimentação no procedimento"
    if tipo in EVENTO_TIPO_PT:
        return EVENTO_TIPO_PT[tipo]
    return tipo.replace("_", " ").lower()


def infer_change_type(text):
    """Tipo de mudança (vocabulary dos tipos usados no site) a partir do texto."""
    t = norm(text)
    if "publication no jornal oficial" in t or "jornal oficial" in t \
            or "official journal" in t:
        return "publicação"
    if "assinatura" in t or "signature" in t:
        return "assinatura"
    if "vota" in t or "vote" in t:
        return "votação"
    if "negocia" in t or "interinstitucional" in t or "trilogo" in t:
        return "negociação interinstitucional"
    if "acordo provisorio" in t or "provisional agreement" in t:
        return "acordo provisório"
    if "emenda" in t or "amend" in t:
        return "emenda"
    if "parecer" in t or "opinion" in t:
        return "parecer"
    if "relatorio" in t or "report" in t:
        return "relatório"
    if "debate" in t or "pauta" in t:
        return "pauta do plenário"
    if "encaminhamento" in t or "referral" in t:
        return "encaminhamento"
    return "tramitação"


def situacao_from_evento(ev):
    """Situação factual a partir do último evento oficial da ficha.

    Nunca descreve estágio futuro: só traduz o que a ficha oficial registra.
    """
    tipo = ev.get("tipo") or ""
    data = ev.get("data") or ""
    fase = ev.get("fase")
    sufixo = f" — {data}" + (f" (fase {fase})" if fase else "")
    mapa = {
        "REFERRAL": "Em avaliação na comissão parlamentar responsável",
        "COMMITTEE_TABLING_REPORT": "Relatório em discussão na comissão",
        "COMMITTEE_ADOPTING_REPORT": "Relatório adotado na comissão — aguarda plenário",
        "COMMITTEE_TABLING_OPINION": "Parecer em elaboração na comissão",
        "COMMITTEE_ADOPTING_OPINION": "Parecer adotado na comissão",
        "COMMITTEE_APPROVE_PROVISIONAL_AGREEMENT":
            "Acordo provisório aprovado — aguarda confirmação no plenário",
        "PLENARY_DEBATE": "Debatido no plenário",
        "PLENARY_AMEND": "Emendas em exame no plenário",
        "PLENARY_AMEND_PROPOSAL": "Propostas de emenda em exame no plenário",
        "PLENARY_VOTE": "Votado no plenário",
        "PLENARY_VOTE_RESULTS": "Votado no plenário (resultado registado)",
        "PLENARY_REFER_COMMITTEE_INTERINSTITUTIONAL_NEGOTIATIONS":
            "Negociações interinstitucionais (trílogos) em curso",
        "TABLING_PLENARY": "Inscrito em pauta do plenário",
        "SIGNATURE": "Assinado — aguarda publicação no Jornal Oficial",
        "PUBLICATION_OFFICIAL_JOURNAL": "Publicado no Jornal Oficial da UE",
    }
    base = mapa.get(tipo) or (label_evento(tipo).capitalize() if tipo else
                              "Tramitação em curso")
    return base + sufixo


# ------------------------------------------------------- categorias inferidas
# Palavras-chave (inglês, texto normalizado) → ids das categorias do dataset.
# Os ids seguem data/legislation/categories.json (categorias UE).
CATEGORY_KEYWORDS = [
    (["ai act", "artificial intelligence act", "ai office", "regulatory framework"],
     [1]),
    (["fundamental rights", "non-discrimination", "discriminat"], [2]),
    (["gdpr", "personal data", "data protection", "privacy"], [3]),
    (["liability", "redress", "compensation"], [4]),
    (["prohibited ai", "unacceptable risk", "social scoring", "real-time remote biometric"],
     [5]),
    (["copyright", "text and data mining", "tdm", "creator"], [6]),
    (["worker", "employment", "labour", "employee"], [7]),
    (["education", "school", "research", "universit"], [8]),
    (["health", "medical device", "hospital", "patient"], [9]),
    (["law enforcement", "police", "criminal", "migration", "border"], [10]),
    (["defence", "defense", "military", "security union"], [11]),
    (["justice", "courts", "judicial", "democracy"], [12]),
    (["election", "electoral", "political advertising"], [13]),
    (["deepfake", "synthetic content", "manipulation of content"], [14]),
    (["disinformation", "misinformation", "information integrity"], [15]),
    (["digital services act", "very large online platform", "vlop", "platform liability"],
     [16]),
    (["biometric"], [17]),
    (["facial recognition", "facial image database"], [18]),
    (["public administration", "public service", "government use"], [19]),
    (["financial service", "credit scoring", "insurance", "bank"], [20]),
    (["consumer", "product safety", "product liability"], [21]),
    (["cybersecurity", "cyber resilience", "nis2", "incident"], [22]),
    (["autonomous system", "robot", "drone", "self-driving"], [23]),
    (["transparency obligation", "watermark", "labelling", "labeling", "marking of"],
     [24]),
    (["conformity assessment", "notified body", "audit", "ce marking"], [25]),
    (["high-risk", "high risk", "annex iii", "risk management system"], [26]),
    (["regulatory sandbox", "innovation", "start-up", "startup", "research and development"],
     [27]),
    (["high-performance computing", "supercomput", "data centre", "datacenter",
      "quantum", "cloud infrastructure", "chips"], [28]),
    (["digital sovereignty", "competitiveness", "single market", "open strategic autonomy"],
     [29]),
    (["general-purpose ai", "gpai", "foundation model", "large language model",
      "generative ai", "systemic risk"], [30]),
]


def infer_categories(ementa, titulo=""):
    t = norm(f"{ementa} {titulo}")
    cats = []
    for keywords, ids in CATEGORY_KEYWORDS:
        if any(k in t for k in keywords):
            for i in ids:
                if i not in cats:
                    cats.append(i)
    return sorted(cats)[:6]


# ---------------------------------------------------------------- coletor
class Collector:
    def __init__(self):
        self.now = today_brt()
        self.run_id = "run_" + self.now.strftime("%Y_%m_%d_%H%M")
        self.run_iso = self.now.isoformat(timespec="seconds")
        self.today = self.now.date().isoformat()
        self.changes = []
        self.errors = []
        self.verified = 0
        self.updated = 0
        self.new_props = []
        self.fontes_ok = set()
        self.nao_verificadas = []   # ids não consultados por fim de orçamento
        self.verificadas_ids = set()  # procedimentos distintos consultados (cobertura)
        # saúde por instituição-fonte do motor legislativo
        self.verificadas_inst = {"parlamento": 0, "eurlex": 0}
        self.fases = {}             # fase -> segundos (métricas do painel)
        self._changes_gravadas = 0  # mudanças já persistidas (checkpoint intermediário)
        self._fases_ini = {}
        self._lock = threading.Lock()  # contadores e sets compartilhados entre threads

    # ------------------------------------------------------------- telemetria
    def fase(self, nome):
        """Context manager para medir a duração de cada fase da coleta."""
        coletor = self

        class _Fase:
            def __enter__(self_):
                self_._t0 = time.monotonic()
                return self_

            def __exit__(self_, *exc):
                with coletor._lock:
                    coletor.fases[nome] = round(
                        coletor.fases.get(nome, 0.0) + time.monotonic() - self_._t0, 1)
                return False

        return _Fase()

    def _resumo_execucao(self):
        return {
            "duracao_segundos": int(BUDGET.decorrido()),
            "orcamento_segundos": BUDGET.limite,
            "orcamento_restante_segundos": int(BUDGET.restante()),
            "fases_segundos": dict(sorted(self.fases.items())),
            "http": http_stats(),
        }

    def _bump(self, attr):
        with self._lock:
            setattr(self, attr, getattr(self, attr) + 1)

    def _marca_verificada(self, prop_id, instituicao="parlamento"):
        """Conta a ficha consultada e o dossiê distinto (cobertura ≤ 100%)."""
        with self._lock:
            self.verified += 1
            self.verificadas_ids.add(prop_id)
            self.verificadas_inst[instituicao] = \
                self.verificadas_inst.get(instituicao, 0) + 1

    def _add_fonte(self, fonte):
        with self._lock:
            self.fontes_ok.add(fonte)

    def _add_fontes(self, fontes):
        with self._lock:
            self.fontes_ok.update(fontes)

    def add_change(self, *, data_evento, titulo, descricao, tipo, proposicao,
                   fonte, fonte_url, campo=None, anterior=None, novo=None):
        self.changes.append({
            "data": data_evento or self.today,
            "titulo": titulo,
            "descricao": descricao,
            "tipo": tipo,
            "proposicao": proposicao,
            "fonte_url": fonte_url,
            "campo_alterado": campo,
            "valor_anterior": anterior,
            "valor_novo": novo,
            "data_deteccao": self.today,
            "fonte": fonte,
            "url_oficial": fonte_url,
            "timestamp_execucao": self.run_iso,
            "id_execucao": self.run_id,
        })

    # ------------------------------------------ procedimentos monitorados
    def _process_id_de_prop(self, p):
        """Id do processo (API v2) do registro; nunca inventado."""
        api = p.get("api_ep") or {}
        if api.get("process_id"):
            return api["process_id"]
        for u in [p.get("url_oficial")] + [d.get("url") for d in p.get("documentos", [])]:
            m = re.search(r"/procedures/(\d{4}-\d{3,4})", u or "")
            if m:
                return m.group(1)
        # tenta pela referência normalizada no próprio id do dataset
        m = re.match(r"^ue_(\d{4})_(\d{3,4})", p.get("id") or "")
        if m:
            return f"{m.group(1)}-{m.group(2)}"
        return None

    def update_procedure(self, p, last_run):
        """Atualiza um procedimento monitorado a partir da ficha oficial (API v2).

        Devolve True quando a ficha foi consultada com sucesso. Detecta:
        novos eventos (→ mudanças + timeline), mudança de situação, textos
        adotados novos (documentos DOCEO) e o snapshot api_ep.
        """
        pid = self._process_id_de_prop(p)
        if not pid:
            self.errors.append(f"{p['id']}: sem identificador de procedimento oficial")
            return False
        ficha = ep_ficha(pid)
        if not ficha:
            self.errors.append(f"{p['id']}: ficha indisponível na API v2 do Parlamento")
            return False
        self._add_fontes(FONTES_PARLAMENTO[:2])
        self._marca_verificada(p["id"], "parlamento")
        fonte_ficha = f"{EP_API}/procedures/{pid}?format={JSONLD}"
        changed = False
        api = p.setdefault("api_ep", {})
        api.update({
            "process_id": ficha.get("process_id") or pid,
            "process_type": ficha.get("process_type"),
            "label": ficha.get("label"),
            "verificado_em": self.run_iso,
            "eventos_total": len(ficha.get("eventos", [])),
        })

        eventos = ficha.get("eventos", [])
        # Título oficial (campo 'title' quando existir; nunca inventado)
        titulo_oficial = (ficha.get("tema") or "").strip()
        if (titulo_oficial and len(titulo_oficial) > 12
                and not titulo_oficial.startswith("European Parliament procedure")
                and not (p.get("revisao_pendente") is False and p.get("titulo"))):
            if norm(p.get("titulo", "")) != norm(titulo_oficial):
                anterior = p.get("titulo")
                p["titulo"] = titulo_oficial[:300]
                if anterior:
                    self.add_change(
                        data_evento=self.today,
                        titulo=f"{ficha.get('label') or pid}: título oficial atualizado",
                        descricao=f"Título passou de “{(anterior or '')[:200]}” para "
                                  f"“{titulo_oficial[:200]}”.",
                        tipo="atualização cadastral", proposicao=p["id"],
                        fonte="Parlamento Europeu — Open Data Portal v2",
                        fonte_url=fonte_ficha, campo="titulo",
                        anterior=anterior, novo=titulo_oficial[:300])
                changed = True

        # Documentos oficiais referenciados pelos eventos (DOCEO p/ A-/TA-)
        docs_registrados = {d.get("url") for d in p.get("documentos", [])}
        novos_docs = []
        for ev in eventos:
            for doc_id in ev.get("docs", []):
                u = doceo_url(doc_id)
                if u and u not in docs_registrados:
                    rotulo = ("Texto adotado pelo Plenário" if doc_id.startswith("TA")
                              else "Relatório da comissão" if doc_id.startswith("A-")
                              else "Documento oficial do procedimento")
                    novos_docs.append({"titulo": rotulo, "id_doc": doc_id, "url": u})
                    docs_registrados.add(u)
        if novos_docs:
            p["documentos"] = (p.get("documentos") or []) + novos_docs
            changed = True

        # Timeline: eventos oficiais ainda não registrados (dedupe por data+tipo+id)
        tl_chaves = {(t.get("data"), norm(t.get("evento", ""))[:60], t.get("id_atividade"))
                     for t in p.get("timeline", [])}
        novos_eventos = []
        for ev in eventos:
            chave = (ev.get("data"), norm(label_evento(ev.get("tipo")))[:60],
                     ev.get("activity_id"))
            if chave in tl_chaves:
                continue
            tl_chaves.add(chave)
            novos_eventos.append(ev)
        if novos_eventos:
            for ev in novos_eventos:
                p.setdefault("timeline", []).append({
                    "data": ev.get("data"),
                    "evento": (label_evento(ev.get("tipo")).capitalize()
                               + (f" (fase {ev.get('fase')})" if ev.get("fase") else "")),
                    "fonte": fonte_ficha,
                    "id_atividade": ev.get("activity_id"),
                })
            p["timeline"] = sorted(
                p.get("timeline", []),
                key=lambda t: (t.get("data") or "9999-99-99", t.get("id_atividade") or ""))
            changed = True

        # Último evento → mudança + situação + última movimentação
        if eventos:
            ultimo = eventos[-1]
            udate = ultimo.get("data")
            utipo = label_evento(ultimo.get("tipo"))
            udato_doc = next((doceo_url(d) for d in ultimo.get("docs", [])
                              if doceo_url(d)), fonte_ficha)
            api["ultimo_evento"] = {"data": udate, "tipo": ultimo.get("tipo"),
                                    "fase": ultimo.get("fase"),
                                    "activity_id": ultimo.get("activity_id")}
            stored = p.get("ultima_movimentacao") or {}
            mudou = (udate and
                     (stored.get("data") != udate
                      or norm(stored.get("descricao", ""))[:80] != norm(utipo)[:80]))
            if mudou:
                nova = udate > (last_run or "0000-00-00") if udate else False
                self.add_change(
                    data_evento=udate or self.today,
                    titulo=(f"{p['tipo'] and (str(p.get('numero')) + '/' + str(p.get('ano'))) or ''}"
                            f"{(' ' + p['tipo']) if p.get('tipo') else ''} procedimento "
                            f"{api.get('label') or pid}: {utipo}"
                            + ("" if nova else " (registro incorporado)")).strip(),
                    descricao=(f"Em {udate}, ficha oficial do procedimento "
                               f"({ficha.get('label') or pid}): {utipo}"
                               + (f", fase {ultimo.get('fase')}" if ultimo.get("fase") else "")
                               + ("" if nova else " — evento já constava na ficha oficial "
                                  "antes desta execução e foi incorporado ao dataset agora.")),
                    tipo=infer_change_type(utipo), proposicao=p["id"],
                    fonte="Parlamento Europeu — Open Data Portal v2 (eventos do procedimento)",
                    fonte_url=udato_doc, campo="ultima_movimentacao",
                    anterior=f"{stored.get('data', '?')} — {(stored.get('descricao') or '')[:200]}",
                    novo=f"{udate} — {utipo}")
                p["ultima_movimentacao"] = {"data": udate, "descricao": utipo}
                nova_sit = situacao_from_evento(ultimo)
                if nova_sit and nova_sit != p.get("situacao"):
                    if p.get("situacao"):
                        self.add_change(
                            data_evento=udate or self.today,
                            titulo=f"{api.get('label') or pid}: situação atualizada",
                            descricao=f"Situação passou de “{(p.get('situacao') or '')[:200]}” "
                                      f"para “{nova_sit[:200]}”.",
                            tipo=infer_change_type(utipo), proposicao=p["id"],
                            fonte="Parlamento Europeu — Open Data Portal v2 (eventos do procedimento)",
                            fonte_url=udato_doc, campo="situacao",
                            anterior=p.get("situacao"), novo=nova_sit)
                    p["situacao"] = nova_sit
                # documentos novos citados na própria mudança
                if novos_docs:
                    self.add_change(
                        data_evento=udate or self.today,
                        titulo=f"{api.get('label') or pid}: novo documento oficial "
                               f"({novos_docs[0]['titulo']})",
                        descricao=("Documento referenciado pela ficha oficial do "
                                   "procedimento: " + "; ".join(d["id_doc"] or ""
                                                                for d in novos_docs[:4])),
                        tipo="documento", proposicao=p["id"],
                        fonte="Parlamento Europeu — Open Data Portal v2 (eventos do procedimento)",
                        fonte_url=fonte_ficha)
                changed = True
        if changed:
            self._bump("updated")
        return True

    # ------------------------------------------------------- descoberta
    def discover_procedures(self, known_refs, last_run):
        """Descobre procedimentos novos nas fontes oficiais.

        Estratégia (ordem de preferência das vias oficiais):
          1) EUR-Lex — busca por tema nos anos corrente/anterior; quando o
             resultado cita o número do arquivo interinstitucional, é
             evidência objetiva de um procedimento (legislativo ou não).
          2) Legislative Train — fichas do tema digital; cada ficha cita o
             arquivo interinstitucional do dossiê.
        Devolve [(ref, rel, via, titulo_hint)].
        """
        found = []
        refs = set(known_refs)

        def _add(ref, rel, via, titulo_hint=None):
            if not ref:
                return
            ref = ref.upper()
            if ref in refs:
                return
            refs.add(ref)
            found.append((ref, rel, via, titulo_hint))

        # 1) EUR-Lex (temas × anos, com teto de orçamento)
        n_buscas = 0
        ano_atual = self.now.year
        for kw in KEYWORDS_DESCOBERTA[:5]:
            if BUDGET.expirado(120):
                break
            for ano in (ano_atual, ano_atual - 1):
                if BUDGET.expirado(120):
                    break
                hits = eurlex_busca(f'"{kw}"', ano=ano)[:25]
                n_buscas += 1
                for item in hits:
                    if BUDGET.expirado(120):
                        break
                    texto = f"{item.get('titulo', '')} {item.get('descricao', '')}"
                    rel = relevance(texto)
                    if not rel:
                        continue
                    m = RE_PROC_REF.search(texto)
                    if not m:
                        continue
                    ref = f"{m.group(1)}/{m.group(2)}({m.group(3)})"
                    _add(ref, rel, f"eurlex:{kw}:{ano}", item.get("titulo"))
        if n_buscas:
            # consultou a busca oficial (mesmo sem candidato inédito): conta
            # como evidência de saúde da instituição — nunca subnotificar.
            self._add_fonte(FONTES_EURLEX[1])

        # 2) Legislative Train (fichas com referência interinstitucional)
        n_train = 0
        for theme_url in TRAIN_THEMES:
            if BUDGET.expirado(120) or n_train >= TRAIN_MAX_PAGINAS:
                break
            for ficha in train_fichas(theme_url, limite=60):
                if BUDGET.expirado(120) or n_train >= TRAIN_MAX_PAGINAS:
                    break
                if not relevance(ficha.get("titulo", "")):
                    continue
                html = train_ficha_html(ficha["link"])
                if not html:
                    continue
                n_train += 1
                for m in RE_PROC_REF.finditer(html[:200000]):
                    ref = f"{m.group(1)}/{m.group(2)}({m.group(3)})"
                    _add(ref, "forte", f"train:{ficha.get('titulo', '')[:40]}",
                         ficha.get("titulo"))
        if n_train:
            self._add_fonte(FONTES_PARLAMENTO[2])
        return found

    def build_new_procedure_record(self, cand):
        """Ficha completa do procedimento novo a partir da fonte oficial.

        cand = (ref, rel, via, titulo_hint). A ficha vem da API v2 do
        Parlamento; o título oficial vem da ficha ou, em último caso, do
        EUR-Lex (busca pela referência). Nunca do nada.
        """
        ref, rel, via, titulo_hint = cand
        pid = process_id_de_ref(ref)
        label = RE_PROC_REF.search(ref).group(3).upper() if RE_PROC_REF.search(ref) else ""
        ficha = ep_ficha(pid) if pid else None
        fonte_ficha = f"{EP_API}/procedures/{pid}?format={JSONLD}" if pid else None
        eventos = (ficha or {}).get("eventos", []) or []

        # Título oficial: ficha do Parlamento → EUR-Lex (busca pela referência)
        titulo = (ficha or {}).get("tema") or ""
        if not titulo or len(titulo) < 12 or titulo.startswith("European Parliament procedure"):
            titulo = None
            if not BUDGET.expirado(120):
                hits = eurlex_busca(ref, pagina=1)
                for h in hits:
                    if h.get("titulo") and len(h["titulo"]) > 12:
                        titulo = h["titulo"][:300]
                        break
        sem_titulo = not titulo

        tipo = label or "COD"
        mref = RE_PROC_REF.search(ref)
        ano = int(mref.group(1)) if mref else None
        numero = int(mref.group(2)) if mref else None
        origem = ("Comissão Europeia" if tipo in (TIPOS_LEGISLATIVOS | {"REG", "DEC", "BUA"})
                  else "Parlamento Europeu")

        url_oficial = fonte_ficha or ""
        docs = [{"titulo": "Ficha do procedimento — Open Data Portal do Parlamento",
                 "url": url_oficial}]
        vistos = {url_oficial}
        for ev in eventos:
            for doc_id in ev.get("docs", []):
                u = doceo_url(doc_id)
                if u and u not in vistos:
                    vistos.add(u)
                    docs.append({
                        "titulo": "Texto adotado pelo Plenário" if doc_id.startswith("TA")
                        else "Relatório da comissão" if doc_id.startswith("A-")
                        else "Documento oficial do procedimento",
                        "url": u})
        timeline = []
        ultima = None
        for ev in eventos:
            ev_label = label_evento(ev.get("tipo")).capitalize()
            if ev.get("fase"):
                ev_label += f" (fase {ev['fase']})"
            timeline.append({"data": ev.get("data"), "evento": ev_label,
                             "fonte": fonte_ficha,
                             "id_atividade": ev.get("activity_id")})
            ultima = ev
        timeline = sorted(timeline, key=lambda t: (t.get("data") or "9999-99-99",
                                                   t.get("id_atividade") or ""))
        situacao = situacao_from_evento(ultima) if ultima else (
            "Situação não confirmada nesta execução — ver ficha oficial")
        ds_id = dataset_id_de_proc_ref(ref)
        rec = {
            "id": ds_id,
            "tipo": tipo,
            "numero": numero,
            "ano": ano,
            "titulo": (titulo or f"Procedimento {ref}")[:300],
            "ementa": (titulo or f"Procedimento interinstitucional {ref} "
                       f"({TIPO_PROC_PT.get(tipo, tipo)}). "
                       "Descrição oficial pendente de confirmação.")[:1200],
            "casa_origem": origem,
            "casa_atual": "Parlamento Europeu",
            "url_oficial": url_oficial,
            "autor": ({"nome": "Comissão Europeia"} if origem == "Comissão Europeia"
                      else {"nome": "Parlamento Europeu"}),
            "data_apresentacao": (eventos[0].get("data") if eventos else None),
            "situacao": situacao,
            "ultima_movimentacao": ({"data": ultima.get("data"),
                                     "descricao": label_evento(ultima.get("tipo"))}
                                    if ultima else {"data": None,
                                                    "descricao": "Sem eventos na ficha"}),
            "resumo": (titulo or f"Procedimento {ref}")[:400],
            "categorias": infer_categories(titulo or ""),
            "impacto": {},
            "documentos": docs,
            "timeline": timeline,
            "origem": "descoberta_automatica",
            "fonte_descoberta": via,
            "revisao_pendente": True,
            "api_ep": {
                "process_id": pid,
                "label": ref,
                "process_type": tipo,
                "verificado_em": self.run_iso,
                "eventos_total": len(eventos),
                "titulo_pendente": sem_titulo,
            },
        }
        rec["impacto"] = compute_impact_score(rec)
        return rec

    # ------------------------------------------------------------- eventos
    def update_events(self, events):
        """Agenda futura oficial: consultas da Comissão (Have Your Say).

        Os endpoints de reuniões do Parlamento na API v2 retornam corpo vazio
        (limitação documentada); o período de feedback oficial das consultas
        é a agenda futura verificável disponível.
        """
        found = []
        for pagina in (1, 2):
            if BUDGET.expirado(60):
                break
            found.extend(hys_listagem(pagina))
        futuros = []
        for it in found:
            fim = it.get("data")
            if not fim or fim <= self.today:
                continue
            texto = f"{it.get('titulo', '')} {it.get('descricao', '')}"
            if relevance(texto):
                futuros.append(it)
        self._add_fonte(FONTES_HYS[0])
        existing_ids = {e.get("id") for e in events.get("eventos", [])}
        added = 0
        for it in futuros:
            eid = f"evt_hys_{it.get('consulta_id') or abs(hash(it.get('link', '')))}"
            if eid in existing_ids:
                continue
            delta = (datetime.strptime(it["data"], "%Y-%m-%d").date()
                     - self.now.date()).days
            janela = ("proximos_7_dias" if delta <= 7
                      else "proximos_30_dias" if delta <= 30 else "sem_data_confirmada")
            events["eventos"].append({
                "id": eid,
                "titulo": (it.get("titulo") or "Consulta pública")[:220],
                "casa": "Comissão Europeia",
                "tipo": (it.get("estagio") or "consulta pública"),
                "data_inicio": (it.get("periodo_feedback") or "").split(" → ")[0] or None,
                "data_fim": it.get("data"),
                "hora": None,
                "local": "Have Your Say (online)",
                "tema": (it.get("descricao") or "")[:500],
                "relacao_ia": ("Consultas com período de feedback aberto, "
                               "relacionadas a IA/dados por filtro temático "
                               "(revisão pendente)."),
                "janela": janela,
                "fonte_titulo": "Comissão Europeia — Have Your Say",
                "fonte_url": it.get("link"),
                "origem": "descoberta_automatica",
                "verificacao": {
                    "fonte_consultada": FONTES_HYS[0],
                    "url": it.get("link"),
                    "como_verificar": ("Página oficial da consulta no portal "
                                       "Have Your Say lista o período de "
                                       "feedback e o tipo de ato."),
                    "data_verificacao": self.today,
                },
            })
            added += 1
        events["verificacao"] = {
            "data": self.today,
            "fontes_consultadas": [{
                "titulo": FONTES_HYS[0],
                "url": HYS,
            }],
            "resultado": (f"{added} nova(s) consulta(s) futura(s) relacionada(s) a "
                          f"IA/dados incorporada(s) à agenda; {len(futuros)} "
                          f"consulta(s) com prazo futuro no período analisado."
                          if futuros else
                          "Nenhuma consulta futura relacionada a IA/dados no "
                          "portal Have Your Say neste período."),
        }
        return added

    # -------------------------------------------------------------- métricas
    def _prioridade(self, p):
        """Ordem de verificação: maior score primeiro; em empate, o mais antigo.

        Garante que, se o orçamento acabar, o que ficou de fora são os dossiês
        de menor impacto — e que eles sejam os primeiros da execução seguinte.
        """
        score = (p.get("impacto") or {}).get("score") or 0
        dias = -1
        d = date_only((p.get("api_ep") or {}).get("verificado_em"))
        if d:
            dias = max(dias, (self.now.date() - datetime.strptime(d, "%Y-%m-%d").date()).days)
        return (-score, -dias)

    @staticmethod
    def _prioridade_candidato(cand):
        """Relevância temática > tipo legislativo > mais recente.

        "Mais recente" = ano do arquivo interinstitucional e, em empate, o
        número maior (uma fatia `ref[2:12]` quebrada como data ISO e virava
        ordinal 0 para todos — recência deixava de desempatar).
        """
        ref, rel, _via, _hint = cand
        ordem_rel = {"forte": 0, "media": 1, "infra": 2}.get(rel, 3)
        m = RE_PROC_REF.search(ref)
        tipo = m.group(3).upper() if m else ""
        legislativo = 0 if tipo in TIPOS_LEGISLATIVOS else 1
        ano = int(m.group(1)) if m else 0
        numero = int(m.group(2)) if m else 0
        return (ordem_rel, legislativo, -ano, -numero)

    def _snapshot_dataset(self, props_all, laws_f, ev_f, up_f):
        """Fotografia do banco ao fim da execução (série histórica do painel)."""
        por_situacao = {}
        for p in props_all:
            t = norm(p.get("situacao") or "")
            if "publicado no jornal oficial" in t:
                g = "publicado_jo"
            elif "assinado" in t:
                g = "assinado"
            elif "negocia" in t or "trilogo" in t:
                g = "negociacao"
            elif "plenário" in t or "comissão" in t or "comiss" in t:
                g = "em_avaliacao"
            else:
                g = "em_tramitacao"
            por_situacao[g] = por_situacao.get(g, 0) + 1
        return {
            "proposicoes_total": len(props_all),
            "por_situacao": dict(sorted(por_situacao.items())),
            "normas_total": len(laws_f.get("normas", [])),
            "eventos_total": len(ev_f.get("eventos", [])),
            "mudancas_registradas": len(up_f.get("mudancas", []))
        + len(self.changes[self._changes_gravadas:]),
        }

    @staticmethod
    def _status_inst(verificadas, falhas):
        """ok · parcial · falha por instituição a partir de evidência de consulta.

        Sem nenhuma ficha consultada, a instituição conta como **falha** —
        nunca como monitorada.
        """
        if not verificadas:
            return "falha"
        return "parcial" if falhas else "ok"

    def _saude_instituicoes(self):
        """Saúde das instituições do motor legislativo (estrutura das fontes)."""
        stats = http_stats()
        por_ep = stats.get("por_endpoint") or {}
        saude = {}
        for inst, host, rotulo, prefixo in (
                ("parlamento", "data.europarl.europa.eu",
                 "Parlamento Europeu — Open Data Portal v2 (motor legislativo)",
                 "parlamento"),
                ("eurlex_motor", "eur-lex.europa.eu",
                 "EUR-Lex — busca oficial (motor legislativo)", "eurlex")):
            chamadas = sum(v.get("chamadas", 0) for k, v in por_ep.items()
                           if k.startswith(prefixo))
            falhas = sum(v.get("falhas", 0) for k, v in por_ep.items()
                         if k.startswith(prefixo))
            if inst == "parlamento":
                # dossiês distintos verificados via ficha da API v2
                verificadas = self.verificadas_inst.get("parlamento", 0)
            else:
                # cada busca oficial executada é uma consulta ao EUR-Lex
                verificadas = chamadas
            erros_inst = [e for e in self.errors if e.startswith(inst)]
            status_inst = self._status_inst(verificadas, falhas)
            saude[inst] = {
                "nome": rotulo,
                "status": status_inst,
                "ultima_tentativa": self.run_iso,
                "ultima_execucao_ok": self.run_iso if status_inst == "ok" else None,
                "itens_consultados": verificadas,
                "novidades": len([p for p in self.new_props
                                  if str(p.get("id", "")).startswith("ue_")])
                if inst == "parlamento" else 0,
                "erros": len(erros_inst),
                "chamadas_http": chamadas,
                "falhas_http": falhas,
                "endpoints": [f"https://{host}/"],
                "canais_ok": [f"{inst}:{k.split(':', 1)[-1]}" for k, v in por_ep.items()
                              if k.startswith(prefixo) and v.get("chamadas")
                              and not v.get("falhas")][:6],
                "canais_falhos": [f"{inst}:{k.split(':', 1)[-1]}" for k, v in por_ep.items()
                                  if k.startswith(prefixo) and v.get("falhas")][:6],
                "erro_detalhe": ("; ".join(erros_inst[:3]) or None) if falhas else None,
            }
        # última execução bem-sucedida vem do histórico (nunca estimada)
        anteriores = (load("updates.json").get("execucoes") or [])[1:]
        for inst, dados in saude.items():
            if dados["status"] == "ok":
                continue
            dados["ultima_execucao_ok"] = next(
                ((ex.get("fontes_monitoradas") or {}).get(inst, {}).get("ultima_tentativa")
                 or ex.get("fim") or ex.get("data_hora")
                 for ex in anteriores
                 if ((ex.get("fontes_monitoradas") or {}).get(inst) or {}).get("status") == "ok"),
                None)
        return saude

    def _atualizar_registro(self, rec, n_ev=0):
        rec.update({
            "resumo": (f"Verificação automática: {self.verified} fichas consultadas, "
                       f"{self.updated} procedimentos atualizados, {len(self.new_props)} novos, "
                       f"{len(self.changes)} mudanças detectadas, {n_ev} eventos adicionados."),
            "procedimentos_verificados": self.verified,
            "procedimentos_atualizados": self.updated,
            "novos_procedimentos": len(self.new_props),
            # aliases de compatibilidade com camadas auxiliares existentes
            "proposicoes_verificadas": self.verified,
            "proposicoes_atualizadas": self.updated,
            "novas_proposicoes": len(self.new_props),
            "novas_leis_regulamentos": 0,
            "mudancas_detectadas": len(self.changes),
            "eventos_adicionados": n_ev,
            "fontes_consultadas": sorted(self.fontes_ok),
            "erros": self.errors[:50],
            "sugestoes_curadoria": rec.get("sugestoes_curadoria", []),
            "observacao": ("Nada foi inventado: todos os registros novos ou alterados citam "
                           "a URL oficial. Registros automáticos aguardam curadoria editorial."
                           + (f" Coleta encerrada pelo orçamento de tempo: "
                              f"{len(self.nao_verificadas)} procedimento(s) ficaram para a "
                              f"próxima execução (prioridade por score)."
                              if self.nao_verificadas else "")),
        })
        rec.update(self._resumo_execucao())
        return rec

    def _gravar(self, props_f, up_f, ev_f, laws_f, tl_f, pm_f, props, exec_record, status,
                atos_f=None):
        """Grava o dataset no disco (chamado também no checkpoint intermediário)."""
        props_all = props + self.new_props
        exec_record["status"] = status
        exec_record.setdefault("data_hora", self.run_iso)
        exec_record["fim"] = today_brt().isoformat(timespec="seconds")
        exec_record["procedimentos_monitorados"] = len(props_all)
        exec_record["procedimentos_pendentes"] = len(self.nao_verificadas)
        exec_record["procedimentos_distintos_verificados"] = len(self.verificadas_ids)
        # aliases de compatibilidade
        exec_record["proposicoes_monitoradas"] = len(props_all)
        exec_record["proposicoes_pendentes"] = len(self.nao_verificadas)
        # cobertura = dossiês distintos verificados / monitorados
        exec_record["cobertura_pct"] = min(
            100.0, round(100.0 * len(self.verificadas_ids) / max(1, len(props_all)), 1))
        exec_record["snapshot_dataset"] = self._snapshot_dataset(props_all, laws_f, ev_f, up_f)
        exec_record.update(self._resumo_execucao())

        props_f["proposicoes"] = props_all
        props_f["meta"]["execucao"] = self.today
        # só as mudanças ainda não gravadas (a execução pode gravar em 2 momentos)
        up_f["mudancas"] = up_f.get("mudancas", []) + self.changes[self._changes_gravadas:]
        self._changes_gravadas = len(self.changes)
        anteriores = up_f.get("execucoes", [])
        if anteriores and anteriores[0].get("id") == exec_record["id"]:
            anteriores[0] = exec_record
        else:
            anteriores = [exec_record] + anteriores
        up_f["execucoes"] = anteriores
        up_f["meta"]["execucao"] = self.today
        ev_f["meta"]["execucao"] = self.today
        laws_f["meta"]["execucao"] = self.today
        tl_f["meta"]["execucao"] = self.today
        pm_f["meta"]["execucao"] = self.today
        save("propositions.json", props_f)
        save("updates.json", up_f)
        save("events.json", ev_f)
        save("laws.json", laws_f)
        save("timeline.json", tl_f)
        save("parliamentarians.json", pm_f)
        if atos_f is not None:
            save("atos.json", atos_f)
        return exec_record

    # ------------------------------------------------------------------- run
    def run(self, dry_run=False):
        props_f = load("propositions.json")
        laws_f = load("laws.json")
        tl_f = load("timeline.json")
        pm_f = load("parliamentarians.json")
        ev_f = load("events.json")
        up_f = load("updates.json")

        props = props_f["proposicoes"]
        last_run = None
        if up_f.get("execucoes"):
            last_run = parse_run_date(up_f["execucoes"][0].get("data_hora", ""))
        print(f"Estado anterior: {len(props)} procedimentos · última execução: {last_run} · "
              f"orçamento: {BUDGET.limite // 60} min · novas/execução: {MAX_NOVAS} · "
              f"workers: {WORKERS} (HTTP ≤ {HTTP_CONCORRENCIA})", flush=True)

        known_keys = {p["id"] for p in props}

        exec_record = {
            "id": self.run_id,
            "data_hora": self.run_iso,
            "tipo": "atualizacao",
            "status": "em_andamento",
            "motor": {"orcamento_segundos": BUDGET.limite, "max_novas": MAX_NOVAS,
                      "workers": WORKERS, "http_concorrencia": HTTP_CONCORRENCIA},
            "procedimentos_monitorados": len(props),
            "sugestoes_curadoria": [],
        }
        self._atualizar_registro(exec_record)

        # 1) Atualizar procedimentos monitorados (paralelo, I/O-bound; cada thread
        #    toca apenas o seu dict de procedimento + estruturas com lock).
        #    A fila é ordenada por prioridade: se o orçamento acabar, o que fica
        #    pendente são os dossiês de menor impacto.
        fila = sorted(props, key=self._prioridade)
        if MAX_PROPS and len(fila) > MAX_PROPS:
            self.nao_verificadas = [p["id"] for p in fila[MAX_PROPS:]]
            fila = fila[:MAX_PROPS]
        print(f"Consultando fichas oficiais de {len(fila)} procedimentos monitorados...",
              flush=True)

        def _update_one(p):
            try:
                ok = self.update_procedure(p, last_run)
                if not ok:
                    with self._lock:
                        if not any(e.startswith(p["id"]) for e in self.errors):
                            self.errors.append(
                                f"{p['id']}: não atualizado pela API v2 do Parlamento")
            except BudgetExceeded:
                with self._lock:
                    self.nao_verificadas.append(p["id"])
            except Exception as e:  # noqa: BLE001 - um dossiê não derruba a execução
                with self._lock:
                    self.errors.append(f"{p['id']}: erro inesperado ({e})")
            return p["id"]

        with self.fase("atualizacao_procedimentos"):
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futures = {pool.submit(_update_one, p): p for p in fila}
                for i, fut in enumerate(as_completed(futures), 1):
                    fut.result()
                    if i % 25 == 0 or i == len(fila):
                        print(f"  [{i}/{len(fila)}] verificadas · {int(BUDGET.decorrido())}s "
                              f"decorridos · {int(BUDGET.restante())}s restantes", flush=True)
        # Ordem determinística das mudanças (mais recentes primeiro)
        self.changes.sort(key=lambda c: (c.get("data", ""), c.get("titulo", "")), reverse=True)
        print(f"Fase 1 concluída em {self.fases.get('atualizacao_procedimentos', 0)}s · "
              f"{self.verified} verificadas · {int(BUDGET.restante())}s de orçamento restantes",
              flush=True)

        # Checkpoint: grava o resultado da fase 1 antes da descoberta. Se o job
        # for interrompido por qualquer motivo, a verificação já feita não se perde.
        if not dry_run:
            self._atualizar_registro(exec_record)
            self._gravar(props_f, up_f, ev_f, laws_f, tl_f, pm_f, props, exec_record,
                         status="em_andamento")

        # 2) Descobrir novos procedimentos (com teto por execução: o excedente
        #    fica para a próxima, sempre priorizando relevância e recência).
        candidatos_total, adiados = 0, 0
        if BUDGET.expirado(120):
            print("Orçamento insuficiente para a descoberta — etapa adiada.", flush=True)
        else:
            print("Descobrindo novos procedimentos (EUR-Lex + Legislative Train)...",
                  flush=True)
            with self.fase("descoberta_procedimentos"):
                try:
                    cands = self.discover_procedures(known_keys, last_run)
                    cands.sort(key=self._prioridade_candidato)
                    candidatos_total = len(cands)
                    uniq, seen = [], set()
                    for c in cands:
                        ds_id = dataset_id_de_proc_ref(c[0])
                        if ds_id in seen or ds_id in known_keys:
                            continue
                        seen.add(ds_id)
                        uniq.append(c)
                    adiados = max(0, len(uniq) - MAX_NOVAS)
                    uniq = uniq[:MAX_NOVAS]
                    print(f"  {len(uniq)} candidatos a detalhar"
                          + (f" (+{adiados} adiados para a próxima execução)"
                             if adiados else ""), flush=True)

                    def _build_proc(cand):
                        try:
                            return self.build_new_procedure_record(cand)
                        except BudgetExceeded:
                            return None
                        except Exception as e:  # noqa: BLE001
                            with self._lock:
                                self.errors.append(f"novo procedimento {cand[0]}: {e}")
                            return None

                    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                        for i, rec in enumerate(pool.map(_build_proc, uniq), 1):
                            if rec is None:
                                continue
                            if any(x["id"] == rec["id"] for x in self.new_props):
                                continue
                            self.new_props.append(rec)
                            self.add_change(
                                data_evento=rec.get("data_apresentacao") or self.today,
                                titulo=f"Novo procedimento monitorado: {rec['api_ep'].get('label')}",
                                descricao=f"{rec['ementa'][:400]} (Registro automático a "
                                          f"partir de fontes oficiais; aguardando curadoria.)",
                                tipo="novo procedimento", proposicao=rec["id"],
                                fonte="Parlamento Europeu — Open Data Portal v2",
                                fonte_url=rec["url_oficial"])
                            if i % 10 == 0:
                                print(f"  ...{i}/{len(uniq)} detalhados", flush=True)
                except BudgetExceeded:
                    print("  orçamento esgotado durante a descoberta", flush=True)
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"descoberta: {e}")

        # 3) Agenda futura (consultas oficiais com prazo)
        n_ev = 0
        if BUDGET.expirado(60):
            print("Orçamento insuficiente para a agenda — etapa adiada.", flush=True)
        else:
            print("Atualizando agenda de consultas (Have Your Say)...", flush=True)
            with self.fase("agenda_consultas"):
                try:
                    n_ev = self.update_events(ev_f)
                except BudgetExceeded:
                    print("  orçamento esgotado na agenda de consultas", flush=True)
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"eventos: {e}")

        # 3.5) Fontes regulatórias multiórgão (AI Office, EUR-Lex/JO, Conselho,
        #      Comissão, Parlamento, EDPB, EDPS). Cada uma roda em subprocesso
        #      com timeout próprio: uma fonte travada/bloqueada não impede as
        #      demais nem o build do site.
        resumo_fontes = None
        atos_f = load("atos.json") if os.path.exists(os.path.join(DATA, "atos.json")) else None
        if atos_f is None:
            import update_sources_eu as _us
            atos_f = _us._atos_vazios()
        if os.environ.get("MONITOR_SEM_FONTES"):
            print("Coleta multiórgão desativada por MONITOR_SEM_FONTES.", flush=True)
        elif BUDGET.expirado(90):
            print("Orçamento insuficiente para as fontes multiórgão — etapa adiada.",
                  flush=True)
            exec_record["fontes_multiorgao_adiadas"] = True
        else:
            print("Coletando fontes regulatórias (AI Office, EUR-Lex, Conselho, "
                  "Comissão, Parlamento, EDPB, EDPS)...", flush=True)
            with self.fase("fontes_multiorgao"):
                try:
                    import update_sources_eu as _us
                    timeout_fonte = int(os.environ.get("MONITOR_FONTES_TIMEOUT_S", "") or 150)
                    # teto total: nunca consome o orçamento que falta para build/commit
                    limite_total = max(60, int(BUDGET.restante() - BUDGET.margem - 60))
                    resultados = _us.executar_todas(timeout_s=timeout_fonte,
                                                    limite_total_s=limite_total)
                    exec_info = {"id": self.run_id, "timestamp": self.run_iso,
                                 "data": self.today}
                    resumo_fontes = _us.mesclar(atos_f, up_f, resultados, exec_info,
                                                execucoes_anteriores=up_f.get("execucoes"))
                    if not dry_run:
                        n_mud = _us.registrar_mudancas(up_f, resumo_fontes["mudancas"],
                                                       exec_info)
                        print(f"  · {n_mud} mudança(s) registradas das fontes multiórgão",
                              flush=True)
                except BudgetExceeded:
                    print("  orçamento esgotado durante as fontes multiórgão", flush=True)
                except Exception as e:  # noqa: BLE001 — não derruba a execução legislativa
                    self.errors.append(f"fontes multiórgão: {e}")
                    print(f"  [erro] fontes multiórgão: {e}", flush=True)

        # 4) Checagem de publicação no JO (sugestão, sem auto-criar norma)
        sugestoes = []
        normas_conhecidas = {norm(n.get("nome", "")) for n in laws_f.get("normas", [])}
        for p in props + self.new_props:
            s = norm(p.get("situacao", ""))
            if "publicado no jornal oficial" in s:
                if norm(p.get("titulo", "")) not in normas_conhecidas:
                    sugestoes.append(p["id"])
        exec_record["sugestoes_curadoria"] = [
            f"Verificar publicação no JO para entrada em laws.json: {pid}"
            for pid in sugestoes[:10]]

        # 5) Fechamento e persistência
        exec_record["descoberta_candidatos"] = candidatos_total
        exec_record["descoberta_adiada"] = adiados
        self._atualizar_registro(exec_record, n_ev=n_ev)

        # 5.1) Saúde por fonte: instituições do motor legislativo + multiórgão.
        #      Fonte obrigatória não consultada nunca é reportada como sucesso.
        saude_legis = self._saude_instituicoes()
        fontes_monitoradas = dict(saude_legis)
        if resumo_fontes:
            fontes_monitoradas.update(resumo_fontes["fontes_monitoradas"])
        else:
            for orgao in ("ai_office", "eurlex", "eu_council", "eu_commission",
                          "eu_parliament", "edpb", "edps"):
                fontes_monitoradas.setdefault(orgao, {
                    "nome": orgao, "status": "falha",
                    "ultima_tentativa": self.run_iso, "ultima_execucao_ok": None,
                    "itens_consultados": 0, "novidades": 0, "erros": 1,
                    "endpoints": [], "canais_ok": [], "canais_falhos": ["(não executada)"],
                    "erro_detalhe": "coleta multiórgão não executada nesta execução "
                                    "(orçamento de tempo ou desativação explícita)",
                })
        import update_sources_eu as _us
        status_global = _us.calcular_status_global(
            {k: v for k, v in fontes_monitoradas.items()
             if k not in ("parlamento", "eurlex_motor")}, saude_legis)
        exec_record["fontes_monitoradas"] = dict(sorted(fontes_monitoradas.items()))
        exec_record["status_global"] = status_global
        exec_record["fontes_falha"] = sorted(o for o, s in fontes_monitoradas.items()
                                             if (s or {}).get("status") == "falha")
        exec_record["fontes_parciais"] = sorted(o for o, s in fontes_monitoradas.items()
                                                if (s or {}).get("status") == "parcial")
        if resumo_fontes:
            exec_record["http_fontes"] = resumo_fontes["http_fontes"]
            exec_record["novidades_multiorgao"] = resumo_fontes["novidades"]
            exec_record["mudancas_multiorgao"] = len(resumo_fontes["mudancas"])
        if status_global != "OK":
            exec_record["observacao"] = ((exec_record.get("observacao") or "")
                                         + f" Status global: {status_global}"
                                         + (f" — fontes com falha: "
                                            f"{', '.join(exec_record['fontes_falha'])}."
                                            if exec_record["fontes_falha"] else "."))

        parcial = (bool(self.nao_verificadas) or BUDGET.expirado()
                   or status_global != "OK")
        status = "parcial" if parcial else "concluida"
        if status_global == "FALHA":
            status = "falha"
        exec_record["status"] = status
        print(f"\nMudanças detectadas: {len(self.changes)} · novas: {len(self.new_props)} · "
              f"atualizadas: {self.updated} · verificadas: {self.verified} · "
              f"erros: {len(self.errors)} · status: {status} · "
              f"duração: {int(BUDGET.decorrido())}s", flush=True)

        if dry_run:
            print("DRY-RUN: nada foi gravado.", flush=True)
            for c in self.changes[:20]:
                print(f"  - [{c['data']}] {c['titulo'][:90]}", flush=True)
            return exec_record

        self._gravar(props_f, up_f, ev_f, laws_f, tl_f, pm_f, props, exec_record,
                     status=status, atos_f=atos_f)
        print(f"Dataset atualizado e salvo · cobertura {exec_record['cobertura_pct']}% · "
              f"HTTP: {exec_record['http']['chamadas']} chamadas "
              f"({exec_record['http']['cache']} do cache, {exec_record['http']['falhas']} falhas) · "
              f"{exec_record['http']['tempo_total']}s em rede", flush=True)
        return exec_record


def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Motor legislativo do Monitor UE (fontes oficiais da União Europeia).")
    ap.add_argument("--dry-run", action="store_true",
                    help="consulta e relata sem gravar o dataset")
    ap.add_argument("--budget-min", type=float, default=None,
                    help=f"teto de duração da coleta em minutos (padrão: {BUDGET_S / 60:.0f})")
    ap.add_argument("--max-novas", type=int, default=None,
                    help=f"máximo de fichas novas detalhadas por execução (padrão: {MAX_NOVAS})")
    ap.add_argument("--limite", type=int, default=None,
                    help="verificar apenas os N procedimentos mais prioritários (padrão: todos)")
    ap.add_argument("--workers", type=int, default=None,
                    help=f"threads de coleta (padrão: {WORKERS})")
    return ap.parse_args(argv)


def main(argv=None):
    global BUDGET, MAX_NOVAS, MAX_PROPS, WORKERS
    args = parse_args(argv)
    if args.budget_min:
        BUDGET = Budget(int(args.budget_min * 60))
    if args.max_novas is not None:
        MAX_NOVAS = max(0, args.max_novas)
    if args.limite is not None:
        MAX_PROPS = max(0, args.limite)
    if args.workers:
        WORKERS = max(1, args.workers)
    if MAX_NOVAS == 0:
        print("Descoberta de novos procedimentos desativada nesta execução (--max-novas 0).",
              flush=True)
    try:
        rec = Collector().run(dry_run=args.dry_run)
    except BudgetExceeded as e:  # rede lenta: sai sem falhar o job (dados já gravados)
        print(f"[aviso] encerrado pelo orçamento de tempo: {e}", flush=True)
        return 0
    if rec and rec.get("status") == "parcial":
        print("[aviso] execução parcial: o excedente entra na próxima execução.",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
