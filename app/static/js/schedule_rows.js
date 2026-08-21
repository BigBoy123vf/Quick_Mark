// Lets a lecturer add/remove repeatable day+time rows on the course form.
(function () {
  var container = document.getElementById('schedule-rows');
  var addButton = document.getElementById('add-schedule-row');
  if (!container || !addButton) return;

  addButton.addEventListener('click', function () {
    var row = container.querySelector('.schedule-row').cloneNode(true);
    row.querySelectorAll('select, input').forEach(function (field) { field.value = ''; });
    container.appendChild(row);
  });

  container.addEventListener('click', function (event) {
    if (!event.target.hasAttribute('data-remove-schedule-row')) return;
    // Always leave at least one row so the "add another" flow stays predictable.
    if (container.querySelectorAll('.schedule-row').length > 1) {
      event.target.closest('.schedule-row').remove();
    }
  });
})();
