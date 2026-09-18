"""Vercel Python function. Same-origin JSON API; no public data/PII export."""
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from commercial import notify,service as svc,store

# A misconfiguration must never look like a visitor error: unknown failures keep this neutral text,
# while the type is written to the function log and /api/health states exactly which piece is missing.
UNEXPECTED='Não foi possível concluir agora. Nenhum sucesso foi confirmado. Tente novamente mais tarde ou solicite atendimento pelo site da LCF Consulting.'


class handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass  # Request payloads, tokens, e-mail and query strings must not enter logs.
    def send_json(self,status,payload,cookie=None):
        data=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(data)))
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(data)
    def cookie(self,token,delete=False):
        secure='' if os.environ.get('MONITOR_DEV')=='1' and not os.environ.get('VERCEL') else '; Secure'
        return 'monitor_session='+token+'; Path=/; HttpOnly; SameSite=Lax; Max-Age='+('0' if delete else '86400')+secure
    def do_GET(self):self.dispatch('GET')
    def do_POST(self):self.dispatch('POST')
    def do_PUT(self):self.send_json(405,{'error':'Método não permitido.'})
    do_DELETE=do_PUT
    def status(self):
        """Configuration readiness for the operator. Booleans and names only, never values."""
        try:
            with store.connect_optional() as s:
                if s is None:database='not_configured'
                else:
                    s.execute('SELECT 1 FROM commercial_records LIMIT 1')
                    database='ok'
        except Exception:database='unreachable'
        try:targets=len(notify.recipients());transport=notify.provider()
        except notify.DeliveryError:targets=-1;transport=''
        return {'ok':database=='ok' or notify.ready(),'database':database,'database_expected':store.configured(),
                'email_provider':transport or None,'lead_recipients':max(targets,0),'recipients_invalid':targets<0,
                'lead_capture':database=='ok' or notify.ready(),
                # 'store' survives across requests; 'instance' only limits one warm function instance.
                'rate_limit':'store' if database=='ok' and os.environ.get('RATE_LIMIT_SECRET') else 'instance'}
    def dispatch(self,method):
        try:
            parsed=urlsplit(self.path)
            route=parsed.path.rstrip('/')
            # Rewrite supplies route; direct /api/index cannot select a private route via untrusted data.
            if route in ('/api/index','/api'):route='/api/'+parse_qs(parsed.query).get('route',[''])[0].strip('/')
            if route=='/api/health':
                if method!='GET':raise svc.Problem(405,'Método não permitido.')
                return self.send_json(200,self.status())
            data={}
            if method=='POST':
                site=os.environ.get('SITE_URL','https://monitor.lcfconsulting.com.br').rstrip('/')
                origins={site}
                if os.environ.get('VERCEL_URL'):origins.add('https://'+os.environ['VERCEL_URL'])
                if os.environ.get('MONITOR_DEV')=='1' and not os.environ.get('VERCEL'):origins.update({'http://127.0.0.1:8765','http://localhost:8765'})
                if self.headers.get('Origin') not in origins:raise svc.Problem(403,'Origem não autorizada.')
                if self.headers.get_content_type()!='application/json':raise svc.Problem(415,'Envie JSON.')
                try:length=int(self.headers.get('Content-Length','0'))
                except ValueError:raise svc.Problem(400,'Corpo inválido.')
                if not 0<length<=16384:raise svc.Problem(413,'Solicitação excede o limite permitido.')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise svc.Problem(400,'Corpo inválido.')
            cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
            token=cookie['monitor_session'].value if 'monitor_session' in cookie else ''
            result=None;new_cookie=None
            with ExitStack() as stack:
                # An unreachable database must not destroy a contact: capture degrades to direct notification.
                try:s=stack.enter_context(store.connect_optional())
                except Exception as exc:
                    if route!='/api/leads':raise
                    s=None;sys.stderr.write('api_store_unavailable '+type(exc).__name__+'\n')
                # Only Vercel's trusted forwarding header; local clients cannot choose rate keys.
                identity=self.headers.get('x-vercel-forwarded-for','unknown') if os.environ.get('VERCEL') else self.client_address[0]
                if method=='POST':svc.guard(s,identity,route,300 if route=='/api/events' else 20,strict=route=='/api/login')
                if route=='/api/leads' and method=='POST':result=svc.capture_lead(s,data)
                elif route=='/api/events' and method=='POST':
                    if s is None:raise svc.Problem(503,'Telemetria indisponível sem o banco privado.')
                    if data.get('name') not in svc.EVENTS or data['name'] in {'diagnostic_submitted','alert_signup','demo_request'}:raise svc.Problem(400,'Evento inválido.')
                    s.insert('event',svc.secrets.token_hex(16),{'name':data['name'],**svc.attribution(data)})
                    result={'ok':True}
                elif route=='/api/alerts' and method=='POST':
                    if s is None:raise svc.Problem(503,'Alertas indisponíveis enquanto o banco privado não estiver ativo. Use o formulário de diagnóstico.')
                    user=svc.authenticated(s,token)[0] if token else None
                    result=svc.subscribe(s,data,user)
                elif route in ('/api/alerts/confirm','/api/alerts/unsubscribe') and method=='POST':
                    if s is None:raise svc.Problem(503,'Confirmação indisponível. Solicite novamente pelo formulário de diagnóstico.')
                    result=svc.subscription_action(s,data,'confirm' if route.endswith('/confirm') else 'unsubscribe')
                elif route=='/api/login' and method=='POST':
                    if s is None:raise svc.Problem(503,'Área do piloto indisponível enquanto o banco privado não estiver ativo.')
                    new_cookie=self.cookie(svc.login(s,data));result={'ok':True}
                elif route=='/api/logout' and method=='POST':
                    if s is None:raise svc.Problem(503,'Sessão indisponível.')
                    s.delete('session',svc.digest(token));new_cookie=self.cookie('',True);result={'ok':True}
                elif route=='/api/app' and method=='GET':
                    if s is None:raise svc.Problem(503,'Área do piloto indisponível enquanto o banco privado não estiver ativo.')
                    user,account=svc.authenticated(s,token);result=svc.pilot(s,user,account)
                elif route=='/api/preferences' and method=='POST':
                    if s is None:raise svc.Problem(503,'Preferências indisponíveis enquanto o banco privado não estiver ativo.')
                    user,account=svc.authenticated(s,token);prefs=svc.preferences(data)
                    s.put('preferences',user['id'],prefs,user['account_id']);result={'ok':True,'preferences':prefs}
                else:raise svc.Problem(404,'Rota não encontrada.')
            self.send_json(200,result,new_cookie)
        except svc.Problem as exc:self.send_json(exc.status,{'error':str(exc),**exc.payload})
        except (ValueError,TypeError,json.JSONDecodeError):self.send_json(400,{'error':'Revise o formato dos campos.'})
        except ImportError:
            sys.stderr.write('api_error dependency_missing\n')
            self.send_json(503,{'error':'Dependências da função não instaladas no deploy (psycopg ausente em requirements.txt).'})
        except Exception as exc:
            sys.stderr.write('api_error '+type(exc).__name__+'\n')
            self.send_json(503,{'error':UNEXPECTED})
