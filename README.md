# Monitor UE de IA — Monitor Exclusivo da União Europeia

**Sistema de inteligência legislativa e regulatória** — monitoramento público, documentado e auditável de toda a atividade legislativa e regulatória da **União Europeia** relacionada à Inteligência Artificial, exclusivamente em **https://monitor-ue.vercel.app/**.

> **Este repositório é EXCLUSIVO da União Europeia.** Não há monitor brasileiro. Todo o conteúdo, dataset, conectores, crons e páginas referem-se ao AI Act e à regulação de IA da UE. O domínio oficial é **https://monitor-ue.vercel.app/** — qualquer referência ao domínio brasileiro antigo é legada e foi removida, e qualquer acesso pelo domínio antigo (`monitor.lcfconsulting.com.br`) é redirecionado (301) para o domínio oficial (`vercel.json`).

O ativo principal é o **dataset legislativo e regulatório histórico da UE** (`/data/legislation-eu`), estruturado e continuamente atualizado. O site em `/docs` é a interface pública desse dataset, publicado pela Vercel.

- **Site oficial:** https://monitor-ue.vercel.app/ (publicado a partir de `/docs` pela Vercel)
- **Dados:** `/data/legislation-eu/*.json` (fonte única da verdade, versionada no Git)
- **Build:** `python3 scripts/build_site.py` (sem dependências externas, exclusivo UE)

---

## O que este repositório monitora (UE)

- Procedimentos legislativos interinstitucionais da UE sobre IA (COD, CNS, NLE, INI, REG — atos delegados e de execução)
- AI Act (Regulamento (UE) 2024/1689) — procedimento 2021/0106(COD) — e atos correlatos (DSA, DMA, Data Act, EHDS, etc. quando com relação direta a IA)
- Atos adotados e publicados no Jornal Oficial da UE (EUR-Lex, CELEX, ELI)
- Documentos do Conselho da UE (registro público)
- Propostas, consultas públicas e feedbacks da Comissão Europeia (Have Your Say, Press Corner)
- Implementação regulatória: European AI Office, códigos de prática GPAI, guidelines
- EDPB e EDPS — guidelines, decisões e enforcement relacionados a IA e dados
- **Mudanças de estado** de cada procedimento (relatoria, parecer de comissão, posição do Parlamento, trílogos, acordo provisório, adoção, assinatura, publicação no JO)
- Agenda de consultas públicas com prazo e marcos de aplicação do AI Act

## Estrutura (exclusivo UE)

```
data/legislation-eu/         # DATASET UE (fonte única da verdade)
  propositions.json          # Banco de procedimentos (chave: ue_ano_numero_tipo)
  laws.json                  # Leis, regulamentos e atos vigentes (AI Act e correlatos)
  timeline.json              # Timeline histórica do AI Act (2021–2026)
  parliamentarians.json      # Mapa de atores legislativos da UE (relatores, comissões)
  events.json                # Agenda de consultas e marcos de aplicação
  updates.json               # "O que mudou" + log de execuções do cron UE
  categories.json            # Categorias temáticas da UE
  atos.json                  # Atos multiórgão (AI Office, EDPB, EDPS, Comissão, Conselho)

scripts/
  update_legislation_eu.py   # Coletor automático UE: Parlamento/EUR-Lex/Conselho/Comissão → dataset
  update_sources_eu.py       # Conectores regulatórios UE (ai_office, edpb, edps, eurlex, eu_council, eu_commission, eu_parliament)
  scoring_eu.py              # Rúbrica pública do AI Legislative Impact Score para UE (impacto, nunca previsão política)
  build_site.py              # Gera o site EXCLUSIVO UE a partir de data/legislation-eu → /docs (https://monitor-ue.vercel.app/)
  build_site_eu_core.py      # Core do build UE (layout, páginas, SEO, JSON-LD)
  dataviz.py                 # Gráficos SVG do painel de monitoramento
  validate_site_eu.py        # Validações UE: JSON, duplicadas, links, SEO, domínio https://monitor-ue.vercel.app/
  selftest_offline_eu.py     # Testes offline do coletor UE
  assets/                    # CSS e JS do site UE
  ai_visibility_eu.py        # Camada AEO/SEO/agentic para UE
  google_ai_citation_eu.py   # Entidades para Google AI Overviews — UE exclusivo

.github/workflows/
  update-ue.yml              # Action diária UE: coleta → build → valida → commit se houver mudança
  probe-ue.yml               # Sondas dos endpoints oficiais da UE

docs/                        # SITE GERADO UE EXCLUSIVO (não editar manualmente)
  index.html                 # Página principal UE (verificação, o que mudou, dashboard, top dossiês)
  procedimentos-legislativos/ # Lista filtrável + ficha individual de cada procedimento UE
  atualizacoes/              # Histórico cronológico das mudanças detectadas na UE
  legislacao-e-atos/         # AI Act e atos correlatos
  timeline/                  # Linha do tempo da regulação de IA na UE
  atores-legislativos/       # Mapa de atores legislativos da UE
  agenda/                    # Agenda de consultas e marcos do AI Act
  metodologia/               # Fontes oficiais da UE, critérios, score, limitações
  monitoramento/             # Painel de métricas do cron UE
  relatorio/                 # Relatório da execução UE
  data/                      # Cópia pública do dataset UE (JSON)
  sitemap.xml · robots.txt · llms.txt · AGENTS.md
```

