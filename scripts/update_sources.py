#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_sources.py — Coleta multiórgão (ANPD, CNJ, TSE, DOU, Planalto, MCTI).

Executa cada conector do pacote `scripts/sources` em um **subprocesso com
timeout próprio** (uma fonte travada não derruba as outras), compara o que foi
coletado com o estado anterior versionado em `data/legislation/atos.json`,
registra as mudanças em `updates.json` (fonte, URL oficial, data do evento,
data da detecção e execução responsável) e devolve o **status de saúde por
fonte** para o painel.

Uso:
    python3 scripts/update_sources.py --listar
    python3 scripts/update_sources.py --fonte anpd            # testa uma fonte
    python3 scripts/update_sources.py --fonte dou --dry-run   # consulta e relata
    python3 scripts/update_sources.py --todos --dry-run       # todas, sem gravar
    python3 scripts/update_sources.py --todos --gravar        # grava atos.json

Regras:
  · Nada é inventado: todo item vem de resposta oficial, com URL oficial;
    campos ausentes ficam ausentes.
  · Falha de uma fonte é registrada (status, erro, endpoints) e **não** é
    escondida: o painel mostra qual órgão falhou na última execução.
  · Execução repetida não duplica: a chave é o id estável derivado da URL
    oficial + hash do texto, comparados contra o estado anterior.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sources import ContextoFonte, FonteIndisponivel, ResultadoFonte, fontes_disponiveis  # noqa: E402
from sources import instanciar  # noqa: E402
from sources.base import BRT, normalizar  # noqa: E402

DATA = os.path.join(BASE, "data", "legislation")
ARQUIVO_ATOS = "atos.json"
ARQUIVO_ARQUIVO_MUDANCAS = "updates_arquivo.json"


def _env_int(nome, padrao):
    try:
        return int(os.environ.get(nome, "") or padrao)
    except ValueError:
        return padrao


TIMEOUT_FONTE_S = _env_int("MONITOR_FONTES_TIMEOUT_S", 150)   # por fonte
# Teto de tempo para o conjunto das fontes novas: garante que a etapa termine
# dentro do orçamento da coleta (Câmara/Senado + build + commit ainda rodam).
LIMITE_TOTAL_FONTES_S = _env_int("MONITOR_FONTES_LIMITE_TOTAL_S", 900)
LIMITE_ATOS_POR_FONTE = _env_int("MONITOR_ATOS_POR_FONTE", 400)
LIMITE_MUDANCAS = _env_int("MONITOR_LIMITE_MUDANCAS", 800)
RETENCAO_DIAS = _env_int("MONITOR_RETENCAO_DIAS", 180)

# Fontes obrigatórias da execução (as demais entram via update_legislation).
FONTES_NOVAS = ["anpd", "cnj", "tse", "dou", "planalto", "mcti"]

# id do tipo de item → tipo do evento registrado em updates.json
TIPO_EVENTO = {
    "resolucao": "nova resolução",
    "regulamento": "nova regulamentação",
    "ato_normativo": "novo ato normativo",
    "consulta_publica": "nova consulta pública",
    "portaria": "nova portaria",
    "lei": "nova lei",
    "decreto": "novo decreto",
    "medida_provisoria": "nova medida provisória",
    "noticia": "nova notícia oficial",
    "publicacao": "nova publicação",
    "decisao": "nova decisão",
    "programa": "novo programa",
    "dados_abertos": "nova base de dados",
    "edital": "novo edital",
}

# Palavras que mudam o tipo do evento (detectadas no título/descrição do ato).
EVENTO_POR_TEXTO = [
    (r"\brevoga", "revogação"),
    (r"\bsancao|\bsanciona|\bpromulg", "sanção"),
    (r"\bveto\b|\bvetado\b|\bvetos\b", "veto"),
    (r"regulament", "regulamentação"),
    (r"consulta publica", "nova consulta pública"),
    (r"\bdecisao\b|\bdecide\b|\bjulgamento\b", "nova decisão"),
    (r"altera(?!cao de texto)", "alteração normativa"),
]


