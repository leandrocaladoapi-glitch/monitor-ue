"""Incremental commercial pages using the existing static shell."""
import json
import sys
from pathlib import Path
from html import escape as esc
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commercial.intelligence import CONFIG, briefing, business_impact, official_fact, score, sectors_for

DISCLAIMER = 'Inteligência regulatória e análise de impacto de caráter informativo. Não constitui parecer ou aconselhamento jurídico, nem garantia de conformidade ou de interpretação legal.'
SECTORS = ['Tecnologia','Bancos','Fintech','Seguros','Saúde','Telecom','Cloud','Data Center','Infraestrutura','Jurídico','Consultoria','Associação','Governo','Outro']


def cta(label='Solicitar diagnóstico regulatório', sector='', kind='diagnostico'):
    query = urlencode({'setor':sector,'interesse':kind})
    return f'<a class="commercial-button" href="/diagnostico/?{query}" data-commercial-cta="{esc(kind)}" data-sector="{esc(sector)}">{esc(label)}</a>'


def strip():
    return '<aside class="commercial-strip"><div class="wrap"><div><strong>Regulação de IA, dados e infraestrutura digital.</strong><p>Saiba o que mudou, por que isso importa para sua operação, quem precisa agir e qual evidência oficial sustenta a conclusão.</p></div><div class="commercial-actions">' + cta() + '<a href="/briefing-executivo/" data-commercial-cta="briefing">Ver exemplo de briefing executivo</a></div></div></aside>'


def input_field(name,label,kind='text',required=True,options=None):
    attrs=f'name="{name}" id="{name}"' + (' required' if required else '')
    if options is not None:
        control=f'<select {attrs}><option value="">Selecione</option>'+''.join(f'<option value="{esc(str(v))}">{esc(str(t))}</option>' for v,t in options)+'</select>'
    elif kind=='textarea':
        control=f'<textarea {attrs} rows="3" maxlength="2000"></textarea>'
    else:
        auto={'email':'email','nome':'name','empresa':'organization','cargo':'organization-title','telefone':'tel'}.get(name,'off')
        control=f'<input {attrs} type="{kind}" maxlength="{256 if kind != "password" else 128}" autocomplete="{auto}">'
    return f'<label for="{name}">{esc(label)}'+(' *' if required else '')+control+'</label>'


def diagnostics():
    fields = ''.join(input_field(*a) for a in [('nome','Nome'),('empresa','Empresa'),('cargo','Cargo'),('email','E-mail corporativo','email'),('telefone','Telefone / WhatsApp (opcional)','tel',False)])
    fields += input_field('setor','Setor',options=[(s,s) for s in SECTORS])
    fields += input_field('tamanho','Tamanho aproximado',options=[('1-10','1–10 pessoas'),('11-100','11–100 pessoas'),('101-500','101–500 pessoas'),('501+','Mais de 500 pessoas')])
    fields += input_field('uso_ia','Uso de IA',options=[('nao','Ainda não utiliza'),('apoio','Apoio a atividades internas'),('critico','Processo crítico do negócio')])
    fields += input_field('area_controle','Possui compliance, RIG ou jurídico?',options=[('sim','Sim'),('nao','Não')])
    fields += input_field('urgencia','Horizonte da preocupação',options=[('imediata','Imediata / próximos 30 dias'),('trimestre','Próximos 3 meses'),('exploratoria','Exploratória')])
    fields += input_field('preocupacao','Principal preocupação regulatória','textarea')
    fields += input_field('interesse','Assunto de interesse',options=[('diagnostico','Diagnóstico de exposição'),('radar-executivo','Radar executivo'),('monitor-ia','Monitor IA'),('institucional','Inteligência institucional'),('briefing-setorial','Briefing setorial'),('demo','Demonstração contextualizada')])
    return '<div class="commercial-grid"><article class="commercial-card"><h2>Uma conversa com contexto</h2><p>Descubra quais projetos, normas e mudanças regulatórias relacionadas à IA podem afetar sua organização.</p><ol><li>Conte como sua organização usa IA.</li><li>Identificamos temas e evidências para a conversa inicial.</li><li>Você recebe uma proposta de diagnóstico, piloto ou assinatura adequada ao escopo.</li></ol><p>O envio solicita uma avaliação comercial. Workshop e relatório de diagnóstico são entregas contratadas separadamente.</p><a href="/briefing-executivo/">Ver exemplo de briefing executivo</a></article><form id="diagnostic-form" class="commercial-card"><p>Campos com * são obrigatórios.</p><div class="form-grid">'+fields+'</div><div class="honeypot" aria-hidden="true"><label>Website<input name="website" tabindex="-1" autocomplete="off"></label></div><label class="check"><input type="checkbox" name="consent" required> Autorizo o uso destas informações pela LCF Consulting para responder à solicitação e conduzir esta conversa comercial. <a href="/privacidade/">Como os dados são usados</a>.</label><button class="commercial-button" type="submit">Solicitar diagnóstico</button><p role="status" aria-live="polite" id="diagnostic-status"></p><noscript>Ative JavaScript para enviar a solicitação. Você também pode acessar <a href="https://lcfconsulting.com.br/">LCF Consulting</a>.</noscript></form></div>'


