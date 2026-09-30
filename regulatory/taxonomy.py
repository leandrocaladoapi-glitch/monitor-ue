"""taxonomy.py — vocabulário controlado do produto de inteligência regulatória.

Concentra tudo o que é estável e auditável: setores (24), temas (19), funções
internas (20), tipos de empresa (20), tipos de ato, estágios, reguladores,
escala de confiança, bandas de impacto/prioridade e as bibliotecas de conteúdo
editorial por tema (obrigações, riscos, oportunidades e ações recomendadas).

Nada aqui é afirmação jurídica: são hipóteses de trabalho que apontam sempre
para a fonte oficial citada no evento. A classificação é determinística — a
mesma entrada produz sempre a mesma saída (exigência do Módulo 18).
"""

from __future__ import annotations

import re
import unicodedata

from . import content

# --------------------------------------------------------------- confiança
CONFIDENCE = {
    "confirmed": 0.95,    # fato explícito na fonte oficial (data, status, decisão)
    "supported": 0.80,    # interpretação sustentada pelo texto oficial
    "probable": 0.60,     # impacto provável por taxonomia (exige ressalva)
    "unpublished": 0.40,  # abaixo do piso: fila de curadoria, nunca publicado
}
CONFIDENCE_FLOOR = 0.60
CONFIDENCE_LABELS = {
    "confirmed": "Fato confirmado em fonte oficial",
    "supported": "Interpretação fortemente suportada pela fonte oficial",
    "probable": "Impacto provável — requer avaliação jurídica específica",
    "unpublished": "Registo aguarda curadoria — leitura preliminar",
}

# ------------------------------------------------- impacto e prioridade
IMPACT_LEVELS = {
    "critical": {"label": "Crítico", "min": 85, "order": 0},
    "high": {"label": "Alto", "min": 70, "order": 1},
    "medium": {"label": "Médio", "min": 50, "order": 2},
    "low": {"label": "Baixo", "min": 0, "order": 3},
}
PRIORITIES = {
    "urgent": {"label": "Urgente — agir em dias", "min": 85, "order": 0},
    "high": {"label": "Alta — agir em semanas", "min": 70, "order": 1},
    "medium": {"label": "Média — planear no trimestre", "min": 50, "order": 2},
    "monitor": {"label": "Monitorizar", "min": 0, "order": 3},
}

# --------------------------------------------------------------- tipos de ato
ACT_TYPES = {
    "regulation": "Regulamento",
    "directive": "Diretiva",
    "delegated_act": "Ato delegado",
    "implementing_act": "Ato de execução",
    "decision": "Decisão",
    "guideline": "Guideline / orientação",
    "code_of_practice": "Código de prática",
    "procedure": "Procedimento legislativo",
    "consultation": "Consulta pública",
    "enforcement": "Enforcement / sanção",
    "judicial": "Decisão judicial",
    "resolution": "Resolução",
    "communication": "Comunicação oficial",
    "report": "Relatório",
    "opinion": "Parecer",
    "other": "Outro documento oficial",
}

STAGES = {
    "nao_classificado": "A classificar",
    "consulta": "Consulta aberta",
    "proposta": "Proposta (não vinculante)",
    "negociacao": "Em negociação",
    "parecer": "Em comissão / parecer",
    "plenario": "Em plenário",
    "adotado": "Adotado",
    "em_vigor": "Em vigor / aplicável",
    "encerrado": "Encerrado",
}