# ------------------------------------------------------------------- utilidades
def agora_brt():
    return datetime.now(BRT)


def ts_iso():
    return agora_brt().isoformat(timespec="seconds")


def load(nome, padrao=None):
    caminho = os.path.join(DATA, nome)
    if not os.path.exists(caminho):
        return padrao
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def save(nome, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, nome), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def inferir_tipo_evento(item):
    """Tipo do evento registrado no histórico (novo item ou alteração)."""
    texto = normalizar(f"{item.get('titulo','')} {item.get('descricao','')}")
    for padrao, tipo in EVENTO_POR_TEXTO:
        if __import__("re").search(padrao, texto):
            return tipo
    return TIPO_EVENTO.get(item.get("tipo") or "", "nova publicação")


# ------------------------------------------------------------- execução da fonte
def executar_fonte(orgao, timeout_s=None, orcamento=None, dry_run=False, logger=print):
    """Executa um conector e devolve {orgao, itens, saude, http}."""
    timeout_s = timeout_s or TIMEOUT_FONTE_S
    t0 = time.monotonic()
    fonte = instanciar(orgao, logger=logger)
    resultado = ResultadoFonte(orgao, fonte.nome)
    ctx = ContextoFonte(orgao, timeout_s=timeout_s, orcamento=orcamento, dry_run=dry_run,
                        logger=logger)
    erro_fatal = None
    try:
        fonte.coletar(ctx, resultado)
    except FonteIndisponivel as e:
        erro_fatal = str(e)
        resultado.erros.append(str(e))
    except Exception as e:  # noqa: BLE001 — falha de uma fonte não derruba a coleta
        erro_fatal = f"{type(e).__name__}: {e}"
        resultado.erros.append(erro_fatal)
    resultado.duracao = time.monotonic() - t0
    return {
        "orgao": orgao,
        "nome": fonte.nome,
        "obrigatoria": bool(getattr(fonte, "obrigatoria", True)),
        "itens": resultado.itens,
        "saude": resultado.como_dict(),
        "http": ctx.cliente.resumo_stats(),
        "erro_fatal": erro_fatal,
    }


def _resultado_falha(orgao, motivo, duracao=0.0, erros=None):
    fonte_nome = orgao
    try:
        fonte_nome = instanciar(orgao, logger=lambda *_: None).nome
    except Exception:  # noqa: BLE001
        pass
    return {
        "orgao": orgao, "nome": fonte_nome, "obrigatoria": True, "itens": [],
        "saude": {
            "nome": fonte_nome, "status": "falha", "ultima_tentativa": ts_iso(),
            "ultima_execucao_ok": None, "itens_consultados": 0, "itens_relevantes": 0,
            "itens_descartados": 0, "itens_duplicados": 0, "revisao_pendente": 0,
            "novidades": 0, "erros": 1,
            "duracao_segundos": round(duracao, 1), "endpoints": [], "canais_ok": [],
            "canais_falhos": ["(execução)"], "canais_falhos_obrigatorios": ["(execução)"],
            "canais_opcionais_falhos": [], "erro_detalhe": motivo,
        },
        "http": {"chamadas": 0, "falhas": 0, "cache": 0, "tempo_total": 0.0,
                 "por_endpoint": {}},
        "erro_fatal": motivo,
    }


