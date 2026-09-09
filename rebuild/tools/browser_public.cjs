const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert'),fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({reducedMotion:'reduce'}),base=process.env.LIONSMED_BROWSER_URL,errors=[],results=[];
 page.on('pageerror',e=>errors.push(e.message));
 const paths=['/','/notre-club/','/nos-actions/','/nos-actions/synthetic/','/actualites/','/actualites/synthetic/','/evenements/','/evenements/synthetic/','/rejoindre/','/candidature/','/contact/','/mentions-legales/','/confidentialite/','/plan-du-site/'];
 async function check(path,width,index){
  await page.setViewportSize({width,height:900});const response=await page.goto(base+path);assert.equal(response.status(),200,path);await page.evaluate(()=>document.fonts.ready);
  const state=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,h1:document.querySelectorAll('h1').length,missingAlt:[...document.images].filter(e=>!e.hasAttribute('alt')).length,unnamed:[...document.querySelectorAll('input:not([type=hidden]),textarea,select')].filter(e=>e.getClientRects().length&&!e.labels?.length&&!e.getAttribute('aria-label')).length,broken:[...document.images].filter(e=>e.complete&&!e.naturalWidth).map(e=>e.src)}));
  assert(!state.overflow,`Overflow ${path} ${width}`);assert.equal(state.h1,1,path);assert.equal(state.missingAlt,0);assert.equal(state.unnamed,0,path);assert.equal(state.broken.length,0,JSON.stringify(state));results.push({path,width,...state});
  if([375,1440].includes(width))await page.screenshot({path:`/tmp/lionsmed-lot3-page${index}-${width}.png`,fullPage:true});
 }
 for(const width of [1440,1280,1024,768,430,375])for(let i=0;i<paths.length;i++)await check(paths[i],width,i);
 await page.goto(base+'/contact/');await page.locator('.nav-burger').click();assert.equal(await page.locator('.nav-burger').getAttribute('aria-expanded'),'true');await page.keyboard.press('Escape');assert.equal(await page.locator('.nav-burger').getAttribute('aria-expanded'),'false');await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'contenu');
 await page.locator('form').evaluate(e=>e.noValidate=true);await page.locator('main button[type=submit]').click();assert(await page.locator('[aria-invalid=true]').count());
 await page.goto(base+'/connexion/');await page.locator('#id_username').fill(process.env.LIONSMED_BROWSER_EMAIL);await page.locator('#id_password').fill(process.env.LIONSMED_BROWSER_PASSWORD);await Promise.all([page.waitForURL(base+'/espace/'),page.locator('button[type=submit]').click()]);
 for(const width of [1440,1280,1024,768,430,375])for(const [i,path] of ['/espace/contenu/','/espace/contenu/action/ajouter/','/espace/contenu/news/ajouter/','/espace/contenu/event/ajouter/'].entries())await check(path,width,14+i);
 const nojs=await browser.newPage({javaScriptEnabled:false,viewport:{width:375,height:900}});await nojs.goto(base+'/contact/');await nojs.locator('#id_name').fill('Test navigateur');await nojs.locator('#id_email').fill('browser@example.invalid');await nojs.locator('#id_subject').selectOption('GENERAL');await nojs.locator('#id_message').fill('Message synthétique navigateur');await nojs.locator('main button[type=submit]').click();assert(nojs.url().endsWith('/contact/recu/'));
 assert.equal(errors.length,0,JSON.stringify(errors));fs.writeFileSync('/tmp/lionsmed-lot3-responsive.json',JSON.stringify(results,null,2));console.log(JSON.stringify({responsive_checks:results.length,js_errors:errors.length,keyboard:true,no_js_contact:true}));await browser.close();
})().catch(e=>{console.error(e.stack);process.exit(1)});
