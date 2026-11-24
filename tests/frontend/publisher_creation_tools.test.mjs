// Outils de création Community Publisher: emoji de légende et sélection audio Reel.
import assert from 'node:assert/strict';
import fs from 'node:fs';

function loadClass(path, name, args, deps) {
  let source = fs.readFileSync(new URL(path, import.meta.url), 'utf8');
  source = source.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
  source = source.replace(/export class/g, 'class').replace(/export function/g, 'function');
  return new Function(...args, `${source}\nreturn { ${name} };`)(...deps)[name];
}

const store = {
  draft: { design: { elements: [] }, caption: { content: '' } },
  updates: [],
  updateCaption(name, value) { this.updates.push([name, value]); this.draft.caption[name] = value; },
};
const PublisherCaptionEditor = loadClass(
  '../../src/public/js/components/PublisherCaptionEditor.js',
  'PublisherCaptionEditor', ['publisherStore', 'getMetaInstagramAccount'], [store, async () => ({})],
);
const captionEditor = new PublisherCaptionEditor();
const textarea = { value: 'Alpes', selectionStart: 3, selectionEnd: 3, focus() {}, setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; } };
captionEditor.element = { querySelector: () => textarea };
captionEditor._updateCounter = () => {};
captionEditor._insertEmoji('🔥');
assert.equal(textarea.value, 'Alp🔥es');
assert.deepEqual(store.updates.at(-1), ['content', 'Alp🔥es']);

const PublisherReelEditor = loadClass(
  '../../src/public/js/editors/PublisherReelEditor.js',
  'PublisherReelEditor',
  ['publisherStore', 'publisherDraftService', 'createStudioEditorView', 'listPhotos', 'photoFileUrl', 'uploadPhotos', 'searchStudioMusic'],
  [store, { currentDraftId: 17 }, () => ({}), () => {}, () => '', () => {}, async () => ({ items: [] })],
);
const reelEditor = new PublisherReelEditor();
const label = { textContent: '' };
const panel = { hidden: false };
reelEditor.element = { querySelector(selector) { return selector === '[data-music-panel]' ? panel : label; } };
let savedDesign;
reelEditor._updateDraft = async ({ design }) => { savedDesign = design; store.draft.design = design; };
await reelEditor._selectMusic({ audio_id: 'track-42', title: 'Run Free', display_artist: 'Example Artist', duration_in_ms: 90000 });
assert.equal(savedDesign.ig_audio.audio_id, 'track-42');
assert.equal(savedDesign.ig_audio.title, 'Run Free');
assert.equal(panel.hidden, true);
assert.match(label.textContent, /Run Free/);

console.log('Outils de légende emoji et de sélection de musique Reel OK.');