def executar_fonte_subprocesso(orgao, timeout_s=None, logger=print):
    """Roda a fonte em subprocesso com timeout rígido (kill se estourar)."""
    timeout_s = timeout_s or TIMEOUT_FONTE_S
    fd, caminho = tempfile.mkstemp(prefix=f"fonte_{orgao}_", suffix=".json")
    os.close(fd)
    cmd = [sys.executable, os.path.abspath(__file__), "--fonte", orgao,
           "--json", caminho, "--timeout", str(timeout_s)]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout_s + 60)
    except subprocess.TimeoutExpired:
        logger(f"    [aviso] {orgao}: timeout de {timeout_s}s + margem — subprocesso morto")
        motivo = f"timeout: a fonte não terminou em {timeout_s}s"
        return _resultado_falha(orgao, motivo, time.monotonic() - t0)
    duracao = time.monotonic() - t0
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError) as e:
        detalhe = (proc.stderr or b"").decode("utf-8", "replace")[-400:]
        motivo = f"subprocesso sem resultado válido ({e}); stderr: {detalhe}"
        if proc.returncode != 0:
            motivo = f"subprocesso saiu com código {proc.returncode}; {motivo}"
        return _resultado_falha(orgao, motivo, duracao)
    finally:
        try:
            os.unlink(caminho)
        except OSError:
            pass
    dados["duracao_subprocesso"] = round(duracao, 1)
    return dados


def executar_todas(orgaos=None, timeout_s=None, usar_subprocesso=True, logger=print,
                   orcamento=None, limite_total_s=None):
    """Executa as fontes novas, isoladas entre si e com teto de tempo total.

    Fonte que não chegou a rodar por falta de tempo entra como **falha**
    explícita ("não executada por orçamento") — nunca como sucesso silencioso.
    """
    orgaos = orgaos or FONTES_NOVAS
    timeout_s = timeout_s or TIMEOUT_FONTE_S
    limite_total_s = limite_total_s or LIMITE_TOTAL_FONTES_S
    t0 = time.monotonic()
    resultados = {}
    for orgao in orgaos:
        restante = limite_total_s - (time.monotonic() - t0)
        if restante < 20:
            motivo = (f"não executada: teto de tempo das fontes esgotado "
                      f"({limite_total_s}s)")
            logger(f"  · fonte '{orgao}': {motivo}")
            resultados[orgao] = _resultado_falha(orgao, motivo)
            continue
        logger(f"  · fonte '{orgao}' (timeout {timeout_s}s"
               + (", subprocesso isolado)" if usar_subprocesso else ")"))
        if usar_subprocesso:
            dados = executar_fonte_subprocesso(orgao, timeout_s, logger=logger)
        else:
            dados = executar_fonte(orgao, timeout_s, orcamento=orcamento, logger=logger)
        resultados[orgao] = dados
        saude = dados["saude"]
        logger(f"    → status={saude['status']} · itens={len(dados['itens'])} "
               f"· consultados={saude['itens_consultados']} "
               f"· canais_ok={len(saude['canais_ok'])} "
               f"· canais_falhos={len(saude['canais_falhos'])}")
    return resultados


# ------------------------------------------------------------------- persistência
def _atos_vazios():
    return {
        "meta": {
            "descricao": ("Atos, publicações e consultas dos órgãos monitorados "
                          "(ANPD, CNJ, TSE, DOU, Planalto e MCTI), coletados "
                          "automaticamente de fontes oficiais."),
            "chave_primaria": "id estável derivado da URL oficial",
            "nota": ("Todo item traz URL oficial, órgão, fonte e as datas de "
                     "detecção. Registros com relevância 'revisar' aguardam "
                     "curadoria editorial. Nada é estimado."),
            "total": 0,
            "por_orgao": {},
            "indice_total": 0,
            "execucao": None,
        },
        "atos": [],
        "indice": {},
    }


def _historico_padrao(atos_f, execucoes_anteriores, orgao, status_atual=None, agora=None):
    """Timestamp da última execução bem-sucedida desta fonte (nunca estimado)."""
    ago = agora or ts_iso()
    if status_atual == "ok":
        return ago
    for ex in execucoes_anteriores or []:
        fonte = (ex.get("fontes_monitoradas") or {}).get(orgao)
        if fonte and fonte.get("status") == "ok":
            return fonte.get("ultima_tentativa") or ex.get("fim") or ex.get("data_hora")
    return None


