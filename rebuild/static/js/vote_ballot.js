(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-vote-ballot]').forEach(function (form) {
      var blank = form.querySelector('[data-vote-blank]');
      var options = Array.prototype.slice.call(form.querySelectorAll('[data-vote-option]'));
      if (!blank) return;
      blank.addEventListener('change', function () {
        if (blank.checked) options.forEach(function (option) { option.checked = false; });
      });
      options.forEach(function (option) {
        option.addEventListener('change', function () {
          if (option.checked) blank.checked = false;
        });
      });
    });
  });
}());
