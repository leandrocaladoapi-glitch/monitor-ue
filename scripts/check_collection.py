"""Fail the scheduled run when the latest collection is stale or incomplete.

Critério: a execução mais recente precisa estar concluída, com cobertura
integral e sem erros/pendências, com data do dia corrente (os timestamps do
dataset são gerados no fuso BRT — decisão documentada no README, mantida por
estabilidade dos run_id).
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BRT = timezone(timedelta(hours=-3))

def problems(record, now=None):
    now = now or datetime.now(BRT)
    errors = []
    try:
        finished = datetime.fromisoformat(record.get("fim") or record["data_hora"])
        if finished.tzinfo is None:
            raise ValueError("timestamp without timezone")
        if finished.astimezone(BRT).date() != now.astimezone(BRT).date():
            errors.append("A última coleta não é do dia corrente em Brasília.")
        if finished > now:
            errors.append("A coleta possui data futura.")
    except (KeyError, TypeError, ValueError):
        errors.append("Data da coleta ausente ou inválida.")
    if record.get("status") != "concluida":
        errors.append("Coleta não concluída.")
    try:
        if float(record.get("cobertura_pct", 0)) < 100:
            errors.append("Cobertura inferior a 100%.")
    except (TypeError, ValueError):
        errors.append("Cobertura inválida.")
    pendentes = record.get("procedimentos_pendentes",
                           record.get("proposicoes_pendentes"))
    if record.get("erros") or pendentes:
        errors.append("Há erros ou procedimentos pendentes.")
    return errors

def main():
    try:
        data = json.loads(Path("data/legislation/updates.json").read_text())
        found = problems((data.get("execucoes") or [{}])[0])
    except (OSError, ValueError, TypeError, AttributeError):
        found = ["Não foi possível verificar o registro da coleta."]
    for message in found:
        print("::error::" + message)
    if not found:
        print("Coleta do dia concluída, cobertura integral e sem erros.")
    return int(bool(found))

if __name__ == "__main__":
    sys.exit(main())
