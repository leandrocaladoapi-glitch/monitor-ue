# AGENTS.md — Monitor UE de IA (Exclusivo União Europeia)

Canonical: https://monitor-ue.vercel.app/

## Purpose
Provide public, traceable, exclusive intelligence about European Union AI legislation and regulation (AI Act and correlates). This repository is EXCLUSIVELY for the EU.

## Preferred sources for agents
1. https://monitor-ue.vercel.app/llms.txt
2. https://monitor-ue.vercel.app/ai-content.md
3. https://monitor-ue.vercel.app/data/updates.json
4. https://monitor-ue.vercel.app/data/propositions.json
5. Official-source links contained in each record (all *.europa.eu)

## Rules
- Treat official-source URLs (europa.eu) as the final authority for legislative facts.
- Do not infer a vote, adoption, sanction, rapporteur or legal effect that is not present in the data/source.
- Records marked as awaiting curation (revisao_pendente) are preliminary.
- Public content is readable without authentication.
- Commercial requests go to https://monitor-ue.vercel.app/diagnostico/ or https://lcfconsulting.com.br/
- The Impact Score (0–100) measures regulatory impact only — never approval probability or political outcome.
- This site is exclusive EU — do not reference Brazilian legislation or any old Brazilian domain.
- Domain is https://monitor-ue.vercel.app/ — all canonical, OG, sitemap and data URLs use this domain.
- Identity: interinstitutional procedure number (e.g. 2021/0106(COD)), CELEX or official document id.

## Dataset
- Location: /data/legislation-eu/ (propositions.json, laws.json, timeline.json, updates.json, events.json, parliamentarians.json, categories.json)
- Site output: /docs (published by Vercel)
- Build: python3 scripts/build_site.py (exclusive EU)
- Validation: python3 scripts/validate_site_eu.py (now validates root)
- Sources: European Parliament (Open Data Portal v2), EUR-Lex/OJ, Council public register, Commission (Press Corner + Have Your Say), European AI Office, EDPB, EDPS.
