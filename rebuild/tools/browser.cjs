const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('assert'), fs=require('fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({reducedMotion:'reduce'}), base=process.env.LIONSMED_BROWSER_URL;
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const results=[];
 async function check(path,width){
  await page.setViewportSize({width,height:900});await page.goto(base+path);await page.evaluate(()=>document.fonts.ready);
  const d=await page.evaluate(()=>{
   const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
   return {overflow:document.documentElement.scrollWidth>innerWidth,h1:document.querySelectorAll('h1').length,
    unnamed:[...document.querySelectorAll('button,a[href],input:not([type=hidden])')].filter(e=>visible(e)&&!e.textContent.trim()&&!e.labels?.length&&!e.getAttribute('aria-label')).map(e=>e.outerHTML.slice(0,80)),
    short:[...document.querySelectorAll('input:not([type=checkbox]):not([type=hidden])')].filter(e=>visible(e)&&e.getBoundingClientRect().height<44).map(e=>e.id),
    motion:[...document.querySelectorAll('*')].some(e=>parseFloat(getComputedStyle(e).animationDuration)>.01||parseFloat(getComputedStyle(e).transitionDuration)>.01),
    robots:document.querySelector('meta[name=robots]')?.content};
  });results.push({path,width,...d});
  assert(!d.overflow,`Overflow ${path} ${width}`);assert.equal(d.h1,1);assert.equal(d.unnamed.length,0,JSON.stringify(d.unnamed));assert.equal(d.short.length,0);assert(!d.motion);assert(d.robots.includes('noindex'));
  if([375,1440].includes(width))await page.screenshot({path:`/tmp/lionsmed-lot1-${path.replaceAll('/','_')||'home'}-${width}.png`,fullPage:true});
 }
 for(const w of [1440,1280,1024,768,430,375])for(const path of ['/','/connexion/','/mot-de-passe-oublie/'])await check(path,w);
 await page.goto(base+'/connexion/');await page.locator('.nav-burger').click();await page.keyboard.press('Escape');assert.equal(await page.locator('.nav-burger').getAttribute('aria-expanded'),'false');
 await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'contenu');
 await page.locator('#id_username').fill(process.env.LIONSMED_BROWSER_EMAIL);await page.locator('#id_password').fill(process.env.LIONSMED_BROWSER_PASSWORD);
 await page.locator('[data-oeil]').click();assert.equal(await page.locator('#id_password').getAttribute('type'),'text');await page.locator('[data-oeil]').click();
 await Promise.all([page.waitForURL(url=>url.pathname==='/espace/'),page.locator('button[type=submit]').click()]);
 for(const w of [1440,1280,1024,768,430,375])for(const path of ['/espace/','/espace/mot-de-passe/'])await check(path,w);
 await page.goto(base+'/espace/');await page.locator('.app-bascule').click();assert.equal(await page.locator('.app-bascule').getAttribute('aria-expanded'),'true');
 await page.locator('.app-nav a').last().focus();await page.keyboard.press('Tab');assert(await page.locator('.app-bascule').evaluate(e=>e===document.activeElement));await page.keyboard.press('Escape');assert.equal(await page.locator('.app-bascule').getAttribute('aria-expanded'),'false');
 await page.locator('.shell-account summary').click();await Promise.all([page.waitForURL(base+'/connexion/'),page.locator('button[type=submit]').click()]);
 const nojs=await browser.newPage({javaScriptEnabled:false,viewport:{width:375,height:900}});
 await nojs.goto(base+'/connexion/');await nojs.locator('#id_username').fill(process.env.LIONSMED_BROWSER_EMAIL);await nojs.locator('#id_password').fill(process.env.LIONSMED_BROWSER_PASSWORD);
 await Promise.all([nojs.waitForURL(base+'/espace/'),nojs.locator('button[type=submit]').click()]);assert(await nojs.locator('.app-nav a').first().isVisible());
 assert.equal(errors.length,0,JSON.stringify(errors));fs.writeFileSync('/tmp/lionsmed-lot1-responsive.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify({responsive_checks:results.length,js_errors:errors.length,keyboard:true,no_js_login:true}));await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
