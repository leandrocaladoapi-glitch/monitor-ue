#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_offline.py — Testes offline do pipeline do Monitor Legislativo e
Regulatório de IA da União Europeia.

Não toca na rede nem no dataset do repositório: copia `data/legislation` para
um diretório temporário, substitui a camada HTTP do motor por um simulador
determinístico (respostas no MESMO formato das fontes oficiais — API v2 do
Parlamento, EUR-Lex, Legislative Train, Have Your Say) e a camada multiórgão
por resultados fixos com o mesmo esquema de `update_sources.executar_todas`.
As respostas simuladas reproduzem apenas FORMATOS reais (payloads verificados
nas sondas); nenhum conteúdo do dataset é inventado a partir delas.

Verifica os invariantes que já quebraram em produção:

  1. a coleta respeita o orçamento de tempo e SEMPRE grava o dataset;
  2. execução interrompida (teto por --limite ou orçamento) é registrada como
     `parcial`, com cobertura e procedimentos pendentes explícitos;
  3. MANDATÓRIO (teste final da missão): rodar a coleta duas vezes — a primeira
     popula, a segunda não duplica nada (ids estáveis, zero mudança fantasma);
  4. as métricas de execução (duração, HTTP, fases, snapshot) são preenchidas;
  5. `build_site.py` + `validate_site.py` continuam funcionando depois.

Uso: python3 scripts/selftest_offline.py
Saída: exit 0 se tudo passar; exit 1 com a lista de falhas.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.parse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

import update_legislation as ul  # noqa: E402
import update_sources as us      # noqa: E402

FALHAS = []


def checar(cond, msg):
    if cond:
        print(f"  ok   · {msg}")
    else:
        print(f"  FALHA· {msg}")
        FALHAS.append(msg)


# ----------------------------------------------------------------- simulador
# Formatos idênticos aos payloads reais (sondas registradas em out/probe e
# documentadas no README). Conteúdo mínimo, determinístico, sem inventar
# campos que as fontes não devolvem.

EP_TERM_LIST = {
    "@context": "https://data.europarl.europa.eu/api/v2/core-context.jsonld",
    "data": [{"id": "eli/dl/proc/2024-2526", "type": "Process",
              "process_id": "2024-2526", "process_type": "RSP",
              "label": "2024/2526(RSP)"}],
    "searchResults": {"hits": 1},
    "meta": {"total": 1},
}

def _ev(data, tipo, activity_id, docs=None, fase=None):
    ev = {"id": f"eli/dl/event/{data}_{activity_id}",
          "activity_date": data, "activity_id": activity_id,
          "had_activity_type": f"http://data.europarl.europa.eu/def/ep-activities/{tipo}"}
    if docs:
        ev["recorded_in_a_realization_of"] = docs
    if fase:
        ev["occured_at_stage"] = f"http://data.europarl.europa.eu/def/procedure-phase/{fase}"
    return ev


# Fichas: eventos já presentes no dataset-seed (nenhuma mudança nova deve ser
# gerada na 2ª execução — dedupe por data+tipo+activity_id).
EP_FICHAS = {
    "2021-0106": {
        "id": "eli/dl/proc/2021-0106", "process_id": "2021-0106",
        "process_type": "COD", "label": "2021/0106(COD)",
        "title": ("Regulation laying down harmonised rules on artificial "
                  "intelligence (Artificial Intelligence Act)"),
        "consists_of": [
            _ev("2024-06-13", "SIGNATURE", "SIGN_210106COD_20240613"),
            _ev("2024-07-12", "PUBLICATION_OFFICIAL_JOURNAL",
                "OJ_210106COD_20240712", docs=["OJ_L_202401689"]),
        ],
    },
    "2025-2058": {
        "id": "eli/dl/proc/2025-2058", "process_id": "2025-2058",
        "process_type": "INI", "label": "2025/2058(INI)",
        "title": ("Parliament resolution with recommendations on a EU framework "
                  "for generative AI and transparency of AI systems"),
        "consists_of": [
            _ev("2026-03-10", "PLENARY_VOTE", "PLENARY_2058INI_20260310",
                docs=["P10_TA(2026)0066"]),
        ],
    },
    "2025-0363": {
        "id": "eli/dl/proc/2025-0363", "process_id": "2025-0363",
        "process_type": "COD", "label": "2025/0363(COD)",
        "title": ("Proposal for a Regulation on the safety and trustworthiness "
                  "of artificial intelligence systems in policing"),
        "consists_of": [
            _ev("2025-01-28", "REFERRAL", "REFERRAL_0363COD_20250128", fase="RDG1"),
        ],
    },
}

