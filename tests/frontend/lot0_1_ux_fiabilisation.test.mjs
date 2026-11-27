// Lot 0.1 — Fiabilisation UX A01 / A02 / A03.
// Exécution : node tests/frontend/lot0_1_ux_fiabilisation.test.mjs
//
// Tests ciblés, sans serveur ni navigateur : les modules sont chargés par
// extraction de source avec des dépendances simulées (même technique que
// tests/frontend/lot0_creation_flow.test.mjs).
import assert from 'node:assert/strict';
import fs from 'node:fs';

const root = new URL('../../', import.meta.url);
const read = (relative) => fs.readFileSync(new URL(relative, root), 'utf8');
const strip = (source) => source
  .replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '')
  .replace(/export class/g, 'class')
  .replace(/export function/g, 'function')
  .replace(/export const/g, 'const');

const noop = () => {};

// ---------------------------------------------------------------------------
// Faux DOM minimal : retient le HTML et les nœuds ajoutés dans les alertes.
// ---------------------------------------------------------------------------
function makeNode() {
  const node = {
    children: [],
    handlers: {},
    subs: new Map(),
    dataset: {},
    style: {},
    textContent: '',
    hidden: false,
    disabled: false,
    parentNode: null,
    classList: { add: noop, remove: noop, toggle: noop },
    _html: '',
    set innerHTML(value) {
      this._html = String(value);
      this.children = [];
    },
    get innerHTML() { return this._html; },
    appendChild(child) {
      this.children.push(child);
      child.parentNode = this;
      return child;
    },
    addEventListener(type, handler) {
      (this.handlers[type] ||= []).push(handler);
    },
    querySelector(selector) {
      if (!this.subs.has(selector)) this.subs.set(selector, makeNode());
      return this.subs.get(selector);
    },
    querySelectorAll(selector) {
      if (!this.subs.has(selector)) this.subs.set(selector, [makeNode()]);
      return this.subs.get(selector);
    },
    setAttribute(name, value) { this.dataset[name] = value; },
    remove() {
      if (this.parentNode) {
        this.parentNode.children = this.parentNode.children.filter(c => c !== this);
      }
    },
    click() { (this.handlers.click || []).forEach(h => h({ stopPropagation: noop })); },
  };
  return node;
}

