// Lot 0 — Création publiable (A01, A02, A03, A14).
// Exécution : node --test tests/frontend/lot0_creation_flow.test.mjs
//
// Valide la chaîne création standalone → sauvegarde → publication, le
// chargement du Publisher par publication_id (calendrier), les suggestions
// Garmin par activity_id et la normalisation des IDs médias.
import assert from 'node:assert/strict';
import fs from 'node:fs';

const root = new URL('../../', import.meta.url);
const read = (relative) => fs.readFileSync(new URL(relative, root), 'utf8');
const strip = (source) => source
  .replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '')
  .replace(/export class/g, 'class')
  .replace(/export function/g, 'function')
  .replace(/export const/g, 'const');

// ============================================================
// 1. PublisherDraftService — A01 / A14
// ============================================================

const store = {
  draft: { format: 'post', media: [], caption: {}, design: {} },
  resetDraft(format = 'post') {
    this.draft = { format, media: [], caption: {}, design: {} };
  },
  getState() { return { draft: this.draft }; },
  _notify() {},
  clear() { this.draft = { format: 'post', media: [], caption: {}, design: {} }; },
};

const calls = {
  createStudioDraft: [],
  getStudioDraft: [],
  updateStudioDraft: [],
  publishStudioDraft: [],
  createFromCalendar: [],
};
let failCreate = false;

const deps = {
  publisherStore: store,
  createStudioDraftFromCalendar: async (data) => { calls.createFromCalendar.push(data); return { publication_id: 1 }; },
  createStudioDraft: async (data) => {
    calls.createStudioDraft.push(data);
    if (failCreate) throw new Error('403');
    return { id: 77 };
  },
  getStudioDraft: async (id) => {
    calls.getStudioDraft.push(id);
    return {
      id, status: 'draft', content_type: null, visual_type: 'photo',
      design: {}, photo_id: null, calendar_entry_id: null,
      title: '', content: '', hashtags: '',
      created_at: null, updated_at: null,
    };
  },
  updateStudioDraft: async (id, updates) => { calls.updateStudioDraft.push([id, updates]); return { id }; },
  validateStudioDraft: async () => ({}),
  publishStudioDraft: async (id, opts) => { calls.publishStudioDraft.push([id, opts]); return { status: 'queued' }; },
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
  publishStoryWithPipeline: async () => ({}),
};

const serviceSource = strip(read('src/public/js/services/publisherDraftService.js'));
const serviceDeps = Object.keys(deps);
const { PublisherDraftService } = new Function(
  ...serviceDeps,
  `${serviceSource}\nreturn { PublisherDraftService };`,
)(...serviceDeps.map((name) => deps[name]));

function freshService() {
  calls.createStudioDraft.length = 0;
  calls.getStudioDraft.length = 0;
  calls.updateStudioDraft.length = 0;
  calls.publishStudioDraft.length = 0;
  calls.createFromCalendar.length = 0;
  failCreate = false;
  store.resetDraft('post');
  return new PublisherDraftService();
}

console.log('A01 : création standalone → sauvegarde → publication');
{
  const svc = freshService();
  const draft = await svc.createBlank('post');
  assert.equal(calls.createStudioDraft.length, 1, 'createBlank crée un brouillon serveur');
  assert.deepEqual(calls.createStudioDraft[0], { visual_type: 'photo' });
  assert.equal(svc.currentDraftId, 77, 'currentDraftId est renseigné après création');
  assert.equal(svc.currentDraftType, 'studio');
  assert.equal(store.draft.id, 77, 'le store local est synchronisé sur le brouillon serveur');
  assert.ok(draft);

  await svc.save({ caption: { title: 'Titre', content: 'Légende', hashtags: '#run' }, media: [], design: {} });
  assert.equal(calls.createStudioDraft.length, 1, 'pas de double création au save');
  const [id, updates] = calls.updateStudioDraft[0];
  assert.equal(id, 77);
  assert.equal(updates.title, 'Titre');
  assert.deepEqual(updates.photo_ids, []);

  await svc.publish({ platforms: ['instagram'] });
  assert.equal(calls.publishStudioDraft.length, 1, 'publish() n échoue plus avec « Aucun brouillon »');
  assert.equal(calls.publishStudioDraft[0][0], 77);
}

console.log('A01 : premier save/publish sans brouillon serveur crée le brouillon à la volée');
{
  const svc = freshService();
  svc.currentDraftType = 'studio'; // type posé par createBlank, ID serveur absent
  svc.currentDraftId = null;
  await svc.save({ caption: { title: 'T', content: 'C', hashtags: '' }, media: [], design: {} });
  assert.equal(calls.createStudioDraft.length, 1, 'save() crée le brouillon serveur');
  assert.equal(calls.updateStudioDraft[0][0], 77);
}

{
  const svc = freshService();
  svc.currentDraftType = 'studio';
  svc.currentDraftId = null;
  await svc.publish({ platforms: ['instagram'] });
  assert.equal(calls.createStudioDraft.length, 1, 'publish() crée le brouillon serveur si besoin');
  assert.equal(calls.publishStudioDraft[0][0], 77);
}

