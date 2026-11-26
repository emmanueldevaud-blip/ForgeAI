// Tests de la CommunityPublisherPage — wiring evenements / etapes / publication.
// Exécution : node tests/frontend/community_publisher_page.test.mjs
import fs from 'node:fs';

const FILE = new URL('../../src/public/js/pages/CommunityPublisherPage.js', import.meta.url);
let src = fs.readFileSync(FILE, 'utf8');
src = src.replace(/^import\s[\s\S]*?from\s+['"][^'"]+['"];?\s*$/gm, '');
src = src.replace(/export class/g, 'class');
src = src.replace(/export function/g, 'function');

const failures = [];
function check(name, cond) {
  if (cond) console.log(`  OK ${name}`);
  else { failures.push(name); console.log(`  KO ${name}`); }
}

// --- Stub DOM : element factice avec recherche par attribut ---
function makeFake() {
  const handlers = {};
  const subs = new Map();
  const el = {
    className: '',
    children: [],
    _html: '',
    set innerHTML(v) { this._html = String(v); this.children = []; },
    get innerHTML() { return this._html; },
    appendChild(c) { el.children.push(c); return c; },
    addEventListener(type, handler) { (handlers[type] ||= []).push(handler); },
    querySelector(sel) {
      const cached = subs.get(sel);
      if (cached) return cached;
      for (const child of el.children) {
        const found = child.querySelector(sel);
        if (found) { subs.set(sel, found); return found; }
      }
      const created = makeFake();
      subs.set(sel, created);
      return created;
    },
    querySelectorAll(sel) {
      const cached = subs.get(sel);
      if (cached) return cached;
      const found = [];
      for (const child of el.children) found.push(...child.querySelectorAll(sel));
      if (found.length) { subs.set(sel, found); return found; }
      const created = [makeFake()];
      subs.set(sel, created);
      return created;
    },
    click() { (handlers.click || []).forEach(h => h({ stopPropagation() {} })); },
    __handlers: handlers,
    __subs: subs,
    dataset: {},
    disabled: false,
    textContent: '',
    style: {},
    classList: { add() {}, remove() {}, toggle() {} },
  };
  return el;
}

const documentStub = { createElement: () => makeFake() };

// --- Stubs store / services / createurs ---
const calls = { nextStep: 0, prevStep: 0, publish: 0, saveDraft: 0, routerNavigate: null, pickerMounted: false };
const listeners = new Set();
const publisherStoreStub = {
  draft: {
    format: 'post', media: [], design: {},
    caption: { title: '', content: '', hashtags: '', accountId: null },
    music: {}, garmin: { activityId: null, stats: {}, overlays: [] },
    status: 'draft',
  },
  ui: { currentStep: 'media', previewOpen: false, aiPanelOpen: false, formatSelectorOpen: false, accountSelectorOpen: false },
  subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  _notify() { listeners.forEach(fn => fn({ draft: this.draft, ui: this.ui })); },
  resetDraft() { this.ui.currentStep = 'media'; this._notify(); },
  setStep(step) { this.ui.currentStep = step; this._notify(); },
  nextStep() {
    calls.nextStep++;
    const all = ['media', 'adjust', 'compose', 'music', 'caption', 'preview', 'publish'];
    const idx = all.indexOf(this.ui.currentStep);
    if (idx >= 0 && idx < all.length - 1) {
      this.ui.currentStep = all[idx + 1];
      this._notify();
    }
  },
  prevStep() {
    calls.prevStep++;
    const all = ['media', 'adjust', 'compose', 'music', 'caption', 'preview', 'publish'];
    const idx = all.indexOf(this.ui.currentStep);
    if (idx > 0) {
      this.ui.currentStep = all[idx - 1];
      this._notify();
    }
  },
  clear() { calls.cleared = true; },
  updateCaption() {},
};
const publisherDraftServiceStub = {
  save: async () => { calls.saveDraft++; return ({}); },
  publish: async () => { calls.publish++; return { status: 'published' }; },
};
const createPublisherMediaPickerStub = () => {
  calls.pickerMounted = true;
  return { mount: () => {}, destroy: () => {} };
};
const createPublisherCaptionEditorStub = () => ({ mount: () => {}, destroy: () => {} });
const createPublisherPreviewStub = () => ({ mount: () => {}, destroy: () => {} });
const createPublisherReelEditorStub = () => ({ mount: () => {}, destroy: () => {} });
const createPublisherStoryEditorStub = () => ({ mount: () => {}, destroy: () => {} });
const createPublisherMusicStepStub = () => {
  calls.musicMounted = true;
  return { mount: () => {}, destroy: () => {} };
};
const routerStub = { navigate: (to) => { calls.routerNavigate = to; } };

const paramNames = [
  'publisherStore', 'publisherDraftService',
  'createPublisherMediaPicker', 'createPublisherCaptionEditor', 'createPublisherPreview',
  'createPublisherReelEditor', 'createPublisherStoryEditor',
  'document', 'router', 'createPublisherMusicStep',
];
const factory = new Function(...paramNames, `${src}\nreturn { CommunityPublisherPage, FORMAT_CONFIG };`);
const { CommunityPublisherPage, FORMAT_CONFIG } = factory(
  publisherStoreStub, publisherDraftServiceStub, createPublisherMediaPickerStub,
  createPublisherCaptionEditorStub, createPublisherPreviewStub, createPublisherReelEditorStub,
  createPublisherStoryEditorStub, documentStub, routerStub, createPublisherMusicStepStub,
);

