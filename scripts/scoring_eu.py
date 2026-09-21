#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scoring.py — AI Legislative Impact Score: critérios claros e reproduzíveis.

O score (0-100) mede a IMPORTÂNCIA REGULATÓRIA de um procedimento/ato da
União Europeia para o monitoramento de IA — não uma opinião sobre seu mérito
e **não** uma previsão de aprovação ou de comportamento político (essa é uma
regra inegociável do projeto). A mesma função é usada para procedimentos
descobertos automaticamente; os registros curados manualmente seguem esta
mesma rúbrica.

Rúbrica (soma máxima = 100):
  1. Abrangência regulatória ............ 0-20
  2. Estágio do procedimento ............ 0-15
  3. Próximas datas aplicáveis .......... 0-10
  4. Regime do procedimento ............. 0-10
  5. Densidade do dossiê (documentos) ... 0-5
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
    "abrangencia_regulatoria": "Quadro horizontal da UE/AI Act (20) · pilar setorial amplo (12) · tema pontual (6) · simbólico/sem efeito (0-2)",
    "estagio_tramitacao": "Publicado no JO / aplicável (15) · assinado-aguarda JO (13) · adotado pelo plenário (12) · acordo provisório aprovado (11) · trílogos em curso (10) · posição do plenário em 1ª leitura (9) · relatório adotado em comissão (8) · em comissão (6) · encaminhamento recente (4) · início/sem confirmação (2)",
    "proximidade_votacao": "Data de aplicação/obrigação futura confirmada (10) · votação em pauta confirmada (10) · trílogos ativos (6) · agenda não confirmada (2) · sem próximas etapas (0)",
    "urgencia_regime": "Ato delegado/de execução com prazo legal (8) · legislativo ordinário (COD, 5) · especial CNS/CONS (5) · não legislativo NLE/INI (3) · resolução (2)",
    "apensados": "Dossiê com 5+ documentos oficiais (5) · 3-4 (3) · 1-2 (1) · nenhum (0)",
    "impacto_economico": "Mercado único inteiro/sanções milionárias (15) · custos relevantes p/ provedores e utilizadores (9) · efeito moderado (5) · baixo/inexistente (0-2)",
    "impacto_direitos": "Direitos fundamentais/dados/práticas proibidas (10) · trabalho/consumidor/saúde (6) · indireto (3) · nenhum (0)",
    "alcance_setorial": "Multissetorial (5) · 2-3 setores (3) · 1 setor (1)",
    "relevancia_institucional": "Cria/governa autoridade da UE (AI Office, EDPB, mercado) (10) · altera competências relevantes (6) · impacto institucional pontual (3) · nenhum (0)",
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
    """Calcula o score de forma determinística a partir dos campos do registro.

    Recebe um dict com (quando disponíveis): tipo, situacao, ultima_movimentacao,
    documentos, categorias (ids), ementa, titulo, procedimento. Retorna
    {"score": int, "classificacao": str, "detalhe": {...}}. Critério
    conservador: na dúvida, pontua para baixo. Mede impacto — nunca aprovação.
    """
    sit = _norm(prop.get("situacao", ""))
    proc = _norm(prop.get("procedimento", "") or prop.get("tipo", ""))
    ult = _norm((prop.get("ultima_movimentacao") or {}).get("descricao", ""))
    texto = _norm(f"{prop.get('ementa', '')} {prop.get('titulo', '')}")
    cats = set(prop.get("categorias") or [])
    try:
        n_docs = len(prop.get("documentos") or [])
    except (TypeError, ValueError):
        n_docs = 0
    texto_all = f"{sit} {ult} {texto}"
    d = {}

    # 1. Abrangência regulatória (0-20)
    if any(k in texto for k in ("artificial intelligence act", "quadro geral",
                                "harmonised rules", "regulatory framework",
                                "horizontal", "marco geral")):
        d["abrangencia_regulatoria"] = 20 if ("artificial intelligence" in texto
                                              or 1 in cats) else 12
    elif cats & {1, 24, 26, 30}:
        d["abrangencia_regulatoria"] = 12
    elif len(cats) >= 4:
        d["abrangencia_regulatoria"] = 12
    elif len(cats) >= 2:
        d["abrangencia_regulatoria"] = 6
    elif cats:
        d["abrangencia_regulatoria"] = 6
    else:
        d["abrangencia_regulatoria"] = 6
    if any(k in sit for k in ("rejeitad", "retirad", "repealed")):
        d["abrangencia_regulatoria"] = min(d["abrangencia_regulatoria"], 6)

    # 2. Estágio do procedimento (0-15) — apenas estágios oficiais da ficha
    if "publicado no jornal oficial" in sit or "jornal oficial" in ult:
        d["estagio_tramitacao"] = 15
    elif "assinado" in sit:
        d["estagio_tramitacao"] = 13
    elif "votado no plenario" in sit or "votação no plenário" in ult \
            or "adotada pelo plenario" in sit or "adotado pelo plenario" in sit:
        d["estagio_tramitacao"] = 12
    elif "acordo provisorio" in sit:
        d["estagio_tramitacao"] = 11
    elif "negocia" in sit or "trilogo" in sit or "trilogue" in sit:
        d["estagio_tramitacao"] = 10
    elif "inscrito em pauta" in sit or "debate no plenario" in sit:
        d["estagio_tramitacao"] = 9
    elif "relatorio adotado" in sit or "report adopted" in sit:
        d["estagio_tramitacao"] = 8
    elif "comissao" in sit or "parecer" in sit:
        d["estagio_tramitacao"] = 6
    elif "encaminhamento" in sit or "referral" in sit:
        d["estagio_tramitacao"] = 4
    elif "não confirmada" in sit or "nao confirmada" in sit:
        d["estagio_tramitacao"] = 2
    else:
        d["estagio_tramitacao"] = 3

    # 3. Próximas datas aplicáveis (0-10) — somente datas confirmadas oficialmente
    if any(k in texto_all for k in ("aplicável", "aplicavel", "aplicação", "aplicacao",
                                    "applies from", "applicable", "entry into force")):
        d["proximidade_votacao"] = 10
    elif "pauta" in sit or "votação no plenário" in ult:
        d["proximidade_votacao"] = 10
    elif "negocia" in sit or "trilogo" in sit:
        d["proximidade_votacao"] = 6
    elif any(k in sit for k in ("publicado", "resolução adotada", "resolucao adotada")):
        d["proximidade_votacao"] = 2
    else:
        d["proximidade_votacao"] = 2

    # 4. Regime do procedimento (0-10) — tipo do procedimento interinstitucional
    tipo_proc = (re.search(r"\(([A-Z]{2,4})\)", prop.get("procedimento") or "") or [None,
                 None])[1]
    if tipo_proc is None:
        tipo_proc = (prop.get("tipo") or "").upper()
    if tipo_proc in ("REG", "DEC"):
        d["urgencia_regime"] = 8
    elif tipo_proc in ("COD", "CNS", "CONS"):
        d["urgencia_regime"] = 5
    elif tipo_proc in ("NLE", "INI", "APP"):
        d["urgencia_regime"] = 3
    else:
        d["urgencia_regime"] = 2

    # 5. Densidade do dossiê — documentos oficiais vinculados (0-5)
    if n_docs >= 5:
        d["apensados"] = 5
    elif n_docs >= 3:
        d["apensados"] = 3
    elif n_docs >= 1:
        d["apensados"] = 1
    else:
        d["apensados"] = 0

    # 6. Impacto econômico (0-15)
    if any(k in texto for k in ("single market", "mercado unico", "mercado único",
                                "harmonised rules", "fines", "sanctions",
                                "turnover", "chips act", "investeu", "fundo")):
        d["impacto_economico"] = 15 if any(k in texto for k in (
            "single market", "mercado unico", "mercado único", "harmonised rules",
            "fines", "sanctions", "chips act")) else 9
    elif any(k in texto for k in ("providers", "deployers", "suppliers",
                                  "providers and deployers", "obligations",
                                  "compliance", "conformity")):
        d["impacto_economico"] = 9
    elif any(k in texto for k in ("transparency", "watermark", "labelling",
                                  "labeling", "information obligation")):
        d["impacto_economico"] = 5
    else:
        d["impacto_economico"] = 2

    # 7. Impacto sobre direitos (0-10)
    if cats & {2, 3, 5} or any(k in texto for k in (
            "fundamental rights", "prohibited practices", "personal data",
            "biometric", "social scoring", "criminal", "children", "minors")):
        d["impacto_direitos"] = 10
    elif cats & {7, 8, 9, 13, 21} or any(k in texto for k in (
            "worker", "employee", "consumer", "patient", "election", "health")):
        d["impacto_direitos"] = 6
    elif cats:
        d["impacto_direitos"] = 3
    else:
        d["impacto_direitos"] = 3

    # 8. Alcance setorial (0-5)
    setoriais = cats & {7, 8, 9, 10, 11, 12, 13, 19, 20, 21, 23, 28}
    if len(setoriais) >= 3 or 1 in cats:
        d["alcance_setorial"] = 5
    elif len(setoriais) == 2:
        d["alcance_setorial"] = 3
    elif len(setoriais) == 1:
        d["alcance_setorial"] = 1
    else:
        d["alcance_setorial"] = 1

    # 9. Relevância institucional (0-10)
    if any(k in texto for k in ("ai office", "european ai office", "governance",
                                "edpb", "market surveillance", "notified body",
                                "authorities", "supervisory")):
        d["relevancia_institucional"] = 10 if "ai office" in texto or "governance" in texto else 6
    elif any(k in texto for k in ("commission", "committee", "competence",
                                  "enforcement")):
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
