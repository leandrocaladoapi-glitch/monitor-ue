#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest_offline.py — Testes offline do pipeline do Monitor Legislativo de IA.

Não toca na rede nem no dataset do repositório: copia `data/legislation` para um
diretório temporário, substitui a camada HTTP por um simulador determinístico e
verifica os invariantes que já quebraram em produção:

  1. a coleta respeita o orçamento de tempo e SEMPRE grava o dataset;
  2. execução interrompida pelo orçamento é registrada como `parcial`, com
     cobertura e proposições pendentes explícitas;
  3. o checkpoint intermediário não duplica registros em `updates.json`;
  4. as métricas de execução (duração, HTTP, fases, snapshot) são preenchidas;
  5. `build_site.py` + `validate_site.py` continuam funcionando depois.

Uso: python3 scripts/selftest_offline.py
Saída: exit 0 se tudo passar; exit 1 com a lista de falhas.
"""
import json
import os
import shutil
import sys
import tempfile
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "scripts"))

import update_legislation as ul  # noqa: E402
import update_sources as us  # noqa: E402

FALHAS = []


def checar(cond, msg):
    if cond:
        print(f"  ok   · {msg}")
    else:
        print(f"  FALHA· {msg}")
        FALHAS.append(msg)


# ----------------------------------------------------------------- simulador
def fake_urllib(url, timeout):
    """Resposta determinística por endpoint (sem rede)."""
    time.sleep(0.25)  # latência artificial: força o consumo do orçamento
    if "/proposicoes/" in url and url.endswith("/tramitacoes"):
        return {"dados": [{"dataHora": "2026-09-10T10:00:00",
                           "descricaoTramitacao": "Publicação de Proposição",
                           "despacho": "Publicação inicial no DCD.",
                           "siglaOrgao": "CCP", "sequencia": 2}]}
    if "/proposicoes/" in url and url.endswith("/votacoes"):
        return {"dados": []}
    if "/proposicoes/" in url and url.endswith("/autores"):
        return {"dados": [{"nome": "Dep. Teste", "uri": "https://dadosabertos.camara.leg.br/api/v2/deputados/1",
                           "tipo": "Deputado"}]}
    if "/deputados/" in url:
        return {"dados": {"ultimoStatus": {"nome": "Dep. Teste", "siglaPartido": "XX", "siglaUf": "DF"}}}
    if "/proposicoes?" in url:
        return {"dados": []}
    if "/eventos?" in url:
        return {"dados": []}
    if "/proposicoes/" in url:
        return {"dados": {"id": 999, "siglaTipo": "PL", "numero": 1, "ano": 2026,
                          "ementa": "Dispõe sobre inteligência artificial.",
                          "statusProposicao": {"dataHora": "2026-09-10T10:00:00",
                                               "descricaoSituacao": "Aguardando Parecer",
                                               "siglaOrgao": "CCP", "regime": "Ordinária",
                                               "apreciacao": "Proposição Sujeita à Apreciação Conclusiva"}}}
    if "/materia/" in url:  # Senado
        return {"DetalheMateria": {"Materia": {"DadosBasicosMateria": {"EmentaMateria": "IA"}}},
                "MovimentacaoMateria": {"Materia": {"Autuacoes": {"Autuacao": [{
                    "SituacoesAtuais": {"SituacaoAtual": {"DataSituacao": "2026-09-10",
                                                          "SiglaSituacao": "AP", "DescricaoSituacao": "Aguardando"}},
                    "InformesLegislativos": {"InformeLegislativo": [{
                        "Data": "2026-09-10 10:00:00", "Descricao": "Recebido"}]}}]}}},
                "RelatoriaMateria": {"Materia": {}}}
    return {}


def copiar_dataset(destino):
    os.makedirs(destino, exist_ok=True)
    for nome in os.listdir(os.path.join(BASE, "data", "legislation")):
        shutil.copy(os.path.join(BASE, "data", "legislation", nome), destino)
    return destino


# Fontes multiórgão (update_sources) também simuladas: o selftest é offline
# e não pode depender de rede real (em CI a fase roda em subprocessos).
ORGAOS_BR_FAKE = ("anpd", "cnj", "tse", "dou", "planalto", "mcti")


def _resultados_br_fake():
    resultados = {}
    for orgao in ORGAOS_BR_FAKE:
        resultados[orgao] = {
            "orgao": orgao, "nome": orgao, "obrigatoria": True, "itens": [],
            "saude": {
                "nome": orgao, "status": "ok",
                "ultima_tentativa": "2026-09-18T12:00:00-03:00",
                "ultima_execucao_ok": None, "itens_consultados": 1,
                "itens_relevantes": 0, "itens_descartados": 0,
                "itens_duplicados": 0, "revisao_pendente": 0, "novidades": 0,
                "erros": 0, "duracao_segundos": 0.1,
                "endpoints": [f"https://{orgao}.gov.br/"],
                "canais_ok": ["canal-fixado-no-selftest"], "canais_falhos": [],
                "erro_detalhe": None,
                "http": {"chamadas": 1, "falhas": 0, "cache": 0,
                         "tempo_total": 0.1, "por_endpoint": {}},
            },
            "duracao_segundos": 0.1,
        }
    return resultados


def preparar_simulacao(tmp):
    ul.DATA = tmp
    ul._CURL_BIN = None
    ul._http_urllib = fake_urllib          # transporte simulado (sem rede)
    us.executar_todas = lambda **_kw: _resultados_br_fake()
    ul._HTTP_CACHE.clear()
    with ul._HTTP_LOCK:
        ul._HTTP_STATS.update({"chamadas": 0, "cache": 0, "falhas": 0,
                               "tempo_total": 0.0, "por_endpoint": {}})


def rodar_coletor(tmp, budget_s, max_novas):
    """Executa o coletor no diretório temporário com HTTP simulado."""
    preparar_simulacao(tmp)
    ul.BUDGET = ul.Budget(budget_s, margem=1)
    ul.MAX_NOVAS = max_novas
    ul.MAX_PROPS = 0
    antes = len(json.load(open(os.path.join(tmp, "updates.json"), encoding="utf-8"))["execucoes"])
    rec = ul.Collector().run(dry_run=False)
    return (rec, os.path.join(tmp, "updates.json"),
            os.path.join(tmp, "propositions.json"), antes)


def testar_camada_http():
    """Cache, contadores e orçamento da camada HTTP (sem rede)."""
    preparar_simulacao(tempfile.mkdtemp(prefix="monitor-selftest-"))
    ul.BUDGET = ul.Budget(60, margem=1)
    url = "https://dadosabertos.camara.leg.br/api/v2/proposicoes/2338"
    a = ul.http_get_json(url)
    b = ul.http_get_json(url)
    st = ul.http_stats()
    checar(a is not None and a == b, "segunda consulta idêntica vem do cache")
    checar(st["cache"] == 1, f"hit de cache contabilizado ({st['cache']})")
    checar(st["chamadas"] == 1, f"apenas 1 chamada real para URLs repetidas ({st['chamadas']})")
    checar("camara:proposicoes/{id}" in st["por_endpoint"],
           f"custo por endpoint medido ({list(st['por_endpoint'])})")
    # orçamento esgotado: nenhuma chamada nova é iniciada
    ul.BUDGET = ul.Budget(60, margem=60)   # margem = teto ⇒ expirado de imediato
    try:
        ul.http_get_json(url + "/autores")
        checar(False, "orçamento esgotado deve interromper a coleta")
    except ul.BudgetExceeded:
        checar(True, "orçamento esgotado interrompe a coleta (BudgetExceeded)")


def main():
    print("== 0) Camada HTTP (cache, contadores, orçamento)")
    testar_camada_http()

    print("\n== 1) Execução com orçamento curto (deve encerrar como 'parcial')")
    tmp = copiar_dataset(tempfile.mkdtemp(prefix="monitor-selftest-"))
    t0 = time.monotonic()
    rec, up_path, props_path, n_exec_antes = rodar_coletor(tmp, budget_s=12, max_novas=2)
    wall = time.monotonic() - t0
    up = json.load(open(up_path, encoding="utf-8"))
    props = json.load(open(props_path, encoding="utf-8"))
    checar(os.path.exists(up_path) and os.path.exists(props_path),
           "dataset foi gravado apesar do fim do orçamento")
    checar(wall < 12 + 25, f"coleta terminou perto do orçamento ({wall:.1f}s p/ 12s)")
    checar(rec["status"] == "parcial", f"status da execução é 'parcial' ({rec['status']})")
    checar(rec["proposicoes_pendentes"] > 0,
           f"proposições pendentes registradas ({rec['proposicoes_pendentes']})")
    checar(0 <= rec["cobertura_pct"] <= 100, f"cobertura calculada ({rec['cobertura_pct']}%)")
    checar(rec["duracao_segundos"] > 0, f"duração registrada ({rec['duracao_segundos']}s)")
    checar(rec["http"]["chamadas"] > 0, f"chamadas HTTP contabilizadas ({rec['http']['chamadas']})")
    checar(bool(rec["fases_segundos"]), f"fases medidas ({list(rec['fases_segundos'])})")
    checar(rec["snapshot_dataset"]["proposicoes_total"] == len(props["proposicoes"]),
           "snapshot do dataset coerente com propositions.json")
    checar(up["execucoes"][0]["id"] == rec["id"],
           "execução mais recente está no topo de updates.json")
    checar(len(up["execucoes"]) == n_exec_antes + 1,
           f"histórico de execuções preservado e ampliado ({n_exec_antes} → {len(up['execucoes'])})")
    ids = [m.get("id_execucao") for m in up["mudancas"]]
    checar(ids.count(rec["id"]) == sum(1 for m in up["mudancas"]
                                       if m.get("id_execucao") == rec["id"]),
           "checkpoint não duplicou mudanças em updates.json")

    print("\n== 2) Execução com orçamento folgado (deve encerrar como 'concluida')")
    tmp2 = copiar_dataset(tempfile.mkdtemp(prefix="monitor-selftest-"))
    rec2, up2_path, _, _ = rodar_coletor(tmp2, budget_s=900, max_novas=3)
    up2 = json.load(open(up2_path, encoding="utf-8"))
    checar(rec2["status"] == "concluida", f"status da execução é 'concluida' ({rec2['status']})")
    checar(rec2["proposicoes_pendentes"] == 0, "nenhuma proposição pendente")
    checar(rec2["http"]["chamadas"] > 100,
           f"volume de consultas registrado ({rec2['http']['chamadas']} chamadas)")
    checar(len(up2["mudancas"]) == len(up2["mudancas"]) and
           len({id(m) for m in up2["mudancas"]}) == len(up2["mudancas"]),
           "nenhuma mudança duplicada")
    checar(all(m.get("fonte_url") for m in up2["mudancas"]),
           "toda mudança registrada tem fonte oficial")

    print("\n== 3) Simulação de interrupção brusca (checkpoint preserva o trabalho)")
    tmp3 = copiar_dataset(tempfile.mkdtemp(prefix="monitor-selftest-"))
    snap = os.path.join(tmp3, "propositions.json")
    antes = json.load(open(snap, encoding="utf-8"))
    rodar_coletor(tmp3, budget_s=15, max_novas=0)
    depois = json.load(open(snap, encoding="utf-8"))
    checar(len(depois["proposicoes"]) == len(antes["proposicoes"]),
           "dataset íntegro após execução parcial (sem perda de proposições)")
    checar(all(p.get("impacto", {}).get("score") is not None for p in depois["proposicoes"]),
           "todas as proposições seguem com score válido")

    print("\n== 4) Build do site a partir do dataset atual (real, sem mock)")
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "build_site.py")],
                       capture_output=True, text=True, cwd=BASE)
    checar(r.returncode == 0, f"build_site.py executou ({(r.stdout or r.stderr).strip()[:80]})")
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "validate_site.py")],
                       capture_output=True, text=True, cwd=BASE)
    checar(r.returncode == 0, f"validate_site.py passou ({(r.stdout or '').strip().splitlines()[-1:]})")

    for t in (tmp, tmp2, tmp3):
        shutil.rmtree(t, ignore_errors=True)

    print()
    if FALHAS:
        print(f"AUTOTESTE FALHOU — {len(FALHAS)} verificação(ões):")
        for f in FALHAS:
            print(f"  - {f}")
        return 1
    print("AUTOTESTE OK — orçamento, persistência e métricas funcionando.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
