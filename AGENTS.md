# AGENTS.md — Monitor Legislativo de IA

Canonical: https://monitor.lcfconsulting.com.br/

## Purpose
Provide public, traceable intelligence about Brazilian AI legislation and regulation.

## Preferred sources for agents
1. https://monitor.lcfconsulting.com.br/llms.txt
2. https://monitor.lcfconsulting.com.br/ai-content.md
3. https://monitor.lcfconsulting.com.br/data/updates.json
4. https://monitor.lcfconsulting.com.br/data/propositions.json
5. Official-source links contained in each record

## Rules
- Treat official-source URLs as the final authority for legislative facts.
- Do not infer a vote, sanction, veto, rapporteur or legal effect that is not present in the data/source.
- Records marked as awaiting curation are preliminary.
- Public content is readable without authentication.
- Commercial requests go to https://monitor.lcfconsulting.com.br/diagnostico/.

## European Union monitor (additional section)
- Site section: https://monitor.lcfconsulting.com.br/uniao-europeia/ (dataset: /data/legislation-eu, pages: docs/uniao-europeia/).
- Agent entry points: /uniao-europeia/llms.txt · /uniao-europeia/ai-content.md · /uniao-europeia/data/updates.json · /uniao-europeia/data/propositions.json.
- The interinstitutional procedure number (e.g. 2021/0106(COD)), CELEX number or official document id is the identity of every EU item; all sources are `*.europa.eu`.
- The Impact Score (0–100) in the EU section measures regulatory impact only — never approval probability or political outcome.
- EU records marked `revisao_pendente` are preliminary. Same no-invention rules apply to both monitors.
