/* Formulaire d'action : aperçu des images choisies et contrôle avant l'envoi.
   Sans JavaScript, le formulaire fonctionne tel quel ; le serveur refuse de toute façon
   une image trop lourde ou en trop. Ce script évite seulement d'attendre l'envoi pour le savoir. */
(function () {
  'use strict';
  var form = document.querySelector('[data-action-form]');
  if (!form) return;
  var maxBytes = parseInt(form.dataset.photoMaxBytes, 10) || 5 * 1024 * 1024;
  var galleryMax = parseInt(form.dataset.galleryMax, 10) || 9;
  var galleryCount = parseInt(form.dataset.galleryCount, 10) || 0;
  var alertBox = form.querySelector('[data-file-alert]');
  var accepted = /\.(jpe?g|png|webp|heic|heif)$/i;
  var urls = {};

  function weight(bytes) {
    if (bytes < 1048576) return Math.max(1, Math.round(bytes / 1024)) + ' Ko';
    return (bytes / 1048576).toFixed(1).replace('.', ',').replace(',0', '') + ' Mo';
  }

  /* Deux formulations du même refus : courte sous la vignette, complète dans l'alerte. */
  function problemOf(file) {
    if (!accepted.test(file.name)) return { short: 'Format non accepté (JPG, PNG, WebP ou HEIC)', full: 'n’est pas dans un format accepté (JPG, PNG, WebP ou HEIC)' };
    if (file.size > maxBytes) return { short: 'Trop lourde : ' + weight(file.size) + ' (' + weight(maxBytes) + ' maximum)', full: 'pèse ' + weight(file.size) + ' (' + weight(maxBytes) + ' maximum)' };
    return null;
  }

  function render(input) {
    var list = form.querySelector('[data-file-preview="' + input.id + '"]');
    if (!list) return;
    (urls[input.id] || []).forEach(function (url) { URL.revokeObjectURL(url); });
    urls[input.id] = [];
    list.textContent = '';
    Array.prototype.forEach.call(input.files, function (file) {
      var item = document.createElement('li');
      var problem = problemOf(file);
      var thumb = document.createElement('span');
      thumb.className = 'apercu-fichiers__vignette';
      if (/\.(jpe?g|png|webp)$/i.test(file.name)) {
        var image = document.createElement('img');
        var url = URL.createObjectURL(file);
        urls[input.id].push(url);
        image.alt = '';
        image.addEventListener('error', function () { image.remove(); });
        image.src = url;
        thumb.appendChild(image);
      }
      var text = document.createElement('span');
      text.className = 'apercu-fichiers__texte';
      var name = document.createElement('span');
      name.className = 'apercu-fichiers__nom';
      name.textContent = file.name;
      var detail = document.createElement('span');
      detail.className = 'apercu-fichiers__detail';
      detail.textContent = problem ? problem.short : weight(file.size);
      text.appendChild(name);
      text.appendChild(detail);
      item.appendChild(thumb);
      item.appendChild(text);
      if (problem) item.className = 'apercu-fichiers__refus';
      list.appendChild(item);
    });
  }

  function problems() {
    var found = [];
    Array.prototype.forEach.call(form.querySelectorAll('input[type="file"]'), function (input) {
      Array.prototype.forEach.call(input.files, function (file) {
        var problem = problemOf(file);
        if (problem) found.push('« ' + file.name + ' » ' + problem.full + '.');
      });
      if (input.multiple && input.files.length + galleryCount > galleryMax) {
        var left = Math.max(galleryMax - galleryCount, 0);
        found.push('Trop d’images : ' + (left ? 'vous pouvez encore en ajouter ' + left + ' (' + input.files.length + ' choisies).' : 'cette action a déjà ses ' + galleryMax + ' images supplémentaires.'));
      }
    });
    return found;
  }

  function refresh() {
    var found = problems();
    if (!alertBox) return found;
    alertBox.hidden = !found.length;
    alertBox.textContent = found.length ? found.join(' ') + ' Choisissez d’autres fichiers avant d’enregistrer.' : '';
    return found;
  }

  Array.prototype.forEach.call(form.querySelectorAll('input[type="file"]'), function (input) {
    input.addEventListener('change', function () { render(input); refresh(); });
    if (input.files.length) render(input);
  });
  refresh();

  form.addEventListener('submit', function (event) {
    if (!refresh().length) return;
    event.preventDefault();
    alertBox.setAttribute('tabindex', '-1');
    alertBox.focus();
    alertBox.scrollIntoView({ block: 'center' });
  });
}());
