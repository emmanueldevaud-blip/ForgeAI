// Tests — Transmission des médias vers le Composer Story (PublisherStoryEditor)
// Exécution : node tests/frontend/publisher_story_media_transmission.test.mjs
import fs from 'node:fs';

const FILE = new URL('../../src/public/js/editors/PublisherStoryEditor.js', import.meta.url);

const failures = [];
function check(name, cond) {
  if (cond) console.log(`  OK ${name}`);
  else { failures.push(name); console.log(`  KO ${name}`); }
}

function baseMedia() {
  return [
    {
      id: 'photo_11', url: '/photos/11/file', thumbnail_url: '/photos/11/file?size=small',
      crop: { x: 0, y: 0, w: 1, h: 1 }, order: 0, type: 'photo', source: 'library', garminActivityId: null,
    },
    {
      id: 'photo_12', url: '/photos/12/file', thumbnail_url: '/photos/12/file?size=small',
      crop: { x: 0, y: 0, w: 1, h: 1 }, order: 1, type: 'photo', source: 'library', garminActivityId: null,
    },
  ];
}

function makeDraft({ media = baseMedia(), design = {}, format = 'story' } = {}) {
  return {
    id: null,
    format,
    media,
    design,
    caption: { title: '', content: '', hashtags: '', accountId: null },
    music: { trackId: null, start: 0, end: 0, volume: 1, source: null },
    garmin: { activityId: null, stats: {}, overlays: [] },
    status: 'draft',
    createdAt: null,
    updatedAt: null,
    sourceEntryId: null,
  };
}

function mountStoryDraft(draft) {
  let src = fs.readFileSync(FILE, 'utf8');
  src = src.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
  src = src.replace(/export class/g, 'class');
  src = src.replace(/export function/g, 'function');

  const captured = { storyDraft: null };
  const publisherStore = {
    draft,
    subscribe() { return () => {}; },
    updateStorySlides() {},
    setStep() {},
  };
  const createStoryEditorView = (options) => {
    captured.storyDraft = options.draft;
    return { mount() {}, destroy() {} };
  };
  const factory = new Function(
    'publisherStore',
    'createStoryEditorView',
    'listPhotos',
    'uploadPhotos',
    'searchInstagramMusic',
    `${src}\nreturn { PublisherStoryEditor, createPublisherStoryEditor };`
  );
  const { PublisherStoryEditor } = factory(
    publisherStore, createStoryEditorView, () => {}, () => {}, () => {}
  );
  const editor = new PublisherStoryEditor({ onSave() {}, onBack() {} });
  editor.element = { querySelector: () => ({ appendChild() {} }) };
  editor._mountStoryEditor();
  return captured.storyDraft;
}

console.log('1. Transmission de deux photos (design = {})');
{
  const d = mountStoryDraft(makeDraft());
  check('2 slides construites depuis les médias', Array.isArray(d.slides) && d.slides.length === 2);
  check('2 design documents construits', Array.isArray(d.design_documents) && d.design_documents.length === 2);
  check('photo_id slide 1 = 11', d.design_documents[0]?.background?.photo_id === 11);
  check('photo_id slide 2 = 12', d.design_documents[1]?.background?.photo_id === 12);
}

console.log('2. Brouillon API / setFormat : design.slides = [] et designDocuments = []');
{
  const d = mountStoryDraft(makeDraft({ design: { slides: [], designDocuments: [] } }));
  check('slides reconstruites (2)', Array.isArray(d.slides) && d.slides.length === 2);
  check('design documents reconstruits (2)', Array.isArray(d.design_documents) && d.design_documents.length === 2);
  check('identifiants préservés [11,12]',
    d.design_documents.map((x) => x.background.photo_id).join(',') === '11,12');
}

console.log('3. Conservation de l’ordre des photos');
{
  const media = [
    { ...baseMedia()[1], order: 0 },
    { ...baseMedia()[0], order: 1 },
  ];
  const d = mountStoryDraft(makeDraft({ media, design: { slides: [], designDocuments: [] } }));
  check('ordre du draft respecté (12 puis 11)',
    d.design_documents.map((x) => x.background.photo_id).join(',') === '12,11');
  check('photo_indices alignés sur l’ordre',
    d.slides.map((s) => s.photo_indices[0]).join(',') === '0,1');
}

console.log('4. Conservation des identifiants (avec et sans préfixe photo_)');
{
  const media = [
    { ...baseMedia()[0], id: '11' },
    { ...baseMedia()[1], id: 'photo_12' },
  ];
  const d = mountStoryDraft(makeDraft({ media, design: { slides: [], designDocuments: [] } }));
  check('ids normalisés en nombres [11,12]',
    d.design_documents.map((x) => x.background.photo_id).join(',') === '11,12');
  check('carousel aligné sur l’id',
    d.design_documents[0].carousel[0] === 11 && d.design_documents[1].carousel[0] === 12);
}

