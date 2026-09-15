/* Profil public — bloc « Mon profil public » : ouverture du modal QR (dialog native,
   Escape/piège de focus/restauration gérés nativement par l'élément) et copie du lien
   public. Vanilla JS, même patron que calendrier.js. */
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    function openDialog(dialog) { if (dialog && typeof dialog.showModal === 'function') dialog.showModal(); }

    document.querySelectorAll('[data-close-dialog]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var dialog = btn.closest('dialog');
        if (dialog) dialog.close();
      });
    });
    document.querySelectorAll('dialog.cal-dialog').forEach(function (dialog) {
      dialog.addEventListener('click', function (event) {
        if (event.target === dialog) dialog.close();
      });
    });
    document.querySelectorAll('[data-open-dialog]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        openDialog(document.getElementById(btn.getAttribute('data-open-dialog')));
      });
    });

    var copyBtn = document.getElementById('qr-copy-link');
    function fallbackCopy(text) {
      var textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try { document.execCommand('copy'); } catch (e) { /* silencieux */ }
      document.body.removeChild(textarea);
    }
    if (copyBtn) {
      copyBtn.addEventListener('click', function () {
        var text = copyBtn.getAttribute('data-copy-text') || '';
        var done = function () {
          copyBtn.textContent = 'Copié !';
          setTimeout(function () { copyBtn.textContent = 'Copier le lien'; }, 1500);
        };
        if (navigator.clipboard) navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text); done(); });
        else { fallbackCopy(text); done(); }
      });
    }
  });
})();
