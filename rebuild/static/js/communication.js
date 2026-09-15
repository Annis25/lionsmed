/* Page Communication (/espace/communication/) : widget de saisie des adresses
   supplémentaires (chips par-dessus le textarea réel, qui reste la source soumise),
   compteur de destinataires informatif, garde anti double-soumission sur la
   confirmation. Vanilla JS ; le formulaire fonctionne sans JavaScript (textarea brut,
   une adresse par ligne ; recalcul et validation systématiques côté serveur). */
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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

  function initEmailPicker() {
    var wrap = document.querySelector('[data-email-picker]');
    if (!wrap) return;
    var textarea = wrap.querySelector('textarea');
    var row = wrap.querySelector('[data-email-picker-row]');
    var input = wrap.querySelector('[data-email-picker-input]');
    var addBtn = wrap.querySelector('[data-email-picker-add]');
    var chipsBox = wrap.querySelector('[data-email-chips]');
    var errorBox = wrap.querySelector('[data-email-picker-error]');
    if (!textarea || !row || !input || !addBtn || !chipsBox) return;

    var emails = dedupe(splitEmails(textarea.value));
    textarea.hidden = true;
    row.hidden = false;
    chipsBox.hidden = false;

    function renderChips() {
      chipsBox.innerHTML = '';
      emails.forEach(function (email, index) {
        var chip = document.createElement('span');
        chip.className = 'email-chip';
        var label = document.createElement('span');
        label.textContent = email;
        var remove = document.createElement('button');
        remove.type = 'button';
        remove.setAttribute('aria-label', 'Retirer ' + email);
        // Icône dessinée (pas de glyphe typographique), même tracé que .cal-dialog__close.
        remove.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="m5 5 14 14M19 5 5 19"></path></svg>';
        remove.addEventListener('click', function () {
          emails.splice(index, 1);
          sync();
        });
        chip.appendChild(label);
        chip.appendChild(remove);
        chipsBox.appendChild(chip);
      });
    }

    function sync() {
      textarea.value = emails.join('\n');
      renderChips();
      document.dispatchEvent(new CustomEvent('communication:recipients-changed'));
    }

    function addFromInput() {
      var tokens = dedupe(splitEmails(input.value));
      if (!tokens.length) return;
      var invalid = tokens.filter(function (token) { return !EMAIL_RE.test(token); });
      if (invalid.length) {
        errorBox.textContent = 'Adresse invalide : ' + invalid.join(', ');
        errorBox.hidden = false;
        return;
      }
      errorBox.hidden = true;
      tokens.forEach(function (token) {
        var key = token.toLowerCase();
        if (!emails.some(function (existing) { return existing.toLowerCase() === key; })) emails.push(token);
      });
      input.value = '';
      sync();
    }

    addBtn.addEventListener('click', addFromInput);
    input.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ',') { event.preventDefault(); addFromInput(); }
    });
    input.addEventListener('paste', function () {
      setTimeout(function () { if (splitEmails(input.value).length > 1) addFromInput(); }, 0);
    });

    renderChips();
  }

  function initAudienceCounter() {
    var radios = document.querySelectorAll('[data-audience-radio]');
    if (!radios.length) return;

    function selectedRadio() { return document.querySelector('[data-audience-radio]:checked'); }
    function externalCount() { return document.querySelectorAll('[data-email-chips] .email-chip').length; }
    function plural(count) { return count === 1 ? '' : 's'; }

    function update() {
      var radio = selectedRadio();
      var internal = radio ? parseInt(radio.dataset.count, 10) || 0 : 0;
      var label = radio ? radio.dataset.label || '' : '';
      var external = externalCount();
      var total = internal + external;

      document.querySelectorAll('[data-audience-radio]').forEach(function (input) {
        var countEl = input.closest('label').querySelector('[data-audience-count]');
        if (!countEl) return;
        var count = parseInt(input.dataset.count, 10) || 0;
        countEl.textContent = count + ' destinataire' + plural(count);
      });

      var totalSummary = document.querySelector('[data-total-summary]');
      if (totalSummary) {
        var text = total + ' destinataire' + plural(total) + ' au total';
        if (external) text += ' (dont ' + external + ' adresse' + plural(external) + ' supplémentaire' + plural(external) + ')';
        totalSummary.textContent = text;
      }
      var sInternal = document.querySelector('[data-summary-internal]');
      var sExternal = document.querySelector('[data-summary-external]');
      var sTotal = document.querySelector('[data-summary-total]');
      var sAudience = document.querySelector('[data-summary-audience]');
      if (sInternal) sInternal.textContent = internal;
      if (sExternal) sExternal.textContent = external;
      if (sTotal) sTotal.textContent = total;
      if (sAudience) sAudience.textContent = label;
    }

    radios.forEach(function (radio) { radio.addEventListener('change', update); });
    document.addEventListener('communication:recipients-changed', update);
    update();
  }

  function initDoubleSubmitGuard() {
    var btn = document.querySelector('[data-confirm-send]');
    if (!btn) return;
    var form = btn.closest('form');
    if (!form) return;
    form.addEventListener('submit', function () {
      if (form.dataset.submitted === 'yes') return;
      form.dataset.submitted = 'yes';
      setTimeout(function () {
        btn.disabled = true;
        btn.textContent = 'Envoi en cours…';
      }, 0);
    });
  }

  ready(function () {
    initEmailPicker();
    initAudienceCounter();
    initDoubleSubmitGuard();
  });
})();
