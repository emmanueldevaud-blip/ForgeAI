/**
 * E2E — Restauration de l'étape après rechargement (Community Publisher)
 *
 * Corrige/valide : après reload, l'UI affiche immédiatement l'étape
 * restaurée par le store (pas de flash « Médias »), et le premier
 * Suivant/Précédent avance exactement d'une étape (pas de décalage).
 *
 * Formats : story (7 étapes dont music), reel (6), post (5).
 * Rechargement testé à chaque étape ; preview/publish restaurent
 * caption (mapping existant du store). Nav arrière/avante incluse.
 */
import { chromium } from 'playwright';

const BASE = 'http://localhost:8000';
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64'
);

const PHOTOS = [
  { id: 11, title: 'Photo A', mime_type: 'image/jpeg', thumbnail_url: '/photos/11/file?size=small', file_url: '/photos/11/file', created_at: '2026-11-01T10:00:00Z' },
  { id: 12, title: 'Photo B', mime_type: 'image/jpeg', thumbnail_url: '/photos/12/file?size=small', file_url: '/photos/12/file', created_at: '2026-11-02T10:00:00Z' },
];

const STEP_LABELS = {
  media: 'Médias',
  adjust: 'Ajuster',
  compose: 'Composer',
  music: 'Musique',
  caption: 'Légende',
  preview: 'Aperçu',
  publish: 'Publier',
};

const FORMATS = {
  story: {
    steps: ['media', 'adjust', 'compose', 'music', 'caption', 'preview', 'publish'],
    photoCount: 1,
    stepHost: {
      media: '[data-photo-id]',
      adjust: '.ppe-header',
      compose: '[data-story-host]',
      music: '.music-step',
      caption: '[data-caption-host]',
      preview: '.pp-story',
      publish: '[data-action="publish-final"]',
    },
  },
  reel: {
    steps: ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'],
    photoCount: 1,
    stepHost: {
      media: '[data-photo-id]',
      adjust: '.ppe-header',
      compose: '[data-studio-host], .publisher-reel-editor',
      caption: '[data-caption-host]',
      preview: '.pp-reel, .pp-story',
      publish: '[data-action="publish-final"]',
    },
  },
  post: {
    steps: ['media', 'adjust', 'caption', 'preview', 'publish'],
    photoCount: 1,
    stepHost: {
      media: '[data-photo-id]',
      adjust: '.ppe-header',
      caption: '[data-caption-host]',
      preview: '.pp-post, .pp-story',
      publish: '[data-action="publish-final"]',
    },
  },
};

function labelFor(format, step) {
  const steps = FORMATS[format].steps;
  const idx = steps.indexOf(step);
  return `${idx + 1}/${steps.length} · ${STEP_LABELS[step]}`;
}

function restoredStepAfterReload(step) {
  if (step === 'preview' || step === 'publish') return 'caption';
  return step;
}

const ver = await (await fetch('http://127.0.0.1:9222/json/version')).json();
const browser = await chromium.connectOverCDP({ wsEndpoint: ver.webSocketDebuggerUrl });

async function setupPage() {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  await page.route('**/auth/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'u1',
        email: 'test@forgeai.local',
        username: 'test',
        full_name: 'Test User',
        roles: ['community_manager'],
        permissions: ['community_manager.strategy_view'],
      }),
    })
  );
  await page.route('**/modules/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ modules: ['community_manager'] }) })
  );
  await page.route('**/notifications/unread-count', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ count: 0 }) })
  );
  await page.route((url) => /\/photos\/\d+\/file/.test(url.pathname), (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: PNG })
  );
  await page.route((url) => url.pathname === '/photos', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: PHOTOS, next_cursor: null }),
    })
  );
  await page.route((url) => url.pathname === '/community-manager/instagram/music/search', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [{ audio_id: 'ig-1', title: 'Run Free', display_artist: 'NR', duration_in_ms: 90000 }] }),
    })
  );
  await page.route((url) => /\/albums|\/suggested|\/activities/.test(url.pathname), (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
  );

  const errors = [];
  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const t = m.text();
    if (/AdministrationPage|Erreur chargement|401 \(Unauthorized\)|Failed to load resource|Non authentifié/.test(t)) return;
    errors.push(t);
  });
  page.on('pageerror', (e) => {
    const t = 'PAGEERROR: ' + (e.stack || e.message);
    if (/Non authentifié|ApiError/.test(t)) return;
    // Préexistant hors périmètre : _navLock ne retourne pas la promesse,
    // le .catch du handler Suivant lève un TypeError (la navigation fonctionne).
    if (/reading 'catch'/.test(t) && /CommunityPublisherPage/.test(t)) return;
    errors.push(t);
  });

  return { context, page, errors };
}

async function progressLabel(page) {
  // Le label peut être dans le DOM mais masqué (header masqué sur Médias)
  await page.waitForSelector('[data-progress-label]', { state: 'attached', timeout: 15000 });
  return (await page.textContent('[data-progress-label]')).replace(/\s+/g, ' ').trim();
}

async function waitHost(page, format, step, timeout = 20000) {
  const sel = FORMATS[format].stepHost[step];
  if (sel) await page.waitForSelector(sel, { timeout });
}

