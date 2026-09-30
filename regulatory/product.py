"""product — camada de produto (Módulos 2–16) sobre o Impact Engine.

Transforma os eventos do Módulo 1 nos nove conjuntos de dados que alimentam as
páginas executivas do produto:

* ``events.json``      — eventos regulatórios publicados (normas, procedimentos,
                         atos, agenda e mudanças com diff) — M1/M10
* ``deadlines.json``   — calendário de prazos com janelas 30/90/180/365 dias — M4
* ``enforcement.json`` — decisões e sanções com lição regulatória — M8
* ``sectors.json``     — matriz de impacto setorial (24 setores) — M2
* ``alerts.json``      — alertas em formato executivo, filtráveis — M5
* ``briefing.json``    — EU AI REGULATORY BRIEF em 8 seções — M6
* ``companies.json``   — perfis de exposição por empresa (linguagem condicional) — M3
* ``watchlist.json``   — watchlists por empresa/setor/tema/norma/regulador — M12
* ``manifest.json``    — integridade, contagens e confiança do conjunto — M16/M18

Nada aqui inventa conteúdo: todo texto de análise vem das bibliotecas de
``taxonomy.py``/``content.py`` (rotuladas como análise/interpretação/
recomendação) e toda evidência aponta para a URL oficial capturada pelo coletor.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

from . import engine
from . import taxonomy as tx

DEFAULT_DATA = engine.DEFAULT_DATA
DATA_FILES = ("events", "deadlines", "enforcement", "sectors", "alerts",
              "briefing", "companies", "watchlist", "manifest")
WEEKDAYS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
SECTOR_BY_NAME = {meta["name"]: slug for slug, meta in tx.SECTORS.items()}
PRIORITY_WEIGHT = {"urgent": 10, "high": 7, "medium": 4, "monitor": 1}
IMPACT_BONUS = {"critical": 4, "high": 2, "medium": 0, "low": 0}

# Chaves temáticas usadas nos perfis de empresa que apontam para os temas
# canónicos da taxonomia atual (evita tema inexistente no produto).
THEME_ALIASES = {
    "transparencia": "ai_act", "praticas-proibidas": "ai_act", "governanca-ia": "ai_act",
    "decisoes-automatizadas": "ai_act", "ai-act": "ai_act", "alto-risco": "ai_act",
    "dados-pessoais": "edpb", "saude-digital": "health_data", "consumo-publicidade": "consumer",
    "emprego": "employment", "direitos-autor": "copyright", "responsabilidade": "ai_liability",
    "dados-e-infraestrutura": "data_act", "plataformas": "dsa",
    "ciberseguranca": "cybersecurity", "financas": "data_act", "energia-clima": "data_act",
    "contratacao-publica": "public_sector", "jurisprudencia": "judicial",
}

COMPANY_NAMES = {
    "google": "Google / Alphabet", "alphabet": "Google / Alphabet", "youtube": "Google / Alphabet",
    "meta": "Meta", "facebook": "Meta", "instagram": "Meta", "whatsapp": "Meta",
    "openai": "OpenAI", "microsoft": "Microsoft", "azure": "Microsoft", "linkedin": "Microsoft",
    "amazon": "Amazon / AWS", "aws": "Amazon / AWS",
    "anthropic": "Anthropic", "nvidia": "NVIDIA", "mistral": "Mistral AI",
    "apple": "Apple", "tiktok": "TikTok", "bytedance": "TikTok",
}

ENFORCEMENT_LESSONS = {
    "enforcement": ("Lição regulatória: o padrão sancionado (base legal, informação ao titular, "
                    "controlo interno) deve ser testado na própria operação antes da próxima auditoria."),
    "edpb": ("Lição regulatória: proteção de dados em produtos digitais é fiscalizada de forma ativa — "
             "base legal, transparência e resposta a pedidos de direitos são verificadas na prática."),
    "ai_act": ("Lição regulatória: documentação, avaliação de risco e supervisão humana precisam de "
               "evidência registada, não apenas de política aprovada."),
    "ai_office": ("Lição regulatória: orientações do European AI Office devem ser incorporadas antes de "
                  "decisões de produto e de lançamento."),
    "health_data": ("Lição regulatória: dados de saúde exigem controles reforçados; falha de segurança "
                    "vira sanção e comunicação pública."),
    "dsa": ("Lição regulatória: deveres de transparência e de resposta ao regulador são cobrados com "
            "prazos curtos em plataformas digitais."),
    "cybersecurity": ("Lição regulatória: falha de segurança com exposição de dados gera sanção "
                      "administrativa além do custo operacional."),
}

LEGAL_BASIS_HINTS = [
    (r"art\.? ?5\b|princ[íi]pio|principle", "Regulamento (UE) 2016/679 (RGPD) — princípios (art. 5.º)"),
    (r"art\.? ?6\b|base legal|lawful", "Regulamento (UE) 2016/679 (RGPD) — base legal (art. 6.º)"),
    (r"art\.? ?12\b|art\.? ?13\b|art\.? ?17\b|direitos|rights of individuals|information to be provided",
     "Regulamento (UE) 2016/679 (RGPD) — informação e direitos do titular (arts. 12.º/13.º/17.º)"),
    (r"art\.? ?32\b|security|seguran[çc]a", "Regulamento (UE) 2016/679 (RGPD) — segurança (art. 32.º)"),
    (r"art\.? ?22\b|automated decision|decis[ãa]o automatizada",
     "Regulamento (UE) 2016/679 (RGPD) — decisões automatizadas (art. 22.º)"),
    (r"cookie|consentiment|consent", "RGPD / ePrivacy — consentimento e cookies"),
    (r"art\.? ?65\b|binding decision", "Regulamento (UE) 2016/679 (RGPD) — mecanismo de coerência (art. 65.º)"),
]


def _norm(text: str) -> str:
    return tx.norm_text(text)


def _short(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def fmt_date(iso: str, short: bool = False) -> str:
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or "—"
    if short:
        return d.strftime("%d/%m/%Y")
    return f"{d.day:02d}/{d.month:02d}/{d.year} ({WEEKDAYS_PT[d.weekday()]})"


def _theme_label(key: str) -> str:
    key = THEME_ALIASES.get(key, key)
    return tx.THEMES.get(key, {}).get("label", key)


def _theme_key(key: str) -> str:
    key = THEME_ALIASES.get(key, key)
    return key if key in tx.THEMES else "ai_act"


def load_companies(base_dir: str | None = None) -> dict:
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    for candidate in (base_dir, os.path.dirname(base_dir)):
        path = os.path.join(candidate, "companies.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
    return {"companies": {}}


# ------------------------------------------------------------------- M1
def build_events_dataset(result: dict, today: date) -> dict:
    events = result["published"]
    excluded = [{"id": item["id"], "regulatory_event": item["regulatory_event"],
                 "confidence": item["confidence"], "reason": "abaixo do piso de confiança",
                 "official_sources": item["official_sources"]} for item in result["excluded"]]
    skipped = [{"id": item["id"], "regulatory_event": item["regulatory_event"],
                "confidence": item["confidence"], "reason": item["reason"],
                "official_sources": item["official_sources"]} for item in result.get("skipped", [])]
    return {
        "meta": {
            "reference_date": today.isoformat(),
            "description": "Eventos regulatórios interpretados pelo Regulatory Impact Engine.",
            "rule": ("FATO, ANÁLISE, INTERPRETAÇÃO e RECOMENDAÇÃO são objetos distintos. "
                     "Confiança mínima 0.6. Nenhum evento sem fonte oficial é publicado."),
            "total": len(events),
            "excluded_low_confidence": len(excluded),
            "excluded_no_material_relation": len(skipped),
        },
        "events": events,
        "excluded": excluded,
        "skipped": skipped,
    }


# ------------------------------------------------------------------- M4
def build_deadlines(events: list[dict], today: date) -> dict:
    milestones = []
    for event in events:
        for index, deadline in enumerate(event.get("deadlines_full") or []):
            iso = deadline.get("date")
            try:
                days = (date.fromisoformat(iso) - today).days
            except (TypeError, ValueError):
                continue
            urgency = ("histórico" if days < 0 else "imediato" if days <= 30
                       else "próximo" if days <= 90 else "planejar" if days <= 180 else "futuro")
            milestones.append({
                "id": f"dl_{event['id']}_{index + 1}",
                "date": iso,
                "days_remaining": days,
                "norm": _short((event.get("fact") or {}).get("title") or event["regulatory_event"], 140),
                "norm_source_url": event["official_sources"][0],
                "obligation": deadline.get("label") or "Marco regulatório",
                "entity": ", ".join(event["affected_company_types"][:3]) or
                          ", ".join(event["affected_sectors"][:3]) or "Organizações afetadas",
                "affected_functions": event["affected_functions"][:8],
                "affected_sectors": event["affected_sectors"][:8],
                "action_needed": event["recommendations"]["next_step"],
                "priority": event["priority"],
                "impact_level": event["impact_level"],
                "urgency": urgency,
                "status": "cumprido" if days < 0 else "pendente",
                "regulator": event["regulator"],
                "basis": deadline.get("basis"),
                "event_id": event["id"],
                "source_url": deadline.get("source_url") or event["official_sources"][0],
            })
    milestones.sort(key=lambda item: item["date"])
    windows = {f"d{limit}": [m["id"] for m in milestones if 0 <= m["days_remaining"] <= limit]
               for limit in (30, 90, 180, 365)}
    return {
        "meta": {
            "reference_date": today.isoformat(),
            "description": ("Calendário regulatório operacional. Cada prazo traz a data escrita na "
                            "fonte oficial, a norma e a ação necessária."),
            "total": len(milestones),
            "upcoming": len([m for m in milestones if m["days_remaining"] >= 0]),
            "rule": "Somente datas escritas em texto oficial preservado no dataset; nenhuma data é estimada.",
        },
        "milestones": milestones,
        "windows": windows,
    }


# ------------------------------------------------------------------- M8
def _authority_label(event: dict) -> str:
    blob = _norm(" ".join([event["regulatory_event"], event.get("summary") or ""]))
    for key, meta in tx.REGULATORS.items():
        if key in ("national_dpa", "other"):
            continue
        if _norm(meta["name"]) in blob:
            return meta["name"]
    if "data protection commission" in blob or re.search(r"\bdpc\b", blob):
        return "Data Protection Commission (Irlanda)"
    if "cnil" in blob:
        return "CNIL (França)"
    if "edpb" in blob:
        return tx.REGULATORS["edpb"]["name"]
    if "edps" in blob:
        return tx.REGULATORS["edps"]["name"]
    return event.get("regulator") or "Autoridade oficial"


def _company_or_sector(event: dict) -> str:
    blob = _norm(event["regulatory_event"])
    for alias, name in COMPANY_NAMES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", blob):
            return name
    return event["affected_sectors"][0] if event["affected_sectors"] else "Setor a classificar"


def _legal_basis(event: dict) -> tuple[str, float]:
    blob = _norm(" ".join([event["regulatory_event"], event.get("summary") or "",
                           (event.get("fact") or {}).get("description") or ""]))
    for pattern, label in LEGAL_BASIS_HINTS:
        if re.search(pattern, blob, re.I):
            return f"{label} — base legal indicada pela autoridade; confirmar na decisão publicada.", 0.80
    return ("Base legal não explicitada no resumo oficial — verificar a decisão na fonte oficial.", 0.60)


def _is_enforcement(event: dict) -> bool:
    return (event.get("act_type") == "enforcement"
            or "penalty" in (event.get("flags") or [])
            or "enforcement" in (event.get("themes") or []))


def build_enforcement(events: list[dict], today: date) -> dict:
    cases = []
    for event in events:
        if not _is_enforcement(event):
            continue
        themes = event.get("themes") or []
        lesson = next((ENFORCEMENT_LESSONS[t] for t in themes if t in ENFORCEMENT_LESSONS),
                      "Lição regulatória: decisões semelhantes indicam prioridade de fiscalização no tema.")
        basis, basis_confidence = _legal_basis(event)
        cases.append({
            "id": event["id"],
            "event": event["regulatory_event"],
            "date": event.get("change_date"),
            "authority": _authority_label(event),
            "company_or_sector": _company_or_sector(event),
            "legal_basis": basis,
            "legal_basis_confidence": basis_confidence,
            "decision": _short((event.get("fact") or {}).get("description") or event.get("summary") or "", 600),
            "consequence": (event.get("so_what") or {}).get("consequence", ""),
            "regulatory_lesson": lesson,
            "affected_sectors": event["affected_sectors"],
            "affected_functions": event["affected_functions"],
            "recommended_actions": event["recommended_actions"][:4],
            "impact_level": event["impact_level"],
            "priority": event["priority"],
            "confidence": event["confidence"],
            "source_url": event["official_sources"][0],
            "official_sources": event["official_sources"],
        })
    cases.sort(key=lambda item: item.get("date") or "", reverse=True)
    return {
        "meta": {
            "total": len(cases),
            "description": ("Enforcement monitorado a partir de fontes oficiais (EDPB, EDPS, Comissão e "
                            "autoridades nacionais citadas nas decisões)."),
            "structure": "Evento → empresa/setor → autoridade → base legal → decisão → consequência → lição regulatória.",
            "rule": "A base legal é a indicada pela autoridade na fonte; o monitor não a reinterpreta.",
        },
        "cases": cases,
    }


# ------------------------------------------------------------------- M2
def _events_for_sector(events: list[dict], slug: str) -> list[dict]:
    name = tx.SECTORS[slug]["name"]
    return [e for e in events if name in (e.get("affected_sectors") or [])]


def build_sectors(events: list[dict], today: date) -> dict:
    blocks = []
    for slug, meta in tx.SECTORS.items():
        related = _events_for_sector(events, slug)
        points = sum(PRIORITY_WEIGHT.get(e["priority"], 1) + IMPACT_BONUS.get(e["impact_level"], 0)
                     for e in related)
        blocks.append({
            "slug": slug, "name": meta["name"], "en": meta["en"], "focus": meta["focus"],
            "functions": [tx.function_name(key) for key in meta["functions"]],
            "company_types": [tx.company_type_name(key) for key in meta["company_types"]],
            "points": points,
            "related": sorted(related, key=lambda e: e["impact_score"], reverse=True),
        })
    peak = max((block["points"] for block in blocks), default=0) or 1
    sectors = []
    for block in blocks:
        related = block["related"]
        top = related[0] if related else None
        sectors.append({
            "slug": block["slug"], "name": block["name"], "en": block["en"], "focus": block["focus"],
            "functions": block["functions"], "company_types": block["company_types"],
            "change_count": len(related),
            "cumulative_impact": min(100, round(block["points"] / peak * 100)),
            "top_priority": top["priority"] if top else "monitor",
            "top_impact_level": top["impact_level"] if top else "low",
            "recent_changes": [{
                "title": e["regulatory_event"][:200], "date": e.get("change_date"),
                "impact_level": e["impact_level"], "priority": e["priority"],
                "event_id": e["id"], "source_url": e["official_sources"][0],
            } for e in related[:8]],
            "obligations": _collect(related, "analysis", "obligations", 6),
            "risks": _collect_plain(related, "risks", 5),
            "recommended_actions": _collect_actions(related, 6),
            "deadlines": [{
                "date": d["date"], "label": d.get("label"), "days_remaining": d.get("days_remaining"),
                "norm": _short((e.get("fact") or {}).get("title") or e["regulatory_event"], 90),
                "event_id": e["id"], "source_url": e["official_sources"][0],
            } for e in related[:4] for d in (e.get("deadlines_full") or [])[:2]][:6],
            "related_acts": [{
                "title": e["regulatory_event"][:200], "act_type": e["act_type_label"],
                "stage": e["stage_label"], "date": e.get("change_date"), "priority": e["priority"],
                "event_id": e["id"], "source_url": e["official_sources"][0],
            } for e in related[:6]],
            "hedge": ("Triagem temática por palavras-chave da fonte oficial. Não confirma enquadramento "
                      "jurídico de nenhuma empresa."),
        })
    sectors.sort(key=lambda item: item["cumulative_impact"], reverse=True)
    for index, sector in enumerate(sectors, 1):
        sector["rank"] = index
    return {
        "meta": {
            "total_sectors": len(sectors),
            "description": "Impacto acumulado por setor calculado a partir dos eventos publicados com fonte oficial.",
            "scoring": "Soma ponderada dos eventos classificados, normalizada a 100 pelo setor de maior exposição.",
        },
        "sectors": sectors,
    }


def _collect(events: list[dict], layer: str, field: str, limit: int) -> list[dict]:
    out: list[dict] = []
    for event in events:
        for item in (event.get(layer) or {}).get(field) or []:
            text = item.get("text") if isinstance(item, dict) else str(item)
            if not text or any(existing["text"] == text for existing in out):
                continue
            out.append({
                "text": text,
                "reference": item.get("reference") if isinstance(item, dict) else None,
                "event_id": event["id"],
                "source_url": event["official_sources"][0],
                "confidence": event["confidence"],
            })
            if len(out) >= limit:
                return out
    return out


def _collect_plain(events: list[dict], field: str, limit: int) -> list[dict]:
    out: list[dict] = []
    for event in events:
        for text in event.get(field) or []:
            if any(existing["text"] == text for existing in out):
                continue
            out.append({"text": text, "event_id": event["id"],
                        "source_url": event["official_sources"][0]})
            if len(out) >= limit:
                return out
    return out


def _collect_actions(events: list[dict], limit: int) -> list[dict]:
    out: list[dict] = []
    for event in events:
        for action in (event.get("recommendations") or {}).get("actions") or []:
            if any(existing["text"] == action["text"] for existing in out):
                continue
            out.append({"text": action["text"], "owner_function": action.get("owner_function"),
                        "priority": action.get("priority"), "event_id": event["id"]})
            if len(out) >= limit:
                return out
    return out


# ------------------------------------------------------------------- M5
def _next_deadline(event: dict) -> dict | None:
    upcoming = [d for d in (event.get("deadlines_full") or []) if d.get("days_remaining", -1) >= 0]
    return min(upcoming, key=lambda d: d["days_remaining"]) if upcoming else None


def build_alerts(events: list[dict], today: date) -> dict:
    alerts = []
    for event in events:
        if event["priority"] not in ("urgent", "high"):
            continue
        deadline = _next_deadline(event)
        if deadline:
            deadline_label = (f"{deadline['label']} — {deadline['date']} "
                              f"({deadline['days_remaining']} dias)")
        else:
            deadline_label = "Sem prazo futuro datado na fonte oficial."
        action = event["recommended_actions"][0] if event["recommended_actions"] else \
            "Avaliar aplicabilidade com a área responsável."
        text = (
            "ALERTA REGULATÓRIO\n\n"
            f"Evento:\n{event['regulatory_event']}\n\n"
            f"Impacto:\n{tx.IMPACT_LEVELS[event['impact_level']]['label'].upper()}\n\n"
            f"Afeta:\n{', '.join(event['affected_sectors'][:4]) or 'setores a classificar'}\n\n"
            f"Áreas internas:\n{', '.join(event['affected_functions'][:5])}\n\n"
            f"O que mudou:\n{_short(event.get('summary') or '', 400)}\n\n"
            f"Ação recomendada:\n{action}\n\n"
            f"Prazo:\n{deadline_label}\n\n"
            f"Fonte oficial:\n{event['official_sources'][0]}"
        )
        alerts.append({
            "id": "al_" + event["id"], "event_id": event["id"], "priority": event["priority"],
            "impact_level": event["impact_level"], "impact_score": event["impact_score"],
            "sectors": event["affected_sectors"][:6], "themes": event["theme_labels"][:4],
            "regulator": event["regulator"], "company_types": event["affected_company_types"][:4],
            "functions": event["affected_functions"][:5],
            "deadline": deadline["date"] if deadline else None,
            "deadline_label": deadline_label,
            "title": event["regulatory_event"], "what_changed": _short(event.get("summary") or "", 400),
            "recommended_action": action, "confidence": event["confidence"],
            "official_sources": event["official_sources"], "text": text,
        })
    alerts.sort(key=lambda item: (-item["impact_score"], item.get("deadline") or "9999"))
    return {
        "meta": {
            "total": len(alerts),
            "description": "Alertas em formato executivo, gerados a partir de eventos com fonte oficial.",
            "filters": ["setor", "tema", "empresa", "órgão", "nível de impacto", "deadline"],
            "rule": "Alerta sem URL oficial não é gerado; confiança mínima 0.6.",
        },
        "alerts": alerts,
    }


# ------------------------------------------------------------------- M6
def _event_item(event: dict, action: str | None = None) -> dict:
    item = {"title": event["regulatory_event"], "impact_level": event["impact_level"],
            "priority": event["priority"], "event_id": event["id"],
            "sectors": event["affected_sectors"][:3], "source_url": event["official_sources"][0]}
    if action:
        item["action"] = action
    return item


def _deadline_item(milestone: dict) -> dict:
    return {"date": milestone["date"], "label": milestone["obligation"], "norm": milestone["norm"],
            "days_remaining": milestone["days_remaining"], "event_id": milestone["event_id"],
            "source_url": milestone["source_url"]}


def build_briefing(events: list[dict], deadlines: dict, enforcement: dict, sectors: dict,
                   today: date) -> dict:
    milestones = deadlines["milestones"]
    upcoming = [m for m in milestones if m["days_remaining"] >= 0]
    recent = [e for e in events if (e.get("change_date") or "") >= (today - timedelta(days=7)).isoformat()]
    recent = recent or events

    def section(title: str, items: list[dict], empty_message: str) -> dict:
        return {"title": title, "items": items, "empty_message": empty_message}

    def sections(window_events: list[dict], window_milestones: list[dict]) -> list[dict]:
        urgent = [e for e in window_events if e["impact_level"] in ("critical", "high")][:5]
        actions = [_event_item(e, e.get("recommendations", {}).get("next_step"))
                   for e in window_events if e["priority"] in ("urgent", "high")][:5]
        enforcement_items = [_event_item(c_event) for c_event in _cases_as_events(enforcement, window_events)][:4]
        consultations = [_event_item(e) for e in window_events if e["act_type"] == "consultation"][:4]
        ai_act = [_event_item(e) for e in window_events
                  if {"ai_act", "ai_office", "gpai"} & set(e["themes"])][:4]
        sector_items = [{"sector": s["name"], "changes": s["change_count"], "slug": s["slug"]}
                        for s in sectors["sectors"] if s["change_count"]][:5]
        watch = [_event_item(e) for e in window_events
                 if e["priority"] in ("urgent", "high", "medium")][5:9]
        if not watch:
            watch = [{"title": m["obligation"], "reason": f"{m['norm']} · {m['days_remaining']} dias",
                      "event_id": m["event_id"], "source_url": m["source_url"]}
                     for m in window_milestones[:4]]
        return [
            section("1. Mudanças críticas", [_event_item(e) for e in urgent],
                    "Nenhuma mudança crítica nova na fonte oficial neste recorte."),
            section("2. O que exige ação", actions,
                    "Nenhuma ação obrigatória datada neste recorte; monitorização mantida."),
            section("3. Deadlines", [_deadline_item(m) for m in window_milestones[:6]],
                    "Nenhum prazo futuro datado em fonte oficial nesta janela."),
            section("4. Enforcement", enforcement_items,
                    "Nenhuma decisão de enforcement nova registada nas fontes monitoradas."),
            section("5. Consultas abertas", consultations,
                    "Nenhuma consulta aberta com fonte oficial neste recorte."),
            section("6. Mudanças no AI Act", ai_act,
                    "Nenhuma mudança no AI Act / GPAI registada neste recorte."),
            section("7. Setores mais impactados", sector_items,
                    "Nenhum setor classificado neste recorte."),
            section("8. O que acompanhar na próxima semana", watch,
                    "Sem item adicional para acompanhamento; manter a watchlist ativa."),
        ]

    daily = {
        "reference_date": today.isoformat(),
        "reading_time_minutes": 5,
        "sections": sections(recent, upcoming[:6]),
    }
    weekly = {
        "reference_date": today.isoformat(),
        "reading_time_minutes": 5,
        "period": f"{(today - timedelta(days=7)).isoformat()} a {today.isoformat()}",
        "sections": sections(events, upcoming[:10]),
    }
    return {
        "meta": {"description": "EU AI REGULATORY BRIEF — diário e semanal, 8 seções fixas, leitura de 5 minutos.",
                 "rule": "Cada item tem fonte oficial; itens sem fonte não entram no brief."},
        "daily": daily,
        "weekly": weekly,
    }


def _cases_as_events(enforcement: dict, events: list[dict]) -> list[dict]:
    by_id = {e["id"]: e for e in events}
    return [by_id[c["id"]] for c in enforcement["cases"] if c["id"] in by_id]


# ------------------------------------------------------------------- M3
def build_companies(profiles: dict, events: list[dict], today: date) -> dict:
    companies = []
    catalogue = profiles.get("companies") or {}
    for slug, profile in catalogue.items():
        aliases = [profile.get("name", slug)] + list(profile.get("aliases") or [])
        patterns = [re.compile(r"\b" + re.escape(_norm(alias)) + r"\b") for alias in aliases if alias]
        mentions = []
        for event in events:
            blob = _norm(" ".join([event["regulatory_event"], event.get("summary") or ""]))
            if any(pattern.search(blob) for pattern in patterns):
                mentions.append(event)
        exposure = []
        seen_exposure = set()
        profile_sectors = set(profile.get("sectors") or [])
        profile_themes = set(_theme_key(t) for t in profile.get("themes") or [])
        for event in events:
            if event["id"] in seen_exposure:
                continue
            event_sectors = {SECTOR_BY_NAME.get(name, "") for name in event["affected_sectors"]}
            if (set(event["id"] for event in mentions) and event in mentions) \
                    or profile_sectors & event_sectors or profile_themes & set(event["themes"]):
                exposure.append(event)
                seen_exposure.add(event["id"])
        related = mentions[:6]
        ranked = sorted(exposure, key=lambda e: e["impact_score"], reverse=True)
        top = ranked[0] if ranked else None
        obligations = []
        for event in ranked:
            for item in (event.get("analysis") or {}).get("obligations") or []:
                if any(existing["text"] == item["text"] for existing in obligations):
                    continue
                obligations.append({"text": item["text"], "reference": item.get("reference"),
                                    "event_id": event["id"]})
                if len(obligations) >= 8:
                    break
            if len(obligations) >= 8:
                break
        deadlines = []
        for event in ranked:
            for deadline in event.get("deadlines_full") or []:
                if deadline.get("days_remaining", -1) < 0:
                    continue
                deadlines.append({"date": deadline["date"], "label": deadline["label"],
                                  "norm": _short((event.get("fact") or {}).get("title") or event["regulatory_event"], 90),
                                  "event_id": event["id"], "source_url": event["official_sources"][0]})
                if len(deadlines) >= 5:
                    break
            if len(deadlines) >= 5:
                break
        level = top["impact_level"] if top else "medium"
        companies.append({
            "slug": slug, "name": profile.get("name", slug), "aliases": aliases,
            "hq": profile.get("hq") or "A classificar",
            "public_activities": profile.get("activities") or [],
            "sectors": [{"slug": s, "name": tx.sector_name(s)} for s in profile.get("sectors") or []
                        if s in tx.SECTORS],
            "themes": [{"key": _theme_key(t), "label": _theme_label(t)} for t in profile.get("themes") or []][:6],
            "evidence_status": ("menção em fonte oficial do dataset" if mentions
                                else "sem menção direta no dataset atual"),
            "evidence_matches": [{"title": e["regulatory_event"][:200], "event_id": e["id"],
                                  "source_url": e["official_sources"][0], "date": e.get("change_date")}
                                 for e in mentions[:6]],
            "related_acts": [{"title": e["regulatory_event"][:200], "act_type": e["act_type_label"],
                              "stage": e["stage_label"], "date": e.get("change_date"),
                              "priority": e["priority"], "impact_level": e["impact_level"],
                              "event_id": e["id"], "source_url": e["official_sources"][0]}
                             for e in related],
            "exposure_themes": [{"title": e["regulatory_event"][:160], "event_id": e["id"],
                                 "priority": e["priority"], "source_url": e["official_sources"][0]}
                                for e in ranked[:6]],
            "possible_obligations": obligations,
            "deadlines": deadlines,
            "regulatory_risk": level,
            "risk_label": tx.IMPACT_LEVELS[level]["label"],
            "watchlist": profile.get("watchlist") or [],
            "assessment_questions": profile.get("questions") or [],
            "hedge": ("potencialmente afetada — exposição provável por perfil público de atuação; "
                      "a aplicabilidade depende das atividades exercidas e requer avaliação jurídica específica."),
        })
    companies.sort(key=lambda item: item["name"])
    return {
        "meta": {
            "total": len(companies),
            "rule": "Nenhuma empresa é declarada juridicamente enquadrada; apenas exposição provável a temas.",
            "evidence_rule": "Itens relacionados exigem menção da empresa no texto da fonte oficial.",
        },
        "companies": companies,
    }


# ------------------------------------------------------------------- M12
WATCHLIST_PRESETS = [
    {"id": "ai-act-gpai", "name": "EU AI Act + GPAI + Foundation Models",
     "themes": ["ai_act", "gpai", "ai_office"], "sectors": ["modelos-de-fundacao", "provedores-de-ia"],
     "regulators": ["European AI Office", "Comissão Europeia"]},
    {"id": "data-protection", "name": "Proteção de dados e EDPB", "themes": ["edpb", "edps"],
     "sectors": [], "regulators": ["EDPB", "EDPS"]},
    {"id": "enforcement", "name": "Enforcement e sanções", "themes": ["enforcement"],
     "sectors": [], "regulators": ["EDPB", "CNIL (França)", "Data Protection Commission (Irlanda)"]},
]


def build_watchlist(events: list[dict], sectors: dict, companies: dict, today: date) -> dict:
    themes: dict[str, int] = {}
    regulators: dict[str, int] = {}
    act_types: dict[str, int] = {}
    for event in events:
        for theme in event["themes"]:
            themes[theme] = themes.get(theme, 0) + 1
        regulators[event["regulator"]] = regulators.get(event["regulator"], 0) + 1
        act_types[event["act_type_label"]] = act_types.get(event["act_type_label"], 0) + 1
    return {
        "meta": {"description": "Watchlists prontas por tema, setor, norma, empresa e regulador.",
                 "rule": "Contagens reais do dataset; nenhum item é inferido."},
        "presets": WATCHLIST_PRESETS,
        "themes": [{"key": key, "label": tx.theme_label(key), "events": count}
                   for key, count in sorted(themes.items(), key=lambda kv: -kv[1])],
        "regulators": [{"name": name, "events": count}
                       for name, count in sorted(regulators.items(), key=lambda kv: -kv[1])],
        "act_types": [{"label": label, "events": count}
                      for label, count in sorted(act_types.items(), key=lambda kv: -kv[1])],
        "sectors": [{"slug": s["slug"], "name": s["name"], "changes": s["change_count"]}
                    for s in sectors["sectors"] if s["change_count"]],
        "companies": [{"slug": c["slug"], "name": c["name"], "themes": [t["label"] for t in c["themes"]]}
                      for c in companies["companies"]],
    }


# ------------------------------------------------------------------- M16/M18
def build_manifest(datasets: dict, events: list[dict], excluded: list[dict], skipped: list[dict],
                   today: date) -> dict:
    confidences = [e["confidence"] for e in events]
    hosts: dict[str, int] = {}
    for event in events:
        for url in event["official_sources"]:
            host = re.sub(r"^https?://", "", url).split("/")[0]
            hosts[host] = hosts.get(host, 0) + 1
    return {
        "meta": {
            "generated_from": "data/legislation-eu/*.json",
            "dataset_execution": today.isoformat(),
            "reference_date": today.isoformat(),
            "description": "Métricas de qualidade e cobertura da camada de inteligência.",
        },
        "events_total": len(events) + len(excluded),
        "events_published": len(events),
        "events_excluded_low_confidence": len(excluded),
        "events_excluded_no_material_relation": len(skipped),
        "events_without_official_source": 0,
        "events_by_priority": {key: len([e for e in events if e["priority"] == key]) for key in tx.PRIORITIES},
        "events_by_impact": {key: len([e for e in events if e["impact_level"] == key]) for key in tx.IMPACT_LEVELS},
        "confidence_min": min(confidences) if confidences else None,
        "confidence_avg": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "deadlines_tracked": datasets["deadlines"]["meta"]["total"],
        "deadlines_next_90_days": len(datasets["deadlines"]["windows"]["d90"]),
        "enforcement_cases": datasets["enforcement"]["meta"]["total"],
        "sectors_covered": len([s for s in datasets["sectors"]["sectors"] if s["change_count"]]),
        "sectors_total": len(datasets["sectors"]["sectors"]),
        "alerts_generated": datasets["alerts"]["meta"]["total"],
        "official_hosts": [{"host": host, "citations": count}
                           for host, count in sorted(hosts.items(), key=lambda kv: -kv[1])],
        "excluded": [item["id"] for item in excluded],
        "skipped_no_material_relation": [item["id"] for item in skipped],
    }


def build_all(data_dir: str | None = None, base_dir: str | None = None) -> dict:
    """Gera os nove conjuntos de dados do produto (sem escrever em disco)."""
    data_dir = data_dir or DEFAULT_DATA
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    result = engine.build_events(data_dir)
    today = date.fromisoformat(result["reference_date"])
    events = result["published"]
    datasets = {
        "events": build_events_dataset(result, today),
        "deadlines": build_deadlines(events, today),
        "enforcement": build_enforcement(events, today),
        "sectors": build_sectors(events, today),
        "alerts": build_alerts(events, today),
    }
    datasets["briefing"] = build_briefing(events, datasets["deadlines"], datasets["enforcement"],
                                          datasets["sectors"], today)
    datasets["companies"] = build_companies(load_companies(base_dir), events, today)
    datasets["watchlist"] = build_watchlist(events, datasets["sectors"], datasets["companies"], today)
    datasets["manifest"] = build_manifest(datasets, events, result["excluded"],
                                          result.get("skipped", []), today)
    return datasets


def write_all(datasets: dict, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, payload in datasets.items():
        path = os.path.join(out_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=False)
            handle.write("\n")
        written.append(path)
    return written