// ===========================================================================
// A01 — fallback local 422 : cause visible, pas de faux succès serveur.
// ===========================================================================
console.log('A01 : 422 stratégie absente → repli local avec cause exposée');
{
  const store = {
    draft: { format: 'post', media: [], caption: {}, design: {} },
    resetDraft(format = 'post') { this.draft = { format, media: [], caption: {}, design: {} }; },
    getState() { return { draft: this.draft }; },
    _notify: noop,
  };
  const calls = { create: [], update: [], publish: [] };
  const apiError = Object.assign(new Error('Stratégie éditoriale non configurée'), {
    status: 422,
    data: { detail: 'Stratégie éditoriale non configurée' },
  });
  const deps = {
    publisherStore: store,
    createStudioDraftFromCalendar: async () => ({ publication_id: 1 }),
    createStudioDraft: async (data) => { calls.create.push(data); throw apiError; },
    getStudioDraft: async () => ({}),
    updateStudioDraft: async (...args) => { calls.update.push(args); return {}; },
    validateStudioDraft: async () => ({}),
    publishStudioDraft: async (...args) => { calls.publish.push(args); return {}; },
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
  const names = Object.keys(deps);
  const { PublisherDraftService } = new Function(
    ...names,
    `${strip(read('src/public/js/services/publisherDraftService.js'))}\nreturn { PublisherDraftService };`,
  )(...names.map(name => deps[name]));

  const service = new PublisherDraftService();
  const local = await service.createBlank('post');
  assert.equal(service.currentDraftId, null, 'aucun ID serveur après le 422');
  assert.equal(local.format, 'post', 'le brouillon local est conservé');
  assert.deepEqual(service.serverDraftError, {
    status: 422,
    detail: 'Stratégie éditoriale non configurée',
  }, 'la cause HTTP est exposée à l’UI');

  store.draft.caption = { title: 'Titre local' };
  const saved = await service.save({ caption: store.draft.caption, media: [], design: {} });
  assert.equal(calls.update.length, 0, 'aucune sauvegarde serveur simulée');
  assert.equal(saved.caption.title, 'Titre local', 'la saisie locale est intacte');
  assert.equal(service.serverDraftError.status, 422, 'l’erreur reste visible après save()');

  await assert.rejects(() => service.publish({ platforms: ['instagram'] }), /Publication impossible/);
  assert.equal(calls.publish.length, 0, 'aucune publication réelle tentée');
}

// ===========================================================================
// CommunityPublisherPage — A01 / A02 / A03.
// ===========================================================================
function makePageHarness(overrides = {}) {
  const service = Object.assign({
    currentDraftId: null,
    currentDraftType: null,
    serverDraftError: null,
    load: async () => ({}),
    createFromCalendar: async () => ({}),
    createBlank: async () => ({}),
    save: async () => ({}),
    publish: async () => ({ status: 'queued' }),
    getSuggestedPhotos: async () => [],
    clearCurrent: noop,
  }, overrides.service || {});
  const pageCalls = {
    load: [], createFromCalendar: [], createBlank: [], save: [], publish: [],
    suggestions: [], addMedia: [], toasts: [],
  };
  const store = {
    draft: {
      format: 'post', media: [], design: {}, music: {},
      caption: { title: '', content: '', hashtags: '', accountId: null },
      status: 'draft',
    },
    ui: { currentStep: 'media' },
    subscribe: () => noop,
    _notify: noop,
    resetDraft: noop,
    setFormat: noop,
    setGarmin: noop,
    addMedia(items) { pageCalls.addMedia.push(items); },
    clear: noop,
    updateCaption: noop,
  };
  if (overrides.store) Object.assign(store, overrides.store);
  const deps = {
    publisherStore: store,
    publisherDraftService: service,
    getSuggestedPhotosForActivity: async (...args) => {
      pageCalls.suggestions.push(args);
      if (overrides.suggestionsError) throw overrides.suggestionsError;
      return overrides.suggestions || [];
    },
    createPublisherMediaPicker: () => ({ mount: noop, destroy: noop }),
    createPublisherCaptionEditor: () => ({ mount: noop, destroy: noop }),
    createPublisherPreview: () => ({ mount: noop, destroy: noop }),
    createPublisherMusicStep: () => ({ mount: noop, destroy: noop }),
    createPublisherReelEditor: () => ({ mount: noop, destroy: noop }),
    createPublisherStoryEditor: () => ({ mount: noop, destroy: noop }),
    document: { createElement: () => makeNode() },
    router: { navigate: noop },
  };
  const names = Object.keys(deps);
  const { CommunityPublisherPage } = new Function(
    ...names,
    `${strip(read('src/public/js/pages/CommunityPublisherPage.js'))}\nreturn { CommunityPublisherPage };`,
  )(...names.map(name => deps[name]));
  service.load = async (...args) => { pageCalls.load.push(args); return (overrides.load || (async () => ({})))(...args); };
  service.createFromCalendar = async (...args) => {
    pageCalls.createFromCalendar.push(args);
    return (overrides.createFromCalendar || (async () => ({})))(...args);
  };
  service.createBlank = async (...args) => {
    pageCalls.createBlank.push(args);
    return (overrides.createBlank || (async () => ({})))(...args);
  };
  service.save = async (...args) => { pageCalls.save.push(args); return (overrides.save || (async () => ({})))(...args); };
  service.publish = async (...args) => { pageCalls.publish.push(args); return (overrides.publish || (async () => ({ status: 'queued' })))(...args); };
  return { CommunityPublisherPage, service, store, pageCalls };
}

function alertText(page) {
  const host = page.element.querySelector('[data-alerts]');
  return host.children.map(node => node.innerHTML).join('\n');
}

console.log('A01 : le 422 de création est rendu dans une alerte visible');
{
  const { CommunityPublisherPage, pageCalls } = makePageHarness({
    service: {
      serverDraftError: {
        status: 422,
        detail: 'Stratégie éditoriale non configurée',
      },
    },
  });
  const page = new CommunityPublisherPage({ navigate: noop }, { format: 'post', freshDraft: true });
  await page.initialize();
  assert.equal(pageCalls.createBlank.length, 1, 'le repli local reste appelé');
  const html = page.render().innerHTML;
  assert.match(html, /data-alerts/, 'une zone d’alertes est rendue');
  const text = alertText(page);
  assert.match(text, /Stratégie éditoriale non configurée/, 'le détail 422 est visible');
  assert.match(text, /\(422\)/, 'le statut est visible');
  assert.match(text, /conservé localement/, 'aucune sauvegarde serveur réussie n’est suggérée');
  assert.match(text, /Configurez une stratégie éditoriale/, 'la cause est explicitée');
}

console.log('A02 : publication_id et calendar_entry_id sont distincts');
{
  {
    const { CommunityPublisherPage, pageCalls } = makePageHarness();
    const page = new CommunityPublisherPage({ navigate: noop }, { format: 'post', publicationId: '77' });
    await page.initialize();
    assert.deepEqual(pageCalls.load[0][0], 77, 'URL → load(publication_id)');
    assert.equal(pageCalls.createFromCalendar.length, 0, 'aucune création depuis le calendrier');
    assert.equal(page.calendarEntryId, null, 'publication_id n’est pas un calendar_entry_id');
  }
  {
    const { CommunityPublisherPage, pageCalls } = makePageHarness();
    const page = new CommunityPublisherPage({ navigate: noop }, { format: 'post', calendarEntryId: 55 });
    await page.initialize();
    assert.equal(pageCalls.createFromCalendar[0][0].calendarEntryId, 55, 'calendrier → createFromCalendar');
    assert.equal(pageCalls.load.length, 0, 'aucun chargement de publication');
    assert.equal(page.publicationId, null, 'calendar_entry_id n’est pas un publication_id');
  }
}

console.log('A02 : 404 → écran d’erreur, jamais un wizard vierge');
{
  const err = Object.assign(new Error('Ressource non trouvée.'), {
    status: 404,
    data: { detail: 'Brouillon introuvable' },
  });
  const { CommunityPublisherPage, pageCalls } = makePageHarness({
    load: async () => { throw err; },
  });
  const page = new CommunityPublisherPage({ navigate: noop }, {
    format: 'post', publicationId: 999999,
  });
  await page.initialize();
  assert.equal(page.loadError, true);
  assert.match(page.error, /Publication #999999 introuvable/);
  assert.match(page.error, /Brouillon introuvable/);
  assert.match(page.error, /\(404\)/);
  const html = page.render().innerHTML;
  assert.match(html, /data-error-message/, 'l’erreur est rendue');
  assert.match(html, /Aucune publication à afficher/);
  assert.doesNotMatch(html, /data-step-content/, 'aucun formulaire vierge affiché');
  assert.equal(pageCalls.createBlank.length, 0, 'aucun brouillon vierge créé');
}

console.log('A02/A03 : route vide + ?garmin=1 restent sur Story sans erreur de publication');
{
  const h = makePageHarness();
  const formats = [];
  h.store.setFormat = (format) => { formats.push(format); h.store.draft.format = format; };
  const page = new h.CommunityPublisherPage({ navigate: noop }, {
    format: 'story', publicationId: '', garminActivityId: 7,
  });
  await page.initialize();
  assert.equal(page.loadError, false, 'un segment de route vide ne doit pas ouvrir le mode publication');
  assert.equal(h.pageCalls.load.length, 0, 'aucune tentative de chargement de publication');
  assert.equal(formats[0], 'story', '?garmin= impose Story dans le store, même avec un brouillon Post');
  assert.deepEqual(h.pageCalls.suggestions, [[7, 10]], 'suggestions chargées pour la vraie activité');
}

console.log('A03 : erreur de suggestions Garmin visible dans l’UI');
{
  const err = Object.assign(new Error('Stratégie éditoriale non configurée'), {
    status: 422,
    data: { detail: 'Stratégie éditoriale non configurée' },
  });
  const { CommunityPublisherPage, pageCalls } = makePageHarness({ suggestionsError: err });
  const page = new CommunityPublisherPage({ navigate: noop }, {
    format: 'story', garminActivityId: 999999,
  });
  await page.initialize();
  assert.deepEqual(pageCalls.suggestions, [[999999, 10]], 'suggestions par activity_id (format Story)');
  page.render();
  const text = alertText(page);
  assert.match(text, /Suggestions Garmin indisponibles/, 'message visible');
  assert.match(text, /Stratégie éditoriale non configurée/, 'cause visible');
  assert.match(text, /\(422\)/, 'statut visible');
}

// ===========================================================================
// Routeur : deep link publication + format Story imposé par ?garmin=.
// ===========================================================================
console.log('A02/A03 : routage /publisher/post/:id et ?garmin=<id>');
{
  const appSource = read('src/public/js/app-erp.js');
  assert.match(appSource, /\/publisher\/:format\/:publicationId/, 'segment nommé publicationId');
  const body = appSource.match(/async function showCommunityPublisherPage\(route\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(body, 'showCommunityPublisherPage extraite');
  const optionsSeen = [];
  const factory = new Function('appShell', 'router', 'window', 'createCommunityPublisherPage', 'console', `
    let communityPublisherPage = null;
    ${body}
    return { showCommunityPublisherPage, getPage: () => communityPublisherPage };
  `);
  const appShell = { showLoading: noop, showContent: noop, showError: noop };
  const harness = factory(
    appShell,
    { navigate: noop },
    { location: { search: '' } },
    (router, options) => {
      optionsSeen.push(options);
      return { initialize: async () => {}, render: () => makeNode(), destroy: noop };
    },
    { error: noop },
  );
  await harness.showCommunityPublisherPage({ params: { format: 'post', publicationId: '4242' } });
  assert.equal(optionsSeen[0].publicationId, '4242', 'deep link → publicationId');
  assert.equal(optionsSeen[0].entryId, undefined, 'plus d’entryId depuis l’URL');

  harness.getPage().destroy();
  const harness2 = factory(
    appShell,
    { navigate: noop },
    { location: { search: '?garmin=999999' } },
    (router, options) => {
      optionsSeen.push(options);
      return { initialize: async () => {}, render: () => makeNode(), destroy: noop };
    },
    { error: noop },
  );
  await harness2.showCommunityPublisherPage({ params: { format: 'post' } });
  assert.equal(optionsSeen[1].format, 'story', '?garmin= force Story');
  assert.equal(optionsSeen[1].garminActivityId, 999999, 'activity_id transmis');
  assert.equal(optionsSeen[1].publicationId, null, 'pas de publication implicite');
}

// ===========================================================================
// MediaPicker : doublon supprimé, erreurs visibles.
// ===========================================================================
console.log('A03 : état vide unique et erreurs Garmin visibles');
{
  const source = strip(read('src/public/js/components/PublisherMediaPicker.js'));
  const store = { draft: { media: [] } };
  let activitiesError = null;
  let suggestionsError = null;
  const { PublisherMediaPicker } = new Function(
    'publisherStore', 'listPhotos', 'uploadPhotos', 'listAlbums',
    'listSportActivities', 'getSuggestedPhotos', 'getSuggestedPhotosForActivity',
    `${source}\nreturn { PublisherMediaPicker };`,
  )(
    store,
    async () => ({}), async () => [], async () => ({}),
    async () => {
      if (activitiesError) throw activitiesError;
      return { items: [], total: 0 };
    },
    async () => [],
    async () => { if (suggestionsError) throw suggestionsError; return []; },
  );

  const notice = makeNode();
  const garminList = makeNode();
  const garminEmpty = makeNode();
  garminEmpty.hidden = true;
  const picker = new PublisherMediaPicker({ format: 'story' });
  picker.element = {
    querySelector(selector) {
      if (selector === '[data-notice]') return notice;
      if (selector === '[data-garmin-empty]') return garminEmpty;
      if (selector === '[data-garmin-list]') return garminList;
      return null;
    },
    dispatchEvent: noop,
  };

  await picker._loadGarmin();
  assert.doesNotMatch(garminList.innerHTML, /Aucune activité Garmin/, 'pas de second message vide');
  assert.equal(garminEmpty.hidden, false, 'le message vide du template est affiché une seule fois');

  activitiesError = Object.assign(new Error('Serveur indisponible'), {
    status: 500, data: { detail: 'Erreur interne' },
  });
  await picker._loadGarmin();
  assert.match(notice.textContent, /Chargement des activités Garmin impossible/, 'erreur visible');
  assert.match(notice.textContent, /Erreur interne/, 'cause visible');

  suggestionsError = Object.assign(new Error('Stratégie éditoriale non configurée'), {
    status: 422, data: { detail: 'Stratégie éditoriale non configurée' },
  });
  await picker._openGarminActivity(12);
  assert.match(notice.textContent, /Suggestions Garmin indisponibles/, 'erreur de suggestions visible');
  assert.match(notice.textContent, /Stratégie éditoriale non configurée/, 'cause visible');
}

console.log('\nLot 0.1 — fiabilisation UX A01/A02/A03 : OK');