def mesclar(atos_f, up_f, resultados, exec_info, execucoes_anteriores=None, logger=print):
    """Compara coleta x estado anterior, registra mudanças e devolve o resumo.

    `exec_info` precisa de: id, timestamp (ISO) e data (YYYY-MM-DD).
    Devolve {"fontes_monitoradas", "mudancas", "novidades", "status_global",
    "fontes_falha", "fontes_parciais", "http_fontes"}.
    """
    atos_f.setdefault("atos", [])
    atos_f.setdefault("indice", {})
    atos_f.setdefault("meta", _atos_vazios()["meta"])

    hoje = exec_info["data"]
    mudancas = []
    novos = 0
    alterados = 0
    novidades_por_fonte = {}
    saude_final = {}

    for orgao, dados in resultados.items():
        saude = dados["saude"]
        idx = atos_f["indice"].setdefault(orgao, {})
        por_id = {a["id"]: a for a in atos_f["atos"] if a.get("orgao") == orgao}
        novidades = 0

        for item in dados.get("itens", []):
            item_id = item.get("id")
            if not item_id:
                continue
            anterior = por_id.get(item_id)
            conhecido = idx.get(item_id)
            registro = {
                "id": item_id,
                "orgao": orgao,
                "tipo": item.get("tipo") or "publicacao",
                "titulo": item.get("titulo"),
                "descricao": item.get("descricao") or None,
                "data": item.get("data"),
                "url_oficial": item.get("url_oficial"),
                "fonte": item.get("fonte"),
                "canais": [item.get("canal")] if item.get("canal") else [],
                "relevancia": item.get("relevancia"),
                "revisao_pendente": bool(item.get("revisao_pendente")),
                "situacao": item.get("situacao"),
                "tipo_ato": item.get("tipo_ato"),
                "hierarquia": item.get("hierarquia"),
                "texto_hash": item.get("texto_hash"),
                "ultima_verificacao": exec_info["timestamp"],
                "ultima_execucao": exec_info["id"],
            }
            campos_alterados = []

            if anterior is None:
                if conhecido is None:
                    # item inédito para o monitoramento → novidade
                    registro["primeira_deteccao"] = exec_info["timestamp"]
                    registro["id_execucao_primeira"] = exec_info["id"]
                    registro["historico"] = []
                    novo = True
                    novidades += 1
                else:
                    # já visto em execução anterior, mas fora da janela de retenção
                    registro["primeira_deteccao"] = conhecido.get("d",
                                                                 exec_info["timestamp"])
                    registro["id_execucao_primeira"] = None
                    registro["historico"] = []
                    if conhecido.get("h") and conhecido["h"] != item.get("texto_hash"):
                        campos_alterados.append(("texto", conhecido.get("h"),
                                                 item.get("texto_hash")))
                    novo = False
            else:
                registro["primeira_deteccao"] = anterior.get("primeira_deteccao",
                                                            exec_info["timestamp"])
                registro["id_execucao_primeira"] = anterior.get("id_execucao_primeira")
                registro["historico"] = list(anterior.get("historico") or [])
                registro["canais"] = sorted(set((anterior.get("canais") or [])
                                                + registro["canais"]))
                if anterior.get("texto_hash") != item.get("texto_hash"):
                    campos_alterados.append(("texto", anterior.get("texto_hash"),
                                             item.get("texto_hash")))
                if (anterior.get("situacao") and item.get("situacao")
                        and anterior["situacao"] != item["situacao"]):
                    campos_alterados.append(("situacao", anterior["situacao"],
                                             item["situacao"]))
                novo = False

            # histórico do item (auditoria: nunca sobrescreve em silêncio)
            for campo, de, para in campos_alterados:
                registro["historico"].append({
                    "data_deteccao": exec_info["timestamp"],
                    "id_execucao": exec_info["id"],
                    "campo": campo,
                    "anterior": de,
                    "novo": para,
                })
            if len(registro["historico"]) > 20:
                registro["historico"] = registro["historico"][-20:]

            idx[item_id] = {"h": item.get("texto_hash"), "s": item.get("situacao"),
                            "d": registro["primeira_deteccao"],
                            "v": exec_info["data"]}

            if novo:
                novos += 1
                mudancas.append(_mudanca(registro, exec_info,
                                         tipo=inferir_tipo_evento(registro),
                                         campo=None, de=None, para=None))
            for campo, de, para in campos_alterados:
                alterados += 1
                mudancas.append(_mudanca(
                    registro, exec_info,
                    tipo=("alteração de texto" if campo == "texto"
                          else "alteração de status"),
                    campo=campo, de=de, para=para))

            if novo or campos_alterados or anterior is not None:
                por_id[item_id] = registro

        # retenção: mantém os N mais recentes por fonte (e nunca descarta os
        # últimos RETENCAO_DIAS) — o índice preserva o histórico de comparação.
        registros = sorted(por_id.values(),
                           key=lambda a: (a.get("data") or "", a.get("primeira_deteccao") or ""),
                           reverse=True)
        corte = agora_brt().date() - timedelta(days=RETENCAO_DIAS)
        mantidos, descartados = [], 0
        for i, reg in enumerate(registros):
            antigo = False
            if reg.get("data"):
                try:
                    antigo = datetime.strptime(reg["data"], "%Y-%m-%d").date() < corte
                except ValueError:
                    antigo = False
            if i < LIMITE_ATOS_POR_FONTE or not antigo:
                mantidos.append(reg)
            else:
                descartados += 1
        atos_f["atos"] = [a for a in atos_f["atos"] if a.get("orgao") != orgao] + mantidos

        # limpa o índice de itens não vistos há muito tempo (evita crescimento infinito)
        for k in list(idx):
            visto = idx[k].get("v")
            if visto:
                try:
                    if datetime.strptime(visto, "%Y-%m-%d").date() < corte:
                        del idx[k]
                except ValueError:
                    pass

        nova_saude = dict(saude)
        nova_saude["ultima_execucao_ok"] = _historico_padrao(
            atos_f, execucoes_anteriores, orgao, status_atual=saude["status"])
        nova_saude["novidades"] = novidades
        nova_saude["atos_registrados"] = len(mantidos)
        nova_saude["atos_descartados_por_retencao"] = descartados
        saude_final[orgao] = nova_saude
        novidades_por_fonte[orgao] = novidades
        logger(f"    {orgao}: {len(dados.get('itens', []))} itens relevantes · "
               f"{novidades} novidades · status {saude['status']}")

    atos_f["atos"].sort(key=lambda a: (a.get("data") or "", a.get("primeira_deteccao") or ""),
                        reverse=True)
    por_orgao = {}
    for a in atos_f["atos"]:
        por_orgao[a["orgao"]] = por_orgao.get(a["orgao"], 0) + 1
    atos_f["meta"].update({
        "execucao": hoje,
        "total": len(atos_f["atos"]),
        "por_orgao": dict(sorted(por_orgao.items())),
        "indice_total": sum(len(v) for v in atos_f["indice"].values()),
    })

    status_global = calcular_status_global(saude_final)
    return {
        "fontes_monitoradas": dict(sorted(saude_final.items())),
        "mudancas": mudancas,
        "novidades": novidades_por_fonte,
        "novos": novos,
        "alterados": alterados,
        "status_global": status_global,
        "fontes_falha": sorted(o for o, s in saude_final.items() if s["status"] == "falha"),
        "fontes_parciais": sorted(o for o, s in saude_final.items()
                                  if s["status"] == "parcial"),
        "fontes_ok": sorted(o for o, s in saude_final.items() if s["status"] == "ok"),
        "http_fontes": _somar_http(resultados),
    }


