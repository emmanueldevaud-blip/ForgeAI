// Banc de test ciblé : déplacement / redimensionnement des clips
// (correction info.clip dans editorTimeline.js). Temporaire — supprimé après exécution.
import { chromium } from 'playwright';

let failures = 0;
const check = (label, cond, extra = '') => {
  if (cond) console.log(`  ok - ${label}`);
  else {
    failures++;
    console.log(`  FAIL - ${label} ${extra}`);
  }
};

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1920, height: 1080 },
  colorScheme: 'dark',
});
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text());
});

await page.goto('http://127.0.0.1:8931/layout_test.html', { waitUntil: 'load' });
await page.waitForFunction('window.__ready === true');
await page.waitForTimeout(400);

const st = () =>
  page.evaluate(() => {
    const s = window.__view.state;
    const find = (id) => {
      for (const tr of s.design.timeline.tracks) {
        const c = (tr.clips || []).find((c) => c.id === id);
        if (c) {
          return {
            trackId: tr.id,
            trackLocked: !!tr.locked,
            start: c.start,
            duration: c.duration,
            locked: !!c.locked,
          };
        }
      }
      return null;
    };
    return {
      v: find('clip-v1'),
      a: find('clip-a1'),
      selectedId: s.selectedId,
      undo: s.undoStack.length,
      redo: s.redoStack.length,
      zoom: window.__view.timeline._zoom,
    };
  });

const box = (id) =>
  page.evaluate((cid) => {
    const el = document.querySelector(`[data-clip-id="${cid}"]`);
    const r = el.getBoundingClientRect();
    const handle = el.querySelector('[data-clip-resize]');
    const hr = handle.getBoundingClientRect();
    return {
      x: r.x, y: r.y, w: r.width, h: r.height,
      cx: r.x + r.width / 2, cy: r.y + r.height / 2, right: r.right,
      handleCx: hr.x + hr.width / 2, handleCy: hr.y + hr.height / 2,
      handleRight: hr.x + hr.width, handleW: hr.width,
      handleCount: el.querySelectorAll('[data-clip-resize]').length,
    };
  }, id);

const styleOf = (id) =>
  page.evaluate((cid) => {
    const el = document.querySelector(`[data-clip-id="${cid}"]`);
    return { left: el.style.left, width: el.style.width };
  }, id);

