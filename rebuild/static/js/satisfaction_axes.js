/* Page /espace/satisfaction/gestion/<id>/modifier/ : confirmation avant suppression
   d'un axe. Amélioration pure — sans JavaScript, le formulaire supprime directement
   (la suppression reste de toute façon bloquée dès qu'une réponse existe). */
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (!window.confirm(form.getAttribute('data-confirm'))) event.preventDefault();
      });
    });
  });
})();
