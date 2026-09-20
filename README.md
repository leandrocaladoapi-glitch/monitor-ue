# Monitor Legislativo e Regulatório de IA da União Europeia

**Sistema de inteligência regulatória** — monitoramento público, documentado e auditável
da atividade legislativa e regulatória da União Europeia relacionada à Inteligência
Artificial: procedimentos interinstitucionais (Parlamento, Conselho, Comissão),
textos adotados e Jornal Oficial, atos delegados e de execução, consultas públicas
(Have Your Say), European AI Office, e os temas de IA/dados do EDPB e do EDPS.

O ativo principal é o **dataset regulatório histórico** (`/data/legislation`),
estruturado e continuamente atualizado. O site em `/docs` é a interface pública
desse dataset (interface em português; coleta em inglês, idioma técnico das fontes).

- **Site:** publicado a partir da pasta `/docs` (compatível com GitHub Pages — opção *Deploy from branch: `main` / `/docs`*)
- **Dados:** `/data/legislation/*.json` (fonte única da verdade, versionada no Git)
- **Build:** `python3 scripts/build_site.py` (sem dependências externas)

---

## O que este repositório monitora

Sete instituições oficiais, cada uma com conector próprio (`scripts/sources/`):

| Instituição | Fontes oficiais |
|---|---|
| **Parlamento Europeu** | Open Data Portal API v2 (procedimentos, eventos, textos adotados), Legislative Train, sala de imprensa |
| **EUR-Lex / Jornal Oficial** | busca oficial pública, URLs CELEX diretas, RSS/OJ, versões consolidadas |
| **Conselho da UE** | registro público (data.consilium.europa.eu), resultados/agendas, PDFs oficiais |
| **Comissão Europeia** | propostas (CELEX COM/...), Press Corner, consultas Have Your Say |
| **European AI Office** | newsroom digital-strategy (aplicação do AI Act, códigos de prática, GPAI) |
| **EDPB** | sala de imprensa (RSS) — somente temas de IA/proteção de dados |
| **EDPS** | notícias, opiniões e press releases — somente temas de IA/proteção de dados |

O motor legislativo (`scripts/update_legislation.py`) rastreia **procedimentos
interinstitucionais** — o número do arquivo (ex.: `2021/0106(COD)`) é a identidade
compartilhada entre as três instituições — da proposta à execução/enforcement.

**Limitação documentada (nada inventado):** o TJUE (CURIA) não dispõe de fonte
automatizada oficial estável para jurisprudência de IA; por isso **não há conector**
para o TJUE. Os endpoints de reuniões da API v2 do Parlamento retornam corpo vazio
(limitação da própria API) — a agenda futura vem das consultas oficiais do
Have Your Say.

## Estrutura