EURLEX_BUSCA_HTML = """<html><body>
<div class="row">
<h2><a class="title" href="https://eur-lex.europa.eu/legal-content/EN/AUTO/?uri=CELEX:32024R1689&amp;qid=1">Regulation (EU) 2024/1689 of 13 June 2024 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)</a></h2>
<div class="tt_page">CELEX number: 32024R1689</div>
<div class="tt_page">Date of document: 12/07/2024;</div>
<div class="tt_page">OJ L, 12.7.2024</div>
</div>
</body></html>"""

TRAIN_TEMA_URL = ("https://www.europarl.europa.eu/legislative-train/"
                  "theme-a-europe-fit-for-the-digital-age")
TRAIN_TEMA_HTML = """<html><body>
<div class="carriage">
<a href="%s/file-policing-ai-regulation">Artificial Intelligence Act in policing</a>
<div>Status: In treatment in committee</div>
</div>
</body></html>""" % TRAIN_TEMA_URL

TRAIN_FICHA_HTML = """<html><body>
<h1>Artificial Intelligence Act in policing</h1>
<p>Proposal for a regulation COM(2025) 63 — file 2025/0363(COD) on the safety
and trustworthiness of artificial intelligence systems used by police
authorities, amending Regulation (EU) 2024/1689.</p>
</body></html>"""

HYS_HTML = """<html><body>
<div class="initiative">
<a href="/have-your-say/initiatives/16155-EHDS-technical-requirements-for-HealthDataEU_implementing-regulation_en">
European Health Data Space: digital technical requirements for HealthData@EU</a>
<div>Call for evidence: Open</div>
<div>Feedback period 01 September 2026 - 29 September 2026</div>
<div>Type of act Implementing regulation</div>
</div>
</body></html>"""

EDPB_ITEM = {
    "id": "edpb-news-2026-09-11-cnil-extia",
    "tipo": "enforcement",
    "titulo": "Press release: CNIL fines EXTIA EUR 300 000 (GDPR, data subject rights)",
    "descricao": "Sanción the CNIL — EXTIA — EUR 300 000 (art. 12 e 17 GDPR).",
    "data": "2026-09-11",
    "url_oficial": "https://www.edpb.europa.eu/system/files/2026-09/cnil_press_release_en.pdf",
    "fonte": "EDPB — sala de imprensa",
    "relevancia": "forte",
    "texto_hash": "fixture-edpb-cnil-extia-2026-09-11",
}

ORGAOS_FAKES = ["ai_office", "edpb", "edps", "eu_commission", "eu_council",
                "eu_parliament", "eurlex"]


def _saude_fake(orgao, itens_consultados=2):
    return {
        "nome": orgao, "status": "ok", "ultima_tentativa": "2026-09-18T12:00:00-03:00",
        "ultima_execucao_ok": None, "itens_consultados": itens_consultados,
        "itens_relevantes": len([None]), "itens_descartados": 0,
        "itens_duplicados": 0, "revisao_pendente": 0, "novidades": 0, "erros": 0,
        "duracao_segundos": 0.1, "endpoints": [f"https://{orgao}.europa.eu/"],
        "canais_ok": ["canal-fixado-no-selftest"], "canais_falhos": [],
        "erro_detalhe": None,
        "http": {"chamadas": itens_consultados, "falhas": 0, "cache": 0,
                 "tempo_total": 0.1, "por_endpoint": {}},
    }


