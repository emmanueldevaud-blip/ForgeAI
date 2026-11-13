// Tests de l'éditeur graphique V1 (state, géométrie, vue) — DOM factice.
// Exécution : node tests/frontend/editor_v1.test.mjs
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const editorDir = path.join(here, '../../src/public/js/editor');

let failures = 0;
const check = (label, cond, extra = '') => {
  if (cond) console.log(`  ok - ${label}`);
  else {
    failures++;
    console.log(`  FAIL - ${label} ${extra}`);
  }
};

// Chargement des modules purs (imports résolus par Node via file URL)
const { EditorState, defaultDesign, normalizeDesign, FORMATS, filterCss } = await import(
  path.join(editorDir, 'editorState.js')
);
const geo = await import(path.join(editorDir, 'editorGeometry.js'));

// ------------------------------------------------------------------
// editorGeometry
// ------------------------------------------------------------------
console.log('editorGeometry');
{
  const r = geo.rotatePoint(10, 0, 0, 0, 90);
  check('rotatePoint 90°', Math.abs(r.x) < 1e-9 && Math.abs(r.y - 10) < 1e-9);

  const el = { x: 100, y: 100, w: 50, h: 20, rotation: 90 };
  const inside = geo.hitTest(100, 90, el);
  const outside = geo.hitTest(120, 100, el);
  check('hitTest tient compte de la rotation', inside === true && outside === false);

  // Resize aspect sur une image carrée : handle 'e' tiré à x=150
  // (ancre ouest à -50 → nouvelle largeur 200, centre à 50).
  const img = { x: 0, y: 0, w: 100, h: 100, rotation: 0 };
  const next = geo.solveResize(img, 'e', 150, 0, { aspect: true, minSize: 10 });
  check('solveResize aspect conserve le ratio', Math.abs(next.w - next.h) < 1e-6, JSON.stringify(next));
  check(
    "solveResize l'ancre ouest reste fixe (x - w/2 = -50)",
    Math.abs(next.x - next.w / 2 - -50) < 1e-6,
    `x=${next.x} w=${next.w}`
  );

  const c1 = geo.clampCrop({ x: -1, y: 0.5, w: 5, h: 0.001 });
  check('clampCrop borné0..1', c1.x >= 0 && c1.w <= 1 && c1.h >= 0.05, JSON.stringify(c1));

  // Élément décentré + roté : ancre 'nw' fixe lors d'un resize
  const off = { x: 300, y: 200, w: 100, h: 60, rotation: 30 };
  const r2 = geo.solveResize(off, 'nw', 250, 170, { aspect: false, minSize: 10 });
  const anchorBefore = geo.handlePoint(off, 'se'); // coin opposé = ancre de 'nw'
  const el2 = { ...off, ...r2 };
  const anchorAfter = geo.handlePoint(el2, 'se');
  check(
    "solveResize ancre fixe hors origine + rotation",
    Math.abs(anchorBefore.x - anchorAfter.x) < 1e-6 &&
      Math.abs(anchorBefore.y - anchorAfter.y) < 1e-6,
    `avant=${JSON.stringify(anchorBefore)} après=${JSON.stringify(anchorAfter)}`
  );

  const crop = geo.solveCrop({ x: 0, y: 0, w: 1, h: 1 }, 'e', 25, 0, 100, 100);
  check('solveCrop réduit le bord droit', crop.w < 1 && crop.x === 0, JSON.stringify(crop));

  const cc = geo.coverCrop(200, 100, 100, 100);
  check('coverCrop recadre en hauteur', Math.abs(cc.w - 0.5) < 0.01 && Math.abs(cc.h - 1) < 0.01, JSON.stringify(cc));

  const scaled = geo.scaleDesign(defaultDesign('ig_feed_11'), 1080, 1920);
  check(
    'scaleDesign adapte dimensions',
    scaled.format.width === 1080 && scaled.format.height === 1920
  );
}