```
data/legislation/            # DATASET (fonte única da verdade)
  propositions.json          # Procedimentos interinstitucionais (id ue_<proc>, ex. ue_2021_0106_cod)
  atos.json                  # Camada multi-instituição: atos, consultas, publicações, enforcement
  laws.json                  # Normas da UE diretamente relacionadas a IA (AI Act + atos correlatos)
  timeline.json              # Linha do tempo: proposta → negociações → adoção → aplicação → enforcement
  parliamentarians.json      # Atores legislativos documentados nos dossiês monitorados
  events.json                # Agenda futura com fonte oficial (consultas, marcos)
  updates.json               # "O que mudou" + log de execuções (saúde, HTTP, cache, mudanças)
  categories.json            # 30 categorias temáticas adaptadas ao quadro de risco da UE

scripts/
  update_legislation.py    # Motor: API v2 do Parlamento + EUR-Lex + Train + HYS → diff → dataset
  update_sources.py        # Orquestra os 7 conectores multiórgão → atos.json + saúde por fonte
  sources/                 # Conectores oficiais (eu_parliament, eurlex, eu_council, eu_commission,
                           #   ai_office, edpb, edps) + eu_parsers + base (canais, dedup, relevância)
  probe_sources.py         # Sondas de rede dos endpoints oficiais (evidência no CI)
  scoring.py               # Rúbrica pública do Impact Score (0–100, impacto — nunca previsão política)
  build_site.py            # Gera o site estático a partir do dataset → /docs
  dataviz.py               # Gráficos SVG (stdlib, sem JS) do painel de monitoramento
  validate_site.py         # Validações: JSON, duplicatas, links, SEO, domínio
  selftest_offline.py      # Testes offline: orçamento, persistência e dupla execução sem duplicar
  check_collection.py      # Gate do cron: coleta do dia concluída, cobertura integral, sem erros
  ai_visibility.py         # AEO: llms.txt, ai-content.md, MCP de descoberta
  assets/                  # CSS e JS do site

.github/workflows/
  update-legislation.yml   # Cron (horário de Bruxelas): coleta → build → valida → commit se houver mudança
  probe-sources.yml        # Sondas periódicas dos endpoints oficiais + dry-run do pipeline
  commercial.yml           # Camada comercial (intacta)

docs/                        # SITE GERADO (não editar manualmente)
  index.html                 # Página principal (verificação, o que mudou, dashboard)
  procedimentos-legislativos/  # Lista filtrável + ficha individual de cada procedimento
  atualizacoes/              # Histórico cronológico das mudanças detectadas
  legislacao-e-atos/         # Normas diretamente relacionadas a IA
  timeline/                  # Linha do tempo da regulação de IA
  atores-legislativos/       # Relatores e atores documentados nos dossiês
  agenda/                    # Agenda de consultas e marcos futuros
  metodologia/               # Fontes, critérios, score, limitações e correções
  monitoramento/             # Painel de métricas do cron (frescor, cobertura, mudanças, custo HTTP)
  relatorio/                 # Relatório da execução + síntese editorial
  data/                      # Cópia pública do dataset (JSON)
  sitemap.xml · robots.txt   # SEO
```

## Como executar

```bash
python3 scripts/update_legislation.py   # motor legislativo (Parlamento/EUR-Lex/Train/HYS) → /data
python3 scripts/update_sources.py       # conectores multiórgão (AI Office, Conselho, Comissão, EDPB, EDPS…)
python3 scripts/build_site.py           # regenera /docs a partir de /data
python3 scripts/validate_site.py        # valida dataset, páginas, links e domínio
python3 scripts/selftest_offline.py     # testes offline do pipeline (orçamento, persistência, dupla execução)
python3 scripts/probe_sources.py --conjunto eu --canais   # sondas de rede das fontes oficiais
```

O coletor aceita limites explícitos (todos com equivalente em variável de ambiente
`MONITOR_*`), usados pela automação para nunca estourar o tempo do job:

```bash
python3 scripts/update_legislation.py --budget-min 25 --max-novas 25 --workers 5
```

Publicação: a Vercel executa `python3 scripts/build_site.py` e publica a pasta `/docs`.
O domínio oficial (`SITE_URL` em `scripts/build_site.py`) é
`https://monitor.lcfconsulting.com.br`.

## Ciclo de execução do monitoramento

1. Carregar o estado anterior (`data/legislation/*.json`)
2. Consultar as fontes oficiais (API v2 do Parlamento, EUR-Lex, registro do Conselho, Have Your Say, AI Office, EDPB, EDPS)
3. Identificar novos procedimentos interinstitucionais e novas movimentações/atos/consultas
4. Comparar estado antigo × atual; detectar alterações
5. Atualizar os registros (nunca sobrescrever silenciosamente: registrar em `updates.json` status anterior, novo, data e fonte)
6. Regenerar o site e validar (`python3 scripts/build_site.py` + `validate_site.py`)
7. Commit na branch de trabalho (o workflow só publica com build e validação verdes)

Se nada relevante mudou, apenas registra-se a verificação — **nada de conteúdo artificial**.
Falha de fonte aparece como `FALHA`/`PARCIAL` no painel — nunca como sucesso silencioso.

## Metodologia e política de qualidade

- **Somente fontes oficiais da UE** (`*.europa.eu` e equivalentes oficiais). Cada fato
  cita a URL oficial verificável. Imprensa oficial (Parlamento/Comissão) serve de
  contexto e agenda — nunca substitui a ficha oficial do procedimento.
