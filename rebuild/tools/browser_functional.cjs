const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('assert');
(async () => {
  const browser = await chromium.launch({executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox']});
  const base = process.env.LIONSMED_BROWSER_URL;
  const sessions = process.env.LIONSMED_VISUAL_SESSIONS.split(',');
  const routes = [
    [0, '/espace/satisfaction/gestion/', 'satisfaction-create'],
    [0, `/espace/satisfaction/gestion/${process.env.LIONSMED_VISUAL_PERIOD}/resultats/`, 'results'],
    [0, `/espace/satisfaction/gestion/${process.env.LIONSMED_VISUAL_PERIOD}/modifier/`, 'axes'],
    [1, '/espace/cotisations/gestion/', 'dues'],
    [1, '/espace/', 'treasurer-dashboard'],
    [2, '/espace/profil/modifier/', 'phone'],
    [2, '/espace/satisfaction/', 'respond'],
    [2, '/contact/', 'contact'],
    [2, '/candidature/', 'application'],
  ];
  let checks = 0;
  for (const [session, path, name] of routes) {
    const context = await browser.newContext({reducedMotion: 'reduce'});
    await context.addCookies([{name: process.env.LIONSMED_VISUAL_COOKIE, value: sessions[session], url: base}]);
    const page = await context.newPage();
    for (const [width, height] of [[1440,900],[390,844],[430,932]]) {
      await page.setViewportSize({width,height});
      const response = await page.goto(base+path);
      assert.equal(response.status(), 200, path);
      assert.equal(new URL(page.url()).pathname, path, 'Unexpected redirect');
      await page.evaluate(() => document.fonts.ready);
      if (name === 'satisfaction-create') {
        const draft = page.locator('#axis-draft');
        await draft.fill('Organisation');
        await page.locator('[data-axis-add]').click();
        await draft.fill('Communication');
        await draft.press('Enter');
        assert.equal(await page.locator('[data-axis-source]').inputValue(), 'Organisation\nCommunication');
        await page.locator('[data-axis-list] [data-action="up"]').nth(1).click();
        assert.equal(await page.locator('[data-axis-source]').inputValue(), 'Communication\nOrganisation');
      }
      if (name === 'phone') {
        await page.locator('[data-portrait-editor]:visible').waitFor();
        await page.locator('#portrait-zoom').fill('2');
        assert.equal(await page.locator('#id_photo_zoom').inputValue(), '2');
        await page.locator('#portrait-y').fill('25');
        assert.equal(await page.locator('#id_photo_y').inputValue(), '25');
        await page.locator('[data-portrait-reset]').click();
        assert.equal(await page.locator('#id_photo_zoom').inputValue(), '1');
      }
      const result = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        h1: document.querySelectorAll('h1').length,
        unlabeled: [...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e => !e.labels.length && !e.getAttribute('aria-label')).length,
      }));
      assert(!result.overflow, `Overflow ${name} ${width}`);
      assert.equal(result.h1, 1, name);
      assert.equal(result.unlabeled, 0, name);
      await page.evaluate(() => document.activeElement?.blur());
      await page.screenshot({path: `/tmp/lionsmed-functional-${name}-${width}.png`, fullPage: true});
      checks++;
    }
    if (name === 'phone') {
      const input = page.locator('[data-phone]');
      await input.fill('22AA4455');
      assert.equal(await input.inputValue(), '224455');
    }
    await context.close();
  }
  console.log(JSON.stringify({responsive_checks: checks, widths: [1440,390,430], phone_numeric: true}));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
