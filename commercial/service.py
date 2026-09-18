"""Lead capture, consented alerts and account-isolated pilot operations."""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import unicodedata
from datetime import date
from urllib.parse import urlparse
from . import notify
from .intelligence import CONFIG, load, briefing, business_impact, official_fact, score

EVENTS={'commercial_cta_click','diagnostic_started','diagnostic_submitted','briefing_sample_view','pricing_view','sector_page_view','high_impact_view','alert_signup','demo_request','whatsapp_click'}
SECTORS={'Tecnologia','Bancos','Fintech','Seguros','Saúde','Telecom','Cloud','Data Center','Infraestrutura','Jurídico','Consultoria','Associação','Governo','Outro'}
FREQUENCIES={'imediato','diario','semanal'}
REPLY_REGISTERED='Solicitação registrada. A equipe da LCF Consulting avaliará o contexto para a conversa inicial.'
REPLY_SENT='Solicitação registrada e enviada à equipe da LCF Consulting. Responderemos no e-mail informado.'
REPLY_QUEUED='Solicitação registrada com segurança. O aviso à equipe está na fila de envio e será reenviado automaticamente.'
REPLY_UNAVAILABLE='O recebimento de contatos está indisponível no momento e nada foi registrado. Tente novamente em alguns minutos ou fale com a LCF Consulting pelo site.'

# Best-effort guards for the no-database mode. Warm function instances share them; new instances do not.
LOCAL={}
LOCAL_TTL=3600


class Problem(Exception):
    """Client-facing failure. Payload carries safe extra fields (e.g. an emergency mailto link)."""
    def __init__(self,status,message,payload=None):super().__init__(message);self.status=status;self.payload=payload or {}


def _local_prune(now=None):
    now=now or int(time.time())
    for key in [k for k,entry in LOCAL.items() if entry.get('seen',now)<now-LOCAL_TTL]:LOCAL.pop(key,None)


def local_rate_limit(identity,bucket,maximum=20):
    """Hourly counter per origin and route, single instance only. The durable limiter uses the store."""
    _local_prune();key='limit:'+identity+':'+bucket;now=int(time.time())
    entry=LOCAL.get(key)
    if not entry or entry['window']+LOCAL_TTL<now:entry={'window':now,'count':0,'seen':now}
    if entry['count']>=maximum:raise Problem(429,'Muitas tentativas. Aguarde antes de tentar novamente.')
    entry['count']+=1;entry['seen']=now;LOCAL[key]=entry


def local_seen(key,fingerprint):
    """True when this instance already completed this submission. Recorded only after success,
    so a failed attempt stays retryable instead of being acknowledged as delivered."""
    _local_prune();entry=LOCAL.get('seen:lead:'+key)
    if entry and entry['value']!=fingerprint:raise Problem(409,'O formulário mudou. Recarregue a página para um novo envio.')
    return bool(entry)


def local_remember(key,fingerprint):
    LOCAL['seen:lead:'+key]={'value':fingerprint,'seen':int(time.time())}


def clean(value,limit=256):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:raise Problem(400,'Revise os campos informados.')
    return value.strip()


def email(value):
    value=clean(value).lower()
    if not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+',value) or '\r' in value or '\n' in value:raise Problem(400,'Informe um e-mail válido.')
    return value


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def token_record(s,kind,key,record,account='',days=7):
    token=secrets.token_urlsafe(32)
    record={**record,'expires':int(time.time())+days*86400}
    s.put(kind,digest(token),record,account)
    return token


def attribution(raw):
    raw=raw if isinstance(raw,dict) else {}
    result={}
    for k in ('page','cta','sector','source','campaign','utm_source','utm_medium','utm_campaign','utm_content','utm_term'):
        value=raw.get(k,'')
        if isinstance(value,str) and len(value)<=160 and not re.search(r'[@<>?\r\n]',value):
            result[k]=value
    result['timestamp']=int(time.time())
    return result


def lead_score(d):
    role=unicodedata.normalize('NFKD',d.get('cargo','').lower()).encode('ascii','ignore').decode()
    factors={
        'grande_empresa':20 if d.get('tamanho')=='501+' else 0,
        'setor_prioritario':20 if d.get('setor') in {'Bancos','Fintech','Seguros','Tecnologia','Cloud','Data Center'} else 0,
        'decisor':15 if re.search(r'\b(diretor\w*|director|head|socio\w*|partner|ceo|cto|cio|cfo)\b',role) else 0,
        'area_controle':15 if d.get('area_controle')=='sim' else 0,
        'urgencia_imediata':15 if d.get('urgencia')=='imediata' else 0,
        'ia_critica':10 if d.get('uso_ia')=='critico' else 0,
        'mais_100_pessoas':5 if d.get('tamanho') in {'101-500','501+'} else 0,
    }
    total=sum(factors.values())
    return {'score':total,'classificacao':'prioridade comercial' if total>=70 else 'alto' if total>=50 else 'médio' if total>=30 else 'baixo','fatores':factors,'versao':'1'}


