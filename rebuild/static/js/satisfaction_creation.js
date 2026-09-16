(() => {
  const builder = document.querySelector('[data-axis-builder]');
  if (!builder) return;
  const source = builder.querySelector('[data-axis-source]');
  const draft = document.getElementById('axis-draft');
  const list = builder.querySelector('[data-axis-list]');
  const error = builder.querySelector('[data-axis-error]');
  let labels = source.value.split(/\r?\n/).map(value => value.trim()).filter(Boolean);
  const sync = () => { source.value = labels.join('\n'); };
  function button(label, action, disabled=false) {
    const item = document.createElement('button');
    item.type = 'button'; item.className = 'btn btn--outline btn--sm';
    item.textContent = label; item.dataset.action = action; item.disabled = disabled;
    return item;
  }
  function render() {
    list.replaceChildren();
    labels.forEach((label, index) => {
      const row = document.createElement('li'); row.className = 'satisfaction-axis-row';
      const order = document.createElement('span'); order.className = 'satisfaction-axis-row__order'; order.textContent = index + 1;
      const text = document.createElement('span'); text.className = 'satisfaction-axis-row__label'; text.textContent = label;
      const actions = document.createElement('span'); actions.className = 'satisfaction-axis-builder__actions';
      actions.append(button('Monter', 'up', index === 0), button('Descendre', 'down', index === labels.length-1), button('Supprimer', 'delete'));
      row.append(order, text, actions); row.dataset.index = index; list.append(row);
    });
    sync();
  }
  function add() {
    const label = draft.value.trim(); error.hidden = true;
    if (!label) { error.textContent = 'Saisissez le nom de l’axe.'; error.hidden = false; return; }
    if (labels.some(item => item.toLocaleLowerCase() === label.toLocaleLowerCase())) { error.textContent = 'Cet axe existe déjà.'; error.hidden = false; return; }
    if (labels.length >= 30) { error.textContent = '30 axes maximum.'; error.hidden = false; return; }
    labels.push(label); draft.value = ''; render(); draft.focus();
  }
  builder.querySelector('[data-axis-add]').addEventListener('click', add);
  draft.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); add(); } });
  list.addEventListener('click', event => {
    const control = event.target.closest('[data-action]'); if (!control) return;
    const index = Number(control.closest('li').dataset.index), action = control.dataset.action;
    if (action === 'delete') labels.splice(index, 1);
    else { const other = action === 'up' ? index - 1 : index + 1; [labels[index], labels[other]] = [labels[other], labels[index]]; }
    render();
  });
  builder.classList.add('is-enhanced'); render();
})();
