import json
import re
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs'
SITE='https://monitor-ue.vercel.app'
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
        # Agora site exclusivo UE — valida docs raiz
        for file in OUT.rglob('*.html'):
            if 'uniao-europeia' in file.parts:
                continue
            html=file.read_text();m=Markup();m.feed(html)
            self.assertEqual(len(m.ids),len(set(m.ids)),str(file))
            self.assertIn('<meta name="description"',html,str(file));self.assertIn('<meta property="og:title"',html,str(file))
            self.assertIn('application/ld+json',html,str(file));self.assertIn('<link rel="canonical"',html,str(file))
            for link in m.links+m.assets:
                if link.startswith(SITE):link=link[len(SITE):]
                if not link.startswith('/') or link.startswith('//'):continue
                path=link.split('?',1)[0].split('#',1)[0]
                dest=OUT/path.lstrip('/')
                self.assertTrue(dest.exists() or (dest/'index.html').exists(),f'{file}: {link}')
            for ld in re.findall(r'<script type="application/ld\+json">(.*?)</script>',html,re.S):json.loads(ld)
    def test_sitemap_preserves_monitor_and_excludes_private_shells(self):
        root=ET.fromstring((OUT/'sitemap.xml').read_text());ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls=[e.text for e in root.findall('s:url/s:loc',ns)]
        self.assertEqual(len(urls),len(set(urls)))
        self.assertGreaterEqual(len(urls),12)
        for path in ['','procedimentos-legislativos/','atualizacoes/','legislacao-e-atos/','timeline/','atores-legislativos/','agenda/','monitoramento/','metodologia/','relatorio/']:
            self.assertIn(SITE+'/'+path,urls)
        self.assertNotIn(SITE+'/app/',urls);self.assertNotIn(SITE+'/login/',urls)
    def test_public_json_unchanged_private_data_not_published(self):
        for file in (ROOT/'data/legislation-eu').glob('*.json'):
            if file.name == 'atos.json' and not (OUT/'data'/file.name).exists():
                continue
            if (OUT/'data'/file.name).exists():
                self.assertEqual(json.loads(file.read_text()),json.loads((OUT/'data'/file.name).read_text()))
        for file in OUT.rglob('*'):
            if file.is_file():
                self.assertNotIn(file.suffix,{'.sqlite3','.env','.py'})
                self.assertNotIn(file.name,{'leads.json','accounts.json','subscriptions.json','briefing-full.json'})
    def test_commercial_asset_budget_and_no_fake_social_proof(self):
        for filename in ['style.css','site.js']:
            p=OUT/'assets'/filename
            if p.exists():
                self.assertLess(p.stat().st_size,50000)
        config=json.loads((ROOT/'config/commercial.json').read_text())
        self.assertFalse(config['social_proof']['enabled'])
        self.assertEqual(config['social_proof']['testimonials'],[])
    def test_workflow_publish_requires_green_build(self):
        text=(ROOT/'.github/workflows/update-ue.yml').read_text()
        self.assertIn("steps.build.outcome == 'success' && steps.validate.outcome == 'success'",text)
        self.assertIn("https://monitor-ue.vercel.app",(ROOT/'.github/workflows/commercial.yml').read_text())
