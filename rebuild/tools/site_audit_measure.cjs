// Mesures d'affichage exécutées dans la page par tools/browser_site_audit.cjs. Tout est mesuré
// sur le rendu réel (contrastes, débordements, cibles tactiles, mise en page), rien n'est estimé.
function measure(opts) {
  opts = opts || {};
  const main = document.querySelector(opts.root || 'main') || document.body;
  const SCALE = [0, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 160];
  const out = { overflowX: 0, h1: 0, headingSkips: [], contrast: [], unknownBg: 0, texts: 0, nonText: [], escape: [], clipped: [],
    small: [], unnamed: [], spacing: [], asideFit: null, brokenImages: [] };

  const visible = e => { if (!e.getClientRects().length || (e.checkVisibility && !e.checkVisibility())) return false; const cs = getComputedStyle(e); return cs.visibility !== 'hidden' && cs.display !== 'none'; };
  const clippedAway = e => { for (let n = e; n && n !== document.documentElement; n = n.parentElement) { if (n.classList && n.classList.contains('visually-hidden')) return true; if (n.hasAttribute && n.hasAttribute('hidden')) return true; } return false; };
  const sig = e => { const cls = (e.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 3).join('.'); return e.tagName.toLowerCase() + (e.tagName === 'INPUT' ? '[' + (e.getAttribute('type') || 'text') + ']' : '') + (cls ? '.' + cls : ''); };
  const snippet = e => (e.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 48);

  const parse = str => {
    let m = /rgba?\(([^)]+)\)/.exec(str);
    if (m) { const p = m[1].split(/[,\s/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; }
    m = /color\(srgb\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)(?:\s*\/\s*([\d.e-]+))?\)/.exec(str);
    if (m) return { r: m[1] * 255, g: m[2] * 255, b: m[3] * 255, a: m[4] === undefined ? 1 : +m[4] };
    return null;
  };
  const over = (top, bottom) => { const a = top.a + bottom.a * (1 - top.a); if (!a) return { r: 0, g: 0, b: 0, a: 0 }; return { r: (top.r * top.a + bottom.r * bottom.a * (1 - top.a)) / a, g: (top.g * top.a + bottom.g * bottom.a * (1 - top.a)) / a, b: (top.b * top.a + bottom.b * bottom.a * (1 - top.a)) / a, a }; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  // Fond effectif : empilement des fonds des ancêtres ; une image de fond rend la mesure inconnue.
  const backgroundOf = el => {
    const layers = []; let unknown = false;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage !== 'none' && !/^(select|input|textarea)$/i.test(n.tagName)) unknown = true;
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; }
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
    return { color: base, unknown };
  };
  const opacityOf = el => { let o = 1; for (let n = el; n && n.nodeType === 1; n = n.parentElement) o *= parseFloat(getComputedStyle(n).opacity); return o; };

  out.overflowX = document.documentElement.scrollWidth - innerWidth;
  out.h1 = document.querySelectorAll('h1').length;
  let last = 0;
  main.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(h => { if (!visible(h) || clippedAway(h)) return; const level = +h.tagName[1]; if (last && level > last + 1) out.headingSkips.push('h' + last + ' → h' + level + ' « ' + snippet(h) + ' »'); last = level; });

  // Contraste du texte (WCAG 1.4.3) : 4,5:1, ou 3:1 pour un grand texte.
  const seen = new Set();
  main.querySelectorAll('*').forEach(el => {
    if (/^(svg|path|circle|script|style|noscript|iframe|option|br)$/i.test(el.tagName) || el.closest('svg')) return;
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
    if (!visible(el) || clippedAway(el) || el.closest(':disabled')) return;
    out.texts++;
    const cs = getComputedStyle(el); const bg = backgroundOf(el);
    if (bg.unknown) { out.unknownBg++; return; }
    const fg = parse(cs.color); if (!fg) return;
    fg.a *= opacityOf(el);
    const shown = over(fg, bg.color); const r = ratio(shown, bg.color);
    const size = parseFloat(cs.fontSize); const bold = parseInt(cs.fontWeight, 10) >= 700;
    const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    if (r < need - 0.005) { const key = sig(el) + hex(shown) + hex(bg.color); if (!seen.has(key)) { seen.add(key); out.contrast.push({ el: sig(el), text: snippet(el), ratio: +r.toFixed(2), need, fg: hex(shown), bg: hex(bg.color), size }); } }
  });
  main.querySelectorAll('input[placeholder],textarea[placeholder]').forEach(el => {
    if (!visible(el) || clippedAway(el) || el.value) return;
    const ps = getComputedStyle(el, '::placeholder'); const fg = parse(ps.color); if (!fg) return;
    fg.a *= parseFloat(ps.opacity || '1') * opacityOf(el);
    const bg = backgroundOf(el).color; const r = ratio(over(fg, bg), bg);
    if (r < 4.495) out.contrast.push({ el: sig(el) + '::placeholder', text: el.getAttribute('placeholder'), ratio: +r.toFixed(2), need: 4.5, fg: hex(over(fg, bg)), bg: hex(bg), size: parseFloat(ps.fontSize) });
  });

  // Contraste non textuel (WCAG 1.4.11) : contour des champs de saisie, 3:1.
  main.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),textarea,select').forEach(el => {
    if (!visible(el) || clippedAway(el)) return;
    const cs = getComputedStyle(el); const border = parse(cs.borderTopColor); if (!border || parseFloat(cs.borderTopWidth) === 0) return;
    const outside = backgroundOf(el.parentElement).color; const r = ratio(over(border, outside), outside);
    if (r < 2.995) out.nonText.push({ el: sig(el), ratio: +r.toFixed(2), border: hex(over(border, outside)), bg: hex(outside) });
  });

  // Débordements : hors de la colonne de contenu, ou hors de sa carte ; textes tronqués.
  const mainRect = main.getBoundingClientRect();
  main.querySelectorAll('.workspace-panel,.com-campagne,.form-errors,.alert,.card,.carte-action,section').forEach(box => {
    if (!visible(box)) return; const b = box.getBoundingClientRect();
    box.querySelectorAll('*').forEach(el => { if (!visible(el) || clippedAway(el) || el.closest('svg')) return; const r = el.getBoundingClientRect(); if (!r.width) return;
      if (r.right > b.right + 1 || r.left < b.left - 1) { const scroller = el.parentElement.closest('.com-membres__liste,.com-verif-liste,pre,.tableau-cadre'); if (scroller && box.contains(scroller)) return; out.escape.push(sig(el) + ' sort de ' + sig(box) + ' de ' + Math.round(Math.max(r.right - b.right, b.left - r.left)) + ' px'); } });
  });
  out.escape = [...new Set(out.escape)].slice(0, 12);
  main.querySelectorAll('h1,h2,h3,p,span,a,button,label,dt,dd,li,td,th,strong').forEach(el => {
    if (!visible(el) || clippedAway(el)) return; const cs = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 1 && cs.overflowX !== 'visible' && cs.display !== 'inline') out.clipped.push(sig(el) + ' « ' + snippet(el) + ' »');
  });
  out.clipped = [...new Set(out.clipped)].slice(0, 12);

  // Cibles tactiles (44 px) et contrôles sans nom accessible.
  const named = e => (e.textContent || '').trim() || (e.labels && e.labels.length) || e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.getAttribute('title');
  main.querySelectorAll('button,a[href],input:not([type=hidden]),select,textarea,summary').forEach(el => {
    if (!visible(el) || clippedAway(el)) return;
    if (!named(el)) out.unnamed.push(sig(el));
    if (el.closest('.app-note,.champ__aide,.form-errors,.alert,p')) { if (el.tagName === 'A') return; }
    const target = el.matches('input[type=checkbox],input[type=radio]') && el.closest('label') ? el.closest('label') : el;
    const r = target.getBoundingClientRect();
    if (r.height < 43.5 || (r.width < 43.5 && !el.matches('input,textarea,select'))) out.small.push(sig(el) + ' ' + Math.round(r.width) + '×' + Math.round(r.height) + ' « ' + snippet(el) + ' »');
  });
  out.small = [...new Set(out.small)].slice(0, 12);

  // Échelle d'espacement du système de design, sur les composants de la page auditée.
  if (opts.spacingPrefix) {
    const re = new RegExp('(^|\\s)(' + opts.spacingPrefix + ')');
    main.querySelectorAll('*').forEach(el => {
      if (!re.test(el.getAttribute('class') || '') || !visible(el)) return; const cs = getComputedStyle(el);
      ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'marginTop', 'marginBottom', 'rowGap', 'columnGap'].forEach(prop => {
        const raw = cs[prop]; if (raw === 'normal' || raw === 'auto') return; const v = Math.round(parseFloat(raw) * 100) / 100;
        if (!SCALE.includes(Math.abs(v)) && v !== -1) out.spacing.push(sig(el) + ' ' + prop + ' = ' + v + ' px');
      });
    });
    out.spacing = [...new Set(out.spacing)].slice(0, 12);
  }

  // Colonne collante : doit tenir entière dans la fenêtre, sinon son bas est inatteignable.
  const aside = document.querySelector('.communication-layout__aside');
  if (aside && getComputedStyle(aside).position === 'sticky') { const top = parseFloat(getComputedStyle(aside).top) || 0; const h = aside.getBoundingClientRect().height; out.asideFit = { height: Math.round(h), top, viewport: innerHeight, fits: h + top <= innerHeight }; }

  document.querySelectorAll('img').forEach(img => { if (img.complete && !img.naturalWidth && visible(img)) out.brokenImages.push(img.getAttribute('src') || '(sans src)'); });
  return out;
};