# ------------------------------------------------------------------ setores
SECTOR_KEYWORDS = {
    "bancos": [r"\bbank", r"banc", r"credit institution", r"lending", r"mortgage", r"\bdora\b",
               r"payment services?", r"psd2", r"psd3", r"open banking", r"institui[çc][õo]es de cr[ée]dito"],
    "fintech": [r"fintech", r"credit scoring", r"scoring", r"neobank", r"robo[- ]adv", r"insurtech",
                r"anti[- ]money", r"\baml\b", r"\bkyc\b", r"automat(ed|ic) decision"],
    "seguros": [r"insuranc", r"segurador", r"underwrit", r"actuar", r"reinsur", r"solvency", r"policyholder"],
    "saude": [r"\bhealth", r"sa[úu]de", r"hospital", r"clinic", r"patient", r"medical", r"\behds\b",
              r"health data", r"diagnos"],
    "pharma": [r"pharma", r"medicinal product", r"clinical trial", r"\bema\b", r"biotech", r"life science"],
    "saas": [r"\bsaas\b", r"software", r"cloud service", r"platform as a service", r"enterprise software",
             r"\bapi\b", r"b2b software"],
    "cloud": [r"\bcloud", r"nuvem", r"hyperscal", r"iaas", r"paas", r"data act", r"cloud switching",
              r"sovereign cloud"],
    "provedores-de-ia": [r"ai provider", r"provider of (an )?ai system", r"deployer of", r"ai system",
                         r"sistema de ia", r"model provider"],
    "modelos-de-fundacao": [r"\bgpai\b", r"general[- ]purpose ai", r"foundation model", r"frontier model",
                            r"generative ai", r"large language model", r"\bllm\b",
                            r"modelo de funda[çc][ãa]o", r"modelo de linguagem"],
    "telecom": [r"telecom", r"telecommunications?", r"network operator", r"\b5g\b", r"\b6g\b", r"berec",
                r"electronic communications", r"roaming"],
    "ecommerce": [r"e[- ]commerce", r"online shop", r"online marketplace", r"consumer protection",
                  r"product safety", r"dark pattern", r"consumidor"],
    "marketplaces": [r"marketplace", r"digital platform", r"very large (online )?platform", r"\bvlop",
                     r"\bvlose\b", r"platform economy", r"app store", r"gatekeeper"],
    "adtech": [r"adtech", r"online advertising", r"advertising", r"targeted ads?", r"behavioural advertising",
               r"\btcf\b", r"real[- ]time bidding", r"publicidade"],
    "martech": [r"martech", r"personalisation", r"personalization", r"customer data platform", r"\bcrm\b",
                r"recommendation system", r"marketing automation"],
    "automotivo": [r"automotive", r"vehicle", r"connected car", r"autonomous driving", r"\badas\b",
                   r"motor vehicle", r"tyre", r"mobilidade"],
    "manufatura": [r"manufactur", r"industrial", r"machinery", r"\brobot", r"factory", r"industry 4\.0",
                   r"cobot", r"supply chain"],
    "energia": [r"\benergy\b", r"energia", r"electricity", r"\bgrid\b", r"renewable", r"hydrogen",
                r"smart meter", r"\boil\b", r"\bgas\b"],
    "utilities": [r"utilit", r"water supply", r"waste water", r"critical infrastructure", r"district heating",
                  r"public utility", r"vital service", r"\bwater\b"],
    "hr-tech": [r"hr tech", r"human resources", r"talent", r"workforce management", r"employee monitoring",
                r"people analytics"],
    "recrutamento": [r"recruit", r"job applicant", r"employment", r"worker management", r"emprego",
                     r"trabalho", r"labour", r"gig work", r"platform work"],
    "educacao": [r"education", r"educa[çc][ãa]o", r"school", r"university", r"student", r"exam",
                 r"admission", r"proctoring", r"tutoring", r"minors", r"children"],
    "legaltech": [r"legal tech", r"legaltech", r"law firm", r"legal service", r"justice", r"judicial",
                  r"\bcourt", r"tribunal"],
    "ciberseguranca": [r"cyber", r"\bnis2\b", r"network and information security", r"vulnerab", r"malware",
                       r"ransomware", r"ciberseguran[çc]a", r"cyber resilience act", r"\bcra\b"],
    "data-centers": [r"data cent(er|re)", r"datacent", r"centro de dados", r"colocation", r"server farm",
                     r"supercomput", r"energy efficiency of data"],
}

