/* ═══════════════════════════════════════════════════════════════════════════
   LIONS CLUB SFAX-MÉDITERRANÉE — comportements partagés
   ═══════════════════════════════════════════════════════════════════════════
   Amélioration progressive : la page est complète et navigable sans ce fichier.
   Chaque module se contente d'un retour anticipé si son point d'ancrage est
   absent — la feuille sert des pages de structures différentes.

     1 · Menu burger            5 · Retour en haut
     2 · Sous-menu déroulant    6 · Année courante
     3 · Révélation au scroll   7 · Formulaires de maquette
     4 · Compteurs animés       8 · Afficher / masquer un mot de passe
                                9 · Repère d'emplacement d'image manquante
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* Marque le document : les états initiaux masqués de .reveal ne s'appliquent
     que si JavaScript est là pour les révéler ensuite. */
  document.documentElement.classList.add('js');

  var reduit = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* ─── 1 · MENU BURGER ──────────────────────────────────────────────────── */
  var burger = document.querySelector('.nav-burger');
  var panneau = burger && document.getElementById(burger.getAttribute('aria-controls'));

  if (burger && panneau) {
    var basculer = function (ouvrir) {
      burger.setAttribute('aria-expanded', String(ouvrir));
      burger.setAttribute('aria-label', ouvrir ? 'Fermer le menu' : 'Ouvrir le menu');
      panneau.classList.toggle('is-open', ouvrir);
      document.body.style.overflow = ouvrir ? 'hidden' : '';
    };

    burger.addEventListener('click', function () {
      basculer(burger.getAttribute('aria-expanded') !== 'true');
    });

    /* Échap referme et rend le focus au bouton */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && burger.getAttribute('aria-expanded') === 'true') {
        basculer(false);
        burger.focus();
      }
    });

    /* Suivre un lien referme le panneau */
    panneau.addEventListener('click', function (e) {
      if (e.target.closest('a')) basculer(false);
    });

    /* Repasser en affichage large remet tout à plat */
    var large = window.matchMedia('(min-width: 1081px)');
    var surChangement = function () { if (large.matches) basculer(false); };
    if (large.addEventListener) large.addEventListener('change', surChangement);
    else if (large.addListener) large.addListener(surChangement);
  }

  /* ─── 2 · SOUS-MENU DÉROULANT ──────────────────────────────────────────── */
  var bascules = document.querySelectorAll('.nav-toggle[aria-controls]');
  Array.prototype.forEach.call(bascules, function (bouton) {
    var menu = document.getElementById(bouton.getAttribute('aria-controls'));
    if (!menu) return;

    var fermer = function () {
      bouton.setAttribute('aria-expanded', 'false');
      menu.classList.remove('is-open');
    };

    bouton.addEventListener('click', function () {
      var ouvert = bouton.getAttribute('aria-expanded') === 'true';
      bouton.setAttribute('aria-expanded', String(!ouvert));
      menu.classList.toggle('is-open', !ouvert);
    });

    document.addEventListener('click', function (e) {
      if (!menu.contains(e.target) && !bouton.contains(e.target)) fermer();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && bouton.getAttribute('aria-expanded') === 'true') {
        fermer();
        bouton.focus();
      }
    });
    /* Le focus quitte l'ensemble : on referme */
    var conteneur = bouton.closest('.nav-item') || bouton.parentNode;
    conteneur.addEventListener('focusout', function (e) {
      if (e.relatedTarget && !conteneur.contains(e.relatedTarget)) fermer();
    });
  });

  /* ─── 3 · RÉVÉLATION AU SCROLL ─────────────────────────────────────────── */
  /* Grands blocs uniquement. Opacité + 16 px, puis unobserve. */
  var aReveler = document.querySelectorAll('.reveal');

  if (!aReveler.length) {
    /* rien à faire */
  } else if (!('IntersectionObserver' in window) || reduit.matches) {
    /* Sans observateur, ou si l'utilisateur refuse les animations :
       état final immédiat, jamais de contenu bloqué invisible. */
    Array.prototype.forEach.call(aReveler, function (el) { el.classList.add('is-visible'); });
  } else {
    var observateur = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (entree) {
        if (!entree.isIntersecting) return;
        entree.target.classList.add('is-visible');
        observateur.unobserve(entree.target);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

    Array.prototype.forEach.call(aReveler, function (el) { observateur.observe(el); });
  }

  /* ─── 4 · COMPTEURS ANIMÉS ─────────────────────────────────────────────── */
  /* La valeur définitive est déjà écrite dans le HTML : sans JavaScript, ou
     avec les animations réduites, le chiffre juste est là. L'animation ne fait
     que rejouer la montée depuis zéro. */
  var compteurs = document.querySelectorAll('[data-compteur]');

  if (compteurs.length && 'IntersectionObserver' in window && !reduit.matches) {
    var animer = function (el) {
      var cible = parseInt(el.getAttribute('data-compteur'), 10);
      if (isNaN(cible)) return;
      var duree = 1400;
      var debut = null;

      var etape = function (horodatage) {
        if (debut === null) debut = horodatage;
        var t = Math.min((horodatage - debut) / duree, 1);
        var adouci = 1 - Math.pow(1 - t, 3);          /* easeOutCubic */
        el.textContent = String(Math.round(cible * adouci));
        if (t < 1) requestAnimationFrame(etape);
        else el.textContent = String(cible);
      };
      requestAnimationFrame(etape);
    };

    var obsCompteurs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (entree) {
        if (!entree.isIntersecting) return;
        obsCompteurs.unobserve(entree.target);
        animer(entree.target);
      });
    }, { threshold: 0.5 });

    Array.prototype.forEach.call(compteurs, function (el) { obsCompteurs.observe(el); });
  }

  /* ─── 5 · RETOUR EN HAUT ───────────────────────────────────────────────── */
  var haut = document.querySelector('.to-top');
  if (haut) {
    var synchroniser = function () {
      haut.classList.toggle('is-visible', window.scrollY > 600);
    };
    synchroniser();
    window.addEventListener('scroll', synchroniser, { passive: true });
    haut.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: reduit.matches ? 'auto' : 'smooth' });
    });
  }

  /* ─── 6 · ANNÉE COURANTE ───────────────────────────────────────────────── */
  var annees = document.querySelectorAll('[data-annee]');
  Array.prototype.forEach.call(annees, function (el) {
    el.textContent = String(new Date().getFullYear());
  });

  /* ─── 7 · FORMULAIRES DE MAQUETTE ──────────────────────────────────────── */
  /* Aucun formulaire de la maquette ne soumet quoi que ce soit. Le blocage est
     posé ici plutôt que page par page, et ne concerne que les formulaires qui
     se déclarent explicitement comme maquettes. */
  var maquettes = document.querySelectorAll('form[data-maquette]');
  Array.prototype.forEach.call(maquettes, function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      console.info('Maquette : soumission bloquee. Ce formulaire sera branche a l\'integration Django.');
    });
  });

  /* ─── 8 · AFFICHER / MASQUER UN MOT DE PASSE ───────────────────────────── */
  /* Le bouton porte son état dans aria-pressed et change de libellé : l'état
     n'est jamais transmis par la seule icône. */
  var yeux = document.querySelectorAll('[data-oeil]');
  Array.prototype.forEach.call(yeux, function (bouton) {
    var champ = document.getElementById(bouton.getAttribute('data-oeil'));
    if (!champ) return;
    bouton.addEventListener('click', function () {
      var visible = champ.type === 'text';
      champ.type = visible ? 'password' : 'text';
      bouton.setAttribute('aria-pressed', String(!visible));
      bouton.setAttribute('aria-label', visible ? 'Afficher le mot de passe' : 'Masquer le mot de passe');
    });
  });

  /* ─── 9 · REPÈRE D'EMPLACEMENT D'IMAGE MANQUANTE ───────────────────────── */
  /* Tant qu'un fichier image est absent, son conteneur affiche un repère
     technique (nom de fichier attendu, ratio, dimensions minimales) décrit
     dans lions.css. Dès que le fichier est déposé, l'image charge, aucune
     erreur n'est levée, la classe n'est jamais posée : le repère ne coûte
     alors strictement rien. Aucune modification de code au dépôt.
     Partagé : toute page portant des .media en a besoin. */
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
  var imagesMedia = document.querySelectorAll('.media img');
  Array.prototype.forEach.call(imagesMedia, function (img) {
    if (img.complete && img.naturalWidth === 0) marquerVide(img);
  });

})();