console.log('A01 : la création serveur en échec conserve le brouillon local');
{
  const svc = freshService();
  failCreate = true;
  const draft = await svc.createBlank('post');
  assert.equal(svc.currentDraftId, null, 'pas d ID serveur en cas d échec');
  assert.equal(svc.currentDraftType, 'studio');
  assert.equal(draft.format, 'post', 'le brouillon local est conservé');
}

console.log('A01 : le contenu local est conservé lors de la création serveur au premier save');
{
  const svc = freshService();
  svc.currentDraftType = 'studio';
  svc.currentDraftId = null;
  store.draft.caption = { title: 'Titre local', content: 'Légende locale', hashtags: '' };
  store.draft.media = [{ id: 'photo_4', photoId: 4 }];
  await svc.save({ caption: store.draft.caption, media: store.draft.media, design: {} });
  assert.equal(calls.createStudioDraft.length, 1, 'un seul brouillon serveur créé');
  assert.equal(calls.updateStudioDraft[0][1].title, 'Titre local', 'le titre local n est pas écrasé');
  assert.deepEqual(calls.updateStudioDraft[0][1].photo_ids, [4]);
}

console.log('A01 : une Story standalone ne dépend pas du brouillon serveur Studio');
{
  const svc = freshService();
  await svc.createBlank('story');
  assert.equal(calls.createStudioDraft.length, 0, 'pas de création serveur pour une Story');
  assert.equal(svc.currentDraftId, null);
  assert.equal(svc.currentDraftType, 'story');
  await assert.rejects(() => svc.publish(), /Aucun brouillon/);
}

console.log('A14 : normalisation robuste des IDs médias');
{
  const svc = freshService();
  assert.equal(svc._resolveServerPhotoId({ photoId: 42, id: 'garmin-x' }), 42, 'photoId numérique explicite');
  assert.equal(svc._resolveServerPhotoId({ id: 'photo_17' }), 17, 'préfixe photo_');
  assert.equal(svc._resolveServerPhotoId({ id: 9 }), 9, 'id numérique brut');
  assert.equal(svc._resolveServerPhotoId({ id: 'media_177000' }), null, 'id sans ID serveur → null');

  await svc.createBlank('post');
  await assert.rejects(
    () => svc.save({ media: [{ id: 'media_177000' }] }),
    /Média sans identifiant serveur/,
    'un média sans ID serveur est une erreur visible, pas un filtrage silencieux',
  );

  await svc.save({ media: [{ photoId: 12, id: 'garmin-x' }, { id: 'photo_8' }] });
  const [, updates] = calls.updateStudioDraft.at(-1);
  assert.deepEqual(updates.photo_ids, [12, 8]);
}

// ============================================================
// 2. CommunityPublisherPage — A02 (chargement par publication_id)
// ============================================================

const pageCalls = { load: [], createFromCalendar: [], createBlank: [], save: [], publish: [], addMedia: [], garminSuggestions: [], reset: 0 };
let garminSuggestions = [];
const pageServiceStub = {
  currentDraftId: null,
  currentDraftType: null,
  load: async (...args) => { pageCalls.load.push(args); return {}; },
  createFromCalendar: async (opts) => { pageCalls.createFromCalendar.push(opts); return {}; },
  createBlank: async (format) => { pageCalls.createBlank.push(format); return {}; },
  clearCurrent() {},
  save: async (data) => { pageCalls.save.push(data); return {}; },
  publish: async (opts) => { pageCalls.publish.push(opts); return { status: 'queued' }; },
  getSuggestedPhotos: async () => [],
};
const pageStoreStub = {
  draft: {
    format: 'post', media: [], design: {},
    caption: { title: '', content: '', hashtags: '', accountId: null },
    music: {}, garmin: { activityId: null, stats: {}, overlays: [] },
    status: 'draft',
  },
  ui: { currentStep: 'media' },
  subscribe() { return () => {}; },
  _notify() {},
  resetDraft() { pageCalls.reset++; },
  setFormat() {},
  setGarmin() {},
  addMedia(items) { pageCalls.addMedia.push(items); },
  clear() {},
  updateCaption() {},
};
const noop = () => {};
const pageDeps = {
  publisherStore: pageStoreStub,
  publisherDraftService: pageServiceStub,
  getSuggestedPhotosForActivity: async (...args) => {
    pageCalls.garminSuggestions.push(args);
    return garminSuggestions;
  },
  createPublisherMediaPicker: () => ({ mount: noop, destroy: noop }),
  createPublisherCaptionEditor: () => ({ mount: noop, destroy: noop }),
  createPublisherPreview: () => ({ mount: noop, destroy: noop }),
  createPublisherMusicStep: () => ({ mount: noop, destroy: noop }),
  createPublisherMinimalComposer: () => ({ mount: noop, destroy: noop, save: async () => true }),
  document: { createElement: () => ({ innerHTML: '', appendChild: noop }) },
  router: { navigate: noop },
};
const pageSource = strip(read('src/public/js/pages/CommunityPublisherPage.js'));
const pageParamNames = Object.keys(pageDeps);
const { CommunityPublisherPage } = new Function(
  ...pageParamNames,
  `${pageSource}\nreturn { CommunityPublisherPage };`,
)(...pageParamNames.map((name) => pageDeps[name]));

