import assert from 'node:assert/strict';
import fs from 'node:fs';

const file = new URL('../../src/public/js/pages/GarminQuickPublicationView.js', import.meta.url);
let source = fs.readFileSync(file, 'utf8');
source = source.replace(/^import\s*\{[\s\S]*?\}\s*from\s+['"][^'"]+['"];?\s*$/m, '');
source = source.replace(/export class/g, 'class').replace(/export function/g, 'function');

const outputStep = { innerHTML: '' };
const captionStep = { innerHTML: '' };
const element = {
  className: '',
  innerHTML: '',
  querySelector(selector) {
    if (selector === '[data-step="4"]') return captionStep;
    if (selector === '[data-step="5"]') return outputStep;
    return null;
  },
  querySelectorAll() { return []; },
};
const documentStub = { createElement: () => element };
const windowStub = {};
const dependencyNames = [
  'companionVideoUrl', 'getStudioDraft', 'getSuggestedPhotos', 'publishStudioDraftBoth',
  'updateStudioDraft', 'validateStudioDraft', 'searchStudioMusic', 'getEditorialBrief',
  'regeneratePublicationContent', 'getLocalStudioMusic', 'getStudioAudioMatch', 'getStudioAudioProposals',
];
const dependencyImpl = {};
const dependencyStubs = Object.fromEntries(dependencyNames.map(name => [
  name,
  (...args) => dependencyImpl[name] ? dependencyImpl[name](...args) : Promise.resolve({}),
]));
const { GarminQuickPublicationView } = new Function('document', 'window', ...dependencyNames, `${source}\nreturn { GarminQuickPublicationView };`)(
  documentStub,
  windowStub,
  ...dependencyNames.map(name => dependencyStubs[name]),
);

const page = new GarminQuickPublicationView(7);
page.publication = { status: 'draft', companion_video_status: 'pending', design: {} };
page.selected = [11];
page.editedTitle = 'Sortie trail';
page.render();
assert.match(outputStep.innerHTML, /data-action="publish" disabled/);
assert.match(outputStep.innerHTML, /Créer l’aperçu/);

page.publication.companion_video_status = 'ready';
page.videoReady = true;
page.videoUrl = 'blob:preview';
page.render();
assert.match(outputStep.innerHTML, /garmin-final-preview/);
assert.match(outputStep.innerHTML, /data-action="publish"(?![^>]*disabled)/);

page.videoReady = false;
await page._publish();
assert.match(page.error, /Générez et vérifiez l’aperçu vidéo/);
assert.equal(page.busy, false);

const publishCalls = [];
dependencyImpl.updateStudioDraft = async (...args) => { publishCalls.push(['save', ...args]); return publishablePage.publication; };
dependencyImpl.validateStudioDraft = async (...args) => { publishCalls.push(['validate', ...args]); };
dependencyImpl.publishStudioDraftBoth = async (...args) => { publishCalls.push(['publish', ...args]); };
dependencyImpl.getStudioDraft = async (...args) => { publishCalls.push(['reload', ...args]); return { status: 'shared' }; };
// Remplacer les dépendances injectées par la suite pour tester le chemin de succès.
const publishablePage = new GarminQuickPublicationView(7);
publishablePage.publication = { status: 'draft', companion_video_status: 'ready', design: {} };
publishablePage.selected = [11, 12];
publishablePage.videoReady = true;
publishablePage.videoUrl = 'blob:preview';
publishablePage.editedTitle = 'Sortie trail';
publishablePage.editedHashtags = '#trail';
publishablePage.render = () => element;
await publishablePage._publish();
assert.deepEqual(publishCalls.map(([name]) => name), ['save', 'validate', 'publish', 'reload']);
assert.deepEqual(publishCalls[0][2], { title: 'Sortie trail', hashtags: '#trail' });

let playCalls = 0;
const audio = {
  paused: true,
  muted: true,
  volume: 0,
  play() { playCalls += 1; this.paused = false; return Promise.resolve(); },
  pause() { this.paused = true; },
};
windowStub.Audio = class { constructor() { return audio; } };
page.element = {
  querySelectorAll() { return []; },
  querySelector() { return null; },
};
page._toggleProposalAudio({ track_id: 'song-1', preview_link: '/preview.mp3' });
assert.equal(playCalls, 1);
assert.equal(audio.muted, false);
assert.equal(audio.volume, 1);
assert.equal(page.audioPlayingId, 'song-1');

console.log('Parcours Garmin frontend : aperçu/publication et lecture audio OK.');
