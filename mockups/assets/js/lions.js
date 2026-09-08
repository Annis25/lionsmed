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
        var t = reduit.matches ? 1 : Math.min((horodatage - debut) / duree, 1);
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

/* Interactions de présentation partagées. Aucun stockage de formulaire ni requête réseau. */
(function () {
  'use strict';
  document.querySelectorAll('form[data-maquette]').forEach(function(form) {
    var status = form.querySelector('[data-form-status]');
    if (!status) { status = document.createElement('p'); status.className = 'champ__aide'; status.setAttribute('role','status'); form.appendChild(status); }
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      status.textContent = 'Maquette uniquement : aucune donnée envoyée ni enregistrée.';
    });
  });
  document.querySelectorAll('.filter-bar').forEach(function(bar) {
    var root = bar.parentElement;
    var search = bar.querySelector('[data-search]');
    var filter = bar.querySelector('[data-filter]');
    var normal = function(t) { return t.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase(); };
    var update = function() {
      var count = 0;
      root.querySelectorAll('[data-item]').forEach(function(item) {
        var shown = item.dataset.roleRestricted !== 'true' && (!search.value || normal(item.textContent).includes(normal(search.value))) && (!filter.value || item.dataset.category === filter.value);
        item.hidden = !shown; if(shown) count++;
      });
      bar.querySelector('[data-count]').textContent = count + ' résultat' + (count === 1 ? '' : 's');
      var empty = root.querySelector('[data-empty]'); if(empty) empty.hidden = count !== 0;
    };
    search.addEventListener('input',update); filter.addEventListener('change',update); update();
  });
  document.querySelectorAll('[data-state-selector]').forEach(function(select) {
    var update = function() {
      document.querySelectorAll('[data-state-group="'+select.dataset.stateSelector+'"]').forEach(function(panel) { panel.hidden = panel.dataset.state !== select.value; });
    };
    select.addEventListener('change',update); update();
  });
  document.querySelectorAll('[data-dialog-open]').forEach(function(button) {
    var dialog = document.getElementById(button.dataset.dialogOpen);
    if(!dialog) return;
    button.addEventListener('click',function() {
      var selected = Array.from(document.querySelectorAll('input[name="bulletin"]:checked')); 
      var summary = dialog.querySelector('[data-vote-summary]');
      if(summary) summary.textContent = selected.length ? 'Choix de démonstration : '+selected.map(function(i){return i.closest('label').textContent.trim();}).join(', ') : 'Aucun choix sélectionné. Revenez au bulletin pour choisir.';
      dialog.showModal();
    });
    dialog.querySelectorAll('[data-dialog-close]').forEach(function(close) { close.addEventListener('click',function() {dialog.close();}); });
    dialog.addEventListener('close',function() {button.focus();});
  });
  document.querySelectorAll('[data-mark-read]').forEach(function(button) {
    button.addEventListener('click',function() {
      var row=button.closest('[data-notification]'); var read=!row.classList.contains('is-read');
      row.classList.toggle('is-read',read);
      row.querySelector('[data-read-state]').textContent=read?'Lue':'Non lue';
      button.textContent=read?'Marquer comme non lue':'Marquer comme lue';
    });
  });
  document.querySelectorAll('[data-photo-preview]').forEach(function(input) {
    var previous;
    input.addEventListener('change',function() {
      var image=input.closest('form').querySelector('[data-photo-image]');
      if(previous) URL.revokeObjectURL(previous);
      var file=input.files[0]; image.hidden=true;
      if(file && file.type.startsWith('image/')) {previous=URL.createObjectURL(file);image.src=previous;image.hidden=false;}
    });
  });
  /* Le menu mobile garde le focus dans ses contrôles ouverts. */
  var burger=document.querySelector('.nav-burger');
  if(burger) document.addEventListener('keydown',function(e) {
    if(e.key!=='Tab' || burger.getAttribute('aria-expanded')!=='true') return;
    var panel=document.getElementById(burger.getAttribute('aria-controls'));
    var list=[burger].concat(Array.from(panel.querySelectorAll('a,button')).filter(function(el){return el.getClientRects().length;}));
    var index=list.indexOf(document.activeElement);
    if(e.shiftKey && index<=0) {e.preventDefault();list[list.length-1].focus();}
    else if(!e.shiftKey && (index===list.length-1 || index<0)) {e.preventDefault();list[0].focus();}
  });
})();

/* Coquille privée : comportements partagés entre tous les écrans. */
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

