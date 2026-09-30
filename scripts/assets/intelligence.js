/* Camada executiva: filtros de eventos, janelas de prazos e cópia de alertas. */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Filtros do Regulatory Impact Engine
  var events = $$('[data-event]');
  if (events.length) {
    function apply() {
      var q = ($('#iq-search') || {}).value || '';
      var pri = ($('#iq-priority') || {}).value || '';
      var sector = ($('#iq-sector') || {}).value || '';
      var theme = ($('#iq-theme') || {}).value || '';
      var shown = 0;
      q = q.toLowerCase().trim();
      events.forEach(function (el) {
        var ok = true;
        if (q && (el.dataset.title || '').toLowerCase().indexOf(q) === -1) ok = false;
        if (pri && el.dataset.priority !== pri) ok = false;
        if (sector && (el.dataset.sectors || '').indexOf(sector) === -1) ok = false;
        if (theme && (el.dataset.themes || '').indexOf(theme) === -1) ok = false;
        el.style.display = ok ? '' : 'none';
        if (ok) shown++;
      });
      var count = $('#iq-count');
      if (count) count.textContent = shown + ' evento(s) exibido(s) de ' + events.length + '.';
    }
    ['#iq-search', '#iq-priority', '#iq-sector', '#iq-theme'].forEach(function (sel) {
      var el = $(sel);
      if (el) el.addEventListener('input', apply);
    });
  }

  // Janelas do deadline tracker
  var tabs = $$('[data-window-tab]');
  if (tabs.length) {
    function selectWindow(id) {
      tabs.forEach(function (tab) { tab.setAttribute('aria-selected', String(tab.dataset.windowTab === id)); });
      $$('[data-window]').forEach(function (block) {
        block.hidden = block.dataset.window !== id;
      });
    }
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () { selectWindow(tab.dataset.windowTab); });
    });
    selectWindow(tabs[0].dataset.windowTab);
  }

  // Cópia do alerta executivo
  $$('[data-copy-alert]').forEach(function (button) {
    button.addEventListener('click', function () {
      var box = document.getElementById(button.dataset.copyAlert);
      if (!box) return;
      var text = box.innerText;
      var done = function () { button.textContent = 'Alerta copiado'; };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, done);
      } else {
        var range = document.createRange();
        range.selectNodeContents(box);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        try { document.execCommand('copy'); } catch (e) { /* silencioso */ }
        done();
      }
    });
  });
}());