def queue(s,key,to,subject,text,account=''):
    s.insert('outbox',key,{'to':to,'subject':subject,'text':text,'status':'pending','attempts':0,'next_attempt':0},account)


def queue_now(s,key,to,subject,text,account=''):
    """Deliver in this invocation and keep the queue row as the durable retry path. Returns 'sent' or 'queued'.

    The queue row is what the hourly delivery job resends; marking it sent only after an accepted
    handoff avoids both silent loss and double sending.
    """
    queue(s,key,to,subject,text,account)
    if not notify.provider():return 'queued'
    try:notify.send(subject,text,to.split(', ') if isinstance(to,str) else to)
    except notify.DeliveryError:return 'queued'
    mail=s.get('outbox',key)
    if mail:mail.update({'status':'sent','sent_at':int(time.time())});s.put('outbox',key,mail,account)
    return 'sent'


def rate_limit(s,identity,bucket,maximum=20):
    secret=os.environ.get('RATE_LIMIT_SECRET') or ('development-only' if os.environ.get('MONITOR_DEV')=='1' and not os.environ.get('VERCEL') else '')
    if not secret:raise RuntimeError('Rate limit secret not configured')
    key=hmac.new(secret.encode(),f'{identity}:{bucket}:{int(time.time())//3600}'.encode(),hashlib.sha256).hexdigest()
    s.lock(key)
    d=s.get('rate',key) or {'n':0,'expires':int(time.time())+7200}
    if d['n']>=maximum:raise Problem(429,'Muitas tentativas. Aguarde antes de tentar novamente.')
    d['n']+=1;s.put('rate',key,d);s.commit()


def guard(s,identity,bucket,maximum=20,strict=False):
    """Rate limiting. `strict` routes (login) require the durable limiter and never degrade silently."""
    if s is not None and os.environ.get('RATE_LIMIT_SECRET'):
        rate_limit(s,identity,bucket,maximum);return
    if strict:raise Problem(503,'Autenticação indisponível no momento. Tente novamente mais tarde.')
    local_rate_limit(identity,bucket,maximum)


