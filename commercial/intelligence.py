"""Evidence-led briefing model. No new legislative facts or altered scores."""
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config/commercial.json').read_text())
OFFICIAL = ('camara.leg.br', 'senado.leg.br', 'congressonacional.leg.br', 'planalto.gov.br', 'in.gov.br', 'gov.br', 'tse.jus.br', 'cnj.jus.br')


def official(url):
    host = (urlparse(str(url)).hostname or '').lower()
    return urlparse(str(url)).scheme == 'https' and any(host == d or host.endswith('.' + d) for d in OFFICIAL)


def load(name):
    return json.loads((ROOT / 'data/legislation' / (name + '.json')).read_text())


def score(p):
    return (p.get('impacto') or {}).get('score', 0)


def sectors_for(p):
    cats = set(p.get('categorias', []))
    return [k for k, s in CONFIG['sectors'].items() if cats.intersection(s['categories']) or 1 in cats]


def business_impact(p):
    cats = set(p.get('categorias', []))
    sectors = sectors_for(p)
    dimensions = {
        'impacto_em_compliance': bool(cats & {1, 24, 25, 26}),
        'impacto_em_dados': bool(cats & {3, 17, 18}),
        'impacto_em_modelos_ia': bool(cats & {1, 6, 23, 24, 25, 26}),
        'impacto_em_infraestrutura': bool(cats & {22, 28, 29, 30}),
    }
    focuses = [CONFIG['sectors'][s]['focus'] for s in sectors[:3]]
    return {
        'setores_afetados': sectors,
        'tipo_de_impacto': 'Triagem temática; aplicabilidade depende do uso de IA e da versão do texto.',
        'prazo_provavel': 'Não confirmado. Depende de tramitação, texto final e regulamentação.',
        'obrigacao_potencial': 'A confirmar por revisão do texto aplicável; proposição não é obrigação vigente.',
        'risco_operacional': 'Mapear dependência de IA, responsáveis e controles relacionados ao tema.',
        'impacto_financeiro_potencial': 'Não quantificado; depende da exposição e dos custos internos.',
        **{k: ('Tema relacionado; requer avaliação interna.' if v else 'Não classificado nesta triagem.') for k,v in dimensions.items()},
        'status_da_interpretacao': 'Análise preliminar por categorias; não validada para uma organização específica.',
        'por_que_importa': 'Pode exigir atenção aos processos: ' + ' '.join(focuses) if focuses else 'Avaliar relação com processos e controles internos antes de priorizar.',
        'acao_recomendada': 'Informar compliance e jurídico interno para triagem; acompanhar a fonte oficial.',
        'metodo': 'sector-category-v1',
        'fonte': p.get('url_oficial'),
    }


def official_fact(p):
    api = p.get('api_camara') or {}
    movement = api.get('ultima_tramitacao') or {}
    # Prefer the official API text over editorial summaries in the legacy dataset.
    return {
        'descricao': movement.get('despacho') or movement.get('tramitacao') or p.get('ementa', ''),
        'data_evento': movement.get('data'),
        'verificado_em': api.get('verificado_em') or (p.get('api_senado') or {}).get('verificado_em'),
        'situacao': api.get('descricao_situacao') or 'Consultar situação na ficha oficial.',
        'orgao': movement.get('orgao') or api.get('sigla_orgao'),
        'fonte': p.get('url_oficial'),
    }


