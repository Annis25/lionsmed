(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('form[data-confirm-delete]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (!window.confirm(form.getAttribute('data-confirm-delete'))) event.preventDefault();
      });
    });
  });
}());
