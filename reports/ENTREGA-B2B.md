# Entrega B2B — Monitor Legislativo de IA

> **NOTA HISTÓRICA:** este relatório descreve a fase ORIGINAL brasileira do projeto (anterior à migração). Este repositório é hoje **EXCLUSIVO do Monitor UE de IA** — https://monitor-ue.vercel.app/ — e não contém mais monitoramento brasileiro. As menções a Câmara/Senado/ANPD/CNJ/TSE/DOU abaixo referem-se apenas ao passado.

Implementação incremental sobre `317bff62d36417ae0f53d7c39b125caaec5f9d08`.

**Estado:** código P0/P1 e base de piloto implementados e testados localmente. Não confundir implementação com ativação comercial em produção: o repositório não fornece credenciais de PostgreSQL/SMTP, nem acesso de administração da Vercel. Captura pública e entrega de e-mail precisam da ativação descrita abaixo. Nenhum e-mail real foi enviado, nenhuma conta real foi provisionada e nenhuma mudança foi mesclada em `main` durante a implementação.

## A. Auditoria inicial

[Auditoria completa](AUDITORIA-INICIAL.md): gerador Python estático; 143 páginas públicas; dados versionados; APIs Câmara/Senado; GitHub Actions; SEO/AEO; nenhuma captura de lead ou analytics comercial. Build e validação iniciais passaram. Riscos encontrados: publicação apesar de falha de validação, coleta parcial, base consolidada pública e mistura de evidências oficiais/contexto editorial.

## B. Alterações realizadas

- Camada comercial na navegação, CTA principal e CTA de briefing, sem substituir a home ou ocultar o monitor.
- Quatro ofertas com preços centralizados; Radar Executivo destacado; escopo experimental; prova social desativada.
- Diagnóstico estruturado; consentimento específico; qualificação e score calculados no servidor; idempotência; origem e campanha preservadas; retorno de sucesso somente após commit.
- Briefing real com registro oficial separado de análise preliminar, datas do evento/detecção, score preservado e referências oficiais. Agenda realmente futura, sem reutilizar rótulos antigos de “próximos dias”.
- Triagem empresarial por categorias em todas as fichas; campos estruturados e status da interpretação; nenhum cálculo de custo ou obrigação inventado.
- Nove páginas setoriais, sete personas, alto impacto e filtros 80+/60–79/<60. Watchlist local e sincronização autenticada.
- Backend privado PostgreSQL; SQLite somente em modo local explícito, recusado na Vercel. Senhas PBKDF2; sessões HttpOnly/SameSite/Secure em produção; validação de origem; rate limit persistente; sem endpoint de administração público.
- Alertas com opt-in confirmado, seleção de filtros, frequências, primeira execução como baseline, deduplicação, fila persistente, retry SMTP e cancelamento. Frequência semanal inclui Executive Regulatory Brief HTML + alternativa texto.
- Pilotos com status trial/pilot/active/inactive, expiração, temas, limite de usuários, registros de uso e acesso isolado por conta. Provisionamento assistido por CLI.
- Workflow legislativo só publica quando build e validação passam; workflow comercial valida PR e deixa entrega real desativada até configuração explícita.

O inventário [ARQUIVOS-ALTERADOS.md](ARQUIVOS-ALTERADOS.md) lista cada arquivo alterado/adicionado. Páginas de `docs/` são derivadas dos geradores; não são edições manuais.

## C. Novas URLs

Domínio de destino: `https://monitor-ue.vercel.app` (domínio oficial e exclusivo do Monitor UE de IA). A lista abaixo descreve rotas da branch; não declara que já foram publicadas em produção.

| Rota | Finalidade |
|---|---|
| `/solucoes/` | Quatro formas de contratação e pricing configurável |
| `/diagnostico/` | Qualificação, consentimento e captura de lead |
| `/briefing-executivo/` | Demonstração do briefing pago |
| `/para-empresas/` | Proposta para comprador corporativo |
| `/alto-impacto/` | Priorização e filtros de score |
| `/alertas/` | Preferências, confirmação e cancelamento |
| `/watchlist/` | Lista local e sincronização com piloto |
| `/privacidade/` | Finalidades, retenção e direitos |
| `/setores/fintech/` | Fintech |
| `/setores/bancos/` | Bancos |
| `/setores/seguros/` | Seguros |
| `/setores/saude/` | Saúde |
| `/setores/data-centers/` | Data centers |
| `/setores/cloud/` | Cloud |
| `/setores/tecnologia/` | Tecnologia |
| `/setores/escritorios-advocacia/` | Jurídico |
| `/setores/associacoes/` | Associações |
| `/casos-de-uso/` | Índice de personas |
| `/casos-de-uso/relacoes-governamentais/` | RIG |
| `/casos-de-uso/juridico-regulatorio/` | Jurídico regulatório |
| `/casos-de-uso/compliance/` | Compliance |
| `/casos-de-uso/public-affairs/` | Public Affairs |
| `/casos-de-uso/diretoria-executiva/` | C-level |
| `/casos-de-uso/escritorios-advocacia/` | Escritórios |
| `/casos-de-uso/associacoes-empresariais/` | Associações empresariais |
| `/login/` | Login de piloto, noindex, fora do sitemap |
| `/app/` | Shell de área autenticada, noindex, fora do sitemap |