function resetPageCalls() {
  pageCalls.load.length = 0;
  pageCalls.createFromCalendar.length = 0;
  pageCalls.createBlank.length = 0;
  pageCalls.save.length = 0;
  pageCalls.publish.length = 0;
  pageCalls.addMedia.length = 0;
  pageCalls.garminSuggestions.length = 0;
  pageCalls.reset = 0;
  garminSuggestions = [];
}

console.log('A02 : publication existante (calendrier) → chargement par publication_id');
{
  resetPageCalls();
  const page = new CommunityPublisherPage(pageDeps.router, {
    format: 'post', entryId: 4242, isExistingPublication: true,
  });
  await page.initialize();
  assert.equal(pageCalls.load.length, 1, 'chargement du brouillon existant');
  assert.equal(pageCalls.load[0][0], 4242, 'load(publication_id) uniquement');
  assert.equal(pageCalls.createFromCalendar.length, 0, 'aucune re-création via calendar_entry_id');
}

console.log('A02 : entrée de calendrier réelle → création from-calendar (chemin légitime)');
{
  resetPageCalls();
  const page = new CommunityPublisherPage(pageDeps.router, { format: 'post', entryId: 55 });
  await page.initialize();
  assert.equal(pageCalls.createFromCalendar.length, 1);
  assert.equal(pageCalls.createFromCalendar[0].calendarEntryId, 55);
}

console.log('A01 : création fraîche → createBlank, puis restauration locale');
{
  resetPageCalls();
  const page = new CommunityPublisherPage(pageDeps.router, { format: 'post', freshDraft: true });
  await page.initialize();
  assert.deepEqual(pageCalls.createBlank, ['post']);

  resetPageCalls();
  const page2 = new CommunityPublisherPage(pageDeps.router, { format: 'post' });
  await page2.initialize();
  assert.deepEqual(pageCalls.createBlank, ['post'], 'page vide → brouillon standalone');
}

console.log('A03 : suggestions Garmin chargées dans le store avec un photoId numérique');
{
  resetPageCalls();
  garminSuggestions = [{ id: 5, thumbnail_url: '/photos/5/file?size=small' }];
  const page = new CommunityPublisherPage(pageDeps.router, {
    format: 'post', garminActivityId: 12,
  });
  await page._loadFromGarmin();
  assert.deepEqual(pageCalls.garminSuggestions[0], [12, 1], 'suggestions appelées par activity_id');
  assert.equal(pageCalls.addMedia.length, 1, 'le résultat n est plus ignoré');
  assert.equal(pageCalls.addMedia[0][0].photoId, 5, 'ID serveur conservé');
}

console.log('A01 : _publish persiste le brouillon Studio avant la publication');
{
  resetPageCalls();
  const page = new CommunityPublisherPage(pageDeps.router, { format: 'post' });
  page.element = { querySelector: () => ({ disabled: false, textContent: '' }), appendChild: noop };
  page._showToast = noop;
  pageServiceStub.currentDraftType = 'studio';
  pageServiceStub.currentDraftId = 77;
  await page._publish();
  assert.equal(pageCalls.save.length, 1, 'save() appelé avant publish()');
  assert.equal(pageCalls.publish.length, 1, 'publish() appelé une fois');
  pageServiceStub.currentDraftId = null;
  pageServiceStub.currentDraftType = null;
}

// ============================================================
// 3. Câblage source — A02 / A03
// ============================================================

console.log('Câblage : calendrier, MediaPicker, sportApi');
{
  const calendar = read('src/public/js/pages/CommunityManagerCalendarPage.js');
  assert.match(calendar, /_openPublisher\(\{ pubId: res\.publication_id/, 'ouverture Publisher via publication_id');
  assert.doesNotMatch(calendar, /entryId: res\.publication_id/, 'plus de publication_id réinterprété en calendar_entry_id');
  assert.match(calendar, /getSuggestedPhotosForActivity\(sourceActivityId/, 'suggestions Garmin par activity_id');
  assert.doesNotMatch(calendar, /getSuggestedPhotos\(null/, 'plus d appel avec null');

  const picker = read('src/public/js/components/PublisherMediaPicker.js');
  assert.match(picker, /getSuggestedPhotosForActivity\(activityId/, 'MediaPicker cible l activité');
  assert.doesNotMatch(picker, /getSuggestedPhotos\(null/, 'plus d appel avec null');

  const sportApi = read('src/public/js/services/sportApi.js');
  assert.match(sportApi, /community-manager\/studio\/draft'/, 'endpoint dédié de création standalone');
  assert.match(sportApi, /community-manager\/studio\/activity\/\$\{encodeURIComponent\(activityId\)\}\/suggested-photos/, 'endpoint suggestions par activité');

  const publisherPage = read('src/public/js/pages/CommunityPublisherPage.js');
  assert.match(publisherPage, /publisherDraftService\.save\(/, 'sauvegarde serveur du brouillon local');
}

console.log('\nLot 0 — création publiable : OK');