def business_html(p):
    a=business_impact(p)
    labels={'tipo_de_impacto':'Tipo de impacto','prazo_provavel':'Prazo provável','obrigacao_potencial':'Obrigação potencial','risco_operacional':'Risco operacional','impacto_financeiro_potencial':'Impacto financeiro potencial','impacto_em_compliance':'Compliance','impacto_em_dados':'Dados','impacto_em_modelos_ia':'Modelos de IA','impacto_em_infraestrutura':'Infraestrutura','status_da_interpretacao':'Status da interpretação'}
    sectors=', '.join(CONFIG['sectors'][s]['name'] for s in a['setores_afetados']) or 'A classificar'
    details=''.join(f'<div><dt>{label}</dt><dd>{esc(a[k])}</dd></div>' for k,label in labels.items())
    return f'<section class="block"><div class="wrap"><span class="eyebrow">ANÁLISE / INTERPRETAÇÃO</span><h2>Impacto empresarial</h2><p>{esc(a["por_que_importa"])}</p><p><strong>Setores potencialmente relacionados:</strong> {esc(sectors)}</p><details><summary>Examinar dimensões e limites da análise</summary><dl class="business-dimensions">{details}</dl></details><p>{esc(a["acao_recomendada"])}</p><p class="disclaimer">{DISCLAIMER}</p><button type="button" class="watch-button" data-watch-id="{esc(p["id"])}">Salvar na watchlist deste navegador</button> {cta()}</div></section>'


def prop_card(p, core, full=False):
    fact=official_fact(p);a=business_impact(p)
    composition=(p.get('impacto') or {}).get('detalhe') or {}
    factors=''.join(f'<li>{esc(k.replace("_"," "))}: {esc(str(v))}</li>' for k,v in composition.items())
    why='<ul>'+factors+'</ul>' if factors else '<p>Score da curadoria existente. A decomposição numérica não foi registrada para esta matéria; consulte a rúbrica. Nenhum fator foi inventado.</p>'
    section=f'<article class="commercial-card impact-card" data-impact-score="{score(p)}"><p class="eyebrow">AI Legislative Impact Score · {score(p)}/100</p><h3><a href="{core.prop_link(p)}">{esc(p["tipo"])} {p["numero"]}/{p["ano"]} — {esc(p["titulo"])}</a></h3>'
    if p.get('revisao_pendente'):
        section+='<p class="note warn">Registro aguardando curadoria: título, categorias e score são preliminares.</p>'
    if full:
        section+=f'<div class="fact"><span class="eyebrow">FATO OFICIAL · REGISTRO DO MONITOR</span><h4>O que mudou / último registro disponível</h4><p>{esc(fact["descricao"])}</p><p>Data do evento: {esc(str(fact["data_evento"] or "não informada"))} · Verificação: {esc(str(fact["verificado_em"] or "não informada"))}</p><p><a href="{esc(fact["fonte"])}" rel="noopener" target="_blank">Fonte oficial ↗</a></p></div><div class="interpretation"><span class="eyebrow">ANÁLISE / INTERPRETAÇÃO</span><h4>Por que importa</h4><p>{esc(a["por_que_importa"])}</p><h4>Quem pode ser afetado</h4><p>{esc(", ".join(CONFIG["sectors"][s]["name"] for s in a["setores_afetados"]))}</p><h4>Impacto potencial</h4><p>{"Crítico" if score(p)>=90 else "Alto" if score(p)>=75 else "Médio" if score(p)>=40 else "Baixo"} como prioridade de monitoramento; exposição da empresa ainda não avaliada.</p><h4>Próxima decisão relevante</h4><p>Acompanhar atualização na ficha oficial. Nenhuma data futura é confirmada por esta amostra.</p><h4>Ação recomendada</h4><p>{esc(a["acao_recomendada"])}</p><p class="disclaimer">{esc(a["status_da_interpretacao"])}</p></div>'
    else:
        section+=f'<p>{esc(p["ementa"][:280])}</p><p>{esc(fact["situacao"])}</p>'
    section+=f'<details><summary>Por que esta matéria recebeu esse score?</summary>{why}<a href="/metodologia/">Abrangência, estágio, proximidade, urgência e impactos: consultar metodologia</a></details><button type="button" class="watch-button" data-watch-id="{esc(p["id"])}">Salvar na watchlist deste navegador</button></article>'
    return section


