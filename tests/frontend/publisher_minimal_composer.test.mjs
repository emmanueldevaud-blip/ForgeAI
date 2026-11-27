// Tests du compositeur minimal : médias multiples, ordre, suppression, 3 calques de texte.
// Exécution : node tests/frontend/publisher_minimal_composer.test.mjs
import assert from 'node:assert/strict';
import fs from 'node:fs';

const root = new URL('../../', import.meta.url);
const read = (relative) => fs.readFileSync(new URL(relative, root), 'utf8');

function loadComposer(store, doc) {
  let src = read('src/public/js/components/PublisherMinimalComposer.js');
  src = src.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
  src = src.replace(/export function/g, 'function').replace(/export class/g, 'class');
  return new Function('publisherStore', 'document',
    `${src}\nreturn { normalizeTextLayers, buildOverlayTextElement, buildStoryDesign, buildReelDesign, PublisherMinimalComposer };`
  )(store, doc);
}

function fakeNode() {
  return {
    value: '', textContent: '', disabled: false, hidden: false, dataset: {},
    classList: { toggle() {}, add() {}, remove() {} },
    addEventListener(type, fn) { (this.handlers ||= {})[type] = fn; },
    focus() {}, setAttribute() {},
    click() { this.handlers?.click?.(); },
  };
}

function makeElement() {
  const nodes = new Map();
  return {
    innerHTML: '', parentNode: null,
    querySelector(sel) {
      if (!nodes.has(sel)) nodes.set(sel, fakeNode());
      return nodes.get(sel);
    },
    querySelectorAll() { return []; },
  };
}

function makeMedia() {
  return [
    { id: 'photo_11', photoId: 11, url: '/photos/11/file', thumbnail_url: '/photos/11/file?size=small', crop: { x: 0, y: 0, w: 1, h: 1 }, order: 0, type: 'photo' },
    { id: 'photo_12', photoId: 12, url: '/photos/12/file', thumbnail_url: '/photos/12/file?size=small', crop: { x: 0.1, y: 0.2, w: 0.8, h: 0.6 }, order: 1, type: 'photo' },
    { id: 'photo_13', photoId: 13, url: '/photos/13/file', thumbnail_url: '/photos/13/file?size=small', crop: { x: 0, y: 0, w: 1, h: 1 }, order: 2, type: 'photo' },
  ];
}

function makeStore(media, format = 'story') {
  return {
    draft: { format, media, design: {} },
    _notify() {},
    reorderMedia(from, to) {
      const [m] = this.draft.media.splice(from, 1);
      this.draft.media.splice(to, 0, m);
      this.draft.media.forEach((m, i) => { m.order = i; });
      this._notify();
    },
    removeMedia(id) {
      this.draft.media = this.draft.media.filter((m) => String(m.id) !== String(id));
      this.draft.media.forEach((m, i) => { m.order = i; });
      this._notify();
    },
    updateStorySlides(slides, designDocuments) {
      this.draft.design = { slides, designDocuments };
      this._notify();
    },
    updateDesign(design) {
      this.draft.design = design;
      this._notify();
    },
  };
}

console.log('1. Élément texte unique, centré');
{
  const { buildOverlayTextElement } = loadComposer(makeStore([]));
  const element = buildOverlayTextElement('Trail du dimanche');
  assert.equal(element.id, 'minimal-overlay-text');
  assert.equal(element.type, 'text');
  assert.equal(element.text, 'Trail du dimanche');
  assert.equal(element.x, 540);
  assert.equal(element.y, 960);
  assert.equal(element.align, 'center');
}

console.log('2. Story : une slide par média, texte uniquement sur la première');
{
  const { buildStoryDesign } = loadComposer(makeStore([]));
  const media = makeMedia().slice(0, 2);
  const story = buildStoryDesign(media, 'Trail du dimanche');
  assert.equal(story.slides.length, 2);
  assert.equal(story.designDocuments.length, 2);
  assert.equal(story.designDocuments[0].background.photo_id, 11);
  assert.equal(story.designDocuments[1].background.photo_id, 12);
  assert.equal(story.designDocuments[0].elements.length, 1);
  assert.equal(story.designDocuments[0].elements[0].text, 'Trail du dimanche');
  assert.equal(story.designDocuments[1].elements.length, 0);
  assert.deepEqual(story.designDocuments[1].background.crop, media[1].crop);
}

