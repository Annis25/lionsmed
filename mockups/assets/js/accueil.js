/* ═══════════════════════════════════════════════════════════════════════════
   PAGE D'ACCUEIL — comportements spécifiques
   ═══════════════════════════════════════════════════════════════════════════
   Tout le reste (burger, sous-menu, révélation, compteurs, retour en haut,
   formulaires de maquette, repère d'emplacement d'image) vit dans lions.js,
   partagé par l'ensemble des pages.

     1 · Séquence d'ouverture du hero
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* La bannière de développement reste visible par défaut. Les captures
     finales peuvent la masquer sans modifier le HTML avec ?capture=final. */
  if (new URLSearchParams(window.location.search).get('capture') === 'final') {
    document.documentElement.classList.add('capture-finale');
  }

  /* ─── 1 · SÉQUENCE D'OUVERTURE DU HERO ─────────────────────────────────── */
  /* Le seul moment orchestré de la page. Les décalages sont portés par
     data-seq dans le HTML ; la neutralisation sous prefers-reduced-motion est
     entièrement gérée en CSS, pour rester vraie même si ce script échoue. */
  var hero = document.querySelector('.hero');
  if (hero) {
    hero.classList.add('is-ready');
  }
})();
