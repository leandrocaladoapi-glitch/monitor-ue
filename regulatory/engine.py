"""engine.py — Módulo 1: Regulatory Impact Engine.

Converte cada item do dataset oficial (normas, procedimentos, atos, agenda e
mudanças detectadas) em um **evento regulatório interpretado** com as onze
respostas exigidas pelo produto:

1. o que mudou · 2. por que importa · 3. quem é afetado · 4. setores ·
5. tipos de empresa · 6. função interna · 7. obrigação/risco/oportunidade ·
8. prazo · 9. ação concreta · 10. evidência oficial · 11. prioridade.

Camadas separadas por construção: `fact` (fato oficial), `analysis` (leitura),
`interpretation` (exposição provável, com limites) e `recommendations`
(recomendação). Nenhum evento é publicado sem URL em domínio oficial; abaixo de
`CONFIDENCE_FLOOR` o item vai para curadoria (`excluded`), nunca para a página.

O motor é determinístico: a mesma entrada produz sempre a mesma saída.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime

from . import content
from . import taxonomy as tx

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(BASE, "data", "legislation-eu")

# --------------------------------------------------------------- fontes oficiais
OFFICIAL_HOSTS = (
    "europa.eu", "eur-lex.europa.eu", "europarl.europa.eu", "consilium.europa.eu",
    "ec.europa.eu", "commission.europa.eu", "digital-strategy.ec.europa.eu",
    "edpb.europa.eu", "edps.europa.eu", "curia.europa.eu", "eba.europa.eu",
    "esma.europa.eu", "eiopa.europa.eu", "enisa.europa.eu", "ema.europa.eu",
    "ecb.europa.eu", "berec.europa.eu", "data.europa.eu", "easa.europa.eu",
    "echa.europa.eu", "efsa.europa.eu", "eurofound.europa.eu", "eib.europa.eu",
    "cnil.fr", "autoriteitpersoonsgegevens.nl", "bfdi.bund.de", "garanteprivacy.it",
    "aepd.es", "dataprotection.ie", "cnpd.public.lu",
)

MONTHS = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"), "dmy"),
]
LONG_DATE = re.compile(
    r"\b(\d{1,2})\s*(?:de\s+)?([a-zçãéíóúâêôA-ZÇÃÉÍÓÚÂÊÔ]{3,12})\.?\s*(?:de\s+)?(\d{4})\b")

# Rótulos de marcos: (padrão, rótulo, é marco de acompanhamento?)
DEADLINE_RULES = [
    (r"aplica[çc][ãa]o das proibi|proibi[çc][õo]es|prohibited practices|prohibitions", "Aplicação das proibições", True),
    (r"modelos de uso geral|obriga[çc][õo]es para (os )?modelos|\bgpai\b|general[- ]purpose ai", "Obrigações para modelos de uso geral (GPAI)", True),
    (r"anexo iii|annex iii", "Obrigações de alto risco — Anexo III", True),
    (r"anexo i\b|annex i\b", "Obrigações de alto risco — Anexo I", True),
    (r"entrada em vigor|em vigor desde|entered into force|in force since", "Entrada em vigor", True),
    (r"in[íi]cio de aplica[çc][ãa]o|aplica[çc][ãa]o geral|aplica-se a partir|applies from", "Início de aplicação das obrigações", True),
    (r"publica[çc][ãa]o no (jo|jornal oficial)|published in the official journal|jornal oficial", "Publicação no Jornal Oficial", True),
    (r"fecho do per[íi]odo|fim do per[íi]odo de feedback|feedback period|end of the feedback", "Fecho do período de feedback oficial", False),
    (r"abertura do per[íi]odo|in[íi]cio do per[íi]odo|start of the feedback|abre em", "Abertura do período de feedback", False),
    (r"prazo para (coment|contribui)|coment[áa]rios at[ée]|at[ée] .{0,20}(comentar|contribuir)|"
     r"deadline for (comments|submissions)|comments? (by|until)|submissions? (by|until)|contribui[çc][õo]es",
     "Prazo para contribuições (consulta pública)", False),
    (r"orienta[çc][õo]es|guidelines|guidance|recomenda[çc][õo]es", "Publicação de orientações", False),
    (r"revis[ãa]o|review (by|clause|report)|avalia[çc][ãa]o (a ser|prevista)|evaluation by",
     "Revisão / avaliação prevista", True),
    (r"save the date|stakeholder event|evento|workshop|webinar|conference|info session|hearing",
     "Evento oficial — data publicada", False),
    (r"ado[çc][ãa]o|adopted on|adoption", "Adoção do ato", False),
]
DEADLINE_FALLBACK = "Data referida no texto oficial"

ACT_TYPE_RULES = [
    (r"\benforcement\b|fines?|sanction|multa|penalt|decision following inquiry", "enforcement"),
    (r"guideline|orienta[çc][ãa]o|guidance|recommendation|parecer|opinion", "guideline"),
    (r"code of practice|c[óo]digo de (pr[áa]tica|conduta)", "code_of_practice"),
    (r"call for evidence|consulta|consultation|have your say|feedback", "consultation"),
    (r"delegated regulation|regulamento delegado", "delegated_act"),
    (r"implementing regulation|regulamento de execu[çc][ãa]o", "implementing_act"),
    (r"directive|diretiva", "directive"),
    (r"resolution|resolu[çc][ãa]o|own[- ]initiative|\bini\b", "resolution"),
    (r"judgment|ac[óo]rd[ãa]o|preliminary ruling|tribunal", "judicial"),
    (r"speech|discours|discurso|declara[çc][ãa]o|statement|remarks", "communication"),
    (r"report|relat[óo]rio|study|estudo", "report"),
    (r"proposal|proposta|com/\d{4}|\bcod\b", "procedure"),
    (r"decision|decis[ãa]o", "decision"),
    (r"regulation|regulamento", "regulation"),
    (r"communication|comunicado", "communication"),
]


# ------------------------------------------------------------------ utilidades
def norm_text(text: str) -> str:
    return tx.norm_text(text)


def official_source(url: str) -> str | None:
    """Devolve o host quando a URL é de domínio oficial; caso contrário, None."""
    if not url or not str(url).startswith(("http://", "https://")):
        return None
    host = re.sub(r"^https?://", "", str(url)).split("/")[0].lower().split(":")[0]
    for allowed in OFFICIAL_HOSTS:
        if host == allowed or host.endswith("." + allowed):
            return host
    return None


def _uid(text: str, limit: int = 56) -> str:
    base = tx.slug(text, limit + 6)
    if len(base) < limit:
        return base
    return base[:limit].rstrip("-") + "-" + hashlib.sha1((text or "").encode()).hexdigest()[:6]


def _slug(text: str, limit: int = 60) -> str:
    return tx.slug(text, limit)


def _iso(year, month, day) -> str | None:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return None


def extract_dates(text: str) -> list[str]:
    """Datas explícitas no texto oficial (ISO, DD/MM/AAAA, DD.MM.AAAA e por extenso)."""
    out: list[str] = []
    if not text:
        return out
    for pattern, kind in DATE_PATTERNS:
        for match in pattern.finditer(text):
            if kind == "iso":
                iso = _iso(match.group(1), match.group(2), match.group(3))
            else:
                iso = _iso(match.group(3), match.group(2), match.group(1))
            if iso and iso not in out:
                out.append(iso)
    for match in LONG_DATE.finditer(text):
        month = MONTHS.get(norm_text(match.group(2)))
        if month:
            iso = _iso(match.group(3), month, match.group(1))
            if iso and iso not in out:
                out.append(iso)
    return sorted(out)


def _label_before(text: str, index: int, window: int = 90) -> tuple[str, bool]:
    """Rótulo do marco a partir do trecho imediatamente anterior à data."""
    trecho = text[max(0, index - window):index]
    best = None
    for pattern, label, tracker in DEADLINE_RULES:
        matches = list(re.finditer(pattern, trecho, re.I))
        if matches:
            position = matches[-1].start()
            if best is None or position > best[0]:
                best = (position, label, tracker)
    if best:
        return best[1], best[2]
    return DEADLINE_FALLBACK, False


def deadlines_from_text(text: str, source_url: str, source_title: str = "") -> list[dict]:
    """Prazos explícitos do texto oficial, com rótulo, fonte e marca de acompanhamento."""
    out, seen = [], set()
    if not text:
        return out
    for pattern, kind in DATE_PATTERNS:
        for match in pattern.finditer(text):
            if kind == "iso":
                iso = _iso(match.group(1), match.group(2), match.group(3))
            else:
                iso = _iso(match.group(3), match.group(2), match.group(1))
            if not iso or iso in seen:
                continue
            seen.add(iso)
            label, tracker = _label_before(text, match.start())
            out.append({"date": iso, "label": label, "tracker": tracker,
                        "source_title": source_title, "source_url": source_url,
                        "basis": "Data escrita no texto oficial preservado no dataset."})
    for match in LONG_DATE.finditer(text):
        month = MONTHS.get(norm_text(match.group(2)))
        iso = _iso(match.group(3), month, match.group(1)) if month else None
        if not iso or iso in seen:
            continue
        seen.add(iso)
        label, tracker = _label_before(text, match.start())
        out.append({"date": iso, "label": label, "tracker": tracker,
                    "source_title": source_title, "source_url": source_url,
                    "basis": "Data escrita no texto oficial preservado no dataset."})
    out.sort(key=lambda item: item["date"])
    return out


def reference_date(dataset: dict | None = None) -> date:
    """Data de referência do produto: a data da execução registrada no dataset."""
    dataset = dataset or {}
    for execution in (dataset.get("updates", {}).get("execucoes") or []):
        value = (execution or {}).get("data") or ""
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            continue
    meta = (dataset.get("updates", {}).get("meta") or {})
    value = meta.get("execucao") or ""
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.today()


def load(data_dir: str, name: str) -> dict:
    path = os.path.join(data_dir, name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------------ detecções
def _hits(text: str, patterns) -> int:
    low = text
    return sum(1 for pattern in patterns if re.search(pattern, low, re.I | re.S))


def detect_themes(text: str) -> list[str]:
    scored = []
    for key, meta in tx.THEMES.items():
        score = _hits(text, meta.get("keywords", []))
        if score:
            scored.append((key, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [key for key, _ in scored]


def detect_flags(text: str) -> list[str]:
    flags = [key for key, patterns in tx.FLAG_KEYWORDS.items() if _hits(text, patterns)]
    order = list(tx.FLAGS)
    return sorted(flags, key=lambda flag: order.index(flag) if flag in order else 99)


def detect_sector_exposure(text: str, themes) -> list[dict]:
    """Setores expostos: evidência textual (explicit) + leitura temática (thematic)."""
    exposure: list[dict] = []
    for slug, meta in tx.SECTORS.items():
        score = _hits(text, meta.get("keywords", []))
        if score:
            exposure.append({"slug": slug, "name": meta["name"],
                             "why": "Termo do item oficial relacionado ao setor.",
                             "basis": "explicit", "score": score})
    explicit = {item["slug"] for item in exposure}
    if len(explicit) < 3:
        for theme in themes:
            for slug in tx.THEMES.get(theme, {}).get("sectors", []):
                if slug in explicit or slug not in tx.SECTORS:
                    continue
                explicit.add(slug)
                exposure.append({
                    "slug": slug, "name": tx.SECTORS[slug]["name"],
                    "why": f"Tema «{tx.theme_label(theme)}» afeta tipicamente este setor.",
                    "basis": "thematic", "score": 0})
    exposure.sort(key=lambda item: (-item["score"], item["name"]))
    return [{k: v for k, v in item.items() if k != "score"} for item in exposure][:8]


def detect_company_types(themes, sector_exposure) -> list[str]:
    out: list[str] = []
    for theme in themes:
        for key in tx.THEME_COMPANY_TYPES.get(theme, []):
            if key in tx.COMPANY_TYPES and key not in out:
                out.append(key)
    for item in sector_exposure:
        for key in content.SECTOR_COMPANY_TYPES.get(item["slug"], []):
            if key in tx.COMPANY_TYPES and key not in out:
                out.append(key)
    return out[:8]


def detect_functions(themes, sector_exposure) -> list[str]:
    keys: list[str] = []
    for theme in themes:
        keys += tx.THEMES.get(theme, {}).get("functions", [])
    for item in sector_exposure:
        keys += content.SECTOR_FUNCTIONS.get(item["slug"], [])
    out: list[str] = []
    for key in keys:
        canonical = tx.normalize_function(key)
        if canonical and canonical not in out:
            out.append(canonical)
    return out[:8] or ["regulatory-affairs", "legal"]


def detect_act_type(tipo: str, titulo: str, descricao: str, fonte: str, kind: str) -> str:
    blob = norm_text(" ".join([tipo or "", titulo or "", descricao or "", fonte or ""]))
    if kind == "agenda":
        return "consultation"
    if kind == "norma":
        if "diretiva" in blob or "directive" in blob:
            return "directive"
        return "regulation"
    if kind == "procedimento":
        return "procedure"
    if tipo and norm_text(tipo) in tx.ACT_TYPES:
        return norm_text(tipo)
    for pattern, act_type in ACT_TYPE_RULES:
        if re.search(pattern, blob, re.I):
            return act_type
    return "other"


def detect_stage(kind: str, texto: str) -> str:
    blob = norm_text(texto)
    if kind == "agenda":
        return "consulta"
    if re.search(r"em vigor|in force|applicable from|aplic[áa]vel desde", blob):
        return "em_vigor"
    if re.search(r"votad|adopted|aprovad|plen[áa]rio|plenary", blob):
        return "plenario"
    if re.search(r"ado[çc][ãa]o|adopted", blob):
        return "adotado"
    if re.search(r"tr[íi]logo|negocia|negotiat", blob):
        return "negociacao"
    if re.search(r"proposal|proposta|com/\d{4}", blob):
        return "proposta"
    if re.search(r"call for evidence|consulta|consultation|feedback period", blob):
        return "consulta"
    if re.search(r"committee|comiss[ãa]o|parecer|opinion|rapporteur|relator", blob):
        return "parecer"
    return "nao_classificado"


def detect_regulator(record: dict, fonte: str, url: str) -> str:
    orgao = norm_text(record.get("orgao") or "")
    if orgao:
        for key, meta in tx.REGULATORS.items():
            if norm_text(meta["name"]) == orgao:
                return key
    alias = tx.REGULATOR_ALIASES.get(orgao)
    if alias:
        return alias
    blob = norm_text(" ".join([orgao, fonte or "", url or ""]))
    if "edpb" in blob:
        return "edpb"
    if "edps" in blob:
        return "edps"
    if "curia" in blob or "court of justice" in blob:
        return "curia"
    if "europarl" in blob or "parlamento" in blob:
        return "eu_parliament"
    if "consilium" in blob or "conselho" in blob:
        return "eu_council"
    if "ai office" in blob:
        return "ai_office"
    if "eur-lex" in blob or "eurlex" in blob or "eur-lex.europa.eu" in (url or ""):
        return "eurlex"
    if "cnil" in blob or "data protection commission" in blob or "dpa" in blob:
        return "national_dpa"
    if "ec.europa.eu" in (url or "") or "commission" in blob or "comiss" in blob:
        return "eu_commission"
    return "other"


# ------------------------------------------------------------------ prioridade
THEME_WEIGHTS = {
    "enforcement": 30, "gpai": 18, "ai_act": 17, "edpb": 14, "dsa": 12, "ai_office": 12,
    "cybersecurity": 12, "health_data": 12, "consultation": 12, "competition": 10,
    "consumer": 10, "employment": 10, "copyright": 8, "data_act": 8, "ai_liability": 8,
    "edps": 6, "judicial": 6, "public_sector": 6, "funding_innovation": 4,
}
ACT_TYPE_WEIGHTS = {
    "enforcement": 18, "regulation": 14, "directive": 14, "guideline": 12, "decision": 10,
    "implementing_act": 8, "delegated_act": 8, "consultation": 8, "code_of_practice": 8,
    "procedure": 6, "judicial": 6, "resolution": 4, "opinion": 4, "communication": 2,
    "report": 2, "other": 0,
}
STAGE_WEIGHTS = {"em_vigor": 4, "adotado": 3, "plenario": 2, "parecer": 2, "consulta": 2}
FLAG_WEIGHTS = {"penalty": 8, "prohibited": 8, "high_risk": 6, "minors": 4, "gpai": 2,
                "consultation": 2}


def impact_score(themes, sector_exposure, act_type, stage, flags, deadlines, today,
                 reference: date, confidence: float | None = None) -> int:
    """Rúbrica reproduzível de impacto (0–100). Nenhum fator é subjetivo."""
    score = 28
    score += max([THEME_WEIGHTS.get(theme, 4) for theme in themes] or [0])
    score += ACT_TYPE_WEIGHTS.get(act_type, 0)
    score += STAGE_WEIGHTS.get(stage, 0)
    score += sum(FLAG_WEIGHTS.get(flag, 0) for flag in flags)
    explicit = [item for item in sector_exposure if item.get("basis") == "explicit"]
    score += min(6, len(explicit))
    future_days = sorted(
        (date.fromisoformat(item["date"]) - today).days for item in deadlines or []
        if item.get("date") and date.fromisoformat(item["date"]) >= today)
    if future_days:
        nearest = future_days[0]
        score += 8 if nearest <= 90 else 6 if nearest <= 180 else 3 if nearest <= 400 else -3
    else:
        score -= 3  # calendário inteiramente passado/sem prazo aplicável
    if reference:
        delta = abs((reference - today).days)
        score += 6 if delta <= 180 else 3 if delta <= 365 else 0
    if confidence is not None and confidence <= tx.CONFIDENCE["probable"]:
        score -= 2
    return max(0, min(100, score))


# ------------------------------------------------------------- composição
def _confidence_of(record: dict, kind: str) -> float:
    if record.get("revisao_pendente"):
        return tx.CONFIDENCE["probable"]
    if str(record.get("relevancia") or "").strip().lower() == "revisar":
        return tx.CONFIDENCE["probable"]
    if kind == "ato" and not (record.get("descricao") or "").strip():
        return tx.CONFIDENCE["probable"]
    return tx.CONFIDENCE["supported"]


def _confidence_label(value: float, curated: bool = False) -> str:
    if curated:
        return tx.CONFIDENCE_LABELS["unpublished"]
    if value >= tx.CONFIDENCE["confirmed"]:
        return tx.CONFIDENCE_LABELS["confirmed"]
    if value >= tx.CONFIDENCE["supported"]:
        return tx.CONFIDENCE_LABELS["supported"]
    return tx.CONFIDENCE_LABELS["probable"]


def _obligations_for(themes) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for theme in themes:
        for text in tx.THEME_OBLIGATIONS.get(theme, []):
            item = (text, tx.theme_label(theme))
            if item not in out:
                out.append(item)
    return out[:6]


def _risks_for(themes) -> list[str]:
    out: list[str] = []
    for theme in themes:
        for text in tx.THEME_RISKS.get(theme, []):
            if text not in out:
                out.append(text)
    return out[:6]


def _opportunities_for(themes) -> list[str]:
    out: list[str] = []
    for theme in themes:
        for text in tx.THEME_OPPORTUNITIES.get(theme, []):
            if text not in out:
                out.append(text)
    return out[:5]


def _actions_for(themes) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for theme in themes:
        for text, owner, priority in tx.THEME_ACTIONS.get(theme, []):
            owner = tx.normalize_function(owner) or "regulatory-affairs"
            item = (text, tx.theme_label(theme), owner, priority)
            if item not in out:
                out.append(item)
    return out[:6]


def _date_label(kind: str, record: dict) -> str:
    if kind == "agenda":
        return "Abertura do período de feedback"
    if kind == "norma":
        return "Publicação no Jornal Oficial"
    if kind == "procedimento":
        return "Data registada no procedimento oficial"
    tipo = norm_text(record.get("tipo") or "")
    if "enforcement" in tipo or "sanction" in tipo:
        return "Data da decisão oficial"
    return "Data do item na fonte oficial"


def _short_title(titulo: str, limit: int = 150) -> str:
    title = re.sub(r"\s+", " ", titulo or "").strip()
    if len(title) <= limit:
        return title
    return title[:limit].rsplit(" ", 1)[0] + "…"


def _norm_label(record: dict) -> str:
    tipo = record.get("tipo") or "Norma"
    relacao = record.get("relacao_ia") or record.get("nome") or ""
    if "Digital Omnibus" in relacao:
        return f"{tipo} — Digital Omnibus on AI"
    if re.search(r"ai act|intelig[êe]ncia artificial", relacao, re.I):
        return f"{tipo} — AI Act"
    return f"{tipo} — norma de referência"


# ------------------------------------------------ relação material (M1/escopo)
# Regra do produto: só entra o que tem relação material com IA, dados,
# plataformas digitais ou infraestrutura digital. O resto é descartado com
# registro auditável (nunca publicado).
MATERIAL_THEMES = set(tx.THEMES) - {"consultation", "public_sector", "funding_innovation"}
MATERIAL_PATTERNS = [
    r"\bartificial intelligence\b", r"intelig[êe]ncia artificial", r"\balgorithm", r"\bchatbot\b",
    r"\bmachine learning\b", r"\bautomat(ed|ic|ion)\b", r"\bmode(l|lo)s? de (ia|linguagem|funda)",
    r"\bdata protection\b", r"prote[cç][ãa]o de dados", r"\bpersonal data\b",
    r"\bdados pessoais\b", r"\bgdpr\b", r"\brgpd\b", r"\bprivacidade\b", r"\bcookie",
    r"\bonline platform", r"\bdigital platform", r"\bplatform (economy|work|services?)\b",
    r"\bmarketplace\b", r"\bcloud\b", r"\bsaas\b", r"\bsoftware\b", r"\bcyber",
    r"\bdata cent", r"centros? de dados", r"\bsemiconductor", r"\binternet\b",
    r"\bonline advertising\b", r"\bdigital services\b", r"\bdigital markets\b",
    r"\bhigh[- ]risk\b", r"\balto risco\b", r"\bdeepfake", r"\bgenerative\b",
]
# Siglas: exigem caixa alta no texto bruto (evita falsos positivos como "j'ai").
MATERIAL_ACRONYMS = [r"\bAI\b", r"\bIA\b", r"\bGPAI\b", r"\bLLM\b"]


def material_relation(event: dict) -> tuple[bool, str]:
    """Diz se o item tem relação material com IA/dados/digital e por quê."""
    themes = [theme for theme in (event.get("themes") or []) if theme in MATERIAL_THEMES]
    if themes:
        return True, "tema material: " + ", ".join(tx.theme_label(theme) for theme in themes[:3])
    raw = " ".join([event.get("regulatory_event") or "", event.get("summary") or ""])
    if any(re.search(pattern, raw) for pattern in MATERIAL_ACRONYMS):
        return True, "sigla de IA/dados no texto oficial"
    blob = norm_text(raw)
    for pattern in MATERIAL_PATTERNS:
        if re.search(pattern, blob):
            return True, "termo material no texto oficial"
    return False, "sem relação material com IA, dados, plataformas ou infraestrutura digital"


def _event_id(kind: str, record: dict, titulo: str) -> str:
    if kind == "norma":
        return "re_norma_" + _slug(record.get("id") or record.get("celex") or titulo, 60)
    if kind == "procedimento":
        return "re_procedimento_" + _slug(record.get("id") or titulo, 60)
    if kind == "agenda":
        return "re_agenda_" + _slug(record.get("id") or titulo, 60)
    if kind == "mudanca":
        return "re_mudanca_" + _uid(record.get("item") or titulo)
    return "re_ato_" + _uid(record.get("id") or titulo)


def build_event(record: dict, kind: str, reference: date, today: date) -> dict | None:
    """Transforma um registro oficial em evento interpretado (ou None se inválido)."""
    if kind == "norma":
        titulo = _norm_label(record)
        oficial = re.sub(r"\s+", " ", record.get("nome") or "")
        texto = " ".join(filter(None, [oficial, record.get("relacao_ia"),
                                       record.get("status"), record.get("jornal_oficial")]))
        source_url = record.get("url") or record.get("url_consolidada") or ""
        source_id = record.get("id") or record.get("celex") or titulo
        change_date = record.get("data")
    else:
        titulo = re.sub(r"\s+", " ", record.get("titulo") or record.get("nome") or "").strip()
        texto = " ".join(filter(None, [titulo, record.get("descricao"), record.get("ementa"),
                                       record.get("resumo"), record.get("situacao"),
                                       record.get("tema"), record.get("relacao_ia"),
                                       record.get("proximo_passo")]))
        source_url = (record.get("url_oficial") or record.get("fonte_url") or record.get("url")
                      or record.get("url_consolidada") or "")
        source_id = record.get("id") or titulo
        change_date = record.get("data") or record.get("data_apresentacao") or record.get("data_inicio")
    if not titulo or not official_source(source_url):
        return None

    blob = norm_text(texto)
    themes = detect_themes(blob)
    flags = detect_flags(blob)
    exposure = detect_sector_exposure(blob, themes)
    company_types = detect_company_types(themes, exposure)
    functions = detect_functions(themes, exposure)
    act_type = detect_act_type(record.get("tipo") or record.get("tipo_ato") or "",
                              titulo, record.get("descricao") or "", record.get("fonte") or "", kind)
    stage = detect_stage(kind, texto)
    regulator_key = detect_regulator(record, record.get("fonte") or "", source_url)
    confidence = _confidence_of(record, kind)
    curated = bool(record.get("revisao_pendente"))

    source_title = oficinal_title = titulo if kind != "norma" else (record.get("nome") or titulo)
    deadlines = deadlines_from_text(texto, source_url, source_title)
    if kind == "agenda":
        deadlines = [item for item in deadlines if item.get("tracker")] or deadlines
        if record.get("data_fim"):
            deadlines = [item for item in deadlines if item["date"] == record["data_fim"]] or [
                {**item, "tracker": True} for item in deadlines]
    for item in deadlines:
        item["days_remaining"] = (date.fromisoformat(item["date"]) - today).days

    score = impact_score(themes, exposure, act_type, stage, flags, deadlines, today,
                         date.fromisoformat(change_date) if change_date else None, confidence)
    impact_level = tx.impact_level_for(score)
    priority = tx.priority_for(score)

    obligations = _obligations_for(themes)
    risks = _risks_for(themes)
    opportunities = _opportunities_for(themes)
    actions = _actions_for(themes)
    sector_names = [item["name"] for item in exposure]
    function_labels = [tx.function_name(key) for key in functions]
    hedge = ("Potencialmente afetada. A aplicabilidade depende das atividades exercidas e "
             "requer avaliação jurídica específica.")

    next_step = actions[0][0] if actions else "Avaliar aplicabilidade com o jurídico da empresa."
    consequence = ("Na prática, isto altera expectativas sobre como a organização documenta, avalia e "
                   f"supervisiona o uso de IA em {', '.join(sector_names[:3])}."
                   if sector_names else
                   "Na prática, isto altera expectativas sobre como a organização documenta, avalia e "
                   "supervisiona o uso de IA em processos ainda a identificar.")
    sla = {"urgent": "agir em dias", "high": "agir em semanas",
           "medium": "planejar no trimestre", "monitor": "acompanhar"}[priority]

    event = {
        "id": _event_id(kind, record, titulo),
        "regulatory_event": titulo,
        "summary": _short_title(record.get("descricao") or record.get("resumo")
                               or record.get("ementa") or record.get("relacao_ia") or titulo, 400),
        "affected_sectors": sector_names,
        "affected_company_types": [tx.COMPANY_TYPES[key] for key in company_types],
        "affected_functions": function_labels,
        "obligations": [text for text, _ in obligations],
        "deadlines": [{"date": item["date"], "label": item["label"],
                       "days_remaining": item["days_remaining"]} for item in deadlines],
        "risks": risks,
        "opportunities": opportunities,
        "recommended_actions": [text for text, _, _, _ in actions],
        "impact_level": impact_level,
        "priority": priority,
        "confidence": confidence,
        "official_sources": [source_url],
        "source_kind": kind,
        "source_id": source_id,
        "territory": "União Europeia",
        "regulator": tx.REGULATORS[regulator_key]["name"],
        "regulator_key": regulator_key,
        "act_type": act_type,
        "act_type_label": tx.ACT_TYPES.get(act_type, act_type),
        "stage": stage,
        "stage_label": tx.STAGES.get(stage, stage),
        "change_date": change_date,
        "publication_date": record.get("data") if kind == "norma" else None,
        "entry_into_force": next((item["date"] for item in deadlines
                                  if item["label"] == "Entrada em vigor"), None),
        "compliance_deadline": next((item["date"] for item in deadlines if item["tracker"]
                                     and item["days_remaining"] >= 0), None),
        "themes": themes,
        "theme_labels": [tx.theme_label(theme) for theme in themes],
        "flags": flags,
        "impact_score": score,
        "confidence_label": _confidence_label(confidence, curated),
        "requires_legal_review": True,
        "hedge": hedge,
        "watchlist_tags": sorted({*[item["slug"] for item in exposure], *themes, act_type}),
        "fact": {
            "title": titulo,
            "description": _short_title(record.get("descricao") or record.get("resumo")
                                        or record.get("ementa") or record.get("relacao_ia")
                                        or record.get("status") or titulo, 700),
            "date": change_date,
            "date_label": _date_label(kind, record),
            "regulator": tx.REGULATORS[regulator_key]["name"],
            "source_url": source_url,
            "sources": _fact_sources(record, kind, titulo, source_url),
            "note": "Texto e data preservados do item do dataset; nenhum fato foi acrescentado.",
        },
        "analysis": {
            "why_it_matters": _why_it_matters(themes, exposure, act_type, kind),
            "sector_exposure": exposure,
            "obligations": [{
                "text": text,
                "reference": reference,
                "basis": _basis_for(record, source_url),
                "applies_if": "Requer avaliação jurídica específica do caso de uso.",
                "confidence": confidence,
            } for text, reference in obligations],
            "risks": [{"text": text, "event_id": None, "confidence": confidence} for text in risks],
            "opportunities": [{"text": text, "confidence": confidence} for text in opportunities],
            "confidence": confidence,
        },
        "interpretation": {
            "text": (f"Exposição provável em: {', '.join(sector_names[:4])}. {hedge}"
                     if sector_names else f"Setores ainda não determinados. {hedge}"),
            "company_types": company_types,
            "functions": functions,
            "flags": flags,
            "confidence": confidence,
            "limits": ("Classificação por palavras-chave e tema. Não estabelece que qualquer "
                       "organização específica esteja juridicamente enquadrada no ato."),
        },
        "recommendations": {
            "actions": [{"text": text, "theme": reference, "owner_function": owner,
                         "priority": priority_label} for text, reference, owner, priority_label in actions],
            "priority": priority,
            "sla": sla,
            "owner_functions": functions,
            "next_step": next_step,
        },
        "so_what": {
            "consequence": consequence,
            "functions": function_labels,
            "possible_costs": ("Custo de adequação não quantificado pelo monitor: depende do número "
                               "de sistemas afetados, da obrigação aplicável e do desenho do controlo."),
            "adaptation_needed": ("Provável necessidade de adequação em documentação, contratos ou "
                                  "controlos internos quando a obrigação se confirmar aplicável."
                                  if impact_level in ("critical", "high") else
                                  "Adequação recomendada: revisão de política, contratos e registos internos."),
            "risk_of_inaction": risks[0] if risks else "Perder prazo interno e aumentar custo de remediação.",
            "next_step": next_step,
        },
        "diff": _diff_of(record),
        "changes_summary": (record.get("tipo") if kind == "mudanca" else None),
        "published": True,
        "relevance": record.get("relevancia"),
    }
    if kind == "norma":
        event["law_meta"] = {
            "tipo": record.get("tipo"), "numero": record.get("numero"), "celex": record.get("celex"),
            "jornal_oficial": record.get("jornal_oficial"), "procedimento": record.get("procedimento"),
            "status": record.get("status"),
        }
    event["deadlines_full"] = [
        {**item,
         "days_remaining": item["days_remaining"],
         "basis": item.get("basis") or "Data escrita no texto oficial preservado no dataset."}
        for item in deadlines]
    if event["id"] == _event_id(kind, record, titulo) and len(event["deadlines_full"]) != len(
            {item["date"] for item in event["deadlines_full"]}):
        return None
    return event


def _fact_sources(record, kind, titulo, source_url) -> list[dict]:
    sources = [{"title": titulo, "url": source_url, "type": "fonte primária", "official": True}]
    consolidated = record.get("url_consolidada")
    if consolidated and consolidated != source_url:
        sources.append({"title": f"Versão consolidada ({record.get('celex') or titulo})",
                        "url": consolidated, "type": "versão consolidada", "official": True})
    for extra in record.get("fontes_adicionais") or []:
        if isinstance(extra, dict) and extra.get("url"):
            sources.append({"title": extra.get("nome") or extra.get("titulo") or "Fonte adicional",
                            "url": extra["url"], "type": "fonte adicional",
                            "official": bool(official_source(extra["url"]))})
    return sources


def _basis_for(record, source_url) -> str:
    blob = norm_text(" ".join([str(record.get("titulo") or record.get("nome") or ""),
                               str(record.get("descricao") or record.get("relacao_ia") or "")]))
    found = [name for name, meta in tx.THEMES.items()
             if any(re.search(pattern, blob, re.I) for pattern in meta.get("keywords", [])[:3])]
    if found:
        return "Fonte menciona: " + ", ".join(tx.theme_label(key) for key in found[:3]).lower()
    return "Obrigação da biblioteca pública do produto aplicada ao tema classificado."


def _why_it_matters(themes, exposure, act_type, kind) -> str:
    theme_text = ", ".join(tx.theme_label(theme) for theme in themes[:3]) or "regulação digital"
    if kind == "agenda":
        return (f"Leitura: consulta pública em {theme_text} — janela de influência com prazo oficial, "
                f"relevante para equipas de assuntos públicos e conformidade.")
    if kind == "norma":
        return (f"Leitura: ato vinculante classificado como {theme_text}, com calendário de aplicação "
                f"faseado que desloca obrigações de documentação, transparência ou controlo interno.")
    return (f"Leitura: o item é classificado como {theme_text}, o que normalmente desloca obrigações de "
            f"documentação, transparência ou controlo interno para as equipas responsáveis.")


def _diff_of(record) -> dict | None:
    campo = record.get("campo_alterado")
    if not campo:
        return None
    return {
        "field": campo,
        "change_type": record.get("tipo") or "alteração de texto",
        "previous": record.get("valor_anterior"),
        "current": record.get("valor_novo"),
        "note": ("Comparação por impressão digital (hash) do texto oficial detectado na coleta. "
                 "O conteúdo integral permanece na fonte oficial citada; nenhuma versão é reconstruída."),
    }


# ------------------------------------------------------------------- build
def build_events(data_dir: str | None = None) -> dict:
    """Gera os eventos publicados e os excluídos (abaixo do piso de confiança)."""
    data_dir = data_dir or DEFAULT_DATA
    dataset = {name: load(data_dir, f"{name}.json")
               for name in ("propositions", "laws", "atos", "events", "updates", "categories")}
    today = reference_date(dataset)
    reference = today
    published: list[dict] = []
    excluded: list[dict] = []
    skipped: list[dict] = []
    seen_ids: set[str] = set()
    seen_keys: set[tuple] = set()

    def add(event: dict | None):
        if not event:
            return
        if event["confidence"] < tx.CONFIDENCE_FLOOR:
            excluded.append({**event, "published": False})
            return
        relevant, reason = material_relation(event)
        if not relevant:
            skipped.append({
                "id": event["id"], "regulatory_event": event["regulatory_event"],
                "confidence": event["confidence"], "official_sources": event["official_sources"],
                "reason": reason,
            })
            return
        key = (event["official_sources"][0], event["regulatory_event"])
        if event["id"] in seen_ids or key in seen_keys:
            return
        seen_ids.add(event["id"])
        seen_keys.add(key)
        published.append(event)

    for record in (dataset["laws"].get("normas") or []):
        add(build_event(record, "norma", reference, today))
    for record in (dataset["propositions"].get("proposicoes") or []):
        add(build_event(record, "procedimento", reference, today))
    for record in (dataset["atos"].get("atos") or []):
        add(build_event(record, "ato", reference, today))
    for record in (dataset["events"].get("eventos") or []):
        add(build_event(record, "agenda", reference, today))

    # Mudanças: deduplicadas por (título, data) e publicadas apenas quando o item
    # não está no conjunto corrente de atos/proposições (mudança fora da janela).
    known_ids = {record.get("id") for record in (dataset["atos"].get("atos") or [])}
    known_ids |= {record.get("id") for record in (dataset["propositions"].get("proposicoes") or [])}
    bookkeeping = {"atualização cadastral", "votação", "novo procedimento", "alteração de status"}
    seen_changes = set()
    for change in (dataset["updates"].get("mudancas") or []):
        key = (change.get("titulo"), change.get("data"))
        if key in seen_changes:
            continue
        seen_changes.add(key)
        if change.get("tipo") in bookkeeping:
            continue
        if change.get("item") in known_ids:
            continue
        add(build_event(change, "mudanca", reference, today))

    published.sort(key=lambda item: (item["impact_score"], item.get("change_date") or ""), reverse=True)
    return {"published": published, "excluded": excluded, "skipped": skipped,
            "reference_date": today.isoformat(),
            "total": len(published) + len(excluded) + len(skipped)}