- **Prioridade de fonte:** 1) API oficial, 2) open data oficial, 3) RSS/Atom oficial,
  4) endpoint JSON usado pelo próprio site, 5) HTML estruturado oficial, 6) HTML simples
  oficial. **Nunca** se recorre a sites de terceiros.
- **Chave primária:** o identificador oficial — número de procedimento interinstitucional
  (`ue_<aaaa>_<nnnn>_<tipo>`, ex.: `ue_2021_0106_cod`), CELEX ou id do documento.
  Deduplicação por URL canônica + hash de texto; nenhuma duplicata.
- **Multilíngue:** coleta em inglês (idioma técnico); interface em português; quando há
  tradução, o título oficial original é preservado.
- **Impact Score (0–100):** mede **impacto regulatório** — nunca probabilidade de
  aprovação ou previsão política (proibido pela política editorial). Faixas e critérios
  públicos em `scripts/scoring.py` e na página Metodologia.
- **Proibido:** inventar procedimentos, tramitações, votos, estágios, datas, documentos,
  decisões, autoridades, obrigações, sanções, prazos, eventos ou relações sem evidência
  documental. Campos não confirmados em fonte oficial ficam **ausentes**, nunca preenchidos.
- **"AI" isolada não é sinal de relevância** (falso positivo em inglês — "said",
  "maintain"); a classificação usa termos específicos ("artificial intelligence",
  "AI Act", "GPAI", "deepfake"…).
- `laws.json` contém **somente normas diretamente relacionadas a IA** (AI Act e atos
  correlatos como o Digital Omnibus on AI) — não toda a legislação digital da UE.
- `events.json` contém **somente eventos futuros com documentação oficial**.

## Estado atual (bootstrap de 18/09/2026)

- **2 procedimentos** monitorados: o AI Act (`ue_2021_0106_cod`, 2021/0106(COD)) e a
  resolução INI sobre IA generativa (`ue_2025_2058_ini`)
- **2 normas** diretamente relacionadas a IA: Regulamento (UE) 2024/1689 (AI Act,
  incl. versão consolidada) e Regulamento (UE) 2026/1744 (Digital Omnibus on AI)
- **23 eventos** na timeline (proposta → adoção → aplicação faseada → reprogramação
  do alto risco pela 2026/1744 → enforcement pela AI Office)
- **2 atores** documentados (co-relatores do AI Act: Brando Benifei e Dragoș Tudorache)
- **1 consulta futura** na agenda (Have Your Say, com verificação registrada)
- Primeiras coletas automáticas: as sondas de rede do sandbox de desenvolvimento são
  bloqueadas para `*.europa.eu` (evidência em `out/probe`); em CI o fluxo completo roda
  contra as fontes oficiais — o dataset é então populado nas primeiras execuções do cron.

Detalhes completos: página [Relatório](docs/relatorio/index.html) ·
saúde da automação: [Painel de monitoramento](docs/monitoramento/index.html).

## Automação

O workflow `.github/workflows/update-legislation.yml` executa no horário de Bruxelas
(diariamente 05:17 UTC + a cada 4h em 08:43/12:43/16:43 UTC):
coleta → rebuild → validação → commit somente se houver alteração real no dataset
ou nas páginas (build e validação precisam estar verdes para publicar). Sem commits
vazios. O histórico de cada execução fica em `data/legislation/updates.json`
(bloco `execucoes`) e as mudanças em `mudancas`. `probe-sources.yml` registra a
evidência de rede de cada endpoint oficial.

**Orçamento de tempo (por que existe).** Cada procedimento monitorado custa consultas
às APIs oficiais. O coletor tem **teto de duração** (`MONITOR_BUDGET_SEGUNDOS`,
padrão 25 min): ao se aproximar do teto ele para de iniciar consultas, grava o que
verificou e registra a execução como `parcial` (nunca perde o trabalho feito).
Verificação em **ordem de prioridade** (maior impacto primeiro; empate → mais tempo
sem verificação), **teto de fichas novas por execução** (`MONITOR_MAX_NOVAS`, padrão
25) com prioridade por relevância temática, tipo legislativo e recência, **cache de
execução** por URL + telemetria de rede (chamadas, cache, falhas, tempo por endpoint).
Rebuild, validação e commit rodam **mesmo se a coleta falhar** (`if: always()`), e a
execução é sinalizada no resumo do job e no painel.