def _mudanca(registro, exec_info, tipo, campo, de, para):
    return {
        "data": registro.get("data") or exec_info["data"],
        "titulo": registro.get("titulo"),
        "descricao": (registro.get("descricao") or "")[:600] or None,
        "tipo": tipo,
        "orgao": registro.get("orgao"),
        "item": registro.get("id"),
        "fonte": registro.get("fonte"),
        "fonte_url": registro.get("url_oficial"),
        "url_oficial": registro.get("url_oficial"),
        "campo_alterado": campo,
        "valor_anterior": de,
        "valor_novo": para,
        "relevancia": registro.get("relevancia"),
        "revisao_pendente": registro.get("revisao_pendente"),
        "data_deteccao": exec_info["data"],
        "timestamp_execucao": exec_info["timestamp"],
        "id_execucao": exec_info["id"],
    }


def _somar_http(resultados):
    total = {"chamadas": 0, "falhas": 0, "cache": 0, "tempo_total": 0.0, "por_orgao": {}}
    for orgao, dados in resultados.items():
        http = dados.get("http") or {}
        total["chamadas"] += http.get("chamadas", 0) or 0
        total["falhas"] += http.get("falhas", 0) or 0
        total["cache"] += http.get("cache", 0) or 0
        total["tempo_total"] += http.get("tempo_total", 0.0) or 0.0
        total["por_orgao"][orgao] = {"chamadas": http.get("chamadas", 0),
                                     "falhas": http.get("falhas", 0),
                                     "tempo_total": http.get("tempo_total", 0.0)}
    total["tempo_total"] = round(total["tempo_total"], 2)
    return total