function makePage() {
  calls.nextStep = 0; calls.prevStep = 0; calls.publish = 0; calls.saveDraft = 0;
  calls.routerNavigate = null; calls.pickerMounted = false; calls.musicMounted = false;
  return new CommunityPublisherPage(routerStub, { format: 'post' });
}

// --- Tests ---
{
  console.log('T1: render monte le media picker et wire le footer');
  const page = makePage();
  const el = page.render();
  check('T1: media picker monte sur l etape media', calls.pickerMounted === true);
  check('T1: bouton header Retour wired', (el.__subs.get('[data-action="back"]').__handlers.click || []).length > 0);
  check('T1: bouton Brouillon wired', (el.__subs.get('[data-action="save-draft"]').__handlers.click || []).length > 0);
  const nextBtn = el.__subs.get('[data-action="next-step"]');
  check('T1: bouton Suivant wired', (nextBtn.__handlers.click || []).length > 0);
  nextBtn.click();
  check('T1: Suivant sur media -> nextStep', calls.nextStep === 1);
}

{
  console.log('T2: footer final (etape publish) -> declenche la publication');
  const page = makePage();
  page.render();
  publisherStoreStub.ui.currentStep = 'publish';
  publisherStoreStub._notify();
  const publishHost = page.element.querySelector('[data-publish-host]');
  const publishBtn = publishHost.querySelector('[data-action="publish-final"]');
  publishBtn.click();
  check('T2: bouton Publier declenche _publish', calls.publish === 1);
}

{
  console.log('T3: bouton Retour header -> navigation back');
  const page = makePage();
  const el = page.render();
  el.__subs.get('[data-action="back"]').click();
  check('T3: retour -> navigate community-manager', calls.routerNavigate === '/community-manager');
}

{
  console.log('T4: etape music (story) — steps et montage');
  check('T4: FORMAT_CONFIG story contient music apres compose',
    JSON.stringify(FORMAT_CONFIG.story.steps) === JSON.stringify(['media', 'adjust', 'compose', 'music', 'caption', 'preview', 'publish']));
  check('T4: FORMAT_CONFIG reel sans music', !FORMAT_CONFIG.reel.steps.includes('music'));
  const page = new CommunityPublisherPage(routerStub, { format: 'story' });
  page.render();
  publisherStoreStub.ui.currentStep = 'music';
  publisherStoreStub._notify();
  check('T4: music step monte le PublisherMusicStep', calls.musicMounted === true);
  page.destroy();
  publisherStoreStub.ui.currentStep = 'media';
  publisherStoreStub._notify();
}

{
  console.log('T5: restauration etape — abonnement avant render (rechargement)');
  publisherStoreStub.draft.format = 'story';
  publisherStoreStub.ui.currentStep = 'music';
  const page = new CommunityPublisherPage(routerStub, { format: 'story' });
  publisherStoreStub._notify();
  check('T5: currentStep resync depuis le store avant render', page.currentStep === 'music');
  page.render();
  check('T5: premier rendu directement sur letape restauree', page._renderedStep === 'music');
  check('T5: pas de rendu media initial apres rechargement', page._renderedStep !== 'media');
  page.destroy();
  publisherStoreStub.ui.currentStep = 'caption';
  publisherStoreStub._notify();
  check('T5: destroy desabonne la page', page.currentStep === 'music');
  publisherStoreStub.draft.format = 'post';
  publisherStoreStub.ui.currentStep = 'media';
  publisherStoreStub._notify();
}

{
  console.log('T6: Suivant/Precedent depuis etape restauree — pas de decalage');
  publisherStoreStub.draft.format = 'story';
  publisherStoreStub.ui.currentStep = 'music';
  const page = new CommunityPublisherPage(routerStub, { format: 'story' });
  publisherStoreStub._notify();
  page.render();
  const nextBtn = page.element.querySelector('[data-action="next-step"]');
  nextBtn.click();
  check('T6: Suivant avance exactement d\'une etape (music -> caption)',
    publisherStoreStub.ui.currentStep === 'caption' && page.currentStep === 'caption'
    && page._renderedStep === 'caption');
  page._navLocked = false;
  const prevBtn = page.element.querySelector('[data-action="prev-step"]');
  prevBtn.click();
  check('T6: Precedent revient a music',
    publisherStoreStub.ui.currentStep === 'music' && page.currentStep === 'music'
    && page._renderedStep === 'music');
  page.destroy();
  publisherStoreStub.draft.format = 'post';
  publisherStoreStub.ui.currentStep = 'media';
  publisherStoreStub._notify();
}

{
  console.log('T7: abonnement unique — constructeur + render + destroy');
  const n0 = listeners.size;
  const page = new CommunityPublisherPage(routerStub, { format: 'post' });
  const n1 = listeners.size;
  page.render();
  const n2 = listeners.size;
  check('T7: +1 abonnement a la construction', n1 === n0 + 1);
  check('T7: render ne double pas abonnement', n2 === n1);
  page.destroy();
  check('T7: destroy retire abonnement', listeners.size === n0);
}

console.log(failures.length === 0 ? '\nTOUS LES TESTS PASSENT' : `\n${failures.length} ECHEC(S)`);
process.exit(failures.length === 0 ? 0 : 1);