def briefing_body(model,core):
    def changes(items):
        return '<ul>'+''.join(f'<li><strong>{esc(m.get("data_deteccao") or m.get("data", ""))}</strong> — {esc(m.get("titulo", ""))}<p>{esc(m.get("descricao", ""))}</p><small>Evento: {esc(m.get("data", "não informado"))}; detecção: {esc(m.get("data_deteccao", "não informada"))}</small> <a href="{esc(m["fonte_url"])}">Fonte oficial</a></li>' for m in items)+'</ul>' if items else '<p>Nenhuma mudança com fonte oficial registrada neste recorte. Isso não comprova ausência de mudanças nas fontes.</p>'
    agenda='<ul>'+''.join(f'<li>{esc(e["data_inicio"])} — <a href="{esc(e["fonte_url"])}">{esc(e["titulo"])}</a></li>' for e in model['events'])+'</ul>' if model['events'] else '<p>Nenhum evento futuro com fonte oficial identificado neste recorte. Consulte a agenda pública e confirme na fonte.</p>'
    return f'<p class="note">Amostra demonstrativa gerada com dados reais do monitor. Período de detecção: {model["since"]} a {model["as_of"]}. Situação da coleta: {esc(model["coverage"])}; cobertura: {esc(str(model["coverage_pct"]))}%; erros registrados: {model["source_errors"]}. Registros incorporados agora podem descrever eventos anteriores.</p><button class="watch-button" type="button" data-print>Imprimir / salvar como PDF</button><h2>Mudanças críticas da semana</h2>{changes(model["critical_changes"])}<h2>Top 5 matérias por impacto</h2><p>Prioridades do estoque monitorado; não significa que todas mudaram nesta semana.</p>'+''.join(prop_card(p,core,True) for p in model['top'])+f'<h2>Mudanças desde o último período</h2>{changes(model["changes"])}<h2>Agenda dos próximos 7 dias</h2>{agenda}<h2>Pontos que merecem atenção executiva</h2><p>Identificar processos de IA expostos, responsáveis internos e evidências necessárias para avaliar custos e prioridades. Os impactos por setor acima são triagem temática.</p><h2>Metodologia e fontes</h2><p>O score existente é preservado. O recorte exige links oficiais; a análise empresarial utiliza categorias e é preliminar. <a href="/metodologia/">Examinar metodologia do monitor</a>.</p><p>{DISCLAIMER}</p>'+cta()


def alert_form(core):
    fields=input_field('email','E-mail corporativo','email')
    fields+=input_field('frequencia','Frequência',options=[('imediato','Após a detecção pelo monitor'),('diario','Diário'),('semanal','Semanal')])
    fields+='<label>Score mínimo<input type="number" name="score_min" min="0" max="100" value="60"></label>'
    fields+='<label>Temas (opcional)<select name="temas" multiple>'+''.join(f'<option value="{c["id"]}">{esc(c["nome"])}</option>' for c in core.cat_map().values())+'</select></label>'
    fields+='<label>Proposições (opcional)<select name="proposicoes" multiple>'+''.join(f'<option value="{esc(p["id"])}">{esc(p["tipo"])} {p["numero"]}/{p["ano"]}</option>' for p in core.load('propositions.json')['proposicoes'])+'</select></label>'
    fields+='<label>Órgãos (opcional)<select name="orgaos" multiple>'+''.join(f'<option>{esc(o)}</option>' for o in ['Câmara dos Deputados','Senado Federal','ANPD','TSE','CNJ'])+'</select></label>'
    return '<form id="alert-form" class="commercial-card"><h2>Configurar alertas por e-mail</h2><p>Selecione temas, proposições e órgãos. Filtros preenchidos são combinados. A confirmação do endereço é necessária; você pode cancelar pelo link de cada e-mail.</p><div class="form-grid">'+fields+'</div><label class="check"><input type="checkbox" name="consent" required> Solicito os alertas selecionados e concordo com o uso do endereço para este envio. <a href="/privacidade/">Privacidade</a>.</label><div class="honeypot" aria-hidden="true"><input name="website" tabindex="-1"></div><button class="commercial-button">Solicitar alertas</button><p role="status" id="alert-status"></p></form>'