SECTORS: dict[str, dict] = {}
for _slug, _meta in content.SECTOR_META.items():
    SECTORS[_slug] = {
        **_meta,
        "functions": list(content.SECTOR_FUNCTIONS.get(_slug, [])),
        "company_types": list(content.SECTOR_COMPANY_TYPES.get(_slug, [])),
        "keywords": SECTOR_KEYWORDS.get(_slug, []),
    }
# Setores com URL legada publicada pela camada comercial (M17: mesma página).
LEGACY_SECTORS = {"bancos": "bancos", "fintech": "fintech", "seguros": "seguros", "saude": "saude",
                  "cloud": "cloud", "data-centers": "data-centers"}

# ------------------------------------------------------------ funções internas
# Formato: chave → {"name": rótulo executivo}. Mantém compatibilidade com as
# páginas do produto, que exibem FUNCTIONS[key]["name"].
FUNCTIONS = {key: {"name": label} for key, label in content.FUNCTIONS.items()}

# ------------------------------------------------------------ tipos de empresa
COMPANY_TYPES = dict(content.COMPANY_TYPES)

# ------------------------------------------------------------------- temas
THEME_FUNCTIONS = {
    "ai_act": ["ai-governance", "regulatory-affairs", "legal", "compliance", "product", "public-policy"],
    "ai_office": ["regulatory-affairs", "public-policy", "government-affairs", "product", "ai-governance"],
    "ai_liability": ["legal", "general-counsel", "risk", "product", "compliance"],
    "gpai": ["ai-governance", "engineering", "legal", "regulatory-affairs", "product", "data-governance"],
    "edpb": ["dpo", "privacy", "compliance", "legal", "data-governance"],
    "edps": ["dpo", "privacy", "compliance", "legal"],
    "enforcement": ["compliance", "legal", "risk", "privacy", "dpo", "cybersecurity", "data-governance"],
    "dsa": ["compliance", "legal", "product", "public-policy", "government-affairs"],
    "competition": ["legal", "public-policy", "government-affairs", "strategy", "compliance"],
    "consultation": ["public-policy", "government-affairs", "regulatory-affairs", "legal", "strategy"],
    "judicial": ["legal", "general-counsel", "compliance", "risk"],
    "public_sector": ["public-policy", "government-affairs", "procurement", "legal"],
    "funding_innovation": ["strategy", "public-policy", "finance", "engineering"],
    "consumer": ["product", "marketing", "legal", "compliance", "data-governance"],
    "cybersecurity": ["cybersecurity", "risk", "engineering", "compliance"],
    "health_data": ["clinical", "dpo", "privacy", "regulatory-affairs", "product"],
    "employment": ["hr", "legal", "compliance", "ai-governance"],
    "copyright": ["legal", "general-counsel", "engineering", "product"],
    "data_act": ["data-governance", "engineering", "procurement", "strategy", "cybersecurity"],
}

THEME_SECTORS = {
    "ai_act": ["provedores-de-ia", "modelos-de-fundacao", "saas", "cloud"],
    "ai_office": ["provedores-de-ia", "modelos-de-fundacao", "saas"],
    "ai_liability": ["automotivo", "manufatura", "saude", "saas", "provedores-de-ia"],
    "gpai": ["modelos-de-fundacao", "provedores-de-ia", "cloud", "saas"],
    "edpb": ["adtech", "saude", "saas", "ecommerce", "marketplaces", "cloud", "provedores-de-ia"],
    "edps": ["saas", "cloud"],
    "enforcement": ["saas", "ecommerce", "marketplaces", "adtech", "cloud", "provedores-de-ia", "saude"],
    "dsa": ["marketplaces", "ecommerce", "adtech", "martech"],
    "competition": ["marketplaces", "adtech", "cloud", "provedores-de-ia"],
    "consultation": ["saas", "ecommerce", "marketplaces", "adtech", "cloud", "provedores-de-ia", "saude"],
    "judicial": ["legaltech", "saas", "marketplaces"],
    "public_sector": ["utilities", "saude", "educacao", "data-centers"],
    "funding_innovation": ["data-centers", "cloud", "provedores-de-ia", "educacao"],
    "consumer": ["ecommerce", "marketplaces", "adtech", "martech", "saas"],
    "cybersecurity": ["ciberseguranca", "cloud", "data-centers", "bancos", "energia", "utilities"],
    "health_data": ["saude", "pharma", "seguros"],
    "employment": ["hr-tech", "recrutamento", "marketplaces"],
    "copyright": ["modelos-de-fundacao", "provedores-de-ia", "adtech"],
    "data_act": ["cloud", "data-centers", "telecom", "provedores-de-ia"],
}