def briefing(as_of=None, since=None, sector=None, themes=None, watchlist=None, score_min=0, organs=None):
    today = date.fromisoformat(str(as_of or date.today())[:10])
    start = date.fromisoformat(str(since)[:10]) if since else today - timedelta(days=7)
    props = [p for p in load('propositions')['proposicoes'] if official(p.get('url_oficial'))]
    if sector:
        props = [p for p in props if sector in sectors_for(p)]
    if themes:
        props = [p for p in props if set(themes).intersection(p.get('categorias', []))]
    if watchlist:
        props = [p for p in props if p['id'] in watchlist]
    props = [p for p in props if score(p)>=score_min and (not organs or (p.get('casa_atual') or p.get('casa_origem')) in organs)]
    ids = {p['id'] for p in props}
    changes = [m for m in load('updates')['mudancas'] if m.get('proposicao') in ids and official(m.get('fonte_url')) and str(start) <= (m.get('data_deteccao') or m.get('data', ''))[:10] <= str(today)]
    changes.sort(key=lambda m: m.get('data_deteccao') or m.get('data', ''), reverse=True)
    # Event sector relationship must be explicit; no invented matching dates.
    events = [e for e in load('events')['eventos'] if official(e.get('fonte_url')) and str(today) <= e.get('data_inicio', '')[:10] <= str(today + timedelta(days=7)) and (not sector or sector in e.get('setores', []) or set(e.get('proposicoes', [])).intersection(ids))]
    if themes or watchlist or organs or score_min:
        events = [e for e in events if (not themes or set(themes).intersection(e.get('categorias', []))) and (not watchlist or set(watchlist).intersection(e.get('proposicoes', []))) and (not organs or e.get('casa') in organs) and (not score_min or (e.get('impacto') or {}).get('score', -1)>=score_min)]
    return {'title':'Executive Regulatory Brief', 'as_of':str(today), 'since':str(start), 'sector':sector,
            'top': sorted(props, key=lambda p: (-score(p),p['id']))[:5], 'changes':changes, 'events':events,
            'critical_changes':[m for m in changes if score(next(p for p in props if p['id']==m['proposicao'])) >=80],
            'coverage':load('updates').get('execucoes', [{}])[0].get('status', 'não informado'),
            'coverage_pct':load('updates').get('execucoes', [{}])[0].get('cobertura_pct'),
            'source_errors':len(load('updates').get('execucoes', [{}])[0].get('erros', []))}


def email_briefing(model):
    """Standalone HTML e-mail using escaped evidence, no public private-report URL."""
    from html import escape
    def changes(items):
        return '<ul>'+''.join('<li>'+escape(c.get('titulo',''))+' — <a href="'+escape(c['fonte_url'],quote=True)+'">Fonte oficial</a></li>' for c in items)+'</ul>' if items else '<p>Nenhuma mudança registrada neste recorte com fonte oficial. A coleta pode ser parcial.</p>'
    body='<h1>Executive Regulatory Brief</h1><p>'+escape(model['since']+' a '+model['as_of'])+'</p><p>Coleta: '+escape(model['coverage'])+'; cobertura '+str(model['coverage_pct'])+'%; erros registrados '+str(model['source_errors'])+'</p><h2>Mudanças críticas da semana</h2>'+changes(model['critical_changes'])+'<h2>Top 5 matérias por impacto</h2>'
    for p in model['top']:
        f=official_fact(p);a=business_impact(p)
        body+='<h3>'+escape(p['titulo'])+' — '+str(score(p))+'/100</h3><p><b>FATO OFICIAL · último registro:</b> '+escape(f['descricao'])+'</p><p>Data: '+escape(str(f['data_evento'] or 'não informada'))+' · <a href="'+escape(f['fonte'],quote=True)+'">Fonte oficial</a></p><p><b>ANÁLISE / INTERPRETAÇÃO:</b> '+escape(a['por_que_importa'])+'</p><p>'+escape(a['acao_recomendada'])+'</p>'
    body+='<h2>Mudanças desde o último relatório</h2>'+changes(model['changes'])+'<h2>Agenda dos próximos 7 dias</h2>'
    body+=''.join('<p>'+escape(e['data_inicio'])+' — <a href="'+escape(e['fonte_url'],quote=True)+'">'+escape(e['titulo'])+'</a></p>' for e in model['events']) or '<p>Nenhum evento com fonte oficial neste recorte.</p>'
    body+='<h2>Pontos de atenção executiva e metodologia</h2><p>Revisar prioridades com os responsáveis internos. Análise temática preliminar; score existente preservado; nenhuma obrigação é inferida de proposições. Não constitui aconselhamento jurídico.</p>'
    return '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><body style="font-family:Arial,sans-serif;color:#14212d;max-width:760px;margin:auto">'+body+'</body></html>'