def capture_lead(s,d):
    """Validate, score and persist (when a store exists), then notify the operator.

    `s` may be None: capture then relies on the direct operator notification, which is the only
    arrangement that keeps incoming contacts available before a database is provisioned.
    """
    if d.get('website'):raise Problem(400,'Não foi possível enviar este formulário.')
    if d.get('consent') is not True:raise Problem(400,'É necessário autorizar o uso dos dados para esta solicitação.')
    result={k:clean(d.get(k,''),2000 if k=='preocupacao' else 256) for k in ('nome','empresa','cargo','telefone','setor','tamanho','uso_ia','area_controle','urgencia','preocupacao','interesse')}
    result['email']=email(d.get('email'))
    if any(not result[k] for k in ('nome','empresa','cargo','preocupacao','interesse')):raise Problem(400,'Preencha os campos obrigatórios.')
    allowed={'setor':SECTORS,'tamanho':{'1-10','11-100','101-500','501+'},'uso_ia':{'nao','apoio','critico'},'area_controle':{'sim','nao'},'urgencia':{'imediata','trimestre','exploratoria'},'interesse':{'diagnostico','radar-executivo','monitor-ia','institucional','briefing-setorial','demo'}}
    if any(result[k] not in options for k,options in allowed.items()):raise Problem(400,'Selecione opções válidas.')
    key=clean(d.get('request_id',''),64)
    if not re.fullmatch(r'[a-zA-Z0-9-]{16,64}',key):raise Problem(400,'Identificador de envio inválido.')
    result.update(lead_score(result));result.update({'attribution':attribution(d.get('attribution')),'consent_at':int(time.time()),'consent_version':'2026-09-v1','stage':'lead','created_at':int(time.time())})
    # Stable payload binding: timestamps do not turn a network retry into a duplicate lead.
    stable={k:result[k] for k in ('nome','empresa','cargo','telefone','email','setor','tamanho','uso_ia','area_controle','urgencia','preocupacao','interesse')}
    fingerprint=digest(json.dumps(stable,sort_keys=True,ensure_ascii=False))
    result['fingerprint']=fingerprint
    persisted=False
    if s is not None:
        s.lock('lead:'+key)
        existing=s.get('lead',key)
        if existing and existing.get('fingerprint')!=fingerprint:raise Problem(409,'O formulário mudou. Recarregue a página para um novo envio.')
        if existing:return {'ok':True,'request_id':key,'message':REPLY_REGISTERED,'persisted':True}
        s.insert('lead',key,result);persisted=True
        event='demo_request' if result['interesse']=='demo' else 'diagnostic_submitted'
        s.insert('event',key,{'name':event,**result['attribution']})
        if event=='demo_request':s.insert('event',key+'-diagnostic',{'name':'diagnostic_submitted',**result['attribution']})
    elif local_seen(key,fingerprint):
        # Without the private store a warm function instance is the only deduplicator available.
        return {'ok':True,'request_id':key,'message':REPLY_REGISTERED}
    notification=notify.notify_lead(result,key,persisted)
    if notification['notified']:
        if not persisted:local_remember(key,fingerprint)
        if persisted:
            result['notified_at']=int(time.time());result['email_provider']=notification['provider']
            s.put('lead',key,result)
        return {'ok':True,'request_id':key,'message':REPLY_SENT,'persisted':persisted,'notified':True}
    if persisted:
        # The record is safe in the private store; an unavailable inbox is the operator's problem, not the visitor's.
        try:targets=', '.join(notify.recipients())
        except notify.DeliveryError:targets=''
        if targets and notification['retryable']:
            status=queue_now(s,'lead-'+key,targets,lead_subject(result),notify.lead_text(result,key,True))
            result['notification']={'status':status,'reason':notification['reason']};s.put('lead',key,result)
            return {'ok':True,'request_id':key,'message':REPLY_SENT if status=='sent' else REPLY_QUEUED,'persisted':True,'notified':status=='sent'}
        result['notification']={'status':'unavailable','reason':notification['reason']};s.put('lead',key,result)
        return {'ok':True,'request_id':key,'message':REPLY_REGISTERED,'persisted':True,'notified':False}
    fallback=notify.mailto(result)
    raise Problem(503,REPLY_UNAVAILABLE,{'mailto':fallback} if fallback else {})


def lead_subject(lead):
    return f"Novo contato — {lead.get('empresa') or lead.get('nome') or 'Monitor Legislativo'} — score {lead.get('score','—')}"


def preferences(d):
    props={p['id'] for p in load('propositions')['proposicoes']}
    themes={c['id'] for c in load('categories')['categorias']}
    result={}
    for key,allowed in [('temas',themes),('proposicoes',props),('orgaos',{'Câmara dos Deputados','Senado Federal','ANPD','TSE','CNJ'})]:
        values=d.get(key,[])
        if not isinstance(values,list) or len(values)>200 or any(isinstance(v,bool) or not isinstance(v,(str,int)) or v not in allowed for v in values):raise Problem(400,'Filtros inválidos.')
        result[key]=list(dict.fromkeys(values))
    minimum=d.get('score_min',0)
    if isinstance(minimum,bool) or not isinstance(minimum,int) or not 0<=minimum<=100:raise Problem(400,'Score mínimo deve estar entre 0 e 100.')
    freq=d.get('frequencia','semanal')
    if freq not in FREQUENCIES:raise Problem(400,'Frequência inválida.')
    result.update({'score_min':minimum,'frequencia':freq})
    return result


def subscribe(s,d,user=None):
    if s is None:raise Problem(503,'Alertas indisponíveis no momento: o cadastro privado não está ativo. Registre um diagnóstico para receber acompanhamento por e-mail.')
    if d.get('website') or d.get('consent') is not True:raise Problem(400,'Confirme a solicitação de alertas.')
    if not notify.provider() and os.environ.get('MONITOR_DEV')!='1':raise Problem(503,'Os alertas ainda não estão disponíveis. Solicite um diagnóstico para definir seu acompanhamento.')
    address=email(d.get('email'))
    if user and address!=user['email']:raise Problem(400,'Use o endereço da sua conta.')
    prefs=preferences(d)
    key=secrets.token_hex(16);account=user['account_id'] if user else ''
    record={'email':address,**prefs,'active':False,'created_at':int(time.time()),'consent_at':int(time.time()),'account_id':account,'user_id':user['id'] if user else None}
    s.put('subscription',key,record,account)
    token=token_record(s,'confirm',key,{'subscription':key},account)
    site=os.environ.get('SITE_URL','https://monitor.lcfconsulting.com.br').rstrip('/')
    queue_now(s,'confirm-'+key,address,'Confirme seus alertas de regulação de IA',f'Você solicitou alertas do Monitor Legislativo de IA. Confirme em {site}/alertas/#confirm={token}\nO link expira em 7 dias. Se não solicitou, ignore. Nenhum alerta será enviado sem confirmação.',account)
    return {'ok':True,'message':'Solicitação registrada. Confirme o endereço pelo link que será enviado por e-mail.'}


