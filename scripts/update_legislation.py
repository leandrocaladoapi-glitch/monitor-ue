#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_legislation.py — Coletor legislativo automático do Monitor Legislativo de IA.

Camada anterior ao build: consulta fontes oficiais, compara com o estado
anterior versionado em /data/legislation, registra mudanças em updates.json e
atualiza o dataset (fonte única da verdade). Depois disso,
`python3 scripts/build_site.py` regenera o site.

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
status `parcial` — o site é reconstruído e publicado de qualquer forma. Sem esse
teto, o crescimento do dataset (mais proposições = mais chamadas HTTP) fazia a
GitHub Action estourar o timeout de 45 min e nada era publicado.

Sem dependências externas (apenas stdlib). É terminantemente proibido inventar
dados: tudo que este script grava vem de resposta oficial das APIs abaixo.
Campos não confirmados ficam ausentes.

Fontes oficiais consultadas (quando tecnicamente disponíveis):
  Câmara dos Deputados — API de Dados Abertos v2
    /proposicoes (busca por tipo/número/ano, keywords, data de apresentação)
    /proposicoes/{id} (detalhe: ementa, status, regime, relator, principal)
    /proposicoes/{id}/tramitacoes (histórico de movimentações)
    /proposicoes/{id}/autores (autoria)
    /proposicoes/{id}/votacoes (votações registradas)
    /deputados/{id} (nome/partido/UF do relator)
    /eventos (agenda futura)
  Senado Federal — API de Dados Abertos v7
    /materia/pesquisa/lista (busca por sigla/número/ano e palavra-chave)
    /materia/{codigo} (detalhe: ementa, autoria, decisão/destino)
    /materia/movimentacoes/{codigo} (situação atual + informes legislativos)
    /materia/relatorias/{codigo} (relatoria atual e histórico)
    /materia/votacoes/{codigo} (votações)
Além das duas casas, a mesma execução roda os conectores multiórgão de
`scripts/sources` (ANPD, CNJ, TSE, DOU/Imprensa Nacional, Planalto e MCTI) em
subprocessos isolados com timeout próprio — ver `scripts/update_sources.py`.
Os itens coletados nesses órgãos ficam em data/legislation/atos.json, as
mudanças em updates.json e a saúde de cada fonte em `fontes_monitoradas`
(com `status_global`: OK · PARCIAL · FALHA). Câmara e Senado seguem sendo
coletados exatamente como antes por este arquivo.
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
from scoring import compute_impact_score  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "legislation")

CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
BRT = timezone(timedelta(hours=-3))
UA = {"User-Agent": "monitor-legislativo-ia/1.0 (+https://monitor-legislativo-five.vercel.app)",
      "Accept": "application/json"}

OLD_DOMAIN = "lcaladoferreira.github.io/monitor-legislativo"

# ---------------------------------------------------------------- orçamento
# Por que isto existe: o dataset cresce a cada execução (mais proposições =
# mais fichas para consultar). Sem teto de tempo, a coleta passava dos 45 min
# do job e era cancelada pelo GitHub Actions ANTES do rebuild/commit — o site
# ficava congelado na execução anterior. O orçamento garante que a execução
# sempre termine a tempo de publicar (mesmo que parcialmente).
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


class BudgetExceeded(RuntimeError):
    """Levantada quando o orçamento de tempo da coleta se esgota."""


class Budget:
    """Relógio monotônico compartilhado pelas threads.

    `margem` é a reserva final: quando o tempo restante cai abaixo dela, o
    coletor para de iniciar consultas e fecha a execução graciosamente.
    """

    def __init__(self, segundos, margem=None):
        self.limite = max(5, int(segundos))  # piso baixo: usado nos testes offline
        self.margem = MARGEM_FINAL_S if margem is None else max(0, int(margem))
        self.t0 = time.monotonic()
        self._lock = threading.Lock()

    def decorrido(self):
        return time.monotonic() - self.t0

    def restante(self):
        return max(0.0, self.limite - self.decorrido())

    def expirado(self, folga=0):
        return self.restante() <= (self.margem + max(0, folga))

    def checar(self, folga=0):
        if self.expirado(folga):
            raise BudgetExceeded(
                f"orçamento de {self.limite}s esgotado "
                f"(decorrido: {int(self.decorrido())}s)")

    def pausa(self, segundos):
        """Pausa educada, encurtada se o orçamento estiver no fim."""
        time.sleep(max(0.0, min(segundos, self.restante() - self.margem)))


BUDGET = Budget(BUDGET_S)

# Tipos de proposição aceitos na descoberta automática (Câmara e Senado).
TIPOS_INCLUIR = {"PL", "PLP", "PEC", "PDL", "PDN", "PLN", "MPV", "PDC", "PRC",
                 "PLC", "PLS", "PDS", "EMS", "SUBSTITUTIVO"}
# Requerimentos entram apenas com match forte e flag de revisão pendente.
TIPOS_REQUERIMENTO = {"REQ", "RIC", "RQS", "RMA"}

# --- Relevância temática (sobre texto normalizado: minúsculo, sem acento) ---
STRONG_PATTERNS = [
    r"inteligencia artificial", r"\bia generativa\b", r"ia de proposito geral",
    r"deepfake", r"conteudo sintetico", r"midia sintetica",
    r"decisao automatizada", r"decisoes automatizadas", r"tomada de decisao automat",
    r"reconhecimento facial", r"reconhecimento biometrico", r"biometria facial",
    r"modelos? fundaciona", r"large language models?", r"\bllms?\b",
    r"agentes? de ia\b", r"agentes? autonomos?", r"sistemas? autonomos?",
    r"sistemas? automatizados?", r"automacao algoritmica", r"governanca algoritmica",
    r"responsabilidade por sistemas de ia", r"marco legal da (inteligencia artificial|\bia\b)",
    r"sistema nacional de (inteligencia artificial|\bia\b)",
    r"treinamento de modelos", r"dados de treinamento",
]
MEDIUM_PATTERNS = [
    r"algoritm", r"automatiz", r"machine learning", r"aprendizado de maquina",
    r"aprendizado profundo", r"deep learning", r"processamento de linguagem natural",
    r"\bchatbots?\b", r"redes neurais", r"visao computacional",
    r"biometr", r"datacenter", r"data centers?", r"centro de dados",
    r"microchip", r"semicondutor", r"computacao de alto desempenho",
]
# Termos de infraestrutura que isoladamente geram revisão pendente (evitar falso positivo).
INFRA_ONLY = [r"datacenter", r"data centers?", r"centro de dados", r"semicondutor", r"microchip"]

STRONG_RE = [re.compile(p) for p in STRONG_PATTERNS]
MEDIUM_RE = [re.compile(p) for p in MEDIUM_PATTERNS]
INFRA_RE = [re.compile(p) for p in INFRA_ONLY]

