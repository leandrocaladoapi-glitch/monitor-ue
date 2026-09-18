"""Durable baseline/diff, filtered delivery queue and opt-in SMTP transport."""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from . import notify
from .intelligence import load, official, score, briefing, email_briefing
from .service import queue, token_record

CHANNELS={'email':'implemented','whatsapp':'future','telegram':'future','webhook':'future','slack':'future','teams':'future'}


def snapshots():
    records={}
    for p in load('propositions')['proposicoes']:
        if not official(p.get('url_oficial')):continue
        api=p.get('api_camara') or {}
        records['proposition:'+p['id']]={'id':p['id'],'entity':'proposition','title':f'{p["tipo"]} {p["numero"]}/{p["ano"]}', 'source':p['url_oficial'],'themes':p.get('categorias',[]),'org':p.get('casa_atual') or p.get('casa_origem'),'score':score(p),'status':api.get('descricao_situacao') or p.get('situacao'), 'movement':api.get('ultima_tramitacao') or p.get('ultima_movimentacao'), 'rapporteur':api.get('relator_api') or p.get('relator') or p.get('relator_camara'), 'votes':api.get('votacoes_total')}
    for p in load('laws')['normas']:
        if official(p.get('url')):records['law:'+p['id']]={'id':p['id'],'entity':'law','title':p['nome'],'source':p['url'],'themes':p.get('categorias',[]),'org':p.get('orgao',''),'score':None,'status':p.get('status'),'date':p.get('data')}
    for p in load('events')['eventos']:
        if official(p.get('fonte_url')):records['event:'+p['id']]={'id':p['id'],'entity':'event','title':p['titulo'],'source':p['fonte_url'],'themes':p.get('categorias',[]),'org':p.get('casa',''),'score':None,'date':p.get('data_inicio'),'propositions':p.get('proposicoes',[])}
    return records


def classify(previous,current):
    if previous is None:return ['novo projeto' if current['entity']=='proposition' else 'nova norma' if current['entity']=='law' else 'evento']
    kinds=[]
    if current.get('rapporteur')!=previous.get('rapporteur'):kinds.append('alteração de relatoria')
    if current.get('votes')!=previous.get('votes') and current.get('votes') is not None:kinds.append('votação')
    if isinstance(current.get('score'),int) and isinstance(previous.get('score'),int) and abs(current['score']-previous['score'])>=5:kinds.append('alteração relevante de score')
    if current.get('movement')!=previous.get('movement'):
        desc=json.dumps(current.get('movement'),ensure_ascii=False).lower()
        kinds.append('inclusão em pauta' if 'pauta' in desc else 'mudança legislativa')
    if current.get('status')!=previous.get('status'):kinds.append('mudança legislativa')
    if current.get('date')!=previous.get('date') and current['entity']=='event':kinds.append('evento')
    return list(dict.fromkeys(kinds))


def capture(s,records=None,now=None):
    now=int(now or time.time());records=snapshots() if records is None else records
    s.lock('alert-snapshot')
    previous=s.get('system','alert-snapshot')
    # First run establishes baseline, never broadcasts the entire historical corpus.
    if previous is not None:
        for key,record in records.items():
            before=previous['records'].get(key)
            kinds=classify(before,record)
            if not kinds:continue
            change_id=hashlib.sha256(json.dumps([key,before,record],sort_keys=True).encode()).hexdigest()
            s.insert('alert_change',change_id,{'detected_at':now,'types':kinds,'record':record,'before':before})
    s.put('system','alert-snapshot',{'records':records,'captured_at':now})


def matches(sub,change):
    r=change['record']
    if change['detected_at']<sub.get('confirmed_at',sub['created_at']):return False
    if sub['score_min'] and (r.get('score') is None or r['score']<sub['score_min']):return False
    if sub['temas'] and not set(sub['temas']).intersection(r.get('themes',[])):return False
    if sub['proposicoes'] and r['id'] not in sub['proposicoes'] and not set(sub['proposicoes']).intersection(r.get('propositions',[])):return False
    org=r.get('org','')
    if sub['orgaos'] and not any(o==org or o in org for o in sub['orgaos']):return False
    return True


