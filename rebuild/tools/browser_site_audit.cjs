// Audit d'affichage de tout le site, lancé par apps/core/tests/test_site_audit_browser.py sur un
// serveur de test jetable. Pour chaque profil, parcourt toutes les pages atteignables par les
// liens (lecture seule), sur ordinateur et sur mobile, puis quelques états que les liens
// n'atteignent pas : erreurs de formulaire, fenêtres du calendrier, message de succès,
// réinitialisation de mot de passe. Les mesures sont dans site_audit_measure.cjs.
// Sortie : un résumé JSON, et un code de retour non nul si un constat bloquant subsiste.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs'), os = require('os'), path = require('path');
const { measure, layout } = require('./site_audit_measure.cjs');

const base = process.env.LIONSMED_BROWSER_URL, cookieName = process.env.LIONSMED_AUDIT_COOKIE;
const sessions = JSON.parse(process.env.LIONSMED_AUDIT_SESSIONS);        // { profil: cookie de session | null }
const extras = JSON.parse(process.env.LIONSMED_AUDIT_EXTRA || '{}');     // pages sans lien entrant, par profil
const out = process.env.LIONSMED_AUDIT_OUT || path.join(os.tmpdir(), 'lionsmed-site-audit');
const shots = process.env.LIONSMED_AUDIT_SHOTS === '1';
const DESKTOP = { width: 1366, height: 768 }, MOBILE = { width: 390, height: 844 };
const SKIP = /(deconnexion|\.ics|telecharger|visualiser|\/photo\/|^\/admin|sitemap\.xml|robots\.txt|images-publiques|^\/static\/|\/qr\/|regenerer|\/supprimer\/$)/;
// Un constat de l'un de ces types fait échouer le contrôle ; les autres sont seulement rapportés
// (pastilles du calendrier volontairement denses, liens de pied de page du site public…).
const BLOCKING = ['débordement horizontal', 'nombre de h1', 'saut de niveau de titre', 'contraste texte', 'contour de champ peu contrasté',
  'contrôle sans nom', 'image cassée', 'entrée de menu sans icône', 'icône sur le texte d’un champ', 'bouton à l’apparence navigateur par défaut',
  'lien en erreur', 'erreur console', 'police de titre différente'];

const pattern = p => p.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g, ':id').replace(/\/\d+(?=\/)/g, '/:n')
  .replace(/^\/(nos-actions|evenements|membres)\/[^/:]+\/$/, '/$1/:slug/').replace(/^\/reinitialiser\/.*/, '/reinitialiser/:jeton/');
const findings = new Map();
const note = (type, detail, where) => { const key = type + '|' + detail; if (!findings.has(key)) findings.set(key, { type, detail, where: new Set() }); findings.get(key).where.add(where); };
const visited = new Set(), fonts = new Map();
let visits = 0;

function record(d, l, where, { privateArea }) {
  if (d.overflowX > 0) note('débordement horizontal', d.overflowX + ' px', where);
  if (d.h1 !== 1) note('nombre de h1', String(d.h1), where);
  d.headingSkips.forEach(x => note('saut de niveau de titre', x, where));
  d.contrast.forEach(x => note('contraste texte', `${x.el} « ${x.text.slice(0, 34)} » ${x.ratio}:1 (min ${x.need})`, where));
  d.nonText.forEach(x => note('contour de champ peu contrasté', `${x.el} ${x.ratio}:1`, where));
  d.escape.forEach(x => note('élément hors de son conteneur', x, where));
  d.clipped.forEach(x => note('texte tronqué', x, where));
  d.small.forEach(x => note('cible < 44 px', x, where));
  d.unnamed.forEach(x => note('contrôle sans nom', x, where));
  d.brokenImages.forEach(x => note('image cassée', x.slice(0, 80), where));
  if (!l) return;
  l.navNoIcon.forEach(x => note('entrée de menu sans icône', x, where));
  l.stuck.forEach(x => note('contrôles collés', x, where));
  l.iconOverInput.forEach(x => note('icône sur le texte d’un champ', x, where));
  l.overlap.forEach(x => note('textes qui se chevauchent', x, where));
  l.emptyCards.forEach(x => note('carte en grande partie vide', x, where));
  l.rawButtons.forEach(x => note('bouton à l’apparence navigateur par défaut', x, where));
  if (privateArea && l.h1) { if (!fonts.has(l.h1.font)) fonts.set(l.h1.font, where); }
}

async function shoot(page, root, name) {
  if (!shots) return;
  await page.evaluate(() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); });
  const box = await page.locator(root).first().boundingBox(); if (!box) return; const vp = page.viewportSize();
  const clip = { x: Math.max(0, box.x), y: Math.max(0, box.y), width: Math.min(box.width, vp.width - Math.max(0, box.x)), height: Math.min(box.height, 2200) };
  await page.screenshot({ path: path.join(out, name.replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_|_$/g, '') + '.png'), fullPage: true, clip });
}