THEME_KEYWORDS = {
    "ai_act": [r"\bai act\b", r"artificial intelligence act", r"2024/1689", r"harmonised rules on artificial"],
    "ai_office": [r"ai office", r"european ai office", r"code of practice", r"c[óo]digo de pr[áa]tica",
                  r"ai board", r"ai pact"],
    "ai_liability": [r"liabilit", r"responsabilidade", r"product liability", r"compensation", r"damages",
                     r"repara[çc][ãa]o"],
    "gpai": [r"\bgpai\b", r"general[- ]purpose ai", r"foundation model", r"frontier model",
             r"large language model", r"modelo de funda[çc][ãa]o", r"systemic risk"],
    "edpb": [r"\bedpb\b", r"european data protection board", r"\bgdpr\b", r"\brgpd\b", r"personal data",
             r"dados pessoais", r"data subject", r"anonymis", r"web[- ]scraping"],
    "edps": [r"\bedps\b", r"european data protection supervisor", r"eu institutions", r"institui[çc][õo]es da ue"],
    "enforcement": [r"\bfine", r"sanction", r"san[çc][ãa]o", r"enforcement", r"penalt", r"multa",
                    r"corrective measure", r"decision following inquiry"],
    "dsa": [r"\bdsa\b", r"digital services act", r"\bvlop", r"\bvlose\b", r"content moderation",
            r"deveres de informa[çc][ãa]o"],
    "competition": [r"competition law", r"antitrust", r"concorr[êe]ncia", r"\bdma\b", r"digital markets act",
                    r"gatekeeper"],
    "consultation": [r"call for evidence", r"consulta", r"consultation", r"have your say",
                     r"feedback period", r"public consultation", r"stakeholder event", r"workshop"],
    "judicial": [r"court of justice", r"\bcjeu\b", r"\bcuria\b", r"general court", r"preliminary ruling",
                 r"judgment", r"ac[óo]rd[ãa]o"],
    "public_sector": [r"public procurement", r"contrata[çc][ãa]o p[úu]blica", r"public authority",
                      r"public sector", r"tender", r"setor p[úu]blico"],
    "funding_innovation": [r"horizon europe", r"funding", r"financiamento", r"innovation", r"inova[çc][ãa]o",
                           r"\berc\b", r"research programme"],
    "consumer": [r"consumer", r"consumidor", r"dark pattern", r"transparency requirement", r"labelling",
                 r"rotula[çc][ãa]o"],
    "cybersecurity": [r"\bnis2\b", r"cyber resilience act", r"\bcra\b", r"cybersecurity", r"ciber",
                      r"vulnerab", r"incident report"],
    "health_data": [r"health data", r"\behds\b", r"european health data space", r"medical device", r"\bmdr\b",
                    r"ivdr", r"dados de sa[úu]de"],
    "employment": [r"employment", r"emprego", r"worker", r"recruit", r"job applicant", r"hiring",
                   r"platform work", r"human resources"],
    "copyright": [r"copyright", r"direitos de autor", r"training data", r"text and data mining",
                  r"rights reserve", r"reserva de direitos"],
    "data_act": [r"data act", r"cloud switching", r"data sharing", r"data governance act", r"data space",
                 r"soberania", r"sovereignty", r"\bsemiconductor", r"high[- ]performance computing"],
}

