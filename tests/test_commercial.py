import contextlib
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import unquote
from unittest.mock import patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from commercial.store import connect,migrate
from commercial import service as s,alerts,notify
from commercial.intelligence import briefing,official
from commercial_admin import provision
from api.index import handler

LEAD={'nome':'Pessoa Teste','empresa':'Organização Exemplo','cargo':'Diretora de Dados','email':'test@example.test','telefone':'','setor':'Bancos','tamanho':'501+','uso_ia':'critico','area_controle':'sim','urgencia':'imediata','preocupacao':'Processo de crédito automatizado','interesse':'diagnostico','consent':True,'request_id':'12345678-1234-1234-1234-123456789012','attribution':{'utm_campaign':'piloto','page':'/diagnostico/','email':'do-not-collect@example.test'}}
PREFS={'temas':[],'proposicoes':[],'orgaos':[],'score_min':0,'frequencia':'imediato'}

class CommercialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'MONITOR_DEV':'1','COMMERCIAL_SQLITE':self.tmp.name+'/test.sqlite3','RATE_LIMIT_SECRET':'test-secret'},clear=False);self.env.start()
        self.no_prod=patch.dict(os.environ,{'DATABASE_URL':'','VERCEL':''});self.no_prod.start();migrate()
    def tearDown(self):self.no_prod.stop();self.env.stop();self.tmp.cleanup()
    def test_scoring_thresholds_and_zero(self):
        self.assertEqual(s.lead_score(LEAD)['score'],100)
        self.assertEqual(s.lead_score({})['classificacao'],'baixo')
        for d,total,band in [({'setor':'Bancos','uso_ia':'critico'},30,'médio'),({'setor':'Bancos','cargo':'Head','area_controle':'sim'},50,'alto'),({'setor':'Cloud','tamanho':'501+','cargo':'Sócio','uso_ia':'critico'},70,'prioridade comercial')]:
            self.assertEqual((s.lead_score(d)['score'],s.lead_score(d)['classificacao']),(total,band))
    def test_lead_durable_idempotent_and_no_pii_in_event(self):
        with connect() as db:s.capture_lead(db,LEAD);s.capture_lead(db,LEAD)
        with connect() as db:
            self.assertEqual(len(db.list('lead')),1);self.assertEqual(db.list('lead')[0][1]['score'],100)
            event=db.list('event')[0][1];self.assertNotIn('email',event);self.assertEqual(event['utm_campaign'],'piloto')
            with self.assertRaises(s.Problem):s.capture_lead(db,{**LEAD,'empresa':'Other'})
    def test_invalid_leads_do_not_persist(self):
        for d in [{**LEAD,'consent':False},{**LEAD,'email':'bad'},{**LEAD,'website':'spam'},{**LEAD,'setor':'Unknown'}]:
            with connect() as db:
                with self.assertRaises(s.Problem):s.capture_lead(db,d)
                self.assertEqual(db.list('lead'),[])
    def test_optin_expiry_and_replacement(self):
        with connect() as db:
            s.subscribe(db,{**PREFS,'email':'a@example.test','consent':True})
            key,sub=db.list('subscription')[0];self.assertFalse(sub['active'])
            token=db.list('outbox')[0][1]['text'].split('#confirm=')[1].split('\n')[0]
            s.subscription_action(db,{'token':token},'confirm');self.assertTrue(db.get('subscription',key)['active'])
            with self.assertRaises(s.Problem):s.subscription_action(db,{'token':token},'confirm')
            expired=s.token_record(db,'confirm','',{'subscription':key},days=-1)
            with self.assertRaises(s.Problem):s.subscription_action(db,{'token':expired},'confirm')
    def test_pilot_user_limit_isolation_expiry_logout(self):
        with connect() as db:
            provision(db,'a','A','pilot','2099-01-01',1,[3],'a@example.test','long-password-A')
            provision(db,'b','B','active',None,2,[29],'b@example.test','long-password-B')
            with self.assertRaises(ValueError):provision(db,'a','A','pilot','2099-01-01',1,[],'c@example.test','long-password-C')
            token=s.login(db,{'email':'a@example.test','password':'long-password-A'})
            user,account=s.authenticated(db,token)
            result=s.pilot(db,user,account);self.assertEqual(result['account']['name'],'A');self.assertNotIn('password_hash',json.dumps(result))
            db.put('preferences',user['id'],{**PREFS,'score_min':80},'a')
            self.assertTrue(all(p['score']>=80 for p in s.pilot(db,user,account)['briefing']['top']))
            a=db.get('account','a');a['ends_on']='2000-01-01';db.put('account','a',a,'a')
            with self.assertRaises(s.Problem):s.authenticated(db,token)
    def test_rate_limit_survives_failed_request(self):
        with connect() as db:s.rate_limit(db,'ip','login',1)
        with connect() as db:
            with self.assertRaises(s.Problem):s.rate_limit(db,'ip','login',1)
    def test_serverless_never_uses_sqlite(self):
        with patch.dict(os.environ,{'VERCEL':'1','DATABASE_URL':''}):
            with self.assertRaises(RuntimeError):
                with connect():pass
    def test_alert_baseline_diff_dedupe_filter(self):
        record={'id':'p','entity':'proposition','title':'P','source':'https://www.camara.leg.br/test','themes':[3],'org':'Câmara dos Deputados','score':70,'movement':{'despacho':'Original'},'votes':1,'rapporteur':None,'status':'Aguardando'}
        with connect() as db:
            alerts.capture(db,{'p':record},100);self.assertEqual(db.list('alert_change'),[])
            updated={**record,'score':80,'rapporteur':'Novo','votes':2,'movement':{'despacho':'Inclusão em pauta'}}
            alerts.capture(db,{'p':updated},200);alerts.capture(db,{'p':updated},201)
            self.assertEqual(len(db.list('alert_change')),1)
            sub={**PREFS,'email':'a@example.test','active':True,'created_at':1,'confirmed_at':1,'account_id':''}
            db.put('subscription','sub',sub);alerts.prepare(db,300);alerts.prepare(db,301)
            self.assertEqual(len(db.list('outbox')),1)
            change=db.list('alert_change')[0][1]
            self.assertIn('votação',change['types']);self.assertIn('inclusão em pauta',change['types'])
            self.assertFalse(alerts.matches({**sub,'score_min':90},change))
            self.assertFalse(alerts.matches({**sub,'temas':[29]},change))
            self.assertFalse(alerts.matches({**sub,'orgaos':['ANPD']},change))
    def test_daily_weekly_and_unscored_norms(self):
        sub={**PREFS,'email':'a@example.test','active':True,'created_at':1,'confirmed_at':1}
        change={'detected_at':100,'record':{'id':'x','themes':[3],'org':'ANPD','score':None}}
        self.assertTrue(alerts.matches(sub,change));self.assertFalse(alerts.matches({**sub,'score_min':1},change))
        with connect() as db:
            db.put('subscription','weekly',{**sub,'frequencia':'semanal'});db.put('alert_change','c',{**change,'types':['nova norma'],'record':{**change['record'],'title':'Norma','source':'https://www.gov.br/anpd'}})
            alerts.prepare(db,604799);self.assertEqual(db.list('outbox'),[])
            alerts.prepare(db,604802);self.assertEqual(len(db.list('outbox')),1)
    def test_smtp_retry_and_idempotent_delivery(self):
        with connect() as db:s.queue(db,'mail','a@example.test','Subject','Body')
        def fail(*a):raise OSError('temporary')
        self.assertEqual(alerts.deliver(connect,fail),0)
        with connect() as db:
            mail=db.get('outbox','mail');self.assertEqual(mail['status'],'retry');mail['next_attempt']=0;db.put('outbox','mail',mail)
        sent=[];self.assertEqual(alerts.deliver(connect,lambda m,k:sent.append(k)),1);self.assertEqual(alerts.deliver(connect,lambda m,k:sent.append(k)),0)
        self.assertEqual(sent,['mail'])
    def test_cancelled_subscription_prevents_queued_send(self):
        with connect() as db:
            db.put('subscription','s',{'active':False});s.queue(db,'m','a@example.test','Subject','Body');m=db.get('outbox','m');m['subscription_id']='s';db.put('outbox','m',m)
        self.assertEqual(alerts.deliver(connect,lambda *x:self.fail('must not send')),0)
    def test_official_sources_and_report_dates(self):
        self.assertFalse(official('https://camara.leg.br.evil.example/x'))
        b=briefing(as_of='2026-09-12',sector='fintech')
        self.assertTrue(all(official(c['fonte_url']) for c in b['changes']))
        self.assertTrue(all('2026-09-12'<=e['data_inicio'][:10]<='2026-09-19' for e in b['events']))
    def test_http_origin_validation_and_failure_semantics(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(route,data=None,origin='https://monitor.lcfconsulting.com.br',method='POST'):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            conn.request(method,route,json.dumps(data) if data is not None else None,{'Origin':origin,'Content-Type':'application/json'})
            response=conn.getresponse();result=(response.status,json.loads(response.read()));conn.close();return result
        try:
            self.assertEqual(request('/api/leads',LEAD,origin='https://evil.example')[0],403)
            self.assertEqual(request('/api/leads',LEAD)[0],200)
            self.assertEqual(request('/api/app',method='GET')[0],401)
            self.assertEqual(request('/api/events',{'name':'diagnostic_submitted'})[0],400)
            with patch.dict(os.environ,{'VERCEL':'1'}):self.assertEqual(request('/api/leads',LEAD)[0],503)
        finally:server.shutdown();server.server_close()

    def test_mailto_fallback_when_transport_fails(self):
        env={'DATABASE_URL':'','VERCEL':'1','LEAD_NOTIFY_EMAIL':'operador@example.test'}
        with patch.dict(os.environ,env,clear=False):
            with self.assertRaises(s.Problem) as caught:s.capture_lead(None,{**LEAD,'request_id':'aaaaaaaa-1111-1111-1111-111111111111'})
        self.assertEqual(caught.exception.status,503)
        self.assertIn('mailto:operador@example.test',caught.exception.payload.get('mailto',''))
        self.assertIn('Pessoa Teste',unquote(caught.exception.payload['mailto']))

    def test_no_store_no_email_reports_unavailable(self):
        with patch.dict(os.environ,{'DATABASE_URL':'','VERCEL':'1','LEAD_NOTIFY_EMAIL':''},clear=False):
            with self.assertRaises(s.Problem) as caught:s.capture_lead(None,{**LEAD,'request_id':'dddddddd-4444-4444-4444-444444444444'})
        self.assertEqual(caught.exception.status,503)
        self.assertIn('indisponível',str(caught.exception).lower())

    def test_direct_email_without_database_and_once_only(self):
        sent=[]
        env={'DATABASE_URL':'','VERCEL':'1','LEAD_NOTIFY_EMAIL':'operador@example.test','RESEND_API_KEY':'re_test','RESEND_FROM':'Monitor <leads@example.test>'}
        request={**LEAD,'request_id':'bbbbbbbb-2222-2222-2222-222222222222'}
        with patch.dict(os.environ,env,clear=False),patch('commercial.notify.resend',side_effect=lambda to,subject,text,reply_to:sent.append((to,subject,reply_to,text))):
            result=s.capture_lead(None,request)
            self.assertTrue(result['notified']);self.assertFalse(result['persisted'])
            repeated=s.capture_lead(None,request)
        self.assertEqual(len(sent),1)
        self.assertEqual(repeated['message'],s.REPLY_REGISTERED)
        to,subject,reply_to,text=sent[0]
        self.assertEqual(to,['operador@example.test']);self.assertEqual(reply_to,'test@example.test')
        self.assertIn('Novo contato — Organização Exemplo — score 100',subject)
        for fragment in ('Pessoa Teste','501+','piloto','100/100'):self.assertIn(fragment,text)
        self.assertNotIn('consent_version',text)

    def test_transport_failure_keeps_durable_lead_and_retries_by_queue(self):
        env={'LEAD_NOTIFY_EMAIL':'operador@example.test','RESEND_API_KEY':'re_test'}
        with patch.dict(os.environ,env,clear=False),patch('commercial.notify.send',side_effect=notify.DeliveryError('resend_unreachable')):
            with connect() as db:result=s.capture_lead(db,{**LEAD,'request_id':'cccccccc-3333-3333-3333-333333333333'})
        self.assertTrue(result['persisted']);self.assertFalse(result['notified'])
        self.assertIn('fila',result['message'])
        with connect() as db:
            mail=db.get('outbox','lead-cccccccc-3333-3333-3333-333333333333')
            self.assertEqual(mail['status'],'pending');self.assertIn('Pessoa Teste',mail['text'])
            self.assertIn('score 100',mail['subject'])

    def test_local_rate_limit_is_single_instance_but_enforced(self):
        for _ in range(20):s.local_rate_limit('203.0.113.7','/api/leads')
        with self.assertRaises(s.Problem) as caught:s.local_rate_limit('203.0.113.7','/api/leads')
        self.assertEqual(caught.exception.status,429)

    def test_health_reports_missing_configuration(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            conn.request('GET','/api/health')
            response=conn.getresponse();status,payload=response.status,json.loads(response.read());conn.close()
        finally:server.shutdown();server.server_close()
        self.assertEqual(status,200)
        self.assertIn(payload['email_provider'],[None,'resend','formsubmit','smtp'])
        for key in ('database','lead_capture','rate_limit','lead_recipients'):self.assertIn(key,payload)
        self.assertNotIn('RESEND',json.dumps(payload))
        self.assertNotIn('test-secret',json.dumps(payload))


if __name__=='__main__':unittest.main()