async function open(browser, role, theme, viewport) {
  const context = await browser.newContext({ colorScheme: theme, reducedMotion: 'reduce', viewport: viewport || DESKTOP });
  if (sessions[role]) await context.addCookies([{ name: cookieName, value: sessions[role], url: base }]);
  const page = await context.newPage(); page.auditWhere = role;
  page.on('pageerror', e => note('erreur console', 'JS : ' + e.message.slice(0, 120), page.auditWhere));
  page.on('console', m => { if (m.type() === 'error' && !/ERR_NAME_NOT_RESOLVED|status of 40[0-9]/.test(m.text())) note('erreur console', m.text().slice(0, 120), page.auditWhere); });
  return { context, page };
}

// Mesure la page affichée sur ordinateur puis sur mobile (thème clair), ou sur ordinateur seul.
async function audit(page, where, { root, privateArea, mobile, shotName }) {
  await page.waitForLoadState('load'); await page.evaluate(() => document.fonts.ready);
  record(await page.evaluate(measure, { root }), await page.evaluate(layout), where + ' ordinateur', { privateArea });
  if (shotName) await shoot(page, root, shotName + '-ordinateur');
  if (!mobile) return;
  await page.setViewportSize(MOBILE); await page.waitForTimeout(120);
  record(await page.evaluate(measure, { root }), await page.evaluate(layout), where + ' mobile', { privateArea });
  if (shotName) await shoot(page, root, shotName + '-mobile');
  await page.setViewportSize(DESKTOP);
}

