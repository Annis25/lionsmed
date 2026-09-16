/* Page /espace/votes/ (liste) : filtre Tous/Ouverts/Clôturés + recherche, purement
   côté client — le serveur rend déjà toutes les cartes, JS ne fait que les montrer ou
   les masquer. Sans JS, toutes les cartes restent visibles : aucune fonctionnalité
   n'est perdue, seul le confort de filtrage disparaît. */
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    var toolbar = document.querySelector('[data-vote-toolbar]');
    if (!toolbar) return;
    var buttons = Array.prototype.slice.call(toolbar.querySelectorAll('[data-vote-filter]'));
    var search = toolbar.querySelector('[data-vote-search]');
    var cards = Array.prototype.slice.call(document.querySelectorAll('[data-vote-card]'));
    var empty = document.querySelector('[data-vote-empty]');
    var activeFilter = 'all';

    function apply() {
      var query = search ? search.value.trim().toLowerCase() : '';
      var visible = 0;
      cards.forEach(function (card) {
        var matchesFilter = activeFilter === 'all' || card.dataset.voteCard === activeFilter;
        var matchesQuery = !query || card.dataset.voteTitle.indexOf(query) !== -1;
        var show = matchesFilter && matchesQuery;
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (empty) empty.hidden = visible !== 0;
    }

    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        activeFilter = button.dataset.voteFilter;
        buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b === button)); });
        apply();
      });
    });
    if (search) search.addEventListener('input', apply);
  });
}());
