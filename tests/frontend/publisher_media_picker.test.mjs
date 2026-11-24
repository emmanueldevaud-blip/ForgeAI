import assert from 'node:assert/strict';
import fs from 'node:fs';

let source = fs.readFileSync(new URL('../../src/public/js/components/PublisherMediaPicker.js', import.meta.url), 'utf8');
source = source.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
source = source.replace(/export class/g, 'class').replace(/export function/g, 'function');
const store = { draft: { media: [
  { id: 'photo-a', url: '/photos/a/file', thumbnail_url: '/photos/a/small', type: 'photo' },
  { id: 'photo-b', url: '/photos/b/file', thumbnail_url: '/photos/b/small', type: 'photo' },
] } };
const { PublisherMediaPicker } = new Function(
  'publisherStore', 'listPhotos', 'uploadPhotos', 'listAlbums', 'listSportActivities', 'getSuggestedPhotos',
  `${source}\nreturn { PublisherMediaPicker };`,
)(store, async () => ({}), async () => ({}), async () => ({}), async () => ({}), async () => []);

const picker = new PublisherMediaPicker({ format: 'carousel' });
let removeHandler;
const stage = {
  innerHTML: '',
  querySelector(selector) {
    assert.equal(selector, '[data-preview-remove]');
    return { addEventListener(_type, handler) { removeHandler = handler; } };
  },
};
const position = { textContent: '' };
const mediaItems = store.draft.media.map(media => ({
  dataset: { previewMedia: media.id },
  classList: { toggle(name, active) { this[name] = active; } },
}));
picker.element = {
  querySelector(selector) {
    if (selector === '[data-selection-preview]') return { hidden: true };
    if (selector === '[data-preview-stage]') return stage;
    if (selector === '[data-preview-position]') return position;
    return null;
  },
  querySelectorAll: () => mediaItems,
};
picker.previewMediaId = 'photo-b';
picker._renderActivePreview();
assert.match(stage.innerHTML, /\/photos\/b\/file/);
assert.equal(position.textContent, '2 / 2 · 4:5');
assert.equal(mediaItems[1].classList.active, true);
assert.equal(typeof removeHandler, 'function');

console.log('Aperçu de sélection photo/carrousel et navigation OK.');