async function crawl(browser, role, theme) {
  const { context, page } = await open(browser, role, theme);
  const start = sessions[role] ? '/espace/' : '/';
  const queue = [{ url: start, from: '(départ)' }]; const seen = new Set([pattern(start)]);
  for (const url of extras[role] || []) if (!seen.has(pattern(url))) { seen.add(pattern(url)); queue.push({ url, from: '(liste)' }); }
  while (queue.length) {
    const { url, from } = queue.shift(); const pat = pattern(url); page.auditWhere = `${pat} [${role}]`;
    // Une page de la liste peut porter des paramètres (vues Semaine et Jour du calendrier).
    const urlPath = url.split('?')[0], query = url.includes('?') ? url.slice(url.indexOf('?')) : '';
    let response;
    try { response = await page.goto(base + url, { waitUntil: 'load', timeout: 30000 }); }
    catch (e) { if (!/RESPONSE_CODE_FAILURE/.test(e.message)) note('lien en erreur', `${pat} : ${e.message.split('\n')[0].slice(0, 70)}`, `${role}, depuis ${from}`); await page.goto('about:blank').catch(() => {}); continue; }
    const status = response ? response.status() : 0; const finalPath = new URL(page.url()).pathname;
    if (!(response.headers()['content-type'] || '').includes('text/html')) continue;
    if (status !== 200 && status !== 405 && url !== '/page-inexistante/') { note('lien en erreur', `${pat} → ${status}`, `${role}, depuis ${from}`); continue; }
    if (finalPath !== urlPath && /^\/connexion\//.test(finalPath) && urlPath !== '/connexion/') { note('lien en erreur', `${pat} → connexion`, `${role}, depuis ${from}`); continue; }
    for (const href of await page.evaluate(() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href')))) {
      let p; try { const u = new URL(href, base); if (u.origin !== new URL(base).origin) continue; p = u.pathname; } catch (e) { continue; }
      if (SKIP.test(p) || seen.has(pattern(p))) continue; seen.add(pattern(p)); queue.push({ url: p, from: pat });
    }
    if (status !== 200 && url !== '/page-inexistante/') continue;
    const privateArea = finalPath.startsWith('/espace'); const final = pattern(finalPath) + query;
    const first = !visited.has(final) || final === '/espace/'; visited.add(final); visits++;
    await audit(page, `${final} [${role}${theme === 'dark' ? ', sombre' : ''}]`, { root: privateArea ? 'main' : 'body', privateArea, mobile: theme === 'light',
      shotName: first && theme === 'light' ? (final === '/espace/' ? role : 'page') + final : null });
  }
  await context.close();
}

// États que le parcours des liens n'atteint pas.
async function states(browser) {
  const submitEmpty = async (page, url, where) => {
    await page.goto(base + url, { waitUntil: 'load' });
    const found = await page.evaluate(() => { const scope = document.querySelector('main') || document.body;
      const form = [...scope.querySelectorAll('form')].find(f => (f.getAttribute('method') || '').toLowerCase() === 'post' && f.querySelector('input:not([type=hidden]),textarea,select') && f.querySelector('[type=submit]'));
      if (!form) return false; form.noValidate = true; form.querySelectorAll('input[type=text],input[type=email],input[type=password],textarea').forEach(e => { e.value = ''; });
      form.querySelector('[type=submit]').setAttribute('data-audit-submit', ''); return true; });
    if (!found) return;
    await Promise.all([page.waitForLoadState('load'), page.locator('[data-audit-submit]').click()]); await page.waitForTimeout(150);
    page.auditWhere = where; const privateArea = new URL(page.url()).pathname.startsWith('/espace');
    await audit(page, where, { root: privateArea ? 'main' : 'body', privateArea, mobile: true, shotName: where }); visits++;
  };
  if (sessions.president) {
    const { context, page } = await open(browser, 'president', 'light');
    for (const url of ['/espace/profil/modifier/', '/espace/parcours/ajouter/', '/espace/gestion/membres/ajouter/', '/espace/gestion/mandats/ajouter/', '/espace/documents/deposer/',
      '/espace/votes/nouveau/', '/espace/notifications/gestion/envoyer/', '/espace/satisfaction/gestion/', '/espace/contenu/action/ajouter/', '/espace/mot-de-passe/'])
      await submitEmpty(page, url, `erreurs de formulaire ${url}`);
    // Fenêtres du calendrier.
    await page.goto(base + '/espace/calendrier/', { waitUntil: 'load' });
    for (const [label, opener] of [['ajout', '[data-open-add]'], ['événement', '.cal-chip, .cal-aside__link']]) {
      const trigger = page.locator(opener).first(); if (!await trigger.count()) continue;
      await trigger.click(); const dialog = page.locator('dialog[open]').first(); await dialog.waitFor({ timeout: 5000 }).catch(() => {});
      if (!await dialog.count()) { note('lien en erreur', `fenêtre « ${label} » du calendrier non ouverte`, 'president'); continue; }
      page.auditWhere = `fenêtre du calendrier (${label})`;
      record(await page.evaluate(measure, { root: 'dialog[open]' }), null, page.auditWhere + ' ordinateur', { privateArea: false });
      await shoot(page, 'dialog[open]', 'fenetre-calendrier-' + label); visits++;
      await page.keyboard.press('Escape'); await page.waitForTimeout(100);
    }
    // Message de succès après un enregistrement (feuille de présence).
    if (extras.presenceSheet) {
      await page.goto(base + extras.presenceSheet, { waitUntil: 'load' });
      await Promise.all([page.waitForLoadState('load'), page.locator('.presence-ligne__form [type=submit]').first().click()]); await page.waitForTimeout(150);
      if (!await page.locator('.alert--success').count()) note('lien en erreur', 'pas de message de succès après enregistrement d’une présence', 'president');
      await audit(page, 'message de succès (feuille de présence)', { root: 'main', privateArea: true, mobile: true, shotName: 'message-de-succes' }); visits++;
    }
    await context.close();
  }
  const { context, page } = await open(browser, 'anonyme', 'light');
  for (const url of ['/connexion/', '/contact/', '/candidature/', '/mot-de-passe-oublie/']) await submitEmpty(page, url, `erreurs de formulaire ${url}`);
  if (extras.passwordReset) { await page.goto(base + extras.passwordReset, { waitUntil: 'load' }); await audit(page, 'réinitialisation du mot de passe', { root: 'body', privateArea: false, mobile: true, shotName: 'reinitialisation' }); visits++; }
  await context.close();
  // Étape de vérification de la double authentification : session en attente de code, sans compte connecté.
  if (extras.mfaSession) {
    const pending = await browser.newContext({ colorScheme: 'light', reducedMotion: 'reduce', viewport: DESKTOP });
    await pending.addCookies([{ name: cookieName, value: extras.mfaSession, url: base }]); const verify = await pending.newPage(); verify.auditWhere = 'double authentification';
    const response = await verify.goto(base + '/connexion/verification/', { waitUntil: 'load' });
    if (response.status() !== 200 || !new URL(verify.url()).pathname.includes('verification')) note('lien en erreur', 'étape de vérification inaccessible', 'double authentification');
    else { await audit(verify, 'vérification de la double authentification', { root: 'body', privateArea: false, mobile: true, shotName: 'double-authentification' }); visits++; }
    await pending.close();
  }
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  const roles = Object.keys(sessions);
  for (const role of roles) await crawl(browser, role, 'light');
  for (const role of ['president', 'anonyme'].filter(r => roles.includes(r))) await crawl(browser, role, 'dark');
  await states(browser);
  await browser.close();
  if (fonts.size > 1) note('police de titre différente', [...fonts.keys()].join(' / '), [...fonts.values()].join(' ; '));
  const list = [...findings.values()].map(f => ({ type: f.type, detail: f.detail, count: f.where.size, where: [...f.where].slice(0, 4) }));
  const byType = {}; list.forEach(f => { byType[f.type] = (byType[f.type] || 0) + 1; });
  const blocking = list.filter(f => BLOCKING.includes(f.type));
  fs.writeFileSync(path.join(out, 'site-audit.json'), JSON.stringify({ visits, pages: [...visited].sort(), byType, findings: list }, null, 1));
  console.log(JSON.stringify({ visites: visits, pages_distinctes: visited.size, profils: roles.length, constats_par_type: byType, bloquants: blocking.length, rapport: path.join(out, 'site-audit.json') }));
  blocking.slice(0, 25).forEach(f => console.error(`BLOQUANT ${f.type} : ${f.detail} ↳ ${f.where.join(' ; ')}`));
  process.exit(blocking.length ? 1 : 0);
})().catch(e => { console.error(e.stack || e.message); process.exit(2); });