def calcular_status_global(fontes_monitoradas, camara_senado=None):
    """OK · PARCIAL · FALHA — nunca dá como completa uma coleta incompleta.

    OK       todos os órgãos obrigatórios consultados com sucesso;
    PARCIAL  ao menos uma fonte falhou ou ficou parcial;
    FALHA    nenhuma fonte consultada com sucesso (ou Câmara e Senado falharam).
    """
    saude = dict(fontes_monitoradas or {})
    if camara_senado:
        saude.update(camara_senado)
    if not saude:
        return "FALHA"
    falhas = [o for o, s in saude.items() if (s or {}).get("status") == "falha"]
    consultadas = [o for o, s in saude.items()
                   if (s or {}).get("status") in ("ok", "parcial")]
    if not consultadas:
        return "FALHA"
    if camara_senado:
        casas = [(camara_senado.get("camara") or {}).get("status"),
                 (camara_senado.get("senado") or {}).get("status")]
        if all(c == "falha" for c in casas):
            return "FALHA"
    if falhas or any((s or {}).get("status") == "parcial" for s in saude.values()):
        return "PARCIAL"
    return "OK"


def registrar_mudancas(up_f, mudancas, exec_info, logger=print):
    """Acrescenta as mudanças ao log, sem perder histórico (arquivo separado)."""
    if not mudancas:
        return 0
    existentes = up_f.setdefault("mudancas", [])
    chaves = {(m.get("id_execucao"), m.get("titulo"), m.get("data")) for m in existentes}
    novas = [m for m in mudancas
             if (m.get("id_execucao"), m.get("titulo"), m.get("data")) not in chaves]
    up_f["mudancas"] = existentes + novas
    up_f["mudancas"].sort(key=lambda m: (m.get("data") or "", m.get("titulo") or ""),
                          reverse=True)
    if len(up_f["mudancas"]) > LIMITE_MUDANCAS:
        excedente = up_f["mudancas"][LIMITE_MUDANCAS:]
        up_f["mudancas"] = up_f["mudancas"][:LIMITE_MUDANCAS]
        arquivo = load(ARQUIVO_ARQUIVO_MUDANCAS) or {
            "meta": {"descricao": "Histórico arquivado de mudanças (auditoria; nada "
                                  "é descartado, apenas rotacionado de updates.json)"},
            "mudancas": [],
        }
        ja = {(m.get("id_execucao"), m.get("titulo"), m.get("data"))
              for m in arquivo.get("mudancas", [])}
        arquivo["mudancas"] = arquivo.get("mudancas", []) + [
            m for m in excedente
            if (m.get("id_execucao"), m.get("titulo"), m.get("data")) not in ja]
        arquivo["meta"]["total"] = len(arquivo["mudancas"])
        arquivo["meta"]["execucao"] = exec_info["data"]
        save(ARQUIVO_ARQUIVO_MUDANCAS, arquivo)
        logger(f"    {len(excedente)} mudança(s) rotacionada(s) para "
               f"{ARQUIVO_ARQUIVO_MUDANCAS} (auditoria preservada)")
    up_f.setdefault("meta", {})["mudancas_total"] = len(up_f["mudancas"])
    return len(novas)


