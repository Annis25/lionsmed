(() => {
  const editor = document.querySelector('[data-portrait-editor]');
  if (!editor) return;
  const canvas = editor.querySelector('canvas'), ctx = canvas.getContext('2d');
  const controls = ['zoom', 'x', 'y'].map(k => ({key:k, input:document.getElementById(`portrait-${k}`), hidden:document.getElementById(`id_photo_${k}`)}));
  const file = document.getElementById('id_photo'), status = editor.querySelector('[data-portrait-status]');
  let image = null, objectURL = null, drag = null;
  const values = () => Object.fromEntries(controls.map(c => [c.key, Number(c.input.value)]));
  function draw() {
    if (!image) return;
    const {zoom,x,y} = values(), side = Math.min(image.width,image.height)/zoom;
    ctx.clearRect(0,0,320,320);
    ctx.drawImage(image,(image.width-side)*x/100,(image.height-side)*y/100,side,side,0,0,320,320);
    controls.forEach(c => { c.hidden.value = c.input.value; });
  }
  function reset() { controls.forEach(c => {c.input.value = c.key === 'zoom' ? 1 : 50;}); draw(); }
  function load(src, fresh) {
    const next = new Image();
    next.onload = () => {image=next; editor.hidden=false; if(fresh) reset(); else draw(); status.textContent='Aperçu prêt. Enregistrez pour appliquer le cadrage.';};
    next.onerror = () => {editor.hidden=false; status.textContent='Aperçu indisponible pour ce format. La photo sera vérifiée lors de l’enregistrement.';};
    next.src=src;
  }
  controls.forEach(c => {c.input.value=c.hidden.value || (c.key==='zoom'?1:50); c.input.addEventListener('input',draw);});
  editor.querySelector('[data-portrait-reset]').addEventListener('click',reset);
  file.addEventListener('change', () => {
    if(objectURL) URL.revokeObjectURL(objectURL);
    if(file.files[0]) {objectURL=URL.createObjectURL(file.files[0]); controls.forEach(c=>{c.hidden.value=c.input.value=c.key==='zoom'?1:50;}); load(objectURL,true);}
    else if(editor.dataset.source) load(editor.dataset.source,false);
  });
  canvas.addEventListener('pointerdown',e=>{if(!image)return; drag={x:e.clientX,y:e.clientY,...values()}; canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{
    if(!drag||!image)return;
    const side=Math.min(image.width,image.height)/drag.zoom, scale=side/canvas.getBoundingClientRect().width;
    for(const [key,delta,extent] of [['x',e.clientX-drag.x,image.width-side],['y',e.clientY-drag.y,image.height-side]]) {
      controls.find(c=>c.key===key).input.value=extent?Math.max(0,Math.min(100,drag[key]-delta*scale/extent*100)):50;
    }
    draw();
  });
  for(const event of ['pointerup','pointercancel','lostpointercapture']) canvas.addEventListener(event,()=>{drag=null;});
  if(editor.dataset.source) load(editor.dataset.source,false);
})();