def prepare(s,now=None):
    now=int(now or time.time());changes=s.list('alert_change',limit=10000)
    for key,sub in s.list('subscription',limit=10000):
        if not sub.get('active'):continue
        account=sub.get('account_id','')
        if account:
            a=s.get('account',account)
            if not a or a['status']=='inactive' or (a.get('ends_on') and a['ends_on']<datetime.fromtimestamp(now,timezone.utc).date().isoformat()):continue
        interval={'imediato':0,'diario':86400,'semanal':604800}[sub['frequencia']]
        if now-sub.get('last_queued_at',sub.get('confirmed_at',now))<interval:continue
        s.lock('subscription:'+key)
        selected=[(cid,c) for cid,c in changes if matches(sub,c) and not s.get('alert_delivery',key+':'+cid)]
        weekly=sub['frequencia']=='semanal'
        if not selected and not weekly:continue
        unsubscribe=token_record(s,'unsubscribe','',{'subscription':key},account,days=3650)
        site=os.environ.get('SITE_URL','https://monitor.lcfconsulting.com.br').rstrip('/')
        lines=['Monitor Legislativo de IA — alerta regulatório','FATOS OFICIAIS: mudanças detectadas no registro. Confirme o texto na fonte.']
        for cid,c in selected:
            r=c['record'];lines+=['',r['title']+' — '+', '.join(c['types']),'AI Legislative Impact Score: '+str(r.get('score') if r.get('score') is not None else 'não atribuído'),r['source']]
        lines+=['','ANÁLISE / INTERPRETAÇÃO: encaminhar à equipe responsável para triagem da exposição. Não constitui aconselhamento jurídico.',f'Briefing: {site}/briefing-executivo/',f'Cancelar alertas: {site}/alertas/#unsubscribe={unsubscribe}']
        outkey='alert-'+hashlib.sha256((key+':'+str(now//604800 if weekly else '')+':'+','.join(cid for cid,_ in selected)).encode()).hexdigest()
        queue(s,outkey,sub['email'],'Atualização regulatória de IA — matérias selecionadas','\n'.join(lines),account)
        mail=s.get('outbox',outkey);mail['subscription_id']=key
        if weekly:
            model=briefing(as_of=datetime.fromtimestamp(now,timezone.utc).date(),since=datetime.fromtimestamp(sub.get('last_queued_at',now-604800),timezone.utc).date(),themes=sub['temas'],watchlist=sub['proposicoes'],score_min=sub['score_min'],organs=sub['orgaos'])
            from html import escape
            mail['html']=email_briefing(model).replace('</body>', '<p><a href="'+escape(site+'/alertas/#unsubscribe='+unsubscribe,quote=True)+'">Cancelar alertas</a></p></body>')
            mail['subject']='Executive Regulatory Brief — seu recorte semanal'
        s.put('outbox',outkey,mail,account)
        for cid,_ in selected:s.insert('alert_delivery',key+':'+cid,{'queued_at':now,'outbox_id':outkey},account)
        sub['last_queued_at']=now;s.put('subscription',key,sub,account)


def send_smtp(mail,key):
    message=EmailMessage()
    message['From']=os.environ['SMTP_FROM'];message['To']=mail['to'];message['Subject']=mail['subject']
    message['Message-ID']='<'+hashlib.sha256(key.encode()).hexdigest()+'@monitor.lcfconsulting.com.br>'
    message.set_content(mail['text'])
    if mail.get('html'):message.add_alternative(mail['html'],subtype='html')
    notify.smtp_send(message)


def deliver(connect,transport=send_smtp,limit=50):
    """Only explicit --send calls this. A crash after SMTP acceptance may duplicate a message."""
    sent=0
    with connect() as s: candidates=s.list('outbox',limit=10000)
    for key,_ in candidates:
        if sent>=limit:break
        with connect() as s:
            s.lock('outbox:'+key);mail=s.get('outbox',key);now=int(time.time())
            if mail['status'] in {'sent','cancelled'} or mail.get('next_attempt',0)>now:continue
            sid=mail.get('subscription_id');sub=s.get('subscription',sid) if sid else None
            account=s.get('account',sub.get('account_id')) if sub and sub.get('account_id') else None
            expired=account and (account['status']=='inactive' or (account.get('ends_on') and account['ends_on']<str(datetime.now(timezone.utc).date())))
            if sid and (not sub or not sub.get('active') or expired):
                mail['status']='cancelled';s.put('outbox',key,mail);continue
            mail.update({'status':'sending','next_attempt':now+300,'attempts':mail['attempts']+1})
            s.put('outbox',key,mail)
        try:
            transport(mail,key)
        except Exception:
            with connect() as s:
                mail.update({'status':'retry','next_attempt':int(time.time())+min(86400,60*2**min(mail['attempts'],10)),'last_error':'smtp_delivery_failed'})
                s.put('outbox',key,mail)
        else:
            with connect() as s:mail.update({'status':'sent','sent_at':int(time.time())});s.put('outbox',key,mail)
            sent+=1
    return sent
