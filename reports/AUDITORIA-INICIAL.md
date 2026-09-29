# Auditoria inicial — 12/09/2026

> **NOTA HISTÓRICA:** este relatório descreve a fase ORIGINAL brasileira do projeto (anterior à migração). Este repositório é hoje **EXCLUSIVO do Monitor UE de IA** — https://monitor-ue.vercel.app/ — e não contém mais monitoramento brasileiro. As menções a Câmara/Senado/ANPD/CNJ/TSE/DOU abaixo referem-se apenas ao passado.

Referência remota: `317bff62d36417ae0f53d7c39b125caaec5f9d08`. Auditoria concluída antes das alterações de implementação.

- Arquitetura: Python stdlib, gerador estático, HTML/CSS/JavaScript sem framework frontend. `build_site.py` envolve `build_site_core.py` e `ai_visibility.py`. Não existiam backend, banco comercial, autenticação, formulário ou dependências externas de build.
- Inventário: 21 arquivos fonte/configuração e saída gerada `docs/`. Árvore completa inspecionada pela API GitHub; snapshot recuperado por SHA porque o clone de rede não ficou disponível.
- Rotas: `/`, `/proposicoes/` e 133 fichas individuais, `/atualizacoes/`, `/leis/`, `/timeline/`, `/parlamentares/`, `/agenda/`, `/metodologia/`, `/monitoramento/`, `/relatorio/`. Total: 143 páginas/URLs. Slugs preservados pelo registro de colisões em `build_slugs`.
- Componentes reutilizáveis: `page`, `write`, breadcrumbs/CollectionPage JSON-LD, `change_card`, score badges, filtros, `prop_link`, layouts `.wrap`, `.block`, `.page-head`, cores CSS e gráficos SVG em `dataviz.py`.
- Dados: sete JSON de `data/legislation`, carregados no build. Navegador filtra HTML já renderizado; não depende de fetch dos JSON. 133 proposições, 14 normas, 10 eventos e 142 registros de mudança no snapshot.
- Público: cópia integral dos sete JSON em `docs/data`, além de `monitoramento.json`. Rodapé, llms.txt e ações declarativas divulgam feeds. Permitem reconstrução substancial do produto; o histórico Git também contém os dados. Remover endpoints não revoga cópias existentes.
- Pipeline: `update_legislation.py`, APIs Câmara/Senado, cache e orçamento, comparação de estado, checkpoint e atualização JSON. Falhas são registradas. Coleta diária 10:17 UTC no GitHub Actions; Vercel executa o build e publica `docs`.
- Problema preexistente no workflow: commit usa `always()` e não exige sucesso de build/validação. Pode publicar artefatos inválidos.
- Qualidade editorial: existem referências de imprensa em registros históricos e agenda. Novos briefings devem selecionar URLs oficiais e mostrar datas de evento separadas da detecção. Não tratar campo `proxima_etapa` editorial como decisão oficialmente agendada.
- Estado da coleta disponível: status `concluida` no registro, mas cobertura de somente 21,1% e 50 erros registrados, incluindo falhas em consultas à Câmara. Build bem-sucedido não comprova completude nem atualização das fontes.
- SEO: canonical/OG/JSON-LD/sitemap/robots emitidos pelo gerador; domínio final corrigido pelo entrypoint. README ainda cita domínio Vercel antigo. Descoberta AEO em `ai_visibility.py`; WebMCP é declaração, não API de execução autenticada.
- Analytics: nenhum coletor de eventos ou GA identificado nos scripts/templates. Há telemetria do cron, que não mede conversão comercial.
- Integrações: APIs legislativas, fontes oficiais e links editoriais; GitHub Actions e publicação Vercel documentada. Sem configuração de SMTP, CRM, pagamentos ou banco privado no repositório.

## Evidências pré-alteração

`python3 scripts/build_site.py`: exit 0; 143 páginas e 143 URLs; domínio validado.

`python3 scripts/validate_site.py`: exit 0; 0 erros e 0 avisos.

`python3 scripts/selftest_offline.py`: exit 0; orçamento, persistência, métricas e build validados. Simulação isolada em diretório temporário, sem alterações do dataset real.

Não houve erro de build preexistente. Os riscos de workflow, disponibilidade da coleta, exposição dos dados e fontes editoriais são distintos do resultado do build.
