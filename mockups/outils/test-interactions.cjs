const {chromium}=require('/home/besbes/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:375,height:900},reducedMotion:'reduce'});
 const base='http://127.0.0.1:8876/';const results=[];
 async function test(name,fn){try{await fn();results.push({name,ok:true});}catch(e){results.push({name,ok:false,error:e.message});}}
 await test('Menu public : ouverture, boucle Tab, Échap et retour du focus',async()=>{
  await page.goto(base+'accueil.html');await page.locator('.nav-burger').click();assert.equal(await page.locator('.nav-burger').getAttribute('aria-expanded'),'true');
  await page.locator('.nav-mobile a').last().focus();await page.keyboard.press('Tab');assert(await page.locator('.nav-burger').evaluate(e=>e===document.activeElement));
  await page.keyboard.press('Escape');assert.equal(await page.locator('.nav-burger').getAttribute('aria-expanded'),'false');
 });
 await test('Lien d’évitement et focus visible',async()=>{await page.goto(base+'contact.html');await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.className),'skip-link');assert.equal(await page.evaluate(()=>getComputedStyle(document.activeElement).outlineWidth),'3px');await page.keyboard.press('Enter');assert(page.url().endsWith('#contenu'));});
 await test('Filtre public et état sans résultat',async()=>{await page.goto(base+'nos-actions.html');await page.locator('[data-filter]').selectOption('Jeunesse');assert.equal(await page.locator('[data-item]:visible').count(),1);await page.locator('[data-search]').fill('introuvable');assert(await page.locator('[data-empty]').isVisible());});
 await test('Aucune soumission de formulaire',async()=>{await page.goto(base+'contact.html');let requests=[];const onRequest=r=>{if(r.method()==='POST')requests.push(r.url());};page.on('request',onRequest);await page.locator('form button[type="submit"]').click();assert.equal(requests.length,0);assert((await page.locator('form [role="status"]').textContent()).includes('aucune donnée'));page.off('request',onRequest);});
 await test('Afficher et masquer le mot de passe',async()=>{await page.goto(base+'connexion.html');const eye=page.locator('[data-oeil]').first();await eye.click();assert.equal(await eye.getAttribute('aria-pressed'),'true');await eye.click();assert.equal(await eye.getAttribute('aria-pressed'),'false');});
 await test('Invité : aucun vote et aucun annuaire',async()=>{await page.goto(base+'espace/votes.html?role=INVITE');assert(await page.locator('[data-access-denied]').isVisible());assert.equal(await page.locator('.app-nav a[href*="votes.html"]:visible').count(),0);assert.equal(await page.locator('input[name="bulletin"]:visible').count(),0);});
 await test('Bureau : aucune publication publique',async()=>{await page.goto(base+'espace/contenu-public.html?role=BUREAU');assert(await page.locator('[data-access-denied]').isVisible());assert.equal(await page.locator('form:visible').count(),0);});
 await test('Président autorisé à publier, Directeur en supervision',async()=>{await page.goto(base+'espace/contenu-public.html?role=PRESIDENT');assert.equal(await page.locator('form:visible').count(),1);await page.locator('[data-role-selector]').selectOption('DIRECTEUR');assert(await page.locator('[data-access-denied]').isVisible());});
 await test('Sélecteur de rôle et navigation le conservent',async()=>{await page.goto(base+'espace/tableau-de-bord.html?role=PRESIDENT');assert((await page.locator('a[href^="responsables.html"]').last().getAttribute('href')).includes('role=PRESIDENT'));});
 await test('Votes : choix multiple, blanc exclusif, confirmation, verrouillage et clôture',async()=>{
  await page.goto(base+'espace/votes.html?role=MEMBRE');assert.equal(await page.locator('a[href*="vote-resultats"]:visible').count(),0);
  await page.locator('[data-ballot-type]').selectOption('multiple');await page.locator('input[value="a"]').check();await page.locator('input[value="b"]').check();assert.equal(await page.locator('input[name="bulletin"]:checked').count(),2);
  await page.locator('[data-dialog-open]').click();assert((await page.locator('[data-vote-summary]').textContent()).includes('Proposition B'));await page.keyboard.press('Escape');
  await page.locator('input[value="blanc"]').check();assert.equal(await page.locator('input[name="bulletin"]:checked').count(),1);
  await page.locator('#etat-vote').selectOption('vote');assert.equal(await page.locator('input[name="bulletin"]:visible').count(),0);assert(await page.locator('button:disabled').isVisible());
  await page.locator('#etat-vote').selectOption('clos');assert(await page.locator('a[href*="vote-resultats"]:visible').isVisible());
 });
 await test('Satisfaction : sélection et quatre états',async()=>{await page.goto(base+'espace/satisfaction.html');await page.locator('#satisfaction-4').check();assert(await page.locator('#satisfaction-4').isChecked());for(const state of ['confirme','repondu','ferme','ouvert']){await page.locator('#etat-satisfaction').selectOption(state);assert(await page.locator('[data-state="'+state+'"]').isVisible());}});
 await test('Notifications : lu et non lu',async()=>{await page.goto(base+'espace/notifications.html');const b=page.locator('[data-mark-read]').first();await b.click();assert.equal(await page.locator('[data-read-state]').first().textContent(),'Lue');await b.click();assert.equal(await page.locator('[data-read-state]').first().textContent(),'Non lue');});
 await test('Profil : e-mail non modifiable et aperçu photo local',async()=>{await page.goto(base+'espace/profil.html');assert(await page.locator('#email').getAttribute('readonly')!==null);await page.locator('[data-photo-preview]').setInputFiles('mockups/assets/images/emblem-256.png');assert(await page.locator('[data-photo-image]').isVisible());});
 await test('Calendrier ICS : téléchargement local',async()=>{await page.goto(base+'espace/calendrier.html');const [dl]=await Promise.all([page.waitForEvent('download'),page.getByText('Exporter ICS',{exact:true}).click()]);assert.equal(dl.suggestedFilename(),'calendrier-demonstration.ics');});
 await test('Menu privé : ouverture et Échap',async()=>{await page.goto(base+'espace/tableau-de-bord.html');await page.locator('.app-bascule').click();assert(await page.locator('.app-nav').evaluate(e=>e.classList.contains('est-ouverte')));await page.keyboard.press('Escape');assert.equal(await page.locator('.app-bascule').getAttribute('aria-expanded'),'false');});
 fs.writeFileSync('mockups/validation/interactions.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));await browser.close();
})();
