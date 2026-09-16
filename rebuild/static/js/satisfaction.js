/* Page /espace/satisfaction/ : compteur de caractères du commentaire facultatif.
   Amélioration pure — le maxlength HTML limite déjà la saisie sans JavaScript.
   Plusieurs consultations peuvent être ouvertes en même temps (un formulaire préfixé
   par période chacune) : on associe chaque compteur au textarea de sa propre carte,
   jamais par un id fixe partagé entre plusieurs formulaires sur la même page. */
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    document.querySelectorAll('[data-comment-counter]').forEach(function (counter) {
      var field = counter.closest('.champ');
      var textarea = field ? field.querySelector('textarea') : null;
      if (!textarea) return;
      var max = parseInt(textarea.getAttribute('maxlength'), 10) || 500;
      function update() { counter.textContent = textarea.value.length + ' / ' + max; }
      textarea.addEventListener('input', update);
      update();
    });
  });
})();
