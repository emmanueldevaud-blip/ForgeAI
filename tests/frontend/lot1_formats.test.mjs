// Lot 1 — Programmation et formats (A04, A05, A06, A07).
// Exécution : node tests/frontend/lot1_formats.test.mjs
//
// Vérifie que le client n'annonce pas une programmation inexistante, bloque
// le carrousel à la publication, publiant les Stories sur Instagram, Facebook
// ou les deux, et présente la musique Story comme brouillon créatif non publié.
import assert from 'node:assert/strict';
import fs from 'node:fs';

import {
  normalizeStoryPlatforms,
  publishStoryWithPipeline,
} from '../../src/public/js/services/storyPublishPipeline.js';

const root = new URL('../../', import.meta.url);
const read = (relative) => fs.readFileSync(new URL(relative, root), 'utf8');
const strip = (source) => source
  .replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '')
  .replace(/export class/g, 'class')
  .replace(/export function/g, 'function')
  .replace(/export const/g, 'const');

// ------------------------------------------------------------
// A04 — export client de programmation désactivé
// ------------------------------------------------------------
{
  const src = read('src/public/js/services/sportApi.js');
  const fn = src.match(/export async function scheduleStudioDraft[\s\S]*?\n\}/)?.[0] || '';
  assert.ok(fn, 'scheduleStudioDraft reste exporté (retrait documenté, pas suppression silencieuse)');
  assert.match(fn, /throw new Error\(/, 'l\'export échoue immédiatement');
  assert.match(fn, /désactivée/, 'le message est explicite');
  assert.doesNotMatch(fn, /cmApi\.post/, 'aucun appel HTTP de programmation');
  console.log('A04 : export client scheduleStudioDraft désactivé sans appel réseau');
}

// ------------------------------------------------------------
// A06/A07 — garde-fous du pipeline et libellés
// ------------------------------------------------------------
{
  await assert.rejects(
    () => publishStoryWithPipeline({
      draftId: 7,
      slides: [],
      designDocuments: [],
      deps: {},
      api: {
        save: async () => { throw new Error('save ne doit pas être appelé'); },
        validate: async () => {},
        publish: async () => {},
      },
      platforms: ['tiktok'],
    }),
    /Choisissez au moins une plateforme/,
  );
  assert.deepEqual(normalizeStoryPlatforms(['both']), ['instagram', 'facebook']);
  assert.deepEqual(
    normalizeStoryPlatforms(['facebook', 'instagram', 'facebook']),
    ['facebook', 'instagram'],
  );
  console.log('A06 : pipeline Story refuse une cible inconnue et déplie both');
}

