(function(){
  var list=document.getElementById('options-list');
  var addBtn=document.getElementById('add-option');
  function makeRow(){
    var row=document.createElement('div');row.className='options-list__ligne';
    var input=document.createElement('input');input.className='champ__input';input.type='text';input.name='options';input.setAttribute('aria-label','Libellé du choix');input.placeholder='Libellé du choix';
    var remove=document.createElement('button');remove.className='btn btn--ghost btn--sm';remove.type='button';remove.dataset.role='remove-option';remove.setAttribute('aria-label','Retirer ce choix');remove.textContent='Retirer';
    row.appendChild(input);row.appendChild(remove);return row;
  }
  addBtn.addEventListener('click',function(){var row=makeRow();list.appendChild(row);row.querySelector('input').focus();});
  list.addEventListener('click',function(e){
    if(e.target.dataset.role==='remove-option'){
      if(list.children.length>1){e.target.closest('.options-list__ligne').remove();}
      else{e.target.previousElementSibling.value='';}
    }
  });
})();
const creationForm = document.getElementById('vote-create-form');
if (creationForm) creationForm.addEventListener('submit', function () {
  const submit = creationForm.querySelector('button[type=submit]');
  if (submit) submit.disabled = true;
});