console.log('5. Conservation des ajustements (crop issu d’Adjust)');
{
  const crop = { x: 0.1, y: 0.2, w: 0.5, h: 0.6 };
  const media = baseMedia().map((m, i) => ({ ...m, crop: { ...crop }, order: i }));
  const d = mountStoryDraft(makeDraft({ media, design: { slides: [], designDocuments: [] } }));
  check('crop du média propagé dans le document',
    JSON.stringify(d.design_documents[0].background.crop) === JSON.stringify(crop));
  check('crop identique sur les deux documents',
    JSON.stringify(d.design_documents[1].background.crop) === JSON.stringify(crop));
}

console.log('6. Slides stockés préservés (pas de réinitialisation à l’ouverture)');
{
  const storedSlides = [{ type: 'photo', photo_indices: [0], hook: 'Mon hook' }];
  const storedDocs = [{
    version: 2,
    format: { width: 1080, height: 1920, type: 'story_916', platform: 'instagram' },
    background: { type: 'photo', photo_id: 11, crop: { x: 0, y: 0, w: 1, h: 1 } },
    elements: [{ type: 'text', text: 'Bonjour' }],
    carousel: [11],
    timeline: { fps: 30, tracks: [] },
  }];
  const d = mountStoryDraft(makeDraft({ design: { slides: storedSlides, designDocuments: storedDocs } }));
  check('slides stockés repris à l’identique', d.slides === storedSlides);
  check('design documents stockés repris à l’identique', d.design_documents === storedDocs);
}

console.log('7. Absence de duplication des slides');
{
  const d = mountStoryDraft(makeDraft({ design: { slides: [], designDocuments: [] } }));
  check('2 médias -> exactement 2 slides', d.slides.length === 2);
  check('2 médias -> exactement 2 documents', d.design_documents.length === 2);
  const d2 = mountStoryDraft(makeDraft());
  check('sans design -> 2 slides (pas 4)', d2.slides.length === 2);
}

console.log('8. Navigation Adjust -> Composer -> Adjust (suppression d’une photo)');
{
  let media = baseMedia();
  const avant = mountStoryDraft(makeDraft({ media, design: { slides: [], designDocuments: [] } }));
  check('avant : 2 slides', avant.slides.length === 2);
  media = media.slice(0, 1);
  const apres = mountStoryDraft(makeDraft({ media, design: { slides: [], designDocuments: [] } }));
  check('après retour : 1 slide', apres.slides.length === 1 && apres.design_documents.length === 1);
  check('la photo restante est la bonne (11)',
    apres.design_documents[0].background.photo_id === 11);
}

console.log('9. Réouverture du brouillon (état restauré depuis localStorage)');
{
  const restored = makeDraft({ design: { slides: [], designDocuments: [] } });
  const d = mountStoryDraft(restored);
  check('slides reconstruites à la réouverture', d.slides.length === 2);
  check('identifiants préservés à la réouverture',
    d.design_documents.map((x) => x.background.photo_id).join(',') === '11,12');
}

console.log('10. Médias vides (pas de crash, pas de slide fantôme)');
{
  const d = mountStoryDraft(makeDraft({ media: [], design: {} }));
  check('slides vides', Array.isArray(d.slides) && d.slides.length === 0);
  check('design documents vides', Array.isArray(d.design_documents) && d.design_documents.length === 0);
  const d2 = mountStoryDraft(makeDraft({ media: [], design: { slides: [], designDocuments: [] } }));
  check('idem avec tableaux stockés vides', d2.slides.length === 0 && d2.design_documents.length === 0);
}

console.log('11. Non-régression : seul le format story utilise PublisherStoryEditor');
{
  const pageSrc = fs.readFileSync(
    new URL('../../src/public/js/pages/CommunityPublisherPage.js', import.meta.url), 'utf8'
  );
  check('compose story -> createPublisherStoryEditor',
    /format === 'story'[\s\S]{0,400}createPublisherStoryEditor\(/.test(pageSrc));
  check('compose reel -> createPublisherReelEditor (inchangé)',
    /format === 'reel'[\s\S]{0,400}createPublisherReelEditor\(/.test(pageSrc));
  check('post/carrousel : aucun éditeur compose (auto-pass)',
    /Post\/Carrousel ne passent pas par compose/.test(pageSrc));
}

if (failures.length > 0) {
  console.log(`\n${failures.length} échec(s) :`);
  failures.forEach((f) => console.log(` - ${f}`));
  process.exit(1);
}
console.log('\nTous les tests de transmission médias -> Composer sont OK.');
