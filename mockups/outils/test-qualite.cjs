const {chromium}=require('/home/besbes/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {PNG}=require('/home/besbes/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pngjs');
const fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});const base='http://127.0.0.1:8876/';
 const output={contrasts:[],pixels:[],roles:[],spacing:[]};
 const publicPages=fs.readdirSync('mockups').filter(x=>x.endsWith('.html'));
 const privatePages=fs.readdirSync('mockups/espace').filter(x=>x.endsWith('.html'));
 for(const f of [...publicPages,...privatePages.map(x=>'espace/'+x)]){
  await page.goto(base+f+(f.startsWith('espace/')?'?role=SUPER_ADMIN':''));
  const data=await page.evaluate(()=>{
   function rgb(v){const a=v.match(/[\d.]+/g)?.map(Number);return a?.length>=3?[a[0],a[1],a[2],a[3]??1]:[0,0,0,0];}
   function mix(a,b){return a.slice(0,3).map((c,i)=>c*a[3]+b[i]*(1-a[3])).concat(1);}
   function lum(c){return c.slice(0,3).map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}
   const failures=[];let measured=0;
   for(const e of document.querySelectorAll('body *')){
    if(!e.getClientRects().length||getComputedStyle(e).visibility==='hidden'||e.closest('svg,script,style,.media--vide,[disabled]')||!Array.from(e.childNodes).some(n=>n.nodeType===3&&n.textContent.trim()))continue;
    const chain=[];for(let a=e;a;a=a.parentElement)chain.unshift(a);
    if(chain.some(a=>getComputedStyle(a).opacity==='0'))continue;
    let bg=[255,255,255,1];for(const a of chain)bg=mix(rgb(getComputedStyle(a).backgroundColor),bg);
    const cs=getComputedStyle(e),fg=mix(rgb(cs.color),bg);const l1=lum(fg),l2=lum(bg);const ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);const threshold=parseFloat(cs.fontSize)>=24||(parseFloat(cs.fontSize)>=18.66&&parseInt(cs.fontWeight)>=700)?3:4.5;
    if(e.closest('.hero,.rejoindre'))continue; measured++;
    if(ratio<threshold-.02)failures.push({text:e.textContent.trim().slice(0,65),class:e.className,ratio:+ratio.toFixed(2),threshold});
   }
   const gaps=[];
   for(const section of document.querySelectorAll('main > .section')){
    const container=section.querySelector(':scope > .container');if(!container)continue;
    const children=[...container.children].filter(e=>e.getClientRects().length);
    const last=children.at(-1);if(last){const excess=section.getBoundingClientRect().bottom-Math.max(...children.map(e=>e.getBoundingClientRect().bottom))-parseFloat(getComputedStyle(section).paddingBottom);if(excess>80)gaps.push({section:section.textContent.trim().slice(0,45),excess});}
   }
   return {measured,failures,gaps};
  });
  output.contrasts.push({page:f,...data});output.spacing.push({page:f,gaps:data.gaps});
 }
 function lum(c){return c.map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}
 for(const width of [1440,1280,1024,768,430,375]){
  await page.setViewportSize({width,height:1000});await page.goto(base+'accueil.html');await page.evaluate(()=>document.fonts.ready);
  for(const selector of ['.hero__titre','.hero__lede','.hero__valeurs li:nth-child(1)','.hero__valeurs li:nth-child(2)','.hero__valeurs li:nth-child(3)','.hero__lieu','.rejoindre__texte h2','.rejoindre__texte .lede']){
   const el=page.locator(selector);if(!await el.isVisible()){output.pixels.push({width,selector,hidden:true});continue;}await el.scrollIntoViewIfNeeded();
   const style=await el.evaluate(e=>({color:getComputedStyle(e).color,size:getComputedStyle(e).fontSize}));
   // Masquer uniquement les glyphes pour mesurer les pixels réellement derrière le texte.
   const mask=await page.addStyleTag({content:selector+','+selector+' * {color:transparent!important;text-shadow:none!important;}'});
   const png=PNG.sync.read(await el.screenshot());await mask.evaluate(e=>e.remove());
   let min=100,maxL=0;const rgba=style.color.match(/[\d.]+/g).map(Number),alpha=rgba[3]??1;
   for(let i=0;i<png.data.length;i+=16){const bg=[png.data[i],png.data[i+1],png.data[i+2]];const fg=rgba.slice(0,3).map((v,j)=>v*alpha+bg[j]*(1-alpha));const l1=lum(fg),l2=lum(bg);min=Math.min(min,(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05));maxL=Math.max(maxL,l2);}
   output.pixels.push({width,selector,minContrast:+min.toFixed(2),method:'pixels du rendu sans glyphes, échantillonnage tous les 4 pixels'});
  }
 }
 await page.setViewportSize({width:1440,height:1000});
 for(const f of privatePages){for(const role of ['MEMBRE','INVITE','BUREAU','PRESIDENT','SECRETAIRE','DIRECTEUR','SUPER_ADMIN']){
  await page.goto(base+'espace/'+f+'?role='+role);
  output.roles.push(await page.evaluate(({f,role})=>{const main=document.querySelector('[data-page-permissions]');return {page:f,role,allowed:main.dataset.pagePermissions.split(/\s+/).includes(role),visible:!!main.getClientRects().length,forbiddenVisible:[...document.querySelectorAll('[data-roles]')].filter(e=>!e.dataset.roles.split(/\s+/).includes(role)&&e.getClientRects().length).length};},{f,role}));
 }}
 fs.writeFileSync('mockups/validation/qualite.json',JSON.stringify(output,null,2));
 console.log(JSON.stringify({contrastFailures:output.contrasts.filter(x=>x.failures.length),pixels:output.pixels,roleFailures:output.roles.filter(x=>x.allowed!==x.visible||x.forbiddenVisible),spacing:output.spacing.filter(x=>x.gaps.length)},null,2));await browser.close();
})();
