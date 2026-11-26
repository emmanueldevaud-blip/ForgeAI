// Tests — Pipeline unique de publication Story (export -> upload -> validate -> publish).
// Exécution : node tests/frontend/story_publish_pipeline.test.mjs
import fs from 'node:fs';
import {
  exportStorySlides,
  publishStoryWithPipeline,
  storySlidesReady,
} from '../../src/public/js/services/storyPublishPipeline.js';

const failures = [];
function check(name, cond) {
  if (cond) console.log(`  OK ${name}`);
  else { failures.push(name); console.log(`  KO ${name}`); }
}

function design(photoId) {
  return {
    version: 2,
    format: { width: 1080, height: 1920, type: 'story_916', platform: 'instagram' },
    background: { type: 'photo', photo_id: photoId, crop: { x: 0, y: 0, w: 1, h: 1 } },
    elements: [],
    carousel: [photoId],
    timeline: { fps: 30, tracks: [] },
  };
}

console.log('1. Export/upload de chaque slide et renseignement de published_photo_id');
{
  const uploaded = [];
  const deps = {
    uploadPhotos: async (files) => {
      uploaded.push(files[0]);
      return { items: [{ id: 100 + uploaded.length }] };
    },
  };
  const result = await exportStorySlides({
    draftId: 7,
    slides: [{ type: 'photo', photo_indices: [0] }, { type: 'photo', photo_indices: [1] }],
    designDocuments: [design(11), design(12)],
    deps,
    renderSlide: async (doc, index) => ({ index, doc }),
  });
  check('2 slides exportées', result.slides.length === 2 && result.design_documents.length === 2);
  check('published_photo_id par slide',
    result.slides.map((s) => s.published_photo_id).join(',') === '101,102');
  check('upload d’un fichier JPEG par slide',
    uploaded.length === 2 && uploaded[0].name === 'story-7-1.jpg' && uploaded[1].name === 'story-7-2.jpg');
  check('designs préservés', result.design_documents[0].background.photo_id === 11);
}

console.log('2. Rendu hors écran sans canvas monté');
{
  const previousImage = globalThis.Image;
  const previousDocument = globalThis.document;
  const ctx = new Proxy({}, {
    get(target, prop) {
      if (prop === 'canvas') return null;
      if (!(prop in target)) target[prop] = () => {};
      return target[prop];
    },
    set(target, prop, value) { target[prop] = value; return true; },
  });
  globalThis.Image = class {
    set src(value) { this._src = value; this.naturalWidth = 1080; this.naturalHeight = 1920; this.onload?.(); }
  };
  globalThis.document = {
    createElement: () => ({
      width: 0,
      height: 0,
      style: {},
      getContext: () => ctx,
      toBlob: (cb) => cb(new Blob(['jpeg'], { type: 'image/jpeg' })),
    }),
  };
  try {
    const uploaded = [];
    const result = await exportStorySlides({
      draftId: 9,
      slides: [{}],
      designDocuments: [design(21)],
      deps: {
        photoFileUrl: (id, size) => `/photos/${id}/file?size=${size}`,
        uploadPhotos: async (files) => { uploaded.push(files[0]); return [{ id: 55 }]; },
      },
    });
    check('export hors écran aboutit', result.slides[0].published_photo_id === 55);
    check('fichier uploadé nommé', uploaded[0]?.name === 'story-9-1.jpg');
  } finally {
    globalThis.Image = previousImage;
    globalThis.document = previousDocument;
  }
}

console.log('3. Pipeline complet : sauvegarde -> validation -> publication');
{
  const calls = [];
  const api = {
    save: async (payload) => { calls.push(['save', payload]); },
    validate: async (id) => { calls.push(['validate', id]); },
    publish: async (id, data) => { calls.push(['publish', id, data]); return { jobs: [] }; },
  };
  await publishStoryWithPipeline({
    draftId: 7,
    slides: [{}],
    designDocuments: [design(11)],
    deps: { uploadPhotos: async () => [{ id: 77 }] },
    renderSlide: async () => new Blob(['jpeg'], { type: 'image/jpeg' }),
    api,
    platforms: ['instagram'],
    draftData: { caption: 'Ma story', hashtags: '#trail', audio_configuration: { trackId: null } },
  });
  check('ordre export -> save -> validate -> publish',
    calls.map((c) => c[0]).join(',') === 'save,validate,publish');
  check('save contient published_photo_id', calls[0][1].slides[0].published_photo_id === 77);
  check('save contient légende et audio',
    calls[0][1].caption === 'Ma story' && calls[0][1].hashtags === '#trail' && 'audio_configuration' in calls[0][1]);
  check('publish reçoit confirmation et plateformes',
    calls[2][2].confirm === true && calls[2][2].platforms[0] === 'instagram');
}

console.log('4. Échec d’export : aucun appel validate/publish');
{
  const calls = [];
  let caught = null;
  try {
    await publishStoryWithPipeline({
      draftId: 7,
      slides: [{}],
      designDocuments: [design(11)],
      deps: { uploadPhotos: async () => [] },
      renderSlide: async () => new Blob(['jpeg'], { type: 'image/jpeg' }),
      api: {
        save: async () => { calls.push('save'); },
        validate: async () => { calls.push('validate'); },
        publish: async () => { calls.push('publish'); },
      },
    });
  } catch (error) {
    caught = error;
  }
  check('erreur explicite si upload sans photo', /enregistrer la Story/.test(caught?.message || ''));
  check('aucune validation/publication après échec', calls.length === 0);
}

console.log('5. Statut « slides prêtes »');
{
  const ready = { slides: [{ published_photo_id: 5 }], designDocuments: [design(11)] };
  check('prêt si export + design alignés', storySlidesReady(ready) === true);
  check('non prêt sans published_photo_id',
    storySlidesReady({ slides: [{}], designDocuments: [design(11)] }) === false);
  check('non prêt sans slides', storySlidesReady({}) === false);
}

console.log('6. Câblage des deux points d’entrée');
{
  const read = (p) => fs.readFileSync(new URL(`../../src/public/js/${p}`, import.meta.url), 'utf8');
  const editor = read('editor/StoryEditorView.js');
  const service = read('services/publisherDraftService.js');
  const page = read('pages/CommunityPublisherPage.js');
  check('StoryEditorView utilise exportStorySlides', /exportStorySlides\(\{/.test(editor));
  check('StoryEditorView ne refait pas l’upload localement', !/this\.deps\.uploadPhotos\(\[file\]\)/.test(editor));
  check('publisherDraftService utilise publishStoryWithPipeline', /publishStoryWithPipeline\(\{/.test(service));
  check('Composer affiche le statut de rendu Story', /storySlidesReady\(design\)/.test(page));
}

if (failures.length > 0) {
  console.log(`\n${failures.length} échec(s) :`);
  failures.forEach((f) => console.log(` - ${f}`));
  process.exit(1);
}
console.log('\nTous les tests du pipeline Story sont OK.');
