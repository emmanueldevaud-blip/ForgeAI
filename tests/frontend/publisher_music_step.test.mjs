// Tests — Étape Musique du Publisher Story (séparation Composer / Musique).
// Exécution : node tests/frontend/publisher_music_step.test.mjs
import fs from 'node:fs';

const failures = [];
function check(name, cond) {
  if (cond) console.log(`  OK ${name}`);
  else { failures.push(name); console.log(`  KO ${name}`); }
}

function read(path) {
  return fs.readFileSync(new URL(path, import.meta.url), 'utf8');
}

function strip(src) {
  return src
    .replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '')
    .replace(/export class/g, 'class')
    .replace(/export function/g, 'function')
    .replace(/export const/g, 'const');
}

function extractSteps(src, fmt) {
  const match = src.match(new RegExp(`${fmt}:\\s*{[^}]*steps:\\s*(\\[[^\\]]+\\])`));
  return match ? JSON.parse(match[1].replace(/'/g, '"')) : null;
}

function deepEq(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

const EXPECTED_STORY_STEPS = ['media', 'adjust', 'compose', 'music', 'caption', 'preview', 'publish'];
const LEGACY_STORY_STEPS = ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'];
const LEGACY_5_STEPS = ['media', 'adjust', 'caption', 'preview', 'publish'];

// ---------- T1 : configuration des étapes ----------
{
  console.log('T1: steps story = media, adjust, compose, music, caption, preview, publish');
  const pageSrc = read('../../src/public/js/pages/CommunityPublisherPage.js');
  const storeSrc = read('../../src/public/js/stores/publisherStore.js');

  check('T1: FORMAT_CONFIG page — story', deepEq(extractSteps(pageSrc, 'story'), EXPECTED_STORY_STEPS));
  check('T1: FORMAT_CONFIG store — story', deepEq(extractSteps(storeSrc, 'story'), EXPECTED_STORY_STEPS));
  check('T1: FORMAT_CONFIG page — reel inchange', deepEq(extractSteps(pageSrc, 'reel'), LEGACY_STORY_STEPS));
  check('T1: FORMAT_CONFIG store — reel inchange', deepEq(extractSteps(storeSrc, 'reel'), LEGACY_STORY_STEPS));
  check('T1: FORMAT_CONFIG page — post inchange', deepEq(extractSteps(pageSrc, 'post'), LEGACY_5_STEPS));
  check('T1: FORMAT_CONFIG page — carousel inchange', deepEq(extractSteps(pageSrc, 'carousel'), LEGACY_5_STEPS));
  check('T1: FORMAT_CONFIG store — post inchange', deepEq(extractSteps(storeSrc, 'post'), LEGACY_5_STEPS));
  check('T1: FORMAT_CONFIG store — carousel inchange', deepEq(extractSteps(storeSrc, 'carousel'), LEGACY_5_STEPS));
  check('T1: STEP_META music', /music:\s*\{\s*label:\s*'Musique',\s*icon:\s*'🎵'\s*\}/.test(pageSrc));
  check('T1: _getStepContent case music', /case 'music':\s*return '<div class="publisher-music-host" data-music-host><\/div>'/.test(pageSrc));
  check('T1: _bindStepEvents case music', /case 'music':\s*this\._mountMusicStep\(\);/.test(pageSrc));
  check('T1: _mountMusicStep present', /_mountMusicStep\(\)\s*\{/.test(pageSrc));
}

// ---------- T2 : Composer sans musique ----------
{
  console.log('T2: suppression complete de la musique dans Composer (StoryEditorView)');
  const storyViewSrc = read('../../src/public/js/editor/StoryEditorView.js');
  check('T2: pas de bouton topbar music', !storyViewSrc.includes('data-action="music"'));
  check('T2: pas de panneau music', !storyViewSrc.includes('data-music-panel'));
  check('T2: pas de barre d\'outils pre-music', !storyViewSrc.includes('pre-music'));
  check('T2: pas de _openMusicPicker', !storyViewSrc.includes('_openMusicPicker'));
  check('T2: pas de _onMusicSearch', !storyViewSrc.includes('_onMusicSearch'));
  check('T2: pas de _selectMusic', !storyViewSrc.includes('_selectMusic'));
  check('T2: pas de _syncMusicLabel', !storyViewSrc.includes('_syncMusicLabel'));
  check('T2: pas de _musicItems', !storyViewSrc.includes('_musicItems'));
  check('T2: pas d\'ecriture ig_audio', !storyViewSrc.includes('ig_audio'));

  const storyEditorSrc = read('../../src/public/js/editors/PublisherStoryEditor.js');
  check('T2: PublisherStoryEditor sans searchInstagramMusic', !storyEditorSrc.includes('searchInstagramMusic'));
}

// ---------- T3 : resolveDraftMusic ----------
const musicRaw = read('../../src/public/js/components/PublisherMusicStep.js');
const musicCode = musicRaw.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
const musicSrc = strip(musicRaw);
const sharedStore = {
  draft: {
    music: { trackId: null, start: 0, end: 0, volume: 1, source: null },
    design: { slides: [], designDocuments: [{ elements: [] }] },
  },
  _listeners: [],
  subscribe(fn) { this._listeners.push(fn); return () => {}; },
  setMusic(cfg) {
    this.draft.music = { ...this.draft.music, ...cfg };
    this._listeners.forEach(fn => fn({ draft: this.draft }));
  },
};
const { resolveDraftMusic, PublisherMusicStep, previewUrlFor } = new Function(
  'publisherStore',
  'searchInstagramMusic',
  'getStoryAudioProposals',
  `${musicSrc}\nreturn { resolveDraftMusic, PublisherMusicStep, previewUrlFor };`,
)(sharedStore, async () => ({ items: [] }), async () => ({ items: [] }));

{
  console.log('T3: resolveDraftMusic — draft.music, legacy et cleared');
  const flat = resolveDraftMusic({
    music: { trackId: 'a1', title: 'Run Free', artist: 'DJ X', source: 'instagram' },
    design: {},
  });
  check('T3: selection draft.music', flat?.trackId === 'a1' && flat?.title === 'Run Free' && flat?.source === 'instagram');

  const empty = resolveDraftMusic({
    music: { trackId: null, start: 0, end: 0, volume: 1, source: null },
    design: {},
  });
  check('T3: brouillon sans musique -> null', empty === null);

  const legacyTop = resolveDraftMusic({
    music: {},
    design: { ig_audio: { audio_id: 'old1', title: 'Ancienne', artist: 'Avant' } },
  });
  check('T3: legacy design.ig_audio (top-level)', legacyTop?.trackId === 'old1' && legacyTop?.title === 'Ancienne');

  const legacySlide = resolveDraftMusic({
    music: {},
    design: { designDocuments: [{ elements: [] }, { ig_audio: { audio_id: 'old2', title: 'Par slide' }, elements: [] }] },
  });
  check('T3: legacy designDocuments[].ig_audio', legacySlide?.trackId === 'old2' && legacySlide?.title === 'Par slide');

  const cleared = resolveDraftMusic({
    music: { trackId: null, cleared: true },
    design: { ig_audio: { audio_id: 'old1', title: 'Ancienne' } },
  });
  check('T3: cleared masque le legacy', cleared === null);

  const orchestrator = resolveDraftMusic({
    music: { source: 'instagram', ig_audio: { audio_id: 'cfg1', title: 'Auto', artist: 'Meta' }, local_track: null },
    design: {},
  });
  check('T3: forme audio_configuration (orchestrateur)', orchestrator?.trackId === 'cfg1' && orchestrator?.title === 'Auto');

  const local = resolveDraftMusic({
    music: { source: 'local', ig_audio: null, local_track: { track_id: 't9', title: 'Piste locale', artist: 'Forge' } },
    design: {},
  });
  check('T3: forme local_track', local?.trackId === 't9' && local?.source === 'local');
}

// ---------- T4 : PublisherMusicStep — recherche / selection / retrait ----------
function makeEl() {
  const handlers = {};
  const subs = new Map();
  return {
    innerHTML: '',
    hidden: false,
    value: '',
    textContent: '',
    querySelector(sel) {
      if (!subs.has(sel)) subs.set(sel, makeEl());
      return subs.get(sel);
    },
    addEventListener(type, fn) { (handlers[type] ||= []).push(fn); },
    __fire(type, event) {
      let result;
      (handlers[type] || []).forEach(fn => { result = fn(event); });
      return result;
    },
    __subs: subs,
  };
}

{
  console.log('T4: PublisherMusicStep — recherche, selection, retrait, aperçu local');
  check('T4: aucun lecteur audio injecté dans le brouillon', !/<audio\b/i.test(musicCode) && !musicRaw.includes('new Audio('));

  const store = sharedStore;
  store.draft.music = { trackId: null, start: 0, end: 0, volume: 1, source: null };
  store.draft.design = { slides: [], designDocuments: [{ elements: [] }] };
  const searchCalls = [];
  const searchOk = async (query) => {
    searchCalls.push(query);
    return { items: [{ audio_id: 'a1', title: 'Run Free', display_artist: 'DJ X', duration_in_ms: 90000, download_url: 'https://audio.example/preview.mp3', on_platform_audio_preview_link: 'https://www.instagram.com/reel/abc/' }] };
  };

  const step = new PublisherMusicStep({ searchInstagramMusic: searchOk });
  const host = makeEl();
  step.mount(host);

  const current = host.__subs.get('[data-music-current]');
  check('T4: etat initial sans musique', current.innerHTML.includes('Aucune musique sélectionnée'));

  const form = host.__subs.get('[data-music-form]');
  const input = form.querySelector('input');
  input.value = 'a';
  await form.__fire('submit', { preventDefault() {} });
  check('T4: requete < 2 caracteres ignoree', searchCalls.length === 0);

  input.value = 'run music';
  await form.__fire('submit', { preventDefault() {} });
  check('T4: recherche effectuee', searchCalls.length === 1 && searchCalls[0] === 'run music');
  check('T4: resultats rendus', host.__subs.get('[data-music-results]').innerHTML.includes('Run Free'));
  check('T4: aperçu proposé dans les résultats', host.__subs.get('[data-music-results]').innerHTML.includes('data-music-preview'));
  check('T4: compteur de resultats', host.__subs.get('[data-music-status]').textContent === '1 résultat(s)');

  const designBefore = JSON.stringify(store.draft.design);
  await host.__subs.get('[data-music-results]').__fire('click', {
    target: { closest: () => ({ dataset: { musicIndex: '0' } }) },
  });
  check('T4: selection ecrite dans draft.music', store.draft.music.trackId === 'a1' && store.draft.music.source === 'instagram' && store.draft.music.cleared === false);
  check('T4: selection rendue avec statut', current.innerHTML.includes('Run Free') && current.innerHTML.includes('non intégrable à la publication actuelle'));
  check('T4: aperçu disponible après selection', current.innerHTML.includes('data-action="music-preview"'));
  check('T4: panneau referme apres selection', host.__subs.get('[data-music-panel]').hidden === true);
  check('T4: design documents non modifies par la selection', JSON.stringify(store.draft.design) === designBefore);
  check('T4: aucune ecriture ig_audio dans le design', !JSON.stringify(store.draft.design).includes('ig_audio'));

  await current.__fire('click', { target: { closest: () => ({ dataset: { action: 'music-remove' } }) } });
  check('T4: retrait -> cleared', store.draft.music.cleared === true);
  check('T4: retrait -> rendu vide', current.innerHTML.includes('Aucune musique sélectionnée'));
  check('T4: retrait -> resolveDraftMusic null', resolveDraftMusic(store.draft) === null);

  const failingStep = new PublisherMusicStep({ searchInstagramMusic: async () => { throw new Error('Meta indisponible'); } });
  const failingHost = makeEl();
  failingStep.mount(failingHost);
  const failingForm = failingHost.__subs.get('[data-music-form]');
  failingForm.querySelector('input').value = 'rock';
  await failingForm.__fire('submit', { preventDefault() {} });
  check('T4: erreur de recherche affichee', failingHost.__subs.get('[data-music-status]').textContent === 'Meta indisponible');

  const emptyStep = new PublisherMusicStep({ searchInstagramMusic: async () => ({ items: [] }) });
  const emptyHost = makeEl();
  emptyStep.mount(emptyHost);
  const emptyForm = emptyHost.__subs.get('[data-music-form]');
  emptyForm.querySelector('input').value = 'introuvable';
  await emptyForm.__fire('submit', { preventDefault() {} });
  check('T4: recherche vide honnete', emptyHost.__subs.get('[data-music-status]').textContent === 'Aucune musique trouvée.');

  step.destroy();
  failingStep.destroy();
  emptyStep.destroy();
}

// ---------- T4b : aperçu audio local, jamais dans le brouillon ----------
{
  console.log('T4b: URL d\'aperçu validée et lecture locale sans écriture du brouillon');
  check('T4b: download_url Meta accepté', previewUrlFor({ download_url: 'https://audio.example/a.mp3' }) === 'https://audio.example/a.mp3');
  check('T4b: preview_link accepté', previewUrlFor({ preview_link: 'https://audio.example/b.mp3' }).includes('/b.mp3'));
  check('T4b: page instagram.com refusée comme audio', previewUrlFor({ on_platform_audio_preview_link: 'https://www.instagram.com/reel/abc/' }) === '');
  check('T4b: javascript: refusé', previewUrlFor({ preview_link: 'javascript:alert(1)' }) === '');
  check('T4b: aucun aperçu sans URL', previewUrlFor({ audio_id: 'x' }) === '');

  const store = sharedStore;
  store.draft = { music: { trackId: null }, design: {} };
  const step = new PublisherMusicStep({ searchInstagramMusic: async () => ({ items: [] }) });
  const host = makeEl();
  step.mount(host);
  const before = JSON.stringify(store.draft);
  step._togglePreview({ audio_id: 'a1', download_url: 'https://audio.example/a.mp3' });
  check('T4b: lecture locale sans URL injectée dans draft.music', JSON.stringify(store.draft) === before);
  check('T4b: URL mémorisée en mémoire uniquement', step._previews.get('a1') === 'https://audio.example/a.mp3');
  step.destroy();
}

// ---------- T5 : persistance publisherDraftService (API) ----------
{
  console.log('T5: sauvegarde/restauration API — audio_configuration, jamais design.ig_audio');
  const serviceRaw = read('../../src/public/js/services/publisherDraftService.js');
  const importNames = [];
  for (const match of serviceRaw.matchAll(/import\s*\{([^}]+)\}\s*from\s*['"][^'"]+['"];?/g)) {
    for (const part of match[1].split(',')) {
      const name = part.trim().split(/\s+as\s+/).pop().trim();
      if (name) importNames.push(name);
    }
  }
  check('T5: imports extraits (updateStoryDraft, updateStudioDraft, getStoryDraft)', ['updateStoryDraft', 'updateStudioDraft', 'getStoryDraft', 'publisherStore'].every(n => importNames.includes(n)));

  const captured = {};
  let storyDraftResponse = {
    id: 42,
    slides: [],
    design_documents: [],
    caption: null,
    hashtags: null,
    audio_configuration: null,
    status: 'editing',
    selected_asset_ids: [],
    render_jobs: [],
    publication_results: [],
    created_at: null,
    updated_at: null,
  };
  const makeApi = (name) => async (...args) => {
    (captured[name] ||= []).push(args);
    if (name === 'getStoryDraft') return { ...storyDraftResponse, id: args[0] };
    if (name === 'getStudioDraft') {
      return {
        id: args[0], design: {}, title: '', content: '', hashtags: '', status: 'draft',
        photo_id: null, content_type: 'post', visual_type: null, calendar_entry_id: null,
        created_at: null, updated_at: null,
      };
    }
    return { id: 1 };
  };
  const storeStub = { draft: {}, _notify() {}, getState() { return { draft: this.draft, ui: {} }; } };
  const deps = importNames.map(name => (name === 'publisherStore' ? storeStub : makeApi(name)));
  const { PublisherDraftService } = new Function(
    ...importNames,
    `${strip(serviceRaw)}\nreturn { PublisherDraftService };`,
  )(...deps);

  const svc = new PublisherDraftService();
  svc.currentDraftId = 42;
  svc.currentDraftType = 'story';
  const music = { trackId: 'a1', title: 'Run Free', artist: 'DJ X', source: 'instagram', cleared: false };
  await svc.save({
    music,
    design: { slides: [{ type: 'photo' }], designDocuments: [{ elements: [] }] },
    caption: { title: 'Titre', content: 'Contenu', hashtags: '#trail' },
  });
  const storyCall = captured.updateStoryDraft[0];
  check('T5: save story -> PATCH story-studio/draft/42', storyCall?.[0] === 42);
  check('T5: audio_configuration porte la musique', deepEq(storyCall[1].audio_configuration, music));
  check('T5: design transmis sans ig_audio', storyCall[1].design && !('ig_audio' in storyCall[1].design));
  check('T5: design documents sans musique', (storyCall[1].design.designDocuments || []).every(doc => !('ig_audio' in doc)));
  check('T5: aucune ecriture ig_audio globale', !('ig_audio' in storyCall[1]));
  check('T5: save story n appelle pas updateStudioDraft', !captured.updateStudioDraft);

  const svcStudio = new PublisherDraftService();
  svcStudio.currentDraftId = 7;
  svcStudio.currentDraftType = 'studio';
  await svcStudio.save({
    music: { trackId: null, start: 0, end: 0, volume: 1, source: null },
    design: { elements: [], ig_audio: { audio_id: 'reel1', title: 'Reel Track' } },
  });
  const studioCall = captured.updateStudioDraft[0];
  check('T5: save studio -> PATCH studio/draft/7', studioCall?.[0] === 7);
  check('T5: studio — design.ig_audio reel conserve', studioCall[1].design?.ig_audio?.audio_id === 'reel1');
  check('T5: studio — pas de pliage draft.music dans design', studioCall[1].design?.ig_audio?.trackId === undefined);
  check('T5: studio — pas audio_configuration', !('audio_configuration' in studioCall[1]));

  storyDraftResponse = {
    id: 9,
    slides: [{ type: 'photo' }],
    design_documents: [{ ig_audio: { audio_id: 'old1', title: 'Ancienne', artist: 'Avant' }, elements: [] }],
    audio_configuration: { trackId: 'cfg1', title: 'Configurée', source: 'instagram' },
    caption: null,
    hashtags: null,
    status: 'editing',
    selected_asset_ids: [11],
    render_jobs: [],
    publication_results: [],
    created_at: null,
    updated_at: null,
  };
  const svcLoad = new PublisherDraftService();
  await svcLoad.loadStory(9);
  check('T5: restauration audio_configuration -> draft.music', storeStub.draft.music?.trackId === 'cfg1');
  check('T5: restauration legacy design_documents conserve', storeStub.draft.design?.designDocuments?.[0]?.ig_audio?.audio_id === 'old1');
  check('T5: selection resolue apres restauration', resolveDraftMusic(storeStub.draft)?.trackId === 'cfg1');
}

// ---------- T6 : store — musique independante des slides ----------
{
  console.log('T6: store — draft.music isole des design documents et des steps');
  const storeRaw = read('../../src/public/js/stores/publisherStore.js');
  const localStorageStub = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  const loaded = new Function(
    'localStorage',
    `${strip(storeRaw)}\nreturn { FORMAT_CONFIG, PublisherStore };`,
  )(localStorageStub);
  const store = new loaded.PublisherStore();

  check('T6: FORMAT_CONFIG store story avec music', deepEq(loaded.FORMAT_CONFIG.story.steps, EXPECTED_STORY_STEPS));
  store.resetDraft('story');
  store.setMusic({ trackId: 'a2', title: 'Trail Song', artist: 'Runner', source: 'instagram' });
  const musicBefore = JSON.stringify(store.draft.music);
  store.updateStorySlides([{ type: 'photo', photo_indices: [0] }], [{ elements: [] }]);
  check('T6: updateStorySlides ne touche pas music', JSON.stringify(store.draft.music) === musicBefore);
  check('T6: selection resolue stable apres sauvegarde compose', resolveDraftMusic(store.draft)?.trackId === 'a2');
  store.updateStorySlides([{ type: 'photo', photo_indices: [0] }, { type: 'photo', photo_indices: [1] }], [{ elements: [] }, { elements: [] }]);
  check('T6: changement de slide sans effet sur music', resolveDraftMusic(store.draft)?.trackId === 'a2');
  store.setStep && store.setStep('compose');
  check('T6: selection resolue apres navigation etape', resolveDraftMusic(store.draft)?.trackId === 'a2');
  check('T6: music jamais ecrite dans designDocuments', !JSON.stringify(store.draft.design).includes('ig_audio'));
}

// ---------- T7 : non-regression Reel / Post / Carrousel ----------
{
  console.log('T7: non-regression — Reel garde son systeme musical, post/carrousel inchanges');
  const reelSrc = read('../../src/public/js/editors/PublisherReelEditor.js');
  check('T7: Reel — panneau musique present', reelSrc.includes('data-music-panel') && reelSrc.includes('_selectMusic'));
  check('T7: Reel — recherche Instagram present', reelSrc.includes('searchInstagramMusic'));
  check('T7: Reel — ecriture design.ig_audio presente', reelSrc.includes('ig_audio'));

  const previewSrc = read('../../src/public/js/components/PublisherPreview.js');
  check('T7: apercu Reel — pp-reel-music conserve', previewSrc.includes('pp-reel-music'));

  const pageSrc = read('../../src/public/js/pages/CommunityPublisherPage.js');
  check('T7: Reel — compose minimal (plus de StudioEditorView)',
    /createPublisherMinimalComposer\(/.test(pageSrc) && !/createPublisherReelEditor\(/.test(pageSrc));
  check('T7: pas de music step pour reel/post/carrousel', !extractSteps(pageSrc, 'reel').includes('music') && !extractSteps(pageSrc, 'post').includes('music') && !extractSteps(pageSrc, 'carousel').includes('music'));
}

// ---------- T8 : présélection IA à l'ouverture ----------
{
  console.log('T8: présélection IA à l’ouverture de l’étape Musique');
  const apiRaw = read('../../src/public/js/services/sportApi.js');
  check('T8: wrapper Story audio-proposals', apiRaw.includes('/story-studio/draft/${encodeURIComponent(draftId)}/audio-proposals'));
  const pageSrc = read('../../src/public/js/pages/CommunityPublisherPage.js');
  check('T8: page passe publicationId au composant', /publicationId:\s*publisherDraftService\.currentDraftType === 'story'/.test(pageSrc));
  check('T8: endpoint backend Story', read('../../app/api/community_manager.py').includes('/story-studio/draft/{draft_id}/audio-proposals'));

  const calls = [];
  const suggest = async (id) => {
    calls.push(id);
    return {
      items: [{ audio_id: 'ai1', title: 'Photo Mix', display_artist: 'IA', duration_in_ms: 120000 }],
      reason: 'Analyse IA des photos de la Story',
    };
  };
  const fresh = (id = 42) => ({
    id,
    format: 'story',
    music: { trackId: null, start: 0, end: 0, volume: 1, source: null },
    design: { slides: [], designDocuments: [{ elements: [] }] },
  });
  const flush = async () => { for (let i = 0; i < 5; i += 1) await Promise.resolve(); };

  sharedStore.draft = fresh();
  const host = makeEl();
  const step = new PublisherMusicStep({ getStoryAudioProposals: suggest, publicationId: 42 });
  step.mount(host);
  await flush();
  check('T8: endpoint appelé avec le brouillon', calls.length === 1 && calls[0] === 42);
  check('T8: première piste présélectionnée', sharedStore.draft.music.trackId === 'ai1' && sharedStore.draft.music.preselectedBy === 'ai');
  check('T8: libellé Présélection IA', host.__subs.get('[data-music-current]').innerHTML.includes('Présélection IA'));
  check('T8: message masqué après succès', host.__subs.get('[data-music-suggestion]').hidden === true);

  step._select({ audio_id: 'manual', title: 'Manual', display_artist: 'Moi' });
  check('T8: remplacement manuel efface le drapeau IA', sharedStore.draft.music.trackId === 'manual' && sharedStore.draft.music.preselectedBy === null);

  sharedStore.draft = fresh();
  sharedStore.draft.music = { trackId: 'kept', title: 'Déjà choisi', source: 'instagram' };
  const keptHost = makeEl();
  const keptStep = new PublisherMusicStep({ getStoryAudioProposals: suggest, publicationId: 42 });
  keptStep.mount(keptHost);
  await flush();
  check('T8: choix existant non écrasé', calls.length === 1 && sharedStore.draft.music.trackId === 'kept');

  sharedStore.draft = fresh();
  sharedStore.draft.music = { cleared: true, trackId: null };
  const clearedHost = makeEl();
  const clearedStep = new PublisherMusicStep({ getStoryAudioProposals: suggest, publicationId: 42 });
  clearedStep.mount(clearedHost);
  await flush();
  check('T8: retrait explicite non réouvert', calls.length === 1);

  sharedStore.draft = fresh(null);
  const noIdHost = makeEl();
  const noIdStep = new PublisherMusicStep({ getStoryAudioProposals: suggest });
  noIdStep.mount(noIdHost);
  await flush();
  check('T8: sans brouillon serveur, aucun appel', calls.length === 1);

  sharedStore.draft = fresh();
  const slowHost = makeEl();
  let resolveSlow;
  const slowStep = new PublisherMusicStep({
    getStoryAudioProposals: () => new Promise((resolve) => { resolveSlow = resolve; }),
    publicationId: 42,
  });
  slowStep.mount(slowHost);
  slowHost.__subs.get('[data-action="music-open"]').__fire('click');
  resolveSlow({ items: [{ audio_id: 'tardive', title: 'Trop tard' }] });
  await flush();
  check('T8: interaction manuelle annule une présélection tardive', sharedStore.draft.music.trackId === null);

  sharedStore.draft = fresh();
  const failHost = makeEl();
  const failStep = new PublisherMusicStep({
    getStoryAudioProposals: async () => { throw new Error('IA indisponible'); },
    publicationId: 42,
  });
  failStep.mount(failHost);
  await flush();
  check('T8: échec IA message visible',
    failHost.__subs.get('[data-music-suggestion]').hidden === false
    && failHost.__subs.get('[data-music-suggestion]').textContent === 'IA indisponible');

  step.destroy();
  keptStep.destroy();
  clearedStep.destroy();
  noIdStep.destroy();
  slowStep.destroy();
  failStep.destroy();
}

console.log(failures.length === 0 ? '\nTOUS LES TESTS PASSENT' : `\n${failures.length} ECHEC(S)`);
process.exit(failures.length === 0 ? 0 : 1);
