/* Page Communication (/espace/communication/) : sélection des membres (recherche,
   sélection rapide), adresses externes, compteurs du résumé, garde anti double-soumission.
   Vanilla JS, aucune requête par case cochée. Sans JavaScript, le formulaire reste
   complet : cases à cocher réelles, textarea brut pour les adresses (une par ligne).
   Dans tous les cas le serveur recalcule et valide les destinataires : les totaux
   affichés ici ne sont qu'une aide à la saisie. */
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var CHANGED = 'communication:recipients-changed';

  function splitEmails(raw) {
    return raw.split(/[,;\s]+/).map(function (token) { return token.trim(); }).filter(Boolean);
  }

  function dedupe(tokens) {
    var seen = {}, out = [];
    tokens.forEach(function (token) {
      var key = token.toLowerCase();
      if (!seen[key]) { seen[key] = true; out.push(token); }
    });
    return out;
  }

  function plural(count, one, many) { return count === 1 ? one : many; }

  // Recherche tolérante : ni la casse ni les accents ne comptent (« rania » trouve « Rânia »).
  function fold(text) {
    return text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function notify() { document.dispatchEvent(new CustomEvent(CHANGED)); }

  function initMemberPicker() {
    var picker = document.querySelector('[data-member-picker]');
    if (!picker) return;
    var tools = picker.querySelector('[data-member-tools]');
    var search = picker.querySelector('[data-member-search]');
    var empty = picker.querySelector('[data-member-empty]');
    var entries = Array.prototype.map.call(picker.querySelectorAll('[data-member-row]'), function (row) {
      return { row: row, box: row.querySelector('[data-member]'), text: fold(row.textContent) };
    });
    if (!tools || !search || !entries.length) return;
    tools.hidden = false;

    function applyFilter() {
      var terms = fold(search.value).split(/\s+/).filter(Boolean);
      var shown = 0;
      entries.forEach(function (entry) {
        var match = terms.every(function (term) { return entry.text.indexOf(term) !== -1; });
        entry.row.hidden = !match;
        if (match) shown += 1;
      });
      if (empty) empty.hidden = shown !== 0;
    }

    search.addEventListener('input', applyFilter);
    // Entrée dans la recherche ne doit jamais soumettre le formulaire d'envoi.
    search.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') event.preventDefault();
    });

    picker.querySelectorAll('[data-select]').forEach(function (button) {
      button.addEventListener('click', function () {
        var mode = button.dataset.select;
        entries.forEach(function (entry) {
          entry.box.checked = mode === 'all' || (mode === 'responsibles' && entry.box.hasAttribute('data-responsible'));
        });
        // La sélection rapide porte sur tous les membres éligibles, pas sur le seul
        // résultat d'une recherche : le filtre est levé pour montrer l'état complet.
        search.value = '';
        applyFilter();
        notify();
      });
    });

    entries.forEach(function (entry) { entry.box.addEventListener('change', notify); });
    applyFilter();
  }

  function initEmailPicker() {
    var wrap = document.querySelector('[data-email-picker]');
    if (!wrap) return;
    var textarea = wrap.querySelector('textarea');
    var fallback = wrap.querySelector('[data-email-fallback]');
    var row = wrap.querySelector('[data-email-picker-row]');
    var input = wrap.querySelector('[data-email-picker-input]');
    var addBtn = wrap.querySelector('[data-email-picker-add]');
    var list = wrap.querySelector('[data-email-list]');
    var errorBox = wrap.querySelector('[data-email-picker-error]');
    if (!textarea || !fallback || !row || !input || !addBtn || !list || !errorBox) return;

    // Le textarea reste le champ réellement soumis ; la liste n'en est que la vue.
    var emails = dedupe(splitEmails(textarea.value));
    fallback.hidden = true;
    row.hidden = false;

    function showError(text) {
      errorBox.textContent = text;
      errorBox.hidden = !text;
      if (text) input.setAttribute('aria-invalid', 'true');
      else input.removeAttribute('aria-invalid');
    }

    function render() {
      list.innerHTML = '';
      list.hidden = !emails.length;
      emails.forEach(function (email, index) {
        var item = document.createElement('li');
        item.className = 'com-externe';
        var label = document.createElement('span');
        label.textContent = email;
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.setAttribute('aria-label', 'Retirer ' + email);
        // Icône dessinée (pas de glyphe typographique), même tracé que .cal-dialog__close.
        remove.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"></path></svg>';
        remove.addEventListener('click', function () {
          emails.splice(index, 1);
          sync();
          input.focus();
        });
        item.appendChild(label);
        item.appendChild(remove);
        list.appendChild(item);
      });
    }

    function sync() {
      textarea.value = emails.join('\n');
      wrap.dataset.emails = JSON.stringify(emails);
      render();
      notify();
    }

    // Renvoie false si la saisie en cours est invalide (elle reste alors dans le champ).
    function addFromInput() {
      var tokens = dedupe(splitEmails(input.value));
      if (!tokens.length) { showError(''); return true; }
      var invalid = tokens.filter(function (token) { return !EMAIL_RE.test(token); });
      if (invalid.length) {
        showError(plural(invalid.length, 'Adresse invalide : ', 'Adresses invalides : ') + invalid.join(', '));
        return false;
      }
      var added = 0;
      tokens.forEach(function (token) {
        var key = token.toLowerCase();
        if (!emails.some(function (existing) { return existing.toLowerCase() === key; })) { emails.push(token); added += 1; }
      });
      input.value = '';
      showError(added ? '' : 'Cette adresse figure déjà dans la liste.');
      sync();
      return true;
    }

    addBtn.addEventListener('click', function () { addFromInput(); input.focus(); });
    input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ',') { event.preventDefault(); addFromInput(); }
    });
    input.addEventListener('paste', function () {
      setTimeout(function () { if (splitEmails(input.value).length > 1) addFromInput(); }, 0);
    });

    // Une adresse tapée mais pas encore ajoutée ne doit ni être perdue ni partir invalide.
    var form = wrap.closest('form');
    if (form) form.addEventListener('submit', function (event) {
      if (!addFromInput()) { event.preventDefault(); input.focus(); }
    });

    wrap.dataset.emails = JSON.stringify(emails);
    render();
  }

  function initSummary() {
    var form = document.querySelector('[data-communication-form]');
    if (!form) return;
    var picker = form.querySelector('[data-email-picker]');
    var boxes = form.querySelectorAll('[data-member]');
    var memberCount = form.querySelector('[data-member-count]');
    var externalCount = form.querySelector('[data-external-count]');
    var sInternal = form.querySelector('[data-summary-internal]');
    var sExternal = form.querySelector('[data-summary-external]');
    var sTotal = form.querySelector('[data-summary-total]');
    var note = form.querySelector('[data-summary-note]');
    var live = form.querySelector('[data-summary-live]');

    function externalEmails() {
      if (picker && picker.dataset.emails) return JSON.parse(picker.dataset.emails);
      var textarea = picker ? picker.querySelector('textarea') : null;
      return textarea ? dedupe(splitEmails(textarea.value)) : [];
    }

    function update(announce) {
      var selected = {}, internal = 0;
      Array.prototype.forEach.call(boxes, function (box) {
        if (!box.checked) return;
        internal += 1;
        selected[(box.dataset.email || '').toLowerCase()] = true;
      });
      // Même règle que le serveur : une adresse externe identique à celle d'un membre
      // coché n'est pas comptée une seconde fois.
      var listed = externalEmails();
      var external = listed.filter(function (email) { return !selected[email.toLowerCase()]; }).length;
      var absorbed = listed.length - external;
      var total = internal + external;

      if (memberCount) memberCount.textContent = internal + ' ' + plural(internal, 'membre sélectionné', 'membres sélectionnés') + ' sur ' + boxes.length;
      if (externalCount) {
        externalCount.textContent = listed.length + ' ' + plural(listed.length, 'adresse externe', 'adresses externes')
          + (absorbed ? ' · ' + absorbed + ' ' + plural(absorbed, 'déjà comptée', 'déjà comptées') + ' parmi les membres sélectionnés' : '');
      }
      if (sInternal) sInternal.textContent = internal;
      if (sExternal) sExternal.textContent = external;
      if (sTotal) sTotal.textContent = total;
      var text = total
        ? total + ' ' + plural(total, 'destinataire recevra', 'destinataires recevront') + ' chacun un e-mail individuel.'
        : 'Aucun destinataire pour l’instant.';
      if (note) note.textContent = text;
      if (live && announce) {
        live.textContent = total
          ? total + ' ' + plural(total, 'destinataire', 'destinataires') + ' : ' + internal + ' ' + plural(internal, 'membre', 'membres')
            + ' et ' + external + ' ' + plural(external, 'adresse externe', 'adresses externes') + '.'
          : 'Aucun destinataire.';
      }
    }

    document.addEventListener(CHANGED, function () { update(true); });
    update(false);
  }

  // Un double clic ou une double validation au clavier ne soumet qu'une fois ; le serveur
  // reste protégé de toute façon par la clé d'idempotence de la campagne.
  function initSubmitOnce() {
    document.querySelectorAll('[data-submit-once]').forEach(function (form) {
      var button = form.querySelector('[data-submit-once-button]');
      var label = button ? button.textContent : '';
      form.addEventListener('submit', function (event) {
        if (form.dataset.submitted === 'yes') { event.preventDefault(); return; }
        form.dataset.submitted = 'yes';
        var main = !event.submitter || event.submitter === button;
        // Après la collecte des données : un bouton désactivé ne transmet pas sa valeur.
        setTimeout(function () {
          form.querySelectorAll('button[type="submit"]').forEach(function (other) { other.disabled = true; });
          if (button && main && button.dataset.busyLabel) button.textContent = button.dataset.busyLabel;
        }, 0);
      });
      // Retour arrière du navigateur (page restaurée telle quelle) : le formulaire redevient utilisable.
      window.addEventListener('pageshow', function (event) {
        if (!event.persisted) return;
        delete form.dataset.submitted;
        form.querySelectorAll('button[type="submit"]').forEach(function (other) { other.disabled = false; });
        if (button) button.textContent = label;
      });
    });
  }

  ready(function () {
    initMemberPicker();
    initEmailPicker();
    initSummary();
    initSubmitOnce();
  });
})();