def build(core):
    paths=[]
    def emit(path,title,desc,body,private=False):
        html='<div class="page-head"><div class="wrap"><div class="crumbs"><a href="/">Monitor público</a> › '+esc(title)+'</div><h1>'+esc(title)+'</h1><p class="sub">'+esc(desc)+'</p></div></div><section class="block"><div class="wrap commercial-content">'+body+'</div></section>'
        ld=core.ld_collection(title,desc,path+'/')
        core.write(path+'/index.html',core.page(title+' — LCF Consulting',desc,path+'/',html,extra_head='<meta name="robots" content="noindex,nofollow">' if private else '',jsonld=ld))
        if not private: paths.append(path+'/')
    cards=[]
    for o in CONFIG['offers']:
        price=f'R$ {o["min"]:,.0f}–{o["max"]:,.0f}/{o["period"]}'.replace(',','.') if 'min' in o else 'Sob consulta'
        cards.append('<article class="commercial-card '+('featured' if o.get('featured') else '')+'">'+('<p class="eyebrow">OFERTA PRINCIPAL</p>' if o.get('featured') else '')+f'<h2>{esc(o["name"])}</h2><p>{esc(o["audience"])}</p><p class="price">{price}</p><ul>'+''.join(f'<li>{esc(f)}</li>' for f in o['features'])+'</ul>'+cta('Solicitar diagnóstico' if o['id']=='diagnostico' else 'Avaliar este escopo',kind=o['id'])+'</article>')
    emit('solucoes','Soluções de inteligência regulatória para empresas',CONFIG['pricing_note'],'<div class="commercial-grid">'+''.join(cards)+'</div><p>Alertas e relatórios são entregas da contratação ou de piloto acordado. API/webhook, SLA e white-label exigem validação de implantação antes da proposta.</p><p>'+DISCLAIMER+'</p>')
    emit('diagnostico','Sua empresa sabe quais mudanças na regulação de IA podem afetá-la nos próximos meses?','Solicite uma conversa de diagnóstico com a LCF Consulting.',diagnostics())
    emit('para-empresas','Inteligência regulatória de IA para quem não pode descobrir mudanças legislativas tarde demais.','IA, dados, infraestrutura digital e tecnologias de alta consequência regulatória.','<div class="commercial-grid"><article class="commercial-card"><h2>Da mudança à decisão interna</h2><p>Uma atualização legislativa pode afetar modelos de IA, tratamento de dados, infraestrutura e prioridades de investimento. Sua equipe precisa entender relevância, evidência e responsáveis.</p>'+cta()+'</article><article class="commercial-card"><h2>O que sua organização recebe</h2><p>Priorização pelo AI Legislative Impact Score, histórico, análise preliminar de impacto, alertas, briefing e reunião executiva conforme o escopo contratado.</p><a href="/solucoes/">Comparar formas de contratação</a></article></div><h2>Por que uma plataforma especializada</h2><dl class="business-dimensions"><div><dt>Especialização</dt><dd>IA, dados e infraestrutura digital.</dd></div><div><dt>Priorização</dt><dd>Score com rúbrica pública e explicação dos fatores disponíveis.</dd></div><div><dt>Auditabilidade</dt><dd>Fonte oficial, data de verificação e histórico.</dd></div><div><dt>Tradução empresarial</dt><dd>Do evento para a avaliação do processo operacional.</dd></div><div><dt>Velocidade</dt><dd>Mudança → classificação → alerta → briefing. Detecção depende da cadência da coleta e disponibilidade das fontes.</dd></div></dl><h2>Segurança e auditabilidade</h2><p>O monitor público demonstra cobertura e método. Informações de contato e preferências de clientes são tratadas separadamente. Pilotos têm escopo, prazo e usuários definidos.</p><a href="/metodologia/">Ver metodologia e limitações</a><p>'+DISCLAIMER+'</p>')
    model=briefing(as_of=core.EXECUTION_DATE)
    emit('briefing-executivo','Executive Regulatory Brief — exemplo de briefing executivo','O que mudou, por que importa, quem pode ser afetado e qual evidência sustenta a análise.',briefing_body(model,core))
    props=core.load('propositions.json')['proposicoes']
    filters='<label>Filtrar prioridade<select id="impact-filter"><option value="80">Score 80+</option><option value="60-79">Score 60–79</option><option value="low">Score &lt;60</option><option value="all">Todos</option></select></label><p role="status" id="impact-count"></p>'
    emit('alto-impacto','Matérias prioritárias por impacto','Use o score para organizar a triagem; confirme aplicabilidade e situação na ficha oficial.',filters+''.join(prop_card(p,core) for p in sorted(props,key=score,reverse=True)))
    for slug,sector in CONFIG['sectors'].items():
        selected=[p for p in props if slug in sectors_for(p)]
        top=sorted(selected,key=score,reverse=True)[:8]
        m=briefing(as_of=core.EXECUTION_DATE,sector=slug)
        sector_body='<h2>Quais temas acompanhar</h2><p>'+esc(sector['focus'])+'</p><p>Seleção temática por categorias do monitor; o marco geral pode alcançar vários setores. Isso não confirma aplicabilidade jurídica.</p><h2>Projetos relacionados e maiores scores</h2>'+''.join(prop_card(p,core) for p in top)
        sector_body+='<h2>O que mudou recentemente</h2>'+(''.join(f'<p>{esc(c.get("data_deteccao") or c.get("data", ""))} — {esc(c["titulo"])} · <a href="{esc(c["fonte_url"])}">Fonte oficial</a></p>' for c in m['changes'][:8]) or '<p>Nenhuma mudança com fonte oficial registrada neste recorte de sete dias.</p>')
        sector_body+='<h2>Próximos eventos relevantes</h2>'+(''.join(f'<p>{esc(e["data_inicio"])} — <a href="{esc(e["fonte_url"])}">{esc(e["titulo"])}</a></p>' for e in m['events']) or '<p>Nenhum evento com vínculo setorial explícito e fonte oficial nos próximos sete dias. <a href="/agenda/">Consultar agenda pública</a>.</p>')
        sector_body+='<h2>O que acompanhar</h2><p>Novos textos, alterações de relatoria, inclusão em pauta e mudanças de score. Encaminhe evidências à equipe responsável pelo processo afetado.</p>'+cta('Receber briefing regulatório deste setor',sector['name'],'briefing-setorial')
        emit('setores/'+slug,'Regulação de IA para '+sector['name'],sector['focus'],sector_body)
    emit('casos-de-uso','Inteligência regulatória por área de atuação','Informação relevante para cada decisão dentro da organização.','<div class="commercial-grid">'+''.join(f'<article class="commercial-card"><h2><a href="/casos-de-uso/{slug}/">{esc(v["name"])}</a></h2><p>{esc(v["value"])}</p></article>' for slug,v in CONFIG['personas'].items())+'</div>')
    for slug,v in CONFIG['personas'].items():
        emit('casos-de-uso/'+slug,v['name']+' — regulação de IA',v['value'],'<h2>Da evidência à sua rotina</h2><ol><li>Defina temas e processos que exigem acompanhamento.</li><li>Priorize por score, estágio e exposição potencial.</li><li>Distribua fontes e análise aos responsáveis internos.</li><li>Revise a watchlist e as decisões na reunião executiva.</li></ol><a href="/briefing-executivo/">Examinar um briefing executivo</a><div class="commercial-actions">'+cta('Solicitar demonstração contextualizada',kind='demo')+'</div>')
    emit('alertas','Alertas regulatórios por e-mail','Acompanhe mudanças legislativas, novas proposições, votações, pauta, relatoria, normas, eventos e mudanças relevantes de score.','<p>“Imediato” significa após a detecção pelo monitor. A coleta atual é diária; não há promessa de monitoramento em tempo real.</p>'+alert_form(core)+'<div id="subscription-action" role="status"></div>')
    emit('watchlist','Sua watchlist','Salve matérias para preparar uma conversa contextualizada.','<p>Os itens públicos ficam neste navegador. Em um piloto autenticado, você pode sincronizar sua lista com sua conta.</p><div id="watchlist-items"></div><button class="watch-button" id="watch-sync">Sincronizar com minha conta</button><p role="status" id="watch-status"></p>'+cta())
    emit('login','Acesso ao piloto','Entre com o e-mail e a senha definidos para seu piloto.','<form id="login-form" class="commercial-card">'+input_field('email','E-mail','email')+input_field('password','Senha','password')+'<button class="commercial-button">Acessar piloto</button><p role="status" id="login-status"></p></form><p>O acesso é provisionado pela equipe após definição do escopo. Para obter ou recuperar acesso, solicite uma conversa.</p>'+cta(),True)
    emit('app','Área do cliente','Dashboard do piloto e preferências de acompanhamento.','<div id="client-app"><p>Verificando acesso…</p></div><button id="logout" class="watch-button">Sair</button>',True)
    emit('privacidade','Privacidade e uso de dados','Transparência na solicitação de diagnóstico e de alertas.','<h2>Responsável e finalidade</h2><p>A LCF Consulting usa nome, contato profissional, empresa, cargo e informações de exposição para responder à solicitação, priorizar a conversa comercial e preparar proposta. Alertas exigem solicitação específica e confirmação por e-mail.</p><h2>Registro e acesso</h2><p>Contatos e preferências ficam no serviço comercial privado. Eventos de navegação registram página, CTA, setor e campanha, sem incluir campos do formulário. A atribuição de campanha usa armazenamento da sessão no navegador; não fazemos rastreamento entre sites.</p><h2>Retenção e direitos</h2><p>Leads sem evolução são previstos para exclusão após 180 dias, sujeitos à necessidade documentada de continuidade da relação. Eventos comerciais são retidos por até 90 dias. Solicite acesso, correção, exclusão ou revogação pela <a href="https://lcfconsulting.com.br/">LCF Consulting</a>, identificando a solicitação feita neste monitor. Cancelar alertas não elimina automaticamente uma relação comercial existente.</p><p>Provedores de hospedagem, banco e e-mail processam dados necessários à operação. A configuração de produção deve ser revisada antes da ativação.</p>')
    return paths