def subscription_action(s,d,action):
    token=clean(d.get('token',''),128);key=digest(token)
    grant=s.get(action,key)
    if not grant or grant['expires']<time.time():raise Problem(400,'Link inválido ou expirado.')
    row=s.get('subscription',grant['subscription'])
    if not row:raise Problem(400,'Assinatura não encontrada.')
    if action=='confirm':
        for other_key,other in s.list('subscription',row.get('account_id','')):
            if other_key!=grant['subscription'] and other.get('email')==row['email'] and other.get('active'):
                other['active']=False;s.put('subscription',other_key,other,row.get('account_id',''))
    row['active']=action=='confirm';row['confirmed_at']=int(time.time()) if row['active'] else row.get('confirmed_at')
    s.put('subscription',grant['subscription'],row,row.get('account_id',''));s.delete(action,key)
    if action=='confirm':s.insert('event','alert-'+grant['subscription'],{'name':'alert_signup','timestamp':int(time.time()),'page':'/alertas/','cta':'confirm'})
    return {'ok':True,'message':'Alertas confirmados.' if row['active'] else 'Envio de alertas cancelado.'}


def password_hash(password,salt=None):
    password=clean(password,128)
    if len(password)<12:raise Problem(400,'A senha deve ter ao menos 12 caracteres.')
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()


def login(s,d):
    address=email(d.get('email'));password=clean(d.get('password',''),128)
    user=s.get('user',digest(address))
    stored=user['password_hash'] if user else '0'*32+':'+'0'*64
    salt=stored.split(':')[0]
    computed=salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    if not user or not hmac.compare_digest(stored,computed):raise Problem(401,'E-mail ou senha inválidos.')
    account=s.get('account',user['account_id'])
    check_account(account)
    token=token_record(s,'session','',{'user_id':user['id'],'account_id':user['account_id']},user['account_id'],days=1)
    s.insert('usage',secrets.token_hex(16),{'event':'login','user_id':user['id'],'timestamp':int(time.time())},user['account_id'])
    return token


def check_account(account):
    if not account or account['status']=='inactive' or (account.get('ends_on') and account['ends_on']<str(date.today())):raise Problem(403,'Acesso ao piloto indisponível ou encerrado. Solicite revisão do escopo.')


def authenticated(s,token):
    session=s.get('session',digest(token)) if token else None
    if not session or session['expires']<time.time():raise Problem(401,'Acesse sua conta para continuar.')
    user=s.get('user',session['user_id'])
    if not user or user['account_id']!=session['account_id']:raise Problem(401,'Sessão inválida.')
    account=s.get('account',user['account_id']);check_account(account)
    return user,account


def pilot(s,user,account):
    prefs=s.get('preferences',user['id']) or {'temas':account.get('themes',[]),'proposicoes':[],'orgaos':[],'frequencia':'semanal','score_min':60}
    model=briefing(themes=prefs['temas'],watchlist=prefs['proposicoes'],score_min=prefs['score_min'],organs=prefs['orgaos'])
    public_top=[{'id':p['id'],'title':f'{p["tipo"]} {p["numero"]}/{p["ano"]} — {p["titulo"]}','score':score(p),'fact':official_fact(p),'analysis':business_impact(p)} for p in model['top']]
    s.insert('usage',secrets.token_hex(16),{'event':'dashboard_view','user_id':user['id'],'timestamp':int(time.time())},user['account_id'])
    return {'account':{k:account.get(k) for k in ('name','status','ends_on','user_limit')},'email':user['email'],'preferences':prefs,'briefing':{**model,'top':public_top},'subscriptions':[{'id':key,**{k:v.get(k) for k in ('active','frequencia','score_min')}} for key,v in s.list('subscription',user['account_id']) if v.get('user_id')==user['id']]}
