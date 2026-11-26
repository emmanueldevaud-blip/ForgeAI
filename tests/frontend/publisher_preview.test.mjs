// Vérifie l’aperçu réellement rendu pour post, carrousel, Reel et Story.
import assert from 'node:assert/strict';
import fs from 'node:fs';

const file = new URL('../../src/public/js/components/PublisherPreview.js', import.meta.url);
let source = fs.readFileSync(file, 'utf8');
source = source.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
source = source.replace(/export class/g, 'class').replace(/export function/g, 'function');

const musicFile = new URL('../../src/public/js/components/PublisherMusicStep.js', import.meta.url);
let musicSource = fs.readFileSync(musicFile, 'utf8');
musicSource = musicSource.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
musicSource = musicSource.replace(/export class/g, 'class').replace(/export function/g, 'function');
const { resolveDraftMusic } = new Function('publisherStore', 'searchInstagramMusic', `${musicSource}\nreturn { resolveDraftMusic };`)({}, async () => ({ items: [] }));

const { PublisherPreview } = new Function('publisherStore', 'publisherDraftService', 'resolveDraftMusic', `${source}\nreturn { PublisherPreview };`)({}, {}, resolveDraftMusic);

const media = [
  { id: '10', url: '/photos/10/file', thumbnail_url: '/photos/10/file?size=small', type: 'photo' },
  { id: '11', url: '/photos/11/file', thumbnail_url: '/photos/11/file?size=small', type: 'photo' },
];
const draft = { media, caption: { title: 'Sortie', content: 'Dans les Alpes', hashtags: '#trail' }, music: {}, design: {} };

const carousel = new PublisherPreview({ format: 'carousel', draft });
const carouselHtml = carousel._render();
assert.doesNotMatch(carouselHtml, /Format non supporté/);
assert.match(carouselHtml, /Photo suivante/);
assert.match(carouselHtml, /data-carousel-index="1"/);
assert.match(carouselHtml, /\/photos\/10\/file/);
assert.match(carouselHtml, /\/photos\/11\/file/);

const makeClassList = () => ({ active: false, toggle(_name, value) { this.active = value; } });
const slides = [{ classList: makeClassList() }, { classList: makeClassList() }];
const dots = [{ classList: makeClassList() }, { classList: makeClassList() }];
const nav = [{ dataset: { carouselNav: '-1' } }, { dataset: { carouselNav: '1' } }];
const count = { textContent: '' };
carousel.element = {
  querySelectorAll(selector) {
    if (selector === '.pp-carousel-slide') return slides;
    if (selector === '[data-carousel-index]') return dots;
    if (selector === '[data-carousel-nav]') return nav;
    return [];
  },
  querySelector: () => count,
};
carousel._setCarouselIndex(1);
assert.equal(slides[0].classList.active, false);
assert.equal(slides[1].classList.active, true);
assert.equal(nav[0].disabled, false);
assert.equal(nav[1].disabled, true);
assert.equal(count.textContent, '2/2');

const reel = new PublisherPreview({ format: 'reel', draft: {
  ...draft,
  media: [media[0]],
  music: { title: 'Piste choisie' },
  design: { format: { width: 1080, height: 1920 }, elements: [
    { type: 'text', text: 'Texte sur le Reel', x: 540, y: 960, size: 72 },
    { type: 'sticker', sticker: '🎉', x: 200, y: 200, w: 80, h: 80 },
  ] },
} })._render();
assert.match(reel, /class="pp-reel-poster"/);
assert.match(reel, /Piste choisie/);
assert.match(reel, /Texte sur le Reel/);
assert.match(reel, /🎉/);
assert.doesNotMatch(reel, /<source src="\/photos\/10\/file" type="image\/jpeg">/);

const story = new PublisherPreview({ format: 'story', draft })._render();
assert.match(story, /class="pp-story-user"/);
assert.match(story, /class="pp-story-reply"/);
assert.doesNotMatch(story, /pp-story-music/);

const storyWithMusic = new PublisherPreview({ format: 'story', draft: {
  ...draft,
  music: { trackId: 'a1', title: 'Run Free', artist: 'DJ X', source: 'instagram' },
} })._render();
assert.match(storyWithMusic, /class="pp-story-music"/);
assert.match(storyWithMusic, /Run Free/);
assert.match(storyWithMusic, /Sélectionnée · non intégrable à la publication actuelle/);

const storyLegacy = new PublisherPreview({ format: 'story', draft: {
  ...draft,
  design: { slides: [{}], designDocuments: [{ ig_audio: { audio_id: 'old1', title: 'Ancienne piste', artist: 'Avant' }, elements: [] }] },
} })._render();
assert.match(storyLegacy, /Ancienne piste/);
assert.match(storyLegacy, /non intégrable à la publication actuelle/);

const storyOverlay = new PublisherPreview({ format: 'story', draft: {
  ...draft,
  design: { slides: [{}], designDocuments: [{ elements: [
    { type: 'text', text: 'Bonjour 👋', x: 540, y: 960, size: 96, color: '#fff' },
    { type: 'sticker', text: '🔥', x: 200, y: 300, size: 80 },
  ] }] },
} })._render();
assert.match(storyOverlay, /Bonjour 👋/);
assert.match(storyOverlay, /font-size:8\.88888888888889cqw/);
assert.match(storyOverlay, /🔥/);

// Les éditions de texte/sticker/musique doivent réactualiser le visuel,
// même quand le store réutilise la même référence de brouillon.
const liveDraft = { ...draft, media: [media[0]], design: {}, music: {} };
const livePreview = new PublisherPreview({ format: 'reel', draft: liveDraft });
livePreview.element = { innerHTML: '', querySelector() { return null; } };
livePreview._visualSignature = livePreview._currentVisualSignature();
liveDraft.design.ig_audio = { title: 'Musique ajoutée' };
livePreview._updatePreview(liveDraft);
assert.match(livePreview.element.innerHTML, /Musique ajoutée/);

console.log('Aperçus Instagram post/carrousel/Reel/Story OK.');
