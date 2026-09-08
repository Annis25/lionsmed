/* ═══════════════════════════════════════════════════════════════════════════
   ESPACE PRIVÉ — comportements de la coquille
   ═══════════════════════════════════════════════════════════════════════════
   Tout le reste (menu déroulant du compte, révélation, retour en haut, année
   courante, blocage des formulaires de maquette) vit dans lions.js, chargé
   avant celui-ci. Rien n'est dupliqué.

   AUCUNE logique d'authentification, d'autorisation, de vote, de satisfaction
   ni de paiement. Ce fichier ne fait que trois choses d'interface.

     1 · Barre latérale : repli au large, tiroir au mobile
     2 · Jauges : largeur de barre calculée depuis aria-valuenow
     3 · Date du jour
     4 · Tri de tableau
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var shell = document.querySelector('.app-shell');
  if (!shell) return;

  var nav      = shell.querySelector('.app-nav');
  var bascule  = document.querySelector('.app-bascule');
  var voile    = document.querySelector('.app-voile');
  var tiroir   = window.matchMedia('(max-width: 760px)');
  var moyen    = window.matchMedia('(max-width: 1080px)');

  /* ─── 1 · BARRE LATÉRALE ───────────────────────────────────────────────── */
  /* Un seul bouton, deux comportements selon la largeur : au-dessus de 760 px
     il replie la barre en rail ; en dessous, il ouvre et ferme un tiroir. */
  var majBouton = function () {
    if (!bascule) return;
    var ouvert = tiroir.matches ? nav.classList.contains('est-ouverte')
                                : !shell.classList.contains('est-replie');
    bascule.setAttribute('aria-expanded', String(ouvert));
    bascule.setAttribute('aria-label', ouvert ? 'Replier le menu' : 'Déplier le menu');
  };

  var fermerTiroir = function () {
    nav.classList.remove('est-ouverte');
    if (voile) voile.classList.remove('est-visible');
    document.body.style.overflow = '';
    majBouton();
  };

  var basculer = function () {
    if (tiroir.matches) {
      var ouvrir = !nav.classList.contains('est-ouverte');
      nav.classList.toggle('est-ouverte', ouvrir);
      if (voile) voile.classList.toggle('est-visible', ouvrir);
      document.body.style.overflow = ouvrir ? 'hidden' : '';
    } else {
      shell.classList.toggle('est-replie');
    }
    majBouton();
  };

  if (bascule) bascule.addEventListener('click', basculer);
  if (voile)   voile.addEventListener('click', fermerTiroir);

  /* Suivre un lien referme le tiroir */
  nav.addEventListener('click', function (e) {
    if (tiroir.matches && e.target.closest('a')) fermerTiroir();
  });

  /* Échap referme le tiroir et rend le focus au bouton */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && nav.classList.contains('est-ouverte')) {
      fermerTiroir();
      if (bascule) bascule.focus();
    }
  });

  /* État initial : replié d'office entre 761 et 1080 px, déplié au-delà.
     Repasser à une largeur donnée remet la barre dans son état par défaut. */
  var appliquerDefaut = function () {
    if (tiroir.matches) {
      shell.classList.remove('est-replie');
      fermerTiroir();
    } else {
      fermerTiroir();
      shell.classList.toggle('est-replie', moyen.matches);
    }
    majBouton();
  };
  appliquerDefaut();
  [tiroir, moyen].forEach(function (mq) {
    if (mq.addEventListener) mq.addEventListener('change', appliquerDefaut);
    else if (mq.addListener) mq.addListener(appliquerDefaut);
  });

  /* ─── 2 · JAUGES ───────────────────────────────────────────────────────── */
  /* La valeur chiffrée est déjà écrite dans le HTML : la barre ne fait que la
     représenter. Sans ce script, l'information reste lisible. */
  var jauges = document.querySelectorAll('.jauge__piste[role="progressbar"]');
  Array.prototype.forEach.call(jauges, function (piste) {
    var v   = parseFloat(piste.getAttribute('aria-valuenow'));
    var min = parseFloat(piste.getAttribute('aria-valuemin')) || 0;
    var max = parseFloat(piste.getAttribute('aria-valuemax'));
    var barre = piste.querySelector('.jauge__barre');
    if (!barre || isNaN(v) || isNaN(max) || max === min) return;
    var pct = Math.max(0, Math.min(100, ((v - min) / (max - min)) * 100));
    barre.style.width = pct + '%';
  });

  /* ─── 3 · DATE DU JOUR ─────────────────────────────────────────────────── */
  /* Écrite par le navigateur plutôt que fixée en dur : une date de maquette
     périmée se lit comme une donnée fausse. Le HTML porte un repli. */
  var dates = document.querySelectorAll('[data-date-longue]');
  Array.prototype.forEach.call(dates, function (el) {
    try {
      var d = new Date();
      el.textContent = d.toLocaleDateString('fr-FR', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
      });
      el.setAttribute('datetime', d.toISOString().slice(0, 10));
    } catch (e) { /* le repli du HTML reste affiché */ }
  });

  /* ─── 4 · TRI DE TABLEAU ───────────────────────────────────────────────── */
  /* Tri côté client, au clavier comme à la souris. aria-sort porte l'état.
     Le type de comparaison vient de data-tri sur la colonne. */
  var boutons = document.querySelectorAll('.tableau__tri');
  Array.prototype.forEach.call(boutons, function (bouton) {
    bouton.addEventListener('click', function () {
      var th      = bouton.closest('th');
      var tableau = bouton.closest('table');
      if (!th || !tableau) return;
      var corps = tableau.tBodies[0];
      if (!corps) return;

      var index = Array.prototype.indexOf.call(th.parentNode.children, th);
      var sens  = th.getAttribute('aria-sort') === 'ascending' ? -1 : 1;

      Array.prototype.forEach.call(tableau.querySelectorAll('th[aria-sort]'), function (autre) {
        autre.setAttribute('aria-sort', 'none');
      });
      th.setAttribute('aria-sort', sens === 1 ? 'ascending' : 'descending');

      var numerique = th.getAttribute('data-tri') === 'nombre';
      var lignes = Array.prototype.slice.call(corps.rows);
      lignes.sort(function (a, b) {
        var x = (a.cells[index] && a.cells[index].textContent || '').trim();
        var y = (b.cells[index] && b.cells[index].textContent || '').trim();
        if (numerique) return (parseFloat(x) - parseFloat(y)) * sens;
        return x.localeCompare(y, 'fr') * sens;
      });
      lignes.forEach(function (l) { corps.appendChild(l); });
    });
  });

})();