Total: 27 novas páginas, 25 indexáveis. Resultado: 170 HTML e 168 URLs no sitemap no snapshot auditado. As 143 URLs anteriores permanecem.

## D. Funil comercial

Conteúdo/Google/LinkedIn/outbound → monitor público → setor ou briefing → diagnóstico → lead persistido e qualificado → demonstração contextualizada → piloto/projeto → contrato recorrente.

A origem UTM acompanha links comerciais na sessão e é armazenada no lead. O interesse `demo` gera oportunidade de demonstração, sem afirmar agendamento confirmado. O operador consulta leads e registra as etapas `lead`, `diagnostic`, `demo`, `pilot`, `contract`, `lost` via CLI. Não há integração de calendário nem venda automática.

## E. Analytics comercial

| Evento | Gatilho real | Registro |
|---|---|---|
| `commercial_cta_click` | Clique em CTA instrumentado | Navegador → API privada |
| `diagnostic_started` | Primeira interação no formulário | Navegador → API privada |
| `diagnostic_submitted` | Transação de lead concluída | Servidor, idempotente |
| `briefing_sample_view` | Abertura do exemplo | Navegador → API privada |
| `pricing_view` | Abertura de soluções | Navegador → API privada |
| `sector_page_view` | Abertura de página setorial | Navegador → API privada |
| `high_impact_view` | Abertura de alto impacto | Navegador → API privada |
| `alert_signup` | Confirmação efetiva do e-mail | Servidor, token de uso único |
| `demo_request` | Lead com interesse em demonstração | Servidor, mesma transação |
| `whatsapp_click` | Clique em link WhatsApp, se houver | Listener preparado; nenhum número inventado |

Campos: página, CTA, setor, origem, campanha, UTM source/medium/campaign/content/term e timestamp do servidor. E-mail/nome/telefone/preocupação não entram nos eventos. A API recusa eventos de sucesso fabricados pelo cliente. Se um `gtag` já estiver presente, há encaminhamento de eventos de navegação; nenhum ID de propriedade foi inventado. A coleta comercial depende do banco privado estar ativo.

## F. Pendências e limites

### Bloqueios de ativação P0

1. Configurar PostgreSQL, rodar migração e definir `DATABASE_URL`, `RATE_LIMIT_SECRET` na hospedagem.
2. Configurar SMTP com STARTTLS e remetente autorizado; cadastrar `LEAD_NOTIFY_EMAIL` para aviso interno opcional. A captura de lead funciona sem aviso interno após ativar o banco.
3. Configurar os secrets do workflow e `COMMERCIAL_ENABLED=true` somente depois de verificar envio/descadastro. Primeira execução apenas estabelece baseline.
4. Validar preview/deploy da Vercel e submissão real controlada antes de direcionar tráfego. Não houve validação remota de PostgreSQL ou entrega SMTP real nesta execução.

### P1 ainda não implementado integralmente

- Curadoria empresarial validada por organização e edição editorial das interpretações. A camada atual é triagem por categorias, claramente identificada.
- Inferência/curadoria de relação setorial de eventos sem metadados explícitos; esses eventos não são inventados para preencher páginas.
- Painel comercial visual/CRM, atribuição entre dispositivos e dashboards de receita. Há registros estruturados e CLI.
- PDF gerado no servidor e arquivamento/versionamento de relatórios completos por cliente. Há HTML, texto, impressão do navegador e briefing semanal por e-mail.
- Coleta contínua das fontes: o coletor original continua diário; “imediato” significa após detecção, com processamento comercial horário sujeito a atrasos do GitHub Actions.

### P2 ainda não implementado

- SSO/SAML, MFA, recuperação self-service de senha, convites e papéis administrativos granulares. Piloto usa provisionamento e reset assistidos; reset revoga sessões.
- API comercial com chaves, quotas e contrato; webhooks assinados, Slack, Teams, Telegram e WhatsApp. Canais futuros constam na arquitetura, não são vendidos como ativos.
- SLA operacional garantido, white-label, faturamento recorrente automático e área enterprise.
- Gestão de multiusuário por interface, exportações em massa e painel de relatórios históricos privados. Limite e isolamento de usuários já existem no backend mínimo.

### Proteção do ativo

O acervo histórico e os JSON públicos existentes continuam públicos para manter URLs, SEO, AEO e demonstração. São suficientes para reconstruir parte substancial da interface: essa exposição não foi falsamente descrita como protegida.

Leads, credenciais, contas, preferências, filas, uso e futuras análises customizadas ficam fora de `docs` e do Git, no banco privado. A triagem temática demonstrativa é deliberadamente pública. Retirar cópias já publicadas não é tecnicamente possível; não reescrever o histórico nem tornar o repositório privado sem decisão separada.