### Painel de monitoramento (DataViz)

A página [`/monitoramento/`](docs/monitoramento/index.html) é reconstruída a cada
execução do site e mostra, a partir do log auditável do cron: frescor da última
execução (recalculado no navegador — se o cron parar, o painel fica vermelho),
cobertura da verificação, procedimentos pendentes, mudanças por dia/mês/tipo,
latência de detecção, evolução do banco, curadoria pendente, custo em chamadas
HTTP por endpoint, saúde por instituição-fonte e o histórico completo de execuções.
As mesmas métricas são publicadas em `docs/data/monitoramento.json` para uso externo
(BI, planilhas).

---

## Autoria

Projeto desenvolvido por [Leandro Calado](https://leandrocaladoferreira.com/) /
[LCF Consulting](https://lcfconsulting.com.br/).


## Camada comercial B2B

As páginas públicas permanecem como demonstração. Ofertas em `config/commercial.json`; geração em `scripts/commercial_pages.py`; API em `api/index.py`; dados comerciais privados via PostgreSQL.

Veja [a entrega e o guia de ativação](reports/ENTREGA-B2B.md) e [a auditoria inicial](reports/AUDITORIA-INICIAL.md). A captura e o envio real dependem da configuração de banco/SMTP; o build estático não configura serviços externos.

```bash
python3 -m unittest discover -s tests -v
MONITOR_DEV=1 python3 scripts/serve_commercial.py
```

### Receber os contatos direto no e-mail da equipe

O formulário de diagnóstico (`/diagnostico/`) entrega o contato por e-mail no mesmo instante em que
é enviado — `commercial/notify.py` faz a entrega, e a fila do banco (se houver) cobre o reenvio.

1. Defina na Vercel (Settings → Environment Variables) o destino e **um** transporte:
   - `LEAD_NOTIFY_EMAIL=lcaladoferreira@gmail.com` (aceita vários endereços separados por vírgula)
   - `RESEND_API_KEY=re_...` e `RESEND_FROM=` — Resend usa HTTPS e funciona na Vercel; antes de
     verificar um domínio próprio, o remetente `onboarding@resend.dev` só entrega no e-mail da conta
   - ou `FORMSUBMIT_KEY=...` — não exige domínio nem DNS, mas os dados passam pelo serviço de terceiros
   - ou `SMTP_HOST/PORT/USER/PASSWORD/SMTP_FROM` com STARTTLS (587) ou TLS (465); a Vercel bloqueia a porta 25
2. Redeploye (variáveis novas só valem após o próximo deploy) e abra `https://monitor.lcfconsulting.com.br/api/health`.

O `/api/health` responde o estado de configuração sem revelar nenhum valor:

| Campo | Significado |
|---|---|
| `database` | `ok` · `not_configured` · `unreachable` (banco privado, onde os leads ficam registrados) |
| `email_provider` | transporte escolhido: `resend` · `formsubmit` · `smtp` · `null` (nenhum) |
| `lead_recipients` | quantos endereços de `LEAD_NOTIFY_EMAIL` são válidos |
| `recipients_invalid` | `true` = há endereço inválido no `LEAD_NOTIFY_EMAIL` |
| `lead_capture` | `true` = o formulário consegue concluir um envio |
| `rate_limit` | `store` = limite persistente; `instance` = limite apenas na instância ativa |

Sem banco privado o lead não é gravado no PostgreSQL, mas o e-mail continua sendo entregue; com o
banco configurado, o registro é durável, idempotente (`request_id`) e o aviso entra na fila de retry
quando o transporte falha (`python3 scripts/send_alerts.py --send` reenvia). Se nem o banco nem o
e-mail estiverem prontos, o visitante recebe uma mensagem honesta de indisponibilidade **e** um link
`mailto:` com o conteúdo já preenchido, para que nenhum contato se perca durante a configuração.
