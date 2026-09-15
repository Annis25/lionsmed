document.querySelectorAll('[data-phone]').forEach(function (input) {
  input.addEventListener('input', function () {
    var value = input.value.replace(/[^0-9+ ]/g, '');
    input.value = value.replace(/(?!^)\+/g, '');
  });
});
