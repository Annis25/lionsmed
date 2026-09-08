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

  /* ─── 1 · SÉQUENCE D'OUVERTURE DU HERO ─────────────────────────────────── */
  /* Le seul moment orchestré de la page. Les décalages sont portés par
     data-seq dans le HTML ; la neutralisation sous prefers-reduced-motion est
     entièrement gérée en CSS, pour rester vraie même si ce script échoue. */
  var hero = document.querySelector('.hero');
  if (hero) {
    requestAnimationFrame(function () { hero.classList.add('is-ready'); });
  }
})();