console.log('3. Story sans texte : aucun élément, structure conservée');
{
  const { buildStoryDesign } = loadComposer(makeStore([]));
  const storyEmpty = buildStoryDesign(makeMedia(), '   ');
  assert.equal(storyEmpty.slides.length, 3);
  assert.equal(storyEmpty.designDocuments[0].elements.length, 0);
}

console.log('4. Reel : design 9:16, un seul élément, données existantes préservées');
{
  const { buildReelDesign } = loadComposer(makeStore([], 'reel'));
  const reel = buildReelDesign({ ig_audio: { title: 'Run Free' }, elements: [{ id: 'old' }] }, 'Alpes');
  assert.equal(reel.format.width, 1080);
  assert.equal(reel.format.height, 1920);
  assert.equal(reel.elements.length, 1);
  assert.equal(reel.elements[0].text, 'Alpes');
  assert.equal(reel.ig_audio.title, 'Run Free');
  assert.deepEqual(buildReelDesign({}, '').elements, []);
}

console.log('5. Non-régression Étape 1 : quatre formats, anti-double-clic, aucun éditeur lourd');
{
  const page = read('src/public/js/pages/CommunityPublisherPage.js');
  assert.match(page, /post:\s*\{[\s\S]*carousel:\s*\{[\s\S]*reel:\s*\{[\s\S]*story:\s*\{/);
  assert.match(page, /_navLock\(/);
  assert.match(page, /createPublisherMinimalComposer\(/);
  assert.doesNotMatch(page, /createPublisherStoryEditor\(|createPublisherReelEditor\(/);
  assert.match(page, /_saveCompose\(\);\s*publisherStore\.prevStep\(\)/, 'Précédent sauvegarde le compose');
  assert.match(page, /_goBack\(\)\s*\{\s*this\._saveCompose\(\)/, 'Retour sauvegarde le compose');
  assert.match(page, /async _saveDraft\(\)\s*\{\s*try\s*\{\s*this\._saveCompose\(\)/, 'Brouillon sauvegarde le compose');
  const css = read('src/public/css/publisher.css');
  assert.match(css, /\.pmc-media-strip\s*\{/);
  assert.match(css, /\.pmc-media-count\s*\{/, 'badge de média positionné');
  assert.doesNotMatch(css, /\.pmc-textarea\s*\{/, 'aucun style de champ de saisie mort');
  assert.doesNotMatch(css, /\.pmc-panel-footer\s*\{/, 'aucun pied de panneau mort');
}

console.log('6. Story : trois médias -> trois slides dans l’ordre, identifiants conservés');
{
  const { buildStoryDesign } = loadComposer(makeStore([]));
  const story = buildStoryDesign(makeMedia(), 'Trail');
  assert.deepEqual(story.designDocuments.map((d) => d.background.photo_id), [11, 12, 13]);
  assert.deepEqual(story.slides.map((s) => s.photo_indices[0]), [0, 1, 2]);
  assert.deepEqual(story.designDocuments.map((d) => d.carousel[0]), [11, 12, 13]);
  assert.equal(story.designDocuments.filter((d) => d.elements.length > 0).length, 1);
}

console.log('7. Composer Story : aperçu, ordre et suppression resynchronisent le design');
{
  const store = makeStore(makeMedia());
  const { PublisherMinimalComposer } = loadComposer(store, {
    createElement: () => makeElement(),
  });
  const composer = new PublisherMinimalComposer({ format: 'story' });
  const host = {
    child: null,
    appendChild(el) { el.parentNode = this; this.child = el; },
    removeChild(el) { if (this.child === el) this.child = null; },
  };
  composer.mount(host);

  assert.match(composer.element.innerHTML, /data-pmc-preview/);
  assert.match(composer.element.innerHTML, /data-photo-id="11"/);
  assert.match(composer.element.innerHTML, /data-photo-id="13"/);
  assert.match(composer.element.innerHTML, /data-action="pmc-remove"/);
  assert.doesNotMatch(composer.element.innerHTML, /<textarea/, 'aucun champ de saisie dans le Composer');
  assert.match(composer.element.innerHTML, /contenteditable="true"/, 'le texte est édité sur la photo');
  assert.match(composer.element.innerHTML, /data-pmc-overlay-actions/, 'actions tactiles sur le calque');
  assert.equal(
    (composer.element.innerHTML.match(/data-pmc-overlay-actions/g) || []).length,
    1,
    'une seule barre d’actions, pas une par calque',
  );
  assert.doesNotMatch(composer.element.innerHTML, /data-action="pmc-clear"/, 'pas de double action « effacer »');
  assert.match(composer.element.innerHTML, /aria-multiline="true"/);
  assert.match(composer.element.innerHTML, /Média 1 \/ 3/, 'compteur de média visible dans l’aperçu');

  composer.element.querySelector('[data-pmc-text]').value = 'Trail du dimanche';
  composer.save();
  assert.equal(store.draft.design.designDocuments[0].elements[0].text, 'Trail du dimanche');

  composer._selectMedia(2);
  assert.equal(composer.activeIndex, 2);
  composer._moveMedia(2, -1);
  assert.deepEqual(store.draft.media.map((m) => String(m.photoId)), ['11', '13', '12']);
  assert.equal(composer.activeIndex, 1, 'l’aperçu suit le média déplacé');
  assert.deepEqual(store.draft.design.designDocuments.map((d) => d.background.photo_id), [11, 13, 12]);
  assert.equal(store.draft.design.designDocuments[0].elements[0].text, 'Trail du dimanche');

  composer._removeMedia(composer.activeIndex);
  assert.deepEqual(store.draft.media.map((m) => String(m.photoId)), ['11', '12']);
  assert.deepEqual(store.draft.design.designDocuments.map((d) => d.background.photo_id), [11, 12]);
  assert.deepEqual(store.draft.media.map((m) => m.order), [0, 1]);

  composer.destroy();
  assert.equal(host.child, null);
}

console.log('8. Store réel : photoId serveur conservé lors de l’ajout de médias');
{
  let src = read('src/public/js/stores/publisherStore.js').replace(/^export /gm, '');
  const localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  const { publisherStore } = new Function('localStorage', `${src}\nreturn { publisherStore };`)(localStorage);
  publisherStore.addMedia([
    { id: 11, photoId: 11, url: '/photos/11/file' },
    { id: 'photo_12', url: '/photos/12/file' },
  ]);
  assert.equal(publisherStore.draft.media[0].photoId, 11);
  assert.equal(publisherStore.draft.media[1].photoId, 'photo_12');
  publisherStore.reorderMedia(1, 0);
  publisherStore.removeMedia('photo_12');
  assert.equal(publisherStore.draft.media.length, 1);
  assert.equal(publisherStore.draft.media[0].photoId, 11);
}

console.log('9. Trois calques : identifiants stables, positions fixes, limite de 3');
{
  const { normalizeTextLayers, buildOverlayTextElement } = loadComposer(makeStore([]));
  const ids = ['minimal-overlay-text', 'minimal-overlay-text-2', 'minimal-overlay-text-3'];
  assert.deepEqual(normalizeTextLayers(['A', 'B', 'C']).map((l) => l.id), ids);
  assert.deepEqual(normalizeTextLayers(['A', 'B', 'C', 'D']).map((l) => l.text), ['A', 'B', 'C']);
  const layers = [0, 1, 2].map((slot) => buildOverlayTextElement(`T${slot}`, slot));
  assert.deepEqual(layers.map((l) => l.id), ids);
  assert.deepEqual(layers.map((l) => l.y), [960, 760, 1160]);
  assert.ok(layers.every((l) => l.type === 'text' && l.x === 540 && l.align === 'center'));
}

console.log('10. Design v2 : trois éléments texte ordonnés, métadonnées conservées');
{
  const { normalizeTextLayers, buildStoryDesign, buildReelDesign } = loadComposer(makeStore([]));
  const layers = normalizeTextLayers(['Un', 'Deux', 'Trois']);
  const story = buildStoryDesign(makeMedia(), layers);
  assert.deepEqual(story.designDocuments[0].elements.map((e) => e.text), ['Un', 'Deux', 'Trois']);
  assert.deepEqual(story.designDocuments.map((d) => d.elements.length), [3, 0, 0]);
  assert.deepEqual(story.designDocuments[0].elements.map((e) => e.y), [960, 760, 1160]);
  assert.equal(story.designDocuments[0].background.photo_id, 11);
  assert.deepEqual(story.designDocuments[0].carousel, [11]);

  const existing = { ig_audio: { title: 'Run Free' }, format: { width: 1 }, extra: 'conservé' };
  const reel = buildReelDesign(existing, layers);
  assert.deepEqual(reel.elements.map((e) => e.text), ['Un', 'Deux', 'Trois']);
  assert.equal(reel.ig_audio.title, 'Run Free');
  assert.equal(reel.extra, 'conservé');
  assert.deepEqual(reel.format, { width: 1080, height: 1920, type: 'reel_916', platform: 'instagram' });
}

console.log('11. Composer Story : ajout, limite, ordre d’empilement, aperçu et suppression');
{
  const store = makeStore(makeMedia());
  const { PublisherMinimalComposer } = loadComposer(store, { createElement: () => makeElement() });
  const composer = new PublisherMinimalComposer({ format: 'story' });
  const host = {
    child: null,
    appendChild(el) { el.parentNode = this; this.child = el; },
    removeChild(el) { if (this.child === el) this.child = null; },
  };
  composer.mount(host);
  assert.match(composer.element.innerHTML, /Calques de texte \(1 \/ 3\)/);
  assert.match(composer.element.innerHTML, /data-pmc-layer-limit hidden/);
  assert.doesNotMatch(composer.element.innerHTML, /<textarea/, 'aucun champ de saisie');

  composer.layers[0].text = 'Un';
  assert.equal(composer._addLayer(), true);
  composer.layers[1].text = 'Deux';
  assert.equal(composer._addLayer(), true);
  composer.layers[2].text = 'Trois';
  assert.equal(composer._addLayer(), false, 'aucun quatrième calque');
  composer._writeDesign();
  composer._render();
  assert.equal(
    (composer.element.innerHTML.match(/data-index="\d+"[^>]*data-pmc-layer-text=/g) || []).length,
    3,
    'chaque calque porte son index : la frappe cible le bon calque',
  );
  assert.match(composer.element.innerHTML, /Limite de 3 calques atteinte/);
  assert.deepEqual(composer.layers.map((l) => l.text), ['Un', 'Deux', 'Trois']);
  assert.deepEqual(store.draft.design.designDocuments[0].elements.map((e) => e.text), ['Un', 'Deux', 'Trois']);

  const overlays = Array.from(composer.element.innerHTML.matchAll(
    /data-pmc-overlay data-layer-index="(\d+)"[^>]*>([^<]*)</g,
  )).map((match) => match[2]);
  assert.deepEqual(overlays, ['Un', 'Deux', 'Trois'], 'tous les calques sont dans l’aperçu');

  composer._selectLayer(1);
  assert.equal(composer.activeLayerIndex, 1);
  assert.equal(
    composer.element.querySelector('[data-pmc-overlay-actions]').dataset.index,
    '1',
    'la barre d’actions suit le calque actif',
  );
  composer._selectLayer(0);
  assert.equal(composer.activeLayerIndex, 0);
  composer._moveLayer(0, 1);
  assert.deepEqual(composer.layers.map((l) => l.text), ['Deux', 'Un', 'Trois']);
  assert.equal(store.draft.design.designDocuments[0].elements[0].text, 'Deux');
  composer._moveLayer(2, -1);
  assert.deepEqual(composer.layers.map((l) => l.text), ['Deux', 'Trois', 'Un']);
  composer._removeLayer(0);
  assert.deepEqual(composer.layers.map((l) => l.text), ['Trois', 'Un']);
  assert.deepEqual(store.draft.design.designDocuments[0].elements.map((e) => e.text), ['Trois', 'Un']);
  composer.destroy();
  assert.equal(host.child, null);
}

console.log('12. Composer Reel : calques multiples sans altérer ig_audio ni le format 9:16');
{
  const media = [{ id: 'video_1', type: 'video', url: '/videos/1.mp4', order: 0 }];
  const store = makeStore(media, 'reel');
  store.draft.design = { ig_audio: { title: 'Run Free' }, extra: { keep: true } };
  const { PublisherMinimalComposer } = loadComposer(store, { createElement: () => makeElement() });
  const composer = new PublisherMinimalComposer({ format: 'reel' });
  composer.mount({ appendChild(el) { el.parentNode = this; } });
  assert.match(composer.element.innerHTML, /data-pmc-media-strip hidden/, 'un seul média : bande masquée');
  composer.layers[0].text = 'Alpes';
  composer._addLayer();
  composer.layers[1].text = 'Dimanche';
  composer._writeDesign();
  assert.deepEqual(store.draft.design.elements.map((e) => e.text), ['Alpes', 'Dimanche']);
  assert.equal(store.draft.design.ig_audio.title, 'Run Free');
  assert.deepEqual(store.draft.design.extra, { keep: true });
  assert.equal(store.draft.design.format.height, 1920);
}

console.log('13. Outils Story : style complet dans l’élément de design v2');
{
  const { normalizeTextLayers, buildOverlayTextElement } = loadComposer(makeStore([]));
  const layer = normalizeTextLayers([{
    id: 'minimal-overlay-text',
    text: 'Style',
    style: {
      color: '#ff3b5c', font: 'Georgia', bold: false, italic: true, underline: true,
      align: 'right', background: true, backgroundColor: '#123456', size: 110, rotation: -25,
    },
  }])[0];
  assert.deepEqual(layer.style, {
    color: '#ff3b5c', font: 'Georgia', bold: false, italic: true, underline: true,
    align: 'right', background: true, backgroundColor: '#123456', size: 110, rotation: -25,
  });
  const element = buildOverlayTextElement(layer.text, 0, layer.style);
  for (const key of ['font', 'color', 'bold', 'italic', 'underline', 'align', 'background', 'backgroundColor', 'size', 'rotation']) {
    assert.equal(element[key], layer.style[key], `${key} est exporté dans le design`);
  }
  assert.equal(buildOverlayTextElement('x', 0, { font: 'Comic Sans', color: 'red', size: 9999 }).font, 'Arial', 'police inconnue repliée');
  assert.equal(buildOverlayTextElement('x', 0, { size: 9999 }).size, 220, 'taille bornée');
}

console.log('14. Story : 3 calques indépendants par photo, ordre et styles préservés');
{
  const store = makeStore(makeMedia());
  const { PublisherMinimalComposer } = loadComposer(store, { createElement: () => makeElement() });
  const composer = new PublisherMinimalComposer({ format: 'story' });
  composer.mount({ appendChild(el) { el.parentNode = this; } });

  composer.layers[0].text = 'Photo 1';
  composer._applyStyle('color', '#34c759');
  composer._selectMedia(1);
  composer.layers[0].text = 'Photo 2';
  composer._applyStyle('font', 'Impact');
  composer._applyStyle('bold');
  composer._selectMedia(0);
  assert.equal(store.draft.design.designDocuments[0].elements[0].text, 'Photo 1');
  assert.equal(store.draft.design.designDocuments[0].elements[0].color, '#34c759');
  assert.equal(store.draft.design.designDocuments[1].elements[0].text, 'Photo 2');
  assert.equal(store.draft.design.designDocuments[1].elements[0].font, 'Impact');
  assert.equal(store.draft.design.designDocuments[1].elements[0].bold, false, 'bascule gras');
  assert.equal(store.draft.design.designDocuments[2].elements.length, 0);

  composer._addLayer();
  composer.layers[1].text = 'P1-2';
  composer._writeDesign();
  assert.equal(store.draft.design.designDocuments[0].elements.length, 2);
  assert.equal(store.draft.design.designDocuments[1].elements.length, 1, 'les calques des autres photos sont intacts');

  // Le DOM factice ne expose pas les noeuds de calques : le repli de save()
  // relit le premier calque depuis [data-pmc-text].
  composer.element.querySelector('[data-pmc-text]').value = 'Photo 1';
  composer._moveMedia(1, -1);
  assert.equal(store.draft.design.designDocuments[0].elements[0].text, 'Photo 2', 'les calques suivent la photo déplacée');
  assert.equal(store.draft.design.designDocuments[1].elements[0].text, 'Photo 1');
}

console.log('15. Story : mini-barre et poignées présentes, Reel : outils masqués');
{
  const storyStore = makeStore(makeMedia().slice(0, 1));
  const storyClass = loadComposer(storyStore, { createElement: () => makeElement() }).PublisherMinimalComposer;
  const story = new storyClass({ format: 'story' });
  story.mount({ appendChild(el) { el.parentNode = this; } });
  assert.match(story.element.innerHTML, /data-pmc-style-row/, 'barre d’outils sur la photo');
  assert.match(story.element.innerHTML, /data-style="color"/);
  assert.match(story.element.innerHTML, /data-style="underline"/);
  assert.match(story.element.innerHTML, /data-style="background"/);
  assert.equal((story.element.innerHTML.match(/data-pmc-handle/g) || []).length, 4, '4 poignées sur le calque');

  const reelStore = makeStore([{ id: 'video_1', type: 'video', url: '/v/1', order: 0 }], 'reel');
  const reelClass = loadComposer(reelStore, { createElement: () => makeElement() }).PublisherMinimalComposer;
  const reel = new reelClass({ format: 'reel' });
  reel.mount({ appendChild(el) { el.parentNode = this; } });
  assert.doesNotMatch(reel.element.innerHTML, /data-pmc-style-row/, 'aucun outil sans rendu final Reel');
  assert.doesNotMatch(reel.element.innerHTML, /data-pmc-handle/);
  assert.match(reel.element.innerHTML, /data-pmc-overlay-actions/, 'l’ordre/suppression des calques reste disponible');
}

console.log('16. Export Story : souligné et fond réellement dessinés dans le canvas');
{
  let src = read('src/public/js/editor/editorCanvas.js');
  src = src.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
  src = src.replace(/export class/g, 'class');
  const EditorCanvas = new Function('filterCss', `${src}\nreturn EditorCanvas;`)(() => 'none');
  const canvas = new EditorCanvas({ state: {} });
  const calls = [];
  const ctx = new Proxy({
    fillStyle: '', strokeStyle: '', font: '', textBaseline: '', textAlign: '',
    shadowColor: '', shadowBlur: 0, shadowOffsetY: 0, lineWidth: 1,
    save() {}, restore() {}, translate() {}, rotate() {}, beginPath() {},
    rect(...args) { calls.push(['rect', args]); },
    roundRect(...args) { calls.push(['roundRect', args]); },
    fill() { calls.push(['fill', this.fillStyle]); },
    fillText(text, x, y) { calls.push(['text', text, x, y]); },
    measureText(text) { return { width: String(text).length * 20 }; },
    moveTo(x, y) { calls.push(['moveTo', x, y]); },
    lineTo(x, y) { calls.push(['lineTo', x, y]); },
    stroke() { calls.push(['stroke', this.strokeStyle]); },
  }, {
    set(target, key, value) { target[key] = value; return true; },
  });
  canvas._mctx = { font: '', measureText(text) { return { width: String(text).length * 20 }; } };
  canvas._drawText(ctx, {
    id: 'x', type: 'text', text: 'Ligne', x: 540, y: 960, w: 864, h: 180,
    size: 72, font: 'Arial', color: '#ffffff', bold: true, italic: false,
    underline: true, align: 'center', background: true, backgroundColor: '#123456',
    shadow: true, opacity: 1, rotation: 0,
  });
  assert.ok(calls.some(([name]) => name === 'roundRect' || name === 'rect'), 'fond dessiné');
  assert.ok(calls.some(([name, color]) => name === 'fill' && color === 'rgba(18,52,86,0.65)'), 'couleur de fond appliquée');
  assert.ok(calls.some(([name, text]) => name === 'text' && text === 'Ligne'), 'texte dessiné');
  assert.equal(calls.filter(([name]) => name === 'stroke').length, 1, 'souligné dessiné');
  assert.equal(calls.filter(([name]) => name === 'stroke')[0][1], '#ffffff', 'souligné de la couleur du texte');
}

console.log('\nCompositeur minimal (médias multiples + calques de texte) OK.');