{
  const musicStep = read('src/public/js/components/PublisherMusicStep.js');
  assert.match(musicStep, /Brouillon créatif/);
  assert.match(musicStep, /non intégrable à la publication actuelle/);

  const preview = read('src/public/js/components/PublisherPreview.js');
  assert.match(preview, /Sélectionnée · non intégrable à la publication actuelle/);
  assert.match(preview, /Brouillon créatif/);
  assert.doesNotMatch(preview, /audio_configuration/, 'aucune promesse de paramètre Meta audio');

  const pipelineSrc = read('src/public/js/services/storyPublishPipeline.js');
  assert.match(pipelineSrc, /normalizeStoryPlatforms/);
  assert.match(pipelineSrc, /Choisissez au moins une plateforme/);
  assert.doesNotMatch(
    pipelineSrc.match(/return api\.publish\([^\n]+/)?.[0] || '',
    /audio_configuration/,
    'la musique n\'est pas transmise à l\'API de publication',
  );
  console.log('A07 : musique Story présentée comme brouillon créatif, non publiée');
}

// ------------------------------------------------------------
// A05/A06 — service unifié côté client
// ------------------------------------------------------------
const store = {
  draft: { format: 'post', media: [], caption: {}, design: {} },
  getState() { return { draft: this.draft }; },
  _notify() {},
};

const calls = { update: [], studioPublish: [], storyPipeline: [] };
const deps = {
  publisherStore: store,
  createStudioDraftFromCalendar: async () => ({}),
  createStudioDraft: async () => ({ id: 1 }),
  getStudioDraft: async () => ({}),
  updateStudioDraft: async (id, data) => { calls.update.push([id, data]); return { id }; },
  validateStudioDraft: async () => ({}),
  publishStudioDraft: async (id, data) => { calls.studioPublish.push([id, data]); return { status: 'queued' }; },
  publishStudioDraftFacebook: async () => ({}),
  publishStudioDraftBoth: async () => ({}),
  previewStudioDraft: async () => ({}),
  getSuggestedPhotos: async () => [],
  generateStudioDraftVariants: async () => ({}),
  generateStudioDraftText: async () => ({}),
  lockStudioDraftTitle: async () => ({}),
  lockStudioDraftContent: async () => ({}),
  lockStudioDraftPhoto: async () => ({}),
  createStoryDraft: async () => ({}),
  getStoryDraft: async () => ({}),
  updateStoryDraft: async () => ({}),
  updateStorySlideDesign: async () => ({}),
  renderStorySlide: async () => ({}),
  validateStoryDraftApi: async () => ({}),
  publishStoryDraftApi: async () => ({}),
  listStoryDrafts: async () => [],
  getMonthCalendar: async () => ({}),
  getWeekCalendar: async () => ({}),
  createStudioRender: async () => ({}),
  getStudioRenderJob: async () => ({}),
  cancelStudioRender: async () => ({}),
  uploadPhotos: async () => [],
  photoFileUrl: () => '',
  publishStoryWithPipeline: async (...args) => { calls.storyPipeline.push(args); return {}; },
};

const serviceSource = strip(read('src/public/js/services/publisherDraftService.js'));
const depNames = Object.keys(deps);
const { PublisherDraftService } = new Function(
  ...depNames,
  `${serviceSource}\nreturn { PublisherDraftService };`,
)(...depNames.map((name) => deps[name]));

{
  const svc = new PublisherDraftService();
  svc.currentDraftType = 'studio';
  svc.currentDraftId = 88;
  svc.currentFormatOverride = 'carousel';
  store.draft = { format: 'carousel', media: [{ id: 11 }, { id: 12 }], caption: {}, design: {} };

  await assert.rejects(() => svc.publish(), /carrousel/);
  assert.equal(calls.update.length, 0, 'aucune sauvegarde serveur');
  assert.equal(calls.studioPublish.length, 0, 'aucune publication');
  console.log('A05 : carrousel bloqué côté client avant sauvegarde/publication');
}

{
  const svc = new PublisherDraftService();
  svc.currentDraftType = 'story';
  svc.currentDraftId = 77;
  store.draft = { format: 'story', caption: { content: '', hashtags: '' }, design: {} };

  await svc.publish({ platforms: ['facebook'] });
  await svc.publish({ platforms: ['instagram', 'facebook'] });
  assert.equal(calls.storyPipeline.length, 2, 'les deux cibles Story lancent le pipeline');
  assert.deepEqual(calls.storyPipeline[0][0].platforms, ['facebook']);
  assert.deepEqual(calls.storyPipeline[1][0].platforms, ['instagram', 'facebook']);
  console.log('A06 : service accepte Facebook et les deux pour une Story');
}

// ------------------------------------------------------------
// A05 — bouton Publier désactivé et explication visible dans l'UI
// ------------------------------------------------------------
{
  const page = read('src/public/js/pages/CommunityPublisherPage.js');
  assert.match(page, /carouselBlocked/, 'l\'état carrousel est pris en compte');
  assert.match(page, /data-carousel-blocked/, 'un message explicite est rendu');
  assert.match(page, /carrousel ne peut pas encore être publié/);
  console.log('A05 : UI Publisher désactive et explique la publication carrousel');
}

// ------------------------------------------------------------
// A06 — sélecteur de destination Story dans l'UI
// ------------------------------------------------------------
{
  const page = read('src/public/js/pages/CommunityPublisherPage.js');
  assert.match(page, /data-story-platforms/, 'sélecteur de destination rendu');
  assert.match(page, /value="facebook"/, 'case Facebook proposée');
  assert.match(page, /_selectedStoryPlatforms/, 'les cases sont lues au clic Publier');
  assert.match(page, /getMetaSettings/, 'préflight de la Page Facebook');
  assert.match(page, /const platforms = this\.format === 'story' \? this\._selectedStoryPlatforms\(\) : \['instagram'\]/);
  console.log('A06 : UI Story propose Instagram, Facebook et les deux avec préflight');
}
