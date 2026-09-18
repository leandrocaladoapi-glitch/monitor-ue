/* Commercial conversion and pilot UI. No form fields sent to analytics. */
(function () {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const all = (s, root = document) => Array.from(root.querySelectorAll(s));
  const safeRead = (store, key, fallback) => { try { return JSON.parse(store.getItem(key)) || fallback; } catch (_) { return fallback; } };
  const safeWrite = (store, key, data) => { try { store.setItem(key, JSON.stringify(data)); return true; } catch (_) { return false; } };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const path = location.pathname.replace(/\/$/, '') || '/';
  const query = new URLSearchParams(location.search);
  let attribution = safeRead(sessionStorage, 'monitor-attribution-v1', {});
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
    const value = query.get(key);
    if (value && value.length <= 160 && !/[@<>?\r\n]/.test(value)) attribution[key] = value;
  }
  attribution.source = attribution.utm_source || (document.referrer ? new URL(document.referrer).hostname : 'direct');
  attribution.campaign = attribution.utm_campaign || '';
  safeWrite(sessionStorage, 'monitor-attribution-v1', attribution);
  const context = (cta = '', sector = '') => ({...attribution, page: location.pathname, cta, sector, timestamp: new Date().toISOString()});
  async function api(route, data, method = 'POST') {
    const response = await fetch('/api/' + route, {method, credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, ...(method === 'GET' ? {} : {body: JSON.stringify(data)} )});
    let result;
    try { result = await response.json(); } catch (_) { throw new Error('O serviço de envio está indisponível. Seus dados não foram confirmados. Tente novamente mais tarde.'); }
    if (!response.ok) {
      const error = new Error(result.error || 'Não foi possível concluir a solicitação.');
      error.mailto = typeof result.mailto === 'string' && result.mailto.startsWith('mailto:') ? result.mailto : '';
      throw error;
    }
    return result;
  }
  function track(name, cta = '', sector = '') {
    const event = {name, ...context(cta, sector)};
    fetch('/api/events', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(event), keepalive: true}).catch(() => {});
    // Optional compatibility with an existing tag container; private API is the primary collector.
    if (typeof window.gtag === 'function') window.gtag('event', name, event);
  }
  all('a[href]').forEach(link => {
    const url = new URL(link.href, location.href);
    const sameSite = url.origin === location.origin || url.origin === 'https://monitor.lcfconsulting.com.br';
    if (sameSite && /^\/(diagnostico|solucoes|para-empresas|briefing-executivo|setores|casos-de-uso|alto-impacto|alertas)(\/|$)/.test(url.pathname)) {
      Object.keys(attribution).filter(k => k.startsWith('utm_')).forEach(k => { if (!url.searchParams.has(k)) url.searchParams.set(k, attribution[k]); });
      link.href = url.origin === location.origin ? url.pathname + url.search + url.hash : url.href;
    }
    link.addEventListener('click', () => {
      if (link.dataset.commercialCta) track('commercial_cta_click', link.dataset.commercialCta, link.dataset.sector || '');
      if (/^(https:\/\/)?(wa\.me|api\.whatsapp\.com)/.test(link.href)) track('whatsapp_click', 'whatsapp');
    });
  });
  const views = {'/solucoes':'pricing_view','/briefing-executivo':'briefing_sample_view','/alto-impacto':'high_impact_view'};
  if (views[path]) track(views[path], 'page_view');
  if (path.startsWith('/setores/')) track('sector_page_view', 'page_view', path.split('/').pop());
  all('[data-print]').forEach(button => button.addEventListener('click', () => window.print()));
  const form = $('#diagnostic-form');
  if (form) {
    for (const key of ['setor', 'interesse']) {
      if (query.has(key) && Array.from(form.elements[key].options).some(o => o.value === query.get(key))) form.elements[key].value = query.get(key);
    }
    let started = false;
    form.addEventListener('input', () => { if (!started) { track('diagnostic_started', 'form', form.elements.setor.value); started = true; } });
    let requestId = crypto.randomUUID();
    form.addEventListener('submit', async e => {
      e.preventDefault(); const button = $('button[type=submit]', form); const status = $('#diagnostic-status');
      button.disabled = true; status.textContent = 'Registrando solicitação…';
      const values = Object.fromEntries(new FormData(form));
      try {
        const result = await api('leads', {...values, consent: form.elements.consent.checked, request_id: requestId, attribution: context(values.interesse, values.setor)});
        status.textContent = result.message;
        form.reset(); requestId = crypto.randomUUID();
        // diagnostic_submitted/demo_request are recorded transactionally by the server.
      } catch (err) {
        status.textContent = err.message;
        // Nothing was confirmed by the server, so the visitor may still reach the inbox directly.
        if (err.mailto) {
          const link = document.createElement('a');
          link.href = err.mailto; link.rel = 'noopener'; link.textContent = 'Enviar por e-mail agora';
          status.append(' ', link);
        }
      } finally { button.disabled = false; }
    });
  }
  function readPreferences(form) {
    const f = new FormData(form);
    return {temas: f.getAll('temas').map(Number), proposicoes: f.getAll('proposicoes'), orgaos: f.getAll('orgaos'), score_min: Number(f.get('score_min')), frequencia: f.get('frequencia')};
  }
  function wireAlert(form) {
    form.addEventListener('submit', async e => {
      e.preventDefault(); const button = $('button', form); const status = $('[role=status]', form);button.disabled=true;
      try { status.textContent = (await api('alerts', {...readPreferences(form), email: form.elements.email.value, consent: form.elements.consent.checked, website: form.elements.website?.value || ''})).message; }
      catch (err) { status.textContent = err.message; } finally { button.disabled = false; }
    });
  }
  if ($('#alert-form')) wireAlert($('#alert-form'));
  const fragment = new URLSearchParams(location.hash.slice(1));
  for (const action of ['confirm','unsubscribe']) {
    if (fragment.has(action) && $('#subscription-action')) {
      const target = $('#subscription-action');const button = document.createElement('button');button.className='commercial-button';
      button.textContent = action === 'confirm' ? 'Confirmar recebimento de alertas' : 'Cancelar meus alertas';target.append(button);
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { target.textContent = (await api('alerts/' + action, {token: fragment.get(action)})).message;history.replaceState({}, '', location.pathname); }
        catch (err) { button.disabled=false;target.append(document.createTextNode(err.message)); }
      });
      target.scrollIntoView();
    }
  }
  const filter = $('#impact-filter');
  if (filter) {
    const apply = () => {
      let count=0;
      all('[data-impact-score]').forEach(card => {
        const n=Number(card.dataset.impactScore), val=filter.value;
        const show=val==='all'||(val==='80'&&n>=80)||(val==='60-79'&&n>=60&&n<=79)||(val==='low'&&n<60);
        card.hidden=!show;if(show)count++;
      });$('#impact-count').textContent = count + ' matérias neste recorte';
    };filter.addEventListener('change',apply);apply();
  }
  let watch = safeRead(localStorage, 'monitor-watchlist-v1', []);
  if (!Array.isArray(watch)) watch=[];
  const paintWatch = () => all('[data-watch-id]').forEach(button => {
    const saved = watch.includes(button.dataset.watchId);button.setAttribute('aria-pressed',String(saved));button.textContent=saved?'Remover da watchlist deste navegador':'Salvar na watchlist deste navegador';
  });
  all('[data-watch-id]').forEach(button => button.addEventListener('click', () => {
    const id=button.dataset.watchId;const next=watch.includes(id)?watch.filter(x=>x!==id):[...watch,id];
    if (safeWrite(localStorage,'monitor-watchlist-v1',next)) {watch=next;paintWatch();}
    else button.textContent='Armazenamento indisponível neste navegador';
  }));paintWatch();
  let propsCache;
  async function propositions() {
    if (!propsCache) propsCache=fetch('/data/propositions.json').then(r=>{if(!r.ok)throw new Error('Não foi possível carregar as matérias.');return r.json();}).then(d=>d.proposicoes);
    return propsCache;
  }
  if ($('#watchlist-items')) propositions().then(props => {
    const selected=props.filter(p=>watch.includes(p.id));
    $('#watchlist-items').innerHTML=selected.length?selected.map(p=>`<article class="commercial-card"><h2>${escape(p.tipo)} ${escape(p.numero)}/${escape(p.ano)}</h2><p>${escape(p.titulo)}</p><p>Score: ${escape(p.impacto.score)}</p><a href="${escape(p.url_oficial)}" rel="noopener">Fonte oficial</a></article>`).join(''):'<p>Nenhuma matéria salva. Abra <a href="/alto-impacto/">Alto impacto</a> e salve os itens relevantes.</p>';
  }).catch(err=>{$('#watchlist-items').textContent=err.message;});
  if ($('#watch-sync')) $('#watch-sync').addEventListener('click',async()=>{
    try {const me=await api('app',null,'GET');await api('preferences',{...me.preferences,proposicoes:watch});$('#watch-status').textContent='Watchlist sincronizada com sua conta.';}
    catch(err){$('#watch-status').textContent=err.message;}
  });
  if ($('#login-form')) $('#login-form').addEventListener('submit', async e => {
    e.preventDefault();const login=e.currentTarget, button=$('button',login);button.disabled=true;
    try {await api('login',Object.fromEntries(new FormData(login)));location.assign('/app/');}
    catch(err){$('#login-status').textContent=err.message;button.disabled=false;}
  });
  if ($('#logout')) $('#logout').addEventListener('click',async()=>{try{await api('logout',{});location.assign('/login/');}catch(err){$('#client-app').textContent=err.message;}});
  if ($('#client-app')) (async()=>{
    const target=$('#client-app');
    try {
      const me=await api('app',null,'GET');const props=await propositions();
      const categories=await fetch('/data/categories.json').then(r=>r.json());
      const prefs=me.preferences;
      const select=(name,label,options,selected)=>`<label>${label}<select name="${name}" multiple>${options.map(([id,title])=>`<option value="${escape(id)}" ${selected.includes(id)?'selected':''}>${escape(title)}</option>`).join('')}</select></label>`;
      const topics=select('temas','Temas monitorados',categories.categorias.map(c=>[c.id,c.nome]),prefs.temas);
      const watched=select('proposicoes','Watchlist',props.map(p=>[p.id,`${p.tipo} ${p.numero}/${p.ano}`]),prefs.proposicoes);
      const organs=select('orgaos','Órgãos',['Câmara dos Deputados','Senado Federal','ANPD','TSE','CNJ'].map(o=>[o,o]),prefs.orgaos);
      target.innerHTML=`<h2>${escape(me.account.name)}</h2><p>Status: ${escape(me.account.status)} · até ${escape(me.account.ends_on||'prazo contratual')} · limite de ${escape(me.account.user_limit)} usuários.</p><nav class="client-tabs"><a href="#client-brief">Briefing</a><a href="#client-settings">Temas e watchlist</a><a href="/alertas/">Alertas</a><a href="#client-agenda">Agenda</a></nav><section id="client-brief"><h2>Briefing do seu recorte</h2><p>${escape(me.briefing.since)} a ${escape(me.briefing.as_of)} · Coleta: ${escape(me.briefing.coverage)}; cobertura ${escape(me.briefing.coverage_pct)}%; erros ${escape(me.briefing.source_errors)}</p>${me.briefing.top.map(p=>`<article class="commercial-card"><h3>${escape(p.title)}</h3><p>Score ${escape(p.score)}/100</p><p class="eyebrow">FATO OFICIAL</p><p>${escape(p.fact.descricao)}</p><a href="${escape(p.fact.fonte)}">Fonte oficial</a><p class="eyebrow">ANÁLISE / INTERPRETAÇÃO</p><p>${escape(p.analysis.por_que_importa)}</p><p>${escape(p.analysis.status_da_interpretacao)}</p></article>`).join('')||'<p>Nenhuma matéria neste recorte.</p>'}<button class="watch-button" id="client-print">Imprimir relatório</button></section><section id="client-agenda"><h2>Agenda dos próximos 7 dias</h2>${me.briefing.events.map(e=>`<p>${escape(e.data_inicio)} — <a href="${escape(e.fonte_url)}">${escape(e.titulo)}</a></p>`).join('')||'<p>Nenhum evento identificado neste recorte.</p>'}</section><form id="client-settings" class="commercial-card"><h2>Configurações de acompanhamento</h2><div class="form-grid">${topics}${watched}${organs}<label>Score mínimo<input name="score_min" type="number" min="0" max="100" value="${escape(prefs.score_min)}"></label><label>Frequência<select name="frequencia">${[['imediato','Após detecção'],['diario','Diário'],['semanal','Semanal']].map(([v,t])=>`<option value="${v}" ${prefs.frequencia===v?'selected':''}>${t}</option>`).join('')}</select></label></div><button class="commercial-button">Salvar preferências</button><p role="status"></p></form><p>Para ativar ou alterar envio por e-mail, use <a href="/alertas/">Configurar alertas</a> e confirme seu endereço. Salvar preferências aqui atualiza o dashboard.</p><h2>Alertas solicitados</h2>${me.subscriptions.map(s=>`<p>${escape(s.frequencia)} · ${s.active?'Confirmado':'Aguardando confirmação'} · score mínimo ${escape(s.score_min)}</p>`).join('')||'<p>Nenhum alerta solicitado nesta conta.</p>'}<p>Relatórios: impressão do briefing disponível. Exportações em massa, API comercial, white-label e SLA exigem escopo adicional.</p>`;
      $('#client-print').addEventListener('click',()=>window.print());
      $('#client-settings').addEventListener('submit',async e=>{
        e.preventDefault();const f=e.currentTarget;
        try {await api('preferences',readPreferences(f));$('[role=status]',f).textContent='Preferências salvas. Recarregue para atualizar o briefing.';}
        catch(err){$('[role=status]',f).textContent=err.message;}
      });
    } catch(err) {target.innerHTML=`<p>${escape(err.message)}</p><a href="/login/">Acessar piloto</a>`;}
  })();
})();