// Heuristiques de mise en page exécutées dans la page : elles visent les défauts qu'un
// simple contrôle de débordement ne voit pas (icône manquante, éléments collés, loupe sur
// le texte, textes qui se chevauchent, carte presque vide, titre dans une autre police).
function layout() {
  const main = document.querySelector('main') || document.body;
  const out = { title: document.title, navNoIcon: [], h1: null, stuck: [], iconOverInput: [], overlap: [], emptyCards: [], missingAlt: [], mainHeight: Math.round(main.getBoundingClientRect().height) };
  const visible = e => { if (!e.getClientRects().length || (e.checkVisibility && !e.checkVisibility())) return false; const cs = getComputedStyle(e); return cs.visibility !== 'hidden' && cs.display !== 'none' && parseFloat(cs.opacity) > 0.05; };
  const hidden = e => { for (let n = e; n && n !== document.documentElement; n = n.parentElement) { if (n.classList && n.classList.contains('visually-hidden')) return true; if (n.hasAttribute && n.hasAttribute('hidden')) return true; } return false; };
  const sig = e => { const cls = (e.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.'); return e.tagName.toLowerCase() + (cls ? '.' + cls : ''); };
  const snip = e => (e.textContent || e.value || e.getAttribute('placeholder') || '').trim().replace(/\s+/g, ' ').slice(0, 30);

  document.querySelectorAll('.app-nav__liste > li > a.app-nav__lien, .app-nav__liste > li > details > summary.app-nav__lien').forEach(a => { if (!a.querySelector('svg')) out.navNoIcon.push(a.textContent.trim()); });

  const h1 = document.querySelector('h1');
  if (h1 && visible(h1)) { const cs = getComputedStyle(h1); const r = h1.getBoundingClientRect(); const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
    out.h1 = { text: snip(h1), font: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(), size: Math.round(parseFloat(cs.fontSize)), lines: Math.max(1, Math.round(r.height / lh)), width: Math.round(r.width), room: Math.round(h1.parentElement.getBoundingClientRect().width) }; }

  // Contrôles collés verticalement (moins de 6 px entre deux champs/boutons superposés).
  const controls = [...main.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]),select,textarea,button,a.btn')]
    .filter(e => visible(e) && !hidden(e)).map(e => ({ e, r: e.getBoundingClientRect() })).filter(c => c.r.width > 20 && c.r.height > 16);
  controls.forEach(a => {
    let best = null;
    controls.forEach(b => { if (a === b || a.e.contains(b.e) || b.e.contains(a.e)) return; const ov = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      if (ov < 0.3 * Math.min(a.r.width, b.r.width)) return; const gap = b.r.top - a.r.bottom; if (gap < -1 || gap > 200) return; if (!best || gap < best.gap) best = { b, gap }; });
    if (best && best.gap < 6) out.stuck.push(`${sig(a.e)} « ${snip(a.e)} » ↓ ${Math.round(best.gap)} px ↓ ${sig(best.b.e)} « ${snip(best.b.e)} »`);
  });
  out.stuck = [...new Set(out.stuck)].slice(0, 10);

  // Icône posée sur le début du texte d'un champ.
  main.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),textarea').forEach(input => {
    if (!visible(input) || hidden(input)) return; const r = input.getBoundingClientRect(); const pad = parseFloat(getComputedStyle(input).paddingLeft) || 0; const start = r.left + pad;
    const scope = input.parentElement && input.parentElement.parentElement ? input.parentElement.parentElement : input.parentElement;
    scope.querySelectorAll('svg').forEach(svg => { if (!visible(svg) || svg.closest('button,a,label')) return; const s = svg.getBoundingClientRect();
      const inside = s.left < r.right && s.right > r.left && s.top < r.bottom && s.bottom > r.top; if (!inside) return;
      if (s.right > start + 1 && s.left < start + 14) out.iconOverInput.push(`${sig(input)} « ${snip(input)} » : icône de ${Math.round(s.left - r.left)} à ${Math.round(s.right - r.left)} px, texte à partir de ${Math.round(pad)} px`); });
  });

  // Textes qui se chevauchent (boîtes de lignes réelles, pas les blocs).
  const boxes = []; const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT); const range = document.createRange(); let node;
  while ((node = walker.nextNode()) && boxes.length < 2600) { if (!node.textContent.trim()) continue; const el = node.parentElement; if (!el || /^(SCRIPT|STYLE|NOSCRIPT|OPTION|TEXTAREA)$/.test(el.tagName) || el.closest('svg') || !visible(el) || hidden(el)) continue;
    range.selectNodeContents(node); for (const r of range.getClientRects()) if (r.width > 2 && r.height > 4) boxes.push({ el, r }); }
  main.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,textarea').forEach(el => { if (visible(el) && !hidden(el)) boxes.push({ el, r: el.getBoundingClientRect(), box: true }); });
  // Ce qui est rogné par une zone de défilement n'est pas à l'écran : on l'écarte.
  const clippedOut = b => { for (let n = b.el.parentElement; n && n !== main; n = n.parentElement) { const cs = getComputedStyle(n); if (/(auto|scroll|hidden)/.test(cs.overflowY + cs.overflowX)) { const c = n.getBoundingClientRect(); if (b.r.bottom <= c.top + 1 || b.r.top >= c.bottom - 1 || b.r.right <= c.left + 1 || b.r.left >= c.right - 1) return true; } } return false; };
  for (let i = boxes.length - 1; i >= 0; i--) if (clippedOut(boxes[i])) boxes.splice(i, 1);
  boxes.sort((a, b) => a.r.top - b.r.top); const seen = new Set();
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length && boxes[j].r.top < boxes[i].r.bottom; j++) {
    const a = boxes[i], b = boxes[j]; if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el) || (a.box && b.box)) continue;
    const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left), h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
    if (w < 3 || h < 4 || h < 0.35 * Math.min(a.r.height, b.r.height)) continue;
    const sa = getComputedStyle(a.el), sb = getComputedStyle(b.el); if (sa.position === 'sticky' || sb.position === 'sticky' || a.el.closest('thead') || b.el.closest('thead')) continue;
    const key = sig(a.el) + '|' + sig(b.el); if (seen.has(key)) continue; seen.add(key);
    out.overlap.push(`${sig(a.el)} « ${snip(a.el)} » ⟂ ${sig(b.el)} « ${snip(b.el)} » (${Math.round(w)}×${Math.round(h)} px)`);
  }
  out.overlap = out.overlap.slice(0, 10);

  // Carte dont plus de 40 % (et plus de 120 px) est vide.
  main.querySelectorAll('.workspace-panel,.carte-info,.carte-action,.card,.editorial-card').forEach(card => {
    if (!visible(card)) return; const c = card.getBoundingClientRect(); if (c.height < 200) return; let bottom = c.top;
    card.querySelectorAll('*').forEach(el => { if (!visible(el) || hidden(el)) return; const leaf = /^(IMG|SVG|INPUT|SELECT|TEXTAREA|BUTTON|IFRAME|CANVAS|METER|PROGRESS)$/i.test(el.tagName) || [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()); if (leaf) bottom = Math.max(bottom, el.getBoundingClientRect().bottom); });
    const blank = c.bottom - (parseFloat(getComputedStyle(card).paddingBottom) || 0) - bottom;
    if (blank > 120 && blank > 0.4 * c.height) out.emptyCards.push(`${sig(card)} « ${snip(card.querySelector('h2,h3') || card)} » : ${Math.round(blank)} px vides sur ${Math.round(c.height)}`);
  });

  main.querySelectorAll('img').forEach(img => { if (!img.hasAttribute('alt')) out.missingAlt.push(img.getAttribute('src') || ''); });
  // Boutons qui gardent l'apparence par défaut du navigateur (fond gris, bordure en relief).
  out.rawButtons = [];
  document.querySelectorAll('button').forEach(b => { const cs = getComputedStyle(b); const face = cs.backgroundColor === 'rgb(239, 239, 239)' || cs.backgroundColor === 'rgb(107, 107, 107)';
    const relief = cs.borderTopStyle === 'outset' && parseFloat(cs.borderTopWidth) > 0; if (!face && !relief) return;
    out.rawButtons.push(sig(b) + (face ? ' fond' : '') + (relief ? ' bordure' : '') + (visible(b) ? '' : ' (masqué pour l’instant)')); });
  out.rawButtons = [...new Set(out.rawButtons)];
  return out;
};

module.exports = { measure, layout };
