"""Direct operator notification for captured leads: HTTPS mail APIs first, SMTP as alternate transport.

Transport selection is configuration-driven (no provider is assumed):
  RESEND_API_KEY (+ optional RESEND_FROM)  -> Resend HTTP API, works on Vercel (port 443)
  FORMSUBMIT_KEY                            -> FormSubmit relay, no domain or DNS setup
  SMTP_HOST (+ PORT/USER/PASSWORD/SMTP_FROM) -> SMTP submission, STARTTLS on 587 or TLS on 465
LEAD_EMAIL_PROVIDER forces one of them. LEAD_NOTIFY_EMAIL lists the operator inboxes.
Every failure here is a DeliveryError: the lead itself is never lost because of it.
"""
import json
import os
import re
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage

TIMEOUT=12
TRANSPORTS=('resend','formsubmit','smtp')
ADDRESS=re.compile(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+')


class DeliveryError(Exception):
    """Transport rejected or could not reach the mail service; safe to retry later."""


def recipients():
    """Operator addresses from LEAD_NOTIFY_EMAIL. Invalid entries fail loudly, not silently."""
    raw=os.environ.get('LEAD_NOTIFY_EMAIL','')
    parts=[part.strip().lower() for part in re.split(r'[,;\s]+',raw) if part.strip()]
    if [part for part in parts if not ADDRESS.fullmatch(part)]:
        raise DeliveryError('LEAD_NOTIFY_EMAIL contém endereço inválido.')
    return list(dict.fromkeys(parts))


def provider():
    """Configured transport name, or '' when none is available."""
    forced=os.environ.get('LEAD_EMAIL_PROVIDER','').strip().lower()
    for name in ([forced] if forced else list(TRANSPORTS)):
        if name=='resend' and os.environ.get('RESEND_API_KEY'):return name
        if name=='formsubmit' and os.environ.get('FORMSUBMIT_KEY'):return name
        if name=='smtp' and os.environ.get('SMTP_HOST'):return name
    return ''


def ready():
    """True when a submission can reach an operator inbox right now."""
    try:return bool(provider() and recipients())
    except DeliveryError:return False


def _post(url,payload,headers=None):
    request=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json',**(headers or {})},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=TIMEOUT) as response:body=response.read()
    except urllib.error.HTTPError as exc:
        detail=exc.read()[:200].decode('utf-8','replace') if exc.fp else ''
        raise DeliveryError(f'{url.split("/")[2]}_rejected_{exc.code}: {detail[:120]}')
    except Exception:raise DeliveryError(f'{url.split("/")[2]}_unreachable')
    try:return json.loads(body or b'{}')
    except ValueError:return {}


def resend(to,subject,text,reply_to):
    payload={'from':os.environ.get('RESEND_FROM','LCF Consulting <onboarding@resend.dev>'),'to':to,'subject':subject,'text':text}
    if reply_to:payload['reply_to']=reply_to
    result=_post(os.environ.get('RESEND_API_URL','https://api.resend.com/emails'),payload,{'Authorization':'Bearer '+os.environ['RESEND_API_KEY']})
    if result.get('name') and not result.get('id'):raise DeliveryError('resend_rejected: '+str(result['name'])[:120])


def formsubmit(to,subject,text,reply_to):
    payload={'name':'Monitor Legislativo de IA','email':reply_to,'message':text,'_subject':subject,'_captcha':'false','_template':'table','_replyto':reply_to}
    result=_post(os.environ.get('FORMSUBMIT_URL','https://formsubmit.co/ajax/send/')+os.environ['FORMSUBMIT_KEY'],payload)
    if str(result.get('success','true')).lower()!='true':raise DeliveryError('formsubmit_rejected: '+str(result.get('message'))[:120])


def smtp_send(message):
    """Authenticated submission. STARTTLS below 465, implicit TLS on 465. Port 25 is never used."""
    host=os.environ['SMTP_HOST'];port=int(os.environ.get('SMTP_PORT','587'))
    client=smtplib.SMTP_SSL if port==465 else smtplib.SMTP
    with client(host,port,timeout=TIMEOUT) as smtp:
        if port!=465:
            smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo()
        if os.environ.get('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.environ.get('SMTP_PASSWORD',''))
        smtp.send_message(message)


def smtp(to,subject,text,reply_to):
    sender=os.environ.get('SMTP_FROM') or os.environ.get('SMTP_USER')
    if not sender:raise DeliveryError('Defina SMTP_FROM (ou SMTP_USER) para enviar como remetente autorizado.')
    message=EmailMessage()
    message['From']=sender
    message['To']=', '.join(to)
    message['Subject']=subject
    if reply_to:message['Reply-To']=reply_to
    message.set_content(text)
    smtp_send(message)


def send(subject,text,to=None,reply_to=''):
    """Deliver one message through the configured transport. Returns the transport name."""
    targets=to if to is not None else recipients()
    if isinstance(targets,str):targets=[targets]
    targets=[address for address in (item.strip() for item in targets) if ADDRESS.fullmatch(address)]
    if not targets:raise DeliveryError('Nenhum destinatário válido em LEAD_NOTIFY_EMAIL.')
    name=provider()
    if not name:raise DeliveryError('Nenhum transporte de e-mail está configurado.')
    reply=reply_to.strip() if isinstance(reply_to,str) and ADDRESS.fullmatch(reply_to.strip()) else ''
    # CRLF no corpo viraria quebra de cabeçalho em transportes textuais; o corpo normaliza antes de sair.
    body=str(text).replace('\r\n','\n').replace('\r','\n')
    if name=='resend':resend(targets,_safe(subject),body,reply)
    elif name=='formsubmit':formsubmit(targets,_safe(subject),body,reply)
    else:smtp(targets,_safe(subject),body,reply)
    return name


def _safe(value):
    """Headers cannot carry line breaks."""
    return ' '.join(str(value).replace('\r',' ').replace('\n',' ').split())[:180]


def lead_text(lead,key='',persisted=None):
    """Readable operator digest; the raw record stays in the private store."""
    labels=[('Nome','nome'),('Empresa','empresa'),('Cargo','cargo'),('E-mail','email'),('Telefone','telefone'),('Setor','setor'),('Porte (pessoas)','tamanho'),('Uso de IA','uso_ia'),('Área de controle','area_controle'),('Urgência','urgencia'),('Interesse','interesse')]
    when=datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')
    lines=['MONITOR LEGISLATIVO DE IA — NOVO CONTATO RECEBIDO PELO SITE',f'Recebido em {when}','Dados pessoais: uso restrito à equipe LCF Consulting.','']
    for label,field in labels:
        value=lead.get(field)
        if value not in (None,''):lines.append(f'{label}: {value}')
    if lead.get('preocupacao'):lines+=['','Preocupação declarada:',lead['preocupacao']]
    lines+=['','QUALIFICAÇÃO AUTOMÁTICA (triagem comercial; não é avaliação jurídica)',f"Score: {lead.get('score','—')}/100 — {lead.get('classificacao','—')}"]
    factors=lead.get('fatores') or {}
    if factors:lines.append('Fatores: '+', '.join(f'{k} +{v}' for k,v in factors.items() if v))
    attribution=lead.get('attribution') or {}
    origin=', '.join(f'{k}={attribution[k]}' for k in ('page','source','cta','utm_source','utm_medium','utm_campaign') if attribution.get(k))
    if origin:lines+=['','Origem: '+origin]
    if key:lines+=['','Identificador da solicitação: '+str(key)]
    if persisted is not None:lines.append('Registrado no banco privado: '+('sim' if persisted else 'não (banco indisponível; este e-mail é o único registro)'))
    return '\n'.join(lines)


def notify_lead(lead,key='',persisted=None):
    """Best-effort immediate delivery. Never raises: the capture itself must succeed."""
    try:
        to=recipients()
        if not to:return {'notified':False,'retryable':False,'reason':'LEAD_NOTIFY_EMAIL não configurado.'}
        subject=f"Novo contato — {lead.get('empresa') or lead.get('nome') or 'Monitor Legislativo'} — score {lead.get('score','—')}"
        name=send(subject,lead_text(lead,key,persisted),to,lead.get('email',''))
        return {'notified':True,'provider':name,'recipients':len(to)}
    except DeliveryError as exc:return {'notified':False,'retryable':True,'reason':str(exc)}
    except Exception as exc:return {'notified':False,'retryable':True,'reason':type(exc).__name__}


def mailto(lead):
    """Emergency path so a contact is never lost while the backend is misconfigured."""
    try:to=recipients()
    except DeliveryError:return ''
    if not to:return ''
    company=lead.get('empresa') or lead.get('nome') or 'Monitor Legislativo'
    body=lead_text(lead)+'\n\n---\nConteúdo preenchido no formulário. Envie esta mensagem para registrar a solicitação por e-mail.'
    # Clientes de e-mail truncam URLs muito longas: o corpo cabe no orçamento restante, na ordem do mais importante.
    link='mailto:'+to[0]+'?subject='+urllib.parse.quote(_safe(f'Novo contato pelo site — {company}'))+'&body='
    return link+urllib.parse.quote(body)[:max(0,1800-len(link))]