# ----------------------------------------------------------------------- CLI
def relatorio_compacto(resultados, limite_amostras=5):
    """Relatório enxuto da coleta (para CI/painel): saúde por fonte + amostras.

    Não substitui o dataset: serve como evidência de teste de cada fonte
    (endpoints consultados, canais que responderam, canais que falharam,
    itens consultados/relevantes e uma amostra dos itens com URL oficial).
    """
    fontes = {}
    for orgao, dados in resultados.items():
        saude = dict(dados.get("saude") or {})
        fontes[orgao] = {
            "nome": saude.get("nome"),
            "status": saude.get("status"),
            "ultima_tentativa": saude.get("ultima_tentativa"),
            "ultima_execucao_ok": saude.get("ultima_execucao_ok"),
            "itens_consultados": saude.get("itens_consultados"),
            "itens_relevantes": saude.get("itens_relevantes"),
            "itens_descartados": saude.get("itens_descartados"),
            "itens_duplicados": saude.get("itens_duplicados"),
            "revisao_pendente": saude.get("revisao_pendente"),
            "novidades": saude.get("novidades"),
            "erros": saude.get("erros"),
            "duracao_segundos": saude.get("duracao_segundos"),
            "endpoints": saude.get("endpoints") or [],
            "canais_ok": saude.get("canais_ok") or [],
            "canais_falhos": saude.get("canais_falhos") or [],
            "canais_falhos_obrigatorios": saude.get("canais_falhos_obrigatorios") or [],
            "canais_opcionais_falhos": saude.get("canais_opcionais_falhos") or [],
            "canais_detalhe": saude.get("canais_detalhe") or [],
            "erro_detalhe": saude.get("erro_detalhe"),
            "http": dados.get("http"),
            "erro_fatal": dados.get("erro_fatal"),
        }
        amostras = []
        for item in (dados.get("itens") or [])[:limite_amostras]:
            amostras.append({
                "id": item.get("id"), "tipo": item.get("tipo"),
                "titulo": item.get("titulo"), "data": item.get("data"),
                "url_oficial": item.get("url_oficial"),
                "relevancia": item.get("relevancia"),
                "revisao_pendente": item.get("revisao_pendente"),
                "hierarquia": item.get("hierarquia"),
                "situacao": item.get("situacao"),
            })
        fontes[orgao]["amostra"] = amostras
    return {
        "gerado_em": ts_iso(),
        "status_global": calcular_status_global(
            {o: f for o, f in fontes.items() if o not in ("camara", "senado")}),
        "fontes": fontes,
    }


