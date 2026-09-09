const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({reducedMotion:'reduce'}),base=process.env.LIONSMED_BROWSER_URL;
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 async function login(p){await p.goto(base+'/connexion/');await p.locator('#id_username').fill(process.env.LIONSMED_BROWSER_EMAIL);await p.locator('#id_password').fill(process.env.LIONSMED_BROWSER_PASSWORD);await Promise.all([p.waitForURL(url=>url.pathname==='/espace/'),p.locator('button[type=submit]').click()]);}
 await login(page);
 const paths=['/espace/','/espace/profil/','/espace/profil/modifier/','/espace/annuaire/',`/espace/membres/${process.env.LIONSMED_OTHER_ID}/`,'/espace/parcours/','/espace/parcours/ajouter/','/espace/gestion/membres/','/espace/pilotage/','/espace/gestion/annees/',`/espace/gestion/membres/${process.env.LIONSMED_OTHER_ID}/`];
 const results=[];
 for(const width of [1440,1280,1024,768,430,375])for(let i=0;i<paths.length;i++){
  await page.setViewportSize({width,height:900});await page.goto(base+paths[i]);await page.evaluate(()=>document.fonts.ready);
  const d=await page.evaluate(()=>{
   const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
   return {width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,h1:document.querySelectorAll('h1').length,
    unnamed:[...document.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea')].filter(e=>visible(e)&&!e.textContent.trim()&&!e.labels?.length&&!e.getAttribute('aria-label')).length,
    short:[...document.querySelectorAll('input:not([type=checkbox]):not([type=hidden]),select')].filter(e=>visible(e)&&e.getBoundingClientRect().height<44).map(e=>e.id),
    robots:document.querySelector('meta[name=robots]').content};
  });assert.equal(d.width,width);assert(!d.overflow,`Overflow ${paths[i]} ${width}`);assert.equal(d.h1,1);assert.equal(d.unnamed,0);assert.equal(d.short.length,0,JSON.stringify(d));assert(d.robots.includes('noindex'));results.push({path:paths[i],...d});
  if([375,1440].includes(width))await page.screenshot({path:`/tmp/lionsmed-lot2-page${i}-${width}.png`,fullPage:true});
 }
 await page.goto(base+'/espace/profil/modifier/');await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'contenu');
 await page.locator('#id_first_name').fill('');await page.locator('main button[type=submit]').click();assert(await page.locator('#id_first_name').getAttribute('aria-invalid'));
 await page.locator('.app-bascule').click();await page.keyboard.press('Escape');assert.equal(await page.locator('.app-bascule').getAttribute('aria-expanded'),'false');
 const nojs=await browser.newPage({javaScriptEnabled:false,viewport:{width:375,height:900}});await login(nojs);
 await nojs.goto(base+'/espace/profil/modifier/');await nojs.locator('#id_first_name').fill('Prénom sans JavaScript');await Promise.all([nojs.waitForURL(base+'/espace/profil/'),nojs.locator('main button[type=submit]').click()]);assert(await nojs.getByText('Prénom sans JavaScript Synthétique',{exact:true}).count());
 await nojs.goto(base+'/espace/annuaire/');await nojs.locator('#q').fill('Autre');await nojs.locator('main button[type=submit]').click();assert(await nojs.getByText('Autre Membre synthétique',{exact:true}).count());
 await nojs.goto(base+`/espace/parcours/${process.env.LIONSMED_EXPERIENCE_ID}/supprimer/`);await nojs.locator('main button[type=submit]').click();assert(!await nojs.getByText('Service associatif',{exact:true}).count());
 assert.equal(errors.length,0,JSON.stringify(errors));fs.writeFileSync('/tmp/lionsmed-lot2-responsive.json',JSON.stringify(results,null,2));console.log(JSON.stringify({responsive_checks:results.length,js_errors:errors.length,keyboard:true,no_js_profile_search_delete:true}));await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
