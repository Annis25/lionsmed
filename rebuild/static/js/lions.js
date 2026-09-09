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
  var reveals = document.querySelectorAll('.reveal');
  var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (reveals.length) {
    if (!('IntersectionObserver' in window) || reducedMotion.matches) {
      reveals.forEach(function (element) { element.classList.add('is-visible'); });
    } else {
      var revealObserver = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
      reveals.forEach(function (element) { revealObserver.observe(element); });
    }
  }
  var errors = document.querySelector('.form-errors');
  if (errors) errors.focus();

  document.querySelectorAll('[data-action-gallery]').forEach(function (gallery) {
    var main = gallery.querySelector('[data-gallery-main]');
    var frame = gallery.querySelector('.action-lightbox__frame');
    var photos = Array.from(gallery.querySelectorAll('[data-gallery-open]'));
    var dialog = gallery.querySelector('[data-action-lightbox]');
    if (!main || !photos.length || !dialog) return;
    var index = 0;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    function apply(position) {
      index = (position + photos.length) % photos.length;
      var photo = photos[index];
      main.src = photo.dataset.large;
      main.width = photo.dataset.width;
      main.height = photo.dataset.height;
      main.alt = photo.dataset.alt;
      gallery.querySelector('[data-gallery-count]').textContent = (index + 1) + ' / ' + photos.length;
    }
    function show(position) {
      if (!frame || reduceMotion) { apply(position); return; }
      frame.classList.add('is-changing');
      window.setTimeout(function () {
        apply(position);
        window.requestAnimationFrame(function () { frame.classList.remove('is-changing'); });
      }, 140);
    }
    photos.forEach(function (photo, position) { photo.addEventListener('click', function () { apply(position); dialog.showModal(); }); });
    var previous = gallery.querySelector('[data-gallery-previous]');
    var next = gallery.querySelector('[data-gallery-next]');
    if (previous) previous.addEventListener('click', function () { show(index - 1); });
    if (next) next.addEventListener('click', function () { show(index + 1); });
    gallery.querySelector('[data-gallery-close]').addEventListener('click', function () { dialog.close(); });
    dialog.addEventListener('click', function (event) { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowLeft') { event.preventDefault(); show(index - 1); }
      if (event.key === 'ArrowRight') { event.preventDefault(); show(index + 1); }
    });
    if (frame && photos.length > 1) {
      var touchStartX = null;
      frame.addEventListener('touchstart', function (event) { touchStartX = event.changedTouches[0].clientX; }, { passive: true });
      frame.addEventListener('touchend', function (event) {
        if (touchStartX === null) return;
        var delta = event.changedTouches[0].clientX - touchStartX;
        touchStartX = null;
        if (Math.abs(delta) < 40) return;
        show(delta > 0 ? index - 1 : index + 1);
      }, { passive: true });
    }
  });
})();