THEMES: dict[str, dict] = {}
for _key, _label in content.THEMES.items():
    THEMES[_key] = {
        "label": _label,
        "functions": THEME_FUNCTIONS.get(_key, ["regulatory-affairs", "legal"]),
        "sectors": THEME_SECTORS.get(_key, []),
        "keywords": THEME_KEYWORDS.get(_key, []),
    }

# --------------------------------------------------------------- reguladores
REGULATORS = {
    "eurlex": {"name": "EUR-Lex / Jornal Oficial", "url": "https://eur-lex.europa.eu/"},
    "eu_commission": {"name": "Comissão Europeia", "url": "https://commission.europa.eu/"},
    "eu_parliament": {"name": "Parlamento Europeu", "url": "https://www.europarl.europa.eu/"},
    "eu_council": {"name": "Conselho da UE", "url": "https://www.consilium.europa.eu/"},
    "ai_office": {"name": "European AI Office", "url": "https://digital-strategy.ec.europa.eu/en/policies/ai-office"},
    "edpb": {"name": "EDPB", "url": "https://www.edpb.europa.eu/"},
    "edps": {"name": "EDPS", "url": "https://www.edps.europa.eu/"},
    "curia": {"name": "Tribunal de Justiça da UE (CURIA)", "url": "https://curia.europa.eu/"},
    "national_dpa": {"name": "Autoridade nacional de proteção de dados",
                     "url": "https://www.edpb.europa.eu/about-edpb/about-edpb/members_en"},
    "other": {"name": "Fonte oficial da União Europeia", "url": "https://europa.eu/"},
}
REGULATOR_ALIASES = {
    "edpb": "edpb", "edps": "edps", "eurlex": "eurlex", "eur-lex": "eurlex",
    "eu_commission": "eu_commission", "ec": "eu_commission", "comissao": "eu_commission",
    "eu_parliament": "eu_parliament", "parlamento": "eu_parliament",
    "eu_council": "eu_council", "conselho": "eu_council",
    "ai_office": "ai_office", "european-ai-office": "ai_office",
    "curia": "curia", "cjeu": "curia", "dpas": "national_dpa",
}

# ------------------------------------------------------------------- flags
FLAGS = {
    "high_risk": "Sistema de alto risco (Anexo III)",
    "penalty": "Sancionatório / multa",
    "consultation": "Consulta aberta",
    "minors": "Menores envolvidos",
    "prohibited": "Prática proibida",
    "gpai": "GPAI / modelo de fundação",
    "open_source": "Código aberto",
    "enforcement": "Enforcement",
}
FLAG_KEYWORDS = {
    "high_risk": [r"high[- ]risk", r"alto risco", r"anexo iii", r"annex iii", r"conformity assessment"],
    "penalty": [r"\bfine", r"fine[sd]?\b", r"multa", r"san[çc][ãa]o", r"penalty", r"penalt"],
    "consultation": [r"call for evidence", r"consulta", r"consultation", r"feedback period",
                     r"have your say", r"stakeholder"],
    "minors": [r"minor", r"menor", r"child", r"crian[çc]a", r"children"],
    "prohibited": [r"prohibit", r"proibi", r"banned", r"unacceptable risk"],
    "gpai": [r"\bgpai\b", r"general[- ]purpose ai", r"foundation model"],
    "open_source": [r"open[- ]source", r"c[óo]digo aberto"],
    "enforcement": [r"enforcement", r"decision following inquiry", r"investigation"],
}

# ---------------------------- obrigações, riscos, oportunidades e ações (por tema)
THEME_OBLIGATIONS = dict(content.THEME_OBLIGATIONS)
THEME_RISKS = dict(content.THEME_RISKS)
THEME_OPPORTUNITIES = dict(content.THEME_OPPORTUNITIES)
THEME_ACTIONS = {key: [(text, owner, priority) for text, owner, priority in value]
                 for key, value in content.THEME_ACTIONS.items()}

