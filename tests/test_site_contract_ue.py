import json
import re
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/uniao-europeia';PREFIX='/uniao-europeia'
SITE='https://monitor.lcfconsulting.com.br'
class Markup(HTMLParser):
    def __init__(self):super().__init__();self.links=[];self.ids=[];self.assets=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if tag=='a' and 'href'in a:self.links.append(a['href'])
        if tag in {'script','img','link'}:
            value=a.get('src') or (a.get('href') if a.get('rel')=='stylesheet' else None)
            if value:self.assets.append(value)
class SiteTests(unittest.TestCase):
    def test_metadata_assets_internal_links_and_unique_ids(self):
        for file in OUT.rglob('*.html'):
            html=file.read_text();m=Markup();m.feed(html)
            self.assertEqual(len(m.ids),len(set(m.ids)),str(file))
            self.assertIn('<meta name="description"',html,str(file));self.assertIn('<meta property="og:title"',html,str(file))
            self.assertIn('application/ld+json',html,str(file));self.assertIn('<link rel="canonical"',html,str(file))
            for link in m.links+m.assets:
                if link.startswith(SITE):link=link[len(SITE):]
                if not link.startswith('/') or link.startswith('//'):continue
                path=link.split('?',1)[0].split('#',1)[0]
                base_site=OUT if path.startswith(PREFIX) else ROOT/'docs'
                if path.startswith(PREFIX):path=path[len(PREFIX):]
                dest=base_site/path.lstrip('/')
                self.assertTrue(dest.exists() or (dest/'index.html').exists(),f'{file}: {link}')
            for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>',html,re.S):json.loads(ld)
    def test_sitemap_preserves_monitor_and_excludes_private_shells(self):
        root=ET.fromstring((OUT/'sitemap.xml').read_text());ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls=[e.text for e in root.findall('s:url/s:loc',ns)]
        self.assertEqual(len(urls),len(set(urls)))
        # 1 home + 2 fichas de procedimento + 9 seções do monitor
        self.assertGreaterEqual(len(urls),12)
        for path in ['','procedimentos-legislativos/','atualizacoes/','legislacao-e-atos/','timeline/','atores-legislativos/','agenda/','monitoramento/','metodologia/','relatorio/']:
            self.assertIn(SITE+PREFIX+'/'+path,urls)
        self.assertNotIn(SITE+PREFIX+'/app/',urls);self.assertNotIn(SITE+PREFIX+'/login/',urls)
        # Sem rotas do monitor brasileiro dentro da seção UE
        for antiga in ['proposicoes/','leis/','parlamentares/']:
            self.assertNotIn(SITE+PREFIX+'/'+antiga,urls)
        # ...e o monitor BR permanece na raiz (seção adicional, não substituta)
        br_urls=ET.fromstring((ROOT/'docs/sitemap.xml').read_text())
        br_loc=[e.text for e in br_urls.findall('s:url/s:loc',ns)]
        self.assertIn(SITE+'/proposicoes/',br_loc)
        self.assertNotIn(SITE+PREFIX+'/procedimentos-legislativos/',br_loc)
        self.assertGreaterEqual(len(list((OUT/'procedimentos-legislativos').glob('*/index.html'))),2)
    def test_public_json_unchanged_private_data_not_published(self):
        for file in (ROOT/'data/legislation-eu').glob('*.json'):
            self.assertEqual(json.loads(file.read_text()),json.loads((OUT/'data'/file.name).read_text()))
        for file in OUT.rglob('*'):
            if file.is_file():
                self.assertNotIn(file.suffix,{'.sqlite3','.env','.py'})
                self.assertNotIn(file.name,{'leads.json','accounts.json','subscriptions.json','briefing-full.json'})
    def test_commercial_asset_budget_and_no_fake_social_proof(self):
        for filename in ['style.css','site.js']:
            self.assertLess((OUT/'assets'/filename).stat().st_size,30000)
        config=json.loads((ROOT/'config/commercial.json').read_text())
        self.assertFalse(config['social_proof']['enabled'])
        self.assertEqual(config['social_proof']['testimonials'],[])
        self.assertNotIn('10.000–20.000',(ROOT/'docs/solucoes/index.html').read_text())
    def test_workflow_publish_requires_green_build(self):
        text=(ROOT/'.github/workflows/update-legislation.yml').read_text()
        self.assertIn("steps.build.outcome == 'success' && steps.validate.outcome == 'success'",text)
        self.assertIn("vars.COMMERCIAL_ENABLED == 'true'",(ROOT/'.github/workflows/commercial.yml').read_text())
    def test_br_legado_fora_do_dataset_publicado(self):
        """Nada de lixo brasileiro no dataset novo (missão: base só UE)."""
        for name in ['propositions.json','atos.json','laws.json','parliamentarians.json','events.json','timeline.json']:
            bruto=(ROOT/'data/legislation-eu'/name).read_text(encoding='utf-8')
            self.assertNotIn('anpd',bruto.lower());self.assertNotIn('planalto.gov.br',bruto.lower())
            self.assertNotIn('camara.leg.br',bruto.lower());self.assertNotIn('senado.leg.br',bruto.lower())