def _resultados_fake():
    """Mesmo esquema de update_sources.executar_todas: 7 órgãos, EDPB com 1 item."""
    resultados = {}
    for orgao in ORGAOS_FAKES:
        itens = [EDPB_ITEM] if orgao == "edpb" else []
        resultados[orgao] = {
            "orgao": orgao, "nome": orgao, "obrigatoria": True, "itens": itens,
            "saude": _saude_fake(orgao, itens_consultados=max(1, len(itens) + 1)),
            "duracao_segundos": 0.1,
        }
    return resultados


def fake_urllib(url, timeout, as_text=False):
    """Resposta determinística por endpoint (sem rede; formatos oficiais)."""
    time.sleep(0.05)  # latência artificial mínima
    caminho = urllib.parse.urlparse(url)
    u = caminho.netloc + caminho.path
    if "legislative-train" in u:
        texto = TRAIN_FICHA_HTML if "file-" in u else TRAIN_TEMA_HTML
        return texto if as_text else {"_html": texto}
    if "have-your-say" in u:
        return HYS_HTML if as_text else {"_html": HYS_HTML}
    if "eur-lex.europa.eu" in u:
        return EURLEX_BUSCA_HTML if as_text else {"_html": EURLEX_BUSCA_HTML}
    if "data.europarl.europa.eu" in u:
        if "/procedures/" in u:
            pid = caminho.path.rsplit("/", 1)[-1]
            ficha = EP_FICHAS.get(pid)
            return {"data": [ficha]} if ficha else {"data": []}
        return EP_TERM_LIST
    return ("<html></html>" if as_text else {})


def copiar_dataset(destino):
    os.makedirs(destino, exist_ok=True)
    for nome in os.listdir(os.path.join(BASE, "data", "legislation")):
        shutil.copy(os.path.join(BASE, "data", "legislation", nome), destino)
    return destino


def preparar_simulacao(tmp):
    ul.DATA = tmp
    ul._CURL_BIN = None
    ul._http_urllib = fake_urllib        # transporte simulado do motor
    us.executar_todas = lambda **_kw: _resultados_fake()  # camada multiórgão
    ul._HTTP_CACHE.clear()
    with ul._HTTP_LOCK:
        ul._HTTP_STATS.update({"chamadas": 0, "cache": 0, "falhas": 0,
                               "tempo_total": 0.0, "por_endpoint": {}})


def rodar_coletor(tmp, budget_s, max_novas, limite=0):
    """Executa o motor no diretório temporário com HTTP simulado."""
    preparar_simulacao(tmp)
    ul.BUDGET = ul.Budget(budget_s, margem=1)
    ul.MAX_NOVAS = max_novas
    ul.MAX_PROPS = limite
    antes = len(json.load(open(os.path.join(tmp, "updates.json"),
                               encoding="utf-8"))["execucoes"])
    rec = ul.Collector().run(dry_run=False)
    return (rec, os.path.join(tmp, "updates.json"),
            os.path.join(tmp, "propositions.json"), antes)


def testar_camada_http():
    """Cache, contadores e orçamento da camada HTTP do motor (sem rede)."""
    preparar_simulacao(tempfile.mkdtemp(prefix="monitor-selftest-"))
    ul.BUDGET = ul.Budget(60, margem=1)
    url = ("https://data.europarl.europa.eu/api/v2/procedures/2021-0106"
           "?format=application/ld%2Bjson")
    a = ul.http_get_json(url)
    b = ul.http_get_json(url)
    st = ul.http_stats()
    checar(a is not None and a == b, "segunda consulta idêntica vem do cache")
    checar(st["cache"] == 1, f"hit de cache contabilizado ({st['cache']})")
    checar(st["chamadas"] == 1, f"apenas 1 chamada real para URLs repetidas ({st['chamadas']})")
    checar("parlamento:api/v2/procedures" in st["por_endpoint"],
           f"custo por endpoint medido ({list(st['por_endpoint'])})")
    # orçamento esgotado: nenhuma chamada nova é iniciada
    ul.BUDGET = ul.Budget(60, margem=60)   # margem = teto ⇒ expirado de imediato
    try:
        ul.http_get_json(url.replace("2021-0106", "2025-2058"))
        checar(False, "orçamento esgotado deve interromper a coleta")
    except ul.BudgetExceeded:
        checar(True, "orçamento esgotado interrompe a coleta (BudgetExceeded)")