def _resumo_texto(dados):
    saude = dados["saude"]
    print(f"[{dados['orgao']}] {dados['nome']}")
    print(f"  status: {saude['status']} · duração {saude['duracao_segundos']}s")
    print(f"  itens consultados: {saude['itens_consultados']} · relevantes: "
          f"{saude['itens_relevantes']} · descartados (tema): {saude['itens_descartados']}")
    print(f"  canais ok: {', '.join(saude['canais_ok']) or '—'}")
    if saude["canais_falhos"]:
        print(f"  canais com falha: {', '.join(saude['canais_falhos'])}")
    if saude.get("erro_detalhe"):
        print(f"  erro: {saude['erro_detalhe'][:400]}")
    for item in dados["itens"][:10]:
        print(f"    - [{item.get('data') or '—'}] ({item.get('tipo')}, "
              f"{item.get('relevancia')}) {item.get('titulo')[:110]}")
        print(f"      {item.get('url_oficial')}")
    if len(dados["itens"]) > 10:
        print(f"    ... (+{len(dados['itens']) - 10} itens)")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Coleta multiórgão do monitor.")
    ap.add_argument("--fonte", help="executa apenas uma fonte")
    ap.add_argument("--todas", action="store_true", help="executa todas as fontes novas")
    ap.add_argument("--listar", action="store_true", help="lista as fontes disponíveis")
    ap.add_argument("--timeout", type=int, default=None,
                    help=f"timeout por fonte em segundos (padrão {TIMEOUT_FONTE_S})")
    ap.add_argument("--json", dest="json_saida",
                    help="grava o resultado bruto da coleta nesse arquivo")
    ap.add_argument("--relatorio", dest="relatorio",
                    help="grava o relatório enxuto da coleta (saúde + amostras)")
    ap.add_argument("--limite-amostras", type=int, default=5,
                    help="itens por fonte no relatório enxuto (padrão 5)")
    ap.add_argument("--dry-run", action="store_true", help="consulta sem gravar")
    ap.add_argument("--gravar", action="store_true",
                    help="grava atos.json (sem executar o coletor legislativo)")
    ap.add_argument("--sem-subprocesso", action="store_true",
                    help="executa as fontes no processo atual (testes)")
    args = ap.parse_args(argv)

    if args.listar:
        for orgao in fontes_disponiveis():
            fonte = instanciar(orgao, logger=lambda *_: None)
            print(f"{orgao:10} {fonte.nome}")
        return 0

    if args.fonte:
        dados = executar_fonte(args.fonte, timeout_s=args.timeout)
        if args.json_saida:
            with open(args.json_saida, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
        if args.relatorio:
            rel = relatorio_compacto({args.fonte: dados},
                                     limite_amostras=args.limite_amostras)
            with open(args.relatorio, "w", encoding="utf-8") as f:
                json.dump(rel, f, ensure_ascii=False, indent=2)
        _resumo_texto(dados)
        if not args.json_saida:
            return 0 if dados["saude"]["status"] != "falha" else 1
        return 0

    if args.todas:
        resultados = executar_todas(timeout_s=args.timeout,
                                    usar_subprocesso=not args.sem_subprocesso)
        for dados in resultados.values():
            _resumo_texto(dados)
        if args.relatorio:
            rel = relatorio_compacto(resultados, limite_amostras=args.limite_amostras)
            with open(args.relatorio, "w", encoding="utf-8") as f:
                json.dump(rel, f, ensure_ascii=False, indent=2)
            print(f"\nrelatório: {args.relatorio} · status global: {rel['status_global']}")
        if args.gravar and not args.dry_run:
            atos_f = load(ARQUIVO_ATOS) or _atos_vazios()
            up_f = load("updates.json") or {"mudancas": [], "execucoes": [], "meta": {}}
            exec_info = {"id": "manual_" + agora_brt().strftime("%Y_%m_%d_%H%M"),
                         "timestamp": ts_iso(), "data": agora_brt().date().isoformat()}
            resumo = mesclar(atos_f, up_f, resultados, exec_info,
                             execucoes_anteriores=up_f.get("execucoes"))
            registrar_mudancas(up_f, resumo["mudancas"], exec_info)
            save(ARQUIVO_ATOS, atos_f)
            save("updates.json", up_f)
            print(f"\nstatus global: {resumo['status_global']} · "
                  f"{len(atos_f['atos'])} atos em {ARQUIVO_ATOS} · "
                  f"{len(resumo['mudancas'])} mudanças registradas")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
