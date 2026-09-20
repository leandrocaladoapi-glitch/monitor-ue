# AGENTS.md — Monitor Legislativo e Regulatório de IA da União Europeia

Canonical: https://monitor.lcfconsulting.com.br/

## Purpose
Provide public, traceable intelligence about European Union AI legislation and regulation (Parliament, Council, Commission, EUR-Lex/OJ, European AI Office, EDPB, EDPS).

## Preferred sources for agents
1. https://monitor.lcfconsulting.com.br/llms.txt
2. https://monitor.lcfconsulting.com.br/ai-content.md
3. https://monitor.lcfconsulting.com.br/data/updates.json
4. https://monitor.lcfconsulting.com.br/data/propositions.json
5. Official-source links contained in each record (all `*.europa.eu`)

## Rules
- The interinstitutional procedure number (e.g. 2021/0106(COD)), CELEX number or official document id is the identity of every item.
- Treat official-source URLs as the final authority for legislative and regulatory facts.
- Do not infer a vote, adoption, sanction, fine, stage, deadline or legal effect that is not present in the data/source.
- The Impact Score (0–100) measures regulatory impact only — it is never a prediction of approval probability or political outcome.
- Records marked as awaiting curation (`revisao_pendente`) are preliminary.
- Public content is readable without authentication.
- Commercial requests go to https://monitor.lcfconsulting.com.br/diagnostico/.