FONTES_CAMARA = [
    "API de Dados Abertos da Câmara dos Deputados — proposições (detalhe)",
    "API de Dados Abertos da Câmara dos Deputados — tramitações",
    "API de Dados Abertos da Câmara dos Deputados — autores",
    "API de Dados Abertos da Câmara dos Deputados — votações",
    "API de Dados Abertos da Câmara dos Deputados — deputados (relator)",
    "API de Dados Abertos da Câmara dos Deputados — eventos (agenda)",
]
FONTES_SENADO = [
    "API de Dados Abertos do Senado Federal — matérias (detalhe)",
    "API de Dados Abertos do Senado Federal — movimentações",
    "API de Dados Abertos do Senado Federal — relatorias",
    "API de Dados Abertos do Senado Federal — votações",
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
    casa = "camara" if "camara" in partes.netloc else (
        "senado" if "senado" in partes.netloc else "outro")
    seg = [p for p in partes.path.split("/") if p][2:] if casa != "outro" else []
    limpos = []
    for p in seg:
        limpos.append("{id}" if p.isdigit() else p.removesuffix(".json"))
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


def _http_urllib(url, timeout):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _http_curl(url, timeout):
    import subprocess
    out = subprocess.run(
        [_CURL_BIN, "-sS", "-m", str(timeout), "-H", "Accept: application/json",
         "-H", f"User-Agent: {UA['User-Agent']}", url],
        capture_output=True, text=True, timeout=timeout + 5)
    if out.returncode != 0:
        raise RuntimeError(f"curl exit {out.returncode}: {(out.stderr or '')[:120]}")
    return json.loads(out.stdout)


def http_get_json(url, timeout=None, retries=None, cache=True):
    """GET com orçamento de tempo, cache de execução e retries. Dict ou None.

    Levanta BudgetExceeded quando o orçamento acaba: nenhuma chamada nova é
    iniciada e a coleta é encerrada de forma limpa (dados parciais preservados).
    Usa curl quando disponível (handshake mais robusto nos runners do GitHub
    Actions); caso contrário, urllib da stdlib.
    """
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
                    payload = _http_curl(url, int(espera))
                else:
                    payload = _http_urllib(url, int(espera))
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
    """Classifica relevância temática: 'forte', 'media', 'infra' ou None."""
    t = norm(text)
    if any(r.search(t) for r in STRONG_RE):
        return "forte"
    if any(r.search(t) for r in MEDIUM_RE):
        # infra isolada (ex.: só "data center") pede curadoria, não inclusão direta
        others = [r for r in MEDIUM_RE if r.pattern not in INFRA_ONLY or True]
        non_infra = [p for p in MEDIUM_PATTERNS if p not in INFRA_ONLY]
        if any(re.search(p, t) for p in non_infra):
            return "media"
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


# ------------------------------------------------------------- APIs Câmara
def camara_find_id(tipo, numero, ano):
    q = urllib.parse.urlencode({"siglaTipo": tipo, "numero": numero, "ano": ano,
                                "ordem": "ASC", "ordenarPor": "id"})
    d = http_get_json(f"{CAMARA}/proposicoes?{q}")
    polite_pause()
    if not d:
        return None
    for item in d.get("dados", []):
        if (item.get("siglaTipo") == tipo and item.get("numero") == numero
                and item.get("ano") == ano):
            return item.get("id")
    return None


def camara_detail(pid):
    d = http_get_json(f"{CAMARA}/proposicoes/{pid}")
    polite_pause()
    return (d or {}).get("dados")


def camara_tramitacoes(pid):
    d = http_get_json(f"{CAMARA}/proposicoes/{pid}/tramitacoes")
    polite_pause()
    return (d or {}).get("dados", []) or []


def camara_autores(pid):
    d = http_get_json(f"{CAMARA}/proposicoes/{pid}/autores")
    polite_pause()
    return (d or {}).get("dados", []) or []


def camara_votacoes(pid):
    # Melhor esforço: endpoint historicamente lento; uma tentativa curta.
    d = http_get_json(f"{CAMARA}/proposicoes/{pid}/votacoes", timeout=12, retries=1)
    polite_pause()
    return (d or {}).get("dados", []) or []


def camara_deputado(uri_or_id):
    if not uri_or_id:
        return None
    url = uri_or_id if str(uri_or_id).startswith("http") else f"{CAMARA}/deputados/{uri_or_id}"
    d = http_get_json(url, retries=2)
    polite_pause()
    return (d or {}).get("dados")


def camara_id_from_prop(p):
    for u in [p.get("url_oficial")] + [d.get("url") for d in p.get("documentos", [])]:
        if not u:
            continue
        m = re.search(r"idProposicao=(\d+)", u)
        if m:
            return int(m.group(1))
    return None


# ------------------------------------------------------------- APIs Senado
def senado_detail(codigo):
    d = http_get_json(f"{SENADO}/materia/{codigo}.json")
    polite_pause()
    try:
        return d["DetalheMateria"]["Materia"]
    except (TypeError, KeyError):
        return None


def senado_movimentacoes(codigo):
    d = http_get_json(f"{SENADO}/materia/movimentacoes/{codigo}.json")
    polite_pause()
    try:
        return d["MovimentacaoMateria"]["Materia"]
    except (TypeError, KeyError):
        return None


def senado_relatorias(codigo):
    d = http_get_json(f"{SENADO}/materia/relatorias/{codigo}.json", retries=2)
    polite_pause()
    try:
        return d["RelatoriaMateria"]["Materia"]
    except (TypeError, KeyError):
        return None


def senado_search(sigla=None, numero=None, ano=None, palavra_chave=None):
    params = {}
    if sigla:
        params["sigla"] = sigla
    if numero:
        params["numero"] = numero
    if ano:
        params["ano"] = ano
    if palavra_chave:
        params["palavraChave"] = palavra_chave
    d = http_get_json(f"{SENADO}/materia/pesquisa/lista?{urllib.parse.urlencode(params)}",
                      retries=2)
    polite_pause()
    if not d:
        return []
    try:
        return as_list(d["PesquisaBasicaMateria"]["Materias"]["Materia"])
    except (TypeError, KeyError):
        return []


def senado_codes_from_prop(p):
    codes = []
    urls = [p.get("url_oficial")] + [d.get("url") for d in p.get("documentos", [])] \
        + [f.get("url") for f in p.get("fontes_adicionais", [])]
    for u in urls:
        if not u:
            continue
        for m in re.finditer(r"materia/(\d+)", u):
            if m.group(1) not in codes:
                codes.append(m.group(1))
    return codes


# ------------------------------------------------------- tipos de mudança
def infer_change_type(text):
    t = norm(text)
    if "desapens" in t and "apense-se" not in t and "apense se" not in t:
        return "desapensação"
    if "apens" in t:
        return "apensação"
    if "desarquiv" in t:
        return "desarquivamento"
    if "arquiv" in t:
        return "arquivamento"
    if "sancao" in t or "sancionad" in t or "transformada em norma" in t or "convertida" in t:
        return "sanção"
    if "veto" in t:
        return "veto"
    if "promulg" in t:
        return "promulgação"
    if "parecer" in t:
        return "parecer"
    if "votac" in t or "aprovad" in t or "rejeitad" in t:
        return "votação"
    if "pauta" in t or "ordem do dia" in t:
        return "pauta"
    if "relator" in t:
        return "relatoria"
    if "redacao final" in t:
        return "redação final"
    if "publica" in t:
        return "publicação"
    return "tramitação"


# ------------------------------------------------------- categorias inferidas
CATEGORY_KEYWORDS = [
    (["marco legal", "marco regulatorio", "sistema nacional", "normas gerais",
      "politica nacional de inteligencia"], [1]),
    (["direitos fundamentais", "direitos humanos"], [2]),
    (["dados pessoais", "lgpd", "protecao de dados", "privacidade"], [3]),
    (["responsabilidade civil", "responsabilidade por"], [4]),
    (["crime", "penal", "pena de", "reclusao", "detencao", "deepfake"], [5]),
    (["direito autoral", "direitos autorais", "titular de direito"], [6]),
    (["trabalh", "emprego", "profission"], [7]),
    (["educac", "escola", "ensino"], [8]),
    (["saude", "hospital", "medic"], [9]),
    (["seguranca publica", "policia", "violencia domestica"], [10]),
    (["defesa nacional", "forcas armadas", "militar"], [11]),
    (["judiciario", "justica", "tribunal", "processo judicial"], [12]),
    (["eleic", "eleitor", "campanha eleitoral", "pleito"], [13]),
    (["deepfake"], [14]),
    (["desinformacao", "fake news", "conteudo falso"], [15]),
    (["plataforma", "rede social", "provedor"], [16]),
    (["biometr"], [17]),
    (["reconhecimento facial"], [18]),
    (["administracao publica", "servico publico", "setor publico", "governo"], [19]),
    (["banco", "credito", "financeir", "fintech"], [20]),
    (["consumidor"], [21]),
    (["ciberseguranca", "seguranca cibernetica", "incidente de seguranca"], [22]),
    (["agente autonomo", "sistema autonomo", "agentes de ia"], [23]),
    (["transparencia", "rotulagem", "rotulo", "identificacao de conteudo"], [24]),
    (["auditoria", "avaliacao de risco", "avaliacao de impacto"], [25]),
    (["alto risco", "risco excessivo", "sistema de alto risco"], [26]),
    (["pesquisa", "desenvolvimento cientifico", "inovacao"], [27]),
    (["incentivo fiscal", "tributario", "renuncia", "regime especial", "fundo"], [28]),
    (["datacenter", "data center", "centro de dados", "infraestrutura"], [29]),
    (["soberania", "nuvem soberana", "dados nacionais"], [30]),
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
        self.verificadas_ids = set()  # proposições distintas consultadas (cobertura)
        self.verificadas_casa = {"camara": 0, "senado": 0}  # saúde por casa
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

    def _marca_verificada(self, prop_id):
        """Conta a ficha consultada e a proposição distinta (cobertura ≤ 100%)."""
        with self._lock:
            self.verified += 1
            self.verificadas_ids.add(prop_id)
            casa = "senado" if str(prop_id).startswith("senado_") else "camara"
            self.verificadas_casa[casa] = self.verificadas_casa.get(casa, 0) + 1

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

    # -------------------------------------------------- proposições Câmara
    def update_camara_prop(self, p, last_run):
        pid = camara_id_from_prop(p)
        if not pid:
            pid = camara_find_id(p["tipo"], p["numero"], p["ano"])
            if pid:
                # completa o registro com a ficha oficial canônica
                ficha = f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}"
                if not p.get("url_oficial"):
                    p["url_oficial"] = ficha
        if not pid:
            return False  # pode ser matéria do Senado; o erro só se confirma em _update_one
        detail = camara_detail(pid)
        if not detail:
            self.errors.append(f"{p['id']}: detalhe indisponível na API da Câmara")
            return False
        self._add_fontes(FONTES_CAMARA[:2])
        self._marca_verificada(p["id"])
        changed = False
        st = detail.get("statusProposicao") or {}
        ficha_url = f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}"
        api = p.setdefault("api_camara", {})
        api.update({
            "id_proposicao": pid,
            "verificado_em": self.run_iso,
            "status_datahora": st.get("dataHora"),
            "descricao_situacao": st.get("descricaoSituacao"),
            "descricao_tramitacao": st.get("descricaoTramitacao"),
            "despacho": st.get("despacho"),
            "sigla_orgao": st.get("siglaOrgao"),
            "regime": st.get("regime"),
            "apreciacao": st.get("apreciacao"),
            "uri_prop_principal": detail.get("uriPropPrincipal"),
            "keywords": detail.get("keywords"),
            "url_inteiro_teor": detail.get("urlInteiroTeor"),
            "ementa_api": detail.get("ementa"),
        })

        # Regime / apreciação (campos objetivos da API)
        for field, key in (("regime_tramitacao", "regime"), ("forma_apreciacao", "apreciacao")):
            new_val = st.get(key)
            if new_val and p.get(field) != new_val:
                # só registra mudança se o valor anterior existia (evita ruído de curadoria)
                if p.get(field):
                    self.add_change(
                        data_evento=date_only(st.get("dataHora")) or self.today,
                        titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: {field.replace('_', ' ')} atualizado",
                        descricao=f"{field.replace('_', ' ').capitalize()} passou de "
                                  f"“{p.get(field)}” para “{new_val}”, conforme ficha oficial.",
                        tipo="atualização cadastral", proposicao=p["id"],
                        fonte="Câmara dos Deputados — API de Dados Abertos",
                        fonte_url=ficha_url, campo=field,
                        anterior=p.get(field), novo=new_val)
                p[field] = new_val
                changed = True

        # Última movimentação via tramitações
        trams = camara_tramitacoes(pid)
        if trams:
            self._add_fonte(FONTES_CAMARA[1])
            last = trams[-1]
            last_date = date_only(last.get("dataHora"))
            last_text = (last.get("despacho") or last.get("descricaoTramitacao") or "").strip()
            last_sigla = last.get("siglaOrgao")
            api["ultima_tramitacao"] = {
                "data": last_date, "orgao": last_sigla,
                "tramitacao": last.get("descricaoTramitacao"), "despacho": last_text,
                "sequencia": last.get("sequencia"),
            }
            stored = p.get("ultima_movimentacao") or {}
            if last_date and (stored.get("data") != last_date or
                              norm(stored.get("descricao", ""))[:80] != norm(last_text)[:80]):
                if stored.get("data") and last_date < stored.get("data"):
                    # Ficha da Câmara está atrás do registro curado (ex.: evento de outra
                    # Casa). Não regride o dataset; apenas mantém o snapshot da API.
                    pass
                else:
                    self._record_movimentacao(p, last, last_date, last_text, last_sigla,
                                              stored, ficha_url, last_run)
                    changed = True
                    # Detecta apensações novas dentro do pacote (para proposições principais)
                    self._detect_apensacoes(trams, p, ficha_url, last_run)

        # Proposição principal (apensação) — dado objetivo da API
        principal_nome = self._resolve_principal(detail, p)
        if principal_nome:
            api["proposicao_principal_api"] = principal_nome
            if p.get("proposicao_principal") != principal_nome["id_dataset"]:
                anterior = p.get("proposicao_principal")
                p["proposicao_principal"] = principal_nome["id_dataset"]
                if anterior:  # só registra se houve troca real (não preenchimento)
                    self.add_change(
                        data_evento=self.today,
                        titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: proposição principal alterada",
                        descricao=f"Principal passou de {anterior} para {principal_nome['id_dataset']}.",
                        tipo="apensação", proposicao=p["id"],
                        fonte="Câmara dos Deputados — API de Dados Abertos",
                        fonte_url=ficha_url, campo="proposicao_principal",
                        anterior=anterior, novo=principal_nome["id_dataset"])
                changed = True

        # Relator (via uriUltimoRelator → ficha do deputado)
        relator_uri = st.get("uriUltimoRelator")
        if relator_uri:
            dep = camara_deputado(relator_uri)
            if dep:
                self._add_fonte(FONTES_CAMARA[4])
                ultimo = dep.get("ultimoStatus") or {}
                nome = ultimo.get("nome") or dep.get("nomeCivil", "").title()
                partido = ultimo.get("siglaPartido")
                uf = ultimo.get("siglaUf")
                api["relator_api"] = {"nome": nome, "partido": partido, "estado": uf}
                stored_rel = p.get("relator") or {}
                if nome and norm(stored_rel.get("nome", "")) not in ("", norm(nome)) \
                        and norm(nome) not in norm(stored_rel.get("nome", "")) \
                        and norm(stored_rel.get("nome", "")) not in norm(nome):
                    self.add_change(
                        data_evento=date_only(st.get("dataHora")) or self.today,
                        titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: relator alterado",
                        descricao=f"Relatoria passou de “{stored_rel.get('nome', '—')}” para "
                                  f"“{nome} ({partido}-{uf})”.",
                        tipo="relatoria", proposicao=p["id"],
                        fonte="Câmara dos Deputados — API de Dados Abertos",
                        fonte_url=ficha_url, campo="relator",
                        anterior=stored_rel.get("nome"), novo=nome)
                    p["relator"] = {"nome": f"Deputado {nome}" if not norm(nome).startswith("deputad") else nome,
                                    "partido": partido, "estado": uf}
                    changed = True

        # Autores (completa quando ausente; não sobrescreve curadoria)
        if not (p.get("autor") or {}).get("nome"):
            autores = camara_autores(pid)
            if autores:
                self._add_fonte(FONTES_CAMARA[2])
                a0 = autores[0]
                if a0.get("tipo") == "Deputado" or "deputados/" in (a0.get("uri") or ""):
                    dep = camara_deputado(a0.get("uri"))
                    ultimo = (dep or {}).get("ultimoStatus", {}) if dep else {}
                    p["autor"] = {"nome": ultimo.get("nome") or a0.get("nome"),
                                  "partido": ultimo.get("siglaPartido"),
                                  "estado": ultimo.get("siglaUf")}
                else:
                    p["autor"] = {"nome": a0.get("nome")}
                changed = True

        # Votações (melhor esforço)
        try:
            vots = camara_votacoes(pid)
        except Exception:  # noqa: BLE001
            vots = []
        if vots:
            self._add_fonte(FONTES_CAMARA[3])
            api["votacoes_total"] = len(vots)
            novas = [v for v in vots if (v.get("data") or "") > (last_run or "0000-00-00")]
            if novas:
                v = sorted(novas, key=lambda x: x.get("data", ""))[-1]
                api["ultima_votacao"] = {"data": v.get("data"), "descricao": v.get("descricao")}
                self.add_change(
                    data_evento=v.get("data") or self.today,
                    titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: votação registrada",
                    descricao=f"{v.get('data')}: {v.get('descricao', '')[:400]}",
                    tipo="votação", proposicao=p["id"],
                    fonte="Câmara dos Deputados — API de Dados Abertos (votações)",
                    fonte_url=v.get("uri") or ficha_url, campo="votacoes",
                    anterior=None, novo=v.get("descricao", "")[:200])
                changed = True
        if changed:
            self._bump("updated")
        return True

    def _record_movimentacao(self, p, last, last_date, last_text, last_sigla, stored,
                             ficha_url, last_run):
        tram_nome = last.get("descricaoTramitacao") or "nova movimentação"
        mesma_data = stored.get("data") == last_date
        if mesma_data:
            # Mesma data, redação diferente: alinhamento de texto à ficha oficial
            ctype = "atualização cadastral"
            titulo = (f"{p['tipo']} {p['numero']}/{p['ano']}: {tram_nome} "
                      f"(alinhamento de texto à ficha oficial)")
            desc = (f"Redação da movimentação de {last_date} alinhada ao texto oficial: "
                    f"{last_text[:400]}")
        else:
            # Nova movimentação (ou correção de registro anterior)
            ctype = infer_change_type(f"{tram_nome} {last_text}")
            nova = (last_date > (last_run or "0000-00-00")) if last_date else False
            titulo = (f"{p['tipo']} {p['numero']}/{p['ano']}: {tram_nome}"
                      + ("" if nova else " (registro incorporado)"))
            desc = f"Em {last_date}, {last_sigla or 'ficha oficial'}: {last_text[:400]}"
            if not nova:
                desc += (" Movimentação já constava na ficha oficial antes desta execução "
                         "e foi incorporada ao dataset agora.")
        self.add_change(
            data_evento=last_date or self.today, titulo=titulo, descricao=desc,
            tipo=ctype, proposicao=p["id"],
            fonte="Câmara dos Deputados — ficha de tramitação (API)",
            fonte_url=ficha_url, campo="ultima_movimentacao",
            anterior=f"{stored.get('data', '?')} — {(stored.get('descricao') or '')[:200]}",
            novo=f"{last_date} — {last_text[:200]}")
        p["ultima_movimentacao"] = {"data": last_date, "descricao": last_text[:800]}
        # Situação: reflete o despacho mais recente quando ele indica estado novo
        new_sit = self._situacao_from_tram(last, p)
        if new_sit and new_sit != p.get("situacao"):
            self.add_change(
                data_evento=last_date or self.today,
                titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: situação atualizada",
                descricao=f"Situação passou de “{(p.get('situacao') or '')[:200]}” para "
                          f"“{new_sit[:200]}”.",
                tipo=ctype, proposicao=p["id"],
                fonte="Câmara dos Deputados — ficha de tramitação (API)",
                fonte_url=ficha_url, campo="situacao",
                anterior=p.get("situacao"), novo=new_sit)
            p["situacao"] = new_sit

    def _situacao_from_tram(self, last, p):
        """Deriva texto de situação a partir da última tramitação.

        Preserva o prefixo curado de apensação quando a proposição segue
        apensada; caso contrário reflete despacho + órgão da ficha oficial.
        """
        stored = p.get("situacao") or ""
        tram = (last.get("descricaoTramitacao") or "").strip()
        desp = (last.get("despacho") or "").strip()
        org = (last.get("siglaOrgao") or "").strip()
        t = norm(f"{tram} {desp}")
        s = norm(stored)
        if "desarquiv" in t:
            return f"Desarquivada — {tram} ({org}): {desp[:220]}".strip()
        terminal = any(k in s for k in ("arquivad", "prejudicad", "transformada em norma",
                                        "convertida em norma", "promulgad"))
        if terminal:
            # Estado terminal curado: despacho burocrático não o degrada.
            return stored
        if "apens" in t and "desapens" not in t:
            # mantém contexto curado; a apensação em si gera change próprio
            return stored
        if "desapens" in t:
            # Re-apensação ("desapense-se de X e apense-se a Y")? extrai o destino.
            m = re.search(r"apense-se\s+[aà](?:\(ao\))?\s*([A-Z]{2,4})\s*(\d{1,5})/(\d{4})",
                          desp, re.IGNORECASE)
            if m:
                target = f"{m.group(1).upper()} {m.group(2)}/{m.group(3)}"
                if target.lower() in s:
                    return stored  # destino igual ao curado: sem mudança de estado
                return f"Apensado ao {target} (despacho de {date_only(last.get('dataHora')) or 'correção'})"
            return f"Desapensada — {tram} ({org}): {desp[:220]}".strip()
        if "sancao" in s and "sancao" in t:
            return stored  # segue aguardando sanção: sem mudança de estado
        if any(k in t for k in ("sancion", "transformada em norma", "convertida")):
            return f"Convertida em norma — {tram}: {desp[:220]}".strip()
        if "sancao" in t:
            return "Aguarda sanção presidencial"
        if any(k in t for k in ("parecer", "votac", "aprovad", "rejeitad", "pauta",
                                "ordem do dia", "redacao final")):
            # mudança de estado relevante: reflete a ficha oficial
            return f"{tram} ({org}): {desp[:220]}".strip()
        # Movimentações burocráticas (publicação, recebimento, juntada etc.) não
        # alteram o estado: preserva a situação curada.
        return stored

    def _detect_apensacoes(self, trams, p, ficha_url, last_run):
        """Registra apensações novas ocorridas no pacote da proposição principal."""
        if not trams or not last_run:
            return
        for t in trams:
            d = date_only(t.get("dataHora"))
            if not d or d <= last_run:
                continue
            txt = f"{t.get('descricaoTramitacao', '')} {t.get('despacho', '')}"
            if "apens" in norm(txt) and "desapens" not in norm(txt):
                pls = re.findall(r"PL\s*(\d{1,5})/(\d{4})", txt)
                detalhe = "; ".join(f"PL {n}/{a}" for n, a in pls[:4]) or txt[:160]
                self.add_change(
                    data_evento=d,
                    titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: nova apensação no pacote ({detalhe})",
                    descricao=f"Em {d}: {txt.strip()[:450]}",
                    tipo="apensação", proposicao=p["id"],
                    fonte="Câmara dos Deputados — ficha de tramitação (API)",
                    fonte_url=ficha_url)

    def _resolve_principal(self, detail, p):
        """Resolve a proposição principal canônica (para apensadas)."""
        uri = detail.get("uriPropPrincipal")
        if not uri:
            return None
        m = re.search(r"/proposicoes/(\d+)", uri)
        if not m:
            return None
        princ_id = int(m.group(1))
        if princ_id == detail.get("id"):
            return None  # é a principal
        princ = camara_detail(princ_id)
        if not princ:
            return None
        sigla = (princ.get("siglaTipo") or "").lower()
        ds_id = f"camara_{sigla}_{princ.get('numero')}_{princ.get('ano')}"
        return {"id_dataset": ds_id,
                "rotulo": f"{princ.get('siglaTipo')} {princ.get('numero')}/{princ.get('ano')}",
                "id_camara": princ_id}

    # --------------------------------------------------- proposições Senado
    def update_senado_refs(self, p, last_run):
        codes = senado_codes_from_prop(p)
        if not codes:
            # tenta localizar pelo Senado (útil p/ casa_origem = Senado Federal)
            if p.get("casa_origem") == "Senado Federal" or p["id"].startswith("senado_"):
                found = senado_search(sigla=p["tipo"], numero=str(p["numero"]), ano=str(p["ano"]))
                for m in found:
                    if (m.get("Sigla") == p["tipo"]
                            and str(m.get("Numero")).lstrip("0") == str(p["numero"])
                            and str(m.get("Ano")) == str(p["ano"])):
                        codes = [m.get("Codigo")]
                        break
        if not codes:
            return False
        changed = False
        for code in codes[:2]:
            det = senado_detail(code)
            mov = senado_movimentacoes(code)
            if not det and not mov:
                continue
            self._add_fontes(FONTES_SENADO[:2])
            self._marca_verificada(p["id"])
            api = p.setdefault("api_senado", {})
            ficha = f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{code}"
            if det:
                dados = det.get("DadosBasicosMateria", {}) or {}
                ident = det.get("IdentificacaoMateria", {}) or {}
                dec = (det.get("DecisaoEDestino") or {}).get("Decisao", {}) or {}
                api.update({
                    "codigo_materia": code, "verificado_em": self.run_iso,
                    "tramitando": ident.get("IndicadorTramitando"),
                    "ementa_api": dados.get("EmentaMateria"),
                    "apelido": dados.get("ApelidoMateria"),
                    "autor_api": dados.get("Autor"),
                    "decisao": dec.get("Descricao"), "decisao_data": dec.get("Data"),
                })
            if mov:
                try:
                    aut = mov["Autuacoes"]["Autuacao"][0]
                    sit = as_list((aut.get("SituacoesAtuais") or {}).get("SituacaoAtual"))[0]
                    infs = as_list((aut.get("InformesLegislativos") or {}).get("InformeLegislativo"))
                except (KeyError, IndexError):
                    continue
                api["situacao_senado"] = {
                    "data": sit.get("DataSituacao"),
                    "sigla": sit.get("SiglaSituacao"),
                    "descricao": sit.get("DescricaoSituacao"),
                }
                if infs:
                    first = infs[0]  # API retorna em ordem descendente (mais recente primeiro)
                    fdate = date_only((first.get("Data") or "").replace(" ", "T")
                                      if re.match(r"\d{4}-\d{2}-\d{2}", first.get("Data") or "")
                                      else None)
                    # Data vem como "2025-03-17 15:53:41"
                    mdate = re.match(r"(\d{4}-\d{2}-\d{2})", first.get("Data") or "")
                    fdate = mdate.group(1) if mdate else None
                    fdesc = (first.get("Descricao") or "").strip()
                    api["ultimo_informe_senado"] = {"data": fdate, "descricao": fdesc[:500]}
                    prev = p.get("api_senado", {}).get("ultimo_informe_senado", {})
                    if fdate and (prev.get("data") != fdate
                                  or norm(prev.get("descricao", ""))[:80] != norm(fdesc)[:80]):
                        if prev.get("data"):  # só registra se já havia snapshot anterior
                            ctype = infer_change_type(fdesc)
                            self.add_change(
                                data_evento=fdate, titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: movimentação no Senado",
                                descricao=f"Em {fdate}: {fdesc[:450]}",
                                tipo=ctype, proposicao=p["id"],
                                fonte="Senado Federal — API de Dados Abertos (movimentações)",
                                fonte_url=ficha, campo="senado_movimentacao",
                                anterior=f"{prev.get('data', '?')} — {(prev.get('descricao') or '')[:200]}",
                                novo=f"{fdate} — {fdesc[:200]}")
                            changed = True
            rel = senado_relatorias(code)
            if rel:
                self._add_fonte(FONTES_SENADO[2])
                atual = rel.get("RelatoriaAtual")
                if atual:
                    parl = (atual.get("IdentificacaoParlamentar") or {})
                    rinfo = {"nome": parl.get("NomeParlamentar"),
                             "partido": parl.get("SiglaPartidoParlamentar"),
                             "estado": parl.get("UfParlamentar")}
                    api["relatoria_senado_atual"] = rinfo
                    stored_rs = p.get("relator_senado") or {}
                    if rinfo["nome"] and stored_rs.get("nome") \
                            and norm(rinfo["nome"]) not in norm(stored_rs["nome"]) \
                            and norm(stored_rs["nome"]) not in norm(rinfo["nome"]):
                        self.add_change(
                            data_evento=self.today,
                            titulo=f"{p['tipo']} {p['numero']}/{p['ano']}: relator no Senado alterado",
                            descricao=f"Relatoria no Senado passou de “{stored_rs.get('nome')}” para "
                                      f"“{rinfo['nome']} ({rinfo['partido']}-{rinfo['estado']})”.",
                            tipo="relatoria", proposicao=p["id"],
                            fonte="Senado Federal — API de Dados Abertos (relatorias)",
                            fonte_url=ficha, campo="relator_senado",
                            anterior=stored_rs.get("nome"), novo=rinfo["nome"])
                        p["relator_senado"] = rinfo
                        changed = True
        if changed:
            self._bump("updated")
        return True

    # ------------------------------------------------- descoberta: Câmara
    def discover_camara(self, known_keys, last_run):
        """Descobre proposições novas na Câmara.

        `last_run` é uma data ISO (YYYY-MM-DD). Antes era passado o timestamp
        completo da execução anterior (com hora e fuso), que é inválido para o
        parâmetro `dataApresentacaoInicio` da API — a paginação vinha sem filtro
        e a descoberta varria o banco inteiro em toda execução (uma das causas
        do estouro de tempo do job).
        """
        found = []
        # 1) Incremental: tudo apresentado desde a última execução (1 dia de
        #    sobreposição para não perder matérias apresentadas entre execuções).
        if last_run:
            inicio = (datetime.strptime(last_run, "%Y-%m-%d").date()
                      - timedelta(days=1)).isoformat()
            for page in range(1, 6):
                if BUDGET.expirado():
                    break
                q = urllib.parse.urlencode({
                    "dataApresentacaoInicio": inicio, "ordem": "DESC",
                    "ordenarPor": "id", "itens": 100, "pagina": page})
                d = http_get_json(f"{CAMARA}/proposicoes?{q}")
                polite_pause()
                if not d:
                    break
                items = d.get("dados", [])
                if not items:
                    break
                for it in items:
                    rel = relevance(it.get("ementa", ""))
                    if not rel:
                        continue
                    tipo = it.get("siglaTipo")
                    if tipo not in TIPOS_INCLUIR and tipo not in TIPOS_REQUERIMENTO:
                        continue
                    key = ("camara", tipo, it.get("numero"), it.get("ano"))
                    if key in known_keys:
                        continue
                    found.append((it, rel, "incremental"))
                if len(items) < 100:
                    break
        # 2) Busca por palavras-chave (capta matérias antigas ainda não monitoradas)
        for kw in ("inteligencia artificial", "deepfake", "reconhecimento facial",
                   "conteudo sintetico", "decisao automatizada"):
            for page in range(1, 4):
                if BUDGET.expirado():
                    break
                q = urllib.parse.urlencode({"keywords": kw, "ordem": "DESC",
                                            "ordenarPor": "id", "itens": 100, "pagina": page})
                d = http_get_json(f"{CAMARA}/proposicoes?{q}")
                polite_pause()
                if not d:
                    break
                items = d.get("dados", [])
                if not items:
                    break
                for it in items:
                    # filtro anti-falso-positivo: a ementa precisa mencionar o tema
                    rel = relevance(it.get("ementa", ""))
                    if not rel:
                        continue
                    tipo = it.get("siglaTipo")
                    if tipo not in TIPOS_INCLUIR and tipo not in TIPOS_REQUERIMENTO:
                        continue
                    key = ("camara", tipo, it.get("numero"), it.get("ano"))
                    if key in known_keys or any(f[0].get("id") == it.get("id") for f in found):
                        continue
                    found.append((it, rel, f"keywords:{kw}"))
                if len(items) < 100:
                    break
        if found:
            self._add_fonte("API de Dados Abertos da Câmara dos Deputados — descoberta (keywords + incremental)")
        return found

    def build_new_camara_record(self, item, rel, via):
        pid = item.get("id")
        detail = camara_detail(pid) or {}
        st = detail.get("statusProposicao") or {}
        trams = camara_tramitacoes(pid)
        last = trams[-1] if trams else {}
        last_date = date_only(last.get("dataHora")) or date_only(item.get("dataApresentacao"))
        last_text = ((last.get("despacho") or last.get("descricaoTramitacao") or "").strip()
                     or "Apresentação da proposição.")
        ementa = detail.get("ementa") or item.get("ementa", "")
        ficha = f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={pid}"
        detalhe_ok = bool(detail)
        tipo = item.get("siglaTipo")
        numero = item.get("numero")
        ano = item.get("ano")
        # Autor (melhor esforço; ausente se não confirmado)
        autor = {}
        autores = camara_autores(pid)
        if autores:
            a0 = autores[0]
            if "deputados/" in (a0.get("uri") or ""):
                dep = camara_deputado(a0.get("uri")) or {}
                ult = dep.get("ultimoStatus", {}) or {}
                autor = {"nome": ult.get("nome") or a0.get("nome"),
                         "partido": ult.get("siglaPartido"), "estado": ult.get("siglaUf")}
            else:
                autor = {"nome": a0.get("nome")}
        titulo = (detail.get("ementa") or item.get("ementa", ""))[:140]
        cats = infer_categories(ementa, titulo)
        rec = {
            "id": f"camara_{tipo.lower()}_{numero}_{ano}",
            "tipo": tipo, "numero": numero, "ano": ano,
            "titulo": titulo, "ementa": ementa,
            "casa_origem": "Câmara dos Deputados",
            "casa_atual": "Câmara dos Deputados",
            "url_oficial": ficha,
            "autor": autor,
            "data_apresentacao": date_only(item.get("dataApresentacao")),
            "situacao": ((f"{st.get('descricaoSituacao') or st.get('descricaoTramitacao') or 'Em tramitação'}"
                          + (f" — {(st.get('despacho') or '')[:200]}" if st.get("despacho") else ""))
                         if detalhe_ok else
                         "Situação não confirmada nesta execução — ver ficha oficial"),
            "regime_tramitacao": st.get("regime"),
            "forma_apreciacao": st.get("apreciacao"),
            "ultima_movimentacao": {"data": last_date, "descricao": last_text[:800]},
            "resumo": ementa,
            "categorias": cats,
            "impacto": {},  # preenchido abaixo
            "documentos": [
                {"titulo": "Ficha de tramitação na Câmara", "url": ficha},
            ] + ([{"titulo": "Inteiro teor", "url": detail.get("urlInteiroTeor")}]
                 if detail.get("urlInteiroTeor") else []),
            "timeline": [{"data": date_only(item.get("dataApresentacao")),
                          "evento": f"Apresentação do {tipo} {numero}/{ano} na Câmara dos Deputados.",
                          "fonte": ficha}],
            "origem": "descoberta_automatica",
            "fonte_descoberta": f"{CAMARA}/proposicoes ({via})",
            "revisao_pendente": True,
            "api_camara": {
                "id_proposicao": pid, "verificado_em": self.run_iso,
                "status_datahora": st.get("dataHora"),
                "descricao_situacao": st.get("descricaoSituacao"),
                "descricao_tramitacao": st.get("descricaoTramitacao"),
                "despacho": st.get("despacho"),
                "sigla_orgao": st.get("siglaOrgao"),
                "keywords": detail.get("keywords"),
            },
        }
        rec["impacto"] = compute_impact_score(rec)
        return rec

    # ------------------------------------------------- descoberta: Senado
    def discover_senado(self, known_keys):
        found = []
        for kw in ("inteligencia artificial", "deepfake", "reconhecimento facial"):
            if BUDGET.expirado():
                break
            for m in senado_search(palavra_chave=kw):
                rel = relevance(f"{m.get('Ementa', '')} {m.get('DescricaoIdentificacao', '')}")
                if not rel:
                    continue
                tipo = (m.get("Sigla") or "").upper()
                if tipo not in TIPOS_INCLUIR and tipo not in TIPOS_REQUERIMENTO:
                    continue
                try:
                    numero = int(str(m.get("Numero")).lstrip("0") or "0")
                    ano = int(str(m.get("Ano")))
                except (TypeError, ValueError):
                    continue
                key = ("senado", tipo, numero, ano)
                if key in known_keys or any(f.get("Codigo") == m.get("Codigo") for f in found):
                    continue
                m["_relevancia"] = rel
                found.append(m)
        if found:
            self._add_fonte("API de Dados Abertos do Senado Federal — descoberta (palavra-chave)")
        return found

    def build_new_senado_record(self, m):
        code = m.get("Codigo")
        det = senado_detail(code) or {}
        dados = det.get("DadosBasicosMateria", {}) or {}
        ident = det.get("IdentificacaoMateria", {}) or {}
        tipo = (m.get("Sigla") or ident.get("SiglaSubtipoMateria") or "").upper()
        numero = int(str(m.get("Numero")).lstrip("0") or "0")
        ano = int(str(m.get("Ano")))
        ficha = f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{code}"
        ementa = dados.get("EmentaMateria") or m.get("Ementa", "")
        # Situação atual via movimentações
        situacao = ("Em tramitação no Senado Federal" if (det or mov)
                    else "Situação não confirmada nesta execução — ver ficha oficial")
        last_date = dados.get("DataApresentacao")
        last_desc = "Apresentação da matéria."
        mov = senado_movimentacoes(code)
        try:
            aut = mov["Autuacoes"]["Autuacao"][0]
            sit = as_list((aut.get("SituacoesAtuais") or {}).get("SituacaoAtual"))[0]
            situacao = sit.get("DescricaoSituacao") or situacao
            infs = as_list((aut.get("InformesLegislativos") or {}).get("InformeLegislativo"))
            if infs:
                md = re.match(r"(\d{4}-\d{2}-\d{2})", infs[0].get("Data") or "")
                if md:
                    last_date = md.group(1)
                last_desc = (infs[0].get("Descricao") or last_desc).strip()[:800]
        except (TypeError, KeyError, IndexError):
            pass
        titulo = (dados.get("ApelidoMateria") or "") or ementa[:140]
        cats = infer_categories(ementa, titulo)
        rec = {
            "id": f"senado_{tipo.lower()}_{numero}_{ano}",
            "tipo": tipo, "numero": numero, "ano": ano,
            "titulo": titulo, "ementa": ementa,
            "casa_origem": "Senado Federal",
            "casa_atual": "Senado Federal",
            "url_oficial": ficha,
            "autor": {"nome": dados.get("Autor") or m.get("Autor", "")},
            "data_apresentacao": date_only(dados.get("DataApresentacao")),
            "situacao": situacao[:400],
            "ultima_movimentacao": {"data": last_date, "descricao": last_desc},
            "resumo": ementa,
            "categorias": cats,
            "impacto": {},
            "documentos": [{"titulo": "Matéria no Senado Federal", "url": ficha}],
            "timeline": [{"data": date_only(dados.get("DataApresentacao")),
                          "evento": f"Apresentação do {tipo} {numero}/{ano} no Senado Federal.",
                          "fonte": ficha}],
            "origem": "descoberta_automatica",
            "fonte_descoberta": f"{SENADO}/materia/pesquisa/lista (palavra-chave)",
            "revisao_pendente": True,
            "api_senado": {"codigo_materia": code, "verificado_em": self.run_iso,
                           "tramitando": ident.get("IndicadorTramitando")},
        }
        rec["impacto"] = compute_impact_score(rec)
        return rec

    # ------------------------------------------------------------- eventos
    def update_events(self, events):
        inicio = self.today
        fim = (self.now + timedelta(days=60)).date().isoformat()
        found = []
        for page in range(1, 4):
            if BUDGET.expirado():
                break
            q = urllib.parse.urlencode({"dataInicio": inicio, "dataFim": fim,
                                        "itens": 100, "pagina": page})
            d = http_get_json(f"{CAMARA}/eventos?{q}")
            polite_pause()
            if not d:
                break
            items = d.get("dados", [])
            if not items:
                break
            for ev in items:
                texto = f"{ev.get('descricao', '')} {ev.get('descricaoTipo', '')}"
                orgaos = " ".join(o.get("apelido", "") or o.get("nome", "") for o in ev.get("orgaos", []))
                if relevance(texto + " " + orgaos):
                    found.append(ev)
            if len(items) < 100:
                break
        self._add_fonte(FONTES_CAMARA[5])
        existing_ids = {e.get("id") for e in events.get("eventos", [])}
        added = 0
        for ev in found:
            eid = f"evt_auto_camara_{ev.get('id')}"
            if eid in existing_ids:
                continue
            di = date_only(ev.get("dataHoraInicio"))
            delta = (datetime.strptime(di, "%Y-%m-%d").date() - self.now.date()).days if di else 999
            janela = "proximos_7_dias" if delta <= 7 else ("proximos_30_dias" if delta <= 30 else "sem_data_confirmada")
            orgaos = ev.get("orgaos", []) or [{}]
            events["eventos"].append({
                "id": eid,
                "titulo": (ev.get("descricaoTipo") or "Evento") + " — " + (ev.get("descricao") or "")[:120],
                "casa": "Câmara dos Deputados",
                "tipo": ev.get("descricaoTipo"),
                "data_inicio": di,
                "data_fim": date_only(ev.get("dataHoraFim")),
                "hora": (ev.get("dataHoraInicio") or "")[11:16] or None,
                "local": ((ev.get("localCamara") or {}).get("nome") or ev.get("localExterno") or "—"),
                "tema": (ev.get("descricao") or "")[:500],
                "relacao_ia": "Detectado automaticamente na agenda oficial (revisão pendente).",
                "janela": janela,
                "fonte_titulo": "API de Dados Abertos da Câmara — Eventos",
                "fonte_url": ev.get("uri") or f"{CAMARA}/eventos/{ev.get('id')}",
                "origem": "descoberta_automatica",
            })
            added += 1
        events["verificacao"] = {
            "data": self.today,
            "fontes_consultadas": [{
                "titulo": "API de Dados Abertos da Câmara dos Deputados — Eventos",
                "url": f"{CAMARA}/eventos?dataInicio={inicio}&dataFim={fim}"}],
            "resultado": (f"{added} novo(s) evento(s) com menção a IA incorporado(s) à agenda; "
                          f"{len(found)} evento(s) relevante(s) no período {inicio}–{fim}."
                          if found else
                          f"Nenhum evento dedicado à temática de IA na agenda oficial da Câmara para {inicio}–{fim}."),
        }
        return added

    # -------------------------------------------------------------- métricas
    @staticmethod
    def _ordinal(data_iso):
        try:
            return datetime.strptime(data_iso, "%Y-%m-%d").toordinal()
        except (TypeError, ValueError):
            return 0

    def _prioridade(self, p):
        """Ordem de verificação: maior score primeiro; em empate, a mais antiga.

        Garante que, se o orçamento acabar, o que ficou de fora são as matérias
        de menor impacto — e que elas sejam as primeiras da execução seguinte.
        """
        score = (p.get("impacto") or {}).get("score") or 0
        dias = -1
        for marca in ((p.get("api_camara") or {}).get("verificado_em"),
                      (p.get("api_senado") or {}).get("verificado_em")):
            d = date_only(marca)
            if d:
                delta = (self.now.date() - datetime.strptime(d, "%Y-%m-%d").date()).days
                dias = max(dias, delta)
        return (-score, -dias)

    @classmethod
    def _prioridade_candidato(cls, cand):
        """Relevância temática > tipo de proposição > mais recente."""
        it, rel, _via = cand
        ordem_rel = {"forte": 0, "media": 1, "infra": 2}.get(rel, 3)
        tipo_ok = 0 if it.get("siglaTipo") in TIPOS_INCLUIR else 1
        return (ordem_rel, tipo_ok, -cls._ordinal(date_only(it.get("dataApresentacao"))))

    def _snapshot_dataset(self, props_all, laws_f, ev_f, up_f):
        """Fotografia do banco ao fim da execução (série histórica do painel)."""
        por_situacao = {}
        for p in props_all:
            t = norm(p.get("situacao") or "")
            if any(k in t for k in ("arquivad", "prejudicad", "retirad")):
                g = "arquivada"
            elif "sancao" in t or "sanção" in t:
                g = "a_sancao"
            elif any(k in t for k in ("transformada em norma", "convertida em norma",
                                      "convertida em lei", "promulgada", "sancionada")):
                g = "aprovada_lei"
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
    def _status_casa(verificadas, falhas):
        """ok · parcial · falha por casa a partir de evidência de consulta.

        A evidência primária é o nº de fichas efetivamente consultadas na casa
        (contadas também quando vêm do cache da execução). Sem nenhuma ficha
        consultada, a casa conta como **falha** — nunca como monitorada.
        """
        if not verificadas:
            return "falha"
        return "parcial" if falhas else "ok"

    def _saude_casas(self):
        """Saúde de Câmara e Senado na mesma estrutura das fontes multiórgão."""
        stats = http_stats()
        por_ep = stats.get("por_endpoint") or {}
        saude = {}
        for casa, base_url, rotulo in (
                ("camara", CAMARA, "Câmara dos Deputados — API de Dados Abertos v2"),
                ("senado", SENADO, "Senado Federal — API de Dados Abertos v7")):
            chamadas = sum(v.get("chamadas", 0) for k, v in por_ep.items()
                           if k.startswith(casa))
            falhas = sum(v.get("falhas", 0) for k, v in por_ep.items()
                         if k.startswith(casa))
            verificadas = self.verificadas_casa.get(casa, 0)
            erros_casa = [e for e in self.errors if e.startswith(f"{casa}_")]
            status_casa = self._status_casa(verificadas, falhas)
            saude[casa] = {
                "nome": rotulo,
                "status": status_casa,
                "ultima_tentativa": self.run_iso,
                "ultima_execucao_ok": self.run_iso if status_casa == "ok" else None,
                "itens_consultados": verificadas,
                "novidades": len([p for p in self.new_props
                                  if str(p.get("id", "")).startswith(casa + "_")]),
                "erros": len(erros_casa),
                "chamadas_http": chamadas,
                "falhas_http": falhas,
                "endpoints": [base_url],
                "canais_ok": [f"{casa}:{k.split(':', 1)[-1]}" for k, v in por_ep.items()
                              if k.startswith(casa) and v.get("chamadas")
                              and not v.get("falhas")][:6],
                "canais_falhos": [f"{casa}:{k.split(':', 1)[-1]}" for k, v in por_ep.items()
                                  if k.startswith(casa) and v.get("falhas")][:6],
                "erro_detalhe": ("; ".join(erros_casa[:3]) or None) if falhas else None,
            }
        # última execução bem-sucedida vem do histórico (nunca estimada)
        anteriores = (load("updates.json").get("execucoes") or [])[1:]
        for casa, dados in saude.items():
            if dados["status"] == "ok":
                continue
            dados["ultima_execucao_ok"] = next(
                ((ex.get("fontes_monitoradas") or {}).get(casa, {}).get("ultima_tentativa")
                 or ex.get("fim") or ex.get("data_hora")
                 for ex in anteriores
                 if ((ex.get("fontes_monitoradas") or {}).get(casa) or {}).get("status") == "ok"),
                None)
        return saude

    def _atualizar_registro(self, rec, n_ev=0):
        rec.update({
            "resumo": (f"Verificação automática: {self.verified} fichas consultadas, "
                       f"{self.updated} proposições atualizadas, {len(self.new_props)} novas, "
                       f"{len(self.changes)} mudanças detectadas, {n_ev} eventos adicionados."),
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
                              f"{len(self.nao_verificadas)} proposição(ões) ficaram para a "
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
        exec_record["proposicoes_monitoradas"] = len(props_all)
        exec_record["proposicoes_pendentes"] = len(self.nao_verificadas)
        exec_record["proposicoes_distintas_verificadas"] = len(self.verificadas_ids)
        # cobertura = proposições distintas verificadas / monitoradas (as refs do
        # Senado podem somar mais de uma consulta por proposição)
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
        print(f"Estado anterior: {len(props)} proposições · última execução: {last_run} · "
              f"orçamento: {BUDGET.limite // 60} min · novas/execução: {MAX_NOVAS} · "
              f"workers: {WORKERS} (HTTP ≤ {HTTP_CONCORRENCIA})", flush=True)

        known_keys = set()
        for p in props:
            casa = "senado" if p["id"].startswith("senado_") else "camara"
            known_keys.add((casa, p.get("tipo"), p.get("numero"), p.get("ano")))

        exec_record = {
            "id": self.run_id,
            "data_hora": self.run_iso,
            "tipo": "atualizacao",
            "status": "em_andamento",
            "motor": {"orcamento_segundos": BUDGET.limite, "max_novas": MAX_NOVAS,
                      "workers": WORKERS, "http_concorrencia": HTTP_CONCORRENCIA},
            "proposicoes_monitoradas": len(props),
            "sugestoes_curadoria": [],
        }
        self._atualizar_registro(exec_record)

        # 1) Atualizar proposições monitoradas (paralelo, I/O-bound; cada thread
        #    toca apenas o seu dict de proposição + estruturas com lock).
        #    A fila é ordenada por prioridade: se o orçamento acabar, o que fica
        #    pendente são as matérias de menor impacto.
        fila = sorted(props, key=self._prioridade)
        if MAX_PROPS and len(fila) > MAX_PROPS:
            self.nao_verificadas = [p["id"] for p in fila[MAX_PROPS:]]
            fila = fila[:MAX_PROPS]
        print(f"Consultando fichas oficiais de {len(fila)} proposições monitoradas...", flush=True)

        def _update_one(p):
            try:
                if p["id"].startswith("senado_"):
                    sen_ok = self.update_senado_refs(p, last_run)
                    if not sen_ok:
                        with self._lock:
                            self.errors.append(f"{p['id']}: não localizada na API do Senado")
                else:
                    cam_ok = self.update_camara_prop(p, last_run)
                    sen_ok = self.update_senado_refs(p, last_run)  # enriquece refs ao Senado
                    if not cam_ok and not sen_ok:
                        with self._lock:
                            self.errors.append(f"{p['id']}: não localizada nas APIs da Câmara e do Senado")
            except BudgetExceeded:
                with self._lock:
                    self.nao_verificadas.append(p["id"])
            except Exception as e:  # noqa: BLE001 - uma proposição não derruba a execução
                with self._lock:
                    self.errors.append(f"{p['id']}: erro inesperado ({e})")
            return p["id"]

        with self.fase("atualizacao_proposicoes"):
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                futures = {pool.submit(_update_one, p): p for p in fila}
                for i, fut in enumerate(as_completed(futures), 1):
                    fut.result()
                    if i % 25 == 0 or i == len(fila):
                        print(f"  [{i}/{len(fila)}] verificadas · {int(BUDGET.decorrido())}s "
                              f"decorridos · {int(BUDGET.restante())}s restantes", flush=True)
        # Ordem determinística das mudanças (mais recentes primeiro)
        self.changes.sort(key=lambda c: (c.get("data", ""), c.get("titulo", "")), reverse=True)
        print(f"Fase 1 concluída em {self.fases.get('atualizacao_proposicoes', 0)}s · "
              f"{self.verified} verificadas · {int(BUDGET.restante())}s de orçamento restantes", flush=True)

        # Checkpoint: grava o resultado da fase 1 antes da descoberta. Se o job
        # for interrompido por qualquer motivo, a verificação já feita não se perde.
        if not dry_run:
            self._atualizar_registro(exec_record)
            self._gravar(props_f, up_f, ev_f, laws_f, tl_f, pm_f, props, exec_record,
                         status="em_andamento")

        # 2) Descobrir novas proposições (com teto por execução: o excedente fica
        #    para a próxima, sempre priorizando relevância temática e recência).
        candidatos_total, adiados = 0, 0
        if BUDGET.expirado(120):
            print("Orçamento insuficiente para a descoberta — etapa adiada.", flush=True)
        else:
            print("Descobrindo novas proposições (Câmara)...", flush=True)
            with self.fase("descoberta_camara"):
                try:
                    cands = [(it, rel, via) for it, rel, via in self.discover_camara(known_keys, last_run)
                             if not (rel == "infra" and it.get("siglaTipo") in TIPOS_REQUERIMENTO)]
                    cands.sort(key=self._prioridade_candidato)
                    candidatos_total = len(cands)
                    uniq, seen = [], set(known_keys)
                    for it, rel, via in cands:
                        key = ("camara", it.get("siglaTipo"), it.get("numero"), it.get("ano"))
                        if key in seen:
                            continue
                        seen.add(key)
                        uniq.append((it, rel, via))
                    adiados = max(0, len(uniq) - MAX_NOVAS)
                    uniq = uniq[:MAX_NOVAS]
                    known_keys.update(("camara", it.get("siglaTipo"), it.get("numero"), it.get("ano"))
                                      for it, _rel, _via in uniq)
                    print(f"  {len(uniq)} candidatas a detalhar"
                          + (f" (+{adiados} adiadas para a próxima execução)" if adiados else ""),
                          flush=True)

                    def _build_cam(args):
                        it, rel, via = args
                        try:
                            return self.build_new_camara_record(it, rel, via)
                        except BudgetExceeded:
                            return None
                        except Exception as e:  # noqa: BLE001
                            with self._lock:
                                self.errors.append(f"nova camara {it.get('id')}: {e}")
                            return None

                    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                        for i, rec in enumerate(pool.map(_build_cam, uniq), 1):
                            if rec is None:
                                continue
                            if any(x["id"] == rec["id"] for x in self.new_props):
                                continue
                            self.new_props.append(rec)
                            self.add_change(
                                data_evento=rec.get("data_apresentacao") or self.today,
                                titulo=f"Nova proposição: {rec['tipo']} {rec['numero']}/{rec['ano']}",
                                descricao=f"{rec['ementa'][:400]} (Registro automático a partir da API oficial; aguardando curadoria.)",
                                tipo="nova proposição", proposicao=rec["id"],
                                fonte="Câmara dos Deputados — API de Dados Abertos",
                                fonte_url=rec["url_oficial"])
                            if i % 10 == 0:
                                print(f"  ...{i}/{len(uniq)} detalhadas", flush=True)
                except BudgetExceeded:
                    print("  orçamento esgotado durante a descoberta (Câmara)", flush=True)
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"descoberta Câmara: {e}")

            desafio_senado = max(0, MAX_NOVAS - len(self.new_props))
            if not BUDGET.expirado(120) and desafio_senado:
                print("Descobrindo novas proposições (Senado)...", flush=True)
                with self.fase("descoberta_senado"):
                    try:
                        matches = self.discover_senado(known_keys)
                        uniqm, seenm = [], set(known_keys)
                        for m in matches:
                            try:
                                numero = int(str(m.get("Numero")).lstrip("0") or "0")
                                ano = int(str(m.get("Ano")))
                            except (TypeError, ValueError):
                                continue
                            key = ("senado", (m.get("Sigla") or "").upper(), numero, ano)
                            if key in seenm:
                                continue
                            seenm.add(key)
                            uniqm.append(m)
                        candidatos_total += len(uniqm)
                        adiados += max(0, len(uniqm) - desafio_senado)
                        uniqm = uniqm[:desafio_senado]
                        known_keys.update(("senado", (m.get("Sigla") or "").upper(),
                                           int(str(m.get("Numero")).lstrip("0") or "0"),
                                           int(str(m.get("Ano")))) for m in uniqm)
                        print(f"  {len(uniqm)} candidatas a detalhar", flush=True)

                        def _build_sen(m):
                            try:
                                return self.build_new_senado_record(m)
                            except BudgetExceeded:
                                return None
                            except Exception as e:  # noqa: BLE001
                                with self._lock:
                                    self.errors.append(f"nova senado {m.get('Codigo')}: {e}")
                                return None

                        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                            for rec in pool.map(_build_sen, uniqm):
                                if rec is None:
                                    continue
                                if any(x["id"] == rec["id"] for x in self.new_props):
                                    continue
                                self.new_props.append(rec)
                                self.add_change(
                                    data_evento=rec.get("data_apresentacao") or self.today,
                                    titulo=f"Nova proposição: {rec['tipo']} {rec['numero']}/{rec['ano']} (Senado)",
                                    descricao=f"{rec['ementa'][:400]} (Registro automático a partir da API oficial; aguardando curadoria.)",
                                    tipo="nova proposição", proposicao=rec["id"],
                                    fonte="Senado Federal — API de Dados Abertos",
                                    fonte_url=rec["url_oficial"])
                    except BudgetExceeded:
                        print("  orçamento esgotado durante a descoberta (Senado)", flush=True)
                    except Exception as e:  # noqa: BLE001
                        self.errors.append(f"descoberta Senado: {e}")

        # 3) Agenda futura
        n_ev = 0
        if BUDGET.expirado(60):
            print("Orçamento insuficiente para a agenda — etapa adiada.", flush=True)
        else:
            print("Atualizando agenda de eventos...", flush=True)
            with self.fase("agenda_eventos"):
                try:
                    n_ev = self.update_events(ev_f)
                except BudgetExceeded:
                    print("  orçamento esgotado na agenda de eventos", flush=True)
                except Exception as e:  # noqa: BLE001
                    self.errors.append(f"eventos: {e}")

        # 3.5) Fontes multiórgão (ANPD, CNJ, TSE, DOU, Planalto, MCTI).
        #      Cada uma roda em subprocesso com timeout próprio: uma fonte
        #      travada/bloqueada não impede as demais nem o build do site.
        resumo_fontes = None
        atos_f = load("atos.json") if os.path.exists(os.path.join(DATA, "atos.json")) else None
        if atos_f is None:
            import update_sources as _us
            atos_f = _us._atos_vazios()
        if os.environ.get("MONITOR_SEM_FONTES"):
            print("Coleta multiórgão desativada por MONITOR_SEM_FONTES.", flush=True)
        elif BUDGET.expirado(90):
            print("Orçamento insuficiente para as fontes multiórgão — etapa adiada.", flush=True)
            exec_record["fontes_multiorgao_adiadas"] = True
        else:
            print("Coletando fontes multiórgão (ANPD, CNJ, TSE, DOU, Planalto, MCTI)...",
                  flush=True)
            with self.fase("fontes_multiorgao"):
                try:
                    import update_sources as _us
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

        # 4) Checagem de conversão em lei (sugestão, sem auto-criar norma)
        sugestoes_lei = []
        for p in props + self.new_props:
            s = norm(p.get("situacao", ""))
            if ("transformada em norma" in s or "convertida" in s) and "lei" in s:
                if not any((p["tipo"] == "PL" and str(p["numero"]) in (l.get("relacao_ia", "") + l.get("ementa_sintese", ""))) for l in laws_f.get("normas", [])):
                    sugestoes_lei.append(p["id"])
        exec_record["sugestoes_curadoria"] = [f"Verificar conversão em lei: {pid}" for pid in sugestoes_lei[:10]]

        # 5) Fechamento e persistência
        exec_record["descoberta_candidatos"] = candidatos_total
        exec_record["descoberta_adiada"] = adiados
        self._atualizar_registro(exec_record, n_ev=n_ev)

        # 5.1) Saúde por fonte: Câmara, Senado e os órgãos multiórgão.
        #      Fonte obrigatória não consultada nunca é reportada como sucesso.
        saude_casas = self._saude_casas()
        fontes_monitoradas = dict(saude_casas)
        if resumo_fontes:
            fontes_monitoradas.update(resumo_fontes["fontes_monitoradas"])
        else:
            for orgao in ("anpd", "cnj", "tse", "dou", "planalto", "mcti"):
                fontes_monitoradas.setdefault(orgao, {
                    "nome": orgao.upper(), "status": "falha",
                    "ultima_tentativa": self.run_iso, "ultima_execucao_ok": None,
                    "itens_consultados": 0, "novidades": 0, "erros": 1,
                    "endpoints": [], "canais_ok": [], "canais_falhos": ["(não executada)"],
                    "erro_detalhe": "coleta multiórgão não executada nesta execução "
                                    "(orçamento de tempo ou desativação explícita)",
                })
        import update_sources as _us
        status_global = _us.calcular_status_global(
            {k: v for k, v in fontes_monitoradas.items()
             if k not in ("camara", "senado")}, saude_casas)
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
        description="Coletor legislativo do Monitor Legislativo de IA (Câmara/Senado).")
    ap.add_argument("--dry-run", action="store_true",
                    help="consulta e relata sem gravar o dataset")
    ap.add_argument("--budget-min", type=float, default=None,
                    help=f"teto de duração da coleta em minutos (padrão: {BUDGET_S / 60:.0f})")
    ap.add_argument("--max-novas", type=int, default=None,
                    help=f"máximo de fichas novas detalhadas por execução (padrão: {MAX_NOVAS})")
    ap.add_argument("--limite", type=int, default=None,
                    help="verificar apenas as N proposições mais prioritárias (padrão: todas)")
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
        print("Descoberta de novas proposições desativada nesta execução (--max-novas 0).", flush=True)
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