Arquitetura de evolução: gerador público recebe apenas catálogo demonstrativo; enriquecimento exclusivo e histórico comercial passam a um repositório/banco privado; API autenticada impõe conta e escopo; publicações preservam páginas indexadas e fontes. Não há necessidade de paywall geral.

## G. Evidências técnicas

- Build inicial: exit 0; 143 páginas/URLs.
- Validação inicial: 0 erros/0 avisos; autoteste offline do coletor passou.
- Build após P0 e após P1: exit 0; novas páginas integradas ao gerador original.
- Validação final local: 0 erros/0 avisos; JSON, links internos, assets, canonical, OG, JSON-LD, sitemap e IDs únicos verificados.
- 18 testes automatizados Python: captura/idempotência/score, consentimento, auth/expiração/limite/isolation, filtros, fila/retry/cancelamento, fontes/datas, dados públicos e gate do workflow.
- Sintaxe JavaScript validada com `node --check`.
- Performance estática: CSS e JS comerciais abaixo de 30 KB cada, sem framework frontend ou recursos visuais externos adicionados. Não equivale a medição de Core Web Vitals.
- Browser local: bloqueado por ausência de Chromium e timeout no download. Browser remoto: acesso a localhost bloqueado (`ERR_BLOCKED_BY_CLIENT`). A inspeção visual/mobile/console não deve ser declarada aprovada por esses testes locais.
- CI preparado: `tests/browser_smoke.cjs` testa desktop/mobile, fluxo de lead com UTM, filtros, watchlist e falha 503; publica screenshots e relatório como artifact `commercial-browser-evidence`. Resultado remoto será registrado no PR.
- Branch: `commercial/b2b-regulatory-intelligence`. Commit remoto e PR constam na entrega da conversa e no histórico GitHub; o commit de snapshot local não substitui o histórico remoto.

## Ativação reproduzível

### Local, sem enviar e-mail real

```bash
MONITOR_DEV=1 python3 scripts/serve_commercial.py
```

Abra `http://127.0.0.1:8765`. O serviço cria SQLite em `/tmp/monitor-commercial.sqlite3`; não é armazenamento de produção. Solicitações de alerta ficam na fila e nenhum SMTP é disparado pela API.

### Produção

Manter a configuração existente de build (`python3 scripts/build_site.py`) e pasta (`docs`). `vercel.json` acrescenta somente a API de funções Python, rewrites e headers.

Instalar `requirements.txt`, definir variáveis do `.env.example` no ambiente privado e executar:

```bash
python3 scripts/commercial_admin.py migrate
python3 scripts/send_alerts.py --capture
```

Provisionar um piloto com e-mail real somente na implantação autorizada; a senha é solicitada por entrada oculta, nunca passada em linha de comando:

```bash
python3 scripts/commercial_admin.py provision --account cliente-a --name 'Cliente A' --email pessoa@empresa.example --status pilot --ends-on 2026-10-15 --users 5 --themes 1 3 26
```

Após configurar SMTP e confirmar destinatários, ativar o workflow com `COMMERCIAL_ENABLED=true`. Secrets GitHub: `COMMERCIAL_DATABASE_URL`, `COMMERCIAL_SMTP_HOST`, `COMMERCIAL_SMTP_USER`, `COMMERCIAL_SMTP_PASSWORD`, `COMMERCIAL_SMTP_FROM`. Variável opcional `COMMERCIAL_SMTP_PORT`, padrão 587. SMTP precisa de STARTTLS e remetente validado pelo provedor.

A entrega possui retry e Message-ID estável. Um crash após aceitação pelo SMTP e antes da confirmação no banco pode duplicar um e-mail; não há promessa de exactly-once. A fila atual é adequada ao piloto, com lotes de 50 envios por execução. Revisar índices/volume e migrar para fila dedicada ao escalar.

Gerar relatório avulso (privado):

```bash
python3 scripts/generate_briefing.py --sector fintech --as-of 2026-09-12 --output .private/fintech-briefing.html
```

Consultar leads e avançar a venda:

```bash
python3 scripts/commercial_admin.py leads
python3 scripts/commercial_admin.py lead-stage ID_DO_LEAD demo
```

O comando de leads é exclusivo do operador e imprime dados de contato: não executar em logs públicos ou artifacts de CI.

Referências de implementação: [Vercel Python em /api](https://vercel.com/docs/functions/runtimes/python/api-directory), [configuração de funções](https://vercel.com/docs/functions/runtimes/python), [Psycopg](https://www.psycopg.org/psycopg3/docs/basic/usage.html).

## H. Ação comercial

A próxima ação com maior probabilidade de gerar receita é:

Apresentar o briefing de fintech a um decisor de dados ou compliance com quem a LCF já tenha relacionamento e propor um Diagnóstico de Exposição Regulatória avulso, usando o formulário para registrar o escopo e a oportunidade assim que a captura estiver ativada.
