const {chromium}=require('/home/besbes/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
const root=path.resolve('mockups');
function walk(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()&&!['_backup','outils','validation'].includes(e.name)?walk(path.join(dir,e.name)):e.isFile()&&e.name.endsWith('.html')?[path.join(dir,e.name)]:[]);}
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const context=await browser.newContext({reducedMotion:'reduce'});
 const page=await context.newPage();const results=[];
 for(const file of walk(root)){
  const rel=path.relative(root,file);let errors=[],consoleErrors=[];page.removeAllListeners('pageerror');page.removeAllListeners('console');page.on('pageerror',e=>errors.push(e.message));page.on('console',msg=>{if(msg.type()==='error')consoleErrors.push({text:msg.text(),url:msg.location().url});});
  for(const width of [1440,1280,1024,768,430,375]){
   await page.setViewportSize({width,height:1000});
   const url='http://127.0.0.1:8876/'+rel+(rel.startsWith('espace/')?'?role=SUPER_ADMIN':'');
   await page.goto(url,{waitUntil:'load',timeout:30000});
   await page.evaluate(async()=>{await document.fonts.ready;document.querySelectorAll('img[loading="lazy"]').forEach(i=>i.loading='eager');await Promise.all([...document.images].filter(i=>!i.complete&&!i.hidden).map(i=>new Promise(resolve=>{i.addEventListener('load',resolve,{once:true});i.addEventListener('error',resolve,{once:true});})));});
   const data=await page.evaluate(()=>{
    const ids=new Set([...document.querySelectorAll('[id]')].map(x=>x.id));
    const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
    return {
     overflow:document.documentElement.scrollWidth>innerWidth,
     overflowing:[...document.querySelectorAll('body *')].filter(e=>visible(e)&&e.getBoundingClientRect().right>innerWidth+1&&!e.closest('svg')).slice(0,10).map(e=>e.tagName+'.'+e.className),
     h1:document.querySelectorAll('h1').length,
     altMissing:document.querySelectorAll('img:not([alt])').length,
     imagesMissing:[...document.images].filter(i=>i.complete&&!i.naturalWidth&&!i.hidden).map(i=>({src:i.getAttribute('src'),placeholder:!!i.closest('.media--vide')})),
     unnamed:[...document.querySelectorAll('a,button,input,select,textarea')].filter(e=>visible(e)&&!e.getAttribute('aria-label')&&!e.getAttribute('aria-labelledby')&&!e.textContent.trim()&&!e.labels?.length&&!e.querySelector('img[alt]:not([alt=""])')).map(e=>e.outerHTML.slice(0,150)),
     localAnchors:[...document.querySelectorAll('a[href^="#"]')].map(a=>a.getAttribute('href')).filter(h=>h==='#'||!ids.has(h.slice(1))),
     duplicateIds:[...document.querySelectorAll('[id]')].map(e=>e.id).filter((x,i,a)=>a.indexOf(x)!==i),
     forms:[...document.forms].map(f=>({action:f.getAttribute('action'),mockup:f.hasAttribute('data-maquette'),unlabelled:[...f.querySelectorAll('input,select,textarea')].filter(e=>!e.labels?.length&&e.type!=='hidden').length})),
     seo:{title:document.title,description:!!document.querySelector('meta[name="description"]'),canonical:!!document.querySelector('link[rel="canonical"]'),noindex:document.querySelector('meta[name="robots"]')?.content.includes('noindex'),og:!!document.querySelector('meta[property="og:image"]'),twitter:!!document.querySelector('meta[name="twitter:card"]'),jsonld:[...document.querySelectorAll('script[type="application/ld+json"]')].every(s=>{try{JSON.parse(s.textContent);return true}catch{return false}})},
     inlineStyles:document.querySelectorAll('[style]:not(.jauge__barre)').length,
     font:getComputedStyle(document.body).fontFamily,
     reducedMotion:[...document.querySelectorAll('*')].filter(e=>parseFloat(getComputedStyle(e).animationDuration)>0.01||parseFloat(getComputedStyle(e).transitionDuration)>0.01).length
    };
   });
   if(width===1440||width===375){await page.screenshot({path:path.join(root,'validation',rel.replaceAll('/','-')+'-'+width+'.png'),fullPage:true});}
   results.push({page:rel,width,...data,errors:[...errors],consoleErrors:[...consoleErrors]});
  }
  console.log(rel+' checked');
 }
 fs.writeFileSync(path.join(root,'validation/responsive.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify({runs:results.length,failures:results.filter(r=>r.overflow||r.h1!==1||r.altMissing||r.unnamed.length||r.localAnchors.length||r.duplicateIds.length||r.errors.length||r.reducedMotion).map(r=>({page:r.page,width:r.width,overflow:r.overflow,offenders:r.overflowing,unnamed:r.unnamed,anchors:r.localAnchors,errors:r.errors,reduced:r.reducedMotion}))},null,2));
 await browser.close();
})();