def install(core):
    old_page=core.page
    old_main=core.main
    def commercial_page(title,desc,path,body,extra_head='',og_type='website',jsonld=None):
        html=old_page(title,desc,path,body,extra_head,og_type,jsonld)
        assets='<link rel="stylesheet" href="/assets/commercial.css"><script src="/assets/commercial.js" defer></script>'
        html=html.replace('</head>',assets+'</head>',1)
        nav='<nav class="commercial-nav wrap" aria-label="Soluções empresariais"><a href="/para-empresas/">Para empresas</a><a href="/solucoes/">Soluções</a><a href="/briefing-executivo/">Briefing executivo</a><a href="/alto-impacto/">Alto impacto</a><a href="/casos-de-uso/">Casos de uso</a><a href="/alertas/">Alertas</a><a href="/watchlist/">Watchlist</a><a href="/login/">Área do cliente</a></nav>'
        html=html.replace('</header>',nav+'</header>'+('' if path in ('login/','app/') else strip()),1)
        sector_links='<div class="wrap sector-links"><strong>Inteligência por setor</strong> '+''.join(f'<a href="/setores/{slug}/">{esc(s["name"])}</a> ' for slug,s in CONFIG['sectors'].items())+'<a href="/privacidade/">Privacidade</a></div>'
        html=html.replace('</footer>',sector_links+'</footer>',1)
        return "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    def main():
        old_main()
        paths=build(core)
        file=Path(core.OUT)/'sitemap.xml';root=ET.fromstring(file.read_text());ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        old_paths=[n.text.removeprefix(core.SITE_URL+'/') for n in root.findall('s:url/s:loc',ns)]
        # Reuse the sitemap formatter; retain AI crawler directives after it writes robots.
        robots=(Path(core.OUT)/'robots.txt').read_text()
        core.build_sitemap(old_paths+paths)
        (Path(core.OUT)/'robots.txt').write_text(robots)
        print(f'OK: camada comercial — {len(paths)} URLs indexáveis; login/app fora do sitemap.')
    core.page=commercial_page
    core.main=main