/* Prévisualisation des permissions : aucune sécurité backend simulée. */
(function() {
  'use strict';
  var selector=document.querySelector('[data-role-selector]');
  if(!selector) return;
  var params=new URLSearchParams(location.search);
  var role=params.get('role') || 'MEMBRE';
  if(!Array.from(selector.options).some(function(o){return o.value===role;})) role='MEMBRE';
  selector.value=role;
  function update() {
    role=selector.value;
    document.querySelectorAll('[data-roles]').forEach(function(el){el.hidden=!el.dataset.roles.split(/\s+/).includes(role);});
    var page=document.querySelector('[data-page-permissions]');
    if(page) {
      var allowed=page.dataset.pagePermissions.split(/\s+/).includes(role);
      page.hidden=!allowed; document.querySelector('[data-access-denied]').hidden=allowed;
    }
    document.querySelectorAll('a[href]').forEach(function(link){
      var url=new URL(link.getAttribute('href'),location.href);
      if(url.origin===location.origin && url.pathname.includes('/espace/') && url.pathname.endsWith('.html')) {
        url.searchParams.set('role',role); link.setAttribute('href',url.pathname.split('/').pop()+url.search+url.hash);
      }
    });
    var url=new URL(location.href);url.searchParams.set('role',role);history.replaceState(null,'',url);
    // Invités : ne montrer que les exemples documentaires qui leur sont destinés.
    document.querySelectorAll('.tableau tr[data-item]').forEach(function(row) {
      if(location.pathname.endsWith('/documents.html')) row.dataset.roleRestricted=(role==='INVITE' && !row.textContent.includes('Invités autorisés'))?'true':'false';
    });
    var search=document.querySelector('[data-search]');if(search)search.dispatchEvent(new Event('input'));
    document.querySelectorAll('[data-current-role]').forEach(function(el){el.textContent=selector.selectedOptions[0].textContent;});
  }
  selector.addEventListener('change',update);update();
  var counter=document.querySelector('[data-counter-preview]');
  if(counter) counter.addEventListener('click',function(){
    document.querySelector('[data-live-counter]').textContent='Prévisualisation de mise à jour : 7 / 10 (70 %), aucune donnée réelle.';
    var numbers=document.querySelectorAll('.metrics .metric strong');numbers[1].textContent='7';numbers[2].textContent='70 %';
    var row=document.querySelectorAll('tbody tr')[6];row.lastElementChild.textContent='A voté';row.dataset.category='A voté';
    document.querySelector('[data-search]').dispatchEvent(new Event('input'));
    counter.disabled=true;
  });
  var voteType=document.querySelector('[data-vote-type]');
  if(voteType) {
    function typeUpdate(){document.querySelector('[data-candidate-fields]').hidden=voteType.value!=='election';document.getElementById('maximum-choix').disabled=voteType.value!=='multiple';}
    voteType.addEventListener('change',typeUpdate);typeUpdate();
  }
  var nav=document.querySelector('.app-nav'),button=document.querySelector('.app-bascule');
  document.addEventListener('keydown',function(e){
    if(e.key!=='Tab' || !nav.classList.contains('est-ouverte')) return;
    var links=Array.from(nav.querySelectorAll('a,button')).filter(function(a){return a.getClientRects().length;});
    links.unshift(button);var index=links.indexOf(document.activeElement);
    if(e.shiftKey && index<=0){e.preventDefault();links[links.length-1].focus();}
    else if(!e.shiftKey && (index===links.length-1 || index<0)){e.preventDefault();links[0].focus();}
  });
})();
(function(){
  var mode=document.querySelector('[data-ballot-type]');
  if(!mode)return;
  var inputs=Array.from(document.querySelectorAll('input[name="bulletin"]'));
  mode.addEventListener('change',function(){
    inputs.forEach(function(i){i.checked=false;i.type=mode.value==='multiple'?'checkbox':'radio';});
    document.querySelector('[data-election-preview]').hidden=mode.value!=='election';
    document.querySelector('[data-ballot-help]').textContent=mode.value==='multiple'?'Plusieurs choix possibles. Le vote blanc exclut les autres choix.':mode.value==='election'?'Choisissez un candidat ou un vote blanc. Les profils sont anonymes.':'Un seul choix autorisé dans cet exemple.';
  });
  inputs.forEach(function(input){input.addEventListener('change',function(){
    if(input.checked&&mode.value==='multiple')inputs.forEach(function(other){if(other!==input&&(input.value==='blanc'||other.value==='blanc'))other.checked=false;});
  });});
})();

(function(){
 var close=document.querySelector('.app-nav-fermer');
 if(close)close.addEventListener('click',function(){var button=document.querySelector('.app-bascule');button.click();button.focus();});
})();

(function(){var type=document.getElementById('contenu-type');if(!type)return;function update(){document.querySelectorAll('[data-editor-fields]').forEach(function(el){el.hidden=el.dataset.editorFields!==type.value;el.querySelectorAll('input,textarea').forEach(function(field){field.disabled=el.hidden;});});}type.addEventListener('change',update);update();})();