// ------------------------------------------------------------------
// editorState
// ------------------------------------------------------------------
console.log('editorState');
{
  const s = new EditorState();
  check('design par défaut feed 4:5', s.design.format.type === 'feed_45');
  check('aucun élément', s.design.elements.length === 0);

  const t = s.addElement({ type: 'text', text: 'Salut', x: 10, y: 10, w: 100, h: 40, size: 20 });
  check('ajout texte', s.design.elements.length === 1 && s.selectedId === t.id);

  s.updateElement(t.id, { text: 'Bonjour' });
  check('mise à jour', s.selected.text === 'Bonjour');

  const st = s.addElement({ type: 'sticker', sticker: '🔥', x: 0, y: 0, w: 50, h: 50 });
  check('ajout sticker au-dessus', s.design.elements[1].id === st.id);

  s.moveLayer(t.id, 'up');
  check('calque monte', s.design.elements[1].id === t.id);
  s.moveLayer(t.id, 'down');
  check('calque redescend', s.design.elements[0].id === t.id);

  s.removeElement(st.id);
  check('suppression', s.design.elements.length === 1);

  // undo/redo
  s.addElement({ type: 'sticker', sticker: '⭐', x: 0, y: 0, w: 40, h: 40 });
  check('état avant undo (2 éléments)', s.design.elements.length === 2);
  s.undo();
  check('undo retire le sticker', s.design.elements.length === 1);
  s.redo();
  check('redo rétablit', s.design.elements.length === 2);

  // transactions continues (geste) : un seul undo
  s.beginTransaction();
  const id = s.design.elements[0].id;
  s.updateElementLive(id, { x: 5 });
  s.updateElementLive(id, { x: 9 });
  s.commitTransaction();
  const before = s.design.elements.length;
  s.undo();
  check('transaction = un seul undo', s.design.elements.length === before && s.design.elements[0].x !== 9);

  // format
  s.setFormat('ig_story');
  check(
    'setFormat story 9:16',
    s.design.format.type === 'story_916' &&
      s.design.format.width === 1080 &&
      s.design.format.height === 1920
  );

  // carrousel
  s.setCarousel([1, 2, 3]);
  s.setCover(2);
  check('carrousel + couverture', s.design.carousel.join(',') === '1,2,3' && s.design.cover === 2);

  // normalize
  const n = normalizeDesign({ format: { type: 'ig_feed_11' }, elements: null });
  check('normalizeDesign répare', n && n.format.width === 1080 && Array.isArray(n.elements) && n.elements.length === 0);
  check('normalizeDesign rejette le vide', normalizeDesign(null) === null && normalizeDesign({}) === null);

  check('FORMATS contient IG et FB', FORMATS.some((f) => f.platform === 'instagram') && FORMATS.some((f) => f.platform === 'facebook'));
  check('filterCss inconnu → none', filterCss('zzz') === 'none' && filterCss('bw') === 'grayscale(100%)');
}