## Como executar (exclusivo UE)

```bash
python3 scripts/update_legislation_eu.py    # coleta das fontes oficiais da UE → atualiza /data/legislation-eu
python3 scripts/update_sources_eu.py        # conectores regulatórios UE
python3 scripts/build_site.py               # regenera /docs a partir de /data/legislation-eu (exclusivo UE)
python3 scripts/validate_site_eu.py         # valida dataset, páginas, links e domínio https://monitor-ue.vercel.app/
python3 scripts/selftest_offline_eu.py      # testes offline do coletor UE
```

Publicação: a Vercel executa `python3 scripts/build_site.py` e publica a pasta `/docs`.
O domínio oficial (`SITE_URL` em `scripts/build_site.py`) é
`https://monitor-ue.vercel.app/`.

## Fontes oficiais monitoradas (UE — exclusivo)

- **Parlamento Europeu** — Open Data Portal, API oficial v2 (procedimentos, eventos, textos adotados), Legislative Train, sala de imprensa
- **EUR-Lex / Jornal Oficial da UE** — busca CELEX, versões consolidadas, RSS oficial
- **Conselho da UE** — registro público de documentos (arquivo interinstitucional)
- **Comissão Europeia** — Press Corner (RSS) e portal Have Your Say (consultas públicas)
- **European AI Office** — implementação do AI Act, GPAI, códigos de prática
- **EDPB** — European Data Protection Board (IA/dados)
- **EDPS** — European Data Protection Supervisor

**Identidade dos itens:** número de procedimento interinstitucional (ex.: `2021/0106(COD)` → id `ue_2021_0106_cod`) é a chave compartilhada entre Parlamento, Conselho e Comissão; CELEX para normas; dedupe por URL canônica + hash.

**Limitações declaradas:** TJUE/CURIA sem conector estável; endpoints de reuniões da API v2 retornam corpo vazio — agenda futura vem das consultas oficiais do Have Your Say.

## Metodologia e política de qualidade (UE)

- **Fontes primárias obrigatórias:** cada fato relevante cita a URL oficial (*.europa.eu). Imprensa institucional apenas complementar.
- **Chave primária:** `ue_ano_numero_tipo` (ex.: `ue_2021_0106_cod`) — nenhuma duplicata.
- **AI Legislative Impact Score (0–100):** mede impacto regulatório apenas — nunca probabilidade de aprovação ou posição política.
- **Proibido:** inventar procedimentos, datas, autores, pareceres, probabilidades ou posições políticas sem evidência documental.
- Campos não confirmados em fonte oficial ficam **ausentes**, nunca preenchidos.

## Automação (UE exclusiva)

O workflow `.github/workflows/update-ue.yml` executa diariamente (horário de Bruxelas): coleta → rebuild → validação → commit somente se houver alteração real no dataset ou nas páginas. Sem commits vazios. O histórico de cada execução fica em `data/legislation-eu/updates.json`.

O painel `/monitoramento/` mostra frescor, cobertura, mudanças, custo HTTP e histórico de execuções — recalculado no navegador (se o cron parar, fica vermelho). Métricas também em `docs/data/monitoramento.json`.

## Autoria

Projeto desenvolvido por [Leandro Calado](https://leandrocaladoferreira.com/) / [LCF Consulting](https://lcfconsulting.com.br/).
Domínio oficial exclusivo UE: https://monitor-ue.vercel.app/
