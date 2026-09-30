#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Páginas da camada de inteligência regulatória (LCF EU Regulatory Intelligence).

Consome `regulatory/*` e escreve:
  /impacto/ (+ ficha por evento)  Módulo 1 e 7
  /setores/ (+ 24 setores)        Módulo 2
  /empresas/ (+ perfis)           Módulo 3
  /prazos/                        Módulo 4
  /alertas-executivos/            Módulo 5
  /briefing-executivo/            Módulo 6
  /enforcement/                   Módulo 8
  /jurisprudencia/                Módulo 9
  /diff/                          Módulo 10
  /demo/                          Módulo 15
  /produto/                       Módulo 14
  /como-analisamos/               Módulo 16
  páginas de captação (M13) e home executiva (M11)
"""
from __future__ import annotations

import json
import re
import sys
from html import escape as esc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from regulatory import product, taxonomy as tx  # noqa: E402
from regulatory.engine import norm_text, official_source  # noqa: E402

DISCLAIMER = ("Inteligência regulatória e análise de impacto de caráter informativo. Não constitui parecer ou "
              "aconselhamento jurídico, nem garantia de conformidade ou de interpretação legal. Toda exposição "
              "é potencial e requer avaliação jurídica específica.")
LAYER_LABELS = {"fact": "FATO OFICIAL", "analysis": "ANÁLISE", "interpretation": "INTERPRETAÇÃO",
                "recommendation": "RECOMENDAÇÃO"}


# --------------------------------------------------------------------------- #
# Helpers de render
# --------------------------------------------------------------------------- #
def badge(text, cls="monitor"):
    return f'<span class="iq-badge {cls}">{esc(text)}</span>'


def priority_badge(priority):
    return badge(tx.PRIORITIES[priority]["label"], priority)


def impact_badge(level):
    return badge(tx.IMPACT_LEVELS[level]["label"], level)


def tag(text):
    return f'<span class="tag">{esc(text)}</span>'


def source_link(url, label="Fonte oficial"):
    return f'<a href="{esc(url)}" rel="noopener" target="_blank">{esc(label)} ↗</a>'


def head(title, sub, kicker, crumbs):
    crumb_html = ' › '.join(([f'<a href="/">Monitor público</a>'] +
                             [f'<a href="{c[1]}">{esc(c[0])}</a>' if c[1] else esc(c[0]) for c in crumbs]))
    return (f'<div class="page-head iq-shell"><div class="wrap"><div class="crumbs">{crumb_html}</div>'
            f'<div class="iq-kicker">{esc(kicker)}</div><h1 class="iq-h1">{esc(title)}</h1>'
            f'<p class="iq-sub">{sub}</p></div></div>')


def body_open():
    return '<section class="block"><div class="wrap iq-content">'


def body_close():
    return '</div></section>'


def cta_block(label="Receba alertas regulatórios personalizados para sua empresa.",
              href="/diagnostico/", button="Falar com a LCF Consulting"):
    return (f'<div class="iq-note" style="margin-top:22px"><strong>{esc(label)}</strong><div class="iq-actions">'
            f'<a class="iq-btn" href="{href}">{esc(button)}</a>'
            '<a class="iq-btn-ghost" href="/briefing-executivo/">Ver briefing executivo</a>'
            '<a class="iq-btn-ghost" href="/produto/">Planos e cobertura</a></div></div>')


def layer(kind, title, content):
    return (f'<div class="iq-layer {kind}"><div class="label">{LAYER_LABELS[kind]}</div>'
            f'<h3>{esc(title)}</h3>{content}</div>')


def event_ref_card(event, full_action=True):
    sectors = ', '.join(event["affected_sectors"][:4]) or 'A classificar'
    action = event["recommendations"]["next_step"]
    return (
        f'<article class="iq-card" data-event data-priority="{esc(event["priority"])}" '
        f'data-title="{esc(event["regulatory_event"])}" '
        f'data-sectors="{esc(",".join(event["affected_sectors"]))}" '
        f'data-themes="{esc(",".join(event["themes"]))}">'
        f'<div class="iq-meta">{priority_badge(event["priority"])}{impact_badge(event["impact_level"])}'
        f'{tag(event["act_type_label"])}{tag(event["change_date"] or "sem data")}{tag(event["regulator"])}</div>'
        f'<h3><a href="/impacto/{esc(event["id"])}/">{esc(_short(event["regulatory_event"], 150))}</a></h3>'
        f'<p>{esc(_short(event["summary"], 240))}</p>'
        f'<p class="iq-small"><strong>Setores:</strong> {esc(sectors)}</p>'
        f'<p class="iq-small"><strong>Áreas internas:</strong> {esc(", ".join(event["affected_functions"][:5]) or "a confirmar")}</p>'
        + (f'<p class="iq-small"><strong>Ação recomendada:</strong> {esc(action)}</p>' if full_action else '')
        + f'<div class="iq-meta">{source_link(event["fact"]["source_url"])}'
          f'<a href="/impacto/{esc(event["id"])}/">Ler análise completa</a></div></article>')


def _short(text, size):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= size else text[:size - 1].rstrip() + "…"


def event_detail(core, event, sector_names):
    facts = [
        ("Data do item", event["change_date"] or "não informada"),
        ("Órgão responsável", event["regulator"]),
        ("Tipo de ato", event["act_type_label"]),
        ("Estágio", event["stage_label"]),
        ("Prioridade", tx.PRIORITIES[event["priority"]]["label"]),
        ("Impacto", tx.IMPACT_LEVELS[event["impact_level"]]["label"]),
        ("Confiança da análise", f'{event["confidence"]:.2f} — {event["confidence_label"]}'),
        ("Território", event["territory"]),
    ]
    if event.get("entry_into_force"):
        facts.append(("Entrada em vigor / aplicável", event["entry_into_force"]))
    if event.get("compliance_deadline"):
        facts.append(("Próximo prazo de adequação", event["compliance_deadline"]))

    body = head(event["regulatory_event"], esc(_short(event["summary"], 300)), "REGULATORY IMPACT ENGINE",
                [("Impacto regulatório", "/impacto/"), (core.SITE_NAME, None)])
    body += body_open()
    body += ('<div class="iq-strip">' + priority_badge(event["priority"]) + impact_badge(event["impact_level"]) +
             badge(f'{event["impact_score"]}/100 prioridade', "medium") +
             badge(f'confiança {event["confidence"]:.2f}', "ok" if event["confidence"] >= 0.8 else "warn") +
             badge(event["act_type_label"]) + '</div>')
    body += '<dl class="iq-facts">' + ''.join(
        f'<div class="iq-fact"><dt>{esc(k)}</dt><dd>{esc(str(v))}</dd></div>' for k, v in facts) + '</dl>'

    # FATO OFICIAL
    fact_links = ' · '.join(source_link(s["url"], s["title"][:70]) for s in event["fact"]["sources"])
    body += layer("fact", "O que mudou (registro da fonte oficial)",
                  f'<p>{esc(event["fact"]["description"] or event["fact"]["title"])}</p>'
                  f'<p class="iq-small">Órgão: {esc(event["fact"]["regulator"])} · '
                  f'{esc(event["fact"]["date_label"])}: {esc(event["fact"]["date"] or "não informada")}</p>'
                  f'<p class="iq-small">{fact_links}</p>'
                  f'<p class="iq-note">{esc(event["fact"]["note"])}</p>')

    # ANÁLISE
    obligations = ''.join(f'<li>{esc(o["text"])} <span class="iq-muted">— base: {esc(o["basis"])} · '
                          f'confiança {o["confidence"]:.2f}</span></li>' for o in event["analysis"]["obligations"])
    risks = ''.join(f'<li>{esc(r["text"])}</li>' for r in event["analysis"]["risks"]) or '<li>Nenhum risco classificado nesta leitura.</li>'
    opportunities = ''.join(f'<li>{esc(o["text"])}</li>' for o in event["analysis"]["opportunities"]) or '<li>Nenhuma oportunidade classificada nesta leitura.</li>'
    body += layer("analysis", "Por que isso importa",
                  f'<p>{esc(event["analysis"]["why_it_matters"])}</p>'
                  f'<h4 style="font-size:13.5px;margin-top:10px">Possíveis obrigações</h4><ul>{obligations or "<li>A classificar.</li>"}</ul>'
                  f'<h4 style="font-size:13.5px;margin-top:10px">Riscos</h4><ul>{risks}</ul>'
                  f'<h4 style="font-size:13.5px;margin-top:10px">Oportunidades</h4><ul>{opportunities}</ul>')

    # INTERPRETAÇÃO
    sectors = ''.join(
        f'<li><a href="/setores/{esc(s["slug"])}/">{esc(s["name"])}</a> — {esc(s["why"])} '
        f'<span class="iq-muted">({esc("base explícita" if s["basis"] == "explicit" else "base temática")})</span></li>'
        for s in event["analysis"]["sector_exposure"]) or '<li>Setor não determinado.</li>'
    company_types = ', '.join(event["affected_company_types"]) or 'a confirmar'
    body += layer("interpretation", "Quem pode ser afetado",
                  f'<p>{esc(event["interpretation"]["text"])}</p>'
                  f'<h4 style="font-size:13.5px;margin-top:10px">Setores</h4><ul>{sectors}</ul>'
                  f'<p class="iq-small" style="margin-top:8px"><strong>Tipos de empresa:</strong> {esc(company_types)}</p>'
                  f'<p class="iq-small"><strong>Áreas internas:</strong> {esc(", ".join(event["affected_functions"]))}</p>'
                  f'<p class="iq-note">{esc(event["interpretation"]["limits"])}</p>')

    # RECOMENDAÇÃO
    actions = ''.join(f'<li>{esc(a["text"])} <span class="iq-muted">— responsável sugerido: '
                      f'{esc(tx.FUNCTIONS.get(a["owner_function"], {"name": a["owner_function"]})["name"])} · '
                      f'prioridade {esc(a["priority"])}</span></li>' for a in event["recommendations"]["actions"])
    body += layer("recommendation", "O que fazer",
                  f'<ol>{actions or "<li>Manter em observação.</li>"}</ol>'
                  f'<p class="iq-small">SLA sugerido: {esc(event["recommendations"]["sla"])} · '
                  f'Áreas responsáveis: {esc(", ".join(event["recommendations"]["owner_functions"]))}</p>')

    # O QUE ISSO SIGNIFICA NA PRÁTICA (Módulo 7)
    so = event["so_what"]
    body += ('<h2 class="section-title">O que isso significa na prática?</h2>'
             '<div class="iq-grid c2">'
             f'<div class="iq-block"><h3>Consequência empresarial</h3><p>{esc(so["consequence"])}</p></div>'
             f'<div class="iq-block"><h3>Áreas internas envolvidas</h3><p>{esc(", ".join(so["functions"]) or "a confirmar")}</p></div>'
             f'<div class="iq-block"><h3>Possíveis custos</h3><p>{esc(so["possible_costs"])}</p></div>'
             f'<div class="iq-block"><h3>Necessidade de adequação</h3><p>{esc(so["adaptation_needed"])}</p></div>'
             f'<div class="iq-block"><h3>Risco de não agir</h3><p>{esc(so["risk_of_inaction"])}</p></div>'
             f'<div class="iq-block"><h3>Próximo passo</h3><p>{esc(so["next_step"])}</p></div>'
             '</div>')

    # Prazos e diff
    if event.get("deadlines_full"):
        rows = ''.join(
            f'<tr><td>{esc(d["date"])}</td><td>{esc(d["label"])}</td>'
            f'<td>{"cumprido" if d["days_remaining"] < 0 else str(d["days_remaining"]) + " dias"}</td>'
            f'<td>{"sim" if d.get("tracker", True) else "referência"}</td></tr>'
            for d in event["deadlines_full"])
        body += ('<h2 class="section-title">Prazos ligados a este evento</h2>'
                 f'<div class="iq-scroll"><table class="iq-table"><thead><tr><th>Data</th><th>Marco</th>'
                 f'<th>Prazo restante</th><th>No tracker</th></tr></thead><tbody>{rows}</tbody></table></div>'
                 '<p class="iq-small"><a href="/prazos/">Abrir o Deadline Tracker completo →</a></p>')
    if event.get("diff"):
        diff = event["diff"]
        body += ('<h2 class="section-title">Regulatory Change Diff</h2>'
                 f'<div class="iq-block"><h3>VERSÃO ANTERIOR → VERSÃO NOVA</h3>'
                 f'<p class="iq-small">Campo alterado: <code>{esc(str(diff.get("field")))}</code> · '
                 f'Tipo: {esc(str(diff.get("change_type")))}</p>'
                 f'<p class="iq-small">Hash anterior: <code>{esc(str(diff.get("previous")))}</code><br>'
                 f'Hash atual: <code>{esc(str(diff.get("current")))}</code></p>'
                 f'<p class="iq-note">{esc(diff.get("note"))}</p></div>')

    body += ('<h2 class="section-title">Evidência utilizada</h2>'
             '<ul class="iq-list">' + ''.join(
                 f'<li>{source_link(s["url"], s["title"] or s["url"])} <span class="iq-muted">— {esc(s["type"])}</span></li>'
                 for s in event["fact"]["sources"]) + '</ul>')
    body += (f'<p class="iq-small iq-muted" style="margin-top:10px">{esc(event["hedge"])}</p>'
             '<p><button type="button" class="watch-button" data-watch-id="'
             f'{esc(event["id"])}">Salvar na watchlist deste navegador</button></p>')
    body += cta_block()
    body += body_close()
    return body


# --------------------------------------------------------------------------- #
# Páginas
# --------------------------------------------------------------------------- #
def page_impact_index(core, data):
    events = data["events"]["events"]
    sectors = sorted({s for e in events for s in e["affected_sectors"]})
    themes = sorted({t for e in events for t in e["themes"]},
                    key=lambda t: tx.THEMES[t]["label"] if t in tx.THEMES else t)
    options = ''.join(f'<option value="{esc(t)}">{esc(tx.THEMES[t]["label"] if t in tx.THEMES else t)}</option>'
                      for t in themes)
    sector_options = ''.join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in sectors)
    body = head("Regulatory Impact Engine",
                "Cada mudança respondida em onze perguntas: o que mudou, por que importa, quem é afetado, "
                "quais setores, quais tipos de empresa, qual área interna age, qual obrigação, qual prazo, "
                "qual ação, qual evidência oficial e qual prioridade.",
                "MÓDULO 1 · INTELIGÊNCIA ACIONÁVEL",
                [("Impacto regulatório", None)])
    body += body_open()
    body += (f'<p class="iq-small iq-muted">{len(events)} eventos publicados com fonte oficial · '
             f'confiança mínima 0.6 · {len(data["sectors"]["sectors"])} setores mapeados.</p>')
    body += ('<div class="iq-filters">'
             '<input id="iq-search" type="search" placeholder="Buscar por evento, norma ou tema" aria-label="Buscar">'
             '<select id="iq-priority" aria-label="Prioridade"><option value="">Todas as prioridades</option>'
             '<option value="urgent">Urgente</option><option value="high">Alta</option>'
             '<option value="medium">Média</option><option value="monitor">Monitorar</option></select>'
             f'<select id="iq-sector" aria-label="Setor"><option value="">Todos os setores</option>{sector_options}</select>'
             f'<select id="iq-theme" aria-label="Tema"><option value="">Todos os temas</option>{options}</select>'
             '</div><p role="status" id="iq-count" class="iq-small iq-muted"></p>')
    body += '<div class="iq-grid c2">' + ''.join(event_ref_card(e) for e in events) + '</div>'
    body += cta_block()
    body += body_close()
    return body


def page_sectors_index(core, data):
    sectors = data["sectors"]["sectors"]
    body = head("Matriz de impacto por setor",
                "24 setores com mudanças recentes, obrigações potenciais, riscos, prazos, atos relacionados "
                "e ações recomendadas. Triagem temática — não confirma enquadramento jurídico.",
                "MÓDULO 2 · SETORES", [("Setores", None)])
    body += body_open()
    body += '<div class="iq-matrix">' + ''.join(
        f'<a href="/setores/{esc(s["slug"])}/"><strong>{esc(s["name"])}</strong>'
        f'<small>{s["change_count"]} mudança(s) classificada(s) · impacto acumulado {s["cumulative_impact"]}/100</small>'
        f'<div class="iq-bar"><span style="width:{max(3, s["cumulative_impact"])}%"></span></div></a>'
        for s in sectors) + '</div>'
    body += ('<h2 class="section-title">Como o impacto acumulado é calculado</h2>'
             '<p class="iq-small">Soma ponderada dos 12 eventos de maior impacto classificados para o setor, '
             'normalizada numa escala de 0 a 100. A classificação vem de palavras-chave do texto oficial e de '
             'temas regulatórios. <a href="/como-analisamos/">Ver método, confiança e limites →</a></p>')
    body += cta_block()
    body += body_close()
    return body


def page_sector(core, data, sector):
    slug = sector["slug"]
    body = head(f"Regulação de IA para {sector['name']}",
                f"{sector['focus']} Exposição provável e potencial; requer avaliação jurídica específica.",
                f"MÓDULO 2 · SETOR {sector['en'].upper()}",
                [("Setores", "/setores/"), (sector["name"], None)])
    body += body_open()
    body += ('<div class="iq-strip">' + impact_badge(sector["top_impact_level"]) + priority_badge(sector["top_priority"]) +
             badge(f'{sector["change_count"]} mudanças classificadas') +
             badge(f'impacto acumulado {sector["cumulative_impact"]}/100', "medium") + '</div>')
    body += ('<h2 class="section-title">Mudanças recentes</h2>'
             + ('<div class="iq-grid c2">' + ''.join(
                 f'<div class="iq-block"><h3><a href="/impacto/{esc(c["event_id"])}/">{esc(_short(c["title"], 120))}</a></h3>'
                 f'<p class="iq-small">{esc(c["date"] or "sem data")} · impacto {esc(tx.IMPACT_LEVELS[c["impact_level"]]["label"])} · '
                 f'prioridade {esc(tx.PRIORITIES[c["priority"]]["label"])}</p></div>'
                 for c in sector["recent_changes"]) + '</div>'
                if sector["recent_changes"] else
                '<p class="iq-note">Nenhuma mudança classificada para este setor no dataset atual. '
                'O setor permanece na matriz porque a regulação de IA pode alcançá-lo por via temática; '
                'a ausência de item não significa ausência de obrigação.</p>'))
    body += ('<h2 class="section-title">Obrigações potenciais</h2><ul class="iq-list">' +
             (''.join(f'<li>{esc(o["text"])} <span class="iq-muted">— {esc(o["reference"])} · '
                      f'confiança {o["confidence"]:.2f} · <a href="/impacto/{esc(o["event_id"])}/">evento</a></span></li>'
                      for o in sector["obligations"]) or '<li>A classificar em nova execução.</li>') + '</ul>')
    body += ('<div class="iq-grid c2" style="margin-top:18px">'
             '<div class="iq-block"><h3>Riscos</h3><ul>' +
             (''.join(f'<li>{esc(r["text"])}</li>' for r in sector["risks"]) or '<li>A classificar.</li>') + '</ul></div>'
             '<div class="iq-block"><h3>Deadlines</h3><ul>' +
             (''.join(f'<li>{esc(d["date"])} — {esc(d["label"])} <span class="iq-muted">({esc(d["norm"][:60])})</span></li>'
                      for d in sector["deadlines"]) or '<li>Nenhum prazo datado associado a este setor no recorte atual.</li>') + '</ul>'
             '<p class="iq-small"><a href="/prazos/">Abrir Deadline Tracker →</a></p></div></div>')
    body += ('<h2 class="section-title">Ações recomendadas</h2><ol class="iq-list">' +
             (''.join(f'<li>{esc(a["text"])} <span class="iq-muted">— {esc(a["owner_function"])}</span></li>'
                      for a in sector["recommended_actions"]) or '<li>Sem ação classificada no recorte atual.</li>') + '</ol>')
    body += ('<h2 class="section-title">Atos e itens relacionados</h2><div class="iq-scroll"><table class="iq-table">'
             '<thead><tr><th>Item</th><th>Tipo</th><th>Estágio</th><th>Data</th><th>Prioridade</th><th>Fonte</th></tr></thead><tbody>' +
             ''.join(f'<tr><td><a href="/impacto/{esc(a["event_id"])}/">{esc(_short(a["title"], 90))}</a></td>'
                     f'<td>{esc(a["act_type"])}</td><td>{esc(a["stage"])}</td><td>{esc(a["date"] or "—")}</td>'
                     f'<td>{priority_badge(a["priority"])}</td><td>{source_link(a["source_url"], "oficial")}</td></tr>'
                     for a in sector["related_acts"]) + '</tbody></table></div>' if sector["related_acts"] else '')
    body += f'<p class="iq-note" style="margin-top:16px">{esc(sector["hedge"])}</p>'
    body += cta_block(f"Receba alertas regulatórios para {sector['name']}.")
    body += body_close()
    return body


def page_deadlines(core, data):
    tracker = data["deadlines"]
    milestones = {m["id"]: m for m in tracker["milestones"]}
    body = head("Deadline Tracker regulatório",
                "Calendário operacional dos prazos de aplicação e adequação, com norma, obrigação, "
                "entidade afetada, tempo restante, urgência, ação necessária e fonte oficial.",
                "MÓDULO 4 · PRAZOS", [("Prazos", None)])
    body += body_open()
    upcoming = [m for m in tracker["milestones"] if m["days_remaining"] >= 0]
    body += ('<div class="iq-grid c4">' +
             f'<div class="iq-block"><h3>Próximos 30 dias</h3><p class="iq-h1" style="font-size:26px">{len(tracker["windows"]["d30"])}</p></div>'
             f'<div class="iq-block"><h3>Próximos 90 dias</h3><p class="iq-h1" style="font-size:26px">{len(tracker["windows"]["d90"])}</p></div>'
             f'<div class="iq-block"><h3>Próximos 6 meses</h3><p class="iq-h1" style="font-size:26px">{len(tracker["windows"]["d180"])}</p></div>'
             f'<div class="iq-block"><h3>Próximos 12 meses</h3><p class="iq-h1" style="font-size:26px">{len(tracker["windows"]["d365"])}</p></div>'
             '</div>')
    body += ('<div class="iq-tabs" role="tablist">'
             '<button role="tab" data-window-tab="d30">Próximos 30 dias</button>'
             '<button role="tab" data-window-tab="d90">Próximos 90 dias</button>'
             '<button role="tab" data-window-tab="d180">Próximos 6 meses</button>'
             '<button role="tab" data-window-tab="d365">Próximos 12 meses</button></div>')
    for window, label in (("d30", "30 dias"), ("d90", "90 dias"), ("d180", "6 meses"), ("d365", "12 meses")):
        items = [milestones[i] for i in tracker["windows"][window]]
        if items:
            rows = ''.join(
                f'<tr><td><strong>{esc(m["date"])}</strong><br><span class="iq-small iq-muted">'
                f'{m["days_remaining"]} dias</span></td>'
                f'<td>{esc(_short(m["norm"], 110))}</td><td>{esc(m["obligation"])}</td>'
                f'<td>{esc(m["entity"])}</td><td>{esc(_short(m["action_needed"], 130))}</td>'
                f'<td>{priority_badge(m["priority"])}</td><td>{source_link(m["source_url"], "oficial")}</td></tr>'
                for m in items)
            table = ('<div class="iq-scroll"><table class="iq-table"><thead><tr><th>Data</th><th>Norma</th>'
                     '<th>Obrigação / marco</th><th>Entidade afetada</th><th>Ação necessária</th>'
                     '<th>Prioridade</th><th>Fonte</th></tr></thead><tbody>' + rows + '</tbody></table></div>')
        else:
            table = ('<p class="iq-note">Nenhum prazo datado em fonte oficial nesta janela. O monitor não '
                     'estima datas: prazos aparecem quando a data está escrita na fonte.</p>')
        body += f'<div data-window="{window}" hidden><h3 class="mini-title">Janela de {label}</h3>{table}</div>'
    body += ('<h2 class="section-title">Histórico de marcos cumpridos</h2><ul class="iq-list">' +
             ''.join(f'<li>{esc(m["date"])} — {esc(m["obligation"])} · {esc(_short(m["norm"], 90))}</li>'
                     for m in reversed(tracker["milestones"]) if m["days_remaining"] < 0) + '</ul>')
    body += ('<p class="iq-small">Regra do tracker: somente datas escritas em texto oficial preservado no dataset '
             '(EUR-Lex, Jornal Oficial, páginas oficiais de consulta). <a href="/como-analisamos/">Ver método →</a></p>')
    body += cta_block("Receba alertas de prazo com 90, 30 e 7 dias de antecedência.")
    body += body_close()
    return body


def page_enforcement(core, data):
    cases = data["enforcement"]["cases"]
    body = head("Enforcement e sanções",
                "Decisões, multas, investigações e medidas corretivas de autoridades europeias com relação "
                "material a IA, dados e plataformas digitais.",
                "MÓDULO 8 · ENFORCEMENT", [("Enforcement", None)])
    body += body_open()
    body += (f'<p class="iq-small iq-muted">{len(cases)} casos com fonte oficial. Estrutura: evento → '
             'empresa/setor → autoridade → base legal → decisão → consequência → lição regulatória.</p>')
    body += '<div class="iq-grid c2">' + ''.join(
        f'<article class="iq-card"><div class="iq-meta">{priority_badge(c["priority"])}{impact_badge(c["impact_level"])}'
        f'{tag(c["authority"])}{tag(c["date"] or "sem data")}</div>'
        f'<h3>{esc(_short(c["event"], 130))}</h3>'
        f'<p><strong>Empresa/setor:</strong> {esc(c["company_or_sector"])} · '
        f'<strong>setores:</strong> {esc(", ".join(c["affected_sectors"][:4]) or "a classificar")}</p>'
        f'<p><strong>Base legal:</strong> {esc(c["legal_basis"])}</p>'
        f'<p><strong>Consequência:</strong> {esc(_short(c["consequence"], 200))}</p>'
        f'<p><strong>Lição regulatória:</strong> {esc(_short(c["regulatory_lesson"], 200))}</p>'
        f'<div class="iq-meta">{source_link(c["source_url"])}</div></article>' for c in cases) + '</div>'
    body += ('<h2 class="section-title">Fontes monitoradas para enforcement</h2>'
             '<ul class="iq-list"><li>EDPB — decisões nacionais publicadas e orientações de aplicação.</li>'
             '<li>EDPS — decisões relativas a instituições da União Europeia.</li>'
             '<li>Comissão Europeia — investigações e decisões no âmbito digital.</li>'
             '<li>Autoridades nacionais de proteção de dados e de supervisão citadas nas decisões publicadas.</li></ul>')
    body += cta_block("Quer o padrão sancionado monitorado para o seu setor?")
    body += body_close()
    return body


def page_companies_index(core, data):
    companies = data["companies"]["companies"]
    body = head("Company Impact Profile",
                "Perfis de exposição regulatória construídos a partir de atividades publicamente conhecidas e "
                "de temas com fonte oficial. Nenhuma empresa é declarada juridicamente enquadrada.",
                "MÓDULO 3 · EMPRESAS", [("Empresas", None)])
    body += body_open()
    body += '<div class="iq-grid c3">' + ''.join(
        f'<a class="iq-card" href="/empresas/{esc(c["slug"])}/" style="display:block">'
        f'<div class="iq-meta">{badge(c["hq"])}'
        f'{badge("com menção oficial" if c["related_acts"] else "exposição temática", "warn" if not c["related_acts"] else "ok")}</div>'
        f'<h3>{esc(c["name"])}</h3><p>{esc(", ".join(s["name"] for s in c["sectors"][:3]))}</p></a>'
        for c in companies) + '</div>'
    body += ('<p class="iq-note" style="margin-top:16px">Linguagem obrigatória do módulo: potencialmente afetada · '
             'exposição regulatória provável · aplicável caso a empresa exerça determinada atividade · requer '
             'avaliação jurídica específica.</p>')
    body += cta_block("Monitore sua empresa na watchlist regulatória.")
    body += body_close()
    return body


def page_company(core, data, company):
    body = head(f"Perfil de exposição: {company['name']}",
                esc(company["hedge"]), "MÓDULO 3 · COMPANY IMPACT PROFILE",
                [("Empresas", "/empresas/"), (company["name"], None)])
    body += body_open()
    body += ('<div class="iq-strip">' + badge(company["hq"]) +
             badge("Menção em fonte oficial do dataset" if company["related_acts"] else "Sem menção direta no dataset",
                   "ok" if company["related_acts"] else "warn") +
             impact_badge(company["regulatory_risk"]) + '</div>')
    body += ('<h2 class="section-title">Atividades publicamente conhecidas</h2><ul class="iq-list">' +
             ''.join(f'<li>{esc(a)}</li>' for a in company["public_activities"]) + '</ul>')
    body += ('<h2 class="section-title">Setores e temas</h2>'
             '<p class="iq-small"><strong>Setores:</strong> ' +
             ', '.join(f'<a href="/setores/{esc(s["slug"])}/">{esc(s["name"])}</a>' for s in company["sectors"]) +
             '</p><p class="iq-small"><strong>Temas:</strong> ' +
             ', '.join(esc(t["label"]) for t in company["themes"]) + '</p>')
    body += ('<h2 class="section-title">Atos relacionados por menção oficial</h2>' +
             ('<div class="iq-grid c2">' + ''.join(
                 f'<div class="iq-block"><h3><a href="/impacto/{esc(a["event_id"])}/">{esc(_short(a["title"], 120))}</a></h3>'
                 f'<p class="iq-small">{esc(a["date"] or "sem data")} · impacto {esc(tx.IMPACT_LEVELS[a["impact_level"]]["label"])}</p>'
                 f'<p>{source_link(a["source_url"])}</p></div>' for a in company["related_acts"]) + '</div>'
              if company["related_acts"] else
              '<p class="iq-note">Nenhum item do dataset atual menciona esta empresa no texto da fonte oficial. '
              'O perfil abaixo é temático e não constitui conclusão sobre aplicação da norma.</p>'))
    body += ('<h2 class="section-title">Possíveis obrigações (exposição temática)</h2><ul class="iq-list">' +
             (''.join(f'<li>{esc(o["text"])} <span class="iq-muted">— {esc(o["reference"])}</span></li>'
                      for o in company["possible_obligations"]) or '<li>A classificar.</li>') + '</ul>')
    body += ('<h2 class="section-title">Deadlines aplicáveis</h2><ul class="iq-list">' +
             (''.join(f'<li>{esc(d["date"])} — {esc(d["label"])} <span class="iq-muted">({esc(_short(d["norm"], 70))})</span></li>'
                      for d in company["deadlines"]) or '<li>Nenhum prazo futuro datado associado aos temas deste perfil.</li>') + '</ul>')
    body += ('<h2 class="section-title">Perguntas de aplicabilidade</h2><ol class="iq-list">' +
             ''.join(f'<li>{esc(q)}</li>' for q in company["assessment_questions"]) + '</ol>')
    body += ('<h2 class="section-title">Watchlist sugerida</h2><p>' +
             ''.join(badge(w) + ' ' for w in company["watchlist"]) + '</p>')
    body += cta_block(f"Receba alertas quando um ato afetar o perfil de {company['name']}.")
    body += body_close()
    return body


def page_jurisprudence(core, data):
    body = head("Jurisprudência — arquitetura de monitoramento",
                "Estrutura preparada para decisões do TJUE, do Tribunal Geral e de tribunais nacionais "
                "relevantes. Sem jurisprudência inventada: nenhum acórdão é publicado sem fonte oficial verificada.",
                "MÓDULO 9 · JURISPRUDÊNCIA", [("Jurisprudência", None)])
    body += body_open()
    body += ('<h2 class="section-title">Estado atual do monitoramento</h2>'
             '<p>O repositório ainda não possui conector estável para o CURIA/TJUE. O monitor declara essa '
             'limitação em vez de preencher a lacuna com dados estimados. Enquanto não existir ingestão verificada, '
             'esta página permanece como arquitetura e não exibe decisões.</p>')
    body += ('<h2 class="section-title">Arquitetura preparada</h2><ol class="iq-list">'
             '<li><strong>Fonte primária:</strong> CURIA (curia.europa.eu) e site do TJUE, com verificação manual '
             'de cada acórdão antes da publicação.</li>'
             '<li><strong>Fallback:</strong> RSS/HTML oficial quando disponível, parsing controlado e registo de '
             'falha — nunca inferência de conteúdo.</li>'
             '<li><strong>Ingestão controlada:</strong> cada decisão entra no dataset com número do processo, data, '
             'tribunal, URL oficial e ponto de decisão.</li>'
             '<li><strong>Ligação ao produto:</strong> a decisão é ligada a eventos, setores e funções internas, '
             'com leitura das quatro camadas (fato, análise, interpretação, recomendação).</li>'
             '<li><strong>Bloqueio de qualidade:</strong> sem URL oficial, o item não é publicado — a mesma regra '
             'do Regulatory Impact Engine.</li></ol>')
    body += ('<h2 class="section-title">O que já é coberto hoje</h2>'
             '<p>Decisões de autoridades de proteção de dados com relação a dados e IA aparecem em '
             '<a href="/enforcement/">Enforcement</a>, sempre com a autoridade, a base legal indicada e a consequência. '
             'Quando a jurisprudência da UE for integrada, ela passa a alimentar automaticamente o enforcement e '
             'os setores afetados.</p>')
    body += cta_block("Precisa de acompanhamento jurisprudencial específico? Falamos de escopo.")
    body += body_close()
    return body


def page_diff(core, data):
    events = [e for e in data["events"]["events"] if e.get("diff")]
    body = head("Regulatory Change Diff",
                "Comparação entre versões anteriores e novas para guidelines, drafts, códigos de prática, "
                "regulamentos, atos delegados e atos de execução detectados pelo monitor.",
                "MÓDULO 10 · DIFF", [("Diff regulatório", None)])
    body += body_open()
    if events:
        rows = ''.join(
            f'<tr><td>{esc(e["change_date"] or "—")}</td>'
            f'<td><a href="/impacto/{esc(e["id"])}/">{esc(_short(e["regulatory_event"], 110))}</a></td>'
            f'<td>{esc(e["act_type_label"])}</td><td>{esc(str(e["diff"].get("field")))}</td>'
            f'<td><code class="iq-small">{esc(str(e["diff"].get("previous"))[:26])}</code> → '
            f'<code class="iq-small">{esc(str(e["diff"].get("current"))[:26])}</code></td>'
            f'<td>{esc(", ".join(e["affected_sectors"][:3]) or "—")}</td>'
            f'<td>{source_link(e["fact"]["source_url"], "oficial")}</td></tr>' for e in events)
        body += ('<div class="iq-scroll"><table class="iq-table"><thead><tr><th>Data</th><th>Norma / item</th>'
                 '<th>Tipo</th><th>Campo</th><th>Versão anterior → nova</th><th>Quem é afetado</th><th>Fonte</th>'
                 '</tr></thead><tbody>' + rows + '</tbody></table></div>')
        body += ('<h2 class="section-title">Como ler o diff</h2>'
                 '<p>O monitor guarda o <strong>hash criptográfico</strong> da versão anterior e da versão atual do '
                 'texto oficial. Hash diferente significa que o texto publicado mudou; o monitor não reconstrói o '
                 'conteúdo. A alteração material deve ser confirmada no URL oficial indicado, e a leitura de impacto '
                 'é apresentada como análise, nunca como fato.</p>')
    else:
        body += ('<p class="iq-note">Nenhuma alteração de versão com hash anterior e novo registada no dataset '
                 'atual. O monitor publica este bloco apenas quando existe mudança de versão em fonte oficial.</p>')
    body += ('<h2 class="section-title">Campos comparados pelo monitor</h2><ul class="iq-list">'
             '<li>Guidelines e orientações — texto e versão publicada.</li>'
             '<li>Drafts e códigos de prática — versão submetida e versão adotada.</li>'
             '<li>Regulamentos, atos delegados e atos de execução — alteração de texto publicado.</li>'
             '<li>Metadados de procedimento — relatoria, situação e estágio.</li></ul>')
    body += cta_block("Quer receber o diff de cada guideline relevante para o seu setor?")
    body += body_close()
    return body


def page_alerts(core, data):
    alerts = data["alerts"]["alerts"]
    body = head("Alertas regulatórios em formato executivo",
                "Cada alerta traz evento, impacto, quem é afetado, áreas internas, o que mudou, ação "
                "recomendada, prazo e fonte oficial. Alertas filtram por setor, tema, empresa, órgão, "
                "impacto e deadline.",
                "MÓDULO 5 · ALERTAS EXECUTIVOS", [("Alertas executivos", None)])
    body += body_open()
    body += ('<div class="iq-filters">'
             '<input id="iq-search" type="search" placeholder="Buscar alerta" aria-label="Buscar alerta">'
             '<select id="iq-priority" aria-label="Prioridade"><option value="">Todos os impactos</option>'
             '<option value="urgent">Urgente</option><option value="high">Alta</option>'
             '<option value="medium">Média</option></select></div>'
             '<p role="status" id="iq-count" class="iq-small iq-muted"></p>')
    body += '<div class="iq-grid c2">' + ''.join(
        f'<article class="iq-card" data-event data-priority="{esc(a["priority"])}" data-title="{esc(a["title"])}">'
        f'<div class="iq-meta">{priority_badge(a["priority"])}{impact_badge(a["impact_level"])}'
        f'{tag(a["regulator"])}{tag(a["deadline"] or "sem prazo datado")}</div>'
        f'<h3>{esc(_short(a["title"], 130))}</h3>'
        f'<p class="iq-small"><strong>Afeta:</strong> {esc(", ".join(a["sectors"][:4]) or ", ".join(a["company_types"][:3]))}</p>'
        f'<p class="iq-small"><strong>Áreas:</strong> {esc(", ".join(a["functions"][:5]))}</p>'
        f'<div class="iq-alert" style="margin-top:10px"><pre id="{esc(a["id"])}">{esc(a["text"])}</pre></div>'
        f'<div class="iq-actions" style="margin-top:10px">'
        f'<button class="iq-btn-ghost" data-copy-alert="{esc(a["id"])}">Copiar alerta</button>'
        f'<a class="iq-btn-ghost" href="/impacto/{esc(a["event_id"])}/">Ver análise</a></div></article>'
        for a in alerts) + '</div>'
    body += ('<h2 class="section-title">Como configurar</h2>'
             '<p>Alertas por setor, tema, empresa, órgão, nível de impacto e deadline. '
             '<a href="/alertas/">Configurar alertas por e-mail →</a> A confirmação do endereço é obrigatória.</p>')
    body += cta_block("Receba alertas regulatórios personalizados para sua empresa.")
    body += body_close()
    return body


def _briefing_sections(brief):
    html = []
    for section in brief["sections"]:
        items = section["items"]
        if not items:
            html.append(f'<h3 class="mini-title">{esc(section["title"])}</h3><p class="iq-note">{esc(section["empty_message"])}</p>')
            continue
        rendered = []
        for item in items:
            if "event_id" in item and "title" in item:
                rendered.append(f'<li><a href="/impacto/{esc(item["event_id"])}/">{esc(_short(item["title"], 130))}</a>'
                                f'{" — " + esc(_short(item.get("action") or item.get("reason") or "", 150)) if (item.get("action") or item.get("reason")) else ""}'
                                f'{badge(tx.IMPACT_LEVELS[item["impact_level"]]["label"], item["impact_level"]) if item.get("impact_level") else ""}</li>')
            elif "sector" in item:
                rendered.append(f'<li>{esc(item["sector"])} — {item["changes"]} mudança(s)</li>')
            elif "date" in item:
                rendered.append(f'<li><strong>{esc(item["date"])}</strong> — {esc(item["label"])} · '
                                f'{esc(_short(item["norm"], 90))} ({item["days_remaining"]} dias)</li>')
            else:
                rendered.append(f'<li>{esc(json.dumps(item, ensure_ascii=False))}</li>')
        html.append(f'<h3 class="mini-title">{esc(section["title"])}</h3><ul class="iq-list">' + ''.join(rendered) + '</ul>')
    return ''.join(html)


def page_briefing(core, data):
    brief = data["briefing"]
    body = head("EU AI Regulatory Brief",
                "Briefing executivo diário e semanal, com leitura máxima de 5 minutos. "
                "Cada item aponta para a fonte oficial.",
                "MÓDULO 6 · EXECUTIVE BRIEFING", [("Briefing executivo", None)])
    body += body_open()
    body += (f'<p class="iq-small iq-muted">Execução de referência: {esc(brief["daily"]["reference_date"])} · '
             f'leitura estimada: {brief["daily"]["reading_time_minutes"]} minutos.</p>')
    body += ('<div class="iq-tabs" role="tablist"><button role="tab" data-window-tab="daily">Brief diário</button>'
             '<button role="tab" data-window-tab="weekly">Brief semanal</button></div>')
    body += f'<div data-window="daily"><h2 class="section-title">EU AI REGULATORY BRIEF — diário</h2>{_briefing_sections(brief["daily"])}</div>'
    body += (f'<div data-window="weekly" hidden><h2 class="section-title">EU AI REGULATORY BRIEF — semanal</h2>'
             f'<p class="iq-small iq-muted">Período: {esc(brief["weekly"]["period"])}</p>{_briefing_sections(brief["weekly"])}</div>')
    body += cta_block("Receba o brief semanal no e-mail dos decisores.")
    body += body_close()
    return body


def page_quality(core, data):
    manifest = data["manifest"]
    scale = ''.join(
        f'<tr><td><code>{k}</code></td><td>{v:.2f}</td><td>{esc(tx.CONFIDENCE_LABELS[k])}</td></tr>'
        for k, v in tx.CONFIDENCE.items() if k != "unpublished")
    hosts = ''.join(f'<li>{esc(h["host"])} — {h["citations"]} citação(ões)</li>' for h in manifest["official_hosts"])
    body = head("Como analisamos: fato, análise, interpretação e recomendação",
                "Metodologia da camada de inteligência: separação obrigatória das quatro camadas, escala de "
                "confiança, regra de não publicação e métricas de qualidade da execução.",
                "MÓDULO 16 · MÉTODO E CONFIANÇA", [("Como analisamos", None)])
    body += body_open()
    body += ('<div class="iq-grid c2">'
             '<div class="iq-layer fact"><div class="label">FATO OFICIAL</div><h3>O que a fonte diz</h3>'
             '<p>Título, data, órgão e URL preservados do dataset. Nada é acrescentado.</p></div>'
             '<div class="iq-layer analysis"><div class="label">ANÁLISE</div><h3>Por que importa</h3>'
             '<p>Leitura do significado do item para uma organização exposta, sempre com a base textual que a sustenta.</p></div>'
             '<div class="iq-layer interpretation"><div class="label">INTERPRETAÇÃO</div><h3>Quem pode ser afetado</h3>'
             '<p>Setores, tipos de empresa e áreas internas provavelmente expostos. Nunca um enquadramento jurídico.</p></div>'
             '<div class="iq-layer recommendation"><div class="label">RECOMENDAÇÃO</div><h3>O que fazer</h3>'
             '<p>Ação sugerida, responsável, prazo de priorização e próximo passo a registar.</p></div></div>')
    body += ('<h2 class="section-title">Escala de confiança</h2>'
             '<div class="iq-scroll"><table class="iq-table"><thead><tr><th>Código</th><th>Valor</th><th>Significado</th>'
             f'</tr></thead><tbody>{scale}</tbody></table></div>'
             '<p class="iq-note">Abaixo de 0.60 o item <strong>não é publicado automaticamente</strong> — fica registado '
             'no manifesto como excluído, para curadoria.</p>')
    body += ('<h2 class="section-title">Qualidade da execução atual</h2><div class="iq-grid c4">' +
             f'<div class="iq-block"><h3>Eventos publicados</h3><p class="iq-h1" style="font-size:26px">{manifest["events_published"]}</p></div>'
             f'<div class="iq-block"><h3>Sem fonte oficial</h3><p class="iq-h1" style="font-size:26px">{manifest["events_without_official_source"]}</p></div>'
             f'<div class="iq-block"><h3>Confiança mínima</h3><p class="iq-h1" style="font-size:26px">{manifest["confidence_min"]:.2f}</p></div>'
             f'<div class="iq-block"><h3>Prazos rastreados</h3><p class="iq-h1" style="font-size:26px">{manifest["deadlines_tracked"]}</p></div>'
             '</div>')
    body += ('<h2 class="section-title">Fontes oficiais citadas nesta execução</h2><ul class="iq-list">' +
             hosts + '</ul>')
    body += ('<h2 class="section-title">Regras que o motor aplica</h2><ul class="iq-list">'
             '<li>Item sem URL oficial não gera evento publicado.</li>'
             '<li>Confiança abaixo de 0.6 não é publicada automaticamente.</li>'
             '<li>Nenhuma empresa é declarada juridicamente enquadrada.</li>'
             '<li>Prioridade calculada por rúbrica pública — nunca probabilidade de aprovação ou posição política.</li>'
             '<li>Os scores existentes do monitor público são preservados e apresentados como informação separada.</li></ul>')
    body += cta_block()
    body += body_close()
    return body


def page_demo(core, data):
    """Demonstração comercial com dados reais do monitor: 3 mudanças, 2 prazos, 1 risco, 4 áreas, 5 ações."""
    events_all = data["events"]["events"]
    sector = next((s for s in data["sectors"]["sectors"] if s["slug"] == "saas"), None)
    sector_event_ids = {c["event_id"] for c in (sector or {}).get("related_acts", [])}
    demo_events = [e for e in events_all if e["id"] in sector_event_ids][:3]
    for event in events_all:
        if len(demo_events) >= 3:
            break
        if event not in demo_events:
            demo_events.append(event)
    demo_events = demo_events[:3]

    all_deadlines = [m for m in data["deadlines"]["milestones"] if m["days_remaining"] >= 0]
    sector_deadlines = [d for d in (sector or {}).get("deadlines", [])
                        if (d.get("days_remaining") or -1) >= 0]
    demo_deadlines = []
    for deadline in sector_deadlines:  # apenas prazos futuros: nenhum prazo vencido é apresentado
        demo_deadlines.append({"date": deadline["date"], "label": deadline["label"],
                               "days_remaining": deadline["days_remaining"], "norm": deadline["norm"]})
    for milestone in all_deadlines:
        if len(demo_deadlines) >= 2:
            break
        if not any(d["date"] == milestone["date"] and d["label"] == milestone["obligation"] for d in demo_deadlines):
            demo_deadlines.append({"date": milestone["date"], "label": milestone["obligation"],
                                   "days_remaining": milestone["days_remaining"], "norm": milestone["norm"]})
    demo_deadlines = demo_deadlines[:2]

    risks = list((sector or {}).get("risks", []))
    for event in demo_events:
        if risks:
            break
        risks.extend(event["analysis"]["risks"])
    risk = risks[0] if risks else None

    functions = list((sector or {}).get("functions", []))
    for event in demo_events:
        for name in event["affected_functions"]:
            if name not in functions:
                functions.append(name)
    functions = functions[:4]

    actions = list((sector or {}).get("recommended_actions", []))
    for event in demo_events:
        for action in event["recommendations"]["actions"]:
            if not any(a["text"] == action["text"] for a in actions):
                actions.append(action)
    actions = actions[:5]

    body = head("Demonstração em 2 minutos: European SaaS Company",
                "Caso completo com dados reais do monitor para uma empresa europeia de SaaS que embute IA "
                "em produtos B2B: 3 mudanças regulatórias, 2 prazos, 1 risco prioritário, 4 áreas internas "
                "afetadas e 5 ações recomendadas.",
                "MÓDULO 15 · DEMO COMERCIAL", [("Demonstração", None)])
    body += body_open()
    body += ('<p class="iq-note">Empresa hipotética, usada para demonstrar o produto. Os eventos, prazos e fontes '
             'são reais e rastreáveis no dataset público; a leitura de impacto é análise e requer avaliação '
             'jurídica específica. Cada cartão abre a ficha completa do evento.</p>')
    body += '<h2 class="section-title">1. Três mudanças regulatórias que exigem leitura</h2>'
    body += ('<div class="iq-grid c3">' + ''.join(event_ref_card(e, full_action=False) for e in demo_events) +
             '</div>' if demo_events else '<p class="iq-note">Sem eventos no dataset atual.</p>')
    body += ('<h2 class="section-title">2. Dois prazos no radar</h2>'
             '<div class="iq-scroll"><table class="iq-table"><thead><tr><th>Data</th><th>Marco</th>'
             '<th>Tempo restante</th><th>Norma</th></tr></thead><tbody>' +
             (''.join(f'<tr><td><strong>{esc(d["date"])}</strong></td><td>{esc(d["label"])}</td>'
                      f'<td>{d["days_remaining"]} dias</td><td>{esc(_short(d["norm"], 80))}</td></tr>'
                      for d in demo_deadlines) or '<tr><td colspan="4">Sem prazo datado no recorte atual.</td></tr>') +
             '</tbody></table></div>')
    body += '<h2 class="section-title">3. Um risco prioritário para tratar primeiro</h2>'
    body += ('<div class="iq-block"><p>' + impact_badge(sector["top_impact_level"] if sector else "high") +
             f' {esc(risk["text"] if risk else "Risco a classificar em nova execução.")}</p>'
             + (f'<p class="iq-small">{source_link(risk["source_url"])}</p>' if risk else '') + '</div>')
    body += '<h2 class="section-title">4. Quatro áreas internas afetadas</h2><p>' + (
        ''.join(badge(name) + ' ' for name in functions) or badge("A classificar"))
    body += '</p><h2 class="section-title">5. Cinco ações recomendadas</h2><ol class="iq-list">' + (
        ''.join(f'<li>{esc(a["text"])} <span class="iq-muted">— {esc(a.get("owner_function", "compliance"))}</span></li>'
                for a in actions) or '<li>Definir responsáveis e revisar a exposição setorial.</li>') + '</ol>'
    company = next((c for c in data["companies"]["companies"] if c["slug"] == "openai"), None)
    if company:
        body += ('<h2 class="section-title">6. E se a empresa fosse um provedor de modelo?</h2>'
                 f'<p>Veja o perfil de exposição de <a href="/empresas/{esc(company["slug"])}/">{esc(company["name"])}</a> '
                 'construído com o mesmo conjunto de dados, com linguagem cautelosa e perguntas de aplicabilidade.</p>')
    body += ('<h2 class="section-title">O que o cliente recebe na prática</h2><ol class="iq-list">'
             '<li>Alerta executivo com o que mudou, por que importa, quem é afetado e o que fazer.</li>'
             '<li>Deadline tracker com prazos e ação necessária por norma.</li>'
             '<li>Exposição por setor e por área interna, com prioridade.</li>'
             '<li>Briefing semanal de 5 minutos para a liderança.</li>'
             '<li>Histórico auditável com fonte oficial em cada item.</li></ol>')
    body += cta_block("Quer esta demonstração aplicada à sua empresa?")
    body += body_close()
    return body


def page_product(core, data):
    plans = [
        ("FREE", "Monitor público", ["Monitor público de procedimentos, atos e atualizações",
                                     "Timeline do AI Act", "Dataset JSON com fonte oficial",
                                     "Sem alertas personalizados"], "/impacto/", False),
        ("PRO", "Inteligência setorial", ["Alertas personalizados por tema e setor",
                                          "Deadline tracker com antecedência",
                                          "Watchlists por empresa, tema, norma e regulador",
                                          "Briefing semanal executivo"], "/alertas/", True),
        ("BUSINESS", "Exposição da empresa", ["Company impact profiles",
                                              "Briefing executivo ampliado",
                                              "Múltiplos usuários e exportações",
                                              "Histórico completo e acesso à API de dados"], "/empresas/", False),
        ("ENTERPRISE", "Regulatory intelligence dedicada", ["Monitoramento customizado e temas sob medida",
                                                             "Integrações e relatórios dedicados",
                                                             "Acompanhamento com especialista",
                                                             "SLA e escopo acordados"], "/diagnostico/", False),
    ]
    body = head("LCF EU Regulatory Intelligence",
                "Transformamos mudanças regulatórias europeias em decisões acionáveis para empresas expostas "
                "à regulação de IA.",
                "MÓDULO 14 · PRODUTO", [("Produto e planos", None)])
    body += body_open()
    body += ('<div class="iq-grid c2">'
             '<div class="iq-block"><h3>O problema</h3><p>Mudança regulatória chega como texto jurídico, '
             'disperso entre reguladores, em inglês técnico, sem dizer o que a empresa deve fazer.</p></div>'
             '<div class="iq-block"><h3>O que entregamos</h3><p>Da fonte oficial à ação: evento → interpretação → '
             'impacto → setor → empresa → obrigação → prazo → responsável interno → ação → evidência.</p></div></div>')
    body += '<div class="iq-grid c4" style="margin-top:18px">' + ''.join(
        f'<article class="iq-card"{" style=border-color:#2fca8a" if featured else ""}>'
        f'<div class="iq-meta">{badge(name, "ok" if featured else "monitor")}</div>'
        f'<h3>{esc(title)}</h3><ul class="iq-list">' +
        ''.join(f'<li>{esc(f)}</li>' for f in features) +
        f'</ul><div class="iq-actions" style="margin-top:12px"><a class="iq-btn-ghost" href="{href}">Ver</a></div></article>'
        for name, title, features, href, featured in plans) + '</div>'
    body += ('<h2 class="section-title">Por que a LCF</h2><ul class="iq-list">'
             '<li>Fonte oficial obrigatória em cada item — regra aplicada por código, não por promessa.</li>'
             '<li>Quatro camadas separadas: fato, análise, interpretação e recomendação.</li>'
             '<li>Escala de confiança pública e exclusão automática abaixo de 0,60.</li>'
             '<li>Histórico versionado no repositório e auditável item a item.</li>'
             '<li>Experiência em regulação de IA, dados e infraestrutura digital na União Europeia.</li></ul>')
    body += ('<h2 class="section-title">Próximo passo comercial</h2>'
             '<p>Sem pagamento online nesta fase: a contratação é feita por proposta, com escopo, cobertura e '
             'disponibilidade acordados. <a href="/diagnostico/">Solicitar uma conversa de diagnóstico →</a></p>')
    body += cta_block("Receba alertas regulatórios personalizados para sua empresa.")
    body += body_close()
    return body


# --------------------------------------------------------------------------- #
# Páginas de captação (Módulo 13)
# --------------------------------------------------------------------------- #
LEAD_PAGES = [
    {"slug": "eu-ai-act-deadlines", "title": "EU AI Act: prazos de aplicação e adequação",
     "query": "eu ai act deadlines", "theme": "ai_act", "sector": None,
     "kicker": "PRAZOS DO AI ACT",
     "intro": "Datas de aplicação do AI Act e do Digital Omnibus on AI, com a norma, o marco, a ação necessária e a fonte oficial no EUR-Lex.",
     "focus": "Quem precisa agir: provedores de sistemas de alto risco, provedores de GPAI, deployers empresariais e áreas de compliance, jurídico e AI governance."},
    {"slug": "gpai-compliance", "title": "GPAI compliance: obrigações para modelos de uso geral",
     "query": "gpai compliance obligations", "theme": "gpai", "sector": "modelos-de-fundacao",
     "kicker": "GPAI E MODELOS DE FUNDAÇÃO",
     "intro": "O que o quadro europeu exige de quem disponibiliza modelos de uso geral: documentação técnica, informação a terceiros, política de direitos de autor e avaliação de risco sistémico.",
     "focus": "Quem precisa agir: provedores de GPAI, fornecedores de modelos a clientes regulados e equipas de AI governance e jurídico."},
    {"slug": "ai-act-banking", "title": "AI Act para bancos e instituições financeiras",
     "query": "ai act banking", "theme": "ai_act", "sector": "bancos",
     "kicker": "SETOR FINANCEIRO",
     "intro": "Como a regulação europeia de IA chega ao crédito, à prevenção de fraude, ao onboarding e à governança de modelos.",
     "focus": "Quem precisa agir: risco de modelo, compliance, jurídico, auditoria interna e data governance."},
    {"slug": "ai-act-healthcare", "title": "AI Act para saúde e dispositivos médicos",
     "query": "ai act healthcare", "theme": "ai_act", "sector": "saude",
     "kicker": "SAÚDE",
     "intro": "Sistemas de IA em apoio à decisão clínica, dados de saúde e a interação entre o AI Act, o RGPD e a legislação de dispositivos médicos.",
     "focus": "Quem precisa agir: assuntos regulatórios, DPO, assuntos clínicos, segurança do paciente e IT clínico."},
    {"slug": "ai-act-saas", "title": "AI Act para empresas SaaS",
     "query": "ai act saas compliance", "theme": "ai_act", "sector": "saas",
     "kicker": "SAAS",
     "intro": "Software B2B com IA embutida: o que muda em contratos, documentação, transparência e resposta a clientes regulados.",
     "focus": "Quem precisa agir: produto, engenharia, jurídico, segurança e customer success."},
    {"slug": "ai-act-foundation-models", "title": "Foundation models: exposição regulatória europeia",
     "query": "foundation models regulation eu", "theme": "gpai", "sector": "modelos-de-fundacao",
     "kicker": "MODELOS DE FUNDAÇÃO",
     "intro": "Documentação de modelo, dados de treino, direitos de autor e risco sistémico para quem constrói ou integra modelos de fundação.",
     "focus": "Quem precisa agir: AI governance, engenharia de modelo, jurídico e public policy."},
    {"slug": "ai-office-updates", "title": "AI Office: atualizações de implementação do AI Act",
     "query": "european ai office updates", "theme": "ai_office", "sector": None,
     "kicker": "IMPLEMENTAÇÃO",
     "intro": "O que a European AI Office publica, orienta e executa — e como isso muda decisões de produto e de conformidade.",
     "focus": "Quem precisa agir: assuntos regulatórios, produto, jurídico e public policy."},
    {"slug": "edpb-ai-guidelines", "title": "EDPB e IA: guidelines, decisões e enforcement",
     "query": "edpb ai guidelines", "theme": "edpb", "sector": None,
     "kicker": "PROTEÇÃO DE DADOS",
     "intro": "Orientações do EDPB com impacto em IA generativa, web scraping, anonimização e decisões automatizadas — e as multas que mostram o padrão de aplicação.",
     "focus": "Quem precisa agir: DPO, privacy, jurídico, engenharia de dados e produto."},
]


def page_lead(core, data, cfg):
    theme_events = [e for e in data["events"]["events"] if cfg["theme"] in e["themes"]][:6]
    if cfg["sector"]:
        sector_data = next((s for s in data["sectors"]["sectors"] if s["slug"] == cfg["sector"]), None)
    else:
        sector_data = None
    deadlines = [m for m in data["deadlines"]["milestones"] if m["days_remaining"] >= 0][:5]
    body = head(cfg["title"], esc(cfg["intro"]), f"MÓDULO 13 · {cfg['kicker']}",
                [("Inteligência regulatória", "/impacto/"), (cfg["title"][:40], None)])
    body += body_open()
    body += f'<p><strong>{esc(cfg["focus"])}</strong></p>'
    if sector_data:
        body += ('<div class="iq-strip">' + badge(f'{sector_data["change_count"]} mudanças classificadas') +
                 badge(f'impacto acumulado {sector_data["cumulative_impact"]}/100', "medium") +
                 priority_badge(sector_data["top_priority"]) + '</div>')
    body += '<h2 class="section-title">Mudanças mais relevantes nesta frente</h2>'
    body += ('<div class="iq-grid c2">' + ''.join(event_ref_card(e) for e in theme_events) +
             '</div>' if theme_events else '<p class="iq-note">Sem item classificado nesta frente no recorte atual.</p>')
    if sector_data and sector_data["obligations"]:
        body += ('<h2 class="section-title">Obrigações potenciais</h2><ul class="iq-list">' +
                 ''.join(f'<li>{esc(o["text"])} <span class="iq-muted">— {esc(o["reference"])}</span></li>'
                         for o in sector_data["obligations"][:5]) + '</ul>')
    body += ('<h2 class="section-title">Próximos prazos</h2><div class="iq-scroll"><table class="iq-table">'
             '<thead><tr><th>Data</th><th>Marco</th><th>Norma</th></tr></thead><tbody>' +
             (''.join(f'<tr><td>{esc(d["date"])}</td><td>{esc(d["obligation"])}</td><td>{esc(_short(d["norm"], 80))}</td></tr>'
                      for d in deadlines) or '<tr><td colspan="3">Sem prazo futuro datado.</td></tr>') +
             '</tbody></table></div><p class="iq-small"><a href="/prazos/">Ver deadline tracker completo →</a></p>')
    body += ('<h2 class="section-title">O que fazer a seguir</h2><ol class="iq-list">'
             '<li>Confirmar na fonte oficial se a obrigação se aplica à sua atividade e ao seu papel na cadeia de valor.</li>'
             '<li>Mapear os sistemas de IA e os dados envolvidos no caso de uso.</li>'
             '<li>Nomear responsável interno e registar a decisão de priorização.</li>'
             '<li>Fixar um ponto de revisão antes do próximo prazo.</li></ol>')
    body += cta_block("Receba alertas regulatórios personalizados para sua empresa.")
    body += body_close()
    return body


# --------------------------------------------------------------------------- #
# Home executiva (Módulo 11)
# --------------------------------------------------------------------------- #
def home_dashboard(core, data):
    events = data["events"]["events"]
    urgent = [e for e in events if e["priority"] in ("urgent", "high")]
    recent_window = [e for e in events if (e["change_date"] or "") >= _days_before(data["deadlines"]["meta"]["reference_date"], 7)]
    attention = len(recent_window) or len(urgent)
    deadlines = [m for m in data["deadlines"]["milestones"] if m["days_remaining"] >= 0][:4]
    alerts = data["alerts"]["alerts"][:3]
    sectors = data["sectors"]["sectors"][:6]
    enforcement = data["enforcement"]["cases"][:3]
    consultations = [e for e in events if e["act_type"] == "consultation"][:3]
    if attention:
        noun = "mudança regulatória exige" if attention == 1 else "mudanças regulatórias exigem"
        headline = f"{attention} {noun} atenção empresarial esta semana"
    else:
        headline = "Nenhuma mudança crítica identificada nesta execução"

    def block(title, link, items, empty):
        content = ''.join(items) if items else f'<li class="iq-muted">{esc(empty)}</li>'
        return (f'<div class="iq-block"><h3>{esc(title)}<a href="{link}">ver tudo →</a></h3><ul>{content}</ul></div>')

    body = ('<section class="block iq-hero-exec" id="painel-executivo"><div class="wrap">'
            '<div class="iq-kicker">DASHBOARD EXECUTIVO · O QUE MUDOU E O QUE FAZER</div>'
            f'<h2 class="iq-h1">{esc(headline)}</h2>'
            '<p class="iq-sub">Leitura em 60 segundos: mudanças críticas, prazos, alertas de alto impacto, '
            'exposição por setor, enforcement e consultas abertas. Cada item tem fonte oficial.</p>'
            '<div class="iq-actions"><a class="iq-btn" href="/impacto/">Abrir o Regulatory Impact Engine</a>'
            '<a class="iq-btn-ghost" href="/prazos/">Ver prazos</a>'
            '<a class="iq-btn-ghost" href="/demo/">Demonstração em 2 minutos</a></div>')
    body += '<div class="iq-grid c3" style="margin-top:18px">'
    body += block("1. Mudanças críticas", "/impacto/", [
        f'<li><a href="/impacto/{esc(e["id"])}/">{esc(_short(e["regulatory_event"], 90))}</a> '
        f'{priority_badge(e["priority"])}<small>{esc(", ".join(e["affected_sectors"][:3]) or "setores a classificar")}'
        f' · {esc(e["change_date"] or "sem data")}</small></li>' for e in urgent[:4]], "Sem mudança crítica registada.")
    body += block("2. Prazos", "/prazos/", [
        f'<li><strong>{esc(d["date"])}</strong> — {esc(d["obligation"])}<small>{esc(_short(d["norm"], 70))} · '
        f'{d["days_remaining"]} dias · ação: {esc(_short(d["action_needed"], 80))}</small></li>' for d in deadlines],
        "Nenhum prazo futuro datado em fonte oficial.")
    body += block("3. Alertas de alto impacto", "/alertas-executivos/", [
        f'<li><a href="/impacto/{esc(a["event_id"])}/">{esc(_short(a["title"], 80))}</a> {impact_badge(a["impact_level"])}'
        f'<small>{esc(a["deadline_label"][:110])}</small></li>' for a in alerts], "Sem alerta de alto impacto.")
    body += '</div><div class="iq-grid c3" style="margin-top:14px">'
    body += block("4. Exposição por setor", "/setores/", [
        f'<li><a href="/setores/{esc(s["slug"])}/">{esc(s["name"])}</a> — {s["change_count"]} mudança(s)'
        f'<small>impacto acumulado {s["cumulative_impact"]}/100 · prioridade {esc(tx.PRIORITIES[s["top_priority"]]["label"])}</small></li>'
        for s in sectors], "Sem setor classificado.")
    body += block("5. Enforcement", "/enforcement/", [
        f'<li><a href="/impacto/{esc(c["id"])}/">{esc(_short(c["event"], 80))}</a>'
        f'<small>{esc(c["authority"])} · {esc(c["date"] or "sem data")} · {esc(c["company_or_sector"])}</small></li>'
        for c in enforcement], "Sem decisão nova de enforcement.")
    body += block("6. Consultas abertas", "/impacto/", [
        f'<li><a href="/impacto/{esc(c["id"])}/">{esc(_short(c["regulatory_event"], 80))}</a>'
        f'<small>{esc(", ".join(c["affected_sectors"][:3]) or "tema transversal")}</small></li>'
        for c in consultations], "Sem consulta aberta com fonte oficial.")
    body += '</div>'
    body += ('<p class="iq-small iq-muted" style="margin-top:14px">'
             f'{data["manifest"]["events_published"]} eventos publicados · '
             f'{data["manifest"]["deadlines_tracked"]} prazos rastreados · '
             f'{data["manifest"]["events_without_official_source"]} sem fonte oficial · '
             f'confiança média {data["manifest"]["confidence_avg"]} · '
             '<a href="/como-analisamos/">como analisamos</a></p>')
    body += '</div></section>'
    return body


def _days_before(ref_iso, days):
    from datetime import date, timedelta
    return (date.fromisoformat(ref_iso) - timedelta(days=days)).isoformat()


# --------------------------------------------------------------------------- #
# Integração com o build
# --------------------------------------------------------------------------- #
NAV_LINKS = [
    ("prazos/", "Prazos"), ("setores/", "Setores"), ("impacto/", "Impacto"),
    ("enforcement/", "Enforcement"), ("empresas/", "Empresas"),
    ("alertas-executivos/", "Alertas"), ("briefing-executivo/", "Briefing"),
    ("demo/", "Demo"),
]


def install(core):
    """Instala a camada de inteligência no gerador estático existente."""
    import build_site_eu_core as core_module  # noqa: WPS433 (import tardio: evita ciclo)

    old_page = core.page
    old_main = core.main

    def iq_page(title, desc, path, body, extra_head="", og_type="website", jsonld=None):
        html = old_page(title, desc, path, body, extra_head, og_type, jsonld)
        assets = ('<link rel="stylesheet" href="/assets/intelligence.css">'
                  '<script src="/assets/intelligence.js" defer></script>')
        html = html.replace("</head>", assets + "</head>", 1)
        nav_links = ''.join(f'<a href="/{u}">{esc(l)}</a>' for u, l in NAV_LINKS)
        html = html.replace('</nav>',
                            f'<a class="iq-nav-divider" href="/produto/" aria-hidden="true">·</a>{nav_links}'
                            f'<a href="/produto/">Planos</a></nav>', 1)
        return html

    def main():
        old_main()
        data = product.build_all(core_module.DATA)
        _write_data(core, data)
        paths = _build_pages(core, data)
        _postprocess(core, data, paths)
        print(f"OK: camada de inteligência — {len(paths)} URLs, "
              f"{data['manifest']['events_published']} eventos, {data['manifest']['deadlines_tracked']} prazos, "
              f"{data['manifest']['events_without_official_source']} sem fonte oficial.")

    core.page = iq_page
    core.main = main


def _write_data(core, data):
    root = Path(core.OUT) / "data" / "intelligence"
    root.mkdir(parents=True, exist_ok=True)
    mapping = {
        "events.json": data["events"], "deadlines.json": data["deadlines"],
        "enforcement.json": data["enforcement"], "sectors.json": data["sectors"],
        "alerts.json": data["alerts"], "briefing.json": data["briefing"],
        "companies.json": data["companies"], "watchlist.json": data["watchlist"],
        "manifest.json": data["manifest"],
    }
    for name, payload in mapping.items():
        (root / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    source = Path(core.BASE) / "data" / "intelligence"
    source.mkdir(parents=True, exist_ok=True)
    for name, payload in mapping.items():
        (source / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _emit(core, paths, path, title, desc, body, private=False, jsonld=None):
    html = core.page(title, desc, path, body, jsonld=jsonld or core.ld_collection(title, desc, path))
    core.write(path + "index.html", html)
    if not private:
        paths.append(path)


def _build_pages(core, data):
    paths = []
    _emit(core, paths, "impacto/", "Regulatory Impact Engine — o que mudou e o que fazer",
          "Eventos regulatórios da UE interpretados: impacto, setores, áreas internas, obrigações, prazos e ações.",
          page_impact_index(core, data))
    for event in data["events"]["events"]:
        _emit(core, paths, f'impacto/{event["id"]}/', f'{_short(event["regulatory_event"], 90)} — análise regulatória',
              _short(event["summary"], 155), event_detail(core, event, None))
    _emit(core, paths, "setores/", "Matriz de impacto por setor — regulação de IA na UE",
          "24 setores com mudanças, obrigações, riscos, prazos e ações recomendadas.", page_sectors_index(core, data))
    for sector in data["sectors"]["sectors"]:
        _emit(core, paths, f'setores/{sector["slug"]}/', f'Regulação de IA para {sector["name"]}',
              _short(sector["focus"], 155), page_sector(core, data, sector))
    _emit(core, paths, "prazos/", "Deadline Tracker — prazos da regulação europeia de IA",
          "Calendário operacional: norma, obrigação, entidade afetada, tempo restante, urgência e ação.",
          page_deadlines(core, data))
    _emit(core, paths, "enforcement/", "Enforcement regulatório — decisões, multas e lições",
          "Decisões e sanções europeias com relação a IA, dados e plataformas digitais, com fonte oficial.",
          page_enforcement(core, data))
    _emit(core, paths, "empresas/", "Company Impact Profile — exposição regulatória",
          "Perfis de exposição regulatória por empresa, com linguagem cautelosa e evidência oficial.",
          page_companies_index(core, data))
    for company in data["companies"]["companies"]:
        _emit(core, paths, f'empresas/{company["slug"]}/', f'{company["name"]} — exposição regulatória provável',
              _short(company["hedge"], 155), page_company(core, data, company))
    _emit(core, paths, "jurisprudencia/", "Jurisprudência da UE — arquitetura de monitoramento",
          "Estrutura para CURIA/TJUE e tribunais nacionais, com fallback controlado e sem jurisprudência inventada.",
          page_jurisprudence(core, data))
    _emit(core, paths, "diff/", "Regulatory Change Diff — versão anterior e versão nova",
          "Comparação de versões de guidelines, códigos de prática, regulamentos e atos delegados.",
          page_diff(core, data))
    _emit(core, paths, "alertas-executivos/", "Alertas regulatórios executivos",
          "Formato executivo: evento, impacto, afeta, áreas internas, o que mudou, ação, prazo e fonte.",
          page_alerts(core, data))
    _emit(core, paths, "briefing-executivo/", "EU AI Regulatory Brief — briefing executivo diário e semanal",
          "Oito seções, leitura de 5 minutos: mudanças críticas, ação, deadlines, enforcement, consultas, AI Act, setores e próximos passos.",
          page_briefing(core, data))
    _emit(core, paths, "demo/", "Demonstração em 2 minutos — European SaaS Company",
          "Caso completo com dados reais: 3 mudanças, 2 prazos, 1 risco alto, 4 áreas e 5 ações.",
          page_demo(core, data))
    _emit(core, paths, "produto/", "LCF EU Regulatory Intelligence — produto e planos",
          "Posicionamento, planos FREE, PRO, BUSINESS e ENTERPRISE e proposta de valor.",
          page_product(core, data))
    _emit(core, paths, "como-analisamos/", "Como analisamos — fato, análise, interpretação e recomendação",
          "Metodologia da camada de inteligência: quatro camadas, escala de confiança e regras de qualidade.",
          page_quality(core, data))
    for cfg in LEAD_PAGES:
        _emit(core, paths, f'{cfg["slug"]}/', cfg["title"], _short(cfg["intro"], 155), page_lead(core, data, cfg))
    return paths



def _watchlist_section(data):
    """Módulo 12 — watchlists prontas (empresa, setor, tema, norma e regulador)."""
    wl = data["watchlist"]
    def chips(items, href_for):
        return ''.join(
            f'<a class="iq-chip" href="{esc(href_for(it))}">{esc(it.get("label") or it.get("name") or it.get("slug"))}'
            f' <span class="iq-muted">{it.get("events", it.get("changes", ""))}</span></a>' for it in items)
    presets = ''.join(
        f'<article class="iq-card"><h3>{esc(p["name"])}</h3>'
        f'<p class="iq-small"><strong>Temas:</strong> {esc(", ".join(p["themes"]) or "—")}</p>'
        f'<p class="iq-small"><strong>Setores:</strong> {esc(", ".join(p["sectors"]) or "—")}</p>'
        f'<p class="iq-small"><strong>Reguladores:</strong> {esc(", ".join(p["regulators"]) or "—")}</p>'
        f'<div class="iq-actions"><a class="iq-btn-ghost" href="/alertas-executivos/">Ver alertas deste recorte</a>'
        f'<a class="iq-btn-ghost" href="/alertas/">Receber por e-mail</a></div></article>'
        for p in wl["presets"])
    body = ('<h2 class="section-title">Watchlists prontas</h2>'
            '<p>Recortes publicados a partir de contagens reais do dataset. Salve itens na watchlist deste navegador '
            'em qualquer análise e, em um piloto autenticado, sincronize a lista com sua conta.</p>'
            f'<div class="iq-grid c3">{presets}</div>'
            '<h2 class="section-title">Por empresa</h2><div class="iq-chips">' +
            chips(wl["companies"], lambda it: f'/empresas/{it["slug"]}/') +
            '</div><h2 class="section-title">Por tema</h2><div class="iq-chips">' +
            chips(wl["themes"], lambda it: '/impacto/') +
            '</div><h2 class="section-title">Por setor</h2><div class="iq-chips">' +
            chips(wl["sectors"], lambda it: f'/setores/{it["slug"]}/') +
            '</div><h2 class="section-title">Por regulador</h2><div class="iq-chips">' +
            chips(wl["regulators"], lambda it: '/enforcement/') +
            '</div><h2 class="section-title">Por tipo de ato</h2><div class="iq-chips">' +
            chips(wl["act_types"], lambda it: '/impacto/') +
            '</div>')
    body += cta_block("Receba alertas regulatórios personalizados para sua empresa.")
    return body

def _postprocess(core, data, paths):
    out = Path(core.OUT)

    # Home executiva
    home = out / "index.html"
    if home.exists():
        html = home.read_text(encoding="utf-8")
        dashboard = home_dashboard(core, data)
        html = html.replace("<main>", "<main>\n" + dashboard, 1)
        html = html.replace("<title>", "<title>", 1)
        hero_old = re.search(r'<p class="lead">.*?</p>', html, re.S)
        hero_new = ('<p class="lead"><strong>LCF EU Regulatory Intelligence</strong> — transformamos mudanças '
                    'regulatórias europeias em decisões acionáveis. O que mudou, por que importa, quem é afetado, '
                    'qual o prazo e o que fazer — com a fonte oficial em cada item.</p>')
        if hero_old:
            html = html[:hero_old.start()] + hero_new + html[hero_old.end():]
        home.write_text(html, encoding="utf-8")

    # Watchlist: presets do Módulo 12 na página existente
    watchlist_page = out / "watchlist" / "index.html"
    if watchlist_page.exists():
        html = watchlist_page.read_text(encoding="utf-8")
        html = html.replace('<div class="wrap commercial-content">',
                            '<div class="wrap commercial-content">' + _watchlist_section(data), 1)
        watchlist_page.write_text(html, encoding="utf-8")

    # Páginas setoriais legadas: apontam para a matriz de impacto
    known = {s["slug"] for s in data["sectors"]["sectors"]}
    for directory in sorted((out / "setores").glob("*/index.html")):
        if directory.parent.name in known:
            continue
        html = directory.read_text(encoding="utf-8")
        note = ('<p class="iq-note" style="margin-bottom:14px"><strong>Matriz de impacto regulatório:</strong> '
                f'{len(known)} setores com mudanças, obrigações, riscos e ações recomendadas em '
                '<a href="/setores/">/setores/</a> · <a href="/prazos/">prazos</a> · '
                '<a href="/impacto/">análises por evento</a>.</p>')
        html = html.replace('<div class="wrap commercial-content">',
                            '<div class="wrap commercial-content">' + note, 1)
        directory.write_text(html, encoding="utf-8")

    # Página de alertas: liga o arquivo executivo
    alerts_page = out / "alertas" / "index.html"
    if alerts_page.exists():
        html = alerts_page.read_text(encoding="utf-8")
        link = ('<p class="iq-note" style="margin-bottom:14px"><strong>Formato executivo:</strong> '
                'veja <a href="/alertas-executivos/">exemplos de alerta com impacto, áreas internas, ação e prazo</a>. '
                'Os alertas filtram por setor, tema, empresa, órgão, nível de impacto e deadline.</p>')
        html = html.replace('<section class="block"><div class="wrap commercial-content">',
                            '<section class="block"><div class="wrap commercial-content">' + link, 1)
        alerts_page.write_text(html, encoding="utf-8")

    # Sitemap: acrescenta as novas URLs às já publicadas
    sitemap = out / "sitemap.xml"
    robots = out / "robots.txt"
    robots_text = robots.read_text(encoding="utf-8") if robots.exists() else None
    existing = []
    if sitemap.exists():
        existing = re.findall(r"<loc>(.*?)</loc>", sitemap.read_text(encoding="utf-8"))
    all_paths = [url[len(core.SITE_URL) + 1:] if url.startswith(core.SITE_URL + "/") else ""
                 for url in existing]
    for path in paths:
        if path not in all_paths:
            all_paths.append(path)
    core.build_sitemap(all_paths)
    if robots_text is not None:
        robots.write_text(robots_text, encoding="utf-8")