def main():
    print("== 0) Camada HTTP (cache, contadores, orçamento)")
    testar_camada_http()

    print("\n== 1) 1ª coleta (deve popular: status 'concluida', 1 novo procedimento)")
    tmp = copiar_dataset(tempfile.mkdtemp(prefix="monitor-selftest-"))
    props0 = json.load(open(os.path.join(tmp, "propositions.json"), encoding="utf-8"))
    n0 = len(props0["proposicoes"])
    t0 = time.monotonic()
    rec, up_path, props_path, n_exec_antes = rodar_coletor(tmp, budget_s=900, max_novas=2)
    wall = time.monotonic() - t0
    up = json.load(open(up_path, encoding="utf-8"))
    props = json.load(open(props_path, encoding="utf-8"))
    ids1 = [p["id"] for p in props["proposicoes"]]
    checar(wall < 120, f"coleta simulada termina rápido ({wall:.1f}s)")
    # 1ª coleta populou sem erros nem pendências: 'concluida' — a cobertura
    # (<100%) revela que o novo procedimento ainda aguarda 1ª verificação.
    checar(rec["status"] == "concluida", f"1ª coleta populando termina 'concluida' ({rec['status']})")
    checar(len(props["proposicoes"]) == n0 + 1,
           f"1 novo procedimento descoberto no Train ({n0} → {len(props['proposicoes'])})")
    checar("ue_2025_0363_cod" in ids1, "id do novo procedimento é ue_2025_0363_cod (normalizado)")
    checar(all(p.get("impacto", {}).get("score") is not None
               for p in props["proposicoes"]), "todos os procedimentos com score válido")
    checar(rec["cobertura_pct"] < 100,
           f"cobertura < 100% (novo procedimento aguarda 1ª verificação: {rec['cobertura_pct']}%)")
    checar(rec["duracao_segundos"] > 0, f"duração registrada ({rec['duracao_segundos']}s)")
    checar(rec["http"]["chamadas"] > 10, f"chamadas HTTP contabilizadas ({rec['http']['chamadas']})")
    checar(bool(rec["fases_segundos"]), f"fases medidas ({list(rec['fases_segundos'])})")
    checar(rec["snapshot_dataset"]["proposicoes_total"] == len(props["proposicoes"]),
           "snapshot do dataset coerente com propositions.json")
    checar(up["execucoes"][0]["id"] == rec["id"],
           "execução mais recente está no topo de updates.json")
    checar(len(up["execucoes"]) == n_exec_antes + 1,
           f"histórico de execuções preservado e ampliado ({n_exec_antes} → {len(up['execucoes'])})")
    checar(rec.get("novidades_multiorgao", {}).get("edpb") == 1,
           "EDPB (simulado) contribuiu 1 novidade na 1ª coleta")
    checar(all(m.get("fonte_url") for m in up["mudancas"]),
           "toda mudança registrada tem fonte oficial (fonte_url)")
    checar(not any(".leg.br" in json.dumps(m) or "planalto" in json.dumps(m)
                   for m in up["mudancas"]), "nenhuma fonte brasileira nas mudanças")
    atos = json.load(open(os.path.join(tmp, "atos.json"), encoding="utf-8"))
    checar(atos["meta"]["por_orgao"].get("edpb") == 1,
           "item do EDPB registrado em atos.json (com url_oficial)")
    checar(all(a.get("url_oficial") for a in atos["atos"]), "atos.json: todo ato com url_oficial")

    print("\n== 2) 2ª coleta no MESMO diretório (teste final: não duplica, "
          "zero mudança fantasma)")
    rec2, up2_path, props2_path, _ = rodar_coletor(tmp, budget_s=900, max_novas=2)
    up2 = json.load(open(up2_path, encoding="utf-8"))
    props2 = json.load(open(props2_path, encoding="utf-8"))
    mud1 = [json.dumps(m, sort_keys=True) for m in up["mudancas"]]
    mud2 = [json.dumps(m, sort_keys=True) for m in up2["mudancas"]]
    checar(rec2["status"] == "concluida",
           f"2ª execução (nada novo) termina 'concluida' ({rec2['status']})")
    checar(rec2.get("procedimentos_pendentes", rec2.get("proposicoes_pendentes")) == 0,
           "nenhum procedimento pendente na 2ª execução")
    checar(mud2 == mud1,
           f"nenhuma mudança nova na 2ª execução ({len(mud1)} → {len(mud2)})")
    checar(len(mud2) == len(set(mud2)), "nenhuma mudança duplicada em updates.json")
    checar(len(props2["proposicoes"]) == len(props["proposicoes"]),
           "nenhum procedimento duplicado na 2ª execução")
    checar([p["id"] for p in props2["proposicoes"]] == ids1,
           "ids dos procedimentos estáveis entre execuções")
    checar(rec2["cobertura_pct"] == 100, f"cobertura integral na 2ª execução ({rec2['cobertura_pct']}%)")
    checar(rec2.get("novidades_multiorgao", {}).get("edpb") == 0,
           "EDPB: item conhecido não gera novidade na 2ª coleta")
    atos2 = json.load(open(os.path.join(tmp, "atos.json"), encoding="utf-8"))
    checar(len(atos2["atos"]) == len(atos["atos"]),
           "atos.json sem duplicação na 2ª coleta")

    print("\n== 3) Execução interrompida (--limite 1 → 'parcial' explícito)")
    tmp3 = copiar_dataset(tempfile.mkdtemp(prefix="monitor-selftest-"))
    snap3 = os.path.join(tmp3, "propositions.json")
    antes3 = json.load(open(snap3, encoding="utf-8"))
    rec3, _, _, _ = rodar_coletor(tmp3, budget_s=900, max_novas=0, limite=1)
    depois3 = json.load(open(snap3, encoding="utf-8"))
    checar(rec3["status"] == "parcial", f"status da execução é 'parcial' ({rec3['status']})")
    checar(rec3.get("procedimentos_pendentes", rec3.get("proposicoes_pendentes")) > 0,
           "procedimentos pendentes registrados")
    checar(rec3["cobertura_pct"] < 100, f"cobertura inferior a 100% ({rec3['cobertura_pct']}%)")
    checar(len(depois3["proposicoes"]) == len(antes3["proposicoes"]),
           "dataset íntegro após execução parcial (sem perda de procedimentos)")
    checar(all(p.get("impacto", {}).get("score") is not None
               for p in depois3["proposicoes"]), "scores válidos após execução parcial")

    print("\n== 4) Build do site a partir do dataset atual (real, sem mock)")
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "build_site.py")],
                       capture_output=True, text=True, cwd=BASE)
    checar(r.returncode == 0, f"build_site.py executou ({(r.stdout or r.stderr).strip()[:80]})")
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "validate_site.py")],
                       capture_output=True, text=True, cwd=BASE)
    checar(r.returncode == 0, f"validate_site.py passou ({(r.stdout or '').strip().splitlines()[-1:]})")

    for t in (tmp, tmp3):
        shutil.rmtree(t, ignore_errors=True)

    print()
    if FALHAS:
        print(f"AUTOTESTE FALHOU — {len(FALHAS)} verificação(ões):")
        for f in FALHAS:
            print(f"  - {f}")
        return 1
    print("AUTOTESTE OK — orçamento, persistência, dedup duplo e métricas funcionando.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
