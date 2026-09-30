# Auditoria completa — Monitor UE → LCF EU Regulatory Intelligence

Data da auditoria: 2026-09-29 · Branch: `arena/01a0efb6-monitor-ue` · Base: `f52a74a`

## 1. O que o repositório é hoje

| Camada | Arquivos | Estado |
|---|---|---|
| Dataset UE | `data/legislation-eu/*.json` (8 arquivos, 1,0 MB) | 4 procedimentos, 2 normas, 19 atos, 1 evento, 79 mudanças, 27 execuções. Fontes oficiais ao lado de cada item. |
| Coleta UE | `scripts/update_legislation_eu.py`, `scripts/update_sources_eu.py`, `scripts/sources/{eu_*,ai_office,edpb,edps,eurlex}.py`, `probe_sources_eu.py` | Ativa, com orçamento HTTP e dedupe |
| Build UE | `scripts/build_site.py` → `build_site_eu_core.py` (2.017 linhas) | 14 páginas base + 25 páginas comerciais; paridade de domínio validada |
| Camada comercial | `commercial/{intelligence,alerts,service,store,notify}.py`, `scripts/commercial_pages.py`, `config/commercial.json` | Leads, alertas, login/app, watchlist local |
| AEO/SEO | `ai_visibility_eu.py`, `google_ai_citation_eu.py` | llms.txt, agent-permissions, JSON-LD |
| Validação | `validate_site_eu.py`, `selftest_offline_eu.py`, 7 suítes (`unittest`, 71 testes) | Verdes |
| Legado BR | `build_site_core.py`, `scoring.py`, `update_legislation.py`, `update_sources.py`, `probe_sources.py`, `selftest_offline.py`, `ai_visibility.py`, `google_ai_citation.py`, `sources/{anpd,cnj,dou,mcti,planalto,tse}.py`, `data/legislation/`, `build_site_eu.py`, `validate_site.py` | **Morto para o produto EU** (1,1 MB de código + dataset) |

## 2. Lacunas frente ao produto pedido

| # | Módulo pedido | Estado hoje | Gap |
|---|---|---|---|
| 1 | Regulatory Impact Engine | `business_impact()` devolve 11 campos genéricos e idênticos para quase todo item | **Não existe** estrutura de evento regulatório, obrigações, ações, prioridade, confiança |
| 2 | Matriz por setor | 9 páginas setoriais, sem obrigações/riscos/prazos/ações | 15 setores faltando e nenhuma inteligência setorial |
| 3 | Company Impact Profile | inexistente | criar `/empresas/*` com linguagem cautelosa |
| 4 | Deadline Tracker | inexistente (a agenda lista eventos) | datas do AI Act e do Digital Omnibus estão no dataset, sem tracker |
| 5 | Regulatory Alerts | alerta = lista de títulos + score | sem formato executivo (impacto, áreas, ação, prazo) |
| 6 | Executive Briefing | 1 página com mudanças + top 5 | falta o formato de 8 seções e recorte diário/semanal |
| 7 | "So what?" | `por_que_importa` genérico | falta bloco "O que isso significa na prática?" por item |
| 8 | Enforcement | inexistente | 4 mudanças de enforcement e 10 atos EDPB no dataset |
| 9 | Jurisprudência | declarado sem conector | criar arquitetura com fallback honesto |
| 10 | Regulatory Change Diff | `updates.json` guarda hash anterior/novo | diff não é exibido; criar `/diff/` |
| 11 | Dashboard executivo | home orientada a volume de dados | home não responde "o que fazer" |
| 12 | Watchlist | local por navegador | falta recorte por setor/tema/norma/regulador |
| 13 | Lead generation | 0 páginas de intenção de busca | criar 8 páginas-alvo |
| 14 | Produto comercial | 4 ofertas em BRL genéricas | criar posicionamento + planos FREE/PRO/BUSINESS/ENTERPRISE |
| 15 | Demo comercial | inexistente | criar `/demo/` |
| 16 | Metodologia/confiança | score único | falta separação FATO/ANÁLISE/INTERPRETAÇÃO/RECOMENDAÇÃO e `confidence_score` |
| 17 | Qualidade de dados | duplicidade BR/EU no repo | consolidar sem quebrar produção |
| 18 | Testes | 71 testes de fiação | faltam integridade JSON, fontes, deadlines, engine, páginas, links |
| 19 | UX | shell dark consistente | falta hierarquia executiva (impacto → prazo → ação) |
| 20 | Priorização | — | seguir P0→P2 |

## 3. Decisão de arquitetura

Não reescrever. Acrescentar **uma camada** sobre o dataset existente:

```
data/legislation-eu/*.json        (preservado, fonte única de fatos)
        ↓
regulatory/  (novo pacote: taxonomia, impact engine, deadlines, enforcement,
              empresas, briefing, alertas, qualidade)
        ↓
data/intelligence/*.json          (novo dataset acionável, versionado)
        ↓
scripts/intelligence_pages.py     (novas páginas + home executiva)
        ↓
docs/                             (site público, mesmo domínio)
```

Regras de produto embutidas no código (não só em texto):

1. Nenhum evento publicado sem URL oficial em `*.europa.eu` (ou EDPB/EDPS/EP).
2. `confidence < 0.6` → não publica, vai para `excluded` no relatório de build.
3. Fato, análise, interpretação e recomendação são objetos distintos no JSON e blocos distintos no HTML.
4. Linguagem de exposição: "potencialmente afetada", "exposição provável", "requer avaliação jurídica específica".
5. Prioridade calculada por rúbrica pública, nunca "probabilidade de aprovação".

## 4. Execução

Ver `reports/ENTREGA-INTELIGENCIA-REGULATORIA.md` (relatório final) para o que foi implementado,
testado e validado, e `reports/ARQUIVOS-ALTERADOS-2026-09-29.md` para o inventário de arquivos.
