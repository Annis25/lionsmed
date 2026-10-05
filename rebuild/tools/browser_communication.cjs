// QA navigateur de la page Communication (/espace/communication/), lancée par
// apps/communications/tests/test_browser.py sur un serveur de test jetable.
// Vérifie par page, thème et largeur : débordement horizontal, un seul <h1>, contrôles
// nommés, cibles tactiles >= 44 px ; puis le parcours complet (recherche, sélection,
// adresses externes, compteurs, vérification, envoi, relance) avec et sans JavaScript.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('assert'),fs=require('fs'),path=require('path');
const base=process.env.LIONSMED_BROWSER_URL,shots=process.env.LIONSMED_SHOT_DIR||'/tmp';
const WIDTHS=[320,390,768,1280,1440];

async function login(page){
 await page.goto(base+'/connexion/');
 await page.locator('#id_username').fill(process.env.LIONSMED_BROWSER_EMAIL);
 await page.locator('#id_password').fill(process.env.LIONSMED_BROWSER_PASSWORD);
 await Promise.all([page.waitForURL(url=>url.pathname==='/espace/'),page.locator('button[type=submit]').click()]);
}

async function audit(page,label,width){
 await page.waitForLoadState('load');await page.evaluate(()=>document.fonts.ready);
 const d=await page.evaluate(()=>{
  const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
  const main=document.querySelector('main');
  const named=e=>e.textContent.trim()||e.labels?.length||e.getAttribute('aria-label')||e.getAttribute('aria-labelledby');
  // Cible tactile d'une case à cocher = sa ligne <label> entière.
  const target=e=>e.matches('input[type=checkbox]')?(e.closest('label')||e):e;
  const controls=[...main.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea,summary')].filter(visible);
  return {width:innerWidth,overflow:document.documentElement.scrollWidth-innerWidth,h1:document.querySelectorAll('h1').length,
   unnamed:controls.filter(e=>!named(e)).map(e=>e.outerHTML.slice(0,90)),
   small:controls.filter(e=>!e.closest('.app-note,.champ__aide,.form-errors,.alert')).map(e=>({e:target(e),src:e}))
    .filter(({e})=>e.getBoundingClientRect().height<44).map(({src})=>src.outerHTML.slice(0,90)),
   clipped:[...main.querySelectorAll('.com-membre__nom,.com-membre__email,.com-externe span,.com-campagne h2,.btn')].filter(visible)
    .filter(e=>e.scrollWidth>e.clientWidth+1).map(e=>e.textContent.trim().slice(0,40)),
   robots:document.querySelector('meta[name=robots]').content};
 });
 assert.equal(d.width,width,label);
 assert(d.overflow<=0,`Débordement horizontal ${label} (${d.overflow}px)`);
 assert.equal(d.h1,1,`h1 ${label}`);
 assert.deepEqual(d.unnamed,[],`Contrôle sans nom ${label} ${width} : ${JSON.stringify(d.unnamed)}`);
 assert.deepEqual(d.small,[],`Cible < 44 px ${label} ${width} : ${JSON.stringify(d.small)}`);
 assert.deepEqual(d.clipped,[],`Texte tronqué ${label} ${width} : ${JSON.stringify(d.clipped)}`);
 assert(d.robots.includes('noindex'));
}

const text=(page,selector)=>page.locator(selector).innerText();
async function fillMessage(page){
 await page.locator('#id_subject').fill('Réunion mensuelle');
 await page.locator('#id_body').fill('Rendez-vous jeudi à 19 h au siège du club.\nMerci de confirmer votre présence.');
}
async function addExternal(page,email){await page.locator('#externe-saisie').fill(email);await page.locator('[data-email-picker-add]').click();}

(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const errors=[],results=[];
 const detailPath=process.env.LIONSMED_CAMPAIGN_PATH,failedPath=process.env.LIONSMED_FAILED_PATH;

 for(const theme of ['light','dark']){
  const context=await browser.newContext({colorScheme:theme,reducedMotion:'reduce'});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await login(page);
  for(const width of WIDTHS){
   const shot=async name=>{await page.evaluate(()=>{document.activeElement&&document.activeElement.blur();window.scrollTo(0,0)});await page.screenshot({path:path.join(shots,`com-${name}-${theme}-${width}.png`),fullPage:true});};
   await page.setViewportSize({width,height:900});

   // Rédaction, état initial : rien n'est présélectionné.
   await page.goto(base+'/espace/communication/');
   assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),theme);
   assert.equal(await text(page,'[data-summary-total]'),'0');
   assert.equal(await page.locator('[data-member]:checked').count(),0);
   await audit(page,`rédaction ${theme}`,width);

   // Recherche instantanée, sans casse ni accents.
   const total=await page.locator('[data-member-row]').count();
   await page.locator('#recherche-membre').fill('RANIA');
   assert.equal(await page.locator('[data-member-row]:visible').count(),1);
   await page.locator('#recherche-membre').fill('chaabouni@example');
   assert.equal(await page.locator('[data-member-row]:visible').count(),1);
   await page.locator('#recherche-membre').fill('zzzz');
   assert.equal(await page.locator('[data-member-row]:visible').count(),0);
   assert(await page.locator('[data-member-empty]').isVisible());
   if(width===390)await shot('recherche-vide');
   await page.locator('#recherche-membre').fill('rania');
   await page.locator('[data-member-row]:visible label').click();
   assert.equal(await text(page,'[data-summary-total]'),'1');

   // Sélection rapide : tous les éligibles, quel que soit le filtre en cours.
   await page.locator('[data-select=all]').click();
   assert.equal(await page.locator('[data-member]:checked').count(),total);
   assert.equal(await page.locator('#recherche-membre').inputValue(),'');
   assert.equal(await text(page,'[data-summary-internal]'),String(total));
   await page.locator('[data-select=responsibles]').click();
   const responsibles=await page.locator('[data-member][data-responsible]').count();
   assert.equal(await page.locator('[data-member]:checked').count(),responsibles);
   await page.locator('[data-select=none]').click();
   assert.equal(await text(page,'[data-summary-total]'),'0');

   // Adresses externes seules : aucun membre ne s'ajoute implicitement.
   await addExternal(page,'pas-une-adresse');
   assert(await page.locator('[data-email-picker-error]').isVisible());
   if(width===320)await shot('externe-invalide');
   await addExternal(page,'contact@association.example');
   await addExternal(page,'partenaire@example.invalid');
   await addExternal(page,'CONTACT@association.example');
   assert.equal(await page.locator('.com-externe').count(),2);
   assert.equal(await text(page,'[data-summary-internal]'),'0');
   assert.equal(await text(page,'[data-summary-external]'),'2');
   assert.equal(await text(page,'[data-summary-total]'),'2');
   await page.locator('.com-externe button').first().click();
   assert.equal(await text(page,'[data-summary-total]'),'1');
   await addExternal(page,'contact@association.example');

   // Membres + externes ; une adresse externe identique à un membre coché n'est pas recomptée.
   await page.locator('[data-member-row]').filter({hasText:'Anis Besbes'}).locator('label').click();
   await page.locator('[data-member-row]').filter({hasText:'Rania Trabelsi'}).locator('label').click();
   await addExternal(page,'ANIS.besbes@example.invalid');
   assert.equal(await text(page,'[data-summary-internal]'),'2');
   assert.equal(await text(page,'[data-summary-external]'),'2');
   assert.equal(await text(page,'[data-summary-total]'),'4');
   await fillMessage(page);
   await audit(page,`rédaction remplie ${theme}`,width);
   await shot('redaction');

   // Aperçu : rien n'est envoyé, le brouillon reste en place.
   await page.locator('button[value=preview]').click();
   await page.locator('#apercu').waitFor();
   assert.equal(await text(page,'[data-summary-total]'),'4');
   await audit(page,`aperçu ${theme}`,width);

   // Vérification.
   await page.locator('button[value=confirm]').click();
   await page.getByRole('heading',{name:'Votre message est prêt à être envoyé'}).waitFor();
   assert.equal((await text(page,'button[value=send]')).trim(),'Envoyer à 4 destinataires');
   assert(await page.getByText('1 adresse en double ignorée').count());
   await audit(page,`vérification ${theme}`,width);
   await shot('verification');

   // « Modifier » rend le brouillon intact.
   await page.locator('button[value=back]').click();
   await page.locator('.com-externe').first().waitFor();  // liste reconstruite par le script différé
   assert.equal(await page.locator('[data-member]:checked').count(),2);
   assert.equal(await page.locator('.com-externe').count(),3);
   assert.equal(await page.locator('#id_subject').inputValue(),'Réunion mensuelle');
   assert.equal(await text(page,'[data-summary-total]'),'4');

   // Erreurs de formulaire : aucun destinataire, message vide.
   await page.goto(base+'/espace/communication/');
   await page.locator('button[value=confirm]').click();
   await page.locator('.form-errors').waitFor();
   assert(await page.getByText('Sélectionnez au moins un membre ou ajoutez une adresse externe.').count());
   await audit(page,`erreurs ${theme}`,width);
   if([320,1280].includes(width))await shot('erreurs');

   // Historique, suivi par destinataire, état d'échec.
   await page.goto(base+'/espace/communication/historique/');
   await audit(page,`historique ${theme}`,width);
   await shot('historique');
   await page.goto(base+detailPath);
   await audit(page,`suivi ${theme}`,width);
   await shot('suivi');
   await page.goto(base+failedPath);
   await audit(page,`suivi échec ${theme}`,width);
   if([390,1440].includes(width))await shot('suivi-echec');
   results.push({theme,width});
  }
  await context.close();
 }

 // Parcours réel jusqu'à l'envoi, clavier et double clic compris.
 const context=await browser.newContext({viewport:{width:1280,height:900},reducedMotion:'reduce'});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await login(page);
 await page.goto(base+'/espace/communication/');
 await page.locator('#recherche-membre').focus();
 await page.keyboard.type('anis');
 await page.keyboard.press('Enter');
 assert.equal(new URL(page.url()).pathname,'/espace/communication/');  // Entrée ne soumet rien
 await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.keyboard.press('Tab');await page.keyboard.press('Tab');
 assert.equal(await page.evaluate(()=>document.activeElement.matches('[data-member]')),true);
 await page.keyboard.press('Space');
 assert.equal(await text(page,'[data-summary-total]'),'1');
 await page.locator('#externe-saisie').fill('contact@association.example');
 await page.keyboard.press('Enter');
 assert.equal(new URL(page.url()).pathname,'/espace/communication/');
 assert.equal(await text(page,'[data-summary-total]'),'2');
 // Une adresse tapée mais non ajoutée est reprise à la soumission, jamais perdue.
 await page.locator('#externe-saisie').fill('partenaire@example.invalid');
 await fillMessage(page);
 await page.locator('button[value=confirm]').click();
 await page.getByRole('heading',{name:'Votre message est prêt à être envoyé'}).waitFor();
 assert.equal((await text(page,'button[value=send]')).trim(),'Envoyer à 3 destinataires');
 const before=Number(process.env.LIONSMED_CAMPAIGN_COUNT);
 await page.locator('button[value=send]').dblclick();
 await page.waitForURL(url=>/\/espace\/communication\/historique\/[0-9a-f-]{36}\/$/.test(url.pathname));
 assert(await page.getByText('Votre message est dans la file d’envoi pour 3 destinataires.').count());
 assert.equal(await page.locator('.com-suivi__ligne').count(),3);
 assert.equal(await page.locator('.com-suivi__ligne .com-etat--pending').count(),3);
 await page.goto(base+'/espace/communication/historique/');
 assert.equal(await page.locator('.com-campagne').count(),before+1);  // un double clic = une seule campagne
 await page.screenshot({path:path.join(shots,'com-apres-envoi-light-1280.png'),fullPage:true});

 // Relance des échecs depuis le suivi.
 await page.goto(base+failedPath);
 await page.getByRole('button',{name:/Réessayer/}).click();
 await page.getByText(/remis en file d’envoi/).waitFor();
 assert.equal(await page.getByRole('button',{name:/Réessayer/}).count(),0);
 await context.close();

 // Sans JavaScript : cases réelles et zone de texte, même parcours jusqu'à l'envoi.
 const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:900},reducedMotion:'reduce'});
 const plain=await nojs.newPage();
 await login(plain);
 await plain.goto(base+'/espace/communication/');
 assert(await plain.locator('#id_extra_emails').isVisible());
 assert(!await plain.locator('#recherche-membre').isVisible());
 await plain.locator('[data-member-row]').filter({hasText:'Rania Trabelsi'}).locator('input').check();
 await plain.locator('#id_extra_emails').fill('contact@association.example\nautre@example.invalid');
 await fillMessage(plain);
 await plain.screenshot({path:path.join(shots,'com-sans-js-390.png'),fullPage:true});
 await plain.locator('button[value=confirm]').click();
 assert.equal((await plain.locator('button[value=send]').innerText()).trim(),'Envoyer à 3 destinataires');
 await plain.locator('button[value=send]').click();
 await plain.getByRole('heading',{name:'Suivi par destinataire'}).waitFor();
 assert.equal(await plain.locator('.com-suivi__ligne').count(),3);
 await nojs.close();

 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(shots,'com-results.json'),JSON.stringify(results,null,2));
 console.log(JSON.stringify({themes_widths:results.length,js_errors:errors.length,keyboard:true,double_click_single_campaign:true,retry:true,no_js_send:true}));
 await browser.close();
})().catch(e=>{console.error(e.stack||e.message);process.exit(1)});
