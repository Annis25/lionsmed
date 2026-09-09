/* Comportements réels du shell issus des maquettes ; aucun rôle/état simulé. */
(function () {
  'use strict';
  document.documentElement.classList.add('js');
  document.querySelectorAll('[data-year], [data-annee]').forEach(function (el) { el.textContent = new Date().getFullYear(); });
  document.querySelectorAll('[data-oeil]').forEach(function (button) {
    button.addEventListener('click', function () {
      var input = document.getElementById(button.dataset.oeil);
      var visible = input.type === 'password';
      input.type = visible ? 'text' : 'password';
      button.setAttribute('aria-pressed', String(visible));
      button.setAttribute('aria-label', visible ? 'Masquer le mot de passe' : 'Afficher le mot de passe');
    });
  });
  var burger = document.querySelector('.nav-burger');
  var panel = document.querySelector('.nav-mobile');
  var toggle = document.querySelector('.app-bascule');
  var side = document.querySelector('.app-nav');
  var shell = document.querySelector('.app-shell');
  var veil = document.querySelector('.app-voile');
  var mobilePrivate = window.matchMedia('(max-width:760px)');
  function publicOpen(open) {
    if (!burger) return;
    panel.classList.toggle('is-open', open);
    burger.setAttribute('aria-expanded', String(open));
    burger.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
    document.body.classList.toggle('shell-menu-open', open);
  }
  function privateOpen(open) {
    if (!toggle) return;
    side.classList.toggle('est-ouverte', open);
    veil.classList.toggle('est-visible', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
    document.body.classList.toggle('shell-menu-open', open);
  }
  if (burger) burger.addEventListener('click', function () { publicOpen(burger.getAttribute('aria-expanded') !== 'true'); });
  if (toggle) {
    function adaptPrivate() {
      privateOpen(false);
      if (!mobilePrivate.matches) {
        toggle.setAttribute('aria-expanded', String(!shell.classList.contains('est-replie')));
        toggle.setAttribute('aria-label', shell.classList.contains('est-replie') ? 'Déplier le menu' : 'Replier le menu');
      }
    }
    adaptPrivate(); mobilePrivate.addEventListener('change', adaptPrivate);
    toggle.addEventListener('click', function () {
      if (mobilePrivate.matches) privateOpen(toggle.getAttribute('aria-expanded') !== 'true');
      else { shell.classList.toggle('est-replie'); adaptPrivate(); }
    });
    veil.addEventListener('click', function () { privateOpen(false); toggle.focus(); });
  }
  window.matchMedia('(max-width:1080px)').addEventListener('change', function () { publicOpen(false); });
  document.addEventListener('keydown', function (event) {
    var button, menu;
    if (burger && burger.getAttribute('aria-expanded') === 'true') { button = burger; menu = panel; }
    if (toggle && mobilePrivate.matches && toggle.getAttribute('aria-expanded') === 'true') { button = toggle; menu = side; }
    if (!button) return;
    if (event.key === 'Escape') { publicOpen(false); privateOpen(false); button.focus(); }
    if (event.key === 'Tab') {
      var items = [button].concat(Array.from(menu.querySelectorAll('a[href],button')).filter(function (el) { return el.getClientRects().length; }));
      var i = items.indexOf(document.activeElement);
      if (event.shiftKey && i <= 0) { event.preventDefault(); items[items.length - 1].focus(); }
      else if (!event.shiftKey && (i === items.length - 1 || i < 0)) { event.preventDefault(); items[0].focus(); }
    }
  });
  var errors = document.querySelector('.form-errors');
  if (errors) errors.focus();
})();
