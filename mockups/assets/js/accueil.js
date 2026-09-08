/* ═══════════════════════════════════════════════════════════════════════════
   PAGE D'ACCUEIL — comportements spécifiques
   ═══════════════════════════════════════════════════════════════════════════
   Tout le reste (burger, sous-menu, révélation, compteurs, retour en haut)
   vit dans lions.js, partagé par l'ensemble des pages.

     1 · Repère d'emplacement d'image manquante
     2 · Séquence d'ouverture du hero
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ─── 1 · REPÈRE D'EMPLACEMENT ─────────────────────────────────────────── */
  /* Tant qu'un fichier image est absent, son conteneur affiche un repère
     technique (nom de fichier attendu, ratio, dimensions minimales) décrit
     dans lions.css. Dès que le fichier est déposé, l'image charge, aucune
     erreur n'est levée, la classe n'est jamais posée : le repère ne coûte
     alors strictement rien. Aucune modification de code au dépôt. */
  var marquerVide = function (img) {
    var conteneur = img.closest('.media');
    if (conteneur) conteneur.classList.add('media--vide');
  };

  /* Capture : attrape aussi les images différées, qui échoueront plus tard. */
  document.addEventListener('error', function (e) {
    if (e.target && e.target.tagName === 'IMG') marquerVide(e.target);
  }, true);

  /* Rattrapage : ce script est différé, certaines images ont pu échouer avant
     que l'écouteur ci-dessus ne soit posé. naturalWidth à 0 sur une image
     déclarée complète signale un chargement échoué. */
  var images = document.querySelectorAll('.media img');
  Array.prototype.forEach.call(images, function (img) {
    if (img.complete && img.naturalWidth === 0) marquerVide(img);
  });

  /* ─── 2 · SÉQUENCE D'OUVERTURE DU HERO ─────────────────────────────────── */
  /* Le seul moment orchestré de la page. Les décalages sont portés par
     --seq dans le HTML ; la neutralisation sous prefers-reduced-motion est
     entièrement gérée en CSS, pour rester vraie même si ce script échoue. */
  var hero = document.querySelector('.hero');
  if (hero) {
    requestAnimationFrame(function () { hero.classList.add('is-ready'); });
  }
})();