# conteúdo adicional para os temas sem eventos no dataset atual (mesma metodologia)
THEME_COMPANY_TYPES = {
    "ai_act": ["ai-system-provider", "gpai-provider", "large-enterprise", "sme", "startup",
               "open-source", "importer-distributor", "digital-platform"],
    "ai_office": ["gpai-provider", "ai-system-provider", "large-enterprise", "startup"],
    "ai_liability": ["ai-system-provider", "manufacturer", "large-enterprise", "sme",
                     "importer-distributor"],
    "gpai": ["gpai-provider", "cloud-infra", "ai-system-provider", "large-enterprise", "open-source",
             "startup"],
    "edpb": ["digital-platform", "large-enterprise", "sme", "cloud-infra", "ai-deployer",
             "professional-services"],
    "edps": ["public-sector", "large-enterprise", "cloud-infra"],
    "enforcement": ["large-enterprise", "digital-platform", "cloud-infra", "ai-system-provider",
                    "sme", "startup", "financial-institution"],
    "dsa": ["digital-platform", "large-enterprise", "sme", "startup"],
    "competition": ["digital-platform", "large-enterprise", "cloud-infra"],
    "consultation": ["large-enterprise", "sme", "startup", "ai-system-provider", "digital-platform",
                     "public-sector", "research"],
    "judicial": ["large-enterprise", "digital-platform", "professional-services"],
    "public_sector": ["public-sector", "large-enterprise", "research", "manufacturer"],
    "funding_innovation": ["startup", "sme", "research", "cloud-infra"],
    "consumer": ["digital-platform", "large-enterprise", "sme", "startup"],
    "cybersecurity": ["cloud-infra", "large-enterprise", "financial-institution", "manufacturer",
                      "ai-system-provider"],
    "health_data": ["health-provider", "large-enterprise", "sme", "research", "ai-system-provider"],
    "employment": ["digital-platform", "large-enterprise", "sme", "ai-deployer", "professional-services"],
    "copyright": ["gpai-provider", "ai-system-provider", "large-enterprise", "startup", "research"],
    "data_act": ["cloud-infra", "large-enterprise", "ai-deployer", "sme"],
}
THEME_OBLIGATIONS.update({
    "ai_liability": [
        "Revisar contratos e apólices para alocação de responsabilidade por danos causados por IA.",
        "Manter trilhas de auditoria e evidência técnica das decisões automatizadas.",
    ],
    "consumer": [
        "Informar o consumidor sobre o uso de IA e sobre decisões automatizadas que o afetem.",
        "Evitar padrões enganosos e garantir transparência de recomendação e personalização.",
    ],
    "cybersecurity": [
        "Reportar incidentes relevantes dentro do prazo aplicável e manter gestão de vulnerabilidades.",
        "Exigir evidência de segurança dos fornecedores que tratam dados ou operam a infraestrutura crítica.",
    ],
    "health_data": [
        "Verificar enquadramento como dispositivo médico e as condições de uso de dados de saúde.",
        "Garantir base legal e avaliação de impacto reforçada para dados de saúde em IA.",
    ],
    "employment": [
        "Avaliar requisitos de IA de alto risco em recrutamento, seleção e gestão de trabalhadores.",
        "Assegurar revisão humana efetiva e informação ao candidato ou trabalhador.",
    ],
    "copyright": [
        "Manter política de direitos de autor e respeitar reservas de direitos em dados de treino.",
        "Documentar a origem e a licença dos dados utilizados em treino e fine-tuning.",
    ],
    "data_act": [
        "Habilitar portabilidade de dados e troca de fornecedor cloud nos termos aplicáveis.",
        "Formalizar contratos de dados com condições de acesso, uso e segurança.",
    ],
})
THEME_RISKS.update({
    "ai_liability": ["Indefinição contratual sobre quem responde pelo dano causado por sistema de IA."],
    "consumer": ["Prática considerada enganosa gera multa, remoção de conteúdo e perda de confiança."],
    "cybersecurity": ["Falha de segurança em sistema de IA crítico expõe a operação e a sanção administrativa."],
    "health_data": ["Uso clínico ou de dados de saúde sem enquadramento correto invalida o produto perante reguladores."],
    "employment": ["Triagem automatizada sem controles é uma das áreas mais fiscalizadas do AI Act."],
    "copyright": ["Treino ou geração sem política de direitos de autor atrai disputas e indenizações."],
    "data_act": ["Dependência de fornecedor sem portabilidade reduz poder de negociação e eleva risco de bloqueio."],
})
THEME_OPPORTUNITIES.update({
    "ai_liability": ["Clareza contratual reduz litígio e acelera vendas para clientes regulados."],
    "consumer": ["Transparência demonstrável aumenta confiança do usuário e reduz churn."],
    "cybersecurity": ["Resiliência comprovada vira argumento de venda para clientes de setores regulados."],
    "health_data": ["Conformidade clínica abre espaço em compras hospitalares e programas públicos."],
    "employment": ["Processos auditáveis reduzem risco trabalhista e melhoram marca empregadora."],
    "copyright": ["Política de direitos clara evita disputas e viabiliza parcerias de licenciamento."],
    "data_act": ["Arquitetura multi-cloud e portabilidade melhoram negociação com fornecedores."],
})
THEME_ACTIONS.update({
    "ai_liability": [("Revisar contratos e seguros para responsabilidade por sistemas de IA.", "legal", "Alta")],
    "consumer": [("Revisar transparência, rotulagem e padrões de interface dos produtos com IA.", "product", "Alta")],
    "cybersecurity": [("Testar resposta a incidentes e reporte nos prazos aplicáveis.", "cybersecurity", "Alta")],
    "health_data": [("Confirmar enquadramento regulatório do caso de uso clínico.", "clinical", "Alta")],
    "employment": [("Mapear uso de IA em recrutamento e gestão de pessoas.", "hr", "Alta")],
    "copyright": [("Documentar licenças e reservas de direitos dos dados de treino.", "general-counsel", "Alta")],
    "data_act": [("Mapear dependências de cloud e condições de portabilidade vigentes.", "data-governance", "Média")],
})

