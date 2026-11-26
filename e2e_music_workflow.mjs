/**
 * E2E — Séparation Composer / Musique (étape Musique Story)
 *
 * S1 : Story avec musique (recherche, sélection, aperçu, navigation
 *      Composer↔Musique, changement de slide, sauvegarde/restauration,
 *      retrait) + aucun réglage début/durée.
 * S2 : Story sans musique (poursuite possible, aucun affichage en aperçu).
 * S3 : Ancien brouillon avec design.ig_audio (compatibilité lecture).
 * S4 : Non-régression Reel (steps + panneau musique du Reel conservés).
 * S5 : Non-régression Post/Carrousel (steps inchangés, pas d'étape Musique).
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

const TRACKS = [
  { audio_id: 'ig-101', title: 'Run Free', display_artist: 'Neon Runner', duration_in_ms: 92000 },
  { audio_id: 'ig-102', title: 'Trail Heat', display_artist: 'Mountain Beat', duration_in_ms: 78000 },
];

const ver = await (await fetch('http://127.0.0.1:9222/json/version')).json();
const browser = await chromium.connectOverCDP({ wsEndpoint: ver.webSocketDebuggerUrl });

async function setupPage(seedFn) {
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
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: TRACKS }) })
  );
  await page.route((url) => /\/albums|\/suggested|\/activities/.test(url.pathname), (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
  );

  if (seedFn) await page.addInitScript(seedFn);

  const errors = [];
  const httpErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + (e.stack || e.message)));
  page.on('response', (r) => { if (r.status() >= 400) httpErrors.push(`${r.status()} ${r.url()}`); });

  return { context, page, errors, httpErrors };
}

function mediaItem(id, order) {
  return {
    id: `photo_${id}`,
    url: `/photos/${id}/file`,
    thumbnail_url: `/photos/${id}/file?size=small`,
    crop: { x: 0, y: 0, w: 1, h: 1 },
    order,
    type: 'photo',
    source: 'library',
    garminActivityId: null,
  };
}

async function progress(page) {
  return page.evaluate(() => ({
    label: document.querySelector('[data-progress-label]')?.textContent || null,
    segments: Array.from(document.querySelectorAll('[data-progress-track] [data-seg]')).map((el) => el.dataset.seg),
  }));
}

async function readMusic(page) {
  return page.evaluate(() => {
    try {
      const raw = localStorage.getItem('forgeai_publisher_draft');
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      const docs = parsed.draft?.design?.designDocuments || [];
      return {
        music: parsed.draft?.music || null,
        step: parsed.ui?.currentStep,
        docsHaveIgAudio: docs.some((d) => d && d.ig_audio),
        slidesLen: Array.isArray(parsed.draft?.design?.slides) ? parsed.draft.design.slides.length : null,
      };
    } catch (e) { return { error: String(e) }; }
  });
}

async function selectPhotos(page, count) {
  await page.waitForSelector('[data-photo-id]', { timeout: 20000 });
  const items = await page.$$('[data-photo-id]');
  for (let i = 0; i < count; i++) {
    await items[i].click();
    await page.waitForTimeout(300);
  }
  await page.click('[data-action="complete"]');
  await page.waitForSelector('.ppe-header', { timeout: 15000 });
}

async function next(page) {
  await page.evaluate(() => document.querySelector('[data-action="next-step"]')?.click());
  await page.waitForTimeout(700);
}

async function prev(page) {
  await page.evaluate(() => document.querySelector('[data-action="prev-step"]')?.click());
  await page.waitForTimeout(700);
}

async function goToMusic(page) {
  await page.waitForSelector('.music-step', { timeout: 15000 });
}

async function ensureMusicStep(page, visited = []) {
  for (let i = 0; i < 10; i++) {
    const label = String((await progress(page)).label || '');
    visited.push(label);
    if (label.includes('Musique')) return true;
    if (label.includes('Publier') || label.includes('Prévisualisation') || label.includes('Légende')) {
      await prev(page);
    } else if (label.includes('Médias')) {
      // Footer masqué sur l'étape Médias : avancer via le sélecteur
      await page.click('[data-action="complete"]');
      await page.waitForTimeout(800);
    } else {
      await next(page);
    }
  }
  visited.push(String((await progress(page)).label || ''));
  return String((await progress(page)).label || '').includes('Musique');
}

async function searchAndSelect(page, index = 0) {
  await page.click('[data-action="music-open"]');
  await page.waitForSelector('[data-music-panel]:not([hidden])', { timeout: 5000 });
  await page.fill('[data-music-form] input', 'run music');
  await page.click('[data-music-form] button[type="submit"]');
  await page.waitForSelector('[data-music-result]', { timeout: 10000 });
  const results = await page.$$('[data-music-result]');
  await results[index].click();
  await page.waitForTimeout(500);
}

const results = {};

// ================= S1 : Story avec musique =================
{
  const { context, page, errors, httpErrors } = await setupPage(null);
  const out = { name: 'S1 — Story avec musique (parcours complet)' };
  try {
    await page.goto(`${BASE}/publisher/story`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await selectPhotos(page, 2);
    out.progress_adjust = await progress(page);
    await next(page); // adjust -> compose
    await page.waitForSelector('[data-story-host]', { timeout: 15000 });
    await page.waitForTimeout(1200);

    await next(page); // compose -> music
    await goToMusic(page);
    out.progress_music = await progress(page);
    out.empty_state = await page.textContent('[data-music-current]');
    out.no_time_controls = await page.$$eval('.music-step input', (els) => els.every((i) => i.type === 'search'));
    out.no_audio_element = await page.$$eval('.music-step audio, .music-step video', (els) => els.length === 0);

    await searchAndSelect(page, 0);
    out.selection_text = (await page.textContent('[data-music-current]')).replace(/\s+/g, ' ').trim();
    out.music_after_select = await readMusic(page);

    await next(page); // music -> caption
    await page.waitForSelector('[data-caption-host]', { timeout: 10000 });
    await next(page); // caption -> preview
    await page.waitForSelector('.pp-story', { timeout: 10000 });
    out.preview_music = await page.evaluate(() => {
      const row = document.querySelector('.pp-story-music');
      return row ? {
        text: row.textContent.replace(/\s+/g, ' ').trim(),
        hasStatus: !!row.querySelector('.pp-story-music-status'),
      } : null;
    });

    await prev(page); // preview -> caption
    await page.waitForSelector('[data-caption-host]', { timeout: 10000 });
    await prev(page); // caption -> music
    await goToMusic(page);
    out.music_after_back = (await page.textContent('[data-music-current]')).replace(/\s+/g, ' ').trim();

    await prev(page); // music -> compose
    await page.waitForSelector('[data-story-host]', { timeout: 15000 });
    await page.waitForTimeout(1000);
    out.slideCount = await page.$$eval('[data-slide-index]', (els) => els.length);
    if (out.slideCount > 1) {
      out.activeSlideBefore = await page.$$eval('.story-slide-thumb', (els) => els.findIndex((e) => e.classList.contains('active')));
      await page.evaluate(() => {
        const btns = document.querySelectorAll('[data-slide-index]');
        const target = btns[btns.length - 1];
        target.scrollIntoView({ block: 'center' });
        target.click();
      });
      await page.waitForTimeout(700);
      out.activeSlideAfter = await page.$$eval('.story-slide-thumb', (els) => els.findIndex((e) => e.classList.contains('active')));
      out.slideChanged = out.activeSlideAfter !== out.activeSlideBefore;
    }
    await next(page); // compose -> music
    await goToMusic(page);
    out.music_after_slide_change = (await page.textContent('[data-music-current]')).replace(/\s+/g, ' ').trim();

    await page.click('[data-action="save-draft"]');
    await page.waitForTimeout(800);
    out.toast = await page.textContent('.publisher-toast').catch(() => null);
    out.before_reload = await readMusic(page);

    await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(1500);
    out.step_after_reload = (await progress(page)).label;
    out.storage_step_after_reload = await page.evaluate(() => {
      try { return JSON.parse(localStorage.getItem('forgeai_publisher_draft')).ui.currentStep; }
      catch (e) { return 'ERR:' + e; }
    });
    // Ordre préexistant initialize()/render() : la page démarre sur Médias
    // malgré ui.currentStep restauré — naviguer jusqu'à Musique.
    out.reached_music_after_reload = await ensureMusicStep(page, out.visit_labels = []);
    await goToMusic(page);
    out.step_music_after_reload = (await progress(page)).label;
    out.music_after_reload = (await page.textContent('[data-music-current]')).replace(/\s+/g, ' ').trim();
    out.after_reload = await readMusic(page);

    await page.click('[data-action="music-remove"]');
    await page.waitForTimeout(500);
    out.after_remove = (await page.textContent('[data-music-current]')).replace(/\s+/g, ' ').trim();
    out.music_after_remove = await readMusic(page);

    // Après retrait : poursuivre sans musique, aperçu sans ligne musique
    await next(page); // music -> caption
    await page.waitForSelector('[data-caption-host]', { timeout: 10000 });
    await next(page); // caption -> preview
    await page.waitForSelector('.pp-story', { timeout: 10000 });
    out.preview_after_remove_has_row = await page.evaluate(() => !!document.querySelector('.pp-story-music'));
  } catch (e) {
    out.error = String(e);
    out.state = await page.evaluate(() => ({
      label: document.querySelector('[data-progress-label]')?.textContent || null,
      body: (document.body.innerText || '').slice(0, 300),
    })).catch(() => ({}));
  }
  out.consoleErrors = errors.slice(0, 10);
  out.httpErrors = httpErrors.slice(0, 15);
  results.S1 = out;
  await context.close();
}

// ================= S2 : Story sans musique =================
{
  const { context, page, errors, httpErrors } = await setupPage(null);
  const out = { name: 'S2 — Story sans musique' };
  try {
    await page.goto(`${BASE}/publisher/story`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await selectPhotos(page, 1);
    await next(page); // adjust -> compose
    await page.waitForSelector('[data-story-host]', { timeout: 15000 });
    await page.waitForTimeout(1000);
    await next(page); // compose -> music
    await goToMusic(page);
    out.empty_state = (await page.textContent('[data-music-current]')).replace(/\s+/g, ' ').trim();
    out.music = (await readMusic(page)).music;

    await next(page); // music -> caption
    await page.waitForSelector('[data-caption-host]', { timeout: 10000 });
    await next(page); // caption -> preview
    await page.waitForSelector('.pp-story', { timeout: 10000 });
    out.preview_has_music_row = await page.evaluate(() => !!document.querySelector('.pp-story-music'));
    out.preview_ok = await page.evaluate(() => !!document.querySelector('.pp-story'));
  } catch (e) {
    out.error = String(e);
  }
  out.consoleErrors = errors.slice(0, 10);
  out.httpErrors = httpErrors.slice(0, 15);
  results.S2 = out;
  await context.close();
}

// ================= S3 : ancien brouillon design.ig_audio =================
{
  const seed = () => {
    localStorage.setItem('forgeai_publisher_draft', JSON.stringify({
      draft: {
        id: null,
        format: 'story',
        media: [{
          id: 'photo_11',
          url: '/photos/11/file',
          thumbnail_url: '/photos/11/file?size=small',
          crop: { x: 0, y: 0, w: 1, h: 1 },
          order: 0,
          type: 'photo',
          source: 'library',
          garminActivityId: null,
        }],
        design: {
          slides: [{ type: 'photo', photo_indices: [0] }],
          designDocuments: [{
            version: 2,
            format: { width: 1080, height: 1920, type: 'story_916', platform: 'instagram' },
            background: { type: 'photo', photo_id: 11, crop: { x: 0, y: 0, w: 1, h: 1 } },
            elements: [],
            ig_audio: { audio_id: 'legacy-9', title: 'Ancienne Piste', artist: 'Avant Refactor', duration_in_ms: 61000 },
            carousel: [11],
            timeline: { fps: 30, tracks: [] },
          }],
        },
        caption: { title: '', content: '', hashtags: '', accountId: null },
        music: { trackId: null, start: 0, end: 0, volume: 1, source: null },
        garmin: { activityId: null, stats: {}, overlays: [] },
        status: 'draft',
        createdAt: 1764000000000,
        updatedAt: 1764000000000,
        sourceEntryId: null,
      },
      ui: { currentStep: 'media', previewOpen: false, aiPanelOpen: false, formatSelectorOpen: false, accountSelectorOpen: false },
      savedAt: Date.now(),
    }));
  };
  const { context, page, errors, httpErrors } = await setupPage(seed);
  const out = { name: 'S3 — Ancien brouillon avec design.ig_audio' };
  try {
    await page.goto(`${BASE}/publisher/story`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('[data-action="complete"]', { timeout: 20000 });
    await page.click('[data-action="complete"]');
    await page.waitForSelector('.ppe-header', { timeout: 15000 });
    await next(page); // adjust -> compose
    await page.waitForSelector('[data-story-host]', { timeout: 15000 });
    await page.waitForTimeout(1000);
    await next(page); // compose -> music
    await goToMusic(page);
    out.selection_text = (await page.textContent('[data-music-current]')).replace(/\s+/g, ' ').trim();
    out.shows_legacy = out.selection_text.includes('Ancienne Piste');
    out.music = (await readMusic(page)).music;

    await next(page); // music -> caption
    await page.waitForSelector('[data-caption-host]', { timeout: 10000 });
    await next(page); // caption -> preview
    await page.waitForSelector('.pp-story', { timeout: 10000 });
    out.preview_music = await page.evaluate(() => {
      const row = document.querySelector('.pp-story-music');
      return row ? row.textContent.replace(/\s+/g, ' ').trim() : null;
    });
  } catch (e) {
    out.error = String(e);
  }
  out.consoleErrors = errors.slice(0, 10);
  out.httpErrors = httpErrors.slice(0, 15);
  results.S3 = out;
  await context.close();
}

// ================= S4 : non-régression Reel =================
{
  const { context, page, errors, httpErrors } = await setupPage(null);
  const out = { name: 'S4 — Reel inchangé (steps + panneau musique)' };
  try {
    await page.goto(`${BASE}/publisher/reel`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await selectPhotos(page, 1);
    out.progress_adjust = await progress(page);
    out.no_music_step = !out.progress_adjust.segments.includes('music');
    out.segment_count = out.progress_adjust.segments.length;

    await next(page); // adjust -> compose
    await page.waitForSelector('[data-studio-host], .publisher-reel-editor', { timeout: 20000 });
    await page.waitForTimeout(1500);
    out.reel_music_button = await page.evaluate(() => !!document.querySelector('[data-action="music-open"]'));
    out.reel_music_panel = await page.evaluate(() => !!document.querySelector('[data-music-panel]'));
  } catch (e) {
    out.error = String(e);
  }
  out.consoleErrors = errors.slice(0, 10);
  out.httpErrors = httpErrors.slice(0, 15);
  results.S4 = out;
  await context.close();
}

// ================= S5 : non-régression Post =================
{
  const { context, page, errors, httpErrors } = await setupPage(null);
  const out = { name: 'S5 — Post inchangé (5 étapes, pas de Musique)' };
  try {
    await page.goto(`${BASE}/publisher/post`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector('[data-photo-id]', { timeout: 20000 });
    await page.waitForTimeout(800);
    out.progress_media = await progress(page);
    out.no_music_step = !out.progress_media.segments.includes('music');
    out.segment_count = out.progress_media.segments.length;
  } catch (e) {
    out.error = String(e);
  }
  out.consoleErrors = errors.slice(0, 10);
  out.httpErrors = httpErrors.slice(0, 15);
  results.S5 = out;
  await context.close();
}

console.log(JSON.stringify(results, null, 2));
await browser.close();
