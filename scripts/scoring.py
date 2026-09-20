#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scoring.py — AI Legislative Impact Score: critérios claros e reproduzíveis.

O score (0-100) mede a IMPORTÂNCIA REGULATÓRIA de uma proposição para o
monitoramento de IA, não uma opinião sobre seu mérito. A mesma função é usada
para novas proposições descobertas automaticamente; os scores das proposições
do bootstrap (08/09/2026) foram atribuídos manualmente seguindo esta mesma
rúbrica e são PRESERVADOS como estão (nunca recalculados para gerar manchete).

Rúbrica (soma máxima = 100):
  1. Abrangência regulatória ............ 0-20
  2. Estágio de tramitação .............. 0-15
  3. Proximidade de votação ............. 0-10
  4. Urgência / regime de tramitação .... 0-10
  5. Apensados (quantidade/relevância) .. 0-5
  6. Impacto econômico .................. 0-15
  7. Impacto sobre direitos ............. 0-10
  8. Alcance setorial ................... 0-5
  9. Relevância institucional ........... 0-10

Faixas:
  90-100 CRÍTICO · 75-89 MUITO RELEVANTE · 60-74 RELEVANTE ·
  40-59 MONITORAR · 0-39 BAIXA PRIORIDADE
"""
import re
import unicodedata

RUBRIC_MAX = {
    "abrangencia_regulatoria": 20,
    "estagio_tramitacao": 15,
    "proximidade_votacao": 10,
    "urgencia_regime": 10,
    "apensados": 5,
    "impacto_economico": 15,
    "impacto_direitos": 10,
    "alcance_setorial": 5,
    "relevancia_institucional": 10,
}

RUBRIC_DESCRIPTIONS = {
    "abrangencia_regulatoria": "Marco geral/nacional (20) · setorial amplo (12) · tema pontual (6) · simbólico/arquivado (0-2)",
    "estagio_tramitacao": "À sanção/convertida recente (15) · plenário ou pronta p/ pauta (12) · comissão com parecer (9) · comissão sem parecer (6) · apresentação/distribuição (3) · arquivada (0)",
    "proximidade_votacao": "Pauta marcada/votação iminente (10) · urgência (8) · prioridade (5) · ordinária (2) · arquivada/parada (0)",
    "urgencia_regime": "Urgência constitucional/MP (10) · urgência aprovada (8) · prioridade (5) · ordinária (2)",
    "apensados": "Principal com 10+ apensados (5) · principal com 3-9 (3) · principal com 1-2 (1) · apensada ou sem apensados (0)",
    "impacto_economico": "Efeito fiscal bilionário/setor inteiro (15) · custos relevantes p/ empresas (9) · efeito moderado (5) · baixo/inexistente (0-2)",
    "impacto_direitos": "Direitos fundamentais/dados/penal (10) · consumidor/trabalho (6) · indireto (3) · nenhum (0)",
    "alcance_setorial": "Multissetorial (5) · 2-3 setores (3) · 1 setor (1)",
    "relevancia_institucional": "Cria/governa autoridade nacional (10) · altera competências relevantes (6) · impacto institucional pontual (3) · nenhum (0)",
}


def classify(score):
    if score >= 90:
        return "CRÍTICO"
    if score >= 75:
        return "MUITO RELEVANTE"
    if score >= 60:
        return "RELEVANTE"
    if score >= 40:
        return "MONITORAR"
    return "BAIXA PRIORIDADE"


def _norm(t):
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode("ascii")
    return t.lower()


def compute_impact_score(prop):
    """Calcula o score de forma determinística a partir dos campos da proposição.

    Recebe um dict com (quando disponíveis): tipo, situacao, regime_tramitacao,
    forma_apreciacao, ultima_movimentacao, total_apensados, categorias (ids),
    ementa, titulo. Retorna {"score": int, "classificacao": str, "detalhe": {...}}.
    Critério conservador: na dúvida, pontua para baixo.
    """
    sit = _norm(prop.get("situacao", ""))
    reg = _norm(prop.get("regime_tramitacao", ""))
    apr = _norm(prop.get("forma_apreciacao", ""))
    ult = _norm((prop.get("ultima_movimentacao") or {}).get("descricao", ""))
    texto = _norm(f"{prop.get('ementa', '')} {prop.get('titulo', '')}")
    cats = set(prop.get("categorias") or [])
    total_ap = prop.get("total_apensados") or 0
    try:
        total_ap = int(total_ap)
    except (TypeError, ValueError):
        total_ap = 0
    texto_all = f"{sit} {reg} {apr} {ult} {texto}"
    d = {}

    # 1. Abrangência regulatória (0-20)
    if any(k in texto for k in ("marco legal", "marco regulatorio", "sistema nacional",
                                "normas gerais", "politica nacional", "estatuto")):
        d["abrangencia_regulatoria"] = 20 if ("inteligencia artificial" in texto or 1 in cats) else 12
    elif cats & {1, 24, 26}:
        d["abrangencia_regulatoria"] = 12
    elif len(cats) >= 4:
        d["abrangencia_regulatoria"] = 12
    elif len(cats) >= 2:
        d["abrangencia_regulatoria"] = 6
    elif cats:
        d["abrangencia_regulatoria"] = 6
    else:
        d["abrangencia_regulatoria"] = 6
    if "arquivad" in sit or "prejudicad" in sit:
        d["abrangencia_regulatoria"] = min(d["abrangencia_regulatoria"], 6)

    # 2. Estágio de tramitação (0-15)
    if "arquivad" in sit or "prejudicad" in sit:
        d["estagio_tramitacao"] = 0
    elif "sancao" in sit or "transformada em norma" in sit or "convertida" in texto_all:
        d["estagio_tramitacao"] = 15
    elif "plenario" in sit and ("pront" in sit or "pauta" in sit or "ordem do dia" in sit):
        d["estagio_tramitacao"] = 12
    elif "parecer" in sit and ("aprovad" in sit or "favoravel" in sit):
        d["estagio_tramitacao"] = 9
    elif "parecer" in sit or "comissao" in sit:
        d["estagio_tramitacao"] = 6
    elif "apensad" in sit:
        d["estagio_tramitacao"] = 6
    else:
        d["estagio_tramitacao"] = 3

    # 3. Proximidade de votação (0-10)
    if "arquivad" in sit or "prejudicad" in sit:
        d["proximidade_votacao"] = 0
    elif "pauta" in sit or "ordem do dia" in sit or "votacao" in ult:
        d["proximidade_votacao"] = 10
    elif "urgencia" in texto_all or "urgente" in texto_all:
        d["proximidade_votacao"] = 8
    elif "prioridade" in texto_all:
        d["proximidade_votacao"] = 5
    else:
        d["proximidade_votacao"] = 2

    # 4. Urgência / regime (0-10)
    if prop.get("tipo") in ("MPV", "MP"):
        d["urgencia_regime"] = 10
    elif "urgencia" in texto_all:
        d["urgencia_regime"] = 8
    elif "prioridade" in texto_all:
        d["urgencia_regime"] = 5
    else:
        d["urgencia_regime"] = 2

    # 5. Apensados (0-5)
    if total_ap >= 10:
        d["apensados"] = 5
    elif total_ap >= 3:
        d["apensados"] = 3
    elif total_ap >= 1:
        d["apensados"] = 1
    else:
        d["apensados"] = 0

    # 6. Impacto econômico (0-15)
    if any(k in texto for k in ("regime tributario", "incentivo fiscal", "renuncia",
                                "bilh", "datacenter", "data center", "fundo nacional")):
        d["impacto_economico"] = 15 if any(k in texto for k in ("bilh", "datacenter", "data center", "renuncia")) else 9
    elif any(k in texto for k in ("empresa", "fornecedor", "desenvolvedor", "aplicacao", "multa", "sancao administrativa")):
        d["impacto_economico"] = 9
    elif any(k in texto for k in ("obrigacao", "dever", "vedado", "proibid", "rotul", "transparencia")):
        d["impacto_economico"] = 5
    else:
        d["impacto_economico"] = 2

    # 7. Impacto sobre direitos (0-10)
    if cats & {2, 3, 5} or any(k in texto for k in ("direitos fundamentais", "dados pessoais", "crime", "pena", "prisional", "crianca", "adolescente")):
        d["impacto_direitos"] = 10
    elif cats & {7, 8, 9, 13, 21} or any(k in texto for k in ("trabalh", "consumidor", "eleitor", "saude", "educacao")):
        d["impacto_direitos"] = 6
    elif cats:
        d["impacto_direitos"] = 3
    else:
        d["impacto_direitos"] = 3

    # 8. Alcance setorial (0-5)
    setoriais = cats & {7, 8, 9, 10, 11, 12, 13, 19, 20, 21, 27, 28, 29}
    if len(setoriais) >= 3 or 1 in cats:
        d["alcance_setorial"] = 5
    elif len(setoriais) == 2:
        d["alcance_setorial"] = 3
    elif len(setoriais) == 1:
        d["alcance_setorial"] = 1
    else:
        d["alcance_setorial"] = 1

    # 9. Relevância institucional (0-10)
    if any(k in texto for k in ("sistema nacional", "autoridade", "agencia", "conselho nacional", "anpd", "competencia")):
        d["relevancia_institucional"] = 10 if "sistema nacional" in texto else 6
    elif any(k in texto for k in ("fiscalizacao", "poder executivo", "regulament")):
        d["relevancia_institucional"] = 3
    else:
        d["relevancia_institucional"] = 0

    # Trava conservadora para registros recém-descobertos sem curadoria:
    # nada entra automaticamente como CRÍTICO.
    score = sum(min(v, RUBRIC_MAX[k]) for k, v in d.items())
    if prop.get("revisao_pendente") and score >= 90:
        score = 89
    score = max(0, min(100, int(score)))
    return {"score": score, "classificacao": classify(score), "detalhe": d}


def rubric_table_html():
    rows = "".join(
        f"<tr><td><b>{k.replace('_', ' ').title()}</b></td><td>0–{v}</td>"
        f"<td>{RUBRIC_DESCRIPTIONS[k]}</td></tr>"
        for k, v in RUBRIC_MAX.items()
    )
    return (f'<table class="tbl"><thead><tr><th>Critério</th><th>Pontos</th>'
            f"<th>Como pontuar (resumo)</th></tr></thead><tbody>{rows}</tbody></table>")