// ------------------------------------------------------------------
// StudioEditorView (sans montage : logique métier)
// ------------------------------------------------------------------
console.log('StudioEditorView');
{
  // Stub Image pour _setBackgroundPhoto
  globalThis.Image = class {
    set src(v) {
      this._src = v;
      this.naturalWidth = 100;
      this.naturalHeight = 100;
      queueMicrotask(() => this.onload && this.onload());
    }
    get src() {
      return this._src;
    }
  };

  const calls = [];
  const record = (name, fn) => (...args) => {
    calls.push([name, ...args]);
    return fn ? fn(...args) : undefined;
  };

  const { StudioEditorView } = await import(path.join(editorDir, 'StudioEditorView.js'));

  const makeView = (publication = { id: 5, design: null, photo_locked: false }) => {
    calls.length = 0;
    const view = new StudioEditorView({
      publication,
      deps: {
        updateDraft: record('updateDraft', async () => ({})),
        uploadPhotos: record('uploadPhotos', async () => ({ items: [{ id: 77 }] })),
        getSuggestedPhotos: record('getSuggestedPhotos', async () => []),
        listPhotos: record('listPhotos', async () => ({ items: [] })),
        photoFileUrl: (id, size) => `/photos/${id}/file?size=${size}`,
        publicationPhotoUrl: (id) => `/photos/${id}/file?size=medium`,
      },
      callbacks: {
        onClose: record('close'),
        onApplied: record('applied'),
      },
    });
    // canvas factice pour l'export
    view.canvas = {
      exportBlob: record('exportBlob', async () => new Blob(['x'], { type: 'image/jpeg' })),
      ensureImages: async () => {},
      requestRender() {},
      destroy() {},
      overlayMode: 'select',
    };
    view.root = null; // pas de DOM : _setStatus tolère root null
    return view;
  };

  // A : sauvegarde du design
  {
    const v = makeView();
    v.state.addElement({ type: 'text', text: 'T', x: 10, y: 10, w: 100, h: 40, size: 20 });
    await v._saveDesign();
    const upd = calls.find((c) => c[0] === 'updateDraft');
    check('A: enregistre le design via updateDraft', !!upd && upd[1] === 5 && upd[2]?.design?.elements?.length === 1, JSON.stringify(upd));
    check('A: publication mise à jour en mémoire', Array.isArray(v.publication.design?.elements));
  }

  // B : apply → export → upload → photo_id + design
  {
    const v = makeView();
    v.state.addElement({ type: 'sticker', sticker: '🔥', x: 0, y: 0, w: 50, h: 50 });
    await v._apply();
    const up = calls.find((c) => c[0] === 'uploadPhotos');
    const upd = calls.find((c) => c[0] === 'updateDraft');
    check('B: export uploadé', !!up);
    check('B: updateDraft reçoit photo_id=77 + design', upd?.[2]?.photo_id === 77 && Array.isArray(upd?.[2]?.design?.elements), JSON.stringify(upd?.[2]));
    check('B: visual_type photo', upd?.[2]?.visual_type === 'photo');
    check('B: callback onApplied', calls.some((c) => c[0] === 'applied'));
  }

  // B2 : photo verrouillée → pas de photo_id dans le patch
  {
    const v = makeView({ id: 5, design: null, photo_locked: true });
    await v._apply();
    const upd = calls.find((c) => c[0] === 'updateDraft');
    check('B2: verrou photo → patch sans photo_id', !!upd && !('photo_id' in upd[2]), JSON.stringify(upd?.[2]));
  }

  // C : action cover → updateDraft photo_id
  {
    const v = makeView();
    await v._onAction('cover', { photoId: 42 });
    const upd = calls.find((c) => c[0] === 'updateDraft');
    check('C: couverture → photo_id=42', upd?.[2]?.photo_id === 42, JSON.stringify(upd?.[2]));
  }

  // D : action set-bg → élément image de fond ajouté au design
  {
    const v = makeView();
    await v._onAction('set-bg', { photoId: 12 });
    const bg = v.state.design.elements.find((e) => e.type === 'image' && e.isBackground);
    check('D: image de fond ajoutée', !!bg && bg.photoId === 12, JSON.stringify(v.state.design.elements));
    check('D: crop cover appliqué', !!bg?.crop && bg.crop.w <= 1);
    const src = v.deps.photoFileUrl(12, 'medium');
    check('D: src construit via photoFileUrl', bg?.src === src, bg?.src);
  }

  // E : add-carrousel puis cover null → couverture auto
  {
    const v = makeView();
    await v._onAction('add-carousel', { photoId: 3 });
    await v._onAction('add-carousel', { photoId: 9 });
    check('E: carrousel [3,9]', v.state.design.carousel.join(',') === '3,9');
    check('E: couverture auto = première photo', v.state.design.cover === 3);
    await v._onAction('add-carousel', { photoId: 3 });
    check('E: pas de doublon', v.state.design.carousel.length === 2);
  }

  // F : fermeture sans DOM
  {
    const v = makeView();
    v.destroy();
    check('F: destroy sans DOM sans erreur', true);
  }
}

console.log(failures === 0 ? '\nTOUS LES TESTS PASSENT' : `\n${failures} ÉCHEC(S)`);
process.exit(failures === 0 ? 0 : 1);
