#!/usr/bin/env python3
"""build_intelligence.py — gera a camada de inteligência regulatória (M1–M16).

Lê o dataset oficial (`data/legislation-eu`) e escreve os nove conjuntos de
dados do produto em `data/intelligence/` (a cópia publicada em
`docs/data/intelligence/` é feita pelo build do site).

Uso:

    python3 scripts/build_intelligence.py                 # data/legislation-eu → data/intelligence
    python3 scripts/build_intelligence.py --data DIR --out DIR

Sai com código 1 se houver qualquer evento publicado sem fonte oficial ou com
confiança abaixo do piso: a camada de produto não pode publicar análise sem
evidência.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from regulatory import product  # noqa: E402
from regulatory import taxonomy as tx  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Camada de inteligência regulatória (produto B2B).")
    parser.add_argument("--data", default=os.path.join(BASE, "data", "legislation-eu"),
                        help="diretório do dataset oficial coletado")
    parser.add_argument("--out", default=os.path.join(BASE, "data", "intelligence"),
                        help="diretório de saída dos JSON do produto")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    datasets = product.build_all(args.data, base_dir=os.path.join(BASE, "regulatory"))
    written = product.write_all(datasets, args.out)

    manifest = datasets["manifest"]
    events = datasets["events"]
    deadlines = datasets["deadlines"]
    print(f"OK: inteligência regulatória gerada em {os.path.relpath(args.out, BASE)}/ "
          f"({len(written)} arquivos)")
    print(f"  · eventos publicados: {manifest['events_published']} "
          f"(normas {len([e for e in events['events'] if e['source_kind'] == 'norma'])}, "
          f"procedimentos {len([e for e in events['events'] if e['source_kind'] == 'procedimento'])}, "
          f"atos {len([e for e in events['events'] if e['source_kind'] == 'ato'])}, "
          f"agenda {len([e for e in events['events'] if e['source_kind'] == 'agenda'])}, "
          f"mudanças {len([e for e in events['events'] if e['source_kind'] == 'mudanca'])})")
    print(f"  · excluídos sem relação material: {manifest['events_excluded_no_material_relation']} · "
          f"abaixo do piso: {manifest['events_excluded_low_confidence']} · "
          f"sem fonte oficial: {manifest['events_without_official_source']}")
    print(f"  · confiança {manifest['confidence_min']}–{manifest['confidence_avg']} (média) · "
          f"prioridades: {manifest['events_by_priority']}")
    print(f"  · setores cobertos: {manifest['sectors_covered']}/{manifest['sectors_total']} · "
          f"prazos: {deadlines['meta']['total']} "
          f"(30d {len(deadlines['windows']['d30'])}, 90d {len(deadlines['windows']['d90'])}) · "
          f"enforcement: {manifest['enforcement_cases']} · alertas: {manifest['alerts_generated']}")

    errors = []
    if manifest["events_without_official_source"]:
        errors.append(f"{manifest['events_without_official_source']} evento(s) sem fonte oficial")
    if (manifest["confidence_min"] or 0) < tx.CONFIDENCE_FLOOR:
        errors.append(f"confiança mínima {manifest['confidence_min']} abaixo de {tx.CONFIDENCE_FLOOR}")
    for dataset_name in product.DATA_FILES:
        if not os.path.exists(os.path.join(args.out, f"{dataset_name}.json")):
            errors.append(f"arquivo ausente: {dataset_name}.json")
    if errors:
        print("\nERRO: " + "; ".join(errors), file=sys.stderr)
        return 1
    if not args.quiet:
        with open(os.path.join(args.out, "manifest.json"), encoding="utf-8") as fh:
            json.load(fh)  # sanidade: JSON válido antes de publicar
    return 0


if __name__ == "__main__":
    sys.exit(main())
