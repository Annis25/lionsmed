/* Calendrier — comportements spécifiques à la page /espace/calendrier/.
   Vanilla JS, aucune dépendance : ouverture des <dialog> natives (add/detail/sync),
   préremplissage de la date depuis une cellule du mois, copie du lien ICS. */
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    var dataEl = document.getElementById('cal-events-data');
    var EVENTS = {};
    if (dataEl) {
      try { EVENTS = JSON.parse(dataEl.textContent) || {}; } catch (e) { EVENTS = {}; }
    }
    function isDesktop() { return window.matchMedia('(min-width: 761px)').matches; }
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

    var addDialog = document.getElementById('dialog-add');
    document.querySelectorAll('[data-open-add]').forEach(function (btn) {
      btn.addEventListener('click', function () { openDialog(addDialog); });
    });

    document.querySelectorAll('[data-open-dialog]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        openDialog(document.getElementById(btn.getAttribute('data-open-dialog')));
      });
    });

    // Clic sur une cellule du mois : sur desktop, ouvre l'ajout avec la date
    // préremplie plutôt que de naviguer (le lien reste le comportement de repli
    // mobile / sans JavaScript, qui sélectionne simplement le jour).
    document.querySelectorAll('[data-cal-daycell]').forEach(function (link) {
      link.addEventListener('click', function (event) {
        if (!isDesktop() || !addDialog) return;
        event.preventDefault();
        var input = addDialog.querySelector('[name="starts_at"]');
        if (input) input.value = link.getAttribute('data-date') + 'T09:00';
        openDialog(addDialog);
      });
    });

    // Détail d'un événement : chip du mois, bloc de la timeline, liste "du jour"
    // ou colonne "À venir" — une seule fenêtre partagée, remplie depuis les
    // données JSON déjà présentes dans la page (aucun appel réseau).
    var viewDialog = document.getElementById('dialog-event');
    function setField(selector, value) {
      var el = viewDialog.querySelector('[data-field="' + selector + '"]');
      if (!el) return;
      if (!value) { el.hidden = true; return; }
      el.hidden = false;
      el.textContent = value;
    }
    document.querySelectorAll('[data-cal-event]').forEach(function (trigger) {
      trigger.addEventListener('click', function () {
        var data = EVENTS[trigger.getAttribute('data-cal-event')];
        if (!data || !viewDialog) return;
        setField('title', data.title);
        setField('when', data.when);
        setField('location', data.location);
        setField('description', data.description);
        var meetingBlock = viewDialog.querySelector('[data-field="meeting"]');
        if (data.meeting_link) {
          meetingBlock.hidden = false;
          meetingBlock.querySelector('a').href = data.meeting_link;
        } else {
          meetingBlock.hidden = true;
        }
        setField('category', data.category);
        var rsvpBlock = viewDialog.querySelector('[data-rsvp-block]');
        if (data.registration_enabled) {
          rsvpBlock.hidden = false;
          var remainingEl = viewDialog.querySelector('[data-field="remaining"]');
          remainingEl.textContent = data.remaining_label || '';
          remainingEl.hidden = !data.remaining_label;
          var confirmForm = viewDialog.querySelector('[data-form="confirm"]');
          var cancelForm = viewDialog.querySelector('[data-form="cancel"]');
          confirmForm.action = data.rsvp_url;
          cancelForm.action = data.rsvp_url;
          var already = data.registration_status === 'CONFIRMED';
          confirmForm.hidden = already;
          cancelForm.hidden = !already;
        } else {
          rsvpBlock.hidden = true;
        }
        openDialog(viewDialog);
      });
    });

    // Synchronisation : copie du lien privé sans jamais l'afficher en clair.
    var copyBtn = document.getElementById('copier-lien');
    var linkInput = document.getElementById('lien-abonnement');
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
    if (copyBtn && linkInput) {
      copyBtn.addEventListener('click', function () {
        var done = function () {
          copyBtn.textContent = 'Lien copié';
          setTimeout(function () { copyBtn.textContent = 'Copier mon lien privé'; }, 2000);
        };
        if (navigator.clipboard) navigator.clipboard.writeText(linkInput.value).then(done).catch(function () { fallbackCopy(linkInput.value); done(); });
        else { fallbackCopy(linkInput.value); done(); }
      });
    }
  });
})();
