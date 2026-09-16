/* Pages /espace/documents/ et /espace/documents/gestion/ : recherche texte côté client
   sur la page actuellement affichée (catégorie/visibilité/tri restent gérés par le
   serveur, déjà paginés). Sans JS, toutes les cartes/lignes restent visibles. */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    var search = document.querySelector('[data-doc-search]');
    if (!search) return;
    var cards = Array.prototype.slice.call(document.querySelectorAll('[data-doc-card]'));
    var empty = document.querySelector('[data-doc-empty]');

    function apply() {
      var query = search.value.trim().toLowerCase();
      var visible = 0;
      cards.forEach(function (card) {
        var show = !query || card.dataset.docTitle.indexOf(query) !== -1;
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (empty) empty.hidden = visible !== 0;
    }

    search.addEventListener('input', apply);
  });
}());
