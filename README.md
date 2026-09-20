# Monitor Legislativo de IA no Brasil

**Sistema de inteligência legislativa** — monitoramento público, documentado e auditável de toda a atividade legislativa federal brasileira relacionada à Inteligência Artificial.

O ativo principal é o **dataset legislativo histórico** (`/data/legislation`), estruturado e continuamente atualizado. O site em `/docs` é a interface pública desse dataset.

- **Site:** publicado a partir da pasta `/docs` (compatível com GitHub Pages — opção *Deploy from branch: `main` / `/docs`*)
- **Dados:** `/data/legislation/*.json` (fonte única da verdade, versionada no Git)
- **Build:** `python3 scripts/build_site.py` (sem dependências externas)

> **Este repositório hospeda dois monitores.** O monitor brasileiro (esta seção,
> raiz do site) permanece intacto — conectores, dataset, motor, crons e páginas.
> Em paralelo, roda o **[Monitor Legislativo e Regulatório de IA da União Europeia](#monitor-da-união-europeia-seção-adicional)**,
> camada adicional com dataset próprio (`/data/legislation-eu`), conectores
> próprios e seção própria do site (`/uniao-europeia/`). Nenhum dos dois
> substitui o outro.

---

## O que este repositório monitora

- PL, PLC, PEC, PDL, PLN, MP, substitutivos, emendas, requerimentos e pareceres relacionados a IA
- Leis sancionadas, vetos, decretos e atos regulatórios (TSE, CNJ, ANPD, MCTI)
- **Mudanças de estado** de cada proposição (relatoria, parecer, pauta, votação, apensação, arquivamento)
- Relações entre proposições (apensados, clusters temáticos, sucessão histórica)
- Parlamentares com atuação documentada em IA
- Agenda de eventos futuros e marcos normativos

## Estrutura

```
data/legislation/            # DATASET (fonte única da verdade)
  propositions.json          # Banco de proposições (chave: casa_tipo_numero_ano)
  laws.json                  # Leis, decretos, resoluções e atos vigentes
  timeline.json              # Timeline histórica documentada (2019–2026)
  parliamentarians.json      # Mapa de parlamentares com atuação documentada
  events.json                # Agenda legislativa de IA (eventos futuros)
  updates.json               # "O que mudou" + log de execuções
  categories.json            # 30 categorias temáticas

scripts/
  update_legislation.py    # Coletor automático: APIs da Câmara/Senado → compara estado → atualiza dataset
  scoring.py               # Rúbrica pública do AI Legislative Impact Score (reproduzível)
  build_site.py            # Gera o site estático a partir do dataset → /docs
  dataviz.py               # Gráficos SVG (stdlib, sem JS) do painel de monitoramento
  validate_site.py         # Validações: JSON, duplicadas, links, SEO, domínio
  selftest_offline.py      # Testes offline: orçamento de tempo, persistência e métricas do coletor
  assets/                  # CSS e JS do site

.github/workflows/
  update-legislation.yml   # Action diária: coleta → build → valida → commit se houver mudança

docs/                        # SITE GERADO (não editar manualmente)
  index.html                 # Página principal (verificação, o que mudou, dashboard, top matérias)
  proposicoes/               # Lista filtrável + ficha individual de cada proposição
  atualizacoes/              # Histórico cronológico das mudanças detectadas
  leis/                      # Leis e normas vigentes
  timeline/                  # Linha do tempo da regulação de IA
  parlamentares/             # Mapa de parlamentares
  agenda/                    # Agenda legislativa de IA
  metodologia/               # Fontes, critérios, score, limitações e correções
  monitoramento/             # Painel de métricas do cron (frescor, cobertura, mudanças, custo HTTP)
  relatorio/                 # Relatório da execução + síntese editorial
  data/                      # Cópia pública do dataset (JSON)
  sitemap.xml · robots.txt   # SEO
```

## Como executar

```bash
python3 scripts/update_legislation.py   # coleta das fontes oficiais → atualiza /data
python3 scripts/build_site.py           # regenera /docs a partir de /data
python3 scripts/validate_site.py        # valida dataset, páginas, links e domínio
python3 scripts/selftest_offline.py     # testes offline do coletor (orçamento, persistência, métricas)
```

O coletor aceita limites explícitos (todos com equivalente em variável de ambiente
`MONITOR_*`), usados pela automação para nunca estourar o tempo do job:

```bash
python3 scripts/update_legislation.py --budget-min 25 --max-novas 25 --workers 5
```

Publicação: a Vercel executa `python3 scripts/build_site.py` e publica a pasta `/docs`.
O domínio oficial (`SITE_URL` em `scripts/build_site.py`) é
`https://monitor.lcfconsulting.com.br`.

## Ciclo de execução do monitoramento (execuções futuras)

1. Carregar o estado anterior (`data/legislation/*.json`)
2. Consultar as fontes oficiais (APIs de Dados Abertos da Câmara e do Senado, fichas de tramitação, DOU)
3. Identificar novas proposições e novas movimentações
4. Comparar estado antigo × atual; detectar alterações
5. Atualizar os registros (nunca sobrescrever silenciosamente: registrar em `updates.json` status anterior, novo, data e fonte)
6. Regenerar o site e validar (`python3 scripts/build_site.py` + checagem de links)
7. Commit na branch de trabalho e PR para revisão

Se nada relevante mudou, apenas registra-se a verificação — **nada de conteúdo artificial**.

## Metodologia e política de qualidade

- **Fontes primárias obrigatórias:** cada fato relevante cita a URL oficial (Câmara, Senado, Congresso, Planalto, DOU, TSE, CNJ, ANPD). Imprensa apenas para descoberta/contexto.
- **Chave primária:** `casa_tipo_numero_ano` (ex.: `camara_pl_2338_2023`) — nenhuma duplicata.
- **AI Legislative Impact Score (0–100):** faixas 90–100 crítico · 75–89 muito relevante · 60–74 relevante · 40–59 monitorar · 0–39 baixa prioridade. Critérios: abrangência, estágio, proximidade de votação, regime de tramitação, apensados, impactos econômico e sobre direitos. Nunca manipulado.
- **Proibido:** inventar proposições, tramitações, datas, autores, pareceres, probabilidades ou posições políticas sem evidência documental.
- Campos não confirmados em fonte oficial ficam **ausentes**, nunca preenchidos.

## Estado atual (execução de 08/09/2026 — bootstrap)

- **32 proposições** monitoradas (incluindo o pacote de 37 apensados ao PL 2338/2023)
- **14 normas** vigentes ou históricas mapeadas (LGPD, ECA Digital, Lei 15.487/2026, Res. TSE 23.748/2026, Res. CNJ 615/2025, Decretos 12.975-12.976/2026, EBIA, PBIA…)
- **35 eventos** na timeline histórica (2019–2026)
- **15 parlamentares** com atuação documentada
- Situação-síntese: marco legal (PL 2338/2023) parado há 16 meses na comissão especial da Câmara, com votação adiada para depois das eleições de outubro/2026; Redata (PL 278/2026) aprovado pelo Congresso e à sanção; Lei 15.487/2026 (deepfakes) em vigor desde 07/08/2026.

Detalhes completos: página [Relatório](docs/relatorio/index.html) ·
saúde da automação: [Painel de monitoramento](docs/monitoramento/index.html).

## Automação

O workflow `.github/workflows/update-legislation.yml` executa diariamente (07:17 BRT):
coleta → rebuild → validação → commit somente se houver alteração real no dataset
ou nas páginas. Sem commits vazios. O histórico de cada execução fica em
`data/legislation/updates.json` (bloco `execucoes`) e as mudanças em `mudancas`.

**Orçamento de tempo (por que existe).** O dataset cresce a cada dia e cada
proposição monitorada custa consultas às APIs oficiais. Em 10/09/2026 o job foi
cancelado pelo timeout de 45 min **durante a coleta** — rebuild, validação e
commit não rodaram e o site ficou congelado na execução anterior. Correções
aplicadas:

- a coleta tem **teto de duração** (`MONITOR_BUDGET_SEGUNDOS`, padrão 25 min);
  ao se aproximar do teto ela para de iniciar consultas, grava o que verificou e
  registra a execução como `parcial` (nunca mais perde o trabalho feito);
- verificação em **ordem de prioridade** (maior impacto primeiro; empate → mais
  tempo sem verificação), de modo que o que fica pendente são as matérias de
  menor score — e elas são as primeiras da execução seguinte;
- **teto de fichas novas por execução** (`MONITOR_MAX_NOVAS`, padrão 25), com
  prioridade por relevância temática, tipo de proposição e recência;
- **cache de execução** por URL + telemetria de rede (chamadas, cache, falhas,
  tempo por endpoint), evitando consultas repetidas;
- rebuild, validação e commit rodam **mesmo se a coleta falhar** (`if: always()`),
  e a execução é sinalizada no resumo do job e no painel.

### Painel de monitoramento (DataViz)

A página [`/monitoramento/`](docs/monitoramento/index.html) é reconstruída a cada
execução do site e mostra, a partir do log auditável do cron: frescor da última
execução (recalculado no navegador — se o cron parar, o painel fica vermelho),
cobertura da verificação, proposições pendentes, mudanças por dia/mês/tipo,
latência de detecção, evolução do banco, curadoria pendente, custo em chamadas
HTTP por endpoint e o histórico completo de execuções. As mesmas métricas são
publicadas em `docs/data/monitoramento.json` para uso externo (BI, planilhas).

## Monitor da União Europeia (seção adicional)

O **Monitor Legislativo e Regulatório de IA da União Europeia** reutiliza esta
mesma arquitetura (coleta com orçamento de tempo, cache, telemetria HTTP,
dedup/diff, checkpoint, scoring, build estático, validação, painel DataViz)
sobre as fontes oficiais da UE. Interface em português; coleta em inglês.

| | Monitor Brasil (raiz) | Monitor UE (`/uniao-europeia/`) |
|---|---|---|
| Dataset | `data/legislation/` | `data/legislation-eu/` (mesmos nomes de arquivo) |
| Motor | `scripts/update_legislation.py` | `scripts/update_legislation_eu.py` |
| Multiórgão | `scripts/update_sources.py` | `scripts/update_sources_eu.py` |
| Conectores extras | ANPD, CNJ, TSE, DOU, Planalto, MCTI | `eu_parliament`, `eurlex`, `eu_council`, `eu_commission`, `ai_office`, `edpb`, `edps` |
| Score | `scripts/scoring.py` | `scripts/scoring_eu.py` (impacto — nunca previsão política) |
| Build/validação | `build_site.py` / `validate_site.py` | `build_site_eu.py` / `validate_site_eu.py` → `docs/uniao-europeia/` |
| Cron | `update-legislation.yml` (horário de Brasília) | `update-ue.yml` (horário de Bruxelas) + `probe-ue.yml` (sondas) |
| Testes | `test_fontes_multiorgao.py` etc. | `test_fontes_ue.py`, `test_site_contract_ue.py`, `selftest_offline_eu.py` |

**Fontes oficiais monitoradas (UE):** API v2 do Open Data Portal do Parlamento
(procedimentos, eventos, textos adotados), Legislative Train, sala de imprensa
do Parlamento, EUR-Lex/Jornal Oficial (busca CELEX, versões consolidadas),
registro público do Conselho, propostas e consultas Have Your Say da Comissão,
newsroom do European AI Office, e temas de IA/dados do EDPB e do EDPS.
**Limitações documentadas (nada inventado):** o TJUE/CURIA não tem conector —
não existe fonte oficial automatizada estável; os endpoints de reuniões da API
v2 do Parlamento retornam corpo vazio — a agenda futura vem das consultas
oficiais do Have Your Say.

**Identidade dos itens:** o número de procedimento interinstitucional
(ex.: `2021/0106(COD)` → id `ue_2021_0106_cod`) é a chave compartilhada entre
Parlamento, Conselho e Comissão; CELEX para normas; dedupe por URL canônica +
hash. `laws.json` (UE) contém somente normas diretamente relacionadas a IA.
Falha de fonte aparece como `FALHA`/`PARCIAL` no painel — nunca sucesso
silencioso. Campos não confirmados em fonte oficial ficam ausentes.

```bash
python3 scripts/update_legislation_eu.py    # motor UE (Parlamento/EUR-Lex/Train/HYS)
python3 scripts/update_sources_eu.py        # conectores regulatórios UE
python3 scripts/build_site_eu.py            # regenera docs/uniao-europeia/
python3 scripts/validate_site_eu.py         # valida a seção UE
python3 scripts/selftest_offline_eu.py      # dupla execução: popula sem duplicar
python3 scripts/probe_sources_eu.py --conjunto eu --canais
```

Detalhes: [Metodologia UE](docs/uniao-europeia/metodologia/index.html) ·
[Painel UE](docs/uniao-europeia/monitoramento/index.html) ·
[llms.txt UE](docs/uniao-europeia/llms.txt) · [AGENTS UE](docs/uniao-europeia/AGENTS.md).

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