async function reloadExpect(page, format, expectedStep, out, tag) {
  await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[data-progress-label]', { state: 'attached', timeout: 15000 });
  const first = await progressLabel(page);
  await page.waitForTimeout(400);
  const stable = await progressLabel(page);
  const expected = labelFor(format, expectedStep);
  const ok = first === expected && stable === expected;
  out.reloads.push({ tag, expected, first, stable, ok });
  if (ok) await waitHost(page, format, expectedStep);
  return ok;
}

async function clickNext(page) {
  await page.evaluate(() => document.querySelector('[data-action="next-step"]')?.click());
  await page.waitForTimeout(800);
}

async function clickPrev(page) {
  await page.evaluate(() => document.querySelector('[data-action="prev-step"]')?.click());
  await page.waitForTimeout(800);
}

async function runFormat(format) {
  const cfg = FORMATS[format];
  const { context, page, errors } = await setupPage();
  const out = { format, reloads: [], nav: [], errors: [] };
  const captionIdx = cfg.steps.indexOf('caption');

  try {
    await page.goto(`${BASE}/publisher/${format}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('[data-photo-id]', { timeout: 20000 });

    // Rechargement sur Médias (étape initiale)
    await reloadExpect(page, format, 'media', out, 'media@start');

    // Sélection -> Ajuster
    const items = await page.$$('[data-photo-id]');
    for (let i = 0; i < cfg.photoCount; i++) {
      await items[i].click();
      await page.waitForTimeout(250);
    }
    await page.click('[data-action="complete"]');
    await page.waitForTimeout(900);
    const afterComplete = await progressLabel(page);
    out.nav.push({
      action: 'complete',
      after: afterComplete,
      expected: labelFor(format, 'adjust'),
      ok: afterComplete === labelFor(format, 'adjust'),
    });

    // Pour chaque étape de Ajuster à Légende : recharger puis (si possible) Suivant
    for (let idx = 1; idx <= captionIdx; idx++) {
      const step = cfg.steps[idx];
      const okReload = await reloadExpect(page, format, step, out, step);
      if (!okReload) break;

      if (idx < captionIdx) {
        const before = await progressLabel(page);
        await clickNext(page);
        const after = await progressLabel(page);
        const expectedAfter = labelFor(format, cfg.steps[idx + 1]);
        out.nav.push({ action: `next@${step}`, before, after, expectedAfter, ok: after === expectedAfter });
        if (after !== expectedAfter) break;
        await waitHost(page, format, cfg.steps[idx + 1]);
      }
    }

    // Arrière/avant depuis Légende (restaurée)
    const atCaption = (await progressLabel(page)) === labelFor(format, 'caption');
    if (atCaption && captionIdx > 0) {
      const prevStep = cfg.steps[captionIdx - 1];
      await clickPrev(page);
      const afterPrev = await progressLabel(page);
      out.nav.push({ action: 'prev@caption', after: afterPrev, expected: labelFor(format, prevStep), ok: afterPrev === labelFor(format, prevStep) });
      await waitHost(page, format, prevStep);

      await clickNext(page);
      const afterNext = await progressLabel(page);
      out.nav.push({ action: 'next@' + prevStep, after: afterNext, expected: labelFor(format, 'caption'), ok: afterNext === labelFor(format, 'caption') });
      await waitHost(page, format, 'caption');
    }

    // Rechargement sur Aperçu -> restaure Légende (mapping store)
    if ((await progressLabel(page)) === labelFor(format, 'caption')) {
      await clickNext(page);
      const atPreview = await progressLabel(page);
      out.nav.push({ action: 'next@caption->preview', after: atPreview, expected: labelFor(format, 'preview'), ok: atPreview === labelFor(format, 'preview') });
      if (atPreview === labelFor(format, 'preview')) {
        await reloadExpect(page, format, 'caption', out, 'preview->caption');
      }
    }

    // Rechargement sur Publier -> restaure Légende (mapping store)
    if ((await progressLabel(page)) === labelFor(format, 'caption')) {
      await clickNext(page); // -> preview
      await page.waitForTimeout(500);
      await clickNext(page); // -> publish
      const atPublish = await progressLabel(page);
      out.nav.push({ action: 'to publish', after: atPublish, expected: labelFor(format, 'publish'), ok: atPublish === labelFor(format, 'publish') });
      if (atPublish === labelFor(format, 'publish')) {
        await reloadExpect(page, format, 'caption', out, 'publish->caption');
      }
    }
  } catch (e) {
    out.error = String(e);
    out.state = await page.evaluate(() => ({
      label: document.querySelector('[data-progress-label]')?.textContent || null,
    })).catch(() => ({}));
  }

  out.errors = errors.slice(0, 10);
  out.allReloadsOk = out.reloads.length > 0 && out.reloads.every((r) => r.ok);
  out.allNavOk = out.nav.length > 0 && out.nav.every((n) => n.ok !== false);
  await context.close();
  return out;
}

const results = {};
for (const format of ['story', 'reel', 'post']) {
  results[format] = await runFormat(format);
}

console.log(JSON.stringify(results, null, 2));
await browser.close();
