const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright' : 'playwright');
const fs=require('fs');
const pathUtil=require('path');
fs.mkdirSync('reports/screenshots',{recursive:true});
(async()=>{
 let step='inicialização';
 const mark=label=>{step=label;console.log('[browser-smoke] '+label);};
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 mark('chromium iniciado');
 const results=[],errors=[];
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
 await ctx.route('https://monitor.lcfconsulting.com.br/**',async route=>{
   const u=new URL(route.request().url());
   const root=pathUtil.resolve('docs');
   let file=pathUtil.resolve(root,'.'+decodeURIComponent(u.pathname));
   if(!file.startsWith(root+pathUtil.sep)&&file!==root)throw Error('Invalid local asset path');
   if(fs.existsSync(file)&&fs.statSync(file).isDirectory())file=pathUtil.join(file,'index.html');
   if(!fs.existsSync(file))throw Error('Missing canonical asset '+u.pathname);
   const types={'.css':'text/css','.js':'application/javascript','.json':'application/json','.html':'text/html','.svg':'image/svg+xml'};
   await route.fulfill({status:200,contentType:types[pathUtil.extname(file)]||'application/octet-stream',body:fs.readFileSync(file)});
 });
 const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
 mark('desktop: layout e navegação');
 for(const path of ['/','/solucoes/','/diagnostico/','/briefing-executivo/','/alto-impacto/','/setores/fintech/','/casos-de-uso/compliance/','/alertas/','/login/']){
   mark('desktop '+path);
   const response=await page.goto('http://127.0.0.1:8765'+path);await page.locator('h1').waitFor({state:'visible'});await page.evaluate(()=>document.fonts.ready);
   if(response.status()!==200)throw Error(path+' HTTP '+response.status());
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
   if(overflow)throw Error(path+' desktop overflow');
   results.push({path,viewport:'desktop',status:200,overflow});
   if(path==='/solucoes/')await page.screenshot({path:'reports/screenshots/solucoes-desktop.png',fullPage:true});
 }
 mark('diagnóstico: envio com UTM');
 await page.goto('http://127.0.0.1:8765/diagnostico/?utm_source=linkedin&utm_campaign=piloto-fintech&setor=Fintech');
 await page.locator('[name=nome]').fill('Pessoa de Teste');await page.locator('[name=empresa]').fill('Empresa de Teste');await page.locator('[name=cargo]').fill('Head de Dados');await page.locator('[name=email]').fill('browser@example.test');
 await page.locator('[name=tamanho]').selectOption('501+');await page.locator('[name=uso_ia]').selectOption('critico');await page.locator('[name=area_controle]').selectOption('sim');await page.locator('[name=urgencia]').selectOption('imediata');await page.locator('[name=preocupacao]').fill('Processos de crédito');await page.locator('[name=interesse]').selectOption('demo');await page.locator('[name=consent]').check();
 await page.locator('#diagnostic-form button').click();await page.waitForFunction(()=>document.querySelector('#diagnostic-status').textContent.includes('Solicitação registrada'));
 results.push({test:'diagnostic submit with UTM',passed:true});
 mark('alto-impacto: filtros de score');
 await page.goto('http://127.0.0.1:8765/alto-impacto/');
 for(const value of ['80','60-79','low']){
   await page.locator('#impact-filter').selectOption(value);
   const visible=await page.locator('[data-impact-score]:visible').evaluateAll(nodes=>nodes.map(n=>+n.dataset.impactScore));
   if(!visible.length||visible.some(n=>value==='80'?n<80:value==='60-79'?(n<60||n>79):n>=60))throw Error('score filter '+value);
 }
 await page.locator('#impact-filter').selectOption('80');await page.locator('[data-watch-id]:visible').first().click();

 mark('watchlist: item salvo no navegador');
 await page.goto('http://127.0.0.1:8765/watchlist/');await page.waitForSelector('#watchlist-items article');results.push({test:'filters and persistent watchlist',passed:true});
 mark('diagnóstico: indisponibilidade 503');
 await page.goto('http://127.0.0.1:8765/diagnostico/');
 await page.route('**/api/leads',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Serviço indisponível em teste'})}));
 for(const [k,v] of Object.entries({nome:'Teste',empresa:'Empresa',cargo:'Head',email:'failure@example.test',preocupacao:'Teste falha'}))await page.locator(`[name=${k}]`).fill(v);
 for(const [k,v] of Object.entries({setor:'Bancos',tamanho:'501+',uso_ia:'critico',area_controle:'sim',urgencia:'imediata',interesse:'diagnostico'}))await page.locator(`[name=${k}]`).selectOption(v);
 await page.locator('[name=consent]').check();await page.locator('#diagnostic-form button').click();await page.waitForFunction(()=>document.querySelector('#diagnostic-status').textContent.includes('indisponível'));
 if(await page.locator('[name=email]').inputValue()!=='failure@example.test')throw Error('Failure lost form values');
 results.push({test:'503 preserves input, never displays success',passed:true});
 await page.unroute('**/api/leads');
 mark('mobile: layout 390x844');
 await page.setViewportSize({width:390,height:844});
 for(const path of ['/','/solucoes/','/diagnostico/','/briefing-executivo/','/alto-impacto/','/setores/fintech/','/alertas/']){
   mark('mobile '+path);
   await page.goto('http://127.0.0.1:8765'+path);await page.locator('h1').waitFor({state:'visible'});await page.evaluate(()=>document.fonts.ready);
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(path+' mobile overflow');
   results.push({path,viewport:'390x844',overflow:false});
   if(path==='/diagnostico/')await page.screenshot({path:'reports/screenshots/diagnostico-mobile.png',fullPage:true});
   if(path==='/briefing-executivo/')await page.screenshot({path:'reports/screenshots/briefing-mobile.png',fullPage:true});
 }
 mark('erros de console acumulados: '+errors.length);
 if(errors.length)throw Error('Browser errors: '+errors.join(';'));
 fs.writeFileSync('reports/browser-results.json',JSON.stringify({results,consoleErrors:errors},null,2));
 console.log(JSON.stringify({checks:results.length,consoleErrors:errors.length}));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