const click = (id) =>
  page.evaluate((cid) => {
    const el = document.querySelector(`[data-clip-id="${cid}"]`);
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, id).then((p) => page.mouse.click(p.x, p.y));

const undoBtn = async () => page.click('[data-ed-undo]');
const redoBtn = async () => page.click('[data-ed-redo]');

// ---------------------------------------------------------------------------
console.log('\n== T1 : sélection d’un clip');
{
  await click('clip-a1');
  const s = await st();
  check('selectedId = clip-a1', s.selectedId === 'clip-a1', s.selectedId);
  const n = await page.evaluate(
    () => document.querySelectorAll('.ed-timeline-clip.is-selected').length
  );
  check('classe is-selected appliquée (1)', n === 1, `n=${n}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T2 : déplacement horizontal + transaction unique');
{
  const b0 = await st();
  const bx = await box('clip-v1');
  await page.mouse.move(bx.cx, bx.cy);
  await page.mouse.down();
  await page.mouse.move(bx.cx + 40, bx.cy, { steps: 3 });
  const mid = await st();
  await page.mouse.move(bx.cx + 80, bx.cy, { steps: 3 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();

  check('aucune entrée d historique pendant le glissement', mid.undo === b0.undo,
    `avant=${b0.undo} pendant=${mid.undo}`);
  check('start = 20 s (0 + 80px/4)', Math.abs(a.v.start - 20) < 0.01, `start=${a.v.start}`);
  check('clip resté sur sa piste', a.v.trackId === 'tr-video-1', a.v.trackId);
  check('une SEULE transaction (undo +1)', a.undo === b0.undo + 1,
    `avant=${b0.undo} apres=${a.undo}`);
  check('redo vidé', a.redo === 0, `redo=${a.redo}`);
  const vis = await styleOf('clip-v1');
  check('position visuelle = start × zoom', Math.abs(parseFloat(vis.left) - 80) < 0.01,
    `left=${vis.left}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T3 : undo / redo après déplacement');
{
  const before = await st(); // start=20
  await undoBtn();
  let s = await st();
  check('undo restaure start = 0', Math.abs(s.v.start - 0) < 0.01, `start=${s.v.start}`);
  check('undo consomme 1 entrée', s.undo === before.undo - 1, `undo=${s.undo}`);
  await redoBtn();
  s = await st();
  check('redo rétablit start = 20', Math.abs(s.v.start - 20) < 0.01, `start=${s.v.start}`);
  await undoBtn();
  s = await st();
  check('retour au départ (start = 0)', Math.abs(s.v.start - 0) < 0.01, `start=${s.v.start}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T4 : déplacement vertical (inter-pistes)');
{
  const b0 = await st();
  const bx = await box('clip-v1');
  const rowH = await page.evaluate(() => {
    const rows = document.querySelectorAll('.ed-timeline-row');
    return rows.length > 1
      ? rows[1].getBoundingClientRect().y - rows[0].getBoundingClientRect().y
      : 41;
  });
  await page.mouse.move(bx.cx, bx.cy);
  await page.mouse.down();
  await page.mouse.move(bx.cx + 40, bx.cy + rowH, { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();

  check(
    'le clip ne change pas de piste (déplacement inter-pistes non implémenté)',
    a.v.trackId === 'tr-video-1',
    `piste=${a.v.trackId}`
  );
  check('la composante verticale est ignorée (start = 10 s)', Math.abs(a.v.start - 10) < 0.01,
    `start=${a.v.start}`);
  check('une seule transaction', a.undo === b0.undo + 1, `avant=${b0.undo} apres=${a.undo}`);
  const sel = await st();
  check('sélection conservée sur le clip', sel.selectedId === 'clip-v1', sel.selectedId);
  await undoBtn();
  const r = await st();
  check('undo restaure start = 0', Math.abs(r.v.start - 0) < 0.01, `start=${r.v.start}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T5 : redimensionnement bord droit (agrandir)');
{
  const b0 = await st(); // dur=12
  const bx = await box('clip-v1');
  await page.mouse.move(bx.handleCx, bx.handleCy);
  await page.mouse.down();
  await page.mouse.move(bx.handleCx + 40, bx.handleCy, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  check('duration = 22 s (12 + 40px/4)', Math.abs(a.v.duration - 22) < 0.01,
    `duration=${a.v.duration}`);
  check('une seule transaction', a.undo === b0.undo + 1, `avant=${b0.undo} apres=${a.undo}`);
  const vis = await styleOf('clip-v1');
  check('largeur visuelle = duration × zoom', Math.abs(parseFloat(vis.width) - 88) < 0.01,
    `width=${vis.width}`);
  await undoBtn();
  const r = await st();
  check('undo restaure duration = 12', Math.abs(r.v.duration - 12) < 0.01,
    `duration=${r.v.duration}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T6 : redimensionnement bord droit (réduire)');
{
  const b0 = await st(); // dur=12
  const bx = await box('clip-v1');
  await page.mouse.move(bx.handleCx, bx.handleCy);
  await page.mouse.down();
  await page.mouse.move(bx.handleCx - 40, bx.handleCy, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  check('duration = 2 s (12 − 40px/4)', Math.abs(a.v.duration - 2) < 0.01,
    `duration=${a.v.duration}`);
  check('une seule transaction', a.undo === b0.undo + 1, `avant=${b0.undo} apres=${a.undo}`);
  await undoBtn();
  const r = await st();
  check('undo restaure duration = 12', Math.abs(r.v.duration - 12) < 0.01,
    `duration=${r.v.duration}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T7 : limite temporelle — durée minimale 0');
{
  const b0 = await st();
  const bx = await box('clip-v1');
  await page.mouse.move(bx.handleCx, bx.handleCy);
  await page.mouse.down();
  await page.mouse.move(bx.handleCx - 2000, bx.handleCy, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  check('duration bornée à 0 (jamais négative)', a.v.duration === 0, `duration=${a.v.duration}`);
  check('transaction unique malgré le dépassement', a.undo === b0.undo + 1,
    `avant=${b0.undo} apres=${a.undo}`);
  await undoBtn();
  const r = await st();
  check('undo restaure duration = 12', Math.abs(r.v.duration - 12) < 0.01,
    `duration=${r.v.duration}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T8 : limite temporelle — start minimal 0');
{
  const b0 = await st(); // start=0
  const bx = await box('clip-v1');
  await page.mouse.move(bx.cx, bx.cy);
  await page.mouse.down();
  await page.mouse.move(bx.cx - 2000, bx.cy, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  check('start borné à 0 (jamais négatif)', a.v.start >= 0, `start=${a.v.start}`);
  check('aucune transaction (déplacement borné sans effet)', a.undo === b0.undo, `avant=${b0.undo} apres=${a.undo}`);
  check('start = 0 après borne', Math.abs(a.v.start - 0) < 0.01, `start=${a.v.start}`);

  // Borne avec effet réel : start>0 puis sur-drag jusqu'à 0 → exactement 1 entrée.
  const m = await box('clip-v1');
  await page.mouse.move(m.cx, m.cy);
  await page.mouse.down();
  await page.mouse.move(m.cx + 40, m.cy, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const p = await st();
  check('start avance (+40px / zoom 4 = +10)', Math.abs(p.v.start - 10) < 0.01, `start=${p.v.start}`);
  const b1 = p.undo;
  const b2 = await box('clip-v1');
  await page.mouse.move(b2.cx, b2.cy);
  await page.mouse.down();
  await page.mouse.move(b2.cx - 4000, b2.cy, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const c = await st();
  check('sur-drag borné à 0', Math.abs(c.v.start - 0) < 0.01, `start=${c.v.start}`);
  check('transaction unique (clamp avec effet)', c.undo === b1 + 1, `avant=${b1} apres=${c.undo}`);
  await undoBtn();
  const r = await st();
  check('undo restaure start = 10', Math.abs(r.v.start - 10) < 0.01, `start=${r.v.start}`);
  await undoBtn(); // remise à 0 pour la suite
  check('2e undo restaure start = 0', Math.abs((await st()).v.start - 0) < 0.01);
}

// ---------------------------------------------------------------------------
console.log('\n== T9 : poignées de redimensionnement');
{
  const bx = await box('clip-v1');
  check('une seule poignée par clip', bx.handleCount === 1, `count=${bx.handleCount}`);
  check(
    'poignée sur le bord droit uniquement (pas de poignée de bord gauche)',
    bx.handleW === 8 && Math.abs(bx.handleCx - (bx.right - 4)) < 2 && bx.handleCx > bx.cx,
    `handleCx=${Math.round(bx.handleCx)} right=${Math.round(bx.right)}`
  );
}

// ---------------------------------------------------------------------------
console.log('\n== T10 : propriété locked du clip');
{
  await page.evaluate(() => {
    const s = window.__view.state;
    for (const tr of s.design.timeline.tracks) {
      const c = (tr.clips || []).find((c) => c.id === 'clip-a1');
      if (c) c.locked = true;
    }
  });
  const b0 = await st();
  const bx = await box('clip-a1');
  await page.mouse.move(bx.cx, bx.cy);
  await page.mouse.down();
  await page.mouse.move(bx.cx + 80, bx.cy, { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  check('clip verrouillé : start inchangé', a.a.start === b0.a.start,
    `avant=${b0.a.start} apres=${a.a.start}`);
  check('clip verrouillé : aucune transaction', a.undo === b0.undo,
    `avant=${b0.undo} apres=${a.undo}`);
  // déverrouiller
  await page.evaluate(() => {
    const s = window.__view.state;
    for (const tr of s.design.timeline.tracks) {
      const c = (tr.clips || []).find((c) => c.id === 'clip-a1');
      if (c) c.locked = false;
    }
  });
}

// ---------------------------------------------------------------------------
console.log('\n== T11 : piste verrouillée (observation du comportement actuel)');
{
  const b0 = await st();
  await page.evaluate(() => window.__view.state.setTrackLocked('tr-video-1', true));
  const locked = await st();
  const bx = await box('clip-v1');
  await page.mouse.move(bx.cx, bx.cy);
  await page.mouse.down();
  await page.mouse.move(bx.cx + 40, bx.cy, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  // Comportement constaté dans le code actuel : seul clip.locked est vérifié.
  check(
    'piste verrouillée : comportement actuel = déplacement encore autorisé (constat)',
    a.v.start === 10 && a.v.trackLocked === true,
    `start=${a.v.start} trackLocked=${a.v.trackLocked}`
  );
  await page.evaluate(() => window.__view.state.setTrackLocked('tr-video-1', false));
  // remettre l état d origine
  await undoBtn(); // annule le déplacement
  await undoBtn(); // annule setTrackLocked(false)
  await undoBtn(); // annule setTrackLocked(true)
  const r = await st();
  check(
    'retour à l état initial (start=0, piste non verrouillée)',
    Math.abs(r.v.start - 0) < 0.01 && r.v.trackLocked === false,
    `start=${r.v.start} locked=${r.v.trackLocked}`
  );
}

// ---------------------------------------------------------------------------
console.log('\n== T12 : annulation par Escape');
{
  const b0 = await st();
  const bx = await box('clip-v1');
  await page.mouse.move(bx.cx, bx.cy);
  await page.mouse.down();
  await page.mouse.move(bx.cx + 40, bx.cy, { steps: 3 });
  await page.keyboard.press('Escape');
  await page.mouse.move(bx.cx + 80, bx.cy, { steps: 3 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  // Aucun écouteur Escape dans le code éditeur : le glissement se poursuit et commit.
  check(
    'Escape : comportement actuel = aucun écouteur, le glissement se termine (constat)',
    Math.abs(a.v.start - 20) < 0.01,
    `start=${a.v.start}`
  );
  check('transaction unique malgré Escape', a.undo === b0.undo + 1,
    `avant=${b0.undo} apres=${a.undo}`);
  await undoBtn();
  const r = await st();
  check('undo restaure start = 0', Math.abs(r.v.start - 0) < 0.01, `start=${r.v.start}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T13 : pointercancel');
{
  const b0 = await st();
  const bx = await box('clip-v1');
  await page.mouse.move(bx.cx, bx.cy);
  await page.mouse.down();
  await page.mouse.move(bx.cx + 40, bx.cy, { steps: 3 });
  await page.evaluate(() => window.dispatchEvent(new Event('pointercancel')));
  // Les écouteurs doivent être détachés : ces mouvements ne doivent plus agir.
  await page.mouse.move(bx.cx + 200, bx.cy, { steps: 4 });
  await page.mouse.up();
  await page.waitForTimeout(50);
  const a = await st();
  check(
    'pointercancel : commit immédiat (start = 10 s, glissement interrompu)',
    Math.abs(a.v.start - 10) < 0.01,
    `start=${a.v.start}`
  );
  check('pointercancel : aucune action postérieure (start non altéré)', Math.abs(a.v.start - 10) < 0.01,
    `start=${a.v.start}`);
  check('pointercancel : une seule transaction', a.undo === b0.undo + 1,
    `avant=${b0.undo} apres=${a.undo}`);
  await undoBtn();
  const r = await st();
  check('undo restaure start = 0', Math.abs(r.v.start - 0) < 0.01, `start=${r.v.start}`);
}

// ---------------------------------------------------------------------------
console.log('\n== T14 : clic sans déplacement = aucune transaction');
{
  const b0 = await st();
  await click('clip-v1');
  await page.waitForTimeout(50);
  const a = await st();
  check('aucune entrée d historique', a.undo === b0.undo, `avant=${b0.undo} apres=${a.undo}`);
  check('sélection du clip', a.selectedId === 'clip-v1', a.selectedId);
}

// ---------------------------------------------------------------------------
console.log('\n== T15 : erreurs console / page');
{
  // Le 404 /photos/55/file est un artefact du harnais statique (aucun backend
  // photo) — le média factice tente de se charger dans l aperçu vidéo.
  const unexpected = errors.filter((e) => !/404|Failed to load resource/.test(e));
  const notFound = errors.filter((e) => /404|Failed to load resource/.test(e));
  if (notFound.length) console.log(`  note - artefact harnais ignoré : ${notFound[0]}`);
  check('aucune erreur inattendue (TypeError info.clip corrigé)', unexpected.length === 0,
    unexpected.slice(0, 3).join(' | '));
}

await browser.close();
console.log(failures === 0 ? '\nTOUS LES TESTS PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
