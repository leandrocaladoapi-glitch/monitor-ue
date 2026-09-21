// Filtros client-side da lista de proposições
(function () {
  var rows = Array.prototype.slice.call(document.querySelectorAll('[data-prop]'));
  var controls = {
    q: document.getElementById('f-q'),
    casa: document.getElementById('f-casa'),
    ano: document.getElementById('f-ano'),
    status: document.getElementById('f-status'),
    cat: document.getElementById('f-cat'),
    score: document.getElementById('f-score')
  };
  if (!rows.length || !controls.q) return;
  var count = document.getElementById('count');

  function apply() {
    var q = controls.q.value.trim().toLowerCase();
    var casa = controls.casa ? controls.casa.value : '';
    var ano = controls.ano ? controls.ano.value : '';
    var status = controls.status ? controls.status.value : '';
    var cat = controls.cat ? controls.cat.value : '';
    var scoreValue = controls.score ? controls.score.value : '0';
    var score = parseInt(scoreValue, 10) || 0;
    var visible = 0;
    rows.forEach(function (r) {
      var d = r.dataset;
      var ok = true;
      if (q && (d.search.indexOf(q) === -1)) ok = false;
      if (casa && d.casa !== casa) ok = false;
      if (ano && d.ano !== ano) ok = false;
      if (status && d.statusgroup !== status) ok = false;
      if (cat && d.cats.indexOf(',' + cat + ',') === -1) ok = false;
      if (score && parseInt(d.score, 10) < score) ok = false;
      if (scoreValue === '60-79' && parseInt(d.score, 10) > 79) ok = false;
      if (scoreValue === 'low' && parseInt(d.score, 10) >= 60) ok = false;
      r.style.display = ok ? '' : 'none';
      if (ok) visible++;
    });
    if (count) count.textContent = visible + ' de ' + rows.length + ' proposições';
  }
  Object.keys(controls).forEach(function (k) {
    if (controls[k]) controls[k].addEventListener('input', apply);
    if (controls[k]) controls[k].addEventListener('change', apply);
  });
  apply();
})();

// Filtro por período da página de atualizações (preserva o filtro de proposições acima)
(function () {
  var items = Array.prototype.slice.call(document.querySelectorAll('[data-update]'));
  var btns = Array.prototype.slice.call(document.querySelectorAll('[data-ufilter]'));
  if (!items.length || !btns.length) return;
  var count = document.getElementById('u-count');
  function apply(limit) {
    var visible = 0;
    items.forEach(function (el) {
      var d = parseInt(el.getAttribute('data-days'), 10);
      var ok = (limit === 'all') || (!isNaN(d) && d <= parseInt(limit, 10));
      el.style.display = ok ? '' : 'none';
      if (ok) visible++;
    });
    if (count) count.textContent = visible + ' de ' + items.length + ' atualizações';
    btns.forEach(function (b) {
      if (b.getAttribute('data-ufilter') === String(limit)) b.classList.add('active');
      else b.classList.remove('active');
    });
  }
  btns.forEach(function (b) {
    b.addEventListener('click', function () { apply(b.getAttribute('data-ufilter')); });
  });
  apply('7');
})();

// Selo de frescor do monitoramento (presente em todas as páginas) e alertas do painel.
// Recalcula no navegador a idade da última execução: se o cron parar, o próprio
// site avisa o visitante mesmo sem rebuild.
(function () {
  function estadoHoras(h) {
    if (h === null) return 'atencao';
    if (h <= 30) return 'ok';
    if (h <= 54) return 'atencao';
    return 'critico';
  }
  function rel(h) {
    if (h === null) return 'idade desconhecida';
    if (h < 1) return 'há ' + Math.round(h * 60) + ' min';
    if (h < 48) return 'há ' + h.toFixed(h < 10 ? 1 : 0) + ' h';
    return 'há ' + Math.round(h / 24) + ' dias';
  }
  var badges = Array.prototype.slice.call(document.querySelectorAll('[data-freshness]'));
  badges.forEach(function (b) {
    var ts = Date.parse(b.getAttribute('data-freshness'));
    if (isNaN(ts)) return;
    var h = (Date.now() - ts) / 3600000;
    var estado = estadoHoras(h);
    b.setAttribute('data-estado', estado);
    var lbl = b.querySelector('[data-fresh-label]');
    if (lbl) {
      var base = lbl.textContent.replace(/^Última verificação:\s*/, '').split('·')[0].trim();
      lbl.textContent = 'Última verificação: ' + rel(h) +
        (estado === 'critico' ? ' · verifique o cron' : '');
      b.title = 'Última verificação registrada: ' + base + ' (' + rel(h) + ')';
    }
  });
  // Faixa de aviso no painel quando a execução está velha
  var painel = document.querySelector('[data-freshness-panel]');
  if (painel) {
    var ts2 = Date.parse(painel.getAttribute('data-freshness-panel'));
    if (!isNaN(ts2)) {
      var h2 = (Date.now() - ts2) / 3600000;
      if (h2 > 30) {
        var aviso = document.createElement('div');
        aviso.className = 'alert ' + (h2 > 54 ? 'critico' : 'atencao');
        aviso.innerHTML = '<b>Painel visto ' + rel(h2) + ' depois da última execução registrada.</b>' +
          '<span>O cron diário deve rodar às 07:17 (BRT). Verifique a aba Actions do repositório ' +
          'para saber se a coleta automática está falhando.</span>';
        painel.parentNode.insertBefore(aviso, painel);
      }
    }
  }
})();