# ----------------------------------------------------------------- utilidades
def norm_text(text: str) -> str:
    """Minúsculas, sem acentos e sem espaços redundantes (base das palavras-chave)."""
    base = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", base).strip()


def slug(text: str, limit: int = 60) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", norm_text(text)).strip("-")
    return base[:limit] or "sem-titulo"


def normalize_function(key: str) -> str | None:
    """Aceita chave canónica ou rótulo e devolve a chave canónica."""
    if not key:
        return None
    if key in FUNCTIONS:
        return key
    low = str(key).strip()
    if low.lower() in FUNCTIONS:
        return low.lower()
    for canonical, meta in FUNCTIONS.items():
        if meta["name"].casefold() == low.casefold():
            return canonical
    return None


def theme_label(key: str) -> str:
    return THEMES.get(key, {}).get("label", key)


def sector_name(key: str) -> str:
    return SECTORS.get(key, {}).get("name", key)


def function_name(key: str) -> str:
    canonical = normalize_function(key)
    if not canonical:
        return key
    return FUNCTIONS.get(canonical, {}).get("name", key)


def company_type_name(key: str) -> str:
    return COMPANY_TYPES.get(key, key)


def all_theme_function_keys() -> set:
    return {key for theme in THEMES.values() for key in theme.get("functions", [])}


def all_sector_function_keys() -> set:
    return {key for sector in SECTORS.values() for key in sector.get("functions", [])}


def impact_level_for(score: int) -> str:
    for key, meta in IMPACT_LEVELS.items():
        if score >= meta["min"]:
            return key
    return "low"


def priority_for(score: int) -> str:
    for key, meta in PRIORITIES.items():
        if score >= meta["min"]:
            return key
    return "monitor"
